"""OmicsClaw interactive CLI — prompt_toolkit REPL loop.

Provides a rich terminal chat interface powered by OmicsClaw's existing
bot/core.py LLM engine (AsyncOpenAI + function calling).

Usage:
    from omicsclaw.interactive.interactive import run_interactive
    run_interactive()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shlex
import sys
from collections import defaultdict, deque
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

_INLINE_MARKDOWN_TOKEN_RE = re.compile(
    r"(?P<link>\[(?P<link_label>[^\]\n]+)\]\((?P<link_url>[^)\n]+)\))"
    r"|(?P<bold>\*\*(?P<bold_text>[^*\n]+)\*\*)"
    r"|(?P<underline>__(?P<underline_text>[^_\n]+)__)"
    r"|(?P<code>`(?P<code_text>[^`\n]+)`)"
    r"|(?P<italic>(?<!\*)\*(?P<italic_text>[^*\n]+)\*(?!\*))"
    r"|(?P<italic_u>(?<!_)_(?P<italic_u_text>[^_\n]+)_(?!_))"
)
_STRONG_LINE_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
_ATX_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
_BULLET_LINE_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?P<body>.*)$")
_NUMBERED_LINE_RE = re.compile(r"^(?P<indent>\s*)(?P<number>\d+)\.\s+(?P<body>.*)$")
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>\s?(?P<body>.*)$")
_MARKDOWN_LINE_START_RE = re.compile(r"^\s*(?:[-*+]\s|#{1,6}\s|>\s|\d+\.\s|\*\*|__|`{1,3})")
_UNCERTAIN_MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:[-*+#>]?|\d+\.?)?\s*$")

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

from omicsclaw.common.runtime_env import load_project_dotenv
from omicsclaw.common.user_guidance import strip_user_guidance_lines

from ._constants import (
    LOGO_GRADIENT,
    LOGO_LINES,
    RUN_COMMAND_USAGE,
    WELCOME_SLOGANS,
)
from ._diagnostics_support import (
    build_context_command_view,
    build_doctor_command_view,
    build_usage_command_view,
)
from ._llm_bridge_support import (
    append_interruption_notice,
    build_usage_delta,
    seed_core_conversation,
    sync_core_conversation,
)
from ._mcp import (
    add_mcp_server,
    list_mcp_servers,
    load_active_mcp_server_entries_for_prompt,
    remove_mcp_server,
)
from ._memory_command_support import (
    build_graph_memory_command_view,
    build_memory_command_view,
    is_graph_memory_subcommand,
    resolve_active_scoped_memory_scope,
)
from ._omicsclaw_actions import (
    list_registered_skill_names,
    list_skills_text,
    run_skill_command,
)
from ._plan_mode_support import (
    build_approve_plan_command_view as build_interactive_approve_plan_command_view,
    build_do_current_task_command_view,
    build_interactive_plan_context_from_metadata,
    build_plan_command_view as build_interactive_plan_command_view,
    build_resume_task_command_view as build_interactive_resume_task_command_view,
    build_tasks_command_view as build_interactive_tasks_command_view,
    load_interactive_plan_from_metadata,
    maybe_seed_interactive_plan,
)
from ._pipeline_support import (
    build_approve_plan_command_view,
    build_pipeline_tasks_command_view,
    build_plan_preview_command_view,
    build_research_history_entries,
    format_research_result_summary,
    format_research_start_summary,
    load_pipeline_workspace_snapshot,
    parse_research_command,
    parse_resume_task_command,
    resolve_pipeline_workspace,
    resolve_research_workspace,
)
from ._skill_run_support import (
    SkillRunExecutionView,
    build_skill_run_exception_result,
    build_skill_run_execution_view,
    parse_skill_run_command,
)
from ._skill_management_support import (
    SkillCommandStatus,
    build_extension_install_usage_text,
    build_installed_extension_list_view,
    build_refresh_extensions_statuses,
    build_installed_skill_list_view,
    build_refresh_skills_statuses,
    format_installed_extension_list_plain,
    format_installed_skill_list_plain,
    install_extension_from_source,
    install_skill_from_source,
    set_installed_extension_enabled,
    uninstall_extension,
)
from ._slash_command_support import (
    CLI_SLASH_COMMAND_SPECS,
    complete_run_skill_names,
    complete_slash_command_rows,
    parse_slash_command,
    slash_command_help_rows,
)
from ._session_state import SessionState
from ._session import (
    format_relative_time,
    generate_session_id,
    get_config_dir,
    list_sessions,
    load_session,
    save_session,
)
from ._session_command_support import (
    build_clear_conversation_command_view,
    build_current_session_command_view,
    build_delete_session_command_view,
    build_export_session_command_view,
    build_new_session_command_view,
    build_resume_session_command_view,
    build_resume_session_command_view_from_data,
    build_session_tag_command_view,
    build_session_metadata,
    build_session_title_command_view,
    build_session_list_view,
    enrich_session_metadata,
    normalize_session_metadata,
    resolve_active_output_style,
    resolve_active_pipeline_workspace,
)
from ._style_support import build_style_command_view

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OmicsClaw paths
# ---------------------------------------------------------------------------
_OMICSCLAW_DIR = Path(__file__).resolve().parent.parent.parent


def _configure_cli_loggers() -> None:
    """Keep chat output focused on user-visible response text."""
    cli_log_level = os.environ.get("OMICSCLAW_LOG_LEVEL", "ERROR").upper()
    level = getattr(logging, cli_log_level, None)
    if not isinstance(level, int):
        level = logging.ERROR
    for noisy in (
        "omicsclaw.bot",
        "omicsclaw.knowledge",
        "omicsclaw.knowledge.knowhow",
        "omicsclaw.core",
        "omicsclaw.memory",
        "omicsclaw.memory.snapshot",
        "omicsclaw.runtime",
        "omicsclaw.runtime.context",
        "omicsclaw.runtime.context_layers",
        "httpx",
        "httpcore",
        "openai",
    ):
        logging.getLogger(noisy).setLevel(level)


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
    from prompt_toolkit.completion import Completer, Completion, PathCompleter
    from prompt_toolkit.document import Document

    class _OmniCompleter(Completer):
        def __init__(self):
            self.path_completer = PathCompleter(expanduser=True)
            self._skills_cache = None

        def get_completions(self, document: Document, complete_event):
            text = document.text_before_cursor

            # 1. Slash commands
            if text.startswith("/") and " " not in text.strip():
                for cmd, desc in complete_slash_command_rows(
                    text,
                    CLI_SLASH_COMMAND_SPECS,
                ):
                    if cmd.startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=f"{cmd:<20}",
                            display_meta=desc,
                        )
                return

            # 2. Skill completion for /run <skill>
            if text.startswith("/run "):
                if self._skills_cache is None:
                    try:
                        self._skills_cache = list_registered_skill_names()
                    except Exception:
                        self._skills_cache = []
                skill_prefix = text[len("/run "):].lstrip()
                for skill_name in complete_run_skill_names(text, self._skills_cache):
                    yield Completion(
                        skill_name,
                        start_position=-len(skill_prefix),
                        display_meta="OmicsClaw Skill"
                    )

            # 3. File path completion
            words = text.split(" ")
            last_word = words[-1]
            if last_word.startswith("./") or last_word.startswith("/") or last_word.startswith("~/"):
                path_doc = Document(text=last_word, cursor_position=len(last_word))
                try:
                    for comp in self.path_completer.get_completions(path_doc, complete_event):
                        yield Completion(
                            comp.text,
                            start_position=-len(last_word),
                            display=comp.display,
                            display_meta="File Path"
                        )
                except Exception:
                    pass

    return _OmniCompleter()


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


def _truncate_preview(text: str, *, max_chars: int) -> str:
    value = str(text or "").replace("\n", " ")
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "..."


def _format_tool_args_preview(args: dict[str, Any], *, max_chars: int = 80) -> str:
    try:
        rendered = json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        rendered = str(args)
    return _truncate_preview(rendered, max_chars=max_chars)


def _format_tool_result_preview(tool_name: str, result: Any, *, max_chars: int = 220) -> str:
    result_text = strip_user_guidance_lines(str(result))
    if tool_name == "inspect_data":
        marker = "### Method Suitability & Parameter Preview"
        pos = result_text.find(marker)
        if pos >= 0:
            result_text = result_text[pos:]
    return _truncate_preview(result_text, max_chars=max_chars)


def _print_stream_section_header(label: str, *, style: str) -> None:
    console.print(Text(label, style=style))


def _print_tool_activity_entry(label: str, detail: str, *, label_style: str) -> None:
    line = Text("  ")
    line.append(label, style=label_style)
    line.append("  ", style="dim")
    line.append(detail, style="dim")
    console.print(line)


def _stream_output_contains_final_text(streamed_content: str, final_text: str) -> bool:
    streamed = str(streamed_content or "").rstrip()
    final = str(final_text or "").rstrip()
    return bool(final) and streamed.endswith(final)


def _append_inline_markdown(target: Text, source: str) -> None:
    cursor = 0
    for match in _INLINE_MARKDOWN_TOKEN_RE.finditer(source):
        start, end = match.span()
        if start > cursor:
            target.append(source[cursor:start])

        if match.group("link"):
            target.append(match.group("link_label"), style="underline cyan")
            target.append(f" ({match.group('link_url')})", style="dim")
        elif match.group("bold"):
            target.append(match.group("bold_text"), style="bold")
        elif match.group("underline"):
            target.append(match.group("underline_text"), style="bold")
        elif match.group("code"):
            target.append(match.group("code_text"), style="bold yellow")
        elif match.group("italic"):
            target.append(match.group("italic_text"), style="italic")
        elif match.group("italic_u"):
            target.append(match.group("italic_u_text"), style="italic")

        cursor = end

    if cursor < len(source):
        target.append(source[cursor:])


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _render_cli_markdown_line(line: str) -> Text:
    body, ending = _split_line_ending(line)
    output = Text()

    if not body.strip():
        if ending:
            output.append(ending)
        return output

    stripped = body.strip()
    if stripped.startswith("```"):
        if ending:
            output.append(ending)
        return output

    strong_match = _STRONG_LINE_RE.match(body)
    atx_heading_match = _ATX_HEADING_RE.match(body)
    bullet_match = _BULLET_LINE_RE.match(body)
    numbered_match = _NUMBERED_LINE_RE.match(body)
    blockquote_match = _BLOCKQUOTE_LINE_RE.match(body)

    if strong_match:
        _append_inline_markdown(output, strong_match.group(1).strip())
        output.stylize("bold cyan", 0, len(output))
    elif atx_heading_match:
        _append_inline_markdown(output, atx_heading_match.group(1).strip())
        output.stylize("bold cyan", 0, len(output))
    elif bullet_match:
        indent = bullet_match.group("indent")
        output.append(f"{indent}- ", style="dim")
        _append_inline_markdown(output, bullet_match.group("body"))
    elif numbered_match:
        indent = numbered_match.group("indent")
        number = numbered_match.group("number")
        output.append(f"{indent}{number}. ", style="dim")
        _append_inline_markdown(output, numbered_match.group("body"))
    elif blockquote_match:
        output.append("| ", style="dim")
        _append_inline_markdown(output, blockquote_match.group("body"))
    else:
        _append_inline_markdown(output, body)

    if ending:
        output.append(ending)
    return output


def _find_safe_plain_prefix_length(buffer: str) -> int:
    if not buffer:
        return 0

    if _MARKDOWN_LINE_START_RE.match(buffer) or _UNCERTAIN_MARKDOWN_PREFIX_RE.match(buffer):
        return 0

    positions: list[int] = []
    for marker in ("**", "__", "```", "`", "[", "*", "_"):
        idx = buffer.find(marker)
        if idx >= 0:
            positions.append(idx)

    if positions:
        first = min(positions)
        return first if first > 0 else 0

    return len(buffer)


class _CliMarkdownStreamFormatter:
    def __init__(self) -> None:
        self._pending = ""

    def write(self, chunk: str) -> None:
        self._pending += str(chunk or "")
        self._emit_available()

    def finish(self) -> None:
        if not self._pending:
            return
        self._emit_rendered(self._pending)
        self._pending = ""

    def _emit_available(self) -> None:
        while True:
            newline_index = self._pending.find("\n")
            if newline_index < 0:
                break
            line = self._pending[: newline_index + 1]
            self._pending = self._pending[newline_index + 1 :]
            self._emit_rendered(line)

        safe_prefix_len = _find_safe_plain_prefix_length(self._pending)
        if safe_prefix_len <= 0:
            return
        plain_prefix = self._pending[:safe_prefix_len]
        self._pending = self._pending[safe_prefix_len:]
        console.print(Text(plain_prefix), end="", soft_wrap=True)

    def _emit_rendered(self, line: str) -> None:
        console.print(_render_cli_markdown_line(line), end="", soft_wrap=True)


def _print_cli_response_text(text: str) -> None:
    formatter = _CliMarkdownStreamFormatter()
    formatter.write(text)
    formatter.finish()


def _session_metadata_from_state(state: SessionState) -> dict[str, Any]:
    metadata = enrich_session_metadata(
        state.session_metadata,
        messages=state.messages,
        workspace_dir=state.workspace_dir or "",
        pipeline_workspace=state.pipeline_workspace or None,
        omicsclaw_dir=_OMICSCLAW_DIR,
    )
    state.session_metadata = metadata
    return metadata


def _active_pipeline_workspace(state: SessionState) -> str | None:
    pipeline_workspace = resolve_active_pipeline_workspace(
        state.pipeline_workspace or None,
        state.session_metadata,
    )
    if pipeline_workspace:
        state.pipeline_workspace = pipeline_workspace
        state.session_metadata = build_session_metadata(
            state.session_metadata,
            pipeline_workspace=pipeline_workspace,
        )
        return pipeline_workspace
    state.session_metadata = build_session_metadata(
        state.session_metadata,
        pipeline_workspace=None,
    )
    return None


def _active_output_style(state: SessionState) -> str | None:
    return resolve_active_output_style(state.session_metadata)


def _active_scoped_memory_scope(state: SessionState) -> str:
    return resolve_active_scoped_memory_scope(state.session_metadata)


def _set_active_pipeline_workspace(state: SessionState, workspace: str | None) -> None:
    state.set_pipeline_workspace(str(workspace or "").strip() or None)
    state.session_metadata = build_session_metadata(
        state.session_metadata,
        pipeline_workspace=state.pipeline_workspace,
    )


async def _persist_session_state(
    state: SessionState,
    *,
    model: str = "",
) -> None:
    await save_session(
        state.session_id,
        state.messages,
        model=model,
        workspace=state.workspace_dir,
        metadata=_session_metadata_from_state(state),
        transcript=state.messages,
    )


# ---------------------------------------------------------------------------
# Slash-command handlers
# ---------------------------------------------------------------------------

def _handle_skills(arg: str) -> None:
    """List skills, optionally filtered by domain."""
    try:
        console.print(list_skills_text(arg.strip() or None), markup=False)
    except Exception as e:
        console.print(f"[red]Error listing skills: {escape(str(e))}[/red]")


def _configured_mcp_server_names() -> tuple[str, ...]:
    return tuple(
        entry["name"]
        for entry in list_mcp_servers()
        if str(entry.get("name", "") or "").strip()
    )


def _print_skill_run_execution(execution: SkillRunExecutionView) -> None:
    if not execution.system_summary_lines:
        return

    first_line = escape(execution.system_summary_lines[0])
    if execution.success:
        console.print(f"[green]{first_line}[/green]")
    elif execution.system_summary_lines[0].startswith("⚠"):
        console.print(f"[yellow]{first_line}[/yellow]")
    else:
        console.print(f"[red]{first_line}[/red]")

    for line in execution.system_summary_lines[1:]:
        console.print(escape(line))

    if execution.stdout:
        console.print(execution.stdout)


def _apply_pipeline_command_view(
    state: SessionState,
    view,
) -> None:
    if getattr(view, "active_workspace", ""):
        _set_active_pipeline_workspace(state, view.active_workspace)
    console.print(view.output_text)


def _apply_interactive_plan_command_view(
    state: SessionState,
    view,
) -> None:
    if getattr(view, "replace_session_metadata", False):
        metadata = normalize_session_metadata(getattr(view, "session_metadata", {}))
        state.session_metadata = metadata
        state.pipeline_workspace = str(metadata.get("pipeline_workspace", "") or "")

    text = str(getattr(view, "output_text", "") or "")
    if not text:
        return
    if getattr(view, "success", True):
        console.print(text)
    else:
        console.print(f"[red]{escape(text)}[/red]")


def _apply_session_command_view(
    state: SessionState,
    view,
) -> None:
    if getattr(view, "session_id", ""):
        state.session_id = view.session_id
    if getattr(view, "workspace_dir", ""):
        state.workspace_dir = view.workspace_dir
    if getattr(view, "replace_session_metadata", False):
        metadata = normalize_session_metadata(getattr(view, "session_metadata", {}))
        state.session_metadata = metadata
        state.pipeline_workspace = str(metadata.get("pipeline_workspace", "") or "")
    if getattr(view, "clear_messages", False):
        state.messages = []
    if getattr(view, "replace_messages", False):
        state.messages = list(getattr(view, "messages", []))
    if getattr(view, "clear_pipeline_workspace", False):
        _set_active_pipeline_workspace(state, None)

    text = str(getattr(view, "output_text", "") or "")
    if not text:
        return
    if getattr(view, "render_as_markup", False):
        console.print(text)
        return
    if getattr(view, "success", True):
        console.print(f"[green]{escape(text)}[/green]")
    else:
        console.print(f"[red]{escape(text)}[/red]")


def _print_skill_command_status(status: SkillCommandStatus) -> None:
    text = escape(status.text)
    if status.level == "success":
        console.print(f"[green]{text}[/green]")
    elif status.level == "warning":
        console.print(f"[yellow]{text}[/yellow]")
    elif status.level == "error":
        console.print(f"[red]{text}[/red]")
    else:
        console.print(f"[dim]{text}[/dim]")


def _handle_run(arg: str) -> SkillRunExecutionView | None:
    """Run a skill inline via the shared `/run` command contract."""
    command = parse_skill_run_command(arg)
    if command is None:
        console.print(f"[yellow]Usage: {RUN_COMMAND_USAGE}[/yellow]")
        return None

    try:
        with console.status(f"[cyan]Running skill: {command.skill}...[/cyan]"):
            result = run_skill_command(command)
        execution = build_skill_run_execution_view(
            arg,
            skill=command.skill,
            result=result,
        )
    except Exception as exc:
        execution = build_skill_run_exception_result(
            arg,
            skill=command.skill,
            exc=exc,
        )
    _print_skill_run_execution(execution)
    return execution


def _handle_doctor(
    state: SessionState,
) -> None:
    _apply_session_command_view(
        state,
        build_doctor_command_view(
            workspace_dir=state.workspace_dir or "",
            pipeline_workspace=_active_pipeline_workspace(state) or "",
            omicsclaw_dir=str(_OMICSCLAW_DIR),
            output_dir=str(_OMICSCLAW_DIR / "output"),
        ),
    )


def _handle_context(
    arg: str,
    state: SessionState,
) -> None:
    _apply_session_command_view(
        state,
        build_context_command_view(
            arg,
            messages=state.messages,
            session_metadata=state.session_metadata,
            workspace_dir=state.workspace_dir or "",
            pipeline_workspace=_active_pipeline_workspace(state) or "",
            output_style=_active_output_style(state) or "",
            omicsclaw_dir=str(_OMICSCLAW_DIR),
            mcp_servers=_configured_mcp_server_names(),
            surface="interactive",
        ),
    )


def _handle_usage(
    state: SessionState,
) -> None:
    _apply_session_command_view(
        state,
        build_usage_command_view(),
    )


async def _handle_sessions(arg: str = "") -> None:
    """List recent sessions in a table."""
    view = await build_session_list_view(limit=20, query=arg)
    if not view.entries:
        console.print(f"[yellow]{view.empty_text}[/yellow]")
        return
    title = "Sessions"
    if view.query:
        title = f"Sessions · {view.query}"
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold yellow", no_wrap=True)
    table.add_column("Title / Preview", style="", max_width=50, no_wrap=True)
    table.add_column("State", style="dim", max_width=54)
    table.add_column("Msgs", justify="right")
    table.add_column("Model", style="dim")
    table.add_column("Last Used", style="dim")
    for entry in view.entries:
        table.add_row(
            entry.session_id,
            entry.title or entry.preview,
            entry.state_summary,
            str(entry.message_count),
            entry.model,
            entry.updated_label,
        )
    console.print()
    console.print(table)
    console.print(f"[dim]  {view.hint_text}[/dim]")
    console.print()


async def _pick_session_interactive(
    current_id: str,
    *,
    query: str = "",
) -> str | None:
    """Show an interactive session picker using questionary."""
    view = await build_session_list_view(limit=20, query=query)
    if not view.entries:
        console.print(f"[yellow]{view.empty_text}[/yellow]")
        return None

    try:
        import questionary

        choices = []
        for entry in view.entries:
            sid = entry.session_id
            preview = entry.title or entry.preview or sid
            when = entry.updated_label
            marker = " ●" if sid == current_id else ""
            state_summary = f" · {entry.state_summary}" if entry.state_summary else ""
            label = f"{preview[:46]:<48}{state_summary[:48]:<50} [{sid}  {when}]{marker}"
            choices.append(questionary.Choice(title=label, value=sid))

        selected = questionary.select(
            "Select session to resume:" if not view.query else f"Select session to resume ({view.query}):",
            choices=choices,
            style=_PICKER_STYLE,
        ).ask()
        return selected
    except ImportError:
        # Fallback: show list and ask for input
        await _handle_sessions(query)
        console.print("Enter session ID to resume (or press Enter to cancel): ", end="")
        try:
            sid = input().strip()
            return sid if sid else None
        except (EOFError, KeyboardInterrupt):
            return None


async def _handle_resume(arg: str, state: SessionState) -> None:
    """Resume a saved session by ID or interactive picker."""
    target_id = arg.strip()
    if not target_id:
        selected = await _pick_session_interactive(state.session_id)
        if not selected:
            return
        target_id = selected

    view = await build_resume_session_command_view(target_id)
    if view.success:
        _apply_session_command_view(state, view)
        if view.render_as_markup:
            console.print()
        return

    search_view = await build_session_list_view(limit=20, query=target_id)
    if not search_view.entries:
        _apply_session_command_view(state, view)
        return
    if len(search_view.entries) == 1:
        resolved_view = await build_resume_session_command_view(
            search_view.entries[0].session_id
        )
        _apply_session_command_view(state, resolved_view)
        if resolved_view.render_as_markup:
            console.print()
        return

    console.print(
        f"[yellow]Multiple sessions matched '{escape(target_id)}'. Narrow the query or choose one below.[/yellow]"
    )
    selected = await _pick_session_interactive(
        state.session_id,
        query=target_id,
    )
    if not selected:
        return
    resolved_view = await build_resume_session_command_view(selected)
    _apply_session_command_view(state, resolved_view)
    if resolved_view.render_as_markup:
        console.print()


async def _handle_delete(arg: str, state: SessionState) -> None:
    """Delete a session by ID."""
    view = await build_delete_session_command_view(
        arg.strip(),
        current_session_id=state.session_id,
    )
    _apply_session_command_view(state, view)


async def _handle_memory(arg: str, state: SessionState, *, model: str = "") -> None:
    """Manage memory entries — ScopedMemory (markdown) and graph memory."""
    if is_graph_memory_subcommand(arg):
        graph_view = await build_graph_memory_command_view(
            arg,
            workspace_dir=state.workspace_dir or "",
        )
        _apply_session_command_view(state, graph_view)
        return

    view = build_memory_command_view(
        arg,
        session_metadata=state.session_metadata,
        workspace_dir=state.workspace_dir or "",
        pipeline_workspace=_active_pipeline_workspace(state) or "",
    )
    _apply_session_command_view(state, view)
    if getattr(view, "replace_session_metadata", False) and model:
        await _persist_session_state(state, model=model)


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

def _handle_install_extension(arg: str) -> None:
    for status in install_extension_from_source(arg, omicsclaw_dir=_OMICSCLAW_DIR):
        _print_skill_command_status(status)


def _handle_install_skill(arg: str) -> None:
    """Install a skill-pack from a local path or a GitHub URL."""
    statuses = install_skill_from_source(arg, omicsclaw_dir=_OMICSCLAW_DIR)
    if len(statuses) == 1 and statuses[0].text == build_extension_install_usage_text():
        statuses = [SkillCommandStatus("error", "Usage: /install-skill <local-path | github-url>")]
    for status in statuses:
        _print_skill_command_status(status)


def _handle_installed_extensions() -> None:
    view = build_installed_extension_list_view(omicsclaw_dir=_OMICSCLAW_DIR)
    if not view.entries:
        console.print(f"[yellow]{view.empty_text}[/yellow]")
        console.print(f"[dim]{view.hint_text}[/dim]")
        return
    console.print(format_installed_extension_list_plain(view), markup=False)


def _handle_installed_skills() -> None:
    view = build_installed_skill_list_view(omicsclaw_dir=_OMICSCLAW_DIR)
    if not view.entries:
        console.print(f"[yellow]{view.empty_text}[/yellow]")
        console.print(f"[dim]{view.hint_text}[/dim]")
        return
    console.print(format_installed_skill_list_plain(view), markup=False)


def _handle_refresh_extensions() -> None:
    for status in build_refresh_extensions_statuses(omicsclaw_dir=_OMICSCLAW_DIR):
        _print_skill_command_status(status)


def _handle_refresh_skills() -> None:
    for status in build_refresh_skills_statuses(omicsclaw_dir=_OMICSCLAW_DIR):
        _print_skill_command_status(status)


def _handle_tasks(arg: str, state: SessionState) -> None:
    if _should_route_plan_commands_to_pipeline(arg, state):
        view = build_pipeline_tasks_command_view(
            arg.strip() or None,
            workspace_fallback=_active_pipeline_workspace(state) or state.workspace_dir or None,
        )
        _apply_pipeline_command_view(state, view)
        return

    view = build_interactive_tasks_command_view(
        session_metadata=state.session_metadata,
    )
    _apply_interactive_plan_command_view(state, view)


def _handle_plan(arg: str, state: SessionState) -> bool:
    if _should_route_plan_commands_to_pipeline(arg, state):
        view = build_plan_preview_command_view(
            arg.strip() or None,
            workspace_fallback=_active_pipeline_workspace(state) or state.workspace_dir or None,
        )
        _apply_pipeline_command_view(state, view)
        return False

    view = build_interactive_plan_command_view(
        arg,
        session_metadata=state.session_metadata,
        messages=state.messages,
        workspace_dir=state.workspace_dir or "",
        omicsclaw_dir=str(_OMICSCLAW_DIR),
    )
    _apply_interactive_plan_command_view(state, view)
    return view.persist_session


def _handle_approve_plan(arg: str, state: SessionState) -> bool:
    if not _should_route_plan_commands_to_pipeline(arg, state):
        view = build_interactive_approve_plan_command_view(
            arg,
            session_metadata=state.session_metadata,
            omicsclaw_dir=str(_OMICSCLAW_DIR),
        )
        _apply_interactive_plan_command_view(state, view)
        return view.persist_session

    try:
        view = build_approve_plan_command_view(
            arg,
            workspace_fallback=_active_pipeline_workspace(state) or state.workspace_dir or None,
            omicsclaw_dir=str(_OMICSCLAW_DIR),
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return False

    _apply_pipeline_command_view(state, view)
    return view.persist_session


async def _run_research_pipeline(
    command_args,
    state: SessionState,
) -> None:
    pdf_path = command_args.pdf_path
    idea = command_args.idea
    h5ad_path = command_args.h5ad_path
    resume = command_args.resume
    from_stage = command_args.from_stage
    skip_stages = command_args.skip_stages
    plan_only = command_args.plan_only

    if not idea and not (resume or from_stage):
        console.print("[red]--idea is required unless you are resuming an existing workspace.[/red]")
        return

    if resume and from_stage:
        console.print("[red]Use either --resume or --from-stage, not both.[/red]")
        return

    if pdf_path and not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        return

    if h5ad_path and not Path(h5ad_path).exists():
        console.print(f"[red]h5ad file not found: {h5ad_path}[/red]")
        return

    try:
        from omicsclaw.agents import _check_research_deps
        _check_research_deps()
    except ImportError as e:
        console.print(f'[red]{e}[/red]')
        console.print('[yellow]Install with: pip install -e ".[research]"[/yellow]')
        return

    if pdf_path and h5ad_path:
        mode = "B"
    elif pdf_path:
        mode = "A"
    else:
        mode = "C"

    workspace_path = str(
        resolve_research_workspace(
            command_args.output_dir,
            _active_pipeline_workspace(state) or state.workspace_dir or None,
        )
    )
    _set_active_pipeline_workspace(state, workspace_path)
    snapshot = load_pipeline_workspace_snapshot(workspace_path)

    console.print()
    console.print(
        format_research_start_summary(
            command_args,
            workspace_path,
            snapshot,
            mode=mode,
        )
    )
    console.print()

    def on_stage(stage: str, status: str):
        console.print(f"  [cyan]▸ [{stage}][/cyan] {status}")

    try:
        from omicsclaw.agents.pipeline import ResearchPipeline
        from omicsclaw.agents.pipeline_result import normalize_pipeline_result

        pipeline = ResearchPipeline(workspace_dir=workspace_path)
        raw_result = await pipeline.run(
            idea=idea,
            pdf_path=pdf_path,
            h5ad_path=h5ad_path,
            on_stage=on_stage,
            resume=resume,
            from_stage=from_stage,
            skip_stages=skip_stages,
            plan_only=plan_only,
        )
        result = normalize_pipeline_result(raw_result)
        if result.workspace:
            _set_active_pipeline_workspace(state, result.workspace)

        console.print()
        console.print(
            format_research_result_summary(
                result,
                workspace_fallback=workspace_path,
                idea=idea,
            )
        )

        state.messages.extend(
            build_research_history_entries(
                command_args,
                result,
                mode=mode,
                workspace_fallback=workspace_path,
            )
        )

        await _persist_session_state(state)
    except Exception as e:
        console.print(f"[red]Research pipeline error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        if state.messages:
            await _persist_session_state(state)


async def _handle_research(arg: str, state: SessionState) -> None:
    """Start or resume the multi-agent research pipeline."""
    if not arg.strip():
        console.print(
            "[yellow]Usage:[/yellow]\n"
            "[dim]  Mode A: /research paper.pdf --idea \"explore TME heterogeneity\"\n"
            "  Mode B: /research paper.pdf --idea \"...\" --h5ad data.h5ad\n"
            "  Mode C: /research --idea \"explore TME heterogeneity\"\n"
            "  Resume: /research --resume --output /path/to/workspace\n"
            "  Stage : /research --from-stage analyze --output /path/to/workspace\n"
            "  Plan  : /research --idea \"...\" --plan-only\n"
            "  Skip  : /research --idea \"...\" --skip research,review[/dim]"
        )
        return

    try:
        command_args = parse_research_command(arg)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    await _run_research_pipeline(command_args, state)


async def _handle_resume_task(arg: str, state: SessionState) -> bool:
    """Resume the research pipeline from a specific structured stage."""
    if not _should_route_resume_task_to_pipeline(arg, state):
        view = build_interactive_resume_task_command_view(
            arg,
            session_metadata=state.session_metadata,
            omicsclaw_dir=str(_OMICSCLAW_DIR),
        )
        _apply_interactive_plan_command_view(state, view)
        return view.persist_session

    try:
        command_args = parse_resume_task_command(arg)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return False

    await _run_research_pipeline(command_args, state)
    return False


async def _handle_do_current_task(arg: str, state: SessionState) -> bool:
    snapshot = load_interactive_plan_from_metadata(state.session_metadata)
    if snapshot is None and _should_route_plan_commands_to_pipeline("", state):
        console.print(
            "[yellow]/do-current-task currently targets interactive session plans. "
            "Use /resume-task <stage> to continue a research pipeline workspace.[/yellow]"
        )
        return False

    view = build_do_current_task_command_view(
        arg,
        session_metadata=state.session_metadata,
        omicsclaw_dir=str(_OMICSCLAW_DIR),
    )
    _apply_interactive_plan_command_view(state, view)
    if not view.success:
        return False
    if view.execution_prompt:
        await _continue_interactive_turn(state, view.execution_prompt)
    return view.persist_session or bool(view.execution_prompt)


def _confirm_extension_removal(name: str) -> bool:
    console.print(
        f"[yellow]Remove extension '{name}'? (y/N)[/yellow] ",
        end="",
    )
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Cancelled.[/dim]")
        return False
    if answer not in ("y", "yes"):
        console.print("[dim]Cancelled.[/dim]")
        return False
    return True


def _handle_uninstall_extension(arg: str, *, expected_type: str = "") -> None:
    name = arg.strip()
    if not name:
        _print_skill_command_status(
            SkillCommandStatus(
                "error",
                "Usage: /uninstall-extension <name>" if not expected_type else "Usage: /uninstall-skill <name>",
            )
        )
        return
    if not _confirm_extension_removal(name):
        return
    for status in uninstall_extension(
        name,
        omicsclaw_dir=_OMICSCLAW_DIR,
        expected_type=expected_type,
    ):
        _print_skill_command_status(status)


def _handle_uninstall_skill(arg: str) -> None:
    _handle_uninstall_extension(arg, expected_type="skill-pack")


def _handle_toggle_extension(arg: str, *, enable: bool) -> None:
    for status in set_installed_extension_enabled(
        arg,
        enable=enable,
        omicsclaw_dir=_OMICSCLAW_DIR,
    ):
        _print_skill_command_status(status)



def _init_llm(config: dict) -> tuple[str, str]:
    """Initialize bot/core LLM. Returns (model, provider)."""
    try:
        sys.path.insert(0, str(_OMICSCLAW_DIR))
        import bot.core as core
        load_project_dotenv(_OMICSCLAW_DIR, override=False)

        provider = str(config.get("provider", "") or os.environ.get("LLM_PROVIDER", "") or "")
        api_key = str(config.get("api_key", "") or os.environ.get("LLM_API_KEY", "") or "")
        model = str(config.get("model", "") or os.environ.get("OMICSCLAW_MODEL", "") or "")
        base_url = str(config.get("base_url", "") or os.environ.get("LLM_BASE_URL", "") or "")

        _configure_cli_loggers()

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


async def _stream_llm_response(
    messages: list[dict],
    *,
    plan_context: str = "",
    workspace_dir: str = "",
    pipeline_workspace: str = "",
    scoped_memory_scope: str = "",
    output_style: str = "",
) -> str:
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
        user_text = seed_core_conversation(core, _INTERACTIVE_USER, messages)

        # Snapshot usage before the call to compute per-turn delta
        usage_before = core.get_usage_snapshot()

        streamed_content = ""
        stream_started = False
        response_started = False
        tool_log_started = False
        last_zone: str | None = None
        next_tool_sequence = 1
        pending_tool_sequences: dict[str, deque[int]] = defaultdict(deque)
        response_formatter = _CliMarkdownStreamFormatter()

        with console.status("[cyan]Thinking...[/cyan]", spinner="dots") as status:
            def enter_tool_zone() -> None:
                nonlocal last_zone, tool_log_started
                if last_zone == "tool":
                    return
                if last_zone == "response":
                    response_formatter.finish()
                if stream_started and streamed_content and not streamed_content.endswith("\n"):
                    console.print()
                console.print()
                if not tool_log_started:
                    _print_stream_section_header("TOOL LOG", style="bold dim")
                    tool_log_started = True
                else:
                    _print_stream_section_header("TOOL UPDATE", style="dim")
                last_zone = "tool"

            def sync_on_tool_call(tool_name: str, args: dict):
                nonlocal next_tool_sequence
                status.update(f"[cyan]Running {tool_name}...[/cyan]")
                enter_tool_zone()
                sequence = next_tool_sequence
                next_tool_sequence += 1
                pending_tool_sequences[tool_name].append(sequence)
                _print_tool_activity_entry(
                    f"CALL #{sequence}",
                    f"{tool_name}({_format_tool_args_preview(args)})",
                    label_style="bold cyan",
                )

            def sync_on_tool_result(tool_name: str, result: str):
                status.update("[cyan]Thinking...[/cyan]")
                enter_tool_zone()
                sequence_queue = pending_tool_sequences[tool_name]
                sequence = sequence_queue.popleft() if sequence_queue else None
                label = f"DONE #{sequence}" if sequence is not None else "DONE"
                _print_tool_activity_entry(
                    label,
                    _format_tool_result_preview(tool_name, result),
                    label_style="bold green",
                )

            async def sync_on_stream_content(chunk: str):
                nonlocal streamed_content, stream_started, response_started, last_zone
                if not stream_started:
                    status.stop()
                    stream_started = True
                if last_zone != "response":
                    if last_zone == "tool":
                        console.print()
                        header = "RESPONSE" if not response_started else "RESPONSE CONTINUES"
                        _print_stream_section_header(header, style="bold cyan")
                    else:
                        console.print()
                    response_started = True
                    last_zone = "response"

                streamed_content += chunk
                response_formatter.write(chunk)

            try:
                active_mcp_servers = await load_active_mcp_server_entries_for_prompt()
                loop_kwargs = {
                    "user_id": "cli_user",
                    "platform": "cli",
                    "plan_context": plan_context,
                    "workspace": workspace_dir or "",
                    "pipeline_workspace": pipeline_workspace or "",
                    "mcp_servers": active_mcp_servers,
                    "on_tool_call": sync_on_tool_call,
                    "on_tool_result": sync_on_tool_result,
                    "on_stream_content": sync_on_stream_content,
                }
                if scoped_memory_scope:
                    loop_kwargs["scoped_memory_scope"] = scoped_memory_scope
                if output_style:
                    loop_kwargs["output_style"] = output_style
                llm_task = asyncio.create_task(core.llm_tool_loop(
                    _INTERACTIVE_USER,
                    user_text,
                    **loop_kwargs,
                ))

                async def _watch_escape():
                    import sys
                    import termios
                    import tty
                    loop = asyncio.get_running_loop()
                    try:
                        fd = sys.stdin.fileno()
                        if not os.isatty(fd):
                            await asyncio.sleep(86400)
                            return False
                    except Exception:
                        await asyncio.sleep(86400)
                        return False

                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setcbreak(fd)
                        while not llm_task.done():
                            def _read():
                                import select
                                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                                if r: return sys.stdin.read(1)
                                return None
                            char = await loop.run_in_executor(None, _read)
                            if char in ('\x1b', '\x03'): # ESC or Ctrl+C
                                return True
                    except Exception:
                        pass
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    return False

                watcher_task = asyncio.create_task(_watch_escape())
                done, pending = await asyncio.wait([llm_task, watcher_task], return_when=asyncio.FIRST_COMPLETED)

                if watcher_task in done and watcher_task.result() is True:
                    # User interrupted via ESC or Ctrl+C
                    llm_task.cancel()
                    try:
                        await llm_task
                    except asyncio.CancelledError:
                        pass
                    
                    status.stop()
                    sys.stdout.write("\r\033[K")
                    console.print("\n[yellow]Conversation interrupted - tell the model what to do differently. Something went wrong?[/yellow]")
                    append_interruption_notice(
                        core,
                        _INTERACTIVE_USER,
                        text=(
                            "Conversation interrupted - tell the model what "
                            "to do differently. Something went wrong?"
                        ),
                        messages=messages,
                    )
                    final_text = ""
                else:
                    watcher_task.cancel()
                    final_text = llm_task.result()
            finally:
                response_formatter.finish()
                if stream_started and streamed_content and not streamed_content.endswith("\n"):
                    console.print()

        if final_text and not streamed_content:
            console.print()
            _print_cli_response_text(final_text)
            if not final_text.endswith("\n"):
                console.print()

        if (
            streamed_content
            and final_text
            and not _stream_output_contains_final_text(streamed_content, final_text)
        ):
            if not streamed_content.endswith("\n"):
                console.print()
            _print_cli_response_text(final_text)
            if not final_text.endswith("\n"):
                console.print()

        # Display per-turn usage statistics (inspired by EvoScientist)
        _display_usage_stats(core, usage_before)

        # Sync the updated conversation history back to our messages list
        sync_core_conversation(core, _INTERACTIVE_USER, messages)

        return final_text or ""
    except Exception as e:
        err_msg = f"LLM error: {e}"
        console.print(f"[red]{escape(err_msg)}[/red]")
        if "api_key" in str(e).lower() or "authentication" in str(e).lower():
            console.print("[dim]Run [bold]oc onboard[/bold] to configure your API key.[/dim]")
        return err_msg


async def _continue_interactive_turn(
    state: SessionState,
    user_prompt: str,
) -> str:
    state.messages.append({"role": "user", "content": user_prompt})
    console.print()
    return await _stream_llm_response(
        state.messages,
        plan_context=_interactive_plan_context(state),
        workspace_dir=state.workspace_dir or "",
        pipeline_workspace=_active_pipeline_workspace(state) or "",
        scoped_memory_scope=_active_scoped_memory_scope(state),
        output_style=_active_output_style(state) or "",
    )


def _display_usage_stats(core, usage_before: dict) -> None:
    """Display per-turn token usage statistics.

    Shows a right-aligned line like:
        [Usage: 1,234 in · 567 out | $0.0012]
    """
    try:
        usage_after = core.get_usage_snapshot()
        delta = build_usage_delta(usage_before, usage_after)

        if not delta.has_usage:
            return

        stats = Text(justify="right")
        stats.append("[", style="dim italic")
        stats.append("Usage: ", style="dim italic")
        stats.append(f"{delta.prompt_tokens:,}", style="cyan italic")
        stats.append(" in · ", style="dim italic")
        stats.append(f"{delta.completion_tokens:,}", style="green italic")
        stats.append(" out", style="dim italic")

        # Show cost estimate if pricing is available
        if delta.estimated_cost_usd > 0:
            stats.append(" | ", style="dim italic")
            stats.append(f"${delta.estimated_cost_usd:.4f}", style="yellow italic")

        stats.append("]", style="dim italic")
        console.print(stats)
    except Exception:
        pass  # Silently skip on any usage retrieval error


def _command_leading_value(arg: str) -> str | None:
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    if tokens and not tokens[0].startswith("--"):
        return tokens[0]
    return None


def _pipeline_snapshot_exists(
    explicit_workspace: str | None,
    *,
    workspace_fallback: str | None,
) -> bool:
    snapshot = load_pipeline_workspace_snapshot(
        resolve_pipeline_workspace(explicit_workspace, workspace_fallback)
    )
    return (
        snapshot.has_pipeline_state
        or snapshot.plan_path.exists()
        or snapshot.todos_path.exists()
    )


def _should_route_plan_commands_to_pipeline(
    arg: str,
    state: SessionState,
) -> bool:
    workspace_fallback = _active_pipeline_workspace(state) or state.workspace_dir or None
    if _pipeline_snapshot_exists(None, workspace_fallback=workspace_fallback):
        return True
    explicit_workspace = _command_leading_value(arg)
    return bool(
        explicit_workspace
        and _pipeline_snapshot_exists(
            explicit_workspace,
            workspace_fallback=workspace_fallback,
        )
    )


def _should_route_resume_task_to_pipeline(
    arg: str,
    state: SessionState,
) -> bool:
    workspace_fallback = _active_pipeline_workspace(state) or state.workspace_dir or None
    if _pipeline_snapshot_exists(None, workspace_fallback=workspace_fallback):
        return True
    try:
        command_args = parse_resume_task_command(arg)
    except ValueError:
        return False
    if not command_args.output_dir:
        return False
    return _pipeline_snapshot_exists(
        command_args.output_dir,
        workspace_fallback=workspace_fallback,
    )


def _interactive_plan_context(state: SessionState) -> str:
    return build_interactive_plan_context_from_metadata(
        state.session_metadata
    )


def _maybe_seed_interactive_plan(
    state: SessionState,
    user_input: str,
) -> bool:
    workspace_fallback = _active_pipeline_workspace(state) or state.workspace_dir or None
    if _pipeline_snapshot_exists(None, workspace_fallback=workspace_fallback):
        return False

    seed = maybe_seed_interactive_plan(
        user_input,
        session_metadata=state.session_metadata,
        workspace_dir=state.workspace_dir or "",
        omicsclaw_dir=str(_OMICSCLAW_DIR),
    )
    if not seed.created:
        return False

    state.session_metadata = normalize_session_metadata(seed.session_metadata)
    if seed.notice_text:
        console.print(f"[dim]{escape(seed.notice_text)}[/dim]")
        console.print()
    return True


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

    # Quiet noisy loggers in interactive mode to prevent analysis logs from
    # flooding the terminal.  Override with OMICSCLAW_LOG_LEVEL=INFO.
    _configure_cli_loggers()

    init_config = {**config}
    if model:
        init_config["model"] = model
    if provider:
        init_config["provider"] = provider

    # Init LLM
    resolved_model, resolved_provider = _init_llm(init_config)

    # Initialise session
    effective_session_id = session_id or generate_session_id()
    effective_workspace = workspace_dir or str(_OMICSCLAW_DIR)

    # Mutable state
    state = SessionState(
        session_id=effective_session_id,
        workspace_dir=effective_workspace,
        ui_backend=ui_backend,
    )

    # Try to resume existing session
    if session_id:
        data = await load_session(session_id)
        if data:
            _apply_session_command_view(
                state,
                build_resume_session_command_view_from_data(data),
            )
            console.print()
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
        state.session_id,
        state.workspace_dir,
        resolved_model,
        resolved_provider,
        ui_backend,
        mode=mode,
    )
    console.print(Text(f"  {random.choice(WELCOME_SLOGANS)}", style="dim italic"))
    console.print()
    _print_separator()

    # ── Main REPL loop ──
    while state.running:
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
            command = parse_slash_command(user_input, CLI_SLASH_COMMAND_SPECS)

            if command is not None and command.name == "/exit":
                console.print("[dim]Goodbye! See you next time.[/dim]")
                state.stop()
                break

            elif command is not None and command.name == "/help":
                table = Table(title="OmicsClaw Commands", show_header=True, header_style="bold cyan")
                table.add_column("Command", style="bold yellow", no_wrap=True)
                table.add_column("Description")
                for cmd, desc in slash_command_help_rows(CLI_SLASH_COMMAND_SPECS):
                    table.add_row(cmd, desc)
                console.print(table)
                console.print()
                _print_separator()
                continue

            if command is not None and command.name == "/skills":
                _handle_skills(command.arg)
                _print_separator()
                continue

            elif command is not None and command.name == "/run":
                run_result = _handle_run(command.arg)
                if run_result:
                    state.messages.extend(run_result.history_messages)
                    await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/research":
                await _handle_research(command.arg, state)
                _print_separator()
                continue

            elif command is not None and command.name == "/approve-plan":
                if _handle_approve_plan(command.arg, state):
                    await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/resume-task":
                if await _handle_resume_task(command.arg, state):
                    await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/do-current-task":
                if await _handle_do_current_task(command.arg, state):
                    await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/tasks":
                _handle_tasks(command.arg, state)
                _print_separator()
                continue

            elif command is not None and command.name == "/plan":
                if _handle_plan(command.arg, state):
                    await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/sessions":
                await _handle_sessions(command.arg)
                _print_separator()
                continue

            elif command is not None and command.name == "/resume":
                await _handle_resume(command.arg, state)
                _print_separator()
                continue

            elif command is not None and command.name == "/delete":
                await _handle_delete(command.arg, state)
                _print_separator()
                continue

            elif command is not None and command.name == "/new":
                _apply_session_command_view(
                    state,
                    build_new_session_command_view(generate_session_id()),
                )
                _print_separator()
                continue

            elif command is not None and command.name == "/current":
                _apply_session_command_view(
                    state,
                    build_current_session_command_view(
                        session_id=state.session_id,
                        workspace_dir=state.workspace_dir,
                        model=resolved_model,
                        provider=resolved_provider,
                        messages=state.messages,
                        session_metadata=state.session_metadata,
                        pipeline_workspace=state.pipeline_workspace or None,
                        omicsclaw_dir=_OMICSCLAW_DIR,
                    ),
                )
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/session-title":
                _apply_session_command_view(
                    state,
                    build_session_title_command_view(
                        command.arg,
                        session_metadata=state.session_metadata,
                    ),
                )
                await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/session-tag":
                _apply_session_command_view(
                    state,
                    build_session_tag_command_view(
                        command.arg,
                        session_metadata=state.session_metadata,
                    ),
                )
                await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/doctor":
                _handle_doctor(state)
                _print_separator()
                continue

            elif command is not None and command.name == "/context":
                _handle_context(command.arg, state)
                _print_separator()
                continue

            elif command is not None and command.name == "/usage":
                _handle_usage(state)
                _print_separator()
                continue

            elif command is not None and command.name == "/memory":
                await _handle_memory(
                    command.arg,
                    state,
                    model=resolved_model,
                )
                _print_separator()
                continue

            elif command is not None and command.name == "/style":
                _apply_session_command_view(
                    state,
                    build_style_command_view(
                        command.arg,
                        session_metadata=state.session_metadata,
                        omicsclaw_dir=str(_OMICSCLAW_DIR),
                    ),
                )
                await _persist_session_state(state, model=resolved_model)
                _print_separator()
                continue

            elif command is not None and command.name == "/clear":
                _apply_session_command_view(
                    state,
                    build_clear_conversation_command_view(),
                )
                _print_separator()
                continue

            elif command is not None and command.name == "/export":
                _apply_session_command_view(
                    state,
                    build_export_session_command_view(
                        state.session_id,
                        state.messages,
                        workspace_dir=state.workspace_dir,
                    ),
                )
                _print_separator()
                continue

            elif command is not None and command.name == "/mcp":
                _handle_mcp(command.arg)
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/config":
                _handle_config(command.arg)
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/tips":
                arg = command.arg.lower()
                if arg in ("on", ""):
                    state.set_tips(enabled=True)
                    console.print("[green]💡 Inline knowledge tips: ON[/green]")
                    try:
                        from omicsclaw.knowledge.telemetry import get_telemetry
                        get_telemetry().log_tips_toggle(state.session_id, True, state.tips_level)
                    except Exception:
                        pass
                elif arg == "off":
                    state.set_tips(enabled=False)
                    console.print("[dim]💡 Inline knowledge tips: OFF[/dim]")
                    try:
                        from omicsclaw.knowledge.telemetry import get_telemetry
                        get_telemetry().log_tips_toggle(state.session_id, False, state.tips_level)
                    except Exception:
                        pass
                elif arg.startswith("level"):
                    level = arg[len("level"):].strip()
                    try:
                        state.set_tips(level=level)
                        console.print(f"[cyan]💡 Tips level set to: {level}[/cyan]")
                    except ValueError:
                        console.print("[yellow]Usage: /tips level [basic|expert][/yellow]")
                else:
                    status = "ON" if state.tips_enabled else "OFF"
                    level = state.tips_level
                    console.print(f"[dim]💡 Tips: {status} (level: {level})[/dim]")
                    console.print("[dim]  /tips on     — enable inline knowledge tips[/dim]")
                    console.print("[dim]  /tips off    — disable tips[/dim]")
                    console.print("[dim]  /tips level basic|expert — set detail level[/dim]")
                console.print()
                _print_separator()
                continue



            elif command is not None and command.name == "/install-extension":
                _handle_install_extension(command.arg)
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/installed-extensions":
                _handle_installed_extensions()
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/refresh-extensions":
                _handle_refresh_extensions()
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/disable-extension":
                _handle_toggle_extension(command.arg, enable=False)
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/enable-extension":
                _handle_toggle_extension(command.arg, enable=True)
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/uninstall-extension":
                _handle_uninstall_extension(command.arg)
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/install-skill":
                _handle_install_skill(command.arg)
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/installed-skills":
                _handle_installed_skills()
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/refresh-skills":
                _handle_refresh_skills()
                console.print()
                _print_separator()
                continue

            elif command is not None and command.name == "/uninstall-skill":
                _handle_uninstall_skill(command.arg)
                console.print()
                _print_separator()
                continue

            # ── Regular LLM conversation ──
            _maybe_seed_interactive_plan(state, user_input)
            response = await _continue_interactive_turn(state, user_input)

            # Save session after each exchange
            await _persist_session_state(state, model=resolved_model)

            console.print()
            _print_separator()
            # console.print()  # breathing room before next prompt

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye! See you next time.[/dim]")
            state.running = False
            break
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            state.running = False
            break
        except Exception as e:
            console.print(f"[red]Unexpected error: {escape(str(e))}[/red]")
            logger.exception("Interactive loop error")
            _print_separator()

    # Final session save on exit
    if state.messages:
        await _persist_session_state(state, model=resolved_model)


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
    init_config = dict(config or {})
    if model:
        init_config["model"] = model
    if provider:
        init_config["provider"] = provider
    _configure_cli_loggers()
    resolved_model, _ = _init_llm(init_config)

    session_id = generate_session_id()
    messages: list[dict] = [{"role": "user", "content": prompt}]

    width = console.size.width
    console.print(Text("─" * width, style="dim"))
    console.print(Text(f"> {prompt}"))
    console.print(Text("─" * width, style="dim"))
    console.print(f"[dim]Session: {session_id}[/dim]")
    console.print()

    await _stream_llm_response(
        messages,
        workspace_dir=workspace_dir or str(_OMICSCLAW_DIR),
        pipeline_workspace="",
    )

    await save_session(
        session_id,
        messages,
        model=resolved_model,
        workspace=workspace_dir or str(_OMICSCLAW_DIR),
        metadata={},
        transcript=messages,
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
