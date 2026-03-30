from pathlib import Path

from omicsclaw.knowledge.knowhow import KnowHowInjector


ROOT = Path(__file__).resolve().parent.parent
KNOWHOW_DIR = ROOT / "knowledge_base" / "knowhows"


def test_spatial_svg_guardrail_is_registered_for_skill():
    injector = KnowHowInjector(knowhows_dir=KNOWHOW_DIR)

    matched = injector.get_kh_for_skill("spatial-svg-detection")

    assert "KH-spatial-genes-guardrails.md" in matched


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
