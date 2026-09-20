"""Contract tests for ``omicsclaw.tools.builtin.write`` (plan 0029 task B).

This is the first tool in the new layer that can destroy something, so
the assertions that matter are not "the tool returned an error" but
**"nothing was created"**. Plan 0029 trap 3 is the clearest case: a
symlink inside the workspace pointing out of it must not merely be
refused, it must leave the directory it points at empty — an
implementation that called :meth:`~pathlib.Path.mkdir` before
:meth:`~omicsclaw.tools._workspace.Workspace.resolve` would satisfy the
first reading and fail the second, and the helper layer has no way to
force the order. That is why the check lives here rather than in
``test_workspace.py``.

The same shape recurs: a denied approval, an unbound approval channel and
a cancelled turn are each checked by looking at the filesystem
afterwards, because each of them has a plausible-looking implementation
in which the refusal arrives after the bytes.

Every refusal is paired with a legitimate write, per plan 0029 §10-9:
a tool that refuses everything passes every refusal test ever written.

**The layering rule does not apply to this file**, for the reason
``test_read.py`` and ``test_bash.py`` record.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.schema import ToolCall
from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalMode,
    ApprovalRequest,
    ApprovalUnavailable,
    ProgressUpdate,
    RiskLevel,
    Tool,
    ToolPolicy,
    ToolRegistry,
    WriteTool,
)
from omicsclaw.tools._pathlock import PATH_LOCKS
from omicsclaw.tools._workspace import (
    PathEscapesWorkspace,
    PathIsSensitive,
    Workspace,
)
from omicsclaw.tools.builtin.read import read_tool
from omicsclaw.tools.builtin.write import (
    DIRECTORY_MODE,
    FILE_MODE,
    TOOL_NAME,
    WriteTool as WriteToolDirect,
)
from omicsclaw.tools.context import use_tool_context
from omicsclaw.tools.function_tool import ToolArgumentError

_T = TypeVar("_T")

_DEADLINE = 10.0


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; the suite drives this way."""
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


def _args(**kwargs: Any) -> str:
    return json.dumps(kwargs)


def _yes(seen: list[ApprovalRequest] | None = None):
    """An approval channel that agrees, and optionally keeps the receipts."""

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        if seen is not None:
            seen.append(request)
        return ApprovalDecision(approved=True)

    return channel


def _no(reason: str = "not this time"):
    def channel(request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=False, reason=reason)

    return channel


def _write(workspace: Workspace, *, approve=None, **kwargs: Any) -> str:
    tool = WriteTool(workspace)
    with use_tool_context(approval=approve if approve is not None else _yes()):
        return _run(tool.execute(_args(**kwargs)))


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)


# ---- the ordinary job ----------------------------------------------------


def test_a_write_creates_the_file_and_every_missing_parent(tmp_path):
    """``write_file.go:108``: auto-mkdir, so a model is not made to retry
    a path that only failed because a directory did not exist yet."""
    message = _write(
        _workspace(tmp_path), path="a/b/c/out.txt", content="hello\n"
    )

    written = tmp_path / "a" / "b" / "c" / "out.txt"
    assert written.read_text() == "hello\n"
    assert "Wrote" in message and str(written) in message


def test_every_literal_carried_over_is_the_one_the_reference_uses():
    """Plan 0029 §10-8, and pinned where it cannot follow the code.

    **This test exists because of a mutation that survived without it.**
    The mode test below compares against ``FILE_MODE & ~umask``, so
    changing ``FILE_MODE`` moves both sides and the suite stays green. A
    borrowed literal needs one assertion that names the number.
    """
    assert FILE_MODE == 0o644  # write_file.go:113
    assert DIRECTORY_MODE == 0o755  # write_file.go:108


def test_the_created_file_and_directory_carry_the_reference_modes(tmp_path):
    """:data:`FILE_MODE` and :data:`DIRECTORY_MODE`, **re-verified**.

    ``0644``/``0755`` are ``write_file.go:113``/``:108``, and in Python
    they had to be *implemented* rather than translated:
    :meth:`~pathlib.Path.write_text` has no mode argument and would create
    with ``0666`` masked by the umask. The umask applies here exactly as
    it does to Go's ``os.WriteFile``, so this asserts the mode under the
    umask the test process actually has.
    """
    _write(_workspace(tmp_path), path="sub/out.txt", content="x")

    umask = os.umask(0o022)
    os.umask(umask)
    assert (tmp_path / "sub" / "out.txt").stat().st_mode & 0o777 == (
        FILE_MODE & ~umask
    )
    assert (tmp_path / "sub").stat().st_mode & 0o777 == (
        DIRECTORY_MODE & ~umask
    )


def test_the_byte_count_is_bytes_and_not_characters(tmp_path):
    """harness9 reports ``len(input.Content)``, which in Go is bytes.

    ``len`` on a Python :class:`str` is characters, so translating the
    expression rather than the meaning would under-report every file
    containing a gene name in Chinese, an accented author, or an emoji in
    a comment. Pinned with a string whose two counts differ.
    """
    message = _write(_workspace(tmp_path), path="u.txt", content="héllo")

    assert "6 bytes" in message
    assert (tmp_path / "u.txt").stat().st_size == 6


def test_empty_content_writes_an_empty_file_rather_than_refusing(tmp_path):
    _write(_workspace(tmp_path), path="empty.txt", content="")

    assert (tmp_path / "empty.txt").read_text() == ""


def test_what_write_produces_is_what_read_gives_back(tmp_path):
    """The two tools have to agree, since a model will pair them."""
    workspace = _workspace(tmp_path)
    _write(workspace, path="round.txt", content="one\ntwo\n")

    output = _run(read_tool(workspace).execute(_args(path="round.txt")))

    assert output == "one\ntwo\n"


# ---- plan 0029 trap 12: overwriting ---------------------------------------


def test_an_existing_file_is_replaced_whole_and_the_answer_says_so(tmp_path):
    """Plan 0029 trap 12 / ``write_file.go:8-9``.

    ``os.WriteFile`` semantics: not an append, not a merge, and the old
    contents are gone. The returned sentence distinguishes the two cases
    because a model that has just destroyed four kilobytes of someone's
    analysis should be told.
    """
    (tmp_path / "out.txt").write_text("a very long previous version\n")

    message = _write(_workspace(tmp_path), path="out.txt", content="new\n")

    assert (tmp_path / "out.txt").read_text() == "new\n"
    assert message.startswith("Replaced")


def test_the_description_tells_the_model_it_will_destroy_what_is_there(
    tmp_path,
):
    """Plan 0029 trap 12's other half: the model has to be told in advance,
    because deciding whether to read the file first is its job."""
    description = WriteTool().definition().description.lower()

    assert "replace" in description
    assert "no append" in description
    assert "whole" in description


def test_the_approval_reason_names_the_resolved_path_and_the_size_at_risk(
    tmp_path,
):
    """What turns a routine write into a decision a human can make.

    The **resolved** path, not the model's string: a person approving a
    write to ``data/../out.txt`` needs to see where it lands. And the size
    of what is there, because "write a file" and "destroy 4,000 bytes" are
    different requests wearing one tool name.
    """
    (tmp_path / "out.txt").write_text("x" * 4000)
    seen: list[ApprovalRequest] = []

    _write(
        _workspace(tmp_path),
        approve=_yes(seen),
        path="./out.txt",
        content="tiny",
    )

    assert "REPLACE" in seen[0].reason
    assert str((tmp_path / "out.txt").resolve()) in seen[0].reason
    assert "4000 bytes" in seen[0].reason
    assert "not recoverable" in seen[0].reason


def test_the_approval_reason_says_create_when_there_is_nothing_there(
    tmp_path,
):
    """The positive twin: a first write must not read as a destruction."""
    seen: list[ApprovalRequest] = []

    _write(
        _workspace(tmp_path), approve=_yes(seen), path="new.txt", content="x"
    )

    assert seen[0].reason.startswith("create ")
    assert "REPLACE" not in seen[0].reason


# ---- approval: the bytes, the order, and the absence of a channel --------


def test_the_approval_prompt_carries_the_exact_bytes_the_model_sent(tmp_path):
    """Why this tool is hand-written rather than a
    :class:`~omicsclaw.tools.function_tool.FunctionTool` (plan 0029 §5).

    The payload below has its keys in an order no schema mentions and
    whitespace a re-encode would normalise. A prompt built from decoded
    arguments would show a *reconstruction*, and a reconstruction is the
    one thing an approval prompt must not be.
    """
    raw = '{"content":  "x",\n "path": "out.txt"}'
    seen: list[ApprovalRequest] = []
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_yes(seen)):
        _run(tool.execute(raw))

    assert seen[0].arguments == raw
    assert seen[0].tool_name == TOOL_NAME


def test_the_human_is_asked_before_anything_exists_on_disk(tmp_path):
    """Order of operations, asserted from inside the prompt itself.

    The channel looks at the workspace at the moment it is consulted. An
    implementation that created the parent directory first — the natural
    way to write this if ``mkdir`` moves up beside the resolution — would
    be seen here.
    """
    observed: list[list[Path]] = []

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        observed.append(sorted(tmp_path.rglob("*")))
        return ApprovalDecision(approved=True)

    tool = WriteTool(_workspace(tmp_path))
    with use_tool_context(approval=channel):
        _run(tool.execute(_args(path="a/b/out.txt", content="x")))

    assert observed == [[]]
    assert (tmp_path / "a" / "b" / "out.txt").exists()


def test_nothing_is_written_when_no_approval_channel_is_bound(tmp_path):
    """Plan 0029 Q2's accepted cost, and the correct behaviour of a
    fail-closed gate: an absent channel is never read as consent."""
    tool = WriteTool(_workspace(tmp_path))

    with pytest.raises(ApprovalUnavailable):
        _run(tool.execute(_args(path="out.txt", content="x")))

    assert list(tmp_path.rglob("*")) == []


def test_nothing_is_written_when_the_human_says_no(tmp_path):
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_no("that path is the input data")):
        with pytest.raises(ApprovalDenied) as caught:
            _run(tool.execute(_args(path="out.txt", content="x")))

    assert "that path is the input data" in str(caught.value)
    assert list(tmp_path.rglob("*")) == []


def test_a_refusal_before_the_write_leaves_an_existing_file_untouched(
    tmp_path,
):
    """The destructive half of the same rule: a denied overwrite must not
    have truncated the file on its way to asking."""
    (tmp_path / "out.txt").write_text("precious\n")
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_no()):
        with pytest.raises(ApprovalDenied):
            _run(tool.execute(_args(path="out.txt", content="x")))

    assert (tmp_path / "out.txt").read_text() == "precious\n"


def test_progress_is_reported_but_a_missing_audience_is_not_a_failure(
    tmp_path,
):
    """A sink is bound here and absent everywhere else in this file, which
    is what shows that reporting is optional rather than load-bearing."""
    updates: list[ProgressUpdate] = []
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_yes(), progress=updates.append):
        _run(tool.execute(_args(path="out.txt", content="hello")))

    assert updates and updates[0].tool_name == TOOL_NAME
    assert "5 bytes" in updates[0].message


# ---- plan 0029 trap 3: the symlinked parent ------------------------------


def test_writing_through_a_symlink_creates_nothing_outside_the_workspace(
    tmp_path,
):
    """**Plan 0029 trap 3, and the assertion is the point.**

    ``Workspace.resolve`` follows symlinks, so ``escape/out.txt`` resolves
    to ``/…-outside/out.txt`` and is refused. But the helper cannot force
    this module to call it *before* ``mkdir(parents=True)``, and an
    implementation that joined the path itself and created directories
    first would already have written into the external directory by the
    time anything was checked.

    So this asserts the external directory is **still empty**, not merely
    that an exception was raised. Swap the resolution in
    ``WriteTool.execute`` for a plain ``workspace.root / target`` and this
    is the test that goes red.
    """
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    os.symlink(outside, tmp_path / "escape")
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_yes()):
        with pytest.raises(PathEscapesWorkspace):
            _run(tool.execute(_args(path="escape/out.txt", content="x")))

    assert list(outside.rglob("*")) == []
    assert not (outside / "out.txt").exists()


def test_writing_into_a_real_subdirectory_of_the_workspace_still_works(
    tmp_path,
):
    """The positive twin of trap 3. Without it, "refuse every path with a
    directory in it" would pass the test above."""
    (tmp_path / "real").mkdir()

    _write(_workspace(tmp_path), path="real/out.txt", content="fine\n")

    assert (tmp_path / "real" / "out.txt").read_text() == "fine\n"


def test_a_symlinked_file_inside_the_workspace_is_writable(tmp_path):
    """Following links must not become refusing them: a link pointing back
    inside the workspace resolves inside it and is allowed."""
    (tmp_path / "real.txt").write_text("old\n")
    os.symlink(tmp_path / "real.txt", tmp_path / "alias.txt")

    _write(_workspace(tmp_path), path="alias.txt", content="new\n")

    assert (tmp_path / "real.txt").read_text() == "new\n"


# ---- the rest of the boundary, each beside a legitimate write -----------


def test_an_escaping_relative_path_writes_nothing(tmp_path):
    tool = WriteTool(_workspace(tmp_path))
    before = sorted(tmp_path.parent.iterdir())

    with use_tool_context(approval=_yes()):
        with pytest.raises(PathEscapesWorkspace):
            _run(tool.execute(_args(path="../escaped.txt", content="x")))

    assert sorted(tmp_path.parent.iterdir()) == before


def test_an_absolute_path_inside_the_workspace_writes_and_one_outside_does_not(
    tmp_path,
):
    """Plan 0029 trap 2 as it reaches a tool: no doubling branch, only the
    behaviour, and both directions checked."""
    workspace = _workspace(tmp_path)

    _write(workspace, path=str(tmp_path / "ok.txt"), content="fine\n")
    assert (tmp_path / "ok.txt").read_text() == "fine\n"

    tool = WriteTool(workspace)
    with use_tool_context(approval=_yes()):
        with pytest.raises(PathEscapesWorkspace):
            _run(tool.execute(_args(path="/tmp/omicsclaw-escape", content="x")))

    assert not Path("/tmp/omicsclaw-escape").exists()


def test_a_dotenv_cannot_be_overwritten_but_a_similar_name_can(tmp_path):
    """Credentials are refused wherever they sit — including inside the
    workspace — while a file that merely starts with ``.env`` is not."""
    (tmp_path / ".env").write_text("LLM_API_KEY=sk-real\n")
    workspace = _workspace(tmp_path)

    _write(workspace, path=".envelope-design.md", content="notes\n")
    assert (tmp_path / ".envelope-design.md").read_text() == "notes\n"

    tool = WriteTool(workspace)
    with use_tool_context(approval=_yes()):
        with pytest.raises(PathIsSensitive):
            _run(tool.execute(_args(path=".env", content="LLM_API_KEY=x")))

    assert (tmp_path / ".env").read_text() == "LLM_API_KEY=sk-real\n"


# ---- plan 0029 trap 7: failures the model can act on --------------------


def test_writing_over_a_directory_is_an_error_the_model_can_correct(tmp_path):
    (tmp_path / "sub").mkdir()
    registry = ToolRegistry([WriteTool(_workspace(tmp_path))])

    with use_tool_context(approval=_yes()):
        result = _run(
            registry.execute(
                ToolCall(
                    id="c1",
                    name=TOOL_NAME,
                    arguments=_args(path="sub", content="x"),
                )
            )
        )

    assert result.is_error is True
    assert "cannot write 'sub'" in result.output
    assert "Is a directory" in result.output


def test_a_name_too_long_for_the_filesystem_reads_as_a_correctable_sentence(
    tmp_path,
):
    """The gap the helper layer leaves open, closed here.

    ``Workspace.resolve`` accepts a 5,000-character name because
    :meth:`~pathlib.Path.resolve` never touches the filesystem, so the
    refusal arrives at the write as ``ENAMETOOLONG``. A bare
    :exc:`OSError` reads to a model as a machine fault; the sentence below
    names the argument to change.
    """
    registry = ToolRegistry([WriteTool(_workspace(tmp_path))])

    with use_tool_context(approval=_yes()):
        result = _run(
            registry.execute(
                ToolCall(
                    id="c1",
                    name=TOOL_NAME,
                    arguments=_args(path="a" * 5000, content="x"),
                )
            )
        )

    assert result.is_error is True
    assert "File name too long" in result.output
    assert "Send a different path inside the workspace" in result.output
    assert "Traceback" not in result.output


def test_a_truncated_payload_is_reported_with_where_it_stopped(tmp_path):
    """``decode_arguments`` is shared rather than re-written (plan 0028
    trap 8); this is the behaviour that sharing buys."""
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_yes()):
        with pytest.raises(ToolArgumentError) as caught:
            _run(tool.execute('{"path": "out.txt", "content": "half'))

    assert "characters starting" in str(caught.value)
    assert list(tmp_path.rglob("*")) == []


def test_a_missing_content_field_is_named_rather_than_defaulted(tmp_path):
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_yes()):
        with pytest.raises(ToolArgumentError) as caught:
            _run(tool.execute(_args(path="out.txt")))

    assert "input.content is required" in str(caught.value)
    assert list(tmp_path.rglob("*")) == []


def test_an_unknown_argument_is_a_schema_complaint_not_a_type_error(tmp_path):
    """``additionalProperties: false`` earns its keep: the model is told
    which key was wrong instead of the tool raising from its own body."""
    tool = WriteTool(_workspace(tmp_path))

    with use_tool_context(approval=_yes()):
        with pytest.raises(ToolArgumentError) as caught:
            _run(
                tool.execute(
                    _args(path="out.txt", content="x", create_dirs=True)
                )
            )

    assert "input.create_dirs is not allowed" in str(caught.value)


# ---- policy --------------------------------------------------------------


def test_the_policy_is_declared_and_says_more_than_the_default_would(
    tmp_path,
):
    """Plan 0029 Q2.

    ``HIGH`` + ``ASK`` happen to be ``ToolPolicy()``'s own defaults, so
    checking only those two would pass under a tool that declared nothing
    — which is precisely the state plan 0028's ``ToolPolicy`` docstring
    says must remain distinguishable. ``writes_workspace`` and the tags
    are the fields only a deliberate declaration sets.
    """
    policy = WriteTool().policy

    assert policy.approval_mode is ApprovalMode.ASK
    assert policy.risk_level is RiskLevel.HIGH
    assert policy.writes_workspace is True
    assert policy.read_only is False
    assert policy.concurrency_safe is False
    assert policy.allowed_in_background is False
    assert policy != ToolPolicy()


def test_a_deployment_can_relax_it_through_the_registry(tmp_path):
    """Plan 0029 Q2's "explicit action": running unattended is possible and
    somebody has to ask for it, at ``register``, where an operator looks.

    This is also what makes the absence of a ``policy=`` constructor
    argument a decision rather than an omission — the override exists and
    it is the one ``require_approval`` actually reads.
    """
    registry = ToolRegistry()
    registry.register(
        WriteTool(_workspace(tmp_path)),
        policy=ToolPolicy(
            approval_mode=ApprovalMode.AUTO, risk_level=RiskLevel.LOW
        ),
    )

    result = _run(
        registry.execute(
            ToolCall(
                id="c1",
                name=TOOL_NAME,
                arguments=_args(path="out.txt", content="x"),
            )
        )
    )

    assert result.is_error is False
    assert (tmp_path / "out.txt").read_text() == "x"


def test_it_is_a_tool_and_agrees_with_itself_about_its_name(tmp_path):
    tool = WriteTool(_workspace(tmp_path))

    assert isinstance(tool, Tool)
    assert tool.name == tool.definition().name == TOOL_NAME
    assert WriteTool is WriteToolDirect


def test_two_instances_do_not_share_one_schema_mapping(tmp_path):
    """A deep copy per instance, so one registry's edit is not another's."""
    first = WriteTool().definition().input_schema
    second = WriteTool().definition().input_schema

    first["properties"]["path"]["description"] = "changed"

    assert second["properties"]["path"]["description"] != "changed"


# ---- where the workspace comes from --------------------------------------


def test_a_workspace_bound_to_the_session_is_used_when_none_was_given(
    tmp_path,
):
    """Shared with ``read`` through one helper, so the two cannot drift."""
    tool = WriteTool()

    with use_tool_context(approval=_yes(), values={"workspace": str(tmp_path)}):
        _run(tool.execute(_args(path="out.txt", content="bound\n")))

    assert (tmp_path / "out.txt").read_text() == "bound\n"


def test_no_workspace_anywhere_is_not_reported_as_the_models_mistake(
    tmp_path,
):
    tool = WriteTool()

    with use_tool_context(approval=_yes()):
        with pytest.raises(RuntimeError) as caught:
            _run(tool.execute(_args(path="out.txt", content="x")))

    assert not isinstance(caught.value, ToolArgumentError)
    assert "workspace" in str(caught.value)


# ---- the write lock ------------------------------------------------------


class _SuspendingEnvironment:
    """A write that yields to the event loop halfway through.

    Which is what makes the lock observable at all. The local write path
    has no ``await`` between ``mkdir`` and the last byte, so a coroutine
    cannot be preempted inside it and two local writes cannot interleave
    whatever the lock does — a test built on the local path would be
    green under no lock at all. A routed write genuinely suspends, so
    this is where the exclusion has to be demonstrated.
    """

    def __init__(self) -> None:
        self.log: list[tuple[str, str]] = []

    async def read_file(self, path: str) -> bytes:
        return b""

    async def write_file(self, path: str, data: bytes) -> None:
        tag = data.decode()[:1]
        self.log.append(("start", tag))
        for _ in range(5):
            await asyncio.sleep(0)
        self.log.append(("end", tag))


def test_two_writes_to_one_path_in_one_turn_do_not_interleave(tmp_path):
    """Plan 0029 Q7: the race is real today, and this is its only defence.

    ``engine/executor.py`` starts every call in a turn with
    :func:`asyncio.ensure_future` and ``max_concurrent_tools`` defaults to
    ``0``, meaning no limit, so two ``write`` calls to one path really do
    run together. The layer being replaced had a serial barrier; this one
    has the path lock and nothing else.

    The two calls name the same file through **different strings**, so a
    lock keyed on the model's argument rather than on the resolved path
    would take two locks — held, paid for, and protecting nothing. One is
    relative and one absolute on purpose: a relative string resolves
    against the *process* working directory, so the pair only collapses to
    one key once the workspace has joined it. A pair of relative aliases
    (``out.txt`` and ``./sub/../out.txt``) collapses either way, and a
    mutation test proved that version of this test green under a lock
    keyed on the raw argument.
    """
    environment = _SuspendingEnvironment()
    tool = WriteTool(_workspace(tmp_path), environment=environment)

    async def main() -> None:
        with use_tool_context(approval=_yes()):
            await asyncio.gather(
                tool.execute(_args(path="out.txt", content="a" * 10)),
                tool.execute(
                    _args(path=str(tmp_path / "out.txt"), content="b" * 10)
                ),
            )

    _run(main())

    assert [phase for phase, _ in environment.log] == [
        "start",
        "end",
        "start",
        "end",
    ], f"the two writes interleaved: {environment.log}"
    assert PATH_LOCKS.tracked_paths() == frozenset()


# ---- the environment seam (plan 0029 Q11) -------------------------------


class _RecordingEnvironment:
    """The same fake ``test_read.py`` uses, satisfying both Protocols."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, bytes]] = []

    async def read_file(self, path: str) -> bytes:
        return b""

    async def write_file(self, path: str, data: bytes) -> None:
        self.writes.append((path, data))


def test_an_injected_environment_takes_the_write_instead_of_the_disk(
    tmp_path,
):
    """Plan 0029 Q11, at the width the decision is about.

    Isolation that covered ``bash`` and not ``write`` would be decoration
    a model steps around by choosing the other tool, so ``write`` takes an
    environment too — and *uses* it, since a stored-and-never-read field
    is the dead code plan 0029 trap 15 forbids. The local file must not
    appear.
    """
    environment = _RecordingEnvironment()
    tool = WriteTool(_workspace(tmp_path), environment=environment)

    with use_tool_context(approval=_yes()):
        message = _run(tool.execute(_args(path="out.txt", content="héllo")))

    assert environment.writes == [
        (str(tmp_path / "out.txt"), "héllo".encode("utf-8"))
    ]
    assert not (tmp_path / "out.txt").exists()
    assert "6 bytes" in message


def test_an_environment_still_answers_to_the_workspace_boundary(tmp_path):
    environment = _RecordingEnvironment()
    tool = WriteTool(_workspace(tmp_path), environment=environment)

    with use_tool_context(approval=_yes()):
        with pytest.raises(PathEscapesWorkspace):
            _run(tool.execute(_args(path="/tmp/nope.txt", content="x")))

    assert environment.writes == []


# ---- plan 0029 trap 5: cancellation is not an Observation ---------------


class _CancellingEnvironment:
    async def write_file(self, path: str, data: bytes) -> None:
        raise asyncio.CancelledError


def test_a_cancelled_write_stays_cancelled_and_is_not_turned_into_an_error(
    tmp_path,
):
    """Plan 0029 trap 5, aimed at ``_put``'s ``except OSError``.

    Widening it to ``except BaseException`` would catch the engine's
    per-tool deadline and report it to the model as "cannot write that
    path", sending it to fix a path that is fine. That is the mutation
    this test exists for.
    """
    tool = WriteTool(_workspace(tmp_path), environment=_CancellingEnvironment())

    async def main() -> str:
        with use_tool_context(approval=_yes()):
            try:
                await tool.execute(_args(path="out.txt", content="x"))
            except asyncio.CancelledError:
                return "cancelled"
        return "swallowed"

    assert asyncio.run(main()) == "cancelled"
    assert list(tmp_path.rglob("*")) == []


def test_a_turn_cancelled_while_a_human_is_deciding_writes_nothing(tmp_path):
    """The realistic shape of the same trap.

    ``omicsclaw/tools/context.py`` documents it in full: an approval wait
    is spent inside the engine's per-tool budget, so a human who thinks
    for longer than ``tool_timeout`` has the whole tool cancelled. What
    must not happen is a partial write, or a cancellation arriving at the
    model as a tool failure.
    """

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        raise asyncio.CancelledError

    tool = WriteTool(_workspace(tmp_path))

    async def main() -> str:
        with use_tool_context(approval=channel):
            try:
                await tool.execute(_args(path="out.txt", content="x"))
            except asyncio.CancelledError:
                return "cancelled"
        return "swallowed"

    assert asyncio.run(main()) == "cancelled"
    assert list(tmp_path.rglob("*")) == []
