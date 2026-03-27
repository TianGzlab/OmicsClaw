import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from bot.core import TOOLS, OMICS_EXTENSIONS, _sanitize_tool_history

def test_tools_generated():
    assert len(TOOLS) > 0
    omicsclaw_tool = next((t for t in TOOLS if t["function"]["name"] == "omicsclaw"), None)
    assert omicsclaw_tool is not None
    description = omicsclaw_tool["function"]["description"]
    assert "Available skills:" in description
    assert "spatial-preprocessing" in description
    assert "genomics-vcf-operations" in description
    
    # Just checking an extension loaded dynamically
    assert ".vcf" in OMICS_EXTENSIONS


def _assert_array_schemas_define_items(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "array":
            assert "items" in schema, f"Array schema missing items: {schema}"
        for value in schema.values():
            _assert_array_schemas_define_items(value)
    elif isinstance(schema, list):
        for item in schema:
            _assert_array_schemas_define_items(item)


def test_all_array_schemas_define_items():
    for tool in TOOLS:
        _assert_array_schemas_define_items(tool)


def test_create_csv_file_data_schema_is_valid():
    csv_tool = next(t for t in TOOLS if t["function"]["name"] == "create_csv_file")
    data_schema = csv_tool["function"]["parameters"]["properties"]["data"]
    assert data_schema["type"] == "array"
    assert data_schema["items"]["type"] == "object"


def test_sanitize_tool_history_keeps_complete_multi_tool_bundle():
    history = [
        {"role": "user", "content": "do two things"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result 1"},
        {"role": "tool", "tool_call_id": "call_2", "content": "result 2"},
        {"role": "assistant", "content": "done"},
    ]

    sanitised = _sanitize_tool_history(history)
    assert sanitised == history


def test_sanitize_tool_history_drops_incomplete_tool_bundle():
    history = [
        {"role": "user", "content": "do two things"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result 1"},
        {"role": "assistant", "content": "next turn"},
    ]

    sanitised = _sanitize_tool_history(history)
    assert sanitised == [
        {"role": "user", "content": "do two things"},
        {"role": "assistant", "content": "next turn"},
    ]
