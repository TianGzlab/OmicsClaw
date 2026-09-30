"""The sandbox boundary ``read``, ``write``, ``edit`` and ``bash`` share.

Plan 0029 §3 and §4 Q1/Q8/Q10. One question is answered here, once: **a
model sent a path — which real file, if any, is that?** Every tool that
touches the filesystem asks it, and a tool that answers it for itself is
a tool that answers it slightly differently, which is how one of four
tools ends up being the one that can be talked out of the workspace.

The attack this exists to stop is one line long::

    workspace = /home/alice/run-7
    the model sends "../../../etc/passwd"

and the defence is that :meth:`Workspace.resolve` is the only way in. It
applies three rules to every path, in this order:

1. **Resolve it** — ``..`` normalised *and symlinks followed*, so what is
   judged is the file that will actually be opened rather than the name
   the model chose for it.
2. **Refuse credentials outright** — :func:`is_sensitive`, applied to the
   resolved path, and applied whether or not the path is inside the
   workspace. A workspace containing an SSH key does not make the key
   readable.
3. **Require containment** — the resolved path must be the workspace root
   or live under it.

Rules 2 and 3 are in that order on purpose, and it is the one ordering
difference from the reference implementation. ``<workspace>/creds`` that
turns out to be a symlink into ``~/.ssh`` fails both rules; reporting it
as "outside the workspace" would file a credential-access attempt under
the same heading as a model that mistyped a relative path. The operator
reading the log needs those to look different, so the sharper rule
answers first.

**What came from harness9, and in what form.**
``internal/tools/safe_path.go`` is the reference. Its *structure* is kept
whole — one shared resolver, a hard credential list that the workspace
whitelist cannot override, and a containment check that cannot be fooled
by a shared name prefix. Two of its *literals* are deliberately not
translated, because both are artefacts of Go's standard library rather
than of the problem:

*The separate branch for absolute input* (``safe_path.go:72-87``) exists
because ``filepath.Join(workDir, "/abs")`` yields ``/workDir/abs`` — Go's
``Join`` does not treat a rooted second argument as rooted, so an
absolute path that was already inside the workspace came back doubled,
passed the prefix check, and named a file that does not exist. Python's
``/`` operator has the opposite convention: ``Path("/ws") / "/etc/passwd"``
is ``/etc/passwd``, not ``/ws/etc/passwd``. So the branch would be a
branch whose two arms compute the same value, and translating it would
add an untestable line while the behaviour it protects — an absolute path
is never concatenated onto the root — is already free. The behaviour is
what is pinned, by
``test_an_absolute_path_inside_the_workspace_is_returned_undoubled``.

*The ``strings.HasPrefix(abs, workDir + os.PathSeparator)`` comparison*
(``safe_path.go:90-92``) is the same rule as :meth:`Path.is_relative_to`,
which compares path components and therefore cannot be tricked by
``/project-evil`` beginning with ``/project``. Keeping the string form in
Python would mean re-deriving the separator handling that pathlib already
gets right. The trap is kept as a test — swap :func:`_is_within` for a
``str.startswith`` and
``test_a_sibling_sharing_the_workspaces_name_is_not_inside_it``
goes red.

**Three ways this is stricter than harness9.**

*Symlinks are resolved* (plan 0029 §4 Q10). ``safePath`` uses
``filepath.Abs``, which normalises ``..`` lexically and follows nothing,
so a symlink planted inside the workspace and pointing anywhere at all
passes its check. :meth:`Path.resolve` follows links, so it does not.
**This is a net improvement and not an alignment defect** — written down
here because the obvious way to "match the reference" later is to swap in
``os.path.abspath``, which would silently reopen the hole.
``strict=False`` is the default and is wanted: ``write`` names files that
do not exist yet, and a non-existent *leaf* is fine, while a symlinked
*parent* is resolved and caught before anything is created.

*The credential list is not anchored to a home directory.* harness9 builds
``~/.ssh``, ``~/.aws`` and the rest from ``os.UserHomeDir`` and returns an
**empty list** when that fails (``safe_path.go:27-29``), on the grounds
that bash's DangerHook is the backstop. This project has no DangerHook,
so an empty list would be a silent total loss of the rule. Rather than
handling the failure, the dependency is removed: a path is credential-ish
because of the components in it, not because of where the current user's
home happens to be. That is strictly broader than the anchored form — it
also catches a second user's home, a copied ``.aws`` inside the workspace
and a container image with no ``HOME`` set — and it makes the "cannot find
home" branch unreachable rather than dangerous.

*The list is re-derived for this project.* ``~/.kube`` stays because it
costs nothing, and ``.env`` is added because it is where **this**
repository keeps ``LLM_API_KEY``, ``TELEGRAM_BOT_TOKEN`` and
``FEISHU_APP_SECRET`` (see ``.env.example``). An omics agent
that can read one ``.env`` can impersonate the bot it is running as.

**Compared against** ``omicsclaw/services/path_validation.py``, which does
this job for the layer being replaced and which this layer may not import
(plan 0028 §9-4 — ``tests/tools/test_tools_is_a_leaf_layer.py`` enforces
it, whitelist, AST, dynamic-import and behaviour probes). Its
``validate_path(filepath, allowed_root)`` is the overlapping half, and on
the overlap the two **agree exactly**: both resolve each side before
comparing, both compare by component so a shared name prefix is not
containment, both accept the root itself, both accept a path that does
not exist yet, and both refuse a path containing a NUL byte — the legacy
one because :meth:`Path.resolve` raises :exc:`ValueError` and it catches
``ValueError`` to mean "no". ``tests/tools/test_workspace.py`` runs both
over a shared corpus and asserts zero disagreements, loading the legacy
module by file path so that assertion does not become an import.

Four differences remain, all deliberate:

* *Where a relative path is joined.* ``validate_path`` takes an
  already-joined path, so a relative one resolves against the **process
  CWD**; ``resolve`` joins to the workspace root and never consults the
  CWD. A boundary that moves when something calls :func:`os.chdir` is not
  a boundary.
* *Credentials.* ``validate_path`` has no notion of them: an SSH key
  inside a trusted root is allowed. Rule 2 above has no equivalent there.
* *What a refusal is.* ``validate_path`` returns ``False`` and
  ``validate_input_path`` returns ``None``; both lose which rule fired.
  Here a refusal is a typed exception carrying a sentence the model can
  act on — and the two subclasses are distinguishable for an operator,
  for the reason given above.
* *One root, not a search path.* ``validate_input_path`` tries the
  Desktop workspace, then the project root, then every trusted data dir,
  and additionally requires the file to exist. That is a *discovery*
  policy, and it belongs to whatever binds :data:`WORKSPACE_KEY` rather
  than to the boundary. ``resolve_dest`` goes further still and **falls
  back to a default directory** when a path escapes, which is the one
  behaviour deliberately not carried over: silently writing somewhere
  else is how a model learns that its escape attempt "worked".

**Leaf.** The standard library, and nothing else — not even the rest of
``omicsclaw.tools``. Whether a refused path is reported to the model as a
correctable argument error is the calling tool's decision, so this module
declines to make it.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_KEY = "workspace"
"""The :class:`~omicsclaw.tools.context.ToolContext` value naming the root.

Spelled as a constant because a typo read through
:func:`~omicsclaw.tools.context.context_value` yields ``None``, which is
indistinguishable from a surface that bound nothing — the tool then
reports "no workspace is bound", which reads like a surface bug.

One session has one workspace, so two tools reading two different keys
would be two workspaces wearing one name. Plan 0028's ``save_gene_panel``
spelled the string a second time and the duplication was pinned by test
until a later step could collapse it; that step arrived by deletion, and
the foundation tools import this one.
``test_the_workspace_key_is_spelled_once_and_the_tools_take_it_from_here``
now pins both the literal and the identity.
"""

CREDENTIAL_PATHS: tuple[tuple[str, ...], ...] = (
    (".ssh",),
    (".aws",),
    (".kube",),
    (".gnupg",),
    (".netrc",),
    (".config", "gcloud"),
    (".config", "gh"),
)
"""Component runs that make a path a credential path, wherever it sits.

Each entry is matched as **consecutive path components**, so ``.ssh``
catches ``/home/bob/.ssh/id_rsa`` and ``/srv/backup/.ssh`` alike, while
``(".config", "gcloud")`` catches ``~/.config/gcloud`` without also
refusing every directory in the world named ``gcloud``. Components, never
substrings: a project file called ``sshconfig.md`` is not a credential,
and a rule that thought it was would be a rule people route around.

The first six are harness9's list (``safe_path.go:31-38``), kept because
the machines this runs on are developer workstations. ``.config/gh`` is
added: a GitHub token is push access to this repository.
"""

SECRET_FILENAMES: tuple[str, ...] = (".env", ".env.*", ".envrc")
"""Final components that hold this project's own secrets.

Matched against the file name only — a *directory* named ``.env`` is the
virtualenv convention and refusing everything under one would cost real
reads for no security gain, since the secrets live in a file.

Plan 0029 §4 Q8 proposes the glob ``.env*``. These three patterns are
narrower on purpose: ``.env*`` also swallows ``.envelope-design.md``,
which is a refusal a user cannot understand and has nothing to do with
credentials. The three cover the conventions that actually carry secrets
— ``.env``, per-environment ``.env.production``, and direnv's ``.envrc``,
which is a shell script and routinely holds exported keys.
"""


class PathRefused(ValueError):
    """This path will not be used, and the message says why.

    A :exc:`ValueError` because the value is the problem. Subclassed
    twice rather than raised bare so that "the model wandered outside its
    workspace" and "something tried to open a private key" are separable
    downstream: they are the same answer to the model and completely
    different events for whoever is watching the machine.
    """


class PathEscapesWorkspace(PathRefused):
    """The path resolved to somewhere outside the session's workspace.

    Ordinarily a model mistake and correctable by sending a different
    path, which is why the message names the workspace root.
    """


class PathIsSensitive(PathRefused):
    """The path names credentials, and no workspace setting permits it.

    The message deliberately does **not** echo where the path resolved
    to. A model that reached a key through a symlink learns only that it
    was refused; confirming the key's location would be a courtesy to the
    one caller who should not receive it.
    """


def _tail_matches(parts: tuple[str, ...], marker: tuple[str, ...]) -> bool:
    """Do ``marker``'s components appear consecutively inside ``parts``?"""
    width = len(marker)
    return any(
        parts[index : index + width] == marker
        for index in range(len(parts) - width + 1)
    )


def is_sensitive(path: Path) -> bool:
    """Is this a credential path, regardless of any workspace?

    Call it on a **resolved** path (plan 0029 trap 8). Called on the name
    the model sent, ``<workspace>/link-to-ssh`` is an ordinary-looking
    file name and the rule never fires — which is the whole of the bypass
    this ordering exists to close. :meth:`Workspace.resolve` is the
    caller that gets this right; it is exposed separately so a future
    ``bash`` pre-flight check can reuse the same list rather than growing
    a second one.
    """
    if any(fnmatch.fnmatchcase(path.name, name) for name in SECRET_FILENAMES):
        return True
    return any(_tail_matches(path.parts, marker) for marker in CREDENTIAL_PATHS)


def _is_within(candidate: Path, root: Path) -> bool:
    """Is ``candidate`` the root itself or something under it?

    :meth:`Path.is_relative_to` compares components, which is what makes
    ``/project-evil`` not a child of ``/project``. Written as its own
    function so the rule has one line to point a mutation at: replace it
    with ``str(candidate).startswith(str(root))`` and the named test goes
    red, which is the only evidence that the component comparison is
    doing anything.
    """
    return candidate.is_relative_to(root)


@dataclass(frozen=True, slots=True)
class Workspace:
    """One session's filesystem boundary, and the only way through it.

    Constructed by whatever binds :data:`WORKSPACE_KEY` — a surface, a
    test — and handed to each tool. Frozen because a boundary that a tool
    can widen at runtime is not a boundary; the root is normalised once,
    in :meth:`__post_init__`, so every later comparison is against an
    already-resolved path.

    The root is expanded and resolved while model-supplied paths are only
    resolved, and the asymmetry is the point: ``~`` in an operator's
    configuration means the operator's home, while ``~`` in a payload the
    model wrote is just a character it chose. The second is treated as an
    ordinary directory name — which lands it inside the workspace, where
    it is harmless — rather than as a way to name ``$HOME``.
    """

    root: Path

    def __post_init__(self) -> None:
        """Normalise the root, and refuse to sit on top of credentials.

        Resolving the root matters more than it looks: temporary
        directories are routinely reached through symlinks (``/var`` →
        ``/private/var`` on macOS, ``/tmp`` wherever an operator has
        linked it), and comparing a resolved candidate against an
        unresolved root would reject every path in such a workspace.

        A root that is itself sensitive would make every call fail with a
        confusing per-path refusal, so it fails here instead, once, where
        the mistake was actually made.
        """
        resolved = Path(self.root).expanduser().resolve()
        if is_sensitive(resolved):
            raise PathIsSensitive(
                f"{self.root} cannot be used as a workspace: it is inside a "
                "location this agent never reads"
            )
        object.__setattr__(self, "root", resolved)

    def resolve(self, path: str | Path) -> Path:
        """The real file ``path`` names, or a refusal saying why not.

        ``path`` is **untrusted input** — whatever the model put in its
        arguments. Relative paths are joined to :attr:`root`; absolute
        ones are judged as given and are accepted only when they land
        inside it, which is how a model that has been told its workspace
        path may use it. The empty string and ``"."`` both name the root,
        matching ``safePath("/project", "")``.

        Returns an absolute, symlink-free :class:`~pathlib.Path`. It is
        not guaranteed to exist — ``write`` needs exactly that — so a
        caller that requires existence checks for it and says so in its
        own words.
        """
        try:
            resolved = (self.root / Path(path)).resolve()
        except (OSError, ValueError) as exc:
            # A NUL byte, a name longer than the filesystem allows, a
            # symlink chain the kernel gives up on. None of these can be
            # proved safe, so none of them are used. Refusing beats
            # letting an OSError surface from whichever tool happened to
            # open the file, where it reads as an I/O failure rather than
            # as a rejected path.
            raise PathRefused(f"{str(path)!r} is not a usable path: {exc}") from exc

        if is_sensitive(resolved):
            raise PathIsSensitive(
                f"{str(path)!r} is refused: it names credentials or "
                "environment secrets, which this agent does not read or "
                "write under any workspace setting"
            )

        if not _is_within(resolved, self.root):
            raise PathEscapesWorkspace(
                f"{str(path)!r} resolves to {resolved}, which is outside "
                f"this session's workspace {self.root}; send a path inside "
                "the workspace"
            )

        return resolved


__all__ = [
    "CREDENTIAL_PATHS",
    "PathEscapesWorkspace",
    "PathIsSensitive",
    "PathRefused",
    "SECRET_FILENAMES",
    "WORKSPACE_KEY",
    "Workspace",
    "is_sensitive",
]
