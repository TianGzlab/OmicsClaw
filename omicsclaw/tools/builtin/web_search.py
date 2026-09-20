"""``web_search`` — one query to one search backend, no API key.

Modelled on harness9's ``internal/tools/web_search.go``, whose smallest
decision is the one worth keeping: it posts to DuckDuckGo's HTML endpoint
and parses the page. No key, no account, no vendor SDK, nothing to
configure wrong. For a layer that may import nothing outside the standard
library it is also the only shape available.

**What that costs is a dependency on somebody else's markup.**
``div.result``, ``a.result__a`` and ``a.result__snippet`` are class names
on a page DuckDuckGo may restyle any week, and the failure mode when they
change is **zero results rather than an error**: the request succeeds, the
parse finds nothing. :func:`parse_results` cannot tell "nothing matched"
from "the page is no longer shaped like this", so :func:`_report` names
both possibilities — the reference says only "no results found", which is
indistinguishable from a restyled page.

**The query is egress**, which is what the ``ASK`` policy is for: a search
query is text sent to a third party, and a model asked "is this variant
known" may put the variant in it. The whole query is in the approval
prompt, verbatim.

**World failure is not tool failure.** No results, a non-200 from the
backend and an unparseable page are returned as text with ``is_error``
false. A malformed query raises, because the model fixes that by sending
different arguments.

**Against the legacy ``web_search``**, which is untouched: it takes a
``topic`` enum (``general``/``news``/``finance``) that has no equivalent
here, and it returns **whole pages as markdown** by fetching every hit,
so one old call becomes one search plus N ``web_fetch`` calls, each with
its own approval. The split is the better design — a model should choose
what to read — but it is a workflow change, not a like-for-like
replacement. What is gained: no Tavily API key and no ``research`` extra.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools._html``,
``omicsclaw.tools._websafety``, ``omicsclaw.tools.base``,
``omicsclaw.tools.context``, ``omicsclaw.tools.function_tool``, and the
standard library.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from omicsclaw.schema import ToolDefinition

from .._html import MAX_BODY_BYTES
from .._websafety import (
    USER_AGENT,
    HttpResponse,
    PinnedTransport,
    Transport,
    TransportFailed,
    inspect_url,
)
from ..base import ApprovalMode, RiskLevel, ToolPolicy
from ..context import report_progress, require_approval
from ..function_tool import ToolArgumentError, decode_arguments, validate_arguments

TOOL_NAME = "web_search"
"""harness9's name, and like ``web_fetch``'s it collides.

``runtime/tools/builders/engineering.py`` has a ``web_search`` too, so the
two cannot be mounted in one registry and the migration has to retire one.
See ``builtin/web_fetch.py`` for the same note and why renaming was
rejected.
"""

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
"""The backend queried by default. ``web_search.go:26``.

The HTML endpoint rather than ``api.duckduckgo.com``, which returns JSON
and would be far easier to parse — and answers almost nothing for an
ordinary query, because it serves only what it has a structured answer
for. That trade is why the reference accepts a dependency on markup.
"""

SEARCH_TIMEOUT = 20.0
"""Seconds one search may take. ``web_search.go:24``.

Re-checked against the engine budget that made ``bash``'s 120 s unusable:
:attr:`~omicsclaw.engine.config.EngineConfig.tool_timeout` defaults to
60 s and wraps the whole call including the approval wait, so 20 s plus
``bash``'s 15 s margin fits with room over.
``tests/tools/test_web_search.py`` asserts the arithmetic.

Five seconds longer than ``web_fetch``'s, which survives checking: a
backend answering a query does more work than one serving a file.
"""

DEFAULT_RESULTS = 5
"""Results returned when the model does not ask. ``web_search.go:99``."""

MAX_RESULTS = 10
"""Most results one call returns, whatever is asked. ``web_search.go:102``.

Ten results with titles, URLs and snippets is roughly 1,500 characters.
The ceiling exists because a search is meant to *choose* a URL to fetch,
and a model given forty candidates will summarise them instead of picking
one.
"""

_RESULT_CLASS = "result"
_EXCLUDED_CLASS = "result--more"
_TITLE_CLASS = "result__a"
_SNIPPET_CLASS = "result__snippet"

_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
"""Tags with no end tag, so the nesting counter must not wait for one.

Not a concern in the reference, whose ``html.Parse`` builds a tree.
:class:`html.parser.HTMLParser` is a stream, so this module counts depth
itself, and a ``<br>`` inside a snippet would otherwise leave the counter
permanently one too deep — every later result swallowed into the first.
"""


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One hit: its title, its URL and its snippet."""

    title: str
    url: str
    snippet: str = ""


def _description() -> str:
    """The description, with the result ceiling interpolated from the code."""
    return (
        "Search the web and get back a list of titles, URLs and snippets. "
        "Use it when you do not already know which page answers the "
        "question, then pass a URL to web_fetch to read one. Runs against "
        "DuckDuckGo's HTML endpoint and needs no API key. Returns "
        f"{DEFAULT_RESULTS} results by default and at most {MAX_RESULTS}. "
        "THE QUERY TEXT IS SENT TO A THIRD-PARTY SEARCH ENGINE: never put "
        "data from the user's files, sequences, sample identifiers or "
        "patient information into a query. This tool asks the user for "
        "approval before searching."
    )


SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "What to search for. English usually works better. "
                "Required."
            ),
        },
        "max_results": {
            "type": "integer",
            "description": (
                f"How many results to return. Default {DEFAULT_RESULTS}, "
                f"clamped to {MAX_RESULTS}."
            ),
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}

_POLICY = ToolPolicy(
    risk_level=RiskLevel.MEDIUM,
    approval_mode=ApprovalMode.ASK,
    prompts_for_itself=True,
    read_only=False,
    concurrency_safe=True,
    touches_network=True,
    allowed_in_background=False,
    tags=frozenset({"network", "web", "egress"}),
)
"""``MEDIUM`` risk, ``ASK`` approval — and the asymmetry with ``web_fetch``
is a decision rather than an oversight.

Risk level follows blast radius, not the verb. ``web_fetch`` is ``HIGH``
because the model chooses an arbitrary destination, path and query: the
whole message is under its control. This tool sends **one field to one
fixed endpoint**, with no way to shape a request to an address of the
model's choosing. Grading the two identically would make the distinction
meaningless.

``ASK`` stays, because risk level and approval mode answer different
questions. A smaller payload is still a payload, and text sent to a search
engine cannot be recalled.
"""


class WebSearchTool:
    """Search the web and return titles, URLs and snippets.

    Satisfies :class:`~omicsclaw.tools.base.Tool` structurally, and is
    hand-written against it rather than wrapped because it asks a human and
    the prompt must carry the bytes the model sent.

    ``endpoint`` exists for a deployment running its own metasearch instance
    and is validated at construction, so a typo is a start-up failure in the
    assembly step that made it rather than a refusal in the middle of somebody
    's conversation. It is still checked and pinned per request: being
    configured by an operator does not exempt an address from the gate, and an
    endpoint pointed at ``127.0.0.1`` is refused on purpose.

    ``transport`` defaults to the gating, pinning
    :class:`~omicsclaw.tools._websafety.PinnedTransport`.
    """

    policy = _POLICY

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        endpoint: str = SEARCH_ENDPOINT,
        timeout: float = SEARCH_TIMEOUT,
    ) -> None:
        inspect_url(endpoint)
        self._endpoint = endpoint
        self._transport = transport or PinnedTransport()
        self._timeout = timeout
        self._definition = ToolDefinition(
            name=TOOL_NAME,
            description=_description(),
            input_schema=copy.deepcopy(SEARCH_SCHEMA),
        )

    @property
    def name(self) -> str:
        return TOOL_NAME

    @property
    def timeout(self) -> float:
        """This instance's per-request budget."""
        return self._timeout

    def definition(self) -> ToolDefinition:
        """The tool definition, built once so the prompt prefix stays stable."""
        return self._definition

    async def execute(self, arguments: str) -> str:
        """Search for the query in ``arguments`` and return the results.

        ``arguments`` is the raw JSON payload and reaches
        :func:`~omicsclaw.tools.context.require_approval` unparsed. Posts the
        query as a form to :attr:`_endpoint` after approval.

        Raises :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` for a
        payload that does not match the schema or an empty query. A backend error
        status and an empty result set are returned as text.
        """
        query, limit = _arguments(arguments)

        await require_approval(
            self.name,
            arguments,
            policy=self.policy,
            reason=self._reason(query),
        )
        await report_progress(f"searching for {query!r}", tool_name=self.name)

        try:
            response = await self._transport.request(
                "POST",
                self._endpoint,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html",
                },
                body=urlencode({"q": query}).encode("utf-8"),
                timeout=self._timeout,
                max_bytes=MAX_BODY_BYTES,
            )
        except TransportFailed as failure:
            # The world said no; no argument the model can send mends a
            # network, so this is output rather than ``is_error``.
            return (
                f"The search could not be delivered: {failure}. That is a "
                "network failure rather than a tool failure. Try again "
                "later, or fetch a known URL directly with web_fetch."
            )
        return _report(response, limit)

    # ---- internals ------------------------------------------------------

    def _reason(self, query: str) -> str:
        """The text a human is shown when asked to approve this search.

        Carries the query **verbatim**, on its own line: what is being reviewed is
        the exact text that will reach a third party, and "search for something
        about a gene" is not reviewable.
        """
        host = urlsplit(self._endpoint).hostname or self._endpoint
        return (
            f"send this search query to {host}:\n{query}\n"
            "That text leaves this machine. Approve only if none of it is "
            "data from the user's files."
        )


# ---- parsing somebody else's HTML ---------------------------------------


class _ResultParser(HTMLParser):
    """Pull ``div.result`` blocks out of a search backend's HTML response.

    ``web_search.go:161-213`` walks a parsed tree; this walks a stream,
    because :class:`html.parser.HTMLParser` is what the standard library
    offers. The difference shows in one place: a tree knows where a ``div``
    ends and a stream has to count, which is why :data:`_VOID_TAGS` exists.

    Nested ``div.result`` blocks are not entered twice. The snippet class is
    accepted on any element, where the reference requires an ``<a>``:
    DuckDuckGo has served both, and requiring the tag loses the snippet on a
    page whose title and URL parsed fine.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self._limit = limit
        self.results: list[SearchResult] = []
        self._depth = 0
        self._title: list[str] = []
        self._url = ""
        self._snippet: list[str] = []
        self._capture: str | None = None
        self._capture_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self.results) >= self._limit:
            return

        classes = _classes(attrs)

        if self._depth == 0:
            if (
                tag == "div"
                and _RESULT_CLASS in classes
                and _EXCLUDED_CLASS not in classes
            ):
                self._depth = 1
                self._title = []
                self._snippet = []
                self._url = ""
                self._capture = None
            return

        if tag not in _VOID_TAGS:
            self._depth += 1

        if self._capture is None:
            if _TITLE_CLASS in classes:
                self._capture = "title"
                self._capture_depth = self._depth
                self._url = decode_redirect(_attribute(attrs, "href"))
            elif _SNIPPET_CLASS in classes:
                self._capture = "snippet"
                self._capture_depth = self._depth

    def handle_endtag(self, tag: str) -> None:
        if self._depth == 0 or tag in _VOID_TAGS:
            return

        if self._capture is not None and self._depth == self._capture_depth:
            self._capture = None

        self._depth -= 1
        if self._depth == 0:
            self._finish()

    def handle_data(self, data: str) -> None:
        if self._capture == "title":
            self._title.append(data)
        elif self._capture == "snippet":
            self._snippet.append(data)

    def _finish(self) -> None:
        """Keep the finished block if it yielded both a title and a URL.

        That test is what drops advertisements and "related searches", which carry
        the ``result`` class and no ``result__a``.
        """
        title = _collapse("".join(self._title))
        if title and self._url:
            self.results.append(
                SearchResult(
                    title=title,
                    url=self._url,
                    snippet=_collapse("".join(self._snippet)),
                )
            )


def parse_results(markup: str, limit: int) -> list[SearchResult]:
    """Search results from a backend's HTML page, at most ``limit`` of them.

    Never raises: :class:`html.parser.HTMLParser` is tolerant, and a page this
    cannot read must come back as "no results, and here is why that might be"
    rather than as a tool failure. :func:`_report` makes that distinction
    visible.
    """
    parser = _ResultParser(max(0, limit))
    parser.feed(markup)
    parser.close()
    return parser.results[:limit]


def decode_redirect(href: str) -> str:
    """The real target behind a search engine's redirect wrapper.

    DuckDuckGo wraps every result as ``/l/?uddg=<encoded>&rut=…``, so the URL
    a model would otherwise be handed is a tracking hop rather than the page.
    Unwrapping matters beyond tidiness: the unwrapped URL is what a person
    sees in ``web_fetch``'s approval prompt next turn, and approving
    ``duckduckgo.com/l/?uddg=…`` asks them to judge a destination they cannot
    read.

    Uses :func:`urllib.parse.parse_qs`, which unescapes once. The
    reference parses the query properly too and then calls
    ``url.QueryUnescape`` on the **already-decoded** value
    (``web_search.go:222-227``), so a target containing ``%2B`` or ``%25``
    comes back corrupted by the second pass. Anything without a ``uddg``
    parameter is returned unchanged, so a backend that links directly
    still works.
    """
    if not href:
        return ""
    try:
        parts = urlsplit(href)
    except ValueError:
        return href
    values = parse_qs(parts.query).get("uddg")
    if values and values[0]:
        return values[0]
    return href


def _classes(attrs: list[tuple[str, str | None]]) -> frozenset[str]:
    """A tag's CSS classes as a set.

    Split on whitespace and compared whole, so ``result`` does not match
    ``result--more`` and ``results-wrapper`` does not match ``result``. A
    substring test would swallow every wrapper element on the page into the
    first result.
    """
    return frozenset(_attribute(attrs, "class").split())


def _attribute(attrs: list[tuple[str, str | None]], name: str) -> str:
    """One attribute's value, or ``""`` — never ``None``."""
    for key, value in attrs:
        if key.lower() == name and value:
            return value
    return ""


def _collapse(text: str) -> str:
    """Whitespace-normalised, single-line text."""
    return " ".join(text.split())


# ---- what the model reads ------------------------------------------------


def _report(response: HttpResponse, limit: int) -> str:
    """Format the results in ``response``, or say what happened instead.

    Three outcomes and none is an error: a backend that answered 503, a page
    that parsed to nothing and a genuine no-match are all facts about the
    world. The middle case is the one that will actually happen — the backend
    restyles its markup and every search silently returns nothing — so it is
    named rather than reported as "no results".
    """
    if not 200 <= response.status < 300:
        return (
            f"The search backend answered HTTP {response.status} "
            f"{response.reason}. That is the backend's response rather "
            "than a tool failure — it rate-limits automated queries, so "
            "trying once more later, or fetching a known URL directly "
            "with web_fetch, is usually the way forward."
        )

    markup = response.body.decode("utf-8", errors="replace")
    results = parse_results(markup, limit)

    if not results:
        return (
            "No results were parsed out of the search page. Either the "
            "query genuinely matched nothing — try different or broader "
            "terms — or the backend has changed the markup this tool "
            "reads, in which case no query will return anything and it "
            "needs fixing rather than rephrasing."
        )

    blocks = []
    for index, result in enumerate(results, start=1):
        lines = [f"[{index}] {result.title}", f"URL: {result.url}"]
        if result.snippet:
            lines.append(f"Snippet: {result.snippet}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _arguments(arguments: str) -> tuple[str, int]:
    """Decode ``arguments`` into ``(query, max_results)``.

    An empty query raises, where ``web_search.go:93-95`` returns
    ``"Error: query parameter is required"`` with no error set: the model
    fixes an empty query by sending a different one, and returning it as
    ordinary output teaches a model to read the word "Error" out of successful
    results. ``max_results`` is clamped to :data:`MAX_RESULTS`.
    """
    decoded = decode_arguments(arguments)
    issues = validate_arguments(decoded, SEARCH_SCHEMA)
    if issues:
        listed = "\n".join(f"  - {issue}" for issue in issues)
        raise ToolArgumentError(
            "the arguments do not match this tool's schema:\n"
            f"{listed}\nRe-send the call with all of these corrected."
        )

    query = str(decoded["query"]).strip()
    if not query:
        raise ToolArgumentError(
            "input.query is empty, so there is nothing to search for. Send "
            "the words you want looked up"
        )

    requested = decoded.get("max_results")
    limit = DEFAULT_RESULTS
    if isinstance(requested, int) and requested > 0:
        limit = min(requested, MAX_RESULTS)
    return query, limit


__all__ = [
    "DEFAULT_RESULTS",
    "MAX_RESULTS",
    "SEARCH_ENDPOINT",
    "SEARCH_SCHEMA",
    "SEARCH_TIMEOUT",
    "SearchResult",
    "TOOL_NAME",
    "WebSearchTool",
    "decode_redirect",
    "parse_results",
]
