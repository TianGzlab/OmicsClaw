"""Adversarial tests for ``omicsclaw.tools._websafety``.

This is the network's ``test_workspace.py``, and it is written to plan
0029 §10-9's rule, which was set for the filesystem boundary and applies
here word for word: **a test suite that only asserts "the bad URL was
refused" passes against an implementation that refuses everything.** So
every class of refusal below is paired with a legitimate URL that must
still go through.

Three properties get more attention than the rest, because each is a
place where an implementation can look right and be wrong:

**Every resolved address is checked, not the first.** A name with one
public ``A`` record and one ``127.0.0.1`` is a DNS-rebinding attack that
needs no timing at all, and "check the address we are about to use" is
the natural implementation that permits it.

**The socket goes to the address that was checked.** harness9 validates
the resolved addresses and then hands the *hostname* to ``http.Client``,
which resolves it again — so a one-second TTL is enough to make the check
describe a different connection from the one that happens. The test that
matters here records what :func:`socket.create_connection` was actually
asked for.

**A redirect is a new request.** Every hop is re-gated, which is the only
reason a public URL answering ``302 Location:
http://169.254.169.254/`` is not a bypass.

**The layering rule does not apply to this file**, for the reason the
other tool tests record.
"""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import time
from typing import Any, Coroutine, Mapping, TypeVar

import pytest

from omicsclaw.tools import _websafety
from omicsclaw.tools._websafety import (
    ALLOWED_SCHEMES,
    BLOCKED_NETWORKS,
    MAX_REDIRECTS,
    USER_AGENT,
    HttpResponse,
    PinnedTransport,
    SafeTarget,
    Transport,
    UrlAddressBlocked,
    UrlMalformed,
    UrlNotResolvable,
    UrlRefused,
    blocked_reason,
    check_url,
    header,
    inspect_url,
    safe_target,
)

_T = TypeVar("_T")

_DEADLINE = 10.0

_PUBLIC = "93.184.216.34"


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; the suite drives this way."""
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


def _resolver(**names: list[tuple[int, str]]):
    """A DNS stand-in. **It cannot make a blocked address acceptable.**

    That is the difference between this seam and harness9's, which makes
    the whole of ``isSafeURL`` replaceable so its own tests can reach a
    local server (``web_fetch.go:27-28``). A safety check with an off
    switch is not a safety check, so what is injected here is the
    *resolver* — a test can point a name anywhere and watch the verdict,
    and the verdict is the real one.
    """

    def resolve(host: str, port: int) -> list[tuple[int, str]]:
        try:
            return names[host.replace(".", "_").replace("-", "_")]
        except KeyError as exc:
            raise socket.gaierror(-2, "Name or service not known") from exc

    return resolve


_ONE_PUBLIC = _resolver(example_org=[(socket.AF_INET, _PUBLIC)])


def _responder(*responses: HttpResponse):
    """An opener that hands back canned responses and records the targets.

    It is given an **already-validated** :class:`SafeTarget`, so a test
    using it exercises the real gate and the real redirect loop without a
    network — the second seam described in ``_websafety.py``'s docstring.
    """
    seen: list[tuple[SafeTarget, str, Mapping[str, str], bytes | None]] = []
    queue = list(responses)

    async def opener(
        target: SafeTarget,
        method: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: float,
        max_bytes: int,
    ) -> HttpResponse:
        seen.append((target, method, dict(headers), body))
        return queue.pop(0)

    opener.seen = seen  # type: ignore[attr-defined]
    return opener


def _response(status: int = 200, **kwargs: Any) -> HttpResponse:
    fields: dict[str, Any] = {
        "status": status,
        "reason": "OK",
        "headers": {},
        "body": b"hi",
        "url": "https://example.org/",
    }
    fields.update(kwargs)
    return HttpResponse(**fields)


# ---- the offline half: scheme, userinfo, host, port --------------------


def test_http_and_https_are_the_allow_list_and_both_work():
    """The paired positive control for every scheme refusal below."""
    assert ALLOWED_SCHEMES == frozenset({"http", "https"})
    assert inspect_url("http://example.org/a").port == 80
    assert inspect_url("https://example.org/a").port == 443
    assert inspect_url("https://example.org:8443/a").port == 8443


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_SET%20x%20y",
        "ftp://example.org/f",
        "data:text/html,<script>x</script>",
        "javascript:alert(1)",
        "http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/json",
        "example.org/page",
        "//example.org/page",
        "",
        "   ",
    ],
)
def test_anything_that_is_not_http_or_https_is_refused(url):
    """An allow-list, because a blocklist of schemes is a list of the ones
    somebody thought of. The three worth naming are in the parameters:
    ``file`` walks past ``_workspace.py``, ``gopher`` is a protocol
    smuggling primitive that can drive Redis, and ``http+unix`` is a
    Docker socket."""
    with pytest.raises(UrlMalformed):
        inspect_url(url)


def test_a_url_carrying_credentials_is_refused_whichever_form_it_takes():
    """``web_safety.go:52-54``. The reason is not tidiness: parsers
    disagree about which host ``https://expected.com@evil.com/`` names,
    and the disagreement is the exploit."""
    for url in (
        "https://user:pass@example.org/",
        "https://user@example.org/",
        "https://expected.com@evil.com/",
    ):
        with pytest.raises(UrlMalformed) as refusal:
            inspect_url(url)
        assert "credentials" in str(refusal.value)

    # And the same host without the userinfo is fine, so the refusal is
    # about the credentials rather than about the host.
    assert inspect_url("https://example.org/").host == "example.org"


def test_a_url_with_no_host_or_an_unusable_port_is_refused():
    with pytest.raises(UrlMalformed) as no_host:
        inspect_url("http:///just/a/path")
    with pytest.raises(UrlMalformed) as bad_port:
        inspect_url("http://example.org:99999/")

    assert "names no host" in str(no_host.value)
    assert "unusable port" in str(bad_port.value)


def test_the_host_is_lower_cased_and_the_url_is_returned_unmodified():
    """The URL a model sent is what is reported back to it; only the host
    is normalised, because DNS is case-insensitive and a blocklist
    comparison must not be."""
    shape = inspect_url("HTTPS://Example.ORG/Path?Q=1")

    assert shape.host == "example.org"
    assert shape.url == "HTTPS://Example.ORG/Path?Q=1"


# ---- the blocklist ------------------------------------------------------


def test_the_reference_ranges_are_all_present_and_named():
    """Plan 0029 §10-8: every literal carried over is asserted somewhere
    that names it, because every other test compares against the tuple
    and would follow it if a line were deleted."""
    reference = {
        "169.254.0.0/16",
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "fe80::/10",
        "fc00::/7",
    }
    present = {str(network) for network in BLOCKED_NETWORKS}

    assert reference <= present, "a range from web_safety.go:19-28 is gone"


def test_the_additions_beyond_the_reference_are_present_and_named():
    """Each of these closes something the reference leaves reachable; the
    argument for each is in :data:`BLOCKED_NETWORKS`' docstring."""
    present = {str(network) for network in BLOCKED_NETWORKS}

    assert {"0.0.0.0/8", "224.0.0.0/4", "240.0.0.0/4"} <= present
    assert {"::1/128", "::/128", "64:ff9b::/96"} <= present


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",
        "169.254.0.1",
        "127.0.0.1",
        "127.0.0.2",
        "10.1.2.3",
        "172.16.5.5",
        "172.31.255.255",
        "192.168.1.1",
        "100.64.0.1",
        "0.0.0.0",
        "0.1.2.3",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fd00::1",
        "64:ff9b::7f00:1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
    ],
)
def test_every_dangerous_address_is_refused(address):
    assert blocked_reason(address) is not None


@pytest.mark.parametrize(
    "address",
    [
        "93.184.216.34",
        "8.8.8.8",
        "1.1.1.1",
        "172.32.0.1",
        "172.15.255.255",
        "11.0.0.1",
        "2606:4700:4700::1111",
        "2001:4860:4860::8888",
    ],
)
def test_ordinary_public_addresses_are_allowed(address):
    """The paired positive control, and the two ``172`` entries are the
    point of it: ``172.16.0.0/12`` ends at ``172.31.255.255``, so an
    implementation that blocked ``172.0.0.0/8`` would pass every refusal
    test above and fail here."""
    assert blocked_reason(address) is None


def test_an_ipv4_mapped_address_is_unwrapped_before_it_is_judged():
    """``web_safety.go:68-71`` does this by hand with ``To4()``.
    ``::ffff:169.254.169.254`` is the metadata endpoint spelled as IPv6,
    and a list without an ``::ffff:0:0/96`` line only covers it because
    of this normalisation."""
    reason = blocked_reason("::ffff:169.254.169.254")

    assert reason is not None
    assert "169.254.169.254" in reason
    assert "169.254.0.0/16" in reason


def test_an_unparseable_address_is_refused_rather_than_skipped():
    """**A deliberate deviation**, in the fail-closed direction.
    ``web_safety.go:64-66`` ``continue``s past an address it cannot parse,
    reasoning that a resolver produced it. Fail-closed is the rule
    everywhere else in this gate, and an answer neither the caller nor
    :mod:`ipaddress` can account for is not the case to make an exception
    for."""
    assert blocked_reason("not-an-address") is not None
    assert blocked_reason("") is not None


def test_an_ipv6_range_does_not_capture_an_ipv4_address_or_the_reverse():
    """The version guard. Without it, :mod:`ipaddress` raises ``TypeError``
    on a mixed comparison rather than answering, and an implementation
    that caught it broadly would answer "allowed"."""
    assert blocked_reason("93.184.216.34") is None
    assert blocked_reason("2606:4700::1") is None
    assert len({network.version for network in BLOCKED_NETWORKS}) == 2


# ---- DNS: fail-closed, and every answer checked ------------------------


def test_a_name_that_does_not_resolve_is_refused_not_assumed():
    """``web_safety.go:57-61``. A destination that cannot be resolved
    cannot be checked, and the alternative to refusing is guessing."""
    with pytest.raises(UrlNotResolvable) as refusal:
        check_url("https://nowhere.invalid/x", resolver=_ONE_PUBLIC)

    assert "could not be resolved" in str(refusal.value)
    # Paired control: the resolver works for the name it knows.
    assert check_url("https://example.org/x", resolver=_ONE_PUBLIC).address == _PUBLIC


def test_a_name_that_resolves_to_nothing_at_all_is_refused():
    with pytest.raises(UrlNotResolvable):
        check_url("https://example.org/x", resolver=_resolver(example_org=[]))


def test_every_resolved_address_is_checked_and_not_merely_the_first():
    """The rebinding attack that needs no timing. ``web_safety.go:63``
    iterates for this reason, and the plausible wrong implementation —
    check the one address we are going to use — permits it.

    **Both orders are tested**, because checking only ``answers[0]`` would
    pass the first of these and fail the second.
    """
    public_first = _resolver(
        rebind_test=[(socket.AF_INET, _PUBLIC), (socket.AF_INET, "127.0.0.1")]
    )
    loopback_first = _resolver(
        rebind_test=[(socket.AF_INET, "127.0.0.1"), (socket.AF_INET, _PUBLIC)]
    )

    for resolver in (public_first, loopback_first):
        with pytest.raises(UrlAddressBlocked):
            check_url("https://rebind.test/x", resolver=resolver)


def test_a_dual_stack_name_is_refused_for_its_ipv6_answer_alone():
    """A host that blocks only IPv4 is not blocked. ``AF_UNSPEC`` in
    :func:`socket.getaddrinfo` is what makes both families visible."""
    resolver = _resolver(
        dual_test=[(socket.AF_INET, _PUBLIC), (socket.AF_INET6, "::1")]
    )

    with pytest.raises(UrlAddressBlocked):
        check_url("https://dual.test/x", resolver=resolver)


def test_an_ip_literal_in_the_url_is_checked_like_any_other_host():
    """There is no "the model gave us an address, so it meant it" path."""
    literal = _resolver()

    def resolve(host: str, port: int) -> list[tuple[int, str]]:
        return [(socket.AF_INET, host)]

    with pytest.raises(UrlAddressBlocked):
        check_url("http://169.254.169.254/latest/meta-data/", resolver=resolve)
    with pytest.raises(UrlAddressBlocked):
        check_url("http://127.0.0.1:8000/admin", resolver=resolve)
    assert literal is not None  # keep the unused factory honest


def test_the_target_carries_the_address_that_was_validated():
    """Why :class:`SafeTarget` is not a boolean: a gate that answers "yes"
    and lets the caller resolve the name again has verified a different
    connection from the one that happens."""
    target = check_url("https://example.org/a?b=1", resolver=_ONE_PUBLIC)

    assert target.address == _PUBLIC
    assert target.host == "example.org"
    assert target.port == 443
    assert target.scheme == "https"
    assert target.url == "https://example.org/a?b=1"


def test_the_gate_runs_off_the_event_loop():
    """DNS is blocking and can take seconds; :func:`safe_target` is how a
    tool reaches it without stalling the loop."""
    target = _run(safe_target("https://example.org/", resolver=_ONE_PUBLIC))

    assert target.address == _PUBLIC


# ---- the pinning, which is the part the reference does not have --------


def test_the_socket_is_opened_to_the_validated_address_not_the_hostname(
    monkeypatch,
):
    """**The test that proves the pinning is real.**

    Without it, every other test here passes against an implementation
    that validates the addresses and then hands the hostname to a client
    that resolves it again — which is exactly what harness9 does, and
    what one DNS record with a short TTL defeats.
    """
    asked: list[tuple[str, int]] = []

    def fake_connect(address, timeout=None, source_address=None):
        asked.append(address)
        raise OSError("no network in this environment, and none needed")

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    target = check_url("https://example.org/page", resolver=_ONE_PUBLIC)
    connection = _websafety._connection(target, 5.0)

    with pytest.raises(OSError):
        connection.connect()

    assert asked == [(_PUBLIC, 443)]


def test_the_hostname_survives_for_the_host_header_and_for_tls():
    """Constructing with ``host=<ip>`` would be simpler and wrong twice
    over: the ``Host`` header would name the address, breaking every
    virtual host, and TLS would verify the certificate against an IP."""
    target = check_url("https://example.org/page", resolver=_ONE_PUBLIC)

    connection = _websafety._connection(target, 5.0)

    assert connection.host == "example.org"
    assert connection.port == 443
    assert isinstance(connection, http.client.HTTPSConnection)


def test_a_python_that_stopped_holding_the_connector_per_instance_fails_loudly(
    monkeypatch,
):
    """The one that must not fail silently.

    If ``_create_connection`` stops being an instance attribute, the
    assignment becomes a no-op and the client resolves the name itself —
    the reference's weakness reintroduced without anybody editing a line
    about safety. So the absence is checked and raises.
    """

    class Unpinnable:
        def __init__(self, host, port=None, **kwargs):
            self.host = host
            self.port = port

    monkeypatch.setattr(http.client, "HTTPSConnection", Unpinnable)
    target = check_url("https://example.org/page", resolver=_ONE_PUBLIC)

    with pytest.raises(RuntimeError) as refusal:
        _websafety._connection(target, 5.0)

    assert "could not be pinned" in str(refusal.value)


# ---- redirects: every hop is a new request -----------------------------


def test_a_redirect_to_a_blocked_address_is_refused_at_the_hop():
    """``web_fetch.go:37-45``'s ``CheckRedirect``, and the reason the loop
    is not :mod:`urllib`'s: it would follow this before anyone could look
    at it."""
    resolver = _resolver(
        example_org=[(socket.AF_INET, _PUBLIC)],
        metadata_test=[(socket.AF_INET, "169.254.169.254")],
    )
    opener = _responder(
        _response(302, headers={"Location": "http://metadata.test/latest/"})
    )
    transport = PinnedTransport(resolver=resolver, opener=opener)

    with pytest.raises(UrlAddressBlocked):
        _run(transport.request("GET", "https://example.org/start"))


def test_a_safe_redirect_is_followed_and_the_final_response_returned():
    """The paired positive control for the refusal above."""
    resolver = _resolver(
        example_org=[(socket.AF_INET, _PUBLIC)],
        other_test=[(socket.AF_INET, "8.8.8.8")],
    )
    opener = _responder(
        _response(301, headers={"Location": "https://other.test/final"}),
        _response(200, body=b"arrived", url="https://other.test/final"),
    )
    transport = PinnedTransport(resolver=resolver, opener=opener)

    response = _run(transport.request("GET", "https://example.org/start"))

    assert response.body == b"arrived"
    assert [target.url for target, *_ in opener.seen] == [
        "https://example.org/start",
        "https://other.test/final",
    ]


def test_a_relative_location_is_resolved_against_the_current_url():
    resolver = _ONE_PUBLIC
    opener = _responder(
        _response(302, headers={"Location": "/moved/here"}),
        _response(200, body=b"ok"),
    )
    transport = PinnedTransport(resolver=resolver, opener=opener)

    _run(transport.request("GET", "https://example.org/a/b"))

    assert opener.seen[1][0].url == "https://example.org/moved/here"


def test_a_chain_longer_than_the_budget_is_abandoned():
    resolver = _ONE_PUBLIC
    opener = _responder(
        *[
            _response(302, headers={"Location": f"https://example.org/{hop}"})
            for hop in range(MAX_REDIRECTS + 1)
        ]
    )
    transport = PinnedTransport(resolver=resolver, opener=opener)

    with pytest.raises(UrlRefused) as refusal:
        _run(transport.request("GET", "https://example.org/start"))

    assert f"more than {MAX_REDIRECTS} times" in str(refusal.value)
    assert len(opener.seen) == MAX_REDIRECTS + 1


def test_a_post_becomes_a_get_across_a_302_and_the_body_is_dropped():
    """What every browser does, and the reason is not compatibility: a
    POST body re-sent to a host the model never named is a request it
    never made."""
    opener = _responder(
        _response(302, headers={"Location": "https://example.org/after"}),
        _response(200, body=b"ok"),
    )
    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=opener)

    _run(transport.request("POST", "https://example.org/form", body=b"q=secret"))

    assert opener.seen[0][1] == "POST" and opener.seen[0][3] == b"q=secret"
    assert opener.seen[1][1] == "GET" and opener.seen[1][3] is None


def test_a_307_preserves_the_method_and_the_body():
    """The status that exists precisely to mean "repeat it exactly"."""
    opener = _responder(
        _response(307, headers={"Location": "https://example.org/after"}),
        _response(200, body=b"ok"),
    )
    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=opener)

    _run(transport.request("POST", "https://example.org/form", body=b"q=1"))

    assert opener.seen[1][1] == "POST" and opener.seen[1][3] == b"q=1"


def test_a_304_is_not_a_redirect_and_is_returned_as_it_stands():
    """``304 Not Modified`` and ``305 Use Proxy`` are in the 3xx range and
    are not redirects to follow; a ``300 <= status < 400`` test would
    follow both, and a 304 carrying a stale ``Location`` would send the
    request somewhere nobody asked."""
    opener = _responder(
        _response(304, headers={"Location": "https://example.org/elsewhere"})
    )
    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=opener)

    response = _run(transport.request("GET", "https://example.org/a"))

    assert response.status == 304
    assert len(opener.seen) == 1


def test_a_redirect_without_a_location_is_not_followed():
    opener = _responder(_response(302, headers={}))
    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=opener)

    assert _run(transport.request("GET", "https://example.org/a")).status == 302


# ---- the small pieces ---------------------------------------------------


def test_the_user_agent_is_this_project_and_not_the_reference():
    """Plan 0027's lesson in its smallest form: a borrowed string that
    happens to compile is not a borrowed behaviour. Identifying this
    client as another project's harness would misattribute every request
    in somebody's access log."""
    assert USER_AGENT.startswith("OmicsClaw/")
    assert "harness9" not in USER_AGENT


def test_the_user_agent_is_sent_and_a_caller_may_override_it():
    opener = _responder(_response(200), _response(200))
    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=opener)

    _run(transport.request("GET", "https://example.org/a"))
    _run(
        transport.request(
            "GET", "https://example.org/a", headers={"User-Agent": "Custom/9"}
        )
    )

    assert opener.seen[0][2]["User-Agent"] == USER_AGENT
    assert opener.seen[1][2]["User-Agent"] == "Custom/9"


def test_headers_are_read_case_insensitively():
    """Real servers exercise HTTP's case-insensitivity. A fake built with
    a lower-case key plus a ``headers["Location"]`` reader is a test that
    passes and a redirect that is not followed in production."""
    response = _response(302, headers={"LoCaTiOn": "https://example.org/x"})

    assert header(response, "location") == "https://example.org/x"
    assert header(response, "Location") == "https://example.org/x"
    assert header(response, "absent") == ""


def test_the_transport_is_a_structural_protocol():
    assert isinstance(PinnedTransport(), Transport)


def test_every_refusal_class_is_recognisable_as_a_refusal():
    """One base class for the model — the registry reports any of them as
    ``is_error=True`` — and distinct subclasses for the operator reading a
    log, where a blocked address and a typo must not share a heading."""
    for subclass in (UrlMalformed, UrlNotResolvable, UrlAddressBlocked):
        assert issubclass(subclass, UrlRefused)
    assert issubclass(UrlRefused, ValueError)


def test_the_blocklist_is_an_explicit_tuple_rather_than_a_property():
    """:attr:`ipaddress.IPv4Address.is_private` is close to this list and
    not equal to it — it excludes ``100.64.0.0/10`` and includes the
    documentation ranges — so a deployment auditing what is blocked would
    be reading the wrong list."""
    cgnat = ipaddress.ip_address("100.64.0.1")

    assert cgnat.is_private is False
    assert blocked_reason(str(cgnat)) is not None


# ---- repairs from the independent audit ---------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/a?q=x\ny",
        "http://example.org/a?q=x\ry",
        "http://example.org/a?q=x\ty",
        "http://example.org/a b",
        "http://example.org/a\x00b",
        "http://example.org/a\x7fb",
        "http://exam\nple.org/",
    ],
)
def test_a_url_carrying_a_space_or_control_character_is_refused(url):
    """The audit's most severe finding, and it is about the *prompt*.

    :func:`urllib.parse.urlsplit` silently strips ``\\t``, ``\\r`` and
    ``\\n`` **for parsing** while the raw string is what the human is
    shown. So ``?sample=\\nHG00123`` displays as an empty query string and
    an identifier on its own line that reads like prose, and sends
    ``?sample=HG00123`` on the wire — the approval prompt describing a
    different request from the one that happens, in the one tool whose
    entire safety argument is "a person reads the URL".
    """
    with pytest.raises(UrlMalformed) as refusal:
        inspect_url(url)

    assert "control characters" in str(refusal.value)


def test_an_ordinary_url_with_percent_encoding_still_passes():
    """The paired positive control: encoded whitespace is fine, since the
    refusal is about what a human would not see."""
    shape = inspect_url("https://example.org/a%20b?q=one%0Atwo")

    assert shape.host == "example.org"
    assert "%20" in shape.url


def test_a_cross_origin_307_that_would_resend_a_body_is_refused():
    """307 and 308 mean "repeat it exactly", and repeating it exactly at a
    host nobody approved is what this module exists to prevent. There is no
    honest downgrade, so the chain stops."""
    resolver = _resolver(
        example_org=[(socket.AF_INET, _PUBLIC)],
        attacker_example=[(socket.AF_INET, "8.8.8.8")],
    )
    opener = _responder(
        _response(307, headers={"Location": "https://attacker.example/collect"})
    )
    transport = PinnedTransport(resolver=resolver, opener=opener)

    with pytest.raises(UrlRefused) as refusal:
        _run(
            transport.request(
                "POST", "https://example.org/search", body=b"q=patient123"
            )
        )

    assert "re-send the request body" in str(refusal.value)
    assert len(opener.seen) == 1, "the second request was never made"


def test_a_same_origin_307_still_repeats_the_request_exactly():
    """The paired control: 307's whole purpose survives where it is safe."""
    opener = _responder(
        _response(307, headers={"Location": "https://example.org/after"}),
        _response(200, body=b"ok"),
    )
    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=opener)

    _run(transport.request("POST", "https://example.org/form", body=b"q=1"))

    assert opener.seen[1][1] == "POST" and opener.seen[1][3] == b"q=1"


def test_a_cross_origin_redirect_does_not_carry_the_callers_headers():
    """An API key, a cookie or a bearer token was attached for one host,
    and a redirect is a different host asking for it."""
    resolver = _resolver(
        example_org=[(socket.AF_INET, _PUBLIC)],
        other_test=[(socket.AF_INET, "8.8.8.8")],
    )
    opener = _responder(
        _response(302, headers={"Location": "https://other.test/final"}),
        _response(200, body=b"ok"),
    )
    transport = PinnedTransport(resolver=resolver, opener=opener)

    _run(
        transport.request(
            "GET",
            "https://example.org/start",
            headers={"X-Api-Key": "SECRET", "Cookie": "session=abc"},
        )
    )

    first, second = opener.seen[0][2], opener.seen[1][2]
    assert first["X-Api-Key"] == "SECRET"
    assert "X-Api-Key" not in second and "Cookie" not in second
    assert second["User-Agent"] == USER_AGENT


def test_a_same_origin_redirect_keeps_the_callers_headers():
    opener = _responder(
        _response(302, headers={"Location": "https://example.org/after"}),
        _response(200, body=b"ok"),
    )
    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=opener)

    _run(
        transport.request(
            "GET", "https://example.org/a", headers={"X-Api-Key": "SECRET"}
        )
    )

    assert opener.seen[1][2]["X-Api-Key"] == "SECRET"


def test_a_different_port_or_scheme_counts_as_crossing_the_origin():
    assert _websafety._origin("https://a.test/x") != _websafety._origin(
        "http://a.test/x"
    )
    assert _websafety._origin("https://a.test/x") != _websafety._origin(
        "https://a.test:8443/x"
    )
    assert _websafety._origin("https://a.test/x") == _websafety._origin(
        "https://A.TEST/y?z=1"
    )


def test_the_timeout_is_a_budget_for_the_whole_call_not_for_each_hop():
    """A per-hop budget multiplies by six behind a number the caller
    derived from the engine's per-tool deadline."""
    slept: list[float] = []

    async def slow(target, method, headers, body, timeout, max_bytes):
        slept.append(timeout)
        await asyncio.sleep(0.05)
        return _response(302, headers={"Location": "https://example.org/next"})

    transport = PinnedTransport(resolver=_ONE_PUBLIC, opener=slow)

    with pytest.raises(_websafety.TransportFailed) as failure:
        _run(transport.request("GET", "https://example.org/a", timeout=0.15))

    assert "did not finish within" in str(failure.value)
    assert slept == sorted(slept, reverse=True), "each hop got what was left"
    assert slept[-1] < slept[0]


def test_a_network_failure_is_a_transport_failure_and_not_a_refusal(monkeypatch):
    """A reset is a fact about the world; a refused URL is the model's to
    correct. Collapsing the two sends a model to fix its arguments when
    there is nothing wrong with them, or to doubt the tool."""

    def refuse(address, timeout=None, source_address=None):
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(socket, "create_connection", refuse)
    target = check_url("http://example.org/p", resolver=_ONE_PUBLIC)

    with pytest.raises(_websafety.TransportFailed) as failure:
        _websafety._open_blocking(target, "GET", {}, None, 5.0, 1024)

    assert "could not reach" in str(failure.value)
    assert not isinstance(failure.value, UrlRefused)


def test_the_connect_is_capped_at_the_dial_timeout(monkeypatch):
    """A black-holed address must not spend the request's whole budget on a
    handshake that was never going to complete."""
    asked: list[float | None] = []

    def record(address, timeout=None, source_address=None):
        asked.append(timeout)
        raise OSError("no network, and none needed")

    monkeypatch.setattr(socket, "create_connection", record)
    target = check_url("http://example.org/p", resolver=_ONE_PUBLIC)
    connector = _websafety._pinned_connector(target)

    with pytest.raises(OSError):
        connector(("example.org", 80), 45.0, None)
    with pytest.raises(OSError):
        connector(("example.org", 80), 2.0, None)

    assert asked == [_websafety.DIAL_TIMEOUT, 2.0]


def test_the_gate_really_leaves_the_event_loop(monkeypatch):
    """The property :func:`safe_target` exists for. Asserting the address
    came back tests :func:`check_url`, which would pass just as well if the
    lookup blocked the loop."""
    import threading

    seen: list[str] = []

    def resolve(host, port):
        seen.append(threading.current_thread().name)
        return [(socket.AF_INET, _PUBLIC)]

    async def main() -> str:
        await safe_target("https://example.org/", resolver=resolve)
        return threading.current_thread().name

    loop_thread = _run(main())

    assert seen and seen[0] != loop_thread


def test_the_system_resolver_asks_for_both_families_and_de_duplicates(
    monkeypatch,
):
    """A host that blocks only IPv4 is not blocked, and the thing that
    makes both families visible is ``AF_UNSPEC`` in this function — which
    every other test replaces with a fake."""
    calls: list[tuple] = []

    def fake_getaddrinfo(host, port, family, kind):
        calls.append((host, port, family, kind))
        return [
            (socket.AF_INET, kind, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, kind, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET6, kind, 6, "", ("2606:4700::1", port, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    answers = _websafety._system_resolver("example.org", 443)

    assert calls == [("example.org", 443, socket.AF_UNSPEC, socket.SOCK_STREAM)]
    assert answers == [
        (socket.AF_INET, "93.184.216.34"),
        (socket.AF_INET6, "2606:4700::1"),
    ]


def test_a_target_carries_no_address_family_it_never_reads():
    """Plan 0029 trap 15: a field stored and never used is dead state, and
    :func:`socket.create_connection` derives the family from the address."""
    target = check_url("https://example.org/", resolver=_ONE_PUBLIC)

    assert not hasattr(target, "family")


def test_the_two_remaining_borrowed_literals_are_pinned_by_name():
    """Every other borrowed constant has a test naming it; these two did
    not, so changing them left the suite green."""
    assert MAX_REDIRECTS == 5  # web_fetch.go:21
    assert _websafety.DIAL_TIMEOUT == 10.0  # web_search.go:25


# ---- the socket layer, against a real local server ----------------------


def _serve(body: bytes, *, drip: float = 0.0):
    """A one-shot HTTP server on loopback, and the thread running it.

    The gate would refuse ``127.0.0.1``, which is the point of it — so the
    :class:`SafeTarget` below is **constructed directly**. That is a
    transport-level test deliberately standing outside the gate, and it is
    the only way to exercise the socket path at all without a network.
    """
    import threading

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def run() -> None:
        connection, _ = listener.accept()
        try:
            connection.recv(65536)
            head = (
                b"HTTP/1.1 200 OK\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
            )
            connection.sendall(head)
            if drip:
                for index in range(len(body)):
                    time.sleep(drip)
                    connection.sendall(body[index : index + 1])
            else:
                connection.sendall(body)
        except OSError:
            pass
        finally:
            connection.close()
            listener.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return port, thread


def _local_target(port: int) -> SafeTarget:
    return SafeTarget(
        shape=_websafety.UrlShape(
            url=f"http://localhost:{port}/x",
            scheme="http",
            host="localhost",
            port=port,
        ),
        address="127.0.0.1",
    )


def test_a_body_past_the_ceiling_is_cut_and_the_socket_is_closed():
    """The byte ceiling is the only thing between a hostile server and
    unbounded memory, and it was previously asserted only against a
    hand-built response object."""
    port, thread = _serve(b"y" * 5_000)

    response = _websafety._open_blocking(_local_target(port), "GET", {}, None, 5.0, 100)
    thread.join(timeout=2.0)

    assert response.truncated is True
    assert response.body == b"y" * 100
    assert response.status == 200


def test_a_body_inside_the_ceiling_is_not_flagged_as_truncated():
    port, thread = _serve(b"y" * 50)

    response = _websafety._open_blocking(_local_target(port), "GET", {}, None, 5.0, 100)
    thread.join(timeout=2.0)

    assert response.truncated is False and response.body == b"y" * 50


def test_a_server_dripping_bytes_cannot_outlast_the_budget():
    """A socket deadline bounds one read and is reset by each; the sum is
    bounded only because the body is read against a monotonic deadline."""
    port, thread = _serve(b"z" * 40, drip=0.05)
    started = time.monotonic()

    with pytest.raises(_websafety.TransportFailed) as failure:
        _websafety._open_blocking(_local_target(port), "GET", {}, None, 0.3, 4096)

    elapsed = time.monotonic() - started
    thread.join(timeout=2.0)

    assert "time budget ran out" in str(failure.value)
    assert elapsed < 1.5, f"the deadline did not bound the read ({elapsed:.2f}s)"


def test_the_byte_ceiling_stops_an_endless_stream_rather_than_the_server():
    """The memory bound, pinned against a body that never ends.

    Every other test of it uses a server that stops on its own, so the
    ceiling and the server's own length agree and an implementation with
    no ceiling passes. This one would run forever without it.
    """

    class _Endless:
        def __init__(self) -> None:
            self.asked: list[int] = []

        def read1(self, size: int) -> bytes:
            self.asked.append(size)
            return b"x" * size

    class _NoSocket:
        sock = None

    raw = _Endless()

    payload, truncated = _websafety._read_bounded(
        _NoSocket(), raw, 100, time.monotonic() + 30.0, "http://x.test/"
    )

    assert truncated is True
    assert payload == b"x" * 100
    assert sum(raw.asked) <= 101, "more than the ceiling was pulled into memory"
