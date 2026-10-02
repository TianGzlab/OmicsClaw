"""Shared helpers for the step-runner tests: a project factory and an in-process runner."""

from __future__ import annotations

import io
import os
import textwrap
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from skills._sdk.notebook import _acceptance, _executor, _skills
from skills._sdk.notebook._runners import StepOutcome


class InProcessRunner:
    """Runs a step notebook's code cells with ``exec`` in this process.

    It sets the environment and working directory the kernel would get, so
    the step-code functions behave as they do in a kernel, without the cost
    of starting one.
    """

    def __init__(self) -> None:
        self.runs: list[dict] = []

    def run(self, notebook, *, env, cwd):
        import nbformat

        saved_env = dict(os.environ)
        saved_cwd = os.getcwd()
        os.environ.clear()
        os.environ.update(env)
        os.chdir(cwd)
        namespace: dict = {"__name__": "__main__"}
        self.runs.append({"env": dict(env), "cwd": Path(cwd)})
        stream: list[str] = []
        try:
            for number, cell in enumerate(notebook.cells, start=1):
                if cell.cell_type != "code":
                    continue
                buffer = io.StringIO()
                try:
                    with redirect_stdout(buffer), redirect_stderr(buffer):
                        exec(compile(cell.source, f"<cell {number}>", "exec"), namespace)
                except Exception as exc:  # the step's own failure
                    text = buffer.getvalue()
                    stream.append(text)
                    cell.outputs = [nbformat.v4.new_output(
                        "error", ename=type(exc).__name__, evalue=str(exc),
                        traceback=traceback.format_exception(exc),
                    )]
                    return StepOutcome(
                        status="failed", notebook=notebook, seconds=0.01,
                        error={"cell": number, "ename": type(exc).__name__, "evalue": str(exc),
                               "traceback": "".join(traceback.format_exception(exc))},
                        stream="".join(stream),
                    )
                text = buffer.getvalue()
                stream.append(text)
                cell.outputs = [nbformat.v4.new_output("stream", name="stdout", text=text)] if text else []
        finally:
            os.chdir(saved_cwd)
            os.environ.clear()
            os.environ.update(saved_env)
        return StepOutcome(status="ok", notebook=notebook, seconds=0.01, stream="".join(stream))


class Project:
    """A temporary project driven through the step runner's functions."""

    def __init__(self, root: Path, runner: InProcessRunner) -> None:
        self.root = root
        self.runner = runner
        self.lines: list[str] = []

    def out(self, text: str) -> None:
        self.lines.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def new(self, slug: str) -> str:
        code = _executor.new_module(self.root, slug, out=self.out)
        assert code == 0, self.text
        return sorted(p.name for p in (self.root / "analysis").iterdir() if p.name.endswith(slug))[-1]

    def step(self, module: str, name: str, body: str) -> Path:
        path = self.root / "analysis" / module / name
        path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        return path

    def run(self, *targets: str, force: bool = False) -> int:
        self.lines.clear()
        return _executor.run_targets(self.root, list(targets), force=force, runner=self.runner, out=self.out)

    def replay(self, target: str, *, new_interpreter: str | None = None) -> int:
        self.lines.clear()
        return _executor.replay(self.root, target, new_interpreter=new_interpreter, runner=self.runner, out=self.out)

    def accept(self, target: str, *, review: str | None = None, skip_review: str | None = None) -> int:
        self.lines.clear()
        return _acceptance.accept(self.root, target, review=review, skip_review=skip_review, out=self.out)

    def revise(self, target: str) -> int:
        self.lines.clear()
        return _acceptance.revise(self.root, target, out=self.out)

    def manifest(self, module: str) -> dict:
        import json

        return json.loads((self.root / "results" / module / "provenance" / "manifest.json").read_text())

    def status(self, target: str | None = None) -> str:
        self.lines.clear()
        assert _executor.status(self.root, target, out=self.out) == 0
        return self.text


@pytest.fixture
def runner() -> InProcessRunner:
    return InProcessRunner()


@pytest.fixture
def project(tmp_path, runner) -> Project:
    root = tmp_path / "proj"
    root.mkdir()
    return Project(root, runner)


@pytest.fixture
def skills_tree(tmp_path, monkeypatch) -> Path:
    """A skills tree with two skills, made the default tree for load_skill and run_cli."""
    root = tmp_path / "skills"
    clustering = root / "singlecell" / "scrna" / "sc-clustering"
    clustering.mkdir(parents=True)
    (clustering / "SKILL.md").write_text(
        "---\nname: sc-clustering\n---\n\n# sc-clustering\n\n## Dependencies\n\n`json5`, `pytest`\n",
        encoding="utf-8",
    )
    (clustering / "_api.py").write_text(textwrap.dedent('''
        """Toy clustering library."""

        __all__ = ["cluster", "cluster_summary"]


        def cluster(data, *, resolution=1.0, random_state=0):
            """Label every cell."""
            return {**data, "leiden": [str(i % 2) for i in range(len(data["cells"]))]}


        def cluster_summary(data, *, key="leiden"):
            """Count cells per label."""
            counts = {}
            for label in data[key]:
                counts[label] = counts.get(label, 0) + 1
            return counts


        def _helper():
            return 1
    '''), encoding="utf-8")
    (clustering / "sc_cluster.py").write_text(textwrap.dedent('''
        import argparse, json, pathlib, sys
        parser = argparse.ArgumentParser()
        parser.add_argument("--input")
        parser.add_argument("--output", required=True)
        parser.add_argument("--fail", action="store_true")
        args = parser.parse_args()
        out = pathlib.Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps({"input": args.input}))
        (out / "tables").mkdir(exist_ok=True)
        (out / "tables" / "clusters.csv").write_text("cell,label\\na,0\\n")
        print("clustered", args.input)
        sys.exit(3 if args.fail else 0)
    '''), encoding="utf-8")
    cli_only = root / "bulkrna" / "bulkrna-de"
    cli_only.mkdir(parents=True)
    (cli_only / "SKILL.md").write_text("---\nname: bulkrna-de\n---\n", encoding="utf-8")
    (cli_only / "bulkrna_de.py").write_text("print('de')\n", encoding="utf-8")
    monkeypatch.setattr(_skills, "DEFAULT_ROOT", root)
    _skills._INDEX.clear()
    return root
