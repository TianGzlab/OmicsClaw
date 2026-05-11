"""Tests for the Skip-when extractor's skill-discovery loop.

ADR 2026-05-11 (#2) POC scope was spatial-only, but the extractor must
correctly discover skills in every domain shape — including domains
that contain a single SKILL.md at the domain root (e.g. `literature`).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import extract_skip_when_cases as extractor  # noqa: E402
from scripts.extract_skip_when_cases import _load_skill_entries  # noqa: E402


def test_extractor_finds_domain_root_skill_md():
    """Some domains (e.g. literature) place their single SKILL.md at the
    domain root rather than nested in a per-skill subdirectory.  The
    extractor MUST surface these as real skills, not skip them as if
    they were INDEX files."""
    entries = _load_skill_entries("literature")
    skill_names = [e.skill for e in entries]
    # literature/SKILL.md exists in the repo — extractor must find it.
    assert (ROOT / "skills" / "literature" / "SKILL.md").exists(), (
        "Test premise broken: skills/literature/SKILL.md no longer exists"
    )
    assert "literature" in skill_names or any("literature" in n for n in skill_names), (
        f"extractor missed the domain-root SKILL.md in literature; got: {skill_names}"
    )


# --------------------------------------------------------------------------- #
# LLM extraction failure handling — when the LLM returns malformed JSON, the
# snapshot entry MUST record extraction_failed=true so a reviewer notices,
# not silently emit an empty cases list (which the drift test would treat as
# "no Skip-when redirects" and pass).
# --------------------------------------------------------------------------- #

def test_extract_for_skill_records_extraction_failed_on_bad_json(monkeypatch):
    """When _call_llm returns text that is not valid JSON, the extractor
    must return a sentinel that propagates extraction_failed=true into the
    snapshot — not an empty cases list."""
    entry = extractor.SkillEntry(
        skill="fake-skill",
        description="Load when X. Skip when Y (use sibling-skill).",
        description_hash="sha256:abc",
    )

    def _fake_llm(prompt, *, api_key, base_url, model, temperature):
        return "this is not JSON, just an apology from the model"

    monkeypatch.setattr(extractor, "_call_llm", _fake_llm)

    result = extractor._extract_for_skill(
        entry,
        valid_skill_names=["fake-skill", "sibling-skill"],
        llm_config=("fake-key", "https://x", "fake-model"),
        temperature=0.0,
    )
    # The result must signal failure — a plain empty list is NOT enough
    # because a real "no Skip-when clauses" skill also yields an empty list.
    assert isinstance(result, dict), (
        f"failed extractions must return a dict with extraction_failed=true, "
        f"got {type(result).__name__}: {result!r}"
    )
    assert result.get("extraction_failed") is True
    assert result.get("cases") == []
    assert "error" in result, "failure dict should carry a short error reason"


def test_extract_for_skill_rejects_self_route_expected_pick(monkeypatch):
    """If the LLM names the host skill as `expected_pick`, the case is
    contradictory (must_not_pick == expected_pick) and must be dropped.
    Closes a threat-model gap: the original whitelist check only required
    membership in `valid_skill_names`, which includes the host — letting
    an injected description steer routing back to the host.  Reported by
    CodeRabbit on PR #170."""
    entry = extractor.SkillEntry(
        skill="spatial-de",
        description="Load when ranking spatial cluster markers. Skip when single-cell (use sc-de).",
        description_hash="sha256:abc",
    )

    def _fake_llm(prompt, *, api_key, base_url, model, temperature):
        return (
            '[{"trigger": "scrna DE", "must_not_pick": "spatial-de", '
            '"expected_pick": "spatial-de"}]'
        )

    monkeypatch.setattr(extractor, "_call_llm", _fake_llm)
    result = extractor._extract_for_skill(
        entry,
        valid_skill_names=["spatial-de", "sc-de"],
        llm_config=("fake-key", "https://x", "fake-model"),
        temperature=0.0,
    )
    assert result["extraction_failed"] is False
    assert result["cases"] == [], (
        f"self-route case must be dropped, got {result['cases']!r}"
    )
