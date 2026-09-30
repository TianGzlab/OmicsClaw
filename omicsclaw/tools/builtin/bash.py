"""``bash`` — the tool whose only boundary is the human being asked.

Plan 0029 §4 Q2/Q3/Q4/Q5/Q6/Q11 and traps 5, 6, 7, 13, 14, 15 and 16. The
reference is harness9's ``internal/tools/bash.go``, and of the three
foundation tools this is the one where the *reference* is worth more than
the design: four of its 239 lines carry measured numbers from failures
somebody else had, and each of those four is reproduced below with the
measurement re-taken under Python.

**This tool has no path argument, and therefore no path attack surface.**
``bash.go:88-107`` takes ``command`` and ``timeout_secs`` and nothing
else, and its ``Execute`` never calls ``safePath``. Neither does this one.
That is not an oversight in either: ``cd ../.. && cat /etc/passwd`` is not
a boundary being evaded, it is a boundary that was never claimed, and a
path check bolted onto the one argument that is a whole programming
language would be security theatre a model steps around by spelling the
path differently. What bounds this tool is the approval gate of Q2 and,
one day, the injection seam of Q11 — written here because plan 0029 §10-9
originally aimed its adversarial path-boundary criterion at this file, and
an implementer reading that would either skip the criterion silently or
invent a check no plan designed.

**Q6 — a non-zero exit is not a tool failure.** This is the tool that
makes plan 0028's "world failure versus tool failure" distinction earn its
keep. ``pytest`` reporting three failures is a fact about the world; the
tool did exactly what it was asked. ``bash.go:145-147, 190-191`` returns
that text with ``err == nil``, so it arrives as an ordinary Observation,
and the reason is what the model does next: told ``is_error=True`` it goes
looking for a broken tool, told the exit status it goes looking for the
broken test. The criterion in full, and it is the same one
``builtin/read.py`` states for its own half: **what should the model
change next?** A non-zero exit gives it nothing to change about the call,
so it is not an error; a payload that will not decode, a command that is
the empty string, a ``timeout_secs`` of zero — each is fixed by sending
different arguments, so each is raised and the registry marks it. The two
live adjacently in ``tests/tools/test_bash.py``; the ``read`` half of the
pair is in ``tests/tools/test_read.py``, because the two tools shipped in
different tasks and neither may edit the other's test file.

**One deliberate departure from the reference, on that same criterion.**
``bash.go:119-121`` answers an empty command with the *string*
``"Error: 命令为空字符串"`` and ``err == nil`` — a failure delivered as a
success whose text happens to begin with "Error". That shape is precisely
the legacy defect this layer exists to end:
``runtime/tools/builders/engineering.py`` returns ``"Error: file not found
or outside allowed roots: …"`` as a tool *result*, so the run never sees
``is_error``, and both ``builtin/read.py`` and ``builtin/write.py``
document rejecting it. An empty command is also squarely on the
correctable side of the criterion above. So the reference's *detection* is
kept and its *reporting* is not: :exc:`ToolArgumentError`, which the
registry turns into ``is_error=True``.

**Q5 / trap 13 — the subprocess writes to a temporary file, never to a
pipe.** ``bash.go:153-165`` is the most valuable comment in the reference.
``CombinedOutput()`` collects output through a pipe, and ``Wait()`` waits
for every holder of the write end to close it; a command like ``A && B &``
leaves a backgrounded grandchild holding that end, so the call blocks
until something else kills it. Measured there: **20 s of hanging became
~5 ms, with the background process still running**, once output went to a
file instead.

That is a property of pipes and process inheritance, not of Go, and it
reproduces here exactly. Measured on this machine, Python 3.13, with
``bash -c 'echo hi && sleep 30 &'``:

* ``create_subprocess_exec(..., stdout=PIPE)`` + ``communicate()`` — still
  blocked when a 6 s test deadline gave up.
* the same command with ``stdout=<temp file>`` — returned in **0.003 s**,
  exit status 0, ``hi\\n`` captured.

``tests/tools/test_bash.py`` pins the second measurement, because a
"simplification" back to ``PIPE`` would leave every other test in this
file green.

The cost is inherited along with the fix and is stated to the model in
:func:`_description`: the temporary file is deleted when this call
returns, so anything the command backgrounds should redirect its own
output (``nohup cmd > out.log 2>&1 &``) rather than inherit this one.

**Trap 16 — a process killed by a signal did not succeed.** This one is
not from harness9. It is an archived bug in ``earendil-works/pi``, whose
bash tool tested ``exitCode !== 0 && exitCode !== null`` — and a
signal-terminated process reports ``null``, so everything ``SIGKILL`` or
``SIGTERM`` stopped sailed past the failure branch and was returned as a
success with whatever partial output it had managed. Translating that
predicate literally would be wrong here too, for a different reason:
:mod:`asyncio.subprocess` reports a signal as a **negative**
``returncode`` (measured: ``kill -9 $$`` → ``-9``, ``kill -TERM $$`` →
``-15``), and ``-9 != 0`` is true but ``-9`` is not a status any shell
ever prints. :func:`_exit_status` normalises to the shell's own
``128 + signum``, so a ``SIGKILL`` reads as ``137``, which is both non-zero
and recognisable. The normalisation is applied to an injected
environment's answer as well, because an environment built the obvious way
— on :mod:`asyncio.subprocess` — would hand back the negative form and
carry pi's bug across the seam.

**Q4 / trap 6 — the budget is 45 seconds because the engine's is 60.**
``bash.go:29-32`` uses 120 s with a 600 s ceiling the model may negotiate
up to. Copying either number would make this module's timeout handling
*unreachable*: ``EngineConfig.tool_timeout`` defaults to **60 s** and
wraps the whole of ``executor.execute(call)``
(``omicsclaw/engine/executor.py::_execute``), so at 120 s the engine
cancels first and the model is told ``tool 'bash' timed out after 60s``
instead of reading the banner below. :data:`DEFAULT_TIMEOUT` is therefore
45 s, leaving the :data:`ENGINE_TIMEOUT_MARGIN` of 15 s, and
:attr:`BashTool.max_timeout` equals the configured timeout rather than
being a second number — the model may ask for **less** and never for more.

That last part is a simplification of the plan, which specifies a ceiling
that happens to equal the default. Two constants whose equality is the
invariant are two constants that can drift apart in one edit; one
attribute derived from the other cannot. What the plan wanted the ceiling
for is unchanged: ``timeout_secs`` stays in the schema because a short
probe is genuinely useful, and if the engine's budget ever becomes
configurable, the ceiling follows the operator's ``timeout`` without a
second edit.

**This module may not import** :class:`~omicsclaw.engine.config.EngineConfig`
**to check any of that** — the layering rule forbids it — so the coupling
is implicit and is held by a test instead: ``tests/tools/test_bash.py``
imports both and asserts the arithmetic with no override on either side.
A test directory is not under the layering guard, which only walks
``omicsclaw/tools/``.

**Q3 / trap 14 — truncation keeps the tail.** 16,000 with a head of one
third and a tail of two thirds (``bash.go:23, 205-222``), and the reason
is in its comment: a test runner prints verbose progress first and the
``FAILED`` lines, the traceback and the ``=== N failed ===`` summary
**last**, and the implementation that kept only the head cut off exactly
the part that was worth reading. See :data:`HEAD_CHARS`.

**Trap 15 — what was deliberately not translated.**
``trimToValidUTF8Suffix`` / ``trimToValidUTF8Prefix``
(``bash.go:224-238``) trim a partial rune off a slice boundary. A Go
``string`` is a byte sequence and slicing one really can split a
multi-byte character; a Python :class:`str` is a sequence of code points
and ``s[:n]`` **cannot**. Translated, those loops would be two functions
whose condition is never true — unreachable code wearing a safety
measure's clothes. They are absent, and the boundary problem is absent
with them, because the bytes are decoded **once** with
``errors="replace"`` before anything is measured or sliced. That is also
what settles the open question plan 0029 Q3 leaves to this task, of
whether 16,000 counts characters or bytes: slicing bytes would put the
split-character problem back and then demand the trimming loops to undo
it, while :class:`str` makes the whole class of defect unspellable. See
:data:`MAX_OUTPUT_CHARS`.

**Trap 5 — cancellation passes through.** No ``except Exception`` and no
``except BaseException`` anywhere below. The engine's per-tool deadline
arrives as :exc:`asyncio.CancelledError`, and reported to the model as a
tool failure it would send the model to fix a command that was fine. It
is *named* only where a subprocess would otherwise be orphaned by the
abandoned turn, while the shell runs and while it is still being started:
the command's process group is killed, the shell is reaped, and the
exception is re-raised untouched, which is passing it through rather than
handling it.

**Q11 — the injection seam, and it is live.** ``environment=None`` means
this machine. Anything else has :meth:`BashEnvironment.run_bash` awaited
instead of a local process being started, and
``tests/tools/test_bash.py`` drives a fake through it. harness9 holds an
environment on its file tools and never reads it (``read_file.go:35-37``
is a TODO), which is the dead state trap 15 asks an assessor to report.
harness9's own ``LocalEnvironment`` is deliberately **not** reproduced:
its ``RunBash`` calls ``CombinedOutput()`` (``local_environment.go:28``),
which is the pipe bug the paragraph on Q5 above exists to avoid, and it is
harmless there only because nothing in production calls it.

**No OS isolation ships with this.** Until something implements
:class:`BashEnvironment`, the only thing between a model's command and
this machine is the approval channel — which is why :data:`_POLICY` is
``ASK``, and why plan 0029 §12 carries the isolation step forward as its
own piece of work.

**Two residuals, stated rather than hidden.**

*The whole output is read into memory before it is truncated.* A command
that emits gigabytes is a memory event no 16,000-character ceiling
prevents; the reference has the identical hole (``bash.go:180``). Closing
it means reading bounded windows from each end of the file, which forces
the elision count into bytes while everything else here counts characters
— a reconciliation worth designing once, not improvising here.

*A process can leave the group it is killed through.* The shell runs in a
session of its own, and a deadline or a cancellation kills that whole
process group, so a pipeline, a backgrounded job or a script the shell is
waiting on goes with it. A process that moves itself out of the group,
with ``setsid`` or as a job started after ``set -m``, is not reached. A
command that finishes in time is not killed at all, so what it
backgrounded keeps running.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools._workspace``,
``omicsclaw.tools.base``, ``omicsclaw.tools.context``,
``omicsclaw.tools.function_tool``, ``omicsclaw.tools.builtin.read``, and
the standard library.
"""

from __future__ import annotations

import asyncio
import copy
import os
import signal
import tempfile
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from omicsclaw.schema import ToolDefinition

from .._workspace import Workspace
from ..base import ApprovalMode, RiskLevel, ToolPolicy
from ..context import report_progress, require_approval
from ..function_tool import ToolArgumentError, decode_arguments, validate_arguments
from .read import resolve_workspace

CONTROL_CREDENTIAL_NAMES: frozenset[str] = frozenset({"OMICSCLAW_REMOTE_AUTH_TOKEN"})
"""Framework control-plane credentials no child process started here may inherit.

Stored upper-case; :func:`without_control_credentials` compares names
case-insensitively.
"""


def without_control_credentials(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of *source* without the names in :data:`CONTROL_CREDENTIAL_NAMES`.

    :param source: The environment to copy; defaults to ``os.environ`` as it is now.
    :returns: A new dict; names are matched case-insensitively.
    """
    source = os.environ if source is None else source
    return {
        name: value for name, value in source.items()
        if name.upper() not in CONTROL_CREDENTIAL_NAMES
    }


TOOL_NAME = "bash"
"""Name the model calls this tool by.

File search has no dedicated tool: globbing and content search go through
this one (``find``, ``grep``, ``rg``).
"""

MAX_OUTPUT_CHARS = 16_000
"""Ceiling on returned output, from ``bash.go:23``.

**A literal carried over, and re-decided as to its unit.** The reference
counts bytes because a Go ``string`` is bytes. Here it counts
**characters**, and that is not a convenience: the bytes are decoded once,
with ``errors="replace"``, before anything measures or slices them, which
makes it impossible to cut a character in half — and therefore makes the
two rune-trimming helpers at ``bash.go:224-238`` unnecessary rather than
merely untranslated (plan 0029 trap 15). Characters are also the closer
proxy for what the ceiling is actually rationing, which is context.

The number itself needed no re-derivation: it is a budget for a model's
context window, and 16,000 characters is roughly 4,000 tokens whichever
language measured it. What a deployment on non-Latin output should know is
that the ceiling is now more generous than the reference's in bytes and
identical in what it costs the model, which is the side that matters.
"""

HEAD_CHARS = MAX_OUTPUT_CHARS // 3
"""Characters kept from the start of an over-long output. ``bash.go:216``.

**The ratio is the borrowed part, and it is a behaviour rather than a
taste.** ``bash.go:205-210`` records why two thirds go to the tail: a test
runner prints its progress first and its verdict last — the ``FAILED``
lines, the traceback, the ``=== N failed ===`` summary — and the
implementation it replaced kept only the head, which cut off precisely the
diagnosis. Nothing about that is Go-specific; ``pytest -q`` has the same
shape, and so does ``pip install``.

Integer division, as in the reference, so the two add up to
:data:`MAX_OUTPUT_CHARS` exactly with no rounding left over:
5,333 + 10,667.
"""

TAIL_CHARS = MAX_OUTPUT_CHARS - HEAD_CHARS
"""Characters kept from the end. The two-thirds share. See :data:`HEAD_CHARS`."""

DEFAULT_TIMEOUT = 45.0
"""Seconds one command may run. **Derived here, not copied.**

``bash.go:29`` uses 120 s, and copying it would make everything this
module does about timeouts dead code:
:attr:`~omicsclaw.engine.config.EngineConfig.tool_timeout` defaults to
**60 s** and wraps the whole tool call, so a 120 s command is cancelled by
the engine at 60 s and the model reads ``tool 'bash' timed out after 60s``
— an engine sentence, not :func:`_timeout_banner`'s.

45 s is 60 s minus :data:`ENGINE_TIMEOUT_MARGIN`. **It is one half of a
coupling this layer cannot see**, since ``omicsclaw/tools/`` may not
import the engine: change ``EngineConfig.tool_timeout`` and this number
has to move with it. ``tests/tools/test_bash.py`` imports both and asserts
the arithmetic, which is the only thing holding the two together.
"""

ENGINE_TIMEOUT_MARGIN = 15.0
"""Seconds left between this tool's budget and the engine's.

The mechanical part is cheap: noticing the deadline, killing the process,
reading the capture back and formatting a banner is milliseconds of work.

**The expensive part is the human, and that is a consequence plan 0029
does not state.** ``require_approval`` is awaited inside ``execute``,
which is inside the engine's per-call budget (``omicsclaw/tools/
context.py`` documents the collision at length, and plan 0028 calls it
R3). So the arithmetic that actually governs is

    time the human spends deciding  +  the command's own run  <=  60s

and this tool only controls the second term. **An approval that takes
longer than this margin defeats the whole of Q4**: the engine cancels
first and the model reads ``tool 'bash' timed out after 60s`` even though
the command was inside its 45 s. Fifteen seconds is not a generous
allowance for a person reading a shell command they are being asked to
consent to.

Nothing here can fix that — the fix is in the engine, where an approval
wait belongs on a session deadline rather than the per-call one — so what
is done is to say it: **this tool's timeout behaviour is guaranteed only
for approvals returned inside this margin**, and a surface whose
approvals are human-paced has to raise ``EngineConfig.tool_timeout``
rather than assume fifteen seconds covers a person.
"""


def _exit_status(returncode: int) -> int:
    """A process's status the way a shell would print it (trap 16).

    :mod:`asyncio.subprocess` reports a signal as a **negative** return
    code — measured on this machine, ``kill -9 $$`` gives ``-9`` and
    ``kill -TERM $$`` gives ``-15``. Both are non-zero, so a simple
    ``!= 0`` test does catch them, but ``-9`` is not a status any shell
    prints and a model asked to reason about it has nothing to match it
    against. ``128 + signum`` is the convention every shell uses, so
    ``SIGKILL`` becomes ``137`` and ``SIGTERM`` becomes ``143``.

    The archived bug this defends against is ``pi``'s, which tested
    ``exitCode !== 0 && exitCode !== null`` and so returned everything a
    signal had killed as a **success** carrying half its output. Python
    never produces that ``null``, so the shape of the bug is different
    here; the defence is the same, which is to have exactly one place that
    decides what "this command failed" means.

    Idempotent for anything non-negative, which is why it is also applied
    to an injected environment's answer: an environment built the obvious
    way, on :mod:`asyncio.subprocess`, would hand back the negative form.
    """
    if returncode < 0:
        return 128 - returncode
    return returncode


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """What running a command produced: its text, and how it ended.

    Two fields because the exit status cannot be recovered from the text.
    harness9's ``sandbox.Environment.RunBash`` returns ``(string, error)``
    and loses it — its Docker implementation folds a non-zero
    ``docker exec`` into an error string — which means a routed command
    cannot distinguish "the test suite failed" from "the container is
    gone". Carrying the status across the seam is what lets
    :func:`_exit_status` apply on both sides of it.
    """

    output: str
    """stdout and stderr merged, in the order they were written."""

    exit_code: int
    """Shell convention: ``0`` for success, ``128 + signum`` for a signal."""


_KILLED_BY_DEADLINE = CommandOutcome(output="", exit_code=_exit_status(-9))
"""What an environment that overran its own budget is recorded as producing.

The status is never rendered — :func:`_timed_out` reports the banner and
no exit line — but a field that has to hold something should hold the true
thing, and ``137`` is exactly what the local path produces when the same
deadline fires and the child is SIGKILLed. Written as ``_exit_status(-9)``
rather than as ``137`` so the two paths cannot drift.
"""


@runtime_checkable
class BashEnvironment(Protocol):
    """Where this tool's commands actually run. Injected, never imported.

    Plan 0029 Q11, narrowed to the one method ``bash`` calls — the same
    narrowing as :class:`~omicsclaw.tools.builtin.read.FileReadEnvironment`
    and :class:`~omicsclaw.tools.builtin.write.FileWriteEnvironment`, and
    for the same reason: Protocols are structural, so a single object
    implementing harness9's whole five-method ``sandbox.Environment`` shape
    satisfies all three at once, while a test double for ``bash`` is not
    made to stub a filesystem.

    Two obligations an implementation carries, because this tool cannot
    check either:

    * ``cwd`` is where the command must run. It is the workspace root, and
      an implementation that ignores it silently relocates every relative
      path a model writes.
    * ``timeout`` is the caller's budget in seconds, and it is passed
      rather than merely enforced from outside so that an implementation
      can end the command cleanly instead of being abandoned mid-call.
      This tool applies its own deadline as well, because an environment
      that overruns must not be able to spend the engine's budget too.

    :attr:`CommandOutcome.exit_code` should already follow the shell's
    ``128 + signum`` convention. :func:`_exit_status` is applied to it
    anyway: an implementation written on :mod:`asyncio.subprocess` would
    naturally return ``-9``, and normalising at the seam is cheaper than
    trusting every future implementation to have read trap 16.
    """

    async def run_bash(
        self,
        command: str,
        cwd: str,
        timeout: float,
    ) -> CommandOutcome:
        """Run ``command`` under ``cwd`` and return what it produced."""
        ...


def _description(limit: float, *, local: bool) -> str:
    """What the model is told, with the real numbers in it.

    Built per instance rather than fixed, because every number in it is a
    promise about *this* tool's configuration: a deployment that raised
    ``timeout`` and left the sentence at 45 would be lying to the model in
    a way nothing else would catch. ``bash.go:101`` formats its own limits
    into the schema for the same reason.

    :param limit: Seconds a command may run.
    :param local: Whether commands run on this machine, where a kill takes
        the command's whole process group, rather than in an injected
        :class:`BashEnvironment`, which may kill less.
    """
    if local:
        killed = "and everything they started is killed with them"
    else:
        killed = "but what they started may keep running"
    return (
        "Run a bash command in the session workspace and read back stdout "
        "and stderr, merged, in the order they were written. The "
        "workspace root is the working directory, and each call starts a "
        "new shell there: a cd, an export or an activated environment does "
        "not carry over to the next call. A NON-ZERO EXIT STATUS "
        "is reported to you as the command's own result, not as a failure "
        "of this tool: read it and fix what the command was complaining "
        f"about. Commands are killed after {limit:g} seconds, {killed}. "
        f"Output longer than {MAX_OUTPUT_CHARS} characters is cut in the middle, "
        "keeping the start and a larger share of the END, so a summary "
        "printed last is never what gets lost. Anything you put in the "
        "background with & in a command that finishes in time keeps "
        "running, but this tool's capture of its output is deleted the "
        "moment this call returns, so redirect it yourself: "
        "'nohup cmd > out.log 2>&1 &'. There is no stdin: an "
        "interactive command sees end-of-file immediately, so pass input "
        "with flags, a heredoc or a file. Depending on the session's "
        "permission settings, the user may be asked to approve a command "
        "before it runs; a declined command returns an error and nothing runs."
    )


def _timeout_description(limit: float) -> str:
    """The ``timeout_secs`` field, stating the cap honestly.

    Plan 0029 Q4 keeps the argument for the case it is genuinely good at —
    a probe the model wants to give up on quickly — while the cap equals
    the default, so the only direction it moves is down. Saying so is the
    point: an argument documented as negotiable when it is not costs the
    model a turn discovering that.
    """
    return (
        f"Optional: seconds to allow this command, at most {limit:g}, and "
        f"{limit:g} if you omit it. It can only make the limit SHORTER — a "
        "larger value is capped — so use it when you want a probe to give "
        "up fast, not to buy more time for a slow suite."
    )


BASH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": (
                "The bash command to run, e.g. 'ls -la' or 'pytest "
                "tests/ -q'. Chains and pipes are fine. Required."
            ),
        },
        "timeout_secs": {
            "type": "integer",
            "description": _timeout_description(DEFAULT_TIMEOUT),
        },
    },
    "required": ["command"],
    "additionalProperties": False,
}
"""The template. :meth:`BashTool.definition` serves a per-instance copy.

``additionalProperties: false`` for the reason ``READ_SCHEMA`` gives: a
key nobody declared should come back as ``input.foo is not allowed``,
which the model can act on.
"""


_POLICY = ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.ASK,
    prompts_for_itself=True,
    read_only=False,
    concurrency_safe=False,
    writes_workspace=True,
    allowed_in_background=False,
    tags=frozenset({"workspace", "shell", "mutation"}),
)
"""``ASK`` and ``HIGH``, **declared rather than defaulted** (plan 0029 Q2).

Omitting ``policy`` would land on these same two values by accident, and
that is exactly why they are written down: a guarded default nobody chose
and a guarded default somebody chose are indistinguishable at the call
site and completely different the day someone relaxes the default.

Every other field is a *claim* in plan 0028's split, and the honest claim
for a shell is the pessimistic one. ``writes_workspace=True`` because most
useful commands do. ``concurrency_safe=False`` because two shells in one
turn share a filesystem and a port space, and unlike ``write`` there is no
path to lock — a lock table cannot key on ``rm -rf build``.
``allowed_in_background=False`` because this tool's only boundary is a
human, and an unattended turn has no human in it.

harness9 defaults to running anything at all, unasked (``bash.go:3-4``
calls it the YOLO philosophy), and it can afford to because it has a
Docker sandbox underneath. This project has none (plan 0029 Q11, §12), and
the machine in question holds genomic data and a readable ``.env``. So the
one axis available is used to the full.

**This tool is inert until some surface binds an approval channel.** That
is plan 0029 Q2's accepted cost, not a defect:
:func:`~omicsclaw.tools.context.require_approval` fails closed and nothing
in production binds a channel yet. A deployment that wants it unattended
passes its own policy to
:meth:`~omicsclaw.tools.registry.ToolRegistry.register` — deliberate, and
visible in a diff, which is the whole point.
"""


class BashTool:
    """Run a shell command in the session's workspace.

    Satisfies :class:`~omicsclaw.tools.base.Tool` structurally: it
    subclasses nothing and the Protocol is never imported here.
    Hand-written rather than wrapped in a
    :class:`~omicsclaw.tools.function_tool.FunctionTool` for the reason
    plan 0029 §5 gives and ``builtin/write.py`` states at length — this is
    an ``ASK`` tool, and an approval prompt has to show the bytes the model
    actually sent, which an adapter that decodes and re-encodes cannot do.

    ``workspace`` may be omitted, in which case the session's bound one is
    read per call; see
    :func:`~omicsclaw.tools.builtin.read.resolve_workspace`.

    ``timeout`` is the operator's budget in seconds and must be positive.
    It is **not** clamped to anything, because the operator setting it is
    the same person setting ``EngineConfig.tool_timeout`` and this layer
    cannot read that value to clamp against; what happens if they are set
    inconsistently is written on :data:`DEFAULT_TIMEOUT`.

    ``policy`` is a plain attribute, which is all
    :meth:`~omicsclaw.tools.registry.ToolRegistry.policy_for` looks for,
    and there is deliberately no ``policy`` constructor argument:
    ``register(policy=)`` is the override plan 0028 Q5 made authoritative
    and the one :func:`~omicsclaw.tools.context.require_approval` actually
    reads, so a second spelling would be a weaker way to say the same
    thing in a place an operator would not look.
    """

    policy = _POLICY

    def __init__(
        self,
        workspace: Workspace | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        environment: BashEnvironment | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError(
                f"timeout must be a positive number of seconds; got "
                f"{timeout!r}. A zero or negative budget would kill every "
                "command before it started"
            )
        self._workspace = workspace
        self._environment = environment
        self.timeout = float(timeout)
        schema = copy.deepcopy(BASH_SCHEMA)
        schema["properties"]["timeout_secs"]["description"] = (
            _timeout_description(self.timeout)
        )
        self._definition = ToolDefinition(
            name=TOOL_NAME,
            description=_description(self.timeout, local=environment is None),
            input_schema=schema,
        )

    @property
    def name(self) -> str:
        return TOOL_NAME

    @property
    def max_timeout(self) -> float:
        """The longest ``timeout_secs`` may ask for: the operator's own budget.

        Plan 0029 Q4 specifies a ceiling that happens to equal the default,
        which is the same behaviour written as a second constant. Derived
        instead, because two numbers whose equality *is* the invariant can
        drift apart in one edit and nothing would notice — and because a
        deployment that raises ``timeout`` gets a ceiling that follows,
        rather than a cap it forgot was there.
        """
        return self.timeout

    def definition(self) -> ToolDefinition:
        """Built once and returned unchanged, so the prompt prefix is stable.

        Deep-copied from :data:`BASH_SCHEMA` at construction, so two
        instances — one per registry — cannot share the nested
        ``properties`` mapping, and so each can state its own limits.
        """
        return self._definition

    async def execute(self, arguments: str) -> str:
        """Decode, **ask**, run, report. The order is the design.

        ``arguments`` reaches
        :func:`~omicsclaw.tools.context.require_approval` unparsed, which
        is why this class exists rather than a
        :class:`~omicsclaw.tools.function_tool.FunctionTool`. Nothing runs
        before the answer comes back, and there is nothing to undo if it is
        no, because a command not started has no effect to reverse.

        Returned text, never a raised exception, for everything the command
        itself did — see this module's docstring on Q6. Exceptions are for
        what the model can fix by sending different arguments, plus a
        refusal from the approval channel, which is its own sentence and
        not this tool's to rephrase.
        """
        command, timeout = self._arguments(arguments)
        cwd = resolve_workspace(self._workspace).root

        await require_approval(
            self.name,
            arguments,
            policy=self.policy,
            reason=self._reason(command, timeout, cwd),
            reason_shows_call=True,
        )
        await report_progress(
            f"running in {cwd}: {_one_line(command)}",
            tool_name=self.name,
        )

        environment = self._environment
        if environment is not None:
            outcome, timed_out = await _in_environment(
                environment, command, cwd, timeout
            )
        else:
            outcome, timed_out = await _locally(command, cwd, timeout)

        if timed_out:
            return _timed_out(outcome.output, timeout)
        return _report(outcome)

    # ---- internals ------------------------------------------------------

    def _arguments(self, arguments: str) -> tuple[str, float]:
        """The payload as ``(command, timeout)``, or a complaint.

        :func:`~omicsclaw.tools.function_tool.decode_arguments` is shared
        rather than re-written: it is the only decoder in this package that
        reports *where* a truncated payload stopped, and a hand-written
        copy has already been observed dropping exactly that (see its
        docstring).

        ``timeout_secs`` is validated rather than coerced, and Python is
        what makes that possible. Go's decoder cannot tell an omitted
        integer from a zero, so ``bash.go:72-84`` has to read ``0`` as
        "not given"; here an omitted argument is ``None`` and a ``0`` was
        really sent, so it is really a mistake and saying so costs the
        model one corrected call instead of a silent 45 seconds it did not
        ask for. ``builtin/read.py`` makes the same call for
        ``start_line``.
        """
        decoded = decode_arguments(arguments)
        issues = validate_arguments(decoded, BASH_SCHEMA)
        if issues:
            listed = "\n".join(f"  - {issue}" for issue in issues)
            raise ToolArgumentError(
                "the arguments do not match this tool's schema:\n"
                f"{listed}\nRe-send the call with all of these corrected."
            )

        command = str(decoded["command"])
        if not command.strip():
            raise ToolArgumentError(
                "input.command is required and must be a command to run; "
                "an empty string runs nothing. Send the command you meant, "
                "for example 'ls -la'"
            )

        requested = decoded.get("timeout_secs")
        if requested is None:
            return command, self.timeout
        if requested <= 0:
            raise ToolArgumentError(
                f"input.timeout_secs must be 1 or greater; got {requested}. "
                f"Omit it to use the {self.timeout:g}s default"
            )
        return command, min(float(requested), self.max_timeout)

    def _reason(self, command: str, timeout: float, cwd: Path) -> str:
        """What the human is told they are approving.

        The **whole** command, never an excerpt. A summary is where
        ``; rm -rf ~`` hides, and the person clicking is the only boundary
        this tool has. Where it will run is named for the same reason, and
        so is the absence of isolation, because "run a command" and "run a
        command as me, on this machine, with my keys reachable" are
        different decisions and only one of them is being offered.
        """
        if self._environment is not None:
            where = "in this session's injected execution environment"
        else:
            where = f"directly on this machine, with no OS isolation, in {cwd}"
        return (
            f"run a shell command {where}, with a {timeout:g}s limit. It "
            f"can read, change or delete anything this process can:\n"
            f"{command}"
        )


# ---- where the command actually runs -------------------------------------


async def _in_environment(
    environment: BashEnvironment,
    command: str,
    cwd: Path,
    timeout: float,
) -> tuple[CommandOutcome, bool]:
    """Route the command through the injected environment (plan 0029 Q11).

    The budget is passed *and* imposed. Passed, so an implementation can
    stop the command cleanly and return whatever it printed; imposed,
    because a ``run_bash`` that ignores its argument would otherwise spend
    the engine's budget too, and the model would read the engine's timeout
    sentence instead of :func:`_timeout_banner`'s.

    **Only the budget that actually fired may claim the timeout.** An
    environment with a network client of its own raises the very class an
    expired deadline does, and reported as ours the model would be told to
    narrow a command when the truth is that a container host is
    unreachable. :func:`asyncio.timeout` can be *asked* which it was, so it
    is — the same reasoning, and the same ``expired()`` call, as
    ``omicsclaw/engine/executor.py::_execute``.

    An environment that does time out leaves nothing to report but the
    banner, which is the honest answer: unlike the local path there is no
    partial capture to read back.

    ``except OSError`` only, and it is reached only after ``TimeoutError``
    has had its turn — on 3.11+ the builtin ``TimeoutError`` **is** an
    ``OSError``, so the order of these two clauses is load-bearing.
    :exc:`asyncio.CancelledError` is neither, and is not caught at all
    (plan 0029 trap 5).
    """
    budget = asyncio.timeout(timeout)
    try:
        async with budget:
            outcome = await environment.run_bash(command, str(cwd), timeout)
    except TimeoutError:
        if not budget.expired():
            raise
        return _KILLED_BY_DEADLINE, True
    except OSError as exc:
        raise RuntimeError(
            f"the execution environment could not run the command: {exc}"
        ) from exc
    return (
        CommandOutcome(
            output=outcome.output,
            exit_code=_exit_status(outcome.exit_code),
        ),
        False,
    )


async def _locally(
    command: str,
    cwd: Path,
    timeout: float,
) -> tuple[CommandOutcome, bool]:
    """Run the command here, capturing output in a temporary file.

    **Not a pipe** — this module's docstring gives the measurements, and
    ``tests/tools/test_bash.py`` pins them. The file is handed to the
    child as an ordinary fd, so
    :meth:`asyncio.subprocess.Process.wait` waits for ``bash -c`` itself
    and for nothing that ``bash`` chose to background.

    ``stdin`` is :data:`~subprocess.DEVNULL`, which the reference does not
    do (``bash.go:174-177`` leaves it inherited). Two reasons, and the
    second is why it is not merely a nicety: a command that reads standard
    input would otherwise block until the deadline rather than seeing
    end-of-file, and on the CLI Surface the inherited stdin is **the
    user's terminal**, so an inherited fd is a subprocess competing with
    the human for their own keystrokes.

    A command that ends by itself leaves whatever it backgrounded running.
    Every other exit kills the shell's whole process group (see
    :func:`_start`): the deadline and a cancellation through :func:`_kill`,
    which also reaps the shell, and any other exception through the
    ``finally``. A cancellation that arrives while the shell is still being
    started is handled by :func:`spawn_group_leader` in the same way. A
    cancellation is re-raised unchanged once the group has been killed.

    The temporary file is removed on every exit path, cancellation
    included, which is also what makes the note in :func:`_description`
    true: a backgrounded process still holding the fd is writing to an
    unlinked inode nobody will read.
    """
    handle, capture = tempfile.mkstemp(prefix="omicsclaw-bash-", suffix=".log")
    try:
        with os.fdopen(handle, "wb") as sink:
            process = await spawn_group_leader(_start(command, cwd, sink))
            timed_out = False
            try:
                async with asyncio.timeout(timeout):
                    code = await process.wait()
            except TimeoutError:
                timed_out = True
                code = await _kill(process)
            except asyncio.CancelledError:
                # Named, not handled: the group is killed and the shell
                # reaped, then the exception continues on its way untouched.
                await _kill(process)
                raise
            finally:
                if process.returncode is None:
                    _signal(process)
        output = _read_back(capture)
    finally:
        os.unlink(capture)
    return CommandOutcome(output=output, exit_code=_exit_status(code)), timed_out


# ---- module-level helpers ------------------------------------------------


async def _start(command: str, cwd: Path, sink: Any) -> asyncio.subprocess.Process:
    """Start ``bash -c command``, or say why it could not start.

    ``create_subprocess_exec("bash", ...)`` rather than
    ``create_subprocess_shell``, which runs ``/bin/sh``. On Debian and
    Ubuntu — the base of this project's own images — ``/bin/sh`` is
    ``dash``, which has no ``[[ ]]``, no arrays and no ``pipefail``, and a
    tool named ``bash`` whose description promises bash has to be bash.

    The shell starts in a new session, which has no controlling terminal.
    It leads a process group of its own, whose id is its pid and which
    every process it starts inherits, so :func:`_signal` reaches all of
    them at once.

    The two ways this fails are both deployment faults rather than
    anything the model chose, so neither is dressed up as a correctable
    argument: no ``bash`` on ``PATH``, or a workspace root that is not
    there.
    """
    try:
        return await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            command,
            cwd=str(cwd),
            env=without_control_credentials(),
            stdout=sink,
            stderr=sink,
            stdin=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError(
            f"could not start a shell in {cwd}: {exc}. Either bash is not "
            "on PATH or the workspace directory does not exist"
        ) from exc


_REAP_GRACE = 2.0
"""Seconds :func:`_kill` waits for a killed shell to exit, and
:func:`spawn_group_leader` for a spawn to finish."""


def _signal(process: asyncio.subprocess.Process) -> None:
    """SIGKILL the command's whole process group.

    The group's id is the shell's pid, because :func:`_start` gives the
    shell a session of its own. It stays addressable after the shell has
    exited, for as long as anything the shell started is still in it.

    Never raises for the two answers that leave nothing more to do:
    :exc:`ProcessLookupError` when the group has no members left, and
    :exc:`PermissionError` when none of its members may be signalled by
    this process, such as a setuid program the shell exec-ed into.
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


async def _kill(process: asyncio.subprocess.Process) -> int:
    """SIGKILL the command's process group and reap the shell.

    Waits at most :data:`_REAP_GRACE` seconds for the shell to exit. A
    shell still running by then, one the signal could not reach, is left
    to asyncio's child watcher.

    :returns: the shell's return code as :mod:`asyncio.subprocess` reports
        it, or ``-SIGKILL`` when it had not exited within the grace period.
    :raises asyncio.CancelledError: when the wait is cancelled; the group
        has already been signalled by then.
    """
    _signal(process)
    try:
        return await asyncio.wait_for(process.wait(), _REAP_GRACE)
    except TimeoutError:
        return -signal.SIGKILL


_ABANDONED_SPAWNS: set[asyncio.Future[Any]] = set()
"""Spawns whose caller was cancelled, held until they finish."""


async def spawn_group_leader(
    spawn: Coroutine[Any, Any, asyncio.subprocess.Process],
) -> asyncio.subprocess.Process:
    """Await *spawn*; if the caller is cancelled first, kill what it starts.

    *spawn* runs as a Task of its own, so cancelling the caller does not
    interrupt it. When the caller is cancelled before *spawn* has
    finished, the started process's whole group is SIGKILLed as soon as
    *spawn* returns it. This waits up to :data:`_REAP_GRACE` seconds for
    that, then up to as long again for the process to exit, and re-raises
    the cancellation. A spawn still running after the first wait is killed
    when it finishes. A spawn that fails after the caller was cancelled
    has started nothing, and its exception is discarded.

    A spawn that is itself cancelled, as when its loop shuts down, is
    cleaned up by asyncio, which kills the process it started and nothing
    else.

    :param spawn: A coroutine that starts a process leading a process group
        of its own and returns it, such as
        :func:`asyncio.create_subprocess_exec` with
        ``start_new_session=True``.
    :returns: The started process.
    :raises asyncio.CancelledError: When the awaiting Task is cancelled.
    :raises Exception: Whatever *spawn* raises, when the caller was not
        cancelled.
    """
    starting = asyncio.ensure_future(spawn)
    try:
        return await asyncio.shield(starting)
    except asyncio.CancelledError:
        _ABANDONED_SPAWNS.add(starting)
        starting.add_done_callback(_kill_when_started)
        await asyncio.wait({starting}, timeout=_REAP_GRACE)
        process = _started(starting)
        if process is not None:
            await _kill(process)
        raise


def _started(
    starting: asyncio.Future[asyncio.subprocess.Process],
) -> asyncio.subprocess.Process | None:
    """The process *starting* produced, or ``None`` if it has not produced one."""
    if not starting.done() or starting.cancelled():
        return None
    if starting.exception() is not None:
        return None
    return starting.result()


def _kill_when_started(starting: asyncio.Future[asyncio.subprocess.Process]) -> None:
    """Done callback: :func:`_signal` the process *starting* produced, if any."""
    _ABANDONED_SPAWNS.discard(starting)
    process = _started(starting)
    if process is not None:
        _signal(process)


def _read_back(capture: str) -> str:
    """The captured output as text, decoded once, replacing what will not.

    ``errors="replace"`` is what makes :data:`MAX_OUTPUT_CHARS` countable
    in characters: after this line there are no partial characters left to
    cut in half, so the reference's two rune-trimming helpers have nothing
    to do and are absent rather than translated (plan 0029 trap 15). A
    command emitting genuinely binary output reads as replacement
    characters, which is the truthful rendering of "this was not text".
    """
    with open(capture, "rb") as handle:
        return handle.read().decode("utf-8", errors="replace")


def _truncate(output: str) -> str:
    """Keep the start and — twice as much of — the end. ``bash.go:205-222``.

    The tail is the part worth keeping, and that is a measured claim
    rather than a preference: a test runner's verdict, an installer's
    error and a compiler's summary all arrive last, and the implementation
    the reference replaced kept only the head.

    Sliced on a :class:`str`, so a character cannot be cut in half and
    there is nothing to repair afterwards. See :data:`MAX_OUTPUT_CHARS`.
    """
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    head = output[:HEAD_CHARS]
    tail = output[len(output) - TAIL_CHARS :]
    elided = len(output) - HEAD_CHARS - TAIL_CHARS
    return (
        f"{head}\n\n...[Output too long: {elided} characters from the "
        f"middle were cut. The first {HEAD_CHARS} and the last "
        f"{TAIL_CHARS} are kept, so anything printed at the end is still "
        "here. Narrow the command if you need all of it.]...\n\n"
        f"{tail}"
    )


def _timeout_banner(timeout: float) -> str:
    """A machine-readable notice that the harness, not the code, stopped this.

    ``bash.go:199-203``, and the distinction it draws is the whole value:
    without it a model reads a truncated output with no verdict and
    concludes the code is broken, then edits something that was fine. The
    bracketed ``[TIMEOUT …]`` form is deliberately greppable, and the
    advice is the reference's — run one test instead of the suite.

    One sentence is not the reference's. harness9 tells the model to raise
    ``timeout_secs``; here that would be advice the model cannot take, so
    it is replaced with the true statement that the argument only shortens
    the limit. See :func:`_timeout_description`.
    """
    return (
        f"\n\n[TIMEOUT {timeout:g}s: the command was killed for running "
        "past its time limit. This is not an error in your code, and "
        "anything above is only what it had printed by then. If this was a "
        "test suite or an install, run a single test or narrow the "
        "command — timeout_secs can only shorten this limit, never extend "
        "it.]"
    )


def _timed_out(output: str, timeout: float) -> str:
    """Whatever was printed, truncated, then the banner. **In that order.**

    ``bash.go:187`` says why in one line: truncate first, so the banner
    cannot be the part that gets cut. Reversed, the longest and most
    confusing outputs — the ones where the notice is worth most — are
    exactly the ones that lose it.

    With nothing printed there is nothing to separate, so the banner's
    leading blank line goes with it.
    """
    body = _truncate(output)
    banner = _timeout_banner(timeout)
    return body + banner if body else banner.lstrip("\n")


def _report(outcome: CommandOutcome) -> str:
    """The text a finished command becomes. Never an error (plan 0029 Q6).

    The status line is added **after** truncation, for the reason the
    banner is: a failing command with 200,000 characters of output is
    precisely the one whose exit status must survive.

    Both empty-output cases are answered in words rather than with an
    empty string — ``bash.go:147-148, 193-194`` for the successful one.
    ``""`` read as an Observation looks like a tool that did not run, and
    a model's next move after "the tool did not run" is to run it again.
    """
    body = _truncate(outcome.output)
    if outcome.exit_code != 0:
        if not body:
            return (
                f"[exit status {outcome.exit_code}] The command failed and "
                "printed nothing."
            )
        return f"[exit status {outcome.exit_code}]\n{body}"
    if not body:
        return "The command finished successfully with no terminal output."
    return body


def _one_line(command: str) -> str:
    """A command as a single line, for a progress message.

    Display only, and the approval prompt is where the full text is
    guaranteed to appear — :meth:`BashTool._reason` says why it is not
    abbreviated there. Nothing is truncated here either; a multi-line
    command is collapsed to its first line so a status display stays one
    line, which is the only property a progress sink needs.
    """
    first, separator, _ = command.partition("\n")
    return f"{first} …" if separator else first


__all__ = [
    "BASH_SCHEMA",
    "BashEnvironment",
    "BashTool",
    "CONTROL_CREDENTIAL_NAMES",
    "CommandOutcome",
    "DEFAULT_TIMEOUT",
    "ENGINE_TIMEOUT_MARGIN",
    "HEAD_CHARS",
    "MAX_OUTPUT_CHARS",
    "TAIL_CHARS",
    "TOOL_NAME",
    "spawn_group_leader",
    "without_control_credentials",
]
