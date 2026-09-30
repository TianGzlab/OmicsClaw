# 计划 0061 — 运行期环境供给：旧"自适应环境搭建流程"的可行性审计与整合

**状态**：**第 7.2 版**（2026-09-25）。owner 裁定（§0.2 D8，§9.1 Q34）只改"包从哪来"这一条：`install_skill_deps` **直接沿用本机
pip 的配置联网安装**（与用户自己敲 `pip install` 相同），不再由部署在 OmicsClaw 配置里声明来源；第 7 版的六个 `skill_env_*` 来源
配置、来源文法、迁移对照与"未配来源即拒绝启动"随之删除，Q25 被 Q34 撤回，Q26、Q29、Q30、Q32 作废，Q33 按新来源改写。为保住
"base 永不改动"，补一道只看键名的安装位置守卫（§4.5 第 7.3 步，F93）。其余 P2 设计不变。本版由协调方按 owner 指示直接修改，
**未送审核**（owner 2026-09-25：暂不派子 agent 修订与审核）；逐条见 §10 第 7.2 版。P2 仍待裁定的问题：Q4–Q10、Q27、Q28、Q31、Q33。**2026-09-25 补记**：上述问题与 P3 的 Q16、Q17 已由 owner 全部按推荐裁定，
P2、P3 即刻实施（§9.1）。**2026-09-27 补记**：P2、P3 已实现并经独立评估；§4.5 第 7.3、7.4、7.9、7.10 步已按实现对齐（§10 末条）。

以下为第 7.1 版状态说明（保留作历史）：第 7 版的定向复核结论为"有条件通过"：B1–B3 已用原攻击实测确认堵住，第 7 版与审核方
意见不同的三处（以 `--` 取代需求文件、http 来源自动加 trusted-host、不查制品主机）也被认可；第 7.1 版按复核的 3 条重要意见与
8 条次要意见做最后修订，逐条处置见 §10 第 7.1 版条目，新增 Q33。第 7 版按第 6 版独立审核修订（结论"不通过"：第 6 版用来取代哈希的
来源控制实测有三条绕过路径 B1–B3），核心改动是安装所用的来源与传输参数**只取自 OmicsClaw 的启动配置**（flag、进程环境与 `.env`），
完全不读 pip 配置、不写需求文件（§4.5 第 5 步、§4.10；请 owner 在 Q29 确认）。第 6 版依据 owner 2026-09-24 的两条裁定（§0.2 D7；
§9.1 Q24 安装不借助哈希确保、Q25 明文索引"部署声明即信任"）只改 P2；P1 已由另一个会话按第 5 版实施，第 7、7.1 版同样**只改 P2 的
设计**，P0b、P1、P3 不变。P2 待裁定的问题：Q4–Q10、Q26–Q33。

第 5 版为定稿（owner 选择不再复核、直接定稿），定稿时未写任何生产代码或测试。第 5 版把 Q19–Q23 移入已裁定（owner 2026-09-24），
并按第 4 版的独立审核（"有条件通过"，无阻断）修订，逐条处置见 §10 第 5 版条目。第 2 版按独立审核（"有条件通过"，10 条重要
意见）修订；第 3 版按第 2 轮复核（仍为"有条件通过"，N-1…N-4）修订，逐条处置见 §11；第 4 版按 owner 2026-09-24 裁定（D6）
与已定稿的计划 0062 只改三处：删除 P0a、依赖 registry 改从 `skills/_sdk/deps.py` 读取、P3 的环境记录并入一次性冻结机制
（§10 第 4 版条目）。其余设计（P0b 残留、P1 探测注记、P2 需审批的本机安装）不变。

**前置**：
- **计划 0062 阶段一**（`core/` 整体搬进 `skills/_sdk/`、删除 `omicsclaw/core/`、凭据剔除移到框架启动边界）是本计划
  一切阶段的前置；它取代了第 3 版的 P0a（`docs/plans/0062-skill-sdk-boundary.md` §0.2 D1、§3.9）。
- **P0b** 在 0062 阶段一合入后实施，另依赖 Q3、Q12–Q14 的裁定。
- **P1** 在 0062 阶段一合入后开工；它读取的 `skills/_sdk/deps.py` 的 `DEPENDENCIES` 要到 **0062 阶段二**合入后才存在
  （0062 §3.9 第一行），所以 P1 的**合入**以 0062 阶段二为前置（Q19，owner 已确认：阶段一后开工、阶段二后合入、不写读取旧
  registry 的过渡代码）。另依赖已落地的 skill 索引与 `use_skill`
  （`omicsclaw/skills/`）、`bash` 的沙箱接缝（`entry/sandbox.py`）。
- **P2** 排在论文主线（0057–0060）之后（owner 已定）；另依赖权限层（`omicsclaw/permission/`）与 Q3–Q10。
- **P3** 依赖计划 0056（`omicsclaw/ensemble/`，已实现、未提交，本计划不改它）合入；冻结清单归 0059 所有，0061 只提
  "对 0059 的要求"（§4.12）。对 0056 的要求在 Q16、Q17 提给 owner。编号 0057–0060 已由 ensemble 系列预留，本计划不占用。

**给实现者的一条硬要求**：新代码的函数、类与模块 docstring 只写"是什么、做什么、参数与返回、
会抛什么"，以及会改变调用方式的行为说明（例如"探针失败时返回一行说明，不抛异常"）。计划编号、
裁定历史、与旧代码或 cellclaw 的对照、实测数字一律写进本计划、交付记录或**测试的 docstring**，
不写进生产代码注释。仓库里旧文件的高密度注释风格不构成反例。

---

## 0. 缘起、已定裁定与结论

### 0.1 缘起

owner 的项目做生信分析，真正跑分析时经常需要现场搭环境。旧框架里为此设计并实现过一套
"自适应环境搭建流程"（`docs/proposals/adaptive-environment-provisioning.md`，PR #25：
`ce767b30`、`0ca3b1c5`、`4486da97`）：在 skill runner 这一个接缝上探测依赖、缺了就静默建
`--system-site-packages` overlay venv 并装上 pip 叶子。旧栈拆除时（`33720785`、`259fb52a`）
这套代码随 runner 一起删除，树上留下了若干残留。本计划回答两件事：

1. **可行性审计**：旧流程每个组成部分该移植、重写还是丢弃，理由锚定到新框架的代码或已定裁定（§3）。
2. **整合设计**：整合的部分给出可落地的设计、分阶段与测试计划（§4–§6）；不整合的部分写明代价（§8）。

### 0.2 已定裁定（owner，不得推翻）

| # | 裁定 | 出处 |
|---|---|---|
| D1 | skill runner 按裁定移除；agent 读 `SKILL.md` 后用 `bash` 跑脚本；不重新引入通用 runner 或 `oc run`。0056 的 `run_skill` 是限于 ensemble 的例外（0056 §0.2 第 2 条） | `README.md`:56；`AGENTS.md` "Running a skill"（:228-237、:310-313）；`docs/FRAMEWORK-REBUILD.md`:1870-1888 |
| D2 | `SKILL.md` 是 skill 元数据唯一来源；`skill.yaml`、`requires:` frontmatter 与生成器已删除；依赖是正文 `## Dependencies` 散文，**且 AGENTS.md 明写"Nothing installs from the section"** | `AGENTS.md`:54-71、"The frontmatter contract"（:206-227）；计划 0045 §"删除五个键" |
| D3 | 遗传数据永不离开本机；沙箱威胁模型为此设计（`--network none`） | `CLAUDE.md`:323；`README.md`:66 |
| D4 | `common/`、`core/` 不是 legacy，skill 脚本依赖它们（第 4 版注：`core/` 由 0062 阶段一整体搬进 `skills/_sdk/`，skill 此后依赖的是 `_sdk`；D4 的"不是 legacy、不能丢"仍成立） | `README.md`:56；0062 §0.2 D2 |
| D5 | 0056 正在实施，不改它；需要的接缝写成"对 0056 的接口要求"，且不得违反 0056 已写定的分层（0056 §3.1） | 本任务；`docs/plans/0056-ensemble-foundation.md`:157-160 |
| D6 | **第 4 版只改三处**（owner 2026-09-24）：①删除 P0a，不建 `omicsclaw/core/child_env.py`，`core/` 断链与凭据剔除由 0062 阶段一处理，仍属 0061 的残留（如删除 `tests/test_adaptive_env_phase3.py`，0062 Q12）归 P0b；②依赖 registry 改为用 AST/`ast.literal_eval` 读 `skills/_sdk/deps.py` 的纯字面量 `DEPENDENCIES`（字段 `module`/`kind`/`install`/`description`/可选 `alt_env`/可选 `also`），名字解析顺序按 0062 §3.4，类别取 `kind`，安装白名单取 `[键, *also]`；框架不 import `skills/_sdk`，只读文件契约；③P3 的环境记录并入一次性冻结机制：论文实验与 SI 用可读的冻结清单 `bench/freezes/<name>.yaml` 加 git tag（框架 tag、镜像标签与冻结时记一次的 digest、评估器、dev/held-out 划分、种子），trial 只记冻结名，SI 另记分支名；冻结期间改任何东西都开新冻结并重跑基线，不同冻结之间不比较；**否决逐 trial 记录内容哈希**（不利于人读与审核）；冻结清单归 0059，0061 只写"对 0059 的要求"。其余设计（P0b、P1、P2）保持不变。实施顺序：0062 阶段一合入后先做 P0b 与 P1；P2 排在 0057–0060 之后 | owner 2026-09-24；`docs/plans/0062-skill-sdk-boundary.md` §0.2 D1/D7、§3.4、§3.9 |
| D7 | **第 6 版只改 P2**（owner 2026-09-24，§9.1 Q24、Q25）：①**安装不借助哈希确保**：去掉 `--require-hashes`、"report 无哈希即失败"、需求文件里的 `--hash=sha256:…`，以及卡片、结果、`.meta.json`、日志中所有为哈希服务的字段和逻辑；overlay 的 key 保持现状——它是 base 全量发行包清单的摘要，只用来判断缓存能否复用，不属于安装校验。②**明文索引"部署声明即信任"**：部署在配置里显式列出的索引主机即允许从它安装，包括 http（如本机内部代理 `http://10.20.16.126:8081` 加 `trusted-host`）；审批卡片对明文源给出醒目提示；未声明的主机一律拒绝。**②已被 D8 取代（第 7.2 版）** | owner 2026-09-24 对话 |
| D8 | **第 7.2 版只改"包从哪来"这一条**（owner 2026-09-25，§9.1 Q34）：`install_skill_deps` **直接沿用本机 pip 的配置联网安装**，与用户自己在终端敲 `pip install` 相同；不再由部署在 OmicsClaw 配置里声明来源，删除第 7 版的 `skill_env_index_url`、`skill_env_extra_index_urls`、`skill_env_find_links`、`skill_env_proxy`、`skill_env_cert`、`skill_env_client_cert`、来源文法、迁移对照与"未配来源即拒绝启动"；审批卡片如实写明"按本机 pip 配置安装，来源未经 OmicsClaw 核对"。理由：被带偏的 agent 本就可以绕开安装工具，直接 `bash pip install --index-url <任意地址>` 装进 base；来源声明只让"安装工具这条路上卡片不说谎"，对单人本机部署，这点收益抵不上六个配置项、一套文法、迁移说明与测试的代价；也与 Q5"审批姿态与 `bash` 同"一致。其余 P2 设计（只补缺、钉版本、只装 wheel、`pip check` 前后差集、落盘与顶层名核对、无凭据验证、锁与回滚、子进程临时 cwd 与 `-I`、spec 文法）不变。日后若开放到多人共享服务器、Channel 或常开 `/auto` 的场景，再以可选配置加回"锁定来源"（§8） | owner 2026-09-25 对话 |

D2 的最后一句意味着：让 `## Dependencies` 成为**安装来源**是改契约，必须由 owner 明确拍板（Q3）。

### 0.3 结论先行

**可行性审计一句话**：**可以部分整合**——旧流程的"子进程探针"与"overlay venv 机械层"在新框架下前提
仍成立、并已在本机实测与复跑（§2 D 组），应重写为一个不依赖 runner 的纯库；而它的**接缝**（runner）、
**默认静默安装**、**依赖集合来源**（`requires:` frontmatter）、**模式环境变量**以及 **`oc env` / Desktop
端点**这些表面，前提在新框架下已不成立，应丢弃或改写。旧流程里被一并删除的 `environment.py` 让 `core/`
三个模块无法 import、10 个 single-cell 主脚本（含地基 `sc_preprocess.py`）连 `--help` 都跑不起来（F11）——
**第 4 版起这件事不再由 0061 修**：根因是 skill 深度 import 框架包，0062 阶段一把 `core/` 整体搬进 `skills/_sdk/`，
凭据剔除移到 `bash` 本机路径与 ensemble `LocalExecutor`（0062 §3.2、§3.7），是本计划的前置。

**推荐的整合形态**（§4.1，Q1）：

```
skills/_sdk/deps.py   DEPENDENCIES 纯字面量（0062 阶段二）  ──只读文件（ast.literal_eval），不 import──┐
skills/**/SKILL.md    ## Dependencies 包名行                  ──只读文件────────────────────────────────┤
                                                                                                        ▼
omicsclaw/skillenv/   纯库：包名行解析 + registry 读取与名字解析（0062 §3.4 顺序）+ 子进程探针 + overlay 机械层
   │
   ├─ use_skill 结果末尾附"环境检查"注记（只读；read-only 模式不附；工具表不变）  ← agent 的 bash 路径
   ├─ 新工具 install_skill_deps（缺省不挂载，部署显式开 install 才有；需审批；
   │    只装指名的、声明过的包，按 registry 展开为 [键, *also]；只补缺、钉版本、只装 wheel、沿用本机 pip 配置的来源联网安装（第 7.2 版）；
   │    装进内容寻址 overlay，返回应使用的解释器路径）                            ← agent 的 bash 路径
   └─ 0056 run_skill：不做任何供给；环境记录分两种场景                           ← ensemble 路径
        ├─ 冻结运行（论文实验、SI）：环境只在 0059 的冻结清单 bench/freezes/<name>.yaml 里记一次，trial 只记冻结名
        └─ 非冻结运行（日常、开发）：经 entry 注入的回调在 trial 里记解释器与声明包版本，供排查
```

**缺省只探测、不安装**（`skill_env=probe`，Q7）。不改写 `bash` 命令，不走 hooks，不在 `run_skill` 里安装，
沙箱里不安装。四个阶段：P0b 残留与文档、P1 探测与报告、P2 本机安装（显式开启，排在 0057–0060 之后）、P3 与 0056/0059
对接（第 3 版的 P0a 已由 0062 阶段一取代）。

---

## 1. 目标

| # | 目标 | 可观察的结果 |
|---|---|---|
| G1 | （第 4 版删除）`core/` 恢复可 import、10 个 sc 脚本 `--help` 恢复 | 由 0062 阶段一的 G1 取代（0062 §1：94 个主脚本 `--help` 90 成功） |
| G2 | 残留逐项处置 | §4.8 表中每一项都有落地动作、明确的"随某裁定 / 某计划处置"或"不在范围"；四个旧环境变量进入 `.env.example` 退役清单；`tests/test_adaptive_env_phase3.py` 已删除 |
| G3 | 依赖声明成为可机读契约而不复活 frontmatter | 94 个 `## Dependencies` 的**包名行**由测试钉住（不钉散文）；`skills/_sdk/deps.py` 的 `DEPENDENCIES` 以 AST 读取、不 import，读取器与名字解析（0062 §3.4 顺序）有单测；声明名中落到回落规则的集合钉为冻结表；registry 引用与声明的一致性有测试 |
| G4 | 探测与报告 | `skill_env=probe`（缺省）时 `use_skill` 结果附注记，写明 `bash` 实际用的 `python`、缺什么、各缺项属哪类、有无现成 overlay；探针不执行工作区代码 |
| G5 | 需审批、显式开启的本机安装 | `install_skill_deps` 只在 `skill_env=install` 且本机时挂载；`packages` 必填；只装白名单内的包；只补缺、钉版本、仅 wheel、来源与传输参数只取自部署的 OmicsClaw 配置（第 6 版起不校验哈希，第 7 版起不读 pip 配置）；依赖约束不满足即回滚；从不改动 base；复用不再审批、不联网 |
| G6 | 消融 | `off` 时系统提示、工具表与 `use_skill` 输出与改动前逐字节相同；`probe` 时系统提示与工具表仍逐字节相同（缺省配置下 0056 的 golden 与 `MOUNTED` 都不用改）；`install` 时工具表只在固定位置插入一项 |
| G7 | 可复现 | overlay 目录自带 `.meta.json`；冻结运行的环境信息写进 0059 冻结清单（一次，可读，无逐 trial 哈希），trial 只记冻结名；非冻结运行的 0056 试验记录解释器与声明包版本（Q17） |

---

## 2. 现状（亲自核实；行号以 2026-09-24 工作树为准，实施时按符号名定位）

> `AGENTS.md`、`README.md`、`entry/assembly.py`、`entry/config.py`、`sandbox/config.py`、`.env.example`、
> `tests/test_env_example.py` 正被其他会话（0056）同时改写，核实期间行号已漂移过两次；引用这些文件时
> 一并给出小节名或符号名，以它们为准。

"`33720785^:<路径>`"指删除提交的父提交里的文件（`git show 33720785^:<路径>`）。标"在途"者是 0056
已实现、尚未提交的代码，只作接口参考。D 组每条都写了第 2 版的**复跑结果**；完整复跑命令在附录 A。

> **第 4 版注**：本节事实描述的是 0062 实施**之前**的工作树（第 4 版对 `omicsclaw/core/`、`skills/_sdk/`、
> `ensemble/`、`FRAMEWORK-REBUILD.md` 的行号重新核对过，`skills/_sdk/` 今天仍不存在）。0062 合入后会失效或改变的事实：
> F11、F12、F14 的 `core/` 部分与 F42 由 **0062 阶段一**处理；F43 的守卫由 0062 的 B2/B3 吸收；F22、F59 描述的四份
> `_lib/dependency_manager.py` 在 **0062 阶段二**合并为 `skills/_sdk/deps.py`，**合入后以 `_sdk/deps.py` 为准**（F64）；
> F52、F58 的扫描口径在阶段二后改为 0062 F29 的调用名规则（§4.2）。

### A. 旧流程本体

| # | 事实 | 出处 |
|---|---|---|
| F1 | 旧提案状态为"Phase 0–3 已实现"，**默认开启**，用 `OMICSCLAW_SKIP_ADAPTIVE_ENV=1` 或 `OMICSCLAW_ADAPTIVE_ENV=off` 关闭；自述范围只限 pip 叶子，不管 conda 重栈、R、CLI；§8 要求 "always probe via subprocess with the final env" | `docs/proposals/adaptive-environment-provisioning.md`:3-22、:40-48、:327 |
| F2 | **实际实现的依赖集合来源是 `SKILL.md` 的 `requires:` frontmatter**（`skill_info["requires"]`），不是提案 §6 写的"`_lib` registry + `parameters.yaml`" | `33720785^:omicsclaw/skill/execution/dep_spec.py`:18-31、:234-250；提案 :257-278 |
| F3 | 可装与否靠手写名单分类：`_BASE_PIP_SAFE`、`_CONDA_PREFERRED`、`_DENY`、`_VCS_ONLY`；import 名桥接读 4 个域的 `DEPENDENCY_REGISTRY`（`module_name` 与 `import_name` 两种字段都读）；版本约束取 `pyproject` extras | `dep_spec.py`:70-127、:135-162、:165-197 |
| F4 | resolver：模式 `off/probe/on` 默认 `on`；探针是子进程 `find_spec`，`find_spec` 抛异常视为"存在"，子进程失败视为"不确定"；**探针 cwd 用脚本所在目录，与真实运行一致**；任何失败都静默回落 base 解释器；带进度回调 `status_cb` | `33720785^:omicsclaw/skill/execution/env_resolver.py`:103-117、:59-68、:129-171、:139-141、:185、:294-300、:367-369、:41-53 |
| F5 | overlay：key = sha256(base 真实路径、mtime、平台、机器、版本\|prefix、**agent 进程的** `CONDA_PREFIX`、排序后的 specs)[:16]；fingerprint 另加 resolver 标签；`uv venv --system-site-packages`（不 seed）→ stdlib venv 回退；**用 venv 自己的 pip + `--no-deps` 安装，明确不用 `uv pip`**；`fcntl.flock` 锁 300 s；list/remove/clean 以"16 位 hex 目录名 + 标记文件"防误删；缓存根 `OMICSCLAW_ENV_DIR` > `XDG_CACHE_HOME` > `~/.cache` | `33720785^:omicsclaw/skill/execution/venv_provision.py`:118-158、:304-347、:227-268、:364-433、:63-74 |
| F6 | 唯一接缝在 runner：`_prepare_skill_run` 构造 argv/env（含 `PYTHONNOUSERSITE=1`）后调 resolver，替换 `cmd[0]` 并合并 overlay env；异步路径用 `to_thread` 避免阻塞事件循环 | `33720785^:omicsclaw/skill/runner.py`:686-692、:745-760、:1312-1331 |
| F7 | **旧栈后期自己关掉了它**：受治理的 V1 执行路径以 `_allow_adaptive_environment=False` 调 runner，注释写"resource-ready Skill runs in the bound base runtime rather than starting unowned setup/install subprocesses" | `33720785^:omicsclaw/control/run_runtime.py`:373；`33720785^:omicsclaw/skill/runner.py`:734-738 |
| F8 | 来源记录：`SkillRunResult.runtime_source ∈ {base, skip, probe, venv:<key>}`；基础解释器由 `OMICSCLAW_RUN_PYTHON`（缺省 `sys.executable`）决定 | `33720785^:omicsclaw/skill/result.py`:86；`33720785^:omicsclaw/skill/execution/python_runtime.py`:25-57 |
| F9 | 旧测试 5 个文件约 90 例；真实安装的 E2E 只在 `OMICSCLAW_TEST_NETWORK=1` 时运行 | `33720785^:tests/test_venv_provision.py`:186-205；`33720785^:tests/test_env_resolver.py`:357-361 |

### B. 旧流程与旧栈在树上的残留

| # | 事实 | 出处 |
|---|---|---|
| F10 | `tests/test_adaptive_env_phase3.py` **仍被 git 跟踪**，收集即报 `No module named 'omicsclaw.skill'` | `git ls-files`；`pytest --co tests/test_adaptive_env_phase3.py` |
| F11 | `core/external_env.py`:25、`core/dependency_manager.py`:8（且 :7 先 import `external_env`）、`core/r_script_runner.py`:20 都 import 已删除的 `omicsclaw.skill.execution.environment`，三模块不可 import。**实测**（`OmicsClaw` 环境，逐个跑 skill 目录顶层 104 个 `.py` 的 `--help`；其中 94 个是每个 skill 一个的主脚本，另 10 个是 `consensus-interpret/_*.py` 辅助模块）：**94 个主脚本 80 成功、14 失败**，均为 `No module named 'omicsclaw.skill'`——10 个 single-cell 脚本经此链（9 个经 `external_env.py`:25，`sc_pseudotime.py` 经 `r_script_runner.py`:20；含地基 `sc_preprocess.py`），4 个 consensus 脚本经 `runtime/workflow/fan_out.py`:25。`tests/test_external_env.py`、`tests/test_r_script_runner.py`、`tests/test_r_script_runner_environment.py` 收集错误。**第 4 版**：由 0062 阶段一修复（其 F9、F10、F34；三个测试文件搬到 `tests/sdk/`） | 各文件；批量 `--help` 探针 |
| F12 | 被删的 `environment.py` 有两个函数 `is_internal_control_credential_name`、`scrub_internal_control_credentials` 与三个凭据名；其中 `OMICSCLAW_REMOTE_AUTH_TOKEN` 仍是 Desktop 的 bearer token。**第 4 版**：0062 从 skill 侧彻底删除剔除，改在 `bash` 本机路径与 `LocalExecutor` 用 `without_control_credentials` 剔除这一个名字（0062 §3.7、Q7） | `33720785^:omicsclaw/skill/execution/environment.py`:1-38；`omicsclaw/launch/_surfaces.py`:351 |
| F13 | `docs/FRAMEWORK-REBUILD.md` "Kept and importable"（第 4 版核对在 :1896，第 3 版写的 :1861 已漂移）称 `common/`、`core/` 可 import——对 `core/` 不成立（F11）。0062 阶段一第 6 步改写这一句 | 同左 |
| F14 | BANKSY 子环境链路断了三处：`0_setup_env.sh`:584-587 的 Tier 5（只在 `--with-banksy` 或 `OMICSCLAW_WITH_BANKSY=1` 时运行）引用 `environments/banksy.yml`，该目录在 `259fb52a` 被当作 assets 删除，`set -euo pipefail` 下 `bootstrap_subenv` 返回 1 即中止；`skills/spatial/_lib/domains.py` `identify_domains_banksy` 的子环境回退（:945 起）import `core.external_env`，现在抛 `ModuleNotFoundError` 而不是设计中的 `EnvNotFoundError` 提示（**0062 阶段一后恢复**，其 F11、用例 9）；`skills/spatial/_lib/dependency_manager.py`:97-107 的 `availability_check` 同样 import 它，但 `is_available`（:266-271）吞掉异常返回 `False`（0062 阶段二以 `alt_env` 字段取代这个 lambda）。`tools/README.md`:17-18 仍以 `environments/banksy.yml` 为范例；`0_setup_env.sh`:4 注释写"4 tiers"，文件实有 Tier 1–5 | 各文件；`git show 259fb52a --stat` |
| F15 | `remote/routers/env.py`:14 import 已删除的 `omicsclaw.diagnostics`；三个自适应端点（:90-128）在函数体内 import 已删除的 `omicsclaw.skill.execution.*`；`remote/routers/jobs.py`:31 先 import 已删除的 `omicsclaw.control`，:41 再 import env。**实测**（`OmicsClaw` 环境，fastapi 0.136.1）：remote 下 **12 个叶子模块**只有 `schemas`、`auth`、`storage`、`routers.connections`、`routers.sessions` 5 个可 import，`routers.env/jobs/datasets/artifacts`、`app_integration`、`run_wire`、`runtime_binding` 7 个不可。新栈 `entry/`、`launch/` 无任何 import remote；新 Desktop 只挂两个路由 | `entry/desktop/wire_contract.py`:58 `SERVED_PATHS = ("/chat/stream", "/health")`；`AGENTS.md`:156 却写 "remote/ … Imports." |
| F16 | `remote/schemas.py`：`EnvDoctorCheck/EnvDoctorReport`（:27-41）、`OverlayInfo/OverlayListResponse/OverlayCleanRequest/OverlayCleanResponse/AdaptiveModeResponse/AdaptiveModeUpdateRequest`（:44-83）、`Job.runtime_source`（:156-159） | 同左 |
| F17 | `autoagent/constants.py`:36-46 的 `SUBPROCESS_ENV_WHITELIST` 含 `OMICSCLAW_ADAPTIVE_ENV`、`OMICSCLAW_SKIP_ADAPTIVE_ENV`、`OMICSCLAW_ENV_DIR`、`OMICSCLAW_RUN_PYTHON`（autoagent 不可 import，只读参考，`AGENTS.md`:182-185）。**0056 在途实现把这四个名字原样复制进了 `omicsclaw/ensemble/execution.py` 的 `ENV_WHITELIST`**（第 4 版核对：集合在 :34-43，四个名字在 :39-40；在途） | 同左 |
| F18 | 上述四个变量全仓无读取者（只剩 F15、F17 的死代码与拷贝）；`.env.example` 未提及它们。退役变量的既有机制是 `.env.example` "# 12. No longer read by the rebuilt stack"（:383-）加 `tests/test_env_example.py` 的 `RETIRED`（:72-） | 全仓 grep；同左 |
| F19 | `pyproject.toml`:77-79 的注释仍说 STAGATE-pyG "is classified `vcs` in omicsclaw/skill/execution/dep_spec.py"；`genomics/proteomics/metabolomics` extras 为空（:242-246）；`banksy` extra 在 :327-331 | 同左 |
| F43 | **import 不存在的 `omicsclaw.*` 模块**（AST 扫描，按"模块文件在盘上是否存在"判定，因此自动覆盖全部已删除的包：`skill`、`providers`、`control`、`services`、`autonomous`、`execution`、`loaders`、`agents`、`knowledge`、`extensions`、`analysis_router`、`research` 与 `diagnostics.py`，均已核实不在盘上）。范围 `omicsclaw/common`、`omicsclaw/core`、`skills/**`：生产代码 4 处——`core/` 三处（F11）与 **`skills/spatial/consensus-interpret/_llm.py`:79 惰性 import `omicsclaw.providers.chat_completion`**（`--help` 测不出，不带 `--no-llm` 运行时失败）；`skills/**/tests/` 下 3 个被跟踪的基准脚本在函数体内 import `omicsclaw.skill.runner`：`bulkrna-enrichment/tests/biomnibench_da12_2.py`:236、`sc-preprocessing/tests/omicbench_preprocessing.py`:114、`sc-pseudotime/tests/scagentbench_paga.py`:190（文件名不以 `test_` 开头，pytest 不收集）。`omicsclaw/common/notebook_export.py`:302 的 `omicsclaw.skill.registry` 在生成 notebook 的字符串模板里，不是 import。**第 4 版**：`core/` 三处随 0062 阶段一消失；skill 侧的"import 不存在模块"守卫由 0062 的 B2（`skills/**` 非测试与模板）与 B3 吸收，`_llm.py` 是其具名已知项 | `/tmp` 下的 AST 扫描脚本（附录 A） |
| F44 | `tests/` 下另有 11 个被跟踪的文件 import 不存在的模块：`test_adaptive_env_phase3.py`（F10）、`test_skill_runner_contract.py`、`test_bot_n_epochs_routing.py`、`test_server_skill_detail.py`、`test_benchmark_campaign.py`、`test_evaluation_protocol.py`、`test_autoagent_output_ownership.py`、`test_discover_file_trust.py`（`omicsclaw.services`）、`test_skill_promotion_sidechannel.py`（`control`、`runtime.agent/context/tools`）、`tests/runtime/workflow/test_fan_out.py`、`tests/runtime/preflight/test_sc_batch.py` | 同上扫描，限 `git ls-files tests` |
| F57 | **Desktop App（另一个仓库）残留**：本机检出 `/workspace/algorithm/zhouwg_project/OmicsClaw-App`（HEAD `11f69cb`）里调用 `/env/*` 的地方至少有：`src/lib/adaptive-env-proxy.ts`（`/env/overlays`、`/env/clean`、`/env/adaptive-mode`）、`src/app/api/env/{overlays,adaptive-mode,doctor}/route.ts`、`src/app/api/runtimes/[id]/ping/route.ts`:67、`src/app/api/connections/[id]/test/route.ts`:108、`src/lib/probe-profile.ts`:119、`electron/main.ts`:707（后四处都是 `/env/doctor`）。新后端对这些路径返回 404：`probe-profile.ts`:125 把非 401 判为 `inconclusive`，连接测试也把缺 `/env/doctor` 视为非致命（`connections/[id]/test/route.ts`:38、:125）；新后端的 `/health` 遇到错误 token 返回 401（`entry/desktop/server.py`:390-395），所以**鉴权不会被误判**，后果只是 App 的 Env 页与 overlay/模式面板不可用。App 启动本地后端时把所选解释器的 bin 目录前置到 PATH（`electron/local-runtime-plan.ts`:88-91）——因此 Desktop 本机模式下 `bash` 的 `python` 就是所选解释器 | 同左 |

### C. 新框架里相关的层

| # | 事实 | 出处 |
|---|---|---|
| F20 | **`## Dependencies` 可机读**：94/94 个 `SKILL.md` 都有，格式完全一致（固定说明句 + 一行以反引号包裹、逗号分隔的 PyPI 名），共 63 个不同包名；逐 skill 与 `33720785^` 的 `requires:` **完全相同（94/94）**。它是 skill 级（不分方法）、只列 Python 包；`AGENTS.md` 明说"Nothing installs from the section … It is there so an agent about to run a script knows what the script needs" | 解析脚本逐文件核对；`AGENTS.md`:65-71；`CLAUDE.md`:188-189 |
| F21 | frontmatter 只读 4 键，`Skill` 记录无依赖字段；`use_skill` 在正文后追加 "Skill directory: …"；其 policy 为 `AUTO/read_only/concurrency_safe/allowed_in_background`；`FunctionTool` 支持 async 函数 | `AGENTS.md` "The frontmatter contract"（:206-227）；`skills/skill.py`:11-81；`skills/use_skill.py`:40-47、:99-102；`tools/function_tool.py`:191-198 |
| F22 | `_lib` registry：4 个域共 74 条（spatial 33、singlecell 33、proteomics 4、metabolomics 4），62 个不同键，**全部是可用 `ast` 静态读取的字面量**；覆盖 63 个声明名中的 46 个，其余 17 个大多是基础库（numpy、pandas、scipy 等），**但也含 `mygene`、`SpatialDE`（注册键是小写的 `spatialde`）这类非基础包**；17 个里只有 `PyYAML→yaml`、`scikit-learn→sklearn` 不能由"`-` 换 `_`"得到 import 名。`SpatialDE` 只有按 PEP 503 规范化后才能匹配到键 `spatialde`，而该键的 `module_name` 是 `NaiveDE`（`skills/spatial/_lib/dependency_manager.py`:166-169；`_lib/genes.py`:246-248 同时 import `SpatialDE` 与 `NaiveDE`）——registry 的 `module_name` 可能是"代表模块"而非包自身。3 条 `pip install git+…`（STAGATE-pyG、pybanksy、STalign），2 条 `Rscript`（xcms、metaboanalyst）；字段名 spatial/singlecell 为 `module_name`、proteomics/metabolomics 为 `import_name`。genomics/bulkrna/literature 无 registry。**第 4 版：这是 0062 之前的现状；0062 阶段二合入后以 `skills/_sdk/deps.py` 为准**（F64） | `skills/*/_lib/dependency_manager.py`；AST 统计脚本 |
| F52 | **`## Dependencies` 有漏报**：`spatial-domains` 支持 `cellcharter` 方法（`skills/spatial/_lib/domains.py`:40 `SUPPORTED_METHODS`；:1061 `require("cellcharter")`），但 94 个 skill 的 `## Dependencies` 都没有它。全仓 `require("…")` 字面量 28 个，按 registry 映射后只有 `cellcharter` 无任何 skill 声明（`scvi→scvi-tools`、`tangram→tangram-sc`、`paste→paste-bio` 都已声明）。这是"全域"粒度；逐 skill 粒度的漏报更多，见 F58。（0062 F29 按更宽的调用规则——`require`/`is_available`/`install_hint`/`get_dependency` 与依赖模块的 `get`——数出 32 个不同调用名，按其解析顺序全部命中 registry、零回落；阶段二合入后一致性测试以该规则为准） | grep + registry 映射脚本 |
| F23 | `bash` 本机路径 `create_subprocess_exec("bash", "-c", …)` **不传 `env=`**，继承 agent 进程全部环境，`python` 由 PATH 解析；`BashEnvironment` 只有 `run_bash(command, cwd, timeout)`；policy 为 `HIGH/ASK/prompts_for_itself`；工具描述随本机/沙箱不同；`_signal` 直接 `os.killpg`，无 Windows 分支——新栈 `bash` 只支持 POSIX | `tools/builtin/bash.py`:864-873、:369-406、:490-499、:585、:899 |
| F24 | 沙箱：网络默认 `none`，**但可配置**（`isolates_network` 只在运行中且网络为 `none` 时为真）；`/tmp` tmpfs 与 pids 上限已被在途 0056 上调为 `64g` 与 `65536`；`HOME=/tmp`；以宿主 `uid:gid` 运行；只读挂载在 `docker run` 时一次定死；`run_bash` 无 env 参数，且每次都在 `<workspace>/.omicsclaw/sandbox` 下写 pid 与 log 文件；**系统提示在无网沙箱下写 "downloads, package installs and remote APIs fail by design. Use the software already in the image."**；`sandbox_auto_approve` 只在无网络沙箱生效；起不来时降级到本机（只在 `sandbox_required=false` 时）或拒绝启动；镜像无默认值、不拉取、由运维决定；仓库里没有 Dockerfile；在途 0056 把 `omicsclaw/`、`skills/` 以只读同路径挂进容器（`sandbox_code_in_image`） | `sandbox/config.py`:44、:59、:67、:70；`sandbox/container.py`:31、:92-98、:111；`sandbox/environment.py`:97-117；`entry/sandbox.py`:67-70、:172-194、:197-214、:217-240；`entry/config.py`:425、:537-（在途）；`docs/plans/0036-sandbox-layer.md`:77-79 |
| F25 | 权限：闸门阶段 bypass → read-only → 受保护路径 → 规则 → 危险模式 → auto-approve → 工具自身 `approval_mode`；**闸门放行后 `_run_settled` 把有效策略改成 `AUTO`，工具内部的 `require_approval` 立即返回**。规则按**工具名**匹配（`toolName(pattern)`），`bash(pip install*)` 管不到别的工具；该规则本身只是 `rules.py` 模块 docstring 里的示例，仓库不附带默认规则；28 条危险模式里没有任何 pip/conda/uv/npm 安装。因此今天 `bash("pip install x")` 在 default 模式下与任何 bash 一样被问，在 auto-approve、`/auto on`、会话 `s` 授权下不问 | `permission/gate.py` `resolve`（:259-353，auto-approve 在 :340）、`_run_settled`（:594-611）；`tools/context.py`:645-646；`permission/rules.py`:1-30；`permission/danger.py`:93-252 |
| F26 | `prompts_for_itself=True` 是被行为测试核验的声明：`tests/permission/test_foundation_tools_keep_their_prompts.py` 用拒绝型审批通道跑每个声明它的工具，断言确实问了；其 docstring 的前提是 "require_approval raises before any tool reaches a socket, a subprocess or a file"；覆盖集合是写死的名单 | 同左 :1-17（前提在 :9-13）、:109-150 |
| F27 | hooks 在权限闸门**之内**（先 `hook_tools` 再 `gate_tools`）；hook 不能问人；hook 改写的参数不再经闸门复核（"executes a command no rule ever saw"） | `hooks/__init__.py`:57-76；`hooks/base.py`:117-134；`entry/assembly.py` `build_app`（:1201-1210） |
| F28 | 审批的 surface 差异：`approval_timeout_s` 默认 `None`（一直等）；Channel 必须设数值，到期即拒绝；**Desktop 未移植 `/chat/permission`，需审批的工具会一直等，`CLAUDE.md` 因此建议 Desktop "Prefer auto-approved work here"**；`start_desktop` 在装配前自行解析配置，可以按 surface 收紧 | `entry/config.py`:207-213；`entry/channel/runtime.py`:266-280；`CLAUDE.md`:278-281；`launch/_surfaces.py` `start_desktop`（:1069-1100） |
| F29 | 装配：`foundation_tools` 依次挂六个基础工具、`use_skill`（:365）、`plan_write`（:367）、`memory_*`（:369），在途的 0056 又在其后挂 `run_skill`（:371-373），`build_app` 再追加 MCP 与 `task`；开关先例 `planning/subagents/memory`，配置经 `_Option` 表同时接受 flag 与环境变量；`## Environment` 段只有工作区、平台、日期；默认系统提示包含工作区的 `CLAUDE.md`；`MOUNTED` 是完整名单；`_LOWER_LAYERS` 是分层测试名单 | `entry/assembly.py` `foundation_tools`（:298-374）、`_environment_source`（:466-493）、`DEFAULT_CONTRACT_FILE`（:213）；`entry/config.py`:233-279、`_Option`/`_OPTIONS`（:746-、:764-）；`tests/entry/test_permission_wiring.py`:49-61；`tests/entry/test_entry_is_the_top_layer.py`:39- |
| F53 | **`use_skill` 不是 skill 正文的唯一入口**：子代理定义可用 `ChildPrompt.skills` 预载 skill 正文进系统提示（`entry/subagent.py`:291-297、`subagent/prompt.py`:65-77）；`CLAUDE.md` 也直接给出脚本命令。这两条路径看不到注记 | 同左 |
| F54 | read-only 模式一律拒绝 `bash`（`permission/modes.py`:41-49），`use_skill` 却因 `read_only=True` 照常放行 | 同左 |
| F30 | 0056（计划 + 在途实现）：`ensemble_python` 本机缺省为 agent 进程的 `sys.executable`、容器缺省为 `python`；`CommandExecutor` 有 `python` 属性与"跑短探针"的 `capture()`；试验 provenance 已有 `python/location/image`；试验环境**不含** `PYTHONNOUSERSITE`；`run_skill` 为 `AUTO`；golden 快照 `tests/entry/golden/ensemble_off_{prompt.txt,tools.json}` 已生成（在途） | 0056 §3.3、§3.8、§3.11；`ensemble/execution.py`:67-100、:112-114、:199-201；`ensemble/runner.py` `run`/`_bind`（第 4 版核对：:327、:371；provenance 字典在 :352-359）、`trial_environment`（:463-）（均在途） |
| F55 | **0056 的分层规定**：`ensemble` 只可 import `schema`、`tools`、`skills` 与标准库，由 `tests/ensemble/test_ensemble_is_a_layer.py` 钉住；`RunStore.bind_run` **只在第一次**写 `run.json`，之后只校验 skill 与 input 的 sha256——写进 `run.json` 的任何环境信息只反映首次绑定时的状态 | `docs/plans/0056-ensemble-foundation.md`:157-160；`ensemble/store.py` `check_run`（第 4 版核对：:106-）、`bind_run`（:125-）（在途） |
| F56 | （编号空缺：该事实在第 2 版并入 F28） | — |
| F31 | 安装期流程：`0_setup_env.sh` Tier 1 conda env（:85-346）、Tier 2 `uv pip install -e ".[full,singlecell-upstream]"` 与 velocyto（:348-391）、Tier 3 GitHub R 包（:401-528）、Tier 4 vendored 工具桩（:530-550）、Tier 5 banksy 子环境（:552-589）；`environment.yml` Tier 0 含 `python=3.11` 与 `uv`（:27-33）；README 推荐真分析走 `0_setup_env.sh`（:177-187、:397） | 同左 |

### D. 实测（全部在 `/tmp` 下完成，仓库内无产物；第 2 版逐条复跑）

| # | 事实（首跑） | 第 2 版复跑结果 / 来源 |
|---|---|---|
| F32 | 以 `OmicsClaw` 环境（Py 3.11.15）为 base：`python -m venv --system-site-packages`（带 ensurepip）3.2 s；`--without-pip --system-site-packages` 0.06 s；`uv venv --python <base> --system-site-packages` 0.12 s。三者 `bin/python` 都是指向宿主 base 解释器绝对路径的符号链接，`pyvenv.cfg` 为 `home = /opt/conda/envs/OmicsClaw/bin`；overlay 内可 import base 的 scanpy 1.11.5；`sys.path` 中 overlay 的 site-packages 排在 base 之前；无 seed 时 `<overlay>/bin/python -m pip` 用 base 的 pip 26.0.1 并装进 overlay | **复现**：3.17 s / 0.05 s / 0.05 s（uv 这次 0.05 s）；符号链接与 `home` 相同；scanpy 1.11.5；顺序 overlay→base；pip 26.0.1 来自 base |
| F33 | 旧的 `--no-deps`：装 mygene 成功，但 overlay 里 `import mygene` 失败（缺 `biothings_client`）；base 不受影响 | **复现**（离线：本地 wheelhouse + `PIP_NO_INDEX=1 PIP_FIND_LINKS`） |
| F34 | `pip install --dry-run --only-binary=:all: --report`（overlay 自己的 pip）**把 base 已装的包算作已满足**：mygene 只计划 2 个；pertpy 计划 22 个，其中 llvmlite、jax、jaxlib、scikit-misc、mpmath 与 base 同名。对 F37 的 14 个缺失包中非 git-only 的 11 个做纯 wheel dry-run：首跑 7 个解析出计划、6 个会遮蔽 base | **复现** mygene 2、pertpy 22 及其同名集合。另：复跑时 popv 也解析出计划（33 个），会遮蔽 **numpy 2.0.2→1.26.4、scikit-learn 1.8.0→1.7.2**、protobuf、tensorboard 等。合计 8 个可解析、7 个会遮蔽；**其中 4 个（SEACells、cnmf、velovi、cellbender）只因本机坏掉的 llvmlite/scikit-misc/mpmath 元数据（F48），3 个（pertpy 的 jax、omicverse 的 legendkit/click、popv 的 numpy 等）是真实的版本冲突** |
| F35 | `uv pip install --python <overlay> --dry-run` **无视 system-site**：mygene 计划 9 个（含 base 已有的 httpx、anyio、h11）；infercnvpy 计划 72 个 | **复现**：mygene 计划 9 个，其中 anyio、certifi、h11、httpcore、httpx、idna、typing-extensions 在 base 均已存在 |
| F36 | **只补缺**：dry-run 计划减去 base 已存在的发行包，以 `==` 钉版本、`--no-deps --only-binary=:all:` 安装 cnmf、palettable、mygene、biothings_client，0.79 s；overlay 内 `import cnmf, mygene` 成功，base 仍 import 不到 cnmf | **复现**（离线）：0.73 s，结果相同 |
| F37 | 探针：63 个 import 名 `find_spec` 0.05 s；经 `bash -c 'python -B -c …'` 0.046 s。`OmicsClaw` 缺 14 个（SEACells、STAGATE_pyG、STalign、banksy、cellbender、cnmf、mygene、omicverse、pertpy、popv、pyscenic、sccoda、simba、velovi）；`rapids_singlecell` 缺 48 个。列出 base 全部发行包名与版本并求哈希 0.34 s | **复现**：0.05 s；缺项相同；哈希 `387a23683aeca380` 不变，0.32 s |
| F38 | 离线确定性：`PIP_NO_INDEX=1 PIP_FIND_LINKS=<目录>` 下 dry-run 与安装完全离线可用；已满足的包（six）得到空计划 | **复现**（`rapids_singlecell` 为 base）：mygene → mygene 3.2.2 + biothings_client 0.5.1；six → 空 |
| F39 | 本机网络：pip 经内部代理索引可达；`simba-bio` "from versions: none"，`pyscenic` dry-run 300 s 超时，`sccoda`/`popv` 连接重试失败 | **部分变化**：`simba-bio` 相同；`pyscenic` 在 150 s 上限内再次超时；**`sccoda` 这次是 150 s 超时（首跑是连接重试失败），`popv` 这次成功解析**——网络结局本身不稳定，这正是"失败要如实报告"的理由 |
| F40 | 基线：`tests/skills tests/tools tests/sandbox tests/permission tests/hooks tests/entry/{test_assembly,test_permission_wiring,test_open_app,test_sandbox,test_entry_is_the_top_layer}.py tests/test_env_example.py` → 2061 passed, 2 skipped | **复跑：2066 passed, 2 skipped**（其他会话在途新增了测试） |
| F41 | 本机没有 docker/podman；`uv` 0.11.8 在 `OmicsClaw` 环境里 | 未变 |
| F42 | **P0a 可行性已模拟**：在 `/tmp` 放一个 `sitecustomize.py`，把 `33720785^` 的 `environment.py` 注入为 `omicsclaw.skill.execution.environment`（不改仓库），则 F11 的三个测试文件 23 passed, 3 skipped；10 个 single-cell 脚本 `--help` 全部退出 0；4 个 consensus 脚本仍失败（`No module named 'omicsclaw.skill.resource_scheduler'`） | 第 2 版新增，本身即复跑。**第 4 版**：P0a 已删除，本条只作历史证据；修复路径改为 0062 阶段一 |
| F45 | **探针在工作区 cwd 下会执行工作区代码并误报**：`python -c` 时 `sys.path[0]==''`。工作区放一个 `json.py`，朴素探针（`import json` 在前）会执行它；`importlib.metadata` 还会连带 import `csv`、`email`、`pathlib`、`zipfile`。工作区放一个空目录 `cellbender/`，`find_spec("cellbender")` 返回命名空间包（报"存在"），而 `python <skill 目录>/x.py` 真实运行时 `import cellbender` 失败。先把 `''`、`'.'` 从 `sys.path` 剔除再 import 其他模块，两个问题都消失 | 第 2 版新增（附录 A） |
| F46 | `OmicsClaw` 环境 `site.ENABLE_USER_SITE=True`，`USER_SITE=/root/.local/lib/python3.11/site-packages`（本机该目录不存在，所以没有实际差异；但探针继承环境时 user site 是开的） | 第 2 版新增 |
| F47 | **base 本身是 venv 时，overlay 看不到 base 的包**：在 venv `vbase`（`prefix=/tmp/…/vbase`、`base_prefix=/opt/conda/envs/OmicsClaw`）里装 mygene，再以 `vbase/bin/python -m venv --without-pip --system-site-packages` 建 overlay：其 `pyvenv.cfg` 的 `home` 指向底层 conda 解释器，overlay 能 import 底层的 scanpy、**import 不到 vbase 里的 mygene**。conda 环境与独立解释器 `prefix == base_prefix` | 第 2 版新增 |
| F48 | **base 元数据有重复与无名记录**：`OmicsClaw` 环境（cwd 为 `/tmp`、不设 `PYTHONPATH`；与只列 `site.getsitepackages()` 结果相同）**541 条记录**、533 个规范化名字；4 个名字有两条（llvmlite：dist-info 0.47.0 与 egg-info 0.43.0；numba 0.60.0/0.65.1；psutil 7.2.2/6.1.1；scikit-misc 0.0.0/0.5.2）；4 条无 `Name`（`distributed`、`tifffile`、`mpmath`、`dask` 的 dist-info，版本可从目录名读出）。`importlib.metadata.version("llvmlite")` 给 0.47.0，**实际 import 到的是 0.43.0**。第 2 版写的"542 条、omicsclaw 两条"是在仓库根目录下运行所致：`sys.path[0]==''` 把仓库里的 `omicsclaw.egg-info` 也算了进去——清单必须只取 base 自己的 site-packages | 第 2 版新增；第 3 版更正 |
| F49 | `pip check`（在 overlay 里跑，`PYTHONNOUSERSITE=1`）报出 base 既有的 14 条依赖违例（如 `numba 0.60.0 has requirement llvmlite<0.44…`、`pygpcca … jinja2==3.0.3`）；按"违例主语是否为本次新装的发行包"过滤后，cnmf/mygene 一条都没有——过滤后的 `pip check` 可作"保留的 base 版本是否满足新包约束"的判据。**第 3 版更正**：只看主语会漏掉"base 包依赖了新装包"一类违例（F60），改用装前装后两次的差集 | 第 2 版新增 |
| F50 | dry-run 的 `--report` 为每个制品给出 `download_info.archive_info.hashes.sha256`；以 `name==ver --hash=sha256:…` 写成需求文件、`--require-hashes` 安装：哈希不符被 pip 拒绝（"THESE PACKAGES DO NOT MATCH THE HASHES"），正确则安装成功 | 第 2 版新增。**第 6 版**：owner 裁定安装不借助哈希确保（Q24），设计不再使用本条，只作历史证据 |
| F51 | **pip 的安装位置可被环境与配置改走**：`PIP_TARGET=<dir>` 时，overlay 的 pip 把 six 装到了 `<dir>`，overlay 里没有。加 `--isolated` 后 `PIP_TARGET` 与 `~/.pip/pip.conf` 都被忽略，six 装进 overlay——但同时**本机配置的内部索引也被忽略**（dry-run 走向 `files.pythonhosted.org`），所以 `--isolated` 必须配合显式传入的索引参数。本机 pip 配置来源是 `/root/.pip/pip.conf`（`pip config debug`），含 `index-url` 与 `trusted-host`。**第 3 版更正**：`--isolated` 只跳过用户配置与 `PIP_*` 选项变量，全局配置与 `PIP_CONFIG_FILE` 仍然生效（F61），第 2 版"其余配置因 `--isolated` 一概不生效"的说法是错的 | 第 2 版新增；第 3 版更正 |
| F58 | **逐 skill 的漏报**（N-4）：对每个 skill 的主脚本，收集它自身与它 import 的 `skills.<domain>._lib.<模块>` 里 `require("…")`/`is_available("…")` 的字面量，按 registry 映射后对照该 skill 的 `## Dependencies`。若把 `skills/singlecell/_lib/preflight.py` 也算进去，21 个 skill 报漏（几乎都是 `liana`、`cellphonedb`——该模块按方法集中做预检，被所有 single-cell 脚本 import，模块粒度会误报）；排除这个共享预检模块后，**8 个 skill、9 处漏报**：`spatial-domains`→cellcharter、`spatial-integrate`→scanorama（`SUPPORTED_METHODS` 含它）、`sc-clustering`→louvain（脚本自己 `is_available("louvain")`）、`sc-integrate-cluster`→scvi-tools、`sc-qc`/`sc-filter`/`sc-preprocessing`/`scatac-preprocessing`→scrublet（经 `_lib/qc.py`，模块粒度，需逐个人工确认）。`get("…")` 不计入（与 `dict.get` 混淆）。**第 4 版**：0062 阶段二把调用形式改为 `from skills._sdk.deps import require` 与 `from skills._sdk import deps as <原别名>`（0062 §3.4），届时扫描规则改用 0062 F29 的 AST 规则（其中只把从依赖模块 import 的 `get` 计入，避开 `dict.get`），P1 实施时复跑并以复跑结果为准 | `/tmp` 扫描脚本（附录 A） |
| F59 | **并集白名单的规模与键名问题**（N-4）：若白名单 = `## Dependencies` ∪ 本域 registry 的 pip 类键，按 skill 计算的中位数：singlecell 8→40、spatial 9→37、proteomics 2→6、metabolomics 3→5；registry 键不等于 PyPI 名——metabolomics 的键 `mzmine` 的 `install_cmd` 是 `pip install pymzml`；singlecell 有 18 条 `install_cmd` 是 `pip install -e ".[singlecell-…]"`，从中得不到包名。**第 4 版**：键名问题由 0062 阶段二解决（键 = PyPI 名、`mzmine` 并入 `pymzml`、`pip` 类 `install` 统一为 `pip install <键> [also…]`，0062 §3.4、Q4）；规模问题（按 skill 扩大 4–5 倍）与 registry 是否合并无关，仍然成立 | 同上 |
| F60 | **`pip check` 按主语过滤会漏检**（N-1）：overlay 里 `pip check` 同时看得到 overlay 与 base。base 有 `corneto 1.0.0b7 requires cvxpy-base, which is not installed`；往 overlay 装一个假的 `cvxpy-base 0.0.1`（测试内造的 wheel），装后违例变为 `corneto 1.0.0b7 has requirement cvxpy-base>=1.5.1, but you have cvxpy-base 0.0.1.`——主语是 base 的 `corneto`，按"主语是新装包"过滤得到空集；**装前装后两次 `pip check` 取差集**则正好得到这一行（行数前后都是 14，只比行数也会漏） | 附录 A |
| F61 | **pip 配置与凭据**（N-2）：`pip/_internal/configuration.py` 的 `iter_config_files` 无条件加载全局配置，`PIP_CONFIG_FILE` 直接从 `os.environ` 读取；实测 `--isolated` 下把 `install.target` 写进 `PIP_CONFIG_FILE` 指向的文件，six 仍被装到 target 目录。`_load_config_files` 遇到 `PIP_CONFIG_FILE=os.devnull` 直接返回：实测 `PIP_CONFIG_FILE=/dev/null` 时 `/root/.pip/pip.conf` 不再生效（dry-run 去了 PyPI）。需求文件里的 `--index-url`、`--trusted-host`、`--no-index`、`--find-links` 行有效（实测经内部代理解析 mygene）；`PIP_CONFIG_FILE=/dev/null` 时 `PIP_TIMEOUT` 等环境变量仍生效。`pip config list` 把环境变量显示为 `:env:.<键>`，并**原样输出** `https://u:secret@…` 这类含凭据的 URL | 附录 A；pip 26.0.1 源码 |
| F62 | **锁文件放在会被删除的目录里会失效**（N-3）：A 持有 `<key>/.lock`，B 已打开同一路径在等锁；A 删掉整个 `<key>/` 后解锁，C 重建目录、打开同一路径——C 立即拿到锁，B 随后也拿到锁（锁的是已删除的 inode），两者同时在里面 | 附录 A |
| F63 | **顶层名碰撞**（次要 9）：palettable 3.3.3 的 `RECORD` 在 site-packages 顶层放了 `build/`、`docs/`、`scripts/`、`test/`，都没有 `__init__.py`（命名空间目录）；base 有同名的命名空间目录 `docs/` 与标准库常规包 `test`。命名空间片段不会遮蔽任何地方的常规包（import 系统先找常规包与模块），只会与同名命名空间合并，所以这次无害；但只按发行包名查遮蔽发现不了这类情况 | 附录 A |
| F64 | **合并后 registry 对声明名的覆盖**（第 4 版，按 0062 §3.4 的合并规则模拟：4 个旧 registry 取并集、`mzmine` 并入 `pymzml`，得 61 键，与 0062 §3.9 的规模一致）：63 个声明名里 **47 个**经 0062 解析顺序①②③命中（46 个键精确命中，`SpatialDE` 在阶段二后也是精确命中——今天键为 `spatialde`，靠规范化命中）；**16 个落到回落**：adjustText、anndata、dask、h5py、matplotlib、**mygene**、networkx、numpy、packaging、pandas、PyYAML、requests、scanpy、scikit-learn、scipy、statsmodels。其中 `PyYAML→yaml`、`scikit-learn→sklearn` 的 import 名与 PyPI 名无规律可循，**0062 的回落④（`module` = 名字本身）对这两个名字给出错误的 import 名**（§4.2、Q20）。`git` 类恰为 {STAGATE-pyG, pybanksy, STalign}，三者都有 skill 声明；`r` 类 {xcms, metaboanalyst} 与唯一带 `also` 的 `singler` **都没有任何 skill 在 `## Dependencies` 里声明** | 附录 A（`cover.py`） |
| F65 | **`pip config list` 对来源键的显示，以及 pip 实际采用哪些来源**（第 6 版）：值原样输出（含 userinfo，F61）；配置文件里的多值键按换行分隔、输出带前导 `\n`（`global.extra-index-url='\nhttps://a…/simple\nhttp://b…:8081/simple'`），环境变量的多值按空格分隔（`:env:.find-links='/opt/w1 /opt/w2'`）——pip 自己对多值键一律按空白切分。`pip install --dry-run -v` 的 "Looking in indexes / Looking in links" 两行证实：同一个键 `install.` **整体取代** `global.`、`:env:` 整体取代两者（替换，不合并）；`no-index` 去掉全部索引、保留 find-links；**什么都没配时 pip 用缺省的 `https://pypi.org/simple`，且不打印 "Looking in indexes"**——有效来源集合必须把这个缺省补进去。本机 pip.conf 另有 `global.index`，只供 `pip search`，安装不读。**第 7 版**：设计不再读 pip 配置（Q29），本条只作背景——它说明了从 pip 配置推导来源要处理多少细节（另见审核方的 m2：`pip config list` 的值是 Python repr），而 F77–F79 说明这样推导出来的结果还靠不住 | 附录 A（F65） |
| F66 | **report 里制品的 URL 与 http 索引**（第 6 版）：`download_info.url` 是索引页给出的**文件链接**，主机不一定是索引主机——经 PyPI 时为 `https://files.pythonhosted.org/packages/…/six-1.16.0-py2.py3-none-any.whl`（索引是 `pypi.org`）；经本机内部代理时与索引同主机（`http://10.20.16.126:8081/repository/pypi-proxy/packages/six/1.16.0/…`）；经 find-links 本地目录时为 `file:///…/x.whl`。索引 URL 带 `u:tok@` 时，report 里的文件 URL 不带 userinfo（本地 `http.server` 实测）。http 索引的主机**不在** `trusted-host` 里时，pip 告警 "not a trusted or secure host and is being ignored" 并忽略它（结局是 "from versions: none"）；加上不带端口的 `trusted-host 10.20.16.126` 即可用。不存在的 find-links 位置只告警、不报错。经内部代理 dry-run 时下载的是**整个 wheel**（代理不提供 PEP 658 元数据），经 PyPI 只下 `.metadata` | 附录 A（F66） |
| F67 | **pip 会跟随依赖元数据里的直接 URL 去任意主机**（第 6 版）：包 `oc-evil` 声明 `Requires-Dist: oc-far @ http://127.0.0.1:18766/oc_far-1.0-py3-none-any.whl`；无论 `oc-evil` 来自 find-links 目录还是来自 `127.0.0.1:18765` 上的索引，dry-run 都会去 `:18766` 取 `oc-far`，report 里该项 `is_direct: true`、URL 是那个外来地址。pip 只对来自 `files.pythonhosted.org`（及 TestPyPI）的包禁止这样做（`pip/_internal/req/constructors.py`:455-470）。**所以只比对 pip 配置里的来源不够，还要逐项查 report** | 附录 A（F67） |
| F68 | **`name==version` 钉不住文件**（第 6 版）：dry-run 计划的是 `oc_dep-1.0-py3-none-any.whl`；在 dry-run 与安装之间往 find-links 目录放一个同版本、带 build 号、内容不同的 `oc_dep-1.0-1-py3-none-any.whl`，`--no-deps --only-binary=:all: oc-dep==1.0` 装上的是后者（`import oc_dep` 得到新内容）。**非 dry-run** 的 `pip install --report`（pip ≥ 22.2）记录实际安装的每个文件的 URL，可以与计划逐项比对。另：PyPI 允许给已发布的版本**追加**新文件（新的 build 号或平台标签），但不允许以同一文件名重传（删除后也不行）——这是 PyPI 的公开规则，非本机实测 | 附录 A（F68） |
| F69 | **重定向，以及 pip `trusted-host` 的匹配规则**（第 6 版）：索引页的文件链接被 302 到另一个端口时，pip 跟随重定向、从后者下载，report 记的仍是**重定向前**的链接（`127.0.0.1:18767`，字节实际来自 `:18766`）——对 report 做主机比对看不见重定向。pip 的 `trusted-host` 匹配（`pip/_internal/network/session.py` `is_secure_origin`，:455-510）：主机名不区分大小写、**精确相等**（没有子域名或后缀匹配）；不带端口的条目匹配该主机的**任何端口**，带端口的只匹配该端口；IP 地址按地址比较 | 附录 A（F69）；pip 26.0.1 源码 |
| F70 | **本机 agent 环境里的代理变量带凭据**（第 6 版）：`HTTP(S)_PROXY`、`ALL_PROXY` 形如 `http://<user>:<token>@127.0.0.1:7891`（此处不抄原值）；`NO_PROXY` 含 `10.0.0.0/8`，所以内部代理 `10.20.16.126` 直连、PyPI 走本地代理。§4.5 第 7.3 步的 pip 白名单会把这些变量传给 pip（pip 要靠它们联网）；第 7.10 步的验证 import 若继承同一环境，新装的第三方代码在 import 时就能读到它们 | `env`（只看变量名与形态） |
| F71 | **小白名单环境下的 import 验证**（第 6 版）：以 `OmicsClaw` 为 base 的 overlay，在 `env -i PATH=/usr/bin:/bin HOME=<空临时目录> TMPDIR=<同> LANG=C.UTF-8 PYTHONNOUSERSITE=1` 下 import scanpy、anndata、numba、matplotlib、squidpy 全部成功（4.2 s）；子进程里只有 7 个环境变量（其中 `KMP_*` 两个是被 import 的包自己设的）；pyproj 因缺少 conda 激活时设置的 `PROJ_DATA` 而告警，但仍 import 成功；import 期间写出的 `.cache/`、`.config/` 落在临时 HOME 里，不碰用户真实的家目录。**第 7 版对齐**（审核 m3）：首跑的命令没有带 `LD_LIBRARY_PATH`，而第 7.10 步的白名单里有它；本机它是 `/usr/local/nvidia/lib:/usr/local/nvidia/lib64`，加上后复跑结果相同（5 s，8 个变量，多出的就是 `LD_LIBRARY_PATH`） | 附录 A（F71） |
| F72 | **wheel 文件与装好的 overlay 的体积**（第 6 版，Q28 的代价估计）：附录 A wheelhouse 里 5 个 wheel 共 432 KB，其中 4 个（cnmf、palettable、mygene、biothings_client）装进 overlay 后 site-packages 为 5.3 MB（含 pip 编译的 `.pyc`）。本机 pip 自己的缓存 `~/.cache/pip` 已有 9.4 GB，但 `http-v2` 按 URL 摘要存响应体，不能直接当 find-links 目录用 | `du` |
| F73 | **新代码第一次执行不在验证 import，而在装完后第一个启动的 overlay 解释器**（第 6 版）：造一个带 `oc_pth_hook.pth`（一行 `import os; open(<标记文件>,'w').write(环境变量名)`）的 wheel，用 overlay 的 pip 安装时标记文件**没有**出现；随后在同一 overlay 里跑 `pip check`，标记文件出现，内容含调用方传入的 `PIP_PROXY`。也就是说 §4.5 第 7.8 步的 after `pip check` 就会执行新 wheel 的 `.pth`，比第 7.10 步的验证 import 更早；第 5 版两步都没有规定环境 | 附录 A（F73） |
| F74 | **只用环境变量给 pip 来源**（第 7 版）：`PIP_CONFIG_FILE=/dev/null` 下，`PIP_INDEX_URL=http://10.20.16.126:8081/repository/pypi-proxy/simple` 加 `PIP_TRUSTED_HOST=10.20.16.126:8081`（带端口）即经内部代理解析 six；`PIP_NO_INDEX=1` 加 `PIP_FIND_LINKS="<目录1> <目录2>"` 同时看两个目录。**环境变量的值不会被当作选项解析**：`PIP_INDEX_URL="http://127.0.0.1:9/simple --no-binary :all:"` 整串是一个 URL（"Looking in indexes: http://127.0.0.1:9/simple --no-binary :all:"）；多值变量按空白切成多个**值**——`PIP_EXTRA_INDEX_URL="http://…/simple --no-binary :all:"` 得到三个"索引" `http://…/simple`、`--no-binary`、`:all:`，`PIP_FIND_LINKS="<目录> --no-binary=:all:"` 里的后者被当作一个不存在的位置而忽略。所以值里不许有空白，但即使有也注入不了选项 | 附录 A（F74） |
| F75 | **`--` 之后的 argv 只当需求解析**（第 7 版）：`pip install --dry-run --no-deps --only-binary=:all: -- oc-leaf==1.0 oc-dep==1.0` 正常；`… -- --no-binary=:all: oc-leaf==1.0` 报 "= is not a valid operator"，即 `--no-binary=:all:` 被当成一个（非法的）需求，而不是选项。因此需求可以直接放在命令行，不需要需求文件 | 附录 A（F75） |
| F76 | **report 分辨不出"来源是否给了摘要"**（第 7 版，Q31 的依据）：pip 在链接没带摘要时会自己对下载的文件算 sha256 填进 `download_info`（`pip/_internal/operations/prepare.py`:638-650，注释"Otherwise we compute it from the downloaded file"）；只取元数据的 dry-run 项则只有链接给出的摘要。本机内部代理的 simple 页带 `#sha256=`（`curl …/simple/six/` 可见 `six-1.16.0-py2.py3-none-any.whl#sha256=8abb2f1d…`） | `curl`；pip 26.0.1 源码 |
| F77 | **（审核方实测）pip 配置的值被原样写进需求文件即可注入选项**（B1）：需求文件的每行先经 shlex 切分、再交 optparse 解析，一行里可以有多个选项；`pip/_internal/req/req_file.py`:50-67 的 `SUPPORTED_OPTIONS` 含 `no_binary`、`only_binary`、`index_url` 等。pip.conf 写 `global.index-url='http://127.0.0.1:18801/simple --no-binary :all:'`：第 6 版的检查按 urlsplit 得到已声明的主机、放行并出卡；写进需求文件后这一行变成 `--index-url … --no-binary :all:`，**覆盖了命令行上的 `--only-binary=:all:`**，sdist 被构建、`setup.py` 在带凭据的 pip 环境里执行，report 显示声明主机、`is_direct=False`。一行里两个 `--index-url` 时后者生效。同样的值改用 `PIP_INDEX_URL` 传入则不会注入（F74） | `/tmp/review0061v6`（`http18801.log` 等） |
| F78 | **（审核方实测）检查器解析出的主机 ≠ pip 实际连接的主机**（B2）：urlsplit、pip 所用的 `pip._vendor.urllib3.util.parse_url`、需求文件用的 shlex 对反斜杠、制表符、非 ASCII 的处理各不相同。`https://evil.com\@pypi.org/simple`：urlsplit 得 `pypi.org`，urllib3 得 `evil.com`。端到端：声明 `10.20.16.126:8081`，配置值写 `http://127.0.0.1:18803\@10.20.16.126:8081/…`，检查器与卡片都显示声明主机，pip 实际连的是 `:18803`，装上的字节来自它（`VALUE = 666`）。19 个 URL 里 5 个两种解析的主机不同 | `/tmp/review0061v6`（`evilproxy.log`、`tools/evilindex2.py`） |
| F79 | **（审核方实测）pip 配置里的 `proxy` 能整体替换字节；`PIP_PROXY` 不理会 `NO_PROXY`**（B3、m1）：pip.conf 设 `proxy = http://127.0.0.1:18803`，索引页与 wheel 全由这个代理提供，装上的是被替换的字节，report 的 URL 仍显示声明主机。另：`PIP_PROXY`（即 `--proxy`）对 `NO_PROXY` 范围内的主机同样生效，环境变量 `HTTP_PROXY` 则遵守 `NO_PROXY` | `/tmp/review0061v6`（`tools/evilproxy.py`） |
| F80 | **（审核方实测）去掉 `--require-hashes` 后，pip 默认仍校验索引页给出的 `#sha256=`**（I1）：`pip/_internal/operations/prepare.py`:344-345，不要求哈希时取 `req.hashes(trust_internet=True)`，即链接上的摘要。摘要与字节不符时 pip 拒装；文件链接 302 到另一主机并换字节，同样被 pip 自己的校验拦下（目标主机确实被访问了 1 次）。这是 pip 的默认行为，**不是本工具的门槛**（Q24）：本工具不关掉它，也不以它为依据或前提 | `/tmp/review0061v6`（`tools/redir.py`、`tools/evil3.py`、`redir.log`、`evil3.log`） |
| F81 | **（审核方核对）pip 自己认为安全的来源**（I3）：`pip/_internal/network/session.py`:66-76 的 `SECURE_ORIGINS` 含 https、`localhost`、`127.0.0.0/8`、`::1/128` 与 `file://`；`is_secure_origin`（:481-497）允许 trusted-host 是网段（如 `10.0.0.0/8`）。第 6 版"http 主机必须在 trusted-host 里，否则拒绝"会误拒前者 | pip 26.0.1 源码 |
| F82 | **（审核方实测）小白名单环境不会造成验证误判**：从 94 个 `SKILL.md` 解析出的 64 个 import 名，在继承环境与第 7.10 步的小白名单环境（`env -i PATH LANG LD_LIBRARY_PATH HOME=<临时> TMPDIR=<临时> PYTHONNOUSERSITE=1 PIP_CONFIG_FILE=/dev/null`）下逐个 import，结果一一相同；49 个模块一次导入 14 s；去掉 `LD_LIBRARY_PATH` 后 cupy、rapids_singlecell 仍可导入。第 6 版回复里"白名单可能导致误判回滚"的顾虑由此消除 | `/tmp/review0061v6`（`tools/imp.sh`、`imp_r.sh`、`imp_results.txt`、`imp_r.txt`） |
| F83 | **§4.10 文法的原型**（第 7 版）：用正则加 `ipaddress` 写了一个 40 行的原型，跑 20 个值：审核方 F78 那类分歧值（`https://evil.com\@pypi.org/simple`、`http://127.0.0.1:18803\@10.20.16.126:8081/…`、两个 `@`、制表符、空格、非 ASCII 的 `pypı.org`、`%2F@`、`#@`、`?@`、以 `-` 开头）10 个全部被拒；越界端口与 `ftp://` 被拒；被接受的 8 个（含 `https://PyPI.org./simple`、带 userinfo 与端口的、`[::1]` 与全写 IPv6、`localhost`）经 `urlsplit` 与 pip 的 `urllib3.util.parse_url` 解析出的主机与端口一致，归一化后 `[0:0:0:0:0:0:0:1]` 与 `[::1]` 相同、`PyPI.org.` 成为 `pypi.org` | 附录 A（F83） |
| F84 | **（审核方实测，本版复现）dry-run 会构建依赖元数据中直接 URL 指向的 sdist**：find-links 里的 wheel `oc-near` 声明 `Requires-Dist: oc-far @ http://127.0.0.1:18810/oc_far-1.0.tar.gz`；按第 7 版的形态调用（只用 `PIP_*` 环境变量、`PIP_CONFIG_FILE=/dev/null`、`--` 之后写需求、`--only-binary=:all:`，本版复现时另加 `-I`、`PIP_NO_INPUT=1` 与空的临时 cwd），**dry-run 期间 `setup.py` 就被执行**，看得到 `HTTPS_PROXY`（本版复现时是一个带 `u:tok@` 的假值）与全部 `PIP_*`；report 里该项 `is_direct: true`。`--only-binary` 只约束从索引和 find-links 选候选，不约束直接 URL；第 7.6 步对 `is_direct` 的拒绝发生在这之后，只能挡住安装。pip 不跟随来自 PyPI 的包里的直接 URL（F67），所以只有已配置的来源、或 find-links 指向的目录里的包能触发。审核方注明：他上一轮的实验 2 其实已经测到这一行为，只是漏报 | `/tmp/review0061v6`（`sd/`、`wh_sd/`）；本版复现 `/tmp/exp0061v71`（附录 A） |
| F85 | **（审核方实测）argv 里的 spec 本身也能是直接 URL**：`pip install --dry-run … -- 'oc-far @ http://…/oc_far-1.0.tar.gz'` 同样执行 `setup.py`。第 7 版的 spec 文法只要求"不以 `-` 开头、无控制字符"，放过了它；spec 来自 pyproject 的 extras 与 registry 的 `also`，都是模型能改的仓库文件 | `/tmp/review0061v6` |
| F86 | **（审核方实测，本版复现）cwd 里的同名包会劫持 `python -m`**：cwd 放一个 `pip/__main__.py`，`<overlay>/bin/python -m pip --version` 执行的是它，并读到了带凭据的 `PIP_INDEX_URL`；`python -m venv` 同理（cwd 里的 `venv/__main__.py` 被执行）。加 `-I` 后两者都执行真正的模块；`-I` 下的 overlay 仍能 import base 的 scanpy 1.11.5（`sys.flags.isolated == 1`），即 `-I` 不影响 `--system-site-packages`——它只忽略 `PYTHON*` 环境变量、关 user site、不把 cwd/脚本目录放进 `sys.path`，不关 `site` 本身 | `/tmp/review0061v6`；本版复现 `/tmp/exp0061v71`（附录 A） |
| F87 | **（审核方实测）不带端口的 trusted-host 会让同一主机的 https 也不校验证书**：`pip/_internal/network/session.py` `add_trusted_host`（:441-450）对 `host` 同时挂载 `http://host/`、`https://host/`，不带端口时再挂 `http://host:`、`https://host:` 两个通配前缀；实测 `trusted_hosts=['nexus.corp']` 时 https 的 443 与 8443 都挂上了 `InsecureHTTPAdapter`；带端口写法只影响该端口 | pip 26.0.1 源码；审核方实测 |
| F88 | **（审核方核对）pip 只对索引页与 find-links 页做安全来源检查**：`pip/_internal/index/collector.py`:454、:465 的 `page_validator=self.session.is_secure_origin` 只作用于页面；页面里链接到的文件不查，所以 https 索引可以链接到任意主机上的明文 http 文件。`.meta.json` 的 `transport` 因此必须取**制品 URL** 的 scheme | pip 26.0.1 源码 |
| F89 | **（审核方实测）base 或 overlay 的 site-packages 里的 `.pth`、`sitecustomize` 会在 pip 进程里执行**，并能读到 `PIP_INDEX_URL`；`-I` 不关 `site`，挡不住它们（F86） | `/tmp/review0061v6` |
| F90 | **`.env` 的加载不覆盖进程环境**：`launch/__init__.py`:200 调 `load_env_file(candidate, override=False)`（`common/runtime_env.py`:124 在 `not override and key in os.environ` 时跳过）——进程环境优先。所以 OmicsClaw 配置的实际来源是"启动环境"：flag、启动 shell 的环境（包括 shell rc 里的 `export`，改了在下一次启动生效）与 `.env`；受权限层保护的只有 `.env`（与 `.omicsclaw/`），shell rc 不在其中。这一点对所有 `_Option` 都一样 | 源码 |
| F91 | **§4.10 文法原型的补充**（第 7.1 版）：原型扩到 `file://` 与绝对路径、端口归一与数字主机、spec 文法。结果：`file:///srv/wheels`、`/srv/wheels` 接受，`file://host/srv`、相对路径、含空格的路径拒绝（`file:///srv/../etc` 在原型里被接受——正文补上"拒绝 `.`/`..` 段"）；`:08081` 归一为 `8081`；`0x7f.1`、`2130706433`、`127.1`、`0177.0.0.1` 这类数字主机写法全部拒绝（最后一段是数字或 `0x` 开头的主机只接受规范的点分四段），`1e100.net` 这类普通主机名不受影响。spec 文法接受 `SpaGCN>=1.2.5,<2.0`、`scanpy >= 1.9`（去空白后为 `scanpy>=1.9`）、`scvi-tools[cuda12]>=1.0`、`pkg[a,b] ~= 2.1 , != 2.1.3`、`x===1.0+local`，拒绝 `oc-far @ http://…`、`x@http://…`、带 `;` 标记的、`x --no-binary :all:`、`-e .`、带 `--hash=` 的、`file:///…`；仓库 `pyproject.toml` 的 62 个 spec（全部 extras 与 dependencies）一个不拒 | 附录 A（F91） |
| F92 | **（第 7.2 版实测）命令行的 `--only-binary=:all:` 胜过 pip 配置与环境里的 `no-binary`**：find-links 目录里只有 `ocsd-1.0.tar.gz`。只有 pip.conf 的 `no-binary = :all:` 时，pip 去构建 sdist；同一 pip.conf 加上命令行 `--only-binary=:all:` → `No matching distribution found`；`PIP_NO_BINARY=:all:` 加命令行 `--only-binary=:all:` 同样如此。所以沿用 pip 配置后，"只装 wheel"仍由命令行保证（第 7 版 F77 的注入之所以成立，是因为值被写进了需求文件，而需求文件里的选项排在命令行之后；第 7.2 版不读配置值、不写需求文件） | `/tmp/v72check`（附录 A） |
| F93 | **（第 7.2 版实测）pip 配置里的安装位置类键会把包装到 overlay 之外**：以 `OmicsClaw` 为 base 建 `--without-pip --system-site-packages` overlay，用它的 `python -I -m pip install --no-index --find-links … --no-deps --only-binary=:all: ocsd==1.0`：`[install] target = <dir>` → 装进 `<dir>/ocsd/`；`prefix = <dir>` → 装进 `<dir>/lib/python3.11/site-packages/`（若指向 base 的 prefix，就是改了 base）；`root = <dir>` → 装进 `<dir>/<overlay 路径>/…`；`user = true` → pip 拒绝（"User site-packages are disabled"）。三种情况下 overlay 里都没有包、pip 退出码为 0。`pip config list` 按 `install.user='true'` 这种"节.键"形式列出，键名本身不需要解析 URL。另：overlay 的 pip 读的 site 级配置是 overlay 自己的 `sys.prefix/pip.conf`，**base 前缀下的 `pip.conf` 不生效**，用户级（`~/.pip/pip.conf`、`~/.config/pip/pip.conf`）与全局（`/etc/…`）照常生效 | `/tmp/v72check`（附录 A）；site 级配置路径见 pip 26.0.1 `pip/_internal/configuration.py`:75（`os.path.join(sys.prefix, "pip.conf")`） |

---

## 3. 可行性审计：逐组件处置

| 旧组成部分 | 处置 | 理由（锚点） |
|---|---|---|
| **接缝**：`runner._prepare_skill_run` 里一处决定解释器（F6） | **丢弃** | runner 按 D1 已移除；新框架里 skill 有多条执行路径（agent 的 `bash`、子代理预载正文后用 `bash`、0056 `run_skill`、人手跑），不存在"单一接缝"。§4.1 重新选接缝 |
| **默认开启的静默安装**（F1、F4） | **丢弃** | 与权限层冲突：安装是联网下载并执行第三方代码，新框架对 `bash` 一律 `ASK`（F23、F25）；确定性路径若在 `AUTO` 工具里装包，闸门的 `_run_settled` 会让内部审批自动通过（F25）。旧栈自己在受治理路径上也关掉了它（F7）。新设计缺省只探测（Q7） |
| **依赖集合来源**：`requires:` frontmatter（F2） | **重写（换来源，不换内容）** | D2 删除了 `requires:`，但其内容被逐字搬进了 `## Dependencies`（F20：94/94 相同）。用于**探测**不改契约；用于**安装**改契约，须 Q3 裁定（F20 引 AGENTS.md） |
| **import 名桥接**：读 4 个 registry（F3） | **移植，改读单一文件（第 4 版）** | registry 是名字映射 SSOT（`AGENTS.md`:59-64）；0062 阶段二把四份合并为 `skills/_sdk/deps.py` 的纯字面量 `DEPENDENCIES`，skillenv 用 `ast.literal_eval` 读它、不 import，名字解析顺序与 0062 §3.4 相同（F64、§4.2） |
| **手写分类名单**（F3） | **重写** | 类别直接取 registry 的 `kind` 字段（`pip`/`git`/`r`，0062 §3.4），不再从安装命令字符串推断；"会不会是一次注定失败的大解析"改由 dry-run 的真实结局 + 超时回答（F34、F39） |
| **子进程探针**（F4） | **移植并加固** | 前提在新框架更强：agent 解释器与 `bash` 的 `python` 可能不同（F23、F30）；沙箱里只能在容器内探（F24）。旧实现的"cwd = 脚本目录"是对的，第 1 版丢了它：改为 cwd = skill 目录，并先剔除 `''`/`'.'`（F45）；安装相关的四步统一 `PYTHONNOUSERSITE=1`（F1、F46） |
| **overlay 创建**：`--system-site-packages`、从 base 创建（F5） | **移植，并拒绝 venv 作 base** | 实测成立（F32）；base 本身是 venv 时 overlay 继承的是底层解释器，看不到 base venv 的包（F47），直接拒绝 |
| **uv→stdlib 回退**（F5） | **丢弃 uv** | stdlib `--without-pip` 与 `uv venv` 同速（F32），无额外依赖；`uv pip` 对 overlay 有害（F35） |
| **`--no-deps` 安装**（F5） | **重写为"只补缺钉版本 + 来源控制 + 约束检查"** | 纯 `--no-deps` 漏传递依赖（F33）；带依赖安装会遮蔽 base（F34）；只补缺后的约束问题用装前装后两次 `pip check` 的差集判定、非空即回滚（F49、F60）；第 6 版起不校验哈希（Q24），第 7 版起来源只取自部署的 OmicsClaw 配置、不读 pip 配置（F77–F79），并把实际安装的文件与计划逐项比对（F67、F68） |
| **pip 子进程环境** | **重写** | `PIP_*` 与 pip.conf 能把安装位置改到 overlay 之外（F51），`--isolated` 挡不住全局配置与 `PIP_CONFIG_FILE`（F61）：改为 `PIP_CONFIG_FILE=/dev/null` + 自建环境 + 来源经本工具生成的 `PIP_*` 环境变量传入（第 7 版起不写需求文件，F74、F75）+ 去凭据显示 + 装后核对落盘位置 |
| **key / fingerprint / flock**（F5） | **移植并修正** | key 去掉 agent 进程的 `CONDA_PREFIX`，加入 base 的 mtime 与发行包清单摘要（只作缓存身份，不是安装校验）——base 一变就是新 key，不再原地重建；fingerprint 只作"建成"标记；锁文件移到永不删除的 `<root>/.locks/`，锁内复查（F62，§4.6） |
| **list/remove/clean**（F5） | **暂不做** | 没有调用方也没有 surface（`oc` 只接 surface，`AGENTS.md`:83）；等真要有 surface 时再加。注记里"查找现成 overlay"只需要一个只读的 `find_overlays` |
| **Windows 路径** | **不作为目标** | 新栈 `bash` 只支持 POSIX（F23） |
| **模式环境变量** `OMICSCLAW_ADAPTIVE_ENV`/`_SKIP_ADAPTIVE_ENV`/`_ENV_DIR` | **退役，改为 `_Option` 配置** | 新框架的开关先例是 `_Option` 表（F29）；旧名语义是"默认静默安装"，复用会让旧 `.env` 静默改义（Q14） |
| **`OMICSCLAW_RUN_PYTHON`**（F8） | **退役** | 它服务的 runner 已不存在；`bash` 路径看 PATH 的 `python`，`run_skill` 看 `ensemble_python`（F30） |
| **`environment.py`**（F12） | **不在 0061（第 4 版）** | `core/` 三模块依赖它，删除它造成 F11 的大面积失效；0062 阶段一把 `core/` 搬进 `skills/_sdk/`、删掉 skill 侧剔除，剔除改在框架启动边界做（0062 §3.2、§3.7），不再重建 `environment.py` 或 `child_env.py` |
| **`runtime_source` 与 `SkillRunResult`**（F8） | **丢弃字段，概念改写** | 来源记录落在工具结果、overlay 的 `.meta.json`、会话记录与 0056 的试验记录（§4.9） |
| **Desktop env 端点、`remote` 模型**（F15、F16） | **不移植；删除随 remote 整包裁定** | 所在模块本就不能 import，新 Desktop 只有两个路由（F15）；App 端的调用方是跨仓库残留（F57，§4.8） |
| **autoagent 白名单**（F17） | **不改；建议 0056 删掉拷贝** | autoagent 是只读参考、0057 迁完即删；死变量却经 0056 进入了新代码（F17，Q16） |
| **状态回调 `status_cb`**（F4） | **改写** | 新栈工具用 `report_progress`（0056 §3.3 同用） |
| **旧 Phase 4：conda 子环境自动创建** | **不做** | 超出 pip 叶子范围；沙箱无网络；见 §4.7 |

---

## 4. 设计

### 4.1 接缝在哪里（设计问题 1，Q1）

| 候选 | 做法 | 覆盖 agent `bash` | 覆盖 `run_skill` | 覆盖人手跑 | 与 D1 一致？ | 主要问题 |
|---|---|---|---|---|---|---|
| (a) 改写 `bash` 命令（cellclaw 式） | 在 `bash` 里把 `python` 换成 overlay 解释器、注入 `PATH/VIRTUAL_ENV` | 本机全覆盖 | 否 | 否 | 边缘：`bash` 不再"跑你写的命令" | 审批卡显示的与实际执行的不同；需要从任意 shell 文本里认出 skill 脚本，脆弱；沙箱里宿主 overlay 不可用（§4.6）；一个会话一个 overlay 无法表达两个 skill 的冲突需求 |
| (b) 显式工具 | agent 调工具"为某 skill 准备环境"，工具返回解释器路径或缺失清单 | 覆盖，但依赖 agent 调用并使用返回的解释器 | 否 | 否 | 是（不跑 skill） | 多一个工具；agent 可能忘了用返回的解释器 |
| (c) 挂在 0056 执行器 | `run_skill` 试验前确定性地探测并安装 | 否 | 是 | 否 | 是（`run_skill` 本身是 0056 §0.2 第 2 条所列的例外；0056 仍待 owner 终审） | `run_skill` 是 `AUTO`，内部安装会被闸门自动放行（F25）＝静默安装；benchmark 要求环境固定（0056 §3.13） |
| (d) hooks（`before_execute`） | 解析 `bash` 命令，探测后拒绝/改写/安装 | 部分 | 否 | 否 | 是 | hook 在闸门之内、改写不复核、不能问人（F27）；skill 级依赖过报会误拒 |
| (f) `use_skill` 附注记 | 取 skill 正文时顺带探测，把结果附在工具结果末尾 | 探测覆盖**经 `use_skill` 的路径** | 否 | 否 | 是 | 只探测不安装；子代理预载正文、直接照 `CLAUDE.md` 写命令两条路径看不到（F53） |
| **(e) 组合（推荐）** | 纯库 + (f) 探测 + (b) 安装（显式开启）+ (c) 只记来源、不供给 | 探测覆盖主路径，安装按需 | 只记来源 | 否（非目标，§8） | 是 | 见 §7 风险 |

**推荐 (e)**，理由：

1. **探测放在 `use_skill`**：agent 按 `CLAUDE.md` 通常先 `use_skill` 再跑脚本（F21），这是主路径上最早、最常经过的一步。它**不是唯一路径**（F53）：子代理预载的正文与直接照 `CLAUDE.md` 写的命令看不到注记，这些路径上 agent 只会在运行时遇到 `ImportError`——与今天相同，不更差。注记只改工具**结果**，不改工具**定义**，工具表与系统提示字节不变（G6）。
2. **安装做成显式工具而不是改写 `bash`**：安装是需要人同意的效果，放进一个有自己 policy 的工具；`bash` 保持"跑你写的命令"。agent 拿到**绝对路径的解释器**，之后照常用 `bash` 跑脚本，审批卡上看得到。缺省不挂载（Q7）。
3. **`run_skill` 不供给**：保持 0056 的"执行环境由部署固定"，只经 entry 注入的回调记录环境（§4.12）。
4. **不走 hooks**：安装不能不问人，改写不能不复核（F27）。

本计划不新增任何"跑 skill"的东西；两个接触点（注记与安装工具）都只围绕"解释器与包"。

### 4.2 依赖从哪来（设计问题 2，Q2、Q3）

**集合（用于探测）**：

| 候选 | 粒度 | 覆盖 | 与 D2 | 评价 |
|---|---|---|---|---|
| **(a) 解析 `## Dependencies` 的包名行 + 格式契约测试（推荐）** | skill 级 | 94/94（F20），有漏报（F52） | 一致：仍是 `SKILL.md` 正文 | 内容就是旧 `requires:`；只用于探测时不改契约 |
| (b) registry（`skills/_sdk/deps.py` 的 `DEPENDENCIES`）当集合 | 包级，无 skill→包映射 | 61 键（F64；0062 之前是 4 个域、62 键，F22） | 一致 | 回答不了"这个 skill 要什么"；只适合做名字桥、类别与安装展开 |
| (c) skill 目录旁挂 `env.yaml`（仿 `tuning.yaml`） | 可到方法级 | 需新写 94 份 | 需 owner 例外批准 | 表达力最强，维护成本最高 |
| (d) 运行时 import 探测（AST 扫脚本 / 捕获 `ImportError`） | 脚本级 | 全部 | 一致 | AST 漏延迟 import 与 `_lib` 间接引用；`ImportError` 是事后的 |
| (e) `tuning.yaml` 的 `methods.<m>.requires` | 方法级 | 只限带 `tuning.yaml` 的 skill | 属 0056 schema 变更 | 留给 0059 视需要再提 |

**格式契约**：测试只钉**包名行**——`## Dependencies` 段内恰好一行匹配
``(`[A-Za-z0-9][A-Za-z0-9._-]*`)(, `…`)*``，段内其他散文不钉（今天那句 "They are not installed for you —
check before a long run." 之后若要改写，不必动 94 个文件的测试）。不符时抛 `DependencyFormatError`，
信息写明文件与行；名字只接受这个字符集，这也是拼 shell 命令前的输入校验。

**registry 从哪读**（第 4 版，D6）：`<skills 根>/_sdk/deps.py`，`<skills 根>` 是 `use_skill` 所用索引的
`SkillIndex.root`（`omicsclaw/skills/loader.py` `load_skills`），由 entry 传给 skillenv。读取方式照 0062 §3.9：`ast.parse`
该文件，找到模块级赋值 `DEPENDENCIES`（带注解的 `AnnAssign`，也接受普通 `Assign`），`ast.literal_eval(node.value)`。
**skillenv 不 import `skills` 或其任何子模块**：skill 与框架零代码耦合（0062 D3），框架不 import `skills/_sdk`，只读这一份
文件契约；0062 的守卫 B4（`omicsclaw/**` 不得 import `skills`）同样约束 skillenv。读出后校验契约（与 0062 用例 22 的字段约束
一致，但由 skillenv 自己的测试钉住，因为这是 0061 这一侧的读者）：值必为 dict，必有 `module`/`kind`/`install`/`description`，
可选字段 ⊆ {`also`, `alt_env`}，`kind ∈ {"pip","git","r"}`，`also` 是字符串列表，PEP 503 规范化后键唯一，`module` 全表唯一，
且没有名字既是某键的规范化形式又是另一条目的 `module`（与 0062 §3.4 的歧义禁令相同）。任何一条不满足、
文件不存在、没有 `DEPENDENCIES`、或值不是字面量（例如 `DependencyInfo(...)` 调用、lambda）→ `RegistryFormatError`，信息写明
文件与行。**不设过渡读取器**：不读 4 份旧 `_lib/dependency_manager.py`（0062 阶段二把它们删掉，写一个只活几周的读取器是
浪费），因此 P1 合入以 0062 阶段二为前置（Q19）。

**`skills_dir` 可配置**（`entry/config.py` `AppConfig.skills_root`，部署可用 `skills_dir` 指向别的目录）：自定义目录下若没有
`_sdk/deps.py`（例如只放了几个自写 skill 的目录），按"文件不存在"处理，报错信息写明原因——"`<skills_dir>/_sdk/deps.py` not
found: the configured skills_dir is not an OmicsClaw skills tree with `_sdk/`; install_skill_deps needs that registry"。

`RegistryFormatError` 的后果按模式区分：`skill_env=probe` 时 entry 记一条 warning，注记照常生成，只是所有名字都走回落规则，
注记首行写"dependency registry unreadable: <原因>"（`use_skill` 不能因此失败）；`skill_env=install` 时**拒绝启动**
（`AppConfigError`）——没有 `kind` 就分不出 git 类，安装白名单也展不开。

**名字解析**（声明名或调用名 → registry 条目），顺序按 0062 §3.4 `_resolve`：①键精确匹配 → ②PEP 503 规范化后匹配键
（`spatialde` → `SpatialDE`）→ ③按 `module` 精确反查（`scvi` → `scvi-tools`、`tangram` → `tangram-sc`、`paste` → `paste-bio`）
→ ④回落。①②③与 0062 完全相同；**④ 在 0061 这一侧用自己的 import 名推导**：`kind="pip"`，import 名先查一张两项的小表
（`PyYAML→yaml`、`scikit-learn→sklearn`），否则 `-` 换 `_`。0062 的回落④把 `module` 设为名字本身，对 `PyYAML`、
`scikit-learn` 会给出错误的 import 名（F64）；这一差异只影响不在 registry 里的名字，而今天这样的声明名恰好 16 个（F64），
**由测试钉成冻结表**（用例 6）：新增声明名若只能靠回落解析，测试即红，要么把它补进 `_sdk/deps.py`，要么加进冻结表（附理由）
——与 0062 对调用名"回落集合钉为冻结空表"同一手法（Q20）。

**类别**：直接取条目的 `kind`，回落名一律 `pip`。**不再从 `install` 字符串推断类别**（第 3 版的"含 `git+` → `git`、以
`Rscript` 开头 → `non-pip`"作废）。第 3 版的 `non-pip` 类改名为 `r`，含义收窄为"R 包"；conda/CLI 本不在 registry 里。
- `pip`：探针对 `module` 做 `find_spec`；可装。
- `git`：探针同上；缺失时注记给出条目的 `install` 原文（完整命令），`install_skill_deps` 不装。有 `alt_env`（今天只有
  `pybanksy` → `omicsclaw_banksy`）时注记加一句"or the conda env `<alt_env>`"；**探针不查 conda 环境**（那要起 conda 子进程，
  且属于 skill 运行期自己的回落逻辑，0062 §3.4 `is_available`）。
- `r`：`module` 是 R 包名，**探针不对它做 `find_spec`**（旧实现正是这么把 R 包误判为永远缺失的，0062 F27）；注记写
  "R package, not checked here; the script's `validate_r_environment` reports it"。今天没有 skill 在 `## Dependencies` 里声明
  `r` 类名字（F64），此分支只为契约完整。

registry 的 `module` 可能是"代表模块"（`SpatialDE→NaiveDE`）——探针以它为准，注记里写出实际探的 import 名。**版本约束**：
仓库根有 `pyproject.toml` 时从 `[project.optional-dependencies]` 取同名条目（规范化匹配），否则用裸名；`also` 里的包同样处理。

**安装来源与漏报（Q3）**：把 `## Dependencies` 用作安装白名单会推翻 AGENTS.md 的"Nothing installs from the
section"（D2），须 owner 拍板。推荐方案（第 3 版改为 b，第 4 版不变）：

- **请求白名单 = 该 skill 的 `## Dependencies` 里的名字，仅此而已**。`packages` 里的每个名字（规范化后）必须是该 skill 的
  声明名；解析到 registry 条目后，**实际安装的发行包 = `[键, *also]`**（0062 §3.9：包名取结构化字段，不从 `install` 字符串
  里解析）；回落名就是它自己。`git`/`r` 类即使在白名单里也不装。第 2 版推荐的"并集 registry 的 pip 类键"会把按 skill 计算
  的白名单扩大 4–5 倍（F59，这一点与 registry 是否合并无关）；键名≠PyPI 名的问题已由 0062 阶段二消除（F59 第 4 版注）。
- **漏报靠补声明与逐 skill 一致性测试解决**：P1 加 `test_skill_requires_are_declared.py`——对每个 skill，收集主脚本与它
  import 的 `skills.<domain>._lib.<模块>` 里对 `skills._sdk.deps` 依赖 API 的字符串调用名（**按 0062 F29 的 AST 规则**：
  `require`/`is_available`/`install_hint`/`get_dependency` 调用、经 `deps` 模块别名的属性调用、以及从 `skills._sdk.deps` import
  的 `get`），按上面的①②③解析后，条目的键必须出现在**该 skill 自己**的 `## Dependencies` 里（F58）。
  `skills/singlecell/_lib/preflight.py` 这类"按方法集中预检、被所有脚本 import"的共享模块列入具名排除表（附理由）；模块粒度的其他
  误报进具名例外表，每条写明为什么该 skill 用不到。0062 之前的扫描报 8 个 skill、9 处（F58），P1 实施时按阶段二后的形式复跑；
  P0b 逐条人工确认后补声明（`spatial-domains`→cellcharter、`spatial-integrate`→scanorama、`sc-clustering`→louvain、
  `sc-integrate-cluster`→scvi-tools 四处可直接确认；scrublet 四处经 `_lib/qc.py`，确认后补或进例外表）。
- AGENTS.md 那句改写为"`install_skill_deps` 只在部署开启且经审批时，按请求从此段安装到 overlay"（P2 文档；0062 阶段二
  已先把同一段的 registry 位置改为 `skills/_sdk/deps.py`）。
- 审核方另给出一个折中（列入 Q3 选项 a′）：若坚持并集，只并入代码里被依赖 API 引用过的名字（0062 F29 数出 32 个），PyPI
  名取 registry 的 `[键, *also]`。第 4 版注：a′ 原先"PyPI 名取自 `install_cmd`"的顾虑已随 0062 的键规则消失。

**已知局限**：skill 级依赖会过报（`spatial-domains` 声明了 pybanksy 与 STAGATE-pyG，leiden 并不需要）。注记明写
"用不到这些包的方法不受影响"，不按方法下结论（R1）。

### 4.3 探测

**探哪个解释器**：`bash` 实际会用的那个 `python`，不是 agent 进程的 `sys.executable`（F23、F30）。Desktop 本机
模式下 App 已把所选解释器的 bin 前置到 PATH，二者一致（F57）。探针**走与 `bash` 相同的执行位置**：

- 本机（沙箱关闭或降级）：`bash -c '<探针命令>'`，继承 agent 进程环境，`stdin=DEVNULL`，新会话、超时杀整组
  （复用 `tools.builtin.bash.spawn_group_leader`）。
- 沙箱运行中：`BashEnvironment.run_bash(<探针命令>, <cwd>, timeout)`。

**cwd 与 `sys.path`**（F45）：**skill 目录在执行位置存在时**以它为 cwd（与旧实现、与 `python <skill 目录>/<脚本>.py` 的
真实运行一致；沙箱里该目录经 0056 的只读挂载可见，F24）；**不存在时**（例如 `sandbox_code_in_image=true`，容器里没有宿主
路径，`entry/config.py`:425、:548-549）以工作区为 cwd。实现上 runner 的 cwd 一律给工作区，命令以
`cd <skill 目录> 2>/dev/null || true;` 开头，避免 `--workdir` 指向不存在的目录而整体失败。固定代码的**第一句**是
`import sys; sys.path[:] = [p for p in sys.path if p not in ("", ".")]`，之后才 import 其他模块；探测前**仅当 skill 目录
存在时**才把它的绝对路径插到 `sys.path[0]`（模拟 `python <脚本>` 的 `sys.path[0]`）。这样工作区里的 `json.py` 不会被执行，
工作区根目录下的同名目录也不会被当成命名空间包。

**探针命令**（纯标准库，语法兼容 Python 3.8，`-B` 不写字节码）：

```
python -B -c '<固定代码>' '<JSON: {"imports": [...], "dists": [...], "skill_dir": "..."}>'
```

对每个 import 名做 `importlib.util.find_spec`（抛异常视为存在，照旧，F4），对找到的记录其 `origin` 是否位于
`site.getusersitepackages()` 之下；对每个发行包名取 `importlib.metadata.version`（取不到记 `null`）。输出一行 JSON：
`{"executable", "version", "prefix", "base_prefix", "user_site_enabled", "missing", "from_user_site", "versions"}`。
参数经 `shlex.quote`；名字已在 §4.2 校验。

```python
@dataclass(frozen=True, slots=True)
class ProbeResult:
    executable: str
    version: str
    prefix: str
    base_prefix: str
    missing: tuple[str, ...]               # import 名
    from_user_site: tuple[str, ...]        # 找到了、但来自 user site 的 import 名
    versions: Mapping[str, str | None]     # 发行包名 → 版本

class ProbeRunner(Protocol):
    location: str                          # "local" | "sandbox"
    async def run(self, command: str, *, cwd: str, timeout: float,
                  env: Mapping[str, str] | None = None) -> tuple[int, str]: ...

def probe_command(imports: Sequence[str], dists: Sequence[str], skill_dir: str) -> str
def probe_argv(python: str, imports: Sequence[str], dists: Sequence[str], skill_dir: str) -> list[str]
                                                     # [python, "-B", "-c", <固定代码>, <JSON>]，不经 shell（第 5 版，供 executor.capture）
def parse_probe(output: str) -> ProbeResult          # 格式不符抛 ProbeError
```

**两种环境**：`use_skill` 注记的探针**继承**环境（反映 agent 实际会怎么跑），把来自 user site 的包单独标出；
`install_skill_deps` 的探针、base 发行包清单、dry-run、验证**四步一律 `PYTHONNOUSERSITE=1`**，与它给出的建议命令
一致（F1 的"用最终环境探测"，F46）。沙箱 runner 的 `env` 以 `env K=V …` 前缀实现（`run_bash` 无 env 参数，F24）。

超时 10 s（本机实测 0.05 s，F37）。非零退出、超时、输出不是 JSON → "环境检查不可用：<原因>"，**不抛到
`use_skill` 之外**。不缓存。

### 4.4 `use_skill` 注记（P1）

`use_skill_tool(index, *, locate=True, annotate=None)`：新增可选参数
`annotate: Callable[[Skill, str], Awaitable[str]] | None`，第二个参数是**已读出的正文**（避免再读一次文件、也避免两次
读取之间的不一致）。为 `None` 时行为与今天逐字节相同；否则在 "Skill directory" 之后追加返回文本。
`omicsclaw/skills` 不 import `skillenv`（回调由 entry 构造），工具定义不变。

**何时不附**：`skill_env=off`；`permission_mode=read-only`（`bash` 一律被拒，注记用不上，而且沙箱里 `run_bash` 会在
`.omicsclaw/sandbox` 下写文件，F24、F54）；`skills_index=off`（`use_skill` 不挂）。

注记示例（本机，英文是产品文字）：

```
---
Environment check (the `python` bash runs here: /opt/conda/envs/OmicsClaw/bin/python, Python 3.11.15)
- 14 of 16 packages under "## Dependencies" are importable.
- Missing, git-only (install_skill_deps cannot install these): pybanksy (import banksy) — pip install git+https://github.com/prabhakarlab/Banksy_py.git …; STAGATE-pyG (import STAGATE_pyG) — pip install git+https://github.com/RucDongLab/STAGATE_pyG.git …
- Methods that do not use a missing package are unaffected.
```

git 类缺项后面的命令是 registry 条目 `install` 字段的原文；有 `alt_env` 时加"or the conda env `<alt_env>`"；`r` 类只写
"R package, not checked here"（§4.2）；registry 不可读时首行写"dependency registry unreadable: <原因>"。
其余变体：有 pip 类缺项且安装工具已挂载时加一行 "install_skill_deps can add the ones your method needs to an
isolated overlay; the base environment is never changed."；**本机模式下**，若已有覆盖某些缺项的 overlay，写出它的解释器
（`find_overlays` 只读 `.meta.json` 与 fingerprint 文件：先按 base 的路径、版本、prefix、mtime 筛；只有筛出候选时才再跑一次
约 0.3 s 的小探针取 base 发行包清单摘要，与 key 精确匹配；不联网。沙箱运行中不调用——宿主上的 overlay 在容器里不可用）；有来自 user site 的包时加一行 "found only in the user site (~/.local); an overlay command with
PYTHONNOUSERSITE=1 will not see it"。**沙箱运行中**措辞按 `SandboxBinding.isolates_network`（F24）：无网 → "This
runs inside the sandbox image `<image>`, which has no network: missing packages have to be added to the image
by whoever maintains it."；有网 → "The sandbox can reach network `<name>`; install_skill_deps is not available
inside the sandbox."。注记总长上限 1500 字符，超出的缺项只列名。

### 4.5 安装工具 `install_skill_deps` 与审批（P2，设计问题 4，Q5–Q8）

**只在 `skill_env=install`、沙箱关闭（降级按 Q4）时挂载；缺省不挂载；Desktop 上显式设 `install` 会拒绝启动（Q6）。**

**schema**（`skill` 是第一个必填字符串，规则文件可写 `install_skill_deps(spatial-domains)`）：

```json
{
  "type": "object",
  "properties": {
    "skill":    {"type": "string", "description": "skill name exactly as in the skill index"},
    "packages": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                 "description": "the packages the method you are about to run needs, by the names the environment check listed"}
  },
  "required": ["skill", "packages"],
  "additionalProperties": false
}
```

`packages` **必填**（Q8）：不存在"装全部缺项"的调用，`torch` 这类 GB 级包只有在模型为所选方法点名时才会进入计划。
工具描述写明"只装你要运行的方法需要的包"。

**policy**（声明而非默认）：`risk_level=HIGH`、`approval_mode=ASK`、`prompts_for_itself=True`、`read_only=False`、
`concurrency_safe=False`、`writes_workspace=False`、`writes_config=False`、`touches_network=True`、
`allowed_in_background=False`、`tags={"skills","environment","network"}`。

**一次调用**（询问之前只读本地、不联网、不写文件；询问之后的一切都在同一把锁与同一个 `try/finally` 里）：

1. **校验**（`ToolArgumentError`）：skill 不在索引；`## Dependencies` 不可解析；`packages` 含白名单（Q3 推荐 b：该 skill
   的 `## Dependencies`）之外的名字。通过后把每个名字按 §4.2 解析并展开为要装的发行包 `[键, *also]`（回落名即自身）；
   卡片与 `.meta.json` 的 `requested_specs` 记展开后的列表。
2. **本机探测**（§4.3，`PYTHONNOUSERSITE=1`，经可注入的 `ProbeRunner`）→ base 身份（真实路径、版本、`prefix`、
   `base_prefix`、解释器 mtime）、缺项，以及 **base 发行包清单与其摘要**（只取 base 自己的 site-packages 目录，见 §4.6；
   摘要只进 key，不参与安装校验）。
   **`prefix != base_prefix`（base 本身是 venv）→ 拒绝**（F47）。请求的包里 `git`/`r` 类（按 registry 的 `kind`）→ 只给提示；已存在 → 跳过。
   没有要装的 → 直接返回报告，**不问人**。
3. **求 key**：`sha256(base 真实路径, 版本, prefix, mtime, base 清单摘要, sys.platform, machine, 排序后的请求 specs)[:16]`。
   **base 的任何变化都得到新 key**；已建成的 overlay 永不原地修改、永不被本工具删除（§4.6）。第 6 版不变：key 是缓存身份，
   只回答"这个 overlay 能不能复用"，与"安装不校验哈希"（Q24）是两回事。
4. **快速复用**：`<root>/<key>/.venv` 有 fingerprint → 返回解释器路径，**不问人、不联网**（锁内会再查一次，见第 7 步）。
   （第 6 版在这里加的"复用前核对来源仍被声明、否则拒绝"已在第 7 版删除，审核 I5：已写 fingerprint 的目录不可变，拒绝只会留下
   一个要人工删除的死 key；而直接用那个解释器跑脚本本来就不经过本工具。）
5. **来源与传输参数：沿用本机 pip 配置**（**第 7.2 版重写**，D8、Q34）：本工具**不决定、不解析、不核对**包从哪来——pip 子进程
   按它自己的规则读用户级与全局 pip 配置（`~/.pip/pip.conf`、`~/.config/pip/pip.conf`、`/etc/…`）以及 pip 环境里的 `PIP_*`，
   就像用户在终端里敲 `pip install`；代理、证书、trusted-host 同理。本工具在这一步什么也不做：不跑 `pip config list`、不设
   `PIP_CONFIG_FILE=/dev/null`、不设 `PIP_INDEX_URL` 等变量、不写需求文件。卡片如实写"按本机 pip 配置安装，来源未经核对"（第 6 步）。
   需要知道的两点：①overlay 的 pip 读的 site 级配置是 overlay 自己的 `sys.prefix/pip.conf`，**base 前缀下的 `pip.conf` 不生效**
   （F93）——依赖它的部署要把设置移到用户级配置；②pip 配置不受权限层保护，模型经 `bash` 就能改（第 6 版审核 B1–B3 的前提），
   第 7.2 版接受这一点：它与模型直接 `bash pip install --index-url <任意地址>` 是同一个风险面（R5、R30）。第 7.2 版保留的只有与来源
   无关的两条：命令行 `--only-binary=:all:` 胜过配置里的 `no-binary`（F92），以及第 7.3 步的安装位置守卫（F93）。
   第 7、7.1 版这一步的原文（只取 OmicsClaw 配置、换算成 `PIP_*`、自动生成 trusted-host、代理的两种情形）已删除，见 §10 第 7.2 版。
6. **审批**（`require_approval`，在任何联网与写文件之前；时机与内容的取舍见 Q27）：卡片写明（第 7.2 版重写，D8）
   ```
   install into an isolated overlay environment (the base environment is not changed):
     SpaGCN>=1.2.5,<2.0
   for skill spatial-domains, wheels only, plus whatever missing dependencies it needs;
   packages the base environment already has are kept as they are.
   packages come from this machine's pip configuration, the same as running `pip install` yourself;
   OmicsClaw does not check where that points (index, proxy, certificates).
   exact versions are resolved after you approve; the result lists every wheel installed and where it came from.
   a package can name a dependency by direct URL; pip may run that dependency's build script while
   resolving, before this tool refuses to install it.
   overlay: ~/.cache/omicsclaw/envs/3f2a…/.venv  (base: /opt/conda/envs/OmicsClaw/bin/python 3.11.15)
   ```
   第 7.2 版删去第 7、7.1 版卡片上的来源清单、`[PLAINTEXT]` 首行告警、代理一行与 "files may be served from hosts …"：本工具不再解析
   pip 配置，写出的来源可能与 pip 实际用的不一致（第 6 版审核 B2、B3 正是这种"卡片说假话"），不如如实写"未经核对"。明文与否改在
   **结果**里逐项给出：安装 report 里每个制品的 URL 是事实，`transport` 取制品 URL 的 scheme，`http` 的项标 `plaintext`（F88）。
   "a package can name a dependency by direct URL …" 两行对应 Q33。第 5 版的 "hash-checked" 删除（Q24）。结果与日志里的 URL 一律去掉
   userinfo 再显示（`https://user:token@host/…` → `https://***@host/…`）。`reason_shows_call=False`。
7. **安装**（整段在 `pause_tool_timeout()` 内，自设上限 `skill_env_install_timeout_s`，默认 1800 s；`report_progress` 报阶段）：
   1. **加锁**：`<root>/.locks/<key>.lock`（`fcntl.flock`，300 s；锁文件永不删除）。**锁内复查**：已有 fingerprint →
      直接复用、不装；`<root>/<key>/` 存在但**没有** fingerprint → 那是被 SIGKILL、OOM 或宿主崩溃留下的半成品（锁保证此刻
      没有别人在建它），先删除再建。
   2. **建 overlay**：`python -m venv --without-pip --system-site-packages`；base 无 pip 时改用带 ensurepip 的 stdlib venv。
   3. **pip 子进程的环境**（第 7.2 版重写，D8）：小白名单 `PATH HOME LANG LC_* TMPDIR XDG_CACHE_HOME XDG_CONFIG_HOME SSL_CERT_FILE
      REQUESTS_CA_BUNDLE HTTP(S)_PROXY NO_PROXY ALL_PROXY（含小写）` + agent 进程环境里的全部 `PIP_*`（与用户在终端里 `pip install`
      看到的一样；`HOME`/`XDG_CONFIG_HOME` 让 pip 找到用户级配置与 `~/.netrc`）+ `PYTHONNOUSERSITE=1` + `PIP_NO_INPUT=1` 与
      `PIP_DISABLE_PIP_VERSION_CHECK=1`（第 7.1 版：遇到 401 不停下来等输入，也不去查 pip 自己的新版本），`stdin=DEVNULL`；**不设**
      `PIP_CONFIG_FILE=/dev/null`，**不写需求文件**。白名单之外的变量（如 `LLM_API_KEY`、`OMICSCLAW_*`）不带。
      **"只装 wheel"仍成立**（F92）：`--only-binary=:all:` 在命令行上，胜过 pip 配置与 `PIP_NO_BINARY` 里的 `no-binary`；第 7 版 F77 的
      注入需要把配置值写进需求文件，第 7.2 版不读配置值、不写需求文件。**但它只约束从索引与 find-links 选候选**（第 7.1 版更正）：
      依赖元数据或 argv 里以直接 URL 指向的 sdist 不受它约束，pip 在解析期间就会构建它、执行其 `setup.py`（F84、F85）——argv 这一路由下面
      的 spec 文法堵住，依赖元数据这一路见第 7.6 步与 Q33。
      **安装位置守卫**（第 7.2 版新增，F93）：沿用 pip 配置后，配置或环境里的 `target`、`prefix`、`root` 会把包装到 overlay 之外——
      `prefix` 指向 base 的前缀就是改了 base，而第 7.9 步的 `RECORD` 核对发现时 base 已经被改。所以在第 7.2 步建好 overlay 之后、
      第 7.4 步之前，用 overlay 的解释器在上面的 pip 环境里跑一次 `<overlay>/bin/python -I -m pip config list`（cwd 为空临时目录；
      这一次另外强制 `PIP_QUIET=0`、`PIP_GLOBAL=0`、`PIP_SITE=0`、`PIP_USER=0`，并去掉这四个变量的其他写法——配置里的 `quiet` 会让
      列表什么都不输出，`global`/`site`/`user` 会让它只列一个文件，而环境变量优先于任何配置文件；这四个强制值回显的 `:env:` 行不计）：
      任何键的最后一段（`.` 之后）按 pip 的规则规范化（小写、`_` 换 `-`、去掉开头的 `--`）后是 `target`、`prefix`、`root`、`user`、
      `src`、`python`，或 pip 环境里有规范化后同名的 `PIP_*` 变量（如 `PIP_TARGET`、`PIP___PREFIX`、`PIP_PYTHON`）→ 拒绝，写明是哪个文件或变量的哪一项、如何移除，走第 8 步回滚。**只看键名、不解析值**，不存在第 6 版 B2 那类
      URL 解析分歧。它挡不住的（pip 以后新增的同类键、`sitecustomize` 改 pip 行为）由第 7.9 步的 `RECORD` 落盘核对兜底，R19。需求一律放在 argv 的 `--` 之后（F75）：dry-run 放请求的 specs，安装放钉版本的
      `name==ver`。每一项先按文法校验（第 7.1 版收紧，F91）——**spec 只许"名字 + 可选 extras + 可选版本约束"**：名字
      `[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?`，extras 是方括号里逗号分隔的名字，版本约束是逗号分隔的若干条
      `(~=|===|==|!=|<=|>=|<|>)` 加版本（`[A-Za-z0-9.*+!_-]`）；运算符与逗号两侧可有空白，校验后去掉全部空白再上命令行；**`@`、`;`
      （环境标记）、`:`、`/`、`\`、URL、控制字符、以 `-` 开头、名字之后跟任何不是运算符的东西（如 `x --no-binary`）一律拒绝**。spec 来自
      pyproject 的 extras 与 registry 的 `also`，都是模型能改的仓库文件，所以拒绝时报错写明是哪个文件的哪一项。钉版本的版本号只许
      PEP 440 的字符 `[A-Za-z0-9.!+_-]`、不以 `-` 开头（名字与版本取自 pip 的 report，同样校验，不合即失败）。命令行上只有选项、包名与
      版本，没有 URL 与凭据。
      **子进程的启动方式**（第 7.1 版，F86）：审批之后本工具起的每个子进程——第 7.2 步建 overlay（`python -m venv`）、第 7.4–7.8 步的
      pip、第 7.10 步的验证——**cwd 一律是一个新建的空临时目录**，解释器一律带 **`-I`**。二者各自都能挡住 cwd 里的 `pip/`、`venv/`
      劫持 `python -m`；两者都做是纵深防御：空临时目录保证 cwd 下没有任何东西可被拾取，`-I` 让解释器根本不把 cwd 放进 `sys.path`，
      并且忽略 `PYTHONPATH`——指向别处的 `PYTHONPATH` 同样能劫持 `-m pip`，临时 cwd 挡不住它（子进程环境本来就不带 `PYTHONPATH`）。`-I`
      等于 `-E -s` 加上不把 cwd/脚本目录放进 `sys.path`：它忽略 `PYTHONPATH` 等 `PYTHON*` 变量（正是想要的）、关掉 user site
      （`PYTHONNOUSERSITE=1` 因此变成冗余，保留无害）、**不关 `site`**，所以 overlay 的 `--system-site-packages` 照常可见 base 的包
      （F86 实测）。`-I` 挡不住 base 或 overlay 的 site-packages 里的 `.pth` 与 `sitecustomize`（F89），那归 R26。探针（第 2 步）属 P1
      的设计，不改。
   4. **before**：在空 overlay 里跑一次 `pip check`，记下违例行集合（这就是 base 已有的违例，F49、F60）。这一次与第 8 步的
      after 用**同一个环境**：第 10 步的无凭据环境，另加 `PIP_CONFIG_FILE=/dev/null`。差集只有在前后条件相同时才有意义，pip 配置里的
      `quiet`、`python` 等选项因此都无法让两次结果不一致；`pip check` 只读元数据、不联网，此时 overlay 里也还没有新代码。
   5. **dry-run**：`--dry-run --only-binary=:all: --report`，解析上限 300 s。
   6. **只补缺与制品核对**（§4.6）：report 里每个要装的项都必须是普通制品——`is_direct` 为假（依赖元数据里的直接 URL 会被 pip
      跟随到任意主机，F67）且有 `archive_info`（不是 VCS 或本地目录）；任一项不满足 → 失败，写明是哪个包、哪个 URL（去 userinfo）。
      **不比对制品 URL 的主机**（第 7.2 版起没有"声明的来源"可比，Q32 作废）：非直接 URL 的制品都是 pip 配置里某个来源给出的链接，
      链接或重定向到哪个主机（PyPI 指向 `files.pythonhosted.org`，F66、F69）不在本工具的判断之内。此时 pip 已经下载过这些制品的元数据或整个文件——
      经不提供 PEP 658 元数据的代理（如本机内部代理）时，dry-run 下载的就是**整个 wheel**（F66，审核 m4）。对 wheel 而言，拒绝发生在
      安装之前、代码执行之前；**对直接 URL 指向的 sdist 则不然**（第 7.1 版更正，F84）：pip 在第 7.5 步解析时就已经构建了它、执行了
      它的 `setup.py`，执行环境是第 7.3 步的 pip 环境（含代理变量与来源凭据）、cwd 是临时目录；这里的拒绝只能挡住安装。能触发的是
      pip 配置里任一来源（索引、额外索引、find-links）提供的包（PyPI 来的包不行，F67）；第 7.2 版起 pip 配置可被模型经 `bash` 改写，
      所以触发面等同于"模型能让 pip 指向哪里"——与模型直接 `bash pip install` 同一风险面。处置见 Q33（推荐作为剩余风险接受，R29）。第 5 版的
      "report 无 sha256 即失败"删除（Q24）。
   7. **安装**：`pip install --no-deps --only-binary=:all: --report <临时目录>/installed.json -- name==ver …`（F75）。装完把安装 report
      与第 6 步的计划逐项比对：（规范化名、版本、wheel 文件名）必须一一相等，否则失败回滚——`name==ver` 钉不住文件，两步之间同版本
      新增的 wheel（带 build 号或更具体的平台标签）会被选中（F68）。结果与 `.meta.json` 里的文件名和来源都取自这份安装 report。
      第 5 版的 `--hash=sha256:…` 与 `--require-hashes` 删除（Q24）。另：pip 默认仍会校验索引页链接上给出的 `#sha256=`（F80）——
      这是 pip 的现成行为，本工具**不关掉它，也不以它为依据或前提**，结果与 `.meta.json` 也不记录它（Q31）。
   8. **约束检查**：再跑 `pip check`，**after − before 的差集**非空即失败（F60：base 包依赖了本次新装包、但版本不满足的情况，
      违例主语是 base 包，只看主语会漏掉）。这一次 `pip check` 用下面第 10 步的**无凭据环境**（另加 `PIP_CONFIG_FILE=/dev/null`；
      `pip check` 只读元数据、不联网）：它是装完之后第一个在 overlay 里启动的解释器，新 wheel 带的 `.pth` 文件此时就会执行（F73）。
   9. **落盘与名字核对**（只读文件，**在第 8 步的 after `pip check` 之前执行**：否则守卫被绕过、`prefix` 指向 base 时，会先以约束
      违例失败、结果误报"未改动"；遮蔽 base 的新模块——如顶层 `pip` 包——也会在 `python -m pip check` 里先被执行。越界时结果写明
      文件可能已写到 overlay 之外）：新装发行包 `RECORD` 里每个路径都解析到 overlay 之内；从 `RECORD` 求出顶层名（去掉 `*.dist-info`、
      `*.data`、`../`），与 base 可 import 的顶层名对照——新装的是模块或常规包（有 `__init__.py`）且 base 已有同名者即遮蔽，
      失败；只是命名空间目录（无 `__init__.py`，如 palettable 的 `build/`、`docs/`、`scripts/`、`test/`，F63）则只报告。`RECORD`
      里新装的 `.pth` 文件逐个列在结果里（只报告：不少正常的包也带 `.pth`）。
   10. **验证**：cwd 为空临时目录、剔除 `''`，在 overlay 里真正 `import` 该 skill 声明的**全部** import 名，限时 120 s；本次请求
       的包必须成功，其余只记录。新装的第三方代码在这里被 import 执行（`.pth` 在第 8 步就已执行，F73），所以**安装之后在 overlay
       里起的子进程（第 8 步与本步）都用本工具自建的无凭据环境**（第 6 版）：只有 `PATH`、`LANG`、`LC_*`、`LD_LIBRARY_PATH` 取自
       agent 环境；`HOME` 与 `TMPDIR` 都指向一个新建的空临时目录（import 期间写出的缓存与配置落在那里，F71）；另设
       `PYTHONNOUSERSITE=1`。**不带**代理变量、`SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE`、任何 `PIP_*`、第 7.3 步 pip 环境里的凭据，
       也不带 agent 环境里的其他任何变量（本机的代理变量就含凭据，F70）。`stdin=DEVNULL`，以 `spawn_group_leader` 启动，超时杀整组；
       临时目录在 `finally` 里删除。它挡住的只是"经环境变量拿到凭据"，挡不住按绝对路径读文件或联网（R6）；conda 激活脚本设置的
       变量（如 `PROJ_DATA`）也不在其中，个别包会因此告警（F71）；审核方实测这不会造成误判（F82）。解释器同样带 `-I`（第 7.3 步
       "子进程的启动方式"）。第 7.5–7.7 步（dry-run、安装）仍用第 7.3 步的 pip 环境——那时 overlay 里还没有新装的代码
       （安装进程本身不执行新 wheel 的 `.pth`，F73）；例外是 dry-run 期间被构建的直接 URL sdist（F84，第 7.6 步、Q33）。第 7.4 步的
       before `pip check` 与第 8 步一样用本环境（另加 `PIP_CONFIG_FILE=/dev/null`）。
   11. 写 `.meta.json`，**最后**写 fingerprint（"完整"标记）。
8. **失败与取消**：第 7 步整体在 `try/finally` 里。任何失败（无 wheel、解析超时、网络错误、制品是直接 URL 或不是 archive、
   名字或版本不合文法、安装的文件与计划不符、约束违例、落盘越界、遮蔽、验证失败、自设上限到期）以及**取消**（`CancelledError`：turn 超时、用户中断）
   都走 `finally`：先杀 pip 的整个进程组（pip 以 `spawn_group_leader` 启动，与 `bash` 同一套），再**仅当 `<root>/<key>/` 还没有
   fingerprint 时**删除它，最后释放锁；取消照常向上传播。失败的结果是普通 Observation（`is_error=False`），写明原因、新增违例清单
   与日志尾部（日志同样去掉 userinfo）。dry-run 已成功时，失败结果另附解析出的计划（要装的 `name==ver` 与 wheel 文件名、
   `kept_from_base`），供用户经 `bash` 手工处理或写进 `0_setup_env.sh`；请求的包装不上时加一句"the method that needs it
   cannot run here; report this rather than switching to another method"（第 6 版，取调研报告里 `install_plan` 与"blocker 显式化"
   两条借鉴的最小形式：只进结果文本，不落盘，§8）。
9. **返回**：装了哪些包（逐项 `name==version`、wheel 文件名、来源主机或目录，明文来源标 `plaintext`）、保留了哪些 base 版本（例："the index wanted llvmlite 0.43.0; the base environment's
   metadata says 0.47.0 while `import llvmlite` gives 0.43.0 — kept as is"，F48）、`pip check` 的新增违例（应为无）、命名空间
   目录、验证结果、仍缺且装不了的项与提示，以及**建议命令**：`PYTHONNOUSERSITE=1 <overlay>/bin/python skills/<domain>/<skill>/<script>.py …`
   （`PYTHONNOUSERSITE` 的理由见旧提交 `1b9b52e0`）。

**为什么 `prompts_for_itself=True`**：卡片要写"装进哪里、从哪些源、base 不变"，闸门的通用理由写不出来；"无事可做 /
复用 / 被拒（venv base）"时本就不该问（第 7 版起来源在启动时校验，调用时没有"来源未声明"这种拒绝）。F26 行为测试的前提
（"询问前不碰子进程"）**对本工具不成立**：询问前要跑一个本机子进程——第 2 步的探针（第 7 版起第 5 步不再跑 `pip config list`，
`IndexConfigReader` 删除）。它做成可注入的（`ProbeRunner`），F26 的测试夹具注入假实现，测试 docstring 写明这一例外与理由；
联网与写文件严格在询问之后。

**各 surface 与模式下的行为**（在 `skill_env=install` 前提下）：

| 情形 | 行为 |
|---|---|
| CLI default | 出卡片；`y` 一次；`s` 本会话不再问这个工具；`a` 写 `install_skill_deps(<skill>)` 的 allow 规则 |
| `auto-approve`、`/auto on`、会话 `s` | 不问——与 `bash("pip install …")` 今天的姿态相同（F25）；**这正是缺省不挂载的原因**（Q7） |
| 已有 `deny`/`ask` 规则 `bash(pip install*)` | **管不到本工具**（规则按工具名匹配，F25）；AGENTS.md 写明：开启 `install` 的部署如需同样约束，另写 `install_skill_deps` 的规则 |
| 规则 `ask: ["install_skill_deps"]` | 每次都问（规则来源的问题属 `ask_every_time`，`s` 不覆盖） |
| `read-only` | 拒绝（不声明 `read_only`） |
| `bypass-all` | 放行 |
| Channel | 文本作答（计划 0052）；`approval_timeout_s` 必设，到期即拒绝（F28） |
| Desktop | 按 Q6：显式设 `install` 时**拒绝启动**，报错写明原因（没有审批通道）与补救（改 `probe`，或改用 `oc cli`）；缺省 `probe` 不受影响 |
| 前台子代理 | 可用（与 `bash` 同）；后台不可用 |
| 沙箱运行中（无网或有网） | 不挂载（§4.6） |
| 沙箱降级 | 按 Q4 |

### 4.6 沙箱、overlay 机制与 benchmark（设计问题 3、5，Q4）

**沙箱**（Q4 三种情形分别裁定）：

1. **运行中、无网**：只探测、只提示，不挂安装工具。容器 `--network none`，系统提示已写"装包会失败"（F24）。
2. **运行中、有网**（部署把 `sandbox_network` 设为别的网络）：推荐同样只探测、不挂安装工具。宿主 overlay 在容器里不可用
   （下条）；在容器里建 overlay 意味着把安装器放进本来为隔离设计的执行环境，还要处理非 root 用户与工作区挂载，超出本计划。
   模型仍可经 `bash` 自行 `pip install`（照常审批）。
3. **降级**（请求了沙箱但没起来，只在 `sandbox_required=false` 时发生）：是 owner 的选项——(a) 不挂载（部署的意图是隔离）；
   (b) 挂载，按本机处理（此时 `bash("pip install …")` 本就能直接装进 base，default 模式下会问；不挂 overlay 工具只是拿掉了
   更安全的那条路，而且部署已接受回退到本机）。**推荐 (b)**。

**宿主建 overlay 再挂进容器不可行**：overlay 的 `bin/python` 是指向宿主 base 解释器绝对路径的符号链接，`pyvenv.cfg` 的
`home` 也指向宿主（F32），容器里通常没有同路径的同一解释器；只读挂载在 `docker run` 时就定死（F24）；编译型 wheel 还受 glibc
与 Python ABI 约束。venv 也不能搬家（console script 的 shebang 是绝对路径），所以"先建到临时目录再 rename"同样走不通。镜像归
运维（`docs/plans/0036-sandbox-layer.md`:77-79），0061 给的是清单：容器内探针的缺项就是镜像要补的包。

**benchmark（0059/0060）**：`sandbox_required=true` + 固定 `sandbox_image` 下安装工具必然不挂载，`run_skill` 从不供给，环境由
镜像唯一决定。论文实验与 SI 在 0059 的一次性冻结下运行（D6）：环境信息（镜像标签与冻结时记一次的 digest、解释器、声明包版本、
`skill_env` 取值）只在冻结清单里写一次，trial 只记冻结名；冻结期间环境有任何改动都开新冻结并重跑基线（§4.12、Q17）。两组消融的
`skill_env` 取值必须相同，并写进冻结清单（§4.10）。

**overlay 机制逐项**（旧提案 §8 风险表按新框架重核）：

| 旧风险 / 机制 | 旧做法 | 新框架下核实 | 处置 |
|---|---|---|---|
| 裸 base 上的重栈（torch/scvi） | `_CONDA_PREFERRED` 名单直接放弃 | dry-run 能在限时内给出纯 wheel 计划或给出失败（F34、F39） | 由 dry-run 结局 + 300 s 解析上限取代名单；`packages` 必填使重栈只在点名时进入 |
| R / CLI / conda-only | 类别闸门 | `## Dependencies` 只含 Python 包（F20）；registry 的 `kind` 字段标出 `git` 与 `r`（0062 §3.4，F64） | 保留：按 `kind` 分类，`git`/`r` 不装、只给提示 |
| system-site 继承创建者 | 从 `base_python` 创建 | 仍成立（F32）；**base 为 venv 时继承的是底层解释器**（F47） | 保留；base = 探针报告的 `executable`；`prefix != base_prefix` 即拒绝 |
| 进程内 `find_spec` 与子进程不一致 | 子进程探针、最终环境、脚本目录为 cwd | 仍成立；且工作区 cwd 会执行工作区代码、误报命名空间包（F45） | 保留并加固（§4.3） |
| 供给阻塞事件循环 | `to_thread` | 新工具是 async | 改用 asyncio 子进程 |
| fingerprint 太粗 | 加版本/prefix/`CONDA_PREFIX` | `CONDA_PREFIX` 取自 agent 进程，与 base 无关；base 事后变化不在内 | 去掉 `CONDA_PREFIX`；**把 mtime 与 base 发行包清单摘要放进 key**（缓存身份，不是安装校验），base 一变就是新 key |
| extra 名≠skill 名 | 计划中的 skill→extra 表（旧实现未做） | 只把 pyproject 当版本约束查找表即可 | 保留"只查约束"，规范化匹配 |
| `module_name`/`import_name` | 两个都读 | 0062 阶段二统一为 `module` 一个字段、键 = PyPI 名（F64） | 改为只读 `_sdk/deps.py` 的 `module`（AST + 0062 §3.4 解析顺序）；"两种字段名都读"作废 |
| BANKSY 双重供给 | `_DENY` | registry 把 pybanksy 标为 `kind="git"`、`alt_env="omicsclaw_banksy"`；子环境链路断了（F14），skill 侧回落由 0062 阶段一恢复 | pybanksy 归 git 类，不装；注记提及 `alt_env`；Tier 5 见 Q12 |
| AutoAgent 剥环境 | 扩白名单 | autoagent 不可 import；0056 复制了死变量（F17） | 建议删除（Q16） |
| 并发 / TOCTOU | 锁文件在 key 目录里 | **锁文件随目录被删时，等锁者锁住的是已删除的 inode，后来者又锁住新 inode，两者同时进入**（F62）；锁外判复用、锁内不复查 | 锁移到永不删除的 `<root>/.locks/<key>.lock`；锁内复查 fingerprint |
| 离线 / 无 uv / Windows | 非致命回退 | stdlib `--without-pip` 与 uv 同速、`uv pip` 有害（F32、F35）；新 `bash` 仅 POSIX（F23） | 去掉 uv；Windows 不作目标 |
| （新）`--no-deps` 漏传递依赖 | — | F33 | 只补缺钉版本 |
| （新）保留的 base 版本不满足新包约束，或 base 包依赖了新装包而版本不符 | — | F34；F60（主语是 base 包的违例） | `pip check` 的前后差集，非空即回滚 |
| （新）安装期执行任意代码 | — | sdist 安装会跑 `setup.py`；`--only-binary=:all:` 是命令行选项，需求文件里的 `--no-binary` 能覆盖它（F77）；它也不约束直接 URL 指向的 sdist，pip 在 dry-run 解析时就会构建（F84、F85） | `--only-binary=:all:`；无 wheel 的包报 `no-wheel`；第 7 版不写需求文件、不带调用方的任何 `PIP_*`，没有哪个配置来源能覆盖这个选项（审核 I2）；第 7.2 版沿用 pip 配置后仍成立：命令行的 `--only-binary=:all:` 胜过配置与环境里的 `no-binary`（F92），且不写需求文件。第 7.1 版如实补充：argv 里的直接 URL 由 spec 文法拒绝（§4.5 第 7.3 步）；依赖元数据里的直接 URL 仍会在 dry-run 期间被构建，只能拒绝其安装（第 7.6 步、Q33、R29） |
| （新）计划与安装之间制品被换 | — | 索引可在两步之间变化；`name==ver` 钉不住文件（F68） | 第 6 版不校验哈希（Q24）：安装 report 与计划逐项比对文件名，不符即回滚；同一文件名的字节被换是剩余风险（R23）。pip 默认会校验索引页给出的摘要（F80），本工具不关它、也不以它为依据 |
| （新，第 6 版；第 7 版重写；**第 7.2 版改为接受**）包从未经部署认可的地方来 | — | pip 配置可被 `bash` 改写（F77–F79）；依赖元数据里的直接 URL 会被跟随到任意主机（F67） | 第 7.2 版（D8）：**沿用本机 pip 配置，来源不核对**，卡片如实写明；与模型直接 `bash pip install` 同一风险面（R30）。仍保留：直接 URL 与非 archive 制品一律拒绝安装（直接 URL 指向的 sdist 在 dry-run 期间已被构建，F84、Q33）；结果逐项给出实际来源与传输方式 |
| （新）安装位置被配置或环境改走；凭据外泄 | — | `--isolated` 挡不住全局配置与 `PIP_CONFIG_FILE`（F61）；pip 配置的 `target`/`prefix`/`root` 把包装到 overlay 之外（F93） | 第 7.2 版：安装位置守卫——`pip config list` 与 pip 环境里出现 `target`/`prefix`/`root`/`user`/`src` 键即拒绝（只看键名，§4.5 第 7.3 步）；显示与记录一律去 userinfo；`RECORD` 落盘核对兜底 |
| （新，第 6 版）装后第一次执行新代码时拿到凭据 | — | agent 环境里的代理变量带凭据（F70）；新 wheel 的 `.pth` 在装后第一个 overlay 解释器（`pip check`）启动时就执行（F73） | 装后 `pip check` 与验证 import 都用自建的无凭据环境与临时 HOME（§4.5 第 7.8、7.10 步，F71） |
| （新）新包的顶层名遮蔽 base 模块 | — | 只按发行包名查遮蔽会漏（F63） | 从 `RECORD` 求顶层名对照 base |
| （新）中途失败、取消、被杀留下半成品 | — | 旧实现无 | `finally` 回滚（只删无 fingerprint 的目录）+ 杀进程组；下次锁内清理半成品 |
| （新）静默安装 | 默认 on | 与权限层冲突（F25） | 需审批的显式工具，缺省不挂载 |

**base 发行包清单**（F48）：在 base 解释器里以 `importlib.metadata.distributions(path=site.getsitepackages())` 只列 base 自己的
site-packages，不受 cwd、`PYTHONPATH` 与 user site 影响（否则摘要会随调用环境变化：在仓库根运行时会多出仓库里的
`omicsclaw.egg-info`）。名字按 PEP 503 规范化；**同名多条 → 只要有任一条即视为"base 已有"，版本记为全部版本的集合并标
`ambiguous`**；**无 `Name` 的记录按目录名 `<name>-<version>.dist-info` / `.egg-info` 解析**，解析不出的计入
`unknown_base_records` 并在结果里报数量。**清单摘要** = 排序后的 `(规范化名, 版本)` 列表的 sha256，只用于 key（缓存身份），
不参与安装校验（第 6 版把这里的"哈希"统一改称"摘要"，内容不变，只为与 Q24 去掉的"安装校验哈希"区分）。

**只补缺（fill-only）**（纯函数）：输入 dry-run 的 `--report` JSON 与 base 清单；输出
`install = [计划中 base 没有的发行包：name、version、wheel 文件名（URL 末段）、来源]`、`kept_from_base = [(名, base 版本, 索引想要的版本)]`、
`foreign = [是直接 URL、或不是 archive 的项]`（不按主机判定；第 7.2 版起 Q32 作废）。`install` 为空 → "无需安装"；`foreign` 非空 → 失败（§4.5 第 7.6 步）。第 5 版
每项的 sha256 与 `missing_hashes` 删除（Q24）。保留的 base 版本是否满足约束交给第 7.8 步的 `pip check` 前后差集——那是 pip 自己的
约束求值，skillenv 不必自带 PEP 508 求值器。

**key 与生命周期**：key 含 base 的全部状态（§4.5 第 3 步），因此**不存在"base 变了、原地重建"**：base 变化后旧 overlay 原样
留着（别的会话可能正在用它），需要时建新 key，旧目录留给用户删除。已写 fingerprint 的目录永不被本工具删除；本工具只会删除
自己这次建到一半、还没有 fingerprint 的目录（第 8 步），或锁内确认过的半成品（第 7.1 步）。

**位置（Q9）**：`skill_env_dir` 缺省 `$XDG_CACHE_HOME/omicsclaw/envs`，否则 `~/.cache/omicsclaw/envs`；每个 key 一个目录：
`<key>/.venv/`、`<key>/.meta.json`（含 `skill`、`requested_specs`、`installed`（第 6 版取代 `installed_pins`：逐项 `name`、
`version`、`wheel`（文件名）、`source`（取自安装 report 的制品 URL 的 `scheme://host[:port]`，已去 userinfo；本地目录写 `file:<目录>`；第 7.2 版不再按 §4.10 归一化）、
`transport`（`https`、`http`、`file`，其中 `http` 即明文源；**取自制品 URL 的 scheme，不取来源的**——https 索引可以链接到明文 http
文件，pip 只对页面做安全来源检查，F88，第 7.1 版；第 7 版删去 `https-unverified`））、`kept_from_base`、`package_sources`
（第 7.2 版：本工具不解析 pip 配置，此字段只记 `"pip configuration of this machine (not checked)"`；各项实际来源见 `installed[].source`，取自安装 report；第 7 版删去"配置键"与 `declared_sources`，审核 I5）、`base_*`、
`base_dists_sha256`（key 用的清单摘要，缓存身份，不是安装校验）、`pip_version`、`created`；**不含任何制品哈希**，也不记录"来源是否
给了摘要"（Q24、Q31）），fingerprint 在 `.venv/.omicsclaw.fingerprint`；锁在
`<root>/.locks/<key>.lock`。**不提供 list/remove/clean**；只有注记用的只读 `find_overlays(root, base_state, skill)`，只在本机
模式下调用。AGENTS.md 写明"整个目录可直接删除；base 改动后旧目录不会再被用到"。

**第 6 版：完整性、安全性与可复现各靠什么**（去掉哈希之后；第 7 版按"来源只取 OmicsClaw 配置"改写前两行与第四行；第 7.2 版按 D8"沿用本机 pip 配置"再改第一、四行）：

| 要保证的 | 靠什么 | 不保证什么 |
|---|---|---|
| 包从哪来（完整性的来源一侧） | 第 7.2 版：本机 pip 配置（与用户自己 `pip install` 相同），本工具不核对，卡片如实写明"未经核对"；argv 的 spec 不许是直接 URL（F85）；直接 URL 与非 archive 制品拒绝安装（§4.5 第 7.3、7.6 步）；结果逐项给出实际来源与传输方式 | 来源是否就是用户本意——pip 配置可被模型经 `bash` 改写（R30）；来源给出的字节是否可信；来源链接或重定向到的其他主机（R25）；代理（R24）；依赖元数据里的直接 URL 指向的 sdist 在 dry-run 期间被构建（F84，Q33、R29） |
| 装的是哪个文件 | `name==ver --no-deps --only-binary=:all:` 加安装 report 与计划逐项比对文件名（F68）；此外 pip 默认会校验索引页给出的摘要（F80）——这是 pip 的现成行为，本工具不关它，也**不以它为依据**（Q24） | 同一文件名的字节在两步之间被换（R23）；明文链路上的替换（R24） |
| 装上后不破坏环境 | 只补缺、`pip check` 前后差集、`RECORD` 落盘核对、顶层名碰撞、验证 import（全部与哈希无关，保留） | 运行期行为与 ABI（R16） |
| 安装过程不泄露凭据、不被改道 | 第 7.2 版：安装位置守卫（`target`/`prefix`/`root`/`user`/`src` 键即拒绝，F93）+ `RECORD` 落盘核对；pip 子进程的白名单环境（白名单外的 `LLM_API_KEY`、`OMICSCLAW_*` 不带）；装后子进程（`pip check`、验证）的无凭据环境（F73）；显示与记录一律去 userinfo | 新代码按绝对路径读文件或联网（R6）；pip 配置本身指向何处（R30） |
| 可复现（人读） | `.meta.json` 逐项记 name、version、wheel 文件名、来源主机与传输方式；冻结运行另由 0059 的冻结清单记录（D6） | 字节级重现：照记录可以从同一来源按同一文件名重装，字节是否相同取决于来源（PyPI 不许同名重传；私有镜像与本地目录靠部署自己担保） |

### 4.7 范围边界（设计问题 6）

| 依赖类别 | 例 | 0061 行为 | 归属 |
|---|---|---|---|
| 有 wheel 的 pip 叶子 | mygene、cnmf、SpaGCN | 探测；开启 `install` 的本机部署可按需安装 | 0061 |
| 只有 sdist | — | 探测；报 `no-wheel`，不装 | 用户经 `bash` 自行决定 |
| git-only | STAGATE-pyG、STalign、pybanksy | 探测；给出 registry 的 git 命令，不装 | 用户经 `bash`（照常审批） |
| 重栈（torch、scvi-tools） | — | 只在点名时规划；只补缺，base 已有者保留并报告；约束违例即回滚 | 推荐仍走 `0_setup_env.sh` |
| R 包 | CellChat、xcms | 不在 `## Dependencies`；skill 运行时的 `validate_r_environment` 自报 | `0_setup_env.sh` Tier 2/3 |
| CLI 工具 | samtools、STAR、GATK | 不探测 | `environment.yml` Tier 1、`tools/` |
| conda 子环境 | `omicsclaw_banksy` | 不做（旧 Phase 4） | Tier 5（Q12） |

**与 `0_setup_env.sh` 的关系**：安装期流程是"建完整环境"的推荐路径（F31），运行期供给只是"某个 skill 缺几片 pip 叶子"
时的补丁层：**从不修改 base 环境**，overlay 可随时删除。两者不共享代码；`0_setup_env.sh` Tier 2 用 `uv pip` 装进 base 是对的
（那里 base 就是目标），与 F35 不矛盾。

### 4.8 残留处置（设计问题 7）

| 残留 | 位置 | 处置 | 阶段 |
|---|---|---|---|
| `environment.py` 被删导致 `core/` 三模块不可 import；凭据剔除 | `core/external_env.py`:25、`core/dependency_manager.py`:8、`core/r_script_runner.py`:20（F11、F12） | **不在 0061（第 4 版）**：0062 阶段一把 `core/` 搬进 `skills/_sdk/`、删 skill 侧剔除、在 `bash` 本机路径与 `LocalExecutor` 剔除；不建 `child_env.py` | 0062 阶段一 |
| `tests/test_adaptive_env_phase3.py` | F10 | **删除**（0062 Q12 裁定移交本计划 P0b） | P0b |
| `skills/spatial/consensus-interpret/_llm.py`:79 import `omicsclaw.providers` | F43 | **不在 0061**：consensus 系列归 0058；0062 守卫 B2/B3 把它列为具名已知项 | 0058 |
| `skills/**/tests/` 下 3 个基准脚本 import `omicsclaw.skill.runner` | F43 | **不在 0061**：不被 pytest 收集，0062 守卫整体排除 `skills/**/tests/`（0062 Q5）；随 skill 基准的整理另行处置 | — |
| "import 不存在的 `omicsclaw.*` 模块"守卫（第 3 版 P0a 的 `tests/test_no_deleted_package_imports.py`） | F43 | **不再新建**：0062 §3.9 裁定由其 B2/B3 吸收。注：0062 的 B2 只扫 `skills/**` 与 `templates/skill/**` 的非测试代码，第 3 版还扫过 `omicsclaw/common`（今天无违例，F43）；这一处不再有守卫，影响很小，记入交付记录 | 0062 |
| `tests/` 下 10 个 import 已删除模块的测试文件（F44，除 F10） | F44 | **不在 0061**：属旧栈测试清理 | — |
| `remote/routers/env.py` 四个端点、`remote/schemas.py` 的 8 个 env 模型与 `Job.runtime_source` | F15、F16 | **不在 0061 修补**：模块本身不能 import；随 `remote/` 整包去留一起删（Q13）。P0b 只把 `AGENTS.md`:156 的 "Imports" 改成实测结果 | P0b（文档） |
| Desktop App 里调用 `/env/*` 的 8 处（`adaptive-env-proxy.ts`、`api/env/{overlays,adaptive-mode,doctor}/route.ts`、`runtimes/[id]/ping/route.ts`:67、`connections/[id]/test/route.ts`:108、`probe-profile.ts`:119、`electron/main.ts`:707） | F57，另一个仓库 | **跨仓库残留**：新后端对这些路径都返回 404；App 把它判为 `inconclusive`/非致命，鉴权由 `/health` 的 401 正确反映，不会误判；实际后果是 Env 页与 overlay/模式面板不可用。记入交付记录，由 App 仓库处理 | App 仓库 |
| `oc env overlays\|clean` | 旧 `surfaces/cli/_main.py`（已删） | **不恢复**；也不保留库函数（§4.6） | — |
| autoagent 白名单 | `autoagent/constants.py`:36-46 | **不改**（只读参考，0057 后删） | — |
| 0056 的白名单拷贝 | `ensemble/execution.py` `ENV_WHITELIST`（:39-40，在途，F17） | **建议**（非硬性）删去四个死名字（Q16）；随 0056 终审或随 P3 处理（0062 §3.7 明写不改白名单，不随 0062 阶段一） | 0056 终审或 P3 |
| `OMICSCLAW_ADAPTIVE_ENV`、`OMICSCLAW_SKIP_ADAPTIVE_ENV`、`OMICSCLAW_ENV_DIR`、`OMICSCLAW_RUN_PYTHON` | 仅死代码 | **退役**：P0b 列入 `.env.example` §12 与 `RETIRED`，说明"旧 runner 的开关，已无读取者"；**P1 合入后**再补一句"由 `OMICSCLAW_SKILL_ENV*` 取代"（Q14） | P0b、P1 |
| `pyproject.toml`:77-79 注释 | F19 | 改为"git-only（`kind="git"`），见 `skills/_sdk/deps.py` 的 `DEPENDENCIES`"。**放在 P1**：该文件在 0062 阶段二才有 registry，P0b 可能早于阶段二 | P1 |
| 旧提案 | `docs/proposals/adaptive-environment-provisioning.md` | 头部加状态行"实现已随 runner 删除；运行期供给见计划 0061" | P0b |
| `FRAMEWORK-REBUILD.md` "Kept and importable"（:1896） | F13 | **不在 0061**：0062 阶段一第 6 步改写 | 0062 阶段一 |
| `AGENTS.md`:165 `diagnostics.py` 条目 | 文件已删（工作树 `D`） | 从结构树删去该行 | P0b |
| 8 个 skill 的 `## Dependencies` 漏报 9 处（含 `spatial-domains`→cellcharter） | F52、F58 | 按 Q3 逐条人工确认后补声明，或进一致性测试的具名例外表 | P0b |
| BANKSY Tier 5 / `environments/banksy.yml` / `tools/README.md`:17-18 | F14 | 按 Q12（推荐另立小计划）；0062 阶段一已使 `domains.py` 的回退恢复设计中的 `EnvNotFoundError` 提示（0062 §3.5 明确 Tier 5 与 yml 不在 0062） | 另议 |
| `0_setup_env.sh`:4 注释"4 tiers" | F14 | 改为实际的 Tier 1–5 | P0b |

### 4.9 可观测与可复现（设计问题 8）

| 问题 | 记录位置 |
|---|---|
| agent 此刻用的是哪个解释器、缺什么 | `use_skill` 注记（`executable`、版本、缺项、user site 来源、可用的现成 overlay） |
| 装了什么、装在哪 | `install_skill_deps` 的结果；overlay 目录的 `.meta.json`（§4.6：逐项名字、版本、wheel 文件名、来源主机与传输方式，明文源标出；不含制品哈希） |
| 某次分析实际在哪个环境跑的 | 会话记录（`memory.db` 里的 `bash` 调用文本含解释器绝对路径）；`AuditHook` 只记参数摘要（`hooks/audit.py`:125-178），不能替代会话记录 |
| ensemble 试验的环境：**冻结运行**（论文实验、SI） | 0059 的冻结清单 `bench/freezes/<name>.yaml`（git tag 固定）里的环境段，冻结时写一次（§4.12 对 0059 的要求）；trial 只记冻结名，SI 另记分支名。不逐 trial 记录内容哈希（D6） |
| ensemble 试验的环境：**非冻结运行**（日常、开发） | 0056 的 `provenance.python`（已有，F30）；P3 经注入的 `describe_environment` 在 `trial.json` 记解释器与声明包版本，供排查（Q17） |

启动日志一行：`skill_env=off|probe|install location=local|sandbox python=<bash 的 python>`；`bash` 的 `python`、agent 的
`sys.executable`、`ensemble_python`（若挂载）三者不一致时记 warning（Q15）。v1 不加 OpenTelemetry span 属性。

### 4.10 配置、装配与消融（设计问题 10）

| 字段 | 默认 | 含义 |
|---|---|---|
| `skill_env` | **`probe`**（Q7） | `off` / `probe` / `install`（`SkillEnvMode`，StrEnum，仿 `SandboxMode`/`SkillsIndex`） |
| `skill_env_dir` | `None`（= §4.6 缺省位置） | overlay 根目录 |
| `skill_env_install_timeout_s` | `1800` | 一次安装（含 dry-run）的上限 |

全部经 `_Option`：`--skill-env` / `OMICSCLAW_SKILL_ENV`、`--skill-env-dir` / `OMICSCLAW_SKILL_ENV_DIR`、
`--skill-env-install-timeout` / `OMICSCLAW_SKILL_ENV_INSTALL_TIMEOUT_S`；同步 `.env.example` 与 `READ_BY_THE_STACK`。

**第 7.2 版删除的配置**（D8）：第 7 版的 `skill_env_index_url`、`skill_env_extra_index_urls`、`skill_env_find_links`、`skill_env_proxy`、
`skill_env_cert`、`skill_env_client_cert`（及其 `_Option`、环境变量、`.env.example` 条目），第 7 版的"来源值的文法"与主机、端口归一化，
"`install` 而未配来源即拒绝启动"（Q26 作废）、"额外索引须有主索引"，以及 pip.conf → `OMICSCLAW_SKILL_ENV_*` 的迁移对照（R28 作废）。
包来源、代理、证书、trusted-host 都由本机 pip 配置决定（§4.5 第 5 步），部署**不需要**为安装另写任何来源配置；已有 pip.conf 的
部署开启 `install` 即可用。第 6 版的 `skill_env_package_hosts`、`skill_env_package_dirs` 早在第 7 版已删除。

**检查点**（审核 I6，第 7.2 版保留其余部分）：纯配置不变量放在 `resolve_app_config`/`AppConfig` 一侧，不放进 `build_skill_env`——后者
只在 `tools is None` 时才被调用（`entry/assembly.py`:1173），显式传 `tools=` 的调用方会绕过它。第 7.2 版之后 `skill_env` 相关的纯配置
不变量只剩 `SkillEnvMode` 的取值与 `skill_env_install_timeout_s` 为正数。要读文件系统的检查——registry 是否可读（Q23）——放在
`build_skill_env`，因为 `resolve_app_config` 是纯函数（计划 0037）；显式传 `tools=` 时安装工具本来就不由 `build_skill_env` 构造，这项
检查跟着工具走即可。两类检查都不看沙箱是否运行。

**注记与建议命令**：安装后的建议命令只是用 overlay 解释器跑脚本，与 pip 无关；P1 注记里 git 类缺项给出的是 registry `install` 字段原文，
由用户经 `bash` 执行，走的是用户自己的 pip 配置——第 7.2 版起安装工具也走同一份 pip 配置，两条路的来源一致。P1 不因此改动。失败结果附的
计划只列 `name==ver`、wheel 文件名与来源主机（去 userinfo）。

**环境变量的读取位置**（审核 I6）：skillenv 不直接读 `os.environ`——pip 与装后子进程要用的少数变量（`PATH`、`LANG`、代理、
`LD_LIBRARY_PATH`，第 7.2 版起另有 agent 环境里的全部 `PIP_*`）由 entry 从交给 `main()` 的环境映射里取出后注入。P2 把 `"skillenv"` 加进
`tests/launch/test_the_environment_is_read_in_known_places.py` 的 `REBUILT_PACKAGES`，让扫描覆盖它；若实现中确需直接读，就在同一文件
的 `ENVIRONMENT_READERS` 里登记并写明理由。**加进去会立刻变红**（第 7.1 版，复核指出）：P1 已实现的 `skillenv/probe.py`:48 在嵌入的
子程序源码字符串里写了 `sys.argv[1]`，扫描按字面匹配 `FORBIDDEN_SPELLINGS`（`tests/_env_probe.py`，含 `sys.argv`）。所以同一改动里
要在 `ENVIRONMENT_READERS` 登记 `skillenv/probe.py`，理由写明"这是探针子进程读自己的 argv，那段源码在另一个解释器里运行，
本进程不读任何进程全局"。
`start_desktop` 在 `skill_env=install` 时按 Q6 **拒绝启动**（`AppConfigError`），报错写明"Desktop 没有审批通道"，补救是改为 `probe` 或改用 `oc cli`——与同文件 `_refuse_an_open_unauthenticated_bind` 的"Refused rather than defaulted"（`launch/_surfaces.py`:1102-1120）、Channel 缺 `approval_timeout_s` 即拒绝启动（`entry/channel/runtime.py`:276）、0056 D6"显式开启、条件不满足就报错"一致；`install` 只可能是部署显式设置的值。

**挂载矩阵**（`skills_index=off` 时 `use_skill` 不挂，什么都没有；`read-only` 模式不附注记）：

| `skill_env` | 沙箱关闭 | 沙箱运行（无网/有网） | 沙箱降级 | Desktop |
|---|---|---|---|---|
| `off` | 无注记、无工具 | 同左 | 同左 | 同左 |
| `probe`（缺省） | 注记（本机探针） | 注记（容器内探针） | 注记（本机探针） | 注记 |
| `install` | 注记 + `install_skill_deps` | 注记，无工具 | 按 Q4（推荐：注记 + 工具） | 按 Q6（推荐：拒绝启动） |

**工具位置**：`foundation_tools` 的最后一项——`…, memory_write, [run_skill], install_skill_deps, <mcp__*…>, task`（追加而非插入）。

**消融要求**：

- `off`：系统提示、工具定义序列、`use_skill` 对同一 skill 的输出，与改动前**逐字节相同**。
- `probe`（缺省）：系统提示与工具定义序列逐字节相同（只改工具结果）——**0056 的 golden 快照与 `MOUNTED` 都不用改**。
- `install`：系统提示逐字节相同；工具定义 = golden 在 `memory_write`（或 `run_skill`）与 `task` 之间插入 `install_skill_deps`。
- 不改 `CLAUDE.md`（默认系统提示的一部分，F29）：指引只放在工具描述与注记里（与 0056 §3.8 同一做法）。
- 复用 0056 的 golden 快照（`tests/entry/golden/ensemble_off_*`，F30），测试配置固定 `ensemble=false`；0056 若尚未合入，
  P1 自行生成 `tests/entry/golden/skill_env_off_*`。
- 0059/0060：两组的 `skill_env` 必须显式设为同一值（推荐 `off`），该值写进冻结清单的环境段（§4.12）。

### 4.11 包结构与分层

```
omicsclaw/skillenv/
  __init__.py   包 docstring 与公开名；不 eager import tool
  registry.py   ## Dependencies 包名行解析；<skills 根>/_sdk/deps.py 的 AST 读取与契约校验（RegistryFormatError）；
                PEP 503 规范化；名字解析（0062 §3.4 的①②③ + 本侧回落④）；类别取 kind；pyproject 约束；
                安装白名单与 [键, *also] 展开；探针输入的构造（r 类不进 imports）。第 5 版由 deps.py 改名，
                避免与 skills/_sdk/deps.py 同名——两者没有代码关系，本模块只读那个文件
  probe.py      探针命令生成与解析（纯函数）；ProbeRunner；LocalProbeRunner、SandboxProbeRunner
  report.py     use_skill 注记的渲染（纯函数）
  sources.py    （第 6 版新增，第 7 版改写，第 7.2 版收窄；纯函数）argv 需求项（spec 与钉版本的 name==ver）的文法校验、
                安装位置守卫（`pip config list` 输出与 pip 环境里 target/prefix/root/user/src 键的识别，只看键名）、
                制品的 transport 标注、report 制品核对（is_direct、archive_info）、URL 去 userinfo。第 7 版的来源值文法、
                主机归一化、配置到 PIP_* 的换算与 trusted-host 生成在第 7.2 版删除（D8）
  overlay.py    base 清单与摘要、key、fingerprint、锁（<root>/.locks）、创建、dry-run 规划、fill_only、安装与安装 report 比对、
                pip check 前后差集、RECORD 落盘与顶层名核对、验证（无凭据环境）、finally 回滚与半成品清理、find_overlays
                （第 7 版删去 IndexConfigReader 与 0600 需求文件）
  tool.py       install_skill_deps
```

只可 import 标准库、`omicsclaw.schema`、`omicsclaw.tools`、`omicsclaw.skills`；不得 import `entry`、`engine`、`provider`、
`sandbox`（经 `BashEnvironment` 结构化注入）、`permission`、`ensemble`、`common`，**也不得 import 顶层包 `skills` 或其任何
子模块**（含 `skills._sdk`；0062 D3 与 B4，registry 只作为文件读取）。`omicsclaw.skills` 不 import `skillenv`（注记回调由
entry 构造）。新增 `tests/skillenv/test_skillenv_is_a_layer.py`，`_LOWER_LAYERS` 加 `"skillenv"`。（第 3 版这里还列了 `core`：
0062 阶段一后 `omicsclaw/core` 已不存在，0062 B1 另有守卫。）

装配：`build_skill_env(config, skills, binding) -> SkillEnvBinding | None`（`off` 或 `skills_index=off` 返回 `None`），registry
路径取 `skills.root / "_sdk" / "deps.py"`，启动时读一次（不缓存到磁盘，进程内复用）；产出 `annotate` 回调（`read-only` 时不产出）
与（按挂载矩阵）工具。

### 4.12 对 0056 与 0059 的接口要求（Q16、Q17、Q21）

0056 已实现、未提交，本计划不改它，也不要求它破坏 0056 §3.1 的分层（F55）。第 4 版按 D6 把环境记录分成两种场景：

| 场景 | 环境记在哪里 | 谁负责 |
|---|---|---|
| **冻结运行**：论文实验与 SI，在 0059 的一次性冻结下跑 | 冻结清单 `bench/freezes/<name>.yaml` 的环境段，**冻结时写一次**；trial 只记冻结名，SI 另记分支名 | 0059（清单格式与冻结工具）；0061 只提下面的"对 0059 的要求" |
| **非冻结运行**：日常使用、开发、调试 | 每个 `trial.json` 的 `provenance.environment`：解释器与声明包版本 | 0056 的 runner 经 entry 注入的回调（本节第 2 条），0061 P3 实现 |

**对 0056 的要求**：

1. **建议**（非硬性）：`ensemble/execution.py` 的 `ENV_WHITELIST` 去掉四个死名字（F17、F18）。
2. **非冻结运行的环境记录经 entry 注入**：`EnsembleRunner` 增加可选参数
   `describe_environment: Callable[[CommandExecutor, str], Awaitable[Mapping[str, Any]]] | None`（第二个参数为 skill 名）；
   entry 用 `skillenv` 生成探针、经 `executor.capture` 执行、解析后返回 `{"executable", "version", "prefix", "packages":
   {发行包名: 版本或 null}, "missing": [...]}`，都是可读的名字与版本，**不含任何内容哈希**。`ensemble` 不 import `skillenv`，
   `test_ensemble_is_a_layer.py` 不改。Q21 已裁定保留该回调。
   - **argv 形式**（第 5 版补）：`CommandExecutor.capture` 接收的是 argv（`capture(argv, *, cwd, timeout, env=None)`，
     `ensemble/execution.py`），而 §4.3 的 `probe_command` 产出 shell 字符串。skillenv 另提供
     `probe_argv(python: str, imports, dists, skill_dir) -> list[str]`，产出 `[python, "-B", "-c", <固定代码>, <JSON>]`，其中
     `python = executor.python`；固定代码与 JSON 参数与 `probe_command` 共用同一份，不经 shell、不需要 `shlex`。cwd 传 skill 目录
     （trial 以 `tuning.script_path` 的绝对路径运行，该目录在执行位置必然存在，沙箱里经同路径只读挂载可见），固定代码照旧先剔除
     `''`/`'.'`；`env` 传 `None`，反映 trial 实际继承的环境。
   - **P3 一律注入**（第 5 版，审核 I2）：0061 不实现"冻结时不注入"——冻结开关由 0059 定义，P3 时还不存在，写一个无从验证的开关
     判断是空转。"冻结运行时不注入、trial 里不出现 `environment`"作为**对 0059 的要求**（下文第 5 条）由 0059 在引入冻结开关时
     实现。备选（未采用）：P3 给 `build_ensemble` 一侧留一个谓词参数 `inject_environment: Callable[[], bool]`，默认恒真，由 0059 填；
     不推荐，理由是它在 0059 之前没有任何调用者，且 0059 无论如何都要改 entry 的装配来读自己的冻结配置，顺手改注入条件的成本与填
     谓词相同。
3. **`run_skill` 不供给**：`ensemble_python` 由部署固定；需要 overlay 里的包时由部署把 `ensemble_python` 显式设为那个解释器。
4. **缺省配置不影响 0056 的 golden 与 `MOUNTED`**（`skill_env=probe` 不改工具表）；部署开 `install` 时由 0061 的测试覆盖。
5. **可选**：试验环境加 `PYTHONNOUSERSITE=1`（旧提交 `1b9b52e0` 的教训）。
6. **不做**：`tuning.yaml` 的方法级 `requires`（§4.2 (e)）。

**对 0059 的要求**（冻结清单归 0059；这里只列 0061 视角下环境段必须能回答的问题，字段名与格式由 0059 定）：

1. **环境段可读、一次写成**：冻结时记录——镜像标签与**冻结时记一次**的 digest（沙箱运行）；`ensemble_python` 与它报告的
   解释器路径、Python 版本、`prefix`；`skill_env` 的取值（两组消融必须相同，推荐 `off`）与 `sandbox_required`；被测 skill 各自
   `## Dependencies` 声明包的版本清单（`名字: 版本`，取不到写 `null`）。不写逐文件或逐包的内容哈希（D6）；代码版本由 git tag
   固定（这同时满足 0062 §3.9"冻结应覆盖 `skills/_sdk/**` 与 `skills/<domain>/_lib/**`"的要求——tag 覆盖整棵树，不需要逐文件
   sha256）。**冻结运行时工作树必须与 tag 完全一致**（干净检出：无未提交改动、无未跟踪的代码文件），否则 tag 不能代表实际运行
   的代码；怎么校验（例如运行开始时检查 `git status --porcelain` 为空且 `HEAD` 等于 tag 所指提交）由 0059 决定。
2. **建议**取数方式复用 skillenv：冻结工具在**执行位置**（沙箱冻结则在容器内）跑一次与 §4.3 相同的探针（`PYTHONNOUSERSITE=1`，
   剔除 `''`），把输出渲染进清单，这样清单与非冻结 trial 的 `environment` 字段口径一致。冻结工具属于 `bench/` 或 entry 一侧时可以
   直接 import `omicsclaw.skillenv`（它不在 `ensemble` 包里，0056 的分层不受影响）。是否采用由 0059 决定。
3. **若冻结运行使用 `sandbox_required=true` + 固定镜像**（§4.6），`install_skill_deps` 按挂载矩阵本就不挂载；**若 0059 允许本机
   冻结**，清单须记 `skill_env` 并要求它不是 `install`。
4. **冻结期间环境改动即新冻结**：镜像重建、`ensemble_python` 换环境、声明包升级都属于"改动"，按 D6 开新冻结并重跑基线；0061
   不提供"同一冻结内比对环境"的机制。是否在每次 run 开始时核对当前镜像 digest 与清单一致，由 0059 自行决定。
5. **冻结运行时不注入 `describe_environment`**（第 5 版由 0061 P3 移来，审核 I2）：0059 定义冻结开关（例如一个给出冻结名的配置
   项），并在 entry 装配 `EnsembleRunner` 时按它传 `describe_environment=None`，使冻结运行的 trial 里不出现 `environment`——环境以
   冻结清单为准，逐 trial 再记一遍既冗余、又会诱导人去比对本该由冻结保证相同的东西。对应的测试（第 4 版用例 25b）随之归 0059：
   冻结开关打开时 `EnsembleRunner` 收到 `None`、trial 里没有 `environment`；关闭时照常注入。

---

## 5. 分阶段（设计问题 9）

**顺序**（owner 已定，D6）：

```
0062 阶段一 合入 ──┬─> P0b 残留与文档
                   └─> P1 开工 ──(0062 阶段二 合入)──> P1 合入 ──(0056 合入)──> P3
论文主线 0057 → 0058 → 0059 → 0060 完成 ──> P2 本机安装
0059 设计时：§4.12 "对 0059 的要求"已写好，由 0059 吸收进冻结清单格式
```

依赖：P0b 需 0062 阶段一与 Q3、Q12–Q14；P1 开工需 0062 阶段一，**合入需 0062 阶段二**（`DEPENDENCIES` 那时才存在，Q19）与
Q1、Q2、Q15、Q20；P2 需 P1、Q3–Q10 与 Q27、Q28、Q31、Q33（第 7.2 版：Q26、Q29、Q30、Q32 作废，Q34 已裁定），排在 0057–0060 之后；P3 需 P1、0056 合入与 Q16、Q17、Q21（时点见 Q22，已裁定）。每阶段跑 §6
里该阶段的命令并保持绿。

**P0a**（第 4 版删除）：由 0062 阶段一取代（D6；0062 §3.9"P0a 的去向"）。第 3 版 P0a 的四项分别去了：`child_env.py`
不建；`core/` 的修复与三个测试文件的转绿归 0062 阶段一（`tests/test_external_env.py` 对应 0062 用例 6，
`test_r_script_runner_environment.py` 对应用例 7，`test_r_script_runner.py` 在 0062 中没有用例编号、随阶段一第 5 步搬进 `tests/sdk/`；
10 个 sc 脚本 `--help` 与既有 sc 测试转绿对应用例 13、14）；"import 不存在模块"守卫由 0062 B2/B3 吸收；
`tests/test_core_modules_import.py` 由 0062 用例 8 取代；`tests/test_adaptive_env_phase3.py` 的删除移到 P0b。

**P0b 残留与文档**（0062 阶段一合入后；依赖 Q3、Q12–Q14）

- 删除 `tests/test_adaptive_env_phase3.py`（F10；0062 Q12 移交）。
- `.env.example` §12（`# 12. No longer read by the rebuilt stack`）与 `tests/test_env_example.py` 的 `RETIRED` 加四个旧变量
  （此时**不提**新变量名）；旧提案状态行；`AGENTS.md`:156（`remote/` 的 "Imports."）、:165（`diagnostics.py` 条目）；
  `0_setup_env.sh`:4 注释；按 Q3 逐条确认 F58 的 9 处漏报并补声明（改的是 `SKILL.md` 正文的包名行，不动 frontmatter，
  `INDEX.md` 不受影响）。
- 第 3 版 P0b 的 `FRAMEWORK-REBUILD.md` 补记由 0062 阶段一第 6 步完成；`pyproject.toml`:77-79 注释移到 P1（§4.8）。
- **验收**：`git ls-files tests/test_adaptive_env_phase3.py` 为空；`tests/test_env_example.py` 通过；文档引用逐条核对；F58 的每一处
  都已补声明或写进 P1 一致性测试的例外表（附理由）；0062 阶段一的用例仍绿。

**P1 探测与报告**（`skill_env ∈ {off, probe}`，缺省 `probe`；`install` 值在 P2 前解析即报错）

- `skillenv/registry.py`（含 `_sdk/deps.py` 的 AST 读取、契约校验、0062 §3.4 顺序的名字解析与本侧回落、`kind` 类别、`[键, *also]`
  展开）、`probe.py`、`report.py`；`use_skill_tool(..., annotate=)`；`AppConfig.skill_env` 与 `_Option`；`build_skill_env`（registry
  路径取 `SkillIndex.root`）；启动日志与解释器不一致告警；`.env.example`（此时在退役说明里补"由 `OMICSCLAW_SKILL_ENV*` 取代"）；
  `pyproject.toml`:77-79 注释；逐 skill 的 registry 引用一致性测试（§4.2，扫描规则按 0062 F29）。
- 开工时先按附录 A 复跑 F58 与 F64 的扫描（此时调用形式已是 0062 阶段二之后的），以复跑结果为准写一致性测试的排除/例外表与
  回落冻结表。
- **验收**：`off` 时 `use_skill` 输出与改动前逐字节相同；`off`/`probe` 的系统提示与工具表都等于 golden；本机与假
  `BashEnvironment` 两条探针路径通过；工作区 `json.py` 不被执行、工作区 `cellbender/` 不致误报；read-only 不附注记；探针失败时
  `use_skill` 仍返回正文并带"不可用"一行；格式契约覆盖 94 个文件；registry 读取器读出真实 `skills/_sdk/deps.py` 的 61 键且
  子进程里 `sys.modules` 没有任何 `skills` 模块；声明名的回落集合等于冻结表；一致性测试除具名排除/例外外全绿；
  `sandbox_code_in_image` 情形（skill 目录不在执行位置）探针仍给出结果；0062 的 `tests/sdk` 仍绿（尤其 B4：`omicsclaw/**`
  不 import `skills`）。

**P2 本机安装**（`skill_env=install`，部署显式开启；**排在 0057–0060 之后**）

- `skillenv/sources.py`（第 7.2 版收窄）、`overlay.py`、`tool.py`；**不新增任何来源配置**（第 7.2 版，D8：沿用本机 pip 配置）；装配
  （挂载矩阵；registry 不可读时拒绝启动，Q23，在 `build_skill_env`）；`start_desktop` 按 Q6 拒绝启动；权限测试名单。
- **解除 P1 对 `install` 的封锁**（审核 I6）：`omicsclaw/entry/config.py` 的 `SkillEnvMode`（今天只有 `OFF`/`PROBE`，:108-118）加
  `INSTALL` 成员；删掉 `_as_skill_env`（:725-735）里"skill_env=install is not available in this version"那条拒绝分支；改写把它钉住的
  `tests/skillenv/test_entry_skill_env.py::test_install_is_refused_until_it_exists`（:75-77），改为断言 `install` 可解析并正常启动（第 7.2 版：不再有"未配来源即拒绝"，Q26 作废）。
- **环境读取的守卫**：把 `"skillenv"` 加进 `tests/launch/test_the_environment_is_read_in_known_places.py` 的 `REBUILT_PACKAGES`，
  **同时**在同一文件的 `ENVIRONMENT_READERS` 登记 `skillenv/probe.py`（第 7.1 版：它嵌入的探针源码含 `sys.argv[1]`，只加前者会立刻
  变红，理由见 §4.10）；skillenv 需要的环境变量由 entry 注入，若实现中还有别处确需直接读 `os.environ`，同样登记理由。
- 文档：`AGENTS.md`（结构树加 `skillenv/`、"Dependency source of truth" 里"Nothing installs from the section"一句按 Q3 改写、
  "Running a skill" 加一段、`bash(pip install*)` 规则管不到新工具的说明、overlay 目录可直接删除、**包来源沿用本机 pip 配置、未经 OmicsClaw 核对**、base 前缀下的 `pip.conf` 对 overlay 不生效（F93）、
  pip 配置里不要有 `target`/`prefix`/`root`（会被拒绝）、不要把 agent 会写入的目录配成 find-links（R26））、`.env.example`（只有
  `OMICSCLAW_SKILL_ENV`、`_DIR`、`_INSTALL_TIMEOUT_S` 三项）、`FRAMEWORK-REBUILD.md`、README 里程碑、本计划交付记录。
- **验收**：离线 E2E（本地 wheel，F38）：审批 → 规划 → 只补缺与制品核对 → 钉版本安装与安装 report 比对 →
  `pip check` 前后差集 → 落盘与顶层名核对 → 验证（无凭据环境）→ 复用时不问人、不联网；拒绝审批零副作用；第 7.2 版：来源取自测试夹具的 pip.conf（`PIP_CONFIG_FILE`
  指向它）且安装成功、卡片写明"未经核对"、结果里 http 制品标 `plaintext`；pip.conf 或环境里的 `no-binary`/`PIP_NO_BINARY` 不能让 sdist
  被构建（F92）；pip.conf 或环境里的 `target`/`prefix`/`root`/`user`/`src` → 在 dry-run 之前拒绝、base 与目标目录都未被写（F93）；
  不产生需求文件，argv 在 `--` 之后只有需求；
  约束违例（含 F60 那类主语是 base 包的违例）、安装的文件与计划不符、制品是直接 URL 都回滚且无残留目录；装后 `pip check` 与验证
  import 的子进程（含新 wheel 的 `.pth`）看不到代理变量与凭据；第 7.1 版：spec 为直接 URL 或带 `;`/`@` 时在任何子进程之前失败；cwd 里放 `pip/__main__.py`、`venv/__main__.py`
  不被执行；pip 子进程带 `PIP_NO_INPUT=1` 且遇到 401 不挂起；按 Q33 的裁定处理依赖元数据里的
  直接 URL（推荐 a 时：安装被拒、卡片有相应说明）；
  venv base 被拒；卡片、结果、`.meta.json`
  与日志里没有 URL 的 userinfo；两个并发调用同一 key 只有一个在建、另一个锁内复查后复用；安装中途取消后进程组被杀、目录被删、
  锁被释放；预置一个无 fingerprint 的半成品目录，下一次调用在锁内清掉它再建；带 `also` 的条目展开为多个发行包；沙箱运行时不挂载；
  golden 插入断言；`uv` 从未被调用；`OMICSCLAW_TEST_NETWORK=1` 的真实网络 E2E 手动跑一次并记入交付记录。

**P3 与 0056/0059 对接**（P1 与 0056 合入后）

- §4.12 对 0056 的 2、4（及经批准的 1、5）：`describe_environment` 回调（P3 一律注入；冻结时不注入由 0059 实现，§4.12 对 0059 的第 5 条）；
  `probe_argv`；`ensemble_python` 与 `bash` 的
  `python` 不一致告警。
- §4.12 对 0059 的要求是文档交付：在 0059 起草前转给 0059 的作者（或由 owner 在 0059 的已定裁定里引用），0061 不实现冻结清单。
- **验收**：假执行器下 `trial.json` 含 `provenance.environment`（字段全是名字与版本，无哈希）；`capture` 收到的是以
  `executor.python` 开头的 argv；探针失败时记 `{"error": …}` 且不阻止试验；`ensemble` 仍不 import `skillenv`；0056 全部
  测试仍绿。

---

## 6. 测试计划

新栈测试一律用 `rapids_singlecell` 环境（默认 `python` 没有 pytest）。第 5 版按阶段分开列命令（审核 I5：`tests/skillenv` 要到 P1
才存在，P0b 不能跑含它的命令）。下面 `$PYT` 指
`PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -p no:cacheprovider -q -o addopts="" -p no:randomly`，
`$BASE` 指 `tests/skills tests/tools tests/sandbox tests/permission tests/hooks tests/entry/test_assembly.py
tests/entry/test_permission_wiring.py tests/entry/test_open_app.py tests/entry/test_sandbox.py tests/entry/test_entry_is_the_top_layer.py
tests/test_env_example.py tests/sdk`：

```
# P0b（0062 阶段一合入后；不含 tests/skillenv）
$PYT $BASE

# P1（0062 阶段二合入后）
$PYT tests/skillenv $BASE

# P2（在 P1 的基础上，权限与装配相关文件已在 $BASE 里）
$PYT tests/skillenv $BASE

# P3（0056 合入后，另加 ensemble）
$PYT tests/skillenv tests/ensemble $BASE
```

P1 与 P2 的命令字面相同，区别只在 `tests/skillenv` 下多出的 P2 文件。第 4 版去掉了第 3 版末尾的五个文件：`tests/test_external_env.py`、`test_r_script_runner.py`、`test_r_script_runner_environment.py`
由 0062 阶段一搬进 `tests/sdk/`，`test_core_modules_import.py`、`test_no_deleted_package_imports.py` 不再新建（§5 P0a）；加入
`tests/sdk`，因为 P1 读取的 registry 契约（0062 用例 22）与零耦合守卫（B4）都在那里，skillenv 的改动不能让它们变红。

基线（F40 复跑，第 3 版，不含 `tests/skillenv`）：2066 passed, 2 skipped——这是 0062 之前的数字；P0b 开工时在 0062 阶段一合入后
的同一 commit 上重跑并以其为准（`tests/sdk` 的数字取自 0062 的交付记录）。已知无关：
`tests/tools/test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget` 单独跑会失败、整套通过；
`tests/tools/test_workspace.py`、`tests/test_control_plane_documentation_contract.py` 的既有失败。手写探针脚本加
`PYTHONPATH=/workspace/dataset/private/zhouwg_data/OmicsClaw`。

另外三条：

- 真实 overlay 与 Py3.11 base：`/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -o addopts="" tests/skillenv/test_overlay_real.py tests/skillenv/test_install_offline.py`
  （rapids 下这些用例以当前解释器为 base 也会跑；交付记录写两套结果，"跳过"不得冒充"通过"）。
- 第 3 版的 P0a 冒烟（10 个 single-cell 脚本 `--help`）已由 0062 用例 13 取代；**仅供测试的**变量 `OMICSCLAW_TEST_BASE_PYTHON` 沿用
  0062 的同名约定（不是配置项，与 Q15 的选项无关）。
- 真实网络：`OMICSCLAW_TEST_NETWORK=1 … tests/skillenv/test_install_network.py`（手动）。

### 6.1 TDD 用例清单

**P0a**（第 4 版删除；编号保留以免 §11 的引用错位）

1. （删除）三个 `core/` 测试文件由红转绿——归 0062 阶段一：`test_external_env.py` → 0062 用例 6，`test_r_script_runner_environment.py`
   → 用例 7，`test_r_script_runner.py` 在 0062 中无用例编号（阶段一第 5 步原样搬进 `tests/sdk/`、改 import）。
2. （删除）`test_core_modules_import.py`——由 0062 用例 8 取代。
3. （删除）`test_no_deleted_package_imports.py`——由 0062 的 B2/B3（用例 3、15）吸收。

**P0b**

4. `test_env_example.py`：`RETIRED` 加四个名字后"被提及、但不以 `NAME=` 提供"。`tests/test_adaptive_env_phase3.py` 的删除不另写
   测试（验收里核对 `git ls-files` 为空即可）。

**P1**

5. `test_dependencies_section.py`：94 个文件的包名行都能解析，名字集合 63 个（补 `cellcharter` 后 64 个）；散文可变；变异：缺段、
   无包名行、两行包名、名字不带反引号、含空格或 `;` → `DependencyFormatError` 且信息含文件路径。
6. `test_registry_reader.py`（第 4 版重写：读 `skills/_sdk/deps.py`）：
   - **真实文件**：读出 61 键；`kind` 直接取自字段——`git` 类恰为 {STAGATE-pyG, pybanksy, STalign}，`r` 类恰为 {xcms, metaboanalyst}，
     有 `also` 的恰为 {singler}，有 `alt_env` 的恰为 {pybanksy}；在子进程里读取后 `sys.modules` 没有任何 `skills` 开头的模块（读取不
     import）；读出结果等于 `import skills._sdk.deps` 的 `DEPENDENCIES`（测试可以同时 import 两侧，0062 §3.6）。
   - **名字解析顺序**（0062 §3.4）：`SpatialDE` 键精确 → `module` 为 `NaiveDE`；`spatialde` 规范化 → `SpatialDE`；`scvi`、`tangram`、
     `paste` 经 `module` 反查 → `scvi-tools`、`tangram-sc`、`paste-bio`；`STAGATE_pyG` 规范化 → `STAGATE-pyG`；本侧回落：`PyYAML→yaml`、
     `scikit-learn→sklearn`、`adjustText→adjustText`、未知名 `a-b→a_b`，类别一律 `pip`。
   - **回落冻结表**：94 个 `## Dependencies` 的声明名里走到回落的集合 == 测试里的 `DECLARED_FALLBACK`（F64 的 16 个名字，P1 开工复跑后
     定稿）。
   - **契约校验**（`tmp_path` 下的夹具文件）：没有 `DEPENDENCIES`、值是 `DependencyInfo(...)` 调用或含 lambda、缺必有字段、未知可选字段、
     `kind` 取值外、`also` 不是字符串列表、规范化后键重复、文件不存在 → 各自 `RegistryFormatError` 且信息含文件与行；`AnnAssign`
     与普通 `Assign` 都能读。
   - **安装展开不看 `install` 字符串**：夹具里把某条 `pip` 条目的 `install` 改成与键无关的命令，白名单展开仍是 `[键, *also]`；带
     `also` 的夹具条目展开为多个发行包。
   - **类别不看 `install` 字符串**（第 5 版，审核 I4）：夹具条目 `kind="pip"` 而 `install` 写 `Rscript -e '…'` → 类别是 `pip`；
     `kind="git"` 而 `install` 写 `pip install x` → 类别是 `git`。
   - **解析顺序②先于③**（第 5 版，审核 I4）：歧义夹具——条目 A 键 `Foo-Bar`，条目 B 键 `other`、`module` 为 `foo_bar`；解析
     `foo_bar` 必须得到 A（②规范化命中）而不是 B（③反查）。这样的注册表违反 0062 §3.4 的歧义禁令，读取器的契约校验会拒绝它
     （上一条），所以本用例**绕过读取器**，直接把 dict 交给纯函数 `resolve(name, entries)`；测试 docstring 写明：在合法 registry
     上②③的次序不可观察，本用例只把实现钉在 0062 文档写定的次序上，防止日后有人放宽歧义禁令时次序已悄悄漂移。
   - **探针输入的构造**（第 5 版，审核 I4）：`r` 类名字（夹具里声明 `xcms`）不进探针的 `imports`，也不进 `missing`；`git` 类照常
     进 `imports`，用的是 `module`（`pybanksy` → `banksy`）。
6b. `test_registry_unreadable.py`（entry）：registry 不可读时，`probe` 模式启动成功、记 warning、注记首行写"dependency registry
   unreadable"且仍附缺项；`install` 模式 `AppConfigError`。
7. `test_skill_requires_are_declared.py`：逐 skill——主脚本及其 import 的 `_lib` 模块里对依赖 API 的字符串调用名（0062 F29 的 AST 规则，
   见 §4.2）按①②③解析后，条目的键必须在该 skill 自己的 `## Dependencies` 里（F58）；共享预检模块与模块粒度误报走具名排除/例外表，每条
   带理由；补声明前对 F58 列出的 skill 失败（以 P1 开工复跑为准）；变异：从 `spatial-domains` 删掉 `cellcharter` → 失败；往例外表加一个
   不存在的 skill → 失败；某 `_lib` 里 `from skills._sdk import deps as dm; dm.require("louvain")` 这种别名形式也被收集。
8. `test_probe.py`（第 5 版加 `probe_argv`：以当前解释器为 `python` 经 `subprocess` 以 argv 形式运行，结果与 `probe_command`
   经 `bash -c` 相同）：真实子进程：存在/缺失；`find_spec` 抛异常视为存在；版本取不到记 `null`；非 JSON → `ProbeError`；`-B` 下无
   `__pycache__`；`shlex` 引用对含单引号的 JSON 正确；**cwd 里放 `json.py`（写一个标记文件）→ 标记文件不出现**；**cwd 里放空目录
   `cellbender/` → 仍报缺失**；`base_prefix` 与 `from_user_site` 字段（以假 `site.getusersitepackages` 目录验证）。
9. `test_probe_runners.py`：本机 runner 经 `bash` 且继承环境——`PATH` 前置假 `python`，探针报告的 `executable` 是它；skill 目录存在时
   cwd 是它、不存在时（模拟 `sandbox_code_in_image`）落在工作区且不把它插进 `sys.path`；
   超时杀整组（照 `tests/tools/test_bash_process_group.py`）；沙箱 runner 把 command/cwd/timeout 原样交给假 `BashEnvironment`，
   env 以 `env K=V` 前缀出现。
10. `test_report.py`：全在、git 缺项（命令取自 `install` 原文；有 `alt_env` 时提及它）、`r` 类（不探测、只写一句）、pip 缺项（工具挂/不挂）、现成 overlay（仅本机；沙箱运行时即使宿主有匹配 overlay 也不提）、user site 来源、沙箱无网与有网两种措辞、
    探针不可用、1500 字符上限。
11. `test_use_skill_annotation.py`：`annotate=None` 时输出等于改动前录下的字节；有回调时为"正文 + 目录 + 注记"，回调收到的正文与
    返回的正文相同；回调抛异常时仍返回正文并带"不可用"一行；`definition()` 两种情况相同。
12. entry：`skill_env` 解析与非法值（P1 期间 `install` 亦报错）；`off/probe` 下系统提示与工具表等于 golden；`read-only` 不附注记；
    沙箱运行时注记用沙箱 runner；解释器不一致时记 warning。
13. 分层：`test_skillenv_is_a_layer.py`（含：`skillenv` 不 import `skills` 或其子模块）；`_LOWER_LAYERS` 含 `skillenv`；`omicsclaw/skills`
    不 import `skillenv`；0062 的 `tests/sdk/test_boundary.py::test_framework_imports_no_skills`（B4）已知项不变。

**P2**

第 7.2 版（D8）：P2 用例的来源一律由测试夹具的 pip.conf 提供（pip 环境的 `PIP_CONFIG_FILE` 指向它、`HOME` 指向临时目录），
不再通过 `skill_env_*` 来源配置；下列各条里残留的第 7 版来源配置写法均按此理解。

14. `test_overlay_keys.py`：key 确定；随 base 路径、版本、prefix、**mtime、base 清单摘要**或请求 specs 变化；不随 agent 的
    `CONDA_PREFIX` 变化；base 清单只取 base 自己的 site-packages（在仓库根目录与 `/tmp` 下、带或不带 `PYTHONPATH` 得到同一个摘要，
    F48）；`.meta.json` 字段齐全（`installed` 逐项有 `name`/`version`/`wheel`/`source`/`transport`），`package_sources` 与各项 `source`
    不含 userinfo，**除 `base_dists_sha256` 外全文没有形如 64 位十六进制的值**（第 6 版，Q24）。
15. `test_fill_only.py`（纯函数，夹具为录下的 `--report` JSON 与 base 清单）：mygene → 装 2 个；pertpy → llvmlite/jax/jaxlib 进
    `kept_from_base`；**重复记录**（llvmlite 0.47.0/0.43.0）→ 视为已有、`ambiguous`；**无名记录**（`mpmath-1.4.1.dist-info`）→ 按目录名
    识别为已有；解析不出的计入 `unknown_base_records`；规范化（`STAGATE-pyG`/`stagate_pyg`）；第 6 版：`install` 每项的 wheel 文件名取自
    URL 末段；`is_direct` 的项、没有 `archive_info` 的项进 `foreign`（夹具取 F66、F67 录下的 report）；第 7 版：来源主机是
    `files.pythonhosted.org`、与索引主机不同的项**不**进 `foreign`（不查制品主机，§4.5 第 7.6 步）；argv 需求项只有 `name==ver`，没有 `--hash`；
    report 里名字或版本不合文法（如以 `-` 开头、含空格）→ 失败。第 7.1 版：夹具 report 中来源是 https 索引、制品 URL 是
    `http://…` → 该项 `transport` 为 `http`（取制品 URL 的 scheme，F88）；`is_direct` 的项进 `foreign` 时记下是谁的依赖元数据引入的
    （report 的 `requested` 与各项 `requires_dist`），供失败结果写明。
15b. `test_sources.py`（第 6 版新增，第 7 版重写，**第 7.2 版收窄**；纯函数）。第 7 版的来源文法、解析器一致、归一化、配置换算
    四组断言随 D8 删除（本工具不再解析来源）。保留与新增：
    - **安装位置守卫**（第 7.2 版，F93）：`pip config list` 的输出夹具里有 `install.target='…'`、`global.prefix='…'`、`install.root='…'`、
      `install.user='true'`、`:env:.src='…'` 任一 → 拒绝且信息写明是哪一项；只有 `global.index-url`、`global.trusted-host`、
      `global.proxy`、`global.no-binary` 等 → 放行；pip 环境里有 `PIP_TARGET`/`PIP_PREFIX`/`PIP_ROOT`/`PIP_USER`/`PIP_SRC` → 拒绝；
      判断只看键名的最后一段，值里含 `target` 字样（如某个 URL 路径）不误判。
    - **pip 环境**：结果环境含白名单变量与 agent 环境里的全部 `PIP_*`、`PYTHONNOUSERSITE=1`、`PIP_NO_INPUT=1`、
      `PIP_DISABLE_PIP_VERSION_CHECK=1`；不含 `PIP_CONFIG_FILE=/dev/null`（除非 agent 环境本来就这么设）；不含白名单外的
      `LLM_API_KEY`、`OMICSCLAW_REMOTE_AUTH_TOKEN`。
    - **spec 文法**（第 7.1 版，复核重要 2，F85、F91）：接受 `SpaGCN>=1.2.5,<2.0`、`scanpy >= 1.9`（上命令行前去空白）、
      `scvi-tools[cuda12]>=1.0`、`pkg[a,b] ~= 2.1 , != 2.1.3`、`x===1.0+local`；拒绝 `oc-far @ http://…/oc_far-1.0.tar.gz`、`x@http://…`、
      `numpy; python_version<'3.12'`、`x --no-binary :all:`、`x --no-binary`、`-e .`、`x==1.0 --hash=sha256:…`、`file:///tmp/x.whl`、
      含控制字符的，拒绝信息含来源文件与条目；仓库 `pyproject.toml` 的全部 extras 与 dependencies 都能通过（今天 62 个，一个不拒）。
16. `test_pip_check_diff.py`（纯函数）：夹具 = F49 的 14 行 base 违例作 before；after 为 before 中 `corneto … requires cvxpy-base,
    which is not installed` 一行被替换成 `corneto 1.0.0b7 has requirement cvxpy-base>=1.5.1, but you have cvxpy-base 0.0.1.`（F60）
    → 差集恰为这一行（主语是 base 包也能抓到，行数不变也能抓到）；after 与 before 相同 → 空；行序不同 → 空。另有一条用**真实 pip**
    的版本（照 F60）：临时 overlay 里先装一个只声明 `Requires-Dist: oc_dep2>=1` 的 `oc_user`（不装 `oc_dep2`）作"已有违例"，记 before；
    再装 `oc_dep2 0.1`，记 after；差集恰为 `oc_user … has requirement oc_dep2>=1, but you have oc_dep2 0.1.`——证明解析的是真实输出格式。
17. `test_overlay_real.py`：以当前解释器为 base 建 overlay；base 的 pip 可见；base 无 pip 时走 ensurepip 分支；**以 venv 为 base →
    拒绝**（F47）。
18. `test_install_offline.py`：测试内用 `zipfile` 现造小 wheel——`oc_leaf` 依赖 `oc_dep`；`oc_needs_old` 依赖 `packaging<1`（base 的
    packaging 更新）；一个只有 sdist 的包；一个顶层带与 base 已有模块同名的 `.py` 模块的 wheel；一个顶层只带无 `__init__.py` 目录的 wheel。
    （"base 包依赖了新装包"那一类违例由用例 16 的真实 pip 版本覆盖：测试用 base 解释器的 site-packages 不可写，作 base 的 venv 又会被拒。）第 7.2 版：
    来源由测试夹具的 pip.conf 给出（`[global] no-index = true`、`find-links = <tmp>`），pip 环境的 `PIP_CONFIG_FILE` 指向它、`HOME` 指向
    临时目录（不让开发机的用户级 pip.conf 混进来）。断言：`oc_leaf` 连同 `oc_dep` 装入、验证通过、base 不变，
    `.meta.json` 的 `installed` 逐项文件名与来源等于安装 report；`oc_needs_old` → 前后差集非空 → 回滚、无残留目录；sdist-only → `no-wheel`；顶层模块碰撞 → 回滚；只含命名空间目录的碰撞 → 报告
    但成功；在 dry-run 与安装之间（经可注入的 pip 调用包装）往 find-links 目录放一个同版本、带 build 号的 wheel → 安装 report 与
    计划不符 → 回滚（F68）；一个依赖元数据带直接 URL 的 wheel → `foreign` → 失败且未安装（F67）。**第 7.2 版的回归**（取代第 7 版的 B1、B3 回归：第 7.2 版有意读 pip 配置）：
    夹具 pip.conf 另加 `no-binary = :all:`、或设 `PIP_NO_BINARY=:all:`，find-links 里另放一个只有 sdist 的包 → sdist 不被构建（F92）；
    夹具 pip.conf 另加 `[install] target = <dir>`、`prefix = <dir>` 或 `root = <dir>`，或设 `PIP_TARGET` → 在 dry-run 之前拒绝、
    `<dir>` 与 base 都未被写、overlay 目录已回滚（F93）；**不产生需求文件**，pip 子进程的 argv 在 `--` 之后只有需求项、没有 URL；第二次调用复用、
    不调审批、在不给 find-links 时仍成功（证明不联网）；`PATH` 前置一个一运行就失败的假 `uv`，全程未被调用。**第 7.1 版**：
    （i）让测试进程的 cwd 与 overlay 根目录的上级各放一个 `pip/__main__.py`、`venv/__main__.py`（写标记文件）→ 标记文件都不出现，
    每个子进程的 argv 以 `<python> -I` 开头、cwd 是已删除的临时目录（复核重要 3，F86）；（ii）往测试 registry 的 `also` 里写
    `oc-far @ http://127.0.0.1:<端口>/oc_far-1.0.tar.gz`（该 sdist 的 `setup.py` 写标记文件）→ 在任何子进程之前失败、标记文件不出现、
    本地服务没收到请求（复核重要 2，F85）；（iii）find-links 里的 wheel 依赖元数据带直接 URL 指向同一个 sdist → 按 Q33 的裁定断言
    （推荐 a 时：安装被拒、无残留目录、结果写明是哪个包引入的直接 URL；测试 docstring 记下 dry-run 期间 `setup.py` 会被执行，F84）；
    （iv）find-links 服务在请求时回 401 → pip 不挂起、按失败返回（`PIP_NO_INPUT=1`）。
18b. `test_validate_env.py`（第 6 版）：两个夹具 wheel——一个的模块在 import 时、另一个带 `.pth` 在解释器启动时（F73），各自把
    `os.environ` 的键名与 `HOME` 追加写进一个路径在造 wheel 时就写死的文件；调用前在进程环境里预置 `HTTPS_PROXY=http://u:tok@…`、
    `PIP_INDEX_URL`、`LLM_API_KEY`、`OMICSCLAW_REMOTE_AUTH_TOKEN`，（第 7.2 版删去"测试配置设 `skill_env_proxy`"）。断言：文件里每一次记录（第 7.8 步的
    `pip check` 与第 7.10 步的验证都会触发 `.pth`）的键名 ⊆ §4.5 第 7.10 步的白名单（加上 Python 自己设的）；上述四个与 `PIP_PROXY`
    都不在；`HOME` 是临时目录且调用结束后已删除；结果列出新装的 `.pth`；import 卡住时超时杀整组。
19. `test_install_concurrency.py`：两个协程（与两个进程各一组）同时请求同一 key——只有一个执行安装，另一个锁内复查后复用，pip 只被调用
    一次；锁文件在 `<root>/.locks/` 且失败回滚后仍在；预置一个无 fingerprint 的 `<root>/<key>/` 半成品 → 下一次调用锁内删除后重建；
    已有 fingerprint 的目录在任何失败路径上都不被删除；base 清单摘要变化后得到新 key、旧目录原样保留。（第 6 版加的"来源不再被声明
    即拒绝复用"断言已随该检查在第 7 版删除，审核 I5。）
20. `test_install_cancel.py`：在 dry-run 与安装两个阶段分别取消调用（假 pip 为长睡眠脚本）——`CancelledError` 向上传播；pip 的进程组
    已被杀（照 `tests/tools/test_bash_process_group.py`）；无 fingerprint 的 key 目录已删除；锁已释放（随后的调用可立即加锁）；自设上限
    到期走同一路径。
21. `test_install_tool.py`：schema（`packages` 必填、`minItems: 1`）；policy 逐字段等于 §4.5；白名单（该 skill 的 `## Dependencies`）
    外的包名 → `ToolArgumentError`；白名单内的名字按 registry 展开为 `[键, *also]`，卡片列出展开后的全部发行包；`kind` 为 `git`/`r` 的名字
    不进计划；无要装的 / 只有 git 类 → 不调审批；拒绝审批 → `ApprovalDenied`，overlay 根目录下无新目录、无联网；
    安装处于 `pause_tool_timeout` 内；结果含建议命令且不含凭据；卡片不含 "hash" 字样；失败结果在 dry-run 成功后附解析出的计划；结果逐项
    列出文件名、来源（去 userinfo）与 `transport`，http 制品标 `plaintext`。第 7.2 版：卡片写明 "packages come from this machine's pip
    configuration … OmicsClaw does not check where that points"，**不列来源清单**；审批**之前**没有跑过任何 pip 子命令（假 pip 记录被调用
    的子命令；`pip config list` 只出现在审批之后的安装位置守卫里）。第 7 版的来源清单、`[PLAINTEXT]` 首行告警、代理一行的三种渲染、
    "pip configuration files are not used" 断言随 D8 删除。
22. 权限：`test_foundation_tools_keep_their_prompts.py` 的名单加入 `install_skill_deps`，注入假 `ProbeRunner`（报一个 pip 缺项）；
    （第 7.2 版删去"测试配置设一个 `skill_env_find_links`"：安装工具不需要来源配置即可挂载）；测试 docstring 写明本工具在询问前会跑一个本机子进程（探针）这一例外及其理由；`MOUNTED`
    **在缺省配置下不变**，`install` 配置下另测；闸门矩阵：default 问、auto-approve 不问、read-only 拒绝、`ask` 规则在 auto-approve 下
    仍问且 `s` 不覆盖、`a` 写出 `install_skill_deps(<skill>)`、`bash(pip install*)` 的 deny 规则不影响本工具（文档化的行为，测试钉住以免误读）。
23. 装配：`install` + 沙箱关闭 → 挂在最后一个基础工具之后、MCP 之前；沙箱运行 → 不挂；降级按 Q4；`start_desktop` 在 `install` 时抛
    `AppConfigError` 且信息含补救办法，`probe` 时正常启动；golden 插入断言；带假 MCP server 时位于第一个 `mcp__*` 之前。第 7 版
    （审核 I6）：`--skill-env install` 解析为 `SkillEnvMode.INSTALL`（改写 P1 的 `test_install_is_refused_until_it_exists`）；第 7.2 版：`install` 不配任何来源即可正常启动、挂载工具（Q26 作废）；第 7 版的"未配来源即拒绝""来源文法""路径存在性""列表变量
    与重复 flag 等价"断言随 D8 删除。
24. 网络 E2E（手动）：`OmicsClaw` 环境为 base 装 mygene，验证 import，第二次复用。第 7.2 版：直接用本机现有的 pip 配置（`/root/.pip/pip.conf` 指向内部代理 `http://10.20.16.126:8081/…` 加 trusted-host），不配任何
    OmicsClaw 来源：安装成功，`.meta.json` 各项 `transport` 为 `http`、结果标 `plaintext`。（`transport` 取制品 URL 的 scheme 这一条由纯函数用例 15 钉住，F88。）

**P3**

25. 假执行器 + 注入的 `describe_environment`（非冻结运行）：`trial.json` 的 `provenance.environment` 含解释器与声明包版本，值只有名字、
    路径与版本字符串（断言其中没有形如 64 位十六进制的值）；探针失败时记 `{"error": …}` 而不阻止试验；`ensemble` 未 import `skillenv`。
25b. （第 5 版移出，审核 I2）冻结时不注入回调的测试归 0059（§4.12 对 0059 的第 5 条）。P3 这边改为：entry 在 `ensemble` 挂载时总是注入
    `describe_environment`，`capture` 收到的 argv 以 `executor.python` 开头、不经 shell。
26. （若 Q16 采纳建议）`ENV_WHITELIST` 不含四个死名字。

### 6.2 关键变异（每条应使至少一个测试变红）

`find_spec` 异常改判为缺失；探针不剔除 `''`；探针 cwd 改回工作区；安装相关步骤漏设 `PYTHONNOUSERSITE`；不拒绝 venv base；
`annotate` 缺省不为 `None`；read-only 仍附注记；安装工具在审批前联网或建目录；`packages` 可省略；`fill_only` 不去掉 base 已有者；
重复/无名记录处理错误；base 清单受 cwd 或 `PYTHONPATH` 影响；去掉 `--only-binary=:all:`；`pip check` 改回只看主语是新装包；违例不回滚；透传 `PIP_*`；去掉 `PIP_CONFIG_FILE=/dev/null`；索引 URL 上命令行；
卡片、结果或 `.meta.json` 保留 userinfo；改用 `uv pip`；key 里放钉版本；key 去掉 base 清单摘要或 mtime；锁文件放回 key 目录；锁内
不复查；回滚删除已有 fingerprint 的目录；取消时不杀进程组或不删半成品；不按 `RECORD` 查顶层名碰撞；沙箱运行时仍挂载安装工具；
沙箱运行时注记仍指向宿主 overlay；Desktop 显式 `install` 不拒绝启动；接受白名单外包名；`skillenv` import `entry`；`ensemble` import `skillenv`；`off` 时工具表或系统提示变化。
第 4 版删去"守卫测试把裸目录当作包存在""`core/` 重新 import `omicsclaw.skill`"两条（归 0062 的变异 M2、M3），新增：registry 改用
`import skills._sdk.deps` 读取（用例 6、13）；类别改回从 `install` 字符串推断（用例 6 的 `kind`/`install` 矛盾夹具）；安装白名单改为解析 `install`
字符串而非 `[键, *also]`（用例 6 的夹具）；名字解析把 `module` 反查排到规范化匹配之前（用例 6 的歧义夹具，经纯函数绕过读取器的歧义禁令）或去掉反查（用例 6）；回落改用 0062 的
"`module` = 名字本身"（`PyYAML`、`scikit-learn` 探错，用例 6）；新增一个只能靠回落解析的声明名却不改冻结表（用例 6）；registry 非字面量
时静默当空表（用例 6）；`install` 模式在 registry 不可读时照常启动（用例 6b）；对 `r` 类名字做 `find_spec`（用例 6 的"探针输入的构造"；第 4 版误挂在纯渲染的用例 10）；
探针改回经 shell 字符串交给 `capture`（用例 25b）；`provenance.environment` 写入内容哈希（用例 25）。
第 6 版删去"去掉 `--require-hashes`""report 无哈希时退回无哈希安装"两条（Q24）。第 7 版删去第 6 版为"从 pip 配置推导来源"加的
变异（不补缺省 PyPI、`install.`/`:env:` 合并、主机后缀匹配、http 不在 trusted-host 时照常出卡、复用时不核对来源），保留并新增：
安装时读取了 pip 配置或调用方的 `PIP_*`（F77 的注入值、F79 的 `proxy`、`PIP_NO_BINARY` 起作用，用例 18）；来源写回需求文件或上命令行
（用例 18）；文法放过反斜杠、空白、两个 `@`、`%`、非 ASCII、`#`/`?`、以 `-` 开头（用例 15b）；IPv6 或尾点不归一化（用例 15b）；https
来源被加进 trusted-host，或 http 来源没被加进（用例 15b）；设了 `skill_env_proxy` 仍透传环境代理变量（用例 15b、18b）；放过 `is_direct`
或非 archive 的制品（用例 15、18）；安装 report 不与计划比对（用例 18）；卡片不标明文源（用例 21）；验证 import 或装后的 `pip check`
继承 agent 环境或 pip 环境（用例 18b）；`install` 且未配来源时照常启动，或该检查放在 `build_skill_env` 里而被显式 `tools=` 绕过（用例 23）；
P1 的"install 不可用"分支未删（用例 23）；`.meta.json` 写入制品哈希或"来源是否给了摘要"（用例 14，Q31）。第 7.1 版新增：spec 文法
放过 `@`、`;` 或名字后的非运算符（用例 15b、18）；子进程 cwd 不是空临时目录，或解释器不带 `-I`（用例 18 的劫持夹具）；trusted-host
不带端口（用例 15b）；`transport` 取来源而非制品 URL 的 scheme（用例 15）；不设 `PIP_NO_INPUT`（用例 18 的 401 夹具）；数字主机写法
或带前导零的端口被放过（用例 15b）；路径存在性检查放回 `resolve_app_config`（用例 23）。
第 7.2 版（D8）删去为"来源只取 OmicsClaw 配置"而设的变异：安装时读取了 pip 配置或调用方的 `PIP_*`（现在是有意为之）、文法放过各类
字符、IPv6 或尾点不归一化、https 或 http 来源的 trusted-host 生成、设了 `skill_env_proxy` 仍透传环境代理、`install` 且未配来源时照常
启动、trusted-host 不带端口、数字主机写法、路径存在性检查的位置。保留"来源写回需求文件或上命令行"。新增：去掉安装位置守卫，或守卫
按值而非键名判断（用例 15b、18）；守卫放到 dry-run 之后（用例 18：`<dir>` 已被写）；pip 环境带上白名单外的变量（用例 15b）；卡片重新
列出从 pip 配置解析出的来源（用例 21）；审批之前跑 pip 子命令（用例 21）。

---

## 7. 风险

| # | 风险 | 应对 |
|---|---|---|
| R1 | skill 级依赖过报（leiden 不需要 banksy） | 注记明写"用不到的方法不受影响"；`packages` 必填由模型按方法点名；方法级留给 §4.2 (e) |
| R2 | base 事后变化：装了同名包、或升级了 overlay 里编译型 wheel 依赖的库 | key 含 base 的 mtime 与发行包清单摘要，base 一变即是新 key，旧 overlay 不再被选中（不原地重建、不删除，别的会话可继续用旧目录）；新 key 需要再审批、再联网（Q28 的离线重建若被采纳，可免去联网，视裁定免去审批） |
| R3 | agent 忘了用 overlay 解释器 | 结果给出完整建议命令；下一次 `use_skill` 注记会指出现成 overlay（`find_overlays`） |
| R4 | 开启 `install` 且 auto-approve 时静默装大包 | 缺省不挂载（Q7）；`packages` 必填（Q8）；Desktop 显式 `install` 拒绝启动（Q6）；1800 s 上限；AGENTS.md 给 `ask` 规则写法 |
| R5 | 供应链：抢注、投毒、依赖混淆 | 只装白名单内的名字；只装 wheel；直接 URL 拒绝（F67）；spec 不许是直接 URL（F85）。**第 7.2 版（D8）：来源沿用本机 pip 配置、不核对**——pip 配置指向哪里、有没有 extra-index-url（依赖混淆的入口）都由用户自己的 pip 配置决定，与用户在终端 `pip install` 相同；卡片写明"未经核对"。第 6 版起不按哈希安装（Q24）：来源上被投毒的真名包不在拦截范围内（有哈希时也拦不住——哈希与文件出自同一个索引） |
| R6 | **对照 D3：本机模式下，新装的第三方代码在 import 时就能把数据外发** | 本计划无法在本机阻止——与用户自己 `pip install` 后运行同一风险；审批卡是唯一关口，真正的边界是沙箱（AGENTS.md 对 `bash` 的同一结论）；因此沙箱下不提供安装、缺省不挂载。第 6 版：安装流程里新代码会执行的两处——装后 `pip check`（`.pth`，F73）与验证 import——都用自建的无凭据环境与临时 HOME，至少拿不到环境变量里的凭据（§4.5 第 7.8、7.10 步，F70、F71）；之后用户按建议命令跑脚本时照常继承 agent 环境，这一点不变 |
| R7 | base 元数据不一致（F48） | 同名多条即视为已有并标 `ambiguous`；结果里写明 metadata 与实际 import 的版本差异；`pip check` 过滤后仍可能被 base 的混乱误导，失败如实报告 |
| R8 | Desktop 审批悬挂 | 按 Q6 显式 `install` 拒绝启动，缺省 `probe` 不涉及审批 |
| R9 | `use_skill`（`read_only`、`AUTO`）会执行一次固定的 `python -B -c` | 代码固定、名字已校验、剔除 `''` 后不会执行工作区代码（F45）；read-only 模式不附注记 |
| R10 | 在途改动冲突（`assembly.py`、`config.py`、`sandbox/config.py`、0056、0062 两个阶段） | 引用带符号名；P0b/P1 在 0062 相应阶段合入后 rebase；P2/P3 在 0056 合入后 rebase |
| R11 | overlay 缓存增长：base 每变一次，用到安装的 skill 就会多出一个新 key 目录 | 内容寻址去重；AGENTS.md 写明整个目录可删、base 改动后旧目录不会再被用到；注记在本机模式下可报出"与当前 base 不匹配的旧 overlay 数"；真有需要时再加清理表面（Q9） |
| R12 | base 的 pip 低于 22.2，无 `--report` | 报"无法规划"，不退回到不受控的安装（第 6 版的安装 report 比对同样依赖 `--report`） |
| R13 | 容器内探针依赖 `docker exec` 时延 | 10 s 上限；失败只写一行"不可用" |
| R14 | （第 4 版移出）10 个 sc 脚本恢复后暴露此前被掩盖的运行期问题 | 归 0062（其 R2） |
| R15 | 安装工具写工作区之外（用户缓存），`ToolPolicy` 没有"写工作区外"的字段 | 路径只由配置决定；删除只发生在本工具自己的回滚与锁内半成品清理里，且只删没有 fingerprint 的 key 目录；工具描述与 AGENTS.md 写明位置 |
| R16 | 约束检查漏检 | 第 2 版的"只看主语是新装包"会漏掉"base 包依赖了本次新装的包、版本不满足"这一类（F60），"反向冲突只可能来自遮蔽"的说法是错的；第 3 版改为装前装后两次 `pip check` 的差集，任何因本次安装新出现的违例都会被抓到。仍抓不到的是 `pip check` 本身不检查的东西（运行期行为、ABI），由 import 验证兜底且只证明"能 import" |
| R17 | 凭据外泄：私有索引或代理 URL 里的 `user:token` | 第 7.2 版：凭据在用户自己的 pip 配置或环境里（与今天用户手动 `pip install` 相同），本工具不读取、不上命令行、不写需求文件；结果、`.meta.json`、日志里的 URL 一律去 userinfo；验证 import 与装后 `pip check` 的子进程不带代理变量与任何 `PIP_*`（本机代理变量含凭据，F70） |
| R18 | 并发与中断：两个会话同时装同一 key；装到一半被取消、SIGKILL 或 OOM | 永不删除的 `<root>/.locks/<key>.lock` + 锁内复查；`finally` 回滚并杀进程组；锁内清理无 fingerprint 的半成品；有 fingerprint 的目录永不被删（F62） |
| R19 | pip 配置或环境里有安装位置类设置（`target`、`prefix`、`root` 等），把包装到 overlay 之外——`prefix` 指向 base 就是改了 base（F93） | 第 7.2 版：安装位置守卫在 dry-run 之前按键名拒绝（§4.5 第 7.3 步）；`RECORD` 落盘核对兜底（pip 日后新增的同类键、`sitecustomize` 改 pip 行为）。第 7 版的 `PIP_CONFIG_FILE=/dev/null` 随 D8 删除 |
| R20 | registry 契约两侧漂移：0062 改了 `DEPENDENCIES` 的字段或放宽为非字面量，skillenv 读不出来 | 两侧各有测试：0062 用例 22 钉住"可 `literal_eval` 且字段固定"，本计划用例 6 在真实文件上读并校验同一组字段；任何一侧改契约都会让另一侧的测试变红。`probe` 模式下读不出只降级注记，不影响 `use_skill` |
| R21 | P1 的合入被 0062 阶段二卡住 | 阶段二可与 0057 并行（0062 §4）；P1 可在阶段一后开工、先做与 registry 无关的部分（包名行解析、探针、注记、装配），读取器以夹具文件开发；不写读旧四份 registry 的过渡代码（Q19） |
| R22 | 冻结与非冻结两种记录方式被混用：有人拿非冻结 trial 里的 `environment` 与冻结清单比对，或在冻结运行里期待 trial 自带环境 | 冻结运行时 trial 里根本没有 `environment`（由 0059 实现并测试，§4.12 对 0059 的第 5 条），只有冻结名；AGENTS.md 与 0059 文档写明"环境以冻结清单为准，不同冻结之间不比较" |
| R23 | **（第 6 版）解析与安装之间，同一文件名的字节被换**——去掉哈希后的剩余风险 | 如实接受。能换而不被发现的只有"同名文件的字节"：换成别的文件名、或给同一版本追加新文件，都会被安装 report 与计划的逐项比对抓到（F68）。PyPI 不允许以同一文件名重传（删除后也不行），在 PyPI 上这个窗口不可利用；私有镜像与本地目录由用户自己的 pip 配置选定、由其担保（第 7.2 版，D8；原为 Q25 的"部署声明"）——能在两步之间换掉其中文件的人，在解析之前就能换，而那种情况下取自同一索引的哈希本来也挡不住；明文源上链路中的人任何时刻都能换（R24），这个窗口不额外增加什么。**第 7 版收窄**（审核 I1）：pip 默认会校验索引页链接上给出的 `#sha256=`（F80），所以来源给了摘要时，两步之间只换文件的字节会被 pip 自己拒绝；窗口实际只剩"来源不给摘要"或"页面与文件一起被换"两种。这是 pip 的现成行为，本工具不以它为依据（Q24），这里只为如实描述窗口的大小。代价是 `.meta.json` 只能证明"装的是哪个名字的哪个文件、从哪来"，证明不了与别处的同名文件字节相同 |
| R24 | **（第 6 版；第 7 版改写；第 7.2 版再改）明文源（http）与代理** | 第 7.2 版（D8）：是否用明文源、走哪个代理由用户自己的 pip 配置决定，本工具不预先识别，卡片统一写"未经核对"；装完后结果与 `.meta.json` 按制品 URL 逐项标 `transport`，http 的标 `plaintext`（F88）。明文链路上的任何人都能替换包的内容，且没有任何一步能发现（pip 默认的摘要校验也不行：摘要与文件走同一条明文链路）；代理同理。适用于用户自己掌控网络路径的内部代理，例如本机 `10.20.16.126:8081`（在 `NO_PROXY` 内、直连，F70） |
| R25 | **（第 6 版；第 7 版按审核 I1 改写）重定向与来源链接到的其他主机**（F66、F69） | 不比对制品 URL 的主机（第 7 版起；第 7.2 版起 Q32 作废，没有声明的来源可比）。重定向由 pip 内部跟随、report 只记重定向前的链接，本来就拦不住。剩余风险有两层（第 7.1 版改写）：①请求发给了没有配置的主机——重定向的目标、来源链接的文件主机会收到下载请求（请求里没有样本数据）；②**只有在来源给了摘要时**，字节才不会被换掉：审核方实测把文件链接 302 到另一主机并换字节，被 pip 默认的摘要校验拦下，目标主机只被访问了 1 次（F80，不作本工具的依据）；来源不给摘要时，链接或重定向到的主机能替换字节。另外，pip 只对索引页与 find-links 页做安全来源检查（F88）：https 索引可以链接到明文 http 文件，所以 `transport` 逐项取制品 URL 的 scheme，这类文件在结果与 `.meta.json` 里如实标为 `http`。依赖元数据里的直接 URL 拒绝**安装**（F67），但其 sdist 在 dry-run 期间已被构建（F84，R29） |
| R26 | **（第 6 版；第 7 版改写）find-links 目录与 pip 缓存被写入** | 能往 pip 配置的 find-links 目录里放 wheel 的人（包括经审批的 `bash` 或写文件工具）就能供包；pip 的 HTTP 缓存（`~/.cache/pip`）同理；第 7.1 版补：base 或 overlay 的 site-packages 里的 `.pth` 与 `sitecustomize` 会在 pip 进程里执行，并能读到 pip 环境（F89），`-I` 挡不住（它不关 `site`，F86）——它们都是用户可写的文件，本工具挡不住一个能以用户身份写文件的人。AGENTS.md 写明不要把 agent 会写入的目录（例如工作区之内）配成 find-links。不做运行期检查 |
| R27 | **（第 7 版；第 7.2 版作废）来源文法过严** | 来源文法随 D8 删除 |
| R28 | **（第 7 版；第 7.2 版作废）已有 pip.conf 的部署发现"配置没生效"** | 第 7.2 版沿用 pip 配置，不存在这个问题；唯一例外是 base 前缀下的 `pip.conf` 对 overlay 不生效（F93），AGENTS.md 写明 |
| R29 | **（第 7.1 版）dry-run 期间构建依赖元数据里直接 URL 指向的 sdist**（F84） | pip 配置里任一来源（第 7.2 版起它可被模型经 `bash` 改写，R30）提供的包、或 find-links 目录里的 wheel，若声明 `Requires-Dist: x @ <URL>` 且 URL 指向 sdist，pip 在第 7.5 步解析时就执行其 `setup.py`：以用户身份、有网络、看得到第 7.3 步 pip 环境里的代理变量与来源凭据；第 7.6 步只能拒绝安装。PyPI 来的包碰不到（F67）；argv 这一路已由 spec 文法堵住（F85）。处置待 Q33，推荐作为剩余风险接受：触发它要么需要 pip 指向一个恶意来源——它本来就能交付 import 时执行的 wheel（R6），这里多出来的只是执行得更早、看得到 pip 环境——要么需要有人往 find-links 目录里写文件（R26）；同一台机器上以用户身份运行的代码本来就能直接读 `.env`、`~/.netrc`、shell rc 里的同一批凭据，通常还能读 agent 进程的 `/proc/<pid>/environ`，而经审批的 `bash` 本就继承 agent 的环境变量——对同一用户的代码，把凭据藏在环境变量之外只是纵深防御。卡片如实写出这一点（§4.5 第 6 步） |
| R30 | **（第 7.2 版）pip 配置不受保护，被带偏的模型能先改 pip 配置、再请求一次看似正常的安装** | owner 裁定接受（D8、Q34）：同一个模型本就能绕过安装工具，直接 `bash pip install --index-url <任意地址>` 装进 base——那条路更糟，来源声明也管不到它；default 权限模式下改 pip 配置的那一步 `bash` 会被询问。卡片如实写"来源未经核对"，结果逐项给出实际来源。需要更强约束的部署（多人共享服务器、Channel、常开 `/auto`）等"锁定来源"作为可选配置加回（§8） |

---

## 8. 非目标（及不整合的代价）

| 不做 | 代价 |
|---|---|
| 通用 skill runner、`oc run`、`oc env`（D1） | 列出/清理 overlay 没有 surface，只能删目录 |
| 改写 `bash` 命令或会话级 overlay（候选 a） | agent 必须显式使用返回的解释器路径 |
| 经 hooks 探测、拒绝或安装（候选 d） | 无——hooks 做不到"问人"与"复核" |
| 缺省开启安装 | 想"现场搭环境"的部署必须显式设 `skill_env=install` |
| `run_skill` 内供给 | ensemble 试验缺包时只能如实失败，直到部署的 `ensemble_python` 环境补齐 |
| 沙箱内安装（无网与有网）、宿主 overlay 挂入容器、镜像构建 | 沙箱模式下缺包会卡住分析，直到运维重建镜像或模型经 `bash` 自行安装（有网时，照常审批） |
| conda-only、R 包、CLI 工具的运行期安装；conda 子环境自动创建 | 这些缺口只有提示，用户仍需 `bash 0_setup_env.sh` |
| git-only 与只有 sdist 的包自动安装 | STAGATE、STalign、BANKSY 需用户经 `bash` 自行安装 |
| 方法级依赖 | 注记过报（R1） |
| 注记覆盖子代理预载路径与直接照 `CLAUDE.md` 写命令的路径 | 这两条路径上仍只能在运行时遇到 `ImportError` |
| 人手跑脚本的探测（Q18） | 人只能读 `## Dependencies` 或跑 `0_setup_env.sh` |
| 复活 `requires:` frontmatter 或 `skill.yaml`（D2） | 依赖声明的格式只能靠测试守 |
| 修改 `CLAUDE.md` 或新增系统提示段 | 指引只在工具描述与注记里 |
| Windows | 新栈 `bash` 本就只支持 POSIX（F23） |
| 修改 `remote/` 死代码、`autoagent/`、旧栈测试、App 仓库 | 残留暂留，随各自的整包裁定或所属仓库处理（§4.8） |
| 修复 consensus 脚本（`runtime/workflow`、`_llm.py`） | 属 0058 |
| BANKSY 子环境（Tier 5） | 按 Q12 另立小计划；在此之前 `--with-banksy` 仍会失败 |
| （第 4 版）`core/` 断链修复与凭据剔除 | 无——由 0062 阶段一完成，是本计划的前置 |
| （第 4 版）import `skills._sdk`、或写读取旧四份 `_lib/dependency_manager.py` 的过渡代码 | P1 合入要等 0062 阶段二（Q19） |
| （第 4 版）冻结清单的格式、生成与校验 | 归 0059；0061 只给"对 0059 的要求"（§4.12） |
| （第 4 版）逐 trial 记录环境内容哈希（发行包清单哈希、镜像 digest 等） | owner 否决（D6）；冻结运行靠冻结清单与"改动即新冻结"，非冻结运行只记可读的名字与版本，排查时看不出"两次 trial 之间哪个没列出的文件变了" |
| （第 6 版）安装时的逐文件哈希校验（`--require-hashes`、取 report 的哈希、下载后本地取哈希） | owner 裁定（Q24）；完整性改靠来源控制加安装 report 比对（§4.6 第 6 版表），剩余风险见 R23、R24 |
| （第 6 版）强制 https、明文源缺省拒绝 | 第 7.2 版（D8）：明文与否由用户的 pip 配置决定，本工具只在结果里逐项标 `plaintext`。出处：调研报告《Claude Science 与 GPT Rosalind 环境供给》（`OmicsClaw_research/reports/`）"值得借鉴与应当避免的具体机制"表，Claude Science 的 `allow_insecure_mirror` |
| （第 6 版）本地 wheelhouse 与 base 变化后的离线重建 | 待 Q28 裁定；在此之前 base 一变就要重新审批、重新联网（R2）。第 6 版 `.meta.json` 的逐项记录已足以日后加上而不迁移数据。出处：同一报告"对 0061 的启示"之"key 粒度"一节 |
| （第 6 版）拒绝或失败时把安装计划落盘（`install_plan.json`）；沙箱模式下输出机器可读的"镜像需求"文件 | 失败结果文本里已附解析出的计划（§4.5 第 8 步），不另写文件——落盘要另定位置、格式与清理。出处：同一报告的借鉴表（Rosalind 的 `install_plan.json`） |
| （第 6 版）注记与工具描述里写"缺包的方法不得静默换成别的方法" | 注记属 P1，本版只改 P2；P2 只在安装失败的结果里写这一句（§4.5 第 8 步）。出处：同一报告的借鉴表（Rosalind 的 blocker 显式化） |
| （第 6 版）会话之外联网构建派生镜像、只放行索引主机的过滤代理沙箱、把请求方法限定为 GET | 另立计划；在此之前沙箱模式下缺包仍只能等运维重建镜像（§4.6）。出处：同一报告的借鉴表与结论（Codex cloud 的 setup 阶段、Claude Science 的域名放行） |
| （第 6 版）参考数据与数据库的就绪检查、锁定与漂移报告 | 超出 0061。出处：同一报告的借鉴表（Rosalind 的 `resource_lock`/`verify-lock`） |
| （第 7.2 版）**锁定来源**：由部署在 OmicsClaw 配置里声明索引、代理、证书，安装时不读 pip 配置（第 7、7.1 版的设计） | owner 裁定暂不做（D8、Q34）：来源沿用本机 pip 配置、不核对（R30）。日后开放到多人共享服务器、Channel 或常开 `/auto` 的场景时，作为可选配置加回；第 7.1 版的文法、换算与测试设计可在 §10 第 7、7.1 版条目与附录 A 里找到 |
| （第 7 版；第 7.2 版作废）https 来源不校验证书 | 第 7.2 版证书校验与 trusted-host 由用户的 pip 配置决定 |
| （第 7 版；第 7.2 版作废）pip 的 `timeout`、`retries`、`keyring-provider` 等其余选项 | 第 7.2 版这些选项照常取自用户的 pip 配置 |
| （第 7 版）核对制品 URL 的主机（第 6 版的 `skill_env_package_hosts`） | 第 7.2 版起没有声明的来源可比（Q32 作废）；来源链接或重定向到的主机不受限制（R25），直接 URL 仍拒绝 |
| （第 7 版）在结果与 `.meta.json` 里记录"来源是否给了摘要" | 待 Q31 确认；report 本身分辨不出来（F76） |
| （第 7.1 版）在解析期间阻止依赖元数据里的直接 URL 被构建（过滤代理、解析前自行遍历依赖、在 pip 之外另建一套解析） | 待 Q33；推荐接受为剩余风险（R29），各选项的可行性见 Q33 |

---

## 9. 待 owner 裁定的问题

审核方的立场在"审核方"一栏如实列出；与我的推荐不同的，在"分歧"里写明。第 4 版在"推荐"一栏标注了被 D6 与 0062 吸收或
作废的问题（"已由 0062/本版吸收"）；Q19–Q23 是第 4 版新引出的问题，第 5 版已移入 §9.1（已裁定）。第 6 版：Q24、Q25 是 owner
2026-09-24 直接给出的两条裁定，记入 §9.1；Q10 的选项与推荐按 Q24 改写；新引出的 Q26–Q28 追加在本表末尾，同属 P2。第 7 版：
按第 6 版审核改写 Q10 的选项 a 与 Q26–Q28 中涉及"声明集合"的措辞，新增 Q29–Q32（同属 P2）。第 7.1 版：按定向复核新增 Q33
（同属 P2）。第 7.2 版：owner 裁定 Q34（来源沿用本机 pip 配置，§9.1），Q26、Q29、Q30、Q32 随之作废，Q10、Q27、Q33 按新来源改写措辞。

| # | 问题 | 选项 | 推荐 | 审核方 / 分歧 |
|---|---|---|---|---|
| Q1 | 整合形态 / 接缝 | A 纯库 + `use_skill` 探测注记 + 需审批的 `install_skill_deps` + `run_skill` 只记来源；B 在 A 上再加会话级 overlay（`bash` 的 PATH 前置，cellclaw 式）；C 只做探测、不做安装（止于 P1）；D 走 hooks；E 在 `run_skill` 执行器里确定性安装 | **A**（read-only 不附注记；子代理预载路径不覆盖，已写明） | 有条件同意 A（条件已全部落实）；无分歧 |
| Q2 | 探测用的依赖集合 | a `## Dependencies` 包名行 + 格式契约测试（只钉包名行）；b registry；c 旁挂 `env.yaml`；d 运行时 import 探测；e `tuning.yaml` 方法级 `requires` | **a**（registry 做名字桥与类别），e 留给 0059。**第 4 版**：registry 的位置与读法已由本版吸收（D6：`skills/_sdk/deps.py`，AST 读取，类别取 `kind`），集合仍是 a | 同意；无分歧 |
| Q3 | `## Dependencies` 能否成为**安装来源**（改 AGENTS.md "Nothing installs from the section"），漏报怎么处理 | a 允许；白名单 = `## Dependencies` ∪ 本域 registry 的 pip 类键（第 2 版推荐）；a′ 允许；白名单 = `## Dependencies` ∪ 代码里被依赖 API 引用过的名字（第 5 版按 0062 F29 的规则为 32 个；第 3 版按 `require` 字面量计为 28 个），PyPI 名取 registry 的 `[键, *also]`（第 3 版写的是"取自 `install_cmd` 或 pyproject extras"，0062 合并后改为结构化字段，与 §4.2 一致）（审核方提出的收窄版）；b 允许，白名单只限该 skill 的 `## Dependencies`，漏报靠补声明 + 逐 skill 一致性测试；c 不允许，白名单只用 registry；d 不允许任何安装（停在 P1） | **b**，**部分吸收**（第 3 版由 a 改为 b；第 4 版不变。已由 0062/本版吸收的部分：白名单内的名字按 `[键, *also]` 展开、键 = PyPI 名；仍待裁定的是"`## Dependencies` 能否成为安装来源"本身）。a 的"registry 键不等于 PyPI 名"这条反对理由已由 0062 消除（F59 第 4 版注），但"安装面扩大 4–5 倍"仍成立，推荐不变 | 第 2 轮审核方推荐 b，不同意 a（安装面扩大 4–5 倍、registry 键不等于 PyPI 名，F59）；**我同意并改推荐**。a′ 作为折中列出，我不推荐：它仍要维护一张"引用名→PyPI 名"的映射，而逐 skill 一致性测试已能把同样的漏报变成显式声明 |
| Q4 | 沙箱三种情形 | (i) 运行无网：只探测 / 另有安装；(ii) 运行有网：只探测、不挂工具 / 容器内在工作区建 overlay；(iii) 降级：不挂载 / 挂载按本机处理 | **(i) 只探测 + 镜像交运维；(ii) 只探测、不挂工具；(iii) 挂载按本机处理** | 审核方同意 (i)，要求补 (ii) 并把 (iii) 列为选项；(iii) 的推荐与我第 1 版相反，理由见 §4.6 |
| Q5 | 安装的审批姿态 | a 与 `bash` 同（default 问，auto-approve / `/auto` / `s` 不问，`ask` 规则可强制每次问）；b 任何模式都问（需权限层新增能力，超出本计划）；c 两次审批（先批准联网解析，再批准钉版本清单） | **a**（前提是 Q7 缺省为 `probe`）。第 6 版：去掉哈希后推荐不变，卡片的时机与内容见 Q27 | 同意，前提相同；无分歧 |
| Q6 | 没有审批通道的 surface（Desktop）上如何对待 `skill_env=install` | a 拒绝启动（`AppConfigError`，写明原因与补救）；a″ 降为 `probe` 并告警（第 2 版推荐）；b 与其他 surface 相同（需审批时一直等）；c 仅在 auto-approve 时挂载 | **a**（第 3 版由 a″ 改为 a） | 第 2 轮审核方同意"不挂载"但要求拒绝启动而非降级，理由是 `_refuse_an_open_unauthenticated_bind`"Refused rather than defaulted"、Channel 缺 `approval_timeout_s` 即拒绝、0056 D6 三个先例；**我同意并改推荐**：`install` 只可能是部署显式写的值，静默降级会让部署以为自己开了安装 |
| Q7 | `skill_env` 缺省值 | `probe`（`install` 由部署显式开）/ `install` / `off` | **`probe`** | 审核方推荐 `probe`。**我第 1 版推荐 `install`，现改为同意审核方**：`CLAUDE.md` 建议 Desktop 用 auto-approve、已有 `bash(pip install*)` 规则管不到新工具，缺省 `install` 等于在一部分部署里重新引入默认静默安装（F25、F28）；且 `probe` 缺省不动 0056 的 golden 与 `MOUNTED` |
| Q8 | `packages` 是否必填 | 必填（`minItems: 1`）/ 省略时只报告不安装 / 省略时装全部缺项 | **必填** | 审核方要求补问；无分歧 |
| Q9 | overlay 位置与管理表面 | 位置：用户缓存 `~/.cache/omicsclaw/envs` / 工作区 `.omicsclaw/envs`（受保护目录、且被 0056 在容器里遮蔽）；表面：无 / CLI `/env` 斜杠命令；库函数：不写 list/remove/clean / 先写好 | **用户缓存、无表面、不写 list/remove/clean** | 同意并建议删库函数，已采纳；无分歧 |
| Q10 | 安装策略（第 6 版按 Q24、Q25 改写；第 7 版再改） | a 只补缺钉版本（`name==ver --no-deps --only-binary=:all:`，需求放在 argv 的 `--` 之后）+ **来源沿用本机 pip 配置**（第 7.2 版，Q34；第 7 版的"只取 OmicsClaw 配置"已撤回）+ 安装位置守卫（F93）+ 拒绝直接 URL+ 安装 report 与计划逐项比对文件名 + **装前装后 `pip check` 差集**违例回滚 + pip 子进程的白名单环境与验证子进程的无凭据环境 + `RECORD` 落盘与顶层名核对；a‴ 同 a，但约束检查改为"主语或依赖对象属于新装包"的过滤（审核方的退一步方案）；b 旧的纯 `--no-deps`（F33 漏依赖）；c 带依赖装、遮蔽即拒绝；d 带依赖装、允许遮蔽（ABI 风险，popv 会把 numpy 降到 1.26.4）；另：是否允许源码构建。第 5 版 a 里的 `--require-hashes`（report 无哈希即失败）已按 Q24 删除 | **a，不允许源码构建** | 第 6 版注：下面审核方的"同意 a"针对的是含哈希的第 3 版 a；按 owner 裁定去掉哈希、加上来源控制后未再送审。第 2 轮：审核方同意 a，**前提是 N-1、N-2、N-3 都修好**（第 2 版写的"I-7/8/9 已落实"不足以成立：N-1 约束检查漏检、N-2 `--isolated` 隔离不全且凭据外泄、N-3 锁与回滚非原子）；三条已在第 3 版修订（§4.5、§4.6）。选差集而非 a‴：差集不依赖解析违例行的语法，也覆盖"新包之间"的冲突。注：否决 c 的证据里 7 个遮蔽中 4 个只因本机坏元数据（F34 复跑），健康 base 上 c 的拒绝率会低一些，但 3 个真实冲突（含 numpy）仍在 |
| Q11 | P0 拆分与先行 | P0a 立即单独实施、P0b 随 Q3/Q12–Q14 / 与 P1 一起 | **已由 0062/本版吸收**：P0a 删除，由 0062 阶段一取代（D6）；P0b 在 0062 阶段一后实施 | 同意拆分；无分歧 |
| Q12 | BANKSY 子环境（F14） | a 在 P0b 从 `259fb52a^` 恢复 `environments/banksy.yml`；b 另立小计划（先验证 yml 仍能解析，再决定恢复还是删 Tier 5 与回退）；c 删除 Tier 5、`--with-banksy`、`domains.py` 子环境回退（需改 skill 代码） | **b** | 审核方倾向 b。**我第 1 版推荐 a，现改为同意审核方**：Tier 5 只在显式 `--with-banksy` 时运行，0062 阶段一（第 3 版写的是 P0a）已恢复设计中的提示，未经验证的 yml 不该直接恢复；0062 §3.5 明确 Tier 5 与 yml 不在 0062 |
| Q13 | `remote/` 残留 | a 0061 只修 `AGENTS.md`:156 的描述，`remote/` 整包去留另议；b 0061 删 `routers/env.py`、8 个 env 模型、`Job.runtime_source` 及引用；c 不动 | **a** | 同意；无分歧 |
| Q14 | 旧环境变量 | 退役四个旧名、新用 `OMICSCLAW_SKILL_ENV*`（P0b 退役说明不提新名，P1 后再补）/ 复用 `OMICSCLAW_ENV_DIR` 等旧名 | **退役 + 新名，分两步写** | 同意并要求 P0 不提前引用新名，已采纳；无分歧 |
| Q15 | `bash` 的 `python`、agent 的 `sys.executable`、`ensemble_python` 不一致 | a 只告警（启动日志 + 注记写明）；b 新增 `skill_python` 配置作为探针与 overlay 的 base；c entry 把 `sys.executable` 所在目录前置到 `bash` 的 PATH | **a**（Desktop 本机模式下 App 已前置所选解释器，F57） | 同意；无分歧 |
| Q16 | 对 0056 的接口要求（§4.12） | 第 1 条（删死变量）：硬性 / 建议；第 2 条（环境记录）：(a) `ensemble` import `skillenv` / (b) entry 注入 `describe_environment`；由 owner 转告 0056 实施方 / 授权 0061 P3 在 0056 合入后补 | **第 1 条为建议；第 2 条取 (b)；授权 P3 补**。第 4 版：第 2 条收窄为"只在非冻结运行注入"（§4.12），是否仍保留见 Q21；**已修正（见第 5 版审核 I1）**：第 4 版写的"第 1 条可随 0062 §3.7 一并做"是错的——0062 §3.7 明写不改白名单；第 1 条只随 0056 终审或随 P3 处理 | 审核方：第 2 条不同意 (a)（违反 0056 分层，F55）。**我第 1 版推荐 (a)，现改为 (b)**；第 1 条同意改为建议 |
| Q17 | ensemble 环境记录的位置与格式（第 4 版按 D6 重写） | **冻结运行**：已由 D6 裁定——环境写进 0059 冻结清单的环境段（一次，可读），trial 只记冻结名，不逐 trial 记内容哈希；0061 只提"对 0059 的要求"（§4.12）。**非冻结运行**：a 写进 `run.json`（`bind_run` 只写首次，F55）；b 写进每个 `trial.json` 的 `provenance.environment`（每试验一次探针，约 50 ms 本机、一次 `docker exec` 容器），只记名字与版本；c 不记录 | **冻结部分已由本版吸收；非冻结部分仍推荐 b**（owner 已明示"非冻结仍按原设计在 trial 里记录"，此处只请确认字段只含名字、路径与版本） | 审核方要求单列并提示 `bind_run` 的首写语义；未给推荐 |
| Q18 | 人手跑脚本的路径 | 不提供 / 提供 `python -m omicsclaw.skillenv check <skill>` | **不提供**（非目标，§8） | 同意；无分歧 |
| Q26 | **`skill_env=install` 但没有配置任何包来源时怎么办**（第 6 版新增；第 7 版起"来源"指 `skill_env_index_url` 与 `skill_env_find_links`） | （第 7.2 版作废：D8 删除了来源配置，`install` 不需要任何来源配置即可启动） | **作废**（D8、Q34） | — |
| Q27 | **审批卡片的时机与内容**（第 6 版新增；与 Q5 相关） | a 保持单次审批、在任何联网之前（现行）：卡片写请求的 specs、"按本机 pip 配置安装、来源未经核对"（第 7.2 版，Q34；不再列来源清单）、overlay 路径与 base，并写明"确切版本在批准后从上列来源解析，结果逐项列出装了哪些 wheel"；b 先 dry-run 再审批，卡片列出钉版本清单与文件名；c 两次审批（即 Q5 的选项 c：先批准联网解析，再批准钉版本清单） | **a**：去掉哈希不改变时机的理由——第 5 版卡片本来就不列钉版本，哈希只出现在批准之后。b 让联网发生在询问之前，违反 F26 行为测试的前提（询问前不碰 socket），而且经内部代理的 dry-run 下载的是**整个 wheel**（F66），等于批准前就把第三方代码拉到了本机。c 的第二张卡列的是几十个传递依赖的名字与版本，用户难以逐一判断；去掉哈希后它也承诺不了"就是这些字节"，对 R23 没有帮助。第 7.2 版起来源由用户自己的 pip 配置决定，卡片如实写"未经核对"。若 owner 在 Q5 改选 c，本题随之作废 | 第 6 版审核：认可推荐 |
| Q28 | **本地 wheelhouse 与 base 变化后的离线重建**（第 6 版新增；出处：调研报告"对 0061 的启示"之"key 粒度"一节） | a 不做（现行）：base 一变即新 key，需要时再审批、再联网（R2）；b 做：首次安装改为先 `pip download` 到 `<root>/.wheels/<来源>/<文件名>`（按来源分目录——去掉哈希后按文件名存放可行，但同一文件名在不同来源可能是不同字节），再 `--no-index --find-links` 从这里装；key 未命中时，找 skill、请求 specs、base 路径/版本/平台都相同、只有清单摘要不同的旧 overlay，用它 `.meta.json` 里的同一批文件名离线重建新 key，重算只补缺并照常做 `pip check` 差集、`RECORD` 核对与验证，任一步失败退回正常的联网审批路径；**重建照常出卡**，卡片标明"离线、与 <旧 key> 同一批 wheel、不联网"；c 同 b，但**重建免审批**（按复用处理），结果写明"用此前批准过的同一批 wheel、针对变化后的 base 离线重建" | **a**：P2 尚未交付，base 变化的真实频率未知（调研报告指出用户经 `bash` 把 git-only 包装进 base 就会让全部 overlay 失效，这是真实的代价，但频率要等 P2 用起来才知道）；b/c 的实现量不小——下载与安装拆成两步、wheelhouse 的布局与并发（沿用 `.locks/`）、旧 overlay 的查找、失败回退，另加至少两个测试文件；而第 6 版的 `.meta.json` 已逐项记下 name、version、wheel 文件名与来源，日后加上不需要迁移数据。磁盘代价约为所装 wheel 文件之和（F72：5 个小包 432 KB，对应 overlay 5.3 MB；torch 一类单个 wheel 就是数百 MB 以上），且与 overlay 一样不会自动清理（Q9）。**若 owner 选做，推荐 c 而非 b**：离线重建不引入新的字节、不联网，所批准的"从这些来源装这些包"没有变，再问一次只增加审批疲劳；条件是按文件名找到的每个 wheel 的来源仍在当前配置的来源里，否则退回联网审批 | 第 6 版审核：认可推荐 |
| Q29 | **来源与传输参数是否只从 OmicsClaw 配置取、完全不读 pip 配置**（第 7 版新增；审核 B1–B3） | （第 7.2 版作废：owner 选了相反方向：来源沿用本机 pip 配置（Q34）） | **作废**（D8、Q34） | — |
| Q30 | **若 Q29 选 b，pip 配置里的 `proxy`、`cert`、`client-cert` 怎么处置**（第 7 版新增） | （第 7.2 版作废：前提（Q29 选 b）不再成立：第 7.2 版本来就读 pip 配置且不另作处置） | **作废**（D8、Q34） | — |
| Q31 | **是否在结果与 `.meta.json` 里记录"来源是否给了摘要、pip 是否据此校验过"**（第 7 版新增；审核 I1） | a 不记录，只在计划里如实描述 pip 的默认行为（F80）；b 记录（要么解析索引页，要么解析 pip 的 `-v` 日志——report 里的摘要在链接没给时是 pip 自己算的，分辨不出来，F76）；c 记录并在卡片上提示 | **a**：Q24 删掉了卡片、结果、`.meta.json`、日志里一切为哈希服务的字段，b、c 会以"是否有摘要"的形式把它带回来，并诱导人把 pip 的默认行为当成保证；而且 report 分辨不出来（F76），要多写一个页面或日志解析器。这里的边界：计划可以如实描述 pip 默认会校验（R23、R25 用它说明窗口有多大），但本工具不关它、不依赖它、不记录它 | — |
| Q32 | **制品 URL 的主机是否也必须写在配置里**（第 7 版新增） | （第 7.2 版作废：没有声明的来源可比；制品主机不查（R25）） | **作废**（D8、Q34） | — |
| Q33 | **dry-run 期间 pip 会构建依赖元数据里直接 URL 指向的 sdist（执行其 `setup.py`，看得到 pip 环境），怎么处置**（第 7.1 版新增；F84、R29） | **a** 作为剩余风险接受，前提是已配置来源由部署担保（Q25）：卡片如实写明（§4.5 第 6 步），第 7.6 步拒绝其安装，失败结果写明是哪个包的依赖元数据引入的。**b** 不支持本地目录形式的 find-links（只许 URL 形式的来源），或要求 find-links 目录不在模型可写的位置。本机模式下模型的 `bash` 与 OmicsClaw 是同一个 uid，"模型不可写"只能落实为"该目录及其各级上级既不属于当前 uid、也不可被它写入"，启动时可用 `os.stat`/`os.access` 检查；但以 root 运行（本机就是）时永远不成立，单用户机器上用户自己的 wheel 目录也不成立——实际等于禁用本地 find-links；它也不覆盖已配置的索引（同样能触发），由本机 http 服务提供、服务目录可写的 URL 形式 find-links 也绕得过去。**c** 让 dry-run 在不带代理凭据的精简环境里跑。对本机内部代理可行：`10.20.16.126` 在 `NO_PROXY` 内、直连，dry-run 不需要代理变量（F74 的第一条命令就是不带代理跑通的）；但经本机代理访问 PyPI 时必须带 `HTTPS_PROXY`（含凭据），要自动判断就得重写 requests 的 `NO_PROXY` 匹配（含 CIDR）；来源 URL 里的凭据（`PIP_INDEX_URL` 的 userinfo）解析时无论如何都得带；而 `setup.py` 以同一用户运行，仍能从 `.env`、shell rc、agent 的 `/proc/<pid>/environ` 读到同一批凭据。**d1** 解析前扫描本地 find-links 目录里每个 wheel 的 `METADATA`（zip 读取，不执行代码），有 `Requires-Dist: … @ …` 即在任何子进程之前拒绝：约 20 行纯函数，堵住"往 find-links 目录写一个 wheel"这一条触发路径，但不覆盖已配置索引，R26 也照旧（放进目录的普通 wheel 本来就会在第 7.8/7.10 步执行）。**d2** 本工具起一个只放行已配置来源主机的本地过滤代理给 dry-run 用：与 Q32 推荐 a 冲突（若同时放行 `files.pythonhosted.org`，任何人都能往那里上传 sdist），实现量大，属于 §8 里"只放行索引主机的过滤代理"那一类。**d3** 先用 `--no-deps` 逐层遍历依赖、自行检查 `requires_dist` 再交 pip 正式解析：等于在 pip 之外另写一个解析器，选出的候选未必与 pip 一致，不可靠 | **a**（owner 若想多一道便宜的防线，可选 **a + d1**）：PyPI 来的包碰不到这条路径（F67）；要触发它，要么需要一个恶意的已配置来源——它本来就能交付 import 时执行的 wheel（R6），这里多出来的只是执行得更早、看得到 pip 环境——要么需要有人能写 find-links 目录（R26，放进去的普通 wheel 本来就会执行）。b 在本机模式（同一 uid、常以 root 运行）下落实不了；c 省不掉来源凭据，同一用户的代码本来就能从文件或 `/proc` 读到同一批凭据；d1 便宜但只堵一条窄路；d2、d3 代价与收益不成比例。**第 7.2 版注**（Q34）：来源沿用 pip 配置后，触发面从"已配置来源"变为"pip 能指向的任何来源"，而 pip 配置模型经 `bash` 就能改（R30）；这与模型直接 `bash pip install` 同一风险面，推荐仍为 **a**，卡片保留对应两行（§4.5 第 6 步） | 复核方要求补列（第 7 版定向复核重要 1）；审核方注明其上一轮实验 2 已测到而漏报 |


### 9.1 已裁定（owner 2026-09-24）

Q19–Q23 由 owner 2026-09-24 在对话中裁定，全部按推荐；其中 Q19 由 owner 明确确认。设计已按此写入正文（§4.2、§4.12、§5）。

另：**Q1、Q2、Q3、Q12、Q13、Q14、Q15、Q18** 由 owner 2026-09-24 在对话中裁定，**全部按 §9 表中"推荐"一栏**（P0b 与 P1 实施所需）。其余 Q4–Q10、Q16、Q17 属 P2/P3，仍待裁定，实施 P2/P3 前须先裁定。

**2026-09-25**：owner 在对话中裁定 **Q4–Q10、Q16、Q17、Q27、Q28、Q31、Q33 全部按 §9 表中"推荐"一栏**（Q33 取 a，不加 d1），并指示
**P2 与 P3 现在实施**，不再等 0057–0060 完成；P3 在未提交的 0056 工作树上实施。至此 P2、P3 已无待裁定问题。

**2026-09-26**：P2 实现评估发现 pip 的 `python` 选项（配置键 `python`、环境变量 `PIP_PYTHON`）会把安装转到另一个解释器，
可绕过"base 不变"。owner 裁定把 `python` 加入 §4.5 第 7.3 步安装位置守卫的键表（与 F93 同类：防本机 pip 配置让安装工具在审批之外
改动 base 并误报"未改动"；不防被带偏的 agent，后者可直接经 `bash` 安装）。§4.12 第 5 条（`PYTHONNOUSERSITE`）不在已批准范围内，不实施。

第 6 版：**Q24、Q25** 是 owner 2026-09-24 在对话中直接给出的两条裁定（不是先列为待裁定问题再选），"选项"一栏照录 owner 的原话，
设计已按此修订（§0.2 D7；§4.5、§4.6、§4.10、§6、§7、§8、Q10）。第 6 版新引出的 Q26–Q28、第 7 版新引出的 Q29–Q32 与第 7.1 版
新引出的 Q33 同属 P2，列在 §9 表末，仍待裁定。第 7 版对 Q25 的落实方式改为"来源本身写在 OmicsClaw 配置里"（Q29），不改变裁定的内容。 **第 7.2 版**：owner 2026-09-25 裁定 Q34（见表末），撤回 Q25 的落实方式。

| # | 问题 | 选项 | 推荐（= 裁定） | 裁定 |
|---|---|---|---|---|
| Q19 | **P1 与 0062 阶段二的时序**（第 4 版新增）。owner 定的是"0062 阶段一合入后先做 P0b 与 P1"，但 `DEPENDENCIES` 要到 0062 **阶段二**才存在（0062 §3.9 第一行） | a P1 在阶段一后开工，**合入等阶段二**；b P1 先读旧四份 `_lib/dependency_manager.py`，阶段二后改读 `_sdk/deps.py`；c P1 拆成 P1a（无 registry：包名行解析、探针、注记，所有名字走回落，git 类识别不出）先合入，P1b 在阶段二后接上 registry | **a**（owner 已明确确认：阶段一后开工、阶段二后合入、不写过渡代码）：b 要写一个只活几周、且与 D6"从 `_sdk/deps.py` 读"相悖的读取器；c 的 P1a 没有 registry，名字全走回落：P1 本身没有安装工具，所以害处不是"误装"，而是 `pybanksy` 会按回落规则以 import 名 `pybanksy` 探测（实际模块是 `banksy`），即使装了也报缺失；另外 git 类在注记里分不出来，一致性测试也要等阶段二后的调用形式。第 5 版按审核意见把第 4 版"误报成可装的 pip 缺项"的说法收回。阶段二可与 0057 并行（0062 §4），P1 开工后等待时间有限（R21） | owner 2026-09-24 裁定：按推荐 |
| Q20 | **不在 registry 里的声明名怎样推 import 名**（第 4 版新增）。0062 回落④设 `module` = 名字本身，对 `PyYAML`、`scikit-learn` 给出错误的 import 名（F64） | a 0061 的回落④用本侧规则（两项小表 + `-` 换 `_`），声明名的回落集合钉成冻结表（今天 16 个）；b 请 0062 把 16 个基础库也写进 `DEPENDENCIES`（改 0062 已定稿的"61 键"与用例 22）；c 照搬 0062 的回落，接受这两个名字在注记里永远误报缺失 | **a**：只影响 registry 之外的名字，①②③与 0062 完全一致；冻结表让"新增后端却忘了注册"在测试里变红，与 0062 对调用名的做法相同；b 让一张"可选后端"表混进 numpy、pandas，改动已定稿的计划；c 是已知缺陷 | owner 2026-09-24 裁定：按推荐 |
| Q21 | **`describe_environment` 回调是否仍需要**（第 4 版按 D6 重新论证） | a 保留，只在非冻结运行注入（本版写法）；b 删除，非冻结 trial 只留已有的 `provenance.python/location/image`，要查包版本时人工在同一解释器上跑 `use_skill` 注记或探针；c 保留并在冻结运行时也注入，把结果与冻结清单比对 | **a**：owner 已定非冻结场景仍在 trial 里记解释器与包版本；0056 的分层（F55）不许 `ensemble` import `skillenv`，要做到这一点只能由 entry 注入，所以回调仍然需要，只是作用范围缩小。代价小：一个可选参数、每试验约 50 ms。b 可行但排查"这次为什么没跑起来"时少了最直接的证据。c 等于在冻结运行里重新引入逐 trial 的环境比对，与 D6 否决的方向相同，而冻结期间的一致性已由"改动即新冻结"保证 | owner 2026-09-24 裁定：按推荐 |
| Q22 | **P3 的时点**（第 4 版新增；owner 只定了 P0b、P1、P2 的顺序） | a P1 与 0056 都合入后即做，"对 0059 的要求"在 0059 起草前交给其作者；b 与 P2 一起排在 0057–0060 之后；c 并入 0059 由其实施方一起做 | **a**：冻结清单的环境段要在 0059 设计时就定下来，否则 0059 可能另写一套探测；P3 的回调很小，**一律注入**（第 5 版，审核 I2），"冻结时不注入"由 0059 在引入冻结开关时实现，不干扰论文主线。若 owner 希望主线期间 `ensemble/` 完全不动，选 c，让 0059 的实施方在同一改动里加回调 | owner 2026-09-24 裁定：按推荐 |
| Q23 | **registry 不可读时的行为**（第 4 版新增） | a `probe` 降级（warning + 注记首行说明，名字全走回落）、`install` 拒绝启动；b 两种模式都拒绝启动；c 两种模式都降级 | **a**：`use_skill` 不应因为一个只用于注记的文件而不可用；而安装要靠 `kind` 挡住 git 类、靠 `also` 展开，读不出时宁可拒绝启动（与 Q6"Refused rather than defaulted"同一原则）。第 5 版补：`skills_dir` 指向没有 `_sdk/` 的自定义目录时按"文件不存在"处理，`install` 模式拒绝启动且报错写明"配置的 skills_dir 不是带 `_sdk/` 的 OmicsClaw skills 树"（§4.2，审核 m4）。0062 阶段二之后该文件由 0062 用例 22 守着，这条分支实际上只在开发中途出现 | owner 2026-09-24 裁定：按推荐 |
| Q24 | **安装是否借助哈希确保**（第 6 版） | owner 原话选项："安装不借助哈希确保（范围：只去掉安装校验，key 不变）" | —（owner 直接裁定） | owner 2026-09-24 裁定：去掉逐文件哈希校验——`--require-hashes`、"report 无哈希即失败"、需求文件里的 `--hash=sha256:…`，以及卡片、结果、`.meta.json`、日志中所有为哈希服务的字段和逻辑；相应的测试用例、§6.2 变异项、风险表条目、F50 在设计里的用法一并改掉或删除。overlay 的 key 保持现状：它是 base 全量发行包清单的指纹，只用来判断缓存能否复用，不属于安装校验。落到设计：§4.5 第 6、7.6、7.7、8 步，§4.6，Q10；逐条见 §10 第 6 版 |
| Q25 | **明文索引能否用于安装**（第 6 版） | owner 原话选项：明文索引"部署声明即信任" | —（owner 直接裁定） | owner 2026-09-24 裁定：只要部署在配置里显式列出某个索引主机，就允许从它安装，包括 http（比如本机内部代理 `http://10.20.16.126:8081` 加 `trusted-host`）；审批卡片上对明文源给出醒目的"明文源"提示；未声明的主机一律拒绝。落到设计：第 6 版为 §4.10 `skill_env_package_hosts`/`skill_env_package_dirs` 与来源比对；第 7 版改为来源本身写在 OmicsClaw 配置里（`skill_env_index_url` 等，§4.10；§4.5 第 5、6 步；Q29），R24。**第 7.2 版：被 Q34 撤回**——不再有"部署声明"这一层，来源沿用本机 pip 配置 |
| Q34 | **安装的包从哪来**（第 7.2 版，owner 在对话中追问"为什么不直接联网安装"后裁定） | a 沿用本机 pip 配置联网安装（与用户自己 `pip install` 相同），卡片写明"来源未经核对"；b 第 7、7.1 版的设计：来源、代理、证书只取 OmicsClaw 配置，不读 pip 配置 | —（协调方推荐 a：对单人本机部署，b 只堵住安装工具这一条路，模型仍可直接 `bash pip install --index-url <任意地址>`；b 的代价是六个配置项、一套文法、迁移说明与测试） | owner 2026-09-25 裁定：**a**。只改这一条，其余 P2 设计不变；Q25 的落实方式撤回，Q26、Q29、Q30、Q32 作废；为保住"base 不变"补安装位置守卫（F93）。落到设计：§0.2 D8；§4.5 第 5、6、7.3、7.6 步；§4.6；§4.10；§4.11；§5 P2；§6；§7 R5、R17、R19、R24、R26–R30；§8；§10 第 7.2 版。本版未送审核（owner 指示） |

---

## 10. 修订记录

**第一版（2026-09-24）**：初稿。事实表 F1–F42 经本人打开文件或运行命令核实；旧提案行号未沿用。发现旧提案两个前提
在新框架下不再成立（"单一接缝"、"默认静默安装"），以及旧实现的依赖集合来自 `requires:`（F2）而其内容已逐字保存在
`## Dependencies`（F20）。

**第 2 版（2026-09-24）**：依据独立审核（"有条件通过"，无阻断）修订，逐条见 §11。主要变化：缺省改为 `probe`、`packages`
必填、Desktop 不挂安装工具；探针 cwd 改为 skill 目录并先剔除 `''`；安装四步统一 `PYTHONNOUSERSITE=1`；拒绝 venv 作 base；只补缺
之外加哈希安装、过滤后 `pip check`、`--isolated` 与落盘核对，失败即回滚；P0 拆为 P0a/P0b，守卫测试改为"模块在盘上不存在即违例"
并排除 `skills/**/tests/`；Q 由 14 个调整为 18 个（新增安装来源、Desktop、`packages` 必填、ensemble 记录格式，沙箱三情形合并为
一问）；Q7、Q12、Q16 的推荐改为与审核方一致。新增事实 F43–F57，D 组逐条复跑（附录 A）；因复跑而变化的是 F32（uv 用时）、
F34（popv 可解析、遮蔽原因分类）、F39（sccoda/popv 结局）、F40（2066 passed）。

**第 3 版（2026-09-24）**：依据第 2 轮复核（"有条件通过"）修订，逐条见 §11"第 2 轮复核"。主要变化：约束检查改为装前装后两次 `pip check`
的差集（N-1）；pip 子进程改用 `PIP_CONFIG_FILE=/dev/null`、自建环境、0600 需求文件承载索引选项，读配置补齐键与优先级，显示与记录一律
去 userinfo（N-2）；锁移到 `<root>/.locks/`、锁内复查、key 纳入 base 的 mtime 与发行包哈希、有 fingerprint 的目录永不删除、
`finally` 回滚并杀进程组、锁内清理半成品（N-3）；Q3 推荐由 a 改为 b，一致性测试细到每个 skill（N-4）；Q6 推荐改为拒绝启动；探针在
skill 目录不存在时退回工作区；report 无哈希即失败；从 `RECORD` 查顶层名碰撞；`find_overlays` 只在本机模式。新增事实 F58–F63；更正
F48、F51、F57。Q 仍为 18 个，编号不变；推荐有变化的是 Q3、Q6，Q10 的"审核方"一栏已更正。

**第 4 版（2026-09-24）**：不是审核驱动，依据是 owner 2026-09-24 的裁定（记为 D6）与已定稿的计划 0062（第 2 版定稿，§0.2 D1/D7、
§3.4、§3.9）。只改三处，其余设计（P0b、P1 探测注记、P2 需审批的本机安装）不变：
1. **删除 P0a**。不建 `omicsclaw/core/child_env.py`；`core/` 断链、凭据剔除（改在 `bash` 本机路径与 `LocalExecutor`）、"import 不存在
   模块"守卫、`test_core_modules_import.py` 都归 0062 阶段一（0062 §3.9"P0a 的去向"）。改动：状态与前置、§0.3 结论与形态图、G1 删除、
   §3 的 `environment.py` 行、§4.8 残留表（`tests/test_adaptive_env_phase3.py` 的删除按 0062 Q12 移到 P0b；`FRAMEWORK-REBUILD.md`
   补记归 0062；`pyproject.toml` 注释移到 P1）、§5、§6 的主命令与用例 1–3（删除，编号保留）、§7 R14、Q11 与 Q12 的表述；F11–F14、
   F42、F43 加第 4 版注。
2. **registry 改从 `skills/_sdk/deps.py` 读**。AST/`ast.literal_eval` 读纯字面量 `DEPENDENCIES`（`module`/`kind`/`install`/`description`/
   可选 `alt_env`/可选 `also`），不 import `skills`（0062 D3、B4）；名字解析①②③照 0062 §3.4，回落④用本侧 import 名规则并以冻结表钉住
   （Q20）；类别取 `kind`（`non-pip` 改名 `r`），安装白名单内的名字展开为 `[键, *also]`，不解析 `install` 字符串；"两种字段名都读"、
   "从 `install_cmd` 推类别"作废。改动：§3 两行、§4.2 重写、§4.4 注记变体、§4.5 第 1–2 步、§4.6 两行、§4.11、用例 6（重写）、6b（新）、
   7、10、13、21、§6.2、§7 R20–R21；F22、F52、F58、F59 按 0062 合并后的状态加注，新增 F64（合并后对声明名的覆盖）。
3. **P3 的环境记录并入一次性冻结机制**。冻结运行的环境只写进 0059 的冻结清单 `bench/freezes/<name>.yaml`（一次、可读），trial 只记冻结名；
   owner 否决逐 trial 记内容哈希；非冻结运行仍在 `trial.json` 记解释器与包版本。改动：G7、§4.6 benchmark 段、§4.9、§4.10、§4.12（重写，
   新增"对 0059 的要求"）、§5 P3、用例 25（改）与 25b（新）、§7 R22、§8、Q16、Q17（重写）；`describe_environment` 重新论证为 Q21。

同时：行号按工作树重新核对（`FRAMEWORK-REBUILD.md` "Kept and importable" 由 :1861 漂到 :1896；`ensemble/runner.py` `run`/`_bind` 为
:327/:371，`trial_environment` 为 :463；`store.py` `check_run`/`bind_run` 为 :106/:125；`tools/README.md` 为 :17-18），未能稳定的改为按
符号名定位；§7 R5 里第 2 版遗留的"`--isolated` 杜绝配置改走安装位置"改为第 3 版的实际做法（勘误）。新增问题 Q19–Q23（P1 与 0062
阶段二的时序、回落规则、回调去留、P3 时点、registry 不可读时的行为）。docstring 规范条款不变。


**第 5 版（2026-09-24）**：依据两件事——①owner 2026-09-24 在对话中裁定 Q19–Q23 全部按推荐（Q19 明确确认：P1 在 0062 阶段一后开工、
阶段二后合入、不写读取旧 registry 的过渡代码），移入 §9.1；②第 4 版的独立审核（结论"有条件通过"，无阻断项），逐条处置如下。
设计的三处主改动（D6）不变；docstring 规范条款不变。

| 意见 | 处置 | 说明 |
|---|---|---|
| **I1** §4.8 与 Q16 写"死变量名可随 0062 阶段一一并删"，与 0062 §3.7"不改白名单"矛盾 | **采纳** | §4.8 该行改为"随 0056 终审或随 P3"两个选项；§9 的 Q16 标"已修正（见 I1）" |
| **I2** 冻结开关在 P3 时不存在，"冻结时不注入"落不了地 | **采纳，选"P3 一律注入"** | P3 总是注入 `describe_environment`；"冻结时不注入"与原用例 25b 移进 §4.12 对 0059 的第 5 条，由 0059 在引入冻结开关时实现。备选"P3 留一个默认恒真的谓词参数、由 0059 填"写在 §4.12 并说明不推荐的理由（0059 前无调用者，0059 本就要改 entry 装配）；用例 25b 改为"总是注入、argv 形式"；Q22 的对应文字同步 |
| **I3** 冻结只靠 tag 标识，未要求工作树与 tag 一致 | **采纳** | §4.12 对 0059 的第 1 条补"冻结运行时工作树必须与 tag 完全一致（干净检出）"，校验方式由 0059 决定 |
| **I4** §6.2 三条变异测不出来 | **采纳** | ①"类别改回从 install 推断"：用例 6 加 `kind`/`install` 矛盾夹具（`kind="pip"` + `Rscript …`；`kind="git"` + `pip install x`）。②"反查排到规范化之前"：用例 6 加歧义夹具，经纯函数 `resolve(name, entries)` 绕过读取器——读取器同时补上与 0062 相同的歧义禁令，所以合法 registry 上②③次序不可观察，测试 docstring 写明这一点，保留该变异以钉住文档次序。③"对 r 类做 find_spec"：从纯渲染的用例 10 改挂到用例 6 的"探针输入的构造"（`r` 类不进 `imports`） |
| **I5** §6 主命令含 P1 才有的 `tests/skillenv` | **采纳** | §6 改为按阶段列命令：P0b 一条不含 `tests/skillenv`、可立即运行；P1、P2、P3 各一条 |
| **m1** Q3 选项 a′ 的"28 个名字、install_cmd"与 §4.2 的"32 个、`[键,*also]`"不一致 | **采纳** | a′ 改为 32 个（0062 F29 规则，注明第 3 版口径为 28）、PyPI 名取 `[键, *also]`；Q3 标"部分吸收" |
| **m2** 对 0059 的第 3 条断言"冻结要求 sandbox_required=true"；第 2 条"不另写探测"过硬 | **采纳** | 第 3 条改为条件句；第 2 条降为建议、由 0059 决定 |
| **m3** `executor.capture` 收 argv，`probe_command` 产出 shell 字符串 | **采纳** | 新增 `probe_argv(python, imports, dists, skill_dir)`，以 `executor.python` 开头、不经 shell、与 `probe_command` 共用固定代码；§4.12 写明 cwd 与 env；用例 8、25b 覆盖 |
| **m4** `skills_dir` 可配置，自定义目录可能没有 `_sdk` | **采纳** | §4.2 写明按"文件不存在"处理：`probe` 降级，`install` 拒绝启动且报错说明"配置的 skills_dir 不是带 `_sdk/` 的 OmicsClaw skills 树"；Q23 同步（`AppConfig.skills_root`，`entry/config.py`:499-507） |
| **m5** `skillenv/deps.py` 与 `skills/_sdk/deps.py` 同名 | **采纳** | 改名 `skillenv/registry.py`，§4.11、§5 同步 |
| **m6** "0062 用例 6、7、14"与三个测试文件的对应关系不对 | **采纳** | 改为 `test_external_env.py`→0062 用例 6、`test_r_script_runner_environment.py`→用例 7、`test_r_script_runner.py` 在 0062 中无用例编号（阶段一第 5 步原样搬迁）；10 个 sc 脚本与既有 sc 测试对应用例 13、14（§5 P0a、§6.1 用例 1） |
| Q19 否决 c 的理由过头 | **采纳** | P1 没有安装工具；c 的实际害处是 `pybanksy` 按回落以 import 名 `pybanksy` 探测而误报缺失，已按此改写 |
| §9 标注 Q16 | **采纳** | 见 I1 |

另：状态行改为"第 5 版，待 owner 终审"；§5 的"每阶段跑 §6 主命令"改为"该阶段的命令"；R22 与 §6.2 里对 25b 的引用同步。

**第 6 版（2026-09-24）**：不是审核驱动，依据是 owner 2026-09-24 对话中的两条裁定——Q24"安装不借助哈希确保（范围：只去掉安装校验，
key 不变）"与 Q25 明文索引"部署声明即信任"（§9.1；§0.2 记为 D7）。P1 已由另一个会话按第 5 版实施，本版**只改 P2 的设计**；P0b、
P1、P3 与 docstring 规范条款不变。本版只做局部修改，没有整篇重写。

删改——与哈希有关的内容（Q24）：

| 位置 | 第 5 版 | 第 6 版 | 理由 |
|---|---|---|---|
| §0.3 形态图、G5 | "校验哈希" | "只从部署声明的主机或目录取包" | Q24、Q25 |
| §3 "`--no-deps` 安装"行 | "只补缺钉版本 + 哈希 + 约束检查"；"按 report 的哈希安装（F50）" | "只补缺钉版本 + 来源控制 + 约束检查"；安装 report 与计划比对（F67、F68） | Q24 |
| §4.5 第 6 步卡片 | "wheels only, hash-checked" | 删去 "hash-checked"；加明文源置顶告警、`[PLAINTEXT]`/`[TLS NOT VERIFIED]` 标注、"确切版本在批准后解析"一句 | Q24、Q25 |
| §4.5 第 7.6 步 | report 无 sha256 即失败，不退回无哈希安装 | 删；改为制品来源核对（拒绝直接 URL 与未声明来源） | Q24；F67 |
| §4.5 第 7.7 步 | 需求文件每行 `name==ver --hash=sha256:…`，`--require-hashes`（F50） | 每行只有 `name==ver`，加 `--report`，装完与计划逐项比对文件名与来源 | Q24；F68 |
| §4.5 第 8 步 | 失败原因含"无哈希、哈希不符" | 删；加"来源不在声明集合或是直接 URL""安装的文件与计划不符" | Q24 |
| §4.6 机制表"计划与安装之间制品被换" | `--require-hashes`，哈希取自 report；report 无哈希即失败 | 安装 report 比对 + 剩余风险 R23 | Q24 |
| §4.6 只补缺 | `install` 每项带 sha256；输出 `missing_hashes` | 删；每项改带 wheel 文件名与来源，输出 `foreign` | Q24 |
| §4.6 `.meta.json` | `installed_pins` | `installed` 逐项 `name`/`version`/`wheel`/`source`/`transport`，明写不含制品哈希 | Q24；owner 此前"否决逐 trial 内容哈希、偏好人可读审计"的立场（D6） |
| §5 P2 验收 | "哈希安装"；"哈希不符、report 无哈希都回滚" | 来源比对、文件比对、明文告警、验证环境、未声明即拒绝启动 | Q24、Q25 |
| §6.1 用例 15、18 | 用例 15"report 缺 sha256 的制品进 `missing_hashes`；需求文件每行带 `--hash`"；用例 18"篡改 wheel 使哈希不符 → 回滚" | 删；用例 15 改测 `foreign` 与文件名、需求文件无 `--hash`；用例 18 改测同版本新增 wheel 与直接 URL；用例 14 加"无制品哈希"断言 | Q24 |
| §6.2 | "去掉 `--require-hashes`""report 无哈希时退回无哈希安装" | 删；新增来源、文件比对、明文告警、验证环境等变异 | Q24 |
| §7 R5 | "按 report 哈希安装" | 来源控制；写明声明来源上的投毒不在拦截范围内 | Q24 |
| §9 Q10 | a 含 `--require-hashes`（report 无哈希即失败） | a 改为来源控制 + 文件比对，注明未再送审 | Q24 |
| F50、附录 A 的 F50 | 设计依据 | 标注"设计不再使用，只作历史证据" | Q24 |
| §11 | I-8 末句、第 2 轮次要 3 的哈希处置 | 加注"已被 Q24 取代"，原文保留 | 历史记录不改写 |
| 措辞 | key 里的"base 发行包哈希" | 统一改称"base 发行包清单摘要"（§3、§4.4、§4.5 第 2–3 步、§4.6、§4.11、用例 14/19、§6.2、R2），**内容与 key 的组成都不变**，只为与"安装校验"区分 | Q24 的范围说明 |

新增：

1. **来源控制取代内容校验**（Q25）：配置 `skill_env_package_hosts`、`skill_env_package_dirs`（§4.10，`_Option`，`OMICSCLAW_SKILL_ENV_PACKAGE_*`；
   名字不用 `index_hosts`，因为制品可能在索引之外的主机上，F66）；§4.5 第 5 步的有效来源计算（缺省 PyPI 补入、`install.`/`:env:`
   整体替换、多值按空白切分、相对路径与空来源拒绝，F65）与卡片前比对（http 须在 `trusted-host` 里，F66）；主机匹配规则与 pip
   `trusted-host` 一致（精确主机名、无子域名匹配、无端口 = 任意端口、不做 DNS，F69）；第 7.6 步的制品来源核对（F67）；第 4 步复用前
   核对 `.meta.json` 的来源仍被声明（撤回信任后不复用）；`install` 且未声明任何来源时拒绝启动（Q26 推荐）。
2. **版本钉死**：保留 dry-run → 只补缺 → `name==ver --no-deps --only-binary=:all:`；新增安装 report 与计划逐项比对（F68：`name==ver`
   钉不住文件）。剩余风险 R23 如实写出接受理由。
3. **人读的可复现记录**：`.meta.json` 逐项记 name、version、wheel 文件名、来源（去 userinfo）与传输方式，明文源可见；§4.6 新增
   "完整性、安全性与可复现各靠什么"对照表。
4. **装后子进程的环境**（§4.5 第 7.8、7.10 步）：自建小白名单、临时 HOME，不带代理变量与凭据（F70、F71）——补上调研报告指出的缺口。
   另更正一个前提：新代码第一次执行不在第 7.10 步的验证 import，而在第 7.8 步的装后 `pip check`（新 wheel 的 `.pth` 在 overlay
   解释器启动时执行，F73），所以两步都用这个环境；新装的 `.pth` 列在结果里。
5. **卡片**：明文源与不校验证书的源置顶告警；写明版本在批准后解析；时机不变（Q27 推荐）。
6. **调研报告的借鉴**：只取与安装流程直接相关、改动很小的两条的最小形式——失败结果附解析出的计划、装不上时提醒"不要静默换方法"
   （§4.5 第 8 步）；wheelhouse 与离线重建列为 Q28（推荐暂不做）；其余（落盘的 `install_plan`、注记里的 blocker 显式化、派生镜像与过滤代理、
   参考数据锁、强制 https）列入 §8 并注明出处。
7. 事实 F65–F73（附录 A 有命令）；风险 R23–R26；问题 Q26–Q28；模块 `skillenv/sources.py`；用例 15b、18b。

保留不变（与哈希无关的安装后检查与隔离）：`pip check` 前后差集、`RECORD` 落盘核对、顶层名碰撞、import 验证、只补缺、仅 wheel、
`PIP_CONFIG_FILE=/dev/null` 与 0600 需求文件、一律去 userinfo、锁与回滚、overlay 的 key。（第 7 版注：0600 需求文件已删除，见下。）

**第 7 版（2026-09-24）**：依据第 6 版的独立审核，结论"不通过"——用来取代哈希的来源控制实测有三条互相独立的绕过路径（B1–B3）。审核方
认可的部分不动：哈希清理、F73 与第 7.8、7.10 步的无凭据环境、Q26–Q28 的推荐、与 P1 的命名和分层一致性（`tests/skillenv` 203 passed）。
本版仍只改 P2，只做局部修改；P0b、P1、P3 与 docstring 规范条款不变。审核方的实测环境在 `/tmp/review0061v6`，其结论记为 F77–F82
（注明"审核方实测"）；本版自己的实测在 `/tmp/exp0061v6`、`/tmp/exp0061v7`（F74–F76、F83，F71 复跑）。

| 意见 | 处置 | 说明 |
|---|---|---|
| **B1** pip 配置值原样写进需求文件，一行可注入 `--no-binary :all:` 等选项，覆盖命令行的 `--only-binary`，sdist 在带凭据的环境里被构建 | **采纳（首选修法）** | 不读 pip 配置、不写需求文件：来源取自 OmicsClaw 配置、经 `PIP_*` 环境变量传入（环境变量的值不会被当作选项，F74），需求放在 argv 的 `--` 之后（F75）；所有来源值启动时严格文法校验。§4.5 第 5、7.3、7.7 步，§4.6 机制表，§4.10，用例 15b、18。事实 F77 |
| **B2** 检查器解析出的主机 ≠ pip 实际连接的主机（反斜杠、制表符、非 ASCII） | **采纳（首选修法）** | 不再有"从 pip 配置解析主机再比对"这一步；来源值本身按 §4.10 的文法校验，反斜杠、空白、非 ASCII、`%`、两个 `@`、`#`/`?`、以 `-` 开头一律拒绝，不做转义；被接受的值经 `urlsplit` 与 pip 的 `urllib3` 解析一致（原型实测 F83，用例 15b 钉住）。事实 F78 |
| **B3** pip 配置里的 `proxy` 整体替换字节，卡片与第 7.6 步都看不见 | **采纳（首选修法）** | 不读 pip 配置；代理只来自 `skill_env_proxy`（→ `PIP_PROXY`）或部署启动时给定的 `HTTP(S)_PROXY`/`NO_PROXY`，卡片写明用的是哪一个；代理能替换 http 来源的字节，作为部署信任的一部分写进 R24。§4.6 完整性表"包从哪来"一行改写。事实 F79 |
| B1–B3 的共同修法列成 Q 请 owner 确认 | **采纳** | Q29（推荐 a：只取 OmicsClaw 配置）；Q30（若保留读 pip 配置，`proxy`/`cert`/`client-cert` 如何处置，推荐拒绝）。影响、迁移、代理关系、注记与建议命令写在 §4.10 |
| **I1** 去掉 `--require-hashes` 后 pip 默认仍校验索引页的 `#sha256=` | **采纳** | 新增 F80（审核方实测）与 F76（report 分辨不出来源是否给了摘要）；R25 改写为"剩余风险是请求发给了未配置的主机，而不是字节被替换"；R23 的窗口写窄；§4.6 完整性表补上这条现成保护，并写明"不关它、不依赖它、不记录它"；是否记录列为 Q31（推荐不记录） |
| **I2** `--only-binary` 是命令行选项，需求文件里的 `--no-binary` 会覆盖它 | **采纳** | §4.5 第 7.3 步与 §4.6 机制表点明：不写需求文件、不带调用方的 `PIP_*` 是"只装 wheel"成立的前提 |
| **I3** "http 主机必须在 trusted-host 里，否则拒绝"会误拒 pip 自己认为安全的来源 | **采纳** | 删去该拒绝；trusted-host 由本工具按 http 来源生成（含带端口的形式），https 从不加；不设 `skill_env_trusted_hosts`。事实 F81 |
| **I4** 主机匹配要写明归一化规则 | **采纳** | 第 7 版不再做主机匹配，归一化规则移进 §4.10 文法（`ipaddress` 规范形式、小写、去尾点、拒绝 `%`），用于生成 trusted-host 与显示；用例 15b 补压缩与全写 IPv6、尾点、反斜杠、空白、两个 `@`、以 `-` 开头 |
| **I5** 复用前核对来源、否则拒绝，只会留下死 key | **采纳（整段删除）** | 删去 §4.5 第 4 步的核对、`.meta.json` 的 `declared_sources`、用例 19 的第 6 版断言与 §6.2 的对应变异 |
| **I6** P2 落地清单漏项；Q26 的检查放在 `build_skill_env` 会被显式 `tools=` 绕过 | **采纳** | §5 P2 加：`SkillEnvMode.INSTALL`、删 `_as_skill_env` 的拒绝分支、改写 `test_install_is_refused_until_it_exists`；Q26 与"额外索引须有主索引"放 `resolve_app_config`/`AppConfig`，registry 可读性留在 `build_skill_env`（§4.10 检查点，用例 23）；`"skillenv"` 加进 `REBUILT_PACKAGES`，skillenv 的环境变量由 entry 注入 |
| **m1** `PIP_PROXY` 不理会 `NO_PROXY` | **采纳** | §4.5 第 5 步与 §4.10 写明：未设 `skill_env_proxy` 时透传环境代理变量、requests 遵守 `NO_PROXY`（内部索引直连）；设了则不透传环境代理、所有主机都经它，卡片写明 |
| **m2** `pip config list` 的值是 Python repr | **随 Q29 a 消失** | 不再解析 `pip config list`；F65 加注只作背景 |
| **m3** F71 的证据命令没带 `LD_LIBRARY_PATH` | **采纳** | 带上复跑，结果相同（F71 第 7 版注，附录 A） |
| **m4** 第 7.6 步写明经不提供 PEP 658 的代理时下载整个 wheel | **采纳** | 已写入第 7.6 步 |
| **m5** `sources.py` 的职责补"来源值的文法校验" | **采纳** | §4.11 改写 |
| 审核方关于小白名单环境的实测 | **记入事实** | F82（审核方实测）：64 个 import 名在两种环境下结果一致，第 6 版回复里的顾虑消除 |

删掉的东西（计划因此变简单）：`IndexConfigReader` 与询问前的第二个子进程（`pip config list`）；pip 配置的解析、优先级与配置键溯源；
`effective_sources` 与"缺省 PyPI 补入"；`skill_env_package_hosts`/`skill_env_package_dirs` 与按声明集合的来源比对、主机与目录匹配规则；
"http 须已在 pip 的 trusted-host 里"的拒绝；制品 URL 的主机比对（待 Q32 确认）；`https-unverified` 与 `[TLS NOT VERIFIED]`；0600 需求文件
及其清理；复用前的来源核对与 `declared_sources`；`timeout`/`retries`/`keyring-provider` 的透传。用例 15b 从"pip 配置解析 + 主机匹配"
变成"文法 + 换算"，用例 21、22 各少一组断言。新增的只有：六个 `_Option`、一段文法、迁移对照、Q29–Q32、风险 R27–R28、事实 F74–F83。

问题的变化：Q10 选项 a 改写；Q26 补检查点；Q27、Q28 措辞跟随；新增 Q29（只取 OmicsClaw 配置，推荐是）、Q30（若保留读 pip 配置，
`proxy` 等怎么办，推荐拒绝）、Q31（记录"来源是否给了摘要"，推荐不记录）、Q32（制品主机是否也须配置，推荐不查、只拒绝直接 URL）。

**第 7.1 版（2026-09-24）**：依据第 7 版的定向复核，结论"有条件通过"：B1–B3 已用原攻击实测确认堵住，第 7 版与审核方意见不同的
三处（`--` 取代需求文件、http 来源自动加 trusted-host、不查制品主机）被认可。本版按 3 条重要、8 条次要意见做最后修订，全部采纳；
仍只改 P2、只做局部修改。审核方实测记为 F84–F89（F84、F86 本版在 `/tmp/exp0061v71` 复现），F90 为源码核对，F91 为本版的文法原型。

| 意见 | 处置 | 落在哪里 |
|---|---|---|
| **重要 1** dry-run 会构建依赖元数据里直接 URL 指向的 sdist，`setup.py` 看得到带凭据的 `HTTPS_PROXY`；第 7.6 步的拒绝在其后 | **采纳** | 三处表述如实改写：§4.6 机制表"安装期执行任意代码"一行（原"没有来源能覆盖它"）、§4.5 第 7.6 步（原"拒绝发生在安装之前"）、R25（原"直接 URL 仍一律拒绝"）；第 7.3 步同步说明 `--only-binary` 不约束直接 URL；新增 F84、R29、卡片上的两行说明（§4.5 第 6 步）、用例 18 (iii)、Q33（推荐 a，可选 a + d1） |
| **重要 2** argv 的 spec 可以是直接 URL，同样执行 `setup.py` | **采纳** | §4.5 第 7.3 步把 spec 文法收紧为"名字 + 可选 extras + 可选版本约束"，禁止 `@`、`;`、`:`、`/`、`\`、URL、名字后跟非运算符；新增 F85、F91（原型：仓库 62 个 spec 全部通过）；用例 15b 的 spec 文法组、用例 18 (ii)；§6.2 变异 |
| **重要 3** cwd 里的 `pip/__main__.py` 劫持 `python -m pip`，读到带凭据的 `PIP_INDEX_URL` | **采纳，并加 `-I`** | §4.5 第 7.3 步新增"子进程的启动方式"：第 7.2–7.10 步的每个子进程 cwd 为新建的空临时目录、解释器带 `-I`；实测 `-I` 不影响 `--system-site-packages`，`python -m venv` 同样可被劫持、同样被 `-I` 挡住（F86）；第 7.10 步引用它；用例 18 (i) |
| 次要：`transport` 取制品 URL 的 scheme；R25 的"而不是字节被替换"只在来源给了摘要时成立 | **采纳** | §4.6 `.meta.json` 的 `transport` 说明、R25 改写；新增 F88；用例 15 |
| 次要：自动加的 trusted-host 会让同一主机的 https 也不校验证书 | **采纳（一律带端口）** | §4.5 第 5 步：生成的 trusted-host 一律是 `host:port`（未写端口补 80），不要求部署写端口；R24；新增 F87；用例 15b |
| 次要：`.env` 以 `override=False` 加载，"受保护的配置"应为"启动环境" | **采纳** | 状态行、§4.5 第 5 步、§4.6 两张表、§4.10 迁移段、R24 改措辞；写明 shell rc 的 `export` 在下一次启动生效、不受权限层保护，这对所有 `_Option` 都一样；新增 F90 |
| 次要：`skillenv` 加进 `REBUILT_PACKAGES` 会因 `probe.py`:48 的 `sys.argv[1]` 立刻变红 | **采纳** | §4.10"环境变量的读取位置"与 §5 P2 清单：同一改动里在 `ENVIRONMENT_READERS` 登记 `skillenv/probe.py` 并写明理由 |
| 次要：base 或 overlay 的 `.pth`、`sitecustomize` 在 pip 进程里执行、读得到 `PIP_INDEX_URL` | **采纳** | 写进 R26；§4.5 第 7.3 步注明 `-I` 挡不住它；新增 F89 |
| 次要：文法原型补 `file://` 与绝对路径；端口归一；数字主机形式 | **采纳（数字主机一律拒绝）** | §4.10 文法：只接受 `file:///<绝对路径>`、拒绝 `.`/`..` 段、端口按整数归一、最后一段为数字或 `0x` 的主机只接受规范点分四段；pip 收到用归一化各部分重建的 URL；新增 F91；用例 15b |
| 次要：pip 子进程加 `PIP_NO_INPUT=1`、`PIP_DISABLE_PIP_VERSION_CHECK=1` | **采纳** | §4.5 第 7.3 步（另有 `stdin=DEVNULL`）；用例 15b、18 (iv) |
| 次要：路径存在性检查从 `resolve_app_config` 移到装配阶段 | **采纳** | §4.10 文法与检查点、§5 P2 清单：文法留在 `resolve_app_config`，路径存在性与 registry 可读性在 `build_skill_env`；用例 23 |

没有不采纳的项。问题的变化：新增 Q33（推荐 a；owner 若想多一道便宜的防线可选 a + d1）；Q32 的审核方一栏记为"认可"。

**第 7.2 版（2026-09-25）**：依据 owner 在对话中的裁定 Q34（§0.2 D8）：owner 追问"安装时直接联网装不就可以了吗，来源声明有没有必要"，
协调方说明来源声明只让安装工具这条路上的卡片不说谎、而模型仍可直接 `bash pip install --index-url <任意地址>`，对单人本机部署收益抵不上
代价；owner 同意改为**沿用本机 pip 配置联网安装**，并指示只改这一条、暂不派子 agent 修订与审核。本版由协调方直接修改，**未经独立审核**。

| 改了什么 | 落在哪里 |
|---|---|
| 来源、代理、证书、trusted-host 改由本机 pip 配置决定；本工具不跑 `pip config list` 取来源、不设 `PIP_CONFIG_FILE=/dev/null`、不换算 `PIP_INDEX_URL` 等 | §4.5 第 5 步（整段重写，第 7、7.1 版原文删除）；§0.3 形态图 |
| 卡片改为"按本机 pip 配置安装，来源未经 OmicsClaw 核对"，不再列来源清单、`[PLAINTEXT]` 首行与代理一行；明文与否改在结果里按制品 URL 逐项标注 | §4.5 第 6 步；用例 21 |
| pip 子进程环境：白名单 + agent 环境里的全部 `PIP_*` + `PYTHONNOUSERSITE`/`PIP_NO_INPUT`/`PIP_DISABLE_PIP_VERSION_CHECK`；白名单外的 `LLM_API_KEY`、`OMICSCLAW_*` 仍不带 | §4.5 第 7.3 步；§4.10 环境变量读取；用例 15b |
| **新增安装位置守卫**：`pip config list` 或 pip 环境里出现 `target`/`prefix`/`root`/`user`/`src` 键即在 dry-run 前拒绝（只看键名）。这是沿用 pip 配置的直接后果——实测这些键会把包装到 overlay 之外（F93），第 7 版靠 `PIP_CONFIG_FILE=/dev/null` 挡住，第 7.2 版不能再用 | §4.5 第 7.3 步；§4.6；§4.11；R19；用例 15b、18；§6.2 |
| 删除六个 `skill_env_*` 来源配置、来源文法、归一化、Q26 的启动拒绝、迁移对照 | §4.10；§4.11 `sources.py` 收窄；§5 P2 清单与验收；用例 23 |
| 实测确认"只装 wheel"在沿用 pip 配置后仍成立：命令行 `--only-binary=:all:` 胜过配置与环境里的 `no-binary`（F92） | §4.5 第 7.3 步；§4.6 机制表；用例 18 |
| 问题：Q34 记为已裁定（a）；Q25 的落实方式撤回；Q26、Q29、Q30、Q32 作废；Q10、Q27、Q33 按新来源改写措辞 | §9、§9.1 |
| 风险：R5、R17、R19、R24、R26 改写，R27、R28 作废，R29 触发面扩大为"pip 能指向的任何来源"，新增 R30（pip 配置不受保护，owner 接受） | §7 |
| 非目标：新增"锁定来源"（日后按需作为可选配置加回） | §8 |
| 测试：P2 用例的来源一律由夹具 pip.conf 提供；15b 收窄为守卫与 pip 环境；18 的第 7 版回归换成第 7.2 版回归（`no-binary` 无效、位置类键被拒）；21、22、23、24 删去来源配置相关断言 | §6.1、§6.2 |

未改：只补缺、钉版本、只装 wheel、spec 文法、`pip check` 前后差集、`RECORD` 落盘与顶层名核对、无凭据验证环境、锁与回滚、子进程临时
cwd 与 `-I`、直接 URL 拒绝安装、key 与 overlay 生命周期、审批姿态（Q5）、挂载矩阵与 Desktop 拒绝启动（Q6）。事实新增 F92、F93（附录 A）。

---

**第 7.2 版实现后对齐（2026-09-27，owner 指示）**：P2 实现与两轮评估中改动了四处，正文据此改写，设计意图不变。①第 7.3 步守卫：键表加入
`python`（2026-09-26 裁定，§9.1）；列配置时强制 `PIP_QUIET/GLOBAL/SITE/USER=0`，否则 `quiet` 或配置文件里的 `site/global = true` 能让
守卫看不全；键名与变量名按 pip 的规则规范化（含 `PIP___PREFIX`、`[:env:]` 段）。②第 7.4 步 before `pip check` 改用与第 8 步相同的
无凭据、无配置环境，使差集的前后条件一致。③第 7.9 步的落盘与遮蔽核对提前到第 8 步之前。④第 7.10 步随②改写。实现与证据见交付记录
"评估后修复"与"复核后修复"两节。

## 11. 审核意见处置表

| 意见 | 处置 | 说明 |
|---|---|---|
| I-1 守卫测试一建立就红；`_llm.py` | **采纳** | 核实（F43）。扫描排除 `skills/**/tests/`；判据改为"import 的 `omicsclaw.*` 模块在盘上不存在"，自动覆盖全部已删除的包（含 `providers`、`diagnostics`），不必维护名单；`_llm.py` 作为具名已知项、归 0058（§4.8、§5 P0a、用例 3）。另核实 `common/notebook_export.py`:302 在字符串模板里，AST 不会误报 |
| I-2 P0 并非无前置 | **采纳** | 拆为 P0a（独立）与 P0b（依赖 Q3、Q12–Q14）；P1 合入前退役说明不提新变量名（§4.8、§5） |
| I-3 Q13 (a) 违反 0056 分层；`bind_run` 首写 | **采纳** | 核实（F55）。改为 entry 注入 `describe_environment`（§4.12-2）；记录位置单列为 Q17，推荐写进每个试验的 `trial.json` |
| I-4 缺省 `install` 重新引入静默安装 | **采纳** | 核实（F25、F28）。缺省 `probe`（Q7）；`packages` 必填（Q8）；工具描述写"只装所选方法需要的包"；风险表新增 R6 对照 D3；另加 Desktop 收紧（Q6） |
| I-5 探针执行工作区代码、命名空间误报 | **采纳** | 实测复现（F45）。cwd = skill 目录，第一句剔除 `''`/`'.'`，再插入 skill 目录模拟真实 `sys.path[0]`；补两个测试（用例 8） |
| I-6 user site 不一致 | **采纳** | 核实 `ENABLE_USER_SITE=True`（F46）。安装工具四步统一 `PYTHONNOUSERSITE=1`；验证扩到该 skill 声明的全部 import 名；注记探针保持继承环境（反映真实运行），但单独标出来自 user site 的包（§4.3、§4.4） |
| I-7 base 为 venv 时 overlay 看不到 base 的包 | **采纳** | 实测复现（F47）。探针输出 `base_prefix`，`prefix != base_prefix` 即拒绝；补测试（用例 17） |
| I-8 保留的 base 版本未查约束；元数据重复；示例写错 | **部分采纳（换实现）** | 问题与示例错误都采纳（F48，§4.5 第 9 步已改）。约束检查不在纯函数里用 `requires_dist` 自行求值——那需要 PEP 508 标记与版本说明符求值器，skillenv 按分层只用标准库——改为装后跑 `pip check` 并只保留主语是新装发行包的违例，有违例即回滚（实测可行，F49）。重复与无名记录的处理已规定并补测试（§4.6、用例 15）。可选加固 `--require-hashes` **采纳为缺省**（实测，F50） |
| I-9 pip 子进程可把安装改到 overlay 之外 | **采纳（实现上更进一步）** | 实测 `PIP_TARGET` 生效、`--isolated` 可屏蔽但也会屏蔽内部索引（F51）。改为 `--isolated` + 显式传入从 `pip config list` 与少数环境变量读到的全部索引参数；不透传任何 `PIP_*`；卡片列出 index-url、extra-index-url、find-links、trusted-host 并对 extra-index-url 警示；装后核对 `RECORD` 落盘位置（§4.5 第 5–7 步）。比"读配置发现 target 就拒绝"更简单且不依赖枚举危险键 |
| I-10 安装来源漏报与契约 | **采纳** | 核实 `cellcharter` 漏报（F52）。新增 Q3；推荐白名单 = `## Dependencies` ∪ 本域 registry pip 类键，漏报补声明 + registry 引用一致性测试；格式契约只钉包名行（§4.2） |
| 次要 1 `use_skill` 非唯一路径 | **采纳** | 核实（F53）；§4.1 理由改写，§8 写明代价 |
| 次要 2 read-only 不附注记 | **采纳** | 核实（F24、F54）；第 1 版 Q1 附议的"仍附"撤回 |
| 次要 3 沙箱网络可配置 | **采纳** | 措辞按 `isolates_network`；有网沙箱并入 Q4 (ii) |
| 次要 4 降级理由偏弱 | **采纳** | 列为 Q4 (iii) 的选项；我的推荐改为"挂载，按本机处理"，理由写在 §4.6 |
| 次要 5 list/remove/clean 过度设计；复用第 3 支 | **部分采纳** | 删去 list/remove/clean，只留注记用的只读 `find_overlays`。复用第 3 支**保留 import 复验**，不只查遮蔽：base 哈希变化常见的原因是升级（如 numpy 1→2），会让 overlay 里的编译型 wheel 失效而不产生遮蔽；复验不联网、不问人，且只在哈希变化时发生 |
| 次要 6 F26 行为测试前提被打破 | **采纳** | §4.5 与用例 20 写明例外；夹具用假 `ProbeRunner` |
| 次要 7 装完后注记仍报缺项 | **采纳** | 注记经 `find_overlays` 指出现成 overlay（§4.4） |
| 次要 8 `OMICSCLAW_SKILL_PYTHON` 未定义且与 Q 选项同名 | **采纳** | 改为仅供测试的 `OMICSCLAW_TEST_BASE_PYTHON`，§6 写明 |
| 次要 9 `tests/` 残留盘点不全 | **采纳** | 扫描核实为 11 个（F44），§4.8 列出并注明不在范围 |
| 次要 10 App 仓库残留 | **采纳** | 在本机 App 检出中核实（F57）；§4.8 记为跨仓库残留；PATH 前置作为 Q15 证据 |
| 次要 11 事实更正 | **采纳** | F12 两个函数；F22 含 mygene、SpatialDE 按 PEP 503 规范化匹配到 `spatialde`（且其 `module_name` 是 `NaiveDE`）；F24 tmpfs 64g（另 pids 65536）；F11/G1 改为 94 个主脚本 80→90；F15 为 12 个叶子模块（5 可、7 不可）；§4.1 (c) 改引 0056 §0.2 第 2 条并注明 0056 待终审；README 行号改为 :56（沙箱段 :66） |
| 次要 12 Q7 证据主要来自坏元数据 | **采纳** | 复跑后分类：7 个遮蔽中 4 个只因坏元数据、3 个真实冲突（F34），写入 Q10 |
| 次要 13 `annotate` 只拿到 `Skill` | **采纳** | 签名改为 `(Skill, body)` |
| 缺失 Q (i) 能否成为安装来源 | **采纳** | Q3 |
| 缺失 Q (ii) Desktop 是否挂载 | **采纳** | Q6 |
| 缺失 Q (iii) 有网沙箱 | **采纳** | 并入 Q4 (ii) |
| 缺失 Q (iv) `packages` 必填 | **采纳** | Q8 |
| 未复现的 F32、F33、F35、F36、F38、F39、F40 | **已复跑** | 结果见 §2 D 组"第 2 版复跑结果"列，命令见附录 A。F33、F35、F36、F38 完全复现；F32 仅 uv 用时变化（0.12→0.05 s）；F39 的 `sccoda`、`popv` 结局变化；F40 变为 2066 passed（他人新增测试） |


> 第 4 版不是审核驱动（见 §10），本节无新增处置行。表中提到的 P0a、`test_no_deleted_package_imports.py`、用例 1–3 与"守卫测试"
> 均已由 0062 取代（§5 P0a）；I-1 与次要 8 的处置因此只作历史记录。

> 第 1 轮表中 I-8（约束检查的实现）、I-9（`--isolated`）与次要 5（复用第 3 支）的处置，已被下面第 2 轮的 N-1、N-2、N-3 取代。

> 第 6 版注：第 1 轮 I-8 末句（"`--require-hashes` 采纳为缺省"）与第 2 轮次要 3（"report 无 sha256 即明确失败"）的处置已被 owner 裁定
> Q24 取代，原文只作历史记录；现行做法见 §4.5 第 7.6–7.7 步。

### 第 2 轮复核（第 3 版）

复核结论"有条件通过"：I-1…I-7 已真正落实、P0a 模拟后守卫测试变绿；N-1…N-4 四条重要意见须改。四条都已在 `/tmp` 复现（F60–F62、F58–F59）。

| 意见 | 处置 | 说明 |
|---|---|---|
| N-1 `pip check` 只看主语是新装包会漏检；R16 理由错误 | **采纳** | 复现（F60：`corneto`/`cvxpy-base`）。改为装前装后两次 `pip check` 的差集，非空即回滚（§4.5 第 7.4、7.8 步），仍只用标准库；R16 改写并承认原说法错误；用例 16 加入 F60 夹具与一条真实 pip 版本。复用第 3 支已不存在（见 N-3：base 一变即新 key），所以"复用时也做前后比对"不再需要——差集只在安装时做 |
| N-2 `--isolated` 隔离范围说错；显式参数不全；凭据外泄 | **采纳（实现略有调整）** | 读源码并实测（F61）。pip 子进程设 `PIP_CONFIG_FILE=/dev/null` 关掉全部配置文件；读配置用 base 的 python、agent 的环境、不加 `--isolated`；补齐 `client-cert`、`proxy`、`keyring-provider`、`timeout`、`retries` 与两条优先级规则（§4.5 第 5 步）；卡片、结果、`.meta.json`、日志一律去 userinfo；`RECORD` 落盘核对保留；正文错误表述已改（F51 注、§3、§4.5）。**调整**：审核方建议 `PIP_CONFIG_FILE=/dev/null` 是"不透传 `PIP_*`"的唯一例外，但 `cert`/`client-cert`/`proxy`/`timeout`/`retries`/`keyring-provider` 不能写进需求文件（pip 只认索引类选项），放命令行会被 `ps` 看到，因此以**本工具自己解析出的值**写成 `PIP_CERT` 等六个环境变量传入（只有同一用户可读），仍不透传调用方环境里的任何 `PIP_*`；同时不再用 `--isolated`，因为它会让这六个变量失效 |
| N-3 回滚与锁非原子 | **采纳** | 复现锁文件 inode 问题（F62）。锁移到永不删除的 `<root>/.locks/<key>.lock`；锁内复查 fingerprint；key 纳入 base 的 mtime 与发行包哈希，base 一变即新 key，有 fingerprint 的目录永不被本工具删除；`try/finally` 覆盖取消，先杀 pip 进程组再删无 fingerprint 的目录；锁内清理半成品（§4.5 第 7–8 步、§4.6）；新增用例 19、20。"临时目录建好再 rename"不可行，已写明（§4.6） |
| N-4 Q3 推荐 a 扩大安装面、键名≠PyPI 名 | **采纳** | 复现规模与键名问题（F59）。Q3 推荐改为 b；一致性测试细到每个 skill（F58：排除共享预检模块后 8 个 skill、9 处漏报；模块粒度的误报进具名例外表）；审核方的收窄并集列为 Q3 的 a′ |
| 次要 1 Desktop 应拒绝启动而非降级 | **采纳** | 核实三个先例（§4.10）；Q6 推荐改为拒绝启动 |
| 次要 2 `sandbox_code_in_image` 时 skill 目录可能不存在 | **采纳** | cwd 一律给工作区、命令内 `cd <skill 目录> 2>/dev/null`；仅目录存在时插入 `sys.path`（§4.3、用例 9） |
| 次要 3 索引不给哈希时的回退 | **采纳** | 规则：report 无 sha256 即明确失败，不退回无哈希安装（§4.5 第 7.6 步）；没有采用"先 `pip download` 再从本地文件装"——那只保证本地文件与自己算的哈希一致，挡不住索引在计划前就给了错误制品，收益小于复杂度 |
| 次要 4 F57 盘点不全、后果写错 | **采纳** | 在本机 App 检出中核实 8 处调用与 `inconclusive`/401 行为（F57、§4.8）；"会误判"的说法已删 |
| 次要 5 F48 数字受 `sys.path` 影响 | **采纳，原因略有不同** | 核实：不设 `PYTHONPATH`、cwd 为 `/tmp` 时 541 条、533 个规范化名、4 个重名（无 omicsclaw 重复）；第 2 版的 542 条来自**在仓库根目录运行**（`sys.path[0]==''` 带进仓库里的 `omicsclaw.egg-info`），不是 `PYTHONPATH`——本机该变量未设。审核方数出的 534 与我的 533 相差 1，大概是规范化口径不同，未深究。规则已改为只列 `site.getsitepackages()`（§4.6、用例 14） |
| 次要 6 F26 例外说明不全 | **采纳** | 询问前的两个本机子进程（探针、`pip config list`）都做成可注入的，并写进测试 docstring（§4.5、用例 22） |
| 次要 7 沙箱下注记不应指向宿主 overlay | **采纳** | `find_overlays` 只在本机模式调用（§4.4、§4.6、用例 10） |
| 次要 8 守卫测试的"存在"判定 | **采纳** | 只认 `.py` 文件或带 `__init__.py` 的目录；核实 `omicsclaw/` 下没有命名空间子目录，不会误伤（§5 P0a） |
| 次要 9 顶层名碰撞 | **采纳** | 复现 palettable 的四个顶层命名空间目录（F63）；从 `RECORD` 求顶层名对照 base，模块或常规包碰撞即回滚，命名空间碰撞只报告（§4.5 第 7.9 步、用例 18） |
| 次要 10 复用第 3 支加前后比对 | **不再适用** | 同意其理由；但按 N-3 的修法 key 已包含 base 发行包哈希，base 一变就是新 key，"哈希变了仍复用"这一支已取消，前后比对只在安装时做（见 N-1 行） |
| §9 Q10 行"审核方"一栏 | **已更正** | 改为"前提是 N-1、N-2、N-3 都修好"，并说明第 2 版"I-7/8/9 已落实"不足以成立 |
| 对 Q 的异议 | 见 §9 | Q3 改推荐 b，另列 a′；Q6 改推荐拒绝启动；Q10 前提已满足并补 a‴ 作选项；Q4 (iii) 无异议 |

---

## 附录 A：复跑命令（全部在 `/tmp`，不写仓库）

```bash
R=/tmp/rerun0061; mkdir -p $R/wh; cd $R
B=/opt/conda/envs/OmicsClaw/bin/python; UV=/opt/conda/envs/OmicsClaw/bin/uv
# F32
time $B -m venv --system-site-packages v_pip; time $B -m venv --without-pip --system-site-packages v_nopip
time $UV venv -q --python $B --system-site-packages v_uv
readlink v_nopip/bin/python; grep '^home' v_nopip/pyvenv.cfg; PYTHONNOUSERSITE=1 v_nopip/bin/python -m pip --version
# wheelhouse（一次联网），之后 F33/F36 离线
PYTHONNOUSERSITE=1 $B -m pip download -q --no-deps --only-binary=:all: -d wh mygene==3.2.2 biothings_client==0.5.1 cnmf==1.7.1 palettable==3.3.3 six==1.16.0
# F33
$B -m venv --without-pip --system-site-packages v33
PYTHONNOUSERSITE=1 PIP_NO_INDEX=1 PIP_FIND_LINKS=$R/wh v33/bin/python -m pip install -q --no-deps mygene==3.2.2
PYTHONNOUSERSITE=1 v33/bin/python -c "import mygene"          # ModuleNotFoundError: biothings_client
# F36
$B -m venv --without-pip --system-site-packages v36
PYTHONNOUSERSITE=1 PIP_NO_INDEX=1 PIP_FIND_LINKS=$R/wh v36/bin/python -m pip install -q --no-deps --only-binary=:all: \
  cnmf==1.7.1 palettable==3.3.3 mygene==3.2.2 biothings_client==0.5.1
PYTHONNOUSERSITE=1 v36/bin/python -B -c "import cnmf, mygene"; $B -c "import cnmf"   # 后者失败
# F34（联网）
$B -m venv --without-pip --system-site-packages v35
PYTHONNOUSERSITE=1 v35/bin/python -m pip install -q --dry-run --only-binary=:all: --report rep_pertpy.json pertpy
# F35（联网，经内部索引）
UV_INDEX_URL=<pip.conf 的 index-url> UV_INSECURE_HOST=<trusted-host> $UV pip install --python v35/bin/python --dry-run mygene
# F38（rapids 为 base，离线）
/opt/conda/envs/rapids_singlecell/bin/python -m venv --without-pip --system-site-packages v38
PYTHONNOUSERSITE=1 PIP_NO_INDEX=1 PIP_FIND_LINKS=$R/wh v38/bin/python -m pip install -q --dry-run --only-binary=:all: --report - mygene
# F39（联网，每个 150 s 上限）
for p in simba-bio sccoda popv pyscenic; do PYTHONNOUSERSITE=1 timeout 150 $B -m pip install -q --dry-run --no-input --only-binary=:all: --report /dev/null $p; echo "$p rc=$?"; done
# F40
cd /workspace/dataset/private/zhouwg_data/OmicsClaw && PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest \
  -p no:cacheprovider -q -o addopts="" -p no:randomly tests/skills tests/tools tests/sandbox tests/permission tests/hooks \
  tests/entry/test_assembly.py tests/entry/test_permission_wiring.py tests/entry/test_open_app.py tests/entry/test_sandbox.py \
  tests/entry/test_entry_is_the_top_layer.py tests/test_env_example.py
# F45：/tmp/ws 里放 json.py（print 一行）与空目录 cellbender/，在 /tmp/ws 下：
#   python -B -c "import sys,json,importlib.util as u; print(u.find_spec('cellbender') is None)"        # json.py 被执行
#   python -B -c "import sys; sys.path[:]=[p for p in sys.path if p not in ('','.')]; import json,importlib.util as u; print(u.find_spec('cellbender') is None)"   # True，且不执行
# F47：$B -m venv --without-pip vbase; 装 mygene 进 vbase；vbase/bin/python -m venv --without-pip --system-site-packages vover
#   cat vover/pyvenv.cfg（home 指向 conda）；vover/bin/python -c "import mygene"（失败）
# F50：以 report 的 sha256 写 req.txt，pip --isolated install --no-deps --only-binary=:all: --require-hashes --no-index --find-links wh -r req.txt
#      （第 6 版起设计不再使用，Q24；只作历史证据）
# F51：PIP_TARGET=/tmp/x <overlay>/bin/python -m pip install --no-deps --no-index --find-links wh six==1.16.0  → 装到 /tmp/x
#      加 --isolated → 装进 overlay；pip config debug 显示配置来自 /root/.pip/pip.conf
# ---- 第 3 版新增 ----
# F60：在 /tmp 用 zipfile 造 cvxpy_base-0.0.1-py3-none-any.whl（METADATA 里 Name: cvxpy-base）
PIP_CONFIG_FILE=/dev/null PYTHONNOUSERSITE=1 vC/bin/python -m pip check > before.txt   # 14 行
PIP_CONFIG_FILE=/dev/null PYTHONNOUSERSITE=1 vC/bin/python -m pip install -q --no-deps --no-index --find-links fakewh cvxpy-base==0.0.1
PIP_CONFIG_FILE=/dev/null PYTHONNOUSERSITE=1 vC/bin/python -m pip check > after.txt    # 仍 14 行
grep -iE '^cvxpy[-_]base ' after.txt                                                   # 空：按主语过滤漏检
comm -13 <(sort before.txt) <(sort after.txt)                                          # corneto … cvxpy-base>=1.5.1, but you have 0.0.1
# F61：printf '[install]\ntarget = /tmp/rerun0061/tgt2\n' > envpip2.conf
PIP_CONFIG_FILE=$PWD/envpip2.conf vN/bin/python -m pip --isolated install -q --no-deps --no-index --find-links wh six==1.16.0  # 装进 tgt2
PIP_CONFIG_FILE=/dev/null vN/bin/python -m pip install -q --dry-run --no-deps --report - mygene     # 走 PyPI：用户 pip.conf 已失效
(umask 077; printf -- '--index-url <内部索引>\n--trusted-host <主机>\nmygene==3.2.2\n' > req_net.txt)
PIP_CONFIG_FILE=/dev/null vN/bin/python -m pip install -q --dry-run --no-deps --report - -r req_net.txt   # 走内部代理
PIP_TIMEOUT=33 PIP_INDEX_URL=https://u:secret@example.invalid/simple $B -m pip config list   # 显示 :env:.index-url='https://u:secret@…'
# F62：A 持锁 <key>/.lock；B 打开同一路径等锁；A rmtree <key>/ 后解锁；C 重建目录并加锁 → C 与 B 同时持锁（Python 脚本见交付记录）
# F63：for r in <overlay>/lib/python3.11/site-packages/*/RECORD; do cut -d, -f1 $r | cut -d/ -f1 | sort -u; done
# F58/F59：AST 扫描 skills/<domain>/_lib/dependency_manager.py 的 DEPENDENCY_REGISTRY 与各 skill 主脚本、其 import 的 _lib 模块里
#          require()/is_available() 字面量，对照 ## Dependencies（排除 skills/singlecell/_lib/preflight.py 前后各跑一次）
#          第 4 版：0062 阶段二合入后改为读 skills/_sdk/deps.py 的 DEPENDENCIES，调用名按 0062 F29 的 AST 规则收集（0062 附录 A dep_names.py）
# ---- 第 4 版新增 ----
# F64（cover.py，只读，从仓库根运行）：AST 读 4 个旧 DEPENDENCY_REGISTRY，按 PEP 503 规范化键取并集并去掉 mzmine（模拟 0062 §3.4 的
#      合并，得 61 键）；正则取 94 个 SKILL.md 的 ## Dependencies 包名行；对每个声明名按 键精确 → 规范化键 → module 反查 → 回落 分类，
#      打印回落集合（16 个）与 git/r/also 条目是否被声明。0062 阶段二合入后改为直接 ast.literal_eval skills/_sdk/deps.py 的 DEPENDENCIES
# F48：cd /tmp && env -u PYTHONPATH PYTHONNOUSERSITE=1 $B -B -c "import importlib.metadata as m, site; print(len(list(m.distributions(path=site.getsitepackages()))))"   # 541
# ---- 第 6 版新增（目录 /tmp/exp0061v6；tools/mkwheel.py 用 zipfile 造最小纯 Python wheel：OUTDIR NAME VERSION [--build N] [--requires SPEC] [--module-code CODE]）----
NOPROXY="env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy"
E="env -i PATH=/usr/bin:/bin HOME=/tmp/exp0061v6/h0 PYTHONNOUSERSITE=1 PIP_CONFIG_FILE=/dev/null"
# F65：h1/.config/pip/pip.conf = [global] index-url=https://u:secret@idx.example.com:8443/simple；extra-index-url 两行（https://a…、http://b…:8081）；
#      find-links=/data/wheels file:///srv/wh；trusted-host=b.example.org；[install] extra-index-url=https://inst.example.net/simple、no-index=false
HOME=$PWD/h1 $B -m pip config list                                   # 多行值带前导 \n；userinfo 原样
HOME=$PWD/h1 PIP_EXTRA_INDEX_URL="https://e1.example/simple https://e2.example/simple" PIP_FIND_LINKS="/opt/w1 /opt/w2" PIP_NO_INDEX=1 $B -m pip config list
$NOPROXY HOME=$PWD/h1 $B -m pip install --dry-run --no-deps --retries 0 --timeout 1 -v ocnonexistpkg 2>&1 | grep 'Looking in'
#      依次加 PIP_EXTRA_INDEX_URL=…、PIP_NO_INDEX=1、PIP_CONFIG_FILE=/dev/null 重跑：install. 取代 global.；:env: 取代两者；
#      no-index 只剩 links；什么都没配时不打印 "Looking in indexes"（缺省 PyPI）
# F66：$NOPROXY HOME=/nonexist PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=http://10.20.16.126:8081/repository/pypi-proxy/simple \
#        $B -m pip install --dry-run --no-deps six==1.16.0            # "not a trusted or secure host and is being ignored"
#      同上加 PIP_TRUSTED_HOST=10.20.16.126 --report rep_six.json      # url 在代理主机上；"Downloading …whl (11 kB)"（整个 wheel）
#      HOME=/nonexist PIP_CONFIG_FILE=/dev/null $B -m pip install --dry-run --no-deps --report rep_pypi.json six==1.16.0   # files.pythonhosted.org；只下 .metadata
#      srv/ 下用 python -m http.server 18765 提供 simple/oc-dep/index.html；需求文件 --index-url http://u:tok@127.0.0.1:18765/simple
#        + --trusted-host 127.0.0.1 + oc-dep==1.0，在新建 overlay 里 $E …/python -m pip install --dry-run --report → url 不带 userinfo
# F67：mkwheel.py wh2 oc-evil 1.0 --requires "oc-far @ http://127.0.0.1:18766/oc_far-1.0-py3-none-any.whl"；far/ 在 :18766 提供 oc-far
#      $E ov2/bin/python -m pip install -q --dry-run --only-binary=:all: --report rep.json -r req（--no-index --find-links wh2，或 --index-url :18765）
#      → report 含 oc-far，is_direct=true，url 为 :18766
# F68：mkwheel.py wh oc-leaf 1.0 --requires "oc-dep>=1"; mkwheel.py wh oc-dep 1.0；dry-run 计划 oc_dep-1.0-py3-none-any.whl
#      mkwheel.py wh oc-dep 1.0 --build 1 --module-code 'VALUE = 666'
#      $E ov1/bin/python -m pip install -q --no-deps --only-binary=:all: --report rep_inst.json -r req（--no-index --find-links wh，oc-dep==1.0、oc-leaf==1.0）
#      → rep_inst.json 里是 oc_dep-1.0-1-py3-none-any.whl；ov1/bin/python -c "import oc_dep; print(oc_dep.VALUE)"   # 666
# F69：tools/redir.py 在 :18767 提供 simple/oc-far/，把 /files/* 302 到 :18766；安装 oc-far==1.0 并 --report
#      → report 的 url 是 :18767 的链接，:18766 的访问日志有 GET；trusted-host 规则见 pip/_internal/network/session.py is_secure_origin
# F71：T=$(mktemp -d); cd $T && env -i PATH=/usr/bin:/bin HOME=$T TMPDIR=$T LANG=C.UTF-8 PYTHONNOUSERSITE=1 <overlay>/bin/python -B -c \
#        "import sys; sys.path[:]=[p for p in sys.path if p not in ('','.')]; import scanpy, anndata, numba, matplotlib, squidpy, os; print(sorted(os.environ))"
#      ls -A $T   # .cache .config
#      第 7 版复跑（m3）：在 env -i 里加 LD_LIBRARY_PATH="$LD_LIBRARY_PATH"，结果相同（5 s，8 个变量）
# F72：du -sk /tmp/rerun0061/wh /tmp/rerun0061/v36/lib/python3.11/site-packages; du -sh ~/.cache/pip
# F73：tools/mkpthwheel.py whp（wheel 里带 oc_pth_hook.pth，启动时把环境变量名写进 /tmp/exp0061v6/pth_ran.txt）
$E PIP_PROXY=http://u:tok@proxy.invalid:1 ov5/bin/python -m pip install -q --no-deps --no-index --find-links whp oc-pth==1.0   # 标记文件不出现
$E PIP_PROXY=http://u:tok@proxy.invalid:1 ov5/bin/python -m pip check; cat pth_ran.txt   # 出现，含 PIP_PROXY
# ---- 第 7 版新增（/tmp/exp0061v6 的 ov7；$base = env -i PATH=/usr/bin:/bin HOME=/tmp/exp0061v6/h0 PYTHONNOUSERSITE=1 PIP_CONFIG_FILE=/dev/null）----
# F74：$base PIP_INDEX_URL=http://10.20.16.126:8081/repository/pypi-proxy/simple PIP_TRUSTED_HOST=10.20.16.126:8081 \
#        ov7/bin/python -m pip install -q --dry-run --no-deps --only-binary=:all: --report r7a.json -r req7.txt   # six 经内部代理解析
#      $base PIP_INDEX_URL="http://127.0.0.1:9/simple --no-binary :all:" ov7/bin/python -m pip install --dry-run -v … | grep 'Looking in'
#        → "Looking in indexes: http://127.0.0.1:9/simple --no-binary :all:"（一个 URL）
#      $base PIP_NO_INDEX=1 PIP_FIND_LINKS="/tmp/exp0061v6/wh /tmp/exp0061v6/wh2" … -v oc-evil   # 两个目录都看
#      $base PIP_NO_INDEX=1 PIP_FIND_LINKS="/tmp/exp0061v6/wh --no-binary=:all:" … -v oc-leaf     # 后者被当作位置并忽略
#      $base PIP_INDEX_URL=http://127.0.0.1:9/simple PIP_EXTRA_INDEX_URL="http://127.0.0.1:8/simple --no-binary :all:" … -v   # 三个"索引"
# F75：$base PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/exp0061v6/wh ov7/bin/python -m pip install --dry-run --no-deps --only-binary=:all: -- oc-leaf==1.0 oc-dep==1.0
#      同上把需求换成 -- --no-binary=:all: oc-leaf==1.0   # "= is not a valid operator"
# F76：curl -s http://10.20.16.126:8081/repository/pypi-proxy/simple/six/ | grep -o 'six-1.16.0-py2.py3-none-any.whl#sha256=[0-9a-f]*'
#      sed -n 632,652p <pip>/_internal/operations/prepare.py
# F83：/opt/conda/envs/OmicsClaw/bin/python /tmp/exp0061v7/grammar.py   # §4.10 文法的原型：20 个值，10 个分歧值被拒，接受者两种解析一致
# F77–F82：审核方的实测环境、wheel、日志与脚本在 /tmp/review0061v6（tools/evilproxy.py、evilindex2.py、redir.py、evil3.py、imp.sh、imp_r.sh 等）
# ---- 第 7.1 版新增（/tmp/exp0061v71；F85、F87–F89 为审核方实测，环境在 /tmp/review0061v6）----
# F84 复现：srv/ 放 oc_far-1.0.tar.gz（取自 /tmp/review0061v6/wh_sd，setup.py 改为写 /tmp/exp0061v71/SDIST_RAN.txt）并以 http.server 18810 提供；
#      fl/ 放 setuptools wheel 与 mkwheel.py 造的 oc-near（Requires-Dist: oc-far @ http://127.0.0.1:18810/oc_far-1.0.tar.gz）
#      cd $(mktemp -d) && env -i PATH=/usr/bin:/bin HOME=/tmp/exp0061v71 PYTHONNOUSERSITE=1 PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 \
#        PIP_FIND_LINKS=/tmp/exp0061v71/fl HTTPS_PROXY=http://u:tok@127.0.0.1:9 NO_PROXY=127.0.0.1 PIP_NO_INPUT=1 \
#        /tmp/exp0061v71/ov/bin/python -I -m pip install -q --dry-run --only-binary=:all: --report rep.json -- oc-near
#      cat /tmp/exp0061v71/SDIST_RAN.txt   # "ran with env keys: HTTPS_PROXY,NO_PROXY,PIP_BUILD_TRACKER,PIP_CONFIG_FILE,…"；report 中 oc-far is_direct=True
# F86 复现：/tmp/exp0061v71/hij/ 下放 pip/__main__.py（写出 PIP_INDEX_URL）与 venv/__main__.py；在该目录下
#      env -i PATH=… PIP_INDEX_URL=http://u:tok@x/simple ov/bin/python -m pip --version      # 劫持生效
#      同上加 -I                                                                              # 执行真正的 pip
#      env -i PATH=… PYTHONPATH=<hij> ov/bin/python -I -c "import scanpy, sys; print(scanpy.__version__, sys.flags.isolated)"   # 1.11.5 1
#      <base>/bin/python -m venv --help → "HIJACKED venv"；加 -I → 正常的 usage
# F90：sed -n 195,202p omicsclaw/launch/__init__.py；sed -n 120,128p omicsclaw/common/runtime_env.py
# F91：/opt/conda/envs/OmicsClaw/bin/python /tmp/exp0061v71/grammar2.py   # file://、路径、端口与数字主机、spec 文法、pyproject 62 个 spec
# ---- 第 7.2 版新增（/tmp/v72check；OmicsClaw 环境的 python 记为 $B=/opt/conda/envs/OmicsClaw/bin/python）
# F92：find-links 目录 fl/ 里只有 ocsd-1.0.tar.gz；pip.conf = [global] no-binary=:all: / find-links=fl / no-index=true
#      PIP_CONFIG_FILE=pip.conf $B -m pip install --dry-run --no-deps ocsd==1.0                      # 去构建 sdist
#      PIP_CONFIG_FILE=pip.conf $B -m pip install --dry-run --no-deps --only-binary=:all: ocsd==1.0  # No matching distribution
#      PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 PIP_FIND_LINKS=fl PIP_NO_BINARY=:all: $B -m pip install --dry-run --no-deps --only-binary=:all: ocsd==1.0  # 同上
# F93：$B -m venv --without-pip --system-site-packages ov；whl/ 里有 ocsd-1.0-py3-none-any.whl；loc.conf = [install] <键> = <值>
#      for k in target prefix root user: PIP_CONFIG_FILE=loc.conf PYTHONNOUSERSITE=1 ov/bin/python -I -m pip install -q --no-index \
#          --find-links whl --no-deps --only-binary=:all: ocsd==1.0
#      # target/prefix/root：包落在 out/ 下、overlay 里没有，退出码 0；user：pip 拒绝
#      PIP_CONFIG_FILE=loc.conf $B -m pip config list   # install.user='true'（"节.键"形式）
#      grep -n "sys.prefix" $B 的 pip/_internal/configuration.py   # :75 site 级配置 = sys.prefix/pip.conf
```
