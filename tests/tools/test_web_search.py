"""Contract tests for ``omicsclaw.tools.builtin.web_search``.

The parsing tests are the substance here, because the tool's dependency
is somebody else's markup and the failure mode when that markup changes
is **zero results rather than an error**. So the fixtures below are shaped
like the real DuckDuckGo HTML page, and each structural assumption —
``div.result``, ``a.result__a``, the ``uddg`` redirect wrapper — is pinned
by a case that fails if the assumption is dropped.

Everything else mirrors ``test_web_fetch.py``: the approval gate, the
order of operations, and which outcomes are the world's fault.

**The layering rule does not apply to this file**, which is what lets it
import :class:`~omicsclaw.engine.config.EngineConfig` for the timeout
coupling.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Coroutine, Mapping, TypeVar
from urllib.parse import parse_qs

import pytest

from omicsclaw.engine import EngineConfig
from omicsclaw.schema import ToolCall
from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalMode,
    ApprovalRequest,
    ApprovalUnavailable,
    RiskLevel,
    Tool,
    ToolPolicy,
    ToolRegistry,
    WebSearchTool,
)
from omicsclaw.tools._html import MAX_BODY_BYTES
from omicsclaw.tools._websafety import (
    USER_AGENT,
    HttpResponse,
    TransportFailed,
    UrlMalformed,
)
from omicsclaw.tools.builtin.bash import ENGINE_TIMEOUT_MARGIN
from omicsclaw.tools.builtin.web_search import (
    DEFAULT_RESULTS,
    MAX_RESULTS,
    SEARCH_ENDPOINT,
    SEARCH_SCHEMA,
    SEARCH_TIMEOUT,
    TOOL_NAME,
    decode_redirect,
    parse_results,
)
from omicsclaw.tools.context import use_tool_context
from omicsclaw.tools.function_tool import ToolArgumentError

_T = TypeVar("_T")

_DEADLINE = 10.0


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; the suite drives this way."""
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


def _args(**kwargs: Any) -> str:
    return json.dumps(kwargs)


def _yes(seen: list[ApprovalRequest] | None = None):
    def channel(request: ApprovalRequest) -> ApprovalDecision:
        if seen is not None:
            seen.append(request)
        return ApprovalDecision(approved=True)

    return channel


def _no():
    def channel(request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=False, reason="no")

    return channel


def _hit(index: int, target: str = "") -> str:
    """One result block, shaped like the real page."""
    href = target or f"//duckduckgo.com/l/?uddg=https%3A%2F%2Fsite{index}.test%2Fp"
    return (
        '<div class="result results_links results_links_deep web-result">'
        '<div class="result__body">'
        f'<h2 class="result__title"><a class="result__a" href="{href}">'
        f"Result {index}</a></h2>"
        f'<a class="result__snippet" href="{href}">Snippet  {index}</a>'
        "</div></div>"
    )


def _page(*blocks: str) -> bytes:
    return ("<html><body>" + "".join(blocks) + "</body></html>").encode("utf-8")


class _FakeTransport:
    def __init__(self, *responses: HttpResponse) -> None:
        self.queue = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 10.0,
        max_bytes: int = 1 << 20,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "body": body,
                "timeout": timeout,
                "max_bytes": max_bytes,
            }
        )
        return self.queue.pop(0)


def _response(status: int = 200, body: bytes | None = None, **kwargs: Any):
    fields: dict[str, Any] = {
        "status": status,
        "reason": "OK",
        "headers": {"Content-Type": "text/html"},
        "body": body if body is not None else _page(_hit(1), _hit(2)),
        "url": SEARCH_ENDPOINT,
    }
    fields.update(kwargs)
    return HttpResponse(**fields)


def _search(transport: _FakeTransport, *, approve=None, **kwargs: Any) -> str:
    tool = WebSearchTool(transport=transport)
    with use_tool_context(approval=approve if approve is not None else _yes()):
        return _run(tool.execute(_args(**kwargs)))


# ---- the ordinary job ----------------------------------------------------


def test_results_come_back_numbered_with_url_and_snippet():
    output = _search(_FakeTransport(_response()), query="brca1 variant")

    assert "[1] Result 1" in output
    assert "URL: https://site1.test/p" in output
    assert "Snippet: Snippet 1" in output
    assert "[2] Result 2" in output


def test_the_query_is_posted_as_a_form_to_the_endpoint():
    transport = _FakeTransport(_response())

    _search(transport, query="a query & more")

    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == SEARCH_ENDPOINT
    assert parse_qs(call["body"].decode())["q"] == ["a query & more"]
    assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert call["headers"]["User-Agent"] == USER_AGENT
    assert call["timeout"] == SEARCH_TIMEOUT
    assert call["max_bytes"] == MAX_BODY_BYTES


def test_the_result_count_defaults_and_is_clamped():
    many = _page(*[_hit(index) for index in range(1, 13)])
    transport = _FakeTransport(_response(body=many), _response(body=many))
    tool = WebSearchTool(transport=transport)

    with use_tool_context(approval=_yes()):
        default = _run(tool.execute(_args(query="q")))
        asked_too_many = _run(tool.execute(_args(query="q", max_results=99)))

    assert default.count("URL:") == DEFAULT_RESULTS
    assert asked_too_many.count("URL:") == MAX_RESULTS


def test_a_snippet_is_optional():
    without = (
        '<div class="result"><a class="result__a" href="https://x.test/p">'
        "Title</a></div>"
    )
    output = _search(_FakeTransport(_response(body=_page(without))), query="q")

    assert "[1] Title" in output
    assert "Snippet:" not in output


# ---- parsing somebody else's markup -------------------------------------


def test_the_more_results_block_is_excluded():
    """``result--more`` carries the ``result`` class and is the "more
    results" footer rather than a hit. Splitting the class attribute on
    whitespace and comparing whole tokens is what keeps them apart — a
    substring test would swallow it."""
    page = _page(
        _hit(1),
        '<div class="result result--more"><a class="result__a" href="/more">'
        "More results</a></div>",
    )

    results = parse_results(page.decode(), 10)

    assert [result.title for result in results] == ["Result 1"]


def test_a_wrapper_whose_class_merely_starts_with_result_is_not_a_hit():
    page = _page(
        '<div class="results-wrapper"><p>ads</p></div>',
        _hit(1),
    )

    assert len(parse_results(page.decode(), 10)) == 1


def test_a_block_with_no_title_link_is_dropped():
    """What removes advertisements and "related searches": they carry the
    ``result`` class and no ``result__a``."""
    page = _page(
        '<div class="result result--ad"><span>Sponsored</span></div>',
        _hit(1),
    )

    results = parse_results(page.decode(), 10)

    assert [result.title for result in results] == ["Result 1"]


def test_a_void_element_inside_a_result_does_not_swallow_the_next_one():
    """The stream parser counts nesting itself, so a ``<br>`` that never
    closes would otherwise leave the counter permanently one too deep and
    every later result inside the first."""
    page = _page(
        '<div class="result"><a class="result__a" href="https://x.test/1">One'
        '</a><br><img src="i.png"><a class="result__snippet">S</a></div>',
        _hit(2),
    )

    results = parse_results(page.decode(), 10)

    assert [result.title for result in results] == ["One", "Result 2"]


def test_a_snippet_served_as_a_div_is_still_read():
    """Deliberately more tolerant than the reference, which requires the
    snippet to be an ``<a>``: DuckDuckGo has served both, and requiring
    the tag loses the snippet on a page whose title parsed fine."""
    page = _page(
        '<div class="result"><a class="result__a" href="https://x.test/1">T</a>'
        '<div class="result__snippet">from a div</div></div>'
    )

    assert parse_results(page.decode(), 10)[0].snippet == "from a div"


def test_nested_markup_inside_the_title_is_flattened():
    page = _page(
        '<div class="result"><a class="result__a" href="https://x.test/1">'
        "<b>Bold</b> and <i>italic</i></a></div>"
    )

    assert parse_results(page.decode(), 10)[0].title == "Bold and italic"


def test_broken_markup_does_not_raise():
    """A page this cannot read must come back as "no results" rather than
    as a tool failure."""
    assert parse_results("<div class='result'><a class='result__a'", 5) == []
    assert parse_results("", 5) == []
    assert parse_results("not html at all", 5) == []


def test_a_limit_of_zero_returns_nothing_rather_than_everything():
    page = _page(_hit(1), _hit(2))

    assert parse_results(page.decode(), 0) == []


# ---- the redirect wrapper ----------------------------------------------


def test_the_uddg_wrapper_is_unwrapped_to_the_real_target():
    """The URL a model is handed has to be the page, not a tracking hop:
    it is what a person sees in ``web_fetch``'s approval prompt next turn,
    and approving ``duckduckgo.com/l/?uddg=…`` asks them to judge a
    destination they cannot read."""
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Freal.test%2Fpage&rut=abc"

    assert decode_redirect(href) == "https://real.test/page"


def test_a_target_containing_an_ampersand_survives_unwrapping():
    """Why :func:`urllib.parse.parse_qs` rather than a manual unquote of a
    substring, which is what the reference does and which loses everything
    after the first ``&``."""
    href = "/l/?uddg=https%3A%2F%2Freal.test%2Fp%3Fa%3D1%26b%3D2&rut=x"

    assert decode_redirect(href) == "https://real.test/p?a=1&b=2"


def test_a_direct_link_is_returned_unchanged():
    """So a self-hosted backend that links directly still works."""
    assert decode_redirect("https://real.test/p") == "https://real.test/p"
    assert decode_redirect("") == ""


def test_an_unparseable_href_is_returned_rather_than_dropped():
    assert decode_redirect("http://[bad") == "http://[bad"


# ---- world failure is not tool failure ----------------------------------


def test_a_backend_error_status_is_returned_as_text_not_as_a_failure():
    registry = ToolRegistry()
    registry.register(
        WebSearchTool(
            transport=_FakeTransport(
                _response(429, reason="Too Many Requests", body=b"")
            )
        ),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    result = _run(
        registry.execute(
            ToolCall(id="1", name=TOOL_NAME, arguments=_args(query="q"))
        )
    )

    assert result.is_error is False
    assert "HTTP 429" in result.output
    assert "rate-limits" in result.output


def test_no_results_names_the_possibility_that_the_markup_changed():
    """The failure this tool will actually have. The reference says only
    "no results found", which is indistinguishable from a restyled page —
    and a restyled page means *every* query returns nothing."""
    output = _search(_FakeTransport(_response(body=_page())), query="q")

    assert "matched nothing" in output
    assert "changed the markup" in output


def test_an_empty_query_is_an_error_rather_than_ordinary_output():
    """**A deliberate deviation** from ``web_search.go:93-95``, which
    returns ``"Error: query parameter is required"`` with no error set.
    The model fixes an empty query by sending a different one, so it
    belongs on the ``is_error`` side; returning it as output teaches a
    model to read the word "Error" out of successful results."""
    registry = ToolRegistry()
    registry.register(
        WebSearchTool(transport=_FakeTransport()),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    result = _run(
        registry.execute(
            ToolCall(id="1", name=TOOL_NAME, arguments=_args(query="   "))
        )
    )

    assert result.is_error is True
    assert "nothing to search for" in result.output


# ---- approval -----------------------------------------------------------


def test_nothing_is_sent_until_the_approval_is_given():
    transport = _FakeTransport(_response())

    with pytest.raises(ApprovalDenied):
        _search(transport, approve=_no(), query="a private identifier")

    assert transport.calls == []


def test_with_no_channel_bound_the_search_fails_closed():
    transport = _FakeTransport(_response())
    tool = WebSearchTool(transport=transport)

    with pytest.raises(ApprovalUnavailable):
        with use_tool_context():
            _run(tool.execute(_args(query="q")))

    assert transport.calls == []


def test_the_prompt_shows_the_query_verbatim_and_names_the_destination():
    """A summary would defeat the purpose: what is being reviewed is the
    exact text that will reach a third party."""
    seen: list[ApprovalRequest] = []
    query = "BRCA1 c.68_69delAG sample P12345"

    _search(_FakeTransport(_response()), approve=_yes(seen), query=query)

    assert query in seen[0].reason
    assert "html.duckduckgo.com" in seen[0].reason
    assert "leaves this machine" in seen[0].reason


def test_the_risk_level_is_below_web_fetchs_and_the_approval_is_not():
    """The asymmetry is the decision. ``web_fetch`` lets the model choose
    an arbitrary destination, path and query; this sends one field to one
    fixed endpoint, which is a materially smaller radius. ``ASK`` stays
    because a smaller payload is still irreversible egress."""
    policy = WebSearchTool.policy

    assert policy.risk_level is RiskLevel.MEDIUM
    assert policy.approval_mode is ApprovalMode.ASK
    assert policy.touches_network is True
    assert policy.allowed_in_background is False


def test_a_cancelled_turn_is_not_reported_to_the_model_as_a_failure():
    transport = _FakeTransport(_response())
    tool = WebSearchTool(transport=transport)

    async def cancelling(request: ApprovalRequest) -> ApprovalDecision:
        raise asyncio.CancelledError

    async def main() -> None:
        with use_tool_context(approval=cancelling):
            await tool.execute(_args(query="q"))

    with pytest.raises(asyncio.CancelledError):
        _run(main())

    assert transport.calls == []


# ---- configuration ------------------------------------------------------


def test_a_custom_endpoint_is_used_and_validated_at_construction():
    """A typo should be a start-up failure in whichever assembly step made
    it, not a refusal in the middle of somebody's conversation."""
    transport = _FakeTransport(_response())
    tool = WebSearchTool(transport=transport, endpoint="https://searx.test/search")

    with use_tool_context(approval=_yes()):
        _run(tool.execute(_args(query="q")))

    assert transport.calls[0]["url"] == "https://searx.test/search"
    with pytest.raises(UrlMalformed):
        WebSearchTool(endpoint="not-a-url")


def test_the_default_endpoint_is_the_html_one_rather_than_the_json_api():
    """``api.duckduckgo.com`` is easier to parse and answers almost
    nothing for an ordinary query; the HTML endpoint is the one that
    searches."""
    assert SEARCH_ENDPOINT == "https://html.duckduckgo.com/html/"
    assert "api." not in SEARCH_ENDPOINT


# ---- the timeout coupling this layer cannot see -------------------------


def test_the_search_budget_fits_inside_the_engines_per_tool_deadline():
    """``EngineConfig.tool_timeout`` wraps the whole call including the
    approval wait, and ``omicsclaw/tools/`` may not import the engine —
    so this arithmetic is asserted here or nowhere. No overrides are
    passed, so lowering the engine default fails this test."""
    assert SEARCH_TIMEOUT == 20.0  # web_search.go:24
    assert SEARCH_TIMEOUT + ENGINE_TIMEOUT_MARGIN <= EngineConfig().tool_timeout
    assert WebSearchTool().timeout == SEARCH_TIMEOUT


# ---- the definition a model is shown ------------------------------------


def test_the_tool_satisfies_the_protocol_and_agrees_with_its_own_name():
    tool = WebSearchTool()

    assert isinstance(tool, Tool)
    assert tool.name == TOOL_NAME == tool.definition().name == "web_search"


def test_the_definition_is_stable_and_not_shared_between_instances():
    first, second = WebSearchTool(), WebSearchTool()

    assert first.definition() is first.definition()
    first.definition().input_schema["properties"].pop("query")
    assert "query" in second.definition().input_schema["properties"]
    assert "query" in SEARCH_SCHEMA["properties"]


def test_the_description_warns_that_the_query_is_transmitted():
    description = WebSearchTool().definition().description

    assert "SENT TO A THIRD-PARTY SEARCH ENGINE" in description
    assert str(MAX_RESULTS) in description


def test_the_borrowed_result_limits_are_the_reference_numbers():
    assert DEFAULT_RESULTS == 5  # web_search.go:99
    assert MAX_RESULTS == 10  # web_search.go:102


def test_a_payload_that_is_not_this_tools_shape_is_correctable():
    tool = WebSearchTool(transport=_FakeTransport())

    with use_tool_context(approval=_yes()):
        with pytest.raises(ToolArgumentError) as missing:
            _run(tool.execute("{}"))
        with pytest.raises(ToolArgumentError) as extra:
            _run(tool.execute(_args(query="q", region="us")))

    assert "query" in str(missing.value)
    assert "region" in str(extra.value)


# ---- repairs from the independent audit ---------------------------------


class _FailingTransport:
    async def request(self, method, url, **kwargs):
        raise TransportFailed("could not reach the backend: connection reset")


def test_a_network_failure_is_reported_as_the_world_failing_not_the_tool():
    """``web_search.go:106-108`` returns the failure as ordinary output.
    No argument the model can send mends a network."""
    registry = ToolRegistry()
    registry.register(
        WebSearchTool(transport=_FailingTransport()),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    result = _run(
        registry.execute(ToolCall(id="1", name=TOOL_NAME, arguments=_args(query="q")))
    )

    assert result.is_error is False
    assert "network failure rather than a tool failure" in result.output


def test_a_duplicated_href_takes_the_first_value_here_too():
    """The same rule as ``_html._attribute``, which previously took the
    last: for ``<a href="good" href="evil">`` the two helpers disagreed."""
    page = _page(
        '<div class="result"><a class="result__a" href="https://good.test/"'
        ' href="https://evil.test/">Title</a></div>'
    )

    assert parse_results(page.decode(), 5)[0].url == "https://good.test/"
