"""Shared constants and utilities for the autoagent module."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Numeric constants (single source of truth)
# ---------------------------------------------------------------------------

SCORE_DIFF_EPSILON = 1e-8
"""Two scores are considered equal if their difference is within this."""

CONSECUTIVE_CRASH_LIMIT = 3
"""Stop optimization after this many consecutive crashed trials."""

TRIAL_TIMEOUT_SECONDS = 3600
"""Maximum wall-clock time for a single trial subprocess (1 hour)."""

ERROR_OUTPUT_MAX_CHARS = 1500
"""Truncate stderr/stdout to this many characters in crash records."""

SESSION_TTL_SECONDS = 300
"""Keep finished API sessions for this long before reaping (5 min)."""

LLM_CALL_TIMEOUT_SECONDS = 120
"""Maximum wall-clock time for a single LLM API call (2 min)."""

LLM_MAX_RETRIES = 3
"""Maximum number of retries for transient LLM API failures."""

LLM_RETRY_BASE_SECONDS = 2.0
"""Base delay (seconds) for exponential backoff on LLM retries."""

SUBPROCESS_ENV_WHITELIST: frozenset[str] = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
    "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
    "TMPDIR", "TMP", "TEMP", "SHELL",
    "R_HOME", "R_LIBS", "R_LIBS_USER", "JAVA_HOME",
})
"""Environment variables passed to trial subprocesses.

Only these variables are forwarded from the parent environment to avoid
leaking secrets (API keys, tokens) into skill subprocess environments.
"""

API_RATE_LIMIT_PER_MINUTE = 30
"""Maximum optimization start requests per minute per API instance."""

SILHOUETTE_SAMPLE_SIZE = 5000
"""Max cells to sample for silhouette score computation."""

SPATIAL_K_NEIGHBORS = 8
"""k for spatial local purity (k-nearest neighbor purity)."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_BOOL_FALSE_STRINGS = frozenset({
    "false", "0", "no", "off", "none", "n", "",
})


def parse_bool(value: Any) -> bool:
    """Parse a value to bool, correctly handling string representations.

    ``bool("false")`` in Python is ``True`` (non-empty string).
    This function treats ``"false"``, ``"0"``, ``"no"``, ``"off"`` as ``False``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _BOOL_FALSE_STRINGS
    return bool(value)


def param_to_cli_flag(param_name: str) -> str:
    """Convert a ``param_hints`` parameter name to a CLI flag.

    ``harmony_theta`` -> ``--harmony-theta``
    """
    return "--" + param_name.replace("_", "-")
