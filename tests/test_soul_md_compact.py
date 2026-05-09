"""Phase 3 (Task 3.1) RED tests pinning the new SOUL.md contract.

After Phase 3:
- SOUL.md is the *single* source for the always-on operating core.
- Verbose persona segments (Acknowledgements, Bot Mode / CLI Mode voice
  variants, full Expertise list, Mission paragraph) move out — voice
  variants to ``surface_voice_rules`` and the rest to README.
- File size is bounded so the always-on cost can't silently regress.

The 7 always-on rules from grill-me Q4 each have a signature keyword
that pins the rule text without locking the exact wording.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOUL_PATH = ROOT / "SOUL.md"


def _soul_text() -> str:
    return SOUL_PATH.read_text(encoding="utf-8")


# --- Size contract ------------------------------------------------------------


def test_soul_md_size_under_1500_chars() -> None:
    """Lint guard: keep SOUL.md compact. >1500 chars and the always-on
    cost will start regressing toward the pre-refactor 3,763 chars."""
    text = _soul_text()
    assert len(text) <= 1500, (
        f"SOUL.md grew to {len(text)} chars; budget is 1500. "
        "Move new long-form content to README instead, or update the "
        "budget here with a justification."
    )


# --- 7 always-on rule signatures ---------------------------------------------


def test_soul_md_states_identity_with_omicsclaw_and_skill_mention() -> None:
    text = _soul_text()
    lower = text.lower()
    assert "omicsclaw" in lower
    assert "skill" in lower, "Identity must mention SKILL.md / skills"


def test_soul_md_routes_through_resolve_capability() -> None:
    """Rule 2 (routing trigger): non-trivial requests use resolve_capability;
    direct skill invocations use omicsclaw."""
    text = _soul_text()
    assert "resolve_capability" in text
    # The 'omicsclaw' tool dispatch is also part of the routing rule.
    assert "omicsclaw" in text.lower()


def test_soul_md_pins_result_fidelity() -> None:
    """Rule 3: never silently round / fabricate scientific outputs."""
    text = _soul_text()
    lower = text.lower()
    assert "preserve" in lower or "fidelity" in lower
    assert "fabricate" in lower or "silently" in lower


def test_soul_md_pins_failure_handling() -> None:
    """Rule 4: don't loop the same failing call; don't silently switch methods."""
    text = _soul_text()
    lower = text.lower()
    assert "silently switch" in lower or "switch methods" in lower
    assert "loop" in lower or "retry" in lower or "retries" in lower


def test_soul_md_pins_action_risk_discipline() -> None:
    """Rule 5: confirm destructive / shared-state actions before executing."""
    text = _soul_text()
    lower = text.lower()
    assert "destructive" in lower or "shared-state" in lower or "shared state" in lower
    assert "confirm" in lower or "shortcut" in lower


def test_soul_md_pins_tone_rules() -> None:
    """Rule 6 (tone): concise, evidence-led, path:line citations, no
    'Let me X:' preambles."""
    text = _soul_text()
    assert "path:line" in text or "`path:line`" in text
    assert "Let me" in text  # the "no 'Let me X:' preamble" rule


def test_soul_md_pins_security_boundary() -> None:
    """Rule 7: never share API keys / credentials; never fabricate scientific results."""
    text = _soul_text()
    lower = text.lower()
    assert "credentials" in lower or "api key" in lower or "api keys" in lower


# --- Removed verbose segments -------------------------------------------------


def test_soul_md_does_not_carry_acknowledgements_section() -> None:
    """Acknowledgements (~1KB) move to README's Inspiration section."""
    text = _soul_text()
    assert "## Acknowledgements" not in text
    assert "RoboTerri" not in text, (
        "ClawBio / RoboTerri attribution belongs in README, not SOUL.md"
    )


def test_soul_md_does_not_carry_bot_mode_or_cli_mode_subsections() -> None:
    """Per-surface voice variants move to surface_voice_rules injector."""
    text = _soul_text()
    assert "Bot Mode" not in text
    assert "CLI Mode" not in text


def test_soul_md_does_not_carry_full_expertise_list() -> None:
    """The bullet-by-bullet expertise list duplicates routing-table content."""
    text = _soul_text()
    # Detect the old bullet pattern; tolerate a one-line expertise mention
    # in identity but reject the verbose bulleted block.
    assert text.count("**Spatial transcriptomics**") == 0
    assert text.count("**Single-cell omics**") == 0


# --- Loader integration -------------------------------------------------------


def test_soul_md_is_loaded_by_load_base_persona() -> None:
    """Sanity: the runtime loader returns the file content unchanged."""
    from omicsclaw.runtime.context_layers import load_base_persona

    loaded = load_base_persona()
    assert loaded == _soul_text().rstrip() or loaded.startswith(_soul_text()[:200])
