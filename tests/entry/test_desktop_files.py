"""``GET /files/tree`` and ``GET /files/serve`` as plain functions.

Runs without a web framework; ``test_desktop_http.py`` covers the routes
over HTTP.

The containment rules are plan 0066 §3.2 (S23): a path is judged by its
real path, so ``..``, absolute paths and symlinks cannot reach outside the
workspace. Q3 = a hides and refuses every path segment below the workspace
that starts with ``.``, whether it is in the spelling or in the real path,
so a link with an ordinary name cannot expose ``.env`` either.

The ``Range`` rules are §3.2 and pitfall 22: Starlette's ``FileResponse``
answers 416 for any range on an empty file and the App's preview always
sends one, so the route computes the span itself. The type rules are S26:
anything a browser would run (HTML, JavaScript, XML other than SVG) goes
out as text. The open is non-blocking and does not follow a final symlink
(pitfall 24), so a path swapped for a FIFO after the check cannot hang the
backend.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import threading

import pytest

from omicsclaw.entry.desktop.files import (
    FILES_SERVE_MAX_BYTES,
    FILES_TREE_MAX_NODES,
    ByteSpan,
    byte_span,
    content_disposition,
    file_chunks,
    file_tree,
    open_served_file,
    resolve_in_workspace,
    serve_target,
    served_media_type,
    tree_depth,
)
from omicsclaw.entry.desktop.turn_submission import DesktopIngressError


@pytest.fixture
def ws(tmp_path: pathlib.Path) -> pathlib.Path:
    """A workspace with data, a figure and a secret, next to an outside file."""
    root = tmp_path / "ws"
    (root / "data").mkdir(parents=True)
    (root / "data" / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (root / "fig").mkdir()
    (root / "fig" / "umap.png").write_bytes(b"\x89PNG....")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (root / ".omicsclaw").mkdir()
    (root / ".omicsclaw" / "plan.md").write_text("plan", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    (tmp_path / "outside-dir").mkdir()
    (tmp_path / "outside-dir" / "b.txt").write_text("b", encoding="utf-8")
    return root


def refusal(call, *args, **kwargs) -> tuple[int, str]:
    with pytest.raises(DesktopIngressError) as caught:
        call(*args, **kwargs)
    return caught.value.status_code, caught.value.code


def names(nodes: list[dict]) -> list[str]:
    return [node["name"] for node in nodes]


# ---- resolving a path --------------------------------------------------------


def test_a_relative_path_is_joined_to_the_workspace(ws):
    found = resolve_in_workspace(ws, "data/a.csv", directory=False)
    assert found.lexical == ws / "data" / "a.csv"
    assert found.real == (ws / "data" / "a.csv").resolve()


def test_an_absolute_path_inside_the_workspace(ws):
    found = resolve_in_workspace(ws, str(ws / "data"), directory=True)
    assert found.real == (ws / "data").resolve()


@pytest.mark.parametrize(
    "raw",
    ["../outside.txt", "data/../../outside.txt", "../../../../etc/passwd", "/etc/hostname"],
)
def test_a_path_outside_the_workspace_is_refused(ws, raw):
    """Refused before existence is checked, so the answer does not say
    whether a file outside exists."""
    assert refusal(resolve_in_workspace, ws, raw, directory=False) == (
        403,
        "path_outside_workspace",
    )


def test_an_absolute_path_outside_that_does_not_exist_is_still_403(ws):
    assert refusal(
        resolve_in_workspace, ws, "/no/such/file", directory=False
    ) == (403, "path_outside_workspace")


def test_dot_dot_is_collapsed_on_the_spelling(ws):
    found = resolve_in_workspace(ws, "fig/../data/a.csv", directory=False)
    assert found.lexical == ws / "data" / "a.csv"


def test_a_file_link_pointing_outside_is_refused(ws, tmp_path):
    (ws / "escape.txt").symlink_to(tmp_path / "outside.txt")
    assert refusal(resolve_in_workspace, ws, "escape.txt", directory=False) == (
        403,
        "path_outside_workspace",
    )


def test_a_path_through_a_directory_link_pointing_outside_is_refused(ws, tmp_path):
    (ws / "elsewhere").symlink_to(tmp_path / "outside-dir")
    assert refusal(
        resolve_in_workspace, ws, "elsewhere/b.txt", directory=False
    ) == (403, "path_outside_workspace")


def test_a_link_pointing_inside_is_followed(ws):
    (ws / "linked-data").symlink_to(ws / "data")
    found = resolve_in_workspace(ws, "linked-data/a.csv", directory=False)
    assert found.lexical == ws / "linked-data" / "a.csv"
    assert found.real == (ws / "data" / "a.csv").resolve()


@pytest.mark.parametrize(
    "raw", [".env", ".omicsclaw/plan.md", "data/.hidden.csv", "./.env", "data/../.env"]
)
def test_a_hidden_segment_is_refused(ws, raw):
    (ws / "data" / ".hidden.csv").write_text("h", encoding="utf-8")
    assert refusal(resolve_in_workspace, ws, raw, directory=False) == (
        403,
        "hidden_path",
    )


def test_a_hidden_path_that_does_not_exist_is_still_403(ws):
    assert refusal(resolve_in_workspace, ws, ".ssh/id_rsa", directory=False) == (
        403,
        "hidden_path",
    )


def test_a_link_with_an_ordinary_name_pointing_at_a_hidden_file_is_refused(ws):
    (ws / "settings.txt").symlink_to(ws / ".env")
    assert refusal(resolve_in_workspace, ws, "settings.txt", directory=False) == (
        403,
        "hidden_path",
    )


def test_dot_directories_above_the_workspace_do_not_count(tmp_path):
    root = tmp_path / ".projects" / "ws"
    root.mkdir(parents=True)
    (root / "a.txt").write_text("a", encoding="utf-8")
    assert resolve_in_workspace(root, "a.txt", directory=False).lexical == root / "a.txt"


def test_a_workspace_spelled_through_a_link_accepts_both_spellings(tmp_path, ws):
    alias = tmp_path / "alias"
    alias.symlink_to(ws)
    via_alias = resolve_in_workspace(alias, str(alias / "data/a.csv"), directory=False)
    via_real = resolve_in_workspace(alias, str(ws / "data/a.csv"), directory=False)
    assert via_alias.real == via_real.real


@pytest.mark.parametrize(
    ("raw", "directory", "expected"),
    [
        ("", False, (422, "path_required")),
        ("data/a\x00.csv", False, (422, "invalid_path")),
        ("data/missing.csv", False, (404, "file_not_found")),
        ("missing-dir", True, (404, "directory_not_found")),
        ("data", False, (422, "not_a_file")),
        ("data/a.csv", True, (422, "not_a_directory")),
        ("data/a.csv/deeper", False, (404, "file_not_found")),
    ],
)
def test_resolution_refusals(ws, raw, directory, expected):
    assert refusal(resolve_in_workspace, ws, raw, directory=directory) == expected


def test_a_directory_the_backend_may_not_search_is_403(ws, monkeypatch):
    """Tests run as root, which searches every directory, so the
    PermissionError a mode-0 directory raises is simulated."""
    real_resolve = pathlib.Path.resolve

    def resolve(self, strict=False):
        if self.name == "a.csv":
            raise PermissionError(13, "Permission denied", str(self))
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(pathlib.Path, "resolve", resolve)
    assert refusal(resolve_in_workspace, ws, "data/a.csv", directory=False) == (
        403,
        "permission_denied",
    )


def test_a_broken_link_is_not_found(ws):
    (ws / "dangling.txt").symlink_to(ws / "gone.txt")
    assert refusal(resolve_in_workspace, ws, "dangling.txt", directory=False) == (
        404,
        "file_not_found",
    )


# ---- the tree ------------------------------------------------------------------


def test_the_tree_lists_the_workspace_by_default(ws):
    payload = file_tree(ws)
    assert payload["root"] == str(ws)
    assert payload["truncated"] is False
    assert names(payload["tree"]) == ["data", "fig"]
    data = payload["tree"][0]
    assert data == {
        "name": "data",
        "path": str(ws / "data"),
        "type": "directory",
        "children": [
            {
                "name": "a.csv",
                "path": str(ws / "data" / "a.csv"),
                "type": "file",
                "size": 8,
                "extension": "csv",
            }
        ],
    }


def test_the_tree_of_a_relative_subdirectory(ws):
    payload = file_tree(ws, "fig")
    assert payload["root"] == str(ws / "fig")
    assert names(payload["tree"]) == ["umap.png"]


def test_the_extension_has_no_dot_and_is_absent_without_one(ws):
    (ws / "Makefile").write_text("all:\n", encoding="utf-8")
    (ws / "b.tar.gz").write_bytes(b"")
    files = {node["name"]: node for node in file_tree(ws, depth=1)["tree"]}
    assert "extension" not in files["Makefile"]
    assert files["b.tar.gz"]["extension"] == "gz"


def test_the_tree_hides_dot_entries(ws):
    (ws / "data" / ".cache-file").write_text("x", encoding="utf-8")
    payload = file_tree(ws)
    assert ".env" not in names(payload["tree"])
    assert ".omicsclaw" not in names(payload["tree"])
    assert names(payload["tree"][0]["children"]) == ["a.csv"]


def test_the_tree_leaves_out_the_ignored_directories(ws):
    for name in ("node_modules", "dist", "build", "coverage", "__pycache__"):
        (ws / name).mkdir()
    (ws / "build.log").write_text("a file, not a directory", encoding="utf-8")
    assert names(file_tree(ws, depth=1)["tree"]) == ["data", "fig", "build.log"]


def test_the_tree_orders_directories_first_then_names_ignoring_case(ws):
    (ws / "Zeta").mkdir()
    (ws / "alpha").mkdir()
    (ws / "B.txt").write_text("b", encoding="utf-8")
    (ws / "a.txt").write_text("a", encoding="utf-8")
    assert names(file_tree(ws, depth=1)["tree"]) == [
        "alpha",
        "data",
        "fig",
        "Zeta",
        "a.txt",
        "B.txt",
    ]


def test_the_tree_leaves_out_links_that_resolve_outside_or_to_hidden_files(
    ws, tmp_path
):
    (ws / "elsewhere").symlink_to(tmp_path / "outside-dir")
    (ws / "escape.txt").symlink_to(tmp_path / "outside.txt")
    (ws / "settings.txt").symlink_to(ws / ".env")
    (ws / "dangling.txt").symlink_to(ws / "gone.txt")
    assert names(file_tree(ws, depth=1)["tree"]) == ["data", "fig"]


def test_the_tree_lists_a_link_pointing_inside_under_its_own_name(ws):
    (ws / "linked-data").symlink_to(ws / "data")
    (ws / "figure.png").symlink_to(ws / "fig" / "umap.png")
    tree = file_tree(ws)["tree"]
    by_name = {node["name"]: node for node in tree}
    assert by_name["linked-data"]["type"] == "directory"
    assert by_name["linked-data"]["children"][0]["path"] == str(
        ws / "linked-data" / "a.csv"
    )
    assert by_name["figure.png"] == {
        "name": "figure.png",
        "path": str(ws / "figure.png"),
        "type": "file",
        "size": 8,
        "extension": "png",
    }


def test_depth_one_lists_only_the_directory_itself(ws):
    tree = file_tree(ws, depth=1)["tree"]
    assert tree[0]["children"] == []


def test_depth_bounds_the_walk(ws):
    deep = ws / "d1" / "d2" / "d3"
    deep.mkdir(parents=True)
    (deep / "leaf.txt").write_text("x", encoding="utf-8")
    d1 = {node["name"]: node for node in file_tree(ws, depth=2)["tree"]}["d1"]
    assert names(d1["children"]) == ["d2"]
    assert d1["children"][0]["children"] == []
    d1 = {node["name"]: node for node in file_tree(ws, depth=4)["tree"]}["d1"]
    assert names(d1["children"][0]["children"][0]["children"]) == ["leaf.txt"]


@pytest.mark.parametrize("depth", [0, 11, -1])
def test_a_depth_outside_one_to_ten_is_refused(ws, depth):
    assert refusal(file_tree, ws, depth=depth) == (422, "invalid_depth")


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, 3), ("", 3), ("1", 1), (" 10 ", 10)]
)
def test_the_depth_parameter(raw, expected):
    assert tree_depth(raw) == expected


@pytest.mark.parametrize("raw", ["0", "11", "two", "1.5", "-3"])
def test_a_bad_depth_parameter_is_refused(raw):
    assert refusal(tree_depth, raw) == (422, "invalid_depth")


def test_links_to_the_same_directory_are_each_listed(ws):
    """Only a link back to an ancestor is left out, so a link to a sibling
    directory shows its contents under its own name."""
    (ws / "alias-one").symlink_to(ws / "data")
    (ws / "alias-two").symlink_to(ws / "data")
    by_name = {node["name"]: node for node in file_tree(ws)["tree"]}
    for name in ("data", "alias-one", "alias-two"):
        assert names(by_name[name]["children"]) == ["a.csv"]


def test_a_link_back_to_an_ancestor_is_left_out(ws):
    """A cycle would otherwise be walked to the depth limit."""
    (ws / "data" / "up").symlink_to(ws)
    (ws / "data" / "self").symlink_to(ws / "data")
    tree = file_tree(ws, depth=10)["tree"]
    assert names(tree[0]["children"]) == ["a.csv"]


def test_the_node_limit_truncates_the_walk_breadth_first(ws):
    for index in range(5):
        (ws / "data" / f"f{index}.txt").write_text("x", encoding="utf-8")
    payload = file_tree(ws, depth=3, max_nodes=4)
    assert payload["truncated"] is True
    assert names(payload["tree"]) == ["data", "fig"]
    assert len(payload["tree"][0]["children"]) == 2
    assert payload["tree"][1]["children"] == []


def test_the_default_node_limit(ws):
    assert FILES_TREE_MAX_NODES == 10_000
    assert file_tree(ws)["truncated"] is False


def test_the_tree_refuses_what_resolution_refuses(ws, tmp_path):
    assert refusal(file_tree, ws, "../outside-dir") == (403, "path_outside_workspace")
    assert refusal(file_tree, ws, ".omicsclaw") == (403, "hidden_path")
    assert refusal(file_tree, ws, "data/a.csv") == (422, "not_a_directory")
    assert refusal(file_tree, ws, "nope") == (404, "directory_not_found")


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads every directory")
def test_an_unreadable_directory_has_no_children(ws):
    locked = ws / "locked"
    locked.mkdir()
    (locked / "x.txt").write_text("x", encoding="utf-8")
    locked.chmod(0)
    try:
        by_name = {node["name"]: node for node in file_tree(ws)["tree"]}
        assert by_name["locked"]["children"] == []
    finally:
        locked.chmod(0o700)


# ---- one file ------------------------------------------------------------------


def test_serve_target_opens_the_real_path_under_the_requested_name(ws):
    (ws / "figure.png").symlink_to(ws / "fig" / "umap.png")
    target = serve_target(ws, "figure.png")
    assert target.path == (ws / "fig" / "umap.png").resolve()
    assert target.name == "figure.png"
    assert target.media_type == "image/png"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("page.html", "text/plain; charset=utf-8"),
        ("page.htm", "text/plain; charset=utf-8"),
        ("page.xhtml", "text/plain; charset=utf-8"),
        ("app.js", "text/plain; charset=utf-8"),
        ("app.mjs", "text/plain; charset=utf-8"),
        ("data.xml", "text/plain; charset=utf-8"),
        ("style.xsl", "text/plain; charset=utf-8"),
        ("style.xslt", "text/plain; charset=utf-8"),
        ("graph.rdf", "text/plain; charset=utf-8"),
        ("plot.svg", "image/svg+xml"),
        ("plot.svgz", "application/octet-stream"),
        ("table.tar.gz", "application/octet-stream"),
        ("matrix.h5ad", "application/octet-stream"),
        ("umap.png", "image/png"),
        ("report.pdf", "application/pdf"),
        ("a.csv", "text/csv"),
    ],
)
def test_the_media_type(name, expected):
    assert served_media_type(name) == expected


def test_content_disposition_is_inline_and_safe_for_any_name():
    assert content_disposition("a.csv") == 'inline; filename="a.csv"'
    assert content_disposition("图 1.png") == (
        "inline; filename*=utf-8''%E5%9B%BE%201.png"
    )
    assert content_disposition('a"b.txt') == "inline; filename*=utf-8''a%22b.txt"


def test_open_served_file_reports_the_size_of_the_open_handle(ws):
    opened = open_served_file(serve_target(ws, "data/a.csv").path)
    try:
        assert opened.size == 8
    finally:
        opened.close()


def test_a_file_swapped_for_a_fifo_after_the_check_is_refused_without_blocking(ws):
    target = serve_target(ws, "data/a.csv")
    target.path.unlink()
    os.mkfifo(target.path)
    outcome: list[object] = []

    def attempt() -> None:
        try:
            open_served_file(target.path)
        except DesktopIngressError as exc:
            outcome.append((exc.status_code, exc.code))

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "opening the FIFO blocked"
    assert outcome == [(422, "not_a_file")]


def test_a_file_swapped_for_a_link_after_the_check_is_refused(ws, tmp_path):
    target = serve_target(ws, "data/a.csv")
    target.path.unlink()
    target.path.symlink_to(tmp_path / "outside.txt")
    assert refusal(open_served_file, target.path) == (422, "not_a_file")


def test_a_file_removed_after_the_check_is_not_found(ws):
    target = serve_target(ws, "data/a.csv")
    target.path.unlink()
    assert refusal(open_served_file, target.path) == (404, "file_not_found")


def read_all(opened, span) -> bytes:
    async def collect() -> bytes:
        return b"".join([chunk async for chunk in file_chunks(opened, span, chunk_bytes=3)])

    return asyncio.run(collect())


def test_file_chunks_yield_the_span_and_close_the_file(ws):
    (ws / "digits.txt").write_bytes(b"0123456789")
    opened = open_served_file(serve_target(ws, "digits.txt").path)
    assert read_all(opened, byte_span("bytes=2-7", opened.size)) == b"234567"
    assert opened.handle.closed


# ---- Range -----------------------------------------------------------------------

LIMIT = 100


def test_without_a_range_the_whole_file_up_to_the_limit():
    assert byte_span(None, 100, limit=LIMIT) == ByteSpan(0, 100, 100, partial=False)


def test_without_a_range_a_file_over_the_limit_is_413():
    assert refusal(byte_span, None, 101, limit=LIMIT) == (413, "file_too_large")


def test_the_default_limit_is_64_mib():
    assert FILES_SERVE_MAX_BYTES == 64 * 1024 * 1024
    assert byte_span(None, FILES_SERVE_MAX_BYTES).length == FILES_SERVE_MAX_BYTES
    assert refusal(byte_span, None, FILES_SERVE_MAX_BYTES + 1) == (
        413,
        "file_too_large",
    )


@pytest.mark.parametrize("header", ["bytes=0-9", "bytes=5-", "bytes=-3", "bytes=0-0"])
def test_any_range_on_an_empty_file_is_ignored(header):
    span = byte_span(header, 0, limit=LIMIT)
    assert (span.status, span.length) == (200, 0)


@pytest.mark.parametrize(
    ("header", "start", "stop"),
    [
        ("bytes=0-9", 0, 10),
        ("bytes=10-19", 10, 20),
        ("bytes=40-", 40, 50),
        ("bytes=-5", 45, 50),
        ("bytes=-500", 0, 50),
        ("bytes=45-1000", 45, 50),
        ("Bytes = 1 - 2", 1, 3),
    ],
)
def test_a_single_range(header, start, stop):
    span = byte_span(header, 50, limit=LIMIT)
    assert (span.status, span.start, span.stop) == (206, start, stop)
    assert span.content_range == f"bytes {start}-{stop - 1}/50"


@pytest.mark.parametrize("header", ["bytes=50-", "bytes=50-60", "bytes=900-", "bytes=-0"])
def test_a_range_starting_at_or_past_the_end_is_416(header):
    assert refusal(byte_span, header, 50, limit=LIMIT) == (416, "range_not_satisfiable")


def test_an_open_range_on_a_large_file_is_capped_at_the_limit():
    """``<video>`` asks for ``bytes=0-``; a 413 there would stop playback."""
    span = byte_span("bytes=0-", 1000, limit=LIMIT)
    assert (span.status, span.start, span.stop) == (206, 0, LIMIT)
    assert span.content_range == "bytes 0-99/1000"


def test_a_closed_range_larger_than_the_limit_is_capped():
    span = byte_span("bytes=10-900", 1000, limit=LIMIT)
    assert (span.start, span.stop) == (10, 10 + LIMIT)


def test_a_suffix_larger_than_the_limit_is_capped_from_its_start():
    span = byte_span("bytes=-500", 1000, limit=LIMIT)
    assert (span.start, span.stop) == (500, 500 + LIMIT)


@pytest.mark.parametrize(
    "header",
    [
        "bytes=0-9,20-29",
        "bytes=0-9, 20-",
        "items=0-9",
        "bytes=9-0",
        "bytes=-",
        "bytes=a-b",
        "",
        "bytes=0-" + "9" * 5000,
        "bytes=" + "1" * 20 + "-",
        "bytes=\u0661-\u0662",
    ],
)
def test_a_multi_part_or_malformed_range_is_ignored(header):
    """A number longer than 19 digits, or in non-ASCII digits, is malformed:
    Python refuses to parse a string of more than 4300 digits, which would
    otherwise turn the request into a 500."""
    span = byte_span(header, 50, limit=LIMIT)
    assert (span.status, span.start, span.stop) == (200, 0, 50)


def test_an_ignored_range_on_a_large_file_is_413():
    assert refusal(byte_span, "bytes=0-9,20-29", 1000, limit=LIMIT) == (
        413,
        "file_too_large",
    )
