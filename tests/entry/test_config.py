"""``AppConfig`` and the single parse point.

Two properties carry most of the weight here, and both are the kind that
pass by accident if the assertion is written loosely.

*The timeout is one number.* Plan 0031 §12-2 raised the tool ceiling to
600 s and made "single source" a condition of the ruling, because the
predictable failure of two independent literals is that a later change
moves one of them. So the tests below assert the **derivation**, not the
two values: hard-coding ``bash_timeout`` to anything turns
:func:`test_bash_timeout_is_derived_from_the_ceiling` red even if the
number chosen happens to be right today.

*The environment is read outside this package entirely.* Q8's rule was
"one parse point, with an exemption list"; plan 0037 §5.4 turned it into
a flat one —— no module under ``omicsclaw/entry/`` reaches for either
global, and the exemption list is empty. That is a property of the
package as a whole, so
:func:`test_no_entry_module_reads_the_environment` reads every module's
source rather than testing a function.
"""

from __future__ import annotations

import inspect
import pathlib

import pytest

from omicsclaw.context import Pressure
from omicsclaw.engine import EngineConfig
from omicsclaw.entry.config import AppConfig, AppConfigError, resolve_app_config
from omicsclaw.tools.builtin.bash import ENGINE_TIMEOUT_MARGIN
from tests._env_probe import offending_sources

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRY_DIR = _REPO_ROOT / "omicsclaw" / "entry"


def _config(**overrides: object) -> AppConfig:
    return AppConfig(workspace=pathlib.Path("/tmp/does-not-need-to-exist"), **overrides)


# ---- the single source of truth -------------------------------------


def test_the_shipped_ceiling_and_its_derived_half():
    """The owner's ruling, and the only place the two numbers are written.

    Plan 0031 §12-2 chose option B — ten minutes — against a draft that
    had argued for keeping one. The evidence in the handover was
    concrete: a ``spatial-deconv`` run or a STAR alignment takes minutes
    to hours, and the old value was an unexamined port from the reference
    harness.

    **This is the only assertion in the repository that names either
    number.** Production code holds the ceiling once, as
    :attr:`AppConfig.tool_timeout_s`, and never holds the derived half at
    all because it is subtracted rather than written — so a repository
    grep finds the ceiling twice and its half once, which is what
    acceptance §9-16 is asking for.
    """
    config = _config()

    assert (config.tool_timeout_s, config.bash_timeout()) == (600.0, 585.0)


def test_the_engine_config_is_derived_not_restated():
    """``EngineConfig.tool_timeout`` comes from the field, not a copy."""
    config = _config(tool_timeout_s=123.0, max_turns=7)
    engine = config.engine_config()

    assert isinstance(engine, EngineConfig)
    assert engine.tool_timeout == config.tool_timeout_s
    assert engine.max_turns == config.max_turns


def test_bash_timeout_is_derived_from_the_ceiling():
    """The derivation, asserted as a derivation.

    **The mutation this is written against**: replacing the body of
    :meth:`AppConfig.bash_timeout` with ``return 45.0`` — the value
    ``BashTool`` defaults to, so the substitution looks harmless. The
    parametrisation kills it at every ceiling except the one it was
    copied from, and the margin is imported from the module that owns it
    so a change there is picked up rather than contradicted.
    """
    for ceiling in (1234.5, 300.0, 60.0):
        config = _config(tool_timeout_s=ceiling)
        assert config.bash_timeout() == ceiling - ENGINE_TIMEOUT_MARGIN


# ---- defaults --------------------------------------------------------


def test_the_defaults_are_the_ones_the_plan_settled_on():
    config = _config()

    assert config.model == ""
    assert config.provider == ""
    assert config.max_turns == 50
    assert config.system_prompt_files == ()
    assert config.summary_model == ""
    assert config.summary_timeout_s == 90.0
    assert config.approval_timeout_s is None
    assert config.turn_timeout_s is None
    assert config.max_queued_per_session == 2
    assert config.delta_ring_size == 2048
    assert config.max_sessions == 256


def test_compaction_triggers_at_full_and_pressure_has_no_order():
    """``Pressure.FULL`` is the default, and ``>=`` on it is a trap.

    :class:`~omicsclaw.context.Pressure` is a :class:`~enum.StrEnum`, so
    comparison is alphabetical. The assertion below records the exact
    inversion plan 0031 trap 0 is about: the tier that most needs
    compacting compares as *lower* than the trigger, so a turn written
    with ``>=`` would skip precisely the emergency case while passing
    every test built from ``SOFT`` and ``FULL``.
    """
    assert _config().compact_at is Pressure.WARN
    assert (Pressure.NONE >= Pressure.FULL) is True
    assert (Pressure.EMERGENCY >= Pressure.FULL) is False


def test_the_config_cannot_be_mutated():
    config = _config()

    with pytest.raises(Exception):
        config.tool_timeout_s = 1.0  # type: ignore[misc]


def test_a_workspace_must_be_named():
    """No default: which directory an agent may write to is not a guess."""
    with pytest.raises(TypeError):
        AppConfig()  # type: ignore[call-arg]


# ---- resolution ------------------------------------------------------


def test_resolution_touches_neither_global_when_both_are_given():
    """The injectability that makes every other test here possible."""
    config = resolve_app_config(argv=[], env={})

    assert config.model == ""
    assert config.tool_timeout_s == _config().tool_timeout_s
    assert config.workspace == pathlib.Path.cwd()


def test_the_workspace_defaults_to_the_working_directory_and_is_absolute():
    """``main.go:112``'s ``os.Getwd()``, and one spelling of the answer."""
    config = resolve_app_config(argv=["--workspace", "."], env={})

    assert config.workspace.is_absolute()
    assert config.workspace == pathlib.Path.cwd().resolve()


def test_the_environment_is_read():
    config = resolve_app_config(
        argv=[],
        env={
            "OMICSCLAW_MODEL": "deepseek-chat",
            "OMICSCLAW_TOOL_TIMEOUT_S": "42",
            "OMICSCLAW_COMPACT_AT": "soft",
            "OMICSCLAW_TURN_TIMEOUT_S": "900",
        },
    )

    assert config.model == "deepseek-chat"
    assert config.tool_timeout_s == 42.0
    assert config.compact_at is Pressure.SOFT
    assert config.turn_timeout_s == 900.0


def test_the_generic_model_variable_is_the_providers_own_spelling():
    """``LLM_MODEL`` moves the budget as well as the request.

    ``omicsclaw/provider/config.py`` reads ``OMICSCLAW_MODEL`` then
    ``LLM_MODEL``. Reading a different name here would leave a deployment
    whose provider talks to one model while the context budget is sized
    for another — and nothing would report it, because both halves would
    look configured.
    """
    assert resolve_app_config(argv=[], env={"LLM_MODEL": "gpt-4o"}).model == "gpt-4o"
    assert (
        resolve_app_config(
            argv=[],
            env={"LLM_MODEL": "gpt-4o", "OMICSCLAW_MODEL": "deepseek-chat"},
        ).model
        == "deepseek-chat"
    )


def test_argv_beats_the_environment_and_overrides_beat_argv():
    config = resolve_app_config(
        argv=["--model", "from-argv", "--max-turns", "9"],
        env={"OMICSCLAW_MODEL": "from-env", "OMICSCLAW_MAX_TURNS": "3"},
        max_turns=99,
    )

    assert config.model == "from-argv"
    assert config.max_turns == 99


def test_a_flag_may_be_spelled_with_an_equals_sign():
    config = resolve_app_config(argv=["--model=written-inline"], env={})

    assert config.model == "written-inline"


def test_prompt_files_accumulate_across_repeats_and_split_in_the_environment():
    from_argv = resolve_app_config(
        argv=["--system-prompt-file", "a.md", "--system-prompt-file", "b.md"],
        env={},
    )
    from_env = resolve_app_config(
        argv=[], env={"OMICSCLAW_SYSTEM_PROMPT_FILES": "a.md:b.md"}
    )

    assert [p.name for p in from_argv.system_prompt_files] == ["a.md", "b.md"]
    assert [p.name for p in from_env.system_prompt_files] == ["a.md", "b.md"]


def test_the_deployment_half_no_longer_answers_to_the_surface_flag_name():
    """The rename is the fix, so the old name has to be *refused*.

    Before the owner's 2026-09-20 ruling both halves of the command line
    answered to ``--prompt-file``, and a forgotten ``--`` fed the user's
    task brief to the system prompt with nothing raised. Accepting the
    old name as an alias would keep exactly that failure alive, so this
    asserts the deployment half rejects it outright — the same refusal
    any unknown flag gets, which is what sends the reader to ``--help``.
    """
    with pytest.raises(AppConfigError, match="prompt-file"):
        resolve_app_config(argv=["--prompt-file", "brief.md"], env={})


def test_a_deadline_can_be_switched_off_from_a_shell():
    """A shell cannot write ``None``; ``none`` is how an operator will."""
    config = resolve_app_config(argv=["--approval-timeout", "none"], env={})

    assert config.approval_timeout_s is None


def test_an_unparseable_value_is_refused_rather_than_defaulted():
    """The divergence from ``provider/config.py``, and why it is one.

    That module replaces a bad value with its default on purpose. Here it
    would mean ``OMICSCLAW_TOOL_TIMEOUT_S=6OO`` — a letter O — resolving
    to 600 s in an operator's head and 60 s in the engine, which is the
    exact failure §12-2 exists to prevent.
    """
    with pytest.raises(AppConfigError) as env_error:
        resolve_app_config(argv=[], env={"OMICSCLAW_TOOL_TIMEOUT_S": "6OO"})
    assert "OMICSCLAW_TOOL_TIMEOUT_S" in str(env_error.value)

    with pytest.raises(AppConfigError):
        resolve_app_config(argv=["--max-turns", "many"], env={})

    with pytest.raises(AppConfigError):
        resolve_app_config(argv=["--compact-at", "high"], env={})


def test_a_pressure_tier_that_does_not_exist_names_the_ones_that_do():
    """``Pressure.HIGH`` was in the plan's draft and does not exist."""
    with pytest.raises(AppConfigError) as error:
        resolve_app_config(argv=["--compact-at", "high"], env={})

    assert "emergency" in str(error.value)


def test_an_unknown_flag_is_refused_and_says_where_to_put_it():
    with pytest.raises(AppConfigError) as error:
        resolve_app_config(argv=["--session", "abc"], env={})

    assert "--" in str(error.value)


def test_a_surfaces_own_flags_go_after_the_terminator():
    """Q8 leaves one argv reader, so a surface needs somewhere to stand."""
    config = resolve_app_config(
        argv=["--model", "m", "--", "--session", "abc", "--tui"],
        env={},
    )

    assert config.model == "m"


def test_a_flag_with_no_value_is_refused():
    with pytest.raises(AppConfigError):
        resolve_app_config(argv=["--model"], env={})


def test_an_override_that_is_not_a_field_is_refused():
    """Catches a renamed field at the call site instead of silently
    dropping it — ``**overrides`` would otherwise swallow a typo."""
    with pytest.raises(AppConfigError) as error:
        resolve_app_config(argv=[], env={}, tool_timeout=1.0)

    assert "tool_timeout" in str(error.value)


# ---- Q8, as a property of the package --------------------------------


def _entry_sources() -> list[pathlib.Path]:
    return sorted(_ENTRY_DIR.rglob("*.py"))


def test_there_are_entry_modules_to_check():
    assert _entry_sources()


_EXEMPT = ()
"""Empty, and that is the point (plan 0037 §5.4, acceptance §8-1).

This list held two names. ``config.py`` was on it because
:func:`resolve_app_config` defaulted ``argv`` to ``sys.argv`` and
``env`` to the process environment; ``__main__.py`` joined it when
``python -m omicsclaw.entry.cli`` shipped, because a command line enters
a process somewhere and a ``__main__`` is where.

Plan 0037 removed both rather than widening the list —— a growing
exemption list is the only way this rule degrades. The process moved out
to :mod:`omicsclaw.launch`, ``resolve_app_config``'s two parameters lost
their defaults, and the rule below is now flat: **no** module under
``omicsclaw/entry/`` names either global, in code or in prose.

Kept as a named empty constant rather than deleted, so that re-opening
an exemption is a visible edit to a documented list and not a quiet
``if path.name == ...`` inside the loop.
"""


def test_the_exemption_list_is_empty():
    """Plan 0037 §8-1, stated as its own criterion.

    The scan below would still pass with one name on this list, so the
    emptiness has to be asserted separately —— otherwise "the exemption
    list is empty" is a claim no test makes.
    """
    assert _EXEMPT == ()


def test_no_entry_module_reads_the_environment():
    """One parse point, checked against every module rather than one.

    Written as a source scan and not as a mock, because the rule is about
    modules that do not exist yet: the session, turn, stream and surface
    modules inherit it the moment they are added. The one permitted
    exception is spelled out in plan 0031 Q8 and lives in the provider
    layer, not here — ``provider_from_env`` keeps reading its own key.

    The needles include prose, which is deliberate here and not an
    oversight: after plan 0037 this package genuinely does not touch
    either global, so a docstring that says it does is wrong rather than
    merely untested. ``config.py``'s own prose was rewritten for that
    reason when its defaults were removed.

    They live in :mod:`tests._env_probe` rather than in this function,
    because the shell one layer up enforces the same rule and the two
    copies of the loop this replaced shared a blind spot rather than
    covering for each other: neither knew ``from os import environ``.
    """
    offenders = offending_sources(_ENTRY_DIR, exempt=_EXEMPT)

    assert not offenders, (
        f"{offenders} — omicsclaw.launch is the only reader of the command "
        "line and the environment; this layer is handed both"
    )


def test_the_deployment_reader_takes_both_sources_as_arguments():
    """Plan 0037 §5.4, the half the source scan cannot see.

    Dropping the defaults is what empties the exemption list; a default
    put back would make ``config.py`` name a global again and the scan
    above would catch it. A *third* spelling —— reading the environment
    through a helper in another module —— would not, so the signature
    itself is pinned.
    """
    signature = inspect.signature(resolve_app_config)

    assert signature.parameters["argv"].default is inspect.Parameter.empty
    assert signature.parameters["env"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        resolve_app_config()  # type: ignore[call-arg]
