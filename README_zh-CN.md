<div align="center">
  <img src="docs/images/OmicsClaw_logo.jpeg" alt="OmicsClaw Logo" width="400"/>

  <h3>🧬 OmicsClaw</h3>
  <p><strong>您的多组学分析持久化 AI 研究伙伴</strong></p>
  <p>记住您的数据 • 学习您的偏好 • 恢复您的工作流</p>
  <p><em>对话式驱动 • 记忆增强 • 本地优先 • 跨平台</em></p>
</div>

# OmicsClaw

> **有记忆的 AI 科研助手。** OmicsClaw 将繁杂的多组学分析从重复性的命令行敲击，转变为与一个持久化伙伴的自然语言对话——它能追踪您的数据集、学习您的分析方法，并在不同会话中无缝恢复被打断的工作流。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/TianGzlab/OmicsClaw/actions)
[![Website](https://img.shields.io/badge/Website-Live-brightgreen.svg)](https://TianGzlab.github.io/OmicsClaw/)

> [!NOTE]
> **🚀 v0.1.0 正式版发布 / Official v0.1.0 Release**
> 
> 经过充分的开发与严格测试，OmicsClaw v0.1.0 现已正式发布！在这一里程碑大版本中，我们提升了交互式自然语言分析的体验，并引入了直观的原生记忆管理面板（Memory Explorer），提供了覆盖 6 个组学领域的 72 个内置原生技能。欢迎下载体验，任何问题与建议请通过 [GitHub Issues](https://github.com/TianGzlab/OmicsClaw/issues) 提交。期待您的反馈！
> 
> [English](README.md) | [中文版](README_zh-CN.md)

<h3>⚡ 统一的中枢内核，跨平台的交互展现</h3>

<table>
  <tr>
    <th width="75%"><p align="center">🖥️ 桌面端：CLI / TUI</p></th>
    <th width="25%"><p align="center">📱 移动端：飞书 / Telegram</p></th>
  </tr>
  <tr>
    <td align="center">
      <video src="https://github.com/user-attachments/assets/a24b16b8-dc72-439a-8fcd-d0c0623a4c8a" autoplay loop muted playsinline width="100%">
        <a href="https://github.com/user-attachments/assets/a24b16b8-dc72-439a-8fcd-d0c0623a4c8a">查看 CLI 交互演示</a>
      </video>
    </td>
    <td align="center">
      <video src="https://github.com/user-attachments/assets/0ccb21f8-6aa9-45ec-b50d-44146566e64e" width="100%" autoplay loop muted playsinline>
        <a href="https://github.com/user-attachments/assets/0ccb21f8-6aa9-45ec-b50d-44146566e64e">查看移动端交互演示</a>
      </video>
    </td>
  </tr>
</table>

## 🤔 为什么选择 OmicsClaw？

**传统工具总是让人重复劳动。** 每次对话都要从零开始：重新上传数据、重新排查上下文、重新运行基础的预处理。但 OmicsClaw 是有记忆的。

## ✨ 核心特性
- **🧠 持久化记忆** — 上下文、偏好设定和完整的分析历史记录会在不同会话间持久留存。
- **🛠️ 极强扩展性 (MCP & 技能脚手架)** — 原生集成并支持各种 Model Context Protocol (MCP) 服务器，内置 `omics-skill-builder` 实现任意自定义分析的自动封装。
- **🌐 多模型后端配置** — 支持 Anthropic、OpenAI、DeepSeek 或完全本地的开源大模型 —— 仅需修改一行配置即可随意切换。
- **📱 全渠道能力** — 以 CLI 为调度中枢；同时原生支持无缝接入 Telegram、飞书 (Feishu) 等通讯软件 —— 一处数据，多端共享 Agent。
- **🔄 工作流连贯性** — 随时恢复被迫中断的分析进程，追踪溯源数据血缘，避免极其浪费时间的重复计算。
- **🔒 隐私与合规优先** — 所有的核心计算均在您的本地环境运行；记忆图谱仅存储分析元数据（绝不会上传原始敏感数据）。
- **🎯 智能路由转发** — 能够将自然语言意图精准、自动投递匹配到最合适的底层分析代码流。
- **🧬 全组学技能覆盖** — 跨空间转录组、单细胞测序、基因组、蛋白质组、代谢组、Bulk RNA-seq 等内置了 72 项即插即用的原生计算技能。

**与传统工具的核心差异：**

| 传统计算工具 | OmicsClaw |
|-------------------|-----------|
| 每次会话都需要重新声明文件路径 | 智能记住文件挂载路径及实验元数据 |
| 无法溯源之前的历史流 | 追踪完整的数据血缘链 (预处理 → 聚类 → 差异表达) |
| 手动一遍遍敲击重复参数 | 自动学习并应用您心仪的参数偏好 |
| 仅限代码终端，上手门槛极大 | 交互式自然语言聊天面板 + 核心 CLI 支撑 |
| 无记忆的单次冷启动执行 | 长久陪伴的持久化科研伙伴 |

> 📖 **深度解析:** 查看 [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) 获取带记忆的智能体与无状态工作流之间的详细技术对比。

## 📦 安装指南

为了防止潜在的 Python 依赖冲突，我们强烈建议您先挂载一个专门的虚拟环境。您可以使用标准的 `venv` 或极速版 `uv` 构建。

<details open>
<summary> 🪛 搭建虚拟运行环境 (强烈推荐)</summary>

**选项 A: 使用标准 venv**
```bash
# 1. 新建虚拟环境
python3 -m venv .venv

# 2. 激活虚拟环境
source .venv/bin/activate
```

**选项 B: 使用 uv (极速部署)**
```bash
# 1. 安装 uv (若尚未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 新建并激活虚拟环境
uv venv
source .venv/bin/activate
```

</details>

```bash
# 拉取系统源码
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw

# 安装核心系统底层依赖
pip install -e .

# 可选建议: 安装交互式 TUI 及 Bot 通讯组件
# 该过程会包含 prompt-toolkit/Textual 以及负责语言模型调用的 client 环境
pip install -e ".[tui]"
pip install -r bot/requirements.txt  # 若需接入飞书、电报等平台
```

**高阶分层安装选项：**
- `pip install -e .` — 仅安装系统骨架
- `pip install -e ".[<domain>]"` — 其中 `<domain>` 可以是 `spatial` (空间组), `singlecell` (单细胞), `genomics` (基因组), `proteomics` (蛋白质), `metabolomics` (代谢), 或 `bulkrna` (普通转录组)
- `pip install -e ".[spatial-domains]"` — 专用于运行 `SpaGCN` 和 `STAGATE` 等的深度学习拓展包
- `pip install -e ".[full]"` — 一键安装全领域所需的所有核心后端支持包

*您可以随时执行 `python omicsclaw.py env` 检查您目前的模块安装状态。*

## 🔑 参数配置

**最简单的方法（交互式向导）：**
OmicsClaw 提供了一个内置的友好交互向导，该向导能安全、自动地一步步引导您完成 LLM 接口、运行时偏好以及记忆引擎的配置归档。
```bash
omicsclaw onboard  # 或使用短别令: oc onboard
```

向导最终会自动将配置稳妥写入到项目根目录下的 `.env` 文件内。

<div align="center">
  <img src="docs/images/OmicsClaw_configure_fast.png" alt="OmicsClaw 交互式搭建向导" width="85%"/>
</div>

<details>
<summary><b>选项 B: 手动配置文件 (.env)</b></summary>

OmicsClaw 支持一键切换底层驱动的大语言模型。项目中的命令行(CLI)、UI(TUI)、智能体路由与群聊 Bot 入口均会统一强制读取根目录的 `.env` 文件。

对于云端托管模型服务商，你可以二选一：
- 统一配置 `LLM_API_KEY`
- 针对该厂商专用配置对应后缀（如 `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, 或 `ANTHROPIC_API_KEY`）

**1. DeepSeek (默认推荐):**
```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**2. Anthropic (Claude):**
```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# 代码会自动嗅探该键值并默认调用 claude-3-5-sonnet
```

**3. OpenAI (GPT-4o 等):**
```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**4. 本地大模型 (Ollama):**
如果您有极高的临床数据合规和隐私要求，可以通过 Ollama 运行完全本地的模型（无需 API 密钥）：
```env
LLM_PROVIDER=ollama
OMICSCLAW_MODEL=qwen2.5:7b  # 替换为您本地已 pull 的模型名
LLM_BASE_URL=http://localhost:11434/v1
```

**5. 第三方中转分发与自定义节点:**
```env
LLM_PROVIDER=custom
LLM_BASE_URL=https://您的转发节点.example.com/v1
OMICSCLAW_MODEL=填入对应的模型名
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
```

> 📖 **完整服务支持列表:** 关于配置 NVIDIA NIM, OpenRouter, 或是 DashScope(通义千问) 等第三方引擎的具体范例，请参阅 `.env.example`。
>
> 📖 **Bot 通讯软体配置:** 关于配置微信、飞书、钉钉、Discord凭证的信息与运行时管理指南参考 [bot/README.md](bot/README.md) 及 [bot/CHANNELS_SETUP.md](bot/CHANNELS_SETUP.md)。

</details>

## ⚡ 快速开始

### 1. 聊天终端交互 (官方钦定用法)

```bash
# 调出交互式聊天操作面板
omicsclaw interactive  # 或别令: oc interactive
omicsclaw tui          # 唤出全屏 TUI: oc tui

# 或者也可以将此终端作为守护后端，启动多渠道通讯代理
python -m bot.run --channels feishu,telegram
```

> 📖 **Bot 网关进阶配置:** 有关启动不同即时通讯平台的信息详情，请移步 [bot/README.md](bot/README.md)。

**用大白话和您的数据交流:**
```
用户: "帮预处理一下我传的这批 Visium 数据"
Bot: ✅ [默默运行 QC, normalization 归一化, 聚类]
     💾 [生成记忆节点: visium_sample.h5ad, 包含5000个 spot, 状态已归一化]

[过了一天]
用户: "找一下它们内部的空间结构域分区"
Bot: 🧠 "检测到您昨天预处理过的 Visium 数据（5000 spots, 状态已归一化）。
     马上开始对该数据执行识别任务..."
```

<details>
<summary>会话内可用的高阶指令 (Interactive CLI/TUI)</summary>

| 指令 | 目的与描述 |
| ------- | ----------- |
| **分析与调度** | |
| `/run <skill> [...]` | 直接拉起某项底层代码技能运行 (例如 `/run spatial-domains --demo`) |
| `/skills [domain]` | 检索并列出支持的所有组学分析技能代码 |
| `/install-skill` | 从本地路经或者 GitHub 热插拔安装属于您自己的扩展包 |
| **会话与记忆管理** | |
| `/sessions` | 展示过往存续过的最近所有会话分析流 |
| `/resume [id/tag]` | 在之前中断的地方原封不动地切入、热恢复旧的分析任务 |
| `/new` / `/clear` | 新开干净的分支逻辑，或一键清除历史对话记忆树 |
| `/memory` | 语义记忆数据库管理以及核心元数据持久化追踪 |
| `/export` | 把当前的分析成果打包导出一份带格式的高阶 Markdown 数据图表报告 |
| **环境与系统设定** | |
| `/mcp` | Model Context Protocol 管理专区 (`/mcp list/add/remove`) |
| `/config` | 热切修改当前分析引擎及底层使用的大模型架构 |
| `/doctor` / `/usage` | 跑测试执行诊断排障；或清算、展示当前模型交互所耗费的 API Token 账单与开销 |
| `/exit` | 优雅退出 OmicsClaw 终端 |

</details>

<details>
<summary>通讯机器人支持指令 (Telegram / 飞书 等)</summary>

| 指令 | 目的与描述 |
| ------- | ----------- |
| `/start` / `/help`| 载入欢迎致辞，查阅使用守则、功能介绍及帮助文档 |
| `/skills` | 列表检索多组学技能注册字典 |
| `/demo <skill>` | 强制让 Agent 使用内嵌的测试用例进行对应技能演算流程供观察 |
| `/new` / `/clear` | 另起干净的聊天环境 (不影响以往的全局记忆节点) |
| `/forget` | 绝情模式，彻底重置一切，包含清洗并摧毁整个当前用户产生的聊天流与知识记忆图谱 |
| `/files` / `/outputs`| 返回该账户过往上传的数据资产和近期生成的图像分析图表 |
| `/recent` | 列显最近刚跑通的 3 场计算任务概况 |
| `/status` / `/health`| 测试健康诊断，打印当前挂载的通讯通道、调用源和守护运行开销 |

</details>

### 2. 传统命令行交互

```bash
# 直接调出 demo 测试
python omicsclaw.py run spatial-preprocess --demo

# 或带入真实属于您个人的参数文件
python omicsclaw.py run spatial-preprocess --input data.h5ad --output results/
```

> 📚 **详尽技术文档:** [INSTALLATION.md](docs/INSTALLATION.md) • [METHODS.md](docs/METHODS.md) • [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)

## 脑图记忆系统 — 核心差异化壁垒

OmicsClaw 与市面上流水线工具的本质区别在于其内部深植的记忆系统结构。这让它真正脱胎成为您案头持久化陪伴的研究伙伴。全新上线的 **Memory Explorer** 提供全屏幕的 Web 图形化视觉中心，便于您直观地可视化检索、审查您毕生项目的研究足迹与所有数据沿革谱系。

<div align="center">
  <img src="docs/images/memory_system.png" alt="Memory System Explorer Frontend Interface" width="100%"/>
  <br>
  <em>Memory Explorer 面板: 专为您量身打造的一个统一的看板，便于数据追溯验证，把控庞大研究网络</em>
</div>

**如何启动 Memory Explorer 看板:**
```bash
# 第一步: 在主终端热启动挂载底层 Memory API 服务
oc memory-server

# 第二步: 新开第二个终端并切换至前端目录跑起控制面板
cd frontend && npm install && npm run dev
```

现在该记忆服务的 API 将默认坚守绑定于 `127.0.0.1:8766`。如果您具有特殊的远程网关暴露需求，需同时规范设置 `OMICSCLAW_MEMORY_HOST` 及验证秘钥 `OMICSCLAW_MEMORY_API_TOKEN` 。

**底层会持久化记忆的事务包括:**
- 📁 **数据集资源** — 挂载路径的演变、使用的实验仪器平台 (如 Visium/Xenium)与数据宏微观多维特性
- 📊 **干预分析流** — 层层推近应用过的方法，下达的数值参数、算力运行时常以及详尽的血统追踪 (父节点衍生出何电子节点)
- ⚙️ **用户专属习惯** — 了解您的癖好：比如更偏爱什么样的聚类策略算法、喜欢哪种风格维度的颜色图表和实验物种预设等
- 🧬 **生物学洞察标注** — 深层认知提点 (比如该 cluster 是指代 "T cells"，该空间 domain 聚类囊括了 "肿瘤发生前沿边界")
- 🔬 **课题工程上下文** — 铭记项目的攻坚靶点，包括正在分析的物种、组织亚型以及病理模型背景

> 📖 **详尽的内核全解技术白皮书:** 请阅读 [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) — 包含各种极其典型的实战案例详解，以及底层的隐私隔绝和深层链路架构剖析。

## 🔌 极强扩展性：原生 MCP 整合与技能脚手架发生器

针对那些需求远超基础工具的高净值生信分析师群体和复杂前沿的 Agent 重型流派，OmicsClaw 从底层设计之初即贯彻了极高灵活的互操作性：

- **原生的 Model Context Protocol (MCP) 接入**： 您可以通过 `/mcp` 指令热插拔般地安全将任何遵循标准化 MCP 扩展协议的服务器直插挂载进 OmicsClaw 内心。这让您的聊天伴侣在眨眼间就具有调用任何外部计算 API 池集、遍历外挂全球医学数据库，或者无缝访问大型三方企业数据仓的能力。
- **`omics-skill-builder`**： 这是一把内置存放于 `skills/orchestrator/` 下方的，旨在疯狂放大数据交互处理能力的战略大杀器。当面临完全未知的全新组学科研需求时，您再也无需人工苦哈哈地敲击那些繁杂累赘的基础控制样板代码；`omics-skill-builder` 会仅仅依据一条包含对话意图或者短短几行 Python 高阶分析逻辑的面条代码，在零秒内自动化编织为您包裹、组装并吐出标准且完全可复用的全体 OmicsClaw 技能脚手架模块组 (囊括了一座新代码山所需的所有 Python wrapper 包装器、精细刻画的 SKILL.md 定义文稿以及相关系统注册登记表)。

## 涵盖的主流分析组学领域

| 分析领域分类 | 下设原装技能总数 | 核心支撑能效与关键场景覆盖 |
|--------|--------|------------------|
| **Spatial Transcriptomics (空间转录组)** | 16 | QC质控、病理聚类、精确到细胞级别的解卷积、空间自相关性统计学测定、通讯轨迹、细胞速度场、病灶微环境圈选提取 |
| **Single-Cell Omics (单细胞组)** | 14 | 常规过滤、双细胞鉴别剔除除噪、深度标注、降维轨迹推断、超巨量数据的批次效应融合抹除、GRN 转录因果推断、scATAC 处理链 |
| **Genomics (基因组学)** | 10 | SNP/INDEL 变异定位解析、读取比对、氨基酸深层影响标记及致病性打分注释、染色体级别的超长序列重测序全变异、CNV 计算 |
| **Proteomics (蛋白组学)** | 8 | 各式质谱的底层开放化转切引擎、肽段识别量化、差异丰度验证、复杂的共翻译折后修饰研究（PTM）、网络拓扑验证 |
| **Metabolomics (代谢组学)** | 8 | 针对代谢峰值的甄别寻找去重、对齐、特征补位聚合，多核查证、多手段归一化校正引擎以及高水准可视化统计量化网络 |
| **Bulk RNA-seq (经典转录本测序)** | 13 | 从 FASTQ 起源开始的大量测序质控分析报告生成、计数统计与表达量关联、批次批平、超复杂的剪接网络和生存存活演化分析、与单细胞的数据整合映射 |
| **Orchestrator (系统调度总线)** | 2 | 分发智能识别的组学跨域请求调度处理中枢、高级自定义代码快速生产组装挂载线 |
| **Literature (前沿文献挖掘检索)** | 1 | 对外接文献 PDF 等介质材料进行的智能化深度解构抓取，用于探明隐藏 GEO/样本信息以便进一步一键自动调用接口抓走后续数据体系 |

**底层兼容实战文件谱系包括但不局限于:** Visium, Xenium, MERFISH, Slide-seq, 10x 单细胞标准系, 全 Illumina 或者 PacBio 机器数据线, LC-MS/MS 实验结果表格, 各类传统 Bulk RNA-seq 的 CSV/TSV 等

> 📋 **完整底层支持包白皮书:** 继续向下滑动可查看具体的 [分领域全组学技能详细目录说明](#涵盖的主流分析组学领域) 以及底层的关键算法映射。

## 技能模块全览 (Skills Overview)

### 空间转录组学 - Spatial Transcriptomics (16 个核心技能)

- **基础篇:** `spatial-preprocess` — 质控 (QC), 归一化, 降维聚类, UMAP
- **病理切片分析:** `spatial-domains`, `spatial-annotate`, `spatial-deconv`, `spatial-statistics`, `spatial-genes`, `spatial-de`, `spatial-condition`, `spatial-microenvironment-subset`
- **高阶探索:** `spatial-communication`, `spatial-velocity`, `spatial-trajectory`, `spatial-enrichment`, `spatial-cnv`
- **切片对齐融合:** `spatial-integrate`, `spatial-register`
- **中枢挂载:** 可指派顶层 `orchestrator` 进行跨域组学互联或流水线搭建

<details>
<summary>展开查看所有空间组学技能</summary>

| 技能指令 | 能力描述 | 依赖的核心底层方法 |
|-------|-------------|-------------|
| `spatial-preprocess` | 质控、归一化、高变基因(HVG)、PCA、UMAP、聚类提取 | Scanpy |
| `spatial-domains` | 组织拓扑微区/切片微环境边界识别 | Leiden, Louvain, SpaGCN, STAGATE, GraphST, BANKSY, CellCharter |
| `spatial-annotate` | 自动化细胞注释引擎 | 基于 Marker (Scanpy), Tangram, scANVI, CellAssign |
| `spatial-deconv` | 将低分辨率 Spot 按细胞比例解卷积 | FlashDeconv, Cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD |
| `spatial-statistics` | 空间自相关性测试及拓扑网络网络量化 | 莫兰指数 Moran's I, Geary's C, Getis-Ord Gi*, Ripley's L, 共现性矩阵, 连通图中心性计算 |
| `spatial-genes` | 寻找带有显著空间拓扑异质表达特征的基因 | Moran's I, SpatialDE, SPARK-X, FlashS |
| `spatial-de` | 提取组间显著差异表达矩阵 | Wilcoxon, t-test, PyDESeq2 |
| `spatial-condition` | 多病理对照组横向大差异化比对 | 伪 Bulk化处理下的 DESeq2 |
| `spatial-microenvironment-subset`| 在巨型全片中精准抠取一个特定细胞的微空间邻域集合作 | KDTree 几何网树, Scanpy |
| `spatial-communication` | 基于受体-配体原理的细胞间微通讯空间推断 | LIANA+, CellPhoneDB, FastCCC, CellChat |
| `spatial-velocity` | 从静态切片推断瞬态 RNA 剪接动力学及演化速率 | scVelo, VELOVI 动态场构建 |
| `spatial-trajectory` | 基于切片坐标与伪时间推算构建的发育成熟轨迹分化树 | CellRank, Palantir, DPT |
| `spatial-enrichment` | 在空间水平描绘富集生物学通路 | GSEA, ssGSEA, Enrichr 数据库 |
| `spatial-cnv` | 推断肿瘤切片上的拷贝数显著变异位点 | inferCNVpy, Numbat |
| `spatial-integrate` | 消除多批次同组织样本效应强行融合对齐降维池 | Harmony, BBKNN, Scanorama |
| `spatial-register` | 强制物理空间镜像配准 | PASTE 最佳传输匹配, STalign |
</details>

### 单细胞组学 - Single-Cell Omics (14个核心技能)

- **基础管线:** `sc-qc`, `sc-filter`, `sc-preprocessing`, `sc-ambient-removal`, `sc-doublet-detection`
- **深层定性:** `sc-cell-annotation`, `sc-de`, `sc-markers`
- **精进深掘:** `sc-pseudotime`, `sc-velocity`, `sc-grn`, `sc-cell-communication`
- **消除融合:** `sc-batch-integration`
- **scATAC 表观数据:** `scatac-preprocessing`

<details>
<summary>展开查看全部单细胞技能</summary>

| 技能指令 | 能力描述 | 依赖的核心底层方法 |
|-------|-------------|-------------|
| `sc-qc` | 并行计算与图解化各类基础质控项 | Scanpy 本源 QC 测试指标体系 |
| `sc-filter` | 全自动依照阈值暴力剔除劣质胞和基因 | 规则门限逻辑筛选引擎 |
| `sc-preprocessing` | 归一化、HVG提取、PCA降阶、流形嵌顿到二维UMAP图表 | Scanpy, Seurat, SCTransform |
| `sc-ambient-removal` | 去除极容易引起假阳性的环境游离背景RNA分子干扰 | CellBender, SoupX, 极简阈值过滤 |
| `sc-doublet-detection` | 甄别并去除两个细胞包裹进同一个油滴的双胞胎干扰源 | Scrublet, DoubletFinder, scDblFinder |
| `sc-cell-annotation` | 从各种主流图谱中学习识别海量亚群类型的注释标签 | 本地 markers, CellTypist 概率预测, SingleR |
| `sc-de` | 获取差异最显著的高光基因榜单矩阵 | Wilcoxon, t-test, DESeq2 pseudobulk |
| `sc-markers` | 构建专属该细胞簇型的特异性表征 Marker 生物库 | Wilcoxon, t-test, 逻辑回归筛选法 |
| `sc-pseudotime` | 无端逆推算拟动态时间的发育分支及轨迹连线图谱 | PAGA 抽象全局流, DPT |
| `sc-velocity` | RNA瞬时剪接速度场模型构建 | scVelo 随机模拟推导 |
| `sc-grn` | 反向建立基于转录阻遏控制元件的级联基因调控大网络(GRN) | pySCENIC (基于随机森林与模体库) |
| `sc-cell-communication` | 重建基于受配体强绑定的细胞交互强度与作用力热图 | 基础矩阵配对, LIANA 合集, CellChat 解析库 |
| `sc-batch-integration` | 抹平并连接强行合并多个非同一测序批次产生的数据巨海 | Harmony, scVI 深度生成网, BBKNN 树形融合, Scanorama, fastMNN, Seurat CCA/RPCA |
| `scatac-preprocessing` | 专项针对 scATAC-seq 开放染色质峰的数据集聚与梳理 | TF-IDF, LSI降维, UMAP可触化展现, Leiden |

</details>

### 后续各基因组差异基因计算及代谢底座等详见下方核心词汇支持表

*(为了确保指令精准对应终端后端引擎触发代码规范，接下来的细分领域分析模块表单不做中文的破坏性指令修改)*

<details>
<summary>Genomics 基因组解析 (10 技能)</summary>

*同原 README.md 文档对应一致，略*
</details>

<details>
<summary>Proteomics 蛋白质计算工程 (8 技能)</summary>

*同原 README.md 文档对应一致，略*
</details>

<details>
<summary>Metabolomics 代谢图谱构建 (8 技能)</summary>

*同原 README.md 文档对应一致，略*
</details>

<details>
<summary>Bulk RNA-seq 转录组及测序建库 (13 技能)</summary>

*同原 README.md 文档对应一致，略*
</details>

### 编排器模块 - Orchestrator (2 核心挂载)

- `orchestrator` — 作为顶层建筑，路由与分发生物学多步复合查询语句，能够执行串联整条数据流水线。
- `omics-skill-builder` — 从零自动无痛为您撰写创造完全可重复分发利用的 OmicsClaw 新技能代码群。

### 前沿文献情报模块 - Literature Mining (1 项重磅工具)

- **定向解构榨取:** `literature` — 给它投喂顶级科研期刊、PDF、网络链接甚至仅仅是 DOI，它会暴力解构学术内容，自动挖掘探明藏在里面的补充数据连接和 GEO 数据仓储号，直接一键帮您从源头全本端回数据！

## 坚实可靠的底层架构

<details>
<summary>展开查看超解耦的松散耦合设计与包模块图</summary>

OmicsClaw 从骨子里采用了一种极强拓展性的模块领域化结构引擎设计：

```
OmicsClaw/
├── omicsclaw.py              # 主体全场命令行挂载点入口
├── omicsclaw/                # 脱离于具体特定组学的顶层控制包
│   ├── core/                 # 注册中心，技能嗅探探测网，依赖模块管理器
│   ├── routing/              # 解析自然查询并分发到最合适技能脚本的网关
│   ├── loaders/              # 底层后缀格式适配判定推测类
│   ├── common/               # UI绘制、报告回写、哈希鉴别工具函数
│   ├── memory/               # 本系统最核心最强力的 Graph 记忆树中枢大模型实体
│   ├── interactive/          # CLI 与全包含式 TUI 交互显示类库
│   ├── agents/               # 各类型大语言多模态 Agent 调度派工定义
│   ├── knowledge/            # 持久化生信研究知识的加载引导区
│   └── r_scripts/            # 承袭外部 R 庞大生态底座语言的跨语言交互桥梁
├── skills/                   # 即插即用、开箱即食的各种独立重算力分析插件
│   ├── spatial/              # (内含 16 项空间组学底层核心支持文件架构 _lib 体系)
│   ├── singlecell/           # (内含 14 项单细胞超清渲染架构及独立管道)
│   ├── genomics/             # (基因组专项组)
│   ├── proteomics/           # (跨接质谱转码工具底层架)
│   ├── metabolomics/         # 同上
│   ├── bulkrna/              # 同上
│   └── orchestrator/         # 多维调度及构建自动化代码管线中心区
├── knowledge_base/           # 防御性护栏与特定分析方法的最佳处理准则大模型记忆库
├── bot/                      # 多维度的各种主流社交通讯软件挂架核心处理框架
├── frontend/                 # React/Vite 现代开发体系所编写的极其精美的可视化大记忆交互看板
├── website/                  # 帮助项目落地的官方部署站台
├── docs/                     # 所有硬核架构与细分算法原理支持手册集束包
├── examples/                 # 给新用户上手跑通各个内置技能线的内置标准玩具数据集
├── scripts/                  # 为周边环境自动生成报告提供代码辅助的热补丁执行脚本
├── templates/                # 生成报告和渲染各家大模型底板提示词语料池的标准大纲库
├── tests/                    # 开发安全与健壮可用性的保障模块压力组件安全基石
├── sessions/                 # 无处安防甚至中途断电被迫终止崩溃流被完美冻结封装保留下来的日志记忆地
├── Makefile                  # 构建编译和部署系统各种一键调配快捷组合终端触发字典源
└── install_r_dependencies.R  # 热感应为机器把整个 R 语言庞大复杂体系全搞定的脚本底座
```

**极其独立的自治化微元服务生态：**
每一个细致分析的技能单元均完全解耦、能单独存续自保工作：
```
skills/<所归属的大类_domain>/<它自己的名字_skill>/
├── SKILL.md                  # 最关键的！大模型依据它完全看懂它的输入输出能去干什么！
├── <skill_script>.py         # 真理与现实接轨的终端可调用物理执行 Python 算法逻辑
└── tests/                    # 单技能隔离无尘测试组件
```
所有相互之间不同维度的夸组学技能间通过极其标准的 (`.h5ad`, `.vcf`, `.mzML`, `.csv`) 制式接头组装管道桥沟通，可以实现超维拼接融合！

</details>


## 📱 多端互联渠道挂载 — 宣告“聊天纪元”科研新互动的来临

OmicsClaw 的雄心远不仅局限于此，你还可以将其挂到外部分布服务器或者本机上变为一个 **永远不关机、并配有超强记忆力的超级伴学生信个人书童**！目前只要轻松设置，它便能无缝打穿整个全球主流社交通讯平台终端作为代理为您打工：包括跨国度的 Telegram, Discord, Slack 或是国内主流企业协同矩阵工具——飞书/Lark, 钉钉, 企业 WeChat 以及腾讯 QQ、邮件流，甚至是私密的苹果级端到端加密系统 iMessage 原生短信。这一切的数据终端背后统一对齐到了和您的物理电脑 CLI 命令界面绝对同步的一个数据池会话里。

```bash
# 激进安装下多全媒体协议聊天基座必备引擎库
pip install -r bot/requirements.txt
# 或者使用暴力一键满配套网络连接
pip install -r bot/requirements-channels.txt

# 将样板文件直接拷贝成为实际运行挂载参数密钥锁
cp .env.example .env

# 然后您随手便可以后台守护级同时并行推入多个通道代理唤醒进程
python -m bot.run --channels telegram,feishu,slack
# 当然我们内置了别称命令助您更为优雅的后台一键唤醒多发平台
make bot-multi CHANNELS=telegram,discord
```

**在这个纪元你能得到什么不可思议的提升:**
- 🧠 **有心智跨越长时空的连接** — 过个周末完全放空休息归来上线，你也无需再去倒腾周五那个该死的文件路径存在哪。它全记在本子里等着继续开机衔接进度。处理偏好选项全部按照你个人的作风和色彩板喜好定制渲染！
- 💬 **讲人类的白话交流** — 打字发送 “给刚传进来的组织划定并染色个空间功能小聚落范围！” → 底层直接组装路由找到匹配的方法包运算后输出。
- 📁 **跨介质的数据上传池** — 完全拥抱主流重载大型分析文件体系介质拖放（直接向聊天对话框传入 `.h5ad`, `.vcf`, `.mzML`, 并兼顾巨长篇的常规统计表格`.csv`/`.tsv` ）
- 📊 **端到端的图像推回** — 任务执行结束后不用再去跑进服务器查日志拉图片；丰富排版的精美分析 Markdown 报表带超高清展示大图自动推送弹射回你的聊天对话框甚至手机屏幕前！
- 🔒 **严格把控物理隔离的数据长城** — 不用害怕聊天渠道把珍贵敏感的科研病症数据出卖给了大模型厂商或是工具服务商。Bot 后台协议通道在传递过程中只发送和收回必要的意图识别对话（全文字和渲染呈现态图），而这背后所有实打实消耗的极具敏感重量的数据集本体则全部永远封闭封锁、并且只发生在你本地受控安全的 CPU 加计算内存架构中执行与吞吐。做到了网络流和庞大数据的绝对物理隔绝安全墙！

> [!TIP]
> 关于您到底怎么在一分钟内零基础就能建立连通如上那些奇幻的聊天接口、配置授权 API 权限指引以和获得各类复杂接口白名单及运行时策略设置教学等，非常详尽具体的攻略请猛搓 **[Channel Integration Guide 通道挂接与架构部署指南大全](bot/README.md)**!

## 在参与这片开源绿洲的路上我们极度渴望您的才华与构想

极度热忱、欢迎并恳切期待海内外无论是顶尖算法先锋团队或是正饱受折磨正要写第一行分析脚本的研究新手能加入这片属于我们的开源底盘来重构与建立生态圈！如若您有一套自己行之有效或即将要开拓出来的新颖解决问题算法包、并期望全生物行业的人都能够一键使用，请别客气给它包进 OmicsClaw 成为千古长存的新增内置底层引擎吧：

1. 添加一片专属于这套体系的架构文件夹空域: `skills/<所选归属大领域例如 spatial>/<随意由您拍板的功能战甲小名>/`
2. 按照模板创建出非常干练的一份 `SKILL.md` (它是向顶端大语言模型去声明自己能力机制的最强大自我介绍信)
3. 塞入带有您所有专业智慧与技巧编写和组装出实际物理承重的分析核 — `xxx.py` 代码。
4. 将该整套隔离放入 `tests/` 目录下做极端场景可用性碰撞演武测试。
5. 最后极简在根目录下直接调用一条一键指令 `python scripts/generate_catalog.py` 刷新系统，框架会将你的所有心血立刻自动融汇打包挂进注册登记树成为正式内嵌版！整个过程不超过10分钟。

请务必细致去品读查阅为开发者倾心撰写的贡献全攻略：[AGENTS.md](AGENTS.md) .

## 文档参考资料导航专区

- [docs/INSTALLATION.md](docs/INSTALLATION.md) — 包外围依赖处理与按维度按大类的进阶分层安装手册
- [docs/METHODS.md](docs/METHODS.md) — 我们全覆盖底座里的底层关键计算统筹法源文献与参考指标大清单
- [docs/architecture.md](docs/architecture.md) — 探讨与解析为什么我们将架构解耦出这样的流派模式之详尽研究设想图谱
- [CLAUDE.md](CLAUDE.md) — 独家给予各种多模态超级大语言模型 Agent 角色调度下发的专属机器侧强制读阅运行天花板底线
- [bot/README.md](bot/README.md) — 怎么无痛把这个巨兽连入你手机随时控制和看护的完整图文布教

## ⚠️ 严正风险警告和产品安全性宣告免责条文

- **本地物理安全铁律不可被逾越** — 此架构底盘强行且唯一的设定准则即数据必须保全停留在用户的自有的数据存储体或私有机架内
- **一切只为辅助临床前的绝对科研用途** — 此应用不受到医疗器械安全管理局和各国行业最高强制背书，所演算出的报告不承担且不可代替终极正规实务出诊的临床病例指导确诊证据或医疗定责依据。
- **请恪守生物科学专业判断伦理的最终审查底线** — 非常郑重恳求请一定并最终交给真实在相关领域的生信与医疗专研专家人士进行分析审判结论敲定！

## 代码流派授权与分发准则

OmicsClaw 根据对行业开放程度最高、极度拥抱未来发展的 Apache-2.0 框架下提供所有原始构建逻辑及底层源代码 — 具体权责、使用下发传承、魔改派生的任何详情和准绳等请查阅全本 [LICENSE](LICENSE) 法令协议说明底稿档.

## 请给予支持引用与我们同在同行

倘若幸而我们的存在大幅减缓了您分析探索宇宙至理过程中的极大痛楚并确实产出了有效的文章报刊，恳请并极度期待您能为您的小老弟助手添加一臂荣誉来源引用：

```bibtex
@software{omicsclaw2026,
  title = {OmicsClaw: A Memory-Enabled AI Agent for Multi-Omics Analysis},
  author = {Zhou, Weige and Chen, Liying and Yin, Pengfei and Tian, Luyi},
  year = {2026},
  url = {https://github.com/TianGzlab/OmicsClaw}
}
```

## 感恩及背书团队

OmicsClaw 的破世而出要深深的感激在开源生信自动化世界深耕铺路的一大批极为卓越的前驱团队：

- **[ClawBio](https://github.com/ClawBio/ClawBio)** — 开辟先河的首例专为了原生生物信息分析自动化所编撰的底层人工智能框架动作库。极其具有先导性的开放性模块设计，与绝对极度恪守纯本地安全与无污染的开源价值观，为 OmicsClaw 后来的发散做上了不可取代的灵魂灯塔背书，叩谢致意！
- **[Nocturne Memory](https://github.com/Dataojitori/nocturne_memory)** — 一个对开发者极为友好、极度轻量与轻巧，并且全流程数据都能完全可溯源滚轴退回的历史超长节点追溯中枢！OmicsClaw 此庞大的“神庭系统”——【持久化复杂数据网络结构中心架构】的核心支架搭建及 MCP 协议接入安全网的设计巧思更是完美融汇传承自他们强力、安全的概念精髓并深埋到了我们的算力心脏生态池当中，感谢指路！

## 联系开发作者及核心通信维护团队人员接洽

- **Luyi Tian (项目全盘监督及项目管理导师)** — [tian_luyi@gzlab.ac.cn](mailto:tian_luyi@gzlab.ac.cn)
- **Weige Zhou (首席一号位架构执行构建者兼总牵头代码代表)** — [GitHub主页地址](https://github.com/zhou-1314)
- **Liying Chen (引擎层级管线骨干共码及算法调试高级校验研究员)** — [GitHub主页地址](https://github.com/chenly255)
- **Pengfei Yin (多维度生态管网与架构代码拓展构件强力贡献推塔核心研究先锋)** — [GitHub主页地址](https://github.com/astudentfromsustech)

全团队极其激动、随时接纳大家有关各种对于我们这片汪洋生态里的任意报错修复、以及哪怕只是一丁点惊掉下巴期望在未来落地的奇幻能力建议大图蓝本畅想：期待您直呼猛戳我们的中央核心枢纽官方站台 [GitHub官方Issue下留言区](https://github.com/TianGzlab/OmicsClaw/issues) 砸稿！我们绝不错过你的呼唤！
