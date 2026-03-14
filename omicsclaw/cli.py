"""Package-level CLI entrypoint for OmicsClaw."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> None:
    """Load and run the repository-root ``omicsclaw.py`` CLI."""
    cli_path = Path(__file__).resolve().parent.parent / "omicsclaw.py"
    spec = importlib.util.spec_from_file_location("omicsclaw_main", cli_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load CLI module from {cli_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
