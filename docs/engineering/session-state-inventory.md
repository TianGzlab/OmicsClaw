# Interactive Session State Inventory

Task 2.1 of the Phase 2 deepening plan. Enumerates every site that reads or
writes the `state: dict[str, Any]` used by `omicsclaw/interactive/interactive.py`,
as the discovery basis for the typed `SessionState` module that replaces it.

## Scope

- **Files using the dict-as-state pattern**: 1 (`omicsclaw/interactive/interactive.py`).
- **Files NOT using it**: `tui.py`, `_session.py`, `_session_command_support.py`,
  `_skill_run_support.py`, `_skill_management_support.py`, `_pipeline_support.py`,
  `_plan_mode_support.py`, `_memory_command_support.py`, `_omicsclaw_actions.py`,
  `_slash_command_support.py`, `_llm_bridge_support.py`, `_history_support.py`, `_mcp.py`.
- **Total access sites in interactive.py**: ~90 (across `state["k"]`, `state.get("k")`,
  `state.setdefault("k", …)`, etc.).

This is significantly smaller than initially feared; the migration is contained
to a single file. The original Phase 2 plan's tasks 2.4 (migrate `tui.py`) and
2.5 (migrate `_*_support.py`) are no-ops and can be skipped.

## Key inventory

The dict is initialized as a 7-field literal at `interactive.py:1782` inside
`run_interactive()`:

```python
state = {
    "session_id":         effective_session_id,
    "workspace_dir":      effective_workspace,
    "pipeline_workspace": "",
    "session_metadata":   {},
    "messages":           [],
    "running":            True,
    "ui_backend":         ui_backend,
}
```

Two additional keys are mutated into the dict later in the same function:

| Key | First write | Reason added later |
|---|---|---|
| `tips_enabled` | `interactive.py:2050,2058` | Toggled by user `/tips` slash command |
| `tips_level`   | `interactive.py:2068`      | Set by `/tips verbose|short|off` |

So the **full key set** is 9.

## Per-key contract

| Key | Type | Default | Mutability | Read access | Write access |
|---|---|---|---|---|---|
| `session_id` | `str` | required (caller of `run_interactive` provides) | mutated only by `_apply_session_command_view` (resume flow) | 10 | low (1-2 sites) |
| `workspace_dir` | `str` (path) | required | rarely mutated; mostly stable for lifetime | 19 (incl. `state.get`) | low |
| `pipeline_workspace` | `str` (path or "") | `""` | toggled by `_set_active_pipeline_workspace` | 7 | 2 sites |
| `session_metadata` | `dict[str, Any]` | `{}` | rebuilt by `build_session_metadata` after every mutation | 28 | 3-4 sites |
| `messages` | `list[dict]` (LLM message log) | `[]` | append-mostly during chat loop | 15 | many |
| `running` | `bool` | `True` | set False on shutdown sentinel | 4 | 1-2 sites |
| `ui_backend` | `str` (`"cli"` or `"tui"`) | required | immutable after init | 0 reads via `state[...]` (passed via other channels) | 1 (init) |
| `tips_enabled` | `bool` (optional) | absent → defaults `True` via `state.get(..., True)` | toggled by `/tips on|off` | 3 | 2 |
| `tips_level` | `str` (`"verbose"`/`"short"`/`"off"`) | absent → defaults via `state.get(..., "verbose")` | set by `/tips <level>` | 4 | 1 |

## Invariants observed

1. **session_metadata is a derived view**: rebuilt via `build_session_metadata(session_id, messages, …)` after any change to `pipeline_workspace`, `workspace_dir`, or `messages`. Three places call `build_session_metadata` (`_set_active_pipeline_workspace`, `_apply_session_command_view`, `_session_metadata_from_state`).
2. **`pipeline_workspace == "" XOR pipeline_mode_enabled`** is implicit: the empty string means "no active pipeline workspace"; non-empty means a pipeline is active. Never `None` in this dict (it would be `None` in `session_metadata.get("pipeline_workspace")`).
3. **`tips_enabled` / `tips_level` may be absent** initially and only appear after the user toggles them. Reads use `state.get(..., default)`.
4. **`running` is the chat-loop sentinel**: while True, the prompt loop continues; set False only by the loop's own exit conditions.
5. **`ui_backend` is set once and never written again**: it carries the initial UI choice (CLI vs TUI) so downstream rendering can branch.

## Function signatures that take `state`

15 functions take `state: dict[str, Any]` as a parameter (per grep). The pattern
is concentrated in two clusters:

- **Helpers (lines 534-660)**: `_session_metadata_from_state`,
  `_active_pipeline_workspace`, `_active_output_style`,
  `_active_scoped_memory_scope`, `_set_active_pipeline_workspace`,
  `_apply_session_command_view`, `_apply_pipeline_command_view`,
  `_apply_interactive_plan_command_view`.
- **Slash command handlers (lines 846-1300)**: `_handle_resume`, `_handle_delete`,
  `_handle_memory`, `_handle_tasks`, `_handle_plan`, `_handle_approve_plan`,
  `_handle_research`, `_handle_resume_task`, `_handle_do_current_task`.
- **Plan context** (line 1713): `_interactive_plan_context`.

All of these will accept `SessionState` instead of `dict[str, Any]`.

## Implications for SessionState design

- 9 typed fields with defaults documented above.
- 3 mutator methods cover the actual transitions: `mark_session_metadata`,
  `set_pipeline_workspace`, `apply_session_command_view`.
- 2 toggle methods for tips: `set_tips_enabled`, `set_tips_level`.
- A `running: bool` field with a `stop()` method (or just direct attribute set).
- `to_dict() / from_dict()` adapters for staged migration (caller-by-caller),
  so old call sites can keep using the dict shape during the transition.
- `messages` stays a `list[dict]` — no benefit to typing each LLM message dict
  here.

## Phase 2 plan adjustments (post-2.1)

- **Task 2.4 SKIP**: `tui.py` does not use the state-dict pattern.
- **Task 2.5 SKIP**: `_*_support.py` files do not use the state-dict pattern.
- **Task 2.3 expanded**: migrate the *whole* `interactive.py` (not just lines
  534-652), since the dict access spans 1700+ lines of the same file.

The plan thus collapses from 6 work tasks to 4 (2.1 done, 2.2, 2.3, 2.6) plus
the review task 2.7. Total work effort drops accordingly.
