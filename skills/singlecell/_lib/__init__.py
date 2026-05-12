"""Single-cell analysis utilities for OmicsClaw.

Attributes are loaded lazily via PEP 562 so that simply touching this
package does not pull in scanpy / matplotlib / numpy. The skill ``--help``
contract (lightweight venv must be able to parse ``argparse``) relies on
this: a singlecell script's import of ``from skills.singlecell._lib.qc
import X`` should not transitively force ``import scanpy`` at startup
just because ``gallery``/``upstream``/``viz`` happen to need it later.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__version__ = "0.1.0"

__all__ = [
    "FastqSample",
    "PlotArtifact",
    "PlotSpec",
    "VisualizationRecipe",
    "render_plot_specs",
    "save_figure",
]

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "FastqSample": (".upstream", "FastqSample"),
    "PlotArtifact": (".gallery", "PlotArtifact"),
    "PlotSpec": (".gallery", "PlotSpec"),
    "VisualizationRecipe": (".gallery", "VisualizationRecipe"),
    "render_plot_specs": (".gallery", "render_plot_specs"),
    "save_figure": (".viz", "save_figure"),
}


def __getattr__(name: str):
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))


if TYPE_CHECKING:
    from .gallery import PlotArtifact, PlotSpec, VisualizationRecipe, render_plot_specs
    from .upstream import FastqSample
    from .viz import save_figure
