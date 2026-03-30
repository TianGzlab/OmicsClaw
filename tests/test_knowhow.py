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
