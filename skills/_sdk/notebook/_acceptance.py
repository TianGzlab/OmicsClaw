"""Accepting a module, and opening an accepted module for revision.

``accept`` records the user's acceptance and freezes the module once four
conditions hold: the module README exists; the module is replayed (latest
replay ok, covering the current step files, validate step included, no
stale step); the report exists and carries the disclaimer; and either an
approving review newer than the replay, or the user's own words asking to
skip the review. ``revise`` snapshots the accepted results into
``baseline/<date>_pre_revision/`` (files up to 16 MiB copied, larger ones
by sha256) and unfreezes the module.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from skills._sdk.notebook import _hashing, _layout, _ledger, _manifest
from skills._sdk.notebook._executor import (
    EXIT_NOT_ACCEPTABLE,
    EXIT_OK,
    EXIT_USAGE,
    Out,
    _locked,
    _print,
    stitch,
)
from skills._sdk.notebook._layout import LayoutError, Module
from skills._sdk.notebook._lock import LockBusy, hold
from skills._sdk.report import DISCLAIMER

LARGE_FILE_BYTES = 16 * 1024 * 1024
"""Files larger than this are recorded by sha256 in a baseline instead of copied."""


def _module(root: Path, target: str, out: Out) -> Module | None:
    try:
        module, step = _layout.resolve_target(root, target)
    except LayoutError as exc:
        out(str(exc))
        return None
    if step is not None:
        out(f"give the module, not a step file: analysis/{module.name}")
        return None
    if not module.results_dir.is_dir():
        out(f"no module at results/{module.name}")
        return None
    return module


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _replay_problem(module: Module, manifest: dict) -> str | None:
    replay = manifest.get("replay")
    if not replay:
        return f"the module has not been replayed: run `replay analysis/{module.name}`"
    if replay.get("status") != "ok":
        return f"the latest replay failed: fix it and run `replay analysis/{module.name}` again"
    current = _manifest.current_step_hashes(module)
    if replay.get("step_sha256") != current:
        return f"step files changed since the latest replay: run `replay analysis/{module.name}` again"
    stale = [s["file"] for s in manifest.get("steps", []) if s.get("state") != "ok"]
    if stale:
        return f"steps are not up to date since the replay ({', '.join(stale)}): run `replay analysis/{module.name}` again"
    if manifest.get("validate_step") is None:
        return "the module needs exactly one validate step"
    return None


def _review_problem(module: Module, review: str, replay_at: float | None) -> tuple[str | None, Path | None]:
    raw = Path(review)
    candidates = [raw] if raw.is_absolute() else [module.root / raw, module.results_dir / raw,
                                                  module.results_dir / "reviews" / raw]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return f"review file {review} does not exist", None
    try:
        inside = path.resolve().relative_to((module.results_dir / "reviews").resolve())
    except ValueError:
        return f"the review must be saved in results/{module.name}/reviews/", None
    if inside.parts[0] == "archive":
        return f"{path.name} was archived by a later replay: review the replayed module again", None
    found = {p: (verdict, mtime) for p, verdict, mtime in _manifest.reviews(module)}
    verdict, mtime = found.get(path, (None, path.stat().st_mtime))
    if verdict != "APPROVE":
        return f"{path.name} does not start with `VERDICT: APPROVE`", None
    if replay_at is None or mtime <= replay_at:
        return f"{path.name} is older than the latest replay: review the replayed module again", None
    if path.name.startswith("task-review-"):
        try:
            receipt_path = path.with_suffix(".json")
            if receipt_path.resolve().parent != path.resolve().parent:
                raise ValueError("receipt leaves the review directory")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not isinstance(receipt, dict) or not isinstance(receipt.get("files"), dict):
                raise ValueError("receipt must contain a file-hash mapping")
            if receipt["schema"] != 1 or receipt["module"] != module.name:
                raise ValueError("receipt schema or module does not match")
            if receipt["review_sha256"] != _hashing.sha256_file(path):
                return "review text changed since delegation; request a fresh review", None
            replay = (_manifest.load(module) or {}).get("replay")
            if receipt["replay"] != replay:
                return "review belongs to a different replay; request a fresh review", None
            required = {f"analysis/{module.name}/README.md",
                        f"results/{module.name}/{module.report_name}",
                        f"results/{module.name}/{_layout.LAYOUT['review_brief']}"}
            required.update(f"analysis/{module.name}/{name}" for name in replay["step_sha256"])
            if set(receipt["files"]) != required:
                raise ValueError("receipt file inventory does not match the module")
            for name, sha in receipt["files"].items():
                source = module.root / name
                if not source.resolve().is_relative_to(module.root.resolve()):
                    raise ValueError("reviewed file leaves the project")
                if not source.is_file() or _hashing.sha256_file(source) != sha:
                    return "reviewed files changed since delegation; request a fresh review", None
        except (OSError, ValueError, KeyError, TypeError):
            return "review receipt is missing or invalid; request a fresh review", None
    return None, path


def accept(root: Path, target: str, *, review: str | None = None, skip_review: str | None = None,
           wait: float = 0.0, out: Out = _print) -> int:
    """``accept``: check the four conditions, then record the acceptance and freeze the module."""
    module = _module(root, target, out)
    if module is None:
        return EXIT_USAGE
    if bool(review) == bool(skip_review and skip_review.strip()):
        out('give exactly one of --review <file> or --skip-review "<the user\'s words>"')
        return EXIT_USAGE
    try:
        with hold(module.lock_path, command="accept", wait=wait):
            manifest = _manifest.build(module, _manifest.load(module))
            if manifest.get("frozen") and manifest.get("accepted"):
                out(f"module {module.name} is already accepted")
                return EXIT_OK
            problems: list[str] = []
            if not (module.analysis_dir / "README.md").is_file():
                problems.append(f"analysis/{module.name}/README.md is missing")
            replay_problem = _replay_problem(module, manifest)
            if replay_problem:
                problems.append(replay_problem)
            report = module.results_dir / module.report_name
            if not report.is_file():
                problems.append(f"the report results/{module.name}/{module.report_name} is missing")
            elif _squash(DISCLAIMER) not in _squash(report.read_text(encoding="utf-8")):
                problems.append(f"{module.report_name} does not carry the disclaimer verbatim")
            review_path = None
            if review:
                replay_at = _manifest.parse_time((manifest.get("replay") or {}).get("at"))
                problem, review_path = _review_problem(module, review, replay_at)
                if problem:
                    problems.append(problem)
            if problems:
                out(f"cannot accept {module.name}:")
                for problem in problems:
                    out(f"  - {problem}")
                return EXIT_NOT_ACCEPTABLE
            accepted = {
                "at": _ledger.iso(_ledger.utc_now()),
                "skip_review": skip_review.strip() if skip_review else None,
                "review": review_path.relative_to(module.results_dir).as_posix() if review_path else None,
                "replay_at": (manifest.get("replay") or {}).get("at"),
            }
            updates: dict = {"frozen": True, "accepted": accepted}
            if review_path is not None:
                updates["review"] = {"file": accepted["review"], "verdict": "APPROVE"}
            manifest = _manifest.rebuild(module, **updates)
            stitch(module, manifest)
    except LockBusy as busy:
        return _locked(module, busy, out)
    out(f"accepted {module.name}; status: {manifest['status'].upper()}, frozen")
    if skip_review:
        out(f"  review skipped at the user's request: {skip_review.strip()}")
    return EXIT_OK


def _baseline_dir(module: Module) -> Path:
    base = module.results_dir / "baseline"
    name = f"{_layout.today()}_pre_revision"
    target = base / name
    counter = 2
    while target.exists():
        target = base / f"{name}-{counter}"
        counter += 1
    return target


def snapshot(module: Module) -> tuple[Path, int, int]:
    """Copy the module's results and step files into a new baseline; return it and the copied and large counts."""
    target = _baseline_dir(module)
    target.mkdir(parents=True)
    copied = large = 0
    large_lines: list[str] = []
    for file in _hashing.directory_files(module.results_dir):
        relative = file.relative_to(module.results_dir)
        if relative.parts[0] == "baseline" or file.name == ".lock":
            continue
        size = file.stat().st_size
        if size > LARGE_FILE_BYTES:
            large_lines.append(f"{_hashing.sha256_file(file)}  {relative.as_posix()}  {size}")
            large += 1
            continue
        destination = target / "results" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, destination)
        copied += 1
    if module.analysis_dir.is_dir():
        for file in _hashing.directory_files(module.analysis_dir):
            destination = target / "analysis" / file.relative_to(module.analysis_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
            copied += 1
    if large_lines:
        (target / "LARGE_FILES.sha256").write_text("\n".join(large_lines) + "\n", encoding="utf-8")
    return target, copied, large


def revise(root: Path, target: str, *, wait: float = 0.0, out: Out = _print) -> int:
    """``revise``: snapshot an accepted module into ``baseline/`` and unfreeze it."""
    module = _module(root, target, out)
    if module is None:
        return EXIT_USAGE
    try:
        with hold(module.lock_path, command="revise", wait=wait):
            previous = _manifest.load(module) or {}
            if not previous.get("frozen"):
                out(f"module {module.name} is not accepted; change it and run it as usual")
                return EXIT_USAGE
            baseline, copied, large = snapshot(module)
            revision = {
                "at": _ledger.iso(_ledger.utc_now()),
                "baseline": baseline.relative_to(module.results_dir).as_posix(),
                "accepted": previous.get("accepted"),
                "replay_at": (previous.get("replay") or {}).get("at"),
            }
            revisions = list(previous.get("revisions", [])) + [revision]
            manifest = _manifest.rebuild(module, frozen=False, accepted=None, replay=None, revisions=revisions)
            stitch(module, manifest)
    except LockBusy as busy:
        return _locked(module, busy, out)
    out(f"module {module.name} is open for revision; status: {manifest['status'].upper()}")
    out(f"  accepted results kept in results/{module.name}/{revision['baseline']}/ "
        f"({copied} files copied, {large} large files recorded by sha256)")
    return EXIT_OK
