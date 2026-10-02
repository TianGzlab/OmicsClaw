# Consensus Subsystem — Design & Usage

> Removed. Plan 0070 deleted the consensus skills, and `omicsclaw/runtime/`
> and `consensus-interpret` were deleted on 2026-10-02. The tag
> `archive/ensemble-before-removal` keeps the code; this page describes it
> as it was.
>
> Status: reflects the post-**ADR 0016** structure (2026-05-30).
> Vocabulary: [`omicsclaw/runtime/CONTEXT.md`](../../omicsclaw/runtime/CONTEXT.md).
> Decisions: ADR [0010](../adr/0010-consensus-runtime-layer.md) ·
> [0011](../adr/0011-consensus-evaluation-protocol.md) ·
> [0012](../adr/0012-consensus-interpret-evaluation-protocol.md) ·
> [0016](../adr/0016-consensus-as-workflow-runtime.md).

---

## 1. What consensus is

Many bioinformatics tasks (spatial domain detection, single-cell clustering)
have **no single correct method** — BANKSY, GraphST, SEDR, Leiden, SpaGCN all
disagree, and the "right" answer depends on the tissue. OmicsClaw's consensus
subsystem runs **N methods in parallel**, scores them, and merges the best into
**one labeling** — the way a human expert would, but operationalized.

It is lifted from **SACCELERATOR**'s expert-in-the-loop methodology, with one
twist: an **LLM evaluation chair** stands in for the human expert at the
*planning* step, while the *statistical merge* stays pure deterministic math.

There are **two paths**, kept strictly separate (ADR 0010):

| Path | Name | What it does | Output label |
|---|---|---|---|
| **A** | **Typed** consensus | Statistical merge over comparable per-observation labels (Hungarian alignment → mode/LCA/weighted vote). LLM picks members + narrates; never touches the math. | `[A: Verified consensus]` — the only output marked **verified** |
| **B** | **Narrative** consensus | LLM extracts + synthesizes N free-form reports with contradiction annotation. | `[B: Exploratory synthesis — NOT statistical consensus]` |

This document is mostly about the **A path** (the shipped, verified one). The B
path exists as a fallback for skills that have no typed operator.

---

## 2. Architecture — three layers

ADR 0016 splits the subsystem into three layers with a deliberately **thin
waist** at pure topology:

```
┌──────────────────────────────────────────────────────────────────────┐
│ L3  Workflow clients  (one declarative contract per consensus flavour) │
│     skills/.../consensus_domains.py  ── 3-line shim ──┐                 │
│     skills/.../sc_consensus_clustering.py ── shim ────┤                 │
│                                                       ▼                 │
│     omicsclaw/runtime/consensus/sources.py   CONSENSUS_SOURCES          │
│        consensus-domains  → ConsensusSource(reader, planner, template…) │
│        sc-consensus-clustering → ConsensusSource(…)                     │
│     omicsclaw/runtime/consensus/run.py       generic entry             │
├──────────────────────────────────────────────────────────────────────┤
│ L2  Consensus-shared  (everything every consensus flavour reuses)      │
│     driver.py        run_typed_consensus()  ← the fixed pipeline        │
│     operators/       kmode · weighted · lca(R)                          │
│     scoring.py       composite member score (ADR 0011)                  │
│     source_registry.py  ConsensusSource type + artifact readers         │
│     templates.py     TEMPLATES (categorical/narrative + provenance)     │
│     dispatch.py      typed/narrative routing, banners, namespaces       │
│     spatial_metrics.py  MLAMI/CHAOS/PAS (eval)                          │
├──────────────────────────────────────────────────────────────────────┤
│ L1  Workflow runtime  (domain-neutral execution topology — "thin waist")│
│     omicsclaw/runtime/workflow/fan_out.py                               │
│        fan_out(steps, …) → asyncio.gather over skill subprocesses       │
│        WorkflowStep · StepRunResult · FanOutResult                      │
└──────────────────────────────────────────────────────────────────────┘
```

- **L1** owns *only* execution topology: parallel fan-out, the concurrency
  semaphore, cancellation, timeout, and an *optional, caller-supplied* survivor
  minimum (`required_survivors`, default off). It knows nothing about
  consensus — `fan_out` runs any `WorkflowStep` (anything with
  `name` / `skill_name` / `to_extra_args()`). It is the one reusable primitive;
  `chain` and a second client (`pipeline_runner`) are deferred (ADR 0016 §Open).
- **L2** owns the consensus *math* and contracts — shared by every flavour.
- **L3** is where you add a flavour: a small **declarative contract**, not code.

### The two-axis extension model

A consensus *flavour* is the product of two independent axes:

```
            Workflow template  (the merge MATH — one driver fn + a provenance)
            ──────────────────────────────────────────────
            categorical (run_typed_consensus, "typed")   ← v1, shipped
            narrative   (B-path synthesis,    "exploratory")
            rank        (RRA over DE,          "typed")   ← v2, reserved (own ADR)
            interval    (variant/SV merge,     "typed")   ← v3, reserved (own ADR)
                                  ×
            Source entry  (the DATA — what a contributor authors)
            ──────────────────────────────────────────────
            consensus-domains        → template=categorical, member=spatial-domains
            sc-consensus-clustering  → template=categorical, member=sc-clustering
```

Adding a flavour whose math already exists = **one `ConsensusSource` row**.
Adding a *new math shape* = a new template **and its own ADR** (the registry is
open but controlled — a template is a new "verified" guarantee).

---

## 3. Core concepts

| Term | What it is |
|---|---|
| **Consensus member** | One fan-out target: a deterministic *skill subprocess* (e.g. `spatial-domains --method banksy`), **not** an LLM agent. A `ConsensusMember(name, skill_name, params)`. |
| **Evaluation chair** | The LLM role that *proposes* which members to run (from a skill's `param_hints`) and narrates the result. It has **no** statistical authority — the operator does the math. Optional, with a deterministic fallback. |
| **Member planner** | The strategy that turns CLI args into the member list: `ChairLLMPlanner` (chair / `--all`), `SweepPlanner` (parameter cartesian product). The one piece of real per-flavour logic. |
| **Artifact reader** | A `MemberArtifactReader` that knows where a member skill writes its labels + intrinsic-quality scalar. One per member skill. |
| **Operator** | The categorical merge: `kmode` (per-row mode after Hungarian alignment), `weighted` (score-weighted majority), `lca` (latent class, R subprocess). |
| **BC (base clusterings)** | The members selected to actually enter the merge — top-K by composite score, or an interactive expert pick. |
| **Composite score** | Member ranking input: `α·cross_NMI + β·intrinsic`, with a class-imbalance hard filter (ADR 0011). |
| **Provenance** | A property of the *template*: `typed`/verified vs `exploratory`. Drives the banner + graph-memory namespace. |

---

## 4. How a typed run works end-to-end

`run_typed_consensus()` (`driver.py`) is a **fixed 8-step pipeline**. Everything
between fan-out and the report stays in local variables; only the final
`TypedConsensusRun` + on-disk artifacts surface.

```
                ┌─ 1. plan.json audit (written BEFORE fan-out, survives failures)
                │
  members ──────┼─ 2. fan_out()  ── parallel skill subprocesses (asyncio.gather,
 (planner)      │       │             semaphore ≤4, per-member timeout 600s,
                │       │             cancel chain; driver sets required_survivors=2)
                │       ▼
                ├─ 3. _gather_labels()  ── per-member reader → labels + intrinsic
                │       │             (member that produced no readable labels is dropped)
                │       ▼
                ├─ 4. score_all_members()  ── α·cross_NMI + β·intrinsic,
                │       │             −∞ if max_class_frac > 0.8  (→ member_scores.csv)
                │       ▼
                ├─ 5. cross_method_nmi_matrix()        (→ cross_method_nmi.csv)
                │       ▼
                ├─ 6. bc_selector()  ── top-K by score (default) OR interactive
                │       │             expert pick on a TTY; <2 BCs → error
                │       ▼
                ├─ 7. operator  ── kmode | weighted | lca   on the selected BCs
                │       ▼
                └─ 8. consensus_labels.tsv  +  format_typed_report() → report.md
                                                  (banner enforced, namespace stamped)
```

**Member planning** (step 0, upstream of the pipeline) is where the two flavours
differ — and the *only* thing that differs:

- `consensus-domains` → `ChairLLMPlanner`: the LLM chair proposes ~5 members from
  `spatial-domains`'s `param_hints` (deterministic offline fallback if no LLM
  key); `--all` fans out every method; `--members` takes an explicit list.
- `sc-consensus-clustering` → `SweepPlanner`: a leiden/louvain × resolution
  cartesian product; `--all` sweeps both methods at default resolutions.

**Intrinsic quality** is keyed per member skill:
`spatial-domains` → `mean_local_purity`; `sc-clustering` → `silhouette_score`.

**Failure semantics** (loud by design — ADR 0010 forbids silent B-path
fallback): `<2` surviving members or `<2` selected BCs → hard error.

---

## 5. Using it

### 5.1 CLI

Two equivalent entry points:

```bash
# (a) via the OmicsClaw skill runner (routable skill name)
python omicsclaw.py run consensus-domains \
    --input preprocessed.h5ad --output out/domains_consensus

# (b) via the generic entry directly (the shims forward to this)
python -m omicsclaw.runtime.consensus.run --source consensus-domains \
    --input preprocessed.h5ad --output out/domains_consensus
```

Single-cell flavour:

```bash
python omicsclaw.py run sc-consensus-clustering \
    --input preprocessed_scrna.h5ad --output out/sc_consensus \
    --resolutions 0.5,0.8,1.0,1.4,2.0 --cluster-methods leiden,louvain
```

**Flags** (both flavours accept the union; flavour-specific ones are noted):

| Flag | Default | Meaning |
|---|---|---|
| `--input` | — | Preprocessed AnnData (`.h5ad`) |
| `--output` | *(required)* | Output directory |
| `--members` | auto | Explicit member list, e.g. `banksy,leiden:resolution=0.5` |
| `--all` | off | Fan out the flavour's full set |
| `--operator` | `kmode` | `kmode` \| `weighted` \| `lca` |
| `--top-k` | `4` | BCs to select by score when non-interactive |
| `--alpha` / `--beta` | `0.6` / `0.4` | Composite-score weights (NMI vs intrinsic) |
| `--max-class-frac` | `0.8` | Class-imbalance hard-filter cap |
| `--confirm-plan` | off | Interactive pre-run plan confirmation (TTY) |
| `--non-interactive` | off | Force top-K BC selection (no prompts) |
| `--seed` | `0` | Operator seed (LCA only; kmode/weighted are deterministic) |
| `--timeout` | `600` (auto-raised to `1800` when an scVI member is planned, ADR 0029 B4) | Per-member subprocess timeout (s) |
| `--max-parallel` | auto | Concurrency cap (`min(N, cpu//2, 4)`) |
| `--run-id` | output dir name | Run identifier (stamped into `plan.json` + namespace) |
| `--query` | `""` | *(domains)* NL query for the evaluation chair |
| `--resolutions` | `0.5,0.8,1.0,1.4,2.0` | *(sc)* sweep resolutions |
| `--cluster-methods` | `leiden` | *(sc)* sweep methods |

> `--n-clusters` and `--llm-judge` are accepted for back-compat but **not yet
> consumed**.

**Exit codes**: `0` ok · `2` no members planned · `3` <2 surviving members ·
`4` template has no run-driver (narrative) · `5` <2 base clusterings ·
`6` LCA operator unavailable (R/diceR missing) · `130` aborted at confirm gate.

### 5.2 Via the agent

The LLM main loop invokes a flavour as an **ordinary skill** through the generic
executor — there is no separate "workflow" tool. A user asking *"run a consensus
of spatial domains on my sample"* routes to `execute_omicsclaw(skill=
"consensus-domains", …)`. The fan-out runs in a subprocess, so the agent's
context only ever sees the final report (no intermediate member chatter).

### 5.3 Output artifacts

Written to `--output/`:

| File | Contents |
|---|---|
| `report.md` | Human-readable report. **First line is the banner** (`[A: Verified consensus]`), then member-score table + cross-method NMI matrix. |
| `consensus_labels.tsv` | `(observation, consensus_<operator>)` — the merged labeling. |
| `member_scores.csv` | Per-member composite/NMI/intrinsic/imbalance + whether selected. |
| `cross_method_nmi.csv` | Pairwise NMI matrix of the members. |
| `plan.json` | Audit: run_id, operator, planned members + params, α/β, the resolved input path. Written **before** fan-out. |
| `<member_name>/…` | Each member's own skill output subdir (labels, figures). |

### 5.4 Downstream — annotation

`consensus-interpret` is a **separate downstream skill** (not a consensus): it
consumes a typed run's `plan.json` + `consensus_labels.tsv`, runs inline DE +
marker-grounded LLM annotation, and writes to the `analysis://interpreted/`
namespace (ADR 0012). The chain `consensus → interpret` is an ordinary
**pipeline**, not part of the consensus run itself.

---

## 6. Extending it

### 6.1 Add a new flavour whose math already exists (the common case)

Example: `consensus-celltypes` over a `sc-cell-annotation` skill that emits
per-cell labels. **Three steps, no orchestration code:**

1. **Reader** (~30 lines) in `source_registry.py` — a `MemberArtifactReader`
   that reads that skill's label column + intrinsic-quality scalar.
2. **Source row** in `sources.py`:
   ```python
   "consensus-celltypes": ConsensusSource(
       reader=CellTypeArtifactReader(),
       name="consensus-celltypes",
       template="categorical",              # reuse the existing math
       member_skill="sc-cell-annotation",
       planner=ChairLLMPlanner(),           # or SweepPlanner / a new one
       domain="singlecell",
       report_title="Verified consensus — cell types",
       param_hints_path=_param_hints("singlecell", "scrna", "sc-cell-annotation"),
   ),
   ```
   (The derived `TYPED_CONSENSUS_REGISTRY` picks it up automatically.)
3. **Shim + SKILL.md** — a 3-line `consensus_celltypes.py` forwarding to
   `run.py --source consensus-celltypes`, plus a `SKILL.md` + `parameters.yaml`
   so the router can discover it.

That's it — fan-out, scoring, BC selection, operators, report, banner, and
namespace all come for free.

### 6.2 Add a new merge *math* (rare — needs an ADR)

A genuinely new consensus shape (e.g. **rank** aggregation for DE results, or
**interval** merge for variant calls) is a new **Workflow template**: a new
driver function + a `TEMPLATES` entry with its provenance. Because a template is
a new *verified* guarantee, **it requires its own ADR** (per ADR 0016 B4a). It
reuses L1 `fan_out`, the `ConsensusSource` contract, and the planners unchanged.

---

## 7. Provenance & safety

The **verified vs exploratory** boundary is the headline contribution and is
non-negotiable:

- **Provenance lives on the template** (`TEMPLATES[t].provenance`). `categorical`
  is `typed`; `narrative` is `exploratory`. (ADR 0016 amended ADR 0010: the
  boundary is now two explicit fields — `source.template` + `template.provenance`
  — rather than one allowlist set.)
- **Banner** is the enforced first line of every report (`report.format_typed_report`);
  no caller can emit an A-path report without `[A: Verified consensus]`.
- **Namespace** splits graph memory: `analysis://typed/<id>` vs
  `analysis://exploratory/<id>` vs `analysis://interpreted/<id>`. Downstream
  meta-analysis reads `typed/*` by default; exploratory output is opt-in.
- **No silent downgrade**: an A-path run is allowed to fail loudly; it never
  falls back to the narrative path.

All processing is **in-process and local** ("genetic data never leaves this
machine"). The runtime is in-process `asyncio` fan-out over skill subprocesses,
**not** a cross-process job system.

---

## 8. Evaluation & testing

- **Composite score** (ADR 0011): `α·cross_NMI + β·intrinsic` with the
  `max_class_frac > 0.8` hard filter. Defaults `α=0.6, β=0.4` are the
  SACCELERATOR-published values, exposed as CLI flags for sensitivity analysis.
- **Metric panel** (hero benchmark): ARI + AMI + V-measure (+ MLAMI for spatial)
  are hard metrics; H/C/CHAOS/PAS are report-only. DLPFC 151673 is the gated
  hero benchmark (`RUN_DLPFC_BENCHMARK=1`).
- **Tests**: `tests/runtime/consensus/` (operators, alignment, scoring, the
  fan-out runtime, planners, templates, the generic entry, self-consistency,
  spatial metrics) + per-flavour smoke tests under each skill's `tests/`.
- **Behaviour lock**: the ADR 0016 refactor was verified by a golden compare —
  the five on-disk artifacts are byte-identical to the pre-refactor wrappers.

---

## 9. ADR map

| ADR | What it fixed |
|---|---|
| **0010** | Introduced the typed-vs-narrative runtime + the verified/exploratory split. |
| **0011** | The composite member score + the DLPFC hero benchmark + the metric panel. |
| **0012** | `consensus-interpret`'s evaluation protocol (the downstream annotation stage). |
| **0016** | Restructured into L1/L2/L3, the two-axis registry, collapsed the wrappers, folded dispatch into the registry. **This is the current shape.** |

---

## 10. Limits & roadmap

- **v1 ships one primitive** (`fan_out`) and one math template (`categorical`).
  `chain` + re-platforming `pipeline_runner` onto L1 are deferred until a second
  client needs them (ADR 0016 §Open).
- **v2 `rank`** (RRA over DE rankings) and **v3 `interval`** (variant/SV merge)
  are reserved templates — each will get its own ADR.
- v1 operators are conceptually-compatible Python simplifications, not bit-exact
  ports of SACCELERATOR's R operators (ADR 0010 §Consequences).
- The interactive expert BC picker is CLI-only; Desktop/Channel surfaces fall
  back to top-K by score.

---

*OmicsClaw is a research and educational tool for multi-omics analysis. It is
not a medical device and does not provide clinical diagnoses. Consult a domain
expert before making decisions based on these results.*
