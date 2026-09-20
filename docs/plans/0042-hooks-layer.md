# 计划 0042 — `omicsclaw/hooks/`：工具调用拦截层

> 状态：**已实现并经两轮独立只读审核**（2026-09-20）。
> `tests/hooks/` 117 项 + `tests/entry/test_hook_wiring.py` 18 项全绿；
> 重构各层合计 **4068 passed / 9 skipped**，零失败。
> §7 记录实现期被自己的测试抓出的两个缺陷，§11 记录两轮审核的发现与返工
> ——正确性审核找出的两个取消语义缺陷是本步最严重的问题，已复现并修复。
> 编号原定 0041，因与并行会话的 `0041-cli-parity-with-harness9.md` 撞车而改为 0042。

参考实现：`/workspace/dataset/private/zhouwg_data/harness9`
（`internal/hooks/`、`internal/observability/hook.go`、`cmd/harness9/main.go:325-417`）。

## 1. 现状：缺的是**扩展点**，不是那四个 hook

harness9 的 `internal/hooks` 把**机制**和**四条策略**打包在一起。本仓库
重构到今天，那四条策略里有三条**已经各有归属**，只有机制一条没有：

| harness9 | 本仓库 | 谁实现的 |
|---|---|---|
| `hooks/hook.go`（拦截机制） | **缺** | 本计划 |
| `permission/hook.go` | `omicsclaw/permission/` | 计划 0038 |
| `hooks/danger_hook.go` | `omicsclaw/permission/danger.py` | 计划 0038 |
| `hooks/offload.go` | `omicsclaw/context/offload.py` `Offloader` | 第 5 步，**语义窄化见下** |
| `hooks/plan_writer.go` | `omicsclaw/planning/` | 计划 0039 |
| `observability/hook.go` | **缺** | 本计划 |

**其中 offload 这一行不是全覆盖，把话说清楚正是列这张表的意义。**
`Offloader` 搬的是同样的字节、写的是同样形状的占位符，但它由**预算压力**
在 compaction 阶段驱动（`Pressure.WARN` 及以上），而 `hooks/offload.go` 是
**每次工具返回都无条件**检查 10000 字符；而且它没有那份
`read_file`/`write_file`/`edit_file` 排除表。后果有二：一段"大但还不足以把
对话推过 WARN"的输出会在之后每一轮被原样重发；被 `read_file` 读回来的占位符
内容可能再次被 offload。两件事都归 `omicsclaw/context/` 管，不归本层——
这里只记录，不顺手改别人的包。

于是本计划的范围就被这张表定死了：**造机制 + 补可观测性那一条**，
其余三条一行都不重写。重写任何一条都会让同一个问题在一个部署里有两个答案。

两条现存证据说明这确实是被**显式推迟**的、而不是被遗忘的：

- `docs/plans/0031-entry-layer.md:1540`
  `| :325-338 | hooks：permission / danger / offload / observability | 不做（Q13） |`
- `omicsclaw/entry/assembly.py`（`build_registry` 的 docstring）已经把门留好了：
  *"`tools` is how **hooks**, permission wrappers, MCP tools and a sub-agent's
  narrowed set all arrive later without this function changing (plan 0031 Q13)."*

以及一条"没有它的代价"的现场记录：
`omicsclaw/entry/channel/telegram.py:758-761` —— *"plan 0031 has no audit log
yet, and inventing one here would be a second unowned place that writes about
users."*

## 2. 决策：装饰 Tool，不装饰 Registry

harness9 的 `HookRegistry` 包住 `tools.Registry`（`hooks/hook.go:28-38`）。
**本项目不照搬**，理由计划 0038 §2 已经写过一遍，这里不重新论证，只复述为什么
它对 hooks 同样成立：

引擎用 `isinstance` 探测 Registry 的两个可选 Protocol
（`ConcurrencyAwareExecutor`、`DeadlineAwareExecutor`），包装 Registry 的
东西必须同时转发 `is_concurrency_safe` 与 `use_timeout_pause`，**忘了不会报错**
——只会让人的审批时间重新被计进工具超时（defect R3）。harness9 没有这两个
Protocol，所以它没有这个雷。

于是形状与 `GatedTool` 一致：`HookedTool(inner: Tool, hooks)`，
`hook_tools(tools, hooks)`，Registry 本体不被包。

## 3. 决策：hook 装在 gate **内层**

组装顺序 `gate_tools(hook_tools(mounted, hooks), gate)`，即
`GatedTool(HookedTool(tool))`。对应 harness9 的链序
（`cmd/harness9/main.go:411-416`：411-412 是写明顺序的注释，413 建列表把
permHook 放在最前，414-416 才把 obsHook 追加到最后）。

三个后果，都写进了 docstring 并由测试钉住：

1. **权限先判。** 被规则拒掉的调用不会到达任何 hook——与 harness9 的
   observability hook 同样的盲区，同样的原因。
2. **hook 重写参数不会被重判。** gate 已经按模型发来的参数判过了。这是排序
   的**代价**而不是意外，`HookDecision.arguments` 的 docstring 把它写明，
   `tests/hooks/test_chain.py::test_a_rewrite_is_not_re_judged_by_the_permission_gate`
   把它钉住（同一个测试里还验证了那条规则**确实**会在模型直接请求时生效，
   免得这个测试变成"规则本来就是死的"）。
3. **hook 问不了人**（见 §4）。

## 4. 决策：决策词表只有 allow / deny，**没有 ask**

harness9 有三个动作（`hooks/decision.go:15-22`）外加两个 context key
（`approvedContextKey`、`explicitlyAllowedContextKey`），后者唯一的工作就是
阻止第三个动作把同一个人问两遍。本层**两个动作、零个 key**。

证据链：`GatedTool._run_settled` 在运行内层工具前用
`use_effective_policy` 发布一个 `approval_mode=AUTO` 的策略；
`require_approval` 第一件事就是读 `effective_policy()`
（`omicsclaw/tools/context.py:593-594`），读到 `AUTO` 立刻返回。
hook 跑在 gate 内层，所以从链里发出的提问**会自己回答自己**。

这不是能力缺失，这正是 harness9 `withExplicitlyAllowed` 的语义
——而且是**复用已有机制**达成的，`tools/context.py` 一行不改。
代价是本层不能新增"问人的理由"；那件事有两个现成扩展点
（`Rule` 和 `DangerPattern`），加第三个会让"我为什么被问"有三个答案。

`tests/hooks/test_hooks_is_a_leaf_layer.py::test_the_package_does_not_reimplement_ask`
直接断言 `HookAction` 只有两个成员——断言枚举而不是断言 docstring，
因为第二份实现恰恰是不会去动 docstring 的那种改动。

## 5. 决策：三个方法，不是两个

```python
async def before_execute(self, call: HookCall) -> HookDecision
async def after_execute(self, call: HookCall, output: str) -> str
async def on_failure(self, call: HookCall, error: BaseException) -> None
```

harness9 两个方法能覆盖成功与失败，是因为它的内层 `Execute` **返回**
`ToolResult{IsError}` 而不是抛异常。Python 这边工具是**抛**的，把异常压平成
字符串塞进一个签名会丢掉类型——而 `ToolRegistry.execute` 给模型的错误文本
正是用类型名拼的。所以失败单独成一个方法，并且返回 `None`：hook 改不了一个
失败，**一个会被静默忽略的返回值是没人能测的契约**。

`Hook` 基类提供三个 no-op，只关心一件事的 hook 只覆盖一个方法。
`ToolHook` 仍是结构化 Protocol，不继承也算 hook。

### 5.1 配对不变量（比参考实现强的地方）

**每个"放行了"这次调用的 `before_execute`，恰好配到一次 `after_execute`
或 `on_failure`**——覆盖四种结局：后面的 hook 拒绝、工具抛异常、turn 被
取消（取消落在工具上，或落在另一个还在决策的 hook 上）。
`hooks/hook.go:70-75` 在 deny 时直接 return，已经跑过的 hook 一个收尾回调
都拿不到，在 `BeforeExecute` 里开了 span 的 hook 就此泄漏。

措辞是"**放行了**"而不是"返回了"，差别就一种情况：**主动 deny 的那个
hook 自己拿不到收尾回调**。它拒绝的时候还没决策完，没有东西需要收尾
（`test_the_hook_that_denied_is_not_told_about_its_own_denial` 钉住）。

实现上：`decided` 列表只在 hook 放行之后才 append，而 deny 是 `raise` 而
不是 return，于是它和"工具抛异常""决策期被取消"共用同一个 `except
BaseException` 处理器——**一条路径，而不是三条各自可能写漏的路径**。
第一版是两个分开的块，其中一个没有处理器，代价见 §11。

## 6. 决策：hook 自身的失败被**包容**，方向与 gate 相反

`omicsclaw/tools/registry.py:330-332` 已经写死了合同：
*"Lifecycle hooks, when they arrive, wrap this call from outside the `try`
below — a hook that raised inside it would be reported to the model as the
tool's own failure."*

装饰 Tool 意味着这条链跑在那个 `try` **里面**，所以合同换个方向履行：
链把每一次进 hook 的调用都包起来，抛了就记日志、当成 `ALLOW` 继续。
一个坏掉的观测器不许弄坏一个好用的工具。

**fail-open，和 gate 的 fail-closed 刻意相反**：`require_approval` 问不到人
就拒绝，因为"没有同意"不等于"同意"；hook 不是同意，它是部署自己加的介入。
想让"检查跑不了就拦住"的部署去写权限规则——那才是 fail-closed 的那一层。

只有一种例外：显式 `deny` 抛 `HookDenied`，形状与 `PermissionDenied` 一致。

不被包容的两样：工具自己的异常**原样**上抛（hook 不许调包一个失败），
`BaseException`（取消、Ctrl-C）同样上抛但**仍然通知**。

`_notify` 只 `except Exception`，**不**捕 `BaseException`——第一版捕了，
理由写成"在已取消的 Task 里 await 会再次抛 `CancelledError`"，这条前提是
**错的**（捕获一次取消并不会让后续 await 自动再抛）。它实际吞掉的是通知
期间到达的**一次新的取消**，后果见 §11。现在的规则是：**取消压过正在
上报的那个失败**，还没被通知到的 hook 少一次通知，这是两害相权的轻者。

## 7. 实现期被自己的测试抓出的两个缺陷

**其一（我自己引入的，静默）。** `entry/assembly.py::_is_bash` 只剥一层
`GatedTool.inner`。装上 hook 链后 `bash` 变成
`GatedTool(HookedTool(BashTool))`，一层剥完拿到的是 `HookedTool`，
`isinstance(..., BashTool)` 返回 False → `_apply_bash_policy` 找不到 bash →
`bash_policy` 不被调用 → **沙箱无网络时的免审批静默失效**，不抛异常、
不打日志、工具本身的测试全绿。改为循环剥到底，
`tests/entry/test_hook_wiring.py` 里有正反两条钉子
（正：两层包装后仍认得出；反：一层剥法确实会漏）。

**其二（设计缺陷，隐私）。** `AuditRecord.detail` 最初记的是
`ClassName: message`，"与模型读到的措辞一致"。
`test_the_audit_file_is_written_when_a_tool_actually_runs` 立刻抓到：
`read_file` 失败的消息里**带着它打不开的那个路径**。这类消息普遍如此——
`write_file` 带路径、`bash` 带命令行、`web_fetch` 带 URL。于是
**错误只记类名**（类名是固定词表，任何参数都到不了），完整文本本来就在
transcript 里，而 transcript 由会话所有者掌握、不像审计文件那样长期留存。

**拒绝是例外**，区别在于那段字是谁写的：`HookDenied` 的理由是**本部署自己的
hook 代码**拼的，记下来等于记下部署对自己的陈述；而且没有理由的审计行没人能
据此行动。唯一要知道的：把参数插进 `deny(...)` 的 hook 会把参数写进这个文件,
那是 hook 作者的决定，本层不替他做。

## 8. 交付物

```
omicsclaw/hooks/
├── __init__.py   公共面 17 个名字，含那张"三条已有归属"对照表
├── base.py       HookCall / HookAction / HookDecision / ToolHook / Hook / HookDenied
├── chain.py      HookedTool / hook_tools
└── audit.py      AuditOutcome / AuditRecord / AuditSink / JsonlAuditSink / AuditHook
```

`AuditHook` 是 harness9 `observability/hook.go` 的等价物，去掉 OTEL：
本层只 import 标准库 + `omicsclaw.schema` + `omicsclaw.tools`，记录交给
调用方提供的 `AuditSink`。想要 OTEL 的部署写十几行 sink，不想要的不背依赖。

**不记耗时**：已经有两个层在计时（`ToolResult.metadata["duration_s"]` 和
`EngineEvent.duration_s`，语义不同，后者才走到 surface），第三个数字就是
第三个答案。

**不记参数**，只记 `sha256[:16]` 摘要——`permission/gate.py` 对同样的字节
已经立了"绝不记日志"的规矩，审计文件比会话活得久，规矩只该更严不该更松。
摘要足够做它本该做的两件事：与 transcript 对上号、区分同一工具的两次调用。

接线（`omicsclaw/entry/`）：

- `AppConfig.audit_log: Path | None = None`，`--audit-log` / `OMICSCLAW_AUDIT_LOG`。
  **唯一一个没有默认位置的路径配置**：规则文件不存在＝空规则集，不花成本；
  而没人要求就出现的审计文件是一份关于人的文件，写它只因为没人说不。
- `build_hooks(config) -> tuple[ToolHook, ...]`，默认返回 `()`。
- `build_app(..., hooks=None)` / `open_app(..., hooks=None)`：`None` 取配置，
  显式序列替换，`()` 是"配置要了但我不要"。
- `hook_tools(tools, ())` **返回原对象**：零 hook 的部署对象图分毫未动。

## 9. 验证

```
tests/hooks/                       117 passed
tests/entry/test_hook_wiring.py     18 passed
重构各层（schema provider engine tools context skills entry
mcp memory permission planning launch sandbox hooks）
                                  4068 passed / 9 skipped，0 failed
```

排除 `tests/tools/test_workspace.py`——它读一个已被删除的
`omicsclaw/services/path_validation.py`，是与本次改动无关的既有 collection error。

## 10. 留给别的 lane 的一条观察

`tests/entry/test_entry_is_the_top_layer.py:39` 的 `_LOWER_LAYERS` 枚举里
没有 `permission`、`planning`、`hooks`。对本层没有实际漏洞——
`tests/hooks/test_hooks_is_a_leaf_layer.py` 用语法与行为两种方式禁掉了
`omicsclaw.entry`，比那条检查更严——但那张清单目前不完整。
按"一步只动自己的包"的规矩，这里只记录，不顺手改别人的清单。

## 11. 两轮独立只读审核的发现与返工

按重建的第 2 条规矩，写代码的 agent 不评自己的活。两轮审核（均为
sonnet 5、只读）分别做正确性与 harness9 对等性。

### 11.1 正确性审核：两个真缺陷，都在取消语义上

两条都由审核方给出可复现脚本，我用**同一段脚本**先复现、再验证修复。

**缺陷 A —— `_notify` 吞掉一次真实的取消。** 第一版 `_notify` 写了
`except BaseException: ... break`，注释说"在已取消的 Task 里 await 会再次
抛 `CancelledError`"。**这条前提是错的**：捕获一次 `CancelledError` 之后
继续 await 别的东西并不会自动再抛。它实际拦住的是通知期间到达的**一次
新的、独立的**取消（turn 关闭、`wait_for` 超时、supervisor shutdown）。
吞掉之后 `_notify` 正常返回，`execute` 的裸 `raise` 重抛的是**工具原来
那个**异常。

代价在下游：`ToolRegistry.execute` 只 catch `Exception` 不 catch
`BaseException`，就是为了让取消不能伪装成 Observation
（`tools/registry.py:314-321`）。而本层把取消换成了一个普通
`ValueError`，于是它被 registry 照单全收、包成 `is_error=True` 返回给
模型——**一个本该终止的 turn 变成了"工具失败了，你可以重试"**，正好从
那道检查的侧面绕了过去。

修复：`_notify` 只 catch `Exception`。**取消压过正在上报的那个失败。**

**缺陷 B —— 决策阶段没有异常安全网。** `execute` 原本是两个块：决策
循环裸跑，只有内层工具调用被 `try/except BaseException` 包着。于是某个
hook 的 `before_execute` 抛 `BaseException`（真取消落在它的 await 上、
Ctrl-C）时，异常直接穿出整个 `execute`，**链上更早已经放行的 hook 一个
收尾回调都拿不到**——正好打破 §5.1 那条本层拿来当卖点的不变量，而且是
在"补了参考实现 deny 分支那个洞"之后，在一个没人看过的对称位置。

修复：决策循环与工具调用合进**同一个** `try`，deny 改成 `raise` 而不是
`return`，三条失败路径共用一个处理器。

**测试盲区才是根因。** 这个文件里原有的取消测试**全部**是手写
`raise asyncio.CancelledError()`，没有一个用真正的 `task.cancel()`——而
两个缺陷都只有后者能触发。现在有五条用真 `task.cancel()`。

**一条钉住了错误行为的测试被改写而不是删除**：
`test_a_cancellation_during_notification_does_not_replace_the_original`
当初把"吞掉取消、保留原异常"断言成了正确行为。改写后的版本在自己的
docstring 里写明当初错在哪、以及它再次变红时该问什么问题；旁边新增
`test_a_swallowed_cancellation_would_reach_the_model_as_a_retryable_error`
把代价钉在它实际发生的那一层（registry）上。

**第三条（措辞，已采纳）**：`ToolHook` 的不变量原文写"每个**返回了**的
`before_execute`"，而主动 deny 的 hook 自己是拿不到回调的。已按 §5.1
改为"**放行了**"并写明那一个例外。

### 11.2 对等性审核：一条过窄引用 + 一条说过头的覆盖声明

- `cmd/harness9/main.go:413` 只有 `mainHooks := []hooks.ToolHook{permHook,
  dangerHook, offloadHook}`，能证"permHook 在前"，证不了"obsHook 在后"
  （那在 414-416）。已改引 `411-416`。本仓库的规矩是
  **没核对过的 file:line 引用就是缺陷，哪怕它周围那句话是对的**。
- `hooks/offload.go` 那行被标成"已覆盖"，实际是**语义窄化**。已在 §1
  展开（触发时机 + 缺排除表），并同步到 `omicsclaw/hooks/__init__.py`
  的对照表与 `docs/FRAMEWORK-REBUILD.md`。
- 计划文档当时写的 `tests/hooks/` 108 项已过时（改动后实为 117）。已更新。
- 其余引用逐条核对全部准确；两轮审核都确认 `_is_bash` 的修法正确，
  且**没有遗漏的同类"剥一层就判断"的地方**（两位审核各自搜过
  `omicsclaw/entry/`、`omicsclaw/launch/`）。

### 11.3 我自己在返工轮补上的一条

hook 若写成同步 `def`，`await` 一个返回值会抛 `TypeError`，被本层包容成
"allow"——于是**一个同步 hook 会被挂上、会注册、然后什么都不做**，只在
没人看的日志里留一行。现在按 `require_approval` 对审批通道的既有写法
（`tools/context.py:614-615`）只 await 可 await 的东西。同步的 `deny`
本来会静默失效，那一半是安全问题而不只是 no-op。
