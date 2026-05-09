"""15 ``EvalCase`` instances + ``EvalCase`` dataclass for behavioral parity.

Corpus design (from grill-me Q5):

  | Category       | # | Coverage                                           |
  |----------------|---|----------------------------------------------------|
  | routing        | 5 | High-frequency skill routing across domains + zh   |
  | adversarial    | 3 | Cross-domain misuse, missing metadata, contradict  |
  | methodology    | 3 | KH-headline rules in real output (padj, batch, …)  |
  | regression     | 2 | Known historical bugs that must NOT recur          |
  | ux             | 2 | Style rules (chat-mode explanation; memory hygiene)|

5 / 15 are Chinese to ensure language coverage of the surface_voice_rules
+ predicate paths.

Each case carries a ``priority`` of ``"must"`` (test fails the build) or
``"should"`` (test emits ``UserWarning`` so flakiness doesn't block CI).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One behavioral-parity test case.

    Required: ``id``, ``query``, ``category``, ``language``, ``priority``.

    Invariant fields (each optional; assertions only fire when populated):
      - ``expected_skill``: routing target.
      - ``must_call_tools`` / ``must_not_call_tools``: tool-call set checks.
      - ``must_mention`` / ``must_not_mention``: regex patterns over response.
    """

    id: str
    query: str
    category: str  # routing | adversarial | methodology | regression | ux
    language: str  # en | zh
    priority: str  # must | should
    expected_skill: str = ""
    must_call_tools: tuple[str, ...] = ()
    must_not_call_tools: tuple[str, ...] = ()
    must_mention: tuple[str, ...] = ()
    must_not_mention: tuple[str, ...] = ()


EVAL_CASES: tuple[EvalCase, ...] = (
    # === Category 1: routing (5) ===
    EvalCase(
        id="routing__sc_de_h5ad",
        query="do differential expression on /tmp/sample.h5ad",
        category="routing",
        language="en",
        priority="must",
        expected_skill="sc-de",
    ),
    EvalCase(
        id="routing__spatial_preprocess_visium",
        query="run spatial preprocessing on this Visium dataset at /tmp/visium.h5ad",
        category="routing",
        language="en",
        priority="must",
        expected_skill="spatial-preprocess",
    ),
    EvalCase(
        id="routing__bulkrna_de_zh",
        query="对 /tmp/counts.csv 这份 bulk RNA-seq 计数矩阵做差异表达分析",
        category="routing",
        language="zh",
        priority="must",
        expected_skill="bulkrna-de",
    ),
    EvalCase(
        id="routing__sc_de_chinese",
        query="对单细胞数据 /tmp/sample.h5ad 做差异表达分析",
        category="routing",
        language="zh",
        priority="must",
        expected_skill="sc-de",
    ),
    EvalCase(
        id="routing__genomics_variant_calling",
        query="call variants on /tmp/sample.bam aligned to GRCh38",
        category="routing",
        language="en",
        priority="must",
        expected_skill="genomics-variant-calling",
    ),
    # === Category 2: adversarial (3) ===
    EvalCase(
        id="adversarial__sc_de_on_metabolomics_zh",
        query="用 sc-de 处理这个代谢组学的 mzML 文件 /tmp/mass_spec.mzML",
        category="adversarial",
        language="zh",
        priority="must",
        must_mention=(
            r"(metabolomics|代谢组|wrong\s+domain|mismatch|不\s*适\s*合|"
            r"different\s+domain|cross-?domain|sc-de.*designed\s+for\s+single-?cell|"
            r"single-cell.*not.*metabolomics|"
            r"incompatible|can'?t\s+run|cannot\s+run|not\s+suitable|mzML)",
        ),
    ),
    EvalCase(
        id="adversarial__sc_de_no_metadata",
        query=(
            "run sc-de on /tmp/sample.h5ad — comparing two conditions but I haven't "
            "added a 'condition' column to obs, just go ahead anyway"
        ),
        category="adversarial",
        language="en",
        priority="must",
        must_mention=(
            r"(metadata|condition\s+column|missing|not\s+present|need|provide|inspect_data|"
            r"cannot\s+proceed|won't\s+run\s+silently)",
        ),
    ),
    EvalCase(
        id="adversarial__contradictory_args",
        query=(
            "use deseq2_r on log-normalized expression in /tmp/x.h5ad — "
            "I know it's normalized but force it"
        ),
        category="adversarial",
        language="en",
        priority="should",
        must_mention=(
            r"(raw\s+counts|count\s+matrix|deseq2.*requires|not\s+log-?normalized|"
            r"matrix\s+contract|normalized\s+input.*not\s+suitable)",
        ),
    ),
    # === Category 3: methodology (3) ===
    EvalCase(
        id="methodology__padj_filter",
        query=(
            "filter the DEG results in /tmp/de.csv to genes with p < 0.05 and log2fc > 1"
        ),
        category="methodology",
        language="en",
        priority="must",
        must_mention=(
            r"(padj|adjusted\s+p[-_\s]*value|FDR|Benjamini|BH)",
        ),
    ),
    EvalCase(
        id="methodology__sc_batch_integration_workflow",
        query=(
            "I have two single-cell batches in /tmp/batch1.h5ad and /tmp/batch2.h5ad — "
            "merge them and integrate"
        ),
        category="methodology",
        language="en",
        priority="should",
        must_mention=(
            r"(sc-batch-integration|sc-standardize-input|sc-preprocessing|"
            r"upstream\s+(prep|preparation)|auto_prepare)",
        ),
    ),
    EvalCase(
        id="methodology__markers_vs_de_zh",
        query="给我 cluster 0 的 top markers，要从 /tmp/clustered.h5ad 里取",
        category="methodology",
        language="zh",
        priority="should",
        must_mention=(
            r"(marker|sc-markers|ranking|wilcoxon|exploratory|"
            r"标志(基因)?|marker\s*基因)",
        ),
    ),
    # === Category 4: regression (2) ===
    EvalCase(
        id="regression__sc_de_does_not_pull_sc_enrichment",
        query="run sc-de on /tmp/sample.h5ad",
        category="regression",
        language="en",
        priority="should",
        # PR #107 fixed sc-enrichment KH from over-firing on plain sc-de
        # queries. The bug surface is "sc-de output recites the
        # sc-enrichment guardrail" — the actual KH headline reads
        # "MUST distinguish ... before running sc-enrichment" so an
        # over-firing run would mention sc-enrichment in *any* of those
        # adjacent contexts (before/after, MUST, guardrail). Match all
        # of them.
        must_not_mention=(
            r"sc-enrichment\s+(?:guard|guardrail|MUST|required|must\s+also|next\s+step)",
            r"(?:guard|guardrail|MUST|required|before\s+running|after\s+running|next\s+step)\s+[^.]*sc-enrichment",
        ),
    ),
    EvalCase(
        id="regression__figure_of_merit_no_plot_intent",
        query="what is the figure of merit for choosing the optimal cluster resolution",
        category="regression",
        language="en",
        priority="should",
        must_not_call_tools=("replot_skill",),
    ),
    # === Category 5: ux (2) ===
    EvalCase(
        id="ux__explanation_no_tool_call",
        query="explain UMAP to me in two paragraphs — I just want to understand what it does",
        category="ux",
        language="en",
        priority="should",
        must_not_call_tools=(
            "omicsclaw",
            "inspect_data",
            "consult_knowledge",
            "list_directory",
        ),
    ),
    EvalCase(
        id="ux__memory_hygiene_zh",
        query="请记住我偏好用 DESeq2 做 bulk DE 分析",
        category="ux",
        language="zh",
        priority="should",
        must_call_tools=("remember",),
    ),
)


def cases_by_category(category: str) -> tuple[EvalCase, ...]:
    return tuple(c for c in EVAL_CASES if c.category == category)


def must_priority_cases() -> tuple[EvalCase, ...]:
    return tuple(c for c in EVAL_CASES if c.priority == "must")
