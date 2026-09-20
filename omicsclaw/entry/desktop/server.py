"""Two routes: ``POST /chat/stream`` and ``GET /health``.

Plan 0031 §5.2, task D2. ``surfaces/desktop/server.py`` is 9,454 lines and
mounts several dozen routes; this module mounts the two the plan admits, and
the reason the other routes are absent is not that they are bad — it is that
they belong to the Run governance family, the persistent memory family and
the MCP/outputs/bridge proxies, each of which is somebody else's step.
:data:`~omicsclaw.entry.desktop.wire_contract.SERVED_PATHS` names what is
here so the four contract descriptors cannot be mistaken for four
implementations.

**Two halves, and only one of them needs a web framework.** Everything above
the HTTP boundary — parse, admit, submit, project, render — is
:func:`open_chat_stream` and :func:`health_payload`, both plain ``async def``
over plain dictionaries and both fully tested. :func:`create_desktop_app` is
the adapter that puts them behind FastAPI, and it imports FastAPI **inside
the function body** (plan 0031 trap 13). That is not a style choice: the
dependency is not installed on this machine, and ``import
omicsclaw.entry.desktop`` has to succeed anyway, or the wire contract this
package exists to publish would only be inspectable where a web server
happens to be installed.

**What this route does not do that the original did.** No provider switching
per request, no per-turn credentials, no title generation, no skill-log
bridge, no ``ControlRuntime`` ticket. A chat request selects nothing about
how the agent is configured; it carries a sentence and an idempotency key.
"""

from __future__ import annotations

import logging
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping

from omicsclaw.entry.assembly import AgentApp
from omicsclaw.entry.ingress import SenderPolicy
from omicsclaw.entry.session import QueueFull, RegistryClosed, SubmissionRefused
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.version import __version__

from .turn_observation import KEEPALIVE_INTERVAL_S, DesktopChatSSEBody
from .turn_submission import (
    DEFAULT_MAX_REQUEST_BYTES,
    DesktopIngressError,
    decode_chat_stream_request,
    parse_chat_stream_document,
)
from .wire_contract import (
    SERVED_PATHS,
    desktop_chat_contract,
    desktop_run_contract,
    desktop_turn_observation_contract,
    desktop_turn_submission_contract,
)

__all__ = [
    "BACKEND_PROCESS_EPOCH",
    "SSE_HEADERS",
    "ChatStream",
    "create_desktop_app",
    "health_payload",
    "open_chat_stream",
]

_log = logging.getLogger(__name__)

BACKEND_PROCESS_EPOCH: Final = secrets.token_hex(32)
"""A nonce minted once per process, reported by ``/health``.

``server.py:194``, unchanged. A desktop client compares it across polls to
notice that the backend it is talking to has been restarted — which
invalidates every ``turn_id`` it is holding, since this rebuild's session
store is in memory (plan 0031 Q4).
"""

SSE_HEADERS: Final[Mapping[str, str]] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
"""``server.py:3292-3296``. ``X-Accel-Buffering`` is the one that is easy to
drop and expensive to miss: an nginx in front of the backend buffers the
whole response without it, which turns a token-by-token stream into one
silent wait followed by the complete answer."""


@dataclass(frozen=True, slots=True)
class ChatStream:
    """An admitted request: which exchange it resolved to, and its frames."""

    turn_id: str
    session_id: str
    body: DesktopChatSSEBody
    resumed: bool
    """Whether this request was a redelivery that resolved to an exchange
    already in flight (``durable_ingress_idempotency``) rather than starting
    one. The two are indistinguishable to the client by design — it gets a
    stream either way — but a log line that cannot tell them apart cannot
    answer "did the retry double the work"."""


async def open_chat_stream(
    app: AgentApp,
    document: Mapping[str, Any],
    *,
    policy: SenderPolicy | None = None,
    after_seq: int = 0,
    keepalive_s: float | None = KEEPALIVE_INTERVAL_S,
) -> ChatStream:
    """Admit one parsed request and return the stream of its frames.

    The whole of ``/chat/stream`` above the HTTP boundary, in one function
    with no framework in its signature, so that the projection can be tested
    without a web server and the route below stays thin enough to read.

    *after_seq* is the resume cursor. The published body has no field for
    it — ``route.ts`` never sends one — so it is a caller-side parameter and
    defaults to "everything the ring still holds". It exists because
    :meth:`~omicsclaw.entry.turn.TurnHandle.observe` may be called any number
    of times over one exchange (Q14), which is what makes a reconnect a
    second cursor rather than a second exchange.

    :raises DesktopIngressError: the request was refused. No exchange is
        created on any refusal path — including the sender policy's, which
        plan 0031 §9-9(b) requires to produce *no turn* rather than a
        politely-worded one.
    :raises RuntimeError: the app has no session registry, which means
        :func:`~omicsclaw.entry.attach_sessions` was never called.
    """
    request = decode_chat_stream_request(document)

    if request.workspace.strip():
        declared = Path(request.workspace).resolve()
        if declared != Path(app.config.workspace).resolve():
            # ``server.py:2091-2102``. A request naming a different workspace
            # is not a request this backend can serve; answering it from the
            # configured one would run tools against files the caller did
            # not mean.
            raise DesktopIngressError(
                "workspace_does_not_match_backend_runtime", status_code=409
            )

    inbound = request.to_inbound()
    if policy is not None and not policy.admits(inbound):
        _log.warning("desktop ingress refused a sender outside the allowlist")
        raise DesktopIngressError("sender_not_allowed", status_code=403)

    registry = app.sessions
    if registry is None:
        raise RuntimeError(
            "this AgentApp has no session registry; call attach_sessions(app) "
            "before serving /chat/stream"
        )

    known = _retained_handle(
        registry, inbound.session_id, inbound.source_request_id
    )
    handle: TurnHandle = await registry.deliver(inbound)
    observation = handle.observe(after_seq=after_seq)
    return ChatStream(
        turn_id=handle.turn_id,
        session_id=handle.session_id,
        resumed=known is handle and known is not None,
        body=DesktopChatSSEBody(
            observation, keepalive_s=keepalive_s, after_seq=after_seq
        ),
    )


def _retained_handle(
    registry: Any, session_id: str, source_request_id: str
) -> TurnHandle | None:
    """Whether this idempotency key is already bound, without submitting.

    Reaches for the registry's private index because the public surface has
    no "have you seen this key" question and inventing one on
    :class:`~omicsclaw.entry.session.SessionRegistry` for a log line would
    be the wrong trade. Missing attribute tolerated: this is observability,
    and observability may not be the reason a request fails.

    Keyed by session *and* request id, which is how the registry keys it:
    a client is free to number its requests per conversation, and a lookup
    that ignored the session would report one conversation's redelivery
    against another conversation's exchange.
    """
    if not source_request_id:
        return None
    index = getattr(registry, "_by_request", None)
    if not isinstance(index, dict):  # pragma: no cover - a registry variant
        return None
    return index.get((session_id, source_request_id))


def health_payload(app: AgentApp) -> dict[str, Any]:
    """What ``GET /health`` answers. Pure, so a test needs no HTTP.

    The four contract descriptors are the point of this route: a client
    checks them before it speaks, and a version it does not recognise is
    how it discovers a backend older than itself rather than by parsing a
    frame it cannot read (Q24).

    ``model`` comes from :class:`~omicsclaw.entry.config.AppConfig` and
    not from the provider: :class:`~omicsclaw.provider.LLMProvider`
    publishes ``name``, ``generate``, ``generate_stream`` and ``bind``,
    so ``app.provider.model`` was an :exc:`AttributeError` that made this
    route answer 500. ``""`` means the deployment named no model and the
    provider layer will detect one.

    **The last four keys are not decoration.** ``backend-health.ts:199-210``
    treats a payload carrying *any* of ``provider`` / ``model`` /
    ``skills_count`` / ``python_executable`` / ``skill_python_executable``
    / ``omicsclaw_dir`` / ``launch_id`` as the *current* wire shape and
    then requires **all seven** (``:230-239``); a payload with the first
    three alone is rejected as ``invalid-payload`` by every validating
    client, and a managed Electron launch additionally refuses a
    ``launch_id`` that is not the one it passed (``:313``). Three of the
    four are this process's own facts; the fourth is
    :attr:`~omicsclaw.entry.config.AppConfig.launch_id`, which
    :func:`~omicsclaw.entry.config.resolve_app_config` reads.

    ``skill_python_executable`` is this interpreter, because this rebuild
    runs no skill in a subprocess: ``use_skill`` reads a ``SKILL.md`` into
    the conversation. The key is answered rather than omitted because
    omitting it fails the shape check, and answering it with a second
    interpreter this deployment does not have would be worse.
    ``omicsclaw_dir`` is the workspace, which is what every path this
    deployment resolves — skills, ``.mcp.json``, ``SOUL.md`` — is
    resolved against.
    """
    return {
        "status": "ok",
        "version": __version__,
        "backend_process_epoch": BACKEND_PROCESS_EPOCH,
        "provider": app.provider.name,
        "model": app.config.model,
        "skills_count": len(app.skills.skills),
        "python_executable": sys.executable,
        "skill_python_executable": sys.executable,
        "omicsclaw_dir": str(app.config.workspace),
        "launch_id": app.config.launch_id,
        "served_paths": list(SERVED_PATHS),
        "contracts": {
            "desktop_chat": desktop_chat_contract(),
            "desktop_run": desktop_run_contract(),
            "desktop_turn_observation": desktop_turn_observation_contract(),
            "desktop_turn_submission": desktop_turn_submission_contract(),
        },
    }


def unauthenticated_health_payload(launch_id: str = "") -> dict[str, Any]:
    """The reduced answer given to an unauthenticated ``/health`` probe.

    ``server.py:4635-4641``. A desktop launcher polls this route to learn
    whether the backend is up *and* whether it needs a token, before it has
    one; answering it with provider and model would publish the deployment's
    configuration to anybody who can reach the port.

    ``launch_id`` is the one field the original kept on this reduced form
    and it is kept here for the same reason: it is how a launcher tells
    *its own* child from a leftover backend squatting the port, and that
    question has to be answerable before the token is. It is not a secret
    — the launcher minted it — so publishing it costs nothing.
    """
    return {
        "status": "ok",
        "version": __version__,
        "launch_id": launch_id,
        "auth_required": True,
    }


def create_desktop_app(
    app: AgentApp,
    *,
    policy: SenderPolicy | None = None,
    bearer_token: str = "",
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    keepalive_s: float | None = KEEPALIVE_INTERVAL_S,
) -> Any:
    """Build the FastAPI application serving :data:`SERVED_PATHS`.

    ``fastapi`` is imported **here**, not at module scope, so that
    ``import omicsclaw.entry.desktop`` succeeds in an environment that has
    no web framework — which is this repository's own test environment, and
    is also every environment that only wants to read the wire contract
    (plan 0031 trap 13).

    ``bearer_token=""`` leaves the routes unauthenticated, which is only
    defensible on a loopback bind; a non-empty token is compared with
    :func:`secrets.compare_digest`, because a string ``==`` on a secret
    leaks its prefix through timing.
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse

    api = FastAPI(title="OmicsClaw Desktop", version=__version__)

    def _authorized(request: Request) -> bool:
        if not bearer_token:
            return True
        header = request.headers.get("authorization", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer":
            return False
        return secrets.compare_digest(presented.strip(), bearer_token)

    async def _read_body(request: Request) -> bytes:
        """Read the body with a running cap, refusing a lie in the header.

        Both halves come from ``surfaces/desktop/turn_submission.py`` — the
        **pre-port** file, not the 339-line sibling of the same name in this
        package. ``:491-504`` refuses a declared ``Content-Length`` over the
        limit before a byte is read; ``:425-436``
        (``_bounded_request_stream``) keeps a running total anyway, because
        the declaration is the client's claim and the bytes are the fact.
        """
        declared = request.headers.getlist("content-length")
        if len(declared) > 1:
            raise DesktopIngressError("invalid_content_length", status_code=400)
        if declared:
            try:
                length = int(declared[0])
            except ValueError as exc:
                raise DesktopIngressError(
                    "invalid_content_length", status_code=400
                ) from exc
            if length < 0:
                raise DesktopIngressError("invalid_content_length", status_code=400)
            if length > max_request_bytes:
                raise DesktopIngressError(
                    "request_document_too_large", status_code=413
                )
        chunks: list[bytes] = []
        observed = 0
        async for chunk in request.stream():
            observed += len(chunk)
            if observed > max_request_bytes:
                raise DesktopIngressError(
                    "request_document_too_large", status_code=413
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @api.post("/chat/stream")
    async def chat_stream(request: Request) -> Any:
        if not _authorized(request):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        try:
            body = await _read_body(request)
            document = parse_chat_stream_document(
                body, max_request_bytes=max_request_bytes
            )
            after_seq = _after_seq(document)
            stream = await open_chat_stream(
                app, document, policy=policy, after_seq=after_seq,
                keepalive_s=keepalive_s,
            )
        except DesktopIngressError as exc:
            return JSONResponse({"detail": exc.code}, status_code=exc.status_code)
        except QueueFull:
            return JSONResponse({"detail": "queue_full"}, status_code=429)
        except RegistryClosed:
            return JSONResponse({"detail": "shutting_down"}, status_code=503)
        except SubmissionRefused:  # pragma: no cover - a future subclass
            return JSONResponse({"detail": "submission_refused"}, status_code=429)

        async def frames() -> Any:
            # ``async with`` rather than a bare ``async for``: a client that
            # disconnects interrupts this generator, and the observation it
            # was holding has to be detached or the exchange never learns
            # that nobody is watching (plan 0031 trap 9).
            async with stream.body as body_iter:
                async for frame in body_iter:
                    yield frame

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={
                **SSE_HEADERS,
                "X-OmicsClaw-Turn-Id": stream.turn_id,
                "X-OmicsClaw-Session-Id": stream.session_id,
            },
        )

    @api.api_route("/health", methods=["GET", "HEAD"], name="health")
    async def health(request: Request) -> Any:
        if bearer_token and not request.headers.getlist("authorization"):
            return unauthenticated_health_payload(app.config.launch_id)
        if not _authorized(request):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return health_payload(app)

    return api


def _after_seq(document: Mapping[str, Any]) -> int:
    """Read the optional resume cursor, refusing anything that is not one.

    Not in the published body — a client that never sends it resumes from
    the oldest frame the ring still holds, which is the right answer for a
    fresh tab. It is read here rather than invented in the route so that
    both halves of the module agree on what a bad value means.
    """
    value = document.get("after_seq", 0)
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DesktopIngressError("invalid_after_seq")
    return value
