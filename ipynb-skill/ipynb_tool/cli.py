import argparse
import base64
import html
import json
from pathlib import Path
import re
import sys


EDITING_COMMANDS = {
    "replace-cell",
    "insert-cell",
    "delete-cells",
    "move-cells",
    "export-percent",
    "import-percent",
}


IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in EDITING_COMMANDS:
        from .editing import main as editing_main

        return editing_main(argv)

    args = build_parser().parse_args(argv)
    notebook_path = Path(args.notebook)
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    output = render_notebook(notebook, notebook_path, args)
    if output:
        print(output)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ipynb-tool",
        description="Inspect and safely edit Jupyter .ipynb notebooks.",
        epilog=(
            "Editing commands: replace-cell, insert-cell, delete-cells, "
            "move-cells, export-percent, import-percent"
        ),
    )
    parser.add_argument("notebook", help="Path to a .ipynb notebook.")

    xml_group = parser.add_mutually_exclusive_group()
    xml_group.add_argument("--xml", action="store_true", help="Use XML formatting.")
    xml_group.add_argument("--noxml", action="store_false", dest="xml", help="Use plain formatting.")
    parser.set_defaults(xml=False)

    parser.add_argument("--code", action="store_true", help="Include code cell source.")
    parser.add_argument("--output", action="store_true", help="Include code cell outputs.")
    parser.add_argument("--markdown", action="store_true", help="Include markdown cell source.")
    parser.add_argument("--all", action="store_true", help="Include code, markdown, and outputs.")
    parser.add_argument("--comments", action="store_true", help="Comment markdown and outputs in plain mode.")

    parser.add_argument("--summary", action="store_true", help="Print a compact notebook inventory.")
    parser.add_argument("--toc", action="store_true", help="Print markdown headings with cell indexes.")
    parser.add_argument("--cells", help="Restrict to 1-based cell indexes/ranges, e.g. 1,3,8-12.")
    parser.add_argument("--max-chars", type=int, default=20000, help="Maximum characters per source/output block.")
    parser.add_argument("--no-truncate", action="store_true", help="Disable source/output truncation.")
    parser.add_argument("--errors", action="store_true", help="Restrict to code cells with error outputs.")
    parser.add_argument("--search", help="Restrict to cells whose source or outputs match this regex.")
    parser.add_argument("--around", type=int, default=0, help="Include N neighboring cells around search matches.")
    parser.add_argument("--metadata", action="store_true", help="Include notebook and cell metadata.")
    parser.add_argument("--execution", action="store_true", help="Show execution counts and out-of-order warnings.")
    parser.add_argument("--cell-ids", action="store_true", help="List cell indexes, types, and stable cell IDs.")

    parser.add_argument(
        "--images",
        choices=("skip", "base64", "files"),
        default="skip",
        help="Handle image outputs by skipping, preserving base64, or writing files.",
    )
    parser.add_argument("--image-dir", help="Directory for images written by --images files.")
    return parser


def render_notebook(notebook, notebook_path, args):
    cells = notebook.get("cells", [])
    selected_indexes = select_cell_indexes(cells, args)
    image_state = {
        "next": 1,
        "dir": Path(args.image_dir) if args.image_dir else notebook_path.parent,
    }

    parts = []
    if args.summary:
        parts.append(render_summary(notebook, selected_indexes, args))
    if args.toc:
        toc = render_toc(notebook, selected_indexes)
        if toc:
            parts.append(toc)
    if args.execution:
        execution = render_execution(notebook, selected_indexes)
        if execution:
            parts.append(execution)
    if args.cell_ids:
        parts.append(render_cell_ids(notebook, selected_indexes))

    content_requested = requested_content(args)
    if args.search and not any(content_requested.values()):
        content_requested = {"code": True, "markdown": True, "output": True}
    if args.errors and not any(content_requested.values()):
        content_requested = {"code": True, "markdown": False, "output": True}

    if args.images == "files":
        extract_images(notebook, selected_indexes, image_state)

    if any(content_requested.values()):
        rendered = render_content(notebook, selected_indexes, args, content_requested, image_state)
        if rendered:
            parts.append(rendered)

    return "\n\n".join(part for part in parts if part)


def requested_content(args):
    return {
        "code": bool(args.code or args.all),
        "markdown": bool(args.markdown or args.all),
        "output": bool(args.output or args.all),
    }


def select_cell_indexes(cells, args):
    indexes = set(range(len(cells)))
    if args.cells:
        indexes &= parse_cell_spec(args.cells, len(cells))

    if args.search:
        pattern = re.compile(args.search, re.IGNORECASE)
        matches = set()
        for index in indexes:
            if pattern.search(cell_search_text(cells[index])):
                matches.add(index)
        expanded = set(matches)
        around = max(args.around, 0)
        for index in matches:
            start = max(index - around, 0)
            end = min(index + around, len(cells) - 1)
            expanded.update(range(start, end + 1))
        indexes &= expanded

    if args.errors:
        indexes &= {
            index
            for index in range(len(cells))
            if has_error_output(cells[index])
        }

    return sorted(indexes)


def parse_cell_spec(spec, cell_count):
    indexes = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            raw_start, raw_end = part.split("-", 1)
            start = int(raw_start)
            end = int(raw_end)
            if start > end:
                start, end = end, start
            for number in range(start, end + 1):
                add_cell_index(indexes, number, cell_count)
        else:
            add_cell_index(indexes, int(part), cell_count)
    return indexes


def add_cell_index(indexes, number, cell_count):
    index = number - 1
    if index < 0 or index >= cell_count:
        raise SystemExit(f"cell index out of range: {number}")
    indexes.add(index)


def render_summary(notebook, selected_indexes, args):
    cells = notebook.get("cells", [])
    selected = [cells[index] for index in selected_indexes]
    type_counts = {}
    output_count = 0
    image_count = 0
    error_count = 0
    execution_counts = []

    for cell in selected:
        cell_type = cell.get("cell_type", "unknown")
        type_counts[cell_type] = type_counts.get(cell_type, 0) + 1
        outputs = cell.get("outputs", []) if cell_type == "code" else []
        output_count += len(outputs)
        if any(output.get("output_type") == "error" for output in outputs):
            error_count += 1
        for output in outputs:
            image_count += len(output_images(output))
        execution_count = cell.get("execution_count")
        if isinstance(execution_count, int):
            execution_counts.append(execution_count)

    lines = [
        "Notebook Summary",
        f"path cells: {len(selected)} selected / {len(cells)} total",
        f"nbformat: {notebook.get('nbformat', '?')}.{notebook.get('nbformat_minor', '?')}",
    ]
    if type_counts:
        counts = ", ".join(f"{name}={type_counts[name]}" for name in sorted(type_counts))
        lines.append(f"cell types: {counts}")
    lines.append(f"outputs: {output_count}")
    lines.append(f"images: {image_count}")
    lines.append(f"error cells: {error_count}")
    if execution_counts:
        lines.append(f"execution counts: {min(execution_counts)}..{max(execution_counts)}")
    else:
        lines.append("execution counts: none")
    if args.metadata:
        lines.append("metadata:")
        lines.append(indent(json.dumps(notebook.get("metadata", {}), indent=2, sort_keys=True), "  "))
    return "\n".join(lines)


def render_toc(notebook, selected_indexes):
    lines = ["Table of Contents"]
    for index in selected_indexes:
        cell = notebook.get("cells", [])[index]
        if cell.get("cell_type") != "markdown":
            continue
        for line in source_text(cell).splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                level = len(match.group(1))
                title = match.group(2)
                lines.append(f"{index + 1}: {'  ' * (level - 1)}{title}")
    return "\n".join(lines) if len(lines) > 1 else ""


def render_execution(notebook, selected_indexes):
    lines = ["Execution"]
    previous = None
    for index in selected_indexes:
        cell = notebook.get("cells", [])[index]
        if cell.get("cell_type") != "code":
            continue
        count = cell.get("execution_count")
        marker = ""
        if isinstance(count, int) and isinstance(previous, int) and count < previous:
            marker = " out-of-order"
        if isinstance(count, int):
            previous = count
        lines.append(f"{index + 1}: execution_count={count}{marker}")
    return "\n".join(lines) if len(lines) > 1 else ""


def render_cell_ids(notebook, selected_indexes):
    cells = notebook.get("cells", [])
    lines = ["Cell IDs"]
    for index in selected_indexes:
        cell = cells[index]
        cell_id = cell.get("id") or "<none>"
        lines.append(f"{index + 1}: {cell.get('cell_type', 'unknown')} id={cell_id}")
    return "\n".join(lines)


def render_content(notebook, selected_indexes, args, content_requested, image_state):
    cells = notebook.get("cells", [])
    if args.xml:
        lines = ["<notebook>"]
        if args.metadata:
            metadata = json.dumps(notebook.get("metadata", {}), indent=2, sort_keys=True)
            lines.append("  <metadata>")
            lines.append(indent(xml_escape(metadata), "    "))
            lines.append("  </metadata>")
        for index in selected_indexes:
            cell_xml = render_cell_xml(cells[index], index, args, content_requested, image_state)
            if cell_xml:
                lines.append(cell_xml)
        lines.append("</notebook>")
        return "\n".join(lines)

    chunks = []
    for index in selected_indexes:
        chunk = render_cell_plain(cells[index], index, args, content_requested, image_state)
        if chunk:
            chunks.append(chunk)
    return "\n\n".join(chunks)


def render_cell_xml(cell, index, args, content_requested, image_state):
    cell_type = cell.get("cell_type", "unknown")
    body = []
    if args.metadata:
        body.append("    <metadata>")
        body.append(indent(xml_escape(json.dumps(cell.get("metadata", {}), indent=2, sort_keys=True)), "      "))
        body.append("    </metadata>")
    if cell_type == "markdown" and content_requested["markdown"]:
        body.append("    <markdown>")
        body.append(indent(xml_escape(truncate(source_text(cell), args)), "      "))
        body.append("    </markdown>")
    elif cell_type == "code":
        if content_requested["code"]:
            body.append("    <code>")
            body.append(indent(xml_escape(truncate(source_text(cell), args)), "      "))
            body.append("    </code>")
        if content_requested["output"]:
            output_text = outputs_as_xml(cell.get("outputs", []), args, image_state)
            if output_text:
                body.append("    <output>")
                body.append(indent(output_text, "      "))
                body.append("    </output>")

    if not body:
        return ""
    lines = [f'  <cell index="{index + 1}" type="{xml_escape(cell_type)}">']
    lines.extend(body)
    lines.append("  </cell>")
    return "\n".join(lines)


def render_cell_plain(cell, index, args, content_requested, image_state):
    cell_type = cell.get("cell_type", "unknown")
    chunks = []
    if args.metadata:
        metadata = f"Cell {index + 1} metadata:\n{json.dumps(cell.get('metadata', {}), indent=2, sort_keys=True)}"
        chunks.append(comment_block(metadata) if args.comments else metadata)
    if cell_type == "markdown" and content_requested["markdown"]:
        text = truncate(source_text(cell), args)
        chunks.append(comment_block(text) if args.comments else text)
    elif cell_type == "code":
        if content_requested["code"]:
            chunks.append(truncate(source_text(cell), args))
        if content_requested["output"]:
            output_text = outputs_as_plain(cell.get("outputs", []), args, image_state)
            if output_text:
                chunks.append(comment_block(output_text) if args.comments else output_text)
    return "\n\n".join(chunk for chunk in chunks if chunk)


def outputs_as_plain(outputs, args, image_state):
    chunks = []
    for output in outputs:
        output_type = output.get("output_type")
        if output_type == "stream":
            chunks.append(join_text(output.get("text", "")))
        elif output_type == "error":
            chunks.append(error_text(output))
        else:
            data = output.get("data", {})
            text = rich_text(data)
            if text:
                chunks.append(text)
            for mime, payload in output_images(output):
                image_ref = image_reference(mime, payload, args, image_state)
                if image_ref:
                    chunks.append(image_ref)
    return "\n\n".join(truncate(chunk, args) for chunk in chunks if chunk)


def outputs_as_xml(outputs, args, image_state):
    chunks = []
    for output in outputs:
        output_type = output.get("output_type")
        if output_type == "stream":
            text = join_text(output.get("text", ""))
            if text:
                chunks.append(xml_escape(truncate(text, args)))
        elif output_type == "error":
            text = error_text(output)
            if text:
                chunks.append(xml_escape(truncate(text, args)))
        else:
            data = output.get("data", {})
            text = rich_text(data)
            if text:
                chunks.append(xml_escape(truncate(text, args)))
            for mime, payload in output_images(output):
                image_ref = image_reference(mime, payload, args, image_state)
                if image_ref:
                    chunks.append(f'<img src="{xml_escape(image_ref)}"/>')
    return "\n".join(chunk for chunk in chunks if chunk)


def source_text(cell):
    return join_text(cell.get("source", ""))


def join_text(value):
    if isinstance(value, list):
        return "".join(str(part) for part in value)
    if value is None:
        return ""
    return str(value)


def rich_text(data):
    for mime in ("text/plain", "text/html"):
        if mime in data:
            return join_text(data[mime])
    return ""


def error_text(output):
    traceback = join_text(output.get("traceback", ""))
    if traceback:
        return traceback
    ename = output.get("ename", "")
    evalue = output.get("evalue", "")
    return f"{ename}: {evalue}".strip(": ")


def output_images(output):
    data = output.get("data", {})
    images = []
    for mime in IMAGE_MIME_EXTENSIONS:
        if mime in data:
            images.append((mime, join_text(data[mime])))
    return images


def image_reference(mime, payload, args, image_state):
    if args.images == "skip":
        return ""
    if args.images == "base64":
        compact_payload = re.sub(r"\s+", "", payload)
        return f"data:{mime};base64,{compact_payload}"
    return write_image(mime, payload, image_state)


def extract_images(notebook, selected_indexes, image_state):
    for index in selected_indexes:
        cell = notebook.get("cells", [])[index]
        for output in cell.get("outputs", []):
            for mime, payload in output_images(output):
                write_image(mime, payload, image_state)


def write_image(mime, payload, image_state):
    image_dir = image_state["dir"]
    image_dir.mkdir(parents=True, exist_ok=True)
    extension = IMAGE_MIME_EXTENSIONS.get(mime, ".img")
    while True:
        path = image_dir / f"image-{image_state['next']}{extension}"
        image_state["next"] += 1
        if not path.exists():
            break
    if mime == "image/svg+xml" and payload.lstrip().startswith("<"):
        path.write_text(payload, encoding="utf-8")
    else:
        compact_payload = re.sub(r"\s+", "", payload)
        path.write_bytes(base64.b64decode(compact_payload))
    return path.name


def cell_search_text(cell):
    chunks = [source_text(cell)]
    for output in cell.get("outputs", []):
        if output.get("output_type") == "stream":
            chunks.append(join_text(output.get("text", "")))
        elif output.get("output_type") == "error":
            chunks.append(error_text(output))
        else:
            chunks.append(rich_text(output.get("data", {})))
    return "\n".join(chunks)


def has_error_output(cell):
    return cell.get("cell_type") == "code" and any(
        output.get("output_type") == "error"
        for output in cell.get("outputs", [])
    )


def truncate(text, args):
    if args.no_truncate or args.max_chars is None or args.max_chars < 0:
        return text
    if len(text) <= args.max_chars:
        return text
    omitted = len(text) - args.max_chars
    return f"{text[:args.max_chars]}\n...[truncated {omitted} chars]"


def comment_block(text):
    lines = text.splitlines()
    if not lines:
        return "#"
    return "\n".join(f"# {line}" if line else "#" for line in lines)


def indent(text, prefix):
    if not text:
        return prefix.rstrip()
    return "\n".join(prefix + line if line else prefix.rstrip() for line in text.splitlines())


def xml_escape(text):
    return html.escape(text, quote=True)
