"""
Disease configuration loader for the Clinical Trial Landscape Scanner.

Loads disease-specific settings (mechanism taxonomy, drug normalization,
descriptions, colors, highlight sections) from YAML config files in
disease_configs/. Falls back to generic intervention-type classification
when no config is available.
"""

import os
import yaml

CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "disease_configs")

# Default color palette for auto-assignment when no colors configured
DEFAULT_PALETTE = [
    "#1B4F72", "#E74C3C", "#27AE60", "#F39C12", "#8E44AD",
    "#E67E22", "#2E86C1", "#1ABC9C", "#D4AC0D", "#95A5A6",
    "#C0392B", "#2980B9", "#16A085", "#D35400", "#7D3C98",
]


def load_disease_config(disease_id):
    """
    Load disease configuration from YAML file.

    Parameters
    ----------
    disease_id : str or None
        Disease identifier (e.g., "ibd"). Looks for disease_configs/{disease_id}.yaml.
        If None or file not found, returns None (pipeline uses generic fallback).

    Returns
    -------
    dict or None
        Parsed config dict, or None if no config available.
    """
    if not disease_id:
        return None
    config_path = os.path.join(CONFIGS_DIR, f"{disease_id}.yaml")
    if not os.path.exists(config_path):
        print(f"  (No disease config found at {config_path} — using generic classification)")
        return None
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    print(f"  Loaded disease config: {config.get('disease_name', disease_id)}")
    return config


def get_default_conditions(config):
    """Get default ClinicalTrials.gov conditions from config."""
    if not config:
        return []
    return config.get("default_conditions", [])


def get_mechanism_patterns(config):
    """
    Get mechanism patterns list from config.
    
    Returns list of (name, [(pattern, is_regex), ...]) tuples
    matching the format used by classify_mechanism().
    Returns empty list if no config (triggers generic fallback).
    """
    if not config:
        return []
    raw = config.get("mechanism_patterns", [])
    result = []
    for entry in raw:
        name = entry["name"]
        patterns = [(p[0], p[1]) for p in entry["patterns"]]
        result.append((name, patterns))
    return result


def get_drug_normalization(config):
    """Get drug normalization regex→canonical dict from config."""
    if not config:
        return {}
    return config.get("drug_normalization", {})


def get_mechanism_descriptions(config):
    """Get long-form mechanism descriptions dict for markdown reports."""
    if not config:
        return {}
    return config.get("mechanism_descriptions", {})


def get_mechanism_briefs(config):
    """Get short-form mechanism descriptions dict for PDF reports."""
    if not config:
        return {}
    return config.get("mechanism_briefs", {})


def get_mechanism_colors(config):
    """
    Get mechanism→color dict from config.
    Falls back to auto-generated palette if not configured.
    """
    if not config:
        return {}
    return config.get("mechanism_colors", {})


def auto_assign_colors(mechanisms, config=None):
    """
    Assign colors to mechanisms, using config colors where available
    and auto-generating for unknown mechanisms.
    """
    configured = get_mechanism_colors(config) if config else {}
    result = dict(configured)
    palette_idx = 0
    for mech in mechanisms:
        if mech not in result:
            result[mech] = DEFAULT_PALETTE[palette_idx % len(DEFAULT_PALETTE)]
            palette_idx += 1
    return result


def get_indication_categories(config):
    """Get indication decomposition rules from config."""
    if not config:
        return []
    return config.get("indication_categories", [])


def get_highlight_mechanisms(config):
    """Get list of mechanism highlight section specs from config."""
    if not config:
        return []
    return config.get("highlight_mechanisms", [])


def get_highlight_sponsors(config):
    """Get list of sponsor highlight section specs from config."""
    if not config:
        return []
    return config.get("highlight_sponsors", [])


def get_executive_highlights(config):
    """Get executive summary highlight specs from config."""
    if not config:
        return {}
    return config.get("executive_highlights", {})


def get_disease_name(config, default="Clinical Trial"):
    """Get the full disease name from config."""
    if not config:
        return default
    return config.get("disease_name", default)


def get_disease_short(config, default=""):
    """Get the short disease abbreviation from config."""
    if not config:
        return default
    return config.get("disease_name_short", default)

