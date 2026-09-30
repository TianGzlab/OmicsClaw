"""``read_file`` — how the model looks at a file it is allowed to see.

Plan 0029 §4 Q2b, Q9, Q11 and traps 7, 10 and 11. The reference is
harness9's ``internal/tools/read_file.go``; what was taken from it is its
**structure** — two modes, a line-number prefix, and truncation notices
that tell the model what to send next — while every *literal* is
re-derived below under Python semantics, because a number that was true
of ``bufio.Scanner`` is not thereby true of :func:`open`.

**Two modes, and the precedence is deliberate.** ``start_line`` selects
line mode and makes ``offset``/``limit`` inert
(``read_file.go:127-130``); with no ``start_line`` the call is byte mode.
Line mode is the one a model should reach for — a line number is what it
will cite back, and what ``edit`` will be asked about — so byte mode is
documented as the fallback for the files line mode refuses (see
:data:`MAX_LINE_CHARS`) rather than as an equal option.

**The line-number prefix is a cross-tool contract, not decoration.**
``read`` renders ``%6d\\t%s`` (:func:`numbered_line`,
``read_file.go:218``) and ``edit`` — a later step — has to recognise and
strip it, because a model that pastes a line straight back into
``source_text`` pastes the number too. harness9 says so twice, in the
tool description and again in a code comment (``read_file.go:64-67`` and
``215-218``), and the repetition is the point: the two tools ship
separately, and whoever writes ``edit`` will read this file's description
even if they never read plan 0029. Both copies are reproduced here, and
``tests/tools/test_read.py`` pins the format and pins that the warning is
still in the description.

**Trap 7 — a missing file is an error; an empty file is not.** The
criterion is not "did something go wrong", it is **what should the model
change next**. A path that does not resolve to a readable file is
something the model can fix by sending a different ``path``, so it is
raised and the registry turns it into ``is_error=True``. A file that
exists and happens to be empty is a fact about the world with nothing for
the model to correct, so it comes back as ordinary output. Both halves
are pinned, adjacently, in ``tests/tools/test_read.py``. (The other half
of plan 0029's trap 7 — a non-zero exit from ``bash`` being
``is_error=False`` — belongs to the task that delivers ``bash``; the two
could not be put in one file because they ship separately.)

**An** :exc:`OSError` **from the filesystem is rephrased, never leaked.**
``Workspace.resolve`` deliberately does not touch the filesystem for a
non-existent leaf, so a 5,000-character filename resolves cleanly and
then fails at :func:`os.stat` with ``ENAMETOOLONG``. That is correctable
— the model must send a shorter path — so it is caught and reported as a
sentence naming the operating system's own reason, rather than allowed to
reach the model as a bare ``OSError`` traceback fragment.

**Why this one is a** :class:`~omicsclaw.tools.function_tool.FunctionTool`
**and ``write`` is not.** Plan 0029 §5 says all three foundation tools
should be hand-written, and gives one reason: they are ``ASK`` tools, and
an approval prompt has to show the bytes the model actually sent, which
:class:`~omicsclaw.tools.function_tool.FunctionTool` cannot do. That
reason does not apply here, because plan 0029 Q2b makes ``read`` ``AUTO``
— it never asks anyone anything, so it never needs the raw payload. What
it does need is the other half of the adapter: an undecodable payload
reported with a character count and an excerpt (plan 0028 trap 8) and
every schema problem listed at once (trap 9), in wording byte-identical
to the fifty tools already in service. Hand-writing it would mean
re-deriving both, and plan 0028's ``save_gene_panel`` is the recorded
evidence of how that goes: its private copy of ``decode_arguments`` had
already dropped the excerpt, which is why that helper was made public.
(The tool itself was removed with the other two reference tools; the
lesson it paid for is the reason this one is a ``FunctionTool``.)

The five arguments are exactly a Python signature, so
``func(**arguments)`` makes the schema and the code two statements of
one thing.

**The ``Environment`` seam (plan 0029 Q11), at the width that matters.**
Isolation that covers ``bash`` but not the file tools is decoration — a
model wanting out would simply use ``write``. So this tool takes an
``environment`` too, and *uses* it: ``None`` means the local filesystem,
and anything else has its :meth:`FileReadEnvironment.read_file` awaited
instead. harness9 stores the environment on its file tools and never
reads it (``read_file.go:35-37`` is a TODO), which would be dead state
here and is what plan 0029 trap 15 forbids. The Protocol is narrowed to
the one method this tool calls rather than copying harness9's five-method
``sandbox.Environment``: Protocols are structural, so one object
implementing the whole shape satisfies this one and ``write``'s and, in
due course, ``bash``'s — and a test double for ``read`` is not forced to
stub a shell. **No isolated implementation is written here**, per plan
0029 Q11; in particular harness9's ``LocalEnvironment`` is not copied,
for the reason that plan gives.

**Compared against** ``omicsclaw/runtime/tools/builders/engineering.py``
``file_read`` (line 601), which this layer may not import (plan 0028
§9-4). Plan 0029 §6 requires every row to be accounted for:

* ``_validate_file_read_input`` (``engineering.py:44``) rejects
  ``end_line < start_line``. **Kept**, and with a better claim to exist
  than the reference has: harness9 lets that combination through, reads
  nothing, and reports "start_line is past the end of the file", which
  points the model at the wrong argument. Same check, this layer's
  wording.
* The line-number prefix is ``f"{index}: {line}"`` there and ``%6d\\t%s``
  here. **Changed deliberately**, per plan 0029 §6: a tab is one
  separator to strip, while ``": "`` also occurs inside real source
  lines. *What breaks on migration*: anything that parsed the old form,
  and the two header lines the old tool prepended (``File: <path>`` and
  ``Lines: A-B of N``), which are gone — a caller that wants the total
  line count now learns it only when it reads past the end. Nothing in
  this repository parses either; the strings are quoted only in prose
  (``runtime/agent/loop_pathology.py`` keys on the *tool name*, not on
  its output).
* ``max_chars`` (``_bounded_int(..., maximum=100000)``) has no
  counterpart in harness9, which lets a model ask for any number of
  bytes. **Kept** as :data:`MAX_LIMIT_BYTES`; dropping it would be a
  silent capability regression on the one axis this project cares about,
  the context window. It clamps rather than refuses, and the truncation
  notice states the number of bytes actually read, so the model is told.
  Two differences inside the "kept": the old one counts **characters of
  the rendered, numbered output** while ``limit`` counts **bytes of the
  file**, and the old default of 12,000 becomes :data:`MAX_READ_BYTES`.
* **The old tool reports failure as ordinary output** — it returns
  ``"Error: file not found or outside allowed roots: …"`` as the tool's
  result, so the run never sees ``is_error``. This one raises, and the
  registry marks the Observation. That is plan 0029 trap 7, and it is a
  behaviour change the migration has to expect: a model that had learned
  to read the word "Error" out of a successful result will instead get a
  result that says it failed.
* ``_bounded_int`` coerces an unusable argument to a default —
  ``start_line="abc"`` silently becomes 1. Here the schema names the
  argument and the type, because a tool that answers a different question
  than the one it was asked is worse than one that asks again.
* ``start_line``/``end_line`` defaulting to the whole file is **not**
  kept: the old tool reads every line and then truncates a character
  budget, so a 200,000-line file is fully read into memory first. Line
  mode here is bounded before reading, by :data:`MAX_LINES`.
* Multi-root discovery (``_resolve_path_for_read`` tries the workspace,
  the pipeline workspace, the project root and trusted data roots in
  turn) is **not** kept. One workspace, one answer — see
  ``omicsclaw/tools/_workspace.py``, which records the same decision.

**Leaf-adjacent.** ``omicsclaw.tools._pathlock``,
``omicsclaw.tools._workspace``, ``omicsclaw.tools.base``,
``omicsclaw.tools.context``, ``omicsclaw.tools.function_tool``, and the
standard library.
"""

from __future__ import annotations

import os
import stat as stat_flags
from collections.abc import Generator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .._pathlock import read_lock
from .._workspace import WORKSPACE_KEY, Workspace
from ..base import ApprovalMode, RiskLevel, ToolPolicy
from ..context import context_value
from ..function_tool import FunctionTool, ToolArgumentError

TOOL_NAME = "read_file"
"""harness9's name, not this repository's ``file_read``.

Two reasons, and neither is deference. The legacy tool is still mounted in
every surface, so a tool of the same name in a registry that one day holds
both would be refused by
:meth:`~omicsclaw.tools.registry.ToolRegistry.register` — a collision that
would surface as a start-up failure in whichever assembly step wires the
two together. And the semantics differ enough (one workspace instead of
four roots, a different line prefix, no header block) that a shared name
would be the more confusing of the two outcomes.
"""

MAX_READ_BYTES = 8192
"""Default byte-mode window, from ``read_file.go:30``.

**A literal, re-checked rather than inherited.** harness9's comment
records it as a tuning decision — 4,096 was raised to 8,192 because
SWE-bench source files paged too often, and each page costs a whole model
turn. Nothing about that reasoning is Go-specific: the cost being traded
is a round trip against context, and both sides of that trade are the
same here. Roughly 2,000 tokens, which is a readable slice rather than a
context event.
"""

MAX_LIMIT_BYTES = 100_000
"""Largest ``limit`` honoured, whatever the model asks for.

Not from harness9, which has no ceiling at all. It is this repository's
own, carried over from ``engineering.py:630``
(``_bounded_int(..., maximum=100000)``) so that migrating off the old tool
does not quietly remove a guard. Clamped rather than refused: a refusal
costs a turn, while a clamp plus a truncation notice naming the bytes
actually read tells the model the same thing and still returns content.
"""

MAX_LINES = 500
"""Most lines one line-mode call returns, from ``read_file.go:109``.

**A literal, re-checked.** Its comment records 200 being raised to 500 to
cut paging on large files, and the trade — one more turn against more
context — transfers unchanged. 500 lines of ordinary source is on the
order of 6,000 tokens.
"""

MAX_LINE_CHARS = 512 * 1024
"""Longest single line line mode will render (plan 0029 trap 11).

**This one had to be re-decided, not translated.** harness9 gets the
limit for free: ``bufio.Scanner`` is given a 512 KiB buffer
(``read_file.go:200``) and returns ``ErrTooLong`` past it, which
``read_file.go:222-225`` catches and turns into "use byte mode instead".
Python has **no such limit** — ``for line in handle`` will happily
materialise a 2 GiB single-line file — so the naive translation is not
"the same behaviour", it is *no* behaviour, and the failure mode is worse
than the reference's: instead of a clear refusal the process consumes the
file into memory and then into the model's context.

So the guard is implemented rather than inherited, with
:meth:`io.TextIOBase.readline`'s size argument, and the number is kept at
the reference's because its only job is to separate "a line a human
wrote" from "a machine-generated blob", and any threshold in that band
does that. The message is the part that matters and is reproduced in
substance: name byte mode as the way to read the file anyway.

**A residual, stated rather than hidden:** this bounds one line, not the
response. 500 lines just under the cap is a 256 MiB reply, and the
reference has the same hole. Closing it needs a total output budget,
which plan 0029 Q3 gives to ``bash`` and to no other tool, so inventing
one here would be a parameter no plan sanctioned.
"""

LINE_NUMBER_WIDTH = 6
"""Width of the line-number field in :func:`numbered_line`."""


def numbered_line(number: int, text: str) -> str:
    """One rendered line — ``%6d``, a tab, the content, a newline.

    ``read_file.go:218``. **Its exact shape is a contract with ``edit``**,
    which must recognise and strip this prefix when a model pastes a read
    line back as ``source_text``; a function rather than an inline
    f-string so that the next step has one thing to invert and one thing
    to point a test at. Numbers wider than six digits push the field out
    rather than truncating, in both languages.
    """
    return f"{number:{LINE_NUMBER_WIDTH}d}\t{text}\n"


@runtime_checkable
class FileReadEnvironment(Protocol):
    """Where this tool's reads actually land. Injected, never imported.

    Plan 0029 Q11, narrowed to the one method ``read`` calls. An object
    offering harness9's whole five-method ``sandbox.Environment`` shape
    satisfies this structurally, so narrowing costs the assembly layer
    nothing and saves every test double from stubbing a shell it will
    never run.

    The path handed over is the **resolved host path**, which assumes an
    implementation sees the same tree — harness9 makes the same
    assumption explicitly, by bind-mounting the workspace into its
    container (``read_file.go:35-37``).

    The known cost of this signature, stated because a later isolation
    step will meet it: the whole file crosses the seam, so line mode
    cannot stream through an environment the way it streams locally, and
    :data:`MAX_LINE_CHARS` is then enforced after the bytes have already
    arrived. A paging method would fix it; inventing one now, with no
    implementation to shape it, would be guessing.
    """

    async def read_file(self, path: str) -> bytes:
        """The whole file at ``path``, as bytes."""
        ...


_DESCRIPTION = (
    "Read a text file from the session workspace. Prefer LINE MODE: set "
    "start_line, and optionally end_line, both 1-based and inclusive, "
    "for at most 500 lines per call. Every line comes back with a "
    "'<line number><TAB><content>' prefix so you can cite exact lines. "
    "The prefix is display only and not part of the file: when you pass "
    "read text to edit_file as source_text, send it without the line "
    "number and the tab that follows it. BYTE MODE (offset, "
    "limit) is the fallback for files line mode refuses: both are "
    "measured in BYTES, never in line numbers, and at most 8192 bytes "
    "come back by default. Setting start_line selects line mode and "
    "makes offset and limit inert. Paths are relative to the workspace "
    "root, and nothing outside it can be read."
)

READ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": (
                "File to read, relative to the workspace root, e.g. "
                "'results/summary.csv'. Required."
            ),
        },
        "start_line": {
            "type": "integer",
            "description": (
                "First line to read, 1-based and inclusive. Setting this "
                "selects line mode and makes offset/limit inert."
            ),
        },
        "end_line": {
            "type": "integer",
            "description": (
                "Last line to read, 1-based and inclusive. Needs "
                "start_line. Omit to read to the end of the file, capped "
                "at 500 lines."
            ),
        },
        "offset": {
            "type": "integer",
            "description": (
                "Byte-mode starting offset, in BYTES and not in line "
                "numbers. Default 0."
            ),
        },
        "limit": {
            "type": "integer",
            "description": (
                "Byte-mode maximum, in BYTES. Default 8192, clamped to "
                "100000. Inert when start_line is set."
            ),
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}
"""``additionalProperties: false`` on purpose.

:class:`~omicsclaw.tools.function_tool.FunctionTool` calls the wrapped
function with ``**arguments``, so an unexpected key would arrive as a
:exc:`TypeError` from deep inside a call the model cannot see. Declaring
it turns the same mistake into ``input.foo is not allowed``, which the
model can act on.
"""

_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=True,
    concurrency_safe=True,
    allowed_in_background=True,
    tags=frozenset({"workspace", "filesystem", "inspection"}),
)
"""``AUTO`` and ``LOW``, and **declared rather than defaulted** (Q2b).

:class:`~omicsclaw.tools.base.ToolPolicy` defaults to ``HIGH`` + ``ASK``,
and :func:`~omicsclaw.tools.context.require_approval` fails closed when no
approval channel is bound — which today is everywhere. Omitting ``policy``
would therefore ship a read-only tool that cannot read a line, and would
teach every test in this file to pass an override, which is how a habit of
bypassing policy starts.

The asymmetry with ``write`` is the plan's and is deliberate: the question
is not "is this dangerous" but **can this cause something irreversible**.
``read`` cannot. Its boundary is
:class:`~omicsclaw.tools._workspace.Workspace`, which is a real boundary;
an approval prompt in front of it would be friction, not security.

``read_only`` and ``concurrency_safe`` are *claims* in plan 0028's split
and gate nothing today, but both are true here and a true claim is worth
declaring for the assembly layer that will filter on them.
``allowed_in_background`` likewise: an unattended analysis run that cannot
read a file is not an unattended analysis run.
"""


def resolve_workspace(explicit: Workspace | None) -> Workspace:
    """The boundary this call runs inside, or a refusal.

    Two sources, constructor first, because plan 0029 names both and each
    is right for a different caller. A script or a test constructs a
    :class:`~omicsclaw.tools._workspace.Workspace` and hands it over (plan
    0029 §1). A surface binds one under
    :data:`~omicsclaw.tools._workspace.WORKSPACE_KEY` in the
    :class:`~omicsclaw.tools.context.ToolContext` (plan 0029 §5), which is
    also what lets **one** registry serve many concurrent sessions — the
    Channel Surface has Telegram and Feishu conversations interleaving on
    one event loop, and a workspace frozen into a constructor would make
    one of them read the other's files.

    A bound value may be a :class:`~omicsclaw.tools._workspace.Workspace`
    or anything spellable as a path; the second is wrapped, which runs the
    root's own credential check at that point.

    A :exc:`RuntimeError`, deliberately **not** a
    :exc:`~omicsclaw.tools.function_tool.ToolArgumentError`, when there is
    neither: no argument the model can send binds a workspace to a
    session, so promising it a correction would send it round a loop it
    cannot leave.

    **This lives here and ``write`` imports it**, which is the wrong home
    for it: it belongs beside :class:`~omicsclaw.tools._workspace.Workspace`
    in ``_workspace.py``, and a later step should move it there. It is in
    one place rather than two because two implementations of one rule are
    one implementation and one bug — the rule this package already learned
    from ``decode_arguments``.
    """
    if explicit is not None:
        return explicit
    bound = context_value(WORKSPACE_KEY)
    if not bound:
        raise RuntimeError(
            f"no {WORKSPACE_KEY!r} is bound to this session and none was "
            "given to the tool, so there is no workspace to read from; "
            "the surface starting the turn is what binds one"
        )
    if isinstance(bound, Workspace):
        return bound
    return Workspace(Path(str(bound)))


def read_tool(
    workspace: Workspace | None = None,
    *,
    environment: FileReadEnvironment | None = None,
) -> FunctionTool:
    """A configured ``read_file``.

    A factory rather than a class because this tool is a
    :class:`~omicsclaw.tools.function_tool.FunctionTool` — the same
    asymmetry ``builtin/__init__.py`` already documents, where the wrapped
    callables get factories and the hand-written tool gets a constructor.

    ``workspace`` may be omitted, in which case the session's bound one is
    read per call; see :func:`resolve_workspace`. ``environment`` is the
    plan 0029 Q11 seam and defaults to the local filesystem.

    No ``policy`` parameter: a deployment that disagrees with
    :data:`_POLICY` passes its own to
    :meth:`~omicsclaw.tools.registry.ToolRegistry.register`, which is the
    override that plan 0028 Q5 made authoritative and that
    :func:`~omicsclaw.tools.context.require_approval` actually reads. A
    constructor argument would be a second, weaker way to spell it.
    """

    async def run(
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> str:
        return await _read(
            path,
            start_line=start_line,
            end_line=end_line,
            offset=offset,
            limit=limit,
            workspace=workspace,
            environment=environment,
        )

    return FunctionTool(
        TOOL_NAME,
        _DESCRIPTION,
        run,
        parameters=READ_SCHEMA,
        policy=_POLICY,
    )


# ---- the work ------------------------------------------------------------


async def _read(
    path: str,
    *,
    start_line: int | None,
    end_line: int | None,
    offset: int | None,
    limit: int | None,
    workspace: Workspace | None,
    environment: FileReadEnvironment | None,
) -> str:
    """Resolve, lock, then render in whichever mode was asked for.

    The path is resolved **before** the lock is taken, because the lock's
    key has to be the resolved path — two names for one file must be one
    lock, which ``_pathlock`` documents and which
    :meth:`~omicsclaw.tools._workspace.Workspace.resolve` is what supplies.

    A :exc:`~omicsclaw.tools._workspace.PathRefused` is allowed to
    propagate **unwrapped**. Its message already tells the model what to
    send instead, and its class name — ``PathEscapesWorkspace`` versus
    ``PathIsSensitive`` — is what an operator reading the log needs;
    re-raising both as
    :exc:`~omicsclaw.tools.function_tool.ToolArgumentError` would file a
    credential-access attempt under the same heading as a typo. The
    registry reports either as ``is_error=True``, which is the answer the
    model needs in both cases.
    """
    target = _target(path)
    resolved = resolve_workspace(workspace).resolve(target)

    async with read_lock(resolved):
        if start_line is not None:
            return await _by_lines(
                target,
                resolved,
                start_line=start_line,
                end_line=end_line,
                environment=environment,
            )
        if end_line is not None:
            raise ToolArgumentError(
                "input.end_line was given without input.start_line, so "
                "line mode was not selected and end_line would have been "
                "ignored. Send start_line=1 to read from the top of the "
                "file, or drop end_line and use offset/limit for byte mode"
            )
        return await _by_bytes(
            target,
            resolved,
            offset=offset,
            limit=limit,
            environment=environment,
        )


def _target(path: str) -> str:
    """The path argument, checked for the one thing a schema cannot say."""
    target = path.strip()
    if not target:
        raise ToolArgumentError(
            "input.path is required and must name a file; an empty string "
            "names the workspace root, which is a directory"
        )
    return target


async def _by_lines(
    target: str,
    resolved: Path,
    *,
    start_line: int,
    end_line: int | None,
    environment: FileReadEnvironment | None,
) -> str:
    """Lines ``start_line``..``end_line``, numbered, capped at 500.

    Bounds are validated rather than clamped where clamping would hide a
    mistake. harness9 raises ``startLine < 1`` to 1 silently
    (``read_file.go:183-185``) and lets ``end_line < start_line`` through
    to produce "start_line is past the end of the file" — a sentence that
    sends the model to fix the wrong argument. Go cannot do better: its
    JSON decoder cannot tell an omitted integer from a zero. Python can,
    because an omitted argument is ``None``, so a ``0`` or a ``-3`` here
    was really sent and is really a mistake.

    The **width** of the window is clamped rather than refused, matching
    ``read_file.go:187-189``: asking for 10,000 lines is a reasonable
    request that this tool answers 500 at a time, and the truncation
    suffix says where to resume.
    """
    if start_line < 1:
        raise ToolArgumentError(
            f"input.start_line must be 1 or greater, because line numbers "
            f"are 1-based; got {start_line}"
        )
    if end_line is not None and end_line < start_line:
        raise ToolArgumentError(
            f"input.end_line must be greater than or equal to "
            f"input.start_line; got start_line={start_line}, "
            f"end_line={end_line}"
        )
    last = start_line + MAX_LINES - 1
    if end_line is None or end_line > last:
        end_line = last

    source = await _lines(target, resolved, environment)
    rendered: list[str] = []
    seen = 0
    truncated = False
    try:
        for text in source:
            seen += 1
            if seen < start_line:
                continue
            if seen > end_line:
                truncated = True
                break
            rendered.append(numbered_line(seen, text))
    finally:
        source.close()

    if not rendered:
        # Counting what was rendered, rather than asking whether the
        # buffer is empty. ``read_file.go:229-231`` reasons that an empty
        # buffer can only mean "start_line past the end", since a blank
        # line still writes its prefix and a newline — and that argument
        # *does* hold in Python, for the same reason and with the same
        # prefix. It holds only as long as the prefix is non-empty,
        # though, which couples an emptiness test to
        # :func:`numbered_line`; counting costs nothing and needs no
        # invariant.
        return (
            f"[start_line={start_line} is past the end of {target}, which "
            f"has {seen} lines]"
        )

    body = "".join(rendered)
    if not truncated:
        return body
    return body + (
        f"\n...[Read lines {start_line}-{end_line} of {target}. To "
        f"continue, call again with start_line={end_line + 1}.]..."
    )


async def _by_bytes(
    target: str,
    resolved: Path,
    *,
    offset: int | None,
    limit: int | None,
    environment: FileReadEnvironment | None,
) -> str:
    """A byte window, decoded, with a notice saying where to resume.

    One byte more than ``limit`` is requested so that "the file ended
    exactly here" and "there is more" are distinguishable without a second
    call — ``read_file.go:160-166``.

    Decoding uses ``errors="replace"``, which is also the answer to plan
    0029 Q3's warning about UTF-8 boundaries: a window that ends mid
    character yields one replacement character, and the loop Go needs to
    trim a partial rune has no Python equivalent to translate.
    """
    if offset is None:
        offset = 0
    elif offset < 0:
        raise ToolArgumentError(
            f"input.offset must be 0 or greater; got {offset}. It is a "
            "byte offset into the file, not a line number"
        )
    if limit is None:
        limit = MAX_READ_BYTES
    elif limit < 1:
        raise ToolArgumentError(
            f"input.limit must be 1 or greater; got {limit}. It is a "
            "count of bytes, not a line number"
        )
    limit = min(limit, MAX_LIMIT_BYTES)

    window, total = await _window(target, resolved, environment, offset, limit)
    if offset > 0 and offset >= total:
        return (
            f"[offset={offset} is past the end of {target}, which is "
            f"{total} bytes; nothing to read]"
        )
    if len(window) <= limit:
        return window.decode("utf-8", errors="replace")
    return window[:limit].decode("utf-8", errors="replace") + (
        f"\n\n...[Truncated. offset and limit are measured in BYTES, not "
        f"line numbers. {limit} bytes were read from offset={offset}; "
        f"{target} is {total} bytes. To continue, call again with "
        f"offset={offset + limit}. Line mode (start_line/end_line) is "
        f"usually easier to read.]..."
    )


# ---- reaching the bytes --------------------------------------------------


async def _lines(
    target: str,
    resolved: Path,
    environment: FileReadEnvironment | None,
) -> Generator[str, None, None]:
    """A generator over the file's lines, from wherever it lives.

    Two sources, one shape. Locally the file is streamed with a bounded
    :meth:`io.TextIOBase.readline`, so a pathological line is refused
    before it is in memory. Through an environment the bytes have already
    all arrived, so the cap is applied afterwards — the limitation
    :class:`FileReadEnvironment` states.
    """
    if environment is None:
        _require_readable_file(target, resolved)
        return _local_lines(target, resolved)
    return _text_lines(_decode(await _fetch(target, resolved, environment)))


def _local_lines(target: str, resolved: Path) -> Generator[str, None, None]:
    """Stream lines, refusing any line longer than :data:`MAX_LINE_CHARS`.

    Universal newlines are left **on** (the default), so ``\\r\\n`` and a
    lone ``\\r`` both arrive as ``\\n``. That matches Go's
    ``bufio.ScanLines``, which also drops a trailing ``\\r``, and it
    removes the one place a size-bounded ``readline`` could split a
    ``\\r\\n`` pair across two calls and invent a blank line. The
    consequence for ``edit`` is the reference's too: text read from a CRLF
    file comes back with LF endings, which is precisely why harness9's
    ``edit`` has a newline-normalising fallback level.

    ``except OSError`` only, so that a stat which succeeded and an
    :func:`open` which then did not — an unreadable mode, a file deleted
    in between — still reaches the model as the sentence
    :func:`_unreadable` builds. :exc:`asyncio.CancelledError` is not an
    :exc:`OSError` and is not caught here (plan 0029 trap 5).
    """
    try:
        with open(resolved, encoding="utf-8", errors="replace") as handle:
            while True:
                chunk = handle.readline(MAX_LINE_CHARS + 1)
                if not chunk:
                    return
                if len(chunk) > MAX_LINE_CHARS and not chunk.endswith("\n"):
                    raise ToolArgumentError(_LONG_LINE)
                yield chunk[:-1] if chunk.endswith("\n") else chunk
    except OSError as exc:
        raise ToolArgumentError(_unreadable(target, exc)) from exc


def _text_lines(text: str) -> Generator[str, None, None]:
    """The same split as :func:`_local_lines`, over text already in hand.

    ``str.splitlines`` is **not** used: it also breaks on form feed, on
    ``\\x0b`` and on ``\\u2028``, none of which universal-newline mode
    treats as a line ending, and the two sources disagreeing about what a
    line is would make a file read through an environment number
    differently from the same file read locally.
    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalised.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line in lines:
        if len(line) > MAX_LINE_CHARS:
            raise ToolArgumentError(_LONG_LINE)
        yield line


async def _window(
    target: str,
    resolved: Path,
    environment: FileReadEnvironment | None,
    offset: int,
    limit: int,
) -> tuple[bytes, int]:
    """``(bytes read, total size)`` — one extra byte, to detect "more"."""
    if environment is not None:
        payload = await _fetch(target, resolved, environment)
        return payload[offset : offset + limit + 1], len(payload)
    status = _require_readable_file(target, resolved)
    try:
        with open(resolved, "rb") as handle:
            if offset:
                handle.seek(offset)
            return handle.read(limit + 1), status.st_size
    except OSError as exc:
        raise ToolArgumentError(_unreadable(target, exc)) from exc


async def _fetch(
    target: str,
    resolved: Path,
    environment: FileReadEnvironment,
) -> bytes:
    """Read through the injected environment, rephrasing its I/O errors.

    ``except OSError``, never ``except Exception`` and never
    ``BaseException`` (plan 0029 trap 5): an
    :exc:`asyncio.CancelledError` raised while this await is pending is
    the engine's per-tool deadline firing, not the environment's opinion
    about the file, and turning it into an Observation would tell a model
    to fix a file that is fine.
    """
    try:
        return await environment.read_file(str(resolved))
    except OSError as exc:
        raise ToolArgumentError(_unreadable(target, exc)) from exc


def _require_readable_file(target: str, resolved: Path) -> os.stat_result:
    """Stat it, and turn every way that fails into a correctable sentence.

    :func:`os.stat` rather than :meth:`~pathlib.Path.is_file`, which
    collapses "no such file", "that is a directory" and "the name is
    longer than this filesystem allows" into one ``False`` — and, on this
    Python, does not even do that consistently. ``errno`` is what
    distinguishes them, and the operating system's own ``strerror`` is a
    better sentence than any this module would invent.
    """
    try:
        status = os.stat(resolved)
    except OSError as exc:
        raise ToolArgumentError(_unreadable(target, exc)) from exc
    if stat_flags.S_ISDIR(status.st_mode):
        raise ToolArgumentError(
            f"{target!r} is a directory, not a file; send the path of a "
            "file inside it"
        )
    return status


def _decode(payload: bytes) -> str:
    """Bytes as text, never raising on the ones that are not."""
    return payload.decode("utf-8", errors="replace")


def _unreadable(target: str, exc: OSError) -> str:
    """One wording for every I/O refusal, and it has to be actionable.

    The case that made this its own function is the one plan 0029 leaves
    to this task: ``Workspace.resolve`` accepts a 5,000-character name
    because :meth:`~pathlib.Path.resolve` does not touch the filesystem,
    and the failure lands here as ``ENAMETOOLONG``. Reported as
    ``OSError: [Errno 36] File name too long: '/…/aaaa…'`` it reads as a
    machine fault; reported as below it names the argument to change.
    """
    reason = exc.strerror or type(exc).__name__
    return (
        f"cannot read {target!r}: {reason}. Send the path of an existing "
        "file inside the workspace"
    )


_LONG_LINE = (
    f"line mode cannot render this file: it contains a line longer than "
    f"{MAX_LINE_CHARS} characters, which is machine-generated rather than "
    "source. Call this tool again with offset and limit to read it in "
    "byte mode instead"
)
"""Plan 0029 trap 11: a specific instruction, not a generic failure.

``read_file.go:222-225`` makes the same point — the model has to be told
*which other mode* works, or it retries the one that cannot.
"""


__all__ = [
    "FileReadEnvironment",
    "LINE_NUMBER_WIDTH",
    "MAX_LIMIT_BYTES",
    "MAX_LINES",
    "MAX_LINE_CHARS",
    "MAX_READ_BYTES",
    "READ_SCHEMA",
    "TOOL_NAME",
    "numbered_line",
    "read_tool",
    "resolve_workspace",
]
