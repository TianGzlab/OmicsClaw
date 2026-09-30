"""``use_skill`` with and without an environment-check callback (plan 0061 case 11).

Without a callback the tool must return exactly what it returned before the
parameter existed; ``fixtures/golden/use_skill_off.txt`` and
``use_skill_definition.json`` were recorded from the unmodified tool, with
the fixture root replaced by ``<root>``. With one, the note goes after the
skill directory, and a failing callback costs one line, never the body.
"""

from __future__ import annotations

import asyncio
import json

from omicsclaw.skills import load_skills, use_skill_tool

from .conftest import FIXTURE_SKILLS, FIXTURES

GOLDEN = FIXTURES / "golden"


def _index():
    return load_skills(FIXTURE_SKILLS)


def _call(tool) -> str:
    return asyncio.run(tool.execute(json.dumps({"skill_name": "demo-skill"})))


def _definition(tool) -> dict:
    d = tool.definition()
    return {"name": d.name, "description": d.description, "input_schema": d.input_schema}


def test_without_a_callback_the_output_is_unchanged():
    out = _call(use_skill_tool(_index())).replace(str(FIXTURE_SKILLS.resolve()), "<root>")
    assert out == (GOLDEN / "use_skill_off.txt").read_text(encoding="utf-8")


def test_the_definition_does_not_depend_on_the_callback():
    recorded = json.loads((GOLDEN / "use_skill_definition.json").read_text(encoding="utf-8"))

    async def annotate(skill, body):
        return "---\nnote"

    assert _definition(use_skill_tool(_index())) == recorded
    assert _definition(use_skill_tool(_index(), annotate=annotate)) == recorded


def test_the_note_follows_the_directory_and_sees_the_same_body():
    seen = []

    async def annotate(skill, body):
        seen.append((skill.name, body))
        return "---\nEnvironment check: fine"

    plain = _call(use_skill_tool(_index()))
    out = _call(use_skill_tool(_index(), annotate=annotate))
    assert out == plain + "\n\n---\nEnvironment check: fine"
    name, body = seen[0]
    assert name == "demo-skill"
    assert plain.startswith(body)


def test_a_failing_callback_still_returns_the_body():
    async def annotate(skill, body):
        raise RuntimeError("probe exploded")

    plain = _call(use_skill_tool(_index()))
    out = _call(use_skill_tool(_index(), annotate=annotate))
    assert out.startswith(plain)
    assert out[len(plain):] == "\n\n---\nEnvironment check unavailable: probe exploded"
