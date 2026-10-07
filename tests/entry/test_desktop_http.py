"""The HTTP adapter: status codes, headers, media types and the bearer gate.

Needs ``fastapi`` (and ``httpx`` for its test client), so it runs under the
OmicsClaw interpreter and is skipped elsewhere. The logic behind each route
is tested without a web framework in ``test_desktop_ingress.py``,
``test_desktop_stream.py`` and ``test_desktop_interactions.py``; what is
left here is the adapter.

Starlette's ``TestClient`` reads a streaming response to its end before it
returns, so it is used only for requests that do not have to overlap a
live stream. The last test runs a real uvicorn on a free loopback port and
drives it with an async client, answering a ``permission_request`` and
stopping a running tool while their streams are open.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import socket
import time

import pytest

pytest.importorskip("fastapi", reason="the Desktop HTTP adapter needs it")
testclient = pytest.importorskip("fastapi.testclient")

from omicsclaw.entry.desktop import create_desktop_app  # noqa: E402
from omicsclaw.entry.desktop.wire_contract import SERVED_PATHS  # noqa: E402
from omicsclaw.entry.session import attach_sessions  # noqa: E402
from omicsclaw.schema import Message, Role  # noqa: E402
from tests.entry.test_turn_runner import (  # noqa: E402
    Asking,  # type: ignore[import-not-found]
    Scripted,
    Sleeping,
    calling,
    make_app,
)

KEY = "a" * 32
DONE = Message(role=Role.ASSISTANT, content="done")


def served(tmp_path: pathlib.Path, provider=None, tools=()):
    return attach_sessions(
        make_app(tmp_path, provider or Scripted(), tools=tools),
        abandon_grace_s=None,
    )


def client(tmp_path: pathlib.Path, **overrides):
    return testclient.TestClient(create_desktop_app(served(tmp_path), **overrides))


def body(**overrides) -> dict:
    document = {
        "ingress_schema_version": 3,
        "content": "hi",
        "session_id": "s1",
        "source_request_id": KEY,
    }
    document.update(overrides)
    return document


def framed(text: str) -> list[tuple[int | None, dict]]:
    """Each SSE frame of *text*: its ``id:`` if it has one, and its object."""
    found: list[tuple[int | None, dict]] = []
    for chunk in text.split("\n\n"):
        if not chunk.strip():
            continue
        lines = chunk.split("\n")
        event_id: int | None = None
        if lines[0].startswith("id: "):
            event_id = int(lines[0][len("id: ") :])
            lines = lines[1:]
        (line,) = lines
        found.append((event_id, json.loads(line[len("data: ") :])))
    return found


def frames_of(text: str) -> list[dict]:
    return [frame for _, frame in framed(text)]


def text_of(frames: list[dict]) -> str:
    return "".join(frame["data"] for frame in frames if frame["type"] == "text")


# ---- /health ------------------------------------------------------------


def test_health_publishes_contract_v3_and_the_served_paths(tmp_path: pathlib.Path):
    payload = client(tmp_path).get("/health").json()
    assert payload["status"] == "ok"
    assert set(payload["contracts"]) == {"desktop_chat"}
    chat = payload["contracts"]["desktop_chat"]
    assert chat["sse_schema_version"] == 3
    assert chat["request_schema_version"] == 3
    assert chat["abandon_grace_s"] is None
    assert payload["served_paths"] == list(SERVED_PATHS)


def test_health_answers_head(tmp_path: pathlib.Path):
    assert client(tmp_path).head("/health").status_code == 200


def test_health_without_a_token_says_only_that_one_is_needed(
    tmp_path: pathlib.Path,
):
    payload = client(tmp_path, bearer_token="s3cret").get("/health").json()
    assert payload == {
        "status": "ok",
        "version": payload["version"],
        "launch_id": "",
        "auth_required": True,
    }
    assert "provider" not in payload


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/chat/stream"),
        ("POST", "/chat/permission"),
        ("POST", "/chat/abort"),
        ("POST", "/chat/session-permission-profile"),
        ("GET", "/workspace"),
        ("PUT", "/workspace"),
        ("GET", "/env/doctor"),
        ("GET", "/health"),
        ("GET", "/skills"),
        ("GET", "/skills/spatial/spatial-de"),
        ("GET", "/mcp/servers"),
        ("GET", "/providers"),
        ("PUT", "/providers"),
        ("POST", "/providers/test"),
        ("POST", "/chat/title"),
        ("GET", "/files/tree"),
        ("GET", "/files/serve"),
    ],
)
def test_every_route_refuses_a_wrong_token(
    tmp_path: pathlib.Path, method: str, path: str
):
    response = client(tmp_path, bearer_token="s3cret").request(
        method, path, json={}, headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


def test_the_right_token_opens_every_kind_of_route(tmp_path: pathlib.Path):
    """The other half of the table above: with the token, ``/health``
    answers in full, and a chat stream and both file routes are served."""
    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")
    http = client(tmp_path, bearer_token="s3cret")
    auth = {"Authorization": "Bearer s3cret"}

    health = http.get("/health", headers=auth)
    assert health.status_code == 200
    assert health.json()["contracts"]["desktop_chat"]["sse_schema_version"] == 3
    assert "provider" in health.json()
    assert http.head("/health", headers=auth).status_code == 200

    stream = http.post("/chat/stream", json=body(), headers=auth)
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert frames_of(stream.text)[-1] == {"type": "done", "data": ""}

    assert http.get("/files/tree", headers=auth).status_code == 200
    served_file = http.get("/files/serve", params={"path": "notes.txt"}, headers=auth)
    assert (served_file.status_code, served_file.content) == (200, b"hi")


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Bearer s3cret"}],
)
def test_an_unknown_route_is_a_404_whatever_the_token(
    tmp_path: pathlib.Path, headers: dict
):
    """A 404 comes before authentication, so it says nothing about the
    token; a client probing whether its token works has to ask
    ``/health``."""
    http = client(tmp_path, bearer_token="s3cret")
    assert http.get("/notebook", headers=headers).status_code == 404


def test_an_unknown_route_is_a_404(tmp_path: pathlib.Path):
    assert client(tmp_path).get("/notebook").status_code == 404


# ---- JSON only on the write routes --------------------------------------

WRITE_ROUTES = [
    ("POST", "/chat/stream"),
    ("POST", "/chat/permission"),
    ("POST", "/chat/abort"),
    ("POST", "/chat/session-permission-profile"),
    ("PUT", "/workspace"),
    ("PUT", "/providers"),
    ("POST", "/providers/test"),
    ("POST", "/chat/title"),
]


@pytest.mark.parametrize(("method", "path"), WRITE_ROUTES)
@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain;charset=UTF-8",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/jsonx",
        "text/application/json",
        "application/json-patch+json",
        None,
    ],
)
def test_a_write_route_refuses_anything_but_json(
    tmp_path: pathlib.Path, method: str, path: str, content_type: str | None
):
    """A web page can send ``text/plain`` to a loopback port without a CORS
    preflight, and this server grants no CORS, so only a JSON body proves
    the sender got past a preflight. Missing is refused too: a request
    that names no type has not said it is JSON. The media type is compared
    exactly, so ``application/jsonx`` and ``text/application/json`` do not
    pass a substring test they would have passed."""
    headers = {} if content_type is None else {"Content-Type": content_type}
    response = client(tmp_path).request(
        method, path, content=json.dumps(body()).encode(), headers=headers
    )
    assert response.status_code == 415
    assert response.json() == {"detail": "unsupported_media_type"}


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=utf-8", "Application/JSON ;x=1"],
)
def test_json_with_parameters_is_json(tmp_path: pathlib.Path, content_type: str):
    response = client(tmp_path).post(
        "/chat/stream",
        content=json.dumps(body()).encode(),
        headers={"Content-Type": content_type},
    )
    assert response.status_code == 200


def test_the_media_type_is_checked_before_the_body_is_read(tmp_path: pathlib.Path):
    """An oversized ``text/plain`` body is a 415, not a 413."""
    response = client(tmp_path).post(
        "/chat/stream",
        content=b"x" * (3 * 1024 * 1024),
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 415


# ---- /chat/stream -------------------------------------------------------


def test_chat_stream_returns_sse_with_the_turn_id(tmp_path: pathlib.Path):
    response = client(tmp_path).post("/chat/stream", json=body())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["X-OmicsClaw-Turn-Id"]
    frames = frames_of(response.text)
    assert [frame["type"] for frame in frames[-2:]] == ["result", "done"]
    assert frames[-1] == {"type": "done", "data": ""}


@pytest.mark.parametrize(
    ("document", "status", "code"),
    [
        (body(source_request_id=""), 422, "source_request_id_required"),
        (body(content=""), 422, "content_required"),
        (body(files=[{"name": "x"}]), 409, "attachments_not_supported"),
        (body(ingress_schema_version=1), 422, "unsupported_ingress_schema_version"),
        (body(ingress_schema_version=2), 422, "unsupported_ingress_schema_version"),
        (body(resume="yes"), 422, "invalid_resume"),
        (
            {k: v for k, v in body().items() if k != "ingress_schema_version"},
            422,
            "unsupported_ingress_schema_version",
        ),
        (body(workspace="/nowhere/else"), 409, "workspace_does_not_match_backend_runtime"),
        (body(workspace="/tmp/a\x00b"), 422, "invalid_workspace"),
    ],
)
def test_a_refusal_keeps_its_published_status(
    tmp_path: pathlib.Path, document: dict, status: int, code: str
):
    response = client(tmp_path).post("/chat/stream", json=document)
    assert response.status_code == status
    assert response.json() == {"detail": code}


def test_frames_carry_ids_and_the_ending_does_not(tmp_path: pathlib.Path):
    response = client(tmp_path).post("/chat/stream", json=body())
    frames = framed(response.text)
    assert frames[-2][0] is None and frames[-2][1]["type"] == "result"
    assert frames[-1] == (None, {"type": "done", "data": ""})
    ids = [event_id for event_id, frame in frames if frame["type"] == "text"]
    assert ids and all(isinstance(event_id, int) and event_id > 0 for event_id in ids)


def test_a_resume_of_an_unknown_request_is_a_409(tmp_path: pathlib.Path):
    response = client(tmp_path).post("/chat/stream", json=body(resume=True))
    assert response.status_code == 409
    assert response.json() == {"detail": "exchange_not_retained"}


def test_a_resume_of_a_finished_exchange_sends_the_rest_and_done(
    tmp_path: pathlib.Path,
):
    from tests.entry.test_desktop_stream import Chatty  # type: ignore[import-not-found]

    provider = Chatty(chunks=12)
    http = testclient.TestClient(create_desktop_app(served(tmp_path, provider)))
    whole = http.post("/chat/stream", json=body())
    frames = framed(whole.text)
    cursor = frames[4][0]
    assert cursor is not None

    rest = http.post("/chat/stream", json=body(resume=True, after_seq=cursor))
    assert rest.status_code == 200
    assert rest.headers["X-OmicsClaw-Turn-Id"] == whole.headers["X-OmicsClaw-Turn-Id"]
    head = [frame for _, frame in frames[:5]]
    tail = frames_of(rest.text)
    assert text_of(head) + text_of(tail) == provider.text
    assert [frame["type"] for frame in tail[-2:]] == ["result", "done"]
    assert json.loads(tail[-2]["data"]) == json.loads(frames[-2][1]["data"])


def test_a_resume_never_starts_an_exchange(tmp_path: pathlib.Path):
    """The id was used for ``/compact``; resuming it reattaches to that
    compaction. A redelivery with other content would have started a new
    exchange and called the model."""
    provider = Scripted(DONE)
    http = testclient.TestClient(create_desktop_app(served(tmp_path, provider)))
    compact = http.post("/chat/stream", json=body(content="/compact"))
    resumed = http.post("/chat/stream", json=body(resume=True, content="hello"))

    assert resumed.status_code == 200
    assert resumed.headers["X-OmicsClaw-Turn-Id"] == compact.headers["X-OmicsClaw-Turn-Id"]
    assert [frame["type"] for frame in frames_of(resumed.text)] == [
        "status",
        "result",
        "done",
    ]
    assert provider.calls == 0


def test_a_resume_does_not_change_the_session_permission_profile(tmp_path: pathlib.Path):
    """Only a message may carry the profile a session runs in; a resume
    that repeats the original body, or a forged one, changes nothing."""
    from omicsclaw.entry.desktop.interactions import DesktopInteractions

    app = served(tmp_path)
    interactions = DesktopInteractions(app)
    http = testclient.TestClient(create_desktop_app(app, interactions=interactions))
    assert http.post("/chat/stream", json=body()).status_code == 200
    assert interactions.permission_profile("s1") == "default"

    resumed = http.post(
        "/chat/stream", json=body(resume=True, permission_profile="full_access")
    )
    assert resumed.status_code == 200
    assert interactions.permission_profile("s1") == "default"


def test_a_resume_still_checks_the_workspace(tmp_path: pathlib.Path):
    http = testclient.TestClient(create_desktop_app(served(tmp_path)))
    assert http.post("/chat/stream", json=body()).status_code == 200

    elsewhere = http.post(
        "/chat/stream", json=body(resume=True, workspace="/nowhere/else")
    )
    assert elsewhere.status_code == 409
    assert elsewhere.json() == {"detail": "workspace_does_not_match_backend_runtime"}
    same = http.post("/chat/stream", json=body(resume=True, workspace=str(tmp_path)))
    assert same.status_code == 200


def test_an_exchange_with_every_observer_slot_taken_is_a_429(tmp_path: pathlib.Path):
    app = served(tmp_path)
    http = testclient.TestClient(create_desktop_app(app))
    first = http.post("/chat/stream", json=body())
    handle = app.sessions.handle(first.headers["X-OmicsClaw-Turn-Id"])
    held = [handle.observe() for _ in range(16)]

    response = http.post("/chat/stream", json=body(resume=True))
    assert response.status_code == 429
    assert response.json() == {"detail": "too_many_observers"}
    for observation in held:
        observation.close()
    assert http.post("/chat/stream", json=body(resume=True)).status_code == 200


def test_an_oversized_body_is_refused_by_status(tmp_path: pathlib.Path):
    response = client(tmp_path).post(
        "/chat/stream",
        content=b'{"content": "' + b"x" * (2 * 1024 * 1024) + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


# ---- /chat/permission, /chat/abort, /workspace ---------------------------


def test_permission_answers_an_unknown_request_as_expired(tmp_path: pathlib.Path):
    response = client(tmp_path).post(
        "/chat/permission",
        json={"request_id": "f" * 32 + "#1", "decision": {"behavior": "allow"}},
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "request_id": "f" * 32 + "#1",
        "status": "expired",
    }


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"permissionRequestId": "f" * 32 + "#1", "decision": {"behavior": "allow"}}, "invalid_request_id"),
        ({"request_id": "f" * 32 + "#1", "decision": {"behavior": "yes"}}, "invalid_decision"),
        ({"request_id": "f" * 32 + "#1", "decision": {"behavior": "allow", "scope": "forever"}}, "unsupported_scope"),
    ],
)
def test_permission_refuses_a_malformed_decision(
    tmp_path: pathlib.Path, document: dict, code: str
):
    response = client(tmp_path).post("/chat/permission", json=document)
    assert response.status_code == 422
    assert response.json() == {"detail": code}


def test_permission_accepts_always(tmp_path: pathlib.Path):
    response = client(tmp_path).post(
        "/chat/permission",
        json={
            "request_id": "f" * 32 + "#1",
            "decision": {"behavior": "allow", "scope": "always"},
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "expired"


def test_the_session_permission_profile_route(tmp_path: pathlib.Path):
    http = client(tmp_path)
    response = http.post(
        "/chat/session-permission-profile",
        json={"session_id": "s1", "permission_profile": "full_access"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "session_id": "s1",
        "permission_profile": "full_access",
        "active": False,
        "auto_approved_requests": 0,
    }
    refused = http.post(
        "/chat/session-permission-profile",
        json={"session_id": "s1", "permission_profile": "yolo"},
    )
    assert refused.status_code == 422
    assert refused.json() == {"detail": "invalid_permission_profile"}


def test_the_doctor_answers_the_app_s_checklist_shape(tmp_path: pathlib.Path):
    """``OmicsClaw-App/src/lib/env-doctor.ts`` reads these keys; a check it
    counts as ``warn`` or ``fail`` puts an Electron activation in
    ``needs-attention``."""
    payload = client(tmp_path).get("/env/doctor").json()
    assert set(payload) == {
        "generated_at",
        "workspace_dir",
        "omicsclaw_dir",
        "overall_status",
        "failure_count",
        "warning_count",
        "checks",
    }
    assert payload["workspace_dir"] == str(tmp_path)
    for check in payload["checks"]:
        assert set(check) == {"name", "status", "summary", "details"}
        assert check["status"] in {"ok", "warn", "fail", "info"}


def test_the_doctor_needs_the_token_like_every_other_route(tmp_path: pathlib.Path):
    http = client(tmp_path, bearer_token="s3cret")
    assert http.get("/env/doctor").status_code == 401
    ok = http.get("/env/doctor", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert ok.json()["checks"]


def test_abort_of_an_unknown_request_is_a_404(tmp_path: pathlib.Path):
    response = client(tmp_path).post(
        "/chat/abort", json={"session_id": "s1", "source_request_id": KEY}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "turn_not_found"}


def test_abort_refuses_a_malformed_request(tmp_path: pathlib.Path):
    response = client(tmp_path).post(
        "/chat/abort", json={"session_id": "s1", "source_request_id": "x"}
    )
    assert response.status_code == 422


def test_abort_after_the_stream_ended_is_idempotent(tmp_path: pathlib.Path):
    http = client(tmp_path)
    assert http.post("/chat/stream", json=body()).status_code == 200
    stop = {"session_id": "s1", "source_request_id": KEY}
    first = http.post("/chat/abort", json=stop)
    second = http.post("/chat/abort", json=stop)
    assert first.status_code == second.status_code == 200
    assert first.json()["turn_id"] == second.json()["turn_id"]


def test_the_workspace_routes(tmp_path: pathlib.Path):
    http = client(tmp_path)
    assert http.get("/workspace").json() == {
        "workspace": str(tmp_path),
        "trusted_dirs": [],
    }
    same = http.put("/workspace", json={"workspace": str(tmp_path) + "/"})
    assert same.status_code == 200
    assert same.json()["workspace"] == str(tmp_path)
    other = http.put("/workspace", json={"workspace": str(tmp_path / "other")})
    assert other.status_code == 409
    assert other.json() == {"detail": "workspace_change_requires_restart"}


def test_an_unresolvable_workspace_is_a_422_not_a_500(tmp_path: pathlib.Path):
    response = client(tmp_path).put(
        "/workspace", json={"workspace": str(tmp_path) + "\x00"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_workspace"}


# ---- /files/tree and /files/serve ------------------------------------------


def files_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """The workspace is *tmp_path*; the app writes ``OMICSCLAW.md`` there."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (tmp_path / "digits.txt").write_bytes(b"0123456789abcdef")
    (tmp_path / "empty.txt").write_bytes(b"")
    (tmp_path / "page.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    return tmp_path


def sparse(path: pathlib.Path, size: int) -> pathlib.Path:
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


def test_the_tree_route_answers_the_tree(tmp_path: pathlib.Path):
    ws = files_workspace(tmp_path)
    response = client(tmp_path).get("/files/tree", params={"path": str(ws), "depth": 2})
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    payload = response.json()
    assert set(payload) == {"root", "tree", "truncated"}
    assert payload["root"] == str(ws)
    assert payload["truncated"] is False
    by_name = {node["name"]: node for node in payload["tree"]}
    assert ".env" not in by_name
    assert by_name["data"]["children"] == [
        {
            "name": "a.csv",
            "path": str(ws / "data" / "a.csv"),
            "type": "file",
            "size": 8,
            "extension": "csv",
        }
    ]


def test_the_tree_route_lists_the_workspace_without_a_path(tmp_path: pathlib.Path):
    files_workspace(tmp_path)
    payload = client(tmp_path).get("/files/tree").json()
    assert payload["root"] == str(tmp_path)
    assert "data" in [node["name"] for node in payload["tree"]]


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({"path": "/etc"}, 403, "path_outside_workspace"),
        ({"path": "../.."}, 403, "path_outside_workspace"),
        ({"path": ".omicsclaw"}, 403, "hidden_path"),
        ({"path": "missing"}, 404, "directory_not_found"),
        ({"path": "digits.txt"}, 422, "not_a_directory"),
        ({"depth": "0"}, 422, "invalid_depth"),
        ({"depth": "eleven"}, 422, "invalid_depth"),
    ],
)
def test_the_tree_route_refusals(
    tmp_path: pathlib.Path, params: dict, status: int, code: str
):
    files_workspace(tmp_path)
    response = client(tmp_path).get("/files/tree", params=params)
    assert response.status_code == status
    assert response.json() == {"detail": code}


def test_serve_answers_the_whole_file(tmp_path: pathlib.Path):
    ws = files_workspace(tmp_path)
    response = client(tmp_path).get("/files/serve", params={"path": str(ws / "data/a.csv")})
    assert response.status_code == 200
    assert response.content == b"x,y\n1,2\n"
    assert response.headers["content-type"] == "text/csv"
    assert response.headers["content-length"] == "8"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "private, max-age=60"
    assert response.headers["content-disposition"] == 'inline; filename="a.csv"'
    assert response.headers["x-content-type-options"] == "nosniff"


def test_serve_answers_a_relative_path(tmp_path: pathlib.Path):
    files_workspace(tmp_path)
    response = client(tmp_path).get("/files/serve", params={"path": "digits.txt"})
    assert response.content == b"0123456789abcdef"


def test_serve_answers_a_range_with_206(tmp_path: pathlib.Path):
    files_workspace(tmp_path)
    response = client(tmp_path).get(
        "/files/serve", params={"path": "digits.txt"}, headers={"Range": "bytes=0-9"}
    )
    assert response.status_code == 206
    assert response.content == b"0123456789"
    assert response.headers["content-range"] == "bytes 0-9/16"
    assert response.headers["content-length"] == "10"


def test_serve_ignores_a_range_on_an_empty_file(tmp_path: pathlib.Path):
    """The App's preview always sends a ``Range``; Starlette's own handling
    answers 416 for any range on an empty file."""
    files_workspace(tmp_path)
    response = client(tmp_path).get(
        "/files/serve", params={"path": "empty.txt"}, headers={"Range": "bytes=0-262143"}
    )
    assert response.status_code == 200
    assert response.content == b""


def test_serve_ignores_a_range_with_an_overlong_number(tmp_path: pathlib.Path):
    """Parsing a 5000-digit number raises in Python, and used to answer 500
    without ``nosniff``; such a Range is malformed and ignored."""
    files_workspace(tmp_path)
    response = client(tmp_path).get(
        "/files/serve",
        params={"path": "digits.txt"},
        headers={"Range": "bytes=0-" + "9" * 5000},
    )
    assert response.status_code == 200
    assert response.content == b"0123456789abcdef"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_serve_answers_416_for_a_range_past_the_end(tmp_path: pathlib.Path):
    files_workspace(tmp_path)
    response = client(tmp_path).get(
        "/files/serve", params={"path": "digits.txt"}, headers={"Range": "bytes=16-"}
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */16"
    assert response.json() == {"detail": "range_not_satisfiable"}


def test_serve_refuses_a_file_over_the_limit_without_a_range(tmp_path: pathlib.Path):
    from omicsclaw.entry.desktop.files import FILES_SERVE_MAX_BYTES

    sparse(tmp_path / "big.bin", FILES_SERVE_MAX_BYTES + 1)
    response = client(tmp_path).get("/files/serve", params={"path": "big.bin"})
    assert response.status_code == 413
    assert response.json() == {"detail": "file_too_large"}


def test_serve_caps_an_open_range_on_a_file_over_the_limit(tmp_path: pathlib.Path):
    """``<video>`` asks for ``bytes=0-``; it gets the first 64 MiB, not 413."""
    from omicsclaw.entry.desktop.files import FILES_SERVE_MAX_BYTES

    size = FILES_SERVE_MAX_BYTES + 1
    sparse(tmp_path / "big.bin", size)
    response = client(tmp_path).get(
        "/files/serve", params={"path": "big.bin"}, headers={"Range": "bytes=0-"}
    )
    assert response.status_code == 206
    assert len(response.content) == FILES_SERVE_MAX_BYTES
    assert response.headers["content-length"] == str(FILES_SERVE_MAX_BYTES)
    assert response.headers["content-range"] == (
        f"bytes 0-{FILES_SERVE_MAX_BYTES - 1}/{size}"
    )


def test_serve_sends_html_as_plain_text(tmp_path: pathlib.Path):
    files_workspace(tmp_path)
    response = client(tmp_path).get("/files/serve", params={"path": "page.html"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("../../etc/passwd", 403, "path_outside_workspace"),
        ("/etc/hostname", 403, "path_outside_workspace"),
        (".env", 403, "hidden_path"),
        ("", 422, "path_required"),
        ("missing.txt", 404, "file_not_found"),
        ("data", 422, "not_a_file"),
    ],
)
def test_serve_refusals_carry_nosniff(
    tmp_path: pathlib.Path, path: str, status: int, code: str
):
    files_workspace(tmp_path)
    response = client(tmp_path).get("/files/serve", params={"path": path})
    assert response.status_code == status
    assert response.json() == {"detail": code}
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "path", ["/files/tree?path=data", "/files/serve?path=digits.txt"]
)
def test_the_file_routes_need_the_token(tmp_path: pathlib.Path, path: str):
    files_workspace(tmp_path)
    http = client(tmp_path, bearer_token="s3cret")
    assert http.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert http.get(path).status_code == 401
    assert http.get(path, headers={"Authorization": "Bearer s3cret"}).status_code == 200


# ---- a real server, with overlapping requests ----------------------------


def test_a_real_server_answers_a_card_and_stops_a_tool_mid_stream(
    tmp_path: pathlib.Path,
):
    """The loop the desktop client runs, over real sockets.

    One stream asks for approval and is answered by a ``/chat/permission``
    POST sent while it is open; a second stream runs a tool that never
    finishes and is ended by ``/chat/abort``, with ``error: "cancelled"``
    then ``done`` arriving within two seconds.
    """
    uvicorn = pytest.importorskip("uvicorn")
    httpx = pytest.importorskip("httpx")

    sleeping = Sleeping()
    app = served(
        tmp_path,
        Scripted(calling("ask"), DONE, calling("sleep"), DONE),
        tools=[Asking("ask"), sleeping],
    )
    api = create_desktop_app(app)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    async def read(response, on_frame=None) -> list[dict]:
        frames: list[dict] = []
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            frame = json.loads(line[len("data: ") :])
            frames.append(frame)
            if on_frame is not None:
                await on_frame(frame)
        return frames

    async def scenario() -> tuple[list[dict], dict, list[dict], dict, float]:
        server = uvicorn.Server(
            uvicorn.Config(api, log_level="warning", lifespan="off", ws="none")
        )
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                await asyncio.sleep(0.01)
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", timeout=10
            ) as http:
                answers: list[dict] = []

                async def answer(frame: dict) -> None:
                    if frame["type"] != "permission_request":
                        return
                    card = json.loads(frame["data"])
                    reply = await http.post(
                        "/chat/permission",
                        json={
                            "request_id": card["request_id"],
                            "decision": {"behavior": "allow", "scope": "once"},
                        },
                    )
                    answers.append(reply.json())

                async with http.stream("POST", "/chat/stream", json=body()) as first:
                    asked = await read(first, answer)

                stop_key = "b" * 32
                stopped: dict = {}
                started_stop = 0.0

                async def stop(frame: dict) -> None:
                    nonlocal started_stop
                    if frame["type"] != "tool_use" or stopped:
                        return
                    await asyncio.wait_for(sleeping.entered.wait(), 5)
                    started_stop = time.monotonic()
                    reply = await http.post(
                        "/chat/abort",
                        json={"session_id": "s1", "source_request_id": stop_key},
                    )
                    stopped.update(reply.json())

                async with http.stream(
                    "POST", "/chat/stream", json=body(source_request_id=stop_key)
                ) as second:
                    halted = await read(second, stop)
                elapsed = time.monotonic() - started_stop
            return asked, answers[0], halted, stopped, elapsed
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 10)

    asked, answer, halted, stopped, elapsed = asyncio.run(
        asyncio.wait_for(scenario(), 30)
    )

    kinds = [frame["type"] for frame in asked]
    assert kinds.count("permission_request") == 1
    assert answer["ok"] is True and answer["scope"] == "once"
    result = next(json.loads(f["data"]) for f in asked if f["type"] == "tool_result")
    assert result["content"] == "ask ran"
    assert kinds[-2:] == ["result", "done"]

    assert stopped["ok"] is True and stopped["state"] == "cancelling"
    assert halted[-2:] == [
        {"type": "error", "data": "cancelled"},
        {"type": "done", "data": ""},
    ]
    assert elapsed < 2.0


def test_a_real_server_resumes_a_dropped_stream_from_its_last_id(
    tmp_path: pathlib.Path,
):
    """Over real sockets, with a token: the client drops the connection
    mid-answer, reconnects with ``resume`` and the last ``id:`` it saw,
    and reads the rest through ``done``. The two halves join into the
    whole answer, nothing repeated."""
    uvicorn = pytest.importorskip("uvicorn")
    httpx = pytest.importorskip("httpx")
    from tests.entry.test_desktop_stream import Paused  # type: ignore[import-not-found]

    provider = Paused()
    app = served(tmp_path, provider)
    api = create_desktop_app(app, bearer_token="s3cret")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    auth = {"Authorization": "Bearer s3cret"}

    async def frames(response, stop_after_text: bool = False):
        seen: list[tuple[int | None, dict]] = []
        event_id: int | None = None
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                event_id = int(line[len("id: ") :])
            elif line.startswith("data: "):
                frame = json.loads(line[len("data: ") :])
                seen.append((event_id, frame))
                event_id = None
                if stop_after_text and frame["type"] == "text":
                    return seen
        return seen

    async def scenario():
        server = uvicorn.Server(
            uvicorn.Config(api, log_level="warning", lifespan="off", ws="none")
        )
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                await asyncio.sleep(0.01)
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", timeout=10, headers=auth
            ) as http:
                async with http.stream("POST", "/chat/stream", json=body()) as first:
                    turn = first.headers["X-OmicsClaw-Turn-Id"]
                    head = await frames(first, stop_after_text=True)
                await asyncio.wait_for(provider.started.wait(), 5)
                handle = app.sessions.handle(turn)
                for _ in range(200):
                    if handle.stream.observer_count() == 0:
                        break
                    await asyncio.sleep(0.01)
                detached = handle.stream.observer_count() == 0
                provider.release.set()
                cursor = head[-1][0]
                async with http.stream(
                    "POST",
                    "/chat/stream",
                    json=body(resume=True, after_seq=cursor),
                ) as second:
                    resumed_turn = second.headers["X-OmicsClaw-Turn-Id"]
                    tail = await frames(second)
            return turn, resumed_turn, head, tail, detached
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 10)

    turn, resumed_turn, head, tail, detached = asyncio.run(
        asyncio.wait_for(scenario(), 30)
    )

    assert detached, "the server never noticed the dropped connection"
    assert resumed_turn == turn
    assert head[-1][0] is not None
    joined = text_of([f for _, f in head]) + text_of([f for _, f in tail])
    assert joined == "first second"
    assert [f["type"] for _, f in tail[-2:]] == ["result", "done"]
    assert [event_id for event_id, _ in tail[-2:]] == [None, None]


def test_health_advertises_optional_capabilities_without_changing_v3(tmp_path):
    payload = client(tmp_path).get('/health').json()
    assert payload['capabilities'] == {
        'files_tree': True,
        'files_serve': True,
    }
    assert payload['contracts']['desktop_chat']['request_schema_version'] == 3
    assert payload['contracts']['desktop_chat']['sse_schema_version'] == 3
    assert 'commit' in payload['build']
    assert 'dirty' in payload['build']
