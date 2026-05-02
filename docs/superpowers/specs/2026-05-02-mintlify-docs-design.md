# Mintlify 中文文档站 — Design

**Status:** Approved (2026-05-02)
**Scope:** OmicsClaw 仓库根目录 — 新增 Mintlify 站点配置 `mint.json` 与 `docs/` 下的 7 组共 20 篇 `.mdx`；不动 `website/`、不动 `skills/`、不动 CI。
**Inspiration:** `repo_learn/langcli/docs`（Claude Code Architecture Whitepaper）的 Mintlify 站点结构、frontmatter 范式、写作模板。

## Problem

OmicsClaw 现状：
- `docs/` 是松散的英文运维 / 架构 MD（`architecture.md`、`INSTALLATION.md`、`METHODS.md`、`R-DEPENDENCIES.md`、`MEMORY_SYSTEM.md`、`remote-connection-guide.md`、`skill-architecture.md`），面向开发者，不构成"用户文档"；
- `website/` 是 Vite + React + Tailwind 的落地页，与 docs 不互通，且未承载文档功能；
- 7 个组学领域共 88 个 skill 仅以 `skills/<domain>/INDEX.md` 形式存在，最终用户无法成体系地了解项目能力；
- 没有面向中文最终用户的"是什么 / 怎么用 / 如何安全使用"的入口体系。

`repo_learn/langcli/docs` 已用 Mintlify + 中文 `.mdx` 实现了一套"白皮书叙事"风格的文档站：导航分组按"读者认知路径"展开（开始 → 对话 → 工具 → 安全 → 上下文 → Agent → 扩展性 → 揭秘），每页用统一模板（一句话定义 → 对比表 → ASCII 框图 → 端到端示例 → "它不是什么"）。该结构可直接迁移到 OmicsClaw，并适配多组学领域。

## Goals

1. 在 OmicsClaw 根目录建立 Mintlify 文档站（`mint.json` + `docs/<group>/*.mdx`），共 20 篇页面，覆盖：开始 / 架构 / 七大组学 / 工程能力 / Bot 与生态 / 安全。
2. 写作风格、frontmatter、配色、导航分组与 langcli docs 同构，但配色改为生命科学常用的 sky-500 蓝绿系，与 OmicsClaw 落地页一致。
3. 中文单语，全部 `.mdx` 用中文撰写；frontmatter 的 `title / description / keywords / og:image` 四项必填。
4. 既有英文 `docs/*.md` 不删除，整体迁入 `docs/_legacy/` 作为开发者参考资料，并在 `mint.json` 的 `excludes` 字段中排除。
5. 本地可用 `npx mintlify dev` 在 OmicsClaw 根目录预览整站。

## Non-Goals

- 不为 88 个 skill 各自写专页（留给后续阶段）。
- 不做英文版（`mint.json` 不预留 `versions` / `locales` 字段，避免无效骨架）。
- 不写 cookbook / 教程 / 案例研究类文章，本期只稳「概念页」。
- 不改 `website/` React 落地页，不改任何 `skills/<domain>/SKILL.md`，不动 `docs/superpowers/`。
- 不接 CI / 不配自动部署。生产部署形态留给后续决策。
- 不引入新的 npm 依赖到 `package.json`；Mintlify CLI 仅用 `npx` 临时拉起，不写入 dependency。

## Architecture

### 目录结构

```
OmicsClaw/
├── mint.json                          ← 新增：Mintlify 站点配置
├── docs/
│   ├── logo/                          ← 新增
│   │   ├── light.svg
│   │   └── dark.svg
│   ├── favicon.svg                    ← 新增
│   ├── images/                        ← 既有，保留；新增 og-cover.png
│   │
│   ├── introduction/                  ← 新增（3 页）
│   │   ├── what-is-omicsclaw.mdx
│   │   ├── why-omicsclaw.mdx
│   │   └── quickstart.mdx
│   │
│   ├── architecture/                  ← 新增（3 页）
│   │   ├── overview.mdx
│   │   ├── skill-system.mdx
│   │   └── orchestrator.mdx
│   │
│   ├── domains/                       ← 新增（7 页）
│   │   ├── spatial.mdx
│   │   ├── singlecell.mdx
│   │   ├── genomics.mdx
│   │   ├── proteomics.mdx
│   │   ├── metabolomics.mdx
│   │   ├── bulkrna.mdx
│   │   └── orchestrator.mdx
│   │
│   ├── engineering/                   ← 新增（3 页）
│   │   ├── replot.mdx
│   │   ├── memory.mdx
│   │   └── remote-execution.mdx
│   │
│   ├── ecosystem/                     ← 新增（2 页）
│   │   ├── chat-bot.mdx
│   │   └── omicsclaw-app.mdx
│   │
│   ├── safety/                        ← 新增（2 页）
│   │   ├── rules-and-disclaimer.mdx
│   │   └── data-privacy.mdx
│   │
│   ├── _legacy/                       ← 既有 7 个英文 MD 整体迁入
│   │   ├── README.md                  ← 新增：说明归档原因 + 指引
│   │   ├── architecture.md
│   │   ├── INSTALLATION.md
│   │   ├── METHODS.md
│   │   ├── R-DEPENDENCIES.md
│   │   ├── MEMORY_SYSTEM.md
│   │   ├── remote-connection-guide.md
│   │   └── skill-architecture.md
│   │
│   └── superpowers/                   ← 不动
```

### `mint.json` 关键字段

```jsonc
{
  "$schema": "https://mintlify.com/schema.json",
  "name": "OmicsClaw 多组学 AI Agent",
  "logo": { "dark": "/docs/logo/dark.svg", "light": "/docs/logo/light.svg" },
  "favicon": "/docs/favicon.svg",
  "colors": {
    "primary": "#0EA5E9",              // sky-500
    "light":   "#38BDF8",              // sky-400
    "dark":    "#0284C7",              // sky-600
    "background": { "dark": "#0F172A", "light": "#FFFFFF" }
  },
  "metadata": {
    "og:image": "/docs/images/og-cover.png",
    "twitter:card": "summary_large_image"
  },
  "topbarCtaButton": {
    "type": "github",
    "url": "https://github.com/zhou-1314/OmicsClaw"
  },
  "search": { "prompt": "搜索 OmicsClaw 文档..." },
  "redirects": [
    { "source": "/docs", "destination": "/docs/introduction/what-is-omicsclaw" }
  ],
  "navigation": [ /* 见下节 */ ],
  "excludes": ["docs/_legacy/**", "docs/superpowers/**"],
  "footerSocials": { "github": "https://github.com/zhou-1314/OmicsClaw" }
}
```

**与 langcli `mint.json` 的差异**：
- `colors.primary` 由 amber `#D97706` 改为 sky `#0EA5E9`，与 OmicsClaw 落地页 Tailwind 配色一致，且避免被误认为 langcli 同源项目。
- `redirects` 把 `/docs` 重定向到 `introduction/what-is-omicsclaw`（langcli 用同样的模式重定向到 `/docs/introduction/what-is-claude-code`）。
- 站点名带"多组学 AI Agent"后缀，强化 SEO 与 OG 卡片表达。

### 导航分组（`navigation` 字段）

```
开始
  ├─ 什么是 OmicsClaw                       docs/introduction/what-is-omicsclaw
  ├─ 为什么需要 OmicsClaw                   docs/introduction/why-omicsclaw
  └─ 五分钟上手                             docs/introduction/quickstart

架构
  ├─ 整体架构                               docs/architecture/overview
  ├─ 技能系统                               docs/architecture/skill-system
  └─ 编排器（Orchestrator）                 docs/architecture/orchestrator

七大组学
  ├─ 空间转录组（spatial · 17 skills）       docs/domains/spatial
  ├─ 单细胞组学（singlecell · 30 skills）    docs/domains/singlecell
  ├─ 基因组学（genomics · 10 skills）        docs/domains/genomics
  ├─ 蛋白组学（proteomics · 8 skills）       docs/domains/proteomics
  ├─ 代谢组学（metabolomics · 8 skills）     docs/domains/metabolomics
  ├─ Bulk RNA-seq（bulkrna · 13 skills）     docs/domains/bulkrna
  └─ 编排（orchestrator · 2 skills）         docs/domains/orchestrator

工程能力
  ├─ R Enhanced 重绘                        docs/engineering/replot
  ├─ Memory 系统                            docs/engineering/memory
  └─ 远程执行模式                           docs/engineering/remote-execution

Bot 与生态
  ├─ 聊天机器人（Telegram + Feishu）         docs/ecosystem/chat-bot
  └─ OmicsClaw-App 桌面端                   docs/ecosystem/omicsclaw-app

安全
  ├─ 安全规则与免责声明                     docs/safety/rules-and-disclaimer
  └─ 数据隐私                               docs/safety/data-privacy
```

排序遵循读者认知曲线：**是什么 → 怎么搭 → 能做什么（按领域） → 怎么用得更顺 → 怎么用得放心**。

## Decisions

### 1. 写作模板（每页统一遵循）

frontmatter 四项必填：

```yaml
---
title: "<本页标题 - 副标题>"
description: "<一句话页面描述，<= 140 字，用于搜索/SEO/OG>"
keywords: ["<关键词 1>", "<关键词 2>", ...]
og:image: "/docs/images/og-cover.png"
---
```

页面正文按页面类型套模板（强制结构，但每节长度可弹性）：

| 区块 | "是什么"页 | 领域页 | 工程能力页 |
|---|---|---|---|
| 第一段 | 一句话定义（粗体） | 本领域解决什么问题 + 涵盖 N 个 skill | 本能力为什么需要、解决什么痛点 |
| 第二段 | 与同类工具对比表 | 典型分析流程 ASCII 框图 | 启用前 / 启用后对比 |
| 第三段 | 端到端示例（命令 + 输出片段） | 关键 skill 列表（表格，含 SKILL.md 链接 + 一行 CLI） | CLI 示例 + 截图占位 |
| 第四段 | "它不是什么" | 何时不适用本领域 | 故障排查 / FAQ |
| 收尾 | 下一步阅读链接（站内内链） | 同左 | 同左 |

**所有领域页强制带"典型分析流程 ASCII 框图"**，模仿 langcli `what-is-claude-code.mdx` 的入口流程图风格。

### 2. 内容来源映射（避免重复劳动）

| 新页 | 主要参考源 | 工作类型 |
|---|---|---|
| introduction/what-is-omicsclaw | `README_zh-CN.md` + `SOUL.md` | 摘录改写 |
| introduction/why-omicsclaw | `README_zh-CN.md` 动机段 | 重写 |
| introduction/quickstart | `docs/_legacy/INSTALLATION.md` + `0_setup_env.sh` | 翻译 + 精简 |
| architecture/overview | `docs/_legacy/architecture.md` | 翻译 |
| architecture/skill-system | `docs/_legacy/skill-architecture.md` | 翻译 |
| architecture/orchestrator | `skills/orchestrator/SKILL.md` | 摘录改写 |
| domains/spatial | `skills/spatial/INDEX.md` + 代表 skill 的 SKILL.md | 汇总 + 重写 |
| domains/singlecell | `skills/singlecell/INDEX.md` + 代表 skill | 同上 |
| domains/genomics | `skills/genomics/INDEX.md` + 代表 skill | 同上 |
| domains/proteomics | `skills/proteomics/INDEX.md` + 代表 skill | 同上 |
| domains/metabolomics | `skills/metabolomics/INDEX.md` + 代表 skill | 同上 |
| domains/bulkrna | `skills/bulkrna/INDEX.md` + 代表 skill | 同上 |
| domains/orchestrator | `skills/orchestrator/INDEX.md` | 重写 |
| engineering/replot | `CLAUDE.md` 的 replot 节 + `docs/_legacy/R-DEPENDENCIES.md` | 整合 |
| engineering/memory | `docs/_legacy/MEMORY_SYSTEM.md` | 翻译 |
| engineering/remote-execution | `docs/_legacy/remote-connection-guide.md`（本就中文） | 直接迁移 + 适配 frontmatter |
| ecosystem/chat-bot | `bot/README.md` + `CLAUDE.md` Bot 节 | 摘录改写 |
| ecosystem/omicsclaw-app | `frontend/` 现状 + `website/README.md` | 重写 |
| safety/rules-and-disclaimer | `CLAUDE.md` Safety Rules 节 | 翻译 + 扩写 |
| safety/data-privacy | 新写（基于"本地处理永不离线"原则 + remote 模式数据流向） | 全新 |

### 3. 旧文档归档而非删除

把既有 `docs/*.md` 的 7 篇英文文件整体 `git mv` 到 `docs/_legacy/`，并在该目录新建 `README.md` 说明：
- 这些是面向**贡献者 / 维护者**的内部参考；
- 面向最终用户的入口请看根 `mint.json` 站；
- 它们的内容已被新中文页吸收 / 翻译（给出新页 ↔ 旧页对应表）。

`mint.json` 的 `excludes` 字段把 `docs/_legacy/**` 排除在站外，确保不渲染。

### 4. 配色

`colors.primary = #0EA5E9`（sky-500，与 OmicsClaw `website/` Tailwind 配色一致）。
不沿用 langcli amber，避免视觉上被误认为同源项目。
其余颜色梯度（`light` / `dark` / `background.dark`）按 langcli 同结构填入对应 sky 色阶。

### 5. Logo

第一版直接复用 `docs/images/OmicsClaw_logo.jpeg`（Mintlify 支持位图），在 `mint.json` 的 `logo.dark` / `logo.light` 都填同一路径。
SVG 化（`docs/logo/light.svg` / `dark.svg`）作为后续 polishing，**不阻塞本期发布**。
`favicon.svg` 同理，第一版用现有 jpeg 转 PNG 占位。

### 6. 部署形态

- 本期**只提交代码到 git**，不绑定任何托管平台。
- 本地预览：在 OmicsClaw 根目录跑 `npx mintlify dev`（不写入 `package.json` dependency，不引入 npm install 流程）。
- 在根 `README.md` 与 `README_zh-CN.md` 顶部各加一行链接：
  - `📖 完整中文文档：docs/`（本地 `npx mintlify dev` 预览）

### 7. 不阻塞 / 不引入

- 不引入 npm 依赖到 `package.json`。
- 不接 CI、不配自动部署、不申请域名。
- 不动 `website/` 任何文件。
- 不动 `skills/` 下任何 SKILL.md。
- 不动 `docs/superpowers/`。

## Risks & Mitigations

| 风险 | 评估 | 应对 |
|---|---|---|
| Mintlify 是付费 SaaS，免费额度有限 | 低 | 站点本地静态预览免费；本期不绑定 mintlify.com 托管，付费不触发 |
| 旧英文 docs 归档后维护者找不到 | 中 | `docs/_legacy/README.md` 留指引；`CLAUDE.md` 加注脚指向 |
| 7 个领域页内容深浅不一（spatial 17 skills vs orchestrator 2 skills） | 低 | 模板强制统一结构；列表长度自然不同可接受 |
| Logo jpeg 直接放进 Mintlify 在 dark 模式可能视觉不佳 | 中 | 第一版接受；后续 polish 任务专门做 SVG |
| `docs/_legacy/remote-connection-guide.md` 与新 `engineering/remote-execution.mdx` 内容重复 | 中 | 新页是旧文翻译/适配后的"权威版"；旧文在 `_legacy/` 顶部加 frontmatter 注释指向新页 |
| 后续若要英文版需重做 `mint.json` 结构 | 低 | 接受。本期明确不预留英文骨架，避免无效复杂度（YAGNI） |

## Out of Scope (明确划界)

- ❌ 单 skill 文档页（88 页规模留给下一阶段）
- ❌ 英文版 / 双语切换
- ❌ Cookbook / 教程文章 / 案例研究
- ❌ 改动 `website/` 落地页
- ❌ 改动 `skills/` 任何 SKILL.md
- ❌ CI / 自动部署 / 域名
- ❌ Mintlify 平台账号申请
- ❌ Logo SVG 化（属后续 polishing）

## Acceptance Criteria

1. 在 OmicsClaw 根目录跑 `npx mintlify dev` 能正常拉起本地预览站，无 schema 报错。
2. 左侧导航出现 7 个分组共 20 个页面，全部可点开渲染中文内容。
3. 每页 frontmatter 含 `title / description / keywords / og:image` 四项，无空页占位。
4. `docs/_legacy/` 下 7 篇旧英文 MD 完整存在，`mint.json` 的 `excludes` 排除生效（站内搜索 / 导航不出现这些页面）。
5. 根 `README.md` 与 `README_zh-CN.md` 顶部含文档站入口指引。
6. `package.json` / CI 配置 / `website/` 任何文件 / `skills/` 任何 SKILL.md / `docs/superpowers/` 任何文件**未被改动**。

## Next Step

转交 `superpowers:writing-plans` 技能，把本设计拆成可执行的实施步骤计划。
