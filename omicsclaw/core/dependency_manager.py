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
    
    # Spatial domain dependencies
    "SpaGCN": "spatial-domains",
    "torch": "spatial-domains",
    "torch_geometric": "spatial",
    "scvi": "spatial",
    "tangram": "spatial",
    "cell2location": "spatial",
    "scvelo": "spatial",
    "liana": "spatial",
    "cellphonedb": "spatial",
    "fastccc": "spatial",
    "cellrank": "spatial",
    "palantir": "spatial",
    "gseapy": "spatial",
    "SpatialDE": "spatial",
    "esda": "spatial",
    "libpysal": "spatial",
    "pysal": "spatial",
    "infercnvpy": "spatial",
    "harmonypy": "spatial",
    "bbknn": "spatial",
    "scanorama": "spatial",
    "ot": "spatial",  # POT
    "paste": "spatial",
    "pydeseq2": "spatial",
    "rpy2": "spatial",
    "anndata2ri": "spatial",
    
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
        "genomics": False, # Genomics currently uses external CLI tools generally, placeholders for now
        "proteomics": False,
        "metabolomics": False,
    }
    return tiers_status
    
