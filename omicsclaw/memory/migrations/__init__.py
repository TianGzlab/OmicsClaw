"""Lightweight migrations framework for OmicsClaw memory schema.

Each migration is a module exposing module-level ``VERSION`` (str),
``DESCRIPTION`` (str), and ``async def apply(db: DatabaseManager) -> None``.
The runner discovers them, applies pending ones in version-sorted order,
and records applications in the ``_schema_version`` table.
"""

from omicsclaw.memory.migrations.runner import run_pending

__all__ = ["run_pending"]
