"""Prompts: typed inputs, the templates, reply checks and the leak check.

A prompt is rendered only from the typed inputs below; nothing concatenates
free strings into it. Before any request, the text this layer injects (the
tissue string, the data summary, the templates and the free-orchestration
task) is checked for a number of layers, regions, zones, niches, domains or
areas; a hit raises :exc:`LeakError`. The skill documentation and anything
derived from trial outputs are not checked.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from omicsclaw.ensemble.tuning.evidence import Evidence

__all__ = [
    "COUNT_PATTERNS",
    "DataSummary",
    "FreeTaskInput",
    "KDecision",
    "KDecisionInput",
    "LeakError",
    "ProposeInput",
    "ReplyError",
    "SkillText",
    "TEMPLATE_NAMES",
    "check_leak",
    "load_template",
    "marker_catalogue",
    "parse_json_reply",
    "render_compact_markers",
    "render_curves",
    "render_free_task",
    "render_full_markers",
    "render_k_decision",
    "render_k_followup",
    "render_nesting",
    "render_propose",
    "render_resolution_map",
    "template_sha256",
    "validate_k_reply",
    "validate_proposal_batch",
]

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATE_NAMES = ("k_decision.txt", "propose.txt", "free_task.txt")
FOLLOW_UP_MARKER = "----8<---- follow-up\n"

_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    "fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
)
COUNT_PATTERNS = (
    re.compile(
        rf"\b(\d+|{_NUMBER_WORDS})\b\s*[-‐]?\s*\b(layers?|regions?|zones?|niches?|domains?|areas?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(\d+|[一二三四五六七八九十]+)\s*(个)?(层|区域|分区|区)"),
)
"""A number of layers, regions, zones, niches, domains or areas, in English or Chinese."""


class LeakError(ValueError):
    """An injected field states a number of regions; no request was made.

    :ivar field: The field that matched.
    :ivar match: The matched text.
    """

    def __init__(self, field_name: str, match: str) -> None:
        super().__init__(f"the {field_name} states a count of regions ({match!r}); nothing was sent")
        self.field = field_name
        self.match = match


def check_leak(fields: Mapping[str, str | None]) -> None:
    """Raise :exc:`LeakError` on the first field matching :data:`COUNT_PATTERNS`."""
    for name, text in fields.items():
        if not text:
            continue
        for pattern in COUNT_PATTERNS:
            found = pattern.search(text)
            if found:
                raise LeakError(name, found.group(0))


# ---- templates ------------------------------------------------------------------------------


def load_template(name: str) -> str:
    """The raw text of template *name* (one of :data:`TEMPLATE_NAMES`)."""
    if name not in TEMPLATE_NAMES:
        raise ValueError(f"unknown template {name!r}")
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def template_sha256() -> dict[str, str]:
    """sha256 of every template's bytes."""
    return {name: hashlib.sha256((TEMPLATE_DIR / name).read_bytes()).hexdigest() for name in TEMPLATE_NAMES}


def _fill(template: str, values: Mapping[str, str]) -> str:
    return string.Template(template).substitute(values)


# ---- typed inputs ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillText:
    """A skill's ``SKILL.md`` body and its ``references/parameters.md``, as shown to the model."""

    skill_md: str
    parameters_md: str = ""

    @property
    def text(self) -> str:
        parts = [self.skill_md.strip()]
        if self.parameters_md.strip():
            parts.append("### references/parameters.md\n\n" + self.parameters_md.strip())
        return "\n\n".join(parts)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DataSummary:
    """What the model is told about the data; built without any ``obs`` column."""

    platform: str
    species: str
    n_obs: int
    n_vars: int
    median_counts: float | None
    median_genes: float | None
    x_span: float | None
    y_span: float | None
    preprocessing: Mapping[str, Any] = field(default_factory=dict)
    obsm_keys: tuple[str, ...] = ()
    n_batches: int | None = None

    @classmethod
    def from_description(cls, description: Mapping[str, Any], *, platform: str = "") -> "DataSummary":
        """From the ``data`` block of ``markers.json``."""
        return cls(
            platform=platform or "not given",
            species=str(description.get("species") or "not given"),
            n_obs=int(description.get("n_obs") or 0),
            n_vars=int(description.get("n_vars") or 0),
            median_counts=description.get("median_counts"),
            median_genes=description.get("median_genes"),
            x_span=description.get("x_span"),
            y_span=description.get("y_span"),
            preprocessing=dict(description.get("preprocessing") or {}),
            obsm_keys=tuple(description.get("obsm_keys") or ()),
            n_batches=description.get("n_batches"),
        )

    def render(self) -> str:
        lines = [
            f"platform: {self.platform}",
            f"species: {self.species}",
            f"observations: {self.n_obs}; genes: {self.n_vars}",
        ]
        if self.median_counts is not None or self.median_genes is not None:
            lines.append(
                f"median counts per observation: {_num(self.median_counts)}; "
                f"median genes detected per observation: {_num(self.median_genes)}"
            )
        if self.x_span is not None and self.y_span is not None:
            aspect = self.x_span / self.y_span if self.y_span else math.inf
            lines.append(
                f"coordinate span: x {_num(self.x_span)}, y {_num(self.y_span)} (aspect ratio {aspect:.2f})"
            )
        if self.preprocessing:
            settings = ", ".join(f"{key}={_num(value)}" for key, value in sorted(self.preprocessing.items()))
            lines.append(f"preprocessing: {settings}")
        if self.obsm_keys:
            lines.append("embeddings and coordinates (obsm): " + ", ".join(self.obsm_keys))
        if self.n_batches is not None:
            lines.append(f"batches: {self.n_batches}")
        return "\n".join(lines)


def _num(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


@dataclass(frozen=True)
class KDecisionInput:
    """Everything the K decision is rendered from."""

    grid: tuple[int, ...]
    skill: SkillText
    data: DataSummary
    tissue: str | None
    evidence: Evidence
    markers: Mapping[str, Any]


@dataclass(frozen=True)
class ProposeInput:
    """Everything a stage-1 proposal is rendered from.

    ``default_result`` holds ``params``, ``n_labels``, ``fixed_k_score``,
    ``se``, ``pas`` and ``silhouette``; ``sweeps`` the planned one-parameter
    settings; ``resolution_map`` the probe's ``resolution -> n_labels`` for a
    calibrated method.
    """

    method: str
    k: int
    method_summary: str
    fixed: Mapping[str, Any]
    dimensions: tuple[str, ...]
    k_control: str
    default_result: Mapping[str, Any]
    sweeps: tuple[Mapping[str, Any], ...]
    resolution_map: Mapping[float, int] | None
    skill: SkillText
    data: DataSummary
    tissue: str | None


@dataclass(frozen=True)
class FreeTaskInput:
    """Everything the free-orchestration task message is rendered from."""

    skill_name: str
    input_path: str
    run_id: str
    probe_run_id: str
    decision: KDecisionInput
    methods: Mapping[str, str]
    budgets: Mapping[str, int]
    resolution_map: Mapping[str, Mapping[float, int]]


# ---- evidence sections ----------------------------------------------------------------------------


def _band(value: float | None, band: tuple[float | None, float | None]) -> str:
    if value is None:
        return "-"
    lo, hi = band
    if lo is None or hi is None:
        return f"{value:.3f}"
    return f"{value:.3f} [{lo:.3f}, {hi:.3f}]"


def _rank(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:g}"


def render_curves(evidence: Evidence) -> str:
    """The stability table: one row per K of the grid, with neutral definitions."""
    head = [
        "f(K): share of subsample clustering runs (leiden and louvain over the resolution grid on "
        "80% subsamples of the observations) that produced exactly K clusters.",
        "c(K): 1 - rPAC of the consensus matrix of those runs with K clusters (1 means the runs "
        "always agree on which observations belong together).",
        "a(K): mean pairwise adjusted mutual information between partitions with K clusters from "
        "different methods (members listed).",
        f"Brackets: bootstrap 95% intervals. f and c are defined only where f(K) >= {evidence.min_f:g}; "
        "a needs at least three partitions. Rank: position of K among the K where that curve is defined "
        "(1 = highest). Peak frequency: share of bootstrap resamples in which K is a local maximum of "
        "that curve. Stable peak: a peak frequency of at least 0.5 on some curve.",
        "",
        "| K | f | c | a | rank f/c/a | peak freq f/c/a | runs at K | a members | stable peak |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    rows = []
    for k in evidence.grid:
        row = evidence.rows.get(k)
        if row is None:
            continue
        values = {
            curve: row.values[curve] if row.defined.get(curve) else None for curve in ("f", "c", "a")
        }
        peak = row.peak_frequency
        rows.append(
            f"| {k} | {_band(values['f'], row.bands['f'])} | {_band(values['c'], row.bands['c'])} | "
            f"{_band(values['a'], row.bands['a'])} | "
            f"{_rank(row.ranks.get('f'))}/{_rank(row.ranks.get('c'))}/{_rank(row.ranks.get('a'))} | "
            f"{_rank(peak.get('f'))}/{_rank(peak.get('c'))}/{_rank(peak.get('a'))} | {row.runs} | "
            f"{', '.join(row.a_members) or '-'} | {'yes' if row.in_stable_peaks else 'no'} |"
        )
    return "\n".join(head + rows)


def _params_text(params: Mapping[str, Any] | None) -> str:
    if not params:
        return "defaults"
    return ", ".join(f"{name}={params[name]}" for name in sorted(params))


def render_compact_markers(markers: Mapping[str, Any], grid: Sequence[int]) -> str:
    lines = []
    compact = markers.get("compact") or {}
    for k in grid:
        block = compact.get(str(k))
        if block is None:
            lines.append(f"K={k}: no partition with K clusters in the probe")
            continue
        domains = "; ".join(
            f"{d['domain']} ({d['share'] * 100:.0f}%): {', '.join(d['genes']) or '-'}" for d in block["domains"]
        )
        lines.append(f"K={k} ({block.get('method')}, {_params_text(block.get('params'))}): {domains}")
    return "\n".join(lines)


def render_full_markers(markers: Mapping[str, Any], ks: Iterable[int]) -> str:
    full = markers.get("full") or {}
    blocks = []
    for k in sorted(ks):
        block = full.get(str(k))
        if block is None:
            blocks.append(f"### K={k}\n(no partition with K clusters in the probe)")
            continue
        lines = [f"### K={k} ({block.get('method')}, {_params_text(block.get('params'))})"]
        for d in block["domains"]:
            genes = ", ".join(
                f"{m['gene']} (log2FC {_num(m.get('log2fc'))}, in {_pct(m.get('pct_in'))}, out {_pct(m.get('pct_out'))})"
                for m in d["markers"]
            )
            lines.append(
                f"- domain {d['domain']}: {d['share'] * 100:.1f}% of observations; same-label spatial "
                f"neighbours {_pct(d.get('same_label_neighbours'))}; centroid "
                f"({d['centroid'][0]:.2f}, {d['centroid'][1]:.2f}); markers: {genes or '-'}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(none)"


def _pct(value: Any) -> str:
    if value is None:
        return "?"
    return f"{float(value) * 100:.0f}%"


def render_nesting(markers: Mapping[str, Any]) -> str:
    blocks = []
    for pair in markers.get("nesting") or []:
        rows = ", ".join(f"{r['domain']} -> {r['into']} ({r['share'] * 100:.0f}%)" for r in pair["rows"])
        blocks.append(f"K={pair['fine']} into K={pair['coarse']}: {rows}")
    return "\n".join(blocks) if blocks else "(fewer than two K with full blocks)"


def render_resolution_map(mapping: Mapping[float, int] | None) -> str:
    if not mapping:
        return ""
    by_k: dict[int, list[float]] = {}
    for resolution, n in sorted(mapping.items()):
        by_k.setdefault(int(n), []).append(float(resolution))
    return "; ".join(
        f"K={k}: resolution {', '.join(f'{r:g}' for r in values)}" for k, values in sorted(by_k.items())
    )


def marker_catalogue(markers: Mapping[str, Any], full_ks: Iterable[int]) -> dict[tuple[int, str], set[str]]:
    """``{(K, domain): genes shown}`` over the compact table and the full blocks of *full_ks*."""
    shown: dict[tuple[int, str], set[str]] = {}
    for key, block in (markers.get("compact") or {}).items():
        for d in block["domains"]:
            shown.setdefault((int(key), str(d["domain"])), set()).update(d["genes"])
    wanted = {int(k) for k in full_ks}
    for key, block in (markers.get("full") or {}).items():
        if int(key) not in wanted:
            continue
        for d in block["domains"]:
            shown.setdefault((int(key), str(d["domain"])), set()).update(m["gene"] for m in d["markers"])
    return shown


# ---- rendering --------------------------------------------------------------------------------------


def _split_k_template() -> tuple[str, str]:
    text = load_template("k_decision.txt")
    first, _, follow = text.partition(FOLLOW_UP_MARKER)
    return first, follow


def _tissue_text(tissue: str | None) -> str:
    return tissue if tissue else "not given"


def _check_injected(template: str, data: DataSummary, tissue: str | None, extra: Mapping[str, str] | None = None) -> str:
    rendered_data = data.render()
    fields = {"template": template, "data summary": rendered_data, "tissue": tissue or ""}
    fields.update(extra or {})
    check_leak(fields)
    return rendered_data


def render_k_decision(inp: KDecisionInput) -> str:
    """The first message of the K decision.

    :raises LeakError: An injected field states a count of regions.
    """
    template, _ = _split_k_template()
    data = _check_injected(template, inp.data, inp.tissue)
    return _fill(template, {
        "grid_text": f"{inp.grid[0]}..{inp.grid[-1]}",
        "skill_md": inp.skill.text,
        "data": data,
        "tissue": _tissue_text(inp.tissue),
        "curves": render_curves(inp.evidence),
        "compact_markers": render_compact_markers(inp.markers, inp.grid),
        "full_markers": render_full_markers(inp.markers, inp.evidence.stable_peaks),
        "nesting": render_nesting(inp.markers),
    }).rstrip() + "\n"


def render_k_followup(inp: KDecisionInput, requested: Sequence[int], markers: Mapping[str, Any]) -> str:
    """The second message of the K decision, with the requested marker blocks.

    *markers* holds the full blocks of the requested K and the nesting over
    the stable peaks and the requested K.
    """
    _, template = _split_k_template()
    check_leak({"template": template})
    return _fill(template, {
        "full_markers": render_full_markers(markers, requested),
        "nesting": render_nesting(markers),
    }).rstrip() + "\n"


def render_propose(inp: ProposeInput) -> str:
    """The stage-1 proposal prompt.

    :raises LeakError: An injected field states a count of regions.
    """
    template = load_template("propose.txt")
    data = _check_injected(template, inp.data, inp.tissue)
    result = inp.default_result
    default_lines = [
        f"parameters: {_params_text(result.get('params'))}",
        f"clusters: {result.get('n_labels')}",
    ]
    if result.get("fixed_k_score") is not None:
        se = result.get("se")
        default_lines.append(
            f"fixed-K score: {result['fixed_k_score']:.4f}" + (f" (standard error {se:.4f})" if se is not None else "")
        )
    else:
        default_lines.append("fixed-K score: none (the default did not produce K clusters, or K has no reference)")
    default_lines.append(
        f"PAS (chance-corrected, higher is smoother): {_num(result.get('pas'))}; "
        f"silhouette on X_pca: {_num(result.get('silhouette'))}"
    )
    mapping = render_resolution_map(inp.resolution_map)
    return _fill(template, {
        "k": str(inp.k),
        "method_summary": inp.method_summary,
        "fixed": _params_text(inp.fixed) if inp.fixed else "none",
        "dimensions": ", ".join(inp.dimensions),
        "k_control": inp.k_control,
        "default_result": "\n".join(default_lines),
        "sweeps": "\n".join(f"- {_params_text(s)}" for s in inp.sweeps) or "- none",
        "resolution_map": (f"\nResolution to number of clusters in the probe (default parameters): {mapping}\n"
                           if mapping else ""),
        "skill_md": inp.skill.text,
        "data": data,
        "tissue": _tissue_text(inp.tissue),
    }).rstrip() + "\n"


def render_free_task(inp: FreeTaskInput) -> str:
    """The task message of the free-orchestration arm.

    :raises LeakError: An injected field states a count of regions.
    """
    template = load_template("free_task.txt")
    decision = inp.decision
    methods = "\n".join(
        f"- {name}: budget {inp.budgets.get(name, 0)} new runs\n  " + summary.replace("\n", "\n  ")
        for name, summary in inp.methods.items()
    )
    maps = "\n".join(
        f"- {name}: {render_resolution_map(mapping)}" for name, mapping in inp.resolution_map.items() if mapping
    ) or "(no calibrated method)"
    data = _check_injected(template, decision.data, decision.tissue)
    text = _fill(template, {
        "skill": inp.skill_name,
        "input": inp.input_path,
        "run_id": inp.run_id,
        "probe_run_id": inp.probe_run_id,
        "grid_text": f"{decision.grid[0]}..{decision.grid[-1]}",
        "methods": methods,
        "skill_md": decision.skill.text,
        "data": data,
        "tissue": _tissue_text(decision.tissue),
        "curves": render_curves(decision.evidence),
        "resolution_map": maps,
        "compact_markers": render_compact_markers(decision.markers, decision.grid),
        "full_markers": render_full_markers(decision.markers, decision.evidence.stable_peaks),
        "nesting": render_nesting(decision.markers),
    }).rstrip() + "\n"
    return text


# ---- replies ------------------------------------------------------------------------------------------


class ReplyError(ValueError):
    """A reply that does not satisfy its contract; the message says what to fix."""


def parse_json_reply(text: str) -> Any:
    """The JSON value in a reply, with code fences and surrounding prose stripped.

    :raises ReplyError: No JSON object can be read.
    """
    stripped = (text or "").strip()
    fence = re.match(r"^```[a-zA-Z0-9_-]*\s*\n(.*?)\n?```\s*$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(stripped[start:end + 1])
        except ValueError:
            pass
    raise ReplyError("the reply is not a JSON object")


@dataclass
class KDecision:
    """A valid final K decision."""

    chosen_k: int
    rationale: str
    evidence: list[dict[str, Any]]
    confidence: str


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def validate_k_reply(
    reply: Any,
    *,
    grid: Sequence[int],
    stable_peaks: Sequence[int],
    shown: Mapping[tuple[int, str], set[str]],
    skill_text: str,
    may_request: bool,
) -> KDecision | list[int]:
    """Check one reply of the K decision.

    :returns: The list of K asked for, when *may_request* and the reply is a
        valid marker request; otherwise the decision.
    :raises ReplyError: The reply breaks the contract; the message lists the
        allowed values.
    """
    grid_set = set(grid)
    if not isinstance(reply, Mapping):
        raise ReplyError("reply with one JSON object")
    if "request_markers" in reply:
        if not may_request:
            raise ReplyError("you cannot ask for more markers now; reply with your decision")
        requested = reply["request_markers"]
        if not isinstance(requested, list) or not 1 <= len(requested) <= 2:
            raise ReplyError("request_markers must list one or two K")
        ks = [_as_int(value) for value in requested]
        allowed = sorted(grid_set - set(stable_peaks))
        if any(k is None or k not in grid_set or k in stable_peaks for k in ks) or len(set(ks)) != len(ks):
            raise ReplyError(f"request_markers may name only K from {allowed} (grid K that are not stable peaks)")
        return ks  # type: ignore[return-value]
    missing = [key for key in ("chosen_k", "rationale", "evidence", "confidence") if key not in reply]
    if missing:
        raise ReplyError(f"the decision is missing {', '.join(missing)}")
    chosen = _as_int(reply["chosen_k"])
    if chosen is None or chosen not in grid_set:
        raise ReplyError(f"chosen_k must be an integer from {sorted(grid_set)}")
    rationale = reply["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise ReplyError("rationale must be a non-empty string")
    if reply["confidence"] not in ("low", "medium", "high"):
        raise ReplyError("confidence must be low, medium or high")
    evidence = reply["evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 10:
        raise ReplyError("evidence must list between 1 and 10 items")
    for index, item in enumerate(evidence):
        where = f"evidence[{index}]"
        if not isinstance(item, Mapping):
            raise ReplyError(f"{where} must be an object")
        k = _as_int(item.get("k"))
        kind = item.get("kind")
        if kind == "markers":
            domain = str(item.get("domain"))
            genes = item.get("genes")
            if k is None or (k, domain) not in shown:
                raise ReplyError(f"{where}: K={item.get('k')} has no domain {domain!r} among the markers shown")
            if not isinstance(genes, list) or not genes or not {str(g) for g in genes} <= shown[(k, domain)]:
                raise ReplyError(
                    f"{where}: genes must be among those shown for K={k} domain {domain}: "
                    f"{sorted(shown[(k, domain)])}"
                )
        elif kind == "curve":
            if k is None or k not in grid_set:
                raise ReplyError(f"{where}: k must be from the grid")
            if item.get("curve") not in ("f", "c", "a"):
                raise ReplyError(f"{where}: curve must be f, c or a")
        elif kind == "skill_md":
            quote = item.get("quote")
            if not isinstance(quote, str) or not quote.strip() or quote not in skill_text:
                raise ReplyError(f"{where}: quote must be copied exactly from the skill documentation")
        else:
            raise ReplyError(f"{where}: kind must be markers, curve or skill_md")
    return KDecision(
        chosen_k=chosen,
        rationale=rationale,
        evidence=[dict(item) for item in evidence],
        confidence=reply["confidence"],
    )


def validate_proposal_batch(reply: Any) -> list[tuple[Any, str]]:
    """The ``(params, why)`` of each proposal in a reply, unchecked against the search space.

    :raises ReplyError: The reply is not ``{"proposals": [...]}``.
    """
    if not isinstance(reply, Mapping) or not isinstance(reply.get("proposals"), list):
        raise ReplyError('reply with {"proposals": [...]} holding exactly 3 settings')
    out = []
    for item in reply["proposals"]:
        if isinstance(item, Mapping):
            out.append((item.get("params"), str(item.get("why") or "")))
        else:
            out.append((None, ""))
    return out
