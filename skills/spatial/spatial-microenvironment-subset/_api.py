"""Select spatial neighborhoods without file writes."""
from __future__ import annotations

import json
import numpy as np
from skills.spatial._lib.microenvironment import (
    resolve_label_key, infer_microns_per_coordinate_unit, compute_radius_native,
    extract_microenvironment_subset, build_selection_table,
)
from skills.spatial._lib.exceptions import DataError
from skills.spatial._lib.adata_utils import require_spatial_coords

__all__ = ["subset", "run_info", "selection_table", "selection_figure"]
_RUN_KEY = "omicsclaw_microenvironment_run"


def subset(adata, *, center_values: list[str], center_key: str | None = None,
           radius_native: float | None = None, radius_microns: float | None = None,
           microns_per_coordinate_unit: float | None = None, data_type: str | None = None,
           include_centers: bool = True, target_key: str | None = None,
           target_values: list[str] | None = None):
    """Return a new neighborhood AnnData; expression matrices remain unchanged.

    :param adata: Labelled AnnData with spatial coordinates; X, layers and raw are sliced.
    :param center_values: Labels defining centers, required as in the CLI.
    :param center_key: Label column; None selects the first recognized label column.
    :param radius_native: Positive coordinate-unit radius; default None requires radius_microns.
    :param radius_microns: Positive micron radius, exclusive with radius_native.
    :param microns_per_coordinate_unit: Explicit positive scale; None uses platform metadata.
    :param data_type: Optional platform hint used to resolve units, as in the CLI.
    :param include_centers: True retains centers regardless of the target-label filter.
    :param target_key: Optional neighbor label column; None uses the center column.
    :param target_values: Optional allowed neighbor labels; None admits all labels.
    :returns: A new AnnData with role, distance and JSON diagnostics.
    :raises ValueError: Invalid radius, labels, units, coordinates or an empty selection.
    """
    if (radius_native is None) == (radius_microns is None):
        raise ValueError("Provide exactly one radius_native or radius_microns")
    for name, value in (("radius_native", radius_native), ("radius_microns", radius_microns),
                        ("microns_per_coordinate_unit", microns_per_coordinate_unit)):
        if value is not None and (not np.isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be finite and positive")
    try:
        center_key = resolve_label_key(adata, center_key)
        target_key = resolve_label_key(adata, target_key) if target_key else None
        scale = None
        if radius_microns is not None or microns_per_coordinate_unit is not None:
            scale = infer_microns_per_coordinate_unit(adata, data_type=data_type, user_scale=microns_per_coordinate_unit)
        native, microns = compute_radius_native(radius_native=radius_native, radius_microns=radius_microns, scale=scale)
        result, summary = extract_microenvironment_subset(
            adata, center_key=center_key, center_values=center_values, radius_native=native,
            include_centers=include_centers, target_key=target_key, target_values=target_values,
            radius_microns=microns, scale=scale,
        )
    except DataError as exc:
        raise ValueError(str(exc)) from exc
    result.uns[_RUN_KEY] = json.dumps(summary)
    return result


def run_info(adata, *, keep: bool = True) -> dict:
    """Read selection counts and resolved coordinate units.

    :param adata: AnnData returned by subset.
    :param keep: True retains diagnostics; False removes them for CLI serialization.
    :returns: Selection diagnostics, or an empty dict before analysis.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def selection_table(adata):
    """Return coordinates, center identities and nearest-center distances.

    :param adata: AnnData returned by subset; expression values are not read.
    :returns: One DataFrame row per selected observation.
    :raises KeyError: Selection columns are absent.
    """
    if "microenv_role" not in adata.obs:
        raise KeyError("Run subset before selection_table")
    table = build_selection_table(adata)
    info = run_info(adata)
    for key in {info.get("center_key"), info.get("target_key")} - {None}:
        if key in adata.obs and key not in table:
            table[key] = adata.obs[key].astype(str).to_numpy()
    return table


def selection_figure(adata):
    """Plot selected centers and neighbors in coordinate units.

    :param adata: AnnData returned by subset; reads coordinates and microenv_role.
    :returns: A matplotlib Figure without saving it.
    :raises KeyError: Selection roles are absent.
    """
    import matplotlib.pyplot as plt
    coords = np.asarray(adata.obsm[require_spatial_coords(adata)])
    fig, ax = plt.subplots()
    for role in ("center", "neighbor"):
        mask = adata.obs["microenv_role"].astype(str).to_numpy() == role
        ax.scatter(coords[mask, 0], coords[mask, 1], label=role, s=12)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.legend()
    return fig
