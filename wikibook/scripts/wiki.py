"""Prepare addressed FB2 sources and validate/build a Markdown knowledge graph.

Run from any directory: python /path/to/wikibook/scripts/wiki.py --root /vault --help
Requires PyYAML. This tool never calls an LLM or changes the original FB2.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

import yaml

YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

ROOT = Path.cwd().resolve()
WIKI = ROOT / "wiki"
DIRECTORIES = {
    "character": "protagonists", "event": "events", "place": "places",
    "object": "objects", "organization": "organizations", "context": "context",
}
PREDICATES = {
    "description": "Описание, подтверждённое указанным источником.",
    "trait": "Черта характера; источник и статус обязательны.",
    "appearance": "Внешность.",
    "role": "Положение, занятие или роль.",
    "alias": "Другое имя той же сущности.",
    "participates": "Событие имеет указанного участника; роль — в role.",
    "located_at": "Событие или лицо находится в указанном месте.",
    "owns": "Владение предметом в указанное время.",
    "member_of": "Принадлежность к организации.",
    "related_to": "Отношение; характер отношения — в explanation.",
    "wants": "Цель или намерение.",
    "knows": "Знание указанного факта.",
    "believes": "Убеждение; не подтверждает истинность его содержания.",
    "asserts": "Произнесённое утверждение.",
    "causes": "Причинная связь с объяснением механизма.",
    "requires": "Условие события, подтверждённое источником или анализом.",
    "prevents": "Препятствие событию.",
    "before": "Строгое относительное предшествование.",
    "state_change": "Изменение состояния при событии.",
    "historical_context": "Исторические сведения, отдельно от канона.",
    "part_of": "Событие является эпизодом более общего события; это не причинная связь.",
}
FACT_RE = re.compile(
    r"(?m)^## Структурированные факты\s*\n+~~~yaml\n(.*?)\n~~~\s*$", re.S
)
LINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")
GENERATED_START = "<!-- wiki:generated:start -->"
GENERATED_END = "<!-- wiki:generated:end -->"
_CARD_CACHE = {}
_MANIFEST_CACHE = {}
_AUTHORING_INDEX = None


def configure(root):
    """Select a vault without changing cwd; never infer it from the skill location."""
    global ROOT, WIKI
    if _AUTHORING_INDEX is not None:
        raise ValueError("Cannot switch vault during authoring_batch")
    ROOT = Path(root).expanduser().resolve()
    WIKI = ROOT / "wiki"
    _CARD_CACHE.clear()
    _MANIFEST_CACHE.clear()


def check_book_id(book_id):
    if not isinstance(book_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", book_id) or book_id == "hist":
        raise ValueError("book_id must be a readable lowercase code, other than reserved 'hist'")
    return book_id


def dump_yaml(data):
    # Quote links so properties remain valid Obsidian YAML.
    class Dumper(yaml.SafeDumper):
        pass

    def represent(dumper, value):
        style = '"' if "[[" in value or "\n" in value else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    Dumper.add_representer(str, represent)
    return yaml.dump(data, Dumper=Dumper, allow_unicode=True, sort_keys=False,
                     width=110, default_flow_style=False).rstrip()


def write_text(path, text):
    """Replace a complete UTF-8 file atomically; leave identical files untouched."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (text.rstrip() + "\n").encode("utf-8")
    if not path.exists() or path.read_bytes() != payload:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".wikibook-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            for attempt in range(6):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.1 * (2 ** attempt))
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    if _AUTHORING_INDEX is not None and path.suffix == '.md' and path.parent in {
            WIKI / directory for directory in DIRECTORIES.values()}:
        _AUTHORING_INDEX[path] = parse_card(path)


def write_json(path, data):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_fb2(path, book_id):
    from fb2_sources import parse
    return parse(path, book_id)


def prepare(book_id, input_path=None, *, title=None, series_order=None):
    check_book_id(book_id)
    from fb2_sources import combine
    paths = ([input_path] if isinstance(input_path, (str, Path)) else input_path)
    paths = list(map(Path, paths or [ROOT / "source" / f"{book_id}.fb2"]))
    manifest = combine(paths, book_id, title=title, series_order=series_order)
    folder = ROOT / "source" / book_id
    previous = folder / "manifest.json"
    if previous.exists():
        old = json.loads(previous.read_text(encoding="utf-8"))
        if old["source_sha256"] != manifest["source_sha256"]:
            raise ValueError("Source changed: create a separate edition and map source addresses")
        if title is None:
            manifest["title"] = old["title"]
        if series_order is None:
            manifest["series_order"] = old.get("series_order", 999)
    for source, path in zip(manifest["source_files"], paths):
        try:
            source["path"] = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            source["path"] = str(path.resolve())
    if len(paths) == 1:
        manifest["original_path"] = manifest["source_files"][0]["path"]
    if previous.exists():
        old = json.loads(previous.read_text(encoding="utf-8"))
        old_addresses = [(u["id"], [b["id"] for b in u["blocks"]]) for u in old["units"]]
        addresses = [(u["id"], [b["id"] for b in u["blocks"]]) for u in manifest["units"]]
        if old_addresses != addresses:
            raise ValueError("Source addresses changed: an explicit migration is required")
    for unit in manifest["units"]:
        meta = {"type": "source", "book_id": book_id, "unit_id": unit["id"],
                "volume": unit.get("volume"), "part": unit["part"], "chapter": unit["chapter"],
                "source_file_id": unit.get("source_file_id")}
        lines = ["---", dump_yaml(meta), "---", "", f"# {unit['title']}", "",
                 f"[[wiki/books/{book_id}|Книга и оглавление]]", ""]
        for block in unit["blocks"]:
            value = block["markdown"]
            if "cite" in block["containers"]:
                value = "> " + value
            lines.extend([value, f"^{block['id']}", ""])
        write_text(ROOT / unit["path"], "\n".join(lines))
    notes_lines = ["---", f"book_id: {book_id}", "type: notes-source", "---", "",
                   "# Примечания источника", "",
                   "Авторство и статус примечаний требуют проверки. Редакторские пояснения "
                   "не являются событиями повествования.", ""]
    for note in manifest["notes"]:
        notes_lines.extend([f"## {note['title']}", "", "\n\n".join(note["blocks"]),
                            f"^{note['id']}", ""])
    write_text(folder / "notes.md", "\n".join(notes_lines))
    write_json(previous, manifest)
    progress_path = folder / "progress.json"
    if not progress_path.exists():
        write_json(progress_path, {"book_id": book_id, "source_sha256": manifest["source_sha256"],
                                  "units": {u["id"]: {"read": False, "extracted": False,
                                            "audited": False, "summary": "", "questions": []}
                                            for u in manifest["units"]}})
    print(f"Prepared {len(manifest['units'])} units, {len(manifest['notes'])} notes; "
          f"{manifest['source_atomic_count']} text atoms preserved.")


def load_manifest(book_id):
    check_book_id(book_id)
    path = ROOT / "source" / book_id / "manifest.json"
    stat = path.stat()
    signature = (stat.st_mtime_ns, stat.st_size)
    cached = _MANIFEST_CACHE.get(path)
    if cached is not None and cached[0] == signature:
        return cached[1]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.setdefault("series_order", 999)
    manifest.setdefault("fingerprint_kind", "file")
    manifest.setdefault("source_files", [{"id": book_id,
        "path": manifest.get("original_path", f"source/{book_id}.fb2"),
        "title": manifest["title"], "sha256": manifest["source_sha256"],
        "atomic_count": manifest["source_atomic_count"],
        "atomic_sha256": manifest["source_atomic_sha256"]}])
    _MANIFEST_CACHE[path] = (signature, manifest)
    return manifest


def ref(book_id, unit_id, block_id):
    return f"[[source/{book_id}/bychapter/{unit_id}#^{block_id}]]"


def parse_card(path):
    content = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", content, re.S)
    if not match:
        raise ValueError(f"Missing YAML frontmatter: {path}")
    metadata = yaml.load(match.group(1), Loader=YAML_LOADER) or {}
    body = content[match.end():]
    fact_match = FACT_RE.search(body)
    structured = yaml.load(fact_match.group(1), Loader=YAML_LOADER) if fact_match else {}
    return {"path": path, "metadata": metadata, "body": body,
            "facts": (structured or {}).get("facts", []),
            "occurrences": (structured or {}).get("occurrences", [])}


@contextmanager
def authoring_batch():
    """Index a single-writer authoring batch; reread the filesystem after exit.

    Card mutations must use write_text inside the batch. External writers must
    not operate concurrently. This never replaces the Markdown source of truth.
    """
    global _AUTHORING_INDEX
    if _AUTHORING_INDEX is not None:
        raise RuntimeError('Authoring batches cannot be nested')
    initial = cards()
    _AUTHORING_INDEX = {card['path']: card for card in initial}
    try:
        yield
    finally:
        _AUTHORING_INDEX = None


def cards():
    if _AUTHORING_INDEX is not None:
        return list(_AUTHORING_INDEX.values())
    result = []
    present = set()
    for directory in DIRECTORIES.values():
        for path in sorted((WIKI / directory).glob("*.md")):
            present.add(path)
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            cached = _CARD_CACHE.get(path)
            if cached is None or cached[0] != signature:
                cached = (signature, parse_card(path))
                _CARD_CACHE[path] = cached
            result.append(cached[1])
    for path in list(_CARD_CACHE):
        if path not in present:
            del _CARD_CACHE[path]
    return result


def link(card, label=None):
    target = card["path"].relative_to(ROOT).with_suffix("").as_posix()
    return f"[[{target}|{label or card['metadata']['title']}]]"


def create_card(metadata, sections, facts, occurrences=None, filename=None):
    """Author a NEW canonical Markdown card; never silently overwrite a card."""
    existing = {c["metadata"]["entity_id"]: c for c in cards()}
    entity_id = metadata["entity_id"]
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("A readable entity_id is required")
    first_source = metadata.get("first_source")
    if first_source != "hist":
        check_book_id(first_source)
    if entity_id in existing:
        raise ValueError(f"Entity already has a card: {entity_id}")
    directory = DIRECTORIES[metadata["type"]]
    name = filename or f"{entity_id}.{first_source}.md"
    if re.search(r'[<>:"/\\|?*#^]', name):
        raise ValueError(f"Unsafe filename: {name}")
    path = WIKI / directory / name
    if path.exists():
        raise ValueError(f"Card path exists: {path}")
    metadata = {"entity_id": entity_id, "title": metadata.get("title", entity_id),
                "type": metadata["type"], "first_source": first_source,
                "book_ids": metadata.get("book_ids", [] if metadata.get("first_source") == "hist"
                                         else [first_source]),
                "source_kinds": metadata.get("source_kinds", ["book"]),
                "aliases": metadata.get("aliases", []),
                "tags": ["wikibook", metadata["type"]], **metadata}
    for fact in facts:
        if fact["subject"] != entity_id:
            raise ValueError("Store each fact in its subject's card")
    body = f"# {metadata['title']}\n\n"
    body += "\n\n".join(f"## {title}\n\n{text}" for title, text in sections.items())
    body += f"\n\n{GENERATED_START}\n{GENERATED_END}\n\n"
    payload = {"facts": facts}
    if occurrences:
        payload["occurrences"] = occurrences
    body += "## Структурированные факты\n\n~~~yaml\n" + dump_yaml(payload) + "\n~~~\n"
    write_text(path, "---\n" + dump_yaml(metadata) + "\n---\n\n" + body)
    return path


def append_facts(entity_id, facts, sections=None):
    card = next(c for c in cards() if c["metadata"]["entity_id"] == entity_id)
    if any(f["subject"] != entity_id for f in facts):
        raise ValueError("Wrong subject")
    old_ids = {f["fact_id"] for f in card["facts"]}
    if any(f["fact_id"] in old_ids for f in facts):
        raise ValueError("Duplicate fact ID")
    book_ids = set(card["metadata"].get("book_ids", []))
    for fact in facts:
        for source in fact.get("sources", []):
            match = re.match(r"\[\[source/([^/]+)/", source)
            if match:
                book_ids.add(match.group(1))
    card["metadata"]["book_ids"] = sorted(book_ids)
    payload = {"facts": card["facts"] + facts}
    if card["occurrences"]:
        payload["occurrences"] = card["occurrences"]
    body = FACT_RE.sub(lambda _: "## Структурированные факты\n\n~~~yaml\n" +
                       dump_yaml(payload) + "\n~~~\n", card["body"])
    if sections:
        new_sections = "\n\n".join(f"## {h}\n\n{v}" for h, v in sections.items()) + "\n\n"
        body = body.replace("## Структурированные факты", new_sections + "## Структурированные факты", 1)
    write_text(card["path"], "---\n" + dump_yaml(card["metadata"]) + "\n---\n" + body)


def set_progress(book_id, unit_id, **fields):
    path = ROOT / "source" / book_id / "progress.json"
    progress = json.loads(path.read_text(encoding="utf-8"))
    stage = {**progress["units"][unit_id], **fields}
    if (stage["extracted"] and not stage["read"]) or (stage["audited"] and not stage["extracted"]):
        raise ValueError("Coverage requires read -> extracted -> audited")
    if stage["audited"] and not all(stage.get(k) for k in ("audit_summary", "audit_date", "audit_method")):
        raise ValueError("Audited coverage requires audit_summary, audit_date and audit_method")
    progress["units"][unit_id] = stage
    write_json(path, progress)


def read_unit(book_id, unit_id, first=1, last=None):
    unit = next(u for u in load_manifest(book_id)["units"] if u["id"] == unit_id)
    if first < 1 or (last is not None and last < first):
        raise ValueError("Block ranges are inclusive, start at 1, and must be ordered")
    print(f"# {unit['title']} [{unit_id}] — {len(unit['blocks'])} blocks")
    for block in unit["blocks"][first - 1:last]:
        print(f"\n[{block['id']}] {block['text']}")


def search_source(book_id, pattern, limit=50):
    expression = re.compile(pattern, re.I)
    count = 0
    for unit in load_manifest(book_id)["units"]:
        for block in unit["blocks"]:
            if expression.search(block["text"]):
                print(f"[{unit['id']} {block['id']}] {block['text']}")
                count += 1
                if count >= limit:
                    print(f"Result limit: {limit}. Use a narrower expression or read a unit.")
                    return


def validate_sources():
    """Check input hashes, coverage stages, and all prepared source anchors."""
    errors = []
    for path in (ROOT / "source").glob("*/manifest.json"):
        bid = path.parent.name
        try:
            manifest = load_manifest(bid)
            ids = [unit["id"] for unit in manifest["units"]]
            if len(ids) != len(set(ids)):
                errors.append(f"Duplicate source units: {bid}")
            for source in manifest["source_files"]:
                original = ROOT / source["path"]
                if not original.is_file() or sha(original.read_bytes()) != source["sha256"]:
                    errors.append(f"Original source hash mismatch: {source['path']}")
            progress = json.loads((path.parent / "progress.json").read_text(encoding="utf-8"))
            if set(progress["units"]) != set(ids):
                errors.append(f"Source and progress units differ: {bid}")
            if progress.get("source_sha256") != manifest["source_sha256"]:
                errors.append(f"Source and progress fingerprint differ: {bid}")
            for uid, stage in progress["units"].items():
                if (stage["extracted"] and not stage["read"]) or (stage["audited"] and not stage["extracted"]):
                    errors.append(f"Invalid coverage stage: {bid}/{uid}")
            notes_text = (path.parent / "notes.md").read_text(encoding="utf-8")
            note_anchors = re.findall(r"(?m)^\^([\w-]+)\s*$", notes_text)
            if len(note_anchors) != len(set(note_anchors)):
                errors.append(f"Duplicate prepared note anchors: {bid}")
            expected_notes = {note["id"] for note in manifest["notes"]}
            if set(note_anchors) != expected_notes:
                errors.append(f"Missing or unexpected prepared note anchors: {bid}")
            for unit in manifest["units"]:
                page = ROOT / unit["path"]
                if not page.is_file():
                    errors.append(f"Missing prepared unit: {bid}/{unit['id']}")
                    continue
                text = page.read_text(encoding="utf-8")
                anchors = re.findall(r"(?m)^\^(b\d+)\s*$", text)
                if anchors != [block["id"] for block in unit["blocks"]]:
                    errors.append(f"Prepared block anchors differ: {bid}/{unit['id']}")
                for block in unit["blocks"]:
                    value = ("> " if "cite" in block.get("containers", []) else "") + block["markdown"]
                    if f"{value}\n^{block['id']}" not in text:
                        errors.append(f"Prepared block text differs: {bid}/{unit['id']}/{block['id']}")
                for target in LINK_RE.findall(text):
                    target = target.split("|", 1)[0]
                    if target.startswith(f"source/{bid}/notes#^") and target.split("#^", 1)[1] not in expected_notes:
                        errors.append(f"Unresolved prepared note link: {target}")
        except (KeyError, ValueError, FileNotFoundError) as error:
            errors.append(f"Invalid prepared source {bid}: {error}")
    return errors


def validate():
    errors, warnings = validate_sources(), []
    all_cards = cards()
    by_id = {}
    facts = {}
    for card in all_cards:
        meta = card["metadata"]
        entity = meta.get("entity_id")
        if not isinstance(entity, str) or not entity:
            errors.append(f"Invalid entity ID: {card['path']}")
        if entity in by_id:
            errors.append(f"Duplicate entity: {entity}")
        by_id[entity] = card
        if not FACT_RE.search(card["body"]):
            errors.append(f"No structured facts section: {entity}")
        if meta.get("type") not in DIRECTORIES:
            errors.append(f"Unknown card type: {entity}")
        first_source = meta.get("first_source")
        if first_source and not card["path"].name.endswith(f".{first_source}.md"):
            errors.append(f"Card suffix and first_source disagree: {entity}")
        if meta.get("type") == "character" and first_source == "hist" and any(
                f.get("scope") == "canon" and any("/bychapter/" in s and s.startswith("[[source/")
                for s in f.get("sources", [])) for f in card["facts"]):
            errors.append(f"Historical person has novel evidence: promote-person required: {entity}")
        if meta.get("type") == "event" and not card["occurrences"]:
            errors.append(f"No narrative occurrences: {entity}")
        for key in ("date_min", "date_max"):
            value = meta.get(key)
            if value:
                try:
                    date.fromisoformat(str(value))
                except ValueError:
                    errors.append(f"Invalid {key}: {entity}")
        if meta.get("date_min") and meta.get("date_max"):
            if str(meta["date_min"]) > str(meta["date_max"]):
                errors.append(f"Reversed date range: {entity}")
        for fact in card["facts"]:
            fid = fact.get("fact_id")
            if fid in facts:
                errors.append(f"Duplicate fact: {fid}")
            facts[fid] = fact
            if fact.get("subject") != entity:
                errors.append(f"Fact in wrong card: {fid}")
            for required in ("fact_id", "subject", "predicate", "scope", "evidence_type",
                             "truth_status", "sources"):
                if not fact.get(required):
                    errors.append(f"Missing {required}: {fid}")
            if ("object" in fact) == ("value" in fact):
                errors.append(f"Fact needs object XOR value: {fid}")
            if fact.get("predicate") not in PREDICATES:
                errors.append(f"Unknown predicate: {fid}")
            if fact.get("scope") not in {"canon", "history", "editorial", "analysis"}:
                errors.append(f"Unknown scope: {fid}")
            if fact.get("evidence_type") not in {
                "narrator", "action", "testimony", "editorial", "web", "inference"
            }:
                errors.append(f"Unknown evidence type: {fid}")
            if fact.get("truth_status") not in {
                "confirmed", "claimed", "disputed", "refuted", "unknown"
            }:
                errors.append(f"Unknown truth status: {fid}")
            if fact.get("predicate") in {"causes", "requires", "prevents"} and not fact.get("explanation"):
                errors.append(f"Causal edge has no explanation: {fid}")
    for fid, fact in facts.items():
        for source in fact.get("sources", []):
            match = re.match(r"\[\[source/([^/]+)/", source)
            if match and match[1] not in by_id[fact["subject"]]["metadata"].get("book_ids", []):
                errors.append(f"Book missing from book_ids: {match[1]} in {fid}")
        for key in ("object", "asserted_by", "at_event", "valid_from", "valid_until"):
            if fact.get(key) and fact[key] not in by_id and fact[key] not in facts:
                errors.append(f"Unknown {key} {fact[key]} in {fid}")
        for basis in fact.get("basis", []):
            if basis not in facts:
                errors.append(f"Unknown basis {basis} in {fid}")
    anchor_cache = {}
    resolved_link_cache = {}
    occurrence_units = {}
    for card in all_cards:
        # Also check links in metadata and structured blocks.
        raw = card["path"].read_text(encoding="utf-8")
        for match in LINK_RE.finditer(raw):
            target = match.group(1).split("|", 1)[0]
            # Most evidence and navigation targets recur in several cards.
            # Cache resolution for this validation only, so later runs still see edits.
            cache_key = (card["path"] if target.startswith("#") else None, target)
            if cache_key in resolved_link_cache:
                problem = resolved_link_cache[cache_key]
                if problem:
                    errors.append(problem + f" in {card['metadata']['entity_id']}")
                continue
            filename, _, anchor = target.partition("#")
            path = (ROOT / filename) if filename else card["path"]
            if not path.suffix:
                path = path.with_suffix(".md")
            # Card names retain a book suffix before the omitted Markdown suffix.
            if not path.exists() and not filename.endswith(".md"):
                path = ROOT / (filename + ".md")
            problem = None
            if not path.is_file():
                problem = f"Broken link {target}"
            elif anchor.startswith("^"):
                if path not in anchor_cache:
                    anchor_cache[path] = set(re.findall(r"(?m)^\^([\w-]+)\s*$",
                                                       path.read_text(encoding="utf-8")))
                if anchor[1:] not in anchor_cache[path]:
                    problem = f"Missing block {target}"
            resolved_link_cache[cache_key] = problem
            if problem:
                errors.append(problem + f" in {card['metadata']['entity_id']}")
        for occurrence in card["occurrences"]:
            try:
                book_id = occurrence["book_id"]
                if book_id not in occurrence_units:
                    occurrence_units[book_id] = {
                        u["id"]: {b["id"] for b in u["blocks"]}
                        for u in load_manifest(book_id)["units"]}
                block_ids = occurrence_units[book_id][occurrence["unit_id"]]
                if occurrence["block_id"] not in block_ids:
                    errors.append(f"Invalid occurrence: {card['metadata']['entity_id']}")
            except (KeyError, StopIteration, FileNotFoundError):
                errors.append(f"Invalid occurrence: {card['metadata']['entity_id']}")
    for predicate in ("before", "causes"):
        adjacency = defaultdict(list)
        for fact in facts.values():
            if fact["predicate"] == predicate and fact["truth_status"] == "confirmed" and fact.get("object"):
                adjacency[fact["subject"]].append(fact["object"])
        visiting, visited = set(), set()
        def visit(node):
            if node in visiting:
                errors.append(f"Cycle in {predicate}: {node}")
                return
            if node in visited:
                return
            visiting.add(node)
            for target in adjacency[node]:
                visit(target)
            visiting.remove(node)
            visited.add(node)
        for node in list(adjacency):
            visit(node)
    return errors, warnings, all_cards


def generated_body(card, by_id, incoming):
    entity = card["metadata"]["entity_id"]
    lines = ["## Связи и навигация", ""]
    own = card["facts"]
    # Display new evidence as readable prose as well as retaining structured YAML.
    # In particular, later chapters must visibly enrich an existing person's profile.
    profile_predicates = [
        ("Описание и положение", {"description", "role", "alias"}),
        ("Внешность", {"appearance"}),
        ("Характер", {"trait"}),
        ("Цели, знания и версии", {"wants", "knows", "believes", "asserts"}),
        ("Исторический контекст — не из романа", {"historical_context"}),
    ]
    if card["metadata"]["type"] == "event":
        profile_predicates = [("Дополнения и версии по источникам", {"description", "asserts"})]
        # The first description is already in the manually authored event section.
        profile_facts = own[1:]
    else:
        profile_facts = own
    labels = {"wants": "Цель", "knows": "Знание", "believes": "Убеждение",
              "asserts": "Утверждение", "role": "Роль", "alias": "Имя"}
    def fact_book(fact):
        for source in fact["sources"]:
            match = re.match(r"\[\[source/([^/]+)/", source)
            if match:
                return match[1]
        return None
    first_source = card["metadata"].get("first_source")
    later = sorted({fact_book(f) for f in profile_facts if fact_book(f) not in {None, first_source}},
                   key=lambda bid: (book_order(bid), bid))
    for current_book in [None] + later:
        grouped_facts = [f for f in profile_facts if
                        (fact_book(f) in {None, first_source} if current_book is None
                         else fact_book(f) == current_book)]
        if current_book is not None:
            title = load_manifest(current_book)["title"]
            lines.extend([f"### Далее из другой книги: {title}", ""])
        for heading, predicates in profile_predicates:
            selected = [f for f in grouped_facts if f["predicate"] in predicates and "value" in f]
            if not selected:
                continue
            lines.extend([f"{'####' if current_book is not None else '###'} {heading}", ""])
            for fact in selected:
                label = labels.get(fact["predicate"])
                qualifiers = []
                if fact["scope"] != "canon":
                    qualifiers.append({"analysis": "вывод", "history": "история вне романа",
                                       "editorial": "примечание издания"}[fact["scope"]])
                if fact["evidence_type"] == "testimony":
                    qualifiers.append("свидетельство/реплика")
                if fact["truth_status"] != "confirmed":
                    qualifiers.append({"claimed": "сообщено", "disputed": "спорно",
                                       "refuted": "опровергнуто", "unknown": "не установлено"}[fact["truth_status"]])
                prefix = (label + ": " if label else "")
                note = " (" + "; ".join(qualifiers) + ")" if qualifiers else ""
                where = ""
                if fact.get("at_event") in by_id:
                    where = " При событии " + link(by_id[fact["at_event"]]) + "."
                lines.append("- " + prefix + str(fact["value"]) + note + where +
                             " Источник: " + ", ".join(fact["sources"]) + ".")
            lines.append("")
    if card["metadata"]["type"] == "event":
        groups = [
            ("Участники", [f for f in own if f["predicate"] == "participates"], False),
            ("Места", [f for f in own if f["predicate"] == "located_at"], False),
            ("Причины и условия", [f for f in incoming[entity] if f["predicate"] == "causes"] +
             [f for f in own if f["predicate"] == "requires"], None),
            ("Последствия", [f for f in own if f["predicate"] == "causes"], False),
            ("Другие связанные события", [f for f in own if f["predicate"] in {"before", "prevents"}],
             False),
            ("Состав события", [f for f in own if f["predicate"] == "part_of"] +
             [f for f in incoming[entity] if f["predicate"] == "part_of"], None),
            ("Изменённые состояния", [f for f in own if f["predicate"] == "state_change"], False),
        ]
        for title, group, reverse in groups:
            lines.extend([f"### {title}", ""])
            if not group:
                lines.extend(["Связи ещё не установлены по обработанному тексту.", ""])
            else:
                for fact in group:
                    if "object" not in fact:
                        qualifier = " (вывод анализа)" if fact["scope"] == "analysis" else ""
                        lines.append("- " + PREDICATES[fact["predicate"]] + ": " +
                                     str(fact.get("value", "")) + qualifier +
                                     " Источник: " + ", ".join(fact["sources"]) + ".")
                        continue
                    target = fact["subject"] if fact["object"] == entity else fact["object"]
                    if target in by_id:
                        note = fact.get("role") or fact.get("explanation")
                        if fact["predicate"] == "state_change":
                            note = (f"{fact.get('property', 'состояние')}: "
                                    f"{fact.get('before_value', '?')} → {fact.get('after_value', '?')}")
                        status = ""
                        if fact["truth_status"] != "confirmed":
                            status = f" ({fact['truth_status']})"
                        lines.append("- " + link(by_id[target]) + (f" — {note}" if note else "") + status)
                lines.append("")
    else:
        events = {f["subject"] for f in incoming[entity]
                  if by_id[f["subject"]]["metadata"]["type"] == "event"}
        lines.extend(["### Связанные события", ""])
        lines.extend("- " + link(by_id[e]) for e in sorted(events))
        if not events:
            lines.append("Связи с событиями пока не извлечены.")
        lines.append("")
        related = [f for f in own + incoming[entity]
                   if f.get("object") in by_id and by_id[f["subject"]]["metadata"]["type"] != "event"]
        if related:
            lines.extend(["### Другие связи концептов", ""])
            for fact in related:
                target = fact["subject"] if fact["object"] == entity else fact["object"]
                detail = fact.get("relation") or fact.get("explanation")
                lines.append("- " + link(by_id[target]) + f" — {PREDICATES[fact['predicate']]}" +
                             (f": {detail}" if detail else "") +
                             (f" ({fact['truth_status']})" if fact["truth_status"] != "confirmed" else ""))
            lines.append("")
    return "\n".join(lines).rstrip()


def book_order(book_id):
    try:
        return load_manifest(book_id).get("series_order", 999)
    except FileNotFoundError:
        return 999


def unit_label(unit):
    context = []
    if unit.get("volume") is not None:
        context.append(f"Том {unit['volume']}")
    if unit.get("part") is not None:
        context.append(f"Часть {unit['part']}")
    return " · ".join(context + [unit["title"]])


def coverage_label(progress):
    units = list(progress["units"].values())
    return "; ".join(f"{label}: {sum(bool(u[key]) for u in units)}/{len(units)}"
                     for key, label in [("read", "прочитано"), ("extracted", "извлечено"),
                                        ("audited", "проверено")])


def build():
    errors, warnings, all_cards = validate()
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        raise ValueError(f"Build refused: {len(errors)} validation errors")
    by_id = {c["metadata"]["entity_id"]: c for c in all_cards}
    incoming = defaultdict(list)
    all_facts = [f for c in all_cards for f in c["facts"]]
    for fact in all_facts:
        if fact.get("object") in by_id:
            incoming[fact["object"]].append(fact)
    for card in all_cards:
        entity = card["metadata"]["entity_id"]
        card["metadata"]["source_kinds"] = sorted({
            {"canon": "book", "history": "web", "editorial": "editorial", "analysis": "analysis"}[f["scope"]]
            for f in card["facts"]
        })
        if card["metadata"]["type"] == "event":
            related = {f["object"] for f in card["facts"] if f.get("object") in by_id
                       and by_id[f["object"]]["metadata"]["type"] == "event"}
            related |= {f["subject"] for f in incoming[entity]
                        if by_id[f["subject"]]["metadata"]["type"] == "event"}
            card["metadata"]["participants"] = [
                link(by_id[f["object"]]) for f in card["facts"] if f["predicate"] == "participates"]
        else:
            related = {f["subject"] for f in incoming[entity]
                       if by_id[f["subject"]]["metadata"]["type"] == "event"}
        card["metadata"]["related_events"] = [link(by_id[e]) for e in sorted(related)]
        replacement = GENERATED_START + "\n\n" + generated_body(card, by_id, incoming) + "\n\n" + GENERATED_END
        pattern = re.escape(GENERATED_START) + r".*?" + re.escape(GENERATED_END)
        body = re.sub(pattern, lambda _: replacement, card["body"], flags=re.S)
        if body == card["body"] and GENERATED_START not in body:
            raise ValueError("No generated region: " + entity)
        write_text(card["path"], "---\n" + dump_yaml(card["metadata"]) + "\n---\n" + body)
    manifests = [load_manifest(p.parent.name)
                 for p in sorted((ROOT / "source").glob("*/manifest.json"))]
    manifests.sort(key=lambda m: (m.get("series_order", book_order(m["book_id"])), m["book_id"]))
    progress_by_book = {}
    for manifest in manifests:
        book_id = manifest["book_id"]
        progress = json.loads((ROOT / "source" / book_id / "progress.json").read_text(encoding="utf-8"))
        progress_by_book[book_id] = progress
        lines = [f"# {manifest['title']}", "",
                 "Основной источник: подготовленный текст исходных FB2.", "",
                 coverage_label(progress) + f". [[wiki/coverage.{book_id}|Журнал покрытия]].", "",
                 f"[[wiki/book-timeline.{book_id}|Порядок изложения]] · "
                 "[[wiki/cal-timeline|Календарный таймлайн]]", "", "## Оглавление", ""]
        audit_path = WIKI / f"audit.{book_id}.md"
        if audit_path.exists():
            lines[5:5] = [f"[[wiki/audit.{book_id}|Отдельный смысловой аудит и неопределённости]].", ""]
        context = None
        for unit in manifest["units"]:
            group = (unit.get("volume"), unit.get("part"))
            if group != context:
                labels = [f"Том {group[0]}" if group[0] else "", f"Часть {group[1]}" if group[1] else ""]
                lines.extend(["", "### " + " · ".join(x for x in labels if x) if any(labels) else "### Вне частей", ""])
                context = group
            lines.append(f"- [[{Path(unit['path']).with_suffix('').as_posix()}|{unit['title']}]]")
        lines.extend(["", "## Исходные файлы", ""])
        for source in manifest.get("source_files", []):
            lines.append(f"- `{source['path']}` — SHA-256 `{source['sha256']}`.")
        write_text(WIKI / "books" / f"{book_id}.md", "\n".join(lines))
        occurrence_rows = []
        for card in all_cards:
            for occurrence in card["occurrences"]:
                if occurrence["book_id"] == book_id:
                    unit = next(u for u in manifest["units"] if u["id"] == occurrence["unit_id"])
                    occurrence_rows.append((unit["order"], occurrence["block_id"], unit, card, occurrence))
        timeline = [f"# Порядок изложения: {manifest['title']}", "",
                    coverage_label(progress) + f". [[wiki/coverage.{book_id}|Покрытие]].",
                    "Одно событие может появляться несколько раз. Это не дубли карточек.", ""]
        last_unit = None
        for _, block, unit, card, occurrence in sorted(occurrence_rows, key=lambda r: (r[0], r[1])):
            if unit["id"] != last_unit:
                timeline.extend([f"## {unit_label(unit)}", ""])
                last_unit = unit["id"]
            timeline.extend([f"- {link(card)} — {occurrence['kind']}; "
                             f"{ref(book_id, unit['id'], block)}.", ""])
        write_text(WIKI / f"book-timeline.{book_id}.md", "\n".join(timeline))
        counts = Counter(k for fields in progress["units"].values()
                         for k in ("read", "extracted", "audited") if fields[k])
        coverage = [f"# Покрытие: {manifest['title']}", "",
                    f"Подготовлено: {len(manifest['units'])}; прочитано: {counts['read']}; "
                    f"извлечено: {counts['extracted']}; проверено: {counts['audited']}.", "",
                    "Статусы отмечаются по выполненной работе, а не по наличию файлов.", "",
                    "| Часть | Прочитано | Извлечено | Проверено | Вопросы |",
                    "|---|---|---|---|---|"]
        if audit_path.exists():
            coverage[4:4] = [f"[[wiki/audit.{book_id}|Журнал отдельного смыслового аудита]].", ""]
        for unit in manifest["units"]:
            fields = progress["units"][unit["id"]]
            states = ["да" if fields[k] else "нет" for k in ("read", "extracted", "audited")]
            questions = "; ".join(fields.get("questions", [])).replace("|", "/")
            coverage.append(f"| [[{Path(unit['path']).with_suffix('').as_posix()}|{unit_label(unit)}]] | "
                            + " | ".join(states) + f" | {questions} |")
        coverage.extend(["", "## Заметки чтения", ""])
        for unit in manifest["units"]:
            fields = progress["units"][unit["id"]]
            if fields.get("summary"):
                coverage.extend([f"### {unit_label(unit)}", "", fields["summary"], ""])
            if fields.get("audit_summary"):
                coverage.extend([f"Проверка {fields.get('audit_date', '?')}: "
                                 f"{fields['audit_summary']}", "",
                                 "Метод: " + fields.get("audit_method", "не указан") + ".", ""])
        write_text(WIKI / f"coverage.{book_id}.md", "\n".join(coverage))
    unfinished = any(not unit["audited"] for progress in progress_by_book.values() for unit in progress["units"].values())
    calendar = ["# Календарный таймлайн", "",
                ("**Извлечение или аудит продолжаются.** " if unfinished else "") +
                "Покрытие и метод проверки указаны в журналах книг; неизвестные даты сохранены.", "",
                "XX означает неизвестный месяц или день. Интервалы не задают точный порядок.", ""]
    events = [c for c in all_cards if c["metadata"]["type"] == "event"]
    confirmed = sorted([c for c in events if c["metadata"].get("event_status") == "occurred"
                        and c["metadata"].get("date_min")],
                       key=lambda c: (str(c["metadata"].get("sort_key", c["metadata"]["date_min"])),
                                      c["metadata"]["entity_id"]))
    for card in confirmed:
        calendar.extend([f"- **{card['metadata']['date_text']}** — {link(card)}.", ""])
    for heading, subset in [
        ("Без обоснованной календарной даты", [c for c in events if c["metadata"].get("event_status") == "occurred"
                                               and not c["metadata"].get("date_min")]),
        ("Сообщения, планы и спорные версии", [c for c in events if c["metadata"].get("event_status") != "occurred"]),
    ]:
        calendar.extend([f"## {heading}", ""])
        calendar.extend("- " + link(c) for c in sorted(subset, key=lambda c: c["metadata"]["entity_id"]))
        calendar.append("")
    write_text(WIKI / "cal-timeline.md", "\n".join(calendar))
    nodes = [{"entity_id": c["metadata"]["entity_id"],
              "path": c["path"].relative_to(ROOT).as_posix(), **c["metadata"]} for c in all_cards]
    edges = [f for f in all_facts if f.get("object")]
    write_json(WIKI / "graph.json", {"schema_version": 1, "books": [
        {"book_id": m["book_id"], "source_sha256": m["source_sha256"],
         "fingerprint_kind": m.get("fingerprint_kind", "file"), "source_files": m.get("source_files", []),
         "series_order": m.get("series_order", book_order(m["book_id"])),
         "coverage": {k: sum(p[k] for p in progress_by_book[m["book_id"]]["units"].values())
                      for k in ("read", "extracted", "audited")},
         "unit_count": len(m["units"])} for m in manifests],
        "nodes": nodes, "facts": all_facts, "edges": edges,
        "occurrences": [{"event_id": c["metadata"]["entity_id"], **o}
                        for c in all_cards for o in c["occurrences"]]})
    index = ["# Wiki книг", "", "## Книги и покрытие", "",
             "| Книга | Покрытие | Навигация |", "|---|---|---|"]
    for manifest in manifests:
        bid = manifest["book_id"]
        index.append(f"| [[wiki/books/{bid}|{manifest['title']}]] | "
                     + coverage_label(progress_by_book[bid]) + " | "
                     + f"[[wiki/coverage.{bid}|Журнал]] · [[wiki/book-timeline.{bid}|Порядок книги]] |")
    index.extend(["", "[[wiki/cal-timeline|Общий календарь]] · "
                  "[[wiki/views/concepts.base|Таблицы Obsidian Bases]] · "
                  "[[wiki/README|Как пользоваться wiki]] · [[wiki/predicates|Словарь связей]]", "",
                  "## Карточки", "", "| Тип | Количество |", "|---|---:|"])
    for kind, directory in DIRECTORIES.items():
        typed = sorted((c for c in all_cards if c["metadata"]["type"] == kind),
                       key=lambda c: c["metadata"]["entity_id"])
        index.append(f"| {kind} | {len(typed)} |")
    for kind in DIRECTORIES:
        index.extend(["", f"## {kind}", ""])
        index.extend("- " + link(c) for c in all_cards if c["metadata"]["type"] == kind)
    write_text(WIKI / "index.md", "\n".join(index))
    base = {
        "filters": {"and": ["file.inFolder(\"wiki\")", "note.entity_id != null"]},
        "views": [{"type": "table", "name": "Все концепты",
                   "order": ["file.name", "note.entity_id", "note.type", "note.book_ids", "note.source_kinds", "note.related_events"]},
                  {"type": "table", "name": "События", "filters": {"and": ["note.type == \"event\""]},
                   "order": ["file.name", "note.date_text", "note.date_precision", "note.event_status", "note.participants"]}],
    }
    write_text(WIKI / "views" / "concepts.base", dump_yaml(base))
    schema = ["# Словарь связей", "", "Предикаты структурированных фактов и JSON-графа.", ""]
    schema.extend(f"- `{key}` — {value}" for key, value in PREDICATES.items())
    write_text(WIKI / "predicates.md", "\n".join(schema))
    if not (WIKI / "README.md").exists():
        write_text(WIKI / "README.md", """# Как пользоваться wiki

Начните с [[wiki/index|индекса книг]], [[wiki/cal-timeline|общего календаря]]
или [[wiki/views/concepts.base|таблиц Bases]]. Книжный таймлайн следует
порядку рассказа, календарный — доступным датировкам событий.

Карточки содержат авторский текст, структурированные факты и производные связи.
Каждый факт имеет источники и статус; свидетельство или план не равны
подтверждённому событию. Исторический контекст отделён от версии книги.

Открывайте корень с каталогами source/ и wiki/ как vault Obsidian.
Для графа концептов примените фильтр path:wiki/ и исключите исходные главы,
индексы и журналы. Типы связей и основания доступны в фактах и graph.json.
Не редактируйте graph.json и области wiki:generated: их обновляет сборка.
Журналы coverage показывают чтение, извлечение, аудит и оставшиеся вопросы.
""")
    print(f"Built {len(all_cards)} cards, {len(all_facts)} facts, {len(edges)} typed edges.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Vault containing source/ and wiki/; defaults to cwd")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--book-id", required=True)
    prep.add_argument("--input", action="append")
    prep.add_argument("--title")
    prep.add_argument("--series-order", type=int)
    read = sub.add_parser("read")
    read.add_argument("unit_id")
    read.add_argument("--book-id", required=True)
    read.add_argument("--first", type=int, default=1)
    read.add_argument("--last", type=int)
    status = sub.add_parser("status")
    status.add_argument("--book-id", required=True)
    search = sub.add_parser("search")
    search.add_argument("pattern")
    search.add_argument("--book-id", required=True)
    search.add_argument("--limit", type=int, default=50)
    sub.add_parser("validate")
    sub.add_parser("build")
    promote = sub.add_parser("promote-person")
    promote.add_argument("entity_id")
    promote.add_argument("--book-id", required=True)
    mode = promote.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    configure(args.root)
    if args.command == "prepare":
        prepare(args.book_id, args.input, title=args.title, series_order=args.series_order)
    elif args.command == "read":
        read_unit(args.book_id, args.unit_id, args.first, args.last)
    elif args.command == "status":
        progress = json.loads((ROOT / "source" / args.book_id / "progress.json").read_text(encoding="utf-8"))
        for key in ("read", "extracted", "audited"):
            print(f"{key}: {sum(u[key] for u in progress['units'].values())}/{len(progress['units'])}")
        next_unit = next((unit for unit in load_manifest(args.book_id)["units"]
                          if not progress["units"][unit["id"]]["extracted"]), None)
        audit_unit = next((unit for unit in load_manifest(args.book_id)["units"]
                           if not progress["units"][unit["id"]]["audited"]), None)
        print("next unit:", next_unit["id"] if next_unit else "extraction pass finished")
        print("next audit unit:", audit_unit["id"] if audit_unit else "audit finished")
        errors, _, all_cards = validate()
        print("cards:", dict(Counter(c["metadata"]["type"] for c in all_cards)))
        print("validation errors:", len(errors))
    elif args.command == "search":
        search_source(args.book_id, args.pattern, args.limit)
    elif args.command == "validate":
        errors, warnings, all_cards = validate()
        for value in warnings:
            print("WARNING:", value)
        for value in errors:
            print("ERROR:", value)
        print(f"{len(all_cards)} cards; {len(errors)} errors; {len(warnings)} warnings.")
        return bool(errors)
    elif args.command == "build":
        build()
    elif args.command == "promote-person":
        from card_migration import promote
        print(json.dumps(promote(sys.modules[__name__], args.entity_id, args.book_id, apply=args.apply),
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
