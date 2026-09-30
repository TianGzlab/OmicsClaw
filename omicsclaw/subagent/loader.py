"""Loading sub-agent definitions from a directory of Markdown files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .definition import SubAgentDefinition
from .frontmatter import parse_agent_file

__all__ = ["AGENT_SUFFIX", "LoadErrorSink", "load_agents"]

AGENT_SUFFIX = ".md"
"""The only file extension this loader reads."""

LoadErrorSink = Callable[[Path, Exception], None]
"""Told about one file that could not be loaded. Called once per file.

This package does not log, so a deployment that wants a bad agent file to
be visible passes one of these; without it a bad file is simply absent.
"""


def load_agents(
    directory: str | os.PathLike[str],
    *,
    on_error: LoadErrorSink | None = None,
    encoding: str = "utf-8",
) -> tuple[SubAgentDefinition, ...]:
    """Every readable definition directly under *directory*, sorted by name.

    :param directory: scanned non-recursively for ``*.md`` files. A
        directory that does not exist yields ``()``.
    :param on_error: told about each file that could not be read or
        parsed; that file is skipped and the scan continues.
    :param encoding: how the files are read.
    :returns: the definitions that loaded, ordered by filename so the
        result is stable across machines.

    A file whose header names no ``name`` is loaded under its filename
    stem, so a definition is never lost to that one omission alone.
    """
    base = Path(directory)
    try:
        paths = sorted(
            path
            for path in base.iterdir()
            if path.is_file() and path.suffix == AGENT_SUFFIX
        )
    except (FileNotFoundError, NotADirectoryError):
        return ()
    except OSError as exc:
        if on_error is not None:
            on_error(base, exc)
        return ()

    loaded: list[SubAgentDefinition] = []
    for path in paths:
        definition = _load_one(path, encoding, on_error)
        if definition is not None:
            loaded.append(definition)
    return tuple(loaded)


def _load_one(
    path: Path,
    encoding: str,
    on_error: LoadErrorSink | None,
) -> SubAgentDefinition | None:
    """One file's definition, or ``None`` after reporting why not."""
    try:
        content = path.read_text(encoding=encoding)
        return parse_agent_file(
            content, source=str(path), fallback_name=path.stem.lower()
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        if on_error is not None:
            on_error(path, exc)
        return None
