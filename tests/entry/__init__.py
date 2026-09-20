"""Tests for ``omicsclaw/entry/`` — plan 0031.

**No ``pytest-asyncio`` on this machine.** Every asynchronous assertion
is driven by :func:`asyncio.run` over a coroutine written inline, and
anything that could wait carries its own :func:`asyncio.wait_for`: a
suite with no timeout plugin has no way to survive a test that hangs, so
"must time out" is never a criterion here — every such judgement is
rewritten as a fast failure.

``test_entry_is_the_top_layer.py`` is the rule the whole package lives
under and it globs the package, so a module added by a later wave is
covered the moment it exists rather than the moment somebody remembers
to list it.
"""
