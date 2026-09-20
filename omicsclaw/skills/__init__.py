"""``omicsclaw.skills`` — the Skill loader.

Skills are the third source the prompt composer draws on, after the
engine's own minimal core and the workspace's ``AGENTS.md``. They are
disclosed progressively: the system prompt carries one line per skill,
and the ``use_skill`` tool loads a body when the model needs one. Over
this repository's 96 skills that is roughly 8.5k tokens of index against
125k tokens of instructions.

Wiring one up takes three lines at a composition root::

    from omicsclaw.context import Section
    from omicsclaw.skills import load_skills, use_skill_tool

    index = load_skills(workdir / "skills")   # absent directory → empty
    assembler = assembler.with_section(
        Section("skills", "## Available skills", index.prompt_body)
    )
    registry.register(use_skill_tool(index))

An empty index renders an empty body, and a section with an empty body
is dropped, so the block disappears rather than announcing that there
are no skills.

Binding ``index.prompt_body`` binds a **snapshot**: a skill written while
the agent runs is not in it. A deployment whose agent creates skills at
runtime passes a closure that rescans instead, which costs about 20 ms
per render over 96 skills::

    Section("skills", "## Available skills",
            lambda: load_skills(root).prompt_body())

Inside the ``omicsclaw`` namespace this package imports
``omicsclaw.schema`` and ``omicsclaw.tools`` and nothing else — in
particular not ``omicsclaw.skill`` (singular), the legacy skill system,
whose name differs by one letter. ``tests/skills/
test_skills_is_a_leaf_layer.py`` enforces that by running the package in
a subprocess and inspecting what was actually imported.
"""

from __future__ import annotations

from .frontmatter import Frontmatter, parse_frontmatter
from .index import SkillIndex, SkillNotFound, SkipReason, SkippedSkill
from .loader import SKILL_FILENAME, SkillLoadError, load_skills
from .skill import Skill
from .use_skill import USE_SKILL_SCHEMA, USE_SKILL_TOOL_NAME, use_skill_tool

__all__ = [
    "Frontmatter",
    "SKILL_FILENAME",
    "Skill",
    "SkillIndex",
    "SkillLoadError",
    "SkillNotFound",
    "SkipReason",
    "SkippedSkill",
    "USE_SKILL_SCHEMA",
    "USE_SKILL_TOOL_NAME",
    "load_skills",
    "parse_frontmatter",
    "use_skill_tool",
]
