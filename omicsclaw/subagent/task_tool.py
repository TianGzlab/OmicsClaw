"""``task``: the model's one way to hand work to a sub-agent."""

from __future__ import annotations

from omicsclaw.schema import ToolDefinition
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import (
    current_context,
    pause_tool_timeout,
    use_tool_context,
)
from omicsclaw.tools.function_tool import ToolArgumentError, decode_arguments

from .definition import TASK_TOOL_NAME, SubAgentDefinition
from .delegate import SUBAGENT_VALUE_KEY, Delegate
from .registry import SubAgentRegistry

__all__ = ["TASK_TOOL_POLICY", "RecursionRefused", "TaskTool"]

TASK_TOOL_POLICY = ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.AUTO,
    concurrency_safe=False,
    allowed_in_background=False,
)
"""Declared rather than defaulted, and each field for its own reason.

``HIGH``: a sub-agent can do whatever its tools can do, which by default
is everything the parent can.

``AUTO``: delegating is not itself the dangerous act — every tool the
sub-agent reaches keeps its own gate and its own approval prompt, and
those prompts still reach the person who started the parent turn. Asking
here as well would ask about work nobody can describe yet.

``concurrency_safe=False`` makes a delegation a barrier, so the rest of
the turn's tools wait rather than interleaving with a whole nested run.
"""

_DESCRIPTION_HEAD = (
    "Hand a self-contained sub-task to a specialised agent that runs with "
    "its own context and its own narrowed tool set, and return only its "
    "conclusion.\n"
    "Use it when a sub-task is well defined and its intermediate steps are "
    "noise for this conversation — a wide search, a survey of many files, a "
    "self-checking analysis. Do not use it for a step you can do in one or "
    "two tool calls yourself.\n"
    "The sub-agent cannot see this conversation, cannot ask you anything, "
    "and reports once when it is done. Available sub-agents:\n"
)


class RecursionRefused(RuntimeError):
    """A definition's own ``resolve_tools`` returned the delegation tool.

    What stops unbounded delegation is
    :meth:`~omicsclaw.subagent.SubAgentDefinition.resolve_tools` removing
    the name from every child tool set. This is a consistency check on
    that method, not a second check on the tool set a child was actually
    built with: the registry a sub-agent runs against is assembled behind
    :class:`~omicsclaw.subagent.Delegate` and never reaches this module.
    Raised rather than logged because a ``resolve_tools`` that no longer
    removes the name has no safe reading.
    """


class TaskTool:
    """The ``task`` tool, over one registry of sub-agents and one delegate.

    Its :meth:`definition` is built on every call from the registry, so a
    sub-agent loaded from a file appears in the ``subagent_type`` enum and
    in the description without anything else being told.
    """

    __slots__ = ("_delegate", "_registry")

    name = TASK_TOOL_NAME

    def __init__(self, registry: SubAgentRegistry, delegate: Delegate) -> None:
        self._registry = registry
        self._delegate = delegate

    @property
    def policy(self) -> ToolPolicy:
        """:data:`TASK_TOOL_POLICY`. Read by the registry at mount time."""
        return TASK_TOOL_POLICY

    def definition(self) -> ToolDefinition:
        """What the model is told, including who it may delegate to.

        The ``subagent_type`` enum and the per-agent lines in the
        description are the only thing the model chooses on, so both are
        rendered from the registry rather than written down twice.
        """
        catalogue = "\n".join(
            f"- {definition.name}: {definition.description}"
            for definition in self._registry.list()
        )
        return ToolDefinition(
            name=TASK_TOOL_NAME,
            description=_DESCRIPTION_HEAD + (catalogue or "- (none configured)"),
            input_schema={
                "type": "object",
                "properties": {
                    "subagent_type": {
                        "type": "string",
                        "description": "Which sub-agent to run.",
                        "enum": list(self._registry.names()),
                    },
                    "prompt": {
                        "type": "string",
                        "description": (
                            "The whole task. The sub-agent sees none of this "
                            "conversation, so state the goal, the file paths, "
                            "the constraints and what to report back."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "A 3-5 word title, shown to the user.",
                    },
                },
                "required": ["subagent_type", "prompt"],
                "additionalProperties": False,
            },
        )

    async def execute(self, arguments: str) -> str:
        """Run one delegation and return the sub-agent's conclusion.

        :raises ~omicsclaw.tools.function_tool.ToolArgumentError: the
            payload is malformed, names no sub-agent, or names one that is
            not registered — all correctable by the model, which is shown
            the available names.
        :raises RecursionRefused: the sub-agent would have been handed the
            delegation tool itself.

        The whole run happens inside
        :func:`~omicsclaw.tools.context.pause_tool_timeout`, because a
        delegation lasts many model calls and the per-tool timeout is
        sized for one. What bounds it instead is the deployment's turn
        deadline.

        The surrounding tool context is re-bound with the sub-agent's name
        added, so an approval prompt raised inside the delegation can say
        which agent is asking. Every other value, the approval channel and
        the progress sink are carried over explicitly.
        """
        payload = decode_arguments(arguments)
        definition = self._chosen(payload)
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ToolArgumentError(
                "input.prompt is required and must describe the whole task: "
                "the sub-agent cannot see this conversation"
            )
        self._refuse_recursion(definition)

        outer = current_context()
        with use_tool_context(
            approval=outer.approval,
            progress=outer.progress,
            values={**outer.values, SUBAGENT_VALUE_KEY: definition.name},
        ):
            with pause_tool_timeout():
                return await self._delegate.delegate(definition, prompt)

    def _chosen(self, payload: dict[str, object]) -> SubAgentDefinition:
        """The requested definition, or a complaint naming the real ones."""
        requested = str(payload.get("subagent_type") or "").strip()
        if not requested:
            raise ToolArgumentError(
                "input.subagent_type is required; available: "
                f"{self._available()}"
            )
        definition = self._registry.get(requested)
        if definition is None:
            raise ToolArgumentError(
                f"there is no sub-agent named {requested!r}; available: "
                f"{self._available()}"
            )
        return definition

    def _available(self) -> str:
        return ", ".join(self._registry.names()) or "none configured"

    @staticmethod
    def _refuse_recursion(definition: SubAgentDefinition) -> None:
        """Refuse a definition whose ``resolve_tools`` yields this tool.

        :raises RecursionRefused: ``resolve_tools`` returned the tool's own
            name, which it must never do.

        Checks the definition, not the registry the child is given —
        that one is built by the delegate and is not visible from here.
        """
        if TASK_TOOL_NAME in definition.resolve_tools((TASK_TOOL_NAME,)):
            raise RecursionRefused(
                f"sub-agent {definition.name!r} resolved {TASK_TOOL_NAME!r} into "
                "its own tool set, which would let it delegate again without "
                "bound; refusing the delegation"
            )
