"""The ``use_skill`` tool: load one skill's instructions on demand.

The system prompt carries only the skill index; this tool is how the
model turns an index entry into the full ``SKILL.md`` body.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.function_tool import FunctionTool, ToolArgumentError

from .index import SkillIndex, SkillNotFound
from .skill import Skill

Annotator = Callable[[Skill, str], Awaitable[str]]
"""Given a skill and the body just read for it, the text to append to the result."""

__all__ = ["USE_SKILL_TOOL_NAME", "USE_SKILL_SCHEMA", "use_skill_tool"]

USE_SKILL_TOOL_NAME = "use_skill"

_DESCRIPTION = (
    "Load the full instructions for one skill. Call this before carrying "
    "out a task in a skill's domain: the system prompt lists only each "
    "skill's name and when to use it, and the methodology, parameters and "
    "commands live in the body this returns."
)

USE_SKILL_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_name": {
            "type": "string",
            "description": (
                "The skill to load, spelled exactly as the `name` in the "
                "skill index in the system prompt."
            ),
        },
    },
    "required": ["skill_name"],
    "additionalProperties": False,
}

_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=True,
    concurrency_safe=True,
    allowed_in_background=True,
    tags=frozenset({"skills", "inspection"}),
)
"""Declared rather than defaulted.

:class:`~omicsclaw.tools.base.ToolPolicy` defaults to ``HIGH`` + ``ASK``,
and approval fails closed when no channel is bound, so omitting a policy
would put a prompt in front of every skill load. The tool reads only
files already indexed at load time, and reads nothing the caller names.
"""


def use_skill_tool(
    index: SkillIndex,
    *,
    locate: bool = True,
    annotate: Annotator | None = None,
) -> FunctionTool:
    """Build a ``use_skill`` tool bound to *index*.

    *locate* appends the skill's directory to the returned text, which is
    what lets the model find the scripts and reference files that sit
    beside a ``SKILL.md`` but are rarely named inside it.

    *annotate*, when given, is awaited with the skill and the body just
    read, and what it returns is appended after the rest, separated by a
    blank line. If it raises, one line saying the environment check is
    unavailable is appended instead; the body is always returned. It does
    not change the tool's definition.

    No ``policy`` parameter: a deployment that disagrees with the default
    passes its own to
    :meth:`~omicsclaw.tools.registry.ToolRegistry.register`.
    """
    if annotate is None:

        def run(skill_name: str) -> str:
            return _load(index, skill_name, locate=locate)

    else:

        async def run(skill_name: str) -> str:
            content, skill = _read(index, skill_name)
            text = _located(content, skill, locate=locate)
            if skill is None:
                return text
            try:
                note = await annotate(skill, content)
            except Exception as exc:  # noqa: BLE001 - the body must survive a failing check
                note = f"---\nEnvironment check unavailable: {exc}"
            return f"{text}\n\n{note}" if note else text

    return FunctionTool(
        USE_SKILL_TOOL_NAME,
        _DESCRIPTION,
        run,
        parameters=USE_SKILL_SCHEMA,
        policy=_POLICY,
    )


def _load(index: SkillIndex, skill_name: str, *, locate: bool) -> str:
    """Return one skill's instructions, with its directory appended.

    :raises ToolArgumentError: the name is blank or not in the index,
        both of which the model can correct from the message.
    """
    content, skill = _read(index, skill_name)
    return _located(content, skill, locate=locate)


def _read(index: SkillIndex, skill_name: str) -> tuple[str, Skill | None]:
    """One skill's instructions and its record.

    :raises ToolArgumentError: the name is blank or not in the index.
    """
    name = skill_name.strip()
    if not name:
        raise ToolArgumentError(
            "input.skill_name is empty; give the `name` of a skill from the "
            "skill index in the system prompt"
        )

    try:
        content = index.get_full_content(name)
    except SkillNotFound as exc:
        raise ToolArgumentError(str(exc)) from exc

    return content, index.get(name)


def _located(content: str, skill: Skill | None, *, locate: bool) -> str:
    if not locate or skill is None:
        return content
    return f"{content}\n\n---\nSkill directory: {skill.directory}"
