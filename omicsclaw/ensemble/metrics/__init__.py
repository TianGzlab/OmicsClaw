"""Registry of internal quality panels, keyed by analysis type.

Data only: this module imports no numerical library, so the agent process can
read which panels exist without paying for numpy. The computation named by
:attr:`PanelDef.compute` is imported by the scoring subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class MetricDef:
    """One metric of a panel.

    ``weight`` 0 marks a diagnostic: reported, never scored. ``higher_is_better``
    describes the raw value. A ``chance_corrected`` metric is scored by its
    corrected value (1 perfect, 0 the level of a random labelling of the same
    sizes); any other is scored by its raw value.
    """

    name: str
    higher_is_better: bool
    weight: float
    description: str
    chance_corrected: bool


@dataclass(frozen=True)
class PanelDef:
    """A panel: its metrics, the dotted path of its compute function, its version."""

    analysis: str
    metrics: Tuple[MetricDef, ...]
    compute: str
    version: str

    @property
    def weights(self) -> Dict[str, float]:
        """Weights of the scored (non-diagnostic) metrics."""
        return {metric.name: metric.weight for metric in self.metrics if metric.weight > 0}


SPATIAL_DOMAINS = PanelDef(
    analysis="spatial_domains",
    metrics=(
        MetricDef(
            "pas",
            higher_is_better=False,
            weight=0.5,
            description=(
                "Fraction of observations whose label differs from more than half "
                "of their 10 nearest spatial neighbours (SpatialPCA PAS)."
            ),
            chance_corrected=True,
        ),
        MetricDef(
            "silhouette_pca",
            higher_is_better=True,
            weight=0.5,
            description="Silhouette of the labels on the input X_pca, in [-1, 1].",
            chance_corrected=False,
        ),
        MetricDef(
            "chaos",
            higher_is_better=False,
            weight=0.0,
            description=(
                "Mean distance from each observation to its nearest neighbour "
                "of the same label, on standardised coordinates (SpatialPCA CHAOS)."
            ),
            chance_corrected=True,
        ),
        MetricDef(
            "spatial_leiden_ami",
            higher_is_better=True,
            weight=0.0,
            description=(
                "Largest adjusted mutual information between the labels and a "
                "Leiden partition of the spatial kNN graph over three resolutions "
                "(adapted from NicheCompass MLAMI)."
            ),
            chance_corrected=True,
        ),
        MetricDef(
            "knn_agreement",
            higher_is_better=True,
            weight=0.0,
            description="Mean fraction of the 10 nearest spatial neighbours sharing the label.",
            chance_corrected=True,
        ),
    ),
    compute="omicsclaw.ensemble.metrics.spatial:compute_panel",
    version="spatial_domains/3",
)

PANELS: Dict[str, PanelDef] = {SPATIAL_DOMAINS.analysis: SPATIAL_DOMAINS}
"""Every registered panel. ``batch_integration`` is reserved and not yet registered."""


def get_panel(analysis: str) -> Optional[PanelDef]:
    """The panel registered for *analysis*, or ``None``."""
    return PANELS.get(analysis)


__all__ = ["MetricDef", "PANELS", "PanelDef", "SPATIAL_DOMAINS", "get_panel"]
