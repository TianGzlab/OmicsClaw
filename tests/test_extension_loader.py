import json

from omicsclaw.core.registry import OmicsRegistry
from omicsclaw.extensions import (
    EXTENSION_STATE_FILENAME,
    INSTALL_RECORD_FILENAME,
    ExtensionManifest,
    extension_store_dir,
    list_installed_extension_records,
    list_installed_extensions,
    load_extension_state,
    load_install_record,
    set_extension_enabled,
    write_extension_state,
    write_install_record,
)


def test_write_and_load_install_record_roundtrip(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    manifest = ExtensionManifest(
        name="my-skill",
        version="1.0.0",
        type="skill-pack",
        trusted_capabilities=["skill-run"],
        dependencies=["scanpy"],
    )

    record_path = write_install_record(
        skill_dir,
        extension_name="my-skill",
        source_kind="github",
        source="https://github.com/user/my-skill",
        manifest=manifest,
        relative_install_path="skills/user/my-skill",
    )
    loaded = load_install_record(skill_dir)

    assert record_path == skill_dir / INSTALL_RECORD_FILENAME
    assert loaded is not None
    assert loaded.extension_name == "my-skill"
    assert loaded.skill_name == "my-skill"
    assert loaded.source_kind == "github"
    assert loaded.manifest_name == "my-skill"
    assert loaded.manifest_version == "1.0.0"
    assert loaded.trusted_capabilities == ["skill-run"]
    assert loaded.dependencies == ["scanpy"]
    assert loaded.relative_install_path == "skills/user/my-skill"

    raw = json.loads(record_path.read_text(encoding="utf-8"))
    assert raw["extension_type"] == "skill-pack"


def test_extension_state_roundtrip_and_toggle(tmp_path):
    extension_dir = tmp_path / "my-skill"
    extension_dir.mkdir()

    state_path = write_extension_state(
        extension_dir,
        enabled=False,
        disabled_reason="testing disable",
    )
    state = load_extension_state(extension_dir)

    assert state_path == extension_dir / EXTENSION_STATE_FILENAME
    assert state.enabled is False
    assert state.disabled_reason == "testing disable"

    updated = set_extension_enabled(extension_dir, enabled=True)
    assert updated.enabled is True
    assert updated.disabled_reason == ""


def test_list_installed_extension_records_includes_untracked_dirs(tmp_path):
    tracked_dir = tmp_path / "tracked-skill"
    tracked_dir.mkdir()
    write_install_record(
        tracked_dir,
        extension_name="tracked-skill",
        source_kind="local",
        source="/tmp/tracked-skill",
    )
    legacy_dir = tmp_path / "legacy-skill"
    legacy_dir.mkdir()

    records = list_installed_extension_records(tmp_path)

    assert len(records) == 2
    assert records[0][0].name == "legacy-skill"
    assert records[0][1] is None
    assert records[1][0].name == "tracked-skill"
    assert records[1][1] is not None


def test_list_installed_extensions_reads_multiple_type_roots(tmp_path):
    skill_dir = extension_store_dir(tmp_path, "skill-pack") / "my-skill"
    skill_dir.mkdir(parents=True)
    write_install_record(
        skill_dir,
        extension_name="my-skill",
        source_kind="local",
        source="/tmp/my-skill",
        extension_type="skill-pack",
    )

    prompt_dir = extension_store_dir(tmp_path, "prompt-pack") / "my-prompts"
    prompt_dir.mkdir(parents=True)
    write_install_record(
        prompt_dir,
        extension_name="my-prompts",
        source_kind="local",
        source="/tmp/my-prompts",
        extension_type="prompt-pack",
    )
    write_extension_state(
        prompt_dir,
        enabled=False,
        disabled_reason="manual disable",
    )

    workflow_dir = extension_store_dir(tmp_path, "workflow-pack") / "my-workflows"
    workflow_dir.mkdir(parents=True)
    write_install_record(
        workflow_dir,
        extension_name="my-workflows",
        source_kind="local",
        source="/tmp/my-workflows",
        extension_type="workflow-pack",
    )

    style_dir = extension_store_dir(tmp_path, "output-style-pack") / "my-styles"
    style_dir.mkdir(parents=True)
    write_install_record(
        style_dir,
        extension_name="my-styles",
        source_kind="local",
        source="/tmp/my-styles",
        extension_type="output-style-pack",
    )

    inventory = list_installed_extensions(tmp_path)

    assert sorted((item.extension_type, item.path.name) for item in inventory) == [
        ("output-style-pack", "my-styles"),
        ("prompt-pack", "my-prompts"),
        ("skill-pack", "my-skill"),
        ("workflow-pack", "my-workflows"),
    ]
    by_type = {item.extension_type: item for item in inventory}
    assert by_type["output-style-pack"].state.enabled is True
    assert by_type["prompt-pack"].state.enabled is False
    assert by_type["prompt-pack"].state.disabled_reason == "manual disable"
    assert by_type["skill-pack"].state.enabled is True
    assert by_type["workflow-pack"].state.enabled is True


def test_registry_skips_disabled_skill_pack(tmp_path):
    skill_dir = tmp_path / "skills" / "user" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "my_skill.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: demo skill\nversion: 1.0.0\n---\n",
        encoding="utf-8",
    )
    write_extension_state(
        skill_dir,
        enabled=False,
        disabled_reason="disabled in test",
    )

    registry = OmicsRegistry()
    registry.load_all(tmp_path / "skills")

    assert "my-skill" not in registry.skills
