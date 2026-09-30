"""``omicsclaw.context`` — what the model is shown, and what it costs.

Plan 0030, step 5 of the staged rebuild. The three layers before this
one can run a ReAct turn but cannot say where the conversation came
from: ``AgentEngine.run(messages)`` takes an assembled conversation and
``omicsclaw/engine/loop.py:34-38`` says so outright — "the conversation
arrives assembled". **This is the layer that assembles it**, decides
whether it still fits, and shrinks it when it does not::

    from omicsclaw.context import (
        ContextBudget, PromptAssembler, Section, assemble, compact, static,
    )

    prompt = (
        PromptAssembler()
        .with_section(Section("contract", "", text_from_file("OMICSCLAW.md")))
        .with_section(Section("project", "## Project", text_from_file("AGENTS.md")))
        .with_section(Section("skills", "## Skills", render_skill_index))
        .render()
    )
    conversation = assemble(prompt, history, "分析这份 Visium 数据")

    limits = get_model_limits(model)
    budget = ContextBudget(
        context_tokens=limits.context_tokens,
        reserve_output_tokens=limits.output_tokens,
        reserve_tool_tokens=estimate_tool_tokens(tools),
    )
    smaller, record, state = await compact(
        conversation, budget, summarizer=summarize_with_haiku, pinned=1
    )
    # Next turn: ``smaller[1:]`` — ``pinned=1`` kept the system message
    # inside the compacted history, and ``assemble`` always adds a fresh
    # one. See :func:`~omicsclaw.context.prompt.assemble`.
    conversation = assemble(prompt, smaller[1:], "下一步")

Note where the knowledge lives in that sketch: ``OMICSCLAW.md``, the skill
index, the model table and the summarizing model are all the composition
root's, reaching this package through a callable or a plain ``int``.

**Leaf package.** Inside ``omicsclaw`` it imports ``omicsclaw.schema``
and nothing else; outside it, only the standard library. Not
``provider`` (``get_model_limits`` would be one table read and one
import too many), not ``engine``, not ``tools``, not ``runtime``. Every
piece of outside knowledge arrives through a Protocol or a callable:
:class:`~omicsclaw.context.tokens.TokenCounter` for an exact tokenizer,
:data:`~omicsclaw.context.sections.SectionSource` for anything textual,
:class:`~omicsclaw.context.summary.Summarizer` for the model that
writes summaries. ``tests/context/test_context_is_a_leaf_layer.py``
enforces it, by running the layer in a subprocess and looking at what
actually got imported rather than at what was spelled.

**Compaction inside a run.** :class:`ProgressiveCompactor` grades the
conversation before every model call and compacts it by tier; it
satisfies the engine's ``HistoryCompactor`` protocol structurally, so an
engine run can be handed one without either package importing the
other::

    compactor = ProgressiveCompactor(
        budget, summarizer=summarizer, offloader=Offloader(store), pinned=1
    )
    result = await engine.run(conversation, compactor=compactor)
    carried = compactor.state

**Not here.** No session, no persistence and no filesystem: offloaded
text goes to an :class:`OffloadStore` and records leave through a
callback, both supplied by the caller.
"""

from __future__ import annotations

from .budget import (
    PRESSURE_ORDER,
    BudgetReport,
    ContextBudget,
    Pressure,
    at_least,
    measure,
)
from .compaction import (
    CompactionPlan,
    CompactionRecord,
    CompactionState,
    DEFAULT_MIN_TAIL,
    MemoryExtractor,
    apply_compaction,
    build_summary_prompt,
    collect_references,
    compact,
    plan_compaction,
)
from .offload import (
    MAX_REFERENCES,
    OFFLOAD_MARKER,
    REFERENCES_HEADING,
    OffloadEntry,
    OffloadOutcome,
    OffloadStore,
    Offloader,
    is_offloaded,
    offload_key,
    offload_messages,
    parse_placeholder,
    parse_references,
    render_placeholder,
    render_references,
)
from .progressive import ProgressiveCompactor, should_write_back
from .prompt import AssembledPrompt, PromptAssembler, assemble
from .sections import (
    RenderedSection,
    Section,
    SectionSource,
    static,
    text_from_file,
)
from .summary import (
    COMPACTION_MARKER,
    FIRST_TEMPLATE,
    INCREMENTAL_TEMPLATE,
    OFFLOAD_RULE,
    SUMMARY_SYSTEM_PROMPT,
    Anchors,
    Summarizer,
    build_compaction_message,
    is_summary_message,
    parse_anchors_and_summary,
)
from .tokens import (
    TokenCounter,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_text_tokens,
    estimate_tool_tokens,
    format_token_count,
)
from .transcript import (
    MISSING_TOOL_RESULT,
    emergency_fit,
    fit_to_budget,
    render_for_summary,
    repair_tool_pairs,
    split_head_tail,
)

__all__ = [
    "Anchors",
    "AssembledPrompt",
    "BudgetReport",
    "COMPACTION_MARKER",
    "CompactionPlan",
    "CompactionRecord",
    "CompactionState",
    "ContextBudget",
    "DEFAULT_MIN_TAIL",
    "FIRST_TEMPLATE",
    "INCREMENTAL_TEMPLATE",
    "MAX_REFERENCES",
    "MISSING_TOOL_RESULT",
    "MemoryExtractor",
    "OFFLOAD_MARKER",
    "OFFLOAD_RULE",
    "OffloadEntry",
    "OffloadOutcome",
    "OffloadStore",
    "Offloader",
    "PRESSURE_ORDER",
    "Pressure",
    "ProgressiveCompactor",
    "PromptAssembler",
    "REFERENCES_HEADING",
    "RenderedSection",
    "SUMMARY_SYSTEM_PROMPT",
    "Section",
    "SectionSource",
    "Summarizer",
    "TokenCounter",
    "apply_compaction",
    "assemble",
    "at_least",
    "build_compaction_message",
    "build_summary_prompt",
    "collect_references",
    "compact",
    "emergency_fit",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    "estimate_text_tokens",
    "estimate_tool_tokens",
    "fit_to_budget",
    "format_token_count",
    "is_offloaded",
    "is_summary_message",
    "measure",
    "offload_key",
    "offload_messages",
    "parse_anchors_and_summary",
    "parse_placeholder",
    "parse_references",
    "plan_compaction",
    "render_for_summary",
    "render_placeholder",
    "render_references",
    "repair_tool_pairs",
    "should_write_back",
    "split_head_tail",
    "static",
    "text_from_file",
]
