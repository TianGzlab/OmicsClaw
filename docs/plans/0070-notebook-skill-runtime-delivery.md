# 计划 0070 交付记录：notebook 运行层与单细胞试点

日期：2026-10-01。规格：`docs/plans/0070-notebook-skill-runtime.md` 第 3 版（定稿，D1 至 D18、O1 至 O6 照此实现）。本记录不改动计划正文。
范围：N-A、N-B1、N-B2、N-C、N-D、N-E 六期，以及 §5 的端到端验收和 9 项变异检查。
状态：六期都已实施并验收，每期一个提交，只在本地分支 `plan-0070-notebook-runtime` 上，没有推送。端到端第 1 至 6 条通过，第 7 条（sandbox）本机没有 docker，待 owner 机器验证。变异检查 9 项都能被对应测试发现。之后按独立评估意见和 owner 裁定 O7 又做了一个修复提交，见 §12；第二轮复核和裁定 O8 带来第二个修复提交，见 §13。最终复核结论为可以交付；随后按它唯一的非阻塞建议做了第三个修复提交，见 §14。sandbox 验收需要换一台有 docker 的服务器，owner 已决定暂缓。
开工状态：`80925742`，工作树只有未跟踪的计划文件。

## 1. 结论

| 阶段 | 提交 | 验收结论 | 关键证据 |
|---|---|---|---|
| 计划 | `a82d737c` | 不适用 | 只含计划文件 |
| N-A 清理 | `e6947b99` | 通过 | 451 passed、1 skipped、1 xpassed；help probe 1 passed；`git grep` 无输出 |
| N-B1 运行层核心 | `5a64314a` | 通过 | 124 passed、1 skipped；只有标准库的 venv 能 `import skills._sdk.notebook`；`eval.yml` 能被 `yaml.safe_load` 解析 |
| N-B2 验收流程 | `1b0883df` | 通过 | `tests/sdk/notebook` 131 passed；手工走查见 §4 |
| N-C 单细胞试点 | `b59d357d` | 通过 | 10 个 parity 基线全部逐值一致（CLI 与 API 两条路）；5 个示例步骤都跑通；help probe 11 passed |
| N-D 框架与契约 | `b4640b89` | 通过 | 712 passed、2 skipped、1 xfailed、1 xpassed；golden 只改了 2 个文件 |
| N-E eval | `78a6bdee` | 通过 | `tests/evals` 181 passed；用例集连跑 3 次都是 29 passed；job2 同款 venv 29 passed，13.8 秒 |
| 评估后的修复 | `3a72bb63`（§12） | 通过 | N-B1 191 passed、1 skipped；`tests/sdk/notebook` 163 passed；skillenv 与 permission 734 passed；`tests/evals` 186 passed；用例集 29 passed；变异 6、7 重做后仍被发现 |
| 第二轮修复 | `daf420cd`（§13） | 通过 | permission 313 passed；skillenv 425 passed、1 skipped、1 xpassed；`tests/sdk/notebook` 166 passed；`tests/evals` 186 passed；用例集 29 passed |
| 交付前的小修 | 分支上的最后一个提交（§14） | 通过 | `test_kernel.py` 12 passed；`tests/sdk/notebook` 167 passed |

N-E 的提交同时带上本记录和端到端发现的一处修复（§8 第 1 条）。

## 2. N-A：删除 consensus 外壳与 `notebook_export`

改动：
- 删除 `skills/singlecell/scrna/sc-consensus-clustering/`、`sc-consensus-integration/`、`sc-consensus-pseudotime/`、`skills/spatial/consensus-domains/` 整个目录（`git rm`），连同两个 `tests/test_cli_smoke.py`。
- `tests/sdk/test_boundary.py` 的 `B3_KNOWN` 改为空集；`OMICSCLAW.md` 删掉提到 4 个外壳和 `SKILL.md.disabled` 的那几句；`llms.txt` 删 4 行。
- 删除 `omicsclaw/common/notebook_export.py` 和 `tests/test_output_ux.py::test_analysis_notebook_rejects_claim_aliases`，顺带去掉那个文件不再用到的 `import nbformat`。
- `consensus-interpret` 不动（O4）。

验收：

```
PYTEST tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py tests/skills tests/test_output_ux.py tests/entry/test_runtime_contract.py
  451 passed, 1 skipped, 1 xpassed
  （xpassed 是 ci_known_failures 里标 env 的 test_spatial_genes_help_does_not_require_scanpy_runtime，rapids 环境有 scanpy）
OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python PYTEST -m slow tests/sdk/test_help_probe.py
  1 passed
git grep -n "sc-consensus-clustering\|sc-consensus-integration\|sc-consensus-pseudotime\|consensus-domains" -- <计划列的排除路径>
  无输出
```

## 3. N-B1：运行层核心

新建 `skills/_sdk/notebook/`，按 §3.2.1 分模块：`contract.py`（`LAYOUT`、`MANIFEST_SCHEMA`、`LEDGER_EVENTS`、`ENVIRONMENT` 四个纯字面量）、`_layout.py`、`_hashing.py`、`_ledger.py`、`_manifest.py`、`_lock.py`、`_percent.py`、`_io.py`、`_skills.py`、`_runners.py`、`_executor.py`、`run.py`、`__main__.py`、`templates/STRATEGY.md`、`templates/README.md`。门面 `__init__.py` 只导出 5 个函数；nbformat、nbclient、anndata、pandas 都在函数体内导入。

几处实现上的取舍（都不改裁定，列在 §10）：
- 解释器核对比较的是 `sys.prefix` 与 `sys.executable` 两者的 realpath。overlay 的 `.venv/bin/python` 是指向基础解释器的符号链接，只比 executable 分不出 overlay 和基础环境。
- 一个步骤读了某个文件、又用同名覆盖它时，这个输入不参与过期判定，执行器输出里给出警告，建议换个名字写。否则这个步骤会永远过期。
- `run.py` 先把自己所在的目录从 `sys.path[0]` 去掉，再执行统一引导块，免得 `contract`、`_io` 这类同目录模块名被当成顶层模块。
- 记账文件按 `run_start` 的毫秒时间排序；`run_id` 的格式照计划写，同一秒内的两次运行只靠时间戳区分先后。

测试放在 `tests/sdk/notebook/`：`test_percent.py`、`test_layout.py`、`test_io.py`、`test_skills.py`、`test_executor.py`（假 runner 在进程内执行 cell）、`test_kernel.py`（真实 kernel）、`test_contract.py`。另外：`environment.yml` 声明 `nbclient>=0.10`，`tests/test_pyproject_thin_pip_layer.py` 的 `CONDA_OWNED` 加 `nbclient`；`tests/sdk/test_public_surface.py` 收录门面和 `contract.py`；`tests/sdk/test_bootstrap.py` 把 `run.py` 加进统一引导块的检查；`eval.yml` 的 job1 加装 `nbclient ipykernel`；`.gitignore` 加课题目录（见 §10 第 6 条）。

验收：

```
PYTEST tests/sdk/notebook tests/sdk/test_public_surface.py tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py tests/test_pyproject_thin_pip_layer.py
  124 passed, 1 skipped（skip 是 test_bootstrap 里要 OMICSCLAW_TEST_SANDBOX=1 的那条）
只有标准库的 venv（python -m venv --without-pip）里，PYTHONPATH=<checkout>：
  import skills._sdk.notebook 成功，nbformat、anndata、pandas 都没被导入；
  run.py new x 成功，run.py run 以退出码 2 报 "the step runner needs nbclient and ipykernel in ..."
yaml.safe_load(.github/workflows/eval.yml)：成功
同一组 notebook 测试在 OmicsClaw 环境（Python 3.11）也是 96 passed
```

## 4. N-B2：验收流程与手工走查

新增 `_acceptance.py`（`accept`、`revise`、baseline 快照，16 MiB 阈值）、`_apidoc.py`（只用 `ast` 生成和核对 `## API` 段），`_executor.py` 加 `replay`，`run.py` 加 `replay`、`accept`、`revise`、`api` 四个子命令。测试：`test_replay.py`、`test_acceptance.py`、`test_apidoc.py`。

走查中发现并修好一处缺陷：把 `km` 交给 nbclient 时，它不负责关 kernel（`owns_km` 为假），kernel 要等到发现执行器退出才自己关掉，下一条命令的输出里会混进 `Parent appears to have exited, shutting down.`。现在 `execute(..., cleanup_kc=True)`，并在 `finally` 里补一次 `shutdown_kernel(now=True)`；`test_kernel.py` 加了"步骤跑完后 kernel 不残留、stderr 里没有这句话"一条。

验收：

```
PYTEST tests/sdk/notebook
  131 passed
```

手工走查（临时课题 `/tmp/oc0070-walk`，OmicsClaw 环境，`R=skills/_sdk/notebook/run.py`）：

```
$ python $R new demo
created module 01_demo
  project folders created: analysis/, results/, results/_archive/, data/, docs/analysis_strategy/, manifests/, scripts/, work/, docs/analysis_strategy/STRATEGY.md
$ python $R run analysis/01_demo
[01_demo] 01_table.py  ok  1.1 s  python=/opt/conda/envs/OmicsClaw/bin/python (3.11.15)
  why:      never run
  wrote:    tables/counts.csv
[01_demo] 02_validate.py  ok  1.2 s  ...
  read:     results/01_demo/tables/counts.csv
exit 0
$ python $R replay analysis/01_demo
[01_demo] replay ok: 2 steps, validate last
  status: REPLAYED
exit 0
$ python $R accept analysis/01_demo --review results/01_demo/reviews/2026-10-01_review.md   # 报告和审查都还没写
cannot accept 01_demo:
  - the report results/01_demo/M01_demo_REPORT.md is missing
  - review file results/01_demo/reviews/2026-10-01_review.md does not exist
exit 4
$ # 写 REPORT（含免责声明）和一份第一行是 VERDICT: APPROVE 的审查
$ python $R status
01_demo  REVIEWED
$ python $R accept analysis/01_demo --review results/01_demo/reviews/2026-10-01_review.md
accepted 01_demo; status: ACCEPTED, frozen
exit 0
$ python $R run analysis/01_demo --force
module 01_demo is accepted and frozen; run `revise analysis/01_demo` before changing it
exit 2
$ python $R revise analysis/01_demo
module 01_demo is open for revision; status: DRAFT
  accepted results kept in results/01_demo/baseline/2026-10-01_pre_revision/ (16 files copied, 0 large files recorded by sha256)
$ python $R status
01_demo  DRAFT (revising)
```

baseline 目录里有 `analysis/` 的 3 个文件和 `results/` 的报告、日志、notebook、manifest、4 份记账、审查和表格。

## 5. N-C：单细胞试点

### 5.1 先录基线

改代码之前，用旧 CLI 在 OmicsClaw 环境里录了 10 个基线（`python -m tests.parity.snapshot record <skill> --case <case>`），每个 skill 是 demo 默认参数加 1 个 Python 方法变体：

| skill | default | 变体 | 录制耗时 |
|---|---|---|---|
| sc-qc | `--demo` | `--species mouse` | 15 s / 9 s |
| sc-preprocessing | `--demo` | `--method pearson_residuals` | 10 s / 20 s |
| sc-clustering | `--demo` | `--cluster-method louvain` | 20 s / 19 s |
| sc-cell-annotation | `--demo` | `--method knnpredict` | 21 s / 23 s |
| sc-de | `--demo` | `--method t-test` | 8 s / 8 s |

为确认旧 CLI 本身是确定的，又用旧代码把 sc-clustering、sc-cell-annotation、sc-preprocessing、sc-de 的 default 各跑一次，与基线比较，4 个都完全一致。基线在 `tests/parity/golden/`，已加进 `.gitignore`，不提交。

### 5.2 改动

每个 skill 加 `_api.py`，CLI 改成薄壳：在 `main()` 里 `load_skill(SKILL_NAME)`，计算交给函数库，argparse、报告、画廊图、`result.json` 留在 CLI。函数库按 §3.13.2 的规则写，覆盖 CLI 的全部方法（R 方法照搬）：

| skill | `_api.py` 公开函数 |
|---|---|
| sc-qc | `calculate_qc`、`run_info`、`qc_summary`、`qc_metrics_table`、`highest_expressed_genes`、`barcode_rank_table`、`qc_correlation_table`、`qc_figure` |
| sc-preprocessing | `preprocess`（scanpy、pearson_residuals、seurat、sctransform）、`run_info`、`hvg_table`、`pca_variance_table`、`pca_embedding_table`、`qc_metrics_table`、`pca_variance_figure` |
| sc-clustering | `cluster`（含 `random_state`，默认 0，与 scanpy 一致）、`auto_resolution`、`run_info`、`cluster_summary`、`embedding_figure` |
| sc-cell-annotation | `annotate` 统一入口，`annotate_markers`、`annotate_manual`、`annotate_celltypist`、`annotate_popv`、`annotate_knnpredict`、`annotate_singler`、`annotate_scmap`、`annotate_scsa`，`run_info`、`annotation_table`、`cluster_annotation_matrix`、`annotation_figure` |
| sc-de | `rank_genes`（wilcoxon、t-test、logreg、mast）、`pseudobulk_de`（deseq2_r）、`run_info`、`top_genes`、`volcano_figure` |

运行中产生的诊断（过滤了多少、用了哪个矩阵当 counts、注释是否回退）以 JSON 字符串存进 `adata.uns`，由各自的 `run_info(adata, keep=True)` 读回；CLI 调 `keep=False` 把它取走，`processed.h5ad` 因此与改造前一样（§10 第 8 条）。

SKILL.md 按附录 B.3 改写（改写前加载了 writing-for-agents），`## API` 段用 `run.py api <dir> --write` 生成。每个 skill 加 `examples/example_step.py`。skill 自己的测试里有几条直接读 CLI 源码或模块内部函数，随代码搬到 `_api.py` 一起改了指向（sc-preprocessing 的 3 条、sc-cell-annotation 的 3 条 dispatch 文本检查）。模板 `templates/skill/` 同步：`_api.py`、`examples/example_step.py`、SKILL.md 正文、README 里 `_api.py` 的规则；`replace_me.py` 按所在目录名找自己的函数库，在 `templates/skill/` 里和复制后都能跑。

测试与 CI：`tests/parity/snapshot.py`、`tests/parity/api_runs.py`、`tests/parity/test_sc_pilot_parity.py`（标 `slow`）；`tests/sdk/notebook/test_skill_api_sections.py`、`test_skill_examples.py`（marker `skill_example`，默认 `addopts` 排除）；`eval.yml` 的 job1 `-m` 加 `and not skill_example`，新增 job3 `skill-examples`。

### 5.3 验收

每个 skill 做完都跑一轮，最后全部再跑一次：

```
PYTEST tests/sdk/notebook/test_skill_api_sections.py                         7 passed
OCPYTEST skills/singlecell/scrna/<skill>/tests                               sc-qc 2、sc-preprocessing 6、sc-clustering 1、sc-cell-annotation 6、sc-de 1 passed
OCPYTEST -m demo skills/singlecell/scrna/<skill>/tests                       2、3（1 skipped：R）、2、3、4 passed
OCPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py          5 passed（39.6 s）
OCPYTEST -m slow tests/parity/test_sc_pilot_parity.py                        20 passed（216 s）
OMICSCLAW_TEST_BASE_PYTHON=... PYTEST -m slow tests/sdk/test_help_probe.py tests/sdk/test_sc_scripts_help.py   11 passed
```

parity 比较结果：10 个 case 的 CLI 输出与基线逐值一致（`summary.json`、`figures.json`、`obsm.json`、全部 `tables/*.csv`、分类 `obs` 列、数值 `obs` 列，浮点按 rtol 1e-6，实际都是完全相等）；直接调函数库得到的表和标签，与基线中对应的部分也一致（sc-qc 5 张表与数值 `obs`；sc-preprocessing 4 张表与数值 `obs`；sc-clustering 的标签与 `cluster_summary.csv`；sc-cell-annotation 的 `cell_type` 等标签、`cell_type_counts.csv`、`cluster_annotation_matrix.csv`；sc-de 的 `de_full.csv`、`markers_top.csv`）。

parity 测试中发现的问题：`tests/conftest.py` 为单元测试设了 `NUMBA_DISABLE_JIT=1`，pytest 里起的 CLI 子进程继承了它，UMAP 退化成纯 Python，一次聚类要 5 分钟以上，数值也未必与录基线时（JIT 开着）一致。现在 CLI 子进程、函数库调用（改为在子进程里跑 `tests/parity/api_runs.py`）和示例测试的执行器都去掉这个变量。

## 6. N-D：框架与契约

改动：
- `OMICSCLAW.md` 按附录 A 改写（先加载 writing-for-agents，再用 humanizer 过了一遍新写的段落）：Identity 两句、Operating Rule 2；"How to Use a Skill" 换成 "Projects, modules and steps"（布局表、先跑 `status` 再读 `STRATEGY.md`、步骤的写法、执行器子命令表、"stale" 的含义、完成模块的四步、修订与归档）和 "Skills"；Demo Data 第一句；删掉 "Chaining skills"。路由表和计数不变。
- `SAFETY_RULES` 按 §3.11.2；`tests/entry/test_assembly.py` 原来断言 "SKILL.md methodology only" 的那一行改成新第 3 条的两个片段。
- 新增 `omicsclaw/entry/project.py`（`step_runner_line`、`recent_modules`、布局常量），`_environment_source` 在技能树有执行器时加 `- Step runner: python <skills>/_sdk/notebook/run.py`。没有 `PROJECT.md`，没有新提示段（O5）。
- `omicsclaw/entry/subagent.py` 加内置 `MODULE_REVIEWER`（工具只有 `read_file`、`use_skill`，提示是附录 B.4 原文），注册顺序 `[GENERAL_PURPOSE, MODULE_REVIEWER]`。
- `install_skill_deps` 的参数改成 `skills` 数组，`OverlayRequest.skill` 改为 `skills`，`.meta.json` 写 `"skills": [...]`；结果末尾先给"用这个解释器运行模块的步骤"，CLI 用法作为第二行；工具工厂多一个 `step_runner` 参数，由 `entry/skill_env.py` 传入。
- channel `/recent` 改为读模块（`recent_modules`）。
- 契约测试（`tests/sdk/notebook/test_contract.py`）：`project.py` 的布局常量与 `LAYOUT`、`MANIFEST_SCHEMA` 一致；契约 "Running steps" 表里的每个子命令和该段落里出现的每个旗标，都存在于 `run.py` 的解析器中。
- 文档：`docs/core-features/agent-skills.md`（skill 形状、§9 执行通道、§9.4 的安全规则那句、§10 链式调用、§13 已知限制）、`sub-agent.md`（新 §2.3.1）、`sandbox.md`（新 §13.1）；`README.md` 的 What's new 加一句，原有 6 条，删掉最旧的两条（`run_skill` 与 `oc channel`，CHANGELOG 里都有），留 5 条；`README_zh-CN.md` 同步加同一句并删掉最旧的一条。

N-D9 的 golden 重录：

```
OMICSCLAW_WRITE_GOLDEN=1 PYTEST tests/entry/test_ensemble_golden.py      17 passed（重录前 14 failed）
PYTEST tests/entry/test_ensemble_golden.py                                16 passed, 1 skipped
git diff --stat tests/entry/golden/
 tests/entry/golden/ensemble_off_prompt.txt | 6 +++---
 tests/entry/golden/ensemble_off_tools.json | 5 +++--
```

逐行看过的差别只有两处：`ensemble_off_prompt.txt` 的 safety 段第 2 至 4 条；`ensemble_off_tools.json` 里 `task` 的描述（`module-reviewer` 的一行）和 `subagent_type` 的 enum 多了 `"module-reviewer"`。`ensemble_tools_all.json` 没有变化。on 部署的提示词与 off 相同、块外工具与 off 相同，由重跑整个测试文件确认。

改写前后各段的 token 数（`build_prompt(default_sections(config)).render().section_stats`，本仓库的估算器）：

| 段 | 0070 之前（`80925742` 的 `OMICSCLAW.md`） | N-A 之后、N-D 之前 | N-D 之后 |
|---|---|---|---|
| contract | 2,382 | 2,318 | 3,691 |
| safety | 133 | 133 | 170 |
| environment（课题目录部署） | 23 | 23 | 48 |
| 整个提示（workspace 为 checkout） | | 9,911 | 11,346 |
| 整个提示（课题目录 + `skills_dir`） | | 9,903 | 11,338 |

计划估计契约净增约 1.3k token，实测从 2,318 到 3,691，增加 1,373。没有 project 段（O5）。

验收：

```
PYTEST tests/entry/test_ensemble_golden.py tests/entry/test_assembly.py tests/entry/test_runtime_contract.py \
  tests/entry/test_subagent_wiring.py tests/entry/test_channel_commands.py tests/entry/test_planning.py \
  tests/skillenv tests/permission/test_foundation_tools_keep_their_prompts.py tests/sdk/notebook/test_contract.py \
  tests/entry/test_entry_is_the_top_layer.py tests/sdk/test_boundary.py
  712 passed, 2 skipped, 1 xfailed, 1 xpassed
```

## 7. N-E：eval

改动：
- `omicsclaw/evals/case.py`：`Case.skill_modules`；`SkillRun` 加 `function`、`source`（`"bash"` 或 `"ledger"`）和 `args`。
- 新增 `omicsclaw/evals/ledger.py`：只读记账文件，不 import `skills.*`；事件名、字段名、环境变量名与 `contract.py` 由契约测试钉住。
- `omicsclaw/evals/runner.py`：用例声明了任一种桩时把它们写进 `tmp_path/stubs/` 并设 `OMICSCLAW_SKILL_STUBS`；所有用例加 `PYTHONDONTWRITEBYTECODE=1`；运行后读记账，`skill_call`、`skill_cli` 变成 `SkillRun`，`stub_target_missing` 记硬失败，设了桩目录却加载真实函数库时记软警告 `skill_ran_unstubbed`。
- `SkillInvoked(skill, domain=None, function=None)`；`_harness.check(timeout_s=)`，skill 用例 90 秒。
- `tests/evals/fixtures/skill_stubs/sc-qc.py`、`sc-clustering.py`；`tests/evals/dataset/test_skill_routing.py` 重写为 §3.15.3 的 8 条。
- `tests/evals/test_fixtures.py` 不再从路由用例导入 `ROUTES`，检查行表移进本文件，加"桩模块只含真实 `__all__` 里的名字"；种子的 `expected_args` 允许写成关键字参数（`method="celltypist"`），因为试点 skill 的 SKILL.md 改用函数库的写法。
- `tests/evals/test_runner.py` 加 5 条（记账变成 `SkillRun`、`stub_target_missing` 是硬失败、`skill_ran_unstubbed` 只在设了桩时出现、桩里多出函数的用例失败、桩目录下没有 `__pycache__`）；`test_assertions.py` 加 1 条；`test_live.py` 加 2 组（执行器命令的审批、记账给出 `executed_skill` 与关键字参数的 `args_ok`）。
- `omicsclaw/evals/live.py`：`executed_skill` 没有 bash 运行时取记账里第一条 `skill_load` 或 `skill_cli`；`routing_policy` 批准单条、不带元字符的执行器调用（§10 第 15 条）。
- `eval.yml` 的 job2 改为 `pip install -e . pytest nbclient ipykernel`；`docs/core-features/eval.md` 改写 skill 用例、Runner 流程、桩、live 判分和 CI 图。

N-D 提交后 CI job1 里有一条 `tests/evals/test_fixtures.py` 的失败（种子要求 `--method celltypist` 出现在 sc-cell-annotation 的 SKILL.md 里，N-C 改写正文时去掉了 CLI 示例），由本期的 `test_fixtures.py` 改动修好。N-C 到 N-E 之间的提交单独检出时这一条是红的。

验收：

```
PYTEST tests/evals                                         181 passed, 26 deselected
PYTEST tests/evals/dataset -m scripted_eval                29 passed（26.8 s）× 3 次，结果一致
pip venv（OmicsClaw 的 Python 3.11.15 建的 venv，只装 -e . pytest nbclient ipykernel）：
  pytest tests/evals/dataset -m scripted_eval -p no:cacheprovider    29 passed，13.84 s
```

## 8. 端到端验收

做法：课题目录 `/tmp/oc0070-e2e/project`（仓库外，起始为空），`OMICSCLAW_SKILLS_DIR=<checkout>/skills`，模型取 `.env`（provider 为 deepseek，模型用 provider 的默认值），权限模式 auto-approve。`oc cli --prompt` 只能单轮，`--session` 只在 REPL 里可用，所以写了一个驱动脚本 `/tmp/oc0070-e2e/drive.py`：照 `oc cli` 的做法 `_adopt_dotenv` 后 `resolve_app_config`、`attach_sessions(await open_app(config))`，每次运行发一条用户消息，会话 `E2E` 存在课题的 `.omicsclaw/memory.db` 里，下一条消息由新进程接着同一会话发。由我扮演用户，读完 agent 的报告和审查结论后回复接受。

7 条用户消息与 agent 的处理：

| # | 用户消息（摘要） | agent 做了什么 | 主线模型调用 | 墙钟 |
|---|---|---|---|---|
| 1 | 用 pbmc3k_raw 走完整流程，先做 QC | `status`、读 `STRATEGY.md`、`use_skill(sc-qc)`、`new qc`、写 `STRATEGY.md`、README、步骤 `01_qc_metrics.py`、`run`；给出指标并请我选过滤阈值 | 18 | 101 s |
| 2 | 选方案 A（200 至 2,500 基因、线粒体 < 5%、基因至少 3 个细胞） | 写 `02_filter.py`（经 `run_cli` 调只有 CLI 的 sc-filter）、`03_validate.py`、`replay`、REPORT、`module-reviewer` 给出 APPROVE；请我验收 | 13 | 371 s |
| 3 | 接受 01，做预处理 | `accept 01_qc`；`new preprocess`、步骤、`run`、validate、`replay`、REPORT；审查先给 REVISE（6 条），修完再 `replay`，复审 APPROVE | 21 | 688 s |
| 4 | 接受 02，聚类并做 UMAP | `accept`；`new cluster`、步骤、`run`；validate 步骤第一次重放失败（它自己写的 `iterrows` 把 `'0'` 变成 `'0.0'`），看了执行器给出的 cell 与 traceback 后修好，再 `replay`、REPORT、APPROVE | 18 | 564 s |
| 5 | 接受 03，做注释（marker 即可） | `accept`；`new annotate`、步骤、`run`、validate 同样的问题再修一次、`replay`、REPORT、APPROVE | 16 | 435 s |
| 6 | 接受 04，做细胞类型间的差异表达 | `accept`；`new de`、步骤、`run`、validate、`replay` 一次通过、REPORT、APPROVE | 11 | 322 s |
| 7 | 接受 05 | `accept 05_de`，更新 `STRATEGY.md` 的 Decisions | 3 | 17 s |
| 合计 | | 6 次审查（一次 REVISE 后复审） | 100 | 2,498 s（约 42 分钟） |

token（各次 `outcome.result.usage` 相加）：输入 8,547,490，其中缓存命中 8,377,472，输出 80,181。模型调用数只计主线引擎轮次，`module-reviewer` 子 agent 的轮次没有单独统计；每次审查花 4 到 6 分钟。

逐条核对 §5：

| # | 期望 | 结果 |
|---|---|---|
| 1 | 5 个模块，各有 README、步骤、validate、带输出的模块 notebook、manifest、含免责声明的 REPORT；`STRATEGY.md` 写有问题、数据、计划、决定 | 通过。01_qc 有 3 个步骤（含 `03_validate.py`），其余各 2 个（含 `02_validate.py`）；模块 notebook 的代码 cell 输出数分别为 15、11、8、8、14；5 份 REPORT 都含免责声明原文；`STRATEGY.md` 四段齐全，Decisions 有 3 条带日期的记录 |
| 2 | 每个模块都经过 `replay`、`module-reviewer` 审查、用户确认后 `accept`；`status` 里 5 个都是 `ACCEPTED` | 通过。`status` 输出 5 行 `ACCEPTED`，5 个 manifest 的 `status` 为 `accepted`、`frozen` 为真；每个模块 `reviews/` 下有审查文件，`accept` 都是在我回复接受之后才运行 |
| 3 | 用到试点 skill 时走 `load_skill`，记账里有函数调用和 skill 版本 | 通过。manifest 记下 sc-qc 7 个函数、sc-preprocessing 6 个、sc-clustering 4 个、sc-cell-annotation 5 个、sc-de 4 个；`skill_load` 有 `git.commit`、`git.dirty`（02 之后为真，因为端到端期间工作树里有 §8 第 1 条的修复）、`content_sha256` 和依赖版本；sc-filter 经 `run_cli` 记为 `skill_cli` |
| 4 | 单独运行一个写表格的步骤，CSV 与执行器的逐值一致 | 通过。模块已冻结，所以在课题的副本里先 `revise` 再单独运行（`PYTHONPATH=<checkout> python analysis/03_cluster/01_cluster_umap.py`，另加 `analysis/05_de/01_rank_genes.py`）：`cluster_summary.csv`（9 行）与 `de_full.csv`（109,248 行）都与执行器写出的完全相等 |
| 5 | 改一个上游步骤后，`status` 正确列出下游的过期原因 | 通过。在副本里 `revise 02_preprocess`，把 `n_top_hvg` 从 2000 改成 1500：改完未运行时显示 `01_normalize_hvg_pca.py  stale: step changed`；重跑之后显示 `03_cluster` 的 `01_cluster_umap.py  stale: input changed: results/02_preprocess/intermediate/adata_preprocessed.h5ad`，以及本模块 `02_validate.py` 的 `input changed` |
| 6 | `/recent` 显示最近 3 个模块的标题和状态 | 通过。输出 `05_de [ACCEPTED]`、`04_annotate [ACCEPTED]`、`03_cluster [ACCEPTED]`，各带 REPORT 的一级标题 |
| 7 | sandbox 模式下跑通一个模块 | 待 owner 机器验证（本机没有 docker 和 podman） |

端到端暴露的问题：
1. agent 第一次执行了 `new 01_qc`，得到 `01_01_qc`，只好 `rm -rf` 后重建。已修：`new` 拒绝已经以两位编号开头的 slug，提示改用 `new qc`；`test_executor.py` 加一条测试。这处修复随 N-E 提交。
2. 同一天的复审把第一次的 REVISE 审查覆盖了（两次都存成 `2026-10-01_review.md`）。当时没有改，列在 §11；后来按 O7 第 2 条在执行器里解决，见 §12。
3. agent 调执行器时习惯写成 `cd /tmp/oc0070-e2e/project && python .../run.py ...`，契约要求的是单条命令。本机无害；在 sandbox 里这正是 R2 说的残留风险。当时列在 §11；后来按 O7 第 3 条加了看门狗，见 §12。
4. agent 为了弄清 `write_output`、`run_cli`、`load_demo` 的行为，几次去读 `_sdk` 的源码。函数本身没有问题，但说明契约和 SKILL.md 对这几个函数的说明还不够让它放心。
5. 观察 R14：每次开工前 agent 都先跑了 `status`，第一次读了 `STRATEGY.md` 并写入问题、数据、计划；之后的消息里它依赖会话记忆，没有再读这个文件，但所做的选择与文件一致。

临时文件：驱动脚本、每条消息的日志（`logs/*.md`、`*.jsonl`）、课题目录和副本都在 `/tmp/oc0070-e2e/`，没有提交。

## 9. 变异检查

每项都是改代码、跑对应测试、再用 `git checkout` 还原，结果记在 `/tmp/oc0070-mutations.log`。

| # | 变异 | 结果 |
|---|---|---|
| 1 | 删掉 `sc-clustering/_api.py` 的 `cluster_summary` | 被发现：eval 用例 1 失败，硬失败 `stub_target_missing: sc-clustering: not in the real _api.py's __all__ (cluster_summary)`；`test_skill_api_sections` 的 sc-clustering 一条失败 |
| 2 | 把 sc-qc SKILL.md API 段里 `n_top` 的默认值 20 改成 30 | 被发现：一致性测试的 sc-qc 一条失败 |
| 3 | 去掉 kernelspec 的解释器固定 | 被发现（第二种改法）。第一种改法把 argv 的解释器写成裸的 `python`，测试没有失败：jupyter_client 会把 kernelspec 里的 `python` 替换成它自己的 `sys.executable`，这种写法等于没去掉固定。第二种改法写成 PATH 上 `python3` 的绝对路径（OmicsClaw 环境），测试用 rapids 环境运行，`test_the_kernel_runs_the_runner_interpreter` 失败，记下的 `exe` 与 `prefix` 都是 OmicsClaw 环境的 |
| 4 | 去掉 `IPYTHONDIR` 隔离 | 被发现：eval 用例 1 的 `NoWriteOutside` 失败，`home/.ipython/profile_default/startup/README` 被创建 |
| 5 | 去掉 Runner 的 `PYTHONDONTWRITEBYTECODE=1` | 被发现：eval 用例 1 的 `NoWriteOutside` 失败，`stubs/__pycache__/sc-clustering.cpython-313.pyc` 被创建（为排除干扰，这次在去掉了该变量的 shell 里运行 pytest） |
| 6 | 过期判定忽略输入哈希 | 被发现：eval 用例 5 失败，`status` 里没有 `input changed` |
| 7 | `run_cli` 不补记输出 | 被发现：eval 用例 8 关于 manifest `outputs` 的断言失败（计数 0）；`test_replay.py::test_run_cli_outputs_are_not_orphans` 失败 |
| 8 | `accept` 跳过重放检查 | 被发现：`test_acceptance.py` 的 3 条失败（从未重放、重放后改过步骤、所有缺项一起列出） |
| 9 | `module-reviewer` 继承全部工具 | 被发现：`test_subagent_wiring.py::test_the_module_reviewer_is_given_only_read_file_and_use_skill` 失败 |

## 10. 偏差

都没有改变 D 或 O 的裁定，也没有扩大或缩小范围。

1. 解释器核对比较 `sys.prefix` 与 `sys.executable` 两者的 realpath（§3.4.1 只写了 executable）。理由见 §3。manifest 的 `interpreter` 因此多一个 `prefix` 键。
2. 同一个步骤读了又原名写回的文件，过期判定拿它的当前 sha256 与这个步骤上次运行在 `output` 事件里最后记下的 sha256 比较，不一致就是过期；执行器输出照样警告（计划没有提这种情况）。最初的实现让这种输入完全不参与判定，上游改了它，下游也显示"up to date"，评估后改成现在这样（§12 b）。
3. `read_input` 读 `manifests/` 下的文件不算契约外（G6 只列了 `data/`、上游模块和本模块）。`manifests/` 按 §3.1 放样本表，步骤读它很正常。
4. markdown cell 里出现不以 `#` 开头的非空行时报错并给出行号（§3.3 没规定）。否则这一行单独运行时会被当成代码执行，notebook 里却是文字。
5. `load_demo` 的候选列表没有照搬 `_lib/io.py` 里 `pbmc3k_processed` 退回 `examples/pbmc3k.h5ad`（原始矩阵）的那一项。
6. checkout 内建课题时，`new` 只警告；Q4 要求的 5 行 `.gitignore` 条目直接写进仓库的 `.gitignore`，没有在运行时往 `.gitignore` 追加，免得运行时改动受版本控制的文件。
7. `test_public_surface.py` 的"每个冻结名都有使用者"对 `read_input`、`run_cli` 豁免（`STEP_API`）：它们给 agent 在课题里写的步骤用，skills 与 templates 里没有自然的使用者。其余 3 个由示例、CLI 薄壳和模板使用。
8. 函数库的运行诊断经 `adata.uns` 里的 JSON 字符串和 `run_info` 读回，CLI 取走后再保存。§3.13.2 只说"修改 AnnData 的函数原地修改并返回同一个对象"；`calculate_qc`、`preprocess` 实际返回新对象（标准化和过滤本来就会生成新对象），docstring 写明了。
9. parity 的函数库比较放在子进程里跑（`tests/parity/api_runs.py`），并去掉 `NUMBA_DISABLE_JIT`。理由见 §5.3。
10. `run.py` 先去掉自身目录再执行统一引导块；冻结模块的 `run`、`replay` 以退出码 2 结束（§3.2.3 的退出码表没有列这种情况）；对已验收的模块再 `accept` 返回 0，对未验收的模块 `revise` 返回 2。
11. 已被 O7 第 1 条取代。原来的做法：`install_skill_deps` 改成数组参数后没有字符串主参数，"总是允许"记下整次调用的原始 JSON（这组 skill 加这组包）。现在记的是排好序的 skill 组合，例如 `install_skill_deps(sc-de, sc-qc)`，与包、参数顺序和 JSON 空格无关。实现方式见偏差 20（§13 O8-1 定稿）。
12. 模板的 `replace_me.py` 按所在目录名加载自己的函数库，试点 CLI 用的是 `load_skill(SKILL_NAME)`。模板目录名是 `skill`，与 frontmatter 的名字不同，按名字找不到。
13. `SkillRun` 除了计划写的 `function`、`source`，还多一个 `args`，live eval 用它判断关键字参数。
14. live eval 也带着 `skill_stubs`，按 §3.15.1 的规则 Runner 同样会给它建桩目录：步骤里的 `run_cli` 由录好的结果回答，`load_skill` 仍加载真实函数库（§3.15.4 说 live eval 不设桩目录，两处规定在这一点上冲突，取了 §3.15.1）。
15. live eval 的 `routing_policy` 批准单条执行器命令。不这样做，执行器在 live eval 里根本跑不起来，§3.15.4 要求的"从记账读 `executed_skill`"就不会发生。`api` 子命令会改 SKILL.md，不批准。
16. `test_fixtures.py` 的种子参数检查接受关键字参数写法（理由见 §7）。
17. `README_zh-CN.md` 也加了同一句并删掉最旧的一条，保持与 `README.md` 对应。
18. job3 用工作流里的一步把 demo 数据下载进 `OMICSCLAW_DEMO_DIR` 再缓存，没有依赖 `load_demo` 自己下载（它下载到 XDG 缓存目录，不在缓存的路径里）。
19. `new` 拒绝已经以两位编号开头的 slug（端到端发现，§8）。
20. O7 第 1 条的最终做法（O8 第 1 条）：主参数由工具在 `ToolPolicy.rule_argument` 里自己声明，声明的参数是字符串列表时取去重、排序后用 `, ` 连接的值；只有 `install_skill_deps` 声明了 `skills`。没有声明的工具，包括所有 MCP 工具，仍按 schema 里第一个必填 string 属性匹配，找不到时回落到原始 JSON，与 `main` 完全一致。第一轮曾把"取第一个必填字符串数组"做成通用规则，复核发现它让依赖 JSON 写法的 deny 规则失效，也让对一个路径的"总是允许"放行带额外参数的调用，已撤回（§13）。以前为 `install_skill_deps` 记下的原始 JSON 规则不再命中，会再问一次。
21. `run_cli` 的 `--output` 必须是四个输出目录之一下面的子目录，`results/<NN>/tables` 这样的顶层目录本身也拒绝：执行器按输出目录补记每个文件，顶层目录会把别的步骤写的文件记成这次的输出。
22. 魔法行检查只看 Python 报语法错误的那一行。同一个 cell 里在魔法行之前另有语法错误时，这次不报魔法行，kernel 先报那个语法错误。
23. 审查存档选的是移进 `reviews/archive/<id>/`，`<id>` 用 run_id 的格式（UTC 时间加 4 位十六进制），每次 replay 一个目录，文件名不变。`accept --review` 指向存档里的文件时，提示"was archived by a later replay"；条件本身没变，存档的审查本来就比新的重放旧。
24. 看门狗退出前不重建 manifest。`status`、`accept`、下一次 `run` 都从记账重新计算，磁盘上的 manifest 要到下一次 `run`、`replay` 或 `accept` 才更新。
25. live eval 只批准路径形式的执行器调用（Environment 段给的就是路径形式），`python -m skills._sdk.notebook ...` 不批准（§13）。第一轮曾在 workspace 里没有 `skills` 时批准它。
26. 看门狗除了比较父进程，还检查进程组原来的组长是否已经退出（O8 第 2 条只要求在入口记录父进程）。只在入口记录父进程，`nohup … &` 后 shell 立即退出时仍会漏掉：Python 走到入口之前 shell 已经退出，记下的父进程已是收养者。本机实测，去掉组长检查时这种运行会一直跑下去。`bash` 工具让 shell 自成进程组，所以组长就是那个 shell。剩下的漏洞：执行器自己换了会话或进程组（`setsid`、`set -m` 之后的作业）并且 shell 在入口之前就退出；组长不在当前 PID 命名空间里（`getpgrp()` 不大于 1）时不做组长检查。后来又加了一条例外（§14）：进程组是控制终端的前台组时不查组长。
27. 执行器在开始任何步骤之前就发现自己被遗弃时（例如 `nohup … &` 之后 shell 立即退出），直接退出，不写记账，因为没有步骤运行过；stderr 写 `run.py: parent exited; stopped while no step was running`。

## 11. 遗留问题

1. sandbox 验收（§5 第 7 条）待 owner 机器：镜像需装 nbclient、ipykernel，demo 数据经 `sandbox_mounts` 挂入并让 `OMICSCLAW_DEMO_DIR` 指向挂载点。
2. 已解决（O7 第 2 条，§12）。同一天的多次审查会互相覆盖：契约要求存成 `<YYYY-MM-DD>_review.md`，复审时第一次的 REVISE 被覆盖。现在 `replay` 先把已有的审查移进 `reviews/archive/<id>/`。
3. 已解决（O7 第 3 条，§12）。agent 用复合命令调执行器（`cd ... && python run.py ...`）时，sandbox 超时只杀外层 shell。现在执行器的看门狗在父进程变了之后杀掉 kernel 并退出。契约措辞没改。
4. 审查耗时：每次 `module-reviewer` 要 4 到 6 分钟（它逐个文件 `read_file`，大 CSV 也读）。
5. CI 从未在 GitHub 上跑过：job3 `skill-examples` 和改过的 job1、job2 只在本机模拟过（pip venv 和 conda 环境），首次运行要看下载与缓存是否顺利。
6. N-C 至 N-D 两个提交里的 eval 失败：§7 说的 `test_fixtures.py` 一条在单独检出这两个提交时是红的，N-E 提交修好。
7. `sc-integrate-cluster` 的 description 仍提到已删除的 `sc-consensus-integration`（§1.3 推迟项，未动）。

## 12. 评估后的修复

独立评估提了 3 个应改项（a、b、d）和 7 个小问题，owner 又给了裁定 O7（三条，已写进计划 §7.0）。全部放在一个修复提交里，仍在本地分支 `plan-0070-notebook-runtime` 上，没有推送。测试命令里的 `PYTEST` 指 `/opt/conda/envs/rapids_singlecell/bin/python -m pytest`。每条新测试都在改代码之前或临时还原改动时跑过，确认它在旧代码上失败。

### 12.1 应改项

a. 输出管道提前关闭。`run ... | head -5` 时，`head` 退出后的下一次打印抛 `BrokenPipeError`，执行器随即退出。评估的复现里第 3 个步骤没有跑，manifest 也没有重建。
- 改动：`_executor._print` 捕获 `BrokenPipeError` 后用 `os.dup2` 把 stdout 换成 `/dev/null`，余下的输出丢弃，步骤照常跑完，退出码照常。
- 新测试：`test_kernel.py::test_a_closed_pipe_does_not_stop_the_run`。3 个步骤各打印 30 行，经 `bash -c '... | head -5'` 运行，断言 `${PIPESTATUS[0]}` 是 0、stderr 里没有 `BrokenPipeError`、manifest 里三个步骤都是 ok、模块 notebook 已拼好。还原改动时这条测试失败，退出码 120。

b. 读了又原名写回的输入（偏差 2）。评估的复现：01 写 `intermediate/a.json`，02 读它再原名写回；改了 01 后 `run`，02 显示 up to date，02 的修改丢了。
- 改动：`_manifest.step_state` 对这种输入，拿当前 sha256 与这个步骤上次运行在 `output` 事件里最后记下的 sha256 比较，不一致就过期，原因写 `input changed: <path>`。执行器的警告改成"单独重跑这个步骤会读到它自己的输出，换个文件名写"。偏差 2 的说明已更新。
- 新测试：`test_executor.py` 的 `test_a_step_that_overwrote_its_input_reruns_when_an_earlier_step_rewrites_it`（就是评估的例子：01 改成写 5 之后，02 重跑，`a.json` 变成 6，再跑一次两步都是 up to date）和 `test_a_step_that_overwrote_its_input_is_stale_when_the_file_is_changed_by_hand`。旧代码上两条都失败。

d. `run_cli` 的 `--output`。原先只要求在 `results/<NN>/` 之内，`--output results/01_de` 也能通过，补记的输出里就有 `provenance/.lock` 和记账文件。
- 改动：`--output` 必须是 `figures/`、`tables/`、`intermediate/`、`logs/` 之一下面的子目录，否则在运行脚本之前抛 `ValueError`，提示默认位置（偏差 21）。
- 新测试：`test_skills.py::test_run_cli_refuses_an_output_outside_the_four_output_folders`，参数为 `results/01_de`、`results/01_de/provenance/cli`、`results/01_de/intermediate`、`results/01_de/notebooks/x`，断言报错、没有补记输出、没有建目录。

### 12.2 小问题

1. 魔法行误报。表达式跨行、续行以 `!=` 或 `%` 开头时被当成魔法行。改动：`_percent._check_code` 先用 `ast.parse` 解析整个 cell，能解析就没有魔法行；解析失败时，只有 Python 报错的那一行以 `%` 或 `!` 开头（并且不在字符串里）才报（偏差 22）。新测试：`test_percent.py` 里三种续行（`!= 0)`、`% 7)`、反斜杠续行）通过，合法代码之后的 `%time` 按它自己的行号报错。旧代码上三种续行都失败。
2. 等锁之后的冻结检查。`run --wait` 等到 `accept` 放锁后，仍在已冻结的模块里跑步骤。改动：`_run_locked` 和 `_replay_locked` 拿到锁后再查一次 `frozen`。新测试：`test_a_run_that_waited_for_the_lock_refuses_a_module_frozen_meanwhile` 和 `test_a_replay_that_waited_for_the_lock_refuses_a_module_frozen_meanwhile`：一个线程持锁、把模块设为冻结、0.5 秒后放锁，`run`/`replay` 带 `wait=10`，断言退出码 2、没有新的运行记账。
3. 解析失败时的旧 notebook。`PercentError` 时输出把上一次成功的 notebook 标成 "(partial)"，拼接时也带上了旧内容。改动：步骤没有产生 notebook 时删掉 `notebooks/<step>.ipynb`，输出写 `notebook: none (no cell ran)`，拼接的模块 notebook 在这一步写 "No notebook: the latest run (failed) stopped before any cell ran."。新测试：`test_a_step_that_cannot_be_parsed_leaves_no_old_notebook_behind`。
4. 非 UTF-8 的步骤文件。原先执行器抛出 traceback，记账停在没有 `run_end` 的状态。改动：捕获 `UnicodeDecodeError`，按失败处理，错误写成 `UnicodeDecodeError: 01_latin.py is not UTF-8 text (byte N: ...); save it as UTF-8`，记账照常写失败的 `run_end`。新测试：`test_a_step_that_is_not_utf8_fails_with_a_clear_error_and_a_finished_ledger`。
5. 解释器变化的警告只在开头。改动：`run` 结束时把同一句警告再打印一次，作为最后一行；`replay` 的总结里加一行 `interpreter: <新> (was <旧>; reason: ...)`。新测试：`test_an_interpreter_change_is_repeated_at_the_end_of_the_output`，断言第一行和最后一行都是这句警告。
6. live eval 的执行器识别。原先按后缀 `_sdk/notebook/run.py` 匹配，workspace 里随便放一个同名脚本也会被批准；`accept`、`revise` 也自动批准。改动：`is_step_runner(command, runner, workspace)` 要求脚本路径的 realpath 等于 skill index 根目录下的 `_sdk/notebook/run.py`（相对路径按 workspace 解析）；`-m skills._sdk.notebook` 只在 workspace 里没有 `skills` 或 `skills.py` 时批准（偏差 25）；子命令限 `new`、`run`、`status`、`replay`。`docs/core-features/eval.md` 同步。新测试：`test_live.py` 的参数表加了 `replay`（批准）和 `accept`、`revise`、`-m ... accept`（拒绝）；`test_only_the_real_step_runner_is_approved` 覆盖绝对与相对路径的仿冒脚本，以及 workspace 里有 `skills/` 时的 `-m`。
7. README。What's new 的 0068 条改成一句话：consensus 外壳后来已删除，链接加上 0070。

### 12.3 O7

O7-1 "总是允许"只记 skill 组合。
- 改动：`omicsclaw/permission/rules.py` 的 `principal_key` 在没有必填 string 属性时，取第一个必填的字符串数组；`principal_argument` 对数组取去重、排序后用 `, ` 连接的值。`install_skill_deps` 的主参数因此是 `skills`，"总是允许"写下 `install_skill_deps(sc-de, sc-qc)` 这样的规则，包、顺序、JSON 空格都不影响匹配。规则是通用的，对其他工具的影响见偏差 20。`docs/core-features/human-in-the-loop.md` 和 `mcp.md` 同步。
- 新测试：`test_rules.py` 加 3 条（字符串优先于数组、数组取去重排序后的值、空数组或混入非字符串时回落到原始 JSON）；`test_install_permissions.py` 用两条替换原来的整次调用测试：记下的规则是 `install_skill_deps(oc-skill)`，之后换一个包、改了键顺序和空格的调用不再询问、照常安装；同一组 skill 换顺序命中，多一个或少一个 skill 都不命中。

O7-2 replay 存档已有审查。
- 改动：`_replay_locked` 在解释器检查之后、跑步骤之前，把 `reviews/*.md` 移进 `reviews/archive/<id>/`（偏差 23），每份记 `{file, verdict, sha256, archived_at}` 追加到 manifest 的 `review_history`，并立即写回 manifest，`review` 置为 null。`MANIFEST_SCHEMA` 的必填键加 `review_history`，另加 `review_history_keys`。执行器输出一行 `moved N earlier review(s) to results/<NN>/reviews/archive/<id>/; review the replayed module again`。`accept --review` 的条件不变，指向存档文件时给出明确提示。`agent-skills.md` §9 和 `sub-agent.md` 同步。
- 新测试：`test_replay.py::test_replay_archives_earlier_reviews_and_records_them`（同名的 REVISE 和 APPROVE 审查先后存档进两个目录，历史按顺序记两条，sha256 与原文一致）、`test_replay_without_reviews_archives_nothing`、`test_acceptance.py::test_an_archived_review_is_refused`。

O7-3 父进程看门狗。
- 改动：新增 `skills/_sdk/notebook/_watchdog.py`。`run.py` 在 `run`、`replay` 开始时启动一个守护线程，每秒查一次 `os.getppid()`，变了就：取得共享锁（`execute_step` 写 `run_start`、`run_end` 时也持这把锁，所以不会出现两条 `run_end`）；调用 `PythonKernelRunner.kill()`，按 kernel 的进程组 SIGKILL（kernel 由 jupyter_client 放在独立 session 里，进程组里也包括步骤里 `run_cli` 起的脚本）；给当前步骤写失败的 `run_end`，`error` 为 `RunnerStopped: parent exited`，另带 `reason: "parent exited"`；往 stderr 写一行说明；`os._exit(1)`，`flock` 随进程退出释放。退出前不重建 manifest（偏差 24）。计划 §1.3 的推迟表删掉看门狗一行，§3.4.3 与 R2 改写。
- 新测试：`test_kernel.py::test_the_runner_stops_when_its_parent_shell_is_killed`。`bash -c 'python run.py run analysis/01_k > runner.log 2>&1; echo done'` 启动执行器，步骤记下执行器和 kernel 的 pid 后 sleep 120 秒；SIGKILL 外层 bash 后，断言 10 秒内执行器和 kernel 都已退出、模块锁能立即拿到、最新记账是失败的 `run_end` 且 `reason` 为 `parent exited`、`runner.log` 里有说明。去掉看门狗时这条测试失败，两个进程 10 秒后都还在。本机单独测了一次，杀掉 shell 之后 0.2 秒两个进程都退出了。

### 12.4 重跑的验收

| 阶段 | 命令 | 结果 |
|---|---|---|
| N-B1 | `PYTEST tests/sdk/notebook tests/sdk/test_public_surface.py tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py tests/test_pyproject_thin_pip_layer.py` | 191 passed、1 skipped（真实 sandbox 运行需要 `OMICSCLAW_TEST_SANDBOX=1` 和容器）、5 deselected（`skill_example` 标记，归 N-C） |
| N-B2 | `PYTEST tests/sdk/notebook` | 163 passed、5 deselected |
| N-D 的 skillenv 部分 | `PYTEST tests/skillenv tests/permission tests/permission/test_foundation_tools_keep_their_prompts.py` | 734 passed、1 skipped、1 xpassed |
| N-E | `PYTEST tests/evals` | 186 passed、26 deselected |
| N-E | `PYTEST tests/evals/dataset -m scripted_eval` | 29 passed |

另外跑过 `PYTEST tests/entry/test_permission_wiring.py tests/skillenv`（464 passed、1 skipped、1 xpassed）。没有跑全量测试。

### 12.5 变异检查重做

工作树里有未提交的修改，所以这次先把文件复制到 `/tmp`，改完跑测试再复制回来，没有用 `git checkout`。结果记在 `/tmp/oc0070-mutations-fix.log`。

| # | 变异 | 结果 |
|---|---|---|
| 6 | 过期判定忽略输入哈希（`_manifest.step_state` 的哈希比较改成 `if False and ...`） | 被发现：用例集 `upstream_change_marks_downstream_stale` 失败；`test_executor.py` 4 条失败（同一次运行里读者重跑、上游变化标记下游过期，以及 §12 b 新加的两条） |
| 7 | `run_cli` 不补记输出（删掉 `_record_outputs(ctx, output_dir)`） | 被发现：用例集 `cli_skill_from_a_step` 失败；`test_replay.py::test_run_cli_outputs_are_not_orphans`、`test_skills.py` 的两条补记测试失败 |

## 13. 第二轮修复

第二轮独立复核确认第一轮的修复和 O7 都已到位，又提了两个问题，owner 为此作出裁定 O8（已写进计划 §7.0），另有三处小问题。全部放在第二个修复提交里，仍只在本地分支上。新测试都在旧代码上跑过，确认会失败。

### 13.1 O8-1：主参数由工具自己声明

- 改动：`omicsclaw/permission/rules.py` 退回 `main` 的匹配规则，去掉"取第一个必填字符串数组"。`ToolPolicy` 新增权限类字段 `rule_argument`（默认 `None`），工具用它声明规则匹配的参数，声明的参数是字符串列表时取去重、排序后用 `, ` 连接的值。`PermissionGate.resolve`、`protects`、`remember` 都读这个字段，`remember` 新增 `policy` 参数，`AgentApp.remember_approval` 传入注册表解析出的策略。只有 `INSTALL_SKILL_DEPS_POLICY` 设了 `rule_argument="skills"`。其余工具都没有声明，匹配与 `main` 一致。`docs/core-features/mcp.md` 退回原文，`human-in-the-loop.md` 和 `tool-calling.md` 的 `ToolPolicy` 表写明新字段。
- 新测试：`tests/permission/test_gate.py` 加 3 条。auto-approve 模式下，deny 规则 `mcp__fs__clean(*"mode": "purge"*)` 仍然拒绝只有列表参数的调用；对 `{"paths": ["/tmp/x"]}` 点过"总是允许"后，带 `recursive: true` 的调用不放行；声明了 `rule_argument` 的工具，记下的规则是 `t(a, b)`，同一组值换顺序、改别的参数都命中，少一个值不命中。`test_rules.py` 的 4 条改为测声明的参数，并测没有声明时列表参数不当主参数。`test_install_permissions.py` 的两条改为经 `policy` 记规则，并用 `resolve` 断言同一组 skill 换顺序、换包时放行，多一个或少一个 skill 时不放行。`tests/tools/test_base.py` 的字段清单加上 `rule_argument`，另加一条测试把它归为权限类字段。
- 验证：把第一轮的 `rules.py` 换回来跑，gate 的前两条测试失败，正是复核用探针复现的两种放宽。

### 13.2 O8-2：执行器只允许前台运行

- 改动：`run.py` 在标准库导入之后、加载其他模块之前读下 `os.getppid()` 和 `os.getpgrp()`（`STARTED_UNDER`），交给 `_watchdog.watch_parent`。看门狗启动时先查一次，之后每秒查一次：父进程变了，或者进程组原来的组长已经退出（偏差 26），就停下。停下时的动作同第一轮，另外删掉这个步骤上一次留下的 notebook（见 13.3）。
- 契约：`OMICSCLAW.md` 的 "Running steps" 在命令表之后加一段："Run it in the foreground and wait for it to return: the runner stops itself once the shell that started it exits, so a run put in the background is cut short. When a module needs more time than one `bash` call allows, run its steps one at a time with `run <step file>`." 措辞先按 writing-for-agents 写，先写要做的事，再写硬约束，然后过 humanizer。`tests/entry/golden/ensemble_off_prompt.txt` 不含 `OMICSCLAW.md` 正文，`test_ensemble_golden.py` 不改就通过，所以没有重录。`test_runtime_contract.py`、`test_assembly.py` 以及读 `OMICSCLAW.md` 的 `tests/sdk/test_replot_hint.py`、`tests/planning/test_render.py` 都通过。
- 计划：§1.3 加推迟项"后台运行和 `--detach`"。§3.4.3 和 R2 写明前台运行、组长检查，以及单次运行的上限约等于 `tool_timeout_s` 减 15 s（`ENGINE_TIMEOUT_MARGIN`，部署默认 600 s，约 585 s）。`agent-skills.md` §9 同步。
- 新测试（`test_kernel.py`）：
  - `test_a_runner_put_in_the_background_stops_when_its_shell_exits`：shell 自成进程组（与 `bash` 工具一样），执行器放到后台，步骤开始后 shell 退出。断言执行器和 kernel 都退出、锁已释放、记账是失败的 `run_end`（reason 为 parent exited）、旧 notebook 已删。
  - `test_a_runner_started_with_nohup_stops_although_its_shell_exited_at_once`：`nohup … &` 之后 shell 立即退出。去掉组长检查时这条测试失败，执行器一直在跑。
  - 原来杀掉外层 shell 的测试改用同一组断言。

### 13.3 小问题

1. 修订记录里的审查路径。replay 存档审查时，`revisions[].accepted.review` 原先还指向 `reviews/` 下的旧路径。现在 `review_history` 的每一项多记一个 `original`（`MANIFEST_SCHEMA` 的 `review_history_keys` 同步），`_manifest.relink_reviews` 在存档时把指向被移走文件的引用改成存档后的路径。新测试：`test_acceptance.py::test_a_revision_follows_its_accepted_review_into_the_archive`，先用审查验收，再 `revise`、`replay`，断言修订记录指向存档里的文件，且文件存在。
2. 看门狗中止时的旧 notebook。`Current` 记下这个步骤的 notebook 路径，看门狗停下时删掉它，与 PercentError 的处理一致。主线程写 notebook、日志和 `run_end` 时持有同一把锁，看门狗拿到锁之后，主线程不会再把 notebook 写回来。上面三条 kernel 测试都断言旧 notebook 已删；去掉删除时，前两条失败。
3. live eval 只批准路径形式的执行器调用，`python -m skills._sdk.notebook ...` 不再批准（偏差 25）。`test_live.py` 的参数表把这一条改为拒绝，`docs/core-features/eval.md` 同步。

### 13.4 重跑的验收

| 范围 | 命令 | 结果 |
|---|---|---|
| permission | `PYTEST tests/permission` | 313 passed |
| skillenv | `PYTEST tests/skillenv` | 425 passed、1 skipped、1 xpassed |
| entry 里与权限匹配相关的测试 | `PYTEST tests/entry/test_approval.py tests/entry/test_approval_card.py tests/entry/test_cli_approval_scope.py tests/entry/test_permission_wiring.py tests/entry/test_cli_inert_output.py tests/entry/test_desktop_interactions.py tests/entry/test_desktop_stream.py` | 193 passed |
| 契约、golden、装配 | `PYTEST tests/entry/test_runtime_contract.py tests/entry/test_ensemble_golden.py tests/entry/test_assembly.py` | 74 passed、1 skipped（只在 `OMICSCLAW_WRITE_GOLDEN=1` 时重录）、1 xfailed（已知的 `cli/_configure.py:482`） |
| 执行器 | `PYTEST tests/sdk/notebook` | 166 passed、5 deselected |
| eval | `PYTEST tests/evals` | 186 passed、26 deselected |
| 用例集 | `PYTEST tests/evals/dataset -m scripted_eval` | 29 passed |

另外跑过：`PYTEST tests/tools --deselect tests/tools/test_workspace.py`，828 passed（`ToolPolicy` 加了字段）；`tests/sdk/test_public_surface.py`、`test_boundary.py`、`test_bootstrap.py`，24 passed、1 skipped。没有跑全量测试。

## 14. 交付前的小修

最终复核结论为可以交付，另提了一条不阻塞的建议：看门狗在交互式终端里会误停执行器。修复单独做一个提交。

- 问题：交互式 shell 开着 job control，会让每条管道自成一个进程组，组长是管道里的第一个命令。在 `echo x | python run.py run …` 里，组长 `echo` 立刻就退出了，看门狗的组长检查于是认定执行器已被遗弃，在第一个步骤开始前就停了下来，输出 `run.py: parent exited; stopped while no step was running`，退出码 1。复现的条件是 bash 有控制终端，并且 job control 已经生效。bash 读启动文件时 job control 还没有开启，所以复现用的 rcfile 里先写了 `set -m`。
- 改动：`skills/_sdk/notebook/_watchdog.py` 新增 `_terminal_foreground()`，打开 `/dev/tty`，用 `os.tcgetpgrp` 判断本进程组是不是终端的前台组。`abandoned()` 只在组长已退出、而且本进程组不是终端前台组时才判为被遗弃，父进程的检查不变。`bash` 工具用 `start_new_session=True` 起 shell，sandbox 的 `docker exec` 不分配终端，这两条路径都打不开 `/dev/tty`，组长检查照旧生效，后台运行仍然会被停下。
- 新测试：`test_kernel.py::test_a_runner_late_in_a_terminal_pipeline_runs_to_the_end`。用 `pty.spawn` 起一个带控制终端的交互式 bash，rcfile 先 `set -m`，再执行 `echo x | python run.py run analysis/01_k`，步骤里先 sleep 3 s 再写文件。断言退出码是 0、日志里没有 parent exited、输出文件存在。把 `_watchdog.py` 换回 `daf420cd` 的版本时，这条测试失败，报错正是上面那句。
- 验证：`PYTEST tests/sdk/notebook/test_kernel.py` 12 passed，原有的三条后台与遗弃测试都在其中；`PYTEST tests/sdk/notebook` 167 passed。没有跑全量测试。

## 15. 首次在 GitHub Actions 上运行

分支推送后开了 draft PR #40，Eval CI 在 GitHub 上第一次运行（run 36963903755）。新加的 job3 `skill-examples` 通过，用时 1 分 47 秒，pbmc3k 的下载和缓存都正常。job1 跑了 7052 条测试，只有 1 条失败：`tests/test_output_ownership_contract.py::test_skill_scripts_do_not_write_to_runner_owned_paths`。job2 依赖 job1，因此被跳过。

这条守卫是给旧 CLI skill 定的规矩：输出目录里的 `README.md` 归 runner 所有，skill 脚本不能直接写。`skills/_sdk/notebook/_layout.py` 新建模块时会写 `analysis/<NN_slug>/README.md`，守卫按文件名把它认成了违规。可是这个 README 是模块模板，写它的步骤执行器本身就是 runner。修法是在这条守卫里跳过 `skills/_sdk/notebook/`，其余 skill 文件的检查照旧，`_layout.py` 的写法没改。

各期验收只跑了与本期相关的测试，顶层的 `tests/test_*.py` 不在其中，这条失败所以一直没被发现。修好后本机跑过 `PYTEST tests/test_*.py`：228 passed、4 skipped、1 xpassed。
