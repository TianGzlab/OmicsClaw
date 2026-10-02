# 计划 0071 交付记录：运行层打磨

日期：2026-10-02。规格：`docs/plans/0071-runtime-polish.md` 第 1 版（定稿，owner 裁定 Q1 至 Q5 全按推荐，见计划 §7.0）。本记录不改动计划正文。
范围：P1 至 P4 四期，P4 包括 A/B 审查和 3 个模块的缩短端到端。
状态：四期都已实施，每期一个提交，只在本地分支 `plan-0071-runtime-polish` 上，没有推送。计划 §5.2 的通过标准：第 1 条（硬条件）两轮都通过；第 2 条里耗时减半达到了，读取字符降到四分之一没有达到；第 4 条达到，见 §6。
开工状态：`main` 的 `4c2fc4d9`，工作树只有未跟踪的计划文件。

## 1. 结论

| 阶段 | 提交 | 验收结论 | 关键证据 |
|---|---|---|---|
| 计划 | `222a4470` | 不适用 | 只含计划文件（状态行改为定稿，加 §7.0 owner 裁定） |
| P1 检查函数与参考 | `89ae1ec5` | 通过 | 新增与相关测试 59 passed、1 skipped；顶层 228 passed、4 skipped、1 xpassed；`tests/sdk/notebook` 195 passed |
| P2 审查摘要与提示 | `1260c621` | 通过 | 382 passed、1 skipped；顶层 228 passed；scripted eval 29 passed；示例 5 passed；`tests/evals` 186 passed |
| P3 契约与文档 | `de104ae1` | 通过 | 102 passed、1 skipped、1 xfailed；契约段 3,758 → 3,877 token |
| P4 真实会话验收 | 本记录随之提交 | 硬条件通过；耗时目标达到；读取字符目标未达到 | 见 §5、§6 |

P4 的提交同时带上审查提示的一处补充（§5.3），以及本记录。

## 2. P1：检查函数与步骤 API 参考

改动：
- 新增 `skills/_sdk/notebook/checks.py`：`as_labels`、`check_columns`、`check_rows`、`check_between`、`check_same_labels`、`check_counts`、`check_files`。全部抛 `AssertionError`（用 `raise`，`python -O` 下照样生效），模块顶层只导入标准库和运行层自身。`check_files` 的路径规则复用 `_io.check_output_path`，把通过检查的文件记成 `input`（`via: "check_files"`）。
- `_io.py` 的 `read_input`、`write_output`、`load_demo` 与 `_skills.py` 的 `load_skill`、`run_cli` 的 docstring 按计划 §3.2 补全：契约内的路径、按后缀的读取器、CSV 里数字样子的标签会读成整数、默认写法逐条、`load_demo` 的查找顺序、`run_cli` 的脚本选择、`--output` 规则、日志位置与报错。
- 新增 `skills/_sdk/notebook/_reference.py` 和 `run.py reference [<function>]`。签名用 `_apidoc.signature` 从源码的 AST 还原（`inspect.signature` 在 `from __future__ import annotations` 下会把注解打成带引号的字符串），说明取 `ast.get_docstring`；`load_demo` 之后附 `DEMOS` 注册表。整段输出 7,823 字符。
- `tests/sdk/test_public_surface.py`：`_sdk_modules()` 加 `skills._sdk.notebook.checks`，`PUBLIC_SURFACE` 加 7 个名字，并全部加进 `STEP_API` 豁免；门面仍是 5 个名字。
- 新测试 `tests/sdk/notebook/test_checks.py`（22 条，含 0070 两次 validate 失败的复现）、`test_reference.py`（6 条）。

验收：

```
PYTEST tests/sdk/notebook/test_checks.py tests/sdk/notebook/test_reference.py tests/sdk/notebook/test_contract.py \
  tests/sdk/test_public_surface.py tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py
  59 passed, 1 skipped（skip 是要 OMICSCLAW_TEST_SANDBOX=1 的那条）
PYTEST tests/test_*.py
  228 passed, 4 skipped, 1 deselected, 1 xpassed
PYTEST tests/sdk/notebook
  195 passed, 5 deselected（skill_example 标记）
只有标准库的 venv（python -m venv --without-pip），PYTHONPATH=<checkout>：
  import skills._sdk.notebook.checks、as_labels、check_counts 都能用；run.py reference 输出 7,823 字符
reference 进程里没有导入 nbformat、nbclient、pandas、anndata、numpy、scanpy
```

## 3. P2：审查摘要与审查提示

改动：
- 新增 `skills/_sdk/notebook/_brief.py`。`_replay_locked` 在跑任何步骤之前删掉旧摘要，重放成功后写 `results/<NN_slug>/provenance/review_brief.md`（先写临时文件再改名），输出末尾加一行 `review brief: …`。写摘要遇到 `OSError`、`ValueError`、`UnicodeDecodeError` 只打警告，重放结果不变；单张表读不了时摘要里写明原因，不影响其余部分。
- 内容按计划 §3.1。超过 450 行时按 5 级逐步收缩：先去掉大表的前几行，再把日志缩到 3 行，再把小表全文和第一个 cell 缩短，最后只列前 60 个文件；每一级都在开头写明 "Shortened to fit"。
- `contract.py` 的 `LAYOUT` 加 `"review_brief": "provenance/review_brief.md"`；`omicsclaw/entry/project.py` 加 `REVIEW_BRIEF_FILE`，`test_contract.py` 钉住相等。
- `MODULE_REVIEWER_PROMPT` 按计划 §3.1 的草稿改写（用 f-string 引用 `REVIEW_BRIEF_FILE`）。`tests/entry/test_subagent_wiring.py` 新增一条，把 4 项检查和结论规则逐字钉住。`description` 没改，golden 不变。
- 新测试 `tests/sdk/notebook/test_brief.py`（9 条）；`test_contract.py` 加 2 条。

验收：

```
PYTEST tests/sdk/notebook tests/entry/test_subagent_wiring.py tests/entry/test_ensemble_golden.py \
  tests/entry/test_entry_is_the_top_layer.py tests/sdk/test_boundary.py tests/sdk/test_public_surface.py
  382 passed, 1 skipped, 5 deselected
PYTEST tests/test_*.py                                  228 passed, 4 skipped, 1 deselected, 1 xpassed
PYTEST tests/evals/dataset -m scripted_eval             29 passed
OCPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py    5 passed（40.3 s）
PYTEST tests/evals                                      186 passed, 26 deselected
```

## 4. P3：契约与文档

改动：
- `OMICSCLAW.md` "Writing a step" 两处，措辞照计划 §3.4（定稿前按 writing-for-agents 又看了一遍）：validate 那句点名 `skills._sdk.notebook.checks` 并多列两类检查；列表末尾加一条，要求在会话里写第一个步骤之前、以及需要细节时运行执行器的 `reference`。
- `test_contract.py` 加 2 条：契约里以 "the step runner's `<命令>`" 提到的命令都存在于解析器；契约点名的检查模块就是 `checks.__name__`。
- `docs/core-features/agent-skills.md` §9.1 补检查函数、`reference` 和审查摘要；`sub-agent.md` §2.3.1 改写审查者的读法；`CHANGELOG.md` 顶部加一条。

contract 段的 token 数（`build_prompt(default_sections(config)).render().section_stats`，课题目录部署）：改动前 3,758，改动后 3,877，增加 119，与计划估计的约 120 一致。

验收：

```
PYTEST tests/entry/test_runtime_contract.py tests/entry/test_assembly.py tests/sdk/notebook/test_contract.py \
  tests/sdk/test_replot_hint.py tests/planning/test_render.py tests/entry/test_ensemble_golden.py
  102 passed, 1 skipped, 1 xfailed（已知的 cli/_configure.py:482）
PYTEST tests/test_*.py                                  228 passed, 4 skipped, 1 deselected, 1 xpassed
```

## 5. P4 之一：A/B 审查

### 5.1 做法

- `/tmp/oc0071-ab/project` 是 `/tmp/oc0070-e2e/project` 的副本（去掉会话库）。用新代码依次对 5 个模块 `revise`、`replay`，5 次重放都成功并写出摘要（01_qc 302 行，其余 85 到 134 行），耗时 9 到 20 秒。
- A 组：在副本的 `.omicsclaw/agents/module-reviewer.md` 放 0070 的提示原文（从 `4c2fc4d9` 的源码用 AST 取出），工具 `read_file, use_skill`；先离线确认注册表加载的确实是这份定义。B 组：去掉这个文件，用内置提示。
- 脚本 `/tmp/oc0071-ab/ab_review.py` 照 `drive.py` 的做法 `open_app`，经 `app.registry.execute` 调 `task`，提示固定为 `Review module <NN_slug>`。脚本内包了三层，只在脚本里生效：`read._read`（每次读取的路径、参数、返回字符数、错误）、`subagent.report_usage`（子 agent 每轮的 token）、`subagent.report_progress`（子 agent 的工具调用）。
- 预设缺陷：`/tmp/oc0071-ab/seeded` 是重放后的再一份副本。在 `03_cluster` 植入 4 处：(1) 第一个 cell 写着调用 `auto_resolution`，实际没调；(2) 删掉 validate 里核对 `cluster_summary.csv` 的整个 cell，`summary` 读了但不用；(3) REPORT 把 cluster 0 的 588 写成 598；(4) REPORT 的 Outputs 加一行不存在的 `figures/umap_louvain.png`。改完步骤后重放（摘要的 Word match 一行因此报出 `named but not recorded: sc-clustering.auto_resolution`），再改 REPORT。
- 第 1 轮：先审预设缺陷模块（B、A），再按模块交替跑 A、B。第 2 轮见 §5.3。

### 5.2 第 1 轮

| 组 | 模块 | 结论 | 耗时 s | `read_file` 次数 | 返回字符 | 出错的读取 | 模型轮次 | 输入 token | 输出 token |
|---|---|---|---|---|---|---|---|---|---|
| A | 01_qc | APPROVE | 272.7 | 63 | 234,003 | 21 | 24 | 1,456,117 | 31,992 |
| A | 02_preprocess | APPROVE | 331.0 | 70 | 80,481 | 41 | 40 | 1,217,119 | 42,339 |
| A | 03_cluster | APPROVE | 295.7 | 77 | 117,487 | 37 | 32 | 1,278,528 | 46,470 |
| A | 04_annotate | `## VERDICT: APPROVE` | 192.8 | 64 | 90,816 | 36 | 22 | 513,559 | 26,957 |
| A | 05_de | APPROVE | 230.3 | 70 | 312,355 | 42 | 22 | 1,738,209 | 37,603 |
| B | 01_qc | APPROVE | 133.9 | 26 | 207,712 | 2 | 18 | 843,414 | 16,162 |
| B | 02_preprocess | APPROVE | 114.8 | 26 | 67,958 | 4 | 16 | 372,401 | 13,523 |
| B | 03_cluster | APPROVE | 133.1 | 26 | 69,260 | 1 | 16 | 391,288 | 19,183 |
| B | 04_annotate | APPROVE | 199.4 | 45 | 82,886 | 19 | 21 | 685,334 | 28,800 |
| B | 05_de | APPROVE | 219.6 | 30 | 88,196 | 5 | 23 | 856,275 | 31,178 |

中位数：A 耗时 272.7 s、读取 70 次、117,487 字符、24 轮、输入 1,278,528 token；B 耗时 133.9 s、读取 26 次、82,886 字符、18 轮、输入 685,334 token。耗时比 0.49，读取字符比 0.71。5 次审查合计：A 1,322.5 s，B 800.8 s。

预设缺陷模块：

| 组 | 结论 | 找到的预设缺陷 | 额外的发现 | 耗时 s | 读取次数 | 返回字符 | 模型轮次 |
|---|---|---|---|---|---|---|---|
| B | REVISE | 4/4 | 无 | 59.2 | 17 | 34,602 | 8 |
| A | REVISE | 4/4 | 1 条误报：把 REPORT 里的 "README" 当成 `results/03_cluster/README.md`，读不到就判为缺失（实际指 `analysis/03_cluster/README.md`） | 64.5 | 23 | 43,656 | 11 |

读法上的差别（逐条看过 `/tmp/oc0071-ab/runs_r1/*.json` 的读取记录）：
- A 靠猜路径找文件，每次审查有 21 到 42 次读取失败（`results/03_cluster/01_cluster_umap.py`、`results/03_cluster/runs/...` 这类）；B 有 1 到 19 次，04_annotate 那次多是在找并不存在的 `README.md`、`plan.md`、`project.json`。
- A 读了 12 次 notebook、12 次二进制文件（h5ad、png）；B 读了 5 次 notebook，没有读二进制。
- B 不带 `start_line` 读摘要，`read_file` 落到字节模式，只返回前 8 KB，01_qc 的摘要（13.9 KB）因此又分两次读完；读步骤文件和 REPORT 也先用字节模式，再用 `start_line` 重读一遍，只为了拿到行号。
- 01_qc 两组都把 2,700 行的 `qc_metrics_per_cell.csv` 整份分页读完（B 6 次、约 15 万字符），用来核对 REPORT 里按阈值数出来的细胞数，这是第 3 项检查本身要做的事。
- 两组都会去读上游模块的 REPORT、manifest、validate 步骤，以及副本里 `revise` 留下的修订记录和 `reviews/archive/` 里 0070 的旧审查。后一类是 A/B 副本特有的：首次审查的模块没有这些文件。

### 5.3 审查提示的补充与第 2 轮

第 1 轮里，B 读摘要时落到字节模式、读步骤文件又各读两遍，原因是提示没说用行模式。计划 §3.1 设想的是"一次行模式 `read_file` 读完摘要"，所以这是实现没跟上设计，不是改设计。补充两处措辞（4 项检查和结论规则不动，`test_subagent_wiring.py` 的逐字钉住照样通过）：
- 第 1 步：`read it with start_line=1, which returns it whole.`
- 第 2 步：`each in full with start_line=1, so every line comes back numbered for your findings.`

然后重跑 B 的 6 次审查，另跑 1 次 A（03_cluster）看时段漂移。补充之后的测试：

```
PYTEST tests/entry/test_subagent_wiring.py tests/sdk/notebook/test_contract.py tests/entry/test_ensemble_golden.py \
  tests/sdk/notebook/test_brief.py                       83 passed, 1 skipped
PYTEST tests/test_*.py                                  228 passed, 4 skipped, 1 deselected, 1 xpassed
PYTEST tests/evals/dataset -m scripted_eval             29 passed
```

| 组 | 模块 | 结论 | 耗时 s | 读取次数 | 返回字符 | 出错的读取 | 模型轮次 | 输入 token | 输出 token |
|---|---|---|---|---|---|---|---|---|---|
| B | 预设缺陷 03_cluster | REVISE，4/4，另有 1 条：`embedding="umap"` 没写理由（属实） | 38.6 | 9 | 22,599 | 1 | 7 | 51,902 | 4,885 |
| B | 01_qc | APPROVE | 142.2 | 29 | 204,435 | 8 | 16 | 1,094,258 | 19,721 |
| B | 02_preprocess | APPROVE | 70.0 | 16 | 48,736 | 1 | 11 | 183,211 | 9,550 |
| B | 03_cluster | APPROVE | 145.7 | 27 | 156,321 | 4 | 15 | 578,152 | 21,184 |
| B | 04_annotate | APPROVE | 84.8 | 17 | 45,794 | 3 | 11 | 168,575 | 11,749 |
| B | 05_de | APPROVE | 116.3 | 28 | 70,276 | 7 | 12 | 300,191 | 17,027 |
| A（漂移对照） | 03_cluster | APPROVE | 204.5 | 67 | 78,030 | 23 | 23 | 613,930 | 32,353 |

B 第 2 轮中位数：耗时 116.3 s、读取 27 次、70,276 字符、12 轮、输入 300,191 token；5 次合计 559.0 s。同一模块上 A 这次比第 1 轮快 31%（204.5 对 295.7 s），说明这一时段服务本身更快，所以第 2 轮的 B 与第 1 轮的 A 相比会偏乐观；第 1 轮 A、B 交替跑，两者的比值更可靠。第 2 轮 B 的 03_cluster 读了一本 64 KB 的 notebook 和 0070 的旧审查，字符数因此偏高。

### 5.4 对照通过标准

1. 预设缺陷（硬条件）：通过。B 两轮都判 REVISE，4 处缺陷都有对应的 finding；摘要的 Word match 一行直接报出了第 (1) 处。
2. 干净模块：耗时中位数第 1 轮 133.9 对 272.7 s（0.49），达到"不超过一半"；返回字符中位数第 1 轮 0.71、第 2 轮 0.60，没达到"不超过四分之一"。按计划如实记录，连同 Q4 带回 owner，见 §8 第 1 条。字符数不是好的代价指标：A 有大量读取失败，失败的读取返回 0 字符，却照样各花一轮模型调用。每次审查的输入 token 更接近真实代价，中位数从 A 的 1,278,528 降到 B 第 1 轮的 685,334（0.54）、第 2 轮的 300,191（0.23）。
3. A 判 REVISE 而 B 判 APPROVE 的模块：没有，干净模块两组都是 APPROVE。另外，A 在 04_annotate 的第一行写成了 `## VERDICT: APPROVE`，`accept --review` 会拒收；B 两轮共 12 次审查，第一行都合格。

## 6. P4 之二：3 个模块的缩短端到端

### 6.1 做法

课题目录 `/tmp/oc0071-e2e/project`（起始为空），`OMICSCLAW_SKILLS_DIR=<checkout>/skills`，模型取 `.env`（与 0070 相同的 provider，模型用其默认值），权限模式 auto-approve。驱动 `/tmp/oc0071-e2e/drive.py` 是 0070 驱动的副本，另包了 `read._read`、`subagent.report_usage` 和 `ChildRunner.delegate`，把每次读取记到主线或审查者名下，每条消息写一份 `logs/<tag>.trace.json`。消息 1 至 4 是 0070 的原文，消息 5 是 "I accept module 03_cluster. Thank you, no summary needed."。由我扮演用户。

### 6.2 过程

| # | 用户消息（摘要） | agent 做了什么 | 主线模型调用 | 墙钟 |
|---|---|---|---|---|
| 1 | 用 pbmc3k_raw 走完整流程，先做 QC | `status`、`reference`、`new qc`、两个步骤（validate 调用了 5 个检查函数）、`run`；没先重放就委派审查，审查者找不到摘要，判 REVISE（REPORT 里 `pct_counts_mt < 20` 去掉的细胞数差 1；没有重放记录）；修好、`replay`、复审 APPROVE；请我选阈值并验收 | 20 | 453 s |
| 2 | 选方案 A（200 至 2,500 基因、线粒体 < 5%、基因至少 3 个细胞），请把 QC 模块做完 | 把这句当作验收，`accept 01_qc`；随即建 `02_preprocess`（经 `run_cli` 调 sc-filter，再 sc-preprocessing），`replay`、审查 APPROVE；又重放了一次，旧审查被存档，复审 APPROVE | 17 | 683 s |
| 3 | 接受 01，做预处理 | 预处理上一条已做完，只报告结果并请我验收 02 | 2 | 14 s |
| 4 | 接受 02，聚类并做 UMAP | `accept 02_preprocess`；`new cluster`、步骤、`run`；又一次没先重放就委派审查，REVISE（没有重放记录；validate 没断言图结构）；修好、`replay`、复审 APPROVE | 11 | 280 s |
| 5 | 接受 03 | `accept 03_cluster` | 2 | 16 s |
| 合计 | | 6 次审查 | 52 | 1,446 s |

`status` 最后显示 3 个模块都是 `ACCEPTED`。

### 6.3 指标对比

| 指标 | 0070 §8（消息 1 至 4，模块 01 至 03） | 0071 缩短端到端 |
|---|---|---|
| 每次审查耗时 | 265、417、101（复审）、372 s；中位数 318 s | 206（REVISE，未重放）、124（复审）、351、114（重放后复审）、117（REVISE，未重放）、47（复审）s；中位数 121 s |
| 审查合计 | 4 次，1,154 s，占墙钟 67% | 6 次，959 s，占墙钟 66% |
| 每次审查的 `read_file` 次数与返回字符 | 没有记录 | 41 / 175,963；20 / 256,727；49 / 235,794；20 / 89,057；27 / 147,790；14 / 27,753 |
| 读 `_sdk` 源码的次数 | 8 | 0（`reference` 调用 1 次，在消息 1） |
| validate 第一次运行就失败的模块 | 3 个里 1 个（03_cluster，失败的运行 2 次） | 0 个 |
| validate 步骤用的检查函数 | 无 | 3 个模块都用：01 调用 5 个（另导入了 `as_labels`、`check_counts` 但没用），02 调用 3 个，03 调用 `check_columns`、`check_rows`、`check_counts`、`check_files` |
| 主线模型调用与墙钟 | 70 次，1,724 s（03 还没 accept） | 52 次，1,446 s（3 个模块都已 accept） |

### 6.4 对照通过标准第 4 条

3 个模块都到 `ACCEPTED`；读 `_sdk` 源码 0 次（期望不超过 1 次）；validate 第一次运行就失败的模块 0 个（期望 0）。都达到，没有再跑第二次。

审查的单次耗时降下来了，但次数从 4 次变成 6 次：两次是 agent 没先 `replay` 就委派审查（契约 "Finishing a module" 第 1 步要求先重放），一次是审查通过后又重放、旧审查被存档，只好复审。所以审查占墙钟的比例和 0070 差不多。见 §8 第 2、5 条。

## 7. 偏差

都没有改变 0070 的 D、O 裁定或 0071 的 Q 裁定，也没有扩大范围。

1. `reference` 的签名用 `_apidoc.signature` 从源码 AST 还原，没用计划写的 `inspect.signature`：模块开了 `from __future__ import annotations`，`inspect.signature` 会把注解打成带引号的字符串。
2. 审查提示在 P4 第 1 轮之后补了两处 `start_line=1`（§5.3），随 P4 提交。计划 §3.1 本来就设想审查者用一次行模式读完摘要，补充没有碰 4 项检查和结论规则。
3. 计划 §4 说 `test_replay.py` 加几条；与摘要相关的重放测试都放在新文件 `test_brief.py` 里，`test_replay.py` 没改。
4. `test_contract.py` 多加了一条"契约点名的检查模块就是 `checks.__name__`"，计划没列。
5. A/B 多跑了第 2 轮（B 6 次，A 1 次漂移对照），计划只写了一轮。第 1 轮的记录保存在 `/tmp/oc0071-ab/runs_r1/`，第 2 轮在 `runs/`。
6. 摘要里的 "changed outputs" 照抄 manifest：模块第一次重放时，之前不存在的输出也算 changed（0070 `replay` 的既有语义），第一次重放的摘要因此会把全部输出标成 "changed by this replay"。

## 8. 遗留问题

1. 读取字符没有降到四分之一（§5.4 第 2 条）。剩下的大头有三类：为核对 REPORT 里按阈值数出来的数字而分页读整张大表（01_qc 每次约 15 万字符），读上游模块的文件，以及主线 agent 的委派提示本身要求逐项追查。可选的下一步：按 Q4 的 b 给审查提示加一句，限定清单以外的核对；或者在摘要里给大表的数值列加 min、中位数、max。两者都会改变审查行为，要 owner 定，定了以后要重跑预设缺陷。
2. agent 两次没先 `replay` 就委派审查，审查者找不到摘要，从 manifest 读起，花 206 s 和 117 s 才判 REVISE。可以让审查提示把"没有摘要"直接当作"没有重放"，一开始就判 REVISE；这会改变审查行为，没做，留给 owner。
3. 消息 2 只说"把 QC 模块做完"，agent 就运行了 `accept 01_qc`。这是 0070 G3 已知的局限：用户确认只靠契约，执行器无法核实。
4. 审查通过后 agent 又重放了一次 02_preprocess，重放把审查存档（O7 的设计），只好复审，多花 114 s。
5. `reference` 的输出 7,823 字符，离测试上限 8,000 只差 177 字符；以后再加函数要先精简 docstring，或者调整上限。
6. sandbox 验收仍待有 docker 的机器（0070 §11 第 1 条，未变）。

临时文件：A/B 的副本、脚本和记录在 `/tmp/oc0071-ab/`，端到端的驱动、日志和课题在 `/tmp/oc0071-e2e/`，没有提交。
