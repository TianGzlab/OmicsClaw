"""OmicsClaw interactive CLI/TUI package.

Entry points:
    omicsclaw interactive   — Rich CLI with prompt_toolkit REPL
    omicsclaw tui           — Textual full-screen TUI
    omicsclaw --ui tui      — Same, via flag
"""

from .interactive import run_interactive  # noqa: F401


def main() -> None:
    """Default CLI entry point — starts interactive mode."""
    run_interactive()
