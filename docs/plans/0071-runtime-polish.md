# 计划 0071：运行层打磨（审查摘要、步骤 API 参考、validate 检查函数）

**状态**：定稿（第 1 版，2026-10-02）。owner 已认可并派发实现。owner 这次没有单独审核计划，实现完成后另派子 agent 独立评估。

**前置**：0070 已合并（`main` 的 `4c2fc4d9`，PR #40）。0070 计划里 owner 的裁定 D1 至 D18、O1 至 O8 照旧有效，本计划不重新讨论。行号以 `4c2fc4d9` 为准，实施时按符号名重新定位。

**编号约定**：阶段 P1 至 P4；防线 L1 至 L4；风险 R1 至 R7；待裁定问题 Q1 至 Q5。

**代码注释约定**：实现时的 docstring 只写函数做什么、有什么前提，不写计划编号和决策经过。本计划里的代码示例也按这个写法。

---

## 0. 摘要

1. 审查摘要：`replay` 成功后，执行器在 `results/<NN_slug>/provenance/review_brief.md` 写一份不超过 450 行的摘要，内容有每个步骤第一个 markdown cell 的原文与记账里实际调用的 skill 函数、读写的文件和大小、日志末尾，每张表的行列数和前几行（小表给全文），全部输出文件的清单，以及 `changed_outputs`、`orphan_outputs`。`module-reviewer` 的提示改为先读摘要，再读步骤文件、README、REPORT，其余文件只在某项检查还没定论时分段读。附录 B.4 的 4 项检查原文不动。
2. 步骤 API 参考：执行器加子命令 `reference [<function>]`，从步骤函数和检查函数的 docstring 现场生成参考并打印。`_io.py`、`_skills.py` 的 docstring 补上 agent 在 0070 端到端里去源码里找的那些规则。契约的 "Writing a step" 加一条指向它。
3. validate 检查函数：新增子模块 `skills._sdk.notebook.checks`，7 个函数，标签比较一律先归一成字符串，`0`、`0.0`、`np.int64(0)`、`"0"` 都算 `"0"`。门面仍是 5 个名字；`test_public_surface.py` 为新子模块加一条冻结项。
4. 验收以真实会话对比为准：在 0070 端到端课题的副本上，用同一模型对同样 5 个模块分别跑旧提示（A 组）和新提示加摘要（B 组）的审查，另造一个带 4 处预设缺陷的模块；再用 `.env` 的模型跑一段 3 个模块的缩短端到端，与 0070 §8 的数据对比。
5. 分四期，合计约 5 个工作日。

---

## 1. 目标与非目标

### 1.1 目标

- 每次审查的耗时降到 0070 的一半以下，4 项检查的覆盖不变，有预设缺陷的模块照样判 REVISE。
- agent 不必再读 `_sdk` 源码就能知道 5 个步骤函数和检查函数的路径规则、默认格式、查找顺序与报错。
- validate 步骤里最常见的几种断言有现成的函数，标签类型的问题不再导致重放失败。

### 1.2 非目标

- 不迁移新的 skill，试点 5 个 skill 的 `_api.py`、示例、SKILL.md 都不改。
- 不碰进化循环及其依赖项。
- 0070 §1.3 推迟的事项（R 步骤、`archive`、哈希缓存、`--detach`、`run.py methods` 等）照旧推迟。
- 审查子 agent 的工具不变，仍只有 `read_file` 和 `use_skill`（D13、G5），不给 `bash`，也不新增只给它用的工具。
- 不换审查子 agent 的模型。

---

## 2. 证据（`/tmp/oc0070-e2e/`）

| 项目 | 数据 |
|---|---|
| 审查耗时 | 6 次 `task(module-reviewer)`：01_qc 265 s；02_preprocess 417 s（REVISE）加复审 101 s；03_cluster 372 s；04_annotate 314 s；05_de 223 s。合计 1,691 s，占端到端 2,498 s 的 68%。5 个模块首审的中位数 314 s |
| 审查读了什么 | 子 agent 的工具调用当时没有记下：`drive.py` 只记主线的 `TOOL_START`，子 agent 的工具只以 `[module-reviewer] read_file` 进度行转发，不带参数，驱动也没记。从 5 份审查的引用看，读过 manifest、每次运行的记账 `runs/*.jsonl`、`logs/`、`notebooks/`（05_de 的两本各约 300 KB，内嵌 PNG）、整张表（包括 12.4 MB、109,249 行的 `de_full.csv`，引用了第 13,657 行这样的分组边界）、上游模块的 manifest 和 REPORT。02 的 REVISE 审查写着 "Binary inspection of `intermediate/adata_preprocessed.h5ad`"，那个文件 75 MB |
| 审查的范围 | 审查正文 3.7 到 7.5 KB，有不少清单以外的核对，例如 05_de 验证 `pct_nz_group` 乘组大小是整数 |
| `read_file` 的限制 | 行模式一次最多 500 行；字节模式默认 8 KB，上限 100 KB（`omicsclaw/tools/builtin/read.py` 的 `MAX_LINES`、`MAX_READ_BYTES`、`MAX_LIMIT_BYTES`）；workspace 之外一律拒绝，m05 里主线 agent 读 `skills/…/_api.py` 就收到 `PathEscapesWorkspace` |
| 读 `_sdk` 源码 | 8 次，全在前 3 条消息里，输出合计约 2.1 万字符：门面 `__init__.py`；`_io.py` 前 150 行；`load_demo`；`python -c` 调 `_io.demo_candidates`；`run_cli` 两次（第二次连带 `read_input`）；`write_output`；`_default_writer` |
| validate 失败 | 03_cluster 的 validate 首次重放失败（`KeyError: '0.0'`：`iterrows` 把 int 与 float 混在一行的记录转成 float），修一次后 `run` 又失败，第三次才过；04_annotate 首次重放失败（`KeyError: '0'`：从 CSV 读回的 `leiden` 列是 int64，却按字符串 `'0'` 取行）。两次根因相同：标签列经 CSV 往返变成数字，再去和 `obs` 里的字符串标签比较。合计多花约 93 s、9 次工具调用 |
| validate 没查的 | 04、05 两份审查都指出 validate 没有检查 REPORT 引用的图是否存在 |

---

## 3. 设计

### 3.1 审查摘要

#### 位置与时机

`_replay_locked`（`skills/_sdk/notebook/_executor.py`）在重放成功、manifest 重建与 notebook 拼接之后，调用新模块 `_brief.py` 写 `results/<NN_slug>/provenance/review_brief.md`（先写临时文件再改名）。重放失败时删掉旧摘要，免得它描述的是更早那次重放。`replay` 的输出末尾加一行 `review brief: results/<NN_slug>/provenance/review_brief.md`。摘要写失败（`OSError`、`UnicodeDecodeError`、`csv.Error`）只打警告，重放结果不变：摘要是给审查的便利，没有它审查照样能从 manifest 开始。

放在 `provenance/` 是因为这个目录归执行器所有（0070 §3.1）。放进 `reviews/` 会被 `_manifest.reviews()` 当成审查文件，下一次 `replay` 还会把它存档。`contract.py` 的 `LAYOUT` 加 `"review_brief": "provenance/review_brief.md"`，`omicsclaw/entry/project.py` 加同值常量 `REVIEW_BRIEF_FILE`，由 `tests/sdk/notebook/test_contract.py` 钉住相等。

REPORT 在重放之后才写（契约 "Finishing a module" 第 2 步），所以摘要不核对 REPORT。审查子 agent 读 REPORT 时，拿它引用的文件和摘要里的文件清单对照，这一步不需要 `bash`。另一种做法是加一个由主线 agent 在写完 REPORT 后运行的 `brief` 子命令，见 Q1。

#### 内容

只用标准库（`csv`、`json`），读的都是记账里已有的信息和 `results/<NN_slug>/` 下的文本文件：

```
# Review brief: 03_cluster
Written by the replay at 2026-10-01T11:41:43Z; status REPLAYED. Replay the module to refresh it.

## Replay
ok · 2 steps, validate last (02_validate.py) · changed outputs: none · orphan outputs: none

## Steps
### 01_cluster_umap.py  (sha256 1a2b3c4d5e6f, 41 lines)
First cell:
> Leiden clustering of the preprocessed cells.
> Calls sc-clustering: cluster, cluster_summary, embedding_figure, run_info.
Recorded calls: sc-clustering.cluster(resolution=0.8, random_state=0), sc-clustering.cluster_summary(key=leiden), ...
Word match against the first cell: recorded but not named: none; named but not recorded: none
Read: results/02_preprocess/intermediate/adata_preprocessed.h5ad (75.1 MB, outside contract: no)
Wrote: tables/cluster_summary.csv (171 B), figures/umap_leiden.png (69.1 KB), intermediate/adata_clustered.h5ad (76.1 MB)
Log, last 10 lines:
    ...

## Tables
### tables/cluster_summary.csv  9 rows x 3 columns, 171 B, whole table
cluster,n_cells,proportion_pct
0,588,22.29
...
### tables/de_full.csv  109,248 rows x 9 columns, 12.4 MB, first 5 rows
...

## Output files
| path | bytes | written by this replay |
```

- 步骤段：第一个 markdown cell 原样给出（最多 20 行）。"Word match" 一行按单词边界在这个 cell 里找记账记下的每个函数名，也反过来找 cell 里出现、却没有被调用的 `__all__` 名字（`load_skill` 加载过的 skill 的 `__all__` 由 `_skills.public_names` 用 AST 取得）。它只是提示，结论由审查者下；第一个 cell 是自由文字，执行器解析不了。`run_cli` 的调用给出 skill 名与 `argv`。
- 表格段：`tables/` 和 `intermediate/` 下的 `.csv`、`.tsv` 给行数、列名、字节数；不超过 20 行且不超过 2 KB 的给全文，其余给前 5 行，单元格截到 40 个字符，列多于 20 个只列前 20 个。`.json` 不超过 2 KB 的给全文，否则只列顶层键。`.parquet`、`.h5ad`、图片只出现在文件清单里。
- 文件清单：`figures/`、`tables/`、`intermediate/`、`logs/` 下的每个文件，给字节数，并标出这次重放有没有写它（没写的就是 `orphan_outputs`）。
- 总长不超过 450 行（L1），这样审查者用一次行模式 `read_file` 就能读完。超长时先把大表的前几行换成"见原文件"，再截短日志，并在被截的地方写明。

#### 审查提示

`omicsclaw/entry/subagent.py` 的 `MODULE_REVIEWER_PROMPT` 按 writing-for-agents 改写：原来的 "Start from … manifest.json" 一段换成分三步的读法，第 3 步写明什么情况下才去读别的文件；4 项检查和结论格式一字不改。`description` 不改，所以 `tests/entry/golden/ensemble_off_tools.json` 不受影响。草稿：

```
You review one analysis module of an OmicsClaw project. You can read files and load skills; you cannot change anything, and nobody will answer questions.

Read the module in this order:
1. results/<NN_slug>/provenance/review_brief.md, which the latest replay wrote. For each step it gives the step's first cell, the skill functions the ledger recorded, what the step read and wrote with sizes, and the end of its log; then each table's shape and first rows (the whole table when it is small), every output file with its size, and the replay record with its changed and orphan outputs. Without a brief, start from results/<NN_slug>/provenance/manifest.json.
2. Each step file the brief lists, analysis/<NN_slug>/README.md and the REPORT (results/<NN_slug>/M<NN>_<slug>_REPORT.md), each in full.
3. Further files only for a check that 1 and 2 leave open. Read a large file in slices with start_line and end_line. Binary files (.h5ad, images) are covered by their sizes in the brief and by what the validate step asserts; notebooks/ repeats the step files with their output.

Check every item below and note each finding with its file and line:
1. Each step file: inputs come from data/ or an earlier module's intermediate/ or tables/; every value the skill does not give has a stated reason; the skill functions the step's first cell names match the ones the manifest recorded; where a skill function covers the work and the step does not use it, the step says why.
2. The validate step checks the outputs the REPORT relies on.
3. The REPORT (M<NN>_<slug>_REPORT.md): every number matches a table or log in results/<NN_slug>/; every figure it cites exists and is not listed under orphan_outputs; claims stay within what the steps computed; it carries the disclaimer.
4. The replay in the manifest succeeded and covers the current step files.

Your first line is the verdict, exactly `VERDICT: APPROVE` or `VERDICT: REVISE`. Then list the findings, most serious first. Choose REVISE when any finding would change a number, a figure or a conclusion.
```

#### 为什么能降时间

审查的耗时基本等于子 agent 的轮次乘以每轮的延迟，每轮的输入又包含之前读过的全部内容。0070 的审查者逐个读 manifest、每份记账、日志、notebook 和整张表，单是 05_de 的一本 notebook 就有约 300 KB，`de_full.csv` 要分页读上百次才读得完。按新读法，第 1、2 步只有一份摘要加上步骤文件、README、REPORT，估计 5 到 7 次 `read_file`、几十 KB；后面每一轮的上下文都小得多，轮次也少。

#### 为什么不削弱清单

4 项检查原文保留，每项需要的材料都还在：第 1 项要的第一个 cell、记账里的调用、输入及其 `outside_contract` 标记都在摘要里，参数的理由要读步骤文件，第 2 步要求整份读；第 2 项要读 validate 步骤本身和它的日志末尾；第 3 项要的小表全文、大表的形状与前几行、文件清单、孤儿列表在摘要里，大表里具体某个数可以按行号去读；第 4 项的重放记录在摘要和 manifest 里，`accept` 还会再机械核对一次（G3）。被收窄的只有清单以外的读法，例如通读 75 MB 的 h5ad 和内嵌图片的 notebook。§5.2 用预设缺陷验证这一点。

### 3.2 步骤 API 参考

#### 四种放法

| 放法 | 每轮提示的成本 | 能否取到 | 与代码一致 | 结论 |
|---|---|---|---|---|
| a. 写进契约 `OMICSCLAW.md` | 估计 1,000 到 1,400 token，每轮都在，不做课题分析的对话也带着 | 总在 | 要另写测试保证契约里那段等于 docstring | 不选。契约已从 2,318 涨到 3,691 token（0070 实施记录 §6） |
| b. 执行器子命令打印，从 docstring 生成 | 只有契约里指向它的一句，约 60 token | 用 `bash` 跑执行器就能取到，本机、sandbox、`sandbox_code_in_image`（`python -m skills._sdk.notebook reference`）都一样 | 现场从当前代码生成，不会不一致 | 推荐 |
| c. 可以 `use_skill` 的文档 | 技能目录里多一行，约 20 token | `_` 开头的目录不是 skill，`tests/sdk/test_boundary.py::test_no_skill_md_under_sdk` 也不许 `_sdk` 下有 `SKILL.md`；只能做成一个真的 skill，skill 数 90 变 91，路由表、INDEX、计数守卫都要改，以后的进化循环也得把它排除在外 | 要生成并测试 | 不选 |
| d. 生成一份 `skills/_sdk/notebook/STEP_API.md` 提交进库，契约指向它 | 一句 | 课题目录与 checkout 分开时 `read_file` 读不到（`PathEscapesWorkspace`），仍要 `bash cat` | 要另写一致性测试 | 不选，比 b 多一个要同步的文件 |

#### 接口

`run.py reference [<function>]`：

- 不带参数时依次打印：一段路径规则（`read_input` 的路径相对课题根；`write_output` 与 `check_files` 的路径相对 `results/<NN_slug>/`，第一段是 4 个输出目录之一），然后是门面 `__all__` 的 5 个函数和 `checks.__all__` 的 7 个函数，每个函数一行签名（`inspect.signature`）加上 `inspect.getdoc` 的原文。`load_demo` 之后附上 `DEMOS` 注册表的名字和说明，从字面量生成，登记新数据集时自动跟上。
- 带函数名时只打印这一个。名字不存在时退出码 2，列出全部名字。
- 门面和 `checks` 在模块顶层只导入标准库，所以这个子命令不起 kernel，也不需要 nbclient。整段输出不超过 8,000 字符（`bash` 在 16,000 字符处截断），由测试钉住。

#### docstring 补什么

只补 0070 端到端里 agent 去源码里找过的规则：

- `read_input`：哪些路径算契约内（`data/`、`manifests/`、上游模块的 `intermediate/` 与 `tables/`、本模块的 results），契约外时 stderr 警告并记 `outside_contract`；按后缀选读取器，`.csv` 用 `pandas.read_csv`，数字样子的标签列会读成整数，比较时用 `checks.as_labels`，或传 `reader=lambda p: pd.read_csv(p, dtype={"leiden": str})`；目录和未知后缀返回 `Path`。
- `write_output`：可写的 4 个目录，允许子目录，不许 `..` 和绝对路径；默认写法逐条列出（`.h5ad`、`.csv`/`.tsv` 遇到 `RangeIndex` 不写索引、`.parquet`、`.png`/`.pdf`/`.svg` 用 dpi 150 与 `bbox_inches="tight"`、`.json` 用 `indent=2` 且 numpy 值转成列表、`.md`/`.txt` 只收字符串）；原子写入；模块冻结时报 `RuntimeError`。
- `load_demo`：查找顺序 `$OMICSCLAW_DEMO_DIR/<name>.h5ad` → checkout 的 `data/` → `examples/` → `$XDG_CACHE_HOME/omicsclaw/demo/`（未设时 `~/.cache/omicsclaw/demo/`）→ 用 scanpy 下载；返回 AnnData，记作输入。
- `run_cli`：skill 目录里唯一的、不以 `_` 开头的 `*.py`；不给 `--output` 时输出进 `results/<NN_slug>/intermediate/<skill>/`，给了就必须是 4 个输出目录之一下面的子目录；`inputs` 的作用；日志写 `logs/<step>__<skill>.log`；子进程去掉三个运行层环境变量，CLI 内部的调用不记账；输出目录里的每个文件补记为输出；非零退出时 `RuntimeError` 带日志末尾。
- `load_skill`：返回的模块只暴露 `__all__`，每次调用都记账；访问别的名字时 `AttributeError` 列出可用函数；没有 `_api.py` 时提示改用 `run_cli`。

#### 契约里指向它的一句

加在 "Writing a step" 的列表末尾，按 writing-for-agents 把触发条件写在前面：

> - Before your first step in a session, and whenever you need a detail of these functions, run the step runner's `reference` (or `reference <function>`): it prints what each step function and validate check accepts, the paths it takes, its default readers and writers, where `load_demo` looks and where `run_cli` puts its output.

措辞只写该做什么。照 writing-for-agents，写成"别读源码"这样的禁止句，反而会把读源码这件事带进上下文。

### 3.3 validate 检查函数

#### 位置

新文件 `skills/_sdk/notebook/checks.py`，步骤里写 `from skills._sdk.notebook.checks import check_columns, check_counts`。门面 `skills._sdk.notebook` 的 5 个名字不变：门面是"每个步骤都要用"的那一层，检查函数只在 validate 步骤里用，分开放能让门面的 `__all__` 保持短。其他放法见 Q3。

#### 接口

7 个函数出错时都抛 `AssertionError`，消息写明哪里不一致，最多列 5 处。函数里用 `raise`，不用 `assert` 语句，所以 `python -O` 下照样生效。模块顶层只导入标准库，不导入 pandas，靠鸭子类型处理 DataFrame、Series、list 和 dict。

```python
def as_labels(values) -> list[str]:
    """Return the values as label strings, so 0, 0.0, numpy.int64(0) and "0" all become "0".

    Integer-valued numbers lose their decimal part, other numbers keep their
    shortest repr, booleans become "True" or "False", strings pass unchanged.

    :raises AssertionError: a value is missing (None or NaN).
    """

def check_columns(table, columns) -> None:
    """Check that the table has every one of the columns; the message lists the missing and the present ones."""

def check_rows(table, *, exactly=None, at_least=1, at_most=None) -> None:
    """Check the table's row count; by default, that it has at least one row."""

def check_between(values, low=None, high=None) -> None:
    """Check that a number, or every number in a column or sequence, lies in [low, high]; NaN fails."""

def check_same_labels(left, right, *, ignore_order=False) -> None:
    """Check that two label columns hold the same labels, compared through as_labels."""

def check_counts(labels, table, *, key, count) -> None:
    """Check that table[count] gives, for each label in table[key], how many times it occurs in labels.

    Both sides go through as_labels, so a cluster column read back from a CSV
    as integers matches the categorical strings in adata.obs. The table must
    list every label once and no other.
    """

def check_files(*paths) -> list[Path]:
    """Check that each output exists and is not empty, and record it as an input of the step.

    Paths are relative to this module's results, as for write_output, for
    example figures/umap_leiden.png. Returns the absolute paths.
    """
```

0070 的两次失败用这组函数写出来是 `check_counts(adata.obs["leiden"], summary, key="cluster", count="n_cells")`，以及 `dict(zip(as_labels(matrix["leiden"]), …))`。`check_files` 记成 `input`（`via: "check_files"`）：图换了，validate 步骤就过期，摘要和 manifest 也能看到 validate 检查过哪些图。它要求在步骤里运行，路径规则复用 `_io.check_output_path`，不在步骤里时与 `write_output` 一样报 `RuntimeError`。

#### 守卫测试

`tests/sdk/test_public_surface.py` 的改法：

- `_sdk_modules()` 加上 `"skills._sdk.notebook.checks"`；
- `PUBLIC_SURFACE` 加 `"skills._sdk.notebook.checks": {as_labels, check_columns, check_rows, check_between, check_same_labels, check_counts, check_files}`；
- 7 个名字加进 `STEP_API` 豁免"每个冻结名都有使用者"：它们给 agent 在课题里写的 validate 步骤用，`skills/` 和 `templates/` 里没有自然的使用者，与 `read_input`、`run_cli` 的豁免理由相同。不为了凑使用者去改试点 skill 的示例（§1.2）。
- `skills._sdk.notebook` 一项保持 5 个名字。

### 3.4 契约与文档

`OMICSCLAW.md` 只改两处，都在 "Writing a step"：

1. 第一段最后一句，原文 "Every module has one `<k>_validate.py` step, which runs last and asserts what the report relies on: tables are non-empty, expected columns exist, counts are in range." 改为：

   > Every module has one `<k>_validate.py` step, which runs last and asserts what the report relies on with the checks in `skills._sdk.notebook.checks`: expected columns exist, tables are non-empty, counts are in range, a counts table agrees with the labels it counts, and the figures the report cites exist.

2. 列表末尾加 §3.2 的那一句。

审查摘要不需要改契约：`replay` 自动写，主线 agent 的做法不变。两处措辞定稿前先用 writing-for-agents 再过一遍，然后用 humanizer。用 `build_prompt(default_sections(config)).render().section_stats` 记下改动前后 contract 段的 token 数，预计增加约 120。`tests/sdk/notebook/test_contract.py` 新增一条：契约里以 "the step runner's `<命令>`" 形式提到的命令都存在于 `run.py` 的解析器。`tests/entry/golden/` 不受影响（golden 部署旁边没有 `OMICSCLAW.md`）。

文档：`docs/core-features/agent-skills.md` §9 补 `reference`、检查函数和审查摘要；`docs/core-features/sub-agent.md` §2.3.1 补摘要与新读法；`templates/skill/README.md` 不动。`README.md` 不动（不是头条功能）。`CHANGELOG.md` 顶部加一条。

### 3.5 防线账

| 编号 | 检查或限制 | 防什么 | 旁路 | 单人本机部署下值不值 |
|---|---|---|---|---|
| L1 | 摘要不超过 450 行 | 摘要本身变成一次大读取，审查又慢回去 | 审查者照样能读原文件 | 值。代价是截断逻辑和一条测试 |
| L2 | 审查提示里的读法（先摘要、二进制与 notebook 不读、大文件分段） | 审查者通读大文件和二进制，耗时变长 | 没有强制，审查者想读什么都能读 | 值，零成本。不做强制：给审查者换一个会拒读二进制的专用读取工具要改框架、加工具，还可能挡住某项检查确实需要的读取，先看 §5.2 的数据 |
| L3 | `check_files` 只认本模块 4 个输出目录下的路径 | validate 去检查别的模块的文件，检查对本模块失去意义 | `os.path.exists`、`read_input` | 值。复用 `write_output` 的路径检查，报错信息还能告诉 agent 正确的写法 |
| L4 | `reference` 的输出不超过 8,000 字符（测试） | 以后加函数让输出超过 `bash` 的 16,000 字符被截断，agent 只看到一半 | 没有 | 值。只是一条测试 |

不加的：`accept` 不要求有摘要，`replay` 也不因摘要写失败而失败，这两项会把一个辅助文件变成闸门，却挡不住什么真实的错误；审查子 agent 不加 `bash`，那违反 D13 的只读裁定（G5）。

---

## 4. 分期与工作量

P1 与 P2 互不依赖；P3 依赖 P1（契约里要写 `reference` 和 `checks`）；P4 在前三期之后。分支 `plan-0071-runtime-polish`，每期一个提交，不推送，推送和开 PR 由 owner 决定。提交说明过 humanizer，不带 Claude 署名。

| 阶段 | 任务 | 估计 |
|---|---|---|
| P1 检查函数与参考 | `checks.py`；`_io.py`、`_skills.py` 的 docstring 按 §3.2 补全；`run.py reference`；`test_public_surface.py` 按 §3.3；新测试 `tests/sdk/notebook/test_checks.py`、`test_reference.py` | 1.5 天 |
| P2 审查摘要与提示 | `_brief.py`；`_replay_locked` 的调用与失败时删除；`LAYOUT["review_brief"]` 与 `project.REVIEW_BRIEF_FILE`；`MODULE_REVIEWER_PROMPT`；新测试 `tests/sdk/notebook/test_brief.py`，`test_replay.py`、`test_contract.py`、`tests/entry/test_subagent_wiring.py` 各加几条 | 1.5 天 |
| P3 契约与文档 | §3.4 的两处措辞、契约测试、token 记录、文档、`CHANGELOG.md` | 0.5 天 |
| P4 真实会话验收 | §5.2 的 A/B 审查与缩短端到端；实施记录 `docs/plans/0071-runtime-polish-delivery.md` | 1.5 天（主要是墙钟时间） |
| 合计 | | 约 5 天 |

---

## 5. 测试与验收

命令：`PYTEST` = `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`；`OCPYTEST` = `/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:randomly`，只用于试点 skill 的示例和 parity 测试，不拿它跑 `tests/launch/test_surfaces.py`（会挂住）。只跑新增与相关的测试，不跑全量。三期都改 `skills/`，每期都加跑顶层的 `PYTEST tests/test_*.py`（约 35 秒）。已知无关的失败：`tests/tools/test_workspace.py`，以及 `tests/ci_known_failures.txt` 里的条目。

### 5.1 单元测试与守卫

| 阶段 | 新测试要点 | 验收命令 |
|---|---|---|
| P1 | `test_checks.py`：复现 0070 的两次失败（`iterrows` 后的 `0.0`、CSV 读回的整数索引），改用 `check_counts` 与 `as_labels` 后通过；多一个、少一个标签和计数不符时消息正确；NaN 与 None 报缺失；`python -O` 下照样抛错；`check_files` 记 `input`、拒绝 4 个目录以外的路径、空文件失败；AST 扫描确认 `checks.py` 顶层只导入标准库。`test_reference.py`：输出含两个 `__all__` 的全部名字、`DEMOS` 的全部名字、`LAYOUT["output_dirs"]` 的 4 个目录；总长不超过 8,000 字符；`reference write_output` 只打印一个；未知名字退出码 2 | `PYTEST tests/sdk/notebook/test_checks.py tests/sdk/notebook/test_reference.py tests/sdk/notebook/test_contract.py tests/sdk/test_public_surface.py tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py tests/test_*.py` |
| P2 | `test_brief.py`（假 runner）：重放成功后摘要存在，失败后旧摘要被删；步骤段含第一个 cell 原文与记账调用，"Word match" 两个方向都能报出不一致；小表全文、大表只给前 5 行和形状；二进制不预览；孤儿文件有标记；60 张表的模块不超过 450 行并写明截断；原子写。`test_contract.py`：`LAYOUT["review_brief"] == project.REVIEW_BRIEF_FILE`，审查提示含这个路径。`test_subagent_wiring.py`：审查子 agent 的工具仍只有两项 | `PYTEST tests/sdk/notebook tests/entry/test_subagent_wiring.py tests/entry/test_ensemble_golden.py tests/test_*.py`；`PYTEST tests/evals/dataset -m scripted_eval`（29 条，用例 6、7 走重放和审查）；`OCPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py` |
| P3 | 契约里 "the step runner's `<命令>`" 都存在 | `PYTEST tests/entry/test_runtime_contract.py tests/entry/test_assembly.py tests/sdk/notebook/test_contract.py tests/sdk/test_replot_hint.py tests/planning/test_render.py tests/entry/test_ensemble_golden.py` |

### 5.2 真实会话对比

审查提示和契约措辞会改变 agent 的行为，按 owner 的要求用真实会话验证。模型取 `.env`（0070 用的是 deepseek 的默认模型），权限模式 auto-approve，解释器 `/opt/conda/envs/OmicsClaw/bin/python`。

#### 计量

驱动脚本以 0070 的 `/tmp/oc0070-e2e/drive.py` 为底，增加两处只在脚本里生效的包装：包一层 `omicsclaw.tools.builtin.read._read`，每次调用记时间、路径、行或字节参数、返回字符数；包一层 `omicsclaw.entry.subagent.report_usage`，记子 agent 每轮的 token。`task` 是 `concurrency_safe=False`，主线在委派期间被挡住，所以 `task` 调用时间窗里的 `read_file` 都算审查者的。读 `_sdk` 源码的计数规则：命令或 `read_file` 路径里出现 `skills/_sdk/` 下的 `.py` 文件，或出现 `skills._sdk.notebook._` 开头的私有模块名，并且不是一次执行器调用。按这条规则，0070 是 8 次。

#### A/B 审查

目录 `/tmp/oc0071-ab/`，脚本 `ab_review.py`：

1. 把 `/tmp/oc0070-e2e/project` 复制过来，用新代码对 5 个模块依次 `revise`、`replay`，生成摘要。两组看到的步骤文件、REPORT、输出完全相同。
2. A 组：在副本的 `.omicsclaw/agents/module-reviewer.md` 里放 0070 的提示原文（工具同样只有 `read_file`、`use_skill`），按现有规则原位替换内置定义。B 组：删掉这个文件，用新的内置提示。
3. 脚本照 `drive.py` 的做法 `open_app`，取 `app.registry` 里的 `task` 工具直接 `execute`，提示固定为 `Review module <NN_slug>`，避免主线 agent 每次写的委派提示不同。每组每个模块跑 1 次。
4. 预设缺陷模块：另复制一份 `03_cluster`，植入 4 处缺陷后重放：(1) 步骤第一个 cell 写着调用 `auto_resolution`，实际没调（第 1 项）；(2) 删掉 validate 里核对 `cluster_summary.csv` 的断言，而 REPORT 的数字来自这张表（第 2 项）；(3) REPORT 把 cluster 0 的 588 个细胞写成 598（第 3 项）；(4) REPORT 引用不存在的 `figures/umap_louvain.png`（第 3 项）。A、B 各审 1 次。第 4 项没法植入：在重放之后改步骤文件，manifest 要等下一次运行才会重建，审查者看不出来；这一项由 `accept` 机械核对（G3）。

#### 缩短的端到端

目录 `/tmp/oc0071-e2e/`。沿用 0070 的消息 m01 至 m04 原文，再加一条 "I accept module 03_cluster. Thank you, no summary needed."，产生 3 个模块（01_qc 经 `run_cli` 用到 sc-filter，03_cluster 是 0070 里 validate 出错的那一类）。

#### 指标与基线

| 指标 | 0070 基线 | 0071 从哪里来 |
|---|---|---|
| 每次审查耗时 | 01 至 03 首审 265、417、372 s，02 复审 101 s；5 模块首审中位数 314 s | A/B 两组与端到端 |
| 每次审查的 `read_file` 次数与返回字符数 | 当时没记，由 A 组补测 | 包装 `_read` |
| 审查者的模型轮次与输入 token | 当时没单独记，由 A 组补测 | 包装 `report_usage` |
| 读 `_sdk` 源码的次数 | 8（前 3 条消息） | 端到端日志 |
| validate 步骤第一次运行就失败的模块数 | 前 3 个模块里 1 个，5 个模块里 2 个；失败的 validate 运行共 3 次 | 端到端的 manifest 历史 |
| 主线模型调用与墙钟（消息 1 至 4） | 70 次，1,724 s | 端到端日志 |
| `reference` 的调用次数；validate 步骤用了哪些检查函数 | 无 | 端到端日志与步骤文件 |

#### 通过标准

1. 预设缺陷：B 组判 REVISE，并且 4 处缺陷都有对应的 finding。这是硬条件，达不到就不合入审查提示的改动，摘要可以保留，回到 owner 商量。
2. 干净模块：B 组首审耗时的中位数不超过 A 组的一半，`read_file` 返回字符数的中位数不超过 A 组的四分之一。达不到时如实记录，连同 Q4 一起带回 owner。
3. A 判 REVISE 而 B 判 APPROVE 的模块，实施者逐条对照 4 项检查核对 A 的 findings，写明是 B 漏了清单内的问题，还是 A 的 finding 落在清单之外。
4. 端到端：3 个模块都到 `ACCEPTED`；读 `_sdk` 源码不超过 1 次；validate 第一次运行就失败的模块为 0。每组只跑一次，后两项是期望值：没达到时记下 agent 读了什么、validate 错在哪里，据此补 docstring 或检查函数，再跑一次。

只跑一轮，不追求统计意义；时间、调用次数、遇到的问题如实写进实施记录。

---

## 6. 风险

| 编号 | 风险 | 处理 |
|---|---|---|
| R1 | 审查者信了摘要，漏掉原文件里的错（例如大表深处的一个错数） | 小表给全文；提示保留"every number matches a table"，允许按行号读大表；§5.2 的预设缺陷 |
| R2 | 重放之后有人用 `bash` 直接改了输出，摘要与文件不符 | 摘要写明生成它的重放时间；绕过执行器写文件本来就在 0070 R9 的范围内，`accept` 照样核对重放覆盖当前步骤 |
| R3 | 真实模型的波动让一次 A/B 不足以说明问题 | 5 个模块各跑一次，给出全部原始数字；结论只说观察到的差别 |
| R4 | agent 不跑 `reference`，照旧读源码 | 端到端里计数；读了就看缺的是哪条规则，补进 docstring；仍然不行再考虑 Q2 的 a |
| R5 | `as_labels` 把本来该区分的值并成一个（例如 `1` 和 `1.0` 本意不同） | validate 里比较的是标签，这种情况罕见；规则写进 docstring 和 `reference` |
| R6 | 摘要让重放变慢 | 只读文本文件、按行计数，`de_full.csv`（12.4 MB）用 `csv` 模块数行实测 0.12 s；实施记录写下 5 个模块重放前后的耗时 |
| R7 | 公开面扩大后再改名代价变大，后续迁移批次也会依赖这组函数 | 只放 7 个、名字按用途起；`test_public_surface.py` 冻结，以后增删都要改冻结表 |

---

## 7. 裁定与待裁定的问题

### 7.0 owner 裁定（2026-10-02）

Q1 至 Q5 全部按推荐：Q1 选 a，Q2 选 b，Q3 选 a，Q4 选 a，Q5 选 a。下面保留各题的选项与理由备查。

### Q1 审查摘要由谁、在什么时候写

- a. `replay` 成功时自动写；REPORT 的引用由审查者对照摘要里的文件清单核对。
- b. 新子命令 `brief analysis/<NN_slug>`，主线 agent 在写完 REPORT、委派审查之前运行，摘要里还能机械地列出 REPORT 引用了却不存在或已是孤儿的文件。
- c. 两者都做。

推荐 a。主线 agent 的步骤不变，契约不用改；b 多一步，agent 忘了跑就没有摘要。REPORT 引用的核对靠文件清单就能完成，b 多出来的那部分审查者自己就能做。

### Q2 步骤 API 参考放在哪里

- a. 写进契约；b. `run.py reference` 从 docstring 现场生成（§3.2）；c. 做成可以 `use_skill` 的文档；d. 生成 `STEP_API.md` 提交进库，契约指向它。

推荐 b。每轮只多一句话，任何部署下都能取到，内容直接来自代码。比较见 §3.2 的表。

### Q3 检查函数放在哪里

- a. 新子模块 `skills._sdk.notebook.checks`，门面保持 5 个名字，冻结表加一项。
- b. 直接加进门面，门面变成 12 个名字。
- c. 放进 `skills/singlecell/_lib`。

推荐 a。只有 validate 步骤用它们，分开放门面最短。c 的位置不合适：这些检查与组学领域无关，空间和 bulkrna 迁移后也要用。

### Q4 审查提示要不要再限定清单以外的核对

- a. 这次不加，先看 §5.2 的数据。
- b. 加一句：清单以外的发现只在会改变数字、图或结论时才写。

推荐 a。0070 的审查做了不少清单以外的核对，其中一些有用（02 的 REVISE 指出 README 与 REPORT 互相矛盾）。读法改了以后这类核对可能自然变少。如果数据显示仍然慢，再按 b 改，并重跑预设缺陷。

### Q5 真实会话验收的规模

- a. A/B 审查（5 个干净模块加 1 个预设缺陷模块）加 3 个模块的缩短端到端（§5.2）。
- b. 只跑 3 个模块的缩短端到端。
- c. 重跑完整的 5 个模块端到端。

推荐 a。审查耗时的比较需要同样的输入，A/B 在同一批模块上比；预设缺陷验证"清单没有被削弱"，端到端看不出这一点。agent 是否还读源码、validate 是否还踩类型坑，只有端到端能看到，3 个模块已经覆盖 `run_cli` 和标签计数这两类。c 多出 annotate、DE 两个模块，0070 里这两条消息约 13 分钟；04 的 validate 失败与 03 是同一根因，预计看不到新的现象。
