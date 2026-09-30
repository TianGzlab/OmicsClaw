# Hooks：工具调用拦截接缝

`omicsclaw/hooks/` 是一个**扩展点**：在一次工具调用的执行前后插入代码，可以观察、拒绝或改写这次调用。这个包包含一套机制和一个现成的 hook（审计日志）。部署方、子代理或后续功能需要在工具调用上加逻辑时，都从这里接入。

工具调用上常见的策略有四个：权限、高危命令、大输出 offload、计划持久化。OmicsClaw 先做了一次盘点，这四个策略里已经有三个在别的包里实现了，所以 `omicsclaw/hooks/` 只提供机制，再加上唯一还没人实现的那个 hook（观测/审计）。

---

## 1. 定位：机制与策略分开

| 关注点 | OmicsClaw | 说明 |
|---|---|---|
| hook 机制（洋葱模型） | `omicsclaw/hooks/chain.py` | 本包新建：`HookedTool` + `hook_tools` |
| 权限、高危命令 | `omicsclaw/permission/` | 独立的权限层，不是 hook（见 `human-in-the-loop.md`） |
| 大输出 offload | `omicsclaw/context/` 的 `Offloader` | 由预算压力驱动，见 §11 |
| 计划持久化 | `omicsclaw/planning/` | 不以 hook 形式实现 |
| 观测/审计 | `omicsclaw/hooks/audit.py`（本地审计） + `omicsclaw/observability/hook.py`（`TracingHook`，见 `observability.md`） | 本包新建 |

重复实现这三个已有策略，会让同一个问题在一个部署里有两个答案。例如"为什么这次调用被问了"，答案只能来自规则文件，不能再来自某个 hook。

---

## 2. 系统架构

```
omicsclaw/hooks/                    叶子层：只 import schema、tools、标准库
├── base.py     HookCall · HookAction(ALLOW/DENY) · HookDecision · allow() · deny()
│               ToolHook（Protocol，三个方法）· Hook（三个 no-op 的基类）· HookDenied
├── chain.py    HookedTool（装饰一个 Tool）· hook_tools（批量装饰）
└── audit.py    AuditHook · AuditSink（Protocol）· JsonlAuditSink · AuditRecord
                AuditOutcome(ok/error/denied/cancelled) · outcome_of · arguments_digest
                SESSION_ID_KEY

omicsclaw/entry/assembly.py        组合根
├── build_hooks(config, telemetry)  配置出的链：[AuditHook?] + [TracingHook?]
└── build_app(..., hooks=)          hook_tools(...) 之后再 gate_tools(...)

omicsclaw/observability/hook.py    TracingHook：第二个内置 hook（仅在可观测性启用时挂载）
```

包的依赖方向由 `tests/hooks/test_hooks_is_a_leaf_layer.py` 强制：`omicsclaw/hooks/` 不 import `omicsclaw.engine`（引擎只拿到一个 registry，不需要知道工具被包过），也不 import `omicsclaw.permission`（两个叶子层互不依赖，由组合根一行代码把它们接起来）。

---

## 3. 装饰工具，而不是装饰 Registry

```
AgentEngine
   │ execute(call)
   ▼
ToolRegistry.execute ── 发布 effective_policy，计时，把异常转成 is_error Observation
   │
   ▼
GatedTool           ← 权限网关（最外层）
   │  DENY → PermissionDenied，hook 链完全不会执行
   ▼
HookedTool          ← hook 链
   │  before_execute：按注册顺序正向执行
   ▼
inner Tool          ← BashTool / ReadFileTool / MCP proxy / TaskTool …
   │
   ▲  after_execute / on_failure：按注册顺序逆向执行
```

OmicsClaw 不用包装器包住整个 registry，原因与权限层相同（plan 0038 §2）：引擎会用 `isinstance` 探测 registry 是否实现了两个可选 Protocol，`ConcurrencyAwareExecutor` 和 `DeadlineAwareExecutor`。一个包住 registry 的包装器如果忘记转发其中之一，**不会报错**，只会悄悄地把人的审批等待时间又算进工具超时里（`entry/assembly.py` 把这个缺陷记为 R3）。装饰单个 Tool 就不会碰到这个问题。

`HookedTool` 向外转发 `name`、`definition()` 和 `policy`。转发 `policy` 是必须的，因为 `ToolRegistry.register` 和 `GatedTool` 都用 `getattr(tool, "policy")` 读取作者声明的策略。如果包装器不转发，每个工具都会退回到 `ToolPolicy()` 默认值：大多数工具被收紧为 `ASK`，原本 `concurrency_safe` 的并行批次会变成串行，而这两种变化都不会以错误的形式出现。

`HookedTool.inner` 和 `GatedTool.inner` 同名，所以可以用同一段循环逐层拆开包装。`entry/assembly.py` 的 `_is_bash` 就是循环拆包的，因为挂上 hook 链之后 `bash` 变成两层包装。只拆一层会认不出 `bash`，沙箱的 `bash_policy` 也就不会生效。

---

## 4. 链在权限网关**内部**

`build_app` 的装配顺序：

```python
chain = build_hooks(config, observing) if hooks is None else hooks
mounted = hook_tools(mounted, chain)      # 先包 hook
gate = build_permission_gate(config)
mounted = gate_tools(mounted, gate)       # 再包 gate → gate 在外
```

这个顺序有两个后果，代码里已经写明：

1. **被规则拒绝的调用永远不会到达 hook。** `PermissionDenied` 在 `GatedTool` 里抛出，hook 链还没开始执行，所以审计日志和 tool span 里都没有这条记录。
2. **hook 改写参数后，gate 不会重新判定。** gate 是基于模型发来的原始参数做的决定，内层工具实际收到的是 hook 改写后的参数。`HookDecision.arguments` 的 docstring 专门警告了这一点：把 `{"command": "ls"}` 改写成 `{"command": "rm -rf /"}` 的 hook，执行的是一条任何规则都没审查过的命令。`tests/hooks/test_chain.py` 钉住了这个行为。hook 是组合根挂上的代码，与被包装的工具处于同一信任级别。

与审批的交互：

- gate **自己问人**时（高危模式、受保护文件、规则 ask 落在不自问的工具上），询问发生在 hook 链之前。人拒绝后抛出 `ApprovalDenied`，hook 链不会执行。
- gate **把问题交给工具自己问**时（工具声明了 `prompts_for_itself`），hook 的 `before_execute` 先执行，然后工具在内部调用 `require_approval`。人拒绝后，hook 收到 `on_failure(ApprovalDenied)`。实测：这种情况下审计记录的 `outcome` 是 `error`，`detail` 是 `ApprovalDenied`。

---

## 5. 决策词表：只有 allow / deny，没有 ask

```python
class HookAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"

@dataclass(frozen=True, slots=True)
class HookDecision:
    action: HookAction = HookAction.ALLOW
    reason: str = ""                 # DENY 时成为 HookDenied 的文本，模型能看到
    arguments: str | None = None     # 改写后的原始 JSON 参数；None 表示不改

allow(*, arguments=None) -> HookDecision
deny(reason) -> HookDecision
```

OmicsClaw 的 hook 只有两个动作，没有 ask，因为"问人"已经由 `omicsclaw/permission/` 负责，它在一轮判定里综合模式、规则和高危模式，并保证最多问一次。

即使 hook 链里有代码调用了 `require_approval`，这个问题也会自动得到回答：gate 放行一次调用后，会发布一个 `approval_mode=AUTO` 的策略再运行内层，`require_approval` 最先读取的就是这个策略。测试断言 `HookAction` 恰好只有两个成员。

`HookCall` 只有 `name` 和 `arguments`（**未解析的原始 JSON 字符串**），**没有** `ToolCall.id`。不给 id 与工具层的决定一致：工具本来就不知道调用 id。需要关联两条记录的 hook 可以用参数摘要（见 §7）。不解析 JSON 是因为先解码再编码会打乱 key 顺序，而 prompt 前缀缓存和回放证据都依赖逐字节一致的 payload。

`HookDenied` 与 `PermissionDenied` 是两个不同的异常。它们回答不同的问题：权限回答"这次调用是否允许发生"，依据是人写的配置；hook 回答"这个部署是否要介入"，依据是组合根挂上的代码。两者合并的话，操作员会去规则文件里找一条并不存在的规则。两者到达模型时的形状一样，都是 `ToolRegistry.execute` 转换出的 `is_error` Observation，例如：

```
tool 'write_file' raised HookDenied: write_file refused by RawDataGuard — data/raw/ holds raw sequencing output and is never modified
```

---

## 6. ToolHook：三个方法与配对不变量

```python
@runtime_checkable
class ToolHook(Protocol):
    async def before_execute(self, call: HookCall) -> HookDecision: ...
    async def after_execute(self, call: HookCall, output: str) -> str: ...
    async def on_failure(self, call: HookCall, error: BaseException) -> None: ...
```

Python 工具是**抛异常**的，把异常压成字符串塞进同一个签名会丢掉异常类型，而 `ToolRegistry.execute` 正是用类型名来构造模型看到的错误文本。所以失败单独用一个方法，返回 `None`：hook 不能改写失败。

**配对不变量**：每个**放行了**这次调用的 `before_execute`，都恰好对应一次 `after_execute` 或 `on_failure`。以下情况都满足这一点：

- 链中后面的 hook 拒绝了调用；
- 工具抛出异常；
- turn 被取消，无论取消发生在工具执行期间，还是发生在另一个 hook 仍在做决定时。

说"放行了"而不说"返回了"，是因为有一个例外：**主动 deny 的那个 hook 自己不会收到收尾回调**，因为它拒绝时还没完成决策（`test_the_hook_that_denied_is_not_told_about_its_own_denial`）。

`HookedTool.execute` 的实现思路：

```python
call = HookCall(name=self._inner.name, arguments=arguments)
decided = []
try:
    for hook in self._hooks:                       # 正向
        decision = await self._decide(hook, call)  # 已包容异常
        if decision.action is HookAction.DENY:
            raise HookDenied(...)                  # 用 raise，与异常走同一路径
        if decision.arguments is not None:
            call = replace(call, arguments=decision.arguments)
        decided.append(hook)                       # 放行后才加入
    output = await self._inner.execute(call.arguments)
except BaseException as error:
    await self._notify(decided, call, error)       # 逆向 on_failure
    raise
for hook in reversed(decided):                     # 逆向 after_execute
    output = await self._rewrite(hook, call, output)
return output
```

决策循环和工具调用共用同一个 `except BaseException`，这是一次修复的结果：最初这是两个独立的块，决策循环那一块没有异常处理，某个 hook 决策时被取消的话，之前已放行的 hook 都收不到收尾回调（plan 0042 §11）。

**顺序**：`before_execute` 按注册顺序执行，两个收尾方法按相反顺序执行，所以**第一个注册的 hook 在最外层**，它最后收到收尾回调，能看到内层所有 hook 对输出做过的修改。

---

## 7. 失败包容：fail-open，方向与 gate 相反

| 情况 | 处理 |
|---|---|
| `before_execute` 抛 `Exception` | 记日志，视为 `ALLOW` |
| `before_execute` 返回的不是 `HookDecision`（包括忘写 return 得到的 `None`） | 记 error 日志，视为 `ALLOW` |
| `after_execute` 抛异常，或返回非 `str` | 记日志，保留原输出 |
| `on_failure` 抛 `Exception` | 记日志，其余 hook 照常收到通知，原始错误不会被掩盖 |
| 通知期间出现 `BaseException`（新的取消、Ctrl-C） | **不捕获**；取消优先于正在上报的失败，还没通知到的 hook 就不再通知 |
| hook 方法写成了同步 `def` | `_resolved` 只对 awaitable 做 await，所以同步 hook 也能生效 |
| 工具自己的异常 | 原样向上抛出；hook 不能替换失败 |

`ToolRegistry.execute` 把 `try` 内部抛出的一切都算作工具失败。HookedTool 运行在这个 `try` 里面，所以 hook 自己的故障必须在链内部消化掉，否则一个坏掉的 metrics sink 就会让一个正常的工具报错。

**fail-open 是刻意的**，与 `require_approval` 的 fail-closed 方向相反。没有得到同意不等于同意，所以审批问不到人时拒绝。hook 则不涉及同意，它只是部署自己加的介入。如果部署希望"检查没法运行时就拦下调用"，应该写权限规则，那一层是 fail-closed 的。唯一的例外是显式 `deny`，它会抛 `HookDenied`，工具不会执行。

`_notify` 只捕获 `Exception`。第一版捕获了 `BaseException`，理由是"在已被取消的 Task 里 await 会再次抛出 `CancelledError`"，但这个前提不成立。结果它吞掉了通知期间到达的**新的**取消，`execute` 末尾的 bare `raise` 又抛回了工具原来的异常，被取消的 turn 于是作为一个普通的 `is_error` Observation 回到模型那里，模型还可以重试（plan 0042 §11.1）。现在有五个测试用真实的 `task.cancel()` 钉住这个行为。

---

## 8. 审计 hook（audit.py）

`AuditHook` 为每次完成的工具调用写一条 `AuditRecord`。它只覆盖 `after_execute` 和 `on_failure`，从不改写输出，也不做任何决策。

### 8.1 启用

没有默认路径，指定一个路径就等于启用：

| 设置 | CLI flag | 环境变量 | 默认值 |
|---|---|---|---|
| `AppConfig.audit_log` | `--audit-log` | `OMICSCLAW_AUDIT_LOG` | `None`（不记录） |

```bash
oc cli --audit-log .omicsclaw/audit.jsonl
```

`build_hooks` 只在这个值被设置时挂载 `AuditHook(JsonlAuditSink(config.audit_log))`，否则返回空元组。`hook_tools` 拿到空链时**不做任何包装**，所以没有配置 hook 的部署，其对象图与 hooks 包出现之前完全一样，测试可以直接断言对象身份。

### 8.2 记录格式

每行一个 JSON 对象，key 排序，所以两条同形记录逐字节一致，diff 有意义：

```json
{"arguments_digest": "c9b64aaf75040a4f", "at": 1790166835.2684908, "detail": "write_file refused by RawDataGuard — data/raw/ holds raw sequencing output and is never modified", "outcome": "denied", "session_id": "", "tool": "write_file"}
{"arguments_digest": "4383b77fac14c9e5", "at": 1790166835.268734, "detail": "", "outcome": "ok", "session_id": "", "tool": "write_file"}
```

| 字段 | 内容 |
|---|---|
| `tool` | 工具注册名 |
| `outcome` | `AuditOutcome`：`ok`（工具正常返回）、`error`（工具抛异常）、`denied`（链中后面的 hook 拒绝）、`cancelled`（非 `Exception` 的 `BaseException`，如取消或 Ctrl-C） |
| `arguments_digest` | 原始 payload 的 SHA-256 前 16 个 hex 字符（`arguments_digest`），**不记录参数本身** |
| `at` | `time.time()` 墙钟时间，便于与 transcript 和外部日志对齐 |
| `session_id` | 从 tool context 的 `SESSION_ID_KEY`（`"session_id"`）读取；没有绑定时为空字符串。`entry/turn.py` 在每个 exchange 外绑定它，`tests/hooks/test_audit.py` 会把 `entry/turn.py` 当文本读取，校验两处拼写一致 |
| `detail` | `error` 时**只记异常类名**；`denied` 时记 hook 写的拒绝理由 |

`detail` 的这种不对称来自一个测试。早期版本记录 `ClassName: message`，`tests/entry/test_hook_wiring.py` 发现一次 `read_file` 失败把请求的路径写进了审计文件，因为工具的错误信息通常会引用出错的参数（`write_file` 引用路径，`bash` 引用命令，`web_fetch` 回显 URL）。审计文件比会话存在得更久，所以只保留类名这种固定词汇。拒绝理由是本部署的 hook 自己写的，所以保留。但如果 hook 在 `deny(...)` 里插入了参数内容，这些内容也会进入审计文件，这由 hook 作者负责。

**不记录耗时**：已经有两处在计时，`ToolResult.metadata["duration_s"]` 是工具本身的耗时，`EngineEvent.duration_s` 是包括审批等待在内的耗时。再加一个数字就会有第三个答案。

### 8.3 `JsonlAuditSink`

- 使用 JSON Lines 而不是 JSON 数组，因为进程中途被杀掉时，数组文件会变得无法解析；
- 首次写入时才创建目录，目录权限 `0o700`，文件通过 opener 以 `0o600` 创建，不存在先创建再 chmod 的时间窗口；
- 写入是阻塞的（append 模式下写一行短文本，与 `logging` 相同）。不能阻塞事件循环的场景需要另写一个 sink；
- 写入失败时**抛出异常**，由 `AuditHook._record` 捕获并记日志。sink 不能静默丢弃记录，否则空的审计文件和一台什么都没做的机器看起来没有区别。

`AuditSink` 是结构化 Protocol（`async def write(record)`），数据库、队列、测试里的 list 都可以作为 sink。

### 8.4 必须挂在链首

链是逆向收尾的，第一个挂上的 hook 最后收到通知，而且即使**它后面**的某个 hook 拒绝了调用，它也会收到通知。这是 `denied` 结果能出现的唯一途径。如果挂在链尾，拒绝记录会全部丢失，而拒绝恰恰是审计日志最需要记录的东西。`build_hooks` 因此把 `AuditHook` 放在最前面，把 `TracingHook` 追加在最后（让 span 只测量工具本身），`tests/entry/test_telemetry_wiring.py::test_the_audit_hook_is_first_and_the_tracing_hook_is_last` 钉住这个顺序。

`outcome_of` 是公开函数，因为 `omicsclaw/observability/hook.py` 的 `TracingHook` 也用它给 `tool.status` 分类。审计日志和 span 对同一次调用的结果判定因此不会不一致。

---

## 9. 写一个自定义 hook

示例：在多组学项目里，`data/raw/` 放的是测序仪的原始输出，任何情况下都不允许修改。

```python
import json
from omicsclaw.hooks import Hook, HookCall, HookDecision, allow, deny

class RawDataGuard(Hook):
    """Refuse writes under data/raw/: raw sequencing output is read-only."""

    async def before_execute(self, call: HookCall) -> HookDecision:
        if call.name not in {"write_file", "edit_file"}:
            return allow()
        try:
            path = json.loads(call.arguments).get("path", "")
        except ValueError:
            return allow()
        if str(path).startswith("data/raw/"):
            return deny("data/raw/ holds raw sequencing output and is never modified")
        return allow()
```

继承 `Hook` 可以获得另外两个方法的 no-op 实现。不继承也可以，只要结构上满足 `ToolHook`；`HookedTool.__init__` 会用 `isinstance(hook, ToolHook)` 检查，缺少任何一个方法时在**装配时**抛出 `TypeError`，不会等到运行中途。

挂到应用上。注意 `hooks=` 会**替换**整条配置链，所以需要自己把审计 hook 和 tracing hook 放回去，并保持"审计在首、tracing 在尾"：

```python
from omicsclaw.entry import build_app
from omicsclaw.entry.assembly import build_hooks
from omicsclaw.observability import build_telemetry

telemetry = build_telemetry()                       # 读 OTEL_* 环境变量
chain = (
    *build_hooks(config),                           # AuditHook（设置了 audit_log 时）
    RawDataGuard(),
    *telemetry.tool_hooks(),                        # TracingHook（可观测性启用时）
)
app = build_app(config, hooks=chain, telemetry=telemetry)
```

`open_app` 接受同样的 `hooks=` 和 `telemetry=` 参数。`hooks=()` 表示即使配置要求了 hook，也一个都不挂。

写 hook 的注意事项：

- **不要记录 `call.arguments`**。它是 `bash` 命令行、`write_file` 的内容、`web_fetch` 的 URL，可能包含样本名或患者编号。
- 需要严格保证的拦截应该写成权限规则（`deny: ["write_file(data/raw/*)"]`），因为规则是 fail-closed 的。hook 自身出故障时会放行。上面的示例更适合演示机制，或者放在需要自定义逻辑（比如解析 `bash` 命令）的地方。
- **不要在 hook 里修改参数，除非你愿意承担这个风险**：改写后的参数不会被 gate 重新判定。
- 要想看到被其他 hook 拒绝的调用，就挂在链的前面；要想只测量工具本身，就挂在最后。
- `hook_tools` **不是幂等的**（`gate_tools` 是）。套两层 hook 就是两条不同的链；而 gate 套两层会问两次人。

---

## 10. 子代理

子代理的 registry 由 `ChildRunner._child_registry` 从父 registry 中挑选**已经 gate 过、已经挂好 hook 的同一批对象**重新注册。所以子代理的工具调用会经过和父代理相同的 hook 链：同一个审计 sink，同一个 tracing hook。`task` 工具本身也通过 `gate_tools(hook_tools((TaskTool(...),), chain), gate)` 挂载，因此一次委派在审计日志里也会留下一条记录。

---

## 11. 已知限制

- **规则拒绝和 gate 自己提问后被拒的调用，都不会出现在审计日志里。** gate 在 hook 链外面，这类拒绝只在 `omicsclaw.permission.gate` 的日志里有一条 warning（`permission denied: tool=… source=…`）。只有"工具自己提问后被人拒绝"会以 `error` / `ApprovalDenied` 的形式出现在审计日志中。
- **hook 改写的参数不会被 gate 重新判定**，这是链放在 gate 内部的代价。
- **hook 是 fail-open 的**，不能作为强制安全边界使用；强制拦截应该写成权限规则。
- **审计没有 `ToolCall.id`**，只能用参数摘要和时间与 transcript 对齐；参数完全相同的两次调用摘要也相同。
- **`JsonlAuditSink` 是阻塞写入**，高并发或网络文件系统上需要自己写一个异步 sink。
- **`Offloader` 只在预算压力下 offload**：它由预算压力驱动（压缩阶段），不会对大结果无条件 offload；它也没有 `read_file` / `write_file` / `edit_file` 豁免名单。所以不足以把会话推过 `Pressure.WARN` 的中等大小结果（例如一个大的 `.h5ad` 摘要输出）每轮都会被完整重发，用 `read_file` 读回的占位文件也可能被再次 offload。这些属于 `omicsclaw/context/` 的范畴，在 `omicsclaw/hooks/__init__.py` 中有记录。
- **目前唯一的配置开关是 `audit_log`**。其他 hook 只能以编程方式通过 `build_app(hooks=)` / `open_app(hooks=)` 挂载，没有配置文件或插件发现机制。
- `tests/entry/test_entry_is_the_top_layer.py` 的 `_LOWER_LAYERS` 清单里没有 `hooks`（plan 0042 §10 记录）。本层自己的 `test_hooks_is_a_leaf_layer.py` 约束更严格，所以这不构成漏洞，但那份清单不完整。

---

## 12. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/hooks/__init__.py` | 公共 API；三条设计决策 |
| `omicsclaw/hooks/base.py` | `HookCall`、`HookAction`、`HookDecision`、`allow`、`deny`、`ToolHook`、`Hook`、`HookDenied` |
| `omicsclaw/hooks/chain.py` | `HookedTool`、`hook_tools`、`_resolved` |
| `omicsclaw/hooks/audit.py` | `AuditHook`、`AuditSink`、`JsonlAuditSink`、`AuditRecord`、`AuditOutcome`、`outcome_of`、`arguments_digest`、`SESSION_ID_KEY` |
| `omicsclaw/observability/hook.py` | `TracingHook`（第二个内置 hook） |
| `omicsclaw/entry/assembly.py` | `build_hooks`、`build_app(hooks=)`、`open_app(hooks=)`、`_is_bash` 循环拆包 |
| `omicsclaw/entry/config.py` | `AppConfig.audit_log`（`--audit-log` / `OMICSCLAW_AUDIT_LOG`） |
| `tests/hooks/test_chain.py` | 顺序、配对不变量、包容、取消、参数改写不被重新判定 |
| `tests/hooks/test_audit.py` | 记录格式、四种结果、摘要、会话 key 拼写 |
| `tests/hooks/test_hooks_is_a_leaf_layer.py` | 依赖方向 |
| `tests/entry/test_hook_wiring.py` | 装配：链在 gate 内部、两层包装下仍能识别 `bash`、审计不泄漏路径 |

参考：`docs/plans/0042-hooks-layer.md`；`docs/FRAMEWORK-REBUILD.md` Step 6.10。
