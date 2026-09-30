"""The tuning tools: ``optimize_params``, ``inspect_trials`` and ``select_result``.

:class:`TuningToolkit` holds what the three share with ``run_skill`` — the
runner, the skill index, the session run budget — and builds each tool. The
model used by ``optimize_params`` is injected; this module never imports a
provider.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from omicsclaw.ensemble.runner import EnsembleRunner
from omicsclaw.ensemble.space import SpecError
from omicsclaw.ensemble.store import RUN_ID_PATTERN, new_run_id, read_json
from omicsclaw.ensemble.tool import reference_path
from omicsclaw.ensemble.tuning.budget import RunBudget
from omicsclaw.ensemble.tuning.ledger import Selection, SelectionError, utc_now
from omicsclaw.ensemble.tuning.llm import LLMSettings
from omicsclaw.ensemble.tuning.pipeline import PipelineError, TuningPipeline, TuningRequest, TuningSettings
from omicsclaw.ensemble.tuning.prompts import LeakError, SkillText, check_leak
from omicsclaw.ensemble.tuning.scoring import KReference, member_values, score_trial
from omicsclaw.tools._workspace import PathRefused, Workspace
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import context_value, pause_tool_timeout
from omicsclaw.tools.function_tool import FunctionTool, ToolArgumentError

__all__ = [
    "INSPECT_TRIALS_POLICY",
    "INSPECT_TRIALS_SCHEMA",
    "INSPECT_TRIALS_TOOL_NAME",
    "OPTIMIZE_PARAMS_POLICY",
    "OPTIMIZE_PARAMS_SCHEMA",
    "OPTIMIZE_PARAMS_TOOL_NAME",
    "SELECT_RESULT_POLICY",
    "SELECT_RESULT_SCHEMA",
    "SELECT_RESULT_TOOL_NAME",
    "TOOL_MODES",
    "TuningToolkit",
    "skill_text_loader",
]

OPTIMIZE_PARAMS_TOOL_NAME = "optimize_params"
INSPECT_TRIALS_TOOL_NAME = "inspect_trials"
SELECT_RESULT_TOOL_NAME = "select_result"
TOOL_MODES = ("all", "free", "tuning")
PARAMETERS_REFERENCE = Path("references") / "parameters.md"

OPTIMIZE_PARAMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "skill": {"type": "string"},
        "input": {"type": "string", "description": "workspace path of the preprocessed .h5ad (needs obsm X_pca)"},
        "methods": {"type": "array", "items": {"type": "string"}},
        "tissue": {
            "type": "string",
            "description": "tissue type, for example its full anatomical name; never a number of regions or layers",
        },
        "k": {"type": "integer", "description": "a number of domains the user asked for; skips choosing K"},
        "run_id": {"type": "string"},
        "images": {"type": "boolean"},
    },
    "required": ["skill", "input"],
    "additionalProperties": False,
}

OPTIMIZE_PARAMS_POLICY = ToolPolicy(
    risk_level=RiskLevel.MEDIUM,
    approval_mode=ApprovalMode.AUTO,
    read_only=False,
    concurrency_safe=False,
    writes_workspace=True,
    touches_network=True,
    allowed_in_background=False,
    tags=frozenset({"skills", "ensemble", "tuning"}),
)

_TRIAL_REF = {
    "type": "object",
    "properties": {"method": {"type": "string"}, "trial": {"type": "string"}},
    "required": ["method", "trial"],
    "additionalProperties": False,
}

INSPECT_TRIALS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string"},
        "trials": {"type": "array", "items": _TRIAL_REF},
        "markers_for": _TRIAL_REF,
        "top_n": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["run_id", "trials"],
    "additionalProperties": False,
}

INSPECT_TRIALS_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=True,
    concurrency_safe=True,
    writes_workspace=False,
    touches_network=False,
    allowed_in_background=False,
    tags=frozenset({"skills", "ensemble", "tuning"}),
)

SELECT_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string"},
        "k": {"type": "integer"},
        "final": _TRIAL_REF,
        "per_method": {"type": "object", "additionalProperties": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": ["run_id", "k", "final", "per_method", "rationale"],
    "additionalProperties": False,
}

SELECT_RESULT_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=False,
    concurrency_safe=False,
    writes_workspace=True,
    touches_network=False,
    allowed_in_background=False,
    tags=frozenset({"skills", "ensemble", "tuning"}),
)


def skill_text_loader(skills: Any):
    """A function returning a skill's ``SKILL.md`` body and ``references/parameters.md`` from *skills*.

    :raises SpecError: (from the returned function) the skill is not indexed.
    """

    def load(name: str) -> SkillText:
        skill = skills.get(name)
        if skill is None:
            raise SpecError(f"skill {name!r} is not in the skill index")
        body = skills.get_full_content(name)
        reference = Path(skill.directory) / PARAMETERS_REFERENCE
        parameters = reference.read_text(encoding="utf-8") if reference.is_file() else ""
        return SkillText(body, parameters)

    return load


@dataclass
class TuningToolkit:
    """What the tuning tools share.

    :param model: The model ``optimize_params`` asks; ``None`` leaves that tool unusable.
    :param tissue_enabled: ``False`` drops any ``tissue`` argument and records that it was withheld.
    :param images_enabled: Whether the deployment allows partition images (not supported; always ``False``).
    :param obs_allowlist: When set, inputs whose ``obs`` columns are not all in it are refused.
    """

    runner: EnsembleRunner
    workspace: Workspace
    skills: Any
    model: Any = None
    llm_settings: LLMSettings = field(default_factory=lambda: LLMSettings(model="", provider=""))
    settings: TuningSettings = field(default_factory=TuningSettings)
    budget: RunBudget | None = None
    tissue_enabled: bool = True
    images_enabled: bool = False
    obs_allowlist: tuple[str, ...] | None = None
    _described: dict[tuple[str, int, int], dict[str, Any]] = field(default_factory=dict)

    # ---- shared pieces ------------------------------------------------------------------

    def _resolve(self, raw: str, what: str = "input") -> Path:
        try:
            path = self.workspace.resolve(raw)
        except PathRefused as exc:
            raise ToolArgumentError(f"{what}: {exc}") from None
        if not path.is_file():
            raise ToolArgumentError(f"{what}: {raw!r} is not a file in the workspace")
        return path

    async def describe(self, path: Path) -> dict[str, Any]:
        """The input's description from the execution environment, cached per (path, size, mtime)."""
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        cached = self._described.get(key)
        if cached is None:
            cached = await self._pipeline().describe_input(path)
            self._described[key] = cached
        return cached

    async def input_check(self, path: Path, skill: str) -> None:
        """Refuse an input without the skill's expression embedding or with ``obs`` columns outside the allowlist.

        :raises SpecError: Either check fails.
        """
        spec = self.runner.catalog.get(skill)
        if spec is None:
            return
        try:
            description = await self.describe(path)
        except PipelineError as exc:
            raise SpecError(f"cannot read the input: {exc}") from None
        self._pipeline().check_input(spec, description)

    def _pipeline(self, *, session: str = "") -> TuningPipeline:
        return TuningPipeline(
            self.runner,
            model=self.model,
            llm_settings=self.llm_settings,
            skill_text=skill_text_loader(self.skills),
            settings=self.settings,
            budget=self.budget,
            session=session,
            obs_allowlist=self.obs_allowlist,
        )

    def tools(self, mode: str, *, run_skill: FunctionTool | None = None) -> tuple[FunctionTool, ...]:
        """The tools of *mode* in mounting order.

        ``all``: ``run_skill``, ``inspect_trials``, ``select_result``,
        ``optimize_params``; ``free``: the first three; ``tuning``: only
        ``optimize_params``.

        :raises ValueError: An unknown mode, or a mode needing ``run_skill`` without it.
        """
        if mode not in TOOL_MODES:
            raise ValueError(f"ensemble tools mode must be one of {TOOL_MODES}, got {mode!r}")
        if mode == "tuning":
            return (self.optimize_params_tool(),)
        if run_skill is None:
            raise ValueError(f"mode {mode!r} mounts run_skill")
        tools = (run_skill, self.inspect_trials_tool(), self.select_result_tool())
        if mode == "all":
            tools = (*tools, self.optimize_params_tool())
        return tools

    # ---- optimize_params -------------------------------------------------------------------

    def optimize_params_description(self) -> str:
        methods = []
        for spec in self.runner.catalog.specs():
            tunable = [name for name, method in spec.methods.items() if method.k_control is not None]
            if tunable:
                methods.append(f"- {spec.skill}: {', '.join(tunable)}")
        hours = self.settings.max_s / 3600
        return "\n".join([
            "Tune a skill's methods on one preprocessed input and pick a result, in one call. It first "
            "probes every method over a grid of domain counts K "
            f"({self.settings.grid[0]}-{self.settings.grid[-1]}) and computes stability curves and marker "
            "genes; a model then chooses K from that evidence and the skill's documentation; each method "
            "is then tuned at that K within a fixed budget of new runs, and the simplest setting within "
            "one standard error of the best is kept. Returns K with its reasons, each method's chosen "
            "trial and score, the single best trial, and the paths of selection.json and the ledger.",
            "",
            "Tunable skills and methods:",
            *methods,
            "",
            "Use it when the user asks to tune or optimise parameters, or when the skill's documentation "
            "calls for it. Give k only when the user named a number of domains. tissue describes the "
            "tissue by name; it must never state a number of regions or layers.",
            "Scores (fixed_k_score) are comparable only between trials with the same number of clusters.",
            f"One call runs many trials and can take hours (at most {self.settings.max_s:g} s, about "
            f"{hours:.1f} h).",
        ])

    def optimize_params_tool(self) -> FunctionTool:
        toolkit = self

        async def run(
            skill: str,
            input: str,
            methods: Sequence[str] | None = None,
            tissue: str | None = None,
            k: int | None = None,
            run_id: str | None = None,
            images: bool | None = None,
        ) -> str:
            path = toolkit._resolve(input)
            if toolkit.model is None and k is None:
                raise ToolArgumentError("no model is configured for choosing K; give k")
            notes: list[str] = []
            withheld = False
            if tissue and not toolkit.tissue_enabled:
                tissue, withheld = None, True
                notes.append("tissue was not used: this deployment withholds it")
            if tissue:
                try:
                    check_leak({"tissue": tissue})
                except LeakError as exc:
                    raise ToolArgumentError(
                        f"tissue must name the tissue without stating a number of regions ({exc.match!r})"
                    ) from None
            if images and not toolkit.images_enabled:
                notes.append("images were not used: this deployment does not send images")
            if run_id and not RUN_ID_PATTERN.fullmatch(run_id):
                raise ToolArgumentError(f"run_id {run_id!r} must match {RUN_ID_PATTERN.pattern}")
            session = str(context_value("session_id", ""))
            pipeline = toolkit._pipeline(session=session)
            request = TuningRequest(
                skill=skill, input=path, run_id=run_id or new_run_id(),
                methods=tuple(methods) if methods else None, tissue=tissue, k=k,
                arm="det" if toolkit.model is not None else "random", tissue_withheld=withheld,
            )
            began = time.monotonic()
            with pause_tool_timeout():
                try:
                    selection = await pipeline.run(request)
                except (SpecError, LeakError) as exc:
                    raise ToolArgumentError(str(exc)) from None
            tuning = toolkit.runner.store.run_dir(request.run_id) / "tuning"
            return json.dumps({
                "status": selection.status,
                "chosen_k": {
                    "k": selection.k.get("chosen"), "source": selection.k.get("source"),
                    "in_stable_peaks": selection.k.get("in_stable_peaks"),
                    "stable_peaks": selection.k.get("stable_peaks"),
                    "rationale": _rationale(tuning),
                },
                "methods": {
                    name: {key: entry.get(key) for key in (
                        "status", "trial", "params", "fixed_k_score", "se", "n_labels", "evaluated",
                        "new_runs", "strategy", "stage2_skipped")}
                    for name, entry in selection.methods.items()
                },
                "final": selection.final,
                "run_id": request.run_id,
                "selection": str(tuning / "selection.json"),
                "ledger": str(tuning / "ledger.jsonl"),
                "llm_calls": selection.provenance.get("llm_calls"),
                "fallbacks": selection.provenance.get("fallbacks"),
                "wall_s": round(time.monotonic() - began, 1),
                "notes": [*notes, *selection.provenance.get("notes", [])],
            }, ensure_ascii=False)

        return FunctionTool(
            OPTIMIZE_PARAMS_TOOL_NAME,
            self.optimize_params_description(),
            run,
            parameters=OPTIMIZE_PARAMS_SCHEMA,
            policy=OPTIMIZE_PARAMS_POLICY,
        )

    # ---- inspect_trials ------------------------------------------------------------------------

    def _trial_dir(self, run_id: str, method: str, trial: str) -> Path:
        run, _, name = trial.rpartition("/") if "/" in trial else (run_id, "", trial)
        if not RUN_ID_PATTERN.fullmatch(run) or not name.startswith("t") or not name[1:].isdigit():
            raise ToolArgumentError(f"trial {trial!r} must be tNNNN or <run_id>/tNNNN")
        directory = self.runner.store.method_dir(run, method) / name
        if not (directory / "trial.json").is_file():
            raise ToolArgumentError(f"there is no trial {trial!r} of {method} in run {run!r}")
        return directory

    def inspect_trials_tool(self) -> FunctionTool:
        toolkit = self

        async def run(
            run_id: str,
            trials: Sequence[Mapping[str, str]],
            markers_for: Mapping[str, str] | None = None,
            top_n: int | None = None,
        ) -> str:
            if not trials:
                raise ToolArgumentError("trials must name at least one trial")
            run_record = toolkit.runner.store.existing_run(run_id)
            if run_record is None:
                raise ToolArgumentError(f"there is no run {run_id!r}")
            reference_file = reference_path(toolkit.runner, run_id)
            reference = read_json(reference_file) if reference_file else None
            entries = []
            inputs = []
            for ref in trials:
                directory = toolkit._trial_dir(run_id, ref["method"], ref["trial"])
                record = read_json(directory / "trial.json") or {}
                metrics = read_json(directory / "metrics.json")
                key = f"{ref['method']}/{ref['trial']}"
                entry: dict[str, Any] = {"method": ref["method"], "trial": ref["trial"], "status": record.get("status"),
                                         "params": record.get("params")}
                if metrics:
                    values = member_values(metrics)
                    entry["n_labels"] = metrics.get("n_labels")
                    entry["pas"] = values["pas"][0]
                    entry["silhouette"] = values["silhouette_pca"][0]
                    per_k = (reference or {}).get("per_k", {}).get(str(metrics.get("n_labels")))
                    scored = score_trial(metrics, KReference.from_json(per_k)) if per_k else None
                    entry["fixed_k_score"] = scored.score if scored else None
                    entry["fixed_k_se"] = scored.se if scored else None
                    if (directory / "labels.csv.gz").is_file():
                        inputs.append({"key": key, "labels": str(directory / "labels.csv.gz")})
                entries.append(entry)
            spec: dict[str, Any] = {"input": run_record.get("input"), "trials": inputs, "top_n": min(10, top_n or 5)}
            if markers_for:
                directory = toolkit._trial_dir(run_id, markers_for["method"], markers_for["trial"])
                key = f"{markers_for['method']}/{markers_for['trial']}"
                if key not in {item["key"] for item in inputs}:
                    inputs.append({"key": key, "labels": str(directory / "labels.csv.gz")})
                spec["markers_for"] = key
            computed: dict[str, Any] = {}
            if inputs:
                work = toolkit.runner.store.run_dir(run_id) / "tuning" / "inspect"
                work.mkdir(parents=True, exist_ok=True)
                spec_path = work / f"inspect-{time.time_ns()}.json"
                spec_path.write_text(json.dumps(spec), encoding="utf-8")
                with pause_tool_timeout():
                    try:
                        computed = await toolkit._pipeline()._module(
                            "omicsclaw.ensemble.tuning.inspect", ["--spec", str(spec_path)], cwd=work, marker="INSPECT"
                        )
                    except PipelineError as exc:
                        computed = {"error": str(exc)[-2000:]}
                    finally:
                        spec_path.unlink(missing_ok=True)
            return json.dumps({"trials": entries, "ami": computed.get("ami"), "markers": computed.get("markers"),
                               "error": computed.get("error"),
                               "note": "fixed_k_score is comparable only between trials with the same n_labels"},
                              ensure_ascii=False)

        return FunctionTool(
            INSPECT_TRIALS_TOOL_NAME,
            "Compare trials of one run: each trial's number of clusters, PAS and silhouette, its fixed_k_score "
            "when the run has a fixed-K reference (comparable only between trials with the same number of "
            "clusters), the pairwise adjusted mutual information between the trials, and optionally the top "
            "marker genes per domain of one trial. A trial is tNNNN of the run, or <run_id>/tNNNN of another "
            "run on the same input.",
            run,
            parameters=INSPECT_TRIALS_SCHEMA,
            policy=INSPECT_TRIALS_POLICY,
        )

    # ---- select_result ---------------------------------------------------------------------------

    def select_result_tool(self) -> FunctionTool:
        toolkit = self

        async def run(
            run_id: str,
            k: int,
            final: Mapping[str, str],
            per_method: Mapping[str, str],
            rationale: str,
        ) -> str:
            run_record = toolkit.runner.store.existing_run(run_id)
            if run_record is None:
                raise ToolArgumentError(f"there is no run {run_id!r}")
            if not per_method:
                raise ToolArgumentError("per_method must name at least one method")
            reference_file = reference_path(toolkit.runner, run_id)
            reference = read_json(reference_file) if reference_file else None
            chosen = dict(per_method)
            if final["method"] in chosen and chosen[final["method"]] != final["trial"]:
                raise ToolArgumentError("final must be the trial chosen for its method in per_method")
            chosen.setdefault(final["method"], final["trial"])
            methods: dict[str, dict[str, Any]] = {}
            for method, trial in chosen.items():
                directory = toolkit._trial_dir(run_id, method, trial)
                record = read_json(directory / "trial.json") or {}
                metrics = read_json(directory / "metrics.json") or {}
                bound = toolkit.runner.store.existing_run(record.get("run_id", run_id)) or {}
                if bound.get("input_sha256") != run_record.get("input_sha256"):
                    raise ToolArgumentError(f"{method} {trial} was run on another input")
                if record.get("status") != "ok":
                    raise ToolArgumentError(f"{method} {trial} did not end ok ({record.get('status')})")
                if metrics.get("n_labels") != k:
                    raise ToolArgumentError(f"{method} {trial} has {metrics.get('n_labels')} clusters, not {k}")
                per_k = (reference or {}).get("per_k", {}).get(str(k))
                scored = score_trial(metrics, KReference.from_json(per_k)) if per_k else None
                methods[method] = {
                    "status": "ok", "run_id": record.get("run_id", run_id), "trial": directory.name,
                    "params": record.get("params"), "n_labels": k,
                    "fixed_k_score": scored.score if scored else None, "se": scored.se if scored else None,
                    "labels": str(directory / "labels.csv.gz"), "h5ad": record.get("h5ad"),
                }
            final_entry = methods[final["method"]]
            selection = Selection(
                status="ok", arm="free", skill=run_record.get("skill", ""), input=run_record.get("input", ""),
                input_sha256=run_record.get("input_sha256", ""), panel_version=run_record.get("panel_version") or "",
                k={"chosen": k, "source": "agent", "rationale": rationale},
                methods=methods,
                final={"method": final["method"], "run_id": final_entry["run_id"], "trial": final_entry["trial"]},
                provenance={"date": utc_now()[:10], "session": str(context_value("session_id", ""))},
            )
            path = toolkit.runner.store.run_dir(run_id) / "tuning" / "selection.json"
            try:
                selection.write(path)
            except SelectionError as exc:
                raise ToolArgumentError(str(exc)) from None
            return json.dumps({"selection": str(path), "k": k, "final": selection.final,
                               "methods": {m: e["trial"] for m, e in methods.items()}})

        return FunctionTool(
            SELECT_RESULT_TOOL_NAME,
            "Record the chosen result of a tuning run: the number of domains K, for each method the trial "
            "judged best at K, and the single final trial. Every named trial must have ended ok with exactly "
            "K clusters. A trial is tNNNN of the run, or <run_id>/tNNNN of another run on the same input. "
            "Writes selection.json in the run's tuning directory.",
            run,
            parameters=SELECT_RESULT_SCHEMA,
            policy=SELECT_RESULT_POLICY,
        )


def _rationale(tuning: Path) -> str | None:
    """The first 300 characters of the K decision's rationale, from the ledger."""
    ledger = tuning / "ledger.jsonl"
    if not ledger.is_file():
        return None
    for line in reversed(ledger.read_text(encoding="utf-8").splitlines()):
        event = json.loads(line)
        if event.get("kind") == "k_decision":
            text = event.get("rationale") or event.get("failure")
            return text[:300] if text else None
    return None
