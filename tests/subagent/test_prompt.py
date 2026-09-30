"""The prompt a delegated run opens with.

Plan 0046 §3.4 and §3.5. Two properties are load-bearing rather than
cosmetic. The first is structural: ``ChildPrompt`` satisfies both halves
of the engine's prompt seam — ``render()`` and ``system_prompt`` — with
no adapter and without this package importing the engine, which is what
``tests/subagent/test_subagent_is_a_leaf_layer.py`` then enforces. The
second is the execution-environment block: a sub-agent reuses the
parent's ``bash``, so a prompt that describes the wrong environment
describes the wrong blast radius.

(This file is not in the plan's §10 test table, which lists five. The
module it covers is in the §10 delivery table, and leaving a delivered
module to be exercised only through the entry wiring would test it
through two layers of somebody else's code.)
"""

from __future__ import annotations

from omicsclaw.subagent import ChildPrompt


def test_render_returns_the_prompt_itself():
    """One object satisfies ``PromptSource`` and ``RenderedPrompt`` both."""
    prompt = ChildPrompt(instructions="Work.")

    assert prompt.render() is prompt
    assert prompt.render().system_prompt == "Work."


def test_the_instructions_come_first():
    prompt = ChildPrompt(instructions="Work.", workspace="/data/run")

    assert prompt.system_prompt.startswith("Work.")


def test_the_workspace_is_stated_when_there_is_one():
    prompt = ChildPrompt(instructions="Work.", workspace="/data/run")

    assert "/data/run" in prompt.system_prompt


def test_no_workspace_leaves_no_empty_heading():
    prompt = ChildPrompt(instructions="Work.")

    assert "Working directory" not in prompt.system_prompt


def test_the_execution_environment_is_carried_verbatim():
    prompt = ChildPrompt(
        instructions="Work.",
        environment="## Execution sandbox\n\n- bash runs in a container",
    )

    assert "- bash runs in a container" in prompt.system_prompt


def test_the_environment_block_follows_the_workspace():
    prompt = ChildPrompt(
        instructions="Work.",
        workspace="/data/run",
        environment="## Execution sandbox\n\n- degraded",
    )
    text = prompt.system_prompt

    assert text.index("/data/run") < text.index("degraded")


def test_named_skills_are_appended_in_order():
    prompt = ChildPrompt(
        instructions="Work.",
        skills=("spatial-de", "spatial-domains"),
        loader=lambda name: f"body of {name}",
    )
    text = prompt.system_prompt

    assert text.index("body of spatial-de") < text.index("body of spatial-domains")


def test_a_skill_that_will_not_load_is_skipped_rather_than_raised():
    """A missing reference is worth less than the delegation it would cancel."""

    def loader(name: str) -> str:
        if name == "missing":
            raise LookupError(name)
        return f"body of {name}"

    prompt = ChildPrompt(
        instructions="Work.", skills=("missing", "spatial-de"), loader=loader
    )

    assert "body of spatial-de" in prompt.system_prompt
    assert "missing" not in prompt.system_prompt


def test_a_skill_that_loads_as_blank_adds_no_heading():
    prompt = ChildPrompt(
        instructions="Work.", skills=("spatial-de",), loader=lambda name: "   "
    )

    assert "Skill:" not in prompt.system_prompt


def test_without_a_loader_the_named_skills_are_not_reached():
    prompt = ChildPrompt(instructions="Work.", skills=("spatial-de",))

    assert prompt.system_prompt == "Work."
