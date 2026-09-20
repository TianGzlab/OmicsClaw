"""Contract tests for ``omicsclaw.tools._workspace`` (plan 0029, task A).

Plan 0029 §8 traps 1, 2, 3, 8 and 9 live here, one named test each, and
each one paired with a **positive** test that the mutation must leave
green. That pairing is the whole discipline of this file: an assertion
that a malicious path is refused stays green under the worst possible
implementation — ``def resolve(self, path): raise PathRefused`` — so a
refusal test on its own proves nothing at all. Every rule below is
therefore pinned twice, from both sides, and the two halves are adjacent
so a reader can see the pair.

The second subject is plan 0029 §4 Q1: this module re-implements what
``omicsclaw/services/path_validation.py`` did for the layer being
replaced. A re-write with no comparison is a guess, so
:func:`test_containment_agrees_with_the_legacy_path_validator` runs both
over one corpus and asserts zero disagreements on the half they share,
and the tests around it pin each place they deliberately differ.

That comparison used to load the legacy module from disk. The framework
rebuild deleted it, so :func:`_legacy_validate_path` below is a **frozen
copy** of the one function this file ever called, taken verbatim from the
last revision that shipped it and verified to answer identically over the
whole corpus at capture time. Freezing the function rather than a table
of its answers keeps the comparison live: a new corpus entry is still
answered by the legacy rule instead of needing a recorded verdict.
"""

from __future__ import annotations

import pathlib

import pytest

from omicsclaw.tools._workspace import (
    CREDENTIAL_PATHS,
    SECRET_FILENAMES,
    WORKSPACE_KEY,
    PathEscapesWorkspace,
    PathIsSensitive,
    PathRefused,
    Workspace,
    is_sensitive,
)


def _legacy_validate_path(filepath: pathlib.Path, allowed_root: pathlib.Path) -> bool:
    """Answer whether ``filepath`` resolves inside ``allowed_root``.

    A verbatim copy of ``validate_path`` from
    ``omicsclaw/services/path_validation.py`` at revision ``ed3c6cc4``,
    the last one to ship that module. Copying it is exact rather than
    approximate: this was the whole function, it read no module state,
    and its ``except ValueError`` is load-bearing — that is what refuses
    a NUL byte, because :meth:`pathlib.Path.resolve` raises for one.

    Its neighbours in that module — ``validate_input_path``,
    ``resolve_dest``, ``discover_file`` — were never called here. They
    answer a different question (*which* of several trusted roots holds
    this file) and reach for ``DATA_DIR`` and friends through a late
    import of the deleted runtime.
    """
    try:
        filepath.resolve().relative_to(allowed_root.resolve())
        return True
    except ValueError:
        return False


@pytest.fixture
def workspace(tmp_path: pathlib.Path) -> Workspace:
    """A workspace that has a sibling, because half the traps need one.

    ``tmp_path`` itself is deliberately *not* the workspace: the escapes
    worth testing land just outside it, and a root with nothing beside it
    can only be escaped into ``/``.
    """
    root = tmp_path / "run-7"
    root.mkdir()
    return Workspace(root)


# --------------------------------------------------------------------------
# The ordinary case, first. Every refusal below is only meaningful next to
# one of these.
# --------------------------------------------------------------------------


def test_a_relative_path_lands_inside_the_workspace(workspace: Workspace):
    """The positive control for every traversal test in this file."""
    assert workspace.resolve("a.txt") == workspace.root / "a.txt"
    assert workspace.resolve("src/main.py") == workspace.root / "src" / "main.py"
    assert workspace.resolve("./README.md") == workspace.root / "README.md"


def test_a_path_that_does_not_exist_yet_still_resolves(workspace: Workspace):
    """``write`` names files that are not there. That has to be allowed.

    ``Path.resolve(strict=False)`` is what makes it so, and it is the
    default — spelled out here because the strict variant is one keyword
    away and would break every first write.
    """
    target = workspace.resolve("results/run/never-written.csv")

    assert target == workspace.root / "results" / "run" / "never-written.csv"
    assert not target.exists()


def test_an_empty_path_and_a_dot_both_name_the_workspace_root(
    workspace: Workspace,
):
    """Matching ``safePath("/project", "") == "/project"`` exactly."""
    assert workspace.resolve("") == workspace.root
    assert workspace.resolve(".") == workspace.root
    assert workspace.resolve(workspace.root) == workspace.root


def test_an_interior_dot_dot_that_stays_inside_is_allowed(
    workspace: Workspace,
):
    """``sub/../a.txt`` never leaves, so refusing it would be superstition.

    The rule is about where a path *lands*, not about which characters it
    contains. A ``".." in path`` check would refuse this and would still
    miss a symlink, which is the trade this module declines to make.
    """
    assert workspace.resolve("sub/../a.txt") == workspace.root / "a.txt"


# --------------------------------------------------------------------------
# Trap 1 — a shared name prefix is not containment.
# --------------------------------------------------------------------------


def test_a_sibling_sharing_the_workspaces_name_is_not_inside_it(
    workspace: Workspace, tmp_path: pathlib.Path
):
    """Plan 0029 trap 1, both halves.

    ``/run-7-evil`` begins with ``/run-7`` and is not under it.
    harness9 handles this by appending a separator before comparing
    (``safe_path.go:90-92``); :func:`_is_within` compares path components
    instead, which cannot express the bug at all.

    The second half is what makes the first half mean something: a
    directory with the *same name* **inside** the workspace is fine. A
    check that refused both would pass the first assertion and be
    useless. Mutation: swap :func:`omicsclaw.tools._workspace._is_within`
    for ``str(candidate).startswith(str(root))`` and the first assertion
    fails while the second still passes.
    """
    evil = tmp_path / "run-7-evil"
    evil.mkdir()
    (evil / "x.py").write_text("stolen", encoding="utf-8")

    with pytest.raises(PathEscapesWorkspace):
        workspace.resolve(str(evil / "x.py"))

    inside = workspace.resolve("run-7-evil/x.py")
    assert inside == workspace.root / "run-7-evil" / "x.py"


# --------------------------------------------------------------------------
# Trap 2 — an absolute path is judged, never concatenated.
# --------------------------------------------------------------------------


def test_an_absolute_path_inside_the_workspace_is_returned_undoubled(
    workspace: Workspace,
):
    """Plan 0029 trap 2, the half that is about a *correct* path failing.

    harness9 opened a separate branch for absolute input
    (``safe_path.go:72-87``) because ``filepath.Join(workDir, "/abs")``
    produces ``/workDir/abs`` — its SWE-bench traces show 10 of 12
    instances failing with "no such file" from exactly that doubling.
    Python's ``/`` operator resets on a rooted right-hand side, so the
    branch is not translated; this test is what makes that claim
    falsifiable. Mutation: replace ``self.root / Path(path)`` with the Go
    behaviour, ``Path(f"{self.root}/{str(path).lstrip('/')}")``, and this
    test fails while every refusal test stays green.
    """
    absolute = workspace.root / "src" / "flask" / "cli.py"

    assert workspace.resolve(str(absolute)) == absolute
    assert workspace.resolve(str(workspace.root)) == workspace.root
    assert (
        workspace.resolve(str(workspace.root / "a" / "b" / ".." / "c.py"))
        == workspace.root / "a" / "c.py"
    )


def test_an_absolute_path_outside_the_workspace_is_refused(
    workspace: Workspace, tmp_path: pathlib.Path
):
    """Plan 0029 trap 2, the security half. Four kinds of outside."""
    other = tmp_path / "somebody-else"
    other.mkdir()

    for outsider in ("/etc/passwd", "/", str(other), str(other / "y.py")):
        with pytest.raises(PathEscapesWorkspace):
            workspace.resolve(outsider)


def test_a_traversal_out_of_the_workspace_is_refused(workspace: Workspace):
    """The attack named in ``safe_path.go``'s own header comment."""
    for escape in ("../../etc/passwd", "../escaped.txt", "src/../../escaped.txt"):
        with pytest.raises(PathEscapesWorkspace):
            workspace.resolve(escape)


def test_a_refusal_tells_the_model_where_the_workspace_is(
    workspace: Workspace,
):
    """An escape is usually a mistake, so the refusal has to be fixable.

    The model cannot correct a path without knowing the root it is
    supposed to be under, and "denied" on its own produces a retry loop.
    Contrast :func:`test_a_credential_refusal_does_not_say_where_the_key_is`.
    """
    with pytest.raises(PathEscapesWorkspace) as caught:
        workspace.resolve("../escaped.txt")

    message = str(caught.value)
    assert "../escaped.txt" in message
    assert str(workspace.root) in message


# --------------------------------------------------------------------------
# Trap 3 and Q10 — symlinks are followed, which harness9 does not do.
# --------------------------------------------------------------------------


def test_a_symlink_pointing_out_of_the_workspace_is_refused(
    workspace: Workspace, tmp_path: pathlib.Path
):
    """Plan 0029 §4 Q10: where this module is **stricter** than harness9.

    ``safePath`` uses ``filepath.Abs``, which follows nothing, so this
    exact file passes its check. :meth:`Path.resolve` follows it.
    Mutation: swap ``.resolve()`` for ``Path(os.path.abspath(...))`` and
    this test fails while the traversal tests stay green — which is the
    evidence that symlink handling is a separate rule and not a side
    effect of normalising ``..``.
    """
    secret = tmp_path / "secret.txt"
    secret.write_text("not yours", encoding="utf-8")
    (workspace.root / "innocent.txt").symlink_to(secret)

    with pytest.raises(PathEscapesWorkspace):
        workspace.resolve("innocent.txt")


def test_a_file_under_a_symlinked_parent_is_refused_before_anything_exists(
    workspace: Workspace, tmp_path: pathlib.Path
):
    """Plan 0029 trap 3: the leaf may be absent, the parent may not lie.

    ``strict=False`` means a non-existent *leaf* is fine — that is
    :func:`test_a_path_that_does_not_exist_yet_still_resolves` — and the
    worry is that the same leniency lets a symlinked *directory* through
    until something calls ``mkdir(parents=True)`` on it. It does not:
    every component that exists is resolved, so the escape is caught
    while the target directory is still empty.

    The positive half is in the same test: a file that does not exist
    under a directory that does not exist either, inside the workspace,
    still resolves. Otherwise "refuse when the parent is a symlink" and
    "refuse when the parent is missing" would be indistinguishable.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathEscapesWorkspace):
        workspace.resolve("escape/new.txt")

    assert list(outside.iterdir()) == [], "resolving must not create anything"
    assert workspace.resolve("real/new.txt") == workspace.root / "real" / "new.txt"


def test_a_symlink_inside_the_workspace_pointing_inside_it_is_allowed(
    workspace: Workspace,
):
    """The positive control for both symlink tests above.

    Following links refuses *escapes*, not links. A workspace where every
    symlink was refused would be one where resolving is doing the wrong
    job — and the mutation to ``os.path.abspath`` leaves this green,
    which is what makes it a control rather than a duplicate.
    """
    (workspace.root / "data").mkdir()
    real = workspace.root / "data" / "counts.csv"
    real.write_text("gene,count\n", encoding="utf-8")
    (workspace.root / "latest.csv").symlink_to(real)

    assert workspace.resolve("latest.csv") == real


def test_a_workspace_reached_through_a_symlink_still_accepts_its_own_files(
    tmp_path: pathlib.Path,
):
    """The root is resolved too, or nothing in such a workspace works.

    Not hypothetical: ``/var`` is a symlink to ``/private/var`` on macOS,
    so :func:`tempfile.mkdtemp` hands out linked paths there as a matter
    of course. Comparing a resolved candidate against an unresolved root
    would refuse every path in the workspace — a total outage wearing a
    security message.
    """
    real = tmp_path / "actual-root"
    real.mkdir()
    linked = tmp_path / "linked-root"
    linked.symlink_to(real, target_is_directory=True)

    workspace = Workspace(linked)

    assert workspace.root == real
    assert workspace.resolve("a.txt") == real / "a.txt"
    assert workspace.resolve(str(linked / "a.txt")) == real / "a.txt"


# --------------------------------------------------------------------------
# Traps 8 and 9 — credentials, checked after resolution and without a home.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        ".ssh/id_rsa",
        ".aws/credentials",
        ".kube/config",
        ".gnupg/secring.gpg",
        ".netrc",
        ".config/gcloud/application_default_credentials.json",
        ".config/gh/hosts.yml",
    ],
)
def test_a_credential_path_is_refused_even_inside_the_workspace(
    workspace: Workspace, relative: str
):
    """harness9's list (``safe_path.go:31-38``) plus ``.config/gh``.

    Inside the workspace on purpose. The rule harness9 states is that the
    workspace whitelist does not override it, and the only way to check
    that is to put the credential somewhere the whitelist *would*
    otherwise allow. ``.config/gh`` is this project's addition: a GitHub
    token is push access to this repository.
    """
    with pytest.raises(PathIsSensitive):
        workspace.resolve(relative)


def test_a_credential_name_must_be_a_whole_component_not_a_substring(
    workspace: Workspace,
):
    """The positive control for the parametrised refusals above.

    A rule matching substrings would refuse ``ssh-setup-notes.md`` and
    ``gcloud-migration.md``, and a rule people route around is worse than
    no rule. Mutation: make :func:`_tail_matches` compare with ``in``
    over the joined string and this test fails while every refusal above
    stays green.
    """
    for harmless in (
        "ssh-setup-notes.md",
        "docs/gcloud-migration.md",
        "notes/.sshrc-draft",
        "awsconfig.json",
    ):
        assert workspace.resolve(harmless) == workspace.root / harmless


def test_a_symlink_into_a_credential_directory_is_refused_as_sensitive(
    workspace: Workspace, tmp_path: pathlib.Path
):
    """Plan 0029 trap 8: the check runs **after** resolution, not before.

    ``<workspace>/creds`` is an ordinary-looking name. Screening the
    string the model sent would let it through; screening what it
    resolves to does not.

    The assertion is on the *class*, not merely on "something raised".
    Both rules refuse this path, so a version that checked containment
    first would also be green under ``pytest.raises(PathRefused)`` — and
    would file a credential-access attempt as a typo. Mutation: move the
    :func:`is_sensitive` call below the containment check and this test
    fails while every other test in the file passes.
    """
    keys = tmp_path / "elsewhere" / ".ssh"
    keys.mkdir(parents=True)
    (keys / "id_ed25519").write_text("PRIVATE KEY", encoding="utf-8")
    (workspace.root / "creds").symlink_to(keys, target_is_directory=True)

    with pytest.raises(PathIsSensitive):
        workspace.resolve("creds/id_ed25519")


def test_a_credential_refusal_does_not_say_where_the_key_is(
    workspace: Workspace, tmp_path: pathlib.Path
):
    """The one message that stays vague, and why.

    An escape refusal names the workspace root so the model can correct
    itself (:func:`test_a_refusal_tells_the_model_where_the_workspace_is`).
    A credential refusal has nothing to correct — there is no argument
    that makes it allowed — so resolving the symlink for the caller would
    be handing over the location of a private key and nothing else.
    """
    keys = tmp_path / "elsewhere" / ".ssh"
    keys.mkdir(parents=True)
    (workspace.root / "creds").symlink_to(keys, target_is_directory=True)

    with pytest.raises(PathIsSensitive) as caught:
        workspace.resolve("creds/id_ed25519")

    message = str(caught.value)
    assert "creds/id_ed25519" in message
    assert str(keys) not in message


def test_a_dotenv_file_is_refused_because_this_projects_keys_live_in_one(
    workspace: Workspace,
):
    """Plan 0029 §4 Q8's project-specific addition.

    ``CLAUDE.md`` puts ``LLM_API_KEY``, ``TELEGRAM_BOT_TOKEN`` and
    ``FEISHU_APP_SECRET`` in ``.env`` at the project root, so for this
    repository ``.env`` is more valuable than ``~/.kube`` and far more
    likely to be sitting in a workspace.
    """
    for secret in (".env", ".env.production", ".envrc", "config/.env.local"):
        with pytest.raises(PathIsSensitive):
            workspace.resolve(secret)


def test_a_file_merely_starting_with_env_is_not_a_secret(
    workspace: Workspace,
):
    """The positive control, and the reason the glob ``.env*`` was narrowed.

    Plan 0029 §4 Q8 proposes ``.env*``, which also swallows these. A
    refusal a user cannot explain is a rule that gets deleted, so the
    patterns are the three conventions that actually carry secrets.
    Mutation: widen :data:`SECRET_FILENAMES` to ``(".env*",)`` and this
    test fails while the test above stays green.
    """
    for harmless in (".envelope-design.md", "environment.yml", "env/settings.py"):
        assert workspace.resolve(harmless) == workspace.root / harmless


def test_the_credential_rule_does_not_depend_on_finding_a_home_directory(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
):
    """Plan 0029 trap 9: no home must mean *stricter*, never looser.

    harness9 returns an empty credential list when ``os.UserHomeDir``
    fails (``safe_path.go:27-29``), leaning on a bash DangerHook this
    project does not have — so translating that fallback would mean the
    rule silently switching off inside a container with no ``HOME``.
    Rather than handling the failure, :func:`is_sensitive` has no home
    dependency to fail: it matches components wherever they sit.

    Both halves again. Without the second assertion this test would pass
    against an implementation that refuses everything when home is
    missing, which is "more conservative" in the useless sense.
    """
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(
        pathlib.Path,
        "home",
        classmethod(lambda cls: _no_home()),
    )

    with pytest.raises(PathIsSensitive):
        workspace.resolve(".ssh/id_rsa")
    assert workspace.resolve("counts.csv") == workspace.root / "counts.csv"


def _no_home() -> pathlib.Path:
    raise RuntimeError("could not determine home directory")


def test_a_credential_path_is_refused_wherever_it_sits(tmp_path: pathlib.Path):
    """The consequence of dropping the home anchor, stated as a test.

    A second user's home, a restored backup, a mounted image: none of
    them are ``~``, and all of them hold real keys. :func:`is_sensitive`
    is exposed separately so this can be asserted without a workspace at
    all — and so a future ``bash`` pre-flight check has one list to
    consult rather than growing a second.
    """
    assert is_sensitive(pathlib.Path("/mnt/backup/home/bob/.ssh/id_rsa"))
    assert is_sensitive(pathlib.Path("/srv/images/root/.aws/credentials"))
    assert not is_sensitive(pathlib.Path("/srv/data/counts.csv"))


def test_a_workspace_root_that_is_itself_a_credential_store_is_refused(
    tmp_path: pathlib.Path,
):
    """Fail at the mistake, not once per call afterwards.

    Such a root would make every :meth:`Workspace.resolve` raise, and the
    operator would read a stream of per-path refusals instead of the one
    sentence that names the actual problem.
    """
    root = tmp_path / ".gnupg"
    root.mkdir()

    with pytest.raises(PathIsSensitive):
        Workspace(root)


# --------------------------------------------------------------------------
# Inputs that are not paths at all.
# --------------------------------------------------------------------------


def test_a_path_with_a_null_byte_is_refused_rather_than_raising_from_a_tool(
    workspace: Workspace,
):
    """The filesystem's own :exc:`ValueError`, caught and renamed.

    Left alone it escapes from whichever tool happened to call
    ``open()``, where it reads as an I/O failure and sends the model
    looking for a broken file rather than a bad argument. It is refused
    rather than sanitised because a path that cannot be resolved cannot
    be proved safe, which is the same reasoning as everywhere else here.
    """
    with pytest.raises(PathRefused) as caught:
        workspace.resolve("a\x00b.txt")

    assert not isinstance(caught.value, (PathEscapesWorkspace, PathIsSensitive))


def test_a_tilde_is_an_ordinary_directory_name_not_the_users_home(
    workspace: Workspace,
):
    """Model-supplied ``~`` is a character it chose, not an instruction.

    :meth:`Path.expanduser` is applied to the *root* — operator
    configuration, where ``~/omics`` plainly means the operator's home —
    and never to the payload. Expanding it here would let one character
    move a path from the workspace to ``$HOME``; not expanding it leaves
    ``~`` as a directory name inside the workspace, which is harmless.

    ``~/.ssh/id_rsa`` is refused, but by the credential rule rather than
    by containment, which is the honest reason.
    """
    assert workspace.resolve("~/notes.md") == workspace.root / "~" / "notes.md"
    with pytest.raises(PathIsSensitive):
        workspace.resolve("~/.ssh/id_rsa")


# --------------------------------------------------------------------------
# Plan 0029 §4 Q1 — the comparison with the layer being replaced.
# --------------------------------------------------------------------------

_CORPUS = (
    "a.txt",
    "./a.txt",
    "",
    ".",
    "sub/a.txt",
    "sub/../a.txt",
    "sub/./deep/../a.txt",
    "../escaped.txt",
    "../../etc/passwd",
    "src/../../escaped.txt",
    "/etc/passwd",
    "/",
    "a\x00b.txt",
    "results/never/written.csv",
)
"""Paths both implementations are asked about, credentials excluded.

Credentials are left out because the legacy validator has no such rule
and would disagree by design — that difference is pinned by
:func:`test_the_legacy_validator_allows_a_credential_this_one_refuses`
instead of being averaged into a "mostly agrees" number.
"""


def test_containment_agrees_with_the_legacy_path_validator(
    workspace: Workspace, tmp_path: pathlib.Path
):
    """Plan 0029 §4 Q1: a re-write with no comparison is a guess.

    ``validate_path(filepath, allowed_root)`` is the overlapping half —
    resolve both sides, compare by component — and on the overlap the two
    agree exactly, including the cases worth being surprised by: a path
    that does not exist is allowed by both, and a path containing a NUL
    byte is refused by both (the legacy one because
    :meth:`Path.resolve` raises :exc:`ValueError` and its ``except
    ValueError`` reads that as "no").

    The legacy function does not *join*, so the corpus is joined here the
    way its caller ``validate_input_path`` would. That is itself a
    documented difference: given a relative path it resolves against the
    process working directory, while this module resolves against the
    workspace root and never consults the CWD.
    """
    disagreements = []
    for raw in (*_CORPUS, str(workspace.root), str(tmp_path / "outside.txt")):
        candidate = pathlib.Path(raw)
        joined = candidate if candidate.is_absolute() else workspace.root / candidate
        legacy = _legacy_validate_path(joined, workspace.root)
        try:
            workspace.resolve(raw)
            mine = True
        except PathRefused:
            mine = False
        if legacy != mine:
            disagreements.append((raw, legacy, mine))

    assert not disagreements, f"legacy vs new: {disagreements}"


def test_the_legacy_validator_allows_a_credential_this_one_refuses(
    workspace: Workspace,
):
    """The first deliberate difference, kept as a test rather than a claim.

    An SSH key sitting inside a trusted root passes ``validate_path``;
    plan 0029 §4 Q8's hard list is what this module adds, and the
    comparison above would quietly hide it.
    """
    key = workspace.root / ".ssh" / "id_rsa"

    assert _legacy_validate_path(key, workspace.root) is True
    with pytest.raises(PathIsSensitive):
        workspace.resolve(".ssh/id_rsa")


def test_the_legacy_validator_reports_a_bool_where_this_one_says_why(
    workspace: Workspace,
):
    """The second deliberate difference.

    ``validate_path`` answers ``False`` and ``validate_input_path``
    answers ``None``; both lose which rule fired, so a caller cannot tell
    a typo from an attempt on a private key and the model is told
    neither. Here the class carries that, and the message carries a
    sentence the model can act on.
    """
    assert _legacy_validate_path(workspace.root / ".." / "x", workspace.root) is False

    with pytest.raises(PathEscapesWorkspace):
        workspace.resolve("../x")
    with pytest.raises(PathIsSensitive):
        workspace.resolve(".aws/credentials")


def test_the_workspace_key_is_spelled_once_and_the_tools_take_it_from_here():
    """One session has one workspace, so the key must not drift.

    ``builtin/gene_panel.py`` spelled this constant a second time in step
    4, and Task A could not edit a delivered module to share it, so the
    duplication was pinned here until a later step collapsed it. That
    step arrived by deletion: the three reference tools were removed
    (owner, 2026-09-18) and the foundation tools import this one.

    Two things are left worth pinning. The literal, because a surface
    binds the value by name and changing it here would silently unbind
    every tool — the failure is a tool reporting "no workspace is bound",
    which reads like a surface bug. And the identity, because a tool that
    re-spelled the string would pass an equality check on the day it was
    written and drift on some later day.
    """
    from omicsclaw.tools.builtin import read as read_module

    assert WORKSPACE_KEY == "workspace"
    assert read_module.WORKSPACE_KEY is WORKSPACE_KEY


def test_the_credential_list_is_the_reference_list_plus_this_projects_own():
    """What was taken and what was added, in one assertion.

    Not a tautology restating the constant: it is the record of *which*
    entries are harness9's (so a reviewer can check them against
    ``safe_path.go:31-38``) and which are this project's, so that
    removing one is a visible decision rather than a tidy-up.
    """
    assert CREDENTIAL_PATHS == (
        (".ssh",),
        (".aws",),
        (".kube",),
        (".gnupg",),
        (".netrc",),
        (".config", "gcloud"),
        (".config", "gh"),
    )
    assert SECRET_FILENAMES == (".env", ".env.*", ".envrc")
