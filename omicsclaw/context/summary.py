"""``omicsclaw/context`` — anchors, and the text that carries them.

Plan 0030 task C. Pure text: the five anchors a compaction preserves,
the parser that recovers them from whatever a model actually wrote, the
templates that ask for them, and the marker that says "this message is a
compaction". All of it ported from ``internal/memory/anchor.go`` and
``progressive_compactor.go:26-65``.

It is its own module for cohesion rather than for size. Anchors and
templates are a self-contained text transform that can be tested without
a budget, a plan or a model anywhere in sight; folded into
:mod:`~omicsclaw.context.compaction` they would turn that file into the
1,200-line compactor this rebuild exists to leave behind.

**There is no gate on what a summarizer returns.** The replaced layer
had six — empty, over-length by tokens, by characters, by bytes,
looks-like-a-tool-call, and a content-fidelity check that re-read the
source material for file paths and ``Error``/``Traceback``/``TODO``
markers and rejected a summary that had dropped one. The harness has
none: ``progressive_compactor.go:423-431`` checks that the call did not
error and did not return nil, and then parses whatever came back. The
owner's 2026-09-18 ruling takes the harness's shape, and **the cost is
that a compaction can lose the path to an ``h5ad`` file and nothing
will notice**. What is left in its place is the degradation path in
:func:`~omicsclaw.context.compaction.compact`, which must therefore
actually hold — see plan 0030 §11.A-9, the debt this makes most worth
repaying. It holds in two places, and both are budget arithmetic rather
than judgements about prose: the fallback trims to a *stricter* target
than the tier that triggered it, and ``compact`` re-measures its own
output against ``usable_tokens`` before handing it back.

**Do not invent a replacement gate.** "Reject a summary longer than the
template" needs a template to measure against, and the
deterministic-template path is exactly what was removed; reintroducing
a yardstick is reintroducing the path. The budget re-measurement is not
that: it compares the result to the number this package already divides
by, asks nothing at all about what the summary says, and is the literal
text of task C acceptance 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from omicsclaw.schema import Message

from .offload import REFERENCES_HEADING, OffloadEntry, render_references

__all__ = [
    "Anchors",
    "COMPACTION_MARKER",
    "FIRST_TEMPLATE",
    "INCREMENTAL_TEMPLATE",
    "OFFLOAD_RULE",
    "SUMMARY_SYSTEM_PROMPT",
    "Summarizer",
    "build_compaction_message",
    "is_summary_message",
    "parse_anchors_and_summary",
]

_MISSING = "N/A"
"""What an anchor says when the model had nothing to put there.

``anchor.go:94-96``. Distinct from the empty string on purpose: an
anchor that says ``N/A`` was considered and found empty, and
:meth:`Anchors.merge` reads it as "do not overwrite what we already
knew".
"""

_ANCHOR_HEADERS: tuple[tuple[str, str], ...] = (
    ("user_intent", "User Intent"),
    ("execution_progress", "Execution Progress"),
    ("key_decisions", "Key Decisions"),
    ("tried_solutions", "Tried Solutions"),
    ("next_steps", "Next Steps"),
)
"""Field name to Markdown heading, in the one order everything uses.

``anchor.go:21-33``. A tuple rather than a dict because the order *is*
the contract: parse, merge and render all walk this list, so a compacted
history reads the same way on every turn.
"""

COMPACTION_MARKER = "[Context Compaction]"
"""Prefix of every message this package produced by compacting.

``anchor.go:42``. A prefix only — there is no closing marker, which
means compaction messages **cannot be safely nested**. The replaced
layer had a matched pair and found the outermost with ``rfind``, a fix
for a real bug (CodePilot #7). The harness does not need one because it
keeps exactly one summary at a time and the compaction message always
sits in one place. This layer copies that shape, so the shape is a
precondition: **anyone who makes several summaries coexist has to
revisit this constant.**
"""


@runtime_checkable
class Summarizer(Protocol):
    """Whatever can turn a pile of conversation into a short one.

    Deliberately *not* shaped like
    :class:`~omicsclaw.provider.LLMProvider`. The harness's equivalent
    (``summarization.go:20-22``) declares a *subset* of its provider
    interface -- ``Generate`` alone, where ``interface.go:24-48`` also
    carries ``GenerateStream`` -- so a provider satisfies it
    structurally and can be passed straight in. Being narrower is
    exactly what makes that work; it is not a copy. Python cannot do
    the trick either way: matching the signature means naming
    ``omicsclaw.provider.Completion`` in an annotation, and this
    package importing ``omicsclaw.provider`` is the end of its leaf
    status.

    The narrower signature is not only a consolation. Summarization
    wants a *different binding* than the agent's own: no tools at all
    (in this repository ``tools=None`` strips them rather than meaning
    "the usual set"), and usually a smaller, cheaper model. Those are
    composition-root decisions. A five-line adapter that makes them
    explicit is more honest than a structural match that hides them.

    **No timeout is imposed on it here**, by this Protocol or by
    :func:`~omicsclaw.context.compaction.compact`. See that function.
    """

    async def summarize(self, prompt: str, *, system: str) -> str:
        """Summarize *prompt* under the instruction *system*."""
        ...


@dataclass(frozen=True, slots=True)
class Anchors:
    """The five facts a compaction refuses to lose.

    Ported from ``anchor.go:12-33``. Fixed set, fixed order: a summary
    is free-form and will drift, but "what was the user asking for" and
    "what has already been tried" have to survive every round of
    compaction in a recognisable place, which is what makes them worth
    naming separately from the prose.
    """

    user_intent: str = _MISSING
    execution_progress: str = _MISSING
    key_decisions: str = _MISSING
    tried_solutions: str = _MISSING
    next_steps: str = _MISSING

    def merge(self, newer: Anchors) -> Anchors:
        """Fold *newer* over this one. ``"N/A"`` does not overwrite.

        ``anchor.go:105-124``. The direction is the whole content of
        this method and it is easy to write backwards: an anchor the
        newer compaction had nothing to say about is a **gap in the
        newer one**, not a retraction of what the older one knew. A
        merge that let ``N/A`` win would erase the user's original
        intent the first time a summarizer did not restate it.
        """
        return Anchors(
            **{
                field: _merge_one(getattr(self, field), getattr(newer, field))
                for field, _ in _ANCHOR_HEADERS
            }
        )

    def render(self) -> str:
        """Markdown: ``### Heading`` then the value, blank line between.

        ``progressive_compactor.go:463-480``.
        """
        blocks = [
            f"### {heading}\n{getattr(self, field)}\n\n"
            for field, heading in _ANCHOR_HEADERS
        ]
        return "".join(blocks).strip()


def _merge_one(older: str, newer: str) -> str:
    """One field of :meth:`Anchors.merge`.

    ``""`` and :data:`_MISSING` are the same statement here — the newer
    compaction had nothing to say about this anchor — and neither may
    overwrite. The empty string is not a theoretical input: step 6
    serializes :class:`Anchors` into a session row, and a JSON round
    trip turns an absent key or a ``null`` into ``""`` on the way back.
    A version of this that folded the two cases apart and let ``""``
    win would satisfy every test written about ``N/A`` while erasing the
    user's original intent on the first reload.
    """
    if not newer or newer == _MISSING:
        return older or _MISSING
    return newer


def parse_anchors_and_summary(text: str) -> tuple[Anchors, str]:
    """Recover anchors and summary prose from a model's output.

    Ported from ``anchor.go:47-100``: a single scan, ``## Summary``
    switches into the prose, ``### <Heading>`` opens a known anchor and
    an unrecognised one closes whatever was open.

    **It never raises, and it always returns five anchors.** A model
    that ignores the format is the normal case, not the exceptional one
    — a parser that threw would turn every bout of model disobedience
    into a crashed run. Missing sections come back as ``"N/A"``.

    Which is also why the caller cannot treat "it parsed" as "it
    worked": ``parse_anchors_and_summary("hello")`` succeeds and returns
    nothing at all. :func:`~omicsclaw.context.compaction.compact` reads
    that empty result as a failed summarization, which is the only
    signal left after the six content gates were removed.
    """
    field_by_heading = {heading: field for field, heading in _ANCHOR_HEADERS}
    parsed: dict[str, str] = {}
    current_field = ""
    current_lines: list[str] = []
    summary_lines: list[str] = []
    in_summary = False

    for line in text.split("\n"):
        trimmed = line.strip()
        if trimmed == "## Summary":
            if current_field:
                parsed[current_field] = "\n".join(current_lines).strip()
                current_field = ""
                current_lines = []
            in_summary = True
            continue
        if in_summary:
            if trimmed == REFERENCES_HEADING:
                break
            summary_lines.append(line)
            continue
        if trimmed.startswith("### "):
            if current_field:
                parsed[current_field] = "\n".join(current_lines).strip()
                current_lines = []
            current_field = field_by_heading.get(trimmed[len("### ") :], "")
            continue
        if current_field:
            current_lines.append(line)

    if current_field:
        parsed[current_field] = "\n".join(current_lines).strip()

    anchors = Anchors(
        **{field: parsed.get(field) or _MISSING for field, _ in _ANCHOR_HEADERS}
    )
    return anchors, "\n".join(summary_lines).strip()


def build_compaction_message(
    anchors: Anchors,
    summary: str,
    references: Sequence[OffloadEntry] = (),
) -> Message:
    """The one message that stands in for everything compaction removed.

    A user-role message: it is context handed to the model, not
    something the model said. *references* adds a ``## Offloaded
    References`` block after the summary, listing where the full text of
    summarized-away tool results can still be read.
    """
    content = (
        f"{COMPACTION_MARKER}\n## Anchors\n\n"
        f"{anchors.render()}\n\n## Summary\n{summary}"
    )
    block = render_references(references)
    if block:
        content = f"{content}\n\n{block}"
    return Message.user(content)


def is_summary_message(message: Message) -> bool:
    """Whether *message* is one of ours — see :data:`COMPACTION_MARKER`."""
    return message.content.startswith(COMPACTION_MARKER)


SUMMARY_SYSTEM_PROMPT = (
    "You are a context compaction engine. Analyze the conversation and "
    "produce a structured compaction preserving essential context. Output "
    "only the compaction - no preamble."
)
"""``progressive_compactor.go:26``."""

FIRST_TEMPLATE = """Produce a structured compaction of the following \
conversation in this exact format:

## Anchors

### User Intent
<one concise sentence>

### Execution Progress
- <key milestone>

### Key Decisions
- <decision: rationale>

### Tried Solutions
- <approach: outcome>

### Next Steps
- <pending task>

## Summary
<supplementary context not captured in anchors>

Rules:
- Each anchor section MUST be present (use "- N/A" if nothing applies)
- Be concise: each item one line

Conversation:
{conversation}"""
"""First compaction of a conversation. ``progressive_compactor.go:28-56``.

Kept in English because the headings it asks for are the headings
:func:`parse_anchors_and_summary` matches on; translating the prompt
while the parser still looks for ``### User Intent`` would be a quiet
way of making every compaction parse to nothing.

Carries no rule about ``[offloaded: ...]`` entries; :data:`OFFLOAD_RULE`
is added only when the conversation being summarized contains one.
"""

OFFLOAD_RULE = (
    "- [offloaded: ...] entries indicate large outputs saved to files; "
    "keep the paths that still matter"
)
"""The rule line added to :data:`FIRST_TEMPLATE` when a placeholder is
present in the conversation."""

INCREMENTAL_TEMPLATE = """Update the existing compaction by merging in new \
conversation content. Output the merged compaction in the same format - no \
preamble.

<previous-compaction>
{previous}
</previous-compaction>

New conversation to merge:
{conversation}"""
"""Every compaction after the first. ``progressive_compactor.go:58-65``.

There is only ever **one** previous compaction. The replaced layer
accumulated summary blocks and dropped the oldest against a token
ceiling; here the model is asked to merge instead, exactly as the
harness does (``:482-486``). What that trades away is a deterministic
bound on loss for the summarizer's judgement about what to keep.
"""
