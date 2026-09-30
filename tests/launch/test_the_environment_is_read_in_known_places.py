"""Plan 0037 judgement 1, restated so that it is true and enforced.

**What the criterion said, and why it was false.** Plan 0037 §3-1 and this
shell's own module docstring claimed ``os.environ`` was read by
``resolve_app_config`` alone, "plus the one declared exception
``provider_from_env``". Two source scans agreed —— and both were scoped to
``omicsclaw/entry/`` and ``omicsclaw/launch/``, which is exactly where the
claim happens to hold. One layer out the rebuilt stack reads the live
environment in seven more places, one of which is on the path every
``open_app`` takes: ``assembly.py`` calls ``load_mcp_config(path)`` without an
``env``, so a ``${VAR}`` in ``.mcp.json`` is expanded from the process
environment and not from the mapping :func:`omicsclaw.launch.main` was handed.

A rule that is enforced over the two packages where it is true, and is false
everywhere else, is worse than a wider rule that is enforced: it reads as a
guarantee and it is decoration. So the claim is replaced by this inventory.
Every entry is a file that names a process global, with the reason it may.
A new one costs an edit here and a red test; that is the whole point, and it
is the property the narrower claim never had.

The scope is the *rebuilt* stack. ``omicsclaw/agents/``, ``omicsclaw/core/``,
``omicsclaw/diagnostics.py`` and the three legacy trees read the environment
freely and are scheduled for deletion or rebuild; counting them would make
this test a measure of how far that has got.
"""

from __future__ import annotations

import pathlib

from tests._env_probe import FORBIDDEN_SPELLINGS

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "omicsclaw"

REBUILT_PACKAGES = (
    "common",
    "context",
    "engine",
    "entry",
    "launch",
    "mcp",
    "memory",
    "permission",
    "provider",
    "schema",
    "skillenv",
    "skills",
    "tools",
)
"""The packages plan 0031 and plan 0037 rebuilt, and therefore own the rule."""

ENVIRONMENT_READERS = {
    "launch/__init__.py": (
        "The process shell. It resolves the default for main(env=None) and "
        "overlays .env onto the process environment, which is the one place "
        "allowed to write it at all (plan 0037 §5.1)."
    ),
    "provider/config.py": (
        "Plan 0031 Q8's one *declared* exception, in its two resolvers: a "
        "secret routed through AppConfig would only add a place it can be "
        "printed from. Both take env= and default to the live one."
    ),
    "provider/openai_provider.py": (
        "The same exception, for the adapter that reads its own key. Takes "
        "env= as well."
    ),
    "provider/factory.py": (
        "Prose only —— provider_from_env's docstring explains the exception "
        "above. Listed because the scan reads prose on purpose: a docstring "
        "that claims a read is either true or a bug."
    ),
    "mcp/config.py": (
        "UNDECLARED, and reached in production: ${VAR} in .mcp.json is "
        "expanded from here, and omicsclaw/entry/assembly.py calls "
        "load_mcp_config(path) with no env, so the mapping handed to "
        "main() does not reach it. The function already takes env=; "
        "threading it through open_app is recorded as debt in plan 0037 "
        "appendix A, and the next person's check is the .mcp.json case."
    ),
    "mcp/stdio.py": (
        "UNDECLARED: child_environment() inherits a fixed list of variables "
        "into an MCP server's child process, defaulting to the live one. "
        "Arguably correct —— a child process's environment is a process "
        "fact —— but it is not the declared exception either."
    ),
    "common/workspace.py": (
        "UNDECLARED: resolve_omicsclaw_dir reads OMICSCLAW_DIR to "
        "short-circuit the source-checkout search. Called from below the "
        "layer that has an AppConfig, which is why it cannot be handed one."
    ),
    "common/runtime_env.py": (
        "UNDECLARED, and the only *writer* besides the shell: it activates "
        "cache directories for the scientific stack and parses .env files. "
        "launch/__init__.py calls load_env_file() from here."
    ),
    "skillenv/probe.py": (
        "Not a read by this process: the fixed probe and inventory programs "
        "embedded as source strings read their own sys.argv[1] in another "
        "interpreter, where bash runs. The agent environment that pip and the "
        "overlay's interpreters start from is handed to skillenv by the entry "
        "layer (plan 0061 §4.10)."
    ),
    "tools/builtin/bash.py": (
        "The local shell is started with a copy of the process environment "
        "minus the framework's control-plane credentials: "
        "without_control_credentials() drops CONTROL_CREDENTIAL_NAMES, and "
        "that has to happen where the environment is read."
    ),
}
"""Every file in the rebuilt stack that names a process global, and why.

Four of the eight are marked UNDECLARED because that is what they are: plan
0037 §3-1 did not know about them. Naming them is not approving them —— it is
the difference between a debt and a surprise.
"""


def _readers() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for package in REBUILT_PACKAGES:
        for path in sorted((_PACKAGE / package).rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            hits = [n for n in FORBIDDEN_SPELLINGS if n in source]
            if hits:
                found[path.relative_to(_PACKAGE).as_posix()] = hits
    return found


def test_every_rebuilt_package_is_a_real_directory():
    """A package renamed away would make this whole file pass vacuously."""
    missing = [name for name in REBUILT_PACKAGES if not (_PACKAGE / name).is_dir()]

    assert not missing, f"{missing} are listed as rebuilt and do not exist"


def test_the_environment_is_read_only_in_the_places_named_here():
    found = _readers()

    unlisted = sorted(set(found) - set(ENVIRONMENT_READERS))
    stale = sorted(set(ENVIRONMENT_READERS) - set(found))

    assert not unlisted, (
        f"{unlisted} read a process global and are not in ENVIRONMENT_READERS "
        "— add them with the reason, or hand the value down instead"
    )
    assert not stale, (
        f"{stale} no longer read a process global — delete the entry, the "
        "inventory is supposed to be exact"
    )


def test_every_entry_carries_a_reason():
    """An inventory of names without reasons is a list, not a rule."""
    thin = sorted(
        name for name, reason in ENVIRONMENT_READERS.items() if len(reason) < 40
    )

    assert not thin, f"{thin} are listed without a reason"


def test_the_shell_is_the_only_place_the_environment_is_written():
    """Reading a variable is a fact; writing one changes what others read.

    ``common/runtime_env.py`` is the mechanism —— it is what parses a
    ``.env`` —— and ``launch/__init__.py`` is the only caller in the
    rebuilt stack that asks it to. Anything else in this inventory that
    started assigning into the environment would be changing a
    deployment behind ``resolve_app_config``'s back.
    """
    writers = []
    for name in ENVIRONMENT_READERS:
        source = (_PACKAGE / name).read_text(encoding="utf-8")
        if "os.environ[" in source:
            writers.append(name)

    assert sorted(writers) == ["common/runtime_env.py"]
