import base64
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from ipynb_tool.cli import build_parser, render_notebook


PNG_DATA = base64.b64encode(b"png-bytes").decode("ascii")


def make_notebook():
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3"}},
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Title\n", "Intro text\n"],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": 2,
                "source": ["print('hello')\n"],
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": ["hello\n"]},
                    {
                        "output_type": "display_data",
                        "data": {"image/png": PNG_DATA, "text/plain": "<Figure size>"},
                        "metadata": {},
                    },
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["## Details\n", "More notes\n"],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": 1,
                "source": ["raise ValueError('bad')\n"],
                "outputs": [
                    {
                        "output_type": "error",
                        "ename": "ValueError",
                        "evalue": "bad",
                        "traceback": ["Traceback\n", "ValueError: bad\n"],
                    }
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "source": ["long_value = '" + ("x" * 30) + "'\n"],
                "outputs": [],
            },
        ],
    }


def parse_args(*args):
    return build_parser().parse_args(["notebook.ipynb", *args])


def render(args, notebook=None, path=None):
    notebook = notebook or make_notebook()
    path = path or Path("notebook.ipynb")
    return render_notebook(notebook, path, args)


class CliTests(unittest.TestCase):
    def test_code_returns_plain_code_only(self):
        output = render(parse_args("--code"))

        self.assertIn("print('hello')", output)
        self.assertIn("raise ValueError('bad')", output)
        self.assertNotIn("<notebook>", output)
        self.assertNotIn("# Title", output)
        self.assertNotIn("hello\n\n<Figure", output)

    def test_comments_make_markdown_python_readable(self):
        output = render(parse_args("--code", "--markdown", "--comments", "--noxml"))

        self.assertIn("# # Title", output)
        self.assertIn("print('hello')", output)
        self.assertNotIn("<notebook>", output)

    def test_xml_all_skips_images_by_default(self):
        output = render(parse_args("--xml", "--all"))

        self.assertIn("<notebook>", output)
        self.assertIn('<cell index="1" type="markdown">', output)
        self.assertIn("<code>", output)
        self.assertNotIn("<img", output)

    def test_summary_and_toc_map_notebook(self):
        output = render(parse_args("--summary", "--toc"))

        self.assertIn("Notebook Summary", output)
        self.assertIn("cell types: code=3, markdown=2", output)
        self.assertIn("Table of Contents", output)
        self.assertIn("1: Title", output)
        self.assertIn("3:   Details", output)

    def test_cells_search_around_and_errors_restrict_output(self):
        cells_output = render(parse_args("--cells", "2", "--code"))
        self.assertIn("print('hello')", cells_output)
        self.assertNotIn("raise ValueError", cells_output)

        search_output = render(parse_args("--search", "Details", "--around", "1"))
        self.assertIn("More notes", search_output)
        self.assertIn("print('hello')", search_output)
        self.assertIn("raise ValueError", search_output)

        error_output = render(parse_args("--errors"))
        self.assertIn("raise ValueError", error_output)
        self.assertIn("ValueError: bad", error_output)
        self.assertNotIn("print('hello')", error_output)

    def test_truncation_can_be_disabled(self):
        truncated = render(parse_args("--code", "--cells", "5", "--max-chars", "12"))
        self.assertIn("...[truncated", truncated)

        full = render(parse_args("--code", "--cells", "5", "--max-chars", "12", "--no-truncate"))
        self.assertNotIn("...[truncated", full)
        self.assertIn("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", full)

    def test_images_files_extracts_without_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            args = parse_args("--images", "files", "--image-dir", str(tmp_path))
            output = render(args, path=tmp_path / "notebook.ipynb")

            self.assertEqual("", output)
            image = tmp_path / "image-1.png"
            self.assertTrue(image.exists())
            self.assertEqual(b"png-bytes", image.read_bytes())

    def test_images_base64_preserves_data_uri(self):
        output = render(parse_args("--output", "--images", "base64"))

        self.assertIn(f"data:image/png;base64,{PNG_DATA}", output)


if __name__ == "__main__":
    unittest.main()
