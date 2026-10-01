"""skill_routing: steps call skills through the step runner, and the ledgers say so.

What these cases test is the path, not the choice of skill: ``use_skill``
resolves the skill, ``bash`` runs ``skills/_sdk/notebook/run.py`` for real,
the step's ``load_skill`` returns a stub module checked against the real
``_api.py``, ``run_cli`` is answered from a recorded run, and the Runner reads
what happened back out of the step ledgers. Whether a model picks the right
skill is for the real-model routing eval.

Each command uses this interpreter, so the kernel has nbclient and ipykernel.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from omicsclaw.evals import (
    NoError,
    ScriptedProvider,
    ScriptedTurn,
    SkillInvoked,
    StubResult,
    ToolArgs,
    tool_call,
)
from skills._sdk.report import DISCLAIMER

from ._checks import CountIs, ToolResultContains, user_changes
from ._harness import check, seed

REPO = Path(__file__).resolve().parents[3]
RUNNER = REPO / "skills" / "_sdk" / "notebook" / "run.py"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
STUB_MODULES = FIXTURES / "skill_stubs"
SKILL_CASE_TIMEOUT_S = 90.0
"""Each runner call starts a kernel per step; CI takes 2 to 5 s for each."""

CELLS = json.dumps({"cells": ["c1", "c2", "c3", "c4"]})
BULK_OUTPUT_LINE = "DE genes: 100 (up=50, down=50)"


def runner(*args: str) -> str:
    return " ".join([sys.executable, str(RUNNER), *args])


def bash(*args: str) -> ScriptedTurn:
    return ScriptedTurn(tool_calls=(tool_call("bash", {"command": runner(*args)}),))


def write(path: str, content: str) -> ScriptedTurn:
    return ScriptedTurn(tool_calls=(tool_call("write_file", {"path": path, "content": content}),))


def cluster_step(resolution: str = "1.0", source: str = "data/cells.json") -> str:
    return (
        "# %% [markdown]\n"
        "# Cluster the cells with sc-clustering.\n"
        f"# Reads {source}.\n"
        "# Calls sc-clustering: cluster, cluster_summary.\n"
        "\n"
        "# %%\n"
        "from skills._sdk.notebook import load_skill, read_input, write_output\n"
        "\n"
        'clustering = load_skill("sc-clustering")\n'
        f'cells = read_input("{source}")\n'
        f"labelled = clustering.cluster(cells, resolution={resolution})\n"
        'write_output(clustering.cluster_summary(labelled), "tables/clusters.json")\n'
    )


def qc_step(species: str = "human") -> str:
    return (
        "# %% [markdown]\n"
        "# QC of the cells with sc-qc.\n"
        "# Reads data/cells.json.\n"
        "# Calls sc-qc: calculate_qc, qc_summary.\n"
        "\n"
        "# %%\n"
        "from skills._sdk.notebook import load_skill, read_input, write_output\n"
        "\n"
        'qc = load_skill("sc-qc")\n'
        'cells = qc.calculate_qc(read_input("data/cells.json"), species="' + species + '")\n'
        'write_output(cells, "intermediate/cells.json")\n'
        'write_output(qc.qc_summary(cells), "tables/qc_summary.json")\n'
    )


VALIDATE_STEP = (
    "# %% [markdown]\n"
    "# Check the cluster table the report relies on.\n"
    "\n"
    "# %%\n"
    "from skills._sdk.notebook import read_input\n"
    "\n"
    'counts = read_input("results/01_clustering/tables/clusters.json")\n'
    "assert sum(counts.values()) == 4\n"
)

REPORT = (
    "# Module 01_clustering\n\n"
    "Four cells in two clusters of two (tables/clusters.json).\n\n"
    f"{DISCLAIMER}\n"
)
REVIEW = "VERDICT: APPROVE\n\nNo findings: the steps, the validate step and the report agree."
REVIEW_FILE = f"results/01_clustering/reviews/{date.today().isoformat()}_review.md"


def _stub_modules(*skills: str) -> dict[str, Path]:
    return {skill: STUB_MODULES / f"{skill}.py" for skill in skills}


def _ledgers(result, step: str, module: str = "01_clustering") -> list[Path]:
    return sorted((result.workspace / "results" / module / "provenance" / "runs" / step).glob("*.jsonl"))


def _manifest(result, module: str = "01_clustering") -> dict:
    path = result.workspace / "results" / module / "provenance" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _created(result, path: str) -> int:
    return user_changes(result).count(("created", path))


def _provider(*turns: ScriptedTurn):
    return lambda: ScriptedProvider(*turns)


def _skill_case(case_id: str, prompt: str, provider, *assertions, **fields):
    fields.setdefault("files", {"data/cells.json": CELLS})
    return seed(case_id, prompt, provider, *assertions, **fields)


CASES = [
    _skill_case(
        "skill_routing/step_calls_a_skill_function",
        "Cluster the cells in data/cells.json.",
        _provider(
            ScriptedTurn(tool_calls=(tool_call("use_skill", {"skill_name": "sc-clustering"}),)),
            bash("new", "clustering"),
            write("analysis/01_clustering/01_cluster.py", cluster_step()),
            bash("run", "analysis/01_clustering"),
            ScriptedTurn(text="The clustering step ran; its table is results/01_clustering/tables/clusters.json."),
        ),
        SkillInvoked("sc-clustering", domain="singlecell", function="cluster"),
        ToolResultContains("bash", "01_cluster.py  ok"),
        CountIs("created the step notebook",
                lambda r: _created(r, "results/01_clustering/notebooks/01_cluster.ipynb"), 1),
        CountIs("created the manifest",
                lambda r: _created(r, "results/01_clustering/provenance/manifest.json"), 1),
        NoError(),
        skill_modules=_stub_modules("sc-clustering"),
    ),
    _skill_case(
        "skill_routing/first_module_builds_the_skeleton",
        "Start a clustering module.",
        _provider(
            bash("new", "clustering"),
            ScriptedTurn(text="Module 01_clustering is ready."),
        ),
        CountIs("preset files modified or deleted",
                lambda r: sum(1 for kind, path in user_changes(r)
                              if kind != "created" and path in {"notes.txt", "data/cells.json", "scripts/mine.sh"}), 0),
        CountIs("created the module README", lambda r: _created(r, "analysis/01_clustering/README.md"), 1),
        CountIs("created STRATEGY.md", lambda r: _created(r, "docs/analysis_strategy/STRATEGY.md"), 1),
        CountIs("PROJECT.md or METHODS_LEDGER.md at the root",
                lambda r: sum((r.workspace / name).exists() for name in ("PROJECT.md", "METHODS_LEDGER.md")), 0),
        NoError(),
        files={"notes.txt": "my notes\n", "data/cells.json": CELLS, "scripts/mine.sh": "echo mine\n"},
    ),
    _skill_case(
        "skill_routing/unchanged_step_is_skipped",
        "Cluster the cells, then run the module again.",
        _provider(
            bash("new", "clustering"),
            write("analysis/01_clustering/01_cluster.py", cluster_step()),
            bash("run", "analysis/01_clustering"),
            bash("run", "analysis/01_clustering"),
            ScriptedTurn(text="The second run had nothing to do."),
        ),
        ToolResultContains("bash", "01_cluster.py  up to date"),
        CountIs("ledger files of 01_cluster", lambda r: len(_ledgers(r, "01_cluster")), 1),
        NoError(),
        skill_modules=_stub_modules("sc-clustering"),
    ),
    _skill_case(
        "skill_routing/edited_step_reruns",
        "Cluster the cells at resolution 1.0, then at 0.5.",
        _provider(
            bash("new", "clustering"),
            write("analysis/01_clustering/01_cluster.py", cluster_step("1.0")),
            bash("run", "analysis/01_clustering"),
            ScriptedTurn(tool_calls=(tool_call("edit_file", {
                "path": "analysis/01_clustering/01_cluster.py",
                "source_text": "resolution=1.0",
                "target_text": "resolution=0.5",
            }),)),
            bash("run", "analysis/01_clustering"),
            ScriptedTurn(text="Reran the step at resolution 0.5."),
        ),
        ToolResultContains("bash", "why:      step changed"),
        CountIs("ledger files of 01_cluster", lambda r: len(_ledgers(r, "01_cluster")), 2),
        CountIs("last cluster call at resolution 0.5",
                lambda r: int([run for run in r.skill_runs if run.function == "cluster"][-1].args.get("resolution") == 0.5), 1),
        NoError(),
        skill_modules=_stub_modules("sc-clustering"),
    ),
    _skill_case(
        "skill_routing/upstream_change_marks_downstream_stale",
        "QC the cells, cluster them, then change the QC species.",
        _provider(
            bash("new", "qc"),
            write("analysis/01_qc/01_qc.py", qc_step("human")),
            bash("run", "analysis/01_qc"),
            bash("new", "clustering"),
            write("analysis/02_clustering/01_cluster.py", cluster_step(source="results/01_qc/intermediate/cells.json")),
            bash("run", "analysis/02_clustering"),
            ScriptedTurn(tool_calls=(tool_call("edit_file", {
                "path": "analysis/01_qc/01_qc.py",
                "source_text": 'species="human"',
                "target_text": 'species="mouse"',
            }),)),
            bash("run", "analysis/01_qc"),
            bash("status"),
            ScriptedTurn(text="02_clustering is stale now."),
        ),
        ToolResultContains("bash", "01_cluster.py  stale: input changed: results/01_qc/intermediate/cells.json"),
        SkillInvoked("sc-qc", domain="singlecell", function="calculate_qc"),
        NoError(),
        skill_modules=_stub_modules("sc-qc", "sc-clustering"),
    ),
    _skill_case(
        "skill_routing/replay_runs_every_step_and_validate",
        "Cluster the cells and replay the module.",
        _provider(
            bash("new", "clustering"),
            write("analysis/01_clustering/01_cluster.py", cluster_step()),
            write("analysis/01_clustering/02_validate.py", VALIDATE_STEP),
            bash("replay", "analysis/01_clustering"),
            ScriptedTurn(text="The replay succeeded."),
        ),
        CountIs("manifest replay ok", lambda r: int((_manifest(r).get("replay") or {}).get("status") == "ok"), 1),
        CountIs("manifest status replayed", lambda r: int(_manifest(r).get("status") == "replayed"), 1),
        CountIs("step sections in the module notebook",
                lambda r: (r.workspace / "results/01_clustering/notebooks/M01_clustering.ipynb")
                .read_text(encoding="utf-8").count("## Step "), 2),
        NoError(),
        skill_modules=_stub_modules("sc-clustering"),
    ),
    _skill_case(
        "skill_routing/review_then_accept",
        "Cluster the cells and finish the module.",
        _provider(
            bash("new", "clustering"),
            write("analysis/01_clustering/01_cluster.py", cluster_step()),
            write("analysis/01_clustering/02_validate.py", VALIDATE_STEP),
            bash("replay", "analysis/01_clustering"),
            write("results/01_clustering/M01_clustering_REPORT.md", REPORT),
            ScriptedTurn(tool_calls=(tool_call("task", {
                "subagent_type": "module-reviewer",
                "prompt": "Review module 01_clustering",
                "description": "review the module",
            }),)),
            ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "results/01_clustering/provenance/manifest.json"}),)),
            ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "results/01_clustering/M01_clustering_REPORT.md"}),)),
            ScriptedTurn(text=REVIEW),
            write(REVIEW_FILE, REVIEW + "\n"),
            ScriptedTurn(text="The report is ready and the reviewer approved it. Do you accept the module?"),
            bash("accept", "analysis/01_clustering", "--review", REVIEW_FILE),
            bash("status"),
            ScriptedTurn(text="Module 01_clustering is accepted."),
        ),
        ToolArgs("task", {"subagent_type": "module-reviewer"}),
        CountIs("manifest frozen and accepted",
                lambda r: int(_manifest(r).get("frozen") is True and _manifest(r).get("status") == "accepted"), 1),
        ToolResultContains("bash", "01_clustering  ACCEPTED"),
        NoError(),
        followups=("Yes, accept it.",),
        skill_modules=_stub_modules("sc-clustering"),
    ),
    _skill_case(
        "skill_routing/cli_skill_from_a_step",
        "Run differential expression on data/counts.csv.",
        _provider(
            bash("new", "de"),
            write(
                "analysis/01_de/01_bulk_de.py",
                "# %% [markdown]\n"
                "# Bulk DE with bulkrna-de's CLI; it has no function library yet.\n"
                "# Reads data/counts.csv.\n"
                "# Calls bulkrna-de (CLI).\n"
                "\n"
                "# %%\n"
                "from skills._sdk.notebook import run_cli\n"
                "\n"
                'run_cli("bulkrna-de", "--input", "data/counts.csv", inputs=["data/counts.csv"])\n',
            ),
            bash("run", "analysis/01_de"),
            ScriptedTurn(text="Differential expression finished."),
        ),
        SkillInvoked("bulkrna-de", domain="bulkrna"),
        CountIs("created result.json",
                lambda r: _created(r, "results/01_de/intermediate/bulkrna-de/result.json"), 1),
        CountIs("result.json in the step's outputs",
                lambda r: sum(o["path"] == "intermediate/bulkrna-de/result.json"
                              for o in _manifest(r, "01_de")["steps"][0]["outputs"]), 1),
        ToolResultContains("bash", BULK_OUTPUT_LINE),
        NoError(),
        files={"data/counts.csv": "gene,c1,t1\ng1,1,2\n"},
        skill_stubs={"bulkrna-de": StubResult.load(FIXTURES / "skill_runs" / "bulkrna-de.json")},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results, timeout_s=SKILL_CASE_TIMEOUT_S)
