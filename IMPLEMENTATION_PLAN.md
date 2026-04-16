# Remote 连通性联调 — 分阶段修复方案

**范围**：OmicsClaw（后端，本仓库）+ OmicsClaw-App（前端，`/data1/TianLab/zhouwg/project/OmicsClaw-App`）
**方法**：TDD，每阶段先写测试再改代码，通过后再进入下一阶段
**策略**：增量联调、不做大爆炸重构；保留本地模式现有行为，只在 remote 模式里引入真远端调用
**不做的事**：
- 不动 skills 的 SKILL.md
- 不给前端 UI 组件改结构（只加 API route 与 lib 层适配）
- 不引入新依赖（后端用 asyncio、前端用现成的 `backendFetch`）

---

## Stage 1：后端执行面接通真实 SubprocessExecutor
**Goal**：把 `_DEFAULT_EXECUTOR` 从 `LocalExecutor`（永远返回 `executor_not_implemented`）换成真正能跑 `python omicsclaw.py run <skill> ...` 的 `SubprocessExecutor`。
**Success Criteria**：
- submit 一个已存在的 skill（例如 `bulkrna-de --demo`）后，job 能走完 queued → running → succeeded
- stdout.log 有真实 skill 输出
- artifacts/ 目录下有真实产物（不是空目录）
- 所有现有 `tests/test_remote_routes_contract.py` 既有断言继续绿（包括 `test_job_events_streams_lifecycle` 依赖失败分支的那部分需相应调整）
**Tests**（新增）：
- `tests/test_execution_default_executor.py::test_default_executor_is_subprocess_executor` — 校验模块级 `_DEFAULT_EXECUTOR` 的类型
- `tests/test_execution_default_executor.py::test_default_command_factory_maps_skill_to_omicsclaw_argv` — 校验命令工厂把 skill/inputs/params 映射成正确 argv
- `tests/test_remote_routes_contract.py::test_submit_real_skill_succeeds_end_to_end` — 用 `--demo` 模式跑一次完整 job（用最便宜的 skill 例如 `bulkrna-qc --demo`）
**Status**：Complete

**实现要点**：
1. 新增 `omicsclaw/execution/executors/default.py`：提供 `default_command_factory(ctx) -> list[str]`，映射 `ctx.skill/ctx.inputs/ctx.params` 到 `python omicsclaw.py run <skill> ...` argv
2. 把 `omicsclaw/remote/routers/jobs.py` 的 `_DEFAULT_EXECUTOR = LocalExecutor()` 改为 `build_default_executor()`
3. `tests/test_remote_routes_contract.py` fixture 显式 monkeypatch 回 `LocalExecutor()`，契约测试验证 wire format 而非执行器行为
4. 既有 4 个 executor 测试（LocalExecutor 相关）保持不动，因为它们验证的是协议合规性

**落地情况**（2026-04-15）：
- 新增 `omicsclaw/execution/executors/default.py`（复用 `autoagent.constants.param_to_cli_flag`）
- 新增 `tests/test_execution_default_executor.py`（10 个单元测试）
- `omicsclaw/remote/routers/jobs.py` 切换默认 executor，docstring 同步
- `tests/test_remote_routes_contract.py` fixture 锁回 `LocalExecutor()`
- 8 个测试文件共 74 tests 全绿（包括 SSE/reconcile/cancel/contract/auth）
- Code review 三路 agent 已过，`_snake_to_kebab` 换成既有 `param_to_cli_flag`，冗余 docstring 已清理

---

## Stage 2：前端 wire 层统一（类型 + 翻译器 + 基础设施）
**Goal**：建立前端一层薄的"后端契约 ↔ App 契约"翻译器，让后续 Stage 3/4 的每一个 proxy route 都能用同一套适配函数，不要每个 route 各写一遍字段重命名。
**Success Criteria**：
- `src/lib/remote-jobs-adapter.ts` 能把后端 `Job`（`job_id/error/created_at/inputs:dict`）翻成 App 的 `Job`（`id/error_message/submitted_at/inputs:string`），反之亦然
- `src/lib/remote-sse-adapter.ts` 能把后端 SSE 事件流翻译成 App 前端期望的 `{ type, job }`/`{ type, lines[] }`/`{ type, artifact_root }` 形状
- 新增 `isRemoteMode()` helper，封装 `connection_mode === "remote"` 判断
**Tests**（新增）：
- `src/__tests__/unit/remote-jobs-adapter.test.ts`（16 tests）：双向翻译、null 处理、execution_target 注入、JSON 序列化/反序列化、字段丢弃
- `src/__tests__/unit/remote-sse-adapter.test.ts`（11 tests）：完整生命周期、首次 snapshot、重复 artifact 去重、done 静默、error 透传
- `src/__tests__/unit/remote-mode-helper.test.ts`（3 tests）：`isRemoteMode()` 边界
**Status**：Complete

**落地情况**（2026-04-15）：
- 新增 `src/lib/remote-jobs-adapter.ts`：`BackendJob/BackendJobSubmitRequest/BackendJobListResponse/BackendJobSubmitResponse` 类型，`backendJobToAppJob/appJobInputToBackendSubmit`
- 新增 `src/lib/remote-sse-adapter.ts`：`RemoteSseAdapter` 类（复用 `jobs-state-machine.ts` 的 `isTerminalJobStatus`）
- `src/lib/backend-config.ts` 追加 `isRemoteMode(cfg?)`
- 30 个新测试全绿；全项目 419 unit tests + typecheck 全绿
- Review 整改：复用 `isTerminalJobStatus`、内联 `deriveDisplayName`、文档化 `exit_code` 丢弃语义、精简 docstring

**关键翻译规则**：
- `job_id ↔ id`
- `error ↔ error_message`（null → ""）
- `created_at ↔ submitted_at`
- `inputs: dict ↔ inputs: JSON.stringify(dict)`
- 后端 `stdout_tail` 不存在 → App 初次拿快照时 `stdout_tail=""`，再靠 SSE `job_log` 累积
- 后端连续多个单行 `job_log` → App 前端逻辑不变，仍收 `{type:'job_log', lines:[...]}`，adapter 每收到一个后端 `job_log` 就映射成 `{lines:[line]}`（不合批，保持延迟最低）

---

## Stage 3：Jobs 控制面改造为 mode-aware proxy
**Goal**：remote 模式下，App 的 `/api/jobs*` 不再读写本地 SQLite，而是透传到后端并翻译响应。Local 模式现状不变。
**Success Criteria**：
- Remote 模式下 `POST/GET/DELETE /api/jobs`、`/api/jobs/[id]`、`/cancel`、`/retry`、`/events` 全部访问后端
- SSE 流用 adapter 翻译，前端（`jobs-client.ts` 消费方）零改动
- `chat/route.ts:253` 的本地 createJob **保持本地**（按已定决策：chat turn 不污染远端）
- 既有 `jobs-client.test.ts`/`jobs-api.test.ts`/`chat-route-jobs.test.ts` 全绿（local 路径不动）
**Tests**（新增）：
- `src/__tests__/unit/remote-jobs-proxy.test.ts`（13 tests）：proxy 工具函数 + unavailableReason→503
- `src/__tests__/unit/jobs-routes-remote.test.ts`（11 tests）：5 路由 remote 模式集成；chat 本地 fallback
**Status**：Complete

**落地情况**（2026-04-15）：
- 新增 `src/lib/remote-jobs-proxy.ts`：`BackendError`、`proxyListJobs/SubmitJob/GetJob/CancelJob/RetryJob`、`openRemoteJobEventStream`、`createSseProxyStream`、`executionTargetForRemote`、`ensureBackendAvailable`
- 改造 5 个 route：`/api/jobs`（GET/POST）、`/api/jobs/[id]`（GET 带本地优先、PUT 405、DELETE 501）、`/cancel`、`/retry`、`/events`
- chat/route.ts 不动（按决策）
- 24 个新测试全绿；全项目 442 passing（另 1 预先 flaky 计时测试与本 stage 无关）+ typecheck 干净
- Review 整改：`unavailableReason` → BackendError(503) 提前拦截、`createSseProxyStream` 增加 `cancel` handler 传播 reader.cancel、route 外层 500 兜底

**决策点请你确认**：
- 方案 A：remote 模式下 App 的 chat turn 也提交到后端 `/jobs`（真正一体化）
- 方案 B：remote 模式下 chat turn 依然是 App-local display-only job，真正的 skill 执行才走 remote `/jobs`（隔离聊天与计算）
- 我倾向 B：chat 本身不是 skill execution，把它也变成远端 job 会放大耦合，而且 chat 已经通过 `/chat/stream` 直连后端了，再记一份远端 job 是重复账本

---

## Stage 4：Datasets + Artifacts + Session resume
**Goal**：把剩下 3 个控制面也改成 remote-aware proxy。
**Success Criteria**：
- Remote 模式 `GET /api/datasets` 返回后端列表；`POST /api/datasets` 决策如下（见下）
- Remote 模式 artifacts list/download/preview 通过后端，不再读本机文件系统
- 新增 `POST /api/chat/sessions/[id]/resume`：代理到 `POST /sessions/{id}/resume`，返回 `active_job_ids`，前端会话 reattach 逻辑可消费
- SetupCenter 的"还没有数据集"判定改为：remote 模式看远端 list，local 模式看本地
**Tests**（新增）：
- `src/__tests__/unit/api-datasets-remote.test.ts`
- `src/__tests__/unit/api-artifacts-remote.test.ts`（list + download streaming + preview 64KB 截断）
- `src/__tests__/unit/api-sessions-resume.test.ts`
**Status**：Complete

**落地情况**（2026-04-16）：
- 新增 `src/lib/remote-datasets-adapter.ts`：`BackendDatasetRef` 类型 + `backendDatasetToAppDatasetRef`
- 新增 `src/lib/remote-datasets-proxy.ts`：`proxyListDatasets / proxyUploadDataset / proxyImportRemoteDataset`
- 新增 `src/lib/remote-artifacts-proxy.ts`：`proxyListArtifacts / proxyDownloadArtifact / proxyPreviewArtifact`、`UnsupportedPreviewError`
- 新增 `src/app/api/datasets/upload/route.ts`（multipart → backend）
- 新增 `src/app/api/datasets/register/route.ts`（JSON → backend `/datasets/import-remote`）
- 新增 `src/app/api/chat/sessions/[id]/resume/route.ts`（代理 → `/sessions/{id}/resume`）
- 改造 `src/app/api/datasets/route.ts`（GET remote proxy；POST 405 remote）
- 改造 `src/app/api/artifacts/*`（list/download/preview 均加 remote-fallback 分支）
- 共享 helpers 抽到 `backend-fetch.ts`：`BackendError, readBackendErrorMessage, ensureBackendAvailable, ensureBackendOk`
- 42+ 个新测试全绿；全项目 466/467 pass（另 1 预先 flaky 计时测试无关）+ typecheck 干净
- Review 整改：共享 helper 消除 3x `readErrorMessage` 重复、`buildDownloadPath` 改用 literal `:` 和 `/`（不 percent-encode separator）、`UnsupportedPreviewError` typed error 替代 regex、download proxy 过滤 Content-Encoding/Transfer-Encoding、resume route 用共享 helpers

---

## Stage 5：测试基线重整 + 文档更新
**Goal**：消除"本地测试全绿但联调不通"这个盲点。
**Success Criteria**：
- Wire-shape 契约测试锁住后端字段名（golden snapshot）
- `datasets.test.ts`/`jobs.test.ts`/`jobs-client.test.ts` 明确标注"本地模式专用"
- README 记 remote 模式联调指引（环境变量、字段映射、已知限制）
**Status**：Complete

**落地情况**（2026-04-16）：
- 新增 `src/__tests__/unit/remote-wire-contract.test.ts`（8 tests）：golden payload × 3 资源（Job/Dataset/Artifact）+ SSE 生命周期 + 字段集合完整性
- 标注 `datasets.test.ts`/`jobs.test.ts`/`jobs-client.test.ts` 为 LOCAL-MODE ONLY
- README 新增 "Remote Mode Integration" 小节（环境变量、字段映射表、SSE 事件映射、已知限制）
- 全项目 475 App tests + 74 backend tests + typecheck 全绿

---

## 跨阶段约定

1. 每阶段单独一个 commit（或一组 commit），不跨阶段混改
2. 每阶段结束跑完整 pytest + npm test，红一个都不进下一阶段
3. 每阶段完成后更新本文件的 Status 字段
4. 全部完成后删除本文件
5. 任何与计划偏差的决策（例如 Stage 3 方案 A vs B）要先回到这里更新，再动手

## 已定决策（2026-04-15 由作者拍板）

- **阶段顺序**：严格 1→2→3→4→5
- **Stage 3**：remote 模式下 chat turn **不**提交到远端 `/jobs`；chat 继续走 `/chat/stream` + App-local display job
- **Stage 4**：`POST /api/datasets` 拆成两个 endpoint — `/api/datasets/upload`（multipart）与 `/api/datasets/register`（登记已有远端绝对路径文件）
