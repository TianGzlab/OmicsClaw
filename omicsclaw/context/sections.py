"""``omicsclaw/context`` — the vocabulary a system prompt is built from.

Plan 0030 task B. A :class:`Section` is one titled block of the system
prompt and, more importantly, one place where knowledge this package is
not allowed to have gets in.

**Every source is a callable, and it is called on every render.** The
reference harness takes a function for exactly one of its blocks —
long-term memory, ``builder.go:56-59`` — with the reason written beside
it: ``memory_write`` rewrites ``MEMORY.md`` *while the agent runs*, so a
snapshot taken at construction would have the agent reasoning from the
version before the one it just wrote. That argument is not special to
memory here. ``create_omics_skill`` adds skills mid-run, ``edit_file``
rewrites ``AGENTS.md`` mid-run. So it is generalised: no section holds a
snapshot, all of them are closures, and "what was written is visible on
the next turn" is a property of the shape rather than a mechanism
someone has to remember to trigger.

**That generalisation has a price, and it is charged in cache.** See
:meth:`~omicsclaw.context.prompt.PromptAssembler.render`.

**Exceptions from a source are not caught, and nothing here logs.** The
layer being replaced wrapped every block in fail-closed error handling
with a warning. Three reasons it is gone: this is a leaf package and the
engine beside it already settled "no I/O, no logging"; a
:data:`SectionSource` is an *arbitrary callable* — not the harness's one
fixed ``os.ReadFile`` — and swallowing arbitrary exceptions is a Python
anti-pattern; and the failure mode it produced was the wrong one. A
``SOUL.md`` that fails to read turning quietly into "the agent has no
persona" is more expensive than a crash, because nobody finds out. The
consequence is real and belongs to the caller: wrap a source that may
fail if a degraded prompt is genuinely better than no prompt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeAlias

__all__ = [
    "RenderedSection",
    "Section",
    "SectionSource",
    "static",
    "text_from_file",
]

SectionSource: TypeAlias = Callable[[], str]
"""Produces one section's body. Called on **every** render, never cached."""


@dataclass(frozen=True, slots=True)
class Section:
    """One block of the system prompt, and where its text comes from."""

    key: str
    """Stable identifier, for :meth:`~omicsclaw.context.prompt.
    PromptAssembler.without` and for diagnostics. Not rendered."""

    heading: str
    """Rendered above the body, separated by a blank line. ``""`` for a
    block that carries no title, such as the base persona."""

    source: SectionSource
    """Where the body comes from."""

    enabled: bool = True
    """``False`` drops the section without removing it from the list."""


@dataclass(frozen=True, slots=True)
class RenderedSection:
    """What one section became on one particular render."""

    key: str
    content: str
    """Heading and body, exactly as they appear in the system prompt."""

    estimated_tokens: int


def static(text: str) -> SectionSource:
    """A source for text that is already in hand."""
    return lambda: text


def text_from_file(
    path: str | os.PathLike[str],
    *,
    encoding: str = "utf-8",
) -> SectionSource:
    """A source that reads *path* fresh on every render.

    The only place in this package that touches a filesystem, and it is
    a convenience rather than a mechanism: the caller decides which
    files are prompt material by building sections, because encoding
    ``CLAUDE.md`` + ``AGENTS.md`` + ``SOUL.md`` + eight
    ``skills/<domain>/INDEX.md`` as parameters of this layer would nail
    that policy to the bottom of the stack.

    **A file that is not there yields ``""``**, which makes the section
    disappear whole — the harness's treatment of a missing ``AGENTS.md``
    (``builder.go:107-110``) and what plan 0030 §5.1 asks for when
    ``SOUL.md`` is absent ("the persona section is empty, the caller
    supplies its own fallback"). Absence is a state, not a failure.

    Every other error — unreadable, undecodable, a directory — is a
    failure and propagates, per the module docstring. Nothing is cached:
    a file edited mid-run is read again on the next render.
    """

    def read() -> str:
        try:
            return Path(path).read_text(encoding=encoding)
        except FileNotFoundError:
            return ""

    return read
