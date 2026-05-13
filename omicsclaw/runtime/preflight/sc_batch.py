"""Preflight checks + auto-preparation for ``sc-batch-integration``.

Migrated out of ``bot/core.py`` per ADR 0001. The functions here inspect
``.h5ad`` inputs to (1) detect a sensible ``batch_key`` column, (2)
verify the AnnData object has been through ``sc-standardize-input`` and
``sc-preprocessing``, and (3) when neither is true, optionally chain
those upstream Skills before running the integration step.

This is **single-cell domain business logic**, not entry-layer code —
the original placement in ``bot/core.py`` was an accident of "where the
agent loop happened to need it first". A future generic preflight engine
will consult a Skill's declared prerequisite schema instead of these
hard-coded helpers; for now the module owns its own scoring rules and
clarification-message rendering.

Skill registry metadata is resolved via
``omicsclaw.runtime.skill_lookup.lookup_skill_info`` (top-level import).
The auto-prepare chain still late-imports ``_run_omics_skill_step`` and
``execute_omicsclaw`` from ``bot.skill_orchestration`` and
``bot.tool_executors``; those reverse edges are tracked in the
boundary guardrail and will move in subsequent slices.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from omicsclaw.runtime.skill_chain import run_omics_skill_step
from omicsclaw.runtime.skill_lookup import lookup_skill_info

logger = logging.getLogger("omicsclaw.runtime.preflight.sc_batch")


# ---------------------------------------------------------------------------
# Scoring tables
# ---------------------------------------------------------------------------

_BATCH_KEY_EXACT_PREFERENCES: tuple[str, ...] = (
    "batch",
    "sample",
    "sample_id",
    "batch_id",
    "orig.ident",
    "orig_ident",
    "library",
    "library_id",
    "donor",
    "donor_id",
    "patient",
    "patient_id",
)
_BATCH_KEY_HINT_TERMS: tuple[str, ...] = (
    "batch",
    "sample",
    "donor",
    "patient",
    "subject",
    "individual",
    "library",
    "dataset",
    "origin",
    "source",
    "condition",
    "treatment",
    "group",
    "replicate",
    "lane",
    "chemistry",
    "center",
    "site",
)
_BATCH_KEY_EXCLUDED_COLUMNS: set[str] = {
    "_index",
    "barcode",
    "cell",
    "cell_id",
    "cell_type",
    "celltype",
    "annotation",
    "predicted_label",
    "predicted_labels",
    "leiden",
    "louvain",
    "seurat_clusters",
    "cluster",
    "clusters",
    "phase",
    "doublet",
    "doublet_score",
    "n_genes_by_counts",
    "total_counts",
    "pct_counts_mt",
    "pct_counts_ribo",
}


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------

def _normalize_obs_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()


def _extract_flag_value(args_list: list[str], flag: str) -> str | None:
    for idx, arg in enumerate(args_list):
        if arg == flag and idx + 1 < len(args_list):
            value = str(args_list[idx + 1]).strip()
            return value or None
        if arg.startswith(flag + "="):
            value = arg.split("=", 1)[1].strip()
            return value or None
    return None


def _resolve_requested_batch_key(args: dict) -> str | None:
    direct = str(args.get("batch_key", "")).strip()
    if direct:
        return direct
    extra_args = args.get("extra_args")
    if isinstance(extra_args, list):
        return _extract_flag_value(extra_args, "--batch-key")
    return None


# ---------------------------------------------------------------------------
# AnnData-touching helpers (require pandas / anndata at runtime)
# ---------------------------------------------------------------------------

def _load_h5ad_obs_dataframe(file_path: Path):
    import anndata as ad

    adata = ad.read_h5ad(file_path, backed="r")
    try:
        return adata.obs.copy(), int(adata.n_obs)
    finally:
        file_handle = getattr(adata, "file", None)
        if file_handle is not None:
            try:
                file_handle.close()
            except Exception:
                pass


def _score_batch_key_candidate(column_name: str, series, n_obs: int) -> dict | None:
    normalized = _normalize_obs_key(column_name)
    normalized_compact = normalized.replace(" ", "")
    if normalized_compact in _BATCH_KEY_EXCLUDED_COLUMNS:
        return None

    non_null = series.dropna()
    nunique = int(non_null.nunique())
    if nunique <= 1:
        return None
    if n_obs > 0 and nunique >= n_obs:
        return None

    score = 0
    reasons: list[str] = []
    preferred_names = {name.replace(".", "").replace("_", "") for name in _BATCH_KEY_EXACT_PREFERENCES}
    if normalized_compact in preferred_names:
        score += 120
        reasons.append("name matches a common batch/sample column")
    else:
        matched_terms = [term for term in _BATCH_KEY_HINT_TERMS if term in normalized]
        if matched_terms:
            score += 35 + 10 * min(len(matched_terms), 3)
            reasons.append("name looks batch-like")

    if 2 <= nunique <= 24:
        score += 35
        reasons.append(f"{nunique} groups")
    elif 25 <= nunique <= 96:
        score += 20
        reasons.append(f"{nunique} groups")
    elif 97 <= nunique <= min(256, max(100, n_obs // 2)):
        score += 5
        reasons.append(f"{nunique} groups")
    else:
        return None

    preview = [str(v) for v in non_null.astype(str).unique()[:5]]
    if not preview or score < 40:
        return None

    return {
        "column": str(column_name),
        "score": score,
        "nunique": nunique,
        "preview": preview,
        "reasons": reasons,
    }


def _find_batch_key_candidates(file_path: Path) -> dict:
    obs_df, n_obs = _load_h5ad_obs_dataframe(file_path)
    candidates = []
    for column in obs_df.columns:
        candidate = _score_batch_key_candidate(column, obs_df[column], n_obs)
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: (-int(item["score"]), int(item["nunique"]), str(item["column"])))
    return {
        "n_obs": n_obs,
        "obs_columns": [str(col) for col in obs_df.columns],
        "candidates": candidates[:8],
    }


def _format_batch_key_clarification(
    *,
    file_path: Path,
    requested_batch_key: str | None,
    preflight: dict,
) -> str:
    obs_columns = preflight.get("obs_columns", [])
    candidates = preflight.get("candidates", [])
    lines = [
        "Batch-key clarification needed before running `sc-batch-integration`.",
        f"- File: `{file_path.name}`",
    ]

    if requested_batch_key:
        lines.extend(
            [
                f"- Requested `batch_key`: `{requested_batch_key}`",
                "- Status: that column was not found in `adata.obs`.",
            ]
        )
    else:
        lines.append("- Status: no `batch_key` was provided, so I paused before guessing.")

    if candidates:
        lines.append("- Possible batch-like columns found in `adata.obs`:")
        for candidate in candidates:
            preview = ", ".join(candidate["preview"])
            lines.append(
                f"  - `{candidate['column']}`: {candidate['nunique']} groups "
                f"(examples: {preview})"
            )
    else:
        lines.append("- I did not find a confident batch-like column automatically.")

    visible_columns = ", ".join(f"`{col}`" for col in obs_columns[:20]) if obs_columns else "(none found)"
    lines.extend(
        [
            f"- Available `obs` columns: {visible_columns}",
            "- Please tell me which column should be used as `batch_key`.",
            "- I have not started the integration yet because `sample`, `patient`, `condition`, and related columns imply different correction targets.",
        ]
    )
    return "\n".join(lines)


def _maybe_require_batch_key_selection(skill_key: str, input_path: str | None, args: dict) -> str:
    """If the caller is asking for ``sc-batch-integration`` but didn't
    supply a valid ``batch_key``, return a clarification message; else "".
    """
    if not input_path:
        return ""

    skill_info = lookup_skill_info(skill_key)
    canonical_skill = skill_info.get("alias", skill_key)
    if canonical_skill != "sc-batch-integration":
        return ""

    file_path = Path(input_path)
    if file_path.suffix.lower() != ".h5ad":
        return ""

    requested_batch_key = _resolve_requested_batch_key(args)
    try:
        preflight = _find_batch_key_candidates(file_path)
    except Exception as exc:
        logger.warning("Failed to inspect AnnData batch candidates for %s: %s", file_path, exc)
        return ""

    obs_columns = set(preflight.get("obs_columns", []))
    if requested_batch_key:
        if requested_batch_key in obs_columns:
            return ""
        return _format_batch_key_clarification(
            file_path=file_path,
            requested_batch_key=requested_batch_key,
            preflight=preflight,
        )

    return _format_batch_key_clarification(
        file_path=file_path,
        requested_batch_key=None,
        preflight=preflight,
    )


def _inspect_h5ad_integration_readiness(file_path: Path) -> dict:
    import anndata as ad

    adata = ad.read_h5ad(file_path, backed="r")
    try:
        contract = adata.uns.get("omicsclaw_input_contract", {})
        if not isinstance(contract, dict):
            contract = {}
        obs_columns = [str(col) for col in adata.obs.columns]
        obsm_keys = [str(key) for key in adata.obsm.keys()]
        obsp_keys = [str(key) for key in adata.obsp.keys()]
        uns_keys = [str(key) for key in adata.uns.keys()]
        obs_keys_lower = {key.lower() for key in obs_columns}
        obsm_keys_lower = {key.lower() for key in obsm_keys}
        obsp_keys_lower = {key.lower() for key in obsp_keys}
        uns_keys_lower = {key.lower() for key in uns_keys}
        looks_preprocessed = bool(
            {"x_pca", "x_umap"} & obsm_keys_lower
            or {"neighbors", "pca"} & uns_keys_lower
            or {"connectivities", "distances"} & obsp_keys_lower
            or {"leiden", "louvain", "cluster", "clusters"} & obs_keys_lower
        )
        return {
            "obs_columns": obs_columns,
            "obsm_keys": obsm_keys,
            "obsp_keys": obsp_keys,
            "uns_keys": uns_keys,
            "layers": [str(key) for key in adata.layers.keys()],
            "has_raw": adata.raw is not None,
            "standardized": bool(contract.get("standardized")),
            "standardized_by": str(contract.get("standardized_by", "")).strip(),
            "looks_preprocessed": looks_preprocessed,
        }
    finally:
        file_handle = getattr(adata, "file", None)
        if file_handle is not None:
            try:
                file_handle.close()
            except Exception:
                pass


def _format_sc_batch_workflow_guidance(file_path: Path, reasons: list[str], *, start_step: int = 1) -> str:
    steps = [
        "`sc-standardize-input` to canonicalize the input contract",
        "`sc-preprocessing` to build normalized expression, PCA, neighbors, UMAP, and clusters",
        "`sc-batch-integration` after the batch column is confirmed",
    ]
    lines = [
        "Workflow check paused before running `sc-batch-integration`.",
        f"- File: `{file_path.name}`",
        "- Why I paused:",
    ]
    lines.extend(f"  - {reason}" for reason in reasons)
    lines.append("- Recommended workflow:")
    for idx, step in enumerate(steps[start_step - 1 :], start=start_step):
        lines.append(f"  {idx}. {step}")
    lines.extend(
        [
            "- Tell me if you want me to start from the recommended first step.",
            "- If you really want direct integration anyway, say that explicitly and I can skip this workflow check.",
        ]
    )
    return "\n".join(lines)


def _get_sc_batch_integration_workflow_plan(skill_key: str, input_path: str | None, args: dict) -> dict | None:
    """Returns a dict ``{file_path, reasons, start_step}`` when the input
    needs upstream prep; otherwise ``None`` (run integration directly)."""
    if not input_path:
        return None

    skill_info = lookup_skill_info(skill_key)
    canonical_skill = skill_info.get("alias", skill_key)
    if canonical_skill != "sc-batch-integration":
        return None

    file_path = Path(input_path)
    if file_path.is_dir():
        return {
            "file_path": file_path,
            "reasons": [
                "directory-style single-cell input should be standardized before integration so counts, feature names, and provenance are normalized",
                "the standard path is to load/standardize first, then preprocess, then integrate",
            ],
            "start_step": 1,
        }

    suffix = file_path.suffix.lower()
    if suffix != ".h5ad":
        return {
            "file_path": file_path,
            "reasons": [
                f"`{suffix or 'unknown'}` is not a ready AnnData integration input for the current workflow",
                "non-h5ad single-cell inputs are better handled by `sc-standardize-input` before integration",
            ],
            "start_step": 1,
        }

    try:
        readiness = _inspect_h5ad_integration_readiness(file_path)
    except Exception as exc:
        logger.warning("Failed to inspect integration readiness for %s: %s", file_path, exc)
        return None

    reasons: list[str] = []
    start_step = 2
    if not readiness.get("standardized"):
        reasons.append("this `.h5ad` was not marked as standardized by `sc-standardize-input`")
        start_step = 1
    if not readiness.get("looks_preprocessed"):
        reasons.append("this object does not show the usual preprocessing markers such as PCA, neighbors, or cluster labels")
        start_step = 1 if start_step == 1 else 2

    if not reasons:
        return None
    return {
        "file_path": file_path,
        "reasons": reasons,
        "start_step": start_step,
    }


def _maybe_require_batch_integration_workflow(skill_key: str, input_path: str | None, args: dict) -> str:
    if not input_path or bool(args.get("confirm_workflow_skip")) or bool(args.get("auto_prepare")):
        return ""
    plan = _get_sc_batch_integration_workflow_plan(skill_key, input_path, args)
    if not plan:
        return ""
    return _format_sc_batch_workflow_guidance(
        plan["file_path"],
        plan["reasons"],
        start_step=int(plan.get("start_step", 1)),
    )


def _format_auto_prepare_summary(step_records: list[dict], *, final_input_path: str | None = None) -> str:
    lines = [
        "Automatic preparation workflow completed for `sc-batch-integration`.",
        "- Completed steps:",
    ]
    for idx, step in enumerate(step_records, start=1):
        lines.append(
            f"  {idx}. `{step['skill']}` -> `{step['output_path']}`"
        )
    if final_input_path:
        lines.append(f"- Integration input prepared at: `{final_input_path}`")
    return "\n".join(lines)


async def _auto_prepare_sc_batch_integration(
    *,
    args: dict,
    skill_key: str,
    input_path: str,
    session_id: str | None,
    chat_id: int | str,
    output_root: Path,
) -> str:
    """Auto-chain ``sc-standardize-input`` → ``sc-preprocessing`` →
    ``sc-batch-integration`` when the input needs upstream prep.
    """
    plan = _get_sc_batch_integration_workflow_plan(skill_key, input_path, args)
    if not plan:
        return ""

    from bot.tool_executors import execute_omicsclaw

    step_records: list[dict] = []
    current_input = str(plan["file_path"])

    if int(plan.get("start_step", 1)) <= 1:
        standardize_result = await run_omics_skill_step(
            output_root=output_root,
            skill_key="sc-standardize-input",
            input_path=current_input,
            mode="path",
        )
        if not standardize_result["success"]:
            guidance = standardize_result["guidance_block"]
            failure = (
                f"`sc-standardize-input` failed during automatic preparation "
                f"(exit {standardize_result['returncode']}):\n{standardize_result['error_text']}"
            )
            return guidance + f"\n\n---\n{failure}" if guidance else failure
        standardized_path = standardize_result["out_dir"] / "processed.h5ad"
        if not standardized_path.exists():
            return (
                "Automatic preparation stopped because `sc-standardize-input` did not produce "
                f"`processed.h5ad` in `{standardize_result['out_dir']}`."
            )
        current_input = str(standardized_path)
        step_records.append({"skill": "sc-standardize-input", "output_path": current_input})

    if int(plan.get("start_step", 1)) <= 2:
        preprocess_result = await run_omics_skill_step(
            output_root=output_root,
            skill_key="sc-preprocessing",
            input_path=current_input,
            mode="path",
        )
        if not preprocess_result["success"]:
            guidance = preprocess_result["guidance_block"]
            failure = (
                f"`sc-preprocessing` failed during automatic preparation "
                f"(exit {preprocess_result['returncode']}):\n{preprocess_result['error_text']}"
            )
            prefix = _format_auto_prepare_summary(step_records, final_input_path=current_input)
            message = prefix + "\n\n---\n" + failure
            return guidance + "\n\n---\n" + message if guidance else message
        processed_path = preprocess_result["out_dir"] / "processed.h5ad"
        if not processed_path.exists():
            return (
                "Automatic preparation stopped because `sc-preprocessing` did not produce "
                f"`processed.h5ad` in `{preprocess_result['out_dir']}`."
            )
        current_input = str(processed_path)
        step_records.append({"skill": "sc-preprocessing", "output_path": current_input})

    chained_args = dict(args)
    chained_args["file_path"] = current_input
    chained_args["mode"] = "path"
    chained_args["confirm_workflow_skip"] = True
    chained_args["auto_prepare"] = False

    batch_clarification = _maybe_require_batch_key_selection(skill_key, current_input, chained_args)
    prefix = _format_auto_prepare_summary(step_records, final_input_path=current_input)
    if batch_clarification:
        return prefix + "\n\n---\n" + batch_clarification

    final_result = await execute_omicsclaw(chained_args, session_id=session_id, chat_id=chat_id)
    return prefix + "\n\n---\n" + final_result
