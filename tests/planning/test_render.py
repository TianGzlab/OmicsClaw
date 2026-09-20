"""What the model is shown, and what a person opens."""

from __future__ import annotations

from datetime import datetime, timezone

from omicsclaw.planning import (
    DOCUMENT_TITLE,
    INJECTION_HEADER,
    PlanItem,
    PlanStatus,
    format_plan,
    render_document,
)

P, R, C, X = (
    PlanStatus.PENDING,
    PlanStatus.IN_PROGRESS,
    PlanStatus.COMPLETED,
    PlanStatus.CANCELLED,
)
_WHEN = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def test_an_empty_plan_renders_nothing_at_all():
    """``""`` means do not inject — an empty user turn is a wasted call."""
    assert format_plan(()) == ""


def test_a_plan_with_no_outstanding_items_renders_nothing():
    assert format_plan((PlanItem("1", "a", C), PlanItem("2", "b", X))) == ""


def test_only_outstanding_items_reach_the_block():
    block = format_plan(
        (
            PlanItem("1", "done already", C),
            PlanItem("2", "doing now", R),
            PlanItem("3", "still to do", P),
            PlanItem("4", "abandoned", X),
        )
    )

    assert "done already" not in block
    assert "abandoned" not in block
    assert "doing now" in block
    assert "still to do" in block


def test_the_two_markers_distinguish_claimed_from_untouched():
    block = format_plan((PlanItem("1", "doing", R), PlanItem("2", "todo", P)))

    assert "[>] doing" in block
    assert "[ ] todo" in block


def test_the_block_leads_with_the_header():
    block = format_plan((PlanItem("1", "a", P),))

    assert block.splitlines()[0] == INJECTION_HEADER


def test_the_header_says_what_makes_it_authoritative():
    """The block's position says nothing; the sentence has to.

    It has to name compaction and resumption, because those are the two
    moments when the visible history disagrees with the list.
    """
    lowered = INJECTION_HEADER.lower()

    assert "authoritative" in lowered
    assert "compaction" in lowered
    assert "resumed" in lowered or "resumption" in lowered


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def test_the_prompt_facing_text_is_english_like_every_other_section():
    """A language switch in the one message whose job is to be obeyed.

    Every section of this repository's system prompt is English and
    ``SOUL.md`` says to default to it, so the reference harness's Chinese
    header was translated rather than ported. Checked for CJK rather than
    with ``isascii``: this repository's prompt constants use em dashes,
    so ASCII-only would fail on punctuation and say nothing about
    language.
    """
    assert not _has_cjk(INJECTION_HEADER)
    assert not _has_cjk(DOCUMENT_TITLE)
    assert not _has_cjk(format_plan((PlanItem("1", "a", P),)))


def test_the_guard_itself_can_see_a_chinese_header():
    """A detector that never fires is not a detector."""
    assert _has_cjk("## 当前执行计划")


def test_the_item_order_is_the_plan_order():
    block = format_plan(
        (PlanItem("3", "third", P), PlanItem("1", "first", P), PlanItem("2", "x", C))
    )

    assert block.splitlines()[1:] == ["[ ] third", "[ ] first"]


def test_the_document_keeps_every_item_including_the_finished_ones():
    """Its whole value over the block is that it answers "what happened"."""
    document = render_document(
        "sess-1",
        (
            PlanItem("1", "done", C),
            PlanItem("2", "doing", R),
            PlanItem("3", "todo", P),
            PlanItem("4", "dropped", X),
        ),
        now=_WHEN,
    )

    assert "- [x] done" in document
    assert "- [>] doing" in document
    assert "- [ ] todo" in document
    assert "- [-] dropped" in document


def test_the_document_records_the_session_and_the_time():
    document = render_document("sess-1", (PlanItem("1", "a", P),), now=_WHEN)

    assert "session: sess-1" in document
    assert "2026-09-20T12:00:00+00:00" in document


def test_the_document_carries_an_explicit_offset():
    """A bare local timestamp out of a container is a time nobody can place."""
    document = render_document("s", (), now=None)

    stamp = [line for line in document.splitlines() if line.startswith("updated:")][0]
    assert "+00:00" in stamp


def test_an_anonymous_session_is_written_as_a_dash_not_as_blank():
    document = render_document("", (), now=_WHEN)

    assert "session: -" in document


def test_an_empty_document_says_so_rather_than_ending_mid_heading():
    document = render_document("s", (), now=_WHEN)

    assert document.startswith(DOCUMENT_TITLE)
    assert "no items yet" in document


def test_the_document_ends_with_a_newline():
    """It is a file a person opens in an editor, not a fragment."""
    assert render_document("s", (PlanItem("1", "a", P),), now=_WHEN).endswith("\n")
