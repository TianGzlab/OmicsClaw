# HCA Asia 2026 Poster Abstract — OmicsClaw

> Target: 2026 Human Cell Atlas Asia Meeting (Fremantle, Perth, 2–4 November 2026).
> Poster abstract deadline: **13 September 2026**. Submission: PDF following the
> official template (presenter name + headshot, title 14 pt bold centred,
> authors/affiliations, abstract ≤ 200 words in 11 pt Times New Roman), sent via
> registration modification or to asia-meetings@humancellatlas.org.
> Suggested themes: Computational biology; A.I.

---

## Submission text

**Presenter:** `[PRESENTER NAME]` (+ headshot, 1.5″ × 1″)

**Title:** OmicsClaw: an auditable, local-first AI agent for single-cell and spatial omics analysis

**Authors:** Weige Zhou¹, Liying Chen¹, Pengfei Yin¹, Luyi Tian¹\*

¹`[Institution, Department, Mailing address]`, `[corresponding-author email]`
\* Corresponding author

**Abstract**

Cell atlas studies chain many tools whose method and parameter choices shape biological conclusions. Large language model (LLM) agents could make such workflows accessible, but free-form generated code is hard to audit, and donor-derived data often cannot leave institutional infrastructure. We present OmicsClaw, an open-source agent that maps natural-language requests to 93 script-backed skills across six omics domains (53 for single-cell or spatial data), wrapping established methods including CellTypist, scVI, Harmony, cell2location, RCTD, BANKSY and LIANA. The LLM selects and parameterizes skills, which run on user-controlled machines. By design, the LLM sees metadata and summaries rather than expression matrices; locally hosted LLMs are supported. Unmatched requests fall back to a bounded code agent gated on a fresh-process rerun. Each successful skill run is checked against its declared outputs and records skill revision, input checksums, parameters and environment fingerprint for replay. Raising a skill's validation level requires version-specific evidence and human approval. Spatial domain calls from multiple methods can be merged deterministically. In a skill-only pilot (no LLM) on 2 of 44 OmicBench and 1 of 50 scAgentBench tasks, sc-preprocessing passed all grader checks and sc-pseudotime reproduced the reference trajectory graph (edge F1 = 1.0). Agent-level evaluation is ongoing.

---

## Claim → evidence map (not for submission)

| Claim in abstract | Evidence in repository |
|---|---|
| 93 skills across six omics domains; 53 single-cell or spatial (96 total incl. orchestration + literature) | `skills/catalog.json` (`skill_count: 96`); README §Domains: 19 + 34 + 10 + 8 + 8 + 14 = 93; spatial 19 + single-cell 34 = 53 |
| Script-backed | `skills/catalog.json` `has_script` |
| Wraps CellTypist, scVI, Harmony, cell2location, RCTD, BANKSY, LIANA | `interface.parameters.hints` in `sc-cell-annotation`, `sc-batch-integration`, `spatial-deconv`, `spatial-domains`, `spatial-communication` `skill.yaml`; implementations in `skills/singlecell/_lib/{annotation,integration}.py`, `skills/spatial/_lib/{deconvolution,domains,communication}.py` |
| Open-source | Apache-2.0 `LICENSE` (note: `pyproject.toml:15` still says MIT — fix before the poster) |
| Skills run on user-controlled machines (local or SSH remote) | README §Interfaces / Remote mode; `docs/safety/data-privacy.mdx` |
| *By design* the LLM sees metadata and summaries, not expression matrices (intent, not enforcement) | `inspect_data` returns AnnData metadata only; README FAQ ("should receive"); caveat: `file_read` / `inspect_file` can return text-file content (`omicsclaw/runtime/tools/builders/engineering.py:601-648`, `agent_executors.py`) |
| Locally hosted LLMs supported | Ollama provider in `omicsclaw/providers/registry.py`; ADR 0026 |
| Bounded code agent gated on a fresh-process rerun | README §Autonomous Analysis Path; ADR 0032; `omicsclaw/autonomous/replay.py:94-183`, `mini_agent_runner.py` (`accepted = outcome.succeeded and replay_ok`). Caveat: the rerun must complete and call `ReturnAnswer`, but its answer/artifacts are **not compared** with the original run (the `validate_replay` docstring overstates this) |
| Successful runs checked against declared outputs | ADR 0065 (result envelope, required keys, declared artifacts, method-scoped files, AnnData readability where declared) |
| Revision, input checksums, parameters, environment fingerprint recorded for replay | ADR 0075; `omicsclaw/skill/execution/reproducibility.py` (per-file SHA-256 / tree digest; environment identity marked `evidence-only`) |
| Validation level raise needs version-specific evidence + human approval | ADR 0066; README (Golden Skill lifecycle slice: "The Agent cannot approve it") |
| Spatial domain calls from multiple methods merged deterministically | `omicsclaw/runtime/consensus/sources.py` (`consensus-domains`, member `spatial-domains`); `docs/design/consensus.md` §1, §4 |
| Skill-only pilot, 2/44 OmicBench tasks (A02 4/4, A03 3/3 by `sc-preprocessing`) and 1/50 scAgentBench tasks | `docs/evaluation/muse-three-suite-skill-lifecycle-benchmark.md` §2, §3.1; `scripts/run_three_suite_skill_lifecycle_benchmark.py` |
| `sc-pseudotime` PAGA graph: edge F1 = 1.0 at 0.03 (aligned cosine 0.99999840; relative Frobenius error 0.0033) — OmicsClaw conformance gate, not an official suite score | same document §3.2 |

## Known limitations deliberately not overclaimed

- Benchmark coverage is partial: OmicBench 2/44, scAgentBench main 1/50, BiomniBench-DA 1/50 (deterministic preflight only, no official LLM-judge score). No LLM/agent was in the loop; no `no_skill / curated_skill / self_created_skill` comparison has been run.
- The scAgentBench adapter reproduced the suite's Paul15 (mouse) preprocessing and root cell, so agreement tests skill conformance, not autonomous analysis. The suite's published all-row-pairs cosine was 0.1086 (gold vs. gold gives the same value).
- 94/96 skills are currently at `smoke-only` validation; 2 are `demo-validated`. ADR 0074 is still Proposed.
- Data locality is a design property, not an enforced boundary: agent tools can return text-file content and code-agent output to a remote LLM endpoint. Only a locally hosted LLM keeps all content on site.
- The code-agent replay gate checks that accepted cells rerun successfully in a fresh kernel; it does not compare results.
- No quantitative consensus-vs-single-method result (e.g. DLPFC 151673) has been recorded; `sc-consensus-clustering` is a resolution sweep, not multi-method.
- Omitted as too preliminary: the run-derived `bulkrna-cosinor-rhythm` replay (synthetic 5-gene × 12-sample input, deterministic OLS) and the Slide-seq V2 consensus-interpret case study (mouse, single LLM run, 37-row marker scaffold).

## Review log

- **v1** (195 words) → independent agent review: **major revisions**. Accepted: soften privacy claim to design intent + local LLM support; restate benchmark as skill-only pilot with denominators; narrow "every run" to successful skill runs; restrict consensus to spatial domains; disclose code-agent fallback; drop cosinor replay result; align title and body; reduce jargon. Spot-checked against `engineering.py` (`file_read`), `consensus/sources.py`, cosinor demo input, `pyproject.toml` license — all confirmed.
- **v2** (211 → trimmed to 198 words) → same reviewer, narrow re-review: **minor revisions**, nothing critical. Accepted: "gated on rerun reproducibility" → "gated on a fresh-process rerun" (verified in `autonomous/replay.py`: no result comparison); split the semicolon sentence; "2/44" reworded so it cannot read as a pass rate; "revision-bound" → "version-specific"; plainer consensus sentence.
- **v3 (final)**: 198 words.

OmicsClaw is a research and educational tool for multi-omics analysis. It is not a medical device and does not provide clinical diagnoses. Consult a domain expert before making decisions based on these results.
