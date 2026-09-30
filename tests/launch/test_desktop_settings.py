"""The ``.env`` settings ``oc desktop`` hands to the Desktop routes.

Plan 0065 §3.6. The Providers page has to tell two things apart that the
live process environment has already merged: what the user **exported**
(which beats every ``.env`` and makes a save ineffective) and what
start-up **read from the files**. And it has to know the environment the
process actually **started with**, including a ``.env`` in the working
directory, without reading the files again after they may have changed.

So :func:`omicsclaw.launch.main` takes the set of names before
``_adopt_dotenv`` runs and a snapshot after it, in the one read of the
process environment it is allowed (``test_launch_is_above_entry.py``
counts it), and hands both down inside the ``env`` mapping as a
:class:`~omicsclaw.launch._dotenv.LaunchEnvironment`. A test that passes
``env`` explicitly describes the whole deployment, so all of it counts as
exported.

The repository's own ``.env`` holds a real key; one test runs a save
through the settings start-up builds and checksums that file around it.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import pathlib
from types import SimpleNamespace

import pytest

import omicsclaw.launch as launch
from omicsclaw.entry.desktop import DotenvSettings
from omicsclaw.entry.desktop.providers import save_provider
from omicsclaw.launch import _adopt_dotenv, _surfaces
from omicsclaw.launch._dotenv import LaunchEnvironment

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def pristine_environment():
    """Restore the process environment, including what a ``.env`` added."""
    before = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def captured_start(monkeypatch) -> list:
    seen: list = []

    def start(deployment, surface, environment):
        seen.append(environment)
        return 0

    monkeypatch.setattr(
        launch, "COMMANDS", {"desktop": SimpleNamespace(start=start, usage="")}
    )
    return seen


def test_main_separates_exported_names_from_what_dotenv_added(
    monkeypatch, pristine_environment
):
    os.environ["OC_0065_EXPORTED"] = "by-the-operator"
    os.environ.pop("OC_0065_FROM_FILE", None)

    def adopt(root=None, cwd=None):
        os.environ["OC_0065_FROM_FILE"] = "from-the-file"
        return ()

    monkeypatch.setattr(launch, "_adopt_dotenv", adopt)
    seen = captured_start(monkeypatch)

    assert launch.main(["desktop"]) == 0

    (environment,) = seen
    assert isinstance(environment, LaunchEnvironment)
    assert "OC_0065_EXPORTED" in environment.exported_names
    assert "OC_0065_FROM_FILE" not in environment.exported_names
    assert environment["OC_0065_FROM_FILE"] == "from-the-file"
    assert environment.startup["OC_0065_FROM_FILE"] == "from-the-file"
    assert environment.startup["OC_0065_EXPORTED"] == "by-the-operator"


def test_an_explicit_environment_is_passed_through_unchanged(monkeypatch):
    seen = captured_start(monkeypatch)
    given = {"LLM_PROVIDER": "zhipu"}
    assert launch.main(["desktop"], given) == 0
    assert seen == [given]


def test_the_snapshot_includes_the_working_directorys_dotenv(
    tmp_path, pristine_environment
):
    """Both candidates are loaded; the first to name a variable decides it."""
    root, here = tmp_path / "root", tmp_path / "here"
    root.mkdir()
    here.mkdir()
    (root / ".env").write_text("OC_0065_A=1\nOC_0065_SHARED=root\n", encoding="utf-8")
    (here / ".env").write_text("OC_0065_B=2\nOC_0065_SHARED=here\n", encoding="utf-8")
    for name in ("OC_0065_A", "OC_0065_B", "OC_0065_SHARED"):
        os.environ.pop(name, None)

    exported = frozenset(os.environ)
    _adopt_dotenv(root=root, cwd=here)
    environment = LaunchEnvironment(os.environ, exported)

    assert environment.startup["OC_0065_A"] == "1"
    assert environment.startup["OC_0065_B"] == "2"
    assert environment.startup["OC_0065_SHARED"] == "root"
    assert not {"OC_0065_A", "OC_0065_B"} & environment.exported_names

    os.environ["OC_0065_A"] = "changed later"
    assert environment.startup["OC_0065_A"] == "1"
    assert environment["OC_0065_A"] == "changed later"


def test_a_launch_environment_is_a_read_only_mapping():
    live = {"A": "1", "B": "2"}
    environment = LaunchEnvironment(live, frozenset({"A"}))
    assert dict(environment) == live
    assert len(environment) == 2 and "B" in environment
    assert environment.get("C", "x") == "x"
    with pytest.raises(TypeError):
        environment["A"] = "3"  # type: ignore[index]


def test_settings_from_a_launch_environment_export_only_the_exported_names(tmp_path):
    live = {"LLM_PROVIDER": "openai", "LLM_API_KEY": "from-file"}
    environment = LaunchEnvironment(live, frozenset({"LLM_PROVIDER"}))
    settings = _surfaces._desktop_settings(environment, root=tmp_path, cwd=tmp_path / "cwd")

    assert isinstance(settings, DotenvSettings)
    assert dict(settings.exported) == {"LLM_PROVIDER": "openai"}
    assert dict(settings.startup) == live
    assert settings.path == tmp_path / ".env"
    assert settings.candidates == (tmp_path / ".env", tmp_path / "cwd" / ".env")


def test_settings_from_an_explicit_environment_export_all_of_it(tmp_path):
    given = {"LLM_PROVIDER": "zhipu", "ZHIPU_API_KEY": "k"}
    settings = _surfaces._desktop_settings(given, root=tmp_path, cwd=tmp_path)
    assert dict(settings.exported) == given
    assert dict(settings.startup) == given
    assert settings.candidates == (tmp_path / ".env",)


def test_the_target_is_the_first_candidate_that_exists(tmp_path):
    root, here = tmp_path / "root", tmp_path / "here"
    root.mkdir()
    here.mkdir()
    (here / ".env").write_text("X=1\n", encoding="utf-8")
    settings = _surfaces._desktop_settings({}, root=root, cwd=here)
    assert settings.path == here / ".env"


def _digest(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_start_desktop_hands_settings_to_the_server_and_the_repo_dotenv_is_untouched(
    tmp_path, monkeypatch
):
    """The whole command up to the socket, then a save through what it built."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("OMICSCLAW_DIR", str(home))
    monkeypatch.chdir(tmp_path)
    repo_dotenv = REPO / ".env"
    before = _digest(repo_dotenv)

    handed: list = []

    async def serve(config, options, token, uvicorn, settings):
        handed.append(settings)
        return 0

    monkeypatch.setattr(_surfaces, "_asgi_server_module", lambda: object())
    monkeypatch.setattr(_surfaces, "_serve_desktop", serve)

    assert _surfaces.start_desktop([], [], {"OC_0065_EXPORTED": "1"}) == 0

    (settings,) = handed
    assert isinstance(settings, DotenvSettings)
    assert settings.path == home / ".env"
    assert dict(settings.exported) == {"OC_0065_EXPORTED": "1"}

    app = SimpleNamespace(
        config=SimpleNamespace(provider="", model=""),
        provider=SimpleNamespace(name="deepseek"),
    )
    save_provider(app, settings, {"provider": "zhipu", "api_key": "sk-test-0065"})
    assert "ZHIPU_API_KEY=sk-test-0065" in (home / ".env").read_text(encoding="utf-8")
    assert _digest(repo_dotenv) == before


def test_the_desktop_usage_names_every_route():
    for route in (
        "/chat/stream",
        "/chat/permission",
        "/chat/abort",
        "/chat/session-permission-profile",
        "/workspace",
        "/env/doctor",
        "/health",
        "/skills",
        "/mcp/servers",
        "/providers",
        "/providers/test",
        "/chat/title",
        "/files/tree",
        "/files/serve",
    ):
        assert route in _surfaces.DESKTOP_USAGE, route


def test_serve_desktop_passes_the_settings_to_the_app(monkeypatch, tmp_path):
    """``_serve_desktop`` is the one caller of ``create_desktop_app``."""
    built: list = []

    async def open_app(config):
        return SimpleNamespace(aclose=_noop)

    monkeypatch.setattr(_surfaces, "open_app", open_app)
    monkeypatch.setattr(_surfaces, "attach_sessions", lambda app: app)
    monkeypatch.setattr(
        _surfaces,
        "create_desktop_app",
        lambda app, **kwargs: built.append(kwargs) or object(),
    )

    class Server:
        def __init__(self, config):
            pass

        async def serve(self):
            return None

    uvicorn = SimpleNamespace(Server=Server, Config=lambda *a, **k: None)
    settings = DotenvSettings(tmp_path / ".env")
    options = SimpleNamespace(host="127.0.0.1", port=0, abandon_grace_s=None)
    assert asyncio.run(_surfaces._serve_desktop(object(), options, "t", uvicorn, settings)) == 0
    assert built == [{"bearer_token": "t", "settings": settings}]


async def _noop():
    return None
