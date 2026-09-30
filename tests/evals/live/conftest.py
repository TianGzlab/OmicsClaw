"""Fixtures for the real-model routing eval (``-m eval``, ``OMICSCLAW_EVAL_LIVE=1``).

The provider comes from the repository's ``.env`` merged over
``os.environ``: ``tests/conftest.py`` clears the ``.env`` keys from the
process environment before every test, so the file is read here.
``OMICSCLAW_EVAL_LIVE_PROVIDER`` and ``OMICSCLAW_EVAL_LIVE_MODEL``
override it, and ``OMICSCLAW_EVAL_LIVE_TRIALS`` sets the trials per seed
(default 3). At the end of the session ``live_report.json`` and
``live_report.md`` are written to ``OMICSCLAW_EVAL_REPORT_DIR``
(default ``build/live-eval``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from omicsclaw.evals import StubResult
from omicsclaw.evals.live import build_report, run_meta, write_json, write_markdown
from omicsclaw.evals.stubs import REPO_ROOT

_SEEDS = pytest.StashKey[list]()
_SETUP = pytest.StashKey[object]()
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "skill_runs"


@dataclass(frozen=True)
class LiveSetup:
    """What every live trial shares: the resolved provider config, stubs and trial count."""

    config: object
    trials: int
    stubs: dict

    def provider(self):
        """A fresh provider for one trial."""
        from omicsclaw.provider import provider_for

        return provider_for(self.config)

    @property
    def app_config(self) -> dict:
        """The :class:`~omicsclaw.entry.AppConfig` overrides that make the window the production one."""
        return {"provider": self.config.provider, "model": self.config.model}


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    dotenv = REPO_ROOT / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


@pytest.fixture(scope="session")
def live_setup(request) -> LiveSetup:
    """The session's provider config, fixture stubs and trial count."""
    from omicsclaw.provider import resolve_config

    env = _environment()
    config = resolve_config(
        env.get("OMICSCLAW_EVAL_LIVE_PROVIDER", ""),
        env.get("OMICSCLAW_EVAL_LIVE_MODEL", ""),
        env=env,
    )
    stubs = {path.stem: StubResult.load(path) for path in sorted(FIXTURES.glob("*.json"))}
    setup = LiveSetup(config=config, trials=int(env.get("OMICSCLAW_EVAL_LIVE_TRIALS", "3")), stubs=stubs)
    request.config.stash[_SETUP] = setup
    return setup


@pytest.fixture
def live_seeds(request) -> list:
    """The session's list of :class:`~omicsclaw.evals.live.SeedReport`."""
    return request.config.stash.setdefault(_SEEDS, [])


def pytest_sessionfinish(session, exitstatus):
    seeds = session.config.stash.get(_SEEDS, [])
    setup = session.config.stash.get(_SETUP, None)
    if not seeds or setup is None:
        return
    config = setup.config
    meta = run_meta(config.provider, config.model, config.base_url, config.temperature, setup.trials)
    report = build_report(meta, seeds)
    directory = Path(os.environ.get("OMICSCLAW_EVAL_REPORT_DIR") or "build/live-eval")
    write_json(report, directory / "live_report.json")
    write_markdown(report, directory / "live_report.md")
