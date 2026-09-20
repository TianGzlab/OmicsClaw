"""``.mcp.json`` parsing.

The file shape is the ``mcpServers`` one Claude Code, Claude Desktop and
harness9 share, so a file written for any of them loads here. Two
properties matter more than the rest: a broken *entry* is rejected alone
while its neighbours load (harness9's fail-soft, moved from connect time
to parse time so the reason is exact), and a broken *file* is loud.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omicsclaw.mcp import (
    MCPConfigError,
    TransportKind,
    load_mcp_config,
    parse_mcp_config,
)


def _parse(servers: dict, env: dict | None = None):
    return parse_mcp_config({"mcpServers": servers}, env or {})


def test_a_missing_file_is_an_empty_configuration(tmp_path: Path):
    """Zero configuration must behave exactly as before MCP existed."""
    config = load_mcp_config(tmp_path / ".mcp.json")

    assert config.is_empty
    assert config.source == tmp_path / ".mcp.json"


def test_a_file_that_is_not_json_is_refused_loudly(tmp_path: Path):
    path = tmp_path / ".mcp.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(MCPConfigError, match="not valid JSON"):
        load_mcp_config(path)


@pytest.mark.parametrize("document", [[], "x", {"mcpServers": []}])
def test_a_document_of_the_wrong_shape_is_refused(document):
    with pytest.raises(MCPConfigError):
        parse_mcp_config(document, {})


def test_a_document_without_servers_is_empty():
    assert parse_mcp_config({"other": 1}, {}).is_empty


def test_the_harness9_example_loads(tmp_path: Path):
    path = tmp_path / ".mcp.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "context7": {
                        "command": "npx",
                        "args": ["-y", "@upstash/context7-mcp"],
                    },
                    "remote-api": {
                        "type": "http",
                        "url": "https://api.example.com/mcp",
                        "headers": {"Authorization": "Bearer YOUR_TOKEN"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_mcp_config(path, env={})

    stdio, remote = config.servers
    assert (stdio.name, stdio.kind, stdio.command) == (
        "context7",
        TransportKind.STDIO,
        "npx",
    )
    assert stdio.args == ("-y", "@upstash/context7-mcp")
    assert remote.kind is TransportKind.HTTP
    assert remote.url == "https://api.example.com/mcp"
    assert dict(remote.headers) == {"Authorization": "Bearer YOUR_TOKEN"}
    assert not config.rejected


def test_servers_keep_file_order():
    config = _parse({name: {"command": "x"} for name in ("b", "a", "c")})

    assert [server.name for server in config.servers] == ["b", "a", "c"]


@pytest.mark.parametrize(
    ("entry", "kind"),
    [
        ({"command": "x"}, TransportKind.STDIO),
        ({"url": "http://127.0.0.1/mcp"}, TransportKind.HTTP),
        ({"type": "streamable-http", "url": "https://x/mcp"}, TransportKind.HTTP),
        ({"transport": "streamable_http", "url": "https://x/mcp"}, TransportKind.HTTP),
        ({"type": "STDIO", "command": "x"}, TransportKind.STDIO),
    ],
)
def test_the_transport_is_declared_or_inferred(entry, kind):
    assert _parse({"s": entry}).servers[0].kind is kind


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        ({}, "needs a 'command'"),
        ({"command": "x", "url": "http://x"}, "add a 'type'"),
        ({"type": "sse", "url": "http://x"}, "not supported"),
        ({"type": "websocket", "url": "ws://x"}, "not supported"),
        ({"type": "carrier-pigeon", "command": "x"}, "unknown transport"),
        ({"type": "stdio", "transport": "http", "command": "x"}, "disagree"),
        ({"type": "stdio"}, "non-empty 'command'"),
        ({"type": "http", "url": "ftp://x"}, "http(s) 'url'"),
        ({"command": ["npx"]}, "'command' must be a string"),
        ({"command": "x", "args": "-y"}, "'args' must be a list"),
        ({"command": "x", "env": {"A": 1}}, "'env' must be an object of strings"),
        ({"command": "x", "env": ["NO_EQUALS"]}, "KEY=VALUE"),
        ({"command": "x", "tools": "echo"}, "'tools' must be a list"),
        ({"command": "x", "enabled": "yes"}, "true or false"),
        ("npx", "must be an object"),
    ],
)
def test_a_bad_entry_is_rejected_with_its_reason(entry, reason):
    config = _parse({"bad": entry, "good": {"command": "x"}})

    assert [server.name for server in config.servers] == ["good"]
    (rejected,) = config.rejected
    assert rejected.name == "bad"
    assert reason in rejected.reason


def test_variables_are_expanded_where_they_are_allowed():
    config = _parse(
        {
            "s": {
                "command": "${BIN}",
                "args": ["--root", "${ROOT:-/data}"],
                "env": {"TOKEN": "${SECRET}"},
            },
            "h": {
                "url": "https://${HOST}/mcp",
                "headers": {"Authorization": "Bearer ${SECRET}"},
            },
        },
        env={"BIN": "server", "SECRET": "s3cr3t", "HOST": "example.org"},
    )

    stdio, remote = config.servers
    assert stdio.command == "server"
    assert stdio.args == ("--root", "/data")
    assert dict(stdio.env) == {"TOKEN": "s3cr3t"}
    assert remote.url == "https://example.org/mcp"
    assert dict(remote.headers) == {"Authorization": "Bearer s3cr3t"}


def test_an_unset_variable_rejects_the_server_and_names_the_variable_only():
    """Silently expanding to ``""`` would send ``Bearer `` and fail later,
    somewhere less legible. The reason names the variable and never a value."""
    config = _parse(
        {"s": {"url": "https://x/mcp", "headers": {"Authorization": "${TOKEN}"}}},
        env={"OTHER": "value-that-must-not-appear"},
    )

    (rejected,) = config.rejected
    assert "TOKEN" in rejected.reason
    assert "value-that-must-not-appear" not in rejected.reason


def test_a_default_covers_an_empty_variable_like_a_shell_does():
    config = _parse({"s": {"command": "${BIN:-fallback}"}}, env={"BIN": ""})

    assert config.servers[0].command == "fallback"


def test_env_may_be_a_list_of_assignments():
    """harness9 writes ``env`` as ``["KEY=VALUE"]``; the rest of the world
    writes an object. Both load."""
    config = _parse({"s": {"command": "x", "env": ["A=1", "B=x=y"]}})

    assert dict(config.servers[0].env) == {"A": "1", "B": "x=y"}


@pytest.mark.parametrize(
    ("flags", "enabled"),
    [({}, True), ({"enabled": False}, False), ({"disabled": True}, False)],
)
def test_a_server_can_be_switched_off_without_deleting_it(flags, enabled):
    assert _parse({"s": {"command": "x", **flags}}).servers[0].enabled is enabled


def test_the_tool_allowlist_is_kept_and_absence_means_all():
    config = _parse(
        {"some": {"command": "x", "tools": ["echo"]}, "all": {"command": "x"}}
    )

    assert config.servers[0].tools == ("echo",)
    assert config.servers[1].tools is None


def test_unknown_keys_are_ignored():
    """Other clients add keys of their own (``autoApprove``, ``timeout``).
    Ignoring ``autoApprove`` errs safe: every MCP call still asks."""
    config = _parse({"s": {"command": "x", "autoApprove": ["echo"], "timeout": 5}})

    assert config.servers[0].command == "x"
    assert not config.rejected


def test_a_parsed_server_cannot_be_mutated():
    server = _parse({"s": {"command": "x", "env": {"A": "1"}}}).servers[0]

    with pytest.raises(TypeError):
        server.env["A"] = "2"  # type: ignore[index]
