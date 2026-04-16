"""``LocalExecutor`` — in-process baseline.

MVP-1 keeps the ``executor_not_implemented`` behavior of the previous
inline stub: return a failed outcome with a diagnostic stdout tail. The
abstraction makes this a 10-line swap once the real subprocess runner
(spawning ``python omicsclaw.py run <skill> …``) is ready.
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
