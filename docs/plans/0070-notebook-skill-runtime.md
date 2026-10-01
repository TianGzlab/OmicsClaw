# 计划 0070：notebook 运行层与单细胞试点（`skills/_sdk/notebook/`、课题布局、契约、eval）

**状态**：定稿（第 3 版，2026-10-01）。已按独立审核意见和 owner 的裁定 O1 至 O6（§7.0）修订，§7.2 的 6 个问题已由 O6 全部裁定。owner 已同意派发实现：在本地分支 `plan-0070-notebook-runtime` 上每个阶段一个提交，不推送。实现完成后的独立评估和 owner 裁定 O7（§7.0）又带来一个修复提交，看门狗因此从 §1.3 移回本计划。

### 修订说明

**第 3 版（2026-10-01）**：按 owner 裁定 O5 修订（§7.0）。
- 不建 `PROJECT.md`，不新增 `## Project` 提示段：§3.11.3 改为只描述 `omicsclaw/entry/project.py` 的其余职责，原 G9 删除，原 G10 改称 G9。
- 不建 `METHODS_LEDGER.md`：D13 的"台账记为 ACCEPTED"落在 manifest 的 `status` 字段；`status` 子命令负责按需汇总；课题锁只留给 `new`；methods 汇总（`run.py methods`）列进 §1.3。
- `docs/analysis_strategy/STRATEGY.md` 吸收原 `PROJECT.md` 的内容，不注入系统提示，模板改为 Question、Data、Plan、Decisions 四段（附录 B.1）。契约要求开工前先跑 `status`、再读 `STRATEGY.md`（附录 A）。
- 连带修改：§0、§1.3、§2.1 的 D13 与 D14、§3.1、§3.2、§3.4、§3.5.2、§3.6、§3.10、§3.11、§3.12、§3.15.3 的第 2 号与第 7 号用例、§3.16、§4、§5、§6（R8、新增 R14）、Q4、附录 A、附录 B.1。
- 工作量重算为约 21.5 天。

**第 2 版（2026-10-01）**：按审核意见与 owner 裁定修订。
- owner 裁定 O1 至 O4 写进 §7.0。O1 砍掉的 8 项列进 §1.3"推迟到后续计划"，正文相应删除：R 步骤、`archive` 子命令、哈希缓存、看门狗、原 G7、`/recent` 用旧运行补足、`load_demo` 登记 bulk CSV、改写 `sc-integrate-cluster`。parity 每个 skill 只录默认参数加 1 个变体。
- O2：N-D 新增重录 `tests/entry/golden/` 的任务和验收（§3.11.8、N-D9）。
- O3：试点 skill 的示例和 parity 测试改用 `OmicsClaw` 环境的 pytest，基线也在这个环境里录；R4 随之改写。
- O4：0070 不动 `consensus-interpret`。所有"90 → 89"的连带改动撤销，计数保持 90。
- 审核应改项：
  - eval 里桩模块的 `__pycache__` 会写进 `tmp_path`，Runner 设 `PYTHONDONTWRITEBYTECODE=1`（§3.15.1）。
  - `run_cli` 跑完后遍历输出目录补记 `output`（§3.7）。
  - parity 基线改存实际数值，可逐值比较；R 方法不录基线（§3.13.6、Q2）。
  - 执行器核对调用它的解释器与 manifest 记录的解释器（§3.4.1，第 2 版记作 G10，第 3 版改称 G9）。
  - CI：nbclient、ipykernel 随 N-B1 加进 job1；job1 的 `-m` 加 `not skill_example`。
  - §5 第 4 条改为比较 CSV。
  - G3 如实写成"用户确认只靠契约"。
- 事实修正：
  - `tests/entry/test_assembly.py` 只需改 `:578`。
  - §3.11.6 的测试清单补 `test_overlay_real.py`、`test_ensemble_environment.py`。
  - 删去 N-A5 里对 `agent-skills.md` §9.3 的修改（那里没提 `notebook_export`）；§9.4 讲安全规则的那句改由 N-D8 处理。
  - 退出码表补上 `replay` 的 2。
  - §3.16 补 `tests/entry/test_ensemble_golden.py`。
  - 行号重新核过：`stubs.py:206`、`runner.py:70`、`test_boundary.py:51-57`、`loader.py:156-173`、`builtins.py:196-239`、`read.py:793`、`skillenv/tool.py:47-55`。
- 问题清单：原 Q2、Q6、Q7、Q10、Q12、Q14 写成计划内的决定；原 Q3 由 O4 裁定；原 Q13 作废；原 Q5 只留"是否设为门禁"。剩下 6 题重新编号为 Q1 至 Q6，新旧编号对照见 §7.1。
- 工作量按砍减后重算，合计约 22.5 天。

**第 1 版（2026-10-01）**：初稿。

**编号约定**：owner 在第 1 版之前的裁定记作 D1 至 D18（§2.1）；之后的裁定记作 O1 至 O5（§7.0）；开放问题 Q1 至 Q6（§7.2，第 2 版编号）；阶段 N-A 到 N-E，阶段内任务记作 N-B1-4、N-C0 这样；防线 G1 至 G9（§3.12）；风险 R1 至 R14。

**行号约定**：以 2026-10-01 的工作树为准（`HEAD` 为 `80925742`，工作树干净）。实施时按符号名重新定位。

**代码注释约定**：实现时写的 docstring 和注释只说明函数做什么、有什么前提，不写计划编号、阶段号和决策经过，这些留在本计划里。本计划里的代码示例也按这个写法。

**如何核实**：代码逐处读过，没有跑测试。另做了几项只读核对：
1. 用 skill loader 扫描 `skills/`：90 个 skill，目录名全部等于 frontmatter 的 `name`，其中 89 个带连字符；各域数目为 singlecell 31、spatial 18、bulkrna 14、genomics 10、proteomics 8、metabolomics 8、literature 1。
2. 在 `OmicsClaw` 与 `rapids_singlecell` 两个 conda 环境里检查导入：nbclient 0.10.4、nbformat 5.10.4、ipykernel（7.2.0 / 7.1.0）、jupyter_client 都在，jupytext 不在。
3. 读了已安装的 `jupyter_client/launcher.py` 与 `ipykernel/kernelapp.py`，确认 kernel 的启动方式和父进程轮询（§3.4.3）。
4. 读了 `tests/entry/test_ensemble_golden.py` 与 `tests/entry/golden/` 下的三个文件，确认哪些改动会改变 golden（§3.11.8）。

**前置与关联**：0062（`skills/_sdk/` 与零代码耦合，守卫 B1 至 B10，`PUBLIC_SURFACE`，统一的 `sys.path` 引导块）；0061（`install_skill_deps` 与 overlay）；0063（`OMICSCLAW.md` 与 `SAFETY_RULES`）；0067、0068（`omicsclaw/evals/`、`bash._locally` 打桩、`tests/ci_known_failures.txt`、PQ1 与 PQ4 对 consensus 的处理）。

---

## 0. 摘要

1. 在 `skills/_sdk/notebook/` 新建 notebook 运行层。步骤代码只用 5 个函数：`read_input`、`write_output`、`load_skill`、`load_demo`、`run_cli`。agent 通过一个命令行工具（下称"步骤执行器"，`skills/_sdk/notebook/run.py`）用 `bash` 运行步骤，子命令有 `new`、`run`、`status`、`replay`、`accept`、`revise`、`api`。Python 步骤由 nbclient 在一次性 kernel 里逐 cell 执行，执行结果直接存成 notebook。框架只读执行器写出的文件，0062 的零耦合边界不变。R 步骤推迟（§1.3）。
2. 课题布局按 D8 落地（§3.1），每个目录都写明归谁写。执行器的状态（记账、manifest、锁）全部放在 `results/<NN_slug>/provenance/` 下，不放 `.omicsclaw/`：sandbox 里 `.omicsclaw/` 被一个 1 MB 的 tmpfs 盖住（`sandbox/container.py:116-120`），容器里写进去的东西宿主机看不到。
3. 一个步骤的"过期"判定只看两样：步骤文件的 sha256，以及该步骤上次成功运行时经 `read_input` 读过的每个输入的 sha256。`replay` 在新的 kernel 里依次重跑模块的全部步骤，包括 validate 步骤。锁加在执行器这一层，用 `fcntl.flock`：模块锁管运行，课题锁只管 `new` 分配编号。执行器还核对调用它的解释器是否就是模块记录的那个（§3.4.1）。
4. `load_skill(name, root=None)` 在 skill 树里找名字等于 `name` 的目录，导入其中的 `_api.py`，返回一个代理模块；步骤运行中每次调用公开函数都记一条账。设了 `OMICSCLAW_SKILL_STUBS` 时改为加载桩模块，同时用 AST 核对桩里每个公开函数在真实 `_api.py` 里都存在，缺了就记 `stub_target_missing`。eval Runner 只读记账文件，不 import `skills.*`。
5. 框架侧：改写 `OMICSCLAW.md` 和 `SAFETY_RULES`（第 3 条按 D14 改写，附录 A 是草稿）；`## Environment` 段加一行执行器路径；课题级文档只有 `docs/analysis_strategy/STRATEGY.md`，不注入系统提示，契约要求开工前先跑 `status` 再读它（O5）；新增内置只读子 agent `module-reviewer`；`install_skill_deps` 改为接受一组 skill；channel 的 `/recent` 改读模块的 REPORT 和 manifest；重录 `tests/entry/golden/` 的 off 部署快照（O2）。
6. 单细胞试点 5 个 skill：`sc-qc`、`sc-preprocessing`、`sc-clustering`、`sc-cell-annotation`、`sc-de`。每个 skill 加 `_api.py`，`SKILL.md` 增加生成的 `## API` 段（有一致性测试）和一个跑 `load_demo` 的可执行示例，CLI 改成调用 `_api.py` 的薄壳。parity 基线在改造前用旧 CLI 在 `OmicsClaw` 环境里录，每个 skill 录默认参数加 1 个变体（O1、O3）。
7. 删除 4 个已禁用的 consensus 外壳；`consensus-interpret` 不动（O4）。eval 的 21 条非 skill 用例不动（交接文档写的 18 条已经过时，0068 加了 3 条），8 条 skill 用例改写成步骤文件加执行器的路径，CI 补装 nbclient 与 ipykernel。
8. 分五期，可以分别合入：N-A 清理（约 0.5 天）、N-B 运行层（N-B1 约 4 天，N-B2 约 2.5 天）、N-C 单细胞试点（约 6.5 天）、N-D 框架与契约（约 4 天）、N-E eval（约 4 天），合计约 21.5 个工作日。

---

## 1. 目标与非目标

### 1.1 目标

- agent 在课题 workspace 里按模块、按步骤写分析代码，执行器运行步骤并记账，每个模块产出可单独重放的代码、notebook、manifest 与 REPORT。
- skill 从"只有 CLI"变成"知识文档加私有函数库"：试点 5 个 skill 能在步骤里用 `load_skill` 调用，`## API` 段与代码保持一致，旧 CLI 的输出不变。
- 模块验收能走通：整模块重放与 validate、只读审查子 agent、用户确认后冻结。
- 脚本化 eval 覆盖新路径，每个 PR 都跑。
- 删除 4 个 consensus 外壳；交接文档列出的失效代码逐项给出处置。

### 1.2 非目标

- skill 的自动改进（进化循环），以及依赖它的评分接口、批量运行模式、候选版本晋级。`load_skill` 的 `root=` 参数按裁定保留，执行器只把 `root` 和候选目录名记进账，不设计晋级流程。
- 单细胞其余 26 个 skill、空间、bulkrna 的迁移；genomics、proteomics、metabolomics；bioSkills 的转换。
- 删除 CLI；调整 ensemble 与 bench。`spatial-domains` 的 CLI 和 `tuning.yaml` 不动。
- `consensus-interpret`（O4，按 D16 随 ensemble 处理）。
- `requires`/`produces` 前后置条件（D4 定在第二期）。
- 桌面 App 的界面（D14：本期只做后端）。
- 子 agent 改动的执行者归属（§7.1，只记哈希变化）。

### 1.3 推迟到后续计划（O1、O5）

| 项目 | 0070 里的处理 | 什么时候做 |
|---|---|---|
| R 步骤（`NN_xxx.R` 的执行与渲染，D10） | `LAYOUT` 的步骤文件只认 `.py`；模块里出现 `.R` 文件时，执行器报 "R steps are not supported yet" 并以退出码 2 结束 | 迁移调用 R 的单细胞 skill 时（其余 skill 里有 11 个） |
| `archive` 子命令 | 课题骨架照样建 `results/_archive/`；契约让 agent 在用户同意后直接用 `tar` 打包（附录 A） | 有需要时 |
| 哈希缓存 | 每次 `status` 都重新计算输入的 sha256 | 大文件让 `status` 明显变慢时 |
| 原 G7（桩模式横幅、`accept` 拒绝含桩运行的模块） | 记账里照样记 `stub: true`；只有 eval Runner 会设 `OMICSCLAW_SKILL_STUBS`，漏进真实会话的可能很小 | 有需要时 |
| `/recent` 用旧的 `output/` 运行补足 | `/recent` 只列模块；没有模块时回答 "No recent analyses found." | 不做，删 CLI 时一并处理 `/outputs` |
| `load_demo` 登记 `examples/` 下的 bulk CSV | 只登记 `pbmc3k_raw`、`pbmc3k_processed`、`pbmc68k_reduced` | 迁移 bulkrna 时 |
| methods 汇总（`run.py methods`，O5） | 不生成 `METHODS_LEDGER.md`；各模块的 skill 函数、参数摘要、版本与解释器都在 manifest 里，`status` 给出模块状态 | 需要为写作汇总方法时 |
| 改写 `sc-integrate-cluster` 对 consensus 的从属说法 | 它的 description 仍提到已删除的 `sc-consensus-integration`；模型照着去 `use_skill` 只会得到"不在 index 里"的提示 | 迁移单细胞其余 skill 时 |

---

## 2. 现状与证据

### 2.1 owner 已裁定（照此写，不重新讨论）

| 编号 | 裁定 |
|---|---|
| D1 | skill 是知识文档加私有函数库，由 LLM 写分析代码，产物是可交互、可复现的代码和 notebook。执行底座：文件经 `bash` 执行，不做常驻 kernel |
| D2 | `SKILL.md` 加本 skill 的私有模块；domain `_lib` 只放跨 skill 的稳定积木 |
| D3 | 方法学部分手写；`## API` 段从签名和 docstring 生成，有测试保证一致；每个 skill 带一个可执行的示例步骤，数据来自 `_sdk` 的 `load_demo`，CI 里真跑 |
| D4 | `_sdk` 提供 `load_skill(name, root=...)`，运行时记账，`root` 可以指向候选目录；`requires`/`produces` 放第二期 |
| D5 | manifest 里的 skill 版本以 git commit 加"有无未提交改动"为主；候选版本用目录名标识；内容哈希只附带记录，不做校验 |
| D6 | 过渡期 CLI 改成调用私有模块的薄壳，用 parity 测试保证新旧结果一致；evals 和 ensemble 改完以后再删 CLI |
| D7 | notebook 运行层（执行器、渲染、重放、provenance）放在 `skills/_sdk/`；框架只读它写出的文件，0062 的零耦合边界不变 |
| D8 | workspace 就是课题根：`analysis/<NN_slug>/` 只放代码（README 加编号步骤文件，字母后缀表示变体，含 validate 步骤）；`results/<NN_slug>/` 只放输出（figures、tables、intermediate、logs、notebooks、provenance、reviews、baseline、`M<NN>_<slug>_REPORT.md`）；另有 `results/_archive/`、`data/`（只读）、`docs/analysis_strategy/`、`manifests/`、`scripts/`、`work/`、`.omicsclaw/` |
| D9 | 一个步骤一个 percent 格式文件，显式调用 `read_input`/`write_output` 并登记 provenance；过期看"文件哈希加输入哈希"；执行器不往代码里注入任何东西，脚本可以单独运行；模块 notebook 由各步骤渲染后拼接，转换器基于 nbformat 自己写 |
| D10 | 允许 `NN_xxx.R` 步骤：`Rscript` 无状态执行，通过 intermediate 文件交换数据，渲染成"代码加日志"（O1 推迟到后续计划） |
| D11 | 一个模块对应一个分析阶段，产出可单独报告的图表，按创建顺序两位编号；下游只读上游的 `results/<NN>/intermediate|tables`；开新模块由 agent 判断，开之前告知用户，拿不准就问；每个模块一个 overlay 环境，依赖取所用 skill 的并集，`install_skill_deps` 接受一组 skill，执行器把解释器记进 manifest |
| D12 | `intermediate/` 一律保留；修订已验收的模块前，小文件整份快照到 `baseline/<日期>_pre_revision/`，大文件只记 sha256；被推翻的版本按需打包进 `_archive`；哈希只作记录，不当闸门 |
| D13 | 验收三步：新进程里整模块重放并跑 validate；内置只读审查子 agent 给出 APPROVE 或 REVISE，写进 `reviews/`；用户确认后台账记为 ACCEPTED，manifest 标记冻结。用户可以要求跳过审查（O5："台账"落在 manifest 的 `status` 字段） |
| D14 | 课题级文档：`STRATEGY.md` 由 agent 与用户一起写（O5：只保留它，`METHODS_LEDGER.md` 与 `PROJECT.md` 及其提示段都不建）。契约：每个步骤如实列出调用了哪些 skill 函数；有 skill 函数能覆盖的步骤必须用，不用要写明理由；SAFETY 3 改为"skill 没给定的参数要写明取值和依据"，"不编造基因关联"保留；免责声明写进 REPORT；`/recent` 改读模块的 REPORT 或 manifest；本期只做后端 |
| D15 | 密闭 eval：执行器真跑，`load_skill` 在 eval 模式下返回桩模块，断言基于记账；桩在真实模块里找不到同名函数时报 `stub_target_missing`；非 skill 用例不动，8 条 skill 用例重写；CI 补装 nbclient 和 ipykernel |
| D16 | 迁移顺序：先单细胞试点主链，再单细胞其余、空间（`spatial-domains` 最后）、bulkrna；4 个已禁用的 consensus 外壳删除；`consensus-interpret` 跟 ensemble 一起处理 |
| D17 | 第 9 轮：`data/` 只读只写进契约，不加权限闸门（闸门挡得住 `write_file`，挡不住 `bash`）；第一次建模块时只补齐缺的目录，不移动用户已有的文件；同一会话里 `bash`、`write_file`、`edit_file`、`task` 都是 `concurrency_safe=False`，由引擎串行，跨会话由执行器按模块加锁；子 agent 可以改父 agent 的模块，改动记进记账；sandbox 镜像要装 nbclient、ipykernel，有 R 步骤时还要 Rscript；以后的 benchmark 一个 case 对应一个模块 |
| D18 | 流程：子 agent 写计划，另一个子 agent 审核，owner 过目，认可之前不写生产代码；实现由 owner 派发 |

之后的裁定 O1 至 O5 见 §7.0。

### 2.2 代码事实

**harness 侧**

- workspace：`AppConfig.workspace` 没有默认值（`entry/config.py:165`），`resolve_app_config` 在没给时取 `Path.cwd()`（`:1331`）。`skills_root()` 没设 `skills_dir` 时是 `<workspace>/skills`（`:582-590`），`repo_root()` 是它的父目录（`:620-622`）。所以不设 `OMICSCLAW_SKILLS_DIR` 的部署里，workspace 就是 OmicsClaw 的 checkout（见 Q4）。
- `bash`：cwd 固定为 workspace 根（`tools/builtin/bash.py:657`）。本机执行由 `_locally`（`:806`）以新 session 起 `bash -c`，环境是 `os.environ` 去掉控制面凭据（`:888-897`）；超时或取消时杀整个进程组。sandbox 执行走 `BashEnvironment.run_bash`（`:420`）。工具超时默认是 `tool_timeout_s - 15`，即 585 s（`entry/config.py:697-708` 的 `bash_timeout`）。
- `bash`、`write_file`、`edit_file`、`task` 的策略都是 `concurrency_safe=False`（`bash.py:519`、`write.py:233`、`edit.py:211`、`subagent/task_tool.py:23`），引擎据此串行派发（`engine/executor.py:334`）。
- sandbox：每条命令一次 `docker exec --workdir <cwd> <container> bash -c WRAPPER`（`sandbox/environment.py:97-136`）。`WRAPPER` 先记下自己的 pid 再 `exec bash -c "$1"`（`:22`），超时只 `kill -KILL` 这一个 pid（`:31`），不杀进程组。容器的挂载（`sandbox/container.py:109-121`）：workspace 读写，挂在与宿主机相同的路径；`<repo>/omicsclaw` 和 `<repo>/skills` 只读（`entry/config.py:624-640`，workspace 本身包含 repo 时不另挂）；`<workspace>/.env` 盖成 `/dev/null`；`<workspace>/.omicsclaw` 盖成 1 MB 的 tmpfs，里面只把 `.omicsclaw/sandbox` 交换目录重新挂回去；`HOME=/tmp`（`:95`），`/tmp` 是 tmpfs；网络默认 `none`（`entry/config.py:464`）；可选 `--user <宿主机 uid>`。repo 的 `data/`、`examples/`、`.git` 都不挂进容器。仓库里没有 sandbox 镜像的 Dockerfile，镜像由部署者通过 `sandbox_image` 提供（`:460`）。
- sandbox 正在运行时不挂 `install_skill_deps`（`entry/skill_env.py:98-100`），容器里的解释器就是镜像里的那个。
- 提示词：`default_sections` 的顺序是 contract → safety → tools → [planning] → [sandbox] → [skills] → environment → [memory]（`entry/assembly.py:596-689`）。`_front_matter` 在设了 `system_prompt_files` 时用这些文件整份替换 `OMICSCLAW.md`（`:564-576`）。`text_from_file` 在文件不存在时返回空串，整个 section 随之消失；文件存在但解码失败时抛异常（`context/sections.py:89-112`）。`tests/entry/test_assembly.py:430`、`:444` 钉住了 section 的 key 序列。
- `SAFETY_RULES` 四条在 `assembly.py:228-236`，`TOOL_GUIDANCE` 在 `:244-252`。`tests/entry/test_assembly.py:578` 断言提示里有 "SKILL.md methodology only"，`:579` 断言有 "Warn before overwriting"，`:597` 断言 `skills._sdk.report.DISCLAIMER in SAFETY_RULES`。
- golden：`tests/entry/test_ensemble_golden.py` 要求 `ensemble=False` 的部署与 `tests/entry/golden/ensemble_off_prompt.txt`、`ensemble_off_tools.json` 逐字节相同；`ensemble=True` 时提示词不变，`memory_write` 与 `task` 之间的工具块等于 `ENSEMBLE_TOOLS[mode]`，块外的工具与 off 的 golden 相同。用 `OMICSCLAW_WRITE_GOLDEN=1` 重录，文件头写明只在有意改动提示词或工具时重录。golden 部署的 `skills_dir` 是 `tests/ensemble/fake_skills`，旁边没有 `OMICSCLAW.md`，所以提示词从 "## Safety rules" 开始。这个测试在 `tests/entry` 下，属于 CI job1。
- 子 agent：内置的只有 `general-purpose`（`entry/subagent.py:117-135`），`build_subagent_registry` 以它开头再加文件定义（`:171`）。`SubAgentDefinition.tools` 是允许清单，`skills` 预加载 skill 正文（`subagent/definition.py`）。`tests/entry/test_subagent_wiring.py:234`、`:281` 钉住 `names() == ("general-purpose",)`。
- `read_file` 不能列目录（`tools/builtin/read.py:793`）；仓库里列目录、找文件都靠 `bash`（`bash.py:238-243` 的说明）。
- `install_skill_deps`：参数是单个 `skill` 加 `packages`（`skillenv/tool.py:57-70`）；每个包必须在这个 skill 的 `## Dependencies` 里；overlay 的 key 由基础环境和 requirement 规格算出（`skillenv/overlay.py:163`），与 skill 名无关；`OverlayRequest.skill` 只写进 `.meta.json`（`overlay.py:892`）。overlay 用 `fcntl` 文件锁防止并发构建（`overlay.py:920`）。
- 审批：`default` 模式下用户可以对整个会话放行 `bash`（`docs/core-features/agent-skills.md` §9.4），之后的 `bash` 命令不再出审批卡。
- channel `/recent` 读 `<workspace>/output/<run>/report.md` 的第一个一级标题（`entry/channel/commands/builtins.py:196-239`），测试在 `tests/entry/test_channel_commands.py:215-264`。
- 框架在运行时用 `ast.literal_eval` 读 `_sdk` 的纯字面量已有先例：`skillenv/registry.py:115` 读 `skills/_sdk/deps.py` 的 `DEPENDENCIES`。

**skill 侧**

- `skills/_sdk/`：顶层 11 个模块加 `r_scripts/`，`__init__.py` 只定义 `REPO_ROOT`（`skills/_sdk/__init__.py`）。`DISCLAIMER` 在 `skills/_sdk/report.py:12-16`。
- 主脚本带统一的 `sys.path` 引导块，以 `skills/_sdk/__init__.py` 为锚（`tests/sdk/test_bootstrap.py:36-43`）。
- skill loader 只读 `name`、`description`、`trigger`、`tags`（`skills/loader.py:156-173`），跳过 `.` 开头的目录和 `__pycache__`、`node_modules`，`_` 开头的目录照样扫描（0068 §8.2 第 1 条）。
- 4 个 consensus 外壳（`sc-consensus-clustering`、`sc-consensus-integration`、`sc-consensus-pseudotime`、`consensus-domains`）的 `SKILL.md` 已改名为 `SKILL.md.disabled`，目录里还有脚本、`references/`，其中两个有 `tests/`。`consensus-interpret` 读取的是 `consensus-domains` 和 `sc-consensus-clustering` 的产物（`skills/spatial/consensus-interpret/_run_reader.py:1-9`）；按 0068 PQ4（`docs/plans/0068-eval-hardening.md:682`）它默认走结构化路径，留在 index 里。
- 试点 skill 的现状：`sc_qc.py` 801 行、`sc_preprocess.py` 1174 行、`sc_cluster.py` 1027 行、`sc_annotate.py` 1746 行、`sc_de.py` 927 行。计算逻辑已经大多写成函数（如 `sc_cluster.py:345` 的 `run_clustering`、`sc_annotate.py:337-730` 的各 `annotate_*`、`sc_de.py:160-288` 的各 `run_de_*`），与报告、画图、`result.json` 写出混在同一个文件里。demo 数据由 `skills/singlecell/_lib/io.py:273` 的 `load_repo_demo_data` 提供：先找 `<repo>/data/` 与 `<repo>/examples/`，找不到就用 scanpy 下载并写进 `<repo>/data/`。仓库不跟踪任何 `.h5ad`（`.gitignore` 的 `data/*`、`*.h5ad`）。
- Leiden：`skills/singlecell/_lib/dimred.py:684` 调 `sc.tl.leiden`。`rapids_singlecell` 环境缺 leidenalg 和 igraph，这一行会抛 `ImportError`；`OmicsClaw` 环境有 pytest、leidenalg、igraph、nbclient、ipykernel（O3）。
- 环境：`environment.yml:275-277` 声明了 nbformat、jupyter_client、ipykernel；nbclient 没有直接声明，是 `nbconvert`（`:298`）带进来的。`tests/test_pyproject_thin_pip_layer.py` 把 nbformat、jupyter-client、ipykernel 列为 conda 管理的包。
- `.gitignore` 全局忽略 `*.ipynb`、`*.jsonl` 和 `*.gz`。

**eval 侧**

- 用例共 29 条（`tests/evals/test_dataset_floor.py:15`），8 条在 `skill_routing` 类：7 个域各一条加 `output_lands_on_disk`（`tests/evals/dataset/test_skill_routing.py`）；其余 21 条不是 skill 用例。
- skill 打桩：`omicsclaw/evals/stubs.py:166` 的 `find_skill_run` 识别 `python <skill 目录>/<脚本>.py`，`stubbed_skill_runs`（`:206`）替换 `bash._locally`。`tests/evals/test_fixtures.py` 从 `test_skill_routing` import `ROUTES`；live eval 的 conftest 读 `tests/evals/fixtures/skill_runs/`（`tests/evals/live/conftest.py:27`）。
- Runner 在 `tmp_path` 下建 `ws`、`outside`、`home`，`HOME` 指向 `tmp_path/home`，运行前后对整个 `tmp_path` 做快照（`omicsclaw/evals/runner.py:160-171`），`NoWriteOutside()` 默认只允许 workspace 内的改动（`assertions.py:326-354`）。所以 kernel 往 `$HOME` 写的文件、桩模块旁边生成的 `__pycache__` 都会让用例失败（§3.4.3、§3.15.1）。用例超时 30 s（`runner.py:70`）。
- CI（`.github/workflows/eval.yml`）：job1 装科学栈但不装 scanpy，命令行显式传了 `-m "not slow and not demo and not eval and not scripted_eval"`，会覆盖 `addopts` 里的 `-m`；job2 只装 `-e . pytest`。

**测试与守卫**

- `tests/sdk/test_bootstrap.py:86-88` 要求恰好 90 个主脚本；`main_scripts()`（`:53-59`）只看有 `SKILL.md` 的目录里不以 `_` 开头的 `*.py`。4 个外壳已经不算在内。
- `tests/sdk/test_boundary.py:51-57` 的 `B3_KNOWN` 正好是这 4 个外壳的 `omicsclaw.runtime.consensus.run` 导入。
- `tests/sdk/test_public_surface.py` 冻结 `_sdk` 的公开面，`_sdk_modules()`（`:48-50`）只看 `_sdk` 顶层的 `*.py`。
- `tests/launch/test_grammar.py:350-353` 要求 `[project.scripts]` 恰好是 `omicsclaw` 和 `oc` 两个入口。
- `tests/launch/test_surfaces.py` 在装了 fastapi 的解释器下会真的起服务并挂住，所以不能用 `OmicsClaw` 环境的 pytest 跑它（O3）。

### 2.3 对交接文档与任务说明的更正

1. "删掉 4 个外壳后 `test_bootstrap.py` 的 90 会变"：不会。`main_scripts()` 以 `SKILL.md` 定位脚本，4 个外壳的 `SKILL.md` 早已改名为 `SKILL.md.disabled`，90 里本来就不含它们（测试 docstring 就是这么写的）。0070 不动 `consensus-interpret`（O4），所以 90 在本计划里保持不变。
2. "18 条非 skill 用例"：现在是 21 条。0068 加了 `safety/protected_dotenv_asked_in_auto_mode`、`safety/subagent_approval_reaches_session`、`error_handling/unknown_tool_is_observation`，`BASELINE = 29`。
3. "已有 nbclient 0.10.4、nbformat、ipykernel（`environment.yml:275-277`）"：那三行是 nbformat、jupyter_client、ipykernel。nbclient 装在环境里，但只是 nbconvert 的依赖，没有直接声明。N-B1 在 `environment.yml` 里补一行。
4. "workspace 默认就是 cwd（`config.py:165`）"：`:165` 是字段声明，没有默认值；取 cwd 的地方在 `resolve_app_config`（`:1331`）。
5. "`tests/ensemble/test_tuning_matches_argparse.py` 会受影响"：0070 不受影响。全仓只有 `spatial-domains` 有 `tuning.yaml`，它不在试点里。等 `spatial-domains` 迁移时才会碰到。
6. "sandbox 镜像要装 nbclient、ipykernel"：仓库里没有镜像定义，镜像由部署者提供。本计划能做的是文档说明，以及执行器在缺包时给出明确的报错（N-B1、N-D8）。
7. 任务说明列的已知无关失败里，`tests/test_control_plane_documentation_contract.py` 已在 0068 H-H1 删除，现在只剩 `tests/tools/test_workspace.py`，外加 `tests/ci_known_failures.txt` 里的 6 条。
8. 交接文档没有提到 `tests/entry/test_ensemble_golden.py`：0070 改 `SAFETY_RULES` 和 `task` 工具的描述，这条测试会失败，需要重录 golden（O2，§3.11.8）。

---

## 3. 设计

### 3.1 课题目录布局与文件归属

workspace 就是课题根（D8）。下表的"写入者"决定了执行器、agent、用户各自的责任，也决定了哪些路径可以由执行器校验。

| 路径 | 内容 | 写入者 |
|---|---|---|
| `data/` | 用户的输入文件 | 用户；契约规定只读（D17，不加闸门） |
| `docs/analysis_strategy/STRATEGY.md` | 课题的问题、数据、跨模块的分析计划与顺序、跨模块的决定 | 执行器在缺失时写模板（附录 B.1），之后由 agent 与用户编辑；不注入系统提示，契约要求开工前先读（O5） |
| `manifests/` | 数据清单：输入的来源、样本表、校验和 | agent |
| `scripts/` | 不属于任何模块的课题级辅助脚本（例如下载脚本） | agent |
| `work/` | 草稿，可随时删除 | agent |
| `analysis/<NN_slug>/README.md` | 模块的目的、上游模块、步骤列表、关键决定 | `new` 写模板，agent 填写 |
| `analysis/<NN_slug>/<k>[v]_<name>.py` | 步骤文件，含一个 `<k>_validate.py` | agent（子 agent 也可以改，D17） |
| `results/<NN_slug>/figures/`、`tables/`、`intermediate/`、`logs/` | 步骤的输出 | 步骤代码经 `write_output` 写；`run_cli` 的输出进 `intermediate/<skill>/`；`logs/<step>.log` 由执行器写 |
| `results/<NN_slug>/notebooks/` | 每个步骤执行后的 notebook，以及拼接成的 `M<NN>_<slug>.ipynb` | 执行器 |
| `results/<NN_slug>/provenance/` | `manifest.json`、`runs/<step>/<run_id>.jsonl`（记账）、`.lock` | 执行器 |
| `results/<NN_slug>/reviews/<YYYY-MM-DD>_review.md` | 审查子 agent 的结论原文 | agent 用 `write_file` 写入子 agent 的回复 |
| `results/<NN_slug>/baseline/<YYYY-MM-DD>_pre_revision/` | 修订前的快照 | 执行器（`revise`） |
| `results/<NN_slug>/M<NN>_<slug>_REPORT.md` | 模块报告，含免责声明 | agent |
| `results/_archive/` | 被推翻版本的压缩包 | agent 在用户同意后用 `tar` 打包（`archive` 子命令推迟，§1.3） |
| `results/.project.lock` | 课题锁 | 执行器 |
| `.omicsclaw/` | 框架状态（记忆、计划、审批规则……） | 框架；执行器不读不写 |

命名规则（`skills/_sdk/notebook/contract.py` 的 `LAYOUT` 字面量是唯一来源，框架侧的常量由契约测试钉住，§3.2.3）：

- 模块目录：`^(\d{2})_([a-z0-9][a-z0-9_]*)$`，例如 `03_clustering`。编号由 `new` 按已有最大编号加一分配。
- 步骤文件：`^(\d{2})([a-z]?)_([a-z0-9][a-z0-9_]*)\.py$`，按文件名排序执行。字母后缀表示变体（`02a_leiden.py`、`02b_louvain.py`），变体都会运行。
- validate 步骤：名字是 `<k>_validate.py`，每个模块恰好一个，执行器总是最后运行它。
- REPORT：`M<NN>_<slug>_REPORT.md`，例如 `M03_clustering_REPORT.md`。

第一次 `new` 时补齐课题骨架（D17）：只创建缺失的目录（`analysis/`、`results/`、`results/_archive/`、`data/`、`docs/analysis_strategy/`、`manifests/`、`scripts/`、`work/`）和缺失的模板文件 `docs/analysis_strategy/STRATEGY.md`，已有的文件和目录一律不动、不移动、不改名。workspace 根下已有的散落文件（比如用户直接放在根目录的 `pbmc.h5ad`）留在原处，`read_input` 可以读它们，但会记一条 `outside_contract` 警告（G6）。

### 3.2 `skills/_sdk/notebook/`：包结构与接口

#### 3.2.1 包结构

```
skills/_sdk/notebook/
  __init__.py     步骤代码的接口：read_input, write_output, load_skill, load_demo, run_cli
  __main__.py     python -m skills._sdk.notebook，转到 run.main()
  run.py          按路径调用的执行器入口（带统一的 sys.path 引导块）
  contract.py     框架和测试读取的纯字面量：LAYOUT, MANIFEST_SCHEMA, LEDGER_EVENTS, ENVIRONMENT
  _layout.py      课题根、模块、步骤的定位与命名校验
  _hashing.py     文件与目录的 sha256
  _ledger.py      记账：写（kernel 内与执行器）、读
  _manifest.py    manifest 的生成与读写，以及 status 的汇总
  _percent.py     percent 文本到 nbformat 的转换
  _runners.py     StepRunner 与 PythonKernelRunner（nbclient）
  _executor.py    run / status / replay：过期判定、加锁、解释器核对、记账生命周期、渲染拼接
  _acceptance.py  accept / revise / baseline
  _skills.py      skill 目录解析、导入 _api.py、记账代理、桩模式、run_cli
  _io.py          read_input / write_output / load_demo 的实现与 demo 注册表
  _lock.py        fcntl 锁
  _apidoc.py      ## API 段的生成与校验
  templates/      STRATEGY.md、模块 README.md 的模板
```

依赖：只用标准库。nbformat 和 nbclient 在 `_percent.py`、`_runners.py` 的函数体内导入，anndata、pandas、matplotlib 按对象类型在 `_io.py` 的函数体内导入。所以 `import skills._sdk.notebook` 在只有标准库的解释器里也能成功，步骤文件单独运行时不需要 nbclient。B5（`_sdk` 不 import 框架和别的 skill）照常成立。

#### 3.2.2 步骤代码的接口

```python
def read_input(path: str | os.PathLike, *, reader: Callable[[Path], Any] | None = None) -> Any:
    """Load a file or directory the step reads, and record its path and sha256.

    The path is relative to the project root. Without a reader the loader is
    chosen by suffix (.h5ad, .csv, .tsv, .json, .parquet, .txt, .md); any other
    suffix returns the Path itself.
    """

def write_output(obj: Any, path: str | os.PathLike, *,
                 writer: Callable[[Any, Path], None] | None = None) -> Path:
    """Write one output of the current module atomically and record its sha256.

    The path is relative to results/<NN_slug>/ and starts with figures/, tables/,
    intermediate/ or logs/. Without a writer the format follows the suffix and the
    object's type. Returns the absolute path written.
    """

def load_skill(name: str, *, root: str | os.PathLike | None = None) -> ModuleType:
    """Return skill `name`'s function library.

    Inside a step run every call to a public function is recorded. `root` is a
    skills tree; None is the tree that contains this _sdk.
    """

def load_demo(name: str) -> Any:
    """Load a registered demo dataset and record it as an input of the step."""

def run_cli(skill: str, *args: str, inputs: Sequence[str] = (),
            timeout: float | None = None) -> Path:
    """Run a skill's command-line script for the current step and return its output directory.

    The output directory is results/<NN_slug>/intermediate/<skill>/ unless args
    carry --output inside the module's results. `inputs` lists project-relative
    files the run reads, so they count towards staleness.
    """
```

错误一律用内建异常的子类（`LookupError`、`ValueError`、`RuntimeError`），不导出自定义异常类：步骤代码按内建类型就能捕获，公开面也保持 5 个名字。

"当前步骤"和"当前模块"怎么确定：执行器给 kernel 设 `OMICSCLAW_STEP_FILE`；单独运行时（`python analysis/03_clustering/02_cluster.py`）取 `sys.argv[0]`，它必须位于 `analysis/<NN_slug>/` 下，否则 `write_output` 报错并说明原因。课题根是 `analysis/` 的父目录，与 cwd 无关。

单独运行时没有记账文件（`OMICSCLAW_STEP_LEDGER` 未设），5 个函数照常工作，只是不记账，并在第一次调用时往 stderr 打一行提示。这样 D9 的"脚本可以单独运行"成立；单独运行的前提是 `skills` 可以导入（设 `PYTHONPATH=<checkout>`，或者 OmicsClaw 已安装），模块 README 模板里写明这条命令。

#### 3.2.3 执行器（agent 通过 `bash` 用的接口）

入口：`python <skills 根>/_sdk/notebook/run.py <子命令>`，cwd 为课题根（`bash` 的 cwd 本来就是 workspace 根）。`sandbox_code_in_image` 的部署里宿主机路径在镜像里不一定存在，改用 `python -m skills._sdk.notebook <子命令>`。不加 console script：`tests/launch/test_grammar.py:350-353` 钉死了只有两个入口，而且 sandbox 里代码是挂载进去的，不一定装成了包。

| 子命令 | 作用 | 退出码 |
|---|---|---|
| `new <slug>` | 分配下一个编号，建 `analysis/<NN_slug>/README.md` 与 `results/<NN_slug>/` 的子目录；第一次运行时补齐课题骨架（含 `STRATEGY.md` 模板） | 0；命名非法为 2 |
| `run <模块目录或步骤文件>... [--force]` | 模块目录：按顺序运行所有过期步骤（validate 最后）。步骤文件：只跑这一个，没过期时跳过，`--force` 强制运行 | 0；有步骤失败为 1；模块里有 `.R` 文件为 2；锁被占为 3 |
| `status [<模块目录>]` | 从各模块的 manifest 汇总：每个模块的状态（`DRAFT`、`REPLAYED`、`REVIEWED`、`ACCEPTED`，修订中的标 `revising`）、每个步骤是否过期及原因、调用过的 skill 函数；不加锁 | 0 |
| `replay <模块目录> [--new-interpreter "<原因>"]` | 在新 kernel 里依次重跑全部步骤（含 validate），比较输出，记一次重放 | 0；失败为 1；没有或多于一个 validate 步骤、模块里有 `.R` 文件、解释器与 manifest 不一致且没给 `--new-interpreter` 时为 2；锁被占为 3 |
| `accept <模块目录> (--review <文件> \| --skip-review "<用户原话>")` | 核对验收条件，记 ACCEPTED 并冻结 | 0；条件不满足为 4 |
| `revise <模块目录>` | 给已验收的模块做 baseline 快照并解冻 | 0 |
| `api <skill 目录> (--check \| --write)` | 校验或重写 `SKILL.md` 的 `## API` 段 | 0；不一致为 1 |

输出是给 agent 看的纯文本，每个步骤一段，例如：

```
[03_clustering] 02_cluster.py  ok  41.8 s  python=/…/envs/OmicsClaw/bin/python (3.11.9)
  read:     results/02_preprocess/intermediate/adata.h5ad
  skills:   sc-clustering.cluster(resolution=0.8), sc-clustering.cluster_summary()
  wrote:    intermediate/adata.h5ad, tables/cluster_summary.csv, figures/umap_leiden.png
  notebook: results/03_clustering/notebooks/02_cluster.ipynb
  output (last 30 lines):
  …
```

失败时给出出错的 cell 序号、异常类型、traceback 末尾 40 行，以及已保存的部分 notebook 路径。`bash` 自己会把超过 16,000 字符的输出截掉，执行器把每段输出控制在 2,000 字符以内。

`contract.py` 只放纯字面量，框架侧和测试侧都能用 `ast.literal_eval` 读取，做法与 `deps.py` 的 `DEPENDENCIES` 相同：

```python
LAYOUT = {
    "module_dir": r"^(\d{2})_([a-z0-9][a-z0-9_]*)$",
    "step_file": r"^(\d{2})([a-z]?)_([a-z0-9][a-z0-9_]*)\.py$",
    "validate_step": r"^\d{2}[a-z]?_validate\.py$",
    "report": "M{nn}_{slug}_REPORT.md",
    "output_dirs": ["figures", "tables", "intermediate", "logs"],
    "runner_dirs": ["notebooks", "provenance", "reviews", "baseline"],
    "manifest": "provenance/manifest.json",
    "runs": "provenance/runs",
    "strategy_file": "docs/analysis_strategy/STRATEGY.md",
    "archive_dir": "results/_archive",
}
ENVIRONMENT = {
    "step_file": "OMICSCLAW_STEP_FILE",
    "step_ledger": "OMICSCLAW_STEP_LEDGER",
    "skill_stubs": "OMICSCLAW_SKILL_STUBS",
    "demo_dir": "OMICSCLAW_DEMO_DIR",
}
```

`MANIFEST_SCHEMA` 和 `LEDGER_EVENTS` 见 §3.5。

#### 3.2.4 内部 seam

- `StepRunner`：接口是 `run(step, env, workdir) -> StepOutcome`（状态、执行后的 notebook 节点、耗时、错误）。0070 只有 `PythonKernelRunner` 一个生产 adapter；测试里的同进程假 runner 是第二个 adapter，用来测过期判定和记账，不必起 kernel。以后加 R 步骤时，`RscriptRunner` 接在这里。
- skill 来源：真实的 `_api.py` 与桩目录两个 adapter，由 `OMICSCLAW_SKILL_STUBS` 选择（§3.7）。

记账写出和时钟只有一个实现，不做成 seam，测试时通过参数注入时钟与目录。

### 3.3 步骤文件格式

步骤文件是普通的 Python 文件，用 percent 注释分 cell。转换器只认下面这个子集，规则写进 `_percent.py` 的模块说明：

- 第一个 `# %%` 之前的非空内容算第一个代码 cell。
- `# %%` 开始一个代码 cell；同一行后面的文字记进 cell 的 metadata（`title`）。
- `# %% [markdown]` 或 `# %% [md]` 开始一个 markdown cell；其中每行去掉开头的 `# ` 或 `#`，空行保留。
- 别的方括号标签一律报错，并指出行号。
- 每个 cell 末尾的空行去掉；代码 cell 的内容原样保留。
- 代码 cell 里以 `%` 或 `!` 开头的行报错（G8）：notebook 魔法和 shell 行会让文件无法用 `python <file>` 单独运行。

notebook 的 metadata 写入 `kernelspec`（python3）、`language_info` 和 `omicsclaw.step`（文件名、sha256、run_id）。

agent 写步骤时要遵守的约定由契约规定（附录 A），执行器只校验上面这些格式问题：

- 第一个 markdown cell 说明这一步做什么、读什么、调用了哪些 skill 函数（D14 的"如实列出"）。记账会记下实际调用，审查子 agent 对照两者。
- 所有输入经 `read_input`，所有输出经 `write_output`。直接用 `pd.read_csv` 读的文件不会被记账，过期判定也看不到它，这是已知的局限（R9）。
- skill 没给定的参数写明取值与理由（SAFETY 3）。

### 3.4 一个步骤从写好到执行完的路径

#### 3.4.1 本机

```
agent: write_file analysis/03_clustering/02_cluster.py
agent: bash "python <skills>/_sdk/notebook/run.py run analysis/03_clustering"
  └─ GatedTool → HookedTool → BashTool.execute → _locally            (bash.py:639, :806)
       └─ bash -c（新 session，cwd=workspace，env=os.environ 去掉控制面凭据）
            └─ run.py：统一引导块把 checkout 根放进 sys.path → _executor
                 1. 定位课题根与模块，校验命名；取模块锁 results/03_clustering/provenance/.lock（§3.6）
                 2. 读 manifest；核对解释器（见下）；对每个步骤做过期判定（§3.6），得到要跑的步骤列表
                 3. 对每个要跑的步骤：
                    a. 生成 run_id，新建 provenance/runs/02_cluster/<run_id>.jsonl，写 run_start
                       （步骤 sha256、上次的 sha256、解释器路径与版本、overlay 元数据、桩目录）
                    b. _percent：文件 → nbformat 节点
                    c. PythonKernelRunner：在临时目录写一个 kernelspec，argv 指向执行器自己的
                       sys.executable；NotebookClient(..., km=…).execute(cwd=课题根, env=…)
                       env = 当前环境
                           + PYTHONPATH=<checkout 根>:原值
                           + OMICSCLAW_STEP_FILE、OMICSCLAW_STEP_LEDGER
                           + IPYTHONDIR、JUPYTER_RUNTIME_DIR、JUPYTER_DATA_DIR 指向本次运行的临时目录
                    d. kernel 里，步骤代码调用 read_input / load_skill / write_output，
                       各自往 OMICSCLAW_STEP_LEDGER 追加 input / skill_load / skill_call / output 事件
                    e. 执行完（或在某个 cell 出错），把带输出的 notebook 写到 notebooks/02_cluster.ipynb，
                       stream 输出写到 logs/02_cluster.log，追加 run_end
                    f. 重新判定后面的步骤是否过期（§3.6）
                 4. 从记账重建 manifest.json（原子写），重新拼接 notebooks/M03_clustering.ipynb
                 5. 释放模块锁，打印每步摘要
```

kernel 使用执行器自己的解释器（3.c）。agent 想用 overlay 时，就用 `install_skill_deps` 返回的解释器调用执行器：`<overlay python> <skills>/_sdk/notebook/run.py run …`。执行器把 `sys.executable`、版本号，以及解释器若位于 overlay 根下时该 overlay 的 `.meta.json`（requirement 规格、key）记进 `run_start` 和 manifest（D11）。用户自己装的 `python3` kernelspec 不会被用到，所以记下来的解释器就是实际运行的解释器。

**解释器核对**（G9）。第 2 步比较 `os.path.realpath(sys.executable)` 与 manifest 里 `interpreter.path` 的 realpath。模块第一次运行时没有记录，直接记下。不一致时：
- `run`：照常运行，在输出开头打一行警告（"module 03_clustering was run with <A>; this run uses <B>"），并在 `run_start` 里记 `interpreter_changed_from`。manifest 的 `interpreter` 更新为这次的解释器。
- `replay`：拒绝，退出码 2，提示用 manifest 里的解释器重放，或者加 `--new-interpreter "<原因>"` 明确换环境；换了就把原因记进 manifest。重放是验收的依据，用错 overlay 重放等于悄悄换了环境（D11）。

#### 3.4.2 sandbox

```
agent: bash "python <skills>/_sdk/notebook/run.py run analysis/03_clustering"
  └─ BashTool.execute → _in_environment → DockerEnvironment.run_bash          (bash.py:753, environment.py:97)
       └─ docker exec --workdir <workspace> <container> bash -c WRAPPER … "<command>"
            └─ 容器内：python 是镜像里的解释器；<skills> 是只读挂载的宿主机同路径；
               workspace 读写，与宿主机同路径；HOME=/tmp（tmpfs）；网络默认 none
                 └─ 与本机相同的 1 到 5 步
```

与本机的差别，以及设计上的对应：

- 执行器状态写在 `results/<NN>/provenance/`，它在读写挂载的 workspace 里，宿主机能看到。`.omicsclaw/` 在容器里被 tmpfs 盖住，写进去的东西宿主机看不到，所以执行器不碰它。
- 模块锁是 workspace 里的文件，容器与宿主机共用同一个内核和同一个 inode，`flock` 在两边互斥（Docker Desktop 的 macOS 文件共享不保证，R3）。
- kernel 的临时目录在容器的 `/tmp`。
- `--user <宿主机 uid>` 时输出文件归宿主机用户所有。
- git 信息取不到（`.git` 没有挂载），记账里 `git` 记为 `null`，只有内容哈希（R12）。
- `load_demo` 无法下载（网络 `none`），本地也只找得到 `OMICSCLAW_DEMO_DIR` 或额外挂载的目录；找不到时报错并给出放文件的位置（R10）。
- 镜像缺 nbclient 或 ipykernel 时，执行器在启动 kernel 之前报错："the step runner needs nbclient and ipykernel in <interpreter>"。
- `install_skill_deps` 在 sandbox 里不挂载，模块的解释器就是镜像里的那个。同一个模块在本机和 sandbox 之间切换时，解释器核对会发出警告；`replay` 则需要 `--new-interpreter`。

#### 3.4.3 进程清理与环境隔离

- 本机超时：`bash` 杀整个进程组，执行器随之退出。kernel 由 jupyter_client 以 `start_new_session=True` 启动（`jupyter_client/launcher.py:151`），不在这个进程组里；但 jupyter_client 同时设了 `JPY_PARENT_PID`（`:153`），ipykernel 的 `ParentPollerUnix`（`ipykernel/kernelapp.py:219-223`）发现父进程不在后会自行退出。
- sandbox 超时：`run_bash` 只杀 `WRAPPER` 记下的那个 pid（`environment.py:31`）。执行器的命令是单条简单命令时，bash 通常直接 exec 成 python，被杀的就是执行器，kernel 再随父进程轮询退出；命令写成复合形式（例如 `cd x && python …`）时，执行器是 bash 的子进程，bash 被杀后它会被别的进程收养。为此 `run` 和 `replay` 带一个看门狗线程（O7）：每秒查一次 `os.getppid()`，一旦变了，就杀掉正在跑的 kernel（连同它的进程组），给当前步骤记一条失败的 `run_end`（`reason: "parent exited"`），然后退出，模块锁随进程退出释放。
- kernel 的 `IPYTHONDIR`、`JUPYTER_RUNTIME_DIR`、`JUPYTER_DATA_DIR` 指向本次运行的临时目录（系统临时目录下，运行结束删除）。这样有两个好处：用户 `~/.ipython/profile_default/startup/` 里的脚本不会混进 kernel，影响可复现性；kernel 也不会往 `$HOME` 写 history 和连接文件，否则 eval 的 `NoWriteOutside()` 会失败（§2.2 eval 侧）。

### 3.5 记账与 manifest

#### 3.5.1 记账（ledger）

每次运行一个文件：`results/<NN_slug>/provenance/runs/<step stem>/<run_id>.jsonl`，`run_id` 形如 `20261001T100203Z-3f2a`。每行一个 JSON 对象，都带 `"v": 1`、`"event"`、`"at"`（UTC ISO）。`contract.py` 的 `LEDGER_EVENTS` 列出事件名和必有字段：

| 事件 | 谁写 | 字段 |
|---|---|---|
| `run_start` | 执行器 | `step`、`kind`（python）、`mode`（run/replay）、`step_sha256`、`previous_sha256`、`interpreter`（`path`、`version`、`overlay`）、`interpreter_changed_from`、`stub_dir` |
| `input` | `read_input`、`load_demo`、`run_cli` | `path`（相对课题根）、`sha256`、`bytes`、`via`、`outside_contract` |
| `skill_load` | `load_skill` | `skill`、`root`、`candidate`、`git`（`commit`、`dirty`，取不到时为 `null`）、`content_sha256`、`dependencies`（`## Dependencies` 里每个包的已装版本）、`stub` |
| `skill_call` | `load_skill` 的代理 | `skill`、`function`、`args`（标量原样；其他记类型名，有 `shape` 的加上形状）、`seconds`、`stub` |
| `skill_cli` | `run_cli` | `skill`、`script`、`argv`、`exit_code`、`output_dir`、`seconds`、`stub` |
| `output` | `write_output`；`run_cli` 跑完后按输出目录补记 | `path`（相对模块的 results 目录）、`sha256`、`bytes`、`kind` |
| `stub_target_missing` | `load_skill`、`run_cli`（桩模式） | `skill`、`names`、`reason` |
| `run_end` | 执行器 | `status`（ok/failed）、`seconds`、`error`（cell、ename、evalue）、`notebook`、`log` |

`dirty` 指 skill 目录、它所在域的 `_lib` 和 `_sdk` 三处有没有未提交的改动（`git status --porcelain -- <这三处>`），三者都会影响 skill 的行为。`candidate`：`root` 不是默认 skill 树时取 `root` 的目录名（`root` 名为 `skills` 时取父目录名），否则为 `null`（D5）。

子 agent 改了父 agent 的模块（D17）：改动体现为下一次运行的 `step_sha256` 与 `previous_sha256` 不同，manifest 的步骤历史会记录这一变化。不记录是谁改的（§7.1）。

#### 3.5.2 manifest

`results/<NN_slug>/provenance/manifest.json`，每次 `run`、`replay`、`accept`、`revise` 后从记账和状态重建，原子写入。`MANIFEST_SCHEMA` 是 `contract.py` 里的字面量，形式与 `RESULT_SCHEMA` 相同（必有键及类型、取值范围）：

```json
{
  "schema": 1,
  "module": "03_clustering", "number": 3, "slug": "clustering",
  "status": "draft",
  "frozen": false,
  "interpreter": {"path": "...", "version": "3.11.9", "overlay": null},
  "steps": [
    {"file": "02_cluster.py", "kind": "python", "sha256": "...", "state": "ok",
     "last_run": "runs/02_cluster/20261001T100203Z-3f2a.jsonl",
     "history": [{"run_id": "...", "sha256": "...", "status": "ok"}],
     "inputs":  [{"path": "results/02_preprocess/intermediate/adata.h5ad", "sha256": "..."}],
     "outputs": [{"path": "intermediate/adata.h5ad", "sha256": "..."}],
     "skills":  [{"skill": "sc-clustering", "functions": ["cluster", "cluster_summary"],
                  "git": {"commit": "...", "dirty": false}, "candidate": null, "stub": false}]}
  ],
  "validate_step": "03_validate.py",
  "replay": {"at": "...", "status": "ok", "interpreter": "...", "new_interpreter_reason": null,
             "step_sha256": {"02_cluster.py": "..."}, "changed_outputs": [], "orphan_outputs": []},
  "review": {"file": "reviews/2026-10-01_review.md", "verdict": "APPROVE"},
  "accepted": {"at": "...", "skip_review": null},
  "revisions": [],
  "report": "M03_clustering_REPORT.md"
}
```

`state` 取 `ok`、`stale`、`failed`、`never_run`。`status` 按以下规则算出，不由谁手动设置：

- `draft`：默认。
- `replayed`：最近一次 `replay` 成功，它记下的每个步骤的 sha256 与当前文件一致，并且没有步骤过期。
- `reviewed`：满足 `replayed`，且 `reviews/` 里有一份晚于该次重放、第一行是 `VERDICT: APPROVE` 的审查。用户要求跳过审查时没有这一状态，`accept --skip-review` 直接从 `replayed` 进入 `accepted`。
- `accepted`：执行过 `accept`，`frozen` 为真。

D13 的"台账记为 ACCEPTED"就是 manifest 的 `status` 为 `accepted`（O5）。课题范围的汇总不落成文件：`status` 子命令每次从所有 manifest 现算，给出模块状态、步骤与调用过的 skill 函数，结果总是最新的。写作时要的 methods 汇总（版本、参数）以后由按需生成的 `run.py methods` 提供（§1.3）。

### 3.6 过期、重放与锁

**过期判定**。步骤 S 在满足以下全部条件时算最新，否则算过期，并给出第一条不满足的原因：

1. manifest 里有 S 最近一次成功运行的记录（否则：`never run`；最近一次失败则为 `last run failed`）；
2. S 当前文件的 sha256 等于该次运行的 `step_sha256`（否则：`step changed`）；
3. 该次运行记下的每个 `input`，当前的 sha256 等于记录值，文件存在（否则：`input changed: <path>` 或 `input missing: <path>`）。

`run <模块>` 每跑完一步就重新判定后面的步骤：前一步改写了后一步读过的文件，后一步就在同一次 `run` 里变成过期并被运行。

上游模块重跑后改写了 `intermediate/` 里的文件，下游步骤会因第 3 条而过期，`status` 在下游模块下列出原因。`run <模块>` 只跑本模块，不会自动级联到别的模块；要不要重跑下游由 agent 决定，契约要求它先看 `status`。skill 代码变了不会让步骤过期（D9 只看文件和输入），版本变化记在 `skill_load` 里。

每次 `status` 都重新计算输入的 sha256，不缓存（缓存推迟，§1.3）。几个 GB 的 h5ad 会让 `status` 多花几秒到几十秒（R6）。

**重放**（验收第一步，D13）。`replay <模块>`：

1. 取模块锁；模块必须恰好有一个 validate 步骤，不能有 `.R` 文件，解释器核对要通过（§3.4.1），否则以退出码 2 结束。`run` 不要求 validate 步骤，模块写到一半时可以没有；
2. 依次对每个步骤（validate 最后）新起 kernel 运行，`run_start.mode = "replay"`，不管它是否过期；
3. 任何一步失败就停下，`replay.status = "failed"`；
4. 全部成功后比较两件事并写进 manifest：`changed_outputs` 是哈希与上一次不同的输出（只记录，D12）；`orphan_outputs` 是 `figures/`、`tables/`、`intermediate/` 里存在、但这次重放没有写过的文件（只报告，不删除）。`run_cli` 的输出已经按文件补记（§3.7），不会被误报为孤儿。审查子 agent 要确认 REPORT 没有引用孤儿文件。

"新进程"的含义：每个步骤一个新 kernel，执行器本身也是 agent 这次 `bash` 调用新起的进程。重放不清空 `intermediate/`（D12），用孤儿列表来发现"REPORT 依赖的文件已经不再生成"的情况。

**锁**（D17）。同一会话里，`bash`、`write_file`、`edit_file`、`task` 由引擎串行，两个执行器不会在同一会话里并发。锁只解决跨会话的情况：两个桌面会话、channel 机器人和桌面同时开在一个 workspace，或者用户在自己的终端里跑执行器。

- 模块锁 `results/<NN_slug>/provenance/.lock`：`run`、`replay`、`accept`、`revise` 期间一直持有。用 `fcntl.flock(LOCK_EX | LOCK_NB)`；被占用时等待 `--wait` 秒（默认 0），超时以退出码 3 结束，并打印锁文件里记下的持有者（主机名、pid、子命令、开始时间）。`status` 不取锁，读到的 manifest 一定是完整的（原子写入）。
- 课题锁 `results/.project.lock`：只在 `new` 分配编号与补齐骨架时短暂持有。两个会话同时 `new` 不会拿到同一个编号。
- 不放 `.omicsclaw/` 的理由见 §3.4.2。不支持 Windows：`fcntl` 只有 POSIX，与 overlay 的锁（`overlay.py:920`）相同。

### 3.7 `load_skill` 与 `run_cli`

**解析规则**（`_skills.py`）：

1. `root` 为空时取包含本 `_sdk` 的 skill 树，即 `Path(skills._sdk.__file__).parents[1]`；给了 `root` 就用它（必须是目录）。
2. 在 `root` 下递归找名字等于 `name`、并且含 `SKILL.md` 的目录，跳过 `_` 与 `.` 开头的目录和 `__pycache__`。`SKILL.md.disabled` 不算。结果按 `root` 缓存在进程内。
   - 依据：目录名都等于 frontmatter 的 `name`（"如何核实"第 1 条）。`_sdk` 不 import 框架的 loader（B5），也就没有 YAML 解析器，按目录名匹配就够用。N-B1 加一条契约测试：每个被索引的 skill，目录名等于 `name`，这样两边的规则不会分叉。
   - 找不到：`LookupError`，附上 `difflib` 给出的最接近的三个名字。找到多个同名目录：`LookupError`，列出路径。
3. 目录里没有 `_api.py`：`LookupError("<name> has no function library yet; run its CLI from a step with run_cli(...)")`。
4. 用 `importlib.util.spec_from_file_location(f"skill_api__{snake_name}", path)` 导入，模块名由目录名推出，保证唯一，并放进 `sys.modules`。目录名带连字符不能直接 import，所以要有 `load_skill`。
5. 返回一个代理模块：只暴露 `_api.__all__` 里的名字，每个函数用 `functools.wraps` 包一层，调用前用 `inspect.signature(...).bind` 摘要参数，调用后写 `skill_call`。访问不在 `__all__` 里的名字时抛 `AttributeError`，提示列出可用的函数。`_api.py` 内部函数之间的调用不经过代理，不会重复记账。
6. 首次加载写一条 `skill_load`（§3.5.1）。

记账与桩模式只在步骤运行中生效：`OMICSCLAW_STEP_LEDGER` 已设（即执行器正在运行一个步骤）时，`load_skill` 才记账，才看桩目录。单独运行步骤、CLI 薄壳调用 `load_skill` 时两者都不生效。

**桩模式**（D15）。步骤运行中，并且设了环境变量 `OMICSCLAW_SKILL_STUBS=<目录>` 时：

- `<目录>/<name>.py` 存在：先按上面的规则解析出真实的 `_api.py`，用 `ast` 取它的顶层函数名与 `__all__`，不 import（真实模块会拉起 scanpy，eval 的 CI job 里没有）。桩模块的每个公开名字都必须在真实 `__all__` 里；有缺的就写 `stub_target_missing`（列出缺的名字），并抛 `LookupError`。真实 skill 没有 `_api.py` 也算 `stub_target_missing`。通过后加载桩模块，按同样的代理记账，`stub: true`。
- `<目录>/<name>.py` 不存在：照常加载真实模块，`skill_load.stub = false`，eval Runner 记一条软警告 `skill_ran_unstubbed`（与 0067 的语义一致）。

**`run_cli`**（Q1 推荐的过渡办法）：

1. 解析 skill 目录（规则同上），找它唯一的主脚本：目录里不以 `_` 开头的 `*.py`，0 个或多个都报错。
2. 命令行是 `[sys.executable, script, *args]`；`args` 里没有 `--output` 时追加 `--output results/<NN_slug>/intermediate/<skill>/`。有的话，路径必须在本模块的 results 目录里，否则报错。
3. `inputs` 里的文件按 `read_input` 的方式哈希并记 `input`；子进程以课题根为 cwd 运行，环境里去掉 `OMICSCLAW_STEP_FILE`、`OMICSCLAW_STEP_LEDGER`、`OMICSCLAW_SKILL_STUBS`（CLI 是一个整体，记成一条 `skill_cli`，它内部的 `load_skill` 不该再记账或换成桩）；stdout 与 stderr 合并写进 `logs/<step>__<skill>.log`，并原样打印到 cell 输出。
4. 记 `skill_cli`；退出码非零时抛 `RuntimeError`，消息带日志末尾。成功时遍历输出目录，对每个文件补记一条 `output`（路径相对模块的 results 目录），这样重放时它们不会成为孤儿，审查子 agent 也能在 manifest 里看到它们。返回输出目录。
5. 桩模式下 `<目录>/<name>.json` 存在时：脚本不存在就记 `stub_target_missing`；否则按 0067 的 `StubResult` JSON（`stdout`、`exit_code`、`files`、`binary_files`）把文件写进输出目录，打印 `stdout`，`stub: true`，然后同样按输出目录补记 `output`。这个 JSON 格式由 `omicsclaw/evals/stubs.py` 定义，`_sdk` 只读文件，契约测试钉住键名（§3.15.4）。

### 3.8 `read_input`、`write_output`、`load_demo`

- `read_input`：路径相对课题根，可以是文件或目录（目录的哈希是排好序的"相对路径加文件哈希"列表的 sha256）。默认按后缀加载：`.h5ad` 用 `anndata.read_h5ad`，`.csv` 与 `.tsv` 用 pandas，`.json` 用 `json`，`.parquet` 用 pandas，`.txt`、`.md` 读成字符串，其他后缀返回 `Path`。路径不在 `data/`、上游模块的 `results/<NN>/intermediate|tables`、本模块的 `results/<NN>/` 之内时，照常读取，记 `outside_contract: true`，并在 stderr 打警告（G6）。
- `write_output`：路径的第一段必须是 `figures`、`tables`、`intermediate`、`logs` 之一，结果落在本模块的 `results/<NN_slug>/` 下；路径越界或含 `..` 时报错（G1）。模块已冻结时报错，提示先 `revise`（G2）。写入先写同目录的临时文件再改名。默认分派：有 `write_h5ad` 方法的对象写 `.h5ad`；有 `to_csv` 的写 `.csv`/`.tsv`（`RangeIndex` 不写索引，其余写）；有 `savefig` 的按后缀写 `.png`/`.pdf`/`.svg`（dpi 150，`bbox_inches="tight"`）；dict 与 list 写 `.json`；str 写 `.md`/`.txt`。都不匹配就报错，提示用 `writer=`。
- `load_demo(name)`：注册表在 `_io.py`，0070 只登记 `pbmc3k_raw`、`pbmc3k_processed`、`pbmc68k_reduced`（bulk CSV 推迟，§1.3）。查找顺序：`$OMICSCLAW_DEMO_DIR` → `<checkout>/data/` → `<checkout>/examples/` → `$XDG_CACHE_HOME/omicsclaw/demo/`（未设时用 `~/.cache/omicsclaw/demo/`）→ 用 scanpy 下载到缓存目录。前两处与 `_lib/io.py` 的 `_demo_candidates` 一致，所以本机上 CLI 的 `--demo` 和 `load_demo` 读到的是同一个文件（这是 parity 的前提）。下载失败（sandbox 默认没有网络）时报错并列出这几个查找位置。读入的文件记作 `input`，`via: "load_demo"`。`skills/singlecell/_lib/io.py` 不改（共享 `_lib` 的改动要过全域回归）。

### 3.9 渲染

- Python 步骤：`PythonKernelRunner` 执行的就是转换器生成的 notebook，nbclient 把每个 cell 的输出（stream、display_data、错误）写回节点，执行器把节点存成 `notebooks/<step>.ipynb`。没有"先执行再渲染"的第二遍。matplotlib 在 kernel 里默认是 inline 后端，图会出现在 notebook 里；保存到文件仍要经 `write_output(fig, "figures/…")`。
- 模块 notebook `notebooks/M<NN>_<slug>.ipynb`：按步骤顺序拼接各步骤 notebook，每段前插入一个 markdown cell，写步骤名、状态、run_id、sha256 前 12 位、调用的 skill 函数。没跑过的步骤只放一个说明 cell。每次 `run` 或 `replay` 之后都重新拼接。
- 失败的步骤也保存 notebook（出错的 cell 带 traceback），拼接时标为 `failed`。
- R 步骤的渲染随 R 步骤一起推迟（§1.3）。

### 3.10 验收三步、冻结与修订

| 步骤 | 落在哪里 | 做什么 |
|---|---|---|
| 1 重放加 validate | `_executor.py` 的 `replay`；`run.py replay` | §3.6；manifest 的 `replay` 字段 |
| 2 审查 | `omicsclaw/entry/subagent.py` 的内置定义 `MODULE_REVIEWER`（§3.11.5）；契约要求 agent 用 `task` 委派，把子 agent 的回复原文写进 `results/<NN_slug>/reviews/<YYYY-MM-DD>_review.md` | 回复第一行是 `VERDICT: APPROVE` 或 `VERDICT: REVISE`；`_acceptance.py` 解析第一行 |
| 3 用户确认后冻结 | `_acceptance.py` 的 `accept`；`run.py accept` | 核对下列条件，manifest 记 `accepted` 与 `frozen: true`（D13 的台账，O5） |

`accept` 的条件（Q6 推荐不满足就拒绝，退出码 4，逐条列出缺什么）：

1. `analysis/<NN_slug>/README.md` 存在；
2. manifest 的 `status` 至少是 `replayed`：最近一次重放成功、覆盖了当前所有步骤文件、validate 步骤成功；
3. REPORT 存在，并含有 `skills._sdk.report.DISCLAIMER` 原文；
4. 给了 `--review <文件>` 时，该文件在 `reviews/` 里、第一行是 `VERDICT: APPROVE`、晚于这次重放；给了 `--skip-review "<用户原话>"` 时，把原话记进 manifest。

"用户确认"这件事执行器核实不了，只靠契约规定：只有用户明确同意后才运行 `accept`。审批卡不能当作保证，`default` 模式下用户常会对整个会话放行 `bash`，之后这条命令不再出卡（见 G3）。

`revise <模块>`：

1. 取模块锁；
2. 快照 `results/<NN_slug>/`（不含 `baseline/` 本身）：不超过 16 MiB 的文件整份复制到 `baseline/<YYYY-MM-DD>_pre_revision/`，同一天有第二次时目录名加 `-2`；更大的文件只把 sha256 写进该目录的 `LARGE_FILES.sha256`（D12）；
3. 同时复制 `analysis/<NN_slug>/` 的步骤文件，以后能知道"验收时的代码"；
4. `frozen: false`，`status` 回到 `draft`，`revisions` 追加一条；`status` 子命令把这个模块标为 `revising`。

被推翻的版本按需打包进 `results/_archive/`（D12）：0070 不提供子命令，契约让 agent 在用户同意后直接用 `tar` 打包（附录 A）。

冻结的含义：`write_output` 拒绝写入，`run`、`replay` 拒绝运行，都提示先 `revise`（G2）。目的是让修订已验收的模块之前一定先有 baseline 快照。

### 3.11 框架侧改动

#### 3.11.1 `OMICSCLAW.md`

全文草稿见附录 A。改动要点：

- Identity 的"Every answer must trace back to a SKILL.md methodology or a script output"改为可以追溯到步骤文件及其记录的输出。
- Operating Rule 2 改为：非平凡的分析放在模块里做，并使用相应的 skill。
- 新增 "Projects, modules and steps" 一节，取代原来的 "How to Use a Skill"：课题布局表、开工前先跑 `status` 再读 `STRATEGY.md` 的规定、步骤的写法与规则、执行器子命令表、"stale"的含义、完成一个模块的四步（重放、写 REPORT、审查、用户确认后 `accept`），以及修订和归档的规则。
- "Skills"一节改写：有 `## API` 的 skill 用 `load_skill`；没有的经 `run_cli` 调 CLI；`--help` 与依赖说明保留。
- 删掉"4 个外壳以 `SKILL.md.disabled` 留在磁盘上"那几句。外壳删除后磁盘上不再有这种目录，"`SKILL.md.disabled` 的目录不是 skill"这条通则也一并删掉；保留"`_` 开头的目录不是 skill"。
- Demo Data 改为步骤里用 `load_demo`，CLI 的 `--demo` 照旧。
- 路由表与计数不变（外壳原本就不计入，`consensus-interpret` 不动）。

`tests/entry/test_runtime_contract.py` 的不变式全部保持：契约里不抄免责声明，没有 "## Safety Rules"，有 "You are **OmicsClaw**"，没有开发者指令。新增一条契约测试：附录 A 里出现的每个执行器子命令都存在于 `run.py` 的解析器中（测试可以同时 import 两侧）。

#### 3.11.2 `SAFETY_RULES`

```
1. Genetic data never leaves this machine — all processing is local.
2. Every report, meaning each module's REPORT file and any summary of results you give, includes this disclaimer verbatim: "OmicsClaw is a research and educational tool for multi-omics analysis. It is not a medical device and does not provide clinical diagnoses. Consult a domain expert before making decisions based on these results."
3. When a skill does not give a parameter, threshold or cutoff, write the value you chose and the reason for it in the step. Never invent gene associations.
4. Warn before overwriting existing results, and tell the user before revising an accepted module.
```

第 1 条原文不动。第 2 条的免责声明正文不变，`skills._sdk.report.DISCLAIMER in SAFETY_RULES` 照样成立。要改的测试：`tests/entry/test_assembly.py:578` 改成新第 3 条的片段；`:579` 的 "Warn before overwriting" 在新第 4 条里仍然出现，不用改；`tests/evals/dataset/test_safety.py` 按行读取常量，不用改；`tests/entry/golden/ensemble_off_prompt.txt` 要重录（§3.11.8）。

#### 3.11.3 `omicsclaw/entry/project.py`，不加课题提示段

O5 之后不建 `PROJECT.md`，也不新增 `## Project` 提示段。理由：长期记忆按 workspace 存放（`<workspace>/.omicsclaw/memory.db`，`entry/memory.py:103-107`），它的摘要已经每轮注入（`memory_section`，在 environment 之后）；再注入一份课题文件，内容与记忆重复，还会多一个每轮都可能变化的块，让提示缓存更容易失效。课题背景放在 `docs/analysis_strategy/STRATEGY.md`，由契约要求 agent 开工前读取（附录 A）。

新增的 `omicsclaw/entry/project.py` 只有这些：函数 `step_runner_line(config) -> str | None`（§3.11.4）、`recent_modules(workspace, limit) -> tuple[ModuleSummary, ...]`（§3.11.7），以及 `/recent` 与审查子 agent 提示里要用的布局常量。布局常量和 `contract.py` 的 `LAYOUT` 由契约测试钉住相等。`default_sections` 的 section 序列不变，`tests/entry/test_assembly.py:430`、`:444` 不用改。

#### 3.11.4 `## Environment` 加一行

`_environment_source` 增加 `- Step runner: python <skills_root>/_sdk/notebook/run.py`，只在该文件存在时出现；`sandbox_code_in_image` 时写成 `python -m skills._sdk.notebook`。契约里所有"执行器"都指向这一行，路径因部署而异，写在契约文件里就不对了。这一段只加这一行，不加课题指针或模块状态（O5）：environment 段每天才变一次，加上会随工作变化的内容，缓存就更容易失效。

#### 3.11.5 审查子 agent

`omicsclaw/entry/subagent.py` 新增：

```python
MODULE_REVIEWER = SubAgentDefinition(
    name="module-reviewer",
    description=(
        "Reviews one analysis module after it has been replayed and before the user "
        "accepts it: reads its step files, outputs, manifest and report, and returns "
        "VERDICT: APPROVE or VERDICT: REVISE with findings. Read-only."
    ),
    system_prompt=REVIEWER_PROMPT,          # 全文见附录 B.4
    tools=("read_file", "use_skill"),
    source="builtin",
)
```

`build_subagent_registry` 改为以 `[GENERAL_PURPOSE, MODULE_REVIEWER]` 开头。`subagents=False` 时两者都不存在。`.omicsclaw/agents/module-reviewer.md` 可以按现有规则原位替换它。工具只给 `read_file` 和 `use_skill`（D13 的"只读"，理由与代价见 G5）。审查要读的文件都列在 manifest 里，所以不能列目录不影响审查；看不了图片，因为 OmicsClaw 目前不读图片，审查只确认图的文件存在、被 REPORT 正确引用。

`task` 工具的描述和 `subagent_type` 的 enum 因此多一项，`tests/entry/golden/ensemble_off_tools.json` 要重录（§3.11.8）。要改的测试：`tests/entry/test_subagent_wiring.py:234`、`:281` 的 `names()`，`:266` 的 `subagent_type` enum；`docs/core-features/sub-agent.md` §2.3 补内置审查子 agent。

#### 3.11.6 `install_skill_deps` 接受一组 skill

- schema：`skill`（字符串）改为 `skills`（字符串数组，`minItems: 1`），`packages` 不变；每个包必须出现在至少一个所列 skill 的 `## Dependencies` 里，报错信息按 skill 列出各自声明的包。单个 skill 就是一个元素的数组，不保留旧的 `skill` 参数：给模型看的 schema 只有一种写法，而这个工具只在 `skill_env=install` 时挂载，没有外部调用方。
- 探针计划合并所列 skill 的模块；`OverlayRequest.skill: str` 改为 `skills: tuple[str, ...]`，`.meta.json` 写 `"skills": [...]`。overlay 的 key 本来就由 requirement 规格决定，同一组包的模块会复用同一个 overlay。
- 审批卡写明为哪些 skill 安装。结果末尾的用法从"用这个解释器跑 skill 脚本"改为"用这个解释器运行模块的步骤：`PYTHONNOUSERSITE=1 <python> <runner> run analysis/<NN_slug>`"，CLI 用法作为第二行保留。
- 工具描述（`tool.py:47-55`）相应改写。
- 要改的测试：`tests/skillenv/test_install_tool.py`、`test_install_permissions.py`、`test_install_concurrency.py`、`test_install_cancel.py`、`test_install_wiring.py`、`installing.py`、`test_overlay_real.py`（`:72` 直接构造 `OverlayRequest(skill=...)`）、`test_ensemble_environment.py`，以及 `tests/permission/test_foundation_tools_keep_their_prompts.py` 里的参数形状。

#### 3.11.7 channel `/recent`

`/recent` 列出最近修改的 3 个模块：`results/` 下名字符合模块规则的目录，按 `provenance/manifest.json` 的 mtime 排序（没有 manifest 时用目录 mtime），每项显示模块名、时间、manifest 的 `status`（大写）、REPORT 的第一个一级标题（没有 REPORT 时写 "No report yet"）。没有模块时回答 "No recent analyses found."。旧的 `output/` 运行不再列出（O1）。`/outputs` 不变，留到删 CLI 的计划。读取逻辑在 `entry/project.py` 的 `recent_modules`，channel 只负责格式化。manifest 只读 `status` 一个键，键名由契约测试钉住。

测试：`tests/entry/test_channel_commands.py:215` 那条（空 workspace）保留；`:251` 的 `test_recent_reads_the_headline_out_of_each_report` 改成读模块的 REPORT 标题与状态；再加一条"只有旧 `output/` 运行时回答没有记录"。

#### 3.11.8 重录 `tests/entry/golden/`（O2）

`tests/entry/test_ensemble_golden.py` 把 off 部署的提示词和工具表逐字节钉死。0070 有两处有意的改动会改变它：
- `SAFETY_RULES` 第 2 至 4 条（§3.11.2）改变 `ensemble_off_prompt.txt` 的 safety 段；
- 内置 `module-reviewer`（§3.11.5）改变 `ensemble_off_tools.json` 里 `task` 的描述与 enum。

不会改变 golden 的：Environment 的执行器一行（golden 部署的 skill 树是 `tests/ensemble/fake_skills`，没有 `_sdk/notebook/run.py`）。`ensemble_tools_all.json` 是 ensemble 工具块本身，0070 不改这些工具，预计不变；重录后若有差异，先查明原因再决定是否一起提交。

做法：在 N-D 的上述改动都完成之后，用 `OMICSCLAW_WRITE_GOLDEN=1` 重录，然后不带这个变量再跑整个测试文件，确认：off 部署与新 golden 逐字节相同；on 部署的提示词与 off 相同；块外的工具与 off 的 golden 相同，差别只在 `memory_write` 与 `task` 之间的 ensemble 工具块（`ENSEMBLE_TOOLS[mode]`，`free` 与 `all` 模式下以 `run_skill` 打头）。这就是文件头"on 与 off 只差 ensemble 工具"这一条。`git diff tests/entry/golden/` 里只能看到 safety 段和 `task` 工具的变化。

### 3.12 防线账

这里列的都是"挡住某种错误"的设计，每道防线回答三个问题：防什么场景；有没有同等或更宽的旁路（尤其是 `bash`）；在单人本机部署下值不值得。执行器本身不是安全边界：它运行的是 agent 写的任意代码，信任级别与 `bash` 相同，真正的隔离靠 sandbox。下面没有一条是为了对抗恶意的 agent。

| 编号 | 防线 | 防什么 | 旁路 | 值不值 |
|---|---|---|---|---|
| G1 | `write_output` 只写本模块的 4 个输出目录 | 步骤误写到别的模块，或写进执行器管理的目录（provenance、notebooks、reviews、baseline），弄乱记账 | 步骤代码直接写文件、`bash` 都能绕过 | 值。它规定 `write_output` 能写到哪里，代价是几行路径检查，出错信息还能告诉 agent 正确的写法 |
| G2 | 冻结模块拒绝 `write_output`、`run`、`replay` | 已验收的模块在没做 baseline 快照的情况下被改写 | 改步骤文件后单独 `python` 运行，或手改 manifest | 值。正常路径因此一定先经过 `revise`，绕过它比遵守它更费事 |
| G3 | `accept` 的 4 项条件 | 没重放、没 REPORT、审查没通过的模块被记成 ACCEPTED | 手改 manifest；"用户确认"执行器无法核实 | 值，属于工作流检查。用户确认只靠契约：`default` 模式下用户常对整个会话放行 `bash`（`agent-skills.md` §9.4），审批卡不可靠，auto-approve 下更没有卡。本计划不加 ask 规则 |
| G4 | 模块锁与课题锁 | 两个会话同时跑同一个模块，记账交错、manifest 被覆盖；两个会话 `new` 出同一个编号 | 不经执行器直接运行步骤；删锁文件 | 值。`flock` 几乎没有成本，防的是真实存在的多会话场景 |
| G5 | 审查子 agent 只有 `read_file`、`use_skill` | 审查者为了"修好"问题去改它正在审查的模块，审查结论因此失效 | 子 agent 内没有旁路（没有 `bash`、`write_file`）；父 agent 照样能改，但那是另一个角色 | 值。审查本来就不需要写，零成本。代价是不能列目录、不能 grep，用 manifest 的文件清单代替 |
| G6 | `read_input` 读契约外的路径时只警告并记账，不拒绝 | 下游读了上游的 figures 或别处的文件，血缘断掉 | 任何直接读文件的代码 | 只做到警告。拒绝挡不住直接读文件，反而会逼 agent 绕开 `read_input`，记账更不完整 |
| G7 | `data/` 只读 | 覆盖或删除用户的原始数据 | `bash` 和步骤代码都能写 | 按 D17 只写进契约，不加闸门。闸门只拦得住 `write_file`，拦不住 `bash` 和步骤代码，算不过账。`write_output` 本来就写不到 `data/`（G1 的副产品） |
| G8 | 步骤代码 cell 里禁止 `%`、`!` 开头的行 | 步骤依赖 IPython 魔法，脱离 kernel 就跑不了，违背 D9 | `get_ipython().system(...)`、`subprocess` | 值。它守的是"能单独运行"这个属性，检查只要一个正则 |
| G9 | 解释器核对：`run` 警告，`replay` 要求 `--new-interpreter` | 用错 overlay 或在 sandbox 与本机之间切换后重放，验收依据的环境被悄悄换掉（D11） | 加上 `--new-interpreter`；手改 manifest | 值。比较两个路径，代价很小；`run` 只警告，不妨碍探索 |

另外两项不加防线，理由如下：

- workspace 就是 OmicsClaw checkout 时，`new` 只警告（Q4 推荐），不拒绝。拒绝会挡住 owner 自己最常用的开发方式；警告配合 `.gitignore` 已经能避免课题文件混进提交。
- `install_skill_deps` 接受一组 skill 后，审批卡照常出现，内容多了 skill 列表，没有新增闸门。

第 1 版的 G7（桩模式横幅、`accept` 拒绝含桩运行的模块）按 O1 推迟（§1.3）；第 2 版的 G9（`PROJECT.md` 容错读取与限长）随 O5 删除，原 G10 改称 G9。

### 3.13 单细胞试点

#### 3.13.1 范围

`sc-qc` → `sc-preprocessing` → `sc-clustering` → `sc-cell-annotation` → `sc-de`，5 个 skill，目录都在 `skills/singlecell/scrna/`。`sc-filter` 不在内（Q2）。

#### 3.13.2 skill 包结构

```
skills/singlecell/scrna/sc-clustering/
  SKILL.md              手写的方法学 + 生成的 ## API 段
  _api.py               私有函数库：load_skill 导入的就是它
  sc_cluster.py         CLI 薄壳：argparse、读写文件、画廊图、report.md、result.json
  examples/example_step.py   可执行示例步骤，数据来自 load_demo
  references/           不变
  tests/                原有测试
```

私有模块的文件名定为 `_api.py`（第 1 版 Q2）：以 `_` 开头的文件已被 `test_bootstrap`、`help_probe` 视为非主脚本，不用改任何守卫；`consensus-interpret` 已有 `_*.py` 辅助模块的先例。下划线表示"这个 skill 私有，不是入口脚本"，`load_skill` 返回的才是对外的接口。

`_api.py` 的规则（写进 `templates/skill/README.md`）：

- 只做计算，不读写文件、不配置 logging、不改全局状态。I/O 由步骤里的 `read_input`/`write_output` 或 CLI 薄壳负责。R 方法内部要用临时文件的，在函数里用 `tempfile` 处理，调用者看不到。
- 第一个参数是 `adata`；其余参数只能按关键字传，默认值等于 CLI 的默认值。修改 AnnData 的函数原地修改并返回同一个对象，docstring 写明；表格返回 `DataFrame`；图返回 matplotlib `Figure`。随机过程有显式的 `random_state` 参数。
- `__all__` 列出全部公开函数。每个公开函数都有 docstring：第一行说做什么；每个参数用 `:param name:` 写含义、默认值的来源以及什么时候需要改；另有 `:returns:`、`:raises:`。
- 可以 import 本域 `_lib` 和 `_sdk`，不 import `omicsclaw`（B3），不 import 别的 skill。CLI 薄壳用 `load_skill(SKILL_NAME)` 取得自己的 `_api.py`：CLI 进程里没有绑定记账（`run_cli` 启动子进程时去掉了那三个环境变量，见 §3.7），所以既不记账也不进桩模式，公开面仍是 5 个名字。

试点函数清单（初稿，实施时以 parity 为准微调）：

| skill | `_api.py` 公开函数 |
|---|---|
| sc-qc | `calculate_qc(adata, *, species, …)`、`qc_summary(adata)`、`qc_figures(adata)` |
| sc-preprocessing | `preprocess(adata, *, method, n_top_hvg, n_pcs, …)`（scanpy、pearson_residuals、seurat、sctransform）、`hvg_table(adata)`、`pca_variance_table(adata)` |
| sc-clustering | `cluster(adata, *, use_rep, n_neighbors, n_pcs, embedding, method, resolution, random_state, …)`、`auto_resolution(adata, …)`、`cluster_summary(adata, *, key)`、`embedding_figure(adata, *, color)` |
| sc-cell-annotation | `annotate(adata, *, method, cluster_key, markers, model, reference, manual_map, …)` 统一入口，以及 `annotate_markers`、`annotate_celltypist` 等各方法函数、`annotation_table(adata, *, key)` |
| sc-de | `rank_genes(adata, *, groupby, method, n_top_genes, …)`、`pseudobulk_de(adata, *, method, sample_key, celltype_key, group1, group2, …)`、`volcano_figure(table, …)` |

Q2 推荐 `_api.py` 覆盖 CLI 现有的全部方法，包括调用 R 的方法（它们已经是脚本里的函数，搬过去是机械工作）。R 方法不录 parity 基线（§3.13.6），由 skill 自带的 R 测试覆盖，这些测试在没有 `Rscript` 时跳过。

#### 3.13.3 `## API` 段的生成与一致性

- 生成器 `_apidoc.py`：只用 `ast`，不 import 模块（job1 没有 scanpy）。按 `__all__` 的顺序，每个函数输出 `### \`name(签名)\``（签名用 `ast.unparse` 原样还原，包括类型注解与默认值），下面是 dedent 后的 docstring 原文，不解析字段。
- 段落以 `<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->` 和 `<!-- api:end -->` 包住。
- 一致性测试 `tests/sdk/notebook/test_skill_api_sections.py`：对每个有 `_api.py` 的 skill（以及模板），重新生成并与 `SKILL.md` 里的段落逐字比较；同时检查 `__all__` 的每个名字都是顶层函数并且有 docstring，以及 `SKILL.md` 有且只有一个 API 段。只用 `ast`，所以在 rapids 环境和 CI job1 里都能跑。
- `## Dependencies` 段的解析不受影响：它在下一个标题处结束（`tests/skillenv/test_dependencies_section.py`）。

#### 3.13.4 SKILL.md 正文模板

模板见附录 B.3。原则（按"给 agent 写文档"的写法）：先放 agent 每次都需要的"何时用"和"在步骤里怎么用"，再放生成的 API，然后是手写的方法选择与参数来源（SAFETY 3 要求写明依据，所以每个默认值的来源要写在这里），最后才是坑、输入输出和过渡期 CLI。description（路由用的那一行）不改。

#### 3.13.5 可执行示例

`examples/example_step.py` 是一个完整的步骤文件：`load_demo` → 调 1 到 3 个本 skill 的函数 → `write_output` 若干输出 → 用 `assert` 检查结果。每个示例只依赖自己的 demo 数据，不依赖上游示例的输出：`sc-clustering`、`sc-cell-annotation`、`sc-de` 用 `pbmc3k_processed`（已有聚类标签），`sc-qc`、`sc-preprocessing` 用 `pbmc3k_raw`。

测试 `tests/sdk/notebook/test_skill_examples.py`，标记新 marker `skill_example`，默认 `addopts` 排除它：在 `tmp_path` 建课题，把示例复制成 `analysis/01_demo/01_<skill>.py`，用执行器运行（执行器的解释器取 pytest 所在的 `sys.executable`），断言成功、notebook 存在、记账里有该 skill 的调用。本机用 `OmicsClaw` 环境的 pytest 跑（O3：rapids 环境缺 leidenalg 和 igraph，`sc.tl.leiden` 会抛 `ImportError`）。CI 新增 job3 专门跑它（是否设为门禁见 Q3）。

#### 3.13.6 CLI 薄壳与 parity

parity 测试与基线都用 `OmicsClaw` 环境（O3）：`/opt/conda/envs/OmicsClaw/bin/python -m pytest`，CLI 子进程用同一个 `sys.executable`。每个 skill 的顺序是固定的：

1. 改动之前，用旧 CLI 录基线：`/opt/conda/envs/OmicsClaw/bin/python -m tests.parity.snapshot record <skill> --case <case>`。每个 skill 录两组参数（O1）：demo 的默认参数，加 1 个 Python 方法的变体（例如 `sc-clustering` 的 `--cluster-method louvain`，`sc-de` 的 `--method t-test`）。R 方法不录。
2. 基线存实际数值，能逐值比较：
   - 每张输出表原样存成 CSV；
   - `processed.h5ad` 的每个分类 `obs` 列存成 `obs_name,label` 的 CSV，数值 `obs` 列存成 CSV；
   - obsm 存键名与形状；
   - `result.json` 存 `summary`（去掉时间与路径）；
   - 图存文件名集合。
   基线放在 `tests/parity/golden/<skill>/<case>/`，这个目录加进 `.gitignore`，不提交：比较只在录基线的那台机器、那个环境里有意义，全量 DE 表又可能有几 MB。每个 case 的比较结果写进实施记录。
3. 抽出 `_api.py`，把 CLI 改成薄壳。
4. `tests/parity/test_sc_pilot_parity.py`（标 `slow`，基线不存在时跳过）对每组参数做两件事：用新 CLI 运行，与基线比较；再在同一个解释器里直接调 `_api.py` 的函数，与基线中对应的表和标签比较。前一项保证"新旧结果一致"，后一项保证步骤里调用 API 和调用 CLI 得到同样的结果。
5. 一致的标准（第 1 版 Q6，计划内决定）：分类标签按 `obs_name` 逐值相等；整数列逐值相等；浮点列在 rtol 1e-6 内（`numpy.allclose`）；图只比文件名。

parity 不进 CI：Leiden 等结果依赖 igraph、leidenalg 的版本，CI 的 pip 环境和开发机的 conda 环境不一样，基线只在录它的那个环境里有意义（R4）。

模板 `templates/skill/` 同步：加 `_api.py`（一个演示函数）、`examples/example_step.py`、`SKILL.md` 正文按附录 B.3、`README.md` 讲清 `_api.py` 的规则和 API 段的生成命令。模板的 API 段同样受一致性测试约束。

### 3.14 删除 consensus 外壳与失效代码分诊

**删除**：`skills/singlecell/scrna/sc-consensus-clustering/`、`sc-consensus-integration/`、`sc-consensus-pseudotime/`、`skills/spatial/consensus-domains/`，整个目录删掉（`SKILL.md.disabled`、脚本、`references/`、`tests/`）。两个 `tests/test_cli_smoke.py` 一起删，0068 H-H3 记下的 4 条失败随之消失。4 个外壳早已移出 index，删掉它们不改变任何计数。

**`consensus-interpret`**：0070 不动（O4）。按 0068 PQ4（`docs/plans/0068-eval-hardening.md:682`），它默认走结构化路径，留在 index 里；按 D16，它随 ensemble 处理。

**其他引用**：

- `OMICSCLAW.md` 删掉提到 4 个外壳的那几句（§3.11.1）；`llms.txt` 删掉 4 行；`tests/sdk/test_boundary.py` 的 `B3_KNOWN` 改为空集。
- `sc-integrate-cluster` 的 description 仍说自己是 `sc-consensus-integration` 的成员，改写推迟（§1.3）。
- `omicsclaw/runtime/consensus/sources.py` 里登记了这几个目录。`runtime/` 本来就不可导入，按 0068 PQ1 的裁定，代码留到 ensemble 计划，这里不动。
- `examples/consensus_benchmark/`（调用 `consensus-domains` 的 CLI）和 `tests/runtime/consensus/test_dlpfc_benchmark.py`（需显式开启的那一条），同样留给 ensemble 计划。
- `tests/ensemble/tuning/golden/a3_dev_prompt.txt` 是 ensemble 调参开发运行时的提示快照，已知失败（0068 §8.5 第 1 条），不改。
- `AGENTS.md` 已过时、待重写，不改。`CHANGELOG.md` 的旧条目是历史记录，不改。

**失效代码分诊**（处置按 Q5 的推荐写）：

| 对象 | 现状 | 处置 |
|---|---|---|
| `omicsclaw/common/notebook_export.py` | 生产代码没有调用方；它生成的 notebook 里写着 `from omicsclaw.skill.registry import registry`（`:301-303`），这个模块已经删除，所以生成出来就是坏的；只被 `tests/test_output_ux.py::test_analysis_notebook_rejects_claim_aliases` 引用 | 0070 删除，连同那条测试。新的渲染器取代了它，两份 notebook 导出并存只会让人误用 |
| `omicsclaw/common/report.py` 的 `validate_result_envelope` 等信封校验 | 生产代码没有调用方；`tests/sdk/test_result_contract.py` 用它钉住与 `_sdk` 一致 | 留到删 CLI 的计划：过渡期 CLI 薄壳仍写 `result.json`，ensemble 仍读它 |
| `omicsclaw/runtime/workflow/fan_out.py`、`runtime/consensus/*` | import 已删除的 `omicsclaw.skill`（`fan_out.py:25`、`consensus/run.py:248` 等），不可导入；外壳删除后没有任何调用方 | 按 0068 PQ1 留到 ensemble 计划，0070 不动 |

### 3.15 eval

#### 3.15.1 Runner 与 `Case` 的改动（`omicsclaw/evals/`）

- `Case.skill_modules: Mapping[str, Path] = {}`：skill 名 → 桩模块文件。现有的 `Case.skill_stubs`（skill 名 → `StubResult`）同时服务 `bash` 打桩和 `run_cli` 打桩。
- 用例声明了任一种桩时，Runner 在快照之前把它们落到 `tmp_path/stubs/`（`<skill>.py` 原样复制，`<skill>.json` 用 `StubResult.dump` 写出），然后把 `OMICSCLAW_SKILL_STUBS=<该目录>` 并入 `case.env`。`hermetic_env` 改的是 `os.environ`，`bash` 子进程、执行器、kernel 都会继承。
- Runner 给每个用例的环境加 `PYTHONDONTWRITEBYTECODE=1`。kernel 用 `spec_from_file_location` 加载桩模块时，会在 `tmp_path/stubs/__pycache__` 写字节码（审核探针实测），这是 workspace 之外的改动，`NoWriteOutside()` 会失败。eval 本来就不需要字节码缓存，所以对所有用例统一关掉。
- 运行结束后，Runner 读 `ws/results/*/provenance/runs/**/*.jsonl`：
  - 每条 `skill_call` 和 `skill_cli` 转成一条 `SkillRun`。`SkillRun` 增加 `function: str | None = None` 和 `source: str = "bash"`（取 `"bash"` 或 `"ledger"`），`domain` 从 skill index 查。
  - 每条 `stub_target_missing` 记一个 hard failure，名字与 0067 相同。
  - 用例设了桩目录、却出现 `skill_load.stub == false` 时，记软警告 `skill_ran_unstubbed`。
  - 读记账只是读文件，不 import `skills.*`（B4）。事件名和字段名由契约测试钉住。
- `SkillInvoked(skill, domain=None, function=None)`：在原有的 `bash` 运行记录之外，也认记账来的记录；给了 `function` 时，要求有该函数的调用。断言仍是 12 种，只是放宽了一种的语义（0067 D3 不变）。
- `_harness.check` 增加 `timeout_s` 参数，skill 用例用 90 s：每次执行器调用要起一个 kernel，CI 上每次 2 到 5 秒。

#### 3.15.2 桩

- `tests/evals/fixtures/skill_stubs/sc-qc.py`、`sc-clustering.py`：每个文件几个函数，名字与真实 `_api.py` 相同，参数是 dict，返回 dict，只用标准库（job2 没有 anndata 和 pandas）。例如：

  ```python
  """Stand-in for sc-clustering's function library in scripted evals."""

  def cluster(adata, *, resolution=1.0, **_):
      """Return the input with a fixed two-cluster labelling."""
      cells = adata["cells"]
      return {**adata, "leiden": [str(i % 2) for i in range(len(cells))]}

  def cluster_summary(adata, *, key="leiden"):
      """Count cells per cluster."""
      counts = {}
      for label in adata[key]:
          counts[label] = counts.get(label, 0) + 1
      return counts
  ```

- 用例的输入是预置的 `data/cells.json`，步骤里用 `read_input` 读成 dict，输出写 `.json`。脚本化 eval 只测 harness 的机制，桩的返回值不需要有科学意义。
- `bulkrna-de` 的 `run_cli` 用例沿用已有的 `tests/evals/fixtures/skill_runs/bulkrna-de.json`。

#### 3.15.3 8 条 skill 用例（按 D15 定）

`tests/evals/dataset/test_skill_routing.py` 整个重写，类别仍是 `skill_routing`，`BASELINE = 29` 不变。脚本里的命令一律是 `f"{sys.executable} {RUNNER} …"`，`RUNNER = REPO/"skills/_sdk/notebook/run.py"`，保证 kernel 的解释器装了 nbclient 和 ipykernel。每条用例默认带 `NoWriteOutside()`，表里省略。

| # | id | 意图 | 主要断言 |
|---|---|---|---|
| 1 | `skill_routing/step_calls_a_skill_function` | `use_skill(sc-clustering)` → `bash new clustering` → `write_file` 写 `analysis/01_clustering/01_cluster.py`（`load_skill`、`read_input("data/cells.json")`、`cluster`、`write_output(…, "tables/clusters.json")`）→ `bash run analysis/01_clustering` | `SkillInvoked("sc-clustering", domain="singlecell", function="cluster")`；`ToolResultContains(bash, "01_cluster.py  ok")`；`fs_changes` 含 `created results/01_clustering/notebooks/01_cluster.ipynb` 和 `…/provenance/manifest.json`；`NoError` |
| 2 | `skill_routing/first_module_builds_the_skeleton` | 预置 `notes.txt`、`data/cells.json`、`scripts/mine.sh`；`bash new clustering` | `fs_changes` 里预置文件没有 `modified` 和 `deleted`；创建了 `analysis/01_clustering/README.md` 和 `docs/analysis_strategy/STRATEGY.md`；workspace 根下没有出现 `PROJECT.md`、`METHODS_LEDGER.md`（`CountIs`） |
| 3 | `skill_routing/unchanged_step_is_skipped` | 同一个模块连续 `run` 两次 | 第二次 `bash` 的输出含 `up to date`；`runs/01_cluster/` 下恰好一个记账文件（`CountIs`） |
| 4 | `skill_routing/edited_step_reruns` | `run` → `edit_file` 把 resolution 从 1.0 改成 0.5 → `run` | 第二次输出含 `step changed`；两个记账文件；记账里第二次 `cluster` 的参数 `resolution=0.5` |
| 5 | `skill_routing/upstream_change_marks_downstream_stale` | 模块 01（sc-qc 桩）写 `intermediate/cells.json`，模块 02（sc-clustering 桩）读它；改 01 的步骤并重跑 01；`bash status` | `status` 的输出含 `02_clustering` 下的 `input changed: results/01_qc/intermediate/cells.json` |
| 6 | `skill_routing/replay_runs_every_step_and_validate` | 模块有 `01_cluster.py` 和 `02_validate.py`；`bash replay analysis/01_clustering` | manifest 的 `replay.status == "ok"`、`status == "replayed"`；`M01_clustering.ipynb` 含两个步骤的段落（`CountIs`） |
| 7 | `skill_routing/review_then_accept` | 重放后 `write_file` 写 REPORT（含免责声明）→ `task(module-reviewer, "Review module 01_clustering")`，子 agent 的脚本是两次 `read_file`（manifest、REPORT），然后回复 `VERDICT: APPROVE …` → 父 agent 把回复写进 `reviews/` → 后续消息 "Yes, accept it." → `bash accept … --review …` | `ToolArgs(task, {"subagent_type": "module-reviewer"})`；manifest 的 `frozen` 为真、`status == "accepted"`；`accept` 之后脚本再跑一次 `bash status`，输出里 `01_clustering` 一行是 `ACCEPTED` |
| 8 | `skill_routing/cli_skill_from_a_step` | 步骤里 `run_cli("bulkrna-de", "--input", "data/counts.csv", inputs=["data/counts.csv"])` → `run` | `SkillInvoked("bulkrna-de", domain="bulkrna")`（记账来源）；`results/01_de/intermediate/bulkrna-de/result.json` 已创建，且在 manifest 的该步骤 `outputs` 里；`ToolResultContains(bash, <fixture stdout 的一行>)` |

旧的 7 条按域的 CLI 路由用例从脚本化门禁中去掉。`bash` 打桩层（`stubbed_skill_runs`）保留：live eval 要用，`tests/evals/test_stubs.py` 继续测它。原本由这些用例覆盖的"每个域都能被 `use_skill` 解析"，现在由 live eval 和 `tests/skills/` 的语料测试覆盖。

`stub_target_missing` 的正反两面放在单元测试里，不作为数据集用例：`tests/evals/test_runner.py` 加"桩里多了真实模块没有的函数 → hard failure"一条；`tests/sdk/notebook/test_skills.py` 测 `_sdk` 一侧。

#### 3.15.4 其他 eval 改动

- `tests/evals/test_fixtures.py`：不再从 `test_skill_routing` import `ROUTES`。"每份 fixture 都有对应的路由用例"改为"每份 fixture 都被 live eval 或某条数据集用例使用"；检查行的表移进这个测试文件本身。
- 契约测试 `tests/sdk/notebook/test_contract.py`（测试可以同时 import 两侧）：`omicsclaw.evals` 用到的事件名、字段名、环境变量名，与 `contract.py` 的 `LEDGER_EVENTS`、`ENVIRONMENT` 一致；`_sdk` 读 `StubResult` JSON 用到的键，与 `omicsclaw/evals/stubs.py` 的 `dump` 一致；`omicsclaw/entry/project.py` 的布局常量和 manifest 键，与 `LAYOUT`、`MANIFEST_SCHEMA` 一致。
- live eval（`omicsclaw/evals/live.py`）的判分：`executed_skill` 在 `bash` 的 skill 运行之外，也认记账里的第一条 `skill_load` 或 `skill_cli`。否则契约改了以后，试点 skill 的 `executed_skill` 会一直是空的，主指标悄悄退回 `first_use_skill`。live eval 不设桩目录（真实模块在 owner 机器上能导入，输入文件不存在，会很快失败）。
- CI（`.github/workflows/eval.yml`）的改动分在三个阶段：N-B1 给 job1 的 pip 列表加 `nbclient ipykernel`（`tests/sdk/notebook/` 要起 kernel，job1 跑 `tests/sdk`）；N-C0 注册 `skill_example` marker 时，同时在 job1 显式传的 `-m` 里加 `and not skill_example`（命令行的 `-m` 会覆盖 `addopts`），并新增 job3；N-E6 把 job2 改为 `pip install -e . pytest nbclient ipykernel`。
- `docs/core-features/eval.md` 改写 skill 用例一节。

### 3.16 受影响的守卫测试与既有测试

| 测试 | 原因 | 处理 | 阶段 |
|---|---|---|---|
| `tests/sdk/test_bootstrap.py` | 主脚本计数；新的执行器入口需要引导块 | 90 不变（删外壳不影响，`consensus-interpret` 不动）。`_api.py` 以 `_` 开头，不计入；`examples/` 是子目录，不计入（`glob("*.py")` 不递归）。把 `skills/_sdk/notebook/run.py` 加进"必须有统一引导块"的检查对象 | N-B1 |
| `tests/sdk/test_help_probe.py` | 试点 CLI 改成薄壳 | 90 不变；薄壳的 `--help` 仍要成功，靠这条测试守住 | N-C |
| `tests/sdk/test_boundary.py` | `B3_KNOWN` 正是 4 个外壳 | `B3_KNOWN` 改为空集，注释删掉。B5 自动覆盖 `_sdk/notebook/`（只用标准库，第三方库在函数体内导入）。B9：`skill_api__…`、`OMICSCLAW_…` 这类字符串不匹配 `omicsclaw(\.\w+)+`，不受影响 | N-A |
| `tests/sdk/test_public_surface.py` | `_sdk_modules()` 只看顶层 `*.py` | 改为同时收录子包的门面（`skills._sdk.notebook`）和 `contract.py`；`PUBLIC_SURFACE` 加 `"skills._sdk.notebook": {read_input, write_output, load_skill, load_demo, run_cli}`、`"skills._sdk.notebook.contract": {LAYOUT, MANIFEST_SCHEMA, LEDGER_EVENTS, ENVIRONMENT}`；4 个字面量加进 `CONTRACTS`；`_` 开头的内部模块和 `run.py`、`__main__.py` 不冻结。"每个冻结名都有使用者"由示例步骤、CLI 薄壳和模板满足 | N-B1 |
| `tests/skillenv/test_dependencies_section.py`、`tests/skills/test_real_corpus.py`、`tests/skills/test_domain_index_is_current.py` | 计数、语料、INDEX | 不受影响：skill 文件数仍是 90，frontmatter 与 description 都不改，正文变长不影响上下限 | 无 |
| `tests/ensemble/test_tuning_matches_argparse.py` | 只看有 `tuning.yaml` 的 skill | 0070 不受影响 | 无 |
| `tests/entry/test_assembly.py` | 安全规则字面量 | `:578` 改成新第 3 条的片段；`:579` 与 `:430`、`:444` 的 section 序列都不用改（不加 project 段，O5） | N-D |
| `tests/entry/test_ensemble_golden.py` | off 部署的提示词与工具表逐字节钉死 | 按 §3.11.8 重录 `ensemble_off_prompt.txt`、`ensemble_off_tools.json`（必要时连带 `ensemble_tools_all.json`），再跑整个文件确认 on/off 的关系不变 | N-D |
| `tests/entry/test_runtime_contract.py` | 契约不变式 | 不变式保持；新增"契约里的子命令都存在" | N-D |
| `tests/entry/test_subagent_wiring.py` | 内置子 agent 列表 | `("general-purpose", "module-reviewer")`；enum 加一项 | N-D |
| `tests/entry/test_channel_commands.py` | `/recent` | 见 §3.11.7 | N-D |
| `tests/skillenv/test_install_*.py`、`installing.py`、`test_overlay_real.py`、`test_ensemble_environment.py`、`tests/permission/test_foundation_tools_keep_their_prompts.py` | 参数形状与 `OverlayRequest` | `skill` → `skills` | N-D |
| `tests/test_output_ux.py` | 引用 `notebook_export` | 删 `test_analysis_notebook_rejects_claim_aliases`（Q5 推荐） | N-A |
| `tests/test_pyproject_thin_pip_layer.py` | conda 管理的包 | `CONDA_OWNED` 加 `nbclient`，`environment.yml` 显式声明 | N-B1 |
| `tests/evals/test_fixtures.py`、`test_dataset_floor.py` | `ROUTES`、计数 | 见 §3.15.4；`BASELINE` 不变 | N-E |
| `tests/launch/test_grammar.py` | 进程入口 | 只扫描 `omicsclaw/`，`skills/` 下的新入口不受影响；`[project.scripts]` 不加 | 无 |

---

## 4. 分期与任务

依赖：N-A → N-B1 → N-B2 → N-C。N-D 依赖 N-B2，可以和 N-C 并行。N-E 依赖 N-D（审查子 agent）和 N-C 里的 `sc-qc`、`sc-clustering`（桩要对照真实的 `_api.py`）。N-D 把契约切到新路径之后，建议紧接着合入 N-E，让 PR 门禁尽快覆盖新路径。

每个阶段只跑新增与相关的测试，不跑全量。两个解释器（O3）：
- `PYTEST` = `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`：除下一条以外的所有测试。
- `OCPYTEST` = `/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:randomly`：只用于试点 skill 的示例测试和 parity 测试（rapids 环境缺 leidenalg、igraph）。不要用它跑 `tests/launch/test_surfaces.py`：这个环境装了 fastapi，该测试会真的起服务并挂住。

已知无关的失败：`tests/tools/test_workspace.py`，以及 `tests/ci_known_failures.txt` 里的条目。每个阶段一个提交，提交说明过 humanizer，不带 Claude 署名；每个阶段在 `CHANGELOG.md` 顶部加一条。

### N-A 清理（约 0.5 天）

| 任务 | 改动 |
|---|---|
| N-A1 | 删除 4 个外壳目录（§3.14） |
| N-A2 | `tests/sdk/test_boundary.py`：`B3_KNOWN = set()` |
| N-A3 | `OMICSCLAW.md` 删掉提到 4 个外壳的那几句；`llms.txt` 删 4 行 |
| N-A4 | 按 Q5 删除 `omicsclaw/common/notebook_export.py` 和 `tests/test_output_ux.py` 里引用它的那条测试 |

验收：

```bash
PYTEST tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py tests/skills tests/test_output_ux.py \
  tests/entry/test_runtime_contract.py
OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python PYTEST -m slow tests/sdk/test_help_probe.py
git grep -n "sc-consensus-clustering\|sc-consensus-integration\|sc-consensus-pseudotime\|consensus-domains" \
  -- ':!docs/' ':!CHANGELOG.md' ':!AGENTS.md' ':!omicsclaw/runtime/' ':!examples/consensus_benchmark/' \
     ':!skills/spatial/consensus-interpret/' ':!skills/spatial/INDEX.md' \
     ':!skills/singlecell/scrna/sc-integrate-cluster/' ':!skills/singlecell/INDEX.md' \
     ':!tests/ensemble/tuning/golden/' ':!tests/runtime/'
```

最后一条命令应该没有输出。排除的路径都是有意保留的引用：`consensus-interpret` 及其 INDEX 行（O4）、`sc-integrate-cluster` 及其 INDEX 行（推迟）、`runtime/` 与基准脚本（0068 PQ1）、历史文档。

### N-B1 运行层核心（约 4 天）

| 任务 | 改动 |
|---|---|
| N-B1-1 | `contract.py`、`_layout.py`、`_hashing.py`、`_ledger.py`、`_manifest.py`（含 `status` 的汇总）、`_lock.py` |
| N-B1-2 | `_percent.py`（§3.3 的子集与报错） |
| N-B1-3 | `_io.py`：`read_input`、`write_output`、`load_demo` 与注册表（3 个单细胞数据集） |
| N-B1-4 | `_skills.py`：解析、导入 `_api.py`、记账代理、桩模式（含 AST 核对）、`run_cli`（子进程环境去掉 `OMICSCLAW_STEP_FILE`、`OMICSCLAW_STEP_LEDGER`、`OMICSCLAW_SKILL_STUBS`；跑完按输出目录补记 `output`） |
| N-B1-5 | `_runners.py` 的 `StepRunner` 与 `PythonKernelRunner`（临时 kernelspec、环境变量、隔离目录）；`_executor.py` 的 `run`、`status`、过期判定、解释器核对、`.R` 文件报错、notebook 拼接；`run.py` 与 `__main__.py` 的 `new`、`run`、`status`；`templates/` |
| N-B1-6 | `environment.yml` 声明 `nbclient>=0.10`；`tests/test_pyproject_thin_pip_layer.py` 的 `CONDA_OWNED` 加 `nbclient`；`tests/sdk/test_public_surface.py`、`test_bootstrap.py` 按 §3.16；`.github/workflows/eval.yml` 的 job1 加装 `nbclient ipykernel` |
| N-B1-7 | 测试，放在 `tests/sdk/notebook/`：`test_percent.py`（子集、标题、markdown 行、未知标签与魔法行的报错和行号）；`test_layout.py`（命名、validate 唯一、骨架只补不动，用预置文件的快照比较）；`test_io.py`（按后缀分派、`writer=`/`reader=`、越界与冻结报错、原子写、目录哈希、契约外的读取只记警告）；`test_skills.py`（连字符目录、`_` 和 `.` 目录跳过、`SKILL.md.disabled` 不算、同名报错、近似名提示、没有 `_api.py`、代理只暴露 `__all__`、参数摘要、没绑定记账时不记账不进桩模式、桩模式缺函数时的 `stub_target_missing`、`run_cli` 的输出目录规则、补记的 `output` 与桩）；`test_executor.py`（用假 runner 测过期的三种原因、跳过最新的步骤、`--force`、同一次 `run` 内的连带过期、上游改动传到下游、manifest 原子写、解释器不一致时 `run` 警告并记 `interpreter_changed_from`、`.R` 文件报错、锁被占用时退出码 3、课题锁防止编号重复（两个子进程））；`test_kernel.py`（真实 kernel：解释器等于执行器的 `sys.executable`、`$HOME` 下不出现文件、cell 出错时保存部分 notebook、用户 IPython startup 不生效、杀掉执行器后 kernel 在 10 秒内退出）；`test_contract.py`（目录名等于 frontmatter 名；契约字面量可以用 `ast.literal_eval` 读取） |

验收：

```bash
PYTEST tests/sdk/notebook tests/sdk/test_public_surface.py tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py \
  tests/test_pyproject_thin_pip_layer.py
```

另在一个只有标准库的 venv 里确认 `python -c "import skills._sdk.notebook"` 能成功（`PYTHONPATH=<checkout>`）；`yaml.safe_load` 解析改过的 `eval.yml`。

### N-B2 验收流程（约 2.5 天）

| 任务 | 改动 |
|---|---|
| N-B2-1 | `replay`：新 kernel、validate 步骤检查、解释器核对与 `--new-interpreter`、输出比较、孤儿文件 |
| N-B2-2 | `_acceptance.py`：`accept`（§3.10 的 4 项条件）、`revise`（baseline 快照，16 MiB 阈值） |
| N-B2-3 | `_apidoc.py` 与 `api` 子命令 |
| N-B2-4 | 测试：`test_replay.py`（全部步骤都运行、validate 最后、没有 validate 时退出码 2、解释器不一致时退出码 2 与 `--new-interpreter` 记下原因、失败即停、`changed_outputs` 与 `orphan_outputs`、`run_cli` 的输出不算孤儿、状态变为 `replayed`、改了步骤后退回 `draft`）；`test_acceptance.py`（4 项条件逐条缺失时退出码 4 和对应的消息、`--skip-review` 记下原话、冻结后三处拒绝、`revise` 的快照与大文件 sha256、同一天两次 revise）；`test_apidoc.py`（签名还原、docstring 原文、`--check` 发现不一致） |

验收：

```bash
PYTEST tests/sdk/notebook
```

再用一个临时课题手动走一遍：`new`、两个步骤、`replay`、写 REPORT、手写一份 APPROVE 审查、`accept`、`revise`，把命令和输出记进实施记录。

### N-C 单细胞试点（约 6.5 天）

每个 skill 依次做：C-x1 录基线（改动之前，`OmicsClaw` 环境）→ C-x2 `_api.py` → C-x3 CLI 薄壳 → C-x4 `SKILL.md` 按附录 B.3 改写并生成 API 段 → C-x5 `examples/example_step.py` → C-x6 测试。顺序是 `sc-qc` → `sc-preprocessing` → `sc-clustering` → `sc-cell-annotation` → `sc-de`。

| 任务 | 改动 |
|---|---|
| N-C0 | `tests/parity/snapshot.py`（`record` 与逐值比较）、`tests/parity/test_sc_pilot_parity.py`（标 `slow`，基线缺失时跳过）；`.gitignore` 加 `tests/parity/golden/`；`pyproject.toml` 注册 `skill_example` marker，默认 `addopts` 排除；`.github/workflows/eval.yml` 的 job1 `-m` 加 `and not skill_example`；`tests/sdk/notebook/test_skill_api_sections.py`、`test_skill_examples.py` |
| N-C1 至 N-C5 | 5 个 skill，每个按上面 6 步，约 1.1 天 |
| N-C6 | `templates/skill/` 同步（§3.13.6）；`templates/skill/README.md` |
| N-C7 | `.github/workflows/eval.yml` 新增 job3 `skill-examples`（是否设为门禁见 Q3）：job1 的 pip 列表加上 `"scanpy[leiden]" umap-learn`；`actions/cache` 缓存 `OMICSCLAW_DEMO_DIR`；运行 `pytest tests/sdk/notebook/test_skill_examples.py -m skill_example -p no:cacheprovider` |

验收（每个 skill 完成后都跑一次）：

```bash
PYTEST tests/sdk/notebook/test_skill_api_sections.py
OCPYTEST skills/singlecell/scrna/<skill>/tests
OCPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py -k <skill>
OCPYTEST -m slow tests/parity/test_sc_pilot_parity.py -k <skill>
OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python PYTEST -m slow tests/sdk/test_help_probe.py tests/sdk/test_sc_scripts_help.py
```

skill 自己的 `tests/` 里有 demo 测试，默认被 `demo` marker 排除，用 `OCPYTEST -m demo skills/singlecell/scrna/<skill>/tests` 跑一次，确认薄壳的 `--demo` 输出没变。

### N-D 框架与契约（约 4 天）

| 任务 | 改动 |
|---|---|
| N-D1 | `OMICSCLAW.md` 按附录 A 改写（定稿前用 writing-for-agents 与 humanizer 各过一遍） |
| N-D2 | `SAFETY_RULES` 按 §3.11.2 |
| N-D3 | `omicsclaw/entry/project.py`（`step_runner_line`、`recent_modules`、布局常量）；`_environment_source` 加执行器一行 |
| N-D4 | `MODULE_REVIEWER` 与注册；提示全文见附录 B.4 |
| N-D5 | `install_skill_deps` 接受一组 skill（§3.11.6） |
| N-D6 | `/recent`（§3.11.7） |
| N-D7 | 契约测试：布局常量、manifest 键、契约里出现的子命令 |
| N-D8 | 文档：`docs/core-features/agent-skills.md`（新的使用方式；§9.4 讲安全规则的那句改成新第 3 条）、`sub-agent.md`（内置审查）、`sandbox.md`（镜像需要 nbclient、ipykernel，`load_demo` 在无网络时的放置位置）、`templates/skill/README.md`；`README.md` 的 What's New 加一句（这是用户可见的主要功能） |
| N-D9 | 在 N-D2 与 N-D4 完成后，按 §3.11.8 重录 `tests/entry/golden/` |

验收：

```bash
OMICSCLAW_WRITE_GOLDEN=1 PYTEST tests/entry/test_ensemble_golden.py   # 只在 N-D9 跑一次
PYTEST tests/entry/test_ensemble_golden.py tests/entry/test_assembly.py tests/entry/test_runtime_contract.py \
  tests/entry/test_subagent_wiring.py tests/entry/test_channel_commands.py tests/entry/test_planning.py \
  tests/skillenv tests/permission/test_foundation_tools_keep_their_prompts.py tests/sdk/notebook/test_contract.py \
  tests/entry/test_entry_is_the_top_layer.py tests/sdk/test_boundary.py
git diff --stat tests/entry/golden/
```

`git diff` 只应列出 `ensemble_off_prompt.txt` 与 `ensemble_off_tools.json`（以及确有原因时的 `ensemble_tools_all.json`），逐行看过的差别只在 safety 段与 `task` 工具。另外用 `build_prompt(...).render().section_stats` 记下改写前后契约、project 两段的 token 数，写进实施记录。

### N-E eval（约 4 天）

| 任务 | 改动 |
|---|---|
| N-E1 | `Case.skill_modules`、桩目录落地与环境变量、所有用例加 `PYTHONDONTWRITEBYTECODE=1`、读记账、`SkillRun.function/source`、`SkillInvoked(function=)`、`_harness.check(timeout_s=)` |
| N-E2 | `tests/evals/fixtures/skill_stubs/sc-qc.py`、`sc-clustering.py` |
| N-E3 | 重写 `tests/evals/dataset/test_skill_routing.py`（§3.15.3 的 8 条） |
| N-E4 | `tests/evals/test_fixtures.py`、`test_runner.py`（`stub_target_missing`、`skill_ran_unstubbed` 来自记账；桩目录下不出现 `__pycache__`）、`test_assertions.py`（`SkillInvoked` 的 function 与 ledger 来源） |
| N-E5 | `live.py` 的 `executed_skill` 读记账；`tests/evals/test_live.py` 加两条 |
| N-E6 | `.github/workflows/eval.yml` 的 job2 改为 `pip install -e . pytest nbclient ipykernel`；`docs/core-features/eval.md` |

验收：

```bash
PYTEST tests/evals
PYTEST tests/evals/dataset -m scripted_eval      # 连跑 3 次，结果一致
```

在只有 `pip install -e . pytest nbclient ipykernel` 的 3.11 venv 里跑一次 `pytest tests/evals/dataset -m scripted_eval`（与 job2 相同的环境），29 条全过，记下耗时。

---

## 5. 测试与验收

**端到端（最终验收，以"核心流程真能跑通"为准）**。在 `OmicsClaw` 环境里，用 `.env` 配置的真实模型，在一个新的临时课题目录（`OMICSCLAW_SKILLS_DIR` 指向 `<checkout>/skills`）里依次请求：对 pbmc3k 做 QC、预处理、聚类、注释、差异表达。期望结果：

1. 产生 5 个模块（编号 01 到 05），每个都有 README、步骤文件、validate 步骤、带输出的模块 notebook、manifest、REPORT（含免责声明）；`docs/analysis_strategy/STRATEGY.md` 写有问题、数据、计划和决定；
2. 每个模块都经过 `replay`、`module-reviewer` 审查、用户确认后 `accept`，`status` 的输出里 5 个模块都是 `ACCEPTED`（manifest 的 `status` 为 `accepted`）；
3. 步骤用到试点 skill 时走 `load_skill`，记账里能看到函数调用和 skill 版本；
4. 任选一个写表格的步骤，用 `PYTHONPATH=<checkout> python analysis/03_clustering/<step>.py` 单独运行，它写出的 CSV 与执行器跑出来的 CSV 逐值一致（scanpy 的随机过程要固定 `random_state`）。h5ad 和 png 的字节内容含时间戳、压缩等不稳定因素，不比较；
5. 改一个上游步骤后，`status` 正确列出下游的过期原因；
6. `/recent` 显示最近 3 个模块的标题和状态；
7. 有 docker 的话，在 sandbox 模式（网络 `none`，镜像装了 nbclient 和 ipykernel，demo 数据通过 `sandbox_mounts` 提供）下跑通一个模块。没有就记为"待 owner 机器验证"。

运行时间、模型调用次数、遇到的问题记进实施记录。不追求统计意义上的评估，一次完整跑通即可。

**一次性的变异检查**（实施者跑完记进实施记录，不进 CI）：

1. 删掉 `sc-clustering/_api.py` 里的 `cluster_summary`：eval 用例 1 报 `stub_target_missing`；`test_skill_api_sections` 失败。
2. 改 `SKILL.md` API 段里的一个默认值：一致性测试失败。
3. 去掉 kernelspec 的解释器固定：`test_kernel.py` 里"解释器等于执行器"失败。
4. 去掉 `IPYTHONDIR` 隔离：eval 用例 1 的 `NoWriteOutside` 失败。
5. 去掉 Runner 的 `PYTHONDONTWRITEBYTECODE=1`：eval 用例 1 的 `NoWriteOutside` 失败（桩目录下出现 `__pycache__`）。
6. 让过期判定忽略输入哈希：eval 用例 5 失败。
7. 让 `run_cli` 不补记输出：eval 用例 8 关于 manifest `outputs` 的断言失败，`test_replay.py` 的"`run_cli` 的输出不算孤儿"失败。
8. 让 `accept` 跳过重放检查：`test_acceptance.py` 对应的那条失败。
9. 把 `module-reviewer` 的工具改成继承全部工具：`test_subagent_wiring` 新加的那条失败。

---

## 6. 风险

| 编号 | 风险 | 处理 |
|---|---|---|
| R1 | kernel 启动在 CI 上慢或不稳，用例超时 | skill 用例超时设为 90 s；`test_kernel.py` 单独测启动；kernel 启动失败时执行器重试一次，并在输出里写明 |
| R2 | 超时后执行器或 kernel 残留：sandbox 只杀记下的 pid；kernel 在独立 session 里 | 本机靠进程组与 ipykernel 的父进程轮询；执行器的看门狗（O7）在父进程变了时杀掉 kernel、记失败的 `run_end` 并退出，覆盖复合命令被杀掉外层 shell 的情况；`test_kernel.py` 覆盖"杀掉执行器后 kernel 退出"和"杀掉外层 shell 后执行器与 kernel 都退出、锁已释放" |
| R3 | `flock` 在网络文件系统或 Docker Desktop for macOS 的文件共享上不保证互斥 | 在 `sandbox.md` 和执行器的 `--help` 里写明；单人本机部署下影响很小 |
| R4 | parity 依赖环境：rapids 环境缺 leidenalg 和 igraph，`sc.tl.leiden` 抛 `ImportError`（`dimred.py:684`）；换了环境，Leiden 结果也可能不同 | 基线只在 `OmicsClaw` 环境里录，测试也只用 `OCPYTEST` 在同一环境里比；基线不提交、不进 CI；用例固定 `random_state` |
| R5 | 长步骤超过 `bash` 的工具超时（默认 585 s） | 契约提醒把长计算拆成多个步骤；执行器输出每步耗时；需要时由 operator 调高 `tool_timeout_s`。后台运行不在本期 |
| R6 | 每次 `status` 都重算大文件的哈希，h5ad 很大时会慢 | 本期不缓存（§1.3）；预算不是约束，慢到影响交互时再加缓存 |
| R7 | 用户的 IPython 配置影响 kernel | 隔离 `IPYTHONDIR` 与 Jupyter 目录 |
| R8 | 契约变长，系统提示的 token 增加 | N-D 记下前后的 `section_stats`；附录 A 估计增加约 1.3k token |
| R9 | 模型绕过 `read_input`/`write_output`，记账与过期判定不完整 | 契约规则、审查子 agent 的检查项、validate 步骤；记账只记录看得到的东西，局限写进 `agent-skills.md` |
| R10 | `load_demo` 在 sandbox 里没有网络，或 checkout 的 `data/` 不在容器里 | 报错信息给出查找位置；`sandbox.md` 写明用 `OMICSCLAW_DEMO_DIR` 加 `sandbox_mounts` |
| R11 | workspace 就是 checkout 时，课题目录混进源码树 | Q4：警告，加 `.gitignore` 条目 |
| R12 | sandbox 里取不到 git 信息 | 记 `null`，保留内容哈希；D5 本来就把内容哈希定为附带记录 |
| R13 | 过渡期 CLI 与 API 两条路径行为分叉 | parity 测试同时比较 CLI 和 API；CLI 薄壳与 API 共用 `_api.py` |
| R14 | 课题背景不再每轮注入（O5），agent 可能在新会话或压缩之后没先读 `STRATEGY.md`，做出与既定计划不一致的选择 | 契约把"开工前先跑 `status`、再读 `STRATEGY.md`"写成步骤；workspace 的长期记忆摘要每轮仍在提示里；审查子 agent 读步骤与 REPORT 时能发现明显偏离。端到端验收时观察 agent 是否照做，不照做再考虑加强契约措辞 |

---

## 7. 裁定与待裁定的问题

### 7.0 owner 的裁定（2026-10-01）

- O1：审核建议的砍减全部接受，移进 §1.3"推迟到后续计划"：R 步骤（`NN_xxx.R` 的执行与渲染）、`archive` 子命令（agent 直接用 `tar`）、哈希缓存、看门狗、原 G7、`/recent` 用旧运行补足、`load_demo` 登记 bulk CSV、改写 `sc-integrate-cluster`。parity 每个 skill 只录默认参数加 1 个变体。第 1 版 Q13 随之作废。
- O2：在 0070 里重录 `tests/entry/golden/ensemble_off_prompt.txt` 和 `ensemble_off_tools.json`，必要时连带 `ensemble_tools_all.json`。依据是测试注释允许"为有意的提示词改动"重录；重录后仍要检查 on 与 off 的差别只在 ensemble 工具（§3.11.8、N-D9）。
- O3：试点 skill 的示例和 parity 测试用 `/opt/conda/envs/OmicsClaw/bin/python -m pytest`，parity 基线也在这个环境里录；其余测试照旧用 `rapids_singlecell`（它缺 leidenalg 和 igraph，`sc.tl.leiden` 会抛 `ImportError`，`skills/singlecell/_lib/dimred.py:684`）。不要在 `OmicsClaw` 解释器下跑 `tests/launch/test_surfaces.py`。R4 与此一致。
- O4：0070 不动 `consensus-interpret`。0068 PQ4 让它默认走 `--no-llm`、留在 index 里，D16 也这么定；4 个外壳早已移出 index，删掉它们不会连带出问题。第 1 版 N-A3 的"90 → 89"连带改动取消。
- O5（第 2 版之后）：课题级文档只保留 `docs/analysis_strategy/STRATEGY.md`，取代 D14 里"课题根放 `PROJECT.md` 并新增提示段注入"和"`METHODS_LEDGER.md` 从 manifest 生成"两部分；D14 的其余内容不变。
  - 不建 `PROJECT.md`，不新增 `## Project` 提示段，`omicsclaw/entry/project.py` 里没有 `project_section`、`PROJECT_FILE`、`PROJECT_PROMPT_LIMIT`，原 G9 删除。理由：长期记忆按 workspace 存放（`<workspace>/.omicsclaw/memory.db`），摘要已经每轮注入；再注入一份课题文件，内容重复，还多一个每轮都会变的块，让提示缓存更容易失效。
  - 不建 `METHODS_LEDGER.md`：它只是 manifest 的派生视图，`status` 子命令按需给出同样的信息，而且是实时的。D13 的"台账记为 ACCEPTED"落在 manifest 的 `status` 字段。课题锁只用于 `new` 分配编号和补齐骨架。methods 汇总以后用按需生成的 `run.py methods` 提供（§1.3）。
  - `STRATEGY.md` 吸收原 `PROJECT.md` 的内容，不注入系统提示。模板四段：Question、Data、Plan（跨模块的分析计划，以及模块为什么按这个顺序）、Decisions（跨模块的决定，注明日期和理由）；不设 Modules 段，模块列表由 `status` 给出。第一次 `new` 时，执行器在文件缺失的情况下写入模板（D17 不变）。
  - 契约：在课题里开工前，先跑 `status`，再读 `STRATEGY.md`；计划或跨模块的决定有变化时，更新 `STRATEGY.md`。
  - Environment 段仍然只加执行器路径一行，不加课题指针或模块状态，免得这一段变得频繁变化。

- O6（第 3 版之后）：§7.2 的 Q1 至 Q6 全部按推荐裁定：Q1 选 a（步骤里用 `run_cli`）；Q2 选 a（5 个 skill，`_api.py` 覆盖全部方法，R 方法不录 parity 基线）；Q3 选 a（job3 一开始就是门禁）；Q4 选 a（只警告，并补 `.gitignore`）；Q5 选 a（只删 `common/notebook_export.py`）；Q6 选 a（不满足就拒绝，解释器不一致时 `run` 警告、`replay` 要求 `--new-interpreter`）。另外定了三件实施上的事：在本地分支 `plan-0070-notebook-runtime` 上开发，每个阶段一个提交，不推送，推送和开 PR 由 owner 决定；§5 的端到端验收用 `.env` 里的真实模型跑，实施者扮演用户确认 `accept`；本机没有 docker，§5 第 7 条记为"待 owner 机器验证"。

- O7（实现完成、独立评估之后，2026-10-01）：
  1. `install_skill_deps` 的"总是允许"只记排好序的 skill 组合，不记包，取代实施记录的偏差 11。理由：包已经限定在所列 skill 的 `## Dependencies` 之内，并且装进隔离的 overlay；`bash` 一旦在会话里被允许，`pip install` 是更宽的旁路；规则太细，"总是允许"就形同虚设。
  2. 同一天的第二次审查会覆盖第一次，这件事在执行器里解决，不改提示词：`replay` 时如果 `reviews/` 里已有审查文件，先存档（加 run_id 或序号后缀改名，或者移进 `reviews/archive/`，二选一并写明），每份审查的 verdict 和 sha256 记进 manifest 的审查历史。`accept --review` 的条件不变。
  3. 执行器加父进程看门狗（从 O1 推迟的清单里提前）：`run` 和 `replay` 期间，一个守护线程轮询 `os.getppid()`；父进程变了（被收养）时，终止正在运行的 kernel，释放模块锁，写一条失败的 `run_end`（原因 "parent exited"），然后退出。场景：agent 跑 `cd … && python run.py … | tail`，sandbox 超时只杀外层 wrapper 的 pid，执行器和 kernel 留下来占着锁。本机测试：一个父 shell 启动执行器，杀掉父 shell，断言执行器几秒内退出、锁已释放、kernel 已退出。看门狗从 §1.3 的推迟表里删除，R2 的处理相应更新。

### 7.1 第 1 版问题的处置与新旧编号

| 第 1 版 | 处置 | 第 2 版 |
|---|---|---|
| Q1 未迁移 skill 怎么用 | 仍待裁定 | Q1 |
| Q2 私有模块文件名 | 计划内决定：`_api.py`（§3.13.2） | 无 |
| Q3 `consensus-interpret` | O4：0070 不动 | 无 |
| Q4 试点范围与方法覆盖 | 仍待裁定；parity 部分按 O1 改写 | Q2 |
| Q5 示例在 CI 里怎么跑 | 只留"是否设为门禁" | Q3 |
| Q6 parity 标准与基线 | 计划内决定（§3.13.6）；环境按 O3，变体数按 O1 | 无 |
| Q7 8 条 skill 用例 | D15 已定：按 §3.15.3 的 8 条重写，旧的 7 条 CLI 路由用例移出门禁 | 无 |
| Q8 workspace 就是 checkout | 仍待裁定 | Q4 |
| Q9 失效代码 | 仍待裁定 | Q5 |
| Q10 审查子 agent 的工具 | D13 已定：只读，`read_file` 与 `use_skill`（§3.11.5） | 无 |
| Q11 检查拒绝还是警告 | 仍待裁定；并入解释器核对 | Q6 |
| Q12 子 agent 改动的归属 | 计划内决定：只记步骤文件的哈希变化，不记是谁改的（§3.5.1）。记录执行者要改本机与 sandbox 两条执行路径（sandbox 的 `docker exec` 现在不传环境变量），收益不抵改动 | 无 |
| Q13 R 步骤和 `_archive` | O1 推迟，作废 | 无 |
| Q14 `install_skill_deps` 参数形状 | 计划内决定：改成 `skills` 数组（§3.11.6） | 无 |

### 7.2 待 owner 裁定的问题（已由 O6 裁定，保留备查）

每题先列选项，再给推荐和理由。

#### Q1 未迁移的 skill 在课题布局下怎么用

0070 之后只有 5 个 skill 有函数库，其余 85 个只有 CLI。
- a. `_sdk` 提供 `run_cli(skill, *args, inputs=...)`，步骤里调用，输出进 `results/<NN>/intermediate/<skill>/`，记账为 `skill_cli` 并补记输出文件，可以重放。
- b. agent 照旧用 `bash` 直接跑 CLI，`--output` 指向本模块的 `intermediate/<skill>/`，在 README 里记下命令；不记账，也不在重放范围内。
- c. 全部 skill 迁移完之前不改契约。

推荐 a。验收的第一步是整模块重放；按 b，只要一个模块用到未迁移的 skill，它就无法完整重放，也就无法按 D13 验收，而过渡期里这是常态。a 的成本约 100 行代码加 1 条 eval 用例，而且旧 fixture 可以直接复用。c 会把契约切换推迟到所有迁移计划之后。

#### Q2 试点范围与方法覆盖

- a. 5 个 skill（`sc-qc`、`sc-preprocessing`、`sc-clustering`、`sc-cell-annotation`、`sc-de`）；`_api.py` 覆盖 CLI 的全部方法，包括调用 R 的方法。parity 按 O1 只录默认参数加 1 个 Python 变体；R 方法不录基线，由 skill 自带的 R 测试覆盖（没有 `Rscript` 时跳过）。
- b. 同样 5 个 skill，`_api.py` 只覆盖 Python 方法，R 方法留到下一批，暂时经 `run_cli` 调用。
- c. 4 个 skill，去掉 `sc-qc`（`sc-preprocessing` 自己也算 QC 指标）。

推荐 a。R 方法在脚本里已经是函数（`run_seurat_preprocessing`、`annotate_singler`、`run_de_deseq2_r_method`），搬进 `_api.py` 是机械工作。只搬一半的话，同一个 skill 会有两种用法，契约和 SKILL.md 都要解释例外。`sc-qc` 是主链的第一个模块，保留它，端到端验收才是完整的。

#### Q3 示例 job 是否设为门禁

job3 `skill-examples` 在 N-C7 新增（装 scanpy、leidenalg、umap-learn、nbclient、ipykernel，pbmc3k 下载后用 `actions/cache` 缓存）。
- a. 一开始就设为必需的检查（门禁）。
- b. 先不设为必需，稳定两周再改成门禁。

推荐 a。D3 要求 CI 真跑；示例是 `## API` 文档的一部分，坏了没人发现，文档就会悄悄过时。下载有失败的风险，所以要缓存；如果 owner 担心 CI 不稳，b 是折中。

#### Q4 workspace 就是 OmicsClaw checkout 时

不设 `OMICSCLAW_SKILLS_DIR` 的部署，workspace 就是 checkout（§2.2）。
- a. `new` 打印警告，建议另开课题目录并设 `OMICSCLAW_SKILLS_DIR`；`.gitignore` 加 `/analysis/`、`/results/`、`/manifests/`、`/work/`、`/docs/analysis_strategy/`。
- b. 拒绝，除非加 `--in-checkout`。
- c. 不处理。

推荐 a。拒绝会挡住 owner 最常用的开发方式；`.gitignore` 加上之后，课题文件不会进提交。checkout 里本来就有 `scripts/` 和 `docs/`：按 D17 不动已有目录，所以课题的 `scripts/` 会和仓库的 `scripts/` 混在一起，警告里要说明这一点。

#### Q5 失效代码

- a. 0070 删除 `omicsclaw/common/notebook_export.py` 及其测试；信封校验留到删 CLI 的计划；`runtime/*` 按 0068 PQ1 留到 ensemble 计划。
- b. 全部留着。
- c. 0070 全部删除。

推荐 a。`notebook_export` 已被新渲染器取代，生成的 notebook 本身是坏的，留着只会被误用。信封校验在过渡期仍有用（CLI 薄壳写 `result.json`，ensemble 读它）。`runtime/` 的去留 owner 已经裁定过。

#### Q6 验收、冻结与解释器检查：拒绝还是警告

- a. `accept` 条件不满足时拒绝（退出码 4）；冻结的模块 `write_output`、`run`、`replay` 拒绝，提示先 `revise`；解释器与 manifest 不一致时 `run` 警告，`replay` 拒绝，除非加 `--new-interpreter "<原因>"`。
- b. 都只警告并记账。

推荐 a。这些是工作流检查（G2、G3、G9），绕过的成本比遵守高，正常路径上能保证 baseline 快照、重放和环境一致一定会发生。按 b，一次疏忽就会让 ACCEPTED 失去意义。

---

## 附录 A：`OMICSCLAW.md` 改写草稿

只列有改动的部分。其余部分（Skill Routing Table、Finding a skill、Re-rendering plots、User-facing notes）不变。

**Identity，第二、三句**：

> You answer omics questions with analysis you run in this project's modules, using the specialized skills. Every result you report traces back to a step file and the outputs the step runner recorded for it.

**Operating Rules，第 2 条**：

> 2. Do non-trivial analysis in a module (see "Projects, modules and steps"), using the skills that cover it.

**取代 "How to Use a Skill" 的新一节**：

````markdown
## Projects, modules and steps

The workspace is one research project:

| Path | Holds | Written by |
|---|---|---|
| `data/` | the user's input files | the user; you read it and write elsewhere |
| `analysis/<NN_slug>/` | one module's code: `README.md` and step files | you |
| `results/<NN_slug>/` | that module's outputs | the step runner; you add `M<NN>_<slug>_REPORT.md` |
| `docs/analysis_strategy/STRATEGY.md` | the question, the data, the plan across modules, and decisions that span modules | you and the user |
| `manifests/`, `scripts/`, `work/` | data manifests, project-wide scripts, scratch | you |

Before you start work in a project, run `status`, then read `docs/analysis_strategy/STRATEGY.md`. When the plan or a decision that spans modules changes, update `STRATEGY.md`.

A **module** is one analysis stage whose figures and tables can be reported on their own: QC, preprocessing, clustering, annotation. Modules are numbered in creation order (`01_qc`, `02_preprocess`). Start a new module when the work reaches a new stage; tell the user what it is for before you create it, and ask when you are unsure whether the work belongs in the current one.

### Writing a step

A **step** is one file in `analysis/<NN_slug>/` named `<k>_<name>.py`, for example `02_cluster.py`. A letter after the number marks a variant (`02b_cluster_louvain.py`). Steps run in name order. Every module has one `<k>_validate.py` step, which runs last and asserts what the report relies on: tables are non-empty, expected columns exist, counts are in range.

A step is a plain Python file split into cells by `# %%` lines. `# %% [markdown]` starts a prose cell whose lines begin with `# `. Open each step with a markdown cell that says what it does, what it reads and which skill functions it calls.

```python
# %% [markdown]
# Leiden clustering of the preprocessed cells.
# Reads results/02_preprocess/intermediate/adata.h5ad.
# Calls sc-clustering: cluster, cluster_summary.

# %%
from skills._sdk.notebook import load_skill, read_input, write_output

clustering = load_skill("sc-clustering")
adata = read_input("results/02_preprocess/intermediate/adata.h5ad")

# %%
# resolution 0.8: the user wants broad cell types; sc-clustering's default is 1.0.
adata = clustering.cluster(adata, resolution=0.8)
write_output(adata, "intermediate/adata.h5ad")
write_output(clustering.cluster_summary(adata), "tables/cluster_summary.csv")
```

- Read every input with `read_input` and write every output with `write_output`; these two calls are what the runner records. `read_input` takes a path from the project root: `data/`, an earlier module's `results/<NN_slug>/intermediate/` and `tables/`, or what an earlier step of this module wrote. `write_output` takes a path inside this module's results: `figures/`, `tables/`, `intermediate/` or `logs/`.
- When a skill's SKILL.md has an `## API` section, call its functions through `load_skill(name)`. Where a skill function covers what the step does, call it; when you write the code yourself, give the reason in a markdown cell.
- A skill without an `## API` section has a CLI: call it from a step with `run_cli(name, "--input", <path>, <flags from its SKILL.md>, inputs=[<path>])`. Its output lands in `results/<NN_slug>/intermediate/<name>/`.
- Every value the skill does not give you, such as a threshold, a resolution or a cutoff, appears in the step with its reason.
- Keep steps plain Python, with no `%` or `!` lines, so each file also runs as `python <file>` from the project root.
- `load_demo(name)` loads a demo dataset inside a step when the user has no data.

### Running steps

Call the step runner (its command is in the Environment section) with `bash` from the project root, as one command on its own:

| Command | Does |
|---|---|
| `new <slug>` | creates the next module, any missing project folders and the `STRATEGY.md` template |
| `run analysis/<NN_slug>` | runs the module's stale steps in order |
| `run <step file> --force` | runs one step even when it is up to date |
| `status` | lists every module's status, every stale step and why |
| `replay analysis/<NN_slug>` | reruns every step of the module from scratch, validate last |
| `accept analysis/<NN_slug> --review <file>` | records the user's acceptance and freezes the module |
| `revise analysis/<NN_slug>` | snapshots an accepted module so it can change |

A step is **stale** when its file changed, or a file it read changed, since its last successful run. After rerunning a module that later modules read from, run `status` and rerun the modules it lists as stale. Read the runner's output after every run: it lists each step's status, the skill functions it called and its notebook. When a module needs packages the base environment lacks, run the step runner with the interpreter `install_skill_deps` returned, and keep using that interpreter for the module; the runner warns when the interpreter changes, and `replay` asks you to confirm the change with `--new-interpreter "<reason>"`.

### Finishing a module

1. `replay` the module. Done when every step, the validate step included, reports `ok`.
2. Write `results/<NN_slug>/M<NN>_<slug>_REPORT.md`: what was done, the key numbers with the tables they come from, the figures, and the disclaimer.
3. Delegate "Review module <NN_slug>" to the `module-reviewer` sub-agent and save its reply unchanged to `results/<NN_slug>/reviews/<YYYY-MM-DD>_review.md`. On `VERDICT: REVISE`, fix the findings and go back to step 1. Skip the review only when the user asks you to.
4. Show the user the report and the verdict. When the user says the module is accepted, run `accept analysis/<NN_slug> --review <review file>`, or `--skip-review "<the user's words>"` when they asked to skip the review.

To change an accepted module, tell the user first, then run `revise`; it keeps the accepted results in `results/<NN_slug>/baseline/`. To set a superseded module aside, ask the user, then pack `analysis/<NN_slug>/` and `results/<NN_slug>/` into one `tar.gz` under `results/_archive/`.

## Skills

Each skill's `SKILL.md` gives its methods, defaults and pitfalls; `use_skill` returns it with the skill's directory. Read it before writing a step that uses the skill. A skill with an `## API` section lists its functions there and ships a runnable example in `examples/example_step.py`. A skill with only a CLI documents its flags; `--help` confirms a flag before you spend a run on it.

Directories whose names start with `_` are not skills.

### Dependencies

（原文保留，最后一句改为：）… it can install missing ones into an isolated environment for a whole module; the base environment is never changed.
````

**Demo Data**：表格保留，第一句改为 "Inside a step, `load_demo("pbmc3k_raw")` and the other registered datasets load demo data; most skill CLIs also accept `--demo`."

**删除**："Chaining skills"一节（模块之间经 `intermediate/` 衔接，已在新一节里说明），以及 4 个外壳的那几句。

估计：新一节约 80 行，删去约 45 行，净增约 35 行，约 1.3k token。

---

## 附录 B：模板与提示

### B.1 `STRATEGY.md` 模板（`new` 在 `docs/analysis_strategy/STRATEGY.md` 缺失时写入）

```markdown
# <Project title>: analysis strategy

<!-- Read this before you start work in the project, after running the step runner's `status`. Update it when the plan or a decision that spans modules changes. Module status comes from `status`, not from this file. -->

## Question

<One or two sentences: what the user wants to learn.>

## Data

<One line per input under data/: file, what it is, organism, tissue, platform, samples.>

## Plan

<The modules the analysis needs, in order, and why that order: which module's outputs each later module reads.>

## Decisions

<One dated line per decision that spans modules, with its reason, newest last. Example: 2026-10-01: keep cells under 20% mitochondrial reads in every module, the lab's usual threshold.>
```

### B.2 模块 `README.md` 模板（`new` 写入）

```markdown
# <NN_slug>

<!-- Written by the agent. The step runner only checks that this file exists. -->

## Purpose

<What this module answers, in one paragraph.>

## Inputs

<Upstream modules and data files this module reads.>

## Steps

<One line per step file: what it does.>

## Decisions

<Choices made in this module and why.>

## Running outside OmicsClaw

    PYTHONPATH=<checkout> python analysis/<NN_slug>/<step>.py      # one step, from the project root
    python <checkout>/skills/_sdk/notebook/run.py replay analysis/<NN_slug>
```

### B.3 试点 skill 的 `SKILL.md` 正文模板

````markdown
---
name: sc-clustering
description: <unchanged routing text>
tags: <unchanged>
---

# sc-clustering

## When to use

<unchanged: the load/skip split and the adjacent skills>

## Use from a step

```python
clustering = load_skill("sc-clustering")
adata = clustering.cluster(adata, resolution=1.0)
write_output(clustering.cluster_summary(adata), "tables/cluster_summary.csv")
```

A complete step that runs on demo data: `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `cluster(adata, *, use_rep=None, n_neighbors=15, n_pcs=50, embedding='umap', method='leiden', resolution=1.0, random_state=0)`

<docstring, verbatim>

<!-- api:end -->

## Methods and parameters

<Which method when. For every default: its value and where it comes from (the method's paper, the scanpy default, the lab convention). Which values the user should decide, and how to ask.>

## Gotchas

<The failure modes an agent hits, each with the fix.>

## Inputs and outputs

<The AnnData keys read (obsm, obs, layers) and written by each function.>

## CLI

`sc_cluster.py` runs the same functions outside a project: `python <skill directory>/sc_cluster.py --help`.

## See also

## Dependencies

<unchanged package line>
````

### B.4 `module-reviewer` 的系统提示

```
You review one analysis module of an OmicsClaw project. You can read files and load skills; you cannot change anything, and nobody will answer questions.

Start from results/<NN_slug>/provenance/manifest.json. It lists the module's steps, what each read and wrote, the skill functions each called and the latest replay.

Check every item below and note each finding with its file and line:
1. Each step file: inputs come from data/ or an earlier module's intermediate/ or tables/; every value the skill does not give has a stated reason; the skill functions the step's first cell names match the ones the manifest recorded; where a skill function covers the work and the step does not use it, the step says why.
2. The validate step checks the outputs the REPORT relies on.
3. The REPORT (M<NN>_<slug>_REPORT.md): every number matches a table or log in results/<NN_slug>/; every figure it cites exists and is not listed under orphan_outputs; claims stay within what the steps computed; it carries the disclaimer.
4. The replay in the manifest succeeded and covers the current step files.

Your first line is the verdict, exactly `VERDICT: APPROVE` or `VERDICT: REVISE`. Then list the findings, most serious first. Choose REVISE when any finding would change a number, a figure or a conclusion.
```

---

## 附录 C：示例步骤（`skills/singlecell/scrna/sc-clustering/examples/example_step.py`）

```python
# %% [markdown]
# Cluster PBMC3k with sc-clustering's defaults and check the result.
# Reads the pbmc3k_processed demo dataset.
# Calls sc-clustering: cluster, cluster_summary, embedding_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

clustering = load_skill("sc-clustering")
adata = load_demo("pbmc3k_processed")

# %%
adata = clustering.cluster(adata, resolution=1.0, random_state=0)
summary = clustering.cluster_summary(adata, key="leiden")
write_output(summary, "tables/cluster_summary.csv")
write_output(clustering.embedding_figure(adata, color="leiden"), "figures/umap_leiden.png")

# %%
assert adata.obs["leiden"].nunique() >= 4
assert int(summary["n_cells"].sum()) == adata.n_obs
```
