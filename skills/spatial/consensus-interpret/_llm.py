"""LLM grounded annotation (γ) + next-step synthesis (β).

Both functions accept an ``llm_call`` callable so tests can stub a
deterministic response without hitting a real endpoint. Default LLM
implementation delegates to :func:`omicsclaw.providers.chat_completion.call_chat_completion`.

Schema invariants per ADR 0012 §"T3 invariants" are enforced HERE,
not in a separate slice — so the LLM call path can never produce an
output that violates marker_grounding or evidence_refs constraints
without raising :class:`InvariantViolationError` (exit 7).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from _candidates import RankedCandidate
from _errors import InvariantViolationError, LLMUnavailableError

logger = logging.getLogger("consensus-interpret.llm")

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_ALLOWED_NEXT_STEP_SKILLS = frozenset({
    "spatial-de", "spatial-deconv", "spatial-communication",
    "spatial-trajectory", "spatial-cnv", "spatial-velocity",
    "spatial-statistics", "spatial-genes", "spatial-condition",
})

# JSON code-fence pattern used by many LLMs (```json ... ``` or ``` ... ```).
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


# --------------------------------------------------------------------------- #
# Dataclasses (frozen — Slice 6 invariant check + Slice 7 report render)       #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class EvidenceMarker:
    gene: str
    de_rank: int
    db_source: str
    db_celltype: str
    weight: float


@dataclass(frozen=True)
class ClusterAnnotation:
    cluster_id: int
    n_cells: int
    cell_type: str
    confidence: float
    evidence_markers: list[EvidenceMarker] = field(default_factory=list)
    narrative: str = ""


@dataclass(frozen=True)
class NextStep:
    skill: str
    args_hint: str
    priority: int
    evidence_refs: list[str] = field(default_factory=list)
    reason: str = ""


# --------------------------------------------------------------------------- #
# Default LLM call                                                            #
# --------------------------------------------------------------------------- #

LLM_UNAVAILABLE = (
    "LLM cell-type naming is not available in this version: the skill has no "
    "model client. Run without --llm for the structural-only report."
)
"""The message of the :class:`LLMUnavailableError` the default call raises."""


def _default_llm_call(prompt: str) -> str | None:
    """The model call used when none is injected.

    :raises LLMUnavailableError: always, with :data:`LLM_UNAVAILABLE`.
    """
    raise LLMUnavailableError(LLM_UNAVAILABLE)


# --------------------------------------------------------------------------- #
# annotate_cluster (γ)                                                         #
# --------------------------------------------------------------------------- #

def annotate_cluster(
    cluster_ctx: dict,
    candidates: list[RankedCandidate],
    *,
    llm_call: Callable[[str], str | None] | None = None,
) -> ClusterAnnotation:
    """LLM-grounded cell-type annotation for one consensus cluster.

    Retries ONCE on malformed JSON before raising :class:`InvariantViolationError`.
    Raises :class:`LLMUnavailableError` (exit 6) if the LLM call returns
    None twice (network / API key missing).
    """
    call = llm_call or _default_llm_call
    prompt = _build_annotate_prompt(cluster_ctx, candidates)
    allowed_cell_types = {c.cell_type for c in candidates} | {"Unknown"}

    last_error: str = ""
    for attempt in range(2):
        raw = call(prompt)
        if raw is None:
            last_error = "LLM call returned None"
            continue
        try:
            data = _extract_json(raw)
        except ValueError as exc:
            last_error = f"JSON parse failed: {exc}"
            logger.warning(
                "annotate_cluster attempt %d/2: malformed JSON, will retry",
                attempt + 1,
            )
            continue
        try:
            annotation = _parse_annotation(data, cluster_ctx, allowed_cell_types)
            return annotation
        except InvariantViolationError:
            # Schema-valid but invariant violation — do NOT retry; this is
            # a structural LLM behaviour bug and a re-roll won't help.
            raise

    if last_error.startswith("LLM call returned None"):
        raise LLMUnavailableError(
            "LLM call returned None twice during cluster annotation. "
            "Check provider endpoint / API key. Pass --no-llm for "
            "structural-only degrade mode."
        )
    raise InvariantViolationError(
        f"annotate_cluster: malformed LLM output after retry — {last_error}"
    )


def _build_annotate_prompt(
    cluster_ctx: dict,
    candidates: list[RankedCandidate],
) -> str:
    template = (_PROMPTS_DIR / "annotate.tmpl").read_text()
    candidate_block = _render_candidate_block(candidates)
    return template.format(candidate_block=candidate_block, **cluster_ctx)


def _render_candidate_block(candidates: list[RankedCandidate]) -> str:
    if not candidates:
        return "(no candidates; you should pick 'Unknown')"
    lines: list[str] = []
    for c in candidates:
        markers = ", ".join(
            f"{m.gene}@rank{m.de_rank}(w={m.weight:.2f})"
            for m in c.supporting_markers
        )
        lines.append(
            f"- {c.cell_type}  (score={c.score:.3f}; supporting_markers: {markers})"
        )
    return "\n".join(lines)


def _parse_annotation(
    data: dict,
    cluster_ctx: dict,
    allowed_cell_types: set[str],
) -> ClusterAnnotation:
    cell_type = str(data.get("cell_type", ""))
    if cell_type not in allowed_cell_types:
        raise InvariantViolationError(
            f"LLM picked cell_type '{cell_type}' but allowed candidates were "
            f"{sorted(allowed_cell_types)}. Hallucination guardrail (ADR 0012 T3)."
        )

    raw_markers = data.get("evidence_markers", [])
    if not isinstance(raw_markers, list):
        raise InvariantViolationError(
            "evidence_markers must be a JSON array"
        )
    markers = [
        EvidenceMarker(
            gene=str(m["gene"]),
            de_rank=int(m["de_rank"]),
            db_source=str(m.get("db_source", "")),
            db_celltype=str(m.get("db_celltype", "")),
            weight=float(m.get("weight", 0.0)),
        )
        for m in raw_markers
        if isinstance(m, dict) and "gene" in m
    ]

    if cell_type != "Unknown" and not markers:
        raise InvariantViolationError(
            f"cluster {cluster_ctx['cluster_id']} cell_type={cell_type!r} but "
            f"evidence_markers is empty. ADR 0012 T3 invariant: every cell-type "
            f"claim MUST cite ≥1 marker."
        )

    return ClusterAnnotation(
        cluster_id=int(cluster_ctx["cluster_id"]),
        n_cells=int(cluster_ctx["n_cells"]),
        cell_type=cell_type,
        confidence=float(data.get("confidence", 0.0)),
        evidence_markers=markers,
        narrative=str(data.get("narrative", "")),
    )


# --------------------------------------------------------------------------- #
# synthesize_next_steps (β)                                                   #
# --------------------------------------------------------------------------- #

def synthesize_next_steps(
    annotations: list[ClusterAnnotation],
    nmi_matrix: pd.DataFrame,
    *,
    top_k: int = 3,
    llm_call: Callable[[str], str | None] | None = None,
) -> list[NextStep]:
    """LLM next-step recommendations with mandatory evidence_refs per entry.

    Caps at ``top_k`` (default 3 per ADR 0012). Raises
    :class:`InvariantViolationError` on empty evidence_refs, unknown skills,
    or persistent malformed JSON.
    """
    call = llm_call or _default_llm_call
    prompt = _build_next_steps_prompt(annotations, nmi_matrix, top_k)

    last_error: str = ""
    for attempt in range(2):
        raw = call(prompt)
        if raw is None:
            last_error = "LLM call returned None"
            continue
        try:
            data = _extract_json(raw)
        except ValueError as exc:
            last_error = f"JSON parse failed: {exc}"
            continue
        try:
            return _parse_next_steps(data, top_k)
        except InvariantViolationError:
            raise

    if last_error.startswith("LLM call returned None"):
        raise LLMUnavailableError(
            "LLM call returned None twice during next-step synthesis."
        )
    raise InvariantViolationError(
        f"synthesize_next_steps: malformed LLM output after retry — {last_error}"
    )


def _build_next_steps_prompt(
    annotations: list[ClusterAnnotation],
    nmi_matrix: pd.DataFrame,
    top_k: int,
) -> str:
    template = (_PROMPTS_DIR / "next_steps.tmpl").read_text()
    annotation_block = _render_annotation_block(annotations)
    nmi_low_pairs = _render_low_nmi_pairs(nmi_matrix)
    return template.format(
        annotation_block=annotation_block,
        nmi_low_pairs=nmi_low_pairs,
        top_k=top_k,
    )


def _render_annotation_block(annotations: list[ClusterAnnotation]) -> str:
    if not annotations:
        return "(no annotations produced yet)"
    return "\n".join(
        f"- cluster {a.cluster_id}: {a.cell_type} (n={a.n_cells}, conf={a.confidence:.2f})"
        for a in annotations
    )


def _render_low_nmi_pairs(nmi_matrix: pd.DataFrame, threshold: float = 0.65) -> str:
    """Emit rows of (member_i, member_j, value) where i < j and value < threshold."""
    if nmi_matrix.empty:
        return "(no NMI matrix available)"
    pairs: list[tuple[str, str, float]] = []
    cols = list(nmi_matrix.columns)
    for i, mi in enumerate(cols):
        for mj in cols[i + 1:]:
            try:
                v = float(nmi_matrix.loc[mi, mj])
            except (KeyError, ValueError):
                continue
            if v < threshold:
                pairs.append((mi, mj, v))
    pairs.sort(key=lambda t: t[2])
    if not pairs:
        return "(all pair-wise NMI ≥ threshold; no contested boundaries)"
    return "\n".join(f"  {mi} <-> {mj}: NMI={v:.3f}" for mi, mj, v in pairs)


def _parse_next_steps(data: dict, top_k: int) -> list[NextStep]:
    raw = data.get("next_steps", [])
    if not isinstance(raw, list):
        raise InvariantViolationError("next_steps must be a JSON array")

    out: list[NextStep] = []
    for entry in raw[:top_k]:
        if not isinstance(entry, dict):
            continue
        skill = str(entry.get("skill", ""))
        evidence_refs = entry.get("evidence_refs", [])
        if skill not in _ALLOWED_NEXT_STEP_SKILLS:
            raise InvariantViolationError(
                f"next_step skill '{skill}' not in allowed downstream set "
                f"{sorted(_ALLOWED_NEXT_STEP_SKILLS)}"
            )
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise InvariantViolationError(
                f"next_step skill={skill!r} has empty evidence_refs. ADR 0012 "
                f"T3 invariant: every β recommendation MUST cite ≥1 typed "
                f"artifact row."
            )
        out.append(NextStep(
            skill=skill,
            args_hint=str(entry.get("args_hint", "")),
            priority=int(entry.get("priority", 2)),
            evidence_refs=[str(r) for r in evidence_refs],
            reason=str(entry.get("reason", "")),
        ))
    return out


# --------------------------------------------------------------------------- #
# JSON extraction                                                             #
# --------------------------------------------------------------------------- #

def _extract_json(raw: str) -> dict:
    """Extract a JSON object from raw LLM output, stripping code fences if present."""
    # Try direct parse first.
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try markdown code fence extraction.
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"code-fence content not valid JSON: {exc}") from exc

    # Try last-resort regex for embedded JSON object.
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError(f"embedded JSON not parseable: {exc}") from exc

    raise ValueError(f"no JSON object found in LLM output (first 200 chars): {text[:200]!r}")
