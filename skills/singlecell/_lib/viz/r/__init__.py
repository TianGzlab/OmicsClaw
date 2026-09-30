"""Python wrapper for OmicsClaw R Enhanced plotting via registry.R.

All skills call ``call_r_plot()`` to invoke R renderers.  R failures
produce Python warnings -- they never crash the skill.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from skills._sdk.r_script_runner import (
    RScriptError,
    RScriptRunner,
    RScriptTimeoutError,
)

_REGISTRY_R = Path(__file__).parent / "registry.R"
_runner = RScriptRunner(scripts_dir=_REGISTRY_R.parent, timeout=120)

__all__ = ["call_r_plot"]


def call_r_plot(
    renderer: str,
    figure_data_dir: Path,
    out_path: Path,
    params: dict | None = None,
) -> Path:
    """Invoke one R Enhanced renderer via registry.R.

    Parameters
    ----------
    renderer : str
        Name of the renderer function registered in R_PLOT_REGISTRY.
    figure_data_dir : Path
        Directory containing figure_data CSVs (passed as data_dir to R).
    out_path : Path
        Absolute path for the output PNG.
    params : dict, optional
        Extra key=value parameters forwarded to the R function.

    Returns
    -------
    Path
        *out_path* (whether or not the file was actually created).

    Notes
    -----
    On failure a :class:`UserWarning` is emitted -- the function never raises.
    """
    kv_args = [f"{k}={v}" for k, v in (params or {}).items()]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _runner.run_script(
            _REGISTRY_R,
            args=[renderer, str(figure_data_dir), str(out_path)] + kv_args,
            expected_outputs=[out_path.name],
            output_dir=out_path.parent,
        )
    except (RScriptError, RScriptTimeoutError, FileNotFoundError) as exc:
        warnings.warn(
            f"R Enhanced plot '{renderer}' failed (Python figures unaffected): {exc}",
            stacklevel=2,
        )
    return out_path
