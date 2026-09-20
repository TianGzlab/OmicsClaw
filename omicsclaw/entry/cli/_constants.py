"""Shared constants for OmicsClaw interactive CLI/TUI.

**Ported** from ``omicsclaw/surfaces/cli/_constants.py`` (85 lines) with no
change beyond line lengths — the data is identical byte for byte once the
wrapping is undone, and the wrapping exists because plan 0031 §9-3 holds
every new file to 88 columns while the original ran to 178.

:data:`SLASH_COMMANDS` is carried over **whole**, including the commands
this surface does not implement. Plan 0031 §5.1 blocks the skill runner,
the research pipeline, plan mode and the memory commands from this step —
each belongs to a step of its own — and deleting their rows here would
mean rewriting the table when those steps land. What the REPL actually
offers is the subset named by
:data:`~omicsclaw.entry.cli._slash_command_support.REPL_SLASH_COMMAND_SPECS`;
this list is the catalogue, not the menu.

:data:`ADDED_SLASH_COMMANDS` is the second half of that catalogue, and it
is a second list rather than more rows in the first because
``tests/entry/test_cli_port_fidelity.py`` compares :data:`SLASH_COMMANDS`
against the original element for element. A command this build gained
*after* the port therefore cannot go in there without making that
comparison meaningless — the test would have to be relaxed to accept
whatever the file now says, which is the opposite of what it is for. The
two lists are concatenated by
:mod:`~omicsclaw.entry.cli._slash_command_support`, so a reader of the
menu sees one catalogue and a reader of the port sees the port.
"""

from __future__ import annotations

WELCOME_SLOGANS = [
    "Ready to decode your omics data? What shall we analyze today?",
    "Multi-omics AI is ready. Drop your question or type /skills.",
    "Spatial, single-cell, genomics, proteomics, metabolomics — "
    "all at your command.",
    "Science doesn't sleep. Neither does OmicsClaw.",
    "From raw data to biological insights — let's go.",
    "95 skills, one intelligent interface.",
    "Type your question, or /run <skill> to execute directly.",
    "What omics mystery shall we solve today?",
    "Your multi-omics co-pilot is ready for takeoff.",
    "Data in. Discoveries out. Let's begin.",
]

# OmicsClaw ASCII art logo (compact version).
#
# Each of the six rows is one string written as three adjacent literals.
# The rows are 76 characters wide and box-drawing characters are three
# bytes each in UTF-8, so a row on one source line is ~200 bytes and plan
# 0031 §9-3's ``awk 'length > 88'`` counts bytes. Splitting is the only
# change: ``tests/entry/test_cli_port_fidelity.py`` asserts these six
# strings are byte-identical to the ones in
# ``omicsclaw/surfaces/cli/_constants.py``, so a mis-typed box character
# is a red test rather than a crooked logo somebody notices later.
LOGO_LINES = (
    r"  ██████╗ ███╗   ███╗██╗ "
    r"██████╗███████╗ ██████╗██"
    r"╗      █████╗ ██╗    ██╗",
    r" ██╔═══██╗████╗ ████║██║█"
    r"█╔════╝██╔════╝██╔════╝██"
    r"║     ██╔══██╗██║    ██║",
    r" ██║   ██║██╔████╔██║██║█"
    r"█║     ███████╗██║     ██"
    r"║     ███████║██║ █╗ ██║",
    r" ██║   ██║██║╚██╔╝██║██║█"
    r"█║     ╚════██║██║     ██"
    r"║     ██╔══██║██║███╗██║",
    r" ╚██████╔╝██║ ╚═╝ ██║██║╚"
    r"██████╗███████║╚██████╗██"
    r"█████╗██║  ██║╚███╔███╔╝",
    r"  ╚═════╝ ╚═╝     ╚═╝╚═╝ "
    r"╚═════╝╚══════╝ ╚═════╝╚═"
    r"═════╝╚═╝  ╚═╝ ╚══╝╚══╝ ",
)

# Minimalist Omics/DNA Sci-Fi Gradient (Bright Cyan -> Royal Blue)
LOGO_GRADIENT = [
    "#00ffff",  # Bright Cyan
    "#00dfff",  # Cyan Blue
    "#00bfff",  # Deep Sky Blue
    "#009fff",  # Dodger Blue
    "#007fff",  # Azure
    "#005fff",  # Royal Blue
]

AGENT_NAME = "OmicsClaw"
DB_NAME = "sessions.db"
MCP_CONFIG_NAME = "mcp.yaml"
RUN_COMMAND_USAGE = (
    "/run <skill> [--demo] [--input <path>] [--output <dir>] [--method <name>]"
)

# Slash commands shown in help and autocompleter
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/run", f"Run a skill: {RUN_COMMAND_USAGE}"),
    ("/skills", "List all OmicsClaw skills (optional: /skills <domain>)"),
    (
        "/interpret",
        "Interpret a verified consensus run: /interpret <typed_run_dir> "
        "[--tissue brain|immune|kidney|liver] [--no-llm] [--output <dir>]",
    ),
    (
        "/research",
        'Research pipeline: /research [pdf] --idea "..." '
        "[--plan-only | --resume --output <dir>]",
    ),
    (
        "/resume-task",
        "Focus an approved plan task or resume a pipeline stage: "
        "/resume-task <task-id|stage>",
    ),
    (
        "/do-current-task",
        "Execute the active approved interactive plan task now: "
        "/do-current-task [task-id|index]",
    ),
    (
        "/tasks",
        "Show structured tasks for the current session plan or pipeline: "
        "/tasks [workspace]",
    ),
    (
        "/plan",
        "Show or create a structured session plan; with a pipeline "
        "workspace, preview plan.md",
    ),
    ("/approve-plan", "Approve the current session plan or pipeline plan.md"),
    ("/new", "Start a new session"),
    ("/current", "Show current session info"),
    ("/sessions", "List recent conversation sessions"),
    (
        "/resume",
        "Resume a previous session: /resume [id|tag:<tag>|title:<text>|"
        "workspace:<path>|domain:<name>]",
    ),
    ("/session-title", "Set or show the current session title: /session-title <title>"),
    ("/session-tag", "Set or show the current session tag: /session-tag <tag>"),
    ("/doctor", "Run environment and runtime diagnostics"),
    ("/context", "Inspect current prompt-context layers and budget"),
    ("/memory", "Manage scoped memory: /memory [list | add | prune | scope]"),
    ("/usage", "Show current token and cost usage."),
    ("/clear", "Clear current conversation history"),
    ("/export", "Export current session to a Markdown report file"),
    ("/delete", "Delete a saved session: /delete <id>"),
    (
        "/install-extension",
        "Add an extension pack from a local path or GitHub: "
        "/install-extension <src>",
    ),
    ("/installed-extensions", "List installed extension packs and audit records"),
    ("/refresh-extensions", "Refresh extension inventory and skill registry state"),
    ("/disable-extension", "Disable an installed extension: /disable-extension <name>"),
    ("/enable-extension", "Enable a disabled extension: /enable-extension <name>"),
    (
        "/uninstall-extension",
        "Remove an installed extension: /uninstall-extension <name>",
    ),
    ("/install-skill", "Add a skill from a local path or GitHub: /install-skill <src>"),
    ("/installed-skills", "List installed user skill packs and audit records"),
    ("/refresh-skills", "Refresh the user skill registry after local changes"),
    ("/uninstall-skill", "Remove an installed skill: /uninstall-skill <name>"),
    ("/style", "Show or switch output style: /style [list | set <name>]"),
    ("/tips", "Toggle inline knowledge tips: /tips [on|off|level basic|expert]"),
    ("/mcp", "Manage MCP servers (/mcp list | add | remove)"),
    ("/config", "View or set config (/config list | /config set key value)"),
    ("/help", "Show this help"),
    ("/exit", "Quit OmicsClaw (aliases: /quit, /q)"),
]

ADDED_SLASH_COMMANDS: list[tuple[str, str]] = [
    (
        "/compact",
        "Summarize this conversation now, keeping the recent messages",
    ),
]
"""Commands this build has that the ported catalogue never listed.

See this module's docstring for why they are not rows of
:data:`SLASH_COMMANDS`.
"""
