from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


class _FakePrompt:
    def __init__(self, value):
        self._value = value

    def ask(self):
        return self._value


class _FakeChoice:
    def __init__(self, title, value=None, checked=False):
        self.title = title
        self.value = value
        self.checked = checked


class _FakeQuestionary:
    Choice = _FakeChoice

    def __init__(self, *, select=None, text=None, password=None, confirm=None, checkbox=None):
        self._answers = {
            "select": list(select or []),
            "text": list(text or []),
            "password": list(password or []),
            "confirm": list(confirm or []),
            "checkbox": list(checkbox or []),
        }

    def Style(self, style):
        return style

    def _next(self, kind: str):
        if not self._answers[kind]:
            raise AssertionError(f"Unexpected {kind} prompt")
        return _FakePrompt(self._answers[kind].pop(0))

    def select(self, *args, **kwargs):
        return self._next("select")

    def text(self, *args, **kwargs):
        return self._next("text")

    def password(self, *args, **kwargs):
        return self._next("password")

    def confirm(self, *args, **kwargs):
        return self._next("confirm")

    def checkbox(self, *args, **kwargs):
        return self._next("checkbox")


class _DummyConsole:
    def print(self, *args, **kwargs):
        return None


class _DummyPanel:
    @staticmethod
    def fit(message, border_style=None):
        return message


def _load_onboard(monkeypatch, tmp_path: Path, fake_questionary: _FakeQuestionary):
    sys.modules.pop("bot.onboard", None)

    rich_module = types.ModuleType("rich")
    rich_console = types.ModuleType("rich.console")
    rich_console.Console = _DummyConsole
    rich_panel = types.ModuleType("rich.panel")
    rich_panel.Panel = _DummyPanel

    monkeypatch.setitem(sys.modules, "questionary", fake_questionary)
    monkeypatch.setitem(sys.modules, "rich", rich_module)
    monkeypatch.setitem(sys.modules, "rich.console", rich_console)
    monkeypatch.setitem(sys.modules, "rich.panel", rich_panel)

    import bot.onboard as onboard

    onboard = importlib.reload(onboard)
    monkeypatch.setattr(onboard, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(onboard, "console", _DummyConsole())
    return onboard


def test_onboard_save_env_updates_and_removes_keys(monkeypatch, tmp_path):
    onboard = _load_onboard(monkeypatch, tmp_path, _FakeQuestionary())
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# header",
                "ACTIVE_CHANNELS=telegram",
                "LLM_PROVIDER=deepseek",
                "OMICSCLAW_DATA_DIRS='/mnt/data one'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    parsed = onboard.load_env()
    assert parsed["OMICSCLAW_DATA_DIRS"] == "/mnt/data one"

    onboard.save_env(
        {
            "ACTIVE_CHANNELS": None,
            "LLM_PROVIDER": "openai",
            "NEW_KEY": "value with space",
        }
    )

    saved = env_path.read_text(encoding="utf-8")
    assert "# header" in saved
    assert "ACTIVE_CHANNELS=" not in saved
    assert "LLM_PROVIDER=openai" in saved
    assert "NEW_KEY='value with space'" in saved


def test_run_onboard_writes_core_runtime_and_channel_config(monkeypatch, tmp_path):
    fake_questionary = _FakeQuestionary(
        select=["deepseek"],
        text=[
            "deepseek-chat",
            "90",
            "12",
            "15",
            "/mnt/nas,/srv/data",
            "user-a,user-b",
            "180",
            "sqlite+aiosqlite:///tmp/omics.db",
            "127.0.0.1",
            "8766",
            "60",
            "5000",
            "25",
            "123456",
            "imap.example.com",
            "993",
            "omics@example.com",
            "smtp.example.com",
            "587",
            "omics@example.com",
            "omics@example.com",
            "INBOX",
            "1",
            "1",
            "30",
            "1",
            "alice@example.com,bob@example.com",
        ],
        password=[
            "sk-test",
            "memory-secret",
            "123:telegram",
            "imap-pass",
            "smtp-pass",
        ],
        confirm=[
            False,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ],
        checkbox=[["telegram", "email"]],
    )
    onboard = _load_onboard(monkeypatch, tmp_path, fake_questionary)

    onboard.run_onboard()

    saved = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=deepseek" in saved
    assert "OMICSCLAW_MODEL=deepseek-chat" in saved
    assert "LLM_API_KEY=sk-test" in saved
    assert "OMICSCLAW_LLM_TIMEOUT_SECONDS=90" in saved
    assert "OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS=12" in saved
    assert "RATE_LIMIT_PER_HOUR=15" in saved
    assert "OMICSCLAW_DATA_DIRS=/mnt/nas,/srv/data" in saved
    assert "ALLOWED_SENDERS=user-a,user-b" in saved
    assert "GLOBAL_RATE_LIMIT=180" in saved
    assert "OMICSCLAW_MEMORY_DB_URL=sqlite+aiosqlite:///tmp/omics.db" in saved
    assert "OMICSCLAW_MEMORY_API_TOKEN=memory-secret" in saved
    assert "OMICSCLAW_MAX_HISTORY=60" in saved
    assert "OMICSCLAW_MAX_HISTORY_CHARS=5000" in saved
    assert "OMICSCLAW_MAX_TOOL_ITERATIONS=25" in saved
    assert "TELEGRAM_BOT_TOKEN=123:telegram" in saved
    assert "TELEGRAM_CHAT_ID=123456" in saved
    assert "EMAIL_IMAP_HOST=imap.example.com" in saved
    assert "EMAIL_SMTP_HOST=smtp.example.com" in saved
    assert "EMAIL_ALLOWED_SENDERS=alice@example.com,bob@example.com" in saved
    assert "ACTIVE_CHANNELS=" not in saved


def test_configure_llm_replaces_legacy_deepseek_default(monkeypatch, tmp_path):
    fake_questionary = _FakeQuestionary(
        select=["deepseek"],
        text=[
            "",
        ],
        password=[""],
        confirm=[False, False],
    )
    onboard = _load_onboard(monkeypatch, tmp_path, fake_questionary)

    env_vars = {
        "LLM_PROVIDER": "deepseek",
        "OMICSCLAW_MODEL": "deepseek-chat",
        "LLM_API_KEY": "old-key",
    }
    ok, provider = onboard._configure_llm(env_vars)

    assert ok is True
    assert provider == "deepseek"
    assert env_vars["OMICSCLAW_MODEL"] == "deepseek-v4-flash"


def test_run_onboard_switches_wechat_backend_and_clears_conflicting_env(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ACTIVE_CHANNELS=wechat",
                "LLM_PROVIDER=deepseek",
                "LLM_API_KEY=old-key",
                "WECOM_CORP_ID=ww-old",
                "WECOM_AGENT_ID=1000001",
                "WECOM_SECRET=old-secret",
                "WECOM_TOKEN=old-token",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    fake_questionary = _FakeQuestionary(
        select=["deepseek", "wechatmp"],
        text=[
            "deepseek-chat",
            "10",
            "",
            "wx123",
        ],
        password=[
            "",
            "wx-secret",
        ],
        confirm=[
            False,
            False,
            False,
            False,
            False,
            False,
            True,
        ],
        checkbox=[["wechat"]],
    )
    onboard = _load_onboard(monkeypatch, tmp_path, fake_questionary)

    onboard.run_onboard()

    saved = env_path.read_text(encoding="utf-8")
    assert "ACTIVE_CHANNELS=" not in saved
    assert "WECHAT_APP_ID=wx123" in saved
    assert "WECHAT_APP_SECRET=wx-secret" in saved
    assert "WECOM_CORP_ID=" not in saved
    assert "WECOM_AGENT_ID=" not in saved
    assert "WECOM_SECRET=" not in saved
    assert "WECOM_TOKEN=" not in saved
    assert "LLM_API_KEY=old-key" in saved
