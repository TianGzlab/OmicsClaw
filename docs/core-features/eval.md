# 测试 · 评估 · 可观测（Test / Eval / Observability）

这三层合起来检查 agent 是否按预期工作。

```
开发阶段 ──→ Test（确定性测试）      ScriptedProvider + Assertion
CI 阶段  ──→ Eval（脚本化用例集）    26 个用例 + Quality Gate（全部通过）
生产阶段 ──→ Observability（追踪）  OTEL Traces + Metrics → Langfuse
```

Test 和 Eval 共用 `omicsclaw/evals/` 这一个包：Test 是包本身和它的单元测试，Eval 是建在包上、按类别组织、会出通过率报告的用例集。Observability 在 `omicsclaw/observability/`，细节见 [observability.md](observability.md)，本文只写它和 eval 的交点。

设计参照 harness9 的 `internal/evals`。和它相比有这些不同：

| 方面 | harness9 | OmicsClaw |
|---|---|---|
| 用例跑在什么上 | 手搭的最小引擎，5 个真实工具，无 Session、无 Compactor | 生产装配：`build_app(provider=...)` 加真实的 `SessionRegistry`，只关掉 MCP、换成内存 session |
| 重依赖的工具 | 无 | skill 脚本在 `bash` 的子进程层打桩，权限、hook、审批照常执行 |
| 密闭 | 清掉 `*_API_KEY` 等变量 | 另外拦截非回环地址的 `socket.connect`，隔离 `HOME`、XDG 目录，固定时区和 locale |
| 断言 | 8 种 | 12 种，另有 Runner 内置的硬失败 |
| 基线只增不减 | 写在文档里的约定 | `test_dataset_floor.py` 用测试强制 |
| 报告 | 写好了函数，CI 没用 | CI 写进 Step Summary，完整报告作为 artifact 保留 30 天 |
| 内容采集（Observability） | 总是上报 prompt 和工具输出 | 默认关闭 |

第一期只做脚本化的密闭 eval：LLM 的每一轮回复都写死，测的是"模型做出这些决策之后，装配、工具、权限、压缩是否表现正确"。模型会不会做出正确决策（例如选对 skill），留给后续的真实模型 eval，它不卡 PR。

---

## 1. Test 子系统

### 1.1 包结构

```
omicsclaw/evals/
├── provider.py     ScriptedProvider、ScriptedTurn、RecordedCall、tool_call()
├── assertions.py   Assertion 协议、Failure、12 种断言
├── case.py         Case、Headroom、Result、SkillRun、ApprovalRecord、FsChange
├── runner.py       arun_case / run_case、eval_config、headroom_budget
├── stubs.py        StubResult、stubbed_skill_runs、record_stub_result（兼作命令行）
├── hermetic.py     hermetic_env、hermetic_changes、block_network
└── report.py       build_report、write_json、write_markdown、step_summary（兼作命令行）
```

`omicsclaw/evals` 只 import `omicsclaw.entry` 及以下各层，框架里没有别的模块 import 它（`tests/evals/test_evals_is_not_imported.py` 检查）。它也不 import `skills.*`（`tests/sdk/test_boundary.py` 检查）。

### 1.2 ScriptedProvider

`ScriptedProvider` 实现 `LLMProvider` 协议（`generate`、`generate_stream`、`bind`），按顺序返回预设的 `ScriptedTurn`，不发任何网络请求。

```python
from omicsclaw.evals import ScriptedProvider, ScriptedTurn, tool_call

def provider():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "notes.md"}),)),
        ScriptedTurn(text="The note says slide A1 has 4992 spots."),
    )
```

| 机制 | 说明 |
|---|---|
| 主线与旁路 | 带 `tools` 的调用消费 `turns`；`tools=None` 的调用（摘要器等）消费 `side_replies`，两者分开记录在 `calls` 和 `side_calls` |
| 脚本用尽 | `on_exhausted="converge"`（默认）回复 `exhausted_text` 且不带工具调用，让循环停下；`"raise"` 抛 `ProviderError(status_code=400)`。用尽后的调用次数计入 `exhausted`，Runner 记为软警告 `script_exhausted` |
| 错误注入 | `ScriptedTurn(err=ProviderError(..., status_code=503))` 模拟 API 失败，用来测重试和失败路径 |
| usage | 每次主线调用报固定 usage，某一轮也可以单独指定 |
| 流式 | `generate_stream` 在第一次迭代时取下一轮，产出一个 `DONE` 块 |
| `bind` | 返回共享同一份脚本和记录的视图，所以 engine、摘要器、子 agent 拿到的都是同一个脚本 |
| 并发 | 状态变更都在一把锁里完成，子 agent 和主循环并发调用不会重复发出同一轮 |
| 调用 id | `tool_call()` 没给 id 时由 provider 实例编号，每次运行得到相同的 id |

`Case.provider` 是工厂函数，每次运行重新创建一个 provider。Runner 发现工厂返回的 provider 已经被调用过，会报错，避免用例之间串状态。

### 1.3 断言

断言实现 `name` 属性和 `check(result) -> Failure | None`。`Failure.is_soft` 为真时只记警告，不影响通过。

```
Hard（失败则用例不通过）
├── ToolCalled(tool, min_times=1)        工具至少被调用 N 次
├── ToolNotCalled(tool)                  工具一次都没被调用
├── OutputContains(text)                 最终回复包含文本
├── OutputExcludes(text)                 最终回复不含文本
├── NoError()                            没有交换失败
├── Error(kind=None)                     交换失败，给了 kind 时异常须是该类型
├── SkillInvoked(skill, domain=)         bash 跑了该 skill 的脚本，并按 index 反查出域
├── ToolArgs(tool, subset)               某次调用的参数包含这个 JSON 子集
├── PermissionRequested(tool, approved=None) 该工具走到了审批；给了 approved 时答复须一致
└── NoWriteOutside(root="workspace")    用例临时目录里的改动都在 root 之内（可写成 workspace/<子目录>）
Soft（失败只记警告）
├── MaxTurns(n)
└── MaxToolCalls(n)
```

用例集还有 4 个内部检查，放在 `tests/evals/dataset/_checks.py`，都是 hard：`SentContains`（送进某次调用的消息里有某段文本，可以要求出现次数和顺序）、`ToolResultContains`、`StopReasonIs`、`CountIs`。它们等到有别的使用者时再考虑提升进包。

Runner 自己也会记硬失败，不需要用例声明：

| 失败名 | 触发条件 |
|---|---|
| `approval_unscripted` | 出现了审批请求，但脚本里没有剩余的答复（Runner 会拒绝它） |
| `compaction_unexpected` | 用例没声明 `compaction=True`，却发生了压缩 |
| `stream_gap` | 观测到 `GAP` 帧，说明有帧丢失 |
| `headroom_infeasible` | 按 `Headroom` 算不出可行的窗口（见 1.6） |
| `case_timeout` | 整个用例超过 30 秒 |
| `stub_target_missing` | 被打桩的 skill 脚本不存在，或命令没带 `--output` |

软警告有两种：`script_exhausted`，以及 `skill_ran_unstubbed`（跑了一个没打桩的 skill 脚本）。

### 1.4 Runner

`run_case(case, tmp_path)` 在新的事件循环里跑 `arun_case`：

```
arun_case(case, tmp_path)
  ├── 建 ws/（工作区）、outside/（哨兵目录）、home/，写入 case.files 与 outside_files
  ├── provider = case.provider()，确认是新的
  ├── with hermetic_env(home, case.env):
  │     ├── 快照 tmp_path
  │     ├── build_app(eval_config(case, ws), provider=provider, telemetry=..., skills=...)
  │     │     eval_config：仓库 skills、claude-sonnet-4-5 的窗口、skill_env 关、sandbox 关、
  │     │     permission="auto" 用 AUTO_APPROVE，"ask" 用 DEFAULT，再叠加 case.config
  │     ├── compaction 用例：按 Headroom 算出 ContextBudget，dataclasses.replace 换进 app
  │     ├── attach_sessions(app, store=InMemorySessionStore())
  │     ├── with stubbed_skill_runs(case.skill_stubs, ...):
  │     │     依次 submit case.prompt 与 case.followups，逐帧观测：
  │     │     TOOL_START / TOOL_RESULT / APPROVAL_REQUIRED（按脚本答复）/ COMPACTION / GAP / EXCHANGE_END
  │     └── app.aclose()，再快照一次
  └── 汇总 Result，逐条执行 case.assertions，得出 passed / failures / warnings
```

memory 用 tmp 工作区里的 SQLite（`build_app` 固定打开 `<workspace>/.omicsclaw/memory.db`），同样与外界隔离。

`Result` 除了 harness9 有的字段（`passed`、`turn_count`、`tool_calls_executed`、`final_output`、`run_error`、`failures`、`warnings`、`duration_s`），还记录 `provider_calls`（每次调用送进模型的消息）、`side_calls`、`tool_results`、`skill_runs`、`approvals`、`fs_changes`、`compactions`、`stop_reasons`、`engine_turns`。`turn_count` 统计主线模型调用次数，包括重试；`engine_turns` 是引擎 `RunResult.turns` 之和。

Runner 修改的环境变量和 `bash` 的本地执行函数都是进程级的，所以同一进程里用例依次运行。`pytest-xdist` 的每个 worker 是独立进程，互不干扰。

### 1.5 skill 打桩

运行中的 agent 用 `bash` 执行 `python <skill 目录>/<script>.py ... --output <dir>` 来跑 skill。`stubbed_skill_runs` 在用例运行期间替换 `omicsclaw.tools.builtin.bash._locally`，也就是 `bash` 启动本地进程的那个函数。权限门、hook、参数校验和审批都在它之前执行，所以这些逻辑和生产完全一致。

替换后的函数这样处理命令：

- 跑的是被打桩 skill 的脚本，带 `--output`、不带 `--help`：检查脚本文件存在，把 `StubResult` 的文件写进输出目录，返回录好的 stdout 和退出码，记一条 `SkillRun(stubbed=True)`。
- 带 `--help` 或 `-h`：真的执行，不记录。
- 跑的是其他 skill 的脚本：真的执行，记 `stubbed=False`，产生 `skill_ran_unstubbed` 警告。
- 其他命令（`ls`、`cat SKILL.md` 等）：真的执行。

`StubResult` 由一次真实运行录制，fixture 放在 `tests/evals/fixtures/skill_runs/<skill>.json`：

```bash
python -m omicsclaw.evals.stubs record spatial-preprocess --demo \
    --out tests/evals/fixtures/skill_runs/spatial-preprocess.json
```

录制时绝对路径换成 `{output}`、`{repo}`、`{home}`、`{python_prefix}`、`{tmp}`，时间戳换成固定值，`provenance` 记下 skill、命令、git commit、日期、Python 版本和环境名。不超过 64 KiB 的输出文件原样保存，更大的只记文件名，回放时写空占位。`tests/evals/test_fixtures.py` 检查 fixture 里没有残留的绝对路径。现有 7 个 fixture 都录自 `--demo` 运行。

### 1.6 Headroom：让压缩在指定的那一次调用触发

默认窗口很大，普通用例不会压缩。压缩类用例声明 `compaction=True` 和 `Headroom(target, trigger_call, trigger_tokens)`，Runner 反推一个窗口，让第一次调用低于 `WARN`、第 `trigger_call` 次调用正好落在 `target` 档。

设 `B` 为第一次调用的 token 估算，`G` 为 `trigger_tokens`（用例作者按脚本估算的增长量），`t` 为目标档阈值，`t'` 为下一档阈值：

```
U = floor((B + G) / t)
可行条件：B / U < warn_at  且  (B + G) / U < t'
ContextBudget(context_tokens = U + 1024 + 工具定义 token,
              reserve_output_tokens = 1024,
              reserve_tool_tokens = 工具定义 token,
              safety_ratio = 0)
```

条件不成立时，用例以 `headroom_infeasible` 失败，并在消息里给出 `B`、`G`、`U`。

### 1.7 密闭环境

`hermetic_env(home, extra)` 在 `with` 块内：

- 删除所有以 `_API_KEY`、`_TOKEN`、`_SECRET` 结尾的变量，以及 `LLM_*`、`OTEL_EXPORTER_*`、`OMICSCLAW_PROVIDER`、`OMICSCLAW_MODEL`、`OMICSCLAW_BASE_URL`、`OMICSCLAW_OTEL_CAPTURE_CONTENT`、`XDG_CACHE_HOME`、`XDG_CONFIG_HOME`；
- 设 `OTEL_ENABLED=false`、`HOME=<tmp>/home`、`TZ=UTC`（并调用 `time.tzset()`）、`LANG=C.UTF-8`；
- 替换 `socket.connect` 与 `connect_ex`，连接非回环地址时抛 `OSError("network disabled in hermetic eval")`，这样 `web_fetch`、`web_search`、MCP 或误建的真实 provider 一旦触网就会失败。

`tests/evals/conftest.py` 的 `hermetic` fixture 用 `monkeypatch` 做同样的修改，供包自身的单元测试使用。

### 1.8 写一个用例

```python
import pytest

from omicsclaw.evals import NoError, ScriptedProvider, ScriptedTurn, ToolArgs, tool_call

from ._checks import ToolResultContains
from ._harness import check, seed


def _edit():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("edit_file", {
            "path": "params.yaml",
            "source_text": "resolution: 0.5",
            "target_text": "resolution: 1.0",
        }),)),
        ScriptedTurn(text="Resolution is now 1.0."),
    )


CASES = [
    seed(
        "tool_calling/edit_existing_file",
        "Set the clustering resolution in params.yaml to 1.0.",
        _edit,                                       # 工厂，不是实例
        ToolArgs("edit_file", {"path": "params.yaml"}),
        ToolResultContains("edit_file", "params.yaml", is_error=False),
        NoError(),
        files={"params.yaml": "method: leiden\nresolution: 0.5\n"},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results)
```

`seed()` 从 id 前缀取出类别，没写 `NoWriteOutside` 时自动补上。`check()` 跑用例、把结果交给报告收集器，有硬失败时调用 `pytest.fail`。

---

## 2. Eval 子系统：用例集

### 2.1 当前用例（26 个）

用例在 `tests/evals/dataset/test_<category>.py`，写成 Python 代码。每条默认都带 `NoWriteOutside()`。

| 类别 | 用例 | 验证目标 |
|---|---|---|
| `tool_calling` | `write_then_read` | `write_file` 写入，下一轮 `read_file` 读回，观测里有写入的内容 |
| `tool_calling` | `edit_existing_file` | `edit_file` 改了预置的 `params.yaml`，磁盘上恰好一处修改 |
| `tool_calling` | `parallel_read_only_calls` | 一轮两个 `read_file`，两条观测按请求顺序进入下一次请求 |
| `planning` | `plan_then_execute` | `plan_write` 写计划并逐步更新，下一次请求末尾带计划块 |
| `planning` | `gate_nudges_read_only_exploration` | 连续两轮只读、不写计划，第三次请求恰好带一次 planning gate 提示，第四次不再带 |
| `context` | `tool_error_is_observation` | 读不存在的文件得到 `is_error` 观测，循环继续并收敛 |
| `context` | `history_carried_across_exchanges` | 第二次交换带上第一次的问答，而且只有一条 system 消息 |
| `error_handling` | `provider_error_fails_exchange` | 400 错误不重试，交换以失败结束，只调用一次 |
| `error_handling` | `transient_error_retried` | 503 错误在同一引擎回合内重试成功 |
| `error_handling` | `max_turns_ceiling` | 达到 `max_turns=3` 时引擎停在 `MAX_TURNS`，不算错误 |
| `memory` | `write_then_search` | `memory_write` 写入的偏好能被 `memory_search` 搜到 |
| `memory` | `precis_reaches_next_exchange` | 写入的记忆出现在下一次交换系统提示的 "## Long-term memory" 一节 |
| `compaction` | `large_result_offloaded` | 大的 `read_file` 结果离开保留尾部后，在 `WARN` 档被 offload 成占位，模型能按占位路径取回 |
| `compaction` | `summary_replaces_head` | 到 `FULL` 档时历史开头换成摘要，system 消息保留，摘要器只调用一次 |
| `skill_routing` | `spatial` | `use_skill("spatial-preprocess")` 解析出目录，`bash` 跑脚本被打桩接住，`SkillInvoked` 反查出 spatial 域 |
| `skill_routing` | `singlecell` | 同上，`sc-clustering`（两级目录） |
| `skill_routing` | `bulkrna` | 同上，`bulkrna-de` |
| `skill_routing` | `genomics` | 同上，`genomics-variant-calling` |
| `skill_routing` | `proteomics` | 同上，`proteomics-quantification` |
| `skill_routing` | `metabolomics` | 同上，`metabolomics-de`（脚本名 `met_diff.py` 和 skill 名不对应） |
| `skill_routing` | `literature` | 同上，`literature`（skill 就在域目录本身） |
| `skill_routing` | `output_lands_on_disk` | 打桩按 `--output` 把 `result.json` 写进工作区，模型读得到 |
| `safety` | `rules_in_system_prompt` | 第一次请求的 system 消息里有 `SAFETY_RULES` 全部原文和 `TOOL_GUIDANCE` 的路径条 |
| `safety` | `dangerous_bash_asked_in_auto_mode` | auto-approve 下 `rm -rf results/` 仍然要审批，拒绝后目录原样保留 |
| `safety` | `ask_mode_denial_blocks_write` | ask 模式下拒绝 `write_file`，文件不存在，随后的 `read_file` 不需要审批 |
| `safety` | `path_escape_refused` | 写 `../outside/` 被 `PathEscapesWorkspace` 拒绝，不出审批卡，哨兵目录不变 |

`skill_routing` 测的是 skill 在 index 里、`use_skill` 能解析、`bash` 命令经过权限与 hook 后被打桩层接住、脚本文件仍然存在。它不测模型会不会选对 skill。7 条的 prompt 取自 `tests/evals/fixtures/live_routing_seed.json`，这份文件由旧的 `routing_oracle/v1.json` 迁来（26 条），也是以后真实模型路由 eval 的种子。

### 2.2 运行

```bash
PY=/opt/conda/envs/rapids_singlecell/bin/python   # 本机；CI 里是 setup-python 的 3.11

# 全部用例（约 1.5 秒，不需要 API key）
$PY -m pytest -q tests/evals/dataset -m scripted_eval

# 只跑一类
$PY -m pytest -q tests/evals/dataset/test_safety.py

# 包的单元测试 + 用例集 + 下限测试
$PY -m pytest -q tests/evals

# 生成报告
OMICSCLAW_EVAL_REPORT_DIR=build/eval-report $PY -m pytest -q tests/evals/dataset -m scripted_eval
python -m omicsclaw.evals.report summary build/eval-report/report.json
```

`tests/evals/dataset/conftest.py` 按路径给目录下的每个测试加 `scripted_eval` marker。pyproject 的默认 `addopts` 不排除它，所以本地直接跑 `pytest` 也会跑到用例集。另一个 marker `eval` 表示真实模型 eval，需要网络和 API key，默认排除，永远不卡 PR。

设置了 `OMICSCLAW_EVAL_REPORT_DIR` 时，session 结束会写出 `report.json` 和 `report.md`，内容包括总通过率、每类通过率、失败和警告。`report summary` 在报告不存在时打印一行说明，并以 0 退出。

### 2.3 新增用例的规范

- 放进对应类别的 `test_<category>.py`，id 写成 `"<category>/<name>"`。新类别要同时加进 `test_dataset_floor.py` 的 `CATEGORIES`。
- `provider` 传工厂函数，不要在模块级持有 `ScriptedProvider` 实例。
- 关键行为用 hard 断言钉住。`MaxTurns`、`MaxToolCalls` 只用来提示效率。
- 不写空转断言。脚本里根本没安排的工具，断言它"没被调用"什么也测不到。
- 用到新 skill 时，先用 `python -m omicsclaw.evals.stubs record` 录一份 fixture。
- 加了用例就把 `test_dataset_floor.py` 的 `BASELINE` 调高。删用例会让下限测试失败，所以用例集只增不减。

---

## 3. CI 质量门控

`.github/workflows/eval.yml` 在 PR 到 `main` 和推送到 `main` 时运行：

```
全局 env：OPENAI_API_KEY=""  ANTHROPIC_API_KEY=""  DEEPSEEK_API_KEY=""  LLM_API_KEY=""
          OTEL_ENABLED=false
       │
       ▼
  unit-tests（Python 3.11，pip 安装，不装 fastapi）
  └── pytest <框架层目录白名单> -m "not slow and not demo and not eval and not scripted_eval"
       │
       ▼ needs: unit-tests
  eval（Quality Gate）
  ├── pip install -e . pytest
  ├── pytest tests/evals/dataset -m scripted_eval   （OMICSCLAW_EVAL_REPORT_DIR=build/eval-report）
  ├── python -m omicsclaw.evals.report summary ... >> $GITHUB_STEP_SUMMARY   （always）
  └── 上传 build/eval-report/ 为 artifact，保留 30 天   （always）
```

门控规则：所有 hard 断言通过，用例才算通过；任何一条用例失败，eval job 就失败。soft 断言只进警告列表。

unit-tests job 只跑框架层目录：`engine`、`entry`、`provider`、`tools`、`context`、`permission`、`hooks`、`memory`、`planning`、`observability`、`schema`、`skills`、`subagent`、`sandbox`、`skillenv`、`mcp`、`sdk`、`evals`。这些目录里已知失败的测试列在 `tests/ci_known_failures.txt`，每行格式是 `<node id> | <原因> [| env]`，由 `tests/conftest.py` 标成 xfail：

- 普通条目是 `strict=True`。测试修好后会以 XPASS 让运行变红，逼着把它从清单里删掉，所以清单只会变短。
- 带 `env` 的条目只在部分环境失败（例如缺 scanpy），是非 strict 的。它们修好后不会自动报警，需要人工清理。

目前清单里有 5 条 strict、2 条 env。框架层以外的旧测试（`runtime/consensus` 等）不在 CI 里跑，清理它们另开计划。

CI 不装 fastapi，因为装了它，`tests/launch/test_surfaces.py` 会真的起服务并挂住。代价是 desktop HTTP 的测试在 CI 里被跳过，本地要用装了 fastapi 的环境跑 `tests/entry/test_desktop_*.py`。

---

## 4. Observability 与 eval 的交点

可观测层本身（span 树 `omicsclaw.interaction > omicsclaw.turn > omicsclaw.llm_request / omicsclaw.tool`、6 个 instrument、默认不采集内容、stdout 与 OTLP 后端）见 [observability.md](observability.md)。接入 Langfuse 只需配置环境变量：

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_TYPE=otlp
OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64 of "pk-...:sk-...">,x-langfuse-ingestion-version=4
# 需要在 Langfuse 里看到 prompt 和工具输出时才打开
# OMICSCLAW_OTEL_CAPTURE_CONTENT=true
```

eval 这边用 Runner 验证可观测层接到了生产装配上。`tests/evals/test_observability_trace.py` 让一条脚本化用例经过 `build_app(provider=)` 和流式的 `SessionRegistry` 路径运行，用 `RecordingTracer` / `RecordingMeter` 记录（不依赖 OTEL SDK），然后断言：

- 恰好一个 interaction span，带 session、类型、两个 turn 和 stop reason；
- 每个 turn 一个 llm_request span，带 GenAI 属性和 token 数；
- tool span 挂在第一个 turn 下；
- 每个 span 恰好结束一次；
- 默认没有任何 `langfuse.*` 属性，打开采集后 4 个 langfuse key 出现在对应的 span 上；
- 指标数值与这次交换对得上；
- 一次交换只 flush 一次。

---

## 5. 已知限制

- 脚本化 eval 测不到模型本身的决策质量。skill 路由是否正确、参数是否合理，要等真实模型 eval。
- skill 的科学正确性不在这里测。它归 skill 自己的测试和 ensemble benchmark。
- 打桩只认 `python <skill 目录>/<script>.py` 这一种调用形式，没有按任意命令匹配的桩。需要大段工具输出的用例改用预置文件加 `read_file`。
- `bash._locally` 是私有函数，打桩依赖这个名字。`tests/evals/test_stubs.py` 有钉子测试，改名时会先失败。
- 模型调用的重试退避基数是 1 秒，Runner 不调小它，所以 `transient_error_retried` 会真的等这 1 秒。
- 两个压缩用例的 `trigger_tokens` 是按当前系统提示和工具定义实测估出来的。系统提示大幅变化后可能报 `headroom_infeasible`，需要重新估算。
- `eval.yml` 只在本地模拟验证过（故意改坏一条用例，pytest 退出码为 1，Step Summary 显示 25/26），还没在 GitHub Actions 上真跑过。
- 仓库里有 30 多个测试文件各自实现假 provider，它们，还没迁移到 `ScriptedProvider`。新测试应当用共享实现。

---

## 6. 文件索引

| 路径 | 内容 |
|---|---|
| `omicsclaw/evals/` | 包本身，见 1.1 |
| `omicsclaw/entry/assembly.py` | `build_app(provider=)` 注入点 |
| `tests/evals/test_*.py` | 包的单元测试、下限测试、fixture 检查、可观测端到端测试 |
| `tests/evals/conftest.py` | `hermetic` 与 `eval_results` fixture，session 结束写报告 |
| `tests/evals/dataset/` | 用例集：`test_<category>.py`、`_harness.py`（`seed`、`check`）、`_checks.py`（4 个内部检查）、`conftest.py`（加 marker） |
| `tests/evals/fixtures/skill_runs/` | 7 个 skill 的 `StubResult` fixture |
| `tests/evals/fixtures/live_routing_seed.json` | 路由 prompt 种子，供 `skill_routing` 与以后的真实模型 eval 使用 |
| `tests/ci_known_failures.txt` | unit-tests job 的已知失败清单 |
| `.github/workflows/eval.yml` | CI 门控 |
| `docs/plans/0067-agent-evals.md` | 设计、裁定与实施记录 |
