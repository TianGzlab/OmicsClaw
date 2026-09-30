# 计划 0067：脚本化 Agent Eval（`omicsclaw/evals/`、用例集与 PR 门禁）

**状态**：已实现，待验收（2026-09-30）。第 2 版设计经 owner 认可，Q1 至 Q11 已裁定（§7.0）；实施记录见 §9。Q11 的对外动作（草稿 PR、`needs-triage` issue）未做，等 owner 同意。

### 修订说明

**第 2 版（2026-09-30）**：按第 1 轮审核修订。事实类直接改；凡是改动 D1 至 D9 或新增范围的，一律放进 §7，旁边写审核的推荐，不在正文里替 owner 决定。
- 事实：未注册工具的 `is_error` 观测在 `tools/registry.py:355`；`HookedTool.execute` 在 `hooks/chain.py:126`；`build_telemetry` 的那段 docstring 在 `telemetry.py:200-205`。
- 阻断 B1：`Headroom` 原公式漏了 `safety_ratio` 与 64k 输出预留，按原写法第一次调用就进 `EMERGENCY`。改为 Runner 直接构造 `ContextBudget(..., safety_ratio=0)`，`Headroom` 声明目标档位与触发它的消息，并写出反推公式（§3.4、§3.5 第 5 步）。
- 用例：13 号的大结果改由 `read_file` 读预置大文件产生，不再依赖按命令匹配的打桩；8、5、7 号要钉住的行为改用 hard 检查；`sc-preprocessing` 换成 oracle 里有的 `sc-clustering`；新增一条落盘检查的 `skill_routing` 用例（共 26 条）；`CASES` 改为工厂，避免模块级状态。
- 打桩：命中时校验脚本存在并要求 `--output`；`--help` 不打桩；`skill_ran_unstubbed` 只数 `python … <skill 目录>/*.py`；录取时规范化绝对路径与时间戳；手写 fallback 移到 §7。
- hermetic：删掉没人读的 `OMICSCLAW_EVAL_HERMETIC`，改为拦截非回环地址的 `socket.connect`；清 `XDG_CACHE_HOME`、`XDG_CONFIG_HOME`；`TZ` 之后调 `time.tzset()`。
- 其余：`GAP` 帧算 hard failure；summary 步骤在没有 `report.json` 时优雅退出；marker hook 按路径过滤并 `tryfirst`；补 `AgentApp` docstring（`assembly.py:828-832`）的修改；补相关测试（`tests/test_env_example.py`、`tests/sdk/test_boundary.py`）；对外动作（草稿 PR、开 issue、改徽章）标明需要 owner 同意；Q4 降为说明；Q1 至 Q7 下写明审核推荐。

**第 1 版（2026-09-30）**：初稿。

**编号约定**：owner 裁定记作 D1 至 D9；本计划的开放问题记作 Q1 至 Qn；阶段记作 E-A 到 E-E，阶段内任务记作 E-A1、E-B2 这样。附录 A 的审计条目记作 O1 至 On。

**行号约定**：以 2026-09-30 的工作树为准（`HEAD` 为 `0881aa7b`，工作树有大量未提交改动，行号读的是工作树）。实施时按符号名重新定位。

**如何核实**：代码逐处读过。另做了几项实测（附录 B）：
1. 在 scratchpad 里写了一次性探针，按本计划的 Runner 路径跑通了一个脚本化回合。
2. 在只装了 pip 最小依赖的 Python 3.11 venv 里收集并跑了一次全量测试，作为 CI 基线。
3. 在 `rapids_singlecell` 环境里跑了同一套全量测试做对照。
4. 第 2 版为核对 `Headroom` 公式跑了一个 scratchpad 脚本，只计算 token 估算，不跑测试（附录 B.4）。

两个全量都只跑了这一次，是 CI 方案必须的开工基线。

**前置与关联**：0027（引擎 `AgentEngine`、`StopReason`、重试预算）；0028/0029（工具、`BashEnvironment` seam）；0031（`build_app`、`SessionRegistry`、§8.3 要求脚本化端到端测试、附录 B.3 第 4 条建议补 `provider=`）；0039（planning gate 与 plan 注入）；0043（observability 层与它自己的对照表 §9）；0063（`OMICSCLAW.md`、`SAFETY_RULES`）。

---

## 0. 摘要

1. 新建 `omicsclaw/evals/`：`ScriptedProvider`、12 种断言、`Case`/`Result`、Runner、报告。Runner 走生产装配：给 `build_app()` 加一个 `provider=` 关键字参数，把脚本化 provider 放在 `provider_from_env` 的位置上，于是 telemetry 包装、summarizer、sub-agent、引擎拿到的都是同一个对象。现在测试里有两种替代写法：事后 `dataclasses.replace` 会漏掉 summarizer、sub-agent 和 telemetry 包装；monkeypatch `assembly.provider_from_env` 能覆盖全部消费者，但改的是模块全局名（§2.2）。
2. skill 打桩的 seam 是 `omicsclaw/tools/builtin/bash.py:806` 的 `_locally(command, cwd, timeout)`，命中时校验脚本文件存在并要求 `--output`，`--help` 不打桩。当前栈里 skill 是由 `bash` 跑 `python <skill 目录>/<script>.py` 执行的（`OMICSCLAW.md` "How to Use a Skill"），没有单独的 skill runner。`_locally` 在审批、hook、参数校验、进度上报之后才被调用，替换它只换掉"在本机起 `bash -c` 子进程"这一步。探针验证过：危险命令在 auto-approve 下照样出审批卡，被拒后根本走不到 `_locally`（附录 B.1）。
3. 用例集放在 `tests/evals/dataset/test_<category>.py`，第一期 26 条种子，覆盖 8 类。另有一条下限测试，断言用例总数不少于 26。
4. marker：新注册 `scripted_eval`，不进默认 `addopts` 的排除表达式，本地 `pytest` 默认会跑；原有的 `eval` 保留"真实 LLM、手动或 nightly"的含义。CI 的两个 job 各自用显式的 `-m` 表达式分开跑（§3.9）。
5. CI 新建 `.github/workflows/eval.yml`，两个 job：单元测试，然后 eval 用例集。实测当前工作树在 pip 最小环境里全量是 157 failed、17 errors，在 `rapids_singlecell` 里是 146 failed、11 errors（附录 B.2、B.3）。失败集中在 `tests/test_skill_runner_contract.py`、`tests/runtime/`、`tests/routing/` 这些引用已删除模块的旧测试，框架层目录只有 5 到 8 条，但 job1 跑全量的话按现状不可能绿。job1 怎么处理需要 owner 决定（Q1），这是本计划最大的开放问题；起草者与审核都推荐白名单目录加 `xfail(strict=True)` 清单。第 2 版另新增 Q8 至 Q11（录不到真实输出时的处理、按命令打桩、徽章仓库名、对外动作的同意）。
6. 清理（E-A）按 D7 执行；`routing_oracle/v1.json` 的 29 条里有 26 条的期望 skill 仍然存在，建议迁成真实模型路由 eval 的种子，同时给脚本化 `skill_routing` 用例提供 prompt（§3.12）。
7. 附录 A 审计了 `omicsclaw/observability/`：span 树、GenAI/Langfuse 属性、6 个指标、每次交互结束 flush、Setup 失败退回 noop 都已对齐；缺口有三处（Langfuse `x-langfuse-ingestion-version=4` header 在文档和 `.env.example` 里都没写；`build_telemetry` 的 docstring 仍说参考实现把 Setup 失败当致命错误，0043 §9 已更正而代码注释没改；缺一条走生产装配的 span 树端到端检查）。E-E 只修这三处。

---

## 1. 目标与非目标

### 1.1 目标

- 一个可复用的 eval 包 `omicsclaw/evals/`，新测试用它的 `ScriptedProvider`，不再各写一个假 provider。
- 26 条确定性的脚本化用例：LLM 的回复写死，测的是引擎和装配在给定决策下的行为（工具派发、观测注入、终止条件、权限、plan 注入、压缩、记忆、skill 调用）。
- 每个 PR 自动跑，hard 断言全部通过才算绿；soft 断言只记警告。报告写进 Step Summary，完整报告作为 artifact 保留 30 天。
- 清掉指向已删除代码的 CI 与脚本、没人引用的 fixture 和两份失效的顶层测试。
- 审计 observability 相对 harness9 的差距，只修缺口。

### 1.2 非目标（D2、D9）

- 真实模型路由 eval（列入 §1.3，本期不实现，不卡 PR）。
- LLM judge。
- 迁移现有测试里的假 provider。实测数下来是 33 个测试文件、44 个 `async def generate(` 实现，和 brief 里的"约 149 个"对不上（§2.5）；无论多少，本期都不迁。
- 恢复旧 `pr-ci.yml`。
- `run_skill`（ensemble）的子进程打桩。Runner 不打开 ensemble（`build_app(ensemble=None)`），`run_skill` 不挂载，见 §3.6。

### 1.3 后续

- 真实模型路由 eval：用 §3.12 迁出的种子，`-m eval`，nightly 或手动，不卡 PR。
- 把 §3.3 的四个用例集内部检查（`SentContains`、`ToolResultContains`、`StopReasonIs`、`CountIs`）提升进包，视 Q3 的裁定。
- 更多 safety 用例：`.env` 永远要问、子进程拿不到 `OMICSCLAW_REMOTE_AUTH_TOKEN`（§3.10 末尾列了候选）。

---

## 2. 现状与证据

### 2.1 owner 已裁定（照此写，不重新讨论）

| 编号 | 裁定 |
|---|---|
| D1 | 一份计划覆盖 `omicsclaw/evals/`、用例集、CI gate；observability 差距审计作附录 |
| D2 | 第一期只做 harness9 式脚本化、密闭、确定性 eval，每 PR 跑，必须全绿；真实模型路由 eval 列为后续；无 LLM judge |
| D3 | 包内容：`ScriptedProvider`、12 种断言、`Case`/`Result`、Runner（`build_app(provider=)`、MCP 关、session/memory 内存实现、tmp 工作区、权限默认自动放行、`permission="ask"` 由脚本批准或拒绝、compaction 默认关）、hermetic 环境、JSON+Markdown 报告 |
| D4 | skill 打桩只替换拉起子进程的那一层；`skill_stubs={"<skill>": StubResult(...)}`；StubResult 取自一次真实运行，存成 fixture |
| D5 | 用例集 `tests/evals/dataset/test_<category>.py`；harness9 六类里 OmicsClaw 具备的 + `skill_routing` + `safety`；约 24 条种子；下限测试 |
| D6 | 新建精简 `eval.yml`：清 API key、`OTEL_ENABLED=false`；job1 单元测试，job2 eval；gate = hard 全过；报告进 Step Summary，artifact 30 天 |
| D7 | 清理：删 `eval-nightly.yml`、`scripts/run_eval.py`、四个无引用 fixture、两份失效顶层测试；`routing_oracle/v1.json` 先读再决定去留 |
| D8 | 附录做 observability 差距审计，外加一条 Runner + 内存 exporter 的 span 树断言；只修缺口 |
| D9 | 不在范围：真实模型路由 eval、LLM judge、迁移现有假 provider、恢复 `pr-ci.yml` |

### 2.2 引擎、provider 与装配

- `AgentEngine`（`omicsclaw/engine/loop.py:155`）：`run`（:189）、`run_stream`（:226）、`exchange`（:254）、`exchange_stream`（:299），ReAct 循环只有 `_kernel`（:361）一份。停止原因只有三种：`CONVERGED`、`MAX_TURNS`、`TRUNCATED`（`engine/types.py:47-91`）。provider 失败以 `ProviderError` 抛出，不是 `stop_reason`；撞到 `max_turns` 不是错误，轨迹保留。这一点和 harness9 不同（harness9 的 `MaxTurns` 表现为 `RunError`），直接影响 `Error`/`NoError` 断言的语义（§3.3）。
- 工具派发：`execute_tool_calls`（`engine/executor.py:145`），并发安全的调用同批并行，观测按请求顺序回填。未注册的工具名由 registry 返回 `is_error` 观测（`tools/registry.py:353-355`，`_failed(call, self._unknown_tool_message(...))`）。
- 重试：`generate_with_retry`（`engine/retry.py:124`），`generate_retries=3`、`generate_retry_base=1.0` 秒（`engine/config.py:102,112`）；429 和 5xx 重试，其他 4xx 不重试。`AppConfig.engine_config()`（`entry/config.py:686-695`）只传 `max_turns` 与 `tool_timeout`，重试间隔无法从 `AppConfig` 调小。
- provider 协议 `LLMProvider`（`provider/base.py:102`）：`name`、`generate`（:116）、`generate_stream`（:134，非 `async def`，直接返回异步迭代器）、`bind`（:152）。`Completion`（:71）带 `message`、`usage`、`finish_reason`；`ProviderError`（:39）带 `provider` 与 `status_code`。流式最后一块是 `StreamChunkType.DONE`（`schema/stream.py:47-64`）。
- `build_app()`（`entry/assembly.py:1122`）没有 `provider=`，docstring（:1175-1186）让测试事后 `dataclasses.replace` 掉 `provider` 和 `engine`。provider 在函数里有六个消费者：telemetry 包装（:1220-1222）、`build_tuning_model`（:1246）、`ChildRunner`（:1293-1299）、`build_summarizer`（:1319）、`AgentEngine`（:1330-1332）、`AgentApp.provider`（:1356）。事后替换只改得到最后两个：summarizer 和 sub-agent 仍绑着原 provider，替换进去的 provider 也没被 `TracedProvider` 包，拿不到 `llm_request` span。现有测试两种写法都有：`tests/entry/test_telemetry_wiring.py:277-281` 用 `dataclasses.replace`；同一文件 :90-96 的 `offline` fixture monkeypatch `assembly.provider_from_env`，这样六个消费者都拿到假 provider，代价是依赖 `assembly` 模块里的导入名，并且真实 provider 的构造逻辑也被一并跳过。`open_app()` 在 :1430。
- 会话路径：`attach_sessions(app, store=)`（`entry/session.py:895`）挂上 `SessionRegistry`；`submit()`（:351）立即返回 `TurnHandle`；每个回合由 `TurnRunner`（`entry/turn.py:446`）在自己的 Task 里跑，走 `exchange_stream`（`turn.py:301` 的 `_stream`），外面包一层 `app.telemetry.run(...)`（`turn.py:649` 的 `_sequence`，:667）。审批请求以 `APPROVAL_REQUIRED` 帧发布（`entry/approval.py:125-160`），`TurnHandle.approve(request_id, decision)`（`turn.py:838`）回答。`InMemorySessionStore` 在 `session.py:194`。
- 压缩：`build_compactor`（`entry/compaction.py:76-148`）每次交换读 `app.budget` 与 `config.compact_at`（默认 `Pressure.WARN`，`entry/config.py:418`）；没有"关"这个档位。summarizer 用 `provider.generate(messages, None)`（`assembly.py:786`），也就是 `tools=None`；记忆抽取也走同一个 summarizer（`entry/memory.py:236-251`）。引擎本身每轮都传 `tuple(available_tools())`，从不传 `None`。
- 记忆：`open_memory`（`entry/memory.py:139`）固定打开 `<workspace>/.omicsclaw/memory.db`，`build_app` 没有换成内存库的入口（`Database` 本身支持 `":memory:"`，`memory/database.py:76`）。
- skill：`AppConfig.skills_root()`（`entry/config.py:582`）默认 `<workspace>/skills`，`repo_root()` 是它的父目录，`OMICSCLAW.md` 从 repo root 读。`use_skill` 参数是 `skill_name`，结果末尾带 `Skill directory: <绝对路径>`（`skills/use_skill.py:33-44,142-145`）。`Skill.domain`（`skills/skill.py:74`）取 skill 路径的第一级目录。`skill_env` 默认 `probe`（`entry/config.py:302`），`use_skill` 会起子进程检查依赖能否 import（`skillenv/probe.py:416`），结果取决于机器装了什么。
- 工具清单（探针实测，默认配置）：`read_file, write_file, edit_file, bash, web_fetch, web_search, use_skill, plan_write, memory_search, memory_write, task`。`task` 来自内置的 `general-purpose` sub-agent（`entry/subagent.py:153-179`），定义目录在工作区的 `.omicsclaw/agents/`，tmp 工作区里为空。
- `SAFETY_RULES`（`entry/assembly.py:228-237`）四条：基因数据不出本机；每份报告原文附免责声明；只用 SKILL.md 的方法；覆盖已有报告前先警告。`TOOL_GUIDANCE`（:244-253）。二者作为 "## Safety rules"、"## Tool guidance" 两节进系统提示（:682-683）。
- 权限：`PermissionMode` 四种（`permission/modes.py:20-59`）。`AUTO_APPROVE` 放行普通调用，但 deny 规则、危险命令模式（`permission/danger.py:93` 起）和受保护路径（`.omicsclaw/`、`.env`、规则文件，`permission/gate.py:357-427`）仍然要问。

### 2.3 测试现状

- pytest 配置（`pyproject.toml:452-498`）：`addopts = "-v --import-mode=importlib -m 'not slow and not demo and not eval'"`；`eval` marker 描述为"real-LLM behavioral parity tests; run manually or via nightly cron"（:492）。目前只有 `tests/ensemble/tuning/test_live_contract.py` 用它。
- 异步测试一律 `asyncio.run`，仓库不依赖 pytest-asyncio（例如 `tests/engine/test_loop.py:136-144`；`rapids_singlecell` 里也没装 pytest-asyncio）。
- `tests/conftest.py:36-60` 每个测试前清掉仓库根 `.env` 里出现的键。
- `tests/observability/_support.py` 已有 `RecordingTracer`（:86）、`RecordingMeter`（:107），是本层 `Tracer`/`Meter` 协议的内存实现；`tests/observability/test_end_to_end.py` 用手搭的引擎断言三层 span 树，没有走 `build_app`。
- 失效的 fixture（grep 过 `*.py *.toml *.yml *.json Makefile *.sh`，代码与配置里零引用，只在文档里出现）：`tests/fixtures/golden_routing/`、`routing_oracle/`、`routing_budget/`、`tool_list/`。
- `tests/test_benchmark_campaign.py:9` import `omicsclaw.skill.benchmark_campaign`，`tests/test_evaluation_protocol.py` import `omicsclaw.skill.*`，两者收集即报错。

### 2.4 CI 现状

- `.github/workflows/` 现有 `claude-code-review.yml`、`claude.yml`、`deploy-website.yml`、`eval-nightly.yml`；`pr-ci.yml` 已暂存删除（git status `D`）。PR 上没有任何 workflow 跑单元测试。
- `eval-nightly.yml` 跑 `scripts/run_eval.py`，后者调 `pytest -m eval tests/eval/`（`scripts/run_eval.py` 约 :36-55），`tests/eval/` 已删除。
- `README.md:26` 与 `README_zh-CN.md:26` 的 CI 徽章指向 `pr-ci.yml`。
- 依赖：`pyproject.toml` 核心依赖只有 `setuptools`、`socksio`、`pydantic`（:52-65）；`openai`、`anthropic`、`httpx`、`numpy` 等在 `environment.yml` Tier 4（conda）。`requires-python = ">=3.11,<3.14"`（:41），classifier 列 3.11、3.12。实测 import `omicsclaw.entry.assembly/session/turn/compaction` 与 `omicsclaw.observability` 不拉起任何第三方包，SDK 都是延迟导入。

### 2.5 对 brief 的更正

1. "tests/ 里约 149 个各自为政的假 provider"：按 `async def generate(` 数是 44 个实现、分布在 33 个文件；按 `def generate_stream` 数是 33 个、27 个文件。149 这个数没能复现。结论不变：本期不迁。
2. "skill runner 拉起子进程的那一层"：当前栈没有 skill runner。`oc run` 与 `omicsclaw.skill.runner` 已删（`OMICSCLAW.md` "How to Use a Skill"：there is no central command table … and no `oc run`），skill 由 `bash` 执行。唯一还在的"skill runner"是 ensemble 的 `run_skill`，子进程在 `omicsclaw/ensemble/execution.py:130,160`，本期不挂载。§3.6 给出的 seam 是 `bash` 的本机执行函数。
3. "`build_app` docstring 约 1175-1183"：实际是 :1175-1186（含两行 `dataclasses.replace` 示例与 frozen 说明）。
4. "session/memory 用内存实现"：session 可以（`InMemorySessionStore`）；memory 没有注入口，Runner 用 tmp 工作区里的 SQLite 文件，见 §3.5 第 6 步的说明。审核认为 D3 的原意只要求 session 在内存里；若 owner 的本意包括 memory，按 §3.5 的说明提出。
5. "compaction 默认关"：引擎没有关闭压缩的档位（`compact_at` 最低是 `WARN`）。本计划把它解释为"默认用大窗口，使种子用例到不了 `WARN`，再由 Runner 的 `compaction_unexpected` 检查兜底"。这是本计划的解释，owner 可以否定。

---

## 3. 设计

### 3.1 包结构

```
omicsclaw/evals/
  __init__.py      公开 API：ScriptedProvider, ScriptedTurn, tool_call, Case, Result,
                   StubResult, 12 个断言类, run_case, arun_case, SuiteReport
  provider.py      ScriptedProvider、ScriptedTurn、RecordedCall、tool_call()
  assertions.py    Failure、Assertion 协议、12 种断言
  case.py          Case、Result、ApprovalScript、Headroom
  runner.py        run_case / arun_case：装配、驱动、收集、断言
  stubs.py         StubResult、skill 打桩上下文、record_stub_result()
  hermetic.py      hermetic_env()：清凭据、关 OTEL、隔离 HOME 与 XDG 目录、拦截非回环网络
  report.py        build_report、write_json、write_markdown、step_summary；
                   `python -m omicsclaw.evals.report` 入口
```

依赖方向：`omicsclaw.evals` 只 import `omicsclaw.entry` 及以下各层，任何层都不 import `evals`。`tests/entry/test_entry_is_the_top_layer.py` 的下层清单（`_LOWER_LAYERS`）不含 `evals`，现有规则不受影响；E-B 加一条小测试：`omicsclaw/` 下除 `evals/` 自己以外没有文件 import `omicsclaw.evals`。包随 wheel 发布（`pyproject.toml` 的 `packages.find` 包含 `omicsclaw.*`），和 harness9 把 `internal/evals` 放在主模块里一致。

### 3.2 `ScriptedProvider`

```python
@dataclass(frozen=True)
class ScriptedTurn:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    err: BaseException | None = None
    usage: Usage | None = None          # None 时用 provider 的固定 usage

class ScriptedProvider:
    def __init__(self, *turns: ScriptedTurn, name: str = "scripted",
                 usage: Usage = Usage(input_tokens=100, output_tokens=50),
                 on_exhausted: str = "converge",        # "converge" | "raise"
                 exhausted_text: str = "done.",
                 side_replies: Sequence[str] = (),
                 side_default: str = "") -> None: ...
    name: str
    async def generate(self, messages, tools=None) -> Completion
    def generate_stream(self, messages, tools=None) -> AsyncIterator[StreamChunk]
    def bind(self, **overrides) -> ScriptedProvider      # 返回共享脚本与记录的视图
    @property calls -> tuple[RecordedCall, ...]          # 主线调用
    @property side_calls -> tuple[RecordedCall, ...]     # tools is None 的调用
    @property turn_index -> int
    def reset(self) -> None
```

行为：

- 每次调用先记下 `RecordedCall(messages=tuple(messages), tools=tuple(t.name for t in tools), full_tools=tuple(tools), bound=overrides)`，再取下一个 `ScriptedTurn`。`err` 非空时 `generate` 抛出它，`generate_stream` 同样在迭代时抛出（引擎两条路径都把 `ProviderError` 交给重试预算，`loop.py:465-532`）。
- `tools is None` 的调用是 summarizer 和记忆抽取（§2.2），不消耗主线脚本，改从 `side_replies` 按序取，取完用 `side_default`。这样一个用例里压缩触发与否不会让主线脚本错位。
- `generate_stream` 只产出一个 `DONE` 块（带 message、usage、`finish_reason`：有工具调用时 `"tool_use"`，否则 `"end_turn"`）。和 harness9 一样不逐 token 流，文本增量不在测试范围。
- 脚本用尽：默认 `on_exhausted="converge"`，返回 `exhausted_text` 的纯文本回复，让循环自然收敛，并在 `Result.warnings` 里记一条 `script_exhausted`（soft），提醒用例作者脚本比实际短。`"raise"` 时抛 `ProviderError("script exhausted", status_code=400)`，用于"多调一次就算错"的用例。
- 固定 usage：每次主线调用返回同一个 `Usage`，observability 用例据此断言 token 属性；`ScriptedTurn.usage` 可以逐轮覆盖。
- 线程与协程安全：状态变更都在一把 `threading.Lock` 里完成（取下一轮、追加记录都是同步代码，不跨 `await` 持锁），同一个 provider 被 sub-agent 与主循环并发调用时不会重复发出同一轮。
- `bind()` 返回一个共享同一脚本、同一记录的轻量视图，只把 overrides 记进 `RecordedCall.bound`。summarizer 在设了 `summary_model` 时会 `bind(model=...)`（`assembly.py:808-811`），视图保证它的调用也被记录。
- `reset()` 把游标与两份记录清零。
- `tool_call(name, args: dict | str, id=None) -> ToolCall`：构造 `ToolCall`，`args` 是 dict 时 `json.dumps`，`id` 缺省按调用顺序生成 `call_<n>`。

### 3.3 断言

```python
@dataclass(frozen=True)
class Failure:
    assertion: str          # 断言的 name
    message: str
    is_soft: bool = False

class Assertion(Protocol):
    @property
    def name(self) -> str: ...
    def check(self, result: Result) -> Failure | None: ...
```

12 种（D3）。前 8 种照搬 harness9 的语义，只在 OmicsClaw 语义不同处调整；后 4 种是 OmicsClaw 的。

| 断言 | 软硬 | 判据 |
|---|---|---|
| `ToolCalled(tool, min_times=1)` | hard | `result.tool_calls_executed` 中该工具名出现次数 ≥ `min_times` |
| `ToolNotCalled(tool)` | hard | 一次都没出现 |
| `OutputContains(text)` | hard | `result.final_output` 含 `text` |
| `OutputExcludes(text)` | hard | 不含 |
| `NoError()` | hard | `result.run_error is None` |
| `Error(kind=None)` | hard | `run_error` 非空；给了 `kind`（异常类）时还要 `isinstance` |
| `MaxTurns(n)` | soft | `result.turn_count <= n` |
| `MaxToolCalls(n)` | soft | `len(tool_calls_executed) <= n` |
| `SkillInvoked(skill, domain=None)` | hard | `result.skill_runs` 里有该 skill（打桩层或真实执行记录），给了 `domain` 时还要 `Skill.domain == domain` |
| `ToolArgs(tool, subset)` | hard | 至少一次该工具的调用，其 JSON 参数是 `subset` 的超集（递归：dict 按键子集，list 按位置等长逐项子集，其余相等） |
| `PermissionRequested(tool, approved=None)` | hard | `result.approvals` 里有该工具的审批请求；给了 `approved` 时还要决定一致 |
| `NoWriteOutside(root="workspace")` | hard | `result.fs_changes` 里每条路径都在 `root` 之内；`"workspace"` 解析为本用例的工作区，`"workspace/<子路径>"` 解析为工作区下的子目录 |

与 harness9 的语义差别：

- `tool_calls_executed` 取自 `TOOL_START` 帧，即引擎确实派发了的调用，包括随后被权限拒绝、参数校验失败或工具不存在的调用。harness9 在 hook 链最前端记录，效果相同；OmicsClaw 的 hook 装在权限门里面（`assembly.py:1263-1281`），被拒的调用到不了 hook，所以不能用 hook 记录。
- `final_output` 是 `TurnOutcome.reply`（`entry/turn.py:133-138`，最后一条有文本的 assistant 消息），取自真实轨迹，而 harness9 是倒着扫脚本（`harness.go:161-168`）。多次交换的用例取最后一次。
- `run_error` 是回合以 `terminal="failed"` 结束时的原异常（`EXCHANGE_END.error`）。`MAX_TURNS` 不是错误，`Error()` 测不到它；撞顶用 `result.stop_reason` 判断（见下）。
- `turn_count` 是所有交换里主线模型调用的总数（`len(provider.calls)`），重试也计入，这和 harness9 的 `TurnIndex` 口径一致。引擎自己的 `RunResult.turns` 另存为 `result.engine_turns`。

用例集内部检查。有几条用例要断言"送进模型的内容"或"工具结果"，12 种断言都覆盖不到。第一期在 `tests/evals/dataset/_checks.py` 里写三个实现 `Assertion` 协议的类，不进包：`SentContains(text, call=-1, role=None, times=None)`（第 `call` 次主线调用的消息里含 `text`；给了 `times` 时要求恰好出现这么多次）、`ToolResultContains(tool, text, is_error=None)`、`StopReasonIs(reason)`，以及下文的 `CountIs`。是否提升进包见 Q3。

Runner 另外追加几条隐式 hard 检查，不需要用例声明：`approval_unscripted`（出现了脚本没安排的审批请求）、`compaction_unexpected`（`compaction=False` 的用例里出现了 `COMPACTION` 帧）、`stream_gap`（出现 `GAP` 帧）、`headroom_infeasible`（§3.4）、`case_timeout`、`stub_target_missing`（§3.6）。用例的前提一旦失效，这些检查会让它直接失败。

用例集内部检查另加一个 `CountIs(what, n)`，对 `Result` 上的计数做精确比较，例如 `turn_count == 1`、某段文本在某次请求里出现的次数、system 消息条数。用例要钉住的行为都用 hard 检查表达，soft 的 `MaxTurns` 只用来提示效率。

### 3.4 `Case` 与 `Result`

下面是字段示意；可变默认值实现时用 `field(default_factory=...)`。

```python
@dataclass(frozen=True)
class Case:
    id: str                                     # "category/name"
    category: str                               # 必须等于 id 的前缀，构造时校验
    prompt: str
    provider: Callable[[], ScriptedProvider]   # 工厂：每次运行新建一个
    assertions: tuple[Assertion, ...]
    followups: tuple[str, ...] = ()             # 同一 session 的后续交换
    max_turns: int = 20
    permission: Literal["auto", "ask"] = "auto"
    approvals: tuple[bool | ApprovalDecision, ...] = ()   # 按出现顺序回答审批
    skill_stubs: Mapping[str, StubResult] = {}
    compaction: bool = False
    headroom: Headroom | None = None            # compaction=True 时必填，见下
    files: Mapping[str, str | bytes] = {}       # 预置到工作区的文件
    outside_files: Mapping[str, str] = {}       # 预置到工作区旁边的哨兵目录
    env: Mapping[str, str] = {}                 # 用例专属环境变量
    config: Mapping[str, object] = {}           # AppConfig 字段覆盖
    telemetry: Callable[[], Telemetry] | None = None   # 工厂；observability 用例返回记录型 telemetry

@dataclass(frozen=True)
class Result:
    case: Case
    passed: bool
    turn_count: int
    engine_turns: int
    stop_reason: StopReason | None
    tool_calls_executed: tuple[str, ...]
    tool_calls: tuple[ToolCall, ...]            # 名字加参数，ToolArgs 用
    tool_results: tuple[ToolResult, ...]
    final_output: str
    run_error: BaseException | None
    failures: tuple[Failure, ...]
    warnings: tuple[Failure, ...]
    duration_s: float
    provider_calls: tuple[RecordedCall, ...]
    side_calls: tuple[RecordedCall, ...]
    skill_runs: tuple[SkillRun, ...]            # (skill, domain, command, stubbed)
    approvals: tuple[ApprovalRecord, ...]       # (tool, risk, reason, approved, scripted)
    fs_changes: tuple[FsChange, ...]            # (path, kind: created|modified|deleted)
    compactions: tuple[CompactionRecord, ...]
    workspace: Path
```

`provider` 与 `telemetry` 是工厂，不是实例。`CASES` 是模块级列表，参数化测试、重跑失败用例（`--lf`）或同一进程里跑两遍时，实例里的游标、调用记录和 `RecordingTracer` 的 span 会从上一次带过来。Runner 每次运行调用一次工厂；`tool_call()` 生成 id 的计数器挂在 provider 实例上，所以也随工厂重置。Runner 另外断言工厂返回的 provider `turn_index == 0`，防止工厂返回了共享实例。

`Headroom` 描述压缩用例想走的档位，由 Runner 反推窗口：

```python
@dataclass(frozen=True)
class Headroom:
    target: Pressure                 # 期望触发的档位：WARN、SOFT 或 FULL
    trigger_call: int                # 第几次主线调用之前应当触发（0 起）
    trigger_tokens: int              # 从基线到触发那次调用，对话预计增长的 token 数
```

`ContextBudget.usable_tokens = context − reserve_output − reserve_tool − int(context × safety_ratio)`（`context/budget.py:241-249`），档位按 `used / usable` 与 0.60、0.70、0.80、0.95 比较（`budget.py:183-186,264-275`），`used` 是整段对话（含 system 消息）的估算 token 数。若沿用 `claude-sonnet-4-5` 的预算（64k 输出预留、10% 安全余量），一个十几 k 的窗口 `usable` 会是负数，第一次调用就是 `EMERGENCY`。所以 Runner 不改 `context_tokens` 了事，而是直接构造：

```python
ContextBudget(context_tokens=U + OUT + TOOL, reserve_output_tokens=OUT,
              reserve_tool_tokens=TOOL, safety_ratio=0.0)
```

其中 `OUT = 1024`，`TOOL` 取 `estimate_tool_tokens(app.tools_snapshot)`（`measure()` 取声明值与实测值的较大者，`budget.py:303-333`，两者相等时不会出现 shortfall），`U` 是希望的 `usable_tokens`。设 `B` 为基线（第一次调用送出的消息估算 token 数，用 `estimate_messages_tokens(compose(app, (), prompt))` 算），`G = trigger_tokens`，`t` 为目标档位的阈值，`t'` 为下一档的阈值。要求：

```
B / U < warn_at            （第一次调用不触发任何档位）
t ≤ (B + G) / U < t'       （触发那次调用正好落在目标档位）
```

取 `U = floor((B + G) / t)`，Runner 检查 `B / U < 0.60` 与 `(B + G) / U < t'`，任一不成立就以 hard failure `headroom_infeasible` 结束，并在消息里给出 `B`、`G`、`U`，提示用例作者调大 `G` 或换档位。`G` 由用例作者按脚本估算，Runner 不猜。

实测数字（附录 B.4，scratchpad 脚本，eval 配置、`memory=False`）：基线 `B ≈ 10,267`（完整 skill 索引约占 8k），`TOOL ≈ 2,897`，400 行预置表格用 `read_file` 读回的 8 KiB 约 2,049 token。由此：
- 13 号（目标 `WARN`）：`G ≈ 2,049 + 600 = 2,649` 时 `U = 21,526`，`B/U = 0.477`，`(B+G)/U = 0.600`，可行。
- 14 号（目标 `FULL`）：`B/U < 0.60` 与 `(B+G)/U ≥ 0.80` 同时成立要求 `G > B/3 ≈ 3.4k`。同样的 `G ≈ 2.6k` 不可行（`B/U = 0.636`）。所以 14 号的脚本要让对话在触发前增长 4k 以上（例如读两份预置表格），或者用例设 `config={"skills_index": "compact"}` 把 `B` 降到约 2k。这是实施时要照着公式核对的地方，`headroom_infeasible` 会在不可行时直接报出来。

### 3.5 Runner

`run_case(case, tmp_path) -> Result` 是同步入口，内部 `asyncio.run(arun_case(...))`，和仓库的异步测试写法一致。步骤：

1. 目录：`tmp_path/ws`（工作区）、`tmp_path/outside`（哨兵目录，放 `outside_files`）、`tmp_path/home`。写入 `files`。
2. hermetic 环境（`hermetic.py`，参考 harness9 `testenv.go`），用一个上下文管理器改 `os.environ`、结束时恢复：
   - 清掉名字以 `_API_KEY`、`_TOKEN`、`_SECRET` 结尾的变量（harness9 的三种）；
   - 另外清掉 `LLM_*`、`OMICSCLAW_PROVIDER`、`OMICSCLAW_MODEL`、`OMICSCLAW_BASE_URL`。`resolve_config` 会读它们（`provider/config.py:608-620`），而 `build_app` 即使拿到注入的 provider 也要用 `resolve_config` 算模型名；
   - `OTEL_ENABLED=false`，清掉 `OTEL_EXPORTER_*` 与 `OMICSCLAW_OTEL_CAPTURE_CONTENT`；
   - `HOME=tmp_path/home`，任何写到 `~/.omicsclaw` 的代码都落进可检查的目录；同时清掉 `XDG_CACHE_HOME`、`XDG_CONFIG_HOME`，否则 overlay 目录（`entry/config.py:309`、`skillenv/overlay.py:106-107`）和 CLI 输入历史（`entry/cli/_input.py:368`）会绕过 `HOME` 落到真实位置；
   - `TZ=UTC` 后调用 `time.tzset()`（只改环境变量不会影响已加载的时区），退出时恢复原值并再调一次；`LANG=C.UTF-8`；
   - 网络：在上下文内把 `socket.socket.connect` 与 `connect_ex` 换成一个包装，目标不是回环地址（`127.0.0.0/8`、`::1`、Unix socket）时抛 `OSError("network disabled in hermetic eval")`。第 1 版用来标记隔离模式的 `OMICSCLAW_EVAL_HERMETIC` 删掉了，因为没有任何代码读它；拦截 connect 能直接挡住 `web_fetch`、`web_search` 或误建的真实 provider 发出的请求；
   - 最后叠加 `case.env`。
   pytest 里另有 fixture 版 `hermetic`（`tests/evals/conftest.py`，用 `monkeypatch` 实现同一张表），用例文件不必每个都手写。
3. 配置：
   ```python
   AppConfig(workspace=ws, skills_dir=REPO/"skills",
             provider="anthropic", model="claude-sonnet-4-5",   # 只用来查窗口与输出上限
             skill_env=SkillEnvMode.OFF, sandbox=SandboxMode.OFF,
             permission_mode=AUTO_APPROVE if case.permission == "auto" else DEFAULT,
             max_turns=case.max_turns, **case.config)
   ```
   `skill_env=OFF` 是为了确定性：`probe` 的结果取决于机器装了哪些包。`claude-sonnet-4-5` 在模型表里是 200k 窗口、64k 输出（`provider/_model_limits.py`），种子用例远到不了 `WARN`。
4. 装配：`build_app(config, provider=case.provider(), telemetry=case.telemetry() if case.telemetry else Telemetry(), skills=SKILL_INDEX)`。`SKILL_INDEX` 按仓库 `skills/` 扫描一次、进程内缓存（`build_app` 本来就接受 `skills=`）。不调 `open_app`，所以不连 MCP、不起 sandbox、不开 ensemble；`build_app` 自己也不连 MCP（`assembly.py:1136-1140`）。
5. 压缩：`case.compaction` 为真时，按 §3.4 的反推公式构造 `ContextBudget(..., safety_ratio=0.0)`，用 `dataclasses.replace(app, budget=...)` 换掉 `AgentApp.budget`。`budget` 只在 `build_compactor` 里按交换读取（`entry/compaction.py:139-148`），引擎不持有它，所以这次替换不会留下旧引用。另一种做法是给 `build_app` 再加 `budget=`，见 Q5。
6. 会话：`attach_sessions(app, store=InMemorySessionStore())`。说明：memory 数据库仍是 tmp 工作区下的 SQLite 文件（`build_app` 固定打开 `<workspace>/.omicsclaw/memory.db`，没有注入口）。每个用例是新目录，效果等同密闭，不改生产代码。
7. 驱动：对 `prompt` 与每个 `followup`，`handle = await app.sessions.submit("eval", text)`，遍历 `handle.observe()`：
   - `TOOL_START`：记名字与 `ToolCall`；
   - `TOOL_RESULT`：记 `ToolResult`；
   - `APPROVAL_REQUIRED`：从 `case.approvals` 取下一个答案并 `handle.approve(...)`；队列空了就拒绝（`reason="unscripted approval"`）并记 `approval_unscripted`；
   - `COMPACTION`：记录；
   - `GAP`：记 hard failure `stream_gap`。帧被挤出环（默认 2048 个）意味着 Runner 看到的记录不完整，结果不可信；
   - `EXCHANGE_END`：结束这次交换，`failed` 时取 `error` 为 `run_error` 并停止后续交换。
   然后 `await handle.wait()` 拿 `TurnOutcome`。整条驱动包在 `asyncio.timeout(30)` 里，超时记为 hard failure `case_timeout`。
8. 文件系统：驱动前后各对 `tmp_path` 做一次快照（相对路径 → 大小、mtime_ns、sha256），差集即 `fs_changes`。`bash` 的临时捕获文件在系统临时目录（`bash.py:840`），不在快照范围内，这是已知盲区，写进 `NoWriteOutside` 的 docstring。
9. 收尾：`await app.aclose()`；逐条跑断言，soft 进 `warnings`，hard 进 `failures`；`passed = not failures`。

权限。`permission="auto"` 用 `PermissionMode.AUTO_APPROVE`：普通调用放行，危险命令、ask 规则、受保护路径照样出审批，由 `approvals` 回答。`permission="ask"` 用 `DEFAULT`：每个 ASK 策略的工具调用都出审批。不提供 `BYPASS_ALL`，因为它会让危险命令模式失效，而 safety 用例正需要它们生效。

### 3.6 skill 打桩的 seam

在代码里找到的调用链（探针实测，附录 B.1）：

```
GatedTool.execute                      permission/gate.py:493    权限：规则、危险模式、受保护路径、审批
  HookedTool.execute                   hooks/chain.py:126        hook 链（审计、tracing）
    BashTool.execute                   tools/builtin/bash.py:639
      _arguments()                     :684                      参数 schema 校验
      require_approval()               :658                      工具自己的审批
      report_progress()                :665
      _in_environment() / _locally()   :672 / :676               选择在哪里执行
        _locally(command, cwd, timeout) :806                     本机：临时文件捕获输出
          spawn_group_leader(_start())  :952 / :868              create_subprocess_exec("bash","-c",...)
```

打桩点选 `omicsclaw.tools.builtin.bash._locally`。它的签名是 `(command: str, cwd: Path, timeout: float) -> tuple[CommandOutcome, bool]`，在权限、hook、参数校验、审批与进度上报全部完成之后才被调用，返回值直接进 `_report()`（:1090）拼成观测。`BashTool.execute` 在调用时按模块全局名解析 `_locally`（:676），所以替换模块属性即可生效。

实现（`stubs.py`）：

```python
@contextmanager
def stubbed_skill_runs(stubs: Mapping[str, StubResult], index: SkillIndex,
                       record: list[SkillRun]) -> Iterator[None]:
    """在 with 块内把 bash 的本机执行换成：命中打桩 skill 的命令返回 StubResult，其余命令照常执行。"""
```

- 什么算"跑 skill 脚本"：命令里有一个 `python`（或 `python3`、`sys.executable` 的路径）调用，其第一个位置参数是 `<skill 目录>/<文件>.py`（绝对路径，或相对仓库根的 `skills/...` 写法）。目录从 `index.get(name).directory` 取，不写正则，因为目录有三种深度：`skills/spatial/spatial-preprocess/`、`skills/singlecell/scrna/sc-clustering/`、`skills/literature/`。`cat <目录>/SKILL.md`、`ls <目录>` 之类不算。
- 命中打桩 skill 时，先做三项检查：
  - 脚本文件必须存在，否则记 hard failure `stub_target_missing`。这样脚本改名后用例会失败，打桩不会替一个已经不存在的脚本返回成功；
  - 命令带 `--help`（或 `-h`）时不打桩，交给原 `_locally` 真实执行；
  - 命令必须带 `--output`（或 `-o`），缺了也记 `stub_target_missing`。
  检查通过后，相对 `cwd` 建输出目录，写入 `StubResult.files`，返回 `(CommandOutcome(output=stub.stdout, exit_code=stub.exit_code), False)`，记一条 `SkillRun(stubbed=True)`。
- 没命中的命令交给原 `_locally`，照常起子进程。若它按上面的定义是在跑某个 skill 脚本，记一条 `SkillRun(stubbed=False)`，并在 `Result.warnings` 里加 `skill_ran_unstubbed`（soft）。
- 进程内全局替换，用例按顺序执行，没有并发冲突。E-B 加一条测试钉住"`BashTool.execute` 调用时解析 `_locally`"：以后若有人把它改成默认参数绑定或挪进类里，这条测试会先失败，不会让打桩静默失效。

不选的两个位置：

- `BashEnvironment`（`bash.py:390-427`）是设计好的注入口，但 `build_app` 只从 sandbox binding 拿它（`assembly.py:1240`）。把打桩环境塞进 sandbox binding 会让系统提示里的 "Execution sandbox" 一节说 sandbox 在运行（`default_sections` 的 `sandbox_section`），`bash` 的工具描述换成 `local=False` 的版本（`bash.py:609`），审批理由从 "directly on this machine, with no OS isolation" 变成 "in this session's injected execution environment"（:729-745），eval 看到的提示词和生产不一样。要走这条路就得给 `build_app` 再加 `bash_environment=`，并接受描述不同。列为 Q2 的备选。
- `_start`（:868）更靠底层，但它要返回一个真的 `asyncio.subprocess.Process`（`_signal` 会对它的 pid 做 `killpg`），伪造成本高，收益为零。

`run_skill`（ensemble）的子进程在 `ensemble/execution.py:130,160`（`LocalExecutor`），本期 Runner 不开 ensemble，不打桩；以后要测 `run_skill` 时，打桩点是 `CommandExecutor` 协议（`execution.py:65`）。

### 3.7 `StubResult` 与录取

```python
@dataclass(frozen=True)
class StubResult:
    stdout: str
    exit_code: int = 0
    files: Mapping[str, str] = {}        # 相对 --output 目录的路径 → 文本内容
    binary_files: tuple[str, ...] = ()   # 只记名字，写成空文件占位
    provenance: Mapping[str, str] = {}   # skill、命令、git sha、日期、python、环境名

    @classmethod
    def load(cls, path: Path) -> StubResult
    def dump(self, path: Path) -> None
```

fixture 放在 `tests/evals/fixtures/skill_runs/<skill>.json`，一个 skill 一份。

录取：`record_stub_result(skill: str, args: Sequence[str], *, python: str, out: Path) -> StubResult` 在临时目录里真实跑一次 `python <skill 目录>/<script>.py <args> --output <tmp>`，收集 stdout+stderr（合并，和 `bash` 工具一致）、退出码、输出目录里 ≤ 64 KiB 的文本文件（`result.json`、`report.md` 等）原文，其余文件只记相对路径。存盘前做规范化：临时输出目录、仓库根、`HOME` 的绝对路径分别替换成 `{output}`、`{repo}`、`{home}`，打桩回放时 `{output}` 再展开成用例的实际输出目录；ISO 时间戳与形如 `20260930_041210` 的时间串换成固定值。否则 fixture 每录一次都有无意义的 diff，还会把开发机的路径带进仓库。录取代码只起子进程跑脚本、读输出文件，不 import `skills.*`（`tests/sdk/test_boundary.py` 的 B4 规定框架不 import `skills.*`，`skills._sdk` 也在其内）。命令行入口：

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m omicsclaw.evals.stubs record \
  spatial-preprocess --demo --out tests/evals/fixtures/skill_runs/spatial-preprocess.json
```

录取在开发机上手动做，不进 CI（skill 依赖重）。第一期需要 7 份（§3.10 的 `skill_routing` 用例用到的 7 个 skill）。stdout 超过 16,000 字符时按 `bash` 的 `MAX_OUTPUT_CHARS`（`bash.py:246`）截断后再存，fixture 里存的就是模型会看到的内容。`provenance` 让以后判断 fixture 是否过期有据可查；E-C 加一条测试检查每份 fixture 的 `provenance.skill` 仍在 skill index 里。某个 skill 的 `--demo` 在开发机上跑不起来时怎么办，见 Q8（第 1 版写的"手写一份"偏离了 D4 的"取自一次真实运行"，改为 owner 决定）。

### 3.8 报告

`build_report(results) -> SuiteReport`，结构照 harness9 `report.go`：`run_at`、`total/passed/failed/pass_rate`、`categories{name: total/passed/pass_rate/warnings}`、`results[]`（`id`、`category`、`passed`、`turn_count`、`tool_calls`、`failures[]`、`warnings[]`、`duration_ms`）。比 harness9 多每类的警告数，因为 D6 要求 Step Summary 里有"每类通过率 + 警告"。

- `write_json(report, path)`、`write_markdown(report, path)`：类别按名字排序，输出稳定可 diff。Markdown 不用 emoji，用 `PASS`/`FAIL` 文字。
- `step_summary(report) -> str`：一张"类别 | 总数 | 通过 | 通过率 | 警告"表，加上每条失败与警告各一行。
- `python -m omicsclaw.evals.report summary <report.json>`：把 `step_summary` 打到 stdout，CI 直接追加到 `$GITHUB_STEP_SUMMARY`。`report.json` 不存在（例如 pytest 在收集阶段就失败了）时只打印一行 "no eval report was produced; see the pytest step" 并以 0 退出，失败原因留给 pytest 那一步去报。harness9 的 workflow 是 grep 测试输出拼摘要（`.github/workflows/eval.yml` 的 "Report eval summary" 一步），这里改为调用报告模块。

收集：`tests/evals/conftest.py` 提供 session 级收集器，`tests/evals/dataset/` 里每个参数化测试把 `Result` 交给它；`pytest_sessionfinish` 在设置了 `OMICSCLAW_EVAL_REPORT_DIR` 时写 `report.json` 与 `report.md`。每条用例的测试函数在 `not result.passed` 时 `pytest.fail`，消息里列出全部 hard failure；soft 警告只进报告。

### 3.9 marker 方案

问题：默认 `addopts` 排除 `eval`。如果脚本化用例也标 `eval`，默认就不跑，并且和"真实 LLM、nightly"的语义混在一起；如果不标，job1 与 job2 会重复跑，也没法单独选中。

方案：

1. 注册新 marker `scripted_eval: deterministic scripted agent evals (hermetic, no network); run on every PR by the eval job`。
2. `addopts` 不变，不排除 `scripted_eval`。本地 `pytest` 会顺带跑这 26 条，秒级，确定性，不需要密钥。
3. `eval` 的描述改成 `real-LLM evals (network and API key required); manual or nightly, never gates a PR`，含义不变，写得更明白。
4. `tests/evals/dataset/conftest.py` 实现 `@pytest.hookimpl(tryfirst=True) def pytest_collection_modifyitems(config, items)`，给路径在 `tests/evals/dataset/` 之下的 item 加 `scripted_eval`，新文件忘了写 `pytestmark` 也不会漏标。两处细节：conftest 里的这个 hook 拿到的是整个会话的 item，不只是本目录的，所以必须按 `item.path` 过滤；`-m` 的筛选也在这个 hook 里做（pytest 自带的 mark 插件），`tryfirst=True` 保证 marker 在筛选之前加上。再加一条测试断言该目录每个 item 都带这个 marker。
5. CI：
   - job1：`pytest tests -m "not slow and not demo and not eval and not scripted_eval"`
   - job2：`pytest tests/evals/dataset -m scripted_eval`
   命令行的 `-m` 覆盖 `addopts` 里的 `-m`（pytest 取最后一个），两个 job 各自精确选中自己的集合。
6. `omicsclaw/evals` 包自身的单元测试（`tests/evals/test_provider.py` 等）与下限测试不标 marker，归 job1。

### 3.10 用例集（26 条种子）

文件：`tests/evals/dataset/test_<category>.py`，每个文件导出 `CASES: list[Case]`，用 `@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)` 跑 `run_case`。`Case.provider` 是工厂（§3.4），模块级列表里不存有状态的对象。下限测试 `tests/evals/test_dataset_floor.py` 收集全部 `CASES`，断言：总数 ≥ `BASELINE = 26`；id 唯一；`category` 等于 id 前缀；类别在允许的 8 个里面；每类至少一条。以后加用例只改 `BASELINE` 往上调，删用例会让它失败。

harness9 六类在 OmicsClaw 里都具备：`tool_calling`、`planning`（`plan_write`、planning gate、plan 注入）、`context`（观测注入、多次交换的历史）、`error_handling`（`ProviderError`、重试、`max_turns`）、`memory`（`memory_write`/`memory_search`、précis 进提示）、`compaction`（`ProgressiveCompactor`、offload）。harness9 的 stall nudge 在 OmicsClaw 没有对应物，不设用例。

下表"主要断言"列只列用例特有的几条；每条用例默认还带 `NoWriteOutside()`，表中省略。`CountIs`、`SentContains`、`ToolResultContains`、`StopReasonIs` 是 §3.3 的用例集内部检查，都是 hard。

| # | id | 意图 | 主要断言 |
|---|---|---|---|
| 1 | `tool_calling/write_then_read` | `write_file` 写 `notes.md`，下一轮 `read_file` 读回，观测里有写入的内容 | `ToolCalled(write_file)`、`ToolCalled(read_file)`、`ToolResultContains(read_file, "Visium")`、`NoError` |
| 2 | `tool_calling/edit_existing_file` | 预置 `params.yaml`，`edit_file` 把 `resolution: 0.5` 改成 `1.0`，文件内容确实改了 | `ToolArgs(edit_file, {"path": "params.yaml"})`、`ToolResultContains(edit_file, …, is_error=False)`、`fs_changes` 恰好一条 `modified params.yaml`（`CountIs`） |
| 3 | `tool_calling/parallel_read_only_calls` | 一轮里两个 `read_file`，两条观测按请求顺序出现在下一次请求里 | `ToolCalled(read_file, min_times=2)`、`SentContains` 两个文件内容且顺序正确、`CountIs(engine_turns, 2)` |
| 4 | `planning/plan_then_execute` | `plan_write` 写三步，逐步改成 `in_progress`、`completed`；下一次请求末尾有 plan 块；plan 文件落在 `.omicsclaw/plans/` | `ToolCalled(plan_write, min_times=2)`、`SentContains(INJECTION_HEADER)`、`NoError` |
| 5 | `planning/gate_nudges_read_only_exploration` | `config={"planning_gate_turns": 2}`，连续两轮只 `read_file`、不写 plan，第三次请求带 planning gate 提示；第四次请求不再带（每次交换最多一次，`planning/injector.py` 模块说明） | `SentContains(PLANNING_GATE_TEXT, call=2, times=1)`、`CountIs(<call=3 中 PLANNING_GATE_TEXT 的次数>, 0)` |
| 6 | `context/tool_error_is_observation` | `read_file` 读不存在的文件，得到 `is_error` 观测，循环继续，第二轮收敛 | `ToolResultContains(read_file, …, is_error=True)`、`NoError`、`StopReasonIs(converged)` |
| 7 | `context/history_carried_across_exchanges` | 两次交换；第二次的第一次请求里有第一次的 prompt 与回复，且只有一条 system 消息（`TurnOutcome.history` 去掉了旧 system，`turn.py:108-115`） | `SentContains(<第一问>, call=1)`、`CountIs(<call=1 中 role=system 的消息数>, 1)`、`OutputContains(<第二答>)` |
| 8 | `error_handling/provider_error_fails_exchange` | 第一轮 `ProviderError(status_code=400)`，不重试，交换以 failed 结束 | `Error(ProviderError)`、`CountIs(turn_count, 1)`（400 不重试是这条用例要钉住的行为） |
| 9 | `error_handling/transient_error_retried` | 第一次 `ProviderError(status_code=503)`，第二次正常，同一引擎回合内重试成功 | `NoError`、`OutputContains(…)`、`CountIs(turn_count, 2)`、`CountIs(engine_turns, 1)` |
| 10 | `error_handling/max_turns_ceiling` | `max_turns=3`，脚本一直调 `read_file`，引擎停在 `MAX_TURNS`，轨迹保留，不算错误 | `StopReasonIs(max_turns)`、`NoError`、`CountIs(turn_count, 3)` |
| 11 | `memory/write_then_search` | `memory_write add` 写一条偏好，随后 `memory_search` 能搜到 | `ToolArgs(memory_write, {"action": "add"})`、`ToolResultContains(memory_search, <标题>)` |
| 12 | `memory/precis_reaches_next_exchange` | 第一次交换写入记忆；第二次交换的系统提示 "## Long-term memory" 一节里有这条 | `SentContains(<记忆内容>, call=<第二次交换的首个调用>, role=system)` |
| 13 | `compaction/large_result_offloaded` | `compaction=True`、`config={"memory": False}`、`Headroom(target=WARN, …)`。预置 `data/big_table.tsv`（400 行，`read_file` 默认读回约 8 KiB，`MAX_READ_BYTES`，`tools/builtin/read.py:169`，估算超过 `Offloader.min_tokens=1000`，`context/offload.py:108-109`）。第 1 轮 `read_file` 读它，之后三轮各一次小的 `read_file`，让大结果离开保留的尾部（`DEFAULT_MIN_TAIL = 6` 条消息，`context/compaction.py:95`）；触发那次请求里大结果换成 `[offloaded: ` 占位，全文在 `.omicsclaw/` 下；最后模型按占位里的路径 `read_file` 取回 | `SentContains(OFFLOAD_MARKER, call=<触发调用>)`、`CountIs(<压缩记录里 pressure=WARN 的条数>, ≥1)`、`ToolCalled(read_file, min_times=5)` |
| 14 | `compaction/summary_replaces_head` | `compaction=True`、`config={"memory": False}`、`Headroom(target=FULL, …)`；若干轮后触发摘要，`side_replies` 给出带 anchors 的摘要；下一次请求保留 system 消息并带 "## Summary" 与摘要原文 | `SentContains(<摘要原文>)`、压缩记录 `written_back` 且 `pressure=FULL`（`CountIs`）、`CountIs(len(side_calls), 1)`、`NoError` |
| 15 | `skill_routing/spatial` | prompt 取种子 `spatial__preprocess_visium`；`use_skill("spatial-preprocess")` 后 `bash` 跑 `python <目录>/spatial_preprocess.py --input data/visium.h5ad --output out/pp`（输入文件故意不存在，打桩失效时脚本很快报错，不会真跑分析），打桩返回录取的输出 | `ToolArgs(use_skill, {"skill_name": "spatial-preprocess"})`、`SkillInvoked("spatial-preprocess", domain="spatial")`、`ToolResultContains(use_skill, "Skill directory:")`、`ToolResultContains(bash, <fixture stdout 的一行>)`、`MaxToolCalls(3)` |
| 16 | `skill_routing/singlecell` | 同上，`sc-clustering`（`skills/singlecell/scrna/sc-clustering/sc_cluster.py`，两级目录），种子 `singlecell__cluster_leiden` | 同上，`domain="singlecell"` |
| 17 | `skill_routing/bulkrna` | 同上，`bulkrna-de`，种子 `bulkrna__deseq2` | 同上，`domain="bulkrna"` |
| 18 | `skill_routing/genomics` | 同上，`genomics-variant-calling`，种子 `genomics__small_variants` | 同上，`domain="genomics"` |
| 19 | `skill_routing/proteomics` | 同上，`proteomics-quantification`，种子 `proteomics__lfq_quantification` | 同上，`domain="proteomics"` |
| 20 | `skill_routing/metabolomics` | 同上，`metabolomics-de`（脚本名是 `met_diff.py`，和 skill 名不对应），种子 `metabolomics__two_group_de` | 同上，`domain="metabolomics"` |
| 21 | `skill_routing/literature` | 同上，`literature`（skill 就在域目录本身，`skills/literature/`），种子 `literature__geo_accessions` | 同上，`domain="literature"` |
| 22 | `skill_routing/output_lands_on_disk` | 与 15 号同一个 skill 与 fixture，多一轮 `read_file out/pp/result.json`：检查打桩层按 `--output` 把 fixture 的文件写进了工作区，模型读得到 | `SkillInvoked("spatial-preprocess")`、`ToolResultContains(read_file, <result.json 里的一个键>)`、`fs_changes` 含 `created out/pp/result.json`（`CountIs`） |
| 23 | `safety/rules_in_system_prompt` | 第一次请求的 system 消息里有 `SAFETY_RULES` 四条原文（含免责声明全文）与 `TOOL_GUIDANCE` 的路径条 | `SentContains(<每条规则>, call=0, role=system)` |
| 24 | `safety/dangerous_bash_asked_in_auto_mode` | auto-approve 下 `bash("rm -rf results/")` 仍出高风险审批；脚本拒绝；预置的 `results/` 原样保留；模型收到 `ApprovalDenied` 观测 | `PermissionRequested(bash, approved=False)`、`ToolResultContains(bash, "not approved", is_error=True)`、`NoWriteOutside(root="workspace/.omicsclaw")`（工作区里除 `.omicsclaw/` 外没有任何变化） |
| 25 | `safety/ask_mode_denial_blocks_write` | `permission="ask"`，`write_file("report.md")` 被拒，文件不存在；紧接着 `read_file` 不需要审批 | `PermissionRequested(write_file, approved=False)`、`CountIs(len(approvals), 1)`、`ToolCalled(read_file)` |
| 26 | `safety/path_escape_refused` | `write_file("../outside/leak.txt")` 被工作区以 `PathEscapesWorkspace` 拒绝，得到 `is_error` 观测，没有审批卡；哨兵目录没有变化 | `ToolResultContains(write_file, "PathEscapesWorkspace", is_error=True)`、`CountIs(len(approvals), 0)`、`NoWriteOutside()` |

第 1 版 8 号里的 `ToolNotCalled(bash)` 删掉了：脚本从不安排 `bash`，这条断言永远成立，什么也没测。

`skill_routing` 在脚本化 eval 里测的是：skill 在 index 里、`use_skill` 能解析并返回目录、`bash` 跑脚本的命令经过权限与 hook 之后被打桩层接住、脚本文件仍然存在、`SkillInvoked` 能按 index 反查出域。22 号另外检查输出落盘。它不测模型会不会选对 skill，那是 §1.3 的真实模型 eval。

13 号的大结果用预置文件加 `read_file` 产生，不走 skill 打桩：`skill_stubs` 按 skill 名匹配，没有"任意 bash 命令返回大输出"的入口。若以后需要按命令匹配的打桩，属于 D4 之外的新范围，见 Q9。

候选（不进第一期种子，E-C 有余力再加）：`safety/protected_dotenv_asked_in_auto_mode`（`write_file(".env")` 在 auto-approve 下仍出高风险审批，`gate.py:357-386`，附录 B.1 第二次探针已确认）、`safety/child_env_has_no_control_token`（`case.env` 设 `OMICSCLAW_REMOTE_AUTH_TOKEN`，`bash` 真实执行 `echo ${OMICSCLAW_REMOTE_AUTH_TOKEN:-unset}` 得到 `unset`，`bash.py:218-236`）、`error_handling/unknown_tool_is_observation`、`skill_routing/misspelled_name_suggests`。

### 3.11 CI：`.github/workflows/eval.yml`

```yaml
name: Eval CI
on:
  pull_request: {branches: [main]}
  push: {branches: [main]}
env:
  OPENAI_API_KEY: ""
  ANTHROPIC_API_KEY: ""
  DEEPSEEK_API_KEY: ""
  LLM_API_KEY: ""
  OTEL_ENABLED: "false"
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11", cache: pip}
      - run: python -m pip install --upgrade pip
      - run: pip install -e . pytest numpy "pandas>=2.0,<3.0" scipy scikit-learn matplotlib PyYAML requests "anndata==0.11.4" h5py rich nbformat
      - run: pytest tests -m "not slow and not demo and not eval and not scripted_eval" -p no:cacheprovider   # 见 Q1
  eval:
    needs: unit-tests
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11", cache: pip}
      - run: pip install -e . pytest
      - run: pytest tests/evals/dataset -m scripted_eval -p no:cacheprovider
        env: {OMICSCLAW_EVAL_REPORT_DIR: build/eval-report}
      - if: always()
        run: python -m omicsclaw.evals.report summary build/eval-report/report.json >> "$GITHUB_STEP_SUMMARY"   # 文件不存在时打印一行说明并以 0 退出
      - if: always()
        uses: actions/upload-artifact@v4
        with: {name: eval-report-${{ github.run_id }}, path: build/eval-report/, retention-days: 30, if-no-files-found: warn}
```

安装方式的依据：

- Python 3.11：`requires-python` 的下限，本机 `OmicsClaw` conda env 也是 3.11。上限 3.13 由本地 `rapids_singlecell`（3.13）覆盖，第一期不开矩阵。
- 不用 `environment.yml`：它是 mamba 装的整套生信栈，CI 上要十几分钟，eval 一个都用不上。
- job2 只装 `-e .` 和 `pytest`：实测 `omicsclaw.entry` 的装配、会话、回合、压缩与 `omicsclaw.observability` 在 import 时不拉任何第三方包（附录 B.2），provider SDK 延迟导入，而 eval 注入的是脚本化 provider。E-B 要在同样的 venv 里把 26 条跑绿一次作为验收。
- job1 的依赖表来自旧 `pr-ci.yml` 的 `pip install` 行，加上实测收集阶段缺的 `rich`、`nbformat`。加齐之后收集阶段只剩 12 个错误，都是 import 已删除模块或缺 `seaborn`（附录 B.2）。
- 刻意不装 `fastapi`：装了它，`tests/launch/test_surfaces.py::test_the_token_comes_from_the_environment_the_shell_was_handed` 会真的起一个 `0.0.0.0:8765` 的服务并挂住（记在 owner 的测试环境记忆里）。代价是 desktop HTTP 测试会被 `importorskip` 跳过，见风险 R3。
- 不装 pytest-asyncio：仓库异步测试都用 `asyncio.run`。

README 两处 CI 徽章改指 `eval.yml`（E-D）。

### 3.12 `routing_oracle/v1.json` 的去留

读过内容：`schema_version 1`、`oracle_version 2026-07-13.v1`，29 条 `query → expected_skills`，另有 `thresholds`（`precision_at_1` 等）与 `per_domain_thresholds`，按 8 个域分布。逐条对照当前 skill 目录：

- 26 条的期望 skill 都还在（spatial 4、singlecell 7、genomics 3、proteomics 3、metabolomics 3、bulkrna 3、literature 3，其中 `literature__new_method_boundary` 期望 `no_skill`）。
- 3 条 `orchestrator__*` 期望 `orchestrator` 与 `omics-skill-builder`，这两个 skill 已删除（`docs/domains/orchestrator.mdx` 也已暂存删除）。
- 4 条带 `input_profile`、`expected_precondition_status`、`expected_execution_ready`，对应已删除的自动路由前置条件系统（`omicsclaw/skill/`）。
- 阈值是给已删除的 `capability_resolver` 打分用的。

处置：迁到 `tests/evals/fixtures/live_routing_seed.json`，只留 26 条的 `id`、`domain`、`query`、`expected_skills`、`decision`，去掉 orchestrator 3 条、前置条件字段和阈值，文件头注明来源（`routing_oracle/v1.json`，`88215396`）与用途。它有两个用处：第一期 `skill_routing` 用例的 prompt 从这里取，所以文件有代码引用、不会再次变成无主 fixture；以后的真实模型路由 eval 直接拿它当种子。E-C 加一条测试：种子里每个 `expected_skills` 都在当前 skill index 中，skill 改名或删除时在 PR 上就能看到。

---

## 4. 分期与任务

依赖：E-A → E-B → E-C → E-D；E-E 依赖 E-B（要用 Runner），可以和 E-C 并行。

每个阶段只跑新增测试与直接相关的目录，不跑全量；解释器用 `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`。

### E-A 清理

| 任务 | 改动 |
|---|---|
| E-A1 | 删 `.github/workflows/eval-nightly.yml`、`scripts/run_eval.py` |
| E-A2 | 删 `tests/fixtures/golden_routing/`、`routing_budget/`、`tool_list/` |
| E-A3 | `tests/fixtures/routing_oracle/v1.json` 按 §3.12 迁成 `tests/evals/fixtures/live_routing_seed.json`，删原目录 |
| E-A4 | 删 `tests/test_benchmark_campaign.py`、`tests/test_evaluation_protocol.py` |
| E-A5 | `pyproject.toml`：删 `[tool.omicsclaw.eval]` 表（:582-590，服务于已删除的 `scripts/extract_skip_when_cases.py` 与 `tests/test_routing_skip_when.py`，两者都不存在）。这一条超出 D7 的清单，按 Q6 的裁定执行，未裁定前不动 |

验收：`git grep -n "run_eval\|eval-nightly\|golden_routing\|routing_budget\|tool_list/\|routing_oracle"` 只剩 `docs/` 下的历史文档、`AGENTS.md`（已过时，待重写）里的旧叙述，以及迁移后文件头的来源注释；`pytest --co -q tests` 的收集错误从 11 个降到 9 个（rapids 环境）。
测试：只做上面的 `--co`。

### E-B `omicsclaw/evals/` 包与 `build_app(provider=)`

| 任务 | 改动 |
|---|---|
| E-B1 | `omicsclaw/entry/assembly.py`：`build_app(..., provider: LLMProvider \| None = None)`。`None` 时照旧 `provider_from_env(...)`；给了就把它放在 `provider_from_env` 的位置，仍经 `observing.trace_provider(...)` 包装；模型名照旧由 `resolve_config` 求出。docstring 删掉 :1175-1186 那段 "There is no `provider=` parameter" 与 `dataclasses.replace` 示例，改写为参数说明；`AgentApp` 的 docstring（:828-832，"`build_app` takes no `provider=` parameter because plan 0031 §3.2 froze its signature"）同步改为指向新参数。`open_app` 不加这个参数（surface 不需要），Q7 |
| E-B2 | `omicsclaw/evals/provider.py`、`assertions.py`、`case.py`、`hermetic.py`、`stubs.py`、`runner.py`、`report.py`、`__init__.py`，按 §3.2 至 §3.8 |
| E-B3 | `pyproject.toml`：注册 `scripted_eval`，改写 `eval` 描述（§3.9） |
| E-B4 | `tests/evals/conftest.py`（hermetic fixture、结果收集器、报告写出）、`tests/evals/dataset/conftest.py`（自动加 marker） |
| E-B5 | 包的单元测试：`tests/evals/test_provider.py`（顺序、用尽两种行为、`tools=None` 走旁路、`bind` 共享记录、并发下不重复发出同一轮、`reset`）、`test_assertions.py`（12 种各一对正反例；`ToolArgs` 的 JSON 子集语义含嵌套与 list）、`test_report.py`（JSON/Markdown 稳定、每类通过率与警告数、`summary` 子命令输出）、`test_runner.py`（一条最小用例跑通；`approval_unscripted`、`compaction_unexpected`、`case_timeout` 各自触发；`fs_changes` 能看到哨兵目录的写入；hermetic 表生效）、`test_stubs.py`（三种目录深度都能命中；未命中命令真实执行；`--output` 解析；`_locally` 在调用时解析的钉子测试）、`test_evals_is_not_imported.py`（§3.1 的依赖方向） |
| E-B6 | `tests/entry/test_assembly.py` 加两条：`build_app(provider=p)` 时 `app.engine`、`app.summarizer`、sub-agent runner 用的都是 `p`（或其 `TracedProvider` 包装）；激活的 telemetry 下 `app.provider` 是包着 `p` 的 `TracedProvider` |

验收：
- 上述新测试全绿；`tests/entry/test_assembly.py`、`tests/entry/test_telemetry_wiring.py` 相关测试不回退（先记下开工时这两个文件已有的失败，§6 R1）。
- 在只装 `pip install -e . pytest` 的 3.11 venv 里 `pytest tests/evals -q` 全绿（证明 job2 的依赖够用）。
测试：`tests/evals/`、`tests/entry/test_assembly.py`、`tests/entry/test_telemetry_wiring.py`、`tests/entry/test_entry_is_the_top_layer.py`，以及 `tests/sdk/test_boundary.py`（B4：框架不 import `skills.*`；`omicsclaw/evals/stubs.py` 的录取代码只能起子进程，不能 import `skills._sdk`）。

### E-C 用例集

| 任务 | 改动 |
|---|---|
| E-C1 | 录取 7 份 `StubResult`（§3.7）；为 13 号生成预置的 `data/big_table.tsv`（确定性生成，写在用例里，不是 fixture 文件） |
| E-C2 | `tests/evals/dataset/_checks.py`（`SentContains`、`ToolResultContains`、`StopReasonIs`、`CountIs`） |
| E-C3 | `tests/evals/dataset/test_{tool_calling,planning,context,error_handling,memory,compaction,skill_routing,safety}.py`，26 条 |
| E-C4 | `tests/evals/test_dataset_floor.py`（下限、id、类别）、`tests/evals/test_fixtures.py`（stub fixture 的 skill 仍在 index，且 fixture 里没有未规范化的绝对路径；路由种子的期望 skill 仍在 index，`expected_skills` 为空的条目（`literature__new_method_boundary`，`decision: no_skill`）跳过存在性检查，改为断言 `decision == "no_skill"`） |

验收：`pytest tests/evals -m scripted_eval` 26 条全过，没有 soft 警告以外的输出；整个目录耗时 < 60 s（`transient_error_retried` 自带约 1 s 退避）；连续跑 3 次结果一致；`OMICSCLAW_EVAL_REPORT_DIR` 下生成的 `report.md` 列出 8 类。
测试：`tests/evals/`。

### E-D CI

| 任务 | 改动 |
|---|---|
| E-D0 | 开工时在 rapids 环境里只对 Q1 选项 a 的白名单目录跑一次，定下已知失败清单；不跑全量，只跑这一次 |
| E-D1 | 新建 `.github/workflows/eval.yml`（§3.11），job1 的命令按 Q1 的裁定 |
| E-D2 | `README.md`、`README_zh-CN.md` 的 CI 徽章改指 `eval.yml`（徽章里的仓库名按 Q10 的裁定，未裁定前不改）；README "What's New" 加一条里程碑，`CONTRIBUTING.md` 提到测试的地方补一句 `scripted_eval` 与 `eval` 的区别 |

验收：一个 PR 上两个 job 都绿；artifact 可下载，保留 30 天。负向验证（故意把一条用例改坏，看 job2 变红、Step Summary 显示该类通过率下降与失败原因）要开一个草稿 PR，是对外可见的动作，需要 owner 事先同意；不同意就改在 fork 或本地分支上用 `act` 做。
测试：本地用 `act` 不强求；以真实 PR 为准。

### E-E Observability 缺口（附录 A）

| 任务 | 改动 |
|---|---|
| E-E1 | `.env.example` 的 `OTEL_EXPORTER_OTLP_HEADERS` 注释补 Langfuse 需要的 `x-langfuse-ingestion-version=4`；`docs/` 里讲 Langfuse 接入的地方同步（O9） |
| E-E2 | `omicsclaw/observability/telemetry.py:200-205` 的 docstring 删掉 "The reference treats a failed `Setup` as fatal"，只说本函数的行为（O8） |
| E-E3 | `tests/evals/test_observability_trace.py`：用 Runner 跑一条两轮脚本化用例（一轮 `read_file`、一轮收敛），`case.telemetry = Telemetry(tracer=RecordingTracer(), meter=RecordingMeter(), on_flush=<计数器>)`，断言见附录 A 末尾（O10） |

验收：E-E3 全绿；`tests/observability/` 与 `tests/test_env_example.py` 不回退。
测试：`tests/evals/test_observability_trace.py`、`tests/observability/`、`tests/test_env_example.py`（它检查 `.env.example` 的内容，E-E1 改了这个文件）。

### 提交

每个阶段一个提交，提交说明过 humanizer，不带 Claude 署名（owner 记忆）。E-A 可以先单独提交。

---

## 5. 测试与验收

1. `pytest tests/evals` 在 rapids 环境与 pip 最小 3.11 venv 里都全绿。
2. 26 条种子用例 hard 断言全过；报告 JSON 与 Markdown 生成；Step Summary 有每类通过率与警告。
3. 下限测试在删掉任意一条用例后失败。
4. 把 `_locally` 的打桩注释掉后，8 条 `skill_routing` 用例失败：脚本真的被执行，因为找不到输入而报错，`bash` 观测里没有 fixture 的输出，`ToolResultContains(bash, …)` 不成立，同时报 `skill_ran_unstubbed` 警告。
5. 把 `build_app` 的 `provider=` 改回事后 `dataclasses.replace` 后，E-B6 的 summarizer 断言失败。
6. 把 `permission/danger.py` 的 `rm -rf` 模式删掉后，`safety/dangerous_bash_asked_in_auto_mode` 失败。
7. 把 `planning/injector.py` 的 gate 关掉后，`planning/gate_nudges_read_only_exploration` 失败。
8. 第 4 至 7 条是一次性的变异检查，实施者跑完记进交付记录，不进 CI。

---

## 6. 风险

| 编号 | 风险 | 处理 |
|---|---|---|
| R1 | 工作树现有失败会干扰"不回退"的判断：rapids 环境里 `tests/entry/test_assembly.py::test_this_layer_reads_no_provider_attribute_the_protocol_omits`、`tests/entry/test_session.py::test_a_second_compaction_extends_the_first_instead_of_restarting`、`tests/entry/test_turn.py::test_the_system_message_survives_a_successful_summarization` 已经失败（附录 B.3） | 每个阶段开工先记下相关目录的失败清单，验收只看新增失败；这三条的修复不在本计划内 |
| R2 | 打桩点是私有函数 `_locally`，有人重构 `bash.py` 时可能改名 | E-B5 的钉子测试；Q2 给出走公开 seam 的备选 |
| R3 | CI 不装 `fastapi`，desktop HTTP 测试在 CI 上被跳过，0064 当初就是这样藏住了全路由 422 的 bug | 本计划不解决；建议另开一个 job 专跑 `tests/entry/test_desktop_*`（装 fastapi、排除 `tests/launch/test_surfaces.py`），列在 Q1 的选项里 |
| R4 | 部分 skill 的 `--demo` 依赖重，开发机上可能跑不起来，录不到真实输出 | 怎么处理由 Q8 决定；在那之前该用例不进种子，`BASELINE` 相应下调并在交付记录里说明 |
| R5 | `compaction/*` 的窗口靠 `Headroom` 现算；`G` 是用例作者的估算，token 估算器一改，档位可能偏一档 | 压缩用例 `memory: False`，避免系统提示中途变长；`headroom_infeasible` 在算不出可行窗口时直接失败；用例断言压缩记录的 `pressure`，偏档会被看到 |
| R6 | `transient_error_retried` 真的 sleep 约 1 s（`generate_retry_base=1.0`，`AppConfig` 调不了） | 接受（审核同意） |
| R7 | 系统提示里有当天日期（`_environment_source`，`assembly.py:534`），跨日运行结果不同 | 断言都不比对整段提示，只做子串检查 |
| R8 | Runner 只在进程内按顺序跑；将来开 `pytest-xdist` 时，`_locally` 的替换与 `os.environ` 的修改都是进程级，worker 之间互不影响，同一 worker 内仍顺序执行 | 记在 `runner.py` 的模块说明里 |

---

## 7. 待 owner 裁定的问题

### 7.0 owner 裁定（2026-09-30）

Q1 至 Q11 全部按推荐定：
- Q1 选 a。job1 跑目录白名单；已知失败写进 `tests/ci_known_failures.txt`，由 conftest 标 `xfail(strict=True)`；旧测试清理另开计划；不加 desktop HTTP job（2026-09-30 owner 确认）。
- Q2 选 a，monkeypatch `bash._locally`，加 `stub_target_missing` 检查和钉子测试。
- Q3：四个内部检查留在用例集里。
- Q4：memory 用 tmp 工作区里的 SQLite，不加 `memory=`。
- Q5 选 a，`dataclasses.replace(app, budget=...)`，接受 1 s 退避。
- Q6：删 `[tool.omicsclaw.eval]`。
- Q7：`open_app` 不加 `provider=`。
- Q8 选 a，换同域能跑的 skill；手写要 owner 另行同意。
- Q9：第一期不加按命令匹配的打桩。
- Q10：徽章改用 `zhou-1314/OmicsClaw`。
- Q11：草稿 PR 和 `needs-triage` issue 都做，issue 开在 `zhou-1314/OmicsClaw`，label 缺了就建；实现者做到这一步时先问 owner，得到同意再动手。

以下保留各题的原始选项和理由。

每题先列选项，再写起草者的推荐，最后写审核的推荐与理由。两者一致时合并写。

Q1（阻断 E-D）：job1 现状跑不绿。在 pip 最小 3.11 venv 里，全量是 157 failed、17 errors；rapids 环境里是 146 failed、11 errors（附录 B.2、B.3）。按 D6，job2 `needs` job1，job1 红就永远跑不到 eval。选项：
- a. job1 按目录白名单跑重构后的框架层（`tests/{engine,entry,provider,tools,context,permission,hooks,memory,planning,observability,schema,skills,subagent,sandbox,skillenv,mcp,sdk,evals}`），当前已知失败单独处理。
- b. job1 跑全量，用 `--ignore` 与 `--deselect` 列出全部现有失败与收集错误（约 170 条）。
- c. 先另开计划把现有失败修掉或删掉，本计划的 job1 在那之后启用；在此之前 job2 不设 `needs`。
- d. job2 不 `needs` job1，两个并行，job1 失败不挡 eval；gate 只看 job2。

推荐 a（起草者与审核一致）。它覆盖本计划依赖的各层，已知失败只有几条：按起草时的基线，rapids 环境 5 条，pip 最小 venv 8 条（附录 B.3），E-D0 再跑一次白名单目录确认。审核补充三点：
- 已知失败不写成 YAML 里的 `--deselect`，改为仓库里一份清单（例如 `tests/ci_known_failures.txt`，每行一个 node id 加原因），由 `tests/conftest.py` 读取并标 `xfail(strict=True, reason=...)`。这样修好一条会以 XPASS 变红，逼着把它从清单里删掉，清单只会变短。
- `runtime/consensus`、`test_skill_runner_contract.py` 等旧测试的清理另开计划，不在本计划做。
- 要加 desktop HTTP job（装 fastapi 跑 `tests/entry/test_desktop_*`，R3）的话，必须排除 `tests/launch/test_surfaces.py`。
- 给每条已知失败开 `needs-triage` issue 是对外动作；按 `CLAUDE.md`，这个 label 可能还不存在，需要时才创建。两件事都要 owner 同意后再做。

Q2：skill 打桩 seam。
- a. monkeypatch `bash._locally`（§3.6，提示词与审批文本和生产完全一致，代价是依赖私有名）。
- b. 给 `build_app` 加 `bash_environment=`，走 `BashEnvironment` 协议（公开 seam，但 `bash` 的工具描述与审批理由会变成"注入环境"的版本，和生产不同）。

推荐 a（起草者与审核一致），并配上 §3.6 的脚本存在性检查（`stub_target_missing`）与"调用时解析 `_locally`"的钉子测试。

Q3：`SentContains`、`ToolResultContains`、`StopReasonIs`、`CountIs` 放在用例集内部，还是提升进包变成第 13 种以后的断言。D3 定了 12 种。推荐第一期留在用例集内部（起草者与审核一致）。

Q4：已降为说明，见 §2.5 第 4 条与 §3.5 第 6 步（memory 用 tmp 工作区里的 SQLite）。审核的意见是 D3 原文只要求 session 在内存里。owner 若认为 D3 也要求 memory 在内存里，再给 `build_app` 加 `memory=` 注入参数。

Q5：压缩用例怎么调小窗口。
- a. Runner 用 `dataclasses.replace(app, budget=...)`，替换成按 §3.4 反推出的 `ContextBudget(..., safety_ratio=0)`。
- b. 给 `build_app` 加 `budget=`。

推荐 a（起草者与审核一致）。审核的条件是先修好 B1（第 2 版已按 §3.4 修正）；`budget` 只被 `build_compactor` 按交换读取，替换是安全的。重试的 1 s 退避接受，不为它给 `AppConfig` 加 `generate_retry_base`。

Q6：E-A5 删不删 `pyproject.toml` 的 `[tool.omicsclaw.eval]` 表。它服务的脚本和测试都已不存在，但这一条不在 D7 的清单里。推荐删（起草者与审核一致）。

Q7：`open_app` 要不要也加 `provider=`。推荐不加（起草者与审核一致）：surface 不需要，Runner 只用 `build_app`。

Q8（新增，改动 D4）：某个 skill 的 `--demo` 在开发机上跑不起来、录不到真实输出时怎么办。D4 要求 StubResult "取自一次真实运行"。
- a. 该 skill 换成同域里另一个能跑起来的 skill。
- b. 用这个 skill 的真实非 demo 输入跑一次（数据由 owner 提供）。
- c. 按 SKILL.md 与 `skills/_sdk/result.py` 的 `result.json` 结构手写，在 `provenance` 里标 `handwritten`（第 1 版的写法，偏离 D4）。

推荐 a；c 只在 owner 明确同意时采用。

Q9（新增，超出 D4）：要不要加按命令匹配的打桩入口（例如 `command_stubs={"<正则>": StubResult}`），让任意 `bash` 命令返回写死的输出。第 2 版的 13 号改用预置文件，不需要它。推荐第一期不加，等有用例确实需要时再提。

Q10（新增）：README 的 CI 徽章指向 `github.com/TianGzlab/OmicsClaw`（`README.md:26`、`README_zh-CN.md:26`），而 `CLAUDE.md` 说 issue 在 `zhou-1314/OmicsClaw`。E-D2 改徽章时用哪个仓库名，需要 owner 确认，确认前不动徽章。

Q11（新增，对外动作）：E-D 的负向验证要开一个故意改坏的草稿 PR；Q1 推荐里要开 `needs-triage` issue（label 可能要新建）。这些都对外可见，是否同意、由谁来做，请 owner 决定。

## 8. 与其他计划的关系

- 0031 §8.3-2 要求的"一个真回合的端到端，脚本化假 provider 跑完整时序"由本计划的 Runner 满足；0031 附录 B.3 第 4 条"建议给 `build_app` 补 `provider=`"由 E-B1 落实。
- 0043 §9 的对照表是附录 A 的起点，附录 A 只补它漏掉的三处，不重做。
- 0057（ensemble tuning）的 `tests/ensemble/tuning/test_live_contract.py` 继续使用 `eval` marker，语义不变。
- 以后的真实模型路由 eval 计划从 `tests/evals/fixtures/live_routing_seed.json` 与本计划的 `Case`/`Result`/报告起步，`ScriptedProvider` 换成真实 provider 即可复用 Runner。

---

## 附录 A：Observability 差距审计

对照 harness9 `internal/observability/`（`attributes.go`、`setup.go`、`provider.go`、`hook.go`、`observer.go`、`config.go`）与 `cmd/harness9/main.go:123-131`，逐项读 `omicsclaw/observability/` 的代码。0043 §9 已有一张对照表，这里按 D8 列的项目重新核对代码，不照抄那张表。

| 编号 | 项目 | harness9 | OmicsClaw | 结论 |
|---|---|---|---|---|
| O1 | span 树 | `harness9.interaction > turn > llm_request / tool`（`attributes.go:14-17`、`observer.go`） | `omicsclaw.interaction > turn > llm_request / tool`（`attributes.py` `SPAN_*`）；interaction 由 `RunScope` 开（`scope.py:322,435`），turn 惰性创建（`scope.py:285-288`），llm_request 由 `TracedProvider` 开（`provider.py:236-237`），tool 由 `TracingHook` 开（`hook.py:161-162`）；阻塞路径只有两层并自报 | 已对齐。惰性 turn 与重试产生多个 llm_request 是有意的差异，0043 已记录 |
| O2 | 内部属性 | `session.id`、`llm.model`、`llm.tokens.input/output`、`agent.turn`、`tool.name`、`tool.success`、`agent.type`、`error.message`（`attributes.go:23-31`） | 全部同名（`attributes.py`），另有 `agent.turns`、`agent.stop_reason`、`turn.has_tool_calls`、`llm.tokens.cache_read`、`tool.status`（四值）、`error.type`、`error.status_code` | 已对齐（超集） |
| O3 | GenAI 属性 | `gen_ai.system`、`gen_ai.request.model`、`gen_ai.usage.input_tokens/output_tokens`（`attributes.go:66-69`） | 同名四个（`attributes.py`），写在 llm_request span 上（`provider.py:227-231,253-256`）；`gen_ai.system` 取 `inner.name` | 已对齐 |
| O4 | Langfuse v4 key | `langfuse.trace.input/output`、`langfuse.observation.input/output`，总是写（`attributes.go:58-61`、`provider.go`、`hook.go`） | 同名四个；trace 级在 interaction span（`scope.py:434,598`），observation 级在 llm_request 与 tool span（`provider.py:233,260`、`hook.py:158,233`）；全部受 `OMICSCLAW_OTEL_CAPTURE_CONTENT` 管，默认不写 | 已对齐；默认不捕获是按 `SAFETY_RULES` 第 1 条有意偏离（`config.py` `capture_content` 的说明） |
| O5 | 6 个指标 | `llm.request.duration`、`llm.tokens.input/output`、`tool.calls.total`、`tool.execution.duration`、`agent.turns.total`（`attributes.go:37-42`） | 同名，前缀 `omicsclaw.`，集中在 `INSTRUMENTS` 表（`attributes.py`），带单位；记录点：LLM 三个在 `provider.py:320-326`，工具两个在 `hook.py:244-246`，turns 在 `scope.py:573` | 已对齐 |
| O6 | 每次交互结束 flush | `OnInteractionEnd` 里 `ForceFlush`，5 s 超时（`observer.go:73-94`） | `RunScope.__aexit__` 在正常结束与普通异常时调 `flush`（`scope.py:449-496`）；`Telemetry.force_flush` 放进工作线程，吞掉 `Exception`、放过取消（`telemetry.py:154-173`）；OTLP 后端 `force_flush(timeout_millis=5000)`（`otel.py:69,183-184`）；console 后端不需要 flush | 已对齐；取消时不 flush 是有意差异 |
| O7 | Setup 失败回退 noop | `main.go:127-130`：`Setup` 出错打日志并换成 `NewNoopProviders()` | `build_telemetry`（`telemetry.py:192-234`）：没开、SDK 缺失、endpoint 为空、exporter 构造失败都退回 `Telemetry()`（noop），各记一条日志（`otel.py:99-126`） | 行为已对齐 |
| O8 | 同上，文字 | 同上 | `telemetry.py:200-205` 的 docstring 写着 "The reference treats a failed `Setup` as fatal"，与 `main.go:127-130` 不符；0043 §9 已把这条更正为"两边本来就一致"，代码注释没跟着改 | 缺口（事实错误），E-E2 |
| O9 | Langfuse `x-langfuse-ingestion-version=4` header | 代码不加，靠文档让用户写进 `OTEL_EXPORTER_OTLP_HEADERS`（`docs/core-features-en/eval.md:446,471`：缺它时 trace 会延迟出现） | 代码按原样透传 `OTEL_EXPORTER_OTLP_HEADERS`（`config.py` `parse_otlp_headers`、`otel.py:143-149`），机制上支持；但 `.env.example:214-215` 的 Langfuse 示例只写了 `Authorization=Basic ...`，仓库里 grep 不到 `ingestion-version` | 缺口（文档），E-E1。不在代码里自动加：harness9 也不加，而按 endpoint 猜厂商会给非 Langfuse 的 collector 发多余 header |
| O10 | 走生产装配的 span 树检查 | harness9 的 observability 测试各测一个 seam | `tests/observability/test_end_to_end.py` 用手搭的引擎测三层树；`tests/entry/test_telemetry_wiring.py:254-300` 走了 `build_app` 与阻塞路径 `run_turn`，但靠 `dataclasses.replace` 换 provider（:277-281，引擎由 :332-335 的 `_engine_over` 按 `app.provider` 重建），替换进去的 provider 没被 `TracedProvider` 包，所以树里没有 llm_request；`SessionRegistry` 的流式路径没有这样的端到端检查 | 缺口（测试），E-E3 |

E-E3 的断言（`tests/evals/test_observability_trace.py`，Runner + `RecordingTracer`，经 `SessionRegistry` 的流式路径）：
1. 恰好一个 `omicsclaw.interaction`，`session.id == "eval"`、`agent.type == "main"`、`agent.turns == 2`、`agent.stop_reason == "converged"`。
2. 两个 `omicsclaw.turn`，`agent.turn` 为 1、2；第 1 个 `turn.has_tool_calls` 为真，第 2 个为假；没有第三个空 turn。
3. 每个 turn 下恰好一个 `omicsclaw.llm_request`，父链为 `[llm_request, turn, interaction]`；属性 `gen_ai.system == "scripted"`、`gen_ai.request.model == "claude-sonnet-4-5"`、`gen_ai.usage.input_tokens == 100`、`gen_ai.usage.output_tokens == 50`，与 `llm.tokens.*` 相等。
4. 第 1 个 turn 下一个 `omicsclaw.tool`，`tool.name == "read_file"`、`tool.status == "ok"`、`tool.success` 为真。
5. 所有 span 都 `ended == 1`。
6. capture 关着时，没有任何 span 带 `langfuse.*` 键（对应 `SAFETY_RULES` 第 1 条）；另跑一遍 `capture_content=True`，四个键出现在各自的 span 上。
7. `RecordingMeter` 里 `omicsclaw.llm.tokens.input` 合计 200、`omicsclaw.agent.turns.total` 合计 2、`omicsclaw.tool.calls.total` 合计 1。
8. `on_flush` 计数器在一次交换后等于 1。

`RecordingTracer`/`RecordingMeter` 直接从 `tests/observability/_support.py` import，不复制一份。它们实现的是本层自己的 `Tracer`/`Meter` 协议，不依赖 OpenTelemetry SDK。这条测试在 `tests/evals/` 根目录、不带 `scripted_eval`，归 job1。D8 说的"内存 exporter"以此实现；若 owner 要求用 SDK 的 `InMemorySpanExporter`，job2 需要加装 `omicsclaw[otel]`，属于 Q1 之外的一个小改动。

---

## 附录 B：核实记录

### B.1 Runner 路径探针（2026-09-30）

scratchpad 里的一次性脚本，不进仓库。做法：monkeypatch `assembly.provider_from_env` 返回一个最小脚本化 provider，`AppConfig(workspace=tmp/ws, skills_dir=<repo>/skills, provider="anthropic", model="claude-sonnet-4-5", skill_env=off, permission_mode=auto-approve)`，`attach_sessions(build_app(cfg, telemetry=Telemetry()), store=InMemorySessionStore())`，`submit` 一次，遍历 `observe()`；同时把 `bash._locally` 换成"命中 `spatial_preprocess.py` 就返回 `STUB OK`，否则调原函数"。脚本四轮：`use_skill("spatial-preprocess")`、`bash("python <repo>/skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output out")`、`bash("rm -rf results/")`、收敛。结果：

- `use_skill` 返回 SKILL.md 正文；
- 第一个 `bash` 被 `_locally` 替身接住，观测为 `STUB OK`；
- `rm -rf results/` 在 auto-approve 下出了 `APPROVAL_REQUIRED`（`bash`、`high`），脚本拒绝后观测为 `is_error=True`、`tool 'bash' raised ApprovalDenied: bash was not approved: eval deny`，替身没有被调用，预置的 `results/a.txt` 仍在；
- 回合 `converged`，`reply == "all done"`；第一次请求 2 条消息（system + user），工具清单 11 个（§2.2）；
- summarizer 没被调用；出现的帧类型：`exchange_start, context, tool_start, progress, tool_result, approval_required, approval_settled, turn_end, exchange_end`。

第二次探针换了前两轮：`write_file("../outside/leak.txt")` 直接得到 `is_error` 观测 `PathEscapesWorkspace: '../outside/leak.txt' resolves to …/outside/leak.txt`，没有出审批卡；`write_file(".env")` 在 auto-approve 下出了 `write_file`、`high` 的审批卡，拒绝后为 `ApprovalDenied`。

### B.2 pip 最小 3.11 venv 基线

`/opt/conda/envs/OmicsClaw/bin/python -m venv`（3.11.15），先只装 `pytest setuptools socksio pydantic`：

- `pytest --co tests` 有 67 个收集错误，缺的模块按次数是 `rich` 21、`numpy` 19、`pandas` 11、`anndata` 4、`yaml` 3、`requests` 2、`nbformat` 1、`matplotlib` 1，另有 4 个 import 已删除的 `omicsclaw.*`。
- 同时确认 import `omicsclaw.entry.assembly`、`omicsclaw.entry.session`、`omicsclaw.entry.turn`、`omicsclaw.entry.compaction`、`omicsclaw.observability` 后 `sys.modules` 里没有第三方包。

再装旧 `pr-ci.yml` 的列表加 `rich nbformat scipy`（`numpy "pandas>=2.0,<3.0" scipy scikit-learn matplotlib PyYAML requests "anndata==0.11.4" h5py rich nbformat`）：

- 收集错误剩 12 个：`tests/runtime/consensus/` 下 7 个与 `tests/runtime/workflow/test_fan_out.py`（生产代码 `omicsclaw/runtime/workflow/fan_out.py:25`、`omicsclaw/runtime/consensus/operators/lca_r/wrapper.py:25` import 已删除的 `omicsclaw.skill.*`）、`tests/test_discover_file_trust.py`（`omicsclaw.services`）、两个 E-A4 要删的测试、`tests/sdk/test_replot_hint.py`（缺 `seaborn`）。
- 全量（`--continue-on-collection-errors`，默认 addopts）：157 failed、7178 passed、53 skipped、17 errors，420 s。失败最多的文件：`tests/test_skill_runner_contract.py` 76（`omicsclaw.providers` 等已删除模块）、`tests/runtime/consensus/*` 合计约 32、`tests/runtime/preflight/test_sc_batch.py` 10、`tests/routing/test_consensus_interpret_hint.py` 9、`tests/test_control_plane_documentation_contract.py` 7（读已删除的文档）。框架层的失败只有 `tests/entry/` 3 条、`tests/skillenv/` 3 条与 `tests/sdk/` 2 条。

### B.3 rapids_singlecell 对照

- `pytest --co tests`：11 个收集错误，除 `test_replot_hint.py` 外与 B.2 相同（该环境有 `seaborn`）。
- B.2 里 `tests/entry/` 的 3 条、`tests/skillenv/test_install_wiring.py::test_with_run_skill_the_tool_comes_after_it`、`tests/routing/test_consensus_interpret_hint.py` 全部、`tests/test_skill_runner_contract.py::test_skill_runner_module_exposes_run_skill_contract` 在 rapids 环境里同样失败（14 failed），说明它们是工作树本身的问题，与依赖无关。
- 全量（`--continue-on-collection-errors -p no:randomly`，默认 addopts）：146 failed、7294 passed、29 skipped、11 errors，574 s。按文件的失败分布与 B.2 基本相同：`tests/test_skill_runner_contract.py` 76、`tests/runtime/consensus/*` 合计 35、`tests/runtime/preflight/test_sc_batch.py` 10、`tests/routing/test_consensus_interpret_hint.py` 9、`tests/test_control_plane_documentation_contract.py` 7、`tests/test_bot_n_epochs_routing.py` 4。
- Q1 选项 a 的白名单目录（`engine entry provider tools context permission hooks memory planning observability schema skills subagent sandbox skillenv mcp sdk`）里的失败：rapids 环境 5 条（`tests/entry/` 3、`tests/skillenv/test_install_wiring.py` 与 `test_ensemble_environment.py` 各 1）；pip 最小 venv 8 条（多出 `tests/skillenv/test_overlay_real.py`、`tests/sdk/test_banksy_fallback.py`，以及 `tests/sdk/test_replot_hint.py` 的收集错误）。
- owner 测试环境记忆里的两条既有失败，`tests/tools/test_workspace.py` 这次两个环境都通过了；`tests/test_control_plane_documentation_contract.py` 仍失败。

### B.4 Headroom 反推（第 2 版，2026-09-30）

scratchpad 里的一次性脚本，不进仓库，只为核对 §3.4 的公式。eval 配置（`claude-sonnet-4-5`、`skill_env=off`、`memory=False`）下：`compose(app, (), prompt)` 的估算 `B = 10,267`；`estimate_tool_tokens(app.tools_snapshot) = 2,897`；`build_app` 给出的默认预算是 `ContextBudget(context_tokens=200000, reserve_output_tokens=64000, reserve_tool_tokens=2897, safety_ratio=0.1)`，即 `usable ≈ 113k`，种子用例到不了 `WARN`。400 行、每行 8 列的表格截到 8 KiB，作为一条 tool 消息估算 2,049 token。按 `U = floor((B+G)/t)`：`WARN` 目标、`G = 2,649` 时可行（0.477 / 0.600）；`FULL` 目标、同样的 `G` 不可行（`B/U = 0.636`）。

---

## 9. 实施记录（2026-09-30）

按 E-A → E-B → E-C → E-D → E-E 的顺序实施，每个阶段做完先核对验收再往下走。没有提交、没有推送，git 索引保持原样。

### 9.1 文件清单

新建：
- `omicsclaw/evals/`：`__init__.py`、`provider.py`、`assertions.py`、`case.py`、`hermetic.py`、`stubs.py`、`runner.py`、`report.py`
- `tests/evals/`：`__init__.py`、`conftest.py`、`_support.py`、`test_provider.py`、`test_assertions.py`、`test_report.py`、`test_runner.py`、`test_stubs.py`、`test_evals_is_not_imported.py`、`test_dataset_floor.py`、`test_fixtures.py`、`test_observability_trace.py`、`test_ci_known_failures.py`
- `tests/evals/dataset/`：`__init__.py`、`conftest.py`、`_checks.py`、`_harness.py`，以及 8 个 `test_<category>.py`（共 26 条用例）
- `tests/evals/fixtures/live_routing_seed.json`（26 条，由 `routing_oracle/v1.json` 迁来）、`tests/evals/fixtures/skill_runs/*.json`（7 份，全部取自真实 `--demo` 运行）
- `.github/workflows/eval.yml`、`tests/ci_known_failures.txt`

修改：
- `omicsclaw/entry/assembly.py`：`build_app(..., provider=None)`；`build_app` 与 `AgentApp` 的 docstring 改为说明新参数
- `pyproject.toml`：注册 `scripted_eval`，改写 `eval` 描述，删 `[tool.omicsclaw.eval]`（Q6）
- `tests/conftest.py`：读取 `tests/ci_known_failures.txt`，标 xfail
- `tests/entry/test_assembly.py`：E-B6 两条
- `omicsclaw/observability/telemetry.py`（O8）、`.env.example` 与 `docs/core-features/observability.md`（O9）
- `README.md`（What's New、CI 徽章）、`README_zh-CN.md`（CI 徽章）、`CONTRIBUTING.md`（marker 与 CI 一节）

删除（只删 E-A 列出的）：`.github/workflows/eval-nightly.yml`、`scripts/run_eval.py`、`tests/fixtures/{golden_routing,routing_budget,tool_list,routing_oracle}/`、`tests/test_benchmark_campaign.py`、`tests/test_evaluation_protocol.py`。

### 9.2 与计划的偏差

1. **13 号的压缩记录断言**。`CompactionRecord.pressure` 是"offload 之后测得、并抬到调用方下限的档位"（`context/compaction.py` 的字段说明），只 offload 的那次压缩记为 `none`，§3.10 写的"`pressure=WARN` 的条数 ≥ 1"不可能成立。改为断言"写回且 offload 了至少一条结果的压缩记录 ≥ 1"，再加"第 4 次调用之前没有占位"。第 4 次调用出现占位本身就说明 `WARN` 在那次调用前触发。
2. **13 号的取回路径**。占位里的路径是 `.omicsclaw/tool_results/eval/<call id>-<内容摘要>.txt`，脚本是写死的，所以用例在 import 时用真实的 `read_tool` 读一遍预置表格，按 `offload_key` 算出路径。`read_file` 默认只读 8 KiB，"读到第 399 行"做不到，改为断言"含表格行的 `read_file` 结果恰好两条"（首读一次、取回一次）。
3. **14 号的 FULL 档位**。选的是计划列出的第一种办法：先三次小读，再在同一轮里并行读两份 400 行表格，让增长集中落在触发调用上（`trigger_tokens=4700`，实测增长 4796）。没有改 `skills_index`，基线 `B` 保持生产配置。13 号 `trigger_tokens=2600`（实测 2675）。两处都取略低于实测的值，使触发调用落在档内、前一次调用低于 `WARN`。
4. **录取规范化多了两个占位符**。录取时发现 fixture 里还带着录取解释器的前缀（`/opt/conda/envs/OmicsClaw/...`）和 skill 自己建的临时目录（`/tmp/omicsclaw_bulkde_*`）。`normalize` 增加 `{python_prefix}` 与 `{tmp}`；`test_fixtures.py` 断言 fixture 里没有 `/workspace/`、`/root/`、`/tmp/`、`/opt/` 等开头的绝对路径。时间串正则改用数字边界，`run_20260930_041210` 这种写法也能匹配。
5. **录取环境**。`rapids_singlecell` 缺 `igraph`，`spatial-preprocess --demo` 跑不起来；7 份 fixture 全部改用 `/opt/conda/envs/OmicsClaw/bin/python` 录取（`provenance.environment` 已记），7 个都退出 0，Q8 没有用上。
6. **`--help` 不记为 skill 运行**。计划只说 `--help` 交给原 `_locally`。实现上 `--help` 既不打桩也不记 `SkillRun`，Runner 对每条 `stubbed=False` 的记录都发 `skill_ran_unstubbed`。否则 §5 第 4 条的变异（打桩失效）不会出警告。
7. **`tool_call()` 的 id**。`id=None` 时留空，由 `ScriptedProvider` 构造时按脚本顺序编号 `call_<n>`。计划要求计数器挂在 provider 实例上，而 `tool_call` 在 provider 之前调用，这样做能让同一工厂每次得到相同的 id。
8. **`ApprovalScript` 没有单独成类**。`Case.approvals` 直接是 `bool | ApprovalDecision` 的元组，和 §3.4 的字段示意一致，§3.1 包结构里提到的 `ApprovalScript` 省掉了。`Result` 多了一个 `stop_reasons`（每次交换一个）。
9. **CI 依赖**。job1 的 pip 列表在旧 `pr-ci.yml` 基础上加了 `seaborn`、`networkx`：`tests/sdk/test_replot_hint.py` 在收集阶段就要这两个包（附录 B.2 只记了 `seaborn`）。
10. **已知失败清单支持 `env` 标记**。E-D0 在 rapids 环境里的 5 条是 `strict=True`。另有两条只在 pip 环境失败、在 rapids 通过：`tests/sdk/test_banksy_fallback.py::…`（缺 scanpy）和 `tests/skillenv/test_overlay_real.py::…`（本地 venv 建在 conda 之上，CI 的 setup-python 不是 venv，可能会通过）。它们标 `| env`，按 `strict=False` 处理，否则本地会 XPASS 变红。这两条不 strict，修好之后不会逼着删，请 owner 知悉。
11. **desktop HTTP job**。Q1 的裁定提到"desktop HTTP job 排除 `tests/launch/test_surfaces.py`"，按"要加"理解，`eval.yml` 加了第三个 job `desktop-http`（装 `fastapi httpx uvicorn`，只跑 `tests/entry/test_desktop_*.py`），不在 `eval` 的 `needs` 里。owner 2026-09-30 确认不加，已从 `eval.yml` 删除；desktop HTTP 测试在 CI 里仍被跳过（R3）。
12. **包的延迟导入**。`omicsclaw/evals/__init__.py` 对 `report`、`runner`、`stubs` 的名字按需导入，避免 `python -m omicsclaw.evals.report` 触发 runpy 的 "found in sys.modules" 警告。
13. E-A 验收的 grep 另外命中 `CONTRIBUTING.md:374` 一句历史叙述（"The old `measure_routing_tokens.py` / `check_routing_budget.py` pair … was deleted"），是 `routing_budget` 子串匹配，不是引用，未改。

### 9.3 测试命令与结果

解释器默认 `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`；"最小 venv"是 scratchpad 里用 OmicsClaw env 的 3.11 建的 venv，只装 `pip install -e . pytest`（另装了 `setuptools socksio pydantic`）；"CI 模拟 venv"再装 job1 的整张 pip 列表。

| 阶段 | 命令 | 结果 |
|---|---|---|
| E-A | `pytest --co -q tests` | 收集错误 11 → 9 |
| E-B | `tests/evals`（包单测）、`tests/entry/test_assembly.py`、`test_telemetry_wiring.py`、`test_entry_is_the_top_layer.py`、`tests/sdk/test_boundary.py` | 173 passed，1 failed（R1 既有的 `test_this_layer_reads_no_provider_attribute_the_protocol_omits`） |
| E-B | 最小 venv：`pytest tests/evals` | 55 passed |
| E-C | `pytest tests/evals/dataset -m scripted_eval`，连跑 3 次，带 `OMICSCLAW_EVAL_REPORT_DIR` | 每次 26 passed，约 1.5 s；三份 `report.json` 去掉时间字段后完全一致；`report.md` 列出 8 类，0 条警告 |
| E-C | `pytest tests/evals`（rapids 与最小 venv） | 各 112 passed |
| E-E | `tests/evals/test_observability_trace.py`、`tests/observability`、`tests/test_env_example.py` | 9 passed；243 passed，1 skipped |
| E-D0 | 白名单目录一次（`-m "not slow and not demo and not eval and not scripted_eval"`） | 5 failed，6148 passed，20 skipped，290 s |
| E-D | CI 模拟 venv：已知失败涉及的文件 | 146 passed，7 xfailed |
| E-D | 最小 venv + `fastapi httpx uvicorn`：`tests/entry/test_desktop_*.py` | 563 passed，3 skipped |
| 收尾 | 上面 E-B、E-E 的相关测试加 `tests/evals` 全部 | 530 passed，1 skipped，1 xfailed；最小 venv `tests/evals` 114 passed |

E-D0 的已知失败（均写进 `tests/ci_known_failures.txt`）：
- `tests/entry/test_assembly.py::test_this_layer_reads_no_provider_attribute_the_protocol_omits`
- `tests/entry/test_session.py::test_a_second_compaction_extends_the_first_instead_of_restarting`
- `tests/entry/test_turn.py::test_the_system_message_survives_a_successful_summarization`
- `tests/skillenv/test_ensemble_environment.py::test_a_real_trial_records_its_interpreter`
- `tests/skillenv/test_install_wiring.py::test_with_run_skill_the_tool_comes_after_it`
- 仅 pip 环境（`env`）：`tests/sdk/test_banksy_fallback.py::test_missing_banksy_and_missing_sub_env_raise_env_not_found`、`tests/skillenv/test_overlay_real.py::test_the_overlay_sees_the_base_and_uses_the_base_pip`

§5 的一次性变异检查（改完即从 scratchpad 备份恢复）：
- 第 3 条：删掉一条用例，`test_there_are_at_least_baseline_cases` 失败。
- 第 4 条：打桩层不返回 stub，8 条 `skill_routing` 全部失败，报告里 8 条 `skill_ran_unstubbed`。
- 第 5 条：事后 `dataclasses.replace` 换 provider，引擎拿到了，summarizer 和 sub-agent runner 都没拿到。
- 第 6 条：删掉 `danger.py` 的 `rm -rf` 模式，`safety/dangerous_bash_asked_in_auto_mode` 失败（没出审批，`results/a.txt` 被删）。
- 第 7 条：关掉 planning gate，`planning/gate_nudges_read_only_exploration` 失败。

eval.yml 的负向验证只在本地模拟：在最小 venv 里按 job2 的步骤跑，把 `memory/write_then_search` 的一条断言改坏，pytest 退出 1，`summary` 输出 `FAIL: 25/26`、memory 类 50.0% 并列出失败原因，退出 0；恢复文件后重跑为绿。`report.json` 不存在时 `summary` 打印一行说明并退出 0。没有用 `act`。

### 9.4 未做与待 owner 决定

- Q11 的两件对外动作没有做，等 owner 同意：故意改坏一条用例的草稿 PR（看 job2 变红与 Step Summary），以及给已知失败开 `needs-triage` issue（`zhou-1314/OmicsClaw`，label 缺了要新建）。
- 两个 job 在真实 GitHub Actions 上是否全绿还没验证，要等第一次推送。白名单目录在 CI 模拟 venv 里只跑了已知失败涉及的文件，没有整体跑一遍（全量白名单只允许在 E-D0 跑一次）。
- 偏差 10：owner 2026-09-30 接受两条非 strict 的 `env` 条目。偏差 11：`desktop-http` job 已删除。Q11 的两件对外动作 owner 决定暂不做，真实 GitHub Actions 尚未验证。
