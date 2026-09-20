"""``oc cli`` — the command, and its command line.

Migrated from ``tests/entry/test_cli_main.py`` when plan 0037 moved the
process out of ``omicsclaw/entry/cli/`` and into
:mod:`omicsclaw.launch`. Responsibility moved, so its tests moved with
it —— step 6's third recorded lesson was a trap whose responsibility
moved while its tests stayed behind, leaving the only Protocol an
external implementer touches with no guard at all.

Plan 0031 §9-10 asks for one runnable command on delivery day: a
subprocess, fed one line, printing a model's answer.
:func:`test_the_command_answers_one_line_from_a_pipe` is that test, and
it runs the **literal** command —— not a function called ``main`` ——
because the thing being accepted is a command.

**How a backend is substituted without a network or a vendor SDK.**
Neither ``openai`` nor ``anthropic`` is installed here and there is no
network, so the real provider path cannot run at all. A
``sitecustomize`` module on ``PYTHONPATH`` is imported by :mod:`site`
before anything else and replaces
``omicsclaw.entry.assembly.provider_from_env`` with a scripted one.
Nothing in the shipped code reads an environment variable to find a
provider, so the substitution happens outside the program rather than
through a back door inside it.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfigError
from omicsclaw.launch import main
from omicsclaw.launch._surfaces import ReplOptions
from omicsclaw.schema import Message, Role
from tests.entry.test_assembly import (  # type: ignore[import-not-found]
    _PROVIDER_SURFACE,
    _declared_as_interface,
    provider_doubles,
)
from tests.entry.test_turn_runner import Scripted  # type: ignore[import-not-found]

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_SITECUSTOMIZE = '''\
"""Substitute the backend before the command starts (see the test)."""
import sys

sys.path.insert(0, {root!r})

from omicsclaw.entry import assembly
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, StreamChunk, StreamChunkType

ANSWER = {answer!r}


class Scripted:
    name = "scripted"

    async def generate(self, messages, tools=None):
        return Completion(message=Message(role=Role.ASSISTANT, content=ANSWER))

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        yield StreamChunk(
            type=StreamChunkType.TEXT_DELTA, delta=completion.message.content
        )
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides):
        return self


assembly.provider_from_env = lambda *a, **k: Scripted()
'''


def scripted_environment(tmp_path: pathlib.Path, answer: str) -> dict[str, str]:
    """A ``PYTHONPATH`` whose ``sitecustomize`` scripts the backend."""
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(
        _SITECUSTOMIZE.format(root=str(_REPO_ROOT), answer=answer), encoding="utf-8"
    )
    return {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(shim),
        "HOME": str(tmp_path),
        "LANG": "C.UTF-8",
    }


def run_command(
    tmp_path: pathlib.Path,
    arguments: list[str],
    *,
    answer: str = "Moran's I measures spatial autocorrelation.",
    stdin: str = "",
) -> subprocess.CompletedProcess[str]:
    """``python -m omicsclaw.launch cli …`` in a subprocess.

    The module is the shell, not the surface: after plan 0037 there is
    no ``python -m omicsclaw.entry.cli`` and no alias for it.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "omicsclaw.launch",
            "cli",
            "--workspace",
            str(workspace),
        ]
        + arguments,
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=scripted_environment(tmp_path, answer),
        timeout=180,
    )


# ---- acceptance: a real process, plan 0031 §9-10 / plan 0037 §8-4 -----


def test_the_command_answers_one_line_from_a_pipe(tmp_path):
    """The command, one line in, an answer out.

    Standard input is a pipe rather than a terminal, so
    :func:`~omicsclaw.entry.cli._input.open_prompt_source` takes the
    ``StreamSource`` branch —— the same test the harness makes at
    ``main.go:453-468`` before choosing between its interactive and
    non-interactive paths —— and the loop ends at EOF rather than
    hanging.
    """
    result = run_command(tmp_path, [], stdin="what is spatial autocorrelation?\n")

    assert result.returncode == 0, result.stderr
    assert "Moran's I measures spatial autocorrelation." in result.stdout


def _bare_environment(tmp_path: pathlib.Path) -> dict[str, str]:
    """No shim, and no credential of any kind.

    Built explicitly rather than inherited: a machine that happens to
    export ``LLM_API_KEY`` would otherwise make the two tests below say
    nothing —— or reach the network from a test suite.
    """
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "LANG": "C.UTF-8",
    }


def _run_without_a_backend(
    tmp_path: pathlib.Path, arguments: list[str], stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, "-m", "omicsclaw.launch", "cli", "--workspace",
         str(workspace)] + arguments,
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=_bare_environment(tmp_path),
        timeout=180,
    )


def test_the_repl_survives_a_backend_it_cannot_reach(tmp_path):
    """Plan 0037 §8-4 (a): the failure a first-time user meets.

    There is no API key and no network here, so the exchange cannot
    succeed —— and that is the point. What is being accepted is that the
    *command* is sound when the *deployment* is not: the banner prints,
    the exchange reports ``ProviderError`` in one line, the loop reaches
    end of input and exits ``0``, and at no point does a Python
    traceback with this machine's paths in it reach the user.

    ``0`` and not ``1``: the REPL ran and ended the way a REPL ends. A
    failed exchange inside a session is not a failed session —— the
    one-shot path below is where a failure is the outcome.
    """
    result = _run_without_a_backend(tmp_path, [], stdin="hello\n")
    printed = result.stdout + result.stderr

    assert result.returncode == 0, printed
    assert "ProviderError" in printed
    assert "Goodbye!" in printed
    assert "Traceback" not in printed


def test_one_exchange_that_cannot_run_is_a_failed_exchange(tmp_path):
    """Plan 0037 §8-4 (a), the other half: ``--prompt`` reports ``1``.

    A pipeline that runs ``oc cli -- --prompt-file brief.md`` has to be
    able to tell "the model answered" from "nothing reached a model",
    and the only channel it has is the exit code.
    """
    result = _run_without_a_backend(tmp_path, ["--", "--prompt", "hello"])
    printed = result.stdout + result.stderr

    assert result.returncode == 1, printed
    assert "ProviderError" in printed
    assert "Traceback" not in printed


def test_the_whole_prompt_file_is_one_exchange(tmp_path):
    """``cli.go:27-33``'s reason, checked rather than repeated.

    The comment there says a multi-line instruction must not be split
    into several independent turns. Four lines produce **one** call
    carrying **one** user message, and that message still contains the
    fourth line.
    """
    brief = tmp_path / "brief.md"
    brief.write_text(
        "Load the Visium slide at /data/s1.h5ad.\n"
        "Run QC with the default thresholds.\n"
        "Then find spatial domains.\n"
        "Report the marker genes per domain.\n",
        encoding="utf-8",
    )
    provider = Scripted(Message(role=Role.ASSISTANT, content="understood"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    real = assembly.provider_from_env
    assembly.provider_from_env = lambda *a, **k: provider
    try:
        code = main(
            [
                "cli",
                "--workspace",
                str(workspace),
                "--",
                "--prompt-file",
                str(brief),
            ],
            {},
        )
    finally:
        assembly.provider_from_env = real

    assert code == 0
    assert provider.calls == 1
    sent = provider.seen[0]
    users = [message for message in sent if message.role is Role.USER]
    assert len(users) == 1
    assert "Report the marker genes per domain." in users[0].content


def test_the_shim_backend_is_no_wider_than_the_provider_protocol():
    """Why :func:`test_the_command_answers_one_line_from_a_pipe` was blind.

    The shim is the only double that drives the **literal** command, so
    a member it publishes and :class:`~omicsclaw.provider.LLMProvider`
    does not is a crash the acceptance test cannot see. It published
    ``model``; the banner read ``provider.model``; the command died on
    its first line with 591 tests green. ``test_assembly.py`` makes the
    same check over the doubles that are ordinary classes.
    """
    source = _SITECUSTOMIZE.format(root="/repo", answer="ok")
    doubles = provider_doubles(source, "sitecustomize.py")

    assert doubles, "the shim no longer defines a provider double"
    for node in doubles:
        extra = set(_declared_as_interface(node)) - _PROVIDER_SURFACE
        assert not extra, f"{node.name} declares {sorted(extra)}"


def test_an_empty_prompt_file_is_refused_rather_than_sent(tmp_path):
    """Submitting nothing costs a model call to be told nothing was asked."""
    empty = tmp_path / "empty.md"
    empty.write_text("   \n", encoding="utf-8")

    with pytest.raises(AppConfigError, match="is empty"):
        ReplOptions.parse(["--prompt-file", str(empty)])


# ---- the argv convention (plan 0031 Q8, plan 0037 §5.2) ---------------


def test_a_surface_flag_before_the_terminator_is_refused(tmp_path):
    """The rule that makes a typo loud.

    ``resolve_app_config`` refuses an unknown flag rather than ignoring
    it, and its message names the terminator —— so the fix is in the
    error the user already has in front of them.
    """
    result = run_command(tmp_path, ["--session", "run-7"])

    assert result.returncode == 2
    assert "pass a surface's own flags after" in result.stderr


def test_an_unknown_surface_flag_is_refused_too(tmp_path):
    """Strict on both sides of ``--``, and one message shape for both."""
    result = run_command(tmp_path, ["--", "--sesion", "run-7"])

    assert result.returncode == 2
    assert "unknown surface option" in result.stderr
    assert "usage:" in result.stderr


@pytest.mark.parametrize(
    "arguments, attribute, expected",
    [
        (["--session", "run-7"], "session_id", "run-7"),
        (["--prompt", "hello"], "prompt", "hello"),
        (["--show-reasoning"], "show_reasoning", True),
        (["--help"], "help", True),
    ],
)
def test_each_surface_flag_lands_where_it_says(arguments, attribute, expected):
    assert getattr(ReplOptions.parse(arguments), attribute) == expected


def test_a_surface_flag_without_its_value_is_refused():
    with pytest.raises(AppConfigError, match="needs a value"):
        ReplOptions.parse(["--session"])


def test_help_prints_the_usage_and_starts_nothing(tmp_path):
    """No app is assembled, so no backend is needed to read ``--help``."""
    result = run_command(tmp_path, ["--", "--help"])

    assert result.returncode == 0
    assert "usage: oc cli" in result.stdout
    assert "is a deployment flag" in result.stdout
    assert "--system-prompt-file" in result.stdout


def test_help_needs_no_terminator(tmp_path):
    """``oc cli --help`` and ``oc cli -- --help`` are the same question.

    Plan 0037 §5.2 sends everything left of ``--`` to
    ``resolve_app_config``, which would refuse ``--help`` as an unknown
    deployment flag. Hoisting it (``_grammar.split_command_line``) is
    what keeps the obvious spelling working, and this is the test that
    notices if the hoist is dropped —— the failure would otherwise be a
    usage error printed *instead of* the usage.
    """
    result = run_command(tmp_path, ["--help"])

    assert result.returncode == 0, result.stderr
    assert "usage: oc cli" in result.stdout
