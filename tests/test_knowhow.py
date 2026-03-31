from pathlib import Path

from omicsclaw.knowledge.knowhow import KnowHowInjector


ROOT = Path(__file__).resolve().parent.parent
KNOWHOW_DIR = ROOT / "knowledge_base" / "knowhows"


def test_spatial_svg_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-svg-detection")

    assert "KH-spatial-genes-guardrails.md" in matched


def test_spatial_preprocess_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-preprocessing")

    assert "KH-spatial-preprocess-guardrails.md" in matched


def test_spatial_preprocess_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="spatial-preprocessing",
        query="Please preprocess this Xenium dataset and explain the QC thresholds first.",
        domain="spatial",
    )

    assert "Spatial Preprocess Guardrails" in constraints
    assert "knowledge_base/skill-guides/spatial/spatial-preprocess.md" in constraints


def test_spatial_svg_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="spatial-svg-detection",
        query="Please find spatially variable genes with Moran and explain tuning.",
        domain="spatial",
    )

    assert "Spatial SVG Analysis Guardrails" in constraints
    assert "knowledge_base/skill-guides/spatial/spatial-genes.md" in constraints


def test_spatial_domain_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-domain-identification")

    assert "KH-spatial-domain-guardrails.md" in matched


def test_spatial_integration_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-integration")

    assert "KH-spatial-integrate-guardrails.md" in matched


def test_spatial_integration_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="spatial-integration",
        query="Please integrate these batches with Harmony and explain theta and lambda.",
        domain="spatial",
    )

    assert "Spatial Integration Guardrails" in constraints
    assert "knowledge_base/skill-guides/spatial/spatial-integrate.md" in constraints


def test_spatial_communication_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-cell-communication")

    assert "KH-spatial-communication-guardrails.md" in matched


def test_spatial_communication_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="spatial-cell-communication",
        query="Please run cell-cell communication with LIANA and explain expr_prop and min_cells first.",
        domain="spatial",
    )

    assert "Spatial Communication Guardrails" in constraints
    assert "knowledge_base/skill-guides/spatial/spatial-communication.md" in constraints


def test_spatial_deconv_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-deconvolution")

    assert "KH-spatial-deconv-guardrails.md" in matched


def test_spatial_deconv_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="spatial-deconvolution",
        query="Please run cell type deconvolution with Cell2location and explain n_cells_per_spot first.",
        domain="spatial",
    )

    assert "Spatial Deconvolution Guardrails" in constraints
    assert "knowledge_base/skill-guides/spatial/spatial-deconv.md" in constraints


def test_spatial_register_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-registration")

    assert "KH-spatial-register-guardrails.md" in matched


def test_spatial_register_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="spatial-registration",
        query="Please align these serial sections with PASTE and explain alpha first.",
        domain="spatial",
    )

    assert "Spatial Registration Guardrails" in constraints
    assert "knowledge_base/skill-guides/spatial/spatial-register.md" in constraints


def test_spatial_trajectory_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-trajectory")

    assert "KH-spatial-trajectory-guardrails.md" in matched


def test_spatial_trajectory_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="spatial-trajectory",
        query="Please run CellRank on this dataset and explain n_states and frac_to_keep first.",
        domain="spatial",
    )

    assert "Spatial Trajectory Guardrails" in constraints
    assert "knowledge_base/skill-guides/spatial/spatial-trajectory.md" in constraints


def test_sc_qc_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("sc-qc")

    assert "KH-sc-qc-guardrails.md" in matched


def test_sc_qc_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="sc-qc",
        query="Please run single-cell QC and explain mitochondrial percentage interpretation first.",
        domain="singlecell",
    )

    assert "Single-Cell QC Guardrails" in constraints
    assert "knowledge_base/skill-guides/singlecell/sc-qc.md" in constraints


def test_sc_preprocessing_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("sc-preprocessing")

    assert "KH-sc-preprocessing-guardrails.md" in matched


def test_sc_preprocessing_constraints_use_guardrail_doc():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="sc-preprocessing",
        query="Please preprocess this single-cell dataset with SCTransform and explain QC thresholds first.",
        domain="singlecell",
    )

    assert "Single-Cell Preprocessing Guardrails" in constraints
    assert "knowledge_base/skill-guides/singlecell/sc-preprocessing.md" in constraints


def test_global_best_practices_are_always_injected_with_skill_match():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="sc-qc",
        query="Please run single-cell QC first.",
        domain="singlecell",
    )

    assert "Best practices for data analyses" in constraints
    assert "Single-Cell QC Guardrails" in constraints


def test_query_only_fallback_matches_cross_skill_knowhow():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    constraints = injector.get_constraints(
        skill="",
        query="Please run pathway enrichment with GSEA on these DEGs.",
        domain="singlecell",
    )

    assert "Pathway Enrichment Analysis" in constraints


def test_frontmatter_alias_keys_are_supported(tmp_path: Path):
    kh_path = tmp_path / "KH-custom-dynamic.md"
    kh_path.write_text(
        """---
doc_id: custom-dynamic
title: Custom Dynamic KH
doc_type: knowhow
critical_rule: MUST prove dynamic frontmatter parsing works
domains: [singlecell]
skills: [custom-skill]
keywords: [custom phrase]
phase: [before_run]
priority: 0.8
---

# Custom Dynamic KH

This is a synthetic KH document for testing.
""",
        encoding="utf-8",
    )

    injector = KnowHowInjector(knowhows_dir=tmp_path)

    matched = injector.get_kh_for_skill("custom-skill")
    constraints = injector.get_constraints(
        skill="custom-skill",
        query="Please run custom phrase first.",
        domain="singlecell",
    )

    assert matched == ["KH-custom-dynamic.md"]
    assert "Custom Dynamic KH" in constraints


def test_phase_filter_uses_normalized_phase_names(tmp_path: Path):
    (tmp_path / "KH-before.md").write_text(
        """---
doc_id: custom-before
title: Custom Before KH
doc_type: knowhow
critical_rule: MUST run before execution
domains: [singlecell]
skills: [custom-skill]
keywords: [custom phrase]
phase: [before_run]
priority: 0.7
---

# Custom Before KH

Before-run rules.
""",
        encoding="utf-8",
    )
    (tmp_path / "KH-after.md").write_text(
        """---
doc_id: custom-after
title: Custom After KH
doc_type: knowhow
critical_rule: MUST inspect outputs after execution
domains: [singlecell]
skills: [custom-skill]
keywords: [custom phrase]
phase: [after_run]
priority: 0.9
---

# Custom After KH

After-run rules.
""",
        encoding="utf-8",
    )

    injector = KnowHowInjector(knowhows_dir=tmp_path)

    assert injector.get_matching_kh_ids(skill="custom-skill", phase="before_run") == [
        "KH-before.md",
    ]
    assert injector.get_matching_kh_ids(skill="custom-skill", phase="post_run") == [
        "KH-after.md",
    ]

    constraints = injector.get_constraints(
        skill="custom-skill",
        query="Please run custom phrase first.",
        domain="singlecell",
        phase="post_run",
    )
    assert "Custom After KH" in constraints
    assert "Custom Before KH" not in constraints
