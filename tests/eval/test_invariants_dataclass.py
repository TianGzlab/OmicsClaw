"""Pure-Python tests for the EvalCase corpus structure.

Doesn't run @pytest.mark.eval — these are dataclass / corpus-level
assertions, no LLM involvement, so they participate in the default
pytest run.
"""

from __future__ import annotations

import re

from tests.eval.invariants import EVAL_CASES, EvalCase, cases_by_category


def test_corpus_has_15_cases() -> None:
    assert len(EVAL_CASES) == 15


def test_case_ids_are_unique() -> None:
    ids = [c.id for c in EVAL_CASES]
    assert len(ids) == len(set(ids)), (
        f"duplicate case IDs: {[i for i in ids if ids.count(i) > 1]}"
    )


def test_category_distribution_matches_grill_me_design() -> None:
    """5 routing + 3 adversarial + 3 methodology + 2 regression + 2 ux."""
    counts = {
        "routing": len(cases_by_category("routing")),
        "adversarial": len(cases_by_category("adversarial")),
        "methodology": len(cases_by_category("methodology")),
        "regression": len(cases_by_category("regression")),
        "ux": len(cases_by_category("ux")),
    }
    assert counts == {
        "routing": 5,
        "adversarial": 3,
        "methodology": 3,
        "regression": 2,
        "ux": 2,
    }, f"category distribution drift: {counts}"


def test_chinese_coverage_meets_5_of_15_target() -> None:
    chinese = [c for c in EVAL_CASES if c.language == "zh"]
    assert len(chinese) >= 5, (
        f"need >=5 Chinese cases for surface_voice_rules + predicate "
        f"path coverage, have {len(chinese)}"
    )


def test_chinese_cases_span_at_least_three_categories() -> None:
    """Don't pile all 5 Chinese cases into one category — they should
    exercise multiple paths."""
    zh_cats = {c.category for c in EVAL_CASES if c.language == "zh"}
    assert len(zh_cats) >= 3, (
        f"Chinese coverage is too narrow ({zh_cats}); spread across "
        f"at least 3 categories"
    )


def test_each_must_case_has_at_least_one_invariant() -> None:
    """A must-priority case with no invariants would always pass —
    that's a corpus bug."""
    for case in EVAL_CASES:
        if case.priority != "must":
            continue
        any_invariant = (
            case.expected_skill
            or case.must_call_tools
            or case.must_not_call_tools
            or case.must_mention
            or case.must_not_mention
        )
        assert any_invariant, (
            f"must-priority case {case.id!r} has no invariant fields populated"
        )


def test_regression_category_includes_phase_4_review_fixes() -> None:
    """The 2 regression cases should directly target the bugs review
    sessions caught: (1) sc-enrichment over-firing on sc-de (PR #107),
    (2) plot_intent over-firing on 'figure of merit' (PR #110 review)."""
    regression_ids = {c.id for c in cases_by_category("regression")}
    assert "regression__sc_de_does_not_pull_sc_enrichment" in regression_ids
    assert "regression__figure_of_merit_no_plot_intent" in regression_ids


def test_priority_values_are_must_or_should() -> None:
    for case in EVAL_CASES:
        assert case.priority in {"must", "should"}, (
            f"unknown priority {case.priority!r} on {case.id!r}"
        )


def test_must_mention_patterns_compile() -> None:
    """All regex patterns in ``must_mention`` / ``must_not_mention`` must
    compile — a bad pattern would fail at runtime mid-eval."""
    for case in EVAL_CASES:
        for pattern in (*case.must_mention, *case.must_not_mention):
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise AssertionError(
                    f"invalid regex on {case.id!r}: {pattern!r} ({exc})"
                ) from exc
