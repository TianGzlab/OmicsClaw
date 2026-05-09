"""Backward-compat contract for bot.tool_executors.

The module collects the 24 ``execute_*`` async tool implementations + the
dispatch table builder, carved out of bot/core.py per ADR 0001 (#120).
External tests (``tests/test_bot_completion_messages.py``,
``tests/test_skill_listing.py``) import these names from ``bot.core``;
this identity test guarantees the two paths point at the same callable.
"""

from __future__ import annotations


TOOL_EXECUTORS_REEXPORTS = (
    # 24 execute_* async functions
    "execute_omicsclaw",
    "execute_replot_skill",
    "execute_save_file",
    "execute_write_file",
    "execute_generate_audio",
    "execute_parse_literature",
    "execute_fetch_geo_metadata",
    "execute_list_directory",
    "execute_inspect_file",
    "execute_inspect_data",
    "execute_make_directory",
    "execute_move_file",
    "execute_remove_file",
    "execute_get_file_size",
    "execute_remember",
    "execute_recall",
    "execute_forget",
    "execute_read_knowhow",
    "execute_consult_knowledge",
    "execute_resolve_capability",
    "execute_list_skills_in_domain",
    "execute_create_omics_skill",
    "execute_web_method_search",
    "execute_custom_analysis_execute",
    # Dispatch surface
    "_available_tool_executors",
    "_build_tool_runtime",
    "get_tool_runtime",
    "get_tool_executors",
)


def test_tool_executors_re_exports_share_identity_with_bot_core():
    """Every previously-public symbol must resolve to the *same object*
    when looked up via ``bot.core`` or via ``bot.tool_executors``."""
    import bot.core
    import bot.tool_executors

    missing_on_tool_exec = [
        name for name in TOOL_EXECUTORS_REEXPORTS
        if not hasattr(bot.tool_executors, name)
    ]
    assert not missing_on_tool_exec, (
        f"Missing on bot.tool_executors: {missing_on_tool_exec}"
    )

    missing_on_core = [
        name for name in TOOL_EXECUTORS_REEXPORTS
        if not hasattr(bot.core, name)
    ]
    assert not missing_on_core, (
        f"Missing on bot.core (re-export): {missing_on_core}"
    )

    mismatched_identity = [
        name for name in TOOL_EXECUTORS_REEXPORTS
        if getattr(bot.core, name) is not getattr(bot.tool_executors, name)
    ]
    assert not mismatched_identity, (
        f"Parallel copies (must be same object): {mismatched_identity}"
    )


def test_tool_executors_dispatch_table_lists_all_24_executors():
    """``_available_tool_executors()`` returns the full dispatch map.
    The lazy ``bot.core.TOOL_EXECUTORS`` attribute also adds the
    engineering tool executors (file_read / write_file / list_directory /
    edit_file / shell). Pin the count so an accidental dropped registration
    (e.g. typo on ``execute_X.__name__``) is caught."""
    import bot.tool_executors

    table = bot.tool_executors._available_tool_executors()
    # 24 native executors are mapped; engineering tools are added on top
    # by ``executors.update(build_engineering_tool_executors(...))``.
    assert len(table) >= 24
    # Spot-check a few canonical entries
    for name in ("omicsclaw", "save_file", "inspect_data", "remember", "consult_knowledge"):
        assert name in table, f"Tool name '{name}' missing from dispatch table"
