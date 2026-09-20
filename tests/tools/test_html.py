"""Tests for ``omicsclaw.tools._html``.

Two things are being checked, and the second one is easy to lose sight of:

**Structure survives.** The point of not flattening a page to plain text
is that a model can tell a heading from a list item and can follow a
link. Each of those is pinned by a case that would pass if the tag were
dropped and fail if it were flattened.

**The known limitation is pinned as a limitation.** There is no
readability port in the standard library, so boilerplate removal is a
fixed tag list. The test that says so exists to stop the gap being
rediscovered as a bug, and to fail loudly if somebody changes the
approach without updating the module docstring that promises it.

**The layering rule does not apply to this file**, for the reason the
other tool tests record.
"""

from __future__ import annotations

from omicsclaw.tools._html import (
    DEFAULT_MAX_CHARS,
    HARD_MAX_CHARS,
    MAX_BODY_BYTES,
    assemble_page,
    extract,
    extract_page,
    truncate_text,
)

# ---- what the extractor keeps -------------------------------------------


def test_the_title_comes_from_the_title_tag():
    document = extract("<html><head><title>  A Page </title></head><body>x</body>")

    assert document.title == "A Page"


def test_the_first_heading_is_the_fallback_title():
    document = extract("<body><h1>Heading</h1><h2>Second</h2><p>x</p></body>")

    assert document.title == "Heading"


def test_headings_become_hashes_at_their_own_level():
    document = extract("<h1>One</h1><h3>Three</h3>")

    assert "# One" in document.content
    assert "### Three" in document.content


def test_a_link_keeps_its_text_and_its_target():
    document = extract('<p>see <a href="https://x.test/a">the docs</a> now</p>')

    assert "[the docs](https://x.test/a)" in document.content


def test_an_empty_anchor_does_not_leave_dangling_punctuation():
    document = extract('<p>text<a href="https://x.test/"><img src="i.png"></a></p>')

    assert "[](" not in document.content
    assert "[" not in document.content


def test_a_javascript_or_fragment_link_is_left_as_plain_text():
    document = extract(
        '<a href="javascript:x()">click</a> and <a href="#top">top</a>'
    )

    assert "click" in document.content and "top" in document.content
    assert "](" not in document.content


def test_list_items_become_dashes_on_their_own_lines():
    document = extract("<ul><li>first</li><li>second</li></ul>")

    assert "- first" in document.content
    assert "- second" in document.content
    assert "- first- second" not in document.content


def test_preformatted_text_keeps_its_whitespace_inside_a_fence():
    document = extract("<pre>def f():\n    return 1\n</pre>")

    assert "```" in document.content
    assert "    return 1" in document.content


def test_table_cells_are_separated_rather_than_run_together():
    document = extract("<table><tr><td>a</td><td>b</td></tr></table>")

    assert "a | b" in document.content


def test_a_line_break_is_a_line_break():
    document = extract("<p>one<br>two</p>")

    assert "one\ntwo" in document.content


def test_entities_arrive_decoded():
    document = extract("<p>a &amp; b &mdash; c &#8364;1</p>")

    assert "a & b — c €1" in document.content


def test_inline_tags_do_not_glue_adjacent_words_together():
    document = extract("<p><b>one</b> <i>two</i></p>")

    assert "one two" in document.content


# ---- what it drops ------------------------------------------------------


def test_script_and_style_contents_never_reach_the_output():
    document = extract(
        "<style>body{color:red}</style><p>real</p>"
        "<script>var secret = 1;</script>"
    )

    assert document.content == "real"


def test_nested_skipped_tags_leave_skip_mode_at_the_right_tag():
    """``<svg><style>…</style></svg><p>real</p>``: counting closes rather
    than tracking names would resume emitting inside the ``svg``."""
    document = extract("<svg><style>a{}</style><text>hidden</text></svg><p>real</p>")

    assert "hidden" not in document.content
    assert "real" in document.content


def test_navigation_and_footer_furniture_is_dropped():
    document = extract(
        "<nav>Home About</nav><header>Logo</header><p>the article</p>"
        "<aside>Ads</aside><footer>(c) 2026</footer>"
    )

    assert document.content == "the article"


def test_boilerplate_removal_is_a_tag_list_and_not_readability():
    """The limitation, pinned so it is not rediscovered as a bug.

    ``go-readability`` scores nodes and would drop this sidebar by
    measuring it. A fixed tag list cannot, so a ``<div class="sidebar">``
    comes through — which is the cost the module docstring states of
    having no readability in the standard library.
    """
    document = extract(
        '<div class="sidebar">Subscribe now</div><p>the article</p>'
    )

    assert "Subscribe now" in document.content


def test_broken_markup_does_not_raise_and_still_yields_content():
    document = extract("<p>unclosed <b>bold <div>and a div</p>")

    assert "unclosed" in document.content
    assert "and a div" in document.content


def test_a_page_that_reduces_to_nothing_comes_back_empty_rather_than_failing():
    """"Nothing readable" is an answer a fetch tool is allowed to give;
    it is not a tool failure."""
    assert extract("<script>only()</script>").content == ""
    assert extract("").content == ""


def test_blank_runs_are_collapsed_to_one_blank_line():
    document = extract("<div><div><p>a</p></div></div><section><p>b</p></section>")

    assert "\n\n\n" not in document.content


# ---- assembling and truncating ------------------------------------------


def test_the_page_carries_its_title_and_its_source():
    """The provenance line is what lets a model tell a quotation from its
    own knowledge when the text reappears many turns later."""
    page = assemble_page("https://x.test/p", "Title", "body text", 0)

    assert page.startswith("# Title\n\n> Source: https://x.test/p\n\n")
    assert page.endswith("body text")


def test_a_page_with_no_title_has_no_empty_heading():
    page = assemble_page("https://x.test/p", "", "body", 0)

    assert not page.startswith("#")
    assert page.startswith("> Source:")


def test_the_cut_prefers_a_line_break_past_the_halfway_mark():
    body = "a" * 40 + "\n" + "b" * 200
    page = assemble_page("https://x.test/p", "", body, 120)

    assert "Truncated" in page
    assert "b" * 10 not in page


def test_a_line_break_too_early_is_not_used_as_the_cut():
    """Otherwise a page whose first newline is at character 5 would be
    truncated to five characters in the name of keeping a paragraph
    whole."""
    body = "a\n" + "b" * 300
    page = assemble_page("https://x.test/p", "", body, 100)

    assert "b" in page


def test_truncation_never_splits_a_multi_byte_character():
    """The Go-ism deliberately **not** translated.

    ``web_content.go:91-93`` walks backwards while
    ``result[cut]&0xC0 == 0x80`` because a Go ``string`` is bytes and can
    be cut mid-character. A Python :class:`str` is code points, so the
    property holds for free and the loop would be unreachable code. This
    asserts the property rather than the loop.
    """
    page = assemble_page("https://x.test/p", "", "汉" * 400, 100)

    assert "�" not in page
    assert page.encode("utf-8").decode("utf-8") == page


def test_zero_or_negative_max_chars_means_the_default():
    body = "x" * (DEFAULT_MAX_CHARS + 500)

    for asked in (0, -1):
        assert "Truncated" in assemble_page("https://x.test/p", "", body, asked)


def test_max_chars_is_clamped_to_the_hard_ceiling():
    body = "x" * (HARD_MAX_CHARS + 5_000)
    page = assemble_page("https://x.test/p", "", body, HARD_MAX_CHARS * 10)

    assert "Truncated" in page
    assert len(page) < HARD_MAX_CHARS + 500


def test_plain_text_is_returned_without_a_title_or_a_source_line():
    """What makes this tool usable for a JSON endpoint or a
    ``robots.txt``: the bytes come back as they arrived."""
    assert truncate_text('{"a": 1}', 0) == '{"a": 1}'
    assert "Truncated" in truncate_text("y" * 100, 20)


def test_the_borrowed_literals_are_the_reference_numbers():
    """Pinned by name, because every other test compares against these
    constants and would follow them if one were changed."""
    assert DEFAULT_MAX_CHARS == 8_000  # web_content.go:20
    assert HARD_MAX_CHARS == 32_000  # web_content.go:21
    assert MAX_BODY_BYTES == 1 << 20  # web_content.go:22


def test_extract_page_is_extract_then_assemble():
    markup = "<html><head><title>T</title></head><body><p>body</p></body></html>"

    page = extract_page(markup, "https://x.test/p", 0)

    assert page == assemble_page("https://x.test/p", "T", "body", 0)


# ---- repairs from the independent audit ---------------------------------


def test_a_duplicated_attribute_takes_the_first_value():
    """What the HTML5 tree-construction algorithm does, and therefore what
    a reader saw in their browser. The same rule is spelled the same way in
    ``builtin/web_search.py``; two helpers of one name disagreeing about
    ``<a href="http://good/" href="http://evil/">`` is the sort of thing
    nobody finds twice."""
    document = extract('<a href="https://good.test/" href="https://evil.test/">x</a>')

    assert "https://good.test/" in document.content
    assert "evil" not in document.content


def test_an_unbalanced_tag_inside_skipped_markup_does_not_end_the_skip():
    """Skip mode is tracked by tag name rather than by counting closes.
    With counting, ``</div>`` here pops the ``nav`` and everything after it
    leaks into the model's context."""
    document = extract("<nav><div>menu</div>LEAK</nav><p>real</p>")

    assert "LEAK" not in document.content
    assert "menu" not in document.content
    assert document.content == "real"


def test_list_items_are_separated_by_exactly_one_newline():
    """``_break``'s accounting, which the blank-run collapse in
    :meth:`_Extractor.document` would otherwise cover for: it cleans up
    runs of three or more, so an implementation that appended blindly
    would still pass every other test here."""
    document = extract("<ul><li>one</li><li>two</li><li>three</li></ul>")

    assert "- one\n- two\n- three" in document.content


def test_the_truncation_notice_reports_what_was_actually_shown():
    """The cut is pulled back to a line break, so reporting the ceiling
    tells the model it has seen more than it has — and a model computing
    an offset from that number skips content."""
    body = "a" * 40 + "\n" + "b" * 200
    page = assemble_page("https://x.test/p", "", body, 120)

    shown = page.split("\n\n[Truncated")[0]
    assert f"the first {len(shown)} characters" in page
    assert "the first 120 characters" not in page


def test_the_plain_text_notice_reports_the_whole_length_too():
    page = truncate_text("y" * 100, 20)

    assert "the first 20 characters of 100" in page
