# Installation Guide

## Quick Start

```bash
# Clone repository
git clone https://github.com/zhou-1314/OmicsClaw.git
cd OmicsClaw

# Create virtual environment (Python 3.11+)
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install
pip install -e .              # Core dependencies
pip install -e ".[full]"      # All optional methods

# Verify installation
python omicsclaw.py env
python omicsclaw.py list
python omicsclaw.py run preprocess --demo
```

> [!TIP]
> If `python3.11 -m venv` fails, see [Troubleshooting](#troubleshooting) section.

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.11 | 3.11 or 3.12 |
| RAM | 8 GB | 32 GB+ |
| Disk (core) | 2 GB | — |
| Disk (full) | 10 GB+ | — |
| GPU | Optional | CUDA GPU for deep learning methods |
| R | Optional | R 4.4+ for RCTD, SPOTlight, Numbat |

## Environment Management

OmicsClaw uses Python `venv` for reproducibility and speed:

- **Reproducibility** - Exact versions from `pyproject.toml`
- **Speed** - Faster than conda to create and activate
- **Isolation** - No conflicts with existing conda environments
- **Portability** - Works on any system with Python 3.11+

**Using conda?** You can still create a venv inside conda:

```bash
conda deactivate
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[full]"
```

## Installation Tiers

OmicsClaw uses tiered dependencies. Skills require specific packages - missing dependencies raise clear `ImportError` with install instructions.

### Core (default)

```bash
pip install -e .
```

Essential packages for preprocessing and basic analysis:
- scanpy, anndata, squidpy
- numpy, pandas, scipy, scikit-learn
- igraph, leidenalg, umap-learn
- matplotlib, seaborn

### Domain Platforms

OmicsClaw supports granular installation tiers so you only install what you need for your research domain:

| Domain | Installation Command | Key Packages / Scope |
|--------|----------------------|----------------------|
| **Spatial** | `pip install -e ".[spatial]"` | SpaGCN, scvi-tools, tangram-sc, rpy2, cell2location, scvelo |
| **Single-cell** | `pip install -e ".[singlecell]"` | scrublet + core single-cell packages |
| **Genomics** | `pip install -e ".[genomics]"` | Genomic python pipelines |
| **Proteomics** | `pip install -e ".[proteomics]"` | Proteomic python pipelines |
| **Metabolomics**| `pip install -e ".[metabolomics]"` | Metabolomic python pipelines |

> [!TIP]
> **Check your installation:** You can run `python omicsclaw.py env` at any time to see exactly which domain frameworks are successfully installed and which ones are missing.

### Standalone Deep-Learning Layer

```bash
pip install -e ".[spatial-domains]"
```

Certain frameworks (like SpaGCN and STAGATE) run complex spatial domains and carry heavy dependencies (e.g. `louvain` and `torch_geometric`) that are often difficult to compile across OS distributions.
We have isolated them into this tier. You can layer this over the `spatial` module:
```bash
pip install -e ".[spatial,spatial-domains]"
```

> [!WARNING]
> **macOS**: SpaGCN's `louvain` dependency may fail to compile. Use pre-built wheel:
> ```bash
> pip install louvain --find-links https://wheels.louvain.org
> ```

> [!NOTE]
> `[spatial]` tier includes R dependencies which requires R ≥4.3.0. See [R Dependencies](#r-dependencies) section.

### Full Arsenal

```bash
pip install -e ".[full]"
```

Installs all 50+ optional methods across all 5 domains.

### BANKSY (isolated environment)

```bash
pip install -e ".[banksy]"
```

> [!CAUTION]
> `pybanksy` requires `numpy<2.0`, conflicting with `full` tier packages. Use a separate environment:
> ```bash
> python3.11 -m venv .venv-banksy
> source .venv-banksy/bin/activate
> pip install -e ".[banksy]"
> pip install -e .
> ```

### Development

```bash
pip install -e ".[dev]"
```

Adds testing and code quality tools: pytest, black, mypy, ruff, isort, pre-commit

### Combining Tiers

```bash
pip install -e ".[spatial,singlecell,dev]"  # Multiple domains + dev tools
pip install -e ".[full,dev]"                # Full methods + dev tools
```

## Fast Installation with uv

[uv](https://docs.astral.sh/uv/) resolves dependencies 10-100× faster than pip:

```bash
pip install uv
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[full]"
```

## R Dependencies

Several skills use R libraries via `rpy2`:

| R Package | Skill | Method |
|-----------|-------|--------|
| spacexr | deconv | RCTD |
| CARD | deconv | CARD |
| SPOTlight | deconv | SPOTlight |
| CellChat | communication | Cell-cell communication |
| numbat | cnv | Copy number variation |
| SPARK | genes | SPARK-X spatially variable genes |

### Setup Steps

**1. Install R (≥4.3.0)**

```bash
# Ubuntu/Debian
sudo apt install r-base r-base-dev

# macOS
brew install r

# Verify
R --version
```

**Ubuntu system libraries:**
```bash
sudo apt install libcurl4-openssl-dev libssl-dev libxml2-dev \
                 libharfbuzz-dev libfribidi-dev libfreetype6-dev \
                 libpng-dev libtiff5-dev libjpeg-dev
```

**2. Install Python bridge**

```bash
pip install "rpy2>=3.5.0,<3.7" anndata2ri
```

> [!NOTE]
> Pin `rpy2<3.7` for R 4.4.x compatibility. rpy2 3.7+ requires R 4.5+.

**3. Install R packages (automated)**

```bash
Rscript install_r_dependencies.R
```

The script installs all required R packages and reports success/failure.

**4. Verify**

```bash
# Test R packages
Rscript -e 'pkgs <- c("spacexr", "CARD", "SPOTlight"); print(sapply(pkgs, requireNamespace, quietly=TRUE))'

# Test Python bridge
python -c "import rpy2.robjects as ro; print('rpy2 OK')"
```

**Set R_HOME if needed:**
```bash
export R_HOME=$(R RHOME)
echo 'export R_HOME=$(R RHOME)' >> ~/.bashrc
```

## Troubleshooting

### venv creation fails

**Error:** `ensurepip` error when creating venv

**Solutions:**

1. **Remove stale venv:**
   ```bash
   rm -rf .venv
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

2. **Ubuntu/Debian - install venv module:**
   ```bash
   sudo apt install python3.11-venv python3-pip
   ```

3. **Anaconda - bootstrap pip manually:**
   ```bash
   python3.11 -m venv --without-pip .venv
   source .venv/bin/activate
   curl -sS https://bootstrap.pypa.io/get-pip.py | python3
   ```

### Package not found on Python 3.10

**Error:** `Could not find a version that satisfies the requirement`

**Solution:** Use Python 3.11+ (minimum required version)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[full]"
```

### macOS louvain compilation fails

**Solution:** Use pre-built wheel

```bash
pip install louvain --find-links https://wheels.louvain.org
```

### rpy2 installation fails

**Solution:** Ensure R is on PATH

```bash
which R
export R_HOME=$(R RHOME)
pip install "rpy2>=3.5.0,<3.7" anndata2ri
```

### PyTorch CUDA mismatch

**Solution:** Install correct CUDA wheel first

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -e ".[full]"
```

### STAGATE_pyG not on PyPI

**Solution:** Install from GitHub

```bash
git clone https://github.com/QIFEIDKN/STAGATE_pyG.git
cd STAGATE_pyG && python setup.py install
pip install torch_geometric torch_sparse torch_scatter torch_cluster
```

### Verify installation

```bash
python omicsclaw.py list
python omicsclaw.py run preprocess --demo
python -m pytest -v
```

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| Linux (x86_64) | ✅ Fully supported | All tiers work |
| macOS (Apple Silicon) | ⚠️ Partial | louvain needs pre-built wheel |
| macOS (Intel) | ⚠️ Partial | Same as Apple Silicon |
| Windows | ⚠️ Untested | WSL2 recommended |
