"""``MCPTool`` — a tool living in another process, wearing the local shape.

An MCP server offers tools this process did not write: a name, a
description, a JSON Schema, and a way to call it. Wrapped here, one
becomes an ordinary :class:`~omicsclaw.tools.base.Tool`, so it gets the
registry's ordering, its error handling and its timing for free and the
engine never learns that MCP exists.

Registry names are ``mcp__{server}__{tool}``, minted by
:func:`mcp_tool_name`. No sanitised segment can contain ``__``, so
``name.split("__", 2)`` always recovers the server and the tool.

Imports ``omicsclaw.schema``, ``omicsclaw.tools.base``,
``omicsclaw.tools.context``, ``omicsclaw.tools.function_tool``,
``omicsclaw.tools.preview`` and the standard library. The MCP client is
*not* imported: an :class:`MCPTool` is built from plain values and a
callable, and the transport stays the caller's business (``omicsclaw.mcp``
supplies one).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any

from omicsclaw.schema import ToolDefinition

from .base import ApprovalMode, RiskLevel, ToolPolicy
from .context import require_approval
from .function_tool import ToolArgumentError, as_text
from .preview import MAX_PREVIEW_CHARS, preview_arguments

MCPCaller = Callable[[str], Any]
"""How this process reaches the tool: raw JSON in, text out.

Receives the argument string exactly as
:attr:`~omicsclaw.schema.ToolCall.arguments` carries it — already checked
to be a JSON object, never re-encoded. May be ``async``; usually is.
"""

NAME_PREFIX = "mcp__"
SEGMENT_SEPARATOR = "__"

MAX_TOOL_NAME_LENGTH = 64
"""The narrowest tool-name limit among the vendors this project targets.

OpenAI and Anthropic both constrain a function name to 64 characters of
``[A-Za-z0-9_-]``. A name over the limit is rejected by the API, which
surfaces as the whole turn failing rather than as one tool misbehaving,
so the cap is applied here where a deterministic answer is still possible.
"""

_DIGEST_LENGTH = 6
_UNNAMED = "unnamed"
_UNDERSCORE_RUN = re.compile(r"_+")


def _empty_schema() -> dict[str, Any]:
    """A fresh empty object schema, never the same dict twice.

    Shared nested state between two tools that both failed to describe
    themselves would make one server's repair show up on another's tool.
    """
    return {"type": "object", "properties": {}}


def sanitize_mcp_name(name: str) -> str:
    """One MCP name segment, reduced to ``[A-Za-z0-9_]`` with no ``__``.

    The rule, in full: every character outside ``A-Za-z0-9_`` becomes
    ``_``; runs of ``_`` collapse to one; leading and trailing ``_`` are
    dropped; an empty result becomes ``"unnamed"``.

    Three deliberate departures from the reference harness's
    ``SanitizeMCPName``, which replaces non-alphanumerics one-for-one and
    stops there:

    *Collapsing runs, so no segment can contain* ``__``. This is what
    makes ``mcp__{server}__{tool}`` parseable at all. Without it a server
    called ``my--server`` sanitises to ``my__server`` and
    ``name.split("__", 2)`` reports the server as ``my`` and the tool as
    ``server__whatever``. The separator has to be a sequence the segments
    cannot produce.

    *ASCII only.* The harness uses ``unicode.IsLetter``/``IsDigit``, so a
    tool named ``分析`` survives intact. That name is then rejected by
    both vendors' ``^[a-zA-Z0-9_-]{1,64}$``, and the failure arrives as a
    400 on the whole request rather than as a problem with one tool.
    ``str.isascii()`` is checked alongside ``str.isalnum()`` for that
    reason; the readable name is not lost, it is kept on
    :attr:`MCPTool.tool` and shown in the description.

    *Never empty.* A name of ``"···"`` sanitises to ``""`` in the
    harness, producing ``mcp____tool`` — which contains ``____``, splits
    wrongly, and which the registry would accept. Here it becomes
    ``unnamed_`` plus a digest of the original, so a server whose tool
    names are entirely non-ASCII gets several distinct placeholders rather
    than several collisions: a placeholder is a legibility problem, and a
    collision is one tool shadowing another.

    **The third kind of loss is left un-fingerprinted, and that is a
    decision with a cost rather than an oversight.** Substitution is
    lossy like the other two: ``get-thing`` and ``get_thing`` from one
    server both sanitise to ``get_thing``, and
    :meth:`~omicsclaw.tools.registry.ToolRegistry.register` refuses the
    second with an error naming a key nobody chose — the exact failure
    :func:`_capped` pays a digest to avoid. Pinned as a known cost in
    ``tests/tools/test_mcp_tool.py`` —
    ``test_two_names_that_differ_only_by_a_separator_collide`` — rather
    than fixed, for three reasons:

    *No pure function of one name can do better.* Sanitising is
    idempotent, so every lossy original collides with its own sanitised
    form, which is itself a legal name. Avoiding collisions therefore
    means a digest on **every** lossy name, not on the colliding ones —
    there is no way to tell them apart without seeing the whole set.

    *Lossy substitution is the common case, where the other two are
    rare.* Truncation and emptiness strike names that are already
    unreadable, so a digest costs nothing there. Hyphens are ordinary in
    MCP server keys (``brave-search``, ``sequential-thinking``), and
    ``mcp__brave_search_4f2a91__web_search_0c7e13`` is what uniform
    fingerprinting would put in front of the model for every one of them
    — thirteen characters of the 64-character budget spent making
    truncation, the loss that *is* fingerprinted, more likely.

    *It would make the server segment unreadable* for every hyphenated
    server key, and that segment is what attributes a call to a server.

    Collision resolution wants set knowledge, and the thing that has it is
    the code that mounts a whole server's tools at once:
    :class:`omicsclaw.mcp.MCPManager` keeps the first tool of a clashing
    name and reports the later one as skipped.

    Reused deliberately rather than kept private: whatever code later
    lists MCP tools for a UI has to arrive at the same name as the
    registry did, and the harness records the same requirement for its own
    ``mcp.Manager``. Two implementations of a naming rule are one
    implementation and one bug — which is also why the de-collision above
    is not smuggled into :class:`MCPTool`'s constructor, where the
    registry key would stop matching what this function answers.
    """
    kept = "".join(
        char if char.isascii() and (char.isalnum() or char == "_") else "_"
        for char in name
    )
    collapsed = _UNDERSCORE_RUN.sub("_", kept).strip("_")
    return collapsed or f"{_UNNAMED}_{_digest(name)}"


def mcp_tool_name(
    server: str,
    tool: str,
    *,
    max_length: int = MAX_TOOL_NAME_LENGTH,
) -> str:
    """``mcp__{server}__{tool}``, sanitised and within ``max_length``.

    The shape is the one the Claude Agent SDK uses, so a name minted here
    is recognisable to other MCP clients' users.

    When the parts do not fit, the **server keeps its length first** and
    the tool is shortened, because the server segment is what attributes
    a call to its server; only if the server alone
    exceeds half the budget is it shortened too. Shortening appends a
    short digest of the full segment rather than simply truncating, so two
    long names that share a prefix — the normal case for one server's
    tools — do not collapse onto one registry key and shadow each other.
    """
    budget = max_length - len(NAME_PREFIX) - len(SEGMENT_SEPARATOR)
    if budget < 2:
        raise ValueError(
            f"max_length={max_length} leaves no room for a server and a tool "
            f"name after the {NAME_PREFIX!r} prefix and {SEGMENT_SEPARATOR!r} "
            "separator"
        )
    server_part = sanitize_mcp_name(server)
    tool_part = sanitize_mcp_name(tool)
    if len(server_part) + len(tool_part) > budget:
        server_part = _capped(server_part, min(len(server_part), budget // 2))
        tool_part = _capped(tool_part, budget - len(server_part))
    return f"{NAME_PREFIX}{server_part}{SEGMENT_SEPARATOR}{tool_part}"


class MCPTool:
    """One MCP server's tool, mounted as if it were local.

    Construction never fails on the server's data. A schema that does not
    decode is replaced by an empty object schema and the complaint is kept
    on :attr:`schema_error`; the reference harness does the same, on the
    grounds that one malformed tool must not stop a server's other tools
    from being registered. Recording *why* is the addition — a silent
    fallback to "this tool takes no arguments" is indistinguishable from a
    tool that genuinely takes none, and the model would be told the second
    while the first was true.
    """

    def __init__(
        self,
        server: str,
        tool: str,
        *,
        caller: MCPCaller,
        description: str = "",
        input_schema: Any = None,
        policy: ToolPolicy | None = None,
        origin: str = "",
        max_name_length: int = MAX_TOOL_NAME_LENGTH,
    ) -> None:
        """*origin* says where calls go (``"remote https://host/mcp"``);
        it is shown to the human asked to approve a call."""
        # ``server`` and ``tool`` are kept unsanitised: they are what a
        # human configured and what the server calls itself, and they are
        # the only way back from a mangled registry key to the thing it
        # names.
        self.server = server
        self.tool = tool
        self.origin = origin
        schema, error = _parse_input_schema(input_schema)
        self.schema_error: str = error
        self._name = mcp_tool_name(server, tool, max_length=max_name_length)
        self._caller = caller
        self._definition = ToolDefinition(
            name=self._name,
            description=_describe(server, description, error),
            input_schema=schema,
        )
        self.policy = policy if policy is not None else _default_policy(server)

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        """The server's own description and schema, passed through.

        Not rewritten: the server author knows what the tool does and this
        process does not. The only addition is the ``[MCP:server]`` tag,
        which tells a model that this capability comes from somewhere
        else — useful when two servers offer something similar and the
        sanitised names have stopped being self-explanatory.
        """
        return self._definition

    async def execute(self, arguments: str) -> str:
        """Check the payload's shape, ask for approval, then call the server.

        Raises :exc:`~omicsclaw.tools.function_tool.ToolArgumentError`
        when *arguments* is not a JSON object (an empty string counts as
        ``{}``), before any human is asked. Approval goes through
        :func:`~omicsclaw.tools.context.require_approval` with the full
        argument string, and a reason naming the tool's :attr:`origin` and
        previewing the arguments (see :meth:`_reason`): the default policy
        is ``ASK``, so with no approval channel bound the call is refused
        and the server is never contacted.

        The payload is checked for shape only, never against the tool's
        schema — the server enforces its own schema, and a second copy
        here could only disagree with it. The caller receives the string
        unchanged.

        A failing caller raises, and
        :meth:`~omicsclaw.tools.registry.ToolRegistry.execute` turns that
        into an ``is_error`` Observation carrying the transport's own
        message — which is the useful one, since "connection refused" and
        "unknown tool" are different problems with different fixes.
        """
        _require_object(arguments)
        reason, shows_call = self._reason(arguments)
        await require_approval(
            self.name,
            arguments,
            policy=self.policy,
            reason=reason,
            reason_shows_call=shows_call,
        )
        outcome = self._caller(arguments)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return as_text(outcome)

    def _reason(self, arguments: str) -> tuple[str, bool]:
        """The text a human is shown when asked to approve this call.

        Names the server, where calls to it go and the tool, then the
        arguments as :func:`~omicsclaw.tools.preview.preview_arguments`
        renders them, on a line of their own.

        Returns:
            The text, and whether it shows the whole call: ``False`` when
            the preview was cut at
            :data:`~omicsclaw.tools.preview.MAX_PREVIEW_CHARS`.
        """
        where = f" via {self.origin}" if self.origin else ""
        head = f"MCP server {self.server!r}{where}, tool {self.tool!r}"
        whole = preview_arguments(arguments, limit=sys.maxsize)
        if not whole:
            return f"{head}, with no arguments", True
        if len(whole) <= MAX_PREVIEW_CHARS:
            return f"{head}, with arguments:\n{whole}", True
        return f"{head}, with arguments:\n{preview_arguments(arguments)}", False


# ---- internals ----------------------------------------------------------


def _require_object(arguments: str) -> None:
    """Refuse a payload that is not a JSON object; ``""`` is allowed."""
    if not arguments.strip():
        return
    try:
        decoded = json.loads(arguments)
    except ValueError as exc:
        raise ToolArgumentError(f"arguments are not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ToolArgumentError(
            f"arguments must be a JSON object, not {type(decoded).__name__}"
        )


def _default_policy(server: str) -> ToolPolicy:
    """What an unvouched-for third-party tool is assumed to be.

    ``ASK`` and ``HIGH``, because this code was neither written nor
    reviewed here and its name is the only thing known about it.

    **The effect claims are left unasserted.** An MCP server may be a
    local subprocess on stdio or an HTTP endpoint across the internet; the
    free-text ``origin`` says which to a human, but nothing here can
    verify it. Setting ``touches_network=True`` would be a guess in one
    direction and ``False`` a guess in the other, and
    :class:`~omicsclaw.tools.base.ToolPolicy` is explicit that a gate must
    never grant anything on the strength of a ``False`` nobody wrote. The
    tags are what a deployment that cares should filter on: ``"mcp"``
    catches every one of them, ``"mcp:{server}"`` catches one server's.
    """
    return ToolPolicy(
        risk_level=RiskLevel.HIGH,
        approval_mode=ApprovalMode.ASK,
        prompts_for_itself=True,
        tags=frozenset({"mcp", f"mcp:{server}"}),
    )


def _describe(server: str, description: str, schema_error: str = "") -> str:
    """The server's description, tagged with where it came from, plus a note
    when the server's argument schema could not be used."""
    text = description.strip()
    tagged = f"[MCP:{server}] {text}" if text else f"[MCP:{server}]"
    if schema_error:
        tagged += (
            f" (This tool's argument schema could not be read — {schema_error} — "
            "so its parameters are unknown; the server validates what you send.)"
        )
    return tagged


def _parse_input_schema(raw: Any) -> tuple[dict[str, Any], str]:
    """The server's schema as a dict, plus why it had to be replaced.

    Accepts what an MCP client might hand over: an already-decoded
    mapping, a JSON string or bytes, or nothing. Never raises — a tool
    that cannot describe its arguments is still a tool that can be called,
    and refusing to register it would take the server's working tools down
    with it.
    """
    if raw is None:
        return _empty_schema(), ""
    if isinstance(raw, Mapping):
        return (dict(raw), "") if raw else (_empty_schema(), "")
    if isinstance(raw, (str, bytes, bytearray)):
        if not raw.strip():
            return _empty_schema(), ""
        try:
            decoded = json.loads(raw)
        except ValueError as exc:
            return _empty_schema(), f"not decodable as JSON: {exc}"
        if isinstance(decoded, dict):
            return decoded, ""
        return (
            _empty_schema(),
            f"decoded to a {type(decoded).__name__}, not a JSON object",
        )
    return _empty_schema(), f"was a {type(raw).__name__}, not a schema"


def _capped(text: str, limit: int) -> str:
    """``text`` within ``limit`` characters, keeping distinct names distinct.

    A plain truncation would map ``search_pubmed_by_author`` and
    ``search_pubmed_by_journal`` onto one name, and the registry would
    accept the first and reject the second as a duplicate — a server's
    tool disappearing with an error about a name nobody chose. The digest
    is of the whole segment, so the collision needs a SHA-256 prefix
    match rather than a shared beginning.

    The trailing ``_`` of the kept head is stripped so the result cannot
    reintroduce the ``__`` that :func:`sanitize_mcp_name` removed.
    """
    if len(text) <= limit:
        return text
    digest = _digest(text)
    if limit <= _DIGEST_LENGTH:
        return digest[:limit]
    head = text[: limit - _DIGEST_LENGTH - 1].rstrip("_")
    return f"{head}_{digest}" if head else digest


def _digest(text: str) -> str:
    """A short, stable fingerprint of a name that could not survive intact."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


__all__ = [
    "MAX_TOOL_NAME_LENGTH",
    "MCPCaller",
    "MCPTool",
    "NAME_PREFIX",
    "SEGMENT_SEPARATOR",
    "mcp_tool_name",
    "sanitize_mcp_name",
]
