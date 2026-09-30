"""Strict Desktop ``POST /chat/stream`` ingress: bytes in, one turn out.

The module owns only transport parsing. It never runs a turn, never
touches a workspace and never decides what the agent does; it decides
whether a request is admissible and, if it is, what
:class:`~omicsclaw.entry.ingress.InboundMessage` it means.

:func:`parse_chat_stream_document` bounds the raw bytes — size, nesting
depth, duplicate keys, non-finite constants — before and while parsing,
because this is the hostile-input surface. :func:`decode_chat_stream_request`
then refuses, by published code, what this route does not serve:

* every attachment-shaped input (``attachments_supported: False``), rather
  than silently dropping files the caller believed were uploaded;
* a request without a ``source_request_id``
  (``source_request_id_required: True``);
* per-turn provider credentials, because a chat request is not where a
  deployment changes which backend it pays;
* an ``ingress_schema_version`` other than the contract's request version.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Final, Mapping

from omicsclaw.entry.ingress import InboundMessage

from .wire_contract import DESKTOP_CHAT_REQUEST_SCHEMA_VERSION

__all__ = [
    "DEFAULT_MAX_JSON_NESTING",
    "DEFAULT_MAX_REQUEST_BYTES",
    "DESKTOP_PROFILE_ID",
    "DESKTOP_SURFACE",
    "PERMISSION_PROFILES",
    "ChatStreamRequest",
    "DesktopIngressError",
    "decode_chat_stream_request",
    "ingress_identity",
    "parse_chat_stream_document",
]

DEFAULT_MAX_REQUEST_BYTES: Final = 2 * 1024 * 1024
"""Largest ``/chat/stream`` body this Surface will read.

It bounds one chat message plus its envelope; attachments never travel
this route.
"""

DEFAULT_MAX_JSON_NESTING: Final = 64
"""Bounds structure depth *before* ``json.loads`` sees the document, so
a deeply nested payload is a 422 rather than a ``RecursionError`` whose
depth depends on the interpreter's recursion limit.
"""

DESKTOP_SURFACE: Final = "desktop"
DESKTOP_PROFILE_ID: Final = "owner"
"""The only profile a local Desktop backend serves.

Pinned here rather than read from the request: accepting an owner
partition from the client would let a same-origin request choose whose
conversations it is continuing.
"""

DEFAULT_PERMISSION_PROFILE: Final = "default"
FULL_ACCESS: Final = "full_access"
PERMISSION_PROFILES: Final = frozenset({DEFAULT_PERMISSION_PROFILE, FULL_ACCESS})
"""The values of a session's ``permission_profile``."""

_OPAQUE_ID = re.compile(r"\A(?:|[0-9a-f]{32})\Z")
r"""``source_request_id`` and ``installation_id`` are either absent or
exactly 32 lowercase hex characters. The pattern admits the empty string
because the field is optional at the transport layer; whether an *empty*
one is admissible is :func:`decode_chat_stream_request`'s decision and
depends on ``source_request_id_required``.

``\A``/``\Z`` rather than ``^``/``$``, which is not style. Python's ``$``
also matches immediately **before** a trailing newline, so ``"^(?:|…)$"``
accepts ``"\n"`` — one character, so the length guard beside it passes too
— and a bare newline becomes a valid idempotency key that is then
concatenated into :attr:`ChatStreamRequest.source_namespace`. ``\Z`` is the
end of the string and nothing else."""


class DesktopIngressError(ValueError):
    """A request refused at the wire, before any turn exists.

    ``code`` is the stable name the client branches on, answered as
    ``{"detail": code}``; ``status_code`` is the HTTP status it maps to.
    """

    def __init__(self, code: str, *, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A repeated key is a rejection, not a last-one-wins merge: which one wins is the parser's choice and two
    parsers on the two sides of this seam need not agree."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    """``NaN`` / ``Infinity`` are Python's JSON extension, not JSON; accepting them inbound would put a value back on the
    wire that a conforming client cannot parse."""
    raise ValueError(f"non-finite JSON constant {value!r}")


def _reject_excessive_json_nesting(
    document: str,
    *,
    maximum: int = DEFAULT_MAX_JSON_NESTING,
) -> None:
    """Bound JSON structure depth independently of Python's recursion setting."""

    depth = 0
    in_string = False
    escaped = False
    for character in document:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > maximum:
                raise DesktopIngressError("invalid_request_json")
        elif character in "]}":
            depth -= 1


def parse_chat_stream_document(
    body: bytes,
    *,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    max_json_nesting: int = DEFAULT_MAX_JSON_NESTING,
) -> dict[str, Any]:
    """Bytes to a JSON object, refusing everything ambiguous on the way.

    Four gates, in this order, because each is cheaper than the next and
    each makes the next one's failure mode smaller: size, then depth, then
    parse, then "is it even an object".

    :raises DesktopIngressError: with ``request_document_too_large`` (413) or
        ``invalid_request_json`` (422).
    """
    if len(body) > max_request_bytes:
        raise DesktopIngressError("request_document_too_large", status_code=413)
    try:
        document_text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DesktopIngressError("invalid_request_encoding", status_code=400) from exc
    _reject_excessive_json_nesting(document_text, maximum=max_json_nesting)
    try:
        document = json.loads(
            document_text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise DesktopIngressError("invalid_request_json") from exc
    if not isinstance(document, dict):
        raise DesktopIngressError("invalid_request_json")
    return document


@dataclass(frozen=True, slots=True)
class ChatStreamRequest:
    """The implemented subset of ``POST /chat/stream``'s published body.

    A frozen dataclass rather than a ``pydantic`` model, so the request can
    be decoded and tested where no optional dependency is installed.

    Fields the client's body carries that this backend has nowhere to put —
    ``model``, ``effort``, ``thinking``, ``context_1m``, ``output_style``,
    ``thread_id``, ``stage`` — are **accepted and ignored**. Rejecting them
    would break a client that is allowed to send them; acting on them would
    be inventing behaviour for a field this layer does not model.
    """

    content: str
    session_id: str
    source_request_id: str
    installation_id: str = ""
    workspace: str = ""
    values: Mapping[str, object] = field(default_factory=dict)
    permission_profile: str = ""
    """One of :data:`PERMISSION_PROFILES`, or ``""`` when the body named
    none and the session keeps the profile it has."""
    resume: bool = False
    """Reattach to the exchange ``source_request_id`` already started on
    ``session_id``, never start one. ``content`` is ``""`` and not read."""

    @property
    def source_namespace(self) -> str:
        """``desktop/v1/{installation}/{profile}``."""
        return ingress_identity(self.installation_id)[2]

    def to_inbound(self) -> InboundMessage:
        """The one thing this whole module exists to produce.

        The idempotency key is **namespace-qualified**:
        :meth:`~omicsclaw.entry.session.SessionRegistry.submit` keys on the
        session and the id alone, so the namespace is folded into the key
        here. Two
        installations that happened to mint the same 32-hex id would
        otherwise resolve to each other's exchange — a redelivery that
        answers a different person's question.
        """
        return InboundMessage(
            text=self.content,
            session_id=self.session_id,
            source_request_id=(
                f"{self.source_namespace}/{self.source_request_id}"
                if self.source_request_id
                else ""
            ),
            sender=DESKTOP_PROFILE_ID,
            surface=DESKTOP_SURFACE,
            values=dict(self.values),
        )


def ingress_identity(installation_id: str) -> tuple[str, str, str]:
    """Derive the local Desktop identity without accepting an Owner partition.

    An absent installation is ``"local"`` and the profile is always
    ``"owner"`` whatever the request said.
    """
    installation = installation_id or "local"
    profile = DESKTOP_PROFILE_ID
    return installation, profile, f"desktop/v1/{installation}/{profile}"


def _string(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DesktopIngressError("invalid_request_json")
    return value


def decode_chat_stream_request(
    document: Mapping[str, Any],
    *,
    require_source_request_id: bool = True,
) -> ChatStreamRequest:
    """Validate one parsed body and refuse what this route does not serve.

    The refusal codes are published: a client branches on the ``detail``
    of the error response. Order matters only in that the attachment
    refusals come first: files the caller believed were uploaded are
    refused *unconditionally*, before any question about identity or
    runtime, rather than silently dropped.

    ``ingress_schema_version`` is required and must equal
    :data:`~omicsclaw.entry.desktop.wire_contract.DESKTOP_CHAT_REQUEST_SCHEMA_VERSION`;
    a body without it, or with another value, is refused with
    ``unsupported_ingress_schema_version`` (422).

    ``resume``, when present, must be a boolean (``invalid_resume``). A
    resuming body needs no ``content``, and any it carries is dropped.

    :raises DesktopIngressError: never returns a partially-accepted request.
    """
    if document.get("files"):
        raise DesktopIngressError("attachments_not_supported", status_code=409)
    if document.get("file_selections") or document.get("attachment_descriptors"):
        raise DesktopIngressError("file_references_not_supported", status_code=409)
    if _string(document, "job_id").strip():
        raise DesktopIngressError(
            "remote_job_binding_not_supported", status_code=409
        )
    if document.get("provider_config") is not None:
        raise DesktopIngressError(
            "per_turn_provider_credentials_not_supported", status_code=409
        )

    version = document.get("ingress_schema_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != DESKTOP_CHAT_REQUEST_SCHEMA_VERSION
    ):
        raise DesktopIngressError("unsupported_ingress_schema_version")

    resume = document.get("resume", False)
    if not isinstance(resume, bool):
        raise DesktopIngressError("invalid_resume")

    content = "" if resume else _string(document, "content")
    if not content and not resume:
        raise DesktopIngressError("content_required")

    source_request_id = _string(document, "source_request_id")
    installation_id = _string(document, "installation_id")
    for name, value in (
        ("source_request_id", source_request_id),
        ("installation_id", installation_id),
    ):
        if len(value) > 32 or _OPAQUE_ID.match(value) is None:
            raise DesktopIngressError(f"invalid_{name}")
    if require_source_request_id and not source_request_id:
        # The contract declares the field required and declares redelivery
        # idempotent; those are one promise, and a
        # request with no key cannot be given the second half of it.
        raise DesktopIngressError("source_request_id_required")

    permission_profile = _string(document, "permission_profile")
    if permission_profile and permission_profile not in PERMISSION_PROFILES:
        raise DesktopIngressError("invalid_permission_profile")

    session_id = _string(document, "session_id") or uuid.uuid4().hex
    return ChatStreamRequest(
        content=content,
        session_id=session_id,
        source_request_id=source_request_id,
        installation_id=installation_id,
        workspace=_string(document, "workspace"),
        values={"surface": DESKTOP_SURFACE, "installation_id": installation_id},
        permission_profile=permission_profile,
        resume=resume,
    )
