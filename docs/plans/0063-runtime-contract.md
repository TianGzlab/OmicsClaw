# 计划 0063 — 运行时契约 `OMICSCLAW.md`：拆分 `CLAUDE.md`，并入 `SOUL.md`

**状态**：第 3 版（2026-09-27），**已实施（2026-09-27），见交付记录 [`0063-runtime-contract-delivery.md`](0063-runtime-contract-delivery.md)**。Q1–Q8 全部按推荐项执行，裁定记录见 §14.1。

**外部前置**：0057 的会话要在 `docs/plans/0057-validation/run_arms.py` 里给 A3 设 `system_prompt_files=(<空文件>,)`，钉住它的前置段（Q8 = b）。本计划不修改 0057 的文件，只把这一条记为前置，由 §12.2 第 6 步检查。

### 第 3 版修订说明

- **记录裁定**：owner 在 2026-09-27 的对话中裁定 Q1–Q8 全部按推荐项执行，即 Q1=a、Q2=a、Q3=b、Q4=a、Q5=a、Q6=a、Q7=a、Q8=b。§14 新增裁定记录（§14.1），正文里的分支按裁定收敛：
  - Q3 = b：删去补充段的设计（原 §5.2），只留一句否决理由；
  - 删去矩阵中"补充段"一列、§7.1 的追加说明、§8.2 为 a 准备的 4 个用例。
- **写入 Q8 = b 的后续**：
  - 外部前置（见文首）；
  - 时间约束：本计划对 `omicsclaw/entry/**` 的全部改动须在 0057 写出 `freeze.json` 之前完成；
  - §12.2 新增第 6 步，实施前检查两个条件，任一不满足就停下、报告 owner。
- **更正 OmicsClaw-App 的部署形态**，涉及 F22、§5.3、R9、Q2（经 App 源码复查）：
  - App 的后端进程以 `OMICSCLAW_DIR`（检出目录）为 cwd，而且不设 `OMICSCLAW_WORKSPACE`。所以接上新后端时，workspace 取 cwd 的缺省值，情形为 **M1**，契约与 skill 都能拿到；没有配置 `OMICSCLAW_DIR` 时，cwd 是用户主目录，情形为 M3。
  - 第 2 版说的"App 只设 workspace、落到 M3"这条路径目前不存在：新后端没有 `/workspace` 路由，App 无法把 workspace 传过去。
  - App 在新后端上切换项目本就不可用，这是 App 接入层面的已知缺口，不属于本计划。
  - "App 实际如何启动新后端"已从未核实清单中移出。

### 第 2 版修订说明

第 1 版经独立审核，结论为"需小修"：阻断 2 条、重要 5 条、次要 9 条。本版改动如下：

- **B1，与 0057 相交。**第 1 版说"与 0057 不相交"，这是错的。0057 的 A3 驱动就是本计划的 M2 部署，而 0057 的冻结范围覆盖 `omicsclaw/entry/**`。本版：
  - 在 §0.2 更正这一判断；
  - 新增 F19、R12；
  - 新增 **Q8**，由 owner 与 0057 的会话共同裁定，须先于实施；
  - 确认至少已有一次 A3 开发运行，见 F19。
- **B2，回退会撤掉别人的工作。**§12 整体重写：
  - 阶段 0 用 `git stash create` 和仓库外、`/tmp` 以外的逐文件副本记下基线；
  - 补丁和回退只针对逐阶段列出的具体文件；
  - `SOUL.md` 回退后是改动前工作树里的版本。
- **I1，"原样"迁移的正文里有现时为假的事实。**新增 §3.3"事实修正"，共 4 条：
  - C8 的 HTML 标记；
  - C9 的脚本路径规则；
  - C9 第 3 步"`--help` 对所有脚本都能用"；
  - C3 的 "fully functional"。

  每条给出无论 owner 如何裁定 4 个 consensus skill 都成立的最小改法，并写明与该裁定的依赖（R13）。
- **I2，免责声明的来源。**D4 改为断言 `skills._sdk.report.DISCLAIMER in SAFETY_RULES`。已核实：skills 下 86 个文件导入 `skills._sdk.report`，导入 `omicsclaw.common.report` 的是 0 个（F21）。
- **I3，非逐字改动。**新增 §3.4"非逐字改动总表"，并与附录 B 的豁免项一一对应。另外三处调整：
  - S4、S7 从"删除"改为"保留"，因为删掉会丢失 "Scientific"、"non-trivial" 的限定；它们的去重移到 O11，`SOUL.md` 的规则编号因此不变；
  - C20、C25 沿用原文的 `### Desktop`、`### Channel — IM bots` 标题，不再另加衔接标签；
  - 估算从约 2,136 改为约 2,206 token。
- **I4，Q2 的论证。**Q2 补上四点：
  - 锚点改用"代码位置"时，测试与 golden 失去隔离；
  - `.env` 的定位方式不宜借用；
  - 只有一个开关；
  - App、channel、0057 A3 各自的实际行为（§5.3）。

  同时写明零代码做法：在仓库 `.env` 设 `OMICSCLAW_SKILLS_DIR`。另改两处：`.env.example` 的拟用措辞，原先写的 "(the checkout root)" 在 M3 下不对；R3 改写为 M2 下 `read_file` 读不到 workspace 外的文件。
- **I5，上线顺序。**改为先停长驻进程，全部验证完再启动，消除降级窗口（§12）。
- **Q3、Q4 的推荐。**
  - Q3 改为推荐 **b（不做补充文件）**，理由是简单，不是安全。这偏离交接基线，记为 D9；当时保留了 a 的完整设计作为备选（第 3 版按裁定已删除）。
  - Q4 仍推荐 a。审核认为至少要删掉 "fully functional"，这一点已作为事实修正 FX4 并入主体。
- **次要项**：
  - §6 补上"agent 自己写契约文件"和 `memory_write` 两行，记忆一行改指 `MEMORY.md` 精简版；
  - 新增 O9–O11；
  - 新 `CLAUDE.md` 指针的第二个分支换成"增删 skill"；
  - §9.3 补上 `context-engineering.md:14, 313, 340` 三处；
  - `default_sections` 的 docstring 改为不写段数；
  - 阶段 0 的测试命令去掉尚不存在的新测试文件；
  - 新增 D8（第三人称指针对交接方案的偏离）；
  - 新增相对 `skills_dir` 用例和"契约不含开发内容"的长期守卫用例；
  - `.env.example` 第 11 节的 `FEISHU_BOT_OPEN_ID` 一并改为 Required。

---

**前置**：
- **Q8 已裁定为 b**，由此产生两条约束：
  - 外部前置：0057 的会话在 `run_arms.py` 里钉住 A3 的前置段（见文首）；
  - 时间约束：本计划对 `omicsclaw/entry/**` 的全部改动（阶段 1、2）须在 0057 写出 `freeze.json` 之前完成。

  两条都由 §12.2 第 6 步在实施前检查。
- 本计划不修改 0057 的任何文件：`docs/plans/0057-*`、`docs/plans/0057-validation/`、`omicsclaw/ensemble/tuning/`。
- 工作树里有大量未提交改动，其中 `CLAUDE.md`、`SOUL.md`、`AGENTS.md`、`README.md`、`omicsclaw/entry/assembly.py` 都已被改过。实施时改任何文件前都要重新读取，并按 §12 先记下基线。

**给实现者的硬要求（注释约定）**：新写或改写的函数、类、模块 docstring 只写：
- 是什么、做什么；
- 参数、返回值、会抛什么；
- 会改变调用方式的行为，例如"文件不存在时该段不出现"。

计划编号、裁定过程、与旧实现的对照、实测 token 数都不写进生产代码，放进本计划、交付记录或测试 docstring。仓库里旧文件注释密度很高，这不能拿来当反例。

**测试**：解释器用 `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`，默认的 `python` 没有 pytest。**只跑 §11 列出的相关测试，不跑全量。**

已知与本改动无关的既有失败：
- `tests/tools/test_workspace.py`；
- `tests/test_control_plane_documentation_contract.py`；
- `tests/skillenv/test_install_wiring.py::test_with_run_skill_the_tool_comes_after_it`；
- `tests/entry/test_turn.py::test_the_system_message_survives_a_successful_summarization`：2026-09-27 在未改动的工作树上单独运行也失败，压力档位是 `EMERGENCY`，测试期望 `FULL`。它对系统提示与工具表的大小敏感（F13）。

---

## 0. 缘起与结论先行

### 0.1 缘起

**`CLAUDE.md` 同时服务两类读者。**
- 对 Claude Code 开发会话，它是自动加载的仓库指令。
- 对 OmicsClaw 运行时，它是 `DEFAULT_CONTRACT_FILE`，每轮作为 "## Project contract" 段注入系统提示。

**两类读者互相污染。**
- 分析 agent 每轮读到约 1,600 token 的开发与运维内容，例如"用 gh 建 issue""改 README""pip install 附加组件"。
- Claude Code 开发会话则读到第一行 "You are **OmicsClaw**"，被注入了产品人设。本计划起草所在的会话里，系统提醒注入的 `CLAUDE.md` 正文就以这句话开头。

**`SOUL.md` 又和 `CLAUDE.md` 重复。**身份句、"答案须可追溯"、"找 skill 并遵循 SKILL.md"都写了两遍。安全规则也有两份：`CLAUDE.md` 一份，常量 `SAFETY_RULES` 一份，两份措辞不同，却同时进入提示。

**本计划的做法**：把运行时内容收成一个文件 `OMICSCLAW.md`，`CLAUDE.md` 只留给开发会话，`SOUL.md` 删除。审计报告 `/tmp/prompt-audit/REPORT.md` 的 core-M8 就是这一条，当时留待本次重写一并处理。

### 0.2 与设计基线的差异，以及第 1 版自身的更正

设计基线是 `/tmp/omicsclaw-handoff-2026-09-27.md` §2.2 的方案，owner 已基本认可。本计划沿用它，核实后有以下修正或补充：

| # | 交接方案的说法 | 核实结果 | 本计划的处理 |
|---|---|---|---|
| D1 | 按 `config.repo_root()` 定位后，"在数据目录里运行时，agent 将始终拿到产品契约" | **只在设了 `OMICSCLAW_SKILLS_DIR`（或 `--skills-dir`）时成立。**`repo_root()` 等于 `skills_root().parent`，而 `skills_root()` 缺省为 `<workspace>/skills`（`entry/config.py:578-585, 616-618`）。所以没设 skills_dir 时 `repo_root() == workspace`，数据目录下读不到仓库契约，也扫不到 skill。这时数据目录里若恰好有 `OMICSCLAW.md`，它就会成为整份契约 | §5 情形矩阵逐条写明。owner 想要的效果不用写代码：在仓库 `.env` 设一行 `OMICSCLAW_SKILLS_DIR` 即可（§5.4） |
| D2 | 未提及 | 工作目录就是仓库根时（owner 的常规用法，F5），"仓库契约"和"工作目录补充"是同一个文件 | Q3 已裁定为 b（不做补充段），这个问题不再存在 |
| D3 | "Surfaces 部署细节、skill 作者规则移到 AGENTS.md 或 README" | 这些内容在 `AGENTS.md` 里**大多已有**（F10）。缺的只有 Channel 的"七个平台可启动"一段。`AGENTS.md` 现有的 Channel 说法反而与代码不符：`ControlRuntime`、"the rest stay gated"、`FEISHU_BOT_OPEN_ID` Optional 三处都过时 | 移入量降到最小（§9.1），并顺带落地事实修正 |
| D4 | "`test_assembly` 的一致性检查随之删除" | 这个检查防的是免责声明两份文本漂移。拆分后，另一份与 agent 行为相关的副本是 skill 报告实际写入的 `skills/_sdk/report.py:12` 的 `DISCLAIMER`：skills 下 86 个文件导入 `skills._sdk.report`，导入 `omicsclaw.common.report` 的是 0 个（F21） | 不是单纯删除，而是改为断言 `skills._sdk.report.DISCLAIMER in SAFETY_RULES`（§8.1）。**这是对基线的偏离**，只加不减 |
| D5 | "引用 CLAUDE.md 作规则出处的 docstring 约 15 处" | `omicsclaw/`（不含 `surfaces/desktop/`）下有 **25 个文件、52 行**，`tests/` 下另有 **26 个文件、45 行**。其中 3 处在拆分前就已是错误事实 | §7.4 逐条给出去向 |
| D6 | "README 里 workspace contract 的说法" | 只出现在 `README.md:76`，是一条带日期的历史里程碑 | 历史条目不改，新增一条（§9.3） |
| D7 | 未提及 | 长驻进程（`oc channel`、`oc desktop`）已加载旧代码，内容文件一改，它们就会读 dev-only 的 `CLAUDE.md`，而 `SOUL.md` 已不存在 | 阶段 1 开始前先停掉长驻进程，全部验证完再启动（§12） |
| D8 | 新 `CLAUDE.md` 写"你不是那个 agent" | 否定句会把"你是 OmicsClaw"重新带进上下文（writing-for-agents 的 Negation 原则） | 改为第三人称的指针（§4.3） |
| D9 | 保留"工作目录同名文件作为可选的项目级补充" | 在 owner 的常规用法（M1）下这个功能不会触发，却要付出去重逻辑、符号链接处理、非对称的呈现方式和 4 个测试 | owner 裁定 Q3 = b，不做补充段。**理由是简单，不是安全**：§6 表明补充文件并不扩大信任边界 |

**第 1 版自身的更正**

| # | 第 1 版的说法 | 更正 |
|---|---|---|
| E1 | "前置：无。本计划与在途的 0057 不相交……已 grep 确认" | **不成立。**那次 grep 只搜了字面上的文件名。0057 的 A3 驱动是 `AppConfig(workspace=ws, skills_dir=REPO / "skills", …)` 加上 `open_app`（`docs/plans/0057-validation/run_arms.py:257-262, 281`），经过 `default_sections → _front_matter`，正是 M2。本计划落地后，A3 每轮会多出约 2.2k token 的契约；而 0057 要求 A3 使用"部署的标准系统提示（与 golden 逐字节相同）"（`0057-ensemble-tuning.md:580`），并把修改系统提示段落列为非目标（`:1066`）。0057 的冻结范围包含 `omicsclaw/entry/**`，但不含 `OMICSCLAW.md`（`freeze.py:29-37`）。详见 F19。owner 已裁定 Q8 = b |
| E2 | §12 用 `git diff -- … omicsclaw tests` 生成回退补丁 | `git diff` 比较的是工作树与暂存区。这些路径现在就带着 0062、0061、审计总补丁和 0057 的大量未暂存改动，反向应用会一并撤掉它们；`SOUL.md` 也会回到暂存区里的旧版。§12 已重写 |
| E3 | D4 说"skill 脚本写报告时用的正是 `omicsclaw.common.report.DISCLAIMER`" | 不对，skill 用的是 `skills._sdk.report`（F21） |
| E4 | 正文"原样搬家"，只做三件事 | 原文里有 3 处现时为假的事实，本版改为按事实修正落地（§3.3）。另外，第 1 版把非逐字改动定义为只有两种，与大纲自相矛盾，本版在 §3.4 列全 |
| E5 | 阶段 1 第 7 步才重启长驻进程 | 会留下降级窗口，已改（D7） |

### 0.3 结论先行

- **新建 `OMICSCLAW.md`**，放在仓库根目录，与 `skills/` 同级，内容分四节：身份、行为规则、使用 skill、用户侧须知。正文按原文迁移，允许的改动只有三类：
  - 去重：只删 S3 和 C26，它们纯属重复，删掉不改变语义；
  - 移出开发与运维内容；
  - 4 条事实修正（§3.3）。

  所有非逐字改动集中列在 §3.4。措辞和会改变语义的去重都放进 §10 的可选项。
- **`CLAUDE.md` 只留给开发会话**，内容是维护契约、issue tracker、triage 标签，外加一段第三人称的指针。不用 `@OMICSCLAW.md` 导入，理由见 §4.3。
- **删除 `SOUL.md`。**`SAFETY_RULES` 常量成为安全规则的唯一来源。
- **代码改动**：`assembly._front_matter` 的 persona 与 project 两段合成一个 `contract` 段，路径为 `config.repo_root() / "OMICSCLAW.md"`。删除 `DEFAULT_PERSONA_FILE` 和 `DEFAULT_CONTRACT_FILE`，新增 `CONTRACT_FILE`。段落顺序不变，前置段仍在最前。
- **效果估算**（本仓库 `estimate_text_tokens`）：
  - owner 的常规部署（M1）下，前置段从 3,982 降到约 2,206 token，全提示从 11,925 降到约 10,150；
  - M2 部署会**新增**约 2,206 token；0057 的 A3 虽属 M2，但按 Q8 = b 由它自己钉住前置段，不受影响；
  - 首次部署时前缀缓存整体失效一次。
- **owner 已裁定 Q1–Q8，全部按推荐项执行**（§14.1）：
  - 契约文件叫 `OMICSCLAW.md`，放在 skill 树旁（`repo_root()`）；
  - 不做工作目录补充段；
  - core-M2、core-M9 及其余可选项延后，另开一项做会话对比；
  - 不兼容旧布局；
  - `OMICSCLAW_SYSTEM_PROMPT_FILES` 非空时整体替换前置段；
  - 0057 的 A3 由 0057 的会话钉住前置段，本计划对 `entry/**` 的改动须在 0057 冻结之前完成。

---

## 1. 目标与非目标

**目标**

1. 运行时 agent 的指令只有一个文件来源 `OMICSCLAW.md`；安全规则只有一个来源 `SAFETY_RULES`。
2. Claude Code 开发会话不再被注入产品人设；运行时 agent 不再读到开发与运维指令。
3. 渲染出的系统提示里，除前置段外其余字节不变（§11 的机械检查）。
4. 代码与文档中"以 `CLAUDE.md`、`SOUL.md` 为规则出处"的引用全部指向新的真实来源。

**非目标**

- 修改 0057 的任何文件。Q8 = b 要求的配合改动由 0057 的会话自己实施，本计划只把它记为外部前置。
- 整体重写 `AGENTS.md` 或 `CLAUDE.md`：owner 另行处理，本计划只做 §9.1 列出的最小改动。
- 措辞改动和会改变语义的去重（§10 的 O1–O11）：它们要在真实会话里对比后再定。
- 子 agent 的安全规则（审计 prompts-S1）。
- 4 个 consensus skill 是修复还是移出索引。本计划只记录这一裁定对路由表计数的依赖（R13）。
- `pip` 安装形态下随 wheel 分发契约。
- 改变 `skills_root()` 的缺省值。
- OmicsClaw-App 如何接入新后端（F22）。App 在新后端上切换项目本就不可用：新后端没有 `/workspace` 路由，请求里的 workspace 不符时返回 409。这是 App 接入层面的已知缺口，不属于本计划。
- 覆盖 `.mcp.json`、`.omicsclaw/`、`.env` 的统一"目录信任"机制（§6 选项 d）。
- 路由表里手工维护的计数的漂移守卫。
- 带日期的历史文档：README 的旧里程碑、`docs/FRAMEWORK-REBUILD.md` 的带日期小节、`docs/plans/*`、`docs/reviews/*`、`docs/_legacy/*`、`docs/product-overview.md`。

---

## 2. 现状（亲自核实；行号以 2026-09-27 工作树为准，实施时按符号名定位）

| # | 事实 | 出处 |
|---|---|---|
| F1 | **全代码库只有一处读取这两个文件。**`_front_matter` 每次渲染都用 `text_from_file` 读 `config.workspace / "SOUL.md"`（键 `persona`、无标题）和 `config.workspace / "CLAUDE.md"`（键 `project`、标题 `## Project contract`）。两个常量分别定义在 `:209`、`:215` | `entry/assembly.py:577-595`, `:209-217` |
| F2 | 文件缺失时 `text_from_file` 返回 `""`，整段连同标题消失。文件内容**逐字**放入提示，HTML 注释也不剥 | `context/sections.py:89-123`, `context/prompt.py:120-165` |
| F3 | 三处不受影响：子 agent 两份文件都不读；golden 提示第一行就是 `## Safety rules`；压缩摘要与记忆抽取用各自的 system | `entry/subagent.py:116-134, 291-305`；`tests/entry/golden/ensemble_off_prompt.txt:1` |
| F4 | **Claude Code 开发会话会自动加载根目录的 `CLAUDE.md`。**第 3 行的 "You are **OmicsClaw**" 因此进入开发会话。本会话中观察到 Claude Code 呈现时剥掉了 HTML 注释，运行时则逐字注入（F2） | `CLAUDE.md:3, 47, 87` |
| F5 | workspace 缺省为当前目录；`skills_root()` 缺省为 `workspace / "skills"`；`repo_root()` 等于 `skills_root().parent`。仓库 `.env` 没有设 `OMICSCLAW_SKILLS_DIR`、`OMICSCLAW_WORKSPACE`、`OMICSCLAW_SYSTEM_PROMPT_FILES`（只查了变量名），可见 **owner 的常规用法是在仓库根启动**。`docs/core-features/quick-start.md:306-308` 把"数据目录 + `OMICSCLAW_SKILLS_DIR`"写成一种受支持的用法 | `entry/config.py:1316-1318, 578-585, 616-618` |
| F6 | `system_prompt_files` 非空时**整体替换**那一对文件，之后仍接 safety、tools、environment 段。它对应的开关是 `--system-prompt-file` 与 `OMICSCLAW_SYSTEM_PROMPT_FILES`，值用 `:` 分隔 | `entry/config.py:194-207, 891-896, 844-846`；`.env.example:93-97` |
| F7 | **`SAFETY_RULES` 常量**有 4 条，作为 `Section("safety", "## Safety rules", ...)` 注入。它的 docstring 以 `CLAUDE.md` 为出处。`test_assembly.py:578-597` 读仓库 `CLAUDE.md`（`:594`），断言免责声明原句同时出现在两处。同一句话还有两个代码副本：`skills/_sdk/report.py:12`（skill 报告实际使用，F21）和 `omicsclaw/common/report.py:22`（只有框架自己在用：`:210`、`:315`）。两个副本是否相同，已由 `tests/sdk/test_result_contract.py:119-121` 检查 | `entry/assembly.py:232-255, 701` |
| F8 | token 构成，见 §2.1 | — |
| F9 | 重复内容，见 §2.2 | — |
| F10 | `AGENTS.md` 已有 `CLAUDE.md` 里的大部分开发与运维内容，具体位置见表下。不一致之处有四：`:583-584` 写 "the rest stay gated" 和 `ControlRuntime`，而代码里有 7 个 builder（`launch/_surfaces.py:1767-1775`），运行时类名是 `ChannelRuntime`（`entry/channel/runtime.py:230`）；`:592-594` 与 `CLAUDE.md:286-288` 都说 `FEISHU_BOT_OPEN_ID` 可选，而代码缺它就拒绝启动（`launch/_surfaces.py:1610-1615`）；`.env.example:354-356` 也没有标 Required；`:596-598` 说 persona 是 `SOUL.md` | `AGENTS.md` |
| F11 | 以 `CLAUDE.md`、`SOUL.md` 为出处或示例的 docstring：`omicsclaw/`（不含只读参考 `surfaces/desktop/`）25 个文件、52 行，`tests/` 26 个文件、45 行。其中 3 处在拆分前已是错误事实：`context/tokens.py:22`、`:75`，`launch/_surfaces.py:328` | §7.4 |
| F12 | workspace 里还有其他被采信的输入，见 §6 | — |
| F13 | 相关测试基线（2026-09-27，未改动工作树）。entry 这组 8 个文件：261 passed、1 failed、1 skipped，失败的是上面那条既有失败。context 这组 4 个路径：299 passed | §11 |
| F14 | 开发工具与说明文档中的其他引用，见 §9 | — |
| F15 | 路由表两侧的 `<!-- ROUTING-TABLE-START/END -->` 标记属于已删除的生成器 `scripts/generate_routing_table.py`（`ls` 确认不存在）。现在只有 `CONTRIBUTING.md:304-305` 还提到这两个标记 | `CLAUDE.md:47, 87` |
| F16 | `README.md:76` 的 "the workspace contract (`CLAUDE.md`)" 与 `:70` 的 `SOUL.md` 都在历史里程碑里 | — |
| F17 | 系统提示里**没有"当前是哪个界面"的信息**，环境段只有 workspace、平台、日期三项 | `entry/assembly.py:547-574` |
| F18 | 在 M2 部署下，`read_file` 会拒绝 workspace 之外的路径：`PathEscapesWorkspace`，TOOL_GUIDANCE 也写明"a path that leaves it is refused"。`read_file` 把文件当作文本解码（非法字节替换），读不了图片 | `tools/_workspace.py:343-347`；`entry/assembly.py:260-261`；`tools/builtin/read.py:707` |
| F19 | **0057 的 A3 就是 M2 部署。**<br>• 驱动写法：`AppConfig(workspace=ws, skills_dir=REPO / "skills", ensemble=True, ensemble_tools="free", …, permission_mode=AUTO_APPROVE)` 加上 `open_app`（`docs/plans/0057-validation/run_arms.py:257-262, 281`）。<br>• 0057 的要求：A3 使用部署的标准系统提示（`0057-ensemble-tuning.md:580`）；token 按输入加输出计，缓存命中全额计入，上限按开发集的 p95 冻结（`:582-583`）；修改系统提示段落是非目标（`:1066`）。<br>• 冻结机制：`freeze.py:29-37` 的 `CODE_GLOBS` 含 `omicsclaw/entry/**/*`、不含 `OMICSCLAW.md`；摘要不符时 `run_holdout` 拒绝运行（`freeze.py:9-11`）；`freeze.json` 尚未写。<br>• **至少已有一次 A3 开发运行**：`/tmp/0057_dev/root/d1/A3/r1/result.json`，2026-09-27 04:18–04:36 UTC，`status=ok`，20 轮，计入 1,578,662 token。它的 workspace 里没有 `SOUL.md`、`CLAUDE.md`，所以那次的提示没有前置段。<br>• 是否还有其他 A3 运行、这一次是否计入 T10 的 p95 标定：**未知**。<br>• **处理**：owner 裁定 Q8 = b。0057 的会话在 `run_arms.py` 里给 A3 设 `system_prompt_files=(<空文件>,)`，A3 的提示保持与今天逐字节相同；这些已有的开发运行因此仍然可比 | — |
| F20 | **skill 目录的实际形状**（`find skills -name SKILL.md`）：94 个 skill 中，58 个是 `skills/<domain>/<skill>/`；35 个多一层分组，其中 `singlecell/scrna` 33 个、`singlecell/scatac` 1 个、`bulkrna/run-derived` 1 个；`literature` 直接在 `skills/literature/`，脚本为 `literature_parse.py`。`skills/spatial/consensus-domains/consensus_domains.py --help` 实测报 `ModuleNotFoundError: No module named 'omicsclaw.skill'`，交接文档 §3 所列的 4 个 consensus skill 都是这样 | — |
| F21 | skills 下有 86 个文件导入 `skills._sdk.report`，导入 `omicsclaw.common.report` 的是 0 个 | grep |
| F22 | **OmicsClaw-App 如何启动后端**（第 3 版按 App 源码复查更正）：<br>• **后端模块**：缺省为旧模块 `omicsclaw.surfaces.desktop.server`（`src/lib/backend-contract.ts:30`），缺省命令为 `oc desktop-server`（`:33`）。旧模块不能 import，`oc desktop-server` 也已不存在；要接新后端，必须用 `OMICSCLAW_BACKEND_MODULE` 或 `OMICSCLAW_BACKEND_CLI` 覆盖。<br>• **工作目录与环境**：后端进程的 cwd 是 `input.omicsclawDir || input.homeDir`（`electron/local-runtime-plan.ts:104`）。App 设置 `OMICSCLAW_DIR`，如果它指向检出目录，还会设 `PYTHONPATH`（`electron/python-env.ts:40-45`）。App **不设** `OMICSCLAW_WORKSPACE`。<br>• **切换项目**：调用链是 `PUT /api/setup` → `updateAuthoritativeWorkspace`（`src/lib/backend-workspace.ts:89`）→ 后端的 `PUT /workspace`（`:96-99`）。新后端 `omicsclaw/entry/desktop/server.py` 只注册了 `POST /chat/stream`（`:348`）和 `GET /health`（`:390`），**没有 `/workspace` 路由**；请求里的 workspace 与后端不一致时返回 409（`:135-143`）。<br>• **结论**：App 接上新后端时，workspace 取 cwd 的缺省值（`entry/config.py:1316-1318`）。配置了 `OMICSCLAW_DIR` 时 cwd 就是检出目录，情形为 **M1**，契约与 skill 都能拿到；没有配置时 cwd 是用户主目录，情形为 **M3**，两者都没有。"App 只设 workspace、落到 M3"这条路径目前不存在，因为 App 无法把 workspace 传给新后端。App 在新后端上切换项目本就不可用，这是 App 接入层面的已知缺口，不属于本计划 | `/workspace/algorithm/zhouwg_project/OmicsClaw-App` |

F10 中 `AGENTS.md` 已有的内容与位置：
- `--` 分隔的写法：`:91-93`；
- surfaces 表：`:533-549`；
- `surfaces/desktop` 只读、`surfaces/cli` 已删：`:202-208`、`:545-549`；
- frontmatter 四键契约：`:249-268`；
- Desktop：`:551-573`；
- Channel：`:575-598`；
- CLI、斜杠表、审批授权、`memory.db`、TUI：`:600-702`、`:731-744`；
- provider 变量：`:756-761`。

### 2.1 token 构成（`omicsclaw.context.tokens.estimate_text_tokens`，按 `CLAUDE.md` 的标题切分）

在仓库根目录用 `AppConfig(workspace=<repo>)`、`skills_index=full` 渲染，各段为：
- `persona` 291
- `project` 3,691（含标题 `## Project contract`）
- `safety` 133
- `tools` 104
- `planning` 287
- `skills` 7,388
- `environment` 31
- **合计 11,925**

`CLAUDE.md` 全文 3,686 token（14,627 字符）。按用途分：

| `CLAUDE.md` 行 | 小节 | token | 用途 |
|---|---|---|---|
| 1–6 | 标题、身份、SpatialClaw | 160 | 运行时 |
| 7–19 | Repository Maintenance Contract | 154 | **开发** |
| 20–44 | Agent skills（Issue tracker 98、Triage labels 145） | 248 | **开发** |
| 45–88 | Skill Routing Table（含 per-domain 表 199） | 754 | 运行时 |
| 89–122 | How to Use a Skill、Chaining | 336 | 运行时 |
| 123–142 | Finding a skill | 228 | 运行时 |
| 143–156 | What the user can type | 126 | 运行时（用户侧） |
| 157–170 | frontmatter 四键（:157-163，约 92）＋依赖说明（:165-169，约 86） | 177 | 前半给 skill 作者；后半运行时 |
| 171–193 | Demo Data、Re-rendering plots | 172 | 运行时 |
| 194–295 | Surfaces（总述 254、CLI 452、Desktop 95、Channel 400） | 1,200 | **运维**（其中约 75 token 是用户侧须知） |
| 296–301 | Safety Rules | 138 | 与 `SAFETY_RULES` 重复 |

开发与运维合计 154 + 248 + 1,200 ≈ **1,600**。`SOUL.md` 291 token：身份 46、规则 246。

### 2.2 重复内容

| 意思 | 出现位置 | 处理 | 理由 |
|---|---|---|---|
| 身份 | `SOUL.md:5`（S3）；`CLAUDE.md:3`（C2） | 删 S3，保留 C2 | S3 "powered by SKILL.md skills" 已被 C2 的"routing to specialized skills"覆盖，也没有放宽任何约束，删掉不改变语义 |
| 答案可追溯 | `SOUL.md:6`（S4）"Scientific answers must trace to a methodology or script output"；C2 "Every answer must trace back to a SKILL.md methodology or a script output" | **两句都保留** | 从逻辑上看，C2 包含 S4；但 S4 的 "Scientific" 可能被读成"非科学的回答不必追溯"这层放宽。删掉 S4 就会改变模型实际读到的语义，所以移到 O11 做会话对比 |
| 找 skill 并遵循 SKILL.md | `SOUL.md:11-12`（S7，规则 2）"For non-trivial analysis, …"；C2；`CLAUDE.md:93-95`；`SAFETY_RULES` 第 3 条 | **S7 保留** | 理由同上：S7 的 "non-trivial" 可能被读成放宽。移到 O11 |
| 安全规则 | `CLAUDE.md:296-301`（C26）；`SAFETY_RULES` | 删 C26 | 两份措辞不同，今天同时进入提示。常量不会因为改了标题而静默消失 |
| 用户语言 | S6；`CLAUDE.md:14`（维护契约） | 两份都保留 | 读者不同 |
| frontmatter 四键 | `CLAUDE.md:157-163`（C13）；`AGENTS.md:249-268` | 以 `AGENTS.md` 为准 | 给 skill 作者看的 |

---

## 3. 迁移对照表

"原样"指逐字搬过去。所有非逐字的改动（新标题、截断、位置移动、事实修正、改写）集中列在 §3.4。§11 的逐字核对脚本逐行执行，§3.4 的每一项都对应附录 B 的一条豁免。

### 3.1 `CLAUDE.md`

| # | 行 | 内容 | 去向 | 理由 |
|---|---|---|---|---|
| C1 | 1 | `# CLAUDE.md — OmicsClaw Agent Instructions` | 删除；`OMICSCLAW.md` 标题为 `# OmicsClaw`（N1） | 标题只是文件名 |
| C2 | 3 | 身份、"routing to specialized skills"、"Every answer must trace back…" | `OMICSCLAW.md` §1，原样 | §2.2 |
| C3 | 5 前半 | "**Note**: For backward compatibility, … can still refer to you as \"SpatialClaw\" and all 19 spatial skills remain fully functional." | §1，按 **FX4** 删去 "and all 19 spatial skills remain fully functional"，其余原样 | 事实修正 |
| C4 | 5 后半 | "Routing across domains is not a skill — it is the skill index in this prompt plus `use_skill`." | §3 路由小节，放在标题之后、C7 导语之前，原样（N6） | 放到讲路由的地方（同址） |
| C5 | 7–18 | Repository Maintenance Contract | 新 `CLAUDE.md`，原样 | 开发 |
| C6 | 20–43 | `## Agent skills`：Issue tracker、Triage labels | 新 `CLAUDE.md`，原样 | 开发 |
| C7 | 45–46、48–86 | Skill Routing Table：标题、导语、7 个域、per-domain 表、"counts … by hand"注记 | §3，原样；计数取决于 R13 | 运行时路由 |
| C8 | 47、87 | `<!-- ROUTING-TABLE-START/END -->` | 删除（**FX1**） | 事实修正 |
| C9 | 89–113 | How to Use a Skill / Skills with Python scripts、`_lib` 说明 | §3。第 2 步路径句按 **FX2** 修正、第 3 步按 **FX3** 修正，其余原样 | 事实修正；第 4 步与 C25 的冲突列为 O10 |
| C10 | 115–121 | Chaining skills | §3，原样 | 运行时 |
| C11 | 123–141 | Finding a skill | §3，原样 | 运行时；O4、O9 |
| C12 | 143–155 | What the user can type，连同原标题 | §4，原样（N6） | 用户侧 |
| C13 | 157–163 | frontmatter 四键 | 删除，以 `AGENTS.md:249-268` 为准 | skill 作者规则 |
| C14 | 165–169 | "`SKILL.md` is the whole of a skill's metadata … `install_skill_deps` …" | §3，原样，放在"运行脚本"之后，新加小标题 `### Dependencies`（N2、N6） | 运行时；原小标题随 C13 删除 |
| C15 | 171–185 | Demo Data | §3，原样 | 运行时 |
| C16 | 187–191 | Re-rendering plots | §3，原样 | 运行时；O7 |
| C17 | 194–214 | Surfaces 总述等 | 删除，以 `AGENTS.md:91-93, 202-208, 533-549` 为准 | 运维 |
| C18 | 216–245 | CLI | 删除，以 `AGENTS.md:600-702, 731-744` 为准 | 运维；R2、O8 |
| C19 | 247–254 | Desktop 安装与 "Serves chat streaming …" | 删除，以 `AGENTS.md:551-573` 为准。**`### Desktop` 标题（`:247`）保留**，放进 §4 作为 C20 的标题 | 运维 |
| C20 | 255–257 | "**Known gap**: `/chat/permission` was not ported, so an approval-gated tool on this surface waits … or use `oc cli`." | §4，放在沿用的 `### Desktop` 标题下，原样。不另加标签，原句的 "this surface" 由标题指明（N5） | 用户侧须知；模型无法判断自己在哪个界面（F17） |
| C21 | 259–267 | Channel 安装与启动命令 | 删除，以 `AGENTS.md:575-582` 与 `oc channel --help` 为准。**`### Channel — IM bots` 标题（`:259`）保留**，作为 C25 的标题 | 运维 |
| C22 | 269–273 | "Seven platforms can start … stops the others too." | `AGENTS.md` Channel 小节，原样，替换 `:583-584` | `AGENTS.md` 缺这一段，且现有说法与代码不符 |
| C23 | 275–276 | "The persona shared by all adapters is `SOUL.md`. … section 11 …" | `AGENTS.md:596-598`，**改写**为 `OMICSCLAW.md`（N9） | 文件改名 |
| C24 | 278–290 | Required environment 等 | 删除，以 `AGENTS.md:585-598`、`.env.example` 为准。同时修正 `AGENTS.md:592-594` 和 `.env.example:354-355` 的 `FEISHU_BOT_OPEN_ID`（FX5） | 运维 |
| C25 | 292–293 | "Photos sent to a Channel are not passed to you …" | §4，放在沿用的 `### Channel — IM bots` 标题下，原样 | 用户侧须知 |
| C26 | 296–301 | Safety Rules | 删除，以 `SAFETY_RULES` 为唯一来源 | §2.2 |

### 3.2 `SOUL.md`

| # | 行 | 内容 | 去向 | 理由 |
|---|---|---|---|---|
| S1 | 1 | `# OmicsClaw Operating Core` | 删除（N1） | 标题 |
| S2 | 3 | `## Identity` | 作为 §1 的标题，原样 | 结构 |
| S3 | 5 | "You are OmicsClaw, a multi-omics AI assistant powered by SKILL.md skills." | 删除，保留 C2（N8） | 纯重复（§2.2） |
| S4 | 6 | "Scientific answers must trace to a methodology or script output." | §1，放在 C2 之后，原样 | 删除会改变语义，移到 O11 |
| S5 | 8 | `## Operating Rules` | 作为 §2 的标题，原样 | 结构 |
| S6–S14 | 10–25 | 规则 1–9，**含规则 2（S7）** | §2，原样，**编号不变** | 规则 2 的去重移到 O11；规则 6 的改写是 O2；规则 8 与 `planning=off` 的冲突是 O5 |

`SOUL.md` 全文分完后删除。

### 3.3 事实修正（主体落地）

这一节只收"原文现时为假"的句子，按 owner 的规则直接修正。对于依赖 4 个 consensus skill 裁定的句子，给出的都是**无论修复还是移出索引都成立**的最小改法。

| # | 原句（位置） | 证据 | 改法 | 与 consensus 裁定的关系 |
|---|---|---|---|---|
| FX1 | `<!-- ROUTING-TABLE-START -->`、`<!-- ROUTING-TABLE-END -->`（`CLAUDE.md:47, 87`） | 生成器已删（F15），运行时会逐字注入这两行（F2） | 删除两行；`CONTRIBUTING.md:304-305` 同步修改 | 无关 |
| FX2 | "The path is always `skills/<domain>/<skill>/<script>.py` — note the **domain level**:"（`CLAUDE.md:96-97`） | 94 个 skill 中只有 58 个是这种形状（F20）。按这句去拼 C10 点名的地基步骤 `sc-preprocessing`，路径是错的 | "The path is `<skill directory>/<script>.py`, where the skill directory is the one `use_skill` returns — usually `skills/<domain>/<skill>/`, one level deeper for grouped skills (`skills/singlecell/scrna/<skill>/`):"，后面两条示例命令原样保留（示例本身是对的） | 无关 |
| FX3 | "`--help` works on every primary script and is the fastest way to confirm a flag before spending a run on it."（`CLAUDE.md:106-107`） | 4 个 consensus skill 的 `--help` 直接报错（F20） | "`--help` is the fastest way to confirm a flag before spending a run on it." | 修复后原句重新成立，但改后的句子在两种裁定下都成立，**不必改回** |
| FX4 | "… can still refer to you as \"SpatialClaw\" and all 19 spatial skills remain fully functional."（`CLAUDE.md:5`） | `consensus-domains` 是 spatial skill，它的 `--help` 直接报错 | 删去 " and all 19 spatial skills remain fully functional"，改为 "… can still refer to you as \"SpatialClaw\"." | 同上；"19" 在移出索引后也不再成立，删掉这半句在两种裁定下都对 |
| FX5 | `AGENTS.md:592-594`、`.env.example:354-355`："Optional, but group chats fail closed without it" / 未标 Required | 缺 `FEISHU_BOT_OPEN_ID` 就拒绝启动（`launch/_surfaces.py:1610-1615`） | 改为 "Required: …"，理由原句保留 | 无关 |

C7 的计数（spatial 19、singlecell 34、合计 94）**现在是对的**：它们数的是被索引的 skill，而 4 个 consensus skill 仍在索引里。如果 owner 裁定移出索引，这三个数要同时改成 18、31、90（R13）。

### 3.4 非逐字改动总表

凡不是逐字搬运的地方都列在这里，逐字核对（附录 B）按此表豁免。

| # | 类别 | 内容 | 语义影响 | 附录 B 的处理 |
|---|---|---|---|---|
| N1 | 新标题 | `# OmicsClaw` 取代 C1、S1 两个标题 | 无，只是文件名 | 不核对 C1、S1 |
| N2 | 新标题 | `### Dependencies`（C14 的新归属）、`## User-facing notes`（§4） | 无，只是分组 | 核对 C14 正文 |
| N3 | 沿用标题 | `## Identity`（S2）、`## Operating Rules`（S5）、`### What the user can type`（C12）、`### Desktop`（`CLAUDE.md:247`）、`### Channel — IM bots`（`:259`） | 无 | 按原文核对 |
| N4 | 截断 | C19 删去 "Serves chat streaming…" 和安装块，只留 `### Desktop` 标题与 C20；C21 删去安装块，只留标题与 C25 | 无，删掉的是运维内容 | C20 从 "**Known gap**" 起核对 |
| N5 | 标签 | 无（第 1 版的 "Desktop (`oc desktop`):" 已取消，由沿用的 `### Desktop` 标题承担指代） | 无 | — |
| N6 | 位置移动 | C4 移到路由小节，插在 C7 的标题与导语之间；C12 移到 §4；C14 移到"运行脚本"之后；C20、C25 移到 §4 | 同址调整，不改句子 | C7 的标题（`:45`）与正文（`:48-86`）分开核对；C4 单独核对 |
| N7 | 事实修正 | FX1–FX5（§3.3） | 改正事实 | FX2、FX3、FX4 核对改后的句子 |
| N8 | 去重删除 | S3（身份）、C26（安全规则） | 无（§2.2） | 断言不在新文件中 |
| N9 | 改写 | C23 在 `AGENTS.md` 中改写为 `OMICSCLAW.md` | 文件改名 | 核对改写后的句子 |
| — | 编号 | **无**：S7 保留，`SOUL.md` 规则保持 1–9 | — | 按原文核对 |

所有可能改变语义的去重、措辞调整和剪枝都**不在**上表，而在 §10：O11 是 S4、S7 的去重，O1 是 SpatialClaw 句的进一步改写，O2 是 "Let me X" 句，等等。

### 3.5 结果

新的 `OMICSCLAW.md` 约 2,206 token。与今天的两份文件合计相比，移出的内容有：
- 开发内容 400 token；
- Surfaces 1,200 token，其中约 75 token 回到 §4；
- 重复的安全规则 138 token；
- skill 作者规则 92 token；
- S3 约 20 token。

---

## 4. `OMICSCLAW.md` 大纲

### 4.1 四节要点

| 节 | 标题 | 要点（来源） | 估算 token |
|---|---|---|---|
| §1 身份与领域范围 | `## Identity` | OmicsClaw 是覆盖 7 个域的多组学 agent；按 skill 路由、不猜测；每个回答都可追溯（C2）；科学回答须有方法依据（S4）；SpatialClaw 别名（C3 经 FX4） | 约 165 |
| §2 行为规则 | `## Operating Rules` | `SOUL.md` 规则 1–9，原样 | 约 245 |
| §3 使用 skill | `## Skill Routing Table`、`## How to Use a Skill`（`### Skills with Python scripts`、`### Dependencies`、`### Chaining skills`）、`## Finding a skill`、`## Demo Data`、`## Re-rendering plots` | 按域路由与 INDEX 指针（C4、C7）；读 SKILL.md，用 `bash` 按 skill 目录运行脚本，`--help`、展示输出、`--demo`、`_lib`（C9 经 FX2、FX3）；依赖检查（C14）；链式调用（C10）；`use_skill` 的用法（C11）；演示数据（C15）；不提供 replot（C16） | 约 1,580 |
| §4 用户侧须知 | `## User-facing notes`（`### What the user can type`、`### Desktop`、`### Channel — IM bots`） | skill 不是斜杠命令，`/skills` 可以浏览（C12）；Desktop 没有审批通道（C20）；Channel 不传图片（C25） | 约 215 |

### 4.2 用 writing-for-agents 审视

依据 `mattpocock-skills` 1.2.3 的 `writing-for-agents/SKILL.md` 与 `SKILL-MECHANICS.md`；后者只针对 skill，本文件不是 skill，只借用"context pointer"的写法。主体只采纳结构类原则；措辞类原则的产出进入 §10。

**主体采纳**
- **单一来源**：安全规则只在 `SAFETY_RULES`；frontmatter 规则只在 `AGENTS.md`；纯重复（S3、C26）删除。
- **两种负载**：约 1,600 token 的开发与运维内容每轮都占上下文，移出它们是主要的减负。
- **同址**：C4 移到路由小节，C14 紧挨"运行脚本"，用户可见的内容归入 §4。
- **Sprawl**：受众拆分后文件约 2.2k token。
- **把环境当作事实来源**：FX2 让路径以 `use_skill` 返回的目录为准，不再用一条会失效的规则去拼。

**留作可选项**（§10）
- **Negation**（禁令会把被禁的行为带进上下文）：O2（"avoid 'Let me X:'"）、O7（"Do not offer replot"）。
- **缓存环境信息**：O3，路由表里手工维护的计数是目录段与 INDEX 的缓存。
- **无操作的说明**：O4，给开发者看的设计理由。
- **相关性**：O5，`planning=off` 时规则 8 仍点名 `plan_write`。
- **同址与步骤顺序**：O9。`## How to Use a Skill` 第 1 步写 "Read the skill's SKILL.md"，排在 `## Finding a skill`（"call `use_skill`…do not `read_file` a SKILL.md"）之前，两处互相拉扯。按步骤顺序应当是：找 skill → `use_skill` 取正文与目录 → 跑脚本 → 展示结果。这属于整节调换，会改变模型读到的先后，所以放进 O 表。
- **自相矛盾**：O10。C9 第 4 步 "open any generated figures" 与 C25 "OmicsClaw cannot read images yet" 冲突，而 `read_file` 只把文件当文本读（F18）。
- **单一来源，同时会改变语义**：O11，S4、S7 的去重。

### 4.3 新 `CLAUDE.md`

保留 C5、C6，在最前面加一段指针。示意如下（英文，实施时可微调措辞）：

```markdown
# CLAUDE.md — OmicsClaw repository

`OMICSCLAW.md` is the runtime contract of the OmicsClaw analysis agent:
`omicsclaw/entry/assembly.py` puts it at the top of that agent's system
prompt, followed by `SAFETY_RULES` and `TOOL_GUIDANCE` from the same module.
Read it when a change affects what that agent is told, and when adding or
removing a skill (its routing table and counts there are kept by hand).

## Repository Maintenance Contract
…（C5 原样）

## Agent skills
…（C6 原样）
```

写法说明：

- **第三人称，不写否定句**（D8）。交接方案提议写"你不是那个 agent"，按 Negation 原则，这句会把"你是 OmicsClaw"重新带进上下文。改为第三人称描述 "the OmicsClaw analysis agent"，读者自然不会把自己当成它。
- **不加身份句。**"You are a coding agent working on this repository" 对 Claude Code 是无操作。
- **两个互相独立的分支**：
  - "改变 agent 被告知的内容"；
  - "增删 skill 时要同步手工维护的路由表"，`AGENTS.md:472` 第 8 步会指向这里。

  第 1 版的第二个分支是"改变路由"，它其实被第一个分支包含，所以换掉。
- **不用 `@OMICSCLAW.md` 导入。**审计 core-M8 原本建议 `CLAUDE.md` 用 `@OMICSCLAW.md` 导入运行时契约。按 owner 的方案不采纳，原因有三：
  - Claude Code 会把被导入的文件全文展开进开发会话，产品人设、用户语言规则、`plan_write` 规则会原样回到开发会话，正是本计划要去掉的东西（F4）；
  - 导入等于把约 2.2k token 的运行时指令常驻开发会话，而开发者只在少数任务里需要它，这正是"指针而非内联"的场景；
  - 开发会话需要的只是"契约在哪、何时读"，一行指针就够。

---

## 5. 定位逻辑

### 5.1 规则（Q2 = a、Q3 = b，已裁定）

- **契约**：`config.repo_root() / "OMICSCLAW.md"`，即 skill 树旁边、与 `skills/` 同级。键为 `contract`，无标题，因为文件自带 `# OmicsClaw`。
- 每次渲染都重新读；文件缺失时整段消失（F2）。
- **不再读** `<workspace>/SOUL.md`、`<workspace>/CLAUDE.md`（Q5）。
- `<workspace>/OMICSCLAW.md` 只在它**就是** `repo_root()` 下那个文件时被读到，即 M1、M3；其他情况下工作目录里的同名文件不读。
- `skills_dir` 是相对路径时，`repo_root()` 也相对于进程当前目录，与 skill 扫描一致（审核探针显示此时 `repo_root()` 为 `.`）。

### 5.2 工作目录补充段（已否决）

owner 裁定 Q3 = b，不做补充段。否决理由：这个功能在 owner 的常规用法 M1 下不会触发，而它要付出去重、符号链接处理、同一文件在 M2 与 M3 下呈现不对称的代价；M2 下需要项目说明时，可以用 §5.5 的开关把契约和说明文件一起列出。

### 5.3 情形矩阵与各部署形态

| # | 部署 | `repo_root()` | 契约段 | 与现状相比 |
|---|---|---|---|---|
| M1 | **workspace 就是仓库根**，未设 skills_dir。包括：owner 的常规用法；在仓库根启动的 `oc channel`；OmicsClaw-App 配置了 `OMICSCLAW_DIR` 并接上新后端时，后端 cwd 为检出目录、App 又不设 workspace（F22） | 等于 workspace | 仓库的 `OMICSCLAW.md` | `SOUL.md` 加 `CLAUDE.md` 变为 `OMICSCLAW.md`，只有内容变化 |
| M2 | workspace 是数据目录，`OMICSCLAW_SKILLS_DIR=<仓库>/skills`。0057 的 A3 属于这种部署，但它按 Q8 = b 用空文件钉住前置段，实际落在 M7（F19） | 仓库根 | 仓库的 `OMICSCLAW.md` | **行为变化**：今天有 skill 但没有前置段，改后多出约 2.2k token 的契约。这正是 owner 在 Q2 中选择的变化 |
| M3 | workspace 是数据目录，未设 skills_dir。例如 `.env.example:20` 自己给出的 `oc channel --workspace /data …`；OmicsClaw-App 没有配置 `OMICSCLAW_DIR` 时，后端 cwd 为用户主目录，也落在这里（F22） | 等于 workspace | 数据目录里若有 `OMICSCLAW.md`，它**就是整份契约**；通常没有，于是没有契约 | 今天数据目录里的 `CLAUDE.md` 会被当作契约注入；改后不再读 `CLAUDE.md`。两种情况下都扫不到 skill |
| M4 | skills_dir 指向别处的 skill 树 `<X>/skills`，例如 golden 与测试夹具 | `<X>` | `<X>/OMICSCLAW.md`（如果有） | 契约随 skill 树走。夹具旁没有这个文件，golden 不受影响 |
| M5 | 只有工作目录有文件，而工作目录不是 `repo_root()` | 不适用 | 不出现 | 工作目录里的文件不读 |
| M6 | 两处都没有 | 不适用 | 不出现 | 与现状相同，提示从 `## Safety rules` 开始 |
| M7 | `system_prompt_files` 非空 | 不适用 | 只读所列文件 | 与现状相同（Q6） |
| M8 | pip 安装，skills_dir 指向 `site-packages/skills` | `site-packages` | 没有 | 今天同样没有，属于非目标 |

交接文档说"在数据目录里运行时 agent 将始终拿到产品契约"。按上表，这只在 M2 成立，M3 下读不到（D1）。

### 5.4 "数据目录下也有契约"不需要写代码

`launch/_dotenv.py:51-66` 先读检出目录下的 `.env`，再读当前目录的 `.env`。检出目录由 `resolve_omicsclaw_dir()` 找到：在源码检出、且没有设 `OMICSCLAW_DIR` 时，它就是仓库根。

所以只要在仓库根的 `.env` 里写一行 `OMICSCLAW_SKILLS_DIR=<仓库>/skills`，从任何目录启动都会把 M3 变成 M2，skill 和契约同时就位；M1 不受影响（skills_dir 本来就等于它）。README 的新条目和 `.env.example` 都要写上这一做法（§9）。

**pytest 不读 `.env`**，这一行不影响测试。

### 5.5 `OMICSCLAW_SYSTEM_PROMPT_FILES`

- **新缺省**：为空时，前置段是 skill 树旁的 `OMICSCLAW.md`。
- **非空时**：替换前置段，每个文件单独成为一段 `prompt:<name>`，之后仍接 safety、tools 等段（Q6 = a）。开关的解析方式、标志名、分隔符都不变。
- **附带用途**：
  - 作为 §12 的"只恢复旧提示"回退；
  - 在会话对比中充当另一组；
  - Q8 = b 用它钉住 0057 A3 的前置段：设为一个空文件，这一段就消失。

### 5.6 旧工作目录兼容

**不兼容**（Q5 = a，已裁定）。改后不再读 `<workspace>/SOUL.md` 和 `<workspace>/CLAUDE.md`，不做回退读取，也不打警告。理由：
- `SPEC.md:47-48` 规定不加兼容垫片；
- 部署形态是单人、本机，owner 的 workspace 就是仓库；
- 在数据目录里定制过 `SOUL.md` 的用户，可以用 §5.5 的开关；
- README 新条目写一句迁移说明。

---

## 6. 工作目录里的契约文件：风险分析

依据 owner 的规则：每道防线都要说清三件事——防的是什么、有没有同等或更宽的旁路、在当前部署形态下值不值。

Q3 已裁定为 b，不做补充段。这一分析仍然适用于 **M3**：未设 skills_dir 时，数据目录里的 `OMICSCLAW.md` 就是整份契约。它也是 Q3 裁定的依据。

**它防的具体场景。**用户以一个外来目录作为 workspace 启动，例如合作者共享的数据目录、解压的公开数据集、`git clone` 下来的分析仓库。目录里带一个 `OMICSCLAW.md`，它的文本每轮进入**系统提示**。系统提示的权威高于工具结果，而且不需要 agent 主动去读。这段文字可以要求外发数据、运行命令、省略免责声明、绕开 SKILL.md 方法。

**同等或更宽的旁路。**同一个 workspace 已经有这些被采信的输入：

| 输入 | 效果 | 与契约文件相比 | 出处 |
|---|---|---|---|
| `<workspace>/.mcp.json` | 启动时拉起 stdio 服务器进程，**不经审批** | **更宽**：直接执行任意代码 | `entry/assembly.py:1501`；`entry/config.py:610-614` |
| `<workspace>/.omicsclaw/settings.json` | allow 规则预先放行工具调用 | 更宽：绕过审批 | `entry/config.py:555-563` |
| 从该目录启动时的 `<cwd>/.env` | 可以设置仓库 `.env` 没设的变量，例如 `OMICSCLAW_PERMISSION_MODE` | 更宽：可以关掉审批 | `launch/_dotenv.py:51-66` |
| `<workspace>/.omicsclaw/agents/*.md` | 子 agent 定义，它的描述与系统提示进入模型 | 同级 | `entry/subagent.py:161-172` |
| `<workspace>/.omicsclaw/MEMORY.md` 精简版，由同目录的 `memory.db` 重建 | 作为长期记忆段进入系统提示 | 同级 | `entry/memory.py:112-116` |
| **agent 通过 `memory_write` 写记忆** | 被注入的 agent 可以把一段文字持久化进之后会话的系统提示；`memory_write` 是 `AUTO`，**不经审批** | **更宽**，而且是已被接受的通道 | `entry/memory.py:369-377` |
| agent 自己写 `<workspace>/OMICSCLAW.md` | 同样能把注入持久化进之后会话的系统提示；要经过 `write_file` 的审批（`ASK`） | 比 `memory_write` 窄 | `tools/builtin/write.py:228-231` |
| **现状**的 `<workspace>/SOUL.md`、`CLAUDE.md` | 外来的 `CLAUDE.md` 就是整份契约 | 相同或更宽 | F1 |
| agent 读到的任何文件，如 README、CSV 单元格 | 工具结果里的注入 | 更窄：权威低，要 agent 主动去读 | — |

在 auto-approve 或 `/auto` 下，审批不再构成缓解；但 `.mcp.json`、`.env`、`memory_write` 仍然更宽，上表的排序不变。

**代价与收益**（单人、本机、default 权限模式）：
- default 模式下 `bash`、`web_fetch`、MCP 调用都要人批准；
- owner 的常规用法是 M1，外来目录的情形不在日常路径上。

**结论与裁定**：
- 契约文件不扩大 workspace 既有的信任边界，本计划不为它单独设防。
- M3 的情形以文档说明应对：`.env.example` 第 2 节加一句"workspace 是受信目录，其中的 `OMICSCLAW.md`（M3 下）、`.mcp.json`、`.omicsclaw/` 都会被采信"（§9.2）。
- owner 裁定 Q3 = b，不做补充段（§5.2）。
- 真正对准这一威胁的，是覆盖上表全部输入的统一"目录信任"机制：首次打开一个目录时询问是否信任。它属于后续议题，不在本计划范围。

---

## 7. 代码改动

### 7.1 `omicsclaw/entry/assembly.py`

1. **常量**：删除 `DEFAULT_PERSONA_FILE`、`DEFAULT_CONTRACT_FILE`（`:209-217`），新增 `CONTRACT_FILE = "OMICSCLAW.md"`，同步修改 `__all__`（`:171-189`）。仓库内没有别处 import 这两个旧名字。
2. **`_front_matter`**（`:577-595`）的示意：
   ```python
   def _front_matter(config: AppConfig) -> tuple[Section, ...]:
       """The contract beside the skill tree, or the configured prompt files instead.

       A missing file contributes no section.
       """
       if config.system_prompt_files:
           return tuple(
               Section(f"prompt:{path.name}", "", text_from_file(path))
               for path in config.system_prompt_files
           )
       return (Section("contract", "", text_from_file(config.repo_root() / CONTRACT_FILE)),)
   ```
3. **`SAFETY_RULES` 的 docstring**（`:241-255`）按注释约定重写，只说三件事：
   - 这是 agent 的安全规则；
   - 它是唯一一份，契约文件不重复它；
   - 它是常量，不会因为某个标题改名而从提示中消失。

   **常量正文一字不改**，golden 与 §11 的字节比对依赖这一点。
4. **`default_sections` 的 docstring**：
   - `:625-627` 的顺序改为 "contract → safety rules → …"；
   - `:646` 的 "**Six by default, five with skills_index=off**" 已与现实不符（今天是 7 个、关掉索引后 6 个），改为不写数字的说法，例如 "the catalogue section is absent with `skills_index=off`"；
   - `:669-671` 改为"没有 `OMICSCLAW.md` 的部署得到的提示里没有契约段"。
5. **其余 docstring**：模块 docstring `:5`、`:48`，以及 `:718`、`:880`，见 §7.4。

### 7.2 `omicsclaw/entry/config.py`

`system_prompt_files` 的 docstring（`:195-207`）改为 §5.5 的语义；`:7`、`:47` 见 §7.4。字段、选项表、解析函数都不变，也不新增方法。

### 7.3 对 prompt 前缀缓存与段落顺序的影响

**顺序不变。**前置段仍在最前，之后依次是：safety → tools → [planning] → [sandbox] → [skills] → environment → [memory]。

**一次性失效。**前置段位于系统消息开头，改动后第一次请求会让整个系统消息及其后的前缀全部失效一次：
- **DeepSeek、OpenAI**：按字节完全一致的前缀自动缓存（`provider/openai_provider.py:261-281`），所以 safety、skills 等段以及历史对话都要重算一次。
- **Anthropic**：断点打在最后一条系统消息和最后一个工具上。工具那部分的缓存不受影响；系统消息和对话要重算一次。
- 续接旧会话时，每轮都会重新渲染系统消息（`entry/turn.py:108-116`），新契约立即生效，同样重算一次。

**稳态。**契约是静态文件，前缀依然稳定：
- M1 下每次请求约少 1.78k token；
- M2 下每轮约多 2.2k token；0057 的 A3 按 Q8 = b 钉住前置段，不在此列；
- 编辑 `OMICSCLAW.md` 的代价与今天编辑 `SOUL.md` 或 `CLAUDE.md` 相同：它之后的内容全部失效。

**golden 不受影响。**`tests/entry/golden/ensemble_off_prompt.txt` 使用 `skills_dir=tests/ensemble/fake_skills`（M4），那里没有契约文件，所以 golden 文本不变，不需要重新生成。

### 7.4 引用 `CLAUDE.md` / `SOUL.md` 的 docstring（`omicsclaw/`，不含 `surfaces/desktop/`）

分五类，每类一种改法：

- **S 类**：把"`CLAUDE.md` 的第一条安全规则"改为 ``:data:`~omicsclaw.entry.assembly.SAFETY_RULES` 第 1 条``。它是可以 grep 到的代码符号，只是文字引用，不增加 import。
- **C 类**：Channel 入口规则。**去掉出处，保留被引用的规则原文。**这些规则的真实来源是代码本身，`AGENTS.md` 又将整体重写。
- **E 类**：`.env` 的位置。改指 `.env.example` 的文件头。
- **P 类**：描述前置段机制。改为 `OMICSCLAW.md`；`context/` 是叶子层，其中的例子改为中性写法。
- **X 类**：拆分前已是错误事实，按代码改写，不再引用文件作出处。

| 文件:行 | 类 | 改法 |
|---|---|---|
| `entry/assembly.py:5` | P | 模块 docstring 引用了 `context/__init__.py` 里的一句话，随那边一起改 |
| `entry/assembly.py:48` | S | → `SAFETY_RULES` 第 1 条 |
| `entry/assembly.py:209-217, 241-255, 625-627, 646, 669-671, 718, 880` | P | 见 §7.1 |
| `entry/config.py:7` | P | "``SOUL.md`` and the model table" → "the contract file and the model table" |
| `entry/config.py:47` | E | → `.env.example` |
| `entry/config.py:197` | P | §5.5 语义 |
| `entry/turn.py:7-8, 319` | P | → `OMICSCLAW.md` |
| `entry/__init__.py:8` | P | "where ``SOUL.md`` lives" → "where ``OMICSCLAW.md`` lives" |
| `entry/desktop/server.py:229-231` | P | 改为 "skills (unless `skills_dir` is set) and `.mcp.json` are resolved against it"，删去 `SOUL.md`：契约现在跟随 skill 树定位，不一定在 workspace |
| `context/__init__.py:16, 37` | P | 示例改为 `Section("contract", "", text_from_file("OMICSCLAW.md"))`，第 37 行同步修改 |
| `context/sections.py:29, 99, 106` | P | 改为泛指 "a prompt file"；`:99` 的文件清单改为 `OMICSCLAW.md` 与 `INDEX.md` |
| `context/tokens.py:22` | X | "prompts (SOUL.md, CLAUDE.md, every SKILL.md) are Chinese" 不成立。去掉文件清单，只保留"中文文本会被低估"这个一般论断 |
| `context/tokens.py:75` | X | 照片路由的说法已不成立（`entry/channel/telegram.py:64`、`binding.py:20-23`）。实施者需先核实有没有其他界面会把图片传给模型，再按代码改写"是否可达"的判断 |
| `planning/render.py:38-41` | P | → `OMICSCLAW.md`（它的规则 1 是用户语言） |
| `observability/config.py:167`、`observability/__init__.py:68` | S | → `SAFETY_RULES` 第 1 条 |
| `tools/_websafety.py:15`、`tools/builtin/web_fetch.py:9` | S | 同上 |
| `tools/_workspace.py:94` | E | "(``CLAUDE.md``, \"Channel Surface\")" → "(see ``.env.example``)" |
| `entry/ingress.py:140, 161` | C | 去掉出处 |
| `entry/channel/__init__.py:26`、`binding.py:16`、`runtime.py:23`、`feishu.py:23, 198`、`telegram.py:30` | C | 去掉出处；`telegram.py:30` 改为 "the same rule Feishu's ingress enforces" |
| `entry/cli/_configure.py:35`、`entry/cli/_screen.py:24` | S | → `SAFETY_RULES` 第 1 条 |
| `launch/__init__.py:176` | E | → "the failure `.env.example`'s instructions would produce" |
| `launch/_dotenv.py:15, 41, 74` | E | → `.env.example` |
| `launch/_surfaces.py:328` | X | "``CLAUDE.md`` publishes ``oc desktop-server …``" 已不成立，该命令不存在。改为直接陈述 "the Electron client connects to 127.0.0.1:8765" |
| `launch/_surfaces.py:344, 1105` | S | → `SAFETY_RULES` 第 1 条 |

**测试中的同类引用**只是 docstring，不影响行为，按同样的五类映射顺手修改。

| 类 | 文件:行 |
|---|---|
| S | `tests/observability/test_config.py:124`、`test_scope.py:550`；`tests/tools/test_web_fetch.py:498`；`tests/entry/test_assembly.py:1069`、`test_cli_configure.py:363`、`test_cli_logging.py:5`、`test_approval.py:253`；`tests/permission/test_modes.py:238`、`test_danger.py:115, 171`；`tests/launch/test_configure_command.py:211`、`test_surfaces.py:147` |
| C | `tests/entry/test_ingress.py:91, 139`、`test_channel_adapters.py:10, 420, 700`、`test_channel_ingress.py:11, 160`；`tests/launch/test_grammar.py:229` |
| E | `tests/launch/test_configure_command.py:200`、`test_surfaces.py:1047`；`tests/tools/test_workspace.py:427`（既有失败文件，只改 docstring） |
| P | `tests/planning/test_render.py:84`、`tests/sdk/test_replot_hint.py:5`、`tests/entry/test_cli_repl.py:163` |

**不改**：`tests/context/test_sections.py`、`tests/engine/test_prompt_source.py` 把 `SOUL.md` 当作泛指的示例文件名；`tests/entry/test_cli_activity.py:996, 1014` 把 `SOUL.md` 当作随便一个文件路径。

---

## 8. 测试改动

新增测试放在 `tests/entry/test_runtime_contract.py`。实施时先写测试，确认变红后再改代码（TDD）。

### 8.1 修改 `tests/entry/test_assembly.py`

| 行 | 用例 | 改法 |
|---|---|---|
| 413-432 | `test_the_default_prompt_is_seven_sections_in_this_order` | 键为 `("contract", "safety", "tools", "planning", "skills", "environment")`。用例名按内容命名，不再写数字 |
| 435-446 | catalogue off | 键同上，去掉 `skills` |
| 578-597 | `test_the_disclaimer_is_byte_for_byte_the_one_claude_md_requires` | **替换**为 `test_the_disclaimer_is_the_one_skill_reports_write`：`from skills._sdk.report import DISCLAIMER; assert DISCLAIMER in SAFETY_RULES`。docstring 写明为什么保留漂移检查：skill 报告用 `_sdk` 的 `DISCLAIMER`，agent 写报告遵循 `SAFETY_RULES`，两者必须同句；框架里的 `omicsclaw.common.report.DISCLAIMER` 与 `_sdk` 的是否相同，由 `tests/sdk/test_result_contract.py:119-121` 检查。0062 的边界只禁止 `omicsclaw/**` 的生产代码导入 `skills._sdk`，测试不受此限 |
| 600-607 | missing persona | 改名为 missing contract：断言没有契约文本、有 `## Safety rules`，删掉对 `## Project contract` 的断言 |
| 610-623 | prompt files replace | workspace 里另写一份带哨兵文本的 `OMICSCLAW.md`（此时 workspace 等于 `repo_root()`），断言哨兵**不在**提示中（M7） |
| 654-672 | editing a prompt file | 写 `OMICSCLAW.md` 而不是 `SOUL.md`；断言不变 |

### 8.2 新增 `tests/entry/test_runtime_contract.py`

构造"仓库"时用 `skills_dir=tmp_path / "repo" / "skills"`，不需要真的建目录，因为 skill 目录缺失时索引为空。

1. `test_a_workspace_that_is_the_checkout_reads_its_contract`（M1）：契约文本恰好出现 1 次；键以 `contract` 开头。
2. `test_the_contract_comes_from_beside_the_skill_tree`（M2、M5）：契约写在 `repo/`，workspace 另设，并放一份带哨兵的 `OMICSCLAW.md`。断言契约出现、workspace 的哨兵**不出现**（Q3 = b）。
3. `test_without_a_skills_dir_the_workspace_is_the_checkout`（M3）：workspace 的 `OMICSCLAW.md` 就是契约。
4. `test_neither_file_leaves_safety_rules_first`（M6）。
5. `test_the_old_layout_is_not_read`（Q5）：workspace 里放带哨兵的 `SOUL.md` 和 `CLAUDE.md`，哨兵都不出现。
6. `test_a_relative_skills_dir_is_read_from_the_process_directory`：`monkeypatch.chdir(tmp_path)`，`skills_dir=Path("repo/skills")`，契约从 `tmp_path/repo/` 读到。
7. `test_the_real_prompt_states_the_disclaimer_once`：`workspace=tmp_path`、`skills_dir=<仓库>/skills`、`skills_index=off`，渲染真实的 `OMICSCLAW.md`，免责声明原句 `count == 1`。将来有人把 Safety Rules 抄回契约，它会变红。
8. `test_the_real_contract_names_the_agent_and_claude_md_does_not`：仓库根的 `OMICSCLAW.md` 含 "You are **OmicsClaw**"；仓库根的 `CLAUDE.md` 不含这句。
9. `test_the_real_contract_carries_no_developer_instructions`（长期守卫）：真实的 `OMICSCLAW.md` 不含 `Repository Maintenance Contract`、`gh issue`、`pip install -e`、`ROUTING-TABLE`、`## Safety Rules`。

### 8.3 其他测试

| 文件:行 | 改法 |
|---|---|
| `tests/entry/test_turn.py:83-84` | `make_app` 只写一份 `OMICSCLAW.md`，内容包含 "You are OmicsClaw." 和 "Route to a skill, never guess." 两句，`:140-143` 的断言不变；`:134` docstring 中的 "the workspace contract" 改为 "the contract" |
| `tests/entry/test_turn.py:150` | 改写 `OMICSCLAW.md` |
| `tests/entry/test_turn_runner.py:218-219`、`tests/entry/test_memory_wiring.py:126` | 改为写 `OMICSCLAW.md`。今天写了却没有断言，改写是为了测试里的提示与生产形态一致 |
| `tests/entry/test_entry_is_the_top_layer.py:211, 227` | 子进程脚本改写 `OMICSCLAW.md`，断言不变 |
| golden | **不重新生成**（§7.3）。如果变红，说明前置段泄漏进了 golden 部署，应当修代码 |
| `tests/context/*`、`tests/engine/*`、`tests/skills/test_prompt_section_seam.py`、`tests/entry/test_config.py` | 不改 |

**尺寸敏感的既有失败**：`test_the_system_message_survives_a_successful_summarization` 改动前已经失败（F13），改动后前置段会少几个 token，档位可能翻转。把改动前后的状态如实写进交付记录，**不要为了让它变绿去调整提示大小**。

---

## 9. 文档改动

### 9.1 `AGENTS.md`：最小改动，不借机重写

| 行 | 改动 | 性质 |
|---|---|---|
| 196 | 删除 `SOUL.md  Persona used by the Channel surface`；新增一行 `OMICSCLAW.md  Runtime contract of the analysis agent — the top of its system prompt, read from beside skills/` | 文件变动 |
| 198 | `CLAUDE.md  Agent routing instructions (Claude Code entry)` → `CLAUDE.md  Claude Code entry: maintenance contract, issue tracker` | 文件变动 |
| 425 | "The `CLAUDE.md` routing table" → `OMICSCLAW.md` | 文件变动 |
| 472 | 第 8 步 "Update the routing table in `CLAUDE.md`" → `OMICSCLAW.md` | 文件变动 |
| 583-584 | 替换为 C22 原文 | 迁入内容，同时是事实修正 |
| 592-594 | `FEISHU_BOT_OPEN_ID` 改为 "Required: …"（FX5） | 事实修正 |
| 596-598 | "The persona every adapter shares is `SOUL.md`" → "The runtime contract every adapter shares is `OMICSCLAW.md`"，并补 "`.env.example` section 11 is the full per-platform list"（C23） | 文件变动 |

### 9.2 仓库根部与模板

| 文件:行 | 改动 |
|---|---|
| `.env.example:93-97` | 示意：`# Empty means OMICSCLAW.md beside the skills directory — by default <workspace>/skills, so <workspace>/OMICSCLAW.md; set OMICSCLAW_SKILLS_DIR (section 4) to read the checkout's. Setting this replaces it.`；括号里关于 `--prompt-file` 的说明保留。第 1 版写的 "(the checkout root)" 在 M3 下不对，已弃用 |
| `.env.example:121` | `#OMICSCLAW_SKILLS_DIR=  # empty = <workspace>/skills; OMICSCLAW.md is read from beside it. Setting it in the checkout's .env gives every start the checkout's skills and contract` |
| `.env.example` 第 2 节 | 加一句"workspace 是受信目录：其中的 `OMICSCLAW.md`（M3 下）、`.mcp.json`、`.omicsclaw/` 都会被采信"（§6） |
| `.env.example:211` | "CLAUDE.md's first safety rule" → "the agent's first safety rule" |
| `.env.example:354-355` | `FEISHU_BOT_OPEN_ID` 前加 "Required."（FX5） |
| `CONTRIBUTING.md:304-305` | → "The routing table in [`OMICSCLAW.md`](OMICSCLAW.md) is maintained by hand."（标记已删，FX1） |
| `CONTRIBUTING.md:334` | `CLAUDE.md` → `OMICSCLAW.md` |
| `templates/skill/README.md:67` | "add the routing-table row in `CLAUDE.md`" → `OMICSCLAW.md` |
| `llms.txt:252` | `CLAUDE.md` 那一行改为 "Claude Code entry: maintenance contract, issue tracker"，另加一行 `OMICSCLAW.md` 为 "Runtime contract of the analysis agent" |
| `mint.json:106, 110` | 排除列表：`SOUL.md` 换成 `OMICSCLAW.md` |

两份 `r_visualization.md:7` 里的 "(CLAUDE.md routing reference)" 本来就不对，属于审计 §3.4 的 references 残留，不在本计划范围。

### 9.3 README 与现状说明文档

**README**
- 不改 `README.md:70, 76` 的历史里程碑（D6）。
- 在 "What's New" 最前面新增一条，写明：
  - 运行时契约已迁到 `OMICSCLAW.md`；
  - 契约跟随 skill 树定位（M1、M2、M3 的区别）；
  - **零代码做法**：在仓库 `.env` 设 `OMICSCLAW_SKILLS_DIR=<仓库>/skills`，从任何目录启动都能同时拿到 skill 和契约；
  - 旧工作目录里的 `SOUL.md`、`CLAUDE.md` 不再被读取。

**`docs/core-features/`**（描述当前行为的文档，未跟踪，属于在途的项目文档）
- **必改**：
  - `context-engineering.md:14`（"`SKILL.md` 与 `CLAUDE.md` 大量是中文"，与 `tokens.py:22` 是同一个错误）、`:21, 122, 138-139, 154-161, 313, 340, 425, 427, 449`
  - `quick-start.md:133, 270-271, 278, 308, 358`；`:341` 的 "`CLAUDE.md` 仍列出它" 已不成立，一并删去；`:308` 改为写零代码做法
  - `cli.md:364, 384`
  - `surfaces.md:63, 65`
  - `agent-loop.md:466`
  - `sub-agent.md:276`
  - `agent-skills.md:51, 406, 489`
- **顺手改**（按 §7.4 的映射）：
  - `observability.md:157`
  - `web-search.md:21`
  - `sandbox.md:23`
  - `shell-execution.md:12`
  - `mcp.md:430, 436`
  - `human-in-the-loop.md:5, 358`
  - `agent-skills.md:499`
  - `surfaces.md:264, 323, 339`：写的是"`CLAUDE.md` 与代码不符"，改为只陈述代码行为
- `docs/safety/rules-and-disclaimer.mdx:30`："来源于 CLAUDE.md Safety Rules 第 2 条" → "`SAFETY_RULES` 第 2 条"。

**`docs/FRAMEWORK-REBUILD.md`**：只在 `:1893` 的指针表补上 `OMICSCLAW.md`，带日期的小节不改。

---

## 10. 可选项（措辞、剪枝与会改变语义的去重，不在主体）

这些改动都会改变模型读到的意思。owner 已裁定 Q4 = a、Q7 = a：**不随主体实施**，另开一项"契约措辞与剪枝"逐项对比。

每项的做法相同：
1. 一次只改一处；
2. 用 §5.5 的开关准备两份契约作为 A、B 两组，同一组任务各跑一遍；
3. 对比记录写进交付记录。

| # | 位置（落地后） | 改动 | 来源 | 预期与风险 |
|---|---|---|---|---|
| O1 | §1 SpatialClaw 句（FX4 之后） | "**Note**: For backward compatibility, spatial transcriptomics users can still refer to you as \"SpatialClaw\"." → "Users may also call you \"SpatialClaw\"." | 审计 core-M2 的剩余部分（事实部分已由 FX4 落地） | 去掉以旧版本为参照的描述；风险极低 |
| O2 | §2 规则 6 | "…avoid \"Let me X:\" preambles." → "…open with the answer or result." | 审计 core-M9；writing-for-agents 的 Negation 原则 | 输出开头的形态会变 |
| O3 | §3 路由表 | 删去 per-domain 计数表（它是 INDEX 与 `compact` 目录的缓存），只保留各域一行简介；或在 `full` 档下删去整个路由表 | writing-for-agents：把环境当作事实来源 | 约省 200 到 740 token，还能消除 R13 的计数依赖；可能影响按域路由，**必须做会话对比** |
| O4 | §3 Finding a skill 首段 | 删去 "about 8.4k tokens … ~125k" 这类设计说明 | 无操作的说明 | 数字会过时；几乎不影响行为 |
| O5 | §2 规则 8 | 删去（`plan_write` 挂载时 `PLANNING_GUIDANCE` 已覆盖），或改为条件句 | 审计 core-H1 的行为部分 | `planning=off` 时提示不再点名一个没有挂载的工具 |
| O6 | §3 | 加一句：路径与示例都相对 `skills/` 旁的检出目录；按 `use_skill` 返回的目录，用 `bash` 以绝对路径运行和读取；workspace 之外的文件 `read_file` 读不到 | R3 | M2 下 "read `skills/<domain>/INDEX.md` directly" 与 `examples/` 用 `read_file` 执行不了（F18） |
| O7 | §3 Re-rendering plots | 删去 "Do not offer `replot` to a user."，保留 "to change a plot, re-run the skill" | Negation | 禁令本身可能诱发提及 replot |
| O8 | §4 | 加一句："`/help` lists the REPL's commands." | R2 | 弥补 C18 移出后 agent 不知道 REPL 命令的问题 |
| O9 | §3 各节顺序 | 按步骤排序：先 `## Finding a skill`（找 skill、`use_skill` 取正文与目录），再 `## How to Use a Skill`（跑脚本、展示结果）；第 1 步 "Read the skill's SKILL.md" 与 "do not `read_file` a SKILL.md" 合并为一句 | writing-for-agents：同址与步骤顺序（审核次要 2） | 模型取 skill 的先后可能变化 |
| O10 | §3 C9 第 4 步 | "open any generated figures" 与 C25 的 "cannot read images yet" 冲突。改为"指出生成的图的路径，并根据 `result.json` 与表格解释结果" | 审核次要 2；F18 | 改变运行后的展示方式 |
| O11 | §1、§2 | S4、S7 去重：删去 "Scientific answers must trace…" 与规则 2，后续规则编号顺延 | writing-for-agents：单一来源 | 丢掉 "Scientific"、"non-trivial" 两个可能被读成放宽的限定；约省 35 token |

O-项定下来之后，建议按交接文档 §4 用 `claude-api`（prompt-audit）再审一遍 `OMICSCLAW.md`。

---

## 11. 验证

下文 `$B` 指 §12 的基线目录 `/workspace/dataset/private/zhouwg_data/0063-baseline`，它在仓库外，也不在 `/tmp`。

### 11.1 渲染对比

**阶段 0**：用附录 A 的脚本以 label `before` 渲染四种部署，输出写到 `$B/render/`：
- R1：workspace 为仓库根；
- R2：空数据目录，`skills_dir=<仓库>/skills`，即 0057 A3 的形态；
- R3：空数据目录，未设 skills_dir；
- R4：workspace 为仓库根，`system_prompt_files` 设为一个外部文件。

**改动后**：以 label `after` 再跑一次，逐项核对：

| 检查 | 期望 |
|---|---|
| R1：`sed -n '/^## Safety rules$/,$p'` 截取改动前后两份，做 `diff` | **为空** |
| R1 前置段 | 变为一个 `contract` 段；"You are **OmicsClaw**" 恰好 1 次；不含 `## Project contract`、`Repository Maintenance Contract`、`gh issue`、`pip install -e`、`<!-- ROUTING-TABLE`、"fully functional"、"works on every primary script" |
| R2 | before 没有前置段，after 有 `contract` 段（M2 的行为变化，Q2 所选；0057 的 A3 由 Q8 = b 另行钉住）；`## Safety rules` 之后与 before 相同 |
| R3、R4 | before 与 after 全文相同 |
| token（`*-stats.json`） | R1 前置段从 3,982 降到约 2,206（±60），全提示约 10,150；R2 增加约 2,206；R3、R4 不变 |

### 11.2 逐字核对

按附录 B 执行，核对结果写进交付记录。

### 11.3 grep

以下命令的结果只应剩 §7.4 标为"不改"的项：

```bash
grep -rn "SOUL\.md\|CLAUDE\.md" --include=*.py omicsclaw | grep -v "^omicsclaw/surfaces/desktop/"
grep -rn "DEFAULT_PERSONA_FILE\|DEFAULT_CONTRACT_FILE\|Project contract" omicsclaw tests --include=*.py
grep -rn "SOUL\.md" AGENTS.md CONTRIBUTING.md .env.example llms.txt mint.json templates
```

### 11.4 测试（只跑相关的）

**阶段 0 的基线命令**（新测试文件此时还不存在，不列入）：

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly -p no:cacheprovider \
  tests/entry/test_assembly.py tests/entry/test_turn.py tests/entry/test_turn_runner.py \
  tests/entry/test_memory_wiring.py tests/entry/test_entry_is_the_top_layer.py tests/entry/test_ensemble_golden.py \
  tests/entry/test_config.py tests/test_env_example.py tests/sdk/test_result_contract.py \
  tests/context tests/planning/test_render.py tests/skills/test_prompt_section_seam.py tests/engine/test_prompt_source.py
```

- **改动后**：在上面的命令里加上 `tests/entry/test_runtime_contract.py`。
- **期望**：除已知的那 1 个失败外全部通过，新增用例全部通过。
- **基线参考**（F13）：entry 这组 261 passed、1 failed、1 skipped；context 这组 299 passed。`tests/sdk/test_result_contract.py` 以阶段 0 实测为准。
- **§7.4 阶段**另跑被改动 docstring 的测试文件，确认没有语法问题。`tests/tools/test_workspace.py` 是既有失败，除外。
- **不跑全量。**

### 11.5 冒烟

冒烟不是正式的 A/B 对比。在仓库根执行一次 `oc cli --prompt-file`，任务为"用 bulkrna-de 的演示数据跑一遍差异分析"。需要真实的 LLM key，由 owner 决定是否执行。

期望：
1. 调用 `use_skill bulkrna-de`；
2. 按返回的目录执行脚本；
3. 报告里带免责声明。

---

## 12. 分阶段、基线与回退

### 12.1 各阶段改动的文件清单（补丁与回退只针对这些文件）

**L1，阶段 1**
- 新建：`OMICSCLAW.md`、`tests/entry/test_runtime_contract.py`
- 删除：`SOUL.md`
- 修改：
  - `CLAUDE.md`、`AGENTS.md`、`CONTRIBUTING.md`、`.env.example`、`llms.txt`、`mint.json`、`templates/skill/README.md`
  - `omicsclaw/entry/assembly.py`、`omicsclaw/entry/config.py`
  - `tests/entry/test_assembly.py`、`tests/entry/test_turn.py`、`tests/entry/test_turn_runner.py`、`tests/entry/test_memory_wiring.py`、`tests/entry/test_entry_is_the_top_layer.py`

**L2，阶段 2**
- `omicsclaw/` 下的 23 个文件：
  - `context/__init__.py`、`context/sections.py`、`context/tokens.py`
  - `entry/__init__.py`、`entry/ingress.py`、`entry/turn.py`、`entry/desktop/server.py`
  - `entry/channel/__init__.py`、`binding.py`、`feishu.py`、`runtime.py`、`telegram.py`
  - `entry/cli/_configure.py`、`_screen.py`
  - `launch/__init__.py`、`_dotenv.py`、`_surfaces.py`
  - `observability/__init__.py`、`config.py`
  - `planning/render.py`
  - `tools/_websafety.py`、`tools/_workspace.py`、`tools/builtin/web_fetch.py`
- `tests/` 下的 18 个文件：§7.4 测试表所列，`test_assembly.py` 除外，它在 L1。

**L3，阶段 3**
- `README.md`、`docs/FRAMEWORK-REBUILD.md`、`docs/safety/rules-and-disclaimer.mdx`
- `docs/core-features/` 下的 13 个文件：§9.3 所列

**这些文件的现状**（2026-09-27）：
- 绝大多数已带有别人未提交的改动（` M`）；
- `tests/sdk/test_replot_hint.py` 与 `docs/core-features/` 是**未跟踪**文件；
- `omicsclaw/entry/**` 在 0057 的冻结范围内（F19）。

### 12.2 阶段 0：记下基线（只读，不改工作树）

1. 建立基线目录 `B=/workspace/dataset/private/zhouwg_data/0063-baseline`。它在仓库外，也不在 `/tmp`（`/tmp` 重启会清空）。把 L1、L2、L3 各写成一个文本文件，存进 `$B/`。
2. **逐文件副本**（主记录）：对清单中所有已存在的文件执行 `cp --parents -p <file> $B/tree/`，含 `SOUL.md`、`CLAUDE.md` 的当前工作树版本，也含未跟踪文件。
3. **git 记录**（辅助）：
   - `BASE=$(git stash create)`，把 SHA 写进 `$B/stash-sha.txt`；
   - `git update-ref refs/backup/0063-base $BASE`，防止这个无引用的提交被 gc 回收。这两步都不改工作树和暂存区。
   - 注意：`stash create` 只记录已跟踪文件，未跟踪文件以第 2 步的副本为准。
   - 如果需要一份连未跟踪文件在内的全量快照，可以用临时索引：`GIT_INDEX_FILE=$B/idx git add -A && GIT_INDEX_FILE=$B/idx git write-tree`，把树的 SHA 记下来。
4. 按 §11.1 渲染 before 快照到 `$B/render/`，按 §11.4 的阶段 0 命令记录测试基线到 `$B/tests-before.txt`。
5. 执行 `pgrep -af "oc (channel|desktop)|omicsclaw\.launch"`，把正在运行的长驻进程及其完整命令行记进 `$B/processes.txt`。
6. **检查 Q8 = b 的两个条件，任一不满足就停下，不做任何改动，报告 owner**：
   - **0057 还没有冻结**：`docs/plans/0057-validation/` 下没有 `freeze.json`（`ls docs/plans/0057-validation/freeze*.json` 应当报找不到）。`freeze.py write` 的 `--out` 可以指向别处，所以如果 0057 的交付记录或会话提到过冻结，也按"已冻结"处理。
   - **A3 已经钉住前置段**：`docs/plans/0057-validation/run_arms.py` 里 A3 的 `AppConfig(…)` 带有 `system_prompt_files=(…)`，指向的文件内容为空（可以在运行时写出）。只读核对这一行，**本计划不修改它**。

   两项检查的结果记进 `$B/preflight.txt`。阶段 2 开始前重复第一项检查，因为阶段 2 也要改 `omicsclaw/entry/**`。

### 12.3 阶段 1（主体，必须一次落地）

**不可拆开的原因**：
- 只落内容文件：旧代码会读已删除的 `SOUL.md`（人设段消失），还会读 dev-only 的 `CLAUDE.md`（开发内容反而进入提示）；
- 只落代码：`OMICSCLAW.md` 不存在，契约段消失。

顺序：
0. 确认 §12.2 第 6 步的两项检查都已通过。
1. **停掉 `$B/processes.txt` 里的长驻进程**，从此刻到第 7 步不存在降级窗口（D7）。
2. 写 §8.1、§8.2 的测试，确认变红。
3. 改 `assembly.py`、`config.py`（§7.1、§7.2）。
4. 按 §3 创建 `OMICSCLAW.md`，重写 `CLAUDE.md`，删除 `SOUL.md`。
5. 改 §8.3 的测试文件，做 §9.1、§9.2 的文档改动。
6. 按 §11.1 至 §11.4 验证。
7. 按 `$B/processes.txt` 重新启动长驻进程。
8. 用附录 C 的方法生成 `$B/0063-phase1.diff`，**逐块检查**：凡不是本计划写的块，都是其他会话的并发改动，要从补丁中剔除，并记进交付记录。

**阶段 2（docstring 出处）**与**阶段 3（说明文档）**只改注释和文档，不影响运行中的进程。各自结束时同样生成 `$B/0063-phase2.diff`、`$B/0063-phase3.diff`。

阶段 2 会改动 `omicsclaw/entry/**`。按 Q8 = b 的时间约束，它必须在 0057 写出 `freeze.json` 之前完成，否则冻结摘要会失配。开始前重复 §12.2 第 6 步的冻结检查；如果 0057 已经冻结，阶段 2 里 `omicsclaw/entry/**` 下的文件就暂停，其余文件照常，并报告 owner。

**阶段 4（另开一项）**：按 Q4 = a、Q7 = a 的裁定，O-项不在本计划内实施，而是另开一项"契约措辞与剪枝"，逐项做会话对比。

### 12.4 回退

- **按阶段回退**，先回退后面的阶段：
  1. 先停掉长驻进程；
  2. 执行 `git apply -R --check $B/0063-phaseN.diff`，通过后再执行 `git apply -R $B/0063-phaseN.diff`。补丁只包含本计划改动的块，所以别的会话在同一批文件里的其他改动会保留下来；
  3. 删除 `SOUL.md` 的那段补丁，其"原文"一侧取自 `$B/tree/SOUL.md`，所以反向应用后恢复的是**改动前工作树里的版本**，不是暂存区里的旧版；
  4. 新建的 `OMICSCLAW.md` 和 `tests/entry/test_runtime_contract.py` 由补丁中 `--- /dev/null` 的段落在反向应用时删除；
  5. 最后重启长驻进程。
- **如果 `--check` 失败**，说明本计划之后有人改了同一段落：
  - 对每个冲突文件，用 `diff` 比较 `$B/tree/<file>` 与当前版本，手工只撤回本计划的块；
  - **不要**直接把副本拷回去，那会抹掉别人之后的改动。
- **已提交后**：`git revert <sha>`。
- **不回退代码，只恢复旧提示**：`OMICSCLAW_SYSTEM_PROMPT_FILES=$B/tree/SOUL.md:$B/tree/CLAUDE.md`，得到的文本与旧前置段只差 `## Project contract` 一行标题。
- **与审计总补丁的先后**：本计划落地后，`/tmp/prompt-audit/applied-facts.diff` 中涉及 `CLAUDE.md`、`SOUL.md` 的部分就不能再 `git apply -R` 了。如果要同时撤回两者，**先撤回本计划**，再撤回审计补丁。交付记录里要写明这一点。

---

## 13. 风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 长驻进程运行旧代码，而内容文件已改，就会读不到人设，还会把 dev-only 的 `CLAUDE.md` 当作契约 | 阶段 1 第 1 步先停、第 7 步再启（§12.3）；回退时同理 |
| R2 | 运行时 agent 不再知道 `/resume`、`/auto`、审批授权 y/s/a 的含义（C18） | O8；冒烟时顺带问一句 |
| R3 | M2 下，契约里"直接读 `skills/<domain>/INDEX.md`"和 `examples/` 的指引用 `read_file` 执行不了：workspace 外的路径会被拒绝（F18）。只能靠 `bash` 以绝对路径访问。0057 的 A3 虽属 M2，但按 Q8 = b 拿不到契约，不受此影响 | `use_skill` 返回正文和绝对目录，脚本用 `bash` 以绝对路径运行可以正常工作；可选 O6 |
| R4 | 路由表里手工维护的计数仍会漂移 | O3 |
| R5 | D1 会改变 owner 对"数据目录下也有契约"的预期 | Q2；§5.4 的零代码做法；README 新条目 |
| R6 | 与审计总补丁的撤回顺序 | §12.4 |
| R7 | 历史文档与 references 残留里仍会提到 `SOUL.md`、`CLAUDE.md` | 属于非目标；交付记录列出 grep 结果 |
| R8 | M3 下，工作目录里的 `OMICSCLAW.md` 就是整份契约，成为注入入口 | §6：不扩大既有信任边界；`.env.example` 写明 workspace 是受信目录；Q3 = b 已排除 M2 下的补充段 |
| R9 | OmicsClaw-App 接上新后端时（F22）：配置了 `OMICSCLAW_DIR` 则后端 cwd 为检出目录，属于 M1，契约与 skill 都能拿到；没有配置则 cwd 为用户主目录，属于 M3，两者都没有。App 在新后端上切换项目本就不可用（新后端没有 `/workspace` 路由，workspace 不符时返回 409） | 切换项目的缺口是 App 接入层面的已知问题，不属于本计划。M3 的情形可以在检出目录的 `.env` 设 `OMICSCLAW_SKILLS_DIR` 改善，但前提是那份 `.env` 能被加载（§5.4） |
| R10 | 工作树里有在途改动，别的会话可能并发修改同一批文件 | §12 的逐文件基线与逐块检查；改文件前重新读取 |
| R11 | 尺寸敏感的既有失败发生翻转 | 如实记录，不去调整 |
| R12 | **0057 A3 的系统提示会变**（多约 2.2k token/轮；契约里 "Run the script with `bash`" 可能让 agent 绕开 `run_skill` 预算，影响的不止 token）；本计划改 `entry/**` 会使 0057 的冻结摘要失配；`OMICSCLAW.md` 不在 `CODE_GLOBS` 里，冻结后编辑它不会被发现 | Q8 = b：由 0057 的会话把 A3 的前置段钉成空文件，所以 A3 的提示不变，`OMICSCLAW.md` 的后续编辑也影响不到 A3；本计划对 `entry/**` 的改动须在 0057 冻结之前完成；§12.2 第 6 步在实施前检查这两条 |
| R13 | **依赖 4 个 consensus skill 的裁定**：若移出索引，C7 的计数（spatial 19、singlecell 34、合计 94）要同时改为 18、31、90；若修复，FX3、FX4 改前的原句重新成立，但改后的句子照样成立，不必改回 | FX2–FX4 按两种裁定下都成立的写法落地；计数的修改随 consensus 裁定一起做，或者选 O3 从根上消除 |

---

## 14. 问题与 owner 裁定

### 14.1 裁定记录

2026-09-27，owner 本人在对话中裁定：Q1–Q8 **全部按推荐项执行**。

| # | 问题 | 裁定 | 对本计划的影响 |
|---|---|---|---|
| Q1 | 文件名 | **a** `OMICSCLAW.md` | — |
| Q2 | 定位锚点 | **a** `config.repo_root()` | §5.1、§5.3；零代码做法见 §5.4 |
| Q3 | 工作目录补充段 | **b** 不做 | 原 §5.2 的设计、§7.1 的追加说明、§8.2 为 a 准备的 4 个用例都已删除；§5.2 只留否决理由 |
| Q4 | core-M2、core-M9 | **a** 不随本计划 | O1、O2 进入另开的一项；FX4 属于事实修正，不受影响，仍在主体 |
| Q5 | 旧布局兼容 | **a** 不兼容 | §5.6 |
| Q6 | `OMICSCLAW_SYSTEM_PROMPT_FILES` 非空时 | **a** 替换前置段 | §5.5。Q3 = b 之后，被替换的只有契约一段 |
| Q7 | O3–O11 | **a** 另开一项，逐项做会话对比 | §10；阶段 4 不在本计划内实施 |
| Q8 | 与 0057 的协调 | **b** 由 0057 的会话钉住 A3 的前置段 | 外部前置（文首）；时间约束：本计划对 `omicsclaw/entry/**` 的改动须在 0057 写出 `freeze.json` 之前完成；§12.2 第 6 步检查这两条，任一不满足就停下、报告 owner |

### 14.2 各问题的选项与论证（存档）

下表保留裁定前的选项与理由，供日后追溯；除第 3 版就事实所作的更正（Q2 中 App 的部分）外，内容未改。

| # | 问题 | 选项 | 推荐与理由 |
|---|---|---|---|
| **Q8（已裁定 b）** | 本计划与 0057 A3 的冲突（F19、R12）。本计划不修改 0057 的任何文件 | **a** 0063 等 0057 的 A3 运行（开发与留出）全部完成后再落地。**b** 现在落地，由 0057 的会话在 `run_arms.py` 里钉住 A3 的前置段：给 A3 的 `AppConfig` 设 `system_prompt_files=(<空文件>,)`，空文件可以在每次运行的目录里现写，内容恒为空，不需要冻结。空文件使前置段消失，A3 的提示与今天逐字节相同。同时，本计划阶段 1、2 对 `omicsclaw/entry/**` 的改动必须在 0057 写出 `freeze.json` 之前完成。**c** 现在落地，0057 接受带契约的 A3：重跑已有的 A3 开发运行，把 `OMICSCLAW.md` 加进 `CODE_GLOBS`，按新的 token 分布重定 T10 的 p95 上限 | **b。** 各项代价：<br>• **a**：0063 要等一段未知的时间，0057 的留出集规模很大（见其 §4.8）。期间现状的代价持续：开发会话继续被注入人设，运行时每轮带约 1.6k token 的开发内容。<br>• **b**：0057 的驱动里改一行（由 0057 的会话改）。A3 测的仍然是"没有产品契约的 agent"，与今天已有的开发运行可比，也守住了 0057 自己"不改系统提示"的非目标；代价是 A3 不再代表 0063 之后的部署形态，这一局限应写进 0057 的报告。另有时间约束：freeze 之前要完成本计划对 `entry/**` 的改动。<br>• **c**：外部效度最好，但要重跑。已知的那次开发运行（F19）是 20 轮、1.58M token、墙钟约 17 分钟，契约每轮多约 2.2k token，20 轮约多 44k（约 2.8%），50 轮约多 110k。更要紧的是，契约 §3 要求用 `bash` 跑脚本，而 A3 的设计围绕 `run_skill` 的预算，契约可能改变 A3 的行为，而不只是 token 数；这需要 0057 重新审视设计。<br>• **尚不清楚的**：除 F19 那一次外是否还有 A3 运行、它是否计入 T10 的标定 |
| Q1 | 运行时契约的文件名 | a `OMICSCLAW.md`；b `AGENTS.md`；c 沿用 `SOUL.md`；d 放进包内，如 `omicsclaw/prompts/contract.md` | **a**。以产品命名，任何开发工具都不会自动加载它（Claude Code 读 `CLAUDE.md`，Codex、Cursor 读 `AGENTS.md`）。b 会让开发代理加载产品人设；c 的名字只表达人设；d 让文件与 `skills/` 分开，违背"契约随 skill 树走"。审核同意 |
| Q2 | 契约的定位锚点，以及由此带来的行为变化 | **a** `config.repo_root()`，即 skill 树旁边（交接基线）；**b** 代码所在的检出目录（由 `Path(__file__)` 推导），与 skills_dir 无关；**c** 先 a，找不到再 b | **a。** 理由有四：<br>• **测试隔离**：a 下所有 `tmp_path` 测试和 golden 都能用 skills_dir 与仓库的真实契约隔开（M4）。b 下它们都会读到真实契约：golden 要重生成，此后每次编辑 `OMICSCLAW.md` 都会让 golden 变红；`test_the_prompt_carries_no_clock_reading` 这类"空 workspace 只剩本层文本"的用例也会失去前提。<br>• **一个开关**：设一次 `OMICSCLAW_SKILLS_DIR`，skill 和契约同时就位。OmicsClaw-App 以检出目录为后端 cwd 时属于 M1，不需要任何变量；没有配置 `OMICSCLAW_DIR` 时 cwd 为主目录，属于 M3（F22，第 3 版更正）。<br>• **`.env` 的先例不宜借用**：`.env` 按检出目录加 cwd 定位（`launch/_dotenv.py:51-66`），但它依赖的 `resolve_omicsclaw_dir()` 会读 `OMICSCLAW_DIR`。App 会设这个变量，而 `.env.example:98` 又把它写成"state dir"，语义冲突；entry 层也不允许直接读环境。<br>• **一致性**：b 在 M3 下会给出一份指导使用 skill 的契约，却没有任何 skill 可用。<br>**代价要讲清楚**（D1、§5.3）："数据目录下也拿到契约"只在 M2 成立。owner 想要这个效果，零代码的做法是在仓库 `.env` 设 `OMICSCLAW_SKILLS_DIR`（§5.4）。**这一变化正是 Q8 的来源。**c 兼有两者的复杂度。审核同意 a |
| Q3 | 工作目录里的同名文件是否作为补充追加 | **a** 保留补充段，接受风险；**b** 不做补充段；**c** 做补充段，但默认关闭；**d** 统一的目录信任机制（另开议题） | **b（第 2 版调整，偏离交接基线，记为 D9）。** 这不是安全上的理由，§6 表明补充段不扩大信任边界，a 与 b 在安全上等价。理由是：功能在 owner 的常规用法 M1 下不会触发；M2 下需要项目说明时，可以把契约和说明文件一起列进 `OMICSCLAW_SYSTEM_PROMPT_FILES`；b 省掉去重、符号链接、M5 这些逻辑和 4 个测试，也没有同一文件在 M2、M3 下呈现不对称的问题。**审核意见**：略倾向 b，a 也可接受。（已裁定 b，a 的设计已从正文删除） |
| Q4 | core-M2、core-M9 是否随本计划实施 | **a** 不随，主体落地后按 §10 单独对比；**b** 随主体一起；**c** 只把 O1 随主体 | **a。** 审核认为至少要删掉 "all 19 spatial skills remain fully functional"，这一点现已作为事实修正 FX4 并入主体，与 Q4 无关。剩下的 O1 只是措辞（"For backward compatibility…" 改为 "Users may also call you"），O2 会改变输出形态，都按"措辞另行对比"的规则延后。O1 的风险确实极低，owner 想省一轮对比时可以选 c。**审核意见**：部分不同意 a，认为至少应做事实部分，相当于 c；本版已用 FX4 满足 |
| Q5 | 仍放着 `SOUL.md`、`CLAUDE.md` 的旧工作目录要不要兼容 | a 不兼容；b 启动时发现旧文件就打警告；c 继续把旧文件作为回退读取 | **a**。`SPEC.md:47-48` 规定不加兼容垫片；单人部署；README 给出迁移说明。c 会让 dev-only 的 `CLAUDE.md` 在数据目录里继续被当作契约。审核同意 |
| Q6 | `OMICSCLAW_SYSTEM_PROMPT_FILES` 非空时的语义 | a 替换全部前置段；b 只替换契约，补充段照常追加（只在 Q3 = a 时有区别；Q3 已裁定 b，两者不再有差别） | **a**。与今天"替换那一对"的语义一致；做消融或基准测试时，前置段要完全由显式配置决定。Q8 的选项 b 也依赖这一点。审核同意 |
| Q7 | O3–O11 的处置 | a 另开一项"契约措辞与剪枝"，逐项做会话对比，可与审计遗留的行为改动同批；b 在本计划阶段 4 逐项实施；c 暂不处理 | **a**。它们都是行为改动，与审计遗留项同批可以共用会话对比的准备工作。O6、O8、O10 是本计划发现的缺口，O11 是主体为了不改变语义而留下的去重，建议排在前面。C9 的路径错误已作为 FX2 进入主体，不在 O 表。审核同意 |

---

## 15. 修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| 1 | 2026-09-27 | 初稿：以交接文档 §2.2 为基线；F1–F18 亲自核实；D1–D7；Q1–Q7 |
| 2 | 2026-09-27 | 按独立审核（"需小修"：阻断 2、重要 5、次要 9）修订，逐项见文首"第 2 版修订说明"。新增：F19–F22；E1–E5；D8、D9；§3.3 FX1–FX5；§3.4 N1–N9；§5.4；O9–O11；R12、R13；**Q8**；附录 C。§12 重写。S4、S7 改为保留。Q3 的推荐改为 b |
| 3 | 2026-09-27 | owner 在对话中裁定 Q1–Q8 全部按推荐项执行（Q1=a、Q2=a、Q3=b、Q4=a、Q5=a、Q6=a、Q7=a、Q8=b），记入 §14.1。状态改为"owner 已裁定，待实施"。正文按裁定收敛：删去补充段设计、相关代码草图说明和 4 个用例。写入 Q8 = b 的外部前置与时间约束，§12.2 新增第 6 步。按 App 源码更正 F22、§5.3、R9、Q2 中 App 的部署形态（有 `OMICSCLAW_DIR` 时为 M1；新后端没有 `/workspace` 路由），App 启动方式移出未核实清单 |

---

## 附录 A：渲染对比脚本（不入库，放在 `$B/render.py`）

用法：

```bash
PYTHONPATH=<repo> /opt/conda/envs/rapids_singlecell/bin/python $B/render.py before <repo> $B/render
```

改动后把 `before` 换成 `after` 再跑一次。脚本只用 `AppConfig`、`default_sections`、`build_prompt`，这几个名字在改动前后都存在。

```python
"""Render the default system prompt under four deployments and write text plus section stats."""
import json
import platform
import sys
import tempfile
from datetime import date
from pathlib import Path

from omicsclaw.entry.assembly import build_prompt, default_sections
from omicsclaw.entry.config import AppConfig

label, repo, out = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)


def render(name: str, config: AppConfig) -> dict:
    prompt = build_prompt(default_sections(config)).render()
    text = prompt.system_prompt.replace(str(config.workspace), "<workspace>")
    text = text.replace(str(repo), "<repo>").replace(date.today().isoformat(), "<today>")
    text = text.replace(f"{platform.system()} ({sys.platform})", "<platform>")
    (out / f"{label}-{name}.txt").write_text(text, encoding="utf-8")
    return {"sections": prompt.section_stats, "total": prompt.total_estimated_tokens}


with tempfile.TemporaryDirectory() as tmp:
    data = Path(tmp).resolve()
    extra = data / "extra.md"
    extra.write_text("extra front matter\n", encoding="utf-8")
    stats = {
        "R1": render("R1", AppConfig(workspace=repo)),
        "R2": render("R2", AppConfig(workspace=data, skills_dir=repo / "skills")),
        "R3": render("R3", AppConfig(workspace=data)),
        "R4": render("R4", AppConfig(workspace=repo, system_prompt_files=(extra,))),
    }
(out / f"{label}-stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
```

## 附录 B：逐字核对（一次性脚本，不入库）

**输入**
- `$B/tree/{CLAUDE,SOUL}.md`：改动前的工作树版本；
- 新的 `OMICSCLAW.md`、`CLAUDE.md`、`AGENTS.md`；
- 一张由 §3 转写的表，每行是 `(源文件, 起行, 止行, 去向)`，去向取值为 `contract`、`claude`、`agents`、`gone`。

**默认规则**：每行原文合并空白、去掉首尾空白后，按去向断言：
- `contract`：是新 `OMICSCLAW.md` 的子串；
- `claude`：是新 `CLAUDE.md` 的子串；
- `agents`：是新 `AGENTS.md` 的子串；
- `gone`：在新 `OMICSCLAW.md`、`CLAUDE.md` 中都不出现。

**§3.4 的豁免与特殊行**

| 行 | 处理 |
|---|---|
| C1、S1（N1） | 不核对 |
| C3（FX4） | 断言 "… can still refer to you as \"SpatialClaw\"." 在新文件中，且 "fully functional" 不在 |
| C4（N6） | 按句号切出 `CLAUDE.md:5` 的后半句，单独核对 |
| C7（N6） | 标题 `:45` 与正文 `:48-86` 分别核对；`:47`、`:87`（FX1）断言不在 |
| C9（FX2、FX3） | `:96-97` 与 `:106-107` 分别核对 §3.3 的改后句子，并断言原句不在；其余行按原文核对 |
| C12、C14、C20、C25（N3、N4、N6） | C12 连同原标题核对；C14 核对正文；C20 从 "**Known gap**" 起核对，并与 `### Desktop` 标题一起核对；C25 与 `### Channel — IM bots` 标题一起核对 |
| C22 | `agents` |
| C23（N9） | 断言改写后的句子 "The runtime contract every adapter shares is `OMICSCLAW.md`" 在 `AGENTS.md` 中，原句不在 |
| S3、C26（N8） | `gone` |
| S4、S6–S14 | `contract`，**编号按原文**（1–9） |

**输出**：每行的通过或失败状态，写进交付记录。

## 附录 C：阶段补丁的生成（只含本计划改动的块）

在仓库根执行，`$B` 与 §12.2 相同，`N` 为阶段号：

```bash
while read -r f; do
  if [ -e "$B/tree/$f" ]; then a="$B/tree/$f"; la="a/$f"; else a=/dev/null; la=/dev/null; fi
  if [ -e "$f" ]; then b="$f"; lb="b/$f"; else b=/dev/null; lb=/dev/null; fi
  diff -u --label "$la" --label "$lb" "$a" "$b"
done < "$B/files-phaseN.txt" > "$B/0063-phaseN.diff"
git apply --check -R "$B/0063-phaseN.diff"   # 生成后立即确认可以反向应用
```

- `--- /dev/null` 与 `+++ /dev/null` 分别标出新建与删除，`git apply` 能识别这两种情形。
- 补丁的原文一侧来自阶段 0 的工作树副本，所以只包含本计划的改动。前提是同一阶段内没有别的会话改动这些文件，这一点由 §12.3 第 8 步的逐块检查保证。
