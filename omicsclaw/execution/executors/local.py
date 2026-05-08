"""``LocalExecutor`` — in-process baseline.

Legacy placeholder executor that preserves the old
``executor_not_implemented`` behavior for tests or explicit fallback wiring.
The default app/remote path now uses ``SkillRunnerExecutor``.
"""

from __future__ import annotations

from .base import JobContext, JobOutcome

EXECUTOR_NOT_IMPLEMENTED_LINE = (
    "executor_not_implemented: see omicsclaw/execution/ "
    "for the upcoming Executor abstraction"
)


class LocalExecutor:
    async def run(self, ctx: JobContext) -> JobOutcome:  # noqa: D401
        return JobOutcome(
            exit_code=1,
            error="executor_not_implemented",
            stdout_text=EXECUTOR_NOT_IMPLEMENTED_LINE,
        )
