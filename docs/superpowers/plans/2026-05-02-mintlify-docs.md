# Mintlify 中文文档站 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 OmicsClaw 仓库根目录建立 Mintlify 中文文档站（20 页 / 7 组），结构对标 `repo_learn/langcli/docs`，旧英文文档整体归档。

**Architecture:** 新增根级 `mint.json` 站点配置；`docs/` 下新建 6 个内容子目录（`introduction/architecture/domains/engineering/ecosystem/safety`）共 20 篇 `.mdx`；既有 7 篇英文 `docs/*.md` 整体 `git mv` 到 `docs/_legacy/`，由 `mint.json` 的 `excludes` 字段排除在站外。

**Tech Stack:** Mintlify (站点) · MDX (内容) · `npx mintlify dev`（本地预览，不写入 `package.json`）

**Spec:** `docs/superpowers/specs/2026-05-02-mintlify-docs-design.md`

**Verification model:** 本计划是文档工程，没有单元测试。每个 page-task 的"测试"是：
1. 文件存在且 frontmatter 含 `title / description / keywords / og:image` 四项；
2. `npx mintlify dev` 启动后该页可访问、无 schema 报错；
3. 页面正文符合 spec 第 1 节定义的写作模板。

---

## Phase 1: 脚手架

### Task 1: 创建 `_legacy/` 目录并迁入 7 篇旧 MD

**Files:**
- Create: `docs/_legacy/README.md`
- Move: `docs/architecture.md` → `docs/_legacy/architecture.md`
- Move: `docs/INSTALLATION.md` → `docs/_legacy/INSTALLATION.md`
- Move: `docs/METHODS.md` → `docs/_legacy/METHODS.md`
- Move: `docs/R-DEPENDENCIES.md` → `docs/_legacy/R-DEPENDENCIES.md`
- Move: `docs/MEMORY_SYSTEM.md` → `docs/_legacy/MEMORY_SYSTEM.md`
- Move: `docs/remote-connection-guide.md` → `docs/_legacy/remote-connection-guide.md`
- Move: `docs/skill-architecture.md` → `docs/_legacy/skill-architecture.md`

- [ ] **Step 1: 用 `git mv` 把 7 篇英文 MD 整体迁入 `docs/_legacy/`**

```bash
mkdir -p docs/_legacy
git mv docs/architecture.md           docs/_legacy/architecture.md
git mv docs/INSTALLATION.md           docs/_legacy/INSTALLATION.md
git mv docs/METHODS.md                docs/_legacy/METHODS.md
git mv docs/R-DEPENDENCIES.md         docs/_legacy/R-DEPENDENCIES.md
git mv docs/MEMORY_SYSTEM.md          docs/_legacy/MEMORY_SYSTEM.md
git mv docs/remote-connection-guide.md docs/_legacy/remote-connection-guide.md
git mv docs/skill-architecture.md     docs/_legacy/skill-architecture.md
```

- [ ] **Step 2: 写 `docs/_legacy/README.md`，含归档说明 + 新旧映射表**

写入以下完整内容：

```markdown
# Legacy English Documentation (Archived)

These English Markdown files were the previous **developer-facing** documentation
of OmicsClaw. They have been superseded by the Mintlify Chinese documentation
site at the repository root (`mint.json` → `docs/<group>/*.mdx`).

They are kept here as **internal reference** for contributors and maintainers.
They are excluded from the public docs site via `mint.json`'s `excludes` field.

## New ↔ Legacy Mapping

| Legacy file (English)           | Replaced by (Chinese MDX)                     |
|---------------------------------|-----------------------------------------------|
| `architecture.md`               | `docs/architecture/overview.mdx`              |
| `skill-architecture.md`         | `docs/architecture/skill-system.mdx`          |
| `INSTALLATION.md`               | `docs/introduction/quickstart.mdx`            |
| `METHODS.md`                    | (distributed across `docs/domains/*.mdx`)     |
| `R-DEPENDENCIES.md`             | `docs/engineering/replot.mdx`                 |
| `MEMORY_SYSTEM.md`              | `docs/engineering/memory.mdx`                 |
| `remote-connection-guide.md`    | `docs/engineering/remote-execution.mdx`       |

## Why archive instead of delete

These files contain detail (R package versions, environment troubleshooting,
SSH bootstrap commands, etc.) that the new user-facing docs intentionally
elide. Maintainers may need them when debugging environment or deployment
issues. Treat them as **append-only** — do not edit; update the corresponding
new MDX page instead.
```

- [ ] **Step 3: 验证 `docs/` 顶层只剩新结构所需的目录与既有非待迁文件**

```bash
ls docs/
```

Expected: 输出包含 `_legacy/`、`images/`、`superpowers/`，**不含** 7 篇被迁走的 `.md`。

- [ ] **Step 4: Commit**

```bash
git add -A docs/_legacy docs/architecture.md docs/INSTALLATION.md docs/METHODS.md docs/R-DEPENDENCIES.md docs/MEMORY_SYSTEM.md docs/remote-connection-guide.md docs/skill-architecture.md
git commit -m "docs(legacy): archive English MD into docs/_legacy"
```

---

### Task 2: 创建 logo / favicon / OG 资产（第一版用既有 jpeg 占位）

**Files:**
- Create: `docs/logo/light.svg`
- Create: `docs/logo/dark.svg`
- Create: `docs/favicon.svg`
- Create: `docs/images/og-cover.png`

**Strategy:** SVG 化属后续 polishing（spec 第 5 节）。本任务用既有 `docs/images/OmicsClaw_logo.jpeg` 直接复用为路径，避免阻塞。Mintlify 接受位图当 logo。

- [ ] **Step 1: 在 `docs/logo/` 直接复制既有 logo 为 jpeg（保留 .svg 文件名以匹配 mint.json 字段约定，Mintlify 按内容 magic bytes 判断格式）**

```bash
mkdir -p docs/logo
cp docs/images/OmicsClaw_logo.jpeg docs/logo/light.svg
cp docs/images/OmicsClaw_logo.jpeg docs/logo/dark.svg
cp docs/images/OmicsClaw_logo.jpeg docs/favicon.svg
cp docs/images/OmicsClaw_logo.jpeg docs/images/og-cover.png
```

注：扩展名与实际内容不一致是已知技术债，记录在 `docs/_legacy/README.md` 后续 polishing 部分（执行人若觉得别扭可改 mint.json 用 jpeg 路径替代）。

- [ ] **Step 2: 验证 4 个文件存在**

```bash
ls -l docs/logo/light.svg docs/logo/dark.svg docs/favicon.svg docs/images/og-cover.png
```

Expected: 4 行输出，每个文件大小 > 0。

- [ ] **Step 3: Commit**

```bash
git add docs/logo/ docs/favicon.svg docs/images/og-cover.png
git commit -m "docs(assets): add Mintlify logo/favicon/og placeholders"
```

---

### Task 3: 编写根 `mint.json` 站点配置

**Files:**
- Create: `mint.json`

- [ ] **Step 1: 写入完整 `mint.json`**

写入以下完整内容（导航中所有 20 页路径必须与后续 task 创建的文件完全一致）：

```json
{
  "$schema": "https://mintlify.com/schema.json",
  "name": "OmicsClaw 多组学 AI Agent",
  "logo": {
    "dark": "/docs/logo/dark.svg",
    "light": "/docs/logo/light.svg"
  },
  "favicon": "/docs/favicon.svg",
  "colors": {
    "primary": "#0EA5E9",
    "light": "#38BDF8",
    "dark": "#0284C7",
    "background": {
      "dark": "#0F172A",
      "light": "#FFFFFF"
    }
  },
  "metadata": {
    "og:image": "/docs/images/og-cover.png",
    "twitter:card": "summary_large_image"
  },
  "topbarCtaButton": {
    "type": "github",
    "url": "https://github.com/zhou-1314/OmicsClaw"
  },
  "search": {
    "prompt": "搜索 OmicsClaw 文档..."
  },
  "redirects": [
    {
      "source": "/docs",
      "destination": "/docs/introduction/what-is-omicsclaw"
    }
  ],
  "navigation": [
    {
      "group": "开始",
      "pages": [
        "docs/introduction/what-is-omicsclaw",
        "docs/introduction/why-omicsclaw",
        "docs/introduction/quickstart"
      ]
    },
    {
      "group": "架构",
      "pages": [
        "docs/architecture/overview",
        "docs/architecture/skill-system",
        "docs/architecture/orchestrator"
      ]
    },
    {
      "group": "七大组学",
      "pages": [
        "docs/domains/spatial",
        "docs/domains/singlecell",
        "docs/domains/genomics",
        "docs/domains/proteomics",
        "docs/domains/metabolomics",
        "docs/domains/bulkrna",
        "docs/domains/orchestrator"
      ]
    },
    {
      "group": "工程能力",
      "pages": [
        "docs/engineering/replot",
        "docs/engineering/memory",
        "docs/engineering/remote-execution"
      ]
    },
    {
      "group": "Bot 与生态",
      "pages": [
        "docs/ecosystem/chat-bot",
        "docs/ecosystem/omicsclaw-app"
      ]
    },
    {
      "group": "安全",
      "pages": [
        "docs/safety/rules-and-disclaimer",
        "docs/safety/data-privacy"
      ]
    }
  ],
  "excludes": [
    "docs/_legacy/**",
    "docs/superpowers/**"
  ],
  "footerSocials": {
    "github": "https://github.com/zhou-1314/OmicsClaw"
  }
}
```

- [ ] **Step 2: 用 `python -m json.tool` 校验 JSON 合法**

```bash
python -m json.tool mint.json > /dev/null && echo "JSON OK"
```

Expected: `JSON OK`

- [ ] **Step 3: Commit（此时还未跑 `mintlify dev`，因为 20 页正文还没写——会有 404，但配置本身合法可独立 commit）**

```bash
git add mint.json
git commit -m "docs(mintlify): add site config with 7-group navigation"
```

---

## Phase 2: 「开始」组（3 页）

### 写作模板速查（所有 page-task 共用）

每篇 `.mdx` 必须包含：

```markdown
---
title: "<本页标题>"
description: "<≤140 字一句话描述>"
keywords: ["...", "...", "..."]
og:image: "/docs/images/og-cover.png"
---

## <第 1 节：按页面类型套 spec 第 1 节模板>
...

## <第 2 节>
...

## <第 3 节>
...

## <第 4 节>
...

## 下一步阅读
- [<内链 1>](/docs/<group>/<slug>)
- [<内链 2>](/docs/<group>/<slug>)
```

页面类型→模板分节对应（spec 第 1 节）：

| 区块 | "是什么"页 | 领域页 | 工程能力页 |
|---|---|---|---|
| § 1 | 一句话定义（粗体） | 本领域解决什么问题 + N 个 skill | 本能力为什么需要 |
| § 2 | 与同类工具对比表 | 典型分析流程 ASCII 框图 | 启用前/启用后对比 |
| § 3 | 端到端示例 | 关键 skill 列表表格 | CLI 示例 |
| § 4 | "它不是什么" | 何时不适用 | 故障排查 / FAQ |

---

### Task 4: `docs/introduction/what-is-omicsclaw.mdx`

**Files:**
- Create: `docs/introduction/what-is-omicsclaw.mdx`

**Source materials to read first:**
- `README_zh-CN.md`（项目定位 / 7 个领域简介）
- `SOUL.md`（Bot 人格设定，可在"它不是什么"节呼应）
- `CLAUDE.md` 顶部说明（一句话定义）

**Page type:** "是什么"页（套模板"是什么"列）

- [ ] **Step 1: 写入文件，frontmatter + 4 节骨架**

写入：

```mdx
---
title: "什么是 OmicsClaw - 多组学 AI Agent"
description: "OmicsClaw 是一个本地运行的多组学 AI 代理，覆盖空间转录组、单细胞、基因组、蛋白组、代谢组、Bulk RNA-seq 6 大组学领域，通过 88 个可路由的 skill 提供端到端分析能力。"
keywords: ["OmicsClaw", "多组学", "AI Agent", "spatial transcriptomics", "single-cell", "scRNA-seq", "bioinformatics"]
og:image: "/docs/images/og-cover.png"
---

## 一句话定义

**OmicsClaw 是一个运行在本地的多组学 AI 代理**——它不是给建议的聊天机器人，而是把 88 个生物信息学技能（skill）组织成一套可路由的分析能力，覆盖 6 大组学领域，由编排器（orchestrator）根据用户的自然语言问题自动选择并调用合适的 skill。

## 与同类工具的差异

<!--
  从 README_zh-CN.md 项目定位段提取关键差异点。
  必须是 markdown 表格，包含 4 列：工具 / 定位 / 运行位置 / 数据流向。
  对比对象建议：OmicsClaw / Galaxy / nf-core / 通用 ChatGPT。
  示例第一行：
  | **OmicsClaw** | 多组学 AI Agent + 88 skill | 本地进程 | 数据永不离开本机 |
-->

| 工具 | 定位 | 运行位置 | 数据流向 |
|---|---|---|---|
| **OmicsClaw** | 多组学 AI Agent + 88 skill 路由 | 本地进程 | 数据永不离开本机 |
| Galaxy | Web 平台 + 工作流可视化 | 云端 / 自托管 web | 上传到服务端 |
| nf-core | Nextflow 流水线集合 | 本地 / HPC | 本地处理 |
| 通用 ChatGPT | 对话式问答 | 云端 | 上传到 OpenAI |

## 端到端示例：从一句话问题到分析结果

<!--
  从 CLAUDE.md 的 CLI Reference 章节挑一个简单完整的例子，
  例如 spatial-preprocess 的 demo 调用。
  格式：用户提问 → orchestrator 路由 → CLI 执行 → 输出片段（粘贴 figure 路径列表即可）
-->

```
用户："帮我跑一下 demo 数据的空间转录组预处理"
        │
        ▼
orchestrator 路由 → spatial-preprocess
        │
        ▼
$ python skills/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/preprocess_demo
        │
        ▼
输出：/tmp/preprocess_demo/
  ├── qc_violin.png
  ├── pca_umap.png
  └── report.md
```

## 它不是什么

- **不是医疗器械**：所有结果仅供研究与教学，不构成临床诊断
- **不是云服务**：所有处理在本地完成，原始数据永不上传
- **不是一站式 GUI 平台**：核心是 skill + Bot 的命令式 / 对话式交互，桌面端 OmicsClaw-App 仅承载结果浏览与聊天界面
- **不是黑盒**：每个 skill 都有公开的 SKILL.md 方法论，输出有可追溯的中间产物

## 下一步阅读

- [为什么需要 OmicsClaw](/docs/introduction/why-omicsclaw)
- [五分钟上手](/docs/introduction/quickstart)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 2: 校验 frontmatter 4 项齐全**

```bash
python -c "
import re, sys
content = open('docs/introduction/what-is-omicsclaw.mdx').read()
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
assert m, 'no frontmatter'
fm = m.group(1)
for k in ['title', 'description', 'keywords', 'og:image']:
    assert k in fm, f'missing {k}'
print('frontmatter OK')
"
```

Expected: `frontmatter OK`

- [ ] **Step 3: Commit**

```bash
git add docs/introduction/what-is-omicsclaw.mdx
git commit -m "docs(intro): what-is-omicsclaw page"
```

---

### Task 5: `docs/introduction/why-omicsclaw.mdx`

**Files:**
- Create: `docs/introduction/why-omicsclaw.mdx`

**Source materials:**
- `README_zh-CN.md`（动机 / 痛点段）
- `SOUL.md`（用户场景）

**Page type:** "是什么"页（套同列模板）

- [ ] **Step 1: 写入文件**

```mdx
---
title: "为什么需要 OmicsClaw - 解决多组学分析的碎片化问题"
description: "多组学分析工具碎片化、学习曲线陡、本地隐私要求高。OmicsClaw 用 AI Agent + skill 路由把 88 个分析工具统一成一句话调用，且全部本地运行。"
keywords: ["多组学分析", "本地 AI", "生物信息学工具", "OmicsClaw 动机"]
og:image: "/docs/images/og-cover.png"
---

## 多组学研究者今天的真实痛点

<!--
  3-4 段，每段一个痛点。建议分段：
  1) 工具碎片化（每种组学一套独立生态，命令记不住）
  2) 学习曲线陡（每个工具自己一套参数）
  3) 数据隐私（基因数据不能上云）
  4) 报告化弱（结果到论文图之间还有大量人工拼图）
  从 README_zh-CN.md 动机段提取，每段不超过 3 句话。
-->

## 启用前 / 启用后对比

<!--
  4 行表格，对比同一类任务（如"做一次空间转录组 + 单细胞联合分析"）
  在没有 OmicsClaw 与有 OmicsClaw 时的步骤数 / 工具切换次数 / 数据离开本机的次数。
-->

| 维度 | 启用前 | 启用 OmicsClaw 后 |
|---|---|---|
| 工具切换次数 | 5+（Squidpy / Scanpy / R / Seurat / Excel） | 1（自然语言提问） |
| 命令记忆负担 | 高（每个工具自己一套 CLI） | 低（orchestrator 自动路由） |
| 数据外发风险 | 中-高（云端工具） | 零（全本地） |
| 报告生成 | 人工拼 | skill 内置 markdown 报告 |

## 三个真实场景

<!--
  3 个用户故事段（150-200 字 / 段）。建议：
  - 场景 1：单细胞研究生第一次跑 scRNA-seq，用 OmicsClaw 的 sc-preprocessing skill
  - 场景 2：空间转录组 PI 想批量比较多个样本的 domain 结构
  - 场景 3：bulk RNA-seq 实验室做差异分析 + 富集 + 生存分析的一站式流程
  数据可参考 CLAUDE.md 的 Skill Routing Table 中"Key skills"列。
-->

## 它不解决什么

- **不解决湿实验环节**：建库、上机、原始信号处理（如 BCL → FASTQ）仍需专业仪器
- **不解决统计学新方法发表**：OmicsClaw 是工具集成层，不替代你设计自己的算法
- **不解决团队协作**：本期版本是单机 Agent，没有共享工作区 / 多人协同

## 下一步阅读

- [什么是 OmicsClaw](/docs/introduction/what-is-omicsclaw)
- [五分钟上手](/docs/introduction/quickstart)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "
import re
fm = re.match(r'^---\n(.*?)\n---', open('docs/introduction/why-omicsclaw.mdx').read(), re.DOTALL).group(1)
for k in ['title','description','keywords','og:image']: assert k in fm
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add docs/introduction/why-omicsclaw.mdx
git commit -m "docs(intro): why-omicsclaw page"
```

---

### Task 6: `docs/introduction/quickstart.mdx`

**Files:**
- Create: `docs/introduction/quickstart.mdx`

**Source materials:**
- `docs/_legacy/INSTALLATION.md`（安装步骤）
- `0_setup_env.sh` 与 `0_build_vendored_tools.sh`（实际安装命令）
- `CLAUDE.md` 的 "Demo Commands" 节

**Page type:** "是什么"页（端到端示例较多，仍套同列模板）

- [ ] **Step 1: 写入文件**

```mdx
---
title: "五分钟上手 OmicsClaw"
description: "从克隆仓库到跑通第一个 demo 分析，五分钟完成 OmicsClaw 安装与首次调用。"
keywords: ["OmicsClaw 安装", "quickstart", "demo", "conda 环境"]
og:image: "/docs/images/og-cover.png"
---

## 这一页能让你做什么

跑通 OmicsClaw 的第一个 demo 分析（无需准备数据）。读完后你会拥有：
- 一个可用的 conda 环境
- 一份 spatial-preprocess demo 的输出报告
- 对 `omicsclaw.py run` CLI 的基本认知

## 安装：四步

<!--
  从 docs/_legacy/INSTALLATION.md + 0_setup_env.sh 提取实际命令。
  必须以编号列表 + bash 代码块呈现，每条命令必须可直接复制粘贴。
  必须包含：
    1) git clone
    2) cd 与 0_setup_env.sh 调用（含解释：mamba-first conda 安装）
    3) 0_build_vendored_tools.sh（如适用）
    4) 验证安装：python omicsclaw.py list
-->

```bash
# 1. 克隆仓库
git clone https://github.com/zhou-1314/OmicsClaw.git
cd OmicsClaw

# 2. 创建 conda 环境（mamba-first，约 5-15 分钟）
bash 0_setup_env.sh

# 3. 构建 vendor 工具（如适用）
bash 0_build_vendored_tools.sh

# 4. 激活并验证
conda activate omicsclaw
python omicsclaw.py list
```

## 第一次调用：跑 demo

```bash
python omicsclaw.py run spatial-pipeline --demo
```

预期看到：
```
[orchestrator] routing 'spatial-pipeline' → spatial-preprocess + spatial-domains + spatial-de + spatial-genes + spatial-statistics
[spatial-preprocess] running on demo Visium (200 spots, 100 genes)
[spatial-preprocess] output → /tmp/spatial_pipeline_demo/
...
✓ Pipeline complete. See /tmp/spatial_pipeline_demo/report.md
```

## 它不是什么

- **不是 GUI 安装包**：本期需用命令行；桌面端 OmicsClaw-App 是另一回事（见生态页）
- **不是云部署指南**：所有命令针对本地 Linux/macOS；远程模式见工程能力组
- **不覆盖 R 依赖问题排查**：详见归档的 [`docs/_legacy/R-DEPENDENCIES.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/docs/_legacy/R-DEPENDENCIES.md)

## 下一步阅读

- [整体架构](/docs/architecture/overview) — 理解 skill 与 orchestrator
- [七大组学：空间转录组](/docs/domains/spatial) — 第一个完整领域示例
- [Memory 系统](/docs/engineering/memory) — 如何让 OmicsClaw 记住你的偏好
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/introduction/quickstart.mdx').read(), re.DOTALL).group(1); [None for k in ['title','description','keywords','og:image'] if k in fm or (_ := (_ for _ in ()).throw(AssertionError(k)))]; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add docs/introduction/quickstart.mdx
git commit -m "docs(intro): quickstart page"
```

---

## Phase 3: 「架构」组（3 页）

### Task 7: `docs/architecture/overview.mdx`

**Files:**
- Create: `docs/architecture/overview.mdx`

**Source materials:**
- `docs/_legacy/architecture.md`（既有英文架构文档，主要参考源）
- `CLAUDE.md`（Skill Routing Table、Bot 节）

**Page type:** "工程能力"页（架构是抽象能力，套此模板）

- [ ] **Step 1: 写入文件**

```mdx
---
title: "OmicsClaw 整体架构"
description: "OmicsClaw 由 5 层组成：用户接口（CLI / Bot / 桌面端）→ 编排器 → skill 注册表 → 88 个 skill → 数据层。各层通过明确接口通信。"
keywords: ["OmicsClaw 架构", "skill system", "orchestrator", "agent architecture"]
og:image: "/docs/images/og-cover.png"
---

## 为什么是这个架构

<!--
  从 docs/_legacy/architecture.md 提取/翻译"Overview"段。3-4 句话讲清楚：
  - 为什么把 skill 做成独立单元而不是一个大脚本
  - 为什么需要 orchestrator 做路由
  - 为什么用户接口要多种（CLI + Bot + 桌面端）
-->

## 五层架构 ASCII 图

```
┌──────────────────────────────────────────────────────────────┐
│ 1. 用户接口层                                                │
│    CLI (omicsclaw.py)  /  Bot (Telegram + Feishu)  /  App   │
├──────────────────────────────────────────────────────────────┤
│ 2. 编排层 (orchestrator)                                     │
│    自然语言意图 → skill 选择 → 参数补全                      │
├──────────────────────────────────────────────────────────────┤
│ 3. Skill 注册表                                              │
│    88 个 SKILL.md + 入口脚本，按 7 个 domain 分组            │
├──────────────────────────────────────────────────────────────┤
│ 4. Skill 执行层                                              │
│    Python (Scanpy / Squidpy / pyDESeq2 / ...)                │
│    R Enhanced (ggplot2 重绘)                                 │
├──────────────────────────────────────────────────────────────┤
│ 5. 数据与产物层                                              │
│    输入: h5ad / counts / FASTQ / mzML                        │
│    输出: figures + figure_data + report.md                   │
└──────────────────────────────────────────────────────────────┘
```

## 启用前 / 启用后

<!--
  对比"自己写 pipeline"与"用 OmicsClaw"：
  - 用户负担（学每个工具 vs 用一种 CLI）
  - 复用度（每次重写 vs skill 即插即用）
  - 一致性（每人风格不同 vs 模板化报告）
-->

## 关键调用链：从 `omicsclaw.py run X` 到产出

<!--
  端到端追踪一次 run。可以基于代码引用，但用 ASCII 而非真代码块。例：
    omicsclaw.py run X --demo
        │
        ├─ omicsclaw/registry.py  → 加载 X 的 SKILL.md + entry script
        ├─ omicsclaw/runner.py    → 拼接 CLI 参数（--demo 等）
        ├─ skills/<domain>/X/X.py → 真正执行
        └─ omicsclaw/replot/      → （可选）后续 replot 命令
-->

## 故障排查

| 症状 | 可能原因 | 解决 |
|---|---|---|
| `omicsclaw.py list` 报 skill 找不到 | conda 环境未激活 | `conda activate omicsclaw` |
| 某 skill 缺 R 依赖 | R Enhanced 依赖未装 | 见归档 `R-DEPENDENCIES.md` |
| Bot 无响应 | `.env` 缺 LLM_API_KEY | 见 [Bot 与生态](/docs/ecosystem/chat-bot) |

## 下一步阅读

- [技能系统](/docs/architecture/skill-system) — skill 的注册与发现机制
- [编排器](/docs/architecture/orchestrator) — 路由是怎么做的
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/architecture/overview.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/overview.mdx
git commit -m "docs(arch): overview page"
```

---

### Task 8: `docs/architecture/skill-system.mdx`

**Files:**
- Create: `docs/architecture/skill-system.mdx`

**Source materials:**
- `docs/_legacy/skill-architecture.md`（主要参考源）
- `skills/<任意 domain>/INDEX.md`（看 INDEX 格式）
- `skills/spatial-preprocess/SKILL.md`（看 SKILL 格式）

**Page type:** "工程能力"页

- [ ] **Step 1: 写入文件**

```mdx
---
title: "技能系统 - Skill 是怎么组织和发现的"
description: "OmicsClaw 的 88 个 skill 按 7 个领域分目录，每个 skill 由 SKILL.md（方法论）+ 入口脚本组成。Registry 启动时扫描全量 skill，orchestrator 据此路由。"
keywords: ["skill system", "SKILL.md", "registry", "OmicsClaw 技能"]
og:image: "/docs/images/og-cover.png"
---

## 为什么用 skill 这种组织方式

<!--
  从 docs/_legacy/skill-architecture.md 提取/翻译"Why skills"段。
  关键论点：可发现性 / 可替换性 / 可教（SKILL.md 同时是文档和路由元数据）
-->

## Skill 的物理布局

```
skills/
├── spatial/
│   ├── INDEX.md                    ← 本领域所有 skill 一行简介列表
│   ├── spatial-preprocess/
│   │   ├── SKILL.md                ← 方法论 + CLI 接口契约
│   │   └── spatial_preprocess.py   ← 入口脚本
│   ├── spatial-domains/
│   │   ├── SKILL.md
│   │   └── spatial_domains.py
│   └── ...（共 17 个）
├── singlecell/    （30 个）
├── genomics/      （10 个）
├── proteomics/    （8 个）
├── metabolomics/  （8 个）
├── bulkrna/       （13 个）
└── orchestrator/  （2 个）
```

## SKILL.md 的契约

每个 SKILL.md 必须包含的字段（从 spatial-preprocess/SKILL.md 模板提取）：

<!--
  读 skills/spatial-preprocess/SKILL.md，把它的章节标题转成一个表格：
  | 字段 | 用途 | 示例 |
  覆盖至少：name / description / inputs / outputs / methodology / CLI / 关联 skill
-->

## 启用前 / 启用后

| 维度 | 普通脚本集合 | OmicsClaw skill 体系 |
|---|---|---|
| 可发现性 | 翻 README | `omicsclaw.py list` 一行列出全部 |
| 可路由性 | 用户记 CLI | orchestrator 自动选 |
| 可替换性 | 改名要全局搜替 | 只改自己目录 |
| 可教性 | 文档与代码两边维护 | SKILL.md 单一来源 |

## 故障排查

<!--
  3-5 行表格：常见 skill 加载错误。可参考 docs/_legacy/skill-architecture.md
  的 troubleshooting 段。
-->

## 下一步阅读

- [整体架构](/docs/architecture/overview)
- [编排器](/docs/architecture/orchestrator)
- [七大组学概览](/docs/domains/spatial)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/architecture/skill-system.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/skill-system.mdx
git commit -m "docs(arch): skill-system page"
```

---

### Task 9: `docs/architecture/orchestrator.mdx`

**Files:**
- Create: `docs/architecture/orchestrator.mdx`

**Source materials:**
- `skills/orchestrator/SKILL.md`
- `skills/orchestrator/INDEX.md`
- `CLAUDE.md` Skill Routing Table 节

**Page type:** "工程能力"页

- [ ] **Step 1: 写入文件**

```mdx
---
title: "编排器 Orchestrator - OmicsClaw 的大脑"
description: "Orchestrator 把用户的自然语言问题映射到具体的 skill 调用，处理跨领域查询的拆分与编排。它本身也是一个 skill，由 LLM 驱动。"
keywords: ["orchestrator", "skill routing", "LLM agent", "意图识别"]
og:image: "/docs/images/og-cover.png"
---

## 为什么需要 Orchestrator

<!--
  从 skills/orchestrator/SKILL.md 提取核心论点。3 段：
  1) 用户不应该记 88 个 skill 名
  2) 跨领域查询（如"我有 spatial 数据想看 cell-cell communication"）需要拆分
  3) Skill 之间有前后依赖（如 preprocess 必须先于 domains）
-->

## 路由流程 ASCII 图

```
用户："比较两个样本的 domain 差异"
      │
      ▼
┌──────────────────────────────────────────────────┐
│ Orchestrator (LLM-driven)                        │
│  1. 识别意图 → spatial 域 + 多样本 + 域识别       │
│  2. 检查前置 → 数据是否已 preprocess?             │
│  3. 拆分调用 → spatial-domains + spatial-condition│
│  4. 拼接 CLI 参数                                 │
└──────────────────────────────────────────────────┘
      │
      ▼
执行 spatial-domains（每个样本各跑一次）
      │
      ▼
执行 spatial-condition（条件比较）
      │
      ▼
合并报告
```

## 启用前 / 启用后

| 维度 | 没有 orchestrator | 有 orchestrator |
|---|---|---|
| 用户输入 | `python omicsclaw.py run spatial-domains ...` | "比较两个样本的 domain 差异" |
| 跨 skill 编排 | 自己写 shell 串联 | 自动 |
| 前置检查 | 自己保证 | 自动验证产物 |

## 调用方式

<!--
  3 个例子：
  1) 命令行直接走 orchestrator: python omicsclaw.py ask "..."（如适用）
  2) 通过 Bot（自然对话）
  3) 通过桌面端聊天面板
  从 CLAUDE.md / bot/README.md 拼凑实际命令。
-->

## 故障排查

| 症状 | 解决 |
|---|---|
| Orchestrator 选错 skill | 在提问中明示领域名（如"用 bulkrna 跑..."） |
| LLM 无响应 | 检查 `.env` 的 `LLM_API_KEY` / `LLM_BASE_URL` |
| Skill 路由后参数缺失 | Orchestrator 会主动追问；按提示补 |

## 下一步阅读

- [技能系统](/docs/architecture/skill-system)
- [Bot 与生态](/docs/ecosystem/chat-bot)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/architecture/orchestrator.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/orchestrator.mdx
git commit -m "docs(arch): orchestrator page"
```

---

## Phase 4: 「七大组学」组（7 页）

### 通用模板（领域页专用，每页都遵循）

```mdx
---
title: "<中文领域名> - <英文 slug> · <N> skills"
description: "<一句话描述本领域解决的问题与覆盖的技术>"
keywords: [<领域关键词>]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

<!-- 一段（150-200 字），从 skills/<domain>/INDEX.md 顶部提取 -->

## 典型分析流程 ASCII 图

<!-- 3-6 步的 pipeline 框图 -->

## 关键 skill 列表

<!-- 表格：skill 名 / 一行说明 / 一行 CLI / SKILL.md 链接 -->
<!-- 必须包含 CLAUDE.md Skill Routing Table 中本领域的 "Key skills" -->

## 何时不适用本领域

<!-- bullet 列表：3-5 项数据形态/问题类型上的边界 -->

## 下一步阅读

- [整体架构](/docs/architecture/overview)
- [编排器](/docs/architecture/orchestrator)
- [<相邻领域 1>]
- [<相邻领域 2>]
```

---

### Task 10: `docs/domains/spatial.mdx`

**Files:**
- Create: `docs/domains/spatial.mdx`

**Source materials:**
- `skills/spatial/INDEX.md`
- `CLAUDE.md` 中 spatial 的 Key skills 列表
- `skills/spatial-preprocess/SKILL.md`、`skills/spatial-domains/SKILL.md`（看代表性 skill 接口）

**N skills:** 17

- [ ] **Step 1: 写入文件**

```mdx
---
title: "空间转录组 - spatial · 17 skills"
description: "Visium / Xenium / MERFISH / Slide-seq 等空间转录组数据的端到端分析：QC、域识别、空间可变基因、解卷积、细胞通讯、轨迹与 CNV。"
keywords: ["空间转录组", "spatial transcriptomics", "Visium", "Xenium", "MERFISH"]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

<!--
  从 skills/spatial/INDEX.md 顶部 + CLAUDE.md spatial 段提取。
  必须覆盖：
  - 支持的平台（Visium / Xenium / MERFISH / Slide-seq）
  - 主要分析维度（QC / 域 / SVG / 解卷积 / 通讯 / 轨迹 / CNV）
  - 为什么需要专门的"空间"分析（与单细胞的区别）
  150-200 字。
-->

## 典型分析流程 ASCII 图

```
原始数据 (h5ad / 10x output)
   │
   ▼
spatial-preprocess     ← QC + 标准化 + HVG + PCA + UMAP
   │
   ▼
spatial-domains        ← 空间域识别 (leiden / SpaGCN / ...)
   │
   ├─→ spatial-de              ← 各域 marker 基因
   ├─→ spatial-genes           ← 空间可变基因 (SVG)
   ├─→ spatial-deconv          ← 细胞类型解卷积
   ├─→ spatial-communication   ← 配体-受体细胞通讯
   ├─→ spatial-trajectory      ← 拟时序轨迹
   └─→ spatial-cnv             ← 拷贝数变异
```

## 关键 skill 列表

<!--
  从 skills/spatial/INDEX.md + CLAUDE.md spatial 段提取。
  表格 4 列：skill 名 / 一行说明 / 一行 CLI / SKILL.md 链接。
  至少列 8 个核心 skill，其他 9 个用一行总结收尾。
  CLI 直接从 CLAUDE.md CLI Reference 节抄。
  示例第一行：
  | spatial-preprocess | QC + 标准化 + HVG + PCA + UMAP | `python omicsclaw.py run spatial-preprocess --demo` | [SKILL.md](https://github.com/.../skills/spatial/spatial-preprocess/SKILL.md) |
-->

| Skill | 用途 | CLI 一行示例 | 文档 |
|---|---|---|---|
| spatial-preprocess | 预处理 + QC | `python omicsclaw.py run spatial-preprocess --demo` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/spatial/spatial-preprocess/SKILL.md) |
| spatial-domains | 空间域识别 | `python omicsclaw.py run spatial-domains --demo` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/spatial/spatial-domains/SKILL.md) |
| spatial-de | 差异表达 | `python omicsclaw.py run spatial-de --demo` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/spatial/spatial-de/SKILL.md) |
| spatial-deconv | 细胞类型解卷积 | `python omicsclaw.py run spatial-deconv ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/spatial/spatial-deconv/SKILL.md) |
| spatial-communication | 细胞通讯 | `python omicsclaw.py run spatial-communication ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/spatial/spatial-communication/SKILL.md) |

完整 17 个 skill 列表见 [`skills/spatial/INDEX.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/spatial/INDEX.md)。

## 何时不适用本领域

- **数据没有空间坐标**（如普通 scRNA-seq）→ 用 [singlecell 域](/docs/domains/singlecell)
- **bulk RNA-seq** → 用 [bulkrna 域](/docs/domains/bulkrna)
- **想做组织切片图像分析（H&E 分割）** → 当前 skill 不覆盖图像深度学习
- **DNA 层面的空间分析（spatial DNA-seq）** → 不在范围内

## 下一步阅读

- [整体架构](/docs/architecture/overview)
- [编排器](/docs/architecture/orchestrator)
- [单细胞组学](/docs/domains/singlecell)
- [Bulk RNA-seq](/docs/domains/bulkrna)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/domains/spatial.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/domains/spatial.mdx
git commit -m "docs(domain): spatial page"
```

---

### Task 11: `docs/domains/singlecell.mdx`

**Files:**
- Create: `docs/domains/singlecell.mdx`

**Source materials:**
- `skills/singlecell/INDEX.md`
- `CLAUDE.md` singlecell 段
- `skills/sc-preprocessing/SKILL.md` 或类似代表 skill

**N skills:** 30

- [ ] **Step 1: 写入文件**

```mdx
---
title: "单细胞组学 - singlecell · 30 skills"
description: "scRNA-seq + scATAC-seq 全流程：FASTQ→counts、QC、过滤、双细胞、归一化→HVG→PCA→UMAP→聚类、注释、DE、轨迹、velocity、GRN、细胞通讯。"
keywords: ["单细胞", "scRNA-seq", "scATAC-seq", "single-cell", "trajectory"]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

<!-- 150-200 字。从 skills/singlecell/INDEX.md 提取，覆盖：
  - scRNA + scATAC 双覆盖
  - 全流程：从 FASTQ 到生物学解读
  - 与 spatial 域的区别（无空间坐标，更注重细胞身份与轨迹）
-->

## 典型分析流程 ASCII 图

```
FASTQ
   │
   ▼
sc-fastq-to-counts    ← cellranger / STARsolo / kallisto
   │
   ▼
sc-preprocessing      ← QC + 双细胞 + 归一化 + HVG + PCA + UMAP + cluster
   │
   ├─→ sc-cell-annotation    ← 细胞类型注释（marker / scType / SingleR）
   ├─→ sc-de                  ← 差异表达
   ├─→ sc-batch-integration  ← 多样本整合（Harmony / scVI）
   ├─→ sc-pseudotime         ← 拟时序
   ├─→ sc-velocity           ← RNA velocity
   ├─→ sc-grn                ← 基因调控网络
   └─→ sc-ccc                ← 细胞通讯
```

## 关键 skill 列表

<!-- 表格 4 列：从 CLAUDE.md singlecell Key skills 抄。至少列 6-8 个，其余 22-24 个用一行收尾。 -->

| Skill | 用途 | CLI 一行示例 | 文档 |
|---|---|---|---|
| sc-preprocessing | 预处理 + 聚类 | `python omicsclaw.py run sc-preprocessing --demo` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/singlecell/sc-preprocessing/SKILL.md) |
| sc-cell-annotation | 细胞类型注释 | `python omicsclaw.py run sc-cell-annotation ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/singlecell/sc-cell-annotation/SKILL.md) |
| sc-de | 差异表达 | `python omicsclaw.py run sc-de ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/singlecell/sc-de/SKILL.md) |
| sc-batch-integration | 多样本整合 | `python omicsclaw.py run sc-batch-integration ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/singlecell/sc-batch-integration/SKILL.md) |
| sc-pseudotime | 拟时序 | `python omicsclaw.py run sc-pseudotime ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/singlecell/sc-pseudotime/SKILL.md) |

完整 30 个 skill 列表见 [`skills/singlecell/INDEX.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/singlecell/INDEX.md)。

## 何时不适用本领域

- **数据带空间坐标** → 用 [spatial 域](/docs/domains/spatial)
- **bulk RNA-seq** → 用 [bulkrna 域](/docs/domains/bulkrna)
- **想做 scDNA-seq / scBS-seq（甲基化）** → 当前 skill 不覆盖
- **CITE-seq 蛋白通道** → 部分 skill 支持，但不是主要场景

## 下一步阅读

- [空间转录组](/docs/domains/spatial)
- [Bulk RNA-seq](/docs/domains/bulkrna)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/domains/singlecell.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/domains/singlecell.mdx
git commit -m "docs(domain): singlecell page"
```

---

### Task 12: `docs/domains/genomics.mdx`

**Files:**
- Create: `docs/domains/genomics.mdx`

**Source materials:**
- `skills/genomics/INDEX.md`
- `CLAUDE.md` genomics 段

**N skills:** 10

- [ ] **Step 1: 写入文件**

```mdx
---
title: "基因组学 - genomics · 10 skills"
description: "Bulk DNA-seq 全流程：FASTQ QC、比对、SNV/Indel/SV/CNV calling、VCF 操作、变异注释、phasing、de novo 组装、ATAC/ChIP peak calling。"
keywords: ["genomics", "DNA-seq", "variant calling", "SNV", "SV", "CNV", "ATAC-seq", "ChIP-seq"]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

<!-- 150-200 字。覆盖：
  - bulk DNA-seq（不是 scDNA）
  - 主要任务：变异检测 + 注释 + peak calling
  - 与 bulkrna 的区别（DNA vs RNA）
-->

## 典型分析流程 ASCII 图

```
FASTQ (DNA-seq)
   │
   ▼
genomics-qc-align       ← FASTQ QC + BWA / minimap2 比对
   │
   ▼
┌─ SNV/Indel ─→ genomics-variant-calling   (GATK / DeepVariant)
├─ SV        ─→ genomics-sv-detection      (Manta / Delly)
├─ CNV       ─→ genomics-cnv-detection
├─ Peak      ─→ genomics-peak-calling      (MACS2)
└─ De novo   ─→ genomics-assembly
       │
       ▼
   genomics-variant-annotation  (VEP / SnpEff)
```

## 关键 skill 列表

<!-- 表格 4 列。从 CLAUDE.md genomics Key skills 抄。10 个 skill 全列也可以。 -->

| Skill | 用途 | CLI 一行示例 | 文档 |
|---|---|---|---|
| genomics-alignment | FASTQ 比对 | `python omicsclaw.py run genomics-alignment ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/genomics/genomics-alignment/SKILL.md) |
| genomics-variant-calling | SNV / Indel 检测 | `python omicsclaw.py run genomics-variant-calling ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/genomics/genomics-variant-calling/SKILL.md) |
| genomics-variant-annotation | 变异注释 | `python omicsclaw.py run genomics-variant-annotation ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/genomics/genomics-variant-annotation/SKILL.md) |
| genomics-sv-detection | 结构变异 | `python omicsclaw.py run genomics-sv-detection ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/genomics/genomics-sv-detection/SKILL.md) |

完整 10 个 skill 列表见 [`skills/genomics/INDEX.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/genomics/INDEX.md)。

## 何时不适用本领域

- **RNA 层面分析** → 用 [bulkrna](/docs/domains/bulkrna) 或 [singlecell](/docs/domains/singlecell)
- **scDNA-seq（单细胞 DNA）** → 不覆盖
- **群体遗传学（GWAS / 系统发育）** → 不覆盖
- **元基因组** → 不覆盖

## 下一步阅读

- [Bulk RNA-seq](/docs/domains/bulkrna)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/domains/genomics.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/domains/genomics.mdx
git commit -m "docs(domain): genomics page"
```

---

### Task 13: `docs/domains/proteomics.mdx`

**Files:**
- Create: `docs/domains/proteomics.mdx`

**Source materials:**
- `skills/proteomics/INDEX.md`
- `CLAUDE.md` proteomics 段

**N skills:** 8

- [ ] **Step 1: 写入文件**

```mdx
---
title: "蛋白组学 - proteomics · 8 skills"
description: "质谱蛋白组学：raw MS QC、肽段/蛋白鉴定、LFQ/TMT/DIA 定量、差异丰度、PTM 分析、通路富集。"
keywords: ["proteomics", "蛋白组学", "mass spec", "TMT", "DIA", "LFQ", "PTM"]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

<!-- 150-200 字。覆盖：MS 数据 → 肽段 → 蛋白 → 定量 → 差异 → 富集的全链。 -->

## 典型分析流程 ASCII 图

```
原始 MS 数据 (.raw / .mzML)
   │
   ▼
proteomics-ms-qc           ← MS 质量控制
   │
   ▼
proteomics-identification  ← 肽段 / 蛋白鉴定 (MaxQuant / DIA-NN)
   │
   ▼
proteomics-quantification  ← LFQ / TMT / DIA 定量
   │
   ├─→ proteomics-de          ← 差异丰度
   ├─→ proteomics-ptm         ← 翻译后修饰分析
   └─→ proteomics-enrichment  ← 通路富集
```

## 关键 skill 列表

| Skill | 用途 | CLI 一行示例 | 文档 |
|---|---|---|---|
| proteomics-identification | 肽段 / 蛋白鉴定 | `python omicsclaw.py run proteomics-identification ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/proteomics/proteomics-identification/SKILL.md) |
| proteomics-quantification | 定量 (LFQ/TMT/DIA) | `python omicsclaw.py run proteomics-quantification ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/proteomics/proteomics-quantification/SKILL.md) |
| proteomics-de | 差异丰度 | `python omicsclaw.py run proteomics-de ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/proteomics/proteomics-de/SKILL.md) |
| proteomics-enrichment | 通路富集 | `python omicsclaw.py run proteomics-enrichment ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/proteomics/proteomics-enrichment/SKILL.md) |

完整 8 个 skill 列表见 [`skills/proteomics/INDEX.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/proteomics/INDEX.md)。

## 何时不适用本领域

- **基于抗体的蛋白定量（Olink / SOMAscan）** → 不覆盖
- **结构生物学（晶体 / cryo-EM）** → 不覆盖
- **代谢组（小分子）** → 用 [metabolomics](/docs/domains/metabolomics)

## 下一步阅读

- [代谢组学](/docs/domains/metabolomics)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/domains/proteomics.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/domains/proteomics.mdx
git commit -m "docs(domain): proteomics page"
```

---

### Task 14: `docs/domains/metabolomics.mdx`

**Files:**
- Create: `docs/domains/metabolomics.mdx`

**Source materials:**
- `skills/metabolomics/INDEX.md`
- `CLAUDE.md` metabolomics 段

**N skills:** 8

- [ ] **Step 1: 写入文件**

```mdx
---
title: "代谢组学 - metabolomics · 8 skills"
description: "LC-MS 代谢组学：XCMS 预处理、峰检测、代谢物注释（SIRIUS/GNPS）、归一化、差异分析、通路富集。"
keywords: ["metabolomics", "代谢组学", "LC-MS", "XCMS", "SIRIUS", "GNPS"]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

<!-- 150-200 字。覆盖：LC-MS 数据 → 峰 → 注释 → 差异 → 通路。 -->

## 典型分析流程 ASCII 图

```
LC-MS 原始数据 (.mzML)
   │
   ▼
metabolomics-peak-detection   ← XCMS 峰检测
   │
   ▼
metabolomics-annotation       ← 代谢物注释 (SIRIUS / GNPS)
   │
   ▼
metabolomics-normalization    ← 归一化
   │
   ├─→ metabolomics-de
   └─→ metabolomics-pathway-enrichment
```

## 关键 skill 列表

| Skill | 用途 | CLI 一行示例 | 文档 |
|---|---|---|---|
| metabolomics-peak-detection | 峰检测 | `python omicsclaw.py run metabolomics-peak-detection ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/metabolomics/metabolomics-peak-detection/SKILL.md) |
| metabolomics-annotation | 代谢物注释 | `python omicsclaw.py run metabolomics-annotation ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/metabolomics/metabolomics-annotation/SKILL.md) |
| metabolomics-de | 差异分析 | `python omicsclaw.py run metabolomics-de ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/metabolomics/metabolomics-de/SKILL.md) |
| metabolomics-pathway-enrichment | 通路富集 | `python omicsclaw.py run metabolomics-pathway-enrichment ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/metabolomics/metabolomics-pathway-enrichment/SKILL.md) |

完整 8 个 skill 列表见 [`skills/metabolomics/INDEX.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/metabolomics/INDEX.md)。

## 何时不适用本领域

- **GC-MS（气相色谱）** → 部分 skill 可用，但主要为 LC-MS 设计
- **NMR 代谢组** → 不覆盖
- **空间代谢组（MALDI imaging）** → 不覆盖
- **蛋白组** → 用 [proteomics](/docs/domains/proteomics)

## 下一步阅读

- [蛋白组学](/docs/domains/proteomics)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/domains/metabolomics.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/domains/metabolomics.mdx
git commit -m "docs(domain): metabolomics page"
```

---

### Task 15: `docs/domains/bulkrna.mdx`

**Files:**
- Create: `docs/domains/bulkrna.mdx`

**Source materials:**
- `skills/bulkrna/INDEX.md`
- `CLAUDE.md` bulkrna 段（含完整 CLI Reference）

**N skills:** 13

- [ ] **Step 1: 写入文件**

```mdx
---
title: "Bulk RNA-seq - bulkrna · 13 skills"
description: "Bulk RNA-seq 全流程：FASTQ QC、比对、计数 QC、DE（DESeq2/edgeR）、富集、剪接、WGCNA、解卷积、PPI、生存分析、TrajBlend bulk-to-sc。"
keywords: ["bulk RNA-seq", "DESeq2", "差异表达", "WGCNA", "deconvolution", "survival"]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

<!-- 150-200 字。覆盖：从 FASTQ 到生存分析的完整 bulk RNA pipeline。 -->

## 典型分析流程 ASCII 图

```
FASTQ
   │
   ▼
bulkrna-read-qc           ← FASTQ QC
   │
   ▼
bulkrna-read-alignment    ← STAR / HISAT2 → counts
   │
   ▼
bulkrna-qc                ← 计数矩阵 QC
   │
   ├─→ bulkrna-batch-correction   ← 批次效应校正
   ├─→ bulkrna-de                  ← 差异表达 (DESeq2)
   ├─→ bulkrna-splicing            ← 可变剪接
   ├─→ bulkrna-coexpression        ← WGCNA 共表达网络
   ├─→ bulkrna-deconvolution       ← bulk → 细胞类型比例
   ├─→ bulkrna-enrichment          ← 通路富集
   ├─→ bulkrna-ppi-network         ← PPI 网络
   ├─→ bulkrna-survival            ← 生存分析
   └─→ bulkrna-trajblend           ← bulk → sc 轨迹插值
```

## 关键 skill 列表

| Skill | 用途 | CLI 一行示例 | 文档 |
|---|---|---|---|
| bulkrna-de | 差异表达 (DESeq2) | `python omicsclaw.py run bulkrna-de --demo` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/bulkrna/bulkrna-de/SKILL.md) |
| bulkrna-enrichment | 通路富集 | `python omicsclaw.py run bulkrna-enrichment ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/bulkrna/bulkrna-enrichment/SKILL.md) |
| bulkrna-coexpression | WGCNA | `python omicsclaw.py run bulkrna-coexpression --demo` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/bulkrna/bulkrna-coexpression/SKILL.md) |
| bulkrna-deconvolution | 细胞解卷积 | `python omicsclaw.py run bulkrna-deconvolution ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/bulkrna/bulkrna-deconvolution/SKILL.md) |
| bulkrna-survival | 生存分析 | `python omicsclaw.py run bulkrna-survival ...` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/bulkrna/bulkrna-survival/SKILL.md) |

完整 13 个 skill 列表见 [`skills/bulkrna/INDEX.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/bulkrna/INDEX.md)。

## 何时不适用本领域

- **单细胞数据** → 用 [singlecell](/docs/domains/singlecell)
- **空间转录组** → 用 [spatial](/docs/domains/spatial)
- **DNA-seq** → 用 [genomics](/docs/domains/genomics)
- **小 RNA / lncRNA 专门分析** → 部分 skill 可用，但非主场景

## 下一步阅读

- [单细胞组学](/docs/domains/singlecell)
- [基因组学](/docs/domains/genomics)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/domains/bulkrna.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/domains/bulkrna.mdx
git commit -m "docs(domain): bulkrna page"
```

---

### Task 16: `docs/domains/orchestrator.mdx`

**Files:**
- Create: `docs/domains/orchestrator.mdx`

**Source materials:**
- `skills/orchestrator/INDEX.md`

**N skills:** 2

注：此页内容与架构页 `architecture/orchestrator.mdx` 有重叠但视角不同——架构页讲"orchestrator 是什么 / 怎么工作"，本页讲"作为 skill 域它包含哪些具体 skill"。

- [ ] **Step 1: 写入文件**

```mdx
---
title: "编排域 - orchestrator · 2 skills"
description: "Orchestrator 作为元领域，包含 2 个 meta skill：orchestrator（多组学查询路由）和 omics-skill-builder（skill 脚手架）。"
keywords: ["orchestrator", "skill builder", "meta skills"]
og:image: "/docs/images/og-cover.png"
---

## 本领域解决什么问题

Orchestrator 域是 OmicsClaw 的"元领域"——它本身不做组学分析，而是提供两个支撑性 skill：
- **orchestrator** 把用户的自然语言问题映射到 6 个分析领域之一并触发对应 skill
- **omics-skill-builder** 帮助开发者按 OmicsClaw 规范快速搭建新 skill

为什么要把它列为一个独立的 "domain"：保持 skill 注册表的对称性（每个 skill 必属于某个 domain），且让用户能在 `omicsclaw.py list` 中看到这两个 meta skill。

## 典型使用流程 ASCII 图

```
开发者新增 skill：
   omics-skill-builder
        │
        ▼
   生成 skills/<domain>/<new-skill>/{SKILL.md, <slug>.py}
        │
        ▼
   写入实现 + commit

用户跑分析：
   自然语言提问
        │
        ▼
   orchestrator → 路由到具体 skill
```

## 关键 skill 列表

| Skill | 用途 | CLI 一行示例 | 文档 |
|---|---|---|---|
| orchestrator | 多组学查询路由 | (作为 LLM agent 内部调用，无独立 CLI) | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/orchestrator/orchestrator/SKILL.md) |
| omics-skill-builder | Skill 脚手架生成器 | `python omicsclaw.py run omics-skill-builder --name <new>` | [SKILL.md](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/orchestrator/omics-skill-builder/SKILL.md) |

完整列表见 [`skills/orchestrator/INDEX.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/skills/orchestrator/INDEX.md)。

## 何时不适用本领域

- **直接想跑分析** → 用 6 个分析领域之一，本域是元工具
- **想改 orchestrator 路由逻辑** → 看代码 `omicsclaw/orchestrator/`，本 skill 文档不覆盖内部修改

## 下一步阅读

- [架构 · 编排器原理](/docs/architecture/orchestrator)
- [架构 · 技能系统](/docs/architecture/skill-system)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/domains/orchestrator.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/domains/orchestrator.mdx
git commit -m "docs(domain): orchestrator page"
```

---

## Phase 5: 「工程能力」组（3 页）

### Task 17: `docs/engineering/replot.mdx`

**Files:**
- Create: `docs/engineering/replot.mdx`

**Source materials:**
- `CLAUDE.md` 的 "Re-rendering Plots (replot)" 节（主要参考源，几乎可直接用）
- `docs/_legacy/R-DEPENDENCIES.md`（R 依赖背景）

**Page type:** "工程能力"页

- [ ] **Step 1: 写入文件**

```mdx
---
title: "R Enhanced 重绘 - 不重跑分析也能调图"
description: "Replot 让你在 skill 跑完后调整 R Enhanced 图的参数（top-N、字号、配色）而无需重跑底层分析，复用已存的 figure_data。"
keywords: ["replot", "R Enhanced", "ggplot2", "figure 重绘"]
og:image: "/docs/images/og-cover.png"
---

## 为什么需要 replot

<!--
  从 CLAUDE.md "Re-rendering Plots (replot)" 节顶部翻译/扩写。覆盖：
  - skill 跑一次很慢；改个图样式就得重跑代价不合理
  - 把"出图"和"算"解耦：skill 算 → 出标准图 + figure_data → replot 拿 figure_data 出 R 增强图
  - 三层可视化流（首跑 / R Enhanced / 参数微调）
-->

## 启用前 / 启用后

| 维度 | 没有 replot | 有 replot |
|---|---|---|
| 改 top-N | 重跑整个 skill | `replot --top-n 30` 秒级 |
| 改配色 | 改源代码 | `replot --palette ...` |
| 同一份分析多种图 | 拷贝代码改 | `replot --renderer ...` |

## CLI 示例

<!-- 直接从 CLAUDE.md 的 Replot CLI 节抄，给 4-5 个最常用的命令 -->

```bash
# 重绘所有 R Enhanced 图
python omicsclaw.py replot sc-de --output /path/to/output/

# 列出可调参数
python omicsclaw.py replot sc-de --output /path/to/output/ --list-renderers

# 微调单个 renderer
python omicsclaw.py replot sc-de --output /path/to/output/ --renderer plot_de_volcano --top-n 30 --dpi 300
```

## 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `replot` 报找不到 figure_data | skill 没生成 figure_data 目录 | 检查首跑是否成功 |
| R 报缺包 | R Enhanced 依赖未装 | 见归档 [`R-DEPENDENCIES.md`](https://github.com/zhou-1314/OmicsClaw/blob/main/docs/_legacy/R-DEPENDENCIES.md) |
| `--top-n` 不生效 | 该 renderer 不接受此参数 | 用 `--list-renderers` 确认 |

## 下一步阅读

- [整体架构](/docs/architecture/overview)
- [Memory 系统](/docs/engineering/memory)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/engineering/replot.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/engineering/replot.mdx
git commit -m "docs(eng): replot page"
```

---

### Task 18: `docs/engineering/memory.mdx`

**Files:**
- Create: `docs/engineering/memory.mdx`

**Source materials:**
- `docs/_legacy/MEMORY_SYSTEM.md`（主要源，需翻译为中文）

**Page type:** "工程能力"页

- [ ] **Step 1: 写入文件**

```mdx
---
title: "Memory 系统 - 让 OmicsClaw 记住你"
description: "OmicsClaw 用两层 memory：会话级（短期上下文）+ 持久级（跨会话偏好）。两者各自的写入触发与读取时机。"
keywords: ["memory", "持久化", "用户偏好", "OmicsClaw memory"]
og:image: "/docs/images/og-cover.png"
---

## 为什么需要 Memory

<!--
  从 docs/_legacy/MEMORY_SYSTEM.md 顶部翻译。3 段：
  1) Agent 跨会话不能"失忆"
  2) 但又不能把所有对话塞进每次提示
  3) 所以分两层：当下会话 vs 跨会话偏好/项目知识
-->

## 启用前 / 启用后

| 场景 | 无 memory | 有 memory |
|---|---|---|
| 第二次会话用户偏好 | 重新设置 | 自动恢复 |
| 多 skill 串联中间状态 | 用户手动传参 | 自动注入 |
| 跨项目复用经验 | 每次重新教 | 持久 |

## 两层 memory 架构

<!--
  从 _legacy/MEMORY_SYSTEM.md 提取。要画出：
  - Layer 1: session memory（in-process, ephemeral）
  - Layer 2: persistent memory（文件系统持久化，按 user / project 分）
  ASCII 框图风格。
-->

## 写入与读取触发时机

<!-- 表格：触发事件 / 写入哪一层 / 由谁触发 -->

## 故障排查

<!-- 3-5 行常见问题表 -->

## 下一步阅读

- [整体架构](/docs/architecture/overview)
- [远程执行模式](/docs/engineering/remote-execution)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/engineering/memory.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/engineering/memory.mdx
git commit -m "docs(eng): memory page"
```

---

### Task 19: `docs/engineering/remote-execution.mdx`

**Files:**
- Create: `docs/engineering/remote-execution.mdx`

**Source materials:**
- `docs/_legacy/remote-connection-guide.md`（本就是中文，可直接迁移 + 适配 frontmatter）

**Page type:** "工程能力"页

- [ ] **Step 1: 读取归档原文，作为正文起点**

```bash
cat docs/_legacy/remote-connection-guide.md
```

- [ ] **Step 2: 写入新页（frontmatter + 套模板的 4 节，正文搬运/精简自归档原文）**

```mdx
---
title: "远程执行模式 - 把分析放到远端服务器"
description: "OmicsClaw-App 支持 UI 留本地、计算放远端 Linux 服务器的分离架构，通过 SSH bootstrap 完成首次部署。"
keywords: ["远程执行", "remote", "SSH", "OmicsClaw-App", "分离部署"]
og:image: "/docs/images/og-cover.png"
---

## 为什么需要远程执行

<!--
  从 docs/_legacy/remote-connection-guide.md 引言段提取。
  要点：
  - 本地机器算力不够（GPU / 内存）
  - 数据已经在远端服务器
  - 多人共享一台服务器
-->

## 启用前 / 启用后架构对比

<!-- 两幅 ASCII 图：本地全栈 vs 远程分离 -->

```
本地全栈:                          远程分离:
┌────────┐                        ┌────────┐         ┌──────────┐
│ App UI │                        │ App UI │ ──SSH──▶│ Server   │
│   +    │                        │ (本地) │         │  skills  │
│ skills │                        └────────┘         │  + data  │
└────────┘                                           └──────────┘
```

## 配置步骤

<!--
  从归档文档抄实际配置步骤（remote_bootstrap_command 等字段）。
  必须能让用户从零接通一台远端服务器。
-->

## 故障排查

<!-- 3-5 行常见问题表，从归档文档抄 -->

## 下一步阅读

- [OmicsClaw-App 桌面端](/docs/ecosystem/omicsclaw-app)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 3: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/engineering/remote-execution.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add docs/engineering/remote-execution.mdx
git commit -m "docs(eng): remote-execution page"
```

---

## Phase 6: 「Bot 与生态」组（2 页）

### Task 20: `docs/ecosystem/chat-bot.mdx`

**Files:**
- Create: `docs/ecosystem/chat-bot.mdx`

**Source materials:**
- `bot/README.md`
- `CLAUDE.md` 的 "Bot Frontends (Telegram + Feishu)" 节（含 Makefile 命令）
- `SOUL.md`（Bot 人格）

**Page type:** "工程能力"页

- [ ] **Step 1: 写入文件**

```mdx
---
title: "聊天机器人 - Telegram + Feishu"
description: "OmicsClaw 提供 Telegram 与 Feishu 双通道聊天机器人，共享 LLM 工具调用核心，复用 88 个 skill。"
keywords: ["Telegram bot", "Feishu", "飞书", "聊天机器人", "LLM agent"]
og:image: "/docs/images/og-cover.png"
---

## 为什么需要 Bot 通道

<!--
  从 bot/README.md 顶部 + CLAUDE.md Bot 节提取。3 段：
  1) 不是所有用户都用命令行
  2) 群聊场景（实验室共享一个 bot）
  3) 移动端访问
-->

## 启用前 / 启用后

| 维度 | 仅 CLI | 加 Bot |
|---|---|---|
| 远程访问 | SSH 进服务器 | 直接发消息 |
| 群协作 | 无 | 群里 @bot |
| 移动端 | 无 | 手机随时发 |

## 启动命令

```bash
# Telegram
python -m bot.run --channels telegram
# or
make bot-telegram

# Feishu
python -m bot.run --channels feishu
# or
make bot-feishu
```

## 配置环境变量

<!-- 表格：变量名 / 用途 / 在哪获取。从 CLAUDE.md "Required environment variables" 节抄 -->

| 变量 | 用途 | 来源 |
|---|---|---|
| `LLM_API_KEY` | OpenAI 兼容 API key | OpenAI / 自托管 LLM 服务 |
| `LLM_BASE_URL` | LLM 端点（非 OpenAI 时） | 自填 |
| `TELEGRAM_BOT_TOKEN` | Telegram only | @BotFather |
| `FEISHU_APP_ID` + `FEISHU_APP_SECRET` | Feishu only | 飞书开发者后台 |

## 故障排查

| 症状 | 解决 |
|---|---|
| Bot 启动后无响应 | 检查 `.env` 是否存在且变量齐全 |
| Bot 路由 skill 出错 | 用 CLI 单独跑该 skill 验证非 Bot 问题 |
| 图片识别不准 | 当前图像理解能力有限，建议同时附文字说明 |

## 下一步阅读

- [OmicsClaw-App 桌面端](/docs/ecosystem/omicsclaw-app)
- [编排器](/docs/architecture/orchestrator)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/ecosystem/chat-bot.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/ecosystem/chat-bot.mdx
git commit -m "docs(eco): chat-bot page"
```

---

### Task 21: `docs/ecosystem/omicsclaw-app.mdx`

**Files:**
- Create: `docs/ecosystem/omicsclaw-app.mdx`

**Source materials:**
- `frontend/` 目录现状（看 README 或 package.json）
- `website/README.md`
- `docs/_legacy/remote-connection-guide.md`（App 与远程模式的关系）

**Page type:** "工程能力"页

- [ ] **Step 1: 先调研 frontend / website 实际形态**

```bash
ls frontend/ 2>/dev/null && cat frontend/README.md 2>/dev/null | head -30
ls website/
cat website/README.md | head -30
```

- [ ] **Step 2: 写入文件（基于上一步调研结果填实正文）**

```mdx
---
title: "OmicsClaw-App 桌面端 - 本地 GUI 与聊天面板"
description: "OmicsClaw-App 是基于 Next.js / Electron 的本地桌面应用，提供聊天界面、结果浏览与可选的远程执行，与 CLI / Bot 共享同一套 skill 系统。"
keywords: ["OmicsClaw-App", "桌面端", "GUI", "Electron", "Next.js"]
og:image: "/docs/images/og-cover.png"
---

## 为什么有桌面端

<!--
  3 段：
  1) CLI 适合开发者，Bot 适合协作；桌面端适合"科研日常工作流"
  2) 结果浏览（图、表、报告）GUI 比终端友好
  3) 同一份 skill 系统，三种入口（CLI / Bot / App）共用
-->

## 启用前 / 启用后

<!-- 表格：CLI 用户 vs App 用户在 onboarding / 结果浏览 / 远程接入 上的体验差 -->

## 部署形态

<!--
  从 frontend/website README 提取。讲清楚：
  - App 与本仓库的关系（独立子项目？同仓库子目录？）
  - 本地全栈 vs 远程分离（链到 remote-execution）
  - 启动命令
-->

## 故障排查

<!-- 3-5 行常见问题；如调研后发现 App 尚未完整就标"开发中" -->

## 下一步阅读

- [聊天机器人](/docs/ecosystem/chat-bot)
- [远程执行模式](/docs/engineering/remote-execution)
```

- [ ] **Step 3: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/ecosystem/omicsclaw-app.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add docs/ecosystem/omicsclaw-app.mdx
git commit -m "docs(eco): omicsclaw-app page"
```

---

## Phase 7: 「安全」组（2 页）

### Task 22: `docs/safety/rules-and-disclaimer.mdx`

**Files:**
- Create: `docs/safety/rules-and-disclaimer.mdx`

**Source materials:**
- `CLAUDE.md` 的 "Safety Rules" 节（4 条规则）
- `SOUL.md`（如有 disclaimer 提及）

**Page type:** "工程能力"页

- [ ] **Step 1: 写入文件**

```mdx
---
title: "安全规则与免责声明"
description: "OmicsClaw 的 4 条核心安全规则：数据本地处理、强制免责声明、严守 SKILL.md 方法论、覆盖前警告。"
keywords: ["安全", "免责声明", "数据隐私", "OmicsClaw safety"]
og:image: "/docs/images/og-cover.png"
---

## 为什么需要明确的安全规则

<!--
  2-3 段。从 SOUL.md / CLAUDE.md 引用：
  - 基因数据不能外泄
  - 分析结果不构成医疗建议
  - LLM 可能幻觉，必须严守方法论
-->

## 4 条核心规则（必读）

<!-- 直接从 CLAUDE.md "Safety Rules" 节翻译，4 条都列。每条配一段说明为什么。 -->

1. **基因数据永不离开本机** —— 所有处理在本地完成。
2. **每份报告必含免责声明** —— "OmicsClaw 是用于多组学分析的研究与教育工具。它不是医疗器械，不提供临床诊断。在基于这些结果做决定前请咨询领域专家。"
3. **严守 SKILL.md 方法论** —— 不臆造生物信息学参数、阈值或基因关联。
4. **覆盖前警告** —— 写入既有报告目录前主动告知。

## 启用前 / 启用后

| 维度 | 无明确规则 | 有规则 |
|---|---|---|
| 数据外发风险 | 取决于工具 | 强制本地 |
| 报告法律责任 | 模糊 | 明示研究/教育用途 |
| 参数臆造 | 可能 | 强约束于 SKILL.md |

## 触发警告的情况

<!--
  3-5 个具体场景，例如：
  - 用户问的基因 / 通路在 SKILL.md 没覆盖
  - skill 输出目录非空
  - Bot 收到含个人信息的图像
-->

## 下一步阅读

- [数据隐私](/docs/safety/data-privacy)
- [整体架构](/docs/architecture/overview)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/safety/rules-and-disclaimer.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/safety/rules-and-disclaimer.mdx
git commit -m "docs(safety): rules-and-disclaimer page"
```

---

### Task 23: `docs/safety/data-privacy.mdx`

**Files:**
- Create: `docs/safety/data-privacy.mdx`

**Source materials:**
- `CLAUDE.md` Safety Rules 节
- `docs/_legacy/remote-connection-guide.md`（远程模式的数据流向）
- 全新撰写（无既有源覆盖此主题）

**Page type:** "工程能力"页

- [ ] **Step 1: 写入文件**

```mdx
---
title: "数据隐私 - 你的数据走过哪些路径"
description: "OmicsClaw 在本地、Bot、远程执行三种部署模式下，原始数据、中间产物、报告各自的存储位置与外发边界。"
keywords: ["数据隐私", "data privacy", "本地处理", "OmicsClaw privacy"]
og:image: "/docs/images/og-cover.png"
---

## 为什么这一页很重要

基因数据、临床代谢数据等都属于敏感信息。即使工具承诺"本地处理"，用户仍需要知道：
- 哪些数据真的不离开本机
- 哪些会在网络传输中暴露
- LLM 调用是否会把数据上传给云端

## 三种部署模式的数据路径

### 模式 1：纯本地 CLI

```
你的数据 → omicsclaw.py run → 本地 skill → 本地输出
                  ↓
              无网络调用
```

### 模式 2：Bot（Telegram / Feishu）

<!--
  画清楚：
  - 用户发的指令文本 → Bot 平台 → 本地 omicsclaw 进程
  - 用户上传的图像 → Bot 平台 → 本地（注意 Bot 平台缓存原图）
  - LLM 调用：仅指令意图理解，是否会把数据上传？说明 .env 中 LLM 端点决定
-->

### 模式 3：远程执行（OmicsClaw-App + 远端服务器）

<!--
  画清楚：
  - UI 在本地，数据上传到远端服务器（SSH）
  - 远端服务器是用户自己控制 → 等同于本地
  - 但 SSH 通道、密钥管理、服务器访问控制需用户自己保证
-->

## 启用前 / 启用后（与云端工具对比）

| 维度 | 云端 SaaS 分析平台 | OmicsClaw |
|---|---|---|
| 原始数据落点 | 平台服务器 | 本地（或用户自托管远端） |
| 模型推理 | 平台 GPU | 本地或用户配置的 LLM |
| 第三方共享 | 取决于条款 | 由用户自己决定 |

## 用户操作清单（你需要做的）

<!-- 5-7 项检查点，例如：
  - 用商业 LLM API 时，确认其数据不留存条款
  - Bot 的 .env 不要 commit
  - 远端服务器的 SSH 密钥单独保管
  - 报告分享前手动检查是否含病人 ID
-->

## 下一步阅读

- [安全规则与免责声明](/docs/safety/rules-and-disclaimer)
- [远程执行模式](/docs/engineering/remote-execution)
```

- [ ] **Step 2: frontmatter 校验**

```bash
python -c "import re; fm=re.match(r'^---\n(.*?)\n---', open('docs/safety/data-privacy.mdx').read(), re.DOTALL).group(1); assert all(k in fm for k in ['title','description','keywords','og:image']); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add docs/safety/data-privacy.mdx
git commit -m "docs(safety): data-privacy page"
```

---

## Phase 8: README 入口与最终验收

### Task 24: 在两份 README 顶部加文档站入口

**Files:**
- Modify: `README.md`
- Modify: `README_zh-CN.md`

- [ ] **Step 1: 读 `README.md` 现状**

```bash
head -20 README.md
```

- [ ] **Step 2: 在 logo 区块下、第一个章节标题之前插入 1 行链接**

用 Edit 工具把以下旧文匹配段（取自当前 head -20 的实际首章标题前）替换为新文：

```markdown
<!-- old_string: README.md 中第一个 ## 标题前一行 (示例：</div> 或空行) -->
<!-- new_string: 同样位置 + 新增一行 -->
```

实际操作：先用 `Read README.md` 看清楚 logo 块和第一节标题之间的内容，再用 `Edit` 在 logo 块结束、第一个 `##` 之前插入：

```
> 📖 **完整中文文档**：见 [`docs/`](docs/)（在仓库根目录跑 `npx mintlify dev` 本地预览）
```

- [ ] **Step 3: 同样方式处理 `README_zh-CN.md`**

- [ ] **Step 4: 校验两份 README 都包含新链接**

```bash
grep -c "npx mintlify dev" README.md README_zh-CN.md
```

Expected: 两个 `1`。

- [ ] **Step 5: Commit**

```bash
git add README.md README_zh-CN.md
git commit -m "docs(readme): link to Mintlify docs site"
```

---

### Task 25: 跑 `npx mintlify dev` 做完整渲染验证

**Files:** 无修改，仅验证。

注：本任务需要联网下载 Mintlify CLI。如执行环境无法联网，跳过此步并在最终交付备注中标明"未做 mintlify dev 验证"，转由后续阶段在能联网的机器上做。

- [ ] **Step 1: 启动 mintlify dev**

```bash
cd /workspace/algorithm/zhouwg_project/OmicsClaw
npx mintlify@latest dev
```

Expected: 终端输出形如
```
Your local preview is available at http://localhost:3000
```

无 `Error: ` / `schema validation failed` 类输出。

- [ ] **Step 2: 用 curl 抓首页与每个分组的第 1 页确认 HTTP 200**

在 mintlify dev 仍运行中，新开 shell：

```bash
for url in \
  http://localhost:3000/docs/introduction/what-is-omicsclaw \
  http://localhost:3000/docs/architecture/overview \
  http://localhost:3000/docs/domains/spatial \
  http://localhost:3000/docs/engineering/replot \
  http://localhost:3000/docs/ecosystem/chat-bot \
  http://localhost:3000/docs/safety/rules-and-disclaimer; do
  printf "%s → %s\n" "$url" "$(curl -s -o /dev/null -w '%{http_code}' "$url")"
done
```

Expected: 6 行全部以 `200` 结尾。

- [ ] **Step 3: 关停 mintlify dev**

`Ctrl-C` 或 `kill` 后台进程。

- [ ] **Step 4: 验收清单核对（spec § Acceptance Criteria）**

依次确认（用 `ls` / `git log` / `grep` 命令逐条核对）：

```bash
# 1. mint.json 存在且 JSON 合法
python -m json.tool mint.json > /dev/null && echo "1. OK"

# 2. 20 篇 mdx 全在
test $(find docs/{introduction,architecture,domains,engineering,ecosystem,safety} -name '*.mdx' | wc -l) -eq 20 && echo "2. OK"

# 3. 每篇 frontmatter 4 项齐全
python <<'PY'
import re, subprocess
files = subprocess.check_output(
    ['bash','-c','ls docs/{introduction,architecture,domains,engineering,ecosystem,safety}/*.mdx']
).decode().split()
for f in files:
    fm = re.match(r'^---\n(.*?)\n---', open(f).read(), re.DOTALL).group(1)
    assert all(k in fm for k in ['title','description','keywords','og:image']), f
print(f'3. OK ({len(files)} files)')
PY

# 4. _legacy 含 7 篇旧 MD + 1 篇新 README, 共 8 个 .md
test $(ls docs/_legacy/*.md | wc -l) -eq 8 && echo "4. OK (7 legacy + README)"
grep -q '"docs/_legacy/\*\*"' mint.json && echo "4. excludes OK"

# 5. README 含文档站入口
grep -q "npx mintlify dev" README.md && grep -q "npx mintlify dev" README_zh-CN.md && echo "5. OK"

# 6. 不该动的没动 (检查 Task 1 起始 commit 至今的 diff 是否触及禁区)
TASK1_PARENT=$(git log --format=%H -- docs/_legacy/README.md | tail -1)^
if [ -n "$TASK1_PARENT" ]; then
  CHANGED=$(git diff --name-only "$TASK1_PARENT"..HEAD -- website/ skills/ docs/superpowers/playbooks/ package.json 2>/dev/null)
  test -z "$CHANGED" && echo "6. OK (no forbidden paths touched)" || echo "6. FAIL - touched: $CHANGED"
else
  echo "6. SKIP (Task 1 commit not found, run after Task 1)"
fi
```

Expected: `1. OK`、`2. OK`、`3. OK (20 files)`、`4. OK (7 legacy + README)`、`4. excludes OK`、`5. OK`、`6.` 无 WARNING 或人工核对 git log 确认。

- [ ] **Step 5: 不做 commit（本任务零文件改动）**

如果验收发现问题，回到对应 task 修复后追加 commit。

---

## 完成

所有 25 个 task 完成后，OmicsClaw 仓库即拥有：
- 一份 `mint.json` 站点配置
- 20 篇中文 `.mdx`，按 6 个分组在导航中陈列
- 1 个归档目录 `docs/_legacy/`（7 篇旧 MD + README）
- 2 份 README 顶部入口链接
- 任何人可在仓库根目录跑 `npx mintlify dev` 本地预览

后续阶段可以承接：
- Logo SVG 化
- 单 skill 文档页（88 篇）
- 英文版（重启 brainstorming）
- Mintlify 平台部署 / 自托管
