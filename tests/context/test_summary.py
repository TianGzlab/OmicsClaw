"""Plan 0030 task C: the compaction message, the marker, the templates.

What holds these three together is a loop that has to close: the
template asks for headings, the parser looks for those headings, and
:meth:`Anchors.render` writes them back out. Break any one of the three
and compaction keeps running and quietly preserves nothing, because
:func:`parse_anchors_and_summary` never raises (pitfall 13).
"""

from __future__ import annotations

from omicsclaw.context.summary import (
    COMPACTION_MARKER,
    FIRST_TEMPLATE,
    INCREMENTAL_TEMPLATE,
    SUMMARY_SYSTEM_PROMPT,
    Anchors,
    build_compaction_message,
    is_summary_message,
    parse_anchors_and_summary,
)
from omicsclaw.schema import Message, Role


def _anchors() -> Anchors:
    return Anchors(
        user_intent="annotate the slide",
        execution_progress="- loaded the h5ad",
        key_decisions="- leiden",
        tried_solutions="- louvain: slow",
        next_steps="- run spatial-de",
    )


def test_the_compaction_message_has_the_shape_the_harness_builds():
    """``progressive_compactor.go:446-460``, minus the offload block.

    There is no ``## Offloaded References`` section because this layer
    writes nothing to disk, and describing a feature that is not there
    is how a model learns to ask for it.
    """
    message = build_compaction_message(_anchors(), "three steps in")

    assert message.role is Role.USER
    assert message.content.startswith(f"{COMPACTION_MARKER}\n## Anchors\n\n")
    assert message.content.endswith("## Summary\nthree steps in")
    assert "Offloaded" not in message.content


def test_a_compaction_message_parses_back_into_what_went_into_it():
    """The round trip, which is what makes the incremental template work.

    Turn two hands turn one's compaction back to the model. If the
    message this package writes were not one this package can read, the
    anchors would silently reset to ``N/A`` on every turn and the
    accumulated context would be quietly gone.
    """
    message = build_compaction_message(_anchors(), "three steps in")

    anchors, summary = parse_anchors_and_summary(message.content)

    assert anchors == _anchors()
    assert summary == "three steps in"


def test_the_marker_identifies_our_own_messages_and_nothing_else():
    ours = build_compaction_message(Anchors(), "body")

    assert is_summary_message(ours)
    assert not is_summary_message(Message.user("an ordinary turn"))
    assert not is_summary_message(
        Message.user("a turn that mentions [Context Compaction] halfway through")
    )


def test_the_marker_is_a_prefix_with_no_closing_tag():
    """``anchor.go:42``, and the precondition that comes with it.

    The replaced layer had a matched pair and used ``rfind`` to reach
    the outermost — a fix for a real nesting bug. A bare prefix cannot
    do that, which is safe only while there is exactly one compaction
    message in exactly one place. Anyone who makes several coexist has
    to come back here.
    """
    assert COMPACTION_MARKER == "[Context Compaction]"
    assert "</" not in COMPACTION_MARKER


def test_the_first_template_asks_for_the_headings_the_parser_reads():
    """The loop, closed from the other end.

    A template that asked for ``### User Goal`` would produce summaries
    that parse to five ``N/A``s — and nothing would raise, because the
    parser is a scan.
    """
    filled = FIRST_TEMPLATE.format(conversation="[user]: hello")

    for heading in (
        "### User Intent",
        "### Execution Progress",
        "### Key Decisions",
        "### Tried Solutions",
        "### Next Steps",
        "## Summary",
    ):
        assert heading in filled

    assert "[user]: hello" in filled
    assert "offloaded" not in filled.lower(), (
        "this layer does not offload, so the template must not describe it"
    )


def test_the_incremental_template_carries_the_previous_compaction():
    """``progressive_compactor.go:58-65``: merge, do not summarize a summary.

    There is only ever one previous compaction — the replaced layer
    accumulated blocks and dropped the oldest against a ceiling, and
    that determinism is what was traded for the model's judgement.
    """
    filled = INCREMENTAL_TEMPLATE.format(
        previous="### User Intent\nannotate", conversation="[user]: and now?"
    )

    assert "<previous-compaction>" in filled
    assert "</previous-compaction>" in filled
    assert "### User Intent\nannotate" in filled
    assert "[user]: and now?" in filled


def test_the_templates_survive_a_conversation_containing_braces():
    """``str.format`` reads the template, never the substituted value.

    Tool arguments are raw JSON and reach the summarizer as text, so
    every compaction of a real trajectory contains braces.
    """
    conversation = '[tool_call bash(c1)]: {"command": "ls {a,b}"}'

    assert conversation in FIRST_TEMPLATE.format(conversation=conversation)
    assert conversation in INCREMENTAL_TEMPLATE.format(
        previous="{}", conversation=conversation
    )


def test_the_system_prompt_asks_for_no_preamble():
    """``progressive_compactor.go:26``. The preamble is not cosmetic.

    "Here is a summary of the conversation:" before the first ``###``
    parses as nothing at all — it sits before any heading, so the scan
    discards it and every anchor comes back ``N/A``.
    """
    assert "no preamble" in SUMMARY_SYSTEM_PROMPT
