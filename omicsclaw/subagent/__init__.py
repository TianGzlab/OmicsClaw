"""``omicsclaw/subagent`` — handing a bounded sub-task to a second agent.

A sub-agent is not a new kind of thing: it is one more run of the same
engine, opened with its own system prompt, given a narrowed set of the
parent's tools, and handed no conversation at all. What comes back is one
piece of text::

    from omicsclaw.subagent import SubAgentRegistry, TaskTool

    agents = SubAgentRegistry([definition])
    registry.register(TaskTool(agents, runner))     # once, per app

Seven modules, each a different kind of thing:

``definition``
    What a sub-agent is, and which parent tools it resolves to.
``registry``
    The sub-agents a deployment offers, in a stable order.
``frontmatter`` / ``loader``
    Reading definitions out of a directory of Markdown files.
``prompt``
    The system prompt a delegated run opens with.
``delegate``
    The seam that actually runs one, declared here and satisfied above.
``task_tool``
    The model's one way in.

**This package does not build engines.** Constructing a child engine
needs a provider, a tool registry and a deployment's sandbox state, which
are the composition root's to hold; :class:`~omicsclaw.subagent.Delegate`
is how the work leaves this layer without it learning any of that.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools`` and the
standard library — the same whitelist as :mod:`omicsclaw.planning`, and
for the same reason: ``task`` declares its own
:class:`~omicsclaw.tools.ToolPolicy` and holds the engine's timeout pause
for the length of a delegation. Nothing here imports
``omicsclaw.engine``, ``omicsclaw.entry`` or ``omicsclaw.skills``, and
importing this package pulls none of them in: :class:`ChildPrompt`
satisfies the engine's prompt seam structurally rather than by
inheriting from it, and :class:`Delegate` is a Protocol the composition
root supplies an implementation of.
"""

from .definition import TASK_TOOL_NAME, InvalidDefinition, SubAgentDefinition
from .delegate import SUBAGENT_VALUE_KEY, Delegate
from .frontmatter import parse_agent_file
from .loader import LoadErrorSink, load_agents
from .prompt import ChildPrompt, SkillLoader
from .registry import SubAgentRegistry
from .task_tool import TASK_TOOL_POLICY, RecursionRefused, TaskTool

__all__ = [
    "SUBAGENT_VALUE_KEY",
    "TASK_TOOL_NAME",
    "TASK_TOOL_POLICY",
    "ChildPrompt",
    "Delegate",
    "InvalidDefinition",
    "LoadErrorSink",
    "RecursionRefused",
    "SkillLoader",
    "SubAgentDefinition",
    "SubAgentRegistry",
    "TaskTool",
    "load_agents",
    "parse_agent_file",
]
