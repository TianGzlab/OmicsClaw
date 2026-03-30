"""Narrative gallery protocol for SpatialClaw standard result figures.

This module sits one level above the low-level plotting primitives.  It lets a
skill declare a stable set of default story plots using lightweight metadata,
then renders those plots and writes a manifest for downstream consumers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


@dataclass
class PlotSpec:
    """Declarative description of one gallery plot."""

    plot_id: str
    role: str
    renderer: str
    filename: str
    title: str | None = None
    description: str | None = None
    backend: str = "python"
    params: dict[str, Any] = field(default_factory=dict)
    required_obs: list[str] = field(default_factory=list)
    required_obsm: list[str] = field(default_factory=list)
    required_uns: list[str] = field(default_factory=list)


@dataclass
class VisualizationRecipe:
    """Ordered plot recipe for a skill's standard gallery."""

    recipe_id: str
    skill_name: str
    title: str
    description: str = ""
    backend: str = "python"
    plots: list[PlotSpec] = field(default_factory=list)


@dataclass
class PlotArtifact:
    """Concrete render outcome for one plot specification."""

    plot_id: str
    role: str
    backend: str
    renderer: str
    filename: str
    title: str | None
    description: str | None
    status: str
    path: str = ""
    skip_reason: str | None = None
    error: str | None = None


Renderer = Callable[[Any, PlotSpec, dict[str, Any]], Any]


def _check_requirements(adata: Any, spec: PlotSpec) -> list[str]:
    missing: list[str] = []
    for key in spec.required_obs:
        if key not in getattr(adata, "obs", {}).columns:
            missing.append(f"obs:{key}")
    for key in spec.required_obsm:
        if key not in getattr(adata, "obsm", {}):
            missing.append(f"obsm:{key}")
    for key in spec.required_uns:
        if key not in getattr(adata, "uns", {}):
            missing.append(f"uns:{key}")
    return missing


def _save_gallery_figure(fig: plt.Figure, output_dir: Path, filename: str, dpi: int = 200) -> Path:
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    path = fig_dir / filename
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved gallery figure: %s", path)
    return path


def _write_gallery_manifest(output_dir: Path, recipe: VisualizationRecipe, artifacts: list[PlotArtifact]) -> Path:
    manifest = {
        "recipe_id": recipe.recipe_id,
        "skill_name": recipe.skill_name,
        "title": recipe.title,
        "description": recipe.description,
        "backend": recipe.backend,
        "plots": [asdict(artifact) for artifact in artifacts],
    }
    manifest_path = output_dir / "figures" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest_path


def render_plot_specs(
    adata: Any,
    output_dir: str | Path,
    recipe: VisualizationRecipe,
    renderers: dict[str, Renderer],
    *,
    context: dict[str, Any] | None = None,
) -> list[PlotArtifact]:
    """Render a visualization recipe into ``<output_dir>/figures``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_context = context or {}
    artifacts: list[PlotArtifact] = []

    for spec in recipe.plots:
        artifact = PlotArtifact(
            plot_id=spec.plot_id,
            role=spec.role,
            backend=spec.backend,
            renderer=spec.renderer,
            filename=spec.filename,
            title=spec.title,
            description=spec.description,
            status="pending",
        )

        if spec.backend != recipe.backend:
            artifact.status = "skipped"
            artifact.skip_reason = (
                f"Plot backend '{spec.backend}' does not match recipe backend '{recipe.backend}'."
            )
            artifacts.append(artifact)
            continue

        renderer = renderers.get(spec.renderer)
        if renderer is None:
            artifact.status = "skipped"
            artifact.skip_reason = f"No renderer registered for '{spec.renderer}'."
            artifacts.append(artifact)
            continue

        missing = _check_requirements(adata, spec)
        if missing:
            artifact.status = "skipped"
            artifact.skip_reason = f"Missing required inputs: {', '.join(missing)}"
            artifacts.append(artifact)
            continue

        try:
            rendered = renderer(adata, spec, runtime_context)
            if rendered is None:
                artifact.status = "skipped"
                artifact.skip_reason = "Renderer returned no figure."
            elif isinstance(rendered, plt.Figure):
                out_path = _save_gallery_figure(
                    rendered,
                    output_dir,
                    spec.filename,
                    dpi=int(spec.params.get("dpi", 200)),
                )
                artifact.status = "rendered"
                artifact.path = str(out_path)
            else:
                out_path = Path(rendered)
                artifact.status = "rendered"
                artifact.path = str(out_path)
        except Exception as exc:  # pragma: no cover - error path
            artifact.status = "failed"
            artifact.error = str(exc)
            logger.warning("Gallery plot '%s' failed: %s", spec.plot_id, exc)

        artifacts.append(artifact)

    _write_gallery_manifest(output_dir, recipe, artifacts)
    return artifacts
