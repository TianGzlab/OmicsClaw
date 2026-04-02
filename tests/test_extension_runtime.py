import json

from omicsclaw.extensions import (
    build_extension_runtime_snapshot,
    ExtensionManifest,
    extension_store_dir,
    load_active_hook_extensions,
    load_enabled_agent_packs,
    load_enabled_output_style_packs,
    load_enabled_prompt_packs,
    load_enabled_workflow_packs,
    load_prompt_pack_runtime_context,
    write_extension_state,
    write_install_record,
)


def _write_prompt_pack(
    tmp_path,
    name: str,
    *,
    source_kind: str = "local",
    enabled: bool = True,
    trusted_capabilities: list[str] | None = None,
    rules_text: str = "Use concise lab language.\n",
):
    pack_dir = extension_store_dir(tmp_path, "prompt-pack") / name
    pack_dir.mkdir(parents=True)
    (pack_dir / "rules.md").write_text(rules_text, encoding="utf-8")
    manifest = ExtensionManifest(
        name=name,
        version="1.0.0",
        type="prompt-pack",
        entrypoints=["rules.md"],
        trusted_capabilities=list(trusted_capabilities or []),
    )
    (pack_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type,
                "entrypoints": manifest.entrypoints,
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


def test_load_enabled_prompt_packs_applies_tracking_enablement_and_trust_filters(tmp_path):
    _write_prompt_pack(tmp_path, "active-rules", trusted_capabilities=["prompt-rules"])
    _write_prompt_pack(tmp_path, "disabled-rules", enabled=False)
    _write_prompt_pack(tmp_path, "remote-rules", source_kind="github")
    _write_prompt_pack(tmp_path, "wrong-capability", trusted_capabilities=["skill-run"])

    loaded = load_enabled_prompt_packs(tmp_path)

    assert [pack.name for pack in loaded] == ["active-rules"]
    assert loaded[0].rules[0].relative_path == "rules.md"
    assert "Use concise lab language." in loaded[0].rules[0].content


def test_load_prompt_pack_runtime_context_builds_budgeted_context_block(tmp_path):
    _write_prompt_pack(
        tmp_path,
        "analysis-style",
        rules_text="Prioritize exact file paths.\nAvoid redundant restatements.\n",
    )

    runtime_context = load_prompt_pack_runtime_context(tmp_path, max_total_chars=1200)

    assert runtime_context.active_prompt_packs == ("analysis-style",)
    assert runtime_context.omitted_prompt_packs == ()
    assert "## Active Local Prompt Packs" in runtime_context.content
    assert "analysis-style v1.0.0" in runtime_context.content
    assert "Avoid redundant restatements." in runtime_context.content


def test_runtime_snapshot_loads_agent_workflow_and_hook_surfaces(tmp_path):
    agent_dir = extension_store_dir(tmp_path, "agent-pack") / "lab-agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agents.yaml").write_text(
        (
            "agents:\n"
            "  - name: reviewer\n"
            "    description: Review analysis plans.\n"
            "    tools: [run_omicsclaw]\n"
        ),
        encoding="utf-8",
    )
    agent_manifest = ExtensionManifest(
        name="lab-agents",
        version="1.0.0",
        type="agent-pack",
        entrypoints=["agents.yaml"],
        trusted_capabilities=["agent-entry"],
    )
    (agent_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": agent_manifest.name,
                "version": agent_manifest.version,
                "type": agent_manifest.type,
                "entrypoints": agent_manifest.entrypoints,
                "trusted_capabilities": agent_manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        agent_dir,
        extension_name="lab-agents",
        source_kind="local",
        source="/tmp/lab-agents",
        manifest=agent_manifest,
        extension_type="agent-pack",
        relative_install_path="installed_extensions/agent-packs/lab-agents",
    )
    write_extension_state(agent_dir, enabled=True)

    workflow_dir = extension_store_dir(tmp_path, "workflow-pack") / "lab-workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "workflows.yaml").write_text(
        (
            "workflows:\n"
            "  - name: qc-pipeline\n"
            "    description: Run QC and summarize outputs.\n"
            "    steps: [inspect, qc, summarize]\n"
            "    skills: [sc-qc, sc-preprocessing]\n"
        ),
        encoding="utf-8",
    )
    workflow_manifest = ExtensionManifest(
        name="lab-workflows",
        version="1.0.0",
        type="workflow-pack",
        entrypoints=["workflows.yaml"],
        trusted_capabilities=["workflow-entry"],
    )
    (workflow_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": workflow_manifest.name,
                "version": workflow_manifest.version,
                "type": workflow_manifest.type,
                "entrypoints": workflow_manifest.entrypoints,
                "trusted_capabilities": workflow_manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        workflow_dir,
        extension_name="lab-workflows",
        source_kind="local",
        source="/tmp/lab-workflows",
        manifest=workflow_manifest,
        extension_type="workflow-pack",
        relative_install_path="installed_extensions/workflow-packs/lab-workflows",
    )
    write_extension_state(workflow_dir, enabled=True)

    hook_dir = extension_store_dir(tmp_path, "hook-pack") / "lab-hooks"
    hook_dir.mkdir(parents=True)
    (hook_dir / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "name": "qc-reminder",
                        "event": "session_start",
                        "mode": "notice",
                        "message": "Verify QC thresholds before execution.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    hook_manifest = ExtensionManifest(
        name="lab-hooks",
        version="1.0.0",
        type="hook-pack",
        hooks=["hooks.json"],
        trusted_capabilities=["hooks"],
    )
    (hook_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": hook_manifest.name,
                "version": hook_manifest.version,
                "type": hook_manifest.type,
                "hooks": hook_manifest.hooks,
                "trusted_capabilities": hook_manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        hook_dir,
        extension_name="lab-hooks",
        source_kind="local",
        source="/tmp/lab-hooks",
        manifest=hook_manifest,
        extension_type="hook-pack",
        relative_install_path="installed_extensions/hook-packs/lab-hooks",
    )
    write_extension_state(hook_dir, enabled=True)

    agent_packs = load_enabled_agent_packs(tmp_path)
    workflow_packs = load_enabled_workflow_packs(tmp_path)
    hook_extensions = load_active_hook_extensions(tmp_path)
    snapshot = build_extension_runtime_snapshot(tmp_path)

    assert [pack.name for pack in agent_packs] == ["lab-agents"]
    assert agent_packs[0].agents[0].name == "reviewer"
    assert [pack.name for pack in workflow_packs] == ["lab-workflows"]
    assert workflow_packs[0].workflows[0].name == "qc-pipeline"
    assert [item.name for item in hook_extensions] == ["lab-hooks"]
    assert hook_extensions[0].hooks[0].name == "qc-reminder"

    activation_by_type = {
        record.extension_type: record
        for record in snapshot.activation_records
    }
    assert activation_by_type["agent-pack"].surfaces[0].surface == "agents"
    assert activation_by_type["agent-pack"].surfaces[0].active is True
    assert activation_by_type["workflow-pack"].surfaces[0].surface == "workflows"
    assert activation_by_type["workflow-pack"].surfaces[0].active is True
    assert activation_by_type["hook-pack"].surfaces[0].surface == "hooks"
    assert activation_by_type["hook-pack"].surfaces[0].active is True


def test_runtime_snapshot_loads_output_style_surface(tmp_path):
    style_dir = extension_store_dir(tmp_path, "output-style-pack") / "lab-styles"
    style_dir.mkdir(parents=True)
    (style_dir / "styles.yaml").write_text(
        (
            "styles:\n"
            "  - name: concise-lab\n"
            "    description: Keep it concise.\n"
            "    aliases: [lab]\n"
            "    instructions: |\n"
            "      - Lead with the answer.\n"
            "      - Preserve exact file paths.\n"
        ),
        encoding="utf-8",
    )
    style_manifest = ExtensionManifest(
        name="lab-styles",
        version="1.0.0",
        type="output-style-pack",
        entrypoints=["styles.yaml"],
        trusted_capabilities=["output-style-entry"],
    )
    (style_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": style_manifest.name,
                "version": style_manifest.version,
                "type": style_manifest.type,
                "entrypoints": style_manifest.entrypoints,
                "trusted_capabilities": style_manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        style_dir,
        extension_name="lab-styles",
        source_kind="local",
        source="/tmp/lab-styles",
        manifest=style_manifest,
        extension_type="output-style-pack",
        relative_install_path="installed_extensions/output-style-packs/lab-styles",
    )
    write_extension_state(style_dir, enabled=True)

    style_packs = load_enabled_output_style_packs(tmp_path)
    snapshot = build_extension_runtime_snapshot(tmp_path)

    assert [pack.name for pack in style_packs] == ["lab-styles"]
    assert style_packs[0].styles[0].name == "concise-lab"
    assert style_packs[0].styles[0].aliases == ("lab",)

    activation_by_type = {
        record.extension_type: record
        for record in snapshot.activation_records
    }
    assert activation_by_type["output-style-pack"].surfaces[0].surface == "output_styles"
    assert activation_by_type["output-style-pack"].surfaces[0].active is True
