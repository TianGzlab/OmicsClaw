"""Tests for SKILL.md `## Gotchas` extraction (ADR 2026-05-11).

These cover the LazySkillMetadata.gotchas property that parses the body of
a SKILL.md file and returns the lead sentence of each Gotcha bullet.  The
lead sentence is the bold-marked first sentence (between `**...**`); when
no bold marker is present, the first sentence (split on '. ') is used as
a fallback.  Template placeholders (italic `_None yet…_`) yield an empty
list so unfilled scaffolds do not pollute the runtime injection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.core.lazy_metadata import LazySkillMetadata


ROOT = Path(__file__).resolve().parent.parent


def _make_skill(tmp_path: Path, body: str, frontmatter: str = "") -> Path:
    skill_dir = tmp_path / "fake-skill"
    skill_dir.mkdir()
    fm = frontmatter or (
        "---\n"
        "name: fake-skill\n"
        "description: Load when running the fake skill. Skip when never.\n"
        "---\n"
    )
    (skill_dir / "SKILL.md").write_text(fm + "\n" + body, encoding="utf-8")
    return skill_dir


def test_gotchas_returns_empty_list_when_section_missing(tmp_path):
    skill_dir = _make_skill(tmp_path, body="## When to use\n\nDo a thing.\n")
    lazy = LazySkillMetadata(skill_dir)
    assert lazy.gotchas == []


def test_gotchas_returns_empty_list_for_template_placeholder(tmp_path):
    body = (
        "## Gotchas\n\n"
        "- _None yet — append as failure modes are reported._\n\n"
        "## Key CLI\n"
    )
    skill_dir = _make_skill(tmp_path, body=body)
    lazy = LazySkillMetadata(skill_dir)
    assert lazy.gotchas == []


def test_gotchas_extracts_bold_lead_sentence(tmp_path):
    body = (
        "## Gotchas\n\n"
        "- **First trap is dangerous.** Long elaboration here.\n"
        "- **Second trap also.** More words after.\n\n"
        "## Key CLI\n"
    )
    skill_dir = _make_skill(tmp_path, body=body)
    lazy = LazySkillMetadata(skill_dir)
    assert lazy.gotchas == [
        "First trap is dangerous.",
        "Second trap also.",
    ]


def test_gotchas_falls_back_to_first_sentence_when_no_bold(tmp_path):
    body = (
        "## Gotchas\n\n"
        "- A non-bold trap. With another sentence after.\n\n"
        "## Key CLI\n"
    )
    skill_dir = _make_skill(tmp_path, body=body)
    lazy = LazySkillMetadata(skill_dir)
    assert lazy.gotchas == ["A non-bold trap."]


def test_gotchas_handles_inline_code_in_lead(tmp_path):
    body = (
        "## Gotchas\n\n"
        "- **`pydeseq2` requires `--sample-key` distinct from `--groupby`.** Long tail.\n\n"
        "## Key CLI\n"
    )
    skill_dir = _make_skill(tmp_path, body=body)
    lazy = LazySkillMetadata(skill_dir)
    assert lazy.gotchas == [
        "`pydeseq2` requires `--sample-key` distinct from `--groupby`."
    ]


def test_gotchas_stops_at_next_section_header(tmp_path):
    body = (
        "## Gotchas\n\n"
        "- **Real gotcha.** Detail.\n\n"
        "## Key CLI\n\n"
        "- This bullet is in CLI section, must NOT be treated as a gotcha.\n"
    )
    skill_dir = _make_skill(tmp_path, body=body)
    lazy = LazySkillMetadata(skill_dir)
    assert lazy.gotchas == ["Real gotcha."]


def test_gotchas_real_spatial_de_skill():
    """Empirical anchor: spatial-de SKILL.md has 6 documented Gotchas.
    If the parser drifts, this test catches it on real production content."""
    skill_dir = ROOT / "skills" / "spatial" / "spatial-de"
    if not skill_dir.exists():
        pytest.skip("spatial-de skill not present in this checkout")
    lazy = LazySkillMetadata(skill_dir)
    leads = lazy.gotchas
    assert len(leads) == 6, f"Expected 6 spatial-de gotchas, got {len(leads)}: {leads}"
    # Check signature lead sentences are present (substring match — robust to
    # minor punctuation edits but catches semantic drift).
    joined = " | ".join(leads)
    assert "--sample-key" in joined
    assert "--group1" in joined and "--group2" in joined
    assert "Counts-layer fallback" in joined
    assert "Paired design" in joined
    assert "Skipped sample-group bins" in joined
    assert "filter_markers" in joined


def test_gotchas_skips_indented_continuation_lines(tmp_path):
    body = (
        "## Gotchas\n\n"
        "- **First trap.** Tail line one.\n"
        "  Continuation indented under the bullet — must NOT be treated as a new bullet.\n"
        "- **Second trap.** Tail.\n\n"
        "## Key CLI\n"
    )
    skill_dir = _make_skill(tmp_path, body=body)
    lazy = LazySkillMetadata(skill_dir)
    assert lazy.gotchas == ["First trap.", "Second trap."]
