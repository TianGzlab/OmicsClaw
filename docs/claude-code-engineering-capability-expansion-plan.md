# Claude Code Engineering Capability Expansion Plan for OmicsClaw

> Status: Draft for review only
> Date: 2026-04-01
> Scope: 仅补充“尚未纳入原 Phase 1-7 的 Claude Code 工程化能力迁移计划”，本轮不执行优化
> Relation: 本文是 [docs/claude-code-migration-plan.md](./claude-code-migration-plan.md) 的补充规划，不替代原计划

## 1. 结论摘要

在原有 `Phase 1-7` 之外，Claude Code 里还有一批非常适合 OmicsClaw 的“高阶工程能力”。这些能力不直接提升单次分析算法本身，但会明显提升：

- 用户体验的一致性
- 多入口行为的可预测性
- 长期可维护性
- 安全边界清晰度
- 会话恢复与长期项目协作能力

我认为最值得继续迁移的不是远程控制、云端桥接或产品化 telemetry，而是下面 8 类能力：

1. 统一权限/审批策略引擎
2. 会话生命周期 hooks 与事件总线
3. 扩展系统 2.0：从“装包”升级到“多扩展面运行时”
4. 输出风格 profiles 与可切换的交互样式
5. Resume 2.0：更强的会话恢复、预览、过滤、任务定位
6. 面向项目与实验的文件型 scoped memory
7. `doctor`/diagnostics/context warnings 这类运维可观测能力
8. Workflow packs：可验证、可复用的分析工作流模板

这些能力和 OmicsClaw 当前状态的匹配度很高，因为 OmicsClaw 已经具备了承载它们的基础：

- `runtime/` 已有最小 tool runtime、task store、verification、transcript store
- `extensions/` 已有 manifest、validator、inventory、prompt-pack runtime
- `interactive/` 已有 session persistence、resume、plan/task 命令骨架
- `knowledge/`、`memory/`、`agents/pipeline.py` 已有知识、长期记忆、workspace 和验证闭环

所以现在不适合再做“更多功能点堆叠”，而适合把这些高阶能力补成真正的系统能力。

## 2. 本轮研读样本

### 2.1 Claude Code 参考文件

本补充计划主要基于以下文件：

- `src/Tool.ts`
- `src/tools.ts`
- `src/utils/sessionStart.ts`
- `src/utils/plugins/pluginLoader.ts`
- `src/utils/plugins/loadPluginCommands.ts`
- `src/utils/plugins/loadPluginAgents.ts`
- `src/utils/plugins/loadPluginOutputStyles.ts`
- `src/utils/plugins/loadPluginHooks.ts`
- `src/constants/outputStyles.ts`
- `src/screens/ResumeConversation.tsx`
- `src/components/SessionPreview.tsx`
- `src/types/logs.ts`
- `src/memdir/memdir.ts`
- `src/memdir/findRelevantMemories.ts`
- `src/commands/doctor/index.ts`
- `src/utils/doctorDiagnostic.ts`
- `src/utils/doctorContextWarnings.ts`
- `src/utils/contextSuggestions.ts`

### 2.2 OmicsClaw 对照文件

- `omicsclaw/runtime/tool_spec.py`
- `omicsclaw/runtime/tool_registry.py`
- `omicsclaw/runtime/tool_orchestration.py`
- `omicsclaw/runtime/query_engine.py`
- `omicsclaw/runtime/context_assembler.py`
- `omicsclaw/runtime/context_layers/output_format.py`
- `omicsclaw/runtime/task_store.py`
- `omicsclaw/runtime/transcript_store.py`
- `omicsclaw/runtime/verification.py`
- `omicsclaw/extensions/manifest.py`
- `omicsclaw/extensions/loader.py`
- `omicsclaw/extensions/runtime.py`
- `omicsclaw/extensions/validators.py`
- `omicsclaw/interactive/_session.py`
- `omicsclaw/interactive/_session_command_support.py`
- `omicsclaw/interactive/_skill_management_support.py`
- `bot/core.py`
- `docs/claude-code-migration-plan.md`

## 3. 补充迁移判断表

| Claude Code 工程能力 | 参考实现 | OmicsClaw 当前状态 | 迁移判断 | 优先级 |
| --- | --- | --- | --- | --- |
| Tool 风险/权限/审批语义 | `src/Tool.ts` | `ToolSpec` 已有 `read_only/concurrency_safe`，但没有统一 risk/approval policy | 强烈建议迁移 | P0 |
| SessionStart / Setup / Tool hooks | `sessionStart.ts`, `loadPluginHooks.ts` | manifest 中已有 `hooks` capability，但运行时未真正落地 | 强烈建议迁移 | P1 |
| Commands / Agents / OutputStyles / Hooks 多扩展面 | `loadPluginCommands.ts`, `loadPluginAgents.ts`, `loadPluginOutputStyles.ts` | 当前主要是 skill-pack + prompt-pack | 强烈建议迁移 | P1 |
| 可切换 output styles | `constants/outputStyles.ts` | 当前仅 `CLI/Bot` 两类硬编码格式指令 | 建议迁移 | P1 |
| 更强的 resume / session preview / tag / rewind | `ResumeConversation.tsx`, `SessionPreview.tsx`, `types/logs.ts` | 当前有 SQLite session 基础，但恢复语义较轻 | 建议迁移 | P1 |
| 文件型 scoped memory | `memdir.ts`, `findRelevantMemories.ts` | 当前有 graph memory 与 knowledge base，但缺项目/实验局部记忆层 | 建议迁移 | P1 |
| doctor / diagnostics / context warnings | `doctorDiagnostic.ts`, `doctorContextWarnings.ts`, `contextSuggestions.ts` | 当前只有零散 health 与日志，没有统一 doctor 面 | 强烈建议迁移 | P0 |
| WorkflowTool 风格工作流脚本 | `WorkflowTool` 相关入口 | 当前有 skill 和 research pipeline，但缺统一 workflow contract | 建议迁移 | P2 |
| 高级 mailbox / background teammate protocol | `coordinatorMode`, mailbox, sidechains | 原计划已延后 | 保持延后 | P3 |

## 4. 为什么这些能力现在值得做

原计划解决的是“主干内核化”问题，重点在 runtime、task、context、extensions、workspace verification。

而当前阶段 OmicsClaw 的主要新风险是：

- 功能已经越来越多，但用户无法清楚知道系统何时需要确认、何时会自动执行
- 扩展系统有了 manifest 和 install record，但运行时激活面还很窄
- 会话可以恢复，但恢复的是“聊天记录”，不是“项目状态”
- 输出体验已改善，但缺少可切换的风格层与统一配置
- 系统越来越复杂，但缺少一条标准化的自诊断入口
- graph memory 和 knowledge base 都有了，但缺少一个“项目局部经验”的中间层

Claude Code 在这些地方的价值不在于具体 UI，而在于它把这些能力都做成了“运行时协议”的一部分，而不是散落的小功能。

## 5. 详细补充计划

### Phase A: Tool Policy Engine

#### 目标

把 OmicsClaw 当前只覆盖 `allowed_extra_flags`、`read_only`、`concurrency_safe` 的工具元数据，升级为真正可执行的 policy 层。

#### 参考思想

- Claude Code 的 tool 不只是 schema，还带 permission context、automated checks、hooks、approval behavior。
- 这使得系统能区分“可自动做的本地安全动作”和“必须显式确认的高风险动作”。

#### OmicsClaw 当前缺口

- `runtime/tool_spec.py` 还没有 risk class / approval mode / background eligibility 等元数据。
- `interactive`、`bot`、`pipeline` 之间缺少统一的审批/阻断语义。
- 扩展安装、MCP 配置、某些 agent/pipeline 动作，风险级别没有统一表述。

#### 建议新增能力

在 `ToolSpec` 上补充：

- `risk_level`: `low` / `medium` / `high`
- `approval_mode`: `auto` / `ask` / `deny_unless_trusted`
- `writes_workspace`: 是否写工作区
- `writes_config`: 是否改配置
- `touches_network`: 是否联网
- `allowed_in_background`: 是否允许后台执行
- `policy_tags`: 如 `extension`, `mcp`, `workflow`, `plan`, `knowledge`

新增 runtime policy 层：

- `runtime/policy.py`
- `runtime/approval.py`
- `runtime/policy_state.py`

#### 交互面行为

- `interactive`/TUI：在需要确认时给出明确的人类可读原因
- `bot`：对高风险动作进行更保守降级
- `pipeline`：对 plan approval 之外再加 tool-level approval rules

#### 验收标准

- 同一个 tool 在三个 surface 中具有同源的审批行为
- 高风险动作不会因为入口差异而自动越权
- policy 决策能进入 transcript / session metadata / audit log

#### 备注

这不是为了“增加确认打断”，而是为了给未来 hooks、workflow、agent-pack 扩展提供清晰边界。

### Phase B: Lifecycle Hooks and Event Bus

#### 目标

把 Claude Code 的 SessionStart / Setup / PreToolUse / PostToolUse 一类 hooks 思想，迁移为 OmicsClaw 的事件总线和生命周期扩展点。

#### 当前判断

OmicsClaw 的 manifest 已经承认了 `hooks` 是一种 capability，但目前只是能力声明，不是运行时能力。

#### 建议事件模型

第一期只支持本地、显式、受限 hooks：

- `session_start`
- `session_resume`
- `plan_created`
- `plan_approved`
- `task_started`
- `task_completed`
- `tool_before`
- `tool_after`
- `verification_completed`
- `extension_installed`

#### 实现建议

新增：

- `omicsclaw/runtime/hooks.py`
- `omicsclaw/runtime/events.py`
- `omicsclaw/runtime/hook_payloads.py`

提供两类 hook：

- managed hook：由 OmicsClaw manifest/配置注册
- extension hook：仅本地 trusted extension 可启用

#### 安全边界

- 第一阶段不开放任意 shell hook
- 只允许本地安装且显式 trusted 的扩展注册 hooks
- hook 的输出应进入结构化 event，而不是随意拼文本

#### 用户价值

- session start 时自动注入实验室 SOP
- tool 完成后自动生成摘要或标准提醒
- pipeline 关键节点自动记录验证结论
- extension 安装后自动注册自定义工作流或说明文本

#### 验收标准

- hooks 可在 runtime 统一注册、执行、记录
- hook 失败不会破坏主查询流程
- hook 输出对用户可见且可追踪

### Phase C: Extension Runtime 2.0

#### 目标

把当前 OmicsClaw 的扩展系统从“可以装一个 pack”升级成“可以装并激活多个扩展面”。

#### 参考思想

Claude Code 的 plugin 不只是一个目录，而是可同时提供：

- commands
- agents
- hooks
- output styles

OmicsClaw 现在已经有：

- manifest
- validator
- install record / enable-disable state
- prompt-pack runtime

但还缺：

- command-pack
- agent-pack runtime activation
- hook activation
- output style activation
- workflow-pack

#### 建议扩展面

在 manifest 基础上扩展 5 类激活面：

1. `skill-pack`
2. `agent-pack`
3. `prompt-pack`
4. `workflow-pack`
5. `hook-pack`

其中第一期的来源策略：

- GitHub/untrusted：仅 `skill-pack`
- local/trusted：可启用 `agent-pack`、`prompt-pack`、`workflow-pack`
- `hook-pack` 单独 gated，默认关闭

#### 运行时加载能力

新增或扩展：

- `omicsclaw/extensions/runtime_agents.py`
- `omicsclaw/extensions/runtime_commands.py`
- `omicsclaw/extensions/runtime_hooks.py`
- `omicsclaw/extensions/runtime_workflows.py`

#### 交互面支持

- `/installed-extensions` 不只列安装信息，还应显示激活面
- `/refresh-extensions` 真正触发 commands/agents/hooks/workflows 热刷新
- `/help`、命令补全、agent 选择器、workflow 列表都能看到扩展内容

#### 验收标准

- extension 的安装、启用、禁用、刷新影响运行时真实可见
- manifest capability 与实际激活面一致
- 非 trusted extension 不可隐式获得 hooks / runtime-policy 权限

### Phase D: Output Style Profiles

#### 目标

把当前 `runtime/context_layers/output_format.py` 的“CLI vs bot”硬编码格式指令，升级为可切换的 output style profiles。

#### 参考思想

Claude Code 把 output style 视为系统 prompt 的一个可配置层，不是 UI 特例逻辑。

#### OmicsClaw 当前缺口

- 只有 surface-based 指令
- 不能针对用户偏好、任务类型、实验阶段切换风格
- 不能被 extension/prompt-pack 自然接管

#### 建议内建风格

- `default`
- `scientific-brief`
- `teaching`
- `pipeline-operator`
- `report-review`

#### 建议命令

- `/style`
- `/style list`
- `/style set scientific-brief`

#### 规则

- output style 只影响输出方式，不改变科学约束
- style 层必须在 context assembler 中独立存在
- CLI 流式输出优先级高于复杂 markdown 花样

#### 扩展兼容

- prompt-pack 或 output-style-pack 可提供新风格
- 允许某些 trusted 扩展声明“推荐 style”，但不允许静默篡改核心 guardrails

#### 验收标准

- style 配置进入 session metadata，并在 resume 后保持
- 不同 style 的指令由统一 registry 提供，不再散落在 surface 特判中
- CLI/TUI/bot 可共享 style 抽象，但各自仍保留渲染适配层

### Phase E: Resume 2.0 and Session State Semantics

#### 目标

把 OmicsClaw 当前的 session 恢复，从“恢复消息列表”升级为“恢复可继续工作的分析上下文”。

#### 参考思想

Claude Code 的 resume 不只是回放 transcript，还恢复：

- session preview
- title/tag
- worktree state
- plan slug
- file history snapshots
- content replacement state

#### OmicsClaw 当前缺口

- `_session.py` 已有 SQLite transcript，但元数据较轻
- `/sessions` 列表信息不错，但不支持 tag/title/filter/search
- resume 后能延续对话，不等于能快速找回“当前分析项目状态”

#### 建议新增 session metadata

- `title`
- `tag`
- `active_style`
- `active_pipeline_workspace`
- `active_workflow`
- `plan_slug`
- `dataset_refs`
- `enabled_extension_refs`
- `last_active_task_id`
- `workspace_kind`

#### 建议交互能力

- `/resume` 支持按 tag/title/domain/workspace 搜索
- `/session-tag <tag>`
- `/session-title <title>`
- `/current` 展示更完整状态
- 会话预览里展示：
  - 最近任务
  - 关联 workspace
  - 扩展激活情况
  - style
  - plan/task 摘要

#### 关于 rewind

不建议一开始照搬 Claude Code 的文件历史回滚。

OmicsClaw 更适合的第一阶段 rewind 是：

- rewind 到某个任务节点
- rewind 到某个 pipeline stage
- rewind 到某个 analysis workspace 快照

而不是直接对任意文件做通用回滚。

#### 验收标准

- resume 后用户能迅速理解“这是哪个分析项目、做到哪一步、下一步该干什么”
- session metadata 可用于列表过滤和搜索
- stage/task/workspace 状态与 transcript summary 对齐

### Phase F: Scoped Memory Layer

#### 目标

在 graph memory 与 knowledge base 之间，增加一层更贴近项目与实验的文件型 scoped memory。

#### 为什么需要它

当前 OmicsClaw 有：

- knowledge base：方法学和 know-how 文档
- graph memory：偏长期结构化记忆

但仍缺少：

- “这个课题组习惯用哪套 QC 阈值”
- “这个数据集坐标是 spot-level 不是 cell-level”
- “这个项目默认不用 Harmony，要先试 BBKNN”
- “这个实验室要求所有差异分析必须附带 volcano plot”

这类信息既不是通用知识，也不完全适合写进图数据库。

#### 参考思想

Claude Code 的 memdir 做了两件很关键的事：

- 用目录与 frontmatter 承载持久记忆
- 用一个轻量 side-query 从候选记忆头部选择“本轮真正相关的少量记忆”

#### OmicsClaw 建议实现

新增：

- `omicsclaw/memory/scoped_memory.py`
- `omicsclaw/memory/scoped_memory_index.py`
- `omicsclaw/memory/scoped_memory_select.py`

建议 memory scope：

- `user`
- `project`
- `dataset`
- `lab_policy`
- `workflow_hint`

#### 与 knowledge_base 的边界

- knowledge base：标准化科学知识与方法建议
- scoped memory：当前用户、项目、数据集、实验室的局部经验

两者不能混。

#### 交互面

- `/memory add`
- `/memory list`
- `/memory prune`
- `/memory scope project`

#### 验收标准

- 相关 memory 只在必要时少量注入，不制造上下文膨胀
- memory 有 freshness / scope / owner / updated_at 元数据
- scoped memory 与 graph memory 不重复存储同一层信息

### Phase G: Doctor, Diagnostics, and Context Observability

#### 目标

为 OmicsClaw 提供一条标准的“自检与诊断”入口。

#### 参考思想

Claude Code 的 `/doctor` 不只是看安装状态，还会做：

- 安装/路径诊断
- 配置/权限问题定位
- context warnings
- keybindings/config 冲突提示

#### OmicsClaw 当前缺口

- 没有 `oc doctor`
- interactive 没有 `/doctor`
- context budget 已存在内部实现，但缺少用户可见的 warnings
- extensions / MCP / knowledge index / provider 配置缺少统一体检入口

#### 建议 doctor 第一阶段检查项

- Python 环境与可选依赖
- Rscript / 常用 R 包可用性
- provider / model 配置
- session DB 状态
- knowledge index 是否存在、是否过期
- extensions 状态与 manifest 错误
- MCP 配置可解析性
- workspace 写权限
- output directory 默认路径健康性

#### 建议新增命令

- `oc doctor`
- `/doctor`
- `/context`
- `/usage`

#### context observability

把当前 runtime 里的内部统计外显给用户：

- transcript compacted refs 数量
- plan refs 数量
- advisory events 数量
- 当前 prompt layer 占用估计
- knowledge / prompt-pack / scoped memory 占用
- “接近预算上限”预警

#### 验收标准

- 出现配置/依赖/扩展/知识索引问题时，用户有单一入口排查
- diagnostics 输出可直接用于 issue 报告或环境自检
- context warning 不只是日志，而是可见提示

### Phase H: Workflow Packs

#### 目标

把 OmicsClaw 现有 skill 与 pipeline 的组合能力，提升为“可安装、可参数化、可 dry-run、可验证”的 workflow packs。

#### 为什么适合 OmicsClaw

OmicsClaw 本身就是多组学分析平台，workflow 是非常自然的组织形式：

- scRNA 标准预处理工作流
- 空间转录组标准 QC + SVG + 域识别工作流
- bulk RNA 差异表达 + 富集 + 生存分析工作流
- proteomics QC + identification + quantification 工作流

#### 与现有能力的区别

- 不是单 skill
- 也不等于 research pipeline
- 更像“预定义的、可验证的多步分析 recipe”

#### 建议实现

新增：

- `omicsclaw/workflows/registry.py`
- `omicsclaw/workflows/schema.py`
- `omicsclaw/workflows/executor.py`
- `omicsclaw/workflows/validation.py`

工作流文件可以声明：

- steps
- parameter prompts
- allowed methods
- required artifacts
- success signals
- post-run verification checks

#### 交互面

- `/workflows`
- `/workflow run <name>`
- `/workflow dry-run <name>`

#### 验收标准

- workflow 能生成可读执行计划
- workflow 的执行与 verification contract 对齐
- workflow 可通过 extension 安装

### Phase I: Optional Long-Term Mailbox and Background Coordination

#### 目标

只在前述能力稳定后，再考虑更重的 Claude Code 式 mailbox/background teammate protocol。

#### 当前建议

继续延后。

原因：

- OmicsClaw 的首要目标还是高质量分析体验，不是通用多代理编程平台
- 当前更大的瓶颈是 policy、resume、doctor、workflow、extensions，而不是 swarm

#### 可以保留的方向

- 后台长分析任务监控
- reviewer/planner/executor 结构化消息
- workflow 级后台状态通知

## 6. 推荐实施顺序

建议顺序如下：

1. Phase A: Tool Policy Engine
2. Phase G: Doctor, Diagnostics, and Context Observability
3. Phase B: Lifecycle Hooks and Event Bus
4. Phase D: Output Style Profiles
5. Phase C: Extension Runtime 2.0
6. Phase E: Resume 2.0 and Session State Semantics
7. Phase F: Scoped Memory Layer
8. Phase H: Workflow Packs
9. Phase I: Optional Mailbox and Background Coordination

### 顺序理由

- 先做 `policy`，才能给 hooks、extensions、workflow 提供安全边界
- 先做 `doctor/context observability`，可以为后续重构提供诊断工具
- hooks 必须早于扩展面大扩张，否则扩展系统只是在“能安装”，不是“能运行”
- output styles 早做，能较低风险地直接提升用户体验
- resume 和 scoped memory 应在 runtime/extension 边界清晰后再增强
- workflow packs 应建立在 policy、verification、extension runtime 稳定之后

## 7. 明确不建议迁移的部分

以下 Claude Code 能力不建议当前迁移：

- 远程 bridge / cloud session
- 内部 telemetry / GrowthBook / remote killswitch
- 复杂 IDE 联动
- 过重的 UI 特性与大量 React/Ink 组件级能力
- 先于 policy/runtime 稳定去做 swarm/team protocol

## 8. 审批时建议重点确认的决策

建议你重点确认以下 6 个决策：

1. 是否同意把“统一 tool policy/approval engine”作为下一阶段最高优先级。
2. 是否同意把 `doctor + context warnings` 提到较前位置，而不是把它视为次要 UX。
3. 是否同意扩展系统从 `skill-pack/prompt-pack` 继续扩张到 `agent-pack/workflow-pack/hook-pack`。
4. 是否同意 resume 的目标从“恢复聊天”升级为“恢复分析项目状态”。
5. 是否同意增加 scoped memory，且明确它与 knowledge base、graph memory 的边界。
6. 是否同意暂不优先做 mailbox/swarm，而先完成 policy/observability/extensions/workflow。

## 9. 审批通过后的第一轮执行建议

如果你批准这份补充计划，我建议第一轮先只做下面三项，不要一口气铺开：

1. `Phase A` 的 policy metadata 与审批框架骨架
2. `Phase G` 的 `oc doctor` 与 `/doctor` 最小版
3. `Phase D` 的 output style registry 与 `/style` 最小版

这三项完成后，OmicsClaw 会明显更像一个“工程化产品内核”，后续再往 hooks、extensions 2.0、resume 2.0、workflow packs 推进，风险会更低。

