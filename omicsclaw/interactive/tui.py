"""OmicsClaw Textual TUI — full-screen terminal user interface.

Requires: textual>=0.80
Install:  pip install textual
"""

from __future__ import annotations

import logging
import os
import random
import shlex
import sys
import time as _time
from pathlib import Path

logger = logging.getLogger(__name__)
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
    WELCOME_SLOGANS,
)
from ._session import (
    generate_session_id,
    list_sessions,
    save_session,
)


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

            from ._constants import SLASH_COMMANDS
            commands = [cmd for cmd, _ in SLASH_COMMANDS]
            matches = []

            if " " not in prefix:
                matches = [c + " " for c in commands if c.startswith(prefix)]
            elif prefix.startswith("/run "):
                skill_prefix = prefix[5:]
                try:
                    from omicsclaw.core.registry import registry
                    if not getattr(registry, "_loaded", False):
                        registry.load_all()
                    matches = ["/run " + s + " " for s in registry.skills.keys() if s.startswith(skill_prefix)]
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
            self._session_id = session_id or generate_session_id()
            self._workspace = workspace_dir or str(_OMICSCLAW_DIR)
            self._model = model
            self._provider = provider
            self._config = config or {}
            self._mode = mode
            self._messages: list[dict] = []
            self._thinking = False
            # Session-level usage statistics
            self._session_stats: dict[str, int] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "api_calls": 0,
            }
            self._session_start = _time.time()

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
                mode_str = f"[{self._mode}] · " if self._mode else ""
                yield Label(
                    f"{self._model or 'AI'} · {mode_str}session {self._session_id}",
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
            # Load LLM in background
            self.run_worker(self._init_llm_async(), exclusive=True)

        async def _init_llm_async(self) -> None:
            try:
                sys.path.insert(0, str(_OMICSCLAW_DIR))
                from dotenv import load_dotenv
                import bot.core as core
                load_dotenv(_OMICSCLAW_DIR / ".env", override=False)
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
                # Update header
                try:
                    mode_str = f"[{self._mode}] · " if getattr(self, "_mode", None) else ""
                    self.query_one("#header-info", Label).update(
                        f"{self._model} · {mode_str}session {self._session_id}"
                    )
                except NoMatches:
                    pass
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
            low = text.lower()
            if low in ("/exit", "/quit", "/q"):
                self.exit()
                return

            elif low == "/help":
                self._add_system_message(
                    "Commands:\n"
                    "  /skills \\[domain]  — List skills\n"
                    "  /run <skill> [--demo] [--input <path>]  — Run skill\n"
                    "  /install-skill <src>  — Add a skill from path or GitHub\n"
                    "  /uninstall-skill <name>  — Remove a user-installed skill\n"
                    "  /sessions  — List sessions\n"
                    "  /new  — New session\n"
                    "  /clear  — Clear chat\n"
                    "  /export  — Export session to Markdown\n"
                    "  /exit  — Quit (aliases: /quit, /q)\n"
                    "  Ctrl+B — Sidebar | Ctrl+H — Help | Ctrl+N — New | Ctrl+Q — Quit"
                )
                return

            elif low.startswith("/skills"):
                arg = text[len("/skills"):].strip()
                self.run_worker(self._list_skills_async(arg), exclusive=False)
                return

            elif low.startswith("/run ") or low == "/run":
                arg = text[len("/run"):].strip()
                self._add_user_message(text)
                self.run_worker(self._run_skill_async(arg), exclusive=False)
                return

            elif low == "/new":
                self._session_id = generate_session_id()
                self._messages = []
                # Reset session usage stats
                for k in ("prompt_tokens", "completion_tokens", "total_tokens", "api_calls",
                          "_last_prompt", "_last_completion"):
                    self._session_stats[k] = 0
                self._session_start = _time.time()
                # Reset core conversation history
                try:
                    import bot.core as core
                    core.conversations.pop("__tui__", None)
                    core.reset_usage()
                except Exception:
                    pass
                self._add_system_message(f"New session: {self._session_id}")
                # Reset usage bar
                try:
                    self.query_one("#usage-label", Label).update(
                        "Tokens: 0 in · 0 out  │  Cost: $0.000000  │  Calls: 0"
                    )
                except Exception:
                    pass
                return

            elif low == "/clear":
                self.action_clear_chat()
                return

            elif low == "/export":
                from ._session import export_conversation_to_markdown
                try:
                    export_dir = Path(self._workspace) / "exports"
                    export_path = export_dir / f"omicsclaw_session_{self._session_id}.md"
                    export_conversation_to_markdown(self._session_id, self._messages, export_path)
                    self._add_system_message(f"✓ Session exported to: {export_path}")
                except Exception as e:
                    self._add_system_message(f"✗ Export failed: {e}")
                return

            elif low == "/sessions":
                self.run_worker(self._show_sessions_async(), exclusive=False)
                return

            elif low == "/usage":
                self._show_usage()
                return

            elif low.startswith("/install-skill"):
                arg = text[len("/install-skill"):].strip()
                self._add_user_message(text)
                self.run_worker(self._install_skill_async(arg), exclusive=False)
                return

            elif low.startswith("/uninstall-skill"):
                arg = text[len("/uninstall-skill"):].strip()
                self._add_user_message(text)
                self.run_worker(self._uninstall_skill_async(arg), exclusive=False)
                return

            # Regular message — send to LLM
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
                # Seed history with everything *except* the last user message
                # (llm_tool_loop will append that message itself).
                seed = list(self._messages[:-1]) if len(self._messages) > 1 else []
                core.conversations[_USER] = seed
                core._conversation_access[_USER] = _time.time()

                last_user_msg = (
                    self._messages[-1].get("content", "") if self._messages else ""
                )
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
                final_text = await core.llm_tool_loop(
                    _USER,
                    last_user_msg,
                    user_id="tui_user",
                    platform="tui",
                    on_tool_call=tui_on_tool_call,
                    on_tool_result=tui_on_tool_result,
                )
                elapsed = _time.time() - t0

                # Collect usage snapshot from core
                try:
                    snap = core.get_usage_snapshot()
                    # Accumulate into session stats
                    # (snap is cumulative from core; diff from last known totals)
                    new_in  = snap["prompt_tokens"]     - self._session_stats.get("_last_prompt", 0)
                    new_out = snap["completion_tokens"] - self._session_stats.get("_last_completion", 0)
                    self._session_stats["prompt_tokens"]     += max(0, new_in)
                    self._session_stats["completion_tokens"] += max(0, new_out)
                    self._session_stats["total_tokens"]      = (
                        self._session_stats["prompt_tokens"] + self._session_stats["completion_tokens"]
                    )
                    self._session_stats["api_calls"]         = snap["api_calls"]
                    self._session_stats["_last_prompt"]      = snap["prompt_tokens"]
                    self._session_stats["_last_completion"]  = snap["completion_tokens"]
                    # Cost for this turn
                    turn_cost = (
                        max(0, new_in)  / 1_000_000 * snap.get("input_price_per_1m",  0) +
                        max(0, new_out) / 1_000_000 * snap.get("output_price_per_1m", 0)
                    )
                    usage_line = (
                        f"[dim]↪ {new_in:,} in · {new_out:,} out · "
                        f"${turn_cost:.6f} · {elapsed:.1f}s[/dim]"
                    )
                    self._update_usage_bar(snap)
                except Exception:
                    usage_line = f"[dim]↪ {elapsed:.1f}s[/dim]"

                # Sync the updated conversation history back to our messages list
                updated_msgs = core._sanitize_tool_history(
                    list(core.conversations.get(_USER, [])),
                    warn=False,
                )
                core.conversations[_USER] = list(updated_msgs)
                self._messages.clear()
                self._messages.extend(updated_msgs)

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

                await save_session(
                    self._session_id,
                    self._messages,
                    model=self._model,
                    workspace=self._workspace,
                )
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
            try:
                sys.path.insert(0, str(_OMICSCLAW_DIR))
                import bot.core as core
                snap = core.get_usage_snapshot()
            except Exception:
                snap = {}

            sess_in  = self._session_stats.get("prompt_tokens", 0)
            sess_out = self._session_stats.get("completion_tokens", 0)
            calls    = self._session_stats.get("api_calls", 0)
            inp_p    = snap.get("input_price_per_1m", 0.0)
            out_p    = snap.get("output_price_per_1m", 0.0)
            cost     = sess_in / 1_000_000 * inp_p + sess_out / 1_000_000 * out_p
            elapsed  = _time.time() - self._session_start
            h, m     = int(elapsed // 3600), int((elapsed % 3600) // 60)

            lines = [
                "┏━ Usage Report ━┓",
                f"  • Model:       {snap.get('model', '?')} ({snap.get('provider', '?')})",
                f"  • Input tokens:  {sess_in:,}",
                f"  • Output tokens: {sess_out:,}",
                f"  • Total tokens:  {sess_in + sess_out:,}",
                f"  • API calls:     {calls}",
                f"  • Est. cost:     ${cost:.6f} USD",
                f"  • Price:         ${inp_p:.3f} / ${out_p:.3f} per 1M tokens (in/out)",
                f"  • Session time:  {h}h {m}m",
                "┗━━━━━━━━━━━━━━┛",
            ]
            self._add_system_message("\n".join(lines))


        # ------------------------------------------------------------------
        # /skills worker — actually list skills in TUI chat area
        # ------------------------------------------------------------------

        async def _list_skills_async(self, domain_filter: str) -> None:
            """List registered skills, optionally filtered by domain."""
            try:
                sys.path.insert(0, str(_OMICSCLAW_DIR))
                import bot.core as core

                # format_skills_table is available in core and already
                # enumerates all domains/skills from the registry.
                table_text = core.format_skills_table(plain=True)

                # Filter by domain keyword if provided
                if domain_filter:
                    lines = table_text.splitlines()
                    filtered: list[str] = []
                    include = False
                    for line in lines:
                        # Section headers look like "[Domain] (N skills, ...)"
                        if line.startswith("["):
                            include = domain_filter.lower() in line.lower()
                        if include or not line.startswith("["):
                            # Always include non-section lines belonging to a
                            # matched section, stop at next unmatched section
                            if line.startswith("[") and not include:
                                continue
                            filtered.append(line)
                    table_text = "\n".join(filtered) if filtered else f"No skills found for domain: {domain_filter}"

                self._add_system_message(table_text)
            except Exception as e:
                logger.exception("list skills error")
                self._add_system_message(f"⚠ Error listing skills: {e}")

        # ------------------------------------------------------------------
        # /run worker
        # ------------------------------------------------------------------

        async def _run_skill_async(self, arg: str) -> None:
            tokens = shlex.split(arg) if arg else []
            if not tokens:
                self._add_system_message("Usage: /run <skill> [--demo] [--input <path>] [--output <dir>]")
                return
            skill = tokens[0]
            demo = "--demo" in tokens
            input_path = None
            output_dir = None
            i = 1
            while i < len(tokens):
                if tokens[i] == "--input" and i + 1 < len(tokens):
                    input_path = tokens[i + 1]
                    i += 2
                elif tokens[i] == "--output" and i + 1 < len(tokens):
                    output_dir = tokens[i + 1]
                    i += 2
                else:
                    i += 1

            self._add_system_message(f"⚙ Running skill: {skill}...")
            try:
                _oc = _load_omicsclaw_script()
                result = _oc.run_skill(
                    skill,
                    input_path=input_path,
                    output_dir=output_dir,
                    demo=demo,
                )
                if result.get("success"):
                    method_line = f"\n  Method: {result.get('method')}" if result.get("method") else ""
                    guide_line = f"\n  Guide: {result.get('readme_path')}" if result.get("readme_path") else ""
                    notebook_line = f"\n  Notebook: {result.get('notebook_path')}" if result.get("notebook_path") else ""
                    self._add_system_message(
                        f"✓ Skill '{skill}' done in {result.get('duration_seconds', 0):.1f}s\n"
                        f"  Output: {result.get('output_dir', '?')}"
                        f"{method_line}"
                        f"{guide_line}"
                        f"{notebook_line}"
                    )
                    # Inject result into conversation for LLM context
                    self._messages.append({"role": "user", "content": f"[Ran skill] {arg}"})
                    self._messages.append({
                        "role": "assistant",
                        "content": f"Skill '{skill}' completed. Output: {result.get('output_dir', '?')}",
                    })
                    await save_session(
                        self._session_id,
                        self._messages,
                        model=self._model,
                        workspace=self._workspace,
                    )
                else:
                    err = result.get("stderr", "unknown error")
                    self._add_system_message(f"✗ Skill '{skill}' failed: {err[:300]}")
            except Exception as e:
                logger.exception("run skill error")
                self._add_system_message(f"⚠ Error running skill '{skill}': {e}")

        # ------------------------------------------------------------------
        # /sessions worker
        # ------------------------------------------------------------------

        async def _show_sessions_async(self) -> None:
            sessions = await list_sessions(limit=10)
            if not sessions:
                self._add_system_message("No saved sessions.")
                return
            lines = ["Recent sessions (newest first):"]
            for s in sessions:
                preview = s.get("preview", "") or ""
                lines.append(
                    f"  [{s['session_id']}]  {preview[:40]}  "
                    f"({s.get('message_count', 0)} msgs)"
                )
            lines.append("\nUse /resume <id> in CLI mode to resume a session.")
            self._add_system_message("\n".join(lines))

        # ------------------------------------------------------------------
        # /install-skill worker
        # ------------------------------------------------------------------

        async def _install_skill_async(self, src: str) -> None:
            """Install a skill from a local path or GitHub URL."""
            import shutil
            import asyncio

            if not src:
                self._add_system_message(
                    "Usage: /install-skill <local-path | github-url>\n"
                    "Examples:\n"
                    "  /install-skill /path/to/my-skill\n"
                    "  /install-skill https://github.com/user/my-skill-repo"
                )
                return

            skills_dir = _OMICSCLAW_DIR / "skills"
            user_skills_dir = skills_dir / "user"
            user_skills_dir.mkdir(parents=True, exist_ok=True)

            is_github = src.startswith(("https://github.com", "http://github.com", "git@github.com"))

            if is_github:
                url_clean = src.rstrip("/")
                skill_name = url_clean.split("/")[-1]
                if skill_name.endswith(".git"):
                    skill_name = skill_name[:-4]
                dest = user_skills_dir / skill_name
                if dest.exists():
                    self._add_system_message(
                        f"Skill '{skill_name}' already exists.\nRun /uninstall-skill {skill_name} first."
                    )
                    return
                self._add_system_message(f"Cloning '{skill_name}' from GitHub...")
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "git", "clone", "--depth=1", src, str(dest),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                    if proc.returncode != 0:
                        self._add_system_message(
                            f"✗ git clone failed:\n{stderr.decode()[:400]}"
                        )
                        return
                    self._add_system_message(f"✓ Cloned to {dest}")
                except FileNotFoundError:
                    self._add_system_message("✗ git is not installed.")
                    return
                except asyncio.TimeoutError:
                    self._add_system_message("✗ Clone timed out (120 s).")
                    return
            else:
                src_path = Path(src).expanduser().resolve()
                if not src_path.exists() or not src_path.is_dir():
                    self._add_system_message(f"✗ Path not found or not a directory: {src_path}")
                    return
                skill_name = src_path.name
                dest = user_skills_dir / skill_name
                if dest.exists():
                    self._add_system_message(
                        f"Skill '{skill_name}' already exists.\nRun /uninstall-skill {skill_name} first."
                    )
                    return
                try:
                    shutil.copytree(src_path, dest)
                    self._add_system_message(f"✓ Copied to {dest}")
                except Exception as e:
                    self._add_system_message(f"✗ Copy failed: {e}")
                    return

            # Reload registry
            try:
                from omicsclaw.core.registry import registry
                registry._loaded = False
                registry.load_all()
                self._add_system_message(
                    f"✓ Skill '{skill_name}' installed and registered.\n"
                    f"Use /skills to list all available skills."
                )
            except Exception as e:
                self._add_system_message(f"⚠ Registry refresh failed: {e}")

        # ------------------------------------------------------------------
        # /uninstall-skill worker
        # ------------------------------------------------------------------

        async def _uninstall_skill_async(self, name: str) -> None:
            """Remove a user-installed skill (skills/user/<name>)."""
            import shutil

            if not name:
                self._add_system_message("Usage: /uninstall-skill <skill-name>")
                return

            skills_dir = _OMICSCLAW_DIR / "skills"
            user_skills_dir = skills_dir / "user"
            candidate = user_skills_dir / name

            if not candidate.exists():
                # Check if it's a built-in skill
                found_builtin = any(
                    (d / name).exists()
                    for d in skills_dir.iterdir()
                    if d.is_dir() and not d.name.startswith((".", "__"))
                )
                if found_builtin:
                    self._add_system_message(
                        f"'{name}' is a built-in skill and cannot be removed.\n"
                        "Built-in skills are part of OmicsClaw core."
                    )
                else:
                    installed = (
                        [p.name for p in user_skills_dir.iterdir() if p.is_dir()]
                        if user_skills_dir.exists() else []
                    )
                    msg = f"User-installed skill '{name}' not found."
                    if installed:
                        msg += f"\nInstalled: {', '.join(installed)}"
                    self._add_system_message(msg)
                return

            try:
                shutil.rmtree(candidate)
                # Reload registry
                from omicsclaw.core.registry import registry
                registry.skills.pop(name, None)
                registry._loaded = False
                registry.load_all()
                self._add_system_message(f"✓ Skill '{name}' removed and registry refreshed.")
            except Exception as e:
                logger.exception("uninstall skill error")
                self._add_system_message(f"✗ Failed to remove skill: {e}")


        # ------------------------------------------------------------------
        # Keyboard actions
        # ------------------------------------------------------------------

        def action_new_session(self) -> None:
            self._session_id = generate_session_id()
            self._messages = []
            try:
                import bot.core as core
                core.conversations.pop("__tui__", None)
            except Exception:
                pass
            self._add_system_message(f"New session: {self._session_id}")

        def action_clear_chat(self) -> None:
            self._messages = []
            try:
                import bot.core as core
                core.conversations.pop("__tui__", None)
            except Exception:
                pass
            chat = self.query_one("#chat-area", ScrollableContainer)
            # Remove children one by one (remove() is sync in Textual)
            for w in list(chat.children):
                w.remove()
            self._add_system_message("Chat cleared.")

        def action_show_sessions(self) -> None:
            self.run_worker(self._show_sessions_async(), exclusive=False)

        def action_show_help(self) -> None:
            self._add_system_message(
                "OmicsClaw TUI — Keyboard shortcuts:\n"
                "  Ctrl+N — New session\n"
                "  Ctrl+L — Clear chat\n"
                "  Ctrl+B — Toggle lateral sidebar (File Browser)\n"
                "  Ctrl+S — List sessions\n"
                "  Ctrl+H — Show help\n"
                "  Ctrl+Q — Quit\n\n"
                "Slash commands:\n"
                "  /help /skills \\[domain] /run <skill> [--demo]\n"
                "  /install-skill <path|url>  /uninstall-skill <name>\n"
                "  /sessions /new /clear /export /exit (aliases: /quit, /q)"
            )

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
