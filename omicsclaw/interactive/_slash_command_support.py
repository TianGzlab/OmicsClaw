"""Shared slash-command metadata and parsing for interactive surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ._constants import SLASH_COMMANDS


@dataclass(frozen=True, slots=True)
class SlashCommandSpec:
    name: str
    description: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SlashCommandMatch:
    name: str
    arg: str
    token: str
    raw: str


@dataclass(frozen=True, slots=True)
class KeyboardShortcut:
    key: str
    description: str


_BASE_SLASH_COMMAND_SPECS = tuple(
    SlashCommandSpec(
        name=name,
        description=description,
        aliases=("/quit", "/q") if name == "/exit" else (),
    )
    for name, description in SLASH_COMMANDS
)

CLI_SLASH_COMMAND_SPECS: tuple[SlashCommandSpec, ...] = _BASE_SLASH_COMMAND_SPECS

TUI_SLASH_COMMAND_SPECS: tuple[SlashCommandSpec, ...] = tuple(
    spec
    for spec in _BASE_SLASH_COMMAND_SPECS
    if spec.name
    in {
        "/run",
        "/skills",
        "/tasks",
        "/plan",
        "/approve-plan",
        "/resume-task",
        "/do-current-task",
        "/new",
        "/current",
        "/sessions",
        "/resume",
        "/session-title",
        "/session-tag",
        "/doctor",
        "/context",
        "/memory",
        "/usage",
        "/clear",
        "/export",
        "/install-extension",
        "/installed-extensions",
        "/refresh-extensions",
        "/disable-extension",
        "/enable-extension",
        "/uninstall-extension",
        "/install-skill",
        "/installed-skills",
        "/refresh-skills",
        "/uninstall-skill",
        "/style",
        "/help",
        "/exit",
    }
)

TUI_KEYBOARD_SHORTCUTS: tuple[KeyboardShortcut, ...] = (
    KeyboardShortcut("Ctrl+N", "New session"),
    KeyboardShortcut("Ctrl+L", "Clear chat"),
    KeyboardShortcut("Ctrl+B", "Toggle sidebar"),
    KeyboardShortcut("Ctrl+S", "List sessions"),
    KeyboardShortcut("Ctrl+H", "Show help"),
    KeyboardShortcut("Ctrl+Q", "Quit"),
)


def list_slash_command_names(
    specs: Iterable[SlashCommandSpec],
    *,
    include_aliases: bool = False,
) -> list[str]:
    names: list[str] = []
    for spec in specs:
        names.append(spec.name)
        if include_aliases:
            names.extend(spec.aliases)
    return names


def slash_command_help_rows(
    specs: Iterable[SlashCommandSpec],
) -> list[tuple[str, str]]:
    return [(spec.name, spec.description) for spec in specs]


def complete_slash_command_rows(
    prefix: str,
    specs: Iterable[SlashCommandSpec],
) -> list[tuple[str, str]]:
    lowered = prefix.lower()
    return [
        (name, description)
        for name, description in slash_command_help_rows(specs)
        if name.startswith(lowered)
    ]


def complete_run_skill_names(
    text: str,
    skill_names: Sequence[str],
) -> list[str]:
    if not text.startswith("/run "):
        return []
    skill_prefix = text[len("/run "):].lstrip()
    if " " in skill_prefix:
        return []
    return [name for name in skill_names if name.startswith(skill_prefix)]


def format_slash_command_help_text(
    specs: Iterable[SlashCommandSpec],
    *,
    header: str = "Commands:",
    footer_lines: Iterable[str] = (),
) -> str:
    lines = [header]
    for name, description in slash_command_help_rows(specs):
        lines.append(f"  {name}  — {description}")
    lines.extend(footer_lines)
    return "\n".join(lines)


def format_tui_help_text(
    specs: Iterable[SlashCommandSpec],
    *,
    shortcuts: Sequence[KeyboardShortcut] = TUI_KEYBOARD_SHORTCUTS,
) -> str:
    lines = ["OmicsClaw TUI — Keyboard shortcuts:"]
    for shortcut in shortcuts:
        lines.append(f"  {shortcut.key} — {shortcut.description}")
    lines.append("")
    lines.append("Slash commands:")
    for name, description in slash_command_help_rows(specs):
        lines.append(f"  {name}  — {description}")
    return "\n".join(lines)


def parse_slash_command(
    text: str,
    specs: Iterable[SlashCommandSpec],
) -> SlashCommandMatch | None:
    raw = text.strip()
    if not raw.startswith("/"):
        return None

    token, _, remainder = raw.partition(" ")
    lookup: dict[str, str] = {}
    for spec in specs:
        lookup[spec.name] = spec.name
        for alias in spec.aliases:
            lookup[alias] = spec.name

    canonical_name = lookup.get(token.lower())
    if canonical_name is None:
        return None

    return SlashCommandMatch(
        name=canonical_name,
        arg=remainder.strip(),
        token=token.lower(),
        raw=raw,
    )
