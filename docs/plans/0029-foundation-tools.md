# 计划 0029 — 基础工具（read / write / bash，edit 预留）

框架分阶段重建的第 4.5 步（见 `docs/FRAMEWORK-REBUILD.md`）。第 4 步
（`omicsclaw/tools/`，计划 0028）交付了注册表、适配器与 3 个参考工具；
本步在它上面建**真正干活的基础工具**。

状态：**待审核**。独立子 agent 审核 → owner 审核 → 再决定执行。

---

## 0. 材料来源与可核实性（先说清楚，因为这直接关系到能不能照搬）

第 3 步买到的最贵教训是：**从参照系搬结构是资产，搬字面量和行为是负债**
（计划 0027 附录 B）。所以本计划的每一条都标注了来源与可核实性：

| 来源 | 本机可核实性 | 本计划如何使用 |
|---|---|---|
| **harness9** `/workspace/dataset/private/zhouwg_data/harness9/internal/tools/` | ✅ **可逐行引证**，本计划所有 harness9 断言都给了文件:行号 | 主要参照系。结构照搬，字面量逐条在 Python 下重验 |
| **OmicsClaw 自身**（`runtime/tools/builders/engineering.py` 的 14 个通用编码工具、`services/path_validation.py`） | ✅ 可逐行引证 | 能力对照的真相源（§6） |
| **openai/codex** | ✅ **已联网核实**（owner 授权后补做） | 仅作**旁证**，不作设计依据。见附录 A |
| **earendil-works/pi** | ✅ **已联网核实到源码级** | 同上。见附录 A |

> 原稿写的是「本机无副本、无网络，一律标注未核实」。owner 指出协调者的
> 检索工具与仓库测试环境不是同一条网络路径，补做后两者都核实到了源码级。
> **但它们的地位没变：旁证，不是依据。** owner 已裁定按 harness9 的设计做，
> 而附录 A 的价值恰恰在于它显示 harness9 的那些参数是**刻意的取舍**——
> 三个工业级实现在几乎每个参数上都不一致，所以没有一个数字是普适真理。

---

## 1. 目标

让 agent 具备「看环境、改文件、执行命令」这三项基本能力，全部建立在第 4 步
的 `Tool` Protocol 与 `ToolRegistry` 之上。

```python
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.builtin import read_tool, write_tool, bash_tool

registry = ToolRegistry()
registry.register(read_tool(workspace))
registry.register(write_tool(workspace))
registry.register(bash_tool(workspace))
```

### 非目标

- **不实现 `edit`。** owner 已明确它因多级降级的复杂性单独一步做。本步只
  **预留接缝并预埋它的陷阱**（见 Q9、§12）。
- **不接线。** 与第 1–4 步一致，交付后没有生产调用方；`runtime/tools/`
  的 14 个既有编码工具继续原样服务所有 Surface。
- **不做沙箱容器，但必须留出 harness9 那个注入接缝。** 见 Q11。

  > ⚠️ **本条原先写的是「OmicsClaw 没有任何 sandbox / docker 设施（已核：
  > 全仓库无相关模块）」——那个「已核」是假的。** 协调者跑的是
  > `grep -rln "docker\|sandbox" | head -5`，**拿一个被截断到 5 条的文件名
  > 列表当成了「不存在」的证据**，也没去 grep 真正的技术名（`bwrap` /
  > `unshare`）。**截断的搜索结果不是缺席的证据**——这正是本项目反复警告
  > 子 agent 的那一种错。
  >
  > 实际上 `omicsclaw/autonomous/`、`skill/execution/` 下有一套基于
  > bubblewrap 的隔离设施（ADR 0032）。**但 owner 已明确：那是旧架构，
  > 正在整体推倒重来，本次重建不受它干扰、也不复用它。** 所以本步的结论
  > 不变（不做容器化），只是理由从「没有」改成「有但不作数」。
- **不迁移那 14 个既有编码工具。** 同计划 0028 §11 的理由：迁移是逐个
  语义验证的活。

---

## 2. 工具清单与裁决

owner 要求「把 harness9 中涉及的必要的额外工具也加上」。harness9 的
`internal/tools/` 共 16 个非测试文件，逐个裁决：

| harness9 | 性质 | 本步 | 理由 |
|---|---|---|---|
| `read_file.go` | 工具 | ✅ **做** | owner 点名 |
| `write_file.go` | 工具 | ✅ **做** | owner 点名 |
| `bash.go` | 工具 | ✅ **做** | owner 点名 |
| `edit_file.go` | 工具 | ⏸ **预留** | owner 明确下一步做 |
| `safe_path.go` | **助手** | ✅ **必做** | 不是「额外工具」，是 read/write/edit/bash 的**前置条件**。没有它，`write` 就是一个能写满整块盘的洞 |
| `path_locker.go` | **助手** | ✅ **必做** | 见 Q7。第 4 步的债 #1 使它从「优化」变成了「必需」 |
| `plan_write.go` | 工具 | ❌ **不做**（原稿判「做」，独立审核推翻，接受） | 见下 |
| `memory_search.go` / `memory_write.go` | 工具 | ❌ **不做** | OmicsClaw 已有 28 模块的图记忆系统（`omicsclaw/memory/`），是**第 6 步**的目标。现在重建一个小的，等于给第 6 步制造一个要合并的分叉 |
| `web_fetch.go` / `web_search.go` / `web_content.go` | 工具 | ❌ **不做** | 三条理由：① 本环境**无网络**，测试只能全靠 fake，而「没跑过真实端点」已经是第 2 步记在案的债；② `runtime/tools/builders/engineering.py` 已有 `web_fetch`/`web_search` 在服役；③ 它们的前置是 `web_safety.go`，而那是一整套独立的安全设计，塞进「基础工具」这一步会让评估失焦 |
| `web_safety.go` | **助手** | ❌ **不做，但必须留档** | 见 §12。这是计划 0028 §11 债 #3：本仓 `web_fetch` 的全部检查是 URL 前缀，`169.254.169.254` 可达。本步不碰 web 工具，所以不引入这个洞，**但也没有修它** |
| `base.go` / `registry.go` / `mcp_adapter.go` | 基础设施 | ✅ 第 4 步已交付 | — |

**`plan_write` 为什么做**：它是长程任务的自我约束机制，且 harness9 在它
里面放了一条**防作弊校验**——一次调用中最多允许 1 个条目从 pending 直接
跳到 completed，超过即判为「幻觉执行」并拒绝写入（`plan_write.go:9-15`，
注释记录原始 bug 是「11 个条目中 9 个被一次性批量完成」）。这条是别人用
真实故障换来的，值得拿。OmicsClaw 侧有对应物 `todo_write`
（`builders/engineering.py:411`），迁移时要对照。

> **裁决已改为「本步不做，留到第 6 步会话层落地后一次做对」**（原稿判
> 「做一个不持久化的版本」，独立审核推翻，协调者接受——它的理由比原稿
> 自己给的退路更硬）：
>
> - harness9 的 `PlanWriteTool` 注入一个会话级 `planning.PlanStore`，而
>   本项目的会话层要到第 6 步。原稿的方案是把计划状态塞进
>   `ToolContext.values`（一个 per-turn 的 contextvar 袋）——**而本项目
>   现有的 `todo_write` 是按 `session_id`/`chat_id` 落盘的**。两种存储
>   模型不兼容，等于先造一个「假的会话态」，第 6 步真会话层落地时大概率
>   整个推翻。**先建一次要拆的房子。**
> - Task A→B→C→D 已经是纯串行链，插一个 B2 只是拉长交付。
>
> **但那条防作弊校验要留档，别丢**：审核方核实了
> `engineering.py:1004-1059` 的 `todo_write` **没有**任何等价校验（每次
> 调用直接 `store.tasks = []` 整表重建），所以 harness9 那条「一次调用最多
> 允许 1 个条目从 pending 直跳 completed，超过即判为幻觉执行并拒绝写入」
> （`plan_write.go:9-15`，注释记录原始 bug 是「11 个条目中 9 个被一次性
> 批量完成」）确实是**新增能力，不是重复造轮子**。结转到 §12。

---

## 3. 文件

```
omicsclaw/tools/_workspace.py     ~200   沙箱边界（safe_path 对应物）+ 敏感路径
omicsclaw/tools/_pathlock.py      ~120   路径级 asyncio 读写锁 + 引用计数
omicsclaw/tools/builtin/read.py   ~320   ReadTool
omicsclaw/tools/builtin/write.py  ~200   WriteTool
omicsclaw/tools/builtin/bash.py   ~380   BashTool
                                 ~1,220

tests/tools/
├── test_workspace.py          路径遍历、绝对路径、符号链接、敏感路径、前缀误判
├── test_pathlock.py           并发读、写排他、引用计数归零、asyncio 而非 threading
├── test_read.py               行号模式 / 字节模式、截断提示、超长行降级
├── test_write.py              覆盖语义、自动建目录、字节数回报
├── test_bash.py               退出码语义、超时横幅、输出截断、后台进程不阻塞
（原稿的 `test_plan.py` 随 `plan` 工具一并取消，见 §2）
```

`_workspace.py` 与 `_pathlock.py` 带下划线前缀、放在包根而非 `builtin/`：
它们是**助手不是工具**，`edit` 下一步也要用。

> **行数预算按计划 0028 附录 B 的实测系数（原稿 ×3，参考工具 ×4）给出，
> 已经乘过了。** 0028 连续两次低估 1.7–3.8 倍，差额全是解释「为什么是
> 这个形状」的 docstring。

---

## 4. 决策

### Q1 —— 沙箱边界重写，不复用 `services/path_validation.py`

`omicsclaw/services/path_validation.py` 有 `validate_path(filepath,
allowed_root)`、`validate_input_path()` 等，**但第 4 步的分层约束禁止导入
它**（`omicsclaw/tools/` 在 `omicsclaw` 命名空间内只许导 `omicsclaw.schema`，
白名单，AST + 行为探针双重强制）。

这与第 4 步 `FunctionTool` 重写 JSON Schema 校验是同一个局面，而那一次的
处置被证明是对的：实现方与旧 `validation.py` 做了 **40 组**参数化对拍
（`test_function_tool.py` 的 `_CROSSCHECK`，实测收集 40 条），**零差异**；
独立评估方 D2 另外用自己构造的随机语料做了约 544 组 `(schema, value)` 的
交叉验证，同样零差异。

> ⚠️ **本段原先把 D2 的 544 记成了「Task B 做了 544 组」**，独立审核指出
> 后复核改正。两次核查都真实存在，但**是两方各自做的，不是一方做的**——
> 把独立验证的规模算到被验证方头上，等于把交叉印证的价值说没了。
**照办：重写，并与 `services/path_validation.py` 对拍行为差异，差异要么
消除、要么写进 docstring。**

> **不要把这条读成「分层约束很讨厌」。** 它正是第 4 步唯一挡住
> 「顺手 import 一下复用」的东西，而那条盲区已经被证明存在（计划 0028
> Q7 的勘误）。重写的成本是一次性的，复用的成本是把工具层重新焊死在
> runtime 上。

### Q2 —— `bash` / `write` 的默认策略：**`ASK`，且本步交付后它们是「惰性」的**

这是本步最重要、也最容易被实现者含糊掉的一条。

第 4 步的 `ToolPolicy` 默认是设防值（`risk_level=HIGH`、
`approval_mode=ASK`），且 `require_approval` 在**没有审批通道绑定时
fail-closed**——返回 `is_error` 并拒绝执行。

而**今天没有任何生产代码绑定 `ApprovalChannel`**（第 4 步已核实）。所以：

> **`bash` 与 `write` 交付后，在任何 Surface 绑定审批通道之前，是完全跑
> 不起来的。** 这不是 bug，是 fail-closed 设计的正确表现。

三条路，**本计划选第 1 条**：

1. ✅ **保持 `ASK`，接受它暂时惰性。** 与第 1–4 步「不接线」一致：本步
   交付的是能力，不是可用的产品。想在受控环境里跑通的人显式传
   `register(tool, ToolPolicy(approval_mode=AUTO))` —— **那是一个必须
   说出口的动作**，而不是一个默认。

   > ⚠️ **原稿写的是「构造函数接受 `policy=` 覆盖」，那是一条更弱、且与
   > 0028 Q5 抵触的旁路**（Task B 指出，判得对）。`require_approval` 读的是
   > `effective_policy()` ← `policy_for()` ← **`register(policy=)` 优先**；
   > 构造函数只能设 `tool.policy`，那是**回落项**，部署一旦在注册时声明过
   > 策略，构造函数里的值就永远不生效。留着它等于给运维两条路径，而其中
   > 一条在最要紧的场景下是哑的。**统一指向 `register(policy=)`。**
2. ❌ 默认 `AUTO`（harness9 的 "YOLO 哲学"，`bash.go:3-4`）。harness9 有
   docker 沙箱兜底，**本项目没有**。在一台放着基因组数据、`~/.ssh` 可达的
   机器上，默认无人值守地执行任意 shell，是拿别人的数据赌自己的判断。
3. ❌ 给 `bash` 发明一个绕过审批的旁路。那等于把 Q5 的三级策略解析推翻，
   而它刚刚才被修好。

**由此产生一条硬排序**（owner 已同意）：
**修 R3（审批等待被计进 `tool_timeout`）必须排在任何 Surface 绑定审批
通道之前。** 本步交付这些工具会让 R3 从「零暴露」变成「一接线就中」。

### Q2b —— `read` 的默认策略：`AUTO` + `read_only=True`

**这是一条独立的、安全相关的决定，不是 Q2 的附注。**（原稿在 §5 表格里写
「`read` 为 `ASK`?→见 Q2 讨论」，而 Q2 通篇只谈 `bash`/`write`——那是一个
指向空处的交叉引用，独立审核指出后补成本条。按本项目纪律，门控默认值
不得留给实现者临场发挥。）

**裁决：`ToolPolicy(risk_level=LOW, approval_mode=AUTO, read_only=True,
concurrency_safe=True)`。**

理由：
- `read` 的边界是 `_workspace.py`——它读不到工作区之外，也读不到 Q8 的
  敏感路径。**边界由路径校验提供，不由审批提供**，所以审批在这里只是摩擦。
- 反面成本是具体的：`ToolPolicy()` 的默认是 `HIGH`+`ASK`，而
  `require_approval` 在无通道时 fail-closed。**若不显式声明，一个纯只读
  工具会因为没人审批而读不了一行文件**，并且 Task B/D 的每一条 `read`
  测试都要记得手工传 `policy=` 覆盖——摩擦会诱导实现者在测试里养成绕过
  策略的习惯，那比默认值本身更危险。
- `read_only=True` / `concurrency_safe=True` 是**声明**字段（计划 0028 的
  `ToolPolicy` docstring 把字段分成「权限」与「声明」两类），不参与门控，
  但它们是装配层将来过滤的依据，属实即应声明。

> ⚠️ 与 Q2 的不对称是刻意的，判据是**「这个工具能不能造成不可逆的后果」**：
> `read` 不能，`write`/`bash` 能。不是「危险不危险」这种模糊感觉。

### Q3 —— 输出截断在**工具层**做，不等存储层

计划 0028 §11 债 #14 把「工具输出上限」判给了存储层。**但存储层不存在，
而 `bash` 是本项目第一个能一次吐 200MB 的工具。**

照 harness9 `bash.go:205-222`：上限 16,000、**头 1/3 + 尾 2/3**、中间标记
省略。保尾的理由写在它注释里，是实测教训：

> 测试运行器（pytest / go test）的 verbose 进度在前，而最关键的
> `FAILED` / traceback / `=== N failed ===` 汇总在最后。旧实现只保留头部，
> **恰好把诊断信息切掉**。

**这是必须照搬的「行为」**，而不是可以自己拍的参数。

> ⚠️ **但 UTF-8 边界回退那两个函数（`trimToValidUTF8Suffix/Prefix`）
> 不要直译。** Go 的 `string` 是字节序列，切片会切碎多字节字符；Python 的
> `str` 是码点序列，`s[:n]` **不可能**产生半个字符。直译过来是一段**永远
> 不会触发**的死代码——正是第 3 步「Go 字面量在 Python 不可达」那类缺陷的
> 教科书形态。
>
> Python 下真正需要决定的是**按字符还是按字节计 16,000**。建议按**字符**
> （与 `len(str)` 一致，也与 LLM 的 token 估算更接近），并在 docstring 里
> 写明这是刻意偏离。

### Q4 —— 超时：工具自己的预算**必须小于**引擎的 `tool_timeout`

harness9：默认 120s、上限 600s、模型可用 `timeout_secs` 单次放宽
（`bash.go:29-32, 72-84`），超时后追加**机器可读横幅**
（`bash.go:199-203`），让模型能区分「被 harness 杀掉」与「代码报错」。

**本项目有一个 harness9 没有的约束**：`EngineConfig.tool_timeout` 默认
**60 秒**，包住整个 `executor.execute(call)`（计划 0028 §11 债 #2 / #15）。
所以：

> **若 bash 的默认超时照抄 120s，引擎会在 60s 先杀掉它，bash 自己的超时
> 逻辑和那条精心设计的横幅永远不会执行。** 照抄字面量在这里不是无害的，
> 是直接让功能不可达——与第 3 步那条网络错误字符串同一种死法。

**裁决**：
- bash 的默认超时取 `min(120s, engine_budget - margin)`，**但工具层读不到
  `EngineConfig`**（分层约束）。所以改为：**构造函数参数 `timeout`，默认
  **45 秒**（留 15 秒余量给 60 秒的引擎预算），docstring 写明这个数字
  是从引擎默认值倒推的，以及引擎默认值改了这里要跟着改。**
- `timeout_secs` 的上限同样受制于引擎预算，**不是 600s**。**上限 = 45s，
  与默认值相同——等于本步不提供协商空间。**

  > ⚠️ **原稿写的是「2 倍且不超过 55s」，那是一个没有推导过程的第二个
  > 魔数**（独立审核指出，判得对）。55s 只给 5s 边际，恰恰是 Q4 全篇要防的
  > 那类「引擎先杀、bash 的横幅永远跑不到」的风险——只是从「默认路径必然
  > 发生」降级成「模型主动要长超时时才发生」，风险类型没变，而精心留出的
  > 15s 边际被砍掉三分之二。
  >
  > 两条自洽的路：套用同一套 15s 边际（上限 = 45s，即关掉协商），或显式
  > 承认更紧的窗口并给理由。**本步选前者**：协商的全部价值是「跑得慢的
  > 测试套件别被腰斩」，而在 60s 的引擎预算下，45s 和 55s 都装不下一个
  > 真实的测试套件——协商在这里买不到它该买的东西，却要付一个魔数的账。
  >
  > **`timeout_secs` 参数仍然保留在 schema 里**（钳制到 45s），因为它让
  > 模型可以要求**更短**的超时（快速探测场景真的有用），而且等引擎预算
  > 将来可配时，放开上限只需改一个常量。schema 描述必须如实说明当前上限。
- 超时横幅照搬（这是行为，且在 Python 下成立）。

> **这条是整个计划里最该被审核方挑战的一条。** 更干净的做法是让引擎的
> 预算可配、或让工具能声明自己需要更长预算——但那要动 `omicsclaw/engine/`，
> 超出本步范围（同 R3）。当前方案是在约束下的妥协，**它的代价是两个数字
> 之间有一条没有任何测试能强制的隐式耦合**。§8 陷阱 6 为此写了一条测试。

> ### 🔴 那 15 秒余量不是给工具的，是**人类审批的全部预算**
>
> Task C 交付时指出，协调者复核确认。`require_approval` 是在 `execute`
> **内部** await 的，而 `execute` 整个被 `EngineConfig.tool_timeout`
> 包住。所以对一个 `ASK` 工具，真正成立的约束是：
>
> ```
> 人类思考的时间  +  命令运行的时间  ≤  60 秒
> ```
>
> 而本工具只控制第二项。默认 45s 命令预算 → **留给人的只有 15 秒**。
> **任何超过 15 秒的审批都会让 Q4 整个失效**：引擎先取消，模型读到
> `tool 'bash' timed out after 60s`，而命令其实远在它自己的 45 秒之内。
> 15 秒不足以让一个人读完一条他正在批准的 shell 命令。
>
> **这把 R3 从「一个排序建议」升级成了结构性前提**：R3 不只是「排在接线
> 之前」，它是让陷阱 6 的保证对 `ASK` 工具**根本能成立**的那个东西。
> 在 R3 修好之前，`bash` 的审批闸门与它的超时预算是互相拆台的。

### Q5 —— 子进程输出用**临时文件**承接，不用 PIPE

harness9 `bash.go:153-165` 有一整段注释记录这个坑，且带实测数字：

> 不用 `CombinedOutput()`：其内部经 pipe + 拷贝 goroutine 承接输出，
> `Wait()` 会等待所有 fd 持有者关闭——当 cmd 是 `"A && B &"` 这类复合后台
> 任务，bash 为整个 `&&` 链 fork 的子 shell 继承了该 pipe 的写端，只要后台
> 进程还活着就**永久阻塞**，直到外层超时才被打断。改用临时文件：
> **返回时间从挂起 20s 降到 ~5ms，且后台进程验证仍在运行。**

**Python 有完全相同的问题**：`asyncio.create_subprocess_shell(...,
stdout=PIPE)` + `await proc.communicate()` 同样等 pipe 的所有写端关闭，
后台化的孙进程继承 fd 后一样会挂住。

**这是必须照搬的行为，而且必须有一条真的起后台进程的测试**，否则它会在
某次「简化」里被换回 `PIPE` 而所有测试仍然绿。

> 连带的代价也要照搬：**本调用返回后临时文件即被删除**，所以被后台化的
> 命令应自行重定向输出（`nohup cmd > file 2>&1 &`），不要依赖继承来的
> stdout。这句话要写进工具的 description，模型看得到。

### Q6 —— 非零退出是 `is_error=False`

计划 0028 §11 债 #16：harness9 刻意区分「**工具失败**」与「**世界失败**」——
命令非零退出（`bash.go:145-147`）、HTTP 404、搜索无结果，全部
`err == nil` 即 `IsError=false`；只有 harness 层面的问题（参数解析失败、
文件打不开）才产生 `err`。

**本步是这条约定第一次真正有用武之地**，因为 `bash` 是它最典型的场景：
「`pytest` 告诉我 3 个测试失败了」是**世界的事实**，不是工具坏了。若标成
`is_error=True`，模型会去修工具而不是修测试。

**裁决**：写进 `bash` 的 docstring，并用测试钉住：非零退出 →
`is_error is False`，输出里含退出码与合并输出。

同理 `read` 读一个不存在的文件：这是**世界的事实**（文件不在），应当是
可修正的 `is_error=True`（模型要改路径）——**注意这两条不矛盾**：判据是
「模型下一步该改什么」，不是「有没有出错」。这条判据要写进 §8 陷阱 7。

### Q7 —— 路径级锁：**asyncio 锁，不是 threading 锁**

harness9 `path_locker.go` 是 `sync.RWMutex` + 引用计数，ref 归零即从全局
map 删除防泄漏。

**为什么本项目现在必须有它**：计划 0028 §11 债 #1 查实——
`ToolPolicy.concurrency_safe` **零消费者**，而 `engine/executor.py` 对每个
调用无条件 `ensure_future`，`max_concurrent_tools` 默认 **0 即无上限**。
所以同一轮里两个 `write` 到同一路径**会真的并发**。旧层靠
`orchestration.py:707-726` 的串行屏障防这个，新层两道防线都没有。

**必须是 `asyncio` 原语**：引擎的并发是事件循环上的 Task，不是线程。
`threading.Lock` 在这里要么无效（不会真的阻塞协程）要么死锁。

引用计数归零即删除这条**照搬**（防 map 无限膨胀）。

> ⚠️ 一条 harness9 没有、本项目需要的：**锁的 key 必须是 `resolve()` 之后
> 的绝对路径**。两个不同的输入路径（`./a.txt` 与 `<workspace>/a.txt`）指向
> 同一个文件，若按原始字符串加锁就是两把锁，锁了等于没锁。

### Q8 —— 敏感路径硬拒绝，清单按本项目重写

harness9 `safe_path.go:25-39` 硬拒 `~/.ssh`、`~/.aws`、`~/.kube`、
`~/.gnupg`、`~/.netrc`、`~/.config/gcloud`，不受 workDir 白名单影响。

**照搬这个机制，但清单要按本项目重新审**。本项目是 omics 工具，
`.env`（`LLM_API_KEY`、`TELEGRAM_BOT_TOKEN`、`FEISHU_APP_SECRET` 都在里面，
见 CLAUDE.md）比 `~/.kube` 相关得多。建议清单：harness9 那 6 项 +
项目根的 `.env*` + `~/.config/gh`。

> 注意 harness9 这个清单的兜底说明（`safe_path.go:27-29`）：拿不到 home
> 目录时返回空列表，靠 bash 的 DangerHook 当备份防线。**本项目没有
> DangerHook**，所以拿不到 home 时应当**更保守**而不是更宽松。

### Q9 —— `read` 的行号前缀：现在就为 `edit` 预埋陷阱

harness9 `read_file.go:64-67` 的工具描述里有一句醒目警告：

> ⚠️ 行号前缀仅供显示，调用 `edit_file` 时 `source_text` 必须是**不含行号
> 前缀**的原始代码。

`read_file.go:215-218` 还在代码注释里重复了一遍。这不是啰嗦——这是一个
**跨工具的契约**，而两个工具由不同的步骤交付。

**本步必须把这条写进 `read` 的 description**，即使 `edit` 还不存在。理由：
下一步写 `edit` 的人不一定读得到本计划，但一定会读 `read` 的 description。

同时**预留接缝**：`read` 输出的行号格式（harness9 是 `%6d\t%s\n`）要写进
docstring 并用测试钉住，因为 `edit` 的容错逻辑要能识别并剥掉它。

### Q11 —— 沙箱：照搬 harness9 的**注入接缝**，不在工具层重写 bwrap

本步**不做**隔离实现，但必须留出 harness9 的那个接缝——**而且要按
harness9 的宽度留，不是只留给 bash**。

harness9 的 `sandbox.Environment`（`internal/sandbox/environment.go`，22 行）
是**五个方法**：`RunBash` / `ReadFile` / `WriteFile` / `ID` / `Close`，
`read_file.go`、`write_file.go`、`edit_file.go`、`bash.go` **四个工具全都
持有它**（各自的 `WithEnvironment` 选项）。

> **这个宽度是要点，不是啰嗦。** 如果只有 `bash` 走隔离，而 `write` 直接
> 写宿主文件系统，那个隔离就是摆设——模型想逃逸只需改用 `write`。
> 「隔离」必须包住**所有触达操作系统的工具**，否则它不是边界，是装饰。

所以本步在工具层定义：

```python
@runtime_checkable
class Environment(Protocol):
    """Where a tool's syscalls actually land. Injected, never imported."""
    async def run_bash(self, command: str, cwd: str, timeout: float) -> CommandOutcome: ...
    async def read_file(self, path: str) -> bytes: ...
    async def write_file(self, path: str, data: bytes) -> None: ...
```

三个工具都接受 `environment=None`，`None` 即本地执行（与 harness9 的
`env == nil` 同义，`bash.go:127-130`）。**工具层只定义 Protocol 与本地
实现**，隔离实现由**装配层注入**——结构化满足，工具层不 import 它，
分层白名单一个字都不用改。这与 `LLMProvider`、`ToolExecutor` 是同一种
接缝，本项目已经用对过两次。

> ⚠️ **参数必须是活的，不是存着不用的**（Task B 指出，判得对）。照抄
> harness9 就是「持有 `env` 但从不读」——`read_file.go:35-37` 与
> `write_file.go:28-30` 都只是 TODO 注释。那是**死状态**，正好是陷阱 15
> 要求评估方当缺陷报告的东西。**注入 environment 后必须真的走它**，并各
> 配一个 fake 的测试，外加一条「注入后 workspace 边界依然先生效」。

> ⚠️ **Protocol 按能力切分，不是一个大而全的 `Environment`**（Task B 的
> 处置，接受）。`FileReadEnvironment` / `FileWriteEnvironment` /
> `BashEnvironment` 各自只声明自己要的方法。理由：Protocol 是结构化的，
> 一个满足 harness9 五方法形状的对象**同时满足这三个**，注入点的宽度
> 一点没少；而 `read` 的测试替身不必去 stub 一个 shell。
>
> 另记一条参照系的缺口：**harness9 的 `sandbox.Environment` 没有
> `mkdir`**，所以一旦真的路由，`write` 描述里「自动建父目录」这个承诺
> 没人能兑现。本步把「实现方必须自己建父目录」写成了 Protocol 契约。

> ⚠️ **不要照抄 harness9 的 `LocalEnvironment`。** 已核实：
> `NewLocalEnvironment()` 在 harness9 里**没有任何生产调用方**（只有测试
> 用），而它的 `RunBash` 用的是 `c.CombinedOutput()`
> （`local_environment.go:28`）——**正是 `BashTool.runLocal` 花了一大段
> 注释去避免的那个 pipe 阻塞 bug**（Q5）。它在 harness9 里是死代码所以
> 无害；照着接上去，就等于把修好的东西又装回去了。**本地实现必须走 Q5
> 的临时文件路径。**

本步交付后 `bash` 仍然没有 OS 隔离——它的唯一边界是 Q2 的审批闸门。
这一点必须写进 docstring 和 §12。隔离本身是**一个独立的步骤**，见 §12。

### Q10 —— 符号链接：Python 的默认行为比 harness9 更严，这是**净增强**

harness9 `safePath` 用 `filepath.Abs` + 前缀比较，**不解析符号链接**。
所以 workDir 内一个指向外部的软链能通过校验。

Python 的 `Path.resolve()` **默认解析符号链接**。所以一个朴素的 Python 版
在这一点上强于参照系。

**裁决：用 `resolve()`，并把「我们比 harness9 严」写进 docstring**，免得
日后有人「对齐参照系」把它改回去。

⚠️ 但要注意 `resolve()` 在 Python 3.6+ 对**不存在的路径**不抛异常
（`strict=False` 是默认）——`write` 的目标文件常常不存在，这正是需要的
行为；而**父目录**若是恶意软链则必须在建目录前就被挡住。见 §8 陷阱 3。

---

## 5. 与第 4 步交付物的关系

| 第 4 步的东西 | 本步怎么用 |
|---|---|
| `Tool` Protocol | `bash` / `read` / `write` 都**手写类**，不用 `FunctionTool` |
| `FunctionTool` | 不用。理由：计划 0028 §11 记明——`FunctionTool` 拿不到**原始 payload**，而这三个都是 `ASK` 工具，审批提示必须对模型发出的字节忠实。这正是 §11「50 个里有 5 个必须手写」那条规则的第一批新增成员 |
| `ToolPolicy` | 三个工具各自**显式**声明，见 Q2（`bash`/`write`）与 Q2b（`read`）。**不得省略 `policy=`**——省略即 `ToolPolicy()` 即 `HIGH`+`ASK` |
| `require_approval` | `bash`/`write` 在**做任何事之前**调用，且把**原始 payload** 交给审批提示 |
| `report_progress` | `bash` 长命令用它。注意第 4 步修复后它对坏掉的 sink 也不 fail |
| `context_value` | 取 workspace。键名用模块常量，不要裸字符串（计划 0028 的实测教训：拼错的症状是一个伪装成部署错误的 `None`） |
| `decode_arguments` | 第 4 步修复时已转正为公开，**必须复用**，不要再写第四份（0028 的 R8 就是这个） |
| 分层守卫 | 本步文件一落地自动受检（`rglob`），且**含动态 import 与行为探针**（0028 的 R2 修复） |

---

## 6. 现有能力的去向

本项目 `runtime/tools/builders/engineering.py` 已有 14 个通用编码工具。
本步的三个是它们的继任者，**但本步不迁移**。下表是给迁移任务的对照，
**每一行都要交代，留空视为缺陷**（同计划 0028 §5 的纪律）：

| 既有能力 | 出处 | 本步处置 |
|---|---|---|
| `file_read` 的 `_validate_file_read_input` | `engineering.py:44` | → `read` 内部；**须对拍**，差异写进 docstring |
| `file_read` 的行号前缀 `f"{index}: {line}"` | `engineering.py` | ⚠️ **格式与 harness9 的 `%6d\t%s` 不同**。本步用哪个？建议 harness9 的（Tab 分隔更易被 `edit` 剥离），但**迁移时所有依赖旧格式的东西会变**——必须在迁移任务里点名 |
| `file_write` | `engineering.py:772` | → `write` |
| `file_edit` 的单级精确匹配 | `engineering.py` | ⏸ 下一步的 `edit`。注意本项目现状**只有 L1**，harness9 有 L1–L4 |
| `glob_files` / `grep_files` | `engineering.py` | ❌ 本步不做。harness9 没有对应物（它靠 bash）。**迁移时要决定：保留它们，还是让 bash 取代**——这是一个未决问题，不是遗漏 |
| `web_fetch` / `web_search` | `engineering.py` | ❌ 本步不碰，见 §2。**它们的 SSRF 缺口依旧敞着**（计划 0028 §11 债 #3） |
| `todo_write` | `engineering.py:411` | → Q2 的 `plan`（若保留）。**须与 harness9 的防作弊校验对照** |
| `ask_user` | `engineering.py:521` | ❌ 不做。计划 0028 §11 记明 Q4 的三条通道里**没有「问用户一个不是审批的问题」的位置**，`ask_user` 要么需要第四条通道，要么继续走带内协议。**这是第 5 步的事** |
| `task_create/get/list/update` | `engineering.py` | ❌ 不做。它们依赖会话级任务存储（第 6 步） |
| `tool_search` | `engineering.py:101` | ❌ 不做。它依赖「工具全集可检索」，而工具全集的裁剪刚刚被 owner 判为不需要（第 5 步的入口层会重新定义这件事） |

---

## 7. 任务切分

四个任务，顺序 **A → B → C → D**，全部串行。

- **Task A —— 助手层。** ✅ **已交付**（`_workspace.py` 360 行 +
  `_pathlock.py` 348 行 + 50 条测试；`tests/tools/` 373 passed，四目录
  1008 passed，纯 additive）。覆盖陷阱 1–4、8–9。
  > 原稿写「覆盖陷阱 1–4、8–10」是错的：**陷阱 10 是「`read` 的行号前缀
  > 格式被钉住」，与助手层毫无关系，归 Task B**（Task A 指出）。
- **Task B —— `read` + `write`。** 依赖 A。覆盖陷阱 5、7、11、12。
- **Task C —— `bash`。** 依赖 A。**不依赖 B**，但仍串行——计划 0027 附录 B
  和 0028 §6 都记了「声称并行实则有依赖」的翻车，不值得为省一点时间再赌
  一次。覆盖陷阱 5、6、7、13、14。
- **Task D —— 两个只读独立评估并行**：正确性 + harness9 对照与能力保全。

（原稿的 Task B2 `plan` 工具已取消，见 §2。）

每个实现任务动手前必须读：`omicsclaw/tools/base.py`、`registry.py`、
`context.py`、`function_tool.py`（`decode_arguments`）、
`docs/plans/0028-tool-registry.md` 的 §11 债表与附录 B，以及对应的
harness9 源文件。

---

## 8. 陷阱

每一条都是必备回归测试，且**每条经变异验证**。

1. **`"/project-evil"` 不是 `"/project"` 的子路径。** 前缀比较必须带路径
   分隔符（harness9 `safe_path.go:90-92` 专门注释了这条）。变异：去掉
   分隔符，点名测试必须变红。
2. **绝对路径输入绝不再与 workDir 拼接。** harness9 为此开了独立分支
   （`safe_path.go:72-87`），因为 `filepath.Join(workDir, "/abs")` 会产出
   `/workDir/abs` 这种翻倍路径——「通过了前缀校验却指向不存在的文件」。
   Python 的 `Path(workdir) / "/abs"` 行为**不同**（会直接变成 `/abs`），
   所以这条**不能直译，要在 Python 语义下重新判**：`/etc/passwd` 必须被
   拒，`<workspace>/sub` 必须通过。

   > ⚠️ **本条与陷阱 15 原先互相冲突，Task A 指出后在此收口。**
   > 陷阱 15 禁止「Python 下不可达的死代码」，而在 Python 里那个独立分支的
   > **两条臂计算结果完全相同**——写出来正好是陷阱 15 的靶子。
   >
   > **裁定：不写那个分支。** 只保留**行为**（绝对路径永不被拼到根上），
   > 用测试钉死，并用「Go 式 join」的变异验证测试会变红。
   > **Task B、C 同样不许写那个分支**，否则评估方会（正确地）把它报成缺陷。
   > 已在 Task A 交付的 `_workspace.resolve()` 里按此实现。
3. **父目录是符号链接时，必须在 `mkdir` 之前就挡住。** `resolve()` 对
   不存在的叶子不抛，但中间的软链会被解析——测试要覆盖「workDir 内有个
   软链指向 /tmp，写它下面的文件」。

   > ⚠️ **这条的真正风险在 Task B，不在 Task A**（Task A 指出，判得对）。
   > `Workspace.resolve()` 确实在解析阶段就挡住了软链父目录（Task A 已有
   > 测试），但**助手层无法强制 B 在 `mkdir(parents=True)` 之前调用它**。
   > **Task B 必须有一条经 `write` 工具本身的等价测试**——断言那个软链
   > 指向的外部目录下**没有**文件被创建出来，而不只是断言工具返回了错误。
4. **锁的 key 是 `resolve()` 后的路径**，不是模型给的字符串。变异：改回
   用原始字符串，「两个别名并发写同一文件」的测试必须变红。
5. **`CancelledError` 必须穿透。** 第 2、3、4 步都写过这条，本步是第四次，
   而且 `bash` 是最容易写错的：包住 `await proc.communicate()` 的
   `except` 必须是 `Exception` 不是 `BaseException`，否则引擎的超时取消会
   变成一条给模型看的 Observation。
6. **bash 的超时预算必须小于引擎的 `tool_timeout`。** 见 Q4。**要两条
   测试，不是一条**：

   (a) **机制**：用一个短 `tool_timeout` 走 `execute_tool_calls` 真实路径，
   确认拿到的是**工具的横幅**而不是引擎的 `"tool 'bash' timed out"`。

   (b) **默认值耦合**——一条纯数值断言，**两边都不传覆盖参数**：
   ```python
   assert BashTool(ws).timeout + _ENGINE_MARGIN <= EngineConfig().tool_timeout
   assert BashTool(ws).max_timeout <= EngineConfig().tool_timeout
   ```

   > ⚠️ **原稿只写了 (a)，而 (a) 守不住它自称要守的东西**（独立审核指出，
   > 判得对）。(a) 只要求挑一对「工具超时 < 引擎超时」的数字去验证机制能
   > 工作，实现者自然会给测试挑便利的自定义值——于是哪天有人把
   > `EngineConfig.tool_timeout` 默认值改成 30s 而没同步改 `bash.py`，
   > (a) 仍然全绿。这正是计划 0028 附录 B 教训 1「**有测试不等于接线了**」
   > 的同一种失败形态，在同一份计划里又出现了一次。
   >
   > 注意 (b) 的测试文件要 import `EngineConfig`——**测试目录不受分层
   > 约束**（守卫只扫 `omicsclaw/tools/`），这是合规的；而 `bash.py`
   > 生产代码仍然不得 import 它。
7. **「世界失败」不是 `is_error`。** `bash` 非零退出 → `is_error is False`；
   `read` 文件不存在 → `is_error is True`。判据是**模型下一步该改什么**。

   > ⚠️ **原稿要求「两条都要测，且在同一个测试文件里相邻」——在当前切分下
   > 不可能满足**（Task B 指出）：`read` 那半归 Task B，`bash` 那半归
   > Task C，两个任务的交付清单互相禁止碰对方的测试文件。
   >
   > **改为**：每个任务在**自己的**测试文件里放一对**同判据的相邻用例**，
   > 并在 docstring 里指向另一半。Task B 已用「文件不存在 → `is_error=True`
   > / 空文件 → `is_error=False`」承载；**Task C 用「非零退出 →
   > `is_error=False` / 参数解析失败 → `is_error=True`」承载**。
   > 判据的原文必须写进两边的 docstring，否则它只是两条孤立的断言。
8. **敏感路径检查在 `resolve()` **之后**。** 否则 `<workspace>/link-to-ssh`
   绕过。
9. **拿不到 home 目录时更保守，不是更宽松。** 见 Q8。
10. **`read` 的行号前缀格式被测试钉住**，因为 `edit` 要剥它。见 Q9。
11. **`read` 超长行降级要有明确提示**，不是一个通用错误
    （harness9 `read_file.go:222-225`：>512KB 单行时提示改用字节模式）。
12. **`write` 的覆盖语义要在 description 里说明白**（harness9
    `write_file.go:8-9`：与 `os.WriteFile` 一致，已存在直接覆盖，模型需
    自行判断是否先 read）。这条影响审批提示该给人看什么。
13. **子进程不得用 PIPE。** 见 Q5。测试必须**真的起一个后台进程**
    （`sleep 30 &`），断言工具在毫秒级返回而不是挂到超时。
14. **截断保尾。** 变异：改成只保头，「输出末尾的 FAILED 汇总仍然可见」
    的测试必须变红。
15. **UTF-8 边界回退不要直译。** 见 Q3。若实现里出现了「去掉半个字符」
    的循环，那是一段 Python 下不可达的死代码——**审核方应当把它当缺陷
    报告**。

16. **被信号杀死的进程不得被当成成功返回。** 这条不来自 harness9，来自
    pi 的一个**已归档的真实 bug**（附录 A）：它的 bash 工具判的是
    `exitCode !== 0 && exitCode !== null`，而信号终止时退出码是 `null`，
    于是 SIGKILL/SIGTERM 杀掉的命令**绕过失败判断、带着残缺输出被当成
    成功**，调用方无从区分。

    Python 的 `asyncio.subprocess` 对信号终止返回**负的** `returncode`
    （`-SIGKILL` 即 `-9`），所以直译 pi 的判据同样会错。**照 shell 惯例
    归一化为 `128 + signum`**（pi 现版正是这么修的），并用测试钉住：
    起一个进程、`kill -9` 它，断言结果不是「成功」。

---

## 9. Task D —— 独立评估

两个**只读**子 agent 并行，均未参与编码，且**不被告知彼此或协调者已知的
问题**（第 4 步靠这条拿到了三方独立收敛）。

**D1 —— 正确性与车道纪律。** 15 条陷阱逐条**变异**验证。专门瞄准三条
车道边界：A↔B、A↔C、新层↔第 3 步引擎（尤其超时归属）。
⚠️ 变异驱动必须用 `-rfE --continue-on-collection-errors`。

**D2 —— harness9 对照 + 能力保全。**
(a) 逐条对照 `bash.go`/`read_file.go`/`write_file.go`/`safe_path.go`/
`path_locker.go`，**特别注意「照搬了在 Python 下不成立的东西」和「该照搬
行为却没照搬」两个方向**；
(b) 逐行核 §6 的能力表，并**自己去读 `builders/engineering.py`**，找表里
根本没提到的字段或行为。

> **给 D2 的特别指示**：§2 与 §6 的表都是协调者写的，盲区即计划的盲区。
> 另外请核实 §0 的可核实性声明——**有没有哪条设计只靠「未核实」的来源
> 支撑？**

---

## 10. 验收标准

1. `tests/tools/` 在无网络、无厂商 SDK、无 MCP SDK 下通过。
2. 第 1–4 步的 **950 条原有用例全部仍然通过，且一个字都没改动**。

   > ⚠️ **原稿写的是「总数逐字不变」，那在本项目不可能成立**（Task A
   > 指出）：分层守卫 `test_tools_is_a_leaf_layer.py` 用 `rglob` 参数化，
   > **每落一个新模块就自动多 4 条用例**。Task A 交付后是 950 → 1008
   > （+50 自写 +8 自动）。判据是**原有用例不被触碰**，不是总数不变。
3. `git status --porcelain` 只许出现 `??`；一个 ` M ` 就是越界。
4. `omicsclaw/tools/` 在 `omicsclaw` 内**只**导入 `omicsclaw.schema`
   （含动态 import 与行为探针，即第 4 步 R2 修复后的那一版守卫）。
5. §8 的 16 条陷阱每条有点名测试且经变异验证。
6. §6 的能力表每行都有交代，没有留空。
7. `awk 'length > 88'` 对新文件无输出。
8. **每一条从 harness9 搬来的字面量，都要在报告里声明「已在 Python 下
   重验」**，包括 16000、45s、512KB、0755/0644、头 1/3 尾 2/3。
9. **`_workspace.py` 的沙箱边界经对抗性测试**（即 `read` / `write` 的
   边界）：路径遍历、软链逃逸、敏感路径、绝对路径注入，每类至少两例，
   且每类都要配一条**正向**用例（合法路径必须通过）——只断言「恶意路径被
   拒」的测试，在一个「拒绝一切」的实现下也照样绿。

   > ⚠️ **本条原先把靶子写成 `bash`，那是错的**（独立审核指出）。
   > harness9 的 `bash.go:88-107` 参数只有 `command` / `timeout_secs`，
   > **没有路径参数**，`Execute` 从不调用 `safePath`；本计划也没有给
   > `bash` 设计任何路径校验。按本设计，**`bash` 除审批闸门外没有路径
   > 攻击面可测**——`cd ../.. && cat x` 在没有 OS 隔离的前提下不是「边界
   > 被绕过」，而是「本来就没有边界」（见 Q11）。照原措辞，实现者要么
   > 静默跳过这条验收，要么被迫给 `bash` 发明一套本计划从未设计过的路径
   > 校验。**`bash` 的边界是 Q2 的审批 + Q11 的注入接缝，不是路径。**
10. 与 `services/path_validation.py` 的对拍结果写进 docstring（Q1）。

---

## 11. 验证

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest \
    tests/schema/ tests/provider/ tests/engine/ tests/tools/ \
    -p no:cacheprovider -q -o addopts=""
# 当前基线：950 passed
```

`pytest-asyncio` 未装（用 `asyncio.run`），`black` 装不了（用 `awk` 查行宽
并手工检查会被重排的构造），无网络、无厂商 SDK。

> ⚠️ **变异活动必须在 pytest 进程外再套一层 OS 级超时**，例如
> `timeout --signal=KILL 60 <pytest ...>`。Task A 踩到了这条：
> **`asyncio.wait_for` 这类进程内 deadline 救不了被阻塞的事件循环**——
> 循环被卡住时定时器回调根本不会触发，进程**永久挂起**，于是变异驱动的
> `finally` 还原逻辑不会执行，**文件会留在被变异的状态**。
>
> 这条对 **Task C（bash，会 fork 子进程）风险更高**：一个失控的子进程能
> 把整个变异跑挂死。OS 级 `timeout` 是唯一能兜住它的东西。

---

## 12. 后续步骤继承什么

- **`edit`（下一步）**：四级降级 L1 精确 → L2 换行归一 → L3 整体去空 →
  L4 逐行去缩进（harness9 `edit_file.go:136-139, 238-252`），外加
  `buildEditSummary` 的 3 行上下文 diff，且**区分精确匹配与模糊匹配**
  （`edit_file.go:128-131`：L2–L4 写入的字节可能与模型预期不同，尤其
  Python 缩进敏感，须提示复核）。本项目现状只有 L1。
  ⚠️ 依赖本步的 `_workspace.py`、`_pathlock.py`，以及 Q9 的行号前缀契约。
- **容器化 / 沙箱**：harness9 的 `sandbox.Environment` 让 bash 走
  `docker exec`。本项目没有任何对应物。**在有它之前，`bash` 的唯一边界是
  审批**——这是 Q2 选 `ASK` 的根本原因，要一起结转。
- **SSRF（计划 0028 §11 债 #3）**：本步不碰 web 工具，所以不新增这个洞，
  **也没有修**。`runtime/tools/builders/engineering.py:1061-1067` 的
  `web_fetch` 仍然只检查 URL 前缀，`169.254.169.254` 仍然可达。
- **R3（审批等待被计进 `tool_timeout`）**：owner 已裁定排在任何 Surface
  绑定审批通道之前。**本步会让它从「零暴露」变成「一接线就中」。**
- **引擎侧的超时预算**：Q4 的 45s 是从引擎的 60s 默认值倒推的魔数。
  正确的长期形态是让工具能声明自己需要的预算，或让引擎的预算可配——
  两者都要动 `omicsclaw/engine/`。
- **`glob_files` / `grep_files` 的去留**（§6）：保留，还是让 `bash` 取代？
  未决。
- **`ask_user` 需要第四条带外通道**（§6），第 5 步的入口层要决定。
- **`plan_write` 的防作弊校验**（§2）：harness9 那条「一次调用最多 1 个
  条目从 pending 直跳 completed」是本项目 `todo_write` 没有的新增能力
  （已核实 `engineering.py:1004-1059` 每次直接整表重建）。**第 6 步会话层
  落地后做**，一次做对。
- **OS 隔离层（建议列为重建的一个独立步骤，`omicsclaw/sandbox/`）。**
  本步只留 Q11 的 `Environment` 接缝。**不要复用 `omicsclaw/autonomous/`
  下那套 bwrap 设施**——owner 已明确那是旧架构、正在整体推倒重来。
  设计建议与取舍见下方「附录 B」。

## 附录 A —— 三方对照（旁证，非依据）

owner 已裁定按 harness9 做。本表的用途是**证明那些参数是刻意取舍**：
三个工业级实现几乎每一项都不一致，所以照抄任何一家的数字都不安全。

| 维度 | harness9（本步照做） | pi | codex |
|---|---|---|---|
| 默认工具集 | bash/read/write/edit + web×3 + memory×2 + plan | **恰好 read/write/edit/bash**（7 个内置只默认开 4 个，系统提示+工具定义 <1,000 token） | shell + `apply_patch` |
| bash 超时 | 默认 120s、上限 600s、`timeout_secs` 可协商 | **无默认**，模型自己填（`MAX_TIMEOUT_MS=2_147_483_647`） | — |
| bash 输出上限 | 16,000 字符，**头 1/3 + 尾 2/3** | `DEFAULT_MAX_LINES=2000` **或** `DEFAULT_MAX_BYTES=50KB`，**只保尾**，完整输出落临时文件并回传 `fullOutputPath` | — |
| 后台进程不阻塞 | **临时文件**承接，不用 pipe | **用 pipe**，但 `detached` 进程组 + `killProcessTree` | — |
| read 分页 | 字节模式 + 行号模式（500 行/8192 字节） | 仅行模式（`offset`/`limit`，1-indexed） | — |
| edit 匹配 | **四级模糊降级 L1–L4** + 区分精确/模糊并提示复核缩进 | **仅精确**，但一次多处不重叠编辑；先剥 BOM、统一 LF；**每处对照原始文件而非增量** | `apply_patch` 差分格式，经 arg0 技巧分发而非当 shell 命令 |
| OS 隔离 | 可选 docker（`env=nil` 走本地） | **完全没有**，官方要求用户自己容器化 | **OS 级**：Seatbelt / Bubblewrap+Landlock+seccomp；**只沙箱自己发出的工具调用，主进程不沙箱** |
| 审批 | 无 | 无 | **两轴**：沙箱模式（`read-only`/`workspace-write`/`danger-full-access`）× 审批策略（`on-request`/`never`） |

**三条对本项目直接有用的旁证**：

1. **codex 的两轴模型说明「边界」与「何时停下」是两件事。** OmicsClaw
   目前只有审批这一轴（第 4 步交付），隔离那一轴有设施但没接到工具上
   （Q11）。pi 两轴都没有并直说「自己去容器化」。**所以 Q2 选 `ASK` 不是
   保守，是在只有一轴可用时用满那一轴。**
2. **pi 的「无默认超时」被它自己记为问题**：模型不可能知道某个仓库的测试
   套件要跑多久，只能瞎猜；且 pi 的 agent loop 根本没有工具执行超时，
   挂住的调用会一直挂。**OmicsClaw 有 60s 引擎预算反而是优势**——代价就是
   Q4 那条隐式耦合。
3. **pi 的两个已知 bug 是免费的教训**：① signal 杀死的进程因 `exitCode`
   为 `null` 绕过失败判断、被当成成功返回（本步 §8 陷阱 16 据此新增）；
   ② no-op 编辑报错、破坏幂等性（留给 `edit` 那一步）。

**一条本项目该留意、但本步不做的**：pi 的 `read` 支持图片
（jpg/png/gif/webp/bmp）作为附件回传。对一个组学项目格外相关——CLAUDE.md
里发到 Channel 的照片要走组织切片分析（H&E、荧光）。但第 1 步的 `schema`
**刻意排除了多模态内容块**（ADR 0077），所以这是一条真实缺口，归 schema
层，不归本步。

来源：[openai/codex](https://github.com/openai/codex) ·
[Codex sandboxing](https://learn.chatgpt.com/docs/sandboxing) ·
[earendil-works/pi](https://github.com/earendil-works/pi) ·
`packages/coding-agent/src/core/tools/{bash,read,edit,truncate}.ts`

## 附录 B —— 该不该把 harness9 的 sandbox 搬进来（owner 提问，2026-09-18）

**结论：抽象现在就搬（几乎免费，且不搬会导致返工），容器实现单列一步，
而且实现时有四处必须按本项目重新标定——照抄参数会当场坏掉。**

### B.1 harness9 那套设计是什么（`internal/sandbox/`，1,793 行含测试）

| 件 | 内容 |
|---|---|
| `Environment` 接口（22 行） | `RunBash` / `ReadFile` / `WriteFile` / `ID` / `Close`。**关键设计：沙箱不是工具去调用的东西，是工具运行于其中的东西**——四个工具各自持有它 |
| 两个实现 | `LocalEnvironment`（无隔离）与 `DockerEnvironment`，由配置 `Enabled` 切换 |
| `Manager`（264 行） | 生命周期：每 agent 一个容器、`CreateWithRetry`（Docker 冷启动重试）、`Destroy`/`DestroyAll`、**`ReapOrphans`**（进程被 SIGKILL 后残留容器的清理，按 `label=harness9=1`） |
| 容器加固 | `--cap-drop all` + 仅 `DAC_OVERRIDE`/`SETUID`/`SETGID`、`--security-opt no-new-privileges:true`、`--pids-limit`（防 fork bomb）、`--cpus`、`--memory`、`--tmpfs /tmp:nosuid,noexec,nodev` |
| 网络护栏 | `--add-host <host>:0.0.0.0` 让容器内 DNS 解析失败。**自陈是「行为护栏而非安全边界」**（硬编 IP + SNI 可绕过）——威胁模型写得很诚实，不吹 |
| `BootstrapCmd` + 独立 `BootstrapTimeout` | 容器就绪后跑一次的初始化（如 `pip install -e .`），**不受单条命令超时约束**。明写是接 SWE-bench 每实例镜像的接缝 |
| 降级 | 创建失败重试一次再降级到本地，理由写得很清楚：「失败即永久降级的代价远高于多等几秒」 |

### B.2 直接可搬的（结构，非字面量）

1. **`Environment` 抽象本身。** 22 行接口，本步 Q11 已经按它的宽度留好
   接缝了。**这是整套设计里性价比最高的一件**：现在留，成本接近零；
   不留，将来三个工具全要重写。
2. **两实现 + 配置切换 + 优雅降级。** 包括「重试一次再降级」那条判断。
3. **`ReapOrphans`。** 进程被强杀后容器残留，是**一定会发生**的事故，不是
   假想。按 label 清理 + 跳过自己持有的（防并发进程互杀）这套做法可以照抄。
4. **`BootstrapCmd` 与单条命令超时分开计预算。** 对 OmicsClaw 更要紧——
   装一个 scanpy 环境比装一个 SWE-bench 仓库慢得多。

### B.3 **必须按本项目重新标定的四处（照抄会坏）**

> 这正是第 3 步那条教训的又一次应用：**搬结构是资产，搬字面量是负债。**

1. **威胁模型不同，因而控制的重心不同。** harness9 隔离是为了**保护宿主
   不被 agent 弄坏**；本项目 CLAUDE.md 的规则是「**Genetic data never
   leaves this machine**」——威胁是**数据外流**。两者推出的控制不一样：
   对本项目，**网络隔离（`--network none`）是主控制**，`--cap-drop` 是次要的；
   而 harness9 只做了 DNS 黑洞，且自陈不是安全边界。**照抄它的网络策略，
   正好漏掉本项目唯一真正在乎的那条。**
2. **资源默认值是按 SWE-bench 标定的，本项目会当场 OOM。**
   `ubuntu:22.04` / `--cpus 1.0` / `--memory 512m`——一次
   `sc.pp.neighbors()` 就爆。本项目的镜像是带 CUDA 的 conda 环境（GB 级），
   还可能要 `--gpus`，**而 `--gpus` 与 `--cap-drop all` 有冲突需要单独验**。
3. **数据必须 bind mount 进去，所以文件系统边界不可能紧。** harness9 的
   工作区是一个小仓库；本项目要挂的是 h5ad / FASTQ / 参考基因组。
   **「隔离」在这里保护的不是数据不被读，而是数据不被送出去**——再次指向
   第 1 条。
4. **本机不一定有 docker。** harness9 有 daemon 探测 + 降级，这条必须
   照搬而不是假设。**且降级必须是响亮的**：静默退回本地执行，等于用户
   以为有隔离而其实没有。

### B.4 放在哪一层

新增一个顶层 `omicsclaw/sandbox/`，与 `schema/` / `provider/` /
`engine/` / `tools/` 平级——**和 harness9 把 `sandbox` 放在 `tools` 的同级
完全一致**。

⚠️ 但**依赖方向要反过来**。harness9 是 `tools` → import `sandbox`；本项目
**不能**这么做，那要放宽 `omicsclaw/tools/` 的分层白名单，而那条白名单是
旧层边界的唯一执行机制（计划 0028 Q7）。**正确做法**：工具层定义
`Environment` Protocol（Q11 已定），`omicsclaw/sandbox/` **结构化满足**它、
不被工具层 import，由装配层注入。这与 `LLMProvider`、`ToolExecutor` 是同
一种接缝，本项目已经用对过两次，**白名单一个字都不用改**。

### B.5 值不值得做——一条反对意见，和我的判断

**反对**：成本不小（含生命周期与孤儿回收约 800 行、外加 docker 依赖与
GPU/内存标定），而本项目**已经有审批闸门**（第 4 步）。如果每一条 `bash`
都要人点同意，隔离带来的增量安全有限。

**我的判断**：**沙箱与审批在低频时是替代品，在高频时是互补品。**
只要人还在逐条点同意，沙箱确实可有可无；**沙箱的价值恰恰出现在你想
停止逐条点同意的那一刻**——而那一刻是必然会到来的（自主分析流水线、
夜间批处理、Channel 上的多用户并发，都不可能逐条人工审批）。

所以建议的排序是：

1. **现在**：Q11 的 `Environment` 接缝（本步，几乎免费）。
2. **接着**：R3（审批等待被计进 `tool_timeout`）——owner 已定，必须在任何
   Surface 绑定审批通道之前。
3. **然后**：`omicsclaw/sandbox/` 作为重建的一个独立步骤。**它的验收标准
   应当是「能关掉审批」**——如果隔离做好了还是不敢让 `bash` 自动跑，那说明
   隔离没做到位，这是一条比任何测试计数都硬的判据。
