"""The prompt section that makes planning a habit rather than a feature.

Plan 0039 §1. The reference harness is explicit that planning is a
**native capability, not a mode** (``plan.go:3-5``, after its Plan Mode
was removed): there is no switch to flip, no tool filtering and no
runtime detection. What replaces all of that is one section of the system
prompt plus one tool, and the model decides when a task is worth planning.

This module is the text. :mod:`omicsclaw.planning` renders it;
:func:`~omicsclaw.entry.assembly.default_sections` places it — the same
split :mod:`omicsclaw.skills` has with the catalogue, and for the same
reason: the layer that writes text and the layer that decides where text
goes should not import each other.

**Mount the section only when the tool is mounted.** The reference
harness gates it on ``planEnabled`` (``builder.go:123``) and the
consequence of getting it wrong is specific: a prompt that instructs the
model to call ``plan_write`` when no such tool exists produces a call
that fails, which the model then tries to correct — spending turns on a
capability the deployment turned off.
"""

from __future__ import annotations

from .tool import PLAN_WRITE_TOOL_NAME

__all__ = ["PLANNING_GUIDANCE", "PLANNING_SECTION_HEADING"]


PLANNING_SECTION_HEADING = "## Planning"

PLANNING_GUIDANCE = f"""\
For a task with several steps — a multi-stage analysis, work that has to \
be explored before it can be done, anything where a later step depends on \
an earlier one — write the plan with `{PLAN_WRITE_TOOL_NAME}` first, then \
work through it.

- Each item is one concrete action you can carry out: "deconvolve the \
Visium sample against the reference", "write the QC report". Not \
"clarify the requirements", not "design the approach" — those are \
thinking, and thinking is not an item.
- Mark an item `in_progress` before you start it, and `completed` once \
it is actually done. Updating the status without doing any other work is \
not doing the item.
- When you update, send only the items still in play. Anything already \
started is kept for you. To abandon an item, mark it `cancelled` — \
leaving it out only trims steps that never began.
- The plan is the authoritative record of this task. It stays visible to \
you after the conversation is compacted and after a session is resumed, \
so when the two disagree, follow the plan.
- A one- or two-step task, a question, a single command: just do it. \
Planning those teaches you to plan everything."""
"""Ported from ``builder.go:125-134``, in this prompt's language.

Four of the five bullets are the reference's, with one addition and one
deliberate sharpening:

*Added* — "updating the status without doing any other work is not doing
the item". In the reference this sentence lives in a TUI-only
continuation prompt (``tui_update.go:53-56``) and its comment explains
why it is worth the line: it is the prompt-layer half of a **pair** with
the tool-layer batch-completion check in
:func:`~omicsclaw.planning.rules.validate`. The tool refuses a batch of
fabricated completions after the fact; this sentence is what stops the
model reaching for one. Keeping only the half that raises an error is
keeping the half that arrives too late. The TUI it was written for was
never ported (plan 0031 §11), so the sentence had to move or be lost.

*Sharpened* — the examples of a concrete item are this repository's
(a deconvolution, a QC report) rather than the reference's
(``create a file``, ``implement a function``). An example a model can
pattern-match on is doing more work here than the rule above it.

**No skill is named in them**, and that is not a stylistic preference:
``tests/entry/test_turn.py::test_switching_the_catalogue_off_removes_it_from_the_turn``
caught a first draft whose example said ``spatial-deconv``, which put a
skill name into the prompt of a deployment running ``skills_index=off``
— the model is then told about a capability that was deliberately not
advertised and has no ``use_skill`` to reach it with. The example
describes the *work* instead.
"""
