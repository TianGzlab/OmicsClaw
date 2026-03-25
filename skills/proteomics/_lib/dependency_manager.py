"""Dependency management for proteomics packages."""

from dataclasses import dataclass


@dataclass
class DependencyInfo:
    import_name: str
    install_cmd: str
    description: str


DEPENDENCY_REGISTRY: dict[str, DependencyInfo] = {
    "pyteomics": DependencyInfo("pyteomics", "pip install pyteomics", "MS data parsing"),
    "pymzml": DependencyInfo("pymzml", "pip install pymzml", "mzML parsing"),
    "ms2pip": DependencyInfo("ms2pip", "pip install ms2pip", "Peptide fragmentation prediction"),
    "mokapot": DependencyInfo("mokapot", "pip install mokapot", "PSM rescoring"),
}


def require(package: str) -> None:
    """Raise ImportError if package not available."""
    if package not in DEPENDENCY_REGISTRY:
        raise ValueError(f"Unknown package: {package}")

    info = DEPENDENCY_REGISTRY[package]
    try:
        __import__(info.import_name)
    except ImportError:
        raise ImportError(
            f"{info.description} requires {package}. Install: {info.install_cmd}"
        )


def check_available(package: str) -> bool:
    """Check if package is available."""
    if package not in DEPENDENCY_REGISTRY:
        return False
    info = DEPENDENCY_REGISTRY[package]
    try:
        __import__(info.import_name)
        return True
    except ImportError:
        return False
