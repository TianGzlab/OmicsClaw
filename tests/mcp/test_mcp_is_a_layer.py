"""Layering of ``omicsclaw/mcp/``: what it imports, and who imports it.

Copied from the repaired guard beside the skill loader. Three directions:

*Down.* Inside the ``omicsclaw`` namespace the package may import
``omicsclaw.tools`` (it mints :class:`~omicsclaw.tools.MCPTool`, so the
naming rule has one implementation), ``omicsclaw.schema`` and the
``omicsclaw.version`` constant. Everything else is the standard library —
no MCP SDK, no ``httpx``, no ``anyio``.

*Up.* No other rebuild layer imports ``omicsclaw.mcp``. The engine stays
ignorant that MCP exists, which is the whole claim of the adapter design.

*Sideways.* The legacy MCP code lives in ``omicsclaw.surfaces.cli._mcp``
and ``omicsclaw.extensions``; either would be the natural thing to reuse
and both are forbidden.

The last check is behavioural: a subprocess connects a real server, calls
a tool through a registry and closes, then reports what
:data:`sys.modules` holds.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "omicsclaw" / "mcp"
_FAKE_SERVER = pathlib.Path(__file__).resolve().parent / "fake_server.py"

_ALLOWED_INTERNAL = (
    "omicsclaw.mcp",
    "omicsclaw.tools",
    "omicsclaw.schema",
    "omicsclaw.version",
)

_OTHER_LAYERS = ("schema", "provider", "engine", "tools", "context", "skills")

_FORBIDDEN_AT_RUNTIME = (
    "omicsclaw.runtime",
    "omicsclaw.engine",
    "omicsclaw.provider",
    "omicsclaw.providers",
    "omicsclaw.context",
    "omicsclaw.entry",
    "omicsclaw.skill",
    "omicsclaw.skills",
    "omicsclaw.surfaces",
    "omicsclaw.extensions",
    "omicsclaw.memory",
    "omicsclaw.control",
    "mcp",
    "httpx",
    "anyio",
    "pydantic",
    "requests",
    "yaml",
    "langchain_mcp_adapters",
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


def _is_allowed(name: str) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in _ALLOWED_INTERNAL)


def test_the_package_has_modules_to_check():
    assert _module_paths(_PACKAGE)


@pytest.mark.parametrize("path", _module_paths(_PACKAGE), ids=lambda p: p.name)
def test_an_mcp_module_imports_only_what_it_may(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, f"{path.name} imports {offenders}"


@pytest.mark.parametrize("path", _module_paths(_PACKAGE), ids=lambda p: p.name)
def test_an_mcp_module_imports_only_the_standard_library(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "omicsclaw"
    ]

    assert not offenders, f"{path.name} imports non-stdlib {offenders}"


@pytest.mark.parametrize("path", _module_paths(_PACKAGE), ids=lambda p: p.name)
def test_an_mcp_module_imports_nothing_at_runtime(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", getattr(node.func, "id", ""))
        in _DYNAMIC_IMPORT_CALLS
    ]

    assert not offenders, f"{path.name} imports dynamically at lines {offenders}"


def test_only_the_manager_reaches_into_the_tool_layer():
    """The protocol modules speak MCP; the manager is the one bridge to
    :class:`~omicsclaw.tools.MCPTool`. A client that raised tool-layer
    exceptions was the coupling the audit found."""
    touching = sorted(
        path.name
        for path in _module_paths(_PACKAGE)
        if any(name.startswith("omicsclaw.tools") for name in _imported_modules(path))
    )

    assert touching == ["manager.py"]


@pytest.mark.parametrize("layer", _OTHER_LAYERS)
def test_no_other_rebuild_layer_imports_mcp(layer: str):
    offenders = [
        f"{layer}/{path.name}"
        for path in _module_paths(_REPO_ROOT / "omicsclaw" / layer)
        for name in _imported_modules(path)
        if name == "omicsclaw.mcp" or name.startswith("omicsclaw.mcp.")
    ]

    assert not offenders, f"{offenders} import omicsclaw.mcp"


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=60,
    )


_BEHAVIOUR_PROBE = """
import asyncio
import json
import sys

from omicsclaw.mcp import MCPManager, ServerState, parse_mcp_config
from omicsclaw.schema import ToolCall
from omicsclaw.tools import ApprovalMode, ToolPolicy, ToolRegistry

config = parse_mcp_config(
    {
        "mcpServers": {
            "fake": {"command": sys.executable, "args": [__SERVER__]},
            "remote": {"type": "http", "url": "http://127.0.0.1:9/mcp"},
            "broken": {"type": "sse", "url": "http://x"},
        }
    },
    {},
)


async def main():
    manager = MCPManager(config, connect_timeout_s=10)
    statuses = {s.name: s.state for s in await manager.start()}
    assert statuses == {
        "fake": ServerState.CONNECTED,
        "remote": ServerState.FAILED,
        "broken": ServerState.FAILED,
    }, statuses
    registry = ToolRegistry()
    for tool in manager.tools():
        registry.register(tool, ToolPolicy(approval_mode=ApprovalMode.AUTO))
    result = await registry.execute(
        ToolCall(id="1", name="mcp__fake__echo", arguments='{"a": 1}')
    )
    assert json.loads(result.output) == {"a": 1}, result
    await manager.aclose()


asyncio.run(main())
FORBIDDEN = __FORBIDDEN__
print(sorted(
    name for name in sys.modules
    if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
))
"""


def test_running_the_layer_loads_nothing_it_must_not():
    source = _BEHAVIOUR_PROBE.replace("__SERVER__", repr(str(_FAKE_SERVER))).replace(
        "__FORBIDDEN__", repr(_FORBIDDEN_AT_RUNTIME)
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", f"running the layer loaded {result.stdout}"


@pytest.mark.parametrize("layer", _OTHER_LAYERS)
def test_importing_another_layer_does_not_load_mcp(layer: str):
    result = _probe(
        f"import sys, omicsclaw.{layer}; print('omicsclaw.mcp' in sys.modules)"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_the_public_surface_is_deliberate():
    import omicsclaw.mcp as mcp

    assert mcp.__all__ == sorted(mcp.__all__), "keep the list sorted"
    assert all(hasattr(mcp, name) for name in mcp.__all__)
    assert set(mcp.__all__) == {
        "DEFAULT_CONNECT_TIMEOUT_S",
        "DEFAULT_MAX_OUTPUT_CHARS",
        "HTTPTransport",
        "MCPClient",
        "MCPConfig",
        "MCPConfigError",
        "MCPError",
        "MCPManager",
        "MCPProtocolError",
        "MCPRemoteError",
        "MCPToolError",
        "MCPTransportError",
        "PROTOCOL_VERSION",
        "RejectedServer",
        "RemoteTool",
        "SUPPORTED_PROTOCOL_VERSIONS",
        "ServerConfig",
        "ServerInfo",
        "ServerState",
        "ServerStatus",
        "StatusListener",
        "StdioTransport",
        "ToolDetail",
        "Transport",
        "TransportKind",
        "load_mcp_config",
        "open_transport",
        "origin_of",
        "parse_mcp_config",
        "render_result",
        "truncate_output",
    }
