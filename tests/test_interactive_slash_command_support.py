from omicsclaw.interactive._slash_command_support import (
    CLI_SLASH_COMMAND_SPECS,
    TUI_SLASH_COMMAND_SPECS,
    complete_run_skill_names,
    complete_slash_command_rows,
    format_slash_command_help_text,
    format_tui_help_text,
    list_slash_command_names,
    parse_slash_command,
    slash_command_help_rows,
)


def test_parse_slash_command_extracts_command_and_argument():
    command = parse_slash_command(
        "/plan /tmp/workspace",
        CLI_SLASH_COMMAND_SPECS,
    )

    assert command is not None
    assert command.name == "/plan"
    assert command.arg == "/tmp/workspace"


def test_parse_slash_command_normalizes_exit_aliases():
    command = parse_slash_command(
        "/q",
        CLI_SLASH_COMMAND_SPECS,
    )

    assert command is not None
    assert command.name == "/exit"
    assert command.token == "/q"


def test_parse_slash_command_requires_exact_command_token():
    assert parse_slash_command("/planner", CLI_SLASH_COMMAND_SPECS) is None
    assert parse_slash_command("/skillsx spatial", CLI_SLASH_COMMAND_SPECS) is None


def test_tui_slash_command_specs_include_phase_g_commands_but_not_research():
    names = list_slash_command_names(TUI_SLASH_COMMAND_SPECS)

    assert "/doctor" in names
    assert "/context" in names
    assert "/usage" in names
    assert "/do-current-task" in names
    assert "/current" in names
    assert "/resume" in names
    assert "/install-extension" in names
    assert "/installed-extensions" in names
    assert "/disable-extension" in names
    assert "/enable-extension" in names
    assert "/installed-skills" in names
    assert "/refresh-skills" in names
    assert "/style" in names
    assert "/memory" in names
    assert "/session-title" in names
    assert "/session-tag" in names
    assert "/research" not in names


def test_slash_command_help_rows_and_text_render_subset():
    rows = slash_command_help_rows(TUI_SLASH_COMMAND_SPECS)
    text = format_slash_command_help_text(
        TUI_SLASH_COMMAND_SPECS,
        footer_lines=("  Footer",),
    )

    assert (
        "/run",
        "Run a skill: /run <skill> [--demo] [--input <path>] [--output <dir>] [--method <name>]",
    ) in rows
    assert any(name == "/do-current-task" for name, _description in rows)
    assert any(name == "/resume" for name, _description in rows)
    assert any(name == "/style" for name, _description in rows)
    assert any(name == "/doctor" for name, _description in rows)
    assert any(name == "/context" for name, _description in rows)
    assert any(name == "/memory" for name, _description in rows)
    assert "/doctor  — Run environment and runtime diagnostics" in text
    assert "/context  — Inspect current prompt-context layers and budget" in text
    assert "/usage  — Show current token and cost usage." in text
    assert "  Footer" in text


def test_complete_slash_command_rows_filters_by_prefix():
    rows = complete_slash_command_rows("/pl", CLI_SLASH_COMMAND_SPECS)

    assert rows == [
        (
            "/plan",
            "Show or create a structured session plan; with a pipeline workspace, preview plan.md",
        )
    ]


def test_complete_run_skill_names_matches_only_run_prefix():
    matches = complete_run_skill_names(
        "/run spatial-",
        ["spatial-preprocess", "spatial-domains", "sc-qc"],
    )

    assert matches == ["spatial-preprocess", "spatial-domains"]
    assert complete_run_skill_names("/skills spatial", ["spatial-preprocess"]) == []


def test_format_tui_help_text_includes_shortcuts_and_slash_commands():
    text = format_tui_help_text(TUI_SLASH_COMMAND_SPECS)

    assert "OmicsClaw TUI — Keyboard shortcuts:" in text
    assert "Ctrl+H — Show help" in text
    assert "Slash commands:" in text
    assert "/doctor  — Run environment and runtime diagnostics" in text
    assert "/context  — Inspect current prompt-context layers and budget" in text
    assert "/usage  — Show current token and cost usage." in text
