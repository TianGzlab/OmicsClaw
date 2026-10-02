# 子代理（Sub-Agent）实现原理

OmicsClaw 的子代理系统让主代理把**边界清晰的子任务**交给另一个代理独立完成：它有自己的 system prompt、收窄后的工具集、可选的模型覆盖，看不到父对话，最后只交回一段结论文本。

子代理不是一种新抽象。它就是**再跑一次同一个 `AgentEngine`**：用自己的 prompt 开局，拿父注册表里挑出来的一部分工具，**不带任何对话历史**，跑一次 `exchange`。引擎主循环没有为子代理改一行代码。

本层对应重建步骤 Step 6.12（计划 0046）。本轮**只做前台委派**。后台委派、`TaskTracker`、`@agent` 直跑都推迟到计划 0047，而 0047 目前仍是计划，没有落地为代码（见第 9 节）。

---

## 1. 系统架构

```
omicsclaw/subagent/                 ← 叶子相邻层：只 import schema、tools 与标准库
├── definition.py   SubAgentDefinition + validate() + resolve_tools()；TASK_TOOL_NAME
├── registry.py     SubAgentRegistry：有序、同名原位替换
├── frontmatter.py  parse_agent_file：YAML 子集 frontmatter + 正文 → 定义
├── loader.py       load_agents：扫描目录下的 *.md
├── prompt.py       ChildPrompt：子代理 system prompt（指令 + 工作目录 + 执行环境 + 预载 skill）
├── delegate.py     Delegate Protocol + SUBAGENT_VALUE_KEY
└── task_tool.py    TaskTool：模型唯一的委派入口；TASK_TOOL_POLICY

omicsclaw/entry/subagent.py         ← 组合根一侧：知道 engine / provider / sandbox / skills
├── GENERAL_PURPOSE           内置的 general-purpose 子代理
├── build_subagent_registry   内置 + <workspace>/.omicsclaw/agents/*.md
├── ChildRunner               Delegate 的实现：构建子引擎并驱动一次 exchange
└── DelegationIncomplete      子代理没有写出结论时抛出

omicsclaw/entry/assembly.py         ← build_app()：把 task 追加到工具表末尾
```

**本包不构建引擎。** 构建子引擎需要 provider、工具注册表、部署的沙箱状态，这些归组合根持有。`omicsclaw.subagent` 只声明 `Delegate` 这条接缝，由 `entry/subagent.py` 的 `ChildRunner` 满足。分层测试 `tests/subagent/test_subagent_is_a_leaf_layer.py` 在子进程里跑完本层真实路径后检查 `sys.modules`，断言没有拉进 `omicsclaw.engine`、`omicsclaw.entry`、`omicsclaw.skills`。

| 组件 | 代码位置 | 职责 |
|---|---|---|
| `SubAgentDefinition` | `omicsclaw/subagent/definition.py` | 一个子代理：名字、描述、指令、工具白/黑名单、模型、轮数、预载 skill |
| `SubAgentRegistry` | `omicsclaw/subagent/registry.py` | 部署提供的子代理，按注册顺序，决定 `subagent_type` 枚举 |
| `parse_agent_file` | `omicsclaw/subagent/frontmatter.py` | 把一个 Markdown 定义文件解析为已校验的定义 |
| `load_agents` | `omicsclaw/subagent/loader.py` | 非递归扫描目录，坏文件交给 `on_error` 并跳过 |
| `ChildPrompt` | `omicsclaw/subagent/prompt.py` | 子代理的 prompt，按结构满足引擎的 prompt 接缝 |
| `Delegate` | `omicsclaw/subagent/delegate.py` | "跑一个子代理并返回结论"的 Protocol |
| `TaskTool` | `omicsclaw/subagent/task_tool.py` | `task` 工具：解析参数、重绑工具上下文、暂停工具超时、调用 `Delegate` |
| `GENERAL_PURPOSE` / `build_subagent_registry` | `omicsclaw/entry/subagent.py` | 内置子代理与部署级注册表 |
| `ChildRunner` | `omicsclaw/entry/subagent.py` | 构建子引擎、转发进度、按 `StopReason` 取结论 |

---

## 2. 子代理定义

### 2.1 `SubAgentDefinition` 字段

`SubAgentDefinition` 是 `frozen=True, slots=True` 的 dataclass。

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `name` | `str` | — | 模型传给 `subagent_type` 的标识。须匹配 `^[a-z0-9][a-z0-9-]*$` |
| `description` | `str` | — | 写给模型看的"何时委派给我"。模型挑子代理时**只看这一段** |
| `system_prompt` | `str` | — | 子代理自己的指令，成为子运行的第 0 条消息 |
| `tools` | `tuple[str, ...]` | `()` | 父工具名白名单。空 = 继承父全部工具 |
| `disallowed_tools` | `tuple[str, ...]` | `()` | 白名单之后再剔除的名字 |
| `model` | `str` | `""` | 模型覆盖。空 = 沿用父模型 |
| `max_turns` | `int` | `0` | 子运行的轮数上限。`0` = 沿用引擎默认（`AppConfig.max_turns`，默认 50） |
| `skills` | `tuple[str, ...]` | `()` | 预载进子代理 prompt 的 skill 名 |
| `source` | `str` | `""` | 来源：`"builtin"` 或文件路径。仅用于诊断，没有代码按它分派 |

`validate()` 检查三个必填字段，任一不合格抛 `InvalidDefinition`（`ValueError` 子类）：名字为空或不合法、描述为空白（"模型没有东西可以据以选择它"）、system prompt 为空白（"它将在没有任何指令的情况下运行"）。

### 2.2 `resolve_tools`：子代理能拿到哪些工具

```python
def resolve_tools(self, all_names: Iterable[str]) -> tuple[str, ...]:
    # all_names 按父注册顺序过滤：白名单（空=全部） - 黑名单 - "task"
```

两个性质：

- **顺序跟随父工具表，而不是白名单的顺序。** 工具表顺序是 prompt 前缀缓存的一部分，按白名单重排会让每个子代理各自作废一份缓存。
- **`task`（`TASK_TOOL_NAME`）无论是否被点名，一律剔除。** 能委派的子代理就能委派给自己，这是防止无界递归的主闸。

### 2.3 内置 `general-purpose`

`entry/subagent.py` 的 `GENERAL_PURPOSE` 是每个部署都有的子代理，`source="builtin"`，`tools`、`model`、`max_turns` 全部留空：继承父模型，继承父的全部工具，**但 `task`、`plan_write`、`memory_write` 除外**（后两者来自 `_WITHHELD_FROM_SUB_AGENTS`，description 由这份映射渲染，逐个写明不给的工具及理由）。

它的 description 告诉模型：适合跨多个文件调研一个问题、把多步分析跑到结论，或者前几次尝试未必能找到答案的搜索。它的 system prompt 强调三点：

1. 看不到委派方的对话，信息不全时就用手头能找到的推进，因为"没有人可以问"；
2. 不能再委派；
3. 最终回复是唯一交回的东西，必须自包含：写清发现、支撑它的文件路径与命令、没能解决的问题。

### 2.3.1 内置 `module-reviewer`

`entry/subagent.py` 的 `MODULE_REVIEWER` 是第二个内置子代理（计划 0070），负责在模块重放之后、用户验收之前审查一个分析模块。它的 `tools` 只有 `read_file` 和 `use_skill`：审查者若能改它正在审的模块，审查结论就会失效。代价是它不能列目录、不能 grep，所以 system prompt 让它先读 `results/<NN_slug>/provenance/review_brief.md`。这份摘要由成功的 `replay` 写下，不超过 450 行：每个步骤第一个 cell 的原文与记账里实际调用的 skill 函数对照，读写的文件与大小，日志末尾；每张文本表的形状与前几行，小表给全文；全部输出文件的大小；changed 与 orphan 输出。读完摘要，它整份读步骤文件、模块 README 和 REPORT，其余文件只在某项检查还没定论时分段读（`start_line`、`end_line`）。h5ad 和图片看摘要里的大小和 validate 步骤的断言，`notebooks/` 不必读，它重复的是步骤文件和输出。没有摘要时它从 `results/<NN_slug>/provenance/manifest.json` 读起。计划 0071 加摘要，是因为 0070 的端到端里审查者逐个读 manifest、记账、notebook 和整张大表，一次审查要 4 到 6 分钟。

它逐项核对：步骤的输入来自 `data/` 或上游模块的 `intermediate/`、`tables/`，skill 没给定的取值都写了理由，步骤第一个 cell 声称调用的 skill 函数与 manifest 记录的一致；validate 步骤检查了 REPORT 依赖的输出；REPORT 里的数字能在表格或日志里找到、引用的图存在且不在 `orphan_outputs` 里、带免责声明；重放成功并覆盖当前的步骤文件。回复第一行必须是 `VERDICT: APPROVE` 或 `VERDICT: REVISE`，主 agent 把回复原文存进 `results/<NN_slug>/reviews/<日期>_review.md`，`accept --review` 解析的就是这一行。下一次 `replay` 会把这份审查移进 `reviews/archive/<id>/`，verdict 和 sha256 记进 manifest 的 `review_history`。

两个内置子代理都可以被 `.omicsclaw/agents/` 下同名的文件原位替换（§2.5）。

### 2.4 文件式定义

定义文件放在 **`<workspace>/.omicsclaw/agents/*.md`**（`AppConfig.agents_root()`，即 `state_dir() / "agents"`）。目录不存在时只有内置子代理，本层不会创建它。

组学场景的示例 `.omicsclaw/agents/sc-qc-reviewer.md`：

```markdown
---
name: sc-qc-reviewer
description: 单细胞 QC 复核。在 sc-preprocessing 跑完之后使用：读取输出目录里的报告与图，判断过滤阈值是否合理，列出可疑样本。
tools: read_file, bash
disallowed_tools: write_file, edit_file
max_turns: 20
skills:
  - sc-preprocessing
---

你是单细胞数据质控复核员。只读取已有输出，不修改任何文件。
按样本给出结论：线粒体比例、每细胞基因数、双细胞比例是否落在 SKILL.md 描述的范围内。
引用具体文件路径作为证据。
```

frontmatter 的键：

| 键 | 形式 | 说明 |
|---|---|---|
| `name` | 标量 | 缺省时用文件名 stem（小写化） |
| `description` | 标量 | 缺省时用正文第一条非空行 |
| `tools` / `disallowed_tools` / `skills` | 块序列（`- item`）或逗号分隔标量 | 两种写法都接受 |
| `model` | 标量 | 模型覆盖 |
| `max_turns` | 标量 | 非整数按 `0` 处理（即沿用默认） |

结束分隔符之后的全部内容就是子代理的 system prompt。

**解析器只认一个 YAML 子集**（`frontmatter.py`）：首行 `---` 到下一行 `---`；顶格的 `key: value`，成对的外层引号会去掉；`- item` 块序列；逗号分隔标量。**块标量（`>`、`|` 及其 chomping 变体）和折叠到下一缩进行的普通标量不在子集内，整个键会被丢弃，而不是只读一半。** 理由是：保留第一行会得到 `'>'`，或者一句在第一个换行处截断的描述，它能通过校验，比字段缺失更糟；字段缺失时反而有上面的回退规则。以 `#` 开头的行是注释。

### 2.5 加载与覆盖

`build_subagent_registry(config)`：

```
config.subagents 为 False → 返回 None（不挂载 task，模型看不到任何委派相关内容）
否则：
    registry = SubAgentRegistry([GENERAL_PURPOSE])
    for definition in load_agents(config.agents_root(), on_error=_report):
        registry.register(definition)       # 同名原位替换
        _warn_withheld(definition)           # tools: 点名 task 或被剔除的工具时记 warning
```

- `load_agents` 按文件名排序，结果在不同机器上稳定。读不了、解析失败、校验失败的文件交给 `on_error`，跳过后继续扫描。`omicsclaw.subagent` 本身不写日志，`entry` 的 `_report` 以 warning 级别记录**路径和错误**，**不记录文件内容**，因为定义文件就是 system prompt。
- `SubAgentRegistry.register` 遇到同名定义时**原位替换**而不是拒绝：写一个 `general-purpose.md` 就能覆盖内置定义，而且不改变 `subagent_type` 枚举的顺序。
- 定义的 `tools:` 如果点名了 `task` 或 `_WITHHELD_FROM_SUB_AGENTS` 中的工具（`plan_write`、`memory_write`），定义照常注册，同时记一条 warning，逐个写明这些工具不会给子代理及理由（见 5.3）。

---

## 3. `task` 工具

`TaskTool` 是注册在父注册表里的普通工具，按结构满足 `omicsclaw.tools.base.Tool`。

### 3.1 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|:-:|---|
| `subagent_type` | string（`enum`） | ✅ | 已注册子代理的名字，枚举值来自 `SubAgentRegistry.names()` |
| `prompt` | string | ✅ | 完整任务。子代理看不到本对话，目标、文件路径、约束、要回报什么都要写进来 |
| `description` | string | ❌ | 3–5 个词的标题，给用户看 |

`additionalProperties: false`。**没有 `background` 参数**：加参数向后兼容，删参数不兼容，所以在后台模式真正存在之前不暴露它。

### 3.2 动态定义

`definition()` 每次调用都从注册表重新渲染：描述由固定头部加上每个子代理一行 `- {name}: {description}` 组成，`subagent_type.enum` 就是注册表里的名字列表。从文件加载的子代理因此自动出现在枚举和描述里，不用再通知别处。注册表为空时描述写 `- (none configured)`。

固定头部告诉模型：适合"定义清晰、中间步骤对本对话只是噪声"的子任务，比如大范围搜索、调研很多文件、需要自我检查的分析；一两次工具调用能完成的事不要委派；子代理看不到本对话，也不能反问，完成后只报告一次。

### 3.3 `TASK_TOOL_POLICY`

```python
TASK_TOOL_POLICY = ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.AUTO,
    concurrency_safe=False,
    allowed_in_background=False,
)
```

| 字段 | 取值 | 理由 |
|---|---|---|
| `risk_level` | `HIGH` | 子代理能做它的工具能做的任何事，默认就是父代理能做的全部 |
| `approval_mode` | `AUTO` | 委派本身不是危险动作。子代理用到的每个工具都保留自己的 gate 和审批提示，这些提示仍然会送到启动父 turn 的那个人面前。在这里再问一次，问的是一件还没有人说得清的工作 |
| `concurrency_safe` | `False` | 委派是一道屏障：本轮其余工具要等它结束，不和一整次嵌套运行交错执行 |
| `read_only` | 未声明（`False`） | 见 5.4：`read-only` 权限模式会因此拒绝委派 |

### 3.4 `execute` 流程

```
TaskTool.execute(arguments)
  │ decode_arguments → payload
  │ _chosen(payload)
  │     subagent_type 为空 / 未注册 → ToolArgumentError（消息里列出可用名字）
  │ prompt 为空 → ToolArgumentError（"子代理看不到本对话"）
  │ _refuse_recursion(definition)
  │     definition.resolve_tools(("task",)) 仍含 "task" → RecursionRefused
  ▼
  outer = current_context()
  with use_tool_context(approval=outer.approval,
                        progress=outer.progress,
                        values={**outer.values, "subagent": definition.name}):
      with pause_tool_timeout():
          return await delegate.delegate(definition, prompt)
```

几个要点：

- **参数错误可以由模型纠正**，以 `ToolArgumentError` 抛出，注册表把它变成 `is_error` 的 Observation，并附上可用子代理列表。
- **`RecursionRefused` 是对 `resolve_tools` 的自洽性检查**，不是对子代理实际拿到的注册表做第二次检查：那个注册表在 `Delegate` 背后构建，本模块看不到。一旦 `resolve_tools` 不再剔除 `task`，就没有安全的解读方式，所以直接抛出而不是记日志。
- **重绑工具上下文时必须展开已有的值。** `use_tool_context` 是整体替换而不是合并，如果只写 `values={"subagent": name}`，`workspace` 等键会被解绑，子代理里的每个文件工具都会报错（`test_the_child_s_file_tools_still_resolve_the_bound_workspace` 钉住了这一点）。审批通道和进度 sink 也要显式带过去。
- **`pause_tool_timeout()` 覆盖整次委派。** 每工具超时（`tool_timeout_s`，默认 600 s）按单次工具调用设定，而一次委派包含多次模型调用。真正约束委派的是部署的 `turn_timeout_s`（见第 9 节）。

---

## 4. `ChildRunner`：一次委派怎么跑

`ChildRunner` 满足 `Delegate`。它持有的是**构建子引擎所需的零件**（provider、父 `ToolRegistry`、`AppConfig`、`SandboxBinding`、`SkillIndex`），不是一个完成的 app，因为 `task` 就挂在它要收窄的那个注册表里。

### 4.1 数据流

```
主代理 LLM ──tool_call: task(subagent_type, prompt)──►
  GatedTool(HookedTool(TaskTool))            ← task 同样经过 hook 链与权限 gate
    TaskTool.execute
      ChildRunner.delegate(definition, prompt)
        │
        ├─ provider = parent.bind(model=definition.model) if model else parent
        ├─ registry = _child_registry(definition)
        │     for name in definition.resolve_tools(parent.names()):
        │         跳过 _WITHHELD_FROM_SUB_AGENTS（plan_write、memory_write）
        │         child.register(parent.get(name), parent.policy_for(name))
        ├─ config   = _engine_config(definition)   # max_turns > 0 时覆盖
        ├─ prompt   = _child_prompt(definition)    # ChildPrompt
        │
        └─ AgentEngine(provider, registry, config)
             .exchange_stream(prompt_text, prompt=ChildPrompt)   # 没有 conversation
                 ├─ TOOL_START → report_progress("[<name>] <tool>", tool_name="task")
                 └─ 带 result 的事件 → 记下 RunResult
        │
        ▼
      _conclusion(name, result) → str 或 DelegationIncomplete
  ◄── tool result（前台，同步）── 父代理上下文
```

### 4.2 子工具集：直接用父代理的对象

`_child_registry` 从父注册表里**按名字挑出已经包装好的工具对象**（已经过 hook 链、已经被 gate 包住），再用**父注册表为它解析出的策略**重新注册：

```python
child.register(tool, self._parent.policy_for(name))
```

这使"子代理的权限不会比父代理宽"成为构造上成立的性质，而不是靠纪律维持：

- **不重建工具。** 重建会丢掉 hook 链与 gate。
- **策略要显式带过去。** `GatedTool` 读取的是**执行它的注册表**发布的策略。如果不传第二个参数，部署用 `register(policy=)` 做的收紧会在每个子代理里悄悄失效。`test_a_deployment_s_policy_override_survives_into_the_child` 与它的变异测试钉住了这一点。

子工具集保持父注册顺序，所以两个工具集相同的子代理给模型看到的工具表逐字节一致。

### 4.3 子代理的 prompt：`ChildPrompt`

`ChildPrompt` 同时满足引擎 prompt 接缝的两半：`render()` 返回自身，`system_prompt` 属性返回文本，引擎可以直接接收它，不需要适配器。每次读取 `system_prompt` 都重新组装，一次委派读一次。组装顺序：

```
<definition.system_prompt>

## Working directory

<AppConfig.workspace>

<父代理同一段执行环境说明（沙箱开启时）>

## Skill: <name>

<SKILL.md 正文（去掉 frontmatter）>
```

- **执行环境说明与父代理完全相同**（`_environment_text` 复用 `entry/sandbox.py` 的 `sandbox_section`）。子代理跑的是父代理的 `bash`，如果沙箱启动失败、实际降级到宿主机，却告诉子代理"你在容器里"，它就可能把包装到用户机器上。沙箱关闭时没有这一块。
- **预载 skill 通过 `SkillIndex.get_full_content` 读取**。任何一个加载失败（名字不在索引里、读不了）都**静默跳过**，不让一份缺失的参考资料取消整次委派。部署没有 skill 索引时（`loader=None`），`skills` 整体忽略。
- 不注入父代理的运行时契约（`OMICSCLAW.md`）、skill 目录索引、规划准则、记忆段。子代理拿到的只有上面这几块。

### 4.4 结论：按 `StopReason` 取

`_conclusion` 读取子运行的 `RunResult`：

| 子运行结果 | 交回给父代理 |
|---|---|
| `CONVERGED`，最后一条 assistant 消息有正文 | 这段正文 |
| `CONVERGED`，正文为空 | `[<name>] finished without a final message` |
| `TRUNCATED`（输出上限截断），已有正文 | `[<name>] was cut off at the output limit; ...` 加上已写出的部分 |
| `TRUNCATED`，没有正文 | 抛 `DelegationIncomplete` |
| 撞到轮数上限（`MAX_TURNS`） | 抛 `DelegationIncomplete`："stopped at the turn limit (N) without a conclusion"，并附上它最后写过的一段 assistant 文字（如果有） |
| 没有收到任何 `RunResult` | 抛 `DelegationIncomplete` |

`DelegationIncomplete` 由父注册表转成 `is_error` 的 Observation。**无论哪条路径，都不会把工具输出原文当作结论交回。** 这是 2026-09-23 缺陷修复的内容：之前撞轮数上限时会把最后一次工具输出当结论交回（计划 0046 §17）。

---

## 5. 权限与安全

| 安全层 | 机制 | 位置 |
|---|---|---|
| 禁止递归（主闸） | `resolve_tools` 总是剔除 `task` | `subagent/definition.py` |
| 禁止递归（自洽检查） | `TaskTool._refuse_recursion` → `RecursionRefused` | `subagent/task_tool.py` |
| 权限不升级 | 子工具就是父注册表里已 gate、已 hook 的对象，并带着父注册表解析出的策略 | `entry/subagent.py` `_child_registry` |
| 只能更窄 | 白名单 ∩ 父工具表 − 黑名单 − `task` − `_WITHHELD_FROM_SUB_AGENTS` | 同上 |
| 父会话计划与持久记忆隔离 | `plan_write`、`memory_write` 不给任何子代理 | `_WITHHELD_FROM_SUB_AGENTS` |
| 上下文隔离 | 不传 `conversation`，不注入父 prompt | `ChildRunner.delegate` |
| 审批不丢失 | 子代理的审批请求经 contextvars 送到父 turn 的 `ApprovalBroker` | 见 5.2 |

### 5.1 上下文隔离

`ChildRunner.delegate` 调用 `exchange_stream(prompt, prompt=ChildPrompt)` 时**不传 `conversation`**。这就是上下文隔离的全部：父对话历史根本没有路径到达子代理，所以也不需要过滤什么。反方向同样隔离：子运行的中间消息、工具输出都不进入父对话，父代理只拿到 4.4 那一段结论文本。

`test_the_child_is_given_the_task_text_and_no_parent_history` 钉住了这个性质。

### 5.2 审批穿透

子代理的 `bash`、`web_fetch`、MCP 工具需要审批时，审批请求会送到**父 turn 绑定的同一个 `ApprovalBroker`**，并以父 turn 的 `APPROVAL_REQUIRED` 帧出现在 CLI / Desktop / Channel 上。这条通路不需要专门搭建：

```
Surface 绑定 ApprovalBroker 到 ToolContext
  └─ engine/executor 为每个工具调用起一个 asyncio.Task（copy_context）
       └─ TaskTool.execute：use_tool_context(approval=outer.approval, ...)
            └─ 子 AgentEngine 又为每个工具调用起一个 Task（再 copy 一次）
                 └─ GatedTool / require_approval → 同一个 broker
```

`contextvars` 会被复制进每个新 Task，所以审批通道能穿过两层 Task 边界。计划 0027 §12.6 预测过这一点，Step 6.12 用真实的 `ApprovalBroker`（不是测试桩）验证了它（`test_the_child_s_approval_request_reaches_the_parent_s_broker`、`test_the_child_s_approval_request_becomes_a_parent_turn_frame`）。子代理被拒绝的调用照样被拒绝，不会执行（`test_a_denied_child_call_is_refused_rather_than_run`）。

`TaskTool` 在工具上下文里加了 `values["subagent"] = <name>`（`SUBAGENT_VALUE_KEY`），用于让审批卡片标明是哪个子代理在请求。**目前还没有任何 Surface 读取这个值**，审批卡片看起来和父代理自己的请求一样。显示子代理名字的工作归计划 0052 T1，尚未实现。

### 5.3 为什么 `plan_write`、`memory_write` 不给子代理

`_WITHHELD_FROM_SUB_AGENTS` 是"不下发给子代理的工具 → 理由"的映射，是剔除清单的唯一出处：`_child_registry` 按它剔除，不管定义要求了什么；`general-purpose` 的 description 由它渲染；定义文件点名其中工具（或 `task`）时 `build_subagent_registry` 记一条带理由的 warning。目前两项：

- `plan_write`：子代理的工具调用沿用父 turn 的 `session_id`，持有它的子代理会改写**父会话**的执行计划。
- `memory_write`：写入的条目进入以后每个会话的系统提示，读到恶意文件的子代理可借此种下一条永久注入。`memory_search` 只读，子代理保留。

### 5.4 `--permission-mode read-only` 会禁用委派

`read-only` 模式拒绝一切没有声明 `read_only=True` 的工具（`permission/gate.py`：没有人写下的声明不算声明）。`task` 无法诚实地声明 `read_only=True`，因为子代理可能做什么取决于它的工具，所以**在 `read-only` 模式下，`task` 本身就会被拒绝**（`test_a_read_only_deployment_refuses_the_delegation_itself`）。这是 fail-closed 的方向，但用户能直接看到这个效果：只读部署里模型可以看到 `task`，调用它却会被拒绝。

即使委派能进行，子代理里的写操作也会在各自的 gate 上被拒绝（`test_a_read_only_deployment_refuses_the_child_s_write`），因为这些工具就是父代理那几个 gate 过的对象。

规则文件同样适用：在 `<workspace>/.omicsclaw/settings.json` 里写 `"deny": ["task"]` 就能单独关掉委派，其余工具不受影响。

---

## 6. 事件与进度

OmicsClaw 没有为子代理**新增事件类型**，复用已有的进度通道：

```
子引擎 EngineEventType.TOOL_START
  → ChildRunner: report_progress(f"[{name}] {tool}", tool_name="task")
  → 父 turn 绑定的 ProgressSink
  → TurnEventType.PROGRESS
       ├─ CLI：ActivityLine.detail(...) 在当前活动行显示 "[general-purpose] bash"
       ├─ Desktop：/chat/stream 帧 "tool_output"（DESKTOP_CHAT_FRAME_TYPE）
       └─ Channel：按各适配器的渲染规则
```

每启动一个工具只转发**一行** `[<name>] <tool>`。**不转发**思考 token（`REASONING_DELTA`）和正文增量（`TEXT_DELTA`），也**不带 `IsError`**：调用方要的是结论，不是过程。这样看长时间委派的人至少能看到一些东西，而不是一个像是卡住的工具调用。

子运行不接父代理的 `HistoryCompactor`，也不接 `TurnAugmentor`：子代理的一次 exchange 里没有渐进压缩与大结果 offload，也不会注入计划块。hook 链上的审计 / 观测 hook 仍然会记录子代理的工具调用，因为那些工具就是父代理包装过的同一批对象。

---

## 7. 接线（`entry/assembly.py`）

```python
# build_app() 内，所有工具（foundation、MCP、调用方传入的）都已 hook + gate 并建好注册表之后：
subagents = build_subagent_registry(config)
if subagents is not None:
    runner = ChildRunner(
        provider=provider,
        parent=registry,
        config=config,
        sandbox=binding,
        skills=skills,
    )
    registry.register(
        gate_tools(hook_tools((TaskTool(subagents, runner),), chain), gate)[0]
    )
snapshot = registry.available_tools()
```

- **`task` 追加在工具表的最后**，排在 foundation 工具和 MCP 工具之后。它不能更早构建，因为它要收窄的正是它被挂入的那个注册表。追加在末尾可以让之前的每个工具保持在缓存前缀依赖的字节位置上。挂载 `task` 本身会让既有缓存前缀作废一次。
- `task` 和其他工具一样经过同一条 hook 链和同一个 gate。
- 启动日志的 `assembled:` 行带 `subagents=<n>`；关闭委派时为 `0`。

---

## 8. 配置

| 配置 | CLI 标志 | 环境变量 | 默认 | 说明 |
|---|---|---|---|---|
| `AppConfig.subagents` | `--subagents` | `OMICSCLAW_SUBAGENTS` | `True` | 挂载或卸载 `task` 及整个委派能力。取值 `true/false/1/0/yes/no/on/off` |
| 定义目录 | — | — | `<workspace>/.omicsclaw/agents/` | `AppConfig.agents_root()`，不可单独配置 |
| 子代理轮数 | 定义里的 `max_turns` | — | 沿用 `AppConfig.max_turns`（50） | `--max-turns` / `OMICSCLAW_MAX_TURNS` 改的是父代理与子代理共同的默认值 |
| 单次委派上界 | `--turn-timeout` | `OMICSCLAW_TURN_TIMEOUT_S` | `turn_timeout_s=None` | 整个 exchange 的墙钟上限，委派包含在内。委派期间每工具超时（`tool_timeout_s`）是暂停的，见第 9 节 |

部署标志写在 `--` 之前，例如：

```bash
oc cli --subagents false                 # 不挂载 task
oc cli --permission-mode read-only       # 注意：这同时禁用了委派（5.4）
```

一个典型的组学用法：主代理在做 bulk RNA-seq 差异分析时，把"读 `skills/bulkrna/` 下几份 SKILL.md、比较 DESeq2 与 edgeR 路线的输入要求"交给 `general-purpose`。子代理可以读很多文件、跑 `--help`，最后只交回一段带文件路径的对比结论，主对话不会被几十次 `read_file` 的输出挤满。

---

## 9. 已知限制

1. **只有前台委派。** 没有 `background` 参数，没有 `TaskTracker`，没有"下次 dispatch 前注入结果"，没有 `@agent` 直跑，也没有后台任务查看器。原因：后台结果必须在 `SessionRegistry.submit` 组 prompt 之前前置拼入，而 `submit` 今天没有这样的接缝；脱离父 turn 的 `asyncio.Task` 还需要有人持有引用、在 `shutdown` 时等待或取消，并且要显式重绑 `ToolContext`（父 turn 结束后它的 broker 已经 `abandon`）。计划 0047 第二版把后台委派标为**暂缓**。CLI 的 `/tasks` 显示的是执行计划的任务状态，不是后台子代理。
2. **委派是一道屏障，引擎侧没有上界。** `concurrency_safe=False`，本轮其余工具要排在它后面等；委派期间每工具超时被暂停。真正的上界是 `turn_timeout_s`，**默认是 `None`**（`AppConfig` 默认值，CLI 也不另设），所以一次跑飞的委派没有任何自动上界，只能 Ctrl+C。
3. **子代理的 token 用量不计入父代理。** 两次运行是两个 `RunResult`，本层不合并，所以 `/usage` 会少算。计划 0047 把"用量并入父会话"列为唯一可实施任务，尚未实现。
4. **`task` 的 `approval_mode=AUTO` 是刻意的宽松默认。** 它成立的前提是"子代理用到的每个工具都保留自己的 gate"。一旦这条性质被破坏，AUTO 就会变成漏洞，配套测试不能删。
5. **`read-only` 模式禁用委派**（5.4），这是用户能直接看到的效果，不只是内部细节。
6. **审批卡片不显示是哪个子代理在请求。** `values["subagent"]` 已经绑定，但还没有 Surface 读取它（计划 0052 T1）。
7. **定义文件没有 schema 校验。** 坏文件只记一条 warning 然后跳过。一个 typo 会让子代理悄悄消失，用户看到的只是 `subagent_type` 枚举里少了一项。
8. **frontmatter 是第二份 YAML 子集解析器。** `omicsclaw/skills/frontmatter.py` 已经有一份，但本层的 import 白名单不允许引用它。两份覆盖的子集不同：本层多认逗号分隔列表，少认块标量与折叠续行。
9. **挂载 `task` 会让既有缓存前缀作废一次**，也会占用 `reserve_tool_tokens`。
10. **子运行没有渐进压缩与 offload**（第 6 节）。一次工具输出很大的委派只能依赖轮数上限、输出上限和工具自身的截断。

---

## 10. 参考

- 计划 0046 `docs/plans/0046-subagent-layer.md`：§9 只做前台的裁定，§12 已知代价，§17 交付后缺陷修复。
- 计划 0047 `docs/plans/0047-background-subagents-and-nudges.md`：用量并入与后台委派（后者暂缓）。
- `docs/FRAMEWORK-REBUILD.md` Step 6.12。
- `omicsclaw/tools/context.py` 模块 docstring：contextvars 为什么能穿过 Task 边界。

---

## 11. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/subagent/__init__.py` | 公共接口与分层说明 |
| `omicsclaw/subagent/definition.py` | `SubAgentDefinition`、`validate`、`resolve_tools`、`TASK_TOOL_NAME`、`InvalidDefinition` |
| `omicsclaw/subagent/registry.py` | `SubAgentRegistry` |
| `omicsclaw/subagent/frontmatter.py` | `parse_agent_file`（YAML 子集） |
| `omicsclaw/subagent/loader.py` | `load_agents`、`LoadErrorSink`、`AGENT_SUFFIX` |
| `omicsclaw/subagent/prompt.py` | `ChildPrompt`、`SkillLoader` |
| `omicsclaw/subagent/delegate.py` | `Delegate` Protocol、`SUBAGENT_VALUE_KEY` |
| `omicsclaw/subagent/task_tool.py` | `TaskTool`、`TASK_TOOL_POLICY`、`RecursionRefused` |
| `omicsclaw/entry/subagent.py` | `GENERAL_PURPOSE`、`build_subagent_registry`、`ChildRunner`、`DelegationIncomplete`、`_WITHHELD_FROM_SUB_AGENTS` |
| `omicsclaw/entry/assembly.py` | `build_app` 中挂载 `task` |
| `omicsclaw/entry/config.py` | `AppConfig.subagents`、`agents_root()`、`--subagents` |
| `omicsclaw/tools/context.py` | `use_tool_context`、`pause_tool_timeout`、`report_progress`、`current_context` |
| `omicsclaw/permission/gate.py` | `read-only` 模式对未声明 `read_only` 工具的拒绝 |
| `tests/subagent/` | 定义、frontmatter、加载、prompt、`task` 工具、分层探针 |
| `tests/entry/test_subagent_wiring.py` | 端到端：结论、隔离、策略继承、审批穿透、进度、超时暂停、read-only |
