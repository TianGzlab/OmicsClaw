<div align="center">
  <img src="docs/images/OmicsClaw_logo.jpeg" alt="OmicsClaw Logo" width="400"/>

  <h3>🧬 OmicsClaw</h3>
  <p><strong>面向多组学分析的持久化 AI 研究助手</strong></p>
  <p>记住数据 • 保留偏好 • 延续工作流</p>
  <p><em>对话式交互 · 记忆增强 · 本地优先 · 跨平台</em></p>

  <p>
    <a href="README.md"><b>English</b></a> •
    <a href="README_zh-CN.md"><b>简体中文</b></a>
  </p>
</div>

# OmicsClaw

> **一个带记忆的 AI 科研助手。** OmicsClaw 把多组学分析从一次性的命令执行，变成可以持续推进的对话式工作流。它能够记录数据集、分析上下文和用户偏好，并在后续会话中继续推进分析。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/TianGzlab/OmicsClaw/actions)
[![Website](https://img.shields.io/badge/Website-Live-brightgreen.svg)](https://TianGzlab.github.io/OmicsClaw/)

> [!NOTE]
> **🚀 v0.1.1 正式发布**
>
> OmicsClaw v0.1.1 已正式发布。当前版本完成了核心交互与执行框架，提供原生记忆管理面板 Memory Explorer，并内置覆盖多组学领域的 89 个分析技能。欢迎通过 [GitHub Issues](https://github.com/TianGzlab/OmicsClaw/issues) 提交问题和建议。

> 📖 **完整中文文档**：见 [`docs/`](docs/)（在仓库根目录跑 `npx mintlify dev` 本地预览）

<h3>⚡ 一套内核，多种交互界面</h3>

<table>
  <tr>
    <th width="75%"><p align="center">🖥️ CLI / TUI</p></th>
    <th width="25%"><p align="center">📱 移动端（飞书）</p></th>
  </tr>
  <tr>
    <td align="center">
      <video src="https://github.com/user-attachments/assets/a24b16b8-dc72-439a-8fcd-d0c0623a4c8a" autoplay loop muted playsinline width="100%">
        <a href="https://github.com/user-attachments/assets/a24b16b8-dc72-439a-8fcd-d0c0623a4c8a">查看 CLI 演示</a>
      </video>
    </td>
    <td align="center">
      <video src="https://github.com/user-attachments/assets/0ccb21f8-6aa9-45ec-b50d-44146566e64e" width="100%" autoplay loop muted playsinline>
        <a href="https://github.com/user-attachments/assets/0ccb21f8-6aa9-45ec-b50d-44146566e64e">查看移动端演示</a>
      </video>
    </td>
  </tr>
</table>

## 为什么选择 OmicsClaw？

很多分析工具的默认前提是“每次都从头开始”。换一次会话，就要重新说明数据、重新设置参数、重新回忆上一步做到了哪里。OmicsClaw 的重点是把这些上下文保存下来，让分析工作具备连续性。

## ✨ 主要特性

- **🧠 持久记忆**：会话上下文、分析历史和用户偏好可以跨会话保留。
- **🛠️ 可扩展性**：原生支持 MCP，内置 `omics-skill-builder` 用于生成自定义技能脚手架。
- **🌐 多模型后端**：支持 Anthropic、OpenAI、DeepSeek、本地模型等多种 LLM 提供方。
- **📱 多通道接入**：CLI 是核心入口，同时可接入 Telegram、飞书等通讯平台，共享同一套会话和记忆。
- **🔄 工作流连续性**：可以恢复中断任务、追踪分析血缘，减少重复计算。
- **🔒 本地优先**：计算在本地完成，记忆系统仅保存元数据，不上传原始数据。
- **🎯 智能路由**：自然语言请求可自动映射到合适的分析技能。
- **🧬 多组学覆盖**：内置 72 个技能，覆盖空间转录组、单细胞、基因组、蛋白组、代谢组、Bulk RNA-seq、文献挖掘和编排调度。

> **桌面后端健康检查：** 当 `oc app-server` 通过
> `OMICSCLAW_DESKTOP_LAUNCH_ID` 启动时，`/health` 会返回可选的
> `launch_id`。OmicsClaw Desktop 用它做进程握手，避免把已经占用
> 8765 端口的旧后端误认为刚启动的新后端。

> **GraphST + App 超时说明：** `spatial-domain-identification` 现在会把
> 桌面端/对话端传入的 epoch 覆盖值转发到实际的 `--epochs` 技能参数。
> 对 Slide-seq/Slide-seqV2 风格输入，GraphST 会解析到上游
> `datatype='Slide'` 路径，不再误退回默认 `10X` 分支。Slide/Stereo
> 图构建会保留稀疏空间邻接矩阵和 readout mask，避免高分辨率数据上
> 旧实现的 dense `n_obs x n_obs` 内存分配。大数据 GraphST 仍会在
> epoch 之外执行预处理、聚类和写盘，`epochs=1` 应理解为流程冒烟测试，
> 不是瞬时完成的正式分析。

**与传统工具的差异：**

| 传统工具 | OmicsClaw |
|-------------------|-----------|
| 每次会话都要重新指定数据路径 | 自动记住数据路径和元信息 |
| 分析历史难以回溯 | 追踪完整血缘关系（预处理 → 聚类 → 差异分析） |
| 参数需要反复手动输入 | 可记住并复用偏好设置 |
| 只有命令行入口，学习成本较高 | 同时支持自然语言交互和 CLI |
| 一次性、无状态执行 | 支持跨会话持续协作 |

> 📖 **进一步了解：** 参见 [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)，查看带记忆工作流与无状态工具的详细对比。

## 📦 安装

OmicsClaw 提供两种安装路径，按需选择。

### 🥇 Conda（推荐 —— 全功能）

一条命令即可装好 R 4.3 + ~30 个 R 包、~15 个生信命令行工具（samtools、STAR、fastqc、bwa、bowtie2、minimap2、bcftools、gatk4、picard、simpleaf、fastp、trim-galore、macs3、multiqc、kb-python、velocyto……）、OmicsClaw 本体（editable 模式），以及全部 Python 可选扩展。

**先决条件** —— PATH 上需要有 `conda`。如果当前还没有，建议安装 [Miniforge](https://github.com/conda-forge/miniforge)：默认走 `conda-forge` 源、Apache-2.0 协议（商用友好）、内置 `mamba` 加速求解。（`0_setup_env.sh` 会优先用 `mamba` 创建/更新环境，无 `mamba` 时回退到 `conda`。环境发现优先使用 `conda info --envs`，以避开旧 Python 版 `mamba env list` 的解析器崩溃。）

<details>
<summary><b>🆕 安装 Miniforge —— 一次性</b></summary>

**Linux 与 macOS**（自动识别 `x86_64`、`aarch64`、Apple Silicon）：

```bash
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash "Miniforge3-$(uname)-$(uname -m).sh"   # 同意 license；conda init 处选 "yes"
exec "$SHELL"                                # 重启 shell 使 `conda` 进入 PATH
conda --version && mamba --version           # 验证
```

**Windows**：从 [Miniforge releases 页](https://github.com/conda-forge/miniforge/releases/latest) 下载 `.exe` 安装器，按 GUI 提示安装，后续命令在「Miniforge Prompt」里执行。

</details>

```bash
# 1. 克隆并执行 bootstrap
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw
bash 0_setup_env.sh           # 创建名为 "OmicsClaw" 的 conda 环境
conda activate OmicsClaw

# 2. 验证
omicsclaw env                 # 或：python omicsclaw.py env
```

脚本**幂等** —— 重复执行会就地更新现有环境。如需自定义环境名：`bash 0_setup_env.sh my_env_name`。

在共享 conda 安装上，`0_setup_env.sh` 默认把 `CONDA_PKGS_DIRS` 设为
`~/.conda/pkgs`，避免 libmamba 去清理或重新解压系统级 base 缓存
（例如 `/share/.../miniconda3/pkgs`）里的包。如果你想用其它可写缓存，
可在运行脚本前设置 `CONDA_PKGS_DIRS=/path/to/pkgs`。如果安装失败信息是
镜像 SSL timeout，请重试或切换 conda channel / 镜像；这属于网络问题，
不是包缓存权限问题。

Tier 2 的 pip 安装还会设置
`SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL=True`，因为上游 `SpaGCN`
包元数据仍引用已废弃的 `sklearn` PyPI 占位包。OmicsClaw 自身依赖的是正确的
`scikit-learn` 包；该变量只用于允许 SpaGCN 的旧传递依赖元数据完成解析。

完整 Python 依赖会把 `scvi-tools` 限定在 Python 3.11+ 兼容线
（`>=1.4.0,<2.0`），并使用 `cell2location>=0.1.5,<0.2`。旧的
`scvi-tools` 1.3.x 元数据会拉入很宽的 `jax<0.7.0` / `jaxlib<0.7.0`
约束，在部分 PyPI 镜像上会导致 pip 回溯大量 `jax` 版本并报
`resolution-too-deep`。
`singlecell-upstream` 辅助栈也会显式限定 MultiQC 日志链路依赖
（`multiqc>=1.33,<2.0`、`coloredlogs>=15.0.1,<16.0`、
`humanfriendly>=10.0,<11.0`），避免 pip 在解析 `multiqc` 时回溯到旧的
`humanfriendly` wheel。
轨迹分析依赖会把 CellRank 限定在最新的 Python 3.11 兼容线
（`>=2.0.7,<2.1`），跳过要求 Python 3.12+ 的 CellRank 2.1+ 版本。
`full` extra 只覆盖分析依赖，默认不包含 `oauth` / `ccproxy-api`；如需
OAuth，请单独运行 `pip install -e ".[oauth]"`，或在明确需要时使用
`pip install -e ".[full,oauth]"`。
CARD 的 CRAN 空间依赖链（`units`、`sf`、`concaveman`）也通过 conda
预装为 `r-units`、`r-sf`、`r-concaveman`，这样 Tier 3 安装
`YMa-lab/CARD` 时不会再临时从源码编译这些重型地理空间包。
CARD 的轻量 `wrMisc` import 和 CellChat 的 `NMF>=0.23.0` 要求会在 Tier 3
从 CRAN 安装 / 更新，而不是只依赖 conda 包：conda-forge 当前 `r-wrmisc`
构建面向 R 4.4/4.5，而 R 4.3 的 `r-nmf` 构建仍是 0.21.0，低于 CellChat
要求的 0.23.0。
Tier 3 其他 GitHub R 根包（`spacexr`、`CellChat`、`numbat`、`SPARK`、
`DoubletFinder`）的 conda 可解析直接 `Depends` / `Imports` / `LinkingTo`
依赖也已前置到 `environment.yml`。对于 `numbat`，Tier 3 会先从 CRAN 显式安装
`hahmmr` 和 `scistreer>=1.1.0`，再安装 `kharchenkolab/numbat`；
`scistreer` 的编译型依赖 `phangorn` 和 R 4.3 兼容的 `RcppParallel` 构建
保持由 conda 层提供。
这 6 个 GitHub 根包以及 `numbat -> hahmmr/scistreer` 预检链都有安装脚本回归
测试覆盖：测试会解析它们的必需 `Depends` / `Imports` / `LinkingTo` 元数据，
如果某个必需依赖既不归 `environment.yml` 管理，也不在 Tier 3 CRAN 预检里，
就会失败。
GitHub 安装不再重新执行 R 依赖解析，并跳过
vignettes / manuals，因此 setup 不会受当前 CRAN 传递依赖漂移影响，例如 R 4.3
基线上的 `CellChat -> ggpubr -> doBy -> forecast` 链。

如果上一次安装中断后留下了完整的 `<conda-root>/envs/OmicsClaw` prefix，
但 `conda info --envs` 没有按名称列出它，脚本会识别该 prefix，包括只显示
路径、不显示名称的匿名 env-list 行，并使用 `env update -p <prefix>` 继续更新。
如果 prefix 目录存在但没有 `conda-meta`，脚本会把它视为不完整环境；删除或修复该目录后再重新运行脚本。

> **提示**：`cnvkit`（用于 `genomics-cnv-calling`）**未预装**，因为其新版本依赖与 `macs3` 冲突。如需使用，请在单独的环境里安装。

### 🪶 venv（轻量 —— 仅 Python 技能）

适用于只需要 **LLM / 路由 / 对话** 等接口、不跑分析的用户。该路径**不会安装 R、samtools、STAR、fastqc 等**，依赖这些工具的技能在运行时会报「tool not on PATH」。

<details>
<summary>使用 venv 安装</summary>

**方案 A：使用 `venv`**
```bash
# 1. 创建虚拟环境
python3 -m venv .venv

# 2. 激活虚拟环境
source .venv/bin/activate
```

**方案 B：使用 `uv`**
```bash
# 1. 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 创建并激活虚拟环境
uv venv
source .venv/bin/activate
```

**安装 OmicsClaw**：
```bash
# 克隆仓库
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw

# 安装核心功能
pip install -e .

# 可选：安装 TUI 和 Bot 能力
pip install -e ".[tui]"
pip install -r bot/requirements.txt
```

**分层安装：**
- `pip install -e .`：仅安装核心系统
- `pip install -e ".[<domain>]"`：按领域安装，如 `spatial`、`singlecell`、`genomics`、`proteomics`、`metabolomics`、`bulkrna`
- `pip install -e ".[spatial-domains]"`：安装 SpaGCN / STAGATE 相关深度学习依赖
- `pip install -e ".[full]"`：安装所有领域依赖和可选方法后端

</details>

*随时通过 `omicsclaw env` 或 `python omicsclaw.py env` 查看安装状态。*

## 环境管理

OmicsClaw 采用 4 层依赖策略，统一入口 `bash 0_setup_env.sh`：

| 层 | 谁管 | 落地位置 | 装什么 |
|---|---|---|---|
| 0 — 基底 | mamba | `environment.yml` Tier 0 | python、R、gxx、cmake、构建工具链 |
| 1 — 重型 Python | mamba | `environment.yml` Tier 4 | scanpy/anndata/squidpy、torch、scvi-tools、scvelo、cellrank、harmonypy/bbknn/scanorama、celltypist、gseapy、pydeseq2、multiqc、kb-python … |
| 2 — Thin pip 残留 | pip（uv 加速） | `pyproject.toml` extras | `omicsclaw` editable + 仅 PyPI 的包（SpaGCN、GraphST、cellcharter、paste-bio、flashdeconv、fastccc、pyVIA、tangram-sc …） |
| 3 — 源码 vendored | 源码构建 | `tools/<name>/`、`0_build_vendored_tools.sh` | bioconda 无 Py3.11 build 的生信 CLI（当前空 stub） |
| 4 — 隔离子环境 | mamba | `environments/<tool>.yml` | 硬冲突依赖（banksy: numpy<2.0；未来 cnvkit/cellranger 同槽位） |

决策树（top-down，命中即停）：能放主 env 就放主 env，子 env 只留给真正硬冲突的依赖。
对子 env 的调用通过 `omicsclaw.core.external_env.run_anndata_op_in_env` 桥接，
经临时 `.h5ad` 文件传输 AnnData，主 env 与子 env 不需要共享 Python ABI。

### 常用安装

```bash
# 默认：Layers 0–2（覆盖除 banksy 外的所有 skill）
bash 0_setup_env.sh

# 启用 banksy 子环境（Layer 4，opt-in）：
OMICSCLAW_WITH_BANKSY=1 bash 0_setup_env.sh
# 或：
bash 0_setup_env.sh --with-banksy

# PyTorch 后端选择：
#   auto（默认）：如果 nvidia-smi -L 能看到 GPU，就尝试安装 CUDA PyTorch。
#                 CUDA 设置失败时会警告并保留 CPU baseline。
#   cuda：强制要求 CUDA PyTorch，安装或验证失败则中断 setup。
#   cpu：即使机器有 GPU，也保留 CPU PyTorch baseline。
OMICSCLAW_TORCH_BACKEND=cuda OMICSCLAW_PYTORCH_CUDA_VERSION=12.1 bash 0_setup_env.sh
OMICSCLAW_TORCH_BACKEND=cpu bash 0_setup_env.sh

# 在 GPU 机器上使用 auto/cuda 后，验证 CUDA 是否真的接上：
mamba run -n OmicsClaw python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
# 预期：True <cuda_version>
```

`OMICSCLAW_PYTORCH_CUDA_VERSION` 默认是 `12.1`，会映射为 PyTorch wheel tag
`cu121`。CUDA PyTorch 使用官方 PyTorch wheel index 安装，例如
`https://download.pytorch.org/whl/cu121`，不再让 conda 在已经很大的科学环境里
重新求解 `pytorch-gpu` / `cuda-version`。这样可以避开 `libtorch`、`libarrow`、
`libprotobuf`、`libabseil` 和 BLAS/MKL 包之间的 solver 冲突。高级镜像用户可用
`OMICSCLAW_TORCH_WHEEL_INDEX` 覆盖 wheel index；需要精细控制时也可以设置
`OMICSCLAW_TORCH_VERSION`、`OMICSCLAW_PYTORCH_CUDA_TAG` 或
`OMICSCLAW_TORCH_WHEEL_SPEC`。
选择 CUDA 时，脚本会先移除 CPU-only PyTorch marker 包（`pytorch-cpu` / `cpuonly`），
再安装 CUDA wheel。Tier 2 调用
`uv pip install` 时默认使用 `UV_LINK_MODE=copy`，避免 uv cache 和 conda env
位于不同文件系统时出现 hardlink fallback 警告；如果你希望使用其他 uv 链接策略，
可在运行脚本前自行设置 `UV_LINK_MODE`。远程运行时要在
真正执行分析的服务器上运行 setup；本地 desktop 机器是否有 GPU 不影响远端环境。

新机器端到端冒烟：`bash scripts/smoke_test_setup.sh`。

依赖边界以 [`0_setup_env.sh`](0_setup_env.sh)、[`environment.yml`](environment.yml)
和 [`pyproject.toml`](pyproject.toml) 为准。

## 🔑 配置

**最简单的方式：使用交互式向导**

OmicsClaw 内置了配置向导，可以依次设置 LLM、共享运行时参数、记忆系统和消息通道凭证。

```bash
omicsclaw onboard  # 或使用短命令: oc onboard
```

向导会把结果写入项目根目录下的 `.env` 文件。

<div align="center">
  <img src="docs/images/OmicsClaw_configure_fast.png" alt="OmicsClaw 配置向导" width="85%"/>
</div>

<details>
<summary><b>手动配置（.env）</b></summary>

OmicsClaw 会统一读取项目根目录下的 `.env` 文件，CLI、TUI、路由层和 Bot 入口使用同一套配置。若未安装 `python-dotenv`，系统会退回到内置解析器，因此标准的 `KEY=value` 语法同样可用。

对于云端模型服务，可以使用以下任一种方式：

- 统一使用 `LLM_API_KEY`
- 使用服务商专属变量，如 `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`

**1. DeepSeek（默认）**
```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**2. Anthropic（Claude）**
```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# 系统会自动识别并使用默认模型
```

**3. OpenAI（GPT-4o 等）**
```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**4. 本地模型（Ollama）**
```env
LLM_PROVIDER=ollama
OMICSCLAW_MODEL=qwen2.5:7b
LLM_BASE_URL=http://localhost:11434/v1
```

**5. 自定义兼容 OpenAI 协议的接口**
```env
LLM_PROVIDER=custom
LLM_BASE_URL=https://your-endpoint.example.com/v1
OMICSCLAW_MODEL=your-model-name
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
```

> 📖 **完整服务商列表：** 参见 [`.env.example`](.env.example)。
>
> 📖 **Bot / 通道配置：** 参见 [bot/README.md](bot/README.md) 和 [bot/CHANNELS_SETUP.md](bot/CHANNELS_SETUP.md)。

> **服务商 / 模型归一化：** 如果重启时发现过期的跨服务商组合，例如
> `LLM_PROVIDER=anthropic` 搭配 `OMICSCLAW_MODEL=deepseek-chat`，OmicsClaw
> 会以所选服务商为准，并把模型重置为该服务商默认值，除非你显式配置了
> 自定义 `*_BASE_URL` / `LLM_BASE_URL`。已废弃的 DeepSeek 默认模型
>（`deepseek-chat` / `deepseek-reasoner`）也会迁移到当前 DeepSeek 默认值
> `deepseek-v4-flash`。

</details>

## ⚡ 快速开始

### 1. 交互式聊天界面

```bash
# 启动交互式终端
omicsclaw interactive  # 或: oc interactive
omicsclaw tui          # 或: oc tui

# 或启动消息通道作为前端
python -m bot.run --channels feishu,telegram
```

> 📖 **Bot 配置说明：** 参见 [bot/README.md](bot/README.md)。

**示例：**

```text
用户: "对我的 Visium 数据做预处理"
Bot: ✅ [执行 QC、归一化、聚类]
     💾 [记录: visium_sample.h5ad, 5000 spots, normalized]

[第二天]
用户: "继续做空间结构域识别"
Bot: 🧠 "已找到你昨天处理过的 Visium 数据（5000 spots，已归一化）。
     现在开始进行结构域识别。"
```

<details>
<summary>交互模式下的常用命令（CLI / TUI）</summary>

| 命令 | 说明 |
| ------- | ----------- |
| **分析与调度** | |
| `/run <skill> [...]` | 直接运行分析技能，例如 `/run spatial-domains --demo` |
| `/skills [domain]` | 列出可用技能 |
| `/research` | 启动多智能体研究流程 |
| `/install-skill` | 从本地或 GitHub 安装扩展技能 |
| **工作流与计划** | |
| `/plan` | 查看或创建当前会话计划 |
| `/tasks` | 查看当前流程的结构化任务列表 |
| `/approve-plan` | 批准计划继续执行 |
| `/do-current-task` | 继续执行当前任务 |
| **会话与记忆** | |
| `/sessions` | 查看最近会话 |
| `/resume [id/tag]` | 恢复之前的会话 |
| `/new` / `/clear` | 新建或清空当前会话 |
| `/memory` | 管理语义记忆与实体追踪 |
| `/export` | 导出当前会话结果为 Markdown 报告 |
| **系统与设置** | |
| `/mcp` | 管理 MCP 服务器（`/mcp list/add/remove`） |
| `/config` | 查看或更新模型与引擎配置 |
| `/doctor` / `/usage` | 诊断环境或查看 token 使用量 |
| `/exit` | 退出 OmicsClaw |

</details>

<details>
<summary>Bot 模式下的常用命令（Telegram / 飞书）</summary>

| 命令 | 说明 |
| ------- | ----------- |
| `/start` / `/help` | 查看欢迎信息和帮助 |
| `/skills` | 浏览技能列表 |
| `/demo <skill>` | 运行技能示例 |
| `/new` / `/clear` | 开启新分支或清空当前对话 |
| `/forget` | 清空记忆和会话状态 |
| `/files` / `/outputs` | 查看上传的数据或近期输出 |
| `/recent` | 查看最近 3 次分析记录 |
| `/status` / `/health` | 查看运行状态与健康信息 |

</details>

### 2. 命令行方式

```bash
# 运行 demo（无需自备数据）
python omicsclaw.py run spatial-preprocess --demo

# 使用自己的数据
python omicsclaw.py run spatial-preprocess --input data.h5ad --output results/
```

> 📚 **文档入口：** [INSTALLATION.md](docs/INSTALLATION.md) • [METHODS.md](docs/METHODS.md) • [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)

## Memory System：核心能力之一

OmicsClaw 的记忆系统让它不只是一个“收到命令就执行”的工具，而是能够持续保留研究上下文。配套的 **Memory Explorer** 提供了一个前端界面，用于查看分析历史、数据血缘和用户偏好。

<div align="center">
  <img src="docs/images/memory_system.png" alt="Memory System Explorer Frontend Interface" width="100%"/>
  <br>
  <em>Memory Explorer：用于查看分析历史、数据关系和用户偏好的统一面板。</em>
</div>

**启动方式：**

```bash
# 终端 1：启动后端 API
oc memory-server

# 终端 2：启动前端面板
cd frontend && npm install && npm run dev
```

默认情况下，Memory API 监听在 `127.0.0.1:8766`。如果需要暴露到本机之外，请同时配置 `OMICSCLAW_MEMORY_HOST` 和 `OMICSCLAW_MEMORY_API_TOKEN`。

**桌面 / Web 前端后端：**
```bash
pip install -e ".[desktop]"
oc app-server --host 127.0.0.1 --port 8765
```

该后端默认监听 `127.0.0.1:8765`，提供 OmicsClaw-App 所使用的 HTTP / SSE 接口。`desktop` extra 现在也会安装 notebook 运行时依赖，因此同一个 `oc app-server` 进程会直接暴露嵌入式 notebook 所需的原生 `/notebook/*` 路由。

如果环境里已经安装 `omicsclaw_kg`，或者通过 `OMICSCLAW_KG_SOURCE_DIR=/path/to/OmicsClaw-KG` 提供源码目录，那么同一个 `oc app-server` 进程也会挂载 KG Explorer 所需的 `/kg/*` 路由。前端开发服务器现在默认把 `/kg` 代理到 `app-server`，不再默认依赖单独的 `omicsclaw-kg http serve` 进程。

**系统会记录的内容包括：**

- 📁 **数据集**：文件路径、平台类型（Visium / Xenium）、数据维度、预处理状态
- 📊 **分析记录**：使用的方法、参数、执行时间和血缘关系
- ⚙️ **用户偏好**：偏好的聚类方法、图形风格、物种默认值等
- 🧬 **生物学标注**：如 cluster 对应的细胞类型、domain 对应的组织区域
- 🔬 **项目上下文**：物种、组织类型、疾病模型和研究目标

> 📖 **详细说明：** 参见 [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)。

## 🔌 扩展能力：MCP 与 Skill Builder

OmicsClaw 的扩展设计主要体现在两个方面：

- **Model Context Protocol（MCP）**：可将符合标准的 MCP 服务器接入 OmicsClaw，使其能够访问外部 API、学术数据库、自定义执行环境或企业内部数据服务。可在交互会话中通过 `/mcp` 管理。
- **`omics-skill-builder`**：位于 `skills/orchestrator/`。它可以根据对话意图或 Python 片段生成可复用的技能脚手架，包括 Python 包装层、`SKILL.md` 和注册信息。

## 支持的领域

| 领域 | 技能数 | 主要能力 |
|--------|--------|------------------|
| **空间转录组** | 16 | 质控、聚类、注释、解卷积、空间统计、通讯、速度、轨迹、微环境提取 |
| **单细胞组学** | 14 | 质控、过滤、预处理、双细胞检测、注释、轨迹、批次整合、差异分析、GRN、scATAC 预处理 |
| **基因组学** | 10 | 变异检测、比对、注释、结构变异、组装、单倍型分相、CNV |
| **蛋白组学** | 8 | 质谱质控、肽段鉴定、定量、差异丰度、PTM 分析 |
| **代谢组学** | 8 | 峰检测、XCMS 预处理、注释、归一化、统计分析 |
| **Bulk RNA-seq** | 13 | FASTQ 质控、比对、计数质控、ID 映射、批次校正、差异分析、剪接、富集、解卷积、共表达、PPI、生存分析、轨迹插值 |
| **Orchestrator** | 2 | 多组学查询路由、命名流水线、技能脚手架生成 |
| **Literature** | 1 | 文献解析、GEO / PubMed 信息提取、数据下载 |

**支持的平台 / 数据类型包括：** Visium、Xenium、MERFISH、Slide-seq、10x scRNA-seq、Illumina / PacBio、LC-MS/MS、Bulk RNA-seq（CSV / TSV）

> 📋 **完整技能目录：** 见下方 [技能总览](#技能总览)。

## 技能总览

### 空间转录组（16 个技能）

- **基础流程**：`spatial-preprocess` — 质控、归一化、聚类、UMAP
- **分析技能**：`spatial-domains`、`spatial-annotate`、`spatial-deconv`、`spatial-statistics`、`spatial-genes`、`spatial-de`、`spatial-condition`、`spatial-microenvironment-subset`
- **高级分析**：`spatial-communication`、`spatial-velocity`、`spatial-trajectory`、`spatial-enrichment`、`spatial-cnv`
- **整合与配准**：`spatial-integrate`、`spatial-register`
- **编排路由**：可通过顶层 `orchestrator` 处理跨领域请求和多步流水线

<details>
<summary>展开查看全部空间转录组技能</summary>

| 技能 | 说明 | 主要方法 |
|-------|-------------|-------------|
| `spatial-preprocess` | 质控、归一化、高变基因、PCA、UMAP、聚类 | Scanpy |
| `spatial-domains` | 组织区域 / niche 识别 | Leiden, Louvain, SpaGCN, STAGATE, GraphST, BANKSY, CellCharter |
| `spatial-annotate` | 细胞类型注释 | Marker-based (Scanpy), Tangram, scANVI, CellAssign |
| `spatial-deconv` | 细胞比例估计 | FlashDeconv, Cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD |
| `spatial-statistics` | 空间自相关与网络拓扑分析 | Moran's I, Geary's C, Getis-Ord Gi*, Ripley's L, Co-occurrence, Centrality |
| `spatial-genes` | 空间变异基因识别 | Moran's I, SpatialDE, SPARK-X, FlashS |
| `spatial-de` | 差异表达分析 | Wilcoxon, t-test, PyDESeq2 |
| `spatial-condition` | 条件间比较 | Pseudobulk DESeq2 |
| `spatial-microenvironment-subset` | 按空间半径提取局部邻域 | KDTree, Scanpy |
| `spatial-communication` | 配体-受体通讯推断 | LIANA+, CellPhoneDB, FastCCC, CellChat |
| `spatial-velocity` | RNA velocity / 细胞动力学分析 | scVelo, VELOVI |
| `spatial-trajectory` | 发育轨迹推断 | CellRank, Palantir, DPT |
| `spatial-enrichment` | 通路富集分析 | GSEA, ssGSEA, Enrichr |
| `spatial-cnv` | 拷贝数变异推断 | inferCNVpy, Numbat |
| `spatial-integrate` | 多样本整合 | Harmony, BBKNN, Scanorama |
| `spatial-register` | 空间配准 | PASTE, STalign |

</details>

### 单细胞组学（14 个技能）

- **基础流程**：`sc-qc`、`sc-filter`、`sc-preprocessing`、`sc-ambient-removal`、`sc-doublet-detection`
- **分析技能**：`sc-cell-annotation`、`sc-de`、`sc-markers`
- **高级分析**：`sc-pseudotime`、`sc-velocity`、`sc-grn`、`sc-cell-communication`
- **整合**：`sc-batch-integration`
- **ATAC**：`scatac-preprocessing`

<details>
<summary>展开查看全部单细胞技能</summary>

| 技能 | 说明 | 主要方法 |
|-------|-------------|-------------|
| `sc-qc` | 计算并可视化质控指标 | Scanpy QC |
| `sc-filter` | 按阈值过滤细胞和基因 | Rule-based filtering |
| `sc-preprocessing` | 归一化、高变基因、PCA、UMAP | Scanpy, Seurat, SCTransform |
| `sc-ambient-removal` | 去除 ambient RNA 污染 | CellBender, SoupX, simple |
| `sc-doublet-detection` | 识别并去除双细胞 | Scrublet, DoubletFinder, scDblFinder |
| `sc-cell-annotation` | 细胞类型注释 | markers, CellTypist, SingleR |
| `sc-de` | 差异表达分析 | Wilcoxon, t-test, DESeq2 pseudobulk |
| `sc-markers` | Marker gene 发现 | Wilcoxon, t-test, logistic regression |
| `sc-pseudotime` | 拟时序与轨迹分析 | PAGA, DPT |
| `sc-velocity` | RNA velocity | scVelo |
| `sc-grn` | 基因调控网络推断 | pySCENIC |
| `sc-cell-communication` | 配体-受体通讯分析 | builtin, LIANA, CellChat |
| `sc-batch-integration` | 多样本整合 | Harmony, scVI, BBKNN, Scanorama, fastMNN, Seurat CCA/RPCA |
| `scatac-preprocessing` | scATAC-seq 预处理与聚类 | TF-IDF, LSI, UMAP, Leiden |

</details>

### 基因组学（10 个技能）

- **基础流程**：`genomics-qc`、`genomics-alignment`、`genomics-vcf-operations`
- **分析技能**：`genomics-variant-calling`、`genomics-variant-annotation`、`genomics-sv-detection`、`genomics-cnv-calling`
- **高级分析**：`genomics-assembly`、`genomics-phasing`、`genomics-epigenomics`

<details>
<summary>展开查看全部基因组技能</summary>

| 技能 | 说明 | 主要方法 / 指标 |
|-------|-------------|----------------------|
| `genomics-qc` | FASTQ 质控：Phred、GC/N 含量、Q20/Q30、接头检测 | FastQC, fastp, MultiQC |
| `genomics-alignment` | 比对统计：MAPQ、比对率、insert size、重复率 | BWA-MEM2, Bowtie2, Minimap2 |
| `genomics-vcf-operations` | VCF 解析、多等位位点处理、Ti/Tv、QUAL/DP 过滤 | bcftools, GATK SelectVariants |
| `genomics-variant-calling` | 变异分类与质量评估 | GATK HaplotypeCaller, DeepVariant, FreeBayes |
| `genomics-variant-annotation` | 功能影响注释 | VEP, SnpEff, ANNOVAR |
| `genomics-sv-detection` | 结构变异检测 | Manta, Delly, Lumpy, Sniffles |
| `genomics-cnv-calling` | 拷贝数变异分析 | CNVkit, Control-FREEC, GATK gCNV |
| `genomics-assembly` | 组装质量评估 | SPAdes, Megahit, Flye, Canu |
| `genomics-phasing` | 单倍型分相 | WhatsHap, SHAPEIT5, Eagle2 |
| `genomics-epigenomics` | 峰分析与 assay 特异指标 | MACS2/MACS3, Homer, Genrich |

</details>

### 蛋白组学（8 个技能）

- **基础流程**：`proteomics-data-import`、`proteomics-ms-qc`
- **分析技能**：`proteomics-identification`、`proteomics-quantification`、`proteomics-de`
- **高级分析**：`proteomics-ptm`、`proteomics-enrichment`、`proteomics-structural`

<details>
<summary>展开查看全部蛋白组技能</summary>

| 技能 | 说明 | 主要方法 |
|-------|-------------|-------------|
| `proteomics-data-import` | 原始数据转换为开放格式 | ThermoRawFileParser, msconvert |
| `proteomics-ms-qc` | 质谱质控 | PTXQC, rawtools |
| `proteomics-identification` | 肽段与蛋白鉴定 | MaxQuant, MSFragger, Comet |
| `proteomics-quantification` | 无标或同位素标记定量 | DIA-NN, Skyline, FlashLFQ |
| `proteomics-de` | 差异丰度分析 | MSstats, limma |
| `proteomics-ptm` | 翻译后修饰分析 | PTM-prophet, MaxQuant |
| `proteomics-enrichment` | 蛋白通路富集 | Perseus, clusterProfiler |
| `proteomics-structural` | 三维结构与交联分析 | AlphaFold, xQuest |

</details>

### 代谢组学（8 个技能）

- **基础流程**：`metabolomics-peak-detection`、`metabolomics-xcms-preprocessing`、`metabolomics-normalization`
- **分析技能**：`metabolomics-annotation`、`metabolomics-quantification`、`metabolomics-statistics`、`metabolomics-de`
- **高级分析**：`metabolomics-pathway-enrichment`

<details>
<summary>展开查看全部代谢组技能</summary>

| 技能 | 说明 | 主要方法 |
|-------|-------------|-------------|
| `metabolomics-peak-detection` | 峰检测与峰形过滤 | `scipy.signal.find_peaks`, peak widths |
| `metabolomics-xcms-preprocessing` | LC-MS / GC-MS 峰提取、对齐和特征分组 | XCMS centWave (Python simulation) |
| `metabolomics-normalization` | 归一化与尺度变换 | Median, Quantile, TIC, PQN, Log2 |
| `metabolomics-annotation` | 代谢物注释与多加合物支持 | HMDB m/z matching, adduct support |
| `metabolomics-quantification` | 特征定量、缺失值填补与归一化 | Min/2, median, KNN imputation, TIC / median / log norm |
| `metabolomics-statistics` | 单变量统计与 FDR 校正 | Welch's t-test, Wilcoxon, ANOVA, Kruskal-Wallis + BH FDR |
| `metabolomics-de` | 差异代谢物分析与 PCA 可视化 | Welch's t-test + BH FDR, PCA |
| `metabolomics-pathway-enrichment` | 通路富集分析 | Hypergeometric test, KEGG pathways, BH FDR |

</details>

### Bulk RNA-seq（13 个技能）

- **上游质控**：`bulkrna-read-qc`
- **比对**：`bulkrna-read-alignment`
- **计数矩阵质控**：`bulkrna-qc`
- **预处理**：`bulkrna-geneid-mapping`、`bulkrna-batch-correction`
- **分析技能**：`bulkrna-de`、`bulkrna-splicing`、`bulkrna-enrichment`、`bulkrna-survival`
- **高级分析**：`bulkrna-deconvolution`、`bulkrna-coexpression`、`bulkrna-ppi-network`、`bulkrna-trajblend`

<details>
<summary>展开查看全部 Bulk RNA-seq 技能</summary>

| 技能 | 说明 | 主要方法 |
|-------|-------------|-------------|
| `bulkrna-read-qc` | FASTQ 质控 | FastQC-style Python implementation |
| `bulkrna-read-alignment` | RNA-seq 比对统计 | STAR/HISAT2/Salmon log parsing |
| `bulkrna-qc` | 计数矩阵质控 | pandas, matplotlib, MAD outlier detection |
| `bulkrna-geneid-mapping` | Gene ID 转换 | mygene, built-in tables |
| `bulkrna-batch-correction` | 批次效应校正 | Empirical Bayes, PCA assessment |
| `bulkrna-de` | 差异表达分析 | PyDESeq2, t-test fallback |
| `bulkrna-splicing` | 可变剪接分析 | rMATS/SUPPA2 parsing, delta-PSI |
| `bulkrna-enrichment` | 通路富集 | GSEApy, hypergeometric fallback |
| `bulkrna-deconvolution` | Bulk 数据细胞成分解卷积 | NNLS, CIBERSORTx bridge |
| `bulkrna-coexpression` | WGCNA 风格共表达网络 | Soft thresholding, hierarchical clustering, TOM |
| `bulkrna-ppi-network` | PPI 网络分析 | STRING API, graph centrality, hub genes |
| `bulkrna-survival` | 生存分析 | Kaplan-Meier, log-rank test, Cox PH |
| `bulkrna-trajblend` | Bulk 到单细胞轨迹插值 | NNLS, PCA + KNN mapping, pseudotime |

</details>

### Orchestrator（2 个技能）

- `orchestrator`：将请求路由到合适技能，并组织多步流水线
- `omics-skill-builder`：自动生成可复用的 OmicsClaw 技能脚手架

### Literature（1 个技能）

- `literature`：解析 PDF、URL、DOI 等文献来源，提取 GEO 编号和相关数据集信息

<details>
<summary>展开查看 Literature 技能</summary>

| 技能 | 说明 | 主要方法 |
|-------|-------------|-------------|
| `literature` | 解析科研论文中的数据集与元数据 | GEOparse, pypdf |

</details>

## 架构概览

<details>
<summary>展开查看项目结构与技能布局</summary>

OmicsClaw 使用按领域组织的模块化结构：

```text
OmicsClaw/
├── omicsclaw.py              # 主 CLI 入口
├── omicsclaw/                # 与领域无关的核心框架
│   ├── core/                 # 注册中心、技能发现、依赖管理
│   ├── routing/              # 查询路由与编排逻辑
│   ├── loaders/              # 文件格式 / 领域识别
│   ├── common/               # 公共工具（报告、校验等）
│   ├── memory/               # 图结构记忆系统
│   ├── interactive/          # 交互式 CLI / TUI
│   ├── agents/               # Agent 定义
│   ├── knowledge/            # 知识加载辅助模块
│   └── r_scripts/            # 共用 R 侧辅助脚本
├── skills/                   # 自包含分析模块
│   ├── spatial/              # 16 个空间转录组技能 + _lib
│   ├── singlecell/           # 14 个单细胞技能 + _lib
│   ├── genomics/             # 10 个基因组技能 + _lib
│   ├── proteomics/           # 8 个蛋白组技能 + _lib
│   ├── metabolomics/         # 8 个代谢组技能 + _lib
│   ├── bulkrna/              # 13 个 Bulk RNA-seq 技能 + _lib
│   └── orchestrator/         # 跨领域编排
├── knowledge_base/           # 规则、指南和可复用知识
├── bot/                      # 多通道消息接口
├── frontend/                 # Memory Explorer React/Vite 前端
├── website/                  # 官方文档站点
├── docs/                     # 文档（安装、方法、架构等）
├── examples/                 # 示例数据
├── scripts/                  # 工具脚本
├── templates/                # 输出模板
├── tests/                    # 集成与回归测试
├── sessions/                 # 会话状态存储
├── Makefile                  # 构建与快捷命令
└── 0_setup_env.sh            # 一键环境安装（mamba + pip + R + 外部工具）
```

**每个技能都是自包含的：**

```text
skills/<domain>/<skill>/
├── SKILL.md                  # 方法说明与接口约定
├── <skill_script>.py         # CLI 实现
└── tests/                    # 单元 / 集成测试
```

技能之间通过标准格式（如 `.h5ad`、`.vcf`、`.mzML`、`.csv`）进行衔接，也可以组合成流水线。

</details>

## 📱 消息通道集成

OmicsClaw 提供带持久记忆的消息 Bot 接口，可让 CLI 和消息平台共享同一套会话状态。目前支持 Telegram、飞书（Lark）、钉钉、Discord、Slack、微信、QQ、Email 和 iMessage。

```bash
# 安装 Bot 基础依赖
pip install -r bot/requirements.txt

# 或安装全部通道依赖
pip install -r bot/requirements-channels.txt

# 准备配置
cp .env.example .env

# 同时启动多个通道
python -m bot.run --channels telegram,feishu,slack

# 或使用 Makefile
make bot-multi CHANNELS=telegram,discord
```

**主要特点：**

- 🧠 **持久记忆**：跨会话记住数据、分析记录和偏好
- 💬 **自然语言交互**：例如“继续做空间结构域识别”，系统会自动选择合适技能
- 📁 **多组学文件支持**：支持 `.h5ad`、`.vcf`、`.mzML`、`.csv`、`.tsv`
- 📊 **结果自动回传**：报告和图表可直接发送到聊天窗口
- 🔒 **本地优先**：计算在本地执行，仅保存必要元数据

> [!TIP]
> 通道配置、能力矩阵和架构说明请参见 [bot/README.md](bot/README.md)。
> 记忆系统相关说明请参见 [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)。

## 🤖 给 AI Agent 的说明

**如果你是一个正在读取此仓库的 AI Agent（例如 OpenClaw、Claude Desktop、Cursor、OpenDevin 或本地 CLI Agent）：**

用户依赖 OmicsClaw 提供的统一技能体系来完成多组学分析。**不要临时拼接零散的 ad-hoc Python 脚本**。优先使用 OmicsClaw 已有的标准化工具和图结构记忆系统。

在采取任何操作前，请先阅读以下文件：

- 📜 [`llms.txt`](llms.txt)：项目结构和提示边界的高层说明
- 🧠 [`AGENTS.md`](AGENTS.md)：`oc` CLI 用法和记忆系统说明
- 🤖 [`CLAUDE.md`](CLAUDE.md)：定制化 Agent 指令和内部编排约束
- 🧩 [`skills/catalog.json`](skills/catalog.json)：全部 72 个技能的机器可读注册表

建议主动告知用户：

> “我会优先使用 OmicsClaw 内置的技能注册表和记忆系统来完成任务，以保证执行的稳定性和一致性。”

## 👥 团队

| 角色 | 姓名 | 联系方式 |
|------|------|---------|
| 负责人（PI） | **Luyi Tian** | [tian_luyi@gzlab.ac.cn](mailto:tian_luyi@gzlab.ac.cn) |
| 主导开发者 | **Weige Zhou** | [GitHub](https://github.com/zhou-1314) |
| 开发者 | **Liying Chen** | [GitHub](https://github.com/chenly255) |
| 开发者 | **Pengfei Yin** | [GitHub](https://github.com/astudentfromsustech) |

问题反馈和功能建议请通过 [GitHub Issues](https://github.com/TianGzlab/OmicsClaw/issues) 提交。

## 🤝 贡献

欢迎生物信息学研究者、计算生物学家以及 AI 开发者参与贡献。如果要添加一个新技能，可以按下面的步骤进行：

1. 新建技能目录：`skills/<domain>/<skill-name>/`
2. 添加 `SKILL.md`，写明方法说明和接口约定
3. 实现 `<skill_name>.py` 的 CLI 接口
4. 在 `tests/` 中补充测试
5. 运行 `python scripts/generate_catalog.py` 更新注册表

详细开发规范请参见 [AGENTS.md](AGENTS.md)。

### 🌐 社区

欢迎加入 OmicsClaw 用户社区，分享分析经验、反馈问题，一起推动多组学 AI 分析工具的发展。

<table>
  <tr>
    <td align="center" width="30%">
      <img src="docs/images/IMG_3729.JPG" alt="OmicsClaw 微信交流群" width="180"/>
      <br/>
      <b>微信交流群</b>
      <br/>
      <sub>扫码加入体验交流</sub>
    </td>
    <td valign="middle" width="70%">
      <ul>
        <li>
          <b>🐛 <a href="https://github.com/TianGzlab/OmicsClaw/issues">问题反馈与功能建议 (Issues)</a></b>
          <br/>遇到 Bug 或有新的需求？点击提交 Issue，帮助我们不断改进。
        </li>
        <br/>
        <li>
          <b>💡 <a href="https://github.com/TianGzlab/OmicsClaw/discussions">交流与工作流分享 (Discussions)</a></b>
          <br/>加入讨论板块，分享您的分析技巧、使用心得以及科研见解。
        </li>
      </ul>
    </td>
  </tr>
</table>

## 📚 致谢

OmicsClaw 的设计和实现受到了以下开源项目的重要启发：

- **[ClawBio](https://github.com/ClawBio/ClawBio)**：生物信息学场景下较早的原生 AI agent 技能库之一。OmicsClaw 的技能架构、本地优先理念、可复现性设计和 Bot 集成模式都受到了它的启发。
- **[Nocturne Memory](https://github.com/Dataojitori/nocturne_memory)**：一个轻量、支持回溯的长时记忆服务。OmicsClaw 的持久记忆系统借鉴了其图结构记忆和 MCP 集成思路。

## 📖 文档

- [docs/INSTALLATION.md](docs/INSTALLATION.md)：安装说明和依赖层级
- [docs/METHODS.md](docs/METHODS.md)：算法参考与参数说明
- [docs/architecture.md](docs/architecture.md)：系统设计与实现模式
- [CLAUDE.md](CLAUDE.md)：AI Agent 路由说明
- [bot/README.md](bot/README.md)：Bot 配置与运行说明

## ⚠️ 安全与免责声明

- **本地优先处理**：数据默认保留在本机
- **仅供科研使用**：本项目不是医疗器械，不提供临床诊断结论
- **请由领域专家复核**：重要结论应结合专业判断进行确认

## 📜 许可证

Apache-2.0，详见 [LICENSE](LICENSE)。

## 📝 引用

如果你在研究中使用了 OmicsClaw，欢迎引用：

```bibtex
@software{omicsclaw2026,
  title = {OmicsClaw: A Memory-Enabled AI Agent for Multi-Omics Analysis},
  author = {Zhou, Weige and Chen, Liying and Yin, Pengfei and Tian, Luyi},
  year = {2026},
  url = {https://github.com/TianGzlab/OmicsClaw}
}
```
