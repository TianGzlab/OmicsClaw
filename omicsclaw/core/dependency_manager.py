import importlib
import importlib.util
import sys

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

    # Spatial-r-bridge standalone
    "rpy2": "spatial-r-bridge",
    "anndata2ri": "spatial-r-bridge",
    "pydeseq2": "spatial-r-bridge",

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
    "scrublet": "singlecell",

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
        "spatial": importlib.util.find_spec("rpy2") is not None or importlib.util.find_spec("scvi") is not None,
        "singlecell": importlib.util.find_spec("scrublet") is not None,
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
        "spatial-r-bridge": importlib.util.find_spec("rpy2") is not None,
        "banksy": importlib.util.find_spec("pybanksy") is not None,
    }
    return tiers_status
    
