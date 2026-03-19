"""OmicsClaw interactive CLI — prompt_toolkit REPL loop.

Provides a rich terminal chat interface powered by OmicsClaw's existing
bot/core.py LLM engine (AsyncOpenAI + function calling).

Usage:
    from omicsclaw.interactive.interactive import run_interactive
    run_interactive()
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import shlex
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rich console (always available — no import guard needed)
# ---------------------------------------------------------------------------
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# prompt_toolkit (required for CLI REPL)
# ---------------------------------------------------------------------------
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.shortcuts import CompleteStyle
    from prompt_toolkit.styles import Style as PtStyle
    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    _HAS_PROMPT_TOOLKIT = False

from ._constants import (
    LOGO_GRADIENT,
    LOGO_LINES,
    SLASH_COMMANDS,
    WELCOME_SLOGANS,
)
from ._mcp import (
    add_mcp_server,
    list_mcp_servers,
    remove_mcp_server,
)
from ._session import (
    delete_session,
    format_relative_time,
    generate_session_id,
    list_sessions,
    load_session,
    save_session,
    get_config_dir,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OmicsClaw paths
# ---------------------------------------------------------------------------
_OMICSCLAW_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helper: load root omicsclaw.py script (not the omicsclaw/ package)
# ---------------------------------------------------------------------------

def _load_omicsclaw_script():
    """Load the root-level omicsclaw.py script via importlib.

    `import omicsclaw` would import the omicsclaw/ *package* (which has an
    __init__.py), not the omicsclaw.py *script* in the project root.  We
    use importlib.util.spec_from_file_location() to load the script directly
    so that list_skills() and run_skill() are always accessible.
    """
    import importlib.util
    script_path = _OMICSCLAW_DIR / "omicsclaw.py"
    spec = importlib.util.spec_from_file_location("_omicsclaw_script", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load omicsclaw.py from: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def print_banner(
    session_id: str,
    workspace_dir: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    ui_backend: str = "cli",
    mode: str | None = None,
) -> None:
    """Print welcome banner with ASCII logo and session info."""
    for line, color in zip(LOGO_LINES, LOGO_GRADIENT):
        console.print(Text(line, style=f"{color} bold"))

    info = Text()
    info.append("  ", style="dim")
    parts: list[tuple[str, str]] = []
    if model:
        parts.append(("Model: ", model))
    if provider:
        parts.append(("Provider: ", provider))
    if mode:
        parts.append(("Mode: ", mode))
    parts.append(("UI: ", ui_backend))

    for i, (label, value) in enumerate(parts):
        if i > 0:
            info.append("  ", style="dim")
        info.append(label, style="dim")
        info.append(value, style="magenta")

    home = os.path.expanduser("~")
    ws = workspace_dir or str(_OMICSCLAW_DIR)
    dir_display = ws.replace(home, "~", 1) if ws.startswith(home) else ws
    info.append("\n  ", style="dim")
    info.append("Workspace: ", style="dim")
    info.append(dir_display, style="magenta")

    info.append("\n  Type ", style="#ffe082")
    info.append("/", style="#ffe082 bold")
    info.append(" for commands, ", style="#ffe082")
    info.append("/help", style="#ffe082 bold")
    info.append(" for full list", style="#ffe082")
    console.print(info)


# ---------------------------------------------------------------------------
# Slash-command autocompleter
# ---------------------------------------------------------------------------

def _make_completer() -> "Completer":
    class _SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            for cmd, desc in SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=f"{cmd:<30}",
                        display_meta=desc,
                    )
    return _SlashCompleter()


_COMPLETION_STYLE = PtStyle.from_dict({
    "completion-menu": "bg:default noreverse",
    "completion-menu.completion": "bg:default #888888",
    "completion-menu.completion.current": "bg:default default bold",
    "completion-menu.meta.completion": "bg:default #666666",
    "completion-menu.meta.completion.current": "bg:default #aaaaaa bold",
}) if _HAS_PROMPT_TOOLKIT else None

_PICKER_STYLE = PtStyle.from_dict({
    "questionmark": "#888888",
    "question": "",
    "pointer": "bold",
    "highlighted": "bold",
    "text": "#888888",
    "answer": "bold",
}) if _HAS_PROMPT_TOOLKIT else None


# ---------------------------------------------------------------------------
# Helper: print separator
# ---------------------------------------------------------------------------

def _print_separator() -> None:
    width = console.size.width
    console.print(Text("─" * width, style="dim"))


# ---------------------------------------------------------------------------
# Slash-command handlers
# ---------------------------------------------------------------------------

def _handle_skills(arg: str) -> None:
    """List skills, optionally filtered by domain."""
    try:
        _oc = _load_omicsclaw_script()
        domain_filter = arg.strip() or None
        _oc.list_skills(domain_filter=domain_filter)
    except Exception as e:
        console.print(f"[red]Error listing skills: {escape(str(e))}[/red]")


def _handle_run(arg: str) -> str:
    """Run a skill inline: /run <skill> [--demo] [--input <path>]."""
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    if not tokens:
        console.print("[yellow]Usage: /run <skill> [--demo] [--input <file>] [--output <dir>][/yellow]")
        return ""

    skill = tokens[0]
    demo = "--demo" in tokens
    input_path = None
    output_dir = None
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "--input" and i + 1 < len(tokens):
            input_path = tokens[i + 1]; i += 2
        elif t == "--output" and i + 1 < len(tokens):
            output_dir = tokens[i + 1]; i += 2
        else:
            i += 1

    try:
        _oc = _load_omicsclaw_script()
        with console.status(f"[cyan]Running skill: {skill}...[/cyan]"):
            result = _oc.run_skill(
                skill,
                input_path=input_path,
                output_dir=output_dir,
                demo=demo,
            )
        if result.get("success"):
            console.print(f"[green]✓ Skill '{skill}' completed in {result.get('duration_seconds', 0):.1f}s[/green]")
            if result.get("output_dir"):
                console.print(f"  [dim]Output:[/dim] {result['output_dir']}")
            if result.get("stdout"):
                console.print(result["stdout"])
            return f"Skill '{skill}' completed successfully. Output in: {result.get('output_dir', '?')}"
        else:
            err = result.get("stderr", "unknown error")
            console.print(f"[red]✗ Skill '{skill}' failed:[/red] {err[:300]}")
            return f"Skill '{skill}' failed: {err[:200]}"
    except Exception as e:
        console.print(f"[red]Error running skill '{skill}': {escape(str(e))}[/red]")
        return f"Error running skill: {e}"


async def _handle_sessions() -> None:
    """List recent sessions in a table."""
    sessions = await list_sessions(limit=20)
    if not sessions:
        console.print("[yellow]No saved sessions.[/yellow]")
        return
    table = Table(title="Sessions", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold yellow", no_wrap=True)
    table.add_column("Preview", style="", max_width=50, no_wrap=True)
    table.add_column("Msgs", justify="right")
    table.add_column("Model", style="dim")
    table.add_column("Last Used", style="dim")
    for s in sessions:
        table.add_row(
            s["session_id"],
            s.get("preview", "") or "",
            str(s.get("message_count", 0)),
            s.get("model", "") or "",
            format_relative_time(s.get("updated_at")),
        )
    console.print()
    console.print(table)
    console.print("[dim]  /resume to continue a session  /delete <id> to remove  /new to start fresh[/dim]")
    console.print()


async def _pick_session_interactive(current_id: str) -> str | None:
    """Show an interactive session picker using questionary."""
    sessions = await list_sessions(limit=20)
    if not sessions:
        console.print("[yellow]No sessions to resume.[/yellow]")
        return None

    try:
        import questionary

        choices = []
        for s in sessions:
            sid = s["session_id"]
            preview = s.get("preview", "") or sid
            when = format_relative_time(s.get("updated_at"))
            marker = " ●" if sid == current_id else ""
            label = f"{preview[:50]:<52}  [{sid}  {when}]{marker}"
            choices.append(questionary.Choice(title=label, value=sid))

        selected = questionary.select(
            "Select session to resume:",
            choices=choices,
            style=_PICKER_STYLE,
        ).ask()
        return selected
    except ImportError:
        # Fallback: show list and ask for input
        await _handle_sessions()
        console.print("Enter session ID to resume (or press Enter to cancel): ", end="")
        try:
            sid = input().strip()
            return sid if sid else None
        except (EOFError, KeyboardInterrupt):
            return None


async def _handle_resume(arg: str, state: dict[str, Any]) -> None:
    """Resume a saved session by ID or interactive picker."""
    target_id = arg.strip()
    if not target_id:
        selected = await _pick_session_interactive(state["session_id"])
        if not selected:
            return
        target_id = selected

    data = await load_session(target_id)
    if not data:
        console.print(f"[red]Session '{escape(target_id)}' not found.[/red]")
        return

    state["session_id"] = data["session_id"]
    state["messages"] = data.get("messages", [])
    if data.get("workspace"):
        state["workspace_dir"] = data["workspace"]

    console.print(f"[green]Resumed session:[/green] [yellow]{data['session_id']}[/yellow]")
    if data.get("workspace"):
        console.print(f"[dim]Workspace:[/dim] [cyan]{data['workspace']}[/cyan]")

    # Show brief history preview
    msgs = [m for m in state["messages"] if m.get("role") in ("user", "assistant")]
    if msgs:
        console.print("[dim]── Conversation history ──[/dim]")
        for m in msgs[-6:]:
            role = m.get("role", "")
            content = m.get("content", "") or ""
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            content = str(content).strip()[:160]
            if role == "user":
                console.print(Text.assemble(("❯ ", "bold cyan"), (content, "")))
            elif role == "assistant":
                console.print(Text(content[:160], style="dim"))
        console.print("[dim]── End of history ──[/dim]")
    console.print()


async def _handle_delete(arg: str, state: dict[str, Any]) -> None:
    """Delete a session by ID."""
    target_id = arg.strip()
    if not target_id:
        console.print("[red]Usage: /delete <session-id>[/red]")
        return
    if target_id == state["session_id"]:
        console.print("[red]Cannot delete the current active session.[/red]")
        return
    data = await load_session(target_id)
    if not data:
        console.print(f"[red]Session '{escape(target_id)}' not found.[/red]")
        return
    deleted = await delete_session(data["session_id"])
    if deleted:
        console.print(f"[green]Deleted session {data['session_id']}.[/green]")
    else:
        console.print(f"[red]Failed to delete session.[/red]")


def _handle_mcp(arg: str) -> None:
    """Handle /mcp subcommands."""
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    subcmd = tokens[0].lower() if tokens else "list"

    if subcmd == "list":
        servers = list_mcp_servers()
        if not servers:
            console.print("[yellow]No MCP servers configured.[/yellow]")
            console.print("[dim]Add one with: /mcp add <name> <command> [args...][/dim]")
            return
        table = Table(title="MCP Servers", show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Transport")
        table.add_column("Command / URL", style="dim")
        table.add_column("Tools")
        for s in servers:
            name = s.get("name", "?")
            transport = s.get("transport", "?")
            target = s.get("command") or s.get("url", "?")
            tools = ",".join(s.get("tools", [])) or "all"
            table.add_row(name, transport, str(target), tools)
        console.print(table)

    elif subcmd == "add":
        # /mcp add <name> <command-or-url> [args...] [--env KEY=VAL]
        if len(tokens) < 3:
            console.print("[yellow]Usage: /mcp add <name> <command-or-url> [args...] [--env KEY=VAL][/yellow]")
            return
        name = tokens[1]
        target = tokens[2]
        extra_args = []
        env: dict[str, str] = {}
        i = 3
        while i < len(tokens):
            if tokens[i] == "--env" and i + 1 < len(tokens):
                kv = tokens[i + 1]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    env[k] = v
                i += 2
            else:
                extra_args.append(tokens[i])
                i += 1
        try:
            entry = add_mcp_server(name, target, extra_args=extra_args or None, env=env or None)
            console.print(f"[green]Added MCP server:[/green] {name} ({entry['transport']})")
            console.print("[dim]Restart the session to activate new MCP tools.[/dim]")
        except Exception as e:
            console.print(f"[red]Error adding MCP server: {escape(str(e))}[/red]")

    elif subcmd == "remove":
        if len(tokens) < 2:
            console.print("[yellow]Usage: /mcp remove <name>[/yellow]")
            return
        name = tokens[1]
        if remove_mcp_server(name):
            console.print(f"[green]Removed MCP server: {name}[/green]")
        else:
            console.print(f"[red]MCP server '{name}' not found.[/red]")

    else:
        console.print(f"[yellow]Unknown /mcp subcommand: {subcmd}[/yellow]")
        console.print("[dim]Available: /mcp list | /mcp add <name> <cmd> | /mcp remove <name>[/dim]")


def _handle_config(arg: str) -> None:
    """Handle /config subcommands."""
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    subcmd = tokens[0].lower() if tokens else "list"

    env_path = _OMICSCLAW_DIR / ".env"

    if subcmd == "list":
        env_vars: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

        table = Table(title="OmicsClaw Configuration", show_header=True)
        table.add_column("Key", style="cyan")
        table.add_column("Value")
        for k, v in sorted(env_vars.items()):
            if any(x in k.lower() for x in ("key", "secret", "token", "password")):
                v = "***" + v[-4:] if len(v) > 4 else "***"
            table.add_row(k, v or "[dim](empty)[/dim]")
        console.print(table)
        console.print(f"\n[dim]Config file: {env_path}[/dim]")

    elif subcmd == "set" and len(tokens) >= 3:
        key = tokens[1]
        value = tokens[2]
        # Read, update, write .env
        lines: list[str] = []
        found = False
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k = stripped.split("=", 1)[0].strip()
                    if k == key:
                        lines.append(f"{key}={value}\n")
                        found = True
                        continue
                lines.append(line + "\n")
        if not found:
            lines.append(f"{key}={value}\n")
        env_path.write_text("".join(lines), encoding="utf-8")
        console.print(f"[green]Set {escape(key)}[/green]")

    else:
        console.print("[yellow]Usage: /config list | /config set <key> <value>[/yellow]")


# ---------------------------------------------------------------------------
# Skill installation / uninstallation helpers
# ---------------------------------------------------------------------------

def _handle_install_skill(arg: str) -> None:
    """Install a skill from a local path or a GitHub URL.

    Usage:
        /install-skill /path/to/skill-dir
        /install-skill https://github.com/user/repo
        /install-skill https://github.com/user/repo/tree/main/skills/my-skill
    """
    import shutil
    import subprocess as _sp

    src = arg.strip()
    if not src:
        console.print("[yellow]Usage: /install-skill <local-path | github-url>[/yellow]")
        console.print("[dim]Examples:[/dim]")
        console.print("  [dim]/install-skill /path/to/my-skill[/dim]")
        console.print("  [dim]/install-skill https://github.com/user/my-skill-repo[/dim]")
        return

    skills_dir = _OMICSCLAW_DIR / "skills"
    user_skills_dir = skills_dir / "user"  # user-installed skills live here
    user_skills_dir.mkdir(parents=True, exist_ok=True)

    is_github = src.startswith(("https://github.com", "http://github.com", "git@github.com"))

    if is_github:
        # Derive skill name from the repo/URL
        # e.g. https://github.com/user/my-skill → my-skill
        url_clean = src.rstrip("/")
        skill_name = url_clean.split("/")[-1]
        # Strip .git suffix if present
        if skill_name.endswith(".git"):
            skill_name = skill_name[:-4]

        dest = user_skills_dir / skill_name
        if dest.exists():
            console.print(f"[yellow]Skill '{skill_name}' already exists at {dest}[/yellow]")
            console.print("[dim]To reinstall, run /uninstall-skill first.[/dim]")
            return

        console.print(f"[cyan]Cloning '{skill_name}' from GitHub...[/cyan]")
        try:
            result = _sp.run(
                ["git", "clone", "--depth=1", src, str(dest)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                console.print(f"[red]git clone failed:[/red]\n{result.stderr[:500]}")
                return
            console.print(f"[green]✓ Cloned to {dest}[/green]")
        except FileNotFoundError:
            console.print("[red]git is not installed. Please install git and try again.[/red]")
            return
        except _sp.TimeoutExpired:
            console.print("[red]Clone timed out (120 s). Check your network connection.[/red]")
            return
    else:
        # Local path install — copy into user_skills_dir
        src_path = Path(src).expanduser().resolve()
        if not src_path.exists():
            console.print(f"[red]Path not found: {escape(str(src_path))}[/red]")
            return
        if not src_path.is_dir():
            console.print(f"[red]Source must be a directory (skill folder): {escape(str(src_path))}[/red]")
            return

        skill_name = src_path.name
        dest = user_skills_dir / skill_name
        if dest.exists():
            console.print(f"[yellow]Skill '{skill_name}' already exists at {dest}[/yellow]")
            console.print("[dim]To reinstall, run /uninstall-skill first.[/dim]")
            return

        console.print(f"[cyan]Copying '{skill_name}' from {src_path}...[/cyan]")
        try:
            shutil.copytree(src_path, dest)
            console.print(f"[green]✓ Copied to {dest}[/green]")
        except Exception as e:
            console.print(f"[red]Copy failed: {escape(str(e))}[/red]")
            return

    # Validate: look for a Python script or SKILL.md
    script_candidates = list(dest.glob("*.py"))
    has_skill_md = (dest / "SKILL.md").exists()
    if not script_candidates and not has_skill_md:
        console.print(
            "[yellow]⚠ No .py script or SKILL.md found in the installed directory.[/yellow]\n"
            "[dim]The skill may not be loadable. Make sure the directory follows OmicsClaw conventions.[/dim]"
        )
    else:
        console.print(
            f"[dim]Found:[/dim] "
            + (f"{len(script_candidates)} script(s)" if script_candidates else "")
            + (" + SKILL.md" if has_skill_md else "")
        )

    # Reset registry so the new skill is discovered on next use
    try:
        from omicsclaw.core.registry import registry
        registry._loaded = False
        registry.load_all()
        console.print(f"[green]✓ Skill '{skill_name}' installed and registered.[/green]")
        console.print(f"[dim]Use /skills to list all available skills.[/dim]")
    except Exception as e:
        console.print(f"[yellow]Registry refresh failed (skill files are in place): {e}[/yellow]")


def _handle_uninstall_skill(arg: str) -> None:
    """Remove a user-installed skill by name.

    Only skills inside skills/user/ can be removed — built-in skills are
    protected.

    Usage:
        /uninstall-skill my-skill
    """
    import shutil

    name = arg.strip()
    if not name:
        console.print("[yellow]Usage: /uninstall-skill <skill-name>[/yellow]")
        return

    skills_dir = _OMICSCLAW_DIR / "skills"
    user_skills_dir = skills_dir / "user"

    # Search inside user/ directory only (protect built-in skills)
    candidate = user_skills_dir / name
    if not candidate.exists():
        # Also search all domain sub-dirs to give a helpful error message
        found_elsewhere: list[Path] = []
        for domain_path in skills_dir.iterdir():
            if not domain_path.is_dir() or domain_path.name.startswith((".", "__")):
                continue
            skill_path = domain_path / name
            if skill_path.exists():
                found_elsewhere.append(skill_path)

        if found_elsewhere:
            console.print(
                f"[yellow]Skill '{escape(name)}' is a built-in skill and cannot be removed via /uninstall-skill.[/yellow]"
            )
            console.print("[dim]Built-in skills are part of the OmicsClaw core and should not be deleted.[/dim]")
        else:
            console.print(f"[red]User-installed skill '{escape(name)}' not found.[/red]")
            console.print(f"[dim]User skills directory: {user_skills_dir}[/dim]")
            # List user-installed skills for reference
            if user_skills_dir.exists():
                installed = [p.name for p in user_skills_dir.iterdir() if p.is_dir()]
                if installed:
                    console.print(f"[dim]Installed user skills: {', '.join(installed)}[/dim]")
                else:
                    console.print("[dim]No user-installed skills found.[/dim]")
        return

    # Confirm removal
    console.print(f"[yellow]Remove skill '{name}' from {candidate}? (y/N)[/yellow] ", end="")
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Cancelled.[/dim]")
        return

    if answer not in ("y", "yes"):
        console.print("[dim]Cancelled.[/dim]")
        return

    try:
        shutil.rmtree(candidate)
        console.print(f"[green]✓ Skill '{name}' removed.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to remove skill: {escape(str(e))}[/red]")
        return

    # Reset registry
    try:
        from omicsclaw.core.registry import registry
        # Remove from runtime registry dict if present
        registry.skills.pop(name, None)
        registry._loaded = False
        registry.load_all()
        console.print("[dim]Registry refreshed.[/dim]")
    except Exception as e:
        console.print(f"[yellow]Registry refresh failed: {e}[/yellow]")



def _init_llm(config: dict) -> tuple[str, str]:
    """Initialize bot/core LLM. Returns (model, provider)."""
    try:
        sys.path.insert(0, str(_OMICSCLAW_DIR))
        import bot.core as core
        from dotenv import load_dotenv
        load_dotenv(_OMICSCLAW_DIR / ".env", override=False)

        provider = os.environ.get("LLM_PROVIDER", config.get("provider", ""))
        api_key = os.environ.get("LLM_API_KEY", config.get("api_key", ""))
        model = os.environ.get("OMICSCLAW_MODEL", config.get("model", ""))
        base_url = os.environ.get("LLM_BASE_URL", config.get("base_url", ""))

        import logging
        logging.getLogger("omicsclaw.bot").setLevel(logging.WARNING)

        core.init(
            api_key=api_key,
            base_url=base_url or None,
            model=model,
            provider=provider,
        )
        return core.OMICSCLAW_MODEL, core.LLM_PROVIDER_NAME
    except Exception as e:
        logger.warning("LLM init error: %s", e)
        return os.environ.get("OMICSCLAW_MODEL", "unknown"), os.environ.get("LLM_PROVIDER", "")


async def _stream_llm_response(messages: list[dict]) -> str:
    """Call bot/core.py llm_tool_loop and print the response to the console.

    Returns the final assistant text response.
    """
    try:
        sys.path.insert(0, str(_OMICSCLAW_DIR))
        import bot.core as core

        # Use the existing LLM tool loop from core.py.
        # core.llm_tool_loop manages its own per-chat conversation history
        # internally via core.conversations[chat_id].  We seed it from our
        # local messages list (excluding the last user message which
        # llm_tool_loop will append itself), then sync back after the call.
        _INTERACTIVE_USER = "__interactive__"

        # Seed history with everything *except* the last user message
        # (llm_tool_loop will append that message itself).
        seed = list(messages[:-1]) if len(messages) > 1 else []
        core.conversations[_INTERACTIVE_USER] = seed
        core._conversation_access[_INTERACTIVE_USER] = __import__("time").time()

        user_text = ""
        if messages:
            last = messages[-1]
            content = last.get("content", "")
            user_text = content if isinstance(content, str) else str(content)

        # Snapshot usage before the call to compute per-turn delta
        usage_before = core.get_usage_snapshot()

        import json
        with console.status("[cyan]Thinking...[/cyan]", spinner="dots") as status:
            def sync_on_tool_call(tool_name: str, args: dict):
                status.update(f"[cyan]Running {tool_name}...[/cyan]")
                args_preview = json.dumps(args)[:80] + ("..." if len(json.dumps(args)) > 80 else "")
                console.print(f"  [dim]↳ 🛠️  Calling [cyan]{tool_name}[/cyan]({args_preview})[/dim]")
                
            def sync_on_tool_result(tool_name: str, result: str):
                status.update("[cyan]Thinking...[/cyan]")
                result_preview = str(result)[:80].replace("\n", " ") + ("..." if len(str(result)) > 80 else "")
                console.print(f"  [dim]↳ ✓ [green]Result:[/green] {result_preview}[/dim]")

            # llm_tool_loop returns the final assistant reply as a plain string.
            final_text = await core.llm_tool_loop(
                _INTERACTIVE_USER,
                user_text,
                on_tool_call=sync_on_tool_call,
                on_tool_result=sync_on_tool_result,
            )

        # Print the response using Markdown rendering
        if final_text:
            from rich.markdown import Markdown
            console.print(Markdown(final_text))

        # Display per-turn usage statistics (inspired by EvoScientist)
        _display_usage_stats(core, usage_before)

        # Sync the updated conversation history back to our messages list
        updated_msgs = list(core.conversations.get(_INTERACTIVE_USER, []))
        messages.clear()
        messages.extend(updated_msgs)

        return final_text or ""
    except Exception as e:
        err_msg = f"LLM error: {e}"
        console.print(f"[red]{escape(err_msg)}[/red]")
        if "api_key" in str(e).lower() or "authentication" in str(e).lower():
            console.print("[dim]Run [bold]oc onboard[/bold] to configure your API key.[/dim]")
        return err_msg


def _display_usage_stats(core, usage_before: dict) -> None:
    """Display per-turn token usage statistics.

    Shows a right-aligned line like:
        [Usage: 1,234 in · 567 out | $0.0012]
    """
    try:
        usage_after = core.get_usage_snapshot()
        delta_in = usage_after.get("prompt_tokens", 0) - usage_before.get("prompt_tokens", 0)
        delta_out = usage_after.get("completion_tokens", 0) - usage_before.get("completion_tokens", 0)

        if delta_in <= 0 and delta_out <= 0:
            return

        stats = Text(justify="right")
        stats.append("[", style="dim italic")
        stats.append("Usage: ", style="dim italic")
        stats.append(f"{delta_in:,}", style="cyan italic")
        stats.append(" in · ", style="dim italic")
        stats.append(f"{delta_out:,}", style="green italic")
        stats.append(" out", style="dim italic")

        # Show cost estimate if pricing is available
        cost_before = usage_before.get("estimated_cost_usd", 0.0)
        cost_after = usage_after.get("estimated_cost_usd", 0.0)
        delta_cost = cost_after - cost_before
        if delta_cost > 0:
            stats.append(" | ", style="dim italic")
            stats.append(f"${delta_cost:.4f}", style="yellow italic")

        stats.append("]", style="dim italic")
        console.print(stats)
    except Exception:
        pass  # Silently skip on any usage retrieval error


# ---------------------------------------------------------------------------
# Main interactive loop
# ---------------------------------------------------------------------------

async def _async_interactive_loop(
    show_thinking: bool = True,
    workspace_dir: str | None = None,
    session_id: str | None = None,
    model: str = "",
    provider: str = "",
    ui_backend: str = "cli",
    config: dict | None = None,
    mode: str | None = None,
) -> None:
    config = config or {}

    if not _HAS_PROMPT_TOOLKIT:
        console.print(
            "[red]prompt_toolkit is required for interactive mode.[/red]\n"
            "[dim]Install with: pip install prompt-toolkit[/dim]"
        )
        return

    # Init LLM
    resolved_model, resolved_provider = _init_llm(config)
    if model:
        resolved_model = model
    if provider:
        resolved_provider = provider

    # Initialise session
    effective_session_id = session_id or generate_session_id()
    effective_workspace = workspace_dir or str(_OMICSCLAW_DIR)

    # Mutable state
    state: dict[str, Any] = {
        "session_id":   effective_session_id,
        "workspace_dir": effective_workspace,
        "messages":     [],
        "running":      True,
        "ui_backend":   ui_backend,
    }

    # Try to resume existing session
    if session_id:
        data = await load_session(session_id)
        if data:
            state["messages"] = data.get("messages", [])
            if data.get("workspace"):
                state["workspace_dir"] = data["workspace"]
            console.print(f"[green]Resumed session:[/green] [yellow]{session_id}[/yellow]")
        else:
            console.print(f"[yellow]Session '{session_id}' not found — starting fresh.[/yellow]")

    # History file for prompt_toolkit
    config_dir = get_config_dir()
    history_file = str(config_dir / "history")

    pt_session: PromptSession = PromptSession(
        history=FileHistory(history_file),
        auto_suggest=AutoSuggestFromHistory(),
        completer=_make_completer(),
        complete_style=CompleteStyle.COLUMN,
        complete_while_typing=True,
        style=_COMPLETION_STYLE,
    )

    # Print banner
    print_banner(
        state["session_id"],
        state["workspace_dir"],
        resolved_model,
        resolved_provider,
        ui_backend,
        mode=mode,
    )
    console.print(Text(f"  {random.choice(WELCOME_SLOGANS)}", style="dim italic"))
    console.print()
    _print_separator()

    # ── Main REPL loop ──
    while state["running"]:
        try:
            user_input_raw: str = await pt_session.prompt_async(
                HTML("<ansiblue><b>❯</b></ansiblue> ")
            )
            user_input = user_input_raw.strip()

            if not user_input:
                sys.stdout.write("\033[A\033[2K\r")
                sys.stdout.flush()
                continue

            _print_separator()

            # ── Slash command dispatch ──
            low = user_input.lower()

            if low in ("/exit", "/quit", "/q"):
                console.print("[dim]Goodbye! See you next time.[/dim]")
                state["running"] = False
                break

            elif low == "/help":
                table = Table(title="OmicsClaw Commands", show_header=True, header_style="bold cyan")
                table.add_column("Command", style="bold yellow", no_wrap=True)
                table.add_column("Description")
                for cmd, desc in SLASH_COMMANDS:
                    table.add_row(cmd, desc)
                console.print(table)
                console.print()
                _print_separator()
                continue

            elif low.startswith("/skills"):
                arg = user_input[len("/skills"):].strip()
                _handle_skills(arg)
                _print_separator()
                continue

            elif low.startswith("/run ") or low == "/run":
                arg = user_input[len("/run"):].strip()
                result_text = _handle_run(arg)
                if result_text:
                    # Inject run result into conversation for context
                    state["messages"].append({
                        "role": "user",
                        "content": f"[Ran skill] {arg}",
                    })
                    state["messages"].append({
                        "role": "assistant",
                        "content": result_text,
                    })
                    await save_session(
                        state["session_id"],
                        state["messages"],
                        model=resolved_model,
                        workspace=state["workspace_dir"],
                    )
                _print_separator()
                continue

            elif low == "/sessions":
                await _handle_sessions()
                _print_separator()
                continue

            elif low.startswith("/resume"):
                arg = user_input[len("/resume"):].strip()
                await _handle_resume(arg, state)
                _print_separator()
                continue

            elif low.startswith("/delete"):
                arg = user_input[len("/delete"):].strip()
                await _handle_delete(arg, state)
                _print_separator()
                continue

            elif low == "/new":
                state["session_id"] = generate_session_id()
                state["messages"] = []
                console.print(f"[green]New session:[/green] [yellow]{state['session_id']}[/yellow]")
                _print_separator()
                continue

            elif low == "/current":
                console.print(f"[dim]Session:[/dim]   [yellow]{state['session_id']}[/yellow]")
                console.print(f"[dim]Workspace:[/dim] [cyan]{state['workspace_dir']}[/cyan]")
                console.print(f"[dim]Model:[/dim]     [magenta]{resolved_model}[/magenta]")
                console.print(f"[dim]Provider:[/dim]  [magenta]{resolved_provider}[/magenta]")
                console.print(f"[dim]Messages:[/dim]  {len([m for m in state['messages'] if m.get('role') in ('user','assistant')])}")
                console.print()
                _print_separator()
                continue

            elif low == "/clear":
                state["messages"] = []
                console.print("[dim]Conversation history cleared.[/dim]")
                _print_separator()
                continue

            elif low.startswith("/mcp"):
                arg = user_input[len("/mcp"):].strip()
                _handle_mcp(arg)
                console.print()
                _print_separator()
                continue

            elif low.startswith("/config"):
                arg = user_input[len("/config"):].strip()
                _handle_config(arg)
                console.print()
                _print_separator()
                continue

            elif low.startswith("/install-skill"):
                arg = user_input[len("/install-skill"):].strip()
                _handle_install_skill(arg)
                console.print()
                _print_separator()
                continue

            elif low.startswith("/uninstall-skill"):
                arg = user_input[len("/uninstall-skill"):].strip()
                _handle_uninstall_skill(arg)
                console.print()
                _print_separator()
                continue

            # ── Regular LLM conversation ──
            state["messages"].append({"role": "user", "content": user_input})
            console.print()

            response = await _stream_llm_response(state["messages"])

            # Save session after each exchange
            await save_session(
                state["session_id"],
                state["messages"],
                model=resolved_model,
                workspace=state["workspace_dir"],
            )

            console.print()
            _print_separator()

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Type /exit to quit.[/dim]")
            _print_separator()
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            state["running"] = False
            break
        except Exception as e:
            console.print(f"[red]Unexpected error: {escape(str(e))}[/red]")
            logger.exception("Interactive loop error")
            _print_separator()

    # Final session save on exit
    if state["messages"]:
        await save_session(
            state["session_id"],
            state["messages"],
            model=resolved_model,
            workspace=state["workspace_dir"],
        )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def run_interactive(
    show_thinking: bool = True,
    workspace_dir: str | None = None,
    session_id: str | None = None,
    model: str = "",
    provider: str = "",
    ui_backend: str = "cli",
    prompt: str | None = None,
    config: dict | None = None,
    mode: str | None = None,
    run_name: str | None = None,
) -> None:
    """Launch the interactive OmicsClaw CLI session.

    Args:
        show_thinking: Whether to display extended reasoning (reserved for future)
        workspace_dir:  Working directory for this session
        session_id:     Resume a previous session by ID
        model:          Override LLM model name
        provider:       Override LLM provider (deepseek, openai, etc.)
        ui_backend:     'cli' (default) or 'tui' (Textual full-screen)
        prompt:         Single-shot prompt (non-interactive mode)
        config:         Additional config overrides
        mode:           Workspace mode: 'daemon' (persistent) or 'run' (isolated)
        run_name:       Human-friendly name for run-mode sessions
    """
    if ui_backend == "tui":
        _run_tui(
            workspace_dir=workspace_dir,
            session_id=session_id,
            model=model,
            provider=provider,
            config=config,
            mode=mode,
        )
        return

    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass

    if prompt:
        # Single-shot mode
        asyncio.run(_single_shot(
            prompt=prompt,
            workspace_dir=workspace_dir,
            model=model,
            provider=provider,
            config=config or {},
        ))
        return

    # Interactive mode
    try:
        asyncio.run(_async_interactive_loop(
            show_thinking=show_thinking,
            workspace_dir=workspace_dir,
            session_id=session_id,
            model=model,
            provider=provider,
            ui_backend=ui_backend,
            config=config or {},
            mode=mode,
        ))
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye![/dim]")


async def _single_shot(
    prompt: str,
    workspace_dir: str | None = None,
    model: str = "",
    provider: str = "",
    config: dict | None = None,
) -> None:
    """Run a single prompt without entering interactive loop."""
    config = config or {}
    resolved_model, resolved_provider = _init_llm(config)

    session_id = generate_session_id()
    messages: list[dict] = [{"role": "user", "content": prompt}]

    width = console.size.width
    console.print(Text("─" * width, style="dim"))
    console.print(Text(f"> {prompt}"))
    console.print(Text("─" * width, style="dim"))
    console.print(f"[dim]Session: {session_id}[/dim]")
    console.print()

    await _stream_llm_response(messages)

    await save_session(
        session_id, messages,
        model=resolved_model,
        workspace=workspace_dir or str(_OMICSCLAW_DIR),
    )


def _run_tui(
    workspace_dir: str | None = None,
    session_id: str | None = None,
    model: str = "",
    provider: str = "",
    config: dict | None = None,
    mode: str | None = None,
) -> None:
    """Launch the Textual TUI (full-screen mode)."""
    try:
        from .tui import run_tui
        run_tui(
            workspace_dir=workspace_dir,
            session_id=session_id,
            model=model,
            provider=provider,
            config=config or {},
        )
    except ImportError as e:
        console.print(f"[yellow]TUI requires textual: {e}[/yellow]")
        console.print("[dim]Install with: pip install textual>=0.80[/dim]")
        console.print("[dim]Falling back to CLI mode...[/dim]")
        run_interactive(
            workspace_dir=workspace_dir,
            session_id=session_id,
            model=model,
            provider=provider,
            ui_backend="cli",
            config=config,
            mode=mode,
        )
    except Exception as e:
        console.print(f"[red]TUI error: {escape(str(e))}[/red]")
        console.print("[dim]Falling back to CLI mode...[/dim]")
        run_interactive(
            workspace_dir=workspace_dir,
            session_id=session_id,
            model=model,
            provider=provider,
            ui_backend="cli",
            config=config,
            mode=mode,
        )
