"""``write_file`` — the first tool in this layer that can destroy something.

Plan 0029 §4 Q2, Q11 and traps 3, 5, 7 and 12. The reference is
harness9's ``internal/tools/write_file.go``, whose whole design is three
sentences in its package comment (``write_file.go:3-9``) and all three
are kept: the path goes through the sandbox boundary, missing parent
directories are created, and an existing file is **replaced**.

**Overwrite semantics are a fact the model has to be told** (plan 0029
trap 12). ``write_file.go:8-9`` says it and says why: the behaviour
matches :func:`os.WriteFile`, there is no append and no merge, and
deciding whether to read the file first is the *model's* job because the
tool will not do it. That sentence is in :data:`_DESCRIPTION` for the
model and in :meth:`WriteTool._reason` for the human, and the second is
the one that changes an approval prompt from "may I write a file" into
"may I replace the 4,000 bytes currently at this path".

**Hand-written against the** :class:`~omicsclaw.tools.base.Tool`
**Protocol, and the reason is the approval prompt** (plan 0029 §5, plan
0028 §11). :class:`~omicsclaw.tools.function_tool.FunctionTool` calls its
function with decoded keyword arguments, so a function wrapped by it can
only show a human something re-encoded from what survived decoding — key
order, spacing and any field the schema did not mention are gone, and
those are exactly the differences a person reviewing a destructive call
is looking at. ``execute`` here is handed the payload unparsed and hands
that same string to
:func:`~omicsclaw.tools.context.require_approval`. This and ``bash`` are
the "some tools must be hand-written" set: both ask a human, so both need
the bytes the model actually sent rather than the arguments a decoder
reconstructed from them.

**Order of operations, which is the design.** Decode, validate, resolve,
**ask**, then write. Nothing before the approval touches the filesystem
in a way that survives — resolution reads, it does not create — so a
refusal at any point leaves no file behind. Resolving *before* asking is
not an optimisation either: it is what lets the prompt name the real path
the bytes will land at rather than the string the model chose, which for
a path containing a symlink are different places.

**Trap 3 is this file's to carry, and the helper layer cannot carry it.**
:meth:`~omicsclaw.tools._workspace.Workspace.resolve` follows symlinks,
so a link inside the workspace pointing at ``/tmp`` resolves to ``/tmp``
and is refused — but nothing in that helper can force *this* module to
call it before :meth:`~pathlib.Path.mkdir`, and ``mkdir(parents=True)``
on an unresolved path would create directories out in ``/tmp`` before any
check ran. So the test that matters is not "the tool returned an error";
it is **"the external directory is still empty"**, and
``tests/tools/test_write.py`` asserts that.

**Trap 7 — the criterion is what the model should change next.** Every
failure this tool produces is correctable by sending different arguments:
a path outside the workspace, a directory where a file was meant, a name
longer than the filesystem allows. All of them raise, and
:meth:`~omicsclaw.tools.registry.ToolRegistry.execute` turns each into
``is_error=True`` so the model reads the reason and retries differently.
A denied approval is the one refusal that is *not* correctable by new
arguments, and it says so in its own words — it comes from
:exc:`~omicsclaw.tools.context.ApprovalDenied`, not from here.

**Trap 5 — cancellation is not a failure to report.** Every ``except`` in
this module names :exc:`OSError`. The engine's per-tool deadline arrives
as :exc:`asyncio.CancelledError`, which is a :exc:`BaseException`, and it
must pass through untouched: a human still deciding when the budget
expires (a collision ``omicsclaw/tools/context.py`` documents in full)
must not be reported to the model as a broken tool.

**The ``Environment`` seam (plan 0029 Q11).** ``environment=None`` means
the local filesystem. The width of that seam is the point of the
decision: if only ``bash`` ran under isolation while ``write`` wrote
straight to the host, the isolation would be decoration a model could
step around by choosing the other tool. So this tool takes one too and
uses it. :class:`FileWriteEnvironment` states the contract that harness9's
own interface leaves implicit — an implementation must create parent
directories itself, because ``sandbox.Environment`` has no ``mkdir`` and
the auto-mkdir promise in the tool description does not stop being made
when a call is routed.

**Compared against** ``omicsclaw/runtime/tools/builders/engineering.py``
``file_write`` (line 772), which this layer may not import. Plan 0029 §6
requires every row to be accounted for:

* Auto-mkdir: both do it. The old tool exposes it as a ``create_dirs``
  argument defaulting to ``true``; that argument is **dropped**, matching
  harness9, because its ``false`` branch only turns a working write into
  "Error: parent directory does not exist" — a refusal the model answers
  by setting the flag it should not have had to think about.
* Return text: ``"Wrote file: {target}"`` there, a byte count and the
  created/overwrote distinction here. The old form cannot tell a model
  whether it just destroyed something.
* Multi-root discovery (``_resolve_path_for_write`` falls back to
  ``allowed_roots[0]``) is **not** kept, for the reason
  ``_workspace.py`` gives about ``resolve_dest``: writing somewhere other
  than where the model asked is how it learns that an escape attempt
  worked.
* Encoding: both write UTF-8 text. The old tool uses
  :meth:`~pathlib.Path.write_text` with default permissions; this one
  opens with :data:`FILE_MODE` explicitly, matching
  ``write_file.go:113``.
* No path locking there, and no equivalent anywhere in the old layer
  except the serial barrier in ``runtime/tools/orchestration.py`` that
  the new engine does not have — see ``omicsclaw/tools/_pathlock.py``.
* **The old tool reports failure as ordinary output** (``"Error: cannot
  write outside allowed roots: …"``), so a refused write reaches the run
  as a success. This one raises and the registry marks ``is_error``.
* **No approval in practice.** The old layer has the machinery —
  ``ToolSpec.approval_mode`` and ``orchestration.py``'s policy decision —
  but ``file_write``'s spec leaves ``approval_mode`` at its ``auto``
  default and declares only ``risk_level=medium`` plus a speculative
  classifier, so the whole-workspace write runs unattended. Here the ask
  is in ``execute``, before the bytes, and is not optional.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools._pathlock``,
``omicsclaw.tools._workspace``, ``omicsclaw.tools.base``,
``omicsclaw.tools.context``, ``omicsclaw.tools.function_tool``,
``omicsclaw.tools.builtin.read``, and the standard library.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from omicsclaw.schema import ToolDefinition

from .._pathlock import write_lock
from .._workspace import Workspace
from ..base import ApprovalMode, RiskLevel, ToolPolicy
from ..context import report_progress, require_approval
from ..function_tool import ToolArgumentError, decode_arguments, validate_arguments
from .read import resolve_workspace

TOOL_NAME = "write_file"
"""harness9's name rather than this repository's ``file_write``.

Same reasoning as ``builtin/read.py``: the legacy tool is still mounted
everywhere, and two tools of one name in one registry is a start-up
failure rather than a merge.
"""

DIRECTORY_MODE = 0o755
"""Mode for directories created on the way to the file.

``write_file.go:108``. **A literal, re-checked.** ``0755`` means the
owner may write and everyone may traverse, which is what a workspace
directory needs, and the umask applies in Python exactly as it does in
Go. One real difference, stated rather than worked around:
:meth:`~pathlib.Path.mkdir` applies ``mode`` to the **final** directory
only and creates intermediate parents with the default ``0o777`` masked
by the umask, while ``os.MkdirAll`` applies its mode to every directory
it creates. Under the ordinary ``022`` umask both land on ``0755``;
under a permissive umask they differ. Matching exactly would mean
re-implementing ``mkdir -p`` one component at a time, for a difference no
deployment of this project has.
"""

FILE_MODE = 0o644
"""Mode for a file this tool creates.

``write_file.go:113``. **A literal, re-checked**, and it needed
implementing rather than translating: :meth:`~pathlib.Path.write_text`
has no mode argument and creates with ``0o666`` masked by the umask, so
the explicit ``os.open`` below is what makes the reference's ``0644``
true here. Like ``os.WriteFile``, the mode applies only when the file is
*created* — overwriting leaves an existing file's permissions alone.
"""


@runtime_checkable
class FileWriteEnvironment(Protocol):
    """Where this tool's writes actually land. Injected, never imported.

    Plan 0029 Q11, narrowed to the one method ``write`` calls, for the
    reason :class:`~omicsclaw.tools.builtin.read.FileReadEnvironment`
    gives: Protocols are structural, so an object offering harness9's
    whole five-method ``sandbox.Environment`` shape satisfies this one,
    ``read``'s, and in due course ``bash``'s, while a test double for
    ``write`` is not made to stub a shell.

    **An implementation must create missing parent directories.** The
    tool's description promises it, and ``sandbox.Environment`` has no
    ``mkdir`` for the caller to use — a gap harness9 never hit because its
    file tools hold an environment and never route through it.
    """

    async def write_file(self, path: str, data: bytes) -> None:
        """Replace the contents of ``path`` with ``data``."""
        ...


_DESCRIPTION = (
    "Create a file, or completely replace one that already exists, "
    "inside the session workspace. Missing parent directories are "
    "created automatically. OVERWRITE SEMANTICS: if the path exists, its "
    "entire contents are replaced. There is no append, no merge and no "
    "backup, and the old contents are gone. Deciding whether to read the "
    "file first is up to you; this tool will not check. Send the WHOLE "
    "file in `content`, never a fragment or a diff. Paths are relative "
    "to the workspace root, and nothing outside it can be written. "
    "Depending on the session's permission settings, the user may be asked "
    "to approve the write first; a declined write returns an error and the "
    "file is untouched."
)

WRITE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": (
                "File to write, relative to the workspace root, e.g. "
                "'results/summary.csv'. Required."
            ),
        },
        "content": {
            "type": "string",
            "description": (
                "The complete contents of the file. Required; send an "
                "empty string to write an empty file."
            ),
        },
    },
    "required": ["path", "content"],
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
"""``ASK`` and ``HIGH``, **declared rather than defaulted** (plan 0029 Q2).

Leaving ``policy`` off would land on the same two values by accident, and
that is the reason to write them down: a guarded default nobody chose and
a guarded default somebody chose are indistinguishable at the call site
and completely different when the next person relaxes the default.

``HIGH`` because the blast radius decides it, not the verb. A tool that
writes one JSON file into one subdirectory under a name matched against a
single-component pattern would be ``MEDIUM`` doing the same verb; this
one writes **any path in the workspace**, including source files,
including a config the next run reads.

``concurrency_safe=False`` is the honest claim — two calls naming one
path in one turn is a lost update — and it is also, today, a claim
nothing reads (plan 0028 §11 debt #1). The write lock in
:meth:`WriteTool.execute` is what actually prevents the race;
the flag is what an assembly layer will one day filter on.

**This tool is inert until some surface binds an approval channel**, and
that is plan 0029 Q2's accepted cost rather than a defect:
:func:`~omicsclaw.tools.context.require_approval` fails closed, and
nothing in production binds a channel yet. A deployment that wants it
running unattended passes its own policy to
:meth:`~omicsclaw.tools.registry.ToolRegistry.register` — an action
somebody has to take deliberately, which is the whole point.
"""


class WriteTool:
    """Create or replace a file inside the session's workspace.

    Satisfies :class:`~omicsclaw.tools.base.Tool` structurally: it
    subclasses nothing and the Protocol is never imported here.

    ``workspace`` may be omitted, in which case the session's bound one is
    read per call — see
    :func:`~omicsclaw.tools.builtin.read.resolve_workspace`, which is
    shared with ``read`` rather than written twice.

    ``policy`` is a plain attribute, which is all
    :meth:`~omicsclaw.tools.registry.ToolRegistry.policy_for` looks for.
    There is no ``policy`` constructor argument: ``register(policy=)`` is
    the override plan 0028 Q5 made authoritative and the one
    :func:`~omicsclaw.tools.context.require_approval` actually reads, and
    a second spelling would be a weaker way to say the same thing in a
    place an operator would not look.
    """

    policy = _POLICY

    def __init__(
        self,
        workspace: Workspace | None = None,
        *,
        environment: FileWriteEnvironment | None = None,
    ) -> None:
        self._workspace = workspace
        self._environment = environment
        self._definition = ToolDefinition(
            name=TOOL_NAME,
            description=_DESCRIPTION,
            input_schema=copy.deepcopy(WRITE_SCHEMA),
        )

    @property
    def name(self) -> str:
        return TOOL_NAME

    def definition(self) -> ToolDefinition:
        """Built once and returned unchanged, so the prompt prefix is stable.

        Deep-copied from :data:`WRITE_SCHEMA` so two instances — one per
        registry — cannot share the nested ``properties`` mapping.
        """
        return self._definition

    async def execute(self, arguments: str) -> str:
        """Decode, resolve, **ask**, then write. The order is the design.

        ``arguments`` reaches
        :func:`~omicsclaw.tools.context.require_approval` unparsed, which
        is why this class exists rather than a
        :class:`~omicsclaw.tools.function_tool.FunctionTool`.

        The write lock is taken **after** approval rather than around the
        whole method on purpose: a human's thinking time is unbounded, and
        holding an exclusive lock on a path for the length of a
        conversation would stall every other tool touching it — including
        the ``read`` the user is looking at while deciding. What the lock
        has to cover is the read-modify-write, which is the ``mkdir`` and
        the replacement.
        """
        target, content = _arguments(arguments)
        resolved = resolve_workspace(self._workspace).resolve(target)
        payload = content.encode("utf-8")

        await require_approval(
            self.name,
            arguments,
            policy=self.policy,
            reason=self._reason(resolved, payload),
        )
        await report_progress(
            f"writing {len(payload)} bytes to {resolved}",
            tool_name=self.name,
        )

        async with write_lock(resolved):
            # Asked again inside the lock, because the answer given to the
            # human was true when they were asked and this one is true
            # when the bytes land. They differ when something else created
            # or removed the file while the prompt was open.
            replaced = _exists(resolved)
            await self._put(target, resolved, payload)

        verb = "Replaced" if replaced else "Wrote"
        return f"{verb} {resolved} with {len(payload)} bytes"

    # ---- internals ------------------------------------------------------

    def _reason(self, resolved: Path, payload: bytes) -> str:
        """What the human is told they are approving.

        Names the **resolved** path, not the model's string, so a person
        approving a write to ``data/../../out.txt`` sees where it lands.
        Says "replace" and the size of what is there when something is
        there, because that is the fact that turns a routine write into a
        decision.
        """
        if not _exists(resolved):
            return f"create {resolved} and write {len(payload)} bytes"
        existing = _size(resolved)
        return (
            f"REPLACE the existing {resolved} ({existing} bytes) with "
            f"{len(payload)} bytes; its current contents are not recoverable"
        )

    async def _put(self, target: str, resolved: Path, payload: bytes) -> None:
        """Put the bytes where they go, locally or through the environment.

        ``except OSError``, never ``except Exception``: the errors worth
        rephrasing are the filesystem's, and everything else — a
        cancellation above all — belongs to whoever raised it.
        """
        if self._environment is not None:
            try:
                await self._environment.write_file(str(resolved), payload)
            except OSError as exc:
                raise ToolArgumentError(_unwritable(target, exc)) from exc
            return

        try:
            resolved.parent.mkdir(
                mode=DIRECTORY_MODE, parents=True, exist_ok=True
            )
            # ``os.open`` rather than ``write_text`` so :data:`FILE_MODE`
            # is really applied; ``fdopen`` rather than ``os.write`` so a
            # short write is retried rather than silently truncating the
            # file to whatever one syscall accepted.
            descriptor = os.open(
                resolved,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                FILE_MODE,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
        except OSError as exc:
            raise ToolArgumentError(_unwritable(target, exc)) from exc


# ---- module-level helpers ------------------------------------------------


def _arguments(arguments: str) -> tuple[str, str]:
    """The payload as ``(path, content)``, or a complaint.

    Three layers, narrowing: the payload must decode to an object, the
    object must match :data:`WRITE_SCHEMA`, and the path must name
    something. Only the third is beyond a schema.

    :func:`~omicsclaw.tools.function_tool.decode_arguments` is shared
    rather than re-written: it is the only decoder in this package that
    reports *where* a truncated payload stopped, and a hand-written copy
    has already been observed losing exactly that (see its docstring).
    """
    decoded = decode_arguments(arguments)
    issues = validate_arguments(decoded, WRITE_SCHEMA)
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
    return target, str(decoded["content"])


def _exists(path: Path) -> bool:
    """Whether ``path`` is there, without raising on the odd ones.

    :meth:`~pathlib.Path.exists` and :meth:`~pathlib.Path.is_file` do not
    agree across Python versions about whether a name too long for the
    filesystem is "does not exist" or an :exc:`OSError`. Here the question
    is only ever asked to choose a verb, so every failure to answer it is
    "no" and the real refusal comes later, from the write itself, with the
    operating system's own reason attached.
    """
    try:
        os.stat(path)
    except OSError:
        return False
    return True


def _size(path: Path) -> int:
    """Bytes currently at ``path``, or ``0`` when that cannot be read."""
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def _unwritable(target: str, exc: OSError) -> str:
    """One wording for every I/O refusal, and it has to be actionable.

    The case plan 0029 leaves to this task: a 5,000-character name passes
    :meth:`~omicsclaw.tools._workspace.Workspace.resolve`, because
    :meth:`~pathlib.Path.resolve` does not touch the filesystem, and fails
    here with ``ENAMETOOLONG``. As a bare
    ``OSError: [Errno 36] File name too long`` that reads as a machine
    fault; as the sentence below it names the argument to change.
    """
    reason = exc.strerror or type(exc).__name__
    return (
        f"cannot write {target!r}: {reason}. Send a different path inside "
        "the workspace"
    )


__all__ = [
    "DIRECTORY_MODE",
    "FILE_MODE",
    "FileWriteEnvironment",
    "TOOL_NAME",
    "WRITE_SCHEMA",
    "WriteTool",
]
