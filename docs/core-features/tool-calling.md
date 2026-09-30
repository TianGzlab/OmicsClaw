# Tool Calling 工具调用系统

## 1. 概述

Tool Calling 是 OmicsClaw agent 与外部世界交互的唯一通道：模型在一次回复里发出若干 `ToolCall`，引擎并发（受写屏障约束）调度执行，每个调用得到一条 `ToolResult`，投影为 `Role.TOOL` 的 Observation 消息追加进历史，进入下一轮模型调用。

对一个多组学分析 agent 而言，这条通道承载的是真实工作：用 `bash` 跑 `skills/spatial/spatial-preprocess/spatial_preprocess.py`，用 `read_file` 看 `result.json`，用 `use_skill` 取回某个 skill 的 `SKILL.md`，用 `web_fetch` 查一个 GEO accession。

本文覆盖 `omicsclaw/tools/`（工具抽象、注册表、适配器、上下文通道）、`omicsclaw/engine/executor.py`（调度模型）、`omicsclaw/tools/_pathlock.py`（路径锁），以及 `omicsclaw/entry/assembly.py` 实际装配的工具清单。权限门、hooks、MCP、沙箱各有专文，这里只讲它们与工具调用的接缝。

分层约束：`omicsclaw/tools/` 在 `omicsclaw` 命名空间内只允许导入 `omicsclaw.schema`，由 `tests/tools/test_tools_is_a_leaf_layer.py`（AST + 动态导入 + 行为探针）强制；`engine` 与 `tools` 互不导入，靠结构化 Protocol 对接。

## 2. 架构总览

```
┌──────────────────────────────── entry/assembly.py (build_app) ───────────────────────────────┐
│                                                                                              │
│  foundation_tools()        mcp.tools()          TaskTool                                     │
│  read/write/edit/bash/     mcp__{server}__{tool} (subagent)                                  │
│  web_fetch/web_search/                                                                       │
│  use_skill/plan_write/memory_*                                                               │
│         │                        │                  │                                        │
│         └──────────┬─────────────┴──────────────────┘                                        │
│                    ▼                                                                         │
│        hook_tools(tools, chain)     → HookedTool   (omicsclaw/hooks)                         │
│                    ▼                                                                         │
│        gate_tools(tools, gate)      → GatedTool    (omicsclaw/permission)                    │
│                    ▼                                                                         │
│        ToolRegistry  ──── 按注册顺序 available_tools() ────► provider（工具定义进 prompt）      │
│            │  execute(call) / is_concurrency_safe(name) / use_timeout_pause(pause)           │
└────────────┼─────────────────────────────────────────────────────────────────────────────────┘
             │ 结构化满足 ToolExecutor / ConcurrencyAwareExecutor / DeadlineAwareExecutor
             ▼
┌──────────────────────── engine/loop.py → engine/executor.py ─────────────────────────┐
│  assistant message.tool_calls                                                        │
│      └─ execute_tool_calls()                                                         │
│           ├─ _concurrency_groups()   安全调用并行成批，不安全调用单独成批（写屏障）       │
│           ├─ 每个调用一个 asyncio.Task（各自拷贝 contextvars）                          │
│           ├─ _execute(): asyncio.timeout(tool_timeout) + TimeoutPause                 │
│           └─ slots[i] 按下标回填 → _answer_every_call() → observations()              │
│                                                  └─ ToolResult.to_message() (Role.TOOL)│
└──────────────────────────────────────────────────────────────────────────────────────┘
             │ 工具执行期间，经 contextvars 访问：
             ▼
   omicsclaw/tools/context.py：ApprovalChannel / ProgressSink / values / effective_policy / TimeoutPause
```

## 3. 核心数据流

```
1. 模型回复带 tool_calls（schema.ToolCall：id / name / arguments 原始 JSON 字符串）
2. AgentEngine 调 execute_tool_calls(registry, calls, config, results, turn)
3. _concurrency_groups 把本轮调用切成批；逐批启动，每个调用一个 Task
4. 每个 Task：发 TOOL_START 事件 → _execute() → registry.execute(call)
      └─ ToolRegistry.execute：查名字 → use_effective_policy(policy_for(name)) → tool.execute(arguments)
            └─ GatedTool → HookedTool → 具体工具（内部可 require_approval / report_progress）
5. 结果写入 slots[index]，发 TOOL_RESULT 事件（带 duration_s）
6. 全部批次结束后 results.extend(slots)；None 槽位由 _answer_every_call 补成失败 Observation
7. observations() 把 ToolResult 投影为 Role.TOOL 消息（空输出替换为 empty_output_placeholder）
8. 进入下一轮模型调用
```

## 4. 核心类型

### 4.1 schema 层（`omicsclaw/schema/message.py`）

| 类型 | 字段 | 说明 |
|---|---|---|
| `ToolCall` | `id`, `name`, `arguments: str = "{}"` | `arguments` 是**原始 JSON 字符串**，引擎不解析；`parsed_arguments()` 对坏 payload 返回 `{}`，工具层刻意不用它 |
| `ToolResult` | `tool_call_id`, `name`, `output`, `is_error`, `metadata` | `metadata` 里由注册表写入 `duration_s`；`to_message()` 投影为 `Role.TOOL` 消息并携带 `is_error` |
| `ToolDefinition` | `name`, `description`, `input_schema: dict` | 模型看到的全部内容；**不含任何策略字段** |

### 4.2 `Tool` Protocol（`omicsclaw/tools/base.py`）

```python
@runtime_checkable
class Tool(Protocol):
    @property
    def name(self) -> str: ...
    def definition(self) -> ToolDefinition: ...
    async def execute(self, arguments: str) -> str: ...
```

| 成员 | 约定 |
|---|---|
| `name` | 必须等于 `definition().name`，注册时校验，不一致抛 `ToolNameMismatch` |
| `definition()` | 方法而非属性，便于 MCP 代理等按构造参数生成 schema；内置工具构造一次、每轮返回同一对象，保持 prompt 前缀字节稳定 |
| `execute(arguments)` | 接收未解析的原始 payload，不接收整个 `ToolCall`（工具不应依赖 `call.id`）。失败**以抛异常表达**，由注册表转换成 `is_error=True` 的 Observation |

`Tool` 是 Protocol 而不是基类：满足它只看形状，测试替身无需导入本包。`policy` 不是 Protocol 成员；实现可以带一个 `policy` 属性作为作者默认值，注册表会读取。

### 4.3 `ToolPolicy`（本地执行策略，永不进入 prompt）

`ToolPolicy` 是冻结 dataclass，与 `ToolDefinition` 分开存放于注册表，`available_tools()` 的返回类型里没有它的通道。

| 字段 | 类别 | 默认值 | 含义 |
|---|---|---|---|
| `risk_level` | 权限 | `RiskLevel.HIGH` | `LOW` / `MEDIUM` / `HIGH` |
| `approval_mode` | 权限 | `ApprovalMode.ASK` | `AUTO` / `ASK` / `DENY_UNLESS_TRUSTED` |
| `concurrency_safe` | 权限 | `False` | 引擎调度时读取；`False` 使调用成为屏障 |
| `allowed_in_background` | 权限 | `False` | 可否在无人值守的回合运行 |
| `read_only` | 声明 | `False` | 权限门据此跳过对 `.omicsclaw/` 的保护检查 |
| `writes_workspace` / `writes_config` / `touches_network` | 声明 | `False` | 仅为建议性声明；门控不得依据一个没人写过的 `False` 放行 |
| `prompts_for_itself` | 声明 | `False` | 声明工具会在自己的 `execute` 里调用 `require_approval`，由 `omicsclaw.permission.GatedTool` 读取，以便把询问交给带 diff/完整命令的工具自身 |
| `tags` | 标签 | `frozenset()` | 自由标签；MCP 工具带 `"mcp"` 与 `"mcp:{server}"` |

**默认值是"受保护"的一侧**：一个什么都没声明的工具得到 `HIGH` + `ASK` + 非并发安全 + 不许后台，遗漏声明的代价是多一次询问，而不是悄悄获得全部权限。

### 4.4 注册表错误类型

| 异常 | 触发 |
|---|---|
| `ToolRegistrationError(ValueError)` | 基类；空名字也直接抛它 |
| `ToolAlreadyRegistered` | 重名注册；已挂载的工具、策略、顺序都不变 |
| `ToolNameMismatch` | `tool.name != tool.definition().name` |

## 5. ToolRegistry（`omicsclaw/tools/registry.py`）

```python
registry = ToolRegistry()
registry.register(tool, ToolPolicy(approval_mode=ApprovalMode.ASK))
defs = registry.available_tools()        # → provider，注册顺序
result = await registry.execute(call)    # → ToolResult，永不抛出
```

| 方法 | 职责 |
|---|---|
| `register(tool, policy=None)` | 挂到末尾；重名抛 `ToolAlreadyRegistered` |
| `replace(tool, policy=None)` | 显式覆盖同名工具并**保留原位置**；名字不存在抛 `KeyError` |
| `unregister(name)` | 卸载；不存在抛 `KeyError` |
| `get(name)` / `names()` / `__contains__` / `__len__` | 查询 |
| `policy_for(name)` | 解析生效策略，未知名字返回 `ToolPolicy()` |
| `is_concurrency_safe(name)` | 满足引擎的 `ConcurrencyAwareExecutor` |
| `available_tools()` | 按注册顺序返回 `ToolDefinition` 元组，先快照再迭代 |
| `use_timeout_pause(pause)` | 满足 `DeadlineAwareExecutor`，把引擎的暂停句柄经 contextvar 传给工具 |
| `execute(call)` | 分发并返回 `ToolResult` |

### 5.1 策略解析顺序

| `tool.policy` | `register(policy=)` | 结果 |
|---|---|---|
| 有 | 有 | 注册时给的（部署方） |
| 有 | 无 | `tool.policy`（作者） |
| 无 | 有 | 注册时给的 |
| 无 | 无 | `ToolPolicy()` |

`tool.policy` 不是 `ToolPolicy` 实例时同样按"无"处理。部署方优先，因为它承担后果。

### 5.2 `execute` 的行为

- 未知工具名：返回 `is_error=True`，文本列出全部已注册工具名，便于模型自纠。
- 调用在 `use_effective_policy(self.policy_for(call.name))` 作用域内执行 —— 这是"部署方收紧 `AUTO`→`ASK`"能在执行期真正生效的唯一连线：`require_approval` 优先读这个值，而不是工具自己手里的作者策略。
- `except Exception` 而**绝不** `BaseException`：`asyncio.CancelledError` 与 `KeyboardInterrupt` 原样穿透。
- 异常文本格式为 `tool 'x' raised ValueError: ...`，类名 + 消息原样给模型。
- 只有工具真正运行过才写 `metadata["duration_s"]`。
- 注册表**不执行**审批、沙箱或路径检查；它只路由和报告。

### 5.3 顺序是保证，不是巧合

工具定义位于系统提示词与对话之间，处于 prompt 前缀缓存的 key 范围内；provider 层会把缓存断点打在 `tools[-1]` 上。因此工具列表必须每轮字节稳定，`replace` 保留原位，`assembly.py` 中后加入的工具（`use_skill`、`plan_write`、`memory_*`、MCP、`task`）一律追加在末尾。

### 5.4 不加锁

注册表不是线程安全的，这是有意的：MCP 工具在事件循环上连接、在注册表构建前交付；唯一的非事件循环线程（Feishu websocket 读取线程）通过 `asyncio.run_coroutine_threadsafe` 回到事件循环。`available_tools()` 在迭代前做快照，避免 `dictionary changed size during iteration`。

## 6. 适配器

### 6.1 FunctionTool（`omicsclaw/tools/function_tool.py`）

把一个普通函数（同步或 `async`）包装成 `Tool`：

```python
FunctionTool(name, description, func, *, parameters=None, policy=None)
```

- `execute` 流程：`decode_arguments(arguments)` → `validate_arguments(dict, schema)` → `func(**arguments)` → `as_text(result)`。
- `decode_arguments` 区分三种情况：空/空白 payload 视为 `{}`；无法解析的 JSON 抛 `ToolArgumentError`，附字符数与最多 `_EXCERPT_LIMIT = 120` 个字符的摘录；解析出来不是对象同样抛出。
- `validate_arguments` 一次列出所有问题（路径语法 `input.foo`），支持 `type`（object/array/string/integer/number/boolean）、`required`、`enum`、`additionalProperties: false`、`items`；不检查 `anyOf/oneOf/allOf/$ref/const/format`、数值/字符串/数组边界。
- `parameters` 深拷贝，多个工具共享同一个模块级 `SCHEMA` 常量也互不影响。
- `as_text`：`str` 原样；`None` → `""`；其他结构用 `json.dumps(..., ensure_ascii=False, default=str)`。
- `ToolArgumentError(ValueError)` 是公开的，工具可以自行抛出，表达 schema 无法描述的约束。

**已知局限**：被包装函数拿不到原始 payload，所以需要"审批提示与模型发送的字节完全一致"的工具（`write_file`、`edit_file`、`bash`）都直接手写 `Tool` Protocol。`read_file`、`use_skill`、`memory_search` / `memory_write` 走 `FunctionTool`。

### 6.2 MCPTool（`omicsclaw/tools/mcp_tool.py`，详见 `mcp.md`）

- 命名 `mcp__{server}__{tool}`，由 `mcp_tool_name()` 生成：经 `sanitize_mcp_name()` 清洗，总长受 `MAX_TOOL_NAME_LENGTH = 64` 约束，超长时优先保留 server 段并追加短摘要防止撞名。
- 描述前加 `[MCP:{server}]` 标记；schema 解析失败时退化为空对象 schema，原因保存在 `schema_error`。
- `execute`：只检查 payload 是 JSON 对象（不按 schema 校验，交给服务端）→ `require_approval`（理由中包含 `origin` 与 `preview_arguments` 渲染的参数）→ 调用 `MCPCaller`。
- 默认策略 `HIGH` + `ASK` + `prompts_for_itself=True`，标签 `{"mcp", "mcp:{server}"}`；不对 `touches_network` 做任何猜测。

### 6.3 参数预览（`omicsclaw/tools/preview.py`）

`preview_arguments(arguments, *, limit=MAX_PREVIEW_CHARS)` 把原始 payload 渲染成**单行**、可安全展示给人的文本，供审批提示使用：

- 解码后以 `sort_keys=True` 重新编码，内容相同的 payload 预览相同；
- 任意深度下，键名命中 `is_credential_key()` 的值替换为 `REDACTED = "[redacted]"`（键名归一化后以 `CREDENTIAL_KEY_FAMILIES` 中某项结尾即命中，如 `github_token`、`Proxy-Authorization`，但不含 `max_tokens`）；
- 控制字符、格式字符、孤立代理项、行/段分隔符写成 `\uXXXX`，结果不含换行和终端转义序列；
- 超过 `MAX_PREVIEW_CHARS = 1000` 截断并注明总长；无法解析为 JSON 时只报告长度、不回显内容。

## 7. 工具上下文通道（`omicsclaw/tools/context.py`）

`execute(arguments)` 只有一个参数，工具要"问人"或"报进度"时，通过 `contextvars` 找到调用方，而不是加宽已发布的 Protocol。

| 通道 | 由谁绑定 | 由谁读取 | 未绑定时 |
|---|---|---|---|
| `ToolContext.approval`（`ApprovalChannel`） | Surface（CLI / Desktop / Channel），回合开始前 | 工具内的 `require_approval` | **失败关闭**：抛 `ApprovalUnavailable` |
| `ToolContext.progress`（`ProgressSink`） | Surface | `report_progress` | 空操作，返回 `False`；sink 抛异常也返回 `False` |
| `ToolContext.values` | Surface | `context_value(key, default)` | 返回 `default` |
| effective policy | `ToolRegistry.execute`，每次调用 | `require_approval` | `None`，回退到工具自带策略 |
| `TimeoutPause` | 引擎 → 注册表 `use_timeout_pause` | `pause_tool_timeout()` | 不暂停 |
| `ask_every_time` | 权限门，在决定询问的那次调用周围 | `require_approval` 写入 `ApprovalRequest.ask_every_time` | `False` |

绑定入口：`use_tool_context(approval=, progress=, values=)`（作用域式，**替换而非合并**，防止一个会话的审批通道回答另一个会话的问题）；`set_tool_context` / `reset_tool_context`（适合独占一个 Task 的会话 worker）。`ToolContext.values` 在构造时被复制并封装为只读 `MappingProxyType`。

`values` 中最重要的键是 `WORKSPACE_KEY = "workspace"`（定义在 `_workspace.py`）：文件工具在构造时没拿到 `Workspace` 时按调用读取它。

### 7.1 `require_approval`

```python
async def require_approval(tool_name, arguments="{}", *, policy=None, reason="") -> ApprovalDecision
```

1. 解析生效策略：`effective_policy()` → `policy` 参数 → `ToolPolicy()`；
2. `approval_mode is AUTO` → 直接批准；
3. 未绑定审批通道 → 抛 `ApprovalUnavailable`（`ApprovalDenied` 的子类，便于区分"人说不"和"部署忘了绑通道"）；
4. 在 `pause_tool_timeout()` 内调用通道，传入 `ApprovalRequest(tool_name, arguments, reason, risk_level, approval_mode, ask_every_time)`；
5. 通道可返回 `ApprovalDecision`、`bool` 或其 awaitable；返回 `None` 视为拒绝，其他类型抛 `TypeError`；
6. 未批准 → 抛 `ApprovalDenied`，注册表转成 `is_error` Observation。

`DENY_UNLESS_TRUSTED` 与 `ASK` 一样交给通道裁决。

### 7.2 为何能工作：每个调用一个 Task

`engine/executor.py` 为每个调用创建一个 `asyncio.Task`，而 `Task.__init__` 调用 `contextvars.copy_context()`，于是每个 worker 都在"调度那一刻的上下文副本"上运行。会破坏这个性质的只有两种写法：把调用内联 await 而不放进 Task；或给多个 Task 传同一个共享 `context=`。`asyncio.TaskGroup` 与 `asyncio.gather` 都不会破坏它。`tests/tools/test_context.py` 通过真实的 `execute_tool_calls` 断言这一点。

## 8. 并发执行模型

### 8.1 引擎侧 Protocol（`omicsclaw/engine/executor.py`）

| Protocol | 方法 | 必需 | 作用 |
|---|---|---|---|
| `ToolExecutor` | `available_tools()`, `execute(call)` | 是 | 最小接缝，不含任何策略 |
| `ConcurrencyAwareExecutor` | `is_concurrency_safe(name)` | 否 | 启用写屏障 |
| `DeadlineAwareExecutor` | `use_timeout_pause(pause)` | 否 | 启用审批期间暂停计时 |

两个可选 Protocol 都是 `runtime_checkable`，引擎用 `isinstance` 判断。因此 `build_registry` 把 `ToolRegistry` **原样**交给 `AgentEngine`：任何包装层如果不转发这两个方法，不会报错，只会悄悄失去屏障或暂停（后者即缺陷 R3 复发：人的思考时间又被算进工具超时）。

### 8.2 `execute_tool_calls`

```python
async def execute_tool_calls(executor, calls, config, results, turn=0) -> AsyncIterator[EngineEvent]
```

- **预分配槽位、按下标写入**：`slots = [None] * len(calls)`；结束时 `results.extend(slots)`，保证 `results[i]` 对应 `calls[i]`。`None` 表示该 worker 什么也没产出（如工具向我们抛了 `CancelledError`），执行器不替它编造 Observation。
- **事件由 worker 入队、主协程出队**：`TOOL_START` 在工具真正开始时就发出，不等兄弟调用；`TOOL_RESULT` 携带 `duration_s`（引擎侧计时）。
- **信号量**：`EngineConfig.max_concurrent_tools > 0` 时限制并发数，从不重排。
- **放弃即取消**：生成器被关闭时，取消所有在途 Task 并 `gather` 回收，没有孤儿任务。

### 8.3 写屏障：`_concurrency_groups`

```
calls:   read_file  read_file  write_file  read_file  web_fetch  bash
safe?    yes        yes        no          yes        yes        no
批次:    [0, 1]                [2]         [3, 4]                [5]
```

- `EngineConfig.serialize_unsafe_tools = True`（默认）且执行器实现了 `ConcurrencyAwareExecutor` 时，不安全调用单独成批（屏障），相邻的安全调用组成并行批；批次按调用顺序依次执行，一批排空后才启动下一批。
- 屏障关闭或执行器不支持时，整轮一个批次，行为与旧版一致。
- `is_concurrency_safe` 抛异常 → 按 `False` 处理（受保护默认）。
- 代价：一个阻塞在人工审批上的屏障调用，会挡住本轮之后所有批次。

内置工具的 `concurrency_safe` 声明见第 9 节表格。

### 8.4 单调用超时与审批暂停：`_execute`

- `EngineConfig.tool_timeout > 0` 时用 `asyncio.timeout(tool_timeout)` 包住单个调用（按调用计，不按回合），慢工具只变成一条失败 Observation，不影响兄弟调用。
- 在预算内通过 `_bound_timeout_pause` 把 `lambda: _paused(budget)` 交给执行器；`require_approval` 进入它时，`_paused` 用 `asyncio.Timeout.reschedule(None)` 摘掉截止时间，退出时恢复**剩余秒数**（不是原始绝对截止点）。
- 只有真正到期的那个预算才能宣称超时：`budget.expired()` 为真时报 `tool 'x' timed out after {timeout}s`；工具自身抛出的 `TimeoutError`（例如 `_websafety.py` 的 socket 超时）按普通异常报告，保留原文。
- 注册表之外的执行器若违约抛异常，`_execute` 也会兜底转为 `is_error` Observation；`CancelledError` 不捕获。

暂停只停表，不限定等待时长：发出审批卡片的 Surface 必须自己为提示设定期限（`AppConfig` 的 `OMICSCLAW_APPROVAL_TIMEOUT_S` 即为此存在）。消费 `execute_tool_calls` 的一方也必须能在事件之间处理审批请求（独立 Task 或在 `async for` 体内 await 请求队列），只在事件间轮询会死锁。

### 8.5 补全与投影

`engine/loop.py` 的 `_answer_every_call(calls, results)` 按位置配对（不按 `tool_call_id`，因为 id 可能为空或被代理改写），把 `None` 槽位补成失败 Observation —— Anthropic 要求每个 `tool_use` 在下一条消息里都有 `tool_result`。随后 `observations()` 调 `ToolResult.to_message()`，空内容替换为 `EngineConfig.empty_output_placeholder`（默认 `"[tool completed with no output]"`）。

### 8.6 跨回合的第二道防线：路径锁

屏障只能排序**一个回合**内的调用。两个 Channel 会话、子 agent、后台运行各自驱动自己的 `execute_tool_calls`，操作同一批文件；一个声明了安全但实际不安全的工具、一个在内部扇出写入的工具，屏障也看不见。这些由 `omicsclaw/tools/_pathlock.py` 负责：

- 进程级唯一表 `PATH_LOCKS = PathLockTable()`，经 `read_lock(path)` / `write_lock(path)` 使用；
- 键是 `Path(path).resolve()` 后的真实路径，别名与符号链接归并为同一把锁；
- 基于 `asyncio.Condition` 的读写锁，**写者优先**，不可重入；
- 引用计数覆盖等待期，最后一个持有者离开即删除条目；
- 不用 `threading.Lock`：在事件循环里它既不能保证 await 之间的原子性，又会阻塞事件循环本身。

`read_file` 持读锁；`write_file` 在审批**之后**才拿写锁；`edit_file` 读时持读锁、审批后在写锁内重读并写入。文件系统细节见 `file-system.md`。

## 9. 已实现的工具

以 `omicsclaw/entry/assembly.py` 的 `foundation_tools()` 与 `build_app()` 为准，默认部署的注册顺序如下：

| # | 工具名 | 实现 | 挂载条件 | 风险 / 审批 | 并发安全 |
|---|---|---|---|---|---|
| 1 | `read_file` | `tools/builtin/read.py` `read_tool()`（FunctionTool） | 总是 | LOW / AUTO，`read_only` | 是 |
| 2 | `write_file` | `tools/builtin/write.py` `WriteTool` | 总是 | HIGH / ASK，`prompts_for_itself` | 否 |
| 3 | `edit_file` | `tools/builtin/edit.py` `EditTool` | 总是 | HIGH / ASK，`prompts_for_itself` | 否 |
| 4 | `bash` | `tools/builtin/bash.py` `BashTool` | 总是 | HIGH / ASK，`prompts_for_itself`；沙箱无网络且 `sandbox_auto_approve` 时改 AUTO | 否 |
| 5 | `web_fetch` | `tools/builtin/web_fetch.py` `WebFetchTool` | 总是 | HIGH / ASK，`touches_network` | 是 |
| 6 | `web_search` | `tools/builtin/web_search.py` `WebSearchTool` | 总是 | MEDIUM / ASK，`touches_network` | 是 |
| 7 | `use_skill` | `skills/use_skill.py` `use_skill_tool()` | `skills_index` 不为 `off` | LOW / AUTO，`read_only` | 是 |
| 8 | `plan_write` | `planning/tool.py` `plan_write_tool()` | `planning` 开启 | LOW / AUTO | 否 |
| 9 | `memory_search` | `entry/memory.py` `memory_search_tool()` | `memory` 开启 | LOW / AUTO | 是 |
| 10 | `memory_write` | `entry/memory.py` `memory_write_tool()` | `memory` 开启 | LOW / AUTO | 否 |
| 11 | `mcp__{server}__{tool}` | `tools/mcp_tool.py` `MCPTool`，由 `MCPManager.tools()` 提供 | `.mcp.json` 中有已连接的服务器 | HIGH / ASK | 否（默认） |
| 12 | `task` | `subagent/task_tool.py` `TaskTool` | `subagents` 开启 | HIGH / AUTO | 否 |

说明：

- 四个文件/Shell 工具共享 `foundation_tools()` 中**唯一一次**构造的 `Workspace(config.workspace)`，保证 `write_file` 写的文件 `read_file` 一定能读到；两个 web 工具不接收 workspace。
- 所有工具（包括调用方自带的和每个 MCP 工具）先经 `hook_tools(mounted, chain)` 包成 `HookedTool`，再经 `gate_tools(mounted, gate)` 包成 `GatedTool`，然后才进注册表。`task` 最后单独注册，同样经过 hook 链与权限门。
- `_apply_bash_policy` 在注册后按 `entry/sandbox.py` 的 `bash_policy()` 结果用 `registry.replace()` 重新登记 `bash` 的策略，并且替换进去的是**门控后的包装对象**；`_is_bash` 会逐层剥开 `GatedTool` / `HookedTool` 识别内层 `BashTool`。
- `plan_write` 若未实际挂载，`build_app` 会把 `plans` 置空，保证提示词不会指示模型调用不存在的工具。

### 9.1 各内置工具要点

| 工具 | 参数 | 关键常量 / 行为 |
|---|---|---|
| `read_file` | `path`, `start_line`, `end_line`, `offset`, `limit` | 行模式最多 `MAX_LINES = 500` 行，行前缀 `%6d\t`；字节模式默认 `MAX_READ_BYTES = 8192`，上限 `MAX_LIMIT_BYTES = 100_000`；单行上限 `MAX_LINE_CHARS = 512 KiB` |
| `write_file` | `path`, `content` | 覆盖写；自动建父目录（`DIRECTORY_MODE = 0o755`），新文件 `FILE_MODE = 0o644`；返回 `Wrote ...` / `Replaced ...` |
| `edit_file` | `path`, `source_text`, `target_text` | 四级匹配 L1 精确 → L2 忽略换行符 → L3 忽略首尾空白 → L4 忽略缩进，每级唯一性校验；审批展示 diff |
| `bash` | `command`, `timeout_secs` | `bash -c`，输出写临时文件而非管道；超过 `MAX_OUTPUT_CHARS = 16_000` 字符保留头 1/3、尾 2/3；非零退出码**不是** `is_error` |
| `web_fetch` | `url`, `max_chars` | `_websafety.py` SSRF 闸门（仅 http/https、拒绝 userinfo、DNS 失败即拒、检查所有解析地址、socket 钉在已校验地址）；`FETCH_TIMEOUT = 15.0`，`MAX_REDIRECTS = 5`，响应体上限 `MAX_BODY_BYTES = 1 MiB`，正文默认 `DEFAULT_MAX_CHARS = 8_000`、上限 `HARD_MAX_CHARS = 32_000` |
| `web_search` | `query`, `max_results` | 端点 `SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"`，`SEARCH_TIMEOUT = 20.0`，结果默认 `DEFAULT_RESULTS = 5`、最多 `MAX_RESULTS = 10` |

`bash` 的超时由部署决定：`AppConfig.tool_timeout_s` 默认 `600.0`，同时派生引擎的 `EngineConfig.tool_timeout`（`engine_config()`）与 `bash` 的构造超时（`bash_timeout()` = `tool_timeout_s - ENGINE_TIMEOUT_MARGIN`，即默认 585 秒），让引擎的截止时间始终留出 15 秒余量。环境变量 `OMICSCLAW_TOOL_TIMEOUT_S` 可调；非法值直接报 `AppConfigError` 而不是回退默认值。独立构造 `BashTool()` 时默认 `DEFAULT_TIMEOUT = 45.0`（对应 `EngineConfig` 自身默认的 60 秒）。

典型用例：模型执行 `python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/preprocess_demo`，命令非零退出时模型收到的是带退出码的普通 Observation，据此修正参数重跑；而 `timeout_secs=0`、空命令这类参数错误才是 `is_error`。判定标准统一为 **"模型下一步应当改什么"**。

### 9.2 `bash` 的边界

`bash` 没有路径参数，也不做路径检查 —— 对一整门编程语言做路径校验只是安全表演。它的边界是审批门（`ASK`）、权限层的危险命令模式与规则文件，以及可选的 Docker 沙箱（`BashTool` 的 `environment` 参数接收一个 `BashEnvironment`，由 `entry/sandbox.py` 提供）。只有 `bash` 被路由进容器；文件工具仍在宿主机上受 `Workspace` 约束，沙箱把工作区挂载到相同路径。

## 10. 与 hooks、权限门的接缝

- 注册表的 `execute` 在 `try` 之内只调用工具；hook 与权限门都以**装饰工具**的方式存在（`HookedTool`、`GatedTool`），而不是包装注册表 —— 这正是为了不破坏两个可选 Protocol 的 `isinstance` 检查。
- 链的顺序为 `GatedTool(HookedTool(tool))`：权限先裁决，被规则拒绝的调用根本到不了 hook。
- `GatedTool` 透传内层的 `name`、`definition()` 与 `policy`；对 `allow` 的调用以已定的策略运行，使工具内部的 `require_approval` 立即返回，避免同一调用被问两次；对 `prompts_for_itself=True` 的工具，询问交给工具本身（带 diff、完整命令或 URL），并在 `ask_every_time()` 作用域内进行。
- `ToolHook` 提供 `before_execute(call) -> HookDecision`、`after_execute(call, output) -> str`、`on_failure(call, error)` 三个钩子；当前唯一的配置型 hook 是 `AuditHook`（`OMICSCLAW_AUDIT_LOG` 设置时挂载，只记录参数摘要），以及可观测性开启时的 tracing hook。

## 11. 扩展指南：新增一个工具

### 11.1 简单工具：用 FunctionTool

```python
from omicsclaw.tools import FunctionTool, ToolPolicy, RiskLevel, ApprovalMode
from omicsclaw.tools.function_tool import ToolArgumentError

SCHEMA = {
    "type": "object",
    "properties": {"accession": {"type": "string"}},
    "required": ["accession"],
    "additionalProperties": False,   # 让多余参数变成可纠正的 schema 错误
}

async def lookup(accession: str) -> dict:
    if not accession.startswith("GSE"):
        raise ToolArgumentError("input.accession must be a GEO series id like GSE12345")
    ...

geo_tool = FunctionTool(
    "geo_lookup", "Look up a GEO series ...", lookup,
    parameters=SCHEMA,
    policy=ToolPolicy(risk_level=RiskLevel.LOW, approval_mode=ApprovalMode.AUTO,
                      read_only=True, concurrency_safe=True),
)
```

### 11.2 需要审批且提示必须忠于原始字节：手写 Tool

参照 `WriteTool` 的形状：`policy` 为类属性；构造时建好 `ToolDefinition` 并深拷贝 schema；`execute(arguments)` 中依次 `decode_arguments` → `validate_arguments` → 解析路径 → `await require_approval(self.name, arguments, policy=self.policy, reason=...)` → 在 `write_lock` 内执行副作用。只捕获 `OSError` 等具体异常，让 `CancelledError` 穿透。若声明 `prompts_for_itself=True`，必须真的调用 `require_approval`（`tests/permission/test_foundation_tools_keep_their_prompts.py` 会检查）。

### 11.3 挂载

工具只在组合根挂载。三种方式：

1. 修改 `foundation_tools()`，**追加在末尾**（保持前缀缓存稳定）；
2. 调用 `build_app(config, tools=[...])` 传入完整列表（测试、子 agent、迁移时使用）；
3. 通过 `.mcp.json` 接入 MCP 服务器。

无论哪种方式，工具都会经过 hook 链和权限门；不要在别处另建注册表。策略声明要显式写出：不写就得到 `HIGH` + `ASK`，而无人绑定审批通道时（脚本、测试）就会失败关闭。部署方想调整某个工具的策略，用 `registry.register(tool, policy)` 或 `replace`，不要给工具加构造参数。

## 12. 关键设计决策

1. **`arguments` 保持原始字符串**：字节级 payload 是前缀缓存和审批展示的依据，先解码再编码会改变键序。
2. **失败即异常，注册表统一转成 `is_error`**：工具作者不需要知道 `ToolResult` 的存在；`is_error` 让模型看到错误并自纠。
3. **策略与定义分离**：模型看见自己的审批规则，就会与规则争辩。
4. **受保护的默认值**：一个没有声明的工具不是安全工具的证据（计划 0028 §4 Q5）。
5. **写屏障在调度器，路径锁在工具**：前者排序一个回合，后者覆盖跨回合与工具内部的并发，二者互补而非替代。
6. **审批期间暂停计时**：人的思考时间不是工具运行时间；报告成 "timed out" 会误导模型去优化工具。
7. **按位置配对结果**：`tool_call_id` 可能为空或被改写，位置是下游无法破坏的对应关系。

参考：`docs/plans/0028-tool-registry.md`、`docs/plans/0029-foundation-tools.md`、`docs/FRAMEWORK-REBUILD.md` 的 Step 4、Step 4.5 与 "Parallel tool calling — the barrier and the pause" 两节。

## 13. 已知限制

- **`ToolPolicy.tags` 的 docstring 仍承诺"surface gating 将落在这里"**，与上述裁决矛盾；标签目前实际用于 MCP 标记等，不存在按标签过滤的机制。
- **`bash` 的 `timeout_secs` 只能缩短**：`BashTool.max_timeout` 返回 `self.timeout`。在默认部署中构造超时已是 585 秒，所以影响有限；但 `TimeoutPause` 不带参数，无法表达"给我更多时间"。
- **审批在 `EngineEventType` 中没有对应事件**（六个成员，无 `approval_required`），Surface 无法从事件流得知正在问人，消费方契约只能以文字约定。
- **屏障调用阻塞后续批次**：一个等待人工审批的不安全调用会挡住本轮其后所有批次；暂停状态下该调用在引擎侧没有上限，期限由 Surface 自己的审批超时承担。
- **并列的两次暂停**：同一调用内并行打开两个 pause 时，先开的那个负责恢复，另一个剩余等待会被计时；目前没有工具这样做。
- **`require_approval` 每次调用都会询问**：它自身没有"至多问一次"机制；门控工具靠 `GatedTool` 的"已定策略"规避，自行嵌套多层 `require_approval` 的包装工具会问两次。
- **`FunctionTool` 看不到原始 payload**，不能用于需要字节级忠实审批提示的工具。
- **`validate_arguments` 覆盖面有限**：组合关键字、`$ref`、数值与字符串边界都不检查，需要时由工具在函数体内自行校验。
- **`except OSError` 会连带捕获 `TimeoutError`**（`read` / `write` / `edit` / `bash` 通用约定）：注入的 `Environment` 若用 `asyncio.wait_for` 限时，基础设施超时会被报告成"换一个路径"。
- **`edit_file` 没有 `replace_all`**：N 处完全相同的行需要全部修改时无法消歧，只能退回 `write_file` 重写整个文件。
- **web 工具从未访问真实 HTTP 端点**：测试全部使用注入的 transport 或假 opener。`test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget` 与 `test_bash.py` 相邻运行时偶发失败，属已知的顺序敏感问题。
- **`_html.py` 不做 readability 式正文抽取**，只按固定标签列表去除样板，新闻类页面噪声较多。
- **`ENGINE_TIMEOUT_MARGIN` 的 docstring 仍按审批暂停修复之前的情形叙述**（"审批时间 + 命令时间 ≤ 60s"）；暂停机制落地后，审批时间已不计入工具超时。
- **Desktop Surface 未移植 `/chat/permission`**：在 Desktop 上需要审批的工具会一直等到超时。
- **多个模块 docstring 仍引用已删除的旧层**（如 `omicsclaw/runtime/tools/...`、`omicsclaw/skill/registry.py`、`builtin/gene_panel.py`）作为对照，这些只是历史记录，不代表当前可导入的代码。

## 14. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/schema/message.py` | `ToolCall`、`ToolResult`、`ToolDefinition`、`Role` |
| `omicsclaw/tools/__init__.py` | 公开 API 汇总 |
| `omicsclaw/tools/base.py` | `Tool` Protocol、`ToolPolicy`、`RiskLevel`、`ApprovalMode` |
| `omicsclaw/tools/registry.py` | `ToolRegistry` 与注册错误类型 |
| `omicsclaw/tools/function_tool.py` | `FunctionTool`、`ToolArgumentError`、`decode_arguments`、`validate_arguments`、`as_text` |
| `omicsclaw/tools/mcp_tool.py` | `MCPTool`、`mcp_tool_name`、`sanitize_mcp_name` |
| `omicsclaw/tools/context.py` | `ToolContext`、`require_approval`、`report_progress`、`pause_tool_timeout` 等上下文通道 |
| `omicsclaw/tools/preview.py` | `preview_arguments`、`is_credential_key` |
| `omicsclaw/tools/_workspace.py` | `Workspace` 路径沙箱 |
| `omicsclaw/tools/_pathlock.py` | `PATH_LOCKS`、`read_lock`、`write_lock` |
| `omicsclaw/tools/_websafety.py` / `_html.py` | web 工具的 SSRF 闸门与 HTML 精简 |
| `omicsclaw/tools/builtin/` | `read.py`、`write.py`、`edit.py`、`bash.py`、`web_fetch.py`、`web_search.py` |
| `omicsclaw/engine/executor.py` | `ToolExecutor` 等三个 Protocol、`execute_tool_calls`、`observations`、写屏障与超时暂停 |
| `omicsclaw/engine/config.py` | `EngineConfig`：`tool_timeout`、`max_concurrent_tools`、`serialize_unsafe_tools`、`empty_output_placeholder` |
| `omicsclaw/engine/loop.py` | `_answer_every_call`，工具执行在主循环中的位置 |
| `omicsclaw/entry/assembly.py` | `foundation_tools`、`build_registry`、`build_app`、`_apply_bash_policy` |
| `omicsclaw/entry/config.py` | `AppConfig.tool_timeout_s`、`bash_timeout()`、`engine_config()` |
| `omicsclaw/skills/use_skill.py` / `planning/tool.py` / `entry/memory.py` / `subagent/task_tool.py` | entry 层注册的 `use_skill`、`plan_write`、`memory_*`、`task` |
| `omicsclaw/permission/gate.py` / `omicsclaw/hooks/chain.py` | `GatedTool` / `gate_tools`、`HookedTool` / `hook_tools` |
| `tests/tools/` | 注册表、适配器、上下文、各内置工具、路径锁、分层约束测试 |
| `tests/engine/test_executor.py` | 调度、屏障、超时暂停测试 |
