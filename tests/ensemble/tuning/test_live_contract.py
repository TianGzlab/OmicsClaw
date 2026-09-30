"""The prompt contracts against a real model (``-m eval``, ``OMICSCLAW_TUNING_LIVE=1``).

One K decision and one stage-1 proposal on the fixture evidence: the replies
must satisfy the contracts within the retry budget. This measures the
contract, not the quality of the choice.
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(os.environ.get("OMICSCLAW_TUNING_LIVE") != "1", reason="set OMICSCLAW_TUNING_LIVE=1"),
]


def _model():
    """The provider of the repository's ``.env`` (the test isolation clears those keys from ``os.environ``)."""
    from pathlib import Path

    from omicsclaw.ensemble.tuning.llm import LLMSettings
    from omicsclaw.provider import provider_from_env, resolve_config

    env = dict(os.environ)
    dotenv = Path(__file__).resolve().parents[3] / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    resolved = resolve_config(env=env)
    return provider_from_env(env=env), LLMSettings(model=resolved.model, provider=resolved.provider,
                                                   temperature=resolved.temperature)


def test_a_real_model_follows_both_contracts(tmp_path):
    from omicsclaw.ensemble.tuning.ledger import Ledger
    from omicsclaw.ensemble.tuning.llm import decide_k, propose
    from tests.ensemble.tuning import fixtures

    model, settings = _model()
    ledger = Ledger(tmp_path)

    async def fetch(ks):
        return fixtures.markers_document(full=(4, 6, *ks))

    outcome = asyncio.run(decide_k(model, fixtures.k_input(), settings=settings, ledger=ledger, fetch_markers=fetch))
    assert outcome.decision is not None, outcome.failure
    assert outcome.decision.chosen_k in fixtures.GRID

    def accept(params):
        if not isinstance(params, dict):
            return None, "not an object"
        return dict(params), ""

    proposals = asyncio.run(propose(model, fixtures.propose_input(), settings=settings, ledger=ledger, accept=accept))
    assert not proposals.failure and len(proposals.accepted) == 3
