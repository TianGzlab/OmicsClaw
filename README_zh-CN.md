<a id="top"></a>

<div align="center">
  <img src="docs/images/OmicsClaw_logo.svg" alt="OmicsClaw Logo" width="380"/>

  <h2>🧬 OmicsClaw</h2>
  <p><strong>面向多组学分析的本地优先 AI 研究助手</strong></p>
  <p>用对话驱动工作流 · 运行可复现技能 · 数据留在本地 · 用记忆延续上下文</p>

  <p>
    <a href="README.md"><b>English</b></a> ·
    <a href="README_zh-CN.md"><b>简体中文</b></a> ·
    <a href="#-为什么选择-omicsclaw"><b>为什么</b></a> ·
    <a href="#-快速开始"><b>快速开始</b></a> ·
    <a href="#-能力"><b>能力</b></a> ·
    <a href="#-领域"><b>领域</b></a> ·
    <a href="https://TianGzlab.github.io/OmicsClaw/"><b>文档站</b></a>
  </p>
</div>

# OmicsClaw

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://github.com/TianGzlab/OmicsClaw/actions/workflows/pr-ci.yml/badge.svg)](https://github.com/TianGzlab/OmicsClaw/actions/workflows/pr-ci.yml)
[![Website](https://img.shields.io/badge/Website-Live-brightgreen.svg)](https://TianGzlab.github.io/OmicsClaw/)

OmicsClaw 把本地多组学工具变成 AI 可调用的技能。LLM 负责规划与编排；Python/R/CLI 工具在你的本地或远程运行时里实际处理数据。

## 🖥️ App 工作区

<p align="center">
  <img src="docs/images/omicsclaw-app-overview.png" alt="OmicsClaw App：连接后端、AutoAgent、数据集、技能、记忆、远程桥与多组学分析卡片" width="94%"/>
</p>

<p align="center">
  <b>一个工作区统一对话、数据集、技能、执行、记忆与分析产出。</b>
</p>

## 💡 为什么选择 OmicsClaw？

| 常见痛点 | OmicsClaw 的回应 |
|---|---|
| 分析每次都从零开始 | 持久化的工作区、会话与图记忆 |
| Python、R、CLI 工具散落各处 | 统一的技能运行器 + 自然语言路由 |
| 大数据放在服务器上 | 本地 UI + 通过 SSH 远程在 Linux 上执行 |
| 报告、产物、参数互相漂移 | 标准化技能输出契约 + 可复现 demo |

## ✨ 能力

| | | | |
|---|---|---|---|
| 🧠 **记忆**<br/>会话、偏好、血缘 | 🔒 **本地优先**<br/>原始数据留在你的运行时 | 🧰 **89 个技能**<br/>自动生成目录 + demo | 🧭 **智能路由**<br/>自然语言映射到工具 |
| 🖥️ **CLI / TUI**<br/>`oc interactive`、`oc tui` | 🌐 **App 后端**<br/>给桌面/Web 前端用的 FastAPI | 🔌 **MCP 就绪**<br/>接入外部工具 | 📡 **远程模式**<br/>SSH 隧道到 Linux 服务器 |

## ⚡ 快速开始

```bash
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw
bash 0_setup_env.sh
conda activate OmicsClaw
oc list
oc run spatial-preprocess --demo --output /tmp/omicsclaw_demo
```

配置对话与运行时：

```bash
oc onboard
oc interactive
```

如果 `oc` 不在 `PATH` 中，用 `python omicsclaw.py <command>` 替代。

<p align="center">
  <img src="docs/images/OmicsClaw_configure_fast.png" alt="OmicsClaw 配置向导" width="82%"/>
</p>

## 🧭 接入方式

| 入口 | 命令 | 用途 |
|---|---|---|
| 🧪 技能运行器 | `oc run <skill> --demo` | 可复现的分析 |
| 💬 交互式 CLI | `oc interactive` | 自然语言驱动工作流 |
| 🖥️ 全屏 TUI | `oc tui` | 终端式工作区会话 |
| 🌐 App 后端 | `oc app-server` | 桌面/Web 前端 |
| 📡 远程服务器 | SSH 上跑 `oc app-server` | 服务端数据与任务 |
| 🤖 Bots | `python -m bot.run --channels ...` | Telegram、飞书等 |
| 🔌 MCP | `oc mcp add ...` | 接入外部工具 |

远程模式使用 `127.0.0.1` + SSH 隧道 + `OMICSCLAW_REMOTE_AUTH_TOKEN`。详见 [remote execution](docs/engineering/remote-execution.mdx) 与 [legacy remote guide](docs/_legacy/remote-connection-guide.md)。

## 📦 安装

| 路径 | 适用 | 命令 |
|---|---|---|
| 🥇 **完整 conda** | 用 Python + R + 生信 CLI 的真实分析 | `bash 0_setup_env.sh` |
| 🪶 **轻量 venv** | 对话、路由、开发、纯 Python 技能 | `pip install -e ".[interactive]"` |
| 🖥️ **桌面/Web 后端** | OmicsClaw-App 或浏览器前端 | `oc app-server --host 127.0.0.1 --port 8765` |
| 🧠 **记忆 API** | 通过 HTTP 检视图记忆 | `pip install -e ".[memory]"` 然后 `oc memory-server` |

📖 详细见 [安装指南](docs/_legacy/INSTALLATION.md) 与 [快速上手](docs/introduction/quickstart.mdx)。依赖分别由 [`pyproject.toml`](pyproject.toml)、[`environment.yml`](environment.yml)、[`0_setup_env.sh`](0_setup_env.sh) 管理。

## 🧬 领域

`oc list` 与 `skills/catalog.json` 当前一致维护 **89 个已注册技能**。

| 领域 | 示例技能 | 文档 |
|---|---|---|
| 🧫 空间转录组 | QC、domain、注释、解卷积、CNV、轨迹 | [spatial](docs/domains/spatial.mdx) |
| 🔬 单细胞组学 | QC、聚类、注释、doublet、velocity、GRN | [singlecell](docs/domains/singlecell.mdx) |
| 🧬 基因组学 | QC、比对、变异、CNV、组装、表观 | [genomics](docs/domains/genomics.mdx) |
| 🧪 蛋白组学 | DIA/DDA、PTM、网络、biomarker | [proteomics](docs/domains/proteomics.mdx) |
| ⚗️ 代谢组学 | 峰、归一化、注释、通路 | [metabolomics](docs/domains/metabolomics.mdx) |
| 📈 Bulk RNA-seq | DE、富集、共表达、解卷积、生存 | [bulkrna](docs/domains/bulkrna.mdx) |
| 🧠 编排 | 路由、规划、文献支持 | [orchestrator](docs/domains/orchestrator.mdx) |

完整 CLI 技能列表运行 `oc list` 查看。

## 🧠 记忆

`omicsclaw/memory/` 下的图记忆把会话、数据集、分析、偏好、洞察跨运行串起来 —— 重开任意入口都能找回对话历史与血缘。每个入口相互隔离，状态不会在用户或工作区之间泄漏：

| 入口 | 记忆作用域 |
|---|---|
| CLI / TUI | 按工作区路径 |
| 桌面 App | 按启动（或登录用户） |
| Telegram / 飞书 Bot | 按平台用户 |

保留的 `__shared__` 池（核心 agent 身份、术语表）是所有入口都会自动回读的部分。完整术语与架构详见 [`docs/CONTEXT.md`](docs/CONTEXT.md)。

## ❓ FAQ

<details>
<summary><b>OmicsClaw 会上传我的原始数据吗？</b></summary>

不会。技能在你配置的本地或远程运行时里执行；LLM 调用收到的是上下文和工具结果，不包含原始组学矩阵。

</details>

<details>
<summary><b>我应该选哪种安装方式？</b></summary>

真实分析用 `bash 0_setup_env.sh`。轻量 venv 仅用于对话、路由、开发、纯 Python 技能。

</details>

<details>
<summary><b>桌面 App 能在服务器上跑任务吗？</b></summary>

可以。在远程 Linux 上运行 `oc app-server`，绑定 `127.0.0.1`，再通过 App 的 SSH 隧道运行时连接过来。

</details>

## ⚠️ 安全

| 规则 | 含义 |
|---|---|
| 🔒 本地优先 | 原始数据处理发生在你的本地或远程运行时 |
| 🧪 仅供研究 | 不是医疗器械，不提供临床诊断 |
| 👩‍🔬 专家复核 | 在做决策前由领域专家验证科学产出 |
| 🔐 远程谨慎 | 使用 localhost 绑定、SSH 隧道与 token |

详见 [数据隐私](docs/safety/data-privacy.mdx) 与 [使用规则与免责声明](docs/safety/rules-and-disclaimer.mdx)。

## 👥 社区

维护者：Luyi Tian（首席研究员）、Weige Zhou（主导开发）、Liying Chen（开发）、Pengfei Yin（开发）。

🐛 [Issues](https://github.com/TianGzlab/OmicsClaw/issues) · 💬 [Discussions](https://github.com/TianGzlab/OmicsClaw/discussions) · 📖 [文档站](https://TianGzlab.github.io/OmicsClaw/)

<table>
  <tr>
    <td align="center" width="30%">
      <img src="docs/images/IMG_3729.JPG" alt="OmicsClaw 微信交流群" width="180"/>
      <br/>
      <b>微信交流群</b>
      <br/>
      <sub>扫码加入</sub>
    </td>
    <td valign="middle" width="70%">
      欢迎扫码加入微信群，分享分析经验、反馈问题、与社区交流多组学 AI 工作流。
    </td>
  </tr>
</table>

## 🙏 致谢

OmicsClaw 的架构、技能设计和本地优先理念深受 **[ClawBio](https://github.com/ClawBio/ClawBio)**（生物信息学场景下较早的原生 AI agent 技能库）启发。记忆与会话续接模式参考了 [Nocturne Memory](https://github.com/Dataojitori/nocturne_memory)。

## 🛠️ 贡献

- **新增技能**：参考 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [`templates/skill/`](templates/skill/) 的 v2 脚手架。
- **仓库 / agent 开发**：参考 [AGENTS.md](AGENTS.md) —— 包含 contract 测试、provider 契约、技能运行器、架构文档索引。

## 📜 许可证

Apache-2.0，详见 [LICENSE](LICENSE)。

## 📝 引用

```bibtex
@software{omicsclaw2026,
  title = {OmicsClaw: A Memory-Enabled AI Agent for Multi-Omics Analysis},
  author = {Zhou, Weige and Chen, Liying and Yin, Pengfei and Tian, Luyi},
  year = {2026},
  url = {https://github.com/TianGzlab/OmicsClaw}
}
```

[⬆ 返回顶部](#top)
