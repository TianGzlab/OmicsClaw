"""Phase 2 (T2.2 + T2.4) tests pinning compact tool descriptions.

The two heaviest always-on tool descriptions had grown to 1,501 chars
(``omicsclaw``) and 1,489 chars (``replot_skill``) — together ~9% of
the entire pre-compression tool list. Phase 2 cuts both to <=500
chars by removing routing-policy narrative that's already encoded in
``capability_resolver`` / SKILL.md / per-parameter schema descriptions,
while pinning the four critical gotchas in each.
"""

from __future__ import annotations

from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs


def _spec_by_name(name: str):
    ctx = BotToolContext(skill_names=("sc-de", "spatial-preprocess"), domain_briefing="(t)")
    for spec in build_bot_tool_specs(ctx):
        if spec.name == name:
            return spec
    raise AssertionError(f"{name} not registered")


# --- omicsclaw ---------------------------------------------------------------


def test_omicsclaw_description_under_500_chars() -> None:
    spec = _spec_by_name("omicsclaw")
    assert len(spec.description) <= 500, (
        f"omicsclaw description grew to {len(spec.description)} chars; "
        f"budget is 500. Detailed routing rules belong in capability_resolver "
        f"metadata or in per-parameter descriptions, not here."
    )


def test_omicsclaw_description_pins_skill_auto_default() -> None:
    """Critical gotcha: the model should default skill='auto' + pass query.
    Without this hint the model often guesses a specific skill incorrectly."""
    spec = _spec_by_name("omicsclaw")
    lower = spec.description.lower()
    assert "auto" in lower
    assert "query" in lower


def test_omicsclaw_description_pins_demo_mode_explicit() -> None:
    """``mode='demo'`` must only fire when the user explicitly asks."""
    spec = _spec_by_name("omicsclaw")
    assert "demo" in spec.description.lower()


def test_omicsclaw_description_pins_return_media_default() -> None:
    """Default behavior is text summary; figures/plots only when asked."""
    spec = _spec_by_name("omicsclaw")
    assert "return_media" in spec.description


def test_omicsclaw_description_pins_auto_prepare_for_batch_integration() -> None:
    """``auto_prepare=true`` is the recovery path for sc-batch-integration
    pauses — keep it pinned so the rule survives any future rewrite."""
    spec = _spec_by_name("omicsclaw")
    lower = spec.description.lower()
    assert "auto_prepare" in lower


# --- replot_skill ------------------------------------------------------------


def test_replot_skill_description_under_550_chars() -> None:
    """Budget bumped from 500 to 550 to keep both the
    ``custom_analysis_execute`` AND Python-plotting prohibition (the
    review-flagged "do not fall back" path) without risking model
    behavior."""
    spec = _spec_by_name("replot_skill")
    assert len(spec.description) <= 550, (
        f"replot_skill description grew to {len(spec.description)} chars; "
        f"budget is 550."
    )


def test_replot_skill_description_pins_top_n_renderer_flags() -> None:
    """Critical gotchas: ``--top-n`` for parameter tuning,
    ``--renderer`` to limit which sub-plot, ``--list-renderers`` to
    discover what's tunable."""
    spec = _spec_by_name("replot_skill")
    lower = spec.description.lower()
    assert "top-n" in lower or "top_n" in lower
    assert "renderer" in lower


def test_replot_skill_description_pins_no_python_fallback() -> None:
    """The original instruction explicitly forbade falling back to
    ``custom_analysis_execute``. Code review caught the loss; pin both
    names so future rewrites can't drop them again."""
    spec = _spec_by_name("replot_skill")
    lower = spec.description.lower()
    assert "custom_analysis_execute" in lower
    assert "python" in lower
