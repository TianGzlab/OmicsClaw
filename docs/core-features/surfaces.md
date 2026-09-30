# Surfaces —— CLI / Desktop / Channel 三个入口共用一个 AgentApp

> OmicsClaw 的交互层是**三个界面**（终端、桌面 HTTP 后端、IM 机器人）驱动**同一个**组装好的 agent。
> 事实来源：`omicsclaw/entry/`、`omicsclaw/launch/_surfaces.py`、`tests/entry/`。
> `docs/ARCHITECTURE.md` 有多处已过时（`ControlRuntime`、`control.db` 等），**以 `entry/` 代码为准**；iMessage 与 WeChat 适配器已从代码中移除，`CHANNEL_REGISTRY` 只有七个平台（§9.1）；
> 旧的 `omicsclaw/surfaces/` 与 `omicsclaw/remote/` 已删除（plan 0064 P3），只能在 git 历史里查阅。

---

## 1. 概述

```
            oc cli                      oc desktop                         oc channel --channels ...
              │                            │                                      │
   omicsclaw/launch/_surfaces.py: start_cli / start_desktop / start_channel  （读 argv/env、退出码、信号）
              │                            │                                      │
              └───────────────┬────────────┴───────────────────┬──────────────────┘
                              ▼                                ▼
          app = attach_sessions(await open_app(resolve_app_config(argv, env)))
                              │
      ┌───────────────────────┴───────────────────────────────────────────────┐
      │ AgentApp  (entry/assembly.py — 组合根)                                 │
      │  provider · registry(ToolRegistry) · engine(AgentEngine) · prompt       │
      │  budget · summarizer · skills · plans · mcp · sandbox · memory          │
      │  telemetry · permission · config                                        │
      │  sessions: SessionRegistry (entry/session.py)                           │
      │     └─ 每会话一条 lane；每次 exchange 一个 TurnHandle + 一个 Task        │
      │          ├─ TurnRunner (entry/turn.py) → engine.exchange / run_stream   │
      │          ├─ TurnStream (entry/stream.py)  事件环形缓冲，可多次 observe   │
      │          └─ ApprovalBroker (entry/approval.py)  "问人" = 帧 + Future     │
      └───────────────────────────────────────────────────────────────────────┘
                              │  TurnEvent (entry/events.py, 14 种)
          ┌───────────────────┼──────────────────────────────┐
          ▼                   ▼                              ▼
   CLI: Repl._pump      Desktop: to_wire → SSE 帧      Channel: ChannelRuntime
   TextRenderer(        DESKTOP_CHAT_FRAME_TYPE         TextRenderer(batched=True)
    batched=False)      POST /chat/stream               结束后一次性投递答案
```

一个界面只允许依赖三样东西（plan 0031 §7）：`TurnEvent`、渲染器（`TextRenderer` / `to_wire`）、ingress 类型
（`InboundMessage` / `SenderPolicy` / `Acceptance` / `DeliveryResult`）——外加部署本身（`AgentApp` / `SessionRegistry`）。
`tests/entry/test_entry_is_the_top_layer.py` 在子进程里断言：下层包不导入 `omicsclaw.entry`；驱动 entry 不会加载
`omicsclaw.runtime`、`omicsclaw.control`、`omicsclaw.providers`、`omicsclaw.skill`、`omicsclaw.surfaces`，也不会加载 `fastapi`、`textual` 或厂商 SDK。

---

## 2. 组合根：`entry/assembly.py`

| 组件 | 代码位置 | 职责 |
|---|---|---|
| `resolve_app_config(argv, env)` | `entry/config.py` | 唯一的部署解析点，返回冻结的 `AppConfig`；坏值抛 `AppConfigError` |
| `build_app(config, ...)` | `entry/assembly.py` | 唯一知道装配顺序的函数；不连接 MCP |
| `open_app(config, ...)` | `entry/assembly.py` | 先启动沙箱，再并发连接 `.mcp.json` 的服务器，然后 `build_app`——**界面应调用它** |
| `attach_sessions(app, store=None)` | `entry/session.py` | 给 app 挂上 `SessionRegistry`；`store=None` 表示"用 app 自己的"：开了 memory 就是 `SqliteSessionStore(memory.db)`，否则 `InMemorySessionStore` |
| `AgentApp.aclose()` | `entry/assembly.py` | 停止接收 → 给运行中的 exchange `SHUTDOWN_GRACE_S = 5.0` 秒 → 取消并回收 → 关 MCP、沙箱、memory、telemetry |

`build_app` 装配的内容：

- **工具**（`foundation_tools`，顺序固定以保持缓存前缀字节稳定）：`read_file`、`write_file`、`edit_file`、`bash`、`web_fetch`、`web_search`
  （共享同一个 `Workspace`），`use_skill`（`skills_index != off`），`plan_write`（planning 开），`memory_search`、`memory_write`（memory 开）；
  之后是 MCP 工具，最后是子代理的 `task` 工具（subagents 开）。每个工具外面依次包 hook 链（`build_hooks`，默认空；`--audit-log` 挂 `AuditHook`）
  与权限门（`GatedTool`，`build_permission_gate`）。
- **Prompt**（`default_sections`，到达顺序即渲染顺序）：契约（`OMICSCLAW.md`，从 skill 树旁读）→ safety（常量 `SAFETY_RULES`，不可关闭）
  → tool guidance（`TOOL_GUIDANCE`）→ [planning] → [execution sandbox] → [skills] → environment → [long-term memory]。
  `AgentApp.prompt` 是**组装器**而不是一次渲染结果，每轮重新 render，所以改了 `OMICSCLAW.md` 或到了第二天都会生效。
- **预算与摘要器**：`build_budget(model, tools)` 用模型表与工具定义算两个保留量；`build_summarizer` 用 `summary_model`（空则主模型）。
- **引擎**：`AgentEngine`，拿到的是**未包装**的 `ToolRegistry`（引擎用 `isinstance` 判断 `DeadlineAwareExecutor` / `ConcurrencyAwareExecutor`，
  包装会让人思考审批的时间重新计入工具超时）。

`AgentApp` 上供界面使用的方法：`set_permission_mode`（只在 `default` ⇄ `auto-approve` 间切换，每次 WARNING 日志）、
`remember_approval`（为精确调用写 `allow` 规则）、`can_remember_approval`（受保护文件返回 `False`）。

---

## 3. 会话与 exchange

### 3.1 `SessionRegistry`（`entry/session.py`）

三条保证（plan 0031 Q6）：

1. **每个 exchange 一个 Task**：`contextvars` 按 Task 隔离，否则一个用户的工具调用会弹到另一个用户的审批里。
2. **会话内串行、会话间并发**：同一会话的第二条消息排队；不同会话互不等待。
3. **排队是语义而不是锁**：`submit` **立即**返回 `TurnHandle`，发布前面排了几个（`QUEUED` 事件），超过
   `max_queued_per_session`（默认 2）直接抛 `QueueFull`；排队中的 exchange 可以在开始前取消。

| 方法 | 用途 |
|---|---|
| `submit(session_id, text, *, values=None, source_request_id="")` | 提交一条消息；同一会话内重复的 `source_request_id` 返回**同一个** handle（幂等，键按会话作用域） |
| `deliver(message: InboundMessage)` | `submit` 的 ingress 版，Desktop 与 Channel 用 |
| `compact(session_id)` | 在该会话 lane 中排一个仅压缩的 exchange（CLI `/compact`、Channel `/compact`） |
| `observe(turn_id, *, after_seq=0)` / `handle(turn_id)` | 按 id 重新观察 / 取 handle |
| `list_sessions(limit=10)` / `load_session` / `persistent` | CLI `/sessions`、`/resume` |
| `running()` / `shutdown(grace_s)` | 运行中的 handle / 关闭 |

**持久化在注册表里做，不在 exchange 的 Task 里做**：取消一个 Task 会在它下一个 `await` 注入 `CancelledError`，
`finally: await store.save(...)` 做不完；所以注册表先回收 Task 再保存（trap 3b）。内存中最多 `max_sessions`（默认 256）个会话，
淘汰最近最少使用的**空闲**会话，运行中的永不淘汰。

**放弃计时**：最后一个观察者离开后 exchange 继续跑 `DEFAULT_ABANDON_GRACE_S = 30.0` 秒，然后被取消——
足以覆盖浏览器刷新重连 SSE、IM 投递重试这类"几秒钟"的空窗。

### 3.2 一次 exchange：`entry/turn.py`

`turn.py` 是函数式内核：`compose` → `prepare`（measure + compact）→ `run_turn` / `stream_turn`，返回 `TurnOutcome`；
`TurnRunner` / `TurnHandle` 在它之上加了会话、取消、事件流与审批。每轮交给引擎三样东西：app 的 prompt 组装器、
承载本次历史的 `_Carried`、一个在**每次模型调用前**测量并按 `compact_at` 压缩的 `ProgressiveCompactor`（外加把计划重新注入尾部的
`PlanInjector`）。`TurnOutcome.history` 去掉了 system 消息，避免下一轮叠出两个 persona。

`TurnHandle` 对界面公开：`observe(after_seq=0)`、`approve(request_id, decision)`、`cancel()`、`wait()`、`done()`、`terminal`、`outcome`，
以及 `approvals`（`ApprovalBroker`）。

---

## 4. 事件流：`entry/events.py` 与 `entry/stream.py`

### 4.1 `TurnEventType`（14 种）

| 类型 | 来源 | 可丢弃 | 说明 |
|---|---|---|---|
| `EXCHANGE_START` | entry | 否 | 一次用户往返开始，每 exchange 恰一次 |
| `QUEUED` | entry | 否 | 排在前面的 exchange 数 |
| `CONTEXT` | 压缩器 | 否 | 本次模型调用前的预算报告 |
| `COMPACTION` | 压缩器 | 否 | 一次压缩的记录 |
| `TEXT_DELTA` | 引擎 | **是** | 回答增量 |
| `REASONING_DELTA` | 引擎 | **是** | 推理增量 |
| `PROGRESS` | 工具 | **是** | 工具进度（如 `bash` 输出） |
| `TOOL_START` / `TOOL_RESULT` | 引擎 | 否 | 工具调用开始 / 结果 |
| `APPROVAL_REQUIRED` / `APPROVAL_SETTLED` | entry | 否 | 需要人审批 / 已决定 |
| `TURN_END` | 引擎 | 否 | **每次模型调用**一次（一个 exchange 有 N 个） |
| `GAP` | stream | 否 | 观察者落后，丢了一段可丢弃帧；`seq` 即恢复游标 |
| `EXCHANGE_END` | entry | 否 | 恰一次，`terminal` ∈ `converged` / `cancelled` / `failed` |

透传事件在 `TurnEvent.engine` 上携带**原始** `EngineEvent`，不重新打包。

### 4.2 `TurnStream` 与 `TurnObservation`

身份与观察分离（plan 0031 Q14）：每个 exchange 一个 `TurnStream`，任意多个 `TurnObservation`，各有游标——
Desktop 的 SSE 重连是一个新 HTTP 请求，Channel 的投递重试需要从游标重放。

- 环形缓冲 `delta_ring_size`（默认 2048，`DEFAULT_RING_SIZE` 与之一致）；控制帧永不丢弃。
- 慢观察者**不被踢掉**，而是丢弃可丢弃类型并收到 `GAP`——桌面用户在慢链路上应该丢 token，而不是丢审批提示。
- 游标超过末尾视为"已追上"，不报错。
- `publish` 只在同一事件循环的 Task 之间安全；SDK 线程上的回调必须走 `publish_threadsafe`（`call_soon_threadsafe`）。
- 观察要用 `async with handle.observe() as obs:`——`break` 出 `async for` 不会减少观察者计数，放弃计时就不会开始（trap 9）。

### 4.3 渲染：`entry/render.py`

| 投影 | 性质 | 用于 |
|---|---|---|
| `TextRenderer(batched=False)` | 有状态；token 到即出 | CLI |
| `TextRenderer(batched=True, batch_chars=...)` | 有状态；跨事件累积成块 | Channel（IM 平台限流编辑/发送） |
| `to_wire(event)` | 纯函数，JSON 可序列化 | Desktop SSE |

三条隐私/正确性规则：工具耗时字段一律叫 `elapsed_s` 并带 `elapsed_includes_approval_wait`（文本加 `ELAPSED_INCLUDES_APPROVAL_WAIT` 后缀）；
`usage=None`（未报告）与零 usage（免费或未报告）渲染成不同字符串；`TextRenderer` 从不把工具参数或输出原样放进屏幕或聊天
（审批行除外——它引用要批准的命令/diff/URL，参数预览里凭据类键被隐藏，见 `omicsclaw/tools/preview.py`）。
`to_wire` 必须携带参数与结果（`ToolCall.arguments` 逐字节透传），因此它的输出**不可记日志**。

`DESKTOP_CHAT_FRAME_TYPE` 把 5 种类型映射到桌面客户端已发布的帧名：`TEXT_DELTA→text`、`TOOL_START→tool_use`、
`TOOL_RESULT→tool_result`、`PROGRESS→tool_output`、`APPROVAL_REQUIRED→permission_request`；`EXCHANGE_END` 按 terminal 分支为 `done` / `error`。
其余类型没有已发布的名字，不发帧——给外部客户端单方面发明词汇超出了后端重建的范围（Q24）。

---

## 5. 审批：`entry/approval.py`

工具调用 `require_approval` 时，等待发生在工具内部、引擎生成器的 `__anext__` 里，同一个生成器不可能既报告问题又等答案。
解法：引擎跑在自己的 Task 里，`ApprovalBroker` 把请求变成流上的 `APPROVAL_REQUIRED` 帧 + 一个 `asyncio.Future`，
由**另一个** Task 调 `settle()` 解决。期限 `approval_timeout_s`：`None` 等到 exchange 结束；有数值则**到期拒绝**（失败关闭）。
Broker 只记录工具名、请求 id 与结果，从不记参数。

| 界面 | 谁回答 | 期限 |
|---|---|---|
| CLI | `Repl._ask` 在独立 Task 读卡片回答（见 cli.md §7） | 默认无 |
| Desktop | App 的卡片 → `POST /chat/permission`（`once` / `session` / `always` / 拒绝），见 §8.2 | 无（`approval_timeout_s=None`）；用 `POST /chat/abort` 停止 |
| Channel | `ChannelRuntime.settle_approval*` 已实现但**生产代码中零调用**（文本/按钮回复是 plan 0052，未落地） | **必须**设置，否则 runtime 拒绝组装；实际效果是每个 ASK 到期被拒 |

---

## 6. Ingress：`entry/ingress.py`

| 类型 | 字段 / 成员 | 要点 |
|---|---|---|
| `InboundMessage` | `text`、`session_id`、`source_request_id`、`sender`、`surface`、`values: Mapping[str, object]` | 冻结的 6 字段契约；群聊信息放在 `values["chat_type"]`、`values["mentions"]` |
| `SenderPolicy` | `allowed_senders: frozenset[str]`（**无默认值**）、`bot_identity: str = ""` | 空 allowlist 在**构造时**就 `ValueError`；`admits()` 两道闸：发送者在名单内；若 `chat_type ∈ {"group","supergroup","channel"}`，必须设置 `bot_identity` 且被 @ 的身份里包含它 |
| `Acceptance` | `ACCEPTED` / `REJECTED` / `UNKNOWN` | `UNKNOWN`（超时、断连、5xx）不是软拒绝：重发可能重复 |
| `DeliveryResult` | `acceptance`、`retry_after: float \| None` | `None` 表示平台没说，不等于 0 |

策略判定返回 `bool` 而不是抛异常：被拒的消息**不创建任何 exchange**（也不回复"拒绝"）。

---

## 7. CLI 界面

详见 [cli.md](cli.md)。与另两个界面的关系：它是唯一既是库又被外壳当作前台进程运行的界面；用 `TextRenderer(batched=False)`；
审批在本地终端回答；`attach_sessions` 使用默认放弃计时（REPL 始终在观察）。

---

## 8. Desktop 界面：`entry/desktop/`

客户端是另一个项目 OmicsClaw-App（Electron + Next.js），它的 Next 服务端把请求转发到本后端。
**线协议由后端定义并版本化**（`wire_contract.py`，plan 0064）：App 只实现 `/health` 公布的那个版本，版本不符时两边都显式拒绝。
字段变更要同时做三件事：版本号加 1、两个仓库同批改、在计划里记录。

### 8.1 启动

```bash
oc desktop --workspace <项目目录>                 # 缺省 --host 127.0.0.1 --port 8765（DESKTOP_HOST / DESKTOP_PORT）
oc desktop --workspace <dir> -- --port 18765      # 界面 flag 写在 -- 之后或之前均可
OMICSCLAW_REMOTE_AUTH_TOKEN=... oc desktop --workspace <dir> -- --host 0.0.0.0
# App 经 SSH 隧道连接的服务器（<dir> 不是检出目录时要带 OMICSCLAW_SKILLS_DIR）
OMICSCLAW_SKILLS_DIR=<检出目录>/skills \
oc desktop --workspace <dir> --delta-ring-size 65536 -- --host 127.0.0.1 --port 8765 --abandon-grace 600
```

fastapi 与 uvicorn 由 conda 环境（`environment.yml`）提供，不是 pip extra；缺失时报 `MissingSurfaceDependency`，提示用 conda/mamba 安装。
一个进程只服务一个工作区；App 切换项目等于重启后端。

界面 flag 还有 `--abandon-grace <秒>`：服务器发现一个 exchange 没有观察者之后，还让它继续跑多少秒，取 1 到 86,400 之间的有限数，否则拒绝启动（退出码 2）。
不给时 `_serve_desktop` 不向 `attach_sessions` 传这个值，沿用 `session.py` 的 30 秒；`/health` 的 `abandon_grace_s` 公布生效的值（`SessionRegistry.abandon_grace_s`）。
App 经 SSH 连接的服务器推荐 `--abandon-grace 600`，并用部署 flag `--delta-ring-size 65536`（写在 `--` 之前，缺省 2048）放大每个 exchange 的续流环，
否则长回复在断线几秒内就可能把续流点挤出环。服务器的 sshd 建议设 `ClientAliveInterval 30` 与 `ClientAliveCountMax 3`：
半开连接时 sshd 约 90 秒后关闭转发，观察者随之离开，宽限期才开始计时；不设时要等 TCP 自己超时，可能几十分钟以上。
远程模式的完整说明见 [`docs/engineering/remote-execution.mdx`](../engineering/remote-execution.mdx)。

部署设了 `skill_env=install` 时 `oc desktop` 照常启动，`install_skill_deps` 的审批和其他工具一样处理（与 CLI 一致）：
它的调用（没有 `ask` 规则命中时）不标 `ask_every_time`，所以 `full_access`、会话授权（`session`）与"总是允许"写下的规则都会不发卡片直接放行安装。

`start_desktop` 的顺序：认领/解析界面 flag → 解析部署半边 → **非回环地址且没有 `OMICSCLAW_REMOTE_AUTH_TOKEN` 时拒绝启动**
（`LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", ""}`）→ 检查 fastapi/uvicorn →
`attach_sessions(await open_app(config))` → uvicorn 服务。服务前构造 `DotenvSettings`（`.env` 的写入目标 `dotenv_target()`、
全部候选文件 `dotenv_candidates()`、启动前已导出的变量、`_adopt_dotenv` 之后的环境快照），经 `create_desktop_app(settings=...)`
交给 Providers 路由；快照由 `launch/__init__.py` 的 `main` 在它唯一一次读取进程环境时取得，包在 `LaunchEnvironment` 里随 `env` 传下。
token 只从环境读，不设 flag（命令行上的密钥会出现在进程列表里）。`OMICSCLAW_DESKTOP_LAUNCH_ID` 让 Electron 父进程识别自己启动的后端。

### 8.2 路由（`SERVED_PATHS`）

| 路由 | 用途 |
|---|---|
| `POST /chat/stream` | 提交一条消息，SSE 流式返回帧 |
| `POST /chat/permission` | 回答一张 `permission_request` 卡片 |
| `POST /chat/abort` | 取消某个 `/chat/stream` 请求所启动的 exchange |
| `POST /chat/session-permission-profile` | 把一个会话切到 `default` 或 `full_access` |
| `GET /workspace`、`PUT /workspace` | 查询工作区；PUT 只接受与当前相同的目录 |
| `GET /env/doctor` | 后端装配事实的检查清单（需要 bearer） |
| `GET`/`HEAD /health` | 进程事实与契约 |
| `GET /skills`、`GET /skills/{domain}/{name}` | 技能目录与单个技能（管理路由） |
| `GET /mcp/servers` | `.mcp.json` 的服务器与连接状态，只读（管理路由） |
| `GET /providers`、`PUT /providers`、`POST /providers/test` | 以 `.env` 为准的模型配置：列表、保存、实时测试（管理路由） |
| `POST /chat/title` | 为会话的第一条消息生成标题（管理路由） |
| `GET /files/tree` | 工作区的文件树，只读 |
| `GET /files/serve` | 工作区里的一个文件，只读，支持单段 `Range` |

管理路由与两条文件路由不纳入 `desktop_chat` 的版本号，随包版本发布；与其他路由一样需要 bearer（配置了 token 时）。

**所有写路由只收 JSON**：`Content-Type` 的媒体类型（`;` 之前、去空白、小写）必须恰好是 `application/json`，
否则（包括缺少这个头）返回 `415 unsupported_media_type`。网页可以不经 CORS 预检向回环端口发 `text/plain` 简单请求，
但发不了 JSON，而本后端不开 CORS。拒绝一律是 `{"detail": <code>}`。

**`POST /chat/stream`**（`create_desktop_app` → `open_chat_stream`）：

1. Bearer 校验（`secrets.compare_digest`；token 为空时不校验）；只收 JSON；
2. 请求体上限 `DEFAULT_MAX_REQUEST_BYTES = 2 MiB`（先查 `Content-Length`，再对实际字节累计），JSON 嵌套上限 `DEFAULT_MAX_JSON_NESTING = 64`；
3. `decode_chat_stream_request` → `ChatStreamRequest`。**`ingress_schema_version` 必须是 3**，缺失或其他值 → `422 unsupported_ingress_schema_version`；
   `after_seq` 是续流游标，非负整数，缺省 0（从环里仍保留的最早事件开始），其他值 → `422 invalid_after_seq`；
   `resume` 是布尔，缺省 `false`，不是布尔 → `422 invalid_resume`，为真时不要求 `content`；
   请求声明的 `workspace` 与后端不一致 → `409 workspace_does_not_match_backend_runtime`，无法解析成路径（含 NUL、`~user` 无此用户等）→ `422 invalid_workspace`；
   `permission_profile` 只能是 `default` 或 `full_access`（其他值 → `422 invalid_permission_profile`），在 exchange 开始前写入会话，缺省则保持原值；
   `model`、`effort`、`thinking` 等字段接受但忽略；
4. `to_inbound()` 把幂等键做命名空间限定，重发同一 `source_request_id` 会接到**同一个** exchange（只在本进程内有效）；
   **`resume: true`** 只接回已有的 exchange：按 `(session_id, source_request_id)` 在 `DesktopInteractions` 里找 `turn_id`，再 `registry.handle(turn_id)`，
   找不到或已被淘汰 → `409 exchange_not_retained`。它从不新开 exchange，也不排队压缩，不读 `content` 与 `permission_profile`，`workspace` 照常检查。
   所以后端重启、exchange 被淘汰、同一个 id 先后用于 `/compact` 与普通消息时，续流都不会把消息再执行一遍。接回压缩 exchange 时，
   游标之前已经送达过的 `status` 不再补报；接回已结束的 exchange 会补发游标之后剩余的帧与 `done`；
5. `registry.deliver` → `handle.observe(after_seq=...)` → `DesktopChatSSEBody` 流式输出（一个 exchange 最多 16 个观察者，满了 → `429 too_many_observers`，客户端可以重试）；响应头带 `X-OmicsClaw-Turn-Id`、`X-OmicsClaw-Session-Id`
   以及 `Cache-Control: no-cache`、`X-Accel-Buffering: no`。
   内容去掉首尾空白后恰好是 `/compact` 时改走 `registry.compact(session_id)`，模型收不到这段文字；流里一定有一帧 `status`（`kind: "compaction"`），
   没压缩任何东西时 `written_back: false`，然后是 `result`、`done`。

错误码：`401 unauthorized`、`409`（附件、工作区不符、`exchange_not_retained`）、`413 request_document_too_large`、`415 unsupported_media_type`、`422`（格式、版本、`invalid_resume`、`invalid_after_seq`）、
`429 queue_full` 与 `429 too_many_observers`、`503 shutting_down`、`403 sender_not_allowed`（仅当传入了 `SenderPolicy`；`oc desktop` 不传）。

**SSE 帧（`sse_schema_version = 3`）**：每帧一行 `data: {"type": T, "data": D}`，只有这两个键；D 是字符串（对象先序列化）。
事件产生的帧前面另有一行 `id: <事件序号>`；单帧连同 `id:` 行不超过 `CHAT_SSE_MAX_FRAME_BYTES = 4 MiB`。
`id:` 是续流游标：收到 `id: N` 表示序号不超过 N 的事件对应的帧都已送达，请求带 `after_seq: N` 就从它们之后接着发。
不带 `id:` 的帧有三类：结束流的一组（`/compact` 补报的 `status`、`result`、`error`、`done`），观察提前结束时合成的 `error` 与 `done`，以及 `keep_alive`。
客户端先缓着不带 `id:` 的帧（`keep_alive` 除外），等 `done` 到了再一起提交，断线时丢掉，续流会重发它们。
`event_omitted` 的 `id:` 是仍可取的第一个事件的前一个序号（它本身就是有效游标），超大帧投影成的 `event_omitted` 带原事件的序号。

| 帧 | D |
|---|---|
| `text` / `thinking` | 回答增量 / 推理增量（纯文本） |
| `tool_use` | `tool_use_id`、`tool_name`、`arguments`（原始 JSON 串）、`turn`，加身份键 |
| `tool_result` | `tool_use_id`、`tool_name`、`content`、`is_error`、`elapsed_s`（含审批等待）、`elapsed_includes_approval_wait`、`turn`，加身份键 |
| `tool_output` | 工具进度文本 |
| `status` | 压缩：`kind: "compaction"` 与前后计数、`degraded`、`written_back`，加身份键 |
| `permission_request` | `request_id`（`<turn_id>#<n>`）、`tool_name`、`arguments`、`reason`、`reason_shows_call`、`risk_level`、`approval_mode`、`ask_every_time`、`can_remember`（"总是允许"能否生效），加身份键；只在请求仍待决时发出 |
| `event_omitted` | 游标落后（`reason: cursor_evicted`）或单帧过大（`frame_too_large`） |
| `result` | converged 时在 `done` 前发一次：`usage`（整个 exchange 里各次模型调用的 `input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_write_tokens` 求和，包括同一 exchange 上先前的观察读到的，按 `TURN_END` 的序号去重；都未上报时为 `null`）、`usage_reported`（每次调用都报了用量，且没有调用可能被漏读）、`model_calls`、`provider`、`model` |
| `keep_alive` | 空闲 `KEEPALIVE_INTERVAL_S = 25` 秒 |
| `error` → `done` | 取消（`"cancelled"`）或失败（只给异常类型名）；converged 时只有 `done` |

身份键是 `sequence`、`turn_id`、`session_id`。实测：卡片可能先于对应的 `tool_use` 到达（审批发生在工具开始之前）。

**`POST /chat/permission`**：请求 `{request_id, decision: {behavior: "allow"|"deny", scope?: "once"|"session"|"always", message?}}`，`scope` 缺省为 `once`。
一律 HTTP 200：成功 `{ok: true, request_id, behavior, scope, session_id, remembered_pattern}`（`scope` 是实际应用的范围，拒绝总是 `once`；
`remembered_pattern` 只在 `scope` 为 `always` 时非空）；
失败 `{ok: false, request_id, status: "expired"|"resolved"}`（exchange 已结束或已不在内存 / 已被回答过）。格式错误 → 422
（`invalid_request_id`、`invalid_decision`、未知 scope → `unsupported_scope`）。
`always` 调用 `AgentApp.remember_approval` 写一条只匹配这次调用的 `allow` 规则，下次相同调用由权限闸门直接放行；
卡片的 `can_remember` 为假（改受保护文件）、部署没有规则文件、或写入失败时降级为 `once`，`remembered_pattern: null`。
拒绝没有 `message` 时，模型收到的理由是 `denied in the desktop app`。`session` 把该工具授权给这个会话（进程内有效，不落盘），
并连带放行同会话、同工具下其他待决请求；此后该会话的同类请求由正在观察流的 SSE 体直接放行、不再发卡片。
`ask_every_time` 为真的请求（危险命令、`ask` 规则、受保护文件、`DENY_UNLESS_TRUSTED`）永远不被会话授权放行；
在这类卡片上回答 `session` 只放行这一次、不授权会话（与 CLI 在这类卡片上按 `s` 相同），响应里的 `scope` 是 `once`。
审批没有期限（`approval_timeout_s` 保持 `None`），所以停止是退出一个无人回答的问题的方式。

**`POST /chat/abort`**：请求 `{session_id, source_request_id}`（即打开流时用的那一对）。成功 200
`{ok: true, session_id, source_request_id, turn_id, state: "cancelling"|"terminal"}`，幂等；找不到 → `404 turn_not_found`；格式错误 → 422。
被取消的流以 `error: "cancelled"` 然后 `done` 结束；排在同会话另一个 exchange 之后的请求，轮到它时直接以同样的帧结束，不调用模型。

**`POST /chat/session-permission-profile`**：请求 `{session_id, permission_profile: "default"|"full_access"}`，
成功 200 `{ok: true, session_id, permission_profile, active, auto_approved_requests}`（`active`：该会话此刻有 exchange 在运行；
`auto_approved_requests`：切换时当场放行的待决请求数）；格式错误 → `422 invalid_session_id` / `invalid_permission_profile`。
`full_access` 与 auto-approve 同一条线：`ask_every_time` 的请求（危险命令、`ask` 规则、受保护文件）照样发卡片。
它按会话保存在 `DesktopInteractions` 里，不动权限闸门的进程级 mode；聊天请求体里的 `permission_profile` 同样写入这里（后端重启后由下一条消息恢复）。

**`GET /env/doctor`**（`doctor.py` 的 `doctor_report`，与其他路由一样受 bearer 保护）：
`{generated_at, workspace_dir, omicsclaw_dir, overall_status, failure_count, warning_count, checks: [{name, status, summary, details}]}`，
`status ∈ ok|warn|fail|info`。检查项依次为 `provider`（provider 与有效模型）、`skills`（0 个时 warn 并提示 `OMICSCLAW_SKILLS_DIR`）、
`skipped_skills`、`mcp`（有失败的服务器时 warn）、`sandbox`（降级时 warn，未启用为 info）、`memory`（关闭为 info）、
`permission`（`bypass-all` 时 warn）、`workspace`（不存在或不可写时 fail）。App 把 warn/fail 计入 `needs-attention`，info 只作附注。

**有效模型**：`/health` 的 `model`、`result` 帧的 `model` 与 doctor 报告的都是 `resolve_config(config.provider, config.model).model`，
即 provider 实际调用的模型（部署只写了 provider 时是预设的缺省模型），不是 `config.model` 的原值。

**`GET /workspace`** → `{workspace, trusted_dirs: []}`。**`PUT /workspace`** `{workspace}`：同一目录的不同写法（`~`、`..`、结尾斜杠、符号链接）→ 200，
其他目录 → `409 workspace_change_requires_restart`，缺失或为空 → `422 workspace_required`，无法解析成路径 → `422 invalid_workspace`。

**`GET /files/tree?path=&depth=`**（`files.py`）：`path` 缺省为工作区，可以是绝对路径或相对工作区的路径；`depth` 取 1 到 10，缺省 3，否则 `422 invalid_depth`。
返回 `{root, tree, truncated}`，节点是 `{name, path, type: "file"|"directory", size?, extension?, children?}`：`path` 是请求目录按字面拼上条目名（不展开符号链接），
`extension` 不带点，没有扩展名时省略；目录在前，名字按不区分大小写的顺序；到达深度上限或读不了的目录 `children: []`。
隐藏条目、真实路径在工作区外或隐藏的条目、断链、指回自己祖先的目录链接，以及 `node_modules`、`.git`、`dist`、`.next`、`__pycache__`、`.cache`、`.turbo`、`coverage`、`.output`、`build` 都不列出。
遍历按广度优先，最多 `FILES_TREE_MAX_NODES = 10,000` 个节点，超出时停下并回 `truncated: true`。
**`GET /files/serve?path=`**：`path` 必填，缺失 → `422 path_required`。文件不超过 `FILES_SERVE_MAX_BYTES = 64 MiB` 时 200 返回全文，更大的文件不带 `Range` → `413 file_too_large`。
只认单段 `Range`（`bytes=a-b`、`bytes=a-`、`bytes=-n`），回 206 与 `Content-Range`，终点截到起点加 64 MiB 减 1，所以大文件上的开放区间也是 206；
起点不小于文件大小或 `bytes=-0` → `416 range_not_satisfiable`，带 `Content-Range: bytes */<size>`；多段、格式错的 `Range` 和空文件上的任何 `Range` 都被忽略。
类型按文件名猜：HTML、JavaScript 和 SVG 以外的 XML 类型以 `text/plain; charset=utf-8` 返回，带编码的猜测（如 `.svgz`）和猜不出的一律 `application/octet-stream`。
响应头有 `Accept-Ranges: bytes`、`X-Content-Type-Options: nosniff`、`Cache-Control: private, max-age=60` 与 `Content-Disposition: inline`（带 UTF-8 文件名）。
文件在线程里以 `O_RDONLY | O_NONBLOCK | O_NOFOLLOW` 打开，打开后再确认是普通文件，否则 `422 not_a_file`。
两条路由对 `path` 的限定相同：`~` 不展开，`..` 先按字面折叠；词法上或跟随符号链接之后落在工作区之外 → `403 path_outside_workspace`；
工作区之下任何以 `.` 开头的路径段（词法上或真实路径上；工作区本身所在路径里的点目录不算）→ `403 hidden_path`；不存在 → `404 file_not_found` 或 `directory_not_found`；
途中有不能进入的目录或读不了的文件 → `403 permission_denied`；含 NUL 或无法解析 → `422 invalid_path`；类型不对 → `422 not_a_file` 或 `not_a_directory`。拒绝的响应同样带 `nosniff`。

**`GET /skills`**（`catalog.py`）：`{domains: [{domain, domain_name, primary_data_types: [], skills: [{name, description, domain,
collection: "curated", status: "ready"}]}], total}`，按索引顺序分组；直接位于技能根目录下的技能归入 `general`。
**`GET /skills/{domain}/{name}`**：`{name, domain, description, aliases: [], script_path: null, tags, skill_md, resources: [{path, kind}]}`；
`skill_md` 是去掉 frontmatter 的正文，读不出时为 `null`；`resources` 是技能目录下的普通文件，只给相对路径，不跟随符号链接，
跳过隐藏文件与 `__pycache__`，最多 200 条，`kind ∈ script|reference|config|doc`。名字不存在或 domain 不符 → `404 skill_not_found`。

**`GET /mcp/servers`**：`{servers: [...]}`，先是配置中的服务器（`name`、`type`/`transport`、stdio 的 `command`/`args`/`env`
或 http 的 `url`/`headers`、`enabled`、有允许列表时的 `tools`、`state ∈ connected|failed|disabled|pending`、`active`、`error`），
再是被拒条目（只有 `name`、`state: "failed"`、`active: false`、`error`）。配置是本进程启动时用的那份，改 `.mcp.json` 后要重启。
`${VAR}` 在五个字段里都会展开，所以 `command`/`args`/`url` 显示 `.mcp.json` 里**未展开的原文**（文件读不到时省略这三项），
`env`/`headers` 只保留键、值一律为 `"••••"`；`error` 里启动环境中长度不少于 8 的值被替换成 `"••••"`，截到 300 字符；
没有启动环境（未注入 settings）时被拒条目的 `error` 固定为 `"invalid_config"`。没有 `.mcp.json` → `{servers: []}`。

**`GET /providers`**（`providers.py`）：`{providers: [{name, display_name, tier, base_url, default_model, models, model_metadata:
[{id, context_window}], env_key, configured, configured_via, configured_base_url, active}], current, current_model, restart_pending, env_file}`。
provider 按 `DETECT_ORDER` 在前；`base_url` 是预设自带的端点。`configured_via ∈ provider-env|generic-env|explicit-provider|null`，
按"下次启动的环境"判断：全部候选 `.env` 先加载者优先，再叠加启动前已导出的变量；只含空白的密钥不算配置。
**`generic-env`（通用 `LLM_API_KEY`/`OMICSCLAW_API_KEY`）只对 `LLM_PROVIDER` 指向的 provider 生效**（未指定 provider 时还有 `custom`），
所以保存另一个 provider 之后，靠通用密钥配置的那一行会显示未配置；反过来，切到一个没有专属密钥变量的 provider（如 `custom`）又不填密钥时，
重启后通用密钥会发给新的厂商（与 `oc cli --configure` 相同）。
`configured_base_url` 是选中该 provider、且不另给端点时下次启动实际生效的端点，即 `resolve_config(name, env=下次启动的环境).base_url`：
依次是 `<PROVIDER>_BASE_URL`、适用时的通用 `LLM_BASE_URL`/`OMICSCLAW_BASE_URL`、预设端点；总是字符串，`""` 表示没有（SDK 缺省端点，
或什么都没设的 `custom`）。例：文件里有 `OLLAMA_BASE_URL=http://gpu:11434/v1` 时 ollama 行为 `"http://gpu:11434/v1"`，
zhipu 行在没有任何设置时为预设的 `"https://open.bigmodel.cn/api/paas/v4"`，openai 行为 `""`。App 用它预填端点并在保存时回传，
这样 `PUT` 不会把别处设好的远端端点写成空串。
`current`/`current_model` 是运行中的配置（用启动快照求），与下次启动的 provider、模型、端点不同时 `restart_pending: true`。
已知局限：部署用 `--provider`/`--model` flag 启动，或 `.env` 的值含 `${…}` 插值（加载器会展开、这里按原文读）时，`restart_pending` 可能一直为真。
任何密钥或其尾号都不出现。没有 settings 时 `env_file: null`、所有条目未配置。
**`PUT /providers`** `{provider, api_key?, model?, base_url?}`：其他键 → `422 unknown_field`；provider 不是预设 → `422 unknown_provider`；
值不是字符串、含控制字符或超过 4096 字符 → `422 invalid_value`；`custom` 缺 `model` 或 `base_url` → `422 custom_endpoint_required`。
写入规则：provider 写文件里已有的 `OMICSCLAW_PROVIDER`，否则 `LLM_PROVIDER`，两者都在文件里时写成同一个值；非空密钥写预设自己的变量（如 `DEEPSEEK_API_KEY`，
`custom` 等无专属变量的写 `LLM_API_KEY`），空密钥不动已有值；模型写文件里已有的 `OMICSCLAW_MODEL`、`LLM_MODEL`（有几个写几个），都没有时写 `LLM_MODEL`；端点写文件里已有的
`<PROVIDER>_BASE_URL`、`LLM_BASE_URL`、`OMICSCLAW_BASE_URL`（有几个写几个，同一个值），都没有时写 `LLM_BASE_URL`；换了 provider 时，没给模型写新预设的缺省模型，
没给端点写空串。成功 200 `{ok: true, provider, model, restart_required: true, env_file, written, shadowed_by_environment}`，
`provider`/`model` 是下次启动会用的，`shadowed_by_environment` 列出让写入不生效的已导出变量：写入的变量本身被导出成另一个值；同一设置的其他写法被导出成非空的另一个值，且它比写入的写法先读、或写入的是空值、或它是 provider 的写法（`AppConfig` 与 `resolve_config` 读 provider 的顺序相反）。与写入值相同的导出不算。文件读写失败（含非 UTF-8）→
`500 env_write_failed`，文件不变。变量名规则与 `oc cli --configure` 共用 `entry/cli/_configure.py` 的 `names_to_write`；写入沿用 CLI 向导的 `write_dotenv`（原子替换、保留权限、先存 `.env.backup-<时间戳>`）。
**`POST /providers/test`** `{provider, model?, base_url?, api_key?}`：按下次启动的环境求配置，`max_retries=0`、`max_tokens=256`、
`timeout_seconds=15`、思考关闭，发一次 `ping`，20 秒上限；调用没有抛异常即通过（空正文也算）。一律 200：
`{ok: true, message, provider, model, duration_ms}` 或 `{ok: false, message, detail, duration_ms}`，`message` 里本次用的密钥（不少于 8 个字符时）换成 `…`、
截到 300 字符，`detail` 是异常类型名（有 HTTP 状态时附上）。每次新建的 adapter 用完后，若它有 `aclose()`/`close()` 就调用（现有 adapter 都没有）。没有 settings 时 PUT 与 test 返回 `503 settings_unavailable`。

**`POST /chat/title`**（`title.py`）：请求 `{schema_version: 1, source_request_id: <32 位小写十六进制>, user_text: <1–4096 字符>}`；
用运行中的 provider `bind(max_tokens=1024, thinking_budget_tokens=0)` 生成一次，30 秒上限，取第一个非空行、去掉成对引号、截到 80 字符。
成功 200 `{schema_version: 1, title}`；失败 `{schema_version: 1, error: {code}}`：`422 TITLE_REQUEST_INVALID`、`502 TITLE_OUTPUT_INVALID`
（空结果）、`504 TITLE_TIMEOUT`、`502 TITLE_PROVIDER_FAILED`。请求体层面的拒绝（415、413、JSON 解析失败）仍是 `{"detail": code}`。

**`GET|HEAD /health`**：`health_payload(app)` 返回 `status`、`version`、`backend_process_epoch`（每进程随机，客户端据此发现后端重启）、
`provider`、`model`、`skills_count`、`python_executable`、`skill_python_executable`、`omicsclaw_dir`（= workspace）、`launch_id`、
`served_paths`，以及只含 `desktop_chat` 一项的 `contracts`：

```json
{"request_schema_version": 3, "sse_schema_version": 3, "interrupt_schema_version": 1,
 "authoritative_ingress": true, "durable_ingress_idempotency": false,
 "source_request_id_required": true, "attachments_supported": false,
 "max_sse_frame_bytes": 4194304, "oversize_event_projection": true,
 "terminal_error_type_preserved": true, "gap_notice": true,
 "abandon_grace_s": 30.0}
```

`abandon_grace_s` 是生效的宽限期（`--abandon-grace` 的值，没给时 30），registry 不取消无人观察的 exchange 时为 `null`；它是进程的事实，不属于线协议，不计入版本号。

设置了 token 而请求未带 `Authorization` 时返回精简版 `unauthenticated_health_payload`。

**交互状态**（`interactions.py` 的 `DesktopInteractions`，每个 `create_desktop_app` 一个，只在内存里且都有上限）：
已发卡片的待决请求（结算后淘汰）、会话授权与 `full_access` 会话（按会话 LRU 淘汰，淘汰的代价是多问一次）、
`(session_id, source_request_id) → turn_id`（只淘汰 registry 已不保留的 exchange；仍保留的，结束与否都留着，以便续流）、
每个 exchange 的用量账本 `TurnUsage`（各观察读到的 `TURN_END` 按序号记一次，另记各观察读过的序号区间；超出上限时只丢 registry 已不保留的 exchange 的账本）。
自动放行（会话授权与 `full_access`）需要有观察者在场：没有 SSE 体在读的 exchange，其请求要等有人重新观察时才会被放行。

### 8.3 与旧 Desktop 后端相比没有的东西

旧后端（`surfaces/desktop/server.py`，已删除）有 144 条路由；这里只有上表几条。按请求切换 provider/模型、每轮凭据、skill 日志桥、
Run 治理、记忆代理、outputs/bridge 代理、`/v1/turns` 多模态 ingress、审批令牌与 5 分钟自动拒绝都不在当前后端里。
标题生成、技能目录与 MCP 服务器列表由 plan 0065 以新的管理路由补回（`POST /chat/title`、`GET /skills`、`GET /skills/{domain}/{name}`、`GET /mcp/servers`），
MCP 只读，不再代理；App 侧没有后端路由的页面（记忆页与 notebook、bench、KG、optimize、bridge、outputs）已按 plan 0065 隐藏或删除。

---

## 9. Channel 界面：`entry/channel/`

### 9.1 七个适配器

`CHANNEL_REGISTRY`（`entry/channel/__init__.py`）+ `launch/_surfaces.py` 的 `_build_*`，`oc channel --list` 打印：

| 适配器 | 模块 / 投递模块 | 必需凭据（缺失即 `AppConfigError`） | Owner allowlist | 额外依赖 |
|---|---|---|---|---|
| `telegram` | `telegram.py` / `telegram_delivery.py` | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_ALLOWED_SENDERS` **或** `TELEGRAM_CHAT_ID` | `python-telegram-bot`（`[channels]` extra） |
| `feishu` | `feishu.py` / `feishu_delivery.py` | `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、**`FEISHU_BOT_OPEN_ID`** | `FEISHU_ALLOWED_SENDERS` | `lark-oapi`（`[channels]` extra） |
| `slack` | `slack.py` / `slack_delivery.py` | `SLACK_BOT_TOKEN`、`SLACK_APP_TOKEN` | `SLACK_ALLOWED_SENDERS` | `slack-sdk aiohttp` |
| `discord` | `discord.py` / `discord_delivery.py` | `DISCORD_BOT_TOKEN` | `DISCORD_ALLOWED_SENDERS` | `discord.py` |
| `dingtalk` | `dingtalk.py` / `dingtalk_delivery.py` | `DINGTALK_CLIENT_ID`、`DINGTALK_CLIENT_SECRET` | `DINGTALK_ALLOWED_SENDERS` | `httpx websockets` |
| `qq` | `qq.py` / `qq_delivery.py` | `QQ_APP_ID`、`QQ_APP_SECRET` | `QQ_ALLOWED_SENDERS` | `qq-botpy` |
| `email` | `email.py` / `email_delivery.py` | `EMAIL_IMAP_HOST`、`EMAIL_IMAP_USERNAME`、`EMAIL_SMTP_HOST`、`EMAIL_SMTP_USERNAME` | `EMAIL_ALLOWED_SENDERS` | 仅标准库 |

各平台 SDK 都在首次需要客户端的方法里惰性导入，所以 `oc channel --list` 不装任何 SDK 也能运行；缺包时启动报
`MissingSurfaceDependency`（退出码 2，提示 `pip install <name>`）。完整变量表见 `.env.example` 第 11 节（速率限制、代理、Feishu 附件上限等）。

> `FEISHU_BOT_OPEN_ID` 是必填项：`_build_feishu` 在它缺失时**拒绝启动**。

### 9.2 启动顺序

```
start_channel
  ├─ 解析 --channels / --health-port / --verbose / --list；部署半边先解析
  └─ _serve_channels  （整个过程在 _stop_signals 内：SIGTERM/SIGINT → 有序关闭，退出码 143/130）
       ├─ channels = [build_channel(name, env) ...]     ← 先建适配器：缺凭据最常见，不必先付 MCP 启动代价
       ├─ app = attach_sessions(await open_app(config))
       ├─ runtime = await compose_channel_runtime(app, channels)
       │     1. 每个 channel prepare_control_binding()（认证 + 产出 ChannelSurfaceBinding）——任一失败则全部释放
       │     2. ChannelRuntime(...) 校验：app 有 sessions；approval_timeout_s 必须是数值；适配器不重复
       │     3. runtime.start()，再 bind_control_runtime(runtime, loop=...)
       ├─ manager.start_all()      ← 所有 channel 的 ingress **同时**打开
       ├─ [--health-port] manager.start_health_server(port)
       └─ manager.run()  …  finally: runtime.close(); app.aclose()
```

一个进程只有一个 `ChannelRuntime`，多个平台共享一个会话注册表；`--channels` 全起或全不起，所以建议**一个平台一个进程**。
同一平台两个账号需要两个进程（一个入站消息只按适配器名定位 surface）。

**必须配置审批期限**：`ChannelRuntime.__init__` 在 `app.config.approval_timeout_s is None` 时抛 `ValueError`，而
`oc channel` 不会替你设默认值——需要 `--approval-timeout <秒>` 或 `OMICSCLAW_APPROVAL_TIMEOUT_S`，否则启动失败（外壳报告为退出码 1）。

### 9.3 `ChannelRuntime` 的三项义务

1. **先拒绝**：`submit` 在触碰注册表之前先问 `SenderPolicy`，名单外的消息不产生 exchange。
2. **关闭观察**：每个观察都用 `async with` 打开，保证放弃计时能开始。
3. **跳回事件循环**：SDK 在自己线程上的回调只能用 `settle_approval_threadsafe`（`call_soon_threadsafe`）。

### 9.4 回复怎么出去

- 运行期间只推送"需要用户注意"的帧：`DEFAULT_DELIVERED_TYPES = {QUEUED, APPROVAL_REQUIRED, APPROVAL_SETTLED, EXCHANGE_END}`。
- **答案在 exchange 结束后从轨迹一次性投递**，而不是逐 token：平台都限流；增量帧按契约可丢弃。
  长文本按 `binding.text_chunk_limit`（`DEFAULT_TEXT_CHUNK_LIMIT = 4096`）用 `chunk_text` 切块。
- `delivery.deliver`：单条消息最多 `MAX_DELIVERY_ATTEMPTS = 3` 次、每次 `ATTEMPT_TIMEOUT_S = 30.0` 秒；适配器返回
  `ACCEPTED` / `NOT_ACCEPTED_RETRYABLE` / `REJECTED_PERMANENT` / `ACCEPTANCE_UNKNOWN`，只有可证明可重试的才重试，
  `ACCEPTANCE_UNKNOWN` 不盲目重发。不持久化——回复只活在进程里（持久 outbox 是被删控制面的能力）。
- 每个平台的能力声明在 `ChannelCapabilities`（`format_type`、`max_text_length`、`markdown`、`groups`、`mentions`、`edit` …）；
  不渲染 Markdown 的客户端不应收到星号，由一致性测试检查。

### 9.5 内置斜杠命令

`entry/channel/commands/builtins.py` 注册：`/clear`、`/compact`、`/new`、`/files`、`/outputs`、`/recent`、`/skills`、`/status`、`/version`、
`/demo`、`/examples`、`/help`（`/help` 只列出实际注册的命令）。斜杠命令不会到达模型（一致性规则之一）。
旧的 `/forget`、`/plan` 未恢复。`/demo` 只是返回几条"用自然语言请求 demo"的示例文本，并不直接执行 skill。

### 9.6 一致性测试代替基类

七个相似适配器靠 `tests/entry/test_channel_cutover_conformance.py`（+ `tests/entry/channel_conformance.py`）维持一致：
遍历注册表，对每个声明 `authoritative_ingress` 的适配器检查八条规则——回复目标两半一致、超时不被归为可重试、群聊闸门不是恒开、
斜杠命令不到模型、不渲染 Markdown 的客户端不收星号等。以代码共享的只有 `reply_target.py`、binding 上的分块上限守卫与
`Channel.command_context`。

### 9.7 附件

`ChannelSurfaceBinding.attachment_input_enabled` 被钉为 `False`：`omicsclaw.schema.Message` 只有 `content: str`，没有内容分片，
入站图片无处可去（plan 0031 §5.3）。因此发给 Channel 的照片不会交给模型：Telegram 回一句不支持，其余适配器拒收或丢弃非文本消息。

---

## 10. 已知限制

1. **Desktop 的会话授权与 `full_access` 需要观察者在场**：没有 SSE 体在读的 exchange 不会被自动放行；审批没有期限，停止（`/chat/abort`）是唯一的出口。
2. **Channel 上无法回答审批**：`settle_approval*` 没有生产调用方，所有 ASK 工具到期被拒；文本回复 / 按钮在 plan 0052 中规划。
3. **Channel 必须设置 `approval_timeout_s`**，`oc channel` 不提供默认值。
4. **Channel 回复不持久**：没有 outbox、回执、重放；进程退出即丢。
5. **不支持附件**：入站图片/文件被丢弃，出站媒体未完成。
6. **三个界面都没有与真实 provider、真实 HTTP 客户端、真实 IM 平台做过持续测试**（FRAMEWORK-REBUILD "Debts carried forward"）。
7. **TUI 未移植**。
8. **文档漂移**：`docs/ARCHITECTURE.md` 仍描述 `ControlRuntime`、`control.db`（iMessage 与 WeChat 适配器已随代码移除，ARCHITECTURE 也不再列出）。
   以本文与 `entry/` 代码为准。
9. `/demo`（Channel）示例里的 `spatial-domain-identification` 不是现有 skill 名（应为 `spatial-domains`）。

---

## 11. 文件索引

| 文件 | 内容 |
|---|---|
| `omicsclaw/entry/__init__.py` | 层说明与公开符号 |
| `omicsclaw/entry/config.py` | `AppConfig`、`resolve_app_config`、`SkillsIndex`、`SandboxMode` |
| `omicsclaw/entry/assembly.py` | `build_app`、`open_app`、`AgentApp`、`foundation_tools`、`default_sections`、`SAFETY_RULES` |
| `omicsclaw/entry/session.py` | `SessionRegistry`、`Session`、`SessionStore`、`InMemorySessionStore`、`attach_sessions`、`QueueFull`、`RegistryClosed` |
| `omicsclaw/entry/turn.py` | `compose`、`prepare`、`run_turn`、`stream_turn`、`TurnRunner`、`TurnHandle`、`TurnOutcome` |
| `omicsclaw/entry/events.py` | `TurnEventType`、`TurnEvent`、`Terminal`、`DROPPABLE_TYPES` |
| `omicsclaw/entry/stream.py` | `TurnStream`、`TurnObservation`、`DEFAULT_RING_SIZE` |
| `omicsclaw/entry/render.py` | `TextRenderer`、`to_wire`、`DESKTOP_CHAT_FRAME_TYPE` |
| `omicsclaw/entry/approval.py` | `ApprovalBroker` |
| `omicsclaw/entry/ingress.py` | `InboundMessage`、`SenderPolicy`、`Acceptance`、`DeliveryResult` |
| `omicsclaw/entry/memory.py`、`compaction.py`、`planning.py`、`sandbox.py`、`subagent.py` | 各子系统在组合根中的接线 |
| `omicsclaw/entry/cli/` | 终端界面，见 cli.md |
| `omicsclaw/entry/desktop/server.py` | `create_desktop_app`、`open_chat_stream`、`health_payload`、`workspace_payload`、`change_workspace` |
| `omicsclaw/entry/desktop/interactions.py` | `DesktopInteractions`、`answer_permission`、`abort_chat` |
| `omicsclaw/entry/desktop/turn_submission.py`、`turn_observation.py`、`_chat_sse.py`、`wire_contract.py` | 请求解析、SSE 投影、帧渲染、契约版本 |
| `omicsclaw/entry/channel/runtime.py` | `ChannelRuntime`、`compose_channel_runtime`、`DEFAULT_DELIVERED_TYPES` |
| `omicsclaw/entry/channel/base.py`、`binding.py`、`capabilities.py`、`manager.py`、`delivery.py`、`reply_target.py` | 适配器基础设施 |
| `omicsclaw/entry/channel/{telegram,feishu,slack,discord,dingtalk,qq,email}.py` 与 `*_delivery.py` | 七个适配器 |
| `omicsclaw/entry/channel/commands/` | 内置斜杠命令 |
| `omicsclaw/launch/_surfaces.py` | `start_desktop`、`start_channel`、`build_channel`、`_build_*` |
| `tests/entry/` | 组合根、会话、流、渲染、审批、Desktop HTTP/线协议、Channel 适配器与一致性 |
| `docs/plans/0031-entry-layer.md`、`0044-channel-surface-cutover.md`、`0052-channel-approval-replies.md` | entry 层设计、Channel 全平台接入、Channel 审批计划 |
