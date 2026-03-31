"""Tests for the interactive onboarding wizard."""

from __future__ import annotations

import bot.onboard as onboard


class _FakeQuestion:
    def __init__(self, answer):
        self.answer = answer

    def ask(self):
        return self.answer


def test_prompt_channels_retries_after_empty_submit(monkeypatch):
    checkbox_answers = iter([[], ["feishu"]])
    confirm_calls: list[tuple[str, bool]] = []
    checkbox_instructions: list[str | None] = []

    def fake_checkbox(message, **kwargs):
        checkbox_instructions.append(kwargs.get("instruction"))
        return _FakeQuestion(next(checkbox_answers))

    def fake_confirm(message, default=False, **kwargs):
        confirm_calls.append((message, default))
        return _FakeQuestion(False)

    monkeypatch.setattr(onboard.questionary, "checkbox", fake_checkbox)
    monkeypatch.setattr(onboard.questionary, "confirm", fake_confirm)

    selected = onboard._prompt_channels(
        [
            {"name": "Telegram", "value": "telegram", "env_req": []},
            {"name": "Feishu / Lark", "value": "feishu", "env_req": []},
        ],
        [],
    )

    assert selected == ["feishu"]
    assert checkbox_instructions[0] == "Space=toggle, Enter=confirm. Y/N does not apply on this checklist."
    assert confirm_calls == [
        (
            "No channels selected. On the checklist, use Space to toggle and Enter to confirm; "
            "Y/N only applies to prompts like this one. Continue without any messaging channels?",
            False,
        )
    ]


def test_run_onboard_collects_feishu_credentials(monkeypatch):
    saved_env: dict[str, str] = {}
    text_answers = iter(["qwen2.5:7b", "cli_a123"])
    password_answers = iter(["cli_s456"])
    confirm_answers = iter([True])

    monkeypatch.setattr(onboard, "load_env", lambda: {})
    monkeypatch.setattr(onboard, "save_env", lambda env: saved_env.update(env))
    monkeypatch.setattr(onboard, "_prompt_channels", lambda all_channels, current_active_list: ["feishu"])
    monkeypatch.setattr(onboard.questionary, "select", lambda *args, **kwargs: _FakeQuestion("ollama"))
    monkeypatch.setattr(onboard.questionary, "text", lambda *args, **kwargs: _FakeQuestion(next(text_answers)))
    monkeypatch.setattr(onboard.questionary, "password", lambda *args, **kwargs: _FakeQuestion(next(password_answers)))
    monkeypatch.setattr(onboard.questionary, "confirm", lambda *args, **kwargs: _FakeQuestion(next(confirm_answers)))
    monkeypatch.setattr(onboard.console, "print", lambda *args, **kwargs: None)

    onboard.run_onboard()

    assert saved_env["LLM_PROVIDER"] == "ollama"
    assert saved_env["OMICSCLAW_MODEL"] == "qwen2.5:7b"
    assert saved_env["ACTIVE_CHANNELS"] == "feishu"
    assert saved_env["FEISHU_APP_ID"] == "cli_a123"
    assert saved_env["FEISHU_APP_SECRET"] == "cli_s456"


def test_run_onboard_keeps_existing_feishu_credentials_on_blank_secret(monkeypatch):
    saved_env: dict[str, str] = {}
    text_defaults: list[str] = []
    text_answers = iter(["qwen2.5:7b", "existing_app_id"])
    password_answers = iter([""])
    confirm_answers = iter([True])

    monkeypatch.setattr(
        onboard,
        "load_env",
        lambda: {
            "FEISHU_APP_ID": "existing_app_id",
            "FEISHU_APP_SECRET": "existing_secret",
        },
    )
    monkeypatch.setattr(onboard, "save_env", lambda env: saved_env.update(env))
    monkeypatch.setattr(onboard, "_prompt_channels", lambda all_channels, current_active_list: ["feishu"])
    monkeypatch.setattr(onboard.questionary, "select", lambda *args, **kwargs: _FakeQuestion("ollama"))

    def fake_text(*args, **kwargs):
        text_defaults.append(kwargs.get("default", ""))
        return _FakeQuestion(next(text_answers))

    monkeypatch.setattr(onboard.questionary, "text", fake_text)
    monkeypatch.setattr(onboard.questionary, "password", lambda *args, **kwargs: _FakeQuestion(next(password_answers)))
    monkeypatch.setattr(onboard.questionary, "confirm", lambda *args, **kwargs: _FakeQuestion(next(confirm_answers)))
    monkeypatch.setattr(onboard.console, "print", lambda *args, **kwargs: None)

    onboard.run_onboard()

    assert saved_env["FEISHU_APP_ID"] == "existing_app_id"
    assert saved_env["FEISHU_APP_SECRET"] == "existing_secret"
    assert "existing_app_id" in text_defaults
