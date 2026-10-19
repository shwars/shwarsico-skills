"""Create and prepare self-contained sprite theaters; never calls an image API."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

SKILL = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL / "assets/templates"
spec = importlib.util.spec_from_file_location("sprite_timeline", TEMPLATES / "pygame/timeline.py")
timeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timeline)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def local_file(root, value):
    if not isinstance(value, str) or not value or ":" in value or "\\" in value:
        raise ValueError("Expected a project-relative slash path: " + str(value))
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Missing or nonlocal resource: " + value)
    return path


def skeleton():
    return {
        "version": 1, "title": "Кукольный спектакль", "subtitle": "Адаптация текста",
        "end_title": "Занавес", "stage": {"width": 1516, "height": 680, "chars_per_second": 32, "curtain_seconds": 2.4},
        "presentation": {"logical_size": [1600, 900], "theme": {"paper": "#f4e8d0", "ink": "#392a20", "gold": "#bf9652", "curtain": "#6e2433"}},
        "characters": {"narrator": {"name": "Рассказчик", "color": "#6b5947"}},
        "adaptation_notes": [], "scenes": [],
    }


def init_project(root, backend, overwrite=False, demo=False):
    root = root.resolve()
    if root.exists() and any(root.iterdir()) and (not overwrite or demo):
        raise ValueError("Output is not empty. Use a new folder; --overwrite replaces template code only, --demo requires an empty folder.")
    root.mkdir(parents=True, exist_ok=True)
    for folder in [TEMPLATES / "common"] + [TEMPLATES / b for b in ("pygame", "web") if backend in (b, "both")]:
        for source in folder.rglob("*"):
            if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
                continue
            target = root / source.relative_to(folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    if not (root / "script.json").exists():
        write_json(root / "script.json", skeleton())
    if not (root / "assets/manifest.json").exists():
        write_json(root / "assets/manifest.json", {"version": 1, "fonts": {
            "regular": "assets/fonts/PT_Sans-Web-Regular.ttf", "bold": "assets/fonts/PT_Sans-Web-Bold.ttf", "license": "assets/fonts/OFL.txt"}, "assets": {}})
    actual = "both" if (root / "main.py").exists() and (root / "index.html").exists() else backend
    write_json(root / "project.json", {"version": 1, "backend": actual})
    if demo:
        make_demo(root)
        prepare_project(root)
    return {"project": str(root), "backend": actual, "demo": demo}


def check_project(root):
    from PIL import Image
    root = root.resolve()
    story = timeline.validate_story(read_json(root / "script.json"))
    manifest = read_json(root / "assets/manifest.json")
    if manifest.get("version") != 1 or not isinstance(manifest.get("assets"), dict):
        raise ValueError("Unsupported/invalid asset manifest")
    presentation = story.get("presentation", {})
    size = presentation.get("logical_size", [1600, 900])
    if len(size) != 2 or any(not isinstance(n, int) or n < 480 for n in size):
        raise ValueError("presentation.logical_size must contain two integers >= 480")
    for color in list(presentation.get("theme", {}).values()) + [c.get("color", "#392a20") for c in story["characters"].values()]:
        if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
            raise ValueError("Colors must use #RRGGBB")
        try:
            int(color[1:], 16)
        except ValueError:
            raise ValueError("Invalid color " + color) from None
    fonts = manifest.get("fonts", {})
    for role in ("regular", "bold", "license"):
        local_file(root, fonts.get(role))
    warnings = []
    assets = manifest["assets"]
    for ident, asset in assets.items():
        kind = asset.get("kind")
        if kind not in ("character", "prop", "background"):
            raise ValueError("Unknown asset kind: " + ident)
        path = local_file(root, asset.get("file"))
        with Image.open(path) as raw:
            image = raw.convert("RGBA")
            width, height = image.size
            asset["size"] = [width, height]
            asset["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            if kind == "background":
                asset["bounds"] = [0, 0, width, height]
            else:
                if raw.format != "PNG":
                    raise ValueError("Sprites/props must be PNG: " + ident)
                alpha = image.getchannel("A")
                low, high = alpha.getextrema()
                bounds = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
                if low != 0 or high == 0 or not bounds:
                    raise ValueError("Sprite needs real transparent and visible pixels: " + ident)
                asset["bounds"] = list(bounds)
                if bounds[0] == 0 or bounds[1] == 0 or bounds[2] == width or bounds[3] == height:
                    warnings.append("Check clipped contour: " + ident)
                for key in ("anchor", "head_anchor") if kind == "character" else ("anchor",):
                    value = asset.get(key)
                    if not isinstance(value, list) or len(value) != 2 or any(not timeline.number(n) or not 0 <= n <= 1 for n in value):
                        raise ValueError("Invalid " + key + ": " + ident)
        if kind == "character":
            local_file(root, asset.get("sheet"))
            metadata = read_json(local_file(root, asset.get("sheet_metadata")))
            for key in ("entity_id", "profile", "version", "generator", "prompt_file"):
                if not metadata.get(key):
                    raise ValueError("Missing sheet metadata " + key + ": " + ident)
            origin = asset.get("sheet_origin", {})
            if any(origin.get(k) != metadata[k] for k in ("entity_id", "profile", "version")):
                raise ValueError("Sheet lineage mismatch: " + ident)
            sheet_dir = (root / asset["sheet_metadata"]).parent
            prompt = (sheet_dir / metadata["prompt_file"]).resolve()
            if not prompt.is_relative_to(root) or not prompt.is_file():
                raise ValueError("Missing/local sheet prompt: " + ident)
        provenance = asset.get("provenance", {})
        if not provenance.get("generator") or not provenance.get("prompt_file"):
            raise ValueError("Missing image provenance: " + ident)
        local_file(root, provenance["prompt_file"])
        for reference in provenance.get("references", []):
            local_file(root, reference)
    for scene in story["scenes"]:
        if assets.get(scene["background"], {}).get("kind") != "background":
            raise ValueError("Missing background: " + scene["id"])
        for item in scene.get("actors", []) + scene.get("props", []):
            expected = "character" if item in scene.get("actors", []) else "prop"
            for ident in [item["asset"]] + [f["asset"] for f in item["keyframes"] if "asset" in f]:
                if assets.get(ident, {}).get("kind") != expected:
                    raise ValueError("Missing/wrong-kind pose: " + ident)
                if expected == "character":
                    entity = story["characters"][item["id"]].get("entity_id", item["id"])
                    if assets[ident]["sheet_origin"]["entity_id"] != entity:
                        raise ValueError("Pose belongs to another character: " + ident)
    return story, manifest, warnings


def runtime_data(story, manifest):
    return "// Generated from script.json and assets/manifest.json; run prepare after editing.\n" + "globalThis.SpriteTheaterData = " + json.dumps({"story": story, "manifest": manifest}, ensure_ascii=False, separators=(",", ":")) + ";\n"


def font_css(root, manifest):
    rules = []
    for role, weight in (("regular", 400), ("bold", 700)):
        encoded = base64.b64encode(local_file(root, manifest["fonts"][role]).read_bytes()).decode("ascii")
        rules.append("@font-face{font-family:'PT Sans';font-weight:" + str(weight) + ";font-style:normal;font-display:block;src:url(data:font/ttf;base64," + encoded + ") format('truetype')}")
    return "\n".join(rules) + "\n"


def prepare_project(root):
    root = root.resolve()
    story, manifest, warnings = check_project(root)
    write_json(root / "assets/manifest.json", manifest)
    if (root / "index.html").exists():
        (root / "data.js").write_text(runtime_data(story, manifest), encoding="utf-8")
        (root / "assets/fonts/fonts.css").write_text(font_css(root, manifest), encoding="utf-8")
    return {"prepared": True, "scenes": len(story["scenes"]), "assets": len(manifest["assets"]), "warnings": warnings}


def validate_project(root):
    root = root.resolve()
    saved = read_json(root / "assets/manifest.json")
    story, manifest, warnings = check_project(root)
    if saved != manifest:
        raise ValueError("Asset metadata is missing or stale. Run prepare.")
    if (root / "index.html").exists():
        if not (root / "data.js").is_file() or (root / "data.js").read_text(encoding="utf-8") != runtime_data(story, manifest):
            raise ValueError("Web data is missing or stale. Run prepare.")
        css = root / "assets/fonts/fonts.css"
        if not css.is_file() or css.read_text(encoding="utf-8") != font_css(root, manifest):
            raise ValueError("Web fonts are missing or stale. Run prepare.")
    return {"valid": True, "scenes": len(story["scenes"]), "duration": sum(s["duration"] for s in story["scenes"]), "assets": len(manifest["assets"]), "warnings": warnings}


def make_demo(root):
    """Geometric test fixtures, explicitly not generated artwork or book canon."""
    from PIL import Image, ImageDraw
    story, assets = skeleton(), {}
    story["title"], story["subtitle"] = "Письмо на сцене", "Техническая постановка: геометрические fixtures"
    story["adaptation_notes"] = ["Вымышленный тестовый текст. Фигуры и листы технические, созданы Pillow, не GPT Images."]
    source = root / "source/demo.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("§1 Мира садится, затем поднимает письмо. Лев ждёт.\n\n§2 Письмо доставлено; герои прощаются.\n", encoding="utf-8")
    prompt_dir = root / "assets/prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "fixture.txt").write_text("Technical geometric fixture drawn with Pillow; no image model was called.\n", encoding="utf-8")
    def register(ident, image, kind, **extra):
        name = "assets/" + ident + ".png"
        image.save(root / name)
        assets[ident] = {"file": name, "kind": kind, "anchor": [.5, 1],
                         "provenance": {"generator": "Pillow technical fixture", "prompt_file": "assets/prompts/fixture.txt", "references": []}, **extra}
    background = Image.new("RGB", (1200, 540), "#d8d4c7")
    draw = ImageDraw.Draw(background)
    draw.rectangle((0, 420, 1200, 540), fill="#b7a081")
    draw.rectangle((780, 170, 1000, 420), fill="#9eaaa3")
    register("room", background, "background")
    for entity, name, color in (("mira", "Мира", "#317b83"), ("lev", "Лев", "#9b593f")):
        story["characters"][entity] = {"entity_id": entity, "name": name, "color": color}
        sheet_dir = root / "assets/characters/sheets" / entity
        sheet_dir.mkdir(parents=True, exist_ok=True)
        poses = []
        for pose in ("stand", "sit"):
            image = Image.new("RGBA", (220, 420), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.ellipse((68, 24, 152, 108), fill="#f6dfb8", outline="#fff8e5", width=4)
            draw.ellipse((91, 59, 98, 66), fill="#392a20")
            draw.ellipse((122, 59, 129, 66), fill="#392a20")
            draw.polygon([(75, 112), (145, 112), (180, 290 if pose == "stand" else 260), (40, 290 if pose == "stand" else 260)], fill=color, outline="#fff8e5", width=4)
            draw.line((80, 285, 75 if pose == "stand" else 170, 390), fill="#fff8e5", width=14)
            draw.line((140, 285, 145 if pose == "stand" else 195, 390), fill="#fff8e5", width=14)
            poses.append(image)
            sheet = f"assets/characters/sheets/{entity}/sheet.png"
            register(entity + "-" + pose, image, "character", head_anchor=[.5, .04], sheet=sheet,
                     sheet_metadata=f"assets/characters/sheets/{entity}/sheet.json",
                     sheet_origin={"entity_id": entity, "profile": "technical-fixture", "version": 1, "path": sheet})
            assets[entity + "-" + pose]["provenance"]["references"] = [sheet]
        contact = Image.new("RGBA", (500, 460), "#f4e8d0")
        contact.alpha_composite(poses[0], (15, 20))
        contact.alpha_composite(poses[1], (260, 20))
        contact.save(sheet_dir / "sheet.png")
        (sheet_dir / "prompt.txt").write_text("Technical fixture: same geometric figure in two poses; not production character art.\n", encoding="utf-8")
        write_json(sheet_dir / "sheet.json", {"entity_id": entity, "profile": "technical-fixture", "version": 1, "image": "sheet.png", "sources": ["source/demo.txt §1"], "generator": "Pillow technical fixture", "prompt_file": "prompt.txt", "reference_files": [], "artistic_choices": ["Geometric test figure"]})
    letter = Image.new("RGBA", (180, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(letter)
    d.rectangle((15, 15, 165, 105), fill="#fff7e6", outline="#392a20", width=3)
    d.line((15, 15, 90, 65, 165, 15), fill="#392a20", width=3)
    register("letter", letter, "prop")
    def actor(entity, x):
        return {"id": entity, "asset": entity + "-stand", "height": 300, "z": 2,
                "keyframes": [{"at": 0, "x": x, "y": .94}], "gestures": []}
    a, b = actor("mira", .25), actor("lev", .7)
    a["keyframes"] += [{"at": 3, "x": .4}, {"at": 5.5, "asset": "mira-sit"}, {"at": 8, "asset": "mira-stand"}, {"at": 12, "x": .55}]
    a["gestures"] = [{"kind": "lift", "at": 7.5, "duration": 1.5}]
    prop = {"id": "letter", "asset": "letter", "height": 65, "z": 3, "keyframes": [
        {"at": 0, "x": .42, "y": .94}, {"at": 8, "attach": "mira", "x": .025, "y": -.23, "tween": False},
        {"at": 11, "attach": None, "x": .7, "y": .94, "tween": False}]}
    def cue(ident, speaker, at, text, source):
        return {"id": ident, "speaker": speaker, "at": at, "duration": 3.5, "text": text, "sources": [source], "adaptation": "Реплика придумана по тестовому тексту."}
    story["scenes"] = [
        {"id": "letter", "title": "Письмо", "duration": 14, "background": "room", "actors": [a, b], "props": [prop], "cues": [cue("sit", "mira", 3, "Присяду на минуту. А вот и письмо!", "source/demo.txt §1"), cue("wait", "lev", 8.5, "Я подожду у двери.", "source/demo.txt §1")]},
        {"id": "farewell", "title": "До встречи", "duration": 10, "background": "room", "actors": [actor("mira", .35), actor("lev", .7)], "props": [], "caption": {"at": 2.5, "text": "Письмо доставлено"}, "cues": [cue("bye", "lev", 3, "До встречи!", "source/demo.txt §2")]},
    ]
    write_json(root / "script.json", story)
    manifest = read_json(root / "assets/manifest.json")
    manifest["assets"] = assets
    write_json(root / "assets/manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--backend", choices=("pygame", "web", "both"), required=True)
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--overwrite", action="store_true")
    init.add_argument("--demo", action="store_true", help="Create geometric technical fixtures, not final artwork")
    for command in ("prepare", "validate"):
        sub.add_parser(command).add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = init_project(args.output, args.backend, args.overwrite, args.demo) if args.command == "init" else (prepare_project if args.command == "prepare" else validate_project)(args.project)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        print("Ошибка подготовки спектакля: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
