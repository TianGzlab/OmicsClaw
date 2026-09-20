"""The middle grant: "allow this for the rest of this conversation".

``y`` costs a prompt per call and ``a`` writes a rule that outlives the
reason it was written, so the interesting assertions here are about what
*separates* the new option from the old ones: the second call is not
asked about, and the rule file on disk is still not there.

No ``pytest-asyncio`` here, so every test drives :func:`asyncio.run`
itself and bounds every await with :func:`asyncio.wait_for`.
"""

from __future__ import annotations

import asyncio

from omicsclaw.schema import Message, Role
from tests.entry.test_cli_repl import (  # type: ignore[import-not-found]
    WAIT_S,
    build,
    repl_over,
)
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Asking,
    Scripted,
    calling,
)


def _twice(*extra: Message) -> Scripted:
    """A backend that calls ``ask`` twice, answering in between."""
    return Scripted(
        calling("ask"),
        Message(role=Role.ASSISTANT, content="first done"),
        calling("ask"),
        Message(role=Role.ASSISTANT, content="second done"),
        *extra,
    )


def test_allowing_for_this_conversation_stops_asking_and_writes_nothing(
    tmp_path,
):
    """Both halves, because either one alone is a different feature.

    "Stops asking" without "writes nothing" is what ``a`` already did;
    "writes nothing" without "stops asking" is what ``y`` already did.
    The rule file's absence is asserted against the same path
    ``test_cli_repl.py`` finds it at after an ``a``, so the two tests
    disagree about the file if this one ever starts persisting.
    """

    async def drive():
        app = build(tmp_path, _twice(), tools=(Asking("ask"),))
        repl, source, buffer = repl_over(
            app, ["once", "s", "twice", "/exit"]
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts, buffer.getvalue()

    prompts, printed = asyncio.run(drive())

    approvals = [one for one in prompts if one.startswith("approve ask [")]
    assert len(approvals) == 1, f"asked {len(approvals)} times: {prompts}"
    assert "Will not ask about ask again in this conversation" in printed
    assert "allowed for this conversation" in printed
    assert "first done" in printed and "second done" in printed
    assert not (tmp_path / ".omicsclaw" / "settings.json").exists(), (
        "the session-scoped grant reached the rule file"
    )


def test_a_new_conversation_asks_again(tmp_path):
    """The grant is scoped to the conversation, or it is ``a`` by another
    name. ``/new`` is the cheapest way to leave one."""

    async def drive():
        app = build(tmp_path, _twice(), tools=(Asking("ask"),))
        repl, source, _buffer = repl_over(
            app, ["once", "s", "/new", "twice", "n", "/exit"]
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts

    prompts = asyncio.run(drive())

    approvals = [one for one in prompts if one.startswith("approve ask [")]
    assert len(approvals) == 2, f"asked {len(approvals)} times: {prompts}"


def test_the_card_says_the_middle_grant_exists(tmp_path):
    """A key nobody is told about is a key nobody presses.

    The prompt itself still reads ``[y/N/a=always]`` — it is what the
    approval tests name and it is as wide as a narrow terminal wants — so
    the legend above the card is the only place the third option is
    announced.
    """

    async def drive():
        app = build(
            tmp_path,
            Scripted(calling("ask"), Message(role=Role.ASSISTANT, content="ok")),
            tools=(Asking("ask"),),
        )
        repl, _source, buffer = repl_over(app, ["once", "n", "/exit"])
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "s = allow for this conversation" in printed
    assert "a = always, and write a rule" in printed
