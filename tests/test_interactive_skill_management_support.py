import json

from omicsclaw.interactive._skill_management_support import (
    SkillCommandStatus,
    SkillEnablementPlan,
    SkillInstallPlan,
    InstalledSkillEntry,
    InstalledSkillListView,
    SkillRemovalPlan,
    build_extension_install_usage_text,
    build_installed_extension_list_view,
    build_installed_skill_list_view,
    build_refresh_extensions_statuses,
    build_refresh_skills_statuses,
    build_skill_install_usage_text,
    finalize_extension_enablement,
    finalize_installed_skill,
    finalize_uninstalled_skill,
    format_installed_extension_list_plain,
    format_installed_skill_list_plain,
    install_extension_from_source,
    prepare_extension_enablement_plan,
    prepare_extension_install_plan,
    prepare_extension_uninstall_plan,
    prepare_skill_install_plan,
    prepare_skill_uninstall_plan,
    set_installed_extension_enabled,
)


def test_prepare_skill_install_plan_rejects_empty_source(tmp_path):
    result = prepare_skill_install_plan("", omicsclaw_dir=tmp_path)

    assert isinstance(result, SkillCommandStatus)
    assert result.level == "error"
    assert result.text == build_skill_install_usage_text()


def test_prepare_extension_install_plan_builds_github_tree_plan(tmp_path):
    result = prepare_extension_install_plan(
        "https://github.com/user/repo/tree/main/skills/my-skill",
        omicsclaw_dir=tmp_path,
    )

    assert isinstance(result, SkillInstallPlan)
    assert result.source_kind == "github"
    assert result.skill_name == "my-skill"
    assert result.repo_url == "https://github.com/user/repo.git"
    assert result.repo_branch == "main"
    assert result.repo_subpath == "skills/my-skill"


def test_prepare_extension_install_plan_rejects_missing_local_dir(tmp_path):
    result = prepare_extension_install_plan(
        str(tmp_path / "missing"),
        omicsclaw_dir=tmp_path,
    )

    assert isinstance(result, SkillCommandStatus)
    assert result.level == "error"
    assert "Path not found:" in result.text


def test_finalize_installed_skill_reports_validation_and_refresh(monkeypatch, tmp_path):
    dest = tmp_path / "skills" / "user" / "my-skill"
    dest.mkdir(parents=True)
    (dest / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (dest / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: demo\nversion: 1.0.0\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "",
    )

    statuses = finalize_installed_skill(
        SkillInstallPlan(
            source_kind="local",
            skill_name="my-skill",
            dest=dest,
            source_path=dest,
            expected_type="skill-pack",
        )
    )

    assert statuses[0].text.startswith("Validated extension candidate:")
    assert statuses[-1].level == "success"
    assert "installed and registered" in statuses[-1].text
    assert (dest / ".omicsclaw-install.json").exists()
    assert (dest / ".omicsclaw-extension-state.json").exists()


def test_install_extension_from_source_installs_local_prompt_pack(monkeypatch, tmp_path):
    source = tmp_path / "my-prompts"
    source.mkdir()
    (source / "rules.md").write_text("# rules\n", encoding="utf-8")
    (source / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": "my-prompts",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "",
    )

    statuses = install_extension_from_source(str(source), omicsclaw_dir=tmp_path)

    assert statuses[0].text.startswith("Staging 'my-prompts'")
    assert any(
        status.level == "success" and "(prompt-pack) installed" in status.text
        for status in statuses
    )
    installed = tmp_path / "installed_extensions" / "prompt-packs" / "my-prompts"
    assert installed.exists()


def test_install_extension_from_source_rejects_untrusted_prompt_pack(monkeypatch, tmp_path):
    source = tmp_path / "my-prompts"
    source.mkdir()
    (source / "rules.md").write_text("# rules\n", encoding="utf-8")
    (source / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": "my-prompts",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
            }
        ),
        encoding="utf-8",
    )
    plan = SkillInstallPlan(
        source_kind="github",
        skill_name="my-prompts",
        source_path=source,
        expected_type="",
    )

    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support._stage_github_source",
        lambda _plan, _staging_root: (source, SkillCommandStatus("success", "cloned")),
    )

    statuses = install_extension_from_source("https://github.com/user/my-prompts", omicsclaw_dir=tmp_path)

    assert any("only install 'skill-pack'" in status.text for status in statuses)


def test_install_extension_from_source_emits_extension_hook_notice(monkeypatch, tmp_path):
    source = tmp_path / "hook-pack"
    source.mkdir()
    (source / "rules.md").write_text("# rules\n", encoding="utf-8")
    (source / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "name": "install-notice",
                        "event": "extension_installed",
                        "message": "Installed extension {extension_name} at {install_path}.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (source / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": "hook-pack",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
                "hooks": ["hooks.json"],
                "trusted_capabilities": ["hooks"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "",
    )

    statuses = install_extension_from_source(str(source), omicsclaw_dir=tmp_path)

    assert any(
        status.level == "info"
        and "Hook notice: Installed extension hook-pack at" in status.text
        for status in statuses
    )


def test_prepare_extension_uninstall_plan_identifies_removable_extension(tmp_path):
    candidate = tmp_path / "installed_extensions" / "prompt-packs" / "my-prompts"
    candidate.mkdir(parents=True)
    (candidate / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"my-prompts","source_kind":"local","source":"/tmp/prompts",'
            '"installed_at":"2026-04-01T00:00:00+00:00","extension_type":"prompt-pack"}'
        ),
        encoding="utf-8",
    )

    result = prepare_extension_uninstall_plan("my-prompts", omicsclaw_dir=tmp_path)

    assert result == SkillRemovalPlan(
        skill_name="my-prompts",
        candidate=candidate,
        extension_type="prompt-pack",
    )


def test_prepare_skill_uninstall_plan_reports_builtin_skill(tmp_path):
    builtin = tmp_path / "skills" / "spatial" / "my-skill"
    builtin.mkdir(parents=True)

    result = prepare_skill_uninstall_plan("my-skill", omicsclaw_dir=tmp_path)

    assert isinstance(result, SkillCommandStatus)
    assert result.level == "warning"
    assert "built-in skill" in result.text


def test_finalize_uninstalled_skill_warns_when_refresh_fails(monkeypatch, tmp_path):
    plan = SkillRemovalPlan(
        skill_name="my-skill",
        candidate=tmp_path / "skills" / "user" / "my-skill",
        extension_type="skill-pack",
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "registry locked",
    )

    status = finalize_uninstalled_skill(plan)

    assert status.level == "warning"
    assert "registry locked" in status.text


def test_prepare_extension_enablement_plan_and_finalize(monkeypatch, tmp_path):
    skill_dir = tmp_path / "skills" / "user" / "tracked-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"tracked-skill","source_kind":"local","source":"/tmp/tracked-skill",'
            '"installed_at":"2026-04-01T00:00:00+00:00","extension_type":"skill-pack"}'
        ),
        encoding="utf-8",
    )
    (skill_dir / ".omicsclaw-extension-state.json").write_text(
        '{"enabled": false, "updated_at": "2026-04-01T00:00:00+00:00", "disabled_reason": "manual"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "",
    )

    plan = prepare_extension_enablement_plan(
        "tracked-skill",
        enable=True,
        omicsclaw_dir=tmp_path,
    )

    assert isinstance(plan, SkillEnablementPlan)
    status = finalize_extension_enablement(plan)
    assert status.level == "success"
    assert "enabled" in status.text


def test_set_installed_extension_enabled_reports_already_enabled(tmp_path):
    skill_dir = tmp_path / "skills" / "user" / "tracked-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"tracked-skill","source_kind":"local","source":"/tmp/tracked-skill",'
            '"installed_at":"2026-04-01T00:00:00+00:00","extension_type":"skill-pack"}'
        ),
        encoding="utf-8",
    )

    statuses = set_installed_extension_enabled(
        "tracked-skill",
        enable=True,
        omicsclaw_dir=tmp_path,
    )

    assert statuses[0].level == "warning"
    assert "already enabled" in statuses[0].text


def test_build_installed_extension_list_view_marks_tracked_and_disabled_entries(tmp_path):
    tracked = tmp_path / "installed_extensions" / "prompt-packs" / "tracked-prompts"
    tracked.mkdir(parents=True)
    (tracked / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": "tracked-prompts",
                "version": "1.2.3",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
                "trusted_capabilities": ["prompt-rules"],
            }
        ),
        encoding="utf-8",
    )
    (tracked / "rules.md").write_text("# rules\n", encoding="utf-8")
    (tracked / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"tracked-prompts","source_kind":"local","source":"/tmp/prompts",'
            '"installed_at":"2026-04-01T00:00:00+00:00","manifest_version":"1.2.3",'
            '"trusted_capabilities":["prompt-rules"],"extension_type":"prompt-pack"}'
        ),
        encoding="utf-8",
    )
    (tracked / ".omicsclaw-extension-state.json").write_text(
        '{"enabled": false, "updated_at": "2026-04-01T00:00:00+00:00", "disabled_reason": "manual"}',
        encoding="utf-8",
    )
    legacy = tmp_path / "skills" / "user" / "legacy-skill"
    legacy.mkdir(parents=True)

    view = build_installed_extension_list_view(omicsclaw_dir=tmp_path)

    assert [entry.skill_name for entry in view.entries] == ["tracked-prompts", "legacy-skill"]
    assert view.entries[0].tracked is True
    assert view.entries[0].enabled is False
    assert view.entries[0].extension_type == "prompt-pack"
    assert view.entries[0].inactive_surfaces == ["prompts: manual"]
    assert view.entries[1].tracked is False


def test_build_installed_skill_list_view_filters_to_skill_packs(tmp_path):
    tracked = tmp_path / "skills" / "user" / "tracked-skill"
    tracked.mkdir(parents=True)
    (tracked / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"tracked-skill","source_kind":"github","source":"https://github.com/user/tracked",'
            '"installed_at":"2026-04-01T00:00:00+00:00","manifest_version":"1.2.3","extension_type":"skill-pack"}'
        ),
        encoding="utf-8",
    )
    prompt_pack = tmp_path / "installed_extensions" / "prompt-packs" / "tracked-prompts"
    prompt_pack.mkdir(parents=True)
    (prompt_pack / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"tracked-prompts","source_kind":"local","source":"/tmp/prompts",'
            '"installed_at":"2026-04-02T00:00:00+00:00","extension_type":"prompt-pack"}'
        ),
        encoding="utf-8",
    )

    view = build_installed_skill_list_view(omicsclaw_dir=tmp_path)

    assert [entry.skill_name for entry in view.entries] == ["tracked-skill"]


def test_format_installed_extension_list_plain_renders_audit_details():
    text = format_installed_extension_list_plain(
        InstalledSkillListView(
            entries=[
                InstalledSkillEntry(
                    skill_name="tracked-prompts",
                    extension_type="prompt-pack",
                    source_kind="local",
                    source="/tmp/prompts",
                    manifest_version="1.2.3",
                    installed_label="just now",
                    tracked=True,
                    enabled=False,
                    disabled_reason="manual",
                    trusted_capabilities=["prompt-rules"],
                    inactive_surfaces=["prompts: manual"],
                    path="/tmp/installed_extensions/prompt-packs/tracked-prompts",
                ),
                InstalledSkillEntry(
                    skill_name="legacy-skill",
                    extension_type="skill-pack",
                    tracked=False,
                    active_surfaces=["skills(1)"],
                    path="/tmp/skills/user/legacy-skill",
                ),
            ]
        )
    )

    assert "Installed extensions:" in text
    assert "tracked: tracked-prompts · prompt-pack · disabled · v1.2.3 · local · just now" in text
    assert "inactive surfaces: prompts: manual" in text
    assert "capabilities: prompt-rules" in text
    assert "legacy: legacy-skill · skill-pack · enabled" in text
    assert "active surfaces: skills(1)" in text


def test_format_installed_skill_list_plain_preserves_header():
    text = format_installed_skill_list_plain(
        InstalledSkillListView(
            entries=[
                InstalledSkillEntry(
                    skill_name="tracked-skill",
                    extension_type="skill-pack",
                    tracked=True,
                    path="/tmp/skills/user/tracked-skill",
                )
            ]
        )
    )

    assert text.startswith("Installed user skills:")


def test_build_refresh_extensions_statuses_reports_inventory(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "",
    )
    user_skill = tmp_path / "skills" / "user" / "tracked-skill"
    user_skill.mkdir(parents=True)
    (user_skill / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"tracked-skill","source_kind":"local","source":"/tmp/tracked-skill",'
            '"installed_at":"2026-04-01T00:00:00+00:00","extension_type":"skill-pack"}'
        ),
        encoding="utf-8",
    )

    statuses = build_refresh_extensions_statuses(omicsclaw_dir=tmp_path)

    assert statuses[0].level == "success"
    assert statuses[0].text == "Extension system refreshed."
    assert statuses[1].level == "info"
    assert "skill-pack=1" in statuses[1].text
    assert statuses[2].level == "info"
    assert "skills=1" in statuses[2].text


def test_install_extension_from_source_tracks_hook_pack_as_disabled(monkeypatch, tmp_path):
    source = tmp_path / "lab-hooks"
    source.mkdir()
    (source / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "name": "session-reminder",
                        "event": "session_start",
                        "message": "Remember to inspect metadata first.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (source / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": "lab-hooks",
                "version": "1.0.0",
                "type": "hook-pack",
                "hooks": ["hooks.json"],
                "trusted_capabilities": ["hooks"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "",
    )

    statuses = install_extension_from_source(str(source), omicsclaw_dir=tmp_path)

    assert any(
        status.level == "info" and "Hook packs install in a gated state" in status.text
        for status in statuses
    )
    installed = tmp_path / "installed_extensions" / "hook-packs" / "lab-hooks"
    state = json.loads((installed / ".omicsclaw-extension-state.json").read_text(encoding="utf-8"))
    assert state["enabled"] is False


def test_build_refresh_skills_statuses_reports_detected_user_packs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "omicsclaw.interactive._skill_management_support.refresh_skill_registry",
        lambda: "",
    )
    user_skill = tmp_path / "skills" / "user" / "tracked-skill"
    user_skill.mkdir(parents=True)
    (user_skill / ".omicsclaw-install.json").write_text(
        (
            '{"extension_name":"tracked-skill","source_kind":"local","source":"/tmp/tracked-skill",'
            '"installed_at":"2026-04-01T00:00:00+00:00","extension_type":"skill-pack"}'
        ),
        encoding="utf-8",
    )

    statuses = build_refresh_skills_statuses(omicsclaw_dir=tmp_path)

    assert statuses[0].level == "success"
    assert statuses[0].text == "Skill registry refreshed."
    assert statuses[1].level == "info"
    assert "User-installed skill packs detected: 1" in statuses[1].text
