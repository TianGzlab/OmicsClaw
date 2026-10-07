# 计划 0056 交付记录 — ensemble 基础层

**日期**：2026-09-24。**规格**：`docs/plans/0056-ensemble-foundation.md` 第 2.1 版（本记录不改动计划正文）。
**状态**：T0–T9 已实施；未 commit。T3b 偏差报告待 owner 过目（0057 开工门槛，计划 §6 第 9 条）。

**2026-10-07 补记**：ensemble 层已于 2026-10-02 删除，代码存档在 tag `archive/ensemble-before-removal`。本计划已被取代，不再实施或维护。

## 1. 各步完成情况

| 步 | 内容 | 落点 |
|---|---|---|
| T0 | 基线复测；改动前生成 golden 快照；尝试安装 STAGATE_pyG / BANKSY | `tests/entry/golden/ensemble_off_{prompt.txt,tools.json}`（由 `tests/entry/test_ensemble_golden.py` 在任何生产改动前以 `OMICSCLAW_WRITE_GOLDEN=1` 写出）。安装被执行环境的权限策略拒绝，按 Q13(b) 接受"5 ok + 2 如实失败" |
| T1 | `tuning.yaml` schema 与加载器 | `omicsclaw/ensemble/space.py`；`tests/ensemble/test_space.py` |
| T2 | `spatial-domains/tuning.yaml` + argparse 一致性 | `skills/spatial/spatial-domains/tuning.yaml`；`tests/ensemble/test_tuning_matches_argparse.py`（改 flag / 删方法 / 改默认值 / None 默认缺 note 四种变异各自失败） |
| T3a | 面板、打分子进程、评估模块 | `omicsclaw/ensemble/metrics/{__init__,panel,spatial,score}.py`、`evaluation.py`；`test_panel.py`、`test_spatial_metrics.py`、`test_score_cli.py`、`test_evaluation.py` |
| T3b | 合成数据偏差研究 | `tests/ensemble/test_panel_bias.py`；完整报告 `docs/plans/0056-panel-bias-report.md` |
| T4 | 资源池、GPU 检测 | `omicsclaw/ensemble/resources.py`；`test_resources.py`、`test_gpu_detect.py` |
| T5 | 监督进程、执行器、沙箱参数 | `omicsclaw/ensemble/_supervise.py`、`execution.py`；`omicsclaw/sandbox/{config,container}.py`；`test_supervise.py`、`test_execution.py`、`tests/sandbox/*` 增补 |
| T6 | 存储与运行器 | `omicsclaw/ensemble/{store,runner}.py`；假 skill `tests/ensemble/fake_skills/spatial/fake-domains/`；`test_runner.py` |
| T7 | `run_skill` 工具 | `omicsclaw/ensemble/tool.py`；`test_run_skill_tool.py` |
| T8 | 装配、清理、文档 | `omicsclaw/entry/{ensemble,assembly,config}.py`；删除 `omicsclaw/__init__.py` 的 `run_skill` 懒属性；`test_ensemble_is_a_layer.py`、`test_executes_under_skill_python.py`、`tests/entry/test_ensemble_{golden,wiring,config}.py`、`test_permission_wiring.py`、`test_entry_is_the_top_layer.py`（`_LOWER_LAYERS` 加 `ensemble`）、`tests/launch/test_grammar.py`（登记两个新 `__main__`）；`.env.example`、`tests/test_env_example.py`、`AGENTS.md`、`docs/FRAMEWORK-REBUILD.md`、`README.md`。`CLAUDE.md` 未改 |
| T9 | 冒烟 | `tests/ensemble/test_smoke_spatial_domains.py`（`-m slow` + `OMICSCLAW_ENSEMBLE_SMOKE_DATA`） |

## 2. `spatial-domains/tuning.yaml` 区间依据

全部依据脚本 argparse 默认值、`references/parameters.md` 的调参提示与 `_lib/domains.py` 源码；**没有任何区间参考开发数据的真值**。

| 参数 | 区间 / 默认 | 依据 |
|---|---|---|
| `resolution`（leiden/louvain/banksy） | [0.1, 2.0] log，1.0 | 脚本默认 1.0；Leiden 分辨率常用范围一个数量级上下，log 刻度 |
| `spatial_weight` | [0.0, 0.9]，0.3 | 脚本默认 0.3；1.0 即完全忽略表达，排除 |
| `spagcn_p` | [0.1, 0.9]，0.5 | parameters.md "0 to 1"，去掉两端退化值 |
| `n_domains` | [3, 20]，7 | 已定 Q7；7 为脚本自身默认（与数据无关），note 写明来源 |
| `epochs` | spagcn [50,400]、stagate [50,1000]、graphst [50,600]，均 100，log | 脚本默认 100；GraphST 官方默认约 600（parameters.md） |
| `k_nn`（stagate） | [3, 15]，6 | 脚本默认 6；`rad_cutoff` 不列（`k_nn>0` 时被忽略，F19） |
| `stagate_alpha` / `pre_resolution` | [0,1] 0.0 / [0.05,1.0] log 0.2，`active_when: stagate_alpha > 0` | F19 |
| `dim_output` | {32, 64, 128}，64 | 脚本默认 64 |
| `lambda_param` / `num_neighbours` | [0,1] 0.2 / [6,30] 15 | 脚本默认；parameters.md 0.2 细胞分型、0.8 区域 |
| `auto_k` 及 `auto_k_min`/`auto_k_max` | false；[2,10] 2 / [4,20] 10，约束 min<max | F20：脚本在 auto-k 时不传 `n_domains`，库取 `auto_k_min+8=10` |
| `n_layers` | [1, 5]，3 | 脚本默认 3 |
| `data_type`（context） | {visium, xenium, slide_seq, merfish, seqfish, generic, stereo}，null | `SUPPORTED_SPATIAL_PLATFORMS` ∪ `_infer_graphst_data_type` 的 `stereo` |

`memory_gb` 按 T9 实测 PSS 峰值约 3 倍校准（已定 Q9）：leiden/louvain 8、spagcn 64（峰值 20.6 GB）、graphst 16（GPU 2.8 / CPU 4.1 GB）、cellcharter 16（1.9 / 1.1 GB）；stagate 64、banksy 32 未能实测，保持草案值。

## 3. 测试

| 命令 | 基线（改动前） | 实现后 |
|---|---|---|
| §5 主命令（基线不含 `tests/ensemble`） | 1931 passed, 2 skipped | **2199 passed, 8 skipped, 0 failed** |
| 其中 `tests/ensemble`（rapids，Py3.13） | — | 259 passed, 6 skipped（igraph 缺失 2、完整偏差报告 1、冒烟 3） |
| `OmicsClaw` 环境（Py3.11）：`test_spatial_metrics.py test_score_cli.py test_panel_bias.py` | — | 27 passed, 1 skipped（完整报告需 `-m slow`） |
| 偏差完整报告（OmicsClaw，`-m slow`） | — | 1 passed，649 s |
| 冒烟（`-m slow`） | — | 3 passed，860 s |
| 其余新栈套件（schema…subagent，AGENTS.md 列表） | — | 3651 passed, 11 skipped（`tests/launch/test_grammar.py` 登记新入口后） |

计划 §5 中 F31 的基线（1847 passed）对应较小的目录集合；本次实测用的是 §5 主命令去掉 `tests/ensemble` 的同一集合，故以 1931 为准。

## 4. T9 冒烟结果

数据：`X ← layers['counts']`，`obs` 只留 `batch`；原始文件不在 workspace（`/tmp/0056_smoke/ws`）。`spatial-preprocess --data-type slide_seq --species mouse` 其余默认：QC 前 **41786**、QC 后 **41786** bead（丢失 0%），72.7 s。预处理后 `obs` 为 `batch` 与预处理自加的 QC 列和 `leiden`，无 `cell_type`；`run.json` 的 `input_obs_columns` 据此可审计。GPU 自动检测到 **4** 张。

**一轮 7 个 `run_skill`**（同一 `run_id`，`data_type=slide_seq`，默认参数）：批墙钟 392.7 s，各 `wall_s` 之和 558.5 s。

| 方法 | 状态 | wall_s | peak_mem_gb (PSS) | lease_gpu | device（来源） | score | CHAOS raw/adj | PAS raw/adj | AMI |
|---|---|---|---|---|---|---|---|---|---|
| leiden | ok | 33.7 | 0.52 | — | unknown（unknown） | 0.321 | 0.023 / 0.427 | 0.587 / 0.410 | 0.172 |
| louvain | ok | 40.7 | 0.52 | — | unknown（unknown） | 0.324 | 0.023 / 0.415 | 0.562 / 0.435 | 0.177 |
| spagcn | ok | 386.7 | 20.64 | — | unknown（unknown） | 0.597 | 0.015 / 0.863 | 0.242 / 0.750 | 0.256 |
| stagate | failed（run） | 3.5 | 0.31 | 2 | cpu（observed） | — | — | — | — |
| graphst | ok | 40.3 | 2.84 | 0 | cuda（skill） | 0.530 | 0.015 / 0.850 | 0.345 / 0.650 | 0.149 |
| banksy | failed（run） | 3.7 | 0.31 | — | cpu（observed） | — | — | — | — |
| cellcharter | ok | 50.0 | 1.93 | 1 | gpu（skill） | 0.682 | 0.014 / 0.884 | 0.090 / 0.907 | 0.368 |

- stagate：`STAGATE_pyG` 未安装，脚本退出码 1，`error` 含日志尾部与安装提示。
- banksy：`banksy` 未安装；且回落路径 `omicsclaw/core/external_env.py` 仍 import 已删除的 `omicsclaw.skill`（`ModuleNotFoundError`）——仓库既有缺陷，不在本份范围。
- `device` 为 `unknown`/`skill` 的原因见 §6 偏离 2。
- 保留：每个方法目录只剩 `t0001/{trial.json, labels.csv.gz, metrics.json, supervisor.json, run.log, output/result.json[, output/processed.h5ad]}`；`tmp/` 均已删除；失败试验无 h5ad。

**`ensemble_gpus=none`**：graphst、cellcharter 均 `degraded=no_gpu`、`lease_gpu=None`、`device=cpu（observed）`、ok；graphst CPU 上 189.7 s（GPU 40 s）；stagate 如实失败。

**`ensemble_gpus=0`（单卡）并发 4 个 GPU 试验**（graphst epochs 50/60，cellcharter n_domains 6/8）：全部 `lease_gpu=0`；`queued_s` = 0 / 51.9 / 93.5 / 145.2；运行区间首尾相接、互不重叠。

**图生成耗时占比（Q14）**：cProfile 下 leiden 5.4%、cellcharter 3.4%（`generate_figures` 累计 4.3 s / 3.9 s）。

## 5. T3b 偏差研究摘要（完整表见 `0056-panel-bias-report.md`，待 owner 过目）

36 个配置（网格/Poisson × 条带/Voronoi × K*∈{4,7,10} × 噪声 {0,5%,15%}）：

- **随机置换的校正值以 0 为中心**：CHAOS 均值 |·| ≤ 0.01（sd ≈ 0.01–0.03），PAS ≤ 0.003，kNN agreement ≈ 0，AMI ≈ 0。快速断言通过。
- **偏向的方向与计划预期相反**：新面板 argmax K 在 33/36 个配置里是候选集的最大 K（2K*，即最细的空间连续再切分），旧面板也是 33/36（其余三处为 5、15、15）。主要推手是 `spatial_leiden_ami`：参照 Leiden 在分辨率 0.1/0.55/1.0 下给出 5/17/28（网格）或 8/26/36（Poisson）个簇，AMI 随候选 K 单调上升（Spearman +1.00）。带噪声时 CHAOS 校正值也随 K 上升（Spearman ≈ +0.9–1.0）。
- 校正后 PAS 在干净数据上随 K 下降（Spearman ≈ −0.9 到 −1.0），与 §3.7.2 的结构性说明一致，但它的权重 0.2 不足以抵消 AMI 与 CHAOS。
- CHAOS 置换期望的标准误中位数约 1e-4，相对校正值约 1e-4–5e-4（N2）。
- 极小簇候选（2% 观测放入 2 点簇）：`chaos_skipped_spots` 如实记录（N1）。

**补充归因（依评估意见复核，2026-09-24）**。以各配置最小 K（K=2 合并）到最大 K（2K* 再切分）的面板分量增量衡量（权重 × 裁剪后校正值之差）：

- CHAOS 校正分母 `E_rand − d_min` 在 K 小时趋于 0，把带噪声时的小偏移放大成大负值。复算 grid/stripes/K*=4/5%：K=2 时 raw 0.05205、E_rand 0.05121、d_min 0.04880，分母 0.00242，校正值 −0.347；K=8 时分母 0.02758，校正值 0.586。折算后 CHAOS 贡献 0.4×(0.586−0)=**0.234**，AMI 贡献 0.4×(0.539−0.183)=**0.142**，与评估方数字一致。
- **与评估方表述不符之处**：并非"24 个带噪声配置中 CHAOS 都是主推手"。复算结果是 **12/24**——全部 12 个网格带噪声配置里 CHAOS 增量（0.13–0.28）大于 AMI（0.11–0.15）；而 12 个 Poisson 带噪声配置里 CHAOS 增量只有 0.07–0.11，均小于 AMI（0.11–0.15），主推手是 AMI。
- 规则网格、无噪声时，CHAOS 校正值对所有空间连续候选（合并、真值、再切分）都饱和在 1.000（raw 恰等于 d_min）；6/6 个网格无噪声配置复核属实。此时排序完全由 AMI 决定（增量 0.10–0.15）。
- "偏好最大 K"受候选上限 2K* 的边界效应影响：候选集在 2K* 截断，argmax 落在边界说明面板在所测范围内单调上升，不能据此确定其真实极值位置。

以上只记事实；面板权重与校正公式未改动，待 owner 裁定。

结论供 owner 裁定：按当前权重，面板系统性偏好过切；是否给 silhouette（表达证据）加权、改 AMI 参照分辨率或权重，属 0057 前需决定的问题。

## 6. 偏离

1. **`.omicsclaw/` 遮蔽改为可写 tmpfs + 回挂交换目录**：计划写 `--tmpfs <ws>/.omicsclaw:ro,size=1m`。但沙箱自身的每命令 pid/日志文件就在 `<ws>/.omicsclaw/sandbox/`（`EXCHANGE_DIR`，容器内 WRAPPER 要写它），只读空 tmpfs 会让每条 `bash` 失败。实现为 `--tmpfs <ws>/.omicsclaw:rw,nosuid,nodev,size=1m` 再 `--volume <ws>/.omicsclaw/sandbox:<ws>/.omicsclaw/sandbox`（嵌套挂载需父挂载可写以建挂载点）。设置、记忆库、计划仍被遮蔽；容器只能写进随容器消失的 tmpfs。原因总结：只读遮蔽与沙箱自己的交换目录冲突，二者只能取其一，而 `bash` 必须可用。本机无 docker，只断言了参数；遮蔽是否生效（`test ! -s <ws>/.env`、`.omicsclaw` 内只见 `sandbox/`）与挂载顺序的**真实容器验证留到 0059**（R12）。
2. **GPU 观测在 PID 命名空间不同的容器里无法按 pid 归属**：本机即如此——`nvidia-smi --query-compute-apps` 报宿主 pid（实测 3936689），进程内看到的是 367374。`_supervise.py` 在"列出的进程在本 `/proc` 中一个都不存在"时记 `gpu_probe=unattributable`（本次运行粘滞），运行器按计划的回退链改用 skill `result.json` 的 `summary.device`（`device_source=skill`），没有则 `unknown`。因此冒烟里 GPU 方法显示 `cuda/gpu（skill）`，同期运行的 CPU 方法显示 `unknown`；计划"每个 observed 的 GPU 试验 device 等于 cuda:<lease>"的断言因无 observed GPU 试验而空转。评估后修订：无租约的试验（`CUDA_VISIBLE_DEVICES=""`）直接判 `cpu`、来源 `inferred_no_lease`；skill 自报的 `cuda`/`gpu`/`cuda:N` 统一写成 `cuda:<lease>`。**后续**：0059 若需要"观测到的设备"，要换一种不依赖 pid 的观测方式，例如在每卡一个试验时监看租约卡的显存变化。
3. **pyyaml 未加进 `pyproject` 核心依赖（Q1）**：`tests/test_pyproject_thin_pip_layer.py` 明确禁止 conda 管理的包（含 pyyaml）出现在 pyproject。已回退，pyyaml 仍只在 `environment.yml`。
4. **STAGATE_pyG / BANKSY 未安装**：安装命令被执行环境的权限策略拒绝，按 Q13(b) 处理。
5. **`test_permission_wiring.py` 的 `MOUNTED` 未改**：该名单由 `build_app` 默认调用断言，默认调用不挂 `run_skill`（运行器只由 `open_app` 在自检后建出）。改为新增 `MOUNTED_WITH_ENSEMBLE` 与两条测试（`run_skill` 在 `memory_write` 与 `task` 之间且被闸门包住；read-only 模式拒绝）。
6. **单卡排队批次用 4 个试验**（graphst、cellcharter 各两组参数），计划写"凑足 3 个"；更多一个只让排队更明显。
7. **`T_call` 公式多两项**：计划的 `T_call` 没有计入输入哈希与首次绑定 run 时读取 obs 列（`_describe_input`）。现各设 300 s 上限（`HASH_TIMEOUT_S`、`DESCRIBE_TIMEOUT_S`，`runner.py`），并纳入 `call_ceiling_s`：默认 `T_call` = 300+300+7200+7200+120+60 = **15180 s**（约 4.2 h）；工具描述、启动告警与 AGENTS.md 同步。
8. **小的实现选择**：`TrialSpec` 多一个 `input_sha256` 字段（避免重复哈希）；`build_app` 增加 `skills=`、`ensemble=` 参数，`AgentApp` 增加 `ensemble` 字段；打分子进程增加 `--describe-input`，由执行环境读输入的 obs 列名（agent 进程不加载 h5py/numpy）；工具的兜底超时实现为 `runner.run(backstop_s=…)`，使 `trial.json` 与工具返回同为 `timeout`，测试用"执行器永远挂住"代替"假 runner 挂住"；`_supervise.py` 自身设 `PDEATHSIG(SIGTERM)`，父进程（沙箱里的 bash 包装）被杀时也能清理进程组（R4）。
9. **本交付记录单列文件**：按派发要求不改计划正文，交付记录与偏差完整报告写在 `0056-ensemble-foundation-delivery.md`、`0056-panel-bias-report.md`。

## 7. 遗留

- T3b 报告需 owner 过目（0057 门槛）；报告显示面板偏好过切，见 §5。
- 沙箱路径（容器执行、遮蔽、挂载顺序、容器内 GPU 检测）只由假 `BashEnvironment` 与参数断言覆盖，真实容器验证留给 0059。
- 容器内 GPU 使用无法按 pid 观测（偏离 2）；若 0059 需要"观测到的设备"，可考虑按租约 GPU 的显存变化判断（每卡一个试验时成立）。
- banksy 回落路径 import 已删除的 `omicsclaw.skill`（`omicsclaw/core/external_env.py:25`），与本份无关但会让 banksy 在任何环境里都失败，除非 `banksy` 包装在主环境。
- 自检在未设 `OMICSCLAW_ENSEMBLE_PYTHON` 时用 agent 自身解释器；rapids 环境缺 igraph，默认只告警不挂载。部署需把它指向 `OmicsClaw` 环境。

## 8. owner 裁定（2026-09-25）

- **E2 / Q1 修订**：pyyaml 只随 conda 环境（`environment.yml`）安装，不进 `pyproject`。这把 §6 偏离 3 的回退定为正式决定；`tests/test_pyproject_thin_pip_layer.py` 的禁止项保持不变。
- **E3（列为 0059 硬约束）**：0059 的输入在预处理**之后**再剥离 `obs`，只保留 `batch`。T9 冒烟里预处理自加的 QC 列与 `leiden` 留在了 `obs`（§4），0059 不得这样。
- **E4**：默认开启（`OMICSCLAW_ENSEMBLE` 未设）时每次启动的执行环境自检开销，以及解释器缺 igraph 时"只告警、不挂载 `run_skill`"的行为，owner 已接受，不再改动。部署时 `OMICSCLAW_ENSEMBLE_PYTHON` 指向 `/opt/conda/envs/OmicsClaw/bin/python`（2026-09-25 核实：存在，可 import igraph 0.11.9、scanpy、scikit-learn、scipy），README 的 ensemble 条目已写明。
- **E1**：扩大候选 K（到 40，另测到 60）的偏差复查已完成，见 `0056-panel-bias-report.md` 末节"扩大候选 K 的复查（2026-09-25）"，脚本在 `docs/plans/0056-panel-bias-study/study.py`。结论：现状面板的过切偏好随候选上限单调后移，不是 2K* 的边界效应；推荐 0057 改用 PAS 0.5 + silhouette（原值）0.5，待 owner 裁定。面板代码未改动。
