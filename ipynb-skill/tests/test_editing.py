from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import jupytext
import nbformat

from ipynb_tool.cli import main
from ipynb_tool.editing import PERCENT_FORMAT


def make_notebook():
    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "custom": {"preserve": True},
        }
    )
    notebook.nbformat_minor = 5
    notebook.cells = [
        nbformat.v4.new_markdown_cell(
            "# Title\nIntro\n",
            metadata={"role": "intro"},
            id="intro",
        ),
        nbformat.v4.new_code_cell(
            "print('hello')\n",
            metadata={"role": "greeting"},
            execution_count=7,
            outputs=[nbformat.v4.new_output("stream", name="stdout", text="hello\n")],
            id="hello",
        ),
        nbformat.v4.new_code_cell(
            "value = 3\n",
            metadata={"role": "calculation"},
            execution_count=8,
            outputs=[nbformat.v4.new_output("execute_result", data={"text/plain": "3"}, execution_count=8)],
            id="value",
        ),
    ]
    return notebook


def write_notebook(path, notebook):
    nbformat.write(notebook, path, version=nbformat.NO_CONVERT)


def read_notebook(path):
    return nbformat.read(path, as_version=nbformat.NO_CONVERT)


def invoke(*args):
    stdout = StringIO()
    with redirect_stdout(stdout):
        result = main(list(args))
    return result, stdout.getvalue()


class EditingTests(unittest.TestCase):
    def test_replace_previews_then_writes_and_clears_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notebook_path = root / "sample.ipynb"
            source_path = root / "replacement.py"
            write_notebook(notebook_path, make_notebook())
            source_path.write_text("print('changed')\n", encoding="utf-8")
            original_bytes = notebook_path.read_bytes()

            _, preview = invoke(
                "replace-cell",
                str(notebook_path),
                "id:hello",
                "--source-file",
                str(source_path),
            )

            self.assertEqual(original_bytes, notebook_path.read_bytes())
            self.assertIn("Notebook edit preview", preview)
            self.assertIn("outputs cleared: 1", preview)
            self.assertIn("--write", preview)

            _, applied = invoke(
                "replace-cell",
                str(notebook_path),
                "id:hello",
                "--source-file",
                str(source_path),
                "--write",
            )
            notebook = read_notebook(notebook_path)

            self.assertIn("Notebook edit applied", applied)
            self.assertEqual("print('changed')\n", notebook.cells[1].source)
            self.assertEqual([], notebook.cells[1].outputs)
            self.assertIsNone(notebook.cells[1].execution_count)
            self.assertEqual({"role": "greeting"}, notebook.cells[1].metadata)
            self.assertEqual("hello", notebook.cells[1].id)

    def test_insert_move_and_delete_support_indexes_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notebook_path = root / "sample.ipynb"
            source_path = root / "note.md"
            write_notebook(notebook_path, make_notebook())
            source_path.write_text("Inserted note\n", encoding="utf-8")

            invoke(
                "insert-cell",
                str(notebook_path),
                "--type",
                "markdown",
                "--before",
                "id:hello",
                "--source-file",
                str(source_path),
                "--write",
            )
            inserted = read_notebook(notebook_path)
            self.assertEqual(["intro", inserted.cells[1].id, "hello", "value"], [cell.id for cell in inserted.cells])
            self.assertEqual("Inserted note\n", inserted.cells[1].source)

            invoke(
                "move-cells",
                str(notebook_path),
                "--cells",
                "id:value",
                "--before",
                "1",
                "--write",
            )
            moved = read_notebook(notebook_path)
            self.assertEqual("value", moved.cells[0].id)
            self.assertEqual("3", moved.cells[0].outputs[0].data["text/plain"])

            invoke("delete-cells", str(notebook_path), "--cells", "2-3", "--write")
            deleted = read_notebook(notebook_path)
            self.assertEqual(["value", "hello"], [cell.id for cell in deleted.cells])

    def test_duplicate_selection_and_selected_anchor_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            notebook_path = Path(tmp) / "sample.ipynb"
            write_notebook(notebook_path, make_notebook())

            with self.assertRaisesRegex(SystemExit, "duplicate cell selection"):
                invoke("delete-cells", str(notebook_path), "--cells", "1,id:intro")
            with self.assertRaisesRegex(SystemExit, "destination cannot be"):
                invoke("move-cells", str(notebook_path), "--cells", "2", "--after", "id:hello")

    def test_export_import_noop_preserves_notebook_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notebook_path = root / "sample.ipynb"
            editable_path = root / "sample.edit.py"
            write_notebook(notebook_path, make_notebook())
            original_bytes = notebook_path.read_bytes()

            _, exported = invoke(
                "export-percent",
                str(notebook_path),
                "--output",
                str(editable_path),
            )
            text = editable_path.read_text(encoding="utf-8")

            self.assertIn("Exported 3 cells", exported)
            self.assertIn("# %%", text)
            self.assertIn("_ipynb_tool", text)
            self.assertNotIn("hello\\n", text)

            _, preview = invoke("import-percent", str(editable_path), str(notebook_path))

            self.assertIn("No notebook changes", preview)
            self.assertEqual(original_bytes, notebook_path.read_bytes())

    def test_import_changed_code_clears_outputs_and_rejects_stale_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notebook_path = root / "sample.ipynb"
            editable_path = root / "sample.edit.py"
            write_notebook(notebook_path, make_notebook())
            invoke("export-percent", str(notebook_path), "--output", str(editable_path))
            editable_path.write_text(
                editable_path.read_text(encoding="utf-8").replace("print('hello')", "print('changed')"),
                encoding="utf-8",
            )

            _, preview = invoke("import-percent", str(editable_path), str(notebook_path))
            self.assertIn("outputs cleared: 1", preview)
            invoke("import-percent", str(editable_path), str(notebook_path), "--write")
            changed = read_notebook(notebook_path)
            self.assertEqual("print('changed')", changed.cells[1].source)
            self.assertEqual([], changed.cells[1].outputs)
            self.assertIsNone(changed.cells[1].execution_count)

            with self.assertRaisesRegex(SystemExit, "changed since"):
                invoke("import-percent", str(editable_path), str(notebook_path))

    def test_import_reorder_insert_and_guarded_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notebook_path = root / "sample.ipynb"
            editable_path = root / "sample.edit.py"
            write_notebook(notebook_path, make_notebook())
            invoke("export-percent", str(notebook_path), "--output", str(editable_path))

            parsed = jupytext.reads(editable_path.read_text(encoding="utf-8"), fmt="py:percent")
            parsed.cells = [
                parsed.cells[2],
                parsed.cells[0],
                nbformat.v4.new_markdown_cell("New ending\n"),
            ]
            editable_path.write_text(jupytext.writes(parsed, fmt=PERCENT_FORMAT), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "would delete existing cells 2"):
                invoke("import-percent", str(editable_path), str(notebook_path))

            _, preview = invoke(
                "import-percent",
                str(editable_path),
                str(notebook_path),
                "--allow-delete",
            )
            self.assertIn("reorder", preview)
            self.assertIn("insert cell 3", preview)
            self.assertIn("delete cell 2", preview)

            invoke(
                "import-percent",
                str(editable_path),
                str(notebook_path),
                "--allow-delete",
                "--write",
            )
            notebook = read_notebook(notebook_path)
            self.assertEqual(["value", "intro"], [notebook.cells[0].id, notebook.cells[1].id])
            self.assertEqual("3", notebook.cells[0].outputs[0].data["text/plain"])
            self.assertEqual({"role": "intro"}, notebook.cells[1].metadata)
            self.assertEqual("New ending\n", notebook.cells[2].source)
            self.assertEqual({}, notebook.cells[2].metadata)

    def test_import_creates_python_notebook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            editable_path = root / "new.py"
            notebook_path = root / "new.ipynb"
            editable_path.write_text(
                "# %% [markdown]\n# # New notebook\n\n# %%\nanswer = 42\n",
                encoding="utf-8",
            )

            _, preview = invoke("import-percent", str(editable_path), str(notebook_path))
            self.assertFalse(notebook_path.exists())
            self.assertIn("Notebook edit preview", preview)

            invoke("import-percent", str(editable_path), str(notebook_path), "--write")
            notebook = read_notebook(notebook_path)
            self.assertEqual("python3", notebook.metadata.kernelspec.name)
            self.assertEqual(["markdown", "code"], [cell.cell_type for cell in notebook.cells])
            self.assertEqual(2, len({cell.id for cell in notebook.cells}))
            self.assertEqual([], notebook.cells[1].outputs)
            self.assertIsNone(notebook.cells[1].execution_count)

    def test_export_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notebook_path = root / "sample.ipynb"
            editable_path = root / "sample.py"
            write_notebook(notebook_path, make_notebook())
            editable_path.write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "use --force"):
                invoke("export-percent", str(notebook_path), "--output", str(editable_path))

            invoke(
                "export-percent",
                str(notebook_path),
                "--output",
                str(editable_path),
                "--force",
            )
            self.assertIn("_ipynb_tool", editable_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
