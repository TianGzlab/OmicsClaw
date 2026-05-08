"""OmicsClaw — Multi-omics analysis skill library."""

from .version import __version__

__all__ = ["__version__", "run_skill"]


def __getattr__(name: str):
    if name == "run_skill":
        from omicsclaw.core.skill_runner import run_skill

        return run_skill
    raise AttributeError(f"module 'omicsclaw' has no attribute {name!r}")
