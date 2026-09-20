"""The network boundary, and the only way through it.

What ``_workspace.py`` is to the filesystem, this is to the network: a
gate every tool that opens a socket passes through, plus the transport
that is the only thing allowed to open one. Modelled on harness9's
``internal/tools/web_safety.go``.

**The class of bug it prevents is SSRF.** On any cloud instance
``http://169.254.169.254/latest/meta-data/iam/`` returns credentials to
whoever asks, and a model told to "check what this endpoint returns" will
ask. A URL prefix check does not prevent it; this repository's existing
``runtime/tools/builders/engineering.py`` ``web_fetch`` has only that, so
the metadata endpoint is reachable from it today.

**What this does NOT protect.** ``CLAUDE.md``'s first safety rule is that
genetic data never leaves this machine, and nothing here enforces it. A
blocklist of destinations cannot: ``https://example.com/?q=`` plus a
patient identifier is a perfectly public address. Data egress is governed
by the ``ASK`` policy on the tools themselves.

**Four checks, in order:** the scheme must be ``http`` or ``https``;
userinfo (``user:pass@host``) is refused because parsers disagree about
which host ``https://expected.com@evil.com/`` names; the host is
resolved, fail-closed on failure; and **every** resolved address is
checked against :data:`BLOCKED_NETWORKS`, not just the first — a name
with one public ``A`` record and one ``127.0.0.1`` is a rebinding attack
with no timing requirement.

**Then it pins, which the reference does not.** harness9 validates the
resolved addresses and hands the *hostname* to ``http.Client``, which
resolves it again, so one record with a short TTL makes the check
describe a different connection from the one that happens.
:class:`PinnedTransport` connects to the address it validated, carrying
the hostname only in the ``Host`` header and the TLS SNI, so certificate
verification is unaffected. Redirects are re-checked on every hop.

**The seams, and which of them is load-bearing.**
:class:`PinnedTransport` takes a ``resolver`` and an ``opener``.
``resolver`` **cannot weaken a check**: whatever address it returns is
itself judged, so a test can point a name at ``127.0.0.1`` and watch it
refused but cannot make ``127.0.0.1`` acceptable. ``opener`` is a
different matter and should not be described as if it were the same —
it is the thing that opens the socket, so an implementation that ignores
the :class:`SafeTarget` handed to it reaches wherever it likes. Like
``bash``'s ``BashEnvironment`` and like a tool's own ``transport``
argument, it sits **inside** the trust boundary: whoever assembles a
registry chooses where the syscalls land and owns that choice.

**A budget for the whole call, not per hop.** ``timeout`` on
:meth:`PinnedTransport.request` covers every redirect and every byte,
because a per-hop budget multiplies by six behind a number the caller
derived from the engine's per-tool deadline — and because a socket
timeout on its own bounds one read rather than their sum, so a server
dripping bytes just inside it holds the request open indefinitely.

**Network failure is not refusal.** A reset, a TLS error or the deadline
raises :exc:`TransportFailed`, which tools report as ordinary output;
only :exc:`UrlRefused` means "send different arguments".

**Leaf-adjacent.** The standard library only — no ``omicsclaw`` import at
all, not even ``schema``.
"""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urljoin, urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
"""The schemes a request may use. An allow-list, because a blocklist of
schemes is a list of the ones somebody thought of — ``file://`` walks
past the filesystem boundary, ``gopher://`` can drive Redis and SMTP, and
``http+unix://`` is a Docker socket.
"""

USER_AGENT = "OmicsClaw/1.0"
"""How this client identifies itself.

Deliberately **not** the reference's ``harness9/1.0``: identifying as
another project's harness would misattribute every request in somebody's
access log, and a site that blocks by user-agent would be answering a
question nobody asked.
"""

MAX_REDIRECTS = 5
"""Hops followed before a chain is abandoned. ``web_fetch.go:21``.

No real documentation URL needs six, and each hop is another chance for
the chain to turn inward.
"""

DIAL_TIMEOUT = 10.0
"""Seconds allowed for the TCP handshake alone. ``web_search.go:25``.

Applied by :func:`_pinned_connector`, which caps the connect at this and
then opens the socket's deadline back up for reads. Without the cap a
black-holed address would spend the request's whole budget on a handshake
that was never going to complete; with it, the remaining time is still
available to a server that is merely slow.

Also the default for :meth:`PinnedTransport.request`'s ``timeout``, which
is only reached by a caller that names none — both tools pass their own.
"""

BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("64:ff9b::/96"),
)
"""Addresses no tool in this layer will connect to.

The reference's own eight (``web_safety.go:19-28``), each re-verified:
``169.254.0.0/16`` link-local, which is where AWS, Azure and GCP serve
instance credentials; ``127.0.0.0/8`` loopback — the whole ``/8``, since
``127.0.0.2`` is what gets tried second; ``10.0.0.0/8``,
``172.16.0.0/12`` and ``192.168.0.0/16`` RFC 1918; ``100.64.0.0/10``
carrier NAT; and ``fe80::/10`` with ``fc00::/7``, the IPv6 counterparts,
because a dual-stack host that blocks only IPv4 is not blocked.

**Added here**, each closing something the reference leaves reachable:
``0.0.0.0/8``, since ``http://0.0.0.0:8080/`` reaches a service bound to
``INADDR_ANY`` on Linux and is not inside ``127.0.0.0/8``;
``224.0.0.0/4`` and ``240.0.0.0/4``, multicast and reserved, which
includes ``255.255.255.255``; ``::1/128``, which the reference checks
against ``net.IPv6loopback`` outside its list, folded in so that one code
path checks everything; ``::/128`` unspecified, which the reference does
not check at all; and ``64:ff9b::/96`` NAT64, whose low
32 bits are an IPv4 address, so ``64:ff9b::7f00:1`` routes to
``127.0.0.1`` on a network with a NAT64 gateway.

IPv4-mapped IPv6 is normalised by :func:`blocked_reason` rather than
listed, so one IPv4 line covers ``::ffff:169.254.169.254`` too.

:attr:`ipaddress.IPv4Address.is_private` is deliberately not used: it is
close to this list and not equal to it, excluding ``100.64.0.0/10`` and
including the documentation ranges, so a deployment auditing what is
blocked would be reading the wrong list.
"""


_READ_CHUNK = 65_536
"""Bytes per :meth:`~http.client.HTTPResponse.read` while draining a body.

Small enough that the deadline is re-checked often, large enough that a
megabyte is sixteen reads rather than a thousand.
"""

_SAFE_REDIRECT_HEADERS = {"Accept": "*/*"}
"""What survives a redirect that leaves the origin the caller named.

Everything else a caller attached — an API key, a cookie, a bearer token,
a ``Content-Type`` describing a body that is no longer being sent — was
for one host, and a redirect is the other host asking for it. The
``User-Agent`` is re-added by the caller's own value because it identifies
the client rather than authorising it.
"""


class TransportFailed(RuntimeError):
    """The request was allowed and the network did not deliver it.

    Deliberately **not** a :exc:`UrlRefused`: a refused URL is the model's
    to correct by sending a different one, while a connection reset, a TLS
    failure or a timeout is a fact about the world that no argument can
    change. Tools turn this into ordinary output with ``is_error`` false,
    matching the reference (``web_fetch.go:112-114``).

    A :exc:`RuntimeError` rather than an :exc:`OSError` subclass so that
    catching it cannot accidentally catch a filesystem error, and so it
    cannot be swallowed by an ``except OSError`` written for something
    else.
    """


class UrlRefused(ValueError):
    """This URL will not be requested, and the message says why.

    Mirrors :exc:`~omicsclaw.tools._workspace.PathRefused`: a tool lets it
    propagate, the registry reports ``is_error=True``, and the model can act
    on it by sending a different URL. The subclasses exist for the operator
    reading a log, where an attempt to reach infrastructure and a typo must
    not share a heading.
    """


class UrlMalformed(UrlRefused):
    """Unparseable, no host, an unsupported scheme, or carrying userinfo."""


class UrlNotResolvable(UrlRefused):
    """DNS gave no answer, so nothing about the destination is known."""


class UrlAddressBlocked(UrlRefused):
    """It resolves to an address this agent does not connect to."""


@dataclass(frozen=True, slots=True)
class UrlShape:
    """A URL's offline facts: what a parser can tell without a network.

    Separate from :class:`SafeTarget` because the two checks have different
    owners and different costs. A bad scheme is the model's mistake and can
    be reported for free; whether a name resolves somewhere acceptable costs
    a DNS round trip. Splitting them keeps that lookup happening exactly once
    per request — two lookups would put a rebinding window between the tool's
    answer and the socket's.
    """

    url: str
    """The URL as given, unmodified."""

    scheme: str
    """``http`` or ``https``; anything else never gets this far."""

    host: str
    """The hostname or IP literal, lower-cased, brackets stripped."""

    port: int
    """The explicit port, or 80/443 by scheme."""


@dataclass(frozen=True, slots=True)
class SafeTarget:
    """A URL that has passed every check, and the address it may use.

    :attr:`address` is why this is a value rather than a boolean: a check
    that answers "yes" and lets the caller resolve the name again has
    verified a different connection from the one that happens.
    """

    shape: UrlShape
    """The offline facts, carried through so callers need one object."""

    address: str
    """The single resolved IP this request may connect to.

    No ``family`` beside it: :func:`socket.create_connection` derives the
    family from the address itself, so carrying one would be a field
    nothing reads — the "stored but never used" state this layer reports
    as a defect when it finds it in the reference.
    """

    @property
    def url(self) -> str:
        return self.shape.url

    @property
    def host(self) -> str:
        return self.shape.host

    @property
    def port(self) -> int:
        return self.shape.port

    @property
    def scheme(self) -> str:
        return self.shape.scheme


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """What came back from one request. A value, so a fake is a constructor
    call.

    ``headers`` is a plain mapping rather than
    :class:`email.message.Message`, which is case-insensitive and
    multi-valued; :func:`header` is the one reader and it lower-cases, so a
    test double built from a dict behaves like the real thing.
    """

    status: int
    reason: str
    headers: Mapping[str, str]
    body: bytes
    url: str
    """The URL that finally answered, after any redirects."""

    truncated: bool = False
    """Whether the body hit the caller's byte ceiling before ending."""


Resolver = Callable[[str, int], list[tuple[int, str]]]
"""Answers "what does this name resolve to": ``(family, address)`` pairs."""

Opener = Callable[
    [SafeTarget, str, Mapping[str, str], bytes | None, float, int],
    Awaitable[HttpResponse],
]
"""Speaks HTTP to an already-validated target. The seam a test replaces."""


@runtime_checkable
class Transport(Protocol):
    """Where a web tool's requests actually go. Injected, never imported.

    The same seam as ``bash``'s
    :class:`~omicsclaw.tools.builtin.bash.BashEnvironment`, including the part
    that matters: an implementation is **inside** the trust boundary. Whoever
    assembles a registry decides where these sockets open — a proxy, an
    offline cache, a recorded fixture — and is responsible for gating them.
    :class:`PinnedTransport` is what gating looks like.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DIAL_TIMEOUT,
        max_bytes: int = 1 << 20,
    ) -> HttpResponse:
        """Perform one logical request, following safe redirects."""
        ...


def inspect_url(raw: str) -> UrlShape:
    """The offline half of the gate: parse ``raw`` and check its shape.

    No network, so a tool can call it before doing anything and give the
    model an instant, specific refusal. Raises :exc:`UrlMalformed` for an
    unparseable URL, an unsupported scheme, embedded credentials, a missing
    host or an unusable port.
    """
    text = (raw or "").strip()
    if not text:
        raise UrlMalformed(
            "no url was given. Send an absolute http:// or https:// URL"
        )

    unsafe = _control_character(text)
    if unsafe is not None:
        raise UrlMalformed(
            f"the URL contains {unsafe!r}, which is not allowed. A URL may "
            "not contain spaces or control characters — percent-encode them "
            "(%20 for a space) if they are really part of the address"
        )

    try:
        parts = urlsplit(text)
    except ValueError as exc:
        raise UrlMalformed(f"{text!r} is not a parseable URL: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        named = scheme or "none"
        raise UrlMalformed(
            f"scheme {named!r} is not allowed; this tool speaks http and "
            "https only. A relative path, a file:// path or a host with no "
            "scheme will all land here — send a full URL beginning http://"
            " or https://"
        )

    if parts.username is not None or parts.password is not None:
        raise UrlMalformed(
            "a URL carrying credentials (user:pass@host) is refused, "
            "because which host it names is ambiguous. Send the URL "
            "without the part before the '@'"
        )

    try:
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        # An out-of-range or non-numeric port. ``urlsplit`` defers this to
        # attribute access, so it surfaces here rather than above.
        raise UrlMalformed(f"{text!r} has an unusable port: {exc}") from exc

    if not host:
        raise UrlMalformed(
            f"{text!r} names no host. Send an absolute URL such as "
            "https://example.org/page"
        )

    return UrlShape(
        url=text,
        scheme=scheme,
        host=host.lower(),
        port=port or (443 if scheme == "https" else 80),
    )


def _control_character(text: str) -> str | None:
    """The first space or control character in ``text``, or ``None``.

    A URL may contain neither. Refusing them is a safety property rather
    than pedantry, because :func:`~urllib.parse.urlsplit` *silently
    removes* ``\\t``, ``\\r`` and ``\\n`` before parsing while the raw
    string is what a human is shown: a model that puts a newline in a
    query string gets an approval prompt where the payload reads as prose
    on its own line, and a request that sends it joined up. Every other
    control character has some parser that treats it specially.
    """
    for character in text:
        if character <= "\x20" or character == "\x7f":
            return character
    return None


def blocked_reason(address: str) -> str | None:
    """Why ``address`` is refused, or ``None`` if it is acceptable.

    IPv4-mapped IPv6 addresses are unwrapped before comparison. An address
    :mod:`ipaddress` cannot parse is **refused**, where the reference skips
    past it — fail-closed is the rule everywhere else in this gate.

    No version guard before ``in``: :meth:`ipaddress.IPv4Network.__contains__`
    already answers ``False`` for a cross-version address rather than
    raising. The reference needs its ``To4()`` call because Go's
    ``net.IPNet.Contains`` really can mis-match a 16-byte IPv4-in-IPv6
    value; adding the equivalent test here would be unreachable code
    wearing a safeguard's clothes.
    """
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return f"{address!r} is not an IP address this gate can check"

    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        parsed = parsed.ipv4_mapped

    for network in BLOCKED_NETWORKS:
        if parsed in network:
            return (
                f"{parsed} is in {network}, which this agent does not "
                "connect to (loopback, link-local, private or reserved "
                "address space)"
            )
    return None


def _system_resolver(host: str, port: int) -> list[tuple[int, str]]:
    """:func:`socket.getaddrinfo` reduced to ``(family, address)`` pairs.

    ``AF_UNSPEC`` so both families are seen — checking only the one this
    machine prefers is how a dual-stack bypass works — and ``SOCK_STREAM`` so
    each address appears once rather than once per socket type.
    """
    infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    seen: list[tuple[int, str]] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        address = str(sockaddr[0])
        if (family, address) not in seen:
            seen.append((family, address))
    return seen


def check_url(raw: str, *, resolver: Resolver | None = None) -> SafeTarget:
    """Run the whole gate and return the :class:`SafeTarget` to connect to.

    Parses ``raw``, resolves its host through ``resolver`` (default
    :func:`_system_resolver`), refuses unless **every** answer is acceptable,
    and pins the first. Blocking, because DNS is; callers on an event loop
    use :func:`safe_target`.

    Raises :exc:`UrlMalformed`, :exc:`UrlNotResolvable` — including when the
    lookup itself fails, since a destination that cannot be resolved cannot
    be checked — or :exc:`UrlAddressBlocked`.
    """
    shape = inspect_url(raw)
    lookup = resolver or _system_resolver

    try:
        answers = lookup(shape.host, shape.port)
    except OSError as exc:
        raise UrlNotResolvable(
            f"{shape.host!r} could not be resolved ({exc}), so this "
            "request was not made. A destination that cannot be resolved "
            "cannot be checked, and this gate refuses rather than guesses"
        ) from exc

    if not answers:
        raise UrlNotResolvable(
            f"{shape.host!r} resolved to no addresses, so this request was "
            "not made"
        )

    for _family, address in answers:
        reason = blocked_reason(address)
        if reason is not None:
            raise UrlAddressBlocked(
                f"{shape.host!r} resolves to an address this agent will "
                f"not connect to: {reason}. Fetching internal, loopback "
                "or cloud-metadata addresses is refused whatever the URL "
                "looks like"
            )

    return SafeTarget(shape=shape, address=answers[0][1])


async def safe_target(raw: str, *, resolver: Resolver | None = None) -> SafeTarget:
    """:func:`check_url` off the event loop, via :func:`asyncio.to_thread`.

    Leaves :exc:`asyncio.CancelledError` propagating from the ``await``
    untouched; the thread finishes into nothing, which for a lookup with no
    side effects is the right kind of leak.
    """
    return await asyncio.to_thread(check_url, raw, resolver=resolver)


class PinnedTransport:
    """HTTP over a socket that goes where the gate said, and nowhere else.

    Satisfies :class:`Transport` structurally. One instance is reusable and
    holds no connection: every request opens and closes its own, which costs
    a handshake and buys the guarantee that no pooled connection to a
    previously-safe address is reused after DNS has moved.

    ``resolver`` answers what a name resolves to; it **cannot weaken a
    check**, because whatever address it returns is itself judged.
    ``opener`` speaks HTTP to an already-validated target and is a
    different matter: it is the thing that opens the socket, so an
    implementation that ignores the :class:`SafeTarget` it is handed
    reaches wherever it likes. It is inside the trust boundary, exactly
    like :class:`Transport` itself, and exists so a test can exercise the
    real gate and the real redirect loop with no network.
    """

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        opener: Opener | None = None,
    ) -> None:
        self._resolver = resolver
        self._opener = opener or _open

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DIAL_TIMEOUT,
        max_bytes: int = 1 << 20,
    ) -> HttpResponse:
        """Gate ``url``, send the request, and follow up to
        :data:`MAX_REDIRECTS` safe hops.

        ``timeout`` is the budget for the **whole** call, redirects
        included, not for each hop: every hop is given whatever is left,
        and running out raises :exc:`TransportFailed`. Per-hop budgets
        would multiply by six behind a number the caller derived from the
        engine's per-tool deadline.

        The redirect loop is here rather than in :mod:`urllib`, which
        follows a hop before anyone can look at it. A redirect body is
        discarded, and a hop that leaves the origin the caller named is
        treated as a different request: the body is dropped and the
        caller's headers are replaced by
        :data:`_SAFE_REDIRECT_HEADERS`.

        Raises whatever :func:`check_url` raises, for any hop, plus
        :exc:`TransportFailed` for a network failure or the deadline, and
        :exc:`UrlRefused` for a chain that is too long or a cross-origin
        hop that cannot be followed without re-sending a body.
        """
        sent = {**(headers or {})}
        sent.setdefault("User-Agent", USER_AGENT)
        current = url
        payload = body
        deadline = time.monotonic() + timeout

        for hop in range(MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportFailed(
                    f"{url!r} did not finish within {timeout:g}s and was "
                    "abandoned"
                )

            target = await safe_target(current, resolver=self._resolver)
            response = await self._opener(
                target, method, sent, payload, remaining, max_bytes
            )

            location = header(response, "location")
            if not _is_redirect(response.status) or not location:
                return response

            if hop == MAX_REDIRECTS:
                raise UrlRefused(
                    f"{url!r} redirected more than {MAX_REDIRECTS} times "
                    "and was abandoned. A chain that long is usually a "
                    "loop; try the final URL directly if you know it"
                )

            following = urljoin(current, location)
            crossed = _origin(following) != _origin(current)
            current = following

            if response.status in (301, 302, 303):
                # What every browser does, and the reason is not
                # compatibility: a body re-sent to a host the model never
                # named is a request it never made.
                if method not in ("GET", "HEAD"):
                    method = "GET"
                payload = None
            elif crossed and payload is not None:
                # 307 and 308 mean "repeat it exactly", and repeating it
                # exactly at a host nobody approved is the thing this
                # whole module exists to prevent. There is no honest
                # downgrade — turning a 307 into a GET would violate the
                # status — so the chain stops here.
                raise UrlRefused(
                    f"{current!r} was reached by a {response.status} "
                    "redirect that leaves the host you asked for, and "
                    f"following it would re-send the request body to "
                    "somewhere nobody approved. Request the final URL "
                    "directly if you meant to"
                )

            if crossed:
                # Headers a caller attached for one host — an API key, a
                # cookie, a bearer token — are not for the next one.
                sent = dict(_SAFE_REDIRECT_HEADERS)
                sent["User-Agent"] = (headers or {}).get("User-Agent", USER_AGENT)

        raise AssertionError("unreachable: the loop returns or raises")


def _origin(url: str) -> tuple[str, str, int]:
    """``(scheme, host, port)`` — what "the same site" means for a redirect.

    Falls back to the raw string on an unparseable URL, which compares
    unequal to any real origin and so is treated as crossing.
    """
    try:
        shape = inspect_url(url)
    except UrlRefused:
        return ("", url, 0)
    return (shape.scheme, shape.host, shape.port)


def header(response: HttpResponse, name: str) -> str:
    """One header from ``response``, case-insensitively, or ``""``.

    HTTP header names are case-insensitive and real servers exercise that
    freedom, so ``response.headers["Location"]`` against a fake built with a
    lower-case key is a test that passes and a redirect that is not followed.
    """
    wanted = name.lower()
    for key, value in response.headers.items():
        if key.lower() == wanted:
            return value
    return ""


def _is_redirect(status: int) -> bool:
    """Whether ``status`` is a redirect worth following.

    Named rather than ranged: ``304 Not Modified`` and ``305 Use Proxy`` are
    3xx and are not redirects, so a ``300 <= status < 400`` test would follow
    both.
    """
    return status in (301, 302, 303, 307, 308)


async def _open(
    target: SafeTarget,
    method: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
    max_bytes: int,
) -> HttpResponse:
    """One request over one pinned socket, off the event loop.

    :mod:`http.client` is blocking and :mod:`asyncio` has no HTTP client, so
    the exchange runs in a worker thread. A cancelled turn returns from the
    ``await`` immediately while that thread keeps going, so what has to bound
    it is :func:`_open_blocking`'s own deadline rather than anything the loop
    can do — which is why ``timeout`` is enforced across the whole exchange
    and not merely handed to the socket.
    """
    return await asyncio.to_thread(
        _open_blocking, target, method, headers, body, timeout, max_bytes
    )


def _open_blocking(
    target: SafeTarget,
    method: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
    max_bytes: int,
) -> HttpResponse:
    """The socket work for :func:`_open`, separated so it can be read and
    tested as itself.

    ``timeout`` bounds the **whole** exchange. A socket deadline alone does
    not: it applies per blocking operation and is reset by each one, so a
    server dripping one byte just inside it holds the request open for as
    long as it likes. The body is therefore read in chunks against a
    monotonic deadline, with the socket's own timeout narrowed to what is
    left before each read.

    Reads at most ``max_bytes`` and flags the response when the body was
    longer. Translates every network failure into :exc:`TransportFailed`,
    so a caller can tell "the world said no" from "this URL is refused".
    """
    deadline = time.monotonic() + timeout
    try:
        connection = _connection(target, timeout)
    except OSError as exc:
        raise TransportFailed(_failure(target.url, exc)) from exc

    try:
        parts = urlsplit(target.url)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        connection.request(method, path, body=body, headers=dict(headers))
        raw = connection.getresponse()
        payload, truncated = _read_bounded(
            connection, raw, max_bytes, deadline, target.url
        )
        return HttpResponse(
            status=raw.status,
            reason=raw.reason,
            headers={key: value for key, value in raw.getheaders()},
            body=payload,
            url=target.url,
            truncated=truncated,
        )
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise TransportFailed(_failure(target.url, exc)) from exc
    finally:
        connection.close()


def _read_bounded(
    connection: http.client.HTTPConnection,
    raw: http.client.HTTPResponse,
    max_bytes: int,
    deadline: float,
    url: str,
) -> tuple[bytes, bool]:
    """The response body, capped at ``max_bytes`` and at ``deadline``.

    Returns ``(payload, truncated)``.

    :meth:`~http.client.HTTPResponse.read1` rather than ``read``, and that
    is the whole mechanism rather than a detail.
    :meth:`~io.BufferedReader.read` loops internally until it has the
    bytes it was asked for, so a server dripping one byte at a time —
    each arriving well inside the socket's deadline — blocks in a single
    call for as long as it likes, and a deadline checked between calls is
    never reached. ``read1`` returns as soon as anything arrives, which
    is what makes the check below happen often enough to matter.

    Two ceilings, both real: ``max_bytes`` bounds the memory, and
    ``deadline`` bounds the time no matter how the bytes are spread out.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        # One byte past the ceiling, so that "exactly at the limit" and
        # "longer than the limit" stay distinguishable. A loop condition
        # on ``total`` as well would be a second spelling of this bound,
        # and a redundant guard is one nobody can test.
        wanted = max_bytes + 1 - total
        if wanted <= 0:
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TransportFailed(
                f"{url} was still sending data when the time budget ran "
                "out; the response was abandoned"
            )
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        chunk = raw.read1(min(_READ_CHUNK, wanted))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)

    payload = b"".join(chunks)
    if len(payload) > max_bytes:
        return payload[:max_bytes], True
    return payload, False


def _failure(url: str, exc: BaseException) -> str:
    """One wording for every network failure, for the model to read."""
    reason = str(exc) or type(exc).__name__
    return f"could not reach {url}: {reason}"


def _connection(target: SafeTarget, timeout: float) -> http.client.HTTPConnection:
    """A connection to ``target`` whose socket goes to its validated address.

    :class:`http.client.HTTPConnection` keeps its connector as an *instance*
    attribute, so replacing it redirects the socket while
    :attr:`~http.client.HTTPConnection.host` stays the hostname — which is
    what fills the ``Host`` header and, for HTTPS, what ``wrap_socket`` uses
    as ``server_hostname``. Certificate verification therefore still checks
    the name the model asked for.

    Constructing with ``host=<ip>`` would break every virtual host and every
    certificate.

    Raises :exc:`RuntimeError` if that attribute is absent, rather than
    silently connecting through an unchecked resolver.
    """
    if target.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            target.host,
            target.port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    else:
        connection = http.client.HTTPConnection(
            target.host, target.port, timeout=timeout
        )

    if "_create_connection" not in vars(connection):
        raise RuntimeError(
            "http.client.HTTPConnection no longer holds its connector per "
            "instance, so this request could not be pinned to the address "
            "the safety gate approved; refusing rather than connecting "
            "through an unchecked resolver"
        )
    connection._create_connection = _pinned_connector(target)
    return connection


def _pinned_connector(
    target: SafeTarget,
) -> Callable[[tuple[str, int], float | None, tuple[str, int] | None], socket.socket]:
    """A :func:`socket.create_connection` replacement pinned to ``target``.

    The address argument is dropped on purpose: it carries the hostname
    :mod:`http.client` would have resolved, and dropping it is the whole
    mechanism.

    The connect itself is bounded by :data:`DIAL_TIMEOUT` rather than by
    the request's whole budget, so a black-holed address cannot spend the
    entire allowance on a handshake; the socket's deadline is then opened
    back up to the caller's, since reads are bounded separately by
    :func:`_read_bounded`.
    """

    def connect(
        address: tuple[str, int],
        timeout: float | None = None,
        source_address: tuple[str, int] | None = None,
    ) -> socket.socket:
        budget = DIAL_TIMEOUT if timeout is None else min(DIAL_TIMEOUT, timeout)
        sock = socket.create_connection(
            (target.address, target.port), budget, source_address
        )
        sock.settimeout(timeout)
        return sock

    return connect


__all__ = [
    "ALLOWED_SCHEMES",
    "BLOCKED_NETWORKS",
    "DIAL_TIMEOUT",
    "HttpResponse",
    "MAX_REDIRECTS",
    "Opener",
    "PinnedTransport",
    "Resolver",
    "SafeTarget",
    "Transport",
    "TransportFailed",
    "USER_AGENT",
    "UrlAddressBlocked",
    "UrlMalformed",
    "UrlNotResolvable",
    "UrlRefused",
    "UrlShape",
    "blocked_reason",
    "check_url",
    "header",
    "inspect_url",
    "safe_target",
]
