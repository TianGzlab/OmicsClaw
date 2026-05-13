"""
bot/onboard.py — Interactive Setup Wizard for OmicsClaw
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from omicsclaw.core.provider_registry import (
    PROVIDER_CHOICES,
    PROVIDER_PRESETS,
    detect_provider_from_env,
    normalize_model_for_provider,
)

try:
    import questionary
    from rich.console import Console
    from rich.panel import Panel
except ImportError:
    print("Error: Missing required packages for onboarding.")
    print("Please run: pip install rich questionary")
    raise SystemExit(1)


console = Console()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
_STYLE = questionary.Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:green bold"),
        ("selected", "fg:green bold"),
        ("pointer", "fg:green"),
    ]
)


@dataclass(frozen=True)
class FieldSpec:
    key: str
    prompt: str
    required: bool = False
    secret: bool = False
    default: str = ""


@dataclass(frozen=True)
class ChannelSpec:
    label: str
    detect_keys: tuple[str, ...]
    required_fields: tuple[FieldSpec, ...]
    optional_fields: tuple[FieldSpec, ...] = ()
    deps: tuple[str, ...] = ()


CHANNEL_SPECS: dict[str, ChannelSpec] = {
    "telegram": ChannelSpec(
        label="Telegram",
        detect_keys=("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
        required_fields=(
            FieldSpec(
                "TELEGRAM_BOT_TOKEN",
                "Telegram Bot Token (from @BotFather)",
                required=True,
                secret=True,
            ),
        ),
        optional_fields=(
            FieldSpec("TELEGRAM_CHAT_ID", "Telegram admin chat ID", default=""),
        ),
        deps=("python-telegram-bot>=21.0",),
    ),
    "feishu": ChannelSpec(
        label="Feishu / Lark",
        detect_keys=("FEISHU_APP_ID", "FEISHU_APP_SECRET"),
        required_fields=(
            FieldSpec("FEISHU_APP_ID", "Feishu App ID", required=True),
            FieldSpec("FEISHU_APP_SECRET", "Feishu App Secret", required=True, secret=True),
        ),
        optional_fields=(
            FieldSpec(
                "FEISHU_THINKING_THRESHOLD_MS",
                "Thinking placeholder threshold in ms",
                default="2500",
            ),
            FieldSpec("FEISHU_MAX_INBOUND_IMAGE_MB", "Max inbound image size (MB)", default="12"),
            FieldSpec("FEISHU_MAX_INBOUND_FILE_MB", "Max inbound file size (MB)", default="40"),
            FieldSpec("FEISHU_MAX_ATTACHMENTS", "Max attachments per message", default="4"),
            FieldSpec("FEISHU_RATE_LIMIT_PER_HOUR", "Feishu rate limit per hour", default="60"),
            FieldSpec("FEISHU_BRIDGE_DEBUG", "Enable bridge debug logging (0/1)", default="0"),
        ),
        deps=("lark-oapi>=1.3.0",),
    ),
    "dingtalk": ChannelSpec(
        label="DingTalk",
        detect_keys=("DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET"),
        required_fields=(
            FieldSpec("DINGTALK_CLIENT_ID", "DingTalk Client ID / AppKey", required=True),
            FieldSpec(
                "DINGTALK_CLIENT_SECRET",
                "DingTalk Client Secret",
                required=True,
                secret=True,
            ),
        ),
        optional_fields=(
            FieldSpec("DINGTALK_RATE_LIMIT_PER_HOUR", "DingTalk rate limit per hour", default="60"),
        ),
        deps=("aiohttp>=3.9",),
    ),
    "discord": ChannelSpec(
        label="Discord",
        detect_keys=("DISCORD_BOT_TOKEN", "DISCORD_PROXY"),
        required_fields=(
            FieldSpec("DISCORD_BOT_TOKEN", "Discord Bot Token", required=True, secret=True),
        ),
        optional_fields=(
            FieldSpec("DISCORD_RATE_LIMIT_PER_HOUR", "Discord rate limit per hour", default="60"),
            FieldSpec("DISCORD_PROXY", "Discord proxy URL", default=""),
        ),
        deps=("discord.py>=2.3",),
    ),
    "slack": ChannelSpec(
        label="Slack",
        detect_keys=("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"),
        required_fields=(
            FieldSpec("SLACK_BOT_TOKEN", "Slack Bot Token (xoxb-...)", required=True, secret=True),
            FieldSpec("SLACK_APP_TOKEN", "Slack App Token (xapp-...)", required=True, secret=True),
        ),
        optional_fields=(
            FieldSpec("SLACK_RATE_LIMIT_PER_HOUR", "Slack rate limit per hour", default="60"),
        ),
        deps=("slack-sdk>=3.27", "aiohttp>=3.9"),
    ),
    "wechat": ChannelSpec(
        label="WeChat / WeCom",
        detect_keys=(
            "WECOM_CORP_ID",
            "WECOM_AGENT_ID",
            "WECOM_SECRET",
            "WECHAT_APP_ID",
            "WECHAT_APP_SECRET",
        ),
        required_fields=(),
        deps=("pycryptodome>=3.20", "aiohttp>=3.9", "httpx"),
    ),
    "qq": ChannelSpec(
        label="QQ",
        detect_keys=("QQ_APP_ID", "QQ_APP_SECRET", "QQ_ALLOWED_SENDERS"),
        required_fields=(
            FieldSpec("QQ_APP_ID", "QQ App ID", required=True),
            FieldSpec("QQ_APP_SECRET", "QQ App Secret", required=True, secret=True),
        ),
        optional_fields=(
            FieldSpec("QQ_ALLOWED_SENDERS", "QQ allowed senders (comma-separated)", default=""),
            FieldSpec("QQ_RATE_LIMIT_PER_HOUR", "QQ rate limit per hour", default="60"),
        ),
        deps=("qq-botpy>=1.0",),
    ),
    "email": ChannelSpec(
        label="Email",
        detect_keys=(
            "EMAIL_IMAP_HOST",
            "EMAIL_IMAP_USERNAME",
            "EMAIL_SMTP_HOST",
            "EMAIL_SMTP_USERNAME",
        ),
        required_fields=(
            FieldSpec("EMAIL_IMAP_HOST", "IMAP host", required=True),
            FieldSpec("EMAIL_IMAP_PORT", "IMAP port", required=True, default="993"),
            FieldSpec("EMAIL_IMAP_USERNAME", "IMAP username", required=True),
            FieldSpec("EMAIL_IMAP_PASSWORD", "IMAP password / app password", required=True, secret=True),
            FieldSpec("EMAIL_SMTP_HOST", "SMTP host", required=True),
            FieldSpec("EMAIL_SMTP_PORT", "SMTP port", required=True, default="587"),
            FieldSpec("EMAIL_SMTP_USERNAME", "SMTP username", required=True),
            FieldSpec("EMAIL_SMTP_PASSWORD", "SMTP password / app password", required=True, secret=True),
        ),
        optional_fields=(
            FieldSpec("EMAIL_FROM_ADDRESS", "Sender address", default=""),
            FieldSpec("EMAIL_IMAP_MAILBOX", "IMAP mailbox", default="INBOX"),
            FieldSpec("EMAIL_IMAP_USE_SSL", "Use IMAP SSL (1/0)", default="1"),
            FieldSpec("EMAIL_SMTP_STARTTLS", "Use SMTP STARTTLS (1/0)", default="1"),
            FieldSpec("EMAIL_POLL_INTERVAL", "Email poll interval in seconds", default="30"),
            FieldSpec("EMAIL_MARK_SEEN", "Mark processed mail as seen (1/0)", default="1"),
            FieldSpec("EMAIL_ALLOWED_SENDERS", "Allowed senders (comma-separated)", default=""),
        ),
    ),
    "imessage": ChannelSpec(
        label="iMessage (macOS)",
        detect_keys=("IMESSAGE_CLI_PATH", "IMESSAGE_ALLOWED_SENDERS"),
        required_fields=(),
        optional_fields=(
            FieldSpec("IMESSAGE_CLI_PATH", "Path to imsg CLI", default="imsg"),
            FieldSpec("IMESSAGE_ALLOWED_SENDERS", "Allowed senders (comma-separated)", default=""),
            FieldSpec("IMESSAGE_SERVICE", "Default service (auto / imessage / sms)", default="auto"),
            FieldSpec("IMESSAGE_REGION", "Phone number region", default="US"),
        ),
    ),
}


_WECOM_FIELDS = (
    FieldSpec("WECOM_CORP_ID", "WeCom Corp ID", required=True),
    FieldSpec("WECOM_AGENT_ID", "WeCom Agent ID", required=True),
    FieldSpec("WECOM_SECRET", "WeCom App Secret", required=True, secret=True),
)
_WECOM_OPTIONAL_FIELDS = (
    FieldSpec("WECOM_TOKEN", "WeCom callback token", default=""),
    FieldSpec("WECOM_ENCODING_AES_KEY", "WeCom encoding AES key", default=""),
    FieldSpec("WECOM_WEBHOOK_PORT", "WeCom webhook port", default="9001"),
)
_WECHAT_MP_FIELDS = (
    FieldSpec("WECHAT_APP_ID", "WeChat Official Account App ID", required=True),
    FieldSpec("WECHAT_APP_SECRET", "WeChat Official Account App Secret", required=True, secret=True),
)
_WECHAT_MP_OPTIONAL_FIELDS = (
    FieldSpec("WECHAT_TOKEN", "WeChat callback token", default=""),
    FieldSpec("WECHAT_ENCODING_AES_KEY", "WeChat encoding AES key", default=""),
    FieldSpec("WECHAT_WEBHOOK_PORT", "WeChat webhook port", default="9001"),
)
_WECOM_KEYS = {
    "WECOM_CORP_ID",
    "WECOM_AGENT_ID",
    "WECOM_SECRET",
    "WECOM_TOKEN",
    "WECOM_ENCODING_AES_KEY",
    "WECOM_WEBHOOK_PORT",
}
_WECHAT_MP_KEYS = {
    "WECHAT_APP_ID",
    "WECHAT_APP_SECRET",
    "WECHAT_TOKEN",
    "WECHAT_ENCODING_AES_KEY",
    "WECHAT_WEBHOOK_PORT",
}


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
        return str(parsed)
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def _serialise_env_value(value: str) -> str:
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or "#" in value:
        return repr(value)
    return value


def load_env() -> dict[str, str]:
    env_vars: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return env_vars

    with open(_ENV_PATH, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            env_vars[key] = _parse_env_value(raw_value)
    return env_vars


def save_env(env_vars: Mapping[str, str | None]) -> None:
    updates = dict(env_vars)
    lines: list[str] = []

    if _ENV_PATH.exists():
        with open(_ENV_PATH, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                stripped = raw_line.strip()
                if "=" not in stripped or stripped.startswith("#"):
                    lines.append(raw_line if raw_line.endswith("\n") else f"{raw_line}\n")
                    continue

                key = stripped.split("=", 1)[0].strip()
                if key not in updates:
                    lines.append(raw_line if raw_line.endswith("\n") else f"{raw_line}\n")
                    continue

                value = updates.pop(key)
                if value is None:
                    continue
                lines.append(f"{key}={_serialise_env_value(value)}\n")

    if lines and not lines[-1].endswith("\n"):
        lines[-1] = f"{lines[-1]}\n"

    for key, value in updates.items():
        if value is None:
            continue
        lines.append(f"{key}={_serialise_env_value(value)}\n")

    with open(_ENV_PATH, "w", encoding="utf-8") as handle:
        handle.writelines(lines)


def _ask_select(message: str, *, choices: list, default: str | None = None) -> str | None:
    return questionary.select(message, choices=choices, default=default, style=_STYLE).ask()


def _ask_checkbox(message: str, *, choices: list) -> list[str] | None:
    return questionary.checkbox(message, choices=choices, style=_STYLE).ask()


def _ask_confirm(message: str, *, default: bool = False) -> bool | None:
    return questionary.confirm(message, default=default, style=_STYLE).ask()


def _field_prompt(field: FieldSpec, existing: str) -> str:
    if field.secret:
        if existing:
            return f"{field.prompt} (leave blank to keep current):"
        return f"{field.prompt}:"
    if existing and field.required:
        return f"{field.prompt} (Enter to keep current):"
    if existing:
        return f"{field.prompt} (Enter to keep current, '-' to clear):"
    return f"{field.prompt}:"


def _prompt_field(env_vars: dict[str, str | None], field: FieldSpec) -> bool:
    existing = str(env_vars.get(field.key, "") or "")
    default = existing or field.default

    while True:
        prompt = _field_prompt(field, existing)
        if field.secret:
            raw_value = questionary.password(prompt, style=_STYLE).ask()
        else:
            raw_value = questionary.text(prompt, default=default, style=_STYLE).ask()

        if raw_value is None:
            return False

        value = raw_value.strip()
        if field.secret:
            if value:
                env_vars[field.key] = value
                return True
            if existing:
                return True
            if not field.required:
                env_vars[field.key] = None
                return True
            console.print(f"[yellow]{field.key} is required.[/yellow]")
            continue

        if value == "-" and existing and not field.required:
            env_vars[field.key] = None
            return True
        if value:
            env_vars[field.key] = value
            return True
        if existing:
            return True
        if field.required:
            console.print(f"[yellow]{field.key} is required.[/yellow]")
            continue
        env_vars[field.key] = None
        return True


def _prompt_fields(
    env_vars: dict[str, str | None],
    fields: tuple[FieldSpec, ...],
) -> bool:
    for field in fields:
        if not _prompt_field(env_vars, field):
            return False
    return True


def _infer_selected_channels(env_vars: Mapping[str, str]) -> list[str]:
    selected: list[str] = []
    for key, spec in CHANNEL_SPECS.items():
        if any(str(env_vars.get(env_key, "") or "").strip() for env_key in spec.detect_keys):
            selected.append(key)
    return selected


def _configure_llm(env_vars: dict[str, str | None]) -> tuple[bool, str]:
    console.print("\n[bold green]LLM setup[/bold green]")

    current_provider = detect_provider_from_env(env=env_vars) or "deepseek"
    providers = list(PROVIDER_CHOICES)
    provider = _ask_select(
        "Select your preferred LLM provider:",
        choices=providers,
        default=current_provider if current_provider in providers else "deepseek",
    )
    if provider is None:
        return False, ""

    env_vars["LLM_PROVIDER"] = provider
    preset_base_url, preset_model, _ = PROVIDER_PRESETS.get(provider, ("", "", ""))

    current_model = str(env_vars.get("OMICSCLAW_MODEL", "") or "")
    if current_provider == provider and current_model:
        current_model, _ = normalize_model_for_provider(provider, current_model)
        env_vars["OMICSCLAW_MODEL"] = current_model
    model_default = current_model if current_provider == provider and current_model else preset_model
    if not _prompt_field(
        env_vars,
        FieldSpec("OMICSCLAW_MODEL", "Model name", required=True, default=model_default),
    ):
        return False, ""

    if provider != "ollama":
        if not _prompt_field(
            env_vars,
            FieldSpec("LLM_API_KEY", f"{provider.title()} API key", required=(provider == "custom"), secret=True),
        ):
            return False, ""

    if provider in {"custom", "ollama"}:
        base_default = (
            str(env_vars.get("LLM_BASE_URL", "") or "")
            if current_provider == provider
            else preset_base_url
        )
        if not _prompt_field(
            env_vars,
            FieldSpec("LLM_BASE_URL", "Base URL", required=True, default=base_default),
        ):
            return False, ""
    else:
        configure_base_url = _ask_confirm(
            "Configure a base URL override for this provider?",
            default=bool(current_provider == provider and env_vars.get("LLM_BASE_URL")),
        )
        if configure_base_url is None:
            return False, ""
        if configure_base_url:
            if not _prompt_field(
                env_vars,
                FieldSpec("LLM_BASE_URL", "Base URL override", default=""),
            ):
                return False, ""
        elif current_provider != provider:
            env_vars["LLM_BASE_URL"] = None

    configure_timeouts = _ask_confirm(
        "Configure LLM timeout overrides?",
        default=bool(
            env_vars.get("OMICSCLAW_LLM_TIMEOUT_SECONDS")
            or env_vars.get("OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS")
        ),
    )
    if configure_timeouts is None:
        return False, ""
    if configure_timeouts and not _prompt_fields(
        env_vars,
        (
            FieldSpec(
                "OMICSCLAW_LLM_TIMEOUT_SECONDS",
                "LLM total timeout in seconds",
                default="120",
            ),
            FieldSpec(
                "OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS",
                "LLM connect timeout in seconds",
                default="10",
            ),
        ),
    ):
        return False, ""

    return True, provider


def _configure_core_runtime(env_vars: dict[str, str | None]) -> bool:
    console.print("\n[bold green]Shared runtime settings[/bold green]")

    if not _prompt_fields(
        env_vars,
        (
            FieldSpec("RATE_LIMIT_PER_HOUR", "Default per-user rate limit per hour", default="10"),
            FieldSpec(
                "OMICSCLAW_DATA_DIRS",
                "Additional trusted data directories (comma-separated absolute paths)",
                default="",
            ),
        ),
    ):
        return False

    configure_access_control = _ask_confirm(
        "Configure a global sender allowlist and middleware rate limit?",
        default=bool(
            env_vars.get("ALLOWED_SENDERS")
            or env_vars.get("GLOBAL_RATE_LIMIT")
        ),
    )
    if configure_access_control is None:
        return False
    if configure_access_control and not _prompt_fields(
        env_vars,
        (
            FieldSpec(
                "ALLOWED_SENDERS",
                "Global allowed senders (comma-separated, applied across channels)",
                default="",
            ),
            FieldSpec(
                "GLOBAL_RATE_LIMIT",
                "Global inbound middleware rate limit per hour",
                default="120",
            ),
        ),
    ):
        return False

    configure_memory = _ask_confirm(
        "Configure graph memory and dashboard API settings?",
        default=bool(
            env_vars.get("OMICSCLAW_MEMORY_DB_URL")
            or env_vars.get("OMICSCLAW_MEMORY_API_TOKEN")
            or env_vars.get("OMICSCLAW_MEMORY_HOST")
            or env_vars.get("OMICSCLAW_MEMORY_PORT")
        ),
    )
    if configure_memory is None:
        return False
    if configure_memory and not _prompt_fields(
        env_vars,
        (
            FieldSpec(
                "OMICSCLAW_MEMORY_DB_URL",
                "Memory database URL",
                # Absolute path — aiosqlite does not expand ``~`` and the
                # backend used to silently open a literal ``~`` directory
                # relative to cwd when this default landed in ``.env``.
                default=f"sqlite+aiosqlite:///{Path.home() / '.config' / 'omicsclaw' / 'memory.db'}",
            ),
            FieldSpec("OMICSCLAW_MEMORY_API_TOKEN", "Memory API bearer token", secret=True),
            FieldSpec("OMICSCLAW_MEMORY_HOST", "Memory API host", default="127.0.0.1"),
            FieldSpec("OMICSCLAW_MEMORY_PORT", "Memory API port", default="8766"),
        ),
    ):
        return False

    configure_runtime_limits = _ask_confirm(
        "Configure advanced bot limits (history/tool iterations)?",
        default=bool(
            env_vars.get("OMICSCLAW_MAX_HISTORY")
            or env_vars.get("OMICSCLAW_MAX_TOOL_ITERATIONS")
        ),
    )
    if configure_runtime_limits is None:
        return False
    if configure_runtime_limits and not _prompt_fields(
        env_vars,
        (
            FieldSpec("OMICSCLAW_MAX_HISTORY", "Max history messages kept in memory", default="50"),
            FieldSpec(
                "OMICSCLAW_MAX_HISTORY_CHARS",
                "Optional max history characters (0 disables the cap)",
                default="0",
            ),
            FieldSpec(
                "OMICSCLAW_MAX_TOOL_ITERATIONS",
                "Max tool iterations per message",
                default="20",
            ),
        ),
    ):
        return False

    return True


def _configure_wechat(env_vars: dict[str, str | None]) -> bool:
    console.print("\n[bold green]WeChat / WeCom setup[/bold green]")

    current_backend = "wecom" if env_vars.get("WECOM_CORP_ID") else "wechatmp"
    backend = _ask_select(
        "Choose WeChat backend:",
        choices=[
            questionary.Choice("WeCom (企业微信)", "wecom"),
            questionary.Choice("WeChat Official Account (公众号)", "wechatmp"),
        ],
        default=current_backend,
    )
    if backend is None:
        return False

    if backend == "wecom":
        for key in _WECHAT_MP_KEYS:
            env_vars[key] = None
        if not _prompt_fields(env_vars, _WECOM_FIELDS):
            return False
        configure_optional = _ask_confirm(
            "Configure optional WeCom webhook settings?",
            default=any(str(env_vars.get(key, "") or "").strip() for key in _WECOM_KEYS - {f.key for f in _WECOM_FIELDS}),
        )
        if configure_optional is None:
            return False
        if configure_optional and not _prompt_fields(env_vars, _WECOM_OPTIONAL_FIELDS):
            return False
        if not configure_optional:
            for key in _WECOM_KEYS - {f.key for f in _WECOM_FIELDS}:
                env_vars.setdefault(key, None)
        return True

    for key in _WECOM_KEYS:
        env_vars[key] = None
    if not _prompt_fields(env_vars, _WECHAT_MP_FIELDS):
        return False
    configure_optional = _ask_confirm(
        "Configure optional WeChat Official Account webhook settings?",
        default=any(
            str(env_vars.get(key, "") or "").strip()
            for key in _WECHAT_MP_KEYS - {f.key for f in _WECHAT_MP_FIELDS}
        ),
    )
    if configure_optional is None:
        return False
    if configure_optional and not _prompt_fields(env_vars, _WECHAT_MP_OPTIONAL_FIELDS):
        return False
    if not configure_optional:
        for key in _WECHAT_MP_KEYS - {f.key for f in _WECHAT_MP_FIELDS}:
            env_vars.setdefault(key, None)
    return True


def _configure_channel(env_vars: dict[str, str | None], channel_key: str) -> bool:
    spec = CHANNEL_SPECS[channel_key]
    if channel_key == "wechat":
        return _configure_wechat(env_vars)

    console.print(f"\n[bold green]{spec.label} setup[/bold green]")

    if spec.required_fields and not _prompt_fields(env_vars, spec.required_fields):
        return False

    if spec.optional_fields:
        default_optional = any(str(env_vars.get(field.key, "") or "").strip() for field in spec.optional_fields)
        configure_optional = _ask_confirm(
            f"Configure optional {spec.label} settings?",
            default=default_optional,
        )
        if configure_optional is None:
            return False
        if configure_optional and not _prompt_fields(env_vars, spec.optional_fields):
            return False
    return True


def run_onboard() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]OmicsClaw Configuration Wizard[/bold cyan]\n"
            "Configure your LLM, shared runtime settings, and messaging channels.",
            border_style="cyan",
        )
    )

    env_vars: dict[str, str | None] = load_env()
    env_vars["ACTIVE_CHANNELS"] = None

    ok, provider = _configure_llm(env_vars)
    if not ok:
        return

    if not _configure_core_runtime(env_vars):
        return

    console.print("\n[bold green]Channel selection[/bold green]")
    inferred_channels = _infer_selected_channels({k: str(v or "") for k, v in env_vars.items()})
    choices = [
        questionary.Choice(spec.label, key, checked=(key in inferred_channels))
        for key, spec in CHANNEL_SPECS.items()
    ]
    selected_channels = _ask_checkbox(
        "Select the messaging channels you want to configure:",
        choices=choices,
    )
    if selected_channels is None:
        return

    for channel_key in selected_channels:
        if not _configure_channel(env_vars, channel_key):
            return

    save = _ask_confirm("Save configuration to .env?", default=True)
    if not save:
        console.print("\n[yellow]Configuration was not saved.[/yellow]")
        return

    save_env(env_vars)
    console.print("\n[bold green]✓ Configuration saved to .env[/bold green]")

    deps: set[str] = set()
    for channel_key in selected_channels:
        deps.update(CHANNEL_SPECS[channel_key].deps)
    if deps:
        console.print("\n[dim]Verify channel dependencies are installed:[/dim]")
        console.print(f"    pip install {' '.join(sorted(deps))}")

    console.print("\n[dim]Configured provider:[/dim] " + provider)
    if selected_channels:
        console.print("[dim]Start the configured channels with:[/dim]")
        console.print(f"    python -m bot.run --channels {','.join(selected_channels)}")
    else:
        console.print("[yellow]No channels were selected. Core runtime settings were still saved.[/yellow]")


if __name__ == "__main__":
    run_onboard()
