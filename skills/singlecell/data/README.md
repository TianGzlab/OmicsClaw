# Single-Cell Omics Shared Data

Centralized data repository for all single-cell skills to eliminate duplication.

## Structure

```
data/
├── demo/                    # Shared demo datasets
│   └── pbmc3k_processed.h5ad
├── databases/               # External resources
│   ├── motifs/             # pySCENIC motif databases
│   └── references/         # Reference datasets
└── utils.py                # Data loading utilities
```

## Usage

```python
from omicsclaw.singlecell.data_utils import get_demo_data

# Get demo data for any skill
demo_path = get_demo_data('grn')
adata = sc.read_h5ad(demo_path)
```

## Benefits

- Single copy of demo data (24MB vs 154MB duplicated)
- Consistent data access across all skills
- Centralized database management
