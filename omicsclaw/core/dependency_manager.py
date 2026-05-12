import importlib
import importlib.util
import os
import subprocess
import sys

from omicsclaw.core.external_env import is_env_available

# Mappings of packages to their respective domain tiers.
DOMAIN_TIERS = {
    # Core dependencies (always installed via pip install -e .)
    "scanpy": "core",
    "anndata": "core",
    "squidpy": "core",
    "numpy": "core",
    "pandas": "core",
    "scipy": "core",
    "scikit-learn": "core",

    # Spatial-domains standalone (deep learning domain methods)
    "SpaGCN": "spatial-domains",
    "torch": "spatial-domains",

    # Spatial-velocity standalone
    "scvelo": "spatial-velocity",

    # Spatial-cnv standalone
    "infercnvpy": "spatial-cnv",

    # Spatial-enrichment standalone
    "gseapy": "spatial-enrichment",

    # Spatial-communication standalone
    "liana": "spatial-communication",
    "cellphonedb": "spatial-communication",
    "fastccc": "spatial-communication",

    # Spatial-integration standalone
    "harmonypy": "spatial-integration",
    "bbknn": "spatial-integration",
    "scanorama": "spatial-integration",

    # Spatial-registration standalone
    "ot": "spatial-registration",  # POT
    "paste": "spatial-registration",

    # R-based methods (require Rscript on PATH, no Python package needed)
    "pydeseq2": "spatial-condition",

    # Spatial domain dependencies (remaining in spatial tier)
    "torch_geometric": "spatial",
    "scvi": "spatial",
    "tangram": "spatial",
    "cell2location": "spatial",
    "cellrank": "spatial",
    "palantir": "spatial",
    "SpatialDE": "spatial",
    "esda": "spatial",
    "libpysal": "spatial",
    "pysal": "spatial",

    # Single-cell domain dependencies
    "scrublet": "singlecell-doublet",
    "doubletdetection": "singlecell-doublet",
    "celltypist": "singlecell-annotation",
    "louvain": "singlecell-clustering",
    "phate": "singlecell-clustering",
    "igraph": "singlecell-clustering",
    "leidenalg": "singlecell-clustering",
    "multiqc": "singlecell-upstream",
    "kb_python": "singlecell-upstream",
    "scvelo": "singlecell-velocity",

    # Other domains can be added here as the software grows
}

def check_dependencies(skill_name: str, required_packages: list[str]) -> bool:
    """
    Checks if a list of required packages are installed.
    If missing, raises a formatted ImportError suggesting the exact installation command.
    """
    missing_packages = []
    tiers_needed = set()
    
    for pkg in required_packages:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing_packages.append(pkg)
            tier = DOMAIN_TIERS.get(pkg, "full")
            tiers_needed.add(tier)
            
    if missing_packages:
        tiers_str = ",".join(sorted(tiers_needed))
        if len(tiers_needed) == 1 and list(tiers_needed)[0] != "full":
            install_cmd = f'pip install -e ".[{list(tiers_needed)[0]}]"'
        else:
            install_cmd = f'pip install -e ".[{tiers_str}]"'
            
        error_msg = (
            f"\n[OmicsClaw Environment Error]\n"
            f"Skill '{skill_name}' requires optional dependencies that are missing: {', '.join(missing_packages)}.\n"
            f"To install them, please run:\n"
            f"    {install_cmd}\n"
        )
        raise ImportError(error_msg)
        
    return True

def get_installed_tiers() -> dict[str, bool]:
    """
    Returns a dictionary of domain tiers and whether their representative packages are installed.
    """
    tiers_status = {
        "core": importlib.util.find_spec("scanpy") is not None,
        "spatial-domains": importlib.util.find_spec("SpaGCN") is not None and importlib.util.find_spec("torch") is not None,
        "spatial": importlib.util.find_spec("scvi") is not None,
        "singlecell": importlib.util.find_spec("scanpy") is not None,
        "singlecell-clustering": importlib.util.find_spec("igraph") is not None and importlib.util.find_spec("leidenalg") is not None,
        "singlecell-batch": importlib.util.find_spec("harmonypy") is not None or importlib.util.find_spec("bbknn") is not None or importlib.util.find_spec("scanorama") is not None or importlib.util.find_spec("scvi") is not None,
        "singlecell-doublet": importlib.util.find_spec("scrublet") is not None or importlib.util.find_spec("doubletdetection") is not None,
        "singlecell-annotation": importlib.util.find_spec("celltypist") is not None,
        "singlecell-enrichment": importlib.util.find_spec("gseapy") is not None,
        "genomics": importlib.util.find_spec("pandas") is not None,  # Uses core deps only
        "proteomics": importlib.util.find_spec("pandas") is not None,  # Uses core deps only
        "metabolomics": importlib.util.find_spec("pandas") is not None,  # Uses core deps only
        "bulkrna": importlib.util.find_spec("pydeseq2") is not None or importlib.util.find_spec("gseapy") is not None,
        # Standalone layers
        "spatial-annotate": importlib.util.find_spec("tangram") is not None or importlib.util.find_spec("scvi") is not None,
        "spatial-deconv": importlib.util.find_spec("flashdeconv") is not None or importlib.util.find_spec("cell2location") is not None,
        "spatial-trajectory": importlib.util.find_spec("cellrank") is not None or importlib.util.find_spec("palantir") is not None,
        "spatial-genes": importlib.util.find_spec("SpatialDE") is not None,
        "spatial-statistics": importlib.util.find_spec("esda") is not None or importlib.util.find_spec("libpysal") is not None,
        "spatial-condition": importlib.util.find_spec("pydeseq2") is not None,
        "spatial-velocity": importlib.util.find_spec("scvelo") is not None,
        "spatial-cnv": importlib.util.find_spec("infercnvpy") is not None,
        "spatial-enrichment": importlib.util.find_spec("gseapy") is not None,
        "spatial-communication": importlib.util.find_spec("liana") is not None,
        "spatial-integration": importlib.util.find_spec("harmonypy") is not None or importlib.util.find_spec("bbknn") is not None,
        "spatial-registration": importlib.util.find_spec("paste") is not None,
        "r-bridge": _check_r_available(),
        "banksy": is_env_available("omicsclaw_banksy"),  # Layer-4 sub-env check
    }
    return tiers_status


def _check_r_available() -> bool:
    """Check if Rscript is on PATH (cached)."""
    candidates = []
    conda_prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if conda_prefix:
        candidates.append(os.path.join(conda_prefix, "bin", "Rscript"))
    if sys.prefix:
        candidates.append(os.path.join(sys.prefix, "bin", "Rscript"))
    candidates.append("Rscript")

    try:
        for rscript in dict.fromkeys(candidates):
            try:
                result = subprocess.run(
                    [rscript, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except FileNotFoundError:
                continue
            if result.returncode == 0:
                return True
        return False
    except subprocess.TimeoutExpired:
        return False


def validate_r_environment(
    required_r_packages: list[str] | None = None,
) -> bool:
    """Check that R is available and required packages are installed.

    Uses subprocess (not rpy2) — no Python-side R dependency needed.

    Parameters
    ----------
    required_r_packages : list[str], optional
        R packages that must be installed.

    Returns
    -------
    True if all checks pass.

    Raises
    ------
    ImportError
        If R is not on PATH or required packages are missing.
    """
    if not _check_r_available():
        raise ImportError(
            "[OmicsClaw] R is not available.\n"
            "Install R (>= 4.3) and ensure 'Rscript' is on your PATH.\n"
            "The recommended path is `bash 0_setup_env.sh` which provisions\n"
            "R 4.3 and all required packages via mamba/conda."
        )

    if required_r_packages:
        from .r_script_runner import RScriptRunner

        runner = RScriptRunner(verbose=False)
        missing = runner.get_missing_packages(required_r_packages)
        if missing:
            raise ImportError(
                f"[OmicsClaw] Missing R packages: {', '.join(missing)}.\n"
                f"The recommended path is `bash 0_setup_env.sh` which provisions\n"
                f"R 4.3 and all required packages via mamba/conda.\n"
                f"Or manually: Rscript -e 'BiocManager::install(c({', '.join(repr(p) for p in missing)}))'"
            )

    return True
    
