"""Promote historical people while retaining identity and rewriting vault links."""
import os
import json
from pathlib import Path
import re
from urllib.parse import quote, unquote

import yaml

WIKI_LINK = re.compile(r"(!?\[\[)([^\]\n]+)(\]\])")
MD_LINK = re.compile(r"(?P<start>!?\[[^\]\n]*\]\()(?P<target><[^>\n]+>|[^\s)]+)(?P<end>(?:\s+[\"'][^\n]*?[\"'])?\))")
REFERENCE = re.compile(r"(?m)^(?P<start>\s*\[[^\]\n]+\]:\s*)(?P<target><[^>\n]+>|[^\s]+)(?P<end>[^\n]*)$")
YAML_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.S)
YAML_FENCE = re.compile(r"(?m)^(?P<fence>~~~|```)ya?ml[ \t]*\r?\n(?P<body>.*?)\r?\n(?P=fence)[ \t]*$", re.S | re.I)


def rewrite(text, page, old, new, root, *, _structured=True):
    """Rewrite exact resolved targets, including links in YAML and embeds."""
    # Most pages contain hundreds of unrelated evidence links. Avoid resolving
    # their filesystem paths when the target basename cannot be the old card.
    searchable = unquote(text)
    # PyYAML may split a quoted filename at a space, escaping the newline
    # and the first space of the continuation. This is still one YAML value.
    searchable = re.sub(r"\\\r?\n[ \t]*", "", searchable).replace("\\ ", " ")
    searchable = re.sub(r"\r?\n[ \t]+", " ", searchable)
    if old.stem not in searchable and not (
            re.search(r"\\[uUxX][0-9a-fA-F]", text) and old.stem.rsplit('.', 1)[-1] in text):
        return text
    old, new, root = old.resolve(), new.resolve(), root.resolve()

    if _structured:
        # Decode only YAML scalars, then replace only changed scalar spans.
        # This preserves comments, unrelated authored text, labels and anchors
        # while handling quoted escapes and folded multi-line YAML values.
        regions = []
        front = YAML_FRONTMATTER.match(text)
        if front:
            regions.append((front.start(1), front.group(1)))
        regions.extend((m.start('body'), m.group('body')) for m in YAML_FENCE.finditer(text))
        edits = []
        for offset, source in regions:
            try:
                tree = yaml.compose(source, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
            except yaml.YAMLError as error:
                raise ValueError(f"Cannot inspect YAML links in {page}: {error}") from error
            visited = set()
            def visit(node):
                if node is None or id(node) in visited:
                    return
                visited.add(id(node))
                if isinstance(node, yaml.ScalarNode):
                    if node.tag != 'tag:yaml.org,2002:str':
                        return
                    updated = rewrite(node.value, page, old, new, root, _structured=False)
                    if updated != node.value:
                        edits.append((offset + node.start_mark.index, offset + node.end_mark.index,
                                      json.dumps(updated, ensure_ascii=False)))
                elif isinstance(node, yaml.MappingNode):
                    for key, value in node.value:
                        visit(key)
                        visit(value)
                elif isinstance(node, yaml.SequenceNode):
                    for value in node.value:
                        visit(value)
            visit(tree)
        for start, end, replacement in sorted(edits, reverse=True):
            text = text[:start] + replacement + text[end:]

    def target(value, wikilink):
        angle = value.startswith("<") and value.endswith(">")
        raw = value[1:-1] if angle else value
        path, separator, anchor = raw.partition("#")
        if not path or re.match(r"^[a-zA-Z][a-zA-Z\d+.-]*://", path):
            return value
        decoded = unquote(path).replace("\\", "/")
        if decoded.rsplit("/", 1)[-1] not in {old.name, old.stem}:
            return value
        explicit_md = decoded.endswith(".md")
        # Vault-absolute wiki paths; ordinary Markdown paths are page-relative.
        candidates = [(root / decoded.lstrip("/")), (page.parent / decoded)] if wikilink else [page.parent / decoded]
        if wikilink and "/" not in decoded:
            candidates.append(old.parent / decoded)
            # Obsidian short links must be unambiguous across the vault.
            names = list(root.rglob(decoded if explicit_md else decoded + ".md"))
            if len(names) > 1:
                raise ValueError(f"Ambiguous short link: {value} in {page}")
        match = next((p for p in candidates if Path(str(p) if explicit_md else str(p) + ".md").resolve() == old), None)
        if match is None:
            return value
        if wikilink and "/" not in decoded:
            replacement = new.name
        elif wikilink and not decoded.startswith("."):
            replacement = new.relative_to(root).as_posix()
            if decoded.startswith("/"):
                replacement = "/" + replacement
        else:
            replacement = Path(os.path.relpath(new, page.parent)).as_posix()
            if decoded.startswith("./") and not replacement.startswith("."):
                replacement = "./" + replacement
        if not explicit_md:
            replacement = replacement[:-3]
        if "%" in path:
            replacement = quote(replacement, safe="/.-_~")
        result = replacement + (separator + anchor if separator else "")
        return "<" + result + ">" if angle else result

    def wiki_replace(match):
        destination, sep, label = match[2].partition("|")
        return match[1] + target(destination, True) + (sep + label if sep else "") + match[3]

    text = WIKI_LINK.sub(wiki_replace, text)
    for pattern in (MD_LINK, REFERENCE):
        text = pattern.sub(lambda m: m["start"] + target(m["target"], False) + m["end"], text)
    return text


def promote(wiki, entity_id, book_id, *, apply=False, rebuild=True):
    """Preflight then rename a history-only person; dry-run is the default."""
    if wiki._AUTHORING_INDEX is not None:
        raise ValueError("Run migrations outside authoring_batch")
    manifest = wiki.load_manifest(book_id)
    matches = [c for c in wiki.cards() if c["metadata"]["entity_id"] == entity_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one card for {entity_id}; found {len(matches)}")
    card = matches[0]
    if card["metadata"]["type"] != "character":
        raise ValueError("Historical-person promotion requires a character card")
    old = card["path"]
    if card["metadata"]["first_source"] != "hist":
        if card["metadata"]["first_source"] == book_id:
            if apply and rebuild:
                wiki.build()
            return {"status": "already-promoted", "path": str(old), "affected_files": []}
        raise ValueError("A novel suffix is already established; extend the existing card")
    if not old.name.endswith(".hist.md"):
        raise ValueError("Historical metadata and suffix disagree")
    # Promotion must be grounded in main-text evidence, not notes or web context.
    evidence = [s for f in card["facts"] if f["scope"] == "canon"
                for s in f["sources"] if s.startswith(f"[[source/{book_id}/bychapter/")]
    if not evidence:
        raise ValueError("Add canonical main-text evidence before promoting this person")
    valid_units = {u["id"]: {b["id"] for b in u["blocks"]} for u in manifest["units"]}
    for source in evidence:
        match = re.match(r"\[\[source/[^/]+/bychapter/([^#]+)#\^(b\d+)(?:\||\]\])", source)
        if not match or match[2] not in valid_units.get(match[1], set()):
            raise ValueError(f"Invalid promotion evidence: {source}")
    new = old.with_name(old.name[:-len(".hist.md")] + f".{book_id}.md")
    if new.exists():
        try:
            conflict = wiki.parse_card(new)["metadata"].get("entity_id", "без entity_id")
        except (ValueError, yaml.YAMLError):
            conflict = "существующий файл без читаемых метаданных"
        raise ValueError(f"Destination collision: {new} (entity_id: {conflict}); "
                         f"requested identity {entity_id} remains at {old}. Resolve identity first")
    edits, originals = {}, {}
    for page in wiki.ROOT.rglob("*.md"):
        if any(part in {".git", ".test-tmp", "__pycache__"} for part in page.relative_to(wiki.ROOT).parts):
            continue
        text = page.read_text(encoding="utf-8")
        updated = rewrite(text, page, old, new, wiki.ROOT)
        if updated != text:
            originals[page], edits[page] = text, updated
    meta = dict(card["metadata"])
    meta["first_source"] = book_id
    meta["book_ids"] = sorted(set(meta.get("book_ids", [])) | {book_id})
    body = rewrite(card["body"], old, old, new, wiki.ROOT)
    originals.setdefault(old, old.read_text(encoding="utf-8"))
    edits[old] = rewrite("---\n" + wiki.dump_yaml(meta) + "\n---\n" + body,
                         old, old, new, wiki.ROOT)
    result = {"status": "applied" if apply else "dry-run", "old_path": str(old),
              "new_path": str(new), "affected_files": [str(p) for p in sorted(edits)]}
    if not apply:
        return result
    if any(p.read_text(encoding="utf-8") != originals[p] for p in edits):
        raise ValueError("Files changed during migration preflight; retry")
    written = []
    try:
        for page, text in edits.items():
            wiki.write_text(new if page == old else page, text)
            written.append(page)
        old.unlink()
    except BaseException:
        for page in written:
            wiki.write_text(page, originals[page])
        if new.exists():
            new.unlink()
        raise
    wiki._CARD_CACHE.clear()
    for page in wiki.ROOT.rglob("*.md"):
        if ".test-tmp" in page.parts:
            continue
        text = page.read_text(encoding="utf-8")
        if rewrite(text, page, old, new, wiki.ROOT) != text:
            raise ValueError(f"Stale card reference after migration: {page}")
    if rebuild:
        wiki.build()
    return result


def merge_concepts(wiki, keep_id, duplicate_id, *, identity_sources, explanation, apply=True):
    """Resolve a text-proven anonymous identity; retain fact IDs and authored text.

    This is an authoring operation, unlike mere candidate matching. The caller
    must have read the identity evidence; guesses are not grounds for merging.
    """
    if not identity_sources or not explanation or keep_id == duplicate_id:
        raise ValueError("Distinct people and explicit identity evidence are required")
    if wiki._AUTHORING_INDEX is not None:
        raise ValueError("Run identity migrations outside authoring_batch")
    cards = wiki.cards()
    by_id = {c['metadata']['entity_id']: c for c in cards}
    if duplicate_id not in by_id and keep_id in by_id and duplicate_id in by_id[keep_id]['metadata'].get('aliases', []):
        return {'status': 'already-merged', 'entity_id': keep_id, 'retired_alias': duplicate_id,
                'affected_files': []}
    if keep_id not in by_id or duplicate_id not in by_id:
        raise ValueError("Both identity candidates must exist")
    keep, duplicate = by_id[keep_id], by_id[duplicate_id]
    if keep['metadata']['type'] != duplicate['metadata']['type']:
        raise ValueError("Only concepts of the same type can be merged")
    known = {f['fact_id'] for f in keep['facts']}
    if known & {f['fact_id'] for f in duplicate['facts']}:
        raise ValueError("Fact ID collision: resolve before identity merge")
    originals, edits = {}, {}
    for card in cards:
        if card is duplicate:
            continue
        facts = card['facts'] + (duplicate['facts'] if card is keep else [])
        facts = [dict(f) for f in facts]
        for fact in facts:
            for key in ('subject', 'object', 'asserted_by', 'at_event', 'valid_from', 'valid_until'):
                if fact.get(key) == duplicate_id:
                    fact[key] = keep_id
        meta = dict(card['metadata'])
        if card is keep:
            meta['aliases'] = list(dict.fromkeys(meta.get('aliases', []) + [duplicate_id] +
                                                duplicate['metadata'].get('aliases', [])))
            meta['book_ids'] = sorted(set(meta.get('book_ids', [])) | set(duplicate['metadata'].get('book_ids', [])))
            number = max([int(f['fact_id'].rsplit('-', 1)[-1]) for f in facts] or [0]) + 1
            while f'{keep_id}/факт-{number:03d}' in {f['fact_id'] for f in facts}:
                number += 1
            facts.append(dict(fact_id=f'{keep_id}/факт-{number:03d}', subject=keep_id, predicate='alias',
                              value=duplicate_id, scope='analysis', evidence_type='inference',
                              truth_status='confirmed', sources=identity_sources, explanation=explanation))
        appearances = card['occurrences'] + (duplicate['occurrences'] if card is keep else [])
        payload = {'facts': facts}
        if appearances:
            payload['occurrences'] = [dict(items) for items in dict.fromkeys(tuple(o.items()) for o in appearances)]
        body = card['body']
        if card is keep:
            manual = wiki.FACT_RE.sub('', duplicate['body'])
            manual = re.sub(re.escape(wiki.GENERATED_START)+r'.*?'+re.escape(wiki.GENERATED_END), '', manual, flags=re.S)
            manual = re.sub(r'\A\s*# [^\n]+\n', '', manual).strip()
            if manual:
                body = body.replace('## Структурированные факты',
                    '## Сведения до уточнения личности\n\n'+manual+'\n\n## Структурированные факты', 1)
        body = wiki.FACT_RE.sub(lambda _: '## Структурированные факты\n\n~~~yaml\n'+wiki.dump_yaml(payload)+'\n~~~\n', body)
        if card is keep or facts != card['facts']:
            edits[card['path']] = '---\n'+wiki.dump_yaml(meta)+'\n---\n'+body
    for page in wiki.ROOT.rglob('*.md'):
        if '.test-tmp' in page.relative_to(wiki.ROOT).parts or page == duplicate['path']:
            continue
        original = page.read_text(encoding='utf-8')
        updated = rewrite(edits.get(page, original), page, duplicate['path'], keep['path'], wiki.ROOT)
        if updated != original:
            originals[page], edits[page] = original, updated
    for page in edits:
        originals.setdefault(page, page.read_text(encoding='utf-8'))
    if any(page.read_text(encoding='utf-8') != originals[page] for page in edits):
        raise ValueError("Files changed during identity preflight")
    result = {'status': 'applied' if apply else 'dry-run', 'entity_id': keep_id,
              'retired_alias': duplicate_id, 'old_path': str(duplicate['path']),
              'new_path': str(keep['path']), 'affected_files': [str(p) for p in sorted(edits)]}
    if not apply:
        return result
    duplicate_text = duplicate['path'].read_text(encoding='utf-8')
    written = []
    try:
        for page, content in edits.items():
            wiki.write_text(page, content)
            written.append(page)
        duplicate['path'].unlink()
    except BaseException:
        for page in written:
            wiki.write_text(page, originals[page])
        if not duplicate['path'].exists():
            wiki.write_text(duplicate['path'], duplicate_text)
        wiki._CARD_CACHE.clear()
        raise
    wiki._CARD_CACHE.clear()
    for page in wiki.ROOT.rglob('*.md'):
        if any(part in {'.git', '.test-tmp', '__pycache__'} for part in page.relative_to(wiki.ROOT).parts):
            continue
        original = page.read_text(encoding='utf-8')
        if rewrite(original, page, duplicate['path'], keep['path'], wiki.ROOT) != original:
            raise ValueError(f"Stale card reference after merge: {page}")
    return result


def merge_people(wiki, keep_id, duplicate_id, *, identity_sources, explanation, apply=True):
    people = {c['metadata']['entity_id']: c for c in wiki.cards()}
    if any(e in people and people[e]['metadata']['type'] != 'character' for e in (keep_id, duplicate_id)):
        raise ValueError("Only character identities can be merged")
    return merge_concepts(wiki, keep_id, duplicate_id,
                          identity_sources=identity_sources, explanation=explanation, apply=apply)
