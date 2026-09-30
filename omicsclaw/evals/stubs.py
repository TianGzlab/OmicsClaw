"""Stubbed skill runs: recorded output replayed in place of a real run.

In the running agent a skill runs as ``bash`` executing
``python <skill directory>/<script>.py ... --output <dir>``. Inside
:func:`stubbed_skill_runs`, the function ``bash`` uses to start a local
process, :func:`omicsclaw.tools.builtin.bash._locally`, is replaced by
one that answers a run of a stubbed skill's script with a
:class:`StubResult` and runs every other command as before. The
permission gate, the hooks, argument validation and approval all happen
before that function is reached, so they behave exactly as in
production.

:func:`record_stub_result` produces a :class:`StubResult` from one real
run in a subprocess, and ``python -m omicsclaw.evals.stubs record`` is
its command line. Nothing here imports a skill's code.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from omicsclaw.skills import Skill, SkillIndex, load_skills
from omicsclaw.tools.builtin import bash as _bash

from .assertions import Failure
from .case import SkillRun

__all__ = [
    "MAX_TEXT_FILE_BYTES",
    "StubResult",
    "find_skill_run",
    "main",
    "normalize",
    "record_stub_result",
    "stubbed_skill_runs",
]

MAX_TEXT_FILE_BYTES = 64 * 1024
"""Output files at most this large are stored verbatim; larger ones by name."""

REPO_ROOT = Path(__file__).resolve().parents[2]

_ISO_TIME = re.compile(
    r"(?<!\d)\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_STAMP = re.compile(r"(?<!\d)\d{8}_\d{6}(?!\d)")
_FIXED_ISO = "2000-01-01T00:00:00"
_FIXED_STAMP = "20000101_000000"
_PYTHON = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")


@dataclass(frozen=True)
class StubResult:
    """What a stubbed run of a skill's script returns.

    :param stdout: The merged stdout and stderr the command prints, with
        ``{output}`` standing for the output directory.
    :param exit_code: The exit status.
    :param files: Text files to write under the output directory,
        relative path to content (``{output}`` expanded on write).
    :param binary_files: Other files, by relative path. Each is written
        as an empty placeholder.
    :param provenance: Where the recording came from: skill, command, git
        commit, date, python and environment name.
    """

    stdout: str
    exit_code: int = 0
    files: Mapping[str, str] = field(default_factory=dict)
    binary_files: tuple[str, ...] = ()
    provenance: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> StubResult:
        """Read a stub from its JSON fixture.

        :raises OSError: the file cannot be read.
        :raises ValueError: the file is not a stub fixture.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            stdout=data["stdout"],
            exit_code=int(data.get("exit_code", 0)),
            files=dict(data.get("files", {})),
            binary_files=tuple(data.get("binary_files", ())),
            provenance=dict(data.get("provenance", {})),
        )

    def dump(self, path: Path) -> None:
        """Write this stub as a JSON fixture, keys sorted, parents created."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provenance": dict(self.provenance),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "files": dict(sorted(self.files.items())),
            "binary_files": sorted(self.binary_files),
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class _Invocation:
    skill: Skill
    script: Path
    output: str | None
    wants_help: bool


def _script_of(tokens: Sequence[str], cwd: Path) -> list[tuple[Path, list[str]]]:
    """Every ``python <script>.py args...`` in *tokens*, with its arguments."""
    found: list[tuple[Path, list[str]]] = []
    executable = os.path.realpath(sys.executable)
    for i, token in enumerate(tokens):
        name = os.path.basename(token)
        is_python = bool(_PYTHON.match(name)) or (
            os.sep in token and os.path.realpath(token) == executable
        )
        if not is_python:
            continue
        j = i + 1
        while j < len(tokens) and tokens[j].startswith("-"):
            j += 1
        if j >= len(tokens) or not tokens[j].endswith(".py"):
            continue
        raw = Path(tokens[j])
        if not raw.is_absolute():
            relative_to_cwd = cwd / raw
            relative_to_repo = REPO_ROOT / raw
            raw = relative_to_cwd if relative_to_cwd.exists() else relative_to_repo
        args: list[str] = []
        for token_after in tokens[j + 1 :]:
            if token_after in ("&&", "||", ";", "|"):
                break
            args.append(token_after)
        found.append((raw, args))
    return found


def _output_of(args: Sequence[str]) -> str | None:
    for k, arg in enumerate(args):
        if arg in ("--output", "-o"):
            return args[k + 1] if k + 1 < len(args) else None
        if arg.startswith("--output="):
            return arg.split("=", 1)[1]
    return None


def find_skill_run(command: str, cwd: Path, index: SkillIndex) -> _Invocation | None:
    """The skill script *command* runs, or ``None`` if it runs none.

    A command runs a skill's script when it invokes ``python`` (or
    ``python3``, ``python3.x`` or the running interpreter) whose first
    positional argument is a ``.py`` file directly inside a skill's
    directory. The path may be absolute, relative to *cwd*, or relative
    to the repository root. Reading ``SKILL.md`` or listing the
    directory does not count.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    by_directory = {skill.directory.resolve(): skill for skill in index.skills}
    for script, args in _script_of(tokens, cwd):
        skill = by_directory.get(script.parent.resolve())
        if skill is None:
            continue
        return _Invocation(
            skill=skill,
            script=script,
            output=_output_of(args),
            wants_help="--help" in args or "-h" in args,
        )
    return None


def _write_stub(stub: StubResult, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for relative, content in stub.files.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.replace("{output}", str(output)), encoding="utf-8")
    for relative in stub.binary_files:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")


@contextmanager
def stubbed_skill_runs(
    stubs: Mapping[str, StubResult],
    index: SkillIndex,
    record: list[SkillRun],
    failures: list[Failure] | None = None,
) -> Iterator[None]:
    """Answer runs of the stubbed skills' scripts from *stubs* inside the block.

    A command that runs a stubbed skill's script, has ``--output`` (or
    ``-o``) and no ``--help``, writes the stub's files into the output
    directory (relative to the command's working directory) and returns
    the stub's output and exit status. With ``--help`` or ``-h`` the
    command runs for real and is not recorded. Every other command runs
    for real too; one that runs any skill's script is recorded with
    ``stubbed=False``.

    :param stubs: Skill name to stub.
    :param index: The skill index the directories come from.
    :param record: Receives one :class:`~omicsclaw.evals.case.SkillRun`
        per skill script command.
    :param failures: Receives a hard ``stub_target_missing`` failure
        when a stubbed skill's script does not exist or the command has
        no ``--output``. The command then returns exit status 2.
    :raises KeyError: a stub names a skill that is not in *index*.
    """
    for name in stubs:
        if index.get(name) is None:
            raise KeyError(f"skill stub for {name!r}, which is not in the skill index")
    original = _bash._locally
    failed = failures if failures is not None else []

    async def locally(command: str, cwd: Path, timeout: float) -> tuple[_bash.CommandOutcome, bool]:
        run = find_skill_run(command, cwd, index)
        if run is None:
            return await original(command, cwd, timeout)
        if run.wants_help:
            return await original(command, cwd, timeout)
        stub = stubs.get(run.skill.name)
        if stub is None:
            record.append(
                SkillRun(run.skill.name, run.skill.domain, command, stubbed=False)
            )
            return await original(command, cwd, timeout)
        if not run.script.is_file():
            message = f"{run.skill.name}: script {run.script} does not exist"
            failed.append(Failure("stub_target_missing", message))
            return _bash.CommandOutcome(output=message, exit_code=2), False
        if not run.output:
            message = f"{run.skill.name}: command has no --output: {command}"
            failed.append(Failure("stub_target_missing", message))
            return _bash.CommandOutcome(output=message, exit_code=2), False
        output = Path(run.output)
        if not output.is_absolute():
            output = cwd / output
        _write_stub(stub, output)
        record.append(SkillRun(run.skill.name, run.skill.domain, command, stubbed=True))
        return (
            _bash.CommandOutcome(
                output=stub.stdout.replace("{output}", str(output)),
                exit_code=stub.exit_code,
            ),
            False,
        )

    _bash._locally = locally  # type: ignore[assignment]
    try:
        yield
    finally:
        _bash._locally = original  # type: ignore[assignment]


def normalize(
    text: str,
    *,
    output: Path,
    home: Path | None = None,
    python_prefix: Path | None = None,
    tmp: Path | None = None,
) -> str:
    """Make recorded text independent of where and when it was recorded.

    Replaces the output directory, the repository root, ``HOME``, the
    recording interpreter's prefix and the system temporary directory
    with ``{output}``, ``{repo}``, ``{home}``, ``{python_prefix}`` and
    ``{tmp}``, longest path first, and ISO timestamps and
    ``YYYYMMDD_HHMMSS`` stamps with fixed values.

    :param text: The text to normalize.
    :param output: The output directory of the run.
    :param home: ``HOME``. ``None`` is the current user's.
    :param python_prefix: The interpreter's environment directory.
        ``None`` leaves it alone.
    :param tmp: The temporary directory. ``None`` leaves it alone.
    """
    replacements = [(str(output.resolve()), "{output}"), (str(output), "{output}")]
    replacements.append((str(REPO_ROOT), "{repo}"))
    home_dir = home if home is not None else Path.home()
    replacements.append((str(home_dir), "{home}"))
    if python_prefix is not None:
        replacements.append((str(python_prefix), "{python_prefix}"))
    if tmp is not None:
        replacements.append((str(tmp), "{tmp}"))
        replacements.append((str(tmp.resolve()), "{tmp}"))
    for old, new in sorted(set(replacements), key=lambda pair: -len(pair[0])):
        if old and old != os.sep:
            text = text.replace(old, new)
    text = _ISO_TIME.sub(_FIXED_ISO, text)
    return _STAMP.sub(_FIXED_STAMP, text)


def _script_for(skill: Skill, script: str | None) -> Path:
    if script is not None:
        return skill.directory / script
    candidates = sorted(
        path
        for path in skill.directory.glob("*.py")
        if not path.name.startswith(("_", "test_"))
    )
    if len(candidates) != 1:
        raise ValueError(
            f"{skill.name} has {len(candidates)} top-level scripts; name one with --script"
        )
    return candidates[0]


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def record_stub_result(
    skill: str,
    args: Sequence[str],
    *,
    python: str,
    out: Path,
    script: str | None = None,
    skills_root: Path | None = None,
    timeout: float = 1800.0,
) -> StubResult:
    """Run *skill*'s script once for real and save what it produced as a stub.

    Runs ``<python> <script> <args> --output <tmp>`` in a temporary
    directory, merges stdout and stderr, truncates them the way ``bash``
    does, keeps text files of at most :data:`MAX_TEXT_FILE_BYTES` from
    the output directory verbatim and lists the rest by name, normalizes
    paths and timestamps with :func:`normalize`, and writes the result to
    *out*.

    :param skill: The skill name.
    :param args: Arguments for the script, without ``--output``.
    :param python: The interpreter to run it with.
    :param out: Where to write the JSON fixture.
    :param script: The script file name inside the skill directory.
        ``None`` takes the directory's only top-level script.
    :param skills_root: The skills directory. ``None`` is the
        repository's ``skills/``.
    :param timeout: Seconds before the run is abandoned.
    :returns: The recorded stub.
    :raises KeyError: *skill* is not in the index.
    :raises ValueError: the script cannot be chosen.
    :raises subprocess.TimeoutExpired: the run took longer than *timeout*.
    """
    index = load_skills(skills_root if skills_root is not None else REPO_ROOT / "skills")
    found = index.get(skill)
    if found is None:
        raise KeyError(f"{skill!r} is not in the skill index")
    path = _script_for(found, script)
    with tempfile.TemporaryDirectory(prefix="omicsclaw-stub-") as scratch:
        workdir = Path(scratch)
        output = workdir / "output"
        command = [python, str(path), *args, "--output", str(output)]
        completed = subprocess.run(
            command,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        prefix = Path(python).resolve().parents[1]
        system_tmp = Path(tempfile.gettempdir())

        def clean(text: str) -> str:
            return normalize(text, output=output, python_prefix=prefix, tmp=system_tmp)

        stdout = _bash._truncate(clean(completed.stdout))
        files: dict[str, str] = {}
        binary: list[str] = []
        if output.is_dir():
            for item in sorted(output.rglob("*")):
                if not item.is_file():
                    continue
                relative = item.relative_to(output).as_posix()
                if item.stat().st_size <= MAX_TEXT_FILE_BYTES:
                    try:
                        text = item.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        binary.append(relative)
                        continue
                    files[relative] = clean(text)
                else:
                    binary.append(relative)
        shown = " ".join(
            shlex.quote(part)
            for part in ["python", f"{{repo}}/{path.relative_to(REPO_ROOT).as_posix()}", *args, "--output", "{output}"]
        )
    stub = StubResult(
        stdout=stdout,
        exit_code=completed.returncode,
        files=files,
        binary_files=tuple(binary),
        provenance={
            "skill": skill,
            "command": shown,
            "git_commit": _git_commit(),
            "date": _dt.date.today().isoformat(),
            "python": sys.version.split()[0] if python == sys.executable else _python_version(python),
            "environment": Path(python).resolve().parents[1].name,
        },
    )
    stub.dump(out)
    return stub


def _python_version(python: str) -> str:
    try:
        return subprocess.run(
            [python, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main(argv: Sequence[str] | None = None) -> int:
    """The ``python -m omicsclaw.evals.stubs`` command line.

    ``record <skill> [script args...] --out <fixture.json>`` records one
    stub. Returns the process exit status.
    """
    parser = argparse.ArgumentParser(prog="python -m omicsclaw.evals.stubs")
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record", help="record a stub from one real run")
    rec.add_argument("skill")
    rec.add_argument("--out", required=True, type=Path)
    rec.add_argument("--python", default=sys.executable)
    rec.add_argument("--script", default=None)
    rec.add_argument("--timeout", type=float, default=1800.0)
    known, rest = parser.parse_known_args(argv)
    stub = record_stub_result(
        known.skill,
        rest,
        python=known.python,
        out=known.out,
        script=known.script,
        timeout=known.timeout,
    )
    print(f"recorded {known.skill}: exit {stub.exit_code}, {len(stub.files)} text file(s), "
          f"{len(stub.binary_files)} other file(s) -> {known.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
