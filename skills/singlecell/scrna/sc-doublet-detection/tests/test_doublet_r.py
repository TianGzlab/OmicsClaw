"""R doublet methods consume local Matrix Market files."""

import numpy as np
import pytest

from skills._sdk.notebook import load_demo, load_skill
from skills._sdk.r_script_runner import RScriptRunner
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR


@pytest.mark.requires_r
@pytest.mark.parametrize("method,packages", [
    ("doubletfinder", ["Seurat", "DoubletFinder", "Matrix"]),
    ("scdblfinder", ["scDblFinder", "SingleCellExperiment", "Matrix"]),
])
def test_r_doublet_method_annotates_real_counts(method, packages):
    runner = RScriptRunner(verbose=False)
    if not runner.check_r_available() or runner.get_missing_packages(packages):
        pytest.skip(f"R packages are unavailable for {method}")
    adata = load_demo("pbmc3k_raw")[:350].copy()
    api = load_skill("sc-doublet-detection")
    result = api.detect_doublets(adata, method=method, random_state=11)
    assert result is adata and result.n_obs == 350
    assert np.isfinite(result.obs["doublet_score"]).all()
    assert api.run_info(result)["executed_method"] == method
    assert api.run_info(result)["fallback_used"] is False


@pytest.mark.requires_r
@pytest.mark.parametrize("script", ["sc_doubletfinder.R", "sc_scdblfinder.R", "sc_scds.R", "sc_mast_de.R"])
def test_matrix_exchange_r_script_parses(script):
    import shutil
    import subprocess
    rscript = shutil.which("Rscript")
    if rscript is None:
        pytest.skip("Rscript is unavailable")
    completed = subprocess.run([rscript, "-e", "invisible(parse(commandArgs(TRUE)[1]))", str(_SDK_R_SCRIPTS_DIR / script)],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
