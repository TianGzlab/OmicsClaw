"""Contract tests for ``omicsclaw.tools.builtin.web_fetch``.

The gate itself is tested in ``test_websafety.py``; what is tested here is
the tool wrapped around it — the order of operations, what a human is
shown, and which outcomes are the model's fault rather than the world's.

Two assertions carry most of the weight:

**The approval happens before the request and after the shape check.**
A malformed URL must be refused without a prompt, and a well-formed one
must not reach the transport until consent is given. Both are checked by
looking at what the transport was asked for.

**A 404 is not a tool failure.** ``is_error`` is the model's signal about
what to change next, and a model told its tool broke will try to fix the
tool rather than the URL.

**The layering rule does not apply to this file**, which is what lets it
import :class:`~omicsclaw.engine.config.EngineConfig` to assert the
timeout coupling the production module cannot see.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Coroutine, Mapping, TypeVar

import pytest

from omicsclaw.engine import EngineConfig
from omicsclaw.schema import ToolCall
from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalMode,
    ApprovalRequest,
    ApprovalUnavailable,
    ProgressUpdate,
    RiskLevel,
    Tool,
    ToolPolicy,
    ToolRegistry,
    WebFetchTool,
)
from omicsclaw.tools._html import DEFAULT_MAX_CHARS, HARD_MAX_CHARS, MAX_BODY_BYTES
from omicsclaw.tools._websafety import (
    HttpResponse,
    TransportFailed,
    UrlAddressBlocked,
    UrlMalformed,
)
from omicsclaw.tools.builtin.bash import ENGINE_TIMEOUT_MARGIN
from omicsclaw.tools.builtin.web_fetch import (
    FETCH_SCHEMA,
    FETCH_TIMEOUT,
    TOOL_NAME,
    render,
)
from omicsclaw.tools.context import use_tool_context
from omicsclaw.tools.function_tool import ToolArgumentError

_T = TypeVar("_T")

_DEADLINE = 10.0

_HTML = (
    b"<html><head><title>Doc</title></head><body><nav>menu</nav>"
    b"<h1>Heading</h1><p>The body.</p></body></html>"
)


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


def _no(reason: str = "not this time"):
    def channel(request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=False, reason=reason)

    return channel


class _FakeTransport:
    """Records every request and answers from a queue.

    A tool-level double, so it sits *outside* the safety gate on purpose:
    the gate has its own adversarial suite, and driving it from here would
    make every rendering test depend on a fake resolver.
    """

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


def _response(status: int = 200, **kwargs: Any) -> HttpResponse:
    fields: dict[str, Any] = {
        "status": status,
        "reason": "OK",
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": _HTML,
        "url": "https://example.org/p",
    }
    fields.update(kwargs)
    return HttpResponse(**fields)


def _fetch(transport: _FakeTransport, *, approve=None, **kwargs: Any) -> str:
    tool = WebFetchTool(transport=transport)
    with use_tool_context(approval=approve if approve is not None else _yes()):
        return _run(tool.execute(_args(**kwargs)))


# ---- the ordinary job ----------------------------------------------------


def test_a_page_comes_back_as_markdown_with_its_source_named():
    transport = _FakeTransport(_response())

    output = _fetch(transport, url="https://example.org/p")

    assert "# Doc" in output
    assert "> Source: https://example.org/p" in output
    assert "# Heading" in output and "The body." in output
    assert "menu" not in output


def test_the_request_is_a_get_with_the_tools_own_budget():
    transport = _FakeTransport(_response())

    _fetch(transport, url="https://example.org/p")

    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://example.org/p"
    assert call["timeout"] == FETCH_TIMEOUT
    assert call["max_bytes"] == MAX_BODY_BYTES
    assert "text/html" in call["headers"]["Accept"]


def test_plain_text_is_returned_as_it_arrived():
    transport = _FakeTransport(
        _response(
            headers={"Content-Type": "text/plain"},
            body=b"User-agent: *\nDisallow: /private\n",
        )
    )

    output = _fetch(transport, url="https://example.org/robots.txt")

    assert output == "User-agent: *\nDisallow: /private\n"
    assert "Source:" not in output


def test_json_is_read_as_text_rather_than_refused():
    transport = _FakeTransport(
        _response(headers={"Content-Type": "application/json"}, body=b'{"a": 1}')
    )

    assert _fetch(transport, url="https://example.org/api") == '{"a": 1}'


def test_a_binary_content_type_says_what_to_do_instead():
    transport = _FakeTransport(
        _response(headers={"Content-Type": "application/pdf"}, body=b"%PDF-1.7")
    )

    output = _fetch(transport, url="https://example.org/paper.pdf")

    assert "application/pdf" in output
    assert "bash" in output


def test_a_missing_content_type_is_reported_as_unset_rather_than_crashing():
    transport = _FakeTransport(_response(headers={}, body=b"bytes"))

    assert "unset" in _fetch(transport, url="https://example.org/x")


# ---- decoding -----------------------------------------------------------


def test_the_servers_charset_is_honoured():
    body = "héllo".encode("latin-1")
    transport = _FakeTransport(
        _response(headers={"Content-Type": "text/plain; charset=iso-8859-1"}, body=body)
    )

    assert _fetch(transport, url="https://example.org/x") == "héllo"


def test_a_quoted_or_misspelled_charset_still_decodes():
    transport = _FakeTransport(
        _response(headers={"Content-Type": 'text/plain; charset="utf8"'}, body=b"ok"),
        _response(
            headers={"Content-Type": "text/plain; charset=totally-made-up"},
            body=b"ok",
        ),
    )
    tool = WebFetchTool(transport=transport)

    with use_tool_context(approval=_yes()):
        first = _run(tool.execute(_args(url="https://example.org/a")))
        second = _run(tool.execute(_args(url="https://example.org/b")))

    assert first == "ok" and second == "ok"


def test_an_undecodable_byte_is_replaced_rather_than_failing():
    """Lenient here and strict in ``edit_file``: this only displays the
    bytes, while an edit would write a replacement character over real
    data."""
    transport = _FakeTransport(
        _response(headers={"Content-Type": "text/plain"}, body=b"ok \xff end")
    )

    output = _fetch(transport, url="https://example.org/x")

    assert "ok" in output and "end" in output


# ---- ceilings -----------------------------------------------------------


def test_max_chars_is_clamped_rather_than_refused():
    """A refusal costs a turn; a clamp plus a truncation notice says the
    same thing and still answers the question."""
    long_text = ("z" * 200 + "\n") * 400
    transport = _FakeTransport(
        _response(headers={"Content-Type": "text/plain"}, body=long_text.encode())
    )

    output = _fetch(
        transport, url="https://example.org/x", max_chars=HARD_MAX_CHARS * 5
    )

    assert "Truncated" in output
    assert len(output) < HARD_MAX_CHARS + 500


def test_a_body_cut_off_at_the_byte_ceiling_says_so_and_still_returns_text():
    """**A deliberate improvement on the reference**, which refuses a page
    over 1 MiB outright (``web_content.go:38-40``) and returns nothing.
    Partial text with a notice is more use than an error."""
    transport = _FakeTransport(_response(truncated=True))

    output = _fetch(transport, url="https://example.org/p")

    assert "# Heading" in output
    assert "cut off" in output


def test_the_default_ceiling_applies_when_nothing_is_asked():
    long_text = "y" * (DEFAULT_MAX_CHARS + 1_000)
    transport = _FakeTransport(
        _response(headers={"Content-Type": "text/plain"}, body=long_text.encode())
    )

    output = _fetch(transport, url="https://example.org/x")

    assert f"first {DEFAULT_MAX_CHARS} characters" in output


# ---- world failure is not tool failure ----------------------------------


def test_an_http_error_status_is_returned_as_text_not_as_a_failure():
    """Plan 0028 §11 debt #16 names HTTP 404 as the example. The model's
    next move is a different URL; after "tool failed" it is to doubt the
    tool."""
    registry = ToolRegistry()
    registry.register(
        WebFetchTool(
            transport=_FakeTransport(
                _response(404, reason="Not Found", headers={}, body=b"")
            )
        ),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    result = _run(
        registry.execute(
            ToolCall(
                id="1", name=TOOL_NAME, arguments=_args(url="https://example.org/gone")
            )
        )
    )

    assert result.is_error is False
    assert "HTTP 404 Not Found" in result.output
    assert "not a tool failure" in result.output


def test_a_refused_url_is_an_error_the_model_can_correct(tmp_path):
    """The paired other half of the criterion: a malformed URL *is*
    answered by sending different arguments, so it is ``is_error=True``."""
    registry = ToolRegistry()
    registry.register(
        WebFetchTool(transport=_FakeTransport()),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    result = _run(
        registry.execute(
            ToolCall(id="1", name=TOOL_NAME, arguments=_args(url="file:///etc/passwd"))
        )
    )

    assert result.is_error is True
    assert "http" in result.output


def test_the_render_branches_can_be_exercised_without_a_tool():
    """``render`` is pure, which is what lets each status class be pinned
    without a transport, an approval channel or an event loop."""
    assert "HTTP 500" in render(_response(500, reason="Server Error"), 0)
    assert "# Heading" in render(_response(), 0)
    # A 3xx that arrives here was not followed — no ``Location`` — and is
    # reported as the server's answer rather than silently rendered.
    assert "HTTP 302" in render(_response(302, reason="Found"), 0)
    # 204 is a success, so the (unusual) body is rendered rather than
    # turned into a status line.
    assert "# Heading" in render(_response(204, reason="No Content"), 0)


# ---- approval: the gate, and the order of operations --------------------


def test_nothing_is_requested_until_the_approval_is_given():
    transport = _FakeTransport(_response())

    with pytest.raises(ApprovalDenied):
        _fetch(transport, approve=_no(), url="https://example.org/p")

    assert transport.calls == []


def test_with_no_channel_bound_the_fetch_fails_closed():
    """The absence of an approval channel is not consent."""
    transport = _FakeTransport(_response())
    tool = WebFetchTool(transport=transport)

    with pytest.raises(ApprovalUnavailable):
        with use_tool_context():
            _run(tool.execute(_args(url="https://example.org/p")))

    assert transport.calls == []


def test_a_malformed_url_is_refused_without_asking_anybody():
    """Asking a human to approve a URL that was never going to parse is
    the friction that teaches people to approve without reading."""
    transport = _FakeTransport()
    seen: list[ApprovalRequest] = []

    with pytest.raises(UrlMalformed):
        _fetch(transport, approve=_yes(seen), url="gopher://127.0.0.1:6379/_x")

    assert seen == []
    assert transport.calls == []


def test_the_prompt_shows_the_whole_url_and_says_it_leaves_the_machine():
    """The risk is not that ``example.org`` is contacted, it is what is
    said to it — so the query string must be visible, unabbreviated."""
    transport = _FakeTransport(_response())
    seen: list[ApprovalRequest] = []
    url = "https://example.org/lookup?variant=BRCA1%3Ac.68_69delAG&id=P12345"

    _fetch(transport, approve=_yes(seen), url=url)

    assert url in seen[0].reason
    assert "leaves this machine" in seen[0].reason
    assert seen[0].risk_level is RiskLevel.HIGH
    assert seen[0].approval_mode is ApprovalMode.ASK


def test_the_prompt_carries_the_bytes_the_model_sent():
    """Why this tool is hand-written rather than a ``FunctionTool``:
    percent-encoding, a stray space and a homoglyph in a hostname are all
    things a person is looking *at*, and a decode-then-re-encode loses
    them."""
    payload = '{"max_chars": 500,  "url":"https://example.org/p"}'
    seen: list[ApprovalRequest] = []
    tool = WebFetchTool(transport=_FakeTransport(_response()))

    with use_tool_context(approval=_yes(seen)):
        _run(tool.execute(payload))

    assert seen[0].arguments == payload


def test_progress_is_reported_and_a_missing_sink_is_not_a_failure():
    updates: list[ProgressUpdate] = []
    tool = WebFetchTool(transport=_FakeTransport(_response(), _response()))

    with use_tool_context(approval=_yes(), progress=updates.append):
        _run(tool.execute(_args(url="https://example.org/p")))
    with use_tool_context(approval=_yes()):
        _run(tool.execute(_args(url="https://example.org/p")))

    assert any(update.tool_name == TOOL_NAME for update in updates)


def test_a_cancelled_turn_is_not_reported_to_the_model_as_a_failure():
    """Plan 0029 trap 5: the engine's deadline arrives as
    :exc:`asyncio.CancelledError` and must not become an Observation."""
    transport = _FakeTransport(_response())
    tool = WebFetchTool(transport=transport)

    async def cancelling(request: ApprovalRequest) -> ApprovalDecision:
        raise asyncio.CancelledError

    async def main() -> None:
        with use_tool_context(approval=cancelling):
            await tool.execute(_args(url="https://example.org/p"))

    with pytest.raises(asyncio.CancelledError):
        _run(main())

    assert transport.calls == []


# ---- the timeout coupling this layer cannot see -------------------------


def test_the_fetch_budget_fits_inside_the_engines_per_tool_deadline():
    """The coupling ``bash`` pays for in full and this tool inherits.

    ``EngineConfig.tool_timeout`` wraps the whole call, approval
    included, and ``omicsclaw/tools/`` may not import the engine — so this
    arithmetic is asserted here or nowhere. **No overrides are passed**,
    which is the point: a test that picked convenient numbers would stay
    green after somebody lowered the engine default.
    """
    assert FETCH_TIMEOUT == 15.0  # web_fetch.go:20
    assert FETCH_TIMEOUT + ENGINE_TIMEOUT_MARGIN <= EngineConfig().tool_timeout
    assert WebFetchTool().timeout == FETCH_TIMEOUT


# ---- the definition a model is shown ------------------------------------


def test_the_tool_satisfies_the_protocol_and_agrees_with_its_own_name():
    tool = WebFetchTool()

    assert isinstance(tool, Tool)
    assert tool.name == TOOL_NAME == tool.definition().name == "web_fetch"


def test_the_definition_is_stable_and_not_shared_between_instances():
    first, second = WebFetchTool(), WebFetchTool()

    assert first.definition() is first.definition()
    first.definition().input_schema["properties"].pop("url")
    assert "url" in second.definition().input_schema["properties"]
    assert "url" in FETCH_SCHEMA["properties"]


def test_the_description_warns_that_the_url_is_transmitted():
    """``SAFETY_RULES`` rule 1 made visible where the model decides."""
    description = WebFetchTool().definition().description

    assert "EVERYTHING IN THE URL IS SENT" in description
    assert "metadata" in description
    assert str(DEFAULT_MAX_CHARS) in description


def test_the_policy_declares_network_egress_and_asks():
    policy = WebFetchTool.policy

    assert policy.risk_level is RiskLevel.HIGH
    assert policy.approval_mode is ApprovalMode.ASK
    assert policy.touches_network is True
    assert policy.read_only is False
    assert policy.allowed_in_background is False
    assert policy.concurrency_safe is True


def test_no_policy_field_name_reaches_the_prompt():
    definition = WebFetchTool().definition()
    rendered = json.dumps(
        {"description": definition.description, "schema": definition.input_schema}
    )

    for field in ("risk_level", "approval_mode", "touches_network", "read_only"):
        assert field not in rendered


def test_a_payload_that_is_not_this_tools_shape_is_correctable():
    tool = WebFetchTool(transport=_FakeTransport())

    with use_tool_context(approval=_yes()):
        with pytest.raises(ToolArgumentError) as missing:
            _run(tool.execute("{}"))
        with pytest.raises(ToolArgumentError) as extra:
            _run(tool.execute(_args(url="https://example.org/", follow=True)))

    assert "url" in str(missing.value)
    assert "follow" in str(extra.value)


# ---- repairs from the independent audit ---------------------------------


class _FailingTransport:
    """A transport whose network is broken, which is the common case."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure

    async def request(self, method, url, **kwargs):
        raise self.failure


def test_a_network_failure_is_reported_as_the_world_failing_not_the_tool():
    """Plan 0029 Q6 and ``web_fetch.go:112-114``: a connection refused, a
    TLS failure or a timeout is a fact about the world, and there are no
    arguments the model can change to mend a network. Reported as
    ``is_error=True`` it would send the model to fix the tool."""
    registry = ToolRegistry()
    registry.register(
        WebFetchTool(
            transport=_FailingTransport(
                TransportFailed("could not reach https://example.org/p: reset")
            )
        ),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    call = ToolCall(
        id="1", name=TOOL_NAME, arguments=_args(url="https://example.org/p")
    )
    result = _run(registry.execute(call))

    assert result.is_error is False
    assert "network failure rather than a tool failure" in result.output
    assert "reset" in result.output


def test_a_refused_url_is_still_an_error_the_model_can_correct():
    """The paired control, so the two are not collapsed: a blocked URL *is*
    answered by sending a different one."""
    registry = ToolRegistry()
    registry.register(
        WebFetchTool(
            transport=_FailingTransport(
                UrlAddressBlocked("127.0.0.1 is in 127.0.0.0/8")
            )
        ),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    call = ToolCall(
        id="1", name=TOOL_NAME, arguments=_args(url="https://example.org/p")
    )
    result = _run(registry.execute(call))

    assert result.is_error is True
