"""The index, plugged into the prompt composer it exists to feed.

The two packages do not import each other; a composition root joins them.
These tests are that composition root, written down, so the seam is
pinned by something rather than by an example in a docstring.
"""

from __future__ import annotations

from omicsclaw.context import PromptAssembler, Section, assemble, static

from omicsclaw.skills import load_skills

from .test_loader import write_skill


def build(tmp_path):
    write_skill(tmp_path / "spatial" / "spatial-de", "spatial-de", "does spatial DE")
    write_skill(tmp_path / "genomics" / "genomics-qc", "genomics-qc", "does QC")
    return load_skills(tmp_path)


def test_the_index_renders_as_a_prompt_section(tmp_path):
    index = build(tmp_path)

    prompt = (
        PromptAssembler()
        .with_section(Section("persona", "", static("You are OmicsClaw.")))
        .with_section(Section("skills", "## Available skills", index.prompt_body))
        .render()
    )

    assert [key for key, _ in prompt.section_stats] == ["persona", "skills"]
    assert "## Available skills" in prompt.system_prompt
    assert "`use_skill`" in prompt.system_prompt
    assert "- spatial-de: does spatial DE" in prompt.system_prompt


def test_an_empty_index_makes_the_whole_section_disappear(tmp_path):
    """Not a heading over nothing: the section is dropped, heading included."""
    index = load_skills(tmp_path / "absent")

    prompt = (
        PromptAssembler()
        .with_section(Section("persona", "", static("You are OmicsClaw.")))
        .with_section(Section("skills", "## Available skills", index.prompt_body))
        .render()
    )

    assert [key for key, _ in prompt.section_stats] == ["persona"]
    assert "Available skills" not in prompt.system_prompt


def test_the_section_reaches_the_conversation_as_message_zero(tmp_path):
    index = build(tmp_path)
    prompt = (
        PromptAssembler()
        .with_section(Section("skills", "## Available skills", index.prompt_body))
        .render()
    )

    conversation = assemble(prompt, [], "分析这份 Visium 数据")

    assert "genomics-qc" in conversation[0].content
    assert conversation[-1].content == "分析这份 Visium 数据"


def test_a_bound_index_is_a_snapshot_and_a_rescan_closure_is_not(tmp_path):
    """A skill written mid-run needs a rescan; binding an index is a snapshot.

    Both are legitimate. The snapshot is cheaper and keeps the prompt
    prefix stable; the closure costs a rescan per render — about 20 ms
    over this repository's 96 skills — and is what a deployment whose
    agent creates skills at runtime wants.
    """
    index = build(tmp_path)
    frozen = Section("skills", "## Available skills", index.prompt_body)
    live = Section(
        "skills",
        "## Available skills",
        lambda: load_skills(tmp_path).prompt_body(),
    )

    write_skill(tmp_path / "spatial" / "spatial-new", "spatial-new", "brand new")

    snapshot = PromptAssembler().with_section(frozen).render().system_prompt
    rescanned = PromptAssembler().with_section(live).render().system_prompt

    assert "spatial-new" not in snapshot
    assert "spatial-new" in rescanned


def test_the_compact_index_is_the_cheaper_section(tmp_path):
    """Sized like the real corpus, where descriptions average 288 characters.

    The saving comes from dropping those, so it only shows above the
    point where they outweigh the per-domain grouping line: with two
    short descriptions the compact form is the *larger* of the two.
    """
    for domain in ("spatial", "singlecell", "genomics"):
        for number in range(6):
            write_skill(
                tmp_path / domain / f"{domain}-{number}",
                f"{domain}-{number}",
                f"Load when {'x' * 140}. Skip when {'y' * 130}.",
            )
    index = load_skills(tmp_path)

    full = (
        PromptAssembler()
        .with_section(Section("skills", "## Available skills", index.prompt_body))
        .render()
    )
    compact = (
        PromptAssembler()
        .with_section(
            Section(
                "skills",
                "## Available skills",
                lambda: index.prompt_body(compact=True),
            )
        )
        .render()
    )

    assert compact.total_estimated_tokens < full.total_estimated_tokens / 4
    assert "Skip when" not in compact.system_prompt
    assert "spatial-0" in compact.system_prompt
