"""The review brief a successful replay writes for the module reviewer.

``provenance/review_brief.md`` gives, for each step, its first markdown cell
beside the skill calls the replay recorded, what the step read and wrote with
sizes, and the end of its log, and for the validate step the checks it calls
with what each asserts; then each text table's shape with its first
rows, or the whole table when it is small; every output file with its size;
and the replay record with its changed and orphan outputs. It stays within
:data:`MAX_LINES` lines, so one line-mode read takes it in; when the module is
too big for that, table rows go first, then log lines, and the brief says
where it was shortened.

A replay removes the old brief before it runs any step, and ``run`` removes
it once it runs a step, so a brief on disk always describes the latest
replay, a successful one, of the step files as they are.
"""

from __future__ import annotations

import ast
import csv
import inspect
import io
import json
import os
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from skills._sdk.notebook import _hashing, _ledger, _skills, checks
from skills._sdk.notebook._layout import VALIDATE_RE, Module
from skills._sdk.notebook._percent import PercentError, parse_cells
from skills._sdk.notebook.contract import LAYOUT

MAX_LINES = 450
SMALL_ROWS = 20
SMALL_BYTES = 2048
HEAD_ROWS = 5
CELL_CHARS = 40
MAX_COLUMNS = 20
LINE_CHARS = 200
JSON_LINES = 60
TABLE_SUFFIXES = {".csv": ",", ".tsv": "\t"}
INVENTORY_DIRS = ("figures", "tables", "intermediate", "logs")


@dataclass(frozen=True)
class Detail:
    """How much the brief shows; each level down drops more."""

    first_cell_lines: int = 20
    log_lines: int = 10
    head_rows: int = HEAD_ROWS
    whole_rows: int = SMALL_ROWS
    inventory: int | None = None


LEVELS = (
    Detail(),
    Detail(head_rows=0),
    Detail(head_rows=0, log_lines=3),
    Detail(head_rows=0, log_lines=3, whole_rows=5, first_cell_lines=8),
    Detail(head_rows=0, log_lines=0, whole_rows=0, first_cell_lines=8, inventory=60),
)


def path_of(module: Module) -> Path:
    return module.results_dir / LAYOUT["review_brief"]


def remove(module: Module) -> None:
    path_of(module).unlink(missing_ok=True)


def write(module: Module, runs: Sequence[tuple[Path, _ledger.RunRecord]], manifest: dict) -> Path:
    """Write the brief for a successful replay, through a temporary file, and return its path."""
    path = path_of(module)
    text = render(module, runs, manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(4)}.tmp"
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _size(count: int) -> str:
    if count < 1000:
        return f"{count} B"
    value = count / 1000
    for unit in ("KB", "MB"):
        if value < 1000:
            return f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} GB"


def _clip(text: str, limit: int = LINE_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _first_cell(step: Path) -> str | None:
    try:
        cells = parse_cells(step.read_text(encoding="utf-8"), language="r" if step.suffix == ".R" else "python")
    except (OSError, UnicodeDecodeError, PercentError):
        return None
    for cell in cells:
        if cell.kind == "markdown":
            return cell.source
    return None


def _words(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))


def _library_names(run: _ledger.RunRecord) -> dict[str, list[str]]:
    names: dict[str, list[str]] = {}
    for load in run.skill_loads:
        try:
            api = _skills.skill_dir(load["skill"], load.get("root")) / "_api.py"
            names[load["skill"]] = _skills.public_names(api)[0] if api.is_file() else []
        except (LookupError, OSError, SyntaxError, ValueError):
            names[load["skill"]] = []
    return names


def checks_called(source: str) -> list[str]:
    """The validate checks a step's code calls, in the order of their first call, read with ast."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    direct: dict[str, str] = {}
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == checks.__name__:
            direct.update({alias.asname or alias.name: alias.name for alias in node.names})
        elif isinstance(node, ast.ImportFrom) and node.module == "skills._sdk.notebook":
            modules.update(alias.asname or alias.name for alias in node.names if alias.name == "checks")
        elif isinstance(node, ast.Import):
            modules.update(alias.asname for alias in node.names if alias.name == checks.__name__ and alias.asname)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in direct:
            name = direct[function.id]
        elif isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name) \
                and function.value.id in modules:
            name = function.attr
        else:
            continue
        if name in checks.__all__:
            found.append((node.lineno, node.col_offset, name))
    return list(dict.fromkeys(name for _line, _column, name in sorted(found)))


def _check_lines(step: Path) -> list[str]:
    try:
        names = checks_called(step.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return []
    if not names:
        return ["Checks called: none recognised from skills._sdk.notebook.checks; read the step for any others"]
    lines = ["Checks called (skills._sdk.notebook.checks), with what each asserts:"]
    for name in names:
        summary = (inspect.getdoc(getattr(checks, name)) or "").splitlines()
        lines.append(_clip(f"  {name}: {summary[0] if summary else ''}"))
    return lines


def _call_text(call: dict) -> str:
    args = call.get("args") or {}
    shown = ", ".join(f"{key}={value}" for key, value in args.items())
    return _clip(f"{call['skill']}.{call['function']}({shown})", 160)


def _step_lines(module: Module, step: Path, run: _ledger.RunRecord, detail: Detail) -> list[str]:
    try:
        line_count = len(step.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        line_count = 0
    lines = [f"### {step.name}  (sha256 {(run.step_sha256 or '')[:12]}, {line_count} lines)"]
    cell = _first_cell(step)
    if cell is None:
        lines.append("First cell: none (the step does not open with a markdown cell)")
        cell = ""
    else:
        cell_lines = cell.splitlines()
        lines.append("First cell:")
        lines.extend(f"> {_clip(line)}" for line in cell_lines[: detail.first_cell_lines])
        if len(cell_lines) > detail.first_cell_lines:
            lines.append(f"> ... ({len(cell_lines) - detail.first_cell_lines} more lines in the step file)")
    calls = list(dict.fromkeys(_call_text(c) for c in run.skill_calls))
    clis = list(dict.fromkeys(
        _clip(f"{c['skill']} (CLI: {' '.join(str(a) for a in c.get('argv') or [])})", 240) for c in run.skill_clis
    ))
    lines.append("Recorded calls: " + ("; ".join(calls + clis) if calls or clis else
                                      "none (R step)" if step.suffix == ".R" else "none"))
    if run.r_sessions:
        session = run.r_sessions[-1]
        packages = list((session.get("packages") or {}).items())
        shown = ", ".join(f"{name}={version}" for name, version in packages[:8])
        if len(packages) > 8:
            shown += f", ... ({len(packages) - 8} more)"
        lines.append(f"R step: Rscript {session.get('r_version', 'unknown')}; packages: {shown or 'none'}")
    called = {(c["skill"], c["function"]) for c in run.skill_calls}
    words = _words(cell)
    unnamed = sorted({f"{s}.{f}" for s, f in called if f not in words})
    named = sorted(
        f"{skill}.{name}" for skill, names in _library_names(run).items()
        for name in names if name in words and (skill, name) not in called
    )
    if called or named:
        lines.append(
            "Word match against the first cell: recorded but not named: "
            f"{', '.join(unnamed) or 'none'}; named but not recorded: {', '.join(named) or 'none'}"
        )
    reads = []
    for record in {str(r.get("path")): r for r in run.inputs}.values():
        flag = ", outside contract" if record.get("outside_contract") else ""
        reads.append(f"{record.get('path')} ({_size(int(record.get('bytes') or 0))}, via {record.get('via')}{flag})")
    lines.append("Read: " + ("; ".join(reads) if reads else "nothing recorded"))
    writes = [f"{o.get('path')} ({_size(int(o.get('bytes') or 0))})"
              for o in {str(o.get("path")): o for o in run.outputs}.values()]
    lines.append("Wrote: " + ("; ".join(writes) if writes else "nothing recorded"))
    if VALIDATE_RE.match(step.name):
        lines += _check_lines(step)
    if detail.log_lines:
        log = module.results_dir / "logs" / f"{step.stem}.log"
        try:
            tail = log.read_text(encoding="utf-8", errors="replace").rstrip("\n").splitlines()[-detail.log_lines:]
        except OSError:
            tail = []
        lines.append(f"Log, last {len(tail)} lines (logs/{step.stem}.log):" if tail else "Log: empty")
        lines.extend(f"    {_clip(line)}" for line in tail)
    return lines


def _csv_rows(path: Path, delimiter: str) -> tuple[list[str], int, list[list[str]]]:
    """Header, data-row count and the first rows, reading the whole file once."""
    with open(path, encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, [])
        kept: list[list[str]] = []
        count = 0
        for row in reader:
            if count < SMALL_ROWS + 1:
                kept.append(row)
            count += 1
    return header, count, kept


def _render_rows(rows: list[list[str]], delimiter: str) -> list[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    for row in rows:
        shown = [_clip(cell, CELL_CHARS) for cell in row[:MAX_COLUMNS]]
        if len(row) > MAX_COLUMNS:
            shown.append(f"... +{len(row) - MAX_COLUMNS} columns")
        writer.writerow(shown)
    return [_clip(line) for line in buffer.getvalue().splitlines()]


def _table_lines(module: Module, path: Path, detail: Detail) -> list[str]:
    relative = path.relative_to(module.results_dir).as_posix()
    size = path.stat().st_size
    if path.suffix.lower() == ".json":
        if size <= SMALL_BYTES and detail.whole_rows:
            text = path.read_text(encoding="utf-8", errors="replace").rstrip("\n").splitlines()
            if len(text) <= JSON_LINES:
                return [f"### {relative}  JSON, {_size(size)}, whole file", *(_clip(line) for line in text)]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return [f"### {relative}  JSON, {_size(size)}, not valid JSON"]
        except RecursionError:
            return [f"### {relative}  JSON, {_size(size)}, nested too deeply to parse"]
        shape = (f"keys: {', '.join(map(str, list(data)[:30]))}" if isinstance(data, dict)
                 else f"a list of {len(data)} items" if isinstance(data, list) else type(data).__name__)
        return [f"### {relative}  JSON, {_size(size)}; {_clip(shape, 400)}"]
    delimiter = TABLE_SUFFIXES[path.suffix.lower()]
    header, count, kept = _csv_rows(path, delimiter)
    head = f"### {relative}  {count:,} rows x {len(header)} columns, {_size(size)}"
    if count <= detail.whole_rows and size <= SMALL_BYTES:
        return [head + ", whole table", *_render_rows([header, *kept], delimiter)]
    if detail.head_rows:
        return [head + f", first {min(detail.head_rows, count)} rows",
                *_render_rows([header, *kept[: detail.head_rows]], delimiter)]
    return [head + "; columns: " + _clip(", ".join(header[:MAX_COLUMNS]), 400)]


def _tables(module: Module) -> list[Path]:
    found = []
    for folder in ("tables", "intermediate"):
        base = module.results_dir / folder
        if base.is_dir():
            found.extend(p for p in _hashing.directory_files(base)
                         if p.suffix.lower() in {*TABLE_SUFFIXES, ".json"} and not p.name.startswith(".tmp-"))
    return found


def _inventory(module: Module, replay: dict, detail: Detail) -> list[str]:
    orphans = set(replay.get("orphan_outputs") or [])
    changed = set(replay.get("changed_outputs") or [])
    files = []
    for folder in INVENTORY_DIRS:
        base = module.results_dir / folder
        if base.is_dir():
            files.extend(p for p in _hashing.directory_files(base) if not p.name.startswith(".tmp-"))
    lines = ["| path | bytes | note |", "|---|---|---|"]
    shown = files if detail.inventory is None else files[: detail.inventory]
    for path in shown:
        relative = path.relative_to(module.results_dir).as_posix()
        note = "orphan" if relative in orphans else "changed by this replay" if relative in changed else ""
        lines.append(f"| {relative} | {path.stat().st_size:,} | {note} |")
    if len(shown) < len(files):
        lines.append(f"| ... and {len(files) - len(shown)} more files | | |")
    return lines


def _compose(module: Module, runs: Sequence[tuple[Path, _ledger.RunRecord]], manifest: dict,
             detail: Detail, shortened: bool) -> list[str]:
    replay = manifest.get("replay") or {}
    lines = [
        f"# Review brief: {module.name}",
        "",
        f"Written by the replay at {replay.get('at')}; module status {str(manifest.get('status', '')).upper()}. "
        "Replaying the module rewrites it. Step files, the README and the REPORT are not copied here.",
    ]
    if shortened:
        lines.append("Shortened to fit: table rows or log lines are left out where noted; read those files for them.")
    changed = ", ".join(replay.get("changed_outputs") or []) or "none"
    orphans = ", ".join(replay.get("orphan_outputs") or []) or "none"
    lines += [
        "",
        "## Replay",
        "",
        f"status {replay.get('status')} · {len(runs)} steps, validate last ({manifest.get('validate_step')}) · "
        f"interpreter {replay.get('interpreter')}",
        f"changed outputs: {_clip(changed, 600)}",
        f"orphan outputs: {_clip(orphans, 600)}",
        "",
        "## Steps",
        "",
    ]
    for step, run in runs:
        lines += _step_lines(module, step, run, detail)
        lines.append("")
    lines += ["## Tables", ""]
    tables = _tables(module)
    if not tables:
        lines += ["No .csv, .tsv or .json files under tables/ or intermediate/.", ""]
    for table in tables:
        try:
            lines += _table_lines(module, table, detail)
        except (OSError, csv.Error, UnicodeDecodeError, ValueError, RecursionError) as exc:
            reason = _clip(f"{type(exc).__name__}: {exc}", 160)
            lines.append(f"### {table.relative_to(module.results_dir).as_posix()}  could not be read: {reason}")
        lines.append("")
    lines += ["## Output files", "", *_inventory(module, replay, detail)]
    return lines


def render(module: Module, runs: Sequence[tuple[Path, _ledger.RunRecord]], manifest: dict) -> str:
    """The brief's text, at the most detail that fits in :data:`MAX_LINES` lines."""
    for number, detail in enumerate(LEVELS):
        lines = _compose(module, runs, manifest, detail, shortened=number > 0)
        if len(lines) <= MAX_LINES:
            return "\n".join(lines) + "\n"
    kept = lines[: MAX_LINES - 1]
    kept.append(f"... cut at {MAX_LINES} lines; read the manifest and the files above for the rest.")
    return "\n".join(kept) + "\n"
