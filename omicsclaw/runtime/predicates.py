"""Predicate functions for context-conditional system-prompt layers.

Phase 4 (Task 4.3) of the system-prompt-compression refactor. Each
predicate takes a ``ContextAssemblyRequest`` and returns ``True`` when
the corresponding conditional rule should be injected into the system
prompt for this turn. Conditional layers register their predicate on
``ContextLayerInjector.predicate`` and the assembler applies the gate.

The predicates are deliberately cheap (regex / string checks) and
side-effect-free. Misbehaving predicates fail-closed at the
``ContextLayerInjector`` layer, so a regex bug never breaks prompt
assembly.
"""

from __future__ import annotations

import re

from .context_layers import ContextAssemblyRequest

# --- Shared regex constants --------------------------------------------------

_FILE_PATH_RE = re.compile(
    r"\.(?:h5ad|h5|loom|csv|tsv|fastq|fq|bam|vcf|mzml)\b|/[A-Za-z0-9._/\-]+",
    re.IGNORECASE,
)

_PDF_OR_PAPER_RE = re.compile(
    r"\.pdf\b|\bpaper\b|\bliterature\b|文献|GEO\s+accession",
    re.IGNORECASE,
)

_IMPLEMENTATION_INTENT_RE = re.compile(
    r"\b(implement|implementing|build|building|refactor|refactoring|"
    r"add|adding|extend|extending|create|creating)\b|"
    r"添加|实现|重构|构建|创建|新增|写一个|写个",
    re.IGNORECASE,
)

_MEMORY_KEYWORDS_RE = re.compile(
    r"\b(remember|forget|recall|memorize)\b|记住|忘记|忘掉|回忆",
    re.IGNORECASE,
)

# Catches statements of *persistent* preferences without an explicit
# 记住 / remember cue. Used to gate the ``remember`` tool so the LLM can
# proactively persist a preference the user states declaratively
# (e.g. "以后请用中文回答", "from now on use DESeq2"). Deliberately
# narrower than "anything containing 总是/always": each branch requires
# a preference verb / preference-shaped collocation so that scientific
# phrasings like "cells are always changing" or "以后再说" don't fire.
_PREFERENCE_STATEMENT_RE = re.compile(
    # English: temporal-scope leaders ("from now on", "going forward")
    r"\b(from now on|going forward)\b|"
    # English: always/never/usually + preference verb
    r"\b(always|never|usually)\s+"
    r"(use|do|run|reply|respond|answer|chat|talk|skip|avoid|prefer|set|show)\b|"
    # English: "I prefer/usually/like/want to ..." + verb
    r"\bi\s+(prefer|usually|always|like|want)\s+(to\s+\w+|using\s+|\w+ing)\b|"
    # English: "prefer to ...", "default to ...", "please always/never ..."
    r"\b(prefer\s+to|default\s+to|please\s+(always|never))\b|"
    # Chinese: persistent-scope adverb + preference verb
    r"(以后|今后|始终|一直|总是|每次)\s*(都|请|改|帮我)?\s*"
    r"(用|不用|不要|要|改用|换成|采用|设为|设成|配置)|"
    # Chinese: "默认" as a verb / setting ("默认用 X", "默认是 X")
    r"默认\s*(用|是|为|采用|设|配置)|"
    # Chinese: I-prefer constructions
    r"我(习惯|喜欢|偏好|常用)|"
    # Chinese: "请用 X / 帮我把 X / 请帮我记 X"
    r"(请|帮我)(用|改用|换成|总是|始终|一直|把|记)",
    re.IGNORECASE,
)

_PLOT_KEYWORDS_RE = re.compile(
    # Plot-type words that are unambiguous (violin/heatmap/barplot/boxplot).
    # ``umap`` / ``tsne`` excluded — algorithm names without plot intent.
    # ``figure`` / ``scatter`` are common enough as non-plot tokens
    # ("figure of merit", "scatter the cells", "figure out") that we
    # require them to co-occur with a verb (``draw|make|generate|show|
    # render|enhance``) to fire.
    r"\b(plot|violin|heatmap|visualize|visualise|barplot|boxplot|"
    r"chart|enhance the (?:plot|figure))\b|"
    r"\b(?:draw|make|generate|show|render|enhance)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:figure|scatter)\b|"
    r"图(?!像|片)|可视化|绘图|画图",
    re.IGNORECASE,
)

# ``web`` / ``website`` / ``webpage`` / explicit URL / search-the-web phrases
# are unambiguous. Bare ``online`` is too common in scientific phrases
# ("online statistical test", "online learning", "online resource") so we
# require it to either follow a search/find/lookup verb (e.g. "find X
# online") OR precede a fetch-noun (e.g. "online tool", "online lookup").
_WEB_OR_URL_RE = re.compile(
    r"https?://|"
    r"\b(web|website|webpage|scrape|crawl|search the web|"
    r"look up online|search online|web search)\b|"
    r"\b(?:look\s+up|search|find|access|fetch|grab|browse)\b[^.\n]*\bonline\b|"
    r"\bonline\s+(?:search|lookup|database|tool|service)\b|"
    r"网页|网站|搜.{0,3}网|在线搜",
    re.IGNORECASE,
)

# Skill-creation specifically — must not match plain skill invocations
# ("run sc-de", "execute spatial-preprocess"). A creation verb must
# co-occur with the literal word "skill" (or a Chinese equivalent).
_SKILL_CREATION_RE = re.compile(
    r"\b(create|creating|add|adding|scaffold|scaffolding|build|building|"
    r"package|packaging|wrap|wrapping)\b[^.\n]*\bskill\b|"
    r"封装(?:成|为)?(?:一个|个)?\s*skill|"
    r"新建(?:一个|个)?\s*skill|"
    r"创建\s*skill",
    re.IGNORECASE,
)

# Trivial-query length cutoff: very short queries don't trigger non-trivial
# routing reminders. Picked to skip greetings ("hi", "hello") and one-word
# follow-ups while letting "do DE" through.
_NON_TRIVIAL_MIN_LENGTH = 8


# --- Predicates --------------------------------------------------------------


def implementation_intent(req: ContextAssemblyRequest) -> bool:
    """Fires when the user wants to implement / refactor / add code.

    Used to gate the scope-control + minimal-change rules so they appear
    only when the agent is about to write code, not on plain analysis
    questions.
    """
    return bool(_IMPLEMENTATION_INTENT_RE.search(req.query or ""))


def anndata_or_file_path_in_query(req: ContextAssemblyRequest) -> bool:
    """Fires when a known omics file extension or absolute path is in the query.

    Triggers the file-path-discipline + ``inspect_data`` preflight rules.
    """
    query = req.query or ""
    if not query:
        return False
    return bool(_FILE_PATH_RE.search(query))


def pdf_or_paper_intent(req: ContextAssemblyRequest) -> bool:
    """Fires on PDF / paper / 文献 / GEO accession mentions.

    Triggers the ``parse_literature`` rule.
    """
    return bool(_PDF_OR_PAPER_RE.search(req.query or ""))


def workspace_active(req: ContextAssemblyRequest) -> bool:
    """Fires when an active workspace or pipeline workspace is bound.

    Triggers the workspace-continuity rule (``plan.md`` / ``todos.md``
    are the source of truth, check artifacts before rerun).
    """
    return bool((req.workspace or "").strip()) or bool(
        (req.pipeline_workspace or "").strip()
    )


def chat_surface(req: ContextAssemblyRequest) -> bool:
    """Fires only on the ``bot`` surface.

    Triggers the chat-mode discipline (answer directly when the user
    only needs an explanation; don't write artifacts unless asked).
    """
    return str(req.surface or "").strip().lower() == "bot"


def memory_in_use(req: ContextAssemblyRequest) -> bool:
    """Fires when the user mentions remember / recall / forget keywords.

    Triggers the memory hygiene rule (no secrets / PII / transient errors).
    """
    return bool(_MEMORY_KEYWORDS_RE.search(req.query or ""))


def preference_statement_intent(req: ContextAssemblyRequest) -> bool:
    """Fires when the user *declaratively* expresses a persistent preference,
    without uttering a 记住 / remember trigger word.

    Gates the ``remember`` tool so the LLM can persist preferences like
    "以后请用中文回答" or "from now on use DESeq2" proactively. ``recall`` /
    ``forget`` remain gated by ``memory_in_use`` alone — those are
    explicit user actions, not LLM-initiated.
    """
    return bool(_PREFERENCE_STATEMENT_RE.search(req.query or ""))


def plot_intent(req: ContextAssemblyRequest) -> bool:
    """Fires when the user wants a plot / figure / visualization tweaked.

    Triggers exposure of ``replot_skill`` — the only tool whose entire
    purpose is post-hoc visual tuning.
    """
    return bool(_PLOT_KEYWORDS_RE.search(req.query or ""))


def web_or_url_intent(req: ContextAssemblyRequest) -> bool:
    """Fires when the user mentions a URL or web/online search intent.

    Triggers exposure of ``web_fetch`` / ``web_search`` /
    ``web_method_search``.
    """
    return bool(_WEB_OR_URL_RE.search(req.query or ""))


def skill_creation_intent(req: ContextAssemblyRequest) -> bool:
    """Fires when the user wants to *create* / *scaffold* / *package* a
    new OmicsClaw skill — not just run an existing one.

    Triggers exposure of ``create_omics_skill``. The regex deliberately
    requires a creation verb co-occurring with the word ``skill`` (or a
    Chinese equivalent) so plain invocations (``run sc-de``) don't match.
    """
    return bool(_SKILL_CREATION_RE.search(req.query or ""))


def non_trivial_no_capability(req: ContextAssemblyRequest) -> bool:
    """Fires for substantive queries that lack a deterministic capability
    block.

    Triggers a concrete reminder to call ``resolve_capability`` with
    explicit args before acting (more specific than the always-on
    SOUL.md rule, which is intentionally brief).
    """
    query = (req.query or "").strip()
    if len(query) < _NON_TRIVIAL_MIN_LENGTH:
        return False
    return not bool((req.capability_context or "").strip())


__all__ = [
    "anndata_or_file_path_in_query",
    "chat_surface",
    "implementation_intent",
    "memory_in_use",
    "non_trivial_no_capability",
    "pdf_or_paper_intent",
    "plot_intent",
    "skill_creation_intent",
    "web_or_url_intent",
    "workspace_active",
]
