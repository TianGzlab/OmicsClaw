"""The permission rule file: reading it, matching against it, writing it back.

Rules say what this deployment has decided about individual tool calls, at a
finer grain than a tool name. A rule file looks like this::

    {
      "permissions": {
        "deny":  ["bash(rm -rf *)", "write_file(/etc/*)"],
        "allow": ["read_file", "bash(git *)", "bash(python -m pytest*)"],
        "ask":   ["bash(pip install*)"]
      }
    }

**Pattern syntax.** Two forms, and no others:

``toolName``
    Matches that tool whatever its arguments.

``toolName(pattern)``
    Matches that tool when *pattern* matches its principal argument. An empty
    ``toolName()`` matches any arguments, like the bare form.

**What a pattern is matched against** is one string, not the whole argument
payload: the value of the tool's first *required* ``string`` property, taken
from the tool's own JSON Schema — ``command`` for ``bash``, ``path`` for the
file tools, ``url`` for ``web_fetch``, ``query`` for ``web_search``. See
:func:`principal_argument`, including what happens when a tool has no such
property. Writing a pattern against the wrong thing is the easy mistake here:
``write_file(*/tmp/*)`` is a statement about the destination path and says
nothing about the content being written.

**Matching.** A pattern containing none of ``*?[`` must equal the principal
argument **exactly**; a pattern containing one of them is a :mod:`fnmatch`
glob over the whole string. There is no substring fallback, so ``bash(ls)``
does not match ``ls -la`` — write ``bash(ls*)`` for that. ``*`` crosses any
character including ``/``, so ``bash(git *)`` matches
``git log -- a/b/c.py``.

**Matching is case-sensitive**, unlike :mod:`omicsclaw.permission.danger`.
A rule naming a tool in the wrong case names a tool that does not exist,
because the registry keys tools exactly; and a case-insensitive ``allow``
would grant more than its author wrote.

**Evaluation.** First match wins, and ``deny`` rules are loaded ahead of
``allow`` ahead of ``ask``, so the key order inside the file does not matter
and a ``deny`` always outranks an ``allow`` that would also have matched. A
call no rule mentions returns ``None`` — not ``ask`` — which is what lets a
caller fall through to further checks of its own.

**A file that cannot be read as written raises** rather than being partly
applied: an unknown action key, a malformed pattern, a scalar where a list
belongs. A *missing* file is an empty rule set and not an error.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

_log = logging.getLogger(__name__)

CONFIG_KEY: Final = "permissions"
"""The top-level object rules live under, so a settings file can grow other
sections without a rule named ``allow`` colliding with one."""

_WILDCARDS: Final = frozenset("*?[")
"""What makes a pattern a glob rather than a literal."""

_FILE_MODE: Final = 0o600
"""The rule file decides what runs unattended: owner-only."""

_DIRECTORY_MODE: Final = 0o700
"""Its parent, when this package is the one creating it."""


class PermissionConfigError(ValueError):
    """A rule file, or a single rule, that cannot be read as written.

    Raised rather than skipped: a misspelled ``"denied"`` key would drop every
    deny rule, and a pattern missing its closing parenthesis would name a tool
    nobody has. Both read, to whoever wrote the file, as a control in force.
    """


class Verdict(StrEnum):
    """What a matching rule says to do. The three actions, and no fourth."""

    ALLOW = "allow"
    """Run it, and do not ask anybody."""

    DENY = "deny"
    """Refuse. The tool does not run and no approval channel is consulted —
    a denial is not a question."""

    ASK = "ask"
    """Put it to a human."""


_LOAD_ORDER: Final = (Verdict.DENY, Verdict.ALLOW, Verdict.ASK)
"""The order rules are loaded in: deny first, so a call matching both a deny
and an allow is denied.

A consequence for :func:`save_rules`: a rule set that interleaved the three
actions does not survive a save-then-load round trip in its original order.
It survives in this one.
"""


@dataclass(frozen=True, slots=True)
class Rule:
    """One line of the file: an action, and what it applies to.

    Validates at construction, so every route in — :func:`load_rules`, a
    hand-built :class:`Rules`, :meth:`RuleStore.remember` — is checked by
    the same code, and a pattern that cannot be parsed can never be held by
    a live rule set.
    """

    verdict: Verdict
    pattern: str
    tool: str = field(init=False)
    """The tool name the pattern selects, parsed out once."""
    glob: str = field(init=False)
    """The argument pattern, or ``""`` for "any arguments"."""

    def __post_init__(self) -> None:
        tool, glob = _parse_pattern(self.pattern)
        object.__setattr__(self, "tool", tool)
        object.__setattr__(self, "glob", glob)

    def matches(self, tool_name: str, argument_text: str) -> bool:
        """Whether this rule speaks about a call to *tool_name*."""
        if tool_name != self.tool:
            return False
        if not self.glob:
            return True
        return _match_argument(argument_text, self.glob)


class Rules:
    """An ordered rule set. Immutable; first match wins.

    Immutable because a live gate holds one: mutating it would change the
    rules a call is being judged against while it is being judged.
    :meth:`with_rule` returns a new set instead.
    """

    __slots__ = ("_rules",)

    def __init__(self, rules: Iterable[Rule] = ()) -> None:
        self._rules = tuple(rules)

    def __len__(self) -> int:
        return len(self._rules)

    def __iter__(self) -> Iterator[Rule]:
        return iter(self._rules)

    def __bool__(self) -> bool:
        return bool(self._rules)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Rules):
            return NotImplemented
        return self._rules == other._rules

    def __hash__(self) -> int:
        return hash(self._rules)

    def __repr__(self) -> str:
        return f"Rules({len(self._rules)} rules)"

    def evaluate(self, tool_name: str, argument_text: str) -> Rule | None:
        """The first rule that matches, or ``None`` if none does.

        Returns the rule rather than its verdict so a caller can report which
        pattern decided — the line a person would edit to change the answer.
        """
        for rule in self._rules:
            if rule.matches(tool_name, argument_text):
                return rule
        return None

    def with_rule(self, verdict: Verdict, pattern: str) -> Rules:
        """This set plus one rule, appended. Returns a new set."""
        return Rules((*self._rules, Rule(verdict, pattern)))

    def to_config(self) -> dict[str, dict[str, list[str]]]:
        """The JSON shape :func:`save_rules` writes.

        Patterns are de-duplicated per action, keeping first occurrence, so
        approving "always allow ``bash(git *)``" twice does not grow the
        file without bound.
        """
        grouped: dict[str, list[str]] = {}
        for verdict in _LOAD_ORDER:
            patterns = [r.pattern for r in self._rules if r.verdict is verdict]
            unique = list(dict.fromkeys(patterns))
            if unique:
                grouped[verdict.value] = unique
        return {CONFIG_KEY: grouped}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> Rules:
        """Read the JSON shape, refusing anything it does not recognise."""
        if CONFIG_KEY not in config:
            return cls()
        section = config[CONFIG_KEY]
        if not isinstance(section, Mapping):
            raise PermissionConfigError(
                f"{CONFIG_KEY!r} must be an object with allow / deny / ask keys, "
                f"not {type(section).__name__}"
            )
        known = {v.value for v in Verdict}
        unknown = sorted(set(map(str, section)) - known)
        if unknown:
            raise PermissionConfigError(
                f"{CONFIG_KEY}: unknown key(s) {unknown}; expected any of "
                f"{sorted(known)}. A misspelled action is a rule that never "
                "fires while reading as though it does"
            )
        rules: list[Rule] = []
        for verdict in _LOAD_ORDER:
            rules.extend(
                Rule(verdict, pattern)
                for pattern in _patterns(section.get(verdict.value), verdict)
            )
        return cls(rules)


def load_rules(path: Path) -> Rules:
    """Read a rule file.

    A **missing** file is an empty rule set, not an error: having written no
    rules is the ordinary case.

    :raises PermissionConfigError: the file exists and cannot be read as
        written — unreadable, not JSON, not an object, an unknown action key,
        or a pattern that will not parse.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Rules()
    except OSError as exc:
        raise PermissionConfigError(f"{path}: {exc}") from exc

    if not raw.strip():
        return Rules()

    try:
        config = json.loads(raw)
    except ValueError as exc:
        raise PermissionConfigError(f"{path}: not valid JSON — {exc}") from exc
    if not isinstance(config, Mapping):
        raise PermissionConfigError(
            f"{path}: the top level must be an object, not {type(config).__name__}"
        )
    try:
        return Rules.from_config(config)
    except PermissionConfigError as exc:
        raise PermissionConfigError(f"{path}: {exc}") from exc


def save_rules(path: Path, rules: Rules) -> None:
    """Write *rules* to *path*, replacing what was there.

    Written to a temporary file in the same directory and renamed into place,
    so a failure partway through leaves the previous rules intact rather than a
    file whose ``deny`` list got truncated.

    The file is created ``0600``, and every directory **this call creates** is
    ``0700``. Directories that already exist are left as they are.

    **Symlinks in *path* are followed, so a directory somebody else can write
    to must not appear anywhere above the rule file.** An existing level that
    is a symlink is treated as the directory it points at — which is what a
    workspace under a symlinked path needs, and also means a symlink planted
    at an intermediate level redirects where the file lands. The modes above
    still hold at the real location; the location is what moves. Point
    ``--permission-rules`` only at a path whose parents are yours.

    :raises OSError: the file could not be written. The temporary file is
        removed first.
    """
    payload = json.dumps(rules.to_config(), indent=2, ensure_ascii=False) + "\n"
    _make_owner_only(path.parent)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(_FILE_MODE)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _make_owner_only(directory: Path) -> None:
    """Create *directory* and every missing parent, each readable only by its owner.

    One :meth:`~pathlib.Path.mkdir` per level rather than ``parents=True``:
    with ``parents=True`` CPython applies *mode* only to the final
    component and creates the intermediate ones at the default ``0o777``,
    so ``--permission-rules /new/deep/settings.json`` would leave ``/new``
    world-traversable while the leaf looked correct.

    The explicit :meth:`~pathlib.Path.chmod` is there because ``mkdir``'s
    mode is masked by the process umask, which can only remove bits — so
    the mode is never wider than asked for, but can be narrower than the
    owner needs.

    Existing directories are left as they are: this creates, it does not
    tighten a tree somebody else set up.
    """
    for level in (*reversed(directory.parents), directory):
        if level.exists():
            continue
        level.mkdir(mode=_DIRECTORY_MODE, exist_ok=True)
        level.chmod(_DIRECTORY_MODE)


class RuleStore:
    """The rule file, re-read on every question.

    Not cached: somebody who answers "always allow" expects the *next* tool
    call to stop asking, and a cached rule set would make that take a restart.
    The file is well under a kilobyte and the read happens once per tool call.

    Loud at construction, resilient afterwards. The file is read once in
    ``__init__``, so a typo raises at start-up rather than on the first tool
    call. A file that *becomes* unreadable later keeps the last good rule set
    and logs a warning instead of raising.
    """

    __slots__ = ("_last", "_path")

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._last = load_rules(self._path)

    @property
    def path(self) -> Path:
        """Where the rules are read from and written to."""
        return self._path

    @property
    def current(self) -> Rules:
        """The rules as the file has them now.

        Warns when ``allow`` rules appear that this process did not write.
        An operator editing the file mid-session is legitimate, so this does
        not refuse them —— but so is the thing it exists to make visible: a
        tool that was allowed to run unsupervised writing its own next
        ``allow`` rule (plan 0049 §4). A warning is the most this layer can
        do without making the operator's edit a restart.
        """
        try:
            loaded = load_rules(self._path)
        except PermissionConfigError as exc:
            _log.warning(
                "permission rules unreadable, keeping the %d previously loaded: %s",
                len(self._last),
                exc,
            )
            return self._last
        appeared = _allow_patterns(loaded) - _allow_patterns(self._last)
        if appeared:
            _log.warning(
                "permission rules changed outside this process: new allow %s "
                "in %s",
                sorted(appeared),
                self._path,
            )
        self._last = loaded
        return self._last

    def remember(self, pattern: str) -> Rules:
        """Append an ``allow`` rule and persist it. Returns the new set.

        The "always allow" half of an approval prompt, and the only method here
        that writes. *pattern* is validated on the way in, so a pattern that
        would never fire raises instead of being written.
        """
        updated = self.current.with_rule(Verdict.ALLOW, pattern)
        save_rules(self._path, updated)
        self._last = updated
        _log.info("permission rule remembered: allow %s", pattern)
        return updated


def _allow_patterns(rules: Rules) -> frozenset[str]:
    return frozenset(
        rule.pattern for rule in rules if rule.verdict is Verdict.ALLOW
    )


def principal_argument(arguments: str, schema: Mapping[str, Any] | None = None) -> str:
    """The one string a pattern is matched against.

    The value of the tool's first *required* property of type ``string``,
    read out of the raw payload. That is the tool's own declaration of what
    the call is *about*: ``bash``'s ``command``, the file tools' ``path``,
    ``web_fetch``'s ``url``, ``web_search``'s ``query``, ``use_skill``'s
    ``skill_name``.

    **Falls back to the raw JSON payload** when there is no schema, no
    required string property, or no such key in the payload. A pattern then
    has to be written against the JSON text, which is the safe direction for a
    ``deny`` — the values are still in there — and the loose direction for an
    ``allow``.

    Never raises: a payload the model truncated still has to be evaluated,
    since the rules are how a truncated call gets stopped.
    """
    key = principal_key(schema)
    if key is None:
        return arguments
    try:
        decoded = json.loads(arguments)
    except (TypeError, ValueError):
        return arguments
    if not isinstance(decoded, Mapping):
        return arguments
    value = decoded.get(key)
    if isinstance(value, str) and value:
        return value
    return arguments


def principal_key(schema: Mapping[str, Any] | None) -> str | None:
    """The first required property typed ``string``, or ``None``.

    Order comes from the schema's own ``required`` list, which is why
    ``write_file`` resolves to ``path`` and not ``content``: its
    ``required`` is ``["path", "content"]``, and the destination is what a
    rule is about. That ordering is a property of the tool, so a tool whose
    principal argument is not first says so by listing it first.
    """
    if not isinstance(schema, Mapping):
        return None
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
        return None
    if not isinstance(properties, Mapping):
        return None
    for name in required:
        if not isinstance(name, str):
            continue
        declared = properties.get(name)
        if isinstance(declared, Mapping) and declared.get("type") == "string":
            return name
    return None


def literal_pattern(tool_name: str, argument_text: str) -> str:
    """A pattern matching *this* call and no other. What "always allow" writes.

    Every wildcard in *argument_text* is neutralised by wrapping it in a
    :mod:`fnmatch` character class — ``*`` becomes ``[*]`` — so an approved
    ``ls *.csv`` is remembered as that command and not as a glob over every
    ``ls`` of every file.

    The pattern is exact rather than a prefix, so approving ``git status``
    once does not also allow ``git status; rm -rf /``. An operator who wants a
    whole family of commands writes that glob into the file themselves.
    """
    if not argument_text:
        return tool_name
    escaped = (
        argument_text.replace("[", "[[]").replace("*", "[*]").replace("?", "[?]")
    )
    return f"{tool_name}({escaped})"


def _parse_pattern(pattern: str) -> tuple[str, str]:
    """Split ``tool`` or ``tool(glob)``, refusing anything else."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise PermissionConfigError("a rule pattern may not be empty")
    text = pattern.strip()
    tool, separator, tail = text.partition("(")
    if not separator:
        return text, ""
    if not tool:
        raise PermissionConfigError(
            f"{pattern!r}: a pattern must name a tool before its '('"
        )
    if not tail.endswith(")"):
        raise PermissionConfigError(
            f"{pattern!r}: missing the closing ')'. Left as written it would "
            "match a tool name nobody has, which reads as a rule in force"
        )
    return tool, tail[:-1]


def _match_argument(argument_text: str, glob: str) -> bool:
    """Exact when the pattern has no wildcard, :mod:`fnmatch` when it does."""
    if not _WILDCARDS & frozenset(glob):
        return argument_text == glob
    return fnmatch.fnmatchcase(argument_text, glob)


def _patterns(raw: Any, verdict: Verdict) -> list[str]:
    """One action's patterns, refusing a scalar written where a list belongs."""
    if raw is None:
        return []
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise PermissionConfigError(
            f"{verdict.value}: must be a list of patterns, not "
            f"{type(raw).__name__}"
        )
    patterns: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise PermissionConfigError(
                f"{verdict.value}: every pattern must be a string, found "
                f"{type(item).__name__}"
            )
        patterns.append(item)
    return patterns


__all__ = [
    "CONFIG_KEY",
    "PermissionConfigError",
    "Rule",
    "RuleStore",
    "Rules",
    "Verdict",
    "literal_pattern",
    "load_rules",
    "principal_argument",
    "principal_key",
    "save_rules",
]
