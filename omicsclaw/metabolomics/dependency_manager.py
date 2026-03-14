"""Dependency management for metabolomics packages."""

from dataclasses import dataclass


@dataclass
class DependencyInfo:
    import_name: str
    install_cmd: str
    description: str


DEPENDENCY_REGISTRY: dict[str, DependencyInfo] = {
    "xcms": DependencyInfo("rpy2", "pip install rpy2", "XCMS via R"),
    "metaboanalyst": DependencyInfo("rpy2", "pip install rpy2", "MetaboAnalyst via R"),
    "mzmine": DependencyInfo("pymzml", "pip install pymzml", "mzML parsing"),
    "ms-entropy": DependencyInfo("ms_entropy", "pip install ms-entropy", "Spectral entropy"),
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
