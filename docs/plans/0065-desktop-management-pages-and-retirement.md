# 计划 0065 — Desktop 管理页与功能退役（0064 后续计划 M）

**状态**：第 2.1 版（2026-09-28），已按独立审核与复审修订（处理记录见附录 C）。**owner 于 2026-09-28 裁定 Q1–Q13 全部按推荐**（§7）。**2026-09-29 实施完成**：后端 BM-1…6 已实现并经独立评估与修复（未提交，按 0056–0060 统一提交策略）；App 的 M-A…M-D 已在 `main` 本地提交（未 push），每期都经过独立评估与修复。剩余：owner 在 Electron 下验收（清单见 App `docs/PROJECT_MEMORY.md` 的 0065 M-D 条目）。

**编号约定**：本文的 Q1–Q13 是本计划自己的问题；引用 0064 的裁定一律写作"0064-Q6""0064-Q9②"等。

### 修订说明

**第 2.1 版（2026-09-28）**：按复审修正 R1（字面守卫）、R2（全部候选 `.env` 与启动快照）与 4 条次要意见，见附录 C 的第 2.1 版一节。

**第 2 版（2026-09-28）**：按独立审核意见修订，每条先核实证据再改。
- **阻断 B1**：第 1 版 Q1 推荐的"`launch` 从 `entry.cli._configure` import"违反 `tests/launch/test_launch_is_above_entry.py:337-353`。`.env` 设置对象改放 `entry/desktop/`，`launch` 只负责构造与注入（§3.6，Q1 重写）。
- **I1**：启动快照的做法重写，满足"`launch/__init__.py` 只读一次 `os.environ`"与"`_surfaces.py` 不出现 `os.environ`"两条测试，并写明传参路径（§3.6）。
- **I2**：S15 有旁路（先 PUT 再 test），实际只防 DNS 重绑定，而 0064-Q4 已经接受这项风险。Q3 改为推荐 c（不做）。
- **I3、I4**：PUT 的写入语义改为与 CLI 向导逐项对照；新增 Q9（密钥变量名）、Q10（`OMICSCLAW_PROVIDER`）。
- **I5**：MCP 的 `${VAR}` 在 command、args、url、env、headers 里都会展开。S13 重算，新增 Q12。
- **I6**：App 的 P0/P1 未提交，列为 M-C 的前置条件，新增 Q11。
- **I7**：补齐 AD-7 漏项；AD-13 只删 `tool_timeout` 变体；修正 `git grep` 验收串的误报与漏检，每个 AD 加一条文案键前缀检索。
- **次要 1–11**：逐条处理，见附录 C。

**涉及仓库**
- 后端：`/workspace/dataset/private/zhouwg_data/OmicsClaw`，以工作树为准（0064 的 P0+P1 已实现、未提交）。
- 桌面客户端：`/workspace/dataset/private/zhouwg_data/OmicsClaw-App`，HEAD `11f69cb`，工作树含 0064 P0/P1 的全部改动（未提交，`git diff` 与未跟踪文件就是全部）。0064 写的 App 路径 `/workspace/algorithm/zhouwg_project/OmicsClaw-App` 已不是现在的位置。

**前置与关联**：0064（§2.7、§4.4、§4.9、§4.11、§5.5、§6、§7、§8 的 Q4/Q6/Q8/Q9）；0057（留出集软约束）；0037（`launch` 分层与环境读取规则）；App 的 ADR 0004、0006。

**行号约定**：两边都以 2026-09-28 工作树为准。实施时按符号名重新定位。

**如何核实**：后端代码逐处亲自读过，另外在 rapids 解释器下实际加载了一次技能索引（附录 B-1）。App 侧由三路只读盘点逐文件列出删除范围，关键行（`main.ts`、`python-manager.ts`、`menu.ts`、`useSSEStream.ts`、`primary-nav.ts`、`ChatListPanel.tsx`、各解析器）再亲自复核。

---

## 0. 摘要（结论先行）

**现状**
- 0064 P0/P1 之后，`oc desktop` 服务 7 个路径（`SERVED_PATHS`，`wire_contract.py:34-42`）：聊天、审批、中止、会话权限档、工作区（GET/PUT）、`/env/doctor`、`/health`（GET/HEAD）。管理页要用的路由一条都没有。
- **新用户在 App 里配置模型这条路是断的。**向导的 LLM 步骤与设置页的 Providers 都靠 `GET/PUT /providers`：列表为空，保存得到 404。现在只能去终端跑 `oc cli --configure`，或者手改 `.env`。
- Skills 页因为 `GET /skills` 缺失而显示错误状态；MCP 页因为 `GET /mcp/servers` 缺失而报错；自动标题回落到启发式。
- 另有十余个旧功能（AutoAgent、Bench、KG、Notebook、技能治理、回放与晋升、市场、OAuth、CLI 设置、Bridge、Outputs、远程死代码、聊天死分支）仍挂在导航里或留在代码里，调用的都是后端已经不存在的路由。

**本计划做什么**
1. **后端薄路由 6 条**，都放在 `entry/desktop/**`，只读为主：
   - `GET /skills`、`GET /skills/{domain}/{name}`
   - `GET /mcp/servers`
   - `GET/PUT /providers`、`POST /providers/test`（0064-Q6 = a：以 `.env` 为准）
   - `POST /chat/title`（0064-Q9③）

   `.env` 设置对象 `DotenvSettings` 放在 `entry/desktop/`，经 `omicsclaw.entry.desktop` 公开导出。`oc desktop` 在启动时用 `dotenv_target()` 与启动快照构造它，再注入 `create_desktop_app`（Q1 推荐 d）。约束来自三条分层测试：`entry` 不能 import `launch`、不能读 `os.environ`；`launch` 只能 import `entry` 的公开名字（§2.4）。
2. **App 三个管理页接上真实数据**：Providers（含向导的 LLM 步骤）、Skills、MCP（只读，0064-Q9④）。Memory 页只隐藏（0064-Q9②）。自动标题只需验证。
3. **App 删除 13 个功能**，每个功能单独提交。删除范围包括导航、页面、API 路由、lib、hooks、组件、仅被其使用的 en/zh 键、测试、smoke/e2e。数据库表保留（0064-Q8 = a）。主进程确认密钥的 bootstrap 保留。**前置条件**：任何 0065 的 App 改动之前，App 的 0064 P0/P1 改动先提交（Q11）。
4. **收尾**：清理 P1 留下的"后端会忽略的请求字段"和死代码；`/compact` 刷新后留痕作为可选项。

**分期**（§4，共 27 个任务）

| 期 | 内容 | 依赖 |
|---|---|---|
| M-A 模型与技能（最先做） | BM-1 Skills 路由、BM-3 Providers 路由（含 `DotenvSettings`）、BM-5 启动快照与注入；AD-8 OAuth 删除 → AM-1 Providers 页与向导；AM-2 Skills 页 | 后端与 App 两条线并行；App 页面先对照替身载荷开发，最后用真实后端验收 |
| M-B 其余管理面 | BM-2 MCP、BM-4 标题、BM-6 契约与文档；AM-3 MCP 只读、AM-4 Memory 隐藏、AM-5 标题验证 | AM-3 依赖 BM-2 |
| M-C 功能退役 | AD-1 … AD-12，顺序见 §4.3 | 不依赖后端，可与 M-A/M-B 并行；App 内部串行；前置条件是 App P0/P1 已提交（Q11） |
| M-D 收尾 | AD-13 聊天死分支、AC-1 P1 遗留、AC-2 `/compact` 留痕（可选）、AM-6 App 文档 | 在 AD-3、AD-4 之后，与它们改同一批聊天文件 |

**核实中发现的、与 0064 §2.7/§5.5 不一致之处**，共 18 条，见 §2.3。其中影响设计的有：
- `lib/onboarding/` 是首次设置向导，不是 Bench 的引导，**不能删**；
- fd-3 管道在**所有**模式下都会创建，不只是打包模式；
- 斜杠菜单的技能项已在 P1 删除，`useSlashCommands` 不再请求 `/api/skills`；
- 同一条后端 `GET /mcp/servers` 被 App 的两个路由按两种形状读取；
- 0064 §4.6 说的"P0/P1 Providers 页改为只读"并没有实施。

**需要 owner 裁定的问题**：13 个（§7）。最关键的是：
- Q1：`.env` 读写如何复用 `entry/cli` 里的私有实现；
- Q9：保存密钥写 `preset.api_key_env` 还是 `LLM_API_KEY`；
- Q11：App P0/P1 的提交时机。

---

## 1. 目标与非目标

### 1.1 目标

| # | 目标 | 验收口径（§5.4） |
|---|---|---|
| G1 | 新用户能在 App 里配置模型：选 provider、填密钥、保存、自动重启（Electron）或提示手动重启（`npm run dev`），重启后 `/health.provider/model` 就是刚保存的值 | §5.3 的 c、d |
| G2 | Skills 页列出当前后端索引里的全部技能；详情抽屉显示 SKILL.md 正文与文件清单 | §5.3 的 a、b |
| G3 | MCP 页只读，显示 `.mcp.json` 里的服务器与连接状态；`env`/`headers` 的值被遮蔽 | §5.3 的 e |
| G4 | 自动标题由后端生成 | §5.3 的 f |
| G5 | 导航里没有死入口；被删功能的路由字符串用 `git grep` 查不到；en/zh 键集一致 | §5.4 |
| G6 | 后端新增的写路由都只收 JSON，都需要 bearer（配置了 token 时），密钥不回显 | 后端测试 |

### 1.2 非目标

- **Memory 页的重做**：按 0064-Q9② 另立计划（`LongTermStore` 的只读列表、搜索、删除）。本计划只隐藏入口。
- **MCP 写入**（0064-Q9④ 推迟）与 `/mcp/sync`。
- **远程模式**：后续计划 R。远程模式下三个管理页只要求不崩溃（§3.9.1 远程一段）。
- **按会话切换 provider/model**：0064 的非目标，保持不变。
- **Skill 的结构化契约**（`skill.yaml` 的 io、security、run_health、validation 等）：重建后的技能层只解析 `name`、`description`、`trigger`、`tags`，这些字段一律不提供，App 侧相应的展示与筛选删掉（AM-2）。
- **数据库迁移**：表保留（0064-Q8 = a），只删除已经没有调用方的访问函数，schema 与迁移代码不动。
- **修改 0057 的任何文件**；**重写 `AGENTS.md`**。

---

## 2. 现状与证据

### 2.1 后端现状（0064 P0+P1 之后）

**路由**：`POST /chat/stream`、`/chat/permission`、`/chat/abort`、`/chat/session-permission-profile`，`GET/PUT /workspace`，`GET /env/doctor`，`GET/HEAD /health`（`server.py:448-549`，`wire_contract.py:34-42`）。

**可复用的机制**（`server.py`）
- `_authorized`（`:389-396`）：bearer 用 `secrets.compare_digest` 比较。
- `_require_json`（`:404-407`）：精确解析媒体类型；缺头或非 JSON 返回 415。
- `_read_body`（`:409-441`）：有上限，拒绝谎报的 `Content-Length`。
- 错误统一为 `{"detail": code}`（`_refused`，`:398-399`）。
- 控制类请求体上限 `CONTROL_MAX_REQUEST_BYTES = 64 KiB`（`:103`）。

**新路由要用到的公开 API**

| 能力 | 位置 |
|---|---|
| 技能索引 | `app.skills: SkillIndex`（`assembly.py:887`）；`SkillIndex.skills/get/by_domain/get_full_content`（`skills/index.py:74-238`）；`Skill.name/description/tags/trigger/domain/relative_path/directory`（`skills/skill.py:12-81`） |
| MCP | `app.mcp: MCPManager \| None`（`assembly.py:924`）；`MCPManager.config -> MCPConfig`（`mcp/manager.py:167-169`）；`statuses() -> tuple[ServerStatus, ...]`（`:215-217`）；`ServerConfig`、`RejectedServer`（`mcp/config.py`） |
| provider | `omicsclaw.provider` 的 `PRESETS`、`DETECT_ORDER`、`resolve_config(..., env=...)`、`provider_for`、`get_model_limits`、`DEFAULT_MODEL_LIMITS`（`provider/__init__.py:49-70`）；`app.provider.name/generate/bind`（`provider/base.py:102-164`）；`effective_model(app)`（`desktop/doctor.py:65-77`） |
| `.env` 定位 | `launch/_dotenv.py`：`dotenv_candidates`、`dotenv_target` |
| `.env` 读写 | `entry/cli/_configure.py`：`read_dotenv`（`:142`）、`write_dotenv`（`:203`）。它们列在该模块的 `__all__` 里（`:70-72`），并被 `entry/cli/_auto.py:29` 复用，但 `omicsclaw.entry.cli` 包没有重新导出它们（`entry/cli/__init__.py:75` 只导出 `missing_credential_hint`、`run_configuration_wizard`）。"写哪个变量名"的规则（`_target_key`，`:449-469`，以及 `_ask_llm` 里的用法，`:472-542`）是私有的 |

**启动注入点**
- `launch/_surfaces.py` 的 `start_desktop(deployment, surface, env)`（`:1072-1102`）调用 `_serve_desktop(config, options, token, uvicorn)`（`:1156-1170`），后者再调用 `create_desktop_app(app, bearer_token=token)`。
- `launch/__init__.py` 的 `main` 在 `env is None` 时先 `_adopt_dotenv()` 再取 `os.environ`（`:122-125`）。这是全包唯一一次读取 `os.environ`（§2.4）。

**provider 的解析顺序（三处，不完全一致）**
- `AppConfig.provider` 依次取 `--provider`、`OMICSCLAW_PROVIDER`、`LLM_PROVIDER`；`AppConfig.model` 依次取 `--model`、`OMICSCLAW_MODEL`、`LLM_MODEL`（`entry/config.py:888-896`）。
- 运行中的 provider 由 `resolve_config(config.provider, config.model)` 求出（`assembly.py:1219-1221`；`doctor.effective_model` 用同一调用只读地求模型，`doctor.py:65-77`）。
- `resolve_config` 与 `detect_provider_from_env` 自己只把 `LLM_PROVIDER` 放在前面（`provider/config.py:535, 613`）。
- 结论：要预测"重启后会用哪个 provider"，必须先按 `AppConfig` 的顺序取 provider 与 model，再交给 `resolve_config(provider, model, env=...)`，与启动路径一致（§3.4）。

**CLI 向导写入 LLM 配置的语义**（`_configure.py:472-542`，PUT 要逐项对照）
- 密钥变量：`_target_key(existing, "LLM_API_KEY", preset.api_key_env, "LLM_API_KEY", "OMICSCLAW_API_KEY")`。规范写法是 **`LLM_API_KEY`**；只有文件里已经有 `preset.api_key_env` 时才写它（`:504-507`）。
- 换了 provider：模型的缺省值重置为新 preset 的 `default_model`，端点的缺省值为空串（`:479-487`、`:517-540`），防止旧厂商的 `LLM_BASE_URL` 劫持新厂商。
- 模型与端点每次都会写入。

**已知的小过时**：`DESKTOP_USAGE`（`_surfaces.py:287-306`）没有列出 P1 新增的 `/chat/session-permission-profile` 与 `/env/doctor`。在 BM-5 里一并修正。

### 2.2 App 现状：管理页与它们的解析器

| 页面 | App 路由 → 后端路由 | 解析器（形状以它为准） | 现在的失败方式 |
|---|---|---|---|
| Skills 目录 | `api/skills/route.ts:8-15` → `GET /skills`，**不论后端状态一律按 200 转发** | `parseSkillCatalogResponse`（`components/skills/skill-catalog-client.ts:176-198`）与 `parseSkill`（`:124-174`） | "domains must be an array" |
| Skills 详情 | `api/skills/[domain]/[skillName]/route.ts:5-20` → `GET /skills/{d}/{n}`，转发状态码 | `mergeSkillDetailResponse`（`:205-230`）；字段见 `components/skills/types.ts:113-149` | 抽屉显示"只有目录摘要" |
| Providers 设置页 | `api/providers/route.ts` GET/PUT → `/providers` | `OmicsClawProviderSection.tsx:220-285`；保存载荷来自 `lib/provider-settings.ts:55-76` | 列表为空，保存 404 |
| 向导 LLM 步骤 | 同上 | `components/setup/hooks/useLLMSetup.ts:71-123` | 同上 |
| Provider 诊断 | `api/providers/doctor/route.ts` → `GET /providers`、`/health`、`POST /providers/test` | `normalizeProviderInfo`（`:75-112`）；test 结果解析（`:270-303`） | "Backend /providers returned HTTP 404" |
| 模型分组 | `api/providers/models/route.ts` → `GET /providers` | `buildProviderModelGroups`（`lib/provider-model-catalog.ts`，读 `model_metadata[].context_window`，`:74-76`） | 分组为空 |
| 网络测试 | `api/network/test/route.ts:59-82` → `GET /providers`，取 `base_url` 的 origin。按名字匹配到 provider 时，即使它的 `base_url` 为空也只返回空目标；只有名字匹配不到时，才回落到第一个有 `base_url` 的 provider（`:70-72`） | 同上 | 无目标 |
| 其他读取 `/api/providers` 的地方 | `settings/overview/useOverviewData.ts:90`；`settings/UsageStatsSection.tsx:81`（provider_id → display_name）；`chat/ChatView.tsx:333`（`provider-changed` 事件）；`lib/onboarding/llm-providers.ts`（按 `tier === 'primary'` 分组、取第一个 `configured`）；`setup/steps/LLMStep.tsx`（`configured`、`env_key`、`base_url`） | 都读 `BackendProvidersResponse` | 空 |
| MCP 列表 | `api/plugins/mcp/route.ts:104-127` → `GET /mcp/servers`，读 `servers[].{name,type\|transport,command,url,args,env,headers,enabled,tools}` | `toSourcedConfig`（`:44-72`） | 错误 |
| MCP 连接状态 | `api/plugins/mcp/status/route.ts:21-37` → **同一条** `GET /mcp/servers`，原样转发 | `McpManager.tsx:40-43, 94-109` 读 `servers[].{name, active}` | `{servers: [], error}` |
| 自动标题 | `lib/session-title.ts:70-130` → `POST /chat/title` | 请求 `{schema_version:1, source_request_id, user_text}`；成功 `{schema_version:1, title}`；失败为非 2xx 的 `{schema_version:1, error:{code}}`，`code` 取 `SESSION_TITLE_FAILURE_CODES`（`:10-18`） | 回落到启发式标题 |

**导航的定义位置**
- `lib/primary-nav.ts:4-35`：`PrimaryNavItemId` 联合类型与条目表。
- `components/layout/ChatListPanel.tsx`：`NAV_ICONS`（`:174-187`，其中 `jobs`/`datasets`/`artifacts` 三项已经没有对应条目），`NAV_GROUP_DEFS`（`:709-712`）。
- `electron/menu.ts:92-98`：Go 菜单，Notebook ⌘2、Memory ⌘3、Skills ⌘4。
- 设置页侧栏：`components/settings/SettingsLayout.tsx`（CLI 一项）。
- 没有 `middleware.ts`，`next.config.mjs` 里也没有 redirects。

**en/zh 键集一致由类型保证**：`zh.ts:3` 声明为 `Record<TranslationKey, string>`，而 `TranslationKey = keyof typeof en`。缺键会报类型错误，多键会被对象字面量的多余属性检查拒绝。所以 `npm run typecheck:web` 通过即表示两边键集一致。目前两边各 3,094 个键。

### 2.3 逐条核实 0064 §2.7 与 §5.5（写于 2026-09-27）

| # | 0064 的说法 | 当前工作树的事实 | 本计划的处理 |
|---|---|---|---|
| E1 | §2.7：斜杠菜单技能项读 `useSlashCommands.ts:102-110` 的 `data.skills`；§5.5 要求"一并对齐" | **P1 已删**。`useSlashCommands.ts:85-86` 只返回内置命令；菜单只剩 `/help`、`/clear`、`/cost`、`/compact`（`lib/constants/commands.ts:14-19`）。残留的是 `usePopoverState.ts:59-147` 对 `/api/skills/search` 的"AI 建议"，永远不会真正发出请求，但输入 2 个字符后会闪一下约 500 ms 的加载 | 不需要对齐；残留代码归 AC-1 删除 |
| E2 | §5.5：`/research`、`/run` 要删 | 已经不存在 | 从清单中去掉 |
| E3 | §5.5：`useSSEStream.ts` 有 7 个死 case 与 `_progress` | 现在是 6 个：`tool_log` `:266`、`tool_timeout` `:372`、`mode_changed` `:391`、`ask_user_question` `:401`、`preflight_pending` `:449`、`pathology_detected` `:463`。`task_update` 已在 P1 删除。另有 `_progress`（`:254-261`）、`tool_result.media` 的读取（`:244-246`），以及 `status` 里除压缩以外的全部分支（`:305-348`） | AD-13 |
| E4 | §5.5：`types/index.ts:774-797` | 现在是 `:771-816`（SSE 类型与 skill-log 类型）、`:847-860`（`AskUserQuestionEvent`）；`ClaudeStreamOptions`（`:1372-1415`）完全没有使用者 | AD-13、AC-1 |
| E5 | §5.5 Bench：删除 `lib/onboarding/` | **错误**。`lib/onboarding/` 是首次设置向导，被 `AppShell.tsx:40-41`、`setup/OnboardingShell*.tsx`、`setup/steps/*`、`RuntimesPanel.tsx:36` 与 `e2e/onboarding.spec.ts` 使用。Bench 的"引导"是 `api/onboard/**` 与 `app/bench/onboard/` | **保留** `lib/onboarding/` |
| E6 | §5.5 Notebook：`backend-contract.ts:47-61`；删除 `components/notebook/`、`lib/notebook/` 整个目录 | 行号已移到 `:70-84`。**不能整目录删除**：`CellOutput.tsx` 被只读的 `.ipynb` 预览（`project/viewers/NotebookViewer.tsx:8`）使用；`lib/notebook/ipynb.ts`、`navigation.ts`、`http.ts` 被聊天、文件预览与 `AppShell` 的导航守卫使用 | AD-4 先迁出这几个文件 |
| E7 | §5.5：`backend-fetch.ts` 里 autoagent 分支 25 处 | 27 行（不分大小写），与 HEAD 相同 | AD-1 |
| E8 | §2.7：Bench 的引导状态在 `bench/page.tsx:24-30` | `:24-31`，仍是尽力而为 | — |
| E9 | §5.5：Bench 与 KG 各自独立删除 | **耦合**。14 个 `api/kg/**` 路由都 import `lib/bench-proxy`；KG 组件 import `lib/bench-api-client`、`lib/bench-last-thread` | 先删 KG（AD-2），再删 Bench（AD-3） |
| E10 | §5.5 技能治理：保留主进程确认密钥的 bootstrap，位于 `main.ts:1236-1241` | 现在是 `bootstrapMainProcessConfirmSecret`，位于 `main.ts:1249-1256`，调用点 `:1572`、`:2202`、`:2226`。它走 HTTP（`/api/internal/main-process-secret`），与 UtilityProcess 的 bootstrap 完全独立 | AD-7 不动这几处 |
| E11 | §5.5 技能治理："打包模式改为直接 fork `server.js`"。0064 E2："fd-3 只在打包模式使用（`main.ts:1549-1551`）" | **前半对，后半错。**现在打包模式 fork 的是 `next-server-bootstrap.js`（`main.ts:1301, 1332`），改回 `server.js` 正是目标。**fd-3 管道在所有模式下都会创建**：`python-manager.ts:398` 的 stdio 总是 4 项，交接在 `:506-537`。只在打包模式运行的是 Next 的 UtilityProcess bootstrap。`main.ts:1549-1551` 现在是任务通知代码。重建后的后端没有任何生产代码读取 fd 3 | AD-7 |
| E12 | §2.7：CLI 设置返回 502，OAuth 返回 503 | 只在后端不可达时成立。后端在线时，两者都把 FastAPI 的 404 JSON 原样转发 | 只影响 §2.7 的描述 |
| E13 | §5.5 技能生命周期：`installed`、`install`、`uninstall` | 它们不是 App 路由，而是 `api/skills/marketplace/{search,install,remove}` 背后调用的后端路径 | 并入 AD-6 市场 |
| E14 | §2.7 MCP：状态路由返回 `{servers:[], error}` | 属实。另外发现：**同一条** `GET /mcp/servers` 被两个 App 路由按两种形状读取：列表读配置字段，状态读 `name`、`active`（§2.2） | BM-2 用一个形状同时满足两者 |
| E15 | §4.6："P0/P1：Providers 页改为只读并说明配置方法" | **没有实施**：`OmicsClawProviderSection.tsx` 的保存流程仍在，P0/P1 的 diff 没有碰这个文件 | AM-1 直接接上真实写入，不再补做只读中间态 |
| E16 | §2.7 KG：`/health` 没有 `kg`，显示"不可用" | 属实。此外设置页总览因此**永远**显示一条 KG 警告（`settings/overview/useOverviewData.ts`） | AD-2 一并清除 |
| E17 | §2.7 Memory：代理转发非 2xx | P1 改过 `api/memory/[...path]/route.ts`（加了作用域，另有 `scoped-memory-route.test.ts`）。Bench 的 `useThreadArtifacts.ts` 也调用 `/api/memory/browse` | 隐藏页面时保留 API 路由与组件，留给 Memory 计划 |
| E18 | 0064 头部：App 位于 `/workspace/algorithm/zhouwg_project/OmicsClaw-App` | 现在位于 `/workspace/dataset/private/zhouwg_data/OmicsClaw-App`。App 的 `AGENTS.md` 已经把旧页面指向"plan 0065" | 本计划采用新路径 |

§2.7 的其余各行（Skills 页、Notebook 的 502、Optimize 的 503、Bridge、Outputs、Env 自适应面板映射为 `not_supported`、标题回落、`instrumentation.ts` 的对账噪音）都已复核属实。

### 2.4 约束

**分层与环境读取（0037，由测试强制；本计划不改任何守卫测试）**

| 测试 | 要求 | 对本计划的影响 |
|---|---|---|
| `tests/launch/test_launch_is_above_entry.py`（行为探针与源码扫描） | `omicsclaw/entry/**` 不 import `omicsclaw.launch` | `entry/desktop` 拿不到 `dotenv_target`，只能由 `launch` 注入 |
| 同文件 `test_the_shell_imports_only_public_names_of_the_entry_layer`（`:337-353`，用 `_imported_modules`，`:195-232`） | `launch/**` 引入的 `omicsclaw.entry.*` 名字里不得有 `_` 开头的部分 | **`launch` 不能 import `omicsclaw.entry.cli._configure`**（第 1 版 Q1-a 就违反这一条） |
| 同文件 `test_only_the_shell_itself_names_the_two_globals`（`:108-122`） | `launch/` 下除 `__init__.py` 外不得出现 `os.environ` 等写法 | 快照只能在 `__init__.py` 里取，再作为参数传给 `_surfaces.py` |
| 同文件 `test_the_shell_hands_both_globals_down_explicitly`（`:159-168`） | `launch/__init__.py` 里必须逐字出现 `environment: Mapping[str, str] = os.environ` | 快照代码保留这一行原样，再在后面包装（§3.6） |
| 同文件 `test_the_shell_reads_each_global_exactly_once`（`:149-158`） | `launch/__init__.py` 在代码里恰好读一次 `os.environ`、一次 `sys.argv`（按语法树计数） | 取快照不能再多读一次 `os.environ`（§3.6） |
| `tests/launch/test_the_environment_is_read_in_known_places.py`、`tests/_env_probe.py` | 重建后的各包只在登记过的文件里读取进程全局；`provider/config.py` 是登记在案的例外，但只在调用方不传 `env=` 时才读 | `entry/desktop` 调 `resolve_config`、`parse_mcp_config` 时一律显式传 `env=` |
| `tests/entry/test_config.py::test_no_entry_module_reads_the_environment`（`:380-405`） | `entry/**` 源码里不得出现 `os.environ` 等写法，**连 docstring 与注释也算**（`:389-394`） | 新模块的 docstring 不能写 `os.environ`，要写"进程环境"（陷阱 19） |
| `tests/entry/test_entry_is_the_top_layer.py::test_importing_the_package_costs_no_optional_dependency` | `import omicsclaw.entry` 不加载 fastapi、textual、prompt_toolkit、openai、anthropic | `entry/desktop` 对 `entry.cli._configure` 的 import 写在函数体内（§3.6） |

**0057 留出集软约束（0064 §4.9，仍然有效）**
- 留出集运行期间，后端只改 `entry/desktop/**`、`launch/**`、`tests/**` 与文档。
- 核实：`import omicsclaw.entry` 不会加载 `entry.cli`、`entry.desktop` 或 `launch`（附录 B-2）。0057 的脚本只 import `entry.config`、`open_app`、`entry.turn`、`ensemble`、`skills`（附录 B-2）。
- 0064 §5.5 另有一句"留出集运行期间也不要改 `entry/cli`"（0064 第 803 行）。本计划照此执行。
- 按 Q1 的推荐 d，本计划的后端改动都落在允许的路径里。选 b′（在 `entry/cli/__init__.py` 重新导出）就需要 owner 豁免这条约束。

**App 的前置条件（Q11）**
- App 工作树里 0064 P0/P1 的改动还没有提交：`git status --short` 共 179 项，`git diff --stat` 显示 161 个文件被修改。
- 这批改动与 AD 任务要改的文件大量重叠：`api/chat/route.ts`、`ChatView.tsx`、`useSSEStream.ts`、`stream-session-manager.ts`、`ChatListPanel.tsx`、i18n 等。
- 在这个基础上，"每个功能一个提交"没法落地：AD 的提交会把 P0/P1 的改动一起带进去。
- 所以任何 0065 的 App 改动（不只是 M-C）的前置条件都是：App 的 P0/P1 先作为独立提交落地。或者 M-A/M-B 在独立的 worktree 里开发，P0/P1 提交后再 rebase。提交时机由 owner 定（Q11）。

**提交**
- 后端：按 owner 的仓库提交策略，"0056–0060 全部完成后统一提交"。
- App：P0/P1 提交之后，每个功能一个提交。提交前按其 SPEC 运行 `cursor-team-kit:make-pr-easy-to-review`；环境里没有这个技能时，按 `docs/agent-playbooks/` 执行（`requesting-code-review.md`、`verification-before-completion.md`、`finishing-development-branch.md`）。不 push。

---

## 3. 设计

### 3.1 后端薄路由总览

| 路由 | 方法 | 新模块中的纯函数 | JSON | bearer | 版本 |
|---|---|---|---|---|---|
| `/skills` | GET | `catalog.skill_catalog(app)` | — | 需要 | 不纳入契约版本（§3.8） |
| `/skills/{domain}/{name}` | GET | `catalog.skill_detail(app, domain, name)` | — | 需要 | 同上 |
| `/mcp/servers` | GET | `catalog.mcp_servers(app)` | — | 需要 | 同上 |
| `/providers` | GET | `providers.provider_listing(app, settings)` | — | 需要 | 同上 |
| `/providers` | PUT | `providers.save_provider(app, settings, document)` | **必须** | 需要 | 同上 |
| `/providers/test` | POST | `await providers.test_provider(settings, document)` | **必须** | 需要 | 同上 |
| `/chat/title` | POST | `await title.generate_title(app, document)` | **必须** | 需要 | 请求体自带 `schema_version: 1` |

**代码放在哪**
- `entry/desktop/catalog.py`：skills 与 MCP 的只读载荷。
- `entry/desktop/providers.py`：provider 的列表、保存、测试，`SettingsFile` 协议，以及它的实现 `DotenvSettings`（§3.6）。
- `entry/desktop/title.py`：标题生成。
- `server.py`：只加路由外壳，沿用 `_authorized`、`_read_json`、`_refused`。
- 纯函数都不依赖 FastAPI，所以在 rapids 解释器下也能测试。

**不能碰的**：`render.py`、`turn_observation.py` 与聊天契约都不改。

**错误形状**
- 请求体层面的拒绝沿用 `_read_json` 与 `_refused`，响应为 `{"detail": code}`：415 缺少 JSON 类型、413 请求体过大、400 `Content-Length` 不合法、422 JSON 解析失败。
- `/chat/title` 也一样。App 的 `parseFailureCode`（`session-title.ts:41-48`）在这些响应里读不到 `schema_version`，会把它们当作 `TITLE_PROVIDER_FAILED`。这是预期行为：只有路由自己的校验失败才返回 `TITLE_REQUEST_INVALID`。

### 3.2 `GET /skills` 与 `GET /skills/{domain}/{name}`

**目录**（形状以 `parseSkillCatalogResponse` 为准）

```json
{
  "domains": [
    {"domain": "spatial", "domain_name": "spatial", "primary_data_types": [],
     "skills": [
       {"name": "spatial-de", "description": "...", "domain": "spatial",
        "collection": "curated", "status": "ready"}
     ]}
  ],
  "total": 94
}
```

- **分组**：用 `SkillIndex.by_domain()`，保持索引顺序（App 另按自己的 `DOMAIN_ORDER` 排序）。
- **`domain_name`**：直接等于 `domain`。后端没有领域显示名，App 需要时可以另做 en/zh 映射，这不在本计划内。
- **`primary_data_types`**：固定为 `[]`。
- **`collection`**：固定为 `"curated"`。重建后的技能层没有 collection 字段（README:153）。
- **`status`**：固定为 `"ready"`。
- **`domain` 为空**：技能直接位于根目录下时 `Skill.domain == ""`。而 App 的 `requiredString` 要求非空，所以归入 `"general"`。今天的 94 个技能里没有这种情况（附录 B-1）。
- **不提供的字段**：`version`、`readiness`、`security`、`run_health`、`io`、`lifecycle_status`、`validation_level`。这些都是解析器的可选字段，省略即可。
- **`total`**：等于所有技能的条数，这是解析器校验的内容（`:195-196`）。

**详情**（`mergeSkillDetailResponse` 以目录里的身份为准，只从详情里补充可选字段）

```json
{
  "name": "spatial-de", "domain": "spatial", "description": "...",
  "aliases": [], "script_path": null, "tags": ["..."],
  "skill_md": "<SKILL.md 去掉 frontmatter 的正文>",
  "resources": [{"path": "scripts/run.py", "kind": "script"}, ...]
}
```

- **查找**：只按 `name` 在索引里查。找不到，或 `domain` 与该技能不符（空 domain 视为 `"general"`），返回 404 `{"detail":"skill_not_found"}`。
- **`skill_md`**：取 `get_full_content(name)`。读取失败（`OSError`、`UnicodeDecodeError`）时返回 `null`，不让整个请求失败。
- **`resources`**：`skill.directory` 下的普通文件，只给相对路径。
  - 不跟随符号链接，跳过隐藏文件与 `__pycache__`，最多 200 条，按路径排序。
  - `kind` 的判定：`.py`/`.R`/`.sh` 为 `script`；`references/` 下的文件为 `reference`；`.yaml`/`.yml`/`.json`/`.toml` 为 `config`；其余为 `doc`。
- **不回传任何绝对路径**：`Skill.path` 在绝对根目录下就是绝对路径，所以只用 `relative_path` 与相对于 `directory` 的路径。

### 3.3 `GET /mcp/servers`

一个形状同时满足 App 的两个读取方（E14）：

```json
{
  "servers": [
    {"name": "context7", "type": "stdio", "transport": "stdio",
     "command": "npx", "args": ["-y", "@upstash/context7-mcp"],
     "env": {"API_KEY": "••••"}, "enabled": true, "tools": ["resolve"],
     "state": "connected", "active": true, "error": ""},
    {"name": "remote", "type": "http", "transport": "http",
     "url": "https://example.org/mcp", "headers": {"Authorization": "••••"},
     "enabled": true, "state": "failed", "active": false, "error": "..."},
    {"name": "bad-entry", "state": "failed", "active": false,
     "error": "<RejectedServer.reason>"}
  ]
}
```

**来源**
- 配置取 `app.mcp.config`，也就是**本进程启动时实际使用的配置**，不重新读文件。编辑 `.mcp.json` 之后需要重启才能生效（0064 陷阱 24）。
- 状态取 `app.mcp.statuses()`，按名字合并。
- `app.mcp is None`（没有 `.mcp.json`）时返回 `{"servers": []}`。

**字段**
- `type` 与 `transport`：都取 `ServerConfig.kind.value`。
- `tools`：配置里的允许列表；为 `None` 时省略（App 显示"全部暴露"）。
- `active`：`state == "connected"`。
- `error`：截到 300 字符。

**展开后的值**
- `mcp/config.py:33-34` 写明：`${VAR}` 在 `command`、`args`、`env` 的值、`url`、`headers` 的值里都会展开。
- `app.mcp.config` 保存的是展开之后的值（`_parse_server`，`:208-230`）。被拒条目的 `reason` 里也可能带着展开后的 URL（`:224`）。
- 所以第 1 版的说法"`args`、`url` 就是用户自己写的原文"不成立：`${TOKEN}` 展开以后，令牌会出现在 `args` 或 `url` 里。

**遮蔽**（Q12 推荐 a）
- `env` 与 `headers`：只保留键，值一律换成 `"••••"`。
- `command`、`args`、`url`：显示 `.mcp.json` 里**未展开的原文**。
  - 原文从 `MCPConfig.source`（文件路径）重新读取一次，并按服务器名对应。
  - 文件读不到或解析失败时，这三个字段省略，其余字段照常返回。
  - 用户直接写在 `args` 里的字面密钥不遮蔽：那是用户自己工作区里的文件，这种写法本身就把密钥放在了明处。
- 被拒条目的 `error`：把其中出现的环境变量**值**替换成 `"••••"`，再截断到 300 字符。
  - 值取自 `settings.startup`，即启动时展开 `.mcp.json` 用的那份环境；只替换长度不少于 8 的值。
  - `settings=None` 时没有这份环境，被拒条目的 `error` 只给固定的 `"invalid_config"`，不回传原因。

### 3.4 `GET/PUT /providers` 与 `POST /providers/test`（0064-Q6 = a）

**设置文件的抽象**。`entry/desktop/providers.py` 定义协议 `SettingsFile`：

| 成员 | 含义 |
|---|---|
| `path: Path` | 写入目标，即 `dotenv_target()` |
| `candidates: tuple[Path, ...]` | `_adopt_dotenv` 依次加载的全部文件，即 `dotenv_candidates()`：`OMICSCLAW_DIR/.env`（或检出根目录）在前，`cwd/.env` 在后（`launch/__init__.py:196-203`） |
| `read() -> Mapping[str, str]` | 写入目标 `path` 里的变量；变量名规则（§3.4）用它判断"文件里已有哪种写法" |
| `write(updates) -> None` | 写入 `path`。键为变量名，值为 `str` 或 `None`（`None` 表示删除） |
| `exported: Mapping[str, str]` | 启动时 `_adopt_dotenv()` **之前**就已存在的环境变量 |
| `startup: Mapping[str, str]` | 启动那一刻、`_adopt_dotenv()` **之后**的真实环境快照，由 `launch` 注入，不重新读文件 |

- 生产实现是同一模块里的 `DotenvSettings`（§3.6）；测试注入一个内存实现。
- `create_desktop_app` 新增关键字参数 `settings: SettingsFile | None = None`。
  - 为 `None` 时，`PUT /providers` 与 `POST /providers/test` 返回 503 `{"detail":"settings_unavailable"}`。
  - `GET /providers` 仍然可用，但所有条目的 `configured` 都为假。

**"重启后会看到的环境"** 记作 M：
- 按 `candidates` 的顺序读取全部文件，**先加载的优先**（`override=False`，同一变量以第一个文件为准）；
- 然后叠加 `exported`，导出的变量优先于任何 `.env`（0064 陷阱 13）。
- 这正是下次启动时 `_adopt_dotenv` 之后的环境。Electron 下 cwd 是项目目录，项目里自带的 `.env` 也会被加载，所以只读 `dotenv_target()` 会算错。
- 写入目标仍然只有 `dotenv_target()`。它是第一个已存在的候选文件，在所有 `.env` 里优先级最高，所以写进去的值总会盖过其他候选文件里的同名变量；能盖过它的只有导出变量，那种情况列入 `shadowed_by_environment`。
- 不能用当前的进程环境代替：它已经混入了启动时从 `.env` 读进来的旧值，分不清哪些是用户自己导出的。

**两个三元组**（都求 provider、model、base_url）
- **运行中**：`resolve_config(app.config.provider, app.config.model, env=settings.startup)`，取它返回的 `provider`、`model`、`base_url` 三个字段。
  - 不用 `app.provider.name`：`app.provider` 被 `trace_provider` 包过（`assembly.py:1220`），它的名字虽然与内层一致，但比较的两侧应当来自同一个函数。
  - `model` 与 `effective_model(app)` 相同，所以与 `/health` 一致。
  - 显式传 `env=`，是因为 `entry` 不读进程环境（§2.4）。
- **重启后**：按 `AppConfig` 的顺序从 M 里取 provider 与 model（§2.1）：
  - provider = `M["OMICSCLAW_PROVIDER"]` 或 `M["LLM_PROVIDER"]`；
  - model = `M["OMICSCLAW_MODEL"]` 或 `M["LLM_MODEL"]`；
  - 然后 `resolve_config(provider, model, env=M)`。
- 比较的是两次 `resolve_config` 返回的 `ProviderConfig` 的 `provider`、`model`、`base_url` 三个字段；不同时，`restart_pending = true`。

**`GET /providers`**（形状以 `normalizeProviderInfo`、`buildProviderModelGroups`、`OmicsClawProviderSection`、`lib/onboarding/llm-providers.ts` 为准）

```json
{
  "providers": [
    {"name": "deepseek", "display_name": "DeepSeek", "tier": "primary",
     "base_url": "https://api.deepseek.com", "default_model": "deepseek-v4-flash",
     "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
     "model_metadata": [{"id": "deepseek-v4-pro", "context_window": 1000000}],
     "env_key": "DEEPSEEK_API_KEY",
     "configured": true, "configured_via": "provider-env", "active": true}
  ],
  "current": "deepseek", "current_model": "deepseek-v4-flash",
  "restart_pending": false, "env_file": "/path/to/.env"
}
```

- **顺序**：按 `DETECT_ORDER`，其余 preset 排在后面，与 CLI 向导一致（`_configure.py:545-553`）。
- **`base_url`**：preset 自带的端点。空串表示用 SDK 的缺省端点。
- **`model_metadata`**：只列出 `get_model_limits(id)` 不是 `DEFAULT_MODEL_LIMITS` 的模型，`context_window = context_tokens`。
- **`configured`**：满足以下任一条件即为真：
  - `resolve_config(name, env=M).api_key` 非空，与运行时的解析规则一致；
  - `ollama` 或 `custom` 满足下面 `explicit-provider` 的条件。

  注意：`LLM_PROVIDER` 未设置时，`resolve_config("custom", env=M)` 也会采用通用密钥（`provider/config.py:620-625` 的 `requested == "custom" and not env_provider`）。所以只要 M 里有 `LLM_API_KEY`，`custom` 就会显示为已配置。这是解析规则本身的行为，照实显示，并用测试钉住。
- **`configured_via`** 的取值：`M[preset.api_key_env]` 非空时为 `"provider-env"`；否则如果通用密钥变量生效，为 `"generic-env"`；`ollama` 与 `custom` 在 provider 指向它、且解析出非空 `base_url` 时为 `"explicit-provider"`。
  - 都不满足时，`configured = false`，`configured_via = null`。
- **`active`**：`name == app.provider.name`。
- **`current` / `current_model`**：运行中三元组的前两项，与 `/health` 一致。
- **`restart_pending`**：见上。`npm run dev` 下 App 用它提示"已保存，重启后生效"。
- **`env_file`**：`str(settings.path)`，是绝对路径。它与 S19"不回传绝对路径"并不矛盾：S19 管的是技能目录（可能暴露用户目录结构），而 `env_file` 是用户需要知道的配置位置（陷阱 3），算账见 §3.7 的 S12。
- **不出现的内容**：任何密钥的值、密钥的尾号、`description`/`description_zh`（preset 没有这两个字段）、`oauth_*`（OAuth 由 AD-8 删除）。

**`PUT /providers`**

请求为 `{provider, api_key?, model?, base_url?}`，也就是 `buildProviderSavePayload` 在 AD-8 删掉 `auth_mode` 之后的形状。

**校验**
- 出现其他键时返回 422 `unknown_field`，这样新路由不会悄悄接受后端忽略的字段。
- `provider` 必须是 `PRESETS` 的键，否则 422 `unknown_provider`。
- 各值都必须是字符串，不含控制字符（`\x00-\x1f`），长度不超过 4096，否则 422 `invalid_value`。
- `custom` 必须带非空的 `model` 与 `base_url`，与 App 的 `validateProviderSaveInput` 一致。

**写入语义**（逐项对照 CLI 向导 `_ask_llm`；有分歧的地方单列为 Q9、Q10）

| 项 | 规则 |
|---|---|
| provider 变量 | 文件里已有 `OMICSCLAW_PROVIDER` 时写它，否则写 `LLM_PROVIDER`（Q10 推荐 a）。原因：`AppConfig` 先读 `OMICSCLAW_PROVIDER`，只写 `LLM_PROVIDER` 的保存会不生效 |
| 密钥 | `api_key` 缺失或为空：不动已有密钥。非空时写入 `preset.api_key_env`；`custom` 或没有专属变量的 preset 写 `LLM_API_KEY`（Q9 推荐 a，与 CLI 的规范写法 `LLM_API_KEY` **不同**，理由见 Q9） |
| 模型变量 | 与 CLI 相同：文件里已有 `OMICSCLAW_MODEL` 时写它，否则写 `LLM_MODEL` |
| 端点变量 | 与 CLI 相同：依次看 `<PROVIDER>_BASE_URL`、`LLM_BASE_URL`、`OMICSCLAW_BASE_URL`，写已存在的第一个；都没有时写 `LLM_BASE_URL` |
| 换了 provider（新 provider ≠ 重启后三元组的 provider）且请求里没给 `model` | 模型变量写新 preset 的 `default_model`，与 CLI 相同 |
| 换了 provider 且请求里没给 `base_url` | 端点变量写空串，与 CLI 相同。防止旧厂商的 `LLM_BASE_URL` 在新厂商下生效 |
| provider 没变 | 只写请求里给出的字段；没给的字段不动 |

- 变量名规则写在 `entry/desktop/providers.py` 的 `provider_settings_updates(existing, *, provider, api_key, model, base_url, previous_provider)` 里，是纯函数。
- BM-3 的对照测试用 `StreamPrompter` 驱动 `run_configuration_wizard`，与这个函数在同一份初始 `.env` 上比较，断言二者写出相同的 provider、模型、端点变量，以及相同的"换 provider 时的清理"。
- 密钥变量按 Q9 的裁定断言：选 a 时，断言"只在密钥变量上与 CLI 不同"。

**成功**：200

```json
{"ok": true, "provider": "deepseek", "model": "deepseek-v4-pro",
 "restart_required": true, "env_file": "/path/.env",
 "written": ["LLM_PROVIDER", "DEEPSEEK_API_KEY", "LLM_MODEL", "LLM_BASE_URL"],
 "shadowed_by_environment": ["LLM_MODEL"]}
```

- `written` 只有变量名。
- `shadowed_by_environment` 列出两类名字：
  - `written` 里同时出现在 `settings.exported` 中的；
  - 优先级更高、且已导出的写法。例如导出了 `OMICSCLAW_MODEL` 而写的是 `LLM_MODEL`，或者导出了 `OMICSCLAW_PROVIDER`。

  重启后这些值**不会**生效，App 必须提示。

**失败**
- 写入时出现 `OSError` 或 `UnicodeDecodeError`：`write_dotenv` 读原文件时，非 UTF-8 内容会抛后者（`_configure.py:245`）。返回 500 `{"detail":"env_write_failed"}`，日志只记路径与异常类型，不记任何值。

**备份**：沿用 `write_dotenv` 的缺省 `backup=True`，与向导一致（陷阱 4）。

**`POST /providers/test`**
- **请求**：`{provider, model?, base_url?, api_key?}`。
  - App 诊断页现在发送 `provider`、`model`、`base_url`（`doctor/route.ts:270-279`）。
  - `api_key` 是可选的新字段，用于"用刚输入、尚未保存的密钥测试"。
- **求配置**：`resolve_config(provider, model, base_url=..., api_key=..., env=M)`，再覆盖 `max_retries=0`、`max_tokens=256`、`timeout_seconds=15`、`thinking_budget_tokens=0`。然后 `provider_for(config).generate([system, user "ping"], None)`，外面包一层 `asyncio.timeout(20)`。
- **通过的判据**：调用没有抛异常。正文是否为空不算失败，因为推理模型可能把额度都用在推理上，这不代表配置有问题。
- **端点与密钥不做绑定**（Q3 推荐 c，§3.7 的 S15）。
- **响应**（诊断页只看 `resp.ok && payload.ok`）
  - 成功：`{ok:true, message:"Live provider test passed.", provider, model, duration_ms}`。
  - 模型侧失败：HTTP 200，`{ok:false, message, detail, duration_ms}`。
    - `detail` 取异常类型名，以及 `ProviderError.status_code`（如果有）。
    - `message` 取异常信息的前 300 个字符，并把本次用到的密钥原文替换成 `"…"`。
  - 请求格式错误：422。

### 3.5 `POST /chat/title`（0064-Q9③）

**请求**：`{schema_version:1, source_request_id, user_text}`。
- `schema_version` 必须是 1；`source_request_id` 必须匹配 `^[0-9a-f]{32}$`；`user_text` 是非空字符串，且不超过 4096 个字符（App 的 `MAX_TITLE_INPUT_CHARS`）。
- 不满足时返回 422 `{"schema_version":1,"error":{"code":"TITLE_REQUEST_INVALID"}}`。
- **不校验** `source_request_id` 是否对应一个已知的回合（§3.7 的 S17）。
- 请求体层面的拒绝走 `{"detail":…}`，见 §3.1。

**生成**
- 调用一次 `app.provider.bind(max_tokens=1024, thinking_budget_tokens=0).generate([system, user], None)`，外面包 `asyncio.timeout(30)`。
  - `max_tokens` 给到 1024，是为了避免推理模型把额度全用在推理上、返回空正文，导致稳定的 502。
  - `thinking_budget_tokens=0` 只对支持它的 adapter 生效。
- system 提示："用与用户相同的语言，给这条消息起一个不超过 8 个词的标题，不加引号，不加句号"。
- 取第一个非空行，去掉空白与成对引号，截到 80 个字符。App 会再规范到 50 个字形（`chat-title.ts:83-90`）。

**响应**

| 情形 | HTTP | 载荷 |
|---|---|---|
| 成功 | 200 | `{schema_version:1, title}` |
| 结果为空 | 502 | `TITLE_OUTPUT_INVALID` |
| 超时 | 504 | `TITLE_TIMEOUT` |
| 其他异常 | 502 | `TITLE_PROVIDER_FAILED`，只记异常类型 |

- 失败时的载荷为 `{schema_version:1, error:{code}}`。
- 不实现 `TITLE_BUSY`、`TITLE_CONTEXT_*`：App 已经把它们当作普通失败处理。
- 用的是正在运行的 provider，所以标题和那个回合出自同一个后端，与旧契约"由服务该回合的运行时生成"一致。

### 3.6 `.env` 读写与启动快照：代码放在哪（Q1 推荐 d）

**`DotenvSettings` 放在 `entry/desktop/providers.py`**，经 `omicsclaw.entry.desktop.__all__` 公开导出。
- 构造参数：`DotenvSettings(path, *, candidates, exported, startup)`，全部由 `launch` 注入，构造时不读任何文件。
- `read()` 与 `write()` 在**方法体内** `from omicsclaw.entry.cli._configure import read_dotenv, write_dotenv`。
  - 这是 `entry` 层内部对兄弟模块的引用。
  - 写在函数体内，所以 `import omicsclaw.entry.desktop` 不会带入 `entry.cli` 及其依赖。实测：在已经 import `entry.desktop` 的进程里再 import `entry.cli._configure`，会多出 87 个模块，其中包括 `rich`（附录 B-4）。
  - 可选依赖守卫（fastapi、textual、prompt_toolkit、openai、anthropic）不受影响。
- `provider_settings_updates`（§3.4）也在这个模块里。

**`launch` 只负责构造与注入，不 import 任何私有名字**
- `_surfaces.py`：`from omicsclaw.entry.desktop import DotenvSettings, create_desktop_app`，这两个都是公开名字。
- `_serve_desktop` 增加参数 `settings`，传给 `create_desktop_app(app, bearer_token=token, settings=settings)`。
- 对第 1 版的改口：brief 说"`.env` 写入的公开函数放 `launch/**`"。放在 `launch` 会违反公开名字守卫（§2.4），所以改为"读写实现放在 `entry/desktop`，`.env` 的**定位**（`dotenv_target`）与启动快照仍然只在 `launch`"。

**启动快照怎样取、怎样传到 `start_desktop`**
- 在 `launch/__init__.py` 的 `main` 里：

  ```python
  if env is None:
      environment: Mapping[str, str] = os.environ   # 全包唯一一次读取，字面保持原样
      exported = frozenset(environment)
      _adopt_dotenv()
      environment = LaunchEnvironment(environment, exported)
  else:
      environment = env
  ```

  - 第一行必须逐字保留为 `environment: Mapping[str, str] = os.environ`：`test_the_shell_hands_both_globals_down_explicitly`（`test_launch_is_above_entry.py:159-168`）按字面检查这一行。
  - `_adopt_dotenv` 修改的正是这个对象，所以包装之后读到的仍然是加载 `.env` 之后的完整环境，其他 surface 的行为不变。
  - 语法树里仍然只有一个 `os.environ`，满足 `test_the_shell_reads_each_global_exactly_once`。
- `LaunchEnvironment` 定义在 `launch/_dotenv.py`：一个只读的 `Mapping[str, str]`，委托给被包装的环境。另有两个属性，都在构造时算好：
  - `exported_names: frozenset[str]`；
  - `startup: Mapping[str, str]`：构造那一刻（也就是 `_adopt_dotenv` 刚结束时）环境的只读副本，就是这次启动实际用到的环境。
- `_surfaces.start_desktop(deployment, surface, env)` 不改签名：
  - `env` 是 `LaunchEnvironment` 时，`names = env.exported_names`；
  - 否则（测试显式传入 `env`）`names = frozenset(env)`，也就是"整个映射都视为导出"，与 `main` 的 docstring 一致："显式给出 `env` 表示这就是全部部署环境，`.env` 不被读取"。
  - `exported = {k: env[k] for k in names if k in env}`。因为 `override=False`，这些键的值不会被 `.env` 改写。
  - `startup` 取 `env.startup`；测试显式传入 `env` 时取 `dict(env)`。**不重新读文件**：启动之后文件可能已经变了，而且只读 `dotenv_target()` 会漏掉 cwd 下的 `.env`。
  - `candidates` 取 `dotenv_candidates()`，`path` 取 `dotenv_target()`，两者都在 `launch` 里求，与 `_adopt_dotenv` 用的是同一个函数。
- `_surfaces.py` 里不出现 `os.environ`，满足 `test_only_the_shell_itself_names_the_two_globals`。
- 不用模块全局变量传递快照：`_surfaces` 与 `__init__` 互相 import 会形成循环。

**`.env` 的写入不会造成注入**
- `_serialise_value`（`_configure.py:117-129`）会给含空白或 `#` 的值加引号并转义换行，再加上 PUT 的控制字符校验，值里写不进第二个变量。
- 另一个需要知道的细节：加载器在装了 python-dotenv 时，缺省会对值里的 `${…}` 做插值（`common/runtime_env.py:79-86` 调用 `load_dotenv`，没有传 `interpolate=False`）。所以密钥里如果恰好含有 `${`，读回来的值会和写入的不同。这属于既有行为，CLI 向导也一样，本计划不改（陷阱 20）。

### 3.7 安全机制逐条算账

前提与 0064 §4.4 相同：单人、本机、default 权限模式；远程只经 SSH 隧道或直连，并带 bearer。DNS 重绑定已按 0064-Q4 作为已接受风险记录。**跨源网页发不出 JSON 写请求**：跨源 JSON 需要 CORS 预检，而后端不授予 CORS（`server.py:20-25`）。所以对写路由来说，除了 S11 以外，剩下的网页攻击者只有 DNS 重绑定。

| # | 机制 | 防什么 | 旁路 | 代价与收益 | 建议 |
|---|---|---|---|---|---|
| S10 | 新路由都走 `_authorized` | 远程模式下网络上的其他人 | 无 | 零代价，沿用 S4 | **做** |
| S11 | 三条写路由都只收 JSON（S3a） | 任意网页用 `text/plain` 简单请求写 `.env`、触发付费的测试调用或标题调用 | DNS 重绑定（已接受） | 零代价，沿用 `_read_json` | **做** |
| S12 | `GET /providers` 不回显密钥，也不回显尾号；但回显 `env_file` 的绝对路径 | 截屏、共享屏幕、App 日志或 SQLite 里出现密钥 | 能访问路由的一方本来就能读 `.env`（本机），或通过 agent 读取（远程，且需要审批） | 零代价；CLI 向导会显示尾 4 位，但 App 用"已配置"徽标就足够。`env_file` 暴露的只是一条路径，而用户需要知道配置写到了哪里（陷阱 3）；`/health` 已经回显工作区的绝对路径（`omicsclaw_dir`），它不会多泄露什么 | **做** |
| S13 | MCP：`env`/`headers` 的值遮蔽；`command`/`args`/`url` 显示未展开的原文；被拒条目的 `error` 里替换掉环境变量的值 | 同 S12。`${VAR}` 在五个字段里都会展开（`mcp/config.py:33-34`），所以展开后的 `args`/`url` 与被拒原因里都可能出现令牌 | 用户直接写在 `args`/`url` 里的字面令牌仍会显示，但那是用户自己文件里的明文；替换只覆盖长度不少于 8 的值 | 约 25 行，要多读一次 `.mcp.json` 原文 | **做**（Q12 推荐 a） |
| S14 | 0064 S9：非 `custom` preset 禁止修改 `base_url` | 能发 `PUT` 的一方把密钥导向别的主机 | 改用 `custom` 加 `LLM_API_KEY` 同样可以做到；本机进程可以直接改 `.env`；合法的镜像或代理端点会被误伤；CLI 向导允许修改 | 收益小，而且有误伤 | **不做**（Q2） |
| S15 | `POST /providers/test` 的端点与密钥绑定：请求的端点不同于**运行中**的端点、又没带密钥时拒绝 | 把已存密钥一步发往任意 URL。能发 JSON 的同机进程本来就能读 `.env`；跨源网页被 S11 挡住。**所以实际只防 DNS 重绑定**，而 0064-Q4 已经接受了这项风险 | 第 1 版写的是与 M 比较，那样可以先 `PUT {provider, base_url:evil}` 再 test 绕过。改成与运行中的端点比较后，这条旁路就只剩等重启生效（归 S16）。重绑定页面还可以把会话切到 `full_access`（0064-Q7 = a），再让 agent 外发 `.env`，只是不那么确定 | 约 5 行；UX 代价是重启之前测试新的镜像端点要重填密钥 | **不做**（Q3 推荐 c）：唯一的受益场景是一个已接受的风险，"更严"不作为缺省推荐 |
| S16 | `PUT /providers` 的同一规则（改端点必须同时给密钥） | 同上，但要等下次重启才生效 | 同上 | 约 5 行；每次改镜像地址都要重填密钥 | **不做**（Q3 的 a 选项才包含它） |
| S17 | 标题请求要求 `source_request_id` 对应一个已知的回合 | 把 `/chat/title` 当成免费的模型调用口 | 能发 JSON 的调用方本来就能驱动 `/chat/stream` | 需要跨路由维护状态 | **不做** |
| S18 | 标题并发上限（`TITLE_BUSY`） | 反复请求导致费用堆积 | 同 S17 | App 每个会话只调用一次 | **不做** |
| S19 | 技能详情只给相对路径，不跟随符号链接，最多 200 条 | 泄露用户主目录的绝对路径；符号链接把清单引到技能目录之外 | 按名字查找，路径不来自调用方，所以没有路径穿越 | 约 15 行 | **做** |
| S20 | 测试失败信息里替换掉密钥原文、截断 | 部分厂商的 401 信息会带上密钥片段 | 厂商也可能用别的方式编码密钥 | 两行 | **做** |
| S21 | `.env` 备份文件（沿用 `write_dotenv` 的 `backup=True`） | 保存写坏后可以恢复 | — | 备份里也有全部密钥，但保留原文件权限，和 CLI 向导一样 | 沿用；陷阱 4 |
| S22 | Outputs 删除后，是否继续读取 `settings.backend_output_dir` 并把它加入文件服务白名单（`path-security.ts:43-51, 127-130`） | 保留：旧会话里的图片仍能通过 `/api/files/*` 预览。删掉：白名单少一个根目录 | 这个值是旧后端写入的输出目录，删除后不再有写入方，成为一个固定不变的放行根。能利用它的一方要先能调用 App 的 Next API（本机进程，或 DNS 重绑定，已接受） | 保留零代价；删掉是一行，但旧会话的图片会失效 | **保留**（Q13 推荐 a） |

**不属于安全、但属于正确性的**：`shadowed_by_environment` 与 `restart_pending`。它们防的是"保存显示成功、实际什么都没变"（`launch/_dotenv.py` 模块 docstring 里描述的正是这种故障）。代价约 20 行。**做。**

### 3.8 契约与版本（Q4）

- 本计划的新路由**不纳入** `desktop_chat` 契约的版本号，也**不升** `sse_schema_version`：
  - 它们不改动任何已有路由的字段；
  - 后端与 App 按 0064 C3-4 在 0.2.0 一起发布；
  - `/chat/title` 的请求体本来就带 `schema_version: 1`。
- `SERVED_PATHS` 加上 `/skills`、`/skills/{domain}/{name}`、`/mcp/servers`、`/providers`、`/providers/test`、`/chat/title`。模板路径按 FastAPI 的写法登记。
- `wire_contract.py` 的模块 docstring 写明两类路由：受版本约束的聊天契约路由，以及随包版本发布的管理路由。
- 同步修改 `server.py` 与 `__init__.py` 的路由清单 docstring，以及 `DESKTOP_USAGE`。

### 3.9 App 侧设计

#### 3.9.1 Providers 页与向导的 LLM 步骤（AM-1）

**保存后的流程**
- 保存成功（后端返回 `restart_required: true`）之后：
  - **Electron**：复用 `project-switch.ts` 里现成的机制，即 `window.electronAPI.omicsclaw.restart()` 加 `waitForBackendHealth`。把它提取成共用助手 `restartBackendForSettings()`，放在 `lib/backend-restart.ts`，`switchProject` 与 Providers 共用。有流在跑时先请用户确认（同 `switchProject` 的第 1 步）。
  - **`npm run dev`**：toast 提示手动重启，命令用 `buildBackendManualCommand(workspace)`。页面依据 `restart_pending` 显示"已保存，重启后生效"。
- `shadowed_by_environment` 非空时，显示警告（en/zh）："这些变量已在环境中导出（如 shell 配置），会覆盖 `.env`，保存不会生效：<名字>"。
- 重启完成后派发 `provider-changed`，`BackendModelLabel` 重新读 `/health`。

**其他改动**
- `useLLMSetup.save` 走同一条路径。
- `api/providers/route.ts` 的 GET 已经转发状态码，保持不变。
- 设置页显示 `env_file`，告诉用户写到了哪个文件。
- `api/network/test/route.ts` 不改。按名字匹配到 provider 时它不会回落（§2.2）；只有名字匹配不到时才会探测第一个有 `base_url` 的 provider，而新的 GET 总是列出全部 preset，这种情况不会出现。
- **其他读取 `/api/providers` 的地方**（§2.2 表的最后一行）不需要改代码，但要纳入回归：
  - 向导按 `tier === 'primary'` 分组、默认选中第一个 `configured`；
  - 总览页与用量页的 provider 名称映射；
  - 为这几处补上以 §3.4 示例载荷为输入的单元测试。

**远程模式**：页面只读，提示"远端的模型配置需要在服务器上修改并重启"。写入留给计划 R（Q5）。

#### 3.9.2 Skills 页（AM-2）

- **`api/skills/route.ts`**：按后端状态码转发（现在一律返回 200）。
- **删除依赖已不存在字段的 UI**
  - 集合筛选：所有技能都是 `curated`。
  - 审计筛选：`undeclared`、`defects`、`deprecated`，逻辑在 `skill-sort.ts:109-117`、`SkillsWorkspace.tsx:121, 219, 296, 429-441`。
  - 排序里依赖 `run_health` 或 `security` 的键。
- **详情抽屉（`SkillDossier`、`SkillDocumentation`）**：只展示已有的数据，即描述、标签、SKILL.md 正文、大纲与文件清单。没有数据的分节整块隐藏，不显示空卡片。
- **"Try in Chat"** 保持不变。
- 技能治理与市场两个标签页分别由 AD-7、AD-6 删除。如果 AM-2 先于它们落地，只保证 catalog 标签页可用。

#### 3.9.3 MCP 页（AM-3，只读，0064-Q9④）

- `McpManager.tsx` 删除以下内容：添加与编辑对话框、删除按钮、JSON 编辑标签页，以及 `saveBackendServers`、`handleSave`、`handleDelete`、`handleJsonSave`。
- 页面标注"只读：编辑工作区的 `.mcp.json` 后重启后端"。
- `api/plugins/mcp/route.ts` 删除 POST、PUT、DELETE 与 `buildBackendCreatePayload`。`toSourcedConfig` 保留。
- 状态点改用 `state`（connected、failed、disabled、pending），并显示 `error`。实施时删除了 `api/plugins/mcp/status` 路由：它唯一的读取方是 MCP 页，而列表本身已带 `state`（M-B/M-C 独立评估同意）。
- **被拒条目**：现在的 `toSourcedConfig` 会丢掉 `state` 与 `error`，被拒条目会显示成一张空的 stdio 卡片。改为把 `state`、`error` 加进 `SourcedMcpServerConfig` 与卡片，被拒条目显示为"配置无效：<原因>"。
- 删除 `lib/mcp-config.ts` 里只用于写入的函数，以及 `types/index.ts:648-655` 的请求类型。

#### 3.9.4 Memory 页（AM-4，只隐藏，0064-Q9②）

- 从 `primary-nav.ts` 与 `ChatListPanel.tsx` 的 `NAV_ICONS`、`NAV_GROUP_DEFS` 里去掉 `memory`，并删除 `electron/menu.ts:96` 的 ⌘3。
- `app/memory/page.tsx` 与 `app/memory/review/page.tsx` 现在都是 `'use client'` 组件。改为不带 `'use client'` 的 server component，只调用 `next/navigation` 的 `redirect('/chat')`（Q6 推荐 a）。原来的页面内容移到 `components/memory/MemoryPage.tsx` 保留，供 Memory 计划恢复时使用。
- 组件、`api/memory/**` 与 `lib/memory-*` 原样保留，交给 Memory 计划。
- `src/__tests__/e2e/smoke.spec.ts:63-68` 的"memory page loads"改为断言会重定向。

#### 3.9.5 自动标题（AM-5）

App 的请求与解析已经符合 §3.5，不需要改代码。只做两项验证：
- 单元测试 `session-title.test.ts` 对照 §3.5 的全部状态码；
- 真机 §5.3 的 f 步。

### 3.10 App 删除清单（逐功能；每行一个提交）

通用规则
- **"只被它使用的"文案键**：删除前在 `src` 里对该键做字面与模板前缀两种检索。模板前缀如 `effort.`、`terminal.action.`、`bench.stage.`。
- **en/zh 同步**：`npm run typecheck:web` 通过即表示两边一致（§2.2）。
- **数据库表与迁移保留**：只删除调用方已经全部删除的访问函数。
- **`git grep` 验收**的范围是 `-- src electron scripts`，并排除 `src/lib/db.ts` 与 `src/__tests__/unit/db-*`，因为保留下来的 schema 注释会提到旧路由。表中每条 grep 都必须为空。表格里的 `\|` 是 Markdown 转义，实际命令里写 `|`。
- **注释里的误报**：删除时把下列注释一并改掉（写法改成不含旧路由），而不是在 grep 里加豁免：
  - `src/lib/git/service.ts:57`（提到 `omicsclaw/autoagent/__init__.py`）；
  - `src/app/layout.tsx:83`、`src/lib/path-security.ts:219`（提到 `/notebook`）；
  - `src/components/chat/MessageItem.tsx:357`（注释提到 `AskUserCard`；这段过滤逻辑本身保留）、`src/lib/preflight-guidance.ts:59`（注释提到 `preflight_pending`）——AD-13；
  - `db.ts:321, 3308`（提到 `/api/autoagent/start`）——db.ts 本来就被排除。
- **不属于该功能、但名字相同的字段**：`types/index.ts:871` 的 `PluginInfo.marketplace`。AD-6 的 grep 用 `-- ':!src/types/index.ts'` 排除这一行所在的文件，并单独确认 `types/index.ts` 里只剩这一处。
- **每个 AD 还要加一条文案键前缀检索**，在 `src/i18n/en.ts` 与 `zh.ts` 里必须为空：`git grep -nE "^\s*'(<前缀>)" -- src/i18n`。例如 AD-3 用 `nav\.bench|bench\.`，AD-1 用 `nav\.autoAgent|autoagent\.`。各 AD 的前缀写在表的最后一列。

| ID | 功能 | 删除范围（要点；完整清单见附录 A） | 必须保留或需要先迁出的 | `git grep -nE` 验收串（必须为空） |
|---|---|---|---|---|
| AD-1 | AutoAgent/Optimize | `app/optimize/`；`api/autoagent/**`（10 个）；`components/optimize/**`；`hooks/useOptimizeStream.ts`；`lib/autoagent-*.ts`（6 个）与 `lib/optimize/`；`src/instrumentation.ts`（整个文件都是对账逻辑）；`backend-fetch.ts` 中的 autoagent 部分（import `:26, :31`；`:542-555`；`:1013-1397`）；`internal/tunnel-binding/route.ts:4, 209-213`；`AppShell.tsx:29, 100-110, 820-829`；`types/index.ts:1276-1292`；nav 与图标；en/zh 的 `nav.autoAgent` 与 `autoagent.*`；19 个单元测试；需要修改的测试 3 个 | `components/git/*`、`useGitStatus`、`lib/bounded-json-request` 与 `backend-fetch` 的通用控制机制；db 迁移测试 | `/autoagent/\|autoagent-\|useOptimizeStream\|components/optimize\|lib/optimize\|'/optimize'`；键前缀 `nav\.autoAgent\|autoagent\.\|omics\.capability\.autoagent` |
| AD-2 | KG explorer（先于 AD-3） | `app/kg-explorer/`；`api/kg/**`（14 个）；`components/kg/**`；`hooks/useKGStatus.ts`；`types/kg.ts`；`bench-api-client.ts` 里的 kg 函数；`/health.kg`（`backend-health.ts:6-12, 60, 187-194, 294`）；设置总览里的 KG 子系统（`useOverviewData.ts`、`HealthSection.tsx:22`、`overviewCards.tsx:61, 227-231`）；en/zh 的 `kg.*`、`nav.kgExplorer`、`overview.subKg`/`kgErrorLabel`；测试 | — | `/kg/\|/api/kg\|kg-explorer\|useKGStatus\|BackendKGStatus\|normalizeKGStatus\|types/kg\|components/kg\|nav\.kgExplorer`；键前缀 `kg\.\|nav\.kgExplorer\|overview\.(subKg\|kgErrorLabel)` |
| AD-3 | Bench/Thread | `app/bench/**`；`api/thread/**`、`api/onboard/**`、`api/preference/bench`（共 16 个）；`components/bench/**`；`hooks/useThread*.ts`；`lib/bench/`、`lib/bench-*.ts`（此时已无其他使用者）；`types/bench.ts`；`usePersistedPanelWidth.ts`；聊天链路里的 `thread_id`/`stage`（`api/chat/route.ts:356-357, 549-560, 739-742`；`stream-session-manager.ts:143-146, 762-763`；`ChatView.tsx` 的 bench 属性）；`MessageItem.tsx` 的阶段徽标；`AppShell.tsx:179-184`；en/zh 的 `bench.*`；smoke 中的 Bench 块（`:30-35, 78-202`）；测试 | **`lib/onboarding/`**（E5）；`<!--stage:` 标记的剥离逻辑按 Q7 处理 | `/api/(thread\|onboard)\|/onboard/(skip\|status\|user)\|bench/onboard\|preference/bench\|types/bench\|bench-(api-client\|proxy\|last-thread\|thread-session)\|components/bench\|useThread(Artifacts\|Hypotheses\|Sources)\|threadId\|thread_id\|['"/]bench['"/]`（不能用单独的 `/onboard`：它会匹配 `@/lib/onboarding/` 的 import；`bench/onboard` 用来抓 smoke 里的 `'/bench/onboard'`）；键前缀 `nav\.bench\|bench\.` |
| AD-4 | Notebook | `app/notebook/`；`api/notebook/**`（12 个加 `proxy.ts`）；`components/notebook/**` 中除 `CellOutput.tsx` 以外的文件；`lib/notebook/` 中除下列三项以外的文件；`backend-contract.ts:70-84`；`message-input-logic.ts:18, 22-24, 124-136`；`useSlashCommands.ts` 的 `onOpenNotebook`；nav 与 ⌘2；en/zh 的 `notebook.*`（`output.showMore`/`showLess` 除外）与 `nav.notebook`；`docs/NOTEBOOK_FEATURE.md`；测试 | **先迁出**：`CellOutput.tsx` 移到 `components/project/viewers/`；`lib/notebook/ipynb.ts` 移到 `lib/ipynb.ts`；`http.ts` 的两个导航函数移到 `lib/navigation-href.ts`；聊天与文件预览里 `.ipynb` 的跳转改为打开预览面板（`getNotebookRouteForFile` 的 6 处调用方） | PCRE：`git grep -nP "/notebook(?!s)\|@/(lib\|components)/notebook\|backend_missing_notebook_routes\|navigate_notebook\|getNotebookRouteForFile\|nav\.notebook"`；键前缀 `notebook\.(?!output\.show)\|nav\.notebook\|chat\.file\.openNotebook` |
| AD-5 | 回放与晋升（先于 AD-7） | `api/runs/[runId]/replay`；`SkillReplayCard.tsx`；`canonical-run-replay.ts`；`skill-promotion.ts`；`SkillPromotionCard.tsx`；`ChatActionsContext.tsx`；聊天中的 `skill_promotion` 管道（`MessageItem.tsx`、`StreamingMessage.tsx`、`ChatView.tsx:761-786`、`chat-stream-transcript.ts:208, 233, 320`、`types/index.ts:417-427, 434, 1318`）；en/zh 的 `chat.skillPromotion.*`、`chat.skillReplay.*`；测试 | 已持久化的旧转录里的 `skill_promotion` 字段不再读取即可，无需迁移 | `SkillReplayCard\|SkillPromotion\|canonical-run-replay\|skill-promotion\|skill_promotion\|convertAnalysisToSkill\|ChatActions\|api/runs\|/v1/runs`；键前缀 `chat\.skillPromotion\|chat\.skillReplay` |
| AD-6 | 市场（先于 AD-7） | `api/skills/marketplace/**`（4 个，背后是后端的 `/skills/installed`、`/skills/install`、`/skills/uninstall`）；`lib/marketplace-skills.ts`；`lib/skills/install-progress-stream.ts`；`Marketplace*.tsx`、`InstallProgressDialog.tsx`；`SkillsWorkspace.tsx` 的 marketplace 分支；en/zh 的市场相关键；测试 | `skills.collection.*` 键在 AM-2 删除集合筛选后再判断去留 | `marketplace\|Marketplace\|InstallProgress\|install-progress\|/skills/(installed\|install\|uninstall)`，排除 `src/types/index.ts`（`PluginInfo.marketplace`）；键前缀 `skills\.(marketplace\|install\|uninstall\|acqBanner\|marketStageNote\|noReadme\|searchNoResults)` |
| AD-7 | 技能治理与 fd-3 | `api/skill-evolution/**`（7 个文件）；`SkillEvolution*`、`SkillMaintenanceQueue`、`SkillProposalDetail`、`SkillExperienceDetail`、`skill-evolution-client.ts`、`SkillWorkspaceTabs.tsx`；`lib/skill-evolution-auth.ts`、`electron/skill-evolution-auth.ts`、`electron/next-server-bootstrap{,-core}.ts`；`main.ts:14-17, 90-93, 1068, 1301-1303, 1332, 1339-1348`（改为直接 fork `standalone/server.js`）；`python-manager.ts` 的 stdio 改回 3 项（`:398`）、删除 `:238-241` 的 fd 指针、`:506-537` 的交接、`skillEvolutionToken` 参数（`:302, 314, 325, 334, 373`），以及 **`lastSkillEvolutionToken`（`:287`）**。它同时是崩溃自动重启的前置条件（`handleCrash` 的 `:1064`、重启参数 `:1090`），要一起删掉，否则崩溃之后永远不会自动重启；显式重启走 `activateCommittedRuntime`（`main.ts:1882-1888`），不受影响；**`src/lib/backend.ts:38` 对 `backendFetchWithSkillEvolutionAuthority` 的重新导出**；`local-runtime-plan.ts:33, 91, 166`；`runtime-supervisor.ts:96, 211`；`scripts/electron-build-entries.mjs:10-13`；`backend-fetch.ts:1465-1523`；`skills/types.ts:151-309`、`skill-meta.tsx:151-172`；`process-env.ts:4-5` 的两个清洗名；`CONTEXT.md:35-41` 的两个术语；en/zh 的相关键；测试（`python-manager.test.ts` 里 14 处 stdio 相关，其中伪造的子进程用的是 4 项 stdio，另有"缺少权限管道"等用例） | **保留** `bootstrapMainProcessConfirmSecret`（`main.ts:1249-1256`）及其调用点 `:1572`、`:2202`、`:2226`；`api/internal/main-process-secret` | `skill-evolution\|skillEvolution\|SkillEvolution\|SKILL_EVOLUTION\|next-server-bootstrap\|validation-review\|validationReview\|stdio\[3\]\|TOKEN_FD`（如果按表中所写删除了 `process-env.ts` 的两个清洗名，就不需要排除）；键前缀 `skills\.(validationReview\|workspaceViews\|maintenance\|audit)` |
| AD-8 | OAuth（先于 AM-1） | `api/auth/[provider]/**`（3 个）；`ProviderRowEditor.tsx:141-267, 326-443` 的 OAuth 部分；`OmicsClawProviderSection.tsx` 的 `AuthMode`；`provider-settings.ts:12-18, 60-68` 的 `auth_mode`；`types/index.ts:520-521` 与 `providers/doctor/route.ts:109-110`、`lib/provider-doctor.ts:191` 的 `oauth_*`；en/zh 的 `settings.authMode*`/`oauth*` | — | `api/auth/\|oauth_supported\|oauth_authenticated\|auth_mode\|startOAuthLogin\|authModeApiKey`；键前缀 `settings\.(authMode\|oauth)` |
| AD-9 | CLI 设置 | `api/settings/route.ts`（整个文件都是 `/claude/settings` 的代理）；`CliSettingsSection.tsx`；`SettingsLayout.tsx:18, 36, 91-97, 123, 263-264`；`overviewCards.tsx:39`；en/zh 的 `cli.*`、`settings.claudeCli`/`cliNav`/`cliSectionDesc`；测试 | `api/settings/app`、`api/settings/workspace` | `claude/settings\|CliSettings\|settings\.cli\|claudeCli`；键前缀 `cli\.\|settings\.(claudeCli\|cliNav\|cliSectionDesc)` |
| AD-10 | Bridge（0064-Q9①） | `app/bridge/`；`api/bridge/**`（3 个）；`components/bridge/**`；`api/settings/{discord,feishu,qq}` 及各自的 `verify`（6 个，没有 UI 使用者）；nav 与图标；`types/index.ts:1577-1600`；`eslint.config.mjs:60, 103`；en/zh 的 `bridge.*`、`telegram.*`、`feishu.*`、`discord.*`、`qq.*`、`weixin.*`、`channels.*`、`nav.bridge`；README 中 Bridge 一节；测试 | `settings` 表里的 `bridge_*` 行保留 | `components/bridge\|BridgeManager\|ChannelConfigDialog\|api/bridge\|nav\.bridge\|bridge_(discord\|feishu\|qq)\|settings/(discord\|feishu\|qq)\|Weixin`；键前缀 `nav\.bridge\|bridge\.\|telegram\.\|feishu\.\|discord\.\|qq\.\|weixin\.\|channels\.` |
| AD-11 | Outputs（0064-Q9⑤；在 AD-1 之后） | `OutputPanel.tsx`；`api/outputs/**`（3 个）；`lib/chat/run-link.ts`；`lib/output-file-tree.ts`；`api/chat/route.ts:13, 17, 1008-1032` 的 run-link 块（保留 `transcript.consumeEvent`）；`path-security.ts:65-78` 的 `cacheBackendOutputDir`；工作区的 results 标签（`usePanel.ts:10, 27-28`、`AppShell.tsx:201, 206-238, 749-750, 783`、`WorkspaceTabBar.tsx:28`、`RightPanel.tsx:8, 679`、`chat/[id]/page.tsx:31, 207-217`、`GeneralSection.tsx:80`）；**已保存的 `default_panel = 'dashboard'` 的兜底**：`chat/[id]/page.tsx:203` 读到不认识的值时回落到 `file_tree`，并加单元测试；`MediaPreview.tsx` 的 `onOpenOutputs`；db 中 run_meta 的写入与读取函数；en/zh 的 `outputs.*`、`dashboard.*`、`topBar.dashboard`；测试 | `run_meta`、`pending_run_meta` 两张表；`path-security.ts:43-51, 127-130` 对 `backend_output_dir` 的读取**保留**（Q13 推荐 a，算账见 §3.7 的 S22） | `OutputPanel\|api/outputs\|run-link\|parseRunLinkFromToolResult\|output-file-tree\|cacheBackendOutputDir\|upsertRunMeta\|onOpenOutputs\|dashboardPanelOpen`；键前缀 `outputs\.\|dashboard\.\|topBar\.dashboard\|settings\.defaultPanelDashboard` |
| AD-12 | 远程死代码（datasets、artifacts、Env 自适应） | `lib/remote-datasets-{adapter,proxy}.ts`、`remote-artifacts-proxy.ts`、`artifacts.ts`、`dataset-remote-path.ts`、`dataset-fingerprint.ts`、`adaptive-env-proxy.ts`；`api/env/{adaptive-mode,overlays}`；`AdaptiveEnvPanel.tsx` 与 `HealthSection.tsx:12, 45-46`；`ChatListPanel.tsx:178-180` 的 jobs/datasets/artifacts 图标；`types/index.ts` 的 `DatasetStatus`、`DatasetRef`、`DatasetInput`；db 中 datasets 的访问函数（`db.ts:2728-2860`）；测试 | **保留** `api/env/doctor`、`lib/env-doctor.ts`；`remote-jobs-*`、`remote-sse-adapter`、`remote-proxy-bootstrap`（留给计划 R）；`DatasetExecutionTarget`；`datasets` 表 | `remote-datasets\|remote-artifacts\|adaptive-env-proxy\|AdaptiveEnvPanel\|api/env/(overlays\|adaptive-mode)\|dataset-remote-path\|dataset-fingerprint\|listDatasets\|/v1/runs`（`AdaptiveEnvPanel` 用的是硬编码字符串，没有文案键） |
| AD-13 | 聊天死分支（M-D） | `useSSEStream.ts` 的 6 个 case、`_progress`、`tool_result.media` 的流式读取、`status` 里的非压缩分支；**`tool_timeout` 变体**（只删这一个变体：`turn-termination.ts` 的 `tool_timeout` 分支 `:5, :44-46`，`TerminalStateChip.tsx:52, 64` 对它的渲染，`stream-session-manager.ts:223-225, 447, 997-1034, 1098`，`new-chat-submission.ts:97-102` 的隔离，`chat-stream-transcript.ts:22, 116-119, 354-362, 382-384`，`api/chat/route.ts:284-290, 324-327`，`interrupt/route.ts:65-77`，`chat-stream-stop-registry.ts:17`，en/zh 的 `terminal.tool_timeout`）；skill-log（`SkillLogPanel.tsx` 与 `types/index.ts:796-816`）；`AskUserCard.tsx` 与 ask-user 仓库；`PermissionPrompt.tsx` 里的 `AskUserQuestionUI`/`ExitPlanModeUI`；模式选择器（`ModeIndicator.tsx`、`api/chat/mode`、`handleModeChange`）；`pathology` 相关；`preflight_pending` 的帧处理 | **保留**：`turn-termination.ts`、`TerminalStateChip.tsx` 本身，它们承载仍然有效的错误芯片（`CONTEXT_TOO_LONG`、`RATE_LIMITED`、`NO_CREDENTIALS` 等，`turn-termination.ts:23-31`）；`MessageItem.tsx:357-359` 对旧转录中 `ask_user` 工具行的过滤；已持久化 `media` 的渲染（`MessageItem.tsx:111, 157`、`MediaBlock`、`MediaPreview`）；`parsePreflightGuidance` 的文本回退；sessions 表的 `mode` 列 | `tool_log\|'tool_timeout'\|kind: 'tool_timeout'\|mode_changed\|ask_user_question\|preflight_pending\|pathology_detected\|AskUserCard\|ExitPlanModeUI\|AskUserQuestionUI\|ModeIndicator\|SkillLogPanel`；键前缀 `terminal\.tool_timeout\|chat\.pathology\|messageInput\.mode` |

**删除之后的导航**：主导航只剩 `runtimes`、`skills`、`mcp`。`NAV_GROUP_DEFS` 合并为一组，或者保留"工作区"一组；由实施者决定并在 PR 说明里写明。Go 菜单只剩 Chat ⌘1 与 Skills，后者改为 ⌘2。

### 3.11 P1 遗留清理（AC-1）与 `/compact` 留痕（AC-2，可选）

**AC-1：后端会忽略的请求字段与死代码**
- `/api/chat` 发给后端的请求体（`api/chat/route.ts:714-743`）只保留后端读取的字段：`ingress`（版本号、`source_request_id`、`installation_id`）、`session_id`、`content`、`workspace`、`permission_profile`。删除 `model`、`mode`、`provider_id`、`effort`、`thinking`、`context_1m`、`system_prompt_append`（`thread_id`、`stage` 已在 AD-3 删除）。
- **effort**：`EffortSelector.tsx`、`claude-model-options.ts`，以及它们在 `MessageInput`、`ChatView`、`page.tsx`、`stream-session-manager.ts` 里的连线；en/zh 的 `effort.*`；测试。
- **1M 上下文**：`ChatView`/`page.tsx` 的开关与 `enable-1m` 这一个终端动作（`turn-termination.ts:13, 20, 26` 与 `is1mActive`；文件本身保留，理由同 AD-13）、`applyContext1mBeta`、`useSessionContextUsage.ts` 的 `context1m` 参数、`/api/providers/options` 里只为 `thinking_mode`/`context_1m` 做的读取（`ChatView.tsx:211-225`、`page.tsx:146-160`）；`terminal.action.enable-1m`。
- **CLI 徽标与 `systemPromptAppend`**：`cliBadge` 从来不会被设成非空值。删除 `useCommandBadge.ts` 的 cli 部分、`buildCliAppend`、`CliBadge`、`PopoverMode 'cli'`、`message-input-logic.ts` 中走不到的 `set_badge` 分支，以及 `systemPromptAppend` 的整条传参链。
- **`buildQuickSwitcherModels`**：`lib/provider-model-catalog.ts:3-7, 25-57` 与它的测试；保留 `getProviderModelOptions`、`getProviderDefaultModel`、`buildProviderModelGroups`。
- **ChatView**：`initMetaRef`（`:287, 745-748`）、`hasSummary`（`:197`），以及对"上下文已压缩"旧字符串的检查（`:401-404`）；`db.ts` 中没有调用方的 `updateSessionSummary`。
- **斜杠菜单残留**：`usePopoverState.ts:59-147` 的 AI 建议、`api/skills/search/route.ts`、`SlashCommandPopover.tsx:237-282` 里永远为空的分组与"管理技能"页脚、`PopoverItem` 上技能相关的字段。
- **未使用的文案键**：`messageInput.{attachFiles,skillsDesc,runDesc,memoryDesc,aiSuggested}`、`composer.{slashCommand*,addFileContext*,searchModels,manageProviders,designAgent*,manageSkills}`、`permission.sessionPermission`、`context.*`（旧的上下文弹层）、`tool.{running,success,error}`、`provider.modelName`、`chat.background.{badge,completedToastBody}`、`chat.diffSummary.modified`。
  - 全仓大约有 1,100 个 en 键没有字面引用，但其中很多是通过模板前缀使用的。**本计划只删上面列出的键和各 AD 任务涉及的键**，不做全仓清扫。
- **按会话选模型的其余管道不在本任务内**：`resolveSessionModel`、`/api/providers/models`、会话表的 `model` 列。上下文用量表依赖它们来确定窗口大小，这里只停止把 `model` 发给后端（§6 陷阱 9）。

**AC-2：`/compact` 刷新后留痕**（可选，Q8）
- 现状：压缩结果只弹 toast。服务端的 `ChatStreamTranscriptBuilder` 只记一个布尔值，`buildPersistedAssistantMessageContent` 对空的压缩回合返回 `null`，所以刷新之后只剩一条用户消息 `/compact`。
- 做法：
  1. `chat-stream-transcript.ts:349-351` 保存压缩统计（`msgs_before`/`msgs_after`、`tokens_before`/`tokens_after`、`degraded`、`written_back`），把 `readCompactionStatus` 移到共享的 lib 里。
  2. 回合没有文本、没有工具时，持久化一个 `[{type:"compaction", messagesCompressed, tokensSaved, degraded, writtenBack}]` 块。
  3. `types/index.ts` 的 `MessageContentBlock` 加上这个变体。
  4. `MessageItem.tsx` 用 `buildContextCompressedNotice`（`lib/context-compression-notice.ts`）渲染成一行提示，文案仍走 `chat.contextCompressed.*`。
- 不需要数据库迁移：`role` 仍是 `assistant`（`db.ts:183` 的 CHECK 只允许 user 和 assistant）。旧会话里未知的块类型本来就会被跳过。

### 3.12 实现约定（沿用 0064 §4.11）

- **注释**：docstring 只说明是什么、做什么；理由写在本计划或测试的 docstring 里。
- **后端**
  - 新模块只 import `entry` 的公开名字、`omicsclaw.provider`、`omicsclaw.skills`、`omicsclaw.mcp` 的公开名字；唯一的例外是 `DotenvSettings` 在方法体内对 `entry.cli._configure` 的引用（Q1-d）；
  - `launch` 只 import `omicsclaw.entry.*` 的公开名字（守卫测试，§2.4）；
  - 不读 `os.environ`；fastapi 只在 `create_desktop_app` 里 import；
  - `server.py` 继续不启用 `from __future__ import annotations`。新模块如果把路由定义在函数里，同样受 `test_desktop_route_guard.py` 约束。
- **App**
  - 遵循 SPEC：直接改，不加兼容层；文案 en/zh 同步；测试放在 `src/__tests__/`；两条开发路径都要考虑；每个里程碑写进 `PROJECT_MEMORY`；不 push。
  - 每个 AD 任务一个提交，提交信息里写上它的 `git grep` 验收串及结果。

---

## 4. 分期与任务

### 4.1 依赖图

```
后端：BM-3（providers，含 DotenvSettings）→ BM-5（启动快照与注入）
      BM-1、BM-2、BM-4 互不依赖，也不依赖 BM-3/BM-5
      BM-1、BM-2、BM-3、BM-4 → BM-6（SERVED_PATHS、文档）

App： 前置：P0/P1 已提交（Q11；或在独立的 worktree 里开发，之后再 rebase）
      AD-8（OAuth）→ AM-1（Providers）      ← 验收需要 BM-3 + BM-5
      AM-2（Skills）                        ← 验收需要 BM-1
      AM-3（MCP 只读）                      ← 验收需要 BM-2
      AM-4（Memory 隐藏）、AM-5（标题）      ← AM-5 验收需要 BM-4
      AD-1 → AD-11；AD-2 → AD-3；AD-5、AD-6 → AD-7
      AD-3 → AD-4 → AD-13 → AC-1 → AC-2（都改聊天相关的同一批文件，必须串行）
      其余 AD 互不依赖，但都改 i18n、primary-nav、ChatListPanel，在同一工作树里按顺序提交
```

**可以并行的**
- 后端整条线（BM-*）与 App 整条线。
- App 里 AM 页面先用替身载荷开发（单元测试用 §3.2–§3.5 的示例载荷），不必等后端。
- 如果用多个 worktree 并行做 AD，必须按上面的依赖顺序 rebase；共享的 i18n 文件冲突多，**建议串行**。

### 4.2 后端（BM）

后端改动只在 `entry/desktop/**`、`launch/**`、`tests/**` 与文档里（§2.4）。

- **BM-1 Skills 路由**
  - `catalog.py`：`skill_catalog`、`skill_detail`（§3.2）。`server.py` 加两条 GET 路由。
  - 测试 `tests/entry/test_desktop_catalog.py`（纯函数，rapids 解释器）：
    - 手工构造的 `SkillIndex` 分组与顺序；`total`；
    - 空 domain 归入 `general`；
    - 详情 404（名字不存在，或 domain 不符）；
    - `skill_md` 读取失败时为 `null`；
    - `resources` 只有相对路径、不跟随符号链接、上限 200、跳过隐藏文件。
  - HTTP 测试（OmicsClaw 解释器）：两条路由的状态码与形状；配置了 bearer 时返回 401。
- **BM-2 MCP 路由**
  - `catalog.mcp_servers`（§3.3），`server.py` 加 GET 路由。
  - 测试：
    - 用 `MCPConfig`/`ServerStatus` 构造合并结果；rejected 条目；`app.mcp is None`；
    - `env`/`headers` 的值被遮蔽、键保留；
    - `.mcp.json` 里写 `${TOKEN}` 时，`args`/`url` 返回的是未展开的原文，展开后的令牌不出现在响应里；
    - 原文文件读不到时，这三个字段省略；
    - 被拒条目的 `error` 里，环境变量的值被替换掉。
- **BM-3 Providers 路由**
  - `providers.py`：`SettingsFile` 协议、`DotenvSettings`、`provider_settings_updates`、`provider_listing`、`save_provider`、`test_provider`（§3.4、§3.6）；`__init__.py` 导出 `DotenvSettings`；`server.py` 加 3 条路由；`create_desktop_app` 增加 `settings=`。
  - 测试 `tests/entry/test_desktop_providers.py`（内存实现的 `SettingsFile`，rapids 解释器）：
    - `configured`/`configured_via` 的各分支；导出变量优先于文件；M 按候选文件先加载者优先合并；`LLM_PROVIDER` 未设置而 M 里有 `LLM_API_KEY` 时，`custom` 显示为已配置；
    - 运行中三元组用 `settings.startup` 求，文件在启动后被改动也不影响它；
    - 文件里有 `OMICSCLAW_PROVIDER` 时，重启后三元组按它求，PUT 也写它（Q10）；
    - 响应里没有任何密钥原文（对整个 JSON 做子串断言）；
    - `restart_pending`；
    - PUT 的 `unknown_provider`、`unknown_field`、`invalid_value`、`custom` 缺字段；
    - `api_key` 为空时不改动已有密钥；密钥写入的变量名（按 Q9 的裁定）；换 provider 时模型写新 preset 的缺省值、端点写空串；`shadowed_by_environment`（包括优先级更高的写法已被导出的情形）；
    - `DotenvSettings` 读写 `tmp_path` 里的 `.env`：只改动指定的键，其余行原样保留；非 UTF-8 文件返回 500 `env_write_failed`，文件不变；
    - **对照测试**：用 `StreamPrompter` 驱动 `run_configuration_wizard`，与 `provider_settings_updates` 在同一份初始 `.env` 上比较（§3.4）；
    - `import omicsclaw.entry.desktop` 之后 `sys.modules` 里没有 `omicsclaw.entry.cli`（子进程探针），钉住"在函数体内 import"；
    - test 路由的通过判据是调用没有抛异常，空正文也算通过；
    - 失败信息里替换掉密钥原文；用脚本化的 provider 覆盖超时与异常。
  - HTTP 测试：`text/plain` 返回 415；缺少 Content-Type 返回 415；`settings=None` 时返回 503。
- **BM-4 标题路由**
  - `title.py`（§3.5），`server.py` 加路由。
  - 测试（脚本化 provider）：成功；bind 参数里有 `max_tokens=1024`；空输出返回 502 `TITLE_OUTPUT_INVALID`；超时返回 504（把超时参数调小）；异常返回 502；各种非法请求返回 422 `TITLE_REQUEST_INVALID`；`text/plain` 返回 415 `{"detail":…}`（§3.1）。
- **BM-5 启动快照与注入**（§3.6）
  - `launch/_dotenv.py`：`LaunchEnvironment`。
  - `launch/__init__.py`：`main` 里取快照，全包仍然只读一次 `os.environ`。
  - `_surfaces.start_desktop` 从传入的 `env` 求 `exported`，构造 `DotenvSettings(dotenv_target(), exported=...)`；`_serve_desktop` 增加 `settings` 参数并注入；更新 `DESKTOP_USAGE`（补上 P1 与本计划的路由）。
  - 测试 `tests/launch/test_desktop_settings.py`（rapids 解释器，不起服务）：
    - 快照只包含 `_adopt_dotenv` 之前就存在的变量，`.env` 带进来的不算；
    - 显式传 `env` 时，整个映射都视为导出；
    - 仓库自己的 `.env` 不被触碰（沿用 `test_configure_command.py` 的做法）；
    - `LaunchEnvironment.startup` 包含 `cwd/.env` 里的变量（两个候选文件各放一个变量，同名变量以先加载的为准）；
    - 已有的守卫测试原样通过：`test_the_shell_hands_both_globals_down_explicitly`、`test_the_shell_reads_each_global_exactly_once`、`test_only_the_shell_itself_names_the_two_globals`、`test_the_shell_imports_only_public_names_of_the_entry_layer`。
- **BM-6 契约与文档**
  - `wire_contract.py`：`SERVED_PATHS` 与 docstring（§3.8）；`test_desktop_wire_contract.py:104` 同步修改。
  - `docs/core-features/surfaces.md` §8.2 的路由表。
  - README 与 README_zh-CN："Desktop pairing"一节，删掉 `:279` 那句"管理页未对齐"的说法，并在顶部加一条里程碑。
  - `OMICSCLAW.md` 不需要改：运行时契约不涉及这些路由。

### 4.3 App

**M-A（最先做）**
- **AD-8 OAuth 删除**（§3.10）。
- **AM-1 Providers 页与向导**（§3.9.1）
  - 新增 `lib/backend-restart.ts`，`switchProject` 改为复用它；
  - 处理 `restart_required`、`restart_pending`、`shadowed_by_environment`，显示 `env_file`；
  - 远程模式只读；en/zh 文案。
  - 测试：`provider-settings.test.ts`（不再有 `auth_mode`）；新增 `provider-save-restart.test.ts`，覆盖 Electron 重启分支、dev 手动提示分支、遮蔽警告；`provider-doctor-route.test.ts` 对照新的 GET 载荷；向导（`onboarding-*.test.ts` 与 `lib/onboarding/llm-providers.ts`）、总览、用量页用新载荷做回归。
- **AM-2 Skills 页**（§3.9.2）
  - `api/skills/route.ts` 转发状态码；删除集合与审计筛选；抽屉的空态处理。
  - 测试：`skill-catalog-client.test.ts` 用 §3.2 的真实形状（没有可选字段）；`skill-try-in-chat.spec.ts` 的桩数据改成新形状。

**M-B**
- **AM-3 MCP 只读**（§3.9.3）。测试：`mcp-route.test.ts` 删去 PUT/DELETE 用例，GET 与 status 用例改用 §3.3 的形状（含被拒条目的 `state`/`error`）；`mcp-config.test.ts` 删去只测写入的用例。
- **AM-4 Memory 隐藏**（§3.9.4）。测试：`primary-nav.test.ts`；smoke 断言重定向。
- **AM-5 标题验证**（§3.9.5）。

**M-C 退役**（前置条件：App 的 P0/P1 已提交，Q11；每项一个提交，推荐顺序）：AD-1 → AD-11 → AD-2 → AD-3 → AD-4 → AD-5 → AD-6 → AD-7 → AD-9 → AD-10 → AD-12。

**M-D 收尾**：AD-13 → AC-1 →（可选）AC-2 → AM-6。

- **AM-6 App 文档**
  - `PROJECT_MEMORY.md`：按期写里程碑，包括管理页接通、各功能退役、表保留、§2.3 的更正；
  - `README.md`：删掉 Notebook、Bridge、Outputs、AutoAgent/Bench/KG 各节以及 token/fd-3 两段；
  - `CONTEXT.md`：删除 Skill Validation Review 与 Local Skill Validation Authority 两个术语；Workspace 的定义里去掉 notebooks；
  - `docs/DESKTOP_BUILD_GUIDE.md`（`:81`、`:381-387`）、`LOCAL_SETUP_GUIDE*.md`（Notebook）、`macos-native-feel-acceptance.md`（Notebook）；
  - `AGENTS.md` 中"由 plan 0065 处理"那句改为已完成。App 的 CLAUDE.md/AGENTS.md 正在另行修订，**只改这一句事实**，不动其他内容。

**任务数**：后端 6（BM-1…BM-6）+ App 页面 6（AM-1…AM-6）+ 退役 13（AD-1…AD-13）+ 收尾 2（AC-1、AC-2）= **27**。

---

## 5. 测试与验收

### 5.1 后端

| 用途 | 解释器 | 命令 |
|---|---|---|
| desktop HTTP 测试（需要 fastapi） | `/opt/conda/envs/OmicsClaw/bin/python` | `PYTHONDONTWRITEBYTECODE=1 … -m pytest -q -p no:cacheprovider -p no:randomly tests/entry/test_desktop_http.py tests/entry/test_desktop_wire_contract.py`，加上新增文件里的 HTTP 用例 |
| 纯 Python 测试 | `/opt/conda/envs/rapids_singlecell/bin/python` | `… -m pytest -q -p no:randomly tests/entry/test_desktop_catalog.py tests/entry/test_desktop_providers.py tests/entry/test_desktop_title.py tests/launch/test_desktop_settings.py tests/launch/test_the_environment_is_read_in_known_places.py tests/launch/test_launch_is_above_entry.py tests/launch/test_configure_command.py tests/entry/test_entry_is_the_top_layer.py tests/entry/test_desktop_route_guard.py "tests/entry/test_config.py::test_no_entry_module_reads_the_environment"` |

- 只跑新增的测试与直接相关的测试，**不跑全量**（owner 2026-09-24 的要求）。
- 已知与本计划无关的既有失败见 0064 §6.1。
- 新的纯函数测试文件不得 import fastapi，这样在 rapids 解释器下不会整份被跳过（0064 陷阱 1）。

### 5.2 App

**依赖**
- 现状：仓库里的 `node_modules` 是指向 `/tmp/0064-app-run/node_modules` 的符号链接。
- 如果实施前改为在仓库内 `npm ci`，命令不变，只是不再依赖那份副本。实施者在 PR 说明里写明用的是哪一种。
- `/tmp` 的副本一旦被清掉，就必须 `npm ci`（需要联网，先请 owner 确认）。

**命令**
1. `npm run typecheck`（其中的 `typecheck:web` 就是 en/zh 键集的检查）。
2. 对改动的文件跑 `npx eslint <files>`。
3. `npm run test:unit`，或只跑相关文件：`npx tsx --import ./src/__tests__/setup/jsdom-setup.ts --test <files>`。
4. 界面有改动的阶段，跑 `npm run test:smoke` 并截图。

**每个 AD 提交**：执行该行的 `git grep` 验收串，结果为空；typecheck 与相关测试通过；smoke 通过。在之后的 HEAD 上重跑时，验收串一律加排除项 `':!src/__tests__/e2e/live-backend-*'`：`live-backend-management.spec.ts` 里有一份退役路由列表，用来断言它们已不在导航里，属于有意命中。

### 5.3 真机端到端（沿用 0064 §6.3）

1. **后端**

   ```bash
   mkdir -p /tmp/oc-e2e-ws && cd /tmp/oc-e2e-ws && \
   OMICSCLAW_DIR=/workspace/dataset/private/zhouwg_data/OmicsClaw \
   OMICSCLAW_SKILLS_DIR=/workspace/dataset/private/zhouwg_data/OmicsClaw/skills \
   /opt/conda/envs/OmicsClaw/bin/python -m omicsclaw desktop --workspace /tmp/oc-e2e-ws -- --port 18765
   ```

   - 测 MCP 时，在 `/tmp/oc-e2e-ws/.mcp.json` 放一个带 `env` 的 stdio 条目，以及一个故意写错的条目。
   - **测 Providers 时，要让 `.env` 落在临时位置**：设 `OMICSCLAW_DIR=/tmp/oc-e2e-home`（其中放一份 `.env`），并另外指定 `OMICSCLAW_SKILLS_DIR`。**不要写仓库根目录的 `.env`**（陷阱 3）。
   - 结束后停掉进程，清理临时目录。
2. **curl**
   - 6 条新路由的形状；
   - `PUT /providers` 与 `POST /providers/test`、`/chat/title` 用 `text/plain` 返回 415；
   - 整个 `GET /providers` 响应里没有密钥原文。
3. **Next**
   - `OMICSCLAW_BACKEND_PORT=18765 NEXT_PUBLIC_OMICSCLAW_BACKEND_PORT=18765 npm run dev`。
   - 冷启动后先 `curl http://127.0.0.1:3000/api/ready` 预热，否则 Playwright 的 `webServer` 会起第二个 dev 服务器并覆盖 `.next`。
4. **Playwright**
   - 新增 `src/__tests__/e2e/live-backend-management.spec.ts`。**文件名必须以 `live-backend-` 开头**，否则 `playwright.live.config.ts` 不会收集。
   - Playwright 进程同样要带 `OMICSCLAW_BACKEND_PORT=18765`。
   - 运行：`OMICSCLAW_LIVE_BACKEND=1 OMICSCLAW_LIVE_WORKSPACE=/tmp/oc-e2e-ws OMICSCLAW_BACKEND_PORT=18765 npx playwright test -c playwright.live.config.ts`

   | # | 操作 | 断言 |
   |---|---|---|
   | a | 打开 Skills 页 | 技能数等于 `/health.skills_count`；按领域分组；没有错误状态；没有集合与审计筛选 |
   | b | 打开 `spatial-de` 的详情 | 显示 SKILL.md 正文与大纲；文件清单里都是相对路径；"Try in Chat"能预填 |
   | c | Providers 页：选一个 provider、填密钥、保存（`npm run dev`） | toast 给出手动重启命令；页面显示"重启后生效"与 `env_file`；列表里看不到密钥 |
   | d | 按提示重启后端后刷新 | `BackendModelLabel` 与 `/health` 显示新的 provider/model；随后发一句话，能正常回复 |
   | e | MCP 页 | 两个条目，一个是 connected 或 failed、一个是 rejected；`env` 显示为 `••••`；没有添加、编辑、删除入口 |
   | f | 新建会话，发第一句话 | 侧栏标题换成后端生成的标题（不是启发式截断） |
   | g | 逐个点主导航与 Go 菜单 | 没有 404、没有错误页；`/memory` 重定向到 `/chat` |
   | h | 诊断对话框的"实时测试" | 已保存的配置测试通过；填错密钥时得到明确的失败信息，信息里没有密钥原文 |

5. **Electron**（在 owner 的机器上做，或用 xvfb）
   - 重复 c、d：保存后应**自动**重启，并等到 `/health` 通过；
   - 有流在跑时保存，会先弹确认；
   - AD-7 之后打包模式能启动（直接 fork `server.js`），full_access 升级确认仍然有效，即主进程密钥的 bootstrap 仍在工作；
   - 后端子进程的 stdio 为 3 项。

### 5.4 验收标准

- **M-A**：§5.3 的 a–d、h 通过，Electron 段的 c、d 通过；BM-1、BM-3、BM-5 的测试通过；G1、G2、G6 成立。
- **M-B**：§5.3 的 e、f 通过；G3、G4 成立。
- **M-C**：
  - 每个 AD 提交的 `git grep` 验收串为空；
  - `npm run typecheck` 通过（en/zh 键集一致）；
  - smoke 通过；
  - §5.3 的 g 通过；
  - Electron 在开发模式与打包模式都能启动。
- **M-D**：AD-13 与 AC-1 的验收串为空；聊天链路回归，即 0064 §6.3 的 a–f 在真机上重跑一次；做了 AC-2 的话，刷新后能看到压缩提示。
- **整体**：三个管理页显示真实数据；导航里没有死入口；被删功能的路由字符串用 `git grep` 查不到；en/zh 键集一致。

---

## 6. 陷阱与风险

1. **只在一个解释器下看得见的缺陷**：HTTP 测试只在 OmicsClaw 解释器下运行。所以纯函数必须写在不 import fastapi 的模块里，并在 rapids 解释器下测试。
2. **分层守卫有四条**（§2.4）：`entry` 不能读环境、不能 import `launch`；`launch` 不能 import `entry` 的私有模块；`launch/__init__.py` 只能读一次 `os.environ`。第 1 版的 Q1-a 就踩了第三条。环境只能靠注入（§3.4、§3.6）。
3. **`.env` 落在哪里取决于启动方式**：`dotenv_target()` 先找 `OMICSCLAW_DIR`（或源码检出的根目录）下已存在的 `.env`，再找 cwd。
   - Electron 下 cwd 是 `workDir`，`OMICSCLAW_DIR` 取自 App 的设置；
   - pip 安装、没有 `OMICSCLAW_DIR` 时，会落到每个用户各自的回落目录。
   - 所以 `GET /providers` 要回传 `env_file`。
   - 测试与真机验证**绝不能写仓库根目录的 `.env`**。
4. **备份文件**：每次保存都会生成一份 `.env.backup-<时间戳>`，里面有全部密钥，权限与原文件相同，这与 CLI 向导一致。
   - 会越积越多。如果 owner 认为 App 保存得频繁，可以改成 `backup=False`（与 `/auto` 相同）。
   - 时间戳只精确到秒（`_configure.py` 的 `%Y%m%d-%H%M%S`）。同一秒内保存两次，第二次的备份会覆盖第一次，那一秒之前的版本就丢了。App 的保存按钮在请求期间禁用，实际很难触发，记录在案，不另外处理。
5. **导出变量遮蔽 `.env`**：Electron 会把用户 shell 里导出的变量传给后端子进程（`local-runtime-plan.ts` 的 `userShellEnv`）。在 `~/.zshrc` 里导出了 `LLM_API_KEY` 的用户，在 App 里改密钥永远不会生效。`shadowed_by_environment` 就是为这种情况准备的，一定要在界面上显示出来。
6. **`restart_required` 会取消进行中的回合**：Providers 保存之后的重启，与切换项目的重启是同一个动作，必须走同一个确认流程（AM-1 复用 `backend-restart`）。
7. **MCP 状态是启动时的快照**：编辑 `.mcp.json` 之后要重启；页面文案要说清楚。
8. **Skills 的可选字段全部缺失**：抽屉与卡片不能显示 "undefined"，也不能显示空分节。`SkillDossier` 里依赖 `input_contract`、`compute_resources` 等字段的分节要整块隐藏。
9. **删除 `model` 请求字段不等于删除按会话的模型**：上下文用量表依赖 `resolveSessionModel` 与 `/api/providers/models` 来确定窗口大小。BM-3 接通 GET `/providers` 之后，这些分组会第一次有数据，可能与 `/health.model` 不一致。AC-1 只停止发送这个字段，其余不动；如果出现偏差，另开一个小任务，让用量表改读 `/health.model`。
10. **Notebook 不能整目录删除**（E6）：先迁出 `CellOutput`、`ipynb.ts` 与导航函数，再删除；不然 `.ipynb` 预览和 AppShell 的导航守卫会一起坏掉。
11. **fd-3 的删除在所有模式下都生效**（E11）：
    - `python-manager.test.ts` 里有 14 处与 stdio 相关的用例要一起改。
    - `lastSkillEvolutionToken` 是崩溃自动重启的前置条件，漏删会让崩溃后永远不再自动重启。
    - 打包模式改回直接 fork `server.js` 之后，`bootstrapMainProcessConfirmSecret` 必须原样保留，否则 full_access 升级会一直被拒绝。
12. **Bench 与 KG 耦合**（E9）：顺序必须是先 KG 后 Bench。
13. **旧转录的兼容**：以下几处要保留渲染或过滤，否则旧会话会出现原始工具行或 HTML 注释：
    - 已持久化的 `media`、`ask_user` 工具行、`<!--stage:x-->` 标记（Q7）；
    - `tool_timeout` 的提示在旧转录里是纯文本，删除这条链不会影响它们的显示。
14. **`git grep` 的误报**：
    - 单独的 `bridge` 会匹配 IPC bridge；单独的 `kg` 太宽；单独的 `/notebook` 会匹配 `notebooks/`；单独的 `artifacts` 会匹配无关的键。
    - `db.ts` 里保留下来的 schema 注释会提到旧路由。
    - 所以验收串用 §3.10 给出的精确形式，并排除 `db.ts`。
15. **Playwright 的 live 配置只收集 `live-backend-*.spec.ts`**；dev 冷启动必须先预热 `/api/ready`；端口不是 8765 时，dev 服务器与 Playwright 两个进程都要带 `OMICSCLAW_BACKEND_PORT`。
16. **留出集软约束**：如果 Q1 选 b′，就要改 `entry/cli/__init__.py`，超出软约束的路径，需要 owner 豁免（§2.4）；选 c 同样越界。
17. **App 的 CLAUDE.md/AGENTS.md 正在另行修订**：AM-6 只改那一句关于 0065 的事实，避免冲突。
18. **远程模式下的 Providers 写入会写远端服务器的 `.env`**，而 App 没办法重启远端后端。本计划在远程模式下把页面设为只读（Q5）。
19. **`entry` 的 docstring 也受环境守卫约束**：`test_no_entry_module_reads_the_environment` 连注释与 docstring 一起扫描（`tests/entry/test_config.py:389-394`）。新模块在文字里提到进程环境时写"进程环境"，不要写出 `os.environ` 这个词。
20. **python-dotenv 的插值**：加载器装了 python-dotenv 时，缺省会展开值里的 `${…}`（`common/runtime_env.py:79-86`）。所以含 `${` 的密钥读回来会和写入的不一样。这是既有行为，CLI 向导也一样；App 保存含 `${` 的值时显示一条提示即可。
21. **App 的 P0/P1 未提交**（Q11）：这些改动不先落地，AD 的提交就会把它们一起带进去，"每个功能一个提交"就做不到了。

---

## 7. 待 owner 裁定的问题

| # | 问题 | 选项 | 推荐与理由 |
|---|---|---|---|
| Q1 | `.env` 的读写实现（在 `entry/cli/_configure.py`，带原子写入、备份、保留权限、跟随符号链接，前后修过几轮）怎样被 Desktop 复用 | **a**（第 1 版推荐，**已撤回**）：`launch` 从 `entry.cli._configure` import。违反 `test_the_shell_imports_only_public_names_of_the_entry_layer`（`test_launch_is_above_entry.py:337-353`）。<br>**b′**：在 `entry/cli/__init__.py` 重新导出 `read_dotenv`/`write_dotenv`，`launch` 从公开包 import，`DotenvSettings` 放在 `launch`。改一行，但违反 0064 §5.5 的"留出集期间不改 `entry/cli`"，需要 owner 豁免。豁免的依据：`import omicsclaw.entry` 不会加载 `entry.cli`，0057 的脚本也不 import 它（附录 B-2）。<br>**c**：把这两个函数及其辅助函数搬到 `omicsclaw/common/`。结构最干净，但改的是共享模块，越界。<br>**d**：`DotenvSettings` 放在 `entry/desktop/providers.py`，在方法体内 import `entry.cli._configure`（`entry` 层内部的引用），经 `omicsclaw.entry.desktop` 公开导出；`launch` 只构造与注入。代价：一处 `entry` 内部对私有兄弟模块的引用；原来说的"公开写入函数在 `launch`"改为"定位与快照在 `launch`"。import 写在函数体内，`import omicsclaw.entry.desktop` 不会多带进模块（实测直接 import 会多 87 个，含 `rich`，附录 B-4）。<br>**e**：等留出集结束后再做 b′ 或 c | **d**。不越界，不需要豁免，不复制密钥文件的写入逻辑，也不改任何守卫测试；留出集结束后，想改成 b′ 或 c 只动 `DotenvSettings` 的两行 import。b′ 也可以接受，但要 owner 明确豁免。e 会让 M-A 最有价值的一项（Providers）一直等下去 |
| Q2 | 0064 S9：非 `custom` preset 是否禁止修改 `base_url` | **a** 做；**b** 不做 | **b**。旁路很直接（切到 `custom` 加通用密钥即可）；会误伤合法的镜像或代理端点；CLI 向导允许修改；本机进程本来就能改 `.env`（§3.7 S14） |
| Q3 | 端点与密钥的绑定：请求里的端点不同于**运行中**的端点时，是否要求同时提供密钥 | **a**：`POST /providers/test` 与 `PUT /providers` 都要求。<br>**b**：只有 test 要求（约 5 行；残余旁路是先 PUT 再等重启，归 S16；UX 代价是重启前测试新的镜像端点要重填密钥）。<br>**c**：都不要求 | **c**。跨源网页发不出 JSON 写请求（S11，后端不给 CORS），同机进程本来就能读 `.env`，所以这道防线只防 DNS 重绑定，而 0064-Q4 已经接受了这项风险。第 1 版推荐 b，而且拿 M 做比较，可以先 PUT 再 test 绕过（审核 I2）；改成与运行中的端点比较后，旁路只剩"等重启"。收益仍然只落在一个已接受的风险上，按 owner 的"更严不作为缺省推荐"，推荐 c（§3.7 S15、S16） |
| Q4 | 新增的管理路由是否纳入契约版本 | **a** 不纳入，只登记进 `SERVED_PATHS`，随 0.2.0 与 App 一起发布；**b** 在 `/health.contracts` 里新增 `desktop_management: {schema_version: 1}`，App 做门控 | **a**。它们是纯新增，不改已有字段；两边一起发布；App 按 SPEC 不做兼容层。旧后端缺这些路由时，页面显示错误状态，这就是现在的行为 |
| Q5 | 远程模式下 Providers 页能否写入 | **a** 只读，提示去服务器上修改并重启；**b** 允许写入远端 `.env`，提示手动重启远端 | **a**。App 重启不了远端后端，写入后状态会长期不一致；远程模式整体留给计划 R |
| Q6 | Memory 页怎样隐藏 | **a** 页面改为 server component，调用 `redirect('/chat')`，同时去掉导航与 ⌘3；**b** 只去掉导航与菜单，页面仍可通过 URL 访问；**c** 在 `next.config.mjs` 里加 redirects | **a**。b 通过 URL 仍会打开一个报错的页面；c 把页面级的决定放到构建配置里，Memory 计划恢复时还要去改配置。两个页面现在都是 `'use client'`，改成不带它的 server component 更干净（§3.9.4） |
| Q7 | 删除 Bench 后，旧消息里的 `<!--stage:x-->` 标记怎么处理 | **a** 保留剥离逻辑（`chat-title.ts:17-18` 与 `MessageItem` 里只剥离、不显示徽标）；**b** 连剥离逻辑一起删掉 | **a**。约 5 行。旧会话里已经存有这个标记，删掉之后可能在消息正文里显示成原始注释。这属于"已持久化的数据"，不是兼容层 |
| Q8 | AC-2（`/compact` 刷新后留痕）是否纳入本计划 | **a** 纳入，作为 M-D 的可选项，不阻塞 M-D 验收；**b** 不纳入，另开小任务 | **a**。改 4 个文件，不需要迁移。现在刷新之后只剩一条 `/compact` 用户消息，看不出压缩是否发生、压缩了多少 |
| Q9 | App 保存密钥时写哪个变量 | **a**：写 `preset.api_key_env`（如 `DEEPSEEK_API_KEY`）；`custom` 与没有专属变量的 preset 写 `LLM_API_KEY`。<br>**b**：与 CLI 向导一致，规范写法是 `LLM_API_KEY`，只有文件里已有 `preset.api_key_env` 时才写它（`_configure.py:504-507`） | **a**。App 的 Providers 页按 provider 逐行配置、逐行显示"已配置"。按 b，保存 openai 会把 deepseek 的 `LLM_API_KEY` 覆盖掉，deepseek 那一行随之变成"未配置"。`resolve_config` 会先读 `preset.api_key_env` 再读通用变量，所以按 a 写入一定生效。代价是与 CLI 向导不一致：CLI 仍写 `LLM_API_KEY`，两边混用时，preset 专属变量优先，结果仍然正确。BM-3 的对照测试只在密钥变量这一项上断言"不同"。无论选哪项，都按 §3.4 的规则处理"换 provider 时清理模型与端点"，与 CLI 一致 |
| Q10 | 文件或环境里已有 `OMICSCLAW_PROVIDER` 时，PUT 怎样处理 provider 变量 | **a**：文件里有 `OMICSCLAW_PROVIDER` 时写它，否则写 `LLM_PROVIDER`；已导出的 `OMICSCLAW_PROVIDER` 列入 `shadowed_by_environment`。<br>**b**：总是写 `LLM_PROVIDER`，并删除文件里的 `OMICSCLAW_PROVIDER`。<br>**c**：总是写 `LLM_PROVIDER`，文件里有 `OMICSCLAW_PROVIDER` 时列入 `shadowed_by_environment` | **a**。`AppConfig` 先读 `OMICSCLAW_PROVIDER`（`entry/config.py:891-896`），只写 `LLM_PROVIDER` 的保存不会生效。a 沿用"写已存在的最高优先级写法"这条与 CLI 一致的规则；b 会删掉用户自己写的变量；c 把一个 App 本可以解决的问题推给用户 |
| Q11 | App 的 0064 P0/P1（179 项未提交）什么时候提交 | **a**：P0/P1 的提交先于任何 0065 的 App 改动，由 owner 按 P0、P1 分开提交（App 的提交不受后端"0056–0060 统一提交"的约束）。<br>**a′**：M-A/M-B 的 App 改动在独立的 worktree 里开发，P0/P1 提交之后再 rebase 上去。<br>**b**：与 M 一起提交，放弃"每个功能一个提交"。<br>**c**：M 全部完成后一起提交 | **a**。AD 任务要改的文件与 P0/P1 大量重叠，不先提交就没法按功能拆分提交，也没法给每个提交跑 `git grep` 验收。P0/P1 已经过真机测试。如果 owner 暂时不想提交，就用 a′，但不要在未提交的工作树上直接叠加 0065 的改动 |
| Q12 | MCP 的 `command`/`args`/`url` 怎样显示（`${VAR}` 在这些字段里都会展开） | **a**：显示 `.mcp.json` 里未展开的原文；`env`/`headers` 只显示键；被拒原因里替换掉环境变量的值。<br>**b**：显示展开后的值，只遮蔽 `env`/`headers`（第 1 版的做法）。<br>**c**：`args`/`url` 整体遮蔽 | **a**。约 25 行，展开后的令牌不会出现在页面上，页面仍然有用。b 会把 `${TOKEN}` 展开后的令牌显示出来；c 让页面失去意义（§3.3、§3.7 S13） |
| Q13 | Outputs 删除后，是否保留 `backend_output_dir` 在文件服务白名单里 | **a**：保留读取，旧会话的图片仍能预览；**b**：删掉读取，白名单只剩工作区与最近项目 | **a**。这是旧后端写入的一个固定目录，以后不会再变。能利用它的一方要先能调用 Next API（本机进程，或已接受的 DNS 重绑定），而删掉会让旧会话的图片失效。保留的代价是零（§3.7 S22） |

**裁定（owner，2026-09-28）**：Q1–Q13 全部按推荐：Q1=d、Q2=b、Q3=c、Q4=a、Q5=a、Q6=a、Q7=a、Q8=a、Q9=a、Q10=a、Q11=a、Q12=a、Q13=a。

**不需要 owner 裁定、在本计划内直接决定的**（审核时可以提出异议）
- 标题路由不做回合绑定，也不做并发上限（S17、S18）；
- `.env` 备份沿用 `backup=True`（陷阱 4）；
- `domain_name` 等于 `domain`；空 domain 归入 `general`；
- 删除后导航的分组方式由实施者决定；
- 标题的 `max_tokens=1024` 加 `thinking_budget_tokens=0`；test 路由的通过判据是"调用没有抛异常"。

---

## 8. 与其他计划的关系

| 计划或 ADR | 关系 |
|---|---|
| **0064** | 本计划就是它 §5.5 的后续计划 M。沿用 0064-Q4（只收 JSON；DNS 重绑定为已接受风险）、0064-Q6 = a、0064-Q8 = a、0064-Q9①–⑤。§2.3 列出了对它 §2.7、§4.6、§5.5 的更正。它的 C3-4（0.2.0 与统一提交）同样覆盖本计划的后端改动 |
| **后续计划 R**（远程模式） | 远程 jobs 面板、文件树、远程模式下的 Providers 写入留给它。AD-12 保留的 `remote-jobs-*`、`remote-sse-adapter` 由它处理 |
| **Memory 计划**（0064-Q9②，另立） | AM-4 只隐藏入口，组件、API 路由与 `lib/memory-*` 留给它 |
| **0057** | 不修改它的任何文件；留出集运行期间遵守软约束（§2.4） |
| **0037** | 遵守 `launch` 在 `entry` 之上、环境只在登记过的地方读取这两条规则；`.env` 的定位继续只有 `dotenv_target` 一处 |
| **App ADR-0004** | 类比：保存 provider 与切换项目一样，都要重启 |
| **App ADR-0006** | 不受影响 |

---

## 附录 A：证据索引（行号以 2026-09-28 工作树为准）

**后端**

| 文件 | 行号与内容 |
|---|---|
| `entry/desktop/server.py` | `:103` 控制请求体上限；`:357-551` `create_desktop_app`；`:389-396` bearer；`:404-407` JSON 检查；`:409-441` 读请求体；`:448-549` 路由 |
| `entry/desktop/wire_contract.py` | `:1-21` docstring；`:34-42` `SERVED_PATHS` |
| `entry/desktop/doctor.py` | `:65-77` `effective_model` |
| `entry/assembly.py` | `:754-792` `_ProviderSummarizer`（`generate(messages, None)` 的先例）；`:887` `skills`；`:924` `mcp` |
| `skills/index.py` | `:74-238` `SkillIndex`；`:191-207` `get_full_content` |
| `skills/skill.py` | `:12-81` `Skill` |
| `mcp/manager.py` | `:54-84` 状态类型；`:167-169` `config`；`:215-217` `statuses` |
| `mcp/config.py` | `:1-44` 文件格式（`:33-34` 五个字段都会展开 `${VAR}`）；`:156-185` `parse_mcp_config`；`:193-230` `_parse_server`（存展开后的值；`:224` 被拒原因带 URL） |
| `provider/config.py` | `:78-117` `ProviderPreset`；`:119-313` `PRESETS`（13 个）；`:315-327` `DETECT_ORDER`；`:390-430` `ProviderConfig` 字段；`:524-543` `detect_provider_from_env`；`:580-680` `resolve_config` |
| `provider/base.py` | `:71-98` `Completion`；`:102-164` `LLMProvider` |
| `provider/_model_limits.py` | `:45-52`；`:155-168` `get_model_limits` |
| `entry/cli/_configure.py` | `:70-72` `__all__`；`:142` `read_dotenv`；`:203-275` `write_dotenv`；`:437-446` `_mask`；`:449-469` `_target_key`；`:472-542` `_ask_llm`；`:545-553` `_provider_order` |
| `entry/cli/__init__.py` | `:75` 只重新导出 `missing_credential_hint`、`run_configuration_wizard` |
| `entry/cli/_auto.py` | `:29` 复用 `read_dotenv`、`write_dotenv` |
| `entry/config.py` | `:888-896` provider 与 model 的读取顺序 |
| `common/runtime_env.py` | `:79-86` python-dotenv 加载，未关闭插值 |
| `launch/_dotenv.py` | `dotenv_candidates`、`dotenv_target`（整个文件，81 行）；本计划在这里新增 `LaunchEnvironment` |
| `launch/__init__.py` | `:122-125` `_adopt_dotenv` 的调用时机；`:163-204` `_adopt_dotenv` |
| `launch/_surfaces.py` | `:85-88` import；`:287-306` `DESKTOP_USAGE`（过时）；`:1072-1102` `start_desktop`；`:1156-1170` `_serve_desktop` |
| 测试 | `tests/launch/test_launch_is_above_entry.py`（`:108-122`、`:149-158`、`:195-232`、`:337-353`）；`tests/entry/test_config.py:380-405`；`tests/launch/test_the_environment_is_read_in_known_places.py`；`tests/_env_probe.py`；`tests/entry/test_desktop_route_guard.py`；`tests/entry/test_desktop_wire_contract.py:104-113`；`tests/entry/test_desktop_http.py:79-86`；`tests/launch/test_configure_command.py` |
| 文档 | `README.md:153, 199, 203, 264-289`（`:279` 那句"管理页未对齐"）；`docs/core-features/surfaces.md` §8.2 |

**App**

| 文件 | 行号与内容 |
|---|---|
| `src/app/api/skills/route.ts` | `:8-15` 一律按 200 转发 |
| `src/app/api/skills/[domain]/[skillName]/route.ts` | `:5-20` |
| `src/components/skills/skill-catalog-client.ts` | `:124-174` `parseSkill`；`:176-198` 目录解析；`:205-230` 详情合并 |
| `src/components/skills/types.ts` | `:1-112` 目录类型；`:113-149` `SkillDetail`；`:151-309` 治理类型 |
| `src/components/skills/SkillsWorkspace.tsx` | `:104-105, 342, 355-363` 标签页；`:121, 219, 296, 429-441` 审计筛选；`:136, 184-186` 请求 |
| `src/components/skills/skill-sort.ts` | `:109-117` `matchesAuditFilters` |
| `src/app/api/providers/route.ts` | 整个文件 |
| `src/app/api/providers/doctor/route.ts` | `:75-112` 规范化；`:169-190` GET `/providers`；`:270-303` `/providers/test` |
| `src/app/api/providers/models/route.ts` | 整个文件 |
| `src/app/api/network/test/route.ts` | `:59-82` 取 origin，回落逻辑有误 |
| `src/lib/provider-settings.ts` | `:12-20, 55-76` 载荷与 `auth_mode` |
| `src/lib/provider-model-catalog.ts` | `:3-7, 25-57` `buildQuickSwitcherModels`（死代码）；`:74-76` `model_metadata` |
| `src/components/settings/OmicsClawProviderSection.tsx` | `:220-285` 读取与保存 |
| `src/components/settings/ProviderRowEditor.tsx` | `:141-267, 326-443` OAuth |
| `src/components/setup/hooks/useLLMSetup.ts` | `:71-123` |
| `src/types/index.ts` | `:503-529` `BackendProviderInfo`、`BackendProvidersResponse`；`:648-655` MCP 写入请求类型；`:771-816`、`:847-860` 死的 SSE 类型；`:1372-1415` `ClaudeStreamOptions` |
| `src/app/api/plugins/mcp/route.ts` | `:8-19` 后端条目类型；`:44-72` `toSourcedConfig`；`:74-89` 创建载荷；`:104-127` GET；`:131-205` POST、PUT、DELETE |
| `src/app/api/plugins/mcp/status/route.ts` | `:21-37` |
| `src/components/plugins/McpManager.tsx` | `:40-43, 80-113` 读取；`:115-253, 272-291, 337-342, 385-530` 写入 UI |
| `src/lib/session-title.ts` | `:10-18` 错误码；`:70-130` |
| `src/lib/chat-title.ts` | `:10-11` 上限；`:14-18` stage 标记；`:83-90` 规范化 |
| `src/app/api/chat/route.ts` | `:342-360` 请求字段；`:453-477` 标题；`:549-560` stage 标记；`:714-743` 后端请求体；`:1008-1032` run-link |
| `src/lib/project-switch.ts` | `:18-52` 重启相关依赖；`:119-140` `waitForBackendHealth`；`:152-241` `switchProject` |
| `src/lib/primary-nav.ts` | `:4-35` |
| `src/components/layout/ChatListPanel.tsx` | `:174-187` `NAV_ICONS`；`:709-712` `NAV_GROUP_DEFS` |
| `electron/menu.ts` | `:92-98` Go 菜单 |
| `electron/main.ts` | `:14-17, 90-93, 1068, 1301-1303, 1332, 1339-1348` 技能治理 bootstrap；`:1249-1256` `bootstrapMainProcessConfirmSecret`（保留），调用点 `:1572, 2202, 2226` |
| `electron/python-manager.ts` | `:238-241` fd 指针；`:287` `lastSkillEvolutionToken`；`:392` cwd；`:398` 4 项 stdio；`:506-537` 交接；`:1060-1066`、`:1086-1092` 崩溃自动重启用到它 |
| `electron/main.ts`（重启） | `:1882-1888` `omicsclaw:restart` 走 `activateCommittedRuntime` |
| `src/lib/backend.ts` | `:38` 重新导出 `backendFetchWithSkillEvolutionAuthority` |
| `src/lib/turn-termination.ts` | `:3-6` 终止种类；`:23-31` 仍然有效的错误芯片 |
| `src/hooks/useSSEStream.ts` | `:244-246` media；`:254-261` `_progress`；`:266`、`:372`、`:391`、`:401`、`:449`、`:463` 死 case；`:305-348` 非压缩的 status 分支 |
| `src/hooks/useSlashCommands.ts` | `:85-86`（不再请求 `/api/skills`） |
| `src/hooks/usePopoverState.ts` | `:59-147` AI 建议残留 |
| `src/lib/chat-stream-transcript.ts` | `:160-177, 256-263, 347-352` 压缩的持久化 |
| `src/lib/db.ts` | `:183` role 的 CHECK；`:225` 绑定表；`:298-333` run_meta；`:380-391` datasets |
| `src/i18n/zh.ts` | `:3` `Record<TranslationKey, string>` |
| `src/__tests__/e2e/smoke.spec.ts` | `:30-35, 78-202` Bench；`:63-68` Memory |
| `playwright.live.config.ts` | `testMatch: '**/live-backend-*.spec.ts'`；端口与预热的说明 |

## 附录 B：核实记录

**B-1 技能索引**（rapids 解释器，`load_skills(Path("skills"))`）
- 共 94 个技能，跳过 0 个，根目录为相对路径 `skills`。
- 领域分布：singlecell 34、spatial 19、bulkrna 14、genomics 10、metabolomics 8、proteomics 8、literature 1。
- 没有 domain 为空的技能；81 个带 `trigger`，94 个带 `tags`。

**B-2 0057 的导入**
- 执行 `import omicsclaw.entry` 之后，`sys.modules` 里没有 `omicsclaw.entry.cli*`、`omicsclaw.entry.desktop*`、`omicsclaw.launch*`。
- `docs/plans/0057-validation/common.py` 只 import `ensemble`、`entry.config`、`skills`。
- 本次核实时，进程表里没有 `run_holdout`、`run_arms` 进程。但无法确认留出集是否已经结束，所以软约束照常执行。

**B-3 App 盘点方法**
- 三路只读盘点，分别覆盖：Optimize/Bench/KG/Notebook；技能治理、回放、市场、OAuth、CLI、Bridge、Outputs、远程死代码、Memory、MCP；聊天死分支、P1 遗留、`/compact`、i18n、斜杠菜单。
- 以下关键行已亲自复核：`main.ts:1249-1256`、`python-manager.ts:398`、`menu.ts:92-98`、`useSSEStream.ts` 的 case 列表、`backend-fetch.ts` 中 autoagent 的行数（27）、`primary-nav.ts`、`ChatListPanel.tsx:174-187, 709-712`、smoke 的 Memory 用例，以及 §2.2 表中各解析器。
- 盘点结果中的其余行号在实施时按符号名重新定位。

**B-4 第 2 版补充的核实**
- 守卫测试的原文：`test_launch_is_above_entry.py:108-122, 149-158, 195-232, 337-353`；`tests/entry/test_config.py:380-405`（docstring 也扫描）。
- 模块开销：在已经 import `omicsclaw.entry.desktop` 的进程里，再 import `omicsclaw.entry.cli._configure` 会多出 87 个模块，其中有 `rich`，但没有 fastapi、textual、prompt_toolkit、openai、anthropic（rapids 解释器实测；审核者测得 73，差异来自环境）。`rich` 由 conda 管理（`environment.yml:277`），`import omicsclaw.launch` 本来就会带进它。
- `test_importing_the_package_costs_no_optional_dependency` 只检查上面五个包。
- `omicsclaw:restart` 走的是 `localRuntimeActivation.activateCommittedRuntime()`（`main.ts:1882-1888`），不经过 `handleCrash`。
- `network/test` 按名字匹配到 provider 时不回落（`route.ts:70-74`）。
- 两个 Memory 页面都以 `'use client'` 开头。
- App 工作树：`git status --short` 179 项；`git diff --stat` 161 个文件。

## 附录 C：审核意见处理记录（第 2 版）

每条都先对照代码或测试核实，再决定怎样处理。

### 阻断

| 编号 | 意见 | 核实 | 处理 | 改动位置 |
|---|---|---|---|---|
| B1 | Q1-a 违反 `test_the_shell_imports_only_public_names_of_the_entry_layer`；§2.4 漏列这条测试；b 受 0064 §5.5 约束 | 属实（`:337-353` 与 `_imported_modules` `:195-232`；0064 第 803 行） | **采纳**。Q1 重写为 a（撤回）/b′/c/d/e，推荐 d；§2.4 改为守卫测试表；§3.6 重写；不改任何守卫测试 | §0、§2.4、§3.1、§3.6、§4.2 BM-3/BM-5、§6 陷阱 2/16、§7 Q1 |

### 重要

| 编号 | 意见 | 核实 | 处理 | 改动位置 |
|---|---|---|---|---|
| I1 | 快照的做法违反"只读一次"与"`_surfaces` 不出现 `os.environ`"；传参路径没写；模块全局会引起循环 import | 属实（`:108-122`、`:149-158`） | **采纳**。用 `live = os.environ; exported = frozenset(live); _adopt_dotenv()`；以 `LaunchEnvironment`（只读 Mapping，带 `exported_names`）作为 `env` 传给 `start_desktop`，签名不变；`_serve_desktop` 增加 `settings` 参数 | §3.6、§4.2 BM-5 |
| I2 | S15 可以先 PUT 再 test 绕过；实际只防 DNS 重绑定，而那是已接受的风险 | 属实（第 1 版拿 M 做比较；`server.py:20-25` 不给 CORS） | **采纳**。比较对象改为运行中的端点，作为选项 b 保留；推荐改为 c（不做） | §3.4、§3.7 S15/S16、§5.3 h、§7 Q3 |
| I3 | CLI 的密钥规范写法是 `LLM_API_KEY`，第 1 版自相矛盾；换 provider 时的清理没写；逐 provider 配置下写通用变量会互相覆盖 | 属实（`_configure.py:479-487, 504-507, 517-540`） | **采纳**，并改写为 Q9（推荐写 `preset.api_key_env`）；写明换 provider 时模型写新 preset 的缺省值、端点写空串，与 CLI 一致；对照测试按 Q9 的裁定断言 | §2.1、§3.4、§4.2 BM-3、§7 Q9 |
| I4 | `AppConfig` 先读 `OMICSCLAW_PROVIDER`，而 `resolve_config` 先读 `LLM_PROVIDER`；运行中三元组怎样求没写 | 属实（`entry/config.py:891-896`；`provider/config.py:535, 613`；`assembly.py:1219-1221`） | **采纳**。M 按 `AppConfig` 的顺序求；运行中三元组参照 `effective_model`，并用启动时的环境求 `base_url`；PUT 的处理改写为 Q10（推荐写已存在的最高优先级写法） | §2.1、§3.4、§7 Q10 |
| I5 | `${VAR}` 在五个字段里都会展开，S13 的理由不成立；被拒原因也带展开后的 URL | 属实（`mcp/config.py:33-34, 208-230, 224`） | **采纳**，并改写为 Q12（推荐显示未展开的原文，被拒原因里替换掉环境变量的值） | §3.3、§3.7 S13、§4.2 BM-2、§7 Q12 |
| I6 | App P0/P1 未提交，与 AD 大量重叠，"每个功能一提交"落不了地 | 属实（179 项） | **采纳**，列为 M-C 的前置条件，并改写为 Q11 | §0、§2.4、§4.1、§4.3、§6 陷阱 21、§7 Q11 |
| I7-1 | AD-7 漏了 `lastSkillEvolutionToken` 与 `backend.ts:38` | 属实 | **采纳** | §3.10 AD-7、§6 陷阱 11、附录 A |
| I7-1′ | "AM-1 保存后的重启依赖 `lastSkillEvolutionToken`" | **不属实**：显式重启走 `activateCommittedRuntime`（`main.ts:1882-1888`），只有崩溃自动重启（`handleCrash`）依赖它 | **部分采纳**：按"漏删会让崩溃后永远不再自动重启"写进 AD-7 与陷阱 11，不写成 AM-1 的依赖 | §3.10 AD-7 |
| I7-2 | stdio 相关的伪造是 14 处，不是 13 | `grep -n stdio python-manager.test.ts` 共 14 行 | **采纳**（按"14 处 stdio 相关"表述） | §3.10 AD-7、陷阱 11 |
| I7-3 | AD-13 与 AC-1 矛盾：`turn-termination.ts`、`TerminalStateChip.tsx` 仍然承载有效的错误芯片 | 属实（`turn-termination.ts:23-31`） | **采纳**。AD-13 只删 `tool_timeout` 变体，补上 `stream-session-manager.ts:447, 1098`、`chat-stream-stop-registry.ts:17`、`terminal.tool_timeout`；AC-1 写明只删 `enable-1m` 这一个动作 | §3.10 AD-13、§3.11 |
| I7-4 | 验收串的误报（注释、`PluginInfo.marketplace`）与漏检（文案键、`'/bench/onboard'`） | 属实（`git/service.ts:57`、`layout.tsx:83`、`path-security.ts:219`、`types/index.ts:871`、smoke `:122`） | **采纳**。注释随删除一起改；AD-6 排除 `types/index.ts`；每个 AD 加一条文案键前缀检索；AD-3 用 `bench/onboard` 与 `/onboard/(skip\|status\|user)`。审核者没有指出、这次核实发现的一点：单独的 `/onboard` 会匹配 `@/lib/onboarding/`，所以没有用它 | §3.10 |

### 次要

| 编号 | 意见 | 处理 |
|---|---|---|
| 1 | Q 编号与 0064 冲突；问题数与路由数写错 | **采纳**。0064 的裁定统一写作"0064-Qn"；问题数改为 13；改为"7 个路径" |
| 2 | §5.1 漏了 `test_no_entry_module_reads_the_environment`，它也扫描 docstring | **采纳**。加入 §5.1 与 §2.4，新增陷阱 19 |
| 3 | 标题 64、test 16 的 `max_tokens` 太小，推理模型会返回空正文 | **采纳**。标题改为 1024 加 `thinking_budget_tokens=0`；test 改为 256，通过判据改为"没有抛异常" |
| 4 | `/chat/title` 在 415/413/解析失败时返回 `{"detail":…}` | **采纳**，写进 §3.1、§3.5：App 把它们当作 `TITLE_PROVIDER_FAILED`，这是预期行为 |
| 5 | `network/test` 的回落描述不准 | **采纳**。修正 §2.2；AM-1 不再修改这个路由 |
| 6 | §2.2 漏列 `/api/providers` 的其他读取方；向导应纳入回归 | **采纳**。§2.2 加一行；AM-1 的测试加上向导、总览、用量页 |
| 7 | MCP 被拒条目显示成空的 stdio 卡片 | **采纳**。§3.9.3 与 AM-3 把 `state`/`error` 传进类型与卡片 |
| 8 | smoke 路径；Memory 页改为 server component；`UnicodeDecodeError`；备份文件同一秒会被覆盖 | **全部采纳**。§3.9.4、§3.4 的失败分支、陷阱 4 |
| 9 | 默认面板为 `dashboard` 时要兜底；`backend_output_dir` 的放行要算账 | **采纳**。AD-11 增加兜底与测试；§3.7 新增 S22；改写为 Q13（推荐保留） |
| 10 | `env_file` 回传绝对路径，与 S19 不一致 | **采纳**。在 §3.4 与 S12 说明理由：用户需要知道配置写到了哪里，而 `/health` 已经回显工作区的绝对路径 |
| 11 | `.env` 注入的说明；python-dotenv 的插值 | **采纳**。§3.6 末段，新增陷阱 20 |

### Q 意见

- Q2、Q4、Q5、Q7：审核同意，保持不变。
- Q6：同意；按意见改为 server component。
- Q8：保持 a，写明"可选，不阻塞 M-D"。
- 新增 Q9–Q13，对应审核要求的五项：密钥变量名与换 provider 时的清理、`OMICSCLAW_PROVIDER`、App P0/P1 的提交时机、MCP 的展开值、`backend_output_dir`。

### 未采纳

- 没有整条不采纳的意见。部分采纳的是 I7-1′："AM-1 的重启依赖 `lastSkillEvolutionToken`"与代码不符，只保留"崩溃自动重启依赖它"这一半。

### 第 2.1 版（复审）

| 编号 | 意见 | 核实 | 处理 | 改动位置 |
|---|---|---|---|---|
| R1 | `test_the_shell_hands_both_globals_down_explicitly` 按字面检查 `environment: Mapping[str, str] = os.environ` | 属实（`test_launch_is_above_entry.py:159-168`） | **采纳**。示例改为先逐字保留这一行，再取 `exported`、调用 `_adopt_dotenv()`、包装成 `LaunchEnvironment`；这条测试加入 §2.4 的守卫表与 BM-5 的"原样通过"清单 | §2.4、§3.6、§4.2 BM-5 |
| R2 | `_adopt_dotenv` 会加载全部候选文件（先加载者优先），只读 `dotenv_target()` 会让运行中的 `base_url`、`configured`、`restart_pending` 与 Q12 的替换来源算错 | 属实（`launch/__init__.py:196-203`；Electron 下 cwd 是项目目录） | **采纳**。`startup` 由 `LaunchEnvironment` 在 `_adopt_dotenv` 之后取快照并注入，不重新读文件；M 按候选文件先加载者优先合并，再叠加 `exported`；候选路径由 `launch` 注入，写入目标仍是 `dotenv_target()`；`settings=None` 时被拒条目的 `error` 只给固定的 `invalid_config` | §3.3、§3.4、§3.6、§4.2 BM-3/BM-5 |
| 次要 1 | 注释误报清单漏了 `MessageItem.tsx:357`、`preflight-guidance.ts:59` | 属实 | **采纳** | §3.10 |
| 次要 2 | `configured` 的规则；`LLM_PROVIDER` 未设置时 `custom` 会采用通用密钥 | 属实（`provider/config.py:620-625`） | **采纳**。规则写成"密钥非空，或 ollama/custom 满足 explicit-provider 条件"，照实显示，并加测试 | §3.4、§4.2 BM-3 |
| 次要 3 | Q11 不应允许在未提交的工作树上开发 | 同意 | **采纳**。改为"P0/P1 的提交先于任何 0065 的 App 改动"，另给 a′（独立 worktree 开发，提交后 rebase） | §2.4、§4.1、§7 Q11 |
| 次要 4 | 三元组比较的字段与来源 | 属实（`assembly.py:1219-1221` 用 `trace_provider` 包装） | **采纳**。两侧都取 `resolve_config` 返回的 `provider`、`model`、`base_url`，运行中一侧用 `env=startup` | §3.4 |
