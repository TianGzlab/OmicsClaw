"""``plan_write``: the only way a model changes its plan.

Plan 0039 §3. One tool with two modes, following the reference harness
(``plan_write.go:4-6``): send ``steps`` to write, omit it to read. One
tool rather than two because a model that has just been refused needs to
see the authoritative list, and making it call a second tool to get it is
a turn spent on plumbing.

**The tool is thin on purpose.** It decodes arguments, resolves which
session is asking, calls :func:`~omicsclaw.planning.rules.apply`, and
serialises the answer. The rules it enforces are not here — see
:mod:`omicsclaw.planning.rules` for why.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import context_value
from omicsclaw.tools.function_tool import FunctionTool, ToolArgumentError

from .book import PlanBook
from .plan import PlanItem, PlanStatus
from .rules import PlanRefused, apply

__all__ = [
    "PLAN_WRITE_SCHEMA",
    "PLAN_WRITE_TOOL_NAME",
    "SESSION_VALUE_KEY",
    "plan_write_tool",
]

PLAN_WRITE_TOOL_NAME = "plan_write"

SESSION_VALUE_KEY = "session_id"
"""The key this tool resolves its session by.

Written into every tool call's context bag by
:meth:`~omicsclaw.entry.turn.TurnRunner.turn_values`. Named here as a
constant rather than spelled inline because it is a contract with a layer
this package may not import, and a contract that exists only as a string
literal in one function body is one rename away from silently resolving
every session to the anonymous store.
"""

_DESCRIPTION = (
    "Create or update the execution plan for the current task — the "
    "authoritative record of what you are doing. Pass `steps` to update "
    "it; omit `steps` to read it back.\n"
    "Use it for any task that takes more than a couple of steps: write "
    "the plan first, mark an item `in_progress` before you start it, and "
    "`completed` as soon as it is actually done. The outstanding items "
    "are shown to you again before every reply, so the plan survives a "
    "context compaction and a resumed session — work from it.\n"
    "You may send only the items you are still working on: anything "
    "already `in_progress` or `completed` is kept, in its original "
    "position. Omitting an item drops it only if it was never started; "
    "to abandon one deliberately, send it with status `cancelled`."
)
"""What the model reads. Ported from ``plan_write.go:63-68`` in English.

The third paragraph is the one worth keeping intact even though it costs
tokens: partial updates are the behaviour a model naturally falls into,
and without this it cannot tell "I need not resend the finished items"
from "resending them is how I keep them".
"""

PLAN_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "description": (
                "The plan items to write. Partial updates are supported: "
                "started items you leave out are kept. Omit this field "
                "entirely to read the current plan without changing it."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Your own identifier for this item. Reuse it "
                            "when you update the item — it is what ties "
                            "the update to the item's history."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "One concrete, doable action.",
                    },
                    "status": {
                        "type": "string",
                        "enum": [status.value for status in PlanStatus],
                    },
                },
                "required": ["id", "content", "status"],
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}
"""The argument schema.

``steps`` is **not** in a ``required`` list, which is what makes read
mode expressible at all. ``additionalProperties: False`` at both levels
is the shape :class:`~omicsclaw.tools.function_tool.FunctionTool`'s
docstring recommends: an unexpected key becomes a schema complaint the
model can act on, rather than a :exc:`TypeError` from ``func(**args)``
that reads like a crash.
"""

_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=False,
    concurrency_safe=False,
    writes_config=True,
    writes_workspace=True,
    allowed_in_background=True,
    tags=frozenset({"planning"}),
)
"""Declared rather than defaulted, and each field for its own reason.

``LOW`` / ``AUTO``: the blast radius is one JSON file of the agent's own
notes. Leaving these to default (``HIGH`` / ``ASK``, and approval fails
closed) would put a human prompt in front of every plan update — which
would not make the deployment safer, it would make the model stop
planning.

``concurrency_safe=False`` makes the call a barrier in the engine's
scheduler. Two ``plan_write`` calls in one turn read the same prior state
and the second's merge would be computed against a plan that no longer
exists — a lost update, and the update lost is the record of what the
model believes it is doing.

``writes_workspace=True`` is a claim about effects, and it is made in the
direction that costs least when wrong: with an archive bound the tool
writes two files under ``<workspace>/.omicsclaw/plans/``, and a
deployment running without one is not harmed by a claim that overstates.
"""


def plan_write_tool(book: PlanBook) -> FunctionTool:
    """Build the ``plan_write`` tool over *book*.

    Mounted once per deployment while a plan is per session, which is
    what *book* resolves: the session is read from the tool context at
    call time, so the one registry
    :func:`~omicsclaw.entry.assembly.build_app` builds serves every
    conversation without any of them seeing another's plan.

    No ``policy`` parameter, following
    :func:`~omicsclaw.skills.use_skill_tool`: a deployment that disagrees
    passes its own to
    :meth:`~omicsclaw.tools.registry.ToolRegistry.register`.
    """

    def run(steps: Any = None) -> str:
        return _plan_write(book, steps)

    return FunctionTool(
        PLAN_WRITE_TOOL_NAME,
        _DESCRIPTION,
        run,
        parameters=PLAN_WRITE_SCHEMA,
        policy=_POLICY,
    )


def _plan_write(book: PlanBook, steps: Any) -> str:
    """Read or write the calling session's plan, and return it as JSON.

    :raises ToolArgumentError: the payload is malformed, or the write
        would have recorded progress that did not happen. Both reach the
        model as a correctable ``is_error`` Observation, which is the
        self-healing path the refusal is designed around: it costs one
        turn, and the model can see from the returned plan what the
        authoritative state actually is.

    ``steps=None`` and ``steps=[]`` both read. The reference harness makes
    the same choice (``plan_write.go:123`` tests ``len(...) > 0``), and
    the alternative is worse than it looks: treating ``[]`` as "erase the
    plan" hands the model a way to lose every item by sending the empty
    value its own schema says is a valid array.
    """
    store = book.for_session(str(context_value(SESSION_VALUE_KEY, "") or ""))
    if steps is None or (isinstance(steps, list) and not steps):
        return _as_json(store.read())
    if not isinstance(steps, list):
        raise ToolArgumentError(
            f"input.steps must be an array of plan items, not "
            f"{type(steps).__name__}"
        )
    proposed = _decode(steps)
    try:
        merged = apply(store.read(), proposed)
    except PlanRefused as exc:
        raise ToolArgumentError(str(exc)) from exc
    return _as_json(store.write(merged))


def _decode(steps: Sequence[Any]) -> tuple[PlanItem, ...]:
    """Turn the decoded payload into items, or say exactly what is wrong.

    :raises ToolArgumentError: with the offending item's index in it.
        A model that sent eight items and one bad field needs to know
        which one; "invalid arguments" makes it resend all eight and
        guess.

    Every field is required by the schema and checked again here, because
    a schema is what the model was *told* and not what it sent — no layer
    between the two validates, and a missing ``status`` would otherwise
    become a ``KeyError`` that reads like a crash in the tool.
    """
    items: list[PlanItem] = []
    for position, entry in enumerate(steps):
        if not isinstance(entry, dict):
            raise ToolArgumentError(
                f"input.steps[{position}] must be an object with id, "
                f"content and status, not {type(entry).__name__}"
            )
        missing = [key for key in ("id", "content", "status") if key not in entry]
        if missing:
            raise ToolArgumentError(
                f"input.steps[{position}] is missing {', '.join(missing)}"
            )
        identifier = str(entry["id"]).strip()
        if not identifier:
            raise ToolArgumentError(
                f"input.steps[{position}].id is empty; it is what ties an "
                "update to the item it updates, so every item needs one"
            )
        try:
            status = PlanStatus(entry["status"])
        except ValueError as exc:
            known = ", ".join(value.value for value in PlanStatus)
            raise ToolArgumentError(
                f"input.steps[{position}].status is {entry['status']!r}; "
                f"it must be one of {known}"
            ) from exc
        items.append(
            PlanItem(id=identifier, content=str(entry["content"]), status=status)
        )
    return tuple(items)


def _as_json(items: Sequence[PlanItem]) -> str:
    """The whole plan, as the model reads it back.

    Always an array, so an empty plan is ``[]`` rather than ``null`` —
    the reference harness normalises the same case for the same reason
    (``plan_write.go:174-178``): a model shown ``null`` has to guess
    whether it means "no plan" or "the call did not work".
    """
    return json.dumps(
        [
            {"id": item.id, "content": item.content, "status": item.status.value}
            for item in items
        ],
        ensure_ascii=False,
    )
