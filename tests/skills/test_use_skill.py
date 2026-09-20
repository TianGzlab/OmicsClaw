"""The ``use_skill`` tool."""

from __future__ import annotations

import asyncio
import json

import pytest

from omicsclaw.tools import ApprovalMode, RiskLevel, Tool, ToolRegistry
from omicsclaw.tools.function_tool import ToolArgumentError
from omicsclaw.schema import ToolCall

from omicsclaw.skills import (
    USE_SKILL_TOOL_NAME,
    SkillIndex,
    load_skills,
    use_skill_tool,
)

from .test_loader import write_skill


def run(tool, **arguments) -> str:
    """Execute *tool* the way the registry does, with a raw JSON payload."""
    return asyncio.run(tool.execute(json.dumps(arguments)))


def test_the_tool_is_called_use_skill():
    tool = use_skill_tool(SkillIndex())

    assert tool.name == USE_SKILL_TOOL_NAME == "use_skill"
    assert tool.definition().name == "use_skill"


def test_the_tool_satisfies_the_tool_protocol():
    assert isinstance(use_skill_tool(SkillIndex()), Tool)


def test_the_definition_asks_for_one_required_string():
    schema = use_skill_tool(SkillIndex()).definition().input_schema

    assert schema["required"] == ["skill_name"]
    assert schema["properties"]["skill_name"]["type"] == "string"
    assert schema["additionalProperties"] is False


def test_the_definition_says_nothing_about_policy():
    """Policy is what this machine permits; a model must not read it."""
    rendered = json.dumps(
        {
            "description": use_skill_tool(SkillIndex()).definition().description,
            "schema": use_skill_tool(SkillIndex()).definition().input_schema,
        }
    )

    for leak in ("risk_level", "approval_mode", "read_only", "concurrency_safe"):
        assert leak not in rendered


def test_loading_a_skill_is_automatic_and_read_only():
    """Left to the guarded defaults, every skill load would need approval."""
    policy = use_skill_tool(SkillIndex()).policy

    assert policy.approval_mode is ApprovalMode.AUTO
    assert policy.risk_level is RiskLevel.LOW
    assert policy.read_only
    assert policy.concurrency_safe


def test_it_returns_the_skill_body(tmp_path):
    write_skill(tmp_path / "spatial" / "spatial-de", "spatial-de")
    tool = use_skill_tool(load_skills(tmp_path))

    output = run(tool, skill_name="spatial-de")

    assert "Instructions for spatial-de." in output
    assert "description:" not in output


def test_it_appends_the_skill_directory(tmp_path):
    """Only 2 of the 96 real bodies say where their own scripts live."""
    write_skill(tmp_path / "spatial" / "spatial-de", "spatial-de")
    tool = use_skill_tool(load_skills(tmp_path))

    output = run(tool, skill_name="spatial-de")

    assert output.endswith(f"Skill directory: {tmp_path / 'spatial' / 'spatial-de'}")


def test_the_directory_footer_can_be_turned_off(tmp_path):
    write_skill(tmp_path / "a", "a")
    tool = use_skill_tool(load_skills(tmp_path), locate=False)

    assert run(tool, skill_name="a") == "# a\n\nInstructions for a."


def test_surrounding_whitespace_in_the_name_is_tolerated(tmp_path):
    write_skill(tmp_path / "a", "a")
    tool = use_skill_tool(load_skills(tmp_path))

    assert "Instructions for a." in run(tool, skill_name="  a\n")


def test_an_unknown_name_is_a_correctable_argument_error(tmp_path):
    write_skill(tmp_path / "spatial-de", "spatial-de")
    tool = use_skill_tool(load_skills(tmp_path))

    with pytest.raises(ToolArgumentError) as caught:
        run(tool, skill_name="spatial-dee")

    assert "spatial-de" in str(caught.value)


def test_an_empty_name_is_refused_by_name():
    tool = use_skill_tool(SkillIndex())

    with pytest.raises(ToolArgumentError) as caught:
        run(tool, skill_name="   ")

    assert "input.skill_name" in str(caught.value)


def test_a_missing_argument_is_refused():
    tool = use_skill_tool(SkillIndex())

    with pytest.raises(ToolArgumentError):
        run(tool)


def test_a_wrongly_typed_argument_is_refused():
    tool = use_skill_tool(SkillIndex())

    with pytest.raises(ToolArgumentError):
        run(tool, skill_name=7)


def test_an_unreadable_payload_is_refused():
    tool = use_skill_tool(SkillIndex())

    with pytest.raises(ToolArgumentError):
        asyncio.run(tool.execute("{not json"))


def test_a_traversal_in_the_name_reads_nothing(tmp_path):
    write_skill(tmp_path / "a", "a")
    (tmp_path / "secret.md").write_text("top secret", encoding="utf-8")
    tool = use_skill_tool(load_skills(tmp_path))

    with pytest.raises(ToolArgumentError):
        run(tool, skill_name="../secret.md")


def test_the_registry_reports_a_failed_load_as_a_correctable_observation(tmp_path):
    """Through the registry, a bad name is an Observation rather than a crash."""
    write_skill(tmp_path / "a", "a")
    registry = ToolRegistry()
    registry.register(use_skill_tool(load_skills(tmp_path)))

    result = asyncio.run(
        registry.execute(
            ToolCall(id="1", name="use_skill", arguments='{"skill_name": "b"}')
        )
    )

    assert result.is_error
    assert "no skill named 'b'" in result.output


def test_the_registry_runs_a_good_load_without_an_approval_channel(tmp_path):
    """Approval fails closed everywhere, so AUTO is what makes this work."""
    write_skill(tmp_path / "a", "a")
    registry = ToolRegistry()
    registry.register(use_skill_tool(load_skills(tmp_path)))

    result = asyncio.run(
        registry.execute(
            ToolCall(id="1", name="use_skill", arguments='{"skill_name": "a"}')
        )
    )

    assert not result.is_error
    assert "Instructions for a." in result.output


def test_the_tool_sees_skills_added_after_it_was_built(tmp_path):
    """The index is bound, not copied; a reload does not need a new tool."""
    write_skill(tmp_path / "a", "a")
    index = load_skills(tmp_path)
    tool = use_skill_tool(index)
    write_skill(tmp_path / "b", "b")

    with pytest.raises(ToolArgumentError):
        run(tool, skill_name="b")

    reloaded = use_skill_tool(load_skills(tmp_path))
    assert "Instructions for b." in run(reloaded, skill_name="b")
