"""OmicsClaw interactive CLI/TUI package.

Entry points:
    omicsclaw interactive   — Rich CLI with prompt_toolkit REPL
    omicsclaw tui           — Textual full-screen TUI
    omicsclaw --ui tui      — Same, via flag
"""

from __future__ import annotations


def run_interactive(*args, **kwargs):
    """Start interactive mode without importing optional deps at package import."""
    from .interactive import run_interactive as _run_interactive

    return _run_interactive(*args, **kwargs)


def main() -> None:
    """Default CLI entry point — starts interactive mode."""
    run_interactive()
