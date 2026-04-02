import sys
from pathlib import Path
from types import SimpleNamespace

from omicsclaw.interactive._omicsclaw_actions import (
    build_skills_catalog_view,
    format_skills_catalog_plain,
    list_registered_skill_names,
    run_skill_command,
)
from omicsclaw.interactive._skill_run_support import SkillRunCommandArgs


def test_build_skills_catalog_view_uses_root_script_metadata(monkeypatch, tmp_path):
    ready_script = tmp_path / "ready.py"
    ready_script.write_text("# ready\n", encoding="utf-8")
    planned_script = tmp_path / "planned.py"
    canonical = {
        "alias": "spatial-preprocess",
        "domain": "spatial",
        "script": ready_script,
        "description": "Preprocess spatial transcriptomics data.",
    }
    fake_script = SimpleNamespace(
        SKILLS={
            "spatial-preprocess": canonical,
            "preprocess": canonical,
            "spatial-domains": {
                "alias": "spatial-domains",
                "domain": "spatial",
                "script": planned_script,
                "description": "Identify spatial domains.",
            },
        },
        DOMAINS={
            "spatial": {
                "name": "Spatial Transcriptomics",
                "primary_data_types": ["h5ad", "csv"],
            }
        },
        _WORKFLOW_ORDER={
            "spatial": ["spatial-preprocess", "spatial-domains"],
        },
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._omicsclaw_actions.load_omicsclaw_script",
        lambda: fake_script,
    )

    view = build_skills_catalog_view("spatial")

    assert view.total_skills == 2
    assert len(view.sections) == 1
    assert view.sections[0].title == "Spatial Transcriptomics"
    assert [skill.alias for skill in view.sections[0].skills] == [
        "spatial-preprocess",
        "spatial-domains",
    ]
    assert view.sections[0].skills[0].available is True
    assert view.sections[0].skills[1].available is False


def test_format_skills_catalog_plain_renders_filter_and_missing_state():
    from omicsclaw.interactive._omicsclaw_actions import SkillsCatalogView

    text = format_skills_catalog_plain(
        SkillsCatalogView(
            total_skills=0,
            filter_value="unknown",
            sections=[],
        )
    )

    assert "OmicsClaw Skills (0 total)" in text
    assert "Filter: unknown" in text
    assert "No skills found for domain: unknown" in text


def test_format_skills_catalog_plain_renders_sections():
    from omicsclaw.interactive._omicsclaw_actions import (
        SkillsCatalogEntry,
        SkillsCatalogSection,
        SkillsCatalogView,
    )

    text = format_skills_catalog_plain(
        SkillsCatalogView(
            total_skills=2,
            filter_value="spatial",
            sections=[
                SkillsCatalogSection(
                    key="spatial",
                    title="Spatial Transcriptomics",
                    data_types=["h5ad", "csv"],
                    skills=[
                        SkillsCatalogEntry(
                            alias="spatial-preprocess",
                            description="Preprocess data.",
                            available=True,
                        ),
                        SkillsCatalogEntry(
                            alias="spatial-domains",
                            description="Identify domains.",
                            available=False,
                        ),
                    ],
                )
            ],
        )
    )

    assert "OmicsClaw Skills (2 total)" in text
    assert "Filter: spatial" in text
    assert "[Spatial Transcriptomics] (2 skills, .h5ad, .csv)" in text
    assert "  [OK] spatial-preprocess" in text
    assert "  [--] spatial-domains" in text


def test_run_skill_command_forwards_skill_run_args(monkeypatch):
    calls: list[tuple[str, str | None, str | None, bool, list[str] | None]] = []

    def _run_skill(
        skill: str,
        *,
        input_path: str | None = None,
        output_dir: str | None = None,
        demo: bool = False,
        extra_args: list[str] | None = None,
    ):
        calls.append((skill, input_path, output_dir, demo, extra_args))
        return {"success": True, "output_dir": output_dir}

    monkeypatch.setattr(
        "omicsclaw.interactive._omicsclaw_actions.load_omicsclaw_script",
        lambda: SimpleNamespace(run_skill=_run_skill),
    )

    result = run_skill_command(
        SkillRunCommandArgs(
            skill="spatial-preprocess",
            demo=True,
            input_path="data.h5ad",
            output_dir="./workspace",
            method="scanpy",
        )
    )

    assert result == {"success": True, "output_dir": "./workspace"}
    assert calls == [
        ("spatial-preprocess", "data.h5ad", "./workspace", True, ["--method", "scanpy"])
    ]


def test_list_registered_skill_names_loads_registry_once(monkeypatch):
    registry = SimpleNamespace(
        _loaded=False,
        skills={"spatial-preprocess": object(), "sc-qc": object()},
    )
    load_calls: list[str] = []

    def _load_all():
        load_calls.append("load")
        registry._loaded = True

    registry.load_all = _load_all

    monkeypatch.setitem(
        sys.modules,
        "omicsclaw.core.registry",
        SimpleNamespace(registry=registry),
    )

    names = list_registered_skill_names()

    assert names == ["sc-qc", "spatial-preprocess"]
    assert load_calls == ["load"]
