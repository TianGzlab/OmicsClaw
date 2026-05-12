"""Unit tests for the carved-out ``omicsclaw.core.runtime.argv_builder`` module.

The forwarded-flag filter logic used to be inline in ``run_skill`` and was
only exercised via integration tests. After OMI-12 P1.4 it lives in its
own module — pin the edge cases here so future tweaks to the alias / value
detection rules cannot silently regress.
"""

from __future__ import annotations

from pathlib import Path

from omicsclaw.core.runtime.argv_builder import (
    build_skill_argv,
    build_user_run_command,
    extract_flag_value,
    filter_forwarded_args,
)


# ---------------------------------------------------------------------------
# extract_flag_value
# ---------------------------------------------------------------------------


def test_extract_flag_value_handles_space_separated_form():
    assert extract_flag_value(["--method", "leiden"], "--method") == "leiden"


def test_extract_flag_value_handles_equals_form():
    assert extract_flag_value(["--method=cellcharter"], "--method") == "cellcharter"


def test_extract_flag_value_returns_none_when_flag_missing():
    assert extract_flag_value(["--foo", "bar"], "--method") is None


def test_extract_flag_value_returns_none_when_flag_is_trailing():
    assert extract_flag_value(["--method"], "--method") is None


def test_extract_flag_value_handles_empty_input():
    assert extract_flag_value(None, "--method") is None
    assert extract_flag_value([], "--method") is None


# ---------------------------------------------------------------------------
# filter_forwarded_args
# ---------------------------------------------------------------------------


def test_filter_forwarded_args_keeps_only_allow_listed_flags():
    out = filter_forwarded_args(
        ["--method", "leiden", "--secret", "shhh"],
        allowed_extra_flags={"--method"},
    )
    assert out == ["--method", "leiden"]


def test_filter_forwarded_args_blocks_input_output_demo_always():
    """``--input``, ``--output``, ``--demo`` are resolved by the runner and
    must never be smuggled through ``extra_args``, even if a skill mistakenly
    allow-lists them."""
    out = filter_forwarded_args(
        ["--input", "/etc/passwd", "--output", "/tmp/x", "--demo", "--method", "leiden"],
        allowed_extra_flags={"--input", "--output", "--demo", "--method"},
    )
    assert out == ["--method", "leiden"]


def test_filter_forwarded_args_rewrites_n_epochs_to_epochs():
    out = filter_forwarded_args(
        ["--n-epochs", "50"], allowed_extra_flags={"--epochs"}
    )
    assert out == ["--epochs", "50"]


def test_filter_forwarded_args_rewrites_epochs_to_n_epochs():
    out = filter_forwarded_args(
        ["--epochs", "50"], allowed_extra_flags={"--n-epochs"}
    )
    assert out == ["--n-epochs", "50"]


def test_filter_forwarded_args_keeps_inline_equals_form_intact():
    out = filter_forwarded_args(
        ["--method=cellcharter"], allowed_extra_flags={"--method"}
    )
    assert out == ["--method=cellcharter"]


def test_filter_forwarded_args_treats_numeric_negative_as_value_not_flag():
    """``--threshold -0.5`` must keep ``-0.5`` as the value of ``--threshold``,
    not be misclassified as a (blocked) flag."""
    out = filter_forwarded_args(
        ["--threshold", "-0.5"], allowed_extra_flags={"--threshold"}
    )
    assert out == ["--threshold", "-0.5"]


def test_filter_forwarded_args_returns_empty_when_no_args():
    assert filter_forwarded_args(None, allowed_extra_flags={"--method"}) == []
    assert filter_forwarded_args([], allowed_extra_flags={"--method"}) == []


# ---------------------------------------------------------------------------
# build_skill_argv
# ---------------------------------------------------------------------------


def test_build_skill_argv_returns_none_when_no_input_demo_or_input_paths(tmp_path):
    """The runner converts ``None`` into a stable ``_err`` result; build_skill_argv
    surfaces the missing-source condition rather than emitting a half-built argv."""
    skill_info = {"demo_args": ["--demo"]}
    out = build_skill_argv(
        python_executable="/usr/bin/python",
        script_path=tmp_path / "skill.py",
        skill_info=skill_info,
        demo=False,
        input_path=None,
        input_paths=None,
        output_dir=tmp_path / "out",
    )
    assert out is None


def test_build_skill_argv_emits_demo_args_when_demo_set(tmp_path):
    skill_info = {"demo_args": ["--demo", "--demo-mode=fast"]}
    script = tmp_path / "skill.py"
    out_dir = tmp_path / "out"
    argv = build_skill_argv(
        python_executable="/usr/bin/python",
        script_path=script,
        skill_info=skill_info,
        demo=True,
        input_path=None,
        input_paths=None,
        output_dir=out_dir,
    )
    assert argv == [
        "/usr/bin/python",
        str(script),
        "--demo",
        "--demo-mode=fast",
        "--output",
        str(out_dir),
    ]


def test_build_skill_argv_emits_multiple_input_flags_for_input_paths(tmp_path):
    skill_info = {"demo_args": ["--demo"]}
    script = tmp_path / "skill.py"
    out_dir = tmp_path / "out"
    argv = build_skill_argv(
        python_executable="/usr/bin/python",
        script_path=script,
        skill_info=skill_info,
        demo=False,
        input_path=None,
        input_paths=[tmp_path / "a.h5ad", tmp_path / "b.h5ad"],
        output_dir=out_dir,
    )
    assert "--input" in argv
    # Each input gets its own ``--input`` flag pair.
    assert argv.count("--input") == 2


def test_build_skill_argv_single_input_path(tmp_path):
    skill_info = {"demo_args": ["--demo"]}
    script = tmp_path / "skill.py"
    out_dir = tmp_path / "out"
    argv = build_skill_argv(
        python_executable="/usr/bin/python",
        script_path=script,
        skill_info=skill_info,
        demo=False,
        input_path=str(tmp_path / "data.h5ad"),
        input_paths=None,
        output_dir=out_dir,
    )
    assert argv[-4:] == ["--input", str(tmp_path / "data.h5ad"), "--output", str(out_dir)]


# ---------------------------------------------------------------------------
# build_user_run_command
# ---------------------------------------------------------------------------


def test_build_user_run_command_demo_form(tmp_path: Path):
    cmd = build_user_run_command(
        skill_name="spatial-domains",
        demo=True,
        input_path=None,
        output_dir=tmp_path / "out",
    )
    assert cmd == ["oc", "run", "spatial-domains", "--demo", "--output", str(tmp_path / "out")]


def test_build_user_run_command_appends_forwarded_args(tmp_path: Path):
    cmd = build_user_run_command(
        skill_name="spatial-domains",
        demo=False,
        input_path="/data/x.h5ad",
        output_dir=tmp_path / "out",
        forwarded_args=["--method", "leiden"],
    )
    assert cmd == [
        "oc", "run", "spatial-domains",
        "--input", "/data/x.h5ad",
        "--output", str(tmp_path / "out"),
        "--method", "leiden",
    ]
