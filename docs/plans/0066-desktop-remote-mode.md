# 计划 0066 — Desktop 远程模式（0064 后续计划 R）

**状态**：第 2.3 版（2026-09-30），owner 已裁定。计划经两轮独立审核修订：第 1 轮的结论是"修改后可以交 owner"；第 2 轮复审确认第 1 轮的意见都已解决，剩下的 R1–R13 属于实现层面，已在第 2.1 版补齐，不需要第三轮（逐条处理见附录 C）。拓扑、范围、续流、bearer 与启动方式在 2026-09-29 的 grilling 里定下（§2.1 的 D1–D6）；§7 的 Q1–Q7 由 owner 于同日全部按推荐裁定，因此 AR-9 不做。编号 0066 已确定（0058–0060 预留给其他工作）。

**进度**：R-A 已完成（2026-09-29），经独立评估和一轮修复，复核结论为通过。后端 BR-1 未提交，按 §4.4 的提交策略处理。App 在 `da509cd` 之后有 7 个本地提交，都未 push：`2f17688` AR-1、`91c9e76` AR-2、`7fe0401` AR-3、`ddc60c4` AR-4，以及评估后的修复 `d5be971`、`deb05c3`、`3da77e2`。评估留下的次要项 m-3、m-4、m-7、m-8、m-9 记在 App 的 `docs/PROJECT_MEMORY.md` 里。R-B 已完成（2026-09-30），同样经过独立评估、两轮修复（含 R-1）和复核，结论为通过。后端 BR-2 到 BR-4 未提交。App 又新增 10 个提交：`9e9241e` AR-5、`158dbca` AR-6、`576ee01` AR-7、`a3b6a0d` AR-8，以及评估后的修复 `ee2730c`、`6fe63c0`、`326550e`、`f835143`、`f3113b5`、`3929abb`。复核留下 10 个次要项，交给 R-C 处理：续流恢复后，"已重新连接"横幅在安静阶段最多多挂约 25 s；先重放内容、随后被取消时仍会弹出"已重新连接"；`nothing_to_reattach` 时页面不重新取消息；补读循环在 sleep 之后不重查截止时间；落盘抛异常时订阅者收不到 `done`；`backend_authority_changed` → 410 没有单测；权限路由的兜底 503 只有英文；`main.ts` 的衔接要在 Electron 下验收；不带 `--import` 跑单测仍会写 `$HOME/.omicsclaw`。这些次要项在 R-C 里处理，只有 `main.ts` 衔接留给 §5.4。R-C 已完成（2026-09-30），经独立评估、一轮修复和复核，结论为通过；AR-10 实跑三次都是 15/15。App 又新增 6 个提交：`a0d8814`（R-B 遗留项）、`0d03db0` AR-10、`88ee47b` AR-11，以及评估后的修复 `9bff7c3`、`ea1f2ce`、`a9c5001`。后端 BR-5 未提交。留作后续的次要项：不加 `--test` 直接运行测试文件时，仍会写 `~/.omicsclaw`；AR-10 的遗留进程清理在组长已退出时不杀组员；本机行 Ping 的回退地址读的是 `OMICSCLAW_BACKEND_PORT`，spec 的 `nextEnv` 没有把它指向死端口；R-A 的 m-3、m-4、m-7、m-8、m-9。§5.4 的 Electron 清单仍待 owner 在自己的机器上做；owner 已于 2026-09-30 在 Mac 上连接运行本工作树的远程服务器实测，暂未发现问题，覆盖了清单哪几项尚未确认。

**编号约定**：Q1–Q7 是本计划自己的问题；grilling 的裁定记作 D1–D6（§2.1 对照原编号）；引用他计划写作"0064-Q9⑥""0065-Q5""0065 S12"。任务编号：后端 BR-n，App AR-n。安全机制接着 0065 编号，从 S23 开始。

**涉及仓库**
- 后端：`/workspace/dataset/private/zhouwg_data/OmicsClaw`，以工作树为准。0064、0065 的后端改动都未提交：`HEAD` 里的 `wire_contract.py` 版本号仍是 1，工作树里是 2。
- 桌面客户端：`/workspace/dataset/private/zhouwg_data/OmicsClaw-App`，HEAD `da509cd`，工作树干净，与 `origin/main` 相同。App 的契约 v2 已经推送：`df525b3` 在 `origin/main` 上，跟踪引用的 reflog 有两次 "update by push"。

**前置与关联**：0064（§2.7 最后一行、§4.1、§4.4、§5.5 计划 R、§6.3、陷阱 18/26）；0065（Q4、Q5、§3.7 S12、AD-12 留给本计划的文件）；0031（陷阱 9、Q14）；0037（`launch` 分层与环境读取规则）；App ADR-0004。

**行号约定**：后端以 2026-09-29 工作树为准，App 以 `da509cd` 为准。实施时按符号名重新定位。

**如何核实**：代码逐处读过；现象来自 2026-09-29 的真机检查（`/tmp/remote-check`：日志、`net-*.log`、`shots/*.png`、脚本）；起草时另做了四项核实，其中两次在 `/tmp` 起过临时的 `oc desktop`（已清理，其中一次真的调用了一次 DeepSeek），见附录 B。第 2 版对审核提到的每一处代码事实都重新核对过。

### 修订说明

**第 2.3 版（2026-09-30）**：记录 R-B 评估之后的裁定 R-1 = a。远程启动串和 App 的占位串都加上 `--delta-ring-size 65536`；续流时如果发现事件已被挤出环，App 在缺口处插入明确说明，不做静默拼接（§3.1）。其余设计不变。

**第 2.2 版（2026-09-29）**：记录 owner 的裁定。Q1–Q7 全部按推荐：Q1 = a（契约升到 v3），Q2 = a（远程启动串的宽限期为 600 s），Q3 = a（隐藏以 `.` 开头的路径段），Q4 = b，Q5 = b（AR-9 不做），Q6 = b，Q7 = a（保留 `/docs`）。正文的设计与任务不变。

**第 2.1 版（2026-09-29）**：按第 2 轮复审补齐 R1–R13，都是实现层面的补充，§7 的选项与推荐没有变化。逐条核实后全部采纳，记录见附录 C 的第 2.1 版一节。
- **R1**：run 登记挂在 `globalThis` 上（仓库里跨路由状态的惯例，也能扛住开发时的热重载）；登记的归属理清为 AR-6 引入、AR-7 扩充；审批路由经 `request_id → session_id` 表找到 run。
- **R2–R5、R8、R11**：看门狗按单次 read 计时；`deferred` 响应不再被浏览器当作可以本地中止；发现断开时立即发一帧 `reconnecting`；隧道绑定按 `reason` 区分瞬时与永久失败，每次尝试前检查是否已切回本机模式；放弃时给浏览器与订阅者补 `error` 与 `done`；续流 POST 沿用 30 s 建连保护。
- **R6、R7**：SVG 之外的所有 XML 类都按 `text/plain` 返回，带编码的猜测按二进制返回；打开文件用 `O_NONBLOCK | O_NOFOLLOW` 并放进线程。
- **R9、R10、R12、R13**：溢出重放的两处等待写明超时后的处理；AR-8 在 reconnect-demand 缺失时按 `null` 处理；Electron 清单的命令改为精确定位 sshd 子进程、双向丢包；§4.4 的说法与用量累计同步。

**第 2 版（2026-09-29）**：按第 1 轮独立审核修订。每条先对照代码核实，再改；逐条记录见附录 C。
- **B1**：刷新恢复（AR-7）从"接管 run、从 0 全量重放"改为"进程内旁听"。原来的 run 始终是唯一的后端读者、转录者与落盘者，Next 为它保留一份有界的已转发行缓冲；重开的页面只是订阅，先收缓冲，再跟实时尾部，超出缓冲上限时才退回后端重放。原设计在长回合里会让落盘内容丢掉开头（环只有 2048 个事件，转录会忽略 `event_omitted`），现状下这不会发生，所以是回退。旁听不需要租约转移，也不用改 `runId` 判定，第 1 版的陷阱 8、9 随之消失。
- **I1**：补上半开连接（关 Wi‑Fi、休眠、换网时两端都收不到 FIN/RST）：
  - ssh2 加 keepalive；Next 的读循环加 60 s 读空闲看门狗；
  - 文档建议服务器 sshd 设 `ClientAliveInterval`；
  - 放弃文案改为"可能已被取消"，放弃后再补读一次；
  - live spec 的代理加 `freeze()`；Electron 清单改为可复现的断开方式，并写明"TCP 自愈"时应有的表现。
- **I2**：重连期间点停止时，停止登记不再 30 s 后被清掉；停止路由在 run 正在重连时立即回 202 `{deferred: true}`，浏览器不再走 2 s 的本地中止；加"点停止后 45 s 才恢复"的单测。
- **I3**：更正 Q1 选项 b 的前提（App 的 v2 已经推送）。采纳"终止组的帧都不带 id"：不用改 `parseCanonicalChatTerminalFrame`，第 1 版的陷阱 5 消失；Next 把不带 id 的帧先缓着，等 `done` 再提交，也修了次要 3。
- **I4**：
  - AR-8 的重试预算改为跟随重连截止时间；
  - Q5 改为推荐 b（不加代码），AR-9 变成只有选 a 才做的条件任务，并补了算账；
  - Q4、Q6 属于范围扩张，改为推荐 b（推迟），写明副作用，并列进 §1.3 的后续候选。
- **次要 1–17**：全部采纳，改动位置见附录 C。其中 S30（关闭 `/docs`）不再推荐，改为 Q7 交 owner。

**第 1 版（2026-09-29）**：初稿。

---

## 0. 摘要（结论先行）

**现状**（真机检查，§2.4）
- 能用：带 bearer 的健康检查与状态灯；普通对话；审批卡片；停止；侧栏项目行上的"+"新建会话。文件写入与 git 路由在远程模式下干净地返回 409 `remote_unsupported`。
- 阻断：文件树 404；对存在的文件，预览报 "File not found"；看不到任何图片；`/chat` 页新建会话掉进目录选择的死路；侧栏"新建会话"提示"目录不存在"。
- 严重：连接一断，App 两秒内显示 `Error: terminated`，从不重连；后端 30 s 后取消回合，历史里什么也不留。审批待决时刷新或关页，回合还在等回答，重开的页面却看不到卡片，也没有停止按钮。

**三个根因**
1. 后端没有文件路由（`/files/tree`、`/files/serve`），App 的远程代理全部落空。
2. App 在远程模式下仍把项目当作可切换的本机目录：用 `/api/files/browse` 校验目录、弹目录选择器、提供"最近项目"切换。远端后端一个进程只服务一个工作区。
3. 续流缺三样东西：帧没有可用的游标（有些事件占用序号却不出帧，按帧计数必然错位）；App 从不带 `after_seq` 重发，半开连接时甚至发现不了断线；刷新后的页面找不到仍在跑的回合（`/api/chat/sessions/:id/resume` 是一个返回 `legacy_session_resume_retired` 的桩）。

**本计划做什么**
1. 后端加两条只读文件路由，按真实路径限定在工作区内，要 bearer（配置了 token 时），响应沿用旧后端的形状（BR-1）。
2. 后端续流：非终止帧带 SSE `id:` 行（事件序号）；请求可带 `resume: true`，只接回已有回合，从不新开；用量按回合累计；宽限期可配置并在 `/health` 公布；契约升到 v3（Q1）（BR-2、BR-3）。
3. App 断线自动重连：后端连接出错、提前结束或 60 s 没有字节时，Next 路由用 `resume` 与 `after_seq` 接回去，浏览器显示"正在重连"；放弃后隧道恢复时再补读一次（AR-6）。
4. App 刷新与关页后的恢复：新路由 `GET /api/chat/sessions/:id/live` 取代 resume 桩；重开的页面旁听仍在跑的那个 Next run，卡片与停止按钮随缓冲重放回来（AR-7）。
5. App 远程工作区固定为远端 `GET /workspace` 的值：不弹选择器，不校验本机目录，不提供切换，错配时给出远程专用的说明（AR-3）。
6. 文件树、预览、图片端到端可用（AR-4）；bearer 探测改用 `/health`（AR-2）；删除远程 jobs 死代码（AR-1）；SSH 隧道加 keepalive 并自动重连（AR-8）。
7. 一份带 bearer、会切断与冻结代理、做文件系统隔离的 live Playwright spec（AR-10），外加 owner 机器上的 Electron 清单（§5.4）；重写后端与 App 的远程文档（BR-5、AR-11）。

**分期**（§4，共 16 个任务，其中 AR-9 只在 Q5 选 a 时做）

| 期 | 内容 | 依赖 |
|---|---|---|
| R-A 远程工作区可用 | BR-1 文件路由；AR-1 删 jobs 死代码、AR-2 bearer 探测、AR-3 工作区固定、AR-4 文件查看 | 后端与 App 并行；AR-4 排在 AR-3 之后，真机验收要 BR-1 |
| R-B 断线续流 | BR-2 宽限期、BR-3 契约 v3、BR-4 认证测试；AR-5 v3 门控、AR-6 断线重连、AR-7 刷新恢复、AR-8 隧道重连、（AR-9 退出时中止） | BR-3 与 AR-5 同批落地（§6 陷阱 2） |
| R-C 验收与文档 | AR-10 live spec；BR-5、AR-11 文档；§5.4 Electron 清单 | R-A、R-B 之后 |

**待 owner 裁定**：7 个问题（§7）。影响最大的是 Q1（契约升 v3，还是改动已推送的 App v2 的含义）、Q2（远程宽限期的缺省值）、Q3（文件路由隐藏哪些路径）。

---

## 1. 目标与非目标

### 1.1 目标

| # | 目标 | 验收口径 |
|---|---|---|
| G1 | 远程模式下新建会话不经过任何目录选择：`/chat` 页、侧栏"新建会话"、项目行"+"都直接落在远端工作区 | §5.3 b、§5.4 第 3 项 |
| G2 | 远端工作区里的文件可以在 App 里浏览与只读查看：文件树、文本与表格预览、PNG/SVG、PDF、聊天里 agent 写出文件的"打开预览"；工作区之外的路径一律拒绝 | §5.3 c–e |
| G3 | 连接中断后自动重连，包括收不到 FIN/RST 的半开连接。宽限期内恢复时，回合接着流，转录不重复、不缺失；超过宽限期或后端重启时，界面给出说明，不再是 `Error: terminated` | §5.3 f、g、m、o；§5.4 第 5–7 项 |
| G4 | 远程模式下刷新或关页后重新打开会话，仍在跑的回合回到界面：已生成的内容、待决的审批卡片、停止按钮；落盘内容完整 | §5.3 h |
| G5 | token 错误与缺失分开提示；探测只用 `/health` | §5.3 j |
| G6 | 远程 jobs 死代码与钉住已删契约的单测删除，换成针对新契约的测试 | AR-1、AR-2 的 `git grep` 验收 |
| G7 | 后端与 App 的远程文档如实描述现状，包括启动方式、token 以明文存放的位置、sshd 的 keepalive 建议、共享服务器的已接受风险 | BR-5、AR-11 |

### 1.2 非目标

- 上传笔记本上的文件、下载服务器上的文件（D2）。
- 浏览器访问部署在服务器上的 Next；多个用户共享一个后端（D1）。
- `npm run dev` 的远程模式入口（D6）。live 测试照 2026-09-29 的检查那样经内部路由进入远程模式（§5.3）。
- 远程模式下的写操作：文件写入、改名、删除、新建目录与 git 路由继续返回 409 `remote_unsupported`；预览编辑器保持只读（`files/preview/route.ts:58` 的 `edit_unavailable: 'remote'`）。
- 远程模式下写 Providers（0065-Q5，已实现为只读）。
- 后端产出图片或媒体帧：两种模式下都没有工具产出 `media`（0064 V1）。聊天里的图片预览靠 App 从文本与工具结果里识别路径（App `README.md:230-238`），接上 `/files/serve` 就能用。
- App 进程重启后接管仍在跑的回合。
- SSH 密码与带口令的私钥：继续只支持私钥文件与 ssh-agent（`ssh-auth.ts`）。
- TLS、CORS、Host 白名单（0064-Q4，DNS 重绑定已接受）。
- 一个后端服务多个工作区；远程模式下切换项目（0064 §5.5）。
- 修改 0057 的任何文件；重写 `AGENTS.md`。

### 1.3 后续候选（本计划推荐不做，owner 可以在 §7 里改选）

- 本机模式的刷新恢复（Q4）：要改变本机模式"浏览器断开即停止读取"的语义（0064 陷阱 18）。
- 远程模式的完成通知（Q6）：远程聊天要写进本地 jobs 表。
- App 退出时中止远程在途回合（Q5 的 a）。
- App 重启后接管在途回合（持久化在途记录，或后端加一条列出在途回合的路由）。
- `useSlashCommands` 里不带 `dir` 的 `fetchFiles`（两种模式都 400 的重复实现，§3.13 m3）。

---

## 2. 现状与证据

### 2.1 已定的裁定（2026-09-29 grilling，另加从 0064、0065 继承的约束）

| 记号 | grilling 原号 | 裁定 |
|---|---|---|
| D1 | Q1 | 拓扑：笔记本上的 Electron App 经 App 自带的 ssh2 隧道，连服务器上绑定 `127.0.0.1` 的 `oc desktop`，bearer 可选。直连 URL 加 bearer 连非回环地址，走同一套代码。浏览器访问服务器上的 Next、多用户共享后端都不在范围内 |
| D2 | Q5 | "远程可用"指：对话闭环（对话、审批、停止）；新建会话可用；只读查看远端工作区里的文件与图片（文件树、预览、图片），限定在工作区内，要 bearer（0064-Q9⑥）。不要求上传与下载 |
| D3 | Q6（真机检查后修订） | 断线后 App 自动用相同的 `session_id`、`source_request_id`、`installation_id` 加 `after_seq` 重发 `POST /chat/stream`；后端给每帧带序号，让 `after_seq` 精确；放弃回合的宽限期可配置，远程启动串用更长的值 |
| D4 | Q7 | bearer 保持可选，只在文档里建议设置。共享服务器上其他操作系统用户能连到 `127.0.0.1`，记为已接受风险 |
| D5 | Q8 | 两种启动方式都支持：用户手动启动（tmux、nohup、systemd，文档主推）；App 现有的 `remote_bootstrap_command`。文档写明 token 以明文存在启动命令与连接配置里 |
| D6 | Q9 | `npm run dev` 没有远程模式入口，远程模式只在 Electron 下提供 |

继承的约束：
- 0064 §5.5：远程工作区以远端 `GET /workspace` 为准，只读，远程模式下禁止切换项目；bearer 探测改为带认证头请求 `GET /health`，401 即失败；删除远程 jobs 面板（`remote-jobs-proxy.ts`、`remote-jobs-adapter.ts`、`remote-sse-adapter.ts` 与 jobs 路由的远程分支）；`/files/tree`、`/files/serve` 只读，按真实路径限定在工作区，要 bearer。
- 0065-Q5：远程模式下 Providers 页只读（已实现）。
- 0065 AD-12 把 `remote-jobs-*`、`remote-sse-adapter`、`remote-proxy-bootstrap` 留给本计划。其中 `remote-proxy-bootstrap.ts` 仍在用（`tunnel-manager.ts:43`），保留。

### 2.2 后端现状（只列本计划用到的事实）

**路由与认证**（`omicsclaw/entry/desktop/server.py`）
- 13 条路径（`wire_contract.py:42-56` 的 `SERVED_PATHS`），由 `create_desktop_app`（`server.py:371-631`）挂出。没有 `/files/*`、`/jobs*`、`/connections/test`、`/sessions/{id}/resume`。
- 每个处理函数自己调用 `_authorized`（`:410-417`，`secrets.compare_digest`）；token 为空时不校验。
- `/health`（`:623-629`）：设了 token 而请求没带认证头时，返回简化的 200 `{status, version, launch_id, auth_required: true}`（`:296-311`）；token 错误返回 401；token 正确返回完整载荷。
- `FastAPI(title=..., version=...)`（`:407`）保留了缺省的 `/docs`、`/redoc`、`/openapi.json`，设了 token 也不要认证（附录 B-2：不带头、错误 token、正确 token 都是 200）。未知路由在认证之前就返回 404，带不带 token 都一样。
- 写路由只收 JSON（`_require_json`，`:425-428`，否则 415）。没有 TLS、CORS、Host 白名单。
- 非回环地址又没有 token 时拒绝启动（`launch/_surfaces.py:1137-1159`）。token 从环境读（`:1104`），`.env` 也算：`_adopt_dotenv`（`launch/__init__.py:168-205`）在 `start_desktop` 之前把 `.env` 叠进环境，已导出的同名变量优先。

**工作区**
- `AppConfig.workspace` 在解析时就做了 `expanduser().resolve()`（`entry/config.py:1330-1332`），所以 `GET /workspace` 回的是真实路径。
- `PUT /workspace` 只接受同一个目录，否则 409 `workspace_change_requires_restart`（`server.py:322-341`）；`/chat/stream` 声明的工作区不符时 409 `workspace_does_not_match_backend_runtime`（`:188-196`）。
- 后端把自己的状态放在 `<workspace>/.omicsclaw/`：权限规则、计划、卸载的工具结果、压缩记录、`memory.db`（`entry/config.py:137-141`）。
- 工具结果是纯文本，写的是服务器上的绝对路径，例如 `Wrote /abs/path with N bytes`（`tools/builtin/write.py:354`）、集成工具的 `output_dir`（`ensemble/tool.py:151`）。

**续流机制**
- 每个回合一个 `TurnStream`，保留环是 `deque(maxlen=2048)`（`entry/stream.py:59, 167`）；每个 token 增量是一个事件，长回合里各类事件（包括 `TURN_END`）都会被挤出。游标落在环外时，观察流先给一帧 `GAP`，它的 `seq = oldest - 1`（`entry/events.py:447-468`），投影为 `event_omitted`。
- 一个回合最多 16 个观察者（`stream.py:85`），超出时 `observe` 抛 `ObserverCapacityError`；Desktop 没有捕获它，客户端会收到 500。
- 最后一个观察者离开后，宽限期（`DEFAULT_ABANDON_GRACE_S = 30.0`，`entry/session.py:91`）到期即取消回合；这期间有观察者接上就撤销计时（`turn.py:951-991`）。被取消的回合不改历史（`session.py:804-809`）。服务器端要先发现连接断了，观察者才会离开；半开连接时这可能要很久（§2.3 的 I1 事实）。
- 已结束的回合按 `max_sessions = 256` 保留（`session.py:849-870`）；接回已结束的回合会补发剩余帧与 `done`。
- 接回的入口已经存在：同一会话、同一 `source_request_id` 的重投回到同一 exchange（`session.py:424-432`，有例外，见 §2.5）；Desktop 另在 `DesktopInteractions` 里记 `(session_id, source_request_id) → turn_id`（`interactions.py:141-166`）。`after_seq` 从请求体读（`server.py:634-645`），交给 `handle.observe(after_seq=...)`（`:227`）。进程内的续流测试已有（`tests/entry/test_desktop_stream.py:420-571`）。
- 帧没有可用的游标：每帧只有一行 `data: {"type", "data"}`，没有 `id:` 行（`turn_observation.py:1-8`）。对象载荷帧（`tool_use`、`tool_result`、`permission_request`、`status`、`event_omitted`）的 data 里有 `sequence`（`:161-174`），纯文本帧、`result`、`done`、`keep_alive` 没有。`TURN_END`、被自动放行的审批等事件占用序号却不出帧（`:395-405`），所以按帧计数的客户端总是落后，接回时收到重复帧（真机检查用 curl 实测多出 2 帧）。
- 接回后的 `result.usage` 只统计这个新观察流看到的 `TURN_END`：`DesktopChatSSEBody` 从零计数（`:308-356`）。
- `keep_alive` 每 25 s 一帧（`turn_observation.py:70`）。后端重启后什么都不剩（`wire_contract.py:67-75`）。

**启动**
- `oc desktop [部署 flag] [-- --host --port]`，界面 flag 只有 `--host`、`--port`（`_surfaces.py:1017-1063`）。`_serve_desktop` 调用 `attach_sessions(await open_app(config))`，不传宽限期（`:1188-1206`）。
- 冷启动：本机热缓存下 3.5 s 开始监听（附录 B-1）。

### 2.3 App 现状（远程模式的管道）

**模式与连接**
- 远程模式 = SQLite 设置 `connection_mode=remote`，加上 `active_connection_profile_id` 指向 `connection_profiles` 的一行（`db.ts:332-365`；`backend-config.ts:413` 的 `isRemoteMode`）。只有 Electron 能切换：`PUT /api/internal/runtime-activation` 要主进程密钥（`runtime-activation/route.ts:47-48`），`PUT /api/settings/app` 拒绝这些键（`settings/app/route.ts:92-101`）。
- bearer 在 `dispatchBackendFetch` 统一附加（`backend-fetch.ts:366-372`），`chat-session-permission.ts:43-48` 手工附加。token 明文存在 SQLite（`settings/app/route.ts` 的 `MASKED_KEYS` 注释）；连接配置的 `auth_token` 支持 `env:VAR` 间接引用（`auth-token-resolver.ts`）。两处把 token 回显给页面时都只遮到"不超过 8 个字符原样显示"（`api/connections/shared.ts:13-16`、`settings/app/route.ts:57-64`）。
- SSH 隧道由 Electron 主进程用 ssh2 实现（`src/lib/tunnel-manager.ts`，`main.ts:46` 引入调和器）。主进程每 3 s 调和一次（`main.ts:235`），期望状态经 Next 的 `/api/settings/app` 与 `/api/connections/:id` 读取（`main.ts:650-675`）。
  - 认证只有私钥文件或 ssh-agent（`ssh-auth.ts`），known_hosts 加 TOFU，支持 `~/.ssh/config` 别名；`readyTimeout` 10 s。
  - `connectConfig` 没有 `keepaliveInterval`（`tunnel-manager.ts:522-560`），全仓库也没有别的 SSH keepalive。
  - 传输断开时状态置为 `broken`，尝试次数加 1（`tunnel-manager.ts:895-968`）；连续 3 次失败后不再自动重开（`:191`；`tunnel-reconciler.ts:116-124`）。所以断线超过约 30–40 s，隧道就停在 `broken`。
  - `reconnecting` 状态已声明但从不设置（`tunnel-manager.ts:164`）。`reconnectTunnel` IPC 在主进程有处理（`main.ts:1897-1900`），渲染进程没有调用方（`preload.ts:84`）。
  - 每次重开都会退役上一次的本地监听端口，并保留到 Next 进程结束，每个 Next 进程最多 32 个（`tunnel-manager.ts:199`）；耗尽后要求重启连接运行时。
  - `tunnel-manager.test.ts` 已经有进程内的 ssh2 server 测试夹具。
- `remote_bootstrap_command` 在端口未监听时经 `client.exec` 执行，缺省轮询 15 s（`tunnel-manager.ts:150, 1102-1230`）；`remote_proxy_url` 由 `remote-proxy-bootstrap.ts` 拼进命令。这条路径从未对 `oc desktop` 实测过。
- 探测：`probe-profile.ts:111-130, 325-345` 与 `runtimes/[id]/ping/route.ts:56-78, 186-225` 先请求 `GET /health`，再用 `GET /env/doctor` 判断 token（401 即错）。现在 `/health` 自己就对错误的 token 返回 401，第二次探测是多余的；ping 对 `/health` 的 401 只显示 `HTTP 401`（`:228-236`）；`:178-186` 的注释还指向已删除的 `omicsclaw/remote/app_integration.py`。`/api/health` 把 401 与缺 token 都归为 `auth-required`（`api/health/route.ts:127-134, 170-175`），状态灯显示 "Backend Offline"（`en.ts:695`）。

**契约门控**
- App 的 `/health` 门控是精确相等（`backend-health.ts:28-41`）；`witnessBackendIdentity` 在版本不符时抛 `BackendContractIncompatibleError`（`backend-fetch.ts:851`）。所以版本不符在见证 `/health` 时就会被拒绝，不必等到第一次发送。
- `AGENTS.md:9` 写着"请求与 SSE 都是 v2"。

**工作区**
- 远程模式下 `getAuthoritativeWorkspace` 读远端 `GET /workspace` 并回写 `default_project_dir`（`backend-workspace.ts:124-137`；`api/setup/route.ts:88-100`）。
- 选择项目的入口：`/chat` 页（`chat/page.tsx:190-211` 用 `/api/files/browse` 校验，另有 `:261`、`:277`、`:759`）；侧栏（`ChatListPanel.tsx:284`，`:302-309` 在 Electron 下打开本机原生选择器，`:311-340` 新建会话，`:1274`）；设置页（`OmicsClawSection.tsx:201, 242, 274, 522`）；向导（`ProjectStep.tsx:68, 166`、`useProjectSetup.ts:32`）；错配提示（`WorkspaceMismatchNotice.tsx:22`）。`resolveNewChatDirectory` 也用 browse 校验（`project-switch.ts:88-99`）。
- 远程模式下 `PUT /api/setup` 把项目转成 `PUT /workspace`（`api/setup/route.ts:285-288`），换目录得到 409，界面直接显示原始错误码。

**文件**
- 远程分支都代理到旧后端的路由：`api/files/route.ts:15-45`（`/files/tree?path&depth`，读 `{root|current, tree}`）、`files/browse/route.ts:34-58`（把 `?dir` 换成 `?path`；远程分支在 `:62-64`，删掉它会落到 `:66` 起的本机分支，列出笔记本的家目录）、`files/serve/route.ts:58-70`、`files/raw/route.ts:105-117`、`files/preview/route.ts:32-69`（带 `Range: bytes=0-(上限-1)`；上限 256 KiB，结构化格式 10 MiB）。
- serve 与 raw 的代理只转发类型、长度、Range、`Cache-Control`、`Content-Disposition` 六个头（`serve/route.ts:40-47`、`raw/route.ts:87-94`），不转发 `X-Content-Type-Options`。
- 旧后端的形状（`git show HEAD:omicsclaw/surfaces/desktop/server.py`，约 `:4248-4592`）：`/files/tree` 回 `{root, tree:[{name, path, type, size, extension, children}]}`，`path` 是绝对路径；`/files/serve?path=` 回 `FileResponse`（支持 Range），限定在可信根目录内；`/files/browse?path=` 回 `{current, parent, directories}`，跳过点文件。
- 图片与文件卡片：`ImageViewer.tsx:17`、`MediaPreview.tsx:27, 212`（相对路径加 `sessionId`；远程代理只转发 `path`）、`PlotViewer.tsx:22`、`MessageItem.tsx:327`（文件卡片的预览）。
- `@` 提及：`MentionPopover.tsx:31` 读 `/api/files/browse`；`useSlashCommands.ts:55-60` 请求 `/api/files` 却不带 `dir`，两种模式下都得到 400（`api/files/route.ts:52-57`）。

**聊天代理**
- 浏览器 → Next `/api/chat` → 后端 `/chat/stream`。Next 路由边读边解析（`processSseChunk`，`api/chat/route.ts:907-975`），把原始字节原样转给浏览器（`:1045`），结束时写 SQLite。浏览器侧有两个 SSE 消费者：会话页的 `stream-session-manager.ts`，以及新会话页经 `src/lib/new-chat-submission.ts:57-84` 调用的 `consumeSSEStream`（由 `chat/page.tsx:24` 引入，回调在页面里）。
- 远程模式下浏览器断开，Next 并不断开后端：`createAbortSignal(..., {propagateRequestAbort: !remoteChat})`（`:668-672`）；`handleClientAbort` 只在本机模式取消读取（`:1003-1009`）；结束时照常落盘（`:1053-1066`）。本机模式下断开即取消读取，且不落盘。
- `await reader.read()` 没有超时（`:1019`）。后端连接出错时它抛出（undici 的 `terminated`），走通用错误分支，落盘 `Error: terminated`（`:1223-1235`）。半开连接时它一直挂着，浏览器 330 s 后自己发 `idle_timeout` 停止（`stream-session-manager.ts:516-535`，`CHAT_STREAM_IDLE_TIMEOUT_MS`，`chat-stream-transcript.ts:10`）。聊天路径里没有任何 `after_seq`（全仓库只有要删的 jobs 代码有游标）。
- 两个解析器都只处理 `data:` 行、跳过其他行（`api/chat/route.ts:930`、`useSSEStream.ts:275`）。例外是终止帧判定：`parseCanonicalChatTerminalFrame`（`api/chat/route.ts:94-118`）要求一帧恰好一行 `data:`，它的结果只用于审批绑定的收尾（`:883-903`）。标题的终止状态取 `settledTerminal`（`:1100-1106`），与它无关。
- `event_omitted` 只有浏览器处理（`useSSEStream.ts:202`）；Next 的转录走 `switch` 的 `default` 分支，直接忽略（`chat-stream-transcript.ts:352`）。
- 转录遇到 `error` 帧会追加一段错误文本（`chat-stream-transcript.ts:338-350`），同一帧收两次就追加两次。
- 同一会话的在途 run 由两处登记：进程内的 `chat-stream-stop-registry.ts`（`beginChatStreamRun` `:51-78`；`isChatStreamGenerationCurrent` 只比较 `source_request_id`，`:132-138`；`finishChatStreamRun` `:147-169`）；跨进程的 SQLite 租约 `chat-execution-lease.ts`（`acquire` `:75-163`）。`isProxyRunCurrent` 同时看两者（`route.ts:493-496`）。
- 停止：`markChatStreamStopped` 给登记挂 30 s 的清理计时（`chat-stream-stop-registry.ts:4, 34-49, 79-111`）；清掉之后 `isProxyRunCurrent` 为假，run 会走 `retireSupersededProxyRun`（`route.ts:614-632`），既不落盘（`assistantMessageId` 恒为 null，`:612`），也不发 `/chat/abort`。浏览器的 `interruptChatStream` 在请求发出前就挂了一个 2 s 后本地中止的兜底（`chat-stream-interrupt.ts:45-54`）。
- 后端目标绑定：`reserveOperation`（`backend-fetch.ts:904`）见证 `/health` 的 epoch 并冻结目标。`resolveOperationTarget('chat', chatOperationResourceId(...))`（`:932-1000`）按持久化的绑定、用**当前**隧道端口重建目标并再次见证 epoch。SSH 目标的指纹不含端口（`backend-operation-binding.ts:127-148`），隧道换了端口，同一台后端仍能找到。停止路由（`api/chat/interrupt/route.ts`）与审批路由（`api/chat/permission/route.ts:136-148`）都这样找后端。
- `target_no_longer_available`（409）的来源很多，彼此分不开：`/health` 传输失败、非 200、载荷格式错（`backend-fetch.ts:794-850`）；epoch 不符（`:954-956`）；连接配置被删或 `authority_revision` 变了（`backend-operation-binding.ts:434-440`）；隧道没有发布（`:117-119`）；绑定行变了（`backend-fetch.ts:962-983`）。
- `POST /api/chat/sessions/:id/resume` 是桩，一律返回 `legacy_session_resume_retired`（`resume/route.ts`）；调用方是 `session-resume.ts` 与 `chat/[id]/page.tsx:144-160` 的占位注入。
- Electron 的后台通知在窗口隐藏时每 5 s 轮询 `/api/jobs`（`main.ts:1488-1535`）。远程模式下 `/api/jobs` 代理到不存在的 `/jobs`，远程聊天也不建本地 job（`route.ts:640`），所以远程模式下没有完成通知。本地 job 的取消只改 SQLite，不停后端的回合（`api/jobs/[id]/cancel/route.ts:21-35`）。退出流程是 `before-quit`（`main.ts:2248-2259`）→ `shutdownBackend`（`:1452-1482`）。

### 2.4 真机检查结果（2026-09-29，`/tmp/remote-check`）

**怎样进入远程模式**（live spec 沿用）
- `OMICSCLAW_DATA_DIR=<临时目录>` 起 `next dev`；预热之后、任何浏览器加载之前取 `GET /api/internal/main-process-secret`（每个 Next 进程只给一次）；
- `POST /api/connections {name, url, auth_token}`；
- `PUT /api/internal/runtime-activation`，头 `x-omicsclaw-main-confirm`，体 `{schemaVersion:1, mode:"remote", pythonPath:null, activeProfileId, expectedProfileAuthorityRevision:1, expectedProfileTargetFingerprint:null}`，得到 200。
- 用一个可重启的 asyncio TCP 代理（18766 → 18765，`proxy.py`）模拟隧道。
- 文件系统隔离：容器里不能 `unshare`，改为用 `setpriv` 去掉 Next 的 `CAP_DAC_OVERRIDE`、`CAP_DAC_READ_SEARCH`，后端工作区放在另一个 uid 所有的 0700 目录下（`next-start.sh`）。
- 另需 `OMICSCLAW_SKILLS_DIR=<仓库>/skills`：技能缺省在 `<workspace>/skills`。

| 类 | 现象 | 证据 |
|---|---|---|
| 可用 | 每个请求都带 bearer，状态灯正常；普通对话；审批卡片"允许一次"后完成；停止 `sleep 90`（`/chat/abort` 200，显示 "(generation stopped)"）；侧栏项目行"+"新建的会话可用；文件写入与 git 路由 409 `remote_unsupported` | `shots/A-*`、`B1/B2/B3-*`、`D4-*` |
| 阻断 | 文件树 "Failed to load (404)"；`/api/files/preview` 对存在的文件返回 404 "File not found"；agent 写出的文件卡片"打开预览"同样失败；没有看 PNG 的途径；`/api/files/raw`、`serve` 都是 404 | `E1/E2-*`、`net-sE*.log` |
| 阻断 | `/chat` 用 browse 校验项目，得到 404，页面进入"选择文件夹"；应用内的 FolderPicker 没有子目录，"Select This Folder" 报 "empty path"（`FolderPicker.tsx:62, 97`：`onSelect(currentDir)`，而 `currentDir` 只在 browse 成功时设置）；只有点"最近项目"才能新建（`PUT /api/setup` → `PUT /workspace` 200），每次刷新都要重来；侧栏"新建会话"提示"目录不存在"，又回到死路（Electron 下会打开本机原生选择器，按代码推断） | `D1/D2/D3-*` |
| 重要 | 断线后 2 s 内显示 `Error: terminated`，从不重发；后端 30 s 后取消；后端 `memory.db` 里这一回合 0 条消息；App 历史里留着 `Error: terminated` | `H-short/long-*`、`net-sH-*.log` |
| 重要 | 审批待决时关页：重开后没有卡片、没有停止按钮；resume 返回桩；新消息排在看不见的回合后面，直到 30 s 宽限把它取消（机制见 §2.6 E6） | `B3b/B3c-*` |
| 重要 | 点"最近项目"换到别的目录，toast 显示 "Could not select this project: workspace_change_requires_restart"（原始码）；在绑定别的目录的会话里发送，后端 409，聊天里的说明（`en.ts:1397`）对远程是错的：让用户点一个不会出现的 "Switch to this project"，说桌面端会重启后端，还给出本机的 `oc desktop … --port 8765` 命令 | `F1/F2/F3-*` |
| 次要 | token 错误或缺失时，说明文字清楚，但状态灯写 "Backend Offline"，Ping 写 "Unreachable · HTTP 401"，且不区分错误与缺失 | `C-*` |
| 次要 | `/api/workspace/quick-actions` 对笔记本磁盘做 `fs.readdir`（`quick-actions/route.ts:26`）；`@` 提及见 §2.3；"打开助手"按钮不出现；远程模式下每 10 s 请求一次 `/api/git/status`（`git-status-store.ts:19, 43`），控制台满是 409；`maskToken` 对不超过 8 个字符的 token 原样显示 | `G-*`、`E3/E4-*` |
| 未覆盖 | 浏览器路径下没有界面会调 `/jobs`；Electron 的任务通知没有验证；代理被杀属于干净断开，没有测到半开连接 | — |

### 2.5 起草时的补充核实（附录 B）

- `oc desktop` 在热缓存下 3.5 s 开始监听，`remote_bootstrap_command` 的 15 s 轮询对这种情况够用；服务器冷缓存下的耗时放进 §5.4 实测。
- 设了 token 时，`/docs`、`/redoc`、`/openapi.json` 对不带头、错误 token、正确 token 都返回 200；未知路由带不带 token 都是 404；`HEAD /health` 带正确 token 返回 200。
- 同一 `source_request_id` 的重投，只在内容"同是 `/compact`"或"同不是"时才回到同一 exchange。先发 `/compact`，再用同一个 id 发普通内容，后端新开了 exchange，还真的调用了模型。原因：压缩走 `registry.compact`，登记时不带 `source_request_id`（`session.py:409-411`）；普通消息走 `registry.deliver`，按 `(session, 带命名空间的 id)` 查（`:424-432`）。所以续流不能依赖重投，要按 `interactions.turn_for` 找回合（BR-3）。
- Starlette 1.0.0 的 `FileResponse` 在 Range 起点不满足 `0 <= start < file_size` 时回 416（`starlette/responses.py:475-476`），空文件带任何 Range 都是 416。

### 2.6 对起草说明（brief）的更正

| # | 起草说明的说法 | 核实结果 |
|---|---|---|
| E1 | SSE 帧不带 seq/id，客户端只能数帧 | 没有 `id:` 行，但对象载荷帧的 data 里有 `sequence`。数帧行不通的根因是有些事件占用序号却不出帧（§2.2） |
| E2 | 回放环 2048 在 `stream.py:60` | 在 `:59`；环里各类事件都会被挤出，不只是增量 |
| E3 | "打开助手"按钮在远程模式下出现不了 | 任何模式下都出现不了：没有代码派发 `assistant-workspace-switched`（`ChatView.tsx:475` 只监听）。与远程无关，本计划不处理 |
| E4 | 钉住已删契约的单测包括 `files-route-remote`、`files-serve-remote`、`files-preview-remote` | 这三个测的是 App 代理对旧形状的转发，本计划沿用旧形状，它们基本保留。另有两个起草说明没列、也要改：`backend-operation-binding.test.ts`（借 `remote-jobs-proxy` 测 job 绑定，`:23-45`）、`runtimes-ping.test.ts`（`/env/doctor` 探测，`:117, 633`）。`remote-wire-shape.test.ts` 里 `/health` 快照那一段要保留，改到 v3 |
| E5 | ping 路由的陈旧注释在 `:175-183` | 在 `:178-186` |
| E6 | 关页后"新消息排在看不见的回合后面，直到 30 s 宽限取消它" | 按代码补全机制（与实测现象一致）：远程模式下关页并不断开后端（§2.3），回合继续跑，结束时本会落盘；新消息使旧 run 失去所有权，旧 run 在下一次读到数据时（最多等一个 25 s 的 `keep_alive`）才断开后端，之后才开始 30 s 宽限。审批待决的回合不会自己结束 |

---

## 3. 设计

### 3.1 拓扑与启动（D1、D5）

**推荐的启动串**（在服务器上用 tmux、nohup 或 systemd 运行）

```bash
OMICSCLAW_SKILLS_DIR=<检出目录>/skills \
oc desktop --workspace <服务器上的项目目录> --delta-ring-size 65536 -- --host 127.0.0.1 --port 8765 --abandon-grace 600
```

- `--abandon-grace` 是 BR-2 新增的界面 flag，远程启动串推荐 600 s（Q2）。本机模式由 Electron 启动，不传这个 flag，仍是 30 s。
- `--delta-ring-size 65536` 是已有的部署 flag（`entry/config.py:1064-1065`，缺省 2048），写在 `--` 之前（R-B 评估 R-1，owner 2026-09-30 裁定）。长回复每秒产生几百个事件，断线几秒续流点就会被挤出 2048 个事件的环。内存按每个回合的实际事件数占用，65536 只是上限。环再大也有上限：续流以 `event_omitted` 开头时，App 在界面和落盘内容里插一段"断线期间有一段输出没能接回"的说明，不做静默拼接。
- token 可选（D4）。要设时，推荐写进 `oc desktop` 启动时读取的 `.env`（检出目录或 `OMICSCLAW_DIR` 下的，或启动时当前目录下的，见 `launch/_dotenv.py` 的 `dotenv_candidates`；`chmod 600`），或者 systemd 的 `EnvironmentFile`。这样启动命令里没有密钥。
- 工作区不是检出目录时要带 `OMICSCLAW_SKILLS_DIR`，否则 `/health.skills_count` 为 0。
- 服务器的 sshd 建议设置 `ClientAliveInterval 30` 与 `ClientAliveCountMax 3`。笔记本断网或休眠时，sshd 约 90 s 后发现连接已死并关闭转发，后端的观察者随之离开，宽限期才开始计时。不设的话要等 TCP 自己超时，可能是几十分钟以上，这期间回合一直被当作有人在看。

**App 自动启动**（`remote_bootstrap_command`）
- 示例（同时更新 App 的占位串，`en.ts:1799` 与 `zh.ts:1794`）：`bash -lc 'cd ~/my-project && OMICSCLAW_SKILLS_DIR=~/OmicsClaw/skills nohup oc desktop --workspace ~/my-project --delta-ring-size 65536 -- --host 127.0.0.1 --port 8765 --abandon-grace 600 > oc-desktop.log 2>&1 &'`。
- 文档写明：这条命令以明文存在 App 的 SQLite（连接配置那一行）。把 `OMICSCLAW_REMOTE_AUTH_TOKEN=...` 写进命令，token 也就明文存在那里，并在 `bash -lc` 进程存活的短暂时间里出现在服务器的进程列表中。推荐做法是 token 放服务器的 `.env`，App 侧的 `auth_token` 写成 `env:VAR`。
- 15 s 的轮询不改；§5.4 在 owner 的服务器上实测冷启动。

### 3.2 只读文件路由（BR-1）

**路由**：新模块 `entry/desktop/files.py` 放纯函数；`server.py` 只加外壳，沿用 `_authorized`。

| 路由 | 查询参数 | 成功 |
|---|---|---|
| `GET /files/tree` | `path`（可选，缺省为工作区；绝对路径，或相对工作区的路径）；`depth`（1–10，缺省 3） | `{root, tree, truncated}`；节点为 `{name, path, type: "file"\|"directory", size?, extension?, children?}` |
| `GET /files/serve` | `path`（必填，写法同上） | 文件字节；支持单段 `Range` |

响应沿用旧后端的形状（§2.3），App 的代理与它们的单测不用改形状。两处细节：
- `path` 是请求目录按词法拼上条目名得到的绝对路径（不展开符号链接），与 App 会话里的 `working_directory` 是同一种写法。
- `extension` 不带点，与 App 本机的 `scanDirectory` 一致（`src/lib/files.ts`）。旧后端带点，这是唯一的形状变化。

**把请求路径限定在工作区里**：`resolve_in_workspace(workspace, raw)`，树与文件共用。
1. `raw` 为空（仅 `serve`）→ 422 `path_required`；含 NUL 或无法解析 → 422 `invalid_path`。不展开 `~`。
2. 相对路径拼在工作区上。
3. 词法检查：`os.path.normpath` 之后，相对工作区的各段做隐藏检查（Q3）；词法上已在工作区之外 → 403 `path_outside_workspace`。只看工作区之下的段，工作区本身所在路径里的点目录不算。
4. `resolve(strict=True)`：不存在 → 404 `file_not_found` 或 `directory_not_found`。
5. 真实路径必须在 `workspace.resolve()` 之下，否则 403 `path_outside_workspace`；真实路径相对工作区的各段再做一次隐藏检查，挡住"名字不隐藏、却指向 `.env` 的链接"。
6. `serve` 要求普通文件（否则 422 `not_a_file`），`tree` 要求目录（否则 422 `not_a_directory`）。

**树的遍历**
- 用 `os.scandir`。跳过隐藏条目（Q3），以及 App 本机同一份忽略目录：`node_modules`、`.git`、`dist`、`.next`、`__pycache__`、`.cache`、`.turbo`、`coverage`、`.output`、`build`（`src/lib/files.ts:8-19`）。
- 每个条目先取真实路径：落在工作区之外的直接略去，不报错；目录用"已访问的真实路径"集合防环；文件大小取 `stat`（跟随链接）。
- 排序：目录在前，名字按不区分大小写的顺序。
- 一次响应最多 10,000 个节点，超出时停止并回 `truncated: true`（App 忽略未知字段，界面提示留待以后）。

**文件的返回**：外壳不用 `FileResponse` 自己的 Range 处理（它对空文件与超限区间的行为不合适，§2.5），按 `serve_target` 算好的区间自己流式返回。
- 用 `os.open(真实路径, O_RDONLY | O_NONBLOCK | O_NOFOLLOW)` 打开第 5 步得到的真实路径，打开与读取都放在线程里做，不在事件循环里阻塞。然后对打开的句柄 `fstat`：确认是普通文件，再以这个大小做下面的判断；不是普通文件时关掉句柄，回 422 `not_a_file`。检查之后路径若被换成 FIFO，阻塞式的 `open()` 会一直等下去，挂死整个后端；加 `O_NONBLOCK` 后它立即返回，`fstat` 再把它拒掉。被换成链接时，`O_NOFOLLOW` 让打开直接失败。
- 大小上限 `FILES_SERVE_MAX_BYTES = 64 MiB`：
  - 没有 Range：文件不超过上限 → 200 全文；超过 → 413 `file_too_large`。
  - 单段 Range（`bytes=a-b`、`bytes=a-`、`bytes=-n`）：空文件 → 忽略 Range，200 空正文；起点不小于文件大小 → 416，带 `Content-Range: bytes */<size>`；否则终点截到 `min(b, size-1, a + 上限 - 1)`，回 206。`<video>` 这类开放区间（`bytes=0-`）截到上限，不回 413。
  - 多段 Range 或格式错的 Range：忽略 Range，按"没有 Range"处理。
- 类型：`mimetypes.guess_type`，猜不到时用 `application/octet-stream`。以下一律以 `text/plain; charset=utf-8` 返回（S26）：`text/html`；`text/javascript`、`application/javascript`；除 `image/svg+xml` 以外所有 `*/xml` 与 `*+xml` 类型（`mimetypes` 会把 `.xsl`、`.xslt` 猜成 `application/xslt+xml`，`.rdf` 猜成 `application/rdf+xml`，它们都能当 XML 打开，执行 XHTML 命名空间里的脚本）。SVG 保持 `image/svg+xml`，App 只在 `<img>` 里用它。`guess_type` 返回了编码（例如 `.svgz` 得到 `('image/svg+xml', 'gzip')`）时，按 `application/octet-stream` 返回，不带 `Content-Encoding`。
- 头：`Accept-Ranges: bytes`、`X-Content-Type-Options: nosniff`、`Cache-Control: private, max-age=60`、`Content-Disposition: inline`（带 UTF-8 文件名）。App 的 serve 与 raw 代理加转发 `X-Content-Type-Options`（AR-4）。

**错误形状**：沿用 `{"detail": code}`。

**不加 `/files/browse`**：远程模式不再选目录（§3.7），`@` 提及改用树（§3.8），它没有调用方。

**契约归类**：两条路由登记进 `SERVED_PATHS`，与管理路由一样随包版本发布，不纳入 `desktop_chat` 的版本号（同 0065-Q4）。`wire_contract.py` 的模块 docstring 同步。

### 3.3 续流契约 v3（BR-3）

**帧的 `id:` 行**
- 非终止事件产生的帧，前面加一行 `id: <event.seq>`：`text`、`thinking`、`tool_output`、`tool_use`、`tool_result`、`permission_request`、真实压缩事件的 `status`、`event_omitted`。`GAP` 投影的 `event_omitted` 带 `id: <oldest - 1>`，这本身就是一个有效游标（`events.py:447-468`）；超大帧投影成的 `event_omitted` 带原事件的序号。
- 不带 `id` 的帧：`EXCHANGE_END` 产生的整组终止帧（压缩补报的 `status`、`result`、`error`、`done`）；观察流结束或被强制分离时合成的 `error`、`done`（`turn_observation.py:495-502`）；`keep_alive`。
- 游标的含义：收到 `id: N` 时，序号不超过 N 的非终止事件所对应的帧都已送达。终止组不推进游标；收到 `done` 之后不会再续流，所以 `done` 不需要 id。
- 客户端据此把不带 id 的帧（`keep_alive` 除外）先缓着，等 `done` 到了再一起提交；断线时丢掉这段缓冲，它们会随续流重发（§3.5）。
- `render_chat_sse_frame(event_type, data, *, event_id=None)` 把 `id:` 行算进 4 MiB 的上限（`_chat_sse.py:161-196`），`max_sse_frame_bytes` 的承诺保持准确。
- 终止帧的字节不变，App 的 `parseCanonicalChatTerminalFrame` 不用改。
- 序号放在 `id:` 行，没有往 JSON 包络里加键：包络"恰好两个键"是既有约定；`id:` 是 SSE 的标准字段，中间的代理也会原样转发。

**请求字段**（`turn_submission.py` 的 `decode_chat_stream_request`）
- `after_seq`：现在已经在读（`server.py:634-645`），v3 起写进公布的契约。
- `resume`：布尔，缺省 false，不是布尔 → 422 `invalid_resume`。为真时：
  - 不要求 `content`（出现也忽略），不应用 `permission_profile`；
  - 用 `interactions.turn_for(session_id, source_request_id)` 找 `turn_id`，再 `registry.handle(turn_id)`；找不到或已被淘汰 → 409 `exchange_not_retained`；
  - **从不新开 exchange**，也不排队压缩；
  - 交给观察体的 `compaction` 按 `handle.compaction_only` 决定（请求里没有内容可看）；环里游标之前已有 `COMPACTION` 事件时，接回的流不再补报 `status`；
  - `workspace` 照常检查。

  后端重启、回合被淘汰、同一个 id 先后用于 `/compact` 与普通消息（§2.5）时，续流都不会变成把消息再执行一遍。

**用量按回合累计**
- 现在每个观察体各数各的 `TURN_END`，而长回合里 `TURN_END` 也会被增量挤出环，接回的流几乎数不全。改为在 `DesktopInteractions` 里按回合累计：
  - 观察体每拉到一个 `TURN_END`，就以它的序号登记一次用量，同一序号只算一次；
  - 观察体同时登记自己拉取过的序号区间；
  - `result` 取这个回合的累计值。只有各观察体拉取过的区间合起来覆盖了 1 到结束序号、并且每次模型调用都报了用量时，`usage_reported` 才为真。
- 每个 `TURN_END` 总会被某个观察体拉到：旧观察体断开前拉到的它已经登记，断开之后的由新观察体从环里重放。只有在无人观察期间被挤出环的那部分会缺，此时 `usage_reported` 为假，这是如实的结果。
- 累计状态与请求映射同样有上限：只淘汰已终止且已不被 registry 保留的回合。

**其他**
- `observe` 抛出的 `ObserverCapacityError` 映射为 429 `too_many_observers`，App 按可重试处理。
- `/health` 的 `contracts.desktop_chat` 加 `abandon_grace_s`（数字；registry 不取消无人观察的回合时为 `null`；取自 `app.sessions.abandon_grace_s`，BR-2）。未认证的简化载荷不变。

**版本（Q1）**：推荐 `request_schema_version` 与 `sse_schema_version` 都升到 3，`interrupt_schema_version` 保持 1。依据有三条：`resume` 是新的请求语义；0064 §4.1 的规则是字段变更要加版本号、两个仓库同批改、在计划里记录；App 的 `/health` 门控是精确相等（`backend-health.ts:28-41`），v2 的 App 在见证 v3 后端的 `/health` 时就会拒绝它，反过来也一样，两个方向都显式失败。

### 3.4 可配置的宽限期（BR-2）

- `DESKTOP_FLAGS` 加 `--abandon-grace <秒>`（`_surfaces.py:1017-1020`）；`DesktopOptions.abandon_grace_s: float | None = None`，取值必须是 1 到 86,400 之间的有限数，否则 `AppConfigError`。
- `_serve_desktop` 在给了值时调用 `attach_sessions(app, abandon_grace_s=...)`；没给时不传，保持 `session.py` 的缺省 30 s。
- `SessionRegistry` 加只读属性 `abandon_grace_s`（`entry/session.py`），`/health` 从这里读，公布的就是生效的值。
- `DESKTOP_USAGE`（`_surfaces.py:287-310`）写明这个 flag：服务器发现连接断开之后，无人观察的回合还保留多久。
- 只做 flag，不加环境变量：它是 Desktop 界面自己的参数，写在启动串里一眼可见，也不用动 `entry/config.py` 的部署配置。

### 3.5 App：断线自动重连（AR-6）

重连放在 Next 路由里做：隧道断开时，浏览器到 Next 这一段并没有断，转录也在 Next 里写，浏览器不必参与。

**算法**（`api/chat/route.ts` 的读取循环，可以抽出 `lib/chat-stream-resume.ts`）
1. **记录游标**：解析时遇到 `id: N` 先暂存，处理同一帧的 `data:` 行时把游标推进到 N。
2. **终止组先缓着**：不带 id 的帧（`keep_alive` 除外）放进待提交区，收到 `done` 时一起提交（交给转录、转给浏览器、写进旁听缓冲，§3.6）。断线时丢掉待提交区。这样每帧恰好提交一次，包括断在 `error` 与 `done` 之间的情况（否则转录会追加两遍错误文本）。
3. **只把整行转给浏览器**：`processSseChunk` 已经按行切分，把完整的行重新编码后 `enqueue`，末尾不完整的那一行留在缓冲里。浏览器与转录看到同一组行，重连时丢掉半行也不会让任何一方多处理或少处理一帧。
4. **读空闲看门狗**：后端空闲时每 25 s 一帧 `keep_alive`。一次 `reader.read()` 发起后 60 s 还没有返回，就视为断开：自己 `reader.cancel()`，然后走续流。计时器在发起 read 时启动，read 返回时清除。读循环在 read 之前会先等浏览器取数据（`waitForDownstreamDemand`，`route.ts:1014`），浏览器暂时不读时 Next 本来就停着不读后端；如果从"上次收到字节"算起，这段等待会被误判为断线，白白多开一个观察者（每个回合最多 16 个）。半开连接时两端都收不到 FIN/RST，`reader.read()` 会一直挂着，看门狗是唯一能发现它的地方。
5. **触发条件**：`reader.read()` 抛出；流结束却没见到 `done`；看门狗到时。以下情况不触发：本机模式下浏览器断开或停止导致的 `reader.cancel()`（之后的 read 返回结束，会被误判为"提前结束"）；本 run 已不是当前 run。另外，最初的 `POST /chat/stream` 在拿到响应头之前出了传输错误时，也先用 `resume` 试一次（后端可能已经收下这条消息）；得到 `exchange_not_retained` 才按原来的"后端不可达"处理。
6. **每次尝试前重置**：`sseBuffer`、`terminalFrameBuffer`、暂存的 id、待提交区清空，换一个新的 `TextDecoder`。
7. **每次尝试**：先看 `connection_mode`，已切回本机模式就按 `backend_authority_changed` 放弃。然后 `resolveOperationTarget('chat', chatOperationResourceId(session_id, source_request_id))` 取目标（用当前隧道端口，并再次见证 epoch），再 `POST /chat/stream`，请求体是原请求体加 `resume: true` 与 `after_seq: 游标`。这个 POST 沿用现有的 30 s 建连保护（`createAbortSignal`，`route.ts:668-672`）：`/health` 见证通过之后隧道才死时，它不会一直挂着，超时按瞬时失败处理。
8. **退避与截止**：1、2、4、8 s，之后每 10 s 一次。截止时间 = 发现断开的时刻 + 窗口：
   - 窗口 = `abandon_grace_s − 5 s`；`abandon_grace_s` 不超过 10 s 时取它的一半；为 `null` 时取 30 min；窗口上限 30 min。
   - `abandon_grace_s` 在 `reserveOperation` 见证 `/health` 时一并取得（`witnessBackendIdentity` 多返回一个字段，`backend-fetch.ts:780-860`）；`resolveOperationTarget` 的见证路径也带回它。
   - App 发现断开的时刻，与服务器发现断开的时刻（宽限期的起点）并不相同，半开时可能差很多。所以这个截止时间只决定 App 什么时候停止重试，不代表服务器已经取消。
   - 重连期间，Next 把各个在重连的 run 里最晚的截止时间通过 `GET /api/internal/reconnect-demand` 告诉主进程，隧道据此延长重试（§3.10）。
9. **结果分类**：
   - 成功：继续读新的响应体。
   - 瞬时失败，退避后重试：网络错误；建连超时；`/health` 传输失败、非 200 或载荷格式错；隧道绑定暂时解析不出，即 `resolveActiveTunnelBinding` 的原因是 `missing`、`malformed`、`revoked` 或 `stale-server-instance`（`tunnel-binding.ts:300-331`）；429；5xx。
   - 永久失败，立即放弃：
     - `backend_process_changed`：epoch 变了，后端重启过；
     - `backend_authority_changed`：隧道绑定的原因是 `owner-mismatch` 或 `profile-revision-mismatch`；连接配置被删或 `authority_revision` 变了；绑定行变了；已切回本机模式（第 7 步）；
     - 409 `exchange_not_retained`；401；契约不兼容；工作区不符。

   现在这些都混在 409 `target_no_longer_available` 里（§2.3）。隧道绑定的问题还都从 `resolveCurrentTunnelBinding`（`backend-operation-binding.ts:110-125`）抛出同一个错误，能区分它们的只有 `resolveActiveTunnelBinding` 返回的 `reason`；切回本机模式时这个原因是 `revoked`，和隧道暂时撤销分不开，所以第 7 步另查 `connection_mode`。`resolveCurrentTunnelBinding` 把 `reason` 带出来；`resolvePersistedOperationTarget`（`backend-fetch.ts:943-1000`）与 `resolveOperationTarget`（`backend-operation-binding.ts:390-483`）据此把前两类拆成独立的错误码，HTTP 状态仍是 409，其余调用方的行为不变。
10. **重连期间点了停止**（I2）：
    - 停止登记对在途 run 不设清理计时：`markChatStreamStopped` 不再挂 30 s 的 TTL，计时改在 `finishChatStreamRun` 时才开始。重连循环也在 run 内部记下停止意图，不只依赖登记。
    - run 正在重连时（停止路由从 run 登记里看到它的连接状态，见下文"run 登记"），停止路由不去连后端，立即返回 202 `{deferred: true}`。
    - 浏览器的 `interruptChatStream` 现在把任何 `response.ok` 都当作可以本地中止（`shouldAbortLocallyFromInterruptResponse`，`chat-stream-interrupt.ts:17-23`），202 也在内，流会被立刻中止。改为先解析响应体：`deferred` 为真时既不本地中止，也撤掉 2 s 的兜底计时（`:45-54` 的计时要能撤销），并提示"连接恢复后会发送停止"；其余情况保持现状。
    - 连上之后，重连循环先发 `/chat/abort`，再接回流，收到 `error: cancelled` 与 `done`，按"已停止"落盘。
11. **重连期间的审批卡片**：卡片保持显示；这时回答会失败，卡片显示现有的错误状态，可以重试。接回的流不会再发这张卡片（游标已经越过它），连上之后再点即可。

**run 登记**（新模块 `lib/chat-run-hub.ts`，AR-6 引入，AR-7 扩充）
- 多条路由要读写同一份登记：`/api/chat`、`/api/chat/interrupt`（判断是否在重连，决定回 202）、`/api/chat/permission`、`/api/chat/sessions/[id]/live`、`/api/internal/reconnect-demand`、AR-9 的内部路由。模块级的 `Map` 在 `next dev` 下可能每条路由各拿一份实例，热重载也会把它清掉：`/live` 会永远"不在途"，202 分支永远走不到，而 live spec 就跑在 `next dev` 上。
- 所以登记挂在 `globalThis` 上，沿用仓库里跨路由状态的惯例：`chat-stream-stop-registry.ts:3, 21-25`、`chat-execution-lease.ts:11-18`、`job-event-cursor.ts:2-9`；`runtime-log.ts:4` 的注释写明这样做是为了在开发时的热重载中保留状态。键名形如 `__omicsclawChatRunHub__`。
- AR-6 引入的内容：按会话登记的 `source_request_id`、连接状态、重连截止时间、停止意图。AR-7 再加缓冲、订阅者集合、"已回答"的审批集合与落盘完成的信号（§3.6）。
- `/api/chat/permission` 只知道 `request_id`。run 每提交一张 `permission_request` 卡片，就登记 `request_id → session_id`；审批路由拿到终局回答后，靠这张表找到 run，把 id 记进它的"已回答"集合。run 注销时一并删掉这些条目。

**放弃与补读**
- 放弃时，Next 给浏览器（以及旁听的订阅者，§3.6）生成一帧 `error`（内容就是下面的落盘文案）和一帧 `done`，正常结束响应，不再用 `controller.error(err)`。这两帧只发给浏览器、写进旁听缓冲，不进转录；落盘文案由终止状态生成。
- 放弃时落盘的终止文案（取代 `Error: terminated`）：
  - 远程超时："未能在 N 分钟内重新连上服务器，这次回复在服务器上可能已被取消。"
  - 本机超时："未能在 N 分钟内重新连上本机后端，这次回复可能已被取消。"
  - 后端重启或不再保留："服务器已重启或不再保留这次回复，回复已丢失。"本机模式把"服务器"换成"本机后端"。
  - 连上时收到 `cancelled`，而用户没有点停止：显示并落盘专用文案"连接已恢复，但服务器在断线期间已经取消了这次回复"（本机模式把"服务器"换成本机后端）。如果取消是续流后的第一帧，不弹"已重新连接"；如果先重放了内容，会先弹"已重新连接"，随后再显示这条文案。实现时改成了这样（R-C 评估 d1，已接受）：超时文案说的是"未能重新连上"，和已经接上的事实矛盾。
- 补读：超时放弃后，在进程内留一个补读任务，最长 30 分钟。
  - 隧道或后端恢复（目标可以解析、`/health` 见证通过）时，试一次 `resume`，`after_seq` 取原来的游标，接着用原来的转录对象。
  - 读到终止帧，就用完整转录更新已落盘的那条消息：`persistAssistantMessage`（`route.ts:239-262`）改为返回消息 id，补读用 `existingMessageId` 更新。
  - 得到 `exchange_not_retained`、`backend_process_changed`，或同一会话开始了新回合（`beginChatStreamRun`），就撤销补读。
  - 这样做的原因：半开时服务器可能根本没开始宽限期，回合会跑完并写进后端历史。不补读的话，下一轮的上下文里有一段用户从没看到的回答。

**给浏览器的 App 内部帧**
- `{"type": "connection", "data": "{\"state\": \"reconnecting\", \"attempt\": n, \"next_retry_ms\": m, \"deadline_ms\": t}"}`。发现断开时立即发一帧（`attempt` 为 0），之后每次尝试失败再发一帧，间隔不超过 10 s，浏览器的空闲超时（330 s）不会误触发；重连成功后发 `{"state": "resumed"}`。第一次尝试就成功时，横幅只一闪而过，随后出现"已重新连接"的提示。
- 类型名 `connection` 不与后端的帧重名；转录的 `switch` 有 `default` 分支，会忽略它（`chat-stream-transcript.ts:352`）。它不进旁听缓冲（§3.6）。

**界面**（en/zh 同步）
- 流式消息上方一条横幅："与服务器的连接中断，正在重连（第 n 次）。"停止按钮保留；重连期间点停止时提示"连接恢复后会发送停止"。
- 恢复后横幅消失，另给一条 toast："已重新连接，回复继续。"
- 两个消费者都要接：`stream-session-manager.ts`（会话页），以及 `new-chat-submission.ts:57-84` 与 `chat/page.tsx` 里的回调（新会话页的第一条消息）。`useSSEStream.ts` 的 `handleSSEEvent` 加 `connection` 分支与 `onConnection` 回调。

### 3.6 App：刷新与关页后的恢复（AR-7，进程内旁听）

远程模式下，浏览器断开后 Next 的那个 run 仍在读后端，并在结束时落盘（§2.3）。恢复只需要让重开的页面旁听这个 run。它始终是唯一的后端读者、转录者与落盘者，不交接任何东西，所以不涉及租约、`runId` 或第二个转录对象。

**旁听登记**：扩充 §3.5 的 run 登记（`lib/chat-run-hub.ts`，挂在 `globalThis` 上，按会话登记）
- run 在后端接受请求之后登记。AR-6 已有 `source_request_id`、连接状态、截止时间与停止意图；AR-7 加上已提交行的缓冲、订阅者集合、已回答的审批 id 与落盘完成的信号。
- **缓冲**：run 每提交一行（§3.5 第 2、3 步的提交，不论原浏览器是否还连着）就追加一份，上限 `RUN_REPLAY_BUFFER_BYTES = 8 MiB`。超出后清空缓冲、标记 `overflowed`，之后的订阅改走后端重放（下文）。
- **订阅者**：每提交一行，也逐个 `enqueue` 给订阅者，不等订阅者读；某个订阅者积压超过 8 MiB（页面不读）时断开它，页面可以重新订阅。
- **审批**：进程内的 `/api/chat/permission` 拿到终局回答（`ok: true`，或 `expired`、`resolved`）时，经 `request_id → session_id` 表（§3.5 "run 登记"）找到 run，把 request id 记进它的"已回答"集合。
- **连接状态**：`connection` 帧不进缓冲，单独记当前状态。
- **结束**：run 落盘之后，给订阅者补完剩余的行（正常结束时以 `done` 收尾；放弃时是 §3.5 生成的 `error` 与 `done`），关闭它们，发出落盘完成的信号，然后注销。

**接口**
1. 删除 `api/chat/sessions/[id]/resume/route.ts`、`lib/session-resume.ts`、`lib/chat-resume-placeholders.ts` 与它们的测试（`sessions-resume-route.test.ts`、`chat-resume-placeholders.test.ts`）。新增 `GET /api/chat/sessions/[id]/live` → `{active, source_request_id}`，取自旁听登记。
2. `chat/[id]/page.tsx` 加载消息时一并请求 `/live`。在途、且 `stream-session-manager` 里这个会话没有活动流时，调用 `startStream({sessionId, sourceRequestId, reattach: true})`。
3. `POST /api/chat {session_id, source_request_id, reattach: true}` 是订阅，不碰后端：
   - 登记里没有这个会话、或 id 不符 → 409 `nothing_to_reattach`，页面重新加载消息（这时回合多半刚结束并已落盘）。
   - 没溢出：先发缓冲，跳过"已回答"集合里的 `permission_request` 行；正在重连时再补一帧当前的 `connection` 状态；然后跟实时尾部。
   - 不写用户消息，不初始化标题，不动停止登记、租约与 job。
4. 停止与审批：订阅页的停止按钮走现有停止路由，按 `(session, id)` 找到这个 run 的登记与后端（`interrupt/route.ts`），与原页面没有区别。回答审批也走现有路由，它的绑定在 run 处理那一帧时就建好了（`route.ts:944-953`）。

**溢出后的后端重放**
- 订阅改为自己向后端开一个只读观察：`resolveOperationTarget('chat', …)`，`POST /chat/stream {resume: true, after_seq: 0}`。只转发，不转录、不落盘、不建绑定。
- 后端的环也有上限，重放以 `event_omitted` 开头时，浏览器照现有逻辑提示"前面的输出省略了"。审批卡片由后端按"仍待决"决定是否重发，比缓冲里的"已回答"集合更准。
- 转发 `permission_request` 之前，确认它的绑定已经存在（run 已处理过这一帧），最多等 5 s。等不到就不转发这张卡片，改发一帧 `event_omitted`（`omitted_event_type: "permission_request"`，`reason: "card_not_ready"`）；浏览器为这个原因显示"有一张审批卡片暂时无法显示，刷新页面后可见"（en/zh，`lib/chat/event-omitted.ts` 加一个分支）。
- 后端发出 `done` 之后，等 run 发出落盘完成的信号再关闭订阅，最多等 60 s（run 可能正在重连，截止时间长达 30 min）。超时就以当前状态结束订阅：发出 `done` 后关闭，页面稍后读消息时再看落盘结果。
- 此时后端不可达（例如 run 正在重连）：返回 503 `reattach_unavailable`，页面稍后再请求 `/live`。

**其他情形**
- 原页面仍开着：照常收流，与订阅页互不影响。
- 缓冲里"已回答"集合之外、其实已被结算的审批（例如回答 A 时选了"本会话允许"，后端连带放行了同工具的 B）：重放后 B 的卡片出现，点击得到现有的 `resolved` 处理。这与正常会话里的表现一致。
- 本机模式：浏览器一断，run 立即停止读取并注销（0064 陷阱 18；Q4 推荐不改），`/live` 返回不在途。
- App 进程重启：登记随 Next 进程消失，重开的页面不知道后端还有回合在跑（§1.3；Q5）。
- 不加后端"列出在途回合"的路由：进程内的登记已经够用。

### 3.7 App：远程工作区固定（AR-3）

远程模式下，工作区就是远端 `GET /workspace` 的值（0064 §5.5）。各入口的处理：

| 入口 | 远程模式下的行为 |
|---|---|
| `/chat` 页初始化（`chat/page.tsx:190-211`） | 直接用 `/api/setup` 的 `defaultProject`（它刚从 `GET /workspace` 读来），不经 browse 校验；读不到时显示"无法读取服务器的工作区：<原因>"与重试按钮，不显示选择器 |
| `/chat` 页的"选择文件夹"、FolderPicker、最近项目（`:261, 277, 759`） | 不显示 |
| 侧栏"新建会话"（`ChatListPanel.tsx:311-340` 的 `resolveNewChatDirectory`） | 远程分支直接返回 `defaultProject`；为空时 toast "无法读取服务器的工作区"，不打开任何选择器 |
| 侧栏项目行 | 只在服务着的工作区那一行显示"+"；其他行的会话照常可以打开阅读 |
| 侧栏的选择器（`:284, 302-309, 1274`） | 不提供；Electron 下不再打开本机原生选择器 |
| 设置页（`OmicsClawSection.tsx:201, 242, 274, 522`） | 工作区只读显示，附一句说明："远程模式下工作区由服务器决定。要换目录，请在服务器上用新的 `--workspace` 重启 `oc desktop`。" |
| 向导的项目步骤（`ProjectStep.tsx`、`useProjectSetup.ts`） | 只读显示服务器工作区，点"继续"即记为完成（对同一目录 `PUT /api/setup`，200） |
| `switchProject`（`project-switch.ts`） | 目标与服务着的工作区相同时视为成功；不同时直接失败，给出上面那句说明，不调用 `PUT /api/setup` |
| `PUT /api/setup`（`api/setup/route.ts:285-288`） | 目录不同时返回 409 `{error, code: "remote_workspace_fixed"}`，不再透出 `workspace_change_requires_restart` |
| 错配提示（`WorkspaceMismatchNotice.tsx`） | 只显示说明，没有"切换到此项目"按钮 |
| 聊天里的错配错误（`describeWorkspaceMismatch`；`en.ts:1397-1398`） | 新增远程文案："服务器上的后端服务的是 {backend}，这个会话属于 {project}。远程模式下工作区由服务器决定：要继续这个会话，请在服务器上用 `oc desktop --workspace {project}` 重启后端，或者连接到服务该目录的后端。" |
| git 状态（`git-status-store.ts`） | 不轮询，git 相关界面隐藏 |
| quick-actions（`quick-actions/route.ts:26`） | 改读 `GET /files/tree?depth=1`，不碰笔记本磁盘 |

- 界面需要知道当前模式。现在各组件各自读 `/api/settings/app` 的 `connection_mode`；建议 `GET /api/setup` 顺带返回 `connectionMode`，新建会话的两条路径本来就在读它。实施者也可以沿用现有读法，在提交说明里写明。
- FolderPicker 在没有加载到目录时禁用 "Select This Folder"（一行，本机模式同样受益），不再出现 "empty path"。

### 3.8 App：文件查看（AR-4，排在 AR-3 之后）

- 树、预览、`serve`、`raw` 四个代理保持现在的转发方式（§2.3），对照 BR-1 核对查询参数与形状；唯一的形状变化是 `extension` 不带点。serve 与 raw 的代理在转发的头里加上 `x-content-type-options`（S26）。
- 预览代理按后端的 `detail` 给出 en/zh 文案：403 `path_outside_workspace`（"只能查看服务器工作区里的文件"）；403 隐藏路径（"这个文件被隐藏，不能在 App 里查看"）；413（"文件超过 64 MiB，远程模式下不能预览"）。404 保持 "File not found"。
- `files/browse/route.ts` 的远程分支改为返回 409 `remote_unsupported`，删掉对后端 `/files/browse` 的代理与 `files-browse-remote.test.ts`（换成"远程返回 409"的测试）。不能直接删掉远程分支：那样会落到本机分支，列出笔记本的家目录（`browse/route.ts:60-66`）。这一改动依赖 AR-3 先去掉远程模式下所有调用 browse 的入口。
- `@` 提及：`MentionPopover.tsx:31` 改读 `/api/files?dir=<工作目录>&baseDir=<工作目录>&depth=1`，两种模式都能用。`useSlashCommands.ts` 里不带 `dir` 的 `fetchFiles` 本计划不处理（§1.3，§3.13 m3）。
- 聊天里的图片（`MediaPreview`、`PlotViewer`、`message.tsx` 的路径识别）与文件卡片预览，接上 `/files/serve` 后不用改代码；相对路径由后端按工作区解析，App 代理不转发 `sessionId` 也没关系。

### 3.9 App：bearer 探测与状态文案（AR-2）

- `probe-profile.ts` 与 `runtimes/[id]/ping/route.ts` 删掉 `/env/doctor` 的第二次探测，只请求带认证头的 `/health`：
  - 401 → "认证失败：服务器拒绝了这个连接配置里的 token。请改成与服务器 `OMICSCLAW_REMOTE_AUTH_TOKEN` 相同的值。"
  - 简化载荷（`auth_required: true`，即请求没带 token）→ "服务器要求 token，这个连接配置没有设置。"
- `/api/health`：401 映射为新的原因 `auth-rejected`，与缺 token 的 `auth-required` 分开（`api/health/route.ts:170-175`；`backend-health.ts` 的 `BackendUnhealthyReason`）。状态灯对这两个原因显示"认证失败"，不再显示 "Backend Offline"。
- 陈旧注释一并改掉：`backend-health.ts:61-63`（"stale bearer answers 200 on liveness"）、`ping/route.ts:178-186`、`probe-profile.ts` 里描述 `/env/doctor` 探测的几处、`db.ts:352-355`（"oc desktop-server"）。
- token 的遮蔽（S31）：`maskToken`（`api/connections/shared.ts:13-16`）与 `settings/app/route.ts:57-64` 的 `maskValue` 用同一规则：不超过 16 个字符的 token 一律显示为 `***`，更长的只显示末 4 位。两处的 PUT 都会识别"回传的遮蔽值"以免覆盖真值，识别规则随之更新。

### 3.10 App：SSH 隧道自动重连（AR-8）

- **keepalive**：`connectConfig`（`tunnel-manager.ts:522-560`）加 `keepaliveInterval: 15_000` 与 `keepaliveCountMax: 3`。半开时约 45–60 s 发现 SSH 已死，走现有的"传输不可用"路径。
- **重连**：已经打开过的隧道因传输断开（`ssh-close`、`ssh-error`，含 keepalive 超时）失效时，状态设为 `reconnecting`，按 3、6、12、24 s 退避，之后每 30 s 重开一次。
- **重试预算**：
  - 只要 Next 里有 run 在重连，就一直重试到它们的截止时间。主进程在隧道处于 `reconnecting` 时读 `GET /api/internal/reconnect-demand` → `{until_ms}`（run 登记里各在重连的 run 的最晚截止时间，没有时为 `null`）。这条路由由 AR-6 新增；它返回 404 或请求失败时按 `null` 处理，所以 AR-8 可以先于 AR-6 落地。
  - 其余情况 15 分钟。预算用完才转为 `broken`。
  - 这样 Q2 选多长的宽限期，隧道都不会先于续流放弃。
- **不重试的错误**：认证失败、主机密钥不符、私钥文件读不到、配置错误，立即 `broken`。这类错误重试也不会好，还可能触发服务器上的 fail2ban。
- **保留监听端口**的上限（每个 Next 进程 32 个）不改。每次成功重连用掉一个，耗尽后沿用现有的"重启连接运行时"提示。
- **界面**：状态灯与提示显示"正在重连"；`broken` 时提示里给出"重新连接"按钮，调用现成的 `reconnectTunnel` IPC（`preload.ts:84`）。
- **测试**：用 `tunnel-manager.test.ts` 已有的进程内 ssh2 server，前面加一个可以暂停转发的 TCP 中继，覆盖：keepalive 发现静默的服务器；传输断开后进入 `reconnecting` 并按退避重开；认证类错误不重开；有重连需求时预算延长到截止时间，没有时 15 分钟后转为 `broken`；强制重连。调和器的纯函数测试放在 `tunnel-reconciler.test.ts`。

### 3.11 App：远程 jobs 死代码（AR-1）

- 删除 `remote-jobs-proxy.ts`、`remote-jobs-adapter.ts`、`remote-sse-adapter.ts`，以及 `api/jobs/route.ts`、`api/jobs/[id]/route.ts`、`[id]/cancel`、`[id]/retry`、`[id]/events` 里的远程分支（`isRemoteMode()` 与 `hasBackendOperationBinding('job', id)`）。jobs 路由在两种模式下都只读本地 SQLite。
- 数据库表与 `resource_kind = 'job'` 的 schema 保留（0064-Q8 的先例）。
- 测试：删除 `remote-jobs-proxy.test.ts`、`remote-jobs-adapter.test.ts`、`remote-sse-adapter.test.ts`、`jobs-routes-remote.test.ts`、`remote-wire-contract.test.ts`；`remote-wire-shape.test.ts` 删掉 jobs 部分，保留 `/health` 快照一段；`backend-operation-binding.test.ts` 里借 `remote-jobs-proxy` 测绑定的用例改用 `chat` 绑定，或者随 job 绑定一起删去；`jobs.test.ts:5`、`jobs-client.test.ts:8` 的注释改掉。
- 远程模式下仍然没有完成通知（远程聊天不建本地 job）。要不要补，见 Q6（推荐推迟）。

### 3.12 安全机制逐条算账

前提与 0064 §4.4 相同：单人使用，default 权限模式。远程只经 SSH 隧道（bearer 可选，D4）或直连（非回环地址，必须有 bearer）。DNS 重绑定是已接受风险（0064-Q4），App 的 Next API 自身的简单请求 CSRF 也是已记录的既有风险（0064 §1.2）。编号接着 0065 的 S22。

| # | 机制 | 防什么 | 旁路 | 代价与收益 | 建议 |
|---|---|---|---|---|---|
| S23 | 文件路由的真实路径限定：相对路径、`..`、绝对路径、符号链接都按真实路径判断，只放行工作区之内的 | 能调这两条路由的一方读工作区之外的文件（`/etc`、`~/.ssh`、其他项目），包括经工作区里的符号链接 | agent 自己的工具（bash、读文件，要审批）；服务器上以同一用户运行的任何进程；工作区里指向外部文件的硬链接（真实路径看不出来）；在检查与打开之间把中间某一段换成链接（要先能写工作区；最后一段换成链接时 `O_NOFOLLOW` 让打开失败，换成 FIFO 时 `O_NONBLOCK` 让它不阻塞） | 约 25 行加测试；0064-Q9⑥ 已裁定 | **做** |
| S24 | 隐藏路径（Q3） | 在 App 里意外看到或截屏到 `.env` 里的密钥；工作区是家目录时的 `~/.ssh` 等 | 同 S23：agent 与服务器进程都能读 | 选 a 约 5 行，代价是远程模式下看不到 `.omicsclaw/` 里的计划与卸载结果；理由与 0065 S12"不回显密钥"相同 | **见 Q3（推荐 a）** |
| S25 | 文件路由走 `_authorized` | 直连模式下网络上的其他人 | 无 | 零代价，沿用 S10 | **做** |
| S26 | `/files/serve` 把 HTML、JS 以及 SVG 之外的所有 XML 类（`*/xml`、`*+xml`，含 XSLT、RDF）以 `text/plain` 返回并带 `nosniff`；带编码的猜测（如 `.svgz`）按 `application/octet-stream` 返回；App 的 serve 与 raw 代理转发 `nosniff` | agent 写出的 HTML/XHTML/XSLT/JS 经 App 的 `/api/files/raw` 在 App 的源下执行，进而调用 App 自己的 `/api/*` | 本机模式的 `raw` 路由照样以 `text/html` 返回（App 侧的既有问题）；直接导航打开 SVG 时脚本仍会执行；不加 CSP `sandbox`，因为它会让 PDF 的 iframe 显示不出来 | 后端约 5 行，App 两个代理各一行；App 的 HTML 预览走文本预览路由，不受影响。收益小，代价也小 | **做** |
| S27 | 64 MiB 响应上限、1 万节点上限 | 资源保护，不算安全边界：误点一个几 GB 的文件占满整条隧道；一次树请求撑爆 Next 的 JSON 解析 | 用多次 Range 请求仍能读完大文件 | 约 15 行（含自己处理 Range） | **做** |
| S28 | SSH 隧道拓扑下 bearer 可选（D4） | — | 共享服务器上的其他操作系统用户能连 `127.0.0.1:8765`：驱动 agent、自己回答审批，也就能以后端用户的身份执行命令；文件路由没有在此之上增加暴露 | 设 token 只要一行配置；文档建议设置 | **已接受风险**（D4），文档写明 |
| S29 | token 以明文存放的位置 | — | App 的 SQLite（连接配置的 `auth_token` 与 `remote_bootstrap_command`）；写在启动命令里时，还会在 `bash -lc` 存活期间出现在服务器进程列表里 | 文档推荐：服务器侧放 `.env`（600）或 systemd 的 `EnvironmentFile`；App 侧 `auth_token` 用 `env:VAR` | **已接受**，文档写明（D5） |
| S30 | 关闭 FastAPI 的 `/docs`、`/redoc`、`/openapi.json` | 未认证地看到路由结构 | 源码公开；版本号本来就在未认证的 `/health` 里 | 一行加一条测试；安全收益约为零。"挂出的路由等于 `SERVED_PATHS`"的断言可以把这三条排除在外照样写，不需要为此关掉 Swagger | **见 Q7（推荐不做）** |
| S31 | 连接页与设置页对短 token 也遮蔽 | 页面上短 token 原样显示，被截屏 | SQLite 里本来就是明文 | 两处各两行，外加 PUT 识别遮蔽值的规则同步 | **做** |
| S32 | 只读文件路由面对跨源网页 | 本机模式没有 token 时，任意网页都能让浏览器对 `127.0.0.1:8765/files/serve` 发 GET：拿不到响应内容（没有 CORS），`<img>` 能在对方页面上显示图片，但读不到像素 | 读出内容要靠 DNS 重绑定（已接受） | 不新增防线 | **不做** |
| S33 | 续流不另设凭据：`resume` 按 `(session_id, source_request_id)` 找回合 | 猜到 id 的一方接到别人的流 | id 是 128 位随机数，只有 App 知道；知道它的一方本来就能用同一对 id 调 `/chat/abort` | 零 | **不做**额外校验 |
| S34 | `GET /api/chat/sessions/:id/live` 与 `reattach` 订阅不另设校验 | 别的调用方看到在途状态、订阅别人的流 | 同源脚本本来就能读 `/api/chat/sessions/:id/messages`、驱动 `/api/chat`；跨源网页读不到 Next API 的响应（没有 CORS）；DNS 重绑定已接受 | 零 | **不做** |
| S35 | `GET /api/internal/reconnect-demand` 不要主进程密钥 | 别的调用方读到重连截止时间 | 只是一个时间戳，不含密钥，也不能改变任何状态 | 零 | **不做** |
| S36 | `POST /api/internal/abort-active-turns` 要主进程密钥（只在 Q5 选 a 时存在） | 渲染进程脚本或网页一次中止所有在途回合 | 同源脚本知道会话与请求 id 时，本来就能逐个调 `/api/chat/interrupt`；跨源网页的简单请求只能碰运气（ids 随机） | 复用现有的 `verifyMainProcessConfirmHeader`，几行 | **做**（若 Q5 选 a） |

**不属于安全、但属于正确性的**：`resume` 从不新开 exchange（后端重启后不会把用户的消息再执行一遍）；`id:` 行、终止组缓提交、只转发整行（续流恰好一次）；续流目标经 epoch 校验（`resolveOperationTarget`，不会把请求送到另一台后端）；隧道不重试认证类错误。

### 3.13 次要项与 `/docs` 的处置

| # | 项 | 建议 | 理由 |
|---|---|---|---|
| m1 | 认证失败时状态灯写 "Backend Offline"，Ping 写 "Unreachable · HTTP 401" | **纳入** AR-2 | 与 bearer 探测是同一处代码 |
| m2 | token 错误与缺失不区分 | **纳入** AR-2 | 同上；后端本来就给出两种不同的响应 |
| m3 | `@` 提及：`MentionPopover` 在远程下 404；`useSlashCommands` 的 `fetchFiles` 不带 `dir`，两种模式都 400 | 前者**纳入** AR-4；后者**不纳入**（§1.3） | 前者一处改动就让远程的 `@` 可用；后者是两种模式共有的重复实现，另开小任务清理，记进 App `PROJECT_MEMORY` |
| m4 | quick-actions 读笔记本磁盘 | **纳入** AR-3 | 改读树路由，约 10 行；否则笔记本上恰好有同名目录时会给出错误的建议 |
| m5 | "打开助手"按钮 | **不纳入** | 任何模式下都出现不了（E3），属于死代码清理 |
| m6 | 远程模式每 10 s 轮询 git，控制台满是 409 | **纳入** AR-3 | 几行 |
| m7 | 短 token 不遮蔽（连接页与设置页） | **纳入** AR-2（S31） | 各两行 |
| m8 | `/docs`、`/redoc`、`/openapi.json` 不要认证 | **交 owner**（Q7，推荐不做） | 安全收益约为零；路由相等的断言可以排除这三条 |
| m9 | SSH 密码与带口令的私钥 | **不纳入** | ssh-agent 已覆盖带口令的私钥；存密码要新增一个密钥存储；文档写明用 ssh-agent |
| m10 | 陈旧注释（`ping/route.ts:178-186`、`backend-health.ts:61-63`、`db.ts:352-355`、App `AGENTS.md:9` 的"v2"等） | **纳入**所在任务 | 顺手改 |
| — | 后端图片与媒体帧 | **不纳入** | D2 只要求查看工作区里的图片，文件树、`/files/serve` 与聊天里的路径识别已经做到；媒体帧要改契约，另立计划 |

### 3.14 实现约定（沿用 0064 §4.11、0065 §3.12）

- **注释**：代码注释与 docstring 只写函数做什么，不写计划编号，也不写决策经过；理由写在本计划或测试的 docstring 里。提交信息可以引用计划与任务编号。
- **后端**：新模块只 import `entry` 的公开名字；`fastapi`、`starlette` 只在 `create_desktop_app` 里 import；`server.py` 继续不启用 `from __future__ import annotations`（`test_desktop_route_guard.py`）；`entry/**` 不读进程环境，docstring 里也不写 `os.environ` 这个词（`tests/entry/test_config.py:380-405`）；`launch/**` 只 import `entry` 的公开名字（`test_launch_is_above_entry.py:337-353`）。
- **App**：遵循 SPEC，直接改，不加兼容层；文案 en/zh 同步（`npm run typecheck:web` 通过即键集一致）；测试放 `src/__tests__/`；两条开发路径都要考虑；里程碑写进 `docs/PROJECT_MEMORY.md`；提交前运行 `cursor-team-kit:make-pr-easy-to-review`，环境里没有这个技能时按 `docs/agent-playbooks/`。

---

## 4. 分期与任务

### 4.1 依赖图

```
后端：BR-1（文件路由）          独立
      BR-2（宽限期）→ BR-3（契约 v3）
      BR-4（认证测试）            在 BR-1、BR-3 之后
      BR-5（后端文档）            最后
App： AR-1、AR-2、AR-3、AR-8     互不依赖，可以先做
      AR-3 → AR-4（文件查看）     真机验收要 BR-1
      AR-5（v3 门控）             与 BR-3 同批落地
      AR-5 → AR-6（断线重连）→ AR-7（刷新恢复）→（AR-9 退出时中止，仅 Q5=a）
      AR-6 与 AR-8 通过 /api/internal/reconnect-demand 衔接；该路由 404 时 AR-8 按 null 处理，所以 AR-8 不必等 AR-6
      AR-10（live spec）           在 BR-1…BR-4、AR-1…AR-7 之后
      AR-11（App 文档）            最后
```

- AR-3、AR-6、AR-7 都改 `api/chat/route.ts`、`chat/page.tsx`、`ChatListPanel.tsx` 一带，在同一工作树里按顺序提交。
- 0057 的留出集已经结束（42/42），0064 §4.9 的软约束不再生效。后端改动仍然从小，`entry/desktop/**` 与 `launch/**` 之外的文件见 §4.4。

### 4.2 后端（BR）

- **BR-1 只读文件路由**（§3.2）
  - `entry/desktop/files.py`：`resolve_in_workspace`、`file_tree`、`serve_target`（返回真实路径、媒体类型与按 Range 规则算好的区间或拒绝码）。`server.py` 加 `GET /files/tree`、`GET /files/serve`（按区间流式返回）。`SERVED_PATHS` 与 `wire_contract.py`、`server.py`、`__init__.py` 的 docstring、`DESKTOP_USAGE` 同步，`test_desktop_wire_contract.py:103-118` 里的 `SERVED_PATHS` 字面值一并改。
  - 纯函数测试 `tests/entry/test_desktop_files.py`（rapids 解释器，不 import fastapi）：相对路径；工作区内的绝对路径；`..` 越界；工作区外的绝对路径；指向外面的文件链接（403）；指向外面的目录链接（树里略去）；指向里面的链接（放行）；名字不隐藏、指向 `.env` 的链接（按 Q3）；隐藏规则（按 Q3）；忽略目录；深度；防环；节点上限与 `truncated`；`extension` 不带点；类型映射（HTML、JS、`.xsl`/`.xslt`/`.rdf` 等 `*+xml` → `text/plain`，SVG 保持原样，`.svgz` → `application/octet-stream`，未知 → `application/octet-stream`）；检查后被换成 FIFO 或链接的文件（打开不阻塞，回 422 或打开失败）；Range 规则的每个分支（无 Range 的上限、空文件忽略 Range、起点越界 416、开放区间截到上限、多段忽略）。
  - HTTP 测试（OmicsClaw 解释器，写在 `tests/entry/test_desktop_http.py`）：两条路由的状态码与形状；`Range: bytes=0-9` → 206 与 `Content-Range`；空文件带 Range → 200；超限无 Range → 413；`bytes=0-` 对超限文件 → 206、长度等于上限；`nosniff`；token 错误 → 401；设了 token 却不带头 → 401；token 正确 → 200。
- **BR-2 可配置的宽限期**（§3.4）
  - `launch/_surfaces.py`：`DESKTOP_FLAGS`、`DesktopOptions`、`_serve_desktop`、`DESKTOP_USAGE`。`entry/session.py`：`SessionRegistry.abandon_grace_s` 只读属性。
  - 测试：`tests/launch/test_surfaces.py`（`--abandon-grace 600` 落到 `abandon_grace_s`；`0`、负数、`nan`、`inf`、`86401`、非数字、缺值都被拒；`_serve_desktop` 把值交给 `attach_sessions`，用替身捕获参数；没给时不传）；`tests/entry/test_session.py`（属性等于构造参数，包括 `None`）。
- **BR-3 续流契约 v3**（§3.3）
  - `wire_contract.py`（版本 3、docstring）；`turn_submission.py`（`resume`、`invalid_resume`，`resume` 时 `content` 可缺）；`server.py`（`resume` 分支、`compaction` 按 `handle.compaction_only`、409 `exchange_not_retained`、429 `too_many_observers`、`health_payload` 公布 `abandon_grace_s`）；`turn_observation.py`（`id:` 行规则、终止组不带 id、用量改读 `DesktopInteractions` 的累计）；`interactions.py`（按回合累计用量与拉取区间，按序号去重，有上限）；`_chat_sse.py`（`event_id`）。
  - 测试：
    - `test_desktop_wire_contract.py`：版本为 3；`abandon_grace_s` 与 registry 一致（含 `null`）；`:315` 子进程探针里的 `sse_schema_version == 2` 改为 3（它断言的 `done` 字面值不变）。
    - `test_desktop_ingress.py`：v2 被拒（把现有的 v2 用例反过来）；`resume` 的解码与校验；`resume` 时 `content` 可缺。
    - `test_desktop_stream.py`：`decode()`（`:107-120`）改为接受可选的 `id:` 行，并同步 `:503-510` 的 docstring；各类帧的 `id` 规则（非终止帧带序号；终止组与合成帧、`keep_alive` 不带；`event_omitted` 的 id）；按最后一个 id 接回后，拼接的文本恰好等于完整文本；两个观察体先后观察同一回合、中间有重叠时，`result.usage` 等于不断流时的值；无人观察期间 `TURN_END` 被挤出环时 `usage_reported` 为假；接回的压缩回合不重复补报 `status`；什么都没压缩的 `/compact` 被 `resume` 接回时仍然补报 `status`。
    - `test_desktop_interactions.py`：`decode()`（`:120-121`）接受 `id:` 行；用量累计与去重、拉取区间的合并、上限与淘汰。
    - `test_desktop_http.py`：`frames_of()`（`:67-72`）接受 `id:` 行；`resume` 找不到回合 → 409；`resume` 已结束的回合补发剩余帧与 `done`；`resume` 从不新开 exchange（先 `/compact`，再用同一个 id `resume`，拿到的是那次压缩，§2.5）；观察者满 → 429。
    - `test_render.py`：`render_chat_sse_frame` 的新参数，`id:` 行计入 4 MiB 上限。
    - 真 socket 测试（uvicorn、临时端口、带 token）：流到一半断开客户端连接，用最后一个 `id` 接回，读到 `done`；拼接的文本无重无漏。
    - 其余测试里的 `ingress_schema_version: 2` 改为 3：`test_desktop_http.py:58, 83-84, 226-230`、`test_desktop_stream.py:292`、`test_desktop_interactions.py:111`、`test_desktop_ingress.py` 的 `document()`。
- **BR-4 认证与路由面**
  - 测试：
    - `test_desktop_management_http.py:53-57` 的 `test_every_served_path_is_mounted` 从"子集"改为"相等"：挂出的路由路径集合减去 FastAPI 的 `/docs`、`/docs/oauth2-redirect`、`/redoc`、`/openapi.json`，等于 `SERVED_PATHS`（Q7 选 b 时改为直接相等，并加 `/docs` 404）。
    - `test_desktop_http.py`：token 正确时，`GET /health` 回完整载荷、`HEAD /health` 200、`/chat/stream` 200 SSE、两条文件路由 200；token 错误的参数化列表加上两条文件路由；带 token 请求未知路由仍是 404（写进测试 docstring：探测 token 只能用 `/health`）。
  - 代码：只在 Q7 选 b 时改 `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)`。
- **BR-5 后端文档**（涉及的文件见 §4.4）
  - `docs/engineering/remote-execution.mdx` 重写为唯一的远程指南：拓扑（D1）；启动串与 `--abandon-grace`；sshd 的 `ClientAliveInterval` 建议与不设时的后果；token 放哪（S29）；两种启动方式（D5）；App 侧的配置；断线重连、半开连接与宽限期；只读文件查看；已接受风险（S28）；排错。
  - `docs/remote-connection-guide.md` 改成一段指向上面那页的短文；`docs/_legacy/remote-connection-guide.md` 保留历史原文，顶部加一段说明。
  - `README.md` 与 `README_zh-CN.md`：`:143`、`:151`、`:204`、`:242`（只链到新指南）、`:280`、FAQ `:358-362`，并在 What's New 加一条里程碑。`docs/ecosystem/omicsclaw-app.mdx` 的横幅与路由清单；`docs/product-overview.md:10-13` 的补注；`docs/core-features/surfaces.md` §8.1（新 flag、sshd 建议）与 §8.2（两条文件路由、`resume`、`after_seq`、`id:` 行与终止组、用量累计、v3、`abandon_grace_s`）。
  - `.env.example`：删掉 `:147` 的 "`oc desktop` refuses it"（B1-6 已解除）；§10（`:323-335`）写明 token 可以放在 `.env`，并说明 `--abandon-grace` 的用途。
  - `entry/config.py:416` 的 docstring（`oc desktop-server` 改为 `oc desktop`）：如果 0064 的 C3-4 届时还没改，在这里顺手改。
  - `OMICSCLAW.md` 不改：agent 的运行时契约不涉及远程模式。

### 4.3 App（AR）

每个任务一个提交（§4.4）。

- **AR-1 删除远程 jobs 死代码**（§3.11）。测试见 §3.11。验收：`git grep -nE "remote-jobs-proxy|remote-jobs-adapter|remote-sse-adapter|proxyListJobs|proxySubmitJob|openRemoteJobEventStream" -- src electron` 为空。
- **AR-2 bearer 探测与状态文案**（§3.9）。测试：`probe-profile.test.ts`（删掉 `:155-200`、`:496-540`、`:632-659` 一带的 `/env/doctor` 用例，改为：`/health` 401 → 认证失败；简化载荷 → 缺 token；`/health` 只请求一次）；`runtimes-ping.test.ts`（`:117`、`:633` 同理）；`health-route.test.ts`（`auth-rejected` 与 `auth-required`）；`connection-status-label.test.ts`；两处遮蔽规则与 PUT 的回传识别。验收：`git grep -n "env/doctor" -- src/lib/probe-profile.ts "src/app/api/runtimes"` 为空。
- **AR-3 远程工作区固定**（§3.7）。测试：`switchProject` 的远程分支（同一目录成功；不同目录失败且不发请求）；`resolveNewChatDirectory` 的远程分支；`PUT /api/setup` 远程换目录 → 409 `remote_workspace_fixed`；quick-actions 的远程分支读树路由（替身后端）；远程模式下 git 轮询不启动；错配文案的远程变体；FolderPicker 没有目录时禁用按钮。界面改动跑 smoke 并截图。
- **AR-4 文件查看**（§3.8，在 AR-3 之后）。测试：`files-route-remote`、`files-serve-remote`、`files-preview-remote` 对照 BR-1 的形状核对（包括 `extension`、403/413 文案、`x-content-type-options` 被转发）；`files-browse-remote.test.ts` 改为断言远程返回 409 `remote_unsupported`、不请求后端、不读本机目录；`MentionPopover` 读树路由（新增单测）。
- **AR-5 契约 v3 门控**（与 BR-3 同批）。`backend-health.ts:28-32` 的 `SUPPORTED_DESKTOP_CHAT_CONTRACT`、`chat-ingress/contract.ts:9`；`witnessBackendIdentity` 读出 `abandon_grace_s`；App `AGENTS.md:9` 的"v2"改为"v3"。测试夹具 `src/__tests__/helpers/backend-health-fixtures.ts` 与引用版本号的单测（§6 陷阱 2 给出检索命令）；`e2e/desktop-contract-v2.spec.ts` 改为 v3（文件改名）。
- **AR-6 断线自动重连**（§3.5）。测试：
  - Next 路由（替身后端，可以控制何时断开、何时停止发送字节）：断在帧中间、帧之间、`error` 与 `done` 之间；续流请求体带 `resume: true` 与正确的 `after_seq`；转录恰好一次（错误文本只追加一次）；浏览器收到的行与转录一致；看门狗只在一次 read 挂住 60 s 时触发，浏览器不读、Next 停在 `waitForDownstreamDemand` 时不触发；`connection` 帧的节奏（发现断开时立即一帧）；续流 POST 挂住时 30 s 建连保护生效，按瞬时失败重试；放弃时浏览器收到 `error` 与 `done` 两帧、响应正常结束；`backend_process_changed` → 立即放弃并落盘"服务器已重启"；409 `exchange_not_retained` 同上；`backend_authority_changed` 同上；超时 → 落盘超时文案（远程与本机两种措辞）；`abandon_grace_s` 为 `null` 与小于 10 s 时的窗口；本机模式下浏览器断开不触发重连；初次 POST 传输失败时先 `resume` 一次；补读成功时更新已落盘的消息，新回合开始时撤销补读。
  - 停止（I2）：点停止后 45 s 才恢复连接：停止登记仍在；run 仍是当前 run；恢复后先发 `/chat/abort`；终止状态为 stopped 并落盘。停止路由在 run 重连时回 202 `{deferred: true}`（从挂在 `globalThis` 上的 run 登记读连接状态）；`interruptChatStream` 收到 `deferred` 后不本地中止、撤掉 2 s 兜底，其余 2xx、404、409 的行为不变（`chat-stream-interrupt` 的单测）。
  - `backend-fetch` 与 `backend-operation-binding`：两个新错误码与仍为 `target_no_longer_available` 的各类瞬时失败；隧道绑定各个 `reason` 的归类（`missing`、`malformed`、`revoked`、`stale-server-instance` 为瞬时，`owner-mismatch`、`profile-revision-mismatch` 为 `backend_authority_changed`）；已切回本机模式时按 `backend_authority_changed` 放弃。
  - `useSSEStream`、`stream-session-manager`、`new-chat-submission`：`connection` 帧更新快照；横幅出现与消失；空闲计时被刷新。
  - `/api/internal/reconnect-demand`：返回在重连的 run 的最晚截止时间，没有时为 `null`。
  - run 登记：挂在 `globalThis` 上，两次独立 import 拿到同一份；`request_id → session_id` 表随卡片登记、随 run 注销。
- **AR-7 刷新与关页恢复**（§3.6）。测试：旁听登记（缓冲追加与 8 MiB 上限、溢出标记、订阅者积压上限、已回答审批的记录、结束时关闭订阅并发信号）；`/live` 路由；`reattach` 订阅（不碰后端、不写消息；先缓冲后实时；跳过已回答的卡片；正在重连时补发当前状态；`nothing_to_reattach`）；溢出后的后端重放（只转发；等绑定 5 s，等不到时改发 `card_not_ready` 的 `event_omitted`；等落盘信号最多 60 s，超时发 `done` 后关闭；后端不可达时 503）；run 放弃时订阅者收到 `error` 与 `done`；审批路由经 `request_id → session_id` 表记下已回答；`chat/[id]` 页在在途时发起订阅；本机模式下 `/live` 在浏览器断开后返回不在途。
- **AR-8 SSH 隧道自动重连**（§3.10）。测试见 §3.10；`ConnectionStatus` 的"正在重连"文案与"重新连接"按钮。
- **AR-9 退出时中止远程在途回合**（只在 Q5 选 a 时做）。`main.ts` 的 `shutdownBackend`（`:1452`）在停止隧道之前，远程模式下调用新的内部路由 `POST /api/internal/abort-active-turns`（要主进程密钥，S36），最多等 3 s；Next 对旁听登记里的每个在途 run 走停止流程并等它们结束。测试：密钥校验、逐个中止与等待；`main.ts` 中的调用顺序按现有的主进程测试方式覆盖。
- **AR-10 live 远程 spec**（§5.3）。依赖 BR-1…BR-4 与 AR-1…AR-7（c–e 要 AR-4，j 要 AR-2，f、g、m、o 要 AR-6，h 要 AR-7）。
- **AR-11 App 文档**
  - `README.md`：`:157-158` 的通知说明（远程模式下没有完成通知）；`:208-238` 的远程聊天、jobs、文件树与图片几段，改为现状。
  - `docs/LOCAL_SETUP_GUIDE.md`（`:333-353`、`:387`、排错）与 `docs/LOCAL_SETUP_GUIDE_zh.md`（`:295-310`、`:341`、`:430-434`）的远程一节：启动串、`--abandon-grace`、sshd 的 `ClientAliveInterval`、token 的位置与明文说明、断线重连与半开时的表现、只有远程模式支持刷新恢复。
  - `docs/PROJECT_MEMORY.md`：每个任务一条里程碑，写进 §2.6 的更正与已接受风险。
  - `playwright.live.config.ts` 头注释补上远程 spec 的运行方式；`AGENTS.md` 只在"对真实后端跑端到端"那句后面补一句远程 spec 在哪里（`:9` 的版本号由 AR-5 改）。

### 4.4 交付与提交

**后端**
- 按 owner 的提交策略，0064、0065 与本计划的后端改动都先不提交，等 0056–0060 系列完成后统一提交，除非 owner 另有指示。
- `entry/desktop/**` 与 `launch/**` 之外会动到的文件：
  - `omicsclaw/entry/session.py`：加 `SessionRegistry.abandon_grace_s` 只读属性（BR-2），让 `/health` 公布实际生效的值；
  - `omicsclaw/entry/config.py`：只改 `:416` 的 docstring（BR-5，条件见上）；
  - `.env.example`：`:147` 与 §10 的说明（BR-5）；
  - `tests/**`：BR-1 到 BR-4 列出的测试；
  - 文档：`README.md`、`README_zh-CN.md`、`docs/engineering/remote-execution.mdx`、`docs/remote-connection-guide.md`、`docs/_legacy/remote-connection-guide.md`、`docs/ecosystem/omicsclaw-app.mdx`、`docs/product-overview.md`、`docs/core-features/surfaces.md`。
- 不动 `entry/stream.py`、`entry/turn.py`、`entry/events.py`：续流只用它们的公开 API，即 `observe`、`ObserverCapacityError`，以及判断压缩事件是否已经送达时读的 `handle.stream.retained()`。用量的按回合累计写在 `entry/desktop/interactions.py` 里（§3.3），不涉及这三个文件。

**App**
- 直接提交到本地 `main`，每个任务一个提交，作者 `zhou-1314 <zhouwg1314@gmail.com>`：`git -c user.name=zhou-1314 -c user.email=zhouwg1314@gmail.com commit ...`。
- 提交信息用 conventional commits，**不加任何 Claude 共同作者行**。
- 只在 owner 明确要求时 push。

---

## 5. 测试与验收

### 5.1 后端

| 用途 | 解释器 | 命令 |
|---|---|---|
| 要 fastapi 的测试 | `/opt/conda/envs/OmicsClaw/bin/python` | `PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:cacheprovider -p no:randomly tests/entry/test_desktop_http.py tests/entry/test_desktop_management_http.py tests/entry/test_desktop_wire_contract.py tests/entry/test_desktop_stream.py tests/entry/test_desktop_ingress.py tests/entry/test_render.py` |
| 纯 Python 测试 | `/opt/conda/envs/rapids_singlecell/bin/python` | `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly tests/entry/test_desktop_files.py tests/entry/test_desktop_interactions.py tests/entry/test_session.py tests/launch/test_surfaces.py tests/launch/test_launch_is_above_entry.py tests/entry/test_entry_is_the_top_layer.py tests/entry/test_desktop_route_guard.py "tests/entry/test_config.py::test_no_entry_module_reads_the_environment"` |

- rapids 环境没有 fastapi，会把 `test_desktop_http.py` 整份静默跳过，HTTP 测试的结果只能在 OmicsClaw 解释器下看（0064 陷阱 1）。
- 只跑新增的与直接相关的测试，**不要反复跑全量**（owner 的要求）。与本计划无关的既有失败见 0064 §6.1。
- 新的纯函数测试文件不得 import fastapi。

### 5.2 App

**环境**
- `node_modules` 是指向 `/tmp/0064-app-run/node_modules` 的符号链接；运行副本是 `/tmp/0064-app-run`，改动后用 `/tmp/sync-app.sh` 同步。副本被清掉时要 `npm ci`（要联网，先问 owner）。
- 起 dev 服务器：在 `/tmp/0064-app-run` 下执行 `env -u NODE_OPTIONS node scripts/run-next-with-build-env.mjs next dev -p 3000 -H 127.0.0.1`（`npm run dev` 会先跑本机原生模块检查）。
- 容器里没有 `ss`，查端口用 `netstat`。
- 冷启动后先 `curl http://127.0.0.1:3000/api/ready` 预热，再跑 Playwright；否则 `webServer` 会另起一个 dev 服务器，覆盖 `.next`。
- 后端端口不是 8765 时，dev 服务器与 Playwright 进程都要带 `OMICSCLAW_BACKEND_PORT`（`playwright.live.config.ts` 头注释）。

**命令**
1. `npm run typecheck`（其中的 `typecheck:web` 也检查 en/zh 键集）。
2. 对改动的文件 `npx eslint <files>`。
3. 相关单测：`npx tsx --import ./src/__tests__/setup/jsdom-setup.ts --test <files>`。
4. 界面有改动的任务跑 `npm run test:smoke` 并截图。

### 5.3 live 远程 spec（AR-10，浏览器路径）

新文件 `src/__tests__/e2e/live-backend-remote.spec.ts`。文件名必须以 `live-backend-` 开头，`playwright.live.config.ts` 才会收集；只在 `OMICSCLAW_LIVE_REMOTE=1` 时运行。

**准备**（写进 spec 头注释；要 root；后端与 Next 各在一个终端里前台运行）

```bash
# 1. 服务器侧：工作区放在另一个 uid 所有的 0700 目录下
install -d -m 0700 -o 65534 /tmp/r66/hidden
mkdir -p /tmp/r66/hidden/ws/{data,fig}
#    放入 data/a.csv、fig/umap.png、fig/report.pdf、.env（假密钥）、
#    一个指向 /etc/hostname 的链接、一个指向 data/ 的链接
cd /tmp/r66/hidden/ws && OMICSCLAW_REMOTE_AUTH_TOKEN=r66-token \
  OMICSCLAW_DIR=/workspace/dataset/private/zhouwg_data/OmicsClaw \
  OMICSCLAW_SKILLS_DIR=/workspace/dataset/private/zhouwg_data/OmicsClaw/skills \
  /opt/conda/envs/OmicsClaw/bin/python -m omicsclaw desktop --workspace /tmp/r66/hidden/ws \
  -- --port 18765 --abandon-grace 20
# 2. 笔记本侧：Next 去掉读目录的特权，读不到服务器工作区
cd /tmp/0064-app-run && OMICSCLAW_DATA_DIR=/tmp/r66/appdata env -u NODE_OPTIONS \
  setpriv --bounding-set -dac_override,-dac_read_search -- \
  node scripts/run-next-with-build-env.mjs next dev -p 3000 -H 127.0.0.1
curl -s http://127.0.0.1:3000/api/ready
# 3. 隔离的前提检查：必须失败（Permission denied）
setpriv --bounding-set -dac_override,-dac_read_search -- ls /tmp/r66/hidden/ws
# 4. 运行
OMICSCLAW_LIVE_BACKEND=1 OMICSCLAW_LIVE_REMOTE=1 OMICSCLAW_LIVE_REMOTE_TOKEN=r66-token \
  OMICSCLAW_LIVE_WORKSPACE=/tmp/r66/hidden/ws \
  npx playwright test -c playwright.live.config.ts live-backend-remote.spec.ts
```

- spec 在进程内起一个 Node TCP 代理（18766 → 18765），模拟隧道：
  - `cut()`：销毁所有连接并停止监听（干净断开，两端都收到 FIN/RST）；
  - `freeze()`：已有连接停止转发但不关闭，新连接照常转发（半开，只有看门狗能发现）；
  - `restore()`：恢复监听与转发。
- 连接配置的 URL 用 `http://127.0.0.1:18766`，token 用 `r66-token`。这里走直连 URL，隧道换端口、按绑定重建目标的路径只由单测（AR-6、AR-8）与 §5.4 覆盖。
- 进入远程模式的步骤照 §2.4。主进程密钥每个 Next 进程只给一次：spec 在 `beforeAll` 里取；已被取走时读 `OMICSCLAW_LIVE_MAIN_SECRET`。所以要在全新的 Next 进程上先跑这份 spec。
- `--abandon-grace 20` 让"超过宽限期"那一步在 30 s 内结束。
- 服务器侧的文件由 root 准备，Next 读不到它们，界面上出现的内容只可能来自后端。

| # | 操作 | 断言 |
|---|---|---|
| a | 激活后打开 App | 状态灯为已连接；Ping 成功；代理记录的每个后端请求都带 bearer |
| b | 在 `/chat` 页发"只回复 OK"；侧栏"新建会话"；服务着的项目行"+" | 都不出现选择器；三处新建的会话都能对话；页面上没有"最近项目"切换 |
| c | 打开文件树 | 列出 `data/`、`fig/` 与指向 `data/` 的链接；不列 `.env`（Q3-a）；指向 `/etc/hostname` 的链接不出现；`a.csv` 预览成表格；`umap.png` 在图片查看器里显示；`report.pdf` 在 iframe 里显示 |
| d | 直接请求 `/api/files/serve?path=../../etc/passwd`、`?path=/etc/hostname`、`?path=.env` | 都是 403，并显示对应的文案（`.env` 一项按 Q3 的裁定）；响应带 `X-Content-Type-Options: nosniff` |
| e | 让 agent 用写入工具写 `out.txt`（审批后） | 文件卡片的"打开预览"显示内容；文件树刷新后出现 `out.txt` |
| f | 让 agent 连续输出长文本，其间 `cut()` 10 s 再 `restore()` | 出现"正在重连"横幅；恢复后回复继续；完成后浏览器显示的文本与刷新后落盘的文本一致，没有重复片段；再用后端解释器只读打开 `.omicsclaw/memory.db` 核对后端记下的回复（做法同 `/tmp/remote-check/backend-history.py`） |
| g | 跑 `sleep 60` 时 `cut()` 30 s（超过 20 s 宽限） | 显示"未能在 N 分钟内重新连上服务器，这次回复在服务器上可能已被取消"；刷新后落盘的是同一句话 |
| h | 审批卡片待决时刷新页面；再用新标签页打开同一会话 | 两次都看到卡片与停止按钮；点"允许一次"后回合完成；落盘的回复从头到尾完整（与 f 同样的核对） |
| i | 在绑定别的目录的会话里发送；调用 `PUT /api/setup` 换目录 | 前者给出远程文案，没有"切换到此项目"按钮；后者 409 `remote_workspace_fixed` |
| j | 把连接配置的 token 改错后 Ping；清空 token 后 Ping | 分别显示"认证失败"与"服务器要求 token"；状态灯不显示 "Backend Offline" |
| k | 远程模式下停留 30 s | 没有 `/api/git/status` 请求；quick-actions 的建议来自服务器文件（有 `.csv` 时出现差异表达的建议） |
| l | 后端换成只支持 v2 的桩 | 见证 `/health` 时就提示版本不兼容（沿用 `desktop-contract-v3.spec.ts` 的桩） |
| m | 长回合中 `cut()`，断开期间重启后端（换一个进程），再 `restore()` | 显示"服务器已重启或不再保留这次回复，回复已丢失"，不再重试 |
| n | 审批卡片出现后 `cut()`，断开期间点"允许一次"，恢复后再点 | 第一次显示现有的错误状态；恢复后再点成功，回合完成 |
| o | 长回合中 `freeze()` 90 s | 约 60 s 后看门狗触发："正在重连"横幅出现（第一次尝试就成功时只一闪而过），随后出现"已重新连接"的提示；经新连接接回，回复继续且没有重复 |

### 5.4 owner 机器上的 Electron 验收清单

这个容器里没有显示器（也没有 xvfb），Electron 部分在 owner 的机器上做。

1. **手动启动**：在服务器上按 §3.1 的启动串（tmux），带与不带 token 各启动一次；App 里新建 SSH 连接配置（`~/.ssh/config` 别名，私钥或 ssh-agent），激活后状态灯为已连接。
2. **自动启动**：停掉服务器上的后端，连接配置填 `remote_bootstrap_command`（§3.1 的示例），激活：15 s 内连上；临时 SSH 会话关闭后，`ps` 仍能看到 `oc desktop`；记下服务器冷缓存下的启动耗时。
3. **对话闭环**：对话、审批、停止；在 `/chat` 页、侧栏、项目行"+"新建会话都不弹选择器，尤其不弹本机原生选择器；向导与设置页只读显示服务器工作区；Providers 页只读。
4. **文件**：文件树；CSV、Markdown、JSON 预览；PNG；PDF；agent 写出文件的卡片。
5. **干净断开**：长回合进行中，在服务器上找到这条隧道对应的 sshd 子进程并 `kill` 它。隧道会话没有终端，用 `pgrep -af 'sshd: .*@notty'` 列出候选；有多个时用 `sudo ss -tnp | grep <笔记本IP>` 按对端地址确认 PID。不要用 `grep 'sshd: <用户>'`，它也会匹配 owner 自己的交互会话。预期：隧道立即进入"正在重连"并重开；聊天里出现横幅，随后接回，没有重复。
6. **半开断开**（丢包，不发 FIN/RST）：
   - macOS：`printf 'block drop quick proto tcp from any to <服务器IP> port 22\nblock drop quick proto tcp from <服务器IP> port 22 to any\n' | sudo pfctl -a com.apple/oc66 -f -`，再 `sudo pfctl -E`（记下它输出的 token）；恢复时 `sudo pfctl -a com.apple/oc66 -F rules`、`sudo pfctl -X <token>`。两个方向都丢，才不会有一侧收到回包。
   - Linux：`sudo iptables -I OUTPUT -p tcp -d <服务器IP> --dport 22 -j DROP` 与 `sudo iptables -I INPUT -p tcp -s <服务器IP> --sport 22 -j DROP`；恢复时把两条的 `-I` 换成 `-D` 再各执行一次。
   - 丢包 90 s 后恢复：约 60 s 内聊天里出现横幅（看门狗），隧道在 keepalive 超时后进入"正在重连"；恢复后隧道重开，回复接着流，没有重复。
   - 丢包 20 s 后恢复（短于看门狗与 keepalive 的阈值，即"TCP 自愈"）：不出现横幅，或者只短暂出现；TCP 重传后回复继续，没有重复，也不会发起重连。
7. **超过宽限期**：服务器 sshd 已按 §3.1 设了 `ClientAliveInterval 30`、`ClientAliveCountMax 3`，后端用 `--abandon-grace 60` 启动。丢包 4 分钟：App 显示"可能已被取消"的文案；恢复后补读得到 `cancelled` 或 409，消息保持原样。再做一次 sshd 不设 `ClientAlive*` 的对照：回合在服务器上跑完；恢复后补读把完整回复写回这条消息。
8. **刷新**：审批待决时按 Cmd+R：卡片回来，"允许"有效，落盘完整。
9. **退出**：回合进行中从托盘退出，重开 App 后在同一会话发送新消息。Q5 选 b 时，新消息排在旧回合后面，直到宽限期满（记下等待时间）；选 a 时，服务器日志里有 `/chat/abort`，新消息立即开始。无论选哪项，5 分钟内被拒都是 §6 陷阱 13 的实例，记下来。
10. **后台通知**：Q6 选 b 时确认远程模式下没有完成通知，也没有报错；选 a 时窗口隐藏到托盘、回合完成时弹出系统通知，点击回到该会话。
11. **token**：把连接配置的 token 改错 → "认证失败"；服务器换了主机密钥 → 现有的 TOFU 提示。
12. 截图存档，结果写进 App `PROJECT_MEMORY`。

### 5.5 验收标准

- **R-A**：§5.3 的 a–e、i–k 通过；BR-1 的测试通过；AR-1、AR-2 的 `git grep` 验收为空；G1、G2、G5、G6 成立。
- **R-B**：§5.3 的 f–h、l–o 通过；BR-2、BR-3、BR-4 的测试通过（包括真 socket 续流）；AR-6、AR-7、AR-8 的单测通过（包括 45 s 停止用例与进程内 ssh2 server 用例）；G3、G4 成立。
- **R-C**：§5.4 全部通过；文档已更新（G7）。

---

## 6. 陷阱与风险

1. **只在一个解释器下看得见的缺陷**：`test_desktop_http.py` 在 rapids 下整份被跳过。
2. **契约 v3 必须两边同批**：只落了 BR-3，App 在见证 `/health` 时就拒绝后端；只落了 AR-5，App 拒绝 v2 的后端。两者在同一次工作里先后完成，中间不做真机验证。App 侧要改的版本字面值在 `backend-health.ts`、`chat-ingress/contract.ts`、测试夹具 `backend-health-fixtures.ts`，以及 `git grep -ln "sse_schema_version\|ingress_schema_version\|SUPPORTED_DESKTOP_CHAT_CONTRACT" -- src/__tests__` 列出的 18 个文件（含 `desktop-contract-v2.spec.ts`）。
3. **续流不能靠重投**：同一个 id 先后用于 `/compact` 与普通消息时，重投会新开 exchange（§2.5）。续流一律带 `resume: true`。
4. **id 与提交规则**：非终止帧带 id，终止组与 `keep_alive`、合成帧不带；客户端在处理 `data:` 行时推进游标；不带 id 的帧等 `done` 再提交，断线时丢掉。任何一条做错，续流都会多一帧或少一帧（例如错误文本追加两遍）。
5. **半开连接**：关 Wi‑Fi、休眠、换网时两端通常收不到 FIN/RST。App 靠 60 s 看门狗与 ssh2 keepalive 发现；服务器要靠 sshd 的 `ClientAliveInterval` 发现，没设时旧观察者一直挂着，宽限期不开始，有待决审批的会话会被卡很久。live spec 的 `cut()` 只测到干净断开，`freeze()` 测看门狗，服务器那一侧只有 §5.4 第 7 项能验。
6. **半行**：Next 把半行字节转给浏览器的话，重连后浏览器会多显示一帧，转录却不会，所以只转发整行。
7. **`target_no_longer_available` 的来源很多**：`/health` 传输失败、非 200、格式错，隧道没发布，epoch 变了，连接配置被删或改过，绑定行变了。不拆开，重连要么在后端重启后空等到超时，要么在隧道短暂不可用时过早放弃（AR-6 加 `backend_process_changed`、`backend_authority_changed`）。
8. **停止登记的 TTL**：现在 `markChatStreamStopped` 30 s 后清掉登记，重连中的 run 会因此悄悄退役、不发 `/chat/abort`、不落盘，后端回合跑到宽限期满（§3.5 第 10 步）。
9. **旁听缓冲的上限**：8 MiB 装得下绝大多数回合；有几个大工具结果的回合会溢出，之后的订阅改走后端重放，屏幕上前面的输出可能缺一段（有提示），落盘内容不受影响。
10. **旁听重放里的审批卡片**：App 只知道自己路由回答过的审批；被"本会话允许"连带结算的，重放后仍会出卡片，点击得到现有的 `resolved` 处理。
11. **滞留的观察者**：服务器端发现旧连接已断之前，旧观察者一直挂着。一个回合最多 16 个观察者，满了返回 429，App 按可重试处理。
12. **每次隧道重连用掉一个保留端口**：每个 Next 进程最多 32 个，网络反复抖动一整天可能耗尽，这时按现有提示重启连接运行时。
13. **App 崩溃后同一会话最多 5 分钟不能发送**：租约行属于已退出的 owner，过期之前新进程拿不到（`chat-execution-lease.ts:75-110`）。这是既有问题，本计划不改。
14. **宽限期过后才连上**：后端补发 `error: cancelled`。用户没有点停止时，这个 `cancelled` 不映射为"已停止"，App 显示并落盘"断线期间已被服务器取消"的专用文案（§3.5；原计划写的是超时文案，R-C 评估 d1 改为专用文案）。
15. **App 放弃不等于服务器取消**：两者发现断开的时刻不同，半开时可能相差很多。文案因此写"可能已被取消"，并靠补读把服务器后来跑完的回复写回。
16. **主进程密钥只给一次**：live spec 要在全新的 Next 进程上先跑，或者从环境变量传入。
17. **文件系统隔离要 root**：owner 的机器上不做 `setpriv` 隔离，改在 Electron 清单里确认界面内容来自服务器。
18. **`OMICSCLAW_SKILLS_DIR`**：远端工作区不是检出目录时技能数为 0，启动串要带上。
19. **token 放 `.env` 时的优先级**：已导出的同名变量优先于 `.env`（`_adopt_dotenv` 用 `override=False`）。
20. **Providers 页在远程模式下只读**（0065-Q5）：`PUT /providers` 会改服务器的 `.env`，而 App 没法重启远端后端。
21. **遮蔽规则改了，回传识别也要改**：两处 PUT 靠识别"遮蔽过的值"来避免用 `***…` 覆盖真值，规则不同步会把 token 写坏。
22. **Range 与 `FileResponse`**：Starlette 对空文件带 Range 回 416，预览又总带 Range，所以外壳要自己处理区间（§3.2）。
23. **进程内登记要挂在 `globalThis` 上**：模块级的 `Map` 在 `next dev` 下可能每条路由各一份，热重载也会清掉，`/live` 与停止路由的 202 分支会悄悄失效，而 live spec 正是在 `next dev` 上跑（§3.5 "run 登记"）。
24. **打开文件不能阻塞事件循环**：检查之后路径被换成 FIFO 时，阻塞式 `open()` 会一直等，整个后端跟着卡住；所以用 `O_NONBLOCK` 并在线程里打开（§3.2）。
25. **看门狗的计时起点**：从"上次收到字节"算起会把浏览器暂时不读的时间也算进去，误判断线并多开观察者；计时只覆盖一次 read 本身（§3.5 第 4 步）。

---

## 7. 待 owner 裁定的问题

| # | 问题 | 选项 | 推荐与理由 |
|---|---|---|---|
| Q1 | `resume`、帧 id、`abandon_grace_s` 进入契约时，版本号怎么处理 | **a** `request_schema_version`、`sse_schema_version` 都升到 3，两边门控随之改。<br>**b** 并入 v2。前提要说清：App 的 v2 已经推送（`df525b3` 在 `origin/main`），后端的 v2 还没提交。b 省掉后端 5 个测试文件与 App 18 个测试文件里的版本字面值，代价是在 App 已发布 v2 之后改变 v2 的含义：新 App 依赖 `resume`，而同样宣称 v2 的旧后端（本机工作树里改动之前的版本）不认识它，重发会新开 exchange，把消息再执行一遍。公开历史里会有两份内容不同的"v2"。<br>**c** 保持 v2，另加能力标志（如 `stream_resume: true`），App 按标志决定是否续流 | **a**。`resume` 是新的请求语义；0064 §4.1 的规则是字段一变就加版本号、两边同批改；App 的门控是精确相等，版本不符在见证 `/health` 时就显式拒绝，两个方向都一样。c 要 App 同时支持两种行为，等于兼容层，App 的 SPEC 不允许 |
| Q2 | 远程启动串推荐的宽限期 | **a** 600 s；**b** 300 s；**c** 1800 s。本机缺省都保持 30 s | **a**。要覆盖切换 Wi-Fi、VPN 重连、笔记本合盖几分钟这类断线。代价：服务器发现断开之后，无人观察的回合还要跑这么久，同一会话的新消息也要排在它后面，包括 App 退出或崩溃之后（Q5 选 b 时）。半开时宽限期要等 sshd 发现断开才开始：按 §3.1 设了 `ClientAlive*` 约多 90 s，没设时可能多出几十分钟以上 |
| Q3 | 文件路由隐藏哪些路径 | **a** 隐藏并拒绝任何以 `.` 开头的路径段：树里不列，`serve` 返回 403。<br>**b** 只隐藏并拒绝 `.env` 与 `.env.*`，与 0065 S12 同一理由的最小规则。<br>**c** 不隐藏；App 本机文件树隐藏点文件但保留 `.env*`，c 比它还宽 | **a**。一条规则，不用维护名单；只看每段的首字符是不是点，不受大小写与 Unicode 规范化影响（b 的名单在大小写不敏感的文件系统上可以用 `.ENV` 绕过，例如后端跑在 macOS 上）；挡住 `.env`，工作区是家目录时也挡住 `~/.ssh`。代价是远程模式下看不到 `.omicsclaw/` 里的计划与卸载的工具结果：计划在待办面板里有，大输出可以让 agent 去读。c 会把 API 密钥显示在预览里，与 S12 的做法相悖 |
| Q4 | 本机模式下浏览器断开时，Next 是否继续读后端（让刷新恢复在本机也能用） | **a** 改：去掉 `api/chat/route.ts` 中 `:672`、`:1006`、`:1015`、`:1036`、`:1257` 的 `!remoteChat` 条件，`:1053`、`:1138` 的 `detachedRemoteStream` 不看模式。副作用：改变本机模式"浏览器断开即停止"的语义（0064 陷阱 18）；`npm run dev` 下关掉标签页后，本机回合会跑完并落盘，不再在 30 s 后被取消；`chat-route-*` 里断定"本机断开即取消"的用例要改。<br>**b** 不改，本计划只在远程模式下提供刷新恢复 | **b**，另立小计划（§1.3）。D1–D6 没有要求它，它改变的是本机模式的既定语义 |
| Q5 | App 退出或崩溃时仍在跑的远程回合 | **a** 退出时尽力中止：Electron 的 `shutdownBackend` 先调 `POST /api/internal/abort-active-turns`（主进程密钥，S36），最多等 3 s（AR-9）；崩溃不处理。<br>**b** 不加代码：回合在服务器发现断开、宽限期满之后被取消，这期间同一会话的新消息排在它后面。这完全符合 D1–D6，副作用由宽限期的长短决定。<br>**c** 重启后接管：持久化在途记录（或后端加一条列出在途回合的路由），并处理已退出的 owner 留下的租约 | **b**。a 缓解的是宽限期变长的副作用，D1–D6 并没有要求它；用户退出前可以先点停止，Q2 也可以选短一些。§5.4 第 9 项量出等待时间后，owner 觉得不可接受再做 a（约 30 行加一个内部路由）。c 要动租约与持久化，另立计划 |
| Q6 | 远程模式的聊天回合是否写入本地 jobs 表，让完成通知在远程模式下也能工作 | **a** 写入：去掉 `api/chat/route.ts:640` 的 `!remoteChat` 条件。副作用：远程聊天会作为 job 行写进 jobs 表，出现在 `JobInlineCard` 与 jobs 列表里；对这些 job 点取消只改本地状态，不会停止服务器上的回合（`api/jobs/[id]/cancel/route.ts:21-35`），用户可能以为已经停了。<br>**b** 不写，远程模式下没有完成通知，文档写明 | **b**，推迟（§1.3）。D2 没有要求完成通知；a 还要先解决"取消 job 不停回合"的误导 |
| Q7 | 是否关闭 FastAPI 自带的 `/docs`、`/redoc`、`/openapi.json` | **a** 保留：路由相等的断言排除这三条（BR-4）。<br>**b** 关闭：一行加一条测试 | **a**。它们只暴露路由结构，源码本来就公开，版本号也已在未认证的 `/health` 里；关掉的安全收益约为零，还让开发者少了一个自查接口（S30）。按"更严不作为缺省推荐"，推荐保留 |

**owner 裁定（2026-09-29）**：全部按推荐。Q1 = a，Q2 = a（600 s），Q3 = a，Q4 = b，Q5 = b（AR-9 不做），Q6 = b，Q7 = a。

**不需要 owner 裁定、在本计划内直接决定的**（审核时可以提出异议）
- 序号放在 SSE `id:` 行，不放进 JSON 包络；终止组的帧不带 id，客户端等 `done` 再提交它们（§3.3）。
- 用量在 `DesktopInteractions` 里按回合累计，以 `TURN_END` 的序号去重（§3.3）。
- 宽限期只做界面 flag `--abandon-grace`，取值 1–86,400 s，不加环境变量（§3.4）。
- 文件路由沿用旧后端的形状，只把 `extension` 改为不带点；不纳入 `desktop_chat` 版本（同 0065-Q4）。
- 不加 `/files/browse`；远程模式下 App 的 browse 返回 409；不加列出在途回合的后端路由。
- 64 MiB 响应上限、1 万节点上限；外壳自己处理 Range；HTML/XHTML/XML/JS 以 `text/plain` 返回。
- 断线重连放在 Next 路由里做；60 s 读空闲看门狗；截止窗口按 §3.5 第 8 步；放弃后补读一次，最长 30 分钟。
- 刷新恢复用进程内旁听，缓冲 8 MiB，溢出后改走后端重放。
- run 登记挂在 `globalThis` 上；溢出重放等绑定 5 s、等落盘 60 s；打开文件用 `O_NONBLOCK` 与 `O_NOFOLLOW`。
- 隧道 keepalive 15 s × 3；重试预算跟随重连截止时间，否则 15 分钟；认证类错误不重试（§3.10）。
- 不做后端图片与媒体帧；不支持 SSH 密码。

---

## 8. 与其他计划的关系

| 计划或 ADR | 关系 |
|---|---|
| **0064** | 本计划就是它 §5.5 的后续计划 R，沿用那里的约束；§2.7 最后一行（远程 jobs 面板、文件树）在这里收口；§4.1 的版本规则是 Q1 推荐的依据；陷阱 26（未知路由先 404）在这里处理；陷阱 18（本机断开即取消）按 Q4 推荐保持不变 |
| **0065** | 沿用 0065-Q4（管理路由不纳入版本）、0065-Q5（远程 Providers 只读），Q3 的推荐沿用 S12 的理由；AD-12 留下的 `remote-jobs-*`、`remote-sse-adapter` 由 AR-1 删除，`remote-proxy-bootstrap` 保留 |
| **0031** | 陷阱 9（最后一个观察者离开才算放弃）与 Q14（观察与身份分离）是续流的基础；本计划只把宽限期做成可配置并公布 |
| **0037** | 遵守 `launch` 在 `entry` 之上、环境只在登记过的地方读 |
| **0057** | 留出集已结束，0064 §4.9 的软约束不再生效；不修改 0057 的任何文件 |
| **App ADR-0004** | 类比：远程模式下换工作区等于在服务器上重启后端，App 不代劳 |

---

## 附录 A：证据索引（后端以 2026-09-29 工作树为准，App 以 `da509cd` 为准）

**后端**

| 文件 | 行号与内容 |
|---|---|
| `entry/desktop/server.py` | `:148-242` `open_chat_stream`（`:188-196` 工作区检查，`:217` `turn_for`，`:227` `observe`）；`:260-293` `health_payload`；`:296-311` 简化载荷；`:322-341` `change_workspace`；`:371-631` `create_desktop_app`（`:407` `FastAPI(...)`，`:410-417` `_authorized`，`:425-428` `_require_json`，`:623-629` `/health`）；`:634-645` `_after_seq` |
| `entry/desktop/turn_observation.py` | `:1-42` 帧的说明；`:70` `KEEPALIVE_INTERVAL_S`；`:161-174` `_identity`；`:177-244` `desktop_chat_frame`；`:247-267` 终止帧；`:308-356` 构造；`:367-410` `__anext__`（`:395-405` 不出帧的事件）；`:495-502` 合成帧 |
| `entry/desktop/_chat_sse.py` | `:44-56` `_raw_frame`；`:161-196` `render_chat_sse_frame` |
| `entry/desktop/turn_submission.py` | `:184-235` `ChatStreamRequest`；`:257-329` `decode_chat_stream_request` |
| `entry/desktop/wire_contract.py` | `:1-29` docstring；`:37-39` 版本；`:42-56` `SERVED_PATHS`；`:67-89` `desktop_chat_contract` |
| `entry/desktop/interactions.py` | `:141-166` 请求映射；`:241-266` `admit_approval` |
| `entry/session.py` | `:91-108` `DEFAULT_ABANDON_GRACE_S`；`:324-349` 构造；`:409-411` 压缩不带 id；`:424-432` 重投；`:502-510` `handle`；`:804-809` 取消不改历史；`:849-870` `_remember`；`:886-920` `attach_sessions` |
| `entry/turn.py` | `:775-816` `abandon_grace_s`；`:828-836` `observe`；`:951-991` 宽限计时 |
| `entry/stream.py` | `:59` `DEFAULT_RING_SIZE`；`:85` `DEFAULT_MAX_OBSERVERS`；`:167` 环；`:241-288` `observe`；`:311-313` `retained` |
| `entry/events.py` | `:447-468` `gap_at` |
| `entry/config.py` | `:137-141` `STATE_DIRNAME`；`:416` 陈旧 docstring；`:1330-1332` 工作区解析 |
| `launch/_surfaces.py` | `:287-310` `DESKTOP_USAGE`；`:359` `DESKTOP_TOKEN_VARIABLE`；`:1017-1063` flag 与 `DesktopOptions`；`:1077-1108` `start_desktop`（`:1104` 读 token）；`:1137-1159` 拒绝无 token 的非回环绑定；`:1188-1206` `_serve_desktop` |
| `launch/__init__.py` | `:168-205` `_adopt_dotenv` |
| `tools/builtin/write.py`；`ensemble/tool.py` | `:354`；`:151` |
| Starlette 1.0.0 | `starlette/responses.py:362-380` Range 分派；`:475-476` 起点越界即 416 |
| 测试 | `tests/entry/test_desktop_http.py:58, 67-72, 83-84, 104-131, 134-135, 226-230, 339-345, 397-`；`tests/entry/test_desktop_stream.py:107-120, 292, 420-571, 503-510`；`tests/entry/test_desktop_interactions.py:111, 120-121`；`tests/entry/test_desktop_wire_contract.py:103-118, 315`；`tests/entry/test_desktop_management_http.py:53-57`；`tests/entry/test_render.py:435-467`；`tests/launch/test_surfaces.py:57-76, 189-226` |
| 文档 | `README.md:143, 151, 204, 242, 280, 358-362`；`README_zh-CN.md:157`；`docs/remote-connection-guide.md`；`docs/_legacy/remote-connection-guide.md`；`docs/engineering/remote-execution.mdx`；`docs/ecosystem/omicsclaw-app.mdx:9-11`；`docs/product-overview.md:10-13`；`docs/core-features/surfaces.md` §8；`.env.example:147, 323-335` |

**App**

| 文件 | 行号与内容 |
|---|---|
| `src/app/api/chat/route.ts` | `:94-118` `parseCanonicalChatTerminalFrame`；`:239-262` `persistAssistantMessage`；`:474-509` 租约、run 与 `isProxyRunCurrent`；`:608` `remoteChat`；`:612` `assistantMessageId`；`:614-632` `retireSupersededProxyRun`；`:640` 只在本机建 job；`:668-672` `propagateRequestAbort`；`:883-903` 审批绑定收尾；`:907-975` `processSseChunk`（`:930` 只处理 `data:`，`:944-953` 审批绑定）；`:996-1265` 读取循环（`:1003-1009`、`:1015`、`:1019` 无超时的 read、`:1036`、`:1045`、`:1053`、`:1100-1106` 标题终止、`:1138`、`:1223-1235`、`:1257`） |
| `src/lib/chat-stream-stop-registry.ts` | `:4` 30 s TTL；`:34-49` 清理计时；`:51-78`；`:79-111` `markChatStreamStopped`；`:132-138`；`:147-169` |
| `src/lib/chat-stream-interrupt.ts` | `:25-73`（`:45-54` 2 s 本地中止兜底） |
| `src/lib/chat-execution-lease.ts` | `:75-163` |
| `src/lib/chat-stream-transcript.ts` | `:10` 空闲超时；`:338-350` `error` 帧；`:352` `default` |
| `src/lib/stream-session-manager.ts` | `:516-535` 空闲检查 |
| `src/lib/new-chat-submission.ts` | `:57-84`（`chat/page.tsx:24` 引入） |
| `src/lib/backend-fetch.ts` | `:366-372` bearer；`:780-860` `witnessBackendIdentity`（`:794-850` 各种失败，`:851` 契约不兼容）；`:904` `reserveOperation`；`:932-1000` `resolveOperationTarget`（`:954-956` epoch，`:962-983` 绑定行） |
| `src/lib/backend-operation-binding.ts` | `:117-119` 隧道未发布；`:127-148` 目标指纹；`:390-483` `resolveOperationTarget`（`:434-440` 连接配置） |
| `src/lib/backend-health.ts` | `:28-41` 支持的契约版本与精确比较；`:61-63` 陈旧注释 |
| `src/lib/chat-ingress/contract.ts` | `:9` |
| `src/app/api/health/route.ts` | `:127-134`、`:170-175` |
| `src/lib/probe-profile.ts` | `:111-130`、`:215-218`、`:325-345` |
| `src/app/api/runtimes/[id]/ping/route.ts` | `:56-78`、`:178-186`、`:186-236` |
| `src/app/api/files/*` | `route.ts:15-45, 52-57`；`browse/route.ts:34-58, 60-66`；`serve/route.ts:40-70`；`raw/route.ts:87-117`；`preview/route.ts:32-69` |
| `src/app/api/chat/permission/route.ts` | `:136-148` 按审批绑定找后端 |
| `src/app/api/jobs/[id]/cancel/route.ts` | `:21-35` 本地 job 取消只改 SQLite |
| 项目入口 | `chat/page.tsx:190-211, 261, 277, 759`；`ChatListPanel.tsx:284, 302-340, 1274`；`OmicsClawSection.tsx:201, 242, 274, 522`；`ProjectStep.tsx:68, 166`；`useProjectSetup.ts:32`；`WorkspaceMismatchNotice.tsx:22`；`project-switch.ts:88-99`；`FolderPicker.tsx:62, 97`；`api/setup/route.ts:88-100, 285-288` |
| 其他 | `MentionPopover.tsx:31`；`useSlashCommands.ts:55-60`；`quick-actions/route.ts:26`；`git-status-store.ts:19, 43`；`api/connections/shared.ts:13-16`；`settings/app/route.ts:57-64`；`en.ts:695, 1397-1398, 1799`；`zh.ts:1794`；`db.ts:332-365`（`:352-355` 陈旧注释）、`:1284` `updateMessageContent`；`resume/route.ts`；`session-resume.ts`；`chat/[id]/page.tsx:144-160`；`useSSEStream.ts:202, 275`；`AGENTS.md:9` |
| 隧道与主进程 | `tunnel-manager.ts:43, 150, 164, 191, 199, 522-560, 895-968, 1102-1230`；`tunnel-reconciler.ts:74-133`（`:116-124` 三次失败即放弃）；`main.ts:46, 235, 650-675, 1452-1482, 1488-1535, 1897-1900, 2248-2259`；`preload.ts:84` |
| 测试 | `probe-profile.test.ts:155, 180, 496, 632-659`；`runtimes-ping.test.ts:117, 633`；`backend-operation-binding.test.ts:23-45`；`jobs.test.ts:5`；`jobs-client.test.ts:8`；`remote-wire-shape.test.ts:72, 120, 178`；`tunnel-manager.test.ts`（进程内 ssh2 server） |
| 文档 | `README.md:157-158, 208-238`；`docs/LOCAL_SETUP_GUIDE.md:333-353, 387`；`docs/LOCAL_SETUP_GUIDE_zh.md:295-310, 341, 430-434`；`playwright.live.config.ts` 头注释 |

## 附录 B：核实记录

**B-1 冷启动**：OmicsClaw 解释器，`/tmp` 下的临时工作区，`OMICSCLAW_SKILLS_DIR` 指向仓库，`--port 18799`：3.5 s 后 `/health` 可达，`skills_count` 94。已停止进程并删除临时目录。

**B-2 认证面**：同上，加 `OMICSCLAW_REMOTE_AUTH_TOKEN=t66`。

| 路径 | 不带认证头 | token 错误 | token 正确 |
|---|---|---|---|
| `/docs`、`/redoc`、`/openapi.json` | 200 | 200 | 200 |
| `/health` | 200（简化载荷） | 401 | 200 |
| `/nope` | 404 | 404 | 404 |

`HEAD /health` 带正确 token 返回 200。已清理。

**B-3 重投与压缩**：同一会话、同一 `source_request_id`，先发 `/compact`（得到 `status`、`result`、`done`），再发内容 `x` 并带 `after_seq: 1`：后端新开了 exchange，产生了 `thinking`、`text` 与一次真实的模型调用（`model_calls: 1`）。机制见 §2.5。

**B-4 仓库状态**：App 的 `git status --short` 为空；`git branch -vv` 显示 `main da509cd [origin/main]`；`git log origin/main..HEAD` 为空；`git reflog show origin/main` 的两条都是 "update by push"；`df525b3`（"speak the rebuilt backend's contract v2"）是 `origin/main` 的祖先。后端 `git show HEAD:omicsclaw/entry/desktop/wire_contract.py` 里的版本号仍是 1。

**B-5 真机检查的证据**：`/tmp/remote-check` 下的 `net-s*.log`（每个场景的请求记录）、`proxy.log`（代理记录的请求头与请求体摘要）、`backend.log`、`shots/*.png`、`s*.js`（场景脚本）、`reattach-*.json`/`*.sse`（curl 续流实验，`reattach-body2.json` 断开时已到 `after_seq: 493`）。

## 附录 C：审核意见处理记录

第 2 版处理第 1 轮审核，第 2.1 版处理第 2 轮复审（本附录末尾）。

每条都先对照代码核实，再决定怎样处理。审核结论："修改后可以交 owner"。

### 阻断

| 编号 | 意见 | 核实 | 处理 | 改动位置 |
|---|---|---|---|---|
| B1 | 接管后从 `after_seq: 0` 全量重放，长回合落盘丢开头 | 属实：环 2048 个事件、每 token 一个事件；Next 转录忽略 `event_omitted`（`chat-stream-transcript.ts:352`）；现状旧 run 读到结束、落盘完整 | **采纳**，改为进程内旁听：旧 run 是唯一的读者、转录者、落盘者；8 MiB 缓冲；`reattach` 只订阅；溢出后退回只转发的后端重放。第 1 版的陷阱 8、9 删除，新增陷阱 9、10 | §0、§3.6、AR-7、§5.3 h、§6、§7 不需裁定一节 |

### 重要

| 编号 | 意见 | 核实 | 处理 | 改动位置 |
|---|---|---|---|---|
| I1 | 半开连接既不触发重连，也不启动宽限期 | 属实：`connectConfig` 没有 keepalive（`tunnel-manager.ts:522-560`）；`reader.read()` 没有超时（`route.ts:1019`）；浏览器 330 s 后自行 `idle_timeout`（`stream-session-manager.ts:516-535`） | **采纳**：ssh2 keepalive 15 s × 3；60 s 读空闲看门狗；文档建议 sshd `ClientAliveInterval`；放弃文案改为"可能已被取消"，放弃后补读一次；live spec 加 `freeze()`；§5.4 改用可复现的丢包与 kill sshd 子进程，写明 TCP 自愈时的表现；Q2 的代价补上半开 | §3.1、§3.5、§3.10、§5.3 o、§5.4 第 5–7 项、§6 陷阱 5、15、Q2 |
| I2 | 重连期间点停止，30 s 后登记被清掉，run 悄悄退役 | 属实（`chat-stream-stop-registry.ts:4, 34-49`；`route.ts:612-632`；`chat-stream-interrupt.ts:45-54` 的 2 s 兜底） | **采纳**：在途 run 的停止登记不设 TTL，计时从 `finishChatStreamRun` 开始；run 内部记下停止意图；停止路由在重连时回 202 `{deferred: true}`，浏览器撤掉 2 s 兜底；加 45 s 单测 | §3.5 第 10 步、AR-6、§6 陷阱 8 |
| I3 | Q1 选项 b 的前提与事实不符；可简化为终止组不带 id | 属实：`df525b3` 在 `origin/main`，reflog 两次 "update by push"；后端 `HEAD` 版本号仍是 1。简化成立：`done` 之后不会再续流 | **采纳**：改写 b 的前提与代价；终止组不带 id，客户端缓提交；`parseCanonicalChatTerminalFrame` 不用改，第 1 版的陷阱 5 删除；仍推荐升 v3（理由是 `resume`） | 涉及仓库、§3.3、§3.5 第 2 步、Q1、附录 B-4 |
| I4 | 五项范围判断 | AR-8：属实（`tunnel-reconciler.ts:116-124`、`tunnel-manager.ts:191`、`main.ts:235`、`readyTimeout` 10 s）。Q6 的副作用属实（`cancel/route.ts:21-35`） | **采纳**：AR-8 的重试预算跟随重连截止时间（经 `/api/internal/reconnect-demand`），其余 15 分钟；Q5 推荐改为 b，AR-9 变成条件任务，补 S36；Q4、Q6 推荐改为 b 并写明副作用，列入 §1.3；AR-7 换成旁听（见 B1） | §1.3、§3.10、§3.11、§3.12 S35、S36、AR-8、AR-9、Q4–Q6 |

### 次要

| 编号 | 意见 | 处理 | 改动位置 |
|---|---|---|---|
| 1 | v2 App 连 v3 后端在见证 `/health` 时就被拒；第 1 版陷阱 5 关于标题的说法不准 | **采纳**：改写兼容性说法；标题取 `settledTerminal`，第 1 版的陷阱 5 已随 I3 删除 | §2.3 契约门控、§3.3 版本、§6 陷阱 2 |
| 2 | `target_no_longer_available` 的来源远不止两种 | **采纳**：列出全部来源；拆出 `backend_process_changed` 与 `backend_authority_changed`，其余按瞬时失败处理 | §2.3、§3.5 第 9 步、AR-6、§6 陷阱 7 |
| 3 | 断在 `error` 与 `done` 之间时，错误文本会追加两遍 | **采纳**：不带 id 的帧等 `done` 再提交，断线时丢掉 | §3.3、§3.5 第 2 步、AR-6 测试 |
| 4 | 长回合续流后用量几乎总是不完整 | **采纳**：在 `DesktopInteractions` 里按回合累计，以 `TURN_END` 的序号去重，并以拉取区间判断完整性 | §3.3、BR-3 |
| 5 | resume 分支的压缩补报 | **采纳**：`compaction` 按 `handle.compaction_only`；App 侧的问题随 B1 消失（旁听不重建转录） | §3.3、BR-3 测试 |
| 6 | 触发条件与状态重置；本机文案；`abandon_grace_s` 为 null 或很小 | **采纳** | §3.5 第 5、6、8 步与放弃文案、AR-6 测试 |
| 7 | 第二个 SSE 消费者写错 | **采纳**：改为 `new-chat-submission.ts:57-84` | §2.3、§3.5 界面 |
| 8 | BR-3 漏了会被 `id:` 行打断的既有测试 | **采纳**：逐个列入 | BR-3 测试、附录 A |
| 9 | §5.1 漏了 `test_render.py` 与 `test_desktop_management_http.py` | **采纳**；相等断言放在后者 | §5.1、BR-4 |
| 10 | 删掉 browse 的远程分支会落到本机分支 | **采纳**：远程返回 409 `remote_unsupported`，AR-4 排在 AR-3 之后 | §3.8、AR-4、§4.1 |
| 11 | 空文件带 Range 回 416；开放区间不应 413；多段应忽略 | **采纳**（已核实 Starlette `responses.py:475-476`）：外壳自己处理区间 | §2.5、§3.2、BR-1 测试、§6 陷阱 22 |
| 12 | S26 效果打折：代理不转发 `nosniff`；漏了 XML 类型；CSP `sandbox` 会破坏 PDF | **采纳**：补类型，App 代理转发 `nosniff`，bypass 栏写明 SVG 与 `sandbox` | §3.2、§3.8、S26、AR-4 |
| 13 | §3.12 缺几行算账 | **采纳**：S34（`/live` 与订阅）、S35（reconnect-demand）、S36（abort-active-turns）；S23 加硬链接 | §3.12 |
| 14 | S30 更严、收益约为零 | **采纳**：不再推荐关闭，改为 Q7（推荐保留）；相等断言排除 docs 路由 | S30、m8、Q7、BR-4 |
| 15 | App `AGENTS.md:9` 写 v2；设置页的遮蔽漏改 | **采纳** | §3.9、S31、AR-2、AR-5、§6 陷阱 21 |
| 16 | 测试覆盖与 AR-10 依赖 | **采纳**：隧道测试用进程内 ssh2 server；live spec 加 m、n；依赖写全 | §3.10、§5.3、AR-10 |
| 17 | Q3 可补一条支持 a 的理由 | **采纳**，并注明 `.ENV` 绕过只在大小写不敏感的文件系统上成立 | Q3 |

### 未能核实的几项

- `/docs` 在 token 错误时也返回 200：起草时实测过（附录 B-2 的"token 错误"一列），不是只看了 `I-curl.txt`。
- 冷启动 3.5 s、curl 多出 2 帧、Electron 的行为：前两项分别见附录 B-1 与真机检查的 `reattach-*.sse`；Electron 的行为留给 §5.4。

### 与审核建议不同的地方

- 没有与审核结论相反的处理。B1 按审核的首选方案（旁听）做，没有保留接管。
- 溢出后的后端重放多了两条约束：转发审批卡片前先等绑定建好，结束前先等落盘信号。原因是这个只读观察与 run 并行读后端，不加这两条，卡片可能先于绑定到达页面，页面也可能在落盘之前刷新消息。

### 第 2.1 版（第 2 轮复审）

复审结论："修改后可以交 owner"，B1、I1–I4 已解决，次要 2、12 部分解决，其余完全解决；剩余 R1–R13 都在实现层面，不需要第三轮。每条先核实再改，没有发现说法有误的；这些改动都不影响 §7 的选项与推荐。

| 编号 | 意见 | 核实 | 处理 | 改动位置 |
|---|---|---|---|---|
| R1 | 进程内登记要挂在 `globalThis` 上；登记的归属要理清 | 属实：`chat-stream-stop-registry.ts:3, 21-25`、`chat-execution-lease.ts:11-18`、`job-event-cursor.ts:2-9` 都这样做；`runtime-log.ts:4` 注释写明是为了扛住热重载 | **采纳**：run 登记挂 `globalThis`；AR-6 引入 `source_request_id`、连接状态、截止时间、停止意图，AR-7 再加缓冲、订阅者、已回答集合与落盘信号；审批路由经 `request_id → session_id` 表找到 run | §3.5 "run 登记"、§3.6、AR-6 与 AR-7 测试、§6 陷阱 23 |
| R2 | 看门狗从"上次收到字节"计时会误触发 | 属实：读循环先 `await waitForDownstreamDemand`（`route.ts:1014`）再读 | **采纳**：计时器在发起 read 时启动、read 返回时清除 | §3.5 第 4 步、AR-6 测试、§6 陷阱 25 |
| R3 | 202 会被浏览器当作可以本地中止 | 属实：`shouldAbortLocallyFromInterruptResponse` 对 `response.ok` 返回 true（`chat-stream-interrupt.ts:17-23`） | **采纳**：先解析响应体，`deferred` 为真时不中止并撤掉兜底；补单测 | §3.5 第 10 步、AR-6 测试 |
| R4 | §5.3 o 与"失败后才发 `connection` 帧"不一致 | 属实：`freeze()` 时新连接照常转发，第一次续流就会成功 | **采纳**：发现断开时立即发一帧 `reconnecting`；o 的断言改为横幅可能一闪即逝、随后出现"已重新连接" | §3.5 内部帧、§5.3 o |
| R5 | 隧道未发布与换了连接配置抛同一个错；切回本机模式时原因是 `revoked` | 属实：`resolveCurrentTunnelBinding`（`backend-operation-binding.ts:110-125`）只抛一个错；`resolveActiveTunnelBinding` 的 `reason` 有 `missing`、`malformed`、`stale-server-instance`、`revoked`、`owner-mismatch`、`profile-revision-mismatch`（`tunnel-binding.ts:300-331`）。另补上审核没列的 `malformed`，按瞬时处理 | **采纳**：按 `reason` 归类；每次尝试前检查 `connection_mode` | §3.5 第 7、9 步、AR-6 测试 |
| R6 | S26 的类型名单不全；`.svgz` | 属实（实测 `mimetypes`：`.xsl`/`.xslt` → `application/xslt+xml`，`.rdf` → `application/rdf+xml`，`.svgz` → `('image/svg+xml', 'gzip')`） | **采纳**：SVG 之外的 `*/xml`、`*+xml` 一律 `text/plain`；带编码的猜测按 `application/octet-stream`，不带 `Content-Encoding` | §3.2、S26、BR-1 测试 |
| R7 | 先 open 再 fstat 时，换成 FIFO 会让 `open()` 阻塞、卡死后端 | 属实（阻塞式打开没有写端的 FIFO 会一直等） | **采纳**：`O_RDONLY \| O_NONBLOCK \| O_NOFOLLOW`，在线程里打开与读取，`fstat` 确认普通文件再读 | §3.2、S23、BR-1 测试、§6 陷阱 24 |
| R8 | 放弃时原浏览器收到 `controller.error`，订阅者没有 `done` | 属实（`route.ts:1223-1235` 的错误分支） | **采纳**：放弃时生成 `error`（内容即落盘文案）与 `done` 两帧，发给浏览器并写进旁听缓冲，不进转录 | §3.5 放弃与补读、§3.6 结束、AR-6 与 AR-7 测试 |
| R9 | 溢出重放的两处等待没写超时后怎么办 | 属实 | **采纳**：等绑定 5 s 不到就不转发卡片，改发 `reason: "card_not_ready"` 的 `event_omitted`（浏览器显示"刷新页面后可见"）；等落盘信号最多 60 s，超时发 `done` 后关闭 | §3.6、AR-7 测试 |
| R10 | 依赖图里 AR-8"可以先做"，但它要读 AR-6 的新路由 | 属实 | **采纳**：reconnect-demand 返回 404 或失败时按 `null` 处理（预算 15 分钟），AR-8 可以先落地 | §3.10、§4.1 |
| R11 | `/health` 见证通过后隧道才死时，续流 POST 会一直挂 | 属实（续流的 POST 要走建连保护才有上限） | **采纳**：沿用现有的 30 s `createAbortSignal`，超时按瞬时失败 | §3.5 第 7、9 步、AR-6 测试 |
| R12 | §5.4 的命令会匹配错进程；只丢了出方向 | 属实（`grep 'sshd: <用户>'` 也匹配交互会话） | **采纳**：`pgrep -af 'sshd: .*@notty'` 加 `ss -tnp` 按笔记本 IP 确认；pf 与 iptables 都写成双向 | §5.4 第 5、6 项 |
| R13 | §4.4"续流只用 `handle.stream.retained()`……"与用量累计不同步 | 属实 | **采纳**：改写为只用 `observe`、`ObserverCapacityError` 与判断压缩是否送达时的 `retained()`，用量累计在 `entry/desktop/interactions.py` | §4.4 |

