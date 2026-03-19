"""Shared constants for OmicsClaw interactive CLI/TUI."""

from __future__ import annotations

WELCOME_SLOGANS = [
    "Ready to decode your omics data? What shall we analyze today?",
    "Multi-omics AI is ready. Drop your question or type /skills.",
    "Spatial, single-cell, genomics, proteomics, metabolomics — all at your command.",
    "Science doesn't sleep. Neither does OmicsClaw.",
    "From raw data to biological insights — let's go.",
    "50+ analysis skills, one intelligent interface.",
    "Type your question, or /run <skill> to execute directly.",
    "What omics mystery shall we solve today?",
    "Your multi-omics co-pilot is ready for takeoff.",
    "Data in. Discoveries out. Let's begin.",
]

# OmicsClaw ASCII art logo (compact version)
LOGO_LINES = (
    r"  ██████╗ ███╗   ███╗██╗ ██████╗███████╗ ██████╗██╗      █████╗ ██╗    ██╗",
    r" ██╔═══██╗████╗ ████║██║██╔════╝██╔════╝██╔════╝██║     ██╔══██╗██║    ██║",
    r" ██║   ██║██╔████╔██║██║██║     ███████╗██║     ██║     ███████║██║ █╗ ██║",
    r" ██║   ██║██║╚██╔╝██║██║██║     ╚════██║██║     ██║     ██╔══██║██║███╗██║",
    r" ╚██████╔╝██║ ╚═╝ ██║██║╚██████╗███████║╚██████╗███████╗██║  ██║╚███╔███╔╝",
    r"  ╚═════╝ ╚═╝     ╚═╝╚═╝ ╚═════╝╚══════╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ",
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

# Slash commands shown in help and autocompleter
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/skills",          "List all OmicsClaw skills (optional: /skills <domain>)"),
    ("/run",             "Run a skill: /run <skill> [--demo] [--input <path>]"),
    ("/install-skill",   "Add a skill from a local path or GitHub: /install-skill <src>"),
    ("/uninstall-skill", "Remove an installed skill: /uninstall-skill <name>"),
    ("/sessions",        "List recent conversation sessions"),
    ("/resume",          "Resume a previous session (interactive picker if no ID)"),
    ("/delete",          "Delete a saved session: /delete <id>"),
    ("/current",         "Show current session info"),
    ("/new",             "Start a new session"),
    ("/clear",           "Clear current conversation history"),
    ("/mcp",             "Manage MCP servers (/mcp list | add | remove)"),
    ("/config",          "View or set config (/config list | /config set key value)"),
    ("/help",            "Show this help"),
    ("/exit",            "Quit OmicsClaw"),
]
