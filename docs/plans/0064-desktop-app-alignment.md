# 计划 0064 — OmicsClaw-App 接入重建后的后端（Desktop 对齐）

**状态**：第 3.1 版（2026-09-27），owner 已裁定 Q1–Q11（包括 Q1 的子项 0.2.0）；0057 的冻结检查已由 owner 撤销，Q2 随之失去作用（见修订说明）。**未写任何生产代码。**

**涉及仓库**
- 后端：`/workspace/dataset/private/zhouwg_data/OmicsClaw`，以工作树为准。
- 桌面客户端：`/workspace/algorithm/zhouwg_project/OmicsClaw-App`，HEAD `11f69cb`，工作树干净。

**前置与关联**：0031（Q24、§5.2、§11、附录 B）、0037（`oc desktop`、§A.3 的未核实项）、0052（§8.1 desk 上提）、0054（G3）、0057（留出集运行 T12）、0063（F22）；App 的 ADR 0001、0004、0005。

**行号约定**：后端以 2026-09-27 工作树为准，App 以 `11f69cb` 为准。实施时按符号名重新定位。

**如何核实**：代码逐处亲自读过；在 OmicsClaw 解释器下跑了相关测试；在 `/tmp` 的临时工作区起过一次真实的 `oc desktop`（附录 B）。

### 修订说明

**第 3.1 版（2026-09-27，事实更新）**
- owner 已撤销 0057 的全部冻结检查：不再比对代码指纹，没有环境锁，也没有签字闸门；`frozen_settings` 只作记录保留，种子注入不变。这一事实由 0057 会话转达，并记入 owner 的项目记忆。0057 的留出集运行（T12）随即开始。
- 已核实：`freeze.py` 与 `freeze.json` 已不在仓库里；`run_holdout.py` 只为记录计算一份代码摘要，不做拦截。
- 相应改动：
  - Q2 = d 已不再需要，裁定保留，作为历史记录；
  - 删除后端 P0 的"核实冻结已签字"前置条件；
  - 删除由环境锁推出的"不提交、不装包、不重装"规则；
  - 保留一条软约束：留出集运行期间，后端只改 0057 不导入的路径（§4.9）；
  - 0.2.0 仍放在统一提交里，理由改为要与 App 的 `expectedBackendVersion` 同时发布。
- 涉及章节：§0、§2.5、§4.1、§4.9、§4.11、§5、陷阱 3 与 15、§8、§9，以及附录。

**第 3 版（2026-09-27）**：owner 对推荐项全部接受。此后又补裁了两项：Q2 = d；包版本升到 0.2.0，但放在留出集结束后的统一提交里。主要改动如下：

- §8 改为裁定记录。
- 按 Q2 = d：
  - 后端 P0 的前置条件是：已签字的 `freeze.json` 不再覆盖 `entry/desktop/**`；
  - 后端改动只能落在 `entry/desktop/**` 与不受冻结的路径里；
  - 一旦需要动共享模块，就停下来问 owner（§4.9）。
- 按 Q11 = a，原 P2、P4 移出本计划，改为 §5.5"后续计划（不在本计划内）"，并把约束它们的裁定写全。新增 §2.7，列出 P0/P1 期间仍会碰到死路由的旧页面及其失败方式。矩阵的期次改为后续计划的名称。
- Q4 = a：B0-2 只要求 JSON，Host 白名单作为"记录在案、未采纳"的选项保留。
- 纳入新事实：`freeze.json` 草稿已于 10:10:35 UTC 生成（§2.5、§4.9）。
- 纳入复审意见（附录 C）：
  - "未选项目"的判定改由 App 的设置决定，`/api/chat` 增加服务端闸门；
  - 侧栏、设置页、向导、新建会话四处的项目切换共用一个"确认后重启"的助手函数；
  - 入站 v2 牵动的测试逐一列出；
  - 引用与措辞细节。

**第 2 版（2026-09-27）**：按独立审核修订（M1–M4、m1–m11、n1–n11），处理记录见附录 C。

---

## 0. 摘要（结论先行）

**现状**
- 新后端的 Desktop 面是 `omicsclaw/entry/desktop/`，由 `oc desktop` 启动。按 0031 Q24 与 §5.2，它只提供 `POST /chat/stream` 和 `GET/HEAD /health`。
- App 是按旧后端写的：`surfaces/desktop/server.py` 加 `omicsclaw/remote/`，共 144 条路由，另有 `/kg/*`。旧后端的依赖已全部删除，现在连 import 都会失败。
- 所以 App 起不来本机后端。就算手动把它指向 `oc desktop`，第一次需要审批的工具调用就会让整条流报错。

**头号事实：`oc desktop` 在真实 HTTP 下两条路由都返回 422**（附录 B）
- `server.py:29` 启用了 `from __future__ import annotations`，而 `Request` 是在函数内部 import 的（`:296`），FastAPI 于是把 `request` 当成了查询参数。
- `test_desktop_http.py` 在 OmicsClaw 解释器下 8 条失败 6 条；在 rapids 解释器下整份被跳过，所以一直没人发现。

**本计划的范围（Q11 = a）**

| 期 | 内容 |
|---|---|
| P0 核心对话闭环（本机） | `npm run dev` 与 `npm run electron:dev` 两条路径；工作区由 App 指定；聊天帧正确渲染；审批可答；停止可用 |
| P1 对话完整性 | 全权限、"总是允许"、`/compact`、doctor、不一致会话的处理、待办面板、错误分类 |
| P3 后端旧代码清理 | 含 Q10 的 npm 构建链删除 |

- 原 P2（管理页与退役）、原 P4（远程模式）移入两份后续计划，范围与约束见 §5.5。
- P0/P1 期间仍在的旧页面会碰到死路由，已逐一核对：**都不影响核心闭环，也不影响启动**（§2.7）。

**已裁定的主设计**
1. **Q1 = a，契约由后端定义并版本化。**
   - 帧名沿用 App 已有的名字，字段采用 `to_wire` 的写法。
   - `sse_schema_version` 与 `ingress_schema_version` 都升到 2。
   - App 在 `/health` 和聊天前的身份见证两处做门控。
   - 包版本升到 0.2.0，并同步修改 App 的 `expectedBackendVersion`。这一改动放在留出集结束后的统一提交里，因为两边要一起发布。
2. **后端只补少量路由**，全部只用 `entry` 的公开 API；投影只改 `turn_observation.py`。
3. **安全**
   - Q3 = a：不要审批令牌，后端不做 epoch 围栏。
   - Q4 = a：后端写路由只接受 JSON。
   - DNS 重绑定作为已接受风险记录在案。
4. **工作区与 provider**
   - Q5 = a：工作区归 App；未选项目时用占位目录并禁止聊天；切换项目等于显式重启，最小切换流程放在 P0。
   - Q6 = a：provider 以 `.env` 为准。
   - Q7 = a：按会话自动放行。
5. **退役（Q8 = a、Q9）**：删除代码，数据库表保留；具体执行在后续计划 M 里。

**后端代码放在哪（§4.9）**
- 0057 的冻结检查已经撤销，Q2 = d 失去作用，后端 P0 没有冻结方面的前置条件。
- 保留一条软约束：0057 留出集运行期间，每个单元都会新起进程，重新导入 `omicsclaw.entry`（`entry` 的共享模块）、`ensemble`、`provider` 与空间 skill 的代码。这时候改动这些路径，会让后面的单元测到另一版代码，而且没人会察觉。
- 所以运行期间，0064 的后端改动只落在 `omicsclaw/entry/desktop/**`（0057 不导入）、`omicsclaw/launch/**`、`tests/**` 与文档。
- 留出集结束后，这条约束自动失效。
- App 侧不受影响。

---

## 1. 目标与非目标

### 1.1 目标

| # | 目标 | 验收口径（§6.4） |
|---|---|---|
| G1 | 本机模式下，App 用 `npm run dev` 和 `npm run electron:dev` 都能连上 `oc desktop`：<br>• Electron 路径的预检、launch_id、解释器身份比对都通过；<br>• 工作区由 App 指定，未选项目时禁止聊天；<br>• `text`、`thinking`、`tool_use`、`tool_result`、`tool_output`、`status`、`result`、`permission_request` 八种帧都正确渲染；<br>• 审批可以回答；<br>• 点"停止"后 2 秒内显示"已停止" | §6.3 的浏览器段与 Electron 段 |
| G2 | 契约只在后端 `wire_contract` 一处定义，App 只实现一个版本 | 两个版本号都是 2，App 有门控测试 |
| G3 | P0/P1 期间仍在的旧页面各有一条已知局限，且都不影响核心闭环与启动 | §2.7 |
| G4 | 后端旧的 desktop/remote 代码、旧测试、npm 构建链删除，文档如实更新 | P3 验收 |

### 1.2 非目标

- **附件上行**：新后端返回 409，另立计划。
- **Desktop 上的 ask_user**：0054 G3。
- **App 侧的断线续流。**
- **多工作区后端，按会话切换 provider/model。**
- **把 App 本地的 `/clear`、rewind、删除会话同步给后端**：这是既有差异。
- **恢复以下功能**：Run 治理与回放、控制面 jobs、技能治理、市场、KG、Bench、AutoAgent/Optimize、notebook 内核、OAuth、skill-log 桥。
- **修改 0057 的任何文件。**
- **重写 `AGENTS.md`。**
- **原 P2、P4 的内容**：移到后续计划（§5.5）。
- **App 的 Next API 层自身的 CSRF 与 DNS 重绑定问题**：这是既有风险，按 Q4 的裁定记录在案，不在本计划处理。

---

## 2. 现状与证据

### 2.1 新后端现在提供什么（`omicsclaw/entry/desktop/`，6 个文件）

**路由与入站**
- 只有两条路由（`wire_contract.py:58`），挂在 `create_desktop_app` 上（`server.py:275-397`）。
- 没有 CORS。不检查 `Content-Type`：`_read_body` 读到原始字节后直接交给 `json.loads`（`server.py:310-356`）。
- 入站解析（`turn_submission.py:166-198, 279-339`）：
  - `model`、`effort`、`thinking`、`context_1m`、`output_style`、`permission_profile`、`thread_id`、`stage` 这几个字段接受但忽略（`:211-217`）。
  - `ingress_schema_version` **缺省为 1**：`document.get("ingress_schema_version", 1)`，不等于 1 时返回 422 `unsupported_ingress_schema_version`（`:309-311`）。
  - `session_id` 可以是任意字符串（`:331`）。
  - `workspace` 与后端不一致时返回 409（`server.py:135-144`）。

**出站帧**
- 格式：`data: {"type": T, "data": D}\n\n`，对象载荷先序列化成字符串，单帧不超过 4 MiB。
- 映射在 `turn_observation.py:178-239`：
  - `TEXT_DELTA` → `text`
  - `PROGRESS` → `tool_output`（纯文本）
  - `TOOL_START` / `TOOL_RESULT` → `tool_use` / `tool_result`（取 `to_wire` 的输出）
  - `APPROVAL_REQUIRED` → `permission_request`
  - `COMPACTION` → `status`
  - `GAP` → `event_omitted`
- `REASONING_DELTA`、`TURN_END` 没有对应的帧。

**`/health`**（`server.py:197-250`）
- current-full 的七个字段，加上 `backend_process_epoch` 和 `launch_id`。
- 仍然广播三份实际上不服务的描述符。

**已具备、只缺路由的公开 API**

| 能力 | 位置 |
|---|---|
| 取回合 | `SessionRegistry.handle(turn_id)`（`session.py:502`） |
| 结算审批 | `handle.approvals.settle(...) -> bool`（`approval.py:187-202`，Channel 已有先例，见 `channel/runtime.py:467-482`）；`approvals.pending()`（`:235-237`） |
| 取消 | `TurnHandle.cancel()`（`turn.py:860`） |
| 请求 id 格式 | `f"{turn_id}#{n}"`（`approval.py:141`），`turn_id` 是 `uuid4().hex` |
| 权限 | `set_permission_mode`（`assembly.py:995`）、`remember_approval`（`:1030`）、`can_remember_approval`（`:1054`） |
| 会话 | `list_sessions`、`load_session`、`compact`（`session.py:529, 516, 395`） |
| 其他 | `app.skills`、`app.mcp.statuses()`、`app.permission`、`app.memory` |

**启动**（`launch/_surfaces.py`）
- 命令：`oc desktop [部署 flag] [-- --host --port]`，缺省绑定 `127.0.0.1:8765`。
- 两种情况会拒绝启动：绑在非回环地址又没有 token；`skill_env=install`。
- 缺依赖时的补救提示（`:1167`）是**错的**：fastapi、uvicorn 由 conda 管理（`tests/test_pyproject_thin_pip_layer.py:49-50`）。

### 2.2 App 依赖什么（`11f69cb`）

**启动**
- 以 `spawn(python, ['-m', OMICSCLAW_BACKEND_MODULE])` 启动，**不带参数**（`python-manager.ts:397-399`）。模块缺省是 `omicsclaw.surfaces.desktop.server`。
- host/port 通过环境变量传给后端（`:229-251`）。cwd 是 `omicsclawDir || homeDir`（`local-runtime-plan.ts:104`）。不传工作区。

**工作区**
- `default_project_dir` 实际上只是后端工作区的缓存：
  - `GET /workspace` 返回后会回写它（`backend-workspace.ts:47-56`）；
  - 重置时清空（`api/setup/route.ts:216`、`api/internal/runtime-activation/route.ts:76`）。
- 以下路由读取工作区时，走的都是 `GET /workspace`：`/api/setup` 的 `defaultProject`（`:86-98`）、`/api/workspace/session`（`:24-26`）、`/api/settings/workspace`、`/api/workspace/summary`、`/api/workspace/quick-actions`。
- 写入口有四个，都是 `PUT /api/setup`（project）→ `PUT /workspace`（`api/setup/route.ts:235-241`）：
  - 向导：`useProjectSetup.ts:35`
  - 新建会话的目录选择：`chat/page.tsx:301-307`
  - 侧栏：`ChatListPanel.tsx:300` → `project-switch.ts` 的 `syncBackendWorkspace`
  - 设置页：`OmicsClawSection.tsx:231`
- 此外，打开会话时会自动同步：`chat/[id]/page.tsx:60`、`SplitColumn.tsx:136`。

**预检**：写死 `import omicsclaw.surfaces.desktop.server`（`python-preflight.ts:61-70`）。

**健康检查**
- current-full 加 launch_id（`backend-health.ts:199-315`）。
- 聊天前的见证只检查 epoch（`backend-fetch.ts:757-826`）。

**聊天**
- 请求体（`api/chat/route.ts:665-695`）里 `workspace` 取自 `session.working_directory`。
- 对 `permission_request` 做规范性准入（`:114-148`），不满足就抛异常，整条流报错。

**Electron liveness**：每 5 s 探测一次，超时 3 s；**失败一次就杀掉后端，且不会自动重启**（`python-manager.ts:27, 926-1006`）。

### 2.3 硬阻断清单（逐条亲自核实；帧层面见 §3.2）

| # | 阻断 | 证据 | 影响 |
|---|---|---|---|
| H1 | 两条路由都返回 422 | `server.py:29` 与 `:296`；附录 B-1、B-2 | 什么都连不上 |
| H2 | 启动路径不对 | 旧模块 import 失败；新后端只收 flag | 起不来 |
| H3 | 预检写死旧模块 | `python-preflight.ts:61-70` | 激活失败 |
| H4 | `tool_use` 形状不对 | App 读 `{id,name,input}`，后端发的是 `to_wire` 字段 | 工具卡空白，转录丢失 |
| H5 | `permission_request` 让整条流报错 | `route.ts:114-148` | 第一次审批就断流 |
| H6 | 没有回传通道 | 只有两条路由；`approval_timeout_s=None` | 审批一直等；停止只会断开连接 |
| H7 | 工作区不闭环 | §2.2 | 首次安装或重置后，agent 在 `$HOME` 或检出目录里执行；其他路径返回 409 |
| H8 | provider 模型不同 | 启动时就固定了 | 模型选择器为空 |
| H9 | 压缩的 `status` 被当成初始元信息 | `useSSEStream.ts:258-268` | 状态行显示错误 |
| H10 | App 自动发 `/compact` | `ChatView.tsx:775-784` 等 | 模型会收到字面的 `/compact` |
| H11 | 附件 | 后端返回 409 | 该回合失败 |
| H12 | launch 测试在 OmicsClaw 解释器下会真的起服务并挂住 | 附录 B-3 | 两类测试要分解释器跑（§6.1） |

### 2.4 对 briefing 的更正（独立审核逐条复核，全部成立）

| # | briefing 的说法 | 核实结果 |
|---|---|---|
| E1 | `/health` 基本可用 | 字段齐全，但请求返回 422 |
| E2 | Next 要靠 fd-3 bootstrap | 两条通道，只有打包模式才用（`main.ts:1549-1551`）。不阻断任何一期；新后端不读 fd 3，也没有副作用 |
| E3 | `[desktop]` extra 缺依赖 | 是刻意的，由 conda 管理；该改的是补救提示 |
| E4 | npm 构建器的冒烟测试会失败 | 属实；它的消费者 `npm/` 已在 `259fb52a` 删除（Q10） |
| E5 | App 调用约 144 条路由 | 144 是旧后端的总数，App 只调其中一部分 |
| E6 | 只有 `durable_ingress_idempotency` 说过了头 | `event_queue_capacity` 和 `producer_backpressure` 也不再成立 |
| E7 | 0052 的 desk 可以直接上提 | desk 还没实现 |
| E8 | 未提及 | `wire_contract.py:1-6` 和 `server.py:71-77` 的说法已经过时 |

### 2.5 跨计划约束

**0057 留出集运行（2026-09-27 第 3.1 版更新）**

- **冻结检查已撤销。** owner 撤销了 0057 的全部冻结检查：代码指纹比对、环境锁、签字闸门都不再有；`frozen_settings` 只作记录保留，种子注入保留。
  - 核实：`docs/plans/0057-validation/` 下已没有 `freeze.py` 与 `freeze.json`。
  - `run_holdout.py:37-41` 仍为**记录**计算一份代码摘要，覆盖 `entry/**` 等路径，但不拦截任何运行。
- **哪些代码会被重新导入。** 留出集（T12）正在运行，可以中断后续跑。每个单元新起进程，都会重新导入：
  - `omicsclaw.entry` 的共享部分：`open_app`（`run_arms.py:223`）、`entry.config`（`common.py:112`、`run_arms.py:298`），以及 `entry.turn` 的内部函数 `_assemble`、`_session_bound`（`run_arms.py:377`）；
  - `ensemble`、`provider`、空间 skill 的代码。
- **`omicsclaw.entry.desktop` 没有被任何地方导入。**
- **第 3 版的历史事实**：`freeze.json` 草稿曾在 10:10:35 UTC 生成，覆盖 181 个文件，环境锁里还记着仓库 HEAD。这些检查已随撤销一起失效，下文不再作为约束。

**由此得出的约束（软约束，仅限留出集运行期间）**
- 运行期间改动上述被导入的路径，会让后面的单元测到另一版代码，而且不会被发现。所以 0064 的后端改动只落在 `omicsclaw/entry/desktop/**`、`omicsclaw/launch/**`、`tests/**` 与文档（§4.9）。
- 留出集结束后，这条约束自动失效。
- 提交与装包不再受 0057 限制。owner 另有一条提交策略："0056–0060 全部完成后统一提交"。那是仓库的提交安排，不是 0064 的约束。

**0063**：F22 在本计划里收口。`OMICSCLAW.md:175-177` 的 Known gap 在 P0 后改写。0057 的 A3 用空文件钉住了前置段，所以留出集运行期间改这个文件也不会影响 A3。

**0054**：Desktop 不挂 `ask_user`。

### 2.6 行为变化与已知局限

**相对旧后端的行为变化**

| # | 变化 |
|---|---|
| V1 | 工具结果不再内联图片（旧 `tool_result.media` 在新栈没有对应物） |
| V2 | 长期记忆、权限规则、MCP 配置改为**按工作区**保存（旧后端的记忆用全局命名空间 `desktop_user`，见 `python-manager.ts:241`） |
| V3 | 审批不再在 5 分钟后自动拒绝（旧令牌带有这个期限，见 App `PROJECT_MEMORY.md:81`） |
| V4 | 全权限的语义变窄：危险命令、`ask` 规则、受保护文件仍会询问（P1） |
| V5 | 工具超时不再终止回合 |
| V6 | 错误信息只保留类型名；P1 起补上类别 |

**P0 自身的已知局限**（P1 修复）
- 工作区与后端不一致的历史会话，发送时返回 409，只给出可读的错误提示。
- 全权限开关在 P0 **隐藏**（A0-12）：没有后端路由时它不会生效。
- Electron 激活后停在 `needs-attention`，原因是"Environment Doctor unavailable"，直到 B1-4。
- 手动 `/compact` 暂时移出斜杠菜单，B1-3 恢复。
- 模型选择器为空，A1-5 改为只读展示。

### 2.7 P0/P1 期间仍在的旧页面（交由后续计划 M 处理）

以下页面在 P0/P1 期间保留，会调到后端已经不存在的路由。表中的失败方式都已按代码逐条核实。FastAPI 对未知路由返回 404，响应体为 `{"detail":"Not Found"}`；B0-2 落地后，不带 JSON 类型的写请求改为返回 415。

| 页面或功能 | 调用的死路由 | 观察到的失败方式 | 崩溃？ |
|---|---|---|---|
| Skills 页 | `GET /skills` | `api/skills/route.ts` 把 404 的响应体按 200 转发；`parseSkillCatalogResponse` 因 "domains must be an array" 抛错，页面显示错误状态 | 否 |
| 斜杠菜单里的技能项 | `GET /skills` | `useSlashCommands.ts:102-110` 在 `res.ok` 时读 `data.skills`，读不到就是空列表，技能项不出现 | 否 |
| 技能治理、回放卡、市场 | `/skill-evolution/*`、`/v1/runs/*/replay`、`/skills/installed` | 面板显示错误状态，或返回空列表 | 否 |
| Memory 页 | `/memory/*` | 代理转发非 2xx，页面显示错误状态 | 否 |
| MCP 页 | `/mcp/servers` | 状态路由返回 `{servers:[], error}`，页面显示错误 | 否 |
| Notebook | `/notebook/*` | 返回 502 `backend_missing_notebook_routes`，附带说明（`api/notebook/proxy.ts`） | 否 |
| Bench | `/thread/*`、`/onboard/*` | 引导状态是尽力而为（`bench/page.tsx:24-30`），页面为空状态 | 否 |
| KG explorer | `/kg/*`、`/health.kg` | `/health` 里没有 `kg`，显示"不可用" | 否 |
| Optimize | `/autoagent/*` | 启动时返回 503 `autoagent_durable_runtime_unavailable` | 否 |
| Bridge | `/bridge/*` | 转发 404，页面显示错误 | 否 |
| Outputs 面板 | `/outputs/*` | 显示空或错误 | 否 |
| Providers 设置页、向导的 LLM 步骤 | `GET/PUT /providers` | 列表为空，保存失败（这一步可以跳过）。只要 `/health.provider` 非空，聊天仍可用 | 否 |
| CLI 设置、OAuth | `/claude/settings`、`/auth/*` | 分别返回 502、503 | 否 |
| Env 自适应面板 | `/env/overlays` 等 | 404 映射为 `not_supported`，属于有意的优雅降级 | 否 |
| 自动标题 | `/chat/title` | 回落到启发式标题，属于有意的优雅降级 | 否 |
| `instrumentation.ts` 的 autoagent 回执对账 | `/autoagent/reconcile`、`abort-receipt` | 只有存在旧的待处理回执行时才会运行。发出后不等待，错误被吞掉，按退避重试（`autoagent-receipt-cancellation.ts:91-94, 155-160`），只在后台产生重试噪音 | 否 |
| fd-3 与 Next bootstrap | — | App 内部机制，与后端无关 | 否 |
| 远程模式的 jobs 面板、文件树 | `/jobs*`、`/files/*` | 远程模式在后续计划 R 之前不在验证范围内 | 否 |

**结论：这些都不在核心闭环和启动的路径上。**
- 核心闭环只用到 `/health`、`/chat/stream`、`/chat/permission`、`/chat/abort`、`/workspace`，以及 App 本地的 SQLite 路由。
- 启动路径：
  - Electron：预检 → `/health` → `/env/doctor`，其中 `/env/doctor` 返回 `not_supported` 时状态为 `needs-attention`，不阻断启动。
  - Next：`instrumentation` 发出对账后不等待结果，不影响启动。

---

## 3. 兼容矩阵

**处置代码**

| 代码 | 含义 |
|---|---|
| B-改 | 改造后端 |
| B-薄 | 后端新增薄路由 |
| A-改 | App 改造 |
| A-退 | App 删除 |
| 不需要 | App 不调用，也不需要承接 |

**期次**
- P0、P1、P3：本计划内的阶段。
- **M**：后续计划"Desktop 管理页与功能退役"（暂名，原 P2）。
- **R**：后续计划"Desktop 远程模式"（暂名，原 P4）。

两份后续计划见 §5.5。

### 3.1 路由矩阵（旧后端 144 条，另加 `/kg/*`）

| # | 组（旧路由数） | 路由 | 处置 | 期 | 新栈承接 |
|---|---|---|---|---|---|
| 1 | 聊天流（1） | `POST /chat/stream` | B-改（修 H1、只收 JSON、v2 投影、入站 v2）+ A-改 | P0 | `entry/desktop` |
| 2 | 中止（1） | `POST /chat/abort` | B-薄 | P0 | `handle.cancel()` |
| 3 | 持久回合（7） | `/v1/turns*`、`/turns/*` | 不需要；删掉对应描述符 | P0 | — |
| 4 | 审批（2） | `POST /chat/permission` | B-薄 + A-改 | P0 | `approvals.settle` |
| | | `POST /chat/session-permission-profile` | B-薄；P0 期间隐藏开关 | P1 | Desktop 交互状态 |
| 5 | 标题（1） | `POST /chat/title` | B-薄（Q9③） | M | `app.provider.generate` |
| 6 | Run 治理（5） | `/v1/runs*` | A-退 | M | 无 |
| 7 | 工作区（2） | `GET /workspace` | B-薄；本机模式下只用于一致性检查 | P0 | `app.config.workspace` |
| | | `PUT /workspace` | B-薄：路径相同返回 200，不同返回 409；App 在本机模式下改为"写设置并重启" | P0 | — |
| 8 | 文件（3） | `/files/*` | 远程只读，限定在工作区内，需要 bearer（Q9⑥） | R | 工作区 |
| 9 | 健康（2） | `GET/HEAD /health` | B-改：契约 v2 | P0 | `health_payload` |
| 10 | 技能目录（2） | `GET /skills*` | B-薄，只读 | M | `app.skills` |
| 11 | 技能生命周期（3） | installed、install、uninstall | A-退 | M | 无 |
| 12 | 技能治理（10） | `/skill-evolution/*` | A-退，连同 fd-3 与 Next bootstrap | M | 无 |
| 13 | 记忆（19） | `/memory/*` | 隐藏页面，另立计划重做（Q9②） | M | `LongTermStore` |
| 14 | 线程/Bench（14）、引导（4） | `/thread/*`、`/onboard/*`、`/preference/bench` | A-退 | M | 无 |
| 15 | 设置（3） | `GET /settings`；`/claude/settings` | 不需要；A-退 | M | 无 |
| 16 | providers（3） | `GET/PUT /providers`、`POST /providers/test` | B-薄（Q6 = a，含 S9） | M | `provider.config` |
| 17 | OAuth（3） | `/auth/{provider}/*` | A-退 | M | 无 |
| 18 | MCP（5） | `GET /mcp/servers` | B-薄，只读 | M | `load_mcp_config` + `statuses()` |
| | | 写入（3）、`/mcp/sync` | 推迟（Q9④）；`/mcp/sync` 不需要 | M | — |
| 19 | 产出（2） | `/outputs/*` | A-退（Q9⑤） | M | 无 |
| 20 | Bridge（6） | `/bridge/*` | A-退（Q9①） | M | `oc channel` |
| 21 | Notebook（16） | `/notebook/*` | A-退 | M | 无 |
| 22 | 远程连接测试（1） | `/connections/test` | 不需要 | — | — |
| 23 | datasets（4）、artifacts（2） | `/datasets*`、`/artifacts*` | A-退 | M | 无 |
| 24 | 远程 env（5） | `GET /env/doctor` | B-薄，最小实现 | P1 | `app.*` 事实 |
| | | 其余 4 条 | A-退 | M | 无 |
| 25 | 远程 jobs（6） | `/jobs*` | A-退 | R | 无 |
| 26 | 远程会话恢复（1） | `/sessions/{id}/resume` | 不需要 | — | — |
| 27 | AutoAgent（11） | `/autoagent/*` | A-退（含 `instrumentation.ts`） | M | 无 |
| 28 | KG | `/kg/*` | A-退 | M | 无 |

合计：1+1+7+2+1+5+2+3+2+2+3+10+19+18+3+3+3+5+2+6+16+1+6+5+6+1+11 = **144**，另加 `/kg/*`。

### 3.2 SSE 帧矩阵（字段细节见 §4.2）

| 帧 | v1 App 读取 | 新后端现状 | v2 处置 | 期 |
|---|---|---|---|---|
| `text` | 字符串增量 | 一致 | 不变 | — |
| `thinking` | 字符串增量 | 不发 | B-改：开始发 | P0 |
| `tool_use` | `{id,name,input}` | `to_wire` 字段 | A-改 | P0 |
| `tool_result` | `tool_use_id`、`content`、`is_error`、`media`… | `to_wire` 的同名字段 | 已兼容；`media` 等字段的读取在 M 里删除 | M |
| `tool_output` | `_progress` 或纯文本 | 纯文本 | 已兼容；`_progress` 分支在 M 里删除 | M |
| `status` | 初始元信息或压缩 | 压缩，外加身份字段 | A-改：先判断 `kind` | P0 |
| `result` | `{usage,provider,model}` | 不发 | B-改：converged 时在 `done` 之前发 | P0 |
| `permission_request` | v1 形状 | `to_wire` | B-改 + A-改（v2） | P0 |
| `event_omitted` | 没有 case | 发 | A-改：提示 | P1 |
| `error` | 字符串或 JSON | 类型名 | `cancelled` 映射为"已停止"（P0）；P1 起可选择加类别 | P0/P1 |
| `keep_alive`、`done` | — | 一致 | 不变 | — |
| `task_update` | 待办列表 | 不发 | A-改：从 `plan_write` 派生 | P1 |
| `tool_log`、`tool_timeout`、`mode_changed`、`ask_user_question`、`preflight_pending`、`pathology_detected` | 各有 case | 不发 | A-退；P0/P1 期间这些 case 是死分支，无害 | M |

---

## 4. 设计

### 4.1 契约所有权与版本（Q1 = a，已裁定）

**为什么不再沿用 0031 Q24。**
- Q24 的前提是：后端在一个现存客户端后面重新实现，契约的作者是旧 `server.py`。
- 这个作者已经不存在了，它的词汇（`suggestions`、`ExitPlanMode`、`approvalToken`）指向已经删除的运行时。

**归属规则**
- 后端定义并版本化 Desktop 线协议，覆盖 `/chat/stream` 的请求与帧、`/chat/permission`、`/chat/abort`、`/workspace`、`/health`。
- App 只实现当前版本。
- 帧名沿用 App 已有的名字，字段采用 `to_wire` 的写法。
- 以后任何字段变更，都要做三件事：版本号加 1、两个仓库同批改、在本类计划里记录。

**版本**

| 版本 | 变化 | 理由 |
|---|---|---|
| `sse_schema_version` | 1 → **2** | 覆盖帧，以及 `/chat/permission` 的请求与响应 |
| `request_schema_version`（入站 `ingress_schema_version`） | 1 → **2**；后端**只接受 2**，字段缺失也拒绝 | 两个方向都能显式失败：旧 App 连新后端，第一次发送就得到 422；新 App 连旧后端，同样被拒绝。App 总是会发送这个字段（`chat-ingress/contract.ts:83`） |
| `interrupt_schema_version` | 保持 1 | 请求体不变 |
| 其余 5 个常量与 3 份描述符 | 删除 | 没有路由在服务它们 |

**App 侧门控**：`validateBackendHealthPayload` 与 `witnessBackendIdentity` 都要求 `sse_schema_version === 2`。这是拒绝不兼容的后端，不是兼容层。

**包版本（已裁定）**
- 升到 **0.2.0**：`omicsclaw/version.py:7` 与 `pyproject.toml` 的 `version`，同时改 App 的 `package.json:4` 的 `expectedBackendVersion`。
- 这一改动放在**留出集结束后的统一提交**里。唯一的理由是：后端版本号要和 App 的 `expectedBackendVersion` 一起发布。
- 所以 P0/P1 实施与验收期间，后端仍报 `0.1.2`，兼容性只看契约版本。

### 4.2 v2 帧与回传形状（逐字段）

**帧封装不变**：两个键；D 为字符串；没有 `id:` 行；单帧不超过 4 MiB。

**投影只改 `entry/desktop/turn_observation.py`**
- 不改 `render.py` 的 `DESKTOP_CHAT_FRAME_TYPE` 与 `_approval_payload`。
- 要同步修改 `test_desktop_stream.py:600-617`：去掉其中的 `REASONING_DELTA`，另加 `thinking` 用例。`TURN_END` 仍然不产生帧。
- `test_render.py:475-499` 不受影响。

**逐帧定义**
- **`text`**：不变。
- **`thinking`**（新）：D 是推理增量字符串，取自 `REASONING_DELTA` 的 `event.engine.delta`。
- **`tool_use`**：取 `to_wire(TOOL_START)` 的载荷。App 这样用：
  - `tool_use_id` → id；
  - `tool_name` → name；
  - `arguments` 是原始 JSON 串，`JSON.parse` 成对象后作为 `input`；解析失败或结果不是对象时，用 `{arguments: 原文}`（ADR-0005）。
  - 持久化的块仍是 `{type:'tool_use', id, name, input}`。
- **`tool_result`**：不变。`elapsed_s` 包含审批等待时间，**不能**标成"工具耗时"。
- **`tool_output`**：不变，纯文本。
- **`status`（压缩）**：后端不变。App 先判断 `kind === 'compaction'`，然后：
  - `messagesCompressed = msgs_before - msgs_after`
  - `tokensSaved = tokens_before - tokens_after`
  - `degraded` 非空时附一句说明（en/zh）。
- **`result`**（新）：converged 时，在 `done` 之前发一次。
  - `usage`：本次观察内所有 `TURN_END` 的 `to_wire` 用量按键求和，键名保持 `to_wire` 的写法：`input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_write_tokens`。App 的 `normalizeTokenUsage` 需要在 creation 候选键里加上 `cache_write_tokens`（`token-usage.ts:56-62`）。
  - 其他字段：`usage_reported`、`model_calls`、`provider = app.provider.name`、`model = app.config.model`（P1 改为有效模型，见 B1-7）。
- **`permission_request`（v2）**
  - 字段：`request_id`（形如 `<32hex>#<n>`）、`turn_id`、`session_id`、`sequence`、`tool_name`、`arguments`、`reason`、`reason_shows_call`、`risk_level`、`approval_mode`、`ask_every_time`；P1 再加 `can_remember`。
  - 只在请求仍然待决时发出；如果被自动放行，就不发。
- **`event_omitted`**：后端不变，App 在 P1 显示一条提示。
- **`error`**
  - P0 不变。App 在"已请求停止"之后收到 `cancelled`，映射为"已停止"（A0-7）。
  - P1（可选，B1-5）：改为 JSON `{category, userMessage, error_type}`，按 `ProviderError.status_code` 映射类别，**不带原文**。

**`POST /chat/permission`**
- 请求：`{request_id, decision:{behavior:"allow"|"deny", scope:"once"|"session"|"always", message?}}`。`scope` 缺省为 `once`；`always` 在 P1 支持。
- 响应一律 HTTP 200：
  - 成功：`{ok:true, request_id, behavior, scope, session_id, remembered_pattern}`；
  - 失败：`{ok:false, request_id, status:"expired"|"resolved"}`。
- 请求格式错误时返回 422。

**`POST /chat/abort`**
- 请求：`{session_id, source_request_id}`。
- 响应：成功 200 `{ok, session_id, source_request_id, turn_id, state}`；找不到返回 404。

**`GET /workspace`**：返回 `{workspace, trusted_dirs: []}`。

**`PUT /workspace`**：与当前工作区相同返回 200，否则返回 409 `workspace_change_requires_restart`。

**`POST /chat/session-permission-profile`**（P1）
- 请求：`{session_id, permission_profile}`。
- 响应：`{ok, session_id, permission_profile, active, auto_approved_requests}`。

**`/health`（v2）的 `contracts`** 只保留 `desktop_chat` 一项：

```json
{"request_schema_version": 2, "sse_schema_version": 2, "interrupt_schema_version": 1,
 "authoritative_ingress": true, "durable_ingress_idempotency": false,
 "source_request_id_required": true, "attachments_supported": false,
 "max_sse_frame_bytes": 4194304, "oversize_event_projection": true,
 "terminal_error_type_preserved": true, "gap_notice": true}
```

### 4.3 回传通道与 Desktop 交互状态

新增 `DesktopInteractions`（暂名），每个 `create_desktop_app` 一个实例。它只保存进程内的状态，且都有上限。

| 状态 | 键 → 值 | 上限与清理 |
|---|---|---|
| 待决请求缓存 | `request_id → (session_id, ApprovalRequest)` | 结算后移除；只淘汰已经结算的条目 |
| 会话授权 | `{(session_id, tool_name)}` | 进程生命周期内有效，不落盘，与 CLI 的 `s` 同义（`_repl.py:1743-1761`） |
| 请求映射 | `(session_id, source_request_id) → turn_id` | 上限为 `max_sessions`；只淘汰已终止的回合 |
| 会话权限档（P1） | `session_id → default\|full_access` | 由请求体与路由两处写入（Q7 = a；前提是 Q4 = a，已成立） |

**SSE 体处理 `APPROVAL_REQUIRED` 的规则**
- `ask_every_time` 为真：发卡片。
- 否则，如果该会话已授权这个工具，或者处于 `full_access`：直接 `settle(...True)`，不发卡片。
- 否则：写入缓存；只有请求仍待决时才发卡片。

**局限**：自动放行需要有观察者在场。这里**不**引入后台常驻观察者，原因见 0031 陷阱 9。

**`/chat/permission` 的处理顺序**
1. 用 `#` 切出 `turn_id`。
2. 取不到 handle，或 handle 已完成 → `expired`。
3. 请求不在待决列表里 → `resolved`。
4. 按 `scope` 处理：
   - `once`：只结算这一条；
   - `session`：写入会话授权，并连带结算同会话、同工具下其他不是 `ask_every_time` 的请求；
   - `always`（P1）：如果 `can_remember_approval` 为真，调用 `remember_approval`；否则降级为 `once`。
5. 拒绝时，缺省理由为 `"denied in the desktop app"`。
6. `settle` 返回 False → `resolved`。

**`/chat/abort`**：用请求映射找到 `turn_id`，然后 `cancel()`。这个调用是幂等的。

**取消与停止的竞态**：后端的 `cancelled` 帧可能比 interrupt 的响应先到达（`stream-session-manager.ts:1045`）。App 应先记下"已请求停止"，再把随后的 `cancelled` 映射成 `stopped`。

**空闲与超时**
- `keep_alive` 每 25 s 发一次。
- 工具超时在等待审批期间暂停计时（`tools/context.py:495-507`）。
- `approval_timeout_s` 保持 None（V3）。

**全权限（P1）**：语义与 auto-approve 相同，`ask_every_time` 的请求照样询问（V4）。切换时，释放当前正在等待的请求。

### 4.4 安全机制逐条算账（Q3 = a、Q4 = a，已裁定）

前提：单人、本机、default 权限模式。远程只经 SSH 隧道或直连，并带 bearer。

| # | 机制 | 防什么 | 旁路 | 代价与收益 | 裁定 |
|---|---|---|---|---|---|
| S1 | 审批 HMAC 令牌 | 看不到帧的一方猜 id | `request_id` 带 128 位随机量；看得到帧的一方同时也看得到令牌；回环上的进程本来就能驱动 agent | 收益约为零；旧令牌的 5 分钟自动拒绝随之消失（V3） | **不做** |
| S2 | 后端检查 epoch 请求头 | 回答被送到重启后的进程 | id 都在内存里且随机，重启后自然返回 expired 或 404 | 收益为零 | 后端**不做**；App 侧已有的 epoch 绑定保留 |
| S3a | 后端写路由要求 `Content-Type: application/json` | 任意网页借浏览器对 8765 端口发 `text/plain` 简单请求。后端接受任意 `session_id`，攻击者不用猜任何 id，就能驱动自动放行的工具；会话处于全权限或 auto-approve 时可以跑 `bash`。修好 H1 的同时，这条路就通了 | 跨源发 JSON 必须先过预检，而后端没有 CORS，预检失败。同用户的本机进程本来就有全部权限 | 约 5 行代码加测试；这条路径是后端独有的 | **做**，并且与修 H1 绑在一起（B0-1） |
| S3b | 后端 Host 白名单 | 对 8765 端口的 DNS 重绑定 | App 的 Next 层同样可以被重绑定：没有 `middleware.ts`，`next.config.mjs:10` 的 `allowedDevOrigins` 不覆盖 API 路由；而且攻击者在 Next 层能做的更多 | 约 15 行，单独做收益有限 | **不采纳**；DNS 重绑定作为已接受风险记录 |
| S3c | Next 中间件：Host 白名单，加 API 路由只收 JSON | 同上，针对 Next 层 | 必须与 S3b 一起做才完整 | App 侧约 20 行 | **不采纳**（记录在案）。App 的 Next API 自身的简单请求 CSRF 也是既有风险，一并记录 |
| S4 | 远程 bearer | 网络上的其他人、共享服务器上的其他用户 | 无 | 已实现 | 保留 |
| S5 | 本机每次启动随机生成 bearer | 多用户主机上的其他操作系统用户 | 同一用户的进程 | 单人机器上收益为零 | 本期不做，作为候选 |
| S6 | fd-3 令牌 | 已删除的路由 | — | — | 在后续计划 M 中退役 |
| S7 | App 主进程对全权限的确认 | 渲染器脚本偷偷升级权限 | 回环进程；网页已被 S3a 挡住 | 已实现 | 保留；后端不另加校验 |
| S8 | 帧里的凭据遮蔽 | 名字像凭据的键 | `arguments` 是字符串，不会被遮蔽 | — | App 在展示时遮蔽（P1） |
| S9 | `PUT /providers` | 攻击者改掉 `LLM_BASE_URL`，密钥就会被发往别处 | 受 S3a 保护；本机进程本来就能改 `.env` | 可以接受 | 属于后续计划 M，按 Q6 = a 实施；非 `custom` 预设禁止修改 `base_url` 是可选加固，由计划 M 的作者决定 |

### 4.5 启动与连接

**启动命令**
- 形式：`<python> -m omicsclaw desktop --host 127.0.0.1 --port <port>`。
- 用 `python -m` 是为了让 `sys.executable` 与用户所选的解释器一致，否则身份比对会失败（`local-runtime-activation.ts:534-565`）。
- 新增 `buildBackendLaunchArgs`。
- 删除 `OMICSCLAW_BACKEND_MODULE` 覆盖和 `getOmicsClawBackendLaunchCommand`。
- `OMICSCLAW_BACKEND_CLI` 的缺省值改为 `oc desktop`；这个变量是否整个删掉，由实施者决定，并在 PR 说明里写明。

**子进程环境**

| 变量 | 处置 |
|---|---|
| `OMICSCLAW_DESKTOP_LAUNCH_ID`、`OMICSCLAW_DIR`、`PYTHONPATH`、`PYTHONUNBUFFERED` | 保留 |
| `OMICSCLAW_WORKSPACE` | **新增**，取值规则见下面的"工作区的权威来源" |
| `OMICSCLAW_SKILLS_DIR` | **新增**。仅当 `omicsclawDir` 是源码检出、且与工作区不是同一目录时，设为 `<omicsclawDir>/skills`（0063 F22 的 M2 情形） |
| `OMICSCLAW_APP_HOST/PORT`、`OMICSCLAW_DESKTOP_USER_ID` | 删除 |
| fd 3 | 不动（E2） |

**工作区的权威来源**

| 模式 | 权威 | 细节 |
|---|---|---|
| Electron 托管的本机模式 | App 设置里的 `default_project_dir` | • `main.ts` 通过**只读**路径读取它，不加进 `ALLOWED_KEYS`，因为那张表同时也是写入白名单（`settings/app/route.ts:14-37, 65, 116`）。<br>• 为空时，先 `mkdir` 一个 App 自有的空占位目录（如 `<userData>/no-project`）再启动后端。**不回落到 cwd。** |
| `npm run dev` 的本机模式（没有 Electron） | 同样是 `default_project_dir` | App 无法重启后端，开发者要自己用 `--workspace <default_project_dir>` 启动后端。两边不一致时，设置页通过一致性检查提示"后端工作区与所选项目不一致，请用 `--workspace` 重启"，发送时后端返回 409 |
| 远程模式 | 远端后端的 `GET /workspace` | 见后续计划 R |

**本机模式下读取工作区的 App 路由，一律改读 `default_project_dir`，为空即视为"未选项目"。**
- 涉及：`/api/setup` 的 `defaultProject`（现为 `:86-98`）、`/api/workspace/session`（`:24-26`）、`/api/settings/workspace`、`/api/workspace/summary`、`/api/workspace/quick-actions`。
- `GET /workspace` 只用来做一致性检查，并且**不再回写**（`backend-workspace.ts:47-56`）。否则占位目录会被当成真实项目（陷阱 32）。

**`/api/chat` 的服务端闸门**
- 本机模式下，如果 `default_project_dir` 为空，返回 409 `project_required`（en/zh 文案）。
- 这道闸门不依赖前端 `chat/page.tsx:450` 的 `!workingDir` 检查。那个检查挡不住占位目录：占位目录真实存在，`validateDir` 会通过。

**预检**（`python-preflight.ts`）
1. Python 版本在 3.11–3.13 之间。
2. 能 `import omicsclaw`。
3. `'desktop' in omicsclaw.launch.COMMANDS`。否则报 `DESKTOP_SERVER_NOT_FOUND`，文案为"这个环境里的 OmicsClaw 过旧，没有 `oc desktop`，请更新到当前源码"，**不写版本号**。
4. `import omicsclaw.entry.desktop.server` 不需要 fastapi。钉住这一点的测试有两条：
   - `tests/entry/test_desktop_wire_contract.py:425`；
   - `tests/entry/test_entry_is_the_top_layer.py::test_every_entry_module_imports_with_no_vendor_sdk_installed`（约 `:296-329`）。
5. 用 `find_spec` 检查 fastapi 和 uvicorn。缺失时报新错误码 `DESKTOP_DEPENDENCIES_MISSING`，提示改用 conda 安装（en/zh）。

**Electron liveness**
- 同步的 `FunctionTool`（`tools/function_tool.py:197`）会占住事件循环，可能导致 liveness 探测失败，后端就被杀掉。
- 纳入 P0 的 Electron 验收：跑一次长时间分析，确认不会被误杀。
- P1 可选：改为连续 N 次失败才判定（A1-8）。

### 4.6 工作区与 provider/model（Q5 = a、Q6 = a，已裁定）

**工作区**
- 一个进程只服务一个工作区，409 保护保留。
- **P0 的最小切换流程**（A0-2b）：在 `project-switch.ts` 里写一个共用助手 `switchProject(dir)`，四个入口都改为调用它：
  - 向导（`useProjectSetup.ts:35`）
  - 新建会话的目录选择（`chat/page.tsx:301`）
  - 侧栏（`ChatListPanel.tsx:300`）
  - 设置页（`OmicsClawSection.tsx:231`）
- 本机模式下，`switchProject` 的步骤：
  1. 有流在跑时先请用户确认，因为重启会取消所有进行中的回合；
  2. 调用 `PUT /api/setup`：校验目录存在，写入设置，返回 `restart_required: true`；
  3. Electron 下调用 `window.electronAPI.omicsclaw.restart()`（`main.ts:1869-1875`）；
  4. 等待 `/health` 通过；
  5. 发出 `project-directory-changed`。
- `npm run dev` 下，第 3 步改为提示用户手动重启后端。
- 同时**删除**打开会话就自动同步的两处调用：`chat/[id]/page.tsx:60`、`SplitColumn.tsx:136`。原来的 `syncBackendWorkspace` 由 `switchProject` 取代。
- P1：工作区与后端不一致的会话，禁用输入框，并提供"切换到此项目"。
- 轮询**不会**自动启动本机后端（`main.ts:984-1008`）。这与 ADR-0004"切换要重启"的取舍是**类比**关系，不是它的直接适用。
- V2：长期记忆、权限规则、MCP 配置都跟着工作区走。

**provider/model**
- `.env` 仍是唯一的凭据存放处。
- P0/P1：隐藏按会话选模型，Providers 页改为只读并说明配置方法。
- 写入路径（`PUT /providers`、S9）在后续计划 M 里做。
- 陷阱 13：已导出的环境变量优先于 `.env`。

### 4.7 删除与退役（Q8 = a、Q9，已裁定）

- 本计划只做 **A0-12**（隐藏全权限开关，P1 恢复）、**A1-6**（斜杠命令）、**A0-8**（去掉自动压缩）这几处与核心闭环直接相关的删改。
- 其余删除全部放到后续计划 M（§5.5）。
- 数据库表保留、不做迁移，这一点写进 App 的 `PROJECT_MEMORY`（A0-11）。

### 4.8 （原 §4.8 删除清单已并入 §5.5 的后续计划 M）

### 4.9 后端新代码放在哪

**演变**
- 第 3 版时，owner 裁定 Q2 = d：由 0057 从冻结范围里排除 `entry/desktop/**`，并把"已签字的冻结不再覆盖该目录"定为后端 P0 的前置条件。
- 第 3.1 版时，owner 撤销了 0057 的全部冻结检查（§2.5）。排除这一步因此不再需要，前置条件也随之取消。
- 裁定本身保留在 §8，作为历史记录。

**现在的规则：留出集运行期间的软约束**
- **原因**：0057 的留出集（T12）正在运行。每个单元都新起进程，重新导入 `omicsclaw.entry` 的共享部分、`ensemble`、`provider` 与空间 skill 的代码（§2.5）。这时候改动这些路径，后面的单元就会测到另一版代码，而且没人会察觉。这是一个会悄悄污染实验的风险，不是冻结检查。
- **运行期间，0064 的后端改动只落在以下路径**：
  - `omicsclaw/entry/desktop/**`（0057 不导入）；
  - `omicsclaw/launch/**`、`tests/**`；
  - 文档（包括 `OMICSCLAW.md`；A3 用空文件钉住了前置段，不受影响）。
- **P3 删除的路径不受限。** `omicsclaw/surfaces/**`、`omicsclaw/remote/**`、`scripts/**`、`.github/**` 与 `pyproject.toml` 的 extras，都没有被 0057 导入。
- **只改到版本号就停。** `pyproject.toml` 的版本号与 `version.py` 按 §4.1 放到统一提交里。
- **这条约束随留出集结束而失效**，之后不再有额外的审批闸门。
- **与设计偏好的区别**：本计划"只用 `entry` 的公开 API"是设计上的偏好，与留出集无关，一直有效。具体做法是：投影只改 `turn_observation.py`；交互状态放在 `entry/desktop` 的新模块里；其余只调用 `registry.handle`、`approvals.settle/pending`、`cancel`、`compact`、`remember_approval`、`can_remember_approval`，以及 `provider.config.resolve_config` 的只读调用。按这个设计，P0/P1 本来就不需要改共享模块。

**硬要求（与 0057 无关）**
- **任何时候都不能存在"已经修好 422、却不要求 JSON"的可运行后端**（S3a）。B0-1 与 B0-2 必须一起落地。

**阶段排序**
- App P0、后端 P0、后端 P3 都可以立即开始，前提是遵守上面的软约束。
- 共享文件 `entry/config.py:416` 的 docstring 放到留出集结束后再改（C3-4）。
- 提交时机按 owner 的仓库提交策略执行（§2.5），不属于本计划的约束。

### 4.10 旧代码清理（P3）

| 对象 | 处置 |
|---|---|
| `omicsclaw/surfaces/`（desktop 下 21 个 py 文件，另加 `__init__`）、`omicsclaw/remote/` | 删除，约 20,337 行 |
| 22 个根目录旧测试 | 删除：`test_chat_abort_cancel_event`、`test_desktop_chat_*` ×4、`test_desktop_skill_log_bridge`、`test_notebook_*` ×4、`test_outbox_executor`、`test_outputs_session_link`、`test_remote_*` ×8、`test_server_skill_detail`、`test_skill_promotion_sidechannel` |
| `tests/entry/test_desktop_stream.py:704-738` | 改为断言字面值，**先改测试再删旧文件** |
| `tests/entry/test_render.py:435-467` | 改为指向 `entry.desktop._chat_sse` |
| `launch/_surfaces.py:354` 的 docstring | 删除旧代码后会成为悬空引用，一并改 |
| `entry/config.py:416` 的 docstring | 这是 0057 会导入的共享文件，**等留出集结束后**再改（§4.9 的软约束） |
| npm 构建链（Q10 = a） | 删除 `scripts/build-backend-runtime.py`、`scripts/tests/test_build_backend_runtime.py`、`.github/workflows/npm-release.yml`，并改写 README 的 npm 一节 |
| `[desktop]` extra | 删除，或改正注释；同步修改 `docs/core-features`、`docs/remote-connection-guide.md` 里的 `.[desktop]` |

### 4.11 实现约定（对实施者有约束力）

- **注释**：docstring 只说明是什么、做什么；理由写进计划或测试的 docstring。
- **后端**：只用 entry 的公开名字；删除 `_retained_handle`（`server.py:173-194`）；fastapi 只在工厂函数里 import。
  - Content-Type 的判断要**精确解析媒体类型**：按 `;` 切开，取第一段去空白、转小写后与 `application/json` 比较。**不能**做子串匹配。缺少这个头时返回 415。
- **App**：
  - 遵循 SPEC，直接改，不加兼容层；文案 en/zh 同步；测试放在 `src/__tests__/`；里程碑写进 `PROJECT_MEMORY`；两条开发路径都要考虑；不 push。
  - 每次提交或更新 PR 之前，运行 `cursor-team-kit:make-pr-easy-to-review`；没有这个技能时，按 `docs/agent-playbooks/` 执行。
- **改动范围**：0057 留出集运行期间，后端改动遵守 §4.9 的软约束。提交时机按 owner 的仓库提交策略执行。
- **文档**：P0 完成时更新后端 README 与 `README_zh-CN`。

---

## 5. 分期与任务

依赖关系：

```
Q1（已定）→ A0-4/5/6、B0-3/5/8
0057 留出集运行期间 → 后端改动只落在 entry/desktop/**、launch/**、tests/**、文档（§4.9 软约束；App 不受影响）
P0 = B0 + A0 → P1
P3：随时可做（删除的路径都不被 0057 导入）
后续计划 M、R 见 §5.5
```

### 5.1 P0 — 核心对话闭环（本机）

**后端**（0057 留出集运行期间，只改 `entry/desktop/**`、`launch/**`、`tests/**` 与文档，见 §4.9 的软约束；按设计本来就不需要改共享模块）

- **B0-1 修 422。**
  - 去掉 `from __future__ import annotations`，或采用等价的改法。
  - `test_desktop_http.py` 在 OmicsClaw 解释器下 8/8 通过。
  - 新增一条 AST 守卫测试（不依赖 fastapi）：在函数体内定义路由的模块，不得启用 future annotations。
  - **B0-1 与 B0-2 不可分**：不能出现"修好了 422、却还没有 JSON 要求"的可运行后端（§4.9 硬要求 2）。
- **B0-2 只收 JSON（Q4 = a）。**
  - 所有写路由都要求 `application/json`，按 §4.11 精确解析媒体类型；否则 415 `unsupported_media_type`，缺少这个头时也是 415。
  - 测试：`text/plain` → 415；没有 Content-Type → 415；`application/json; charset=utf-8` → 通过；`application/jsonx` 或 `text/application/json` → 415。
- **B0-3 v2 投影**（只改 `turn_observation.py`）：
  - 新增 `thinking` 和 `result`；
  - `permission_request` 加字段，只发给待决请求，会话授权时自动放行；
  - `open_chat_stream` 把 `approvals` 和 `DesktopInteractions` 注入进来。
  - 测试写在 `test_desktop_stream.py`，并修改 `:600-617`。
- **B0-4 `DesktopInteractions`**：删除 `_retained_handle`。测试覆盖上限与淘汰规则。
- **B0-5 `/chat/permission`、B0-6 `/chat/abort`。**
  - 逻辑写成纯 async 函数。交错时序（流在跑的同时 POST 审批）用函数级测试覆盖；Starlette 1.0 的 TestClient 会缓冲整个流式响应，做不到这一点（陷阱 30）。
  - TestClient 只用来测非流式的请求形状。
  - 另加一条真实 uvicorn 测试：临时端口，`--workspace` 指向 `tmp_path`，只在 OmicsClaw 解释器下跑。
  - 用例：`once`、`session`、`deny`、`expired`、`resolved`、422；取消后依次收到 `error:"cancelled"` 和 `done`；排队中的回合也能取消；未知回合返回 404；幂等。
- **B0-7 `/workspace`**：同一路径的不同写法返回 200，不同路径返回 409。
- **B0-8 契约 v2。**
  - `wire_contract.py`：两个版本号改为 2；删除 3 份描述符和 5 个常量；按实际情况改写 chat 描述符；更新 `SERVED_PATHS`。
  - `turn_submission.py`：`ingress_schema_version` **必须是 2**，字段缺失也拒绝。去掉现在的缺省值 `document.get(..., 1)`。
  - 更新 `health_payload` 与包的 docstring。
  - 测试：
    - 按 v2 重写 `test_desktop_wire_contract.py`；
    - **把 `test_desktop_ingress.py:198-200` 反转**：现在断言 v2 被拒，改为断言 v1 被拒、字段缺失被拒；
    - `test_desktop_ingress.py` 的 `document()` 辅助函数、`test_desktop_http.py:45, 95-99, 119` 的请求体、`test_desktop_stream.py:290` 的请求体，都补上 `ingress_schema_version: 2`。
- **B0-9 launch。**
  - 改正 `DESKTOP_USAGE` 和补救提示。
  - 修两条假设"没装 fastapi"的 launch 测试，让它们在两个解释器下都不再真的起服务。
  - 不新增 flag。

**App**

- **A0-1 启动。**
  - `backend-contract.ts`：新增 `buildBackendLaunchArgs`；删除模块覆盖与 `getOmicsClawBackendLaunchCommand`。
  - `python-manager.ts:397-399` 带上参数。
  - 从子进程环境里删除 `APP_HOST/PORT` 与 `USER_ID`。
  - 删除 `python/server.py`。
  - 测试：`backend-contract.test.ts`、`python-manager.test.ts`；`python-backend-shim.test.ts` 删除或改写。
- **A0-2 工作区的权威来源**（§4.5）。
  - `main.ts` 只读 `default_project_dir`；占位目录在启动前 `mkdir`；`buildLocalRuntimePlan` 增加 `workspace` 与 `skillsDir` 两个参数。
  - 五个读工作区的路由改为读设置。
  - `/api/chat` 加 `project_required` 闸门。
  - `backend-workspace.ts` 在本机模式下不再回写。
  - 测试：
    - `local-runtime-plan.test.ts` 覆盖四种情况：源码检出、不同目录、同一目录、未设置；
    - `workspace-authority.test.ts`；
    - 新增 `/api/chat` 的 `project_required` 测试，以及 `/api/setup` 在"未选项目"时的快照测试。
- **A0-2b `switchProject` 共用助手**（§4.6）：四个入口统一调用它；删除两处打开会话就同步的调用；`api/setup` 的 PUT 在本机模式下改为"写设置并返回 `restart_required`"；en/zh 文案。测试：助手的确认、重启、`npm run dev` 下的提示三个分支。
- **A0-3 预检**：新错误码；修改 `local-runtime-copy.ts`；测试 `python-preflight.test.ts`、`local-runtime-copy.test.ts`。
- **A0-4 契约门控。**
  - `backend-health.ts` 新增 `incompatible-contract`，不再接受 legacy-v1；`witnessBackendIdentity` 同时检查版本；`chat-ingress/contract.ts` 的版本改为 2；en/zh 文案。
  - 测试：`backend-health`、`health-route`、`remote-wire-shape`、`probe-profile`、`backend-fetch`、`chat-ingress-contract`。
- **A0-5 v2 解析**：`useSSEStream.ts`、`chat-stream-transcript.ts`、`types/index.ts`、参数解析函数；在 `token-usage.ts` 里加上 `cache_write_tokens`。测试：`sse-stream*`、`chat-stream-transcript`、`permission-tool-input-readability`。
- **A0-6 审批链路。**
  - 改 `route.ts:114-148` 的准入：`request_id` 必须匹配 `^[0-9a-f]{32}#[1-9][0-9]{0,8}$`，不再要求令牌。
  - `backend-operation-binding.ts:247-255` 的正则允许 `#`。
  - 同步修改 `chat-permission-capability.ts`、`api/chat/permission/route.ts`、`chat-permission.ts`、`PermissionPrompt.tsx`、`stream-session-manager.ts`。
  - 另外改 `src/app/chat/page.tsx` 的 `:133`、`:374-379`、`:649` 三处。
  - 测试：`chat-permission-route`、`chat-permission`、`chat-route-*`。
- **A0-7 停止**：`cancelled` 映射为 `stopped`。测试：`stream-session-manager`、`chat-interrupt-route`。
- **A0-8 去掉自动压缩**，把 `/compact` 移出菜单。
- **A0-9 附件**：禁用入口，并在本地拦截。
- **A0-10 文案**：SSH 占位串（`en.ts:2807-2809`、`zh.ts:2796-2798`）、`ssh-probe.ts`、tunnel-manager。只改字符串；远程模式的验证放在后续计划 R。
- **A0-11 App 文档**：README、LOCAL_SETUP_GUIDE（中英两份）、DESKTOP_BUILD_GUIDE、`PROJECT_MEMORY`（写明 §2.6、§2.7，以及数据库表未迁移）。
- **A0-12 隐藏全权限开关**，P1 恢复。

**后端文档**：`OMICSCLAW.md:175-177`；README 与 README_zh-CN；`FRAMEWORK-REBUILD.md:1812-1813`；`docs/core-features/surfaces.md` §8、`human-in-the-loop.md:175`。

### 5.2 P1 — 对话完整性

- **B1-1 全权限**：`/chat/session-permission-profile`；请求体里的 `permission_profile` 也会写入（Q7 = a）。切换时释放正在等待的请求。测试：危险命令仍然弹卡片。
- **B1-2 总是允许**：新增 `scope:"always"` 与 `can_remember`。
- **B1-3 `/compact`**：内容恰好是 `/compact` 时调用 `registry.compact`；App 恢复菜单项。
- **B1-4 `/env/doctor` 最小实现**：检查 provider 与模型、技能数（为 0 时警告）、被跳过的技能、失败的 MCP、沙箱、记忆、权限模式、工作区是否可写。需要 bearer。
- **B1-5 错误分类**（可选）。
- **B1-6 解除 `skill_env=install` 的拒绝**，同步修改测试与 README:42。
- **B1-7 有效模型**：用 `resolve_config` 求出，**不读 `provider.model`**。
- **A1-1** `event_omitted` 提示。
- **A1-2 待办面板**：从 `plan_write` 的结果派生，`cancelled` 映射为 `skipped`；新增 ADR-0006；更新 `CONTEXT.md`；删除 `task_update` 的 case。
- **A1-3** "总是允许"按钮、全权限说明文案（en/zh），恢复开关。
- **A1-4** 工作区不一致的会话：禁用输入框，并提供"切换到此项目"（调用 `switchProject`）。
- **A1-5** 模型改为只读展示。
- **A1-6** 斜杠菜单只保留 help、clear、cost、compact；`@` 提及并入 content。
- **A1-7** 后端错误码的 en/zh 文案：`project_required`、`workspace_does_not_match_backend_runtime`、`queue_full`、`shutting_down`、`attachments_not_supported`、`unsupported_media_type`。
- **A1-8（可选）** liveness 改为连续 N 次失败才判定，只在 P0 的 Electron 验收出现误杀时才做。
- **文档**：`OMICSCLAW.md` 的 Desktop 小节。

### 5.3 P3 — 后端旧代码清理（随时可做；只有 C3-4 要等留出集结束）

- **C3-1** 先改 `tests/entry` 里的三处，再删 `surfaces/`、`remote/` 和 22 个旧测试，同时修改 `_surfaces.py:354`。
- **C3-2** 删除 npm 构建链，改写 README 的 npm 一节（Q10 = a）。
- **C3-3** 处理 `[desktop]` extra 及相关文档。
- **C3-4** 留出集结束后再做两件事：
  - 修改共享文件的 docstring（`config.py:416`）；
  - 与 0056–0060 的统一提交一起落地版本号 0.2.0：`omicsclaw/version.py`、`pyproject.toml`、App `package.json` 的 `expectedBackendVersion`（Q1 子项）。
- **C3-5** README 里其余过时的 Desktop 说法。
- **验收**：
  - `git grep -n "surfaces\.desktop\|omicsclaw\.remote\|build-backend-runtime" -- omicsclaw tests scripts .github` 没有结果；
  - `tests/entry` 在 rapids 解释器下通过；
  - desktop 系列测试在 OmicsClaw 解释器下通过。

### 5.4 （原 P2、P4 已移出，见 §5.5）

### 5.5 后续计划（不在本计划内）

按 Q11 = a，拆成两份后续计划。**本计划不创建它们的文件，编号由 owner 分配。**下面列出约束它们的裁定，后来的作者不必重新推导。

**后续计划 M：Desktop 管理页与功能退役**（暂名，原 P2）

- **前置**：0064 的 P0 已落地。有了 v2 契约与只收 JSON 的写路由之后，新增的写路由自动受 S3a 保护。
- **留出集约束**：如果计划 M 在 0057 留出集运行期间实施，§4.9 的软约束同样适用：后端只改 `entry/desktop/**`、`launch/**`、`tests/**` 与文档。计划 R 同理。
- **后端薄路由**（只读为主，只用 entry 的公开 API）：

  | 路由 | 要求 |
  |---|---|
  | `GET /skills`、`GET /skills/{d}/{n}` | 载荷按 App 解析器的要求（`skill-catalog-client.ts:124-198`）：`collection:"curated"`、`status:"ready"`、`primary_data_types:[]`；`skill_md` 取自 `get_full_content`；只给相对路径。注意：`useSlashCommands.ts:102-110` 读的是 `data.skills`，与目录的形状不同，要一并对齐 |
  | `GET /mcp/servers` | 合并配置与 `statuses()`；`env`、`headers` 里的值要遮蔽 |
  | `GET/PUT /providers`、`POST /providers/test`（Q6 = a） | `.env` 为准；写入 `dotenv_target()` 指向的文件，返回 `restart_required`，App 随后触发重启；不回显密钥；需要一个公开的 `.env` 写入函数。现在的实现在 `entry/cli/_configure.py:142, 203`，是私有的。建议把公开版本放在 `launch/**`（`launch/_dotenv.py` 已经负责 `.env` 的定位）；如果在 0057 留出集运行期间实施，也不要改 `entry/cli`（§4.9）。S9：非 `custom` 预设禁止改 `base_url`，这项加固由计划 M 的作者决定。陷阱 13：已导出的环境变量优先于 `.env` |
  | `POST /chat/title`（Q9③） | 请求 `{schema_version:1, source_request_id, user_text}`；响应 `{schema_version:1, title}` 或 `{schema_version:1, error}`；一次有界的 `app.provider.generate`，超时 30 s |

- **App 删除（Q8 = a）**：每个功能单独提交。删除范围包括导航项、页面、API 路由、lib、hooks、组件、只被它们使用的 en/zh 文案键、测试、smoke 与 e2e 用例。数据库表保留。

  | 功能 | 主要路径 |
  |---|---|
  | AutoAgent/Optimize | `src/app/optimize/`、`api/autoagent/**`、`components/optimize/`、`useOptimizeStream.ts`、`lib/autoagent-*.ts`、`instrumentation.ts`、`backend-fetch.ts` 里的 autoagent 分支（25 处） |
  | Bench/Thread/Onboarding | `src/app/bench/`、`api/{thread,onboard,preference/bench}/**`、`components/bench/`、`lib/bench*`、`lib/onboarding/`、`useThread*.ts`，以及请求里的 `thread_id` 与 `stage` |
  | KG | `src/app/kg-explorer/`、`api/kg/**`、`components/kg/`、`useKGStatus.ts` |
  | Notebook | `src/app/notebook/`、`api/notebook/**`、`components/notebook/`、`lib/notebook/`、`backend-contract.ts:47-61`、`docs/NOTEBOOK_FEATURE.md` |
  | 技能治理 | `api/skill-evolution/**` 与对应组件；fd-3 管道（stdio 改回三项）与 `skillEvolutionToken`；`electron/skill-evolution-auth.ts`；`next-server-bootstrap*.ts`（打包模式改为直接 fork `server.js`，**但保留主进程确认密钥的 bootstrap**，即 `main.ts:1236-1241`） |
  | 回放与晋升、市场、OAuth、CLI 设置 | `api/runs/[runId]/replay`、`SkillReplayCard.tsx`、`canonical-run-replay.ts`、`skill-promotion.ts`；`api/skills/marketplace/**`；`api/auth/[provider]/**`；`CliSettingsSection.tsx` |
  | Q9 裁定的去留 | ① **Bridge 删除**：`src/app/bridge/`、`api/bridge/**`、`api/settings/{discord,feishu,qq}`，用户改用 `oc channel`。② **Memory 页隐藏，另立计划**，用 `LongTermStore` 做只读列表、搜索、删除。④ **MCP 写入推迟**，页面标为只读。⑤ **Outputs 面板删除**：`OutputPanel.tsx`、`api/outputs/**`、`run-link.ts`、run_meta 的写入 |
  | 远程死代码 | `remote-datasets-*`、`remote-artifacts-proxy.ts`、`adaptive-env-proxy.ts`、`api/env/{overlays,adaptive-mode}` |
  | 聊天里的死分支 | `useSSEStream.ts` 的 7 个 case 与 `_progress`；`AskUserCard`；`ExitPlanModeUI`、`AskUserQuestionUI`；模式选择器；`/research`、`/run`；`types/index.ts:774-797` |

- **验收**：三个管理页显示真实数据；导航里没有死入口；App 仓库里 `git grep` 查不到被删功能的路由字符串；en/zh 的键集一致。

**后续计划 R：Desktop 远程模式**（暂名，原 P4）

- **前置**：0064 的 P0 与 P1 已完成。其中 B1-4 的 doctor 需要 bearer，这样 App 的远程 bearer 探测才重新有效。
- **内容**：
  - 远程启动串：`oc desktop --workspace <dir> -- --host 127.0.0.1 --port 8765`，并在远端设置 `OMICSCLAW_REMOTE_AUTH_TOKEN`。
  - 远程工作区以远端的 `GET /workspace` 为准，只读，远程模式下禁止切换项目。
  - bearer 探测改为带认证头请求 `GET /health`，401 即判定失败。
  - 删除远程 jobs 面板：`remote-jobs-proxy.ts`、`remote-jobs-adapter.ts`、`remote-sse-adapter.ts`，以及 jobs 路由里的远程分支。
  - **Q9⑥ 远程文件浏览**：`/files/tree` 与 `/files/serve` 只读，用 realpath 限定在工作区之内，需要 bearer。
- **验收**：在本机用 `OMICSCLAW_REMOTE_AUTH_TOKEN=t oc desktop --workspace /tmp/r -- --port 18765` 模拟远程，完整走通激活、对话、审批、停止；token 错误时提示明确；连到只支持 v1 的桩后端时，提示版本不兼容。

---

## 6. 测试与验收

### 6.1 后端：解释器与命令

| 用途 | 解释器 | 命令 |
|---|---|---|
| desktop 测试（需要 fastapi） | `/opt/conda/envs/OmicsClaw/bin/python` | `PYTHONDONTWRITEBYTECODE=1 … -m pytest -q -p no:cacheprovider -p no:randomly tests/entry/test_desktop_http.py tests/entry/test_desktop_stream.py tests/entry/test_desktop_wire_contract.py tests/entry/test_desktop_ingress.py tests/entry/test_render.py`，加上新增的测试 |
| entry 与 launch 的纯 Python 测试 | `/opt/conda/envs/rapids_singlecell/bin/python` | `… -m pytest -q -p no:randomly tests/launch/test_surfaces.py tests/launch/test_launch_is_above_entry.py tests/launch/test_grammar.py tests/entry/test_entry_is_the_top_layer.py`，加上 AST 守卫测试 |

- **B0-9 完成之前，禁止用 OmicsClaw 解释器跑 `tests/launch/`**（附录 B-3）。
- 基线：OmicsClaw 解释器下，`http` 2 passed、6 failed，`wire` 19 passed、1 skipped，`ingress` 37 passed，`stream` 26 passed，`render` 41 passed；rapids 解释器下，`test_surfaces` 128 passed。
- 只跑新增的测试和直接相关的测试。已知与本计划无关的既有失败有三处：`tests/tools/test_workspace.py`、`test_control_plane_documentation_contract.py`、`websafety` 的 drip 用例。

### 6.2 App：命令

1. 先 `npm ci`：`node_modules` 为空，需要联网，由 owner 确认。
2. `npm run typecheck`。
3. 对改动的文件跑 lint。
4. `npm run test`，或只跑相关文件。
5. 界面有改动的阶段，跑 `npm run test:smoke` 并截图。

### 6.3 真机端到端

1. **后端**
   ```bash
   mkdir -p /tmp/oc-e2e-ws && cd /tmp/oc-e2e-ws && \
   OMICSCLAW_DIR=/workspace/dataset/private/zhouwg_data/OmicsClaw \
   OMICSCLAW_SKILLS_DIR=/workspace/dataset/private/zhouwg_data/OmicsClaw/skills \
   /opt/conda/envs/OmicsClaw/bin/python -m omicsclaw desktop --workspace /tmp/oc-e2e-ws -- --port 8765
   ```
   结束后停掉进程，并清理临时目录。
2. **curl**：两个版本号都是 2；`text/plain` 返回 415；缺少 Content-Type 返回 415；入站版本为 1 时返回 422。
3. **浏览器路径**：执行 `npm run dev`。在 App 设置里把项目设为 `/tmp/oc-e2e-ws`。项目未设置时，发送应当返回 `project_required`。
4. **Playwright**
   - 使用独立配置 `playwright.live.config.ts`：只匹配 `live-*.spec.ts`，`workers: 1`，超时 10 分钟，复用已有的 dev 服务器；主配置里用 `testIgnore` 排除它。
   - 用例文件为 `live-backend-chat.spec.ts`，只在 `OMICSCLAW_LIVE_BACKEND=1` 时运行。

   | # | 操作 | 断言 |
   |---|---|---|
   | a | 新建会话，发"只回复 OK" | 文本流式输出；有 `result` 用量；模型支持时能看到 thinking |
   | b | 让它用 bash 执行 `echo hello-0064` | 弹出审批卡片，参数逐字段展示；点"允许一次"后，工具卡显示 `hello-0064` |
   | c | 再来一次 bash，点"拒绝" | 模型的回复里能看出被拒 |
   | d | 点"本会话允许"，然后连续两次 bash | 第二次不再弹卡片 |
   | e | `sleep 120` 时点停止 | 2 秒内终止，界面显示"已停止"，而不是"Error: cancelled" |
   | f | 刷新页面 | 转录已持久化 |
   | g | 让它写一份计划 | 待办面板出现（P1 起） |
   | h | 切换到另一个项目目录 | 浏览器路径下：先得到"请手动重启后端"的提示，按提示用新的 `--workspace` 重启后端后，能继续对话；旧项目的会话发送时给出明确的 409 提示 |

5. **Electron 路径**（`npm run electron:dev`；本环境没有显示器，在 owner 的机器上做，或者用 xvfb）：
   - 预检通过，`launch_id` 匹配，身份比对通过；
   - doctor：P0 预期为 `needs-attention`，原因写明"doctor 不可用"；P1 起应为 `running`，或只剩真实存在的警告；
   - 首次启动（未选项目）时，后端运行在占位目录，界面禁止聊天，`/api/chat` 返回 `project_required`；
   - 依次重复 a–f 与 h。Electron 下的 h 应当由 `switchProject` 自动重启到新工作区；
   - 跑一次 ≥10 分钟的真实分析，确认 liveness 没有误杀后端。

### 6.4 各期验收标准

- **P0**
  - H1–H11 中属于 P0 的部分全部消除；
  - desktop 测试在 OmicsClaw 解释器下全部通过；launch 测试在两个解释器下都不挂住；
  - App 的 typecheck、lint（改动文件）、unit 全绿；
  - §6.3 的浏览器段 a–f、h 通过，Electron 段完整通过（含 a–f、h、首次启动与长分析），截图存档；
  - §2.7 列出的旧页面都不影响核心闭环；
  - 文档已更新。
- **P1**
  - 全权限下，普通 bash 不弹卡片，危险命令仍弹；
  - "总是允许"生效；
  - `/compact` 有提示；
  - Electron 不再停在 `needs-attention`；
  - 工作区不一致的会话，输入框被禁用；
  - g 步通过。
- **P3**：见 §5.3。

---

## 7. 陷阱与风险

1. **只在一个解释器里看得见的缺陷**：desktop 的 HTTP 测试只在 OmicsClaw 解释器下运行。
2. **留出集运行期间静默污染实验**：0057 的每个单元都新起进程，重新导入 `entry` 的共享部分、`ensemble`、`provider` 与空间 skill 的代码。这时候改动这些路径，后面的单元会测到另一版代码。**现在没有任何检查会拦住它**，冻结检查已经撤销；`run_holdout.py` 只为记录计算一份代码摘要，不做拦截。
3. **0057 的冻结检查已撤销**（第 3.1 版事实更新）：第 3 版里的签字前置条件，以及"不提交、不装包、不重装"的规则都已取消。剩下的只有 §4.9 的软约束（运行期间，后端只改 `entry/desktop/**`、`launch/**`、`tests/**` 与文档），它在留出集结束后失效。
4. **自动压缩**：`result` 一旦带上用量，App 的自动压缩就会被重新激活，所以 A0-8 必须与 B0-3 同期。
5. **压缩的 `status` 帧带 `session_id`**：App 必须先判断 `kind`。
6. **绑定正则不接受 `#`。**
7. **没有双栈过渡**：两边要一起升级。入站 v2 加 `/health` 门控，保证错配时两个方向都显式报错。
8. **`result.usage` 是求和语义**，这是旧后端就有的语义。
9. **自动放行需要观察者在场。**
10. **只收 JSON 不能误伤 App**：逐个核对 App 所有 POST 请求的 Content-Type，并精确解析媒体类型。
11. **切换项目会重启后端**：会取消所有正在进行的回合，必须先确认；四个入口统一走 `switchProject`，删除打开会话就同步的调用。
12. **M2/M3 情形**：`skills_count == 0` 就是信号。
13. **已导出的环境变量优先于 `.env`。**
14. **删除 fd 3 时**（计划 M）：stdio 要改回三项；主进程确认密钥的 bootstrap 保留。
15. **包版本号在 P0/P1 期间不变**，兼容性只看契约版本。0.2.0 要等留出集结束后，随统一提交一起落地（C3-4），这样后端版本号与 App 的 `expectedBackendVersion` 能一起发布。
16. **审批不设期限**，所以停止功能是硬性要求。
17. **工具超时不再终止回合。**
18. **断开即取消**（30 s 宽限）。
19. **描述符不得超额声明。**
20. **App 验证需要 `npm ci`，Electron 验证需要显示器。**
21. **App 本地的 `/clear`、rewind、删除不同步给后端**，这是既有差异。
22. **同一端口上的两个后端**：会报 launch_id 不匹配。
23. **`.env` 里设了 `OMICSCLAW_SKILL_ENV=install`**，在 B1-6 之前会导致拒绝启动。
24. **MCP 配置改动后需要重启。**
25. **删除旧代码的顺序**：先改测试，再删文件。
26. **远程 bearer 探测**：未知路由先返回 404 而不是 401，所以在 B1-4 或计划 R 之前，这个探测无效。
27. **`arguments` 不经遮蔽**，并会被 App 持久化。
28. **测试的副作用**：必须显式传 `--workspace`（附录 B-3）。
29. **Electron liveness 误杀**（§4.5）。
30. **TestClient 会缓冲流式响应**（B0-5/6）。
31. **取消与停止的竞态**（A0-7）。
32. **占位目录回写**：`GET /workspace` 的结果如果写回 `default_project_dir`，占位目录就会被当成真实项目；前端的 `!workingDir` 检查也挡不住它，所以需要 `/api/chat` 的服务端闸门（§4.5）。
33. **P0/P1 期间旧页面的错误状态**（§2.7）：对用户可见，但不影响核心功能。要在 `PROJECT_MEMORY` 里说明，避免被误报成回归。

---

## 8. 裁定记录（owner，2026-09-27）

各问题的选项与论证见第 2 版的 §8（git 历史与审核记录中可查），这里只列选项的要点。

| # | 问题 | 选项要点 | 裁定 |
|---|---|---|---|
| Q1 | 契约的所有权与 v2 形状 | a 由后端定义（`to_wire` 字段，`sse` 与入站同升 v2，App 两处门控）；b 投影回 v1；c 重新设计 | **a**（2026-09-27）。子项"包版本升到 0.2.0"：**是**。放在留出集结束后的统一提交里，与 App 的 `expectedBackendVersion` 一起发布（C3-4） |
| Q2 | 后端代码放在哪 | a 在签字前完成并重新生成草稿；b 放到 `entry/**` 之外；c 等留出集结束；d 缩小冻结范围 | **d**（2026-09-27）：0057 把 `entry/desktop/**` 排除出冻结范围，作为后端 P0 的前置条件。**第 3.1 版更新（同日）**：owner 撤销了 0057 的全部冻结检查，排除这一步已不再需要，前置条件取消；裁定保留作为历史记录。现行规则是 §4.9 的软约束：留出集运行期间，后端只改 `entry/desktop/**`、`launch/**`、`tests/**` 与文档，留出集结束后失效 |
| Q3 | 审批令牌与后端 epoch 围栏 | a 都不做；b 随机令牌；c HMAC | **a**（2026-09-27）。旧的 5 分钟自动拒绝随之消失（V3） |
| Q4 | 本机访问防护 | a 后端只收 JSON；b a 加后端 Host 白名单；c b 加 Next 中间件；d 不做 | **a**（2026-09-27）。DNS 重绑定（后端与 Next 两层）以及 Next API 自身的简单请求 CSRF，作为已接受风险记录在案；b、c 未采纳 |
| Q5 | 工作区模型 | a App 拥有工作区，未选项目时用占位目录并禁止聊天，显式重启，P0 就做最小切换；a′ 拒绝启动并调整向导顺序；b 多工作区；c 自动切换；d 固定一个 | **a**（2026-09-27） |
| Q6 | provider/model | a 以 `.env` 为准，由后端写入（计划 M 实施）；a′ 由 Electron 直接写；b App 存密钥；c 只读 | **a**（2026-09-27） |
| Q7 | 全权限与"总是允许" | a 按会话自动放行，请求体与路由两处都可写；a′ 只认路由；b 进程级；c 取消 | **a**（2026-09-27）。因为 Q4 = a（≠ d），从请求体读取成立 |
| Q8 | 退役方式 | a 删除代码，数据库表保留；b 只隐藏 | **a**（2026-09-27）。在 App 的 `PROJECT_MEMORY` 里记录（A0-11） |
| Q9 | 管理类功能的去留 | 见右列 | ① Bridge 删除；② Memory 页隐藏，另立计划；③ 标题做薄路由；④ MCP 写入推迟；⑤ Outputs 面板删除；⑥ 远程文件浏览只读、限定在工作区内、需要 bearer（2026-09-27） |
| Q10 | 孤立的 npm 构建链 | a 删除；b 恢复 | **a**（2026-09-27）。放在 P3（C3-2） |
| Q11 | 是否拆分范围 | a 拆出 P2 与 P4；b 保持一份计划 | **a**（2026-09-27）。0064 保留 P0、P1、P3；后续计划 M、R 的约束见 §5.5 |

---

## 9. 与其他计划的关系

| 计划或 ADR | 关系 |
|---|---|
| **0031** | 收口 §11 的债 8，以及 FRAMEWORK-REBUILD 里的两条 Desktop 债；按 Q1 = a 改写 Q24 的所有权规则；R1 的教训落实在 B1-7 |
| **0037** | 核实了"`/health` 未核实"这一项：确实不通，由 B0-1 修复。不加 `__main__`，也不给 `desktop-server` 起别名 |
| **0052** | desk 尚未实现；`DesktopInteractions` 只服务 Desktop。0052 的 T3 落地时，评估两者是否合并 |
| **0054** | Desktop 继续关闭 `ask_user`。将来如果开放 Desktop 的问答，按本计划的方式新增帧和路由，并把 `sse_schema_version` 再加 1 |
| **0057** | 冻结检查已由 owner 撤销（第 3.1 版），Q2 = d 的排除步骤不再需要。本计划不修改 0057 的任何文件。留出集（T12）运行期间，后端改动遵守 §4.9 的软约束，避开 0057 会导入的路径 |
| **0063** | F22 收口；Known gap 改写 |
| **App ADR-0001** | 由 ADR-0006 部分取代（A1-2） |
| **App ADR-0004** | 作为类比：切换要重启 |
| **App ADR-0005** | 展示方式不变 |
| **后续计划 M、R** | 由 Q11 = a 拆出，其约束见 §5.5 |

---

## 附录 A：证据索引（行号以 2026-09-27 为准）

**后端**

| 文件 | 行号与内容 |
|---|---|
| `entry/desktop/server.py` | `:29`；`:70-77`；`:105-170`；`:135-144`；`:173-194`；`:197-250`；`:275-397`；`:296-297`；`:301-308`；`:310-356` |
| `entry/desktop/turn_observation.py` | `:82`；`:91-159`；`:178-239`；`:242-263`；`:251-255`；`:266-392` |
| `entry/desktop/turn_submission.py` | `:211-217`；`:279-339`；`:309-311`（缺省为 1）；`:331` |
| `entry/desktop/wire_contract.py` | `:1-6`；`:48-55`；`:58`；`:68-90` |
| `entry/render.py` | `:141-147`；`:430-451`；`:462-472`；`:515-532`；`:535-552`；`:593-607` |
| `entry/approval.py` | `:67-81`；`:141`；`:187-202`；`:235-237` |
| `entry/turn.py` | `:721`；`:790`；`:860` |
| `entry/session.py` | `:91`；`:395`；`:502`；`:516`；`:529`；`:849-871` |
| `entry/assembly.py` | `:995`；`:1030`；`:1054` |
| `entry/config.py` | `:226`；`:403`；`:416`；`:582-590`；`:620-622` |
| `entry/cli/_repl.py` | `:1743-1793` |
| `entry/cli/_configure.py` | `:142`、`:203` |
| `entry/channel/runtime.py` | `:467-482` |
| `launch/_surfaces.py` | `:287-302`；`:354`；`:1009-1011`；`:1069-1186`；`:1167` |
| `tools/function_tool.py` | `:197` |
| `tools/context.py` | `:495-507` |
| `version.py` | `:7` |
| `docs/plans/0057-validation/` | 第 3.1 版现状：没有 `freeze.py` 与 `freeze.json`；`run_holdout.py:37-41` 只为记录计算代码摘要；对 entry 的导入为 `run_arms.py:223`（`open_app`）、`:298`（`entry.config`）、`:377`（`entry.turn` 的内部函数），以及 `common.py:112`。第 3 版时的冻结文件行号已随撤销失效 |
| 测试 | `test_pyproject_thin_pip_layer.py:49-50`；`tests/entry/test_desktop_ingress.py:198-200`；`test_desktop_http.py:45, 95-99, 119`；`test_desktop_stream.py:290, 600-617, 704-738`；`test_render.py:435-467, 475-499`；`test_desktop_wire_contract.py:425`；`test_entry_is_the_top_layer.py::test_every_entry_module_imports_with_no_vendor_sdk_installed`（约 `:296-329`）；`tests/launch/test_surfaces.py:192`；`test_launch_is_above_entry.py:597-613` |
| 文档 | `OMICSCLAW.md:175-177`；`docs/FRAMEWORK-REBUILD.md:1812-1813` |

**App**

| 文件 | 行号与内容 |
|---|---|
| `src/lib/backend-contract.ts` | `:17-61` |
| `electron/python-manager.ts` | `:27`；`:229-251`（`:241` 为 `desktop_user`）；`:397-416`；`:516-547`；`:926-1006` |
| `electron/python-preflight.ts` | `:21-84` |
| `electron/local-runtime-plan.ts` | `:104` |
| `electron/main.ts` | `:984-1008`；`:1010-1070`；`:1236-1241`；`:1549-1551`；`:1869-1875` |
| `electron/local-runtime-activation.ts` | `:534-565`；`:584-599` |
| `src/lib/backend-health.ts` | `:199-315` |
| `src/lib/backend-fetch.ts` | `:757-826` |
| `src/lib/backend-workspace.ts` | `:47-56` |
| `src/lib/backend-operation-binding.ts` | `:247-255` |
| `src/lib/token-usage.ts` | `:46-62` |
| `src/lib/chat-ingress/contract.ts` | `:9`、`:83` |
| `src/lib/autoagent-receipt-cancellation.ts` | `:91-94`、`:155-160` |
| `src/app/api/chat/route.ts` | `:114-148`；`:599`；`:665-695` |
| `src/app/api/setup/route.ts` | `:86-98`；`:216`；`:235-241` |
| `src/app/api/workspace/session/route.ts` | `:24-26` |
| `src/app/api/internal/runtime-activation/route.ts` | `:76` |
| `src/app/api/settings/app/route.ts` | `:14-37`；`:65`；`:116` |
| `src/app/api/skills/route.ts` | 整个文件 |
| `src/app/api/notebook/proxy.ts` | 返回 502 `backend_missing_notebook_routes` |
| `src/app/chat/page.tsx` | `:133`；`:218-262`；`:301-307`；`:374-379`；`:450`；`:649`；`:732-755` |
| 项目写入口 | `useProjectSetup.ts:35`；`OmicsClawSection.tsx:231`；`ChatListPanel.tsx:300`；`project-switch.ts` |
| 自动同步 | `chat/[id]/page.tsx:60`；`SplitColumn.tsx:136` |
| `src/hooks/useSSEStream.ts` | `:258-268`、`:300-310` |
| `src/hooks/useSlashCommands.ts` | `:102-110` |
| `src/lib/stream-session-manager.ts` | `:1045` |
| `src/components/chat/PermissionPrompt.tsx` | `:436-441` |
| `src/app/bench/page.tsx` | `:24-30` |
| `next.config.mjs` | `:10`（不存在 `middleware.ts`） |
| `docs/PROJECT_MEMORY.md` | `:81`；`:119`；`:121` |

## 附录 B：本次核查的运行记录

**B-1 探测真实的 `oc desktop`**
- 端口 18765，工作区为临时目录。
- `GET /health`、`HEAD /health`、`POST /chat/stream` 都返回 422，错误位置为 `["query","request"]`。
- 环境：fastapi 0.136.1、starlette 1.0.0、uvicorn 0.46.0。
- 已清理。

**B-2 `test_desktop_http.py`**：OmicsClaw 解释器下 6 failed、2 passed；rapids 解释器下收集到 0 条。

**B-3 launch 测试挂住**
- 在 OmicsClaw 解释器下，`test_surfaces.py` 运行超过 120 s；单独跑 `-k token_comes_from` 时 25 s 超时。
- 有一次以仓库根目录为 cwd 运行，重写了被 gitignore 的 `.omicsclaw/MEMORY.md`（内容为空）。只读确认过：内容没有变化；那次曾在 `0.0.0.0:8765` 上短暂监听，已随超时终止。
- rapids 解释器下 128 passed。

**B-4 其余基线**：`wire` 19 passed、1 skipped；`ingress` 37 passed；`stream` 26 passed；`render` 41 passed。

**B-5 第 2 版补充的只读核实**（关于环境锁与 HEAD 的那一条已随冻结检查撤销而失效）
- `pip freeze` 里含后端仓库 HEAD 那一行。
- Starlette 的 TestClient 会缓冲整个流式响应。
- App 没有 `middleware.ts`。

**B-6 第 3 版补充的只读核实**（其中关于 `freeze.json` 的内容已随冻结检查撤销而失效，只作历史记录）
- `freeze.json` 存在：`status = draft: awaiting the owner's signature`；`code_digest` 覆盖 181 个文件，其中 `entry/**` 64 个（含 `entry/desktop` 的 6 个）；`environment` 有 5 个键，含 `pip_OmicsClaw.txt`。
- `freeze_appendix.md` 于 10:11:51 UTC 生成。
- 0057 的脚本对 entry 的导入只有 `entry.config`、`open_app`、`entry.turn`。
- 核实了 §2.7 各页面的失败方式：skills 路由的转发与解析抛错、`useSlashCommands` 的优雅降级、notebook 的 502、optimize 的 503、bench 的尽力而为、reconciler 的错误吞没。
- 核实了四个项目写入口，以及五个读工作区的路由。

## 附录 C：审核意见处理记录

### 第 2 版（首轮独立审核）

| 编号 | 处理 | 改动位置 |
|---|---|---|
| M1 环境锁含仓库 HEAD | 采纳 | §2.5、§4.9、§4.11、P3、Q2、陷阱 3、§9 |
| M2 工作区闭环 | 部分采纳：不回落到 cwd；最小切换提前到 P0。"拒绝启动"因为向导顺序改为占位目录（Q5 a′ 记录了另一种做法） | §2.2、§2.6、§4.5、§4.6、A0-2、A0-2b |
| M3 S3 说过了头 | 采纳 | §4.4、Q4 |
| M4 请求体中的 full_access | 采纳 | §4.3、§4.4、B0-1、Q4、Q7 |
| m1 TestClient 缓冲 | 采纳 | B0-5/6、陷阱 30 |
| m2 投影只改 `turn_observation.py` | 采纳 | §4.2、§4.9、B0-3 |
| m3 两个方向都显式失败 | 采纳 | §4.1、B0-8、A0-4 |
| m4 `result` 的键名 | 采纳 | §4.2、A0-5 |
| m5 Electron 纳入 P0 验收 | 采纳 | G1、§6.3、§6.4 |
| m6 取消竞态 | 采纳 | §4.3、A0-7 |
| m7 liveness 误杀 | 采纳 | §4.5、A1-8、陷阱 29 |
| m8 行为变化 | 采纳 | §2.6、A0-12 |
| m9 `PUT /providers` | 采纳 | S9、§5.5 M |
| m10 `ALLOWED_KEYS` 同时是写入白名单 | 采纳 | §4.5、A0-2 |
| m11 篇幅 | 采纳 | 删除原附录 B；增加 Q11 |
| n1–n11 | 采纳；其中 n7 部分采纳（两处引用都给出） | 各处 |

### 第 3 版（复审与 owner 裁定）

| 编号 | 处理 | 改动位置 |
|---|---|---|
| owner 裁定 Q1、Q3–Q11 | 按裁定改写 | 状态行、§0、§8（改为裁定记录） |
| owner 补裁 Q2 = d | 改写 §4.9：写明 0057 一方要做的事、后端 P0 的前置条件与核实方法、允许与禁止的路径、"需要改共享模块就停下来"，以及越界时 `check_freeze` 会报错 | 状态行、§0、§2.5、§4.9、§5、§5.1、陷阱 3、§8、§9 |
| owner 补裁 Q1 子项 0.2.0 = 是 | 放在留出集结束后的统一提交里，同时改 App 的 `expectedBackendVersion` | §0、§4.1、C3-4、陷阱 15、§8 |
| Q11 = a 拆分 | 原 P2、P4 移到 §5.5 的后续计划 M、R，并写全约束它们的裁定；矩阵期次改为 M、R；核对 P0/P1 不依赖移出的内容 | §3、§5.5、§4.7、§4.8 |
| 旧页面的中间态 | 新增 §2.7：逐页列出失败方式，结论是都不影响核心闭环与启动 | §2.7、陷阱 33、§6.4 |
| 新事实：`freeze.json` 草稿已生成 | 更新了"尚未生成"的说法、签字前后的约束，以及 0057 的导入事实 | §2.5、§4.9、陷阱 3、§9、附录 B-6 |

### 第 3.1 版（事实更新）

| 编号 | 处理 | 改动位置 |
|---|---|---|
| owner 撤销 0057 的全部冻结检查（代码指纹、环境锁、签字闸门；`frozen_settings` 只作记录，种子注入保留），留出集 T12 开始运行 | 已核实 `freeze.py` 与 `freeze.json` 都不在了。Q2 = d 保留为历史，排除步骤不再需要；删去后端 P0 的签字前置条件，以及"不提交、不装包、不重装"的规则；改为运行期间的软约束（理由是每个单元都新起进程、重新导入代码），这条约束在留出集结束后失效；"只用公开 API"作为设计偏好保留；0.2.0 的时机不变，理由改为与 App 同时发布；0057 导入处的行号更新为 `run_arms.py:223/298/377` | 状态行、修订说明、§0、§2.5、§4.1、§4.9、§4.10、§4.11、§5、§5.1、§5.3、§5.5、陷阱 2/3/15、§8 的 Q1/Q2、§9、附录 A、B-5、B-6 |
| MINOR：占位目录下的"禁止聊天"没有任务落实 | 采纳：本机模式下五个路由改读 `default_project_dir`；`/api/chat` 增加 `project_required` 闸门；写明 `npm run dev` 下以谁为准；启动前 `mkdir` 占位目录 | §4.5、A0-2、§6.3、陷阱 32 |
| MINOR：侧栏切换没有覆盖到 | 采纳：写一个共用助手 `switchProject`，覆盖四个入口（含设置页 `OmicsClawSection.tsx:231`） | §4.6、A0-2b |
| MINOR：入站 v2 的测试 | 采纳：`test_desktop_ingress.py:198-200` 反转；三处请求体补上字段；字段缺失时拒绝 | B0-8、§4.1 |
| NIT：Q4 的选项 c 没有对应任务 | 按裁定作为"未采纳"记录 | §4.4 S3c、§8 |
| NIT：§6.4 与 §6.3 第 5 步对齐 | 采纳：Electron 段覆盖 a–f 与 h；浏览器下的 h 需要手动重启后端 | §6.3、§6.4 |
| NIT："Q4 与……互斥"的措辞 | 采纳：改为"Q4 = d 与……互斥"；因为 Q4 = a，该互斥不再触发 | §4.3、§8 Q7 |
| NIT：Q2 选项 a 与 B0-1 的措辞 | 采纳：改为两条硬要求（工作树改动与草稿生成的先后关系；不能存在修好 422 却不要求 JSON 的后端），不再用"提交"来表述 | §4.9、B0-1 |
| NIT：n7 的引用 | 采纳：改为引用 `test_every_entry_module_imports_with_no_vendor_sdk_installed`（约 `:296-329`） | §4.5、附录 A |
| 实现要点：Content-Type | 采纳：缺少时返回 415；精确解析媒体类型，不做子串匹配 | §4.11、B0-2、§6.3 |
