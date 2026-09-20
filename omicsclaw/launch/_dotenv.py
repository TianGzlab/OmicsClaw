"""Where ``.env`` is — answered once, for every consumer in this package.

Two functions read this program's credential file and they must not
disagree: :func:`omicsclaw.launch._adopt_dotenv` loads it at start-up,
and ``oc cli -- --configure`` writes it. A wizard that configured one
file while the shell loaded another would be a setup step that appears
to succeed and changes nothing — the most expensive shape of bug a
first-run experience can have, because the user's next move is to doubt
their credential rather than the tool.

So the search is written here, once, and both callers take their answer
from it. Neither computes a path of its own; that is the whole reason
this module is separate from the two that use it.

**Two locations, project root first.** ``CLAUDE.md`` documents the
repository's own ``.env`` and the reference harness reads the one in the
working directory, so both are searched —— and in that order, because
:func:`omicsclaw.launch._adopt_dotenv` loads them with ``override=False``
and therefore the *first* file to name a variable is the one that
decides it. :func:`dotenv_target` returns the first that exists for
exactly that reason: writing anywhere else would put the new value
behind a file that already wins.

**Both roots are parameters.** ``resolve_omicsclaw_dir()`` and the
working directory are facts about a process, and a test that has to
arrange them by changing the process it runs in is a test that leaks.
Two tests in ``tests/launch/test_surfaces.py`` were red on this
checkout for that reason —— they pinned ``root`` and left the working
directory pointing at a tree that happens to contain a real ``.env``.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["DOTENV_FILE", "dotenv_candidates", "dotenv_target"]

DOTENV_FILE = ".env"
"""The credential file this shell adopts, and the name it is written under.

``CLAUDE.md`` teaches ``.env`` at the project root as *the* way to supply
``LLM_API_KEY``, ``TELEGRAM_BOT_TOKEN`` and the Feishu pair, and the
runner this shell replaces loaded it (``surfaces/channels/__main__.py``
:44-45), as does the reference harness (``cmd/harness9/main.go:117``).
``omicsclaw/entry/config.py`` records loading it as this package's job.
Between plan 0037's delivery and its review, no package did it —— the
promise was in three places and the implementation in none.
"""


def dotenv_candidates(
    root: Path | None = None, cwd: Path | None = None
) -> tuple[Path, ...]:
    """The files the shell reads, in the order it reads them.

    De-duplicated, because the common case is running ``oc`` from the
    checkout, where both roots are the same directory and loading it
    twice would report it twice.
    """
    from omicsclaw.common.workspace import resolve_omicsclaw_dir

    base = resolve_omicsclaw_dir() if root is None else Path(root)
    here = Path.cwd() if cwd is None else Path(cwd)
    return tuple(
        directory / DOTENV_FILE for directory in dict.fromkeys((base, here))
    )


def dotenv_target(root: Path | None = None, cwd: Path | None = None) -> Path:
    """The file a new setting has to go into to take effect.

    The first candidate that exists, because that is the one whose value
    wins; the first candidate outright when none does, because a file
    that has to be created should be created where ``CLAUDE.md`` says it
    lives rather than wherever the user happened to be standing.
    """
    candidates = dotenv_candidates(root, cwd)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]
