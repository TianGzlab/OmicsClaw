"""
bot/onboard.py — Interactive Setup Wizard for OmicsClaw
"""

import os
from pathlib import Path

from omicsclaw.core.provider_registry import PROVIDER_CHOICES

try:
    import questionary
    from rich.console import Console
    from rich.panel import Panel
except ImportError:
    print("Error: Missing required packages for onboarding.")
    print("Please run: pip install rich questionary")
    exit(1)

console = Console()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

def load_env() -> dict:
    env_vars = {}
    if _ENV_PATH.exists():
        with open(_ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

def save_env(env_vars: dict):
    lines = []
    keys_written = set()
    
    if _ENV_PATH.exists():
        with open(_ENV_PATH, "r") as f:
            for line in f:
                stripped = line.strip()
                if "=" in stripped and not stripped.startswith("#"):
                    k = stripped.split("=", 1)[0].strip()
                    if k in env_vars:
                        lines.append(f"{k}={env_vars.pop(k)}\n")
                        keys_written.add(k)
                        continue
                lines.append(line)
        if not lines[-1].endswith("\n"):
            lines.append("\n")
    
    # Append remaining
    for k, v in env_vars.items():
        if v is not None:
            lines.append(f"{k}={v}\n")
            
    with open(_ENV_PATH, "w") as f:
        f.writelines(lines)

def run_onboard():
    console.print(Panel.fit("[bold cyan]OmicsClaw Configuration Wizard[/bold cyan]\nLet's get your AI multi-omics assistant set up!", border_style="cyan"))
    
    env_vars = load_env()
    
    # ── 1. LLM Provider ──
    providers = list(PROVIDER_CHOICES)
    current_provider = env_vars.get("LLM_PROVIDER", "deepseek")
    
    provider = questionary.select(
        "Select your preferred LLM provider:",
        choices=providers,
        default=current_provider if current_provider in providers else "deepseek",
        style=questionary.Style([('qmark', 'fg:cyan bold'), ('question', 'bold'), ('answer', 'fg:green bold')])
    ).ask()
    
    if provider is None:
        return
        
    env_vars["LLM_PROVIDER"] = provider
    
    # ── 2. LLM API Key ──
    if provider != "ollama":
        current_k = env_vars.get("LLM_API_KEY", "")
        if not current_k:
            specific_k = f"{provider.upper()}_API_KEY"
            current_k = env_vars.get(specific_k, "")
            
        api_key = questionary.password(
            f"Enter your {provider.title()} API Key (leave empty to keep current):",
            default="" # Do not display actual key
        ).ask()
        
        if api_key is None:
            return
            
        if api_key.strip():
            env_vars["LLM_API_KEY"] = api_key.strip()
            
    # Base URL / Model config
    if provider == "custom":
        url = questionary.text("Enter custom base URL:", default=env_vars.get("LLM_BASE_URL", "")).ask()
        if url: env_vars["LLM_BASE_URL"] = url.strip()
        model = questionary.text("Enter model name:", default=env_vars.get("OMICSCLAW_MODEL", "")).ask()
        if model: env_vars["OMICSCLAW_MODEL"] = model.strip()
    elif provider == "ollama":
        model = questionary.text("Enter Ollama model name (e.g. qwen2.5:7b):", default=env_vars.get("OMICSCLAW_MODEL", "qwen2.5:7b")).ask()
        if model: env_vars["OMICSCLAW_MODEL"] = model.strip()

    # ── 3. Channels Multi-select ──
    all_channels = [
        {"name": "Telegram", "value": "telegram", "env_req": [("TELEGRAM_BOT_TOKEN", "Bot Token (from @BotFather)")]},
        {"name": "Feishu / Lark", "value": "feishu", "env_req": [("FEISHU_APP_ID", "App ID"), ("FEISHU_APP_SECRET", "App Secret")]},
        {"name": "DingTalk", "value": "dingtalk", "env_req": [("DINGTALK_CLIENT_ID", "Client ID (AppKey)"), ("DINGTALK_CLIENT_SECRET", "Client Secret")]},
        {"name": "Discord", "value": "discord", "env_req": [("DISCORD_BOT_TOKEN", "Bot Token")]},
        {"name": "Slack", "value": "slack", "env_req": [("SLACK_BOT_TOKEN", "Bot Token (xoxb...)"), ("SLACK_APP_TOKEN", "App Token (xapp...)")]},
        {"name": "WeChat (WeCom / MP)", "value": "wechat", "env_req": [("WECOM_CORP_ID", "WeCom Corp ID (or leave blank)"), ("WECOM_SECRET", "WeCom App Secret (or leave blank)")]},
        {"name": "QQ", "value": "qq", "env_req": [("QQ_APP_ID", "App ID"), ("QQ_APP_SECRET", "App Secret")]},
        {"name": "Email", "value": "email", "env_req": [("EMAIL_IMAP_USERNAME", "IMAP Username"), ("EMAIL_IMAP_PASSWORD", "IMAP App Password")]},
        {"name": "iMessage (macOS)", "value": "imessage", "env_req": []},
    ]
    
    current_active = env_vars.get("ACTIVE_CHANNELS", "")
    current_active_list = [c.strip() for c in current_active.split(",") if c.strip()]
    
    choices = [questionary.Choice(ch["name"], ch["value"], checked=(ch["value"] in current_active_list)) for ch in all_channels]
    
    selected_channels = questionary.checkbox(
        "Select messaging channels to enable (Space to toggle, Enter to confirm):",
        choices=choices,
        style=questionary.Style([('selected', 'fg:green bold'), ('pointer', 'fg:green')])
    ).ask()
    
    if selected_channels is None:
        return
        
    env_vars["ACTIVE_CHANNELS"] = ",".join(selected_channels)
    
    # ── 4. Gather secrets for chosen channels ──
    ch_lookup = {ch["value"]: ch for ch in all_channels}
    for ch_val in selected_channels:
        ch_def = ch_lookup[ch_val]
        if not ch_def["env_req"]:
            continue
        console.print(f"\n[bold green]── {ch_def['name']} Setup ──[/bold green]")
        for env_key, prompt in ch_def["env_req"]:
            current_val = env_vars.get(env_key, "")
            is_secret = "secret" in env_key.lower() or "token" in env_key.lower() or "password" in env_key.lower()
            
            if is_secret:
                val = questionary.password(
                    f"{prompt} (leave blank to keep current):"
                ).ask()
                if val is None: return
                if val.strip():
                    env_vars[env_key] = val.strip()
            else:
                val = questionary.text(
                    f"{prompt}:", 
                    default=current_val
                ).ask()
                if val is None: return
                if val.strip():
                    env_vars[env_key] = val.strip()

    console.print()
    save = questionary.confirm("Save configuration to .env?").ask()
    if save:
        save_env(env_vars)
        console.print("\n[bold green]✓ Configuration saved![/bold green]")
        
        # Give hints on missing Python deps
        deps = []
        if "telegram" in selected_channels: deps.append("python-telegram-bot>=21.0")
        if "feishu" in selected_channels: deps.append("lark-oapi>=1.3.0")
        if "discord" in selected_channels: deps.append("discord.py>=2.3")
        if "slack" in selected_channels: deps.extend(["slack-sdk>=3.27", "aiohttp>=3.9"])
        if "dingtalk" in selected_channels: deps.append("aiohttp>=3.9")
        if "wechat" in selected_channels: deps.extend(["pycryptodome>=3.20", "aiohttp>=3.9"])
        if "qq" in selected_channels: deps.append("qq-botpy>=1.0")
        
        if deps:
            console.print("\n[dim]To ensure selected channels work, please verify dependencies are installed:[/dim]")
            console.print(f"    pip install {' '.join(set(deps))}")

        if selected_channels:
            console.print("\nTo start your selected channels, simply run:")
            console.print("    [bold cyan]python -m bot.run[/bold cyan]")
        else:
            console.print("\n[yellow]No channels selected.[/yellow]")
            
if __name__ == "__main__":
    run_onboard()
