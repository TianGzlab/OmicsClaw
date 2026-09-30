"""The management routes over HTTP: status codes, shapes and the adapter.

Needs ``fastapi``, so it runs under the OmicsClaw interpreter and is
skipped elsewhere. What each route answers is tested without a web
framework in ``test_desktop_catalog.py``, ``test_desktop_providers.py``
and ``test_desktop_title.py``; what is left here is that the adapter
mounts every published path, passes the settings through, and keeps the
write routes JSON-only (``test_desktop_http.py`` covers the media types
and the bearer gate for all routes).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

pytest.importorskip("fastapi", reason="the Desktop HTTP adapter needs it")
testclient = pytest.importorskip("fastapi.testclient")

from omicsclaw.entry.desktop import DotenvSettings, create_desktop_app  # noqa: E402
from omicsclaw.entry.desktop.wire_contract import SERVED_PATHS  # noqa: E402
from omicsclaw.entry.session import attach_sessions  # noqa: E402
from omicsclaw.schema import Message, Role  # noqa: E402
from omicsclaw.skills import Skill, SkillIndex  # noqa: E402
from tests.entry.test_turn_runner import Scripted, make_app  # noqa: E402

SECRET = "sk-live-0123456789abcdefSECRET"
RID = "0123456789abcdef0123456789abcdef"


def served(tmp_path: pathlib.Path, provider=None, **app_fields):
    app = attach_sessions(
        make_app(tmp_path, provider or Scripted(), tools=()), abandon_grace_s=None
    )
    return dataclasses.replace(app, **app_fields) if app_fields else app


def settings_in(tmp_path: pathlib.Path, text: str = "") -> DotenvSettings:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    path = home / ".env"
    if text:
        path.write_text(text, encoding="utf-8")
    return DotenvSettings(path, candidates=(path,), exported={}, startup={})


def client_for(app, **overrides):
    return testclient.TestClient(create_desktop_app(app, **overrides))


FASTAPI_DOCS_PATHS = frozenset(
    {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
)
"""What FastAPI mounts on its own. They are kept: they describe routes
whose source is public, and ``/health`` already names the version."""


def test_the_mounted_paths_are_exactly_the_served_paths(tmp_path):
    """Equality, so a route mounted without being published fails here as
    surely as a published one that was never mounted."""
    api = create_desktop_app(served(tmp_path))
    mounted = {route.path for route in api.routes}
    assert FASTAPI_DOCS_PATHS <= mounted
    assert mounted - FASTAPI_DOCS_PATHS == set(SERVED_PATHS)


# ---- skills --------------------------------------------------------------


def one_skill_index(tmp_path: pathlib.Path) -> SkillIndex:
    root = tmp_path / "skills"
    path = root / "spatial" / "spatial-de" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: spatial-de\ndescription: d\n---\n\nBody\n", encoding="utf-8")
    skill = Skill(name="spatial-de", description="d", path=path, root=root)
    return SkillIndex(skills=(skill,), root=root)


def test_the_skill_catalog_and_one_skill(tmp_path):
    client = client_for(served(tmp_path, skills=one_skill_index(tmp_path)))

    catalog = client.get("/skills")
    assert catalog.status_code == 200
    assert catalog.json()["total"] == 1
    assert catalog.json()["domains"][0]["skills"][0]["name"] == "spatial-de"

    detail = client.get("/skills/spatial/spatial-de")
    assert detail.status_code == 200
    assert detail.json()["skill_md"] == "Body"

    missing = client.get("/skills/bulkrna/spatial-de")
    assert (missing.status_code, missing.json()) == (404, {"detail": "skill_not_found"})


# ---- MCP -----------------------------------------------------------------


def test_no_mcp_configuration_is_an_empty_list(tmp_path):
    response = client_for(served(tmp_path)).get("/mcp/servers")
    assert (response.status_code, response.json()) == (200, {"servers": []})


# ---- providers -----------------------------------------------------------


def test_the_provider_listing_names_the_settings_file(tmp_path):
    settings = settings_in(tmp_path, f"DEEPSEEK_API_KEY={SECRET}\n")
    response = client_for(served(tmp_path), settings=settings).get("/providers")
    assert response.status_code == 200
    payload = response.json()
    assert payload["env_file"] == str(settings.path)
    assert SECRET not in response.text
    deepseek = next(row for row in payload["providers"] if row["name"] == "deepseek")
    assert deepseek["configured"] is True


def test_without_settings_the_listing_answers_and_writes_are_unavailable(tmp_path):
    client = client_for(served(tmp_path))
    assert client.get("/providers").status_code == 200
    for method, path in (("PUT", "/providers"), ("POST", "/providers/test")):
        response = client.request(method, path, json={"provider": "deepseek"})
        assert (response.status_code, response.json()) == (
            503,
            {"detail": "settings_unavailable"},
        )


def test_a_save_writes_the_file_and_never_echoes_the_key(tmp_path):
    settings = settings_in(tmp_path, "# keep\nLLM_PROVIDER=openai\n")
    response = client_for(served(tmp_path), settings=settings).put(
        "/providers", json={"provider": "zhipu", "api_key": SECRET}
    )
    assert response.status_code == 200
    assert SECRET not in response.text
    payload = response.json()
    assert payload["ok"] is True and payload["restart_required"] is True
    assert payload["provider"] == "zhipu"
    assert f"ZHIPU_API_KEY={SECRET}" in settings.path.read_text(encoding="utf-8")


def test_a_bad_save_is_a_422_with_its_code(tmp_path):
    settings = settings_in(tmp_path)
    response = client_for(served(tmp_path), settings=settings).put(
        "/providers", json={"provider": "deepseek", "auth_mode": "oauth"}
    )
    assert (response.status_code, response.json()) == (422, {"detail": "unknown_field"})
    assert not settings.path.exists()


def test_a_save_as_text_plain_writes_nothing(tmp_path):
    settings = settings_in(tmp_path)
    response = client_for(served(tmp_path), settings=settings).put(
        "/providers",
        content=json.dumps({"provider": "deepseek", "api_key": SECRET}).encode(),
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 415
    assert not settings.path.exists()


def test_a_provider_test_answers_200_whichever_way_it_goes(tmp_path):
    """A failed live call is a result, not an HTTP error: the client reads
    ``resp.ok && payload.ok``. ``ollama`` on a closed port fails fast."""
    settings = settings_in(tmp_path, "OLLAMA_BASE_URL=http://127.0.0.1:9/v1\n")
    response = client_for(served(tmp_path), settings=settings).post(
        "/providers/test", json={"provider": "ollama", "model": "m"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert isinstance(payload["duration_ms"], int)


# ---- /chat/title ---------------------------------------------------------


def test_a_title_is_generated(tmp_path):
    provider = Scripted(Message(role=Role.ASSISTANT, content='"Mouse brain DE"'))
    response = client_for(served(tmp_path, provider)).post(
        "/chat/title",
        json={"schema_version": 1, "source_request_id": RID, "user_text": "hi"},
    )
    assert (response.status_code, response.json()) == (
        200,
        {"schema_version": 1, "title": "Mouse brain DE"},
    )


def test_a_bad_title_request_is_a_422_with_its_code(tmp_path):
    response = client_for(served(tmp_path)).post(
        "/chat/title", json={"schema_version": 1, "user_text": "hi"}
    )
    assert response.status_code == 422
    assert response.json() == {
        "schema_version": 1,
        "error": {"code": "TITLE_REQUEST_INVALID"},
    }


def test_a_title_body_that_is_not_json_is_refused_at_the_wire(tmp_path):
    response = client_for(served(tmp_path)).post(
        "/chat/title", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_request_json"}
