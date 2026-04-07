"""Parameter search space for autoagent optimization.

Mirrors AutoAgent's *editable harness section* — defines what the LLM
meta-agent is allowed to change and within what bounds.

The search space is constructed from a skill's ``param_hints`` (declared in
SKILL.md and loaded via the skill registry) plus optional user overrides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParameterDef:
    """A single tunable parameter.

    Attributes:
        name: Internal parameter name (e.g. ``"harmony_theta"``).
        param_type: One of ``"float"``, ``"int"``, ``"bool"``, ``"categorical"``.
        default: The default value from ``param_hints.defaults``.
        low: Lower bound (numeric types).
        high: Upper bound (numeric types).
        choices: Allowed values (categorical type).
        cli_flag: The CLI flag forwarded to the skill script
                  (e.g. ``"--harmony-theta"``).
        tip: Human-readable hint from ``param_hints.tips``.
    """

    name: str
    param_type: str  # "float" | "int" | "bool" | "categorical"
    default: Any
    low: float | None = None
    high: float | None = None
    choices: list[Any] | None = None
    cli_flag: str = ""
    tip: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.param_type,
            "default": self.default,
            "cli_flag": self.cli_flag,
        }
        if self.low is not None:
            d["low"] = self.low
        if self.high is not None:
            d["high"] = self.high
        if self.choices is not None:
            d["choices"] = self.choices
        if self.tip:
            d["tip"] = self.tip
        return d


@dataclass(frozen=True)
class FixedParameterDef:
    """A non-tunable method parameter that must stay fixed during optimization.

    These parameters still matter for launchability. Some have defaults and can
    be overridden; others are required runtime inputs that must be provided by
    the caller before optimization can start.
    """

    name: str
    param_type: str  # "float" | "int" | "bool" | "string"
    required: bool
    default: Any | None = None
    has_default: bool = False
    cli_flag: str = ""
    tip: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.param_type,
            "required": self.required,
            "cli_flag": self.cli_flag,
        }
        if self.has_default:
            d["default"] = self.default
        if self.tip:
            d["tip"] = self.tip
        return d


@dataclass(frozen=True)
class MethodSurface:
    """Concrete method capability derived from raw ``param_hints``."""

    skill_name: str
    method: str
    tunable: list[ParameterDef]
    fixed: list[FixedParameterDef]

    def required_fixed_names(self) -> list[str]:
        return [param.name for param in self.fixed if param.required]


@dataclass
class SearchSpace:
    """The full parameter surface that the meta-agent can explore.

    ``tunable`` contains the parameters the LLM may change.
    ``fixed`` contains parameters that the user locked (e.g. ``batch_key``).
    """

    skill_name: str
    method: str
    tunable: list[ParameterDef] = field(default_factory=list)
    fixed: dict[str, Any] = field(default_factory=dict)

    # ----- construction helpers -----

    @classmethod
    def from_param_hints(
        cls,
        skill_name: str,
        method: str,
        param_hints: dict[str, Any],
        fixed_params: dict[str, Any] | None = None,
    ) -> SearchSpace:
        """Build a ``SearchSpace`` from a skill registry's ``param_hints``.

        Parameters
        ----------
        param_hints:
            The ``param_hints[method]`` dict from SKILL.md.  Expected shape::

                {
                    "params": ["batch_key", "harmony_theta", ...],
                    "defaults": {"batch_key": "batch", "harmony_theta": 2.0, ...},
                    "tips": ["--harmony-theta: diversity penalty", ...],
                    "priority": "harmony_theta -> integration_pcs",
                }

        fixed_params:
            Parameters the user wants to lock (not optimized).  Keys present
            here are removed from the tunable set.
        """
        fixed = dict(fixed_params or {})
        method_surface = build_method_surface(skill_name, method, param_hints)
        tunable = [param for param in method_surface.tunable if param.name not in fixed]

        return cls(
            skill_name=skill_name,
            method=method,
            tunable=tunable,
            fixed=fixed,
        )

    def defaults_dict(self) -> dict[str, Any]:
        """Return a dict of default parameter values (tunable only)."""
        return {p.name: p.default for p in self.tunable}

    def to_summary(self) -> str:
        """Human-readable summary for the LLM directive."""
        lines = [f"Search space for {self.skill_name} / {self.method}:"]
        for p in self.tunable:
            range_str = ""
            if p.low is not None and p.high is not None:
                range_str = f"  range: [{p.low}, {p.high}]"
            elif p.choices is not None:
                range_str = f"  choices: {p.choices}"
            tip_str = f"  ({p.tip})" if p.tip else ""
            lines.append(
                f"  - {p.name} ({p.param_type}): default={p.default}"
                f"{range_str}{tip_str}"
            )
        if self.fixed:
            lines.append("  Fixed (not optimized):")
            for k, v in self.fixed.items():
                lines.append(f"    {k} = {v}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _infer_type(value: Any) -> str:
    """Infer the parameter type from its default value."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "string"


def build_method_surface(
    skill_name: str,
    method: str,
    param_hints: dict[str, Any],
) -> MethodSurface:
    """Derive the real optimization surface from raw ``param_hints``.

    The result is the single source of truth for:
    - which parameters are actually tunable by the autoagent
    - which parameters must be supplied as fixed runtime inputs
    - which methods are genuinely launchable from the optimize UI
    """
    params: list[str] = param_hints.get("params", [])
    defaults: dict[str, Any] = param_hints.get("defaults", {})
    tips_list: list[str] = param_hints.get("tips", [])
    tip_map = _parse_tips(tips_list)

    tunable: list[ParameterDef] = []
    fixed: list[FixedParameterDef] = []

    for raw_name in params:
        pname = str(raw_name).strip()
        if not pname:
            continue

        has_default = pname in defaults and defaults.get(pname) is not None
        default = defaults.get(pname)
        inferred_type = _infer_type(default) if has_default else "string"
        cli_flag = _param_to_cli_flag(pname)
        tip = tip_map.get(pname, "")

        if has_default and inferred_type in {"float", "int", "bool"}:
            low, high = _infer_range(inferred_type, default)
            choices = None
            if inferred_type == "bool":
                choices = [True, False]
                low, high = None, None
            tunable.append(
                ParameterDef(
                    name=pname,
                    param_type=inferred_type,
                    default=default,
                    low=low,
                    high=high,
                    choices=choices,
                    cli_flag=cli_flag,
                    tip=tip,
                )
            )
            continue

        fixed.append(
            FixedParameterDef(
                name=pname,
                param_type=inferred_type,
                required=not has_default,
                default=default,
                has_default=has_default,
                cli_flag=cli_flag,
                tip=tip,
            )
        )

    return MethodSurface(
        skill_name=skill_name,
        method=method,
        tunable=tunable,
        fixed=fixed,
    )


def _infer_range(
    param_type: str,
    default: Any,
) -> tuple[float | None, float | None]:
    """Infer a reasonable search range from the default value."""
    if param_type == "float":
        d = float(default)
        if d == 0.0:
            return (0.0, 1.0)
        low = max(0.0, d * 0.2)
        high = d * 5.0
        return (round(low, 6), round(high, 6))

    if param_type == "int":
        d = int(default)
        if d <= 0:
            return (0, 10)
        low = max(1, d // 4)
        high = d * 4
        return (float(low), float(high))

    return (None, None)


def _param_to_cli_flag(param_name: str) -> str:
    """Convert a ``param_hints`` parameter name to a CLI flag."""
    from omicsclaw.autoagent.constants import param_to_cli_flag
    return param_to_cli_flag(param_name)


def _parse_tips(tips: list[str]) -> dict[str, str]:
    """Parse a list of tip strings into a {param_name: tip} lookup.

    Expected format: ``"--harmony-theta: diversity penalty; raise for mixing"``
    """
    result: dict[str, str] = {}
    for tip in tips:
        tip = tip.strip()
        if not tip.startswith("--"):
            continue
        # Split at first colon
        colon_idx = tip.find(":")
        if colon_idx == -1:
            continue
        flag_part = tip[:colon_idx].strip()
        desc_part = tip[colon_idx + 1 :].strip()
        # Convert --harmony-theta to harmony_theta
        param_name = flag_part.lstrip("-").replace("-", "_")
        result[param_name] = desc_part
    return result
