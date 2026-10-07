"""The step runner's ``new``, ``run`` and ``status``.

``run`` takes the module lock, checks the interpreter against the
manifest, and runs each stale step in a fresh kernel (validate step last),
re-checking later steps after each one because an earlier step may have
rewritten what they read. Every run gets a ledger file; afterwards the
manifest is rebuilt from the ledgers and the module notebook re-stitched.

Output goes to stdout. When its reader goes away (``run ... | head``), the
rest of the output is dropped and the run carries on to the end.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from skills._sdk.notebook import _brief, _hashing, _io, _layout, _ledger, _manifest, _watchdog
from skills._sdk.notebook._layout import LayoutError, Module
from skills._sdk.notebook._lock import LockBusy, hold
from skills._sdk.notebook._percent import PercentError, to_notebook
from skills._sdk.notebook._runners import PythonKernelRunner, RscriptRunner, StepOutcome, StepRunner, missing_kernel_packages
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
    """Print *text*; once stdout's reader has gone, send the rest of the output to the null device."""
    try:
        print(text, flush=True)
    except BrokenPipeError:
        _drop_stdout()


def _drop_stdout() -> None:
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - lives as long as the process
    finally:
        os.close(devnull)


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
    runtime = _short_python(info)
    if run.start.get("kind") == "r":
        session = run.r_sessions[-1] if run.r_sessions else {}
        runtime = f"Rscript={session.get('rscript', 'unknown')} ({session.get('r_version', 'unknown')})"
    head = f"[{module.name}] {result.step.name}  {outcome.status}  {outcome.seconds:.1f} s  {runtime}"
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
            + "); a rerun of this step alone reads its own output, so write to a new name"
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
        if outcome.notebook is None:
            lines.append("  notebook: none (no cell ran)")
        else:
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
    env[ENVIRONMENT["step_io"]] = str(ledger_path.with_suffix(".io.tsv"))
    env[ENVIRONMENT["sdk_dir"]] = str(Path(__file__).resolve().parents[1])
    return env


def _record_r_io(module: Module, step: Path, ledger: _ledger.Ledger) -> None:
    """Hash the R step's IO journal after it exits, while the activity lock is held."""
    path = ledger.path.with_suffix(".io.tsv")
    if not path.exists():
        return
    ctx = _io.StepContext(step, module.root, module, ledger)
    for line in path.read_text(encoding="utf-8").splitlines():
        kind, recorded, via = line.split("\t", 2)
        if kind == "input":
            _io.record_input(ctx, Path(recorded), via=via)
        elif kind == "output":
            target = _io.check_output_path(module, recorded)
            ledger.append("output", path=target.relative_to(module.results_dir).as_posix(),
                          sha256=_hashing.sha256_path(target),
                          bytes=_hashing.size_of(target), kind=via)
    path.unlink()


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
    notebook_rel = f"notebooks/{step.stem}.ipynb"
    log_rel = f"logs/{step.stem}.log"
    started = time.perf_counter()
    kind = "r" if step.suffix == ".R" else "python"
    with _watchdog.ACTIVITY.lock:
        ledger.append(
            "run_start",
            step=step.name,
            kind=kind,
            mode=mode,
            step_sha256=step_sha,
            previous_sha256=previous[-1].step_sha256 if previous else None,
            interpreter=interpreter,
            interpreter_changed_from=changed_from,
            stub_dir=os.environ.get(ENVIRONMENT["skill_stubs"]) or None,
        )
        _watchdog.ACTIVITY.current = _watchdog.Current(
            ledger=ledger, label=f"{module.name}/{step.name}", started=started, kill=getattr(runner, "kill", None),
            notebook=module.results_dir / notebook_rel,
        )
    try:
        text = step.read_text(encoding="utf-8")
        notebook = to_notebook(text, step={"file": step.name, "sha256": step_sha, "run_id": run_id}, language=kind)
    except UnicodeDecodeError as exc:
        outcome = StepOutcome(status="failed", notebook=None, seconds=time.perf_counter() - started, error={
            "cell": None, "ename": "UnicodeDecodeError",
            "evalue": f"{step.name} is not UTF-8 text (byte {exc.start}: {exc.reason}); save it as UTF-8",
            "traceback": "",
        })
    except PercentError as exc:
        outcome = StepOutcome(status="failed", notebook=None, seconds=time.perf_counter() - started,
                              error={"cell": None, "ename": "PercentError", "evalue": str(exc), "traceback": ""})
    else:
        outcome = runner.run(notebook, env=_step_env(module, step, ledger_path), cwd=module.root)
    error = None
    if outcome.error:
        error = {key: outcome.error.get(key) for key in ("cell", "ename", "evalue")}
    with _watchdog.ACTIVITY.lock:
        if kind == "r":
            try:
                _record_r_io(module, step, ledger)
            except (OSError, ValueError) as exc:
                outcome.status = "failed"
                outcome.notes.append(f"could not record R IO: {exc}")
                if outcome.error is None:
                    outcome.error = {"cell": None, "ename": "RJournalError", "evalue": str(exc), "traceback": ""}
                    error = {key: outcome.error[key] for key in ("cell", "ename", "evalue")}
                outcome.stream += f"\nRJournalError: {exc}\n"
            if outcome.r_session:
                ledger.append("r_session", **outcome.r_session)
        if outcome.notebook is not None:
            _write_notebook(module.results_dir / notebook_rel, outcome.notebook)
        else:
            # The notebook of an earlier run would otherwise pass for this one's.
            (module.results_dir / notebook_rel).unlink(missing_ok=True)
        log_path = module.results_dir / log_rel
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(outcome.stream, encoding="utf-8")
        ledger.append(
            "run_end",
            status=outcome.status,
            seconds=round(outcome.seconds, 3),
            error=error,
            notebook=notebook_rel if outcome.notebook is not None else None,
            log=log_rel,
        )
        _watchdog.ACTIVITY.current = None
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
        if latest is None:
            combined.cells.append(v4.new_markdown_cell("This step has not run yet."))
            continue
        if not path.is_file():
            combined.cells.append(v4.new_markdown_cell(
                f"No notebook: the latest run ({status}) stopped before any cell ran."
            ))
            continue
        try:
            step_notebook = nbformat.read(str(path), as_version=4)
        except Exception:  # an unreadable notebook should not stop the stitch
            combined.cells.append(v4.new_markdown_cell(f"The notebook {path.name} could not be read."))
            continue
        if entry.get("kind") == "r":
            runtime = (manifest.get("rscript") or {}).get("version", "unknown")
            combined.cells.append(v4.new_markdown_cell(f"R step, Rscript {runtime}"))
            for cell in step_notebook.cells:
                if cell.cell_type == "code":
                    from skills._sdk.notebook._runners import stream_text

                    outputs = stream_text(v4.new_notebook(cells=[cell]))
                    combined.cells.append(v4.new_markdown_cell(
                        f"```r\n{cell.source}\n```\n\n```text\n{outputs}\n```"
                    ))
                else:
                    combined.cells.append(cell)
        else:
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
    problems = module.layout_problems()
    if problems:
        out("invalid step layout:\n" + "\n".join(problems))
        return EXIT_USAGE
    return _frozen(module, out)


def _frozen(module: Module, out: Out) -> int | None:
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


def _rscript_check(steps: Sequence[Path], runners: Mapping[str, StepRunner], out: Out) -> int | None:
    if any(step.suffix == ".R" for step in steps):
        if isinstance(runners["r"], RscriptRunner) and not runners["r"].rscript:
            out("Rscript not found; searched CONDA_PREFIX/bin/Rscript, "
                f"{sys.prefix}/bin/Rscript and PATH. Install R in the environment or sandbox image.")
            return EXIT_USAGE
    return None


def _rscript_warning(module: Module, manifest: dict, runners: Mapping[str, StepRunner]) -> str | None:
    recorded = (manifest.get("rscript") or {}).get("path")
    current = getattr(runners["r"], "rscript", None)
    if recorded and current and os.path.realpath(recorded) != os.path.realpath(current):
        return f"warning: module {module.name} Rscript changed from {recorded} to {current}"
    return None


def run_targets(root: Path, targets: Sequence[str], *, force: bool = False, runner: StepRunner | None = None,
                runners: Mapping[str, StepRunner] | None = None,
                wait: float = 0.0, out: Out = _print) -> int:
    """``run``: run the stale steps of each target module, or the named step files."""
    try:
        resolved = [_layout.resolve_target(root, target) for target in targets]
    except LayoutError as exc:
        out(str(exc))
        return EXIT_USAGE
    problem = _kernel_check(runner or (runners or {}).get("python"), out)
    if problem is not None:
        return problem
    selected = {"python": runner or PythonKernelRunner(), "r": RscriptRunner(), **(runners or {})}
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
        code = run_module(module, steps, force=force, runners=selected, wait=wait, out=out)
        worst = max(worst, code)
    return worst


def run_module(module: Module, steps: list[Path] | None, *, force: bool, runners: Mapping[str, StepRunner],
               wait: float = 0.0, out: Out = _print) -> int:
    problem = _check_runnable(module, out)
    if problem is not None:
        return problem
    if steps is not None:
        for step in steps:
            if not step.is_file():
                out(f"no step file {step.relative_to(module.root).as_posix()}")
                return EXIT_USAGE
    problem = _rscript_check(module.steps() if steps is None else steps, runners, out)
    if problem is not None:
        return problem
    try:
        with hold(module.lock_path, command="run", wait=wait):
            return _run_locked(module, steps, force=force, runners=runners, out=out)
    except LockBusy as busy:
        return _locked(module, busy, out)


def _interpreter_warning(module: Module, recorded: str | None, current: str) -> str:
    return f"warning: module {module.name} was run with {recorded}; this run uses {current}"


def _run_locked(module: Module, steps: list[Path] | None, *, force: bool, runners: Mapping[str, StepRunner], out: Out) -> int:
    # Checked again under the lock: an `accept` this run waited for may have frozen the module.
    problem = _frozen(module, out)
    if problem is not None:
        return problem
    previous = _manifest.load(module)
    r_warning = _rscript_warning(module, previous or {}, runners)
    if r_warning:
        out(r_warning)
    interpreter = _manifest.interpreter_info()
    recorded = (previous or {}).get("interpreter")
    changed_from = None
    if recorded and not _manifest.same_interpreter(recorded, interpreter):
        changed_from = recorded.get("path")
        out(_interpreter_warning(module, changed_from, interpreter["path"]))
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
        result = execute_step(module, step, mode="run", runner=runners["r" if step.suffix == ".R" else "python"], interpreter=interpreter,
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
        # The brief describes the latest replay; a step run since then leaves it out of date.
        _brief.remove(module)
        notebook = stitch(module, manifest)
        out(f"[{module.name}] module notebook: {notebook.relative_to(module.root).as_posix()}")
    if changed_from:
        out(_interpreter_warning(module, changed_from, interpreter["path"]))
    if r_warning:
        out(r_warning)
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
        for problem in module.layout_problems():
            out(f"  invalid layout: {problem}")
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
           runners: Mapping[str, StepRunner] | None = None,
           wait: float = 0.0, out: Out = _print) -> int:
    """``replay``: rerun every step of a module in fresh kernels, validate last, and record the result.

    A successful replay also writes the review brief (``provenance/review_brief.md``);
    ``run`` removes it again once it runs a step.
    """
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
    problem = _kernel_check(runner or (runners or {}).get("python"), out)
    if problem is not None:
        return problem
    selected = {"python": runner or PythonKernelRunner(), "r": RscriptRunner(), **(runners or {})}
    problem = _rscript_check(module.steps(), selected, out)
    if problem is not None:
        return problem
    try:
        with hold(module.lock_path, command="replay", wait=wait):
            return _replay_locked(module, new_interpreter, selected, out)
    except LockBusy as busy:
        return _locked(module, busy, out)


def _replay_locked(module: Module, new_interpreter: str | None, runners: Mapping[str, StepRunner], out: Out) -> int:
    problem = _frozen(module, out)
    if problem is not None:
        return problem
    previous = _manifest.load(module) or {}
    r_warning = _rscript_warning(module, previous, runners)
    if r_warning:
        out(r_warning)
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
    archived = _manifest.archive_reviews(module, _ledger.new_run_id())
    if archived:
        history = list(previous.get("review_history") or []) + archived
        revisions = _manifest.relink_reviews(list(previous.get("revisions") or []), archived)
        _manifest.rebuild(module, review_history=history, review=None, revisions=revisions)
        folder = Path(archived[0]["file"]).parent.as_posix()
        out(f"[{module.name}] moved {len(archived)} earlier review(s) to results/{module.name}/{folder}/; "
            "review the replayed module again")
    _brief.remove(module)
    before = _output_files(module)
    steps = module.steps()
    hashes = {step.name: _hashing.sha256_file(step) for step in steps}
    written: set[str] = set()
    status_value = "ok"
    runs: list[tuple[Path, _ledger.RunRecord]] = []
    for index, step in enumerate(steps):
        result = execute_step(module, step, mode="replay", runner=runners["r" if step.suffix == ".R" else "python"], interpreter=interpreter,
                              changed_from=changed_from, reason="replay")
        runs.append((step, result.run))
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
        if r_warning:
            out(r_warning)
        return EXIT_FAILED
    out(f"[{module.name}] replay ok: {len(steps)} steps, validate last")
    try:
        brief = _brief.write(module, runs, manifest)
        out(f"  review brief: {brief.relative_to(module.root).as_posix()}")
    except Exception as exc:  # the brief only helps the review; whatever stops it, the replay stands
        out(f"  warning: could not write the review brief: {type(exc).__name__}: {exc}")
    if changed:
        out("  changed outputs: " + _join(changed))
    if orphans:
        out("  orphan outputs (not written by this replay; the report must not rely on them): " + _join(orphans))
    if changed_from:
        out(f"  interpreter: {interpreter['path']} (was {changed_from}; reason: {new_interpreter})")
    out(f"  status: {manifest['status'].upper()}")
    if r_warning:
        out(r_warning)
    return EXIT_OK
