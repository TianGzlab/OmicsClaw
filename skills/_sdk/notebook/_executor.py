"""The step runner's ``new``, ``run`` and ``status``.

``run`` takes the module lock, checks the interpreter against the
manifest, and runs each stale step in a fresh kernel (validate step last),
re-checking later steps after each one because an earlier step may have
rewritten what they read. Every run gets a ledger file; afterwards the
manifest is rebuilt from the ledgers and the module notebook re-stitched.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from skills._sdk.notebook import _hashing, _layout, _ledger, _manifest
from skills._sdk.notebook._layout import LayoutError, Module
from skills._sdk.notebook._lock import LockBusy, hold
from skills._sdk.notebook._percent import PercentError, to_notebook
from skills._sdk.notebook._runners import PythonKernelRunner, StepOutcome, StepRunner, missing_kernel_packages
from skills._sdk.notebook.contract import ENVIRONMENT

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_LOCKED = 3
EXIT_NOT_ACCEPTABLE = 4

SEGMENT_LIMIT = 2000
"""Most characters printed for one step."""

Out = Callable[[str], None]


def _print(text: str) -> None:
    print(text, flush=True)


@dataclass
class StepResult:
    step: Path
    run: _ledger.RunRecord
    outcome: StepOutcome
    reason: str | None


def _short_python(info: dict) -> str:
    return f"python={info['path']} ({info['version']})"


def _call_text(call: dict) -> str:
    args = call.get("args") or {}
    shown = ", ".join(f"{key}={value}" for key, value in args.items())
    return f"{call['skill']}.{call['function']}({shown})"


def _join(items: Sequence[str], limit: int = 400) -> str:
    text = ", ".join(items)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_step(module: Module, result: StepResult) -> str:
    """The text block the runner prints for one step run, at most ``SEGMENT_LIMIT`` characters."""
    run, outcome = result.run, result.outcome
    info = run.start.get("interpreter") or {}
    head = f"[{module.name}] {result.step.name}  {outcome.status}  {outcome.seconds:.1f} s  {_short_python(info)}"
    lines = [head]
    if result.reason:
        lines.append(f"  why:      {result.reason}")
    for note in outcome.notes:
        lines.append(f"  note:     {note}")
    if run.inputs:
        lines.append("  read:     " + _join(sorted({str(r.get('path')) for r in run.inputs})))
    calls = [_call_text(c) for c in run.skill_calls] + [
        f"{c['skill']} (CLI, exit {c.get('exit_code')})" for c in run.skill_clis
    ]
    if calls:
        lines.append("  skills:   " + _join(list(dict.fromkeys(calls))))
    if run.stub_missing:
        lines.append("  stubs:    " + _join([f"{m['skill']}: {m['reason']}" for m in run.stub_missing]))
    if run.outputs:
        lines.append("  wrote:    " + _join(list(dict.fromkeys(str(o.get("path")) for o in run.outputs))))
    overwritten = _manifest.overwritten_inputs(module, run)
    if overwritten:
        lines.append(
            "  warning:  the step overwrote a file it read (" + _join(overwritten, 200)
            + "); write to a new name so a later change to that input can be seen"
        )
    notebook = module.results_dir / "notebooks" / f"{result.step.stem}.ipynb"
    rel_notebook = notebook.relative_to(module.root).as_posix()
    if outcome.status == "ok":
        lines.append(f"  notebook: {rel_notebook}")
        tail = outcome.stream.rstrip("\n").splitlines()[-30:]
        if tail:
            lines.append("  output (last 30 lines):")
            lines.extend("  " + line for line in tail)
    else:
        error = outcome.error or {}
        where = f"cell {error.get('cell')}" if error.get("cell") else "before any cell ran"
        lines.append(f"  error:    {where}: {error.get('ename')}: {error.get('evalue')}")
        traceback = (error.get("traceback") or "").rstrip("\n").splitlines()[-40:]
        if traceback:
            lines.append("  traceback (last 40 lines):")
            lines.extend("  " + line for line in traceback)
        lines.append(f"  notebook: {rel_notebook} (partial)")
    text = "\n".join(lines)
    if len(text) > SEGMENT_LIMIT:
        keep = SEGMENT_LIMIT - 60
        text = text[: keep // 2] + "\n  ... (output shortened) ...\n" + text[-keep // 2:]
    return text


def _step_env(module: Module, step: Path, ledger_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(_layout.CHECKOUT) + (os.pathsep + existing if existing else "")
    env[ENVIRONMENT["step_file"]] = str(step)
    env[ENVIRONMENT["step_ledger"]] = str(ledger_path)
    return env


def _write_notebook(path: Path, notebook: object) -> None:
    import nbformat

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp"
    nbformat.write(notebook, str(temporary))
    os.replace(temporary, path)


def execute_step(module: Module, step: Path, *, mode: str, runner: StepRunner, interpreter: dict,
                 changed_from: str | None = None, reason: str | None = None) -> StepResult:
    """Run one step, writing its ledger, notebook and log."""
    previous = _ledger.runs_of(module.runs_dir, step.stem)
    run_id = _ledger.new_run_id()
    ledger_path = module.runs_dir / step.stem / f"{run_id}.jsonl"
    ledger = _ledger.Ledger(ledger_path)
    step_sha = _hashing.sha256_file(step)
    ledger.append(
        "run_start",
        step=step.name,
        kind="python",
        mode=mode,
        step_sha256=step_sha,
        previous_sha256=previous[-1].step_sha256 if previous else None,
        interpreter=interpreter,
        interpreter_changed_from=changed_from,
        stub_dir=os.environ.get(ENVIRONMENT["skill_stubs"]) or None,
    )
    notebook_rel = f"notebooks/{step.stem}.ipynb"
    log_rel = f"logs/{step.stem}.log"
    started = time.perf_counter()
    try:
        notebook = to_notebook(step.read_text(encoding="utf-8"),
                               step={"file": step.name, "sha256": step_sha, "run_id": run_id})
    except PercentError as exc:
        outcome = StepOutcome(status="failed", notebook=None, seconds=time.perf_counter() - started,
                              error={"cell": None, "ename": "PercentError", "evalue": str(exc), "traceback": ""})
    else:
        outcome = runner.run(notebook, env=_step_env(module, step, ledger_path), cwd=module.root)
    if outcome.notebook is not None:
        _write_notebook(module.results_dir / notebook_rel, outcome.notebook)
    log_path = module.results_dir / log_rel
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(outcome.stream, encoding="utf-8")
    error = None
    if outcome.error:
        error = {key: outcome.error.get(key) for key in ("cell", "ename", "evalue")}
    ledger.append(
        "run_end",
        status=outcome.status,
        seconds=round(outcome.seconds, 3),
        error=error,
        notebook=notebook_rel if outcome.notebook is not None else None,
        log=log_rel,
    )
    return StepResult(step=step, run=_ledger.read_run(ledger_path), outcome=outcome, reason=reason)


def stitch(module: Module, manifest: dict) -> Path:
    """Concatenate the step notebooks into ``notebooks/M<NN>_<slug>.ipynb``."""
    import nbformat
    from nbformat import v4

    combined = v4.new_notebook()
    combined.cells.append(v4.new_markdown_cell(
        f"# Module {module.name}\n\nStatus: {str(manifest.get('status', 'draft')).upper()}. "
        "Each section below is one step's notebook from its latest run."
    ))
    for entry in manifest.get("steps", []):
        stem = Path(entry["file"]).stem
        functions = [
            f"{s['skill']}.{f}" for s in entry.get("skills", []) for f in s.get("functions", [])
        ] + [f"{s['skill']} (CLI)" for s in entry.get("skills", []) if s.get("cli")]
        latest = entry["history"][-1] if entry.get("history") else None
        status = latest["status"] if latest else "not run"
        header = [f"## Step {entry['file']}", ""]
        header.append(
            f"status: {status} · run: {latest['run_id'] if latest else '-'} · "
            f"sha256: {(entry.get('sha256') or '')[:12]}"
        )
        if functions:
            header.append("")
            header.append("skill functions: " + ", ".join(dict.fromkeys(functions)))
        combined.cells.append(v4.new_markdown_cell("\n".join(header)))
        path = module.results_dir / "notebooks" / f"{stem}.ipynb"
        if latest is None or not path.is_file():
            combined.cells.append(v4.new_markdown_cell("This step has not run yet."))
            continue
        try:
            step_notebook = nbformat.read(str(path), as_version=4)
        except Exception:  # an unreadable notebook should not stop the stitch
            combined.cells.append(v4.new_markdown_cell(f"The notebook {path.name} could not be read."))
            continue
        combined.cells.extend(step_notebook.cells)
    combined.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    combined.metadata["language_info"] = {"name": "python"}
    combined.metadata["omicsclaw"] = {"module": module.name}
    target = module.results_dir / "notebooks" / f"M{module.number:02d}_{module.slug}.ipynb"
    _write_notebook(target, combined)
    return target


def _check_runnable(module: Module, out: Out) -> int | None:
    if not module.analysis_dir.is_dir():
        out(f"no module at analysis/{module.name}; create one with `new <slug>`")
        return EXIT_USAGE
    r_files = module.r_files()
    if r_files:
        out("R steps are not supported yet: " + ", ".join(p.relative_to(module.root).as_posix() for p in r_files))
        return EXIT_USAGE
    manifest = _manifest.load(module)
    if manifest and manifest.get("frozen"):
        out(f"module {module.name} is accepted and frozen; run `revise analysis/{module.name}` before changing it")
        return EXIT_USAGE
    return None


def _kernel_check(runner: StepRunner | None, out: Out) -> int | None:
    if runner is not None:
        return None
    missing = missing_kernel_packages()
    if missing:
        out(f"the step runner needs nbclient and ipykernel in {sys.executable}; missing: {', '.join(missing)}")
        return EXIT_USAGE
    return None


def _locked(module: Module, busy: LockBusy, out: Out) -> int:
    holder = busy.holder
    who = ", ".join(f"{k} {v}" for k, v in holder.items()) or "an unknown process"
    out(f"module {module.name} is busy: its lock is held by {who}. Wait for it, or retry with --wait <seconds>.")
    return EXIT_LOCKED


def run_targets(root: Path, targets: Sequence[str], *, force: bool = False, runner: StepRunner | None = None,
                wait: float = 0.0, out: Out = _print) -> int:
    """``run``: run the stale steps of each target module, or the named step files."""
    try:
        resolved = [_layout.resolve_target(root, target) for target in targets]
    except LayoutError as exc:
        out(str(exc))
        return EXIT_USAGE
    problem = _kernel_check(runner, out)
    if problem is not None:
        return problem
    step_runner = runner or PythonKernelRunner()
    grouped: dict[str, tuple[Module, list[Path] | None]] = {}
    for module, step in resolved:
        current = grouped.get(module.name)
        if step is None:
            grouped[module.name] = (module, None)
        elif current is None:
            grouped[module.name] = (module, [step])
        elif current[1] is not None:
            current[1].append(step)
    worst = EXIT_OK
    for module, steps in grouped.values():
        code = run_module(module, steps, force=force, runner=step_runner, wait=wait, out=out)
        worst = max(worst, code)
    return worst


def run_module(module: Module, steps: list[Path] | None, *, force: bool, runner: StepRunner,
               wait: float = 0.0, out: Out = _print) -> int:
    problem = _check_runnable(module, out)
    if problem is not None:
        return problem
    if steps is not None:
        for step in steps:
            if step.suffix in {".R", ".r"}:
                out(f"R steps are not supported yet: {step.name}")
                return EXIT_USAGE
            if not step.is_file():
                out(f"no step file {step.relative_to(module.root).as_posix()}")
                return EXIT_USAGE
    try:
        with hold(module.lock_path, command="run", wait=wait):
            return _run_locked(module, steps, force=force, runner=runner, out=out)
    except LockBusy as busy:
        return _locked(module, busy, out)


def _run_locked(module: Module, steps: list[Path] | None, *, force: bool, runner: StepRunner, out: Out) -> int:
    previous = _manifest.load(module)
    interpreter = _manifest.interpreter_info()
    recorded = (previous or {}).get("interpreter")
    changed_from = None
    if recorded and not _manifest.same_interpreter(recorded, interpreter):
        changed_from = recorded.get("path")
        out(f"warning: module {module.name} was run with {recorded.get('path')}; this run uses {interpreter['path']}")
    for ignored in module.ignored_files():
        out(f"ignored: {ignored.name} (not a step name: <k>_<name>.py)")
    order = steps if steps is not None else module.steps()
    if not order:
        out(f"[{module.name}] no step files yet; add analysis/{module.name}/01_<name>.py")
    ran = 0
    code = EXIT_OK
    for index, step in enumerate(order):
        state = _manifest.step_state(module, step)
        if state.state == "ok" and not force:
            out(f"[{module.name}] {step.name}  up to date")
            continue
        reason = "forced" if state.state == "ok" else state.reason
        result = execute_step(module, step, mode="run", runner=runner, interpreter=interpreter,
                              changed_from=changed_from, reason=reason)
        ran += 1
        out(format_step(module, result))
        if result.outcome.status != "ok":
            rest = [p.name for p in order[index + 1:]]
            if rest:
                out(f"[{module.name}] stopped; not run: {', '.join(rest)}")
            code = EXIT_FAILED
            break
    updates = {"interpreter": interpreter} if ran else {}
    manifest = _manifest.rebuild(module, **updates)
    if ran:
        notebook = stitch(module, manifest)
        out(f"[{module.name}] module notebook: {notebook.relative_to(module.root).as_posix()}")
    return code


def status(root: Path, target: str | None = None, *, out: Out = _print) -> int:
    """``status``: every module's status, each step's state and the skill functions it called."""
    if target:
        try:
            module, _step = _layout.resolve_target(root, target)
        except LayoutError as exc:
            out(str(exc))
            return EXIT_USAGE
        modules = [module]
    else:
        modules = _layout.modules(root)
    if not modules:
        out("No modules yet. Create one with `new <slug>`.")
        return EXIT_OK
    for module in modules:
        previous = _manifest.load(module)
        manifest = _manifest.build(module, previous)
        label = manifest["status"].upper()
        if manifest["status"] != "accepted" and manifest.get("revisions"):
            label += " (revising)"
        out(f"{module.name}  {label}")
        for entry in manifest["steps"]:
            state = entry["state"]
            detail = state if state == "ok" else f"{state.replace('_', ' ')}: {entry['reason']}"
            if state == "never_run":
                detail = "never run"
            out(f"  {entry['file']}  {detail}")
        if not manifest["steps"]:
            out("  no step files yet")
        elif manifest["validate_step"] is None:
            count = len(module.validate_steps())
            out("  no validate step yet" if count == 0 else f"  {count} validate steps; a module has exactly one")
        functions = [
            f"{s['skill']}.{f}" for e in manifest["steps"] for s in e["skills"] for f in s["functions"]
        ] + [f"{s['skill']} (CLI)" for e in manifest["steps"] for s in e["skills"] if s.get("cli")]
        if functions:
            out("  skills: " + ", ".join(dict.fromkeys(functions)))
        report = module.results_dir / module.report_name
        if report.is_file():
            out(f"  report: results/{module.name}/{module.report_name}")
    return EXIT_OK


def new_module(root: Path, slug: str, *, out: Out = _print) -> int:
    """``new``: allocate the next module number and create its folders, and the project skeleton."""
    if not _layout.SLUG_RE.match(slug):
        out(f"{slug!r} is not a module slug: use lowercase letters, digits and underscores")
        return EXIT_USAGE
    if _layout.NUMBERED_SLUG_RE.match(slug):
        out(f"{slug!r} starts with a module number; give the slug alone (for example `new {slug[3:]}`), "
            "and `new` assigns the number")
        return EXIT_USAGE
    had_results = (root / "results").is_dir()
    try:
        with hold(root / "results" / ".project.lock", command="new", wait=10.0):
            created = _layout.ensure_skeleton(root)
            if not had_results and "results/" not in created:
                created.insert(1, "results/")
            module = _layout.create_module(root, slug)
    except LockBusy as busy:
        out(f"another process is creating a module ({busy.holder}); try again")
        return EXIT_LOCKED
    except LayoutError as exc:
        out(str(exc))
        return EXIT_USAGE
    out(f"created module {module.name}")
    out(f"  code:    analysis/{module.name}/ (README.md to fill in; add step files 01_<name>.py ... and one <k>_validate.py)")
    out(f"  results: results/{module.name}/")
    if created:
        out("  project folders created: " + ", ".join(created))
    if _layout.is_checkout(root):
        out(
            "warning: this project is inside an OmicsClaw checkout, so its scripts/ and docs/ folders are the "
            "repository's own. Prefer a separate project folder, with OMICSCLAW_SKILLS_DIR pointing at "
            "<checkout>/skills."
        )
    return EXIT_OK


def _output_files(module: Module) -> dict[str, str]:
    """``figures/``, ``tables/`` and ``intermediate/`` files with their sha256, relative to the results."""
    found: dict[str, str] = {}
    for folder in ("figures", "tables", "intermediate"):
        base = module.results_dir / folder
        if not base.is_dir():
            continue
        for file in _hashing.directory_files(base):
            if file.name.startswith(".tmp-"):
                continue
            found[file.relative_to(module.results_dir).as_posix()] = _hashing.sha256_file(file)
    return found


def replay(root: Path, target: str, *, new_interpreter: str | None = None, runner: StepRunner | None = None,
           wait: float = 0.0, out: Out = _print) -> int:
    """``replay``: rerun every step of a module in fresh kernels, validate last, and record the result."""
    try:
        module, step = _layout.resolve_target(root, target)
    except LayoutError as exc:
        out(str(exc))
        return EXIT_USAGE
    if step is not None:
        out("replay takes a module, not a step file: replay analysis/" + module.name)
        return EXIT_USAGE
    problem = _check_runnable(module, out)
    if problem is not None:
        return problem
    validate = module.validate_steps()
    if len(validate) != 1:
        out(
            f"module {module.name} needs exactly one validate step (<k>_validate.py) before replay; "
            f"found {len(validate)}"
        )
        return EXIT_USAGE
    problem = _kernel_check(runner, out)
    if problem is not None:
        return problem
    try:
        with hold(module.lock_path, command="replay", wait=wait):
            return _replay_locked(module, new_interpreter, runner or PythonKernelRunner(), out)
    except LockBusy as busy:
        return _locked(module, busy, out)


def _replay_locked(module: Module, new_interpreter: str | None, runner: StepRunner, out: Out) -> int:
    previous = _manifest.load(module) or {}
    interpreter = _manifest.interpreter_info()
    recorded = previous.get("interpreter")
    changed_from = None
    if recorded and not _manifest.same_interpreter(recorded, interpreter):
        if not new_interpreter:
            out(
                f"module {module.name} was run with {recorded.get('path')}; this replay would use "
                f"{interpreter['path']}. Replay with the recorded interpreter, or confirm the change with "
                '--new-interpreter "<reason>".'
            )
            return EXIT_USAGE
        changed_from = recorded.get("path")
        out(f"note: replaying {module.name} with {interpreter['path']} instead of {changed_from}: {new_interpreter}")
    before = _output_files(module)
    steps = module.steps()
    hashes = {step.name: _hashing.sha256_file(step) for step in steps}
    written: set[str] = set()
    status_value = "ok"
    for index, step in enumerate(steps):
        result = execute_step(module, step, mode="replay", runner=runner, interpreter=interpreter,
                              changed_from=changed_from, reason="replay")
        out(format_step(module, result))
        written.update(str(o.get("path")) for o in result.run.outputs)
        if result.outcome.status != "ok":
            status_value = "failed"
            rest = [p.name for p in steps[index + 1:]]
            if rest:
                out(f"[{module.name}] replay stopped; not run: {', '.join(rest)}")
            break
    after = _output_files(module)
    changed = sorted(path for path in written if path in after and before.get(path) != after[path])
    orphans = sorted(path for path in after if path not in written) if status_value == "ok" else []
    record = {
        "at": _ledger.iso(_ledger.utc_now()),
        "status": status_value,
        "interpreter": interpreter["path"],
        "new_interpreter_reason": new_interpreter if changed_from else None,
        "step_sha256": hashes,
        "changed_outputs": changed,
        "orphan_outputs": orphans,
    }
    manifest = _manifest.rebuild(module, interpreter=interpreter, replay=record)
    stitch(module, manifest)
    if status_value != "ok":
        out(f"[{module.name}] replay failed; status: {manifest['status'].upper()}")
        return EXIT_FAILED
    out(f"[{module.name}] replay ok: {len(steps)} steps, validate last")
    if changed:
        out("  changed outputs: " + _join(changed))
    if orphans:
        out("  orphan outputs (not written by this replay; the report must not rely on them): " + _join(orphans))
    out(f"  status: {manifest['status'].upper()}")
    return EXIT_OK
