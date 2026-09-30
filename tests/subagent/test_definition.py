"""What a sub-agent must declare, and which tools that resolves to.

``resolve_tools`` is three rules stacked — an allow-list, a deny-list and
one unconditional removal — plus an ordering guarantee that is not
cosmetic: the tool table sits inside the region every vendor's
prompt-prefix cache keys on, so a sub-agent that reorders it is a
sub-agent that re-bills the prefix it could have shared.

Plan 0046 §4 and §6, first row. The unconditional removal is **the**
guard against unbounded delegation — the check in ``TaskTool`` beside it
reads the definition, not the registry the child was built with (§6's
correction) — and it has a mutation test beside it: delete the ``name != TASK_TOOL_NAME`` clause and
``test_the_delegation_tool_is_always_removed`` must go red.
"""

from __future__ import annotations

import pytest

from omicsclaw.subagent import TASK_TOOL_NAME, InvalidDefinition, SubAgentDefinition

PARENT = ("read_file", "write_file", "bash", "use_skill", "task")


def _definition(**overrides: object) -> SubAgentDefinition:
    fields: dict[str, object] = {
        "name": "surveyor",
        "description": "Surveys a tree of files",
        "system_prompt": "You survey.",
    }
    fields.update(overrides)
    return SubAgentDefinition(**fields)  # type: ignore[arg-type]


# ---- validate ------------------------------------------------------------


def test_a_complete_definition_validates():
    _definition().validate()


@pytest.mark.parametrize("name", ["", "Surveyor", "-leading", "with space", "a_b"])
def test_an_unusable_name_is_refused(name: str):
    """The name is what the model sends as ``subagent_type``."""
    with pytest.raises(InvalidDefinition):
        _definition(name=name).validate()


@pytest.mark.parametrize("name", ["a", "general-purpose", "9lives", "x-y-z"])
def test_a_usable_name_is_accepted(name: str):
    _definition(name=name).validate()


def test_a_definition_without_a_description_is_refused():
    """The description is the only thing the model chooses on."""
    with pytest.raises(InvalidDefinition, match="description"):
        _definition(description="  ").validate()


def test_a_definition_without_a_system_prompt_is_refused():
    with pytest.raises(InvalidDefinition, match="system prompt"):
        _definition(system_prompt="\n").validate()


# ---- resolve_tools -------------------------------------------------------


def test_an_empty_allow_list_inherits_everything_but_the_delegation_tool():
    assert _definition().resolve_tools(PARENT) == (
        "read_file",
        "write_file",
        "bash",
        "use_skill",
    )


def test_an_allow_list_intersects_rather_than_adds():
    """A name the parent does not have cannot be conjured by asking."""
    resolved = _definition(tools=("read_file", "no_such_tool")).resolve_tools(PARENT)

    assert resolved == ("read_file",)


def test_the_deny_list_applies_after_the_allow_list():
    resolved = _definition(
        tools=("read_file", "write_file", "bash"),
        disallowed_tools=("bash",),
    ).resolve_tools(PARENT)

    assert resolved == ("read_file", "write_file")


def test_the_deny_list_applies_to_an_inherited_set_too():
    resolved = _definition(disallowed_tools=("bash", "write_file")).resolve_tools(
        PARENT
    )

    assert resolved == ("read_file", "use_skill")


def test_the_delegation_tool_is_always_removed():
    """Both ways of asking for it, refused — this is the guard itself.

    Mutation: drop the ``name != TASK_TOOL_NAME`` clause from
    ``resolve_tools`` and this goes red on the first assertion.
    """
    assert TASK_TOOL_NAME not in _definition().resolve_tools(PARENT)
    assert TASK_TOOL_NAME not in _definition(
        tools=("read_file", TASK_TOOL_NAME)
    ).resolve_tools(PARENT)


def test_the_parent_order_is_kept_not_the_allow_list_order():
    """The tool table is part of a cached prompt prefix (plan 0028)."""
    resolved = _definition(tools=("bash", "read_file")).resolve_tools(PARENT)

    assert resolved == ("read_file", "bash")


def test_resolving_over_nothing_yields_nothing():
    assert _definition(tools=("read_file",)).resolve_tools(()) == ()
