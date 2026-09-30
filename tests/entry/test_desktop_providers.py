"""``GET/PUT /providers`` and ``POST /providers/test`` as plain functions.

A key is saved under the preset's own variable, and every spelling of
the provider, model and endpoint the file already has is written.

**What "after a restart" means.** The next start loads every candidate
``.env`` in order, the first file to name a variable deciding it, and an
exported variable beats every file. Predicting that from the write
target alone is wrong under Electron, whose working directory is the
project and whose project may carry a ``.env`` of its own; predicting it
from the live process is wrong too, because the live process already
holds the values start-up read from the files. So the in-memory
:class:`Memory` below keeps every candidate file separately, the exported
variables, and the start-up snapshot, and each test says which of them it
is about.

**No secret leaves.** Every listing and every save is serialised whole
and searched for the key, rather than checking the fields one expects a
key to be in: the failure this guards against is a field nobody thought
of.

The comparison with ``oc cli --configure`` drives the real wizard over a
pipe and the pure update function over the same starting file, so a
change to either one's variable-name rules turns this red.
"""

from __future__ import annotations

import asyncio
import io
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from omicsclaw.entry.desktop.providers import (
    DotenvSettings,
    _next_start_config,
    next_start_environment,
    provider_listing,
    provider_settings_updates,
    save_provider,
    test_provider as run_provider_test,
)
from omicsclaw.entry.desktop.turn_submission import DesktopIngressError
from omicsclaw.provider import DETECT_ORDER, PRESETS, ProviderError
from omicsclaw.schema import Message, Role
from omicsclaw.provider.base import Completion

REPO = pathlib.Path(__file__).resolve().parents[2]
SECRET = "sk-live-0123456789abcdefSECRET"
TARGET = pathlib.Path("/virtual/home/.env")
PROJECT = pathlib.Path("/virtual/project/.env")


@dataclass
class Memory:
    """A :class:`~omicsclaw.entry.desktop.providers.SettingsFile` in memory."""

    files: dict[pathlib.Path, dict[str, str]] = field(default_factory=dict)
    exported: dict[str, str] = field(default_factory=dict)
    startup: dict[str, str] = field(default_factory=dict)
    path: pathlib.Path = TARGET
    candidates: tuple[pathlib.Path, ...] = (TARGET, PROJECT)
    writes: list[dict] = field(default_factory=list)

    def read(self):
        return dict(self.files.get(self.path, {}))

    def read_candidates(self):
        return tuple(dict(self.files.get(c, {})) for c in self.candidates)

    def write(self, updates):
        self.writes.append(dict(updates))
        target = self.files.setdefault(self.path, {})
        for key, value in updates.items():
            if value is None:
                target.pop(key, None)
            else:
                target[key] = value


def app(provider: str = "", model: str = "", name: str = "deepseek"):
    return SimpleNamespace(
        config=SimpleNamespace(provider=provider, model=model),
        provider=SimpleNamespace(name=name),
    )


def rows(payload: dict) -> dict[str, dict]:
    return {row["name"]: row for row in payload["providers"]}


# ---- GET /providers ------------------------------------------------------


def test_every_preset_is_listed_detect_order_first():
    payload = provider_listing(app(), Memory())
    names = [row["name"] for row in payload["providers"]]
    assert names[: len(DETECT_ORDER)] == list(DETECT_ORDER)
    assert sorted(names) == sorted(PRESETS)


def test_a_row_carries_the_fields_the_client_reads():
    row = rows(provider_listing(app(), Memory()))["deepseek"]
    preset = PRESETS["deepseek"]
    assert row["display_name"] == "DeepSeek"
    assert row["tier"] == "primary"
    assert row["base_url"] == preset.base_url
    assert row["default_model"] == preset.default_model
    assert row["env_key"] == "DEEPSEEK_API_KEY"
    assert preset.default_model in row["models"]
    assert all(
        set(entry) == {"id", "context_window"} and entry["context_window"] > 0
        for entry in row["model_metadata"]
    )
    assert "oauth_supported" not in row and "description" not in row


def test_a_provider_key_configures_its_row():
    settings = Memory(files={TARGET: {"DEEPSEEK_API_KEY": SECRET}})
    listed = rows(provider_listing(app(), settings))
    assert (listed["deepseek"]["configured"], listed["deepseek"]["configured_via"]) == (
        True,
        "provider-env",
    )
    assert (listed["openai"]["configured"], listed["openai"]["configured_via"]) == (
        False,
        None,
    )


def test_a_generic_key_configures_the_named_provider():
    settings = Memory(files={TARGET: {"LLM_PROVIDER": "zhipu", "LLM_API_KEY": SECRET}})
    listed = rows(provider_listing(app(), settings))
    assert listed["zhipu"]["configured_via"] == "generic-env"
    assert listed["deepseek"]["configured"] is False


def test_custom_takes_the_generic_key_when_no_provider_is_named():
    """``resolve_config("custom")`` reads ``LLM_API_KEY`` while
    ``LLM_PROVIDER`` is unset (``provider/config.py``). Shown as it is."""
    settings = Memory(files={TARGET: {"LLM_API_KEY": SECRET}})
    listed = rows(provider_listing(app(), settings))
    assert (listed["custom"]["configured"], listed["custom"]["configured_via"]) == (
        True,
        "generic-env",
    )


def test_ollama_named_as_the_provider_is_explicitly_configured():
    settings = Memory(files={TARGET: {"LLM_PROVIDER": "ollama"}})
    listed = rows(provider_listing(app(), settings))
    assert (listed["ollama"]["configured"], listed["ollama"]["configured_via"]) == (
        True,
        "explicit-provider",
    )
    assert rows(provider_listing(app(), Memory()))["ollama"]["configured"] is False


def test_the_first_candidate_file_wins_and_an_export_beats_both():
    settings = Memory(
        files={
            TARGET: {"LLM_PROVIDER": "openai"},
            PROJECT: {"LLM_PROVIDER": "zhipu", "ZHIPU_API_KEY": SECRET},
        }
    )
    payload = provider_listing(app(provider="openai"), settings)
    assert rows(payload)["zhipu"]["configured"] is True  # the second file is read
    settings.startup = {"LLM_PROVIDER": "openai"}
    assert provider_listing(app(provider="openai"), settings)["restart_pending"] is False

    settings.exported = {"LLM_PROVIDER": "zhipu"}
    assert provider_listing(app(provider="openai"), settings)["restart_pending"] is True


def test_the_running_triple_comes_from_the_start_up_snapshot():
    """The file changing after start-up does not change what is running."""
    settings = Memory(
        files={TARGET: {"LLM_PROVIDER": "zhipu", "ZHIPU_API_KEY": SECRET}},
        startup={"DEEPSEEK_API_KEY": SECRET},
    )
    payload = provider_listing(app(), settings)
    assert payload["current"] == "deepseek"
    assert payload["current_model"] == PRESETS["deepseek"].default_model
    assert payload["restart_pending"] is True


def test_nothing_changed_means_no_restart_pending():
    env = {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": SECRET, "LLM_MODEL": "m1"}
    settings = Memory(files={TARGET: dict(env)}, startup=dict(env))
    payload = provider_listing(app(provider="deepseek", model="m1"), settings)
    assert payload["restart_pending"] is False
    assert payload["current_model"] == "m1"
    assert payload["env_file"] == str(TARGET)


def test_omicsclaw_provider_in_the_file_decides_the_restart_triple():
    settings = Memory(
        files={TARGET: {"OMICSCLAW_PROVIDER": "zhipu", "LLM_PROVIDER": "openai"}},
        startup={"OMICSCLAW_PROVIDER": "zhipu", "LLM_PROVIDER": "openai"},
    )
    assert provider_listing(app(provider="zhipu"), settings)["restart_pending"] is False
    assert provider_listing(app(provider="openai"), settings)["restart_pending"] is True


def test_active_is_the_running_providers_name():
    listed = rows(provider_listing(app(name="zhipu"), Memory()))
    assert [name for name, row in listed.items() if row["active"]] == ["zhipu"]


def test_without_settings_nothing_is_configured_and_the_file_is_unknown():
    settings = None
    payload = provider_listing(app(name="deepseek"), settings)
    assert not any(row["configured"] for row in payload["providers"])
    assert payload["env_file"] is None
    assert payload["restart_pending"] is False
    assert payload["current"] == "deepseek"


def test_no_key_appears_anywhere_in_a_listing():
    settings = Memory(
        files={
            TARGET: {"DEEPSEEK_API_KEY": SECRET, "LLM_API_KEY": SECRET + "2"},
            PROJECT: {"OPENAI_API_KEY": SECRET + "3"},
        },
        exported={"ANTHROPIC_API_KEY": SECRET + "4"},
        startup={"DEEPSEEK_API_KEY": SECRET},
    )
    text = json.dumps(provider_listing(app(), settings))
    assert SECRET not in text
    assert SECRET[-4:] not in text


def test_configured_base_url_is_the_endpoint_the_next_start_resolves():
    """The client pre-fills the endpoint field from it, so a save that sends
    the field back keeps a remote endpoint set elsewhere (the CLI, by hand)
    instead of writing ``""`` over it."""
    settings = Memory(
        files={
            TARGET: {"LLM_PROVIDER": "deepseek", "OLLAMA_BASE_URL": "http://gpu:11434/v1"},
            PROJECT: {"LLM_BASE_URL": "https://proxy.example/v1"},
        }
    )
    listed = rows(provider_listing(app(), settings))
    assert listed["ollama"]["configured_base_url"] == "http://gpu:11434/v1"
    assert listed["deepseek"]["configured_base_url"] == "https://proxy.example/v1"
    assert listed["zhipu"]["configured_base_url"] == PRESETS["zhipu"].base_url
    assert listed["openai"]["configured_base_url"] == ""
    assert listed["custom"]["configured_base_url"] == ""


def test_configured_base_url_follows_what_an_export_overrides():
    settings = Memory(
        files={TARGET: {"OLLAMA_BASE_URL": "http://file:11434/v1"}},
        exported={"OLLAMA_BASE_URL": "http://exported:11434/v1"},
    )
    listed = rows(provider_listing(app(), settings))
    assert listed["ollama"]["configured_base_url"] == "http://exported:11434/v1"


def test_a_whitespace_key_does_not_configure_a_row():
    settings = Memory(files={TARGET: {"DEEPSEEK_API_KEY": "   ", "LLM_API_KEY": " "}})
    listed = rows(provider_listing(app(), settings))
    assert (listed["deepseek"]["configured"], listed["deepseek"]["configured_via"]) == (
        False,
        None,
    )
    assert listed["custom"]["configured"] is False


def test_explicit_provider_reads_the_provider_as_resolve_config_does():
    """``resolve_config`` reads ``LLM_PROVIDER`` before ``OMICSCLAW_PROVIDER``
    when it decides whether the generic variables apply."""
    settings = Memory(
        files={TARGET: {"LLM_PROVIDER": "custom", "OMICSCLAW_PROVIDER": "ollama"}}
    )
    listed = rows(provider_listing(app(), settings))
    assert listed["ollama"]["configured"] is False


# ---- PUT /providers: validation -----------------------------------------


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"provider": "deepseek", "auth_mode": "api_key"}, "unknown_field"),
        ({"provider": "nope"}, "unknown_provider"),
        ({}, "unknown_provider"),
        ({"provider": 3}, "invalid_value"),
        ({"provider": "deepseek", "model": 3}, "invalid_value"),
        ({"provider": "deepseek", "api_key": "a\nb"}, "invalid_value"),
        ({"provider": "deepseek", "base_url": "x" * 4097}, "invalid_value"),
        ({"provider": "custom", "model": "m"}, "custom_endpoint_required"),
        ({"provider": "custom", "base_url": "http://h"}, "custom_endpoint_required"),
    ],
)
def test_a_bad_save_is_refused_before_anything_is_written(document, code):
    settings = Memory()
    with pytest.raises(DesktopIngressError) as caught:
        save_provider(app(), settings, document)
    assert (caught.value.code, caught.value.status_code) == (code, 422)
    assert settings.writes == []


def test_without_settings_a_save_is_unavailable():
    with pytest.raises(DesktopIngressError) as caught:
        save_provider(app(), None, {"provider": "deepseek"})
    assert (caught.value.code, caught.value.status_code) == ("settings_unavailable", 503)


# ---- PUT /providers: what is written -------------------------------------


def test_a_key_is_saved_under_the_presets_variable():
    """Q9 = a: saving openai does not overwrite deepseek's key."""
    settings = Memory(files={TARGET: {"DEEPSEEK_API_KEY": "kept"}})
    result = save_provider(app(), settings, {"provider": "openai", "api_key": SECRET})
    assert settings.files[TARGET]["OPENAI_API_KEY"] == SECRET
    assert settings.files[TARGET]["DEEPSEEK_API_KEY"] == "kept"
    assert "OPENAI_API_KEY" in result["written"]


def test_custom_saves_its_key_as_the_generic_variable():
    settings = Memory()
    save_provider(
        app(),
        settings,
        {"provider": "custom", "api_key": SECRET, "model": "m", "base_url": "http://h/v1"},
    )
    written = settings.files[TARGET]
    assert written["LLM_API_KEY"] == SECRET
    assert (written["LLM_MODEL"], written["LLM_BASE_URL"]) == ("m", "http://h/v1")


def test_an_empty_key_leaves_the_stored_one_alone():
    settings = Memory(files={TARGET: {"DEEPSEEK_API_KEY": "kept"}})
    result = save_provider(app(), settings, {"provider": "deepseek", "api_key": ""})
    assert settings.files[TARGET]["DEEPSEEK_API_KEY"] == "kept"
    assert "DEEPSEEK_API_KEY" not in result["written"]


def test_switching_resets_the_model_and_clears_the_endpoint():
    """The CLI's rule: a vendor's leftover base URL must not hijack the next."""
    settings = Memory(
        files={
            TARGET: {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-5.5",
                "LLM_BASE_URL": "https://proxy.example/v1",
            }
        }
    )
    save_provider(app(), settings, {"provider": "zhipu"})
    written = settings.files[TARGET]
    assert written["LLM_PROVIDER"] == "zhipu"
    assert written["LLM_MODEL"] == PRESETS["zhipu"].default_model
    assert written["LLM_BASE_URL"] == ""


def test_the_same_provider_writes_only_what_was_given():
    settings = Memory(
        files={TARGET: {"LLM_PROVIDER": "zhipu", "LLM_MODEL": "glm-x", "LLM_BASE_URL": "u"}}
    )
    result = save_provider(app(), settings, {"provider": "zhipu", "api_key": SECRET})
    written = settings.files[TARGET]
    assert (written["LLM_MODEL"], written["LLM_BASE_URL"]) == ("glm-x", "u")
    assert result["written"] == ["LLM_PROVIDER", "ZHIPU_API_KEY"]


def test_an_existing_higher_precedence_spelling_is_the_one_written():
    """The CLI's rule for the provider, the model and the endpoint."""
    settings = Memory(
        files={
            TARGET: {
                "OMICSCLAW_PROVIDER": "openai",
                "OMICSCLAW_MODEL": "gpt-5.5",
                "ZHIPU_BASE_URL": "https://mirror/v4",
            }
        }
    )
    result = save_provider(
        app(),
        settings,
        {"provider": "zhipu", "model": "glm-5.1", "base_url": "https://mirror2/v4"},
    )
    written = settings.files[TARGET]
    assert written["OMICSCLAW_PROVIDER"] == "zhipu"
    assert "LLM_PROVIDER" not in written
    assert written["OMICSCLAW_MODEL"] == "glm-5.1"
    assert written["ZHIPU_BASE_URL"] == "https://mirror2/v4"
    assert result["provider"] == "zhipu" and result["model"] == "glm-5.1"


def test_a_file_with_both_provider_spellings_gets_both_written():
    """``AppConfig`` reads ``OMICSCLAW_PROVIDER`` first and ``resolve_config``
    reads ``LLM_PROVIDER`` first; a stale one of the two would, for
    ``custom``, leave the next start with no endpoint and no key."""
    settings = Memory(
        files={TARGET: {"OMICSCLAW_PROVIDER": "openai", "LLM_PROVIDER": "openai"}}
    )
    result = save_provider(
        app(),
        settings,
        {"provider": "custom", "api_key": SECRET, "model": "m", "base_url": "http://h/v1"},
    )
    written = settings.files[TARGET]
    assert (written["OMICSCLAW_PROVIDER"], written["LLM_PROVIDER"]) == ("custom", "custom")
    assert result["written"][:2] == ["OMICSCLAW_PROVIDER", "LLM_PROVIDER"]
    from omicsclaw.entry.desktop.providers import next_start_environment
    from omicsclaw.provider import resolve_config

    env = next_start_environment(settings)
    resolved = resolve_config(env["OMICSCLAW_PROVIDER"], env["LLM_MODEL"], env=env)
    assert (resolved.base_url, resolved.api_key) == ("http://h/v1", SECRET)


def test_a_save_reports_what_an_export_will_keep_from_taking_effect():
    settings = Memory(exported={"LLM_MODEL": "pinned", "OMICSCLAW_PROVIDER": "openai"})
    result = save_provider(
        app(), settings, {"provider": "zhipu", "model": "glm-5.1", "api_key": SECRET}
    )
    assert result["shadowed_by_environment"] == ["OMICSCLAW_PROVIDER", "LLM_MODEL"]
    assert result["provider"] == "openai"  # what the next start will run
    assert result["restart_required"] is True


def test_an_exported_higher_spelling_of_the_model_or_endpoint_is_reported():
    settings = Memory(
        exported={"OMICSCLAW_MODEL": "pinned", "ZHIPU_BASE_URL": "https://x", "EMPTY": ""}
    )
    result = save_provider(
        app(), settings, {"provider": "zhipu", "model": "glm-5.1", "base_url": "https://y"}
    )
    assert result["shadowed_by_environment"] == ["OMICSCLAW_MODEL", "ZHIPU_BASE_URL"]


def test_a_file_with_both_generic_endpoints_gets_both_cleared_on_a_switch():
    """Readers skip an empty variable, so clearing only ``LLM_BASE_URL``
    would let the old vendor's ``OMICSCLAW_BASE_URL`` through."""
    settings = Memory(
        files={
            TARGET: {
                "LLM_PROVIDER": "openai",
                "LLM_BASE_URL": "https://proxy.example/v1",
                "OMICSCLAW_BASE_URL": "https://proxy.example/v1",
            }
        }
    )
    save_provider(app(), settings, {"provider": "zhipu", "api_key": SECRET})
    written = settings.files[TARGET]
    assert written["LLM_BASE_URL"] == written["OMICSCLAW_BASE_URL"] == ""
    env = next_start_environment(settings)
    assert _next_start_config(env).base_url == PRESETS["zhipu"].base_url


def test_an_exported_lower_provider_spelling_that_disagrees_is_reported():
    """``resolve_config`` reads ``LLM_PROVIDER`` first, so an exported one
    naming another vendor keeps the generic endpoint and key from applying."""
    settings = Memory(
        files={TARGET: {"OMICSCLAW_PROVIDER": "openai"}},
        exported={"LLM_PROVIDER": "openai"},
    )
    result = save_provider(
        app(),
        settings,
        {"provider": "custom", "api_key": SECRET, "model": "m", "base_url": "http://h/v1"},
    )
    assert result["written"][0] == "OMICSCLAW_PROVIDER"
    assert result["shadowed_by_environment"] == ["LLM_PROVIDER"]


def test_an_export_that_agrees_with_the_save_is_not_reported():
    settings = Memory(
        exported={"LLM_PROVIDER": "zhipu", "OMICSCLAW_MODEL": "glm-5.1", "LLM_MODEL": "glm-5.1"}
    )
    result = save_provider(app(), settings, {"provider": "zhipu", "model": "glm-5.1"})
    assert result["shadowed_by_environment"] == []


def test_an_exported_lower_endpoint_is_reported_when_the_save_clears_it():
    settings = Memory(
        files={TARGET: {"LLM_PROVIDER": "openai"}},
        exported={"OMICSCLAW_BASE_URL": "https://proxy.example/v1"},
    )
    result = save_provider(app(), settings, {"provider": "zhipu", "base_url": ""})
    assert result["shadowed_by_environment"] == ["OMICSCLAW_BASE_URL"]


def test_the_save_response_carries_no_key():
    settings = Memory()
    result = save_provider(app(), settings, {"provider": "deepseek", "api_key": SECRET})
    assert SECRET not in json.dumps(result)
    assert result["env_file"] == str(TARGET)
    assert result["ok"] is True


def test_the_update_rule_is_a_pure_function():
    updates = provider_settings_updates(
        {"LLM_PROVIDER": "openai"},
        provider="deepseek",
        api_key=SECRET,
        model=None,
        base_url=None,
        previous_provider="openai",
    )
    assert updates == {
        "LLM_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": SECRET,
        "LLM_MODEL": PRESETS["deepseek"].default_model,
        "LLM_BASE_URL": "",
    }


# ---- the same rules as ``oc cli --configure`` ----------------------------


def _wizard(path: pathlib.Path, answers: list[str]) -> dict[str, str]:
    from omicsclaw.entry.cli import run_configuration_wizard
    from omicsclaw.entry.cli._configure import StreamPrompter, read_dotenv

    sink = io.StringIO()
    source = io.StringIO("".join(f"{line}\n" for line in answers))
    assert run_configuration_wizard(
        path, prompter=StreamPrompter(source, sink), sink=sink
    ) == path
    return read_dotenv(path)


LLM_NAMES = (
    "LLM_PROVIDER",
    "OMICSCLAW_PROVIDER",
    "LLM_MODEL",
    "OMICSCLAW_MODEL",
    "LLM_BASE_URL",
    "OMICSCLAW_BASE_URL",
    "DEEPSEEK_BASE_URL",
    "ZHIPU_BASE_URL",
)


@pytest.mark.parametrize(
    ("initial", "answers", "request_"),
    [
        (  # switching vendor: model and endpoint are reset
            "LLM_PROVIDER=openai\nLLM_API_KEY=old\nLLM_MODEL=gpt-5.5\n"
            "LLM_BASE_URL=https://proxy/v1\n",
            ["deepseek", SECRET, "", "", "", "n", "n", "n", "y"],
            {"provider": "deepseek", "api_key": SECRET},
        ),
        (  # same vendor, higher spellings already in the file
            "LLM_PROVIDER=zhipu\nOMICSCLAW_MODEL=glm-4\nZHIPU_BASE_URL=https://a/v4\n",
            ["zhipu", SECRET, "glm-5.1", "https://b/v4", "", "n", "n", "n", "y"],
            {
                "provider": "zhipu",
                "api_key": SECRET,
                "model": "glm-5.1",
                "base_url": "https://b/v4",
            },
        ),
    ],
)
def test_the_save_writes_what_the_cli_wizard_writes(tmp_path, initial, answers, request_):
    """Same provider, model and endpoint variables and values as the CLI.

    The one deliberate difference: the key goes to the preset's own
    variable, where the CLI writes ``LLM_API_KEY`` unless the file
    already has the preset's variable.
    """
    cli_file = tmp_path / "cli" / ".env"
    cli_file.parent.mkdir()
    cli_file.write_text(initial, encoding="utf-8")
    by_cli = _wizard(cli_file, answers)

    app_file = tmp_path / "app" / ".env"
    app_file.parent.mkdir()
    app_file.write_text(initial, encoding="utf-8")
    settings = DotenvSettings(app_file, candidates=(app_file,), exported={}, startup={})
    save_provider(app(), settings, request_)
    by_app = settings.read()

    assert {k: by_cli.get(k) for k in LLM_NAMES} == {k: by_app.get(k) for k in LLM_NAMES}

    preset = PRESETS[request_["provider"]]
    cli_key = "LLM_API_KEY" if preset.api_key_env not in by_cli or preset.api_key_env == "" else preset.api_key_env
    assert by_cli[cli_key] == SECRET
    assert by_app[preset.api_key_env] == SECRET
    key_names = {"LLM_API_KEY", preset.api_key_env}
    assert {k for k in key_names if by_cli.get(k) == SECRET} != {
        k for k in key_names if by_app.get(k) == SECRET
    }


def test_with_omicsclaw_provider_in_the_file_the_save_and_the_cli_both_take_effect(
    tmp_path,
):
    """Against the wizard: a file holding both provider spellings
    gets the new vendor in both, from the App and from the CLI alike, so
    ``AppConfig`` (``OMICSCLAW_PROVIDER`` first) runs it after a restart."""
    initial = (
        "OMICSCLAW_PROVIDER=openai\nLLM_PROVIDER=openai\nLLM_MODEL=gpt-5.5\n"
        "LLM_BASE_URL=https://proxy/v1\n"
    )
    cli_file = tmp_path / "cli" / ".env"
    cli_file.parent.mkdir()
    cli_file.write_text(initial, encoding="utf-8")
    by_cli = _wizard(cli_file, ["deepseek", SECRET, "", "", "", "n", "n", "n", "y"])

    app_file = tmp_path / "app" / ".env"
    app_file.parent.mkdir()
    app_file.write_text(initial, encoding="utf-8")
    settings = DotenvSettings(app_file, candidates=(app_file,), exported={}, startup={})
    result = save_provider(app(), settings, {"provider": "deepseek", "api_key": SECRET})
    by_app = settings.read()

    assert {k: by_cli.get(k) for k in LLM_NAMES} == {k: by_app.get(k) for k in LLM_NAMES}
    assert (by_cli["OMICSCLAW_PROVIDER"], by_cli["LLM_PROVIDER"]) == ("deepseek", "deepseek")
    assert result["provider"] == "deepseek"
    cli_settings = DotenvSettings(cli_file, candidates=(cli_file,), exported={}, startup={})
    by_cli_next = _next_start_config(next_start_environment(cli_settings))
    assert by_cli_next.provider == "deepseek"


# ---- DotenvSettings on a real file ----------------------------------------


def test_dotenv_settings_rewrites_only_the_keys_it_is_given(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# a comment\nUNRELATED=keep me\nLLM_PROVIDER=openai\n\nexport OTHER=1\n",
        encoding="utf-8",
    )
    settings = DotenvSettings(path, candidates=(path,), exported={}, startup={})
    save_provider(app(), settings, {"provider": "zhipu", "api_key": SECRET})

    text = path.read_text(encoding="utf-8")
    assert text.startswith("# a comment\nUNRELATED=keep me\nLLM_PROVIDER=zhipu\n\nexport OTHER=1\n")
    assert f"ZHIPU_API_KEY={SECRET}" in text
    assert list(tmp_path.glob(".env.backup-*"))


def test_a_file_that_is_not_utf8_is_a_500_and_is_left_alone(tmp_path):
    path = tmp_path / ".env"
    original = b"LLM_PROVIDER=openai\nNAME=\xff\xfe\n"
    path.write_bytes(original)
    settings = DotenvSettings(path, candidates=(path,), exported={}, startup={})

    with pytest.raises(DesktopIngressError) as caught:
        save_provider(app(), settings, {"provider": "zhipu"})
    assert (caught.value.code, caught.value.status_code) == ("env_write_failed", 500)
    assert path.read_bytes() == original
    # the listing still answers, reading that file as empty
    assert provider_listing(app(), settings)["env_file"] == str(path)


def test_dotenv_settings_reads_every_candidate(tmp_path):
    first, second = tmp_path / "a.env", tmp_path / "b.env"
    first.write_text("LLM_PROVIDER=zhipu\n", encoding="utf-8")
    second.write_text("LLM_PROVIDER=openai\nZHIPU_API_KEY=k\n", encoding="utf-8")
    settings = DotenvSettings(
        first, candidates=(first, second, tmp_path / "missing"), exported={}, startup={}
    )
    assert settings.read_candidates() == (
        {"LLM_PROVIDER": "zhipu"},
        {"LLM_PROVIDER": "openai", "ZHIPU_API_KEY": "k"},
        {},
    )
    assert rows(provider_listing(app(), settings))["zhipu"]["configured"] is True


def test_importing_the_package_does_not_import_the_cli():
    """``DotenvSettings`` imports the ``.env`` helpers inside its methods,
    so ``import omicsclaw.entry.desktop`` stays as light as it was."""
    probe = (
        "import sys, omicsclaw.entry.desktop\n"
        "print(any(m.startswith('omicsclaw.entry.cli') for m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


# ---- POST /providers/test ------------------------------------------------


class Replying:
    def __init__(self, text: str = "pong", error: BaseException | None = None, delay: float = 0.0):
        self.text, self.error, self.delay = text, error, delay
        self.configs: list = []
        self.seen: list = []

    def __call__(self, config):
        self.configs.append(config)
        return self

    async def generate(self, messages, tools=None):
        self.seen.append((tuple(messages), tools))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return Completion(message=Message(role=Role.ASSISTANT, content=self.text))


def run(coro):
    return asyncio.run(coro)


def test_a_call_that_returns_passes_even_with_an_empty_body():
    factory = Replying(text="")
    settings = Memory(files={TARGET: {"DEEPSEEK_API_KEY": SECRET}})
    result = run(
        run_provider_test(settings, {"provider": "deepseek"}, provider_factory=factory)
    )
    assert result["ok"] is True
    assert result["message"] == "Live provider test passed."
    assert result["provider"] == "deepseek"
    assert result["model"] == PRESETS["deepseek"].default_model
    assert isinstance(result["duration_ms"], int)
    config = factory.configs[0]
    assert config.api_key == SECRET
    assert (config.max_retries, config.max_tokens, config.thinking_budget_tokens) == (0, 256, 0)
    assert config.timeout_seconds == 15
    assert factory.seen[0][1] is None


def test_a_key_in_the_request_is_the_one_used():
    factory = Replying()
    settings = Memory(files={TARGET: {"DEEPSEEK_API_KEY": "stored"}})
    run(
        run_provider_test(
            settings,
            {"provider": "deepseek", "api_key": SECRET, "model": "m", "base_url": "https://b"},
            provider_factory=factory,
        )
    )
    config = factory.configs[0]
    assert (config.api_key, config.model, config.base_url) == (SECRET, "m", "https://b")


def test_a_failure_names_the_error_without_the_key():
    """S20: some vendors echo part of the key back in a 401."""
    error = ProviderError(f"invalid key {SECRET} rejected", provider="deepseek", status_code=401)
    factory = Replying(error=error)
    result = run(
        run_provider_test(
            Memory(), {"provider": "deepseek", "api_key": SECRET}, provider_factory=factory
        )
    )
    assert result["ok"] is False
    assert SECRET not in json.dumps(result)
    assert "invalid key" in result["message"]
    assert result["detail"] == "ProviderError (HTTP 401)"
    assert len(result["message"]) <= 300


def test_a_hung_call_is_a_timeout_failure():
    factory = Replying(delay=5)
    result = run(
        run_provider_test(
            Memory(), {"provider": "deepseek"}, provider_factory=factory, timeout_s=0.05
        )
    )
    assert result["ok"] is False
    assert result["detail"] == "TimeoutError"


def test_an_adapter_that_cannot_be_built_is_a_failure_not_a_crash():
    def factory(config):
        raise ImportError("no SDK")

    result = run(run_provider_test(Memory(), {"provider": "anthropic"}, provider_factory=factory))
    assert (result["ok"], result["detail"]) == (False, "ImportError")


def test_the_adapter_is_closed_after_the_call():
    closed: list = []

    class Closing(Replying):
        async def aclose(self):
            closed.append(True)

    factory = Closing(error=RuntimeError("boom"))
    run(run_provider_test(Memory(), {"provider": "deepseek"}, provider_factory=factory))
    assert closed == [True]


def test_a_test_with_a_bad_request_is_refused():
    with pytest.raises(DesktopIngressError) as caught:
        run(run_provider_test(Memory(), {"provider": "nope"}, provider_factory=Replying()))
    assert caught.value.status_code == 422
    with pytest.raises(DesktopIngressError) as caught:
        run(run_provider_test(None, {"provider": "deepseek"}, provider_factory=Replying()))
    assert (caught.value.code, caught.value.status_code) == ("settings_unavailable", 503)
