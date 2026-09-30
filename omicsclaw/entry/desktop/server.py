"""The Desktop HTTP routes, and the plain functions behind them.

Routes (see :data:`~omicsclaw.entry.desktop.wire_contract.SERVED_PATHS`):

* ``POST /chat/stream`` — admit one chat message and stream its frames;
* ``POST /chat/permission`` — answer one ``permission_request``;
* ``POST /chat/abort`` — cancel the exchange a stream request started;
* ``POST /chat/session-permission-profile`` — put a session in the
  ``default`` or ``full_access`` permission profile;
* ``GET /workspace`` — the workspace this process serves;
* ``PUT /workspace`` — accepted only for that same workspace, since a
  process serves one workspace and changing it means a restart;
* ``GET /env/doctor`` — a checklist of what this backend was assembled
  with (:mod:`~omicsclaw.entry.desktop.doctor`);
* ``GET``/``HEAD /health`` — process facts and the wire contract;
* ``GET /skills`` and ``GET /skills/{domain}/{name}`` — the skill index
  (:mod:`~omicsclaw.entry.desktop.catalog`);
* ``GET /mcp/servers`` — the MCP servers and their connection state
  (:mod:`~omicsclaw.entry.desktop.catalog`);
* ``GET``/``PUT /providers`` and ``POST /providers/test`` — the model
  backend the deployment's ``.env`` configures
  (:mod:`~omicsclaw.entry.desktop.providers`);
* ``POST /chat/title`` — a title for a session's first message
  (:mod:`~omicsclaw.entry.desktop.title`);
* ``GET /files/tree`` and ``GET /files/serve`` — read-only views of the
  workspace's files (:mod:`~omicsclaw.entry.desktop.files`).

A ``/chat/stream`` message whose content is exactly ``/compact`` compacts
the session's history instead of being sent to the model. A
``/chat/stream`` body with ``resume: true`` reattaches to the exchange
its ``source_request_id`` started and never starts one.

Every write route requires ``Content-Type: application/json`` and answers
415 ``unsupported_media_type`` otherwise, including when the header is
missing. A cross-origin page can send a ``text/plain`` request to a
loopback port without a CORS preflight, but not a JSON one, and this
server grants no CORS. A refused request is answered as
``{"detail": <code>}`` with the code's status.

Everything above the HTTP boundary — :func:`open_chat_stream`,
:func:`health_payload`, :func:`workspace_payload`,
:func:`change_workspace`, the functions in
:mod:`~omicsclaw.entry.desktop.interactions` and
:func:`~omicsclaw.entry.desktop.doctor.doctor_report` — is plain ``async def`` or
``def`` over plain dictionaries. :func:`create_desktop_app` is the adapter
that puts them behind FastAPI, and it imports FastAPI **inside the
function body**, so ``import omicsclaw.entry.desktop`` succeeds where no
web framework is installed.

This module does **not** enable ``from __future__ import annotations``.
The routes are defined inside :func:`create_desktop_app`, where
``Request`` is a local name; with postponed evaluation FastAPI would see
the string ``"Request"``, fail to resolve it in this module's globals and
treat the parameter as a required query parameter, so every route would
answer 422.
"""

import asyncio
import logging
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping

from omicsclaw.entry.assembly import AgentApp
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.ingress import SenderPolicy
from omicsclaw.entry.session import (
    QueueFull,
    RegistryClosed,
    SessionRegistry,
    SubmissionRefused,
)
from omicsclaw.entry.stream import ObserverCapacityError, TurnObservation
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.version import __version__

from .catalog import mcp_servers, skill_catalog, skill_detail
from .doctor import doctor_report, effective_model
from .files import (
    byte_span,
    content_disposition,
    file_chunks,
    file_tree,
    open_served_file,
    serve_target,
    tree_depth,
)
from .interactions import (
    DesktopInteractions,
    abort_chat,
    answer_permission,
    change_permission_profile,
)
from .providers import SettingsFile, provider_listing, save_provider, test_provider
from .title import generate_title
from .turn_observation import KEEPALIVE_INTERVAL_S, DesktopChatSSEBody
from .turn_submission import (
    DEFAULT_MAX_REQUEST_BYTES,
    DesktopIngressError,
    decode_chat_stream_request,
    parse_chat_stream_document,
)
from .wire_contract import SERVED_PATHS, desktop_chat_contract

__all__ = [
    "BACKEND_PROCESS_EPOCH",
    "COMPACT_COMMAND",
    "CONTROL_MAX_REQUEST_BYTES",
    "SSE_HEADERS",
    "ChatStream",
    "change_workspace",
    "create_desktop_app",
    "health_payload",
    "is_json_media_type",
    "open_chat_stream",
    "workspace_payload",
]

_log = logging.getLogger(__name__)

BACKEND_PROCESS_EPOCH: Final = secrets.token_hex(32)
"""A nonce minted once per process, reported by ``/health``.

A desktop client compares it across polls to notice that the backend it is
talking to has been restarted — which invalidates every ``turn_id`` and
``request_id`` it is holding, since sessions' exchanges live in memory.
"""

CONTROL_MAX_REQUEST_BYTES: Final = 64 * 1024
"""Largest body ``/chat/permission``, ``/chat/abort``,
``/chat/session-permission-profile``, ``PUT /workspace``,
``PUT /providers``, ``POST /providers/test`` and ``POST /chat/title``
will read."""

COMPACT_COMMAND: Final = "/compact"
"""A ``/chat/stream`` content that compacts the session instead of asking
the model. Surrounding whitespace is ignored; anything else is a message."""

SSE_HEADERS: Final[Mapping[str, str]] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
"""``X-Accel-Buffering`` is the one that is easy to drop and expensive to
miss: an nginx in front of the backend buffers the whole response without
it, which turns a token-by-token stream into one silent wait followed by
the complete answer."""


@dataclass(frozen=True, slots=True)
class ChatStream:
    """An admitted request: which exchange it resolved to, and its frames."""

    turn_id: str
    session_id: str
    body: DesktopChatSSEBody
    resumed: bool
    """Whether this request resolved to an exchange already started, by
    ``resume`` or by redelivering its ``source_request_id``, rather than
    starting one."""


async def open_chat_stream(
    app: AgentApp,
    document: Mapping[str, Any],
    *,
    policy: SenderPolicy | None = None,
    after_seq: int = 0,
    keepalive_s: float | None = KEEPALIVE_INTERVAL_S,
    interactions: DesktopInteractions | None = None,
) -> ChatStream:
    """Admit one parsed request and return the stream of its frames.

    The whole of ``/chat/stream`` above the HTTP boundary, with no
    framework in its signature.

    *after_seq* is the resume cursor, the body's ``after_seq`` as the HTTP
    route reads it; it defaults to "everything the ring still holds". A
    redelivered ``source_request_id`` on the same session resolves to the
    same exchange, and a new observation over it is opened at that
    cursor.

    With ``resume: true`` in the body, the exchange is found by
    ``(session_id, source_request_id)`` alone and observed from
    *after_seq*; ``content`` and ``permission_profile`` are not read, and
    nothing is started or queued, so a restarted backend or an exchange no
    longer retained can never turn a reconnect into a second run of the
    message.

    *interactions* is the server's
    :class:`~omicsclaw.entry.desktop.interactions.DesktopInteractions`:
    the request is recorded in it so ``/chat/abort`` can find the
    exchange, a ``permission_profile`` in the body is applied to the
    session in it before the exchange starts, and the body consults it for
    session grants and ``full_access``. ``None`` uses a fresh one that
    nothing else shares.

    Content equal to :data:`COMPACT_COMMAND` queues
    :meth:`~omicsclaw.entry.SessionRegistry.compact` for the session
    rather than a message; a redelivered ``source_request_id`` resolves
    to the same compaction while it is retained.

    :raises DesktopIngressError: the request was refused. No exchange is
        created on any refusal path, including the sender policy's. A
        resume that finds no retained exchange is 409
        ``exchange_not_retained``; an exchange that already has as many
        observers as it allows is 429 ``too_many_observers``.
    :raises RuntimeError: the app has no session registry, which means
        :func:`~omicsclaw.entry.attach_sessions` was never called.
    """
    request = decode_chat_stream_request(document)

    if request.workspace.strip() and not _same_workspace(
        request.workspace, app.config.workspace
    ):
        # A request naming a different workspace is not one this backend
        # can serve; answering it from the configured one would run tools
        # against files the caller did not mean.
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
    if interactions is None:
        interactions = DesktopInteractions(app)

    if request.resume:
        handle = _retained_exchange(
            registry,
            interactions.turn_for(request.session_id, request.source_request_id),
        )
        return ChatStream(
            turn_id=handle.turn_id,
            session_id=handle.session_id,
            resumed=True,
            body=_observed_body(
                app, handle, after_seq, keepalive_s, interactions
            ),
        )

    if request.permission_profile:
        interactions.set_permission_profile(
            request.session_id, request.permission_profile
        )

    known = interactions.turn_for(request.session_id, request.source_request_id)
    compacting = request.content.strip() == COMPACT_COMMAND
    handle: TurnHandle
    if compacting:
        handle = await _compaction(registry, request.session_id, known)
    else:
        handle = await registry.deliver(inbound)
    interactions.remember_request(
        handle.session_id, request.source_request_id, handle.turn_id
    )
    return ChatStream(
        turn_id=handle.turn_id,
        session_id=handle.session_id,
        resumed=known == handle.turn_id,
        body=_observed_body(app, handle, after_seq, keepalive_s, interactions),
    )


def _retained_exchange(registry: SessionRegistry, turn_id: str | None) -> TurnHandle:
    """The exchange a resume names, if the registry still retains it.

    :raises DesktopIngressError: 409 ``exchange_not_retained`` otherwise.
    """
    if turn_id is not None:
        try:
            return registry.handle(turn_id)
        except KeyError:
            pass
    raise DesktopIngressError("exchange_not_retained", status_code=409)


def _observed_body(
    app: AgentApp,
    handle: TurnHandle,
    after_seq: int,
    keepalive_s: float | None,
    interactions: DesktopInteractions,
) -> DesktopChatSSEBody:
    """A new SSE body over *handle*, observed from *after_seq*.

    A compaction exchange is handed to the body so that it reports its
    outcome, unless the ``COMPACTION`` event that already reported it is
    at or before the cursor.

    :raises DesktopIngressError: 429 ``too_many_observers``.
    """
    observation = _observe(handle, after_seq)
    compaction = handle if handle.compaction_only else None
    if compaction is not None and any(
        event.type is TurnEventType.COMPACTION and event.seq <= after_seq
        for event in handle.stream.retained()
    ):
        compaction = None
    return DesktopChatSSEBody(
        observation,
        keepalive_s=keepalive_s,
        after_seq=after_seq,
        approvals=handle.approvals,
        interactions=interactions,
        provider=app.provider.name,
        model=effective_model(app),
        compaction=compaction,
    )


def _observe(handle: TurnHandle, after_seq: int) -> TurnObservation:
    try:
        return handle.observe(after_seq=after_seq)
    except ObserverCapacityError as exc:
        raise DesktopIngressError("too_many_observers", status_code=429) from exc


async def _compaction(
    registry: SessionRegistry, session_id: str, known: str | None
) -> TurnHandle:
    """The compaction *known* names if it is still retained, else a new one."""
    if known is not None:
        try:
            handle: TurnHandle = registry.handle(known)
        except KeyError:
            pass
        else:
            if handle.compaction_only:
                return handle
    return await registry.compact(session_id)


def health_payload(app: AgentApp) -> dict[str, Any]:
    """What ``GET /health`` answers. Pure, so a test needs no HTTP.

    ``contracts.desktop_chat`` is the wire contract; a client checks its
    versions before it speaks, and refuses a backend whose versions it
    does not implement. Its ``abandon_grace_s`` is the session registry's,
    ``None`` for an app without one.

    ``provider``, ``model``, ``skills_count``, ``python_executable``,
    ``skill_python_executable``, ``omicsclaw_dir`` and ``launch_id`` are
    all required by the desktop client's health validator: a payload with
    any of them must carry every one. ``model`` is the model the provider
    calls (:func:`~omicsclaw.entry.desktop.doctor.effective_model`), not
    only the one the deployment named.
    ``skill_python_executable`` is this interpreter, because no skill runs
    in a subprocess of its own. ``omicsclaw_dir`` is the workspace, which
    skills (unless ``skills_dir`` is set) and ``.mcp.json`` are resolved
    against. ``launch_id`` is
    :attr:`~omicsclaw.entry.config.AppConfig.launch_id`, which a managed
    launch compares with the id it passed.
    """
    return {
        "status": "ok",
        "version": __version__,
        "backend_process_epoch": BACKEND_PROCESS_EPOCH,
        "provider": app.provider.name,
        "model": effective_model(app),
        "skills_count": len(app.skills.skills),
        "python_executable": sys.executable,
        "skill_python_executable": sys.executable,
        "omicsclaw_dir": str(app.config.workspace),
        "launch_id": app.config.launch_id,
        "served_paths": list(SERVED_PATHS),
        "contracts": {
            "desktop_chat": desktop_chat_contract(
                abandon_grace_s=(
                    app.sessions.abandon_grace_s if app.sessions is not None else None
                )
            )
        },
    }


def unauthenticated_health_payload(launch_id: str = "") -> dict[str, Any]:
    """The reduced answer given to an unauthenticated ``/health`` probe.

    A desktop launcher polls this route to learn whether the backend is up
    *and* whether it needs a token, before it has one; answering it with
    provider and model would publish the deployment's configuration to
    anybody who can reach the port. ``launch_id`` is kept because it is how
    a launcher tells its own child from a leftover backend squatting the
    port; the launcher minted it, so publishing it costs nothing.
    """
    return {
        "status": "ok",
        "version": __version__,
        "launch_id": launch_id,
        "auth_required": True,
    }


def workspace_payload(app: AgentApp) -> dict[str, Any]:
    """What ``GET /workspace`` answers: ``{workspace, trusted_dirs}``.

    ``trusted_dirs`` is always ``[]``.
    """
    return {"workspace": str(app.config.workspace), "trusted_dirs": []}


def change_workspace(app: AgentApp, document: Mapping[str, Any]) -> dict[str, Any]:
    """``PUT /workspace``: accept ``{workspace}`` naming the current one.

    Two spellings of one directory (``~``, ``..``, a trailing slash, a
    symlink) are the same workspace. Returns :func:`workspace_payload`.

    :raises DesktopIngressError: 422 ``workspace_required`` when
        ``workspace`` is missing or empty; 422 ``invalid_workspace`` when
        it is not a resolvable path; 409
        ``workspace_change_requires_restart`` when it names another
        directory.
    """
    declared = document.get("workspace")
    if not isinstance(declared, str) or not declared.strip():
        raise DesktopIngressError("workspace_required")
    if not _same_workspace(declared, app.config.workspace):
        raise DesktopIngressError(
            "workspace_change_requires_restart", status_code=409
        )
    return workspace_payload(app)


def _same_workspace(declared: str, workspace: Path | str) -> bool:
    """Whether the client's *declared* path names the served *workspace*.

    :raises DesktopIngressError: 422 ``invalid_workspace`` when *declared*
        cannot be resolved to a path at all: an embedded NUL, a ``~user``
        naming no user, or a symlink loop on Python versions whose
        :meth:`~pathlib.Path.resolve` raises for one.
    """
    try:
        resolved = Path(declared.strip()).expanduser().resolve()
    except (ValueError, OSError, RuntimeError) as exc:
        raise DesktopIngressError("invalid_workspace") from exc
    return resolved == Path(workspace).expanduser().resolve()


def is_json_media_type(content_type: str) -> bool:
    """Whether a ``Content-Type`` value names ``application/json``.

    The media type is the part before the first ``;``, stripped and
    compared case-insensitively; parameters such as ``charset`` are
    allowed. ``application/jsonx`` and ``text/application/json`` are not
    JSON.
    """
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json"


def create_desktop_app(
    app: AgentApp,
    *,
    policy: SenderPolicy | None = None,
    bearer_token: str = "",
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    keepalive_s: float | None = KEEPALIVE_INTERVAL_S,
    interactions: DesktopInteractions | None = None,
    settings: SettingsFile | None = None,
) -> Any:
    """Build the FastAPI application serving :data:`SERVED_PATHS`.

    ``fastapi`` is imported here, not at module scope, so that ``import
    omicsclaw.entry.desktop`` succeeds in an environment that has no web
    framework.

    ``bearer_token=""`` leaves the routes unauthenticated, which is only
    defensible on a loopback bind; a non-empty token is compared with
    :func:`secrets.compare_digest`, because a string ``==`` on a secret
    leaks its prefix through timing.

    *interactions* defaults to a new
    :class:`~omicsclaw.entry.desktop.interactions.DesktopInteractions`
    shared by every route of this application.

    *settings* is the deployment's ``.env``
    (:class:`~omicsclaw.entry.desktop.providers.SettingsFile`). Without it
    ``PUT /providers`` and ``POST /providers/test`` answer 503
    ``settings_unavailable`` and ``GET /providers`` lists no provider as
    configured.

    :raises ModuleNotFoundError: ``fastapi`` is not installed.
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse

    api = FastAPI(title="OmicsClaw Desktop", version=__version__)
    shared = interactions if interactions is not None else DesktopInteractions(app)

    def _authorized(request: Request) -> bool:
        if not bearer_token:
            return True
        header = request.headers.get("authorization", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer":
            return False
        return secrets.compare_digest(presented.strip(), bearer_token)

    def _refused(exc: DesktopIngressError) -> Any:
        return JSONResponse({"detail": exc.code}, status_code=exc.status_code)

    def _unauthorized() -> Any:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)

    def _require_json(request: Request) -> None:
        declared = request.headers.getlist("content-type")
        if len(declared) != 1 or not is_json_media_type(declared[0]):
            raise DesktopIngressError("unsupported_media_type", status_code=415)

    async def _read_body(request: Request, limit: int) -> bytes:
        """Read the body with a running cap, refusing a lie in the header.

        A declared ``Content-Length`` over the limit is refused before a
        byte is read, and a running total is kept anyway, because the
        declaration is the client's claim and the bytes are the fact.
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
            if length > limit:
                raise DesktopIngressError(
                    "request_document_too_large", status_code=413
                )
        chunks: list[bytes] = []
        observed = 0
        async for chunk in request.stream():
            observed += len(chunk)
            if observed > limit:
                raise DesktopIngressError(
                    "request_document_too_large", status_code=413
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def _read_json(request: Request, limit: int) -> dict[str, Any]:
        _require_json(request)
        body = await _read_body(request, limit)
        return parse_chat_stream_document(body, max_request_bytes=limit)

    @api.post("/chat/stream")
    async def chat_stream(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, max_request_bytes)
            after_seq = _after_seq(document)
            stream = await open_chat_stream(
                app,
                document,
                policy=policy,
                after_seq=after_seq,
                keepalive_s=keepalive_s,
                interactions=shared,
            )
        except DesktopIngressError as exc:
            return _refused(exc)
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
            # that nobody is watching.
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

    @api.post("/chat/permission")
    async def chat_permission(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, CONTROL_MAX_REQUEST_BYTES)
            return await answer_permission(app, shared, document)
        except DesktopIngressError as exc:
            return _refused(exc)

    @api.post("/chat/abort")
    async def chat_abort(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, CONTROL_MAX_REQUEST_BYTES)
            return await abort_chat(app, shared, document)
        except DesktopIngressError as exc:
            return _refused(exc)

    @api.post("/chat/session-permission-profile")
    async def chat_session_permission_profile(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, CONTROL_MAX_REQUEST_BYTES)
            return await change_permission_profile(app, shared, document)
        except DesktopIngressError as exc:
            return _refused(exc)

    @api.get("/env/doctor")
    async def env_doctor(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        return doctor_report(app)

    @api.get("/workspace")
    async def get_workspace(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        return workspace_payload(app)

    @api.put("/workspace")
    async def put_workspace(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, CONTROL_MAX_REQUEST_BYTES)
            return change_workspace(app, document)
        except DesktopIngressError as exc:
            return _refused(exc)

    @api.get("/skills")
    async def skills(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        return skill_catalog(app)

    @api.get("/skills/{domain}/{name}")
    async def skill(request: Request, domain: str, name: str) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            return skill_detail(app, domain, name)
        except DesktopIngressError as exc:
            return _refused(exc)

    @api.get("/mcp/servers")
    async def mcp(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        startup = settings.startup if settings is not None else None
        return mcp_servers(app, startup=startup)

    @api.get("/providers")
    async def get_providers(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        return provider_listing(app, settings)

    @api.put("/providers")
    async def put_providers(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, CONTROL_MAX_REQUEST_BYTES)
            return save_provider(app, settings, document)
        except DesktopIngressError as exc:
            return _refused(exc)

    @api.post("/providers/test")
    async def providers_test(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, CONTROL_MAX_REQUEST_BYTES)
            return await test_provider(settings, document)
        except DesktopIngressError as exc:
            return _refused(exc)

    @api.post("/chat/title")
    async def chat_title(request: Request) -> Any:
        if not _authorized(request):
            return _unauthorized()
        try:
            document = await _read_json(request, CONTROL_MAX_REQUEST_BYTES)
        except DesktopIngressError as exc:
            return _refused(exc)
        status, payload = await generate_title(app, document)
        return JSONResponse(payload, status_code=status)

    def _nosniff(response: Any) -> Any:
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @api.get("/files/tree")
    async def files_tree(request: Request) -> Any:
        if not _authorized(request):
            return _nosniff(_unauthorized())
        query = request.query_params
        try:
            depth = tree_depth(query.get("depth"))
            payload = await asyncio.to_thread(
                file_tree, app.config.workspace, query.get("path"), depth=depth
            )
        except DesktopIngressError as exc:
            return _nosniff(_refused(exc))
        return _nosniff(JSONResponse(payload))

    @api.get("/files/serve")
    async def files_serve(request: Request) -> Any:
        if not _authorized(request):
            return _nosniff(_unauthorized())
        try:
            target = await asyncio.to_thread(
                serve_target, app.config.workspace, request.query_params.get("path", "")
            )
            opened = await asyncio.to_thread(open_served_file, target.path)
        except DesktopIngressError as exc:
            return _nosniff(_refused(exc))
        try:
            span = byte_span(request.headers.get("range"), opened.size)
        except DesktopIngressError as exc:
            opened.close()
            refused = _nosniff(_refused(exc))
            if exc.status_code == 416:
                refused.headers["Content-Range"] = f"bytes */{opened.size}"
            return refused
        headers = {
            "Content-Type": target.media_type,
            "Content-Length": str(span.length),
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": content_disposition(target.name),
            "X-Content-Type-Options": "nosniff",
        }
        if span.partial:
            headers["Content-Range"] = span.content_range
        return StreamingResponse(
            file_chunks(opened, span), status_code=span.status, headers=headers
        )

    @api.api_route("/health", methods=["GET", "HEAD"], name="health")
    async def health(request: Request) -> Any:
        if bearer_token and not request.headers.getlist("authorization"):
            return unauthenticated_health_payload(app.config.launch_id)
        if not _authorized(request):
            return _unauthorized()
        return health_payload(app)

    return api


def _after_seq(document: Mapping[str, Any]) -> int:
    """Read the optional resume cursor, refusing anything that is not one.

    A client that never sends it observes from the oldest frame the ring
    still holds, which is the right answer for a fresh tab.
    """
    value = document.get("after_seq", 0)
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DesktopIngressError("invalid_after_seq")
    return value
