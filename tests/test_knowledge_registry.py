from omicsclaw.knowledge.registry import KnowledgeRegistry, validate_frontmatter


def test_registry_normalizes_kh_alias_fields_and_phase_alias(tmp_path):
    doc = tmp_path / "KH-custom-registry.md"
    doc.write_text(
        """---
doc_id: custom-registry
title: Custom Registry KH
doc_type: knowhow
critical_rule: MUST keep alias metadata normalized
domains: [singlecell]
skills: [custom-skill]
keywords: [custom phrase]
phase: [after_run]
priority: 0.8
---

# Custom Registry KH

Registry alias test.
""",
        encoding="utf-8",
    )

    registry = KnowledgeRegistry()
    summary = registry.build_from_directory(tmp_path)

    assert summary["validation_warnings"] == []

    results = registry.lookup(
        skill="custom-skill",
        domain="singlecell",
        phase="post_run",
    )
    assert len(results) == 1
    meta = results[0]
    assert meta["related_skills"] == ["custom-skill"]
    assert meta["search_terms"] == ["custom phrase"]
    assert meta["phases"] == ["post_run"]
    assert meta["critical_rule"] == "MUST keep alias metadata normalized"


def test_validate_frontmatter_accepts_kh_alias_keys():
    errors = validate_frontmatter(
        {
            "doc_id": "custom-dynamic",
            "title": "Custom Dynamic KH",
            "doc_type": "knowhow",
            "critical_rule": "MUST parse alias fields",
            "domains": ["singlecell"],
            "skills": ["custom-skill"],
            "keywords": ["custom phrase"],
            "phase": ["after_run"],
            "priority": 0.8,
        }
    )

    assert errors == []
