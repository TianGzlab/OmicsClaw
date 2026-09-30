"""skill_routing: use_skill resolves a skill, bash runs its script, the stub answers.

What these cases test is the path, not the choice of skill: the skill is
in the index, ``use_skill`` returns its directory, the ``bash`` command
running its script passes the permission gate and the hooks and is
answered by the stub layer, the script file still exists, and the
domain comes back from the index. Whether a model picks the right skill
is for the real-model routing eval, which will start from the same seed
file the prompts come from.

Each input file is deliberately missing: if the stub stops answering,
the real script fails fast on its input instead of running an analysis.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omicsclaw.evals import (
    MaxToolCalls,
    NoError,
    ScriptedProvider,
    ScriptedTurn,
    SkillInvoked,
    StubResult,
    ToolArgs,
    tool_call,
)
from omicsclaw.evals.runner import skill_index

from ._checks import CountIs, ToolResultContains, user_changes
from ._harness import check, seed

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SEEDS = {
    case["id"]: case
    for case in json.loads((FIXTURES / "live_routing_seed.json").read_text(encoding="utf-8"))["cases"]
}

# (seed id, skill, domain, script, input, a line of the recorded stdout)
ROUTES = (
    ("spatial__preprocess_visium", "spatial-preprocess", "spatial", "spatial_preprocess.py",
     "data/visium.h5ad", "Preprocessing complete: 200 cells, 3 clusters"),
    ("singlecell__cluster_leiden", "sc-clustering", "singlecell", "sc_cluster.py",
     "data/pbmc.h5ad", "Running Leiden clustering (resolution=1.00, key=leiden)"),
    ("bulkrna__deseq2", "bulkrna-de", "bulkrna", "bulkrna_de.py",
     "data/counts.csv", "DE genes: 100 (up=50, down=50)"),
    ("genomics__small_variants", "genomics-variant-calling", "genomics", "genomics_variant_calling.py",
     "data/sample.bam", "Variant calling complete: 500 variants (453 SNPs, Ti/Tv=2.10)"),
    ("proteomics__lfq_quantification", "proteomics-quantification", "proteomics",
     "proteomics_quantification.py", "data/peptides.tsv", "Quantification complete: 99 proteins (lfq)"),
    ("metabolomics__two_group_de", "metabolomics-de", "metabolomics", "met_diff.py",
     "data/features.csv", "Differential analysis complete: 0 significant features (FDR<0.05)"),
    ("literature__geo_accessions", "literature", "literature", "literature_parse.py",
     "data/paper.pdf", "Found 1 GEO datasets: GSE123456"),
)


def _stub(skill: str) -> StubResult:
    return StubResult.load(FIXTURES / "skill_runs" / f"{skill}.json")


def _command(skill: str, script: str, input_path: str, output: str) -> str:
    directory = skill_index().get(skill).directory
    return f"python {directory / script} --input {input_path} --output {output}"


def _route(skill: str, script: str, input_path: str, *, read_result: bool = False):
    def provider() -> ScriptedProvider:
        turns = [
            ScriptedTurn(tool_calls=(tool_call("use_skill", {"skill_name": skill}),)),
            ScriptedTurn(
                tool_calls=(tool_call("bash", {"command": _command(skill, script, input_path, "out/pp")}),)
            ),
        ]
        if read_result:
            turns.append(ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "out/pp/result.json"}),)))
        turns.append(ScriptedTurn(text=f"{skill} finished; the report is in out/pp."))
        return ScriptedProvider(*turns)

    return provider


def _routing_case(seed_id, skill, domain, script, input_path, line):
    return seed(
        f"skill_routing/{domain}",
        SEEDS[seed_id]["query"],
        _route(skill, script, input_path),
        ToolArgs("use_skill", {"skill_name": skill}),
        SkillInvoked(skill, domain=domain),
        ToolResultContains("use_skill", "Skill directory:"),
        ToolResultContains("bash", line),
        MaxToolCalls(3),
        NoError(),
        skill_stubs={skill: _stub(skill)},
    )


CASES = [_routing_case(*route) for route in ROUTES]

_first = ROUTES[0]
CASES.append(
    seed(
        "skill_routing/output_lands_on_disk",
        SEEDS[_first[0]]["query"],
        _route(_first[1], _first[3], _first[4], read_result=True),
        SkillInvoked(_first[1]),
        ToolResultContains("read_file", '"input_checksum"'),
        CountIs("created out/pp/result.json", lambda r: user_changes(r).count(("created", "out/pp/result.json")), 1),
        NoError(),
        skill_stubs={_first[1]: _stub(_first[1])},
    )
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results)
