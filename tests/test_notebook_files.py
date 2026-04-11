"""Unit tests for the notebook `.ipynb` file I/O helper module.

Covers pure-Python parsing and listing helpers — not the FastAPI layer.
The router-level integration checks live in `test_app_server.py` and the
new `test_notebook_files_router` test in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_ipynb_bytes(cells: list[dict]) -> bytes:
    import nbformat

    nb = nbformat.v4.new_notebook()
    for cell in cells:
        if cell["cell_type"] == "code":
            nb.cells.append(nbformat.v4.new_code_cell(source=cell["source"]))
        elif cell["cell_type"] == "markdown":
            nb.cells.append(nbformat.v4.new_markdown_cell(source=cell["source"]))
        elif cell["cell_type"] == "raw":
            nb.cells.append(nbformat.v4.new_raw_cell(source=cell["source"]))
    return nbformat.writes(nb).encode("utf-8")


# ---------------------------------------------------------------------------
# parse_ipynb_bytes
# ---------------------------------------------------------------------------


class TestParseIpynbBytes:
    def test_returns_code_and_markdown_cells(self):
        from omicsclaw.app.notebook.nb_files import parse_ipynb_bytes

        raw = _make_ipynb_bytes(
            [
                {"cell_type": "markdown", "source": "# Title"},
                {"cell_type": "code", "source": "x = 1"},
            ]
        )

        cells = parse_ipynb_bytes(raw)

        assert len(cells) == 2
        assert cells[0]["cell_type"] == "markdown"
        assert cells[0]["source"] == "# Title"
        assert cells[1]["cell_type"] == "code"
        assert cells[1]["source"] == "x = 1"

    def test_drops_raw_cells(self):
        from omicsclaw.app.notebook.nb_files import parse_ipynb_bytes

        raw = _make_ipynb_bytes(
            [
                {"cell_type": "code", "source": "y = 2"},
                {"cell_type": "raw", "source": "raw content"},
            ]
        )

        cells = parse_ipynb_bytes(raw)
        types = [cell["cell_type"] for cell in cells]
        assert "raw" not in types
        assert "code" in types

    def test_each_cell_includes_empty_outputs_list(self):
        from omicsclaw.app.notebook.nb_files import parse_ipynb_bytes

        raw = _make_ipynb_bytes([{"cell_type": "code", "source": "1+1"}])
        cells = parse_ipynb_bytes(raw)

        assert cells[0]["outputs"] == []

    def test_raises_on_non_json_bytes(self):
        from omicsclaw.app.notebook.nb_files import parse_ipynb_bytes

        with pytest.raises(ValueError):
            parse_ipynb_bytes(b"\x00\x01\x02 not json")

    def test_raises_on_json_that_is_not_a_notebook(self):
        from omicsclaw.app.notebook.nb_files import parse_ipynb_bytes

        with pytest.raises(ValueError):
            parse_ipynb_bytes(json.dumps({"hello": "world"}).encode("utf-8"))

    def test_handles_utf8_with_bom(self):
        from omicsclaw.app.notebook.nb_files import parse_ipynb_bytes

        raw = _make_ipynb_bytes([{"cell_type": "code", "source": "a = 1"}])
        cells = parse_ipynb_bytes(b"\xef\xbb\xbf" + raw)
        assert len(cells) == 1


# ---------------------------------------------------------------------------
# list_ipynb_files
# ---------------------------------------------------------------------------


class TestListIpynbFiles:
    def test_returns_sorted_ipynb_names(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import list_ipynb_files

        (tmp_path / "b.ipynb").write_text("{}")
        (tmp_path / "a.ipynb").write_text("{}")
        (tmp_path / "readme.md").write_text("not an ipynb")

        files = list_ipynb_files(str(tmp_path))

        assert files == ["a.ipynb", "b.ipynb"]

    def test_ignores_directories_with_ipynb_suffix(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import list_ipynb_files

        (tmp_path / "not_a_file.ipynb").mkdir()
        (tmp_path / "real.ipynb").write_text("{}")

        files = list_ipynb_files(str(tmp_path))
        assert files == ["real.ipynb"]

    def test_returns_empty_for_missing_directory(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import list_ipynb_files

        missing = tmp_path / "does_not_exist"
        assert list_ipynb_files(str(missing)) == []

    def test_returns_empty_for_file_path_instead_of_dir(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import list_ipynb_files

        f = tmp_path / "x.ipynb"
        f.write_text("{}")
        assert list_ipynb_files(str(f)) == []


# ---------------------------------------------------------------------------
# resolve_ipynb_path (path-traversal guard)
# ---------------------------------------------------------------------------


class TestResolveIpynbPath:
    def test_resolves_simple_filename(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import resolve_ipynb_path

        target = tmp_path / "a.ipynb"
        target.write_text("{}")

        resolved = resolve_ipynb_path(str(tmp_path), "a.ipynb")
        assert Path(resolved).resolve() == target.resolve()

    def test_rejects_parent_directory_escape(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import resolve_ipynb_path

        with pytest.raises(ValueError):
            resolve_ipynb_path(str(tmp_path), "../etc/passwd.ipynb")

    def test_rejects_absolute_path(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import resolve_ipynb_path

        with pytest.raises(ValueError):
            resolve_ipynb_path(str(tmp_path), "/tmp/evil.ipynb")

    def test_rejects_non_ipynb_extension(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import resolve_ipynb_path

        with pytest.raises(ValueError):
            resolve_ipynb_path(str(tmp_path), "a.txt")


# ---------------------------------------------------------------------------
# create_empty_notebook / save_notebook / delete_notebook
# ---------------------------------------------------------------------------


class TestCreateEmptyNotebook:
    def test_creates_valid_empty_notebook_file(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import create_empty_notebook, parse_ipynb_bytes

        path = create_empty_notebook(str(tmp_path), "new.ipynb")

        assert Path(path).exists()
        cells = parse_ipynb_bytes(Path(path).read_bytes())
        assert cells == []

    def test_creates_parent_directory_if_missing(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import create_empty_notebook

        root = tmp_path / "nested" / "sub"
        path = create_empty_notebook(str(root), "x.ipynb")
        assert Path(path).exists()

    def test_refuses_to_overwrite_existing(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import create_empty_notebook

        (tmp_path / "x.ipynb").write_text("{}")
        with pytest.raises(FileExistsError):
            create_empty_notebook(str(tmp_path), "x.ipynb")

    def test_rejects_path_escape(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import create_empty_notebook

        with pytest.raises(ValueError):
            create_empty_notebook(str(tmp_path), "../escape.ipynb")


class TestSaveNotebook:
    def test_round_trip_code_and_markdown_cells(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import (
            create_empty_notebook,
            parse_ipynb_bytes,
            save_notebook,
        )

        create_empty_notebook(str(tmp_path), "x.ipynb")
        cells_in = [
            {"cell_type": "markdown", "source": "# Title"},
            {"cell_type": "code", "source": "print('hi')"},
        ]
        save_notebook(str(tmp_path), "x.ipynb", cells_in)

        cells_out = parse_ipynb_bytes((tmp_path / "x.ipynb").read_bytes())
        assert len(cells_out) == 2
        assert cells_out[0]["cell_type"] == "markdown"
        assert cells_out[0]["source"] == "# Title"
        assert cells_out[1]["source"] == "print('hi')"

    def test_creates_file_if_missing(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import save_notebook

        save_notebook(
            str(tmp_path),
            "fresh.ipynb",
            [{"cell_type": "code", "source": "x = 1"}],
        )
        assert (tmp_path / "fresh.ipynb").exists()

    def test_rejects_invalid_cell_type(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import save_notebook

        with pytest.raises(ValueError):
            save_notebook(
                str(tmp_path),
                "y.ipynb",
                [{"cell_type": "raw", "source": "bad"}],
            )

    def test_rejects_path_escape(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import save_notebook

        with pytest.raises(ValueError):
            save_notebook(
                str(tmp_path),
                "../escape.ipynb",
                [{"cell_type": "code", "source": "x"}],
            )


class TestDeleteNotebook:
    def test_removes_existing_file(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import delete_notebook

        f = tmp_path / "doomed.ipynb"
        f.write_text("{}")
        delete_notebook(str(tmp_path), "doomed.ipynb")
        assert not f.exists()

    def test_missing_file_raises_file_not_found(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import delete_notebook

        with pytest.raises(FileNotFoundError):
            delete_notebook(str(tmp_path), "ghost.ipynb")

    def test_rejects_path_escape(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import delete_notebook

        with pytest.raises(ValueError):
            delete_notebook(str(tmp_path), "../../etc/passwd.ipynb")


# ---------------------------------------------------------------------------
# FastAPI router integration (uses TestClient, no kernel required)
# ---------------------------------------------------------------------------


def _import_client():
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app.notebook.router import router

    app = FastAPI()
    app.include_router(router, prefix="/notebook")
    return TestClient(app)


class TestNotebookFilesRouter:
    def test_list_empty_directory_returns_empty(self, tmp_path: Path):
        client = _import_client()
        resp = client.get(f"/notebook/files/list?root={tmp_path}")
        assert resp.status_code == 200
        assert resp.json() == {"files": [], "root": str(tmp_path)}

    def test_list_returns_sorted_files(self, tmp_path: Path):
        (tmp_path / "beta.ipynb").write_text("{}")
        (tmp_path / "alpha.ipynb").write_text("{}")
        client = _import_client()

        resp = client.get(f"/notebook/files/list?root={tmp_path}")
        assert resp.status_code == 200
        assert resp.json()["files"] == ["alpha.ipynb", "beta.ipynb"]

    def test_upload_returns_parsed_cells(self, tmp_path: Path):
        raw = _make_ipynb_bytes(
            [
                {"cell_type": "markdown", "source": "# Hello"},
                {"cell_type": "code", "source": "print('hi')"},
            ]
        )
        client = _import_client()

        resp = client.post(
            "/notebook/files/upload",
            files={"file": ("demo.ipynb", raw, "application/x-ipynb+json")},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "demo.ipynb"
        assert len(body["cells"]) == 2
        assert body["cells"][0]["cell_type"] == "markdown"

    def test_upload_rejects_non_ipynb_filename(self, tmp_path: Path):
        client = _import_client()
        resp = client.post(
            "/notebook/files/upload",
            files={"file": ("evil.py", b"print('x')", "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_rejects_bad_content(self, tmp_path: Path):
        client = _import_client()
        resp = client.post(
            "/notebook/files/upload",
            files={
                "file": (
                    "broken.ipynb",
                    b"not a notebook at all",
                    "application/x-ipynb+json",
                )
            },
        )
        assert resp.status_code == 400

    def test_open_returns_cells_for_existing_file(self, tmp_path: Path):
        raw = _make_ipynb_bytes([{"cell_type": "code", "source": "1 + 1"}])
        (tmp_path / "nb.ipynb").write_bytes(raw)
        client = _import_client()

        resp = client.post(
            "/notebook/files/open",
            json={"root": str(tmp_path), "filename": "nb.ipynb"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "nb.ipynb"
        assert len(body["cells"]) == 1
        assert body["cells"][0]["source"] == "1 + 1"

    def test_open_404_for_missing_file(self, tmp_path: Path):
        client = _import_client()
        resp = client.post(
            "/notebook/files/open",
            json={"root": str(tmp_path), "filename": "nope.ipynb"},
        )
        assert resp.status_code == 404

    def test_open_rejects_path_escape(self, tmp_path: Path):
        client = _import_client()
        resp = client.post(
            "/notebook/files/open",
            json={"root": str(tmp_path), "filename": "../../etc/passwd.ipynb"},
        )
        assert resp.status_code == 400


class TestNotebookCrudRouter:
    """Router tests for the flat /notebook/{list,open,create,save,delete} CRUD endpoints."""

    def test_list_endpoint_returns_sorted_files(self, tmp_path: Path):
        (tmp_path / "second.ipynb").write_text("{}")
        (tmp_path / "first.ipynb").write_text("{}")
        client = _import_client()

        resp = client.get(f"/notebook/list?root={tmp_path}")
        assert resp.status_code == 200
        assert resp.json()["files"] == ["first.ipynb", "second.ipynb"]

    def test_create_endpoint_writes_empty_notebook(self, tmp_path: Path):
        client = _import_client()
        resp = client.post(
            "/notebook/create",
            json={"root": str(tmp_path), "filename": "brand_new.ipynb"},
        )
        assert resp.status_code == 200
        assert (tmp_path / "brand_new.ipynb").exists()

    def test_create_endpoint_409_on_conflict(self, tmp_path: Path):
        (tmp_path / "dup.ipynb").write_text("{}")
        client = _import_client()
        resp = client.post(
            "/notebook/create",
            json={"root": str(tmp_path), "filename": "dup.ipynb"},
        )
        assert resp.status_code == 409

    def test_open_endpoint_returns_cells(self, tmp_path: Path):
        raw = _make_ipynb_bytes([{"cell_type": "code", "source": "x = 7"}])
        (tmp_path / "o.ipynb").write_bytes(raw)
        client = _import_client()

        resp = client.post(
            "/notebook/open",
            json={"root": str(tmp_path), "filename": "o.ipynb"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["cells"]) == 1
        assert body["cells"][0]["source"] == "x = 7"

    def test_save_endpoint_round_trip(self, tmp_path: Path):
        from omicsclaw.app.notebook.nb_files import parse_ipynb_bytes

        client = _import_client()
        resp = client.post(
            "/notebook/save",
            json={
                "root": str(tmp_path),
                "filename": "saved.ipynb",
                "cells": [
                    {"cell_type": "markdown", "source": "# H"},
                    {"cell_type": "code", "source": "y = 9"},
                ],
            },
        )
        assert resp.status_code == 200

        cells = parse_ipynb_bytes((tmp_path / "saved.ipynb").read_bytes())
        assert [c["cell_type"] for c in cells] == ["markdown", "code"]

    def test_delete_endpoint_removes_file(self, tmp_path: Path):
        (tmp_path / "trash.ipynb").write_text("{}")
        client = _import_client()
        resp = client.post(
            "/notebook/delete",
            json={"root": str(tmp_path), "filename": "trash.ipynb"},
        )
        assert resp.status_code == 200
        assert not (tmp_path / "trash.ipynb").exists()

    def test_delete_endpoint_404_for_missing_file(self, tmp_path: Path):
        client = _import_client()
        resp = client.post(
            "/notebook/delete",
            json={"root": str(tmp_path), "filename": "ghost.ipynb"},
        )
        assert resp.status_code == 404

    def test_create_rejects_path_escape(self, tmp_path: Path):
        client = _import_client()
        resp = client.post(
            "/notebook/create",
            json={"root": str(tmp_path), "filename": "../evil.ipynb"},
        )
        assert resp.status_code == 400
