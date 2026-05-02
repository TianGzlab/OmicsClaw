# Mamba-first 统一环境管理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `pip install -e ".[full,singlecell-upstream]"` 触发的 `resolution-too-deep` 彻底消除，落地"mamba 为主、pip 为辅、源码兜底、子环境隔离"四层统一环境管理体系。

**Architecture:** 把 pip 解析图里的"重型枢纽"包（scanpy/anndata/squidpy/torch/scvi-tools/scvelo/cellrank/harmonypy/bbknn/scanorama/celltypist/gseapy/pydeseq2/multiqc/kb-python 等）从 pyproject 上提到 environment.yml，让 mamba 的 SAT solver 一次性求解；pyproject 仅保留 conda 没有发布的"thin pip residue"（SpaGCN/GraphST/cellcharter/paste-bio/flashdeconv/fastccc/pyVIA/tangram-sc/omicsclaw 自身等）；硬冲突依赖（numpy<2.0 的 pybanksy、pandas<2.0 的 cnvkit）落到独立 `omicsclaw_<tool>` 子环境，靠 subprocess 桥接进主流程；源码构建路径保留 `0_build_vendored_tools.sh` 作为最终兜底。

**Tech Stack:** mamba/miniforge3、conda-forge + bioconda（strict priority、`nodefaults`）、`mamba run -n <env>` 跨环境调用、`uv pip install` 作为 thin-pip 加速回退、subprocess + 临时文件（`.h5ad`/JSON）的跨进程数据桥。

**前置约定:**
- 单一入口：`bash 0_setup_env.sh [env_name]`，幂等可重跑
- 分层决策树（top-down，命中即停）：
  1. **Layer 0 基底**：python/R/gcc/cmake/build-tools — `environment.yml` Tier 0
  2. **Layer 1 重型 Python 科学栈**：bioconda/conda-forge 上有的全走 mamba — `environment.yml` Tier 4（新增）
  3. **Layer 2 thin pip residue**：conda 没有 recipe 的纯 Python 包 — `pyproject.toml` 收窄后的 extras
  4. **Layer 3 源码 vendored**：bioconda 缺 Py3.11 build / 上游已死 / 需要自定义 patch — `tools/<name>/`，`0_build_vendored_tools.sh`
  5. **Layer 4 隔离子环境**：硬冲突依赖（numpy/pandas major 版本反向钉死）— `environments/<tool>.yml`，`omicsclaw_<tool>` 命名约定，subprocess 桥
- 确认开始前工作树干净：`git status` 无待提交修改（pyproject.toml/test/README/README_zh-CN 当前 dirty，先 commit 或 stash）

---

## 阶段 0：清单与可行性核查

### Task 0：跑包可用性核查脚本

**Files:**
- Create: `scripts/audit_conda_availability.py`
- Create: `docs/superpowers/specs/2026-05-02-mamba-first-env-design.md`（同步设计记录）

**目的:** 把 `[full,singlecell-upstream]` 解析出的所有 PyPI 包逐一在 conda-forge + bioconda 上查 Python 3.11 build 是否存在。输出三档分类：`mamba_ok`（直接迁）/ `mamba_pin_needed`（要钉版本）/ `pip_only`（保留在 pyproject）。

- [ ] **Step 1: 写脚本（无需联网，靠 `mamba search --json`）**

```python
# scripts/audit_conda_availability.py
"""Audit which pyproject deps are available on conda-forge/bioconda for Py3.11.

Usage:
    mamba run -n OmicsClaw python scripts/audit_conda_availability.py \
        --extras full,singlecell-upstream \
        --python 3.11 \
        --output docs/superpowers/specs/conda-availability-2026-05-02.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement


CHANNELS = ["bioconda", "conda-forge"]
ALWAYS_PIP = {  # known-no-conda packages, skip search
    "omicsclaw", "spagcn", "graphst", "cellcharter", "paste-bio",
    "flashdeconv", "fastccc", "pyvia", "pybanksy", "ccproxy-api",
    "tangram-sc", "deepagents", "opendataloader-pdf",
}


def expand_extras(pyproject: dict, extras: list[str]) -> set[str]:
    extras_table = pyproject["project"]["optional-dependencies"]
    seen, queue = set(), list(extras)
    pkgs: set[str] = set()
    while queue:
        e = queue.pop()
        if e in seen or e not in extras_table:
            continue
        seen.add(e)
        for dep in extras_table[e]:
            req = Requirement(dep)
            if req.name == "omicsclaw":
                queue.extend(req.extras)
            else:
                pkgs.add(req.name.lower())
    return pkgs


def search_conda(pkg: str, py_ver: str) -> tuple[str, str]:
    """Return (status, latest_version_or_reason)."""
    if pkg in ALWAYS_PIP:
        return "pip_only", "known-no-conda-recipe"
    cmd = ["mamba", "search", "--json"]
    for ch in CHANNELS:
        cmd.extend(["-c", ch])
    cmd.append(pkg)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return "pip_only", "not-found"
    data = json.loads(res.stdout or "{}")
    builds = data.get(pkg, [])
    py_builds = [b for b in builds if f"py{py_ver.replace('.', '')}" in b.get("build", "")]
    if not py_builds:
        return "pip_only", f"no-py{py_ver}-build"
    latest = max(py_builds, key=lambda b: b.get("timestamp", 0))
    return "mamba_ok", latest.get("version", "unknown")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extras", default="full,singlecell-upstream")
    ap.add_argument("--python", default="3.11")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pkgs = sorted(expand_extras(pyproject, args.extras.split(",")))

    rows = []
    for pkg in pkgs:
        status, info = search_conda(pkg, args.python)
        rows.append({"package": pkg, "status": status, "version_or_reason": info})
        print(f"  [{status:9}] {pkg:30} {info}", file=sys.stderr)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["package", "status", "version_or_reason"])
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 在当前 OmicsClaw env 上跑一次，产出 CSV**

Run:
```bash
mamba run -n OmicsClaw python scripts/audit_conda_availability.py \
    --extras full,singlecell-upstream \
    --python 3.11 \
    --output docs/superpowers/specs/conda-availability-2026-05-02.csv
```

Expected: stderr 流出 `[mamba_ok]` / `[pip_only]` 标签 + 每个包的判定；CSV 文件写到 `docs/superpowers/specs/conda-availability-2026-05-02.csv`。预期至少 60% 标记为 `mamba_ok`。

- [ ] **Step 3: 把分类结果汇总到设计 spec**

写 `docs/superpowers/specs/2026-05-02-mamba-first-env-design.md`：
- 复述四层决策树
- 引用 CSV 作为 Layer 1 vs Layer 2 的证据来源
- 列出每个 `pip_only` 包的具体原因（"上游未发布到 bioconda" / "Py3.11 build 缺失" / "我们维护的私有包"）
- 列出 Layer 4 子环境清单（当前：banksy；预留：cnvkit、cellranger）

- [ ] **Step 4: Commit**

```bash
git add scripts/audit_conda_availability.py \
        docs/superpowers/specs/2026-05-02-mamba-first-env-design.md \
        docs/superpowers/specs/conda-availability-2026-05-02.csv
git commit -m "feat(env): audit conda availability for [full,singlecell-upstream]

Generates a manifest classifying each PyPI dep into mamba_ok / pip_only,
which becomes the source of truth for Phase 1 environment.yml migration."
```

---

## 阶段 1：把重型 Python 枢纽包上提到 mamba

### Task 1：扩充 environment.yml — Layer 1 Python 科学栈

**Files:**
- Modify: `environment.yml`（添加新的 Tier 4 区块）

**Decision rule:** Task 0 CSV 里 `status == mamba_ok` 的包默认全部上提；以下"高信心"清单是必须先迁的最小集（即使 Task 0 没跑也能下手）：

| 类别 | 包名（conda 命名） | 来自 pyproject 哪个 extra |
|---|---|---|
| 单细胞/空间核心 | scanpy, anndata, squidpy | core |
| 数据科学栈 | numpy, pandas, scipy, scikit-learn, matplotlib, seaborn, pillow, scikit-misc | core |
| 图论 | python-igraph, leidenalg, louvain | core / singlecell-clustering |
| 降维 | umap-learn | core |
| Pydantic / 服务 | pydantic, nbformat, jupyter_client, ipykernel | core / desktop / autonomous |
| Web 服务 | aiosqlite, sqlalchemy, fastapi, uvicorn, cryptography, requests, openai, python-dotenv, httpx | desktop / memory |
| 交互 | prompt-toolkit, rich, questionary, pyyaml | interactive |
| 深度学习 | pytorch (cpu) | spatial / spatial-domains / spatial-annotate / spatial-deconv / singlecell-batch |
| scvi 系列 | scvi-tools, scvelo, cellrank | spatial / spatial-velocity / spatial-trajectory / spatial-deconv / singlecell-* |
| 批次校正 | harmonypy, bbknn, scanorama | spatial-integration / singlecell-batch |
| 注释/通讯 | celltypist, cellphonedb | spatial-communication / singlecell-* |
| 富集/差异 | gseapy, pydeseq2 | spatial-enrichment / spatial-condition / bulkrna |
| Doublet | scrublet, doubletdetection | singlecell-doublet |
| GRN / 轨迹 | arboreto, palantir | singlecell-grn / spatial-trajectory |
| 上游 | multiqc, kb-python | singlecell-upstream |
| 空间统计 | esda, libpysal, pysal, pot | spatial-statistics / spatial-registration |
| nbconvert / Jinja2 链 | nbconvert, beautifulsoup4, jinja2 | 由 kb-python 拖进 — 直接 conda 装锁住 jinja2 版本 |

- [ ] **Step 1: 在 environment.yml 末尾追加 Tier 4 区块**

写入下述 patch（保留现有 Tier 0–3 不变）。注意 `pytorch=*=cpu*` 锁 CPU build，CUDA 用户在 README 里指引另装。`liana-py` / `infercnvpy` / `tangram-sc` 等"中信心"包等 Task 0 CSV 验证后再迁，本阶段先不动。

```yaml
  # ────────── Tier 4: heavy Python science stack (lifted from pyproject pip layer) ──────────
  # Why: pip 24.2+ aborts the [full,singlecell-upstream] resolve with
  # `resolution-too-deep`. Lifting the heavy hubs (torch, scvi-tools, scanpy
  # family, jinja2/nbconvert chain) to mamba shrinks the pip graph by ~70%,
  # which lets the residual thin pip layer resolve reliably.
  # See docs/superpowers/specs/2026-05-02-mamba-first-env-design.md.
  # Channel pins: prefer conda-forge for python-only libs, bioconda for
  # genomics-domain libs. Strict channel priority is enforced by 0_setup_env.sh.
  - scanpy>=1.9.0,<2.0
  - anndata>=0.11.0
  - squidpy>=1.2.0
  - numpy>=1.24,<2.1            # cap at 2.1 until scvi-tools/numba clear 2.x
  - pandas>=2.0,<3.0
  - scipy>=1.7.0
  - scikit-learn>=1.3
  - matplotlib>=3.7
  - seaborn>=0.11.0
  - pillow>=8.0.0
  - scikit-misc>=0.5.0
  - python-igraph>=0.11.0
  - leidenalg>=0.10.0
  - louvain>=0.8.0
  - umap-learn>=0.5.0
  - pydantic>=2.0,<3.0
  - nbformat>=5.9
  - jupyter_client>=8.0
  - ipykernel>=6.0
  - rich>=13.0.0
  - greenlet>=3.0.0
  - prompt-toolkit>=3.0
  - questionary>=2.0
  - pyyaml>=6.0
  - aiosqlite>=0.19.0
  - sqlalchemy>=1.4.0
  - fastapi>=0.100.0
  - uvicorn>=0.23.0
  - cryptography>=41.0.0
  - requests>=2.31.0
  - openai>=1.0.0
  - python-dotenv>=1.0.0
  - httpx>=0.27
  - jinja2>=3.1.5               # over pygpcca's bad pin; conda installs the
                                # winning version up front so pip never
                                # backtracks across this leaf.
  - nbconvert>=7.0
  - beautifulsoup4>=4.12
  - pytorch>=2.0,<3.0
  - pytorch-cpu                 # explicit CPU variant; CUDA users override.
                                # See README for CUDA install instructions.
  - scvi-tools>=1.4.0,<2.0
  - scvelo>=0.3.0
  - cellrank>=2.0.7,<2.1
  - harmonypy>=0.0.9
  - bbknn>=1.5.0
  - scanorama>=1.7.0
  - celltypist>=1.6.0
  - cellphonedb>=5.0.0,<6.0
  - gseapy>=1.0.0
  - pydeseq2>=0.4.0
  - scrublet>=0.2.3
  - doubletdetection>=4.3.0
  - arboreto>=0.1.6
  - palantir>=1.0.0
  - multiqc>=1.33,<2.0
  - kb-python>=0.29.0
  - esda>=2.4.0
  - libpysal>=4.6.0
  - pysal>=2.6.0
  - pot>=0.9.0                  # PyPI name `POT`, conda name `pot`
  - coloredlogs>=15.0.1,<16.0   # transitive narrowing kept here for parity
  - humanfriendly>=10.0,<11.0   # with old singlecell-upstream constraints
```

- [ ] **Step 2: 在干净虚拟机上验证 mamba 能解出**

Run:
```bash
mamba env create -n OmicsClaw_test -f environment.yml --strict-channel-priority
```

Expected: 不报 `LibMambaUnsatisfiableError`；如果某个包名/版本在 channel 上不存在，逐一标记并降级到下一个最近版本，或移到 Task 1.5（pip 兜底）。

- [ ] **Step 3: 验证关键包能 import**

Run:
```bash
mamba run -n OmicsClaw_test python -c "
import scanpy, anndata, squidpy, scvi, scvelo, cellrank
import torch, harmonypy, bbknn, scanorama
import celltypist, cellphonedb, gseapy, pydeseq2
import scrublet, doubletdetection, arboreto, palantir
import multiqc, kb_python
import esda, libpysal, pysal, ot
print('all imports OK')
"
```

Expected: stdout `all imports OK`，无 ImportError。

- [ ] **Step 4: Commit**

```bash
git add environment.yml
git commit -m "feat(env): lift heavy Python science stack from pip to mamba

Adds Tier 4 to environment.yml: ~50 packages (torch, scvi-tools, scanpy
family, jinja2/nbconvert chain, harmonypy/bbknn/scanorama, etc.) that
previously lived in pyproject's [full] extras. This shrinks pip's resolve
graph by ~70%, eliminating the resolution-too-deep error on pip 24.2+."
```

### Task 2：从 pyproject.toml 移除已上提的包

**Files:**
- Modify: `pyproject.toml:47-95`（dependencies）
- Modify: `pyproject.toml:97-360`（optional-dependencies — 多处）

**Decision rule:** environment.yml Tier 4 装过的包，从 pyproject 的 `dependencies` 和 `optional-dependencies` 同步删除；保留只在 conda 上没有 recipe 的"thin pip residue"。

- [ ] **Step 1: 写一个 sanity-check 测试，先红**

```python
# tests/test_pyproject_thin_pip_layer.py
"""Verify pyproject's pip layer is thin: heavy hubs must live in environment.yml."""
from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]

# Packages that MUST be installed via conda/mamba, NOT listed in pyproject.
CONDA_OWNED = {
    "scanpy", "anndata", "squidpy", "numpy", "pandas", "scipy",
    "scikit-learn", "matplotlib", "seaborn", "pillow", "scikit-misc",
    "igraph", "leidenalg", "louvain", "umap-learn", "pydantic",
    "nbformat", "jupyter-client", "ipykernel", "rich", "greenlet",
    "prompt-toolkit", "questionary", "pyyaml", "aiosqlite", "sqlalchemy",
    "fastapi", "uvicorn", "cryptography", "requests", "openai",
    "python-dotenv", "httpx", "torch", "scvi-tools", "scvelo", "cellrank",
    "harmonypy", "bbknn", "scanorama", "celltypist", "cellphonedb",
    "gseapy", "pydeseq2", "scrublet", "doubletdetection", "arboreto",
    "palantir", "multiqc", "kb-python", "esda", "libpysal", "pysal",
    "pot",
}


def test_pyproject_thin_pip_layer_excludes_conda_owned_packages():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    seen: set[str] = set()
    for dep in pyproject["project"].get("dependencies", []):
        seen.add(Requirement(dep).name.lower())
    for extra, deps in pyproject["project"]["optional-dependencies"].items():
        for dep in deps:
            req = Requirement(dep)
            if req.name == "omicsclaw":
                continue  # self-extras references are fine
            seen.add(req.name.lower())
    leaked = seen & CONDA_OWNED
    assert not leaked, (
        f"these packages must be installed via mamba (environment.yml) only, "
        f"but still appear in pyproject: {sorted(leaked)}"
    )
```

- [ ] **Step 2: 跑测试，确认红**

Run: `mamba run -n OmicsClaw python -m pytest tests/test_pyproject_thin_pip_layer.py -v`

Expected: `FAIL` — 列出当前还在 pyproject 里的所有 conda-owned 包名。

- [ ] **Step 3: 编辑 pyproject.toml**

把测试列出的所有名字从 `dependencies` + `optional-dependencies` 里删掉。同时对每个 extra：
- 如果 extra 全部包都被删空，extra 改成空 list `[]` + 注释说明"全部依赖已迁移到 environment.yml"，**保留 extra 名字**以维持向后兼容
- 如果 extra 还剩一些 thin pip 包（如 SpaGCN、GraphST、cellcharter、tangram-sc、SpatialDE、infercnvpy 等），保持那些不动

实例（`spatial-domains`）：

```toml
spatial-domains = [
    # torch / scvi-tools / GraphST 已迁移到 environment.yml Tier 4
    "SpaGCN>=1.2.5,<2.0",             # PyPI only
    "torch_geometric>=2.4",           # 加下界，PyPI only
    "cellcharter>=0.2.0",             # PyPI only
]
```

实例（`spatial`）— 大幅瘦身：

```toml
spatial = [
    # 注：scvi-tools / cellrank / harmonypy / bbknn / scanorama / pydeseq2 /
    # gseapy / palantir / pot / esda / libpysal / pysal / scvelo 全部已迁移到
    # environment.yml Tier 4。本 extra 仅保留 conda 没有 recipe 的 thin pip 包。
    "GraphST>=1.1.0",
    "torch_geometric>=2.4",
    "cellcharter>=0.2.0",
    "tangram-sc>=1.0.0",
    "cell2location>=0.1.5,<0.2",      # 暂留 pip；conda 上有但版本滞后，待 Task 0 确认
    "flashdeconv>=0.1.0",
    "liana>=1.4.0",                   # 加下界，conda 上有但 lag
    "fastccc>=0.1.0",
    "SpatialDE>=1.1.3",
    "infercnvpy>=0.4.0",
    "paste-bio>=1.0.0",
]
```

注：上面 `cell2location` / `liana` / `infercnvpy` 是中信心档，等 Task 0 CSV 跑完后再决定是否上提。

- [ ] **Step 4: 跑 sanity-check 测试，确认绿**

Run: `mamba run -n OmicsClaw python -m pytest tests/test_pyproject_thin_pip_layer.py -v`
Expected: PASS。

- [ ] **Step 5: 跑现有约束测试，确认未误伤**

Run: `mamba run -n OmicsClaw python -m pytest tests/test_optional_dependency_constraints.py -v`

Expected: 部分测试可能 FAIL，因为 scvi-tools/cellrank/multiqc 已经从 pyproject 移除。立即更新这些测试 — 既然这些包不再由 pyproject 管理，对应测试应改为：

```python
def test_scvi_tools_no_longer_in_pyproject_pip_layer():
    """scvi-tools is now mamba-owned (environment.yml Tier 4)."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for extra, deps in pyproject["project"]["optional-dependencies"].items():
        for dep in deps:
            req = Requirement(dep)
            assert req.name != "scvi-tools", (
                f"scvi-tools must live in environment.yml only, found in [{extra}]"
            )
```

对 `cellrank`、`multiqc`、`coloredlogs`、`humanfriendly`、`cell2location`（如已迁移）做同样处理。

- [ ] **Step 6: 跑全量测试**

Run: `mamba run -n OmicsClaw python -m pytest tests/ -v -x`
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests/test_pyproject_thin_pip_layer.py \
        tests/test_optional_dependency_constraints.py
git commit -m "refactor(pyproject): remove conda-owned packages from pip layer

Heavy hubs (scvi-tools, scvelo, cellrank, harmonypy, bbknn, scanorama,
torch, scanpy/anndata/squidpy, multiqc, kb-python, etc.) are now installed
via environment.yml Tier 4. pyproject's optional-dependencies retain only
the thin pip residue (SpaGCN, GraphST, cellcharter, paste-bio, flashdeconv,
fastccc, pyVIA, tangram-sc, etc.) — packages that have no conda recipe
or whose conda version lags upstream too far.

Adds tests/test_pyproject_thin_pip_layer.py to enforce the boundary."
```

---

## 阶段 2：精简 0_setup_env.sh

### Task 3：让 Tier 2 只装 thin pip residue + uv 加速回退

**Files:**
- Modify: `0_setup_env.sh:219-237`

**Decision rule:** environment.yml 现在已经把 80% 的 Python 包装好了，pip 的工作量只剩 editable install + 10–15 个 thin pip 包。优先用 `uv`（如果可用）加速；不可用回退 pip。

- [ ] **Step 1: 修改 Tier 2 块**

替换 `0_setup_env.sh:219-237` 整块：

```bash
# ----- Tier 2: thin pip residue -------------------------------------
# After Tier 1 mamba env creation, the bulk of Python deps are already
# installed (see environment.yml Tier 4). Tier 2 here only installs:
#   1. omicsclaw itself in editable mode
#   2. PyPI-only packages with no conda recipe (SpaGCN/GraphST/cellcharter/
#      paste-bio/flashdeconv/fastccc/pyVIA/tangram-sc/...)
#   3. velocyto (no Py3.11 bioconda build)
# Prefer `uv pip install` if available — its PubGrub resolver is dramatically
# faster than pip on the residual graph and never hits resolution-too-deep.
# Fall back to pip with --resolver-max-rounds bump for older toolchains.

echo "[setup_env] Tier 2.0: pip install -e \".[full,singlecell-upstream]\""

if [ -z "${SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL:-}" ]; then
    export SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL=True
    echo "[setup_env] allowing deprecated sklearn placeholder for upstream SpaGCN metadata"
fi

# uv lives in environment.yml (added by this plan) so it should be present
# in the env's bin dir. If not, fall back to pip with bumped max-rounds.
if env_run sh -c 'command -v uv >/dev/null 2>&1'; then
    echo "[setup_env] using uv (PubGrub resolver) for thin pip residue"
    env_run uv pip install -e "$PROJECT_ROOT[full,singlecell-upstream]"
else
    echo "[setup_env] uv not found; falling back to pip with --resolver-max-rounds=200000"
    env_run pip install --resolver-max-rounds=200000 \
        -e "$PROJECT_ROOT[full,singlecell-upstream]"
fi

# Tier 2.1: tools that have no bioconda Python 3.11 build:
#   - velocyto.py: bioconda has only 3.6–3.10 and 3.12 builds, not 3.11.
#                  PyPI name is `velocyto` (the .py suffix is bioconda-only).
echo "[setup_env] Tier 2.1: pip install velocyto"
env_run pip install "velocyto>=0.17.17"

echo "[setup_env] ✔ Tier 2 complete"
```

- [ ] **Step 2: 在 environment.yml Tier 0 加 uv**

```yaml
  # ────────── Tier 0: Python interpreter + build toolchain ──────────
  - python=3.11
  - pip
  - uv                          # PubGrub-resolver pip front-end; used by
                                # 0_setup_env.sh Tier 2 for the thin pip layer
  - gxx_linux-64=12.*
  ...
```

- [ ] **Step 3: 在干净虚拟机上端到端验证**

Run:
```bash
mamba env remove -n OmicsClaw_test -y || true
bash 0_setup_env.sh OmicsClaw_test
```

Expected: Tier 1 mamba 创建成功 → Tier 2 uv 装 thin pip residue 在 30s–2min 内完成 → Tier 3 R 包 → Tier 4 完成。整体退出码 0。

- [ ] **Step 4: 验证 omicsclaw 可用**

Run:
```bash
mamba run -n OmicsClaw_test python omicsclaw.py list | head -20
mamba run -n OmicsClaw_test python omicsclaw.py run spatial-preprocess --demo
mamba run -n OmicsClaw_test python omicsclaw.py run sc-de --demo  # 如果存在
mamba run -n OmicsClaw_test python omicsclaw.py run bulkrna-de --demo
```

Expected: 全部退出码 0；输出目录里有图。

- [ ] **Step 5: Commit**

```bash
git add 0_setup_env.sh environment.yml
git commit -m "feat(setup): use uv for thin pip residue; pip fallback with bumped max-rounds

Tier 2 now only installs editable omicsclaw + ~15 thin pip packages
(SpaGCN, GraphST, cellcharter, paste-bio, flashdeconv, ...). With the
heavy hubs already installed by environment.yml Tier 4, the pip resolve
graph is small enough that uv finishes in under 2 minutes. Falls back
to pip --resolver-max-rounds=200000 if uv is unavailable.

Adds uv to environment.yml Tier 0 to make it available in the env."
```

---

## 阶段 3：Layer 4 子环境基础设施

### Task 4：实现 `omicsclaw/core/external_env.py` 跨环境调用 helper

**Files:**
- Create: `omicsclaw/core/external_env.py`
- Create: `tests/test_external_env.py`

**Architecture:** 三类调用约定，按需求复杂度递增：
1. **One-shot Python eval**: `run_python_in_env(env, "import foo; print(foo.bar())")` — 适合简单查询
2. **Script call**: `run_script_in_env(env, script_path, args)` — 适合带 IO 的处理
3. **AnnData bridge**: `run_anndata_op_in_env(env, runner_module, adata, params)` — 把 AnnData 写到临时 .h5ad，子进程读取处理后写回，主进程合并 — 用于 banksy/cnvkit 这种需要传输 anndata 对象的场景

- [ ] **Step 1: 写测试，先红**

```python
# tests/test_external_env.py
"""Tests for the cross-env subprocess bridge."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from omicsclaw.core.external_env import (
    EnvNotFoundError,
    is_env_available,
    run_python_in_env,
)


def _current_env_name() -> str:
    """Return the active conda env name, or skip if not in a conda env."""
    name = os.environ.get("CONDA_DEFAULT_ENV", "")
    if not name or not shutil.which("mamba"):
        pytest.skip("requires conda/mamba env")
    return name


def test_is_env_available_true_for_current_env():
    name = _current_env_name()
    assert is_env_available(name)


def test_is_env_available_false_for_missing_env():
    assert not is_env_available("omicsclaw_definitely_does_not_exist_xyz")


def test_run_python_in_env_returns_stdout():
    name = _current_env_name()
    out = run_python_in_env(name, "import sys; print(sys.version_info[0])")
    assert out.strip() == "3"


def test_run_python_in_env_raises_on_missing_env():
    with pytest.raises(EnvNotFoundError):
        run_python_in_env("omicsclaw_does_not_exist", "print(1)")


def test_run_python_in_env_propagates_subprocess_error():
    name = _current_env_name()
    with pytest.raises(subprocess.CalledProcessError):
        run_python_in_env(name, "raise RuntimeError('boom')")
```

- [ ] **Step 2: 跑测试，确认红**

Run: `mamba run -n OmicsClaw python -m pytest tests/test_external_env.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_env_available'`.

- [ ] **Step 3: 写实现**

```python
# omicsclaw/core/external_env.py
"""Cross-environment subprocess helpers.

OmicsClaw runs the bulk of its skills inside the primary conda env
(`OmicsClaw`). Some tools have hard dependency conflicts with the primary
env (e.g. pybanksy requires numpy<2.0 while scvi-tools requires numpy>=2.0).
For those, we maintain dedicated sub-envs named `omicsclaw_<tool>` and
shell out via `mamba run -n omicsclaw_<tool> python ...`.

This module provides three call shapes:
  - run_python_in_env(env, code)             # one-shot eval
  - run_script_in_env(env, script, args)     # IO-bearing script
  - run_anndata_op_in_env(env, runner, adata, params)
                                             # AnnData bridge via .h5ad
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "EnvNotFoundError",
    "is_env_available",
    "run_python_in_env",
    "run_script_in_env",
    "run_anndata_op_in_env",
]


class EnvNotFoundError(RuntimeError):
    """Raised when the requested conda env is not registered."""


def _runner() -> str:
    if shutil.which("mamba"):
        return "mamba"
    if shutil.which("conda"):
        return "conda"
    raise RuntimeError("neither mamba nor conda is on PATH")


def is_env_available(env: str) -> bool:
    """Return True if a conda env named `env` exists."""
    runner = _runner()
    res = subprocess.run(
        [runner, "env", "list"], capture_output=True, text=True, check=False
    )
    if res.returncode != 0:
        return False
    for line in res.stdout.splitlines():
        if line.strip().startswith("#") or not line.strip():
            continue
        first = line.split()[0]
        if first == env:
            return True
    return False


def run_python_in_env(env: str, code: str, *, timeout: float | None = None) -> str:
    """Run a Python one-liner in another conda env, return stdout.

    Raises:
        EnvNotFoundError: if `env` does not exist.
        subprocess.CalledProcessError: if the subprocess exits non-zero.
    """
    if not is_env_available(env):
        raise EnvNotFoundError(f"conda env not found: {env!r}")
    runner = _runner()
    cmd = [runner, "run", "-n", env, "--no-capture-output", "python", "-c", code]
    res = subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=timeout
    )
    return res.stdout


def run_script_in_env(
    env: str,
    script: str | Path,
    args: Sequence[str] = (),
    *,
    timeout: float | None = None,
) -> str:
    """Run a Python script in another env. `script` must be readable from both envs."""
    if not is_env_available(env):
        raise EnvNotFoundError(f"conda env not found: {env!r}")
    runner = _runner()
    cmd = [runner, "run", "-n", env, "--no-capture-output", "python", str(script), *args]
    res = subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=timeout
    )
    return res.stdout


def run_anndata_op_in_env(
    env: str,
    runner_script: str | Path,
    adata: "Any",  # AnnData; not imported here to keep this module dep-light
    params: dict | None = None,
    *,
    timeout: float | None = None,
) -> "Any":
    """Bridge an AnnData object into a sub-env, run a script, get AnnData back.

    The `runner_script` is invoked in `env` with two args:
        --input <tmp_in.h5ad>  --output <tmp_out.h5ad>
    plus `--params <json>` if `params` is non-empty. The script is responsible
    for loading the input, doing its work, and writing the output.
    """
    import anndata  # local import — main env has anndata, sub-env may not yet

    if not is_env_available(env):
        raise EnvNotFoundError(f"conda env not found: {env!r}")

    with tempfile.TemporaryDirectory(prefix="omicsclaw_xenv_") as tmp:
        tmp_in = Path(tmp) / "in.h5ad"
        tmp_out = Path(tmp) / "out.h5ad"
        adata.write_h5ad(tmp_in, compression="gzip")

        args = ["--input", str(tmp_in), "--output", str(tmp_out)]
        if params:
            args.extend(["--params", json.dumps(params)])

        run_script_in_env(env, runner_script, args, timeout=timeout)

        if not tmp_out.exists():
            raise RuntimeError(
                f"sub-env runner did not write output: {runner_script} in {env}"
            )
        return anndata.read_h5ad(tmp_out)
```

- [ ] **Step 4: 跑测试，确认绿**

Run: `mamba run -n OmicsClaw python -m pytest tests/test_external_env.py -v`
Expected: PASS（如果不在 conda env 里则 SKIP — 测试已带 skip 守卫）。

- [ ] **Step 5: Commit**

```bash
git add omicsclaw/core/external_env.py tests/test_external_env.py
git commit -m "feat(core): add external_env helper for cross-env subprocess bridge

Provides run_python_in_env / run_script_in_env / run_anndata_op_in_env
for skills that need to call out to a sub-env (e.g. omicsclaw_banksy
which pins numpy<2.0). The AnnData bridge writes via temporary .h5ad
files, so the main env and sub-env only need to share the file system,
not the Python ABI."
```

### Task 5：Banksy 子环境作为首个落地用例

**Files:**
- Create: `environments/banksy.yml`
- Create: `skills/spatial/_lib/_runners/banksy_runner.py`
- Modify: `skills/spatial/_lib/domains.py:629-770`（`identify_domains_banksy`）
- Modify: `skills/spatial/_lib/dependency_manager.py:80-82`
- Modify: `0_setup_env.sh`（新增可选 Tier 5 子环境引导）

**Architecture:** 主 env 不再装 pybanksy；用户跑 `--method banksy` 时，主进程把 AnnData 写到 .h5ad，调用 `omicsclaw_banksy` 子环境跑 `banksy_runner.py`，把结果（embedding + obs 标签）写回 .h5ad，主进程读回合并。

- [ ] **Step 1: 写子环境定义文件**

```yaml
# environments/banksy.yml
# Sub-env for pybanksy: requires numpy<2.0, conflicts with main OmicsClaw env
# (numpy>=2.0 via scvi-tools/numba). Bootstrap via `mamba env create -f
# environments/banksy.yml`. Invoked at runtime by skills/spatial/_lib/domains.py
# `identify_domains_banksy` through omicsclaw.core.external_env.
name: omicsclaw_banksy
channels:
  - conda-forge
  - bioconda
  - nodefaults
dependencies:
  - python=3.11
  - pip
  - numpy<2.0
  - pandas<2.2
  - scipy
  - scikit-learn
  - anndata>=0.10,<0.11        # match main-env writer protocol
  - scanpy<1.10                # banksy upstream tested against scanpy 1.9
  - python-igraph
  - leidenalg
  - umap-learn
  - pip:
      - pybanksy>=1.3.0
```

- [ ] **Step 2: 写 banksy runner（在子环境里执行）**

```python
# skills/spatial/_lib/_runners/banksy_runner.py
"""BANKSY runner script. Runs inside the `omicsclaw_banksy` sub-env.

Reads --input (.h5ad), runs BANKSY domain identification, writes --output (.h5ad)
with the BANKSY embedding in obsm['X_banksy_pca'] and cluster labels in
obs['spatial_domain']. Parameters are passed as a JSON blob via --params.

Do NOT import OmicsClaw modules here — the sub-env does not have omicsclaw
installed, only the BANKSY-specific deps from environments/banksy.yml.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
from banksy.embed_banksy import generate_banksy_matrix
from banksy.initialize_banksy import initialize_banksy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--params", default="{}")
    args = ap.parse_args()

    params = json.loads(args.params)
    lambda_param = float(params.get("lambda_param", 0.8))
    k_geom = int(params.get("k_geom", 10))
    pca_dims = int(params.get("pca_dims", 20))
    resolution = float(params.get("resolution", 0.5))
    n_neighbors = int(params.get("n_neighbors", 15))
    use_kmeans = bool(params.get("use_kmeans", False))
    n_clusters = params.get("n_clusters")  # int or None

    adata = anndata.read_h5ad(args.input)

    banksy_dict = initialize_banksy(
        adata, lambda_param=lambda_param, k_geom=k_geom
    )
    _, banksy_matrix = generate_banksy_matrix(
        adata, banksy_dict, lambda_param=lambda_param
    )
    sc.pp.pca(banksy_matrix, n_comps=pca_dims)

    if use_kmeans:
        from sklearn.cluster import KMeans

        if n_clusters is None:
            raise ValueError("use_kmeans=True requires n_clusters")
        labels = KMeans(n_clusters=int(n_clusters), n_init=10, random_state=0).fit_predict(
            banksy_matrix.obsm["X_pca"]
        )
        banksy_matrix.obs["banksy_cluster"] = pd.Categorical(labels.astype(str))
    else:
        sc.pp.neighbors(banksy_matrix, use_rep="X_pca", n_neighbors=n_neighbors)
        sc.tl.leiden(
            banksy_matrix,
            resolution=resolution,
            flavor="igraph",
            key_added="banksy_cluster",
        )

    adata.obs["spatial_domain"] = banksy_matrix.obs["banksy_cluster"].values
    adata.obsm["X_banksy_pca"] = banksy_matrix.obsm["X_pca"]
    adata.uns["banksy_meta"] = {
        "lambda_param": lambda_param,
        "k_geom": k_geom,
        "pca_dims": pca_dims,
        "resolution": resolution,
        "n_domains": int(banksy_matrix.obs["banksy_cluster"].nunique()),
        "banksy_features": int(banksy_matrix.n_vars),
    }
    adata.write_h5ad(args.output, compression="gzip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 改 dependency_manager.py 让 banksy 改走 sub-env 检测**

把 `skills/spatial/_lib/dependency_manager.py:80-82` 的 banksy 条目从"检查能否 import banksy"改成"检查 omicsclaw_banksy 子环境是否存在"。

```python
# skills/spatial/_lib/dependency_manager.py
# (existing imports stay)
from omicsclaw.core.external_env import is_env_available

# ... existing DependencyInfo entries ...

    # banksy lives in a dedicated sub-env (numpy<2.0 conflicts with main env).
    # Override the default importability check with a sub-env existence check.
    "pybanksy": DependencyInfo(
        package="banksy",
        install_hint=(
            "BANKSY requires the `omicsclaw_banksy` sub-env "
            "(numpy<2.0, conflicts with main env). "
            "Create it via: mamba env create -f environments/banksy.yml"
        ),
        availability_check=lambda: is_env_available("omicsclaw_banksy"),
    ),
```

> 假设 `DependencyInfo` 当前没有 `availability_check` 字段。如果没有，在 `DependencyInfo` 数据类上加一个可选回调：
> ```python
> @dataclass
> class DependencyInfo:
>     package: str
>     install_hint: str
>     availability_check: Callable[[], bool] | None = None
> ```
> 并在 `require()` 函数里：当 `availability_check` 非空时优先调用它而不是 `importlib.util.find_spec`。

- [ ] **Step 4: 改 `identify_domains_banksy` 走 sub-env**

把 `skills/spatial/_lib/domains.py:629-770` 整体替换：

```python
def identify_domains_banksy(
    adata,
    lambda_param: float = 0.8,
    k_geom: int = 10,
    pca_dims: int = 20,
    resolution: float = 0.5,
    num_neighbours: int = 15,
    use_kmeans: bool = False,
    n_clusters: int | None = None,
):
    """BANKSY spatial domain identification (runs in `omicsclaw_banksy` sub-env)."""
    from omicsclaw.core.external_env import run_anndata_op_in_env
    from skills.spatial._lib import dependency_manager as _dm
    from pathlib import Path

    _dm.require("banksy", feature="BANKSY spatial domain identification")

    runner = (
        Path(__file__).resolve().parent / "_runners" / "banksy_runner.py"
    )
    params = {
        "lambda_param": lambda_param,
        "k_geom": k_geom,
        "pca_dims": pca_dims,
        "resolution": resolution,
        "n_neighbors": num_neighbours,
        "use_kmeans": use_kmeans,
        "n_clusters": n_clusters,
    }

    adata_out = run_anndata_op_in_env(
        env="omicsclaw_banksy",
        runner_script=runner,
        adata=adata,
        params=params,
    )

    # propagate sub-env results back into the caller's AnnData
    adata.obs["spatial_domain"] = adata_out.obs["spatial_domain"].values
    adata.obsm["X_banksy_pca"] = adata_out.obsm["X_banksy_pca"]
    return {
        "method": "banksy",
        **adata_out.uns.get("banksy_meta", {}),
    }
```

- [ ] **Step 5: 在 `0_setup_env.sh` 加可选的 banksy 子环境引导**

在 Tier 4 之后插一段 Tier 5：

```bash
# ----- Tier 5: optional sub-environments (Layer 4) -----------------
# Tools whose dependency pins conflict with the main env live in dedicated
# sub-envs named `omicsclaw_<tool>`, invoked at runtime via subprocess
# bridge (see omicsclaw/core/external_env.py).
#
# Bootstrap is opt-in: pass `--with-banksy` (or set OMICSCLAW_WITH_BANKSY=1)
# to install. Default skips to keep base-install fast.

bootstrap_subenv() {
    local sub_name="$1"
    local sub_yml="$2"
    if [ ! -f "$sub_yml" ]; then
        echo "[setup_env] ⚠ sub-env file missing: $sub_yml" >&2
        return 1
    fi
    if "$INSTALLER" env list | awk '{print $1}' | grep -qx "$sub_name"; then
        echo "[setup_env] sub-env '$sub_name' exists — updating"
        CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env update -n "$sub_name" -f "$sub_yml" --prune
    else
        echo "[setup_env] creating sub-env '$sub_name'"
        CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env create -n "$sub_name" -f "$sub_yml"
    fi
}

if [ "${OMICSCLAW_WITH_BANKSY:-0}" = "1" ] || [[ " $* " == *" --with-banksy "* ]]; then
    echo "[setup_env] Tier 5: bootstrapping omicsclaw_banksy sub-env"
    bootstrap_subenv "omicsclaw_banksy" "$PROJECT_ROOT/environments/banksy.yml"
    echo "[setup_env] ✔ Tier 5 (banksy) complete"
else
    echo "[setup_env] Tier 5 skipped (set OMICSCLAW_WITH_BANKSY=1 to enable banksy)"
fi
```

> 注：`*` 解析 `bash 0_setup_env.sh OmicsClaw --with-banksy` 这种用法。如果 ENV_NAME 已经是 $1，需要把 `--with-banksy` 走 `getopts` 或在脚本头明确分离 positional 与 flag。这里采用最简单的"包含字符串匹配"，实施时可改为 getopts。

- [ ] **Step 6: 端到端验证**

```bash
# 重建主 env（不带 banksy）
mamba env remove -n OmicsClaw_test -y || true
bash 0_setup_env.sh OmicsClaw_test
# 不应该装 pybanksy
mamba run -n OmicsClaw_test python -c "import banksy" 2>&1 | grep -q "ModuleNotFoundError"

# 单独建子 env
OMICSCLAW_WITH_BANKSY=1 bash 0_setup_env.sh OmicsClaw_test
mamba env list | grep -q "^omicsclaw_banksy"

# 跑 banksy demo
mamba run -n OmicsClaw_test python omicsclaw.py run spatial-domains --demo --method banksy
```

Expected: 主 env 不含 banksy；子 env 创建成功；banksy demo 跑出 spatial_domain 列。

- [ ] **Step 7: Commit**

```bash
git add environments/banksy.yml \
        skills/spatial/_lib/_runners/banksy_runner.py \
        skills/spatial/_lib/domains.py \
        skills/spatial/_lib/dependency_manager.py \
        0_setup_env.sh
git commit -m "feat(env): isolate pybanksy in omicsclaw_banksy sub-env

pybanksy requires numpy<2.0 which conflicts with the main env. Move it
to a dedicated sub-env (environments/banksy.yml) and bridge via the
external_env helper:
  - new environments/banksy.yml defines the sub-env
  - new skills/spatial/_lib/_runners/banksy_runner.py runs in the sub-env
  - identify_domains_banksy now writes adata to .h5ad, calls the runner
    via mamba run -n omicsclaw_banksy, reads results back
  - 0_setup_env.sh Tier 5 optionally bootstraps the sub-env when
    OMICSCLAW_WITH_BANKSY=1 or --with-banksy is passed
  - dependency_manager redirects 'banksy' availability check to sub-env"
```

---

## 阶段 4：源码 vendored 路径占位（Layer 3）

### Task 6：在 `0_build_vendored_tools.sh` 落实 vendored convention

**Files:**
- Modify: `0_build_vendored_tools.sh`（已有，目前空 stub）
- Create: `tools/README.md`
- Modify: `0_setup_env.sh:282-297`（Tier 4 链接占位）

**Decision rule:** Layer 3 不立即引入新工具，只做"约定 + 文档 + 第一个示例 build 函数（注释掉）"。当未来某个 bioinformatics CLI 在 bioconda 没有 Py3.11 build 且 pip 也装不上时，按约定补一段 build 块。

- [ ] **Step 1: 写 `tools/README.md`**

```markdown
# tools/ — vendored source builds

OmicsClaw vendors source builds here when a tool meets ALL of these:
1. Not on bioconda for Python 3.11 (or for Linux x86_64).
2. Not on PyPI, or PyPI version is broken.
3. Not appropriate for a Layer 4 sub-env (i.e. not a Python lib with
   conflicting deps; rather a CLI binary or self-contained library).

## Layout

Each vendored tool gets its own directory:

    tools/
    ├── README.md
    ├── <tool-name>/
    │   ├── upstream/        # git submodule or unpacked tarball
    │   ├── build/           # generated; gitignored
    │   └── bin/             # final binaries; symlinked into $CONDA_PREFIX/bin

## Adding a new vendored tool

1. Add a `build_<tool>()` function to `0_build_vendored_tools.sh` that:
   - Fetches source (git clone or curl + tar)
   - Configures + builds inside the active conda env (so it picks up
     gxx/sysroot from environment.yml Tier 0)
   - Installs binaries into `tools/<tool-name>/bin/`
2. Add `link_if_exists "$TOOLS_DIR/<tool-name>/bin/<binary>"` to
   `0_setup_env.sh` Tier 4.
3. Document the upstream source URL and build prerequisites in this README.

## Why not just `apt install` / `mamba install`?

- `apt`: distro-pinned versions, no Python integration, breaks reproducibility
- `mamba`: covers 95% of bioinformatics CLIs already (see environment.yml).
  Vendored builds are the 5% escape hatch.
```

- [ ] **Step 2: 把 `0_build_vendored_tools.sh` 改成可执行模板**

```bash
#!/usr/bin/env bash
# OmicsClaw vendored tool builder
#
# Add a build_<tool>() function below for each tool that meets the criteria
# in tools/README.md. Then add a `build_<tool>` call to the dispatch block
# at the bottom and a `link_if_exists` line to 0_setup_env.sh Tier 4.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"

mkdir -p "$TOOLS_DIR"

# Example template (commented out — uncomment + adapt when needed):
#
# build_examplebio() {
#     local name="examplebio"
#     local repo="https://github.com/example/examplebio.git"
#     local rev="v1.2.3"
#     local dest="$TOOLS_DIR/$name"
#
#     if [ -e "$dest/bin/examplebio" ]; then
#         echo "[vendored] $name already built — skipping"
#         return 0
#     fi
#
#     mkdir -p "$dest"
#     if [ ! -d "$dest/upstream" ]; then
#         git clone --depth 1 --branch "$rev" "$repo" "$dest/upstream"
#     fi
#
#     pushd "$dest/upstream" >/dev/null
#     mkdir -p "$dest/build"
#     cmake -B "$dest/build" -S . -DCMAKE_INSTALL_PREFIX="$dest"
#     cmake --build "$dest/build" -j"$(nproc)"
#     cmake --install "$dest/build"
#     popd >/dev/null
#
#     echo "[vendored] $name built — binaries in $dest/bin"
# }

# Dispatch — call build_<tool> for each vendored tool.
# Currently empty.

echo "[vendored] no tools to build (stub)"
```

- [ ] **Step 3: Commit**

```bash
git add tools/README.md 0_build_vendored_tools.sh
git commit -m "docs(tools): document vendored build convention; promote stub to template"
```

---

## 阶段 5：端到端验证 + 文档

### Task 7：写端到端 smoke test

**Files:**
- Create: `scripts/smoke_test_setup.sh`

- [ ] **Step 1: 写脚本**

```bash
#!/usr/bin/env bash
# End-to-end smoke test for 0_setup_env.sh.
# Builds a fresh env in a throwaway name, runs core demos, verifies imports.
# Run on a clean machine before tagging a release.

set -euo pipefail

ENV_NAME="${1:-OmicsClaw_smoketest_$(date +%s)}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
    echo "[smoke] removing test env $ENV_NAME"
    mamba env remove -n "$ENV_NAME" -y >/dev/null 2>&1 || true
    mamba env remove -n omicsclaw_banksy -y >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "$PROJECT_ROOT"

echo "[smoke] === Stage 1: bash 0_setup_env.sh $ENV_NAME ==="
time bash 0_setup_env.sh "$ENV_NAME"

echo "[smoke] === Stage 2: import smoke ==="
mamba run -n "$ENV_NAME" python - <<'PY'
import importlib
mods = [
    "scanpy", "anndata", "squidpy", "scvi", "scvelo", "cellrank",
    "torch", "harmonypy", "bbknn", "scanorama",
    "celltypist", "cellphonedb", "gseapy", "pydeseq2",
    "scrublet", "doubletdetection", "arboreto", "palantir",
    "multiqc", "kb_python",
    "esda", "libpysal", "pysal", "ot",
    # thin pip residue
    "spagcn", "GraphST", "tangram",
    # omicsclaw itself
    "omicsclaw",
]
failed = []
for m in mods:
    try:
        importlib.import_module(m)
        print(f"  OK  {m}")
    except Exception as exc:  # noqa: BLE001 — we want all failures listed
        print(f"  FAIL {m}: {exc}")
        failed.append(m)
if failed:
    raise SystemExit(f"{len(failed)} import(s) failed: {failed}")
PY

echo "[smoke] === Stage 3: demo skills ==="
mamba run -n "$ENV_NAME" python omicsclaw.py run spatial-preprocess --demo
mamba run -n "$ENV_NAME" python omicsclaw.py run spatial-domains --demo --method leiden
mamba run -n "$ENV_NAME" python omicsclaw.py run bulkrna-de --demo

echo "[smoke] === Stage 4: banksy sub-env (opt-in) ==="
OMICSCLAW_WITH_BANKSY=1 bash 0_setup_env.sh "$ENV_NAME"
mamba env list | grep -q '^omicsclaw_banksy'
mamba run -n "$ENV_NAME" python omicsclaw.py run spatial-domains --demo --method banksy

echo "[smoke] ✔ all stages passed"
```

- [ ] **Step 2: 在 CI 友好的方式跑一次（本地，慢）**

Run: `bash scripts/smoke_test_setup.sh`
Expected: 三个 stage 全过；总耗时 5–15 min。

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_test_setup.sh
git commit -m "test(setup): add end-to-end smoke test for 4-layer env management"
```

### Task 8：更新 README 与设计 spec

**Files:**
- Modify: `README.md`（保留既有结构，加一节"Environment Management"）
- Modify: `README_zh-CN.md`（同步中文版）
- Modify: `docs/superpowers/specs/2026-05-02-mamba-first-env-design.md`（如已在 Task 0 创建则补完）

- [ ] **Step 1: README 加 "Environment Management" 段落（preserve existing structure）**

在 README.md 现有"Setup"或"Installation"段之后插入：

```markdown
## Environment Management

OmicsClaw uses a 4-layer dependency strategy, all routed through a single
`bash 0_setup_env.sh` entrypoint:

| Layer | Owner | Where it lives | What goes here |
|---|---|---|---|
| 0 — Foundation | mamba | `environment.yml` Tier 0 | python, R, gxx, cmake, build toolchain |
| 1 — Heavy Python | mamba | `environment.yml` Tier 4 | scanpy/anndata/squidpy, torch, scvi-tools, scvelo, cellrank, harmonypy/bbknn/scanorama, celltypist, gseapy, pydeseq2, multiqc, kb-python, ... |
| 2 — Thin pip residue | pip (uv-accelerated) | `pyproject.toml` extras | omicsclaw editable + PyPI-only packages (SpaGCN, GraphST, cellcharter, paste-bio, flashdeconv, fastccc, pyVIA, tangram-sc, ...) |
| 3 — Vendored sources | source build | `tools/<name>/`, `0_build_vendored_tools.sh` | bioinformatics CLIs without bioconda Py3.11 builds |
| 4 — Isolated sub-envs | mamba | `environments/<tool>.yml` | hard-conflict deps (banksy: numpy<2.0; cnvkit: pandas<2.0) |

Decision rule (top-down, first match wins): if a package can live in the
main env, it does. Sub-envs are only for hard conflicts (incompatible
major-version pins on numpy/pandas/etc.). Calls into a sub-env go through
`omicsclaw.core.external_env.run_anndata_op_in_env`, which bridges via
temporary .h5ad files.

### Common installs

```bash
# Default: Layers 0–2 (covers all skills except banksy)
bash 0_setup_env.sh

# With banksy sub-env (Layer 4)
OMICSCLAW_WITH_BANKSY=1 bash 0_setup_env.sh

# CUDA users: after the default install, override pytorch:
mamba install -n OmicsClaw -c pytorch -c nvidia pytorch-cuda=12.1
```

See `docs/superpowers/specs/2026-05-02-mamba-first-env-design.md` for the
design rationale (including why pip 24.2's `resolution-too-deep` made the
old all-pip strategy untenable).
```

- [ ] **Step 2: README_zh-CN.md 同步中文版**

把同样的内容翻成中文加进去。表格表头和列保留英文文件名（`environment.yml` 等）。

- [ ] **Step 3: 完善 spec 文档**

在 `docs/superpowers/specs/2026-05-02-mamba-first-env-design.md` 里补：
- Background：pip 24.2 `resolution-too-deep` 复盘
- Decision：4 层模型 + 决策树
- Implementation：Phase 0–5 任务回看
- Migration plan：当前 OmicsClaw env 用户怎么平滑升级（建议 `mamba env remove -n OmicsClaw && bash 0_setup_env.sh`）
- Open questions：哪些"中信心"包（liana/infercnvpy/cell2location/tangram-sc）等 Task 0 CSV 跑完后再决定是否上提

- [ ] **Step 4: Commit**

```bash
git add README.md README_zh-CN.md \
        docs/superpowers/specs/2026-05-02-mamba-first-env-design.md
git commit -m "docs(env): document 4-layer dependency strategy

README + spec now describe the mamba-first / pip-thin / vendored / sub-env
model. Includes CUDA override snippet and the rationale for moving heavy
hubs out of pip (pip 24.2 resolution-too-deep)."
```

---

## 自检清单（完成所有任务后跑一次）

- [ ] `git status` 干净
- [ ] `bash scripts/smoke_test_setup.sh` 全过（含 banksy stage）
- [ ] `mamba run -n OmicsClaw python -m pytest tests/ -v` 全绿
- [ ] `python omicsclaw.py run spatial-pipeline --demo` 跑通
- [ ] `python omicsclaw.py run sc-de --demo` 跑通（如该 skill 存在）
- [ ] `python omicsclaw.py run bulkrna-de --demo` 跑通
- [ ] `OMICSCLAW_WITH_BANKSY=1 python omicsclaw.py run spatial-domains --demo --method banksy` 跑通
- [ ] README.md / README_zh-CN.md 反映新模型
- [ ] `docs/superpowers/specs/2026-05-02-mamba-first-env-design.md` 完整
- [ ] CSV `docs/superpowers/specs/conda-availability-2026-05-02.csv` 存档
- [ ] pyproject.toml 通过 `tests/test_pyproject_thin_pip_layer.py`（边界守卫）

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| 某个"高信心"包在 conda 上版本太旧 | 在 Task 1 Step 2 验证；版本不行就降级到 `pip:` 子段或保留 pyproject extra |
| `mamba env create` 在 Tier 4 加包后变慢 | mamba 用 SAT solver，加 50 个包通常 +30s–2min；若超 10min 检查是否引入了 channel 冲突 |
| banksy 子环境磁盘开销 | ~2 GB，opt-in；只对显式 `--with-banksy` 用户生效 |
| 已有用户机器 `OmicsClaw` env 升级路径 | spec 里写明：`mamba env update -n OmicsClaw -f environment.yml --prune`；若失败就 remove + 重建 |
| pyproject 里依然存在的小众包（fastccc/pyVIA/...）pip 装不上 | uv fallback 已就位；最坏情况跳过 extra，不阻塞主 env |
| CUDA torch 用户 | 主 env 默认 CPU；README 给 override 命令 |

## 不做的事（YAGNI）

- 不重命名 `[full]` extra（保留向后兼容）
- 不引入 `poetry` / `pdm` 替代 pip
- 不引入 `pixi`（虽然合适，但增加学习成本；待项目稳定后再评估）
- 不并行化 setup 脚本（mamba 内部已并行；外层并行收益小）
- 不为 cellranger / cnvkit 立刻建子环境（推迟到真有用户提需求）
- 不重写 `0_build_vendored_tools.sh`（保留模板，按需扩展）
