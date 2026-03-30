# Installation Guide: gwas-to-function-twas

Comprehensive setup instructions for FUSION, S-PrediXcan, and all required dependencies.

## Quick Start (S-PrediXcan - Recommended for Beginners)

```bash
# Create conda environment
conda create -n metaxcan python=3.9
conda activate metaxcan

# Install S-PrediXcan
pip install pandas numpy scipy plotnine plotnine-prism seaborn statsmodels metaxcan

# Download expression weights (1 tissue for testing)
mkdir -p weights/GTEx_v8
cd weights/GTEx_v8
wget https://predictdb.org/post/2021/07/21/gtex-v8-models-on-eqtl-and-sqtl/Whole_Blood.db

# Ready to run!
```

**Expected time:** 10-15 minutes
**Disk space:** ~2 GB (includes Python + 1 tissue weight)
**See:** [S-PrediXcan Setup](#s-predixcan-setup) below for complete instructions

---

## Installation Options

### Option 1: S-PrediXcan (Fast, Python-based)

**Pros:**
- ✅ Fast installation (10-15 min)
- ✅ Low memory requirements (<16 GB RAM)
- ✅ 10-100x faster runtime than FUSION
- ✅ Cross-platform (macOS, Linux, Windows via WSL)

**Cons:**
- ❌ Single prediction model (MASHR only)
- ❌ Requires external colocalization tool

**Best for:** Exploratory analysis, large-scale screens, local machines

### Option 2: FUSION (Comprehensive, R-based)

**Pros:**
- ✅ Multiple prediction models (BSLMM, lasso, elastic net)
- ✅ Built-in colocalization
- ✅ Publication-standard tool

**Cons:**
- ❌ Complex R dependencies
- ❌ High memory requirements (>32 GB RAM)
- ❌ Slower runtime (2-6 hours per tissue)

**Best for:** In-depth analysis, method comparisons, HPC environments

---

## S-PrediXcan Setup

### Step 1: Create Python Environment

**Using conda (recommended):**
```bash
conda create -n metaxcan python=3.9
conda activate metaxcan
```

**Using venv:**
```bash
python3.9 -m venv metaxcan_env
source metaxcan_env/bin/activate  # macOS/Linux
# metaxcan_env\Scripts\activate  # Windows
```

### Step 2: Install Python Packages

```bash
pip install pandas numpy scipy statsmodels metaxcan
pip install plotnine plotnine-prism seaborn  # For visualization
```

**Verify installation:**
```bash
python -c "import metaxcan; print(f'MetaXcan version: {metaxcan.__version__}')"
```

### Step 3: Download GTEx v8 Expression Weights

**Option A: Manual download (recommended for transparency)**

Visit https://predictdb.org/post/2021/07/21/gtex-v8-models-on-eqtl-and-sqtl/

Download individual tissues or all 54 tissues:
```bash
mkdir -p weights/GTEx_v8
cd weights/GTEx_v8

# Example: Download Whole_Blood
wget https://predictdb.org/post/2021/07/21/gtex-v8-models-on-eqtl-and-sqtl/mashr/mashr_Whole_Blood.db
wget https://predictdb.org/post/2021/07/21/gtex-v8-models-on-eqtl-and-sqtl/mashr/mashr_Whole_Blood.txt.gz

# Repeat for other tissues or download all with:
wget -r -np -nH --cut-dirs=6 -A "*.db,*.txt.gz" https://predictdb.org/post/2021/07/21/gtex-v8-models-on-eqtl-and-sqtl/mashr/
```

**Option B: Use helper script**
```python
from assets.eval.eval_helpers import load_gtex_weights
weights = load_gtex_weights(tissues=["Whole_Blood", "Artery_Coronary"])
```

**Disk space:** ~100 MB per tissue, ~5 GB for all 54 tissues

### Step 4: Download LD Reference (for covariance calculation)

**Option A: Use pre-computed covariances (recommended)**

PredictDB provides pre-computed LD matrices:
```bash
cd weights/GTEx_v8
wget https://predictdb.org/post/2021/07/21/gtex-v8-models-on-eqtl-and-sqtl/gtex_v8_expression_mashr_ld_matrices.tar.gz
tar xzf gtex_v8_expression_mashr_ld_matrices.tar.gz
```

**Option B: Download 1000 Genomes genotypes**
```bash
mkdir -p 1000G_EUR
cd 1000G_EUR
wget https://zenodo.org/record/3518299/files/1000G_EUR.tar.gz
tar xzf 1000G_EUR.tar.gz
```

**Disk space:** ~3 GB (pre-computed) or ~5 GB (full genotypes)

### Step 5: Test Installation

```bash
# Test S-PrediXcan
python -c "from metaxcan import Utilities; print('S-PrediXcan ready!')"

# Quick test run (requires test GWAS data)
python scripts/run_spredixxcan.py --help
```

---

## FUSION Setup

### Step 1: Install R and Required Packages

**Install R ≥4.0:**
- macOS: `brew install r` or download from https://cran.r-project.org/
- Linux: `sudo apt-get install r-base` (Ubuntu/Debian) or equivalent
- Verify: `R --version`

**Install R packages:**
```R
# Launch R
R

# Install FUSION dependencies
install.packages(c('optparse', 'RColorBrewer', 'data.table', 'glmnet'))
install.packages(c('reshape', 'ggplot2', 'Rcpp', 'RcppArmadillo'))
```

### Step 2: Clone FUSION Repository

```bash
cd ~/software  # Or your preferred location
git clone https://github.com/gusevlab/fusion_twas.git
cd fusion_twas
```

### Step 3: Download FUSION LDREF Panel

```bash
cd ~/software/fusion_twas

# Download LD reference (~2 GB compressed, ~5 GB uncompressed)
wget https://data.broadinstitute.org/alkesgroup/FUSION/LDREF.tar.bz2
tar xjvf LDREF.tar.bz2

# Verify
ls LDREF/1000G.EUR.*/  # Should show .bim, .bed, .fam files
```

### Step 4: Download GTEx v8 Weights (FUSION format)

```bash
mkdir -p weights/GTEx_v8_FUSION
cd weights/GTEx_v8_FUSION

# Download all GTEx v8 tissues from FUSION website
wget http://gusevlab.org/projects/fusion/gtex_v8_fusion_weights.tar.bz2
tar xjvf gtex_v8_fusion_weights.tar.bz2

# Or download individual tissues
# See: http://gusevlab.org/projects/fusion/#reference-datasets
```

**Disk space:** ~10 GB for all tissues

### Step 5: Set Environment Variables

Add to `~/.bashrc` or `~/.zshrc`:
```bash
export FUSION_PATH=~/software/fusion_twas
export PATH=$FUSION_PATH:$PATH
```

Reload: `source ~/.bashrc` or `source ~/.zshrc`

### Step 6: Test FUSION Installation

```bash
# Test FUSION help
Rscript $FUSION_PATH/FUSION.assoc_test.R --help

# Quick test (requires test GWAS data)
python scripts/run_fusion.py --help
```

---

## Common Installation Issues

### Issue 1: Python package conflicts

**Error:** `ERROR: metaxcan X.X requires pandas>=Y.Y, but you have pandas Z.Z`

**Solution:**
```bash
# Create fresh conda environment
conda create -n metaxcan_clean python=3.9
conda activate metaxcan_clean
pip install metaxcan --no-cache-dir
```

### Issue 2: R package installation fails

**Error:** `installation of package 'X' had non-zero exit status`

**Solution (macOS):**
```bash
# Install Xcode command line tools
xcode-select --install

# Install gfortran (required for some R packages)
brew install gcc
```

**Solution (Linux):**
```bash
sudo apt-get install libcurl4-openssl-dev libssl-dev libxml2-dev
```

### Issue 3: FUSION LDREF download slow/fails

**Error:** `wget: unable to resolve host address`

**Solution:**
```bash
# Use curl instead
curl -O https://data.broadinstitute.org/alkesgroup/FUSION/LDREF.tar.bz2

# Or use aria2c for faster download with resume capability
brew install aria2  # macOS
sudo apt-get install aria2  # Linux
aria2c -x 16 -s 16 https://data.broadinstitute.org/alkesgroup/FUSION/LDREF.tar.bz2
```

### Issue 4: GTEx weights download incomplete

**Error:** `wget recursive download gets stuck`

**Solution:**
```bash
# Download individual tissues manually
# List of all 54 GTEx v8 tissues at: https://predictdb.org/
# Or use the download script provided in assets/eval/eval_helpers.py
```

### Issue 5: Memory errors during FUSION

**Error:** `Error: cannot allocate vector of size X GB`

**Solution:**
- Use S-PrediXcan instead (10x less memory)
- Run FUSION chromosome-by-chromosome
- Increase swap space (not recommended for performance)
- Use HPC with >32 GB RAM

---

## Validation Checklist

After installation, verify:

- [ ] **Python environment active**: `which python` shows correct path
- [ ] **Python packages installed**: `pip list | grep metaxcan`
- [ ] **R installed (if using FUSION)**: `R --version`
- [ ] **R packages available**: `R -e "library(optparse)"`
- [ ] **Expression weights downloaded**: `ls weights/GTEx_v8/*.db` (S-PrediXcan) or `ls weights/GTEx_v8_FUSION/*.pos` (FUSION)
- [ ] **LD reference available**: `ls LDREF/` or `ls weights/GTEx_v8/gtex_v8_ld/`
- [ ] **Scripts executable**: `python scripts/run_spredixxcan.py --help`
- [ ] **Test data available**: `python -c "from assets.eval.eval_helpers import load_test_gwas; load_test_gwas()"`

---

## Disk Space Requirements

**Minimal (chr22 only, 1 tissue):**
- Python/R + packages: ~2 GB
- 1 tissue weights: ~100 MB
- LD reference (minimal): ~500 MB
- **Total: ~3 GB**

**Standard (genome-wide, 5 tissues):**
- Python/R + packages: ~2 GB
- 5 tissue weights: ~500 MB
- LD reference (full): ~5 GB
- **Total: ~8 GB**

**Complete (all 54 tissues, both tools):**
- Python/R + packages: ~3 GB
- All tissue weights (S-PrediXcan): ~5 GB
- All tissue weights (FUSION): ~10 GB
- LD references (both): ~8 GB
- **Total: ~26 GB**

---

## Computational Requirements

**S-PrediXcan:**
- CPU: 2+ cores (benefits from 4-8 cores)
- RAM: 8 GB minimum, 16 GB recommended
- Disk: See above
- Runtime: 5-30 minutes per tissue (genome-wide)

**FUSION:**
- CPU: 4+ cores recommended
- RAM: 32 GB minimum, 64 GB recommended
- Disk: See above
- Runtime: 2-6 hours per tissue (genome-wide)

---

## Next Steps

After installation:

1. **Test with example data**: Run `python scripts/run_spredixxcan.py --help`
2. **Download test GWAS**: See [assets/eval/datasets/README.md](../assets/eval/datasets/README.md)
3. **Run quick test**: Execute `python assets/eval/test_tier1_basic.py` (when implemented)
4. **Read usage guides**: [spredixxcan_best_practices.md](spredixxcan_best_practices.md) or [fusion_best_practices.md](fusion_best_practices.md)

---

## Additional Resources

**S-PrediXcan:**
- Documentation: https://github.com/hakyimlab/MetaXcan
- PredictDB: https://predictdb.org/
- Tutorial: https://github.com/hakyimlab/MetaXcan/wiki

**FUSION:**
- Documentation: http://gusevlab.org/projects/fusion/
- GitHub: https://github.com/gusevlab/fusion_twas
- Paper: Gusev A, et al. (2016) *Nat Genet* 48:245-252

**GTEx:**
- Portal: https://gtexportal.org/
- V8 release notes: https://gtexportal.org/home/releaseInfoPage
- eQTL data: https://gtexportal.org/home/datasets
