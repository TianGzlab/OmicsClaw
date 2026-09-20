"""``omicsclaw/context`` — message lists in, message lists out.

Plan 0030 task C. Pure transforms over a conversation: no clock, no
I/O, no model. Everything here is ``(messages, budget) -> messages``,
which is what makes the whole compaction story testable without
inventing half a session to test it in.

**Every return value is a tuple, and none of them is the caller's
list.** The reference harness has a scar here: issue #117 was an
aliasing bug, and ``progressive_compactor.go:354-360`` still carries the
defensive copy and the explanation. Python looks safer than it is —
:class:`~omicsclaw.schema.Message` is frozen, so no single entry can be
edited behind a caller's back — but a returned *slice* of the caller's
list is the same bug in a different spelling: one ``append`` and two
conversations are one conversation.

**Nothing here truncates a message.** Capacity is solved at the
granularity of whole messages — :func:`fit_to_budget` peels them off the
front, :func:`emergency_fit` skips the ones that do not fit — never by
shortening one. In particular
:attr:`~omicsclaw.schema.ToolCall.arguments` is never rewritten: ADR
0077 requires it to stay the unparsed JSON text the model emitted, byte
for byte, because prompt-prefix caching and replay evidence both read
those bytes. A truncated argument payload is also an *invalid* one,
which the model will be handed and will retry against forever.
"""

from __future__ import annotations

from typing import Sequence

from omicsclaw.schema import Message, Role

from .budget import ContextBudget
from .tokens import (
    TokenCounter,
    estimate_message_tokens,
    estimate_messages_tokens,
)

__all__ = [
    "MISSING_TOOL_RESULT",
    "emergency_fit",
    "fit_to_budget",
    "render_for_summary",
    "repair_tool_pairs",
    "split_head_tail",
]

MISSING_TOOL_RESULT = "[tool result unavailable: the context was compacted]"
"""Stands in for a tool result that compaction removed.

Worded rather than copied: the harness's string is Chinese prose about
its own compactor, and this one has to read as an explanation to the
model of why an answer it is looking at is not there. Callers who want
different words pass ``placeholder=``.
"""


def repair_tool_pairs(
    messages: Sequence[Message],
    *,
    placeholder: str = MISSING_TOOL_RESULT,
) -> tuple[Message, ...]:
    """Make every tool call and tool result find its partner, **in place**.

    Two repairs, in both directions, ported from ``compaction.go:
    195-239``: a tool result whose call is gone is dropped, and a tool
    call whose result is gone gets a placeholder result inserted
    directly after it. The Anthropic Messages API refuses a conversation
    where either is unpaired, so this is not tidiness — it is the
    difference between a compacted history and a 400.

    **Pairing is adjacency, not membership.** The Go tests two sets of
    ids and so did the first version of this function, and both are
    weaker than the rule they are defending. Anthropic requires every
    ``tool_use`` block of an assistant turn to be answered by a
    ``tool_result`` block in the *immediately following* user turn, and
    ``anthropic_provider.py:271-291`` flushes its batch of pending
    results the moment any other message interrupts them. A membership
    test says "the answer is somewhere in this list" and that is not the
    same statement. It goes wrong on parallel tool calls: an assistant
    turn asking for ``c0`` and ``c1`` whose ``c0`` result survives and
    whose ``c1`` result ends up behind a compaction summary encodes as
    ``assistant[tool_use c0, tool_use c1]``, ``user[tool_result c0]``,
    ``user[text]``, ``user[tool_result c1]`` — ``c1`` unanswered where it
    has to be answered, which is the 400 this function exists to
    prevent. So the answers an assistant turn may keep are exactly the
    contiguous run of ``Role.TOOL`` messages behind it; anything else
    wearing that role is unpaired wherever it happens to sit, and every
    call the run does not answer gets a placeholder.

    **Two lines of the Go cannot be taken literally.**

    *Which message is a tool result.* The harness asks
    ``m.ToolCallID != ""``, because its schema has three roles and folds
    observations into ``user``. This repository has a fourth role and
    the Anthropic adapter dispatches on it — ``Role.TOOL`` at
    ``anthropic_provider.py:276`` — so the test here is the role. A
    repair that used a different criterion than the adapter would be
    repairing something the adapter cannot see.

    *What the placeholder is.* The harness builds
    ``Message{Role: RoleUser, ToolCallID: tc.ID}`` for the same reason.
    Translated literally that becomes ``Message(role=USER,
    tool_call_id=...)``, and ``anthropic_provider.py:271-291`` branches
    on role alone: the message would encode as an ordinary text turn,
    ``tool_call_id`` would be dropped on the floor, and the unanswered
    ``tool_use`` block would still be unanswered — the exact API 400
    this function exists to prevent, now with the appearance of a fix.
    So the placeholder is a real ``Role.TOOL`` message.

    ``is_error`` stays ``False``: nothing failed. Marking it an error
    would teach the model to retry a call that already succeeded.

    **The role test is ``==``, not ``is``.** Decision Q11 spells it
    ``message.role == Role.TOOL`` and both adapters are written that way
    (``anthropic_provider.py:272,276,281``; ``openai_provider.py:140``
    converts with ``str()`` first). :class:`~omicsclaw.schema.Message` is
    a dataclass with no validation, so a history deserialized from a
    session row arrives with plain ``str`` roles, and
    :class:`~omicsclaw.schema.Role` is a ``StrEnum`` precisely so that
    keeps working. Under ``is`` it does not: every ``str`` role misses
    every branch, this function answers one ``tool_use`` with two
    ``tool_result`` messages, and the failure is silent.
    """
    repaired: list[Message] = []
    index = 0
    total = len(messages)
    while index < total:
        message = messages[index]
        index += 1
        if message.role == Role.TOOL:
            # Reached without an assistant turn in front of it: whatever
            # it answered is not where the API will look for it.
            continue
        repaired.append(message)
        if message.role != Role.ASSISTANT or not message.tool_calls:
            continue
        run_end = index
        while run_end < total and messages[run_end].role == Role.TOOL:
            run_end += 1
        answers: dict[str, Message] = {}
        for answer in messages[index:run_end]:
            answers.setdefault(answer.tool_call_id, answer)
        for call in message.tool_calls:
            found = answers.pop(call.id, None)
            if found is None:
                found = Message.tool(tool_call_id=call.id, content=placeholder)
            repaired.append(found)
        index = run_end
    return tuple(repaired)


def split_head_tail(
    messages: Sequence[Message],
    *,
    pinned: int,
    min_tail: int,
) -> tuple[tuple[Message, ...], tuple[Message, ...], tuple[Message, ...]]:
    """Cut a conversation into ``(pinned, head, tail)``.

    *pinned* messages at the front are kept whatever happens, *min_tail*
    at the back are kept whatever happens, and the head between them is
    what a compaction is allowed to touch.

    **Nobody here guesses that message zero is a system prompt.** Every
    compactor in the harness requires it and returns the input untouched
    when it is missing (``compaction.go:103-105``,
    ``progressive_compactor.go:235-237``), which is safe there because
    its engine injects one at position 0 on every load
    (``history.go:62-64``). This project's engine injects nothing, so
    copying that precondition would turn the compactor into a silent
    no-op for any conversation assembled differently — a thing that
    resolves, is never read, and never goes red. The caller says how
    many messages are pinned instead: ``pinned=1`` is the harness's
    behaviour, ``pinned=0`` says there is no protected prefix.

    Ported from ``progressive_compactor.go:230-245``, including its one
    structural guard: when the messages after the pinned prefix number
    ``min_tail`` or fewer there is **no head**, and the caller skips the
    tier rather than compacting something that is already minimal.
    """
    kept = tuple(messages[:pinned])
    rest = tuple(messages[pinned:])
    if len(rest) <= min_tail:
        return kept, (), rest
    head_end = len(rest) - min_tail
    return kept, rest[:head_end], rest[head_end:]


def fit_to_budget(
    messages: Sequence[Message],
    budget: ContextBudget,
    *,
    pinned: int = 0,
    min_tail: int,
    counter: TokenCounter | None = None,
    target_tokens: int | None = None,
) -> tuple[Message, ...]:
    """Peel messages off the front until the rest fits, then repair.

    Ported from ``compaction.go:95-132``. The oldest compactible message
    goes first and one at a time, so the result keeps as much history as
    the budget allows rather than jumping to a fixed window.

    Returns the input unchanged when it already fits, and when there is
    no head to peel — both of those are the harness's, and both matter:
    a function that rebuilds the conversation on every call would churn
    the prompt prefix for nothing.

    **``target_tokens`` is what "fits" means**, and it defaults to
    ``budget.usable_tokens``. The harness has the same two numbers and
    they are deliberately *different*: ``NewTokenBudgetCompactor``
    trims to ``contextWindow * 80/100`` (``compaction.go:86-92``) while
    the tiers that call it trigger from 60% of the same window
    (``progressive_compactor.go:129-133, 215``), so a fallback from
    ``TierFull`` genuinely removes messages. Collapse the two onto one
    number and the fallback becomes a provable no-op: every tier below
    ``EMERGENCY`` sits under 95% of ``usable_tokens`` by definition, so
    ``estimate <= usable`` holds on arrival and the first branch below
    returns the input byte for byte.
    :func:`~omicsclaw.context.compaction.compact` therefore passes a
    target drawn from :class:`~omicsclaw.context.budget.ContextBudget`'s
    own declared tier thresholds rather than from a fresh literal.

    The replaced layer cut differently: it was block-aware, and an
    assistant turn was never separated from the tool results answering
    it. That is gone. **The cost is real** — peeling the front off can
    orphan a tool result, which :func:`repair_tool_pairs` then deletes,
    and can strand a tool call, which it then answers with a
    placeholder. Content that the block-aware cut would have kept is
    lost. The harness accepts this; so does this layer.
    """
    usable = budget.usable_tokens if target_tokens is None else target_tokens
    if not messages:
        return tuple(messages)
    if estimate_messages_tokens(messages, counter=counter) <= usable:
        return tuple(messages)

    kept, head, tail = split_head_tail(messages, pinned=pinned, min_tail=min_tail)
    if not head:
        return tuple(messages)

    for head_end in range(len(head), 0, -1):
        candidate = (*kept, *head[:head_end], *tail)
        if estimate_messages_tokens(candidate, counter=counter) <= usable:
            return repair_tool_pairs(candidate)

    return repair_tool_pairs((*kept, *tail))


def emergency_fit(
    messages: Sequence[Message],
    budget: ContextBudget,
    *,
    pinned: int = 0,
    counter: TokenCounter | None = None,
) -> tuple[Message, ...]:
    """Lossy truncation that keeps the task in view.

    Ported from ``compaction.go:134-179`` together with the reason its
    comment gives, which is measured rather than argued:

    * **The first message after the pinned prefix is kept
      unconditionally.** It carries the task. An emergency truncation
      that throws it away leaves the model with no goal and it spins:
      the harness recorded 143 consecutive emergency turns and a failed
      task before this line was added (issue #117).
    * **Newest first, and a message that does not fit is skipped, not
      shortened.** One enormous tool result would otherwise fill the
      emergency view by itself and push the task back out of it. Older
      and smaller messages still get their chance.

    *pinned* is on this function for the reason it is on
    :func:`split_head_tail`: the harness hardcodes "message zero is the
    system prompt" and this layer refuses to guess. Plan 0030 §3.2 omits
    the parameter here, which would have left
    :func:`~omicsclaw.context.compaction.compact` unable to honour its
    own ``pinned`` on the one path that discards the most.
    """
    if not messages:
        return tuple(messages)
    kept = tuple(messages[:pinned])
    rest = tuple(messages[pinned:])
    if not rest:
        return tuple(messages)
    survivors = _emergency_survivors(kept, rest, budget, counter)
    return repair_tool_pairs((*kept, *survivors))


def _emergency_survivors(
    kept: tuple[Message, ...],
    rest: tuple[Message, ...],
    budget: ContextBudget,
    counter: TokenCounter | None,
    target_tokens: int | None = None,
) -> tuple[Message, ...]:
    """The task anchor plus whatever else fits, oldest-to-newest order.

    *target_tokens* is what the survivors must fit in; ``None`` means
    ``budget.usable_tokens``.

    Separate from :func:`emergency_fit` so that
    :func:`~omicsclaw.context.compaction.plan_compaction` can put the
    survivors in a plan and let one repair pass run over the assembled
    result, instead of repairing twice.
    """
    task = rest[0]
    later = rest[1:]
    target = budget.usable_tokens if target_tokens is None else target_tokens
    remaining = target - estimate_messages_tokens((*kept, task), counter=counter)
    keep = [False] * len(later)
    for index in range(len(later) - 1, -1, -1):
        cost = estimate_message_tokens(later[index], counter=counter)
        if cost <= remaining:
            remaining -= cost
            keep[index] = True
    return (task, *(m for index, m in enumerate(later) if keep[index]))


def render_for_summary(messages: Sequence[Message]) -> str:
    """Flatten messages into the text handed to a summarizing model.

    Ported line for line from ``progressive_compactor.go:391-404``::

        [tool_result <id>]: <content>
        [<role>]: <content>
        [tool_call <name>(<id>)]: <arguments>

    joined with newlines. A tool result contributes its one line and
    nothing else; any other message contributes its content when it has
    some, then one line per tool call it requested.

    **Nothing is truncated, at any length.** The Go does not truncate
    either, and the layer being replaced — which did, at 70/30 — has had
    every one of the three paths that called it deleted. Size is handled
    by :func:`fit_to_budget` dropping whole messages before this is
    reached, never by a renderer quietly deciding how much of a tool
    result matters.

    **This output goes to the summarizer and comes back as a summary. It
    never becomes a** :attr:`~omicsclaw.schema.Message.content` **the
    agent will read.** That is the only reason it can be plain prose.
    The replaced layer rendered historical tool calls as
    ``<prior-tool-calls names="…"/>`` because prose in the *model's own*
    view triggers few-shot imitation — the model starts narrating tool
    calls instead of making them — while a structured tag reads as
    metadata and is not repeated. That finding still holds; it simply
    has nothing to apply to while this is the only renderer here and its
    output only ever travels outward. **Anyone adding a second renderer,
    or routing this one's output back into the conversation, has to come
    back and read this paragraph first.**
    """
    lines: list[str] = []
    for message in messages:
        if message.role == Role.TOOL:
            lines.append(f"[tool_result {message.tool_call_id}]: {message.content}")
            continue
        if message.content:
            # ``str`` and not ``.value``: a ``StrEnum`` prints as its
            # value, and a history deserialized from a session row
            # carries plain ``str`` roles that have no ``.value``.
            lines.append(f"[{message.role!s}]: {message.content}")
        for call in message.tool_calls:
            lines.append(f"[tool_call {call.name}({call.id})]: {call.arguments}")
    return "\n".join(lines)
