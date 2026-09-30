"""``web_fetch`` — read one URL, after asking, and never an internal one.

Modelled on harness9's ``internal/tools/web_fetch.go``. An HTTP GET whose
destination has been proved not to be internal infrastructure, whose
response is reduced to Markdown, and which asks a human first because the
request itself is the risk.

**The approval is about the request, not the response**, which is what
makes ``ASK`` right for a tool that only reads.
:data:`~omicsclaw.entry.assembly.SAFETY_RULES` rule 1 is that genetic data
never leaves this machine, and a URL is an outbound
channel: everything in the path and query string is transmitted, and a
model asked to "look this identifier up" will put the identifier in the
URL. The gate in ``omicsclaw/tools/_websafety.py`` cannot see that — to
it, ``https://example.com/?q=<patient-id>`` is a public address like any
other. So what stands between a payload and the wire is a person reading
:meth:`WebFetchTool._reason`, which shows the whole URL and says plainly
that it will be sent. By the "can this cause something irreversible"
criterion the answer is yes: bytes that have left cannot be recalled.

**World failure is not tool failure.** A 404, a 500, an unsupported
content type and a transport error are facts about the world, are returned
as ordinary text, and leave ``is_error`` false — a model told its *tool*
failed will try to fix the tool. A refused URL is the other case: the
model fixes that by sending a different one, so
:exc:`~omicsclaw.tools._websafety.UrlRefused` propagates.

**Nothing here has spoken to a real HTTP endpoint.** This environment has
no network, so every test drives an injected
:class:`~omicsclaw.tools._websafety.Transport` or a fake ``opener`` under
the real gate. It is the same debt ``docs/FRAMEWORK-REBUILD.md`` records
against the provider adapters, and the reason every borrowed literal here
carries a re-verification note.

The existing ``runtime/tools/builders/engineering.py`` ``web_fetch`` is
untouched and still checks only whether the URL starts with ``http://``.
Three things it does better, recorded rather than discovered later:

* its ``max_chars`` ceiling is **100,000**, against
  :data:`~omicsclaw.tools._html.HARD_MAX_CHARS`' 32,000. ``read_file``
  kept the same legacy ceiling for its own byte limit; this tool did not,
  and the reference's 32,000 won by default rather than by argument.
* it converts HTML with ``markdownify``, a real converter with tables,
  emphasis and nesting, where :mod:`omicsclaw.tools._html` is a fixed tag
  list. When this was written the library was a dependency of this
  repository (through extras deleted since), so the honest statement of
  the gap was not only "the standard library has no readability" but
  "this layer may not import what the old one uses".
* it sends a browser ``User-Agent``. ``OmicsClaw/1.0`` is the honest one
  and is what ships, but documentation sites behind a WAF answer 403 to
  non-browser agents, so some pages the old tool reads this one will not.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools._html``,
``omicsclaw.tools._websafety``, ``omicsclaw.tools.base``,
``omicsclaw.tools.context``, ``omicsclaw.tools.function_tool``, and the
standard library. Notably **not** ``builtin/bash.py``: the engine-margin
arithmetic discussed under :data:`FETCH_TIMEOUT` is asserted in
``tests/tools/test_web_fetch.py``, and importing a constant only to
mention it in prose would leave an unused name here.
"""

from __future__ import annotations

import copy
from typing import Any

from omicsclaw.schema import ToolDefinition

from .._html import (
    DEFAULT_MAX_CHARS,
    HARD_MAX_CHARS,
    MAX_BODY_BYTES,
    extract_page,
    truncate_text,
)
from .._websafety import (
    HttpResponse,
    PinnedTransport,
    Transport,
    TransportFailed,
    UrlShape,
    header,
    inspect_url,
)
from ..base import ApprovalMode, RiskLevel, ToolPolicy
from ..context import report_progress, require_approval
from ..function_tool import ToolArgumentError, decode_arguments, validate_arguments

TOOL_NAME = "web_fetch"
"""harness9's name, and unlike ``read_file``'s it really does collide.

``runtime/tools/builders/engineering.py`` has a ``web_fetch`` too, so a
registry holding both would be refused by
:meth:`~omicsclaw.tools.registry.ToolRegistry.register`: the migration has
to retire one of them rather than mount both. Named here so that is met
in the source rather than in a start-up failure. Renaming this one was
rejected — a model shown ``web_fetch_v2`` learns nothing, and the legacy
tool is the one with the SSRF hole.
"""

FETCH_TIMEOUT = 15.0
"""Seconds one fetch may take. ``web_fetch.go:20``.

Re-checked against the constraint that made ``bash``'s 120 s unusable:
:attr:`~omicsclaw.engine.config.EngineConfig.tool_timeout` defaults to
60 s and wraps the whole call, approval included. 15 s plus ``bash``'s
15 s margin is 30 s, so unlike ``bash`` this number needed verification
rather than derivation. ``tests/tools/test_web_fetch.py`` asserts the
arithmetic, since this layer cannot import the engine.

It is a *network* deadline rather than a workload one: a page that has
not begun answering in fifteen seconds is not going to.
"""


def _description() -> str:
    """The tool description, with the ceilings interpolated from the code.

    Built rather than written out so the numbers a model is told are the
    numbers that are enforced; a description quoting a stale limit teaches the
    model to send arguments that get clamped.
    """
    return (
        "Fetch one web page over HTTP and return its main text as "
        "Markdown. Use it to read documentation, an article or a plain "
        "text endpoint when you already know the URL; use web_search "
        "first if you do not. Only http:// and https:// URLs are "
        f"accepted, at most {MAX_BODY_BYTES // 1024} KiB of page is read, "
        f"and at most {DEFAULT_MAX_CHARS} characters come back by default "
        f"({HARD_MAX_CHARS} if you ask). Addresses inside this machine or "
        "its private network are refused, including cloud metadata "
        "endpoints, so this cannot be used to inspect local services — "
        "use bash for that. EVERYTHING IN THE URL IS SENT TO THE REMOTE "
        "HOST, including the query string: never put data from the user's "
        "files, sequences or identifiers into a URL. Depending on the "
        "session's permission settings, the user may be asked to approve the "
        "request first; a declined request returns an error and nothing is sent."
    )


FETCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": (
                "The absolute URL to fetch, beginning http:// or "
                "https://. Required."
            ),
        },
        "max_chars": {
            "type": "integer",
            "description": (
                f"Maximum characters to return. Default "
                f"{DEFAULT_MAX_CHARS}, clamped to {HARD_MAX_CHARS}."
            ),
        },
    },
    "required": ["url"],
    "additionalProperties": False,
}

_POLICY = ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.ASK,
    prompts_for_itself=True,
    read_only=False,
    concurrency_safe=True,
    touches_network=True,
    allowed_in_background=False,
    tags=frozenset({"network", "web", "egress"}),
)
"""``HIGH`` risk, ``ASK`` approval, declared rather than left to default.

``HIGH`` needs the argument spelled out, because the instinct is that a
GET is a read and reads are cheap. This tool's blast radius is not what it
brings back, it is **what it takes out**: an arbitrary URL is an arbitrary
outbound message, and this repository's first safety rule is about exactly
that.

``read_only=False`` is a deliberate refusal to make a comfortable claim.
The field says "changes nothing anywhere", and a GET to a badly built API
changes their data while a GET of any kind adds a line to their logs.

``concurrency_safe=True`` is honest: two fetches share no local state and
:class:`~omicsclaw.tools._websafety.PinnedTransport` holds no connection
between calls. ``allowed_in_background=False`` because an unattended turn
has nobody to approve the egress.
"""


class WebFetchTool:
    """Fetch one URL and return its readable text.

    Satisfies :class:`~omicsclaw.tools.base.Tool` structurally. Hand-written
    against that Protocol rather than wrapped by
    :class:`~omicsclaw.tools.function_tool.FunctionTool` because it asks a
    human, and a URL is the case where showing the bytes the model actually
    sent matters most — percent-encoding, a stray space and a homoglyph in a
    hostname are all things a person is looking *at*.

    ``transport`` defaults to
    :class:`~omicsclaw.tools._websafety.PinnedTransport`, which gates and pins
    every hop; an implementation is inside the trust boundary, like ``bash``'s
    ``BashEnvironment``. ``policy`` is a plain attribute with no constructor
    argument, since ``register(policy=)`` is the authoritative override.
    """

    policy = _POLICY

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        timeout: float = FETCH_TIMEOUT,
    ) -> None:
        self._transport = transport or PinnedTransport()
        self._timeout = timeout
        self._definition = ToolDefinition(
            name=TOOL_NAME,
            description=_description(),
            input_schema=copy.deepcopy(FETCH_SCHEMA),
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
        """Fetch the URL in ``arguments`` and return its text.

        ``arguments`` is the raw JSON payload and reaches
        :func:`~omicsclaw.tools.context.require_approval` unparsed.

        Checks the URL's shape, asks for approval, then requests it — the
        resolving half of the gate runs inside the transport. A malformed URL is
        refused *before* the prompt: asking a human to approve a URL that was
        never going to parse is the friction that teaches people to approve
        without reading.

        Raises :exc:`~omicsclaw.tools._websafety.UrlRefused` for a URL that will
        not be requested and
        :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` for a payload that
        does not match the schema. An HTTP error status is *not* an exception.
        """
        raw, max_chars = _arguments(arguments)
        shape = inspect_url(raw)

        await require_approval(
            self.name,
            arguments,
            policy=self.policy,
            reason=self._reason(shape),
            reason_shows_call=True,
        )
        await report_progress(f"fetching {shape.url}", tool_name=self.name)

        try:
            response = await self._transport.request(
                "GET",
                shape.url,
                headers={"Accept": "text/html,text/plain,*/*"},
                timeout=self._timeout,
                max_bytes=MAX_BODY_BYTES,
            )
        except TransportFailed as failure:
            # A reset, a TLS failure or the deadline. The world said no,
            # and there are no arguments the model can change to mend a
            # network — so this is output, not ``is_error``.
            return (
                f"The request was made and did not complete: {failure}. "
                "That is a network failure rather than a tool failure — "
                "the site may be down or unreachable from here. Trying "
                "again later, or a different URL, is the way forward."
            )
        return render(response, max_chars)

    # ---- internals ------------------------------------------------------

    def _reason(self, shape: UrlShape) -> str:
        """The text a human is shown when asked to approve this fetch.

        Carries the **whole URL**, unabbreviated, and says that it leaves the
        machine. Abbreviating the middle would hide precisely the part an
        exfiltration attempt lives in, and naming the host alone would answer a
        question nobody asked: the risk is not that ``example.org`` is contacted,
        it is what is said to it.
        """
        return (
            f"send an HTTP GET to {shape.host} and fetch:\n{shape.url}\n"
            "Everything in that URL, including its query string, leaves "
            "this machine. Approve only if none of it is data from the "
            "user's files."
        )


# ---- rendering the response ---------------------------------------------


def render(response: HttpResponse, max_chars: int) -> str:
    """Turn ``response`` into the text the model reads.

    ``web_fetch.go:117-142``. HTML and XHTML are reduced to Markdown, other
    text-shaped types are returned as they arrived, and anything else is
    reported as an unread content type. A non-2xx status becomes a line naming
    it.

    Never raises: an HTTP status, a content type and a truncated body are all
    facts about the world, and the model's next move after "HTTP 404" is a
    different URL. A body cut off at the byte ceiling is still returned with a
    notice, where the reference discards a page over 1 MiB entirely.
    """
    if not 200 <= response.status < 300:
        return (
            f"HTTP {response.status} {response.reason} from {response.url}. "
            "The request itself succeeded — this is the server's answer, "
            "not a tool failure. Check the URL, or try a different page."
        )

    content_type = header(response, "content-type")
    kind = content_type.split(";")[0].strip().lower()
    text = _decode(response.body, content_type)

    if kind in ("text/html", "application/xhtml+xml"):
        page = extract_page(text, response.url, max_chars)
        if response.truncated:
            return (
                f"{page}\n\n[The page was larger than "
                f"{MAX_BODY_BYTES // 1024} KiB and was cut off before it "
                "ended, so the text above may be incomplete]"
            )
        return page

    if kind.startswith("text/") or kind in (
        "application/json",
        "application/xml",
        "application/javascript",
    ):
        body = truncate_text(text, max_chars)
        if response.truncated:
            return (
                f"{body}\n\n[The response was larger than "
                f"{MAX_BODY_BYTES // 1024} KiB and was cut off]"
            )
        return body

    named = kind or "unset"
    return (
        f"{response.url} returned content of type {named}, which this "
        f"tool does not read ({len(response.body)} bytes). It handles HTML "
        "and text; a PDF, an image or an archive has to be downloaded with "
        "bash and opened by something that understands it."
    )


def _decode(body: bytes, content_type: str) -> str:
    """Decode ``body`` using the charset named in ``content_type``.

    Implemented rather than translated: ``web_fetch.go:130`` writes
    ``string(data)``, a no-op in Go, while a Python :class:`str` needs an
    encoding chosen. Falls back to UTF-8 when no charset is named or the named
    one is unknown, since ``charset=utf8`` and ``charset=iso8859-1`` both
    appear in the wild.

    ``errors="replace"``, unlike ``edit_file``'s strict decode: this only
    displays the bytes, so a page with one bad byte in a footer should be
    readable rather than an error.
    """
    charset = ""
    for parameter in content_type.split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "charset":
            charset = value.strip().strip('"\'')
            break

    if charset:
        try:
            return body.decode(charset, errors="replace")
        except LookupError:
            pass
    return body.decode("utf-8", errors="replace")


# ---- module-level helpers ------------------------------------------------


def _arguments(arguments: str) -> tuple[str, int]:
    """Decode ``arguments`` into ``(url, max_chars)``.

    ``max_chars`` is clamped to :data:`~omicsclaw.tools._html.HARD_MAX_CHARS`
    rather than refused — a refusal costs a turn, while a clamp plus a
    truncation notice says the same thing and still answers the question.
    Zero and negative mean the default.

    Raises :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` when the
    payload does not match :data:`FETCH_SCHEMA`.
    """
    decoded = decode_arguments(arguments)
    issues = validate_arguments(decoded, FETCH_SCHEMA)
    if issues:
        listed = "\n".join(f"  - {issue}" for issue in issues)
        raise ToolArgumentError(
            "the arguments do not match this tool's schema:\n"
            f"{listed}\nRe-send the call with all of these corrected."
        )

    requested = decoded.get("max_chars")
    limit = DEFAULT_MAX_CHARS
    if isinstance(requested, int) and requested > 0:
        limit = min(requested, HARD_MAX_CHARS)
    return str(decoded["url"]), limit


__all__ = [
    "FETCH_SCHEMA",
    "FETCH_TIMEOUT",
    "TOOL_NAME",
    "WebFetchTool",
    "render",
]
