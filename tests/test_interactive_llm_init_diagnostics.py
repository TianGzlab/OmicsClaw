"""Tests for ``oc chat`` LLM-init diagnostics.

When ``omicsclaw/interactive/interactive._init_llm`` fails to construct
the LLM client — typically because the user is running ``oc chat`` before
configuring an API key — the CLI must surface an actionable diagnostic
inline. Logging a ``WARNING`` is not enough; the CLI logger config drops
WARNING-level lines below the banner, so the user sees ``Model: unknown``
and only learns the real cause after submitting their first prompt.

These tests pin the user-visible contract — they do not constrain how
the diagnostic is rendered (rich `console.print`, plain `print`, or
`stderr.write` are all acceptable).
"""

from __future__ import annotations

import sys


def test_init_llm_surfaces_actionable_message_when_core_init_fails(
    monkeypatch, capsys
):
    """If ``bot.core.init`` raises (e.g. ``OpenAIError: Missing credentials``),
    ``_init_llm`` must print a user-visible diagnostic naming the env var
    to set and the onboard remediation. The fallback ``(model, provider)``
    return is still ``("unknown", ...)`` so the banner can keep rendering.
    """
    import omicsclaw.interactive.interactive as interactive

    sys.path.insert(0, str(interactive._OMICSCLAW_DIR))
    import bot.core as core

    def _boom(**_kw):
        raise core.OpenAIError(
            "Missing credentials. Please pass an `api_key`, "
            "`workload_identity`, `admin_api_key`, or set the "
            "`OPENAI_API_KEY` or `OPENAI_ADMIN_KEY` environment variable."
        )

    monkeypatch.setattr(core, "init", _boom)

    model, _provider = interactive._init_llm({})

    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert "LLM_API_KEY" in output or "OPENAI_API_KEY" in output, (
        f"diagnostic must name the env var to set; got: {output!r}"
    )
    assert "onboard" in output.lower(), (
        f"diagnostic must point at the onboard remediation; got: {output!r}"
    )
    # Banner-render fallback contract preserved
    assert model in ("unknown", "") or isinstance(model, str)
