"""What the terminal is shown, and the two facts it must not blur.

Plan 0031 traps 6 and 7 land here because this surface is where a frame
becomes something a person reads. Both are checked **structurally** —
against constants imported from :mod:`omicsclaw.entry.render`, never
against prose — which is appendix C-Y13's requirement and also the only
form that survives somebody improving the wording.

The pump is driven over a :class:`~omicsclaw.entry.turn.TurnHandle`
constructed directly and fed by hand. That is the registry's job in
production, and doing it here is deliberate: these tests are about what
five particular frames look like on a screen, and reaching them through a
real engine would mean arranging for a backend that reports no usage and
one that reports zero, which no scripted provider can do at the same time.
"""

from __future__ import annotations

import asyncio
import io

import pytest

from omicsclaw.engine import EngineEvent
from omicsclaw.entry.cli import MarkdownStreamFormatter, Repl, ScriptedSource, Screen
from omicsclaw.entry.cli._reasoning import REASONING_HEADER
from omicsclaw.entry.events import TurnEvent
from omicsclaw.entry.render import (
    ELAPSED_INCLUDES_APPROVAL_WAIT,
    USAGE_UNREPORTED,
    USAGE_ZERO,
)
from omicsclaw.entry.session import attach_sessions
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.schema import Message, Role, ToolCall, ToolResult, Usage
from omicsclaw.tools.context import ApprovalRequest
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    make_app,
)

WAIT_S = 10.0


def pump_over(tmp_path, frames, *, show_reasoning: bool = False) -> str:
    """Publish *frames*, run the pump over them, return what was printed.

    The terminal frame is appended here rather than by each caller: a
    stream that never seals leaves the pump waiting on ``queue.get()``
    forever, which is trap 1b seen from the consumer's side.
    """

    async def drive() -> str:
        app = attach_sessions(
            make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="x")))
        )
        buffer = io.StringIO()
        repl = Repl(
            app,
            source=ScriptedSource(()),
            screen=Screen.into(buffer),
            show_reasoning=show_reasoning,
        )
        handle = TurnHandle(session_id="s1", turn_id="t1")
        for frame in frames:
            handle.stream.publish(frame)
        handle.stream.publish(
            TurnEvent.exchange_end("converged", session_id="s1", turn_id="t1")
        )
        handle._settle("converged")
        await asyncio.wait_for(repl._pump(handle), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    return asyncio.run(drive())


def engine_frame(event: EngineEvent) -> TurnEvent:
    return TurnEvent.from_engine(event, session_id="s1", turn_id="t1")


# ---- trap 6: the elapsed figure is not "how long the tool took" -------


def test_a_tool_result_carries_the_includes_approval_wait_constant(tmp_path):
    """``duration_s`` is measured by the scheduler and **includes** the
    time a human spent deciding (``engine/types.py:239-245``).

    The assertion is on the imported constant, not on a sentence: a
    renderer that starts calling this "tool time" has to delete a name,
    and a surface that stops printing tool results at all fails here too —
    which is the mutation that would otherwise hide the whole guarantee.
    """
    printed = pump_over(
        tmp_path,
        [
            engine_frame(
                EngineEvent.tool_finished(
                    ToolResult(tool_call_id="c0", name="bash", output="ok"),
                    duration_s=12.0,
                )
            )
        ],
    )

    assert ELAPSED_INCLUDES_APPROVAL_WAIT in printed
    assert "tool time" not in printed.lower()


# ---- trap 7: a missing count and a zero count are different facts -----


def test_unreported_usage_and_zero_usage_do_not_render_the_same(tmp_path):
    """``usage=None`` is "the backend said nothing"; a zero
    :class:`~omicsclaw.schema.Usage` is "free **or** unreported".

    ``Completion.usage`` cannot express the difference
    (``engine/types.py:204-215``), so the blocking path reports zero for
    both — which is why the zero string says both things and the ``None``
    string says neither. Rendering them alike would put "0 tokens" under
    an answer that cost money.
    """
    missing = pump_over(tmp_path, [engine_frame(EngineEvent.turn_end(1, None))])
    zero = pump_over(tmp_path, [engine_frame(EngineEvent.turn_end(1, Usage()))])

    assert USAGE_UNREPORTED in missing
    assert USAGE_ZERO in zero
    assert missing != zero


def test_only_a_reported_count_is_added_to_the_session_total(tmp_path):
    """``/usage`` must not invent zeros for turns nobody counted."""

    async def drive() -> list[int]:
        app = attach_sessions(
            make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="x")))
        )
        repl = Repl(app, source=ScriptedSource(()), screen=Screen.into(io.StringIO()))
        repl._count(engine_frame(EngineEvent.turn_end(1, None)))
        repl._count(engine_frame(EngineEvent.turn_end(2, Usage(input_tokens=7))))
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return repl._usage

    assert asyncio.run(drive()) == [7, 0]


# ---- what the console must not eat ------------------------------------


def test_an_approval_id_survives_rich_markup(tmp_path):
    """A rendered line is data, so it is printed as data.

    ``TextRenderer`` writes an approval's correlation id as
    ``[abc#1]``, and rich reads square brackets as a style tag: printed
    through an f-string with markup enabled, the id **disappears** — and
    it is the one thing a person needs to match a card to a question. The
    same hazard covers any tool whose name or reason contains a bracket.
    """
    request = ApprovalRequest(tool_name="bash", reason="delete [42] files")
    printed = pump_over(
        tmp_path,
        [
            TurnEvent.approval_required(
                request, "t1#1", session_id="s1", turn_id="t1"
            )
        ],
    )

    assert "[t1#1]" in printed
    assert "delete [42] files" in printed


def test_a_screen_that_fails_mid_stream_still_detaches_the_observation(tmp_path):
    """The ``async with`` around the cursor, and the only way to reach it.

    ``TurnStream.observer_count`` counts *attachments*, and an object with
    ``__anext__`` has no ``break`` hook — so an observation left by an
    exception is still attached, the "last observer left" grace period
    never starts, and the Task running the exchange is kept alive by a
    cursor nobody holds (plan 0031 trap 9, from the consumer's side).

    A broken pipe is how this happens in production: ``oc cli | head
    -5`` closes the far end mid-answer.
    """

    class Breaking:
        """A console that fails the way a closed pipe does."""

        def __init__(self) -> None:
            self.size = type("Size", (), {"width": 80})()
            self.calls = 0

        def print(self, *args, **kwargs) -> None:
            self.calls += 1
            if self.calls > 1:
                raise BrokenPipeError("the reader went away")

    async def drive():
        app = attach_sessions(
            make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="x")))
        )
        repl = Repl(app, source=ScriptedSource(()), screen=Screen(Breaking()))
        handle = TurnHandle(session_id="s1", turn_id="t1")
        for index in range(4):
            handle.stream.publish(
                engine_frame(EngineEvent.turn_end(index, Usage(input_tokens=1)))
            )
        handle.stream.publish(
            TurnEvent.exchange_end("converged", session_id="s1", turn_id="t1")
        )
        handle._settle("converged")
        with pytest.raises(BrokenPipeError):
            await asyncio.wait_for(repl._pump(handle), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return handle.stream.observer_count()

    assert asyncio.run(drive()) == 0


# ---- the ported Markdown formatter ------------------------------------


def test_a_half_written_emphasis_waits_for_the_line_that_settles_it():
    """The rule the ported formatter exists for.

    A stream that printed every delta would show ``**Mor`` and then have
    to unprint it. The prefix before the first character that could start
    markup is safe and goes out; the rest waits.
    """
    buffer = io.StringIO()
    formatter = MarkdownStreamFormatter(Screen.into(buffer).console)

    formatter.write("Moran's I is ")
    early = buffer.getvalue()
    formatter.write("**spatial**")
    formatter.finish()

    assert early == "Moran's I is "
    assert buffer.getvalue() == "Moran's I is spatial"


def test_a_completed_line_is_rendered_as_soon_as_it_ends():
    """Newline is what settles a line, so it is what releases it."""
    buffer = io.StringIO()
    formatter = MarkdownStreamFormatter(Screen.into(buffer).console)

    formatter.write("- one\n- two\n")

    assert buffer.getvalue() == "- one\n- two\n"


def test_the_tail_is_printed_even_though_it_never_ended(tmp_path):
    """An answer with no trailing newline is still an answer.

    A formatter that only flushed on newline would silently drop the last
    sentence of every reply that did not end in one.
    """

    async def drive() -> str:
        app = attach_sessions(
            make_app(
                tmp_path,
                Scripted(Message(role=Role.ASSISTANT, content="no newline here")),
            )
        )
        buffer = io.StringIO()
        repl = Repl(
            app,
            source=ScriptedSource(["question", "/exit"]),
            screen=Screen.into(buffer),
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    assert "no newline here" in asyncio.run(drive())


def test_reasoning_is_off_unless_it_was_asked_for(tmp_path):
    """``Repl`` shows reasoning only when told to; the *product* decides.

    Since 2026-09-23 ``oc cli`` tells it to by default —— the owner's
    ruling, resolved in ``ReplOptions.shows_reasoning`` in the process
    shell, where a pipe can be told from a person. The library default
    stays off so that an embedding caller gets the answer alone unless it
    asks for more.
    """
    frames = [engine_frame(EngineEvent.reasoning("because Moran's I is a ratio"))]

    assert "because Moran's I" not in pump_over(tmp_path, frames)


def test_reasoning_appears_when_the_switch_is_on(tmp_path):
    async def drive() -> str:
        app = attach_sessions(
            make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="x")))
        )
        buffer = io.StringIO()
        repl = Repl(
            app,
            source=ScriptedSource(()),
            screen=Screen.into(buffer),
            show_reasoning=True,
        )
        handle = TurnHandle(session_id="s1", turn_id="t1")
        handle.stream.publish(
            engine_frame(EngineEvent.reasoning("because Moran's I is a ratio"))
        )
        handle.stream.publish(
            TurnEvent.exchange_end("converged", session_id="s1", turn_id="t1")
        )
        handle._settle("converged")
        await asyncio.wait_for(repl._pump(handle), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    assert "because Moran's I is a ratio" in asyncio.run(drive())


def test_a_tool_call_is_announced_with_the_argument_it_was_given(tmp_path):
    """Q22 rule 1 no longer covers the screen. Owner's ruling, recorded here.

    It used to: a terminal is a log with a scrollback buffer, and
    ``write_file``'s content or ``bash``'s command can carry a subject
    identifier, so the transcript said ``-> bash`` and nothing else. The
    cost was a transcript nobody could read — ``-> bash`` does not say
    *which* command, and after the fact that is the only question worth
    asking. The owner weighed the two and chose legibility for this
    surface.

    **The log half of the rule is untouched and is now tested on its
    own** (``test_cli_logging.py``): a record can be shipped somewhere
    this scrollback never goes, so the two stopped being one rule. A
    deployment that needs the old behaviour back passes
    ``ToolTranscript(detail=False)``.
    """
    call = ToolCall(id="c0", name="bash", arguments='{"command": "cat PATIENT-7.vcf"}')
    printed = pump_over(tmp_path, [engine_frame(EngineEvent.tool_start(call))])

    assert "-> bash" in printed
    assert 'command="cat PATIENT-7.vcf"' in printed
    assert "(1)" in printed, "the number its result will pair back to"


def test_a_message_the_user_typed_is_never_read_as_markup(tmp_path):
    """The model's answer is data too.

    An answer containing ``[dim]`` is a plausible thing for a model
    explaining this codebase to write, and rich would swallow it.
    """

    async def drive() -> str:
        app = attach_sessions(
            make_app(
                tmp_path,
                Scripted(Message(role=Role.ASSISTANT, content="use [dim]text[/dim]")),
            )
        )
        buffer = io.StringIO()
        repl = Repl(
            app,
            source=ScriptedSource(["how?", "/exit"]),
            screen=Screen.into(buffer),
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    assert "[dim]text[/dim]" in asyncio.run(drive())


def test_reasoning_reads_as_one_block_set_apart_from_the_answer(tmp_path):
    """What the owner saw was ``[reasoning] The[reasoning]  user``, and an
    answer glued to the last word of the thinking (``look.I'll``).

    One header, a gutter, one blank line, then the answer.
    """
    frames = [
        engine_frame(EngineEvent.reasoning(delta))
        for delta in ("The", " user", " asks.", "\n\n", "Let", " me", " look.")
    ] + [
        engine_frame(EngineEvent.text(delta))
        for delta in ("I'll", " explore", " first.\n")
    ]

    out = pump_over(tmp_path, frames, show_reasoning=True)

    assert "[reasoning]" not in out
    assert out.count(REASONING_HEADER) == 1
    assert (
        f"{REASONING_HEADER}\n"
        "│ The user asks.\n"
        "│\n"
        "│ Let me look.\n"
        "\n"
        "I'll explore first.\n"
    ) in out


def test_thinking_resumed_after_a_tool_line_starts_after_a_gap(tmp_path):
    """Without it the second block's header sits on the tool line's heels."""
    frames = [
        engine_frame(
            EngineEvent.tool_start(
                ToolCall(id="c1", name="bash", arguments='{"command": "ls"}')
            )
        ),
        engine_frame(EngineEvent.reasoning("The README is huge.")),
    ]

    out = pump_over(tmp_path, frames, show_reasoning=True)

    assert f'-> bash  command="ls"\n\n{REASONING_HEADER}\n' in out
