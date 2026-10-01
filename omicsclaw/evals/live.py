"""Real-model routing eval: which skill a real model picks for a request.

Each seed in ``tests/evals/fixtures/live_routing_seed.json`` is a user
request with the skills that answer it. :func:`live_case` turns one seed
into a :class:`~omicsclaw.evals.case.Case` that runs through the Runner
against a real provider wrapped in :class:`RecordingProvider`, with
network access, default permission mode, the approval policy of
:func:`routing_policy` and a fallback stub for every skill without a
fixture. :func:`judge` reads the trajectory and decides what the model
chose; :func:`build_report` and :func:`compare` summarise runs.

``python -m omicsclaw.evals.live compare <old.json> <new.json>`` prints
how each seed's pass rate and choice changed between two reports.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import os
import shlex
import sys
import threading
from collections import Counter
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omicsclaw.entry.config import SkillEnvMode
from omicsclaw.entry.project import STEP_RUNNER
from omicsclaw.permission.gate import DOTENV_NAME
from omicsclaw.provider import Completion, LLMProvider, ProviderError
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolDefinition,
    Usage,
)
from omicsclaw.skills import SkillIndex
from omicsclaw.tools import ApprovalDecision, ApprovalRequest

from .case import Case, Result
from .provider import RecordedCall
from .ledger import read_ledgers
from .stubs import REPO_ROOT, StubResult, _git_commit, find_skill_run

__all__ = [
    "CATEGORY",
    "FALLBACK_STUB",
    "SEED_FILE",
    "Denial",
    "LiveReport",
    "RecordingProvider",
    "Seed",
    "Verdict",
    "build_report",
    "compare",
    "judge",
    "live_case",
    "load_report",
    "load_seeds",
    "main",
    "routing_policy",
    "write_json",
    "write_markdown",
]

CATEGORY = "live_routing"
SEED_FILE = REPO_ROOT / "tests" / "evals" / "fixtures" / "live_routing_seed.json"
LIVE_MAX_TURNS = 6

FALLBACK_STUB = StubResult(
    stdout="[eval] {skill} run recorded; outputs in {output}",
    exit_code=0,
    files={"result.json": '{"status": "ok", "note": "placeholder written by the routing eval"}\n'},
)
"""What a run of a skill without a recorded fixture returns."""

_META_CHARACTERS = (";", "&", "|", "$", "`", "<", ">", "(", ")", "\n", "\r")
_READ_ONLY = frozenset(
    {"ls", "cat", "head", "tail", "wc", "find", "grep", "pwd", "file", "stat", "tree", "du"}
)
_FIND_ACTIONS = frozenset(
    {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"}
)
_WORKSPACE_TOOLS = frozenset({"write_file", "edit_file"})
_WEB_TOOLS = frozenset({"web_fetch", "web_search"})


# ---- seeds -------------------------------------------------------------------


@dataclass(frozen=True)
class Seed:
    """One routing request and what answers it.

    :param id: The seed id, ``<domain>__<name>``.
    :param domain: The domain the request belongs to.
    :param query: The user's request.
    :param expected_skills: Skills any of which is a correct choice.
        Empty for a ``no_skill`` seed.
    :param decision: ``"route"`` or ``"no_skill"``.
    :param inputs: Workspace-relative input files named in the prompt.
    :param expected_args: Arguments the executed command should carry,
        as ``(flag, value)`` pairs. Only scored, never required.
    """

    id: str
    domain: str
    query: str
    expected_skills: tuple[str, ...]
    decision: str
    inputs: tuple[str, ...] = ()
    expected_args: tuple[tuple[str, str], ...] = ()


def load_seeds(path: Path = SEED_FILE) -> tuple[Seed, ...]:
    """Read the seeds from *path*.

    :raises OSError: the file cannot be read.
    :raises KeyError: a seed lacks a required field.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(
        Seed(
            id=item["id"],
            domain=item["domain"],
            query=item["query"],
            expected_skills=tuple(item["expected_skills"]),
            decision=item["decision"],
            inputs=tuple(item.get("inputs", ())),
            expected_args=tuple(
                (flag, value) for flag, value in dict(item.get("expected_args", {})).items()
            ),
        )
        for item in data["cases"]
    )


def seed_digest(path: Path = SEED_FILE) -> str:
    """The sha256 of the seed file, for the report's metadata."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- the recording provider ----------------------------------------------------


class _Records:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.calls: list[RecordedCall] = []
        self.replies: list[Message] = []
        self.side_calls: list[RecordedCall] = []
        self.usage = Usage()


class RecordingProvider:
    """A real :class:`~omicsclaw.provider.LLMProvider` that records its traffic.

    Every call is recorded like a
    :class:`~omicsclaw.evals.provider.ScriptedProvider` call: calls made
    with tools go to :attr:`calls`, calls with ``tools=None`` to
    :attr:`side_calls`. :attr:`replies` holds the reply of each call in
    :attr:`calls`, in the same order (an empty assistant message when the
    call raised). Views from :meth:`bind` share the records, so a
    sub-agent's calls land in the same lists, in the order they were made.

    :param inner: The provider that answers.
    """

    def __init__(self, inner: LLMProvider, *, _records: _Records | None = None,
                 _bound: Mapping[str, Any] | None = None) -> None:
        self._inner = inner
        self._records = _records if _records is not None else _Records()
        self._bound = dict(_bound or {})

    @property
    def name(self) -> str:
        """The wrapped provider's name."""
        return self._inner.name

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        """Call the wrapped provider and record the call and its reply.

        :raises Exception: whatever the wrapped provider raises; the call
            is still recorded.
        """
        reply = Message(role=Role.ASSISTANT, content="")
        usage = Usage()
        try:
            completion = await self._inner.generate(messages, tools)
            reply = completion.message
            usage = completion.usage or Usage()
            return completion
        finally:
            self._record(messages, tools, reply, usage)

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream the wrapped provider's chunks, recording the ``DONE`` message."""
        return self._stream(messages, tools)

    async def _stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
    ) -> AsyncIterator[StreamChunk]:
        reply = Message(role=Role.ASSISTANT, content="")
        usage = Usage()
        try:
            async for chunk in self._inner.generate_stream(messages, tools):
                if chunk.type is StreamChunkType.DONE:
                    if chunk.message is not None:
                        reply = chunk.message
                    if chunk.usage is not None:
                        usage = chunk.usage
                yield chunk
        finally:
            self._record(messages, tools, reply, usage)

    def bind(self, **overrides: Any) -> RecordingProvider:
        """A view over ``inner.bind(**overrides)`` that shares these records."""
        return RecordingProvider(
            self._inner.bind(**overrides),
            _records=self._records,
            _bound={**self._bound, **overrides},
        )

    def _record(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
        reply: Message,
        usage: Usage,
    ) -> None:
        offered = tuple(tools) if tools is not None else ()
        call = RecordedCall(
            messages=tuple(messages),
            tools=tuple(tool.name for tool in offered),
            full_tools=offered,
            bound=dict(self._bound),
        )
        records = self._records
        with records.lock:
            records.usage = records.usage + usage
            if tools is None:
                records.side_calls.append(call)
            else:
                records.calls.append(call)
                records.replies.append(reply)

    @property
    def calls(self) -> tuple[RecordedCall, ...]:
        """Every call made with tools, oldest first."""
        with self._records.lock:
            return tuple(self._records.calls)

    @property
    def replies(self) -> tuple[Message, ...]:
        """The reply to each call in :attr:`calls`, in the same order."""
        with self._records.lock:
            return tuple(self._records.replies)

    @property
    def side_calls(self) -> tuple[RecordedCall, ...]:
        """Every call made with ``tools=None``, oldest first."""
        with self._records.lock:
            return tuple(self._records.side_calls)

    @property
    def usage(self) -> Usage:
        """The summed usage of every call, side calls included."""
        with self._records.lock:
            return self._records.usage

    @property
    def turn_index(self) -> int:
        """How many calls with tools have been made."""
        with self._records.lock:
            return len(self._records.calls)

    @property
    def exhausted(self) -> int:
        """Always 0: a real provider has no script to run out of."""
        return 0


# ---- the approval policy -------------------------------------------------------


@dataclass(frozen=True)
class Denial:
    """One approval request the routing policy refused.

    :param tool: The tool that asked.
    :param kind: ``"unmatched_skill_command"`` (names a skill directory
        but is not a recognised run of its script), ``"help_not_strict"``,
        ``"web"``, ``"outside_workspace"`` or ``"not_permitted"``.
    :param detail: The command or path.
    """

    tool: str
    kind: str
    detail: str


def _arguments(request: ApprovalRequest) -> dict[str, Any]:
    try:
        value = json.loads(request.arguments or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _interpreters() -> frozenset[str]:
    return frozenset({"python", "python3", sys.executable, os.path.realpath(sys.executable)})


def is_strict_help(command: str, workspace: Path, index: SkillIndex) -> bool:
    """Whether *command* is exactly ``python <skill script> --help`` (or ``-h``).

    The interpreter may be ``python``, ``python3`` or the running one. No
    environment prefix, no other argument and no shell metacharacter is
    allowed.
    """
    if any(mark in command for mark in _META_CHARACTERS):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) != 3 or tokens[0] not in _interpreters() or tokens[2] not in ("--help", "-h"):
        return False
    run = find_skill_run(command, workspace, index)
    return run is not None and run.wants_help


def is_read_only(command: str) -> bool:
    """Whether *command* only reads: listed commands joined by ``|`` and nothing else.

    Every ``|``-separated segment must start with one of ``ls``, ``cat``,
    ``head``, ``tail``, ``wc``, ``find``, ``grep``, ``pwd``, ``file``,
    ``stat``, ``tree`` or ``du``. Any other shell metacharacter, a
    ``find`` action that runs or writes something, ``tree -o`` and a
    literal ``.env`` make it not read-only.
    """
    if any(mark in command for mark in _META_CHARACTERS if mark != "|"):
        return False
    if DOTENV_NAME.search(command):
        return False
    for segment in command.split("|"):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            return False
        if not tokens or tokens[0] not in _READ_ONLY:
            return False
        if tokens[0] == "find" and any(token in _FIND_ACTIONS for token in tokens):
            return False
        if tokens[0] == "tree" and any(token == "-o" or token.startswith("-o") for token in tokens[1:]):
            return False
    return True


_RUNNER_SUBCOMMANDS = frozenset({"new", "run", "status", "replay"})


def _same_file(token: str, target: Path, workspace: Path) -> bool:
    path = Path(token)
    if not path.is_absolute():
        path = workspace / path
    return os.path.realpath(path) == os.path.realpath(target)


def is_step_runner(command: str, runner: Path, workspace: Path) -> bool:
    """Whether *command* is one plain call of the step runner at *runner*.

    ``python <runner> <subcommand> ...``, the form the Environment section
    gives, where the script resolves to *runner* itself (a relative path
    against *workspace*). The interpreter is ``python``, ``python3`` or the
    running one, there is no shell metacharacter, and the subcommand is
    ``new``, ``run``, ``status`` or ``replay``: ``accept`` and ``revise``
    record the user's decision, so they are not approved here.
    """
    if any(mark in command for mark in _META_CHARACTERS):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) < 3 or tokens[0] not in _interpreters():
        return False
    if not _same_file(tokens[1], runner, workspace):
        return False
    return tokens[2] in _RUNNER_SUBCOMMANDS


def _names_a_skill_directory(command: str, index: SkillIndex) -> bool:
    for skill in index.skills:
        directory = skill.directory
        relative = directory.relative_to(REPO_ROOT) if directory.is_relative_to(REPO_ROOT) else directory
        if str(directory) in command or relative.as_posix() in command:
            return True
    return False


def _inside(path: str, workspace: Path) -> bool:
    target = Path(path)
    if not target.is_absolute():
        target = workspace / target
    try:
        return os.path.realpath(target).startswith(os.path.realpath(workspace) + os.sep)
    except (OSError, ValueError):
        return False


def routing_policy(
    workspace: Path, index: SkillIndex, denials: list[Denial]
) -> Callable[[ApprovalRequest], ApprovalDecision]:
    """The approval policy of a routing eval run.

    ``bash`` is approved for a strict ``--help`` of a skill script, for a
    run of a skill script (the stub layer answers it, so nothing runs),
    for a call of the step runner under *index*'s root
    (:func:`is_step_runner`; the step's inputs are empty files, so a real
    skill fails fast on them), and for a
    read-only command (:func:`is_read_only`); a command that
    names a skill directory without being a recognised run is refused as
    ``unmatched_skill_command``, and everything else is refused.
    ``web_fetch`` and ``web_search`` are refused. ``write_file`` and
    ``edit_file`` are approved inside *workspace* only. Every other tool is
    approved.

    :param workspace: The run's workspace; relative paths and commands
        resolve against it.
    :param index: The skill index the skill directories come from.
    :param denials: Receives one :class:`Denial` per refusal.
    :returns: A function answering one request.
    """

    def deny(tool: str, kind: str, detail: str) -> ApprovalDecision:
        denials.append(Denial(tool, kind, detail))
        return ApprovalDecision(approved=False, reason="not permitted in the routing eval")

    runner = Path(index.root).joinpath(*STEP_RUNNER)

    def decide(request: ApprovalRequest) -> ApprovalDecision:
        tool = request.tool_name
        arguments = _arguments(request)
        if tool == "bash":
            command = str(arguments.get("command", ""))
            if is_strict_help(command, workspace, index):
                return ApprovalDecision(approved=True)
            run = find_skill_run(command, workspace, index)
            if run is not None and not run.wants_help:
                return ApprovalDecision(approved=True)
            if run is not None:
                return deny(tool, "help_not_strict", command)
            if is_step_runner(command, runner, workspace):
                return ApprovalDecision(approved=True)
            if is_read_only(command):
                return ApprovalDecision(approved=True)
            if _names_a_skill_directory(command, index):
                return deny(tool, "unmatched_skill_command", command)
            return deny(tool, "not_permitted", command)
        if tool in _WEB_TOOLS:
            return deny(tool, "web", request.arguments[:200])
        if tool in _WORKSPACE_TOOLS:
            path = str(arguments.get("path", ""))
            if path and _inside(path, workspace):
                return ApprovalDecision(approved=True)
            return deny(tool, "outside_workspace", path)
        return ApprovalDecision(approved=True)

    return decide


# ---- one case ------------------------------------------------------------------


def prompt_of(seed: Seed) -> str:
    """The first user message: the query, then an ``Input:`` line when there are inputs."""
    if not seed.inputs:
        return seed.query
    return f"{seed.query}\nInput: {', '.join(seed.inputs)}"


def live_case(
    seed: Seed,
    provider: Callable[[], RecordingProvider],
    workspace: Path,
    index: SkillIndex,
    *,
    trial: int = 0,
    stubs: Mapping[str, StubResult] | None = None,
    config: Mapping[str, object] | None = None,
) -> tuple[Case, list[Denial]]:
    """The case for one trial of *seed*, and the list its policy records denials in.

    The case runs in default permission mode with :func:`routing_policy`,
    network access, ``skill_env=probe``, at most :data:`LIVE_MAX_TURNS`
    turns, the recorded *stubs* and :data:`FALLBACK_STUB` for every other
    skill. Each input file is created empty. ``PYTHONPATH`` is cleared.

    :param seed: The seed.
    :param provider: Returns a fresh :class:`RecordingProvider`.
    :param workspace: Where the Runner will put the workspace
        (``<tmp_path>/ws``); the policy needs it up front.
    :param index: The skill index.
    :param trial: The trial number, part of the case id.
    :param stubs: Recorded stubs by skill name.
    :param config: :class:`~omicsclaw.entry.AppConfig` overrides, applied
        over ``skill_env=probe``; the real ``provider`` and ``model``
        belong here.
    """
    denials: list[Denial] = []
    fields: dict[str, object] = {"skill_env": SkillEnvMode.PROBE}
    fields.update(config or {})
    case = Case(
        id=f"{CATEGORY}/{seed.id}-t{trial}",
        category=CATEGORY,
        prompt=prompt_of(seed),
        provider=provider,
        assertions=(),
        max_turns=LIVE_MAX_TURNS,
        permission="ask",
        approvals=routing_policy(workspace, index, denials),
        skill_stubs=dict(stubs or {}),
        skill_fallback=FALLBACK_STUB,
        files={path: b"" for path in seed.inputs},
        env={"PYTHONPATH": ""},
        network=True,
        config=fields,
    )
    return case, denials


# ---- judging -------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    """What one trial of a seed chose and how it is scored.

    :param outcome: ``correct``, ``wrong_skill``, ``no_skill_called`` or
        ``error``.
    :param no_skill_detail: For ``no_skill_called``: ``after_denial``,
        ``no_denial`` or ``asked_user`` (no denial, and the last reply
        ends with a question mark). Empty otherwise.
    :param first_use_skill: The first skill ``use_skill`` loaded.
    :param parallel_use_skill: The ``use_skill`` names in the first reply
        that loaded any.
    :param executed_skill: The first skill whose script ran (``--help``
        does not count) or, without one, the first skill a step loaded or
        ran through ``run_cli``, by the step ledgers.
    :param chosen: *executed_skill* when set, else *first_use_skill*.
    :param args_ok: Whether the executed command carries the seed's
        expected arguments, its input and ``--output``, or, for a function
        a step called, whether its recorded keyword arguments match; ``None``
        when the seed has no expected arguments or nothing was executed.
    :param harness_failures: The Runner's hard failures, as text.
    """

    outcome: str
    no_skill_detail: str
    first_use_skill: str | None
    parallel_use_skill: tuple[str, ...]
    executed_skill: str | None
    chosen: str | None
    args_ok: bool | None
    harness_failures: tuple[str, ...]


def _use_skill_names(message: Message) -> list[str]:
    names = []
    for call in message.tool_calls or ():
        if call.name != "use_skill":
            continue
        try:
            payload = json.loads(call.arguments or "{}")
        except ValueError:
            payload = {}
        names.append(str(payload.get("skill_name", "")) if isinstance(payload, dict) else "")
    return names


def _args_ok(command: str, seed: Seed) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False

    def value_of(flag: str) -> str | None:
        for k, token in enumerate(tokens):
            if token == flag:
                return tokens[k + 1] if k + 1 < len(tokens) else None
            if token.startswith(flag + "="):
                return token.split("=", 1)[1]
        return None

    if value_of("--output") is None and value_of("-o") is None:
        return False
    given = value_of("--input")
    if seed.inputs and (given is None or not any(given.endswith(path) for path in seed.inputs)):
        return False
    return all(value_of(flag) == value for flag, value in seed.expected_args)


def _kwargs_ok(args: Mapping[str, Any], seed: Seed) -> bool:
    """Whether a recorded function call carries each expected flag as a keyword (``--method`` as ``method``)."""
    return all(
        str(args.get(flag.lstrip("-").replace("-", "_"))) == value for flag, value in seed.expected_args
    )


def judge(
    result: Result,
    seed: Seed,
    replies: Sequence[Message],
    denials: Sequence[Denial],
) -> Verdict:
    """Score one trial from its trajectory alone.

    The chosen skill is the first skill script that ran or, when none
    ran, the first skill ``use_skill`` loaded, taking main line and
    sub-agents together in call order. A trial whose exchange ended in a
    :class:`~omicsclaw.provider.ProviderError` or ran out of time is an
    ``error``. A ``no_skill`` seed is correct when no skill script ran.

    :param result: The Runner's result.
    :param seed: The seed the trial ran.
    :param replies: :attr:`RecordingProvider.replies` of the trial.
    :param denials: The denials the trial's policy recorded.
    """
    first: str | None = None
    parallel: tuple[str, ...] = ()
    for reply in replies:
        names = _use_skill_names(reply)
        if names:
            first = names[0]
            parallel = tuple(names)
            break
    bash_runs = [run for run in result.skill_runs if run.source == "bash"]
    executed_run = bash_runs[0] if bash_runs else None
    executed = executed_run.skill if executed_run is not None else None
    if executed is None and result.workspace is not None:
        executed = read_ledgers(result.workspace).first_skill
        executed_run = next(
            (run for run in result.skill_runs if run.source == "ledger" and run.skill == executed), None
        )
    chosen = executed or first
    failures = tuple(str(failure) for failure in result.failures)
    timed_out = any(failure.assertion == "case_timeout" for failure in result.failures)

    args_ok: bool | None = None
    if seed.expected_args and executed_run is not None:
        if executed_run.function is not None:
            args_ok = _kwargs_ok(executed_run.args, seed)
        else:
            args_ok = _args_ok(executed_run.command, seed)

    detail = ""
    if isinstance(result.run_error, ProviderError) or timed_out:
        outcome = "error"
    elif seed.decision == "no_skill":
        outcome = "correct" if executed is None else "wrong_skill"
    elif chosen is None:
        outcome = "no_skill_called"
        if denials:
            detail = "after_denial"
        elif result.final_output.rstrip().endswith(("?", "？")):
            detail = "asked_user"
        else:
            detail = "no_denial"
    elif chosen in seed.expected_skills:
        outcome = "correct"
    else:
        outcome = "wrong_skill"
    return Verdict(
        outcome=outcome,
        no_skill_detail=detail,
        first_use_skill=first,
        parallel_use_skill=parallel,
        executed_skill=executed,
        chosen=chosen,
        args_ok=args_ok,
        harness_failures=failures,
    )


# ---- the report ----------------------------------------------------------------


@dataclass(frozen=True)
class TrialRecord:
    """One trial as the report keeps it."""

    verdict: Verdict
    model_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    duration_s: float
    denials: tuple[Denial, ...] = ()
    stubbed_with_fallback: bool = False


def trial_record(
    verdict: Verdict,
    result: Result,
    usage: Usage,
    denials: Sequence[Denial],
    stubbed: Mapping[str, StubResult],
) -> TrialRecord:
    """Collect what the report keeps about one trial."""
    return TrialRecord(
        verdict=verdict,
        model_calls=result.turn_count,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        duration_s=round(result.duration_s, 3),
        denials=tuple(denials),
        stubbed_with_fallback=bool(verdict.executed_skill and verdict.executed_skill not in stubbed),
    )


@dataclass(frozen=True)
class SeedReport:
    """Every trial of one seed."""

    seed: Seed
    trials: tuple[TrialRecord, ...]

    @property
    def errors(self) -> int:
        return sum(1 for trial in self.trials if trial.verdict.outcome == "error")

    @property
    def correct(self) -> int:
        return sum(1 for trial in self.trials if trial.verdict.outcome == "correct")

    @property
    def pass_rate(self) -> float | None:
        """Correct trials over trials that did not error; ``None`` when all errored."""
        scored = len(self.trials) - self.errors
        return self.correct / scored if scored else None


@dataclass(frozen=True)
class LiveReport:
    """A routing eval run: its metadata and every seed's trials."""

    meta: Mapping[str, Any]
    seeds: tuple[SeedReport, ...]


def build_report(meta: Mapping[str, Any], seeds: Sequence[SeedReport]) -> LiveReport:
    """A report over *seeds*, in seed order, with *meta* plus the run time."""
    stamped = {"run_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"), **meta}
    return LiveReport(meta=stamped, seeds=tuple(seeds))


def run_meta(provider: str, model: str, base_url: str, temperature: float, trials: int) -> dict[str, Any]:
    """The metadata a report records about the run."""
    return {
        "git_commit": _git_commit(),
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "temperature": temperature,
        "trials": trials,
        "seed_file_sha256": seed_digest(),
    }


def _rate(correct: int, scored: int) -> float | None:
    return correct / scored if scored else None


def to_dict(report: LiveReport) -> dict[str, Any]:
    """The JSON form of *report*."""
    seeds = []
    domains: dict[str, list[int]] = {}
    confusion: Counter[tuple[str, str]] = Counter()
    denials: list[dict[str, Any]] = []
    totals = Counter()
    for entry in report.seeds:
        scored = len(entry.trials) - entry.errors
        bucket = domains.setdefault(entry.seed.domain, [0, 0])
        bucket[0] += entry.correct
        bucket[1] += scored
        trials = []
        for trial in entry.trials:
            verdict = trial.verdict
            if verdict.outcome in ("wrong_skill", "no_skill_called"):
                expected = "|".join(entry.seed.expected_skills) or "(none)"
                confusion[(expected, verdict.chosen or "(none)")] += 1
            for denial in trial.denials:
                denials.append({"seed": entry.seed.id, **dataclasses.asdict(denial)})
            totals["input_tokens"] += trial.input_tokens
            totals["output_tokens"] += trial.output_tokens
            totals["cache_read_tokens"] += trial.cache_read_tokens
            totals["model_calls"] += trial.model_calls
            trials.append(
                {
                    **dataclasses.asdict(verdict),
                    "model_calls": trial.model_calls,
                    "input_tokens": trial.input_tokens,
                    "output_tokens": trial.output_tokens,
                    "cache_read_tokens": trial.cache_read_tokens,
                    "duration_s": trial.duration_s,
                    "stubbed_with_fallback": trial.stubbed_with_fallback,
                }
            )
        seeds.append(
            {
                "id": entry.seed.id,
                "domain": entry.seed.domain,
                "expected_skills": list(entry.seed.expected_skills),
                "pass_rate": entry.pass_rate,
                "errors": entry.errors,
                "trials": trials,
            }
        )
    correct = sum(entry.correct for entry in report.seeds)
    scored = sum(len(entry.trials) - entry.errors for entry in report.seeds)
    return {
        "meta": dict(report.meta),
        "pass_rate": _rate(correct, scored),
        "seeds": seeds,
        "domains": {
            name: {"correct": c, "scored": n, "pass_rate": _rate(c, n)}
            for name, (c, n) in sorted(domains.items())
        },
        "confusion": [
            {"expected": expected, "chosen": chosen, "count": count}
            for (expected, chosen), count in sorted(confusion.items())
        ],
        "denials": denials,
        "tokens": dict(totals),
    }


def write_json(report: LiveReport, path: Path) -> None:
    """Write *report* as ``live_report.json``-style JSON, parents created."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_report(path: Path) -> dict[str, Any]:
    """Read a report written by :func:`write_json`.

    :raises OSError: the file cannot be read.
    :raises ValueError: it is not JSON.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def markdown(report: LiveReport) -> str:
    """The Markdown summary of *report*."""
    data = to_dict(report)
    meta = data["meta"]
    lines = [
        "# Live routing eval",
        "",
        f"- provider: `{meta.get('provider', '')}`, model: `{meta.get('model', '')}`, "
        f"base_url: `{meta.get('base_url', '')}`, temperature: {meta.get('temperature', '')}",
        f"- trials per seed: {meta.get('trials', '')} (with 3 trials a seed can only score 0%, 33%, 67% or 100%)",
        f"- run at {meta.get('run_at', '')}, commit `{meta.get('git_commit', '')}`",
        f"- overall pass rate: {_percent(data['pass_rate'])}",
        f"- tokens: input {data['tokens'].get('input_tokens', 0)}, "
        f"cache hits {data['tokens'].get('cache_read_tokens', 0)}, "
        f"output {data['tokens'].get('output_tokens', 0)}, "
        f"model calls {data['tokens'].get('model_calls', 0)}",
        "",
        "## Domains",
        "",
        "| Domain | Correct | Scored | Pass rate |",
        "|---|---|---|---|",
    ]
    for name, row in data["domains"].items():
        lines.append(f"| {name} | {row['correct']} | {row['scored']} | {_percent(row['pass_rate'])} |")
    failing = [seed for seed in data["seeds"] if seed["pass_rate"] != 1.0]
    lines += ["", "## Seeds below 100%", ""]
    if not failing:
        lines.append("None.")
    for seed in failing:
        choices = ", ".join(
            f"{trial['outcome']}:{trial['chosen'] or '-'}" for trial in seed["trials"]
        )
        lines.append(
            f"- `{seed['id']}` (expected {', '.join(seed['expected_skills']) or 'no skill'}): "
            f"{_percent(seed['pass_rate'])}; {choices}"
        )
    lines += ["", "## Confusion (expected -> chosen)", ""]
    if not data["confusion"]:
        lines.append("None.")
    for row in data["confusion"]:
        lines.append(f"- {row['expected']} -> {row['chosen']}: {row['count']}")
    details = Counter(
        trial["no_skill_detail"]
        for seed in data["seeds"]
        for trial in seed["trials"]
        if trial["outcome"] == "no_skill_called"
    )
    lines += ["", "## No skill called", ""]
    if not details:
        lines.append("None.")
    for name, count in sorted(details.items()):
        lines.append(f"- {name}: {count}")
    lines.append("")
    lines.append("`asked_user` is a heuristic: the last reply ends with a question mark.")
    lines += ["", "## Denied commands", ""]
    if not data["denials"]:
        lines.append("None.")
    for denial in data["denials"]:
        lines.append(f"- `{denial['seed']}` {denial['tool']} ({denial['kind']}): `{denial['detail'][:160]}`")
    harness = [
        (seed["id"], failure)
        for seed in data["seeds"]
        for trial in seed["trials"]
        for failure in trial["harness_failures"]
    ]
    lines += ["", "## Harness failures", ""]
    if not harness:
        lines.append("None.")
    for seed_id, failure in harness:
        lines.append(f"- `{seed_id}`: {failure[:200]}")
    return "\n".join(lines) + "\n"


def write_markdown(report: LiveReport, path: Path) -> None:
    """Write :func:`markdown` of *report* to *path*, parents created."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown(report), encoding="utf-8")


def compare(old: Mapping[str, Any], new: Mapping[str, Any]) -> str:
    """How each seed's pass rate and choices changed from *old* to *new*.

    Both are :func:`to_dict` forms. The first line warns when provider,
    model or base_url differ, since the numbers are then not comparable.
    """
    lines: list[str] = []
    keys = ("provider", "model", "base_url")
    changed = [
        f"{key}: {old['meta'].get(key)!r} -> {new['meta'].get(key)!r}"
        for key in keys
        if old["meta"].get(key) != new["meta"].get(key)
    ]
    if changed:
        lines.append("WARNING: different runs, not comparable: " + "; ".join(changed))
    lines.append(f"overall: {_percent(old.get('pass_rate'))} -> {_percent(new.get('pass_rate'))}")
    before = {seed["id"]: seed for seed in old["seeds"]}
    for seed in new["seeds"]:
        previous = before.pop(seed["id"], None)
        chosen = sorted({trial["chosen"] or "-" for trial in seed["trials"]})
        if previous is None:
            lines.append(f"{seed['id']}: new, {_percent(seed['pass_rate'])}, chose {', '.join(chosen)}")
            continue
        was = sorted({trial["chosen"] or "-" for trial in previous["trials"]})
        mark = "" if previous["pass_rate"] == seed["pass_rate"] and was == chosen else "  *"
        lines.append(
            f"{seed['id']}: {_percent(previous['pass_rate'])} -> {_percent(seed['pass_rate'])}, "
            f"chose {', '.join(was)} -> {', '.join(chosen)}{mark}"
        )
    for seed_id in before:
        lines.append(f"{seed_id}: missing from the new report")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """The ``python -m omicsclaw.evals.live`` command line.

    ``compare <old.json> <new.json>`` prints :func:`compare`. Returns 0,
    or 2 when a report cannot be read.
    """
    parser = argparse.ArgumentParser(prog="python -m omicsclaw.evals.live")
    commands = parser.add_subparsers(dest="command", required=True)
    diff = commands.add_parser("compare", help="compare two live routing reports")
    diff.add_argument("old", type=Path)
    diff.add_argument("new", type=Path)
    args = parser.parse_args(argv)
    try:
        old, new = load_report(args.old), load_report(args.new)
    except (OSError, ValueError) as error:
        print(f"cannot read a report: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(compare(old, new))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
