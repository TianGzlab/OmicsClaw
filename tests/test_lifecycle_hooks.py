import json

from omicsclaw.extensions import (
    ExtensionManifest,
    extension_store_dir,
    write_extension_state,
    write_install_record,
)
from omicsclaw.runtime.events import EVENT_SESSION_START
from omicsclaw.runtime.hook_payloads import SessionHookPayload
from omicsclaw.runtime.hooks import (
    HOOK_MODE_CONTEXT,
    build_default_lifecycle_hook_runtime,
)


def test_build_default_lifecycle_hook_runtime_loads_trusted_extension_hooks(tmp_path):
    pack_dir = extension_store_dir(tmp_path, "prompt-pack") / "lab-hooks"
    pack_dir.mkdir(parents=True)
    (pack_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (pack_dir / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "name": "session-sop",
                        "event": "session_start",
                        "mode": "context",
                        "message": "Follow SOP for {surface}.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = ExtensionManifest(
        name="lab-hooks",
        version="1.0.0",
        type="prompt-pack",
        entrypoints=["rules.md"],
        hooks=["hooks.json"],
        trusted_capabilities=["hooks"],
    )
    (pack_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type,
                "entrypoints": manifest.entrypoints,
                "hooks": manifest.hooks,
                "trusted_capabilities": manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        pack_dir,
        extension_name="lab-hooks",
        source_kind="local",
        source=str(pack_dir),
        manifest=manifest,
        extension_type="prompt-pack",
        relative_install_path="installed_extensions/prompt-packs/lab-hooks",
    )
    write_extension_state(pack_dir, enabled=True)

    runtime = build_default_lifecycle_hook_runtime(tmp_path)
    runtime.emit(
        EVENT_SESSION_START,
        SessionHookPayload(chat_id="chat-1", surface="cli"),
        context={"surface": "cli"},
    )

    messages = runtime.consume_pending_messages(
        mode=HOOK_MODE_CONTEXT,
        event_names=(EVENT_SESSION_START,),
    )
    assert messages == ["Follow SOP for cli."]
    assert runtime.records[0].hook_records[0].extension_name == "lab-hooks"
