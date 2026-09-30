# 计划 0057 — ensemble 调参：稳定性证据 → LLM 定 K → 固定 K 下按维度分治的确定性调参，`optimize_params` 与 agent 自由编排对照

**状态**：第 3.1 版（2026-09-26），按复审与 owner 裁定局部修订，待 owner 终审；未写任何生产代码。

**前置**：0056 基础层已实施、未 commit（`docs/plans/0056-ensemble-foundation-delivery.md`）；面板偏差研究四节已完成
（`docs/plans/0056-panel-bias-report.md`，下称"0056 报告"）。本计划是 0056–0060 系列的第二份，输出接口给 0058（§3.14），并为 0059
预登记确证设计（§4.9）。

**给实现者的一条硬要求**：新代码的函数、类与模块 docstring 只写"是什么、做什么、参数与返回、会抛什么"，以及会
改变调用方式的行为说明（例如"超出预算时拒绝并返回已用/上限"）。**不写计划编号、裁定编号、决策叙事、与旧
autoagent 的对照、开发集上的实测数字**——这些写进本计划、交付记录或测试的 docstring。prompt 模板同理：只写给模型看的内容。

---

## 0. 缘起与已定裁定

### 0.1 缘起与论文立意

**核心主张**：在 benchmark 指标上，"autoagent 自动调参 + consensus 多方法共识"这条流水线**优于直接跑 skill**（即用 skill 的默认
参数）。这是 skill 自进化的另一条路径：

| 路径 | 做法 | 在本系列中的位置 |
|---|---|---|
| 路径一：离线修改 skill | autoresearch 式持续搜索：在 benchmark 数据集上爬山，修改 skill 的默认值、提示或代码，再在留出数据集上检验迁移效果 | 0059 之后的独立计划，合并 J3 的回写与 Q8 的 harness 进化（M2）；不在 0057 范围 |
| **路径二：测试时自适应** | 不改 skill，运行时针对每份数据调参、再做共识 | 0056 基础层 → **0057 调参（本份）** → 0058 consensus → 0059 方法层 benchmark → 0060 端到端 benchmark |

**两条路径的分工**（M2）：运行时（0057/0058），LLM 的价值在**选 K、选方法和 consensus**——这些是依赖当前数据、需要把证据与领域知识
结合的决策；参数的局部搜索交给确定性程序（§3.8）。离线阶段用持续搜索改进 skill 本身，并检验改进能否迁移到新数据。本份的台账设计成能支持
离线阶段（§3.10.1），但不实现它。

全部完成后统一提交。

0056 报告给出本份的技术出发点：内部指标面板**在固定 K 下能比较方法**（DLPFC 两张切片上，同一 `n_domains` 下三个模型方法之间，候选面板 6/6
与 6/6、现状面板 6/6 与 5/6 挑中 ARI 最高者），但**选不出 K**（候选面板被 silhouette 拉到 K=2，现状面板被空间过度平滑的 `leiden(w=0.9)` 拉到
K=17–21）。所以本份把"选 K"与"在 K 下选参"拆开：K 由 LLM 看稳定性证据、marker 与 SKILL.md 先验定夺，参数在选定 K 下由面板打分、确定性程序推进。

### 0.2 autoagent 与 skill 的设计差异

- **skill** = 一个方法 + 人写的静态知识（SKILL.md、默认参数、`references/parameters.md` 的调参提示）。它对所有数据给出同一套默认。
- **autoagent**（本系列的调参 + 共识层）= 一族 skill 之上的**元层**：把**当前数据上的证据**（稳定性曲线、marker、固定 K 面板分数、试验台账）与
  **SKILL.md 先验**结合，做数据相关的决策（选 K、选参数、选哪个方法的结果）。**SKILL.md 是它的输入，不是需要屏蔽的东西**（J1）。
- **对旧实现的如实描述**：旧 OmicsClaw autoagent 实际上是 **Python 确定性循环 + LLM 提议器**——`optimization_loop.py`:256 的
  `for trial_id in range(1, self.max_trials)` 驱动循环，LLM 按 `directive.py` 的指令（:66-72，"you suggest parameter values, the system runs the skill"）
  每轮提议一组参数、并可回 `converged`。它所参照的外部项目（kevinrgu/autoagent 与 Karpathy 的 autoresearch）才是"agent 自由编排"。本份的新设计是
  **混合骨架**：确定性程序负责预算、打分、搜索的局部部分与选择；LLM 的决策点是**定 K、补请求 marker、为 2–3 维方法提议第 1 阶段参数**（K2，
  其中"停止"由 M1 的确定性跳过规则取代，§3.8）；"agent 自由编排"作为次要对照组保留（K1，§3.12）。

### 0.3 已定裁定（owner，不在本份重新讨论）

第一轮（起草前）：

| # | 裁定 | 本份落实位置 |
|---|---|---|
| Q5 | 每项能力可由配置单独关闭；消融四组：默认参数单方法、调参单方法、默认参数 consensus、调参后 consensus；基线组做法是不挂载 tool | §3.13、§4.3（后两组属 0058/0060） |
| Q6 | 调参 = 确定性库 + `optimize_params` tool，只有"提议"与"决策"调用 LLM | §3.7、§3.8 |
| Q8 | harness 自我进化暂缓，不迁移 | §0.1、§3.15、§9 |
| Q9 | 精简重写；旧 `omicsclaw/autoagent/` 在本份实施完成后删除，含测试与文档引用 | §3.15、T11 |
| Q12 | 调参与 consensus 串成流水线；0057 输出接口为 0058 留位 | §3.14 |
| Q13 | LLM 默认只看文本；看图为可选开关，默认关 | §3.7、§3.13 |
| Q16 | 用户明确要求或 agent 依 SKILL.md 自行判断时才调用 `optimize_params`；benchmark 由配置强制消融组 | §3.11、§3.13 |
| Q23 | 不告诉方法真值类别数 | §3.4、§3.9、§4.2 |
| Q24 | ~~每轮 3 组、最多 4 轮、加一次基线；连续 2 轮无提升提前停止~~ **已被 M1 取代**；"按运行次数计预算"保留 | §3.8 |
| Q25 | 分数提升不大时偏向偏离默认值少的参数 | §3.8.4 |
| Q26 | 自由编排对照组：同运行预算（tool 层计数）、同模型、同打分 tool、同初始信息；两组都能看到 SKILL.md 调参提示 | §3.12 |
| Q28 | 提议用 LLM 默认与主 agent 相同，可单独覆盖；每次运行记录模型 ID 与日期 | §3.10、§3.13 |
| F2 | 输入没有 `X_pca` 时拒绝打分 | §3.6 |
| G3 | 两层选参：稳定性 → LLM 定 K（理由可审计）→ 固定 K 下面板打分、确定性程序 | §3.2–§3.8 |
| G4 | 可以告诉 LLM 组织类型，绝不给区域数或层数；"给不给组织信息"是一组消融 | §3.9、§4.3 |
| G5 | 遗憾值与"不低于默认中位数"；Spearman ρ 为次要 | 由 J2、L1 重新组织为 §4.4 的估计量 |
| G6 | 规则、阈值、权重在看留出数据前写进本 plan 并冻结；开发集 DLPFC 151673/151674；留出集其余 10 张 DLPFC + CosMx 人肝；留出集只跑一次 | §4 |
| G7 | `max_mt_pct=20` 删掉 DLPFC 12%–20% 的 spot，留给 0059；本份说明影响与处理 | §4.2 |
| E3 | 输入在预处理之后再剥离 obs，只保留 `batch` | §4.2、§3.9 |
| 环境 | stagate、banksy 缺包；可跑 leiden、louvain、spagcn、graphst、cellcharter；`OMICSCLAW_ENSEMBLE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python`；本机无 docker；4×H100、104 核、约 2 TB 内存 | §2、§4 |

第二轮（第一版审核后）：

| # | 裁定 | 本份落实位置 |
|---|---|---|
| H1 | 稳定性只作证据、不作硬过滤；LLM 看整个 K 网格上的三条曲线自选 K；原 V1/V2/V3 候选规则删除 | §3.5、§3.7 |
| H2 | 固定 K 面板先归一化再对 PAS 与 silhouette 取平均；开发比较单列"同一方法、不同参数"的组 | §3.6、§4.6 |
| H4 | 组织描述维持原样（完整名称）；禁词表只禁区域数、层数的直接数值泄漏；G4 消融保留 | §3.9 |

第三轮（第二版复审后）：

| # | 裁定 | 本份落实位置 |
|---|---|---|
| J1 | SKILL.md 全文提供给 LLM，删除全部去锚机制；"默认 7 = DLPFC 真值"对基线有利、对主张保守；锚定风险由多数据集分列报告暴露 | §3.7、§3.9、§4.4（判读规则见复审第四轮必改 5） |
| J2 | 主要比较两个：(i) 同一方法调参后 vs 自己的默认；(ii) 流水线 vs 各方法默认的中位数；次要：vs oracle-of-defaults；基线就是 skill 默认值（含 `n_domains=7`） | §4.4（L1 之后全部为估计量） |
| J3 | 台账设计成可用于回写的格式，不实现回写 | §3.10.1、§9 |
| K1 | 自由编排只保留 A3（给组织），2 次重复、次要；隔离；`use_skill` 不禁用；token 上限与 `max_turns=50` | §3.12 |
| K2 | LLM 决策点：定 K、补请求 marker、提议参数、停止；"LLM 自选方法子集"放到 0058 | §0.2（"停止"被 M1 取代） |
| J4 | 次要对照：给/不给组织（只在确定性骨架，A1 vs A2）；A6（无 LLM，3 个种子） | §3.13 |
| I1 | 全网格精简 marker；稳定峰值（bootstrap 频率 ≥ 0.5）给完整 marker；曲线附 bootstrap 置信带；报告选中峰值比例 vs \|M\|/\|G\| | §3.5、§3.7、§4.4 |

第四轮（第三版复审后，2026-09-26）：

| # | 裁定 | 本份落实位置 |
|---|---|---|
| M1 | **搜索按维度分治**：K 固定后 1 维的方法（leiden/louvain 的 `spatial_weight`、cellcharter 的 `n_layers`）用确定性网格扫完、不调 LLM；2–3 维的方法（spagcn、graphst；设计覆盖 stagate、banksy）两阶段并行：第 1 阶段 6 组（3 组按 priority 单参数扫描 + 3 组 LLM 提议），第 2 阶段在第 1 阶段最优点附近联合微调 6 组；每方法仍为 12 组新运行 + 1 次默认，轮数由 4 降到 2；早停改为两阶段适用的规则；1-SE 简洁性保留为主要防过拟合手段；瓶颈是面板与 ARI 的相关性而非运行次数，不提高预算 | §3.8 |
| M2 | 离线 skill 进化（autoresearch 式，合并 J3 回写与 Q8）是 0059 之后的独立计划；0057 的台账要能支持它；§0 写两条路径的分工 | §0.1、§3.10.1、§9 |
| L1 | 0057 留出集**只做估计**，不判定通过：报告 D1、D2 的效应量、t 区间与 BCa 区间，供 0059 功效计算；主、次要终点全部改为描述性；**预设无效停止线**（D1 与 D2 的 95% 区间上界都 < 0 则不进入 0059 确证，先回头排查），写入冻结项；**现在就预登记 0059 的确证设计**（完整流水线 vs 直接跑 skill，单侧 α=0.05，全新数据、优先真值 K≠7），0059 的 plan 必须引用该节、不得事后换数据集 | §4.4、§4.5、§4.6、§4.9 |
| O19 | D1 先对方法取均值，单元为唯一独立单位 | §4.4 |
| O20 | 保留 A0k，作描述性指标 | §3.13、§4.4 |
| O21 | A3 的 token 按输入 + 输出计，缓存命中全额计入，另报实际计费量 | §3.12 |

### 0.4 本份对裁定的解读（owner 已按推荐采纳）

1. **Q6 的"决策"**在 M1 之后指：LLM 定 K（每个输入一次，可附一次补 marker 请求）与第 1 阶段参数提议；是否进入第 2 阶段、当前最优、简洁性由
   确定性 judge 决定。
2. **按运行次数计预算**：每方法 12 组新参数 + 1 次默认（默认取自探测、不花新运行）；calibrate 型方法每组参数至多 1 + 4 次运行（校准），另计新运行
   上限（§3.8.5）；两组（A1 与 A3）按同一每方法上限计（§3.12）。

---

## 1. 目标

| # | 目标 | 可观察的结果 |
|---|---|---|
| G1 | 固定 K 面板 `spatial_domains/3` | PAS 与 silhouette 按探测参照范围归一化后取平均；无 `X_pca` 拒绝打分；带 SE |
| G2 | `tuning.yaml` 声明每个方法如何控制 K | 新键 `k_control`；一致性测试 |
| G3 | 层 1：探测 + 稳定性曲线（证据） | K 网格 3–16 上的 f、1−rPAC、跨方法 AMI 及 bootstrap 置信带、峰值频率 |
| G4 | 层 2：LLM 在整个网格上定 K | 全网格精简 marker + 稳定峰值完整 marker + SKILL.md 全文；固定 schema、校验、回退 |
| G5 | 层 3：固定 K、按维度分治的确定性程序 | 1 维网格；2–3 维两阶段（单参数扫描 + LLM 提议 → 邻域扰动）；跳过规则；1-SE 形式的简洁性；校准 |
| G6 | 台账与可复现 | 每次 LLM 调用记模型 ID、日期、prompt 与回复哈希；种子；回放；可支持离线进化的聚合记录 |
| G7 | 工具 | `optimize_params`、`inspect_trials`、`select_result`；`run_skill` 会话级、按方法的运行预算 |
| G8 | 消融开关 | 调参开/关、组织给/不给（确定性骨架）、确定性/自由编排（A3）、无 LLM（A6）；系统提示逐字节一致 |
| G9 | 给 0058 的接口 | `selection.json` 与 `load_selection()` |
| G10 | 验证 | 开发集迭代 → 冻结 → 留出集跑一次 → 估计效应量；无效停止线；0059 预登记 |
| G11 | 清理 | 删除 `omicsclaw/autoagent/`、21 个旧测试与活文档引用 |

---

## 2. 现状（亲自核实；行号以 2026-09-26 工作树为准，实施时按符号名定位）

### 2.1 代码

| # | 事实 | 出处 |
|---|---|---|
| F1 | `ensemble/__init__.py` 不 import 任何东西，把 `tuning`、`consensus` 两个名字留给后续模块 | `omicsclaw/ensemble/__init__.py`:14-15 |
| F2 | `EnsembleRunner.prepare`（:254）、`fan_out`（:315）、`run`（:342）；首次绑定 run 时 `run.json` 记 `input_obs_columns`（:399-424）；`call_ceiling_s` 默认 15180 s（:226-240） | `omicsclaw/ensemble/runner.py` |
| F3 | `TrialResult` 字段（:102-135）；`trials.jsonl` 逐试验追加，`best.json` 按 `(run_id, method)` 以 `score` 保留 h5ad | `runner.py`；`store.py`:1-12、:153-207 |
| F4 | `run_skill`：schema 首个 required 为 `skill`（:30），policy `AUTO`+`concurrency_safe=True`（:50），描述挂载时渲染一次（:62），整个调用在 `pause_tool_timeout()` 内（:158） | `omicsclaw/ensemble/tool.py` |
| F5 | 面板 `spatial_domains/2`：CHAOS 0.4 / PAS 0.2 / spatial-Leiden AMI 0.4，kNN agreement 与 silhouette 为诊断 | `omicsclaw/ensemble/metrics/__init__.py`:45-96 |
| F6 | silhouette 的 `adjusted = (s+1)/2`（:314）；缺 `expression` 时面板照常出分（:463-467）；`load_reference` 只在 `X_pca` 存在时读入（`score.py`:52-54）——F2 裁定需要改这里 | `metrics/spatial.py`；`metrics/score.py` |
| F7 | `tuning.yaml` 的参数键与方法键是封闭集合；`MethodSpec.summary()`（:198-214）；`validate_params` 用默认值补齐活跃参数 | `omicsclaw/ensemble/space.py` |
| F8 | spatial-domains 参数（`tuning.yaml`:36-99，括号内为 priority）：leiden/louvain `resolution`(1)、`spatial_weight`(2) [0, 0.9] 默认 0.3；spagcn `spagcn_p`(1) [0.1, 0.9] 默认 0.5、`n_domains`(2)、`epochs`(3) [50, 400] log 默认 100；stagate `k_nn`(1)、`n_domains`(2)、`stagate_alpha`(3)、`pre_resolution`(4，仅 alpha>0 活跃)、`epochs`(5)；graphst `n_domains`(1)、`epochs`(2) [50, 600] log 默认 100、`dim_output`(3) {32, 64, 128} 默认 64；banksy `lambda_param`(1)、`num_neighbours`(2)、`resolution`(3)；cellcharter `auto_k`(1)、`n_domains`(2)、`auto_k_min/max`(3/4)、`n_layers`(5) [1, 5] 默认 3 | 同左 |
| F9 | 脚本在未给 `--n-domains` 时取 7（`spatial_domains.py`:969-974）；SKILL.md（:80、:91）与 `references/parameters.md`（:73）写明默认 7 | 同左 |
| F10 | **louvain 的 `spatial_weight` 在 (0, 0.9] 上无效**：`sc.tl.louvain(..., adjacency=...)` 未传 `use_weights`（`_lib/domains.py`:219），scanpy 1.11.5 默认 `False`；leiden 走 `flavor="igraph"` 用权重（:154） | 同左 |
| F11 | `open_ensemble` 自检 + GPU 检测 + 建池（`entry/ensemble.py`:216-252） | 同左 |
| F12 | `foundation_tools` 在 memory 工具后挂 `run_skill`，再挂 `install_skill_deps`（若启用）（`assembly.py`:378-383）；`build_app` 随后挂 MCP、最后 `task` | `omicsclaw/entry/assembly.py`:299-384 |
| F13 | ensemble 配置字段（`config.py`:317-360）与 `_Option`（:905-950）；`max_turns` 默认 50（:189）；`turn_timeout_s` 默认 `None`（:234） | `omicsclaw/entry/config.py` |
| F14 | `LLMProvider.generate(messages, tools=None) -> Completion`；`bind(**overrides)`；`ProviderConfig.model` 与 `with_overrides`；`DEFAULT_TEMPERATURE = 0.3`；`provider_from_env(provider, model)` | `provider/base.py`；`provider/config.py`:340、:388-465；`provider/factory.py`:91 |
| F15 | `Message` 只有文本 `content`；图像经 `omicsclaw/attachments/rendering.py` 接入 | `schema/message.py`:167-208 |
| F16 | 工具可读每轮事实 `context_value(key)`（`tools/context.py`:515），`session_id` 由 `entry/turn.py`:360 放入 | 同左 |
| F17 | 分层测试：ensemble 只可 import `schema/tools/skills/ensemble`，禁止 `entry/engine/provider/sandbox/runtime/autoagent/common`；`evaluation` 不得被运行路径 import | `tests/ensemble/test_ensemble_is_a_layer.py` |
| F18 | 0062 边界：框架不 import `skills`（`tests/sdk/test_boundary.py` B4，唯一例外 `omicsclaw/autoagent/metrics_compute.py`，:63-66；断言 `offenders == B4_KNOWN`，:162） | 同左 |
| F19 | golden：`tests/entry/golden/ensemble_off_{prompt.txt,tools.json}` 与 `test_ensemble_golden.py`；`MOUNTED_WITH_ENSEMBLE`（`tests/entry/test_permission_wiring.py`:63） | 同左 |
| F20 | 旧 autoagent：29 个 `.py`、19,173 行，不能 import；确定性循环 `optimization_loop.py`:256；LLM 提议指令 `directive.py`:66-72；judge"分数升 > 1e-8 保留，平分且偏离默认少保留"（`judge.py`:44-155，`constants.py`:12） | `omicsclaw/autoagent/` |
| F21 | autoagent 的引用：21 个 `tests/test_autoagent_*.py`；`tests/sdk/test_boundary.py`:63-66；`tests/launch/test_grammar.py`:271；`AGENTS.md`:166-167、:204、:231-232；`README.md`:41（"autoagent excepted"）、:61（"Five packages are deliberately kept … `autoagent/`"）；`docs/FRAMEWORK-REBUILD.md`:1757-1759、:1802、:1929；`docs/product-overview.md`（:53、:93、:156-158、:254、:990-991、:1032、:1533、:1609、:1634、:1996-2018）；`docs/core-features/README.md`:51、`docs/core-features/sandbox.md`:13；`docs/architecture/2026-05-18-current-architecture.md`:49、:127；`docs/architecture/skill-system.mdx`:56；`omicsclaw/surfaces/desktop/server.py`（只读参考）。另有 `README_zh-CN.md`:57 与 `docs/ARCHITECTURE.md`（:70-72、:221、:504-508、:754-815、:1059）中的 "AutoAgent" | 全仓 grep |
| F22 | 旧 consensus 成员打分：`composite = 0.6·cross_NMI + 0.4·intrinsic`；最大类占比 > 0.8 硬过滤 | `omicsclaw/runtime/consensus/scoring.py`:24-26、:61-134 |
| F23 | pytest：`addopts` 默认排除 `slow/demo/eval`；`eval` 标记为"真实 LLM 行为测试" | `pyproject.toml` |
| F24 | `spatial-preprocess`：默认 `max_mt_pct=20`（`_lib/preprocessing.py`:37-50），`--max-mt-pct` 可设（`spatial_preprocess.py`:966）；平台列表无 cosmx（`_lib/loader.py`:28-35） | 同左 |
| F25 | 记忆库每个 workspace 一个 `<workspace>/.omicsclaw/memory.db`（`entry/memory.py`:71、:103-107）；子代理用父注册表收窄后的副本（已经过闸门）与父模型（`entry/subagent.py`:138-139、:181-） | 同左 |
| F26 | MultiK 源码：`rPAC <- PAC/(1 - prop_zeroes)`，`PAC = Fn(x2) − Fn(x1)` 取共识矩阵下三角，`prop_zeroes = sum(M==0)/length(M)` 取整个矩阵 | `/tmp/mkh.R`:83-87（审核方取得） |
| F27 | **usage 只有流式路径能区分"未报告"**：`_TurnOutcome.usage` 的说明（`engine/loop.py`:126-143）写明 `StreamChunk.usage` 可为 `None` 而 `Completion.usage` 默认全零，阻塞回合无法区分"没花钱"与"没报告"；每个模型回合以 `EngineEvent.turn_end(turns, outcome.usage)` 发出（:449）；`TurnRunner` 走 `exchange_stream`（`entry/turn.py`:650），`run_turn` 的阻塞分支走 `exchange`（:292） | 同左 |
| F28 | **子代理的用量不回传父级**：`ChildRunner.delegate` 在子引擎 `exchange_stream` 上只转发 `TOOL_START` 进度并取最后的 `RunResult`（`entry/subagent.py`:244-253），`_conclusion` 只返回文本（:300-）；子代理的 `turn_end` usage 父级看不到 | 同左 |

### 2.2 数据

| # | 事实 | 核实方式 |
|---|---|---|
| D1 | 开发集 `/workspace/algorithm/zhouwg_project/data_external/DLPFC/{151673,151674}.h5ad`：3639 × 33538（151673），`X` 原始整数计数，obs 为 `in_tissue, array_row, array_col, sce.sample_name, sce.layer_guess`；151673 真值 Layer1–6 + WM，NaN 28 个 | `anndata.read_h5ad(backed='r')` |
| D2 | 其余 10 张本机没有；计数 `https://spatial-dlpfc.s3.us-east-2.amazonaws.com/h5/{id}_filtered_feature_bc_matrix.h5`（`ETag` 分段形式 `…-2`）；坐标 `https://raw.githubusercontent.com/LieberInstitute/HumanPilot/master/10X/{id}/tissue_positions_list.txt`；层注释 spatialLIBD `sce` 对象 `https://www.dropbox.com/s/f4wcvtdq428y73p/Human_DLPFC_Visium_processedData_sce_scran_spatialLIBD.Rdata?dl=1`（取自 `spatialLIBD/R/fetch_data.R`）；三者均可达。另有 SDMBench 在 figshare 的 12 张 h5ad 镜像（`https://doi.org/10.6084/m9.figshare.22548901`，API 列出 151507–151676 共 12 个文件），只作校验旁证 | `curl -I`；figshare API |
| D3 | 本机 `OmicsClaw` 环境的 R 有 `SingleCellExperiment`、`SpatialExperiment`、`zellkonverter` | `Rscript` |
| D4 | CosMx 人肝 `/workspace/dataset/private/spFoundation_SpatialCorpus/spFoundation_SpatialCorpus_by_species/Homo_sapiens/nanostring_cosmx_human_liver.h5ad`：3.58 GB，793,318 × 999，`layers['counts']` | 同 D1 |
| D5 | CosMx 的 `obsm['spatial']` 是 **FOV 内局部像素坐标**（x、y 都在 8–4248）；`donor_id`（383 个值）实际是 FOV 编号、两张 slide 共用；无全局位置，不能拼接 | 分组统计 |
| D6 | (slide, FOV) 块中细胞数 ≥ 500 的合格块：slide 1 有 269 块，K* 分布 {2: 5, 3: 24, 4: 117, 5: 86, 6: 37}；slide 2 有 376 块，K* 分布 {1: 53, 2: 115, 3: 170, 4: 38}（K* = 块内出现的 niche 种类数）。"占比 ≥ 5% 的 niche 数 ≤ 2"口径：slide 1 为 31 块，slide 2 为 222 块 | `/tmp/rev2_cosmx.py` |

### 2.3 开发集预检（只作设计依据，不是验证）

输入取自 0056 DLPFC 研究的预处理产物（`/tmp/0056_dlpfc/<slice>/input.h5ad`，默认 `max_mt_pct=20`）；脚本在 `/tmp/0057_probe/` 与复审脚本
`/tmp/rev0057_*.py`、`/tmp/rev2_*.py`、`/tmp/rev3_*.py`，均不进仓库。rPAC 一律按 MultiK 源码公式。

| # | 观察 | 数字 |
|---|---|---|
| P1 | 三个模型方法两两 ARI 的均值随 K 下降 | 151673：K=3/5/7/9/12/16 为 0.574/0.499/0.424/0.363/0.349/0.320；151674：0.583/0.383/0.356/0.351/0.382/0.340 |
| P2 | `1−rPAC` 在 K=2 最高（0.92/0.91），K≥3 后不单调；出现频率 f 有平台 | `B_sub=20`，151673：K=3…13 为 0.77/0.54/0.56/0.54/0.46/0.43/0.46/0.47/0.52/0.51/0.49；151674：0.43/0.47/0.36/0.42/0.46/0.52/0.49/0.48/0.47/0.46/0.47 |
| P3 | 若把稳定性当过滤器，结果随子采样次数翻转并落入陷阱 K=3 | `B_sub=5`：{3,5} 与 {3,7,9,12}；`B_sub=20`：{3,5,7} 与 {9,12}（H1 的依据） |
| P4 | f 的峰值在子采样重抽下的出现频率（`rev2_boot.py`） | 151673：K=4 1.00、K=6 0.65、K=11 0.59；151674：K=4 0.83、K=10 0.62、K=6 0.57、K=13 0.53；c 的峰值在两半子采样间只部分重合 |
| P5 | 按精确 K 分组，各面板组内选中者相对组内最佳 ARI 的命中与平均遗憾；另单列"同一方法、同一 K、不同参数"的组（每组 2–5 个试验） | 全部组：固定权重 5/12 0.026、4/12 0.029；组内名次 5/12 0.025、5/12 0.032；参照范围归一化 6/12 0.024、6/12 0.023；只用 silhouette 8/12 0.010、7/12 0.024。同方法组：固定权重 1/7 0.009、5/8 0.008；名次 2/7 0.010、6/8 0.001；范围归一化 3/7 0.008、5/8 0.004；只用 silhouette 2/7 0.033、3/8 0.009 |
| P6 | 回退 K 若允许只有一条曲线有定义的 K 参评，151674 会退到 K=16；要求至少两条后为 4 与 10 | `rev2_fb.py` |

---

## 3. 设计

### 3.1 模块结构与分层

```
omicsclaw/ensemble/tuning/
  __init__.py      只有包 docstring；不 import 任何子模块
  ── agent 侧（agent 进程；可 import schema/tools/skills/ensemble 的 agent 侧；不加载 numpy）──
  budget.py        RunBudget：按 (会话, 方法) 的新运行计数（原子预留）；caps() 计算上限
  search.py        维度判定、1 维网格、单参数扫描点、邻域扰动点、随机搜索、规范化与去重键
  probe.py         探测设计：K 网格、resolution 网格、子采样计划 → TrialSpec 列表
  evidence.py      读 stability.json：稳定峰值集合 M、回退 K
  calibrate.py     calibrate 型方法的 resolution 二分校准
  scoring.py       固定 K 分数：按参照范围归一化 PAS 与 silhouette、SE 传播
  judge.py         当前最优、跳过第 2 阶段的判定、1-SE 简洁性、跨方法选择
  prompts.py       类型化 prompt 输入、模板渲染、输出 schema 校验、防泄漏检查
  llm.py           ChatModel 协议、带校验与重试的调用、录制/回放（cassette）
  ledger.py        ledger.jsonl、tuning.json、reference.json、selection.json、聚合记录；Selection 与 load_selection()
  pipeline.py      两层流程编排（TuningPipeline）
  tools.py         optimize_params、inspect_trials、select_result
  templates/       k_decision.txt、propose.txt、free_task.txt（冻结时记 sha256）
  ── 执行环境侧（子进程 `python -m`，Py3.11 可 import；只 import ensemble.metrics 与本组）──
  subsample.py     写 80% 子采样输入并重算表达近邻图
  stability.py     每个 K 的 f、1−rPAC、跨方法 AMI，bootstrap 置信带与峰值频率 → stability.json
  markers.py       每个 K 的代表划分：精简 marker（全网格）与完整 marker 块（M 与补请求的 K）、嵌套表 → markers.json
  inspect.py       inspect_trials 的计算
```

- **不 import `omicsclaw.provider`**（F17）：`llm.py` 定义结构化协议 `ChatModel`（`name`、`async generate(messages, tools=None)`，只读
  `.message.content` 与 `.usage`），由 `entry` 注入。
- **不 import `skills` 的 Python 代码**（F18）：marker 与子采样直接用 scanpy/anndata；SKILL.md 作为文本经 `omicsclaw.skills` 索引读取（与 `use_skill` 同源）。
- **`evaluation` 隔离不变**：`tuning/*` 全部加入"运行路径不得 import evaluation"。真值只出现在 §4 的验证脚本（`docs/plans/0057-validation/`）。
- 分层测试扩展：agent 侧按 `ALLOWED_AGENT_SIDE`；执行环境侧只可 import `omicsclaw.ensemble.metrics` 与本组四个子进程模块；子进程探针断言
  `import omicsclaw.ensemble.tuning.tools` 不加载 numpy/pandas/scanpy。

### 3.2 数据流

```
input.h5ad（预处理后、obs 只剩 batch、含 X_pca）
   │
   ├─[层 1a 探测]  E 方法（k_control=exact）× K∈G(3–16)       ─┐  run_id=<base>-probe
   │               L 方法（k_control=calibrate）× r∈R(39 个)   ├─→ EnsembleRunner.fan_out
   │               L 方法 × r∈R × 20 个 80% 子采样             ─┘  子采样各自 run_id=<base>-sub<b>
   ├─[层 1b 证据]  stability.py：G 上 f、c=1−rPAC、a=跨方法 AMI + bootstrap 置信带 + 峰值频率 → stability.json
   │               scoring：每个 K 的参照范围（探测试验中该 K 的 PAS 与 silhouette 的 min/max）→ reference.json
   ├─[层 2a marker] 全网格精简 marker；稳定峰值集合 M 上完整 marker 块；M ∪ 补请求 K 的嵌套表 → markers.json
   ├─[层 2b 定 K]  LLM 看全部曲线、全网格精简 marker、M 上完整 marker、SKILL.md 全文；可请求至多 2 个 K 的完整 marker（一次）
   │               → chosen_k ∈ G；超出重试预算 → 回退 K
   ├─[层 3 调参]   每个方法并行，基线 = 探测中该方法在 K 下的默认参数试验（不花新运行）
   │               1 维方法：确定性网格一次扫完（§3.8.2）
   │               2–3 维方法：第 1 阶段 6 组并行（3 组单参数扫描 + 3 组 LLM 提议）
   │                           → 跳过规则 → 第 2 阶段 6 组并行（最优点邻域的确定性扰动）（§3.8.3）
   │               → judge：1-SE 简洁性选每方法最终结果；跨方法取 fixed_k_score 最高者
   └─[输出]        selection.json；ledger.jsonl；llm/NNNN.json；tuning.json（含聚合记录）
```

探测是确定性的（种子固定），同一单元上被多个臂共享（§4.3）。目录：

```
<workspace>/ensemble_runs/
  <base>-probe/ …   <base>-sub01 … <base>-sub20/ …    探测（0056 布局）
  <base>/                                               调参试验
    tuning/  ledger.jsonl  tuning.json  stability.json  reference.json  markers.json  selection.json
             llm/0001.json …     inputs/sub01.h5ad …（默认结束后删除）
```

### 3.3 `tuning.yaml` 扩展：`k_control`

方法级新增可选键（加载器校验，`schema_version` 仍为 1；无此键的方法不参与两层调参）：

```yaml
methods:
  spagcn:      {k_control: {kind: exact, param: n_domains}, …}
  stagate:     {k_control: {kind: exact, param: n_domains}, …}
  graphst:     {k_control: {kind: exact, param: n_domains}, …}
  cellcharter: {k_control: {kind: exact, param: n_domains, pin: {auto_k: false}}, …}
  leiden:      {k_control: {kind: calibrate, param: resolution}, …}
  louvain:     {k_control: {kind: calibrate, param: resolution}, …}
  banksy:      {k_control: {kind: calibrate, param: resolution}, …}
```

| 字段 | 规则 |
|---|---|
| `kind` | `exact`（参数直接等于 K）或 `calibrate`（单调影响簇数的参数，§3.8.5 二分到 K） |
| `param` | 该方法的参数名；`exact` 要求 `int`，`calibrate` 要求数值型 |
| `pin` | 可选，调参期间固定的参数值；须满足 `validate_params` |

leiden/louvain 另把 `resources.cpus` 设为 2（基本单线程；0056 的 8 核预留使池只能并发 13 个；工程参数，T10 实测后定）。一致性测试扩展：`param` 存在；
`exact` 区间覆盖 G 或记录截断；变异（改名、`exact` 指向 float、`pin` 违反约束）各自失败。

### 3.4 层 1a：探测设计（冻结项）

| 项 | 值 | 依据 |
|---|---|---|
| K 网格 G | 3, 4, …, 16（14 个整数） | 下界取 `tuning.yaml` 的 `n_domains` 下界 3（已定 Q7，与数据无关）；上界 16：L 方法在 resolution ≤ 2.0 内几乎给不出 > 16 的簇数（开发集 f(K≥16) ≤ 1.6%），超过 16 只剩单一证据 a(K)；用户仍可显式给 `k` ≤ 20 |
| E 方法 / 探测 | `kind=exact` 且可运行（本机 spagcn、graphst、cellcharter）；每个 K∈G 一次，其余默认 | 42 次运行；其中 K=7 的三次即 E 方法的默认参数基线（J2） |
| L 方法 | `kind=calibrate` 且可运行（本机 leiden、louvain） | — |
| resolution 网格 R | `[round(0.10 + 0.05*i, 2) for i in range(39)]`，即 0.10, 0.15, …, 2.00，**恰好包含 1.00** | MultiK 网格 0.05–2.00、步长 0.05（Liu et al. 2021），截到 `tuning.yaml` 下界 0.1；用 `round` 生成以免浮点累加使 1.00 变成 0.9999… |
| L 全量探测 | 每个 r∈R 一次，其余默认 | 78 次；兼作"默认参数下 resolution→K 映射"；其中 r=1.00 即 L 方法的默认参数基线 |
| 子采样 | 80% 观测、`B_sub = 20`（种子 5701–5720），只对 L 方法 | 80% 取自 Monti et al. 2003 与 MultiK；MultiK 做 100 次，此处取 20（P3、P4 显示 5 次不稳定）；1560 次运行 |
| 子采样的预处理 | 取子集后用输入的 `X_pca` 重算表达近邻图（`n_neighbors` 取预处理记录值，默认 15）；PCA 不重算 | 有意简化，写进交付记录 |

- 不向任何方法提供真值类别数（Q23）。E 方法实际簇数 ≠ 请求值时，按实际簇数归档并记 `requested_k`。
- stagate/banksy 缺包：如实失败，流程以存活方法继续；a(K) 需要 ≥ 3 个划分，否则无定义。

### 3.5 层 1b：稳定性曲线与 marker 点（证据，不过滤）

**三条曲线**（K∈G，执行环境 `stability.py` 计算）：

| 曲线 | 定义 | 文献 |
|---|---|---|
| f(K) 出现频率 | L 方法子采样运行中实际簇数为 K 的比例 | MultiK（Liu et al., *Genome Biol* 22:232, 2021，doi:10.1186/s13059-021-02445-5；Europe PMC 全文 PMC8375188 核对） |
| c(K) = 1 − rPAC(K) | 所有给出 K 的子采样运行合成共识矩阵 M_K；`PAC = CDF(0.9) − CDF(0.1)`（上三角元素的经验分布）；`rPAC = PAC / (1 − prop_zeroes)`；K 上少于 2 次运行时无定义 | Monti et al., *Mach Learn* 52:91–118, 2003；Şenbabaoğlu et al., *Sci Rep* 4:6207, 2014；rPAC：MultiK 源码（F26）。实现取上三角计 `prop_zeroes`，MultiK 取整个矩阵，二者只差 O(1/n) |
| a(K) 跨方法一致性 | K 上各方法划分两两 AMI 的均值；成员 = 每个 E 方法在 K 上的探测划分 + 每个 L 方法全量扫描中簇数为 K 的划分（多个时取 resolution 居中者）；少于 3 个划分时无定义 | cross_NMI 思想（F22；Strehl & Ghosh, *JMLR* 3:583–617, 2002）；改用 AMI（Vinh et al., *JMLR* 11:2837–2854, 2010） |

观测数 > 5000 时，M_K 在固定的 5000 个观测上计算（种子 5700），记 `consensus_subset=5000`。

**bootstrap 置信带与峰值频率**（I1）：f、c 对 20 个子采样编号有放回重抽 1000 次（种子 5800）；a 对观测有放回重抽 200 次（种子 5801）；每个 K 报 2.5%/97.5%
分位。峰值 = G 上不小于相邻 K 的点（端点只比一侧）；f 与 c 只在 `f(K) ≥ 2.5%` 处参与（MultiK 频率门槛按比例换算）。**峰值频率** = 该 K 在重抽中是
该曲线峰值的比例；**稳定峰值** = 任一曲线上峰值频率 ≥ 0.5 的 K；**M** = 稳定峰值的并集。不设固定补充点。

**呈现方式（冻结，只有一种）**：G 上逐 K 一行——f、c、a 的原值与置信带、名次、峰值频率、运行数、a 的成员方法、是否在 M；外加每个 K 的精简 marker（§3.7）。
表头只给中性定义，不给"应当选峰值或选最稳"的指引，不给合成分数。

**回退 K**（LLM 超出重试预算、A6 臂）：只在**至少两条曲线有定义**的 K 中选（f、c 的"有定义"含 `f(K) ≥ 2.5%` 门槛；a 为至少 3 个划分）；每条曲线的名次
**只在该曲线有定义的 K 之间**计算；取名次平均值最好的 K；平手取 a 大者，再平手取 K 小者。

### 3.6 固定 K 面板 `spatial_domains/3`

**成员**：`pas`（校正值）与 `silhouette_pca`（原值）两项计分；CHAOS、`spatial_leiden_ami`、`knn_agreement` 保留计算、权重 0。

**组合方式（默认 N1：按参照范围归一化后平均）**：对选定 K，参照集 = 探测试验中簇数为 K 的全部 ok 试验（E 方法与 L 方法全量探测）；每个成员 j 取参照集上的
`lo_j = min`、`hi_j = max`，`fixed_k_score = mean_j (x_j − lo_j)/(hi_j − lo_j)`（不裁剪，可越出 [0,1]、可为负）。参照在探测后固定，写进 `reference.json`。某成员
`hi_j = lo_j` 或参照集不足 2 个试验时，该成员退出平均并记 `reference_degenerate`；两者都退出时该 K 无固定 K 分数，调参只报告原值（记入台账）。

**需要知道的性质**：一个方法的 `fixed_k_score` 依赖**其他方法**探测试验的极值；换一组可运行方法，同一试验的分数会变。同一单元内比较无害，不同单元、不同
方法集合之间不可直接比较（0058、离线进化都要注意）。

**为什么选"参照范围"而不是"组内名次"**：(1) 需要绝对、稳定的分数（judge 的门槛与 1-SE 要用 SE，0058 要用分数）；组内名次随新试验回溯改变、无 SE 可传。
(2) 探测是两组共享的材料（§3.12），打分函数完全相同（Q26）。(3) **在三种组合面板（固定权重、组内名次、参照范围）之中**，P5 的范围归一化在"全部组"上
两张切片都最好（6/12、6/12）；但**同方法组的差异 ≤ 0.01、每组只有 2–5 个试验，证据弱**。名次平均（N2）作为 §4.6 的唯一预登记比较。

**论证**：PAS 是 0056 报告 DLPFC 节中唯一在一张切片上单独与 ARI 相关且 CI 不跨 0 的成员（+0.37 [+0.10, +0.61]），但奖励空间平滑（`spatial_weight` 0.6/0.9 的
PAS ≥ 0.98）；silhouette 跨方法比较强（P5 全部组 8/12、7/12），同方法调参组最差（151673 平均遗憾 0.033），偏好 `spatial_weight=0`。二者在 `spatial_weight` 上
方向相反，是取平均的理由；量纲悬殊是必须先归一化的理由。CHAOS、AMI 降为诊断（0056 报告）。silhouette 用原值（`(s+1)/2` 把随机水平放在 0.5）。

**`metrics.json` 的 `score` 字段**：打分子进程看不到参照集，`score` 记绝对值 `0.5·clip(PAS_adj) + 0.5·clip(sil)`，只用于 0056 运行器的 h5ad 保留（F3）；
**所有决策用 `fixed_k_score`**，由 `tuning/scoring.py` 从分量与 `reference.json` 计算。`run_skill` 返回里在该 run 存在该 K 的参照时附 `fixed_k_score`，否则为
`null` 并提示用 `inspect_trials`；描述加一句"分数只在簇数相同的试验之间可比"。

**F2：拒绝打分**。`load_reference` 在声明了 `expression_obsm` 而输入没有时抛 `ScoreError`；`optimize_params` 与 `run_skill` 在准备阶段用 `--describe-input`
（扩展为同时返回 `obsm_keys`、`n_vars`）提前拒绝。

**SE**：`SE_pas_adj = sqrt(PAS·(1−PAS)/n)/E[PAS]`；`SE_sil = sd(s_i)/sqrt(m)`；`SE_fixed = sqrt(Σ_j (SE_j/(hi_j−lo_j))²)/2`。单次划分的测量误差，忽略空间自相关
（偏小）与方法自身的随机性。

**影响面**：`panel_version` 变为 `spatial_domains/3`；0056 的面板测试、冒烟断言更新；参照缓存键随版本变化。

### 3.7 层 2：LLM 定 K 的 prompt 契约

**输入**（`prompts.KDecisionInput`，类型化；渲染函数不接受任意字符串拼接）：

| 字段 | 内容 | 来源 |
|---|---|---|
| `skill_md` | SKILL.md 全文（与 `use_skill` 返回的正文同源）与 `references/parameters.md` 全文 | `omicsclaw.skills` 索引（J1） |
| `data` | 平台、物种、观测数、基因数、每观测计数与基因数中位数、坐标范围与长宽比、预处理参数、obsm 键名、批次数 | 输入 h5ad 与预处理 `result.json`；不含 obs 列名或取值（批次数除外） |
| `tissue` | 组织描述（完整名称）或缺省 | 调用方；`ensemble_tuning_tissue=false` 时强制缺省 |
| `curves[]` | G 上每个 K：f、c、a 原值、置信带、名次、峰值频率、运行数、a 的成员方法、是否在 M | `stability.json` |
| `compact_markers[]` | **G 上每个 K**：代表划分（该 K 探测试验中 `fixed_k_score` 最高者）的方法与参数；每个 domain 的占比与 top-3 marker 基因名 | `markers.json` |
| `full_markers[]` | M 中每个 K（及补请求的 K）：每个 domain 的占比、同标签近邻比例（k=10）、质心（归一到 [0,1]）、top-5 marker（Wilcoxon，附 log2FC、组内/组外表达比例） | `markers.json` |
| `nesting` | M ∪ 补请求 K 中相邻 K 之间：较细划分每个 domain 主要落在较粗划分的哪个 domain、重叠比例 | `markers.json` |
| `images` | 仅当开关开启：M 中每个 K 代表划分的空间图 | Q13，默认关，O5 |

marker 在输入 `X`（log 归一化）上用 `scanpy.tl.rank_genes_groups(method="wilcoxon")`，每个 K 一次；观测数 > 20000 时在分层随机的 20000 个观测上做（工程上限）。

**两步交互**：第一次回复可以是最终决定，或补请求 `{"request_markers": [7, 9]}`；合法条件：1–2 个 K、全部 ∈ G、全部 ∉ M、此前未请求过。合法请求 → 计算这些 K 的
完整 marker、按 M ∪ 请求 K 重算嵌套表、追加在原 prompt 之后再问一次（这一次只能给最终决定）。

**最终输出 schema**：

```json
{
  "chosen_k": 7,
  "rationale": "≤1200 字符",
  "evidence": [
    {"k": 7, "kind": "markers", "domain": "3", "genes": ["GENE_A", "GENE_B"], "reading": "≤200 字符"},
    {"k": 7, "kind": "curve", "curve": "f | c | a", "reading": "≤200 字符"},
    {"k": 7, "kind": "skill_md", "quote": "≤200 字符，SKILL.md 原文片段", "reading": "≤200 字符"}
  ],
  "confidence": "low | medium | high"
}
```

**校验**：可解析（剥代码围栏）；字段齐全；`chosen_k` ∈ G；`evidence` 1–10 条；`markers` 类的 `(k, domain)` 存在于已提供的 marker，`genes` 全部出现在该 domain
已提供的基因里；`curve` 类的 `k` ∈ G；`skill_md` 类的 `quote` 必须是提供文本的子串；`rationale` 非空。

**重试预算（全文统一：每次 LLM 决策至多重试 2 次）**：K 决策的预算跨两步累计为 2 次。最终决定不合规、补请求不合法（K ∈ M、K ∉ G、超过 2 个、第二次请求、
第二步仍发请求）都算校验失败、消耗一次重试，错误信息附合法取值范围。超出预算或 provider 报错 → 回退 K（§3.5），`k.source="fallback"`。

### 3.8 层 3：固定 K、按维度分治的确定性程序（M1）

**设计前提**：调参的瓶颈是**固定 K 面板与 ARI 的相关性**（0056 报告：DLPFC 上最好的单成员与 ARI 的 ρ 只有约 +0.3–0.4，同方法组内差异 ≤ 0.01），不是运行次数。
多跑试验只会让"面板最优"更可能是面板噪声的最大值，因此**不提高预算**，并把 1-SE 简洁性（§3.8.4）作为最终选择的主要防过拟合手段。

#### 3.8.1 维度判定与预算

K 固定后，每个方法的**搜索维度** = 在默认值下活跃、且不被 `k_control.param` 与 `pin` 占用的参数个数。本机与设计覆盖的方法：

| 方法 | 剩余维度（priority 顺序） | 策略 |
|---|---|---|
| leiden、louvain | `spatial_weight`（1 维；`resolution` 由校准占用） | 1 维网格 |
| cellcharter | `n_layers`（1 维；`auto_k` 钉住、`auto_k_min/max` 不活跃） | 1 维网格 |
| spagcn | `spagcn_p`、`epochs`（2 维） | 两阶段 |
| graphst | `epochs`、`dim_output`（2 维） | 两阶段 |
| stagate（本机缺包） | `k_nn`、`stagate_alpha`、`epochs`（3 维；`pre_resolution` 仅在 alpha > 0 时活跃，不计入维度，但可随提议出现） | 两阶段 |
| banksy（本机缺包） | `lambda_param`、`num_neighbours`（2 维；`resolution` 由校准占用） | 两阶段 |

维度 ≥ 4 的方法（本 skill 没有）按 priority 取前 3 维作为搜索维度，其余保持默认，交付记录注明。

**每方法预算**：1 次默认（取自探测，不花新运行）+ 至多 **12 组新参数**；轮数至多 2（1 维方法 1 轮）。

#### 3.8.2 1 维方法：确定性网格

- 不调用 LLM，一次并行扫完，无早停。
- `spatial_weight`（leiden、louvain）：`[round(0.075*i, 3) for i in range(13)]`，即 0, 0.075, …, 0.9 共 13 点，默认 0.3 是第 5 点，其余 12 点为新参数。
  louvain 的 `spatial_weight` 在 (0, 0.9] 上无效（F10），会产生重复划分，按 `duplicate_of` 记录、照常计数，不另作处理（修复留给 0059）。
- `n_layers`（cellcharter）：1–5 全部 5 个值，默认 3 之外 4 个新参数（预算余量不使用）。
- 类别型 1 维参数（本 skill 没有）：全部取值。整数型取值数超过 13 时在区间上等距取 13 点（log 参数在对数尺度）。

#### 3.8.3 2–3 维方法：两阶段并行

**第 1 阶段（6 组并行）**：

- **3 组单参数扫描**（确定性，每组只改一个参数、其余取默认）：对 priority 最前的参数取值。
  - 3 维：前三个参数各 1 组，取值为该参数区间内**离默认值最远的端点**（数值型按区间长度归一化，log 参数在对数尺度；类别型取列表中离默认索引最远者；平手取较大值）。
  - 2 维：priority 1 的参数取两个端点各 1 组，priority 2 的参数取离默认最远的端点 1 组。
  - 例：spagcn → `spagcn_p=0.1`、`spagcn_p=0.9`、`epochs=400`；graphst → `epochs=50`、`epochs=600`、`dim_output=128`。
- **3 组 LLM 提议**（可同时改多个参数），见 §3.8.6。

**跳过规则**：若第 1 阶段没有任何一组的 `fixed_k_score` 超过**默认结果的分数 + 默认结果的 `SE_fixed`**，跳过第 2 阶段，剩余 6 组预算不使用。理由：第 2 阶段只在第 1 阶段
最优点附近微调；若最优点与默认在测量误差内不可区分，最终的 1-SE 规则本来就会偏向默认或更简单的配置，局部微调没有可兑现的收益；跳过规则与 1-SE 使用同一误差口径。

**第 2 阶段（6 组并行，确定性邻域扰动）**：以第 1 阶段 `fixed_k_score` 最高的配置为中心 c（平手取偏离默认少者）：

- 每个搜索维度的步长 δ_j = 该参数区间长度的 1/8（log 参数在对数尺度；整数取整后至少 1；类别型取相邻取值）。
- 3 维：每维 ±δ_j 共 6 点。
- 2 维：每维 ±δ_j 共 4 点，另加 2 个对角点：沿"从默认指向 c"的方向（某维 c 等于默认时取正方向）在两维同时移动 +δ 与 −δ 各 1 点。
- 越界的点裁到区间内；裁剪后与已有配置重复的点，改取该维 2δ_j 的反方向点；仍重复则丢弃（该组预算不使用）。

**为什么第 2 阶段用确定性扰动而不用 LLM 提议**：(1) M2 的分工：运行时 LLM 的价值在选 K、选方法与 consensus，局部微调处面板噪声（SE 与组内差异同量级）主导，领域知识
可贡献的信息少；(2) 可复现、无 LLM 采样方差、少一次模型调用；(3) 使 A1 与 A6（无 LLM）之差只来自定 K 与第 1 阶段的 3 组提议，归因清楚。

**第 1 阶段的 LLM 提议与单参数扫描同时并行**：LLM 在提议时只看到默认结果（来自探测）与单参数扫描的**计划**（不是结果），因此它的 3 组是在默认点信息下的独立提议。

#### 3.8.4 最终选择（Q25，主要防过拟合手段）

- **每方法**：S = {`fixed_k_score` ≥ 最优 − 最优的 `SE_fixed` 的 ok 且簇数为 K 的试验（含默认）}；在 S 中按（偏离默认的活跃参数个数，归一化偏离距离，试验序号）
  字典序取最小。钉住 K 的参数不计偏离；数值参数距离 `|x − default|/(high − low)`（log 参数在对数尺度），类别与布尔不等即 1。**这是借用 1-SE 规则形式的
  启发式**：Breiman et al.（1984）与 Hastie et al.（*ESL* §7.10）的 SE 是交叉验证误差的折间标准误，本份的 SE 是单次划分的测量误差（§3.6），二者含义不同，
  不声称继承其统计性质。
- **没有 ok 且簇数为 K 的试验**（全部 `off_k`、`unreachable_k` 或失败）：该方法的答案**回退为它的默认结果**，`status="fallback_default"`（可能不在 K 上）。
- **跨方法**：在簇数为 K 的各方法答案中取 `fixed_k_score` 最高者，即流水线的单一答案 `final`；没有任何方法在 K 上有答案 → `final=null`、`status=failed`。

#### 3.8.5 calibrate 型方法的校准

参照 SpaGCN 的 `search_res`（Hu et al., *Nat Methods* 18:1342–1351, 2021）：每组参数先按 resolution 初值（1 维网格与邻域扰动用探测映射插值；LLM 可给初值）跑一次；
簇数 ≠ K 时在对数尺度上二分（端点取台账中同组其余参数下"簇数 < K 的最大 r"与"簇数 > K 的最小 r"，缺失时用 [0.1, 2.0]），最多 C=4 次追加运行；未命中 → 最接近者
标 `off_k`、不进入选择；越过区间端点仍到不了 K → `unreachable_k`。

**每方法新运行上限**（A1 与 A3 相同）：E 方法 12 次；calibrate 型 12 × (1 + C) = 60 次。基线若需要校准（探测中没有簇数为 K 的默认试验），其校准运行也计入。

#### 3.8.6 第 1 阶段提议的 prompt 契约

**输入**（`prompts.ProposeInput`）：方法名；钉住的 K 与 `k_control`；`MethodSpec.summary()`（去掉钉住参数）；本方法的搜索维度；默认结果（参数、簇数、`fixed_k_score` ± SE、
PAS 与 silhouette 原值）；单参数扫描的 3 组参数（计划，不含结果）；calibrate 型附探测得到的 resolution→K 映射；**SKILL.md 与 `references/parameters.md` 全文**（J1）；数据摘要；
组织（若给）；规则（区间是硬约束、不得与默认或扫描点重复、第 2 阶段将在最优点附近自动微调、最终按简洁性规则选择）。

**输出 schema**：`{"proposals": [{"params": {...}, "why": "≤300 字符"}]}`（恰好 3 组）。

**校验与重试**：每组经 `validate_params`；含钉住参数须等于钉住值；规范化后与默认、扫描点及同批互不重复。**不合格的组被丢弃，不消耗重试**，缺额用随机搜索补足
（`random.Random(seed)`，seed = `int(sha256(run_id|method|stage1))`，数值参数均匀、log 参数对数均匀、类别均匀；Bergstra & Bengio, *JMLR* 13:281–305, 2012），记
`source="random_fallback"`；整批解析失败才算校验失败，至多重试 2 次，超出则 3 组全部随机补足。

**重复划分**：按标签规范化指纹检查，与已有试验相同记 `duplicate_of`，照常计数（F10）。

### 3.9 防泄漏检查

只防**我们注入的真值**造成的直接数值泄漏（J1、H4）。检查失败时不发请求，抛 `LeakError`、写台账、该步走回退（或驱动不启动该单元）：

1. **结构**：prompt 只能由类型化输入渲染；数据摘要构造函数不接收 obs 列；输入的 `input_obs_columns`（`run.json`）必须 ⊆ `ensemble_obs_allowlist`（benchmark 设 `batch`），
   否则 `optimize_params` 与 `run_skill` 拒绝（E3）。
2. **计数短语**：只作用于**我们注入的字段**——组织字符串、数据摘要、三份模板、驱动渲染的自由编排任务消息。带词边界的正则：英文
   `\b(\d+|one|two|…|twenty)\b\s*[-‐]?\s*\b(layers?|regions?|zones?|niches?|domains?|areas?)\b`，中文 `(\d+|[一二三四五六七八九十]+)\s*(个)?(层|区域|分区|区)`。模板一律写 `K=7`。
3. **不检查的字段**：SKILL.md 与 `references/parameters.md` 全文、试验输出（标签派生的统计、失败日志尾部）——它们不可能携带我们注入的真值。
4. **组织字符串**用完整名称（如 `human dorsolateral prefrontal cortex`），不设其他措辞限制；数据集名称不禁。
5. **测试**：golden 模板与典型组织字符串零误报；每个计数短语各有一个注入测试断言 `LeakError` 且 provider 调用次数为 0；断言 SKILL.md 全文与日志夹具不经过该检查。
6. **不透明编号**只为保住 G4 消融：验证单元的输入路径、`run_id`、`batch` 取值用 `u07`、`b0`，不出现切片号。

### 3.10 台账与可复现

`tuning/ledger.jsonl` 每行一个事件（`seq, at (UTC ISO), kind, ...`）：

| kind | 关键字段 |
|---|---|
| `start` | 输入路径与 sha256、`input_obs_columns`、方法列表、arm、组织是否给出、全部冻结参数、面板版本、`tuning.yaml`、SKILL.md 与模板 sha256、代码摘要、模型 ID、provider、温度、日期 |
| `probe_trial` / `trial` | run_id、方法、trial、参数、`requested_k`、簇数、`score`、`fixed_k_score`、SE、状态、来源（`probe/baseline/grid/sweep/llm/random_fallback/neighborhood/calibration`）、阶段、`off_k`、`duplicate_of` |
| `stability` | G 上每个 K 的 f、c、a、置信带、名次、峰值频率；M；回退 K；`reference.json` 摘要 |
| `llm_call` | 用途、provider、解析后的模型 ID、温度、`max_tokens`、思考预算、时间、延迟、用量（输入/输出/缓存）、模板与渲染后 prompt 的 sha256、回复 sha256、重试序号、校验结果；全文另存 `llm/NNNN.json` |
| `k_decision` | chosen_k、来源（`llm/fallback/user`）、是否在 M 中、补请求的 K、理由、证据、置信度 |
| `stage` | 方法、阶段、计划的配置及来源、是否跳过第 2 阶段及依据（第 1 阶段最优、默认分数与 SE） |
| `select` | 每方法最终选择（S 集合与简洁性排序、是否 `fallback_default`）与跨方法选择 |
| `leak_refused` | 哪一层、命中的模式 |

**种子**：子采样 5701–5720；共识子集 5700；bootstrap 5800/5801；随机补足由 `sha256(run_id|method|stage1)` 派生，A6 另加种子索引 s∈{1,2,3}；面板沿用 0056 常量；
各方法自身种子由 skill 决定（GNN 固定 42，leiden `random_state=0`）。

**回放**：`CassetteChatModel` 按"用途 + 渲染后 prompt 的 sha256"取回复，命中不到即报错。skill 结果确定时，同一输入、同一冻结参数、回放同一 cassette，`selection.json`
除时间戳外逐字节相同（验收 11）。

#### 3.10.1 可支持离线进化的聚合记录（J3、M2；只定格式、不实现）

`tuning.json` 含一条 `omicsclaw.ensemble.tuning_record/1` 记录，字段按"跨数据集聚合、提炼默认值或提示、再在留出数据检验迁移"所需设计：

| 字段组 | 内容 |
|---|---|
| 数据描述 | 平台、物种、组织字符串（若给）、观测数、基因数、计数与基因数中位数、预处理参数、输入 sha256 |
| K | chosen_k、来源、是否在 M、G 上三条曲线与峰值频率的摘要、回退 K |
| 每方法 | skill 默认参数、默认试验的 `fixed_k_score`（若簇数 = K）、全部评估配置（参数、来源、阶段、分数 ± SE）、最终参数、参数相对默认的偏离向量（按参数名）、是否跳过第 2 阶段、是否 `fallback_default` |
| 溯源 | 面板版本、`tuning.yaml` 与 SKILL.md 的 sha256、代码摘要、模型 ID、日期、臂 |

记录**不含任何真值指标**；验证脚本另写 `eval.json`（ARI 等），以 `run_id` 关联。离线进化计划（0059 之后）读取这两类文件。

### 3.11 工具与审批

三个新工具与 `run_skill` 同属 ensemble 开关；描述挂载时渲染一次，不随组织开关、预算与看图开关变化。

**`optimize_params`**

```json
{
  "type": "object",
  "properties": {
    "skill":   {"type": "string"},
    "input":   {"type": "string", "description": "workspace path of the preprocessed .h5ad (needs obsm X_pca)"},
    "methods": {"type": "array", "items": {"type": "string"}},
    "tissue":  {"type": "string", "description": "tissue type, for example its full anatomical name; never a number of regions or layers"},
    "k":       {"type": "integer", "description": "a number of domains the user asked for; skips choosing K"},
    "run_id":  {"type": "string"},
    "images":  {"type": "boolean"}
  },
  "required": ["skill", "input"],
  "additionalProperties": false
}
```

- policy：`MEDIUM`、`AUTO`、`read_only=False`、`concurrency_safe=False`、`writes_workspace=True`、`touches_network=True`、`allowed_in_background=False`、
  `tags={"skills","ensemble","tuning"}`。规则主参数为 `skill`（`permission/rules.py` `principal_key`，:449）。
- 整个调用在 `pause_tool_timeout()` 内，自设墙钟上限 `ensemble_tuning_max_s`；`report_progress` 报阶段。
- `tissue` 过 §3.9-2；`k` 给出时跳过层 1–2；`images=true` 而部署未开 → 忽略并写明。
- 返回紧凑 JSON：`status`、`chosen_k`（来源、理由摘要）、每方法（最终试验、参数、`fixed_k_score` ± SE、评估组与新运行数、是否跳过第 2 阶段、是否 `fallback_default`）、`final`、
  `selection` 与 `ledger` 路径、LLM 调用数、回退数、墙钟。

**`inspect_trials`**：`{run_id, trials:[{method, trial}], markers_for?:{method, trial}, top_n?≤10}` → 各试验簇数、`fixed_k_score`（有参照时）与分量、两两 AMI、指定试验的
marker。policy `LOW`、`AUTO`、`read_only=True`、`concurrency_safe=True`。

**`select_result`**：`{run_id, k, final:{method, trial}, per_method:{method: trial}, rationale}` → 校验试验存在、ok、簇数一致，写 `selection.json`。policy `LOW`、`AUTO`、
`read_only=False`、`concurrency_safe=False`。

**`run_skill` 的会话预算**：`ensemble_run_budget`（空为不限；形如 `leiden:60,louvain:60,spagcn:12,graphst:12,cellcharter:12` 或单个整数）。`RunBudget` 以
`(context_value("session_id"), method)` 分账；`prepare` 成功后、分配试验目录前原子预留，校验失败不计，试验失败照计；超出 → `ToolArgumentError`。同会话的
`optimize_params` 从同一账户扣除。

**审批**：全部 `AUTO`；部署可用规则改 `ask`。`read-only` 模式拒绝 `optimize_params` 与 `select_result`，放行 `inspect_trials`。三个工具不进 `_WITHHELD_FROM_SUB_AGENTS`。

### 3.12 agent 自由编排组（A3，次要分析）

回答的问题：**确定性骨架与 agent 自己编排相比如何**（K1）。A3 不受 M1 的搜索策略约束，它自己决定怎么用预算。

| 项 | 做法 |
|---|---|
| 工具表 | `run_skill`（按方法预算）、`inspect_trials`、`select_result`，以及部署的其余工具（含 `use_skill`）；不挂 `optimize_params`（`ensemble_tools=free`） |
| 共享探测 | 与确定性组共用同一次探测：任务消息给出同一份证据（三条曲线与置信带、全网格精简 marker、M 上完整 marker、嵌套表、**resolution→K 映射**，与 K 决策 prompt 同一渲染函数），并把 `reference.json` 与探测试验的标签复制进本组 workspace 的 `ensemble_runs/<base>-probe/`；探测不计入预算，其中的默认参数试验对两组都是"不花新运行的基线" |
| 运行预算 | 与 A1 相同：**每个方法 12 组新参数 + 1 次默认**；以新运行计为 E 方法 12、calibrate 型 60（`budget.caps()` 同一函数）；另报两组实际消耗的 GPU 秒与 CPU 秒 |
| 同模型 | 主 agent 模型 = 确定性组 `ensemble_tuning_model` 的解析结果；验证时两组显式设为同一模型 ID |
| 同初始信息 | 任务消息 `templates/free_task.txt` 的共同部分与确定性组 prompt 同一渲染函数产出：数据摘要、组织、探测证据、各方法 `summary`、SKILL.md 与 parameters.md 全文、每方法预算；要求以 `select_result` 结束并给出每个方法在同一 K 下的最佳试验 |
| 系统提示 | 部署的标准系统提示（与 golden 逐字节相同，§3.13） |
| 轮次 | `max_turns = 50`（引擎配置，F13） |
| token 计数 | 按**主 agent 引擎每个 `turn_end` 事件的 usage** 累计（F27），**计入子代理**（T8 让 `ChildRunner` 把子引擎每个 `turn_end` 的 usage 经工具上下文的用量通道上报给驱动，F28）；输入 + 输出，**缓存命中全额计入**（O21），另报 provider 报告的实际计费量（缓存折扣后）。驱动只走流式路径（`TurnRunner`/`exchange_stream`）；任一 `turn_end` 的 usage 为 `None`（provider 未在流中报告用量）→ **拒绝运行该单元**并报错，因为阻塞路径的零用量无法与"未报告"区分（F27） |
| token 上限 | 初值 3M；T10 按开发集上 A3 每次运行 token 分布的 **p95** 确定并冻结（粗估每次 2–3M） |
| 超限处理 | 达到 `max_turns` 或 token 上限而未 `select_result` → 驱动发一条预登记提醒（"Please finish now by calling select_result."），作为**一次 `run_turn`**（一次交换）执行，该次 `max_turns=2`（够一次工具调用加一次收尾回复），其 token 照常计入；仍未调用 → 该次运行记失败 |

**隔离**（验证时，每个"单元 × 臂 × 重复"）：

- 独立 workspace：`<root>/<uid>/<arm>/r<k>/ws/`，`.omicsclaw/memory.db` 在启动前不存在、由本次运行新建；各自的规则文件、`ensemble_runs/`。
- 规则文件对 `bash`、`web_fetch`、`web_search` 设 `deny`（工具仍挂载）；`use_skill` 不禁用（J1）。本机无 docker，这是代替沙箱的防线，0059 起改用真实沙箱。验证配置
  关闭 MCP（`mcp=None`）。
- 为什么读不到其他臂的产物：文件工具经 `Workspace.resolve`，跟随符号链接后仍须落在本 workspace 内（0056 F16）；`memory_search` 只读本 workspace 新建的 `memory.db`（F25）；
  `bash` 与网络被拒；原始数据与真值在 workspace 之外；`use_skill` 只返回 skill 正文与目录路径。
- 子代理使用父注册表收窄后的副本，每个工具都已被同一闸门包住（F25），同受规则约束；测试钉住"子代理调用 `bash` 被拒"。

### 3.13 配置与消融开关矩阵

**新增配置**（全部经 `_Option`；同步 `.env.example` 与 `tests/test_env_example.py`）：

| 字段 | 默认 | 含义 |
|---|---|---|
| `ensemble_tools` | `all` | `all`：`run_skill, inspect_trials, select_result, optimize_params`；`free`：前三者；`tuning`：只 `optimize_params`；`ensemble=false` 时全不挂 |
| `ensemble_run_budget` | `""` | 会话级 `run_skill` 预算（总数或按方法），空为不限 |
| `ensemble_tuning_model` / `_provider` | `""` | 空 = 与主 agent 相同（Q28） |
| `ensemble_tuning_tissue` | `true` | `false` 时 `optimize_params` 丢弃 `tissue` 并记 `tissue_withheld=true` |
| `ensemble_tuning_images` | `false` | Q13 |
| `ensemble_tuning_budget` | `12` | 每方法新参数组数（M1）；benchmark 冻结 |
| `ensemble_tuning_max_s` | `43200` | 一次 `optimize_params` 的墙钟上限（工程上限） |
| `ensemble_obs_allowlist` | `""` | 非空时输入 obs 列必须 ⊆ 它 |

**臂**：

| 臂 | 角色 | 调参 | 组织 | 编排 | 要点 |
|---|---|---|---|---|---|
| A0 默认 | 基线 | 关 | — | — | **直接用 skill 默认值**（J2）：spagcn/graphst/cellcharter `n_domains=7`（cellcharter `auto_k=false`），leiden/louvain r=1.0、w=0.3；全部取自探测试验。T10 核验它与直接跑 skill 逐 spot 一致 |
| A0k | 描述性参照 | 关 | — | — | cellcharter `--auto-k`（默认 `auto_k_min=2`、`auto_k_max=10`），每单元 1 次运行；方法内置的"自己定 K"（O20） |
| A1 | 主 | 开 | 给 | 确定性 | `ensemble_tools=tuning`，给 `tissue`；3 次重复 |
| A2 | 次要（J4） | 开 | 不给 | 确定性 | `ensemble_tuning_tissue=false`，任务文本不含组织；3 次重复 |
| A3 | 次要（K1） | 开 | 给 | 自由编排 | `ensemble_tools=free`，按方法预算；2 次重复 |
| A6 | 次要（J4） | 开（无 LLM） | — | 确定性 | K 取回退 K；第 1 阶段的 3 组 LLM 提议改为随机搜索；其余与 A1 相同；3 个种子 |

验证时 A1/A2/A6 由驱动直接调用 `TuningPipeline`，A3 经 `open_app` + `TurnRunner`（流式）驱动主 agent。

**系统提示逐字节一致**（沿用 0056 golden，F19）：指引只在工具描述里，不改 `CLAUDE.md`。测试：`ensemble_tools ∈ {all, free, tuning}` × `ensemble_tuning_tissue` ×
`ensemble_run_budget ∈ {"", 按方法}` × `ensemble_tuning_images` 的全部组合下，系统提示等于 `tests/entry/golden/ensemble_off_prompt.txt`；工具表等于 golden 工具表在
`memory_write` 与 `task` 之间按固定顺序插入该模式的 ensemble 工具，其余逐字节不变；同一模式下工具描述与其余开关无关。新增 golden
`tests/entry/golden/ensemble_tools_all.json`。`install_skill_deps` 启用时排在这四个之后（F12）。

### 3.14 给 0058 的输出接口

`selection.json`（`ledger.Selection`；`load_selection(path) -> Selection`，校验 schema 与路径）：

```json
{
  "schema": "omicsclaw.ensemble.selection/1",
  "status": "ok | partial | failed",
  "arm": "det | free | random | user",
  "skill": "spatial-domains", "input": "…", "input_sha256": "…",
  "panel_version": "spatial_domains/3",
  "k": {"chosen": 7, "grid": [3, 16], "stable_peaks": [4, 6, 11], "requested_markers": [7],
        "in_stable_peaks": false, "source": "llm | fallback | user | agent",
        "stability": "stability.json", "decision": "llm/0001.json"},
  "reference": "reference.json",
  "methods": {
    "cellcharter": {"status": "ok | fallback_default | failed", "run_id": "…", "trial": "t0012", "params": {…},
                    "fixed_k_score": 0.71, "se": 0.02, "n_labels": 7,
                    "labels": "<…>/labels.csv.gz", "h5ad": "<…> | null",
                    "evaluated": 5, "new_runs": 4, "strategy": "grid | two_stage", "stage2_skipped": false}
  },
  "final": {"method": "cellcharter", "run_id": "…", "trial": "t0012"},
  "budget": {"caps": {"leiden": 60, …}, "used": {…}, "gpu_s": 812.4, "cpu_s": 5210.0},
  "provenance": {"model": "…", "provider": "…", "temperature": 0.3, "date": "2026-…",
                 "templates_sha256": {…}, "skill_md_sha256": "…", "freeze_sha256": "…|null",
                 "code_digest": "…", "seeds": {…}, "tissue_given": true}
}
```

0058 约定：

- consensus 成员为 `methods.*` 中 `status=ok` 且簇数等于 `k.chosen` 的成员；`fallback_default` 的成员簇数可能不同，由 0058 决定是否纳入。
- **成员权重不能直接用 `fixed_k_score`**：它可为负、可大于 1，且依赖同一单元上其他方法的探测极值（§3.6）。0058 须自行定义映射（推荐 `max(0, score)`，全为 0 时等权），
  并在 0058 计划里论证。
- `final` 是"单方法调参"组的答案；1-SE 简洁性可能选中已被删 h5ad 的试验，此时 `h5ad=null`，0058 只依赖 `labels.csv.gz`。
- "LLM 自选方法子集"（K2）与旧 consensus 的 LLM 主席在 0058 里合并设计（Q27 消融）。

### 3.15 旧代码处置

| 旧位置 | 处置 | 去向 |
|---|---|---|
| `autoagent/judge.py`（:44-155） | 重写：门槛由 `1e-8` 改为 `SE_fixed`，简洁性改为误差带内起作用，加归一化距离；新增跳过规则 | `tuning/judge.py` |
| `autoagent/directive.py`（:15-72） | 借分段思路，重写为固定模板 + 类型化输入 | `tuning/templates/propose.txt`、`prompts.py` |
| `autoagent/experiment_ledger.py` | 重写为事件流 + 聚合记录 | `tuning/ledger.py` |
| `autoagent/optimization_loop.py`（:256 单提议循环） | 改为按维度分治：1 维网格、2–3 维两阶段；新增 LLM 定 K 与补 marker | `tuning/pipeline.py`、`search.py` |
| `autoagent/llm_client.py` | 重写解析；调用改走注入的 provider | `tuning/llm.py` |
| `autoagent/search_space.py`、`metrics_*`、`evaluator.py` | 已被 0056 取代，不迁 | — |
| `autoagent/harness_*`、`patch_engine.py`、`edit_surface.py`、`api.py` 等 | Q8：不迁，随包删除（路径一留给离线进化计划） | — |
| `runtime/consensus/scoring.py` cross_NMI | 思想用于 a(K)，改用 AMI | `tuning/stability.py` |
| `runtime/consensus/planners.py` `ChairLLMPlanner` | 不迁；在 0058 与"LLM 自选方法子集"合并设计 | 0058 |

`runtime/consensus/`、`runtime/workflow/` 留给 0058 删除。

---

## 4. 验证协议（估计，不判定；L1）

### 4.1 数据集、单元与下载校验

| 集合 | 单元 | 用途 |
|---|---|---|
| 开发集 | DLPFC 151673、151674 | 迭代、调试、§4.6 的一次性面板比较 |
| 留出集 · DLPFC | 151507、151508、151509、151510、151669、151670、151671、151672、151675、151676 | 主要估计量 |
| 留出集 · CosMx 主 | slide 1、slide 2 各 12 个 K* ≥ 3 的 FOV 块 | 次要估计量 |
| 留出集 · CosMx 单列 | slide 1、slide 2 各 4 个 **K* = 2** 的块 | 单列描述 |
| 预热块 | CosMx slide 1 额外 1 块 | 冻结前跑通全流程（不读真值），不进任何分析 |

**推断范围**：DLPFC 10 张切片来自 **3 个供体**（Br5292：151507–151510；Br5595：151669–151672；Br8100：151675–151676），同一供体的相邻切片不独立；全部区间只描述
"切片"层面的变异，**不外推到供体**。

**DLPFC 下载与转换**（`docs/plans/0057-validation/prepare_dlpfc.py`）：

1. 下载：计数（S3）；坐标与比例因子（HumanPilot GitHub raw）；层注释 `sce` 对象（Dropbox，D2）。
2. 校验：S3 `ETag` 为分段 MD5，按 8 MiB（不符再试 5、16 MiB）分段计算比对，都不符停下报 owner；GitHub raw 用 contents API 的 git blob SHA-1 比对；Dropbox 首次下载记 sha256
   （TOFU）进 `manifest.json`，另做内容检查；可再与 SDMBench figshare 镜像（D2）的 spot 集合比对作旁证。全部文件 sha256 写进 manifest，每次使用前复核。
3. 转换：同一脚本把 151673、151674 也从下载源重建一遍，与 D1 逐项比对，不一致即停。
4. 预期（下载后核对，不一致停下报 owner；未联网核实）：in-tissue spot 数 151507 4226、151508 4384、151509 4789、151510 4634、151669 3661、151670 3498、151671 4110、
   151672 4015、151675 3592、151676 3460；151669–151672 只有 Layer3–6 与 WM（K*=5）。涉及真值的核对只在冻结之后由评估脚本做。

**CosMx 分块与抽样**（`prepare_cosmx.py`、`define_population.py`）：

- 单元 = (slide_id, FOV) 块，坐标即 FOV 内局部坐标（D5）；合格块：细胞数 ≥ 500。
- 总体划分（冻结后、任何方法运行前，只读取每块真值 niche 的种类数与占比，输出块清单）：主总体 = K* ≥ 3；单列总体 = K* = 2（slide 1 有 5 块，slide 2 有 115 块）；
  K* = 1 的块不入选（ARI 退化）。
- 抽样：种子 20260926；预热块先从 slide 1 合格块中抽 1 块并剔除；再每张 slide 在主总体中无放回抽 12 块、在单列总体中抽 4 块。
- 口径敏感性：另用"占比 ≥ 5% 的 niche 数"重新计 K*，报告主结果在"两种口径都 ≥ 3"的块上的子集结果，以及"选 K=7 的比例按真值 K 分组"的两种口径版本。
- `X ← layers['counts']`；obs 剥到只剩 `batch="b0"`（E3）。纳入评估的 niche：slide 1 全部 6 个，slide 2 全部 4 个。
- 组织描述：来自数据来源说明；找不到非真值来源时两张都写 `human liver`（O6）。

### 4.2 预处理与输入（G7、E3）

| 数据 | 固定参数 | 说明 |
|---|---|---|
| DLPFC | `spatial-preprocess --data-type visium --species human --max-mt-pct 100`，其余默认 | G7：默认 20 删掉 12%–20% 的 spot 且集中在 L1–L4；验证固定 100，不改 skill 默认值（留给 0059）；开发阶段另用 20 跑 A0/A1 作敏感性报告 |
| CosMx 块 | `--data-type generic --species human`，其余默认 | 999 基因 < `n_top_hvg=2000` 时 scanpy 取全部基因；QC 丢失 > 20% 的块停下报 owner |

预处理后 obs 剥到只剩 `batch`（取值不透明）；输入写到 `<root>/units/<uid>/input.h5ad`；原始数据与真值不在任何 workspace；评估脚本机械审计每个单元的
`input_obs_columns == ["batch"]`。

### 4.3 臂、重复与共享

- 臂见 §3.13。同一单元上探测只做一次，A0 与所有调参臂共用；探测产物以只读副本放进各臂的 workspace。
- 重复：A1、A2 各 3 次；A3 2 次；A6 3 个种子。单元取重复的平均进入估计，另报重复间标准差。
- 模型：一个固定的模型 ID（冻结清单写明），A1、A2、A3 用同一个。

### 4.4 估计量（J2；L1 之后全部为描述性）

记单元 u、可运行方法集合 𝓜、方法 m 的默认结果 `def_m(u)`（A0）、A1 的每方法答案 `tun_m(u)`（含 `fallback_default`）、跨方法答案 `fin(u)`；ARI 只在有真值的观测上算。

**方法的纳入**（复审必改 1）：`def_m(u)` 失败（`status ≠ ok`）的方法在该单元**直接剔除**，不进入 D1、D2、D3。剩余方法集合记 𝓜_u。

| 类别 | 估计量 | 定义 |
|---|---|---|
| **主要 (i)** | 同一方法的配对差 | `D1(u) = mean_{m∈𝓜_u} [ARI(tun_m(u)) − ARI(def_m(u))]`；先对方法取均值，单元为唯一独立单位（O19）。K 不可达或调参全部失败的方法，`tun_m` 按流水线行为取 `fallback_default`（即 `def_m`），贡献 0；敏感性：把这些方法剔除后再算。另报每方法 `D1_m(u)` |
| **主要 (ii)** | 流水线 vs 默认中位数 | `D2(u) = ARI(fin(u)) − median_{m∈𝓜_u} ARI(def_m(u))`（中位数只在默认结果 ok 的方法上取） |
| 次要 | vs 默认参数下最好的方法 | `D3(u) = ARI(fin(u)) − max_{m∈𝓜_u} ARI(def_m(u))`；"oracle-of-defaults"用真值挑出最好的默认方法，是现实中拿不到的上限对照 |
| 次要 | 组织信息 / 编排方式 / LLM 本身 | A1 vs A2、A1 vs A3、A1 vs A6 的 `ARI(fin)` 差 |
| 描述 | 方法内置自动定 K | A1 的 `tun_cellcharter` vs A0k（O20） |
| 描述 | 遗憾值（G5） | `oracle(u) − ARI(fin(u))`；oracle 为单元上全部臂全部试验的最大 ARI；另报只用探测试验的 `oracle_probe(u)` |
| 描述 | 固定 K 面板与 ARI | 单元内、选定 K 的全部 ok 试验上 `fixed_k_score` 与 ARI 的 Spearman ρ（n ≥ 5 才计） |
| 描述 | K 选择 | chosen_k 分布；选中稳定峰值的比例 vs 随机水平 \|M\|/\|G\|；补请求与回退次数；\|chosen_k − K*\| |
| 描述 | 搜索 | 2–3 维方法跳过第 2 阶段的比例；最终选择来自默认/网格/扫描/LLM/随机/邻域的比例 |
| 描述 | 成本 | 新运行数、GPU 秒与 CPU 秒、LLM 调用与 token（含实际计费量）、墙钟 |

**失败计分**：流水线在某单元没有产出 `fin` → 主分析 ARI 记 0；敏感性按 `median def` 计。

**J1 判读规则（预登记，复审必改 5）**：

1. 报告 A1、A2、A6 在 **K* = 5 组**（151669–151672）与 **K* = 7 组**（其余 6 张）中选 K=7 的比例；CosMx 按块的 K*（两种口径）同样分组报告。
2. 按 K* 分组报告 D1、D2；报告 chosen_k = 7 条件下的 D1。
3. **若 A1 在 K* = 5 组选 7 的比例不低于 A6**，报告必须写明："DLPFC 主要估计量主要反映 K=7 下的调参，不能作为 LLM 定 K 优于稳定性规则的证据。"

### 4.5 统计（描述性估计，L1）

- **不判定通过与否**。所有估计量报：均值、中位数、**t 区间**（95%，df=n−1）、**BCa bootstrap 区间**（10,000 次，种子 20260926）、**精确符号翻转 p 值**（双侧；DLPFC 10 个单元
  2^10 = 1024 种符号组合，最小可达 p = 2/1024 ≈ 0.002），不做多重比较校正，p 值只作描述。
- **DLPFC**：10 个单元为主；按供体分列（报告项）；去掉 Br8100 的敏感性。
- **CosMx**（复审必改 2）：**按 slide 分列**报告（slide 1 非肿瘤分区、slide 2 肿瘤相关 niche，两者的"区域"性质不同，不合并为一个估计量），每张 slide n=12，符号翻转
  2^12 = 4096 种；另给一个按 slide 等权分层的汇总均值（分层 bootstrap，在 slide 内重抽）作描述，不作为主要数字。K*=2 单列块只列逐块结果与中位数。
- **最小可检出效应（供解读与 0059 参考）**：n=10、双侧 α=0.05、功效 80% 时约 (t_{0.975,9} + t_{0.80,9})/√10·sd_d ≈ 0.99·sd_d；t 区间半宽 0.715·sd_d（sd_d ≈ 0.08 时约 0.057）。
- **无效停止线**（冻结项）：若 DLPFC 留出集上 **D1 与 D2 的 95% t 区间上界都 < 0**，不进入 0059 的确证实验，先回头排查（面板、定 K、搜索策略），排查结论写入报告并由
  owner 决定是否修订后重启开发阶段（届时 0057 留出集已用过，不得再作留出）。BCa 区间与 t 区间结论不一致时两者都报，停止线以 t 区间为准。

### 4.6 开发阶段、冻结点与冻结后禁令

**开发阶段允许**（只在 151673/151674 与合成数据上）：

1. 实现、调试、任意次运行全流程（桩 LLM 或真实 LLM）。
2. 模板修改只能以格式与契约为目标（减少解析失败、校验失败、泄漏误报、prompt 长度），**不得以开发集 ARI 为目标**；每次修改在日志中引用触发它的失败事件编号（台账
   `seq` 或 `llm/NNNN.json`），并记新模板 sha256。
3. **一次性面板比较**（占优规则）：N1（参照范围归一化平均）为默认；N2（组内名次平均）在两张开发切片上"全部组的组内平均遗憾"都严格小于 N1 时才替换；单列"同一方法、
   同一 K、不同参数"的组，只作说明。替换后重跑一遍开发流程，只看能跑通。
4. 工程参数（超时、并发、`cpus`、内存）与 A3 的 token 上限（按 p95）按实测确定，不以 ARI 为目标。
5. 冻结前对留出集只允许：下载、校验、格式转换、预处理（不读真值列）；预热块跑通全流程（不读真值）。

**冻结点 F1**（开发阶段结束，owner 签字后生效）：写 `docs/plans/0057-validation/freeze.json` 并在本计划末尾追加"冻结附录"。冻结清单：

- 探测：G、R（`round` 生成）、`B_sub=20`、子采样比例、全部种子；曲线定义、bootstrap 次数、稳定峰值门槛 0.5、补请求规则、回退 K 规则；
- 面板：版本、组合方式（N1 或 N2）、SE 公式；搜索：维度判定、1 维网格点、单参数扫描规则、邻域步长与对角点规则、跳过规则、每方法 12 组、C=4、新运行上限；简洁性启发式与距离定义；
- LLM：provider、模型 ID、温度、`max_tokens`、思考预算、重试预算、三份模板 sha256、输出 schema 版本；A3 的 token 上限（p95 定值）、计数口径与 `max_turns`；
- 防泄漏：计数正则、检查作用的字段清单、组织字符串（DLPFC：`human dorsolateral prefrontal cortex`；CosMx 见 O6）；
- 数据：切片清单、CosMx 总体划分与抽样种子、口径敏感性定义、预处理参数、obs 白名单、manifest sha256；
- 臂、重复次数、A6 种子、自由编排任务模板、提醒消息、规则文件（含 MCP 关闭）、预算；估计量、方法纳入与失败计分、J1 判读规则、统计方法与种子、报告模板；
- **无效停止线**（§4.5）；
- **代码摘要**：`omicsclaw/ensemble/**`、`omicsclaw/entry/**`、`omicsclaw/provider/**`、`skills/spatial/spatial-domains/**`、`skills/spatial/spatial-preprocess/**`、
  `skills/spatial/_lib/**`、`docs/plans/0057-validation/*.py` 的逐文件 sha256 及总哈希；
- **环境锁定**：`conda env export -n OmicsClaw`、`conda env export -n rapids_singlecell`、两个环境的 `pip freeze`、R 的 `sessionInfo()`。

**冻结后禁止**：改动清单中任何一项；在留出集上跑两次；看了留出结果后增删臂、单元或估计量；在预登记规则之外排除单元。发现缺陷时停下，已得结果如实保留；修复后的重跑
只能作为标注"冻结后偏离"的附加结果并列报告。驱动在 `freeze.json` 缺失、代码摘要或环境锁定不符时拒绝运行，并记录"第几次运行"。

**对后续计划的约束**：0058、0059、0060 不得依据本份留出集的结果做设计，唯一例外是 §4.9 预登记的**功效计算**（只读取 D1、D2 的效应量与离散度）。

### 4.7 留出集运行与报告

- 一条命令 `run_holdout.py --freeze … --root <验证根目录>`：依次定义 CosMx 总体、预处理、探测、A0/A0k、各调参臂各重复；每个"单元 × 臂 × 重复"一个独立 workspace（§3.12）。
- 真值只在全部运行结束后由 `evaluate.py` 读取（CosMx 总体划分只读 niche 种类数与占比，例外已预登记）。
- 报告 `docs/plans/0057-holdout-report.md`，固定表格：
  1. 逐单元：数据集、单元、K*、各方法 A0 ARI、A0k、`median def`、`max def`、各臂 chosen_k 与 `fin` ARI、每方法 `tun_m` ARI（标 `fallback_default`）、失败；
  2. 主要估计量 D1、D2：均值、中位数、t 区间、BCa 区间、符号翻转 p；每方法 D1_m；方法剔除与失败计分的敏感性；**无效停止线判定**；
  3. 次要估计量：D3 与各对照；
  4. K 选择与 **J1 判读**：选 K=7 的比例按真值 K 分组（A1、A2、A6）、按 K* 分组的 D1/D2、chosen_k=7 条件下的 D1、判读句（若触发）；选中稳定峰值比例 vs \|M\|/\|G\|；
  5. 按供体分列；CosMx 按 slide 分列与分层汇总；K*=2 单列；口径敏感性；
  6. 描述性：遗憾值（两种 oracle）、固定 K 下 Spearman ρ、搜索来源分布与跳过比例；
  7. 成本：新运行数、GPU 秒与 CPU 秒、LLM 调用与 token（含实际计费量）、墙钟；A3 的 token 分布与失败数；
  8. 给 0059 的功效计算输入（§4.9）；
  9. 偏离、失败与泄漏拦截事件。
- 结果无论正负都写进 README 里程碑与交付记录。

### 4.8 成本估算（粗估，T10 实测后更新并在冻结前由 owner 确认）

单元：DLPFC 10 + CosMx 主 24 + 单列 8 = 42（另预热 1）。每次运行的时间取开发数据的量级（leiden/louvain 约 9 s、占 2 核；GNN 方法约 30 s GPU、占 8 核；spagcn 约 60 s CPU、
占 8 核），均为假设；核·h 按预留核数计（实际占用更低）。

| 项 | 每单元 | 全部（42 单元） |
|---|---|---|
| 探测运行 | E 42 + L 全量 78 + L 子采样 1560 = 1680 次 | 70,560 次 |
| 探测 GPU（graphst、cellcharter 28 次 × 30 s） | 0.23 GPU·h | 约 10 GPU·h |
| 探测 CPU（L 1638 × 9 s × 2 核 = 8.2；spagcn 14 × 60 s × 8 核 = 1.9；GNN 28 × 30 s × 8 核 = 1.9） | **11.9 核·h** | **约 500 核·h** |
| 调参"臂 × 重复"数 | A1 3 + A2 3 + A6 3 + A3 2 = 11 | 462 |
| 每"臂 × 重复"新运行 | leiden、louvain 各 12 组（校准后至多各 60 次）；spagcn、graphst 各至多 12；cellcharter 4 | 至多约 7.0 万次 |
| 调参 GPU（每"臂 × 重复"graphst 12 + cellcharter 4 = 16 次 × 30 s = 0.13 GPU·h） | 1.5 GPU·h | 约 **62 GPU·h** |
| 调参 CPU（每"臂 × 重复"：L 至多 120 × 9 s × 2 核 = 0.6；spagcn 12 × 60 s × 8 核 = 1.6；GNN 16 × 30 s × 8 核 = 1.1） | 11 × 3.3 ≈ 36 核·h | 约 **1,510 核·h** |
| 确定性臂 token（A1、A2 各 3 次；每次：定 K 约 18k 入 / 1.5k 出，spagcn、graphst 第 1 阶段提议各约 9k 入 / 0.6k 出） | 6 × (36k 入 + 2.7k 出) ≈ 0.22M 入 / 0.02M 出 | 约 **9M 入 / 0.7M 出** |
| A3 token（2 次；每次估约 1.0M 入 / 25k 出，上限初值 3M、T10 按 p95 定） | 2.0M 入 / 0.05M 出（上限 6M） | 约 **84M 入 / 2.1M 出**（上限 252M） |
| 开发阶段 | 2 单元 × 全部臂 | 约 4 GPU·h、约 5M 入 token |

合计约 **72 GPU·h、约 2,000 核·h**（预留口径）、约 **95M 输入 token**（A3 全部触顶时约 260M）。M1 使确定性臂的 LLM 调用从每方法每轮一次降为"定 K 1 次 + 每个 2–3 维方法 1 次"，
确定性臂 token 约降为第三版的 1/5。削减次序（冻结前由 owner 定）：先减 CosMx 单列块，再把 A6 降为 2 个种子，最后减 CosMx 主块至每 slide 8 块；不减 DLPFC 与 `B_sub`。

### 4.9 给 0059 的预登记（L1；0059 的 plan 必须引用本节，不得事后换数据集）

**确证对象**：完整流水线（0057 调参 + 0058 consensus）对直接跑 skill（默认参数）。

**假设与检验**：主要终点 = 单元级 `ARI(流水线输出) − median_{m} ARI(def_m)`（D2 的流水线版本，方法纳入规则同 §4.4）；H₀：均值 ≤ 0，H₁：均值 > 0；**单侧 α = 0.05**；
检验为单侧精确符号翻转检验（单元数 ≤ 16 时穷举），并报单侧 t 检验作敏感性。唯一主要终点，不做多重比较。

**数据集要求**：从未用于 0056、0057 的开发或留出（DLPFC 12 张、CosMx 人肝全部排除）；**优先选真值 K ≠ 7 的数据**；有人工或作者提供的区域 / domain 注释；单元定义、预处理与
0057 同一规范（obs 只留 `batch`、不透明编号）。

**候选数据集**（2026-09-26 逐条核实；"已核实"指下载了文件并读出注释列与类别数）：

| # | 数据集 | 来源 URL | 单元数 | 真值 K | 核实状态 |
|---|---|---|---|---|---|
| C1 | MERFISH 小鼠下丘脑（Moffitt et al. 2018），SDMBench 预处理版 | figshare `https://doi.org/10.6084/m9.figshare.22565170`（5 个 h5ad：MERFISH_0.04…0.24） | 5 张切片 | 8（`domain` 列：MPN、MPA、BST、PVH、fx、PV、V3、PVT） | **已核实**（下载 MERFISH_0.04：5488 × 155，`domain` 8 类）；其余 4 张只核实文件存在 |
| C2 | BaristaSeq 小鼠初级视皮层（Sun et al. 2021），SDMBench 版 | figshare `https://doi.org/10.6084/m9.figshare.22550074`（Slice_1/2/3） | 3 | 6（`layer`：VISp_I、II/III、IV、V、VI、wm） | **已核实**（Slice_1：1525 × 79，6 类）；另两张只核实文件存在 |
| C3 | STARmap 小鼠内侧前额叶（Wang et al. 2018），SDMBench 版 | figshare `https://doi.org/10.6084/m9.figshare.22565200`（BZ5、BZ9、BZ14） | 3 | 4（`region` 1–4） | **已核实**（BZ5：1049 × 166，4 类）；另两张只核实文件存在 |
| C4 | osmFISH 小鼠体感皮层（Codeluppi et al. 2018），SDMBench 版 | figshare `https://doi.org/10.6084/m9.figshare.22565194` | 1 | 11（`Region`） | **已核实**（4839 × 33，11 类） |
| C5 | CosMx 人非小细胞肺癌（SDMBench "SMI datasets"） | figshare `https://doi.org/10.6084/m9.figshare.22550056`（global_z0…z4） | 5 | 8（`niche`） | **部分核实**（global_z0：18895 × 980，`niche` 8 类）；组织与来源论文**待核实**；平台与 0057 的 CosMx 肝相同，作次选 |
| C6 | HER2+ 乳腺癌 ST（Andersson et al. 2021） | `https://github.com/almaan/her2st`（`data/ST-cnts/*.tsv.gz` 计数，`data/ST-pat/lbl/*_labeled_coordinates.tsv` 病理注释） | 9 个有注释切片（A1、B1、C1、D1、E1、F1、G2、H1、J1） | 各切片不同（A1 为 6 类，含 `undetermined`） | **已核实**（A1 注释 348 spot、6 类；A1 计数文件为普通 gzip）；其余切片的类别数**待核实**；Zenodo 版本是 7z 加密的，用 GitHub 版本 |
| C7 | 10x Visium 人乳腺癌 Block A Section 1 + SEDR 注释 | 注释 `https://github.com/JinmiaoChenLab/SEDR_analyses`（`data/BRCA1/metadata.tsv`）；计数 10x 数据集页 | 1 | 20（`fine_annot_type`）/ 4（`annot_type`） | **注释已核实**（3798 行、20/4 类）；10x 计数下载页本次返回 HTTP 429，**计数来源待核实** |
| — | STARmap* 小鼠视皮层 1k 基因（SDMBench `https://doi.org/10.6084/m9.figshare.22565209`） | — | 1 | 7（L1、L2/3、L4、L5、L6、CC、HPC） | 已核实；**真值 K = 7，按要求排除** |
| — | MOSTA 小鼠胚胎 Stereo-seq（`https://db.cngb.org/stomics/mosta/`） | — | — | — | 站点可达；注释是否可作区域真值**待核实**，暂不列入 |

候选合计：已核实可用的 C1–C4 共 12 个单元（K = 4、6、8、11，全部 ≠ 7），加 C5、C6 后可达 26 个；单元定义（整张切片或 FOV）在 0059 的 plan 中按本节规则固定。

**功效计算方法**（用 0057 留出集的 D2，因为流水线版本的效应在 0059 之前没有无偏估计）：

1. 读取 DLPFC 留出集 D2 的均值 d̂ 与标准差 ŝ（10 个单元）；以 **d̂ 的 80% 双侧 t 区间下界**作为计划效应 δ（保守；若 ≤ 0，报告"无法在可行样本量内确证"并按 §4.5
   停止线处理），以 **ŝ 的 80% 上置信界**（卡方）作为计划离散度 σ。
2. 所需单元数 n = 满足"单侧 α=0.05、非中心 t 分布功效 ≥ 0.80"的最小 n；另以精确符号翻转检验的蒙特卡洛功效（正态模拟 10,000 次）复核。
3. 若 0058 的开发阶段给出 consensus 相对单方法调参的额外效应，**不得**用来放大 δ（开发集估计有偏）；只可在报告里并列。
4. n 超过候选可用单元数时，0059 必须先补充候选（遵守本节的数据集要求并逐条核实）或报告不可行，不得改用已用过的数据。

**约束**：0059 的 plan 必须引用本节；数据集只能从上表中选，或按同一要求新增并写明核实记录；不得在看过任何 0059 结果后更换数据集或终点。

---

## 5. 分步实施

依赖：T1、T2、T3 互不依赖；T4 需要 T1；T5 需要 T2、T4；T6 独立；T7 需要 T3、T5、T6；T8 需要 T7；T9 需要 T8；T10 需要 T9；T11 可在 T8 之后任何时候；T12 需要 T10 冻结与 T11。
每步跑 §6 主命令并保持绿。

**T0 基线**（不写生产代码）：复测 §6 主命令并记数（0056 交付后为 2199 passed, 8 skipped）；确认 golden 未漂移；在开发 workspace 用 §4.2 参数重做 151673/151674 预处理与 obs 剥离。

**T1 面板 v3**：`metrics/__init__.py` 版本与成员；`silhouette_metric` 改原值并输出 `sd(s_i)` 与 `m`；PAS 输出 SE 所需量；`score` 字段改为 §3.6 的绝对值；`load_reference` 缺 `X_pca`
时抛错；`--describe-input` 增 `obsm_keys`、`n_vars`。测试更新。

**T2 `k_control` 与 leiden/louvain `cpus`**：`space.py` 加载与校验；`tuning.yaml` 七个方法补齐；假 skill 增加 calibrate 型方法与一个 2 维方法；一致性测试与变异。

**T3 纯 Python 部分**：`budget.py`（按方法并发预留）；`search.py`（维度判定表驱动测试覆盖 §3.8.1 全部 7 个方法；1 维网格点与 `round`；单参数扫描端点规则与平手；邻域步长、对角点、
越界裁剪与重复替换；随机补足可复现）；`scoring.py`；`judge.py`（跳过规则、1-SE 与平手链、`fallback_default`、跨方法选择）；`ledger.py`（含聚合记录 schema）。

**T4 执行环境子进程**：`subsample.py`；`stability.py`（rPAC 与 MultiK 源码公式手算一致；共识子集；AMI 与 sklearn 一致；bootstrap 置信带与峰值频率可复现）；`markers.py`；
`inspect.py`。OmicsClaw 环境（Py3.11）跑。

**T5 探测、证据、校准**：`probe.py`（R 恰好含 1.00）；`evidence.py`（稳定峰值门槛、回退 K 规则——表驱动测试，含 P6 的 K=16 反例）；`calibrate.py`。

**T6 prompt、防泄漏、LLM**：三份模板；类型化输入（含 SKILL.md 全文）；两步 K 交互、跨两步累计的重试预算、非法补请求各分支；第 1 阶段提议契约（恰好 3 组、与扫描点去重、
不合格组随机补足）；`LeakError` 与字段来源标注；`ScriptedChatModel`、`CassetteChatModel`；golden 模板测试。

**T7 `TuningPipeline`**：假 skill 上端到端（脚本化 LLM）：1 维网格路径、2 维两阶段路径、跳过第 2 阶段、邻域点重复替换、合法与非法补请求、选非峰值 K、K 决策回退、提议整批坏 JSON、
部分组越界被丢弃并补足、`fallback_default`、方法全部失败、墙钟上限、参照退化；`selection.json` 与聚合记录 schema；性质测试（随机失败注入下每方法 `new_runs ≤ cap`、评估组 ≤ 12）；
cassette 回放一致。

**T8 工具与装配**：三个工具；`run_skill` 按方法预算与 `fixed_k_score`；配置与 `_Option`；`entry` 注入 provider；**`ChildRunner` 的用量上报**：把子引擎每个 `turn_end` 的 usage 经工具
上下文的用量通道交给调用方（F28），测试钉住"父级累计用量包含子代理"；挂载顺序；`test_permission_wiring.py` 各模式名单；§3.13 golden 矩阵；子代理在 deny 规则下调用 `bash` 被拒；
分层测试扩展；Py3.11 import 测试；`.env.example`。

**T9 验证脚本**（`docs/plans/0057-validation/`，可 import `evaluation`）：`prepare_dlpfc.py`、`prepare_cosmx.py`、`define_population.py`、`run_arms.py`（独立 workspace 与新 `memory.db`、
规则文件、MCP 关闭；A3 走 `TurnRunner` 流式路径，按 `turn_end` 累计 token、usage 为 `None` 即拒绝、提醒作为一次 `max_turns=2` 的 `run_turn`）、`run_holdout.py`（冻结检查、环境锁定
比对、计次）、`evaluate.py`（估计量、方法纳入、t/BCa、符号翻转、J1 判读、停止线）、`power_0059.py`（§4.9 的功效计算）、`report.py`、`cost.py`。

**T10 开发阶段**：

1. **A0 等价核验**（复审必改 4）：取开发单元，直接用默认参数跑一次 spatial-domains（每个可运行方法一次，`n_domains` 不传、`resolution`/`spatial_weight` 不传），与从探测结果中取出
   的 A0 逐 spot 比对标签（重新编号后完全相同，即 ARI = 1.0）。不一致 → 停下查原因（非确定性、参数渲染差异），修正前不得冻结。
2. 真实 LLM 在 151673/151674 上跑全部臂与重复；§4.6 的一次性面板比较（含同方法组单列）；默认预处理敏感性；预热块跑通。
3. 测量成本并按 §4.8 外推；按开发集 A3 token 分布的 p95 定上限；粗估 sd_d。
4. 写 `docs/plans/0057-dev-report.md`；生成 `freeze.json`、环境锁定与冻结附录 → **owner 签字**。

**T11 删除旧 autoagent**：

- 删除 `omicsclaw/autoagent/`（29 个文件）与 21 个 `tests/test_autoagent_*.py`。
- `tests/sdk/test_boundary.py`:63-66 的 `B4_KNOWN` 改为空集（:162 为相等断言）；`tests/launch/test_grammar.py`:271 `LEGACY_TREES` 去掉 `autoagent`；`test_ensemble_is_a_layer.py`
  的 `FORBIDDEN` 去掉 `omicsclaw.autoagent`。
- 活文档：`AGENTS.md`:166-167、:204、:231-232；`README.md`:41 的 "autoagent excepted" 与 **:61 的"Five packages are deliberately kept … `autoagent/` (19k lines …)"**（改写为"已删除，运行时调参见
  `omicsclaw/ensemble/tuning/`"，该条其余历史内容保留），另加本份里程碑（写明立意与两条路径的分工）；`docs/FRAMEWORK-REBUILD.md`:1757-1759、:1802、:1929；`docs/product-overview.md`
  （3.11 Self-Evolution 一节、:93、:156-158、:254、:990-991、:1032、:1533、:1609、:1634、:1996-2018——改为"已删除；运行时调参见 `omicsclaw/ensemble/tuning/`；离线的 skill 进化见
  0059 之后的独立计划"）；`docs/core-features/README.md`:51；`docs/core-features/sandbox.md`:13；`docs/architecture/2026-05-18-current-architecture.md`:49、:127；
  `docs/architecture/skill-system.mdx`:56。
- **豁免**：`README_zh-CN.md`:57 与 `docs/ARCHITECTURE.md`（:70-72、:221、:504-508、:754-815、:1059）中的 "AutoAgent" 指外部项目 / 桌面端产品功能名，不是本包，不改；
  `omicsclaw/surfaces/desktop/server.py` 是只读参考、本就不能 import，不改，在 AGENTS.md 注明其中的 autoagent 引用已无对象；历史计划（`docs/plans/00xx`）、`docs/_legacy/`、
  `docs/proposals/` 不改。
- 验证：`grep -rn "autoagent" omicsclaw tests skills docs AGENTS.md README.md README_zh-CN.md` 的结果只允许出现在上述豁免位置、`docs/plans/`、`docs/_legacy/`、`docs/proposals/`，以及
  活文档中"已删除"的说明句；清单写进交付记录。

**T12 留出集与收尾**：`run_holdout.py` 跑一次；`evaluate.py`；报告（含停止线判定与 0059 功效计算输入）；AGENTS.md 加 ensemble 调参一节；FRAMEWORK-REBUILD；README 里程碑；交付记录
`0057-ensemble-tuning-delivery.md`。

---

## 6. 测试计划

**主命令**（rapids_singlecell 环境，Py3.13）：

```
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly -p no:cacheprovider \
  tests/ensemble tests/tools tests/engine tests/skills tests/sandbox tests/sdk tests/launch tests/subagent \
  tests/entry/test_entry_is_the_top_layer.py tests/entry/test_open_app.py tests/entry/test_assembly.py \
  tests/entry/test_permission_wiring.py tests/entry/test_ensemble_golden.py tests/entry/test_ensemble_wiring.py \
  tests/entry/test_ensemble_config.py tests/test_env_example.py
```

**执行环境（Py3.11）**：

```
/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:randomly -o addopts="" \
  tests/ensemble/test_spatial_metrics.py tests/ensemble/test_score_cli.py \
  tests/ensemble/tuning/test_stability.py tests/ensemble/tuning/test_markers.py \
  tests/ensemble/tuning/test_subsample.py tests/ensemble/test_executes_under_skill_python.py
```

rapids 下缺依赖的用例 `importorskip`；交付记录分列两套结果，"跳过"不冒充"通过"。

**慢测试**（`-m slow`）：`tests/ensemble/tuning/test_dev_pipeline.py` 需 `OMICSCLAW_TUNING_DEV_DATA=/workspace/algorithm/zhouwg_project/data_external/DLPFC` 与
`OMICSCLAW_ENSEMBLE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python`；在 151673 上跑全流程，LLM 用 `ScriptedChatModel`；断言探测数、曲线与置信带齐全、全网格精简 marker 齐全、
每方法策略与维度判定一致、`selection.json` 合法、每方法新运行不超上限。0056 冒烟测试按面板 v3 更新。

**LLM 打桩**：单元与集成测试一律用 `ScriptedChatModel`（按用途排队返回，记录收到的 prompt）或 `CassetteChatModel`；测试不访问网络；桩按结构满足 `ChatModel`，不 import
`omicsclaw.provider`。

**真实 LLM**：`-m eval`（F23）且 `OMICSCLAW_TUNING_LIVE=1`：在假 skill 上各做一次 K 决策与第 1 阶段提议，只测契约。质量评测只由 `docs/plans/0057-validation/` 的脚本运行。

**关键变异**（每条应使至少一个测试变红）：silhouette 仍用 `(s+1)/2`；缺 `X_pca` 照常出分；rPAC 分母写成 `prop_zeroes`；a(K) 用 NMI；稳定性被用来过滤 K；稳定峰值门槛改为
单次计算；回退 K 允许只有一条曲线有定义的 K；补请求允许两次或允许 K∈M；重试预算不跨两步累计；补请求的 K 未进嵌套表；R 用浮点累加生成（不含 1.00）；1 维方法调用了 LLM；
cellcharter 未扫完 5 个 `n_layers`；单参数扫描同时改两个参数；第 2 阶段在未超过"默认 + SE"时仍运行；邻域步长或对角方向算错；评估组超过 12；`fixed_k_score` 用组内名次却声称绝对；
参照随调参试验更新；简洁性只在平分时生效；没有 K 上答案时不回退默认；预算在运行后才扣或不按方法分账；计数正则去掉词边界；计数检查作用到 SKILL.md 字段；`skill_md` 证据
接受非子串；`tuning/*` import `evaluation` 或 `omicsclaw.provider`；工具描述随开关变化；`ensemble_tools=free` 仍挂 `optimize_params`；子代理绕过 deny；子代理用量未计入父级；
A3 在 usage 为 `None` 时仍运行；`B4_KNOWN` 未清空。

---

## 7. 验收标准

1. §6 主命令与 Py3.11 命令全绿；T0 基线无回归；数字写进交付记录。
2. 分层：如 §3.1；`import omicsclaw.ensemble.tuning.tools` 不加载 numpy/pandas/scanpy；Py3.11 可 import 四个子进程模块。
3. 面板 v3：`fixed_k_score` 按 §3.6 计算并可由 `reference.json` 复算；无 `X_pca` 被拒；SE 字段齐全。
4. rPAC 实现与 MultiK 源码公式一致（手算例）；bootstrap 置信带与峰值频率可复现；R 恰好含 1.00；`k_control` 一致性测试与变异通过。
5. K 决策：prompt 含 SKILL.md 与 parameters.md 全文、全网格精简 marker、M 上完整 marker；LLM 可选 G 中任意 K；补请求规则与跨两步重试预算的各分支有测试；回退 K 规则表驱动测试通过。
6. 搜索：§3.8.1 的维度判定对 7 个方法全部正确；1 维网格不调用 LLM；两阶段的扫描点、邻域点、跳过规则与 §3.8.3 一致；每方法评估组 ≤ 12、新运行 ≤ 上限（性质测试）。
7. 假 skill + 脚本化 LLM 的端到端：`selection.json` 与聚合记录合规；台账事件齐全。
8. 防泄漏：注入字段零误报；注入计数短语全部 `LeakError` 且 provider 调用 0 次；SKILL.md 与试验输出字段不经过计数检查；obs 白名单外的输入被拒绝。
9. 工具与装配：schema 与 policy 逐字段如 §3.11；按方法预算下并发超额恰好拒绝多余者；系统提示在 §3.13 全部组合下与 golden 相同；子代理 deny 生效；父级累计用量包含子代理。
10. autoagent 已删除；T11 的 grep 结果清单写进交付记录；`B4_KNOWN` 为空且测试通过。
11. 可复现：一个开发单元上以 cassette 回放 A1，`selection.json` 除时间戳外逐字节相同；A0 等价核验通过（T10-1）。
12. 开发报告、`freeze.json`（含代码摘要、环境锁定、停止线）、冻结附录与 owner 签字存在，且早于留出集第一条台账事件；驱动在冻结缺失或摘要不符时拒绝运行。
13. 留出集：全部单元 × 臂 × 重复各运行一次（或偏离已标注）；报告含 §4.7 全部表格（含停止线判定、J1 判读与 0059 功效计算输入）。**验收不要求结果为正**。

---

## 8. 风险与未决问题

### 8.1 风险

| # | 风险 | 应对 |
|---|---|---|
| R1 | LLM 被最"稳"的粗划分（P2、P3 的 K=3）或 SKILL.md 的默认 7 吸引 | 曲线只作证据、不给"选最稳"的指引；报告选中峰值比例 vs 随机水平；J1 判读规则（§4.4） |
| R2 | 开发集只有两张、同一供体 | 只允许一次面板比较、占优规则；推断限于切片；按供体分列；后续计划不得据留出结果设计（功效计算除外） |
| R3 | SE 是单次划分的测量误差，偏小；跳过规则与 1-SE 带偏窄 | 明确为启发式（§3.8.4）；开发报告给出不同子采样下分数的实际波动作对照 |
| R4 | 面板与 ARI 的相关弱，搜索可能只是在追面板噪声 | 不提高预算、1-SE 简洁性、跳过规则（§3.8）；报告最终选择的来源分布 |
| R5 | LLM 不可复现 | 重复（A1/A2 3 次、A3 2 次）；台账全文；cassette |
| R6 | 本机无 docker，`bash` 可读真值 | deny 规则与 workspace 隔离（§3.12）；真实沙箱留 0059/0060 |
| R7 | 参照范围来自少数探测试验，范围窄时放大噪声；分数依赖其他方法的极值 | 退化成员退出平均；开发报告列出各 K 的参照集大小；N2 作预登记比较；0058 权重自行映射 |
| R8 | 默认 `n_domains=7` 恰等于 DLPFC 真值，基线在 DLPFC 上占便宜 | 对主张是保守的（J1）；K*=5 切片与 CosMx 提供反例；J1 判读规则 |
| R9 | louvain `spatial_weight` 无效（F10），1 维网格在 louvain 上多为重复划分 | 记 `duplicate_of`；修复留 0059 |
| R10 | 算力与 token（§4.8） | T10 实测外推；预登记削减次序 |
| R11 | CosMx 只有 FOV 局部坐标，块小 | 次要估计量；按 slide 分列；K*=2 单列；口径敏感性 |
| R12 | 看图开关依赖图像进 provider 的路径（F15） | 默认关；O5 |
| R13 | 面板 v3 改变 `run_skill` 分数；`score` 与 `fixed_k_score` 易混淆 | T1 更新测试；描述与 AGENTS.md 写明"决策只用 `fixed_k_score`" |
| R14 | 部分推理模型忽略 `temperature`；部分 provider 在流中不报 usage | 温度只记录；A3 在 usage 缺失时拒绝运行（§3.12），换 provider 或报 owner |
| R15 | Dropbox 链接失效 | SDMBench figshare 镜像可作旁证；来源变化停下报 owner |
| R16 | A3 拿到探测证据后，与确定性骨架的差异只剩"谁来编排与定 K" | 这正是 K1 要回答的问题 |
| R17 | 0057 留出集 n=10、只作估计，给 0059 的效应估计不确定性大 | §4.9 用 80% 区间下界与离散度上界做保守功效计算 |
| R18 | 0059 候选数据集以单细胞分辨率成像数据为主，spatial-domains 部分方法（如 graphst 的平台路由）适配未验证 | 0059 的开发阶段在各数据集的开发切片上验证；本份只登记候选与核实状态 |

### 8.2 已定（owner 按推荐采纳）

| # | 结论 |
|---|---|
| O1 | A6"无 LLM"臂（回退 K + 第 1 阶段随机提议），3 个种子 |
| O2 | A1、A2 每单元重复 3 次，A3 重复 2 次；§4.8 为粗估，T10 实测后更新 |
| O3 | 校准运行计入每方法新运行上限（E 12、calibrate 型 60），两组相同 |
| O4 | 三个工具 `AUTO`，部署可用规则改 `ask` |
| O5 | 看图开关：核实 attachments 渲染层能否用于直接的 `provider.generate`；能则只用于 K 决策，不能则开关保留但设为 `true` 时报错说明 |
| O6 | CosMx：主总体（K* ≥ 3）每 slide 12 块、K* = 2 单列每 slide 4 块、预热 1 块；"占比 ≥ 5%"口径敏感性；组织描述只用数据来源说明，找不到时统一 `human liver` |
| O7 | Q6 的"决策" = K 决策（含一次补 marker）+ 第 1 阶段提议；其余确定性 |
| O8 | CosMx 为次要估计量，按 slide 分列 |
| O9 | 验证固定 `--max-mt-pct 100`；默认 20 只在开发集作敏感性 |
| O10 | 面板：参照范围归一化平均（N1）为默认，组内名次（N2）为唯一预登记比较，占优规则；单列同方法不同参数的组 |
| O11 | 隔离：每"单元 × 臂 × 重复"独立 workspace 与新 `memory.db`；deny `bash`、`web_*`，子代理同受约束；`use_skill` 不禁用；验证关闭 MCP |
| O12 | `inspect_trials`、`select_result` 随 `run_skill` 挂载；简洁性选中试验不额外保留 h5ad |
| O13 | 遗憾值为描述性，oracle = 全部臂全部试验的最大 ARI，另报 `oracle_probe` |
| O14 | 失败单元 ARI 记 0；另报按默认中位数计的敏感性 |
| O15 | 子采样对 leiden 与 louvain 都做，`B_sub = 20` |
| O17 | CosMx 单列只取 K*=2 的块，K*=1 不入选 |
| O18 | A3 拿同一份探测证据 |
| O19 | D1 先对方法取均值，单元为唯一独立单位 |
| O20 | 保留 A0k，作描述性指标 |
| O21 | A3 的 token 按输入 + 输出计，缓存命中全额计入，另报实际计费量 |

### 8.3 仍未决（待 owner 裁定）

| # | 问题 | 推荐 |
|---|---|---|
| O22 | 第 2 阶段邻域步长取区间长度的 1/8（本份设定）是否合适；它是启发式、无数据依据 | **1/8**，冻结前不在开发集上调（避免以 ARI 为目标）；交付记录报告第 2 阶段相对第 1 阶段的分数增量分布 |
| O23 | 0059 候选中 C5（CosMx 肺，与 0057 肝同平台同 niche 概念）是否允许入选 | **次选**：只在 C1–C4、C6 单元数不足以满足功效计算时使用 |

---

## 9. 不做的事

- **离线 skill 进化**（M2）：autoresearch 式在 benchmark 数据集上持续爬山，修改 skill 的默认值、提示或代码，再在留出数据集上检验迁移效果；合并 J3 的回写与 Q8 的 harness 进化。
  这是 0059 之后的独立计划；0057 只让台账能支持它（§3.10.1）。
- **LLM 自选方法子集**（K2）：放到 0058，与旧 consensus 的 LLM 主席（Q27 消融）合并设计。
- 0057 留出集上的确证检验（L1）：本份只估计；确证在 0059 按 §4.9 进行。
- `run_consensus` 与 consensus 两组消融（0058）；区域标签构造、方法层与端到端 benchmark（0059、0060）。
- 修改 skill 脚本：louvain `use_weights`、`spatial-preprocess` 的 `max_mt_pct` 默认值、`--seed`、`--no-figures`（记给 0059）。
- 修改 `CLAUDE.md`、任何 `SKILL.md`、系统提示段落。
- 迁移 `runtime/consensus`、`runtime/workflow`（0058 删除）。
- 其他 skill 的 `k_control` 与调参。
- 跨进程资源调度、沙箱镜像、Desktop 审批端点。
- 冻结后调整任何预登记项；为让结果好看而重跑留出集。

---

## 10. 给实现者的提醒

- docstring 只写函数做什么、参数与返回、会抛什么；**不写计划编号、裁定编号、决策叙事、实测数字**。§2.3 的预检数字、§3.5/§3.6/§3.8 的论证、文献对照都写进交付记录或测试 docstring。
- prompt 模板只写给模型看的内容；冻结后不得再改；开发阶段每次改动引用触发它的失败事件编号。
- 不确定的数据事实（§4.1 的 spot 数与层集合、CosMx 组织描述、§4.9 中标"待核实"的条目）以核对为准，不符即停下报 owner，不要"修正"本计划的数字来迁就数据。

---

## 修订记录

**第一版（2026-09-26）**：初稿。

**第二版（2026-09-26）**：依据独立审核与 owner 裁定 H1–H4 修订（rPAC 公式、稳定性改为证据、面板归一化、组织描述、隔离、统计、成本、CosMx、T11、冻结代码摘要）。

**第三版（2026-09-26）**：依据新立意与 J1–J4、K1–K2、I1 修订（SKILL.md 全文进 prompt 并删除去锚机制、新终点、回写格式、A3 精简、全网格 marker 与 bootstrap 稳定峰值等），
删除清单见第三版记录。

**第 3.1 版（2026-09-26）**，依据第三版复审（"还需小改"）与 owner 裁定 M1、M2、L1、O19–O21：

| 改动 | 来源 | 位置 |
|---|---|---|
| 搜索按维度分治：维度判定表；1 维方法确定性网格（`spatial_weight` 13 点、`n_layers` 1–5）、不调 LLM；2–3 维方法两阶段（3 组单参数扫描 + 3 组 LLM 提议 → 跳过规则 → 6 组确定性邻域扰动，并论证为何不用 LLM）；每方法 12 组 + 1 次默认、至多 2 轮；1-SE 为主要防过拟合手段；写明瓶颈是面板与 ARI 的相关性、不提高预算。**Q24 的"每轮 3 组、最多 4 轮、连续 2 轮无提升早停"与 K2 的"停止"决策点已被 M1 取代** | M1 | §0.2、§0.3、§0.4、§3.8、§3.10、§3.12、§3.13、§3.14、§4.8、T3、T7 |
| 两条路径的分工；离线 skill 进化写入"不做的事"；聚合记录补全支持离线进化的字段 | M2 | §0.1、§3.10.1、§9 |
| 留出集只做估计：D1、D2 报效应量、t 与 BCa 区间、描述性符号翻转 p；删除 Holm 族与"通过"判定；无效停止线（写入冻结项）；新增 §4.9 给 0059 的预登记（确证对象、单侧 α=0.05、数据集要求、候选清单与核实状态、功效计算方法、引用约束） | L1 | §4.4、§4.5、§4.6、§4.7、§4.9 |
| O19–O21 改标已定 | owner | §8.2 |
| D1 口径：默认失败的方法剔除；K 不可达或调参全失败时按 `fallback_default` 取默认（贡献 0），另报剔除敏感性；D2 的中位数只在默认 ok 的方法上取；流水线新增 `fallback_default` 行为 | 复审必改 1 | §3.8.4、§3.14、§4.4 |
| CosMx 按 slide 分列，另给 slide 等权分层汇总作描述 | 复审必改 2 | §4.5 |
| A3 token 按主 agent 引擎 `turn_end` usage 累计并计入子代理（新增 T8 的 `ChildRunner` 用量上报）；只走流式路径，usage 为 `None` 即拒绝；"给 1 轮"= 一次 `max_turns=2` 的 `run_turn`；上限按开发集 p95 定、3M 为初值 | 复审必改 3、小问题 | F27、F28、§3.12、T8、T9、T10 |
| T10 增加 A0 等价核验（直接跑默认与探测取出的 A0 逐 spot 比对） | 复审必改 4 | T10、§7 |
| J1 判读规则预登记 | 复审必改 5 | §4.4、§4.7 |
| 探测 CPU 改为每单元 11.9 核·h、合计约 500 核·h；成本表按 M1 重算 | 小问题 | §4.8 |
| 推断范围限于"切片"（3 个供体、相邻切片不独立） | 小问题 | §4.1 |
| T11 补 README.md:61；README_zh-CN 与 docs/ARCHITECTURE.md 的 "AutoAgent" 豁免 | 小问题 | F21、T11 |
| resolution 网格用 `round` 生成、恰好含 1.00 | 小问题 | §3.4、T5 |
| 新增未决 O22（邻域步长）、O23（C5 是否入选）；新增风险 R4、R17、R18 | 本版 | §8 |
