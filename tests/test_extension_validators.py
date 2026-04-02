import json

from omicsclaw.extensions import (
    EXTENSION_MANIFEST_FILENAME,
    discover_extension_manifest,
    load_extension_manifest,
    validate_extension_directory,
    validate_skill_pack_directory,
)


def test_discover_and_load_extension_manifest(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    manifest_path = skill_dir / EXTENSION_MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "name": "my-skill",
                "version": "1.0.0",
                "type": "skill-pack",
                "entrypoints": ["run.py"],
                "tool_execution_hooks": ["tool-hooks.json"],
                "required_files": ["SKILL.md"],
                "trusted_capabilities": ["skill-run"],
            }
        ),
        encoding="utf-8",
    )

    discovered = discover_extension_manifest(skill_dir)
    manifest = load_extension_manifest(manifest_path)

    assert discovered == manifest_path
    assert manifest.name == "my-skill"
    assert manifest.version == "1.0.0"
    assert manifest.entrypoints == ["run.py"]
    assert manifest.tool_execution_hooks == ["tool-hooks.json"]
    assert manifest.required_files == ["SKILL.md"]
    assert manifest.trusted_capabilities == ["skill-run"]


def test_validate_skill_pack_directory_accepts_valid_manifest_and_skill_files(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: test skill\nversion: 1.0.0\n---\n",
        encoding="utf-8",
    )
    (skill_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "my-skill",
                "version": "1.0.0",
                "type": "skill-pack",
                "entrypoints": ["run.py"],
                "required_files": ["SKILL.md"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_skill_pack_directory(skill_dir)

    assert report.valid is True
    assert report.manifest is not None
    assert report.extension_type == "skill-pack"
    assert report.errors == []
    assert report.warnings == []


def test_validate_skill_pack_directory_reports_manifest_contract_errors(tmp_path):
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir()
    (skill_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "broken-skill",
                "version": "1.0.0",
                "type": "skill-pack",
                "entrypoints": ["missing.py"],
                "required_files": ["SKILL.md"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_skill_pack_directory(skill_dir)

    assert report.valid is False
    assert "Extension manifest requires missing file: SKILL.md" in report.errors
    assert "Extension manifest entrypoint not found: missing.py" in report.errors


def test_validate_extension_directory_rejects_untrusted_privileged_capabilities(tmp_path):
    extension_dir = tmp_path / "remote-skill"
    extension_dir.mkdir()
    (extension_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "remote-skill",
                "version": "1.0.0",
                "type": "skill-pack",
                "entrypoints": ["run.py"],
                "trusted_capabilities": ["skill-run", "hooks"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="github")

    assert report.valid is False
    assert report.restricted_capabilities == ["hooks"]
    assert any("privileged capabilities" in error for error in report.errors)


def test_validate_extension_directory_rejects_untrusted_non_skill_pack(tmp_path):
    extension_dir = tmp_path / "prompt-pack"
    extension_dir.mkdir()
    (extension_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "prompt-pack",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="github")

    assert report.valid is False
    assert "Untrusted extension sources may only install 'skill-pack' extensions." in report.errors


def test_validate_extension_directory_accepts_local_prompt_pack(tmp_path):
    extension_dir = tmp_path / "prompt-pack"
    extension_dir.mkdir()
    (extension_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "prompt-pack",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is True
    assert report.extension_type == "prompt-pack"
    assert report.entrypoint_paths[0].name == "rules.md"


def test_validate_extension_directory_accepts_local_output_style_pack(tmp_path):
    extension_dir = tmp_path / "style-pack"
    extension_dir.mkdir()
    (extension_dir / "styles.yaml").write_text(
        "styles:\n  - name: concise-lab\n    instructions: Keep it concise.\n",
        encoding="utf-8",
    )
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "style-pack",
                "version": "1.0.0",
                "type": "output-style-pack",
                "entrypoints": ["styles.yaml"],
                "trusted_capabilities": ["output-style-entry"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is True
    assert report.extension_type == "output-style-pack"
    assert report.entrypoint_paths[0].name == "styles.yaml"


def test_validate_extension_directory_rejects_hook_manifest_without_capability(tmp_path):
    extension_dir = tmp_path / "hook-pack"
    extension_dir.mkdir()
    (extension_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (extension_dir / "hooks.json").write_text('{"hooks":[]}', encoding="utf-8")
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "hook-pack",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
                "hooks": ["hooks.json"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is False
    assert any("declare hooks must request the 'hooks' trusted capability" in error for error in report.errors)


def test_validate_extension_directory_accepts_local_workflow_pack(tmp_path):
    extension_dir = tmp_path / "workflow-pack"
    extension_dir.mkdir()
    (extension_dir / "workflows.yaml").write_text(
        "workflows:\n  - name: qc\n    steps: [inspect, qc]\n",
        encoding="utf-8",
    )
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "workflow-pack",
                "version": "1.0.0",
                "type": "workflow-pack",
                "entrypoints": ["workflows.yaml"],
                "trusted_capabilities": ["workflow-entry"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is True
    assert report.extension_type == "workflow-pack"
    assert report.entrypoint_paths[0].name == "workflows.yaml"


def test_validate_extension_directory_accepts_local_hook_pack(tmp_path):
    extension_dir = tmp_path / "hook-pack"
    extension_dir.mkdir()
    (extension_dir / "hooks.json").write_text('{"hooks":[{"event":"session_start","message":"hi"}]}', encoding="utf-8")
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "hook-pack",
                "version": "1.0.0",
                "type": "hook-pack",
                "hooks": ["hooks.json"],
                "trusted_capabilities": ["hooks"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is True
    assert report.extension_type == "hook-pack"


def test_validate_extension_directory_rejects_tool_execution_hooks_without_runtime_policy(
    tmp_path,
):
    extension_dir = tmp_path / "runtime-policy-pack"
    extension_dir.mkdir()
    (extension_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (extension_dir / "tool-hooks.json").write_text(
        '{"tool_execution_hooks":[]}',
        encoding="utf-8",
    )
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "runtime-policy-pack",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
                "tool_execution_hooks": ["tool-hooks.json"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is False
    assert any(
        "declare tool_execution_hooks must request the 'runtime-policy' trusted capability"
        in error
        for error in report.errors
    )


def test_validate_extension_directory_accepts_hook_pack_with_tool_execution_hooks_only(
    tmp_path,
):
    extension_dir = tmp_path / "runtime-hook-pack"
    extension_dir.mkdir()
    (extension_dir / "tool-hooks.json").write_text(
        '{"tool_execution_hooks":[{"name":"gate","tools":["alpha"],"pre":{"action":"ask","message":"confirm"}}]}',
        encoding="utf-8",
    )
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "runtime-hook-pack",
                "version": "1.0.0",
                "type": "hook-pack",
                "tool_execution_hooks": ["tool-hooks.json"],
                "trusted_capabilities": ["runtime-policy"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is True
    assert report.extension_type == "hook-pack"


def test_validate_extension_directory_warns_when_runtime_surface_capability_is_omitted(tmp_path):
    extension_dir = tmp_path / "agent-pack"
    extension_dir.mkdir()
    (extension_dir / "agents.yaml").write_text(
        "agents:\n  - name: reviewer\n",
        encoding="utf-8",
    )
    (extension_dir / EXTENSION_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "name": "agent-pack",
                "version": "1.0.0",
                "type": "agent-pack",
                "entrypoints": ["agents.yaml"],
                "trusted_capabilities": ["data-read"],
            }
        ),
        encoding="utf-8",
    )

    report = validate_extension_directory(extension_dir, source_kind="local")

    assert report.valid is True
    assert any("runtime activation will be skipped" in warning for warning in report.warnings)
