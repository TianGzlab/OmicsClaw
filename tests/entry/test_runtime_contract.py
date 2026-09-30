"""The runtime contract: one file beside the skill tree, at the top of the prompt.

``OMICSCLAW.md`` is read from ``AppConfig.repo_root()`` — the directory that
holds ``skills/`` — so the contract travels with the skills the agent is told
to use. Without a ``skills_dir`` that directory is the workspace itself. A
workspace's own ``OMICSCLAW.md`` is not read when the skill tree lives
elsewhere, and the pre-split pair ``SOUL.md`` + ``CLAUDE.md`` is not read at
all: there is one source for the agent's instructions, and the safety rules
are the ``SAFETY_RULES`` constant, stated once.

The last three tests read the checkout's real files. They are the guards on
the split itself: the disclaimer must not be copied back into the contract,
the product persona must stay out of ``CLAUDE.md`` (which Claude Code loads
into development sessions), and developer instructions must stay out of the
contract (which the analysis agent reads every turn).
"""

from __future__ import annotations

import pathlib

from omicsclaw.entry.assembly import build_prompt, default_sections
from omicsclaw.entry.config import AppConfig, SkillsIndex

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

DISCLAIMER = (
    "OmicsClaw is a research and educational tool for multi-omics "
    "analysis. It is not a medical device and does not provide "
    "clinical diagnoses. Consult a domain expert before making "
    "decisions based on these results."
)


def _render(config: AppConfig) -> str:
    return build_prompt(default_sections(config)).render().system_prompt


def _rendered_keys(config: AppConfig) -> tuple[str, ...]:
    """Keys of the sections that survive rendering; an empty file's section does not."""
    stats = build_prompt(default_sections(config)).render().section_stats
    return tuple(key for key, _tokens in stats)


def test_a_workspace_that_is_the_checkout_reads_its_contract(tmp_path):
    """Started in the checkout with no ``skills_dir``: the workspace is the checkout."""
    (tmp_path / "OMICSCLAW.md").write_text("CHECKOUT-CONTRACT", encoding="utf-8")
    config = AppConfig(workspace=tmp_path)

    assert _render(config).count("CHECKOUT-CONTRACT") == 1
    assert _rendered_keys(config)[0] == "contract"


def test_the_contract_comes_from_beside_the_skill_tree(tmp_path):
    """A data directory with ``skills_dir`` pointing into a checkout.

    The checkout's contract is read; the data directory's own copy is not.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OMICSCLAW.md").write_text("CONTRACT-FROM-REPO", encoding="utf-8")
    workspace = tmp_path / "data"
    workspace.mkdir()
    (workspace / "OMICSCLAW.md").write_text("WORKSPACE-SENTINEL", encoding="utf-8")
    config = AppConfig(workspace=workspace, skills_dir=repo / "skills")

    system = _render(config)

    assert "CONTRACT-FROM-REPO" in system
    assert "WORKSPACE-SENTINEL" not in system


def test_without_a_skills_dir_the_workspace_is_the_checkout(tmp_path):
    """A data directory started without ``skills_dir`` is its own checkout.

    Its ``OMICSCLAW.md``, if it has one, is the whole contract.
    """
    workspace = tmp_path / "data"
    workspace.mkdir()
    (workspace / "OMICSCLAW.md").write_text("DATA-DIR-CONTRACT", encoding="utf-8")

    assert "DATA-DIR-CONTRACT" in _render(AppConfig(workspace=workspace))


def test_neither_file_leaves_safety_rules_first(tmp_path):
    """No contract anywhere, and the prompt opens with the safety rules."""
    config = AppConfig(workspace=tmp_path, skills_dir=tmp_path / "repo" / "skills")

    assert _rendered_keys(config)[0] == "safety"
    assert _render(config).startswith("## Safety rules")


def test_the_old_layout_is_not_read(tmp_path):
    """A workspace still holding ``SOUL.md`` and ``CLAUDE.md`` gets neither."""
    (tmp_path / "SOUL.md").write_text("SOUL-SENTINEL", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("CLAUDE-SENTINEL", encoding="utf-8")

    system = _render(AppConfig(workspace=tmp_path))

    assert "SOUL-SENTINEL" not in system
    assert "CLAUDE-SENTINEL" not in system
    assert "## Project contract" not in system


def test_a_relative_skills_dir_is_read_from_the_process_directory(
    tmp_path, monkeypatch
):
    """A relative ``skills_dir`` resolves against the process directory.

    The skill scan resolves it the same way.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "repo").mkdir()
    contract = tmp_path / "repo" / "OMICSCLAW.md"
    contract.write_text("RELATIVE-CONTRACT", encoding="utf-8")
    workspace = tmp_path / "data"
    workspace.mkdir()
    config = AppConfig(workspace=workspace, skills_dir=pathlib.Path("repo/skills"))

    assert "RELATIVE-CONTRACT" in _render(config)


def test_the_real_prompt_states_the_disclaimer_once(tmp_path):
    """The checkout's contract rendered with ``SAFETY_RULES``: one disclaimer.

    A contract that copied the safety rules back in would state it twice,
    in two wordings that can drift apart.
    """
    config = AppConfig(
        workspace=tmp_path,
        skills_dir=_REPO_ROOT / "skills",
        skills_index=SkillsIndex.OFF,
    )

    assert _rendered_keys(config)[0] == "contract"
    assert _render(config).count(DISCLAIMER) == 1


def test_the_real_contract_names_the_agent_and_claude_md_does_not():
    contract = (_REPO_ROOT / "OMICSCLAW.md").read_text(encoding="utf-8")
    claude_md = (_REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "You are **OmicsClaw**" in contract
    assert "You are **OmicsClaw**" not in claude_md
    assert "You are OmicsClaw" not in claude_md


def test_the_real_contract_carries_no_developer_instructions():
    contract = (_REPO_ROOT / "OMICSCLAW.md").read_text(encoding="utf-8")

    for marker in (
        "Repository Maintenance Contract",
        "gh issue",
        "pip install -e",
        "ROUTING-TABLE",
        "## Safety Rules",
    ):
        assert marker not in contract, marker
