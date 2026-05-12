"""Skill-aware preflight modules.

Each Skill that needs to validate user-supplied input data before its
analysis script is invoked owns a sibling module here. The first such
module is ``sc_batch`` — `sc-batch-integration`'s batch-key detection
and auto-preparation workflow. As more Skills migrate their preflight
checks, this directory will grow into a generic preflight engine that
consults a Skill's declared prerequisite schema instead of hard-coding
per-Skill helpers; today it's just the location.

Per ADR 0001 the migration started with ``sc-batch`` because that body
of code (~390 LOC) was sitting in ``bot/core.py`` despite being
single-cell domain business logic, not entry-layer infrastructure.

No exported API in this package: callers should import directly from
the per-Skill submodule (``omicsclaw.runtime.preflight.sc_batch``).
"""

from __future__ import annotations
