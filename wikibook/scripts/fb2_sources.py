"""Lossless addressed preparation for single-file and multipart FB2 books."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ATOMIC = {"p", "v", "text-author", "subtitle"}


def local(element):
    return element.tag.rsplit("}", 1)[-1]


def plain(element):
    return " ".join("".join(element.itertext()).split())


def sha(value):
    return hashlib.sha256(value).hexdigest()


def numeral(value):
    if value.isdigit():
        return int(value)
    total = previous = 0
    for char in reversed(value.upper()):
        number = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}[char]
        total += -number if number < previous else number
        previous = max(previous, number)
    return total


def parse(path, book_id, *, source_id=None, part_override=None, note_prefix=""):
    path = Path(path)
    raw = path.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError(f"Cannot parse FB2 XML {path}: {error}") from error
    ns = {"f": root.tag.split("}")[0][1:] if "}" in root.tag else ""}
    bodies = root.findall("f:body", ns)
    mains = [b for b in bodies if b.get("name") not in {"notes", "comments"}]
    if not mains:
        raise ValueError(f"No main text body in {path}")
    atoms = [e for main in mains for e in main.iter() if local(e) in ATOMIC]
    positions = {id(e): i for i, e in enumerate(atoms)}
    represented, structural, units = [], [], []
    counters = Counter()
    notes, note_map = [], {}
    for body in bodies:
        if body.get("name") not in {"notes", "comments"}:
            continue
        for section in body.findall("f:section", ns):
            original = section.get("id", "")
            anchor = note_prefix + original.replace("_", "-")
            if not original or original in note_map:
                raise ValueError(f"Missing or duplicate note ID in {path}: {original}")
            note_map[original] = anchor
            title = section.find("f:title", ns)
            blocks = [plain(e) for child in section if local(child) != "title"
                      for e in child.iter() if local(e) in ATOMIC]
            notes.append({"id": anchor, "original_id": original, "source_file_id": source_id,
                          "title": plain(title) if title is not None else original, "blocks": blocks})

    def inline(element):
        value = element.text or ""
        for child in element:
            text = inline(child)
            if local(child) == "a":
                href = child.get("{http://www.w3.org/1999/xlink}href", "")
                if child.get("type") == "note" or href.lstrip("#") in note_map:
                    key = href.lstrip("#")
                    if key not in note_map:
                        raise ValueError(f"Unresolved source note {href} in {path}")
                    text = f"[[source/{book_id}/notes#^{note_map[key]}|{text}]]"
            value += text + (child.tail or "")
        return " ".join(value.split())

    def record(element, block=None, containers=()):
        result = {"kind": local(element), "text": plain(element), "markdown": inline(element),
                  "atom_index": positions[id(element)]}
        if source_id:
            result["source_file_id"] = source_id
        if block:
            result.update(id=block, containers=list(containers))
        represented.append(result)
        return result

    def prefix(volume, part):
        return (f"v{volume:02d}-" if volume is not None else "") + (f"p{part:02d}-" if part is not None else "")

    def emit(elements, title_element, volume, part, framing=False):
        title = plain(title_element) if title_element is not None else ""
        title_atoms = [] if title_element is None else [record(e) for e in title_element.iter() if local(e) in ATOMIC]
        blocks = []
        def visit(e, parents=()):
            if local(e) in ATOMIC:
                blocks.append(record(e, f"b{len(blocks)+1:04d}", parents))
                return
            for child in e:
                visit(child, parents + (local(e),))
        for element in elements:
            visit(element)
        if not title_atoms and not blocks:
            return
        base = prefix(volume, part)
        normalized = title.casefold().replace("’", "'")
        special = {"предисловие автора": "preface", "предисловие": "preface", "preface": "preface",
                   "введение": "introduction", "introduction": "introduction",
                   "пролог": "prologue", "prologue": "prologue", "заключение": "conclusion",
                   "conclusion": "conclusion", "эпилог": "epilogue", "epilogue": "epilogue"}.get(normalized)
        chapter = None
        if framing:
            unit_id = base + "frontmatter"
        elif special:
            unit_id = base + special
        elif part is not None or re.match(r"(?:глава|chapter)\s+[\dIVXLCDM]+", title, re.I):
            counters[(volume, part)] += 1
            chapter = counters[(volume, part)]
            match = re.match(r"(?:глава|chapter)\s+(\d+)", title, re.I)
            if match and int(match[1]) != chapter:
                raise ValueError(f"Unexpected chapter sequence: {title}")
            unit_id = base + f"ch{chapter:02d}"
        else:
            unit_id = f"section-{len(units)+1:02d}"
        if any(u["id"] == unit_id for u in units):
            unit_id += f"-{len(units)+1:02d}"
        units.append({"id": unit_id, "order": len(units), "volume": volume, "part": part,
                      "chapter": chapter, "title": title or "Вступительный текст",
                      "kind": "frontmatter" if framing else "text", "source_file_id": source_id,
                      "title_atoms": title_atoms, "path": f"source/{book_id}/bychapter/{unit_id}.md",
                      "blocks": blocks})

    def walk(section, volume=None, part=part_override, is_body=False):
        title_element = section.find("f:title", ns)
        title = plain(title_element) if title_element is not None else ""
        children = section.findall("f:section", ns)
        if not children:
            emit([e for e in section if local(e) != "title"], title_element, volume, part)
            return
        match = re.fullmatch(r"(ТОМ|ЧАСТЬ|VOLUME|VOL\.?|PART|BOOK|КНИГА)\s+([IVXLCDM]+|\d+)", title, re.I)
        if match:
            if match[1].upper().rstrip(".") in {"ТОМ", "VOLUME", "VOL"}:
                volume = numeral(match[2])
            else:
                part = numeral(match[2])
        pending = []
        if title_element is not None:
            if is_body:
                emit([], title_element, volume, part, framing=True)
            else:
                structural.extend(record(e) for e in title_element.iter() if local(e) in ATOMIC)
        for child in section:
            if local(child) == "title":
                continue
            if local(child) == "section":
                if pending:
                    emit(pending, None, volume, part, framing=True)
                    pending = []
                walk(child, volume, part)
            else:
                pending.append(child)
        if pending:
            emit(pending, None, volume, part, framing=True)

    for main in mains:
        walk(main, is_body=True)
    represented.sort(key=lambda item: item["atom_index"])
    if [a["atom_index"] for a in represented] != list(range(len(atoms))):
        raise ValueError("Source parser lost or duplicated atomic text elements")
    if [a["text"] for a in represented] != [plain(e) for e in atoms]:
        raise ValueError("Source parser changed atomic text")
    info = root.find("f:description/f:title-info", ns)
    te = info.find("f:book-title", ns) if info is not None else None
    translators = [] if info is None else [" ".join(plain(c) for c in e if local(c) in
                   {"first-name", "middle-name", "last-name"}) for e in info.findall("f:translator", ns)]
    return {"schema_version": 2, "book_id": book_id, "title": plain(te) if te is not None else book_id,
            "translators": translators, "source_sha256": sha(raw), "source_atomic_count": len(atoms),
            "source_atomic_sha256": sha("\n".join(plain(e) for e in atoms).encode("utf-8")),
            "structural_title_atoms": structural, "units": units, "notes": notes}


def combine(paths, book_id, *, title=None, series_order=None):
    paths = list(map(Path, paths))
    multi = len(paths) > 1
    parsed = [parse(p, book_id, source_id=f"p{i:02d}" if multi else book_id,
                    part_override=i if multi else None, note_prefix=f"p{i:02d}-" if multi else "")
              for i, p in enumerate(paths, 1)]
    # Independent files can both contain Volume I / Part I / Chapter 1.
    # Add physical-file scope only where the structural addresses collide.
    addresses = [unit["id"] for source in parsed for unit in source["units"]]
    if len(addresses) != len(set(addresses)):
        for i, source in enumerate(parsed, 1):
            for unit in source["units"]:
                unit["id"] = f"s{i:02d}-" + unit["id"]
                unit["path"] = f"source/{book_id}/bychapter/{unit['id']}.md"
    manifest = dict(parsed[0])
    sources = [{"id": f"p{i:02d}" if multi else book_id, "path": str(path),
                "title": source["title"], "sha256": source["source_sha256"],
                "atomic_count": source["source_atomic_count"], "atomic_sha256": source["source_atomic_sha256"]}
               for i, (path, source) in enumerate(zip(paths, parsed), 1)]
    manifest.update(source_files=sources, series_order=series_order if series_order is not None else 999,
                    title=title or manifest["title"])
    if multi:
        manifest["source_sha256"] = sha(json.dumps([(s["id"], s["sha256"]) for s in sources],
                                                  ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        manifest["source_atomic_sha256"] = sha("\n".join(s["atomic_sha256"] for s in sources).encode("ascii"))
    manifest["fingerprint_kind"] = "ordered-source-set" if multi else "file"
    manifest["source_atomic_count"] = sum(s["source_atomic_count"] for s in parsed)
    for key in ("units", "notes", "structural_title_atoms"):
        manifest[key] = [entry for source in parsed for entry in source[key]]
    for order, unit in enumerate(manifest["units"]):
        unit["order"] = order
    for key in ("units", "notes"):
        ids = [item["id"] for item in manifest[key]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {key} addresses across input sources")
    return manifest
