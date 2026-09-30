# 计划 0046 — `omicsclaw/subagent/`：子代理委派层

**状态**：**已实现**（2026-09-21）。两轮独立只读审核已完成并返工（§15），
owner 批准后按本文实现，交付结果与实现期发现见 §16。
验证：`tests/subagent/` 123 项 + `tests/entry/test_subagent_wiring.py` 34 项
全绿；重建后的整套栈 **4982 passed, 12 skipped**（2026-09-21 实测）。§13 的
三条变异测试逐条实测通过。

> 整套栈那个数字是**某一时刻的测量值**，不是本层的不变量：这棵树同时有
> 几个 session 在写，交付当天它就从 4746 走到了 4852 再到 4982，而本层只
> 贡献了其中的 157 项。引用它时看日期；要判断自己的改动，跑一次拿当下的
> 数再比。

**前置**：计划 0027 §12（引擎自持一次 exchange 的生命周期）已交付
（2026-09-21，1197 passed）。§12 在十处点名本层为它的第一个真实使用者，
本计划兑现那些承诺，并复核 §12 替本层预先判掉的三件事是否真的成立。

**参考实现**：harness9 `internal/subagent/`（8 个非测试文件约 1,000 行）、
`docs/核心功能/sub-agent.md`、`cmd/harness9/main.go:355-420`（接线段）。

---

## 1. 目标

主代理把一个**边界清晰的子任务**委派给拥有独立上下文、受限工具集与可选
模型覆盖的专门代理执行，只拿回一份自包含的结论。

```
主代理 LLM ──调用 task 工具──► 子代理（独立 context + 窄工具集）
                                      │
主代理上下文 ◄── 结论文本（tool result）─┘
```

子代理**不是新抽象**：它就是一个 `AgentEngine` 实例，跑一次
`exchange()`。这句话在 harness9 那里是设计口号，在本仓库是 §12 交付后的
字面事实——见 §3.3。

### 非目标（本轮不做，逐条注明在等谁）

- **后台异步委派（`background=true`）、`TaskTracker`、`/tasks` 面板、
  结果注入下一轮。** 推迟至 **0047**，理由见 §9——它需要在
  `SessionRegistry` 上开一条"把上轮遗留结果前置进本轮 prompt"的接缝，
  那是 entry 层手术，与本层的委派语义是两件事。
- **`@agent` 直跑。** 同样推迟至 0047：`0041` 已裁定它"依赖尚不存在的
  子代理层"，本层落地后它变成纯 CLI 工作，归 CLI 那条线。
- **子代理独立 Sandbox。** `0036` §表 #18 早已把接缝留好
  （`SandboxManager` 支持多沙箱 + `label`），但**调用方到了而需求没到**：
  本仓库今天的 bash 工具已在沙箱内，子代理共用同一个不构成越权。
  要"每个子代理一个容器"时再开，不在本层。
- **子代理递归委派。** 永久不做，见 §6。

---

## 2. 参考实现的形状，以及它在本仓库**不成立**的部分

harness9 的 `Runner.Run`（`runner.go:89-245`）做七件事。逐条对照本仓库
今天的状态：

| # | harness9 `Runner` 做的事 | 本仓库 | 本层要不要做 |
|---|---|---|---|
| 1 | `buildChildRegistry`：按 `ResolveTools` 筛工具、包 hook 链 | 无 | ✅ 要做（§4、§5） |
| 2 | `providerFor(def.Model)`：模型覆盖 + 查 context window | `LLMProvider.bind(**overrides)`（`provider/base.py:152`） | ✅ 要做，但一行 |
| 3 | `newPromptBuilder(...)`：拼 system prompt + workDir + skills 正文 | §12 的 `PromptSource` 接缝已在 | ✅ 要做（§3.4） |
| 4 | `memory.NewMemorySession(childID)`：给子代理一个纯内存 Session | **不需要**，见 §3.3 | ❌ 不做 |
| 4′ | `WithSandboxContext` / `WithSandboxDegraded`：把执行环境说明注入子 prompt（`prompt.go:73-93`） | `entry/sandbox.py` 的 `sandbox_section` 有三态 | ✅ **要做**，见 §3.5（初稿漏记，独立审核补入） |
| 5 | `engine.NewAgentEngine(...)` + 7 个 `Option` | §12 后是一次构造 + `exchange()` | ✅ 一次调用 |
| 6 | `execCtx` 从 `baseCtx` 派生，绕开 60s 工具超时 | `pause_tool_timeout()`（`tools/context.py:449`） | ✅ 要做，但换机制（§7.2） |
| 7 | 消费事件流：转发进度、桥接审批、累积最终文本 | 进度有 `ProgressSink`；审批已自动穿透 | ◐ 只做进度（§7.1、§8） |

**第 4 行是本轮最大的简化——但理由不是初稿写的那个。**

> **初稿在此写了一句假话，由独立审核纠正，记在这里而不是抹掉**：原文说
> 「harness9 的引擎必须绑一个 `Session` 才能跑」。**不成立。**
> `agent_loop.go:48` 逐字写着 `session memory.Session // 可选，nil 表示无
> 持久化`，`loop_phases.go:90` 是 `if e.session != nil` 的空值分支。
> harness9 的 `Runner` 给子代理造 `MemorySession`（`runner.go:141`）是
> **设计选择**，不是被迫。用一个不存在的约束去衬托本仓库"更简单"，是把
> 参考实现说得比实际更笨——这种论证即使结论对也必须改掉。

真实的差异小得多，但仍然是差异：harness9 选择给子代理一个丢弃式
`MemorySession`（很可能是为了让 compactor 写回和 observability 的
`SessionID()` 有落点，**未确证**）；本仓库 §12 之后
`exchange(user_text, conversation=None)` 根本不碰任何会话对象，所以**连
这个选择都不必做**。少一个对象、少一条生命周期、少一处可能泄漏父上下文
的路径。

**第 6 行换了机制但语义更强。** harness9 要从会话级 `baseCtx` 另派生一个
`execCtx`，并且前台还要起一个 goroutine 去分辨"真取消"与"60s 工具超时"
（`runner.go:157-178`，该文件最长的一段注释）。本仓库 `_paused`
（`engine/executor.py:389`）把 per-call deadline 摘掉再按剩余秒数装回去，
`task` 工具握住一个 pause 即可——**取消语义完全不用碰**，父 Task 被取消
时子代理随之取消，这正是想要的。

---

## 3. 决策

### 3.1 包的位置与依赖白名单：`schema` + `tools`，与 `planning` 同级

`omicsclaw/subagent/`，白名单 **`omicsclaw.schema` + `omicsclaw.tools`**
——和 `omicsclaw/planning/` 逐字相同。

**不依赖 `engine`**，这一条值得解释，因为直觉上子代理要造引擎：造引擎的是
**组装根**，不是本层。本层只描述"什么是一个子代理"和"怎么把任务交出去"，
交出去这个动作经一条本层自己声明的 `Delegate` Protocol 完成。

**不依赖 `skills`**：预加载 skill 正文经一个 `Callable[[str], str]` 注入，
这正是 harness9 `prompt.go:19` 的 `skillLoader` 做法。
**不依赖 `provider` / `permission` / `context` / `entry`**：同理。

| 层 | 职责 | 白名单 |
|---|---|---|
| `omicsclaw/subagent/` | 定义、注册表、文件式加载、工具解析、子 prompt、`task` 工具 | `schema` + `tools` |
| `omicsclaw/entry/subagent.py` | 造子引擎：窄化 registry、模型覆盖、skills loader、驱动 `exchange_stream`、透传进度 | entry 是顶层，可以 import 一切 |

这与 `planning`（叶子）+ `entry/planning.py`（接线）的既有切法完全一致，
也与 0039 §2.1 立下的理由一致。

### 3.2 `Delegate` —— 本层声明、entry 结构化满足

```python
# omicsclaw/subagent/delegate.py
@runtime_checkable
class Delegate(Protocol):
    async def delegate(self, definition: SubAgentDefinition, prompt: str) -> str:
        """跑完一次委派，返回子代理的结论文本。"""
```

签名里**没有引擎类型**，所以本层不必 import `engine`。这是 `PromptSource` /
`TurnAugmentor` / `ToolExecutor` 同一套惯用法的第四次使用。

### 3.3 子代理不需要 `Conversation`

`AgentEngine.exchange(text, conversation=None)` 时，`_opening` 不追加任何
历史、`_settle` 不调用任何 `commit`（`engine/loop.py` 的两个 helper 都是
`if conversation is not None` 守卫）。子代理**确实会传 `prompt=ChildPrompt`**，
所以发出去的是 `[system, user]` 而不是初稿写的 `[user]`——措辞已纠正，
结论不变：**没有会话对象，一轮跑完即弃**，输出是 `RunResult.final_message`。

**这同时是上下文隔离的实现方式，不是额外的一道措施**：子代理拿不到父
对话历史，不是因为我们过滤了什么，而是因为**没有任何一条路径能把它交过去**。

### 3.4 子代理的 `PromptSource`：本层构造，结构化满足 §12 的接缝

```python
# omicsclaw/subagent/prompt.py
@dataclass(frozen=True, slots=True)
class ChildPrompt:
    system_prompt_text: str
    workspace: str
    skills: tuple[str, ...] = ()
    loader: Callable[[str], str] | None = None

    def render(self) -> "ChildPrompt": ...      # 满足 PromptSource
    @property
    def system_prompt(self) -> str: ...         # 满足 RenderedPrompt
```

同一个对象既是 `PromptSource` 又是 `RenderedPrompt`，与
`tests/engine/test_conversation.py` 里的 `Prompt` 测试桩同形。**不 import
`engine`**——满足是结构上的。

组装顺序对齐 harness9 `prompt.go:52-71`：子代理 system prompt → 工作目录 →
预加载 skill 正文（加载失败静默跳过，不阻断委派）。

### 3.5 执行环境说明必须继承（初稿漏记，独立审核补入）

harness9 的 `promptBuilder` 有两个专门的方法把**执行环境**写进子代理
prompt（`prompt.go:73-93`）：`WithSandboxContext`（"你在一个隔离的 Docker
容器里，缺工具直接 apt-get 装"）与 `WithSandboxDegraded`（"Sandbox 启动
失败，你的一切操作直接落在宿主机上"）。后者**优先于**前者，理由写在
`runner.go:120-123`：降级时子代理运行在宿主机本地，给它容器说明会让它
误判隔离边界。

本仓库有等价物：`entry/sandbox.py` 的 `sandbox_section`，三态（运行中 /
降级 / 未启用），今天只进主代理 prompt。

**裁定：子代理的 `ChildPrompt` 必须带上同一段文本。** 子代理复用的就是父
代理那个 `bash` 工具对象（§6），它执行的位置与父完全相同；一个被告知
"你在容器里、随便装包"的子代理，在降级部署上会直接往用户宿主机装东西。

实现上由 `entry/subagent.py` 把 `sandbox_section` 的渲染结果作为一个
字符串传给 `ChildPrompt`——本层仍然不依赖 `entry` 或 `sandbox`，拿到的
只是一段文本。配套测试：降级部署下，子代理 prompt 里出现降级说明而**不**
出现容器说明。

**不注入规划准则**：harness9 的 `promptBuilder.Build()` 里硬编码了一段
「面对复杂多步任务时先用 `plan_write`」。本仓库该段由
`omicsclaw/planning/guidance.py` 的 `PLANNING_GUIDANCE` 持有，且本层不依赖
`planning`。子代理要不要规划，由 §5 的工具白名单决定——给了 `plan_write`
就给对应准则，这件事归 entry 拼装，不归本层写死。

---

## 4. `SubAgentDefinition`

```python
@dataclass(frozen=True, slots=True)
class SubAgentDefinition:
    name: str                              # ^[a-z0-9][a-z0-9-]*$
    description: str                       # 写给 LLM 的「何时用我」——调度依据
    system_prompt: str
    tools: tuple[str, ...] = ()            # 白名单；空 = 继承父全部
    disallowed_tools: tuple[str, ...] = ()
    model: str = ""                        # 空 = 继承父模型
    max_turns: int = 0                     # 0 = 继承引擎默认
    skills: tuple[str, ...] = ()
    source: str = ""                       # "builtin" 或文件路径，诊断用
```

`validate()` 与 harness9 `definition.go:33-48` 同：name 非空且合法、
description 非空、system_prompt 非空。

### `resolve_tools(all_names) -> tuple[str, ...]`

```
tools 非空 → tools ∩ all；tools 为空 → all
减去 disallowed_tools
永远减去 TASK_TOOL_NAME（无论是否在白名单里）
```

**保持 `all_names` 的原始顺序**，这一条是本仓库特有的、harness9 没有的
约束：工具表顺序是前缀缓存的一部分（0028 的裁定），按集合重排会让每个
子代理各自作废一份缓存前缀。harness9 的 `ResolveTools` 在白名单分支里按
`d.Tools` 的顺序输出，本层改为按 `all` 的顺序过滤。

---

## 5. `task` 工具

工具名 `task`（与 harness9 一致；本仓库工具名都是 snake_case，`task` 合规）。

`definition()` **动态生成**：`subagent_type` 的 `enum` 是注册表里全部名字，
description 把每个子代理的 `description` 拼进去——这是 LLM 选哪个子代理的
唯一依据（harness9 `task_tool.go:36-69`）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `subagent_type` | ✅ | 已注册子代理名，`enum` 动态枚举 |
| `prompt` | ✅ | 完整任务描述。**子代理看不到主对话历史**，文件路径、背景、要求都要写在这里 |
| `description` | ❌ | 3–5 词标题，UI 展示用 |

**没有 `background` 参数**（§9）。加参数是向后兼容的，删参数不是——0047
再加。

### `ToolPolicy`

```python
ToolPolicy(
    risk_level=RiskLevel.HIGH,        # 子代理能做父代理能做的一切
    approval_mode=ApprovalMode.AUTO,  # 见下
    concurrency_safe=False,           # 见下
    allowed_in_background=False,
)
```

**`approval_mode=AUTO` 需要理由**，因为 `ToolPolicy` 的默认是 `ASK` 且
0028 明确说"忘记声明的代价应该是多弹一次框"。理由：委派本身不是危险动作，
**危险的是子代理将要调用的工具，而那些工具各自的 gate 一个都没少**
（§6 第 2 条）。在委派处再弹一次，问的是一个人无法回答的问题——他不知道
子代理会去做什么。这条必须配一条点名测试：子代理调用 `bash` 时父审批框
照常弹出。

**`concurrency_safe=False`**：一次委派会跑很多轮、每轮又起自己的工具 Task。
让它成为 barrier（`EngineConfig.serialize_unsafe_tools` 默认真）是保守值，
且与 §7.2 的 pause 叠加时语义最清楚——一个握着 pause 的 barrier，独占。

---

## 6. 三条安全保障

| 保障 | 机制 | 失效时的后果 |
|---|---|---|
| **禁止递归** | `resolve_tools` 硬编码移除 `task`（唯一一道真闸）；`TaskTool.execute` 另对 `definition` 做一次自洽性断言，见下方更正 | 子代理委派子代理，指数展开 |
| **权限只能更严** | 子 registry 的工具**就是父 registry 里那几个同名对象**（已 gate、已 hook），只做筛选不做重建；**且策略必须显式带过去**，见 §6.1 | 子代理绕过父的 permission gate |
| **上下文隔离** | 子代理没有 `Conversation`（§3.3）；prompt 是唯一入口 | 父对话历史泄漏进子代理 |

> **初稿把禁止递归写成"两道闸"，交付后的第三轮独立审核证伪，原地纠正**
> （体例同 §2、§15.3）。原文是「`TaskTool.execute` 在**拿到窄化工具名
> 集合后**再断言一次」。**不成立，而且当初就不可实现。**
>
> `task_tool.py` 的 `_refuse_recursion` 拿的是
> `definition.resolve_tools((TASK_TOOL_NAME,))`——它**自己又算了一遍**，
> 看不到 `ChildRunner._child_registry` 真正建出来的那个 `ToolRegistry`。
> 审核的变异实测：把 `_child_registry` 改成直接遍历
> `self._parent.names()`、完全绕过 `resolve_tools`，子代理**拿到了
> `task`**，而 `_refuse_recursion` 一声不吭；抓住这次变异的是三条测试，
> 不是这道"闸"。
>
> **这是计划写得不可实现，不是实现偷工。** §3.1 的白名单只给本层
> `schema` + `tools`，而子 registry 是 `ChildRunner`（entry 层）在
> `Delegate` 背后建的；`TaskTool` 结构上就拿不到它。要让第二道闸盖到真实
> 路径，得让 `Delegate` 把建好的子 registry 回传给 `TaskTool` 复检——那是
> 给一条只为断言存在的接缝，代价大于收益。
>
> **如实的表述是：一道闸 + 一条定义自洽性断言。** 闸是 `resolve_tools`
> 的那行过滤。`_refuse_recursion` 断言的是「这份 `SubAgentDefinition` 的
> `resolve_tools` 不会吐出 `task`」——它能抓住 `resolve_tools` 本身被改坏
> （§13 第一条变异实测里它先于测试拦下了委派），抓不住调用方绕过
> `resolve_tools`。后者由 `test_the_child_never_gets_the_delegation_tool`
> 与 `test_the_child_inherits_the_rest_of_the_parent_s_table_in_order`
> 钉住，纵深防御的第二层在**测试**里而不在运行时。

**第 2 条是本层与 harness9 最重要的一处差异，且本仓库的做法更强。**
harness9 的 `buildChildRegistry`（`runner.go:60-85`）拿的是**未包装的
`baseTools`**，然后自己重新包一遍 `permission.NewFileHook(settingsPath)` +
`denyTaskHook` + `sharedHooks`——也就是说，**父的 hook 链与子的 hook 链是
两次独立组装，靠人工保持一致**。漏包一个，子代理就比父代理宽松，而且不会
有任何东西报错。

**这不是假想的风险，harness9 自己就漏了一个。** 子链是
`{permission.NewFileHook, denyTaskHook}` + danger + offload（`runner.go:84`），
父链是 `{permHook, dangerHook, offloadHook}` + **`obsHook`**
（`main.go:413-416`）——子代理的工具调用**不进 OTEL span**。方向上无害，
但它恰好证明了"两条链独立维护"会发生什么。

本层改为：**从父 `ToolRegistry` 已注册的工具里按名字挑**。`GatedTool` 与
hook 包装都已经在那些对象上了，筛选不会把它们剥掉。

### 6.1 但"挑对象"还不够——策略不在对象上（独立审核发现，高危）

初稿把这条性质称作"构造上为真"，**只说对了一半**。判据：

- `GatedTool._policy()`（`permission/gate.py:405-420`）**最优先读
  `effective_policy()`**——那是**正在执行它的那个 registry** 在
  `registry.py:359` 用 `use_effective_policy(self.policy_for(name))` 发布的
  contextvar。
- 读不到时退回 `self._inner.policy`，也就是**工具作者写在类上的默认值**，
  **不是**父 registry 的部署级覆盖。
- 部署级覆盖存在父 registry 私有的 `_policies` dict 里，`Tool` 对象本身
  不携带它。而这种覆盖**真实存在**：`entry/assembly.py:1206` 的
  `_apply_bash_policy` 在沙箱无网络时把 `bash` 从 `ASK` 改成 `AUTO`。

所以朴素地"挑对象重建 registry"会**静默丢掉部署级策略覆盖**。当前代码库
唯一那处覆盖的方向恰好是变严（子代理里 bash 退回 `ASK`，多问一次），但
API 完全支持反向——一个部署若用 `register(tool, policy=更严的)` 收紧某个
工具，子代理里就会比父代理**更松**，直接反证"构造上为真"。

**硬约束：子 registry 必须逐个显式带上父的策略。**

```python
child = ToolRegistry()
for name in definition.resolve_tools(parent.names()):
    child.register(parent.get(name), parent.policy_for(name))
```

三个 API 都是公开的：`names()`（`registry.py:220`，返回注册顺序，顺便满足
§4 的顺序要求）、`get()`（`:216`，返回已包装的对象本身）、`policy_for()`
（`:224`）。

配套测试**两条**，且各配一条变异测试：

1. `permission-mode=read-only` 的部署下，子代理调 `write_file` 同样被拒。
2. 父 registry 用 `register(tool, policy=收紧的)` 覆盖过的工具，在子代理里
   **仍然是收紧的**。把 `parent.policy_for(name)` 那个实参删掉 →
   第 2 条必须红。删掉不红的测试不算测试。

---

## 7. 审批与超时 —— §12.6 已铺好的地基，本层只需复核

### 7.1 审批：什么都不用做

§12.6 已实测：父 turn 绑定的 `ApprovalChannel` 经 `copy_context()` 穿过
三层嵌套 Task 到达父 broker。`task` 工具在父工具 Task 里跑，子引擎的
`execute_tool_calls` 再起 Task，**子代理的审批请求自动变成父 turn 事件流
上的 `APPROVAL_REQUIRED` 帧**。

本层要补的只有**归属**：往 `ToolContext.values` 里放一个
`SUBAGENT_VALUE_KEY = "subagent"`（值为子代理名），让 surface 能把审批框
标成「general-purpose 请求执行 bash」而不是含糊的「请求执行 bash」。
`ApprovalRequest` 不加字段——`values` 已经是"这一轮的事实"的去处。

#### 7.1.1 但"放一个键"若按字面实现会打挂子代理（独立审核发现，高危）

`use_tool_context` 的语义是**整体替换**，不是合并。
`tools/context.py:335` 逐字写着：「**Replaces rather than merges, and that
is a safety property.**」——刻意如此，省略的参数读作"我不需要设它"，绝不
读作"沿用上一个"。

于是 `use_tool_context(values={SUBAGENT_VALUE_KEY: name})` 会**冲掉外层
全部既有键**。后果不是审批卡片文案难看，是子代理直接报错：

| 被冲掉的键 | 谁读它 | 缺失时 |
|---|---|---|
| `workspace`（`WORKSPACE_KEY`） | `tools/builtin/read.py:404` 及其余三个文件工具 | **直接 `RuntimeError`** |
| `session_id` | `hooks/audit.py` | 静默退化为空串，审计日志丢会话归属 |
| planning 的 `SESSION_VALUE_KEY` | `planning/tool.py:191` | `plan_write` 写到错误的会话作用域 |

**硬约束：委派时必须显式 spread 现有 values，并显式转交 approval 与
progress**（后两者同样会被替换语义清掉）：

```python
outer = current_context()
with use_tool_context(
    approval=outer.approval,
    progress=outer.progress,
    values={**outer.values, SUBAGENT_VALUE_KEY: definition.name},
):
    ...
```

本仓库已有同形先例：`entry/turn.py:360` 的
`values={**outer.values, "session_id": session_id}`。

**§10 必须加一条测试**：子代理内调用 `read_file` 能正确解析 workspace。
这条缺陷最容易漏测——审批测试全绿而文件工具全挂。

#### 7.1.2 回应 0027 §12.8 第 6 条的前提条件

§12.8 第 6 条把"审批自动穿透"的结论限定为：**只要 0046 不触碰
`tools/context.py:37-43` 写明的两种破坏写法**——(a) 内联 `await` 而不起
Task，(b) 显式传 `context=` 共享同一个 context 对象。

本层的实现必须满足：`task` 工具经 `Delegate` 调到 `entry/subagent.py`，
后者驱动 `exchange_stream`，子引擎的 `execute_tool_calls` 照常
`asyncio.ensure_future` 起 Task 且不传 `context=`。**两条都不碰。**
§10 的端到端审批测试同时就是这条的回归测试。

### 7.2 超时：`task` 工具握住一个 pause

一次委派远超 `tool_timeout`（默认 60s）。`task.execute` 全程持有
`pause_tool_timeout()`：

```python
with pause_tool_timeout() as paused:
    if not paused:
        ...  # 没有 pause 可用：说明没人给 deadline，照跑
    return await self._delegate.delegate(definition, prompt)
```

`_paused`（`executor.py:389`）把 deadline 摘掉，退出时按**剩余秒数**装回去。
这比 harness9 的 `execCtx` 派生更简单，且取消语义不变：父 Task 被取消时
子代理随之取消。

**代价要写明**（`_paused` 的 docstring 自己说了）：一个握着 pause 的调用在
引擎侧**没有上界**，它同时是 barrier，所以本轮其余工具都在它后面等。真正
的上界是 `turn_timeout_s`（entry 侧，§12.4.4 裁定留在那里）——也就是说，
**一次跑飞的委派由回合超时兜底，而不是工具超时**。这是正确的层级。

---

## 8. 进度透传：复用 `ProgressSink`，不新增事件类型

harness9 为此新建了 `schema.SubAgentUpdate`、`hooks.SubAgentProgressFunc`
和 `engine.EventSubAgent` 三样东西（`sub-agent.md`「TUI 实时进度渲染」）。
本仓库**一样都不需要新建**：

```
子引擎 exchange_stream 事件
   → entry/subagent.py 转成一行文本
   → await report_progress(f"[{name}] ▸ {tool}", tool_name="task")
   → 父 ToolContext.progress（ProgressSink）
   → TurnEventType.PROGRESS 帧
```

**"超集"这个说法初稿写夸大了，独立审核纠正如下。** 逐字段对照
`schema/subagent.go:26-37` 的 `SubAgentUpdate` 与 `tools/context.py:216`
的 `ProgressUpdate`：

| `SubAgentUpdate` | 本层的去处 |
|---|---|
| `ToolName` | `ProgressUpdate.tool_name` |
| `Text` | `ProgressUpdate.message` |
| `AgentName` | 另一条通道：`ToolContext.values` 的 `SUBAGENT_VALUE_KEY`（§7.1） |
| `Kind` | 不传。它只被 TUI 用来选前缀字符，属渲染，归 surface |
| `IsError` | **不传，这是一处真实的信息损失** |

`IsError` 今天只能塞进 `message` 文本里（如 `[name] ✗ bash`），surface 无法
按结构判断。可接受，因为**子代理内失败的工具会以 `is_error` Observation
的形式回到子代理自己手里并被它处理**，父代理关心的是最终结论；但这不是
"超集"，是一处有意的裁剪，写出来而不是含糊过去。

**`REASONING_DELTA` 不转发**，与 harness9 一致（它的 `SubAgentThinking`
"故意不展示，减少噪声"）。

---

## 9. 本轮范围：只做前台

后台委派在 harness9 里是四件事的合集：`TaskTracker`（线程安全事实源）、
`go func` 脱离父 turn、`DrainCompleted` 在下次 dispatch 前注入、TUI 面板。

**本仓库做后台需要一条今天不存在的接缝**：`DrainCompleted` 的等价物必须在
`SessionRegistry.submit` 组 prompt 之前被查询并前置拼入，而 `submit`
（`entry/session.py:341`）今天只接 `text` 与 `values`。这是 entry 层手术，
与"委派一个子代理"是两件独立的事。

再加一条 Python 特有的：脱离父 turn 的 `asyncio.create_task` 必须有人持有
引用（否则被 GC）、必须在 `SessionRegistry.shutdown` 时被等待或取消、且它
的 `ToolContext` 必须显式重绑（不能继承父的 broker——父 turn 结束后那个
broker 已 `abandon`）。这三条每一条都能单独写成一条缺陷。

**裁定：0046 只做前台，0047 做后台 + `TaskTracker` + `@agent` 直跑。**
前台委派是 80% 的价值，且是后台的严格子集——后台只改"结果怎么回来"，不改
"子代理怎么跑"。

---

## 10. 交付物

### 新增包 `omicsclaw/subagent/`（叶子邻接层，白名单 `schema` + `tools`）

| 文件 | 内容 |
|---|---|
| `definition.py` | `SubAgentDefinition`、`validate`、`resolve_tools`、`TASK_TOOL_NAME` |
| `registry.py` | `SubAgentRegistry`：`register` / `get` / `list`（启动注册，运行期只读） |
| `frontmatter.py` | `parse_agent_file`：YAML frontmatter + 正文 → 定义 |
| `loader.py` | `load_agents(dir)`：扫 `*.md`；目录不存在静默返回；单文件失败跳过不中断；缺 `name` 用文件名兜底 |
| `prompt.py` | `ChildPrompt`：同时满足 `PromptSource` 与 `RenderedPrompt` |
| `delegate.py` | `Delegate` Protocol、`SUBAGENT_VALUE_KEY` |
| `task_tool.py` | `TaskTool`：动态 `definition()`、`ToolPolicy`、握 pause、防递归断言 |

### 新增 `omicsclaw/entry/subagent.py`（组装）

`build_subagent_registry(config)`（内置 `general-purpose` + `load_agents`
扫 `config.agents_root()`）、`ChildRunner`（实现 `Delegate`）。

### 修改（最小面）

| 文件 | 改动 |
|---|---|
| `entry/config.py` | `AppConfig.agents_root() -> Path`（= `state_dir()/agents`，与 `plans_root()` 同形）；`AppConfig.subagents: bool = True` 开关 |
| `entry/assembly.py` | `build_app` 在 registry 建好后追加 `task` 工具（**追加在末尾**，不移动任何既有工具，保持前缀缓存字节稳定——0028） |
| `omicsclaw/entry/__init__.py` | 导出 `build_subagent_registry` |

### 内置 `general-purpose`

对标 Claude Code 与 DeepAgents 的同名子代理：`tools` / `model` /
`max_turns` 全部留空 = 继承父代理的全部工具与模型。system prompt 强调
「你看不到主代理的对话历史」「最终回复是唯一交付物，必须自包含」。

### 测试

| 文件 | 盯什么 |
|---|---|
| `tests/subagent/test_subagent_is_a_leaf_layer.py` | 白名单 `schema` + `tools`；**行为探针**：跑完全部真实路径后 `sys.modules` 里没有 `engine`/`entry`/`skills` |
| `tests/subagent/test_definition.py` | `validate`；`resolve_tools` 的三步与**顺序保持** |
| `tests/subagent/test_frontmatter.py` | 解析；缺字段；引号；列表 |
| `tests/subagent/test_loader.py` | 目录不存在；单文件坏了不中断；文件覆盖同名内置 |
| `tests/subagent/test_task_tool.py` | 动态 enum；未知类型的报错带可用列表；**`task` 不在自己给出的工具集里** |
| `tests/entry/test_subagent_wiring.py` | 端到端：委派一次拿到结论；**子代理权限 ⊆ 父**（read-only 部署下子代理写文件被拒）；**部署级策略覆盖不丢失**（§6.1，配变异测试）；**子代理内 `read_file` 能解析 workspace**（§7.1.1，values 被整体替换的回归）；**审批穿透**（子代理调 bash 时父 broker 收到请求，且 `values` 里有子代理名）；**降级部署下子 prompt 出现降级说明而非容器说明**（§3.5）；**进度到达父 PROGRESS 帧**；**pause 让委派跑满超过 `tool_timeout`** |

---

## 11. 刻意偏离参考实现（逐条给理由）

| # | harness9 | 本层 | 理由 |
|---|---|---|---|
| 1 | 子代理绑一个丢弃式 `memory.MemorySession`（**是选择，不是被迫**——`agent_loop.go:48` 的 session 可为 nil） | 不绑 `Conversation` | §12 之后 `exchange(conversation=None)` 连这个选择都不必做；少一条能泄漏父上下文的路径（§3.3） |
| 2 | `buildChildRegistry` 拿未包装的 `baseTools` **重新包一遍** hook 链 | 从父 registry 里**按名字挑已包装的对象** | "子权限 ⊆ 父"从纪律变成构造上为真（§6） |
| 3 | `execCtx` 从 `baseCtx` 派生 + goroutine 分辨真取消 | `pause_tool_timeout()` | 更简单，且取消语义不用碰（§7.2） |
| 4 | 新建 `SubAgentUpdate` / `SubAgentProgressFunc` / `EventSubAgent` 三样 | 复用 `ProgressSink` + `PROGRESS` | 已有的覆盖 ToolName/Text，AgentName 走 values，**`IsError` 有意裁剪**；新增等于给 surface 多一套要认的词汇（§8） |
| 5 | `ResolveTools` 按白名单顺序输出 | 按父工具表顺序过滤 | 工具表顺序是前缀缓存的一部分（0028） |
| 6 | `promptBuilder` 硬编码规划准则 | 不注入 | 准则属 `planning`，本层不依赖它；给不给 `plan_write` 由白名单决定（§3.4） |
| 7 | 前台 + 后台双模式 | 只做前台 | 后台需要一条 `SessionRegistry` 上的注入接缝（§9），0047 |
| 8 | `denyTaskHook` 纵深防御 | `resolve_tools` 移除 + `TaskTool` 内的定义自洽性断言 | 不必依赖 `hooks` 包（白名单）。**注意**：这不是对等的两道闸，本层的第二条看不到真实子 registry，见 §6 的更正 |

---

## 12. 已知代价

1. **`task` 工具的 `approval_mode=AUTO` 是一个刻意的宽松默认**，与 0028
   "忘记声明的代价应该是多弹一次框"的精神相反。§5 给了理由，但这是本层
   最该被审核盯的一处：如果那条"子工具的 gate 一个都没少"的性质将来被
   破坏，这个 AUTO 就从合理变成漏洞。配套测试必须存在且不可删。
2. **一次委派是一个 barrier，且引擎侧无上界。** 本轮其余工具在它后面等，
   真正的上界是 `turn_timeout_s`（§7.2）。一个部署若把 `turn_timeout_s`
   设为 `None`（CLI 默认），一次跑飞的委派没有任何自动上界，只能 Ctrl+C。
3. **子代理的 token 用量不进父 `RunResult.usage`。** 两次运行是两个
   `RunResult`，本层不合并。后果是 `/usage` 少算。0047 一并解决，或者
   接受——但要写出来。
4. **`task` 进入工具表会让所有既有缓存前缀作废一次**（追加在末尾只能保证
   *之后*稳定，不能免掉这一次）。0028 已记过这个代价的形状。
5. **文件式定义没有 schema 校验**，坏文件只记一条 warning 并跳过（与
   harness9 一致）。一个 typo 导致子代理静默消失，用户看到的是
   `subagent_type` 的 enum 里少了一项。

---

## 13. 验证

- `pytest tests/subagent tests/entry tests/engine -q -p no:randomly`
  （`/opt/conda/envs/rapids_singlecell/bin/python`）
- **层边界行为探针**（沿用 `tests/planning/` 的写法）：在子进程里跑完本层
  全部真实路径，断言 `sys.modules` 里没有 `omicsclaw.engine`、
  `omicsclaw.entry`、`omicsclaw.skills`。
- **三条安全性质各一条点名测试**，且各配一条变异测试：
  - 把 `resolve_tools` 里移除 `task` 的那行删掉 → 递归测试必须红
  - 把"从父 registry 挑"改成"重新构造工具" → 权限测试必须红
  - 把 `pause_tool_timeout()` 去掉 → 长委派测试必须红（超时）
- **审批穿透**用真实的 `ApprovalBroker` 而不是测试桩，因为要验的正是
  contextvars 穿过 Task 边界这件事。

---

## 14. 本层落地后要回头复核的两条

- **0027 §12.2.3 的 `EngineObserver`**：那条债的理由是"等 0046 这个真实
  消费者"。本层大量使用阻塞路径（`task` 要的是结论不是事件流），落地后
  必须复核一次：还需不需要 `EngineObserver`。§12.8 第 6 条已自我设限
  ——**若仍无消费者，降级为「不做」，不许再推第三次**。
- **0027 §12.6 的那条链路图**：它当时是对未来代码的预测（`task` 工具与
  子引擎都还不存在）。本层落地后，把 §12.6 的语气从预测改为核实，或者
  如实记录预测哪里错了。

---

## 15. 两轮独立只读审核的发现与返工（2026-09-21）

体例沿用 0039 §8 与 0027 §12.10。初稿写完后交给两个**独立、只读、未参与
撰写**的审核者：一个查正确性（对照本仓库源码），一个查 harness9 对照
忠实度。判定分别是「需返工」与「基本忠实，两处实质瑕疵」。

### 15.1 已返工（高危）：子 registry 会静默丢掉部署级策略覆盖

初稿把「从父 registry 挑已包装的对象」称作"构造上为真"，**只对了一半**：
`GatedTool` 的策略不在对象上，而在**执行它的那个 registry** 发布的
contextvar 里（`permission/gate.py:405-420` + `registry.py:359`）。朴素地挑
对象重建 registry，会丢掉 `register(tool, policy=…)` 形式的部署级覆盖，
而 `assembly.py:1206` 的 `_apply_bash_policy` 就是一条真实的覆盖。

已补 §6.1：硬约束是逐个显式 `child.register(parent.get(n), parent.policy_for(n))`，
并配一条变异测试（删掉 policy 实参必须变红）。

### 15.2 已返工（高危）：往 `values` 塞键会打挂子代理的文件工具

`use_tool_context` 是**整体替换**（`tools/context.py:335` 的原话：
「Replaces rather than merges, and that is a safety property」）。初稿
§7.1 那句"往 `ToolContext.values` 里放一个键"若被字面实现，会冲掉
`workspace` 键 → `tools/builtin/read.py:405` 直接 `RuntimeError`，子代理里
一切文件工具与 `plan_write` 全挂。

已补 §7.1.1：必须 spread 现有 values 并显式转交 approval / progress，
并在 §10 加了一条"子代理内 `read_file` 能解析 workspace"的回归测试。
本仓库已有同形先例（`entry/turn.py:360`）。

### 15.3 已返工：初稿对 harness9 说了一句假话

初稿称「harness9 的引擎必须绑一个 `Session` 才能跑」。**不成立**——
`agent_loop.go:48` 的 session 字段注释是「可选，nil 表示无持久化」。这句
被用来衬托本仓库"更简单"，属于把参考实现说得比实际更笨。已在 §2 原地
纠正并保留了错误记录，而不是抹掉重写。

### 15.4 已补：`compact.go` 之外的又一条漏记 —— 执行环境说明

harness9 的 `WithSandboxContext` / `WithSandboxDegraded`（`prompt.go:73-93`）
把容器/降级说明注入子代理 prompt。初稿全篇未提，也没列入"推迟"或"不做"。
这不是细节：子代理复用父 `bash`，若在降级部署上被告知"你在容器里，缺包
直接 apt-get"，它会往用户宿主机装东西。已补 §3.5。

### 15.5 已改：§8 的"超集"表述夸大

`SubAgentUpdate.IsError` 在本层没有传递路径。已改为逐字段对照表，如实
写明这是一处**有意的裁剪**而非超集。

### 15.6 已补：回应 0027 §12.8 第 6 条的前提条件

§12.8 把"审批自动穿透"限定为"只要 0046 不触碰两种已知破坏写法"。初稿
未回应。已补 §7.1.2，并说明本层的实现路径两条都不碰。

### 15.7 已修：事实性引用错误 5 处

`runner.go:88-210`→`:89-245`、`task_tool.go:41-77`→`:36-69`、
`prompt.go:57-95`→`:52-71`、`executor.py:388`→`:389`、§3.3 的退化路径
（子代理会传 prompt，所以是 `[system, user]` 不是 `[user]`）。

### 15.8 三条被认真攻击而未被推翻的

| 裁定 | 审核做了什么 | 结果 |
|---|---|---|
| `pause_tool_timeout` 能让长委派跑满 | 写了探针 + 对照组实测：持 pause 的工具在 `tool_timeout=0.3s` 下 sleep 2s 未被杀；不持 pause 的对照组被杀并返回 `timed out` | **证伪失败**，§7.2 成立 |
| 白名单 `schema` + `tools` 够用 | 逐个过 §10 交付物，确认 `PromptSource` 是纯 `typing.Protocol`、`pause_tool_timeout` 在 `tools.context` 内 | **证伪失败**，§3.1 成立 |
| §9 推迟后台的三条理由 | 核实 `submit` 签名无注入位、`ApprovalBroker.abandon` 只在 exchange 结束时触发 | **证伪失败**，且第三条准确地只适用于后台 |

### 15.9 已驳回：无

两份报告的发现全部接受。

---

## 16. 交付结果（2026-09-21）

体例沿用 0027 §12.11。

### 16.1 交付物

| 文件 | 内容 |
|---|---|
| `omicsclaw/subagent/definition.py` | `SubAgentDefinition`、`validate`、`resolve_tools`、`TASK_TOOL_NAME`、`InvalidDefinition` |
| `omicsclaw/subagent/registry.py` | `SubAgentRegistry`，注册顺序即枚举顺序，同名覆盖**保位** |
| `omicsclaw/subagent/frontmatter.py` | `parse_agent_file`：自带的 YAML 子集解析器（本层不能 import `omicsclaw.skills`） |
| `omicsclaw/subagent/loader.py` | `load_agents(dir, on_error=…)`：非递归扫 `*.md`；目录不存在返回 `()` |
| `omicsclaw/subagent/prompt.py` | `ChildPrompt`：同时满足 `PromptSource` 与 `RenderedPrompt` |
| `omicsclaw/subagent/delegate.py` | `Delegate` Protocol、`SUBAGENT_VALUE_KEY` |
| `omicsclaw/subagent/task_tool.py` | `TaskTool`、`TASK_TOOL_POLICY`、`RecursionRefused` |
| `omicsclaw/entry/subagent.py` | `GENERAL_PURPOSE`、`build_subagent_registry`、`ChildRunner` |
| `omicsclaw/entry/config.py` | `AppConfig.subagents` + `--subagents` / `OMICSCLAW_SUBAGENTS`；`agents_root()` |
| `omicsclaw/entry/assembly.py` | `task` 追加在工具表末尾，经同一条 hook 链与同一个 gate |
| `omicsclaw/entry/__init__.py` | 导出 `build_subagent_registry`、`ChildRunner` |

测试：`tests/subagent/`（`__init__` + 五个计划内文件 + `test_prompt.py`）与
`tests/entry/test_subagent_wiring.py`。

### 16.2 硬约束逐条核实

| 约束 | 实现处 | 钉住它的测试 |
|---|---|---|
| §6.1 子 registry 显式带上父策略 | `ChildRunner._child_registry` 的 `child.register(parent.get(n), parent.policy_for(n))` | `test_a_deployment_s_policy_override_survives_into_the_child` + 对照组 |
| §7.1.1 委派时 spread 现有 values、显式转交 approval/progress | `TaskTool.execute` | `test_the_child_s_file_tools_still_resolve_the_bound_workspace`、`test_every_outer_value_survives_and_the_sub_agent_s_name_joins_them` |
| §6 禁止递归（一道闸 + 一条定义自洽性断言，见 §6 更正） | 闸：`resolve_tools` 移除；断言：`TaskTool._refuse_recursion`（只看 `definition`，看不到子 registry） | `test_the_delegation_tool_is_always_removed`、`test_the_child_never_gets_the_delegation_tool`、`test_a_definition_that_resolves_the_delegation_tool_is_refused` |
| §7.2 全程握 pause | `TaskTool.execute` | `test_a_delegation_may_outlast_the_per_tool_timeout` + 不持 pause 的对照组 |
| §3.5 执行环境说明继承 | `ChildRunner._child_prompt` 复用 `sandbox_section` | `test_a_degraded_sandbox_is_described_to_the_child_as_degraded` |
| §3.3 无 `Conversation` | `exchange_stream(prompt, prompt=ChildPrompt)`，不传 `conversation` | `test_the_child_is_given_the_task_text_and_no_parent_history` |
| §4 保持父工具表顺序 | `resolve_tools` 按 `all_names` 过滤 | `test_the_child_inherits_the_rest_of_the_parent_s_table_in_order` |

三条变异测试实测：

1. 删掉 `resolve_tools` 里 `name != TASK_TOOL_NAME` → `tests/subagent` +
   `tests/entry/test_subagent_wiring.py` 22 项红，其中点名的两条是
   `test_the_delegation_tool_is_always_removed` 与
   `test_the_child_never_gets_the_delegation_tool`。后者红成 `IndexError`
   而不是断言失败，因为第二道闸先拦下了委派——纵深防御按设计工作。
2. 删掉 `child.register(...)` 的 `parent.policy_for(name)` 实参 → **恰好
   一条**红：`test_a_deployment_s_policy_override_survives_into_the_child`，
   且红在最坏的方向上（子代理把父部署收紧过的 `read_file` 读了出来）。
3. 去掉 `pause_tool_timeout()` → **恰好一条**红：
   `test_a_delegation_may_outlast_the_per_tool_timeout`，报
   `tool 'task' timed out after 0.15s`。

### 16.3 实现期发现的、计划没写到的

1. **`task` 也要过 gate，而 `read-only` 模式会因此拒绝委派本身。**
   `task` 无法诚实声明 `read_only=True`（子代理干什么都行），所以
   `PermissionGate` 的 `read-only` 分支直接拒掉它。这是正确的方向，但
   §6.1 的第 1 条测试因此不能走 `task` 工具——改为直接驱动 `ChildRunner`，
   另配一条 `test_a_read_only_deployment_refuses_the_delegation_itself`
   把这条后果写成断言。
2. **工具描述里不能出现 "Delegate" 这个词。**
   `tests/entry/test_permission_wiring.py::test_the_gate_does_not_change_what_the_model_is_shown`
   用裸子串 `"gate"` 断言"被 gate 这件事不进 prompt"，而 `Delegate` 里
   含 `gate`。选择改措辞（`Hand a self-contained sub-task…`）而不是放宽那条
   断言——但那条断言本身是脆的（`aggregate_counts` 一样会误伤），**留给
   owner 决定要不要收紧成按 `GatedTool` / `approval_mode` 匹配**。
3. **`task` 挤进工具表会把两条既有压缩测试推过压力档。**
   `tests/entry/test_turn.py::test_the_system_message_survives_a_successful_summarization`
   与 `tests/entry/test_session.py::test_a_second_compaction_extends_the_first_instead_of_restarting`
   本来就为此写了 `memory=False`；补 `subagents=False` 并同步注释。这是
   §12 第 4 条代价（缓存前缀作废一次）的另一面：它也动到了
   `reserve_tool_tokens`。
4. **MCP 工具不再是工具表末尾。** `task` 追加在 MCP 之后，
   `tests/entry/test_open_app.py` 的 `names[-2:]` 断言相应改写。
5. **本层的 `frontmatter.py` 是第二份 YAML 子集解析器。**
   `omicsclaw/skills/frontmatter.py` 已有一份，但白名单不许 import。两份
   实现覆盖的子集不同（本层多认逗号分隔列表，少认块标量与折叠续行），
   这是白名单换来的重复，写在这里而不是假装没有。
6. **进度事件没有 `IsError`，也没有子代理内的最终文本。** §8 已承认
   `IsError` 的裁剪；实现时确认 `REASONING_DELTA` 与 `TEXT_DELTA` 一并不转发，
   父代理看到的进度只有 `[<name>] <tool>` 一行。

### 16.4 §14 两条回头复核的结果

- **`EngineObserver`**：0046 走的是 `exchange_stream` 而非阻塞 `run()`，
  预测的消费者没有出现。按 0027 §12.8 第 6 条的自我设限，已在
  `docs/plans/0027-react-main-loop.md` §12.2.3 结案为「不做」。
- **0027 §12.6 的链路图**：预测正确，已就地改为核实并注明钉住它的测试；
  同时记下原文没预见的一点（`use_tool_context` 的整体替换语义）。

## 17. 交付后缺陷修复（2026-09-23）

- **子代理改写父会话计划。** 子代理的工具调用沿用父轮的 `session_id`，而 general-purpose 继承了 `plan_write`。修法：`entry/subagent.py` 设唯一的父会话专属工具集合 `_PARENT_SESSION_TOOLS`（目前只有 `plan_write`），`_child_registry` 按它剔除；agent 文件的 `tools:` 点名其中工具时 `build_subagent_registry` 记 warning；general-purpose 的描述改为"除 `task`、`plan_write` 外的全部工具"。测试：`test_a_sub_agent_cannot_see_or_change_the_parent_s_plan`、`test_an_agent_file_that_asks_for_plan_write_is_warned_and_runs_without_it`，并改写 `test_the_child_inherits_the_rest_of_the_parent_s_table_in_order`。
- **撞轮数上限时把工具原文当结论交回。** 修法：`ChildRunner.delegate` 按 `StopReason` 取结论——`CONVERGED` 行为不变；`MAX_TURNS` 抛 `DelegationIncomplete`（"stopped at the turn limit (N) without a conclusion"，附最后一段 assistant 文字）；`TRUNCATED` 有正文则标明"cut off at the output limit"后返回，无正文同样抛 `DelegationIncomplete`。测试：`test_a_sub_agent_that_runs_out_of_turns_reports_failure_not_its_last_tool_output`、`test_the_turn_limit_error_carries_the_sub_agent_s_last_words`、`test_a_truncated_answer_is_marked_as_cut_off`、`test_a_truncated_turn_with_no_text_is_reported_as_no_conclusion`，`test_a_sub_agent_s_turn_ceiling_is_honoured` 改为断言抛出。
- 设计依据：0047 第一版的 A0（子代理不得改写父会话的计划）与 A1（撞轮数上限时不得把工具原文当结论交回），要点即上两条修法；0047 第二版已把两项移出（见其开头的去向表），第一版未入 git。审核意见见 `docs/reviews/2026-09-23-plans-0047-0052-0053-0054.md`："0047 审核"一节对 A0/A1 的结论及 S10（A1 边界）、S11（A0 告警），"接缝审核"一节的 Q-C（剔除机制统一到一处）。
- **子代理可写跨会话的持久记忆；剔除清单、描述、告警各写一份。** `memory_write` 写入的条目会进入以后每个会话的系统提示，读到恶意文件的子代理可借此种下一条永久注入；它不属于"父会话状态"，不宜并入 `_PARENT_SESSION_TOOLS`。修法：该集合改为唯一的映射 `_WITHHELD_FROM_SUB_AGENTS`（工具名 → 理由），现含 `plan_write`、`memory_write`，0054 的 `ask_user` 也加在这里；`_child_registry` 仍是唯一剔除点，`memory_search` 保留。general-purpose 的描述改由 `_general_purpose_description` 从映射渲染（`task` 在前，每个工具附理由）；agent 文件的 `tools:` 写了 `task` 或映射中的工具，一律记 warning 并附理由（此前写 `task` 不告警）。测试：新增 `test_a_sub_agent_cannot_write_the_memory_later_conversations_read`、`test_the_general_purpose_description_is_rendered_from_the_withheld_tools`、`test_an_agent_file_that_asks_for_task_is_warned_too`，改写 `test_the_child_inherits_the_rest_of_the_parent_s_table_in_order`（再减去 `memory_write`）。依据：同一审核文档第二轮 S1、第三轮"O3 剔除机制"一行（参照 harness9 不给子代理 `memory_write`）。
