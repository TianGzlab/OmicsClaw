"""Spatial microenvironment subsetting utilities.

Extract a local neighborhood around a center cell/spot population using
physical-distance thresholds when possible.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .adata_utils import require_spatial_coords
from .exceptions import DataError

logger = logging.getLogger(__name__)

_DEFAULT_VISIUM_SPOT_DIAMETER_UM = 55.0
_MICRON_TOKENS = {
    "um",
    "micron",
    "microns",
    "micrometer",
    "micrometers",
    "mum",
}
_COMMON_LABEL_KEYS = (
    "cell_type",
    "celltype",
    "annotation",
    "annot",
    "label",
    "labels",
    "cluster",
    "clusters",
    "leiden",
    "spatial_domain",
    "domain_ground_truth",
)


@dataclass(frozen=True)
class SpatialScale:
    """Scale metadata for converting coordinate units to microns."""

    microns_per_coordinate_unit: float
    native_unit: str
    source: str


def parse_csv_values(raw: str | None) -> list[str]:
    """Parse a comma-separated string into a clean list of labels."""
    if raw is None:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def resolve_label_key(adata, requested_key: str | None = None) -> str:
    """Resolve the obs column used for center / target labels."""
    if requested_key:
        if requested_key not in adata.obs.columns:
            available = ", ".join(sorted(map(str, adata.obs.columns[:20])))
            raise DataError(
                f"Annotation column '{requested_key}' was not found in adata.obs. "
                f"Available examples: {available}"
            )
        return requested_key

    for key in _COMMON_LABEL_KEYS:
        if key in adata.obs.columns:
            return key

    raise DataError(
        "Could not auto-detect an annotation column in adata.obs. "
        "Please provide --center-key explicitly."
    )


def build_label_mask(
    adata,
    *,
    key: str,
    values: list[str],
    label_role: str,
) -> np.ndarray:
    """Return a boolean mask for exact label matches (case-insensitive)."""
    if not values:
        raise DataError(f"No {label_role} labels were provided.")

    series = adata.obs[key].astype(str)
    requested = {value.lower() for value in values}
    mask = series.str.lower().isin(requested).to_numpy()
    if mask.any():
        return mask

    available = sorted(series.dropna().astype(str).unique().tolist())[:25]
    raise DataError(
        f"None of the requested {label_role} labels matched adata.obs['{key}']: {values}. "
        f"Available examples: {available}"
    )


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dict_indicates_microns(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("coordinate_unit", "coordinate_units", "unit", "units"):
        value = str(payload.get(key, "")).strip().lower()
        if value in _MICRON_TOKENS:
            return True
    return False


def _extract_scale_from_mapping(payload: Any) -> tuple[float, str] | None:
    if not isinstance(payload, dict):
        return None

    direct_scale_keys = (
        "microns_per_coordinate_unit",
        "microns_per_unit",
        "um_per_coordinate_unit",
        "um_per_unit",
        "microns_per_pixel",
        "pixel_size_um",
        "um_per_pixel",
    )
    for key in direct_scale_keys:
        value = _coerce_float(payload.get(key))
        if value and value > 0:
            return value, key

    return None


def infer_microns_per_coordinate_unit(
    adata,
    *,
    data_type: str = "",
    user_scale: float | None = None,
) -> SpatialScale:
    """Infer how many microns each coordinate unit represents."""
    if user_scale is not None:
        if user_scale <= 0:
            raise DataError("--microns-per-coordinate-unit must be > 0")
        return SpatialScale(
            microns_per_coordinate_unit=float(user_scale),
            native_unit="custom",
            source="user override",
        )

    # OmicsClaw-native metadata written by this skill or future preprocessors.
    for uns_key in ("omicsclaw_spatial_units", "spatial_units", "spatial_unit_metadata"):
        if uns_key not in adata.uns:
            continue
        payload = adata.uns[uns_key]
        extracted = _extract_scale_from_mapping(payload)
        if extracted is not None:
            value, source_key = extracted
            return SpatialScale(value, "metadata", f"{uns_key}.{source_key}")
        if _dict_indicates_microns(payload):
            return SpatialScale(1.0, "micron", f"{uns_key}.unit")
        if isinstance(payload, str) and payload.strip().lower() in _MICRON_TOKENS:
            return SpatialScale(1.0, "micron", uns_key)

    platform_tokens = " ".join(
        [
            str(data_type or ""),
            str(adata.uns.get("spatial_name", "")),
            str(adata.uns.get("platform", "")),
            str(adata.uns.get("technology", "")),
        ]
    ).lower()

    if "xenium" in platform_tokens:
        return SpatialScale(1.0, "micron", "xenium default assumption")

    spatial_uns = adata.uns.get("spatial", {})
    if isinstance(spatial_uns, dict):
        for payload in spatial_uns.values():
            if not isinstance(payload, dict):
                continue
            metadata = payload.get("metadata", {})
            scalefactors = payload.get("scalefactors", {})

            extracted = _extract_scale_from_mapping(metadata)
            if extracted is not None:
                value, source_key = extracted
                return SpatialScale(value, "metadata", f"spatial.metadata.{source_key}")

            extracted = _extract_scale_from_mapping(scalefactors)
            if extracted is not None:
                value, source_key = extracted
                return SpatialScale(value, "metadata", f"spatial.scalefactors.{source_key}")

            if _dict_indicates_microns(metadata):
                return SpatialScale(1.0, "micron", "spatial.metadata.unit")

            spot_diameter_fullres = _coerce_float(scalefactors.get("spot_diameter_fullres"))
            spot_diameter_um = _coerce_float(metadata.get("spot_diameter_um"))
            if spot_diameter_fullres and spot_diameter_um and spot_diameter_fullres > 0:
                return SpatialScale(
                    spot_diameter_um / spot_diameter_fullres,
                    "pixel",
                    "spatial.metadata.spot_diameter_um",
                )

            bin_size_fullres = _coerce_float(scalefactors.get("bin_size_fullres"))
            bin_size_um = _coerce_float(metadata.get("bin_size_um"))
            if bin_size_fullres and bin_size_um and bin_size_fullres > 0:
                return SpatialScale(
                    bin_size_um / bin_size_fullres,
                    "pixel",
                    "spatial.metadata.bin_size_um",
                )

            if (
                spot_diameter_fullres
                and spot_diameter_fullres > 0
                and ("visium" in platform_tokens or data_type == "visium")
            ):
                return SpatialScale(
                    _DEFAULT_VISIUM_SPOT_DIAMETER_UM / spot_diameter_fullres,
                    "pixel",
                    "visium default 55um spot assumption",
                )

    raise DataError(
        "Could not infer coordinate-to-micron scaling from the input data. "
        "If your coordinates are already in microns, add "
        "adata.uns['omicsclaw_spatial_units'] = {'coordinate_unit': 'micron'}. "
        "Otherwise provide --microns-per-coordinate-unit explicitly."
    )


def compute_radius_native(
    *,
    radius_native: float | None,
    radius_microns: float | None,
    scale: SpatialScale | None,
) -> tuple[float, float | None]:
    """Resolve radius in native coordinate units."""
    if radius_native is not None:
        if radius_native <= 0:
            raise DataError("--radius-native must be > 0")
        radius_um = None
        if scale is not None:
            radius_um = float(radius_native) * scale.microns_per_coordinate_unit
        return float(radius_native), radius_um

    if radius_microns is None:
        raise DataError("Provide either --radius-native or --radius-microns")
    if radius_microns <= 0:
        raise DataError("--radius-microns must be > 0")
    if scale is None:
        raise DataError(
            "A micron radius requires coordinate scaling, but no scale metadata was available."
        )
    return float(radius_microns) / scale.microns_per_coordinate_unit, float(radius_microns)


def extract_microenvironment_subset(
    adata,
    *,
    center_key: str,
    center_values: list[str],
    radius_native: float,
    include_centers: bool = True,
    target_key: str | None = None,
    target_values: list[str] | None = None,
    radius_microns: float | None = None,
    scale: SpatialScale | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Return a subset AnnData plus summary metadata."""
    spatial_key = require_spatial_coords(adata)
    coords = np.asarray(adata.obsm[spatial_key])
    if coords.ndim != 2 or coords.shape[0] != adata.n_obs or coords.shape[1] < 2:
        raise DataError(
            f"adata.obsm['{spatial_key}'] must be a two-dimensional coordinate array."
        )
    coords = coords[:, :2].astype(float)

    center_mask = build_label_mask(
        adata,
        key=center_key,
        values=center_values,
        label_role="center",
    )
    center_indices = np.flatnonzero(center_mask)
    if center_indices.size == 0:
        raise DataError("No center observations matched the requested labels.")

    if target_values:
        effective_target_key = target_key or center_key
        target_mask = build_label_mask(
            adata,
            key=effective_target_key,
            values=target_values,
            label_role="target",
        )
    else:
        effective_target_key = target_key or center_key
        target_mask = np.ones(adata.n_obs, dtype=bool)

    center_tree = cKDTree(coords[center_indices])
    nearest_dist_native, nearest_idx = center_tree.query(coords, k=1)
    nearest_center_indices = center_indices[np.asarray(nearest_idx, dtype=int)]
    within_radius_mask = nearest_dist_native <= float(radius_native)
    selected_mask = within_radius_mask & target_mask
    if include_centers:
        selected_mask |= center_mask
    else:
        selected_mask &= ~center_mask

    selected_indices = np.flatnonzero(selected_mask)
    if selected_indices.size == 0:
        raise DataError(
            "No observations fell within the requested radius after applying filters."
        )

    nearest_center_names = adata.obs_names.to_numpy()[nearest_center_indices]
    selected = adata[selected_mask].copy()
    selected.obs["microenv_role"] = pd.Categorical(
        np.where(center_mask[selected_mask], "center", "neighbor"),
        categories=["center", "neighbor"],
    )
    selected.obs["microenv_is_center"] = center_mask[selected_mask]
    selected.obs["microenv_within_radius"] = within_radius_mask[selected_mask]
    selected.obs["microenv_nearest_center"] = nearest_center_names[selected_mask]
    selected.obs["microenv_distance_native"] = pd.to_numeric(
        nearest_dist_native[selected_mask],
        errors="coerce",
    ).astype(float)
    if scale is not None:
        selected.obs["microenv_distance_microns"] = (
            selected.obs["microenv_distance_native"].astype(float)
            * float(scale.microns_per_coordinate_unit)
        )

    summary: dict[str, Any] = {
        "spatial_key": spatial_key,
        "center_key": center_key,
        "center_values": list(center_values),
        "target_key": effective_target_key if target_values else None,
        "target_values": list(target_values or []),
        "radius_native": float(radius_native),
        "radius_microns": float(radius_microns) if radius_microns is not None else None,
        "include_centers": bool(include_centers),
        "n_total_observations": int(adata.n_obs),
        "n_center_observations": int(center_mask.sum()),
        "n_selected_observations": int(selected.n_obs),
        "n_neighbor_observations": int((selected.obs["microenv_role"] == "neighbor").sum()),
        "center_label_counts": (
            adata.obs.loc[center_mask, center_key].astype(str).value_counts().to_dict()
        ),
    }

    if scale is not None:
        summary["microns_per_coordinate_unit"] = float(scale.microns_per_coordinate_unit)
        summary["scale_source"] = scale.source
        summary["coordinate_unit"] = scale.native_unit

    selected.uns["omicsclaw_spatial_microenvironment"] = summary
    if scale is not None:
        selected.uns["omicsclaw_spatial_units"] = {
            "microns_per_coordinate_unit": float(scale.microns_per_coordinate_unit),
            "source": scale.source,
            "coordinate_unit": scale.native_unit,
        }

    return selected, summary


def build_selection_table(adata) -> pd.DataFrame:
    """Export a flat table describing the selected microenvironment subset."""
    spatial_key = require_spatial_coords(adata)
    coords = np.asarray(adata.obsm[spatial_key])[:, :2]
    table = pd.DataFrame(
        {
            "observation": adata.obs_names.astype(str),
            "x": coords[:, 0],
            "y": coords[:, 1],
            "microenv_role": adata.obs.get("microenv_role", pd.Series(index=adata.obs_names)).astype(str),
            "microenv_is_center": pd.to_numeric(
                adata.obs.get("microenv_is_center", False),
                errors="coerce",
            ).fillna(False).astype(bool),
            "microenv_within_radius": pd.to_numeric(
                adata.obs.get("microenv_within_radius", False),
                errors="coerce",
            ).fillna(False).astype(bool),
            "microenv_nearest_center": adata.obs.get(
                "microenv_nearest_center",
                pd.Series(index=adata.obs_names, dtype=object),
            ).astype(str),
            "microenv_distance_native": pd.to_numeric(
                adata.obs.get("microenv_distance_native", np.nan),
                errors="coerce",
            ),
        }
    )
    if "microenv_distance_microns" in adata.obs.columns:
        table["microenv_distance_microns"] = pd.to_numeric(
            adata.obs["microenv_distance_microns"],
            errors="coerce",
        )
    return table


def build_label_composition_table(
    full_adata,
    subset_adata,
    *,
    label_key: str,
) -> pd.DataFrame:
    """Compare label composition before and after subsetting."""
    full_counts = full_adata.obs[label_key].astype(str).value_counts()
    subset_counts = subset_adata.obs[label_key].astype(str).value_counts()
    labels = sorted(set(full_counts.index) | set(subset_counts.index))
    rows: list[dict[str, Any]] = []
    for label in labels:
        n_full = int(full_counts.get(label, 0))
        n_subset = int(subset_counts.get(label, 0))
        rows.append(
            {
                "label": label,
                "n_subset": n_subset,
                "pct_subset": round((n_subset / max(subset_adata.n_obs, 1)) * 100, 2),
                "n_full": n_full,
                "pct_full": round((n_full / max(full_adata.n_obs, 1)) * 100, 2),
            }
        )
    return pd.DataFrame(rows).sort_values(["n_subset", "label"], ascending=[False, True])
