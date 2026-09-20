"""Layering of ``omicsclaw/sandbox/``: a true leaf, imported only by ``entry``.

*Down.* The package imports the standard library and nothing else — not
even ``omicsclaw.tools``, whose ``BashEnvironment`` it satisfies
structurally. That is the dependency direction the tool layer's seam was
laid down for: the tool layer declares the shape, the sandbox fills it,
and only the composition root knows both.

*Up.* No rebuild layer but ``entry`` imports ``omicsclaw.sandbox``: the
engine and the tools stay ignorant that containers exist.

*Sideways.* The old bubblewrap isolation under ``omicsclaw/autonomous/``
belongs to the architecture being torn down; it is the natural thing to
reuse and is forbidden.

The last check is behavioural: a subprocess drives the real paths through
the fake CLI, then reports what :data:`sys.modules` holds.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "omicsclaw" / "sandbox"
_SUPPORT = pathlib.Path(__file__).resolve().parent

_OTHER_LAYERS = (
    "schema",
    "provider",
    "engine",
    "tools",
    "context",
    "skills",
    "mcp",
    "memory",
)

_FORBIDDEN_AT_RUNTIME = (
    "omicsclaw.tools",
    "omicsclaw.schema",
    "omicsclaw.engine",
    "omicsclaw.provider",
    "omicsclaw.providers",
    "omicsclaw.context",
    "omicsclaw.entry",
    "omicsclaw.mcp",
    "omicsclaw.runtime",
    "omicsclaw.autonomous",
    "omicsclaw.memory",
    "omicsclaw.skills",
    "docker",
    "pydantic",
    "requests",
)

_DYNAMIC_IMPORT_CALLS = frozenset(
    {
        "__import__",
        "import_module",
        "reload",
        "spec_from_file_location",
        "module_from_spec",
        "exec_module",
        "load_module",
    }
)


def _module_paths(package: pathlib.Path) -> list[pathlib.Path]:
    return sorted(package.rglob("*.py"))


def _imported_modules(path: pathlib.Path) -> list[str]:
    """Absolute module names imported by *path*, relative ones resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = list(path.relative_to(_REPO_ROOT).with_suffix("").parts[:-1])
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                if node.module:
                    names.append(node.module)
                continue
            climbed = len(package) - (node.level - 1)
            base = package[:climbed] if climbed > 0 else []
            names.append(".".join([*base, node.module] if node.module else base))
    return names


def test_the_package_has_modules_to_check():
    assert _module_paths(_PACKAGE)


@pytest.mark.parametrize("path", _module_paths(_PACKAGE), ids=lambda p: p.name)
def test_a_sandbox_module_imports_no_other_omicsclaw_package(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw"
        and not (name == "omicsclaw.sandbox" or name.startswith("omicsclaw.sandbox."))
    ]

    assert not offenders, f"{path.name} imports {offenders}"


@pytest.mark.parametrize("path", _module_paths(_PACKAGE), ids=lambda p: p.name)
def test_a_sandbox_module_imports_only_the_standard_library(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "omicsclaw"
    ]

    assert not offenders, f"{path.name} imports non-stdlib {offenders}"


@pytest.mark.parametrize("path", _module_paths(_PACKAGE), ids=lambda p: p.name)
def test_a_sandbox_module_imports_nothing_at_runtime(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", getattr(node.func, "id", ""))
        in _DYNAMIC_IMPORT_CALLS
    ]

    assert not offenders, f"{path.name} imports dynamically at lines {offenders}"


@pytest.mark.parametrize("path", _module_paths(_PACKAGE), ids=lambda p: p.name)
def test_a_sandbox_module_never_logs(path: pathlib.Path):
    """Like ``mcp``: report through values, let the composition root log."""
    assert "logging" not in _imported_modules(path)


@pytest.mark.parametrize("layer", _OTHER_LAYERS)
def test_no_other_rebuild_layer_imports_the_sandbox(layer: str):
    offenders = [
        f"{layer}/{path.name}"
        for path in _module_paths(_REPO_ROOT / "omicsclaw" / layer)
        for name in _imported_modules(path)
        if name == "omicsclaw.sandbox" or name.startswith("omicsclaw.sandbox.")
    ]

    assert not offenders, f"{offenders} import omicsclaw.sandbox"


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=120,
    )


_BEHAVIOUR_PROBE = """
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, __SUPPORT_PARENT__)
from sandbox_support_probe import install

from omicsclaw.sandbox import SandboxManager


async def main(root):
    docker = install(Path(root) / "fake")
    workspace = Path(root) / "ws"
    workspace.mkdir()
    manager = SandboxManager(docker.config(), start_daemon=None)
    await manager.reap_orphans()
    environment = await manager.create_with_retry(workspace)
    result = await environment.run_bash("echo hi; exit 2", str(workspace), 30)
    assert (result.output, result.exit_code) == ("hi\\n", 2), result
    await manager.aclose()


with tempfile.TemporaryDirectory() as root:
    asyncio.run(main(root))

FORBIDDEN = __FORBIDDEN__
print(sorted(
    name for name in sys.modules
    if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
))
"""


def test_running_the_layer_loads_nothing_it_must_not(tmp_path):
    """``tests/sandbox/_support.py`` imports ``omicsclaw.sandbox`` only, but
    the test package's ``__init__`` must not be imported either, so the
    helper is loaded as a standalone module from a copy."""
    helper = tmp_path / "sandbox_support_probe.py"
    helper.write_text(
        (_SUPPORT / "_support.py")
        .read_text(encoding="utf-8")
        .replace(
            '_FAKE = Path(__file__).resolve().parent / "fake_docker.py"',
            f"_FAKE = Path({str(_SUPPORT / 'fake_docker.py')!r})",
        )
        + "\n\ndef install(root):\n    return FakeDocker.install(root)\n",
        encoding="utf-8",
    )
    source = _BEHAVIOUR_PROBE.replace(
        "__SUPPORT_PARENT__", repr(str(tmp_path))
    ).replace("__FORBIDDEN__", repr(_FORBIDDEN_AT_RUNTIME))

    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", f"running the layer loaded {result.stdout}"


@pytest.mark.parametrize("layer", _OTHER_LAYERS)
def test_importing_another_layer_does_not_load_the_sandbox(layer: str):
    result = _probe(
        f"import sys, omicsclaw.{layer}; print('omicsclaw.sandbox' in sys.modules)"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_the_public_surface_is_deliberate():
    import omicsclaw.sandbox as sandbox

    assert sandbox.__all__ == sorted(sandbox.__all__), "keep the list sorted"
    assert all(hasattr(sandbox, name) for name in sandbox.__all__)
    assert set(sandbox.__all__) == {
        "BootstrapOutcome",
        "ChangeListener",
        "CommandRunner",
        "CommandTimedOut",
        "Completed",
        "Container",
        "ContainerState",
        "DaemonStarter",
        "DockerEnvironment",
        "EXCHANGE_DIR",
        "ExecResult",
        "LABEL",
        "NAME_PREFIX",
        "NETWORK_NONE",
        "OWNER_LABEL",
        "ReapReport",
        "SandboxConfig",
        "SandboxConfigError",
        "SandboxError",
        "SandboxInfo",
        "SandboxManager",
        "SubprocessRunner",
        "check_mount_path",
        "desktop_starter",
        "ensure_daemon_ready",
        "host_user",
        "owner_is_dead",
        "owner_token",
        "run_arguments",
    }
