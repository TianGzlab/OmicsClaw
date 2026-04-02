import asyncio
import json

from omicsclaw.extensions import (
    ExtensionManifest,
    extension_store_dir,
    write_extension_state,
    write_install_record,
)
from omicsclaw.runtime import (
    EXECUTION_STATUS_FAILED,
    ToolExecutionRequest,
    ToolRegistry,
    ToolSpec,
    build_default_tool_execution_hooks,
    execute_tool_requests,
)


def _write_runtime_policy_extension(
    tmp_path,
    name: str,
    *,
    source_kind: str = "local",
    enabled: bool = True,
    hook_payload: dict | None = None,
):
    pack_dir = extension_store_dir(tmp_path, "prompt-pack") / name
    pack_dir.mkdir(parents=True)
    (pack_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (pack_dir / "tool-hooks.json").write_text(
        json.dumps(hook_payload or {"tool_execution_hooks": []}),
        encoding="utf-8",
    )
    manifest = ExtensionManifest(
        name=name,
        version="1.0.0",
        type="prompt-pack",
        entrypoints=["rules.md"],
        tool_execution_hooks=["tool-hooks.json"],
        trusted_capabilities=["runtime-policy"],
    )
    (pack_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type,
                "entrypoints": manifest.entrypoints,
                "tool_execution_hooks": manifest.tool_execution_hooks,
                "trusted_capabilities": manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        pack_dir,
        extension_name=name,
        source_kind=source_kind,
        source=f"/tmp/{name}",
        manifest=manifest,
        extension_type="prompt-pack",
        relative_install_path=f"installed_extensions/prompt-packs/{name}",
    )
    write_extension_state(
        pack_dir,
        enabled=enabled,
        disabled_reason="" if enabled else "disabled in test",
    )
    return pack_dir


def test_build_default_tool_execution_hooks_compiles_rewrite_and_failure_hooks(tmp_path):
    observed = {}

    _write_runtime_policy_extension(
        tmp_path,
        "runtime-rules",
        hook_payload={
            "tool_execution_hooks": [
                {
                    "name": "rewrite-alpha",
                    "tools": ["alpha"],
                    "surfaces": ["cli"],
                    "pre": {
                        "set_arguments": {"path": "{workspace}/rewritten.txt"},
                    },
                    "post": {
                        "output_template": "{output}\npost:{workspace}",
                    },
                },
                {
                    "name": "broken-recovery",
                    "tools": ["broken"],
                    "failure": {
                        "output_template": "{output}\nworkspace:{workspace}",
                    },
                },
            ]
        },
    )

    hooks = build_default_tool_execution_hooks(tmp_path)

    assert [hook.name for hook in hooks] == [
        "runtime-rules:broken-recovery",
        "runtime-rules:rewrite-alpha",
    ]

    async def alpha_executor(args):
        observed["alpha"] = dict(args)
        return "alpha-ok"

    async def broken_executor(args):
        raise RuntimeError("boom")

    runtime = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            ),
            ToolSpec(
                name="broken",
                description="Broken tool",
                parameters={"type": "object", "properties": {}},
            ),
        ]
    ).build_runtime(
        {
            "alpha": alpha_executor,
            "broken": broken_executor,
        }
    )

    alpha_result = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-alpha",
                    name="alpha",
                    arguments={},
                    spec=runtime.specs_by_name["alpha"],
                    executor=runtime.executors["alpha"],
                    runtime_context={
                        "surface": "cli",
                        "workspace": "/tmp/lab",
                        "tool_execution_hooks": hooks,
                    },
                )
            ]
        )
    )[0]

    broken_result = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-broken",
                    name="broken",
                    arguments={},
                    spec=runtime.specs_by_name["broken"],
                    executor=runtime.executors["broken"],
                    runtime_context={
                        "surface": "cli",
                        "workspace": "/tmp/lab",
                        "tool_execution_hooks": hooks,
                    },
                )
            ]
        )
    )[0]

    assert observed["alpha"] == {"path": "/tmp/lab/rewritten.txt"}
    assert alpha_result.output == "alpha-ok\npost:/tmp/lab"
    assert alpha_result.trace is not None
    assert alpha_result.trace.post_hook_records[0].updated_output is True

    assert broken_result.success is False
    assert broken_result.status == EXECUTION_STATUS_FAILED
    assert "workspace:/tmp/lab" in str(broken_result.output)
    assert broken_result.trace is not None
    assert broken_result.trace.failure_hook_records[0].updated_output is True


def test_build_default_tool_execution_hooks_ignores_remote_extensions(tmp_path):
    _write_runtime_policy_extension(
        tmp_path,
        "remote-runtime-rules",
        source_kind="github",
        hook_payload={
            "tool_execution_hooks": [
                {
                    "name": "rewrite-alpha",
                    "tools": ["alpha"],
                    "pre": {"action": "ask", "message": "confirm"},
                }
            ]
        },
    )

    assert build_default_tool_execution_hooks(tmp_path) == ()
