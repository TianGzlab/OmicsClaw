# 计划 0056 — ensemble 基础层：`run_skill`、资源信号量、统一指标面板与 `tuning.yaml`

**状态**：第 2.1 版（2026-09-24），按复审与 owner 裁定局部修订，待 owner 终审；未写任何生产代码。

**前置**：无硬前置。依赖已落地的执行器分批（`engine/executor.py`）、`bash` 的沙箱接缝
（`entry/sandbox.py`）与 skill 索引（`omicsclaw/skills/`）。本计划是 0056–0060 系列的第一份，
后四份都建立在这里定下的接口上（§3.13）。

**给实现者的一条硬要求**：新代码的函数、类与模块 docstring 只写"是什么、做什么、参数与返回、
会抛什么"，以及会改变调用方式的行为说明（例如"超时记为 `timeout`，不抛异常"）。计划编号、
裁定历史、与旧代码或文献的对照、实测数字一律写进本计划、交付记录或**测试的 docstring**，不写进
生产代码注释。唯一例外是第三方代码的版权/许可声明（§3.7）。仓库里旧文件的高密度注释风格不构成反例。

---

## 0. 缘起与已定裁定

### 0.1 缘起

论文主线有三个创新点：**LLM 选参**、**多方法 consensus**、**SWE-bench 式 benchmark**。owner
把它拆成五份计划：

| 计划 | 内容 |
|---|---|
| **0056（本份）** | ensemble 基础层：skill 子进程执行、并行 fan-out、资源信号量、统一内部指标面板、机器可读搜索空间、`run_skill` 工具 |
| 0057 | 调参：确定性循环 `optimize_params`，以及"agent 自由编排 `run_skill`"对照组 |
| 0058 | consensus 路径 A（`run_consensus`） |
| 0059 | 方法层 benchmark（区域标签构造、与真值的相关性检验） |
| 0060 | 端到端 benchmark（含消融） |

今天的新框架里，agent 只能经 `bash` 手动跑 skill 脚本（AGENTS.md "Running a skill"）：一次一个、
`bash` 是屏障（`concurrency_safe=False`）、没有统一的产物位置、没有可比的质量指标、没有机器
可读的参数空间。旧栈里做过同类事情的三处代码——`autoagent/`、`runtime/consensus/`、
`runtime/workflow/`——都依赖已删除的 `omicsclaw.skill`，**无法 import**（AGENTS.md:178-181），
只能作为参考重写。

### 0.2 已定裁定（owner，第一版）

1. 新包 `omicsclaw/ensemble/`，子模块至少有 `runner`（skill 子进程执行 + 并行 fan-out + 资源
   信号量）与 `metrics`（统一内部指标面板，按分析类型注册，调参与 consensus 共用同一套）；
   `tuning`、`consensus` 本份只留位置、不实现。旧 `omicsclaw/autoagent/`、`runtime/consensus/`、
   `runtime/workflow/` 本份**不删**（0057/0058 迁完后删），本份列出复用/重写清单（§3.14）。
2. 新工具 `run_skill(skill, method, params, input, ...) → {status, output_dir, metrics, ...}`：
   只运行已索引 skill 的主脚本；参数经白名单校验（`tuning.yaml` 与脚本 argparse）；每次调用
   写独立输出目录，`concurrency_safe=True`；内部资源信号量防抢卡；执行位置跟随 `bash` 的沙箱
   设置，benchmark 固定同一镜像；审批默认自动放行；每次运行受时间与内存上限约束，超限如实
   记为失败；可通过配置整体不挂载（消融基线）。
3. 产物存储 `<workspace>/ensemble_runs/<run_id>/<method>/<trial>/`；默认只保留 `result.json`、
   标签向量与指标，h5ad 只留最佳试验；配置开关可全部保留。
4. 每个 skill 目录新增 `tuning.yaml`（不恢复 `skill.yaml`，不动 `SKILL.md` frontmatter 的四个
   键）；测试校验它与脚本 argparse 一致；本份只写 `spatial-domains`（7 个方法）；**不向方法
   提供真值类别数**。
5. 统一指标面板以 CHAOS/PAS/MLAMI 为基础（默认权重 0.4/0.2/0.4），表达空间指标可作补充；面板
   只用内部指标，真值指标放单独的评估模块，调参与 agent 永远看不到真值。
6. 开发数据 `/workspace/dataset/private/spFoundation_SpatialCorpus/test/slideseqv2_mouse_hippocampus.h5ad`：
   不用 `X`，从 `layers['counts']` 起跑 `spatial-preprocess`，预处理参数固定；冒烟验收在其上跑通
   `run_skill` 并行 7 个方法。
7. 第二个试点 `sc-batch-integration`（`obsm` embedding）只说明接口，不实现。

### 0.3 已定裁定（owner，第二版，针对审核分歧）

| # | 裁定 | 落实位置 |
|---|---|---|
| D1 | v1 就对面板中受标签占比影响的指标做**机会校正**（kappa 式 `(观测−期望)/(1−期望)`，按每个指标的确切定义推导随机期望），同时记录原始值；加合成数据测试量化"偏向少簇"的偏差；**偏差评估完成并经 owner 过目之前 0057 不开工** | §3.7、T3b、§6 第 9 条、§3.13 |
| D2 | 核查 CHAOS/PAS 的文献原始定义（SDMBench、SpatialPCA），对照旧实现指出偏差，给出按文献修正后的定义、方向、归一化与机会校正，附 URL | §3.7.1 |
| D3 | GPU 策略：GPU 请求不在 `fits()` 被拒；启动时（配置为空时）**自动检测** GPU（本机与沙箱各自检测）；有 GPU → 进 GPU 槽位池；无 GPU → 支持 CPU 的方法降级到 CPU 并记"降级"，只能 GPU 的方法明确失败并报原因；显式配置 `ensemble_gpus` 时以配置为准；写清审批语义 | §3.4、§3.8 |
| D4 | 沙箱资源放宽：上调沙箱默认资源（内存、CPU、`/tmp` 容量、pids-limit、shm-size 等），给具体默认值与依据，可配置；每个试验单独设 `TMPDIR`/`MPLCONFIGDIR`/`NUMBA_CACHE_DIR`，cwd 设为试验目录 | §3.10、§3.3 |
| D5 | 其余审核意见全部采纳（真值泄漏、沙箱找不到代码、超时、backfill、schema 谓词与约束、golden 快照、Py3.11 import 测试及各小问题），第一版中审核同意的推荐改标"已定" | §9 修订记录 |
| D6（2.1 版） | 自检失败：**显式开启** ensemble（`--ensemble true` 或 `OMICSCLAW_ENSEMBLE=true`）→ 报错、不启动；**默认开启**（未设置）→ 只告警、不挂载 ensemble 相关工具，其余照常启动。第二版未决 N1–N5 按推荐采纳，N3 附加 `spatial_leiden_ami` 单独报告，N5 附加资源池内存余量 | §3.10、§3.11、§7.1 |

---

## 1. 目标

| # | 目标 | 可观察的结果 |
|---|---|---|
| G1 | `tuning.yaml` schema 与加载器 | `omicsclaw/ensemble/space.py` 能加载、校验、渲染 CLI；坏文件给出指名字段的错误；支持比较/`in` 谓词与跨参数约束 |
| G2 | `spatial-domains` 的 `tuning.yaml` | 7 个方法齐全；一条测试把它与脚本的真实 argparse 逐项比对 |
| G3 | 统一指标面板 + 评估模块 | 按文献定义的 CHAOS/PAS + MLAMI，全部机会校正、原始值并存；合成数据偏差报告；ARI/NMI 只在 `evaluation.py` |
| G4 | 资源池 | 自动检测 GPU；GPU/内存/CPU 一次性原子申请；不推迟队头的 backfill；不死锁 |
| G5 | 试验运行器 | 一次试验 = 独立目录 + 受监督子进程（时间/内存上限）+ 打分 + 保留策略 + `trial.json`；本机与沙箱两条路径；每试验独立临时目录 |
| G6 | `run_skill` 工具 | `AUTO` + `concurrency_safe=True`；一轮内多个调用真正并行，由资源池限流；运行期暂停引擎超时、自身兜底 |
| G7 | 装配、沙箱与消融开关 | 仓库只读同路径挂载并在启动时自检；沙箱默认资源上调；`ensemble=false` 时系统提示与工具表与 golden 快照逐字节相同 |
| G8 | 冒烟验收 | 开发数据上一轮 7 个 `run_skill` 并发，结果如实（含失败与降级） |

---

## 2. 现状（亲自核实；行号以 2026-09-24 工作树为准，实施时按符号名定位）

| # | 事实 | 出处 |
|---|---|---|
| F1 | 执行器把一轮的调用按 `is_concurrency_safe` 分批：不安全的单独成批（屏障），相邻安全调用同批并发；每个调用一个 Task，结果按调用顺序落槽 | `engine/executor.py` `execute_tool_calls`（:145-265）、`_concurrency_groups`（:307-343） |
| F2 | 生产没有并发上限（`max_concurrent_tools=0`），`serialize_unsafe_tools=True` | `engine/config.py`:60-77；`executor.py`:211-212 |
| F3 | **每个调用有引擎侧超时**：生产 `tool_timeout_s = 600.0`；`bash` 以 `tool_timeout_s − ENGINE_TIMEOUT_MARGIN(15 s)` 构造 | `entry/config.py`:160、:491-512；`tools/builtin/bash.py`:280；`executor.py` `_execute`（:454-523） |
| F4 | `tools.context.pause_tool_timeout()` 让其内的时间不计入该调用的引擎超时（暂停期间引擎侧没有上界，由工具自己负责）；`report_progress()` 可报进度 | `tools/context.py`:495-512、:526；`executor.py` `_paused` docstring（:388-433） |
| F5 | `ToolPolicy` 权限字段默认取最保守值，放宽须显式声明；`use_skill` 是 `AUTO`+`concurrency_safe=True` 的先例 | `tools/base.py`:141-243；`skills/use_skill.py`:40 |
| F6 | 权限闸门阶段：`bypass-all` 放行 → `read-only` 拒绝未声明 `read_only=True` 者 → 受保护路径 → 规则文件 → 危险命令 → `auto-approve` → 工具自身 `approval_mode`；规则匹配的"主参数"是 schema `required` 中第一个 `string` 属性 | `permission/gate.py` `resolve`（:259-）；`permission/rules.py` `principal_key`（:449-472） |
| F7 | Desktop 没有移植 `/chat/permission`，需审批的工具在 Desktop 上等到超时 | `CLAUDE.md`:279 |
| F8 | 沙箱是**每个部署一个长期容器**，`bash` 经 `docker exec` 在里面跑；`--gpus`/`--memory`/`--cpus` 是容器级参数；`DockerEnvironment.run_bash(command, cwd, timeout)` 没有 env 参数，取消时只 SIGKILL 记录的那一个 PID | `sandbox/container.py` `run_arguments`（:53-104）；`sandbox/environment.py` `run_bash`（:97-164）、`_kill`（:173-188） |
| F9 | 沙箱装配：`SandboxBinding.environment is None` 表示在本机跑（关闭或降级）；`sandbox_required` 时起不来即拒绝启动 | `entry/sandbox.py`（:43-75、:78-138、:172-194） |
| F10 | `BashEnvironment.run_bash` 是结构化接缝；本机路径以新会话起进程、超时/取消时 `killpg`；`spawn_group_leader` 公开 | `tools/builtin/bash.py`（:369-406、:782-841、:927-965） |
| F11 | 工具挂载顺序：六个基础工具 → `use_skill` → `plan_write` → `memory_*`（只追加）→ MCP → `task`；全部过 hook 链与闸门 | `entry/assembly.py` `foundation_tools`（:295-363）、`build_app`（:1140-1206） |
| F12 | 开关先例：`planning`、`subagents`、`memory`；配置经 `_Option` 表同时接受 flag 与环境变量 | `entry/config.py`:232-280、`_OPTIONS`（:640-） |
| F13 | `tests/entry/test_permission_wiring.py` 的 `MOUNTED`（:49-61）是完整名单，新增默认挂载工具须同步；`tests/entry/test_assembly.py`:138-140 **只做前缀断言，无需修改** | 同左 |
| F14 | 分层：下层不得 import `entry`；`entry` 运行时不得加载 `omicsclaw.runtime` 等被替换的包 | `tests/entry/test_entry_is_the_top_layer.py`（:37-55） |
| F15 | `Skill` 记录**没有"主脚本"字段**；94 个 skill 中 16 个主脚本不叫 `<name 下划线化>.py`（含 `sc-batch-integration` → `sc_integrate.py`） | `skills/skill.py`:11-81；逐目录核对 |
| F16 | `Workspace.resolve` 跟随符号链接后要求落在 workspace 内，并拒绝凭据文件 | `tools/_workspace.py` `resolve`（:310） |
| F17 | `result.json` 信封由 `write_result_json` 写；写入拒绝经符号链接的输出根 | `common/report.py`:319-353；`common/output_claim.py`:323-352 |
| F18 | `spatial_domains.py`：argparse 在 `main()` 里构建（:912-944）；缺 `X_pca` 时自动 PCA（:955-959）；`spagcn/stagate/graphst` 与关闭 auto-k 的 `cellcharter` 未给 `--n-domains` 时静默取 7（:963-970）；每次都生成图（:1115）；`tables/domain_assignments.csv` 无条件写出（:620-630），**id 列名来自 `obs_names` 的索引名**：`reset_index()` 后只有索引无名时列名才是 `index` 并被改成 `observation`（:625）；写 `processed.h5ad`（:1135-1136）；**没有 `--seed`**；`--data-type` 没有 `choices` | 同左 |
| F19 | `_lib/domains.py`：`SUPPORTED_METHODS` 7 个（:40）；STAGATE 只要 `k_nn>0` 就忽略 `rad_cutoff`（:418-427）；**`pre_resolution` 只在 `stagate_alpha>0` 时传入训练**（:438-441）；BANKSY 库默认 `resolution=0.7`（:894），脚本总传 `--resolution`；GNN 与 CellCharter 内部种子固定 42（:375、:494、:991）；GPU 方法按 `torch.cuda.is_available()` 选设备、否则用 CPU（:432、:590、:1148） | 同左 |
| F20 | CellCharter auto-k：`auto_k_max` 为 `None` 时取 `n_domains`（若给）否则 `auto_k_min + 8`（:1032-1034、:1181-1183）；脚本在 auto-k 开启时不设 `n_domains`，故默认有效值为 `2 + 8 = 10` | 同左；`spatial_domains.py`:969-970 |
| F21 | SpaGCN：仓库 docstring 称 1.2.x 仅 CPU（`_lib/domains.py`:249）；**已核实**：`OmicsClaw` 环境安装的 SpaGCN 1.2.7 包源码中没有任何 `cuda`/`device` 引用 | `grep -rn "cuda\|device" site-packages/SpaGCN/*.py` 无输出 |
| F22 | `spatial-preprocess` 把 **`X` 当原始计数**（QC 后 `layers['counts'] = X.copy()`，`_lib/preprocessing.py`:228）；默认 `max_mt_pct=20`、`n_top_hvg=2000`、`n_pcs=30`（:37-50） | 同左；`spatial_preprocess.py` `_build_parser`（:940-1003） |
| F23 | 开发数据：41786 × 4000，`obs` 有 `cell_type`、`batch`（`sample1`），`obsm['spatial']`，`layers['counts']`，`uns` 为空 | `anndata.read_h5ad(..., backed='r')` |
| F24 | 旧 consensus 指标：代码里的 `chaos` 是"k=10 个空间近邻中同标签的比例"（高好）；`pas` 为"同标签近邻比例 < 0.5 的点所占比例"；`mlami` 为"标签 vs 坐标 kNN 图上 Leiden 的最大 AMI"；面板权重 0.4/0.2/0.4、按理论范围裁剪、失败剔除重归一；文件含 nichecompass 的 BSD-3 声明 | `runtime/consensus/spatial_metrics.py`:1-58、:88-237；`spatial_panel.py`:40-133 |
| F25 | 旧 autoagent 面板：silhouette 0.4 / `mean_local_purity` 0.4 / Calinski-Harabasz 0.2（`range 0..1000`，人为上界）；`mean_local_purity` 与旧 `chaos` 是同一量（k=8 对 k=10）；silhouette 所用 embedding 按方法而异 | `autoagent/metrics_registry.py`:223-246；`metrics_compute.py`:114-163、:567-607 |
| F26 | 旧 autoagent 试验运行器：新会话 + 进程树终止；**环境变量白名单**；超时写死 3600 s；未知参数"警告后忽略" | `autoagent/runner.py`:50-280、:307-346；`constants.py`:36-46 |
| F27 | 旧 fan-out：状态 `ok/failed/timeout/cancelled`；单步超时不取消兄弟步；幸存数门槛由调用方选；依赖已删除的 `omicsclaw.skill.resource_scheduler` | `runtime/workflow/fan_out.py`:25-30、:71-101、:240-254、:290-370 |
| F28 | `pyyaml` 不在 pip 核心依赖（只在 `environment.yml`:281）；`**/*.yaml` 已在 skills 的 package-data | `pyproject.toml`:52-65、:580-590 |
| F29 | 环境：`rapids_singlecell`（Py3.13，跑新栈测试）有 scanpy/anndata/yaml/pyarrow/psutil，缺 squidpy、igraph、torch 与全部 GNN 包；`OmicsClaw`（**Py3.11**）有 scanpy/squidpy/igraph/louvain/SpaGCN/GraphST/cellcharter/torch/torch_geometric/pytest，**缺 `STAGATE_pyG` 与 BANKSY**（`omicsclaw_banksy` 子环境也不存在）；本机**没有 docker/podman**；`spatial_domains.py --help` 在 rapids 环境可运行 | 本机逐个 import 核实 |
| F30 | 硬件：4 × H100 80GB、104 核、`MemTotal` 2 041 151 900 kB（≈ 1947 GiB） | `nvidia-smi`、`nproc`、`/proc/meminfo` |
| F31 | 测试基线：`tests/tools tests/engine tests/skills tests/entry/test_entry_is_the_top_layer.py tests/entry/test_open_app.py tests/sandbox` → **1847 passed, 2 skipped** | rapids_singlecell 环境 |
| F32 | `CLAUDE.md` 是默认系统提示的一部分，写"用 `bash` 跑 skill 脚本" | `entry/config.py` `system_prompt_files`；`CLAUDE.md` "How to Use a Skill" |
| F33 | 沙箱容器默认：`pids_limit=4096`、`/tmp` tmpfs `1g`、不传 `--shm-size`（Docker 默认 `/dev/shm` 64 MiB）、`memory`/`cpus`/`gpus` 空即不传、无 `--ulimit` | `sandbox/config.py`:49-69；`container.py`:73-98 |
| F34 | `omicsclaw/__init__.py`:5-12 仍导出懒属性 `run_skill`，指向已删除的 `omicsclaw.skill.runner`；仓库内（除旧包外）无调用者 | 同左；全仓 grep |
| F35 | **轮级超时**：`AppConfig.turn_timeout_s: float \| None = None`（在 `entry/config.py`:214，不在 `engine/config.py`）；设了数值时 `run_turn`（`entry/turn.py`:388-396）与 `TurnRunner._deadline`（:630-646）用 `asyncio.timeout` 包住**整轮**，到期取消引擎的全部 Task（含在途工具），终态 `failed`。仓库内没有任何 surface 或 launch 代码给它设默认值（全仓 grep），只能由 `--turn-timeout`/`OMICSCLAW_TURN_TIMEOUT_S` 设 | 同左 |
| F36 | 实际挂载顺序：`foundation_tools` 依次给出六个基础工具、`use_skill`、`plan_write`、`memory_search`、`memory_write`（`assembly.py`:341-362），`build_app` 随后追加 MCP 工具（:1154-1155），最后注册 `task`（:1195-1206）；`test_permission_wiring.py` 的 `MOUNTED` 无 MCP，末项为 `task` | 同左 |
| F37 | 仓库根目录含 `.env`（凭据）与 `.omicsclaw/`（规则文件、记忆库）；skill 脚本运行只需 `omicsclaw/` 与 `skills/`：`spatial_domains.py` 仅在 `--demo` 路径读 `examples/` 与 `scripts/`（:847、:852），`run_skill` 从不传 `--demo`；`omicsclaw/version.py` 不读 `pyproject.toml` | `ls -a`；同左 |
| F38 | 旧 `mlami` 先试 `sc.tl.leiden(flavor="igraph")`，`TypeError` 时回退到默认 flavor（需 `leidenalg`）（`spatial_metrics.py`:228-231） | 同左 |

---

## 3. 设计

### 3.1 包结构与分层

```
omicsclaw/ensemble/
  __init__.py      只放包 docstring 与少量常量；不 eager import 任何子模块（见下）
  space.py         tuning.yaml：TuningSpec / MethodSpec / ParamSpec / Predicate / Constraint / ResourceSpec，
                   load_tuning_spec()、TuningCatalog、validate_params()、render_cli_args()
  resources.py     ResourcePool / ResourceRequest / Lease；GPU 检测 detect_gpus()
  _supervise.py    stdlib-only 独立脚本：在执行环境里监督一个子进程的时间与内存
  execution.py     CommandExecutor Protocol；LocalExecutor、SandboxExecutor（经 BashEnvironment）
  store.py         ensemble_runs 目录布局、run_id/trial 编号、run.json、trials.jsonl、保留策略
  runner.py        Limits / TrialSpec / TrialResult / EnsembleRunner（prepare、run、fan_out）
  metrics/
    __init__.py    面板注册表：analysis 键 → PanelDef；只含数据，不 import numpy
    panel.py       通用组合：机会校正值的裁剪、加权、失败剔除后重归一
    spatial.py     spatial_domains 面板：CHAOS、PAS、MLAMI（及诊断）与各自随机期望
    score.py       `python -m omicsclaw.ensemble.metrics.score` 入口，在执行环境里跑
  evaluation.py    真值指标（ARI/NMI）；运行路径上的任何模块都不得 import 它
  tool.py          run_skill 工具
```

- **`tuning` 与 `consensus` 不建空文件**（已定 Q16）：包 docstring 写明这两个名字留给 0057/0058。
- **分层**：`ensemble` 只可 import `omicsclaw.schema`、`omicsclaw.tools`、`omicsclaw.skills` 与
  标准库；不得 import `entry`、`engine`、`provider`、`sandbox`（沙箱经 `BashEnvironment` 结构化
  注入）、`runtime`、`autoagent`、`common`。`entry` 是唯一装配它的地方。新增
  `tests/ensemble/test_ensemble_is_a_layer.py`，并把 `"ensemble"` 加进
  `tests/entry/test_entry_is_the_top_layer.py` 的 `_LOWER_LAYERS`。
- **两个运行时、两个解释器**：`tool.py`、`runner.py`、`resources.py`、`execution.py`、`store.py`
  在 agent 进程（Py3.13 或其他 ≥3.11）里跑；`metrics/score.py`、`metrics/spatial.py`、`metrics/panel.py`
  与 `_supervise.py` 在**执行环境**里跑（本机即 `ensemble_python`，沙箱即容器里的 `python`，
  可能是 Py3.11）。因此：`ensemble/__init__.py` 与 `metrics/*` 不得 import `omicsclaw.tools`、
  `omicsclaw.skills`、`omicsclaw.ensemble.tool/runner` 等 agent 侧模块，也不得用 3.12+ 语法；
  `_supervise.py` 只用标准库，按文件路径运行。测试钉住（§5 T8）。
- **重依赖只在子进程**：面板需要 numpy/sklearn/scanpy，只在打分子进程里 import；agent 进程
  `import omicsclaw.ensemble.tool` 不加载 numpy/pandas/scanpy（子进程探针断言）。

### 3.2 `tuning.yaml` schema

位置：`skills/<domain>/<skill>/tuning.yaml`。文件存在是 `run_skill` 可运行该 skill 的必要条件
（已定 Q2）；它声明主脚本（解决 F15）。

```yaml
schema_version: 1
skill: spatial-domains            # 必须等于同目录 SKILL.md 的 name
script: spatial_domains.py        # 相对 skill 目录；必须存在
analysis: spatial_domains         # 指标面板注册键（§3.7）
method_flag: --method             # null 表示单方法 skill
output:
  kind: labels                    # labels | embedding（§3.12）
  labels:
    table: tables/domain_assignments.csv
    id_column: observation        # 缺失时回退到表的第一列（须不是 label_column），见下
    label_column: spatial_domain
  h5ad: processed.h5ad
reference:                        # 打分时从 **输入** h5ad 读的共同参照
  coords_obsm: spatial
  expression_obsm: X_pca
defaults:
  resources: {gpu: none, memory_gb: 32, cpus: 8, timeout_s: 1800}
context:                          # 数据集事实，任何方法可带，不参与搜索
  data_type: {type: categorical, flag: --data-type, choices: [...], default: null}
methods:
  stagate:
    resources: {gpu: preferred, memory_gb: 64}
    params:
      stagate_alpha:  {type: float, flag: --stagate-alpha, low: 0.0, high: 1.0, default: 0.0, priority: 2}
      pre_resolution: {type: float, flag: --pre-resolution, low: 0.05, high: 1.0, default: 0.2, log: true,
                       priority: 3, active_when: {stagate_alpha: {gt: 0}}}
  cellcharter:
    params:
      auto_k_min: {type: int, flag: --auto-k-min, low: 2, high: 10, default: 2, active_when: {auto_k: {eq: true}}}
      auto_k_max: {type: int, flag: --auto-k-max, low: 4, high: 20, default: 10, active_when: {auto_k: {eq: true}}}
    constraints:
      - {lhs: auto_k_min, op: lt, rhs: auto_k_max}
```

**字段规则**（加载器逐条校验，错误信息指名文件与字段路径）：

| 键 | 规则 |
|---|---|
| `schema_version` | 必须为 `1` |
| `skill` / `script` / `analysis` | 非空字符串；`analysis` 必须是已注册面板键 |
| `method_flag` | 字符串或 `null` |
| `output.kind` | `labels` 或 `embedding`；对应子块必填 |
| `output.labels.id_column` | 读表时若该列不存在，回退到第一列，前提是第一列不是 `label_column`；回退在 `trial.json` 里记 `id_column_used`（F18：索引有名字时列名就是索引名） |
| `resources` | `gpu ∈ {none, preferred, required}`；`memory_gb > 0`；`cpus ≥ 1`；`timeout_s > 0`；方法级覆盖 `defaults` 同名项 |
| ParamSpec `type` | `float` / `int` / `bool` / `categorical` |
| `flag` | `--` 开头；不得是 `--input`、`--output`、`--demo` 或 `method_flag` |
| `low` / `high` | 数值型必填，`low < high`，闭区间 |
| `choices` | categorical 必填，非空，元素同类型 |
| `default` | 落在区间/choices 内；`null` 仅允许 `context` 参数（表示不传） |
| `log` | 仅数值型，要求 `low > 0` |
| `priority` | 正整数，1 最先调 |
| `active_when` | 可选，`{同方法内参数: {op: 值}}`，`op ∈ {eq, ne, gt, ge, lt, le, in}`（`in` 的值是列表）；多个键为"且"；条件不满足时该参数**不得给出**、也不渲染；被引用的参数必须存在且不可形成环 |
| `constraints` | 可选列表，`{lhs, op, rhs}`，`op ∈ {lt, le, gt, ge, ne}`，`lhs`/`rhs` 为参数名或字面量；只在两侧参数都活跃时检查；加载时用默认值自检一遍（默认值本身必须满足约束） |
| `note` | 可选短句，展示给模型与 0057 |

**参数校验（`validate_params`）**：只收参数名（snake_case）。未知名、属于别的方法的名、类型
不符、越界、`active_when` 不满足、违反 `constraints` → `SpecError`，信息附该方法搜索空间摘要
（`MethodSpec.summary()`）。**区间是硬约束**（已定 Q3）。校验后用默认值补齐所有活跃参数，
**每个活跃参数都显式渲染**进命令行，脚本的静默默认（F18 的 `n_domains=7`、F20 的
`auto_k_max`）不会隐式生效。bool 渲染为 `--flag true|false`（`str2bool` 接受）；`store_true`
型 flag 用 `switch: true`（本份不需要）。

**`spatial-domains/tuning.yaml` 草案**（数值为草案，实施时逐项对照 `references/parameters.md`
与源码定稿，交付记录写每个区间的依据；**任何区间都不得参考开发数据的真值**）：

| 方法 | `gpu` | 参数（priority 顺序） |
|---|---|---|
| `leiden` | none | `resolution` float [0.1, 2.0] log, 1.0；`spatial_weight` float [0.0, 0.9], 0.3 |
| `louvain` | none | 同 `leiden` |
| `spagcn` | none（F21 已核实 1.2.7 无 GPU 代码） | `spagcn_p` float [0.1, 0.9], 0.5；`n_domains` int [3, 20], 7；`epochs` int [50, 400] log, 100 |
| `stagate` | preferred | `k_nn` int [3, 15], 6；`n_domains` int [3, 20], 7；`stagate_alpha` float [0.0, 1.0], 0.0；`pre_resolution` float [0.05, 1.0] log, 0.2, `active_when: {stagate_alpha: {gt: 0}}`（F19）；`epochs` int [50, 1000] log, 100。不列 `rad_cutoff`（F19） |
| `graphst` | preferred | `n_domains` int [3, 20], 7；`epochs` int [50, 600] log, 100；`dim_output` categorical [32, 64, 128], 64 |
| `banksy` | none | `lambda_param` float [0.0, 1.0], 0.2；`num_neighbours` int [6, 30], 15；`resolution` float [0.1, 2.0] log, 1.0。不列 `n_domains` |
| `cellcharter` | preferred | `auto_k` bool, `false`；`n_domains` int [3, 20], 7, `active_when: {auto_k: {eq: false}}`；`auto_k_min` int [2, 10], 2 与 `auto_k_max` int [4, 20], **10**（= 脚本在默认 `auto_k_min=2` 时的实际取值 `2+8`，F20），二者 `active_when: {auto_k: {eq: true}}`，约束 `auto_k_min < auto_k_max`；`n_layers` int [1, 5], 3 |
| context | — | `data_type` categorical（取值依 `SUPPORTED_SPATIAL_PLATFORMS` 与 `_infer_graphst_data_type` 定稿），默认 `null` |

`n_domains` 区间 [3, 20]、默认 7（脚本自身默认，与数据无关）——已定 Q7。GPU 方法在本机都能
回落 CPU（F19），因此标 `preferred` 而非 `required`；`required` 为将来只能 GPU 的 skill 保留。

### 3.3 试验运行器

**两层 API**：`EnsembleRunner` 是 0057/0059 直接调用的 Python 接口；`run_skill` 是它的工具外壳。
两者共用同一个资源池与面板，"确定性循环"与"agent 自由编排"因此是公平对照。

```python
@dataclass(frozen=True, slots=True)
class Limits:
    timeout_s: float          # 运行上限，不含打分
    memory_gb: float

@dataclass(frozen=True, slots=True)
class TrialSpec:
    skill: str
    method: str
    input: Path                      # 已经过 Workspace.resolve 的绝对路径
    params: Mapping[str, object]     # 已校验、已补默认
    run_id: str
    limits: Limits
    resources: ResourceRequest

class EnsembleRunner:
    def prepare(self, *, skill, method, input, params, run_id=None, timeout_s=None) -> TrialSpec   # 纯校验，失败抛 SpecError
    async def run(self, spec: TrialSpec) -> TrialResult     # 不因 skill 失败而抛；只有取消会传播
    async def fan_out(self, specs, *, required_survivors: int | None = None) -> list[TrialResult]
```

**一次试验的生命周期**：

1. **分配目录**：`(run_id, method)` 锁内分配 `tNNNN`，`mkdir(exist_ok=False)`。首次使用 `run_id`
   时写 `run.json`（skill、输入路径与 sha256、**输入的 obs 列名清单**、`tuning.yaml` 与主脚本
   sha256、面板版本、上限、执行位置与镜像）。同一 `run_id` 再次使用时 skill 或输入 sha256 不同 →
   `SpecError`。
2. **准入**（`stage=admission`）：按 §3.4 决定设备。`gpu=required` 且池中无 GPU → 不起进程，
   `status=failed`，`error="method requires a GPU; none detected (…检测结果…)"`；请求的内存/CPU
   超过池总量 → 同样 `failed`，给出总量。二者都写 `trial.json` 并进 `trials.jsonl`（benchmark 据此
   排除方法），不是工具错误。
3. **排队**：`async with pool.acquire(spec.resources)`，最长 `ensemble_max_queue_s`（§3.5）；超过即
   `status=failed, stage=admission, error="queued longer than …s"`，不起进程；排队期间
   `report_progress("queued …")`。
4. **运行 skill**（`stage=run`）：经 `CommandExecutor` 执行
   `python _supervise.py --timeout T --max-rss-mb M --status <trial>/supervisor.json -- <python> <script> --input <input> --output <trial>/output --method <m> <params…>`。
   **cwd = `<trial>/`**。环境 = 白名单变量（已定 Q11）+ `PYTHONPATH=<repo_root>` +
   `PYTHONDONTWRITEBYTECODE=1` + `CUDA_VISIBLE_DEVICES=<lease 的 GPU 或空串>` +
   `OMP/MKL/OPENBLAS/NUMBA_NUM_THREADS=<lease.cpus>` + **每试验独立的
   `TMPDIR=TMP=TEMP=<trial>/tmp`、`MPLCONFIGDIR=<trial>/tmp/mpl`、`NUMBA_CACHE_DIR=<trial>/tmp/numba`**。
   合并输出写 `<trial>/run.log`。
5. **收集**（`stage=collect`）：退出码 0 且 `output/result.json` 与标签表存在 → 按 §3.2 规则读
   id 列与标签列，写 `<trial>/labels.csv.gz`（`obs_id,label`，已定 Q10）；缺任何一项 → `failed`。
6. **打分**（`stage=score`）：第二条受监督命令
   `python -m omicsclaw.ensemble.metrics.score --trial <trial> --input <input> --analysis <key> --cache <dir>`，
   同一租约、`score_timeout_s=120`，写 `<trial>/metrics.json`。失败 → `failed`（打不了分不算成功）。
7. **保留**（§3.6），删除 `<trial>/tmp/`（`keep_all` 时保留），写 `trial.json`、追加 `trials.jsonl`。

**状态**：`ok` / `failed` / `timeout` / `memory_exceeded` / `cancelled`；`stage ∈ {admission, run,
collect, score}`。校验错误（`SpecError`）不是试验，不建目录，由工具层报 `is_error`。

**`TrialResult` 字段**：`status, stage, run_id, method, trial, output_dir, params, command, exit_code,
queued_s, wall_s, peak_mem_gb, mem_metric ("pss" | "rss"), lease_gpu (str | null), device, gpu_mem_peak_mb,
degraded ("" | "no_gpu"), metrics, score, h5ad, error (日志尾部 ≤ 2 KiB), log, started_at, ended_at,
id_column_used, provenance {script_sha256, tuning_sha256, input_sha256, python, image}`。

**`device` 取实际设备，不取租约**：`_supervise.py` 每 5 s 执行一次
`nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`，本进程组内任一 pid 出现即视为
用了 GPU，记 `gpu_mem_peak_mb`；`device = "cuda:<lease_gpu>"` 当且仅当观测到 GPU 使用，否则 `"cpu"`
（租了卡却没用上——例如方法内部回落 CPU——会如实显示为 `cpu`，并与 `lease_gpu` 并列便于排查）。
`nvidia-smi` 不可用时，退而读 skill `result.json` 的 `summary.device`（`_lib/domains.py` 的 GNN 方法会写），
再没有则记 `"unknown"`；`TrialResult` 用 `device_source ∈ {observed, skill, unknown}` 标明来源。

**执行路径**（`execution.py`）：

- `LocalExecutor`：`spawn_group_leader(create_subprocess_exec(..., cwd=trial, start_new_session=True, stdout/stderr=log, stdin=DEVNULL))`，
  取消时 `killpg`（F10）。
- `SandboxExecutor(environment: BashEnvironment)`：argv 经 `shlex.quote` 拼成
  `env K=V … python _supervise.py …`，以 `cwd=<trial>` 交给 `run_bash`（F8 无 env 参数）。
- 按 `SandboxBinding.environment` 二选一，与 `bash` 同源（F9）。benchmark 用 `sandbox_required=true`
  + 固定 `sandbox_image`。

**`_supervise.py`**（stdlib-only）：自己做进程组组长，子进程留在同组；每 1 s 扫 `/proc` 汇总本组
（除自身）内存，记峰值；**计量用 PSS**（读 `/proc/<pid>/smaps_rollup` 的 `Pss:` 行，共享页按份摊，
多进程 worker 不重复计）；该文件不可读（内核 < 4.14、权限或容器限制）时**回退 RSS**（`/proc/<pid>/status`
的 `VmRSS`），并在 `supervisor.json` 记 `mem_metric`。超内存 → `SIGKILL` 整组，`memory_exceeded`；
超时 → `SIGTERM`、5 s 后 `SIGKILL`，`timeout`；自身收到 `SIGTERM` → 杀整组后退出；Linux 上给子进程设
`PR_SET_PDEATHSIG`（ctypes）。另按上段做 GPU 使用观测。结束写
`supervisor.json {status, exit_code, wall_s, peak_mem_mb, mem_metric, gpu_used, gpu_mem_peak_mb}`。

**`fan_out`**：`asyncio.gather` 各 `run`，结果按输入顺序；单个失败不影响兄弟（F27）；
`required_survivors` 由调用方给，不满足抛 `InsufficientSurvivors`；取消时杀掉所有在途试验、等待回收。

### 3.4 资源池与 GPU 检测

```python
@dataclass(frozen=True, slots=True)
class ResourceRequest:
    gpu: Literal["none", "preferred", "required"]
    memory_gb: float
    cpus: int

class ResourcePool:
    def __init__(self, *, gpu_ids: Sequence[str], slots_per_gpu: int, memory_gb: float, cpus: int)
    def admit(self, request) -> Admission   # 决定设备：gpu / cpu（降级）/ 拒绝（required 无 GPU、内存或 CPU 超总量）
    def acquire(self, admitted) -> AsyncContextManager[Lease]   # Lease.gpu: str | None
```

**GPU 检测（D3）**：`ensemble_gpus` 取值：
- `""`（默认）= **自动检测**，启动时做一次：本机执行 `nvidia-smi --query-gpu=index --format=csv,noheader`
  （命令不存在或失败 → 0 张），若进程已设 `CUDA_VISIBLE_DEVICES` 则取交集；沙箱在跑时在**容器内**
  经 `environment.run_bash` 执行同一命令——`sandbox_gpus` 为空时容器看不到 GPU，直接记 0 张并
  告警"沙箱未透传 GPU（`--sandbox-gpus`）"。检测在 `open_app` 里完成（需事件循环与已启动的沙箱）。
- `"none"` = 不用 GPU；逗号列表（如 `0,1,2,3`）= 以配置为准，不检测（沙箱下是容器内可见编号）。
- 启动日志：`ensemble gpus=4 (detected)` / `(configured)` / `0 (none detected: …)`。

**准入规则**：`fits()` 不再因 GPU 拒绝请求。
| 方法 `gpu` | 池中有 GPU | 池中无 GPU |
|---|---|---|
| `none` | CPU，`CUDA_VISIBLE_DEVICES=""` | CPU |
| `preferred` | 占一个 GPU 槽位 | **降级** CPU：`CUDA_VISIBLE_DEVICES=""`，`device=cpu`，`degraded="no_gpu"` |
| `required` | 占一个 GPU 槽位 | `failed`，`stage=admission`，原因含检测结果 |

所有不占 GPU 的试验都设 `CUDA_VISIBLE_DEVICES=""`，杜绝多个试验默认挤到 0 号卡。

**调度**：一次性原子申请（GPU 槽位 + 内存 + CPU），不会持有一部分等另一部分，故不死锁。
**不推迟队头的 backfill**：队头 H 不满足时，后续请求 R 仅当对每个维度 d 都有
`R_d ≤ max(0, free_d − H_d)` 才可插空启动——即当前空闲资源中队头需要的那部分永远不被别人拿走，
队头只等真正短缺的那个维度（通常是 GPU），CPU-only 小试验可利用剩余内存/CPU。只为队头一个
请求做预留；预留随队头变化而重算。

每个 `AgentApp` 一个池，所有会话、所有 `run_skill`、0057 的 `optimize_params` 共享；**不跨进程**
（R3）。默认值：`slots_per_gpu=1`；`cpus` = `os.cpu_count()`，沙箱设了 `--cpus` 时取较小者。

**池可分配内存（含余量，N5 附加）**：

```
base      = 沙箱在跑时为容器内存上限（sandbox_memory 解析值），否则为 MemTotal × 0.8
pool_mem  = base − tmpfs_size − shm_size − ensemble_reserved_gb        （本机路径 tmpfs_size = shm_size = 0）
```

`ensemble_reserved_gb` 默认 **64**，留给 `bash`、打分以外的系统进程、Python 解释器本身与 page cache 压力。
tmpfs 与 shm 都记入容器内存 cgroup，故按上限整额扣除。本机默认值：沙箱 `1557 − 64 − 128 − 64 = 1301` GiB；
本机路径 `1557 − 64 = 1493` GiB。`ensemble_memory_gb` 显式给出时取 `min(给定, pool_mem)`；结果 ≤ 0 → 启动报错。
这保证"所有在跑试验的内存上限之和 + tmpfs/shm 满载 + 预留"不超过容器上限，试验级上限先于容器 OOM
触发——前提是 `bash` 与系统进程的实际用量不超过预留，这一点**无法保证**（`bash` 不受池约束），见 R11。

### 3.5 时间与内存上限

- **每试验内存上限**：方法 `resources.memory_gb`（可被 `ensemble_memory_gb_cap` 统一压低），既是
  池的记账量又是 `_supervise.py` 的硬上限；超了就是 `memory_exceeded`。GPU 显存靠"每卡一个试验"隔离。
- **每试验时间上限**：`timeout_s = min(调用方给的, 方法 resources.timeout_s, ensemble_max_trial_s)`；
  `ensemble_max_trial_s` 默认 **7200 s**（配置总上限）。打分另有 `score_timeout_s = 120 s`。
- **引擎超时（审核意见 4）**：`run_skill` 从进入到返回整体处于 `pause_tool_timeout()` 之内（F4），
  引擎的 600 s 每调用超时不再切断长试验；工具自身用 `asyncio.timeout(timeout_s + score_timeout_s + 60)`
  从**准入后**开始兜底（排队时间不计，排队有界：前面每个试验都受自己的上限约束）。兜底触发时
  杀掉进程组，`status=timeout`。
- **排队上界**：`ensemble_max_queue_s` 默认 **7200 s**（等于一个最长试验），超过即准入失败（§3.3 第 3 步）。
  因此**一次 `run_skill` 调用**的墙钟上界是
  `T_call = ensemble_max_queue_s + ensemble_max_trial_s + score_timeout_s + 60`，默认 ≈ **4 h 3 min**；
  一轮内并发的 N 个调用同批执行，**同批墙钟上界仍是 `T_call`**，不是 `N × 7200 s`——每个调用的排队时间
  各自受 `ensemble_max_queue_s` 约束，排不上的如实失败。一次交换最多 `max_turns` 轮，最坏上界为
  `max_turns × T_call`，要更紧的上界用 `turn_timeout_s`（下一条）。
- **轮级超时 `turn_timeout_s`（F35）**：默认 `None`，不影响长试验。一旦设了数值，它从外面取消整轮，
  `run_skill` 的 `pause_tool_timeout` 管不到它：在途试验收到取消，运行器杀掉进程组，结果为 `cancelled`
  （`trial.json` 以 shield 方式尽力写入）。处理：(1) 启动时若 `turn_timeout_s` 非空且小于 `T_call`，记一条告警
  写明两数；(2) 工具描述写明"一轮可能长达数小时（含排队），部署的轮级超时会取消在途试验"；(3) benchmark
  （0059/0060）要么不设 `turn_timeout_s`，要么设为不小于 `T_call`。不在 0056 里自动改写该配置。
- **消融公平（给 0060 的约束）**：基线组没有 `run_skill`，只能用 `bash` 跑同样的脚本，而 `bash`
  的上限是 `tool_timeout_s − 15 s`（F3）。0060 两组必须把 `tool_timeout_s` 设为不小于
  `ensemble_max_trial_s + score_timeout_s + 60 + 15`，否则基线组会因更短的时限输给实验组。
- `EnsembleRunner` 直接调用（0057/0059）只受 `Limits`。

### 3.6 产物存储与保留

```
<workspace>/ensemble_runs/
  _cache/<input_sha256>/                 面板的参照缓存（§3.7），与试验无关
  <run_id>/
    run.json    trials.jsonl
    <method>/
      best.json                          {trial, score}
      t0001/
        trial.json   labels.csv.gz   metrics.json   supervisor.json   run.log（截断到 256 KiB）
        tmp/         每试验临时目录；结束后删除
        output/      skill 自己的输出目录；保留后只剩 result.json（与最佳试验的 processed.h5ad）
```

- 默认删除 `output/` 下除 `result.json` 外的全部（图、表、figure_data、report.md、reproducibility）。
  **h5ad**：`(run_id, method)` 锁内比较 `score`，更优则删旧最佳的 h5ad、保留新的并更新 `best.json`，
  否则删自己的；失败试验一律删；平分保留先到者。`ensemble_keep_all=true` 时什么都不删。
- `run_id`：调用方可给（`^[a-z0-9][a-z0-9_-]{0,63}$`），否则生成 `rYYYYMMDD-HHMMSS-xxxx`。
- 工具描述写明：这些目录不保留图和报告，面向用户的单次分析仍按 `SKILL.md` 用 `bash` 跑。

### 3.7 统一指标面板与评估模块

#### 3.7.1 文献核查（D2）

| 来源 | 核查结果 |
|---|---|
| SpatialPCA（Shang & Zhou, *Nat Commun* 13:7203, 2022）— CHAOS、PAS 的出处 | 论文 <https://www.nature.com/articles/s41467-022-34879-1>；官方 R 实现 `fx_CHAOS`/`fx_PAS`/`fx_1NN`/`fx_kNN` 在 <https://github.com/shangll123/SpatialPCA/blob/main/R/SpatialPCA_utilties.R>（:457-530，已用 `gh api` 取得全文核对） |
| SDMBench（Yuan et al., *Nat Methods* 2024, "Benchmarking spatial clustering methods with spatially resolved transcriptomics data"） | 论文 <https://www.nature.com/articles/s41592-024-02215-8>；Python 实现 `_compute_CHAOS`/`_compute_PAS`/`fx_1NN`/`fx_kNN` 在 <https://github.com/zhaofangyuan98/SDMBench/blob/main/SDMBench/SDMBench.py>（已取得源码核对），是 SpatialPCA R 版的移植 |
| MLAMI（NicheCompass） | <https://github.com/Lotfollahi-lab/nichecompass/blob/main/src/nichecompass/benchmarking/mlami.py>（已取得源码核对） |
| BASS | 未发现 CHAOS/PAS 出自 BASS；两者的原始实现在 SpatialPCA 包内，SDMBench 引用并移植。未取得 BASS 原文逐页核对，此点只作"未见"而非"否定"记录 |

**文献定义（以代码为准）**：

- **CHAOS**：坐标先逐轴标准化（R `scale()`，样本标准差；SDMBench 用 `StandardScaler`，总体标准差，
  差一个 `√(N/(N−1))` 因子）；对每个簇，求簇内每点到**同簇最近邻**的欧氏距离并求和；各簇之和除以
  **全部点数 N**。**越低越好**，无上界、量纲依赖点密度。小簇处理两版不同：SDMBench 跳过点数 ≤ 2 的簇；
  SpatialPCA R 版的 `length(location_cluster)==2` 检查的是矩阵元素个数，实际只跳过单点簇（2 维坐标
  下单行即 2 个元素）。被跳过的点贡献 0 但仍计入分母 N。
- **PAS**：对每点取 10 个空间最近邻（不含自身，**原始坐标，不标准化**）；若与自身标签不同的邻居数
  **> k/2 = 5**（即 ≥ 6）则为异常点；PAS = 异常点比例。**越低越好**，[0,1]。
- **MLAMI（原始）**：比较**潜空间 kNN 图**的 Leiden 划分与**空间 kNN 图**的 Leiden 划分，在
  `min_res=0.1…max_res=1.0` 共 3 个分辨率的所有组合对上取 AMI 最大值；评的是潜空间表示，不是标签。

**旧实现（F24）的偏差**：

| 旧指标 | 与文献的关系 | 处置 |
|---|---|---|
| `chaos` | **不是 CHAOS**：它是"k=10 近邻中同标签比例"（越高越好），文献 CHAOS 是"同簇最近邻距离均值"（越低越好）。二者方向相反、量纲不同 | 按文献重写 CHAOS；旧量改名 `knn_agreement`，降为诊断 |
| `pas` | 阈值等价：旧式"同标签比例 < 0.5"在 k=10 时即"异类邻居 ≥ 6"，与 `> k/2` 相同；坐标不标准化也相同 | 保留定义，加机会校正 |
| `mlami` | 改编版：用**标签**代替潜空间 Leiden，只扫空间侧的分辨率。AMI 本身已对机会校正。它衡量"标签与某一尺度的空间 Leiden 划分的一致程度"，不是 NicheCompass 的 MLAMI | 保留计算，改名 `spatial_leiden_ami`，论文里如实描述为改编；原名只在文档中注明出处 |

本仓库的 CHAOS 实现：簇内最近邻用 `scipy.spatial.cKDTree`（与 O(N²) 距离矩阵结果相同）；标准化
用总体标准差（与 SDMBench 一致，便于与其数字比较）；小簇规则跟 SDMBench（跳过 ≤ 2 点的簇），
并在 `metrics.json` 记 `chaos_skipped_spots`。这三处选择待复审确认（§7 N1）。

#### 3.7.2 机会校正（D1）

随机基线统一定义为**保持各簇大小不变的标签随机置换**（每个簇大小 n_c，比例 p_c = n_c/N）。
每个指标都保留原始值 `raw`、随机期望 `expected`、校正值 `adjusted`；计分用 `adjusted` 裁剪到 [0,1]。

| 指标 | 原始方向 | 随机期望的推导 | 校正值（1 = 完美，0 = 随机水平，<0 劣于随机） |
|---|---|---|---|
| PAS | 低好 | 置换下，标签为 c 的点其 10 个邻居里同标签数 X_c ~ 超几何(N−1, n_c−1, 10)（精确，不是二项近似）；异常 ⇔ X_c ≤ 4。`E[PAS] = Σ_c p_c · P(X_c ≤ 4)` | 转成"正常率"再套 kappa：`(E[PAS] − PAS) / E[PAS]`；`E[PAS]=0`（例如单簇）时记 `degenerate` |
| CHAOS | 低好，无上界 | 无闭式；用 **B 次**（默认 B=10，seed 固定）保持簇大小的置换估计 `E_rand` 并记标准误；理论下界 `d_min` = 同一套小簇规则下"簇内最近邻 = 全局最近邻"时的值，即各点全局最近邻距离之和（跳过小簇的点）除以 N | kappa 式的距离版：`(E_rand − CHAOS) / (E_rand − d_min)`；分母 ≤ 0（例如单簇时三者相等）记 `degenerate` |
| MLAMI（`spatial_leiden_ami`） | 高好 | AMI 已按置换模型的期望互信息校正 | 直接用 AMI，负值裁到 0 |
| `knn_agreement`（诊断） | 高好 | 置换下同标签邻居比例的期望 `Σ_c p_c · (n_c−1)/(N−1)`（≈ Σp²） | `(obs − E)/(1 − E)` |

默认权重不变：`CHAOS 0.4 / PAS 0.2 / MLAMI 0.4`（作用于校正值）。诊断（权重 0）：
`knn_agreement`（原始与校正）、`silhouette_pca`（输入 `X_pca` 上，采样 5000，`random_state=0`，
映射 `(s+1)/2`）、`n_labels`、`largest_label_frac`。`n_labels < 2` → `degenerate=true`、`score=0`。

**机会校正能做什么、不能做什么**（写进测试 docstring）：它**大部分减弱**、但不能完全消除"簇越少越容易
拿高分"的偏差（例如 K=2 的随机合并不再因簇少而得高分），并且**不能**让纯空间指标识别"真实的"簇数——
把一个真实区域在空间上连续地再切成两半，校正后的空间指标依然很高。区分过切需要表达空间的证据
（silhouette 等），这正是 T3b 偏差研究要量化、由 0057 与 owner 决定是否加权的问题。

**校正后 PAS 在干净数据上仍偏向 K=2 的结构性原因**（预期，由 T3b 量化）：PAS 只数"10 个近邻中异类 ≥ 6"
的点。空间连续的划分里，直线边界两侧的点看到的大致是一半对一半，达不到 6 个异类，所以干净数据上的观测
PAS 几乎只来自**多区域交汇处与窄条区域**的点；区域越多，交汇点与窄区越多，观测 PAS 随 K 上升。与此同时，
随机期望 `E[PAS]` 在 K=2（均衡）时约为 0.38，K=3 约 0.79、K=5 约 0.97（二项近似 `P(Bin(10, 1/K) ≤ 4)`），此后几乎不变，分母的变化远小于分子。于是校正值
`1 − PAS/E[PAS]` 在 K=2 时最接近 1。这是 PAS 定义（只惩罚"多数异类"点）的性质，不是校正公式的缺陷；
机会校正只去掉"随机水平随 K 变化"这一部分。CHAOS 的校正同理可能残留偏差，二者都由 T3b 如实报告。

#### 3.7.3 合成数据偏差研究（D1，T3b）

`tests/ensemble/test_panel_bias.py`（快速版进默认套件）+ 同文件里的报告函数（完整版，输出表格进
交付记录）：

- 生成：规则网格或 Poisson 点（N≈5000），K* 个真实空间区域（条带与 Voronoi 两种几何，K* ∈ {4, 7, 10}），
  每个区域有自己的表达均值（用于诊断 silhouette）。
- 候选标签：真实区域的**合并**（K = 2…K*−1，每次合并相邻区域）、真实标签、**空间连续的再切分**
  （K = K*+1…2K*）、**随机置换**（各 K）。
- **标签噪声施加于所有候选**：先构造无噪声候选，再对每个候选（合并、真实、再切分；随机置换本身即
  全噪声，不再加）以同一噪声率 {0, 5%, 15%} 和同一随机种子序列把对应比例的点改为该候选中另一个随机
  标签——噪声只作用于真实标签时，合并与再切分会因"更干净"而占便宜。
- 对每个候选计算全部原始值、期望、校正值与面板分数。报告：
  - 每个配置下**新面板**（§3.7.2 校正值、0.4/0.2/0.4）与**旧面板**的 argmax K。**旧面板**明确定义为
    第一版之前 `runtime/consensus/spatial_panel.py` 的组合：旧 `chaos`（k=10 同标签比例）、旧 `pas`（取
    `1−pas`）、旧 `mlami`（负值裁 0），权重 0.4/0.2/0.4，逐项裁到 [0,1] 后加权平均。
  - **平分规则**：分数差 ≤ 1e-9 视为平分，报告 argmax **集合**，而不是取第一个；网格数据上的平分因此
    不会被误读为"偏向最小 K"。
  - 各指标（raw 与 adjusted）对 K 的 Spearman 相关；随机置换的校正值分布（应以 0 为中心）。
  - **`spatial_leiden_ami` 单独一栏**（N3 附加）：它自己的 argmax K 集合，以及参照 Leiden 在每个分辨率
    （0.1、0.55、1.0）下得到的簇数——AMI 的最优 K 受参照划分簇数牵引，需要看到这组数才能解读。
- 快速版断言（方向性，不设编造的阈值）：(1) 随机置换的 CHAOS/PAS/`knn_agreement` 校正值的均值绝对值
  < 0.05（B 次重复）；(2) 真实标签的各校正值高于同 K 的随机置换。第一版的"原始面板 argmax 在 K=2、
  校正后不在 K=2"**降为报告项**，不作断言（干净网格上平分与上段所述 PAS 的结构性偏差都会让它假失败）。
  完整报告的数字由 owner 过目。
- **门槛**：偏差报告经 owner 过目之前 0057 不开工（§6 第 9 条、§3.13）。

#### 3.7.4 其余

- **注册表**：`analysis` 键 → `PanelDef(metrics, compute, version)`；`MetricDef` 取旧形状（名称、方向、
  权重、描述）并加 `chance_corrected: bool`。`metrics.json` 含 `raw/expected/adjusted/weights/score/
  errors/degenerate/n_obs/n_labels/…` 与 `panel_version = "spatial_domains/2"`。
- **参照缓存**：空间 kNN 图、空间 Leiden 划分、全局最近邻距离只依赖坐标，按 `(input_sha256, 面板版本,
  参数)` 缓存到 `ensemble_runs/_cache/<sha>/`（临时文件 + `os.replace`）。CHAOS 的置换期望依赖簇大小，
  不缓存。
- **打分子进程**读 `labels.csv.gz` 与输入 h5ad（`backed='r'`，只取参照 `obsm`），按 obs id 对齐；标签的
  obs 集合必须等于输入的 obs 集合，否则失败。
- **取舍**：local purity 并入 `knn_agreement`（F25，同一量）；silhouette 改在共同的输入 `X_pca` 上算
  （方法各自 embedding 上的 silhouette 不可比）；Calinski-Harabasz 删除（无理论上界）。
- **许可**：从 `spatial_metrics.py` 复制 MLAMI 相关代码时原样保留 nichecompass 的 BSD-3 声明；CHAOS/PAS
  按文献定义自行实现：SpatialPCA 的 `DESCRIPTION` 声明 `GPL (>= 3)`，SDMBench 仓库未声明任何许可证
  （GitHub API `license` 为空，即默认保留全部权利），二者代码都**不复制**，只实现公开的数学定义。
- **评估模块**（`evaluation.py`）：`ari`、`nmi`，按 obs id 对齐、忽略真值缺失。隔离：(1) 结构测试：
  `runner`、`tool`、`space`、`store`、`execution`、`resources`、`metrics.*` 不 import `evaluation`；
  (2) `run_skill` 没有接收真值的参数，`metrics.json` 不含真值指标；(3) §3.9 的防泄漏前提。

### 3.8 `run_skill` 工具与审批语义

**schema**（`skill` 在 `required` 第一位，规则文件可写 `run_skill(spatial-domains)`，F6）：

```json
{
  "type": "object",
  "properties": {
    "skill":     {"type": "string"},
    "method":    {"type": "string"},
    "input":     {"type": "string", "description": "workspace path of the input .h5ad"},
    "params":    {"type": "object"},
    "run_id":    {"type": "string"},
    "timeout_s": {"type": "number"}
  },
  "required": ["skill", "method", "input"],
  "additionalProperties": false
}
```

**policy**（声明而非默认）：`risk_level=MEDIUM`、`approval_mode=AUTO`、`read_only=False`、
`concurrency_safe=True`、`writes_workspace=True`、`touches_network=False`、`allowed_in_background=False`、
`tags={"skills","ensemble","execution"}`。

**审批语义（D3 要求写清）**：
- 放行与否只由权限闸门决定（F6），与设备无关：GPU 运行、CPU 降级、沙箱或本机，都是同一个 `AUTO`
  决定；降级**不会**触发询问，也不会被当作错误，只在结果里记 `degraded`。
- `read-only` 模式拒绝（不声明 `read_only`）；`bypass-all`、`auto-approve` 放行；规则文件可对它写
  `allow`/`ask`/`deny`（按 `skill` 匹配）；Desktop 上不会卡在审批（F7）。
- `gpu=required` 无 GPU、资源超总量 → 是**试验结果**（`status=failed, stage=admission`），不是审批
  拒绝，也不是工具错误。

**校验**（`ToolArgumentError` → `is_error=True`）：skill 不在索引或没有 `tuning.yaml`；方法不存在；参数
不合法（附摘要）；`input` 不过 `Workspace.resolve` 或不是文件；`run_id` 格式错或与既有 run 的 skill/输入
不符；`timeout_s` 超过 `ensemble_max_trial_s`。

**返回**：紧凑 JSON（`status, stage, run_id, method, trial, output_dir, params, metrics{score + 各分量的
raw/adjusted + n_labels}, wall_s, queued_s, peak_mem_gb, mem_metric, lease_gpu, device, device_source, degraded, h5ad, error, log`）。skill 跑失败
作为普通 Observation 返回（`is_error=False`），与 `bash` 对非零退出码的处理一致。

**描述**：由 `TuningCatalog` 在挂载时渲染一次（部署内字节稳定）：用途（并行比较方法/参数，一次调用
一个试验，同一轮多个调用并行）、可用 skill 与方法名、`run_id` 用法、产物只保留标签/指标/`result.json`、
面向用户的报告仍用 `bash`、失败与降级会如实报告；并明写**一轮可能长达数小时（含排队）**，给出当前部署的
`T_call` 数值，以及"部署设置的轮级超时会取消在途试验"（§3.5）。

**不改 `CLAUDE.md`**（F32）：全部指引只放在工具描述里，开关一关就整体消失。**子代理**：`run_skill`
不进 `_WITHHELD_FROM_SUB_AGENTS`，前台子代理可用，共享资源池。

### 3.9 真值防泄漏（审核阻断 1）

- **输入只含非真值 obs 列**：`run_skill`/`EnsembleRunner` 的输入 h5ad 由数据准备步骤生成，`obs`
  只保留列白名单（spatial-domains 的冒烟与 0059：只留 `batch`；`cell_type` 等任何可能用于构造
  区域标签的列一律删除）。运行器把输入的 obs 列名写进 `run.json`，benchmark 驱动据此机械审计。
- **防泄漏前提**：`sandbox_required=true` 且**原始数据集路径（含真值）不在 workspace 内、不挂载进
  容器**（不出现在 `sandbox_mounts`）。无沙箱时 `bash` 能读本机任何文件，防泄漏不成立。
- 容器只看得到 workspace、只读的 `omicsclaw/` 与 `skills/`（§3.10）；`.env` 与 `.omicsclaw/` 被遮蔽。benchmark 的
  workspace 不得是仓库根，仓库里也不得存放真值文件。
- 这两条是 **0059/0060 的硬约束**（§3.13）；0056 的冒烟遵守第一条，并在交付记录注明本机无 docker、
  第二条无法在本机验证。

### 3.10 沙箱：代码可见性、自检与资源默认值

**代码可见性（与 `ensemble` 开关解耦）**：`repo_root = skills_root().parent`。只要沙箱开启且
`repo_root/omicsclaw/` 与 `repo_root/skills/` 都存在，`AppConfig.sandbox_config()` 就**无论 `ensemble` 开关
如何**都把下列路径以只读、同路径挂进容器——消融基线组（`ensemble=false`）里 `bash` 看到的 skill 代码与
实验组完全相同，0060 两组公平：

| 挂载 | 理由 |
|---|---|
| `<repo_root>/omicsclaw/` | skill 脚本 `import omicsclaw.common…`；`_supervise.py` 与打分模块也在其中 |
| `<repo_root>/skills/` | skill 脚本本身与 `skills.<domain>._lib`（脚本把 `repo_root` 插进 `sys.path`，F37） |

**不挂**整个仓库根，也不挂 `examples/`、`scripts/`（只在 `--demo` 路径使用，`run_skill` 从不传 `--demo`，F37）、
`pyproject.toml` 等其余文件。容器里 `PYTHONPATH=<repo_root>` 仍有效：Docker 会为挂载点创建空的父目录。
某路径已被 workspace 挂载覆盖（workspace 就是或包含 `repo_root`）时不重复挂载。镜像自带代码时用
`sandbox_code_in_image=true` 关闭这两项挂载，自检仍要通过。

**`.env` 与 `.omicsclaw/` 不进容器**：它们只会经 workspace 挂载进入（workspace 为仓库根或其中含这两者时）。
`run_arguments` 在它们存在时追加遮蔽：`--volume /dev/null:<workspace>/.env:ro` 与
`--tmpfs <workspace>/.omicsclaw:ro,size=1m`（容器内看到空文件与空目录；宿主上的 agent 进程照常读写真实
文件）。这一改动同样作用于 `bash`，属于收紧。benchmark 另要求 workspace 不是仓库根（§3.9、§3.13）。

**启动自检**（`open_app` 中、沙箱启动与 GPU 检测之后；本机路径同样执行）：在执行环境里运行

```
<ensemble_python> -c "import sys; assert sys.version_info >= (3, 11);
  import numpy, scipy.spatial, scipy.stats, pandas, h5py, anndata, sklearn.neighbors, sklearn.metrics, scanpy, igraph;
  import omicsclaw.ensemble.metrics.score"
test -f <repo_root>/omicsclaw/ensemble/_supervise.py
```

import 清单即打分路径实际用到的全部依赖：`numpy`；`scipy.spatial`（`cKDTree`，CHAOS/PAS 近邻）；
`scipy.stats`（`hypergeom`，PAS 期望）；`pandas`（读 `labels.csv.gz`）；`h5py`、`anndata`（`backed='r'` 读输入）；
`sklearn.neighbors`、`sklearn.metrics`（AMI、silhouette）；`scanpy`（`pp.neighbors`、`tl.leiden`）；`igraph`
（`tl.leiden(flavor="igraph")`）。新实现**只用 `flavor="igraph"`**，不保留旧代码在 `TypeError` 时回退到
`leidenalg` 的分支（F38），所以 `leidenalg` 不在清单里。另对每个带 `tuning.yaml` 的 skill 检查主脚本存在。

**失败时（D6）**：`ensemble` 被**显式**设为 `true` → 启动报错（`AppConfigError`，附失败命令的输出）；
`ensemble` 未设置（默认开启）→ 记一条 warning（同样附输出与"设 `--ensemble false` 可消除此告警"），**不挂载**
ensemble 相关工具（本份即 `run_skill`），其余照常启动。已定 Q12 的"启动时检查解释器可 import"即此步。

**沙箱默认资源（D4）**——作用于整个容器（`bash` 同享），全部可配置：

| 设置 | 现默认（F33） | 新默认 | 依据 |
|---|---|---|---|
| `sandbox_memory` | 不设（无上限） | `auto` = `MemTotal × 0.8`，本机 ≈ **1557g** | 留 20% 给宿主与 page cache；资源池从它再扣除 tmpfs、shm 与预留（§3.4），使试验级上限在容器 OOM 之前触发——前提是 `bash` 等池外用量不超过预留，这一点不能保证（R11） |
| `sandbox_cpus` | 不设（无上限） | 保持**不设** = 全部 104 核 | 已是最大；线程数由每试验的 `*_NUM_THREADS` 控制 |
| `sandbox_tmpfs_size`（`/tmp`） | `1g` | **`64g`** | tmpfs 只在写入时占内存；试验的 `TMPDIR` 已指向磁盘上的试验目录，64g 覆盖仍直接写 `/tmp` 的库（R `tempdir`、joblib） |
| `sandbox_shm_size`（新增，`--shm-size`） | Docker 默认 64 MiB | **`128g`** | PyTorch DataLoader、joblib/loky 内存映射依赖 `/dev/shm`；64 MiB 下并发 GPU 试验会报 bus error；128g 不到内存的 7% |
| `sandbox_pids_limit`（新增配置项） | `4096`（含线程） | **`65536`** | pids 计线程；13 个并发试验 × 每个 BLAS/OMP/torch/numba 多线程池 × 若干进程，4096 易触顶 |
| `sandbox_nofile`（新增，`--ulimit nofile=`） | 镜像默认 | **`65536`** | 并发读写 h5ad、多进程 joblib 与 torch 需要大量文件描述符 |
| `sandbox_gpus` | 不设 | 保持**不设**（需显式 `all` 或 `device=…`） | GPU 透传是安全姿态选择，不随 ensemble 自动打开；未设时 GPU 检测记 0 张并告警 |

`auto` 在 entry 层解析（读 `/proc/meminfo`），`omicsclaw/sandbox` 包仍不读环境；`SandboxConfig` 增加
`shm_size`、`nofile` 字段，`run_arguments` 追加对应参数（`--shm-size`、`--ulimit nofile=N:N`）。

### 3.11 装配与配置

| 字段 | 默认 | 含义 |
|---|---|---|
| `ensemble` | 未设置（= 开启） | 挂载/不挂载 `run_skill`（将来连同 `optimize_params`、`run_consensus`）。类型 `bool \| None`：`None` 表示默认开启，用来区分 D6 的"显式开启"与"默认开启" |
| `ensemble_gpus` | `""` | `""` 自动检测；`none`；或逗号列表（执行环境内编号） |
| `ensemble_slots_per_gpu` | `1` | 每卡并发试验数 |
| `ensemble_memory_gb` | `0`（= §3.4 公式的 `pool_mem`） | 池的内存总量；显式值取 `min(给定, pool_mem)` |
| `ensemble_reserved_gb` | `64` | 池外预留（`bash`、系统进程、page cache），§3.4 |
| `ensemble_cpus` | `0`（= `os.cpu_count()`，沙箱上限取小） | 池的 CPU 总量 |
| `ensemble_memory_gb_cap` | `0`（不压低） | 单试验内存上限的统一上限 |
| `ensemble_max_trial_s` | `7200` | 单试验运行时间总上限 |
| `ensemble_max_queue_s` | `7200` | 单试验排队上限，超过即准入失败（§3.5） |
| `ensemble_keep_all` | `false` | 保留全部产物 |
| `ensemble_python` | `""`（本机 = 本进程 `sys.executable`，容器 = `python`） | 运行 skill 与打分的解释器 |
| `sandbox_code_in_image` | `false` | 沙箱镜像自带代码时关闭 `omicsclaw/`、`skills/` 的自动挂载（与 `ensemble` 无关，§3.10） |
| `sandbox_shm_size` / `sandbox_pids_limit` / `sandbox_nofile` | 见 §3.10 | 新增沙箱项；`sandbox_memory`、`sandbox_tmpfs_size` 改默认 |

全部经 `_Option`（flag + `OMICSCLAW_*` 环境变量），同步 `.env.example` 与 `tests/test_env_example.py`。

装配：`build_ensemble(config, skills, binding)`（开关关、`skills_index=off` 或无合法 `tuning.yaml` 时返回
`None`，后两者记 info 日志；坏 `tuning.yaml` 进 `TuningCatalog.skipped` 并告警）。`open_app` 的顺序：
启动沙箱 → GPU 检测与启动自检（§3.10，D6 决定失败时报错还是只告警并不挂载）→ `build_app`。
`foundation_tools(..., ensemble=runner)` 把 `run_skill` 放在 `memory_write` 之后，也就是 `foundation_tools`
返回的最后一项（F36）；`build_app` 随后照旧追加 MCP 工具、最后注册 `task`。**完整顺序**：
`read_file, write_file, edit_file, bash, web_fetch, web_search, use_skill, plan_write, memory_search,
memory_write, run_skill, <mcp__*…>, task`。启动日志加 `ensemble=on|off gpus=<n> (detected|configured)`；
`turn_timeout_s` 小于 `T_call` 时加一条告警（§3.5）。

**消融（审核意见）**：T0 在改动前生成 golden 快照
`tests/entry/golden/ensemble_off_prompt.txt`（`build_prompt` 渲染的系统提示）与
`tests/entry/golden/ensemble_off_tools.json`（`registry.available_tools()` 的定义序列化，按固定测试配置）。
固定测试配置不含 MCP，故 golden 工具序列是 `…, memory_write, task`。测试断言：`ensemble=false` 时两者与
golden 逐字节相等；`ensemble=true` 时系统提示与 golden 逐字节相等，工具定义等于 golden 在 `memory_write`
与 `task` **之间插入** `run_skill`（不是末尾追加），其余每项逐字节不变。另有一条带假 MCP server 的断言：
`run_skill` 排在 `memory_write` 之后、第一个 `mcp__*` 之前。

### 3.12 embedding 型输出（`sc-batch-integration`，本份不实现）

```yaml
analysis: batch_integration
output:
  kind: embedding
  embedding:
    h5ad: processed.h5ad
    obsm_key: {harmony: X_harmony, scanorama: X_scanorama, scvi: X_scVI}   # 按方法
  labels: {...}            # 可选
reference:
  batch_obs: batch
  expression_obsm: X_pca
```

收集步把 embedding 抽成 `<trial>/embedding.npz`（`obs_ids` + float32 矩阵），与 `labels.csv.gz` 同属默认
保留；打分走注册键 `batch_integration`，面板从旧 `integration_panel.py` 迁。运行器、资源池、保留策略、
`run_skill` 都不需改动。主脚本 `sc_integrate.py` 由 `script` 声明（F15）。

### 3.13 下游如何使用

| 计划 | 用到本份的什么 | 约束 / 留位 |
|---|---|---|
| 0057 调参 | `EnsembleRunner`、`TuningCatalog`（类型、区间、log、priority、谓词、约束、`summary()`）、`trials.jsonl`、`metrics.json` 全部分量 | **开工前提：T3b 偏差报告经 owner 过目**（D1）；新模块 `ensemble/tuning.py`；`optimize_params` 同样在 `pause_tool_timeout` 内运行并自设总上限；对照组即直接用 `run_skill`，同池同面板 |
| 0058 consensus | `labels.csv.gz`、`best.json`、`run.json` 保证的同一输入、面板用于成员权重 | 新模块 `ensemble/consensus.py`、工具 `run_consensus`，挂在同一 `ensemble` 开关下 |
| 0059 方法层 benchmark | `fan_out`、`Limits`、`provenance`、`evaluation.py`、`run.json` 的 obs 列清单 | **硬约束**：`sandbox_required=true`；原始数据集与真值不在 workspace、不挂载进容器；输入 obs 只留白名单列；固定 `sandbox_image`；workspace 不是仓库根；`turn_timeout_s` 不设或 ≥ `T_call`（§3.5）；需要重复种子时给 `spatial_domains.py` 加 `--seed`（已定 Q15） |
| 0060 端到端 | `ensemble=false` 作消融基线（golden 快照保证提示只差工具表） | **硬约束**：同 0059 的防泄漏前提与 `turn_timeout_s` 约束；两组 `tool_timeout_s ≥ ensemble_max_trial_s + score_timeout_s + 75`（§3.5 消融公平）；两组容器里的 `omicsclaw/`、`skills/` 挂载相同（§3.10，已与 `ensemble` 开关解耦） |

### 3.14 旧代码复用 / 重写清单

旧包都无法 import（F14），"复用"指复制并改写进新包。

| 旧位置 | 处置 | 去向 |
|---|---|---|
| `spatial_metrics.py` `chaos`（:88-117） | **不复用**：定义与文献 CHAOS 不同（§3.7.1）；逻辑作为 `knn_agreement` 诊断重写 | `metrics/spatial.py` |
| `spatial_metrics.py` `pas`（:120-156）、`_spatial_knn_indices`（:77-85）、`_validate`（:67-74） | 复制并加机会校正 | `metrics/spatial.py` |
| `spatial_metrics.py` `mlami`（:159-237） | 复制（保留 BSD-3 声明），拆成"参照划分（可缓存）"与"AMI"两步，改名 `spatial_leiden_ami`；只用 `flavor="igraph"`，删去回退 `leidenalg` 的分支（F38） | `metrics/spatial.py` |
| `spatial_panel.py` 权重、归一、组合、失败剔除（:40-131） | 重写为通用、作用于校正值 | `metrics/panel.py` |
| `integration_panel.py`（:93-315） | 本份不迁，留 `batch_integration` 键 | 后续 |
| `member.py` `to_extra_args`（:42-49） | 弃用，由有类型的 `render_cli_args` 取代 | `space.py` |
| `source_registry.py` `SpatialDomainsArtifactReader`（:128-227） | 重写：改读无条件写出的 `tables/domain_assignments.csv`（含 id 列回退）；质量改用本面板；读法由 `tuning.yaml` 声明 | `runner.py` 收集步 |
| `fan_out.py` 状态分类、单步超时不殃及兄弟、`required_survivors`（:71-101、:240-254、:290-368） | 保留语义，用 asyncio 子进程 + `ResourcePool` 重写；弃守护线程与已删除的 `resource_scheduler` | `runner.fan_out`、`resources.py` |
| `autoagent/runner.py` `execute_trial`（:50-250） | 重写：取新会话 + 进程树终止、环境白名单；弃写死 3600 s、authority/receipt（改记 sha256） | `runner.py`、`execution.py`、`_supervise.py` |
| `autoagent/runner.py` `_params_to_cli_args`（:253-280） | 弃用（未知参数改为拒绝） | `space.validate_params` |
| `autoagent/constants.py` `SUBPROCESS_ENV_WHITELIST`（:36-46）、`SILHOUETTE_SAMPLE_SIZE`（:56） | 复制常量（白名单再加 CUDA、线程与缓存目录变量） | `execution.py`、`metrics/spatial.py` |
| `autoagent/search_space.py` `ParameterDef`（:17-57）、`to_summary`（:159-182） | 改写并入 `ParamSpec`、`MethodSpec.summary()` | `space.py` |
| `autoagent/search_space.py` `build_method_surface`/`_infer_range`（:196-291） | 弃用（区间改为显式） | — |
| `autoagent/metrics_registry.py` `MetricDef`（:21-56） | 改写为面板指标定义 | `metrics/__init__.py` |
| `autoagent/metrics_registry.py` `SPATIAL_DOMAIN_METRICS`、`metrics_compute.py` silhouette/local purity（:114-163、:567-607） | 由统一面板取代（§3.7.4 取舍） | `metrics/spatial.py` |

---

## 4. 分步实施

依赖：T1→T2；T3a→T3b；T3a、T4、T5 互不依赖；T6 需要 T1、T3a、T4、T5；T7 需要 T6；T8 需要 T7；
T9 需要全部。每步都跑 §5 主命令并保持绿。

**T0 基线、golden 与准备**（不写生产代码）：复测基线（F31）；在改动前生成 §3.11 的两份 golden
快照并提交为测试夹具；按已定 Q13 先尝试把 `STAGATE_pyG` 与 BANKSY 装进 `OmicsClaw` 环境，装不上
则冒烟接受 5 ok + 2 如实失败。

**T1 `space.py`**：数据类、加载器、谓词（`eq/ne/gt/ge/lt/le/in`，环检测）、约束（加载时用默认值自检）、
`validate_params`、`render_cli_args`、`summary()`。测试 `tests/ensemble/test_space.py`：合法样例；每条
规则一个反例且错误含字段路径；谓词各运算符；`active_when` 不满足时给出即被拒、未给时不渲染；约束
违反被拒；默认补齐；四种类型渲染；越界/未知名/他方法参数被拒并带摘要。

**T2 `spatial-domains/tuning.yaml` 与一致性测试**：落文件（交付记录写区间依据）。
`tests/ensemble/test_tuning_matches_argparse.py` 对仓库里每个 `tuning.yaml`：子进程里 `runpy` 运行
脚本 `main()`，把 `ArgumentParser.parse_args` 打补丁成抛出携带 parser 的哨兵异常，取真实 `_actions`，
断言：flag 存在；类型对应（float/int/`str2bool` 或 `store_true`）；categorical 元素类型与 argparse `type`
一致，**argparse 有 `choices` 时** tuning 的 choices ⊆ 它，**无 `choices` 时（如 `--data-type`）不比较
choices**；argparse 默认非 `None` 时与 tuning 默认相等（`None` 时须在 `note` 写明有效默认来源，如
`auto_k_max`）；`methods` 键集合等于 `method_flag` 的 choices；`skill` 等于 `SKILL.md` name；`script` 存在。
变异：改一个 flag 名、删一个方法、改一个默认值 → 各自失败。

**T3a 面板与评估**：`metrics/__init__.py`、`panel.py`、`spatial.py`、`score.py`、`evaluation.py`。
测试：`test_panel.py`（校正值裁剪、加权、剔除、诊断、`degenerate`）；`test_spatial_metrics.py`（CHAOS 与
PAS 在小例子上与**手算的文献定义**一致——两簇、带 1 点与 2 点小簇、标准化；PAS 的 5/6 阈值边界；
超几何期望与蒙特卡洛置换（大 B）相符；`knn_agreement` 期望公式；`spatial_leiden_ami` 需 igraph，rapids
下 `importorskip`）；`test_score_cli.py`（子进程打分合成 h5ad；obs 不齐失败；第二次命中参照缓存）；
`test_evaluation.py`。

**T3b 偏差研究**：§3.7.3 的 `test_panel_bias.py` 快速断言 + 完整报告；交付记录附报告表。**0057 的开工门槛。**

**T4 `resources.py`**：`test_resources.py`：原子申请；backfill 规则（队头缺 GPU 时 CPU-only 小请求可插空，
但不得占用队头所需的空闲内存/CPU；队头缺内存时不放行吃内存的后来者）；GPU 编号不重复；准入表的
三种 `gpu` 取值 × 有无 GPU 六种组合；内存/CPU 超总量 → 准入失败；取消在等待中的申请不泄漏。
`test_gpu_detect.py`：假 `nvidia-smi`（`PATH` 前置脚本）输出 0/2/4 行、命令缺失、`CUDA_VISIBLE_DEVICES`
交集、沙箱下经假 `BashEnvironment` 检测、`sandbox_gpus` 为空时记 0 并告警、显式配置不检测。

**T5 `_supervise.py`、执行器与沙箱配置**：`test_supervise.py`（分配内存 → `memory_exceeded`；`sleep` →
`timeout`；退出码透传；峰值内存；杀监督进程后子进程不残留，照 `tests/tools/test_bash_process_group.py`）；
`test_execution.py`（`LocalExecutor` cwd 为试验目录、每试验 `TMPDIR`/`MPLCONFIGDIR`/`NUMBA_CACHE_DIR`
互不相同、取消杀整组；`SandboxExecutor` 用假 `BashEnvironment` 断言 `shlex` 引用、`env` 前缀、cwd、timeout）；
`tests/sandbox/test_container.py` 增补 `--shm-size`、`--ulimit nofile`、新 `pids_limit`/tmpfs 默认；
`tests/sandbox`/`tests/entry` 增补：`sandbox_memory=auto` 解析；`omicsclaw/`、`skills/` 只读挂载在 `ensemble=false`
时**同样存在**、已被 workspace 覆盖时不重复、`sandbox_code_in_image` 关闭；不挂仓库根；`.env` 与 `.omicsclaw/`
存在时出现 `/dev/null` 与 tmpfs 遮蔽参数。`test_supervise.py` 另测 PSS 计量与 `smaps_rollup` 不可读时回退 RSS
（以假 `/proc` 根目录注入）、GPU 观测（假 `nvidia-smi` 输出含/不含本组 pid）。T4 另测 §3.4 的 `pool_mem`
公式（本机与沙箱两种 base、显式值取小、结果 ≤ 0 报错）与 `ensemble_max_queue_s` 超时即准入失败。

**T6 `store.py` 与 `runner.py`**：`test_runner.py` 用临时 skills 目录的**假 skill**（`SKILL.md` + `tuning.yaml`
+ 小脚本，可按参数失败/睡眠/吃内存，标签表 id 列可按参数命名为 `observation` 或其他名）驱动真实子进程
路径：目录布局；`run.json` 绑定、obs 列清单与冲突拒绝；编号并发不撞；admission/collect/score 各失败阶段；
id 列回退与 `id_column_used`；保留策略（默认删、`keep_all`、最佳 h5ad 迁移、平分、`tmp/` 删除）；`fan_out`
与 `required_survivors`；`trials.jsonl` 行数。

**T7 `tool.py`**：`test_run_skill_tool.py`：schema；policy 逐字段整体相等；每类校验错误 → `is_error`；
skill 失败与准入失败 → 普通 Observation；降级字段；返回字段；描述字节稳定；**整个调用处于
`pause_tool_timeout` 内**（注入计数假 pause 断言进入与退出包住 run 与 score）；自身 `asyncio.timeout` 兜底
（假 runner 挂住 → `timeout`）。引擎级并行：`[run_skill×3]` → 一批、区间重叠；`[run_skill, bash, run_skill]` → 三批。

**T8 装配、清理、文档**：`AppConfig` 字段与 `_OPTIONS`；`build_ensemble`；`open_app` 中 GPU 检测与启动自检
（D6：显式开启失败即报错、默认开启失败只告警并不挂载——两条都有测试，用假执行环境让自检失败）；自检 import
清单与 §3.10 一致（变异：删去 `igraph` 使一条测试失败）；`turn_timeout_s < T_call` 时的告警；
`foundation_tools` 把 `run_skill` 放在 `memory_write` 之后；**删除 `omicsclaw/__init__.py`:5-12 的 `run_skill` 懒属性**（F34，
`__all__` 只留 `__version__`）；分层测试（`test_ensemble_is_a_layer.py`、`_LOWER_LAYERS` 加 `ensemble`、agent
侧模块不加载 numpy/pandas/scanpy、`evaluation` 隔离）；**Py3.11 测试**
`tests/ensemble/test_executes_under_skill_python.py`：用 `OMICSCLAW_SKILL_PYTHON`（默认
`/opt/conda/envs/OmicsClaw/bin/python`，不存在则跳过并在报告中显示）在子进程里
`import omicsclaw.ensemble, omicsclaw.ensemble.metrics.score` 并断言 `omicsclaw.tools`、`omicsclaw.skills`、
`omicsclaw.ensemble.tool`、`omicsclaw.ensemble.runner` 不在 `sys.modules`，以及用该解释器 `py_compile`
`_supervise.py` 与 `metrics/*`；更新 `test_permission_wiring.py` 的 `MOUNTED`（F13；`test_assembly.py` 不改）；
§3.11 golden 断言（`memory_write` 与 `task` 之间插入，带假 MCP 时位于第一个 `mcp__*` 之前）。文档：`AGENTS.md`
（结构加 `ensemble/`；Skill Architecture 加 `tuning.yaml` 一节；写明**一轮可能长达数小时（含排队）**、`T_call`
公式与 `turn_timeout_s` 的相互作用；沙箱只读挂载 `omicsclaw/`、`skills/` 与 `.env`/`.omicsclaw/` 遮蔽；资源池不跨进程）、
`.env.example`、`tests/test_env_example.py`、`docs/FRAMEWORK-REBUILD.md`、README 里程碑、本计划交付记录。
**不改 `CLAUDE.md`**。

**T9 冒烟验收**（`tests/ensemble/test_smoke_spatial_domains.py`，标 `slow`，未设
`OMICSCLAW_ENSEMBLE_SMOKE_DATA` 时跳过；`ensemble_python` = `OmicsClaw` 环境）：

1. 在临时 workspace 写 `data/slideseqv2_hippocampus_counts.h5ad`：`X ← layers['counts']`（整数），
   **`obs` 只保留 `batch`**（删除 `cell_type`，§3.9）；原始数据集不在 workspace 内。
2. 按已定 Q17 跑 `spatial-preprocess`：`--data-type slide_seq --species mouse`，其余全默认；记录 QC 前后
   bead 数，丢失超过 20% 时报 owner。
3. `open_app` 装配（`ensemble_gpus` 留空走自动检测，期望检测到 4 张），用 `execute_tool_calls` 在**一轮**里
   发 7 个 `run_skill`（7 个方法、默认参数、同一 `run_id`，`data_type=slide_seq`）。
4. 断言：7 个结果都有 `status`；`ok` 的有 `metrics.json`、`labels.csv.gz`；同时在跑的试验中 `lease_gpu` 两两
   不同；每个 `device_source=observed` 的 GPU 试验其 `device` 等于 `cuda:<lease_gpu>`；至少两个试验区间重叠；墙钟总时长 < 各 `wall_s` 之和；`best.json` 与 h5ad 保留符合 §3.6；
   各试验 `TMPDIR` 不同且结束后已删除；失败试验的 `error` 含日志尾部。另跑一次 `ensemble_gpus=none`，
   断言 GPU 方法 `degraded="no_gpu"` 且 `device="cpu"`。**槽位上限的真实触发**：再跑一批，`ensemble_gpus=0`
   （只给 1 张卡）并发 3 个 GPU 方法（`stagate` 装不上时用 `graphst`、`cellcharter` 各两个不同参数的试验凑足 3 个），
   断言任意时刻持有 GPU 租约的试验至多 1 个、至少一个试验 `queued_s > 0`、同卡试验的运行区间互不重叠
   （7 个方法里只有 3 个 GPU 方法，4 卡下"≤4"不可能被触发，故不用它）。交付记录列 7 行（方法、状态、wall_s、
   peak_mem_gb、mem_metric、lease_gpu、device、score、各分量 raw/adjusted），并据实测 `peak_mem_gb` 校准各方法 `memory_gb`（已定 Q9）、据实测记录图生成耗时
   占比（已定 Q14）。

---

## 5. 测试计划

新栈测试一律用 rapids_singlecell 环境（默认 `python` 没有 pytest）：

```
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -p no:cacheprovider -q -o addopts="" \
  tests/ensemble tests/tools tests/engine tests/skills tests/sandbox \
  tests/entry/test_entry_is_the_top_layer.py tests/entry/test_open_app.py \
  tests/entry/test_assembly.py tests/entry/test_permission_wiring.py tests/test_env_example.py
```

基线（F31，不含 `tests/ensemble` 与后三个文件）：1847 passed, 2 skipped。已知无关：
`tests/tools/test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget` 单独跑会失败、整套通过。

另外三条：
- 需 igraph/squidpy 的面板测试与 Py3.11 测试用 `OmicsClaw` 环境再跑：
  `/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -o addopts="" tests/ensemble/test_spatial_metrics.py tests/ensemble/test_score_cli.py tests/ensemble/test_panel_bias.py`
  （rapids 下这些用例 `importorskip`，交付记录写两套结果，"跳过"不得冒充"通过"）。
- 偏差完整报告：`test_panel_bias.py` 的报告函数（`-m slow`）。
- 冒烟：`OMICSCLAW_ENSEMBLE_SMOKE_DATA=<开发数据路径>` 加 `-m slow tests/ensemble/test_smoke_spatial_domains.py`。

**关键变异**（每条应使至少一个测试变红）：`concurrency_safe=False`；backfill 放行占用队头所需内存的请求；
`fits()` 因 GPU 拒绝；`preferred` 无 GPU 时不设 `CUDA_VISIBLE_DEVICES=""`；`validate_params` 放过越界或违反
约束；谓词 `gt` 写成 `ge`；`render_cli_args` 省略默认值；CHAOS 改回"近邻同标签比例"；PAS 阈值改成 `≥ 5`；
超几何期望改成二项近似（大 B 蒙特卡洛比对捕获）；保留策略不删非最佳 h5ad；`runner` import `evaluation`；
`ensemble=false` 仍挂载或提示改变（golden）；运行不在 `pause_tool_timeout` 内；`_supervise.py` 不杀整组；
`ensemble/__init__` eager import `tool`（Py3.11 测试）。

**沙箱路径**：本机没有 docker（F29），容器执行、GPU 检测与资源参数只由假 `BashEnvironment` 与参数断言
覆盖；真实容器验证留给 0059，交付记录写明缺口。

---

## 6. 验收标准

1. §5 主命令全绿；基线无回归。
2. `spatial-domains/tuning.yaml` 覆盖 7 个方法，一致性测试通过，三种变异各自使其失败。
3. `import omicsclaw.ensemble.tool` 不加载 numpy/pandas/scanpy；`ensemble` 不 import `entry`/`runtime`/`autoagent`；
   运行路径不 import `evaluation`；`omicsclaw.ensemble` 与打分模块在 Py3.11 `OmicsClaw` 环境可 import 且不连带
   agent 侧模块。
4. `ensemble=false`：系统提示与工具定义与 golden 逐字节相同；`ensemble=true`：系统提示与 golden 相同，工具表
   等于 golden 在 `memory_write` 与 `task` 之间插入 `run_skill`（有 MCP 时位于第一个 `mcp__*` 之前），其余逐字节不变。
5. `run_skill` policy 逐字段等于 §3.8；一轮内多个调用同批且区间重叠；与 `bash` 之间有屏障；整个调用处于
   `pause_tool_timeout` 内且自身兜底生效。
6. 超时、超内存、非零退出、缺产物、打分失败、`required` 无 GPU、资源超总量各自得到正确 `status`/`stage`，
   均不作为工具错误；`preferred` 无 GPU 记 `degraded`。
7. 默认保留下每个试验目录只剩 §3.6 所列文件，`tmp/` 已删，每个 `(run_id, method)` 至多一个 h5ad。
8. CHAOS/PAS 实现与文献定义的手算例一致；四个面板指标都有 raw/expected/adjusted。
9. **T3b 偏差报告完成并经 owner 过目；在此之前 0057 不开工。**
10. 冒烟：一轮 7 个调用全部返回，自动检测到 4 张 GPU、不重复分配、并发可证、结果（含失败/降级）如实；
    输入 obs 只含 `batch`；交付记录附 7 行结果表与 QC 前后 bead 数。
11. 启动自检：执行环境缺 `_supervise.py`、打分模块或 §3.10 清单中任一依赖不可 import 时——显式开启 → 启动报错；
    默认开启 → 告警且不挂载 `run_skill`、其余照常（两条都由假环境测试覆盖）。
12. 沙箱参数：`omicsclaw/`、`skills/` 只读同路径挂载在 `ensemble=false` 时同样存在；不挂仓库根；`.env`、`.omicsclaw/`
    存在时有遮蔽参数；资源池内存等于 §3.4 公式；`ensemble_max_queue_s` 超时即准入失败。
13. 结果中的 `device` 来自实际观测（或标明来源），不来自租约；内存峰值为 PSS（不可得时标明 RSS）。

---

## 7. 风险与未决问题

### 7.1 已定（owner 按推荐采纳，含审核附加意见）

| # | 结论 |
|---|---|
| Q1 | pyyaml 加进 `pyproject` 核心依赖 |
| Q2 | `run_skill` 只运行带 `tuning.yaml` 的已索引 skill |
| Q3 | 搜索区间是硬约束 |
| Q4 | 改为：整个调用在 `pause_tool_timeout` 内，工具自身 `asyncio.timeout` 兜底，`ensemble_max_trial_s` 总上限，打分 120 s；0060 两组给同等时长（§3.5） |
| Q5 | 被 owner 裁定 D1 取代：v1 做机会校正 + 偏差研究 + 0057 门槛 |
| Q6 | 被 owner 裁定 D2 取代：已核查文献并按文献重写（§3.7.1） |
| Q7 | `n_domains` [3, 20]、默认 7 |
| Q8 | 被 owner 裁定 D3 取代：自动检测 + 降级/失败规则（§3.4） |
| Q9 | 改为 **PSS** 计量，`smaps_rollup` 不可读时回退 RSS 并记 `mem_metric`（复审）；各方法 `memory_gb` 在 T9 用实测峰值校准 |
| Q10 | 标签向量 `csv.gz` |
| Q11 | 环境变量白名单，另加 CUDA、线程与每试验缓存/临时目录变量（`TMPDIR/TMP/TEMP`、`MPLCONFIGDIR`、`NUMBA_CACHE_DIR`） |
| Q12 | `ensemble_python` 配置；启动时检查解释器 ≥3.11 且可 import 打分模块（§3.10） |
| Q13 | 先尝试安装 STAGATE/BANKSY（a），装不上接受 5 ok + 2 如实失败（b） |
| Q14 | 本份不改脚本；T9 先实测图生成耗时占比，0057 再定是否加 `--no-figures` |
| Q15 | `--seed` 在 0059 加 |
| Q16 | 不建 `tuning`/`consensus` 空模块 |
| Q17 | 冒烟预处理全默认 + `slide_seq`/`mouse`，记录 QC 前后 bead 数，丢失 >20% 报 owner |

### 7.2 第二版未决问题的结论（owner 按推荐采纳，2.1 版）

| # | 结论 |
|---|---|
| N1 | CHAOS 跟 SDMBench：跳过 ≤2 点的簇、总体标准差、被跳过点仍计入分母；`chaos_skipped_spots` 进诊断；T3b 加"大量极小簇"候选观察 |
| N2 | 置换次数 B 默认 10、记标准误；T3b 报告标准误相对校正值的量级 |
| N3 | 改名 `spatial_leiden_ami`，论文写"改编自 NicheCompass MLAMI"；附加：T3b 单独报告其 argmax K 与各分辨率参照 Leiden 的簇数（§3.7.3） |
| N4 | 偏差研究只做方向性断言 + 完整报告，达标与否由 owner 看报告裁定 |
| N5 | 沙箱资源默认值作用于整个容器（含 `bash`），写进 AGENTS.md；附加：资源池内存扣除 tmpfs、shm 与预留（§3.4） |
| N6 | 由 owner 裁定 D6 取代：显式开启时自检失败报错，默认开启时只告警并不挂载（§3.10） |

2.1 版没有新增待裁定问题。

### 7.3 风险

| # | 风险 | 应对 |
|---|---|---|
| R1 | `run_skill` 为 `AUTO`：模型可先改 skill 脚本（`write_file`/`edit_file` 默认要审批）再无审批运行 | `provenance.script_sha256`；部署可用规则把 `run_skill` 设为 `ask` |
| R2 | 多个试验同时读大 h5ad、写 `processed.h5ad`，I/O 成瓶颈 | 默认只留最佳 h5ad；T9 记录墙钟 |
| R3 | 资源池不跨进程，同机两个 `oc` 进程会超额使用 GPU | 写进 AGENTS.md；benchmark 单进程 |
| R4 | 沙箱取消只杀一个 PID（F8），监督进程被 SIGKILL 时孙进程可能残留 | `_supervise.py` 处理 SIGTERM + `PDEATHSIG`；真实容器验证留 0059 |
| R5 | 暂停引擎超时后，引擎对 `run_skill` 没有上界 | 工具自身 `asyncio.timeout` 与 `ensemble_max_trial_s`；测试钉住兜底 |
| R6 | 机会校正不能识别过切（§3.7.2） | T3b 量化；0057 与 owner 决定是否给 silhouette 权重 |
| R7 | `tuning.yaml` 与脚本漂移 | T2 一致性测试 |
| R8 | 工作树有其他会话的未提交改动（`assembly.py`、`config.py`、`sandbox/*`） | 引用带符号名；T8 最后合入并 rebase |
| R9 | 输入在试验运行中被改写 | `write_file` 是屏障；`run.json` 记 sha256，不符即拒绝 |
| R10 | 真值经 `bash` 或挂载泄漏 | §3.9 前提列为 0059/0060 硬约束；`run.json` 记 obs 列供审计 |
| R11 | `bash` 与系统进程不受资源池约束，若用量超过 `ensemble_reserved_gb`，容器仍可能先于试验级上限 OOM | 预留可配置；AGENTS.md 写明；T9 记录容器内存峰值 |
| R12 | `.env`/`.omicsclaw/` 遮蔽依赖挂载顺序（嵌套挂载覆盖 workspace 挂载）；本机无 docker，只能断言参数 | 0059 在真实容器里 `test ! -s <ws>/.env` 验证 |

---

## 8. 不做的事

- 调参循环与 `optimize_params`（0057）；`run_consensus`（0058）；区域标签构造与 benchmark（0059、0060）。
- 删除 `autoagent/`、`runtime/consensus/`、`runtime/workflow/`。
- `sc-batch-integration` 的 `tuning.yaml` 与 `batch_integration` 面板。
- 修改 `spatial_domains.py`（`--seed`、`--no-figures`）与任何 `SKILL.md`；恢复 `skill.yaml`。
- 修改 `CLAUDE.md` 或新增系统提示段落。
- 后台/异步试验、作业轮询、跨进程资源调度、GPU 显存配额；自动打开沙箱 GPU 透传。
- `replot`、`oc run` 或任何 CLI 子命令。

---

## 9. 修订记录

**第二版（2026-09-24）**，依据独立审核（结论"需修改后实施"）与 owner 裁定 D1–D5：

| 改动 | 来源 | 位置 |
|---|---|---|
| 状态行；新增 §0.3 第二版裁定表 | owner | 头部、§0.3 |
| 面板：按文献重写 CHAOS（同簇最近邻距离，低好），PAS 保留并确认阈值等价，`mlami` 改名 `spatial_leiden_ami`，旧 `chaos` 降为诊断 `knn_agreement`；附 SpatialPCA/SDMBench/NicheCompass 源码 URL | D2 | §3.7.1、§3.14 |
| 机会校正：保持簇大小的置换基线；PAS 精确超几何期望；CHAOS 置换期望 + 理论下界的 kappa 式；`knn_agreement` 期望公式；raw/expected/adjusted 并存；面板版本升 `spatial_domains/2` | D1 | §3.7.2 |
| 合成数据偏差研究 T3b；0057 开工门槛写进验收与下游 | D1 | §3.7.3、§4、§6-9、§3.13 |
| GPU：`gpu ∈ {none, preferred, required}`；自动检测（本机/容器内）；降级与明确失败规则；`fits()` 不因 GPU 拒绝；审批语义 | D3、审核阻断 3 | §3.2、§3.4、§3.8 |
| 沙箱默认资源上调（memory auto≈1557g、tmpfs 64g、shm 128g、pids 65536、nofile 65536，CPU 保持不限）及依据；每试验 `TMPDIR`/`MPLCONFIGDIR`/`NUMBA_CACHE_DIR`、cwd=试验目录 | D4 | §3.10、§3.3 |
| 真值防泄漏：输入 obs 白名单、`run.json` 记 obs 列、`sandbox_required` 且原始数据不挂载；列为 0059/0060 硬约束；冒烟删除 `cell_type` | 审核阻断 1 | §3.9、§3.13、T9 |
| 仓库只读同路径挂载（或 `ensemble_code_in_image`，2.1 版改为只挂 `omicsclaw/`、`skills/` 并更名 `sandbox_code_in_image`）与启动自检 | 审核阻断 2 | §3.10、T8 |
| 超时：整个调用在 `pause_tool_timeout` 内、工具自身兜底、`ensemble_max_trial_s=7200`、打分 120 s；0060 消融公平 | 审核阻断 4 | §3.5、§3.13 |
| 资源池改为不推迟队头的 backfill | 审核 | §3.4、T4 |
| schema：`active_when` 支持 `eq/ne/gt/ge/lt/le/in`；新增 `constraints`；`auto_k_max` 默认改为 10（脚本实际行为）；`pre_resolution` 依赖 `stagate_alpha>0` | 审核 | §3.2、F19、F20 |
| 消融：golden 快照逐字节断言 | 审核 | §3.11、T0、T8 |
| Py3.11 `OmicsClaw` 环境 import 测试；`__init__` 不 eager import agent 侧模块 | 审核 | §3.1、T8 |
| 小问题：T9 引用改为 Q17；SpaGCN 仅 CPU 已补证（F21）；F13 改为 `test_assembly.py` 只做前缀断言无需修改；清理 `omicsclaw/__init__.py` 残留 `run_skill` 懒属性（F34、T8）；标签表 id 列回退（F18、§3.2）；一致性测试允许 argparse 无 choices | 审核 | 各处 |
| 第一版未决问题中审核同意者改标"已定"，吸收附加意见（Q11 缓存目录变量、Q12 启动检查、Q13 先 a 后 b、Q14 先实测、Q17 记录 bead 数）；新增未决 N1–N6（SDMBench 与 SpatialPCA 的许可已核对，见 §3.7.4） | 审核、owner | §7 |

**第 2.1 版（2026-09-24）**，依据复审（结论"还需小改、无阻断"）与 owner 裁定 D6：

| 改动 | 来源 | 位置 |
|---|---|---|
| 状态行；§0.3 增 D6 | owner | 头部、§0.3 |
| 自检失败：显式开启报错、默认开启只告警并不挂载；`ensemble` 改为 `bool \| None` 以区分二者 | D6 | §3.10、§3.11、T8、§6-11 |
| 第二版 N1–N6 改标"已定"，N3 附加单独报告、N5 附加池余量 | owner | §7.2 |
| B2：`omicsclaw/`、`skills/` 挂载与 `ensemble` 开关解耦，消融两组容器里代码相同；配置项更名 `sandbox_code_in_image` | 复审 | §3.10、§3.11、§3.13、T5、§6-12 |
| B4：核实 `turn_timeout_s` 在 `entry/config.py`:214（不在 `engine/config.py`），说明它会取消长试验及处理办法；新增 `ensemble_max_queue_s=7200`；给出单调用/同批墙钟上界 `T_call` 与多轮上界 | 复审 | F35、§3.3、§3.5、§3.11、§3.13 |
| 挂载顺序按 `build_app` 实际写准：`…, memory_write, run_skill, <mcp__*>, task`；golden 断言为"在 `memory_write` 与 `task` 之间插入" | 复审 | F36、§3.11、§6-4、T8 |
| 凭据：只挂 `omicsclaw/`、`skills/`（逐项理由），不挂仓库根、`examples/`、`scripts/`；`.env`、`.omicsclaw/` 以 `/dev/null` 与只读 tmpfs 遮蔽 | 复审 | F37、§3.9、§3.10、R12 |
| 池内存余量：`pool_mem = base − tmpfs − shm − ensemble_reserved_gb(64)`，默认沙箱 1301 GiB、本机 1493 GiB；修正"先由试验级上限拦截"的表述 | 复审、N5 | §3.4、§3.10、§3.11、R11 |
| 自检 import 清单按打分路径列全（numpy、scipy.spatial、scipy.stats、pandas、h5py、anndata、sklearn.neighbors、sklearn.metrics、scanpy、igraph），新实现只用 igraph flavor 故不含 leidenalg | 复审 | F38、§3.10、§3.14 |
| 偏差研究：措辞改"大部分减弱"并写明校正后 PAS 仍偏 K=2 的结构性原因；定义"旧面板"与平分规则，原断言(2)降为报告项；噪声施加于所有候选；单独报告 `spatial_leiden_ami` 的 argmax K 与参照 Leiden 簇数 | 复审 | §3.7.2、§3.7.3 |
| 内存计量改 PSS，不可得时回退 RSS 并记 `mem_metric` | 复审 | §3.3、§7.1-Q9、T5 |
| `device` 取实际观测（`nvidia-smi` compute-apps 匹配本组 pid），另记 `lease_gpu` 与 `device_source` | 复审 | §3.3、§3.8、§6-13 |
| T9 删去空转的"≤4 个 GPU"断言，改为单卡下 3 个 GPU 试验的真实排队断言 | 复审 | T9 |
| 工具描述与 AGENTS.md 待改清单写明"一轮可能长达数小时（含排队）" | 复审 | §3.8、T8 |
