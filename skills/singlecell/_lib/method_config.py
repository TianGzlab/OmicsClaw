"""SingleCell MethodConfig — unified method registration for single-cell skills.

Provides a standard framework for registering analysis methods with their
dependencies, GPU support, and R requirements. Mirrors the pattern used
in spatial skills (e.g. spatial_deconv.py METHOD_REGISTRY).

Usage in a skill script::

    from .method_config import MethodConfig, check_method_available

    METHOD_REGISTRY = {
        "harmony": MethodConfig(
            name="harmony",
            description="Fast linear batch correction",
            dependencies=("harmonypy",),
        ),
        "scvi": MethodConfig(
            name="scvi",
            description="Variational autoencoder integration",
            dependencies=("scvi", "torch"),
            supports_gpu=True,
        ),
    }

    # At runtime:
    cfg = METHOD_REGISTRY[method]
    ok, msg = check_method_available(cfg)
    if not ok:
        raise RuntimeError(msg)
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MethodConfig:
    """Configuration for a single analysis method within a skill."""

    name: str
    description: str
    dependencies: tuple[str, ...] = ()
    supports_gpu: bool = False
    requires_layers: tuple[str, ...] = ()
    requires_obs_keys: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------

# Map package names to their actual importable module names
_IMPORT_ALIASES: dict[str, str] = {
    "harmonypy": "harmonypy",
    "harmony-pytorch": "harmony",
    "scvi": "scvi",
    "scvi-tools": "scvi",
    "torch": "torch",
    "bbknn": "bbknn",
    "scanorama": "scanorama",
    "scrublet": "scrublet",
    "celltypist": "celltypist",
    "palantir": "palantir",
    "scvelo": "scvelo",
    "cellbender": "cellbender",
    "pydeseq2": "pydeseq2",
    "pyscenic": "pyscenic",
    "tangram": "tangram",
    "liana": "liana",
    "seaborn": "seaborn",
}


def check_method_available(cfg: MethodConfig) -> tuple[bool, str]:
    """Check whether all dependencies for a method are installed.

    Returns
    -------
    (available, message)
        ``True`` + empty string when ready, or ``False`` + human-readable
        explanation of what is missing and how to install it.
    """
    missing: list[str] = []
    for dep in cfg.dependencies:
        module_name = _IMPORT_ALIASES.get(dep, dep)
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(dep)

    if missing:
        install_hint = "pip install " + " ".join(missing)
        return False, (
            f"Method '{cfg.name}' requires: {', '.join(missing)}. "
            f"Install with: {install_hint}"
        )
    return True, ""


def get_available_methods(registry: dict[str, MethodConfig]) -> list[str]:
    """Return method names whose dependencies are satisfied."""
    available = []
    for name, cfg in registry.items():
        ok, _ = check_method_available(cfg)
        if ok:
            available.append(name)
    return available


def validate_method_choice(
    method: str,
    registry: dict[str, MethodConfig],
    *,
    fallback: str | None = None,
) -> str:
    """Validate and potentially fall back to an available method.

    Parameters
    ----------
    method
        User-requested method name.
    registry
        The skill's METHOD_REGISTRY.
    fallback
        If provided and *method* is unavailable, try this instead.

    Returns
    -------
    The validated method name.

    Raises
    ------
    ValueError
        If the method is unknown.
    RuntimeError
        If the method (and fallback) dependencies are missing.
    """
    if method not in registry:
        raise ValueError(
            f"Unknown method '{method}'. "
            f"Available: {', '.join(registry.keys())}"
        )

    cfg = registry[method]
    ok, msg = check_method_available(cfg)
    if ok:
        return method

    # Try fallback
    if fallback and fallback in registry:
        fb_cfg = registry[fallback]
        fb_ok, fb_msg = check_method_available(fb_cfg)
        if fb_ok:
            logger.warning(
                "Method '%s' unavailable (%s). Falling back to '%s'.",
                method, msg, fallback,
            )
            return fallback

    raise RuntimeError(msg)


def check_data_requirements(adata, cfg: MethodConfig) -> None:
    """Verify that the AnnData object meets method requirements.

    Raises ``ValueError`` with a clear message if layers or obs keys
    are missing.
    """
    for layer in cfg.requires_layers:
        if layer not in adata.layers:
            raise ValueError(
                f"Method '{cfg.name}' requires layer '{layer}' in adata.layers. "
                f"Available layers: {list(adata.layers.keys())}"
            )
    for key in cfg.requires_obs_keys:
        if key not in adata.obs.columns:
            raise ValueError(
                f"Method '{cfg.name}' requires column '{key}' in adata.obs. "
                f"Available columns: {list(adata.obs.columns)}"
            )
