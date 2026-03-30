"""
Load experiment IDs from user files for ChIP-Atlas Diff Analysis.

Supports multiple formats:
- Plain text (one experiment ID per line)
- CSV/TSV with experiment ID column
- Two-group format (single file with group column)
"""

import os
import re

import pandas as pd

# Valid experiment ID pattern
EXPERIMENT_ID_PATTERN = re.compile(r"^(SRX|ERX|DRX|GSM)\d+$")


def load_user_data(file_path, column_name=None):
    """
    Load experiment IDs from user file.

    Parameters
    ----------
    file_path : str
        Path to file containing experiment IDs
    column_name : str or None
        Column name for experiment IDs (auto-detects if None)

    Returns
    -------
    list of str
        Experiment IDs (SRX/ERX/DRX/GSM format)

    Supported formats
    -----------------
    - Plain text: one experiment ID per line
    - CSV/TSV: with experiment ID column

    Examples
    --------
    >>> ids = load_user_data("my_experiments.txt")
    >>> ids = load_user_data("samples.csv", column_name="srx_id")
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext == ".txt":
        ids = _load_plain_text(file_path)
    elif file_ext in [".csv", ".tsv", ".tab"]:
        sep = "," if file_ext == ".csv" else "\t"
        ids = _load_delimited(file_path, sep=sep, column_name=column_name)
    else:
        # Try to infer format
        try:
            ids = _load_delimited(file_path, sep=",", column_name=column_name)
        except Exception:
            try:
                ids = _load_delimited(file_path, sep="\t", column_name=column_name)
            except Exception:
                ids = _load_plain_text(file_path)

    # Validate IDs
    valid, invalid = [], []
    for exp_id in ids:
        if EXPERIMENT_ID_PATTERN.match(exp_id):
            valid.append(exp_id)
        else:
            invalid.append(exp_id)

    if invalid:
        print(f"   Warning: {len(invalid)} IDs don't match expected format "
              f"(SRX/ERX/DRX/GSM): {invalid[:5]}")

    if not valid and not invalid:
        raise ValueError(f"No experiment IDs found in {file_path}")

    # Return all IDs (valid + invalid) so users with non-standard IDs aren't blocked
    all_ids = valid + invalid if invalid else valid
    print(f"✓ Data loaded successfully: {len(all_ids)} experiment IDs")
    return all_ids


def load_experiment_groups(file_a_path=None, file_b_path=None, group_file_path=None,
                           group_column="group", id_column=None):
    """
    Load two groups of experiment IDs.

    Option 1: Two separate files (file_a_path + file_b_path)
    Option 2: Single file with group column (group_file_path)

    Parameters
    ----------
    file_a_path : str or None
        Path to group A experiment IDs file
    file_b_path : str or None
        Path to group B experiment IDs file
    group_file_path : str or None
        Path to single file with group assignments
    group_column : str
        Column name for group assignment (default: 'group')
    id_column : str or None
        Column name for experiment IDs (auto-detects if None)

    Returns
    -------
    tuple of (list, list)
        (experiments_a, experiments_b)
    """
    if file_a_path and file_b_path:
        experiments_a = load_user_data(file_a_path, column_name=id_column)
        experiments_b = load_user_data(file_b_path, column_name=id_column)
        return experiments_a, experiments_b

    elif group_file_path:
        if not os.path.exists(group_file_path):
            raise FileNotFoundError(f"File not found: {group_file_path}")

        file_ext = os.path.splitext(group_file_path)[1].lower()
        sep = "," if file_ext == ".csv" else "\t"
        df = pd.read_csv(group_file_path, sep=sep)

        if group_column not in df.columns:
            raise ValueError(
                f"Group column '{group_column}' not found. "
                f"Available: {list(df.columns)}"
            )

        # Auto-detect ID column
        if id_column is None:
            possible_names = [
                "experiment_id", "srx", "srx_id", "SRX",
                "accession", "sample_id", "id", "ID",
            ]
            for name in possible_names:
                if name in df.columns:
                    id_column = name
                    break
            if id_column is None:
                # Use first column that isn't the group column
                for col in df.columns:
                    if col != group_column:
                        id_column = col
                        break

        groups = df[group_column].unique()
        if len(groups) != 2:
            raise ValueError(
                f"Expected exactly 2 groups, found {len(groups)}: {list(groups)}"
            )

        group_a_name, group_b_name = sorted(groups)
        experiments_a = df[df[group_column] == group_a_name][id_column].tolist()
        experiments_b = df[df[group_column] == group_b_name][id_column].tolist()

        print(f"✓ Loaded groups: '{group_a_name}' ({len(experiments_a)} IDs), "
              f"'{group_b_name}' ({len(experiments_b)} IDs)")

        return experiments_a, experiments_b

    else:
        raise ValueError(
            "Provide either (file_a_path + file_b_path) or group_file_path"
        )


def _load_plain_text(file_path):
    """Load experiment IDs from plain text file (one per line)."""
    ids = []
    with open(file_path, "r") as f:
        for line in f:
            exp_id = line.strip()
            if not exp_id or exp_id.startswith("#"):
                continue
            ids.append(exp_id)

    if not ids:
        raise ValueError(f"No experiment IDs found in {file_path}")
    return ids


def _load_delimited(file_path, sep=",", column_name=None):
    """Load experiment IDs from delimited file (CSV/TSV)."""
    df = pd.read_csv(file_path, sep=sep)

    if column_name is None:
        possible_names = [
            "experiment_id", "srx", "srx_id", "SRX",
            "accession", "sample_id", "id", "ID",
        ]
        for name in possible_names:
            if name in df.columns:
                column_name = name
                break
        if column_name is None:
            column_name = df.columns[0]
            print(f"   Auto-detected ID column: '{column_name}'")

    if column_name not in df.columns:
        raise ValueError(
            f"Column '{column_name}' not found. Available: {list(df.columns)}"
        )

    ids = df[column_name].astype(str).tolist()
    ids = [x for x in ids if x != "nan" and x.strip() != ""]

    if not ids:
        raise ValueError(f"No experiment IDs found in column '{column_name}'")
    return ids

