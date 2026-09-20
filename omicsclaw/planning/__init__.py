"""``omicsclaw/planning`` — the plan the agent keeps, and keeps seeing.

Plan 0039, the layer that makes a long task survive its own context. The
main loop can already act, use tools and compact its history; what it
could not do is *remember what it set out to do* once the turns that said
so had been summarized away. A plan is that memory, held outside the
conversation and put back in front of the model before every call::

    from omicsclaw.planning import PlanBook, PlanInjector, plan_write_tool

    book = PlanBook(FilePlanArchive(workspace / ".omicsclaw" / "plans"))
    registry.register(plan_write_tool(book))                 # once, per app
    injector = PlanInjector(book.for_session(session_id))    # per exchange
    result = await engine.run(messages, augmentor=injector)

Four pieces, and each is a different kind of thing, which is why they are
four modules rather than one:

``plan`` / ``rules``
    The state, and what may be said about it. Standard library only.
``tool``
    The model's one way in. ``plan_write``, read and write modes,
    refusing a write that would record progress that did not happen.
``injector``
    Re-injection before every model call, plus a nudge for a run that has
    explored for a long time without writing anything down.
``archive`` / ``book``
    One plan per session, written through to disk as it changes, restored
    when a session resumes.

**Planning is native, not a mode.** There is no switch a person flips to
"enter planning" — the reference harness removed exactly that and said so
(``plan.go:3-5``). What decides whether a task gets a plan is the model,
reading :data:`~omicsclaw.planning.guidance.PLANNING_GUIDANCE` in its
system prompt.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools`` and the
standard library — the same whitelist as :mod:`omicsclaw.skills`, and
for the same reason: ``plan_write`` declares its own
:class:`~omicsclaw.tools.ToolPolicy`, and the guarded defaults would put
a human approval prompt in front of every plan update. Notably **not**
``omicsclaw.engine``: :class:`PlanInjector` satisfies that layer's
``TurnAugmentor`` structurally, and ``tests/planning/`` runs the real
code paths in a subprocess and then asserts no ``omicsclaw.engine``,
``omicsclaw.context`` or ``omicsclaw.entry`` is in ``sys.modules``.
"""

from .archive import (
    FilePlanArchive,
    PlanArchive,
    PlanArchiveError,
    dump_items,
    load_items,
    safe_name,
)
from .book import ArchiveErrorSink, PlanBook
from .guidance import PLANNING_GUIDANCE, PLANNING_SECTION_HEADING
from .injector import (
    DEFAULT_GATE_TURNS,
    PLANNING_GATE_TEXT,
    PROGRESS_TOOL_NAMES,
    PlanInjector,
)
from .plan import PlanItem, PlanStatus, PlanStore, PlanWriteSink
from .render import DOCUMENT_TITLE, INJECTION_HEADER, format_plan, render_document
from .rules import MAX_DIRECT_COMPLETIONS, PlanRefused, apply, merge, validate
from .tool import (
    PLAN_WRITE_SCHEMA,
    PLAN_WRITE_TOOL_NAME,
    SESSION_VALUE_KEY,
    plan_write_tool,
)

__all__ = [
    "ArchiveErrorSink",
    "DEFAULT_GATE_TURNS",
    "DOCUMENT_TITLE",
    "FilePlanArchive",
    "INJECTION_HEADER",
    "MAX_DIRECT_COMPLETIONS",
    "PLANNING_GATE_TEXT",
    "PLANNING_GUIDANCE",
    "PLANNING_SECTION_HEADING",
    "PLAN_WRITE_SCHEMA",
    "PLAN_WRITE_TOOL_NAME",
    "PROGRESS_TOOL_NAMES",
    "PlanArchive",
    "PlanArchiveError",
    "PlanBook",
    "PlanInjector",
    "PlanItem",
    "PlanRefused",
    "PlanStatus",
    "PlanStore",
    "PlanWriteSink",
    "SESSION_VALUE_KEY",
    "apply",
    "dump_items",
    "format_plan",
    "load_items",
    "merge",
    "plan_write_tool",
    "render_document",
    "safe_name",
    "validate",
]
