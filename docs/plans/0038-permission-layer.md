# 计划 0038 — `omicsclaw/permission/`：Human-in-the-Loop 权限控制层

> 状态：**已实现并经两轮独立只读审核**（2026-09-20）。`tests/permission/`
> 262 项 + `tests/entry/` 增量 30 项全绿；重构各层合计 3301 passed /
> 3 skipped，与实现前的 3021 基线相比无回归。
> 编号原为 0037，因与并行进行的 `0037-launch-and-entry-points.md` 撞车而改为 0038。
> §7 记录实现期被自己的测试抓出的两个缺陷，§8 记录两轮审核的发现与返工。

参考实现：`/workspace/dataset/private/zhouwg_data/harness9`
（`internal/permission/`、`internal/hooks/`、`internal/engine/permission.go`）。

## 1. 现状：传输已通，决策缺位

重构后的新框架**已经有一套完整的审批传输链路**，这次不要重建它：

| 已有能力 | 位置 |
|---|---|
| 审批请求/决策类型、fail-closed 语义 | `omicsclaw/tools/context.py` |
| 审批通道（contextvars，按 Task 传播） | `ToolContext.approval` |
| 部署策略优先于作者策略（`_EFFECTIVE_POLICY`） | `ToolRegistry.execute` → `use_effective_policy` |
| 人类思考时间不计入工具超时 | `pause_tool_timeout` + `DeadlineAwareExecutor` |
| 请求/落定事件、Future 配对、超时即拒绝、退出即拒绝 | `omicsclaw/entry/approval.py` `ApprovalBroker` |
| 沙箱无网络时 `bash` 免审批 | `omicsclaw/entry/sandbox.py` `bash_policy` |

缺的是**决策层**。当前"要不要问人"只有一个输入：工具名对应的
`ToolPolicy.approval_mode`。由此产生四个真实缺口：

1. **粒度只到工具名。** `bash` 要么每条命令都问，要么全部放行。
   无法表达"`git status` 直接跑、`rm -rf` 直接拒"。
2. **没有"拒绝"这条路。** `ApprovalMode.DENY_UNLESS_TRUSTED` 只有在工具
   自己调用 `require_approval` 时才被送给通道，而且通道拿到它和 `ASK`
   完全一样；没有任何代码路径能在工具运行**之前**否决一次调用。
3. **没有全局权限模式。** 无法一句话切到"只读"或"受控环境全放行"。
4. **升级方向无效。** 若部署想把一个 `AUTO` 工具的某类参数升级为要审批，
   今天无处表达——这正是计划 0028 §4 Q5 记下的失败形状：
   *解析出了权限，但对执行没有影响*。

另有一个已被 `tools/context.py:14-23` 自己写明的缺口：没有
harness9 的 `approvedContextKey` / `explicitlyAllowedContextKey`，
所以**包装型工具会重复弹两次审批**。本计划的网关必须不制造这个问题。

## 2. 决策：网关建在 Tool 边界，而不是 Registry 边界

harness9 的做法是 `HookRegistry` 包住 `tools.Registry`（装饰 Registry）。
本项目**不照搬**，改为装饰单个 `Tool`。理由三条，都是本仓库自己的前车之鉴：

- **`build_registry` 的 docstring 明确警告过 R3 缺陷**：任何包住
  `ToolRegistry` 的东西必须同时转发 `use_timeout_pause` 与
  `is_concurrency_safe`，而两个 Protocol 都是 `runtime_checkable`、引擎用
  `isinstance` 探测——忘了转发**不会报错**，只会让人类的审批等待重新
  被计进工具超时。装饰 Tool 则完全绕开这个雷：Registry 本体不被包。
- **不必改任何既有叶子文件。** 装饰 Tool 之后，网关运行在
  `ToolRegistry.execute` **内部**，因此可以直接读 `effective_policy()`
  拿到部署已解析的策略，并用 `use_effective_policy` 重新发布一个
  `AUTO` 策略来告诉内层工具"这次已经定了，别再问"。
  这就是 harness9 `withApproved` / `withExplicitlyAllowed` 的等价物，
  而且复用的是既有机制，`tools/context.py` 一行不动。
- **拒绝的观测形状与既有一致。** 网关拒绝时抛
  `ApprovalDenied`，与工具自己被人拒绝时走的是同一条路，模型读到的是
  同一种 `is_error` 观测，而不是两种。

代价写明：一个绕过 `gate_tools` 直接注册的工具不受网关管辖。这是组合根
（`build_app`）的责任，用测试钉住。

### 谁来问人

`ask` 这个结论**不等于网关自己弹窗**。基础工具自己的提示更好：`edit_file`
展示 **diff** 而不是参数、`web_fetch` 展示完整 URL —— 这是计划 0029
写下的安全属性："当人的阅读就是控制手段时，他读到的必须就是将要发生的事"。
抢走这些提示换一个通用提示是降级。

所以规则是：**除非工具声明自己会问，否则网关问**。声明字段是
`ToolPolicy.prompts_for_itself`，默认 `False`（即网关问）。两种情况下
即使声明了也由网关问：

- 工具这一次会**自我放行**（已解析 `approval_mode` 是 `AUTO`，被规则升级为
  ask）。不问就是"有解析、无效果"。
- **高危模式命中**，此时"危险在哪"这个理由是匹配的全部价值。`bash` 本来也会问，
  但它只会问"要执行这条命令吗"，不会说"这会删掉整个根目录"。

> 这个字段不在原始设计里，是实现期被自己的测试逼出来的 —— 见 §7.2。

### 决策流水线

每次调用按顺序求值，**第一个匹配者胜出**：

```
BYPASS_ALL 模式        → ALLOW（连 deny 规则都不查，仅受控环境用）
READ_ONLY 模式         → 除显式声明 read_only=True 者，全部 DENY
deny 规则命中          → DENY
allow 规则命中         → ALLOW
ask 规则命中           → ASK
bash 高危模式命中      → ASK（携带风险级别与原因）
AUTO_APPROVE 模式      → ALLOW
                       → 落回工具自己的 approval_mode
```

三种结论的执行动作：

- **DENY** — 抛 `PermissionDenied`（`ApprovalDenied` 的子类），内层工具
  从不运行。
- **ALLOW** — 以 `approval_mode=AUTO` 的策略运行内层工具，于是它自己的
  `require_approval` 立即返回通过，不弹窗。这就是"`bash(git *)` 白名单"
  和"总是允许"能生效的那根线。
- **ASK** — 三个条件同时成立时网关**让路**，由工具自己问（见上文「谁来问人」）：
  工具声明了 `prompts_for_itself`、这一次它确实会问（已解析
  `approval_mode` 不是 `AUTO`）、且理由是它本来就知道的（来源不是 danger）。
  否则网关自己问，问完发布 `AUTO` 策略，内层不再重复问。

## 3. 交付物

### 新增包 `omicsclaw/permission/`（叶子邻接层）

允许导入 `omicsclaw.schema` + `omicsclaw.tools` + 标准库，其余一律禁止。
白名单与 `omicsclaw/skills/` 同宽，理由同类：它必须说
`ToolPolicy` / `ApprovalMode` / `RiskLevel` 这套词汇。

| 模块 | 职责 |
|---|---|
| `modes.py` | `PermissionMode`：`DEFAULT` / `AUTO_APPROVE` / `READ_ONLY` / `BYPASS_ALL` |
| `rules.py` | `Verdict`、`Rules`（有序、首个匹配胜出）、模式匹配、JSON 读写（原子替换 + 0600/0700）、`RuleStore`（每次查询重读文件） |
| `danger.py` | `bash` 高危模式表 → 升级为 ASK |
| `gate.py` | `PermissionGate`（求值 + 执行）、`GatedTool`（Tool 装饰器）、`gate_tools` |

### 修改（既有文件，最小面）

- `omicsclaw/entry/config.py` — 新增 `permission_mode`、`permission_rules`
  两个字段与对应 flag/env（`--permission-mode` / `--permission-rules`、
  `OMICSCLAW_PERMISSION_MODE` / `OMICSCLAW_PERMISSION_RULES`），新增
  `permission_rules_path()`，默认 `<workspace>/.omicsclaw/settings.json`。
- `omicsclaw/entry/assembly.py` — 新增 `build_permission_gate`；`build_app`
  里用 `gate_tools` 包裹**全部**挂载工具（含调用方自带工具与 MCP 工具）；
  `_apply_bash_policy` 改为透过包装层识别 bash 并**回填包装层**；
  `AgentApp` 增加带默认值的 `permission` 字段；装配日志加上 posture。
- `omicsclaw/tools/base.py` — `ToolPolicy` 新增第九个字段
  `prompts_for_itself: bool = False`，归类为 *claim*。
- 五个内置工具 + `mcp_tool.py` 的 `_POLICY` 声明 `prompts_for_itself=True`。

**不导出到 `omicsclaw.entry`**：`PermissionMode` 定义在
`omicsclaw.permission`，从 entry 再导一次就会给一个名字两条导入路径。
`Pressure`（来自 `omicsclaw.context`）已有同样的先例。

`omicsclaw/launch/_grammar.py` 无需改动：部署 flag 原样透传给
`resolve_app_config`。

### 测试

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/permission/test_danger.py` | 98 | 命中、**不误伤**、严重度优先、命令名边界 |
| `tests/permission/test_rules.py` | 57 | 语法、优先级、匹配语义、JSON 往返、原子写、目录权限、热加载 |
| `tests/permission/test_gate.py` | 43 | 三种结论的执行效果、并发隔离，重点在收紧方向 |
| `tests/permission/test_permission_is_a_leaf_layer.py` | 32 | 分层探针（抄 `tests/skills/` 那份已修复版），含子进程行为探针 |
| `tests/permission/test_modes.py` | 20 | 四个模式各有不同且可测的效果 |
| `tests/permission/test_foundation_tools_keep_their_prompts.py` | 12 | 用**真实**工具验证 `prompts_for_itself` 声明属实 |
| `tests/entry/test_permission_wiring.py` | 28 | 组合根义务：没有任何工具能绕过网关进 registry |
| `tests/entry/test_cli_repl.py` 增量 | 2 | 「总是允许」从按键到规则文件、再到下次不再问 |

几条值得单独点出的：

- **收紧方向**优先。规则把 `AUTO` 工具升级为 ASK 时必须真的弹窗、拒绝时必须
  真的拦住（计划 0028 §4 Q5：放宽方向的测试通过什么也证明不了）。
- **不误伤占了 `test_danger.py` 的一半**。参考实现会在
  `sort | shuf`（撞 `| sh`）、`2> /dev/null`（撞 `> /dev/`）、
  `openssl enc`（撞 `nc `）上弹窗 —— 三个都是 omics 流水线里的日常命令，
  每个都有一条对应的测试。
- **声明用行为验证，不用读声明**。`prompts_for_itself=True` 是个断言，
  所以那 12 项拿真实工具配一个"一律拒绝"的通道跑，逐个断言它确实停下来了。
  拒绝路径让这个探针既便宜又安全：`require_approval` 在任何 socket、
  子进程、文件操作之前就抛了。

## 4. 对参考实现的刻意偏离（逐条给理由）

| harness9 | 本实现 | 理由 |
|---|---|---|
| 装饰 `tools.Registry` | 装饰 `Tool` | 绕开 R3 双 Protocol 转发雷（`isinstance` 探测，忘了转发**不报错**，只是把人的审批时间重新计进 `tool_timeout`）；且网关跑在 `registry.execute` 内部，能直接读到已发布的策略解析结果，不必二次推导 |
| `PermissionModeAutoApprove` / `ReadOnly` 是**死枚举**（全仓仅 `stream.go:178` 读过 `BypassAll`） | 四个模式都有效果，且 `test_no_two_modes_agree_on_everything` 钉住"两个模式不能塌成一个" | 计划 0029 的"从 Go 搬来的死代码"陷阱；一个读起来像安全控制、实际什么都不做的枚举值，比没有这个值更糟 |
| `DangerHook` 在默认接线下**完全不可达**（permission hook 走 allow/ask 都会打 `withExplicitlyAllowed`/`withApproved`，`hook.go:87` 读到就跳过 danger 的 Ask） | 高危模式是**同一条流水线的第 4 站**，恰好在"没有任何规则提到这次调用"时生效 | 搬结构是资产，这里出问题的是**接线**。也是为什么 `Rules.evaluate` 未命中返回 `None` 而不是 `ask` |
| `Evaluate` 未命中返回 `ask` | 返回 `None` | 把"没有规则提到它"和"要问人"混为一谈，导致没有规则文件的 harness9 进程**每一次工具调用都弹窗**，也导致它自己的高危模式永远不可达 |
| 匹配大小写不敏感（`EqualFold` + `ToLower`） | **规则**大小写敏感，**高危模式**大小写不敏感 | 两者方向相反：高危模式只能收紧，放宽覆盖面是免费的；而大小写不敏感的 **allow** 规则授予的比作者写下的多，且 registry 本身按名字精确查表 |
| 无通配符时 `strings.Contains` | **精确相等** | `allow: ["bash(ls)"]` 在子串语义下会放行 `rm -rf /; ls`。便利性出现在放宽方向就是漏洞 |
| 额外再做一遍**逐词** `filepath.Match` | 不做 | 同一个漏洞的另一条路：`allow: ["bash(ls*)"]` 会放行任何含 `ls` 开头词的命令 |
| `filepath.Match`：`*` 不跨 `/`，故需首/尾星号快捷路径 | `*` 跨任意字符，`fnmatchcase` 一条路走完 | Go 的语义是文件路径遗留，漏到命令行匹配上就是负债 —— `bash(git *)` 能匹配 `git log -- a/b/c` 在 Go 里靠的是尾星号捷径兜底，而非 glob 本身 |
| 只为 `bash` 特判 `command` 字段，其余工具匹配原始 JSON | **从工具自己的 JSON Schema 推导**：第一个 `required` 且 `type: string` 的属性 | 一张要维护的名字表变成零耦合，且覆盖全部 7 个工具而非 1 个。更关键的是让 allow 规则名副其实：`write_file(*/tmp/*)` 匹配 `path` 而不会误撞 `content` |
| "总是允许"写 `bash(*<首词>*)` | 写**精确字面量**，并把 `*?[` 转义成 `[*][?][[]` | 前缀/子串式记忆会放行 `git status; rm -rf /`。点"总是允许"的人是在回答眼前这一次 |
| 未校验的键被忽略 | 拼错的 action 键、缺右括号的模式、标量写在列表位 —— 一律**在启动时报错** | 拼错 `"denied"` 会让整张 deny 表静默失效，而文件读起来仍像一份黑名单 |
| `SaveRules` 直接覆写 | 临时文件 + `os.replace` 原子替换，`0600`/`0700` | 步骤 4.5 的 `edit_file` 教训用在内容是安全控制的地方：`O_TRUNC` 在写第一个字节前就清空了文件 |
| `hooks` 包承载通用双向拦截器（`AfterExecute`、`ModifiedArgs`） | 只做权限，不做通用 hook | 本次任务是权限。通用 hook 没有第二个使用者，而 `ModifiedArgs`（执行前重写参数）在本框架里会直接破坏"人读到的就是将要发生的事" |
| 高危模式 19 条子串 | 21 条**正则**，逐条在 Linux 上复核；另加 5 条外传模式 | 计划 0027 的教训：**搬结构是资产，搬字面量是负债**。外传那 5 条是 `CLAUDE.md` 第一条规则（遗传数据不得离开本机）落到 shell 上的写法，参考实现里一条都没有 |
| `READ_ONLY` 靠"工具名单 + 判断 bash 命令是否写" | 除显式 `read_only=True` 者一律拒 | "这条 shell 命令会不会写"是不可判定的；而"不能凭一个没人写过的 `False` 授权"反过来用在**拒绝**上才是正确方向 |

## 5. 已知风险与代价（都写进了对应模块的 docstring）

- **装饰 Tool 的代价**：绕过 `gate_tools` 直接注册的工具不受管辖。这是组合根的
  义务，由 `tests/entry/test_permission_wiring.py` 钉住。失效方式很安静 ——
  未被包的工具照样能跑、照样自己问，只是不再查规则文件和高危模式。
- **`READ_ONLY` 会拒掉 `web_search`**：它没有也不可能声明 `read_only=True`。
  这是 fail-closed 的正确方向，但与 harness9 只拦文件写的直觉不同。
- **`prompts_for_itself=True` 是断言，不是保证**。声明了却不问的工具会绕过网关。
  用 `test_foundation_tools_keep_their_prompts.py` 拿真实工具做行为验证顶住，
  而不是靠读声明。
- **规则文件每次调用都重读**（参考实现同样如此）。不做 mtime 缓存，因为缓存会
  引入同一秒双写漏掉的问题，而文件不到 1 KB、读一次远小于一次模型往返。
  启动时读不通就报错，运行中读不通则保留上一份好规则并告警。
- **规则 ASK 落在自带提示的工具上时，提示会被换成网关的通用提示**。
  这是规则作者主动要求的网关，可接受；但高危模式命中时网关必须自己问，
  所以 `bash` 的 cwd/timeout 上下文会让位给"危险在哪"。

## 6. 参考实现里被发现的三处问题

读 harness9 时发现的、影响到本实现设计的三点，都已在上表列出理由，此处汇总：

1. **`DangerHook` 是死代码。** `main.go:417` 的顺序是 permission → danger，
   而 permission hook 无论走 allow 还是 ask 都会打上
   `withExplicitlyAllowed` / `withApproved`，`hook.go:87` 读到这两个标记就跳过
   后续 hook 的 `Ask`。19 条高危模式在其默认接线下一条也到不了用户面前。
2. **`AutoApprove` / `ReadOnly` 是有名无实的枚举值。** 全仓只有
   `stream.go:178` 读过 `permissionMode`，且只判 `BypassAll`。
3. **没有规则文件时每次工具调用都弹窗。** `Evaluate` 未命中返回 `ask`，
   而 `NewFileHook` 在文件不存在时给出空规则集。

## 7. 实现期被测试抓出的两个真实缺陷

两个都是自己写的测试抓的，都不是"测试写错了"，记在这里因为它们各自是一类
**形状**而不是一次性问题。

### 7.1 危险模式表按主题分组，而 `inspect` 取首个匹配

`chmod -R 777 . && git push` 同时命中 HIGH 的递归 chmod 和 MEDIUM 的
`git push`。由于表按主题（破坏性 / RCE / 外传 / 权限）分组、外传组在权限组之上，
首个匹配返回的是 `git push` —— 报给人的是"推送到远端"，把"给所有人全权限"
盖住了。

修法不是重排表，而是把 `inspect` 改成**取最严重匹配**（同级取靠前者）。
理由是正确性不该依赖源码顺序：分组是二十多条正则可审计的前提，而为可读性
重排一次就静默改变提示内容，是没人会在 review 里发现的。

顺带发现一个语言陷阱：`RiskLevel` 是 `StrEnum`，`>` 按**字母序**比较，
于是 `"medium" > "high"` 为真。所以用显式 rank 表，而不是一个看起来对、
实际反的比较。

### 7.2 `policy=ASK` 被当成了"工具会自己问"

`test_a_deployment_tightening_a_tool_to_ask_is_honoured` 用一个**不调用**
`require_approval` 的工具 + 部署侧 `approval_mode=ASK`，结果它跑完了，
一个人都没问到。

根因是网关原来从 `approval_mode is not AUTO` 推断"工具会自己问"。这是约定
而非保证：`approval_mode` 说的是**部署想要什么**，而一个从不调用
`require_approval` 的工具无论模式是什么都会照跑。于是网关恰好放过了它本该
拦住的那一类调用 —— 形状上正是计划 0028 §4 Q5 的"有解析、无效果"。

修法是让工具**显式声明**：`ToolPolicy.prompts_for_itself`，默认 `False`。
方向是不对称的：这个字段的 `True` 含义是"让外层网关站开"，所以危险值是
`True`，必须被明确写下；忘了声明的代价是提示变朴素，而不是无人审批。

这也让迁移是渐进且始终安全的 —— 不声明 = 安全但提示朴素，声明 = 安全且提示丰富。

## 8. 两轮独立只读审核的发现与返工

按本重构的规矩，实现与评估分属不同 agent，评估只读、只报告，修复另起一轮。
两轮审核各自独立进行：一轮查正确性，一轮对照 harness9 查特性对等与内聚耦合。

### 8.1 审核结论

正确性审核：**无阻断级、无严重级问题**。特别核实并确认没有以下任何一种：
网关被绕过、同一次调用弹两次窗、人的审批等待被重新计进 `tool_timeout`。
代码里十余处 harness9 行号引用逐条核对**全部准确**；对
`test_every_mounted_tool_is_gated` 与 `test_an_ask_rule_on_an_auto_tool_really_does_ask`
做了 mutation 推演，确认它们真能抓回归。

对等性审核：**有条件通过**，条件是把「总是允许」接到至少一个 surface 上。
其余特性要么已实现、要么是有理由的刻意偏离、要么在参考实现里本就无效。

### 8.2 返工（全部已完成）

**1. 「总是允许」端到端不可达（对等性审核，真实缺口）**

`PermissionGate.remember()` / `RuleStore.remember()` 机制完整、有测试，但
全仓没有任何 surface 调用它 —— CLI 审批只有是/否两个选项。交付一段没有调用方的
能力，恰恰是本仓库反复警告的「别搬死代码」。

修法：
- `AgentApp.remember_approval(request)` —— 放在组合根，因为它是唯一同时知道
  registry 与网关的地方。让 surface 自己去拼 schema 容易拼错，写出一条
  `resolve()` 永不命中的规则。
- CLI 审批改为三选一 `[y/N/a=always]`，并把落地结果（成功 / 无处可写 / 写失败）
  显式打在屏幕上 —— 一个被告知「不会再问」却又被问的人会不再相信这个提示。
- **没有**给 `ApprovalDecision` 加 `remember` 字段（harness9 的
  `ApprovalResponse.Remember` 是这么做的）。surface 同时持有请求和网关，自己调用
  即可；给 `omicsclaw/tools/` 的类型加一个只有权限层能兑现的字段是反向耦合。

**2. `save_rules` 多级目录权限（正确性审核，已复验）**

`Path.mkdir(parents=True, mode=...)` 只对最深一级应用 `mode`，中间层用默认
`0o777 & ~umask`。实测 `root/a` 是 `0o755`、只有 `root/a/b` 是 `0o700`，
而 docstring 承诺的是整条路径 owner-only。原测试没抓到，是因为 `tmp_path`
已存在、只新建了一级，根本没走到递归分支。

修法：`_make_owner_only()` 逐级 `mkdir(mode=...)` 再 `chmod`（`mkdir` 的 mode 会被
umask 削减，只会更窄不会更宽，所以补一次 `chmod` 让承诺精确）。新增两条测试：
一条走三级递归、一条确认**已存在**的目录不被重新收紧 —— 这个函数负责创建，
不负责改别人搭好的目录树。

**3. 危险模式假阴性（正确性审核）**

以下命令全部返回"未命中"，而它们与 `rm -rf` 同级或更适合提示：
`shred`、`truncate -s 0`、`find -delete`、`find -exec rm`、`xargs rm`、
`> /etc/passwd`、以及**全部 `ssh` 通道**。最后一条最要紧：外传组里有
`scp`/`rsync`/`curl` 上传/`nc`，唯独漏了最常见的 `ssh host 'cat > out' < 文件`，
而 `CLAUDE.md` 第一条规则正是遗传数据不得离开本机。参考实现同样没有。

修法：新增 8 条正则，表从 21 条增至 28 条，每条配正反两向测试。

**4. 命令名边界的假阳性（正确性审核）**

`\b` 把连字符当词边界，于是 `\bsudo\b` 命中 `--sudo-mode`、
`\bsystemctl\b` 命中 `systemctl-status-checker`。这与模块自己宣称"已消灭
`| shuf` / `> /dev/null` 那类噪声"相悖，只是换了一批正则。

修法：命令名统一用 `(?<![\w-])…(?![\w-])`。左侧**刻意允许 `/`** ——
顺手把 `/` 也排掉是最自然的写法，却会让 `/usr/bin/sudo` 这个真实调用漏掉，
已用测试钉住这一点。仍然无法处理的两类（`grep sudo notes.txt`、
`echo "... kill -9 ..."`）需要真正的 shell 解析，模块 docstring 现在**如实写明
边界覆盖什么、不覆盖什么**，不再宣称消灭了噪声。

**5. docstring 纪律（对等性审核附带指出，与既有约定冲突）**

五个模块的 docstring 堆了大量 `Plan 0037 §3`、`rules.go:90`、
"这是参考实现第几行的第几个缺陷"这类编号与叙事，与仓库既有约定
（实现代码注释聚焦函数本身）直接相反。已全部重写：代码里只留**会改变调用方式**
的行为说明（匹配语义、fail-closed、未命中返回 `None`、哪些目录会被创建成 0700、
`raises` 什么）；设计取舍、与 harness9 的逐条对照、被推翻的方案，全部留在本文档
与**测试的 docstring** 里。

**6. 本文档测试计数陈旧（正确性审核）**

`test_gate.py` 实为 43 项而非 46、目录合计 262 项而非 234。已更正。

### 8.3 留给下一步的待办

- **Channel adapter 还没有「总是允许」按钮。** 能力现在只在 CLI 上可达。
  架构上不缺东西：`APPROVAL_REQUIRED` 事件本身就带完整的 `ApprovalRequest`，
  adapter 渲染审批卡时已经持有 `tool_name` 与 `arguments`，按 `request_id`
  本地缓存到回调抵达即可，然后调 `AgentApp.remember_approval`。这是 surface
  自己的状态管理，不需要改 `omicsclaw/tools/` 或 `omicsclaw/permission/`
  里的任何类型。

### 8.4 已确认但刻意不修的一条：规则文件路径上的符号链接

正确性审核在复验时构造了一个更刁钻的场景：攻击者预先在**中间层**放一个指向
树外目录的符号链接，`_make_owner_only` 的"已存在则跳过"对它返回
`exists() == True` 直接放过，随后 `mkdir` 被操作系统透明地跟随该链接，
文件最终落在攻击者指定的目录里（权限仍是 0700/0600，**移动的是位置而非模式**）。
已自行复现确认。

**不修，理由三条：**

1. **不是本次回归。** 审核把同一场景喂给旧的单次
   `mkdir(parents=True, mode=...)`，行为完全一致 —— 这是任何"顺序 mkdir
   穿越符号链接"实现本就有的特性。
2. **任何"路径含符号链接就拒绝"的修法会打断合法布局。** macOS 的 `/tmp`、
   软链的 home、软链的数据盘都很常见，而攻击者植入的符号链接与部署自己的
   软链在文件系统层面**不可区分**。真正 TOCTOU 安全的做法是逐级
   `openat` + `O_NOFOLLOW`，那恰好就是会拒掉合法软链的那个语义。
3. **在默认布局下它不额外给攻击者任何东西。** 默认路径是
   `<workspace>/.omicsclaw/settings.json`；能在中间层创建符号链接的攻击者
   本来就能直接写这个规则文件。它只在 `--permission-rules` 指向一条
   中间层可被他人写入、而末级不可的路径时才有意义 —— 一个人为构造的布局。

已写进 `save_rules` 的 docstring：这是会改变调用方式的事实
（"别把 `--permission-rules` 指向父目录不属于你的路径"），所以属于代码注释
该留的那一类。

### 8.5 未采纳的两条

- **Desktop surface 缺 `/chat/permission`**（对等性审核列为次要缺口）：这是
  entry 层早于本计划的既有债务，`docs/FRAMEWORK-REBUILD.md` 已记录，不在本层范围。
- **`ToolPolicy.prompts_for_itself` 的轻微反向信息耦合**（对等性审核 verdict：
  可接受但非零成本）：保留。被否决的替代方案是从 `approval_mode` 推断，而那正是
  §7.2 那个真实漏洞的成因。代价记在这里而不是抹掉。
