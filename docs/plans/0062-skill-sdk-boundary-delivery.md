# 计划 0062 交付记录 — skill 与框架的边界：`skills/_sdk/`

**日期**：2026-09-24。**规格**：`docs/plans/0062-skill-sdk-boundary.md` 定稿版（本记录不改动计划正文）。
**状态**：阶段一、阶段二均已实施并验收；未 commit、未 `git add`（见偏离 1）。开工 commit：`0881aa7b` + 未提交工作树。

## 1. 结论

| 阶段 | 验收结论 | 关键证据 |
|---|---|---|
| 一 | **通过** | 用例 1–14 全绿；`--help` 80 → **90/94**（余 4 个 consensus 薄壳）；`test_scrna_method_contracts.py` 4 例、`test_sc_ambient_removal.py` 3 例转绿，`sc-pathway-scoring` skill 测试由收集错误转为可运行（1 passed、2 skipped：AUCell R 栈缺失）；全量失败集合 = 开工基线 − F36 的 10 项，**新增失败为空** |
| 二 | **通过** | 用例 15–24 全绿；`--help` 仍 90/94；阶段一全部用例仍绿；全量失败集合 = 开工基线 − 同样 10 项，**新增失败为空**；关键变异 M1–M20 逐条验证 |

测试解释器 `/opt/conda/envs/rapids_singlecell/bin/python`（3.13）；`--help` 探针与慢测试用 `/opt/conda/envs/OmicsClaw/bin/python`（3.11）。
`skills/_sdk/**` 全部模块在 3.11 下 import 通过。

## 2. 开工基线（开工第一步，同一工作树复跑）

输出目录：`/tmp/claude-0/…/scratchpad/impl0062/baseline/`（会话临时目录，不入库；关键数字逐字抄在下面）。

### 2.1 全量测试（附录 B 命令）

`221 failed, 6044 passed, 42 skipped, 5 deselected, 47 warnings, 46 errors in 303.32s`；`baseline_failures.txt` 267 行
（与计划第 2 版参考值一致）。清单逐字见附录 A。归因于 `core/` 断链的 10 项与计划 F36 完全一致：

```
ERROR tests/test_external_env.py
ERROR tests/test_r_script_runner.py
ERROR tests/test_r_script_runner_environment.py
FAILED tests/test_sc_ambient_removal.py::test_cellbender_without_input_requires_expected_cells
FAILED tests/test_sc_ambient_removal.py::test_simple_uses_adata_raw_when_no_counts_layer
FAILED tests/test_sc_ambient_removal.py::test_simple_uses_counts_layer_when_x_is_not_count_like
FAILED tests/test_scrna_method_contracts.py::test_builtin_communication_marks_non_statistical_significance
FAILED tests/test_scrna_method_contracts.py::test_de_runtime_dependency_validation_uses_expected_r_stacks
FAILED tests/test_scrna_method_contracts.py::test_doubletfinder_fallback_records_requested_and_executed_method
FAILED tests/test_scrna_method_contracts.py::test_scanvi_fallback_records_requested_and_executed_method
```

本次运行中 `tests/tools/test_workspace.py` 未失败；`tests/test_control_plane_documentation_contract.py` 7 项在基线内（D8 已知）。

### 2.2 附录 A 扫描（逐字摘录）

- **A1 skills→omicsclaw**：216 条、111 个文件，非测试 105 个。按符号计文件数：
  `write_result_json 88 · generate_report_header 86 · generate_report_footer 86 · sha256_file 46 · load_result_json 29 · write_replot_hint 22 · RScriptRunner 21 · validate_r_environment 18 · ensure_runtime_cache_dirs 13 · write_repro_requirements 7 · runtime.consensus.run.main 4 · read_r_result_csv 4 · check_r_tier 3 · suggest_r_install 3 · RScriptError 3 · mark_result_status 1 · emit_user_guidance 1 · emit_user_guidance_payload 1 · RScriptTimeoutError 1 · EnvNotFoundError 1 · is_env_available 1 · run_anndata_op_in_env 1 · providers.chat_completion.call_chat_completion 1`（与 F1 一致）。
- **A1 framework**：`omicsclaw.core` 只被 `core/` 自身与 4 个测试 import；框架 import `skills.*` 两处：`common/report.py`:517、`autoagent/metrics_compute.py`:207/:223（与 F18/F19 一致）。
- **A2 字符串**：`skills/spatial/_lib/dependency_manager.py 104 omicsclaw.core.external_env`（唯一一处，F3）。
- **A3 `--help`**：**80 成功、14 失败**，全部 `ModuleNotFoundError: No module named 'omicsclaw.skill'`（10 个 sc 脚本 + 4 个 consensus 薄壳，F10）。
- **A4 closure**：16 个定义、`lines 381 of 675`（F21）。
- **A5 registry**：`entries 74 keys 62`；12 个重叠键中 10 个 `install_cmd` 不同；唯一 NONLITERAL `pybanksy`（`availability_check`）；`module shared by keys: {'pymzml': {'pymzml', 'mzmine'}}`（F28）。
- **A6 调用名**：32 个，全部命中；`paste`/`scvi`/`tangram` 靠 `module` 反查，`STAGATE_pyG` 靠规范化；`spatialde` 当时是键（F29）。
- **A7 引导**：`94 {'parents[N]-oneliner': 7, '_PROJECT_ROOT-parent-chain': 79, 'anchor-omicsclaw': 6, 'other': 1, 'none': 1}`（F30）。
- **A8**：`"omicsclaw" / "r_scripts"` 23 行 / 19 个文件；认领标记只在 `surfaces/desktop/server.py`、`common/output_claim.py`、`autoagent/output_ownership.py`；`CONTRIBUTING.md` :108、:172、:351 三处旧引用。

## 3. 阶段一

### 3.1 TDD：先红

新写/搬来的测试在实现前运行（`--continue-on-collection-errors`）：**21 failed, 9 passed, 7 errors**。红的是用例 1、2、5b（B1/B9）、7b（4 例）、13（10 个 sc 脚本 `--help`）、8（3 例）、12（环境读取清单）；7 个收集错误是 `skills._sdk` / `CONTROL_CREDENTIAL_NAMES` 尚不存在（用例 6、7、9、10、11 及两个搬来的测试）。B2/B5/B7/B8、B4（两项已知表）在开工时即为绿——B2 的违例集合开工时就恰等于 `{_llm.py}`，符合计划。

### 3.2 实施

1. 新建 `skills/_sdk/__init__.py`（只定义 `REPO_ROOT`）；`omicsclaw/core/{external_env,r_script_runner,r_utils,r_dependency_manager}.py` 搬到 `skills/_sdk/` 同名，`dependency_manager.py` 搬为 `skills/_sdk/deps.py`；`omicsclaw/r_scripts/`（28 个 `.R`）搬为 `skills/_sdk/r_scripts/`；删 `omicsclaw/core/__init__.py`（目录只剩未跟踪的 `__pycache__/`）。
2. 删 skill 侧剔除：3 处 import、6 处调用；`_build_r_env` 改为 `dict(os.environ)`；`_SCRIPTS_DIR` 改为公开常量 `R_SCRIPTS_DIR = <_sdk>/r_scripts`。
3. 23 个非测试文件 + 2 个 skill 测试的 `omicsclaw.core.X` → `skills._sdk.X`（`dependency_manager` → `deps`），只改模块路径；F3 的字符串改为 `"skills._sdk.external_env"`；F6 的 23 行按别名规则改为 `_SDK_R_SCRIPTS_DIR`（`from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR`，与原 `RScriptRunner` import 同一作用域；`sc_differential_abundance.py` 的模块常量用模块级别名 import）。
4. 框架：`omicsclaw/tools/builtin/bash.py` 新增 `CONTROL_CREDENTIAL_NAMES`、`without_control_credentials`（大小写不敏感），`_start` 传 `env=without_control_credentials()`；`ENVIRONMENT_READERS` 加 `tools/builtin/bash.py`；`omicsclaw/ensemble/execution.py` 只改 `LocalExecutor.environment` 一行与同一 import 行。
5. 测试：4 个测试搬进 `tests/sdk/`，F35 三例改写为"原样继承"断言（用例 6、7）；新增用例 1–5、5b、7b、8、9、10–13。
6. 文档：`AGENTS.md`（结构树删 `core/`、加 `skills/_sdk/`；Import convention 加 `_sdk` 规则与"剔除只在框架启动边界"）、`docs/FRAMEWORK-REBUILD.md` "Kept and importable"、`docs/core-features/agent-skills.md` §9.3、`0_setup_env.sh` 注释。

### 3.3 验收证据

| 检查 | 命令 | 结果 |
|---|---|---|
| 阶段一用例（含慢测试） | `pytest -o addopts="--import-mode=importlib" tests/sdk tests/tools/test_bash_child_environment.py tests/ensemble/test_local_executor_credentials.py tests/launch/test_the_environment_is_read_in_known_places.py`，`OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python` | **75 passed, 3 skipped**（3 个 skip 是 `test_external_env.py` 里需要 mamba 当前环境的既有用例） |
| 用例 14 | `pytest tests/test_scrna_method_contracts.py tests/test_sc_ambient_removal.py skills/.../sc-pathway-scoring/tests/test_sc_pathway_scoring.py` | **7 passed, 3 deselected**；sc-pathway-scoring 不带标记过滤：1 passed、2 skipped（AUCell R 栈缺失） |
| §5 主命令 | 计划 §5 原文 | **1059 passed, 6 skipped, 14 deselected**（179.6 s） |
| `--help` 探针 | 附录 A3 | **90 成功、4 失败**（4 个 consensus 薄壳，均 `omicsclaw.skill`） |
| 全量回归 | 附录 B | `214 failed, 6100 passed, 45 skipped, 15 deselected, 43 errors`；新增失败 **∅**；消失的失败恰为 §2.1 的 10 项 |

## 4. 阶段二

### 4.1 TDD：先红

用例 15–24 与 B3/B6/B10 全量、用例 9 的 `deps.is_available` 版本在实现前运行：**31 failed, 59 passed, 3 errors**（`test_result*.py`、`test_replot_hint.py` 因模块不存在收集失败）。

### 4.2 实施

1. §3.3：新建 `skills/_sdk/{checksums,report,result,runtime_env,user_guidance}.py`；`write_owned_text` 按 Q1 简化（见 §7）；`RESULT_SCHEMA` 为模块级纯字面量，`optional` 只作说明；`RESULT_STATUS_VALUES = ("ok","partial","failed")`。`write_replot_hint` 移到 `skills/singlecell/_lib/viz/r/replot_hint.py`（改用 `_sdk.result`），框架 `omicsclaw/common/report.py` 删除该函数（Q11 唯一改动）。
2. §3.4：`skills/_sdk/deps.py` 重写为单一 registry（61 键）与 `_resolve`/`require`/`get`/`is_available`/`install_hint`/`validate_r_environment`；删 `DOMAIN_TIERS`/`check_dependencies`/`get_installed_tiers`；删四份 `_lib/dependency_manager.py`；30 个文件的 import 改写（`from . import dependency_manager as dm` 与 `from skills.<d>._lib import dependency_manager as sc_dep_manager` → `from skills._sdk import deps as <原别名>`，`from .dependency_manager import …` → `from skills._sdk.deps import …`）；删 metabolomics/proteomics `_lib/__init__.py` 的 re-export。
3. 机械改写：96 个文件（95 个 skill + 模板）的 `omicsclaw.common.*` import → `skills._sdk.*`（`write_replot_hint` → single-cell `_lib`）。改写脚本在会话临时目录、不入库；它对每个文件断言"改写前后 import 绑定的名字集合相同"，全部通过。两处多行 import 首行的 `# noqa: E402` 被改写脚本丢掉，已手工补回（`bulkrna_enrichment.py`、模板）。
4. §3.11：93 个 import `skills.*` 的主脚本与模板换成统一引导块（`consensus_interpret.py` 不 import `skills.*`，不加）；21 个在引导之外还用 `_PROJECT_ROOT` 的脚本加 `from skills._sdk import REPO_ROOT as _PROJECT_ROOT  # noqa: E402`。计划说 31 个：另外 10 个 single-cell 脚本只把 `_PROJECT_ROOT` 用于 R 脚本路径，阶段一换成 `_SDK_R_SCRIPTS_DIR` 后已不再使用它。改写时逐一核对旧 `_PROJECT_ROOT` 的 `.parent` 链都解析到仓库根，`REPO_ROOT` 与旧值相同。
5. 守卫与契约测试全量上线；B4 已知表收缩为 `{autoagent/metrics_compute.py}`。
6. 文档：`CONTRIBUTING.md` :108（示例改为引导块 + `skills._sdk.report`/`result`）、:172、:351（`DEPENDENCIES` 与字段格式）；`AGENTS.md` "Dependency source of truth"、结构树（`common/`、`_sdk/`）、"Import convention"；`docs/core-features/agent-skills.md` §9.3 等 4 处与 `docs/FRAMEWORK-REBUILD.md` 两处；`README.md` 里程碑一条。`CLAUDE.md`、`templates/skill/README.md` 经 grep 核对**没有** `omicsclaw.common` / `dependency_manager` 提及，未改。

### 4.3 验收证据

| 检查 | 命令 | 结果 |
|---|---|---|
| `tests/sdk` 全部（含慢测试 13、24） | `OMICSCLAW_TEST_BASE_PYTHON=… pytest -o addopts="--import-mode=importlib" tests/sdk` | **140 passed, 4 skipped**（3 个 mamba 既有 skip；23c 真实沙箱 skip，见偏离 5） |
| §5 主命令 | 计划 §5 原文 | **1135 passed, 7 skipped, 15 deselected**（195.8 s） |
| `--help` 探针 | 附录 A3 | **90 成功、4 失败**（同阶段一） |
| 全量回归 | 附录 B | `214 failed, 6176 passed, 46 skipped, 16 deselected, 43 errors`（343 s）；新增失败 **∅**；消失的失败恰为 §2.1 的 10 项 |
| A1 复跑 | `scan_imports.py skills` | skill→omicsclaw 只剩 B3 的 5 个已知项与 `skills/**/tests/` 下 4 个（3 个基准脚本 `omicsclaw.skill.runner`、`consensus-domains/tests/test_cli_smoke.py`，Q5 排除、计划 §7 非目标） |
| A1 framework 复跑 | `scan_imports.py framework` | 非测试的框架→skills 只剩 `autoagent/metrics_compute.py` |
| A2 复跑 | `scan_strings.py` | 空 |
| A7 复跑 | `bootstrap_classes.py` | 93 个统一块 + `consensus_interpret.py` 不引导（脚本的旧分类法把新块计为 `other`） |
| R1 人工核对 | `grep -rn '"-m", "omicsclaw\|runpy' skills` | 无命中 |
| R10 wheel | 仓库副本（会话临时目录）上 `pip wheel --no-deps --no-build-isolation` | wheel 内 `skills/_sdk/` 39 个文件：11 个 `.py` + 28 个 `.R`；无 `omicsclaw/core`、`omicsclaw/r_scripts` |
| R11 安装态 | 把 wheel `pip install --target` 到临时目录，无 `PYTHONPATH` 跑 `site/skills/bulkrna/bulkrna-qc/bulkrna_qc.py --help` | 退出 0；`skills._sdk.REPO_ROOT` 指向 `site/` |

### 4.4 给 0061 的接口（§3.4、§3.9 逐条核对）

- 位置：`skills/_sdk/deps.py`，模块级带注解赋值 `DEPENDENCIES: dict[str, dict] = {…}`（`AnnAssign`），值为纯字面量；`ast.literal_eval` 结果与 import 所得相等（用例 22）。
- 字段：必有 `module`/`kind`/`install`/`description`，可选只有 `also`（字符串列表）与 `alt_env`；`kind ∈ {pip, git, r}`；`pip` 类 `install == "pip install " + " ".join([键, *also])`。
- 规模与特例：61 键；`git` 类恰为 {STAGATE-pyG, pybanksy, STalign}；`r` 类恰为 {xcms, metaboanalyst}（`module` 分别为 R 包名 `xcms`、`MetaboAnalystR`）；有 `also` 的恰为 {singler}；有 `alt_env` 的恰为 {pybanksy → omicsclaw_banksy}。键按 `## Dependencies` 拼写（`SpatialDE`），`mzmine` 并入 `pymzml`。
- 规范化后键唯一、`module` 全表唯一、无"既是某键规范化形式又是另一条目 `module`"的名字（用例 22）。
- 解析顺序：键 → PEP 503 规范化键 → `module` 反查 → 回落；`_resolve` 返回 `(键或 None, 条目)`，回落时键为 `None`。

## 5. `--help` 探针前后对比

| 时点 | 成功 | 失败 | 失败明细 |
|---|---|---|---|
| 开工基线 | 80 | 14 | 10 个 sc 脚本（sc-ambient-removal、sc-batch-integration、sc-cell-annotation、sc-cell-communication、sc-de、sc-doublet-detection、sc-enrichment、sc-pathway-scoring、sc-preprocessing、sc-pseudotime）+ 4 个 consensus 薄壳，全部 `No module named 'omicsclaw.skill'` |
| 阶段一后 | **90** | 4 | sc-consensus-clustering、sc-consensus-integration、sc-consensus-pseudotime、consensus-domains（`omicsclaw.skill`，经 `omicsclaw/runtime/…`，归 0058） |
| 阶段二后 | **90** | 4 | 同上；用例 24 把失败集合钉为恰好这 4 个 |

## 6. 变异验证

方法：会话临时目录里的脚本对一个文件做字符串替换（或新建文件），跑指定测试，结束后按字节恢复原文件（或删除新建文件）；每条结束后 `git status` 与开工一致。"红"指至少一个测试失败。

| # | 变异 | 结果 | 变红的用例 |
|---|---|---|---|
| M1 | `genomics_qc.py` 加惰性 `from omicsclaw.common.report import write_result_json` | 红 | 15（B3） |
| M2 | `spatial/_lib/qc.py` 加 `__import__("omicsclaw.core.external_env")` | 红 | 2（B1）、5b（B9），另 B2/B3/B6/B10 |
| M3 | 恢复 `omicsclaw/core/__init__.py`；在 `omicsclaw/r_scripts/` 放一个 `.R` | 红 / 红 | 1 |
| M4 | `without_control_credentials` 不过滤 / 改为大小写敏感 / `_start` 去掉 `env=` | 红 / 红 / 红 | 10 |
| M5 | `LocalExecutor.environment` 去掉过滤；`ENV_WHITELIST` 加入 token | 红 / 红 | 11 |
| M6 | 删掉 `_llm.py` 那行 import 而不改已知表 | 红 | 3（B2）、15（B3） |
| M7 | `_sdk/result.py` import `skills.singlecell._lib.io` | 红 | 4（B5）；阶段一另以 `r_utils.py` import `omicsclaw.common.report` 验证 B5 与用例 8 |
| M8 | (a) `_sdk` 模块新增不带 `_` 的函数但不进 `__all__` | **绿（按设计）** | §3.10：不进 `__all__` 的公开名允许存在、只禁止 skill 使用；闸门是 `__all__` |
|  | (a2) 新函数写进 `__all__` 而不改 `PUBLIC_SURFACE` | 红 | 18 |
|  | (b) skill import `_sdk` 的非公开名（`deps._resolve`） | 红 | 18 |
|  | (c) 冻结一个无人使用的名字（`RScriptResult` 进 `__all__`） | 红 | 18 |
| M9 | `write_result_json` 把 `summary` 改名 | 红 | 19、20(a)(d) |
| M10 | `DEPENDENCIES` 某值含 `str(...)` 调用；含 lambda | 红 / 红 | 22 |
| M11 | 框架 `common/report.py` 恢复对 `skills.*` 的 import | 红 | 16（B4） |
| M12 | 引导块改回 `parents[3]`；`next(..., None)` 去掉默认值 | 红 / 红 | 23；后者另有 23b（副本在仓库外时 `StopIteration`） |
| M13 | 环境读取清单删掉 `tools/builtin/bash.py` | 红 | 12 |
| M14 | `_sdk/r_script_runner.py` 恢复过滤；`external_env.py` 子进程过滤环境 | 红 / 红 | 5（B8）、7；6 |
| M15 | `write_owned_text` 改为直接写目标 | 红 | 19（5 例） |
| M16 | `_resolve` 去掉 `module` 反查 | 红 | 22（`scvi`/`tangram`/`paste` 进入回落集合） |
| M17 | `sc_enrichment.py` 加不带别名的 `R_SCRIPTS_DIR` import | 红 | 7b |
| M18 | `preflight.py`:622 改回 `from skills.singlecell._lib import dependency_manager` | 红 | 3（B2） |
| M19 | `_sdk` 一侧改 `DISCLAIMER`；框架一侧改 | 红 / 红 | 20(f) |
| M20 | `_sdk.validate_result_envelope` 开始校验 `lineage` 类型 | 红 | 20(b) |
| 补 | 用例 3 的正向：`_lib` 惰性 `from skills._sdk import deps` | 绿（预期） | — |
| 补 | B6：proteomics `_lib` import spatial `_lib`；B10：genomics `_lib/__init__` import `omicsclaw.common.report` | 红 / 红 | 17 |
| 补 | B7 `_sdk/SKILL.md`；B8 skill 源码写入 token 名；用例 9 改回 `omicsclaw.core.external_env` | 红 / 红 / 红 | 4、5、9 |
| 补 | 用例 20(e) 改前缀；用例 21 未知 skill 也写入；用例 22 `r` 类走 `find_spec`、`alt_env` 异常外抛 | 红 ×4 | 20(e)、21、22 |

阶段二完成后又在最终工作树上复跑 M2、M3、M4、M5、M13、M14、M17 与用例 9 的变异，仍全部为红。

## 7. 偏离与理由

1. **`git mv` 改为普通 `mv`/`rm`**。计划写 `git mv`，但本次派发的硬规则禁止 `git add`，而 `git mv` 会改动暂存区。所以搬家只动工作树：git 现在看到的是"删除 + 未跟踪"。提交时 `git add -A` 后，git 会按内容相似度认出这些改名。搬移的 4 个测试同样处理。
2. **B2/B3 已知表的形状**：用 `(文件, 模块)` 对表示，`_llm.py` 的已知模块写作完整的 `omicsclaw.providers.chat_completion`（计划写 `omicsclaw.providers`）。比较仍然是"恰好相等"，只是粒度更细。
3. **公开面在阶段二才冻结**：§3.10 末句说阶段一"只冻结搬来的 5 个模块"，而用例 18 列在阶段二。这里按用例清单，在阶段二一次上线；`external_env.__all__` 从 5 个名字收缩为 3 个（`run_python_in_env`、`run_script_in_env` 只有测试在用，仍可被测试 import）。
4. **B10 的"报错链出现 omicsclaw"按异常链判定**，不看整段 traceback 文本：traceback 会打印源码行，例如 `ensure_runtime_cache_dirs("omicsclaw")` 里的字符串，按全文匹配会误报。判定对象是异常链上每个异常的消息与 `name` 属性。其余异常（非 omicsclaw、非缺包）只打印出来，不算违例，与计划一致。
5. **用例 23c 的真实沙箱分支没有自动化**：本机没有 docker/podman，无法验证 `SandboxExecutor` 路径。测试在 `OMICSCLAW_TEST_SANDBOX=1` 且有容器运行时的情况下仍然 skip，并写明原因。替代方案每次都跑：把 `skills/` 与 `omicsclaw/` 复制成只读副本后运行，断言退出 0、副本文件列表不变。复制时排除 `tests/`、`data/`、`*.h5ad`，以控制体积。
6. **registry 内容的选择**（计划没写到的部分，取最保守做法）：spatial 与 singlecell 重叠的 12 个键，`description` 取 spatial 那份（旧 spatial 表更完整）。`STAGATE-pyG`、`pybanksy` 的 `install` 按计划示例写成纯命令，删掉了原文括注（"requires torch + torch_geometric"、"or sub-env: bash 0_setup_env.sh --with-banksy"）；`pybanksy` 的 `description` 仍然提到 `omicsclaw_banksy` 子环境。singlecell 调用方看到的安装提示从 `pip install -e ".[singlecell-…]"` 变为 `pip install <键>`，这是计划规定的结果。
7. **`require` 的报错去掉了旧 spatial 版本末尾的 `pip install -e ".[full]"` 提示**：那条命令只在源码检出的仓库根下有效，与计划"`pip install -e ".[extra]"` 形式不再出现"的方向一致。报错仍含 `install` 与 `feature`。回落条目的 `description` 为空串，信息里用名字代替。
8. **`write_owned_text` 细节**：拒绝的情形有三种：输出根之上与之内任一祖先是符号链接（与框架一致），越出输出根（先按词法判断，再按 `resolve()` 判断），目标是符号链接或已存在但不是普通文件。保留"只替换普通文件"，只丢掉硬链接数检查、认领标记与 Windows reparse 判定（Q1）。`mark_result_status` 经 `load_result_json` 读，因此与读取侧同样拒绝符号链接。
9. **用例 10 走完整的 `BashTool.execute` 路径**（带审批上下文），不直接调用 `_start`，这样覆盖的是 agent 真实会走的调用链。
10. **`sc_annotate.py` 的引导块位置**：原脚本在旧引导之前已经 import 了 `omicsclaw.common.runtime_env`，只有在 `omicsclaw` 已安装时才可用。改写后这一行成了 `skills._sdk` import，按"第一条 `skills.` import 之前"的规则，把引导块移到了它前面。
11. **旧引导上方的注释**：紧贴旧引导、提到 `omicsclaw` 的连续注释行删掉了。consensus 薄壳与 `sc-integrate-cluster` 上方"so `omicsclaw` resolves"之类的注释保留，因为锚点目录同样提供 `omicsclaw`，注释仍然成立。
12. **`LocalExecutor.environment` 的 docstring 没改**：严格遵守"只改一处"。它仍写"whitelisted inherited variables, then *extra*"，没有提剔除；剔除行为由用例 11 钉住。
13. **新增测试辅助模块 `tests/sdk/_scan.py`**（计划没列），供守卫、公开面等测试共用 AST 扫描与"模块在盘上存在"的判定。
14. **用例 24 用 8 线程并行**跑 94 个 `--help`（约 1 分钟）；用例 23a/23b 用测试解释器（rapids 3.13）跑 3 个轻量脚本，完整探针用 `OmicsClaw` 3.11。
15. **文档改动比清单多两处**：`docs/core-features/agent-skills.md` 除 §9.3 外，另有第 65、78、482、536 行也引用 `omicsclaw.common.report` 或 `write_replot_hint` 的旧位置；`docs/FRAMEWORK-REBUILD.md` 的 "Open after the migration" 表里 `replot` 一行也是。这些都随代码位置更新。`.env.example` 计划没有要求，未改。

## 8. 改动文件清单

**新增**
- `skills/_sdk/__init__.py`、`checksums.py`、`report.py`、`result.py`、`runtime_env.py`、`user_guidance.py`
- `skills/singlecell/_lib/viz/r/replot_hint.py`
- `tests/sdk/__init__.py`、`_scan.py`、`test_boundary.py`、`test_sdk_imports.py`、`test_r_script_paths.py`、`test_banksy_fallback.py`、`test_sc_scripts_help.py`、`test_deps_registry.py`、`test_result.py`、`test_result_contract.py`、`test_replot_hint.py`、`test_public_surface.py`、`test_bootstrap.py`、`test_help_probe.py`
- `tests/tools/test_bash_child_environment.py`、`tests/ensemble/test_local_executor_credentials.py`
- `docs/plans/0062-skill-sdk-boundary-delivery.md`（本文件）

**搬移（工作树内 mv，见偏离 1）**
- `omicsclaw/core/{external_env,r_script_runner,r_utils,r_dependency_manager}.py` → `skills/_sdk/` 同名（改 import、删剔除、加 `__all__`）
- `omicsclaw/core/dependency_manager.py` → `skills/_sdk/deps.py`（阶段二重写为合并 registry）
- `omicsclaw/r_scripts/*.R`（28 个）→ `skills/_sdk/r_scripts/`（内容不变）
- `tests/test_{external_env,r_script_runner,r_script_runner_environment,r_dependency_manager}.py` → `tests/sdk/`

**删除**
- `omicsclaw/core/__init__.py`
- `skills/{spatial,singlecell,metabolomics,proteomics}/_lib/dependency_manager.py`

**修改：框架**
- `omicsclaw/tools/builtin/bash.py`（`CONTROL_CREDENTIAL_NAMES`、`without_control_credentials`、`_start` 的 `env=`、`__all__`）
- `omicsclaw/ensemble/execution.py`（import 行多取一个名字 + `LocalExecutor.environment` 一行）
- `omicsclaw/common/report.py`（删 `write_replot_hint`）
- `tests/launch/test_the_environment_is_read_in_known_places.py`（加一条清单项）

**修改：skill 与模板**：124 个 skill 文件加模板。其中 119 个非测试 skill 文件现在含 `skills._sdk` 或引导块，按域计：bulkrna 14、genomics 10、literature 1、metabolomics 8、proteomics 8、singlecell 43、spatial 35；另有 metabolomics/proteomics `_lib/__init__.py`（删 re-export）、`skills/spatial/_lib/__init__.py`（docstring 删 `dependency_manager` 行）、2 个 skill 测试（`sc-pathway-scoring`、`sc-preprocessing`）。

**修改：文档**：`AGENTS.md`、`CONTRIBUTING.md`、`README.md`、`docs/FRAMEWORK-REBUILD.md`、`docs/core-features/agent-skills.md`、`0_setup_env.sh`（注释）。

## 9. 遗留

- **4 个 consensus 薄壳与 `consensus-interpret/_llm.py`** 仍 import 框架（B3/B2 具名已知项，归 0058）；`skills/**/tests/` 下 3 个基准脚本的 `omicsclaw.skill.runner` 与 `consensus-domains/tests/test_cli_smoke.py`（计划 §7 非目标）。
- **`replot` 块仍指向不存在的 `python omicsclaw.py replot`**（只搬家，未修，计划 §7）。
- **计划范围外的过时文档**：`llms.txt`:212–217 仍写 `omicsclaw/common/` 与 `dependency_manager.py`；`docs/architecture/overview.mdx`、`orchestrator.mdx` 引用早已不存在的 `omicsclaw/core/registry.py` 等。均未改。
- **23c 真实沙箱验证**留到有容器运行时的环境（偏离 5），可与 0056 遗留的沙箱真机验证一起做。
- **暂存区**：所有改动都在工作树里、没有暂存；提交前需要 `git add -A`（或逐项添加），git 会按相似度识别改名。
- **`omicsclaw/core/__pycache__/`** 是未跟踪的缓存目录，还留在盘上；B1 与 B2 的判定都不受它影响。
- **框架 `omicsclaw/common/report.py` 与 `_sdk` 两份实现并存**（R5），由用例 20 钉住；按 Q11 未删减框架侧。
- 0061 P1 现在可以按 §4.4 读取 `skills/_sdk/deps.py`。

## 附录 A：开工基线失败清单（`baseline_failures.txt`，267 行，逐字）

```
ERROR tests/runtime/consensus/test_integration_panel.py
ERROR tests/runtime/consensus/test_lca_wrapper.py
ERROR tests/runtime/consensus/test_plan_narrative.py
ERROR tests/runtime/consensus/test_report_panel_diagnostics.py
ERROR tests/runtime/consensus/test_run_entry.py
ERROR tests/runtime/consensus/test_team_runtime.py
ERROR tests/runtime/consensus/test_templates.py
ERROR tests/runtime/workflow/test_fan_out.py
ERROR tests/test_adaptive_env_phase3.py
ERROR tests/test_autoagent_accepted_commit.py
ERROR tests/test_autoagent_constants.py
ERROR tests/test_autoagent_edit_surface.py
ERROR tests/test_autoagent_errors.py
ERROR tests/test_autoagent_failure_memory.py
ERROR tests/test_autoagent_hard_gates.py
ERROR tests/test_autoagent_harness_directive.py
ERROR tests/test_autoagent_harness_integration.py
ERROR tests/test_autoagent_harness_loop.py
ERROR tests/test_autoagent_harness_workspace.py
ERROR tests/test_autoagent_judge.py
ERROR tests/test_autoagent_llm_client.py
ERROR tests/test_autoagent_llm_client_deepseek.py
ERROR tests/test_autoagent_output_ownership.py
ERROR tests/test_autoagent_patch_engine.py
ERROR tests/test_autoagent_process_owner.py
ERROR tests/test_autoagent_stage1.py
ERROR tests/test_autoagent_start_body_guard.py
ERROR tests/test_autoagent_trace.py
ERROR tests/test_benchmark_campaign.py
ERROR tests/test_chat_abort_cancel_event.py
ERROR tests/test_desktop_chat_wire_contract.py
ERROR tests/test_discover_file_trust.py
ERROR tests/test_evaluation_protocol.py
ERROR tests/test_external_env.py
ERROR tests/test_notebook_kernel_manager.py
ERROR tests/test_outbox_executor.py
ERROR tests/test_outputs_session_link.py
ERROR tests/test_r_script_runner.py
ERROR tests/test_r_script_runner_environment.py
ERROR tests/test_remote_auth_rejection_log.py
ERROR tests/test_remote_canonical_auth.py
ERROR tests/test_remote_jobs_atomic_write.py
ERROR tests/test_remote_jobs_reconcile.py
ERROR tests/test_remote_sse_log_tail.py
ERROR tests/test_remote_write_text_atomic.py
ERROR tests/test_skill_promotion_sidechannel.py
FAILED tests/routing/test_consensus_interpret_hint.py::test_is_typed_consensus_run_false_for_missing_path
FAILED tests/routing/test_consensus_interpret_hint.py::test_is_typed_consensus_run_false_for_non_directory
FAILED tests/routing/test_consensus_interpret_hint.py::test_is_typed_consensus_run_false_when_any_artifact_missing
FAILED tests/routing/test_consensus_interpret_hint.py::test_is_typed_consensus_run_true_when_all_artifacts_present
FAILED tests/routing/test_consensus_interpret_hint.py::test_suggest_interpret_args_hint_is_ready_to_paste_into_slash_run
FAILED tests/routing/test_consensus_interpret_hint.py::test_suggest_interpret_returns_none_for_non_typed_run
FAILED tests/routing/test_consensus_interpret_hint.py::test_suggest_interpret_returns_suggestion_for_typed_run
FAILED tests/routing/test_consensus_interpret_hint.py::test_suggest_interpret_run_id_falls_back_to_dirname_when_plan_lacks_run_id
FAILED tests/routing/test_consensus_interpret_hint.py::test_suggest_interpret_typed_run_id_falls_back_when_plan_malformed
FAILED tests/runtime/consensus/test_continuous_driver.py::test_degenerate_member_dropped
FAILED tests/runtime/consensus/test_continuous_driver.py::test_direction_safeguard_flips_anticorrelated
FAILED tests/runtime/consensus/test_continuous_driver.py::test_fail_loud_when_too_few_nondegenerate
FAILED tests/runtime/consensus/test_continuous_driver.py::test_happy_path_writes_banner_and_artifacts
FAILED tests/runtime/consensus/test_continuous_driver.py::test_nonfinite_member_dropped_whole
FAILED tests/runtime/consensus/test_continuous_driver.py::test_partial_coverage_member_dropped_whole
FAILED tests/runtime/consensus/test_continuous_driver.py::test_too_few_full_coverage_members_raises
FAILED tests/runtime/consensus/test_continuous_driver.py::test_weak_agreement_guard_flags_disagreement
FAILED tests/runtime/consensus/test_continuous_driver.py::test_weighted_operator_runs
FAILED tests/runtime/consensus/test_continuous_planner_reader.py::test_cli_categorical_rejects_continuous_operator
FAILED tests/runtime/consensus/test_continuous_planner_reader.py::test_cli_continuous_rejects_categorical_operator
FAILED tests/runtime/consensus/test_driver.py::test_driver_catches_lca_unavailable_and_reraises_cleanly
FAILED tests/runtime/consensus/test_driver.py::test_driver_input_path_overrides_caller_supplied_relative_value
FAILED tests/runtime/consensus/test_driver.py::test_driver_persists_input_path_in_plan_json
FAILED tests/runtime/consensus/test_driver.py::test_driver_raises_insufficient_bcs_when_selector_picks_fewer_than_2
FAILED tests/runtime/consensus/test_driver.py::test_driver_raises_insufficient_survivors_when_under_2
FAILED tests/runtime/consensus/test_driver.py::test_driver_returns_complete_typed_consensus_run
FAILED tests/runtime/consensus/test_driver.py::test_driver_survivor_error_preserves_member_failure_details
FAILED tests/runtime/consensus/test_driver.py::test_driver_writes_4_canonical_artifacts
FAILED tests/runtime/consensus/test_driver.py::test_format_typed_report_starts_with_banner
FAILED tests/runtime/consensus/test_driver.py::test_integration_panel_rejects_claim_alias_h5ad
FAILED tests/runtime/consensus/test_driver.py::test_integration_panel_runs_even_when_spatial_panel_disabled
FAILED tests/runtime/consensus/test_driver.py::test_report_and_artifacts_carry_explainability
FAILED tests/runtime/consensus/test_planners.py::test_chair_all_from_param_hints
FAILED tests/runtime/consensus/test_planners.py::test_chair_default_offline_returns_members
FAILED tests/runtime/consensus/test_planners.py::test_derive_non_voting_baseline_gated_on_integration_source
FAILED tests/runtime/consensus/test_planners.py::test_resolve_timeout_keyed_on_planned_scvi_member
FAILED tests/runtime/consensus/test_sc_integrate_cluster.py::test_none_baseline_emits_reader_and_panel_artifacts
FAILED tests/runtime/consensus/test_spatial_metrics.py::test_mlami_deterministic_under_same_seed
FAILED tests/runtime/consensus/test_spatial_metrics.py::test_mlami_perfect_alignment_scores_high
FAILED tests/runtime/consensus/test_spatial_metrics.py::test_mlami_random_labels_scores_low
FAILED tests/runtime/consensus/test_spatial_metrics.py::test_mlami_value_in_unit_interval
FAILED tests/runtime/consensus/test_spatial_panel.py::test_driver_no_spatial_panel_keeps_reader_intrinsic
FAILED tests/runtime/consensus/test_spatial_panel.py::test_driver_skips_panel_for_non_spatial_flavour_even_with_coords
FAILED tests/runtime/consensus/test_spatial_panel.py::test_driver_uses_spatial_panel_when_coords_present
FAILED tests/runtime/preflight/test_sc_batch.py::test_auto_prepare_rejects_claim_alias_processed_h5ad
FAILED tests/runtime/preflight/test_sc_batch.py::test_format_batch_key_clarification_explains_when_requested_key_not_found
FAILED tests/runtime/preflight/test_sc_batch.py::test_format_batch_key_clarification_lists_candidates_when_available
FAILED tests/runtime/preflight/test_sc_batch.py::test_normalize_obs_key_collapses_punctuation_and_lowers
FAILED tests/runtime/preflight/test_sc_batch.py::test_resolve_requested_batch_key_falls_back_to_extra_flag
FAILED tests/runtime/preflight/test_sc_batch.py::test_resolve_requested_batch_key_prefers_direct_arg_over_extra_flag
FAILED tests/runtime/preflight/test_sc_batch.py::test_score_batch_candidate_high_score_for_exact_preference_match
FAILED tests/runtime/preflight/test_sc_batch.py::test_score_batch_candidate_includes_preview_examples
FAILED tests/runtime/preflight/test_sc_batch.py::test_score_batch_candidate_rejects_excluded_columns
FAILED tests/runtime/preflight/test_sc_batch.py::test_score_batch_candidate_rejects_singleton_or_unique_per_cell
FAILED tests/test_autoagent_admission_authority.py::test_default_skill_surface_is_target_local_and_minimal
FAILED tests/test_autoagent_admission_authority.py::test_default_skill_surface_rejects_non_python_or_aliased_entry
FAILED tests/test_autoagent_admission_authority.py::test_hard_gate_receipt_and_ledger_persist_exact_evidence_bytes
FAILED tests/test_autoagent_admission_authority.py::test_parameter_candidate_must_pass_hard_gates_before_judgment
FAILED tests/test_autoagent_admission_persistence.py::test_harness_admission_trace_persistence_failure_fails_closed
FAILED tests/test_autoagent_admission_persistence.py::test_parameter_admission_reconstruction_failure_is_a_failed_verdict
FAILED tests/test_bot_n_epochs_routing.py::test_argv_builder_still_rewrites_n_epochs_for_spatial_domains
FAILED tests/test_bot_n_epochs_routing.py::test_bot_skill_orchestration_has_no_spatial_domain_identification_special_case
FAILED tests/test_bot_n_epochs_routing.py::test_bot_tool_executors_has_no_spatial_domain_identification_special_case
FAILED tests/test_bot_n_epochs_routing.py::test_spatial_domains_canonical_alias_makes_branch_unreachable
FAILED tests/test_control_plane_documentation_contract.py::test_adr_0059_documents_the_narrow_attachment_production_slice
FAILED tests/test_control_plane_documentation_contract.py::test_effective_decision_chain_includes_reclosure_adrs
FAILED tests/test_control_plane_documentation_contract.py::test_project_memory_scope_and_projection_fence_are_closed_decisions
FAILED tests/test_control_plane_documentation_contract.py::test_resource_contract_matches_skill_metadata_and_forbids_nested_global_acquire
FAILED tests/test_control_plane_documentation_contract.py::test_root_exact_demo_scope_slice_is_documented_without_overclaiming
FAILED tests/test_control_plane_documentation_contract.py::test_scheme_1_documents_canonical_transcript_cutover_and_observer_boundary
FAILED tests/test_control_plane_documentation_contract.py::test_scheme_4_claims_whole_turn_only_for_cut_over_paths
FAILED tests/test_desktop_chat_abort_cancel_event.py::test_chat_abort_keeps_legacy_empty_generation_compatible
FAILED tests/test_desktop_chat_abort_cancel_event.py::test_chat_abort_rejects_stale_or_missing_generation_without_touching_owner
FAILED tests/test_desktop_chat_abort_cancel_event.py::test_chat_abort_returns_404_when_session_unknown
FAILED tests/test_desktop_chat_abort_cancel_event.py::test_chat_abort_routes_control_turn_through_opaque_turn_id
FAILED tests/test_desktop_chat_abort_cancel_event.py::test_chat_abort_sets_envelope_cancel_event_before_cancelling_task
FAILED tests/test_desktop_chat_immediate_abort.py::test_abort_after_first_sse_frame_still_terminates_body_iterator
FAILED tests/test_desktop_skill_log_bridge.py::test_detached_skill_log_observer_drops_buffered_and_future_lines
FAILED tests/test_desktop_skill_log_bridge.py::test_single_skill_log_line_is_bounded_before_buffering
FAILED tests/test_desktop_skill_log_bridge.py::test_skill_log_batches_are_individually_bounded_and_report_drops
FAILED tests/test_notebook_files.py::TestCreateEmptyNotebook::test_creates_parent_directory_if_missing
FAILED tests/test_notebook_files.py::TestCreateEmptyNotebook::test_creates_valid_empty_notebook_file
FAILED tests/test_notebook_files.py::TestCreateEmptyNotebook::test_refuses_to_overwrite_existing
FAILED tests/test_notebook_files.py::TestCreateEmptyNotebook::test_rejects_path_escape
FAILED tests/test_notebook_files.py::TestDeleteNotebook::test_missing_file_raises_file_not_found
FAILED tests/test_notebook_files.py::TestDeleteNotebook::test_rejects_path_escape
FAILED tests/test_notebook_files.py::TestDeleteNotebook::test_removes_existing_file
FAILED tests/test_notebook_files.py::TestListIpynbFiles::test_ignores_directories_with_ipynb_suffix
FAILED tests/test_notebook_files.py::TestListIpynbFiles::test_returns_empty_for_file_path_instead_of_dir
FAILED tests/test_notebook_files.py::TestListIpynbFiles::test_returns_empty_for_missing_directory
FAILED tests/test_notebook_files.py::TestListIpynbFiles::test_returns_sorted_ipynb_names
FAILED tests/test_notebook_files.py::TestListWorkspaceNotebooks::test_reports_lower_bound_total_when_hard_cap_truncates_walk
FAILED tests/test_notebook_files.py::TestNotebookWorkspaceCrudRouter::test_open_endpoint_returns_notebook
FAILED tests/test_notebook_files.py::TestParseIpynbBytes::test_drops_raw_cells
FAILED tests/test_notebook_files.py::TestParseIpynbBytes::test_each_cell_includes_empty_outputs_list
FAILED tests/test_notebook_files.py::TestParseIpynbBytes::test_handles_utf8_with_bom
FAILED tests/test_notebook_files.py::TestParseIpynbBytes::test_raises_on_json_that_is_not_a_notebook
FAILED tests/test_notebook_files.py::TestParseIpynbBytes::test_raises_on_non_json_bytes
FAILED tests/test_notebook_files.py::TestParseIpynbBytes::test_returns_code_and_markdown_cells
FAILED tests/test_notebook_files.py::TestResolveIpynbPath::test_rejects_absolute_path
FAILED tests/test_notebook_files.py::TestResolveIpynbPath::test_rejects_non_ipynb_extension
FAILED tests/test_notebook_files.py::TestResolveIpynbPath::test_rejects_parent_directory_escape
FAILED tests/test_notebook_files.py::TestResolveIpynbPath::test_resolves_simple_filename
FAILED tests/test_notebook_files.py::TestResolveWorkspaceNotebookTarget::test_rejects_untrusted_absolute_path_without_workspace
FAILED tests/test_notebook_files.py::TestSaveNotebook::test_creates_file_if_missing
FAILED tests/test_notebook_files.py::TestSaveNotebook::test_rejects_invalid_cell_type
FAILED tests/test_notebook_files.py::TestSaveNotebook::test_rejects_path_escape
FAILED tests/test_notebook_files.py::TestSaveNotebook::test_round_trip_code_and_markdown_cells
FAILED tests/test_notebook_files.py::TestWorkspaceScopeEnforcement::test_resolve_workspace_and_target_fails_closed_without_trust
FAILED tests/test_notebook_files.py::TestWorkspaceScopeEnforcement::test_validate_workspace_fails_closed_when_no_trusted_roots_configured
FAILED tests/test_notebook_var_inspector.py::TestBuildAdataSlotScript::test_allows_empty_key_for_obs
FAILED tests/test_notebook_var_inspector.py::TestBuildAdataSlotScript::test_key_with_quotes_is_safely_escaped
FAILED tests/test_notebook_var_inspector.py::TestBuildAdataSlotScript::test_rejects_non_identifier_var_name
FAILED tests/test_notebook_var_inspector.py::TestBuildAdataSlotScript::test_rejects_unsupported_slot
FAILED tests/test_notebook_var_inspector.py::TestBuildAdataSlotScript::test_supports_obs_slot_with_key
FAILED tests/test_notebook_var_inspector.py::TestBuildAdataSlotScript::test_supports_obsm_slot
FAILED tests/test_notebook_var_inspector.py::TestBuildVarDetailScript::test_allows_dotted_paths
FAILED tests/test_notebook_var_inspector.py::TestBuildVarDetailScript::test_embeds_row_and_col_limits
FAILED tests/test_notebook_var_inspector.py::TestBuildVarDetailScript::test_embeds_variable_name_as_literal
FAILED tests/test_notebook_var_inspector.py::TestBuildVarDetailScript::test_rejects_names_with_quotes_or_backslashes
FAILED tests/test_notebook_var_inspector.py::TestBuildVarDetailScript::test_rejects_non_identifier_variable
FAILED tests/test_notebook_var_inspector.py::TestBuildVarDetailScript::test_uses_shared_payload_delimiters
FAILED tests/test_notebook_var_inspector.py::TestParseVarDetailPayload::test_parses_anndata_payload
FAILED tests/test_notebook_var_inspector.py::TestParseVarDetailPayload::test_parses_dataframe_payload
FAILED tests/test_notebook_var_inspector.py::TestParseVarDetailPayload::test_parses_scalar_payload
FAILED tests/test_notebook_var_inspector.py::TestParseVarDetailPayload::test_propagates_error_payload
FAILED tests/test_notebook_var_inspector.py::TestParseVarDetailPayload::test_returns_missing_for_empty_stdout
FAILED tests/test_notebook_var_inspector.py::TestParseVarDetailPayload::test_returns_missing_on_corrupt_json
FAILED tests/test_notebook_var_inspector.py::TestParseVarDetailPayload::test_returns_missing_when_delimiters_absent
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_adata_slot_dotted_var_name_roundtrip
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_adata_slot_obs_roundtrip
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_adata_slot_obsm_preview_respects_row_and_col_limits
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_adata_slot_obsm_roundtrip
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_adata_slot_whole_obs_respects_max_rows_and_cols
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_var_detail_dataframe_roundtrip
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_var_detail_missing_variable
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_var_detail_scalar_roundtrip
FAILED tests/test_notebook_var_inspector.py::TestScriptExecutionSafety::test_var_detail_series_roundtrip
FAILED tests/test_sc_ambient_removal.py::test_cellbender_without_input_requires_expected_cells
FAILED tests/test_sc_ambient_removal.py::test_simple_uses_adata_raw_when_no_counts_layer
FAILED tests/test_sc_ambient_removal.py::test_simple_uses_counts_layer_when_x_is_not_count_like
FAILED tests/test_scrna_method_contracts.py::test_builtin_communication_marks_non_statistical_significance
FAILED tests/test_scrna_method_contracts.py::test_de_runtime_dependency_validation_uses_expected_r_stacks
FAILED tests/test_scrna_method_contracts.py::test_doubletfinder_fallback_records_requested_and_executed_method
FAILED tests/test_scrna_method_contracts.py::test_scanvi_fallback_records_requested_and_executed_method
FAILED tests/test_skill_runner_contract.py::test_anndata_validator_resolves_relative_pythonpath_from_skill_cwd
FAILED tests/test_skill_runner_contract.py::test_anndata_validator_strips_all_backend_roots_and_preserves_runtime_paths
FAILED tests/test_skill_runner_contract.py::test_arun_skill_accepts_one_internal_frozen_snapshot_without_recapture
FAILED tests/test_skill_runner_contract.py::test_async_cancellation_records_one_frozen_cancelled_event_then_reraises
FAILED tests/test_skill_runner_contract.py::test_async_driver_exception_records_the_pre_spawn_execution_identity
FAILED tests/test_skill_runner_contract.py::test_async_explicit_skill_uses_the_same_precondition_gate
FAILED tests/test_skill_runner_contract.py::test_async_prepare_cancellation_waits_for_preparation_thread
FAILED tests/test_skill_runner_contract.py::test_async_skill_applies_only_governed_resource_environment
FAILED tests/test_skill_runner_contract.py::test_async_zero_exit_uses_the_same_output_contract_gate
FAILED tests/test_skill_runner_contract.py::test_bound_sync_run_rejects_source_drift_before_output_or_runtime_resolution
FAILED tests/test_skill_runner_contract.py::test_canonical_prepare_can_disable_adaptive_provisioning
FAILED tests/test_skill_runner_contract.py::test_claim_alias_anndata_never_records_earned_demo_success
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_allows_external_h5ad_without_omicsclaw_modality_tag
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_preserves_existing_directory_inputs
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_preserves_matching_non_h5ad_inputs_until_they_are_inspectable
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_a_missing_non_h5ad_path[missing.csv]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_a_missing_non_h5ad_path[missing.vcf]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_a_session_without_a_usable_local_input[session_payload0]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_a_session_without_a_usable_local_input[session_payload1]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_a_session_without_a_usable_local_input[session_payload2]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_directory_for_a_file_only_skill
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_file_for_a_directory_only_skill
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_freeform_for_a_file_only_skill[10.1038/s41586-024-00000-0]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_freeform_for_a_file_only_skill[https://example.org/paper]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_rejects_freeform_for_a_file_only_skill[plain raw text]
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_returns_a_stable_result_for_an_invalid_session
FAILED tests/test_skill_runner_contract.py::test_explicit_gate_still_rejects_an_observed_modality_conflict
FAILED tests/test_skill_runner_contract.py::test_explicit_runner_rejects_missing_input_before_creating_output
FAILED tests/test_skill_runner_contract.py::test_explicit_skill_gate_allows_a_verified_local_input
FAILED tests/test_skill_runner_contract.py::test_explicit_skill_gate_does_not_reclassify_demo_or_free_form_inputs
FAILED tests/test_skill_runner_contract.py::test_explicit_skill_output_requires_authoritative_project_metadata[hardlink]
FAILED tests/test_skill_runner_contract.py::test_explicit_skill_output_requires_authoritative_project_metadata[missing-project-id]
FAILED tests/test_skill_runner_contract.py::test_explicit_skill_output_requires_authoritative_project_metadata[symlink]
FAILED tests/test_skill_runner_contract.py::test_explicit_skill_rejects_uninspectable_local_input_before_execution
FAILED tests/test_skill_runner_contract.py::test_missing_declared_runtime_interpreter_is_actionable_dependency_failure[async]
FAILED tests/test_skill_runner_contract.py::test_missing_declared_runtime_interpreter_is_actionable_dependency_failure[sync]
FAILED tests/test_skill_runner_contract.py::test_output_contract_validator_exception_fails_closed_with_typed_error
FAILED tests/test_skill_runner_contract.py::test_output_finalizer_exception_is_one_typed_framework_failure[async]
FAILED tests/test_skill_runner_contract.py::test_output_finalizer_exception_is_one_typed_framework_failure[sync]
FAILED tests/test_skill_runner_contract.py::test_prepare_non_python_runtime_skips_adaptive_python_probe[bash-bash]
FAILED tests/test_skill_runner_contract.py::test_prepare_non_python_runtime_skips_adaptive_python_probe[r-Rscript]
FAILED tests/test_skill_runner_contract.py::test_prepare_skill_run_defaults_to_sys_executable_without_override
FAILED tests/test_skill_runner_contract.py::test_prepare_skill_run_does_not_add_an_empty_pythonpath_element
FAILED tests/test_skill_runner_contract.py::test_prepare_skill_run_honours_omicsclaw_run_python
FAILED tests/test_skill_runner_contract.py::test_prepare_skill_run_isolates_user_site_by_default
FAILED tests/test_skill_runner_contract.py::test_prepare_skill_run_respects_explicit_pythonnousersite_optout
FAILED tests/test_skill_runner_contract.py::test_project_completed_commit_is_terminal_provenance_boundary[async]
FAILED tests/test_skill_runner_contract.py::test_project_completed_commit_is_terminal_provenance_boundary[sync]
FAILED tests/test_skill_runner_contract.py::test_resource_environment_precedes_adaptive_runtime_resolution
FAILED tests/test_skill_runner_contract.py::test_root_omicsclaw_reexports_shared_run_skill
FAILED tests/test_skill_runner_contract.py::test_run_ledger_keeps_pre_spawn_manifest_and_execution_source_identity
FAILED tests/test_skill_runner_contract.py::test_run_skill_callback_exception_does_not_break_run
FAILED tests/test_skill_runner_contract.py::test_run_skill_cancel_event_kills_long_running_subprocess
FAILED tests/test_skill_runner_contract.py::test_run_skill_cancellation_with_partial_result_json_is_not_reported_as_success
FAILED tests/test_skill_runner_contract.py::test_run_skill_returns_skill_run_result_natively
FAILED tests/test_skill_runner_contract.py::test_run_skill_streams_stdout_and_stderr_lines_via_callbacks
FAILED tests/test_skill_runner_contract.py::test_runner_uses_one_registry_snapshot_across_selection_and_preflight
FAILED tests/test_skill_runner_contract.py::test_shared_runner_binds_selected_runtime_and_frozen_hashes_before_spawn
FAILED tests/test_skill_runner_contract.py::test_shared_runner_blocks_deprecated_skill_before_output_or_process
FAILED tests/test_skill_runner_contract.py::test_shared_runner_claims_empty_output_once
FAILED tests/test_skill_runner_contract.py::test_shared_runner_environment_id_comes_from_selected_runtime_and_env
FAILED tests/test_skill_runner_contract.py::test_shared_runner_environment_id_distinguishes_selected_executable
FAILED tests/test_skill_runner_contract.py::test_shared_runner_environment_id_uses_selected_runtime_dependency_versions
FAILED tests/test_skill_runner_contract.py::test_shared_runner_fails_closed_when_runtime_claim_binding_fails[async]
FAILED tests/test_skill_runner_contract.py::test_shared_runner_fails_closed_when_runtime_claim_binding_fails[sync]
FAILED tests/test_skill_runner_contract.py::test_shared_runner_keeps_loaded_legacy_skill_without_manifest_compatible
FAILED tests/test_skill_runner_contract.py::test_shared_runner_rejects_manifest_changed_after_registry_load_before_output
FAILED tests/test_skill_runner_contract.py::test_shared_runner_rejects_stale_explicit_output_before_spawn[async]
FAILED tests/test_skill_runner_contract.py::test_shared_runner_rejects_stale_explicit_output_before_spawn[sync]
FAILED tests/test_skill_runner_contract.py::test_shared_runner_rejects_unsupported_unified_method_before_spawn[async]
FAILED tests/test_skill_runner_contract.py::test_shared_runner_rejects_unsupported_unified_method_before_spawn[sync]
FAILED tests/test_skill_runner_contract.py::test_shared_runner_runtime_probe_failure_does_not_spawn_skill
FAILED tests/test_skill_runner_contract.py::test_skill_runner_module_exposes_run_skill_contract
FAILED tests/test_skill_runner_contract.py::test_sync_driver_exception_records_the_pre_spawn_execution_identity
FAILED tests/test_skill_runner_contract.py::test_unknown_skill_identifier_is_not_copied_into_health_ledger
FAILED tests/test_skill_runner_contract.py::test_zero_exit_with_invalid_declared_output_is_a_contract_failure
```

## 评估后清理（2026-09-24，owner 授权）

处理 0062 独立评估遗留的次要项。按 owner 的要求，这一轮**不跑全量测试**。

| # | 问题 | 处理 | 证据 |
|---|---|---|---|
| C1 | `LocalExecutor.environment` 的 docstring 没说会剔除控制面凭据 | 只改 docstring：补一句"with the framework's control-plane credentials removed from both" | `tests/ensemble/test_local_executor_credentials.py` 通过（3 passed，含在下面的命令里） |
| C2 | `AGENTS.md` 的 Import convention 写"Skill code never imports `omicsclaw`"，没列例外 | 在后面补一句具名例外：4 个 consensus 薄壳和 `consensus-interpret/_llm.py`（由 0058 取代），框架侧的 `omicsclaw/autoagent/metrics_compute.py`（随 autoagent 删除）；并注明清单在 `tests/sdk/test_boundary.py` 里 | 文档改动，无测试 |
| C3 | `tests/launch/test_the_environment_is_read_in_known_places.py` 里 `tools/builtin/bash.py` 条目的理由夹着中文和计划编号 | 改成纯英文，去掉计划编号，风格与其它条目一致（长度仍大于 40，满足 `test_every_entry_carries_a_reason`） | `tests/launch` 全绿 |
| C4 | 删除未跟踪的 `omicsclaw/core/` 目录 | **没有执行**：前置条件不满足。盘上确实只剩 `__pycache__/`，没有任何 `.py`；但 `git ls-files omicsclaw/core` 不为空，仍列出 6 个文件（`__init__.py`、`dependency_manager.py`、`external_env.py`、`r_dependency_manager.py`、`r_script_runner.py`、`r_utils.py`）。原因是阶段一用 `mv`/`rm` 搬走了它们，而派发规则不许 `git add`，所以暂存区还保留着这些条目（见 §7 偏离 1）。等暂存或提交之后，前置条件自然成立，届时可以删掉这个缓存目录。B1 与 B2 的判定都不受这个目录影响 | `git ls-files omicsclaw/core` 输出 6 行；`find omicsclaw/core -type f` 只有 `.pyc` |
| C5 | `skills/_sdk/r_dependency_manager.py` 模块 docstring 的断行 | 把三行散文重排成均匀的段落，文字不变 | `tests/sdk` 全绿 |

**所跑测试**：与 0061 清理共用同一条命令（见 0061 交付记录"评估后清理"），结果 873 passed、6 skipped、11 deselected，覆盖 `tests/sdk`、`tests/launch` 和 `tests/ensemble/test_local_executor_credentials.py`。C1、C2、C3、C5 都只改文字，没有做变异。
