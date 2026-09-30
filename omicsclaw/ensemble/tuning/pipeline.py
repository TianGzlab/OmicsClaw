"""The tuning pipeline: probe, stability evidence, K, then each method at K.

:class:`TuningPipeline` runs one skill's methods on one input::

    probe       exact methods at every K of the grid; calibrated methods over the
                resolution grid on the full input and on each subsample
    evidence    stability curves, the fixed-K reference ranges, marker genes
    K           the model's decision (or the fallback K, or the caller's K)
    tuning      per method, in parallel: a grid over one dimension, or two
                stages over two or three; calibrated methods calibrate every
                parameter set to K
    selection   each method's answer and the single final trial

The probe and its evidence are kept under ``<probe_base>-probe/`` and reused
by any later run on the same input with the same probe design, so several
arms share one probe. Trials go through the :class:`EnsembleRunner`; the
pipeline counts every new run against per-method caps and, when given one,
against a session :class:`~omicsclaw.ensemble.tuning.budget.RunBudget`.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import json
import math
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from omicsclaw.ensemble.runner import EnsembleRunner, TrialResult
from omicsclaw.ensemble.space import SpecError, TuningSpec, validate_params
from omicsclaw.ensemble.store import read_json, write_json
from omicsclaw.ensemble.tuning import probe as probe_design_module
from omicsclaw.ensemble.tuning.budget import BudgetExceeded, RunBudget, caps as budget_caps
from omicsclaw.ensemble.tuning.calibrate import calibrate, initial_value
from omicsclaw.ensemble.tuning.evidence import Evidence, load_evidence
from omicsclaw.ensemble.tuning.judge import Evaluated, MethodChoice, choose_final, choose_method, eligible, skip_stage2
from omicsclaw.ensemble.tuning.ledger import Ledger, Selection, TUNING_RECORD_SCHEMA, utc_now
from omicsclaw.ensemble.tuning.llm import LLMSettings, decide_k, propose
from omicsclaw.ensemble.tuning.probe import probe_run_id, sub_run_id
from omicsclaw.ensemble.tuning.prompts import (
    DataSummary,
    KDecisionInput,
    LeakError,
    ProposeInput,
    SkillText,
    check_leak,
    template_sha256,
)
from omicsclaw.ensemble.tuning.scoring import KReference, build_references, member_values, score_trial
from omicsclaw.ensemble.tuning.search import (
    config_key,
    deviation,
    fixed_values,
    full_key,
    grid_values,
    neighbourhood_points,
    random_configs,
    search_plan,
    stage1_seed,
    sweep_points,
)
from omicsclaw.tools.context import report_progress

__all__ = [
    "EvidenceBundle",
    "PipelineError",
    "TuningPipeline",
    "TuningRequest",
    "TuningSettings",
    "code_digest",
    "labels_fingerprint",
]

TOOL_NAME = "optimize_params"
ARMS = ("det", "random", "user")


class PipelineError(RuntimeError):
    """The pipeline cannot run on this input; the message says why."""


@dataclass(frozen=True)
class TuningSettings:
    """The pipeline's fixed constants and engineering limits."""

    groups: int = 12
    calibration_runs: int = 4
    retries: int = 2
    sweeps: int = 3
    proposals: int = 3
    grid: tuple[int, ...] = probe_design_module.K_GRID
    resolutions: tuple[float, ...] = probe_design_module.RESOLUTION_GRID
    n_sub: int = probe_design_module.B_SUB
    subsample_fraction: float = probe_design_module.SUBSAMPLE_FRACTION
    subsample_seeds: tuple[int, ...] = probe_design_module.SUBSAMPLE_SEEDS
    boot_fc: int = probe_design_module.BOOT_FC
    boot_a: int = probe_design_module.BOOT_A
    seed_fc: int = probe_design_module.SEED_FC
    seed_a: int = probe_design_module.SEED_A
    consensus_seed: int = probe_design_module.CONSENSUS_SEED
    consensus_subset: int = probe_design_module.CONSENSUS_SUBSET
    min_f: float = probe_design_module.MIN_F
    max_s: float = 43200.0
    keep_subsamples: bool = False
    helper_timeout_s: float = 7200.0
    stability_processes: int | None = None
    stability_threads: int = 2

    def frozen(self) -> dict[str, Any]:
        """The settings that define the method, as recorded in the ledger."""
        return {
            "groups": self.groups,
            "calibration_runs": self.calibration_runs,
            "retries": self.retries,
            "stage1": {"sweeps": self.sweeps, "proposals": self.proposals},
            "k_grid": list(self.grid),
            "resolution_grid": list(self.resolutions),
            "b_sub": self.n_sub,
            "subsample_fraction": self.subsample_fraction,
            "subsample_seeds": list(self.subsample_seeds),
            "boot_fc": self.boot_fc,
            "boot_a": self.boot_a,
            "seeds": {"fc": self.seed_fc, "a": self.seed_a, "consensus": self.consensus_seed},
            "consensus_subset": self.consensus_subset,
            "min_f": self.min_f,
        }


@dataclass(frozen=True)
class TuningRequest:
    """One tuning run.

    ``arm``: ``det`` (the model decides K and proposes), ``random`` (the
    fallback K and random proposals, with ``random_index`` as seed index) or
    ``user`` (``k`` given; set automatically). ``probe_base`` names the
    probe to create or reuse; it defaults to ``run_id``.
    """

    skill: str
    input: Path
    run_id: str
    methods: tuple[str, ...] | None = None
    tissue: str | None = None
    k: int | None = None
    arm: str = "det"
    random_index: int | None = None
    context: Mapping[str, Any] = field(default_factory=dict)
    probe_base: str | None = None
    tissue_withheld: bool = False


@dataclass
class ProbeTrial:
    """What the pipeline keeps of one probe trial."""

    method: str
    kind: str
    run_id: str
    trial: str
    status: str
    params: dict[str, Any]
    n_labels: int | None
    labels: str
    metrics: dict[str, Any] | None
    requested_k: int | None = None
    resolution: float | None = None
    b: int | None = None
    h5ad: str | None = None
    wall_s: float = 0.0
    lease_gpu: str | None = None
    cpus: int = 1

    def to_json(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        return data


@dataclass
class EvidenceBundle:
    """The probe and everything derived from it, shared by every arm on one input."""

    probe_base: str
    trials: list[ProbeTrial]
    references: dict[int, KReference]
    evidence: Evidence
    markers: dict[str, Any]
    data: DataSummary
    directory: Path
    reused: bool = False

    def default_trial(self, spec: TuningSpec, method: str, k: int) -> ProbeTrial | None:
        """The probe trial with the method's default parameters at K, if any.

        Exact methods: the trial run with K requested (whatever it returned).
        Calibrated methods: among full-input trials with K labels, the one of
        median resolution.
        """
        control = spec.method(method).k_control
        if control is None:
            return None
        if control.kind == "exact":
            return next((t for t in self.trials if t.method == method and t.kind == "exact"
                         and t.requested_k == k), None)
        at_k = sorted((t for t in self.trials if t.method == method and t.kind == "full"
                       and t.status == "ok" and t.n_labels == k), key=lambda t: t.resolution or 0.0)
        return at_k[len(at_k) // 2] if at_k else None

    def resolution_map(self, method: str) -> dict[float, int]:
        """``resolution -> n_labels`` of a calibrated method's full-input probe trials."""
        return {
            float(t.resolution): int(t.n_labels)
            for t in self.trials
            if t.method == method and t.kind == "full" and t.status == "ok" and t.n_labels is not None
            and t.resolution is not None
        }


def code_digest(paths: Sequence[Path]) -> str:
    """sha256 over the relative names and bytes of every file under *paths* (``__pycache__`` excluded)."""
    digest = hashlib.sha256()
    for root in paths:
        root = Path(root)
        files = [root] if root.is_file() else sorted(
            p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
        )
        for path in files:
            digest.update(str(path.relative_to(root.parent)).encode("utf-8"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def labels_fingerprint(path: Path) -> str | None:
    """sha256 of a label table with labels renumbered by first appearance in obs-id order."""
    try:
        with gzip.open(path, "rt", newline="", encoding="utf-8") as source:
            rows = list(csv.reader(source))[1:]
    except OSError:
        return None
    rows.sort(key=lambda row: row[0])
    names: dict[str, int] = {}
    digest = hashlib.sha256()
    for obs_id, label in rows:
        code = names.setdefault(label, len(names))
        digest.update(f"{obs_id}\t{code}\n".encode("utf-8"))
    return digest.hexdigest()


def _n_labels(result: TrialResult) -> int | None:
    if result.status != "ok" or not result.metrics:
        return None
    value = result.metrics.get("n_labels")
    return int(value) if value is not None else None


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), digits)


class _MethodBudget:
    """New runs of one method against its cap, and the session budget if any."""

    def __init__(self, method: str, cap: int, session_budget: RunBudget | None, session: str) -> None:
        self.method = method
        self.cap = cap
        self.used = 0
        self.session_budget = session_budget
        self.session = session

    def take(self) -> bool:
        if self.used >= self.cap:
            return False
        if self.session_budget is not None:
            try:
                self.session_budget.reserve(self.session, self.method)
            except BudgetExceeded:
                return False
        self.used += 1
        return True


class TuningPipeline:
    """Runs :class:`TuningRequest` s over one runner.

    :param runner: The trial runner (its catalogue, pool and executor are used).
    :param model: The model for the K decision and proposals; ``None`` allows
        only the ``random`` and ``user`` arms.
    :param llm_settings: What is recorded about *model*.
    :param skill_text: Returns the ``SKILL.md`` body and ``parameters.md`` of a skill.
    :param settings: Constants and limits.
    :param budget: A session budget every new run is also counted against.
    :param session: The session the budget is kept for.
    :param obs_allowlist: When given, the input's ``obs`` columns must all be in it.
    :param code_paths: Files and directories whose digest is recorded.
    """

    def __init__(
        self,
        runner: EnsembleRunner,
        *,
        model: Any = None,
        llm_settings: LLMSettings | None = None,
        skill_text: Callable[[str], SkillText],
        settings: TuningSettings | None = None,
        budget: RunBudget | None = None,
        session: str = "",
        obs_allowlist: Sequence[str] | None = None,
        code_paths: Sequence[Path] = (),
        freeze_sha256: str | None = None,
    ) -> None:
        self.runner = runner
        self.model = model
        self.llm_settings = llm_settings or LLMSettings(model="", provider="")
        self.skill_text = skill_text
        self.settings = settings or TuningSettings()
        self.budget = budget
        self.session = session
        self.obs_allowlist = tuple(obs_allowlist) if obs_allowlist is not None else None
        self.code_paths = tuple(code_paths)
        self.freeze_sha256 = freeze_sha256
        self._seq = 0
        self._fingerprints: dict[tuple[str, str], str] = {}

    # ---- helpers -------------------------------------------------------------------------

    async def _module(
        self, module: str, args: Sequence[str], *, cwd: Path, marker: str, threads: int | None = None
    ) -> dict[str, Any]:
        executor = self.runner.executor
        env = {"PYTHONPATH": str(self.runner.repo_root), "PYTHONDONTWRITEBYTECODE": "1"}
        if threads is not None:
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
                env[name] = str(threads)
        result = await executor.capture(
            [executor.python, "-m", module, *args],
            cwd=cwd,
            timeout=self.settings.helper_timeout_s,
            env=env,
        )
        for line in reversed(result.output.splitlines()):
            if line.startswith(marker + "="):
                return json.loads(line[len(marker) + 1:])
        raise PipelineError(f"{module} failed (exit {result.exit_code}): {result.output[-2000:]}")

    async def describe_input(self, path: Path) -> dict[str, Any]:
        """``n_obs``, ``n_vars``, ``obs_columns`` and ``obsm_keys`` of the input."""
        return await self._module(
            "omicsclaw.ensemble.metrics.score", ["--describe-input", str(path)], cwd=path.parent, marker="DESCRIBE"
        )

    def check_input(self, spec: TuningSpec, description: Mapping[str, Any]) -> None:
        """Refuse an input without the expression embedding or with ``obs`` columns outside the allowlist.

        :raises SpecError: Either check fails.
        """
        expression = spec.reference.get("expression_obsm")
        if expression and expression not in (description.get("obsm_keys") or []):
            raise SpecError(
                f"the input has no obsm[{expression!r}]; the fixed-K score needs it (run the preprocessing skill first)"
            )
        if self.obs_allowlist is not None:
            extra = sorted(set(description.get("obs_columns") or []) - set(self.obs_allowlist))
            if extra:
                raise SpecError(
                    f"the input's obs has columns outside the allowed set {list(self.obs_allowlist)}: {extra}"
                )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def _progress(self, message: str) -> None:
        await report_progress(message, tool_name=TOOL_NAME)

    # ---- the probe ----------------------------------------------------------------------------

    def _probe_signature(self, spec: TuningSpec, methods: Sequence[str], sha: str, k: int | None,
                         context: Mapping[str, Any]) -> str:
        document = {
            "skill": spec.skill, "tuning_sha256": spec.sha256, "input_sha256": sha,
            "methods": list(methods), "settings": self.settings.frozen(), "k": k,
            "context": dict(context),
        }
        return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()

    async def prepare_evidence(
        self,
        spec: TuningSpec,
        methods: Sequence[str],
        input_path: Path,
        *,
        probe_base: str,
        context: Mapping[str, Any],
        k: int | None = None,
        ledger: Ledger | None = None,
        platform: str = "",
    ) -> EvidenceBundle:
        """Run (or reuse) the probe and compute stability, references and markers.

        With *k* given only the trials at that K and the full resolution scan
        are run, and there are no stability curves.
        """
        sha = await asyncio.to_thread(self.runner.input_sha256, input_path)
        probe_id = probe_run_id(probe_base)
        directory = self.runner.store.run_dir(probe_id) / "evidence"
        signature = self._probe_signature(spec, methods, sha, k, context)
        done = read_json(directory / "probe_done.json")
        if done is not None and done.get("signature") == signature:
            trials = [ProbeTrial(**item) for item in done["trials"]]
            reused = True
        else:
            trials = await self._run_probe(spec, methods, input_path, probe_base, context, k, directory)
            directory.mkdir(parents=True, exist_ok=True)
            write_json(directory / "probe_done.json", {
                "signature": signature, "input_sha256": sha, "written_at": utc_now(),
                "trials": [t.to_json() for t in trials],
            })
            reused = False
        if ledger is not None:
            for t in trials:
                fields = {key: value for key, value in t.to_json().items() if key not in ("metrics", "kind")}
                ledger.append("probe_trial", probe_kind=t.kind, **fields,
                              score=(t.metrics or {}).get("score") if t.metrics else None, reused=reused)
        scored = [t for t in trials if t.kind in ("exact", "full") and t.status == "ok" and t.n_labels is not None]
        references = build_references({"n_labels": t.n_labels, "metrics": t.metrics} for t in scored)
        write_json(directory / "reference.json", {
            "panel_version": _panel_version(spec),
            "per_k": {str(key): ref.to_json() for key, ref in references.items()},
        })
        grid = [k] if k is not None else list(self.settings.grid)
        if k is None:
            stability_path = directory / "stability.json"
            if not reused or not stability_path.is_file():
                await self._progress("computing stability curves")
                spec_path = directory / "stability_spec.json"
                write_json(spec_path, self._stability_spec(input_path, trials))
                args = ["--spec", str(spec_path), "--output", str(stability_path)]
                if self.settings.stability_processes:
                    args += ["--processes", str(self.settings.stability_processes)]
                await self._module("omicsclaw.ensemble.tuning.stability", args, cwd=directory, marker="STABILITY",
                                   threads=self.settings.stability_threads)
            evidence = load_evidence(read_json(stability_path) or {})
        else:
            evidence = Evidence(grid=grid, rows={}, stable_peaks=[], fallback_k=None, min_f=self.settings.min_f)
        markers_path = directory / "markers.json"
        partitions = self._representatives(trials, references, grid)
        if not reused or not markers_path.is_file():
            await self._progress("computing marker genes")
            await self._markers(input_path, partitions, evidence.stable_peaks, directory, markers_path, spec)
        markers = read_json(markers_path) or {}
        data = DataSummary.from_description(markers.get("data") or {}, platform=platform)
        return EvidenceBundle(
            probe_base=probe_base, trials=trials, references=references, evidence=evidence,
            markers=markers, data=data, directory=directory, reused=reused,
        )

    async def _run_probe(
        self, spec: TuningSpec, methods: Sequence[str], input_path: Path, probe_base: str,
        context: Mapping[str, Any], k: int | None, directory: Path,
    ) -> list[ProbeTrial]:
        design = probe_design_module.probe_design(
            spec, methods,
            grid=[k] if k is not None else self.settings.grid,
            resolutions=self.settings.resolutions,
            n_sub=self.settings.n_sub,
            subsample=k is None,
        )
        inputs: dict[int, Path] = {}
        if k is None and any(item.kind == "sub" for item in design):
            await self._progress(f"writing {self.settings.n_sub} subsamples")
            out = directory / "inputs"
            written = await self._module(
                "omicsclaw.ensemble.tuning.subsample",
                ["--input", str(input_path), "--output-dir", str(out),
                 "--seeds", ",".join(str(s) for s in self.settings.subsample_seeds[: self.settings.n_sub]),
                 "--fraction", repr(self.settings.subsample_fraction)],
                cwd=input_path.parent, marker="SUBSAMPLE",
            )
            for index, item in enumerate(written["files"], start=1):
                inputs[index] = Path(item["path"])
        await self._progress(f"probe: {len(design)} trials")
        specs = []
        for item in design:
            path = input_path if item.kind != "sub" else inputs[item.b]
            run_id = probe_run_id(probe_base) if item.kind != "sub" else sub_run_id(probe_base, item.b)
            specs.append(await asyncio.to_thread(
                self.runner.prepare, skill=spec.skill, method=item.method, input=path,
                params={**context, **item.params}, run_id=run_id,
            ))
        results = await self.runner.fan_out(specs)
        trials = []
        for item, result in zip(design, results):
            trials.append(ProbeTrial(
                method=item.method, kind=item.kind, run_id=result.run_id, trial=result.trial,
                status=result.status, params=dict(result.params), n_labels=_n_labels(result),
                labels=str(Path(result.output_dir) / "labels.csv.gz"),
                metrics=result.metrics if item.kind != "sub" else None,
                requested_k=item.requested_k, resolution=item.resolution, b=item.b, h5ad=result.h5ad,
                wall_s=result.wall_s, lease_gpu=result.lease_gpu, cpus=spec.method(item.method).resources.cpus,
            ))
        if not self.settings.keep_subsamples and inputs:
            shutil.rmtree(directory / "inputs", ignore_errors=True)
        return trials

    def _stability_spec(self, input_path: Path, trials: Sequence[ProbeTrial]) -> dict[str, Any]:
        ok = [t for t in trials if t.status == "ok"]
        return {
            "input": str(input_path),
            "grid": list(self.settings.grid),
            "n_sub": self.settings.n_sub,
            "sub": [{"b": t.b, "method": t.method, "resolution": t.resolution, "labels": t.labels}
                    for t in ok if t.kind == "sub"],
            "full": [{"method": t.method, "resolution": t.resolution, "labels": t.labels}
                     for t in ok if t.kind == "full"],
            "exact": [{"method": t.method, "requested_k": t.requested_k, "labels": t.labels}
                      for t in ok if t.kind == "exact"],
            "min_f": self.settings.min_f,
            "boot_fc": self.settings.boot_fc,
            "boot_a": self.settings.boot_a,
            "seed_fc": self.settings.seed_fc,
            "seed_a": self.settings.seed_a,
            "consensus_subset": self.settings.consensus_subset,
            "consensus_seed": self.settings.consensus_seed,
        }

    def _representatives(
        self, trials: Sequence[ProbeTrial], references: Mapping[int, KReference], grid: Sequence[int]
    ) -> dict[int, ProbeTrial]:
        """Per K, the probe trial with K labels and the highest fixed-K score (the earliest on a tie)."""
        chosen: dict[int, tuple[float, int, ProbeTrial]] = {}
        for order, t in enumerate(trials):
            if t.kind not in ("exact", "full") or t.status != "ok" or t.n_labels not in grid:
                continue
            scored = score_trial(t.metrics or {}, references.get(t.n_labels))
            value = scored.score if scored.score is not None else -math.inf
            best = chosen.get(t.n_labels)
            if best is None or value > best[0]:
                chosen[t.n_labels] = (value, order, t)
        return {k: entry[2] for k, entry in chosen.items()}

    async def _markers(
        self, input_path: Path, partitions: Mapping[int, ProbeTrial], full: Sequence[int],
        directory: Path, output: Path, spec: TuningSpec,
    ) -> None:
        spec_path = output.with_name(output.stem + "_spec.json")
        write_json(spec_path, {
            "input": str(input_path),
            "coords_obsm": spec.reference.get("coords_obsm", "spatial"),
            "partitions": [
                {"k": k, "labels": t.labels, "method": t.method, "trial": f"{t.run_id}/{t.method}/{t.trial}",
                 "params": _shown_params(spec, t)}
                for k, t in sorted(partitions.items())
            ],
            "full": sorted(full),
        })
        await self._module("omicsclaw.ensemble.tuning.markers", ["--spec", str(spec_path), "--output", str(output)],
                           cwd=directory, marker="MARKERS")

    async def requested_markers(
        self, bundle: EvidenceBundle, spec: TuningSpec, input_path: Path, requested: Sequence[int], out_dir: Path,
    ) -> dict[str, Any]:
        """Full marker blocks for *requested* plus the stable peaks, with their nesting."""
        partitions = self._representatives(bundle.trials, bundle.references, self.settings.grid)
        wanted = sorted(set(bundle.evidence.stable_peaks) | set(requested))
        chosen = {k: partitions[k] for k in wanted if k in partitions}
        name = "markers_requested_" + "_".join(str(k) for k in requested) + ".json"
        output = out_dir / name
        await self._markers(input_path, chosen, wanted, out_dir, output, spec)
        return read_json(output) or {}

    # ---- a whole run ---------------------------------------------------------------------------

    async def run(self, request: TuningRequest) -> Selection:
        """Run *request* to its selection, written as ``<run_id>/tuning/selection.json``.

        :raises SpecError: An unknown skill or method, a method without a K
            control, an input without the expression embedding, ``obs``
            columns outside the allowlist, or a model-less ``det`` arm.
        :raises PipelineError: A helper module failed.
        """
        began = time.monotonic()
        spec = self.runner.catalog.get(request.skill)
        if spec is None:
            raise SpecError(f"skill {request.skill!r} has no tuning.yaml; tunable skills: "
                            f"{', '.join(self.runner.catalog.names()) or 'none'}")
        methods = list(request.methods or [n for n, m in spec.methods.items() if m.k_control is not None])
        for name in methods:
            if spec.method(name).k_control is None:
                raise SpecError(f"method {name!r} of {spec.skill} has no k_control and cannot be tuned at a fixed K")
        arm = "user" if request.k is not None else request.arm
        if arm not in ARMS:
            raise SpecError(f"arm must be one of {ARMS}")
        if arm == "det" and self.model is None:
            raise SpecError("the det arm needs a model")
        if request.k is not None and request.k not in range(2, 1000):
            raise SpecError("k must be a positive number of domains")
        if request.tissue:
            check_leak({"tissue": request.tissue})
        input_path = Path(request.input)
        description = await self.describe_input(input_path)
        self.check_input(spec, description)
        sha = await asyncio.to_thread(self.runner.input_sha256, input_path)
        tuning_dir = self.runner.store.run_dir(request.run_id) / "tuning"
        ledger = Ledger(tuning_dir)
        context = dict(request.context)
        platform = str(context.get("data_type") or "")
        skill_text = self.skill_text(spec.skill)
        digest = code_digest(self.code_paths) if self.code_paths else ""
        ledger.append(
            "start",
            input=str(input_path), input_sha256=sha, input_obs_columns=description.get("obs_columns"),
            methods=methods, arm=arm, random_index=request.random_index,
            tissue_given=bool(request.tissue), tissue_withheld=request.tissue_withheld,
            frozen=self.settings.frozen(), panel_version=_panel_version(spec), tuning_sha256=spec.sha256,
            skill_md_sha256=skill_text.sha256, templates_sha256=template_sha256(), code_digest=digest,
            freeze_sha256=self.freeze_sha256, date=utc_now()[:10], context=context,
            **self.llm_settings.to_json(),
        )
        state = _RunState(spec=spec, request=request, arm=arm, ledger=ledger, sha=sha, methods=methods,
                          skill_text=skill_text, digest=digest, input_path=input_path, context=context)
        try:
            async with asyncio.timeout(self.settings.max_s):
                bundle = await self.prepare_evidence(
                    spec, methods, input_path, probe_base=request.probe_base or request.run_id,
                    context=context, k=request.k, ledger=ledger, platform=platform,
                )
                state.bundle = bundle
                for name in ("stability.json", "reference.json", "markers.json"):
                    source = bundle.directory / name
                    if source.is_file():
                        shutil.copyfile(source, tuning_dir / name)
                if request.k is None:
                    ledger.append("stability", **bundle.evidence.summary())
                await self._decide(state)
                if state.k is not None:
                    await self._tune_all(state)
        except TimeoutError:
            state.notes.append(f"stopped at the wall-clock limit of {self.settings.max_s:g} s")
        selection = self._select(state)
        selection.write(tuning_dir / "selection.json")
        self._write_summary(state, selection, tuning_dir, began)
        ledger.append("end", status=selection.status, wall_s=round(time.monotonic() - began, 1))
        return selection

    # ---- K ---------------------------------------------------------------------------------------

    async def _decide(self, state: "_RunState") -> None:
        bundle = state.bundle
        assert bundle is not None
        request = state.request
        if state.arm == "user":
            state.k, state.k_source = int(request.k), "user"  # type: ignore[arg-type]
        elif state.arm == "random":
            state.k, state.k_source = bundle.evidence.fallback_k, "fallback"
        else:
            inp = KDecisionInput(
                grid=tuple(self.settings.grid), skill=state.skill_text, data=bundle.data,
                tissue=request.tissue, evidence=bundle.evidence, markers=bundle.markers,
            )

            async def fetch(requested: list[int]) -> Mapping[str, Any]:
                return await self.requested_markers(bundle, state.spec, state.input_path, requested,
                                                    state.ledger.directory)

            try:
                outcome = await decide_k(self.model, inp, settings=self.llm_settings, ledger=state.ledger,
                                         fetch_markers=fetch, retries=self.settings.retries)
            except LeakError as exc:
                state.ledger.append("leak_refused", layer="k_decision", field=exc.field, match=exc.match)
                state.k, state.k_source = bundle.evidence.fallback_k, "fallback"
                state.k_failure = str(exc)
            else:
                state.requested = outcome.requested
                state.k_calls = outcome.calls
                state.llm_calls += len(outcome.calls)
                if outcome.decision is not None:
                    state.k, state.k_source = outcome.decision.chosen_k, "llm"
                    state.k_decision = outcome.decision
                else:
                    state.k, state.k_source = bundle.evidence.fallback_k, "fallback"
                    state.k_failure = outcome.failure
                    state.fallbacks += 1
        state.ledger.append(
            "k_decision",
            chosen_k=state.k, source=state.k_source,
            in_stable_peaks=state.k in bundle.evidence.stable_peaks if state.k is not None else None,
            requested_markers=state.requested,
            rationale=state.k_decision.rationale if state.k_decision else None,
            evidence=state.k_decision.evidence if state.k_decision else None,
            confidence=state.k_decision.confidence if state.k_decision else None,
            failure=state.k_failure, calls=state.k_calls,
        )
        if state.k is None:
            state.notes.append("no K could be chosen: the stability evidence defines no fallback K")

    # ---- tuning ------------------------------------------------------------------------------------

    async def _tune_all(self, state: "_RunState") -> None:
        await self._progress(f"tuning {len(state.methods)} methods at K={state.k}")
        kinds = {m: state.spec.method(m).k_control.kind for m in state.methods}  # type: ignore[union-attr]
        caps = budget_caps(kinds, groups=self.settings.groups, calibration_runs=self.settings.calibration_runs)
        state.caps = caps
        for method in state.methods:
            state.budgets[method] = _MethodBudget(method, caps[method], self.budget, self.session)
            state.items[method] = []
        await asyncio.gather(*(self._tune_method(state, method) for method in state.methods))

    async def _tune_method(self, state: "_RunState", method: str) -> None:
        spec = state.spec
        k = int(state.k)  # type: ignore[arg-type]
        method_spec = spec.method(method)
        control = method_spec.k_control
        assert control is not None
        plan = search_plan(spec, method)
        state.strategy[method] = plan.strategy
        fixed = {**state.context, **fixed_values(method_spec, k)}
        defaults = validate_params(spec, method, dict(control.pin))
        bundle = state.bundle
        assert bundle is not None
        taken: set[str] = set()
        baseline = bundle.default_trial(spec, method, k)
        default_point = {param.name: defaults[param.name] for param in plan.dimensions}
        if baseline is not None:
            item = self._from_probe(state, method, baseline, k)
            state.items[method].append(item)
            taken.add(self._identity(spec, method, fixed, {}))
        else:
            await self._evaluate(state, method, {}, source="baseline", stage="baseline", is_default=True)
            taken.add(self._identity(spec, method, fixed, {}))
        if plan.strategy == "grid":
            dimension = plan.dimensions[0]
            points = [{dimension.name: value} for value in grid_values(dimension)
                      if value != defaults[dimension.name]][: self.settings.groups]
            await asyncio.gather(*(
                self._evaluate(state, method, point, source="grid", stage="grid") for point in points
            ))
            state.ledger.append("stage", method=method, stage="grid",
                                planned=[{"params": p, "source": "grid"} for p in points])
        elif plan.strategy == "two_stage":
            await self._two_stages(state, method, plan, fixed, defaults, default_point, taken)
        choice = choose_method(state.items[method], k, method_spec,
                               ignore=(control.param, *control.pin, *state.context))
        state.choices[method] = choice

    async def _two_stages(self, state, method, plan, fixed, defaults, default_point, taken) -> None:
        spec = state.spec
        k = int(state.k)
        method_spec = spec.method(method)
        control = method_spec.k_control
        sweeps = sweep_points(plan.dimensions, defaults)[: self.settings.sweeps]
        for point in sweeps:
            taken.add(self._identity(spec, method, fixed, point))
        sweep_tasks = [
            asyncio.ensure_future(self._evaluate(state, method, point, source="sweep", stage="stage1"))
            for point in sweeps
        ]
        proposals, sources = await self._stage1_proposals(state, method, plan, fixed, defaults, sweeps, taken)
        state.ledger.append("stage", method=method, stage="stage1",
                            planned=[{"params": p, "source": "sweep"} for p in sweeps]
                            + [{"params": p, "source": s} for p, s in zip(proposals, sources)])
        proposal_tasks = [
            asyncio.ensure_future(self._evaluate(state, method, point, source=source, stage="stage1"))
            for point, source in zip(proposals, sources)
        ]
        await asyncio.gather(*sweep_tasks, *proposal_tasks)
        stage1 = [item for item in state.items[method] if item.stage == "stage1"]
        default_item = next((item for item in state.items[method] if item.is_default), None)
        skip, why = skip_stage2(default_item, stage1, k)
        state.stage2_skipped[method] = skip
        if skip:
            state.ledger.append("stage", method=method, stage="stage2", skipped=True, reason=why)
            return
        eligible_stage1 = [item for item in stage1 if eligible(item, k)]
        ignore = (control.param, *control.pin, *state.context)

        def closeness(item: Evaluated) -> tuple:
            count, distance = deviation(item.params, method_spec, ignore=ignore)
            return (item.score, -count, -distance, -item.seq)

        centre_item = max(eligible_stage1, key=closeness)
        centre = {**fixed, **_explicit(centre_item.params, fixed, control)}
        identity = lambda params: self._identity(spec, method, {}, params)  # noqa: E731
        taken_all = {self._identity(spec, method, fixed, _explicit(item.params, fixed, control))
                     for item in state.items[method]} | set(taken)
        default_dims = {param.name: defaults[param.name] for param in plan.dimensions}
        points = neighbourhood_points(spec, method, plan.dimensions, centre, default_dims, taken_all, key=identity)
        remaining = self.settings.groups - len([i for i in state.items[method] if not i.is_default])
        points = [_explicit(point, fixed, control) for point in points][: max(0, remaining)]
        state.ledger.append("stage", method=method, stage="stage2", skipped=False, reason=why,
                            centre=centre_item.trial, planned=[{"params": p, "source": "neighbourhood"} for p in points])
        await asyncio.gather(*(
            self._evaluate(state, method, point, source="neighbourhood", stage="stage2") for point in points
        ))

    async def _stage1_proposals(self, state, method, plan, fixed, defaults, sweeps, taken):
        """Three stage-1 settings from the model, topped up (or replaced) by random search."""
        spec = state.spec
        method_spec = spec.method(method)
        control = method_spec.k_control
        want = self.settings.proposals
        accepted: list[dict[str, Any]] = []
        sources: list[str] = []
        seen = set(taken)
        if state.arm == "det":
            bundle = state.bundle
            default_item = next((item for item in state.items[method] if item.is_default), None)
            values = member_values((default_item.extra.get("metrics") or {}) if default_item else {})
            inp = ProposeInput(
                method=method, k=int(state.k),
                method_summary=method_spec.summary(omit=(control.param, *control.pin)),
                fixed={**{n: v for n, v in fixed.items() if n not in state.context}},
                dimensions=tuple(p.name for p in plan.dimensions),
                k_control=(f"The number of domains is set directly by {control.param}."
                           if control.kind == "exact" else
                           f"{control.param} is adjusted automatically until the trial has K clusters; "
                           f"you may give a starting value for it."),
                default_result={
                    "params": default_item.params if default_item else {},
                    "n_labels": default_item.n_labels if default_item else None,
                    "fixed_k_score": default_item.score if default_item else None,
                    "se": default_item.se if default_item else None,
                    "pas": values["pas"][0], "silhouette": values["silhouette_pca"][0],
                },
                sweeps=tuple(sweeps),
                resolution_map=bundle.resolution_map(method) if control.kind == "calibrate" else None,
                skill=state.skill_text, data=bundle.data, tissue=state.request.tissue,
            )

            def accept(params: Any) -> tuple[dict[str, Any] | None, str]:
                if not isinstance(params, Mapping):
                    return None, "params is not an object"
                explicit = {name: value for name, value in params.items()}
                for name, value in fixed.items():
                    if name in explicit and explicit[name] != value:
                        return None, f"{name} is fixed at {value}"
                    explicit.pop(name, None)
                initial = None
                if control.kind == "calibrate" and control.param in explicit:
                    initial = explicit.pop(control.param)
                try:
                    validate_params(spec, method, {**fixed, **explicit, **(
                        {control.param: initial} if initial is not None else {})})
                except SpecError as exc:
                    return None, str(exc).split("\n", 1)[0]
                key = self._identity(spec, method, fixed, explicit)
                if key in seen:
                    return None, "repeats the default, a sweep or another proposal"
                seen.add(key)
                if initial is not None:
                    explicit["__initial__"] = initial
                return explicit, ""

            try:
                outcome = await propose(self.model, inp, settings=self.llm_settings, ledger=state.ledger,
                                        accept=accept, count=want, retries=self.settings.retries)
            except LeakError as exc:
                state.ledger.append("leak_refused", layer=f"propose:{method}", field=exc.field, match=exc.match)
            else:
                state.llm_calls += len(outcome.calls)
                if outcome.failure:
                    state.fallbacks += 1
                for params, _ in outcome.accepted[:want]:
                    accepted.append(params)
                    sources.append("llm")
                if outcome.dropped:
                    state.ledger.append("stage", method=method, stage="stage1_dropped",
                                        dropped=[{"params": p, "reason": r} for p, r in outcome.dropped])
        missing = want - len(accepted)
        if missing > 0:
            seed = stage1_seed(state.request.run_id, method, state.request.random_index)
            drawn = random_configs(spec, method, plan.dimensions, missing, seed, fixed=fixed, taken=seen,
                                   key=lambda params: self._identity(spec, method, {}, params))
            for point in drawn:
                seen.add(self._identity(spec, method, fixed, point))
                accepted.append(point)
                sources.append("random_fallback" if state.arm == "det" else "random")
        return accepted, sources

    def _identity(self, spec: TuningSpec, method: str, fixed: Mapping[str, Any], point: Mapping[str, Any]) -> str:
        """The key of a parameter set, without a calibrated method's resolution."""
        control = spec.method(method).k_control
        params = {**fixed, **{n: v for n, v in point.items() if n != "__initial__"}}
        if control is not None and control.kind == "calibrate":
            params.pop(control.param, None)
            try:
                values = validate_params(spec, method, params)
            except SpecError:
                return config_key(params)
            values.pop(control.param, None)
            return config_key(values)
        return full_key(spec, method, params) or config_key(params)

    def _from_probe(self, state: "_RunState", method: str, trial: ProbeTrial, k: int) -> Evaluated:
        scored = score_trial(trial.metrics or {}, state.bundle.references.get(k)) if trial.n_labels == k else None
        item = Evaluated(
            method=method, run_id=trial.run_id, trial=trial.trial, seq=self._next_seq(),
            params=dict(trial.params), status=trial.status, n_labels=trial.n_labels,
            score=scored.score if scored else None, se=scored.se if scored else None,
            source="baseline", stage="baseline", is_default=True,
            extra={"metrics": trial.metrics, "labels": trial.labels, "h5ad": trial.h5ad,
                   "requested_k": trial.requested_k, "from_probe": True},
        )
        state.ledger.append("trial", **_trial_event(item, new_run=False))
        fingerprint = labels_fingerprint(Path(trial.labels)) if trial.status == "ok" else None
        if fingerprint:
            self._fingerprints.setdefault((method, fingerprint), trial.trial)
        return item

    async def _evaluate(self, state: "_RunState", method: str, point: Mapping[str, Any], *,
                        source: str, stage: str, is_default: bool = False) -> Evaluated:
        """Run one parameter set (calibrating it for a calibrated method) and record it."""
        spec = state.spec
        k = int(state.k)  # type: ignore[arg-type]
        method_spec = spec.method(method)
        control = method_spec.k_control
        fixed = {**state.context, **fixed_values(method_spec, k)}
        explicit = {n: v for n, v in point.items() if n != "__initial__"}
        seq = self._next_seq()
        budget = state.budgets[method]
        if control.kind == "exact":
            if not budget.take():
                item = self._skipped(method, seq, {**fixed, **explicit}, source, stage, is_default)
                state.items[method].append(item)
                return item
            result = await self._run_trial(state, method, {**fixed, **explicit})
            item = self._evaluated(state, method, result, seq, source, stage, is_default, k)
            state.items[method].append(item)
            state.ledger.append("trial", **_trial_event(item, new_run=True))
            return item
        param = method_spec.params[control.param]
        bundle = state.bundle
        mapping = bundle.resolution_map(method)
        if point.get("__initial__") is not None:
            initial = float(point["__initial__"])
        else:
            initial = initial_value(mapping, k, low=float(param.low), high=float(param.high))
        history = [(r, n) for r, n in mapping.items()] if not explicit else []
        runs: list[TrialResult] = []

        async def run(value: float) -> tuple[int | None, Any]:
            if not budget.take():
                return None, "budget"
            result = await self._run_trial(state, method, {**fixed, **explicit, control.param: value})
            runs.append(result)
            calibration_item = self._evaluated(state, method, result, self._next_seq(),
                                               "calibration" if len(runs) > 1 else source, stage, False, k)
            state.ledger.append("trial", **_trial_event(calibration_item, new_run=True, calibration_of=seq))
            return _n_labels(result), result

        outcome = await calibrate(k, run, initial=initial, low=float(param.low), high=float(param.high),
                                  history=history, extra=self.settings.calibration_runs)
        if not runs:
            item = self._skipped(method, seq, {**fixed, **explicit}, source, stage, is_default)
        elif outcome.status == "ok":
            item = self._evaluated(state, method, outcome.hit[2], seq, source, stage, is_default, k)
        else:
            closest = outcome.closest[2] if outcome.closest else runs[-1]
            item = self._evaluated(state, method, closest, seq, source, stage, is_default, k)
            if item.status == "ok":
                item.status = outcome.status if outcome.status in ("off_k", "unreachable_k") else "failed"
            item.extra["calibration"] = outcome.status
        item.extra["runs"] = len(runs)
        state.items[method].append(item)
        return item

    def _skipped(self, method, seq, params, source, stage, is_default) -> Evaluated:
        return Evaluated(method=method, run_id="", trial="", seq=seq, params=dict(params),
                         status="budget_exhausted", source=source, stage=stage, is_default=is_default)

    async def _run_trial(self, state: "_RunState", method: str, params: Mapping[str, Any]) -> TrialResult:
        # Prepared on the event loop, not in a thread: trials then take their
        # numbers in the order they were planned. The input's hash is cached.
        prepared = self.runner.prepare(
            skill=state.spec.skill, method=method, input=state.input_path,
            params=dict(params), run_id=state.request.run_id,
        )
        result = await self.runner.run(prepared)
        state.results.append(result)
        return result

    def _evaluated(self, state, method, result: TrialResult, seq, source, stage, is_default, k) -> Evaluated:
        n_labels = _n_labels(result)
        score = se = None
        if result.status == "ok" and n_labels == k:
            scored = score_trial(result.metrics or {}, state.bundle.references.get(k))
            score, se = scored.score, scored.se
        item = Evaluated(
            method=method, run_id=result.run_id, trial=result.trial, seq=seq, params=dict(result.params),
            status=result.status, n_labels=n_labels, score=score, se=se, source=source, stage=stage,
            is_default=is_default,
            extra={"metrics": result.metrics, "labels": str(Path(result.output_dir) / "labels.csv.gz"),
                   "h5ad": result.h5ad},
        )
        if result.status == "ok":
            fingerprint = labels_fingerprint(Path(result.output_dir) / "labels.csv.gz")
            if fingerprint:
                first = self._fingerprints.setdefault((method, fingerprint), result.trial)
                if first != result.trial:
                    item.duplicate_of = first
        return item

    # ---- the answer ------------------------------------------------------------------------------------

    def _select(self, state: "_RunState") -> Selection:
        spec = state.spec
        bundle = state.bundle
        k = state.k
        methods: dict[str, dict[str, Any]] = {}
        for method in state.methods:
            choice = state.choices.get(method)
            items = state.items.get(method, [])
            if choice is None and items and k is not None:
                control = spec.method(method).k_control
                choice = choose_method(items, k, spec.method(method),
                                       ignore=(control.param, *control.pin, *state.context))
                state.choices[method] = choice
            if choice is None or choice.chosen is None:
                methods[method] = {"status": "failed", "strategy": state.strategy.get(method),
                                   "evaluated": len(items), "new_runs": state.budgets[method].used
                                   if method in state.budgets else 0}
                continue
            chosen = choice.chosen
            h5ad = chosen.extra.get("h5ad")
            methods[method] = {
                "status": choice.status,
                "run_id": chosen.run_id,
                "trial": chosen.trial,
                "params": chosen.params,
                "fixed_k_score": _round(chosen.score),
                "se": _round(chosen.se),
                "n_labels": chosen.n_labels,
                "labels": chosen.extra.get("labels"),
                "h5ad": h5ad if h5ad and Path(h5ad).is_file() else None,
                "evaluated": len([i for i in items if i.status != "budget_exhausted"]),
                "new_runs": state.budgets[method].used if method in state.budgets else 0,
                "strategy": state.strategy.get(method),
                "stage2_skipped": state.stage2_skipped.get(method),
                "source": chosen.source,
                "within_se": choice.within_se,
            }
        final_choice = choose_final(state.choices, k) if k is not None else None
        final = None
        if final_choice is not None and final_choice.chosen is not None:
            final = {"method": final_choice.method, "run_id": final_choice.chosen.run_id,
                     "trial": final_choice.chosen.trial}
        ok_methods = [m for m, entry in methods.items() if entry["status"] != "failed"]
        if k is None or not ok_methods:
            status = "failed"
        elif final is not None and len(ok_methods) == len(methods) and not state.notes:
            status = "ok"
        else:
            status = "partial"
        state.ledger.append(
            "select",
            k=k,
            methods={m: {"status": c.status, "chosen": c.chosen.trial if c.chosen else None,
                         "within_se": c.within_se, "ranking": c.ranking}
                     for m, c in state.choices.items()},
            final=final, status=status, notes=state.notes,
        )
        gpu_s = sum(r.wall_s for r in state.results if r.lease_gpu is not None)
        cpu_s = sum(r.wall_s * spec.method(r.method).resources.cpus for r in state.results)
        evidence = bundle.evidence if bundle else None
        return Selection(
            status=status,
            arm=state.arm,
            skill=spec.skill,
            input=str(state.input_path),
            input_sha256=state.sha,
            panel_version=_panel_version(spec) or "",
            k={
                "chosen": k,
                "grid": [self.settings.grid[0], self.settings.grid[-1]],
                "stable_peaks": evidence.stable_peaks if evidence else [],
                "requested_markers": state.requested,
                "in_stable_peaks": (k in evidence.stable_peaks) if (evidence and k is not None) else None,
                "source": state.k_source or ("user" if state.arm == "user" else "fallback"),
                "fallback_k": evidence.fallback_k if evidence else None,
                "stability": "stability.json",
                "decision": state.k_calls[-1] if state.k_calls else None,
                "failure": state.k_failure or None,
            },
            methods=methods,
            final=final,
            budget={
                "caps": state.caps,
                "used": {m: b.used for m, b in state.budgets.items()},
                "gpu_s": round(gpu_s, 1),
                "cpu_s": round(cpu_s, 1),
            },
            provenance={
                **self.llm_settings.to_json(),
                "date": utc_now()[:10],
                "templates_sha256": template_sha256(),
                "skill_md_sha256": state.skill_text.sha256,
                "tuning_sha256": spec.sha256,
                "freeze_sha256": self.freeze_sha256,
                "code_digest": state.digest,
                "seeds": {"subsample": list(self.settings.subsample_seeds), **self.settings.frozen()["seeds"],
                          "random_index": state.request.random_index},
                "tissue_given": bool(state.request.tissue),
                "tissue_withheld": state.request.tissue_withheld,
                "probe_reused": bundle.reused if bundle else None,
                "llm_calls": state.llm_calls,
                "fallbacks": state.fallbacks,
                "notes": state.notes,
            },
        )

    def _write_summary(self, state: "_RunState", selection: Selection, tuning_dir: Path, began: float) -> None:
        spec = state.spec
        bundle = state.bundle
        per_method = {}
        for method in state.methods:
            method_spec = spec.method(method)
            control = method_spec.k_control
            items = state.items.get(method, [])
            choice = state.choices.get(method)
            default = next((i for i in items if i.is_default), None)
            final = choice.chosen if choice else None
            per_method[method] = {
                "defaults": validate_params(spec, method, dict(control.pin)) if control else {},
                "default_fixed_k_score": _round(default.score) if default else None,
                "evaluated": [
                    {"trial": i.trial, "params": i.params, "source": i.source, "stage": i.stage,
                     "status": i.status, "n_labels": i.n_labels, "fixed_k_score": _round(i.score),
                     "se": _round(i.se), "duplicate_of": i.duplicate_of}
                    for i in items
                ],
                "final_params": final.params if final else None,
                "deviation": _deviation_vector(final.params, method_spec) if final else None,
                "stage2_skipped": state.stage2_skipped.get(method),
                "fallback_default": bool(choice and choice.status == "fallback_default"),
                "strategy": state.strategy.get(method),
            }
        record = {
            "schema": TUNING_RECORD_SCHEMA,
            "data": {
                "platform": bundle.data.platform if bundle else None,
                "species": bundle.data.species if bundle else None,
                "tissue": state.request.tissue,
                "n_obs": bundle.data.n_obs if bundle else None,
                "n_vars": bundle.data.n_vars if bundle else None,
                "median_counts": bundle.data.median_counts if bundle else None,
                "median_genes": bundle.data.median_genes if bundle else None,
                "preprocessing": dict(bundle.data.preprocessing) if bundle else None,
                "input_sha256": state.sha,
            },
            "k": {
                "chosen": state.k, "source": state.k_source,
                "in_stable_peaks": selection.k.get("in_stable_peaks"),
                "fallback_k": selection.k.get("fallback_k"),
                "curves": {str(k): {"values": row.values, "peak_frequency": row.peak_frequency}
                           for k, row in (bundle.evidence.rows.items() if bundle else [])},
            },
            "methods": per_method,
            "provenance": {
                "panel_version": selection.panel_version, "tuning_sha256": spec.sha256,
                "skill_md_sha256": state.skill_text.sha256, "code_digest": state.digest,
                **self.llm_settings.to_json(), "date": utc_now()[:10], "arm": state.arm,
            },
        }
        write_json(tuning_dir / "tuning.json", {
            "status": selection.status,
            "wall_s": round(time.monotonic() - began, 1),
            "llm_calls": state.llm_calls,
            "fallbacks": state.fallbacks,
            "tuning_record": record,
        })


@dataclass
class _RunState:
    spec: TuningSpec
    request: TuningRequest
    arm: str
    ledger: Ledger
    sha: str
    methods: list[str]
    skill_text: SkillText
    digest: str
    input_path: Path
    context: dict[str, Any]
    bundle: EvidenceBundle | None = None
    k: int | None = None
    k_source: str = ""
    k_decision: Any = None
    k_failure: str = ""
    k_calls: list[str] = field(default_factory=list)
    requested: list[int] = field(default_factory=list)
    llm_calls: int = 0
    fallbacks: int = 0
    caps: dict[str, int] = field(default_factory=dict)
    budgets: dict[str, _MethodBudget] = field(default_factory=dict)
    items: dict[str, list[Evaluated]] = field(default_factory=dict)
    choices: dict[str, MethodChoice] = field(default_factory=dict)
    strategy: dict[str, str] = field(default_factory=dict)
    stage2_skipped: dict[str, bool] = field(default_factory=dict)
    results: list[TrialResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _explicit(params: Mapping[str, Any], fixed: Mapping[str, Any], control) -> dict[str, Any]:
    """*params* without the fixed values and without a calibrated method's resolution."""
    out = {n: v for n, v in params.items() if n not in fixed}
    if control is not None and control.kind == "calibrate":
        out.pop(control.param, None)
    return out


def _shown_params(spec: TuningSpec, trial: ProbeTrial) -> dict[str, Any]:
    return {n: v for n, v in trial.params.items() if n not in spec.context}


def _deviation_vector(params: Mapping[str, Any], method_spec) -> dict[str, Any]:
    from omicsclaw.ensemble.tuning.search import to_unit

    out: dict[str, Any] = {}
    for name, value in params.items():
        param = method_spec.params.get(name)
        if param is None or value == param.default:
            continue
        if param.type in ("float", "int") and param.default is not None:
            out[name] = round(to_unit(param, value) - to_unit(param, param.default), 6)
        else:
            out[name] = {"from": param.default, "to": value}
    return out


def _trial_event(item: Evaluated, *, new_run: bool, calibration_of: int | None = None) -> dict[str, Any]:
    metrics = item.extra.get("metrics") or {}
    return {
        "run_id": item.run_id, "method": item.method, "trial": item.trial, "params": item.params,
        "requested_k": item.params.get("n_domains") if "n_domains" in item.params else item.extra.get("requested_k"),
        "n_labels": item.n_labels, "score": metrics.get("score") if metrics else None,
        "fixed_k_score": item.score, "se": item.se, "status": item.status, "source": item.source,
        "stage": item.stage, "duplicate_of": item.duplicate_of, "new_run": new_run,
        "calibration_of": calibration_of, "seq": item.seq,
    }


def _panel_version(spec: TuningSpec) -> str | None:
    from omicsclaw.ensemble.metrics import get_panel

    panel = get_panel(spec.analysis)
    return panel.version if panel else None
