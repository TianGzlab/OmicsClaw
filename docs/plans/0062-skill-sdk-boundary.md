# 计划 0062 — skill 与框架的边界：`skills/_sdk/` 与零代码耦合

**状态**：定稿（第 2 版，2026-09-24）。第 1 版经独立审核（"有条件通过"，重要 5 条、次要 11 条）修订；Q1–Q14 已由 owner
2026-09-24 全部按推荐裁定（§0.3、§8），owner 选择不再复核、直接定稿。逐条处置见 §10。未写任何生产代码或测试；
实施由 owner 派发。

**前置**：阶段一无前置，**必须先于计划 0057 开工**合入。阶段二依赖阶段一合入，可与 0057 并行。
本计划取代 0061 第 3 版的 P0a（`omicsclaw/core/child_env.py` 不再新建）；0061 第 4 版需要的接口集中在 §3.9。
`omicsclaw/ensemble/` 是 0056 尚未提交的在途实现，本计划只允许对它做 §3.7 所列的一处最小改动，不改它的设计。

**给实现者的一条硬要求**：新代码的函数、类与模块 docstring 只写"是什么、做什么、参数与返回、会抛什么"，
以及会改变调用方式的行为说明（例如"失败时返回 `False`，不抛异常"）。计划编号、裁定历史、与旧代码的
对照、实测数字一律写进本计划、交付记录或**测试的 docstring**，不写进生产代码注释。仓库里旧文件的高密度
注释风格不构成反例。

测试解释器：`/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`（默认 `python` 没有 pytest）。
脚本 `--help` 探针用 `/opt/conda/envs/OmicsClaw/bin/python`（skill 的运行环境，Python 3.11）。

**开工第一步（审核重要意见 5）**：实施者在开工所在的同一个 commit 上，按附录 B 的命令重跑全量基线与附录 A 的全部扫描
与探针，把失败清单、扫描结果逐字写进交付记录；本计划里的数字（第 2 版以工作树 `0881aa7b` + 未提交改动为准）只作参考，
以开工时的复跑为验收依据。

---

## 0. 缘起、已定裁定与结论

### 0.1 缘起

skill 脚本深度 import 框架包 `omicsclaw.common` 与 `omicsclaw.core`。框架重构删掉 `omicsclaw.skill` 时，
`core/` 里三个模块 import 的 `omicsclaw.skill.execution.environment` 随之消失，10 个 single-cell 主脚本（含地基
`sc_preprocess.py`）连 `--help` 都跑不起来，banksy 的子环境回落也断了（F9–F11）。这不是一次偶然的漏改，而是结构
问题：skill 的机械依赖挂在框架包下面，框架每重构一次就可能断一次。本计划把 skill 需要的机械能力收进
`skills/_sdk/`，让 `skills/**` 与 `omicsclaw/**` 之间只剩文件契约。

### 0.2 已定裁定（owner，不得推翻）

| # | 裁定 | 本计划落点 |
|---|---|---|
| D1 | 根因是 skill 深度 import `omicsclaw.common`/`omicsclaw.core`，框架重构即断。**不新建 `omicsclaw/core/child_env.py`**；0061 P0a 由本计划阶段一取代 | §2 F9–F11；§4 阶段一 |
| D2 | 新建 `skills/_sdk/`（`_` 开头不是 skill），只收跨 skill 的机械能力：result.json/报告写出、checksum、R 调用器（连同 `omicsclaw/r_scripts/`）、**合并后的单一依赖检查**（今天四份）、外部 conda env 调用。各域 `_lib` 保留，只能 import `_sdk` | §3.1–§3.5 |
| D3 | skill 与框架**零代码耦合**：`skills/**` 非测试代码不 import `omicsclaw`；框架不 import `skills/_sdk`。只靠文件契约（`SKILL.md`、`tuning.yaml`、`_sdk` 里的 result.json schema）对接，用契约测试钉住双方一致 | §3.6、§3.8；用例 15–20 |
| D4 | 凭据剔除从 skill 侧彻底移除，改由框架启动边界负责：`omicsclaw/tools/builtin/bash.py` 本机路径与 `omicsclaw/ensemble/execution.py` 的 `LocalExecutor`。名单由框架维护 | §3.7；用例 10–12 |
| D5 | 一份计划两阶段：阶段一（先于 0057）搬 `core/`、删 skill 侧剔除、修 10 个 sc 脚本与 banksy、边界剔除、处理测试；阶段二（可与 0057 并行）复制 `common` 子集、机械改写 import、守卫测试、统一 `sys.path` 引导 | §4 |
| D6 | 机读契约不新增文件：依赖 = `SKILL.md` 的 `## Dependencies` 包名行；参数与输出 = `tuning.yaml`；result.json 结构 = `_sdk` 里的 schema | §3.6、§3.9 |
| D7 | 0061 出第 4 版（删 P0a；registry 改从 `_sdk` 用 AST 读取；P3 环境记录并入冻结清单）；本计划给出合并后 registry 的位置与字段格式。未来 skill self-improvement（排 0060 后）禁止改 `_sdk` 与共享 `_lib`，所以 `_sdk` 要有稳定、小而清楚的公开面 | §3.4、§3.9、§3.10 |
| D8 | docstring 约定见上；测试解释器见上；已知无关的既有失败：`tests/tools/test_workspace.py`、`tests/test_control_plane_documentation_contract.py` | 全文 |

### 0.3 已裁定（owner 2026-09-24 裁定，Q1–Q12 全部按第 1 版推荐；Q4、Q8、Q9 同时满足审核条件）

| # | 问题 | 裁定 | 审核条件如何满足 |
|---|---|---|---|
| Q1 | `result.py` 的写入/读取安全语义 | 约 60 行的 `write_owned_text`：保留符号链接/越界/原子写；丢弃硬链接数、认领标记与 Windows reparse 判定（§3.3） | — |
| Q2 | `write_replot_hint` | 原样移到 `skills/singlecell/_lib/viz/r/replot_hint.py`，不改产物 | — |
| Q3 | result.json schema 的载体 | `_sdk/result.py` 里可 `literal_eval` 的 `RESULT_SCHEMA`；**`optional` 只作说明、不参与校验**（§3.3） | — |
| Q4 | registry 合并规则 | 键 = PyPI 名、`kind` 字段、`pip` 类统一 `pip install …`、`mzmine`→`pymzml`、`alt_env` 取代 lambda | 保留按 `module` 反查（`scvi`/`tangram`/`paste`/`STAGATE_pyG` 等）；回落集合钉为冻结空表；`singler` 两包用 `also` 字段；写明 `kind="r"` 的 `is_available` 语义（§3.4；Q13、Q14 为此新提） |
| Q5 | 守卫 B3 对 `skills/**/tests/` | 整体排除；B1 仍覆盖 tests 不碰 `core` | — |
| Q6 | `_sdk` 测试位置 | `tests/sdk/` | — |
| Q7 | 剔除名单范围 | 只含 `OMICSCLAW_REMOTE_AUTH_TOKEN`；provider key/bot token 另开议题 | — |
| Q8 | 名单与函数放哪里 | `omicsclaw/tools/builtin/bash.py` | 函数改名 `without_control_credentials`，不与 `omicsclaw/mcp/stdio.py`:92 的 `child_environment` 同名；名字按大小写不敏感匹配以保持旧语义（§3.7） |
| Q9 | `sys.path` 引导 | 每个脚本同一块、以 `skills/_sdk/__init__.py` 为锚 | 用 `next(..., None)`，找不到锚点不插入、交给 `PYTHONPATH`；本机/ensemble/沙箱三种情形逐一论证并各配用例（§3.11） |
| Q10 | 阶段一搬 `core/dependency_manager.py` 的名字 | 直接叫 `skills/_sdk/deps.py` | — |
| Q11 | 框架 `common/` 的删减 | 只删 `write_replot_hint` | — |
| Q12 | 删 `tests/test_adaptive_env_phase3.py` | 移交 0061 第 4 版 P0b | — |

### 0.4 结论先行

```
skills/_sdk/                 新包（有 __init__.py），只依赖标准库与科学栈，不 import omicsclaw、不 import skills.<domain>
  __init__.py  （只定义 REPO_ROOT）
  checksums.py  report.py  result.py  runtime_env.py  user_guidance.py     ← 阶段二从 common 复制最小子集
  deps.py  r_script_runner.py  r_utils.py  r_dependency_manager.py  external_env.py   ← 阶段一由 core/ 搬来
  r_scripts/*.R                                                              ← 阶段一由 omicsclaw/r_scripts 搬来
skills/<domain>/_lib/        保留；只 import 本域 _lib 与 skills._sdk
omicsclaw/                   不 import skills.*；凭据剔除在 bash 本机路径与 LocalExecutor
tests/sdk/                   _sdk 自身的测试、边界守卫、契约测试（测试可以同时 import 两侧）
```

阶段一改动面：约 26 个 skill 文件的 import 与 R 脚本路径、5 个模块搬家、3 处框架代码、5 个测试文件。
阶段二改动面：约 95 个文件的 import 机械改写、四份依赖检查合并（约 40 个 import 点）、94 个主脚本加统一引导块、模板。

---

## 1. 目标

| # | 目标 | 验收方式 |
|---|---|---|
| G1 | 10 个 single-cell 主脚本与 banksy 回落恢复 | 94 个主脚本 `--help` 90 成功（余 4 个 consensus 归 0058）；banksy 缺包缺环境时抛 `EnvNotFoundError` 而非 `ModuleNotFoundError` |
| G2 | `omicsclaw/core/` 与 `omicsclaw/r_scripts/` 不再有代码 | 守卫测试（按"没有 `.py`/`.R`/`__init__.py`"判定） |
| G3 | 凭据剔除只在框架启动边界做一次 | 边界测试 + skill 侧源码扫描无凭据名 |
| G4 | `skills/**` 非测试代码不 import `omicsclaw`（具名已知项除外）；`omicsclaw/**` 不 import `skills.*`（具名已知项除外） | 守卫测试（静态 + 子进程行为探针），已知项集合**恰好相等** |
| G5 | `_sdk` 有冻结的、只含实际被用到名字的公开面 | 公开面测试 |
| G6 | result.json 结构、用户指引前缀、免责声明三处契约由测试钉住 | 契约测试 |
| G7 | 依赖检查只剩一份，registry 可被 0061 用 `ast.literal_eval` 读取，现有调用名零回落 | registry 测试 |
| G8 | 94 个主脚本的 `sys.path` 引导一致，本机/ensemble/沙箱三种情形都可用 | 引导测试 |

---

## 2. 现状（亲自核实；行号以 2026-09-24 工作树为准，实施时按符号名定位）

复跑脚本全文在附录 A（审核重要意见 5：不再引用会话临时目录）。行号引用的 `omicsclaw/ensemble/`、
`omicsclaw/tools/builtin/bash.py`、`omicsclaw/launch/_surfaces.py` 有未提交改动，以符号名为准。

### A. skill 侧对框架的 import（AST 扫描，只读）

扫描 `skills/**/*.py`（排除 `__pycache__`），收集 `import omicsclaw…` 与 `from omicsclaw… import …`（含函数体内的惰性
import）。共 216 条、111 个文件，全部被 git 跟踪；其中 6 个文件在 `skills/**/tests/` 下。

| # | 事实 | 出处 |
|---|---|---|
| F1 | **非测试文件 105 个**：95 个 import `omicsclaw.common`，23 个 import `omicsclaw.core`，另有 5 个 import 其他框架包（F4）。按符号计文件数：`common.report.write_result_json` 88、`generate_report_header` 86、`generate_report_footer` 86、`load_result_json` 29、`write_replot_hint` 22、`write_repro_requirements` 7、`mark_result_status` 1；`common.checksums.sha256_file` 46；`common.runtime_env.ensure_runtime_cache_dirs` 13；`common.user_guidance.emit_user_guidance`/`emit_user_guidance_payload` 1（`skills/singlecell/_lib/preflight.py`:10）；`core.r_script_runner.RScriptRunner` 21、`RScriptError` 3、`RScriptTimeoutError` 1；`core.dependency_manager.validate_r_environment` 18；`core.r_utils.read_r_result_csv` 4；`core.r_dependency_manager.check_r_tier`/`suggest_r_install` 3；`core.external_env.{EnvNotFoundError,is_env_available,run_anndata_op_in_env}` 1 | 附录 A `scan_imports.py skills` |
| F2 | import `omicsclaw.core` 的 23 个非测试文件：bulkrna 4（`bulkrna_batch_correction.py`:108-109、`bulkrna_coexpression.py`:401-402、`bulkrna_de.py`:88-89、`bulkrna_survival.py`:111-112，均为函数体内）；singlecell `_lib` 3（`preflight.py`:11、:1755；`pseudobulk.py`:240-241；**`viz/r/__init__.py`:12 模块顶层**，任何 import 它的模块都连带失败）；single-cell 主脚本 11（`sc_ambient.py`:50-51、`sc_integrate.py`:42-43、`sc_annotate.py`:60-61、`sc_cell_communication.py`:44-46、`sc_de.py`:51-52、`sc_differential_abundance.py`:379、`sc_doublet.py`:35-36、`sc_enrichment.py`:36-37、:616、:730、`sc_pathway_scoring.py`:28-29、`sc_preprocess.py`:32-33、`sc_pseudotime.py`:44-45）；spatial `_lib` 5（`cnv.py`:267-269、`communication.py`:581-583、`deconvolution.py`:473-475、:874-876、:971-973、`domains.py`:945、`genes.py`:374-376，均为函数体内）。测试 2 个：`sc-pathway-scoring/tests/test_sc_pathway_scoring.py`:13、`sc-preprocessing/tests/test_sc_preprocess.py`:13 | 同上 |
| F3 | **AST 的 import 节点扫描漏掉一处字符串 import**：`skills/spatial/_lib/dependency_manager.py`:97-107 的 `pybanksy` 条目用 `availability_check=lambda: … __import__("omicsclaw.core.external_env", fromlist=[...])`；`is_available`（:249-271）吞掉异常返回 `False`。扫描 skills 非测试代码里全部匹配 `^omicsclaw(\.\w+)+$` 的字符串常量，**只有这一处**（:104） | 附录 A `scan_strings.py` |
| F4 | 5 个非测试文件 import `common`/`core` 以外的框架包：4 个 consensus 薄壳 `sc_consensus_clustering.py`:23、`sc_consensus_integration.py`:25、`sc_consensus_pseudotime.py`:26、`consensus_domains.py`:23 模块顶层 `from omicsclaw.runtime.consensus.run import main`；`skills/spatial/consensus-interpret/_llm.py`:79 惰性 `from omicsclaw.providers.chat_completion import call_chat_completion`（`omicsclaw/providers` 已删除）。这 5 处是 0058 的范围，本计划作为**具名已知项** | 同上；0061 F43 |
| F5 | `skills/**/tests/` 下 6 个文件：3 个基准脚本在函数体内 import 已删除的 `omicsclaw.skill.runner`（`bulkrna-enrichment/tests/biomnibench_da12_2.py`:236、`sc-preprocessing/tests/omicbench_preprocessing.py`:114、`sc-pseudotime/tests/scagentbench_paga.py`:190；文件名不以 `test_` 开头，pytest 不收集）；`consensus-domains/tests/test_cli_smoke.py`:85 惰性 import `omicsclaw.runtime.consensus.operators.lca_r`；F2 的 2 个测试 | 同上 |
| F6 | **R 脚本以硬编码路径引用**：19 个文件共 **23 行** `<仓库根> / "omicsclaw" / "r_scripts"`，例如 `bulkrna_de.py`:93、`sc_preprocess.py`:349、`sc_pseudotime.py`:73（模块常量 `R_SCRIPTS_DIR`）、`sc_differential_abundance.py`:67（同名模块常量）、`skills/singlecell/_lib/pseudobulk.py`:245、`skills/spatial/_lib/deconvolution.py`:514/:897/:999。**`sc_enrichment.py` 同时有两个目录**：:125 `R_SCRIPTS_DIR = Path(__file__).resolve().parent / "rscripts"`（本 skill 的 R 脚本，用于 :425、:491）与 :126 `R_SCRIPTS_PROJECT_DIR = _PROJECT_ROOT / "omicsclaw" / "r_scripts"`（:618）。`core/r_script_runner.py`:25 的默认目录 `_SCRIPTS_DIR` 也指向项目目录。28 个 `.R` 之间无 `source()` 互引 | `grep -rn '"omicsclaw" / "r_scripts"'` |
| F7 | **R 脚本今天不随 wheel 发布**：`pyproject.toml`:570 `omicsclaw = ["py.typed"]` 只带 `py.typed`；而 `skills` 的 package-data（:580-592）通配 `**/*.R`。搬进 `skills/_sdk/r_scripts/` 后顺带修好。`[tool.setuptools.packages.find]` 的 `include = ["skills", "skills.*"]` 会收 `skills._sdk`（需有 `__init__.py`） | `pyproject.toml` |
| F8 | 各域 `_lib` 之间**没有**跨域 import；主脚本也不 import 别域的 `_lib`。D2 的"`_lib` 只能 import `_sdk`"今天已成立（除 import `omicsclaw`） | grep |

### B. 断点与凭据剔除

| # | 事实 | 出处 |
|---|---|---|
| F9 | `core/external_env.py`:25、`core/dependency_manager.py`:8（:7 先 import `external_env`）、`core/r_script_runner.py`:20 都 `from omicsclaw.skill.execution.environment import scrub_internal_control_credentials`，该模块已删除。剔除调用点共 6 处：`external_env.py`:72、:116、:165、`dependency_manager.py`:168、`r_script_runner.py`:253、:323 | 各文件 |
| F10 | **批量 `--help` 探针**（`OmicsClaw` 环境，94 个主脚本，cwd 为临时目录，`-B` 且 `PYTHONDONTWRITEBYTECODE=1`，不写仓库）：**80 成功、14 失败**，全部 `ModuleNotFoundError: No module named 'omicsclaw.skill'`。10 个 single-cell 脚本经 `core/`：sc-ambient-removal、sc-batch-integration、sc-cell-annotation、sc-cell-communication、sc-de、sc-doublet-detection、sc-enrichment、sc-pathway-scoring、sc-preprocessing、sc-pseudotime；4 个 consensus 薄壳经 `omicsclaw/runtime/…`（0058）。与 0061 F11 一致 | 附录 A `probe_help.sh` |
| F11 | banksy 回落：`skills/spatial/_lib/domains.py` 的 `identify_domains_banksy`（:890）先在 :928 惰性 import `skills.spatial._lib._runners.banksy_runner`（它 import `banksy`），:939 捕获 `ImportError`；随后 :945-949 惰性 import `omicsclaw.core.external_env`，今天抛 `ModuleNotFoundError` 而不是 :951-957 设计中的 `EnvNotFoundError` 提示。（审核意见给出的 943–947 与工作树不符：:943 是注释，import 起于 :945，已逐行核对） | 同左 |
| F12 | 被删的 `environment.py` 定义三个凭据名：`OMICSCLAW_REMOTE_AUTH_TOKEN`、`OMICSCLAW_SKILL_EVOLUTION_TOKEN`、`OMICSCLAW_SKILL_EVOLUTION_TOKEN_FD`，**按 `str(name).upper()` 匹配**（大小写不敏感）。**只有第一个仍有生产者**：`omicsclaw/launch/_surfaces.py`:351 `DESKTOP_TOKEN_VARIABLE`、`omicsclaw/remote/auth.py`:30 `TOKEN_ENV`、`omicsclaw/entry/cli/_configure.py`:660-668（写 `.env`）。两个 `SKILL_EVOLUTION_*` 只出现在 `tests/test_autoagent_harness_workspace.py`:24-25（autoagent 不可 import） | `git show 33720785^:omicsclaw/skill/execution/environment.py`；grep |
| F13 | **`bash` 本机路径把 agent 的全部环境透传给子进程**：`omicsclaw/tools/builtin/bash.py` 的 `_start`（:844）调用 `asyncio.create_subprocess_exec("bash", "-c", …)`（:864-873）不带 `env=`。该文件今天不含 `os.environ` 字样 | 同左 |
| F14 | **`LocalExecutor` 已是白名单**：`omicsclaw/ensemble/execution.py`:34-50 `ENV_WHITELIST` 不含 `OMICSCLAW_REMOTE_AUTH_TOKEN`；`LocalExecutor.environment`（:116-118）= 白名单子集 ∪ 调用方 `extra`。`extra` 只来自 `runner.py` 的 `trial_environment`（:463-481）与评分探针（:403），都是固定键。所以今天 trial 拿不到这个 token；D4 要求的剔除在这里是**纵深防御** | 同左 |
| F15 | `SandboxExecutor` 与 `bash` 的沙箱路径不继承宿主环境：容器只带 `--env HOME=/tmp`（`omicsclaw/sandbox/container.py`:94-95），trial 变量由 `SandboxExecutor.command_line` 显式拼进命令行 | 同左 |
| F16 | 框架里其余会起子进程的地方：`mcp/stdio.py` 按固定名单继承（其函数名就叫 `child_environment`，:92）；`entry/cli/_shell.py`:210 的 `!<cmd>` 是用户自己敲的命令、继承全部环境；`ensemble/resources.py`、`_supervise.py`、`sandbox/*` 不跑 skill 代码 | grep `create_subprocess_exec`/`subprocess.run` |
| F17 | **环境读取清单测试**：`tests/launch/test_the_environment_is_read_in_known_places.py` 对 `REBUILT_PACKAGES`（含 `tools`、`common`）做源码扫描，任何含 `os.environ` 等拼写的文件必须列在 `ENVIRONMENT_READERS` 且带理由，清单须**恰好相等**；`os.environ[` 写入者只允许 `common/runtime_env.py`。给 `bash.py` 加剔除必须同时加一条清单项 | 同左 |

### C. 框架侧对 `core` 与 `skills` 的 import

| # | 事实 | 出处 |
|---|---|---|
| F18 | **`omicsclaw/core` 在框架内没有非 skill 用户**：扫描 `omicsclaw/**`、`tests/**`、根目录 `*.py`、`scripts/**`，`omicsclaw.core` 只被 `core/` 自身（`dependency_manager.py`:7、`r_dependency_manager.py`:187、:211）与 4 个测试文件 import：`tests/test_external_env.py`、`test_r_script_runner.py`、`test_r_script_runner_environment.py`、`test_r_dependency_manager.py`。`omicsclaw/surfaces/`（不可 import 的参考代码）、`autoagent/`、`runtime/`、`remote/` 都不 import `core`。字符串提及只在文档、`0_setup_env.sh`:555 注释、`tests/launch/…known_places.py`:21 docstring、`tests/test_autoagent_edit_surface.py`（旧路径字面量，autoagent 不可 import） | 附录 A `scan_imports.py framework` |
| F19 | **框架今天 import `skills.*` 两处**：`omicsclaw/common/report.py`:517 `write_replot_hint` 惰性 import `skills.singlecell._lib.viz.r.renderer_params`；`omicsclaw/autoagent/metrics_compute.py`:207、:223 import `skills.singlecell._lib.integration`（autoagent 不可 import，0056 §0.2 第 1 条定为 0057/0058 迁完后删除）。`tests/` 下另有 4 个文件 import `skills._lib`（测试，允许） | 同上 |
| F20 | **新栈里 result.json 的读者只有 ensemble**：`runner.py` 的 `_collect`（:616-618）只检查 `result.json` 存在；`_device`（:587-613）读 `envelope["summary"]["device"]`。ensemble 被 `tests/ensemble/test_ensemble_is_a_layer.py`:30-34 禁止 import `omicsclaw.common`，所以它用自己的 `read_json`。`common.report.validate_result_envelope`（:366）与 `load_result_json`（:29）的框架调用者只剩不可 import 的 `autoagent/`、`runtime/`、`surfaces/desktop/`，以及 `common/notebook_export.py`:18。runner 只记录 `script_sha256`（:353、:387），不记录脚本 import 的 `_lib`/`_sdk` | grep |
| F21 | `common/report.py` 依赖 `output_claim.py` 的 4 个函数（:13-18）；按 AST 求闭包得 16 个定义、381 行（全文件 675 行）。闭包的核心语义有二：①写入 `result.json` 时拒绝经符号链接/Windows reparse point 的祖先、拒绝越出输出根、拒绝替换非"单链接普通文件"、`mkstemp`+`fsync`+`os.replace` 原子写；②读取时同样拒绝别名、**拒绝硬链接数 ≠ 1**、拒绝 `.omicsclaw-run-claim.json` 认领标记。**认领标记在新栈里没有生产者**（只有 `autoagent/output_ownership.py` 与 `surfaces/desktop/server.py` 写它） | 附录 A `closure.py` |
| F22 | `user_guidance`：skill 只用两个发射函数；前缀 `USER_GUIDANCE:`/`USER_GUIDANCE_JSON:` 由框架侧 `extract_user_guidance_*` 解析（`tests/test_user_guidance.py`；`tests/test_sc_standardize_input.py`:143 断言 stderr 里的前缀）。新栈里没有生产代码读取它 | 同左 |
| F23 | `write_replot_hint` 的 22 个调用者**全部是 single-cell 主脚本**；它写进 `result.json` 的 `replot.command` 指向已不存在的 `python omicsclaw.py replot`（`CLAUDE.md` "Re-rendering plots — currently unavailable"） | `report.py`:485-549 |
| F37 | `common/report.py`:356 `_RESULT_STATUS_VALUES = {"ok","partial","failed"}` **不含 `scaffold`**；`validate_result_envelope` 接受 `scaffold`（:363、:397），而 `mark_result_status("scaffold")` 返回 `False`（:434-440）。`DISCLAIMER`（:22-26）是 `generate_report_footer` 的内容；skill 代码不直接 import 它 | 同左 |

### D. 四份依赖检查

| # | 事实 | 出处 |
|---|---|---|
| F24 | **`omicsclaw/core/dependency_manager.py`**（222 行）：`DOMAIN_TIERS`、`check_dependencies`、`get_installed_tiers`、`_check_r_available`（优先 `$CONDA_PREFIX/bin/Rscript`、`sys.prefix/bin/Rscript`，再 `Rscript`）、`validate_r_environment`（经 `RScriptRunner.get_missing_packages` 查 R 包）。**skill 只用 `validate_r_environment`**（18 个文件）；前三者全仓无调用者 | grep |
| F25 | **`skills/spatial/_lib/dependency_manager.py`**（379 行）：`DependencyInfo(module_name, install_cmd, description, availability_check=None)`，33 条；API `require(name, *, feature="")`、`get(name, *, warn_if_missing=False)`、`is_available(name)`；**`_get_info` 先查键、再按 `module_name` 反查、最后恒等回落**；另有一份只找 PATH 上 `Rscript` 的 `validate_r_environment`（:329-379），**无调用者**。`singler` 条目（:152-155）的 `install_cmd` 是 `pip install singler singlecellexperiment`——一条装两个包 | 同左 |
| F26 | **`skills/singlecell/_lib/dependency_manager.py`**（199 行）：同形 `DependencyInfo`（无 `availability_check`），33 条；`_get_info` 同样按 `module_name` 反查；多一个 `install_hint(name)`；`require` 的报错不带 `pip install -e ".[full]"` 那行；同样有一份**无调用者**的 `validate_r_environment` | 同左 |
| F27 | **metabolomics/proteomics 简化版**（各 44 行，除 registry 外逐字相同）：字段名 `import_name`；`require(package)` 未知名抛 `ValueError`；`check_available` 用 `__import__(import_name)`——对 `xcms`、`MetaboAnalystR` 这两个 **R 包**永远返回 `False`。**两份都无调用者**（只在各自 `_lib/__init__.py`:4 re-export） | 同左 |
| F28 | **合并冲突**（AST 读 4 个 `DEPENDENCY_REGISTRY`）：74 条、62 个不同键；spatial 与 singlecell 重叠 12 键，`module_name` 全部一致，**10 键 `install_cmd` 不同**（spatial 写 `pip install <名>`，singlecell 写 `pip install -e ".[singlecell-…]"`，只在源码检出的仓库根下有效）；metabolomics 的键 `mzmine` 实际装 `pymzml`，与 proteomics 的键 `pymzml` 同义（`module` 同为 `pymzml`，是全表唯一的 module 重复）；spatial 键 `spatialde` 的 `module_name` 是 `NaiveDE`，而 `## Dependencies` 写 `SpatialDE`；唯一的非字面量是 `pybanksy` 的 `availability_check` lambda（F3） | 附录 A `registry.py` |
| F29 | **调用名**（AST：`require`/`is_available`/`install_hint`/`get_dependency` 调用、`dm.*`/`sc_dep_manager.*` 属性调用、以及从依赖模块 import 的 `get` 的字符串首参）共 32 个不同名字。按"键 → PEP 503 规范化键 → `module` 反查"解析后**全部命中、零回落**；其中 4 个只能靠 `module` 反查命中：`scvi`（×5，→`scvi-tools`）、`tangram`（×2，→`tangram-sc`）、`paste`（→`paste-bio`）；`STAGATE_pyG` 靠规范化命中 `STAGATE-pyG`，`spatialde` 靠规范化命中。若去掉反查，`scvi`/`tangram`/`paste` 会回落成 `pip install scvi`/`tangram`/`paste`——都是错的包（PyPI 上的 `paste` 是 web 框架） | 附录 A `dep_names.py` |
| F30′ | 调用面：spatial `_lib` 里 `require` 约 20 处、`get` 2 处，主脚本 `is_available` 2 处、`require` 1 处；singlecell 经 `dm.require` 8 处、`sc_dep_manager.is_available` 6 处、`.install_hint` 3 处、`.require` 1 处；`sc_pseudotime.py`:55 直接 import `install_hint, is_available`；`preflight.py`:25 与 :622 `from skills.singlecell._lib import dependency_manager as sc_dep_manager`；R 侧 `check_r_tier`/`suggest_r_install` 3 个文件。测试里**没有**对这些 API 的 monkeypatch，也没有对报错文本的断言；`tests/test_scrna_method_contracts.py`:124 与 `test_sc_preprocess.py`:107 以 `setattr(module, "validate_r_environment", …)` 打补丁——**只要主脚本命名空间里的符号名不变就不受影响** | grep |

### E. `sys.path` 引导、模板与加载器

| # | 事实 | 出处 |
|---|---|---|
| F30 | 94 个 skill 目录、94 个主脚本（顶层非 `_` 开头的 `.py`）。引导方式按互斥类计：**79** 个 `_PROJECT_ROOT = Path(__file__).resolve().parent…parent`（4 或 5 层手数 `.parent`）+ `sys.path.insert`，其中 3 个（spatial-domains、spatial-preprocess、spatial-microenvironment-subset）在 demo 函数里另插 `_PROJECT_ROOT / "scripts"`；**7** 个 bulkrna 脚本 `sys.path.insert(0, str(Path(__file__).resolve().parents[3]))`；**6** 个沿父目录找 `omicsclaw/__init__.py`（4 个 consensus 薄壳、sc-integrate-cluster、**bulkrna-cosinor-rhythm**）；**1** 个 `literature_parse.py` 用 `.parent.parent.parent`；**1** 个 `consensus_interpret.py` 不引导（只 import 同目录 `_*.py`）。79+7+6+1+1 = 94（第 1 版的 77/5 分类有误，已更正）。79 个定义 `_PROJECT_ROOT` 的脚本里，31 个在引导之外还用它（demo 数据、R 脚本路径） | 附录 A `bootstrap_classes.py` |
| F31 | ensemble 在 trial 与评分命令上设 `PYTHONPATH=<repo_root>`（`runner.py`:403、:468），trial 的 cwd 是 trial 目录（:519、:571），脚本以 `tuning.script_path` 的**绝对路径**运行（:508；`space.py`:360-363 要求它位于 `tuning.yaml` 所在目录内）。沙箱执行时 `omicsclaw/` 与 `skills/` 以只读、同路径挂进容器（0056 §3.10） | 同左 |
| F32 | 新 skill 的脚手架 `templates/skill/replace_me.py`:24-38 沿父目录找 `omicsclaw/__init__.py` 并 `from omicsclaw.common.report import …`；self-improvement 与人工新建 skill 都会从它复制 | 同左 |
| F33 | skill 加载器只跳过 `.` 开头的目录与 `__pycache__`/`node_modules`（`omicsclaw/skills/loader.py`:30-31）。"`_` 开头不是 skill"是约定而非机制：`_sdk/` 里若出现 `SKILL.md` 会被索引 | 同左 |
| F38 | `CONTRIBUTING.md` 引用旧位置：:108 `from omicsclaw.common.report import (`、:172 "Use `omicsclaw.common.report.write_result_json`"、:351 "`dependency_manager.py`) with an `install_cmd`" | 同左 |

### F. 测试现状

| # | 事实 | 出处 |
|---|---|---|
| F34 | 收集错误：`tests/test_external_env.py`、`tests/test_r_script_runner.py`、`tests/test_r_script_runner_environment.py`、`skills/singlecell/scrna/sc-pathway-scoring/tests/test_sc_pathway_scoring.py`（都经 `core/` → `omicsclaw.skill`）；`tests/test_r_dependency_manager.py` 通过（`r_dependency_manager` 顶层不 import 断链）；**`tests/test_scrna_method_contracts.py` 共 4 个用例、4 个全部失败**（都在 `core/external_env.py`:25；第 1 版写的"46 passed"是同批其他文件的数字，已更正）；`tests/test_sc_ambient_removal.py` 3 failed（子进程跑 `sc_ambient.py`，经 `core/dependency_manager.py`:7）。`sc-preprocessing/tests/test_sc_preprocess.py` 单独跑报 `No module named 'tests.test_sc_preprocess'`——与另一个 skill 的 `tests` 包同名冲突的既有问题 | 本次运行 |
| F35 | 断言"skill 侧清理生效"的三个用例：`tests/test_external_env.py`:79 `test_cross_environment_children_scrub_backend_control_credentials`、:118 `test_dependency_r_probe_scrubs_backend_control_credentials`；`tests/test_r_script_runner_environment.py`:12 `test_r_runner_scrubs_base_override_and_probe_environments`。三者都以三个凭据名为输入 | 同左 |
| F36 | 全量基线（`rapids_singlecell`，`tests/` 全目录，默认标记过滤，附录 B 命令）：**221 failed, 6044 passed, 42 skipped, 46 errors**，300 s。绝大多数失败属于不可 import 的旧代码的测试；**归因于 `core/` 断链的只有 10 项**：F34 的 3 个收集错误、`test_scrna_method_contracts.py` 4、`test_sc_ambient_removal.py` 3。开工时以同一 commit 的复跑为准（见文首"开工第一步"） | 本次运行 |

---

## 3. 设计

### 3.1 包形状与依赖方向

```
skills/_sdk/__init__.py      只定义 REPO_ROOT = Path(__file__).resolve().parents[2]；不 import 任何子模块（import skills._sdk 不得拉起 numpy/pandas）
skills/_sdk/<module>.py      只 import 标准库、第三方科学栈、skills._sdk.<module>
skills/<domain>/_lib/*.py    只 import 标准库、第三方、本域 _lib、skills._sdk
skills/<domain>/<skill>/*.py 同上，另可 import 同目录模块
omicsclaw/**                 不 import skills.*（具名已知项除外）
tests/**                     可以 import 两侧——契约测试就在这里
```

`_sdk` 的代码必须在 Python 3.11 上可运行（`OmicsClaw` 环境是 3.11，测试环境是 3.13）；新代码不用 3.12+ 语法。

### 3.2 阶段一：`core/` 与 R 脚本整体搬家

| 源 | 目的 | 处理 |
|---|---|---|
| `omicsclaw/core/external_env.py` | `skills/_sdk/external_env.py` | `git mv`；删 :25 import 与 3 处 `env=scrub(...)`（改为不传 `env=`，即继承当前进程环境） |
| `omicsclaw/core/dependency_manager.py` | `skills/_sdk/deps.py` | `git mv` 直接用最终模块名（Q10）；删 :8 import 与 :168 的剔除；:7 改为 `from skills._sdk.external_env import is_env_available`；:208 的相对 import `.r_script_runner` 保留 |
| `omicsclaw/core/r_script_runner.py` | `skills/_sdk/r_script_runner.py` | `git mv`；删 :20 import；:253 删掉合并后的剔除；:323 改为 `env = dict(os.environ)`；`_SCRIPTS_DIR` 改名为公开常量 `R_SCRIPTS_DIR = Path(__file__).resolve().parent / "r_scripts"` |
| `omicsclaw/core/r_utils.py`、`r_dependency_manager.py` | `skills/_sdk/` 同名 | `git mv`；`r_dependency_manager` 的惰性 import 改指 `skills._sdk.r_script_runner` |
| `omicsclaw/r_scripts/`（28 个 `.R`） | `skills/_sdk/r_scripts/` | `git mv`，内容不变 |
| `omicsclaw/core/__init__.py` | 删除 | 目录里只可能剩未跟踪的 `__pycache__/` |

skill 侧改写（阶段一）：F2 的 23 个文件、F3 的字符串 import（改为 `"skills._sdk.external_env"`，阶段二随 lambda 一起消失）、F5 的
2 个 skill 测试，`omicsclaw.core.X` → `skills._sdk.X`（`dependency_manager` → `deps`），**只改模块路径、不改符号名、不改 import
的位置**（惰性的仍惰性，F30′ 的 monkeypatch 继续有效）。

**R 脚本路径（审核重要意见 2）**：F6 的 23 行不做"整名替换"，一律改为**带别名的 import** 再替换表达式本身：

```python
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
...
scripts_dir = _SDK_R_SCRIPTS_DIR                 # 原 _PROJECT_ROOT / "omicsclaw" / "r_scripts"
R_SCRIPTS_PROJECT_DIR = _SDK_R_SCRIPTS_DIR       # sc_enrichment.py:126；:125 的本地 R_SCRIPTS_DIR（rscripts/）不动
R_SCRIPTS_DIR = _SDK_R_SCRIPTS_DIR               # sc_pseudotime.py:73、sc_differential_abundance.py:67：原变量名保留，只换右值
```

规则：只替换 `<任意根> / "omicsclaw" / "r_scripts"` 这个表达式；左边的变量名一律保留；`_sdk` 的常量只以
`_SDK_R_SCRIPTS_DIR` 这个别名进入 skill 模块命名空间，永远不会覆盖 skill 自己的同名变量。用例 7b 分别钉住
`sc_enrichment` 的两个目录。

阶段一**不删**`deps.py` 里无调用者的 `DOMAIN_TIERS`/`check_dependencies`/`get_installed_tiers`：阶段一只做保持行为的
搬家，删减放进阶段二的合并。

### 3.3 阶段二：`common` 的最小子集复制进 `_sdk`

框架保留自己的 `omicsclaw/common/`，唯一改动是删掉 `report.py` 的 `write_replot_hint`（F19 的框架→skills import，Q11）。

| `_sdk` 模块 | 内容 | 来源与取舍 |
|---|---|---|
| `checksums.py` | `sha256_file` | 逐字复制 |
| `report.py` | `DISCLAIMER`、`generate_report_header`、`generate_report_footer`、`write_repro_requirements` | 逐字复制；`generate_report_header` 用 `_sdk.checksums` |
| `result.py` | `RESULT_SCHEMA`、`RESULT_STATUS_VALUES`、`validate_result_envelope`、`write_result_json`、`load_result_json`、`mark_result_status`、`write_owned_text` | 见下 |
| `runtime_env.py` | `ensure_runtime_cache_dirs` | 复制它与两个私有辅助（`common/runtime_env.py`:14-72）；`.env` 解析不复制 |
| `user_guidance.py` | `USER_GUIDANCE_PREFIX`、`USER_GUIDANCE_JSON_PREFIX`、`emit_user_guidance`、`emit_user_guidance_payload` | 只复制发射侧与前缀；解析侧留在框架 |

**`result.py` 的最小子集（Q1 已裁定）**：约 60 行的 `write_owned_text(path, *, output_root, text)`，保留 F21 语义①的全部（祖先与目标
不得是符号链接、不得越出输出根、`mkstemp`+`fsync`+`os.replace` 原子写、失败不留临时文件），读取侧保留"符号链接与越界返回
`None`"；**丢弃**硬链接数检查、认领标记与 Windows reparse point 的专门判定（改用 `Path.is_symlink()`）。行为差异写进交付记录，
由用例 19 钉住保留部分。

**状态值（审核次要意见）**：`RESULT_STATUS_VALUES = ("ok", "partial", "failed")`，**不含 `scaffold`**，因此
`mark_result_status(out, "scaffold")` 返回 `False`、不改文件；`validate_result_envelope` 接受 `RESULT_SCHEMA["status_values"]`
（含 `scaffold`）。两者都与框架现状一致（F37），用例 19 分别钉住。

**`RESULT_SCHEMA`（Q3 已裁定）**：`result.py` 模块级纯字面量，可被 `ast.literal_eval` 读取：

```python
RESULT_SCHEMA = {
    "required": {"skill": "str", "version": "str", "completed_at": "str",
                 "input_checksum": "str", "summary": "dict", "data": "dict"},
    "non_empty": ["skill", "version", "completed_at"],
    "status_values": ["ok", "partial", "failed", "scaffold"],
    "optional": {"lineage": "list", "status": "str", "replot": "dict"},
}
```

**`optional` 只作说明、不参与校验**：`validate_result_envelope` 只检查 `required` 的存在与类型、`non_empty` 的非空、以及
`status` 出现时的取值（`status_values`），不检查 `lineage`/`replot` 的类型、不拒绝未列出的键——与 `common/report.py`:366-400
逐条相同，否则用例 20(b) 的两边判定会不一致。

**`write_replot_hint`（Q2 已裁定）**：原样移到 `skills/singlecell/_lib/viz/r/replot_hint.py`（改用 `_sdk.result.write_owned_text`），
22 个调用点改 import；它写出的过时命令不在本计划修（§7）。

### 3.4 阶段二：四份依赖检查合并为 `skills/_sdk/deps.py`

一个文件、一张表、一组函数。四个域的 `_lib/dependency_manager.py` 删除（不留 re-export 壳，SPEC "Do not add
backward-compatibility shims"），约 40 个 import 点改写：`from .dependency_manager import require` →
`from skills._sdk.deps import require`；`from . import dependency_manager as dm` 与 `from skills.singlecell._lib import
dependency_manager as sc_dep_manager`（`preflight.py`:25、:622，`sc_cluster.py`:44 等）→ `from skills._sdk import deps as <原别名>`
（保留别名，调用点一行不动）；metabolomics/proteomics `_lib/__init__.py` 的 re-export 删除（无调用者，F27）。

**registry 格式（0061 的接口，§3.9）**：

```python
DEPENDENCIES: dict[str, dict] = {
    "scvi-tools": {"module": "scvi", "kind": "pip", "install": "pip install scvi-tools",
                   "description": "Single-cell variational inference"},
    "singler": {"module": "singler", "kind": "pip", "also": ["singlecellexperiment"],
                "install": "pip install singler singlecellexperiment", "description": "..."},
    "STAGATE-pyG": {"module": "STAGATE_pyG", "kind": "git",
                    "install": "pip install git+https://github.com/RucDongLab/STAGATE_pyG.git", "description": "..."},
    "pybanksy": {"module": "banksy", "kind": "git", "alt_env": "omicsclaw_banksy",
                 "install": "pip install git+https://github.com/prabhakarlab/Banksy_py.git", "description": "..."},
    "xcms": {"module": "xcms", "kind": "r", "install": "Rscript -e 'BiocManager::install(\"xcms\")'", "description": "..."},
    ...
}
```

- 键 = PyPI 项目名，拼写与 `## Dependencies` 一致（`SpatialDE` 而非 `spatialde`；`mzmine` 并入 `pymzml`）；PEP 503 规范化后键唯一。
- 值是**纯字面量** dict。必有字段：`module`（`pip`/`git` 类是探测用的 import 名，可以是代表模块，如 `SpatialDE→NaiveDE`；`r` 类是
  R 包名）、`kind ∈ {"pip","git","r"}`、`install`、`description`。可选字段：`also`（`pip` 类要一起装的其他 PyPI 包名列表）、
  `alt_env`（conda 子环境名，存在即视为可用——替代 `pybanksy` 的 lambda）。
- **`install` 的规则**：`pip` 类恒等于 `"pip install " + " ".join([键, *also])`（由测试钉住；`singler` 是今天唯一有 `also` 的条目，
  Q13）；`git`/`r` 类是完整命令。10 个 `install_cmd` 冲突（F28）一律按此规则生成；`pip install -e ".[extra]"` 形式不再出现。
- **名字解析 `_resolve(name)`（审核重要意见 1）**，顺序固定：①键精确匹配 → ②PEP 503 规范化后匹配键 → ③按 `module` 精确反查
  （`scvi`→`scvi-tools`、`tangram`→`tangram-sc`、`paste`→`paste-bio`；`module` 在表内唯一，F28 的 `pymzml` 重复随合并消失）→
  ④回落 `{"module": name, "kind": "pip", "install": f"pip install {name}"}`。①②③之间不得有歧义：任何名字不能同时是某键的规范化形式
  与另一条目的 `module`（用例 22 断言）。**今天全仓 32 个调用名的回落集合为空（F29），用例 22 把它钉成冻结空表**：新增调用名若只能
  靠回落解析，测试即红，必须补表或把名字写进测试里的具名例外表（附理由）。回落只服务未来 self-improvement 新增的后端（D7），
  不能掩盖现有调用。
- **API**：`require(name, *, feature="") -> module`（缺失抛 `ImportError`，信息含 `install` 与 `feature`）、`get(name, *,
  warn_if_missing=False)`、`is_available(name) -> bool`、`install_hint(name) -> str`、`validate_r_environment(required_r_packages=None)`
  （阶段一搬来的 conda 感知版）。
- **`kind` 与 `is_available` 的语义（审核重要意见 1；Q14）**：
  - `pip`/`git`：`importlib.util.find_spec(module) is not None`（带缓存，同旧实现）；有 `alt_env` 时，`find_spec` 为空再查
    `external_env.is_env_available(alt_env)`，该调用不缓存、异常视为 `False`。
  - `r`：`module` 是 R 包名；`is_available` = R 可用（`_check_r_available`）且 `RScriptRunner(verbose=False).get_missing_packages([module])`
    为空；Rscript 不存在、超时或任何异常都返回 `False`，不抛。**不**做 Python import（F27 的旧实现对 R 包永远返回 `False`，是缺陷）。
  - `require`/`get` 对 `r` 类抛 `TypeError("<name> is an R package; use validate_r_environment")`——R 包没有可返回的 Python 模块。今天无调用者。
- 删除：`DOMAIN_TIERS`、`check_dependencies`、`get_installed_tiers`（F24 无调用者），两份无调用者的 `validate_r_environment`
  （F25、F26），`check_available`（F27）。

R 侧的 `r_dependency_manager.py`（R 包分层表与安装建议）保留为独立模块，不并入 `deps.py`：它的表是 R 包分层，与 Python
registry 不是一类数据。

### 3.5 外部 conda env 调用

`external_env.py` 搬家后行为不变（`mamba`→`conda` 回退、`EnvNotFoundError`、三种调用形态），只删剔除。banksy 回落
（F11）因此恢复设计中的 `EnvNotFoundError` 提示。BANKSY 的 Tier 5 与 `environments/banksy.yml`（0061 F14、Q12）不在本计划。

### 3.6 契约：框架与 skill 靠什么对接

| 契约 | 权威位置 | skill 侧 | 框架侧读者 | 钉住它的测试 |
|---|---|---|---|---|
| skill 元数据与依赖 | `SKILL.md` frontmatter 四键与 `## Dependencies` 包名行 | 作者维护 | `omicsclaw/skills/`（索引、`use_skill`）；0061 | 既有 `tests/skills/`；0061 格式契约 |
| 参数与输出 | `tuning.yaml` | 作者维护 | `omicsclaw/ensemble/space.py` | 既有 `tests/ensemble/test_tuning_matches_argparse.py` |
| result.json 结构 | `skills/_sdk/result.py` 的 `RESULT_SCHEMA` | `_sdk.result.write_result_json` | ensemble `runner._collect`/`_device`；框架 `common.report.validate_result_envelope` | 用例 20(a)–(d) |
| 用户指引行 | `skills/_sdk/user_guidance.py` 的两个前缀 | `_sdk.user_guidance.emit_*` | 框架 `common.user_guidance.extract_*` | 用例 20(e) |
| 免责声明 | `skills/_sdk/report.py` 的 `DISCLAIMER` | `generate_report_footer` | 框架 `common.report.DISCLAIMER`（`CLAUDE.md` 安全规则 2 的原文） | 用例 20(f) |
| 依赖名桥 | `skills/_sdk/deps.py` 的 `DEPENDENCIES` 字面量 | `_sdk.deps` | 0061（AST 读取） | 用例 22 |

契约测试放在 `tests/sdk/`：测试是唯一允许同时 import 两侧的地方，这正是它们的用途。契约测试可以读 `_sdk` 模块的非公开属性
（如 `DISCLAIMER`、两个前缀）——公开面约束只针对 `skills/**` 与 `templates/**` 的非测试代码（§3.10）。

### 3.7 凭据剔除移到框架启动边界（D4）

- **名单与函数**放在 `omicsclaw/tools/builtin/bash.py`（Q8）；函数名避开 `omicsclaw/mcp/stdio.py`:92 的 `child_environment`：

  ```python
  CONTROL_CREDENTIAL_NAMES: frozenset[str] = frozenset({"OMICSCLAW_REMOTE_AUTH_TOKEN"})

  def without_control_credentials(source: Mapping[str, str] | None = None) -> dict[str, str]:
      """A copy of *source* (default: this process's environment) without the names in CONTROL_CREDENTIAL_NAMES,
      compared case-insensitively."""
  ```

  **大小写**：旧 `is_internal_control_credential_name` 按 `str(name).upper()` 匹配（F12）。新函数保持大小写不敏感：名单存大写，比较
  `name.upper() in CONTROL_CREDENTIAL_NAMES`。POSIX 环境变量名区分大小写，`omicsclaw_remote_auth_token` 今天没有读者，但保持旧语义
  是零成本的保守选择；用例 10 含小写变体。两个 `SKILL_EVOLUTION_*` 已无生产者（F12），不进名单（Q7）。
- **`bash` 本机路径**：`_start` 的 `create_subprocess_exec` 加 `env=without_control_credentials()`，在每次起 shell 时从进程环境现算，
  除被剔除的名字外与今天的继承完全相同。沙箱路径不动（F15）。
- **`tests/launch/test_the_environment_is_read_in_known_places.py`** 的 `ENVIRONMENT_READERS` 加一条 `"tools/builtin/bash.py"`，理由写
  "起子 shell 时复制进程环境并剔除框架控制面凭据；剔除必须在读到环境的地方做"（F17）。
- **对 0056 的最小改动**（`omicsclaw/ensemble/execution.py`，一处）：`LocalExecutor.environment` 改为
  `return without_control_credentials({**whitelisted_environment(self._base_env), **extra})`，import 从已有的
  `from omicsclaw.tools.builtin.bash import …` 行里多取一个名字。不改白名单、不改 `SandboxExecutor`、不改 runner。依 F14，这是纵深防御。
  `tests/ensemble/test_ensemble_is_a_layer.py` 允许 ensemble import `omicsclaw.tools`，分层不受影响。
- skill 侧：`skills/**` 里不再出现任何凭据名或剔除函数（用例 5）。直接在用户自己的 shell 里跑 skill 脚本时，子进程继承用户环境——
  那是用户的环境，不是框架签发给子进程的（§6 R3）。

### 3.8 守卫：零代码耦合的机械判定

`tests/sdk/test_boundary.py`。静态部分全部基于 AST（不 import 被扫描的模块），"import"包括：`Import`、`ImportFrom`（相对 import 按
包路径展开）、以及 `__import__(...)`/`importlib.import_module(...)`/`importlib.util.find_spec(...)` 的字符串字面量首参（F3）。另有
字符串常量扫描与子进程行为探针（B9、B10）。

**"模块在盘上存在"的判定**（B2 用）：`a.b.c` 存在 ⇔ `a/b/c.py` 存在，或 `a/b/c/` 是目录且（有 `__init__.py`，或它是 `skills`、
`skills/<domain>` 这两层已知的命名空间目录）。`from P import n`：P 须存在；若 P 是目录包，`n` 须是盘上的子模块，或 `P/__init__.py`
顶层绑定的名字（赋值、`def`/`class`、import 别名）。只认 `.py` 文件与带 `__init__.py` 的目录，未跟踪的 `__pycache__/` 或空目录不能
让已删除的模块被判为存在。

| 规则 | 范围 | 已知项（集合须**恰好相等**，新增或消失都要改表） | 阶段 |
|---|---|---|---|
| B1 不得 import `omicsclaw.core`；`omicsclaw/core/` 与 `omicsclaw/r_scripts/` 下没有 `.py`、`.R`、`__init__.py` | `skills/**` 全部（含 tests）、`omicsclaw/**`、`tests/**`、`templates/**` | 无 | 一 |
| B2 import 的 `omicsclaw.*` **与 `skills.*`** 模块（及 `from P import n` 的 `n`）必须在盘上存在 | `skills/**` 非测试、`templates/skill/**` 非测试 | `{"skills/spatial/consensus-interpret/_llm.py": "omicsclaw.providers"}`。阶段二删掉四份 `dependency_manager.py` 后，任何漏改的 `from skills.singlecell._lib import dependency_manager`（如 `preflight.py`:622）由这条抓住 | 一（`skills.*` 部分同样从阶段一起生效） |
| B3 不得 import `omicsclaw` 或其子模块 | `skills/**` 非测试、`templates/skill/**` 非测试 | 4 个 consensus 薄壳（`omicsclaw.runtime.consensus.run`）+ `_llm.py`（`omicsclaw.providers`），全部归 0058 | 二 |
| B4 不得 import `skills` 或其子模块 | `omicsclaw/**` | `{"omicsclaw/autoagent/metrics_compute.py"}`（0057/0058 删 autoagent 时消失） | 二（阶段一先以 `{common/report.py, autoagent/metrics_compute.py}` 上线） |
| B5 `_sdk` 只 import 标准库、第三方与 `skills._sdk.*` | `skills/_sdk/**` | 无 | 一 |
| B6 域 `_lib` 只 import 本域 `_lib` 与 `skills._sdk.*`（外加第三方） | `skills/<domain>/_lib/**` | 无 | 二 |
| B7 `skills/_sdk/` 下没有 `SKILL.md`（F33） | — | 无 | 一 |
| B8 `skills/**` 源码不含凭据名与 `scrub_internal_control_credentials` | `skills/**` 全部 | 无 | 一 |
| B9 字符串常量不得完全匹配 `^omicsclaw(\.\w+)+$` | `skills/**` 非测试 | 空。F3 是今天唯一的一处，阶段一第 3 步改写后消失；它是本用例的"先红"样本 | 一 |
| B10 行为探针：子进程里先 `sys.modules["omicsclaw"] = None`，再逐个 `importlib.import_module` 全部 `skills.<domain>._lib.*` 与 `skills._sdk.*` 模块 | 同左 | 失败只在报错链里出现 `omicsclaw` 时计为违例；因第三方包缺失（`ModuleNotFoundError` 且名字不是 `omicsclaw`）的模块记为"跳过"并在测试输出里列名，不算通过也不算违例 | 二（阶段一先对 `skills._sdk.*` 生效） |

**`skills/**/tests/` 的取舍（Q5 已裁定）**：B3 整体排除 `skills/**/tests/`；B1 仍覆盖 tests 不碰 `core`。

### 3.9 给 0061 第 4 版的接口

| 0061 需要 | 本计划给出 |
|---|---|
| registry 的位置 | `skills/_sdk/deps.py`，模块级赋值 `DEPENDENCIES`（带注解的 `AnnAssign`），**阶段二**合入后存在；阶段二之前 0061 若要读，读 4 个旧 `DEPENDENCY_REGISTRY`（0061 F22 的现状） |
| 读取方式 | `ast.parse` 找到 `DEPENDENCIES` 赋值，`ast.literal_eval(node.value)`；不 import `skills.*`。用例 22 钉住"字面量可求值且等于 import 结果" |
| 字段 | 键 = PyPI 名（`## Dependencies` 拼写），按 PEP 503 规范化匹配；值必有 `{"module","kind","install","description"}`，可选 `"also"`（PyPI 名列表）、`"alt_env"`；`kind ∈ {"pip","git","r"}`；`pip` 类 `install == "pip install " + " ".join([键, *also])`。0061 的"类别"直接取 `kind`；安装白名单里的包名取 `[键, *also]`，不从 `install` 字符串里解析 |
| 名字解析 | 与 §3.4 `_resolve` 同序：键 → 规范化键 → `module` 反查 → 回落；0061 的探针遇到 `scvi`/`tangram`/`paste` 这类 import 名时必须走反查 |
| 规模 | 合并后 61 个键（62 − `mzmine` 并入 `pymzml`）；`git` 类恰为 {STAGATE-pyG, pybanksy, STalign}，`r` 类恰为 {xcms, metaboanalyst}；有 `also` 的恰为 {singler} |
| 冻结清单（0061 P3 / 0059） | runner 今天只记录主脚本的 `script_sha256`（F20）。一次试验真正执行的 skill 代码还包括它 import 的 `skills/_sdk/**` 与本域 `skills/<domain>/_lib/**`；**0059 的冻结清单应覆盖这两棵树**：以冻结清单（`bench/freezes/<name>.yaml`）里的 git tag 标识，要求冻结运行在与 tag 一致的干净检出上；tag 覆盖整棵树，已包含 `skills/_sdk/**` 与本域 `skills/<domain>/_lib/**`，否则改动 `_sdk`/`_lib` 不会反映在试验记录里 |
| P0a 的去向 | `child_env.py` 不建；0061 P0a 的"import 不存在模块"守卫由本计划 B2/B3 吸收；`tests/test_core_modules_import.py` 由用例 8 取代；`tests/test_adaptive_env_phase3.py` 的删除移交 0061 第 4 版 P0b（Q12） |
| `use_skill` 注记与探针的解释器 | 不变；本计划不碰 `omicsclaw/skills/` |

### 3.10 `_sdk` 的公开面（self-improvement 的只读 API）

公开面 = 各模块 `__all__`，由 `tests/sdk/test_public_surface.py` 的 `PUBLIC_SURFACE` 冻结；**只冻结 `skills/**` 与 `templates/**` 非测试
代码实际 import 的名字**，外加两项机读契约（`RESULT_SCHEMA`、`DEPENDENCIES`，由 AST 读取而非 import）。模块里其余不带 `_` 前缀的
函数照常存在、可被测试使用，但不在 `__all__` 里，skill 代码也不得 import 它们。增删公开名要改测试表——这是审查闸门。

| 模块 | 公开名（阶段二完成后） | 今天的实际使用者 |
|---|---|---|
| `skills._sdk` | `REPO_ROOT` | 引导块（§3.11） |
| `skills._sdk.checksums` | `sha256_file` | 46 个文件 |
| `skills._sdk.report` | `generate_report_header`、`generate_report_footer`、`write_repro_requirements` | 86/86/7 个文件（`DISCLAIMER` 无 skill 使用者，只受契约测试约束） |
| `skills._sdk.result` | `RESULT_SCHEMA`（契约）、`write_result_json`、`load_result_json`、`mark_result_status`、`write_owned_text` | 88/29/1(+模板)/`replot_hint.py` |
| `skills._sdk.runtime_env` | `ensure_runtime_cache_dirs` | 13 个文件 |
| `skills._sdk.user_guidance` | `emit_user_guidance`、`emit_user_guidance_payload` | `preflight.py` |
| `skills._sdk.deps` | `DEPENDENCIES`（契约）、`require`、`get`、`is_available`、`install_hint`、`validate_r_environment` | F30′ |
| `skills._sdk.r_script_runner` | `R_SCRIPTS_DIR`、`RScriptRunner`、`RScriptError`、`RScriptTimeoutError` | F1、F6（`RScriptResult` 无使用者，不公开） |
| `skills._sdk.r_utils` | `read_r_result_csv` | 4 个 spatial `_lib`（其余 6 个函数只有测试在用） |
| `skills._sdk.r_dependency_manager` | `check_r_tier`、`suggest_r_install` | 3 个文件 |
| `skills._sdk.external_env` | `EnvNotFoundError`、`is_env_available`、`run_anndata_op_in_env` | `domains.py`、`deps.py` |
| `skills/_sdk/r_scripts/*.R` | 28 个脚本的文件名 | skill 以文件名调用 |

`validate_result_envelope`、`RESULT_STATUS_VALUES`、`DISCLAIMER`、两个指引前缀不在公开面：它们今天没有 skill 使用者，由契约测试直接
读取。阶段一只冻结搬来的 5 个模块（`deps` 先只有 `validate_r_environment`）与 `REPO_ROOT` 以外的部分；阶段二补齐。

### 3.11 `sys.path` 引导统一（阶段二，Q9 已裁定）

每个 import `skills.*` 的主脚本（及 `templates/skill/replace_me.py`）在第一条 `skills.` import 之前放同一块代码：

```python
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
from skills._sdk import REPO_ROOT as _PROJECT_ROOT  # noqa: E402   ← 仅当脚本在引导之外还用 _PROJECT_ROOT（31 个）
```

- 以 `skills/_sdk/__init__.py` 为锚：不依赖目录深度（F30 的手数 `.parent` 与 `parents[3]` 都消失），不依赖 `omicsclaw` 在不在。
- **找不到锚点时不插入**，交给调用方的 `PYTHONPATH`（审核重要意见 3）。此时 `skills._sdk` 从 `PYTHONPATH` 指向的仓库加载，
  `_PROJECT_ROOT` 取 `skills._sdk.REPO_ROOT`——即提供 `_sdk` 的那个仓库，而不是脚本所在目录的祖先。这让 demo 数据路径等在脚本
  被放到仓库外时仍指向真实仓库。
- `REPO_ROOT` 定义在 `skills/_sdk/__init__.py`，只用 `pathlib`，不 import 子模块。
- 不做成可 import 的辅助函数：引导本身就是为了让 `skills` 可 import，鸡生蛋。
- 不 import `skills.*` 的脚本（`consensus_interpret.py`）不加；4 个 consensus 薄壳与 `bulkrna-cosinor-rhythm`、`sc-integrate-cluster`
  按同一块改写锚点（F30 的 6 个）。
- ensemble 的 `PYTHONPATH=<repo_root>`（F31）不动；它现在是"锚点缺失"情形的正式后备。
- demo 路径里另插 `_PROJECT_ROOT / "scripts"` 的 3 处保持原样（§7）。

**三种运行情形的论证**（各配一个用例，23a–23c）：

| 情形 | 脚本路径与 cwd | 锚点 | 结果 |
|---|---|---|---|
| 本机：agent 经 `bash` 或用户直接 `python skills/<d>/<s>/x.py` | 仓库内的相对或绝对路径；cwd 任意 | `Path(__file__).resolve()` 是仓库内绝对路径，父目录链经过仓库根，锚点命中 | 仓库根插到 `sys.path[0]`，`skills._sdk` 从本仓库加载 |
| ensemble：`LocalExecutor`/`SandboxExecutor` 跑 trial | cwd = trial 目录（`runner.py`:519）；argv 是 `tuning.script_path` 的绝对路径（:508）；`PYTHONPATH=<repo_root>`（:468） | 脚本在 `tuning.yaml` 所在 skill 目录内（`space.py`:360-363），锚点命中 | 与本机相同；`PYTHONPATH` 冗余。0059 若把被测 skill 目录换成仓库外的副本、或 self-improvement 的候选副本放在仓库外：锚点缺失 → 不插入 → 经 `PYTHONPATH` 取仓库里的 `_sdk`（候选副本不能带自己的 `_sdk`，正合 D7） |
| 沙箱：`bash` 或 `SandboxExecutor` 在容器里 | `omicsclaw/` 与 `skills/` 以只读、同路径挂入（0056 §3.10），cwd 为工作区或 trial 目录 | 同路径挂载使 `<repo>/skills/_sdk/__init__.py` 在容器里存在；`resolve()` 在只读挂载上照常工作 | 与本机相同；不写任何文件（`-B`/`PYTHONDONTWRITEBYTECODE` 由调用方设置，引导块本身不写盘） |

---

## 4. 分阶段

### 阶段一（先于 0057，无前置）

0. 开工第一步：在同一 commit 上跑附录 B 基线与附录 A 全部扫描/探针，结果写进交付记录。
1. 新建 `skills/_sdk/__init__.py`（定义 `REPO_ROOT`）；按 §3.2 `git mv` 5 个模块与 `r_scripts/`，删 `omicsclaw/core/__init__.py`。
2. 删 skill 侧剔除（F9 的 6 处调用 + 3 处 import）。
3. 改写 F2 的 23 个文件、F3 的字符串 import、F5 的 2 个 skill 测试；按 §3.2 的别名规则替换 F6 的 23 行 R 脚本路径。
4. 框架：`bash.py` 加 `CONTROL_CREDENTIAL_NAMES`/`without_control_credentials` 并用于 `_start`；环境读取清单加一条；
   `LocalExecutor.environment` 一处改动（§3.7）。
5. 测试：`git mv` `tests/test_external_env.py`、`test_r_script_runner.py`、`test_r_script_runner_environment.py`、
   `test_r_dependency_manager.py` → `tests/sdk/`（Q6），改 import；F35 的三个用例改写为用例 6、7（断言 `_sdk` **不**剔除、原样继承），
   剔除的断言移到用例 10、11；新增用例 1–5、7b、8、9、10–13、B9 与 B10 的 `_sdk` 部分。
6. 文档：`AGENTS.md` 项目结构树（删 `core/` 行，`skills/` 下加 `_sdk/`）与 "Import convention"（加一句 `_sdk` 规则）；
   `docs/FRAMEWORK-REBUILD.md`:1896 "Kept and importable" 改为记录 `core/` 已搬进 `skills/_sdk/`；
   `docs/core-features/agent-skills.md` §9.3 表格；`0_setup_env.sh`:555 注释；`README.md` 里程碑一条；本计划交付记录。
   `README.md`:56 那句"`common/` and `core/` are not legacy"是历史里程碑叙述，保留原文，新里程碑里说明 `core/` 的去向。

**验收**：用例 1–14 全绿；94 个主脚本 `--help` **90 成功**（余 4 个 consensus，F10）；`tests/test_scrna_method_contracts.py` 4 个用例
全绿，`tests/test_sc_ambient_removal.py` 的 3 个失败转绿（若转为别的失败，如实记录原因）；`sc-pathway-scoring` 的 skill 测试由收集
错误转为可运行；全量失败集合 ⊆ 开工基线减去 F36 的 10 项。

### 阶段二（阶段一合入后；可与 0057 并行）

1. §3.3：复制 5 个 `common` 子集模块；`write_replot_hint` 移到 singlecell `_lib`，删框架 `report.py` 里的它。
2. §3.4：合并依赖检查，删四份 `_lib/dependency_manager.py`，改约 40 个 import 点（含 `preflight.py`:25、:622 这类
   `from skills.<domain>._lib import dependency_manager` 形式）。
3. 机械改写约 95 个文件的 `omicsclaw.common.*` import → `skills._sdk.*`（改写脚本不入库；改写后以 AST 复核"每个文件 import 的符号
   名集合不变"）。
4. §3.11：94 个主脚本里 import `skills.*` 的全部换统一引导块；模板改 import `_sdk` 与引导块。
5. 守卫与契约测试全量上线（用例 15–24、B6、B10 全量）；B4 的已知项收缩为 autoagent 一处。
6. 文档（**必改**，SPEC "Repository Maintenance"）：`CONTRIBUTING.md`:108、:172 改为 `skills._sdk.report`/`skills._sdk.result`，:351 改为
   `skills/_sdk/deps.py` 的 `DEPENDENCIES` 与字段格式；`AGENTS.md` "Dependency source of truth"（registry 位置、字段格式）、结构树
   （`common/` 注释改为"框架自用；skill 不再 import"）、"Import convention"；`templates/skill/README.md` 与 `CLAUDE.md` 中对
   `omicsclaw.common` 的提及（实施时 grep 核对，逐处列入交付记录）；README 里程碑。

**验收**：用例 15–24 全绿；`--help` 仍 90/94；阶段一全部用例仍绿；全量失败集合 ⊆ 开工基线减去 F36 的 10 项。

与 0057 的冲突面：0057 主要改 `omicsclaw/ensemble/` 与新增 `tuning.yaml`；阶段二只在 `spatial_domains.py` 等脚本的 import 与引导
块上与它相交，按文件合并即可。

---

## 5. 测试计划

主命令（每阶段结束跑，保持绿）：

```
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly -p no:cacheprovider \
  tests/sdk tests/tools/test_bash_child_environment.py tests/ensemble tests/launch tests/skills \
  tests/test_scrna_method_contracts.py tests/test_sc_ambient_removal.py tests/test_user_guidance.py tests/test_sc_standardize_input.py
```

全量回归见附录 B。慢测试（`-m slow`）：`--help` 探针以 `OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python` 运行，
变量未设或解释器不存在则跳过并在报告中显示（该变量仅供测试，不是配置项，测试 docstring 写明）。

### 5.1 TDD 用例清单

**阶段一**

1. `tests/sdk/test_boundary.py::test_core_is_gone`（B1 的目录部分）：`omicsclaw/core/` 与 `omicsclaw/r_scripts/` 下**没有任何 `.py`、`.R`、`__init__.py`**（未跟踪的 `__pycache__/` 不影响判定）；`skills/_sdk/__init__.py` 存在；`skills/_sdk/r_scripts/` 恰有 28 个 `.R`。先红。
2. `::test_nothing_imports_omicsclaw_core`（B1）：含字符串 import、含 `skills/**/tests/`、`tests/**`、`templates/**`。先红（F2、F3）。
3. `::test_imported_modules_exist_on_disk`（B2，`omicsclaw.*` 与 `skills.*`）：违例集合恰等于 `{_llm.py}`。变异：在某 `_lib` 加 `from skills.singlecell._lib import no_such_module` → 红；`from skills._sdk import deps`（阶段一存在）→ 绿。
4. `::test_sdk_imports_nothing_above_it`（B5）与 `::test_no_skill_md_under_sdk`（B7）。
5. `::test_skill_code_carries_no_control_credentials`（B8）：`skills/**` 源码不含 `OMICSCLAW_REMOTE_AUTH_TOKEN`、`SKILL_EVOLUTION`、`scrub_internal_control_credentials`。
5b. `::test_no_omicsclaw_module_strings`（B9）：先红（F3 的 :104），阶段一第 3 步后绿。
6. `tests/sdk/test_external_env.py`（搬来）：原有用例照旧；`test_children_inherit_the_parent_environment` 取代 F35 的两例——设哨兵变量，假 `subprocess.run` 捕获到的 `env` 为 `None`（继承）或含哨兵；`deps._check_r_available` 同理。
7. `tests/sdk/test_r_script_runner_environment.py`（搬来）：`_build_r_env` 与 `run` 传给子进程的环境含哨兵变量、且未被过滤（取代 :12 的剔除断言）；`R_SCRIPTS_DIR` 指向 `skills/_sdk/r_scripts`。
7b. `tests/sdk/test_r_script_paths.py`（审核重要意见 2）：import `sc_enrichment` 模块后 `R_SCRIPTS_DIR == <sc-enrichment 目录>/"rscripts"` 且 `R_SCRIPTS_PROJECT_DIR == skills/_sdk/r_scripts`；`sc_pseudotime.R_SCRIPTS_DIR`、`sc_differential_abundance.R_SCRIPTS_DIR` 等于 `skills/_sdk/r_scripts`；AST 断言：`skills/**` 里凡从 `skills._sdk.r_script_runner` import `R_SCRIPTS_DIR` 的都带 `as _SDK_R_SCRIPTS_DIR` 别名；全仓不再出现 `"omicsclaw" / "r_scripts"`。
8. `tests/sdk/test_sdk_imports.py`：子进程 `import skills._sdk.{external_env,deps,r_script_runner,r_utils,r_dependency_manager}` 成功，`sys.modules` 里没有任何 `omicsclaw` 开头的模块；`import skills._sdk` 不拉起 `numpy`。B10 的 `_sdk` 部分（`sys.modules["omicsclaw"] = None` 后逐个 import）同文件。
9. `tests/sdk/test_banksy_fallback.py`：`monkeypatch.setitem(sys.modules, "banksy", None)`（使 :928 的进程内路径抛 `ImportError`）、`monkeypatch` `skills._sdk.external_env.is_env_available` 为返回 `False` → `identify_domains_banksy` 抛 `EnvNotFoundError`（先红：今天是 `ModuleNotFoundError`）；spatial `is_available("pybanksy")`（阶段二起为 `deps.is_available`）返回 `False` 且确实调用了 `is_env_available("omicsclaw_banksy")`。
10. `tests/tools/test_bash_child_environment.py`：`monkeypatch.setenv` 设 `OMICSCLAW_REMOTE_AUTH_TOKEN`、小写变体 `omicsclaw_remote_auth_token` 与哨兵变量，本机 `bash` 执行 `echo ${OMICSCLAW_REMOTE_AUTH_TOKEN-unset}:${omicsclaw_remote_auth_token-unset}:$SENTINEL` → `unset:unset:<哨兵值>`；`without_control_credentials` 对传入映射同样生效；`launch._surfaces.DESKTOP_TOKEN_VARIABLE.upper() ∈ CONTROL_CREDENTIAL_NAMES`；`bash.py` 里不存在名为 `child_environment` 的函数（避免与 `mcp/stdio.py` 混淆）。先红。
11. `tests/ensemble/test_local_executor_credentials.py`：`LocalExecutor(base_env={token, PATH…}).environment({token: "x", "A": "1"})` 不含 token、含 `A`；`ENV_WHITELIST` 与 `CONTROL_CREDENTIAL_NAMES` 按大写比较交集为空；真实 `run(["env"])` 的日志里没有 token。
12. `tests/launch/test_the_environment_is_read_in_known_places.py`：加 `tools/builtin/bash.py` 条目后通过；不加则红（F17）。
13. `tests/sdk/test_sc_scripts_help.py`（slow）：10 个 F10 的 single-cell 脚本 `--help` 退出 0。
14. 既有 `tests/test_scrna_method_contracts.py`（4 例）、`tests/test_sc_ambient_removal.py` 与 `sc-pathway-scoring` 的 skill 测试由红转绿（F34）。

**阶段二**

15. `test_boundary::test_skill_code_imports_no_omicsclaw`（B3）：违例恰等于 5 个已知项（F4）。
16. `::test_framework_imports_no_skills`（B4）：违例恰等于 `{autoagent/metrics_compute.py}`；阶段一以 `{common/report.py, autoagent/metrics_compute.py}` 上线，阶段二删 `write_replot_hint` 后必须改表。
17. `::test_domain_lib_imports_only_itself_and_sdk`（B6）；`::test_lib_modules_import_without_omicsclaw`（B10 全量：`skills.<domain>._lib.*` 逐个子进程 import，报错链含 `omicsclaw` 即违例，第三方缺失列为跳过）。
18. `tests/sdk/test_public_surface.py`：各模块 `__all__` == `PUBLIC_SURFACE`（§3.10）；**检查范围仅 `skills/**` 与 `templates/**` 的非测试代码**：其中所有 `from skills._sdk.X import n` 的 `n ∈ X.__all__`、不以 `_` 开头，且 `PUBLIC_SURFACE` 里每个名字（契约项除外）至少有一个使用者（防止冻结无人用的名字）；`r_scripts/` 文件名集合 == 冻结表。
19. `tests/sdk/test_result.py`：`write_result_json` 写出的键集合 == `RESULT_SCHEMA["required"]` 的键（外加传入 `lineage` 时的 `lineage`）；原子写（在 `os.replace` 前注入异常 → 目标不变、无 `.tmp` 残留）；目标是符号链接、输出根内祖先是符号链接、路径越出输出根 → `RuntimeError`；`load_result_json` 遇符号链接/坏 JSON 返回 `None`；`mark_result_status` 对 `"ok"/"partial"/"failed"` 写入、对 `"scaffold"` 与未知值返回 `False` 且文件不变、不抛；`validate_result_envelope` 接受 `status: "scaffold"`。
20. `tests/sdk/test_result_contract.py`：(a) `_sdk.write_result_json` 的产物同时通过 `_sdk.validate_result_envelope` 与框架 `omicsclaw.common.report.validate_result_envelope`；(b) 一组合法/非法样本（缺键、类型错、空字符串、非法 `status`、`scaffold`、`lineage` 为字符串、多余键）上两边判定逐条相同（问题列表空/非空一致）——`lineage` 为字符串与多余键两边都判合法，钉住"`optional` 不校验"；(c) `ast.literal_eval` 读出的 `RESULT_SCHEMA` 等于 import 所得；(d) 以 `_sdk` 写出 `summary={"device": "cuda"}` 的 `result.json`，ensemble `_device` 在有 GPU 租约、无 nvidia-smi 归属时得到 `cuda:<租约>`、`device_source == "skill"`；(e) `_sdk` 与框架的两个前缀相等，框架 `extract_user_guidance_lines/payloads` 能解析 `_sdk.emit_*` 写出的行；(f) `skills._sdk.report.DISCLAIMER == omicsclaw.common.report.DISCLAIMER`，且 `_sdk.generate_report_footer()` 含它。
21. `tests/sdk/test_replot_hint.py`：移到 singlecell `_lib` 后，对已知 skill 写入 `replot` 块、对未知 skill 不改文件、坏 `result.json` 不抛。
22. `tests/sdk/test_deps_registry.py`：`DEPENDENCIES` 可 `ast.literal_eval` 且等于 import 所得；61 键；规范化后唯一；`module` 全表唯一；无"某名字既是某键的规范化形式又是另一条目的 `module`"；每个值必有四字段、可选字段 ⊆ {`also`, `alt_env`}；`kind` 取值；`pip` 类 `install == "pip install " + " ".join([键, *also])`；git 类、r 类、有 `also` 的条目恰为 §3.9 所列；**反查**：`_resolve("scvi")` → `scvi-tools`，`"tangram"` → `tangram-sc`，`"paste"` → `paste-bio`，`"STAGATE_pyG"` → `STAGATE-pyG`，`"spatialde"` → `SpatialDE`；**回落集合 == 冻结空表**：对 `skills/**` 非测试代码里依赖 API 的全部字符串调用名（F29 的 AST 规则），经 `_resolve` 走到回落的名字集合必须等于测试里的 `FALLBACK_ALLOWED = {}`；未知名 `require("no-such-pkg")` 报错含 `pip install no-such-pkg`；`require` 缺包时报错含 `install` 与 `feature`；`kind="r"`：假 `RScriptRunner.get_missing_packages` 返回空/非空时 `is_available("xcms")` 为 `True`/`False`，Rscript 不存在时为 `False` 不抛，`require("xcms")` 抛 `TypeError`；`alt_env`：`find_spec` 为空、`is_env_available` 真/假/抛异常 → `True`/`False`/`False`；四个旧 `_lib/dependency_manager.py` 不存在。
23. `tests/sdk/test_bootstrap.py`：94 个主脚本里凡 import `skills.*` 的，第一条 `skills.` import 之前都有与模板逐 AST 相等的引导块；模板同。三种情形各一例（审核重要意见 3）：
    - 23a 本机：从无关 cwd 以 `-B`、清空 `PYTHONPATH` 跑 3 个轻量脚本（bulkrna-qc、genomics-qc、proteomics-de）`--help` 退出 0；
    - 23b ensemble：cwd = `tmp_path/trial`、argv 为脚本绝对路径、`env={"PYTHONPATH": repo_root, …}` 跑同一脚本 `--help` 退出 0；另把该 skill 目录复制到 `tmp_path/outside/<skill>/`（仓库外，无锚点）并以 `PYTHONPATH=repo_root` 运行 → 退出 0，且脚本内 `_PROJECT_ROOT == repo_root`（经一个在 `--help` 前打印 `_PROJECT_ROOT` 的探针脚本复本验证）；不设 `PYTHONPATH` 时 → `ModuleNotFoundError: skills`（锚点缺失不静默猜测）；
    - 23c 沙箱：沙箱镜像可用时（`OMICSCLAW_TEST_SANDBOX=1`，否则跳过并显示）经 `SandboxExecutor` 以同路径只读挂载跑同一脚本 `--help` 退出 0；无沙箱时的替代：把仓库 `skills/` 与 `omicsclaw/` 以只读权限复制到 `tmp_path/<同层级路径>` 并 `chmod -R a-w` 后运行，验证引导块不写盘、只读下可用。
24. `tests/sdk/test_help_probe.py`（slow）：94 个主脚本 `--help`，失败集合恰等于 4 个 consensus 薄壳。

### 5.2 关键变异（每条应使至少一个测试变红）

| # | 变异 | 应红的用例 |
|---|---|---|
| M1 | 任一 skill 脚本加 `from omicsclaw.common.report import write_result_json` | 15 |
| M2 | 任一 `_lib` 加 `__import__("omicsclaw.core.external_env")` | 2、5b |
| M3 | 恢复 `omicsclaw/core/__init__.py` 或在 `omicsclaw/r_scripts/` 放回一个 `.R` | 1 |
| M4 | `without_control_credentials` 不再过滤 / 改为大小写敏感 / `_start` 去掉 `env=` | 10 |
| M5 | 把 `OMICSCLAW_REMOTE_AUTH_TOKEN` 加进 `ENV_WHITELIST` 并去掉 `LocalExecutor` 的过滤 | 11 |
| M6 | 修好 `_llm.py`（删掉那行 import）却不改已知项表 | 3 或 15（恰好相等） |
| M7 | `_sdk/result.py` import `skills.singlecell._lib…` | 4 |
| M8 | `_sdk` 模块新增公开函数而不改 `PUBLIC_SURFACE`；或 skill import `_sdk` 的非公开名；或冻结一个无人使用的名字 | 18 |
| M9 | `write_result_json` 把 `summary` 改名 | 19、20 |
| M10 | `DEPENDENCIES` 某值改成 `DependencyInfo(...)` 调用或含 lambda | 22 |
| M11 | 框架 `common/report.py` 恢复对 `skills.*` 的 import | 16 |
| M12 | 任一主脚本引导块改回 `parents[3]`，或把 `next(..., None)` 改成无默认值的 `next(...)` | 23、23b |
| M13 | 从环境读取清单删掉 `tools/builtin/bash.py` | 12 |
| M14 | `_sdk/r_script_runner.py` 恢复任何凭据过滤 | 5、7 |
| M15 | `write_owned_text` 改成直接 `open(path, "w")` | 19 |
| M16 | `_resolve` 去掉 `module` 反查 | 22（`scvi`/`tangram`/`paste` 进入回落集合） |
| M17 | `sc_enrichment.py` 用不带别名的 `from skills._sdk.r_script_runner import R_SCRIPTS_DIR` | 7b |
| M18 | 漏改 `preflight.py`:622 的 `from skills.singlecell._lib import dependency_manager` | 3（B2） |
| M19 | 框架或 `_sdk` 一侧改动 `DISCLAIMER` 文本 | 20(f) |
| M20 | `validate_result_envelope` 开始校验 `lineage` 类型 | 20(b) |

---

## 6. 风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 遗漏的隐式耦合：字符串 import、`runpy`、`subprocess [python, -m, omicsclaw…]` | B9 扫全部 `omicsclaw.*` 形字符串常量；B10 子进程行为探针；交付时另 grep `"-m", "omicsclaw` 人工核对一次并记入交付记录 |
| R2 | 修好 10 个 sc 脚本后暴露此前被掩盖的运行期问题（0061 R14） | 阶段一只承诺 `--help` 与 F34 列出的测试；其余如实记入交付记录 |
| R3 | skill 侧不再剔除后，不经 `bash`/`LocalExecutor` 启动的 skill（用户自己的 shell、CLI `!<cmd>`、老的 remote job 路由）会把 token 传给 R/conda 子进程 | 这些路径上的环境本来就是用户自己的；remote job 路由不可 import（0061 F15）。Desktop 模式下 agent 的 `bash` 已剔除。在交付记录与 `AGENTS.md` 写明"剔除只在框架启动边界" |
| R4 | 简化的 `write_owned_text` 放宽了硬链接与 Windows junction 防护（Q1） | 威胁模型变了（§3.3）；保留部分由用例 19 钉住 |
| R5 | 框架 `common/report.py` 与 `_sdk/result.py`/`report.py` 两份实现漂移 | 用例 20 同样本比对 + `DISCLAIMER` 相等；框架那份只剩不可 import 的旧代码在用，0057/0058 删 autoagent/runtime 时可一并评估是否删除 |
| R6 | 阶段二 diff 大（约 140 个文件） | 改写脚本只动 import 行与引导块，AST 复核符号集合不变；按域拆成 7 个提交，每个提交跑主命令 |
| R7 | 0056 在途文件被并行修改，`LocalExecutor` 那一行冲突 | 改动一行、测试独立成文件；实施前与 0056 负责方对一次 |
| R8 | `_sdk` 被 3.13 专有语法污染，3.11 的 `OmicsClaw` 环境跑不了 | 慢测试用 `OmicsClaw` 解释器跑 `--help`；代码审查时注意 |
| R9 | 冻结公开面过严，阶段二之后的正常维护也要改测试表 | 这是设计意图：`_sdk` 的任何变更都应被看见；表在测试里，改动成本是一行 |
| R10 | `pip install` 安装态：`skills._sdk` 需有 `__init__.py` 才会被 `packages.find` 收进 wheel；R 脚本由 `**/*.R` 收入（F7） | 用例 1 断言 `__init__.py` 存在；交付时 `python -m build` 一次、列出 wheel 内 `skills/_sdk/` 文件并记入交付记录 |
| R11 | 统一引导块在 `site-packages` 安装态下同样要找到锚点 | 锚点 `skills/_sdk/__init__.py` 随 wheel 安装，`parents` 能走到 `site-packages`；R10 的构建核对里顺带跑一个脚本的 `--help` |
| R12 | 锚点缺失且调用方没设 `PYTHONPATH` 时脚本以 `ModuleNotFoundError: skills` 失败 | 有意为之：不猜测仓库位置；用例 23b 钉住失败形态，报错信息清楚 |
| R13 | `kind="r"` 的 `is_available` 要起 Rscript 子进程，比 `find_spec` 慢 | 今天无调用者；结果按名字缓存于进程内（与 `pip` 类同一 `lru_cache` 策略），`alt_env` 路径除外 |

---

## 7. 非目标

- 4 个 consensus 薄壳与 `_llm.py` 对框架的 import（0058）。
- `skills/**/tests/` 下 3 个基准脚本的死 import（0059/0060）；`sc-preprocessing` skill 测试的包名冲突（F34，既有问题）。
- `replot` 提示指向不存在命令这件事（`CLAUDE.md` 已记为开放项）；本计划只搬家。
- demo 路径里 `_PROJECT_ROOT / "scripts"` 对仓库根 `scripts/generate_demo_data.py` 的依赖（3 处，F30）。
- 依赖的探测与安装、`## Dependencies` 漏报（0061）；BANKSY 子环境 yml（0061 Q12）。
- CLI `!<cmd>` 与 MCP 子进程的环境策略（F16）；把 provider key/bot token 加进剔除名单（Q7 另开议题）。
- 删减框架 `omicsclaw/common/` 中 skill 不再使用的函数（除 `write_replot_hint`，Q11）。
- ensemble 的 `PYTHONPATH` 设置（F31）与 0059 冻结清单的实现（§3.9 只提要求）。
- `omicsclaw/autoagent/` 对 `skills._lib` 的 import（0057/0058 删除 autoagent 时消失）。

---

## 8. 第 2 版新增问题（已裁定）

Q1–Q12 已裁定（§0.3）。以下两条由审核重要意见 1 引出，owner 2026-09-24 裁定均按推荐（**Q13 = a、Q14 = a**），设计已按此写入 §3.4 与用例 22。

| # | 问题 | 选项 | 推荐 |
|---|---|---|---|
| Q13 | `singler` 一条装两个包（`pip install singler singlecellexperiment`，F25） | a 可选字段 `also: [PyPI 名]`，`install` 由 `[键, *also]` 生成；b `install` 允许为列表；c 保持字符串，在用例 22 里列为具名例外 | **a**：包名留在结构化字段里，0061 的安装白名单直接取 `[键, *also]`，不必解析命令字符串；b 让 `install` 字段有两种类型，读者都要分支；c 把知识藏进测试 |
| Q14 | `kind="r"` 条目的语义 | a `is_available` 用 Rscript 探测 R 包、异常返回 `False`，`require`/`get` 抛 `TypeError`；b 把两个 `r` 条目移出 Python registry，并入 `r_dependency_manager` 的 R 表；c 保持旧行为（`__import__`，恒为 `False`） | **a**：0061 需要在同一张表里看到 `r` 类；c 是缺陷（F27）；b 会让 0061 读两张表 |

---

## 9. 修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| 1 | 2026-09-24 | 初稿：按 owner 裁定 D1–D8 起草；现状 F1–F36 亲自核实（AST 扫描、批量 `--help` 探针、registry 对比、全量测试基线） |
| 2 | 2026-09-24 | Q1–Q12 按 owner 2026-09-24 裁定移入 §0.3；按独立审核（"有条件通过"）修订，逐条处置见 §10；新增 F37、F38，更正 F6、F11（核对后维持工作树行号）、F29/F30、F34；新增 Q13、Q14；附录 A 改为可直接复跑的脚本全文 |
| 定稿 | 2026-09-24 | owner 裁定 Q13 = a、Q14 = a，选择不再复核、直接定稿；正文未改设计 |
| 定稿后勘误 | 2026-09-24 | 定稿后勘误（2026-09-24）：§3.9 冻结标识措辞按 owner 冻结裁定对齐，设计不变 |

---

## 10. 审核意见处置表（第 2 版）

独立审核结论"有条件通过"。每条都已对工作树复核；"部分采纳"与"不采纳"写明理由。

### 重要

| # | 意见 | 处置 | 说明与落点 |
|---|---|---|---|
| I-1a | 保留按 `module` 反查，否则 `scvi`/`tangram`/`paste`/`STAGATE_pyG` 回落成错包 | **采纳** | 复核：32 个调用名中 `scvi`×5、`tangram`×2、`paste` 只能靠反查命中，`STAGATE_pyG` 靠规范化命中（F29）。`_resolve` 固定四步顺序并加歧义检查（§3.4）；M16 |
| I-1b | 用例 22 断言"回落集合 == 冻结空表" | **采纳** | 复核今天回落集合为空（F29）；用例 22 的 `FALLBACK_ALLOWED = {}` |
| I-1c | 裁定 `singler` 两包 | **采纳** | 推荐 `also` 字段，另两种做法列为选项（Q13） |
| I-1d | 写明 `kind="r"` 时 `is_available` 的语义 | **采纳** | §3.4；同时发现旧简化版对 R 包永远 `False`（F27），列 Q14 |
| I-2 | `sc_enrichment.py` 的两个 R 目录，机械替换会覆盖 | **采纳** | 复核 :125/:126（F6）。改为别名 `_SDK_R_SCRIPTS_DIR`、只替换表达式、保留左值（§3.2）；用例 7b、M17 |
| I-3a | 引导块用 `next(..., None)`，缺锚点交给 `PYTHONPATH` | **采纳** | §3.11；另加 `REPO_ROOT`，使缺锚点时 `_PROJECT_ROOT` 仍指向提供 `_sdk` 的仓库（否则 31 个把 `_PROJECT_ROOT` 另作他用的脚本会拿到 `None`）；R12 |
| I-3b | 本机/ensemble/沙箱三种情形逐一论证，各配用例 | **采纳** | §3.11 表；用例 23a–23c。沙箱用例在无镜像时以只读副本替代并显示跳过原因 |
| I-4a | B2 扩展到 `skills.*`（抓 `preflight.py`:622 这类） | **采纳** | 复核 :622 与 :25 两处（F30′）。B2 的存在性判定补上命名空间目录与 `from P import n` 的 `n`（§3.8）；M18 |
| I-4b | 扫描 `^omicsclaw(\.\w+)+$` 字符串常量，F3 列为具名例外 | **部分采纳** | 扫描规则采纳为 B9。复核全仓只有 F3 一处；阶段一第 3 步即把它改成 `"skills._sdk.external_env"`，所以 B9 的已知项表为空、F3 作为"先红"样本，而不是长期例外——列为例外会让表在阶段一合入的同一提交里就过期 |
| I-4c | 行为探针：`sys.modules["omicsclaw"]=None` 后逐个 import `_lib` | **采纳** | B10；因第三方包缺失的模块记"跳过"并列名，避免在缺 torch 等的环境里误报 |
| I-5a | 开工时同 commit 重跑基线并写进交付记录 | **采纳** | 文首"开工第一步"、§4 阶段一第 0 步；验收改为"⊆ 开工基线" |
| I-5b | 扫描与探针脚本写进计划，能直接复跑 | **采纳** | 附录 A 给出全文，从仓库根运行、输出到 `$OUT`（默认 `/tmp`），不再引用会话临时目录 |

### 次要

| # | 意见 | 处置 | 说明 |
|---|---|---|---|
| m-1 | 用例 1 改为"没有 `.py`/`__init__.py`" | **采纳** | 同时加 `.R`（`r_scripts/` 同理）；B1 |
| m-2 | 用例 9 改用 `monkeypatch.setitem(sys.modules, "banksy", None)` | **采纳** | 复核进程内路径经 :928 import `banksy_runner` → `banksy`，捕获 `ImportError`（F11） |
| m-3 | 用例 18 限定 `skills/**` 与 `templates/**` 非测试 | **采纳** | 并写明契约测试可读非公开属性（§3.6） |
| m-4 | 公开面只冻结实际被用到的名字 | **采纳** | 复核：`r_utils` 用 1/7、`r_dependency_manager` 用 2/4、`external_env` 用 3/5；另发现 `RScriptResult`、`validate_result_envelope`、`RESULT_STATUS_VALUES`、`DISCLAIMER` 无 skill 使用者，一并移出；用例 18 反向检查"冻结名必须有使用者"（§3.10、M8） |
| m-5 | `child_environment` 改名，避免与 `mcp/stdio.py`:92 同名 | **采纳** | 改名 `without_control_credentials`；名单改名 `CONTROL_CREDENTIAL_NAMES`；用例 10 断言 `bash.py` 无 `child_environment` |
| m-6 | 写明旧 `.upper()` 与新 frozenset 的大小写差异及处置 | **采纳** | 处置为保持大小写不敏感（§3.7、F12）；用例 10 含小写变体、M4 |
| m-7 | 写明 `RESULT_STATUS_VALUES` 不含 `scaffold` | **采纳** | F37、§3.3、用例 19 |
| m-8 | `DISCLAIMER` 纳入契约测试 | **采纳** | §3.6 契约表、用例 20(f)、M19 |
| m-9 | Q3 注明 `optional` 只作说明、不参与校验 | **采纳** | §3.3；用例 20(b) 的样本含"`lineage` 为字符串"与"多余键"；M20 |
| m-10 | `CONTRIBUTING.md`:108/172/351 改为必改 | **采纳** | 复核三处（F38）；阶段二第 6 步列为必改 |
| m-11 | §3.9 补 0059 冻结清单覆盖 `_sdk/**` 与本域 `_lib/**` | **采纳** | §3.9 表"冻结清单"一行；F20 补 `script_sha256` 事实 |
| m-12a | F6 实为 23 行、19 个文件 | **采纳** | 复核 `grep` 得 23 行/19 文件（第 1 版的 24 把 `core/` 的 `_SCRIPTS_DIR` 算了进去）；已更正 |
| m-12b | F30 计数只有 91；锚定 `omicsclaw` 的是 6 个，漏了 `bulkrna-cosinor-rhythm` | **采纳** | 按互斥类重算：79/7/6/1/1 = 94（F30）；附录 A 给分类脚本 |
| m-12c | F34 `test_scrna_method_contracts.py` 只有 4 个用例 | **采纳** | 复核 4 个用例、4 个失败；"46 passed"来自同批其他文件，已更正 |
| m-12d | F11 行号应为 943–947 | **不采纳（已核对）** | 工作树逐行：:939 `except ImportError`、:943 注释、:944 `from pathlib import Path`、**:945–949** `from omicsclaw.core.external_env import (…)`、:951 `sub_env = …`、:953 `raise EnvNotFoundError(`。第 1 版写 944–949 含了 `pathlib` 行，第 2 版精确为 945–949，另补 :928/:939 两个进程内路径的行号 |

另：第 1 版 F9 写"剔除调用点共 8 处"，复核为 6 处调用 + 3 处 import，已更正。

---

## 附录 A：复跑脚本（只读；从仓库根运行，输出写到 `$OUT`，默认 `/tmp/0062`）

```bash
export OUT=${OUT:-/tmp/0062}; mkdir -p "$OUT"
cd "$(git rev-parse --show-toplevel)"
```

**A1 `scan_imports.py`**（F1–F5、F18–F19）：`python3 scan_imports.py skills > $OUT/skills_imports.tsv`；`python3 scan_imports.py framework > $OUT/framework_imports.tsv`

```python
import ast, subprocess, sys
from pathlib import Path
ROOT = Path.cwd()
tracked = set(subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split())

def scan(paths, prefix):
    out = []
    for p in paths:
        rel = str(p.relative_to(ROOT))
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 and (n.module == prefix or n.module.startswith(prefix + ".")):
                out.append((rel, n.lineno, n.module, ",".join(a.name for a in n.names), "top" if n.col_offset == 0 else "nested"))
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name == prefix or a.name.startswith(prefix + "."):
                        out.append((rel, n.lineno, a.name, "(module)", "top" if n.col_offset == 0 else "nested"))
    return out

def py(d):
    return sorted(p for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts) if (ROOT / d).exists() else []

if sys.argv[1] == "skills":
    rows = scan(py("skills"), "omicsclaw")
else:
    files = py("omicsclaw") + py("tests") + py("scripts") + sorted(ROOT.glob("*.py"))
    rows = scan(files, "omicsclaw.core") + scan(files, "skills")
for r in rows:
    print("T" if r[0] in tracked else "U", *r, sep="\t")
```

汇总：非测试文件数 `awk -F'\t' '$2 !~ /\/tests\//{print $2}' $OUT/skills_imports.tsv | sort -u | wc -l`；按符号计文件数用下面的一行：

```bash
python3 -c "
import csv,collections;d=collections.defaultdict(set)
for t,f,l,m,ns,pos in csv.reader(open('$OUT/skills_imports.tsv'),delimiter='\t'):
    if '/tests/' in f: continue
    for n in ns.split(','): d[(m,n)].add(f)
[print(len(v),*k) for k,v in sorted(d.items(),key=lambda x:-len(x[1]))]"
```

**A2 `scan_strings.py`**（F3、B9）

```python
import ast, re
from pathlib import Path
for p in sorted(Path("skills").rglob("*.py")):
    if "/tests/" in str(p) or "__pycache__" in p.parts:
        continue
    for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"omicsclaw(\.\w+)+", n.value):
            print(p, n.lineno, n.value)
```

**A3 `probe_help.sh`**（F10；`PY` 默认 `OmicsClaw` 环境）：`bash probe_help.sh > $OUT/help_probe.tsv`；汇总 `cut -f1 $OUT/help_probe.tsv | sort | uniq -c`

```bash
#!/bin/bash
PY=${PY:-/opt/conda/envs/OmicsClaw/bin/python}
ROOT=$(git rev-parse --show-toplevel); WORK=$(mktemp -d)
for sk in $(find "$ROOT/skills" -name SKILL.md -printf '%h\n' | sort); do
  for p in "$sk"/[!_]*.py; do
    [ -f "$p" ] || continue
    ( cd "$WORK" && env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 timeout 120 "$PY" -B "$p" --help >/dev/null 2>"$WORK/err" ); rc=$?
    printf '%s\t%s\t%s\n' "$rc" "${p#$ROOT/}" "$(grep -E 'Error' "$WORK/err" | tail -1)"
  done
done
```

**A4 `closure.py`**（F21）：`python3 closure.py atomic_write_owned_output_text collect_output_claim_identities is_contained_output_path is_scientific_output_file`

```python
import ast, sys
src = open("omicsclaw/common/output_claim.py", encoding="utf-8").read()
defs = {}
for n in ast.parse(src).body:
    if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
        defs[n.name] = n
    elif isinstance(n, (ast.Assign, ast.AnnAssign)):
        t = n.targets[0] if isinstance(n, ast.Assign) else n.target
        if isinstance(t, ast.Name):
            defs[t.id] = n
seen, stack = set(), list(sys.argv[1:])
while stack:
    s = stack.pop()
    if s in seen:
        continue
    seen.add(s)
    stack += ({x.id for x in ast.walk(defs[s]) if isinstance(x, ast.Name)} & set(defs)) - seen
print(sorted(seen)); print("lines", sum(defs[s].end_lineno - defs[s].lineno + 1 for s in seen), "of", len(src.splitlines()))
```

**A5 `registry.py`**（F28）

```python
import ast
from pathlib import Path
entries = {}
for d in ["spatial", "singlecell", "proteomics", "metabolomics"]:
    for n in ast.parse(Path(f"skills/{d}/_lib/dependency_manager.py").read_text(encoding="utf-8")).body:
        t = n.target if isinstance(n, ast.AnnAssign) else (n.targets[0] if isinstance(n, ast.Assign) else None)
        if isinstance(t, ast.Name) and t.id == "DEPENDENCY_REGISTRY":
            for k, v in zip(n.value.keys, n.value.values):
                args = [a.value if isinstance(a, ast.Constant) else "<expr>" for a in v.args]
                entries.setdefault(k.value, []).append((d, args, [kw.arg for kw in v.keywords]))
print("entries", sum(len(v) for v in entries.values()), "keys", len(entries))
for k, v in sorted(entries.items()):
    if len(v) > 1:
        print("DUP", k, [x[0] for x in v], "module-conflict" if len({x[1][0] for x in v}) > 1 else "",
              {x[1][1] for x in v} if len({x[1][1] for x in v}) > 1 else "")
    for d, args, kws in v:
        if kws or "<expr>" in args:
            print("NONLITERAL", k, d, kws)
mods = {}
for k, v in entries.items():
    for d, args, _ in v:
        mods.setdefault(args[0], set()).add(k)
print("module shared by keys:", {m: ks for m, ks in mods.items() if len(ks) > 1})
```

**A6 `dep_names.py`**（F29；阶段二后把 `REGISTRY_SOURCES` 换成 `skills/_sdk/deps.py` 的 `DEPENDENCIES` 再跑，结果即用例 22 的回落集合）

```python
import ast, re
from pathlib import Path
keys, mods = {}, {}
for d in ["spatial", "singlecell", "proteomics", "metabolomics"]:
    for n in ast.parse(Path(f"skills/{d}/_lib/dependency_manager.py").read_text(encoding="utf-8")).body:
        t = n.target if isinstance(n, ast.AnnAssign) else (n.targets[0] if isinstance(n, ast.Assign) else None)
        if isinstance(t, ast.Name) and t.id == "DEPENDENCY_REGISTRY":
            for k, v in zip(n.value.keys, n.value.values):
                keys[k.value] = v.args[0].value
                mods.setdefault(v.args[0].value, set()).add(k.value)
norm = lambda s: re.sub(r"[-_.]+", "-", s).lower()
nkeys = {norm(k): k for k in keys}
FUNCS = {"require", "is_available", "install_hint", "get_dependency"}
names = set()
for p in Path("skills").rglob("*.py"):
    if "/tests/" in str(p) or p.name == "dependency_manager.py" or "__pycache__" in p.parts:
        continue
    src = p.read_text(encoding="utf-8")
    get_is_dep = re.search(r"dependency_manager import[^\n]*\bget\b(?! as)", src) is not None
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            f = n.func
            if isinstance(f, ast.Name) and (f.id in FUNCS or (f.id == "get" and get_is_dep)):
                names.add(n.args[0].value)
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in {"dm", "sc_dep_manager"}:
                names.add(n.args[0].value)
for x in sorted(names):
    how = ("key" if x in keys else f"norm->{nkeys[norm(x)]}" if norm(x) in nkeys
           else f"module->{sorted(mods[x])}" if x in mods else "FALLBACK")
    print(x, how)
```

**A7 `bootstrap_classes.py`**（F30）

```python
import re
from collections import Counter
from pathlib import Path
c, ex = Counter(), {}
for sk in sorted(Path("skills").glob("**/SKILL.md")):
    for p in sorted(sk.parent.glob("*.py")):
        if p.name.startswith("_"):
            continue
        s = p.read_text(encoding="utf-8")
        if '"omicsclaw" / "__init__.py"' in s: k = "anchor-omicsclaw"
        elif re.search(r"sys\.path\.insert\(0, str\(Path\(__file__\)\.resolve\(\)\.parents\[\d\]\)\)", s): k = "parents[N]-oneliner"
        elif re.search(r"^_PROJECT_ROOT = Path\(__file__\)\.resolve\(\)(\.parent)+\s*$", s, re.M): k = "_PROJECT_ROOT-parent-chain"
        elif "sys.path.insert" in s: k = "other"
        else: k = "none"
        c[k] += 1; ex.setdefault(k, []).append(str(p))
print(sum(c.values()), dict(c))
for k in ("anchor-omicsclaw", "other", "none"):
    print(k, ex.get(k))
```

**A8 其余单行**

```bash
grep -rn '"omicsclaw" / "r_scripts"' --include=*.py skills | tee $OUT/r_paths.txt | wc -l       # F6：23
grep -rln '"omicsclaw" / "r_scripts"' --include=*.py skills | wc -l                             # F6：19
grep -rln "OUTPUT_CLAIM_FILENAME\|omicsclaw-run-claim" --include=*.py omicsclaw skills           # F21
grep -n "omicsclaw.common\|dependency_manager" CONTRIBUTING.md                                   # F38
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly -p no:cacheprovider -o addopts="" \
  tests/test_r_dependency_manager.py tests/test_scrna_method_contracts.py tests/test_sc_ambient_removal.py   # F34
```

## 附录 B：全量测试基线

```
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly -p no:cacheprovider tests \
  -o addopts="-m 'not slow and not demo and not eval' --import-mode=importlib" -rfE --continue-on-collection-errors \
  > $OUT/full_tests.txt 2>&1
grep -E "^(FAILED|ERROR)" $OUT/full_tests.txt | sed 's/ - .*//' | sort > $OUT/baseline_failures.txt
# 第 1/2 版参考值（工作树 0881aa7b + 未提交改动，2026-09-24）：221 failed, 6044 passed, 42 skipped, 5 deselected, 46 errors in 299.91s；
# baseline_failures.txt 267 行
```

失败按文件（前若干）：`test_skill_runner_contract.py` 76、`test_notebook_files.py` 30、`test_notebook_var_inspector.py` 28、
`runtime/consensus/test_driver.py` 12、`runtime/preflight/test_sc_batch.py` 10、`runtime/consensus/test_continuous_driver.py` 9、
`routing/test_consensus_interpret_hint.py` 9、`test_control_plane_documentation_contract.py` 7（D8 已知）、
`test_desktop_chat_abort_cancel_event.py` 5、`test_scrna_method_contracts.py` 4（core）、`test_sc_ambient_removal.py` 3（core）……；
收集错误 46 个文件，其中 `test_external_env.py`、`test_r_script_runner.py`、`test_r_script_runner_environment.py` 3 个归因 core，
其余为 remote/autoagent/notebook 等旧代码。**每阶段的全量回归以"失败集合 ⊆ 开工时同 commit 复跑的 `baseline_failures.txt`
减去 F36 的 10 项"为准**；开工基线逐字写进交付记录。
