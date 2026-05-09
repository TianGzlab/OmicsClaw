"""Backward-compat contract for bot.skill_orchestration.

The module collects skill-execution helpers carved out of bot/core.py
across slice #119 (PR #122) and slice #119-remainder (this PR). These
identity tests pin the contract: every previously-public symbol on
``bot.core`` must resolve to the **same object** as on
``bot.skill_orchestration`` — not parallel copies, not aliases.

External tests (``tests/test_oauth_regressions.py``,
``tests/test_skill_listing.py``, etc.) import these names from
``bot.core``; the regression net only stays meaningful if the two
paths point at the same callable.
"""

from __future__ import annotations


SKILL_ORCH_REEXPORTS = (
    # Slice #119 (PR #122) — already in bot.skill_orchestration
    "OutputMediaPaths",
    "_collect_output_media_paths",
    "_AUTO_DISAMBIGUATE_GAP",
    "_format_auto_disambiguation",
    "_format_auto_route_banner",
    # Slice #119-remainder (this PR) — execution path
    "_normalize_extra_args",
    "_run_omics_skill_step",
    "_run_skill_via_shared_runner",
    # Skill lookup + param inference
    "_lookup_skill_info",
    "_resolve_param_hint_info",
    "_infer_skill_for_method",
    "_build_method_preview",
    "_build_param_hint",
    # Memory auto-capture
    "_auto_capture_dataset",
    "_auto_capture_analysis",
    # Env-error parsing
    "_extract_env_snippet",
    "_extract_fix_hint",
    "_classify_env_error",
    # Output state
    "_resolve_last_output_dir",
    "_read_result_json",
    "_update_preprocessing_state",
    "_format_next_steps",
)


def test_skill_orchestration_re_exports_share_identity_with_bot_core():
    """Every previously-public symbol must resolve to the *same object*
    when looked up via ``bot.core`` or via ``bot.skill_orchestration``."""
    import bot.core
    import bot.skill_orchestration

    missing_on_skill_orch = [
        name for name in SKILL_ORCH_REEXPORTS
        if not hasattr(bot.skill_orchestration, name)
    ]
    assert not missing_on_skill_orch, (
        f"Missing on bot.skill_orchestration: {missing_on_skill_orch}"
    )

    missing_on_core = [
        name for name in SKILL_ORCH_REEXPORTS
        if not hasattr(bot.core, name)
    ]
    assert not missing_on_core, (
        f"Missing on bot.core (re-export): {missing_on_core}"
    )

    mismatched_identity = [
        name for name in SKILL_ORCH_REEXPORTS
        if getattr(bot.core, name) is not getattr(bot.skill_orchestration, name)
    ]
    assert not mismatched_identity, (
        f"Parallel copies (must be same object): {mismatched_identity}"
    )
