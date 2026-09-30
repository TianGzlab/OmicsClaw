"""BANKSY's sub-environment fallback reaches ``external_env`` again (plan 0062 case 9).

Before the move, the fallback imported ``omicsclaw.core.external_env``, whose
own import of the deleted ``omicsclaw.skill`` package raised
``ModuleNotFoundError`` in place of the designed ``EnvNotFoundError``.
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("anndata")

import skills._sdk.external_env as external_env
from skills._sdk.external_env import EnvNotFoundError


def test_missing_banksy_and_missing_sub_env_raise_env_not_found(monkeypatch):
    from skills.spatial._lib import domains

    monkeypatch.setitem(sys.modules, "banksy", None)
    monkeypatch.delitem(sys.modules, "skills.spatial._lib._runners.banksy_runner", raising=False)
    monkeypatch.setattr(external_env, "is_env_available", lambda env: False)

    with pytest.raises(EnvNotFoundError, match="omicsclaw_banksy"):
        domains.identify_domains_banksy(object())


def test_pybanksy_availability_consults_the_sub_env(monkeypatch):
    from importlib import util

    asked: list[str] = []

    def fake_is_env_available(env: str) -> bool:
        asked.append(env)
        return False

    real_find_spec = util.find_spec
    monkeypatch.setattr(
        util, "find_spec",
        lambda name, *a, **k: None if name == "banksy" else real_find_spec(name, *a, **k),
    )
    monkeypatch.setattr(external_env, "is_env_available", fake_is_env_available)

    from skills._sdk import deps

    deps._check_spec.cache_clear()
    try:
        assert deps.is_available("pybanksy") is False
        assert asked == ["omicsclaw_banksy"]
    finally:
        deps._check_spec.cache_clear()
