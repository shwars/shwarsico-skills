import argparse
from copy import deepcopy
from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Optional
from uuid import uuid4

import jupytext
import nbformat


COMMANDS = {
    "replace-cell",
    "insert-cell",
    "delete-cells",
    "move-cells",
    "export-percent",
    "import-percent",
}
TOOL_METADATA_KEY = "_ipynb_tool"
EDIT_FORMAT_VERSION = 1
MAX_DIFF_CHARS = 20000
PERCENT_FORMAT = {
    "extension": ".py",
    "format_name": "percent",
    "notebook_metadata_filter": TOOL_METADATA_KEY,
    "cell_metadata_filter": TOOL_METADATA_KEY,
}


@dataclass
class Change:
    kind: str
    old_index: Optional[int] = None
    new_index: Optional[int] = None
    old_cell: Optional[Any] = None
    new_cell: Optional[Any] = None
    note: str = ""
    outputs_cleared: int = 0
    execution_reset: bool = False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        raise SystemExit("expected an editing command")
    command = argv[0]
    args = build_parser(command).parse_args(argv[1:])
    return HANDLERS[command](args)


def build_parser(command):
    parser = argparse.ArgumentParser(
        prog=f"ipynb-tool {command}",
        description=command.replace("-", " ").capitalize() + ".",
    )

    if command == "replace-cell":
        parser.add_argument("notebook")
        parser.add_argument("cell", help="1-based cell index or id:<cell-id>.")
        add_source_arguments(parser)
        add_write_argument(parser)
    elif command == "insert-cell":
        parser.add_argument("notebook")
        parser.add_argument("--type", dest="cell_type", choices=("code", "markdown", "raw"), required=True)
        add_destination_arguments(parser)
        add_source_arguments(parser)
        add_write_argument(parser)
    elif command == "delete-cells":
        parser.add_argument("notebook")
        parser.add_argument("--cells", required=True, help="Indexes, ranges, and id:<cell-id> values.")
        add_write_argument(parser)
    elif command == "move-cells":
        parser.add_argument("notebook")
        parser.add_argument("--cells", required=True, help="Indexes, ranges, and id:<cell-id> values.")
        add_destination_arguments(parser)
        add_write_argument(parser)
    elif command == "export-percent":
        parser.add_argument("notebook")
        parser.add_argument("--output", required=True, help="Destination Python percent-format file.")
        parser.add_argument("--force", action="store_true", help="Replace an existing output file.")
    elif command == "import-percent":
        parser.add_argument("editable", help="Python percent-format file.")
        parser.add_argument("target", help="Notebook to update or create.")
        parser.add_argument(
            "--allow-delete",
            action="store_true",
            help="Allow existing cells omitted from an exported edit buffer to be deleted.",
        )
        add_write_argument(parser)
    return parser


def add_source_arguments(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-file", help="Read UTF-8 cell source from this file.")
    group.add_argument("--stdin", action="store_true", help="Read cell source from standard input.")


def add_destination_arguments(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--before", help="Place before this cell index or ID.")
    group.add_argument("--after", help="Place after this cell index or ID.")
    group.add_argument("--at-start", action="store_true", help="Place at the start of the notebook.")
    group.add_argument("--at-end", action="store_true", help="Place at the end of the notebook.")


def add_write_argument(parser):
    parser.add_argument("--write", action="store_true", help="Apply the validated edit; otherwise preview it.")


def handle_replace(args):
    path, notebook, digest = load_notebook(args.notebook)
    index = resolve_cell_selector(notebook.cells, args.cell)
    source = read_source(args)
    candidate = deepcopy(notebook)
    old_cell = notebook.cells[index]
    new_cell = candidate.cells[index]
    source_changed = normalize_source(new_cell.source) != source
    outputs_cleared = 0
    execution_reset = False
    if source_changed:
        new_cell.source = source
        if new_cell.cell_type == "code":
            outputs_cleared = len(new_cell.outputs)
            execution_reset = new_cell.execution_count is not None
            new_cell.outputs = []
            new_cell.execution_count = None
    changes = []
    if source_changed:
        changes.append(
            Change(
                "replace",
                old_index=index,
                new_index=index,
                old_cell=old_cell,
                new_cell=new_cell,
                outputs_cleared=outputs_cleared,
                execution_reset=execution_reset,
            )
        )
    return finish_notebook_edit(path, notebook, candidate, digest, changes, args.write)


def handle_insert(args):
    path, notebook, digest = load_notebook(args.notebook)
    source = read_source(args)
    insertion_index = resolve_destination(notebook.cells, args)
    candidate = deepcopy(notebook)
    cell = make_new_cell(args.cell_type, source, candidate)
    candidate.cells.insert(insertion_index, cell)
    changes = [Change("insert", new_index=insertion_index, new_cell=cell)]
    return finish_notebook_edit(path, notebook, candidate, digest, changes, args.write)


def handle_delete(args):
    path, notebook, digest = load_notebook(args.notebook)
    indexes = resolve_cell_spec(notebook.cells, args.cells)
    if not indexes:
        raise SystemExit("no cells selected")
    selected = set(indexes)
    candidate = deepcopy(notebook)
    candidate.cells = [cell for index, cell in enumerate(candidate.cells) if index not in selected]
    changes = [Change("delete", old_index=index, old_cell=notebook.cells[index]) for index in indexes]
    return finish_notebook_edit(path, notebook, candidate, digest, changes, args.write)


def handle_move(args):
    path, notebook, digest = load_notebook(args.notebook)
    indexes = resolve_cell_spec(notebook.cells, args.cells)
    if not indexes:
        raise SystemExit("no cells selected")
    selected = set(indexes)
    anchor_index = destination_anchor(notebook.cells, args)
    if anchor_index is not None and anchor_index in selected:
        raise SystemExit("move destination cannot be one of the selected cells")

    remaining_indexes = [index for index in range(len(notebook.cells)) if index not in selected]
    if args.at_start:
        insertion_index = 0
    elif args.at_end:
        insertion_index = len(remaining_indexes)
    else:
        insertion_index = remaining_indexes.index(anchor_index)
        if args.after is not None:
            insertion_index += 1

    new_order = (
        remaining_indexes[:insertion_index]
        + indexes
        + remaining_indexes[insertion_index:]
    )
    if new_order == list(range(len(notebook.cells))):
        changes = []
        candidate = deepcopy(notebook)
    else:
        candidate = deepcopy(notebook)
        candidate.cells = [candidate.cells[index] for index in new_order]
        new_positions = {old_index: new_index for new_index, old_index in enumerate(new_order)}
        changes = [
            Change(
                "move",
                old_index=index,
                new_index=new_positions[index],
                old_cell=notebook.cells[index],
                new_cell=candidate.cells[new_positions[index]],
            )
            for index in indexes
        ]
    return finish_notebook_edit(path, notebook, candidate, digest, changes, args.write)


def handle_export(args):
    notebook_path, notebook, digest = load_notebook(args.notebook)
    output_path = Path(args.output)
    if output_path.suffix.lower() != ".py":
        raise SystemExit("percent-format output must use a .py extension")
    if output_path.exists() and not args.force:
        raise SystemExit(f"output already exists: {output_path}; use --force to replace it")

    editable = make_editable_notebook(notebook, digest)
    try:
        text = jupytext.writes(editable, fmt=PERCENT_FORMAT)
    except Exception as exc:
        raise SystemExit(f"could not export percent format: {exc}") from exc
    atomic_write_text(output_path, text, replace=args.force)
    print(f"Exported {len(notebook.cells)} cells to {output_path}")
    print(f"base sha256: {digest}")
    print(f"source notebook: {notebook_path}")
    return 0


def handle_import(args):
    editable_path = Path(args.editable)
    target_path = Path(args.target)
    if editable_path.suffix.lower() != ".py":
        raise SystemExit("percent-format input must use a .py extension")
    if target_path.suffix.lower() != ".ipynb":
        raise SystemExit("import target must use a .ipynb extension")
    try:
        text = editable_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"could not read percent-format file {editable_path}: {exc}") from exc
    try:
        parsed = jupytext.reads(text, fmt="py:percent")
    except Exception as exc:
        raise SystemExit(f"could not parse percent-format file: {exc}") from exc

    header = parsed.metadata.get(TOOL_METADATA_KEY)
    if target_path.exists():
        path, base, digest = load_notebook(target_path)
        validate_edit_header(header, digest)
        candidate, changes = merge_editable(base, parsed, args.allow_delete)
        return finish_notebook_edit(path, base, candidate, digest, changes, args.write)

    if isinstance(header, dict) and header.get("base_sha256"):
        raise SystemExit("exported edit buffer requires its original target notebook")
    candidate, changes = create_notebook_from_percent(parsed)
    validate_notebook(candidate, "candidate notebook")
    if args.write:
        atomic_write_notebook(target_path, candidate, expected_digest=None, expect_missing=True)
    print(render_change_report(changes, applied=bool(args.write)))
    return 0


def load_notebook(path_value):
    path = Path(path_value)
    if path.suffix.lower() != ".ipynb":
        raise SystemExit("notebook path must use a .ipynb extension")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"could not read notebook {path}: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        notebook = nbformat.reads(raw.decode("utf-8-sig"), as_version=nbformat.NO_CONVERT)
    except Exception as exc:
        raise SystemExit(f"could not parse notebook {path}: {exc}") from exc
    validate_notebook(notebook, f"notebook {path}")
    return path, notebook, digest


def validate_notebook(notebook, label):
    try:
        nbformat.validate(notebook)
    except Exception as exc:
        raise SystemExit(f"invalid {label}: {exc}") from exc


def normalize_source(source):
    if isinstance(source, list):
        source = "".join(str(part) for part in source)
    elif source is None:
        source = ""
    else:
        source = str(source)
    return source.replace("\r\n", "\n").replace("\r", "\n")


def read_source(args):
    if args.source_file:
        try:
            source = Path(args.source_file).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SystemExit(f"could not read source file {args.source_file}: {exc}") from exc
    else:
        source = sys.stdin.read()
    return normalize_source(source)


def resolve_cell_selector(cells, selector):
    if selector.startswith("id:"):
        cell_id = selector[3:]
        if not cell_id:
            raise SystemExit("cell ID cannot be empty")
        matches = [index for index, cell in enumerate(cells) if cell.get("id") == cell_id]
        if not matches:
            raise SystemExit(f"cell ID not found: {cell_id}")
        if len(matches) > 1:
            raise SystemExit(f"cell ID is not unique: {cell_id}")
        return matches[0]
    try:
        number = int(selector)
    except ValueError as exc:
        raise SystemExit(f"invalid cell selector: {selector}") from exc
    index = number - 1
    if index < 0 or index >= len(cells):
        raise SystemExit(f"cell index out of range: {number}")
    return index


def resolve_cell_spec(cells, spec):
    indexes = []
    seen = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            raise SystemExit("empty cell selector in --cells")
        if part.startswith("id:"):
            part_indexes = [resolve_cell_selector(cells, part)]
        else:
            match = re.fullmatch(r"(\d+)-(\d+)", part)
            if match:
                start = int(match.group(1))
                end = int(match.group(2))
                if start > end:
                    start, end = end, start
                part_indexes = [resolve_cell_selector(cells, str(number)) for number in range(start, end + 1)]
            else:
                part_indexes = [resolve_cell_selector(cells, part)]
        for index in part_indexes:
            if index in seen:
                raise SystemExit(f"duplicate cell selection: {index + 1}")
            seen.add(index)
            indexes.append(index)
    return sorted(indexes)


def destination_anchor(cells, args):
    selector = args.before if args.before is not None else args.after
    return None if selector is None else resolve_cell_selector(cells, selector)


def resolve_destination(cells, args):
    anchor = destination_anchor(cells, args)
    if args.at_start:
        return 0
    if args.at_end:
        return len(cells)
    return anchor if args.before is not None else anchor + 1


def make_new_cell(cell_type, source, notebook, reserved_ids=None):
    if cell_type == "code":
        cell = nbformat.v4.new_code_cell(source=source, metadata={}, outputs=[], execution_count=None)
    elif cell_type == "markdown":
        cell = nbformat.v4.new_markdown_cell(source=source, metadata={})
    elif cell_type == "raw":
        cell = nbformat.v4.new_raw_cell(source=source, metadata={})
    else:
        raise SystemExit(f"unsupported cell type: {cell_type}")
    set_cell_id_for_notebook(cell, notebook, reserved_ids=reserved_ids)
    return cell


def set_cell_id_for_notebook(cell, notebook, reserved_ids=None):
    if notebook.nbformat == 4 and notebook.nbformat_minor >= 5:
        existing = {item.get("id") for item in notebook.cells if item.get("id")}
        existing.update(reserved_ids or ())
        while True:
            cell_id = uuid4().hex[:8]
            if cell_id not in existing:
                cell["id"] = cell_id
                return
    cell.pop("id", None)


def finish_notebook_edit(path, original, candidate, digest, changes, write):
    validate_notebook(candidate, "candidate notebook")
    if write and changes:
        atomic_write_notebook(path, candidate, expected_digest=digest)
    print(render_change_report(changes, applied=bool(write and changes)))
    return 0


def atomic_write_notebook(path, notebook, expected_digest, expect_missing=False):
    try:
        text = nbformat.writes(notebook, version=nbformat.NO_CONVERT)
    except Exception as exc:
        raise SystemExit(f"could not serialize notebook: {exc}") from exc
    if not text.endswith("\n"):
        text += "\n"
    if expected_digest is not None:
        try:
            current = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise SystemExit(f"could not recheck notebook before writing: {exc}") from exc
        if current != expected_digest:
            raise SystemExit("notebook changed while the edit was being prepared; no changes written")
    elif expect_missing and path.exists():
        raise SystemExit(f"target appeared before writing: {path}; no changes written")
    atomic_write_text(path, text, replace=not expect_missing)


def atomic_write_text(path, text, replace):
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not replace:
            raise SystemExit(f"target already exists: {path}")
        old_mode = None
        if path.exists():
            old_mode = stat.S_IMODE(path.stat().st_mode)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if old_mode is not None:
            os.chmod(temp_path, old_mode)
        os.replace(temp_path, path)
    except SystemExit:
        raise
    except OSError as exc:
        try:
            if "temp_path" in locals():
                temp_path.unlink()
        except OSError:
            pass
        raise SystemExit(f"could not write {path}: {exc}") from exc


def cell_handle(cell, index):
    cell_id = cell.get("id")
    return f"id:{cell_id}" if cell_id else f"index:{index + 1}"


def make_editable_notebook(notebook, digest):
    editable = nbformat.v4.new_notebook(
        metadata={
            TOOL_METADATA_KEY: {
                "format_version": EDIT_FORMAT_VERSION,
                "base_sha256": digest,
            }
        }
    )
    editable.nbformat_minor = 5
    for index, original in enumerate(notebook.cells):
        metadata = {TOOL_METADATA_KEY: {"handle": cell_handle(original, index)}}
        if original.cell_type == "code":
            cell = nbformat.v4.new_code_cell(source=normalize_source(original.source), metadata=metadata)
        elif original.cell_type == "markdown":
            cell = nbformat.v4.new_markdown_cell(source=normalize_source(original.source), metadata=metadata)
        elif original.cell_type == "raw":
            cell = nbformat.v4.new_raw_cell(source=normalize_source(original.source), metadata=metadata)
        else:
            raise SystemExit(f"unsupported cell type at index {index + 1}: {original.cell_type}")
        set_cell_id_for_notebook(cell, editable)
        editable.cells.append(cell)
    return editable


def validate_edit_header(header, digest):
    if not isinstance(header, dict):
        raise SystemExit("percent file is not an ipynb-tool export for this notebook")
    if header.get("format_version") != EDIT_FORMAT_VERSION:
        raise SystemExit("unsupported or missing ipynb-tool edit format version")
    if header.get("base_sha256") != digest:
        raise SystemExit("target notebook has changed since the percent file was exported")


def canonical_cell(cell):
    notebook = nbformat.v4.new_notebook()
    if cell.cell_type == "code":
        clean = nbformat.v4.new_code_cell(source=normalize_source(cell.source), metadata={})
    elif cell.cell_type == "markdown":
        clean = nbformat.v4.new_markdown_cell(source=normalize_source(cell.source), metadata={})
    elif cell.cell_type == "raw":
        clean = nbformat.v4.new_raw_cell(source=normalize_source(cell.source), metadata={})
    else:
        raise SystemExit(f"unsupported cell type: {cell.cell_type}")
    notebook.cells = [clean]
    text = jupytext.writes(notebook, fmt="py:percent")
    parsed = jupytext.reads(text, fmt="py:percent")
    return parsed.cells[0].cell_type, normalize_source(parsed.cells[0].source)


def merge_editable(base, parsed, allow_delete):
    base_handles = [cell_handle(cell, index) for index, cell in enumerate(base.cells)]
    base_by_handle = {handle: (index, cell) for index, (handle, cell) in enumerate(zip(base_handles, base.cells))}
    seen = set()
    imported_existing_order = []
    candidate = deepcopy(base)
    candidate.cells = []
    changes = []
    reserved_ids = {cell.get("id") for cell in base.cells if cell.get("id")}

    for new_index, imported in enumerate(parsed.cells):
        tool_metadata = imported.metadata.get(TOOL_METADATA_KEY)
        if tool_metadata is None:
            new_cell = make_new_cell(
                imported.cell_type,
                normalize_source(imported.source),
                candidate,
                reserved_ids=reserved_ids,
            )
            if new_cell.get("id"):
                reserved_ids.add(new_cell.id)
            candidate.cells.append(new_cell)
            changes.append(Change("insert", new_index=new_index, new_cell=new_cell))
            continue
        if not isinstance(tool_metadata, dict) or not isinstance(tool_metadata.get("handle"), str):
            raise SystemExit(f"invalid ipynb-tool cell marker at imported cell {new_index + 1}")
        handle = tool_metadata["handle"]
        if handle in seen:
            raise SystemExit(f"duplicate ipynb-tool cell handle: {handle}")
        if handle not in base_by_handle:
            raise SystemExit(f"unknown ipynb-tool cell handle: {handle}")
        seen.add(handle)
        imported_existing_order.append(handle)
        old_index, original = base_by_handle[handle]
        canonical_type, canonical_source = canonical_cell(original)
        imported_type = imported.cell_type
        imported_source = normalize_source(imported.source)
        if imported_type == canonical_type and imported_source == canonical_source:
            merged = deepcopy(original)
        else:
            merged, cleared = update_existing_cell(original, imported_type, imported_source, candidate)
            changes.append(
                Change(
                    "replace",
                    old_index=old_index,
                    new_index=new_index,
                    old_cell=original,
                    new_cell=merged,
                    outputs_cleared=cleared,
                    execution_reset=original.cell_type == "code" and original.execution_count is not None,
                )
            )
        candidate.cells.append(merged)

    missing = [handle for handle in base_handles if handle not in seen]
    if missing and not allow_delete:
        indexes = ", ".join(str(base_by_handle[handle][0] + 1) for handle in missing)
        raise SystemExit(f"import would delete existing cells {indexes}; rerun with --allow-delete")
    for handle in missing:
        old_index, cell = base_by_handle[handle]
        changes.append(Change("delete", old_index=old_index, old_cell=cell))

    surviving_base_order = [handle for handle in base_handles if handle in seen]
    if imported_existing_order != surviving_base_order:
        changes.append(Change("reorder", note="existing cells changed relative order"))
    return candidate, changes


def update_existing_cell(original, new_type, source, notebook):
    if new_type == original.cell_type:
        updated = deepcopy(original)
        updated.source = source
    else:
        metadata = deepcopy(original.metadata)
        if new_type == "code":
            updated = nbformat.v4.new_code_cell(source=source, metadata=metadata)
        elif new_type == "markdown":
            updated = nbformat.v4.new_markdown_cell(source=source, metadata=metadata)
        elif new_type == "raw":
            updated = nbformat.v4.new_raw_cell(source=source, metadata=metadata)
        else:
            raise SystemExit(f"unsupported imported cell type: {new_type}")
        if original.get("id"):
            updated["id"] = original["id"]
        else:
            set_cell_id_for_notebook(updated, notebook)
    cleared = len(original.get("outputs", [])) if original.cell_type == "code" else 0
    if updated.cell_type == "code":
        updated.outputs = []
        updated.execution_count = None
    return updated, cleared


def create_notebook_from_percent(parsed):
    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        }
    )
    notebook.nbformat_minor = 5
    changes = []
    for index, imported in enumerate(parsed.cells):
        cell = make_new_cell(imported.cell_type, normalize_source(imported.source), notebook)
        notebook.cells.append(cell)
        changes.append(Change("insert", new_index=index, new_cell=cell))
    return notebook, changes


def render_change_report(changes, applied=False):
    if not changes:
        return "No notebook changes.\nvalidation: ok"
    lines = ["Notebook edit applied" if applied else "Notebook edit preview"]
    for change in changes:
        if change.kind == "replace":
            old_label = describe_cell(change.old_index, change.old_cell)
            new_label = describe_cell(change.new_index, change.new_cell)
            if change.old_cell.cell_type == change.new_cell.cell_type:
                lines.append(f"replace {old_label}")
            else:
                lines.append(f"replace {old_label} with {new_label}")
            if change.outputs_cleared or change.execution_reset:
                lines.append(
                    f"  outputs cleared: {change.outputs_cleared}; execution_count reset"
                )
            diff = source_diff(change)
            if diff:
                lines.append(diff)
        elif change.kind == "insert":
            lines.append(f"insert {describe_cell(change.new_index, change.new_cell)}")
            diff = source_diff(change)
            if diff:
                lines.append(diff)
        elif change.kind == "delete":
            lines.append(f"delete {describe_cell(change.old_index, change.old_cell)}")
            diff = source_diff(change)
            if diff:
                lines.append(diff)
        elif change.kind == "move":
            lines.append(
                f"move {describe_cell(change.old_index, change.old_cell)} "
                f"to position {change.new_index + 1}"
            )
        elif change.kind == "reorder":
            lines.append(f"reorder: {change.note}")
    lines.append("validation: ok")
    if not applied:
        lines.append("rerun with --write to apply")
    return "\n".join(lines)


def describe_cell(index, cell):
    cell_id = cell.get("id")
    identity = f" id={cell_id}" if cell_id else ""
    return f"cell {index + 1} ({cell.cell_type}{identity})"


def source_diff(change):
    old_source = "" if change.old_cell is None else normalize_source(change.old_cell.source)
    new_source = "" if change.new_cell is None else normalize_source(change.new_cell.source)
    if old_source == new_source:
        return ""
    old_name = "/dev/null" if change.old_index is None else f"cell-{change.old_index + 1}"
    new_name = "/dev/null" if change.new_index is None else f"cell-{change.new_index + 1}"
    diff = "".join(
        difflib.unified_diff(
            old_source.splitlines(keepends=True),
            new_source.splitlines(keepends=True),
            fromfile=old_name,
            tofile=new_name,
        )
    )
    if len(diff) > MAX_DIFF_CHARS:
        omitted = len(diff) - MAX_DIFF_CHARS
        return f"{diff[:MAX_DIFF_CHARS]}\n...[diff truncated {omitted} chars]"
    return diff.rstrip("\n")


HANDLERS = {
    "replace-cell": handle_replace,
    "insert-cell": handle_insert,
    "delete-cells": handle_delete,
    "move-cells": handle_move,
    "export-percent": handle_export,
    "import-percent": handle_import,
}
