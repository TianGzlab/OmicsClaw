"""Regression test for the dead ``spatial-domain-identification`` --epochs
conditional removal.

The bot used to branch on ``canonical_skill == "spatial-domain-identification"``
to pick between ``--epochs`` and ``--n-epochs``. The registry resolves that
alias to canonical ``spatial-domains`` before this code runs, so the branch
was dead — the bot always emitted ``--n-epochs`` and relied on
``argv_builder.filter_forwarded_args`` to rewrite ``--n-epochs`` to
``--epochs`` (or vice versa) per each skill's ``allowed_extra_flags``.

This test pins the simplification so a future "helpful" branch
re-introduction has to break a test.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bot_skill_orchestration_has_no_spatial_domain_identification_special_case():
    """``bot/skill_orchestration.py`` must not switch on the legacy alias.

    The argv builder owns the ``--epochs`` / ``--n-epochs`` rewrite; the
    bot adapter is supposed to be ignorant of which skill takes which.
    """
    source = (ROOT / "bot" / "skill_orchestration.py").read_text(encoding="utf-8")
    # Tolerate docstring / comment mentions explaining the removal, but not
    # an actual code conditional.
    pattern = re.compile(r'^\s*if\s+canonical_skill\s*==\s*"spatial-domain-identification"', re.M)
    assert not pattern.search(source), (
        "dead ``if canonical_skill == 'spatial-domain-identification'`` "
        "conditional reintroduced in bot/skill_orchestration.py — let "
        "argv_builder.filter_forwarded_args handle the --epochs rewrite."
    )


def test_bot_tool_executors_has_no_spatial_domain_identification_special_case():
    """``bot/tool_executors.py`` must not switch on the legacy alias either."""
    source = (ROOT / "bot" / "tool_executors.py").read_text(encoding="utf-8")
    pattern = re.compile(r'^\s*if\s+canonical_skill\s*==\s*"spatial-domain-identification"', re.M)
    assert not pattern.search(source), (
        "dead ``if canonical_skill == 'spatial-domain-identification'`` "
        "conditional reintroduced in bot/tool_executors.py — let "
        "argv_builder.filter_forwarded_args handle the --epochs rewrite."
    )


def test_argv_builder_still_rewrites_n_epochs_for_spatial_domains():
    """Sanity-check the rewrite the bot now relies on: when a skill only
    allow-lists ``--epochs``, the bot's ``--n-epochs`` argv is rewritten
    correctly. If this stops working, the dead-branch deletion would
    silently strip the flag and skills would run with default epochs."""
    from omicsclaw.core.runtime.argv_builder import filter_forwarded_args

    out = filter_forwarded_args(
        ["--n-epochs", "50"], allowed_extra_flags={"--epochs"}
    )
    assert out == ["--epochs", "50"]


def test_spatial_domains_canonical_alias_makes_branch_unreachable():
    """The branch was dead because the registry's canonical alias for
    ``spatial-domain-identification`` is ``spatial-domains``. Pin that so a
    future SKILL.md edit that renames the canonical alias back to
    ``spatial-domain-identification`` re-introduces the bug visibly."""
    from omicsclaw.core.registry import ensure_registry_loaded

    registry = ensure_registry_loaded()
    legacy_view = registry.skills.get("spatial-domain-identification")
    assert legacy_view is not None, "legacy alias must remain resolvable"
    assert legacy_view["alias"] == "spatial-domains", (
        "If the canonical alias changes back to spatial-domain-identification, "
        "the bot's dead-branch deletion needs to be revisited — the rewrite "
        "rule lives in argv_builder now."
    )
