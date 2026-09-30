"""``edit_file`` — replace one passage of a file, not the whole file.

Modelled on harness9's ``internal/tools/edit_file.go``. Where
``write_file`` replaces a file entirely, this takes an anchor
(``source_text``) and what to put in its place, and refuses unless the
anchor names exactly one place.

**Four match levels, each looser than the last, each keeping the
uniqueness guard:** L1 exact, L2 ignoring line endings, L3 ignoring
whitespace around the anchor, L4 ignoring indentation. A model writing an
anchor from memory lands *near* the bytes on disk rather than on them;
refusing a near miss costs a turn, and matching loosely writes bytes
nobody approved, so the cascade trades one for the other a step at a time.

**L1 is reported as exact and L2–L4 as fuzzy.** After an exact match the
diff in the result is authoritative. After a fuzzy one the written bytes
may differ from what the model pictured — in Python, where indentation is
syntax, that is the difference between a fix and an ``IndentationError``
— so the result asks for a re-read instead.

**Order of operations: read, match, ask, re-read, write.** The match runs
before the approval so a human is shown the diff rather than the
arguments. The file is then read again inside the write lock; if it
changed while the prompt was open the edit is refused, because the thing
approved was a diff against particular bytes. The lock is not held across
the approval — a human's thinking time is unbounded, and holding it would
stall every other tool touching the path.

**Two guards the reference lacks.** An empty or all-whitespace anchor is
refused by name (see :func:`_reject_empty`), and a no-op edit succeeds
rather than erroring, so re-sending an edit already applied is harmless.

**Failures are the model's to correct.** A missing anchor, an ambiguous
one, a path outside the workspace or a file that is not UTF-8 all raise
and become ``is_error=True``. A no-op edit does not: the world is already
in the requested state.

``environment=None`` means the local filesystem; anything else has both
its ``read_file`` and ``write_file`` awaited. See
:class:`FileEditEnvironment`.

**What the legacy ``file_edit`` could do and this cannot.** Its schema
carries ``replace_all``, and on an ambiguous anchor it tells the model to
set it. There is no equivalent here, so N identical lines that must all
change have no anchor that disambiguates them and the edit is simply
refused — the model has to fall back to ``write_file`` with the whole
file. The reference has no such flag either, which is why porting it was
never considered, but it is a real capability loss and belongs on the
migration's list rather than in nobody's.

**A known imprecision in the error classification.** ``except OSError``
in :meth:`EditTool._get` and :meth:`EditTool._put` also catches
:exc:`TimeoutError`, which is an ``OSError`` subclass and is what
:func:`asyncio.wait_for` raises — so an ``Environment`` that bounds its
own container round-trip reports a transient infrastructure failure as
"send a different path". :exc:`asyncio.CancelledError` is unaffected.
The same pattern is in ``read.py``, ``write.py`` and ``bash.py``, so it
is a layer-wide convention to fix in one place rather than here.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools._pathlock``,
``omicsclaw.tools._workspace``, ``omicsclaw.tools.base``,
``omicsclaw.tools.context``, ``omicsclaw.tools.function_tool``,
``omicsclaw.tools.builtin.read``, ``omicsclaw.tools.builtin.write``, and
the standard library.
"""

from __future__ import annotations

import copy
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from omicsclaw.schema import ToolDefinition

from .._pathlock import read_lock, write_lock
from .._workspace import Workspace
from ..base import ApprovalMode, RiskLevel, ToolPolicy
from ..context import report_progress, require_approval
from ..function_tool import ToolArgumentError, decode_arguments, validate_arguments
from .read import LINE_NUMBER_WIDTH, resolve_workspace
from .write import DIRECTORY_MODE, FILE_MODE

TOOL_NAME = "edit_file"
"""harness9's name, kept so it does not collide with the legacy
``file_edit``, which is still mounted in every surface. Two tools of one
name in one registry is a start-up failure rather than a merge.
"""

MATCH_EXACT = 1
"""L1: ``source_text`` occurred once, verbatim. ``edit_file.go:136``."""

MATCH_NEWLINE = 2
"""L2: matched after ``\\r\\n`` → ``\\n`` on both sides. ``edit_file.go:137``."""

MATCH_TRIMMED = 3
"""L3: matched after stripping the anchor's ends. ``edit_file.go:138``."""

MATCH_LINE_BY_LINE = 4
"""L4: matched line by line, ignoring indentation. ``edit_file.go:139``."""

CONTEXT_LINES = 3
"""Unchanged lines shown either side of a change in the summary diff.

``edit_file.go:143``. Three is the unified-diff convention: enough to
place a hunk in a file, not enough to matter against a context budget.
"""

MAX_SUMMARY_LINES = 20
"""Changed lines above which the summary reports counts instead of a diff.

``edit_file.go:200``. Roughly a screenful — the size at which a diff
stops being glanced at and starts being scrolled.
"""

_LINE_PREFIX = re.compile(rf"^ {{0,{LINE_NUMBER_WIDTH - 1}}}\d+\t")
"""Matches one ``read_file`` line-number prefix, the inverse of
:func:`~omicsclaw.tools.builtin.read.numbered_line`'s ``%6d<TAB>``.

Built from :data:`~omicsclaw.tools.builtin.read.LINE_NUMBER_WIDTH` so the
two halves of the contract cannot drift. Leading spaces are optional and
bounded because the field is right-aligned in six columns: line 7 arrives
as five spaces and a digit, line 1,000,000 as seven digits and none.
"""


@runtime_checkable
class FileEditEnvironment(Protocol):
    """Where this tool's reads and writes land. Injected, never imported.

    Two methods, unlike ``read``'s and ``write``'s one each: an edit is a
    read-modify-write and both halves must reach the same filesystem.
    Routing the read through a container while writing to the host would
    corrupt the file rather than merely leak it.

    Protocols are structural, so an object offering harness9's whole
    five-method ``sandbox.Environment`` shape satisfies this one, ``read``'s
    and ``write``'s at once.

    An implementation must create missing parent directories in
    ``write_file``, though this tool only edits files that already exist.
    """

    async def read_file(self, path: str) -> bytes:
        """The whole file at ``path``, as bytes."""
        ...

    async def write_file(self, path: str, data: bytes) -> None:
        """Replace the contents of ``path`` with ``data``."""
        ...


_DESCRIPTION = (
    "Replace one passage of an existing file with another. Prefer this "
    "over write_file for any change to a file that already exists: "
    "write_file replaces the whole file and needs you to reproduce every "
    "line you are not changing. `source_text` must appear EXACTLY ONCE in "
    "the file, so include enough surrounding lines to be unambiguous; if "
    "it matches more than once exactly, the edit is refused rather than "
    "guessed. With no exact match, the anchor is tried ignoring line "
    "endings, then surrounding whitespace, then indentation, and is used "
    "in the first of those forms where it is unique. Send source_text "
    "without read_file's line-number prefix and the tab after it; a "
    "pasted prefix is removed only when nothing matched with it. The "
    "result says whether the match was exact or fuzzy (prefix removal "
    "counts as fuzzy); after a fuzzy match, re-read the file to check the "
    "indentation. The file must already exist — use write_file to create "
    "one. Depending on the session's permission settings, the user may be "
    "asked to approve the edit first; a declined edit returns an error and "
    "the file is untouched."
)

EDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": (
                "File to edit, relative to the workspace root, e.g. "
                "'src/analysis.py'. It must already exist. Required."
            ),
        },
        "source_text": {
            "type": "string",
            "description": (
                "The existing text to replace, with enough surrounding "
                "context to occur exactly once in the file. Must not "
                "include read_file's line-number prefix. Required."
            ),
        },
        "target_text": {
            "type": "string",
            "description": (
                "The replacement text. Required; send an empty string to "
                "delete the matched passage."
            ),
        },
    },
    "required": ["path", "source_text", "target_text"],
    "additionalProperties": False,
}

_POLICY = ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.ASK,
    prompts_for_itself=True,
    read_only=False,
    concurrency_safe=False,
    writes_workspace=True,
    allowed_in_background=False,
    tags=frozenset({"workspace", "filesystem", "mutation"}),
)
"""``HIGH`` risk, ``ASK`` approval, declared rather than left to default.

``HIGH`` rather than a notch below ``write_file`` despite the smaller
blast radius: an edit's scope is narrower but its subtlety is not —
replacing a file is a change a human notices, replacing four lines inside
one is a change that ships — and the fuzzy levels mean the bytes written
are not always the bytes sent.

``concurrency_safe=False`` is honest: two edits to one path in one turn
is a lost update, and it is :func:`~omicsclaw.tools._pathlock.write_lock`
plus the changed-file check that prevent it, not this flag, which nothing
reads yet.

The tool is inert until some surface binds an approval channel, since
:func:`~omicsclaw.tools.context.require_approval` fails closed.
"""


class EditTool:
    """Replace one passage of a file inside the session's workspace.

    Satisfies :class:`~omicsclaw.tools.base.Tool` structurally. Hand-written
    against that Protocol rather than wrapped by
    :class:`~omicsclaw.tools.function_tool.FunctionTool` because it asks a
    human, and an approval prompt must show the bytes the model actually sent
    rather than a payload re-encoded from what survived decoding.

    ``workspace`` may be omitted, in which case the session's bound one is
    read per call; see
    :func:`~omicsclaw.tools.builtin.read.resolve_workspace`. ``environment``
    defaults to the local filesystem.

    ``policy`` is a plain attribute with no constructor argument:
    ``register(policy=)`` is the authoritative override.
    """

    policy = _POLICY

    def __init__(
        self,
        workspace: Workspace | None = None,
        *,
        environment: FileEditEnvironment | None = None,
    ) -> None:
        self._workspace = workspace
        self._environment = environment
        self._definition = ToolDefinition(
            name=TOOL_NAME,
            description=_DESCRIPTION,
            input_schema=copy.deepcopy(EDIT_SCHEMA),
        )

    @property
    def name(self) -> str:
        return TOOL_NAME

    def definition(self) -> ToolDefinition:
        """The tool definition, built once so the prompt prefix stays stable.

        Deep-copied from :data:`EDIT_SCHEMA`, so two instances cannot share the
        nested ``properties`` mapping.
        """
        return self._definition

    async def execute(self, arguments: str) -> str:
        """Apply the edit described by ``arguments`` and return a summary diff.

        ``arguments`` is the raw JSON payload; it reaches
        :func:`~omicsclaw.tools.context.require_approval` unparsed.

        Reads the file, plans the replacement, asks for approval, then re-reads
        inside the write lock and writes. A file that changed while the prompt was
        open raises rather than being edited: the approved diff no longer
        describes it. A replacement identical to what is already there writes
        nothing.

        Raises :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` for
        anything the model can correct by sending different arguments, and
        :exc:`~omicsclaw.tools._workspace.PathRefused` for a path outside the
        workspace.
        """
        target, source, replacement = _arguments(arguments)
        resolved = resolve_workspace(self._workspace).resolve(target)

        async with read_lock(resolved):
            original = await self._get(target, resolved)
        outcome = plan_edit(original, source, replacement)

        await require_approval(
            self.name,
            arguments,
            policy=self.policy,
            reason=self._reason(resolved, outcome),
            reason_shows_call=outcome.change.diff is not None,
        )
        await report_progress(
            f"editing {resolved} ({outcome.level_name})",
            tool_name=self.name,
        )

        async with write_lock(resolved):
            if await self._get(target, resolved) != original:
                raise ToolArgumentError(
                    f"{target!r} changed while this edit was waiting for "
                    "approval, so the approved diff no longer describes "
                    "it and nothing was written. Read the file again and "
                    "re-send the edit against its current contents"
                )
            if outcome.content == original:
                return _unchanged(target, outcome)
            await self._put(target, resolved, outcome.content)

        return build_summary(target, original, outcome)

    # ---- internals ------------------------------------------------------

    def _reason(self, resolved: Path, outcome: EditOutcome) -> str:
        """The text a human is shown when asked to approve this edit.

        Names the resolved path and carries the diff rather than the arguments,
        plus the match level — "this anchor was found by ignoring indentation" is
        the most useful thing a reviewer can know before saying yes. Falls back to
        line counts when the change is too large to show.
        """
        change = outcome.change
        if change.diff is None:
            scale = f"{change.removed} lines removed, {change.added} added"
            return (
                f"edit {resolved}: {scale}, matched by "
                f"{outcome.level_name}. The diff is too large to show here"
            )
        return (
            f"edit {resolved}, matched by {outcome.level_name}:\n"
            f"{change.diff}"
        )

    async def _get(self, target: str, resolved: Path) -> str:
        """Read ``resolved`` as text, locally or through the environment.

        Decoding is strict, unlike ``read_file``'s byte mode: showing a model a
        replacement character costs it a confusing line, while editing through one
        would write that character over whatever byte was really there.

        Raises :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` naming the
        argument to change — a missing file points at ``write_file``.
        """
        if self._environment is not None:
            try:
                raw = await self._environment.read_file(str(resolved))
            except OSError as exc:
                raise ToolArgumentError(_unreadable(target, exc)) from exc
        else:
            try:
                raw = resolved.read_bytes()
            except OSError as exc:
                raise ToolArgumentError(_unreadable(target, exc)) from exc

        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolArgumentError(
                f"cannot edit {target!r}: it is not valid UTF-8 text "
                f"({exc.reason} at byte {exc.start}). This tool edits text "
                "files; a binary file has to be rewritten by whatever "
                "produces it"
            ) from exc

    async def _put(self, target: str, resolved: Path, content: str) -> None:
        """Write ``content`` back, locally or through the environment.

        The local path writes a sibling temporary file and
        :func:`os.replace`\\ s it over the target, so a failure part-way
        leaves the original **untouched** rather than truncated. A plain
        ``O_TRUNC`` open empties the file before the first byte is
        written, which turns an ENOSPC into silent data loss — and makes
        :func:`_unwritable`'s "the file is unchanged" a lie at exactly the
        moment somebody is relying on it.

        The target's existing permissions are carried over, since
        :func:`os.replace` installs a new inode and
        :data:`~omicsclaw.tools.builtin.write.FILE_MODE` describes a file
        being *created* rather than one being edited.
        """
        payload = content.encode("utf-8")
        if self._environment is not None:
            try:
                await self._environment.write_file(str(resolved), payload)
            except OSError as exc:
                raise ToolArgumentError(_unwritable(target, exc)) from exc
            return

        scratch: Path | None = None
        try:
            resolved.parent.mkdir(
                mode=DIRECTORY_MODE, parents=True, exist_ok=True
            )
            mode = _mode_of(resolved)
            handle, name = tempfile.mkstemp(
                dir=resolved.parent, prefix=f".{resolved.name}.", suffix=".tmp"
            )
            scratch = Path(name)
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
            os.chmod(scratch, mode)
            os.replace(scratch, resolved)
            scratch = None
        except OSError as exc:
            raise ToolArgumentError(_unwritable(target, exc)) from exc
        finally:
            if scratch is not None:
                # The replace never happened, so the original is intact and
                # the half-written sibling is litter.
                try:
                    scratch.unlink()
                except OSError:
                    pass


# ---- the match ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Change:
    """Where two versions of a file differ, and the rendered hunk.

    A type rather than a tuple because its fields are consumed both in the
    approval prompt and in the result.
    """

    removed: int
    """Lines present in the original and not in the result."""

    added: int
    """Lines present in the result and not in the original."""

    diff: str | None
    """The rendered hunk, or ``None`` past :data:`MAX_SUMMARY_LINES`."""


@dataclass(frozen=True, slots=True)
class EditOutcome:
    """A planned edit: the new text, the level that matched, what changes.

    Built by :func:`plan_edit` before anything is written, so the approval
    prompt and the result describe the same change. Frozen, because a value
    that can be adjusted mid-journey is a value the prompt no longer
    describes.
    """

    content: str
    """The whole file as it will be after the edit."""

    level: int
    """Which of :data:`MATCH_EXACT`..:data:`MATCH_LINE_BY_LINE` won."""

    change: Change
    """The diff between the original and :attr:`content`."""

    stripped_prefix: bool = False
    """Whether a ``read_file`` line-number prefix had to be removed."""

    @property
    def exact(self) -> bool:
        """Whether the written bytes are certainly the ones intended.

        Only L1 with no prefix stripping qualifies. A property rather than
        ``level == MATCH_EXACT`` at four call sites, since prefix stripping is a
        second way to lose exactness.
        """
        return self.level == MATCH_EXACT and not self.stripped_prefix

    @property
    def level_name(self) -> str:
        """The winning level in words, for an approval prompt or a result."""
        name = _LEVEL_NAMES[self.level]
        if self.stripped_prefix:
            return f"{name}, after removing read_file's line numbers"
        return name


_LEVEL_NAMES = {
    MATCH_EXACT: "an exact match",
    MATCH_NEWLINE: "a match ignoring line endings",
    MATCH_TRIMMED: "a match ignoring surrounding whitespace",
    MATCH_LINE_BY_LINE: "a match ignoring indentation",
}


def plan_edit(original: str, source: str, target: str) -> EditOutcome:
    """Work out what ``original`` becomes, without touching the filesystem.

    Pure, which is what lets the approval prompt describe a change that has
    not happened yet.

    Retries the match with ``read_file``'s line-number prefixes stripped, but
    only when nothing was found at any level — an ambiguous anchor is
    ambiguous whether or not it carries line numbers. That ordering is also
    what makes the retry safe on a TSV of ``1<TAB>gene_a`` lines: an anchor
    copied from one matches at L1, so the retry never runs. A match found by
    stripping is reported as fuzzy.

    Raises :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` for an
    anchor that is empty, all whitespace, absent or ambiguous.
    """
    _reject_empty(source)
    try:
        content, level = replace_once(original, source, target)
    except AnchorNotFound:
        stripped = strip_line_numbers(source)
        if stripped is None:
            raise
        # ``target_text`` is stripped too, and only on this path. A model
        # that pasted numbered lines as its anchor pasted them as its
        # replacement about as often, and writing ``   42\tfoo`` into the
        # file is the one outcome nobody wants. Outside this path the
        # replacement is never touched, because a line that really does
        # begin with a number and a tab is ordinary content in a TSV.
        content, level = replace_once(
            original, stripped, strip_line_numbers(target) or target
        )
        return EditOutcome(
            content,
            level,
            describe_change(original, content),
            stripped_prefix=True,
        )
    return EditOutcome(content, level, describe_change(original, content))


class AnchorNotFound(ToolArgumentError):
    """``source_text`` is nowhere in the file, at any match level.

    A subclass of :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` so
    that :func:`plan_edit`'s prefix retry can catch this and nothing else,
    while the model still reads a correctable error.

    Public, with no underscore, because the registry formats an unhandled
    exception as ``tool 'X' raised {type(exc).__name__}`` — a
    leading-underscore name would reach the model as this package's
    internals.
    """


def replace_once(original: str, source: str, target: str) -> tuple[str, int]:
    r"""Apply the four-level cascade, returning ``(new_content, level)``.

    ``edit_file.go:260-309``. Raises :exc:`AnchorNotFound` when no level
    matched and :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` when
    one matched too often.

    L1 replaces using the unmodified ``target`` while L2–L4 use a
    newline-normalised copy: L1 matched the file's real bytes, so its line
    endings are whatever the model sent, whereas L2–L4 have already
    rewritten the file to ``\n``.

    **An ambiguity at L1 is reported; one at L2 or L3 is not.** Those two
    fall through to the next level, so an anchor occurring twice in its
    normalised form can still be resolved by L4 finding one line-window
    match. The uniqueness guard holds at whichever level *wins*, but the
    model is only told which level that was — never that an earlier level
    was ambiguous. That is faithful to ``edit_file.go:280-308`` and it is
    why the tool description promises refusal for an exact multi-match
    specifically rather than for ambiguity in general.
    """
    normalised_target = target.replace("\r\n", "\n")

    count = original.count(source)
    if count == 1:
        return original.replace(source, target, 1), MATCH_EXACT
    if count > 1:
        raise ToolArgumentError(
            f"source_text occurs {count} times in this file, so which one "
            "to edit is ambiguous and nothing was written. Send a longer "
            "source_text with enough surrounding lines to be unique"
        )

    content = original.replace("\r\n", "\n")
    normalised_source = source.replace("\r\n", "\n")
    has_crlf = "\r\n" in original

    if content.count(normalised_source) == 1:
        result = content.replace(normalised_source, normalised_target, 1)
        return _restore(result, has_crlf), MATCH_NEWLINE

    trimmed = normalised_source.strip()
    if trimmed and content.count(trimmed) == 1:
        result = content.replace(trimmed, normalised_target, 1)
        return _restore(result, has_crlf), MATCH_TRIMMED

    result = _line_by_line(content, normalised_source, normalised_target)
    return _restore(result, has_crlf), MATCH_LINE_BY_LINE


def _line_by_line(content: str, source: str, target: str) -> str:
    """L4: match ``source`` against ``content`` a line at a time, ignoring
    indentation, and re-indent ``target`` to where the block actually sat.

    ``edit_file.go:324-382``. Every match is counted before any is used,
    which is what makes "matched in several places" reachable at this level.
    """
    content_lines = content.split("\n")
    source_lines = [line.strip() for line in source.strip().split("\n")]

    # No length guard before the scan, unlike ``edit_file.go:328-330``.
    # ``"".split("\n")`` is ``[""]`` and never empty, and a source longer
    # than the file makes ``range`` empty, so both of its arms land on the
    # same ``AnchorNotFound`` eleven lines below — unreachable code in the
    # shape of a safeguard.
    matches = [
        index
        for index in range(len(content_lines) - len(source_lines) + 1)
        if all(
            content_lines[index + offset].strip() == source_line
            for offset, source_line in enumerate(source_lines)
        )
    ]

    if not matches:
        raise AnchorNotFound(_absent())
    if len(matches) > 1:
        raise ToolArgumentError(
            f"source_text matches {len(matches)} places once indentation "
            "is ignored, so nothing was written. Send a longer "
            "source_text with enough surrounding lines to be unique"
        )

    start = matches[0]
    end = start + len(source_lines)
    base_indent = _leading_whitespace(content_lines[start])
    replacement = _reindent_block(target, base_indent)
    edited = content_lines[:start] + [replacement] + content_lines[end:]
    return "\n".join(edited)


def _restore(content: str, has_crlf: bool) -> str:
    r"""Convert ``\n`` back to ``\r\n`` when the original file used it.

    ``edit_file.go:284-286``. The test is whether the file contained *any*
    CRLF and the action applies to all of it, so a file with mixed endings
    comes back uniformly CRLF — a known cost carried from the reference, and
    the better of two bad outcomes next to leaving one lone ``\n`` behind.
    L1 avoids the question by never normalising.
    """
    if not has_crlf:
        return content
    return content.replace("\n", "\r\n")


def _leading_whitespace(line: str) -> str:
    """The spaces and tabs at the front of ``line``."""
    return line[: len(line) - len(line.lstrip(" \t"))]


def _common_prefix(left: str, right: str) -> str:
    """The longest shared start of two strings.

    Character-wise where the reference is byte-wise; identical in practice,
    since the only strings passed here are ASCII whitespace prefixes.
    """
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return left[:index]


def _reindent_block(target: str, base_indent: str) -> str:
    """Re-hang ``target`` from ``base_indent``, keeping its internal shape.

    The common whitespace prefix of every non-blank line is the block's own
    base; strip that and substitute the file's, so relative indentation
    survives while the block lands at the level of the code around it. Blank
    lines are emitted empty rather than as trailing whitespace.

    What it cannot do is recover relative indentation the model never sent:
    an L4 anchor whose replacement arrived flat is written flat, which is why
    a fuzzy result asks for a re-read.
    """
    lines = target.split("\n")
    common: str | None = None
    for line in lines:
        if not line.strip():
            continue
        lead = _leading_whitespace(line)
        common = lead if common is None else _common_prefix(common, lead)

    shared = common or ""
    return "\n".join(
        "" if not line.strip() else base_indent + _remove_prefix(line, shared)
        for line in lines
    )


def _remove_prefix(line: str, prefix: str) -> str:
    """Drop ``prefix`` from ``line`` if it is there, as ``strings.TrimPrefix``."""
    return line[len(prefix) :] if line.startswith(prefix) else line


def strip_line_numbers(text: str) -> str | None:
    """``text`` without ``read_file``'s line-number prefixes, or ``None``.

    Returns ``None`` unless *every* non-blank line carries a prefix: one line
    in five having a number and a tab describes a TSV, not a pasted
    ``read_file`` response, and stripping it would corrupt data.

    Blank lines are exempt, because
    :func:`~omicsclaw.tools.builtin.read.numbered_line` renders an empty
    source line as a number, a tab and nothing, and a model copying that
    block usually drops the trailing whitespace.
    """
    lines = text.split("\n")
    candidates = [line for line in lines if line.strip()]
    if not candidates:
        return None
    if not all(_LINE_PREFIX.match(line) for line in candidates):
        return None
    return "\n".join(
        _LINE_PREFIX.sub("", line) if line.strip() else line for line in lines
    )


# ---- what the model and the human are told -------------------------------


def describe_change(original: str, new: str) -> Change:
    """The difference between two versions of a file, as a :class:`Change`.

    A common-prefix / common-suffix scan rather than a real diff, because an
    edit is one contiguous replacement — the cascade cannot produce anything
    else. Line endings are normalised first, so a CRLF file does not report
    every line as changed.
    """
    original_lines = _lines(original)
    new_lines = _lines(new)

    start = 0
    while (
        start < len(original_lines)
        and start < len(new_lines)
        and original_lines[start] == new_lines[start]
    ):
        start += 1

    original_end = len(original_lines) - 1
    new_end = len(new_lines) - 1
    while (
        original_end >= start
        and new_end >= start
        and original_lines[original_end] == new_lines[new_end]
    ):
        original_end -= 1
        new_end -= 1

    removed = max(0, original_end - start + 1)
    added = max(0, new_end - start + 1)
    if removed + added > MAX_SUMMARY_LINES:
        return Change(removed, added, None)

    return Change(
        removed,
        added,
        _hunk(original_lines, new_lines, start, original_end, new_end),
    )


def _hunk(
    original_lines: list[str],
    new_lines: list[str],
    start: int,
    original_end: int,
    new_end: int,
) -> str:
    """A unified-diff-shaped hunk with :data:`CONTEXT_LINES` either side."""
    context_start = max(0, start - CONTEXT_LINES)
    context_end = min(len(original_lines) - 1, original_end + CONTEXT_LINES)

    rendered = [f"  {line}" for line in original_lines[context_start:start]]
    rendered += [f"- {line}" for line in original_lines[start : original_end + 1]]
    rendered += [f"+ {line}" for line in new_lines[start : new_end + 1]]
    rendered += [
        f"  {line}"
        for line in original_lines[original_end + 1 : context_end + 1]
    ]
    return "\n".join(rendered)


def _lines(text: str) -> list[str]:
    r"""``text`` as lines, without the empty one a trailing newline produces.

    Drops exactly one empty trailing element, undoing :meth:`str.split`'s
    artefact; ``rstrip("\n")`` would eat a file's meaningful blank last
    lines.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        return lines[:-1]
    return lines


def build_summary(target: str, original: str, outcome: EditOutcome) -> str:
    """The text the model reads after a successful edit.

    Carries the diff so the model need not spend a turn re-reading the file,
    and a trailer saying how far that diff can be trusted: an exact match
    confirms the **bytes** are on disk and explicitly not that the behaviour
    is fixed, while a fuzzy match asks for the indentation to be checked.
    """
    change = outcome.change
    scale = f"{change.removed} lines removed, {change.added} added"
    header = f"Edited {target} ({scale}, {outcome.level_name})"
    if change.diff is None:
        return (
            f"{header}. The change is too large to show as a diff here; "
            "read the file if you need to see it."
        )

    if outcome.exact:
        trailer = (
            "✓ Exact match. The diff above is what is on disk, so there is "
            "no need to read the file again to confirm this edit landed. "
            "That is all it confirms: run the test or the reproduction to "
            "find out whether the behaviour is right."
        )
    else:
        trailer = (
            "⚠️ Fuzzy match: whitespace, line endings or indentation were "
            "tolerated, so the bytes written may differ slightly from what "
            "you sent. Read the edited region back and check the "
            "indentation and surrounding context, especially in an "
            "indentation-sensitive language like Python."
        )
    return f"{header}:\n\n{change.diff}\n---\n{trailer}"


def _unchanged(target: str, outcome: EditOutcome) -> str:
    """The message for an edit whose result equals the current contents.

    The anchor was still required to exist, which is what separates "already
    done" from "never found". Nothing was written, so the modification time
    does not move and whatever watches the file does not rebuild.
    """
    return (
        f"{target} already contains exactly this text, so nothing was "
        f"written ({outcome.level_name}). The file is in the state your "
        "edit asked for."
    )


# ---- module-level helpers ------------------------------------------------


def _arguments(arguments: str) -> tuple[str, str, str]:
    """Decode ``arguments`` into ``(path, source_text, target_text)``.

    Raises :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` when the
    payload does not decode, does not match :data:`EDIT_SCHEMA`, or names no
    path.
    """
    decoded = decode_arguments(arguments)
    issues = validate_arguments(decoded, EDIT_SCHEMA)
    if issues:
        listed = "\n".join(f"  - {issue}" for issue in issues)
        raise ToolArgumentError(
            "the arguments do not match this tool's schema:\n"
            f"{listed}\nRe-send the call with all of these corrected."
        )

    target = str(decoded["path"]).strip()
    if not target:
        raise ToolArgumentError(
            "input.path is required and must name a file; an empty string "
            "names the workspace root, which is a directory"
        )
    return target, str(decoded["source_text"]), str(decoded["target_text"])


def _reject_empty(source: str) -> None:
    """Refuse an anchor with no content, which the reference only half-does.

    An *empty* anchor is a comprehensibility problem: ``str.count("")`` is
    ``len + 1``, so it reaches L1's multi-match branch and the model is told
    to add context to something that has none.

    An *all-whitespace* anchor is a safety problem. ``edit_file.go:292``
    skips L3 for exactly this input and gives the right reason — it would
    match a blank line by mistake — but guards only L3. L4 then splits
    ``strip("   ")`` into ``[""]``, a one-line window matching every blank
    line: ambiguity in a file with several, and a **silently replaced blank
    line** in a file with one.
    """
    if source == "":
        raise ToolArgumentError(
            "input.source_text is empty, which names every position in the "
            "file rather than one passage. Send the existing text to "
            "replace, or use write_file to replace the whole file"
        )
    if not source.strip():
        raise ToolArgumentError(
            "input.source_text is nothing but whitespace, which names "
            "every blank line in the file rather than one passage. Send "
            "the existing text to replace, including the lines around it"
        )


def _mode_of(path: Path) -> int:
    """``path``'s permission bits, or :data:`FILE_MODE` if it has none yet."""
    try:
        return os.stat(path).st_mode & 0o777
    except OSError:
        return FILE_MODE


def _absent() -> str:
    """One wording for "the anchor is not in this file", at any level."""
    return (
        "source_text was not found in this file, even allowing for "
        "differences in line endings, surrounding whitespace and "
        "indentation. Read the file to get the current text — the passage "
        "may already have been edited — and send an anchor copied from it "
        "without read_file's line-number prefix"
    )


def _unreadable(target: str, exc: OSError) -> str:
    """One wording for every failure to read the file being edited.

    Names the "create it first" case explicitly, because
    :exc:`FileNotFoundError` is what a model reaches by using this tool when
    it wanted ``write_file``.
    """
    reason = exc.strerror or type(exc).__name__
    if isinstance(exc, FileNotFoundError):
        return (
            f"cannot edit {target!r}: it does not exist. This tool only "
            "changes a passage of a file that is already there; use "
            "write_file to create one"
        )
    if isinstance(exc, IsADirectoryError):
        return f"cannot edit {target!r}: it is a directory, not a file"
    return f"cannot edit {target!r}: {reason}. Send a different path"


def _unwritable(target: str, exc: OSError) -> str:
    """One wording for every failure to write the edited file back.

    Separate from :func:`_unreadable` because a read failure means the edit
    never started, while a write failure after a successful match means the
    file is unchanged but was editable a moment ago.
    """
    reason = exc.strerror or type(exc).__name__
    return (
        f"matched {target!r} but could not write it back: {reason}. The "
        "file is unchanged"
    )


__all__ = [
    "AnchorNotFound",
    "CONTEXT_LINES",
    "EDIT_SCHEMA",
    "Change",
    "EditOutcome",
    "EditTool",
    "FileEditEnvironment",
    "MATCH_EXACT",
    "MATCH_LINE_BY_LINE",
    "MATCH_NEWLINE",
    "MATCH_TRIMMED",
    "MAX_SUMMARY_LINES",
    "TOOL_NAME",
    "build_summary",
    "describe_change",
    "plan_edit",
    "replace_once",
    "strip_line_numbers",
]
