"""Shell-command patterns that should be read by a person before they run.

Scans a shell command for syntax that destroys data, escalates privilege, or
sends local files somewhere else, and reports the match so a caller can put
the call to a human.

What this module guarantees, and what it does not:

- A match escalates to *ask*, **never** to *deny*. A pattern match is a
  suspicion, and only a person can tell ``rm -rf ./tmp_run7`` from
  ``rm -rf /``.
- Matching is **case-insensitive**, so ``chmod -R`` and ``chmod -r`` are the
  same command.
- Patterns are anchored so a command name is not matched inside a longer word
  or as part of a flag: ``sudo`` does not match ``--sudo-mode`` or
  ``pseudobulk``, ``sh`` does not match ``shuf``. They are **not** shell
  parsing: a command name appearing as an argument to something else
  (``grep sudo notes.txt``) still matches, and a command quoted inside a
  string still matches. The cost of both is one prompt.
- This looks at one command string. Deciding *which* tool arguments are
  command strings is the caller's job; :data:`COMMAND_ARGUMENT` is the
  convention it can use.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Final

from omicsclaw.tools.base import RiskLevel

COMMAND_ARGUMENT: Final = "command"
"""The argument name that marks a tool as taking shell text.

A tool whose own schema calls its principal argument ``command`` is taken to
be a shell, whatever the tool is named — so a sandboxed shell, a renamed
``bash`` or an MCP server exposing one are all covered without this module
knowing they exist.
"""


@dataclass(frozen=True, slots=True)
class DangerPattern:
    """One thing worth reading a command for, and why."""

    expression: str
    """Regular expression, matched with :func:`re.search` and
    :data:`re.IGNORECASE`."""

    risk_level: RiskLevel
    """Blast radius, for the approval prompt. Only ``HIGH`` and ``MEDIUM``
    appear: a command worth ``LOW`` is not worth interrupting anybody for."""

    reason: str
    """What the command does, in words a person can decide on. Describes the
    effect, never the pattern that matched."""

    compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)
    """:attr:`expression`, compiled at construction."""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "compiled", re.compile(self.expression, re.IGNORECASE)
        )

    def found_in(self, command: str) -> bool:
        """Whether this pattern appears anywhere in *command*."""
        return self.compiled.search(command) is not None


_CMD: Final = r"(?<![\w-])"
"""Left anchor for a command name: not inside a word, and not after a dash.

The dash is what ``\\b`` misses — ``\\bsudo\\b`` matches the ``sudo`` inside
``--sudo-mode``, because a word boundary exists between ``-`` and ``s``. A
``/`` is deliberately allowed on the left so ``/usr/bin/sudo`` still matches.
"""

_END: Final = r"(?![\w-])"
"""Right anchor for a command name: not followed by a word character or a
dash, so ``systemctl`` does not match ``systemctl-status-checker``."""

_SEGMENT: Final = r"[^|;&\n]*"
"""Characters that stay inside one command of a chain.

``rm -f a | grep -r b`` has an ``-f`` and an ``-r`` and deletes one file, so
a pattern needing two flags on *one* command scans across this rather than
across the whole line.
"""

DEFAULT_DANGER_PATTERNS: Final[tuple[DangerPattern, ...]] = (
    # --- Destructive: data that does not come back ------------------------
    DangerPattern(
        rf"{_CMD}rm{_END}(?={_SEGMENT}\s-[a-z]*r)(?={_SEGMENT}\s-[a-z]*f)",
        RiskLevel.HIGH,
        "deletes files and directories recursively, with no prompt and no "
        "recovery",
    ),
    DangerPattern(
        rf"{_CMD}rm{_END}{_SEGMENT}\s/\s*(\*|$)",
        RiskLevel.HIGH,
        "deletes the filesystem root",
    ),
    DangerPattern(
        rf"{_CMD}shred{_END}",
        RiskLevel.HIGH,
        "overwrites a file's contents so they cannot be recovered",
    ),
    DangerPattern(
        rf"{_CMD}truncate{_END}{_SEGMENT}(-s\s*|--size[=\s])0{_END}",
        RiskLevel.HIGH,
        "empties a file, keeping the name and discarding the contents",
    ),
    DangerPattern(
        rf"{_CMD}find{_END}{_SEGMENT}-delete{_END}",
        RiskLevel.HIGH,
        "deletes every file the search matches",
    ),
    DangerPattern(
        rf"{_CMD}find{_END}{_SEGMENT}-exec\s+rm{_END}",
        RiskLevel.HIGH,
        "runs rm on every file the search matches",
    ),
    DangerPattern(
        rf"{_CMD}xargs{_END}{_SEGMENT}{_CMD}rm{_END}",
        RiskLevel.HIGH,
        "deletes every path piped into it",
    ),
    DangerPattern(
        rf"{_CMD}dd{_END}\s+[io]f=",
        RiskLevel.HIGH,
        "reads or writes raw blocks, which can overwrite a whole disk",
    ),
    DangerPattern(
        r">\s*/dev/(sd|nvme|hd|mem|kmem|loop)",
        RiskLevel.HIGH,
        "redirects output onto a block device, destroying its contents",
    ),
    DangerPattern(
        r">\s*/etc/",
        RiskLevel.HIGH,
        "overwrites a file under /etc, which configures the machine itself",
    ),
    DangerPattern(
        rf"{_CMD}mkfs(\.[a-z0-9]+)?{_END}",
        RiskLevel.HIGH,
        "creates a filesystem, erasing whatever is on the target",
    ),
    # --- Remote code execution -------------------------------------------
    DangerPattern(
        rf"\|\s*(bash|sh|zsh|dash|ksh|python[0-9.]*|perl|ruby){_END}",
        RiskLevel.HIGH,
        "pipes content straight into an interpreter, so whatever was "
        "downloaded runs unread",
    ),
    DangerPattern(
        r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:",
        RiskLevel.HIGH,
        "fork bomb: spawns processes until the machine stops responding",
    ),
    # --- Data leaving this machine ----------------------------------------
    DangerPattern(
        rf"{_CMD}scp{_END}",
        RiskLevel.HIGH,
        "copies local files to another machine",
    ),
    DangerPattern(
        rf"{_CMD}rsync{_END}{_SEGMENT}\s\S+:",
        RiskLevel.HIGH,
        "synchronises local files to a remote host",
    ),
    DangerPattern(
        rf"{_CMD}ssh{_END}\s+\S",
        RiskLevel.HIGH,
        "opens a channel to another machine that can carry local data out",
    ),
    DangerPattern(
        rf"{_CMD}(curl|wget){_END}{_SEGMENT}(--upload-file|\s-T\s|"
        r"--data-binary\s*@|\s-d\s*@|--form\s*\S*=@)",
        RiskLevel.HIGH,
        "uploads the contents of a local file to a remote endpoint",
    ),
    DangerPattern(
        rf"{_CMD}nc{_END}\s+\S",
        RiskLevel.MEDIUM,
        "opens an arbitrary network connection, which can carry a file out",
    ),
    DangerPattern(
        rf"{_CMD}git{_END}\s+push{_END}",
        RiskLevel.MEDIUM,
        "publishes commits to a remote repository",
    ),
    # --- Privilege and system state ---------------------------------------
    DangerPattern(
        rf"{_CMD}chmod{_END}{_SEGMENT}\s-[a-z]*r[a-z]*\s+777{_END}",
        RiskLevel.HIGH,
        "grants every account full access to a whole directory tree",
    ),
    DangerPattern(
        rf"{_CMD}chown{_END}\s+-[a-z]*r[a-z]*",
        RiskLevel.HIGH,
        "changes who owns a whole directory tree",
    ),
    DangerPattern(
        rf"{_CMD}sudo{_END}",
        RiskLevel.MEDIUM,
        "runs as root, so nothing in the workspace boundary applies",
    ),
    DangerPattern(
        rf"{_CMD}chmod{_END}\s+777{_END}",
        RiskLevel.MEDIUM,
        "grants every account full access",
    ),
    DangerPattern(
        rf"{_CMD}killall{_END}",
        RiskLevel.MEDIUM,
        "kills every process of a given name",
    ),
    DangerPattern(
        rf"{_CMD}pkill{_END}",
        RiskLevel.MEDIUM,
        "kills processes matching a name",
    ),
    DangerPattern(
        rf"{_CMD}kill{_END}\s+-9{_END}",
        RiskLevel.MEDIUM,
        "force-kills a process, so it cannot save or clean up",
    ),
    DangerPattern(
        rf"{_CMD}iptables{_END}",
        RiskLevel.MEDIUM,
        "changes this machine's firewall rules",
    ),
    DangerPattern(
        rf"{_CMD}systemctl{_END}",
        RiskLevel.MEDIUM,
        "starts, stops or reconfigures a system service",
    ),
)
"""The built-in patterns, grouped by theme so the table can be audited.

:meth:`DangerPatterns.inspect` returns the most severe match, so this order
decides only which of two **equally severe** reasons a person reads.
"""

_SEVERITY: Final[dict[RiskLevel, int]] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
}
"""Rank for comparison. :class:`~omicsclaw.tools.RiskLevel` is a
:class:`~enum.StrEnum`, so ``>`` on it compares alphabetically — under which
``"medium"`` outranks ``"high"``."""


class DangerPatterns:
    """An immutable pattern set, scanned as a whole.

    Injectable so a deployment can narrow or widen the list — a container
    with no network and no mounted data has no use for the upload patterns.
    """

    __slots__ = ("_patterns",)

    def __init__(
        self, patterns: Iterable[DangerPattern] = DEFAULT_DANGER_PATTERNS
    ) -> None:
        self._patterns = tuple(patterns)

    def __len__(self) -> int:
        return len(self._patterns)

    def __iter__(self) -> Iterator[DangerPattern]:
        return iter(self._patterns)

    def __repr__(self) -> str:
        return f"DangerPatterns({len(self._patterns)} patterns)"

    def inspect(self, command: str) -> DangerPattern | None:
        """The most severe pattern found in *command*, or ``None`` if none is.

        Every pattern is scanned, not just up to the first hit, so the reason
        reported for ``chmod -R 777 . && git push`` is the permissions change
        and not the push. Ties go to the pattern listed first, so the answer
        does not depend on scan order.
        """
        best: DangerPattern | None = None
        for pattern in self._patterns:
            if not pattern.found_in(command):
                continue
            if best is None or _SEVERITY[pattern.risk_level] > _SEVERITY[
                best.risk_level
            ]:
                best = pattern
        return best


__all__ = [
    "COMMAND_ARGUMENT",
    "DEFAULT_DANGER_PATTERNS",
    "DangerPattern",
    "DangerPatterns",
]
