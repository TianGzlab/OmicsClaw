"""Plan 0030 task C: the five anchors, and a parser that cannot fail.

Pitfalls 13 and 14. Both are about a model that did not do as it was
told, which is the normal case rather than the exceptional one — and
about a merge rule that is trivial to write backwards and produces a
plausible-looking result either way.
"""

from __future__ import annotations

import pytest

from omicsclaw.context.summary import Anchors, parse_anchors_and_summary

_WELL_FORMED = """## Anchors

### User Intent
Annotate the Visium slide

### Execution Progress
- loaded the h5ad

### Key Decisions
- leiden: it is the default

### Tried Solutions
- louvain: too slow

### Next Steps
- run spatial-de

## Summary
The user is three steps into a spatial workflow.
"""


def test_a_well_formed_compaction_round_trips():
    anchors, summary = parse_anchors_and_summary(_WELL_FORMED)

    assert anchors == Anchors(
        user_intent="Annotate the Visium slide",
        execution_progress="- loaded the h5ad",
        key_decisions="- leiden: it is the default",
        tried_solutions="- louvain: too slow",
        next_steps="- run spatial-de",
    )
    assert summary == "The user is three steps into a spatial workflow."


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("empty", ""),
        ("summary only", "## Summary\njust prose, no anchors at all"),
        (
            "misspelled heading",
            "## Anchors\n\n### User Intentions\nwrong\n\n## Summary\nbody",
        ),
        (
            "nested subheading",
            "## Anchors\n\n### User Intent\nreal\n#### Detail\nmore\n\n"
            "## Summary\nbody",
        ),
        ("prose only", "Sure! Here is a summary of the conversation:"),
        ("json instead", '{"user_intent": "nope"}'),
    ],
)
def test_a_model_that_ignores_the_format_does_not_raise(label: str, text: str):
    """Pitfall 13: ``anchor.go:47-100`` is a scan, and scans do not throw.

    A parser that raised would turn every bout of model disobedience
    into a crashed run. Missing sections come back as ``"N/A"`` and
    there are always exactly five, so every consumer downstream can read
    all five fields without asking whether they are there.
    """
    anchors, summary = parse_anchors_and_summary(text)

    assert isinstance(anchors, Anchors)
    assert isinstance(summary, str)
    assert len([f for f in Anchors.__dataclass_fields__]) == 5


def test_a_misspelled_heading_loses_its_content_rather_than_misfiling_it():
    """An unrecognised ``###`` closes whatever was open — ``anchor.go:78-80``.

    Guessing which anchor "User Intentions" meant would be a heuristic
    that eventually files the wrong thing under the wrong anchor and
    carries it forward through every later compaction.
    """
    anchors, _ = parse_anchors_and_summary(
        "### User Intentions\nwrong heading\n\n### Next Steps\nright heading"
    )

    assert anchors.user_intent == "N/A"
    assert anchors.next_steps == "right heading"


def test_everything_after_the_summary_heading_is_summary():
    """Including something that looks like an anchor heading.

    ``anchor.go:66-69`` checks ``inSummary`` before it checks for
    ``###``, so the prose wins once it has started. Worth pinning: the
    other order would let a summary quoting a heading silently reopen an
    anchor.
    """
    _, summary = parse_anchors_and_summary(
        "## Summary\nwe discussed\n### User Intent\nwhich was quoted"
    )

    assert summary == "we discussed\n### User Intent\nwhich was quoted"


def test_a_newer_anchor_overwrites_an_older_one():
    older = Anchors(user_intent="find the file", next_steps="- read it")
    newer = Anchors(user_intent="edit the file")

    assert older.merge(newer).user_intent == "edit the file"


def test_a_newer_na_does_not_overwrite_what_was_already_known():
    """Pitfall 14, and the direction is the entire content of the method.

    ``"N/A"`` in the newer compaction is a **gap in the newer one**, not
    a retraction. A merge that let it win would erase the user's
    original intent the first time a summarizer forgot to restate it —
    and would keep passing every other test in this file.
    """
    older = Anchors(user_intent="find the file", next_steps="- read it")
    newer = Anchors(user_intent="edit the file")

    merged = older.merge(newer)

    assert merged.next_steps == "- read it"
    assert merged.user_intent == "edit the file"


def test_an_empty_newer_anchor_is_a_gap_and_not_a_retraction_either():
    """Pitfall 14's other spelling, and the one a round trip produces.

    ``merge`` is documented as "a gap in the newer one, not a
    retraction", and it honoured that for ``"N/A"`` while the empty
    string went the other way: ``""`` is not ``"N/A"``, so it won the
    comparison, and ``"" or "N/A"`` turned it into ``"N/A"`` on the way
    out — erasing the older value through the branch that exists to
    protect it.

    ``""`` is not a hypothetical input. :class:`Anchors` is a public
    value object that step 6 serializes into a session row, and a JSON
    round trip turns an absent key or a ``null`` into ``""`` coming
    back. The first reload would have dropped the user's original
    intent.
    """
    older = Anchors(user_intent="find the file", next_steps="- read it")

    merged = older.merge(Anchors(user_intent="", next_steps=""))

    assert merged.user_intent == "find the file"
    assert merged.next_steps == "- read it"

    revived = Anchors(user_intent="", next_steps="").merge(older)
    assert revived.user_intent == "find the file"
    assert Anchors(user_intent="").merge(Anchors(user_intent="")).user_intent == "N/A"


def test_merging_onto_nothing_keeps_the_newer_values():
    merged = Anchors().merge(Anchors(key_decisions="- use leiden"))

    assert merged.key_decisions == "- use leiden"
    assert merged.user_intent == "N/A"


def test_an_unrecognised_heading_closes_the_anchor_that_was_open():
    """``anchor.go:78-80``, in the position where the rule does something.

    The existing test for this puts the misspelling *first*, so nothing
    was open when it arrived and "closes what was open" was never
    exercised — an implementation that kept accumulating into the
    current anchor passed it. Here the bogus heading arrives with
    ``### User Intent`` open, and the content underneath it must not be
    filed under an anchor it has nothing to do with: a wrong value
    carried forward by :meth:`Anchors.merge` through every later
    compaction is worse than a missing one.
    """
    anchors, _ = parse_anchors_and_summary(
        "### User Intent\nreal\n### Bogus Heading\nspill\n"
        "### Next Steps\n- go\n### Also Bogus\nmore spill"
    )

    assert anchors.user_intent == "real"
    assert anchors.next_steps == "- go"
    assert "spill" not in "".join(
        getattr(anchors, field) for field in Anchors.__dataclass_fields__
    )


def test_an_anchor_renders_as_the_headings_the_parser_looks_for():
    """The loop closes: what :meth:`Anchors.render` writes, the parser reads.

    This is the one place the two halves have to agree, and they agree
    through :data:`_ANCHOR_HEADERS` rather than through two lists that
    happen to match today.
    """
    anchors = Anchors(
        user_intent="a",
        execution_progress="b",
        key_decisions="c",
        tried_solutions="d",
        next_steps="e",
    )

    rendered = anchors.render()

    assert rendered.splitlines()[0] == "### User Intent"
    assert rendered.endswith("### Next Steps\ne")
    assert parse_anchors_and_summary(rendered)[0] == anchors


def test_the_rendered_anchors_keep_a_blank_line_between_blocks():
    """``progressive_compactor.go:463-480``, and the bytes are the point.

    ``render`` produces the text that goes into
    :data:`~omicsclaw.context.summary.INCREMENTAL_TEMPLATE` on the next
    turn and into every compaction message this package writes, so its
    exact shape is prompt bytes: run the blocks together and the prefix
    changes for every conversation that has ever been compacted. The
    round-trip test cannot see it — :func:`parse_anchors_and_summary`
    reads the tight form just as happily.
    """
    rendered = Anchors(
        user_intent="a",
        execution_progress="b",
        key_decisions="c",
        tried_solutions="d",
        next_steps="e",
    ).render()

    assert rendered == (
        "### User Intent\na\n\n"
        "### Execution Progress\nb\n\n"
        "### Key Decisions\nc\n\n"
        "### Tried Solutions\nd\n\n"
        "### Next Steps\ne"
    )
    assert not rendered.endswith("\n"), "the trailing blank line is stripped"


def test_anchors_render_in_one_fixed_order():
    """``anchor.go:21-24``: the order *is* the contract.

    A compacted history that reshuffles its own anchors between turns
    changes the prompt prefix for no reason anybody can see.
    """
    rendered = Anchors().render()

    assert [line for line in rendered.splitlines() if line.startswith("###")] == [
        "### User Intent",
        "### Execution Progress",
        "### Key Decisions",
        "### Tried Solutions",
        "### Next Steps",
    ]
