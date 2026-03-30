"""Package-level CLI entrypoint for OmicsClaw."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _iter_cli_path_candidates() -> list[Path]:
    """Return candidate paths for the top-level ``omicsclaw.py`` launcher."""
    candidates: list[Path] = []

    # 1) Standard source/editable layout: <repo>/omicsclaw/cli.py -> <repo>/omicsclaw.py
    candidates.append(Path(__file__).resolve().parent.parent / "omicsclaw.py")

    # 2) Optional explicit override.
    env_path = os.environ.get("OMICSCLAW_CLI_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser().resolve())

    # 3) Search from current working directory upwards (non-editable install
    #    but user is running `oc` inside a cloned OmicsClaw repo).
    cwd = Path.cwd().resolve()
    for base in (cwd, *cwd.parents):
        candidates.append(base / "omicsclaw.py")

    # Deduplicate while preserving order.
    uniq: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def _discover_cli_path() -> Path:
    for p in _iter_cli_path_candidates():
        if p.exists() and p.is_file():
            return p

    tried = "\n".join(f"  - {p}" for p in _iter_cli_path_candidates())
    raise FileNotFoundError(
        "Could not locate 'omicsclaw.py' launcher.\n"
        "Tried:\n"
        f"{tried}\n\n"
        "If you are using a source checkout, run `oc` from inside the OmicsClaw repo,\n"
        "or set OMICSCLAW_CLI_PATH to the absolute path of omicsclaw.py."
    )


def main() -> None:
    """Load and run the repository-root ``omicsclaw.py`` CLI."""
    cli_path = _discover_cli_path()
    spec = importlib.util.spec_from_file_location("omicsclaw_main", cli_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load CLI module from {cli_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
