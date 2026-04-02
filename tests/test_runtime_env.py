from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

from omicsclaw.common import runtime_env
from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs
from omicsclaw.interactive import interactive


def test_ensure_numba_cache_dir_sets_writable_default(monkeypatch):
    monkeypatch.delenv("NUMBA_CACHE_DIR", raising=False)
    monkeypatch.delenv("OMICSCLAW_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)

    paths = ensure_runtime_cache_dirs("omicsclaw-test")
    path = paths["numba_cache_dir"]

    assert path.exists()
    assert path.is_dir()
    assert Path(tempfile.gettempdir()) in path.parents or path == Path(tempfile.gettempdir())
    assert paths["xdg_cache_home"].exists()
    assert paths["mplconfigdir"].exists()


def test_ensure_numba_cache_dir_respects_configured_root(monkeypatch, tmp_path):
    monkeypatch.delenv("NUMBA_CACHE_DIR", raising=False)
    monkeypatch.setenv("OMICSCLAW_CACHE_DIR", str(tmp_path / "cache_root"))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)

    paths = ensure_runtime_cache_dirs("omicsclaw-test")
    path = paths["numba_cache_dir"]

    assert paths["xdg_cache_home"] == (tmp_path / "cache_root" / "xdg_cache")
    assert paths["mplconfigdir"] == (tmp_path / "cache_root" / "xdg_cache" / "matplotlib")
    assert path == (tmp_path / "cache_root" / "xdg_cache" / "numba")
    assert path.exists()


def test_load_env_file_fallback_reads_basic_dotenv(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "LLM_PROVIDER=custom",
                "export LLM_BASE_URL=https://example.com/v1",
                'OMICSCLAW_MODEL="demo-model"',
                "LLM_API_KEY=secret-value # inline comment",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OMICSCLAW_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        runtime_env,
        "_load_env_file_with_python_dotenv",
        lambda env_path, *, override: False,
    )

    assert runtime_env.load_env_file(env_path, override=False) is True
    assert os.environ["LLM_PROVIDER"] == "custom"
    assert os.environ["LLM_BASE_URL"] == "https://example.com/v1"
    assert os.environ["OMICSCLAW_MODEL"] == "demo-model"
    assert os.environ["LLM_API_KEY"] == "secret-value"


def test_interactive_init_llm_uses_shared_env_loader(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=custom",
                "LLM_BASE_URL=https://example.com/v1",
                "OMICSCLAW_MODEL=demo-model",
                "LLM_API_KEY=secret-value",
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, str | None] = {}
    core_module = ModuleType("bot.core")
    core_module.OMICSCLAW_MODEL = "demo-model"
    core_module.LLM_PROVIDER_NAME = "custom"

    def _init(**kwargs):
        captured.update(kwargs)
        core_module.OMICSCLAW_MODEL = kwargs["model"] or "demo-model"
        core_module.LLM_PROVIDER_NAME = kwargs["provider"] or "custom"

    core_module.init = _init
    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "_OMICSCLAW_DIR", tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OMICSCLAW_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    model, provider = interactive._init_llm({})

    assert captured == {
        "api_key": "secret-value",
        "base_url": "https://example.com/v1",
        "model": "demo-model",
        "provider": "custom",
    }
    assert model == "demo-model"
    assert provider == "custom"
