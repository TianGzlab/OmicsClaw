"""A module's manifest: rebuilt from the run ledgers and the runner's own state.

``provenance/manifest.json`` lists every step with its current state, the
inputs, outputs and skills of its latest run, and the module-level state
the runner keeps: interpreter, latest replay, review, acceptance and
revisions. Its ``status`` is derived, never set by hand:

* ``draft`` by default;
* ``replayed`` when the latest replay succeeded, covered exactly the
  current step files with their current contents, and no step is stale;
* ``reviewed`` when it is replayed and ``reviews/`` holds a review newer
  than that replay whose first line is ``VERDICT: APPROVE``;
* ``accepted`` once ``accept`` has run and the module is frozen.
"""

from __future__ import annotations

import json
import os
import platform
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from skills._sdk.notebook import _hashing, _ledger
from skills._sdk.notebook._layout import Module
from skills._sdk.notebook.contract import MANIFEST_SCHEMA

VERDICTS = ("APPROVE", "REVISE")


def load(module: Module) -> dict | None:
    try:
        data = json.loads(module.manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_atomic(path: Path, data: Any) -> None:
    """Write JSON to *path* through a temporary file in the same folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(4)}.tmp"
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def interpreter_info() -> dict:
    """The running interpreter: path, environment prefix, version, and its overlay if it is one."""
    overlay = None
    prefix = Path(sys.prefix)
    if (prefix / ".omicsclaw.fingerprint").is_file():
        try:
            meta = json.loads((prefix.parent / ".meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        overlay = {key: meta.get(key) for key in ("key", "skills", "skill", "packages", "requested_specs") if key in meta}
        overlay["root"] = str(prefix.parent)
    return {"path": sys.executable, "prefix": sys.prefix, "version": platform.python_version(), "overlay": overlay}


def same_interpreter(recorded: dict | None, current: dict) -> bool:
    """Whether *recorded* names the same interpreter and environment as *current*.

    The environment prefix counts as well as the executable, because an
    overlay's ``python`` is a symlink to its base interpreter.
    """
    if not recorded:
        return True

    def real(value: Any) -> str:
        return os.path.realpath(str(value)) if value else ""

    return real(recorded.get("path")) == real(current.get("path")) and real(
        recorded.get("prefix") or recorded.get("path")
    ) == real(current.get("prefix") or current.get("path"))


@dataclass
class StepState:
    """A step file's current state against its latest recorded run."""

    path: Path
    sha256: str
    state: str
    reason: str | None
    runs: list[_ledger.RunRecord]

    @property
    def latest(self) -> _ledger.RunRecord | None:
        return self.runs[-1] if self.runs else None


def _input_target(root: Path, recorded: str) -> Path:
    path = Path(recorded)
    return path if path.is_absolute() else root / path


def step_state(module: Module, step: Path) -> StepState:
    """Whether *step* is up to date, and the first reason it is not."""
    runs = _ledger.runs_of(module.runs_dir, step.stem)
    sha = _hashing.sha256_file(step)
    latest = runs[-1] if runs else None
    if latest is None:
        return StepState(step, sha, "never_run", "never run", runs)
    if latest.status != "ok":
        reason = "last run did not finish" if latest.status == "unfinished" else "last run failed"
        return StepState(step, sha, "failed", reason, runs)
    if latest.step_sha256 != sha:
        return StepState(step, sha, "stale", "step changed", runs)
    own_outputs = {f"results/{module.name}/{out.get('path')}" for out in latest.outputs}
    seen: set[str] = set()
    for record in latest.inputs:
        recorded = str(record.get("path"))
        if recorded in seen or recorded in own_outputs:
            continue
        seen.add(recorded)
        target = _input_target(module.root, recorded)
        if not target.exists():
            return StepState(step, sha, "stale", f"input missing: {recorded}", runs)
        if _hashing.sha256_path(target) != record.get("sha256"):
            return StepState(step, sha, "stale", f"input changed: {recorded}", runs)
    return StepState(step, sha, "ok", None, runs)


def overwritten_inputs(module: Module, run: _ledger.RunRecord) -> list[str]:
    """Inputs of *run* that the same run then overwrote, so they cannot mark it stale."""
    own_outputs = {f"results/{module.name}/{out.get('path')}" for out in run.outputs}
    return sorted({str(r.get("path")) for r in run.inputs} & own_outputs)


def skills_of(run: _ledger.RunRecord) -> list[dict]:
    """The skills a run loaded or ran, with the functions it called."""
    entries: dict[str, dict] = {}
    for load in run.skill_loads:
        entries.setdefault(load["skill"], {
            "skill": load["skill"], "functions": [], "cli": False,
            "git": load.get("git"), "candidate": load.get("candidate"), "stub": bool(load.get("stub")),
        })
    for call in run.skill_calls:
        entry = entries.setdefault(call["skill"], {
            "skill": call["skill"], "functions": [], "cli": False, "git": None, "candidate": None,
            "stub": bool(call.get("stub")),
        })
        if call["function"] not in entry["functions"]:
            entry["functions"].append(call["function"])
    for cli in run.skill_clis:
        entry = entries.setdefault(cli["skill"], {
            "skill": cli["skill"], "functions": [], "cli": True, "git": None, "candidate": None,
            "stub": bool(cli.get("stub")),
        })
        entry["cli"] = True
    return list(entries.values())


def _unique(records: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for record in records:
        latest[str(record.get("path"))] = {"path": record.get("path"), "sha256": record.get("sha256")}
    return list(latest.values())


def step_entry(module: Module, state: StepState) -> dict:
    latest = state.latest
    return {
        "file": state.path.name,
        "kind": "python",
        "sha256": state.sha256,
        "state": state.state,
        "reason": state.reason,
        "last_run": f"runs/{state.path.stem}/{latest.run_id}.jsonl" if latest else None,
        "history": [
            {"run_id": run.run_id, "sha256": run.step_sha256, "status": run.status, "mode": run.mode}
            for run in state.runs
        ],
        "inputs": _unique(latest.inputs) if latest else [],
        "outputs": _unique(latest.outputs) if latest else [],
        "skills": skills_of(latest) if latest else [],
    }


def _parse_time(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def reviews(module: Module) -> list[tuple[Path, str | None, float]]:
    """Review files with their verdict (``None`` when the first line is not one) and mtime, oldest first."""
    folder = module.results_dir / "reviews"
    if not folder.is_dir():
        return []
    found = []
    for path in folder.glob("*.md"):
        try:
            first = path.read_text(encoding="utf-8").lstrip().splitlines()[0].strip()
        except (OSError, IndexError, UnicodeDecodeError):
            first = ""
        verdict = next((v for v in VERDICTS if first == f"VERDICT: {v}"), None)
        found.append((path, verdict, path.stat().st_mtime))
    return sorted(found, key=lambda item: item[2])


def approving_review_after(module: Module, moment: float | None) -> Path | None:
    """The newest review approving the module that is newer than *moment*."""
    if moment is None:
        return None
    approving = [path for path, verdict, mtime in reviews(module) if verdict == "APPROVE" and mtime > moment]
    return approving[-1] if approving else None


def current_step_hashes(module: Module) -> dict[str, str]:
    return {step.name: _hashing.sha256_file(step) for step in module.steps()}


def derive_status(module: Module, manifest: dict, states: list[StepState]) -> str:
    if manifest.get("accepted") and manifest.get("frozen"):
        return "accepted"
    replay = manifest.get("replay") or {}
    replayed = (
        replay.get("status") == "ok"
        and replay.get("step_sha256") == {s.path.name: s.sha256 for s in states}
        and all(s.state == "ok" for s in states)
        and bool(states)
    )
    if not replayed:
        return "draft"
    if approving_review_after(module, _parse_time(replay.get("at"))) is not None:
        return "reviewed"
    return "replayed"


def build(module: Module, previous: dict | None = None, **updates: Any) -> dict:
    """The manifest for *module* now: steps from the ledgers, the rest from *previous* and *updates*."""
    base = previous or {}
    states = [step_state(module, step) for step in module.steps()]
    validate = module.validate_steps()
    review_files = reviews(module)
    newest = review_files[-1] if review_files else None
    manifest = {
        "schema": MANIFEST_SCHEMA["schema"],
        "module": module.name,
        "number": module.number,
        "slug": module.slug,
        "status": "draft",
        "frozen": bool(base.get("frozen", False)),
        "interpreter": base.get("interpreter"),
        "steps": [step_entry(module, state) for state in states],
        "validate_step": validate[0].name if len(validate) == 1 else None,
        "replay": base.get("replay"),
        "review": (
            {"file": newest[0].relative_to(module.results_dir).as_posix(), "verdict": newest[1]}
            if newest else base.get("review")
        ),
        "accepted": base.get("accepted"),
        "revisions": list(base.get("revisions", [])),
        "report": module.report_name,
    }
    manifest.update(updates)
    manifest["status"] = derive_status(module, manifest, states)
    return manifest


def save(module: Module, manifest: dict) -> None:
    write_atomic(module.manifest_path, manifest)


def rebuild(module: Module, **updates: Any) -> dict:
    """Rebuild and save the manifest, keeping the runner state of the previous one."""
    manifest = build(module, load(module), **updates)
    save(module, manifest)
    return manifest
