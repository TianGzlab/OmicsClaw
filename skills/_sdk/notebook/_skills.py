"""Loading a skill's function library, and running a skill's CLI, from a step.

A skill is a directory holding ``SKILL.md``, found by name under a skills
tree; its function library is the ``_api.py`` beside it. Inside a step run
(``OMICSCLAW_STEP_LEDGER`` set) every call to a public function is
recorded, and with ``OMICSCLAW_SKILL_STUBS`` set a stub module from that
folder stands in for the real library after its names are checked against
the real ``_api.py`` by AST.
"""

from __future__ import annotations

import ast
import difflib
import functools
import importlib.metadata
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import time
import types
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from skills._sdk.notebook import _hashing, _ledger
from skills._sdk.notebook._io import StepContext, record_input, step_context
from skills._sdk.notebook.contract import ENVIRONMENT, LAYOUT

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
"""The skills tree that holds this ``_sdk``."""

_SKIPPED = {"__pycache__", "node_modules"}
_INDEX: dict[Path, dict[str, list[Path]]] = {}
_LOADED: dict[tuple[str, Path, bool], types.ModuleType] = {}
_RECORDED_LOADS: set[tuple[str, str, str]] = set()


def _snake(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]", "_", name)


def _index(root: Path) -> dict[str, list[Path]]:
    cached = _INDEX.get(root)
    if cached is not None:
        return cached
    found: dict[str, list[Path]] = {}
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _SKIPPED and not d.startswith((".", "_")))
        if "SKILL.md" in files:
            path = Path(current)
            found.setdefault(path.name, []).append(path)
    _INDEX[root] = found
    return found


def _resolve_root(root: str | os.PathLike | None) -> Path:
    if root is None:
        return DEFAULT_ROOT
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise LookupError(f"skills root {root} is not a directory")
    return path


def skill_dir(name: str, root: str | os.PathLike | None = None) -> Path:
    """The directory of the skill named *name* under *root*.

    :raises LookupError: no skill or more than one has that name.
    """
    base = _resolve_root(root)
    index = _index(base)
    matches = index.get(name, [])
    if not matches:
        close = difflib.get_close_matches(name, list(index), n=3)
        hint = f"; closest: {', '.join(close)}" if close else ""
        raise LookupError(f"no skill named {name!r} under {base}{hint}")
    if len(matches) > 1:
        raise LookupError(f"more than one skill named {name!r}: " + ", ".join(str(p) for p in matches))
    return matches[0]


def candidate_name(root: Path) -> str | None:
    """The candidate's name for a skills tree other than the default, else ``None``."""
    if root == DEFAULT_ROOT:
        return None
    return root.parent.name if root.name == "skills" else root.name


def _git(skill_path: Path, root: Path) -> dict | None:
    domain = skill_path.relative_to(root).parts[0] if skill_path != root else ""
    watched = [str(skill_path), str(root / domain / "_lib"), str(root / "_sdk")]
    try:
        commit = subprocess.run(
            ["git", "-C", str(skill_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if commit.returncode != 0:
            return None
        status = subprocess.run(
            ["git", "-C", str(skill_path), "status", "--porcelain", "--", *watched],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return {"commit": commit.stdout.strip(), "dirty": bool(status.stdout.strip())}


def _dependency_names(skill_path: Path) -> list[str]:
    try:
        lines = (skill_path / "SKILL.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    start = next((i for i, line in enumerate(lines) if line.strip() == "## Dependencies"), None)
    if start is None:
        return []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if re.fullmatch(r"\s*`[A-Za-z0-9._-]+`(\s*,\s*`[A-Za-z0-9._-]+`)*\s*", line):
            return re.findall(r"`([^`]+)`", line)
    return []


def _installed_versions(names: Sequence[str]) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _record_load(ctx: StepContext, name: str, path: Path, root: Path, *, stub: bool) -> None:
    if ctx.ledger is None:
        return
    key = (str(ctx.ledger.path), name, str(root))
    if key in _RECORDED_LOADS:
        return
    _RECORDED_LOADS.add(key)
    ctx.ledger.append(
        "skill_load",
        skill=name,
        root=str(root),
        candidate=candidate_name(root),
        git=_git(path, root),
        content_sha256=_hashing.sha256_path(path),
        dependencies=_installed_versions(_dependency_names(path)),
        stub=stub,
    )


def public_names(path: Path) -> tuple[list[str], set[str]]:
    """``__all__`` and the top-level function names of a Python file, read with ``ast``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    declared: list[str] = []
    functions: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets) and node.value is not None:
            declared = [str(v) for v in ast.literal_eval(node.value)]
    return declared, functions


def _stub_names(path: Path) -> list[str]:
    declared, functions = public_names(path)
    return declared or sorted(n for n in functions if not n.startswith("_"))


def _import_file(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise LookupError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


def _proxy(name: str, library: types.ModuleType, ctx: StepContext, *, stub: bool) -> types.ModuleType:
    exported = list(getattr(library, "__all__", []))
    proxy = types.ModuleType(f"skill:{name}", getattr(library, "__doc__", None))
    proxy.__file__ = getattr(library, "__file__", None)

    def wrap(function_name: str, function: Any) -> Any:
        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError):
            signature = None

        @functools.wraps(function)
        def recorded(*args: Any, **kwargs: Any) -> Any:
            arguments: dict[str, Any] = {}
            if signature is not None:
                try:
                    bound = signature.bind(*args, **kwargs)
                    arguments = dict(bound.arguments)
                except TypeError:
                    arguments = {}
            started = time.perf_counter()
            error: str | None = None
            try:
                return function(*args, **kwargs)
            except BaseException as exc:
                error = f"{type(exc).__name__}: {exc}"[:300]
                raise
            finally:
                if ctx.ledger is not None:
                    fields: dict[str, Any] = {
                        "skill": name,
                        "function": function_name,
                        "args": _ledger.summarize_args(arguments),
                        "seconds": round(time.perf_counter() - started, 3),
                        "stub": stub,
                    }
                    if error is not None:
                        fields["error"] = error
                    ctx.ledger.append("skill_call", **fields)

        return recorded

    for export in exported:
        value = getattr(library, export)
        setattr(proxy, export, wrap(export, value) if callable(value) else value)
    proxy.__all__ = exported

    def __getattr__(attribute: str) -> Any:
        if attribute.startswith("__"):
            raise AttributeError(attribute)
        raise AttributeError(
            f"skill {name!r} has no function {attribute!r}; available: {', '.join(exported) or 'none'}"
        )

    proxy.__getattr__ = __getattr__  # type: ignore[attr-defined]
    proxy.__dir__ = lambda: list(exported)  # type: ignore[attr-defined]
    return proxy


def _stub_dir(ctx: StepContext) -> Path | None:
    if ctx.ledger is None:
        return None
    raw = os.environ.get(ENVIRONMENT["skill_stubs"], "").strip()
    return Path(raw) if raw else None


def _missing(ctx: StepContext, name: str, names: list[str], reason: str) -> LookupError:
    if ctx.ledger is not None:
        ctx.ledger.append("stub_target_missing", skill=name, names=names, reason=reason)
    return LookupError(f"stub for {name!r} does not match the skill: {reason}" + (f" ({', '.join(names)})" if names else ""))


def load_skill(name: str, *, root: str | os.PathLike | None = None) -> types.ModuleType:
    """Return skill `name`'s function library.

    The skill is the directory named `name` that holds a SKILL.md; its
    library is the _api.py beside it. The returned module exposes the names
    in the library's __all__, which the ## API section of the SKILL.md
    lists; another name raises AttributeError naming them. Inside a step
    run every call is recorded with its arguments. `root` is a skills tree;
    None is the tree that contains this _sdk.

    :raises LookupError: no such skill; the skill has no function library
        yet (run its CLI with run_cli); or a stub does not match the real
        library.
    """
    ctx = step_context(notice=False)
    base = _resolve_root(root)
    path = skill_dir(name, base)
    api = path / "_api.py"
    stubs = _stub_dir(ctx)
    stub_file = stubs / f"{name}.py" if stubs is not None else None
    if stub_file is not None and stub_file.is_file():
        if not api.is_file():
            raise _missing(ctx, name, [], f"{name} has no _api.py")
        declared, _functions = public_names(api)
        absent = [n for n in _stub_names(stub_file) if n not in declared]
        if absent:
            raise _missing(ctx, name, absent, "not in the real _api.py's __all__")
        library = _LOADED.get((name, stub_file, True)) or _import_file(f"skill_stub__{_snake(name)}", stub_file)
        _LOADED[(name, stub_file, True)] = library
        if not hasattr(library, "__all__"):
            library.__all__ = _stub_names(stub_file)  # type: ignore[attr-defined]
        _record_load(ctx, name, path, base, stub=True)
        return _proxy(name, library, ctx, stub=True)
    if not api.is_file():
        raise LookupError(f"{name} has no function library yet; run its CLI from a step with run_cli(...)")
    key = (name, api, False)
    library = _LOADED.get(key)
    if library is None:
        suffix = "" if base == DEFAULT_ROOT else f"__{_hashing.sha256_file(api)[:8]}"
        library = _import_file(f"skill_api__{_snake(name)}{suffix}", api)
        _LOADED[key] = library
    _record_load(ctx, name, path, base, stub=False)
    return _proxy(name, library, ctx, stub=False)


def main_script(path: Path) -> Path:
    """The one CLI script of a skill: the ``*.py`` file in its directory not starting with ``_``."""
    scripts = sorted(p for p in path.glob("*.py") if not p.name.startswith("_"))
    if len(scripts) != 1:
        found = ", ".join(p.name for p in scripts) or "none"
        raise LookupError(f"{path.name} should have exactly one CLI script; found {found}")
    return scripts[0]


def _output_arg(args: list[str]) -> tuple[int, str] | None:
    for i, arg in enumerate(args):
        if arg in {"--output", "-o"} and i + 1 < len(args):
            return i + 1, args[i + 1]
        if arg.startswith("--output="):
            return i, arg.split("=", 1)[1]
    return None


def _record_outputs(ctx: StepContext, output_dir: Path) -> None:
    if ctx.ledger is None or ctx.module is None or not output_dir.is_dir():
        return
    for file in _hashing.directory_files(output_dir):
        ctx.ledger.append(
            "output",
            path=file.relative_to(ctx.module.results_dir).as_posix(),
            sha256=_hashing.sha256_file(file),
            bytes=file.stat().st_size,
            kind="intermediate",
        )


def _write_stub_result(stub: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for relative, content in dict(stub.get("files", {})).items():
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content).replace("{output}", str(output_dir)), encoding="utf-8")
    for relative in stub.get("binary_files", []):
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")


def run_cli(skill: str, *args: str, inputs: Sequence[str] = (),
            timeout: float | None = None) -> Path:
    """Run a skill's command-line script for the current step and return its output directory.

    The script is the one *.py file in the skill's directory whose name does
    not start with _, run with this interpreter from the project root.
    Without --output in args the output goes to
    results/<NN_slug>/intermediate/<skill>/; a given --output must name a
    folder inside this module's figures/, tables/, intermediate/ or logs/.
    `inputs` lists the project-relative files the run reads, so they count
    towards staleness. The script's output is printed and saved to
    results/<NN_slug>/logs/<step>__<skill>.log; every file in the output
    directory is recorded as an output of the step. `timeout` is in seconds.

    :raises LookupError: no such skill, or it does not have exactly one script.
    :raises ValueError: --output is not a folder inside one of those four.
    :raises FileNotFoundError: an entry of `inputs` does not exist.
    :raises RuntimeError: the script exits non-zero; the message ends with
        the end of its log.
    """
    ctx = step_context()
    module = ctx.require_module("run a skill's CLI")
    assert ctx.root is not None
    path = skill_dir(skill)
    argv = [str(a) for a in args]
    found = _output_arg(argv)
    if found is None:
        output_dir = module.results_dir / "intermediate" / skill
        argv += ["--output", str(output_dir)]
    else:
        given = Path(found[1])
        output_dir = Path(os.path.abspath(given if given.is_absolute() else ctx.root / given))
        try:
            parts = output_dir.relative_to(module.results_dir).parts
        except ValueError:
            raise ValueError(
                f"--output {found[1]} is outside results/{module.name}/; "
                f"leave --output out to use results/{module.name}/intermediate/{skill}/"
            ) from None
        if len(parts) < 2 or parts[0] not in LAYOUT["output_dirs"]:
            folders = ", ".join(f"{name}/" for name in LAYOUT["output_dirs"])
            raise ValueError(
                f"--output {found[1]} must be a folder inside one of {folders} under results/{module.name}/, "
                f"for example results/{module.name}/intermediate/{skill}/"
            )
    for item in inputs:
        target = Path(item) if Path(item).is_absolute() else ctx.root / item
        if not target.exists():
            raise FileNotFoundError(f"input {item} does not exist")
        record_input(ctx, target, via="run_cli")
    step_stem = ctx.step_file.stem if ctx.step_file is not None else "step"
    log_path = module.results_dir / "logs" / f"{step_stem}__{skill}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    stubs = _stub_dir(ctx)
    stub_file = stubs / f"{skill}.json" if stubs is not None else None
    if stub_file is not None and stub_file.is_file():
        script_names = sorted(p.name for p in path.glob("*.py") if not p.name.startswith("_"))
        if len(script_names) != 1:
            raise _missing(ctx, skill, script_names, "the skill has no single CLI script")
        stub = json.loads(stub_file.read_text(encoding="utf-8"))
        _write_stub_result(stub, output_dir)
        text = str(stub.get("stdout", "")).replace("{output}", str(output_dir))
        exit_code = int(stub.get("exit_code", 0))
        log_path.write_text(text, encoding="utf-8")
        print(text, end="" if text.endswith("\n") else "\n")
        script = path / script_names[0]
        is_stub = True
    else:
        script = main_script(path)
        env = {k: v for k, v in os.environ.items()
               if k not in {ENVIRONMENT["step_file"], ENVIRONMENT["step_ledger"], ENVIRONMENT["skill_stubs"]}}
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        tail: list[str] = []
        with open(log_path, "w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, str(script), *argv], cwd=ctx.root, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
            )
            assert process.stdout is not None
            timer = threading.Timer(timeout, process.kill) if timeout else None
            if timer is not None:
                timer.start()
            try:
                for line in process.stdout:
                    log.write(line)
                    print(line, end="")
                    tail.append(line)
                    del tail[:-40]
                exit_code = process.wait()
            finally:
                if timer is not None:
                    timer.cancel()
        text = "".join(tail)
        is_stub = False
    seconds = round(time.perf_counter() - started, 3)
    if ctx.ledger is not None:
        ctx.ledger.append(
            "skill_cli",
            skill=skill,
            script=str(script),
            argv=argv,
            exit_code=exit_code,
            output_dir=output_dir.relative_to(module.results_dir).as_posix(),
            seconds=seconds,
            stub=is_stub,
        )
    if exit_code != 0:
        raise RuntimeError(
            f"{skill} exited with status {exit_code}; log: {log_path}\n" + text[-2000:]
        )
    _record_outputs(ctx, output_dir)
    return output_dir
