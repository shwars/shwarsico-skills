"""Helpers for authoring source-grounded Markdown cards, without storing a second graph."""
import wiki

BOOK_ID = None
BOOK_TITLE = None
BOOK_ROOT = None


def require_book():
    if BOOK_ID is None:
        raise ValueError("Call wiki.configure(root), then authoring.set_book(book_id)")
    if BOOK_ROOT is not None and BOOK_ROOT != wiki.ROOT:
        raise ValueError("Vault changed: call authoring.set_book(book_id) again")


def set_book(book_id):
    """Select a prepared source for authoring another book without editing these helpers."""
    manifest = wiki.load_manifest(book_id)
    global BOOK_ID, BOOK_TITLE, BOOK_ROOT
    BOOK_ID = book_id
    BOOK_TITLE = manifest["title"]
    BOOK_ROOT = wiki.ROOT


def revise(entity_id, *, metadata=None, facts=None, occurrences=None, replace_text=None):
    """Revise an existing note while preserving unrelated manually written text."""
    card = next(c for c in wiki.cards() if c["metadata"]["entity_id"] == entity_id)
    body = card["body"]
    if replace_text:
        for old, new in replace_text.items():
            if old not in body:
                raise ValueError(f"Text to revise absent in {entity_id}: {old}")
            body = body.replace(old, new)
    payload = {"facts": card["facts"] if facts is None else facts}
    appearances = card["occurrences"] if occurrences is None else occurrences
    if appearances:
        payload["occurrences"] = appearances
    body = wiki.FACT_RE.sub(lambda _: "## Структурированные факты\n\n~~~yaml\n" +
                           wiki.dump_yaml(payload) + "\n~~~\n", body)
    meta = dict(card["metadata"])
    meta.update(metadata or {})
    wiki.write_text(card["path"], "---\n" + wiki.dump_yaml(meta) + "\n---\n" + body)


def appearance(entity_id, unit, block, kind):
    require_book()
    card = next(c for c in wiki.cards() if c["metadata"]["entity_id"] == entity_id)
    occurrence = {"book_id": BOOK_ID, "unit_id": unit, "block_id": f"b{block:04d}", "kind": kind}
    if occurrence not in card["occurrences"]:
        old = [o for o in card["occurrences"] if not all(
            o[key] == occurrence[key] for key in ("book_id", "unit_id", "block_id"))]
        revise(entity_id, occurrences=old + [occurrence])


def sources(unit, blocks):
    require_book()
    return [wiki.ref(BOOK_ID, unit, f"b{n:04d}") for n in blocks]


def fact(subject, number, predicate, unit, blocks, value=None, object=None, **fields):
    record = {
        "fact_id": f"{subject}/факт-{number:03d}", "subject": subject,
        "predicate": predicate, "scope": "canon", "evidence_type": "narrator",
        "truth_status": "confirmed", "sources": sources(unit, blocks),
    }
    record.update({"object": object} if object is not None else {"value": value})
    record.update(fields)
    return record


def add_facts(entity_id, records, sections=None):
    card = next(c for c in wiki.cards() if c["metadata"]["entity_id"] == entity_id)
    number = max([int(f["fact_id"].rsplit("-", 1)[-1]) for f in card["facts"]] or [0])
    result = []
    def content(record):
        return {k: v for k, v in record.items() if k != "fact_id"}
    for record in records:
        candidate = fact(entity_id, number + len(result) + 1, **record)
        if not any(content(candidate) == content(existing) for existing in card["facts"] + result):
            result.append(candidate)
    if result:
        wiki.append_facts(entity_id, result, sections)


def concept(entity_id, kind, unit, blocks, text, aliases=None, **metadata):
    metadata.setdefault("first_source", BOOK_ID)
    metadata.setdefault("book_ids", [BOOK_ID])
    wiki.create_card(
        {"entity_id": entity_id, "type": kind, "aliases": aliases or [], **metadata},
        {f"Книжный источник: {BOOK_TITLE}": text + "\n\n" + ", ".join(sources(unit, blocks))},
        [fact(entity_id, 1, "description", unit, blocks, value=text)])


def event(entity_id, unit, blocks, text, participants=(), places=(), causes=(),
          changes=(), parent=None, dates=None, extra=(), status="occurred",
          occurrence_kind="действие"):
    if dates is None:
        raise ValueError("Provide explicit date bounds or explicitly unknown dates")
    if status not in {"occurred", "reported", "disputed", "refuted", "planned", "hypothetical"}:
        raise ValueError("Unknown event status")
    records = [fact(entity_id, 1, "description", unit, blocks, value=text)]
    for person in participants:
        target, role = (person, "участник") if isinstance(person, str) else person
        records.append(fact(entity_id, len(records)+1, "participates", unit, blocks,
                            object=target, role=role, evidence_type="action"))
    for place in places:
        records.append(fact(entity_id, len(records)+1, "located_at", unit, blocks, object=place))
    for target, explanation in causes:
        records.append(fact(entity_id, len(records)+1, "causes", unit, blocks, object=target,
                            scope="analysis", evidence_type="inference", explanation=explanation))
    for target, property, before, after in changes:
        records.append(fact(entity_id, len(records)+1, "state_change", unit, blocks, object=target,
                            property=property, before_value=before, after_value=after, evidence_type="action"))
    if parent:
        records.append(fact(entity_id, len(records)+1, "part_of", unit, blocks, object=parent))
    for item in extra:
        records.append(fact(entity_id, len(records)+1, unit=unit, blocks=blocks, **item))
    if status == "reported":
        for record in records:
            if record["scope"] == "canon":
                record.update(evidence_type="testimony", truth_status="claimed")
    elif status in {"disputed", "refuted"}:
        for record in records:
            if record["scope"] == "canon":
                record.update(evidence_type="testimony", truth_status=status)
    elif status in {"planned", "hypothetical"}:
        # The occurrence of a plan is not confirmation of its intended outcome.
        for record in records:
            if record["scope"] == "canon":
                record.update(truth_status="unknown")
    meta = {"entity_id": entity_id, "type": "event", "event_status": status,
            "first_source": BOOK_ID, "book_ids": [BOOK_ID],
            "sort_key": (dates.get("date_min") or "9999") + "-" + unit + f"-{blocks[0]:04d}",
            **{k: v for k, v in dates.items() if k != "prefix"}}
    sections = {
        "Что произошло": text + "\n\n" + ", ".join(sources(unit, blocks)),
        "Датировка": dates["date_text"] + ". Границы используются для сортировки, "
                     "а не для назначения отсутствующего в тексте точного дня.",
    }
    if changes:
        sections["Изменения состояния"] = "\n".join(
            f"- {target}: {prop} — {before} → {after}." for target, prop, before, after in changes)
    wiki.create_card(meta, sections, records,
                     [{"book_id": BOOK_ID, "unit_id": unit, "block_id": f"b{blocks[0]:04d}", "kind": occurrence_kind}],
                     filename=f"{dates['prefix']}--{entity_id}.{BOOK_ID}.md")
