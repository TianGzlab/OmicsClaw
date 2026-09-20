"""Plan 0031 Q22: the first layer allowed to do I/O, and its two rules.

Rule 1 — *no tool argument and no tool output is ever logged.* A
``write_file``'s content, a ``bash`` command and a ``web_fetch`` URL can
each carry a subject identifier, and ``CLAUDE.md``'s first safety rule
("genetic data never leaves this machine") is one a log file on that
machine can still break.

Rule 2 — *a REPL owning the terminal reroutes logging, and puts it back.*
The harness redirects its log sink before starting its UI and restores it
with a ``defer`` (``tui.go:365-367``). A ``WARNING`` in the middle of a
streamed sentence corrupts the one thing the user is reading.
"""

from __future__ import annotations

import asyncio
import io
import logging
import pathlib

import pytest

from omicsclaw.entry.cli import Repl, ScriptedSource, Screen, terminal_owned_logging
from omicsclaw.entry.session import attach_sessions
from omicsclaw.schema import Message, Role, ToolDefinition
from omicsclaw.tools import ApprovalMode, ToolPolicy, require_approval
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    calling,
    make_app,
)

WAIT_S = 10.0

SUBJECT = "PATIENT-7-GRCh38-chr17-43094464"
"""A string that looks like a subject identifier and is easy to find.

Long and unmistakable on purpose: a substring search for something like
``patient`` would match a docstring, and this test is about a leak, not
about vocabulary.
"""


class Recording:
    """A tool whose arguments carry a subject identifier into the layer.

    ``ASK`` rather than ``AUTO``, and the difference is the point: the
    approval path is where this layer gets **handed** the raw argument
    payload (``ApprovalRequest.arguments``, kept raw on purpose so a
    prompt shows what will actually run). An ``AUTO`` tool exercises the
    tool-call and tool-result frames and leaves the one place a surface is
    most tempted to log the payload untouched — which is where a
    "nothing is logged" test would pass while proving less than it looks.
    """

    policy = ToolPolicy(approval_mode=ApprovalMode.ASK, concurrency_safe=True)

    @property
    def name(self) -> str:
        return "sequence_lookup"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="sequence_lookup",
            description="Looks a variant up.",
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        await require_approval(self.name, arguments)
        return f"found {SUBJECT} in the cohort"


def carrying_subject() -> Message:
    """One assistant message whose tool call names the subject."""
    call = calling("sequence_lookup").tool_calls[0]
    return Message(
        role=Role.ASSISTANT,
        tool_calls=(
            type(call)(
                id=call.id,
                name=call.name,
                arguments=f'{{"variant": "{SUBJECT}"}}',
            ),
        ),
    )


# ---- rule 1 -----------------------------------------------------------


def test_a_tool_argument_never_reaches_a_log_record(tmp_path: pathlib.Path):
    """Drive a real tool call at ``DEBUG`` and read every record.

    ``DEBUG`` and not the default, because the rule has to hold at the
    most verbose setting an operator can choose — a rule that only holds
    while nobody is looking closely is not one.
    """

    async def drive() -> tuple[str, str]:
        app = attach_sessions(
            make_app(
                tmp_path,
                Scripted(
                    carrying_subject(),
                    Message(role=Role.ASSISTANT, content="looked it up"),
                ),
                tools=(Recording(),),
            )
        )
        screen = io.StringIO()
        repl = Repl(
            app,
            source=ScriptedSource(["find that variant", "y", "/exit"]),
            screen=Screen.into(screen),
        )
        records = io.StringIO()
        handler = logging.StreamHandler(records)
        handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
        logger = logging.getLogger("omicsclaw")
        previous_level, previous_propagate = logger.level, logger.propagate
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            await asyncio.wait_for(repl.run(), WAIT_S)
            await asyncio.wait_for(app.aclose(), WAIT_S)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate
        return records.getvalue(), screen.getvalue()

    logged, printed = asyncio.run(drive())

    assert "looked it up" in printed, "the turn must actually have run"
    assert SUBJECT not in logged
    # Nor on the screen: a terminal is a log with a scrollback buffer.
    assert SUBJECT not in printed


# ---- rule 2 -----------------------------------------------------------


def test_records_are_rerouted_while_the_repl_owns_the_terminal():
    """What was going to the screen goes to the returned sink instead."""
    screen_handler = logging.StreamHandler(io.StringIO())
    root = logging.getLogger()
    root.addHandler(screen_handler)
    previous = root.level
    root.setLevel(logging.INFO)
    try:
        with terminal_owned_logging() as records:
            logging.getLogger("omicsclaw.test").info("a background warning")
            assert len(root.handlers) == 1
            assert screen_handler not in root.handlers
        assert screen_handler in root.handlers
    finally:
        root.removeHandler(screen_handler)
        root.setLevel(previous)

    assert "a background warning" in records.getvalue()
    assert screen_handler.stream.getvalue() == ""


def test_the_previous_sink_is_restored_even_when_the_body_raises():
    """The ``defer`` half. A REPL that raised on its way out must not
    leave the process logging into a buffer nobody will read."""
    root = logging.getLogger()
    before = list(root.handlers)

    with pytest.raises(RuntimeError, match="boom"):
        with terminal_owned_logging():
            raise RuntimeError("boom")

    assert root.handlers == before


def test_a_quieted_logger_gets_its_level_back():
    """The noisy-logger levels are a loan, not a change.

    ``httpx`` at ``ERROR`` for the duration of a chat is right; ``httpx``
    at ``ERROR`` for the rest of the process because a REPL ran once is a
    surface reaching outside its own lifetime.
    """
    httpx = logging.getLogger("httpx")
    previous = httpx.level
    httpx.setLevel(logging.DEBUG)
    try:
        with terminal_owned_logging():
            assert httpx.level != logging.DEBUG
        assert httpx.level == logging.DEBUG
    finally:
        httpx.setLevel(previous)
