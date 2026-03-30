"""
Test Pickle Loading

Simple script to verify that analysis_object.pkl can be loaded correctly.
This demonstrates downstream skill compatibility.
"""

import sys
import pickle
from pathlib import Path


def test_pickle_load(pickle_path="results/analysis_object.pkl"):
    """
    Test loading pickled analysis object.

    Parameters
    ----------
    pickle_path : str
        Path to pickled analysis object (default: "results/analysis_object.pkl")

    Returns
    -------
    dict
        Loaded analysis object with variants, genes, and metadata
    """
    pickle_file = Path(pickle_path)

    if not pickle_file.exists():
        print(f"Error: Pickle file not found: {pickle_path}")
        print("Run the Standard Workflow first to generate analysis_object.pkl")
        return None

    print("="*70)
    print("TESTING PICKLE LOAD")
    print("="*70)
    print()

    # Load pickle
    print(f"Loading: {pickle_path}")
    try:
        with open(pickle_file, 'rb') as f:
            obj = pickle.load(f)
        print("✓ Pickle loaded successfully!")
    except Exception as e:
        print(f"✗ Failed to load pickle: {e}")
        return None

    print()
    print("Analysis Object Contents:")
    print("-"*70)

    # Check structure
    if isinstance(obj, dict):
        print(f"  Type: Dictionary with {len(obj)} keys")
        print(f"  Keys: {list(obj.keys())}")

        # Check variants
        if 'variants' in obj:
            variants_df = obj['variants']
            print(f"\n  Variants DataFrame:")
            print(f"    Shape: {variants_df.shape}")
            print(f"    Columns: {len(variants_df.columns)}")
            if len(variants_df) > 0:
                print(f"    Sample columns: {list(variants_df.columns[:5])}")

        # Check genes
        if 'genes' in obj:
            genes_df = obj['genes']
            if genes_df is not None:
                print(f"\n  Genes DataFrame:")
                print(f"    Shape: {genes_df.shape}")
                print(f"    Columns: {list(genes_df.columns)}")

        # Check metadata
        if 'tool' in obj:
            print(f"\n  Tool: {obj['tool']}")
        if 'n_variants' in obj:
            print(f"  Total variants: {obj['n_variants']}")
        if 'n_genes' in obj:
            print(f"  Total genes: {obj['n_genes']}")

    else:
        print(f"  Type: {type(obj)}")
        print("  Warning: Expected dictionary structure")

    print()
    print("="*70)
    print("✓ Pickle load test completed successfully!")
    print("="*70)
    print()
    print("Downstream skills can load this object with:")
    print("  import pickle")
    print(f"  obj = pickle.load(open('{pickle_path}', 'rb'))")
    print()

    return obj


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test pickle loading')
    parser.add_argument(
        '--pickle',
        default='results/analysis_object.pkl',
        help='Path to pickle file (default: results/analysis_object.pkl)'
    )

    args = parser.parse_args()

    # Run test
    obj = test_pickle_load(args.pickle)

    if obj is None:
        sys.exit(1)
    else:
        sys.exit(0)

