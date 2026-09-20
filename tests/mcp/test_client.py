"""The client's own rules, over a scripted transport.

What arrives from ``tools/call`` is rendered here, and harness9's version
keeps only ``text`` blocks: an image result came back as the empty string,
which the model reads as "the tool returned nothing". Every block kind
therefore leaves a trace, and output is capped because this is the one
tool whose size nothing else bounds.
"""

from __future__ import annotations

import pytest

from omicsclaw.mcp import (
    MCPClient,
    MCPProtocolError,
    MCPToolError,
    render_result,
    truncate_output,
)
from omicsclaw.mcp.client import MAX_TOOL_PAGES
from tests.mcp._support import (
    ScriptedTransport,
    initialize_result,
    run,
    scripted_server,
)


def _render(result) -> str:
    text, _ = render_result(result)
    return text


# ---- rendering ------------------------------------------------------------


def test_text_blocks_are_joined_in_order():
    result = {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}

    assert _render(result) == "a\nb"


def test_a_block_that_cannot_be_shown_says_so_instead_of_vanishing():
    result = {
        "content": [
            {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
            {"type": "audio", "data": "", "mimeType": "audio/wav"},
            {"type": "resource_link", "uri": "file:///r.csv", "name": "r.csv"},
            {"type": "resource", "resource": {"uri": "file:///b", "blob": "AA=="}},
            {"type": "hologram"},
        ]
    }

    lines = _render(result).splitlines()

    assert lines[0] == "[image (image/png, 8 base64 characters) not shown]"
    assert "audio" in lines[1]
    assert lines[2] == "[resource link: r.csv file:///r.csv]"
    assert "binary resource file:///b" in lines[3]
    assert lines[4] == "[content of type 'hologram' not shown]"


def test_an_embedded_text_resource_is_shown():
    result = {"content": [{"type": "resource", "resource": {"text": "col1,col2"}}]}

    assert _render(result) == "col1,col2"


def test_structured_content_is_used_when_there_is_no_text():
    result = {"content": [], "structuredContent": {"genes": ["TP53"]}}

    assert _render(result) == '{"genes": ["TP53"]}'


def test_structured_content_does_not_duplicate_existing_text():
    result = {
        "content": [{"type": "text", "text": "TP53"}],
        "structuredContent": {"genes": ["TP53"]},
    }

    assert _render(result) == "TP53"


def test_long_output_is_cut_and_the_cut_is_reported_truthfully():
    text = truncate_output("x" * 50, 10)

    assert text.startswith("x" * 10 + "\n")
    assert "showing the first 10 of 50 characters" in text
    assert truncate_output("x" * 50, 0) == "x" * 50


def test_is_error_must_be_literally_true():
    assert render_result({"content": [], "isError": True})[1] is True
    assert render_result({"content": [], "isError": "yes"})[1] is False


def test_a_result_that_is_not_an_object_is_a_protocol_error():
    with pytest.raises(MCPProtocolError):
        render_result(["text"])


# ---- handshake over a scripted transport ----------------------------------


def test_the_negotiated_version_reaches_the_transport():
    transport = scripted_server(initialize=initialize_result("2025-03-26"))

    info = run(MCPClient("s", transport).connect())

    assert info.protocol_version == "2025-03-26"
    assert transport.version == "2025-03-26"


@pytest.mark.parametrize("version", ["2024-11-05", "2025-03-26", "2025-06-18"])
def test_every_supported_version_is_accepted(version: str):
    transport = scripted_server(initialize=initialize_result(version))

    assert run(MCPClient("s", transport).connect()).protocol_version == version


@pytest.mark.parametrize("version", ["2099-01-01", None, 20250618])
def test_a_version_this_client_does_not_speak_fails_and_closes(version):
    transport = scripted_server(initialize=initialize_result(version))

    with pytest.raises(MCPProtocolError, match="protocol version"):
        run(MCPClient("s", transport).connect())
    assert transport.closed


def test_pages_are_followed_until_the_cursor_runs_out():
    transport = scripted_server(
        tools__list=[
            {"tools": [{"name": "a"}], "nextCursor": "p2"},
            {"tools": [{"name": "b"}], "nextCursor": "p3"},
            {"tools": [{"name": "c"}]},
        ]
    )
    client = MCPClient("s", transport)

    run(client.connect())

    assert [tool.name for tool in client.tools] == ["a", "b", "c"]
    cursors = [params for method, params in transport.sent if method == "tools/list"]
    assert cursors == [None, {"cursor": "p2"}, {"cursor": "p3"}]


def test_a_cursor_that_never_ends_is_refused():
    endless = [{"tools": [], "nextCursor": "again"}] * (MAX_TOOL_PAGES + 1)
    transport = scripted_server(tools__list=list(endless))

    with pytest.raises(MCPProtocolError, match="did not end"):
        run(MCPClient("s", transport).connect())


def test_a_tool_without_a_name_is_skipped_not_fatal():
    """One bad entry must not cost the server its other tools."""
    transport = scripted_server(
        tools=[{"description": "no name"}, {"name": ""}, "junk", {"name": "ok"}]
    )
    client = MCPClient("s", transport)

    run(client.connect())

    assert [tool.name for tool in client.tools] == ["ok"]
    assert client.unnamed_tools == 3


@pytest.mark.parametrize("listing", [None, {"tools": "echo"}, {}])
def test_a_malformed_listing_is_a_protocol_error(listing):
    transport = scripted_server(tools__list=listing)

    with pytest.raises(MCPProtocolError):
        run(MCPClient("s", transport).connect())
    assert transport.closed


def test_a_failing_handshake_closes_the_transport():
    transport = ScriptedTransport({"initialize": ConnectionError("boom")})

    with pytest.raises(ConnectionError):
        run(MCPClient("s", transport).connect())
    assert transport.closed


def test_a_listed_tool_keeps_its_description_and_schema():
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    transport = scripted_server(
        tools=[{"name": "search", "description": "Find.", "inputSchema": schema}]
    )
    client = MCPClient("s", transport)

    run(client.connect())

    (tool,) = client.tools
    assert (tool.name, tool.description) == ("search", "Find.")
    assert tool.input_schema == schema


def test_an_is_error_result_raises_with_a_message_even_when_empty():
    transport = scripted_server(tools__call={"content": [], "isError": True})
    client = MCPClient("s", transport)

    async def main():
        await client.connect()
        with pytest.raises(MCPToolError, match="reported an error"):
            await client.call_tool("echo", "{}")

    run(main())


def test_the_call_carries_the_name_and_the_decoded_arguments():
    transport = scripted_server()
    client = MCPClient("s", transport)

    async def main():
        await client.connect()
        return await client.call_tool("echo", '{"b": 1, "a": 2}')

    assert run(main()) == "ok"
    method, params = transport.sent[-1]
    assert method == "tools/call"
    assert params == {"name": "echo", "arguments": {"b": 1, "a": 2}}
    assert list(params["arguments"]) == ["b", "a"]
