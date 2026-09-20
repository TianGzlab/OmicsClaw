# 0034 — MCP 层：`omicsclaw/mcp/`

> 状态：已交付（2026-09-19），经一轮独立只读审计与一轮修复。参照系：harness9
> `internal/mcp/`（config / transport / client / manager）+
> `internal/tools/mcp_adapter.go` + `cmd/harness9/main.go:291-323` 的接线。
> 编号说明：起草时用的是 0033，并行会话同日占用了 0033（memory 层），本计划改为 0034。

## 1. 目标与非目标

**目标**：让重构后的 Agent 主循环能调用任意遵循 Model Context Protocol 的外部
工具服务器。MCP 工具以 `mcp__{server}__{tool}` 注册进 `ToolRegistry`，对
`engine` 透明——调度、超时、审批暂停、错误回传全部沿用既有机制，**主循环一行
不改**（`engine/executor.py` 只改了一句过时的 docstring）。

**非目标**：

- 不做 TUI 的 MCPBar / `/mcp` 面板——Surface 的事；本层只提供 `ServerStatus`
  快照与 `on_change` 状态回调两个接缝。
- 不做 resources / prompts / sampling / roots / elicitation——harness9 同样只做 tools。
- 不做运行期热重载与 `tools/list_changed` 刷新（见 Q1）。
- 不接旧的 `~/.config/omicsclaw/mcp.yaml`（见 Q3）。
- 不引入 MCP SDK：本机未安装，且各层约定只用标准库。

## 2. harness9 能力清单与处置（审计后订正）

| # | harness9 能力 | 出处 | 处置 |
|---|---|---|---|
| 1 | `.mcp.json` 加载，文件缺失为空配置 | `config.go:46-62` | ✅ `config.py` |
| 2 | 配置文件损坏：记日志、跳过、照常启动 | `main.go:297-300` | ◐ **有意偏离**：抛 `MCPConfigError`，启动失败（Q3） |
| 3 | `type` 省略时按 command / url 推断 | `config.go:28-37` | ✅；两者都写时拒绝（Go 选 stdio） |
| 4 | stdio：NDJSON、ID 关联、pending 表、写锁 | `transport.go` | ✅ `stdio.py` |
| 5 | 读循环忽略非 JSON 行 | `transport.go:123-133` | ✅，并区分 server 发来的请求（Q5） |
| 6 | 传输关闭时挂起请求失败 | `transport.go:147-152` | ✅；进程退出路径先等最多 1.5 s 收集退出码与 stderr 再失败 |
| 7 | 请求三路退出：响应 / 取消 / 传输关闭 | `transport.go:181-194` | ✅，取消时另发 `notifications/cancelled` |
| 8 | 大行缓冲 1 MB | `transport.go:115` | ✅ 8 MiB，超限关闭传输并报原因 |
| 9 | 独立进程组，关闭时整组终止 | `transport_proc_unix.go` | ✅ 服务过的 server 先优雅关闭（Q7），握手未完成的立即整组 KILL |
| 10 | HTTP：每消息一次 POST | `transport.go:247-283` | ✅ `streamable_http.py`，补齐 Streamable HTTP 必需项（§5） |
| 11 | 握手三步 | `client.go:69-103` | ✅，另校验协议版本 |
| 12 | tools/list（只取一页） | `client.go:93-101` | ✅ 跟随 `nextCursor` 分页；无名条目跳过并计数 |
| 13 | tools/call：拼接 text 块，`isError` → 错误 | `client.go:107-140` | ✅，非文本块留占位说明，`structuredContent` 兜底 |
| 14 | Manager 并发连接、每 server 30 s、fail-soft | `manager.go:76-127` | ✅；握手未完成即 KILL，实测 1 s 超时 → 1.02 s 返回 |
| 15 | 状态 pending / connected / failed + 工具明细 | `manager.go:20-43` | ✅，另加 disabled / skipped / info |
| 16 | 状态回调在锁外调用 | `manager.go:217-226` | ✅；回调抛错被吞掉（本层不写日志，与其他层同约定） |
| 17 | 连接成败写日志 | `manager.go:97,122` | ✅ 移到 `entry/assembly.py` 的 `_log_mcp_outcome` |
| 18 | InjectTools：`mcp__{server}__{tool}`，冲突跳过 | `manager.go:162-191` | ✅ MCP 之间冲突：先到者留下，后到者记入 `skipped`；与 `tools=` 传入的工具冲突：`ToolAlreadyRegistered`，启动失败（有意，见 §5） |
| 19 | 名字消毒 | `mcp_adapter.go:67-77` | ◐ 有意偏离三处：只留 ASCII、折叠连续下划线、空结果带摘要；另有 64 字符上限（plan 0028 陷阱 10） |
| 20 | 描述加 `[MCP:server]`，schema 解析失败回退 | `mcp_adapter.go:46,81-90` | ✅，并记录 `schema_error` |
| 21 | Stop 关闭全部连接 | `manager.go:194-203`，`main.go:321` | ✅ `AgentApp.aclose()` 先排空会话、再关 MCP |
| 22 | 引擎透明：**同一 turn 内并发执行** | `engine/tools_exec.go:38-67` | ◐ **有意偏离**：MCP 工具的默认策略 `concurrency_safe=False`，被引擎写屏障串行（§5 第一行） |
| 23 | 引擎透明：超时、取消、错误回传 | `tools_exec.go:48-54`，`tools/registry.go:83-122` | ✅ |
| 24 | 审批（permHook 对无规则工具默认 Ask） | `permission/rules.go:66`，`main.go:413` | ✅ 对等；审批前先查参数形状，审批理由写明调用去向 |
| 25 | 启动接线：异步启动后注入 | `main.go:291-323` | ◐ **改为启动时阻塞（有上限）**，见 Q1；入口是 `open_app()` |

## 3. 包结构与依赖方向

```
omicsclaw/mcp/
├── __init__.py          公共接口
├── config.py            .mcp.json → MCPConfig（合法条目 + 被拒条目）
├── transport.py         Transport Protocol、JSON-RPC 帧与编码、错误类型
├── stdio.py             StdioTransport
├── streamable_http.py   HTTPTransport（Streamable HTTP）
├── client.py            MCPClient：握手、分页 tools/list、tools/call、结果渲染
└── manager.py           MCPManager：并发连接、状态、铸造 MCPTool、输出上限、关闭
```

- `omicsclaw.mcp` 只 import 标准库、`omicsclaw.tools`、`omicsclaw.version`；
  **只有 `manager.py` 碰 tools 层**（测试钉住），协议模块只讲 MCP。
- `engine` / `context` / `provider` / `skills` / `tools` 不 import `omicsclaw.mcp`。
- `entry/assembly.py` 是唯一使用方：`open_app()` 读配置、连接、把工具交给
  `build_app(mcp=...)`；`AgentApp.aclose()` 负责关闭。`build_app` 自身**不连接**
  任何 server。

## 4. 关键裁决

### Q1 —— 启动时阻塞连接，而不是会话中途扩表

`AgentApp.tools_snapshot` 与 `ContextBudget.reserve_tool_tokens` 都在 `build_app`
里算一次；工具定义又位于前缀缓存区内。晚到的工具会让预算少算工具 token，并作废
之后的全部缓存。所以 `open_app()` 在 `build_app()` 之前并发连接所有 server，
等待上限约等于单个 server 的连接超时（默认 30 s，`--mcp-connect-timeout`）。
失败的 server 不阻断启动。`notifications/tools/list_changed` 被忽略，工具表在
进程生命周期内固定。

### Q2 —— 审批必须真的发生

接入前 `MCPTool` 声明 `ASK` 却从不调用 `require_approval`。现在
`execute` 先检查参数是 JSON 对象（不对 schema 校验），再带上完整参数与调用去向
（`local process <command>` 或脱敏后的 `remote <url>`）请求审批，没有审批通道时
fail-closed。部署若信任某个 server，经 `registry.register(tool, policy)` 放宽；
`.mcp.json` 不提供放宽开关（它在工作区里，可被仓库内容控制）。审计指出这一条
与 harness9 **对等**而非偏离：harness9 的 permHook 对无规则工具同样默认 Ask。

### Q3 —— 配置文件：`<workspace>/.mcp.json`

取 Claude Code / Claude Desktop / harness9 共用的 `mcpServers` 形状。位置可由
`--mcp-config` / `OMICSCLAW_MCP_CONFIG` 修改；文件缺失 = 不启用 MCP。
`${VAR}` 与 `${VAR:-default}` 插值，变量未设置时拒绝该 server 并只点名变量。
`env` 接受对象或 `["K=V"]`。保留旧 `mcp.yaml` 的 `enabled: false` 与 `tools`
白名单。文件不可解析 → 启动失败；单个条目不合法 → 只拒绝该条目。旧 YAML 与
`oc mcp add/remove` 属于旧 Surface，迁移时再定。

### Q4 —— 子进程环境变量：白名单继承

只继承 `HOME LOGNAME PATH SHELL TERM USER`（Windows 另一组），再叠加配置里的
`env`——与官方 Python SDK 一致。进程里的 `LLM_API_KEY`、`TELEGRAM_BOT_TOKEN`
不会流到第三方 server。子进程工作目录是 workspace（harness9 继承当前目录）。

### Q5 —— 协议版本与 server→client 消息

请求 `2025-06-18`，接受 `2024-11-05` / `2025-03-26` / `2025-06-18`。stdio 读循环
区分响应、server 请求、通知：`ping` 回 `{}`，其余请求回 `-32601`；`"id": true`
不被当作请求 1。HTTP 事件流里的 server 请求只被跳过、不作答（已知限制）。

### Q6 —— 输出上限

MCP 工具是唯一不自限输出的工具，一次 exchange 内又不压缩；输出上限 32,000
字符，放在 manager 的桥接调用里（面向模型的策略不进协议层），截断时如实写明
看到多少、总共多少。

### Q7 —— 关闭流程

完成过握手的 stdio server：关 stdin → 等 2 s → 进程组 SIGTERM → 等 2 s →
SIGKILL，最后再整组 KILL 一次清理后代。握手未完成的立即整组 KILL。HTTP：
有 session 时发 `DELETE`。每个 HTTP 请求跑在自己的 daemon 线程上，被放弃的
请求不占共享线程池、不拖住进程退出。

### Q8 —— 事件循环归属

一个 manager / transport 属于启动它的事件循环。该循环停止时读循环把传输标记
为关闭，之后的调用立即报错（修复前会永久挂起）。`open_app` 必须在服务所用的
循环里 await。

## 5. 与 harness9 的差异

**有意偏离**

| 差异 | 理由 |
|---|---|
| MCP 工具在引擎里串行（写屏障），harness9 同 turn 并发 | `ToolPolicy` 对未声明的工具取保守默认，本地未声明工具同样串行；第三方工具是否会写工作区本进程无从知道。放开的方式：部署以 `concurrency_safe=True` 重新注册可信工具。**是否默认放开由 owner 决定**（例如信任 `readOnlyHint`——规范要求把它当作不可信提示） |
| 配置文件损坏时启动失败，harness9 跳过 | 与 `AppConfigError` 同一哲学：坏输入要响亮 |
| 与 `tools=` 同名时启动失败，harness9 跳过 | 与注册表「重名不静默」的设计一致；只有部署传入 `mcp__` 前缀的工具才会发生 |
| 启动时阻塞连接 | Q1 |
| 环境白名单、工作目录固定为 workspace | Q4 |
| 输出上限 32k | Q6 |
| 名字消毒三处偏离 | plan 0028 陷阱 10 |

**修正（harness9 的缺陷，本实现避开）**

| harness9 缺陷 | 证据（审计探针） |
|---|---|
| stdio server 连接完成后立即被 kill：`exec.CommandContext(connCtx)` + `defer cancel()` | `manager.go:92-93`，`transport.go:89`；首次调用报 `broken pipe` |
| server 请求与挂起请求同号时被当成响应 | `transport.go:123-143`；`parse tools/call result: unexpected end of JSON input` |
| tools/list 只取第一页 | `client.go:93-101` |
| 非文本内容块静默丢弃 | `client.go:128-134` |
| HTTP 不带 `Accept`（合规 server 回 406）、不回传 session id（有状态 server 回 400）、不带 `MCP-Protocol-Version`（server 会按 2025-03-26 处理）、不解析 SSE、不检查状态码、Notify 丢掉鉴权 header | `transport.go:247-309` |
| 不校验 server 选的协议版本 | `client.go:83` |
| stderr 丢弃：server 启动后崩溃时只剩 "transport closed" | `transport.go:107` |
| 继承全部环境变量 | `transport.go:94-96` |
| Connect 失败不关闭 transport | `client.go:70-101` |

**等价而非修正**（初稿误列为修正）：参数先解码再编码——Go 的 `json.Marshal` 对
`RawMessage` 同样校验并压缩，换行到不了线上。

## 6. 验收（结果）

1. `tests/mcp/`：配置、stdio 真实子进程、HTTP 回环（JSON 与 SSE）、客户端渲染、
   manager、分层。
2. 分层：只有 `manager.py` import tools 层；其他重建层不 import mcp；子进程行为
   探针跑通真实路径后检查 `sys.modules`。
3. `tests/tools/test_mcp_tool.py`：无通道拒绝、拒绝不触达 server、收紧方向生效、
   参数形状先于审批、审批理由带去向。
4. `tests/entry/test_open_app.py`：无配置等价 `build_app`；MCP 工具进入快照与
   预算；失败 server 记日志且应用照常启动；`aclose()` 终止子进程与后代；组装
   失败不泄漏子进程；**ReAct 主循环端到端调用 MCP 工具**。
5. 重建测试目录 schema / provider / engine / tools / context / skills / entry / mcp：
   2,676 通过、1 跳过（desktop 缺 fastapi，既有）。另有两处与本步无关的红：
   - `tests/tools/test_workspace.py` 收集失败，原因是 `omicsclaw/services/` 在工作区被删；
   - `test_no_other_entry_module_reads_the_environment`，原因是并行会话正在写的
     `omicsclaw/entry/cli/`。
6. 变异验证：实现轮 18 个 + 修复轮 12 个，全部被指名测试杀死。

## 7. 已知限制

- 旧 HTTP+SSE（2024-11-05 双端点）与 websocket 不支持，条目被拒并说明原因。
- HTTP 请求被取消后，其 daemon 线程最迟在 socket 超时（默认等于
  `tool_timeout_s`）后退出；HTTP 取消不发 `notifications/cancelled`。
- session 过期（HTTP 404）不自动重连，需重启。
- 工具表在进程生命周期内固定（Q1），修改 `.mcp.json` 需重启。
- server 的 `instructions` 被记录在 `ServerStatus.info`，未注入系统提示。

## 附录 A —— 独立审计与修复记录

一名未参与实现的只读 agent 对照 harness9 源码审计（并在副本上跑了 Go 探针），
结论：核心特性全部实现，无高危缺陷；中危 4、低危 10，另指出本计划初稿 8 处错误。

| 编号 | 发现 | 处置 |
|---|---|---|
| M1 | MCP 工具被串行，计划未声明 | 声明为有意偏离（§5），默认是否放开待 owner 裁定 |
| M2 | HTTP 请求取消后工作线程占住默认线程池并阻塞进程退出（600 s） | 改为每请求 daemon 线程；探针 20 s 超时被杀 → 1.00 s 退出 |
| M3 | 没有入口调用 `open_app`，文档示例全是 `build_app` | 文档示例改为 `attach_sessions(await open_app(...))`，`build_app` 写明不连接 MCP；并行会话的 CLI surface 已使用 `open_app` |
| M4 | 跨事件循环使用永久挂起 | 读循环被取消时标记关闭，之后立即报错（Q8） |
| L1 | 连接超时实际 5.04 s（1 s 配置） | 握手未完成立即 KILL；实测 1.02 s |
| L2 | 回调异常与 `list_changed` 未记日志 | 维持不记（本层无日志约定），订正计划措辞 |
| L3 | `tool_timeout_s<=0` 使 HTTP socket 非阻塞、全部失败 | `<=0`/`None` 映射为无限等待 |
| L4 | 连接超时可为 0 或负数 | `MCPManager` 拒绝非正值 |
| L5 | URL 中的密钥进入错误信息与日志 | 错误信息与审批理由一律用去掉 userinfo / query 的 URL |
| L6 | 未写出的请求被取消时仍发 `notifications/cancelled` | 只为已写出的请求发送 |
| L7 | `"id": true` 被当作请求 1 | id 须为真正的 int |
| L8 | 先审批后校验参数；审批理由没有去向 | 形状检查先于审批；理由带 `local process …` / `remote <url>` |
| L9 | 与 `tools=` 重名启动失败 | 维持，声明为有意偏离 |
| L10 | 一个无名工具让整个 server 连接失败 | 跳过并记入 `skipped` |
| 内聚 | 协议层 client 抛 tools 层异常；输出上限放在协议层；`_encode` 两份 | 参数形状检查移到 `MCPTool`；上限移到 manager；编码合并到 `transport.encode` |
| 文档 | `mcp_tool.py` 引用已删除的 `orchestration.py`、称「装配层不存在」；`executor.py`、`registry.py` 仍按异步注入描述 MCP | 已订正 |

修复由实现者本人完成（未按 FRAMEWORK-REBUILD「修复由第三个 agent 执行」的惯例），
每条修复都配了回归测试并经变异确认；如需，可再派一次只读复核。
