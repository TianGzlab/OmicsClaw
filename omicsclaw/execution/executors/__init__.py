"""Executor interface and implementations for remote job dispatch."""

from .base import Executor, JobContext, JobOutcome
from .default import SkillRunnerExecutor, build_default_executor, default_command_factory
from .local import LocalExecutor
from .subprocess import SubprocessExecutor

__all__ = [
    "Executor",
    "JobContext",
    "JobOutcome",
    "LocalExecutor",
    "SkillRunnerExecutor",
    "SubprocessExecutor",
    "build_default_executor",
    "default_command_factory",
]
