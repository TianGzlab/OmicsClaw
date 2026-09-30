"""``oc cli -- --configure`` —— the command, run as a command.

Plan 0037 §8-4's rule applied to the setup wizard: *a launch arrangement's
acceptance can only be given by a real process.* Step 6's most expensive
lesson was 619 green tests over a command that crashed on its first line,
because the double was wider than the protocol. A wizard is exactly the
shape of thing that invites the same mistake —— its library is easy to
drive with a fake prompter, and the question being accepted is whether
the **process** reads a pipe, writes the file the shell will load, and
never prints a secret.

**The repository's own ``.env`` is at risk here and is guarded.** This
checkout has a real one with a real key in it, and the file the wizard
writes is chosen by searching for it. Every subprocess below therefore
runs with ``OMICSCLAW_DIR`` and its working directory pointing into
``tmp_path`` —— and :func:`test_the_repository_dotenv_is_never_touched`
checksums the real file around a run rather than trusting that.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
import time

import pytest

from omicsclaw.entry.config import AppConfigError
from omicsclaw.launch import dotenv_candidates, dotenv_target
from omicsclaw.launch._surfaces import ReplOptions, _report_a_missing_credential

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_ANSWERS = [
    "deepseek",  # provider
    "sk-secret-value-1234",  # api key
    "",  # model: the preset default
    "",  # base URL: the preset's own
    "",  # workspace: the default offered
    "n",  # telegram
    "n",  # feishu
    "n",  # desktop bearer token
    "y",  # save
]

_EXISTING = """\
# a comment the wizard has no opinion about
UNKNOWN_KEY=leave-me-alone
LLM_PROVIDER=openai
"""


def configure(
    tmp_path: pathlib.Path,
    answers: list[str],
    arguments: list[str] | None = None,
    *,
    terminator: bool = True,
) -> subprocess.CompletedProcess[str]:
    """``python -m omicsclaw.launch cli -- --configure`` over a pipe.

    ``OMICSCLAW_DIR`` and ``cwd`` are both *tmp_path* so that the two
    candidates :func:`omicsclaw.launch.dotenv_candidates` produces
    collapse onto one file inside the sandbox. ``PYTHONPATH`` carries the
    checkout because the working directory can no longer do it.

    *terminator* picks which of the two spellings to run. Both have to
    reach the same wizard (plan 0048), and the tests that are about the
    wizard rather than about the command line keep the explicit one.
    """
    return subprocess.run(
        [sys.executable, "-m", "omicsclaw.launch", "cli"]
        + (["--"] if terminator else [])
        + (arguments if arguments is not None else ["--configure"]),
        input="".join(f"{line}\n" for line in answers),
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(_REPO_ROOT),
            "HOME": str(tmp_path),
            "LANG": "C.UTF-8",
            "OMICSCLAW_DIR": str(tmp_path),
        },
        timeout=120,
    )


def _values(path: pathlib.Path) -> dict[str, str]:
    saved: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            saved[key.strip()] = value.strip()
    return saved


# ---- acceptance: the real process -------------------------------------


def test_the_command_writes_the_answers_to_the_file_the_shell_reads(tmp_path):
    started = time.monotonic()
    result = configure(tmp_path, _ANSWERS)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 120
    written = tmp_path / ".env"
    assert written.is_file()
    assert _values(written) == {
        "LLM_PROVIDER": "deepseek",
        "LLM_API_KEY": "sk-secret-value-1234",
        "LLM_MODEL": "deepseek-v4-flash",
        "LLM_BASE_URL": "",
        "OMICSCLAW_WORKSPACE": str(tmp_path),
    }


def test_the_file_it_wrote_is_the_file_the_shell_would_load(tmp_path):
    """The two halves of plan 0037's R3 agree, asserted rather than assumed.

    ``_adopt_dotenv`` and the wizard take their answer from one function;
    this is the assertion that says so from outside, by asking the shell
    where it would read and comparing that with what appeared on disk.
    """
    configure(tmp_path, _ANSWERS)

    target = dotenv_target(root=tmp_path, cwd=tmp_path)

    assert target == tmp_path / ".env"
    assert target.is_file()
    assert dotenv_candidates(root=tmp_path, cwd=tmp_path) == (target,)


def test_it_updates_the_file_the_shell_would_load_and_not_the_nearer_one(tmp_path):
    """The two candidates differ, and only one of them is the live file.

    ``OMICSCLAW_DIR`` points at a directory that already has a ``.env``
    while the process runs somewhere else. The shell loads the project
    root first with ``override=False``, so that file is the one whose
    values win —— and a wizard that wrote a *new* ``.env`` in the working
    directory would produce a save that appears to work and is shadowed
    on the next start-up. This is the "configured one file, read another"
    failure written as a test.
    """
    root = tmp_path / "project"
    here = tmp_path / "elsewhere"
    root.mkdir()
    here.mkdir()
    (root / ".env").write_text(_EXISTING, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "omicsclaw.launch", "cli", "--", "--configure"],
        input="".join(f"{line}\n" for line in _ANSWERS),
        capture_output=True,
        text=True,
        cwd=str(here),
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(_REPO_ROOT),
            "HOME": str(tmp_path),
            "LANG": "C.UTF-8",
            "OMICSCLAW_DIR": str(root),
        },
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert not (here / ".env").exists()
    assert _values(root / ".env")["LLM_PROVIDER"] == "deepseek"
    assert "UNKNOWN_KEY=leave-me-alone" in (root / ".env").read_text(encoding="utf-8")


def test_the_target_is_the_file_that_exists_and_not_always_the_first(tmp_path):
    """Because the first file to name a variable is the one that decides it.

    Writing to the project root while the working directory holds the
    only ``.env`` would create a second file rather than change the live
    one; writing to the working directory while the project root has one
    would be overridden by it.
    """
    root = tmp_path / "project"
    here = tmp_path / "elsewhere"
    root.mkdir()
    here.mkdir()
    (here / ".env").write_text("X=1\n", encoding="utf-8")

    assert dotenv_target(root=root, cwd=here) == here / ".env"

    (root / ".env").write_text("X=2\n", encoding="utf-8")

    assert dotenv_target(root=root, cwd=here) == root / ".env"


def test_with_no_file_anywhere_one_is_created_at_the_project_root(tmp_path):
    """``.env.example`` documents the repository's ``.env``, so that is where
    a first run puts one rather than wherever the user was standing."""
    root = tmp_path / "project"
    here = tmp_path / "elsewhere"
    root.mkdir()
    here.mkdir()

    assert dotenv_target(root=root, cwd=here) == root / ".env"


def test_the_terminal_never_shows_the_secret_that_was_typed(tmp_path):
    """``SAFETY_RULES`` rule 1, over a real terminal session.

    Not the same assertion as the library's: this one covers the process
    as a whole, including anything the logging path or an unhandled
    exception would have added.
    """
    result = configure(tmp_path, _ANSWERS)
    printed = result.stdout + result.stderr

    assert "sk-secret-value-1234" not in printed
    assert "…1234" in printed
    assert "Traceback" not in printed


def test_a_secret_already_on_disk_is_not_read_back_out_loud(tmp_path):
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=deepseek\nLLM_API_KEY=sk-already-stored-5678\n", encoding="utf-8"
    )

    result = configure(tmp_path, ["deepseek", "", "", "", "", "n", "n", "n", "y"])
    printed = result.stdout + result.stderr

    assert result.returncode == 0, result.stderr
    assert "sk-already-stored-5678" not in printed
    assert "…5678" in printed
    assert _values(tmp_path / ".env")["LLM_API_KEY"] == "sk-already-stored-5678"


def test_an_existing_file_keeps_its_comments_and_gains_a_backup(tmp_path):
    (tmp_path / ".env").write_text(_EXISTING, encoding="utf-8")

    result = configure(tmp_path, _ANSWERS)
    saved = (tmp_path / ".env").read_text(encoding="utf-8")
    backups = sorted(tmp_path.glob(".env.backup-*"))

    assert result.returncode == 0, result.stderr
    assert "# a comment the wizard has no opinion about" in saved
    assert "UNKNOWN_KEY=leave-me-alone" in saved
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == _EXISTING
    assert not list(tmp_path.glob("*.partial"))


def test_input_that_ends_early_writes_nothing_and_does_not_hang(tmp_path):
    """A pipe that runs out mid-question is abandonment, not a hang.

    The bound is the subprocess timeout above: a wizard that waited on a
    closed stream would be killed by it rather than reported by an
    assertion, which is the only way to write this criterion on a machine
    with no ``pytest-timeout``.
    """
    (tmp_path / ".env").write_text(_EXISTING, encoding="utf-8")

    result = configure(tmp_path, ["deepseek"])

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert (tmp_path / ".env").read_text(encoding="utf-8") == _EXISTING
    assert not list(tmp_path.glob(".env.backup-*"))


def test_the_repository_dotenv_is_never_touched(tmp_path):
    """The guard for the risk this whole file runs.

    The wizard finds its file by searching, and one of the places it
    searches is this checkout —— which has a real ``.env`` with a real
    key. If the sandboxing above ever stops working, this is the test
    that says so instead of the owner's credentials being rewritten.
    """
    live = _REPO_ROOT / ".env"
    before = hashlib.md5(live.read_bytes()).hexdigest() if live.exists() else None
    backups = set(_REPO_ROOT.glob(".env.backup-*"))

    configure(tmp_path, _ANSWERS)

    after = hashlib.md5(live.read_bytes()).hexdigest() if live.exists() else None
    assert after == before
    assert set(_REPO_ROOT.glob(".env.backup-*")) == backups
    assert not list(_REPO_ROOT.glob("*.partial"))


# ---- the flag is a surface flag, on either side of the terminator ----


def test_the_flag_needs_no_terminator(tmp_path):
    """``oc cli --configure`` is the same command as ``oc cli -- --configure``.

    It used to be a usage error —— refused by ``resolve_app_config`` as
    an unknown *deployment* flag, and then answered with the surface
    usage that lists ``--configure`` two lines further down. The reader
    of that screen was told the flag does not exist and shown that it
    does.

    Plan 0048's fix is not an exception to the cut in
    ``split_command_line`` (which is unchanged) but a statement about
    ownership: ``start_cli`` claims its own flags from the deployment
    half, and the two flag families are disjoint, so nothing that
    ``resolve_app_config`` wanted can be taken.
    """
    result = configure(tmp_path, _ANSWERS, terminator=False)

    assert result.returncode == 0, result.stderr
    assert _values(tmp_path / ".env")["LLM_API_KEY"] == "sk-secret-value-1234"


def test_both_spellings_reach_the_same_wizard(tmp_path):
    """The old spelling keeps working, to the byte."""
    result = configure(tmp_path, _ANSWERS)

    assert result.returncode == 0, result.stderr
    assert _values(tmp_path / ".env")["LLM_API_KEY"] == "sk-secret-value-1234"


def test_the_surface_usage_lists_it(tmp_path):
    result = configure(tmp_path, [], arguments=["--help"])

    assert result.returncode == 0
    assert "--configure" in result.stdout


@pytest.mark.parametrize("flag", ["--prompt", "--prompt-file", "--session"])
def test_configuring_and_running_an_exchange_are_refused_together(flag, tmp_path):
    """It starts no agent, so there is nothing for the other three to act on.

    Silently ignoring one of them is the shape of defect plan 0037's
    review found in ``--session`` beside ``--prompt``: a flag that is
    accepted and does nothing.

    ``--prompt-file`` is given a real, non-empty file on purpose —— it is
    read during parsing, so pointing it at an empty one would produce a
    *different* refusal and this test would pass without ever reaching
    the rule it is named after.
    """
    brief = tmp_path / "brief.md"
    brief.write_text("summarise this\n", encoding="utf-8")
    value = str(brief) if flag == "--prompt-file" else "something"

    with pytest.raises(AppConfigError) as refusal:
        ReplOptions.parse(["--configure", flag, value])

    assert "--configure" in str(refusal.value)


def test_the_flag_is_off_unless_it_is_given():
    assert ReplOptions.parse([]).configure is False
    assert ReplOptions.parse(["--configure"]).configure is True


# ---- the hint that makes the flag findable ----------------------------


def _start_repl(
    tmp_path: pathlib.Path, dotenv: str
) -> subprocess.CompletedProcess[str]:
    """``oc cli`` with one line of input and no backend it can reach."""
    (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    return subprocess.run(
        [
            sys.executable, "-m", "omicsclaw.launch", "cli",
            "--workspace", str(workspace),
        ],
        input="hello\n",
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(_REPO_ROOT),
            "HOME": str(tmp_path),
            "LANG": "C.UTF-8",
            "OMICSCLAW_DIR": str(tmp_path),
        },
        timeout=180,
    )


def test_a_first_run_with_no_key_is_told_what_to_type(tmp_path):
    """A first run cannot guess a flag it has never read about.

    A user who has never read the usage cannot guess the flag, and the
    deployment that most needs it is the one that has nothing configured
    —— so that deployment is handed the whole command, on stderr, before
    it spends several seconds failing to reach a model.
    """
    result = _start_repl(tmp_path, "# nothing configured\n")

    assert "oc cli --configure" in result.stderr


def test_a_configured_deployment_is_not_nagged(tmp_path):
    """A hint that fires when it does not apply is how hints stop being read."""
    result = _start_repl(tmp_path, "LLM_PROVIDER=deepseek\nLLM_API_KEY=sk-x\n")

    assert "--configure" not in result.stderr


def test_the_hint_is_one_line_on_stderr_or_nothing_at_all(capsys):
    """The silence is asserted as well as the line.

    A hint fires **at most** once and only when it applies; the count is
    returned so that "it printed nothing" is an assertion rather than the
    absence of one.
    """
    assert _report_a_missing_credential({}) == 1
    assert "oc cli --configure" in capsys.readouterr().err

    assert _report_a_missing_credential({"LLM_API_KEY": "sk-x"}) == 0
    assert capsys.readouterr().err == ""
