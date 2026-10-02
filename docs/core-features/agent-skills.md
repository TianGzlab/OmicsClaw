# Agent Skills —— 组学 Skill 体系

> Skill 是 OmicsClaw 与通用 coding agent 最大的区别：
> 7 个组学领域、90 个 skill，每个 skill 是一份 `SKILL.md` 方法学 + 一个可直接运行的 Python 脚本。
> 本文以 `omicsclaw/skills/`、`omicsclaw/entry/assembly.py`、`skills/` 语料与 `tests/skills/` 为唯一事实来源
> （2026-09-23 工作树实测）。

---

## 1. 设计原理：渐进式披露（Progressive Disclosure）

Skill 分两段交给模型：

- **每次渲染 system prompt 时**：只注入每个 skill 的 `name` + `description`（一行一个），即"skill 索引"；
- **模型需要时**：调用 `use_skill` 工具，按名字取回 `SKILL.md` 正文（frontmatter 之后的全部内容）**以及 skill 所在目录**。

这一取舍在 OmicsClaw 的语料上是被数字决定的（`load_skills("skills")` 实测）：

| 量 | 数值 |
|---|---|
| 被索引的 `SKILL.md` | 90 个，`skipped` 为空（另有 4 个 consensus skill 的 `SKILL.md` 改名为 `SKILL.md.disabled`，不被扫描） |
| `full` 索引正文（`prompt_body()`） | 29,357 字符（plan 0032 在 96 个 skill 时测得约 7.5k tokens） |
| `compact` 索引正文（`prompt_body(compact=True)`） | 2,105 字符（约 550 tokens） |
| 全部正文之和 | 440,733 字符（约 125k tokens） |
| 全量扫描耗时 | 约 20 ms |

把 90 份正文全部塞进 prompt 需要约 125k tokens，已超过许多模型的上下文；索引只需其 6% 左右。

第二段拿到的不只是方法学文本：OmicsClaw 的 skill **自带脚本**，
所以 `use_skill` 还会把 skill 目录告诉模型，模型随后用 `bash` 直接执行脚本（见 §9）。
"Skill = 方法学 + 可执行代码"是这个体系的核心定位。

---

## 2. 架构总览

```
                      skills/<domain>/.../<skill>/SKILL.md   (90 个，磁盘上)
                                    │  只读 frontmatter
                                    ▼
             omicsclaw.skills.load_skills(root) ──► SkillIndex (不可变快照)
                                    │
          entry/assembly.py: build_skill_index(config)   ← 每个 build_app 只扫描一次
                    │                                   │
                    ▼                                   ▼
   _skills_section(config, index)            use_skill_tool(index)
   Section("skills", "## Available skills")  挂到 ToolRegistry（foundation_tools 第 7 个）
                    │                                   │
                    ▼                                   │
   PromptAssembler 每轮 render：                         │
   OMICSCLAW.md → safety → tool guidance                │
   → [planning] → [sandbox] → **skills** → environment  │
   → [long-term memory]                                 │
                    │                                   │
                    ▼                                   ▼
        模型看到索引，判断需要 spatial-preprocess ──► tool_use: use_skill{"skill_name": ...}
                                                        │
                                   SKILL.md 正文 + "---\nSkill directory: skills/spatial/spatial-preprocess"
                                                        │
                                                        ▼
                   bash: python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output ...
                                                        │
                                                        ▼
                 输出目录：report.md / result.json / figures/ / tables/ / processed.h5ad ...
                 （由 skills/_sdk 的 result/report 等"科学层"写出）
```

| 组件 | 代码位置 | 职责 |
|---|---|---|
| `Frontmatter` / `parse_frontmatter` | `omicsclaw/skills/frontmatter.py` | 一个明确声明的 YAML 子集解析器，不依赖任何 YAML 库 |
| `Skill` | `omicsclaw/skills/skill.py` | 一个 `SKILL.md` 的元数据记录（正文未读） |
| `load_skills` / `SkillLoadError` / `SKILL_FILENAME` | `omicsclaw/skills/loader.py` | 递归扫描目录树，建立索引 |
| `SkillIndex` / `SkillNotFound` / `SkipReason` / `SkippedSkill` | `omicsclaw/skills/index.py` | 索引渲染、查找、搜索、懒加载正文 |
| `use_skill_tool` / `USE_SKILL_SCHEMA` / `USE_SKILL_TOOL_NAME` | `omicsclaw/skills/use_skill.py` | `use_skill` 工具 |
| `build_skill_index` / `_skills_section` / `foundation_tools` / `default_sections` | `omicsclaw/entry/assembly.py` | 组合根：扫描一次，同时喂给 prompt 与工具 |
| `SkillsIndex` / `AppConfig.skills_dir` / `AppConfig.skills_index` | `omicsclaw/entry/config.py` | 部署开关 `full` / `compact` / `off` 与扫描根目录 |
| `Repl._skills` | `omicsclaw/entry/cli/_repl.py` | CLI 的 `/skills [query]` |
| `skills._sdk.*` | `skills/_sdk/` | skill 脚本共用的"科学层"（报告、`result.json`、校验和、R 调用、依赖表）；skill 不再导入 `omicsclaw.common` |
| `skills/<domain>/INDEX.md` | 语料 | 每个领域的人读索引，由测试保证与 `SKILL.md` 同步 |

**分层约束**：`omicsclaw.skills` 在 `omicsclaw` 命名空间内只允许导入 `omicsclaw.schema` 与 `omicsclaw.tools`
（`use_skill` 需要声明自己的 `ToolPolicy`）。它不导入 `omicsclaw.context`——返回 `Section` 会让两个叶子层互相依赖，
二者由组合根一行代码接起来。`tests/skills/test_skills_is_a_leaf_layer.py` 在子进程里真实导入本包并检查
`sys.modules`，同时确认它没有碰到已删除的 `omicsclaw.skill`（单数，旧 skill 系统，仅差一个字母）。

---

## 3. 目录结构

### 3.1 一个 skill 的形状

一个 skill 就是一个包含 `SKILL.md` 的目录，旁边放它需要的一切：

```
skills/spatial/spatial-preprocess/
├── SKILL.md                 唯一的元数据来源：frontmatter + 方法学正文
├── spatial_preprocess.py    脚本本体，直接用 python 运行
├── references/              正文链接到的细节（methodology / parameters / output_contract ...）
├── r_visualization/         （部分 skill）R 可视化
└── tests/
```

计划 0070 起，单细胞试点的 5 个 skill（`sc-qc`、`sc-preprocessing`、`sc-clustering`、`sc-cell-annotation`、`sc-de`）多了函数库，形状是：

```
skills/singlecell/scrna/sc-clustering/
├── SKILL.md                  手写正文 + 由 _api.py 生成的 ## API 段（有一致性测试）
├── _api.py                   函数库：步骤里 load_skill("sc-clustering") 拿到的就是它
├── sc_cluster.py             CLI 薄壳：argparse、报告、画廊图、result.json，计算都调 _api.py
├── examples/example_step.py  可执行示例步骤，数据来自 load_demo，CI 的 skill-examples job 真跑
├── references/
└── tests/
```

`_api.py` 以 `_` 开头，不算主脚本。其余 85 个 skill 还只有 CLI，步骤里用 `run_cli` 调用（§9.2）。

### 3.2 三种深度

扫描是递归的，skill 可以处在任意深度。当前语料里有三种（`find skills -name SKILL.md` 按深度统计）：

| 深度 | 数量 | 例子 |
|---|---|---|
| `skills/<domain>/SKILL.md` | 1 | `skills/literature/SKILL.md`（领域本身就是一个 skill） |
| `skills/<domain>/<skill>/SKILL.md` | 57 | `skills/spatial/spatial-de/SKILL.md` |
| `skills/<domain>/<sub>/<skill>/SKILL.md` | 32 | `skills/singlecell/scrna/sc-de/SKILL.md`、`skills/singlecell/scatac/scatac-preprocessing/SKILL.md` |

`Skill.domain` 取"扫描根下的第一级目录"，因此 `scrna/`、`scatac/` 不是领域，它们下面的 skill 都归入 `singlecell`。

### 3.3 七个领域

| 领域（`Skill.domain`） | skill 数 | 基础步 / 代表 skill | 领域索引 |
|---|---|---|---|
| `spatial` | 18 | `spatial-preprocess` → `spatial-domains` / `spatial-de` / `spatial-deconv` / `spatial-communication` | `skills/spatial/INDEX.md` |
| `singlecell` | 31 | `sc-preprocessing` → `sc-cell-annotation` / `sc-de` / `sc-batch-integration` / `sc-pseudotime` | `skills/singlecell/INDEX.md` |
| `genomics` | 10 | `genomics-alignment` / `genomics-variant-calling` / `genomics-variant-annotation` | `skills/genomics/INDEX.md` |
| `proteomics` | 8 | `proteomics-identification` / `proteomics-quantification` / `proteomics-de` | `skills/proteomics/INDEX.md` |
| `metabolomics` | 8 | `metabolomics-peak-detection` / `metabolomics-annotation` / `metabolomics-de` | `skills/metabolomics/INDEX.md` |
| `bulkrna` | 14 | `bulkrna-de` / `bulkrna-enrichment` / `bulkrna-coexpression` / `bulkrna-survival` | `skills/bulkrna/INDEX.md` |
| `literature` | 1 | `literature` | `skills/literature/INDEX.md` |
| **合计** | **90** | | |

核对命令：`find skills/<domain> -name SKILL.md | wc -l`，或 `make list`（调用 `load_skills` 并打印 `domain_summary()`）。

### 3.4 不是 skill 的目录

- **`_lib/` 等下划线目录**：`skills/spatial/_lib/`、`skills/singlecell/_lib/`、`skills/bulkrna/_lib/`、
  `skills/genomics/_lib/`、`skills/proteomics/_lib/`、`skills/metabolomics/_lib/` 是同领域脚本共享的 Python 代码
  （例如 `skills/spatial/_lib/preprocessing.py`、`deconvolution.py`）。
  注意：加载器**并不**按 `_` 前缀跳过目录——`loader.py` 只忽略以 `.` 开头的目录以及 `__pycache__`、`node_modules`。
  `_lib/` 不是 skill，是因为它里面没有 `SKILL.md`；约定上不要在 `_` 目录里放 `SKILL.md`。
- **`INDEX.md`**：领域级的人读索引，不是 skill（文件名不是 `SKILL.md`）。
- 符号链接目录不会被跟随（`entry.is_dir(follow_symlinks=False)`）。

---

## 4. `SKILL.md` 格式

### 4.1 例子

```markdown
---
name: spatial-preprocess
description: Load when running the foundational spatial transcriptomics QC + filtering + normalisation
  + HVG + PCA + neighbour-graph + Leiden pipeline on a Visium / Xenium / generic spatial AnnData. Skip
  when raw FASTQs need converting first (use spatial-raw-processing); tissue-domain detection on already-preprocessed
  data (use spatial-domains).
trigger: preprocess, spatial preprocessing, spatial QC, normalize, visium, xenium, merfish, slide-seq, load spatial data, leiden, umap
tags:
- spatial
- visium
- preprocessing
---

# spatial-preprocess

## When to use
...
## Key CLI
python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/spatial_pp_demo
...
## Dependencies
...
```

### 4.2 只读四个键

| 键 | 必填 | 被谁读取 |
|---|---|---|
| `name` | 是 | 索引、`use_skill` 的参数；全库唯一 |
| `description` | 是 | 索引——模型做路由的**唯一**依据。约定写成 "Load when … Skip when … (use <other-skill>)" |
| `trigger` | 否 | 仅 `/skills <query>` 搜索；逗号分隔标量或块序列均可，加载器统一成 `", "` 连接的字符串 |
| `tags` | 否 | 仅 `/skills <query>` 搜索 |

缺 `name` 或 `description` 的头部会被跳过、不进索引。其他键全部惰性：不读、不校验。
旧系统的 `skill.yaml`、`version` / `author` / `license` / `emoji` / `requires` 等已随旧系统删除；
skill 的 Python 依赖写在正文的 `## Dependencies` 小节里，**没有任何机制会替你安装它们**。

`trigger` 出现在对话里**不会**自动加载 skill（`Skill.triggers` 的 docstring 明确这一点）；
路由只看 `description`。

### 4.3 frontmatter 解析器

`parse_frontmatter` 支持 skill 头部实际用到的 YAML 子集：首行 `---` 与独立一行的闭合 `---`；
顶格 `key: value`（去掉成对引号）；缩进续行折叠为单空格（多行 `description` 靠它）；`- item` 块序列；
`|` / `>` 块标量；顶格 `#` 注释。不支持嵌套映射、锚点、别名、流式集合、tag、多文档——用到它们的键被丢弃而不是误解析。

为什么不采用"每行在第一个冒号处切开"的做法：那样只能读到 `description` 的第一行，
恰好丢掉后半句 "Skip when … use <other-skill>"，而这半句是防止选错 skill 的关键。
`tests/skills/test_real_corpus.py` 把本解析器与 `yaml.safe_load` 在全部真实头部上逐键比对；
包本身不导入任何 YAML 库，并有测试阻止它导入。

---

## 5. 加载器：`load_skills`

```python
from omicsclaw.skills import load_skills

index = load_skills("skills")           # 相对根 → 相对路径；绝对根 → 绝对路径
print(len(index), index.skipped)        # 90 ()
```

行为要点（`omicsclaw/skills/loader.py`）：

1. **递归且不剪枝**。找到一个 `SKILL.md` 后仍继续向下走，因为一个 skill 目录里可以再嵌套 skill。
   （plan 0032 的第一版在命中处剪枝，曾因此漏掉一个 skill。）
2. **只读头部**。正文留在磁盘上，直到 `get_full_content` 被调用。
3. **按相对路径排序**（POSIX 形式），而不是按目录遍历顺序，保证渲染出的索引跨机器字节稳定——索引位于 prompt 的可缓存前缀里。
4. **同名先到先得**。第二个同名 skill 记为 `SkipReason.DUPLICATE_NAME`，`detail` 写明被谁占用。
5. **跳过是数据，不是日志**。`SkillIndex.skipped` 是 `SkippedSkill(path, reason, detail)` 的元组，`reason` 取自：

| `SkipReason` | 含义 |
|---|---|
| `UNREADABLE` | 文件或途经的目录读不了（含解码失败） |
| `NO_FRONTMATTER` | 没有 `---` 分隔的头部 |
| `MISSING_NAME` | 有头部但 `name` 缺失或为空 |
| `MISSING_DESCRIPTION` | 有头部但 `description` 缺失或为空 |
| `DUPLICATE_NAME` | 名字已被索引顺序更靠前的 skill 占用 |

6. **缺失的根目录 = 空索引**（零配置）；**存在但读不了的根目录**抛 `SkillLoadError`（配置错误要大声）。

组合根在 `build_skill_index` 里对 `skipped` 非空打一条 WARNING（数量 + 第一条的路径与原因）。

---

## 6. `SkillIndex`：索引渲染与查找

`SkillIndex` 是不可变 dataclass（`skills`、`skipped`、`root`、`encoding`），可以不经文件系统直接构造，方便测试。

| 方法 | 作用 |
|---|---|
| `summary()` | 每个 skill 一行 `- name: description` |
| `domain_summary()` | 每个领域一行 `- domain (N skills): name, name, ...`，不含描述 |
| `prompt_body(*, compact=False)` | 一句提示 `Load a skill's full instructions with the \`use_skill\` tool when you need them.` + 上面二者之一；空索引返回 `""` |
| `get(name)` / `names()` / `by_domain()` | 精确查找 / 全部名字 / 按领域分组（首次出现顺序） |
| `search(query)` | 在 name、domain、tags、triggers 上做大小写无关的子串匹配；空 query 返回全部 |
| `get_full_content(name)` | **每次都重新读盘**，去掉 frontmatter 并 strip；找不到抛 `SkillNotFound` |
| `close_names(name)` | `difflib.get_close_matches(..., n=5, cutoff=0.5)`，给 "Did you mean" 用 |

### 6.1 三档索引：`full` / `compact` / `off`

| `AppConfig.skills_index` | prompt 中的 skills 段 | `use_skill` | 适用 |
|---|---|---|---|
| `full`（默认） | `summary()`：90 行，每行含完整 description | 挂载 | 常规部署；这段稳定，适合放在缓存前缀里 |
| `compact` | `domain_summary()`：7 行，只有名字 | 挂载 | 上下文紧张的模型；只能按名字路由，必要时读 `skills/<domain>/INDEX.md` |
| `off` | 整段消失（prompt 回到 5 段） | **不挂载** | 语料迁移期；"给模型一个取不到任何东西的工具"比两者都没有更糟 |

设置方式：`--skills-index compact` 或 `OMICSCLAW_SKILLS_INDEX=compact`；扫描根用 `--skills-dir` / `OMICSCLAW_SKILLS_DIR`
（默认 `<workspace>/skills`）。

`compact` 下 prompt 里看到的样子（节选）：

```
## Available skills

Load a skill's full instructions with the `use_skill` tool when you need them.

- bulkrna (14 skills): bulkrna-batch-correction, bulkrna-coexpression, bulkrna-de, ...
- genomics (10 skills): genomics-alignment, genomics-assembly, ...
- literature (1 skills): literature
...
```

截断 description 不是第三种档位：`SkillsIndex` 的 docstring 与 plan 0032 都明确"缩短描述是更便宜但路由更差的索引"。

---

## 7. `use_skill` 工具

### 7.1 调用与返回

```json
{"name": "use_skill", "arguments": {"skill_name": "bulkrna-de"}}
```

返回 = `SKILL.md` 正文 + 目录尾注：

```
# bulkrna-de

## When to use
...

---
Skill directory: skills/bulkrna/bulkrna-de
```

目录尾注的理由：plan 0032 统计过，绝大多数正文并不说明自己的脚本在哪，
没有这一行，模型拿到方法学却找不到实现它的脚本。`use_skill_tool(index, locate=False)` 可以关掉它。

### 7.2 Schema 与策略

- `USE_SKILL_SCHEMA`：唯一必填参数 `skill_name`（string），`additionalProperties: false`。
- `_POLICY`：`RiskLevel.LOW`、`ApprovalMode.AUTO`、`read_only=True`、`concurrency_safe=True`、
  `allowed_in_background=True`、tags `{"skills", "inspection"}`。
  **显式声明而非默认**：`ToolPolicy` 默认是 `HIGH` + `ASK`，且无审批通道时失败关闭——不声明就等于每次加载 skill 都弹审批。
  因为 `read_only=True`，`--permission-mode read-only` 下它仍可用。

### 7.3 错误与自愈

| 场景 | 行为 |
|---|---|
| `skill_name` 为空白 | `ToolArgumentError`：提示给出索引里的 `name` |
| 名字不在索引 | `ToolArgumentError(str(SkillNotFound))`，例如 `no skill named 'spatial-deconvolution'. Did you mean: spatial-deconv, spatial-condition, spatial-communication, bulkrna-deconvolution, spatial-cnv? The skill index in the system prompt lists all 90.` |
| 索引里有但文件已删或读不了 | `OSError` / `UnicodeDecodeError` 向上抛，由工具层作为错误结果返回 |
| `../../etc/passwd` 之类 | 只是一个查不到的名字：模型的字符串**从不**被拼成路径，`Skill.path` 永远由加载器写入 |

`SkillIndex.get` 严格精确匹配（不折叠大小写）：模型是从发给它的索引里抄名字的，拼错时 "did you mean" 正是教它拼对的信息。

---

## 8. 组合根接线

`omicsclaw/entry/assembly.py`：

```python
skills = build_skill_index(config)          # build_app 里只调用一次
tools  = foundation_tools(config, skills=skills, ...)    # read_file, write_file, edit_file,
                                                         # bash, web_fetch, web_search, use_skill,
                                                         # [plan_write], [memory_search, memory_write]
sections = default_sections(config, skills=skills, ...)  # ... tools → [planning] → [sandbox] → skills → environment → [memory]
```

三条值得记住的性质：

1. **一次扫描，两个消费者**。两次扫描不会报错，但会让 prompt 广告一个 `use_skill` 取不到的 skill，
   模型会把自己正确的调用读成自己的错误。测试用"每次扫描返回不同目录"的替身来钉住共享性。
2. **位置**：skills 段放在工具指引之后、environment 之前。它是 prompt 里最大且最稳定的块，
   而每天都变的 environment 放最后，只让缓存前缀的末端失效。
3. **快照**：`_skills_section` 绑定的是一次扫描的快照。运行中新写入的 skill 在下次扫描（下次启动）之前不可见；
   需要热加载的部署自己传一个每次重新 `load_skills` 的闭包（约 20 ms/次）。`get_full_content` 则每次重新读盘，
   所以**已索引 skill 的正文**修改后下一次 `use_skill` 就能看到。

`AgentApp.skills` 保存这份索引，供界面报告（CLI `/skills`、Desktop `/health` 的 `skills_count`）而无需再扫。

---

## 9. 执行通道：在模块里写步骤，用步骤执行器运行

旧的确定性执行入口（`oc run <skill>`、`omicsclaw/skill/` 里的 runner、`python omicsclaw.py replot`）已全部删除，
且按 owner 裁定**不恢复**。计划 0070 之后，非平凡的分析都在课题的模块里做：workspace 就是课题根，`analysis/<NN_slug>/`
放一个模块的代码（README 和编号的步骤文件），`results/<NN_slug>/` 放它的输出。agent 写步骤文件，再用 `bash` 调步骤执行器
`skills/_sdk/notebook/run.py`（Environment 段里有它的完整命令）运行：

```
用户: 对 pbmc3k 做聚类
  │
  ├─ bash: python <skills>/_sdk/notebook/run.py status        ← 开工前先看课题状态，再读 STRATEGY.md
  ├─ use_skill{"skill_name": "sc-clustering"}                  ← 读方法学、## API、参数来源
  ├─ bash: python <skills>/_sdk/notebook/run.py new clustering ← 建 analysis/03_clustering/ 与 results/03_clustering/
  ├─ write_file: analysis/03_clustering/01_cluster.py           ← load_skill + read_input + write_output
  ├─ write_file: analysis/03_clustering/02_validate.py
  ├─ bash: python <skills>/_sdk/notebook/run.py run analysis/03_clustering
  ├─ bash: ... replay analysis/03_clustering → write_file REPORT → task(module-reviewer) → 用户确认 → accept
```

### 9.1 步骤与执行器

- 步骤是 percent 格式的普通 Python 文件（`# %%` 分 cell，`# %% [markdown]` 写说明），名字形如 `02_cluster.py`，字母后缀表示变体，
  每个模块恰好一个 `<k>_validate.py`，总是最后运行。不允许 `%`、`!` 开头的魔法行，所以每个步骤也能用 `python <file>` 单独运行。
- 步骤代码只用 `skills._sdk.notebook` 的 5 个函数：`read_input`、`write_output`、`load_skill`、`load_demo`、`run_cli`。
  执行器在一次性的 IPython kernel 里逐 cell 运行步骤（kernel 用执行器自己的解释器），每次运行写一份 JSON-lines 记账
  （`results/<NN>/provenance/runs/<step>/<run_id>.jsonl`）：读了哪些文件及其 sha256、调用了哪些 skill 函数和参数、写了哪些输出。
  manifest 从记账重建，各步骤的 notebook 拼成 `notebooks/M<NN>_<slug>.ipynb`。
- validate 步骤另有 `skills._sdk.notebook.checks` 的 7 个检查函数：`check_columns`、`check_rows`、`check_between`、
  `check_same_labels`、`check_counts`、`check_files`，以及 `as_labels`。标签一律先转成字符串再比较，`0`、`0.0`、`"0"`
  算同一个标签，所以从 CSV 读回成整数的 cluster 列能和 `obs` 里的字符串标签对上。`check_files` 检查 REPORT 引用的图
  存在且不为空，并把它们记成 validate 步骤的输入。检查失败抛 `AssertionError`，`python -O` 下也一样。
- `python <skills>/_sdk/notebook/run.py reference [<function>]` 打印这 5 个步骤函数和 7 个检查函数的签名与说明：路径规则、
  默认的读写格式、`load_demo` 的查找顺序、`run_cli` 的输出位置与报错。内容直接取自 docstring，契约要求 agent 在写第一个
  步骤之前看一遍。
- 一个步骤过期只看两样：步骤文件变了，或者它经 `read_input` 读过的文件变了。步骤读了又原名写回的文件，按它自己最后写入的
  sha256 比较。`status` 列出每个过期步骤的原因，上游模块重跑后下游模块会显示 `input changed: results/...`。
- 子命令：`new`、`run`、`status`、`replay`、`accept`、`revise`、`api`、`reference`。验收分三步：`replay` 在新 kernel 里重跑全部步骤；
  内置的只读子代理 `module-reviewer` 给出 `VERDICT: APPROVE` 或 `REVISE`；用户确认后 `accept` 冻结模块。冻结的模块要先 `revise`
  （快照进 `baseline/`）才能再改。`replay` 开始前把 `reviews/` 里已有的审查移进 `reviews/archive/<id>/`，每份的 verdict 和
  sha256 记进 manifest 的 `review_history`，所以同一天的复审不会覆盖第一次的审查。重放成功时执行器还写
  `results/<NN>/provenance/review_brief.md`，供审查子代理先读（见 `sub-agent.md` §2.3.1）；重放失败时不留摘要。
- 执行器只在前台运行。`run`、`replay` 在启动它们的进程退出后自行停止（父进程变了，或进程组原来的组长已经退出，后者覆盖
  `nohup … &` 这类 shell 立即退出的写法；进程组是终端前台组时不查组长，所以在交互式终端里写成 `echo x | python run.py …` 也能跑完）：杀掉正在跑的 kernel，删掉这个步骤上一次留下的 notebook，给当前步骤记一条失败的
  `run_end`（`reason: "parent exited"`），然后退出并释放模块锁。单次运行的上限约等于 `tool_timeout_s` 减 15 s，
  模块一次跑不完时按步骤逐个 `run <step file>`。输出的读取方提前关闭（`run ... | head`）时，执行器丢弃余下输出，照常跑完。

### 9.2 有函数库的 skill 与只有 CLI 的 skill

- 有 `## API` 段的 skill：`library = load_skill("sc-clustering")`，再调用 `library.cluster(adata, ...)`。只有 `__all__` 里的名字可用，
  每次调用都进记账。
- 只有 CLI 的 skill：`run_cli("bulkrna-de", "--input", "data/counts.csv", inputs=["data/counts.csv"])`。输出默认落在
  `results/<NN>/intermediate/<skill>/`；给 `--output` 时，它必须是本模块 `figures/`、`tables/`、`intermediate/`、`logs/`
  之一下面的子目录。跑完后按输出目录逐个文件补记，所以重放时不会被当成孤儿文件。脚本约定照旧：
  路径以 `use_skill` 返回的目录为准，主脚本都支持 `--help`，绝大多数支持 `--demo`。
- 过渡期 CLI 仍可在课题外直接用 `bash` 运行，输出结构见下。试点 skill 的 CLI 已是 `_api.py` 的薄壳，
  `tests/parity/` 保证它们的输出与改造前逐值一致。

以 `python skills/bulkrna/bulkrna-de/bulkrna_de.py --demo --output /tmp/de_demo` 实测：

```
/tmp/de_demo/
├── report.md                     人读报告（含免责声明）
├── result.json                   机器可读结果：skill / version / completed_at / input_checksum / summary / data
├── figures/                      volcano_plot.png, ma_plot.png, de_barplot.png, pvalue_histogram.png
├── tables/                       de_results.csv, de_significant.csv
└── reproducibility/commands.sh   复现命令
```

### 9.3 科学层：`omicsclaw/common/` 与 `skills/_sdk/`

skill 脚本依赖的"科学层"。计划 0062 起它全部在 `skills/_sdk/`，skill 代码不再导入 `omicsclaw`；框架自己的 `omicsclaw/common/` 仍保留读取与校验一侧，两边由 `tests/sdk/` 的契约测试钉住：

| 模块 | 提供 |
|---|---|
| `skills/_sdk/report.py`、`result.py` | `generate_report_header` / `generate_report_footer`、`write_repro_requirements`；`write_result_json`（`result.json` 信封，结构见 `RESULT_SCHEMA`）、`load_result_json`、`mark_result_status`、`write_owned_text` |
| `skills/_sdk/checksums.py`、`runtime_env.py`、`user_guidance.py` | 输入文件 SHA-256（`sha256_file`）、科学栈缓存目录（`ensure_runtime_cache_dirs`）、用户指引行 |
| `skills/singlecell/_lib/viz/r/replot_hint.py` | 已失效的 `write_replot_hint`（见 §13） |
| `omicsclaw/common/report.py` 等 | 框架侧：`validate_result_envelope`、`DISCLAIMER`、`write_output_readme`、`.env` 读取（启动层的 `_adopt_dotenv` 用 `runtime_env.load_env_file`）、输出目录归属（`output_claim.py`） |
| `skills/_sdk/r_script_runner.py`、`r_utils.py`、`r_dependency_manager.py`、`r_scripts/` | 调用 R（CellChat、Numbat 等 R 后端）；原 `omicsclaw/core/` 与 `omicsclaw/r_scripts/`，计划 0062 阶段一搬入 |
| `skills/_sdk/deps.py`、`external_env.py` | 可选依赖检测、外部 conda 子环境调用；`skills/_sdk/` 不导入 `omicsclaw` |

### 9.4 与 agent 框架的交汇点

- **超时**：`bash` 的上限由 `AppConfig.tool_timeout_s`（默认 600 s）派生，`bash_timeout() = tool_timeout_s - 15`。
  反卷积、比对这类分钟到小时级的运行需要调大 `--tool-timeout` / `OMICSCLAW_TOOL_TIMEOUT_S`，**只改这一个数**。
- **审批**：`bash` 的策略是 `ASK`。在 `default` 权限模式下，每次调执行器都会出审批卡片（CLI 可答 `s` 对本会话放行 `bash`，
  或 `/auto`）；`use_skill` 本身不需要审批。放行之后 `accept` 也不再出卡，所以"用户确认后才验收"只靠契约约束。
- **大输出**：脚本的 stdout 进入对话上下文；上下文压力达到 `compact_at`（默认 `warn`）后，
  `ProgressiveCompactor` 会先把大的工具结果 offload 到 `<workspace>/.omicsclaw/tool_results/`，再做摘要。
- **沙箱**：开启 `--sandbox docker` 时脚本在容器里运行，工作区以相同路径挂载。
- **安全规则**：system prompt 的 safety 段（`SAFETY_RULES`）第 3 条要求"skill 没给定的参数、阈值或截断值，在步骤里写明取值和理由；不编造基因关联"，
  第 2 条要求每个模块的 REPORT 和给用户的结果摘要都附免责声明——与 skill 报告实际写入的 `skills/_sdk/report.py` 的 `DISCLAIMER` 是同一句话，
  由 `test_assembly.py` 校验，`accept` 也会检查 REPORT 里有它。

---

## 10. 链式调用

一个模块对应一个分析阶段（QC、预处理、聚类、注释、差异表达……），按创建顺序编号。下游模块只读上游模块的
`results/<NN>/intermediate/` 和 `tables/`，例如聚类模块的步骤 `read_input("results/02_preprocess/intermediate/adata.h5ad")`。
上游重跑改写了这些文件，`status` 会把下游的步骤标为过期；要不要重跑下游由 agent 决定，执行器不自动级联。

多数领域仍有一个必须先跑的**基础步**：

| 领域 | 基础步 | 产物 | 典型下游 |
|---|---|---|---|
| spatial | `spatial-preprocess`（上游可选 `spatial-raw-processing`） | `processed.h5ad`（`obsm["X_pca"]`、`obs["leiden"]`） | `spatial-domains`、`spatial-de`、`spatial-genes`、`spatial-deconv` |
| singlecell | `sc-preprocessing`（上游 `sc-qc` / `sc-filter` 等） | 预处理后的 AnnData | `sc-clustering`、`sc-cell-annotation`、`sc-de`、`sc-batch-integration` |

每个领域的链条写在 `skills/<domain>/INDEX.md` 的手写部分和各 `SKILL.md` 的 "See also / Adjacent skills" 里。课题级的计划与跨模块的
决定写在 `docs/analysis_strategy/STRATEGY.md`，由 agent 与用户一起维护，不注入系统提示；契约要求开工前先跑 `status` 再读它。

---

## 11. 用户侧：发现 skill

skill **不是**斜杠命令（plan 0051 撤掉了 `/skill-name` 直通）。用户在请求里点名（"用 spatial-de 比较这两组"）或直接描述任务即可。

| 输入 | 效果 |
|---|---|
| `/skills` | CLI：按领域分组列出全部已索引 skill |
| `/skills <query>` | 用 `SkillIndex.search` 过滤：name / domain / tags / triggers 子串匹配，如 `/skills deconv`、`/skills visium` |
| `/spatial-de ...` | CLI 回答 `No command named /spatial-de.`，并提示"Skills are picked by the agent: describe the task"；**不会**发给模型 |
| `/data/run7/x.h5ad 看看这个` | 首个 token 含 `/`，被识别为路径而非命令名，照常发给模型 |

Channel 也注册了 `/skills`（`omicsclaw/entry/channel/commands/builtins.py`）。

---

## 12. 新建一个 skill

`templates/skill/` 是**供人复制**的起点（不被任何代码生成器读取）：

```bash
cp -r templates/skill skills/<domain>/<my-new-skill>
cd skills/<domain>/<my-new-skill>
mv replace_me.py <my_new_skill>.py
mv tests/test_replace_me.py tests/test_<my_new_skill>.py
# 手写 SKILL.md：frontmatter（name / description / trigger / tags）+ 整个正文
# 把 <my_new_skill>.py 的合成 CSV demo 换成真实 I/O；补 references/*.md
```

验证与收尾：

```bash
python -c "from omicsclaw.skills import load_skills; i = load_skills('skills'); print(len(i), i.skipped)"
make skill-index      # = OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py
```

写 description 的要点（模板注释原话的意思）：它是模型看到的关于这个 skill 的**全部**信息；写清何时 Load、何时 Skip，
并点名替代 skill——Skip 那半句是防止误选的关键。`name` 必须全局唯一，重名会被跳过而不是合并。

### 12.1 `INDEX.md` 与一致性测试

每个 `skills/<domain>/INDEX.md` 分两部分：顶部手写散文（标题、Domain key、Primary data types、简介），
以及由 `SKILL.md` 头部**推导**的 `**Skill count:**` 行和 `## Skills` 小节（按名字排序，每行 `` `name` — description ``，
有 trigger 时附一行 `triggers: ...`）。

`tests/skills/test_domain_index_is_current.py` 负责：

- `test_every_domain_directory_has_an_index`：加载器发现的领域集合 = 有 `INDEX.md` 的领域集合；
- `test_the_index_matches_the_skills_on_disk`：推导部分与磁盘一致，否则失败并提示重生成命令；
- 设置 `OMICSCLAW_WRITE_SKILL_INDEX=1` 时就地重写推导部分，不动手写散文。

这取代了已删除的 `scripts/generate_domain_index.py`："一个没人运行的生成器"正是索引曾经漂移的原因，所以改为测试。

---

## 13. 已知限制

1. **`replot` 死链仍在产品输出里**。22 个 skill 脚本调用 `skills/singlecell/_lib/viz/r/replot_hint.py` 的 `write_replot_hint`，
   往 `result.json` 写一个指向 `python omicsclaw.py replot` 的 `replot` 块，而该命令已不存在。
   R 渲染器和 `figure_data/` 仍会产出，但目前除了重跑 skill 没有办法重绘。不要向用户提供这个命令。
2. **`oc run` 残留**。`SKILL.md` 正文里的 `oc run` 已在工作树中清理（`grep` 计数为 0），但 skills/ 下仍有 15 个文件
   （主要是 `references/methodology.md`）提到 `oc run` / `omicsclaw.py run`。
   FRAMEWORK-REBUILD.md "Open after the migration" 记录的"96 个 SKILL.md 仍写 oc run"是迁移当时的状态。
3. **生成器已不存在**。`scripts/generate_skill_md.py`、`generate_routing_table.py`、`generate_domain_index.py` 等随旧 skill 系统删除；
   `SKILL.md` 只能手写，`OMICSCLAW.md` 的路由表手工维护，只有 `INDEX.md` 有测试兜底。
4. **`consensus-interpret` 的 LLM 路径不可用**。它的 `_llm.py` 惰性导入已删除的 `omicsclaw.providers`，默认走结构化路径（`--no-llm`）；
   它读的是已删除的 4 个 consensus 外壳的产物，随 ensemble 计划处理（计划 0070 删除了这 4 个外壳）。
5. **没有执行信封校验**。旧 runner 负责的 `result.json` 信封检查、run receipt、`reproducibility/replay.json`、
   `environment.json`、`replay.sh`、输出目录占用声明、废弃 skill 的路由屏蔽，现在都**没有任何东西强制**——
   是否写、写得对不对取决于各脚本自己。
6. **依赖不自动安装**。`## Dependencies` 只是文字；缺包时脚本在运行中途才失败。长任务前应先让 agent 检查。
7. **索引是启动时快照**。运行中新增的 skill 需重启（或自定义重扫闭包）才进索引。
8. **`examples/demo_visium.h5ad` 不存在**：当前工作树的 `examples/` 下只有 CSV 与 `consensus_benchmark/`，
   空间 skill 的 demo 请用各脚本的 `--demo`。
9. **记账只看得到经 `read_input` / `write_output` 的读写**。步骤里直接用 `pd.read_csv` 读的文件不进记账，过期判定也看不到它；
   契约、审查子代理和 validate 步骤负责把这种写法挡在外面。

---

## 14. 测试

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest tests/skills -q     # 430 passed（2026-09-23）
```

| 测试文件 | 覆盖 |
|---|---|
| `tests/skills/test_frontmatter.py` | YAML 子集解析 |
| `tests/skills/test_loader.py` | 递归扫描、排序、重名、跳过原因、根目录错误 |
| `tests/skills/test_index.py` | `summary` / `domain_summary` / `prompt_body` / `search` / `get_full_content` |
| `tests/skills/test_use_skill.py` | 工具 schema、策略、目录尾注、错误信息 |
| `tests/skills/test_real_corpus.py` | 真实 94 个头部 vs `yaml.safe_load` |
| `tests/skills/test_prompt_section_seam.py` | 作为 `Section` 源的接缝（快照 vs 重扫） |
| `tests/skills/test_skills_is_a_leaf_layer.py` | 子进程导入白名单 |
| `tests/skills/test_domain_index_is_current.py` | `INDEX.md` 与头部一致 |

---

## 15. 文件索引

| 文件 | 内容 |
|---|---|
| `omicsclaw/skills/__init__.py` | 包说明、三行接线示例、公开符号 |
| `omicsclaw/skills/frontmatter.py` | `Frontmatter`、`parse_frontmatter` |
| `omicsclaw/skills/skill.py` | `Skill`（`triggers`、`directory`、`relative_path`、`domain`） |
| `omicsclaw/skills/loader.py` | `load_skills`、`SkillLoadError`、`SKILL_FILENAME` |
| `omicsclaw/skills/index.py` | `SkillIndex`、`SkillNotFound`、`SkipReason`、`SkippedSkill` |
| `omicsclaw/skills/use_skill.py` | `use_skill_tool`、`USE_SKILL_SCHEMA`、`USE_SKILL_TOOL_NAME` |
| `omicsclaw/entry/assembly.py` | `build_skill_index`、`foundation_tools`、`_skills_section`、`default_sections`、`AgentApp.skills` |
| `omicsclaw/entry/config.py` | `SkillsIndex`、`AppConfig.skills_dir` / `skills_index` / `skills_root()` |
| `omicsclaw/entry/cli/_repl.py` | `/skills`、未知 `/name` 的提示 |
| `skills/_sdk/` | skill 共用的报告、`result.json`、依赖表与 R 调用（`omicsclaw/common/report.py` 保留框架侧的校验与 `DISCLAIMER`） |
| `skills/<domain>/INDEX.md` | 领域索引（部分推导） |
| `templates/skill/` | 新 skill 模板（`SKILL.md`、`replace_me.py`、`references/`、`tests/`、`README.md`） |
| `tests/skills/` | 见 §14 |
| `docs/plans/0032-skill-loader.md` | 加载器设计计划 |
| `docs/plans/0045-agent-skills-parity.md`、`docs/plans/0051-cli-drop-skill-slash-and-resume-picker.md` | agent-skills 一致性修订、以及撤回 `/skill-name` |
| `docs/FRAMEWORK-REBUILD.md` | Step 5.6、"The skill runner was not re-homed"、"Open after the migration" |
