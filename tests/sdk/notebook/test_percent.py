"""Percent-format step files to notebook cells."""

from __future__ import annotations

import pytest

from skills._sdk.notebook._percent import PercentError, parse_cells, to_notebook


def test_text_before_the_first_marker_is_a_code_cell():
    cells = parse_cells("import os\nx = 1\n\n# %%\ny = 2\n")
    assert [(c.kind, c.source) for c in cells] == [("code", "import os\nx = 1"), ("code", "y = 2")]


def test_marker_text_becomes_the_cell_title():
    cells = parse_cells("# %% Load the data\nx = 1\n")
    assert cells[0].title == "Load the data"
    assert cells[0].source == "x = 1"


def test_markdown_cells_drop_the_comment_prefix_and_keep_blank_lines():
    text = "# %% [markdown]\n# Cluster the cells.\n#\n# Reads `x`.\n\n# %%\nx = 1\n"
    cells = parse_cells(text)
    assert cells[0].kind == "markdown"
    assert cells[0].source == "Cluster the cells.\n\nReads `x`."
    assert cells[1].kind == "code"


def test_md_is_an_alias_for_markdown():
    assert parse_cells("# %% [md]\n# hi\n")[0].kind == "markdown"


def test_trailing_blank_lines_are_removed_and_code_is_kept_as_written():
    cells = parse_cells("# %%\n    if True:\n        x = 1\n\n\n# %%\ny = 2\n")
    assert cells[0].source == "    if True:\n        x = 1"


def test_an_unknown_tag_is_an_error_with_its_line():
    with pytest.raises(PercentError, match="line 3.*raw"):
        parse_cells("x = 1\n\n# %% [raw]\nfoo\n")


@pytest.mark.parametrize("line", ["%matplotlib inline", "!pip install scanpy", "    %time x = 1"])
def test_magic_and_shell_lines_are_errors(line):
    with pytest.raises(PercentError, match="line 2"):
        parse_cells(f"# %%\n{line}\n")


@pytest.mark.parametrize("body", [
    "keep = (counts\n        != 0)\n",
    "rest = (total\n        % 7)\n",
    "flag = a \\\n    != b\n",
])
def test_an_expression_continued_on_a_line_starting_with_an_operator_is_not_a_magic_line(body):
    cells = parse_cells(f"# %%\n{body}")
    assert cells[0].source == body.rstrip("\n")


def test_a_magic_line_after_valid_code_is_reported_at_its_own_line():
    with pytest.raises(PercentError, match="line 5"):
        parse_cells("# %%\nimport os\nfor i in range(3):\n    print(i)\n%time os.getcwd()\n")


def test_percent_inside_a_string_is_not_a_magic_line():
    cells = parse_cells('# %%\nquery = """\n%s rows\n!important\n"""\n')
    assert "%s rows" in cells[0].source


def test_code_in_a_markdown_cell_is_an_error():
    with pytest.raises(PercentError, match="line 3"):
        parse_cells("# %% [markdown]\n# Title\nx = 1\n")


def test_to_notebook_sets_kernel_and_step_metadata():
    nb = to_notebook("# %% [markdown]\n# Hi\n\n# %%\nx = 1\n", step={"file": "01_a.py", "sha256": "ab", "run_id": "r"})
    assert nb.metadata["kernelspec"]["name"] == "python3"
    assert nb.metadata["language_info"]["name"] == "python"
    assert nb.metadata["omicsclaw"]["step"] == {"file": "01_a.py", "sha256": "ab", "run_id": "r"}
    assert [c.cell_type for c in nb.cells] == ["markdown", "code"]
    assert nb.cells[1].source == "x = 1"
