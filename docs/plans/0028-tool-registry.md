# 计划 0028 — Tool Registry（工具注册表）

框架分阶段重建的第 4 步（见 `docs/FRAMEWORK-REBUILD.md`）。第 1 步
（`omicsclaw/schema/`，ADR 0077）、第 2 步（`omicsclaw/provider/`，计划
0026）、第 3 步（`omicsclaw/engine/`，计划 0027）已交付；本步写引擎的
「双手」。

状态：**已交付**（2026-09-18）。经两个独立只读评估把关，查实的缺陷已修复
并复验。`tests/tools/` 315 passed，四目录合计 950 passed，纯 additive。
结果与教训见**附录 B**。

### owner 的三条批复（2026-09-17）

1. **范围照批。** 约 1,040 行，注册表 + 适配器 + 2–3 个参考工具，不迁移
   既有的 50 个工具。任务序列因此是 **A → B → C → D**。
2. **Task 0（驱逐）取消。** 旧工具层留在 `omicsclaw/runtime/tools/`，边界
   改由分层测试强制。理由与新约束见 Q7。
3. **§5 判给装配层的四项能力（Surface 门控、predicate 门控、每会话冻结
   工具列表、按阶段裁剪子集）去留未决**，owner 未作答。**这不阻塞本步**
   ——无论保留还是废弃，本步都不实现它们中的任何一项，注册表只负责
   「全集有序」。此项原样结转为第 5 步的待决事项，见 §11。

## 1. 目标

一个集线器，把工具的**注册**、**描述暴露**与**路由分发执行**三件事收在
一处，并让引擎在完全不认识任何具体工具的前提下使用它们。

```python
from omicsclaw.tools import ToolRegistry, FunctionTool

registry = ToolRegistry()
registry.register(InspectDataTool(workspace))       # 动态挂载
defs = registry.available_tools()                    # 描述暴露 → Provider
result = await registry.execute(call)                # 路由分发 → ToolResult
```

第 3 步已经替本步把接口定死了。`omicsclaw/engine/executor.py` 里那个
Protocol 就是本步必须满足的契约，而且要**结构化满足——不 import
`omicsclaw.engine`**：

```python
@runtime_checkable
class ToolExecutor(Protocol):
    def available_tools(self) -> Sequence[ToolDefinition]: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

### 本步真正要解决的问题：内聚

这不是「把旧代码搬个地方」。现状与 harness9 的差别是结构性的：

**harness9 —— 一个工具就是一个对象**，自己持有名字、自己的 JSON Schema、
自己的执行逻辑（`base.go` 的 `BaseTool` 三个方法）。要加工具就新建一个
文件，然后 `registry.Register(tool)`。

**现状 —— 一个工具的身份被拆成三处**：`ToolSpec`（`spec.py`，只有元数据，
没有执行）躺在一个元组里；真正的 callable 躺在另一个 `dict[str, Callable]`
里；两者靠 `spec.executor_name` 这个**字符串**在启动时按名匹配
（`executor.py:build_executor_map`，匹配不上就抛 `KeyError`）。于是：

- 改一个工具的参数，要同时改 spec 和 executor 两个地方，而且编译期没有
  任何东西保证它们一致；
- 「这个工具到底干什么」这个问题，没有任何**一个**地方能回答；
- `builders/` 三个文件 6,105 行，是 50 个工具的 spec 与 executor 被硬塞在
  一起的结果，而不是 50 个各自内聚的工具。

本步把工具变回一个对象。

### 非目标

- **不接线。** 与第 1、2、3 步一致：交付后没有任何生产调用方。旧工具层
  继续原样服务所有 Surface。
- **不迁移那 50 个既有工具。** 本步交付注册表、抽象与适配器，外加 2–3 个
  参考实现。逐个迁移是后续步骤，而且必须逐个验证——见 §11。
- **不实现沙箱 / 路径安全。** harness9 的 `safe_path.go`、`path_locker.go`
  是具体工具的依赖，不是注册表的。本项目已有
  `omicsclaw/services/path_validation.py`。
- **不做审批 UI、不做权限模式。** 本步只提供带外通道（Q5）与策略载体
  （Q6），谁来弹框是 Surface 的事。
- **不碰 `omicsclaw/providers/`（复数）。** 计划 0026 §10 仍然开着。

## 2. 接口

### harness9 的形状

```go
// base.go — 一个工具必须长成什么样
type BaseTool interface {
    Name() string
    Definition() schema.ToolDefinition
    Execute(ctx context.Context, args json.RawMessage) (string, error)
}

// registry.go — 注册表
type Registry interface {
    Register(tool BaseTool) error
    GetAvailableTools() []schema.ToolDefinition
    Execute(ctx context.Context, call schema.ToolCall) schema.ToolResult
}
```

核心只有 152 行（`base.go` 28 + `registry.go` 124）。其余 2,200 余行全是
**具体工具**。这个比例本身就是设计意图：注册表应当薄到没有可出错的余地。

### 建议的 Python 形态

```python
@runtime_checkable
class Tool(Protocol):
    """一个工具：自己的名字、自己的描述、自己的执行。"""

    @property
    def name(self) -> str: ...

    def definition(self) -> ToolDefinition: ...

    async def execute(self, arguments: str) -> str: ...


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """工具的本地执行策略 —— 绝不进入 prompt。"""
    risk_level: RiskLevel = RiskLevel.HIGH        # 见下方勘误
    approval_mode: ApprovalMode = ApprovalMode.ASK
    read_only: bool = False
    concurrency_safe: bool = False
    writes_workspace: bool = False
    writes_config: bool = False
    touches_network: bool = False
    allowed_in_background: bool = False
    tags: frozenset[str] = frozenset()


class ToolRegistry:
    def register(self, tool: Tool, policy: ToolPolicy | None = None) -> None: ...
    def unregister(self, name: str) -> None: ...
    def get(self, name: str) -> Tool | None: ...
    def policy_for(self, name: str) -> ToolPolicy: ...
    def available_tools(self) -> tuple[ToolDefinition, ...]: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

`ToolRegistry` 同时满足第 3 步的 `ToolExecutor`（`available_tools` +
`execute`），结构化，不 import engine。

> **勘误（Task A 交付时修正）。** 上面这段草图原先写的是
> `risk_level=LOW`、`approval_mode=AUTO`、`concurrency_safe=True`——
> 恰恰是**最方便**的那一组，而 Q5 逐字要求相反（「`ToolPolicy()` 的默认
> 必须是最保守而非最方便的那一组」），且要求 Q5 表第 4 行必须有测试。
> 照草图写会让那个测试变成空转：它会去断言「一个空白策略授予一切权限」。
>
> 而且草图与它自己引用的证据也矛盾：它声称承接旧 `ToolSpec` 的字段，但
> `omicsclaw/runtime/tools/spec.py:38` 的 `concurrency_safe` 默认就是
> `False`。草图另外漏了 `writes_config` 与 `allowed_in_background`——
> §5 的能力表判给了 `ToolPolicy`，以 §5 为准。
>
> **实现已按 Q5 交付**，并在 `ToolPolicy` docstring 里把字段分成两类：
> **权限**（`risk_level` / `approval_mode` / `concurrency_safe` /
> `allowed_in_background`，一律默认到设防值）与**声明**
> （`read_only` / `writes_workspace` / `writes_config` /
> `touches_network`，默认到「未作声明」）。这里有一个如实记下而非粉饰的
> 残留空洞：**门控不得凭一个没人写过的 `False` 放行**——
> `touches_network=False` 与「这个工具压根没声明过」长得一模一样。所以
> `approval_mode` 是权威的，那四个声明字段只是参考。

### 三处对 harness9 的偏离，每处都有原因

**`execute` 返回 `str` 而不是 `(str, error)`。** Go 用多返回值表达失败，
Python 用异常。工具抛异常，注册表捕获并封装成 `is_error=True` 的
`ToolResult`——这与第 3 步 `engine/executor.py` 里对「会抛异常的
executor」的兜底是同一条纪律，只是移到了正确的位置。

**没有 `ctx` 参数。** 与第 3 步 §2 同理，取消在 Python 里是环境自带的。
Go 的 ctx 还携带**值**（审批回调、子代理进度），那一半由 Q5 的
`contextvars` 承接——这正是第 3 步遗留下来、`FRAMEWORK-REBUILD.md`
点名要在本步决定的那件事。

**`policy` 不在 `Tool` Protocol 上。** harness9 没有这个概念（它把权限
模式放在 engine 上）。本项目有一套成熟的策略元数据必须保住（§5），但
它绝不能出现在 `definition()` 里。做法是注册时旁挂，由注册表持有——
见 Q6。

## 3. 文件

```
omicsclaw/tools/
├── __init__.py          ~50   公开接口面
├── base.py             ~130   Tool Protocol + ToolPolicy + RiskLevel/ApprovalMode
├── registry.py         ~200   ToolRegistry —— 注册、暴露、分发
├── function_tool.py    ~160   FunctionTool：包装普通 callable + JSON Schema
├── mcp_tool.py         ~110   MCPTool：把 MCP 工具包装成原生 Tool
├── context.py          ~120   带外通道的 contextvars 约定（审批 / 进度）
└── builtin/
    ├── __init__.py      ~20
    └── <2-3 个参考工具>  ~250
                        ~1,040
tests/tools/
├── test_base.py                Protocol 一致性、policy 不泄漏进 definition
├── test_registry.py            注册冲突、未知工具、异常兜底、顺序确定性
├── test_registry_is_a_tool_executor.py   结构化满足 engine 的 ToolExecutor
├── test_function_tool.py       参数解析、校验失败的可修正错误
├── test_mcp_tool.py            命名消毒、schema 透传
├── test_context.py             contextvars 在 ensure_future 下的传播
├── test_builtin_tools.py
└── test_tools_is_a_leaf_layer.py   AST 分层守卫
```

`omicsclaw/tools/` 经查**当前空闲**（2026-09-17 复核，`tests/tools/` 同）。
无网络、无厂商 SDK；工具全部由本地 fake 驱动。

> **行数预算偏低约 3×，据 A、B 两次实测修正。** 原稿 / 实际：
> `base.py` 130→**221**、`registry.py` 200→**368**、`__init__.py`
> 50→**102**、`context.py` 120→**408**、`function_tool.py` 160→**414**、
> `mcp_tool.py` 110→**345**。生产代码合计 **770 → 1,858**。
>
> 差额几乎全是 docstring，而这不是注水——`schema/`、`provider/`、
> `engine/` 一律用模块级与成员级 docstring 解释「为什么是这个形状」，
> 本步要求与它们风格一致。中途按 Task A 实测把系数定为 1.7× 仍然不够，
> 因为那是拿**原稿**乘出来的，而原稿本身就没把 Q4 五问、对拍取舍、命名
> 规则三处偏离这类「必须写下理由」的内容计入。**Task C/D 直接按原稿
> ×3 估。**
>
> **这不是范围扩大**：owner 批准的范围（不迁移那 50 个工具）一行没变，
> 交付的模块与文件清单也与 §3 完全一致。

## 4. 决策

**Q1 —— `Tool` 是 Protocol，不是基类。** 与 `LLMProvider`、`ToolExecutor`
一致：结构化满足，一个测试替身就是二十行、不 import 本模块。同时提供
`FunctionTool` 适配器包装普通 callable——那 50 个既有工具的 executor 都是
普通函数，让它们逐个变成手写类是没必要的仪式。

**Q2 —— `execute` 收原始 JSON 字符串，不收解析后的 dict。** 对齐
harness9 的 `json.RawMessage`，也对齐 `ToolCall.arguments` 自己的设计意图
（ADR 0077：「延迟反序列化……解析是具体工具的事，不是循环的事」）。
`FunctionTool` 在自己内部做一次解析 + 校验，所以便利性不丢。

**不传整个 `ToolCall`。** 工具不需要知道 `call.id`；传进去只会让某个工具
哪天开始依赖它，而 id 恰恰是第 3 步评估里出过事的那个字段。

**Q3 —— 工具列表顺序必须确定，这是本步反超 harness9 的地方。**
harness9 的 `GetAvailableTools` 在注释里明说「返回的列表顺序不固定（map
迭代顺序不确定）」——Go 的 map 迭代是**刻意随机化**的。照搬即错。

理由不在任何一份本项目的文档里，而在**厂商侧的计费事实**：OpenAI、
Anthropic、DeepSeek 的 prompt 前缀缓存都是按「从头开始逐字节相同的最长
前缀」命中的，而工具定义排在系统提示之后、对话之前——是前缀的一部分。
工具列表每轮换一次顺序，等于每轮把缓存断点推到工具段之前，后面所有内容
全部按 miss 计价。缓存命中的输入 token 通常是未命中的十分之一量级，所以
这是一个**一个字典遍历顺序决定的十倍成本差**。

这条与本项目现有的任何架构决策都无关，重构之后依然成立——它是
`provider` 层要对接的那些 API 的性质，不是本仓库的约定。

**而且不必依赖对厂商文档的转述：第 2 步已交付的代码就建立在这个前提
上。** `provider/openai_provider.py` 的 `apply_cache_breakpoints` 会调用
`_mark_last_tool`，把 `cache_control` 断点打在 **`tools[-1]`**——最后一个
工具定义上：

```python
def _mark_last_tool(tools):
    out = list(tools)
    out[-1] = {**out[-1], "cache_control": dict(_EPHEMERAL)}
    return out
```

它的 docstring 写着「Deterministic every turn, so the breakpoint itself
never churns the prefix it exists to cache」。这句话只在工具列表本身
逐轮稳定时才成立：顺序一抖，断点每轮落在**不同的工具**上，断点之前的
字节也每轮不同，于是第 2 步专门为 Anthropic 加的那次显式缓存写入**每轮
都作废**——而 Anthropic 是不加断点就完全不缓存的那个后端。

所以 Q3 不是一条关于外部世界的推测，而是**新架构内部已有的一个不变量**。
独立审核如实声明它无法在线核实厂商文档；这条证据把论证从「按厂商文档
应该如此」降级为「本仓库第 2 步的代码已经这样假设了」，后者是可以直接
读到的。

Python 的 dict 保序是免费的，但**免费不等于可以不写**：本步必须把
「`available_tools()` 返回注册顺序」写进 docstring、写进测试，并且用变异
验证（把实现换成 `sorted()` 或 `set` 遍历，测试必须变红）。这是从参照系
继承**行为**而非字面量的一次翻车预演——第 3 步的教训说「照搬字面量是
负债」，这一条说明**照搬行为同样是**。

**Q4 —— 带外通道：`contextvars`，且写成显式约定。**
`FRAMEWORK-REBUILD.md` 点名的第一条。harness9 经 ctx 向工具注入两样东西：
审批回调（`tools_exec.go:58-60`）与子代理进度 sink（`stream.go:203-205`）。
本项目第 3 步发布的缝是 `execute(call)`，没有 ctx。

两条路：改已发布的 Protocol（它还没有实现者，改得起），或用
`contextvars`。**选 contextvars**，因为第 3 步的
`engine/executor.py` 用 `asyncio.ensure_future` 创建 worker，而它会复制
当前 context——所以 Surface 设一个 contextvar，工具就读得到，**引擎一行
都不用改**。

这个前提已实测确认（协调者与独立审核各自读了
`engine/executor.py` 的 `ensure_future(run_one(...))`，未传 `context=`，
故拷贝当前 context；协调者另跑了一次三工具并发的实际验证）。

但它目前**成立于一个巧合**。本步必须把它变成契约：`context.py` 一个模块，
显式回答五问——

1. **装的是什么：一个引用，不是一个值。** contextvar 里放的是审批*回调*
   与进度 *sink*，不是审批结果。双向交互（工具阻塞等待人类点「同意」）
   由回调自身内部实现。**这一点已实测可行**：contextvar 携带一个 async
   callable，工具 `await ask(call)` 即可拿到回传，实测两个工具分别得到
   「已执行」与「被拒绝」。harness9 的 `ctx.Value` 也是同一个「传回调
   引用」模式，不是传值。
2. **谁设**：Surface（CLI / Desktop / Channel），在进入 agent turn 之前。
3. **谁读**：具体工具，在自己的 `execute()` 内部。注册表**不读**——它只是
   让通道存在，不参与审批语义。

   > ⚠️ **本条与 §5「生命周期 hooks」那一行互相矛盾，而 §5 是对的。**
   > §5 逐字预言过：「若落在单工具超时预算之内，人类审批的思考时间会被
   > 计进工具超时（harness9 `tools_exec.go:56-60` 专门为此用会话级 ctx
   > 而非 toolCtx）」。然后本条把审批放进了 `execute()` **里面**——而
   > `engine/executor.py::_execute` 正是用 `asyncio.timeout(tool_timeout)`
   > 包住 `executor.execute(call)` 的，默认 **60 秒**。
   >
   > 实测（协调者复现）：审批等待被计进预算，超时后模型收到
   > `"tool 'X' timed out after 60s"`——**一句事实上错误的话**（工具没有
   > 超时，是人没在 60 秒内点同意），而且模型会据此去「让它跑快一点」。
   > Telegram / Feishu 上这不是边缘情况。
   >
   > **正确的修法要动 `omicsclaw/engine/`**（让 `tool_timeout` 不覆盖
   > 审批等待，或给审批一份会话级预算），而那超出本步范围；`asyncio.shield`
   > 解决不了——外层 `asyncio.timeout` 仍会在 await 点抛。结转为债，见 §11。
   >
   > 教训本身比这个 bug 更值钱：**同一份计划的两处对同一件事给出了相反的
   > 安排，实现方照着其中一处做，于是撞上另一处已经预言过的事。** 计划里
   > 凡是「X 不能落在 Y 之内」这类约束，必须在**做安排的那一处**复述，
   > 而不是只写在论证它的那一处。
4. **没设时怎么办**：必须明确是 fail-closed（拒绝执行需审批的工具）还是
   静默放行。这是安全相关的，**不能留给实现者临场决定**。建议
   fail-closed：`approval_mode=ASK` 的工具在没有审批通道时返回
   `is_error` 结果并说明原因，而不是当作已批准。
5. **多会话会不会串**：Channel Surface 是多用户的（Telegram / Feishu
   各自的会话并发跑在同一个进程里）。contextvars 的隔离粒度是 asyncio
   Task，所以**每个顶层会话必须起自己的 Task**；若多个会话共享一个顶层
   任务再各自 `var.set()`，后设的会覆盖先设的，一个用户的审批回调会接到
   另一个用户的工具调用。这条必须有测试。

**第三个槽位：运行期值袋（Task B 交付时补入）。** 上面五问通篇只谈了
harness9 那两条通道（审批回调、进度 sink），但 §5 的 `context_params` 一行
把**一整袋平铺的运行期值**也判给了同一套 `contextvars`——而那一行正是
「否则 50 个工具全部迁不动」的那一行。严格照原稿的 Q4 做只会建两条通道，
`context_params` 就没有家。所以 `ToolContext` 有第三个成员 `values`。

实测该袋须覆盖 14 个键（AST 扫全仓库 `ToolSpec(context_params=...)` 得 13
个，加 `query_engine.py:906` 无条件注入的 `request_tool_approval`）：
`session_id / chat_id / surface / workspace / pipeline_workspace /
thread_id / policy_state / cancel_event / run_runtime /
candidate_chain_gate / model_override / provider_override /
tool_result_root / request_tool_approval`。**两处刻意的行为差异**已写进
docstring：`build_executor_kwargs` 会滤掉 `None` 让 executor 签名默认值
生效，新约定把默认值放在**读取处**；旧约定要求工具先声明想要哪些键、
漏声明就静默传空（`tests/test_executor_cancel_kwarg.py` 记过这类真实
bug），新约定取消声明这一步。

配套测试直接断言「在 `execute_tool_calls` 的并发 worker 里读得到调用方
设置的值」，而不是在同一个协程里读一次就算数。巧合不写下来就是下一次
事故。

**Q5 —— 策略元数据旁挂在注册表，不进 `Tool` Protocol，更不进
`definition()`。** `FRAMEWORK-REBUILD.md` 点名的第四条。

`ToolDefinition` 只有三个字段（name / description / input_schema），它的
docstring 明说排除本地执行策略是因为「那是工具层的事务，且绝不能序列化
进 prompt」。所以：

- `register(tool, policy=...)` 时旁挂，注册表用 `policy_for(name)` 提供；
- 工具实现**可以**自带一个 `policy` 属性作为默认值（高内聚：风险等级
  本就是工具自己的性质），注册时可覆盖（部署侧的事）；
- `available_tools()` 永远只吐 `ToolDefinition`。**一个测试必须断言
  `definition()` 的序列化结果里不含任何策略字段名**——这是防止它哪天
  顺着某个「顺手加上去」漏进 prompt 的唯一手段。

**这确实把真相源拆成了两处**，而那正是本步声称要消灭的毛病。独立审核
点出了这一点，判得对。保留双源的理由是二者语义不同——工具自带的是
**它本性上的风险**，注册时传的是**这次部署愿意承担的风险**，后者是部署
决策不是工具属性——但既然并存，优先级必须写死而不是靠直觉：

| `tool.policy` | `register(policy=)` | `policy_for(name)` 返回 |
|---|---|---|
| 有 | 有 | **`register` 的赢**（部署覆盖工具默认） |
| 有 | 无 | `tool.policy` |
| 无 | 有 | `register` 的 |
| 无 | 无 | `ToolPolicy()` 的字段默认值 |

四行全部要有测试，尤其是最后一行——`ToolPolicy()` 的默认必须是**最保守
而非最方便**的那一组，否则一个忘了声明策略的工具会静默获得最高权限。
`test_registry.py` 须点名覆盖这四个用例。

> **⚠️ 这张表原先只在 `policy_for()` 上成立，到不了做授权判断的那一行。**
> 三方独立命中：工具在自己的 `execute()` 里调
> `require_approval(..., policy=self.policy)` 传的是**作者的** policy，
> 而部署方经 `register(policy=...)` 的收紧没有任何途径抵达。实测：
> `policy_for` 答 `ask`，审批通道被问 **0** 次，不可逆操作照跑。
>
> **已修复，解析改为三级**（交付形态）：
>
> 1. **注册表发布的解析结果** —— `ToolRegistry.execute` 在
>    `use_effective_policy(self.policy_for(call.name))` 作用域内 await
>    工具，`require_approval` 优先读它。**这是权威来源。**
> 2. 调用方传入的 `policy=` —— 仅作 fallback，用于没有注册表参与的场景
>    （脚本直调工具）。
> 3. `ToolPolicy()` —— 即 `ASK`，fail-closed。
>
> 因此 `require_approval` 的 `policy=` 参数在挂载到注册表的工具上**大部分
> 时候会被忽略**。这是修复的必然代价，也是一个容易被误读的 API（作者会
> 以为自己在设置策略）。docstring 已用整段写明三级顺序；更干净的长期形态
> 可能是改名为 `fallback_policy=`，留给迁移那一步统一决定。
>
> 验收标准因此补了 §9-10：**解析结果必须在执行期真的生效，且要钉住收紧
> 方向。** 见附录 B「三条最贵的教训」第 1 条。

**Q6 —— 重复注册：抛异常，保留原有。** 对齐 harness9（返回 error 且
「原有工具保持不变」）。Python 里抛 `ToolAlreadyRegistered`。另提供显式的
`unregister()` 与 `replace()`，让「我就是要覆盖」成为一个需要说出口的
动作，而不是一次静默的赢家通吃。

**Q7 —— 不驱逐旧工具层。边界由分层测试强制，不由包名暗示。**
（owner 裁定，2026-09-17；原稿建议移到 `omicsclaw/legacy/tools/`，已推翻。）

旧层留在 `omicsclaw/runtime/tools/` 原地不动，本步一个既有文件都不碰。

裁定的依据是原稿自己交代的那笔账：本步与第 3 步的 task 0 有本质区别——
第 3 步的改名是**被迫**的，`omicsclaw/engine/` 那个名字不仅被占，在本环境
里根本导不进来；本步**没有名字冲突**，`omicsclaw/tools/` 空闲。所以移动
78 个文件的 import 买到的是一个**标签**，不是一次解锁。

而标签要买的那个东西——让新层里的误引用显形——有更便宜也更强的买法。
原稿把 AST 静态检查列为「可选项」，现在它是**唯一**的执行机制，因此升格为
必须项，并且要求收紧到比原稿更严：

> `test_tools_is_a_leaf_layer.py` 断言 `omicsclaw/tools/` 在 `omicsclaw`
> 命名空间内**只**导入 `omicsclaw.schema`。这一条同时挡住 `runtime.tools`、
> `omicsclaw.engine`、`omicsclaw.provider` 以及任何日后新增的包——是白名单
> 而非黑名单，所以不需要预见要禁哪些。用 AST 遍历，不用字符串 grep：
> `import omicsclaw.runtime.tools as t` 与 `from ..runtime import tools`
> 这两种写法 grep 都可能漏，AST 不会。

> ### ⚠️ 上面这段论证原先是不完整的（协调者的错，D1 评估指出后修正）
>
> 原稿——以及协调者向 owner 陈述这条建议时——写的是「AST 比 grep 更强」，
> 把两者当成了**包含**关系。**实际是互补盲区**：
>
> | 写法 | grep | AST（只遍历 `Import`/`ImportFrom`） |
> |---|---|---|
> | `from ..runtime import tools` | ❌ 漏 | ✅ 抓得到 |
> | `importlib.import_module("omicsclaw.runtime.tools.validation")` | ✅ 抓得到 | ❌ **漏** |
>
> 实测（协调者亲手复现）：把 `function_tool.py` 的 `validate_arguments`
> 函数体换成对 legacy `validation.py` 的**惰性委托**，`tests/tools/`
> **286 条全绿**——包括那条专门为了挡「其实是同一个实现」而写的对拍
> 守卫（它断言 `__module__`、`__file__` 与对象不同一，这三条对一个一行
> 委托 wrapper 全部成立）。
>
> **而 §5 明令禁止的恰恰就是复用那个模块**，计划自己还警告过「顺手
> import 一下复用看起来毫无异常」。Task 0 取消后这条测试是**唯一**的执行
> 机制，唯一 + 有盲区 = 一条无人看守的路——而且是迁移 50 个工具时最自然
> 会走的那条（「execute 里惰性 import，避免启动开销/循环依赖」）。
>
> **裁定不变（仍然取消 Task 0），但守卫必须补到两个方向**：
> (a) AST 增加 `ast.Call` 扫描，禁掉 `importlib.import_module` /
> `__import__`（这一层不需要动态 import，白名单为空即可）；
> (b) 增加 subprocess **行为**探针：真跑一遍代表性路径**之后**断言
> `sys.modules` 里没有任何 `omicsclaw.runtime*`——静态检查查的是写法，
> 行为探针查的是事实。
>
> 记在这里而不是只记在修复任务里，因为**第 5、6 步会照抄这条分层测试**
> （`context/`、`memory/` 各要一份），照抄的是哪一版决定了它们有没有
> 同一个洞。

相对「可 grep 的包名」，它的优势是**硬失败**：包名只挡得住人工审核，挡不住
CI 里的静默回归；而第 3 步的评估已经证明，并行分工下缺陷恰恰聚集在「谁都
没认领的边界」上——那正是最不该靠人眼盯的地方。

**顺带取消的代价**：`omicsclaw/legacy/` 这个命名空间不在本步建立。计划
0026 §10 的 `omicsclaw/providers/`（复数，2,426 行）与第 6 步的
`omicsclaw/memory/` 日后若要收编，各自决定去处。这是被接受的代价，不是
被遗忘的事项——记在 §11。

**Q8 —— 本步不迁移那 50 个工具。** 只交付注册表 + 适配器 + 2–3 个参考
实现。理由见 §11：迁移是**逐个语义验证**的活，跟建注册表是两种工作。

## 5. 现有能力的去向（本步最大的风险）

harness9 的工具层比本项目**简单得多**。它没有 Surface 概念、没有
per-request 门控、没有结果策略、没有生命周期 hooks。照着它重建，很容易
在「更干净」的名义下把这些能力悄悄丢掉。

> **前提已变（2026-09-17，owner）：整个项目将被重构，既有 ADR 不再作为
> 约束。** 所以下表**不是**一张「必须原样保住」的清单——`ToolSpec` 上的
> 若干字段很可能就不该活过重构。但「**决定不要**」和「**忘了要**」是
> 两件完全不同的事，而后者不会报错：一个静默消失的门控不会让任何测试变
> 红，只会在某天让一个本不该出现的工具出现在某个 Surface 上。
>
> 因此这张表的作用变成了**强制交代**：实现任务必须逐行给出去向，
> 「不需要了」是完全可接受的答案，但必须写出理由。留空视为缺陷。

| 现有能力 | 出处 | 本步处置（建议） |
|---|---|---|
| `name` / `description` / `parameters` | `spec.py` | → `Tool.definition()` |
| `executor_name` + `build_executor_map` | `executor.py` | **消失**——这正是本步要消灭的那道缝，执行逻辑回到工具对象内部 |
| `risk_level` / `approval_mode` | `spec.py` | → `ToolPolicy`（Q5） |
| `read_only` / `concurrency_safe` | `spec.py` | → `ToolPolicy` |
| `writes_workspace` / `writes_config` / `touches_network` / `allowed_in_background` | `spec.py` | → `ToolPolicy` |
| `policy_tags` | `spec.py` | → `ToolPolicy.tags` |
| `surfaces`（Surface 门控） | `spec.py` | **本步不做**——它是「哪个入口能看到这个工具」，属于装配层（第 5 步 `context/`）。注册表提供 `policy.tags`，由装配层过滤。**必须在计划里说清楚，否则就是丢功能** |
| `predicate`（per-request 门控，fail-closed） | `registry.py:select_tool_specs` | 同上，装配层。注册表不认识 request |
| 每会话冻结工具列表（前缀缓存） | `registry.py` | **顺序确定性由本步保证**（Q3，理由是厂商计费事实而非本仓库约定）。「一个会话内不再变动」这条策略属装配层 |
| 按生命周期阶段裁剪子集 | `registry.py:STAGE_TO_TOOL_SUBSETS` | 装配层——若重构后仍要这个概念。注册表只负责「全集有序」 |
| `input_validator` | `spec.py` | → **能力保留，槽位取消**（本行原写「→ `FunctionTool` 内部」，读起来像要在 `FunctionTool` 上重建一个 `input_validator=` 参数，那是错的方向）。理由有二：① 旧 `input_validator` 做**两件**事——自定义校验，**以及**经 `normalized_arguments` **改写参数**（`validation.py:40-47`），后者不是 schema 校验能承接的；② 这个槽位存在的**原因**就是 spec 与 executor 是两个对象、校验无处可放，而消灭这道缝正是本步的立意，照字面做等于把三分结构原样搬进新层。处置：被包装的函数自己校验、自己归一化、自己抛 `ToolArgumentError`，由注册表转成**可修正的** `is_error`（见陷阱 9 的措辞修正） |
| **共享 JSON Schema 校验**（`validate_arguments_against_schema`、`ToolInputValidationResult`、`normalize_input_validation_result`） | `runtime/tools/validation.py`（141 行） | **→ `function_tool.py` 独立重写，不可复用。** 这是本表原先的盲区。它做的事与陷阱 8/9 要求 `FunctionTool` 做的**逐字重合**，但 §9-4 的分层约束（`omicsclaw/tools/` 只许从 `omicsclaw` 导入 `omicsclaw.schema`）使它导不进来——Task 0 取消后这条约束更要紧了，因为旧层现在就叫 `runtime.tools`，「顺手 import 一下复用」看起来毫无异常。**取舍必须写明**：重写意味着校验语义可能与旧版 50 个工具不一致（`additionalProperties: false` 的处理、枚举失败的措辞等），因此实现任务须与 `validation.py` 的行为**对拍**，差异要么消除、要么写进 docstring |
| `speculative_classifier` | `spec.py` | **→ 装配层。** 消费者是 `runtime/tools/orchestration.py:271` `_classifier_policy_decision`：它能在执行**前**把 `risk_level`/`approval_mode` 升级为 DENY 或 REQUIRE_APPROVAL，且读取 `request.runtime_context` 里的 `surface`/`trusted`/`background`——正是陷阱 12 禁止注册表持有的东西 |
| `result_policy`（6 个值） | `spec.py` | **→ 存储/压缩层。** 消费者是 `runtime/storage/tool_result.py`（`_effective_result_policy` / `_inline_bytes_for_policy` / `_preview_chars_for_policy`）与 `runtime/context/compaction.py:739`：控制工具输出何时落盘、inline 阈值与预览长度，是会话级的事 |
| `progress_policy` | `spec.py` | **→ loop / Surface 层。** 消费者是 `runtime/agent/loop.py:822`：仅当值为 `analysis` 时触发「耗时 10–60 分钟」的进度通知，直接依赖 `chat_id` / `progress_fn` 回调 |
| `context_params`（运行期上下文注入） | `executor.py:build_executor_kwargs` | → Q4 的 `contextvars`。这是现有设计里的带外通道，**必须一对一有替代**，否则 50 个工具全部迁不动 |
| 生命周期 hooks（`tool_before` / `tool_after` / `tool_failure`） | `hooks.py`、`execution_hooks.py`（1,155 行） | **本步不做**，挂载点**在此指明**：`execute()` 内部，包裹 `tool.execute()` 的 try/except **之外**——与陷阱 3 的异常边界共用同一位置。理由：hook 若落在 try 之内，hook 自己抛的异常会被当成工具失败报给模型；若落在单工具超时预算之内，人类审批的思考时间会被计进工具超时（harness9 `tools_exec.go:56-60` 专门为此用会话级 ctx 而非 toolCtx） |
| MCP `mcp__{server}__{tool}` 命名 | `orchestration.py:193` | → `mcp_tool.py`。⚠️ **本表原先写「必须与现有约定逐字节一致」，那条约定经核实并不存在**——`mcp__` 全仓库只有 1 处、且是读取，无生产者、无消毒函数，唯一的转换器是零调用方的死代码。改为**由本步立规**，见陷阱 10 |

## 6. 任务切分

四个任务，顺序 **A → B → C → D**，全部串行。
（原稿的 Task 0「驱逐」已由 owner 取消，见 Q7。本步因此是**纯 additive**：
`git status --porcelain` 里出现任何 ` M `，本身就是缺陷。）

> **不要写「B 与 C 并行」。** 计划 0027 附录 B 记录的第一条自身错误，正是
> 「声称 B 与 C 独立，实际 B 要调用 C 的函数」。这里是同一个陷阱的镜像：
> Task C 要交付一个「需要带外上下文」的参考工具，而带外上下文的读取约定
> 是 Task B 的 `context.py` 定义的——C 的那个工具依赖 B。独立审核把这条
> 判为「重演了刚记录过的错误」，判得对。
>
> C 的另外两个参考工具（只读无参、带必填参数会校验失败）确实只依赖 A，
> 可以与 B 并行；但把三个工具拆到两个任务里不值得，所以整体串行。

> **Task 0 已取消**（owner，2026-09-17）。原稿要把
> `omicsclaw/runtime/tools/` 改名到 `omicsclaw/legacy/tools/`，实测影响
> **78 个文件**（含 `runtime.tools` 的 70 个 + 文档字符串路径 1 个 + 包内
> 相对 import 7 个）。取消后这 78 个文件一个都不动，边界改由 Task A 的
> `test_tools_is_a_leaf_layer.py` 强制——见 Q7。
>
> 那次清点里有一条事实值得留给日后真要做这件事的人，因为它花了时间才
> 拿到：`omicsclaw/runtime/` 内有 **7 个文件用相对 import 引用 tools**
> （`runtime/__init__.py`、`agent/query_engine.py`、`storage/task.py`、
> `storage/tool_result.py`、`policy/{approval,policy,verification}.py`，
> 写法是 `from .tools...` / `from ..tools...` / `from ...tools import
> hooks`）。它们**不含 `runtime.tools` 字样**，`grep -rl "runtime\.tools"`
> 全部漏检。其中 `runtime/__init__.py` 是 391 行 eager 再导出枢纽，从
> `.tools.spec`、`.tools.registry`、`.tools.hooks`、`.tools.validation` 等
> 8 处导入——漏改它，`import omicsclaw.runtime` 直接失败。检索须用两条
> 命令，并以 `python -c "import omicsclaw.runtime"` 作第一道闸。

**Task A —— 抽象与注册表。** `base.py`、`registry.py`、`__init__.py`，
配 `test_base.py`、`test_registry.py`、`test_registry_is_a_tool_executor.py`、
`test_tools_is_a_leaf_layer.py`。覆盖陷阱 1–7。

**Task B —— 适配器。** `function_tool.py`、`mcp_tool.py`、`context.py`，
配各自测试。覆盖陷阱 8–11。

**Task C —— 参考工具。** `builtin/` 下 2–3 个真正的工具，用来证明这套
抽象拿得住真实场景。建议选：一个只读无参的、一个带必填参数会校验失败
的、一个需要带外上下文的（验证 Q4 的约定真的能用）。

> **§3 的行数预算与本段的授权互相矛盾，以本段为准。** §3 给 `builtin/`
> 合计 250–270 行，即每个工具约 83 行；而本段要求每个工具「打在一个会
> 暴露问题的点上」、真实场景。**83 行写不出一个只靠标准库就真能做完一
> 件事的工具，能写出来的只有打桩**——而打桩的参考实现证明不了任何事，
> 等于把本任务取消。实测交付 **1,016 行**（×3.76）。参考工具这一类按
> **原稿 ×4** 估，不沿用其它模块的 ×3：它要同时承载领域内容（遗传密码
> 表、发行版清单、符号模式）**和**其它模块都写的「为什么是这个形状」。

**Task D —— 独立评估**，两个只读 agent 并行：正确性 + harness9 对照。
见 §8。

每个实现任务动手前必须读：`omicsclaw/schema/message.py`、
`omicsclaw/engine/executor.py`（它定义了要满足的契约）、
`omicsclaw/runtime/tools/spec.py` 与 `registry.py`（要保住的能力——**只读
参考，不得 import**，见 Q7），以及 harness9 的
`internal/tools/base.go`、`registry.go`、`mcp_adapter.go`。

## 7. 陷阱

每一条都是必备回归测试。

1. **工具列表顺序必须是注册顺序。** 见 Q3。变异验证：把实现换成 `sorted()`
   或 `set` 遍历，点名测试必须变红。理由是厂商前缀缓存的计费方式（Q3），
   与本仓库的任何既有约定无关，重构之后依然成立。

2. **未知工具返回 `is_error` 结果，绝不抛异常。** harness9 明确如此：模型
   拿到「不存在名为 X 的工具」这条 Observation 后可以自我修正；抛异常则
   杀掉整条 run。这也是第 3 步 `engine` 侧陷阱 5 的同一条纪律，只是移到
   了它真正该在的层。

3. **工具抛异常 → `is_error`，但 `CancelledError` 必须穿透。**
   `except Exception`，**绝不** `except BaseException`。第 2、3 步都已写下
   这条；本步是第三次。

   ⚠️ **理由已修正（D2 评估指出）。原稿写的是「Go 的 `recover()` 会捕获
   一切，直译即错」——那句话是错的。** Go 的 `recover()` **只捕获
   panic**；而在 Go 里 context 取消是一个**返回的 error**（`bash.go:141`
   就是 `ctx.Err() == context.DeadlineExceeded`），走的是 `registry.go` 的
   `err` 分支变成 `IsError`，**从不经过 recover**；`SIGINT` 默认直接终止
   进程，也不可 recover。

   所以 `except Exception` 恰恰是 `recover()` 的**忠实**等价物，不是对它
   的偏离。这条陷阱在 Python 里依然**必须存在且写对**，但正确的理由是：
   **Python 的异常层级把「取消」和「工具失败」塞进了同一个机制，Go 没有。**
   在 Go 里这两者天然分流，在 Python 里要靠 `Exception` / `BaseException`
   这道线手工分流——写错就把 Ctrl-C 和超时取消变成了给模型看的
   Observation。这句话会被后人引用，值得记对。

4. **`KeyboardInterrupt` / `SystemExit` 同理。** 它们是 `BaseException`
   而非 `Exception`，被陷阱 3 一并覆盖，但值得单列一个测试——harness9 的
   `recover()` 兜底注释说的是「不让单个工具崩溃拖垮整个进程」，那个意图
   在 Python 里若写成 `BaseException` 就变成了「Ctrl-C 按不动」。

5. **`definition()` 绝不泄漏策略字段。** 断言序列化结果里不含
   `risk_level` / `approval_mode` / `read_only` 等任何一个名字。

6. **`tool.name` 与 `tool.definition().name` 必须一致。** harness9 有两个
   独立来源，可以不一致而无人发现——注册按 `Name()`，模型看到的是
   `Definition().Name`，一旦不同，模型调用的名字注册表永远找不到。注册时
   校验并抛。

7. **重复注册保留原有实现。** 见 Q6。测试要断言「冲突之后，拿到的仍是
   第一个」——只断言抛异常不够。

8. **`parsed_arguments()` 对坏 JSON 返回 `{}` 而不抛**（ADR 0077 的既定
   行为）。所以 `FunctionTool` 必须能区分「模型给了空对象」与「模型给的
   JSON 截断了」，并且两种情况都要给模型一条**可据以修正**的错误，而不是
   一个空 dict 悄悄跑完。

9. **参数校验失败必须以 `is_error` Observation 抵达模型，且不得终结
   run。** 同陷阱 2 的理由：这是模型最常犯也最容易自己改对的错。

   ⚠️ **措辞已修正（Task B 交付时）。** 原稿写的是「是 `is_error` 结果，
   不是异常」，那在 Task A 已交付的接口下**字面不可实现**：`Tool.execute`
   返回 `str`，没有任何带内方式表达「这是错误」，唯一的机制就是抛，再由
   `ToolRegistry.execute` 转成 `is_error`——而那正是陷阱 3 建立的那条
   边界。陷阱真正要禁的是「校验失败杀掉整条 run」，不是「不许用异常」。
   实现按此意图交付，并用 `ToolArgumentError(ValueError)` →
   `(BaseException)` 的变异验证了它**确实被注册表接住**（改成
   `BaseException` 后 `except Exception` 接不住，异常逃逸，测试变红）。

10. **MCP 命名消毒：本仓库没有可对拍的现有约定，Task B 是在「发明」它。**
    ⚠️ 原稿写的是「必须与现有约定逐字节一致」，**那条约定不存在**——
    Task A 核实、协调者复核确认：`mcp__` 在全仓库 `*.py` 里只出现
    **1 次**，是 `runtime/tools/orchestration.py:193` 的
    `request.name.startswith("mcp__")`，一次**读取**，用于给已分发的调用
    打观测标签。**没有任何生产者**，也**没有任何消毒函数**（无
    `SanitizeMCPName` 的对应物）。唯一的 MCP→工具转换器
    `surfaces/cli/_mcp.py:304 load_mcp_tools_as_openai_functions` 原样
    使用 `tool.name`、不加前缀，而且**零调用方**，是死代码。

    所以：**不要去找对拍基准，找不到。** 改为照 harness9 的
    `mcp_adapter.go:SanitizeMCPName` 立一条规则，把它写进 docstring 并
    测试，同时**与 `orchestration.py:193` 的 `mcp__` 前缀保持前向兼容**
    （那一行是将来唯一会读到这个名字的既有代码）。这条从「保住一个约定」
    变成了「立一个约定」，是**本步的一项设计决定**，不是一次迁移。

    ⚠️ **原稿漏了这条规则最重要的性质：唯一性。**（D1 评估指出。）
    「两个不同的 `(server, tool)` 绝不能塌成同一个注册表键」没有被写成
    要求，于是实现只在**截断**与**空消毒结果**两处加了指纹，最常见的那类
    **有损替换**无人认领：`get-thing` / `get_thing` / `get.thing` /
    `get thing` 全部消成 `mcp__srv__get_thing`，第二个起被注册表当重名
    拒绝。失败模式与实现自己 docstring 里描述的一模一样——「一个 server
    的工具带着一个没人选过的名字消失了」。

    **裁定：保留现状，钉成「已知代价」，不加指纹。** 修复任务拒绝了
    「有损即加指纹」这个建议，理由成立且比建议本身强：

    - **消毒是幂等的**（`s(s(x)) == s(x)`），所以**每一个**有损原名都会与
      它自己的消毒结果碰撞，而后者本身是合法名。纯函数没法「只给会碰撞的
      加指纹」——只能给**所有**含连字符的名字加。
    - 连字符在 MCP server key 里是家常便饭（`brave-search`、
      `sequential-thinking`）。统一加指纹会从 64 字符预算里切掉 13，
      **反而让真正被指纹保护的那种损失（截断）更容易发生**。
    - 它会毁掉这个模块唯一对外的承诺：`orchestration.py:193` 把第 1 段
      当 server 读来做归因，给每个含连字符的 key 加指纹后这条读取变噪音。

    **碰撞消解本质上需要「看见整个集合」的知识**，而一次挂载整台 server
    工具的那一层（§5 的装配层）还不存在。在它出现之前，正确的做法是把
    行为钉死、理由写清、缓解手段告诉部署方（server key 不要只差一个
    分隔符；MCP 挂载时把 `ToolAlreadyRegistered` 当命名冲突而非重复挂载
    处理）。日后若要修，落点是**铸名函数 `mcp_tool_name`**，不是
    `MCPTool.__init__`——否则 UI 算出的名字与注册表键会不一致，正是该
    模块自己警告过的「一个命名规则两个实现」。

    > 记下来的价值不在这个结论，在**结论的形状**：本条「原稿漏了唯一性」
    > 是对的，「所以应该加指纹」是错的。**发现缺陷的人未必给得出正确的
    > 修法**，修复任务有权推翻它——但必须给出理由并把行为钉住。

11. **`contextvars` 要在并发 worker 里真的读得到。** 不是「设了就行」：
    第 3 步的 `execute_tool_calls` 用 `ensure_future` 起 worker，测试必须
    真的走那条路径去断言，而不是在同一个协程里读一次就算数。

12. **注册表不认识 request、surface、stage。** §5 里那三行能力属于装配
    层。一个测试断言 `ToolRegistry` 的公开面上没有任何以 request/surface/
    stage 为参数的方法——防止它们在「顺手」的名义下爬回来，把注册表重新
    变成今天那个什么都管的东西。

    ⚠️ **这条陷阱的措辞决定了它只能被实现成一次拼写检查**（D1 评估指出，
    判得对）。「没有以 request/surface/stage 为参数的方法」可以逐字实现，
    但保证不了「注册表不认识 request」这个**语义**——一个叫
    `def for_caller(self, ctx)` 的方法可以完整绕过它。这不是实现的错，是
    要求写错了。应改成结构性陈述，例如「公开方法的参数类型只能是 `str`、
    `Tool`、`ToolPolicy`」——那是可判定的，而且不依赖命名习惯。

## 8. Task D —— 独立评估（本步的关卡）

两个**只读**子 agent 并行，均未参与任何代码编写，且不被告知彼此或协调者
已知的问题。第 3 步的经验：它们各自独立撞上同样的缺陷，那个交叉印证比
任何单份报告都有说服力。

**D1 —— 正确性与车道纪律。** 12 条陷阱逐条验证，**用变异而不是看绿**。
重点查测试是否在对着实现自己的输出做断言。车道：Task 0 取消后本步是纯
additive，`git status --porcelain` **只许出现 `??`**；任何 ` M ` 都是缺陷。

**D2 —— harness9 对照 + 能力保全。** 两个问题：
(a) 逐条对照 `internal/tools/*.go`，指出 harness9 有而这里没有的；
(b) **逐行核对 §5 的能力表**——每一个「装配层」「存储层」「不需要了」都要
被追问：那个理由是真的吗？如果某项能力在移交中**丢了而没人说**，那是本
步最严重的一类缺陷，比任何实现 bug 都重要，因为它不会报错。

> **给 D2 的特别指示**：§5 那张表是协调者写的，所以它的盲区就是计划的
> 盲区。请自己去读 `omicsclaw/runtime/tools/spec.py` 与 `registry.py`，找
> **表里根本没提到的**字段或行为。第 3 步的对照评估正是靠这条找出了 4 项
> 漏记能力。

## 9. 验收标准

1. `tests/tools/` 在无网络、两个厂商 SDK 均未安装的条件下通过。
2. 第 1、2、3 步的 635 个测试不受影响，且**逐字不变**——本步纯 additive，
   连一个既有文件都没碰，所以这条应当是自动成立的；不成立即说明越界了。
3. `ToolRegistry` **结构化满足** `omicsclaw.engine.ToolExecutor`：
   `isinstance(registry, ToolExecutor)` 为真，且 `omicsclaw/tools/`
   **不 import `omicsclaw.engine`**（AST 测试强制）。
4. `omicsclaw/tools/` 在 `omicsclaw` 命名空间内**只**导入
   `omicsclaw.schema`——白名单，用 AST 遍历而非字符串 grep。连 `provider`
   都不需要（工具层比引擎层更靠下），`runtime.tools` 更不许（Q7：Task 0
   取消后，这条测试是旧层边界的**唯一**执行机制，所以它自己必须经变异
   验证：往 `omicsclaw/tools/` 里塞一行 `from omicsclaw.runtime import
   tools`，这条测试必须变红）。
5. §7 的 12 条陷阱每条有点名的回归测试，且每条经变异验证。**这是步级
   标准，不是任务级**：陷阱 1–7 与 12 归 Task A（12 虽在编号外，但纯属
   注册表侧，没有后续任务会自然认领它），8–11 归 Task B。不要拿这条去
   判 Task A 不完整。
6. §5 的能力表每一行都有交代，没有留空。
7. §5 中标为「装配层」「存储/压缩层」「loop / Surface 层」的每一项，**须
   给出一个具体的模块路径落点**（哪怕是猜测性的，如「很可能落在
   `omicsclaw/context/policy.py`」），而不是笼统写一个层名。这是针对
   本步审核发现的「待定三项」问题的系统性预防——层名是理由，路径才是
   承诺。
8. `awk 'length > 88'` 对新文件不输出。
9. **纯 additive**：`git status --porcelain` 只许出现 `??`。Task 0 取消后
   本步没有任何合法的既有文件改动，一个 ` M ` 就是一处越界。

10. **`policy_for()` 的解析结果必须在执行期真的生效**，且要有一条测试
    证明**收紧**方向有效（部署把 AUTO 收紧成 ASK，工具必须被拦下问人）。

    > **这条是补的，补的原因值得记下。** 原稿 §9-5 只要求「Q5 的优先级表
    > 四行全部要有测试」——四行都测了，四条都绿，而整个特性是**惰性的**：
    > 没有任何生产代码读 `policy_for`，`require_approval` 拿的是工具自报
    > 的那份 policy，于是部署方的收紧一次也没生效（三方独立命中）。
    > **「有测试覆盖优先级表」与「优先级表有用」是两件事**，原稿只要求了
    > 前者。凡是「解析出一个策略」的设计，验收标准都必须同时钉住**解析**
    > 与**生效**，否则做出来的是一个长得像安全控制、实际不接线的 API。

## 10. 验证

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest \
    tests/schema/ tests/provider/ tests/engine/ tests/tools/ \
    -p no:cacheprovider -q -o addopts=""
```

本机默认 `python3` 是 3.10 会失败，须用上面这个解释器。
`pytest-asyncio` **未安装**，异步测试用 `asyncio.run` 驱动。`black`
装不了，用 `awk` 查行宽并手工检查 black 会重排的构造。

## 11. 后续步骤继承什么

- **50 个里有 5 个必须手写，不能走适配器。** Q1 断言「那 50 个既有工具的
  executor 都是普通函数，让它们逐个变成手写类是没必要的仪式」——这句话
  对 `approval_mode=ASK` 的那 5 个**不成立**：`parse_literature`、
  `move_file`、`remove_file`、`create_omics_skill`、
  `autonomous_analysis_execute`。`FunctionTool` 包装的函数拿到的是解析并
  校验后的关键字参数，**拿不到原始 payload**，所以它的审批提示无法对模型
  发出的字节忠实。要字节级忠实的审批，就必须按 `Tool` Protocol 手写
  （`execute` 拿到的就是未解析的 payload）。Task C 的 `save_gene_panel`
  是这条路线的工作样例，并配了一对测试把「同一份工作包进 `FunctionTool`
  就看不到那些字节」钉成事实。

- **新层的 schema 校验是「部分」的，这一点必须传给新工具作者。** Task B
  与旧 `runtime/tools/validation.py` 对拍做到了零差异（正确），但一致的
  那套语义**接受它并不执行的 schema**：`minimum` / `maximum` / `pattern` /
  `minItems` / `anyOf` / `oneOf` / `allOf` / `$ref` / `const` / `format`
  一律只解析不检查，`type` 只认六种。对迁移无损（旧的一样），但对**新
  工具作者**是活的陷阱——写 `"minimum": 0` 会被静默忽略。清单见
  `validate_arguments` 的 docstring；超出部分由工具自校验。

- **那 50 个工具的迁移。** 本步只建路。迁移必须逐个做、逐个验证语义，
  并且要先把 §5 里判给装配层 / 存储层的那几项真正安置好
  （`result_policy`、`progress_policy`、`speculative_classifier`、
  `surfaces`、`predicate`）——去向已定，但**家还没建**，家不建工具就
  迁不干净。
- **装配层（第 5 步 `context/`）继承四件事**：Surface 门控、predicate
  门控、每会话冻结工具列表、按阶段裁剪子集。本步把它们从注册表里摘
  出来，但**没有**为它们建新家。第 5 步要么建，要么明确废弃——既然整个
  项目在重构，「废弃」是正当选项，但必须是被决定的，不是被遗忘的。

  > **owner 于 2026-09-17 被问到这四项的去留，未作答。** 之所以不阻塞本
  > 步：无论保留还是废弃，本步都不实现它们中的任何一项——注册表只负责
  > 「全集有序」，四项全在它的公开面之外（陷阱 12 还专门有一个测试挡着
  > 它们爬回来）。所以这是一个**结转到第 5 步的待决项**，不是一个被跳过
  > 的问题。第 5 步开工前必须先要到这个答复。

- **`omicsclaw/legacy/` 命名空间本步不建**（Q7，Task 0 取消的代价）。计划
  0026 §10 的 `omicsclaw/providers/`（复数，2,426 行）与第 6 步的
  `omicsclaw/memory/` 日后若要收编，各自决定去处；届时若仍想集中安置，
  旧工具层的那 78 个文件可以与它们一并移动，那时改名是真实工作的一部分，
  而不是一次独立的大范围 churn。
- **生命周期 hooks**（1,155 行）本步只留挂载点，不搬。
- **`ToolCall.id` 的铸造**仍然欠着：`ToolCall.id` 的 docstring 承诺
  adapter 在厂商不给 id 时铸一个，而 `openai_provider.decode_tool_call`
  留空，`ollama` 是已发布预设。第 3 步的引擎已自保（按位置配对 + id 重
  刻），但源头的承诺仍未兑现。这是 provider 层的债，不是工具层的。
- **`ToolResult.metadata` 的用途**：第 3 步的引擎已在里面写
  `reported_tool_call_id`。本步的注册表应当写入单工具执行耗时——这顺手
  补上计划 0027 附录 A #35 记的那项 harness9 能力（引擎侧精确耗时），
  而它不被任何层阻塞。已交付。

### Task D 两份独立评估查实的债

下面每一条都有可复现证据。**它们不是本步的缺陷**（缺陷已单独修复），而是
本步**照出来**的、归属在别处的空缺。按 §5 的纪律：判「不需要了」完全可以，
但必须是**被决定的**。

| # | 债 | 证据 | 谁必须决定 |
|---|---|---|---|
| 1 | **写屏障整个丢了。** `ToolPolicy.concurrency_safe` **零消费者**（实测：新层只有 builtin 在设、dataclass 在声明、docstring 在引用）；真正排程的 `engine/executor.py` 对每个调用无条件 `ensure_future`，唯一约束 `max_concurrent_tools` 默认 **0 即无上限**；而 `ToolExecutor` 只有两个方法，注册表**结构上无法**把并发安全性告诉引擎 | 旧层 `orchestration.py:707-726` 把非并发安全的工具当**串行屏障**（688-689 行明写）。迁移后同一轮里两个写同一路径的 `file_write` 从串行变并发 | 第 5 步。**并且要注意附录 A #13 恰恰把这个字段指认为 `path_locker.go` 的「挂载点」——于是两套并发写保护同时缺席，而提到它的那一行正是让它看起来已经有着落的那一行** |
| 2 | **人类审批的思考时间被计进 `tool_timeout`**（默认 60s），超时后模型收到一句事实上错误的 `"tool 'X' timed out"` | 见 Q4 第 3 问下的实测 | 要动 `omicsclaw/engine/`，超出本步范围。第 5 步或一个独立任务 |
| 3 | **SSRF / 出网安全门从未被命名。** harness9 有整个 `web_safety.go`（scheme 白名单、拒 userinfo、DNS 解析后查 8 个 CIDR 段含 `169.254.0.0/16` 云 metadata、DNS 失败 fail-closed、每一跳重定向重跑）；本仓 `web_fetch` 的全部检查是 `url.startswith(("http://","https://"))`（`builders/engineering.py:1061-1067`） | 附录 A 给了 `safe_path.go`、`path_locker.go` 各一行并点名对应物，**唯独把 `web_safety.go` 折叠进「web×4」内置工具里**，于是它从没被问过第 12 行被问的那个问题 | **本步不做完全站得住**（§1 非目标）。问题是它在任何文档里都没有记录。现已记录 |
| 4 | **迁移不可能是机械的**：`ToolPolicy` 的默认按 Q5 全面反转（`low→HIGH`、`AUTO→ASK`、`allowed_in_background True→False`、`concurrency_safe` 保持 `False`） | `spec.py:37-46` vs `base.py:185-209` | 迁移任务。任何一个既有 spec 不重述策略就迁移，都会**静默**从「自动/低危/允许后台」变成「必须审批/高危/仅前台」 |
| 5 | **`surfaces` 门控的默认语义反转且无人记录**：旧 `registry.py:109` 是 `if spec.surfaces and surface and surface not in spec.surfaces: continue`，`surface` 为空时 **fail-open**；新 `ToolPolicy.tags` 默认空集、docstring 写「matches no allow-list」= **fail-closed** | 两者都可辩护，但没人写下它们是**相反**的。于是「`surfaces=("bot",)` → `tags={"bot"}`」不是自动的：无标签的工具会从每个 Surface **消失**，而不是出现在 `bot` 上 | 第 5 步装配层 |
| 6 | **`STAGE_TO_TOOL_SUBSETS` 的宽容默认**：表里没有的 stage 一律 `UNFILTERED`（`registry.py:20-22`）。照着重建但默认成「过滤」，任何未知 stage 字符串都会**静默造成工具全黑** | 同上 | 第 5 步装配层 |
| 7 | **`build_executor_map` 的 fail-fast 开机闸死了**：它在**启动时**抛 `KeyError("Missing tool executors for: ...")` 并列出全部未解析对（`executor.py:28-30`）。新设计下未注册的工具只是不在表里，失败改为运行中的一条 `is_error` | 可辩护（不再有两张表要对齐），但这是**损失，不是等价变换**，§5「executor_name 消失」那一行没提 | 迁移任务 |
| 8 | **`to_openai_tool()` 的 `deepcopy` 护栏死了**：旧层每次发射都 `deepcopy(parameters)`（`spec.py:62-70`）；新层 `definition()` 返回的 `input_schema` 与工具内部 schema **共享** | 今天不会被污染（两个 adapter 都先 `dict(...)` 再改），但那都是**浅**拷贝，`["properties"]` 仍是同一个对象。`deepcopy` 是让这件事不可达的那道墙 | 记录即可；若日后有 adapter 深改 schema 需重新评估 |
| 9 | **`policy_tags` 不只是过滤标签**：`orchestration.py:201` 用 `"mcp" in spec.policy_tags` 做**分派** | `base.py` 把 tags 描述成「给装配层过滤用」，低估了它 | 迁移任务 |
| 10 | **predicate 的事件流一并废掉**：`select_tool_specs` 经 `register_predicate_event_sink` 发 `EVENT_PREDICATE_HIT`/`MISS`，其 docstring 自称是该 hook 在生产侧的**唯一 producer** | §5 的 predicate 那一行一字未提 | 第 5 步 |
| 11 | **七种执行状态与整个 trace（provenance）无声消失**：`EXECUTION_STATUS_{COMPLETED,FAILED,HOOK_BLOCKED,INPUT_SCHEMA_INVALID,INPUT_VALIDATION_FAILED,POLICY_BLOCKED,UNKNOWN_TOOL}` 与 `ToolExecutionTrace` 的 `requested_arguments`/`effective_arguments`/`mcp_metadata`/`classifier_result`/`schema_errors`/三组 hook 记录/`phase_timings_ms`/`blocked_by` 等十二项。新 `ToolResult` 只有 `is_error` + `duration_s` | 其中任何一项判「不需要了」都可能是对的——但**没有被问过** | 第 5 / 6 步 |
| 12 | **归一化不再可观测**：旧层把 `effective_arguments` 与 `requested_arguments` 分列在 trace 里；新层归一化发生在函数体内，外部看不到「跑的和模型发的不一样」 | `gene_panel` 正是活例：人批准的是 `['cd3d','cd3d']`、写下的是 `['CD3D']`。按设计这是对的（审批要字节忠实），但那条 provenance 记录没了 | 第 5 / 6 步 |
| 13 | **未知工具的自愈提示退化**：旧层用 `difflib.get_close_matches(n=3, cutoff=0.6)`，docstring 记录它来自一次实际诊断（裸拒绝会多花一轮）；新层列出**全部**已注册名字。49 个工具时每次拼错都是约 600 字符的 Observation | 新层给的理由（「在对话尾部、不在缓存前缀里」）对**缓存**成立、对**本轮**不成立：模型还是要读它，而「这里有 49 个名字」的纠错信号弱于「你是不是想要 `file_read`？」 | 迁移任务。这是对本仓库**已经付过一次学费**的修复的可测量回退 |
| 14 | **工具输出没有上限**：harness9 `bash.go:205-238` 有 16,000 字符上限且**保头保尾**（头 1/3 + 尾 2/3，注释写明理由：测试运行器的 FAILED/traceback 在最后，只保头会切掉诊断信息）。新层 `registry.execute` 与 `as_text` 都无上限 | §5 把它判给存储层（`storage/tool_result.py` 的 head 70% / tail 30% 概念确实活着），但附录 A 无对应行，而存储层正是「家还没建」的那几层之一 | 第 5 / 6 步 |
| 15 | **每次调用可协商的超时预算 + 机器可读超时横幅**：harness9 允许模型用 `timeout_secs` 临时放宽（钳到 600s 上限），超时后追加一段告诉模型「这不是代码错误」的横幅；`bash.go:25-29` 注释记录这是实测教训。本仓两层都没有，`tool_timeout` 是**所有工具一个数字** | 对跑分析流水线的 agent，60s 平铺预算会复现 harness9 已经付过一次学费的故障 | 第 5 步 |
| 16 | **「工具失败」与「世界失败」的三分塌成了二分**：harness9 刻意区分——命令非零退出、HTTP 404、搜索无结果都是 `err == nil` 即 `IsError=false`，只有 harness 层面的问题才产生 `err`。新层机制上仍可表达（直接返回文本），但**没有任何地方写下这条约定**，而 `base.py` 的措辞自然读法是「任何失败都该抛」 | 照它写，将来每一次非零退出都会被标成 `is_error=True`，把「命令告诉我测试失败了」和「工具坏了」混为一谈——恰恰是 ReAct 自愈最需要区分的一对 | 只需补一段约定，不涉及代码改动。迁移任务 |

## 附录 A —— harness9 `internal/tools/` 对照表

D2 的标尺。左列穷举 harness9 工具包（16 个非测试文件，约 2,400 行）的
能力，右列声明本步处置。**审计它，不要相信它。**

| # | harness9 能力 | 出处 | 本步处置 |
|---|---|---|---|
| 1 | `BaseTool` 三方法接口 | `base.go` | ✅ `Tool` Protocol |
| 2 | 注册（同名冲突保留原有） | `registry.go` | ✅ Q6 |
| 3 | 工具定义列表暴露 | `registry.go` | ✅ 且**加强**：顺序确定（Q3） |
| 4 | 按名路由分发 | `registry.go` | ✅ |
| 5 | 未知工具 → `IsError` 而非抛 | `registry.go` | ✅ 陷阱 2 |
| 6 | 工具错误 → `IsError` 封装 | `registry.go` | ✅ 陷阱 3 |
| 7 | `recover()` 兜底防单工具崩进程 | `registry.go` | ✅ Python 对应物是 `except Exception`，而且是**忠实**等价物——⚠️ 本行原写「刻意不等价，`recover()` 捕获一切」，D2 指出那是错的：`recover()` 只捕获 panic，Go 里 context 取消是返回的 error、`SIGINT` 直接终止进程，两者都不经过 recover。真正的差异在 Python 侧：它把取消与工具失败塞进了同一个异常机制，所以需要 `Exception`/`BaseException` 这道手工分流线（陷阱 3、4）。**代码一直是对的，错的是写下的理由。** |
| 8 | 并发注册安全（RWMutex） | `registry.go` | ◐ 待实现任务裁决：Python asyncio 单线程，但 MCP 若从别的线程注入就需要锁。**须调查本项目 MCP 注入实际在哪个线程**，不要凭空加锁也不要凭空省略 |
| 9 | MCP 工具包装成原生工具 | `mcp_adapter.go` | ✅ `mcp_tool.py` |
| 10 | MCP 命名消毒 | `mcp_adapter.go:SanitizeMCPName` | ✅ **由本步立规**，不是迁移——本仓库经核实没有可对拍的既有约定（见陷阱 10）。且**刻意三处偏离 harness9**，D2 应把它们当修正而非缺口核实：折叠连续下划线（否则 `orchestration.py:193` 的 `split("__", 2)` 会把含 `__` 的 server 名截断）、只留 ASCII（harness9 用 `unicode.IsLetter`，非 ASCII 名字会存活到厂商侧被 `^[a-zA-Z0-9_-]{1,64}$` 拒成整请求 400）、空消毒结果带指纹（否则同一 server 下多个非 ASCII 名工具会塌成一个名字、被注册表当重名拒掉） |
| 11 | MCP schema 解析失败不阻断注册 | `mcp_adapter.go:parseInputSchema` | ✅ |
| 12 | 沙箱路径校验 | `safe_path.go` | ⬜ 不做——具体工具的依赖；本项目已有 `services/path_validation.py` |
| 13 | 写操作路径锁 | `path_locker.go` | ⬜ 不做——同上。但 `ToolPolicy.concurrency_safe` 是它的挂载点 |
| 14 | 内置工具（bash / read / write / edit / web×4 / memory×2 / plan） | 11 个文件 | ⬜ 本步只做 2–3 个参考实现。⚠️ **本行原先写「本项目的工具形态完全不同（omics 技能而非通用编码）」，那是错的**：`runtime/tools/builders/engineering.py` 定义了**恰好 14 个通用编码工具**——`ask_user` / `file_edit` / `file_read` / `file_write` / `glob_files` / `grep_files` / `task_create|get|list|update` / `todo_write` / `tool_search` / `web_fetch` / `web_search`，与 harness9 的内置工具近乎一一对应。另有约 35 个 omics / 知识图谱工具无对应物。<br>（协调者的第一版更正把 `web_method_search` 也列了进去、并把 15 个名字称作 14 个，D2 指出后复核：它定义在 `builders/agent.py:1222`，`engineering.py:509` 只是 `executor_name` 引用——一个 `name="…"` 的 grep 会把 `executor_name="…"` 一并匹配。同理「12 个文件」应为 **11**：bash+read+write+edit+web×4+memory×2+plan。） |
| 15 | 工具级功能选项（`ReadFileOption` 等） | 各工具 | ⬜ 不做——Python 用构造函数参数 |

**本步反超 harness9 之处**（D2 应一并核实）：

1. **工具列表顺序确定。** harness9 明说不确定；任何依赖 prompt 前缀
   缓存的系统都承受不起（Q3）。
2. **策略元数据有正式载体且被测试挡在 prompt 之外。** harness9 把权限
   模式放在 engine 上，工具自身不携带风险等级。
3. ~~**`recover()` 不直译。**~~ **已撤回**——见 #7。D2 核实后表明这不是
   反超，`except Exception` 是 `recover()` 的忠实等价物。留在这里是因为
   「一条被证伪的反超声明」本身就是给后续步骤的提醒：**声称自己胜过参照
   系时，先确认自己读懂了参照系。**

## 附录 B —— 结果与教训

本步已交付。以下是交付事实与买到的教训，写给第 5、6 步。

### 交付事实

| 项 | 数 |
|---|---|
| 生产代码 | `omicsclaw/tools/` 共 10 个模块（含 `builtin/` 3 个参考工具）。⚠️ **那 3 个参考工具已于 2026-09-18 由 owner 裁定移除**——见下方「后记」 |
| 测试 | `tests/tools/` **315 passed** |
| 四目录合计 | **950 passed**（第 1–3 步的 635 一条不差） |
| 车道 | **纯 additive**：`git status --porcelain` 非 `??` 条目 14 条，与开工前逐行相同，旧工具层一个文件没碰 |

任务序列 **A → B → C → D → 修复**，全部串行；D 是两个**只读**评估并行。

### 本步的缺陷是怎么被找到的

| 缺陷 | 谁找到 |
|---|---|
| `register(policy=)` 收紧完全不生效 | **Task C、D1、协调者三方独立命中** |
| `FunctionTool(parameters=)` 浅拷贝共享 | Task C、D1 两方 |
| 分层守卫的动态 import 盲区 | D1 |
| 审批等待被计进 `tool_timeout` | D1 |
| 坏掉的 progress sink 毁掉工具结果 | D1 |
| `concurrency_safe` 零消费者 | D2 |
| SSRF 从未被命名 | D2 |

**「不告诉评估方自己已知的问题」这条纪律又一次兑现。** 协调者在派 D1/D2
之前就已经复现了策略覆盖失效，全程没有透露；D1 独立撞上同一条。那个交叉
印证比任何单份报告都有说服力——而且它是可重复的，第 3 步也是这样。

### 计划自身的错误

**实现方与评估方一共指出 20 余处，全部已回写。** 其中值得单独记的：

1. **§2 的 `ToolPolicy` 草图与 Q5 直接矛盾**，而且与它自己引用的证据也
   矛盾（旧 `ToolSpec.concurrency_safe` 默认就是 `False`）。照草图写会让
   Q5 要求的那个测试变成「断言空白策略授予一切权限」的空转。
2. **§5 声称 MCP 命名有「现有约定」要对拍——那条约定不存在。** 全仓库
   只有一次 `startswith` 读取，无生产者、无消毒函数，唯一的转换器是零
   调用方的死代码。这条从「保住一个约定」变成「立一个约定」。
3. **§9 只要求「优先级表四行有测试」。** 四行都测了、都绿，而整个特性
   是惰性的。**「有测试覆盖 X」与「X 有用」是两件事。**
4. **陷阱 9 的字面表述在已交付的接口下不可实现**（`Tool.execute` 返回
   `str`，没有带内错误通道）。
5. **附录 A 第 14 行说本项目工具「形态完全不同」**——实际有 14 个与
   harness9 近乎一一对应的通用编码工具。**附录 A 是 D2 的标尺，标尺错了
   会让评估漏掉一整类对照。**
6. **协调者自己的更正也错了一次**：修第 14 行时把 `web_method_search`
   列了进去、把 15 个名字称作 14 个（`name="…"` 的 grep 会把
   `executor_name="…"` 一并匹配）。D2 指出后复核改正。**更正也需要被
   审计。**

### 三条最贵的教训

**1. 「有测试」不等于「接线了」。**

Q5 建了一套双源 + 优先级表 + 四行测试，全绿；而**没有任何生产代码读
`policy_for`**，部署方的收紧一次也没生效。这是本步最严重的缺陷，也是最
容易再犯的一种：**一个长得像安全控制、实际不接线的 API。** 凡是「解析出
一个策略/权限/门控」的设计，验收标准必须同时钉住**解析**与**生效**，而且
生效那条要钉**收紧**方向——放宽方向的测试全绿也说明不了任何事。

**2. 互补盲区不是包含关系。**

Q7 取消 Task 0 的论证是「AST 检查严格强于可 grep 的包名」。在静态 import
上成立，但反方向不成立：`importlib.import_module("omicsclaw.runtime...")`
是 **grep 抓得到、AST 抓不到**的。而 Task 0 取消后这条测试是旧层边界的
**唯一**执行机制——唯一 + 有盲区 = 一条无人看守的路。**静态检查查的是
写法，只有行为探针查的是事实**：修复后的守卫补了一个 subprocess 探针，
真跑一遍代表性路径**之后**断言 `sys.modules` 里没有 `omicsclaw.runtime*`。

> **第 5、6 步会照抄这条分层测试**（`context/`、`memory/` 各要一份）。
> 照抄的是哪一版，决定了它们有没有同一个洞。

**3. 同一份计划的两处对同一件事给出相反安排时，实现方会照其中一处做。**

§5 逐字预言了「审批不能落在单工具超时预算之内」并引了 harness9 的做法；
Q4.3 转头把审批放进了 `execute()` 里面。实现方照 Q4 做，于是撞上 §5 已经
预言过的事。**约束必须在「做安排的那一处」复述，而不是只写在论证它的
那一处。**

### 第 3 步的两条教训在本步的复验

- **「结构是资产、字面量是负债」——本层干净。** D2 专门扫过：没有搬任何
  Go 错误字符串、CIDR、HTTP 头名或超时常量，仅有的三个数值常量都有本地
  论证；参照系里唯一一处「不可能发生」的断言也没被搬过来。
- **「缺陷聚集在没人认领的边界」——完全复现。** 修掉的 9 条里，
  **7 条落在车道接缝上**：A↔B 的策略消费端与 schema 所有权、B↔C 的解码器
  重复、新层↔第 3 步引擎的超时归属。每条车道内部都自洽。**派评估时专门
  瞄准接缝，是本步产出最高的一条指令。**

### 一条方法上的收获

**变异驱动必须用 `-rfE --continue-on-collection-errors`。** 破坏 import
的变异会让测试模块在**收集期**失败，而 `pytest -rf` 不列收集错误，于是
把它误报成「变异存活」。本步有 agent 在这上面浪费过时间，此后每一个任务
都带着这条提醒派出去。

### 后记 —— 三个参考工具已移除（owner，2026-09-18）

`inspect_analysis_environment`、`analyze_sequence`、`save_gene_panel`
连同 `tests/tools/test_builtin_tools.py` 一并删除。理由：它们是**证据，
不是产品**——存在的目的是「用代码而不是声明来回答：这套抽象经得起一个
真干活的工具吗」。计划 0029 的 `read_file` / `write_file` / `bash` 把同一
个问题回答得更好，因为它们**本身就是真东西**，而不是一次演示。

**它们证明的每一条都有了新家**，删除前逐条核对过：

| 原本由谁证明 | 现在由谁证明 |
|---|---|
| 包一个普通 callable 不需要仪式 | `read_tool()`（同为 `FunctionTool`） |
| 坏 payload / 缺字段 / 类型不符 → 可修正的 Observation 且 run 不终结 | `read_file` 的解码与校验测试 |
| Q4 带外通道经**真实引擎并发**可用 | `tests/tools/test_context.py::test_the_context_reaches_tools_running_in_concurrent_engine_workers` |
| 审批提示对模型发出的**原始字节**忠实 | `test_write.py` 与 `test_bash.py` 各一条同名测试 |

**顺带关掉的一笔债**：§11 债表里「`WORKSPACE_KEY` 被写下两次」那条
（`_workspace.py` 与 `gene_panel.py` 各一份）随删除自动消失，现在
`read`/`write` 直接 import `_workspace` 的那一份，测试改为同时钉住字面量
与**同一性**。

**分层守卫的行为探针也改写了**：它原本跑那三个参考工具来证明「工具真的
跑过之后 `sys.modules` 里没有 `omicsclaw.runtime*`」，现在跑
`write_file` → `read_file` → 两种失败路径 → `bash` → `MCPTool` → 未知
工具名。**探针因此变强了**——它现在测的是会被真正使用的那条路径。

删除后：`tests/tools/` 与其它三目录合计 **1115 passed**，非 `??` 条目仍
14 条。
