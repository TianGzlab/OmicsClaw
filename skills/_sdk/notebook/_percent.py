"""Convert a percent-format step file into notebook cells.

The subset understood here:

* Non-blank text before the first ``# %%`` line is the first code cell.
* ``# %%`` starts a code cell; text after it on the same line is the
  cell's title (kept in the cell metadata).
* ``# %% [markdown]`` or ``# %% [md]`` starts a markdown cell. Each of its
  lines drops a leading ``# `` or ``#``; blank lines are kept; any other
  line is an error, because it would run as code outside the notebook.
* Any other bracketed tag is an error naming its line.
* Blank lines at the start and end of a cell are dropped; code is
  otherwise kept as written.
* A notebook magic or shell line is an error: a code line that starts
  with ``%`` or ``!`` outside a string literal where Python reports the
  cell's syntax error. Such lines stop the file from running as
  ``python <file>``. A continuation line such as ``!= b)`` inside an
  expression is plain Python and passes.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from typing import Any

_MARKER = re.compile(r"^# %%(?P<rest>.*)$")
_TAG = re.compile(r"^\s*\[(?P<tag>[^\]]*)\](?P<title>.*)$")
_MARKDOWN_TAGS = {"markdown", "md"}


class PercentError(ValueError):
    """The step file uses something outside the supported percent subset."""


@dataclass
class Cell:
    kind: str
    source: str
    title: str = ""
    line: int = 1
    lines: list[str] = field(default_factory=list, repr=False)


def _trim(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _string_lines(source: str) -> set[int]:
    """1-based lines of *source* that lie inside a string literal after its first line."""
    inside: set[int] = set()
    fstring_start = getattr(tokenize, "FSTRING_START", None)
    fstring_end = getattr(tokenize, "FSTRING_END", None)
    open_fstrings: list[int] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.STRING and token.end[0] > token.start[0]:
                inside.update(range(token.start[0] + 1, token.end[0] + 1))
            elif fstring_start is not None and token.type == fstring_start:
                open_fstrings.append(token.start[0])
            elif fstring_end is not None and token.type == fstring_end and open_fstrings:
                began = open_fstrings.pop()
                inside.update(range(began + 1, token.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return inside


def _check_code(cell: Cell, first_line: int) -> None:
    source = "\n".join(cell.lines)
    try:
        ast.parse(source)
    except SyntaxError as exc:
        offset = exc.lineno
    else:
        return
    if offset is None or not 1 <= offset <= len(cell.lines) or offset in _string_lines(source):
        return
    stripped = cell.lines[offset - 1].lstrip()
    if stripped[:1] in {"%", "!"}:
        number = first_line + offset - 1
        raise PercentError(
            f"line {number}: {stripped[:40]!r} is a notebook magic or shell line; "
            "write plain Python so the step also runs as `python <file>`"
        )


def parse_cells(text: str) -> list[Cell]:
    """Split a step file into cells.

    :raises PercentError: an unknown cell tag, a magic or shell line, or
        code inside a markdown cell.
    """
    cells: list[Cell] = []
    current = Cell(kind="code", source="", line=1)
    body_start = 1

    def close(cell: Cell, start: int) -> None:
        if cell.kind == "code":
            _check_code(cell, start)
        trimmed = _trim(cell.lines)
        if not trimmed:
            return
        cell.source = "\n".join(trimmed)
        cells.append(cell)

    for number, line in enumerate(text.splitlines(), start=1):
        marker = _MARKER.match(line)
        if marker is None:
            if current.kind == "markdown":
                if line.strip() and not line.startswith("#"):
                    raise PercentError(
                        f"line {number}: markdown cells hold only `#` comment lines; "
                        "start a code cell with `# %%` before code"
                    )
                current.lines.append(line[2:] if line.startswith("# ") else line[1:])
            else:
                current.lines.append(line)
            continue
        close(current, body_start)
        rest = marker.group("rest")
        tagged = _TAG.match(rest)
        if tagged is not None:
            tag = tagged.group("tag").strip().lower()
            if tag not in _MARKDOWN_TAGS:
                raise PercentError(
                    f"line {number}: unknown cell tag [{tagged.group('tag')}]; "
                    "use `# %%` for code or `# %% [markdown]` for prose"
                )
            current = Cell(kind="markdown", source="", title=tagged.group("title").strip(), line=number)
        else:
            current = Cell(kind="code", source="", title=rest.strip(), line=number)
        body_start = number + 1
    close(current, body_start)
    return cells


def to_notebook(text: str, *, step: dict[str, Any]) -> Any:
    """The notebook node for a step file; *step* goes into ``metadata.omicsclaw.step``."""
    import nbformat
    from nbformat import v4

    nb = v4.new_notebook()
    for cell in parse_cells(text):
        metadata = {"title": cell.title} if cell.title else {}
        if cell.kind == "markdown":
            nb.cells.append(v4.new_markdown_cell(cell.source, metadata=metadata))
        else:
            nb.cells.append(v4.new_code_cell(cell.source, metadata=metadata))
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["language_info"] = {"name": "python"}
    nb.metadata["omicsclaw"] = {"step": dict(step)}
    nbformat.validate(nb)
    return nb
