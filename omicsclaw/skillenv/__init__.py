"""``omicsclaw.skillenv`` — which Python packages a skill needs, whether ``bash`` can import them, and adding them.

``registry`` reads a skill's ``## Dependencies`` line and the dependency
registry file ``<skills root>/_sdk/deps.py`` (as a file, never imported);
``probe`` runs fixed Python programs where ``bash`` runs; ``report``
renders what it found as a note for ``use_skill``. ``sources`` checks what
reaches pip, ``overlay`` builds overlay environments over the base
interpreter, and ``tool`` is ``install_skill_deps``; they are not imported
here. Inside ``omicsclaw`` this package imports only ``schema``, ``tools``
and ``skills``.
"""

from .probe import (
    LocalProbeRunner,
    ProbeError,
    ProbeResult,
    ProbeRunner,
    SandboxProbeRunner,
    parse_probe,
    probe_command,
    run_probe,
)
from .registry import (
    DependencyFormatError,
    ProbePlan,
    RegistryFormatError,
    Resolution,
    parse_dependencies,
    probe_plan,
    read_registry,
    resolve,
)
from .report import SandboxContext, render_annotation

__all__ = [
    "DependencyFormatError",
    "LocalProbeRunner",
    "ProbeError",
    "ProbePlan",
    "ProbeResult",
    "ProbeRunner",
    "RegistryFormatError",
    "Resolution",
    "SandboxContext",
    "SandboxProbeRunner",
    "parse_dependencies",
    "parse_probe",
    "probe_command",
    "probe_plan",
    "read_registry",
    "render_annotation",
    "resolve",
]
