"""The HTTP adapter, where a web framework exists to run it.

**This file is skipped on the machine this step was built on.** ``fastapi``
is not installed here (plan 0031 §8.2), so nothing below has been executed
and no claim is made that it passes. It exists because the alternative —
leaving the FastAPI wiring with no test at all — would make the first person
to install the dependency the first person to run the route.

Everything that *can* be verified without a server already is:
``test_desktop_ingress.py`` covers admission and idempotency,
``test_desktop_stream.py`` covers the frames and the cursor, and
``test_desktop_wire_contract.py`` covers the published contract and the fact
that importing this package costs no web framework. What is left here is
only the adapter: status codes, headers, and the bearer gate.
"""

from __future__ import annotations

import json
import pathlib

import pytest

pytest.importorskip("fastapi", reason="the Desktop HTTP adapter needs it")
testclient = pytest.importorskip("fastapi.testclient")

from omicsclaw.entry.desktop import create_desktop_app  # noqa: E402
from omicsclaw.entry.session import attach_sessions  # noqa: E402
from tests.entry.test_turn_runner import (  # noqa: E402
    Scripted,  # type: ignore[import-not-found]
    make_app,
)

KEY = "a" * 32


def client(tmp_path: pathlib.Path, **overrides):
    app = attach_sessions(
        make_app(tmp_path, Scripted(), tools=()), abandon_grace_s=None
    )
    return testclient.TestClient(create_desktop_app(app, **overrides))


def body(**overrides) -> dict:
    document = {"content": "hi", "session_id": "s1", "source_request_id": KEY}
    document.update(overrides)
    return document


def test_health_reports_the_four_contracts(tmp_path: pathlib.Path):
    payload = client(tmp_path).get("/health").json()
    assert payload["status"] == "ok"
    assert set(payload["contracts"]) == {
        "desktop_chat",
        "desktop_run",
        "desktop_turn_observation",
        "desktop_turn_submission",
    }
    assert payload["served_paths"] == ["/chat/stream", "/health"]


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


def test_chat_stream_refuses_a_wrong_token(tmp_path: pathlib.Path):
    response = client(tmp_path, bearer_token="s3cret").post(
        "/chat/stream", json=body(), headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


def test_chat_stream_returns_sse_with_the_turn_id(tmp_path: pathlib.Path):
    response = client(tmp_path).post("/chat/stream", json=body())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["X-OmicsClaw-Turn-Id"]
    frames = [line for line in response.text.split("\n\n") if line.strip()]
    assert json.loads(frames[-1][len("data: ") :]) == {"type": "done", "data": ""}


@pytest.mark.parametrize(
    ("document", "status"),
    [
        ({"content": "hi", "session_id": "s1", "source_request_id": ""}, 422),
        ({"content": "", "session_id": "s1", "source_request_id": KEY}, 422),
        (
            {
                "content": "hi",
                "session_id": "s1",
                "source_request_id": KEY,
                "files": [{"name": "x"}],
            },
            409,
        ),
    ],
)
def test_a_refusal_keeps_its_published_status(
    tmp_path: pathlib.Path, document: dict, status: int
):
    response = client(tmp_path).post("/chat/stream", json=document)
    assert response.status_code == status
    assert "detail" in response.json()


def test_an_oversized_body_is_refused_by_status(tmp_path: pathlib.Path):
    response = client(tmp_path).post(
        "/chat/stream",
        content=b'{"content": "' + b"x" * (2 * 1024 * 1024) + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
