"""OmicsClaw Textual TUI — full-screen terminal user interface.

Requires: textual>=0.80
Install:  pip install textual
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import shlex
import sys
import time as _time
from pathlib import Path

from omicsclaw.common.runtime_env import load_project_dotenv

logger = logging.getLogger(__name__)
_OMICSCLAW_DIR = Path(__file__).resolve().parent.parent.parent

try:
    from textual import events, on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.css.query import NoMatches
    from textual.message import Message
    from textual.widgets import (
        Collapsible,
        DirectoryTree,
        Footer,
        Label,
        Static,
        TextArea,
    )
    _HAS_TEXTUAL = True
except ImportError:
    _HAS_TEXTUAL = False


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
    build_usage_delta,
    seed_core_conversation,
    sync_core_conversation,
)
from ._mcp import list_mcp_servers, load_active_mcp_server_entries_for_prompt
from ._memory_command_support import (
    build_memory_command_view,
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
    load_pipeline_workspace_snapshot,
    parse_resume_task_command,
    resolve_pipeline_workspace,
)
from ._skill_run_support import (
    build_skill_run_exception_result,
    build_skill_run_execution_view,
    parse_skill_run_command,
)
from ._skill_management_support import (
    SkillCommandStatus,
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
    TUI_SLASH_COMMAND_SPECS,
    complete_run_skill_names,
    complete_slash_command_rows,
    format_tui_help_text,
    parse_slash_command,
)
from ._session import (
    generate_session_id,
    save_session,
)
from ._session_command_support import (
    build_clear_conversation_command_view,
    build_current_session_command_view,
    build_export_session_command_view,
    build_new_session_command_view,
    build_resume_session_command_view,
    build_session_tag_command_view,
    build_session_metadata,
    build_session_title_command_view,
    build_session_list_view,
    enrich_session_metadata,
    format_session_list_plain,
    normalize_session_metadata,
    resolve_active_output_style,
    resolve_active_pipeline_workspace,
)
from ._style_support import build_style_command_view
from ._tui_support import build_tui_header_label


# ---------------------------------------------------------------------------
# TUI CSS
# ---------------------------------------------------------------------------

_APP_CSS = """
Screen {
    background: #0d1117;
}

#header-bar {
    height: 3;
    background: #161b22;
    border-bottom: solid #21262d;
    padding: 0 2;
    align: center middle;
}

#header-title {
    color: #00b8b8;
    text-style: bold;
    width: auto;
}

#header-info {
    color: #8b949e;
    width: auto;
    content-align: right middle;
    text-align: right;
}

#chat-area {
    height: 1fr;
    overflow-y: auto;
    padding: 1 2;
    background: #0d1117;
}

.msg-user {
    margin-top: 1;
    margin-bottom: 0;
    color: #c9d1d9;
}

.msg-user-label {
    color: #58a6ff;
    text-style: bold;
}

.msg-assistant {
    margin-top: 0;
    margin-bottom: 1;
    color: #c9d1d9;
}

.msg-assistant-label {
    color: #00b8b8;
    text-style: bold;
}

.msg-system {
    color: #8b949e;
    text-style: italic;
    margin: 0;
    padding: 0 0 0 0;
}

#input-area {
    height: auto;
    min-height: 3;
    background: #161b22;
    border-top: solid #21262d;
    padding: 1;
    align: center middle;
}

#chat-input {
    background: #21262d;
    border: solid #30363d;
    color: #c9d1d9;
    width: 1fr;
    height: 5;
    margin-right: 1;
}

#chat-input:focus {
    border: solid #58a6ff;
}

#send-hint {
    color: #8b949e;
    width: auto;
    padding-top: 1;
}

Footer {
    background: #161b22;
    color: #8b949e;
    height: 1;
}

#usage-bar {
    height: 1;
    background: #0d1117;
    border-top: solid #21262d;
    padding: 0 2;
    align: left middle;
}

#usage-label {
    color: #484f58;
    width: 1fr;
}

#main-area {
    height: 1fr;
}

#chat-container {
    width: 1fr;
    height: 1fr;
}

#sidebar {
    width: 30;
    dock: left;
    height: 1fr;
    background: #0d1117;
    border-right: solid #30363d;
    display: none;
}
"""


# ---------------------------------------------------------------------------
# TUI App
# ---------------------------------------------------------------------------

if _HAS_TEXTUAL:
    class ChatTextArea(TextArea):
        """Custom multiline TextArea supporting Enter to submit and Shift+Enter for newline."""
        
        # BINDINGS are often ignored by TextArea for text-editing inputs like 'enter'
        # so we must explicitly intercept the raw Key events.
        def _on_key(self, event: events.Key) -> None:
            if event.key == "enter":
                event.prevent_default()
                self.action_submit()
            elif event.key in ("shift+enter", "ctrl+j", "alt+enter"):
                # Handle shift+enter. Also provide ctrl+j/alt+enter as a fallback
                # for older terminals that cannot differentiate shift+enter from enter.
                event.prevent_default()
                self.action_insert_newline()
            elif event.key == "tab":
                event.prevent_default()
                self.action_autocomplete()
            else:
                super()._on_key(event)

        def action_autocomplete(self) -> None:
            if not hasattr(self, "_tab_matches"):
                self._tab_matches = []
                self._tab_index = 0
                self._tab_prefix = ""

            row, col = self.cursor_location
            line = self.document.get_line(row)
            prefix = line[:col]

            # If user is continuing a cycle
            if self._tab_matches and prefix in self._tab_matches and prefix.startswith(self._tab_prefix):
                self._tab_index = (self._tab_index + 1) % len(self._tab_matches)
                match = self._tab_matches[self._tab_index]
                if hasattr(self, "replace"):
                    self.replace(match, (row, 0), (row, col))
                return

            # Start a new autocomplete session
            if not prefix.startswith("/"):
                if hasattr(self, "insert_text"):
                    self.insert_text("\t")
                elif hasattr(self, "replace"):
                    self.replace("\t", self.cursor_location, self.cursor_location)
                return

            matches = []

            if " " not in prefix:
                matches = [
                    command + " "
                    for command, _description in complete_slash_command_rows(
                        prefix,
                        TUI_SLASH_COMMAND_SPECS,
                    )
                ]
            elif prefix.startswith("/run "):
                try:
                    matches = [
                        "/run " + skill_name + " "
                        for skill_name in complete_run_skill_names(
                            prefix,
                            list_registered_skill_names(),
                        )
                    ]
                except Exception:
                    pass

            if matches:
                self._tab_prefix = prefix
                self._tab_matches = sorted(matches) + [prefix]
                self._tab_index = 0
                match = self._tab_matches[0]
                if hasattr(self, "replace"):
                    self.replace(match, (row, 0), (row, col))

        class Submitted(Message):
            def __init__(self, control: "ChatTextArea", text: str) -> None:
                self._control = control
                self.text = text
                super().__init__()

            @property
            def control(self) -> "ChatTextArea":
                return self._control

        def action_submit(self) -> None:
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(self, text))
                self.text = ""

        def action_insert_newline(self) -> None:
            # Safely invoke the native newline behavior across all Textual versions
            if hasattr(self, "action_newline"):
                self.action_newline()
            elif hasattr(self, "insert_text"):
                self.insert_text("\n")
            elif hasattr(self, "replace"):
                self.replace("\n", self.cursor_location, self.cursor_location)
            else:
                # Absolute fallback buffer append
                self.text += "\n"

    class OmicsClawTUI(App):
        """OmicsClaw full-screen terminal chat interface."""

        CSS = _APP_CSS
        TITLE = "OmicsClaw"
        BINDINGS = [
            Binding("ctrl+n", "new_session", "New session"),
            Binding("ctrl+l", "clear_chat", "Clear chat"),
            Binding("ctrl+b", "toggle_sidebar", "Toggle Sidebar"),
            Binding("ctrl+s", "show_sessions", "Sessions"),
            Binding("ctrl+h", "show_help", "Help"),
            Binding("ctrl+q", "quit", "Quit"),
        ]

        def __init__(
            self,
            session_id: str | None = None,
            workspace_dir: str | None = None,
            model: str = "",
            provider: str = "",
            config: dict | None = None,
            mode: str | None = None,
        ):
            super().__init__()
            self._requested_session_id = session_id
            self._session_id = session_id or generate_session_id()
            self._workspace = workspace_dir or str(_OMICSCLAW_DIR)
            self._model = model
            self._provider = provider
            self._config = config or {}
            self._mode = mode
            self._messages: list[dict] = []
            self._session_metadata: dict[str, object] = {}
            self._pipeline_workspace = ""
            self._thinking = False
            # Session-level usage statistics
            self._session_stats: dict[str, int] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "api_calls": 0,
            }
            self._session_start = _time.time()

        def _active_pipeline_workspace(self) -> str | None:
            active = resolve_active_pipeline_workspace(
                self._pipeline_workspace,
                self._session_metadata,
            )
            if active:
                self._pipeline_workspace = active
                self._session_metadata = build_session_metadata(
                    self._session_metadata,
                    pipeline_workspace=active,
                )
            else:
                self._session_metadata = build_session_metadata(
                    self._session_metadata,
                    pipeline_workspace=None,
                )
            return active

        def _active_output_style(self) -> str | None:
            return resolve_active_output_style(self._session_metadata)

        def _active_scoped_memory_scope(self) -> str:
            return resolve_active_scoped_memory_scope(self._session_metadata)

        def _configured_mcp_server_names(self) -> tuple[str, ...]:
            return tuple(
                entry["name"]
                for entry in list_mcp_servers()
                if str(entry.get("name", "") or "").strip()
            )

        def _set_active_pipeline_workspace(self, workspace: str | None) -> None:
            value = str(workspace or "").strip()
            self._pipeline_workspace = value
            self._session_metadata = build_session_metadata(
                self._session_metadata,
                pipeline_workspace=value,
            )

        async def _persist_session(self) -> None:
            await save_session(
                self._session_id,
                self._messages,
                model=self._model,
                workspace=self._workspace,
                metadata=enrich_session_metadata(
                    self._session_metadata,
                    messages=self._messages,
                    workspace_dir=self._workspace,
                    pipeline_workspace=self._pipeline_workspace,
                    omicsclaw_dir=_OMICSCLAW_DIR,
                ),
                transcript=self._messages,
            )

        def _refresh_header_info(self) -> None:
            try:
                self.query_one("#header-info", Label).update(
                    build_tui_header_label(
                        model=self._model,
                        session_id=self._session_id,
                        mode=self._mode,
                    )
                )
            except NoMatches:
                pass

        def _get_welcome_renderable(self):
            from rich.text import Text
            
            welcome = Text()
            welcome.append("\n")
            for line, color in zip(LOGO_LINES, LOGO_GRADIENT):
                welcome.append(f"{line}\n", style=f"{color} bold")
            
            welcome.append("\n  ", style="dim")
            if self._mode:
                welcome.append(f"Mode: ", style="dim")
                welcome.append(f"{self._mode}", style="magenta")
                welcome.append(f"  ·  ", style="dim")
            welcome.append(f"Session: ", style="dim")
            welcome.append(f"{self._session_id}", style="magenta")
            welcome.append(f"  ·  Workspace: ", style="dim")
            
            home = os.path.expanduser("~")
            ws = self._workspace
            dir_display = ws.replace(home, "~", 1) if ws.startswith(home) else ws
            welcome.append(f"{dir_display}\n", style="cyan")
            
            welcome.append("\n  Type ", style="#ffe082")
            welcome.append("/", style="#ffe082 bold")
            welcome.append(" for commands, ", style="#ffe082")
            welcome.append("Ctrl+H", style="#ffe082 bold")
            welcome.append(" or ", style="#ffe082")
            welcome.append("/help", style="#ffe082 bold")
            welcome.append(" for full menu\n\n", style="#ffe082")
            
            welcome.append(f"  > {random.choice(WELCOME_SLOGANS)}\n", style="dim italic")
            
            return welcome

        def compose(self) -> ComposeResult:
            with Horizontal(id="header-bar"):
                yield Label("⬡ OmicsClaw", id="header-title")
                yield Label(
                    build_tui_header_label(
                        model=self._model,
                        session_id=self._session_id,
                        mode=self._mode,
                    ),
                    id="header-info",
                )
            with Horizontal(id="main-area"):
                yield DirectoryTree(self._workspace, id="sidebar")
                with Vertical(id="chat-container"):
                    with ScrollableContainer(id="chat-area"):
                        yield Static(
                            self._get_welcome_renderable(),
                            classes="msg-system",
                        )
                    with Horizontal(id="usage-bar"):
                        yield Label(
                            "Tokens: 0 in · 0 out  │  Cost: $0.000000  │  Calls: 0",
                            id="usage-label",
                        )
                    with Horizontal(id="input-area"):
                        yield ChatTextArea(id="chat-input")
                        yield Label("[dim]Enter to send[/dim]\n[dim]Shift+Enter newline[/dim]", id="send-hint")
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#chat-input", ChatTextArea).focus()
            if self._requested_session_id:
                self.run_worker(self._resume_initial_session_async(), exclusive=False)
            # Load LLM in background
            self.run_worker(self._init_llm_async(), exclusive=True)

        async def _resume_initial_session_async(self) -> None:
            requested_session_id = self._requested_session_id
            if not requested_session_id:
                return

            view = await build_resume_session_command_view(requested_session_id)
            if view.success:
                self._apply_session_command_view(view)
                return

            from rich.markup import escape

            self._add_system_message(
                f"[yellow]Session '{escape(requested_session_id)}' not found — starting fresh.[/yellow]"
            )

        async def _init_llm_async(self) -> None:
            try:
                sys.path.insert(0, str(_OMICSCLAW_DIR))
                import bot.core as core
                load_project_dotenv(_OMICSCLAW_DIR, override=False)
                provider = os.environ.get("LLM_PROVIDER", self._config.get("provider", ""))
                api_key = os.environ.get("LLM_API_KEY", self._config.get("api_key", ""))
                model = os.environ.get("OMICSCLAW_MODEL", self._config.get("model", ""))
                base_url = os.environ.get("LLM_BASE_URL", self._config.get("base_url", ""))
                
                logging.getLogger("omicsclaw.bot").setLevel(logging.WARNING)
                # Suppress verbose loggers in TUI mode to make output cleaner
                logging.getLogger("httpx").setLevel(logging.WARNING)
                logging.getLogger("httpcore").setLevel(logging.WARNING)
                logging.getLogger("omicsclaw.memory").setLevel(logging.WARNING)
                logging.getLogger("omicsclaw.memory.snapshot").setLevel(logging.WARNING)

                
                core.init(api_key=api_key, base_url=base_url or None, model=model, provider=provider)
                self._model = core.OMICSCLAW_MODEL
                self._provider = core.LLM_PROVIDER_NAME
                self._refresh_header_info()
            except Exception as e:
                logger.warning("LLM init error: %s", e)
                self._add_system_message(f"⚠ LLM init error: {e}\nRun 'python omicsclaw.py onboard' to configure.")

        @on(ChatTextArea.Submitted, "#chat-input")
        async def _on_submit(self, event: ChatTextArea.Submitted) -> None:
            text = event.text.strip()
            if not text:
                return
            # TextArea is already cleared locally

            # Slash commands
            command = parse_slash_command(text, TUI_SLASH_COMMAND_SPECS)

            if command is not None and command.name == "/exit":
                self.exit()
                return

            elif command is not None and command.name == "/help":
                self._add_system_message(format_tui_help_text(TUI_SLASH_COMMAND_SPECS))
                return

            elif command is not None and command.name == "/skills":
                self.run_worker(self._list_skills_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/run":
                self._add_user_message(text)
                self.run_worker(self._run_skill_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/tasks":
                self.run_worker(self._show_tasks_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/plan":
                self.run_worker(self._show_plan_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/current":
                self._apply_session_command_view(
                    build_current_session_command_view(
                        session_id=self._session_id,
                        workspace_dir=self._workspace,
                        model=self._model,
                        provider=self._provider,
                        messages=self._messages,
                        session_metadata=self._session_metadata,
                        pipeline_workspace=self._pipeline_workspace,
                        omicsclaw_dir=_OMICSCLAW_DIR,
                    )
                )
                return

            elif command is not None and command.name == "/approve-plan":
                self.run_worker(self._approve_plan_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/resume-task":
                self.run_worker(self._resume_task_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/do-current-task":
                self.run_worker(self._do_current_task_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/new":
                self._apply_session_command_view(
                    build_new_session_command_view(generate_session_id())
                )
                return

            elif command is not None and command.name == "/style":
                self._apply_session_command_view(
                    build_style_command_view(
                        command.arg,
                        session_metadata=self._session_metadata,
                        omicsclaw_dir=str(_OMICSCLAW_DIR),
                    )
                )
                await self._persist_session()
                return

            elif command is not None and command.name == "/clear":
                self._apply_session_command_view(
                    build_clear_conversation_command_view()
                )
                return

            elif command is not None and command.name == "/export":
                self._apply_session_command_view(
                    build_export_session_command_view(
                        self._session_id,
                        self._messages,
                        workspace_dir=self._workspace,
                    )
                )
                return

            elif command is not None and command.name == "/sessions":
                self.run_worker(self._show_sessions_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/resume":
                self.run_worker(self._resume_session_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/session-title":
                self._apply_session_command_view(
                    build_session_title_command_view(
                        command.arg,
                        session_metadata=self._session_metadata,
                    )
                )
                await self._persist_session()
                return

            elif command is not None and command.name == "/session-tag":
                self._apply_session_command_view(
                    build_session_tag_command_view(
                        command.arg,
                        session_metadata=self._session_metadata,
                    )
                )
                await self._persist_session()
                return

            elif command is not None and command.name == "/doctor":
                self.run_worker(self._show_doctor_async(), exclusive=False)
                return

            elif command is not None and command.name == "/context":
                self.run_worker(self._show_context_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/memory":
                view = build_memory_command_view(
                    command.arg,
                    session_metadata=self._session_metadata,
                    workspace_dir=self._workspace,
                    pipeline_workspace=self._active_pipeline_workspace() or "",
                )
                self._apply_session_command_view(view)
                if getattr(view, "replace_session_metadata", False):
                    await self._persist_session()
                return

            elif command is not None and command.name == "/usage":
                self._show_usage()
                return

            elif command is not None and command.name == "/install-extension":
                self._add_user_message(text)
                self.run_worker(self._install_extension_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/installed-extensions":
                self.run_worker(self._show_installed_extensions_async(), exclusive=False)
                return

            elif command is not None and command.name == "/refresh-extensions":
                self.run_worker(self._refresh_extensions_async(), exclusive=False)
                return

            elif command is not None and command.name == "/disable-extension":
                self._add_user_message(text)
                self.run_worker(
                    self._toggle_extension_enabled_async(command.arg, enable=False),
                    exclusive=False,
                )
                return

            elif command is not None and command.name == "/enable-extension":
                self._add_user_message(text)
                self.run_worker(
                    self._toggle_extension_enabled_async(command.arg, enable=True),
                    exclusive=False,
                )
                return

            elif command is not None and command.name == "/uninstall-extension":
                self._add_user_message(text)
                self.run_worker(self._uninstall_extension_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/install-skill":
                self._add_user_message(text)
                self.run_worker(self._install_skill_async(command.arg), exclusive=False)
                return

            elif command is not None and command.name == "/installed-skills":
                self.run_worker(self._show_installed_skills_async(), exclusive=False)
                return

            elif command is not None and command.name == "/refresh-skills":
                self.run_worker(self._refresh_skills_async(), exclusive=False)
                return

            elif command is not None and command.name == "/uninstall-skill":
                self._add_user_message(text)
                self.run_worker(self._uninstall_skill_async(command.arg), exclusive=False)
                return

            # Regular message — send to LLM
            self._maybe_seed_interactive_plan(text)
            self._add_user_message(text)
            self._messages.append({"role": "user", "content": text})
            self.run_worker(self._llm_response_async(), exclusive=True)

        def _add_user_message(self, text: str) -> None:
            chat = self.query_one("#chat-area", ScrollableContainer)
            from rich.text import Text
            from rich.markup import escape
            msg = Text.from_markup(f"[bold cyan]You ❯[/bold cyan] {escape(text)}")
            msg.overflow = "fold"
            chat.mount(Static(msg, classes="msg-user"))
            self.call_after_refresh(chat.scroll_end)

        def _add_assistant_message(self, text: str) -> None:
            chat = self.query_one("#chat-area", ScrollableContainer)
            from rich.markdown import Markdown
            chat.mount(Static(""))  # Add visual spacing before AI message
            chat.mount(Static("[bold #00b8b8]AI ❯[/bold #00b8b8]", classes="msg-assistant-label"))
            chat.mount(Static(Markdown(text), classes="msg-assistant"))
            self.call_after_refresh(chat.scroll_end)

        def _add_system_message(self, text: str) -> None:
            chat = self.query_one("#chat-area", ScrollableContainer)
            from rich.text import Text
            msg = Text.from_markup(text)
            msg.overflow = "fold"
            chat.mount(Static(msg, classes="msg-system"))
            self.call_after_refresh(chat.scroll_end)

        def _apply_skill_command_status(self, status: SkillCommandStatus) -> None:
            if status.level == "success":
                self._add_system_message(f"[green]{status.text}[/green]")
            elif status.level == "warning":
                self._add_system_message(f"[yellow]{status.text}[/yellow]")
            elif status.level == "error":
                self._add_system_message(f"[red]{status.text}[/red]")
            else:
                self._add_system_message(status.text)

        def _clear_chat_widgets(self) -> None:
            chat = self.query_one("#chat-area", ScrollableContainer)
            for widget in list(chat.children):
                widget.remove()

        def _clear_core_conversation(self) -> None:
            try:
                import bot.core as core

                core.conversations.pop("__tui__", None)
            except Exception:
                pass

        def _reset_session_runtime_state(self) -> None:
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "api_calls",
            ):
                self._session_stats[key] = 0
            self._session_start = _time.time()
            try:
                import bot.core as core

                core.reset_usage()
            except Exception:
                pass
            try:
                self.query_one("#usage-label", Label).update(
                    "Tokens: 0 in · 0 out  │  Cost: $0.000000  │  Calls: 0"
                )
            except Exception:
                pass

        def _apply_session_command_view(self, view) -> None:
            if getattr(view, "session_id", ""):
                self._session_id = view.session_id
            if getattr(view, "workspace_dir", ""):
                self._workspace = view.workspace_dir
            if getattr(view, "replace_session_metadata", False):
                metadata = normalize_session_metadata(
                    getattr(view, "session_metadata", {})
                )
                self._session_metadata = metadata
                self._pipeline_workspace = str(
                    metadata.get("pipeline_workspace", "") or ""
                )
            if getattr(view, "clear_pipeline_workspace", False):
                self._set_active_pipeline_workspace(None)
            if getattr(view, "clear_messages", False):
                self._messages = []
                self._clear_core_conversation()
                self._clear_chat_widgets()
            if getattr(view, "replace_messages", False):
                self._messages = list(getattr(view, "messages", []))
            if getattr(view, "reset_session_runtime", False):
                self._reset_session_runtime_state()
            self._refresh_header_info()
            text = str(getattr(view, "output_text", "") or "")
            if not text:
                return
            if getattr(view, "render_as_markup", False):
                self._add_system_message(text)
                return

            from rich.markup import escape

            if getattr(view, "success", True):
                self._add_system_message(f"[green]{escape(text)}[/green]")
            else:
                self._add_system_message(f"[red]{escape(text)}[/red]")

        def _apply_pipeline_command_view(self, view) -> None:
            if getattr(view, "active_workspace", ""):
                self._set_active_pipeline_workspace(view.active_workspace)
            self._add_system_message(view.output_text)

        def _apply_interactive_plan_command_view(self, view) -> None:
            if getattr(view, "replace_session_metadata", False):
                metadata = normalize_session_metadata(
                    getattr(view, "session_metadata", {})
                )
                self._session_metadata = metadata
                self._pipeline_workspace = str(
                    metadata.get("pipeline_workspace", "") or ""
                )
            text = str(getattr(view, "output_text", "") or "")
            if not text:
                return
            if getattr(view, "success", True):
                self._add_system_message(text)
            else:
                from rich.markup import escape

                self._add_system_message(f"[red]{escape(text)}[/red]")

        def _command_leading_value(self, arg: str) -> str | None:
            tokens = shlex.split(arg.strip()) if arg.strip() else []
            if tokens and not tokens[0].startswith("--"):
                return tokens[0]
            return None

        def _pipeline_snapshot_exists(self, explicit_workspace: str | None) -> bool:
            snapshot = load_pipeline_workspace_snapshot(
                resolve_pipeline_workspace(
                    explicit_workspace,
                    self._active_pipeline_workspace() or self._workspace,
                )
            )
            return (
                snapshot.has_pipeline_state
                or snapshot.plan_path.exists()
                or snapshot.todos_path.exists()
            )

        def _should_route_plan_commands_to_pipeline(self, arg: str) -> bool:
            if self._pipeline_snapshot_exists(None):
                return True
            explicit_workspace = self._command_leading_value(arg)
            return bool(
                explicit_workspace
                and self._pipeline_snapshot_exists(explicit_workspace)
            )

        def _should_route_resume_task_to_pipeline(self, arg: str) -> bool:
            if self._pipeline_snapshot_exists(None):
                return True
            try:
                command_args = parse_resume_task_command(arg)
            except ValueError:
                return False
            if not command_args.output_dir:
                return False
            return self._pipeline_snapshot_exists(command_args.output_dir)

        def _interactive_plan_context(self) -> str:
            return build_interactive_plan_context_from_metadata(
                self._session_metadata,
            )

        def _maybe_seed_interactive_plan(self, user_text: str) -> bool:
            if self._pipeline_snapshot_exists(None):
                return False
            seed = maybe_seed_interactive_plan(
                user_text,
                session_metadata=self._session_metadata,
                workspace_dir=self._workspace,
                omicsclaw_dir=str(_OMICSCLAW_DIR),
            )
            if not seed.created:
                return False
            self._session_metadata = normalize_session_metadata(seed.session_metadata)
            if seed.notice_text:
                self._add_system_message(f"[dim]{seed.notice_text}[/dim]")
            return True

        # ------------------------------------------------------------------
        # LLM response worker
        # ------------------------------------------------------------------

        async def _llm_response_async(self) -> None:
            self._thinking = True
            self._add_system_message("⏳ Thinking...")
            t0 = _time.time()
            try:
                sys.path.insert(0, str(_OMICSCLAW_DIR))
                import bot.core as core

                _USER = "__tui__"
                last_user_msg = seed_core_conversation(core, _USER, self._messages)
                usage_before = core.get_usage_snapshot()
                import json
                self._current_reasoning = None

                async def tui_on_tool_call(tool_name: str, args: dict):
                    args_preview = json.dumps(args)[:80] + ("..." if len(json.dumps(args)) > 80 else "")
                    chat = self.query_one("#chat-area", ScrollableContainer)
                    
                    if not getattr(self, "_current_reasoning", None):
                        c = Collapsible(title="🧠 Agent Reasoning & Tool Execution")
                        v = Vertical()
                        c.mount(v)
                        chat.mount(c)
                        self._current_reasoning = v
                    
                    from rich.text import Text
                    msg = Text.from_markup(f"[dim]↳ 🛠️  Calling [cyan]{tool_name}[/cyan]({args_preview})[/dim]")
                    msg.overflow = "fold"
                    self._current_reasoning.mount(Static(msg, classes="msg-system"))
                    self.call_after_refresh(chat.scroll_end)

                async def tui_on_tool_result(tool_name: str, result: str):
                    if not getattr(self, "_current_reasoning", None):
                        return
                    result_preview = str(result)[:80].replace("\n", " ") + ("..." if len(str(result)) > 80 else "")
                    from rich.text import Text
                    msg = Text.from_markup(f"[dim]↳ ✓ [green]Result:[/green] {result_preview}[/dim]")
                    msg.overflow = "fold"
                    self._current_reasoning.mount(Static(msg, classes="msg-system"))
                    self.call_after_refresh(self.query_one("#chat-area", ScrollableContainer).scroll_end)

                # llm_tool_loop returns the final assistant reply as a plain string.
                # Pass user_id and platform so graph memory is active.
                active_mcp_servers = await load_active_mcp_server_entries_for_prompt()
                loop_kwargs = {
                    "user_id": "tui_user",
                    "platform": "tui",
                    "plan_context": self._interactive_plan_context(),
                    "workspace": self._workspace,
                    "pipeline_workspace": self._active_pipeline_workspace() or "",
                    "mcp_servers": active_mcp_servers,
                    "on_tool_call": tui_on_tool_call,
                    "on_tool_result": tui_on_tool_result,
                }
                active_memory_scope = self._active_scoped_memory_scope()
                if active_memory_scope:
                    loop_kwargs["scoped_memory_scope"] = active_memory_scope
                active_style = self._active_output_style() or ""
                if active_style:
                    loop_kwargs["output_style"] = active_style
                final_text = await core.llm_tool_loop(
                    _USER,
                    last_user_msg,
                    **loop_kwargs,
                )
                elapsed = _time.time() - t0

                # Collect usage snapshot from core
                try:
                    snap = core.get_usage_snapshot()
                    delta = build_usage_delta(usage_before, snap)
                    self._session_stats["prompt_tokens"] += delta.prompt_tokens
                    self._session_stats["completion_tokens"] += delta.completion_tokens
                    self._session_stats["total_tokens"] = (
                        self._session_stats["prompt_tokens"] + self._session_stats["completion_tokens"]
                    )
                    self._session_stats["api_calls"] += delta.api_calls
                    usage_line = (
                        f"[dim]↪ {delta.prompt_tokens:,} in · {delta.completion_tokens:,} out"
                    )
                    if delta.estimated_cost_usd > 0:
                        usage_line += f" · ${delta.estimated_cost_usd:.6f}"
                    usage_line += f" · {elapsed:.1f}s[/dim]"
                    self._update_usage_bar(snap)
                except Exception:
                    usage_line = f"[dim]↪ {elapsed:.1f}s[/dim]"

                # Sync the updated conversation history back to our messages list
                sync_core_conversation(core, _USER, self._messages)

                # Remove "⏳ Thinking..." message (last .msg-system widget)
                try:
                    chat = self.query_one("#chat-area", ScrollableContainer)
                    for widget in reversed(list(chat.children)):
                        rendered = getattr(widget, "renderable", None)
                        if "Thinking" in str(rendered):
                            widget.remove()
                            break
                except Exception:
                    pass

                self._add_assistant_message(final_text or "(no response)")
                # Show per-turn usage stats below the answer
                self._add_system_message(usage_line)

                await self._persist_session()
            except Exception as e:
                logger.exception("TUI LLM response error")
                self._add_system_message(f"⚠ Error: {e}")
            finally:
                self._thinking = False
                try:
                    self.query_one("#chat-input", ChatTextArea).focus()
                except Exception:
                    pass

        def _update_usage_bar(self, snap: dict) -> None:
            """Refresh the persistent usage bar with cumulative session stats."""
            try:
                sess_in  = self._session_stats["prompt_tokens"]
                sess_out = self._session_stats["completion_tokens"]
                calls    = self._session_stats["api_calls"]
                # Cumulative cost for session
                cost = (
                    sess_in  / 1_000_000 * snap.get("input_price_per_1m",  0) +
                    sess_out / 1_000_000 * snap.get("output_price_per_1m", 0)
                )
                label_text = (
                    f"● Tokens: {sess_in:,} in · {sess_out:,} out  │  "
                    f"Cost: ${cost:.6f}  │  Calls: {calls}  │  "
                    f"🤖 {snap.get('model', '?')}"
                )
                self.query_one("#usage-label", Label).update(label_text)
            except Exception:
                pass

        def _show_usage(self) -> None:
            """Display detailed usage statistics in the chat area."""
            self._apply_session_command_view(
                build_usage_command_view(
                    session_usage=self._session_stats,
                    session_seconds=_time.time() - self._session_start,
                )
            )

        async def _show_doctor_async(self) -> None:
            self._apply_session_command_view(
                build_doctor_command_view(
                    workspace_dir=self._workspace,
                    pipeline_workspace=self._active_pipeline_workspace() or "",
                    omicsclaw_dir=str(_OMICSCLAW_DIR),
                    output_dir=str(_OMICSCLAW_DIR / "output"),
                )
            )

        async def _show_context_async(self, arg: str) -> None:
            self._apply_session_command_view(
                build_context_command_view(
                    arg,
                    messages=self._messages,
                    session_metadata=self._session_metadata,
                    workspace_dir=self._workspace,
                    pipeline_workspace=self._active_pipeline_workspace() or "",
                    output_style=self._active_output_style() or "",
                    omicsclaw_dir=str(_OMICSCLAW_DIR),
                    mcp_servers=self._configured_mcp_server_names(),
                    surface="interactive",
                )
            )


        # ------------------------------------------------------------------
        # /skills worker — actually list skills in TUI chat area
        # ------------------------------------------------------------------

        async def _list_skills_async(self, domain_filter: str) -> None:
            """List registered skills, optionally filtered by domain."""
            try:
                self._add_system_message(list_skills_text(domain_filter or None))
            except Exception as e:
                logger.exception("list skills error")
                self._add_system_message(f"⚠ Error listing skills: {e}")

        # ------------------------------------------------------------------
        # /run worker
        # ------------------------------------------------------------------

        async def _run_skill_async(self, arg: str) -> None:
            command = parse_skill_run_command(arg)
            if command is None:
                self._add_system_message(f"Usage: {RUN_COMMAND_USAGE}")
                return

            self._add_system_message(f"⚙ Running skill: {command.skill}...")
            try:
                result = run_skill_command(command)
                execution = build_skill_run_execution_view(
                    arg,
                    skill=command.skill,
                    result=result,
                )
            except Exception as e:
                logger.exception("run skill error")
                execution = build_skill_run_execution_view(
                    arg,
                    skill=command.skill,
                    result=build_skill_run_exception_result(e),
                )

            self._add_system_message(execution.system_message)
            self._messages.extend(execution.history_messages)
            await self._persist_session()

        async def _show_tasks_async(self, arg: str) -> None:
            if self._should_route_plan_commands_to_pipeline(arg):
                view = build_pipeline_tasks_command_view(
                    arg or None,
                    workspace_fallback=self._active_pipeline_workspace() or self._workspace,
                )
                self._apply_pipeline_command_view(view)
                return

            view = build_interactive_tasks_command_view(
                session_metadata=self._session_metadata,
            )
            self._apply_interactive_plan_command_view(view)

        async def _show_plan_async(self, arg: str) -> None:
            if self._should_route_plan_commands_to_pipeline(arg):
                view = build_plan_preview_command_view(
                    arg or None,
                    workspace_fallback=self._active_pipeline_workspace() or self._workspace,
                )
                self._apply_pipeline_command_view(view)
                return

            view = build_interactive_plan_command_view(
                arg,
                session_metadata=self._session_metadata,
                messages=self._messages,
                workspace_dir=self._workspace,
                omicsclaw_dir=str(_OMICSCLAW_DIR),
            )
            self._apply_interactive_plan_command_view(view)
            if view.persist_session:
                await self._persist_session()

        async def _approve_plan_async(self, arg: str) -> None:
            if self._should_route_plan_commands_to_pipeline(arg):
                try:
                    view = build_approve_plan_command_view(
                        arg,
                        workspace_fallback=self._active_pipeline_workspace() or self._workspace,
                        omicsclaw_dir=str(_OMICSCLAW_DIR),
                    )
                    self._apply_pipeline_command_view(view)
                    if view.persist_session:
                        await self._persist_session()
                except ValueError as e:
                    self._add_system_message(f"✗ {e}")
                return

            view = build_interactive_approve_plan_command_view(
                arg,
                session_metadata=self._session_metadata,
                omicsclaw_dir=str(_OMICSCLAW_DIR),
            )
            self._apply_interactive_plan_command_view(view)
            if view.persist_session:
                await self._persist_session()

        async def _resume_task_async(self, arg: str) -> None:
            if self._should_route_resume_task_to_pipeline(arg):
                self._add_system_message(
                    "Pipeline /resume-task is currently available in CLI mode. Use `oc interactive` to resume structured pipeline stages."
                )
                return

            view = build_interactive_resume_task_command_view(
                arg,
                session_metadata=self._session_metadata,
                omicsclaw_dir=str(_OMICSCLAW_DIR),
            )
            self._apply_interactive_plan_command_view(view)
            if view.persist_session:
                await self._persist_session()

        def _submit_programmatic_prompt(
            self,
            prompt: str,
            *,
            display_text: str = "",
        ) -> None:
            shown = (display_text or prompt).strip()
            if shown:
                self._add_user_message(shown)
            self._messages.append({"role": "user", "content": prompt})
            self.run_worker(self._llm_response_async(), exclusive=True)

        async def _do_current_task_async(self, arg: str) -> None:
            snapshot = load_interactive_plan_from_metadata(self._session_metadata)
            if snapshot is None and self._should_route_plan_commands_to_pipeline(""):
                self._add_system_message(
                    "[yellow]/do-current-task targets interactive session plans. Use `/resume-task <stage>` in CLI mode for research pipeline workspaces.[/yellow]"
                )
                return

            view = build_do_current_task_command_view(
                arg,
                session_metadata=self._session_metadata,
                omicsclaw_dir=str(_OMICSCLAW_DIR),
            )
            self._apply_interactive_plan_command_view(view)
            if view.persist_session:
                await self._persist_session()
            if view.success and view.execution_prompt:
                self._submit_programmatic_prompt(
                    view.execution_prompt,
                    display_text=view.suggested_prompt,
                )

        # ------------------------------------------------------------------
        # /sessions worker
        # ------------------------------------------------------------------

        async def _show_sessions_async(self, query: str = "") -> None:
            view = await build_session_list_view(limit=10, query=query)
            self._add_system_message(
                format_session_list_plain(
                    view,
                    hint_text=(
                        "Use /resume <id> or /resume tag:<tag> title:<text> workspace:<path> in TUI."
                    ),
                )
            )

        async def _resume_session_async(self, target: str) -> None:
            query = target.strip()
            if not query:
                await self._show_sessions_async()
                self._add_system_message(
                    "[dim]Use /resume <session-id> or a search query to restore a session.[/dim]"
                )
                return

            view = await build_resume_session_command_view(query)
            if view.success:
                self._apply_session_command_view(view)
                return

            matches = await build_session_list_view(limit=10, query=query)
            if not matches.entries:
                self._apply_session_command_view(view)
                return
            if len(matches.entries) == 1:
                resolved = await build_resume_session_command_view(matches.entries[0].session_id)
                self._apply_session_command_view(resolved)
                return

            self._add_system_message(
                format_session_list_plain(
                    matches,
                    header=f"Sessions matching: {query}",
                    hint_text="Multiple sessions matched. Re-run /resume <session-id> with one of the IDs above.",
                )
            )

        async def _show_installed_extensions_async(self) -> None:
            view = build_installed_extension_list_view(omicsclaw_dir=_OMICSCLAW_DIR)
            if not view.entries:
                self._add_system_message(
                    f"[yellow]{view.empty_text}[/yellow]\n[dim]{view.hint_text}[/dim]"
                )
                return
            self._add_system_message(format_installed_extension_list_plain(view))

        async def _show_installed_skills_async(self) -> None:
            view = build_installed_skill_list_view(omicsclaw_dir=_OMICSCLAW_DIR)
            if not view.entries:
                self._add_system_message(
                    f"[yellow]{view.empty_text}[/yellow]\n[dim]{view.hint_text}[/dim]"
                )
                return
            self._add_system_message(format_installed_skill_list_plain(view))

        async def _refresh_skills_async(self) -> None:
            for status in build_refresh_skills_statuses(omicsclaw_dir=_OMICSCLAW_DIR):
                self._apply_skill_command_status(status)

        async def _refresh_extensions_async(self) -> None:
            for status in build_refresh_extensions_statuses(omicsclaw_dir=_OMICSCLAW_DIR):
                self._apply_skill_command_status(status)

        # ------------------------------------------------------------------
        # /install-skill worker
        # ------------------------------------------------------------------

        async def _install_extension_async(self, src: str) -> None:
            statuses = await asyncio.to_thread(
                install_extension_from_source,
                src,
                omicsclaw_dir=_OMICSCLAW_DIR,
            )
            for status in statuses:
                self._apply_skill_command_status(status)

        async def _install_skill_async(self, src: str) -> None:
            statuses = await asyncio.to_thread(
                install_skill_from_source,
                src,
                omicsclaw_dir=_OMICSCLAW_DIR,
            )
            for status in statuses:
                self._apply_skill_command_status(status)

        # ------------------------------------------------------------------
        # /uninstall-skill worker
        # ------------------------------------------------------------------

        async def _toggle_extension_enabled_async(self, name: str, *, enable: bool) -> None:
            statuses = await asyncio.to_thread(
                set_installed_extension_enabled,
                name,
                enable=enable,
                omicsclaw_dir=_OMICSCLAW_DIR,
            )
            for status in statuses:
                self._apply_skill_command_status(status)

        async def _uninstall_extension_async(self, name: str) -> None:
            statuses = await asyncio.to_thread(
                uninstall_extension,
                name,
                omicsclaw_dir=_OMICSCLAW_DIR,
            )
            for status in statuses:
                self._apply_skill_command_status(status)

        async def _uninstall_skill_async(self, name: str) -> None:
            statuses = await asyncio.to_thread(
                uninstall_extension,
                name,
                omicsclaw_dir=_OMICSCLAW_DIR,
                expected_type="skill-pack",
            )
            for status in statuses:
                self._apply_skill_command_status(status)


        # ------------------------------------------------------------------
        # Keyboard actions
        # ------------------------------------------------------------------

        def action_new_session(self) -> None:
            self._apply_session_command_view(
                build_new_session_command_view(generate_session_id())
            )

        def action_clear_chat(self) -> None:
            self._apply_session_command_view(
                build_clear_conversation_command_view()
            )

        def action_show_sessions(self) -> None:
            self.run_worker(self._show_sessions_async(), exclusive=False)

        def action_show_help(self) -> None:
            self._add_system_message(format_tui_help_text(TUI_SLASH_COMMAND_SPECS))

        def action_toggle_sidebar(self) -> None:
            sidebar = self.query_one("#sidebar", DirectoryTree)
            if sidebar.display:
                sidebar.display = False
                self.query_one("#chat-input", ChatTextArea).focus()
            else:
                sidebar.display = True
                sidebar.focus()

        @on(DirectoryTree.FileSelected, "#sidebar")
        def _on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
            path = str(event.path)
            chat_box = self.query_one("#chat-input", ChatTextArea)
            if hasattr(chat_box, "insert_text"):
                chat_box.insert_text(path)
            elif hasattr(chat_box, "replace"):
                chat_box.replace(path, chat_box.cursor_location, chat_box.cursor_location)
            else:
                chat_box.text += path
            chat_box.focus()


def run_tui(
    workspace_dir: str | None = None,
    session_id: str | None = None,
    model: str = "",
    provider: str = "",
    config: dict | None = None,
    mode: str | None = None,
) -> None:
    """Launch the OmicsClaw Textual TUI application."""
    if not _HAS_TEXTUAL:
        raise ImportError(
            "textual is required for TUI mode.\n"
            "Install with: pip install 'textual>=0.80'"
        )

    app = OmicsClawTUI(
        session_id=session_id,
        workspace_dir=workspace_dir,
        model=model,
        provider=provider,
        config=config or {},
        mode=mode,
    )
    app.run()
