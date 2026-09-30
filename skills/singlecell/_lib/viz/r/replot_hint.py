"""Record the R Enhanced renderers a single-cell skill offers in its ``result.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skills._sdk.result import load_result_json, write_owned_text


def write_replot_hint(
    output_dir: str | Path,
    skill_alias: str,
    _r_enhanced_plots=None,  # deprecated: now auto-resolved from SKILL_RENDERERS
) -> None:
    """Add a ``replot`` block to the ``result.json`` in *output_dir* (idempotent).

    The block lists the R Enhanced renderers registered for *skill_alias* in
    ``SKILL_RENDERERS`` with their default parameters. Nothing is written for
    a skill with no renderers or when ``result.json`` is missing or
    unreadable. Never raises.
    """
    try:
        output_dir = Path(output_dir)
        envelope = load_result_json(output_dir)
        if not isinstance(envelope, dict):
            return

        from skills.singlecell._lib.viz.r.renderer_params import (
            RENDERER_PARAMS,
            SKILL_RENDERERS,
        )

        renderers = SKILL_RENDERERS.get(skill_alias)
        if not renderers:
            return

        renderer_info: dict[str, Any] = {}
        for rname in renderers:
            schema = RENDERER_PARAMS.get(rname, {})
            renderer_info[rname] = {
                "params": {k: v["default"] for k, v in schema.items() if v.get("default") is not None}
            }

        envelope["replot"] = {
            "available": True,
            "command": f"python omicsclaw.py replot {skill_alias} --output {output_dir}",
            "renderers": renderer_info,
        }

        write_owned_text(
            output_dir / "result.json",
            output_root=output_dir,
            text=json.dumps(envelope, indent=2, default=str),
        )
    except Exception:
        pass
