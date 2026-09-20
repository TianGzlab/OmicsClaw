"""HTML reduced to something a model can read, standard library only.

Modelled on harness9's ``internal/tools/web_content.go``, and the one
place in this work where the reference cannot be ported, only answered:
its pipeline is ``go-readability → html-to-markdown``, both third-party
Go libraries, and this package may import nothing outside the standard
library. There is no readability in it and no HTML-to-Markdown converter.

**So what ships is a better version of the reference's fallback path.**
Tags that are never content (``script``, ``style`` and neighbours) are
dropped, as ``extractPlainText`` does; tags that are structurally
boilerplate (``nav``, ``header``, ``footer``, ``aside``, ``form``) are
dropped too; and structure is kept rather than flattened — headings as
``#``, list items as ``-``, links as ``[text](url)``, ``pre`` in a fence.

**The gap, stated rather than papered over:** ``go-readability`` finds
the article by *scoring* nodes, so it discards a sidebar built from a
``<div class="sidebar">``. A fixed tag list cannot. On a documentation
page or a blog post the two are close; on a news site heavy with
promotional furniture this returns more noise.

**Truncation** aligns the cut to the last newline before the ceiling when
that newline is past the halfway point, so a page is cut at a paragraph
rather than mid-sentence. What is *not* ported is the loop after it in
``web_content.go:91-93``, which walks backwards off a partial UTF-8
character: a Go ``string`` is bytes and can be split mid-character, while
a Python :class:`str` is code points and ``text[:n]`` cannot be.

**Leaf-adjacent.** The standard library only — :mod:`html.parser` and
:mod:`re`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

DEFAULT_MAX_CHARS = 8_000
"""Characters returned unless the model asks for fewer. ``web_content.go:20``.

Counted in characters where the reference counts bytes, because the bytes
are decoded once before anything measures them. For English the two
agree; for a Chinese page this is about three times as generous in bytes
and identical in what it costs the model, which is the side the number
rations. Roughly 2,000 tokens.
"""

HARD_MAX_CHARS = 32_000
"""Ceiling on ``max_chars`` whatever the model asks for. ``web_content.go:21``.

Four times the default: room for a genuinely long reference page, without
letting one fetch consume a model's whole window.
"""

MAX_BODY_BYTES = 1 << 20
"""Bytes of HTML read before the page is considered over-long.
``web_content.go:22``.

Stays in bytes, unlike the two above, because this rations the wire and
memory rather than the model's context.
"""

_SKIP_TAGS = frozenset(
    {"script", "style", "noscript", "template", "svg", "canvas", "iframe"}
)
"""Tags that are never content, so their text is discarded.

``script`` and ``style`` are the reference's; the rest are the same kind
of thing — an ``<svg>``'s path data and a ``<template>``'s unrendered
markup are text to a parser and noise to a reader.
"""

_BOILERPLATE_TAGS = frozenset({"nav", "header", "footer", "aside", "form"})
"""Tags that are structurally furniture, dropped along with their text.

Not in the reference, and not readability: it removes these by scoring,
and this is the crude approximation the layering rule leaves available.
Listed separately from :data:`_SKIP_TAGS` because the claim is weaker —
these are *usually* not the content somebody asked for, and a page whose
whole body sits inside a ``<header>`` comes back empty.
"""

_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "blockquote",
        "body",
        "div",
        "dd",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "hr",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "tfoot",
        "thead",
        "ul",
    }
)
"""Tags whose boundaries become a blank line in the output."""

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

_WHITESPACE = re.compile(r"[ \t\r\f\v\xa0]+")
r"""Runs of horizontal whitespace, collapsed to one space.

``\n`` is absent on purpose: newlines are how this module records
structure. ``\xa0`` is spelled as an escape rather than written as the raw
character, which an editor normalising whitespace would silently delete.
A non-breaking space between
words is a space to a reader and a distinct character to
:meth:`str.split`.
"""

_BLANK_RUN = re.compile(r"\n{3,}")
"""Three or more newlines, i.e. more than one blank line."""


@dataclass(frozen=True, slots=True)
class Document:
    """A page reduced to a title and a body."""

    title: str
    """``<title>``, or the first ``<h1>``, or ``""``."""

    content: str
    """Markdown-shaped body text, whitespace already normalised."""


class _Extractor(HTMLParser):
    """Walks markup once and emits Markdown-shaped pieces.

    One pass and no tree, which is both what the standard library offers and
    what suits a linear output: the only state worth keeping is "what am I
    inside of".

    ``convert_charrefs`` is left at its default, so ``&amp;`` and ``&#8212;``
    arrive decoded in :meth:`handle_data`. :class:`html.parser.HTMLParser` is
    also tolerant of broken markup, which matters here more than anywhere:
    real pages have unclosed tags, and a strict parser would return nothing
    for a page a browser renders fine.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._pieces: list[str] = []
        self._skipping: list[str] = []
        self._pre_depth = 0
        self._title_parts: list[str] = []
        self._in_title = False
        self._link: str | None = None
        self._link_start = 0
        self._first_heading: list[str] = []
        self._in_first_heading = False
        self._seen_heading = False

    # ---- output ---------------------------------------------------------

    def document(self) -> Document:
        """The page so far, whitespace normalised and blank runs collapsed."""
        body = "".join(self._pieces)
        body = _BLANK_RUN.sub("\n\n", body).strip()
        title = " ".join("".join(self._title_parts).split())
        if not title:
            title = " ".join("".join(self._first_heading).split())
        return Document(title=title, content=body)

    def _emit(self, text: str) -> None:
        if text:
            self._pieces.append(text)

    def _break(self, newlines: int) -> None:
        """Ask for ``newlines`` of separation, without stacking blank lines.

        Counts the newlines already at the tail rather than appending blindly, so
        ``</p></div></section>`` is one paragraph break and not three. Fixing
        that afterwards with a regex would work but would lose the ability to ask
        for a single newline inside a list.
        """
        if not self._pieces:
            return
        tail = "".join(self._pieces[-3:])
        existing = len(tail) - len(tail.rstrip("\n"))
        if existing >= newlines:
            return
        self._pieces.append("\n" * (newlines - existing))

    # ---- parser callbacks -----------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skipping:
            # Track nesting by name so that ``<svg><style>`` leaves skip
            # mode once, at the right tag, rather than on the first close.
            if tag in _SKIP_TAGS or tag in _BOILERPLATE_TAGS:
                self._skipping.append(tag)
            return

        if tag in _SKIP_TAGS or tag in _BOILERPLATE_TAGS:
            self._skipping.append(tag)
            return

        if tag == "title":
            self._in_title = True
            return

        if tag == "br":
            self._emit("\n")
            return

        if tag in _HEADINGS:
            self._break(2)
            self._emit("#" * _HEADINGS[tag] + " ")
            if not self._seen_heading:
                self._in_first_heading = True
            return

        if tag == "li":
            self._break(1)
            self._emit("- ")
            return

        if tag in ("td", "th"):
            if self._pieces and not "".join(self._pieces[-2:]).endswith("\n"):
                self._emit(" | ")
            return

        if tag == "tr":
            self._break(1)
            return

        if tag == "pre":
            self._break(2)
            self._emit("```\n")
            self._pre_depth += 1
            return

        if tag == "a":
            href = _attribute(attrs, "href")
            if href and not href.startswith(("javascript:", "#")):
                self._link = href
                self._link_start = len(self._pieces)
                self._emit("[")
            return

        if tag in _BLOCK_TAGS:
            self._break(2)

    def handle_endtag(self, tag: str) -> None:
        if self._skipping:
            if tag == self._skipping[-1]:
                self._skipping.pop()
            return

        if tag == "title":
            self._in_title = False
            return

        if tag in _HEADINGS:
            self._in_first_heading = False
            self._seen_heading = True
            self._break(2)
            return

        if tag == "pre":
            if self._pre_depth:
                self._pre_depth -= 1
            self._break(1)
            self._emit("```")
            self._break(2)
            return

        if tag == "a" and self._link is not None:
            inner = "".join(self._pieces[self._link_start + 1 :]).strip()
            if inner:
                self._emit(f"]({self._link})")
            else:
                # An empty anchor — an icon, a named target — would render
                # as a bare ``[](url)``. Drop the opening bracket instead
                # of leaving punctuation with nothing in it.
                del self._pieces[self._link_start :]
            self._link = None
            return

        if tag == "li":
            self._break(1)
            return

        if tag in _BLOCK_TAGS:
            self._break(2)

    def handle_data(self, data: str) -> None:
        if self._skipping:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._pre_depth:
            # Inside ``pre`` the whitespace *is* the content.
            self._emit(data)
            return

        text = _WHITESPACE.sub(" ", data)
        if not text.strip():
            # Whitespace between tags is layout, not content — except that
            # dropping it entirely would run "one" and "two" together in
            # ``<b>one</b> <b>two</b>``. So it collapses to a single space
            # and only when something is already there to separate.
            if text and self._pieces and not self._pieces[-1].endswith((" ", "\n")):
                self._emit(" ")
            return

        cleaned = text.replace("\n", " ")
        if self._in_first_heading:
            self._first_heading.append(cleaned)
        self._emit(cleaned)


def _attribute(attrs: list[tuple[str, str | None]], name: str) -> str:
    """One attribute's value, or ``""`` — never ``None``.

    **First wins**, which is what the HTML5 tree-construction algorithm
    does with a duplicated attribute and therefore what a reader saw in
    their browser. :class:`html.parser.HTMLParser` reports both, so the
    choice has to be made here, and it is made the same way in
    ``builtin/web_search.py`` — two helpers of one name disagreeing about
    ``<a href="http://good/" href="http://evil/">`` is the sort of thing
    nobody finds twice.
    """
    for key, value in attrs:
        if key.lower() == name and value:
            return value
    return ""


def extract(markup: str) -> Document:
    """Reduce HTML to a :class:`Document`.

    Never raises on bad markup: a page a browser renders must not become a
    tool failure because a tag was left unclosed. A page that reduces to
    nothing returns empty :attr:`Document.content`, which a caller reports as
    an empty page rather than as an error.
    """
    parser = _Extractor()
    parser.feed(markup)
    parser.close()
    return parser.document()


def assemble_page(url: str, title: str, content: str, max_chars: int) -> str:
    """Title, source line and body, truncated to ``max_chars``.

    ``max_chars`` of zero or less means :data:`DEFAULT_MAX_CHARS`, and
    anything above :data:`HARD_MAX_CHARS` is clamped to it.

    The source line is kept from the reference for a reason it does not
    state: the body is Markdown containing whatever links the page had, and
    without a line saying where it came from a model has no way to tell a
    quotation from its own knowledge when the text reappears twenty turns
    later.

    The cut prefers the last newline before the ceiling, but only past the
    halfway mark — otherwise a page whose first newline is at character 40
    would be truncated to 40 characters in the name of keeping a paragraph
    whole.
    """
    limit = DEFAULT_MAX_CHARS if max_chars <= 0 else min(max_chars, HARD_MAX_CHARS)

    head = f"# {title}\n\n" if title else ""
    result = f"{head}> Source: {url}\n\n{content}"
    if len(result) <= limit:
        return result

    cut = limit
    newline = result.rfind("\n", 0, limit)
    if newline > limit // 2:
        cut = newline
    return (
        f"{result[:cut]}\n\n[Truncated: the first {cut} characters of "
        f"{len(result)} are shown. Fetch the URL again with a larger "
        "max_chars, or read the rest another way]"
    )


def extract_page(markup: str, url: str, max_chars: int) -> str:
    """:func:`extract` followed by :func:`assemble_page`."""
    document = extract(markup)
    return assemble_page(url, document.title, document.content, max_chars)


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate a plain-text body to ``max_chars``, with no title or source
    line.

    Separate from :func:`assemble_page` because a ``text/plain`` response is
    returned as it arrived, which is what makes a fetch tool usable for a
    JSON endpoint or a ``robots.txt``.
    """
    limit = DEFAULT_MAX_CHARS if max_chars <= 0 else min(max_chars, HARD_MAX_CHARS)
    if len(text) <= limit:
        return text
    return (
        f"{text[:limit]}\n\n[Truncated: the first {limit} characters of "
        f"{len(text)} are shown]"
    )


__all__ = [
    "DEFAULT_MAX_CHARS",
    "Document",
    "HARD_MAX_CHARS",
    "MAX_BODY_BYTES",
    "assemble_page",
    "extract",
    "extract_page",
    "truncate_text",
]
