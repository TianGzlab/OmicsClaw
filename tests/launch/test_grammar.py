"""Three commands, one cut, and an inventory that costs something to grow.

Plan 0037 judgement 4 —— one family of entry points, and an enumerable
one —— and its acceptance §8-7. Two halves:

*The table is the inventory.* :data:`~omicsclaw.launch._grammar.COMMANDS`
has exactly three keys, each naming a subpackage of ``omicsclaw.entry``.

*The tree agrees with the table.* Module guards under ``omicsclaw/`` and
``[project.scripts]`` in ``pyproject.toml`` are both checked against a
named constant, so a fourth way into the program cannot arrive by
accident —— it has to make one of these tests red first.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
import tomllib

import pytest

from omicsclaw.launch import COMMANDS, main, usage
from omicsclaw.launch._grammar import HELP_FLAGS, TERMINATOR, split_command_line

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "omicsclaw"

SURFACES = frozenset({"cli", "desktop", "channel"})
"""The owner's ruling of 2026-09-20, as a constant a test can compare to.

``oc run <skill>`` is not here and is not coming back as a command:
deterministic skill execution is what the agent does in a session and
what an in-surface command asks for (plan 0037 §5.3).
"""


# ---- the table --------------------------------------------------------


def test_the_entry_points_are_exactly_three():
    assert set(COMMANDS) == SURFACES


def test_every_command_names_a_subpackage_of_the_entry_layer():
    """The command name *is* the subpackage name, checked not trusted."""
    for name, command in COMMANDS.items():
        assert command.name == name
        assert command.module == f"omicsclaw.entry.{name}"
        assert (_PACKAGE / "entry" / name / "__init__.py").is_file()


def test_the_table_cannot_be_grown_at_import_time():
    """A mutable inventory is not an inventory.

    The point of the constant is that a fourth entry point costs an edit
    to this file and a red test; a plain ``dict`` would let any imported
    module add one without either.
    """
    with pytest.raises(TypeError):
        COMMANDS["tui"] = COMMANDS["cli"]  # type: ignore[index]


def test_the_top_level_usage_names_every_command():
    text = usage()

    for name in SURFACES:
        assert f" {name} " in text or f" {name:9s}" in text


# ---- the cut ----------------------------------------------------------


def test_the_command_line_is_cut_at_the_terminator():
    """Q8: one reader for the deployment, the surface for its own flags."""
    deployment, surface = split_command_line(
        ["--workspace", "/data", "--", "--session", "run-7"]
    )

    assert deployment == ["--workspace", "/data"]
    assert surface == ["--session", "run-7"]


def test_a_command_line_with_no_terminator_is_all_deployment():
    deployment, surface = split_command_line(["--model", "deepseek-chat"])

    assert deployment == ["--model", "deepseek-chat"]
    assert surface == []


@pytest.mark.parametrize("flag", sorted(HELP_FLAGS))
def test_a_help_flag_on_the_deployment_side_is_hoisted(flag):
    """Once the command name is fixed there is one thing help can mean.

    The deployment half is handed to ``resolve_app_config``, which
    refuses unknown flags —— so without the hoist ``oc cli --help``
    would answer with a *usage error* rather than the usage.
    """
    deployment, surface = split_command_line(["--workspace", "/data", flag])

    assert deployment == ["--workspace", "/data"]
    assert surface == [flag]


@pytest.mark.parametrize("flag", sorted(HELP_FLAGS))
def test_a_help_flag_that_is_a_value_is_not_hoisted(flag):
    """The hoist used to eat the value of the flag in front of it.

    ``oc cli --workspace --help /data`` lifted the ``--help`` out of the
    deployment half, leaving ``--workspace /data`` —— a *different,
    well-formed* deployment plus a help screen, from a command line that
    is not well formed at all. Nothing downstream could notice, because
    what reached ``resolve_app_config`` was valid.

    What happens instead is that the line is refused: ``--workspace``
    takes ``--help`` as its value and ``/data`` is then an unknown
    option. Loud, and the right kind of loud.
    """
    deployment, surface = split_command_line(["--workspace", flag, "/data"])

    assert deployment == ["--workspace", flag, "/data"]
    assert surface == []


@pytest.mark.parametrize("flag", sorted(HELP_FLAGS))
def test_a_help_flag_after_a_complete_pair_is_still_hoisted(flag):
    """The stride has to keep working, or the fix would be "never hoist"."""
    deployment, surface = split_command_line(["--workspace", "/data", flag])

    assert deployment == ["--workspace", "/data"]
    assert surface == [flag]


@pytest.mark.parametrize("flag", sorted(HELP_FLAGS))
def test_the_inline_spelling_advances_one_token_not_two(flag):
    """``--flag=value`` carries its own value, so the next token is a flag."""
    deployment, surface = split_command_line(["--workspace=/data", flag])

    assert deployment == ["--workspace=/data"]
    assert surface == [flag]


@pytest.mark.parametrize("flag", sorted(HELP_FLAGS))
def test_an_empty_inline_value_is_not_a_value(flag):
    """``--workspace=`` goes on to eat the next token, so this is not a hoist.

    The case the test above cannot see. ``config.py``'s ``_from_argv``
    reads an inline value only when there is one after the ``=``; the
    hoist used to ask whether the token *contained* an ``=``, and the two
    then disagreed about exactly this line —— the shell printing a help
    screen for a deployment ``resolve_app_config`` was reading as a
    workspace named ``--help``. Both now walk
    ``_surfaces.flag_stride``.
    """
    deployment, surface = split_command_line(["--workspace=", flag])

    assert deployment == ["--workspace=", flag]
    assert surface == []


def test_only_the_first_terminator_cuts():
    """A surface is allowed to have a ``--`` of its own inside its half."""
    deployment, surface = split_command_line(["--", "--prompt", "--", "x"])

    assert deployment == []
    assert surface == ["--prompt", TERMINATOR, "x"]


# ---- the shell's own answers ------------------------------------------


def test_no_arguments_prints_the_usage_and_refuses(capsys):
    """Both halves, because the name promised both and only checked one.

    These two tests said "prints the usage" and asserted a return value,
    so deleting the ``print`` in ``__init__.py`` left them green —— a
    user typing ``oc`` would have got a silent ``2``. A usage that is
    not printed is the whole of what these commands do.
    """
    code = main([], {})

    assert code == 2
    assert "usage: oc <surface>" in capsys.readouterr().err


def test_an_unknown_command_is_refused(capsys):
    code = main(["tui"], {})
    captured = capsys.readouterr()

    assert code == 2
    assert "unknown command 'tui'" in captured.err
    assert "usage: oc <surface>" in captured.err


@pytest.mark.parametrize("word", ["help", "--help", "-h"])
def test_the_bare_help_word_is_answered(word, capsys):
    """And answered on stdout, which is where a thing that was asked for goes."""
    code = main([word], {})
    captured = capsys.readouterr()

    assert code == 0
    assert "usage: oc <surface>" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, "FEISHU_APP_ID and FEISHU_APP_SECRET"),
        ({"FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "s"}, "ALLOWED_SENDERS"),
        (
            {
                "FEISHU_APP_ID": "a",
                "FEISHU_APP_SECRET": "s",
                "FEISHU_ALLOWED_SENDERS": "ou_owner",
            },
            "FEISHU_BOT_OPEN_ID",
        ),
    ],
)
def test_the_environment_handed_to_main_reaches_the_surface(env, expected, capsys):
    """The mapping is *used*, not merely accepted.

    Three mappings, three different refusals: a shell that dropped the
    argument and read the process environment instead —— or passed an
    empty dict —— would give the same first answer to all three. The
    Feishu builder is the probe because its allowlist and bot identity
    are mandatory, so each missing variable has
    its own message and no platform SDK or network is needed to reach
    any of them.
    """
    code = main(["channel", "--", "--channels", "feishu"], env)
    captured = capsys.readouterr()

    assert code == 2
    assert expected in captured.err


# ---- the tree agrees with the table -----------------------------------


MODULE_GUARDS = {
    "launch/__main__.py": "the shell; plan 0037 §5.1",
    "__main__.py": (
        "python -m omicsclaw, repointed at this shell on the owner's "
        "ruling (2026-09-20) from omicsclaw.surfaces.cli.launcher, which "
        "has been unimportable since omicsclaw/skill/ was deleted. Both "
        "guards land on the same main(); neither is a second parse point."
    ),
    "ensemble/_supervise.py": (
        "the trial supervisor, run by file path inside the execution "
        "environment (host or sandbox); plan 0056 §3.3. Parses only its "
        "own limits, never a deployment."
    ),
    "ensemble/metrics/score.py": (
        "python -m omicsclaw.ensemble.metrics.score, the scoring "
        "subprocess of one trial; plan 0056 §3.3. Parses only the trial "
        "it scores, never a deployment."
    ),
    "ensemble/tuning/subsample.py": (
        "python -m omicsclaw.ensemble.tuning.subsample, writes the "
        "subsampled inputs of a tuning probe in the execution environment. "
        "Parses only its own input and seeds, never a deployment."
    ),
    "ensemble/tuning/stability.py": (
        "python -m omicsclaw.ensemble.tuning.stability, computes the "
        "stability curves of a tuning probe. Parses only its spec file."
    ),
    "ensemble/tuning/markers.py": (
        "python -m omicsclaw.ensemble.tuning.markers, marker genes of the "
        "probe's candidate partitions. Parses only its spec file."
    ),
    "ensemble/tuning/inspect.py": (
        "python -m omicsclaw.ensemble.tuning.inspect, what inspect_trials "
        "computes. Parses only its spec file."
    ),
}
"""Every ``__main__`` guard outside the legacy trees, with its reason.

The legacy trees —— :data:`LEGACY_TREES` —— are excluded because they
are scheduled for deletion whole and counting their entry points would
make this test a measure of how far that deletion has got rather than of
how many ways in the rebuilt stack has.
"""

LEGACY_TREES = ("surfaces", "runtime")


def _guarded_modules() -> set[str]:
    """Files under ``omicsclaw/`` with a real ``if __name__`` guard.

    Parsed rather than grepped: a docstring that mentions the guard is
    prose, and a check that cannot tell prose from a statement forces
    the documentation to be written badly.
    """
    found: set[str] = set()
    for path in sorted(_PACKAGE.rglob("*.py")):
        relative = path.relative_to(_PACKAGE)
        if relative.parts[0] in LEGACY_TREES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and any(
                    isinstance(other, ast.Constant) and other.value == "__main__"
                    for other in test.comparators
                )
            ):
                found.add(relative.as_posix())
    return found


def test_the_process_entry_points_in_the_tree_are_the_named_ones():
    assert _guarded_modules() == set(MODULE_GUARDS)


def test_the_console_scripts_land_on_this_shell():
    """``[project.scripts]``, the other half of plan 0037 §8-7.

    Two names and one landing point. ``omicsclaw-chat`` / ``oc-chat``
    are gone rather than repointed —— ``oc cli`` is the same thing, and
    a fourth name for it is what the redesign removes.
    """
    manifest = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert manifest["project"]["scripts"] == {
        "omicsclaw": "omicsclaw.launch:main",
        "oc": "omicsclaw.launch:main",
    }


def test_python_dash_m_omicsclaw_reaches_this_shell():
    """The sixth way in, which was broken until the owner ruled on it.

    ``omicsclaw/__main__.py`` predates plan 0037 and pointed at
    ``omicsclaw.surfaces.cli.launcher``, unimportable since
    ``omicsclaw/skill/`` was deleted —— so the spelling a reader guesses
    first was the one that crashed. Asserted through a **subprocess**
    because that is the only way ``-m`` resolution is exercised at all:
    importing the module would run it in this interpreter, and asserting
    on its source would only check that someone typed the right name.
    """
    result = subprocess.run(
        [sys.executable, "-m", "omicsclaw", "channel", "--", "--list"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    assert "telegram" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_the_repo_root_sentinel_still_points_at_this_shell():
    """Plan 0037 §8-5. ``omicsclaw.py`` may move, but it may not vanish.

    ``omicsclaw/common/workspace.py`` and the Electron client's
    ``python-env.ts`` both decide "is this a source checkout?" by this
    file's existence, so deleting it breaks an external client. Running
    it in a subprocess rather than importing it is deliberate: the
    module name collides with the package, so an import would silently
    resolve to the wrong thing.
    """
    sentinel = _REPO_ROOT / "omicsclaw.py"

    assert sentinel.is_file()
    result = subprocess.run(
        [sys.executable, str(sentinel), "channel", "--", "--list"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    assert "telegram" in result.stdout


def test_the_sentinel_is_still_recognised_as_a_source_checkout(monkeypatch):
    """The consumer, not just the file (plan 0037 §8-5).

    ``OMICSCLAW_DIR`` short-circuits the upward search, so it is cleared
    here: a variable set in somebody's shell would make this test pass
    while saying nothing about the sentinel.
    """
    from omicsclaw.common.workspace import resolve_omicsclaw_dir

    monkeypatch.delenv("OMICSCLAW_DIR", raising=False)
    resolved = resolve_omicsclaw_dir(start=_PACKAGE / "launch" / "__init__.py")

    assert resolved == _REPO_ROOT
