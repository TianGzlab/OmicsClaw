"""The audit hook: what it records, what it refuses to record, and where.

Two rules carry most of this file.

**It observes and nothing else.** An observer that changes what the model
reads is not an observer, and an observer whose sink failing fails the
tool is worse than no observer.

**The arguments are never written down.** ``permission/gate.py`` states
the rule for the layer that sees the same bytes; an audit file outlives
the session, so the rule is stricter here, not looser. A test that only
checked the happy path would not notice a ``bash`` command line landing
in a file on disk.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import stat

import pytest

from omicsclaw.hooks import (
    SESSION_ID_KEY,
    AuditHook,
    AuditOutcome,
    AuditRecord,
    AuditSink,
    Hook,
    HookCall,
    HookDecision,
    JsonlAuditSink,
    ToolHook,
    arguments_digest,
    deny,
    hook_tools,
)
from omicsclaw.schema import ToolCall
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.context import use_tool_context

from ._support import Echo, Raiser, Recorder, run

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

SECRET = '{"text": "patient-4417 BRCA1 c.5266dupC"}'
"""A payload with something in it that must not reach a file."""


class ListSink:
    """A sink that keeps records in memory. Satisfies the Protocol by shape."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def write(self, record: AuditRecord) -> None:
        self.records.append(record)


class BrokenSink:
    def __init__(self) -> None:
        self.attempts = 0

    async def write(self, record: AuditRecord) -> None:
        self.attempts += 1
        raise OSError("disk full")


def audited(tool, *, sink: ListSink | None = None):
    """One tool behind one audit hook, plus the sink it writes to."""
    destination = sink if sink is not None else ListSink()
    return hook_tools([tool], (AuditHook(destination),))[0], destination


# ---- what is recorded ---------------------------------------------------


def test_a_successful_call_is_recorded_as_ok():
    hooked, sink = audited(Echo())

    run(hooked.execute(SECRET))

    assert len(sink.records) == 1
    assert sink.records[0].outcome is AuditOutcome.OK
    assert sink.records[0].tool == "echo"
    assert sink.records[0].detail == ""


def test_a_failed_call_is_recorded_as_the_exception_class():
    hooked, sink = audited(Raiser(ValueError("bad threshold")))

    with pytest.raises(ValueError):
        run(hooked.execute("{}"))

    assert sink.records[0].outcome is AuditOutcome.ERROR
    assert sink.records[0].detail == "ValueError"


def test_a_failures_message_is_dropped_because_it_quotes_the_arguments():
    """The repair this step's own tests found.

    ``read_file`` names the path it could not open, ``bash`` quotes the
    command, ``web_fetch`` echoes the URL. Recording "the wording the
    model was shown" therefore put arguments into a file that outlives
    the transcript. The class name is a fixed vocabulary no argument can
    reach; ``tests/entry/test_hook_wiring.py`` pins the real tool.
    """
    hooked, sink = audited(Raiser(FileNotFoundError(SECRET)))

    with pytest.raises(FileNotFoundError):
        run(hooked.execute("{}"))

    assert sink.records[0].detail == "FileNotFoundError"
    assert "BRCA1" not in sink.records[0].as_json()


def test_a_failure_with_no_message_still_names_the_class():
    hooked, sink = audited(Raiser(ValueError()))

    with pytest.raises(ValueError):
        run(hooked.execute("{}"))

    assert sink.records[0].detail == "ValueError"


def test_a_refusal_by_a_later_hook_is_recorded_as_denied_not_as_an_error():
    """The record an audit trail exists for, and the reason for mount order.

    ``AuditHook`` mounted *first* is the one still listening when a hook
    mounted after it refuses. Mounted last it would see nothing at all,
    and the file would show a machine that never refused anything.
    """
    sink = ListSink()
    hooked = hook_tools(
        [Echo()], (AuditHook(sink), Recorder("guard", decision=deny("off-machine")))
    )[0]

    with pytest.raises(Exception):
        run(hooked.execute("{}"))

    assert sink.records[0].outcome is AuditOutcome.DENIED
    assert "off-machine" in sink.records[0].detail


def test_mounted_last_it_would_have_recorded_nothing():
    """The negative of the test above, so the ordering rule is not folklore."""
    sink = ListSink()
    hooked = hook_tools(
        [Echo()], (Recorder("guard", decision=deny("off-machine")), AuditHook(sink))
    )[0]

    with pytest.raises(Exception):
        run(hooked.execute("{}"))

    assert sink.records == []


def test_a_cancelled_call_is_recorded_as_cancelled_not_as_an_error():
    """A log that conflates the two reports a failure rate that is Ctrl-C."""
    hooked, sink = audited(Raiser(asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        run(hooked.execute("{}"))

    assert sink.records[0].outcome is AuditOutcome.CANCELLED


def test_a_keyboard_interrupt_is_cancellation_too_not_a_tool_failure():
    hooked, sink = audited(Raiser(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        run(hooked.execute("{}"))

    assert sink.records[0].outcome is AuditOutcome.CANCELLED


def test_the_session_is_recorded_when_a_surface_bound_one():
    hooked, sink = audited(Echo())

    async def scenario() -> None:
        with use_tool_context(values={SESSION_ID_KEY: "s-42"}):
            await hooked.execute("{}")

    run(scenario())

    assert sink.records[0].session_id == "s-42"


def test_no_session_is_not_an_error_it_is_an_empty_column():
    hooked, sink = audited(Echo())

    run(hooked.execute("{}"))

    assert sink.records[0].session_id == ""


def test_the_session_key_matches_what_the_turn_layer_binds():
    """This layer may not import ``entry``, so it checks the literal.

    An assumption about another layer's spelling that nothing checks is
    how a whole audit file quietly loses its session column — every row
    still written, every row still true, and every row unattributable.
    """
    source = (_REPO_ROOT / "omicsclaw" / "entry" / "turn.py").read_text("utf-8")

    assert f'"{SESSION_ID_KEY}": session_id' in source


def test_the_timestamp_is_wall_clock_so_it_can_be_correlated():
    import time

    before = time.time()
    hooked, sink = audited(Echo())
    run(hooked.execute("{}"))

    assert before <= sink.records[0].at <= time.time()


# ---- what is *not* recorded ---------------------------------------------


def test_the_arguments_never_reach_the_record():
    hooked, sink = audited(Echo())

    run(hooked.execute(SECRET))

    written = sink.records[0].as_json()
    assert "BRCA1" not in written
    assert "patient-4417" not in written
    assert SECRET not in written


def test_the_arguments_never_reach_the_file_either():
    """The same rule where it actually costs something: bytes on disk."""
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        path = pathlib.Path(raw) / "audit.jsonl"
        hooked, _ = audited(Echo(), sink=JsonlAuditSink(path))  # type: ignore[arg-type]
        run(hooked.execute(SECRET))

        assert "BRCA1" not in path.read_text("utf-8")


def test_a_failures_detail_is_the_exception_class_not_the_arguments():
    hooked, sink = audited(Raiser(ValueError("bad threshold")))

    with pytest.raises(ValueError):
        run(hooked.execute(SECRET))

    assert "BRCA1" not in sink.records[0].as_json()


def test_a_refusal_keeps_its_reason_because_this_deployment_wrote_it():
    """The asymmetry, stated as a test so it is a decision and not a slip.

    A denial reason is composed by a hook in this deployment's own code;
    dropping it would leave an audit line nobody can act on.
    """
    sink = ListSink()
    hooked = hook_tools(
        [Echo()],
        (AuditHook(sink), Recorder("guard", decision=deny("genetic data off-machine"))),
    )[0]

    with pytest.raises(Exception):
        run(hooked.execute(SECRET))

    assert "genetic data off-machine" in sink.records[0].detail
    assert "BRCA1" not in sink.records[0].as_json()


# ---- the digest ---------------------------------------------------------


def test_the_digest_is_stable_and_short():
    assert arguments_digest("{}") == arguments_digest("{}")
    assert len(arguments_digest("{}")) == 16


def test_the_digest_separates_two_calls_of_the_same_tool():
    hooked, sink = audited(Echo())

    run(hooked.execute('{"text": "a"}'))
    run(hooked.execute('{"text": "b"}'))

    assert sink.records[0].arguments_digest != sink.records[1].arguments_digest


def test_the_digest_joins_two_calls_with_the_same_payload():
    hooked, sink = audited(Echo())

    run(hooked.execute('{"text": "a"}'))
    run(hooked.execute('{"text": "a"}'))

    assert sink.records[0].arguments_digest == sink.records[1].arguments_digest


def test_the_digest_is_of_the_bytes_not_of_a_re_encoding():
    """Two payloads that decode to the same object are not the same call.

    Byte-exactness is what lets the digest join to a transcript entry:
    the transcript stores what the model sent, not a normalisation of it.
    """
    assert arguments_digest('{"a": 1}') != arguments_digest('{"a":1}')


def test_the_digest_recorded_is_of_what_actually_ran():
    """A hook that rewrote the payload changes what is audited."""
    sink = ListSink()
    hooked = hook_tools(
        [Echo()],
        (
            AuditHook(sink),
            Recorder("r", decision=HookDecision(arguments='{"text": "rewritten"}')),
        ),
    )[0]

    run(hooked.execute('{"text": "original"}'))

    assert sink.records[0].arguments_digest == arguments_digest(
        '{"text": "rewritten"}'
    )


# ---- it observes, and only observes -------------------------------------


def test_the_hook_returns_the_output_untouched():
    hooked, _ = audited(Echo())

    assert run(hooked.execute('{"text": "x"}')) == 'echo:{"text": "x"}'


def test_a_broken_sink_does_not_fail_the_tool():
    sink = BrokenSink()
    hooked = hook_tools([Echo()], (AuditHook(sink),))[0]

    assert run(hooked.execute("{}")) == "echo:{}"
    assert sink.attempts == 1


def test_a_broken_sink_does_not_reach_the_model():
    sink = BrokenSink()
    registry = ToolRegistry(hook_tools([Echo()], (AuditHook(sink),)))

    result = run(registry.execute(ToolCall(id="1", name="echo", arguments="{}")))

    assert not result.is_error, result.output


def test_a_broken_sink_does_not_mask_a_real_failure():
    sink = BrokenSink()
    hooked = hook_tools([Raiser(ValueError("real"))], (AuditHook(sink),))[0]

    with pytest.raises(ValueError, match="real"):
        run(hooked.execute("{}"))


def test_the_hook_never_denies():
    hooked, _ = audited(Echo())

    assert run(hooked.execute("{}")) == "echo:{}"


def test_the_hook_satisfies_the_protocol_and_inherits_the_no_ops():
    hook = AuditHook(ListSink())

    assert isinstance(hook, ToolHook)
    assert isinstance(hook, Hook)
    assert run(hook.before_execute(HookCall(name="x", arguments="{}"))) == (
        HookDecision()
    )


def test_a_list_sink_satisfies_the_sink_protocol_by_shape():
    assert isinstance(ListSink(), AuditSink)


# ---- the file sink ------------------------------------------------------


def test_the_file_holds_one_json_object_per_line(tmp_path: pathlib.Path):
    path = tmp_path / "audit.jsonl"
    hooked = hook_tools([Echo()], (AuditHook(JsonlAuditSink(path)),))[0]

    run(hooked.execute('{"text": "a"}'))
    run(hooked.execute('{"text": "b"}'))

    lines = path.read_text("utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["tool"] for line in lines] == ["echo", "echo"]


def test_the_file_is_appended_to_not_rewritten(tmp_path: pathlib.Path):
    """A JSON array would have to be rewritten, and a killed process would
    leave a file no parser opens — the run whose record matters most."""
    path = tmp_path / "audit.jsonl"
    path.write_text('{"pre": "existing"}\n', encoding="utf-8")

    hooked = hook_tools([Echo()], (AuditHook(JsonlAuditSink(path)),))[0]
    run(hooked.execute("{}"))

    assert path.read_text("utf-8").splitlines()[0] == '{"pre": "existing"}'


def test_the_directory_is_created_on_first_write(tmp_path: pathlib.Path):
    path = tmp_path / "nested" / "deeper" / "audit.jsonl"
    sink = JsonlAuditSink(path)

    assert not path.parent.exists(), "constructing a sink creates nothing"

    run(sink.write(_record()))

    assert path.is_file()


def test_the_file_is_owner_readable_only(tmp_path: pathlib.Path):
    """An audit trail names what a machine did and belongs to its owner."""
    path = tmp_path / "audit.jsonl"

    run(JsonlAuditSink(path).write(_record()))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_the_sink_reports_its_path(tmp_path: pathlib.Path):
    path = tmp_path / "audit.jsonl"

    assert JsonlAuditSink(path).path == path


def test_the_sink_raises_rather_than_dropping_a_record(tmp_path: pathlib.Path):
    """One place decides what a write failure means, and it is the hook.

    A sink that swallowed would make an empty audit file and a quiet
    machine look identical.
    """
    path = tmp_path / "audit.jsonl"
    path.mkdir()

    with pytest.raises(OSError):
        run(JsonlAuditSink(path).write(_record()))


def test_a_record_serialises_with_sorted_keys():
    """So two records of the same shape are byte-identical."""
    written = _record().as_json()

    assert list(json.loads(written)) == sorted(json.loads(written))


def test_a_record_keeps_non_ascii_readable():
    """``ensure_ascii=False``: a Chinese denial reason is for a person."""
    record = AuditRecord(
        tool="bash",
        outcome=AuditOutcome.DENIED,
        arguments_digest="0" * 16,
        at=0.0,
        detail="拒绝",
    )

    assert "拒绝" in record.as_json()


def _record() -> AuditRecord:
    return AuditRecord(
        tool="echo",
        outcome=AuditOutcome.OK,
        arguments_digest=arguments_digest("{}"),
        at=0.0,
    )
