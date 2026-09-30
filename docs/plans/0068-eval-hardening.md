# 计划 0068：Eval 加固（真实模型路由 eval、压缩用例事后检查与 0067 遗留限制分诊）

**状态**：已实现，待验收（2026-09-30）。H-A、H-B、H-C、H-D、H-E、H-H 已实施，实施记录见 §8；H-F 未做（对外动作需 owner 逐步同意），H-G 延后。计划正文为第 2.3 版，owner 已裁定 Q1 至 Q8（§7.0）与 PQ1 至 PQ5（§7.0.1）。

### 修订说明

**第 2.3 版（2026-09-30）**：记录 owner 对 PQ1 至 PQ5 的裁定（§7.0.1）。PQ5 维持 Q5 原裁定，H-H4 不改为跑全量。

**第 2.2 版（2026-09-30）**：记录 owner 对 Q1 至 Q8 的裁定（§7.0）。Q4 按 owner 明确撤回 0067 "不加 desktop-http job" 的裁定改写 H-E；Q8 改为在本计划内清理旧测试，新增 §3.1 盘点与 H-H 阶段，删掉正文里"单列 0069"的说法；清理中涉及生产代码的项目列为 PQ1 至 PQ5（§7.2），不由计划决定。

**第 2.1 版（2026-09-30）**：按第 2 轮审核的小问题修订，不涉及 owner 裁定。
- N1：没有指定模型的 sub-agent 直接用父 provider，不经过 `bind`（`entry/subagent.py:242-245`），它的调用和主线混在同一个 `calls` 里、`bound` 为空，分不开，两处来源也没有共同的时钟。`first_use_skill` 与 `parallel_use_skill` 改为只从 `RecordingProvider.replies`（本来就按时间排序）里取，删掉两处来源的合并；报告里的"主线调用次数"改为模型调用总数。
- N2：新增第五处 Runner 扩展 `Case.skill_fallback`，由 `arun_case` 传给 `stubbed_skill_runs(..., fallback=)`，否则兜底桩没有入口。
- N3：`.env` 规则改写为"尽力而为，只挡直接写出 `.env` 的命令"。
- N4：`headroom_missed` 按 0 起计的 `trigger_call` 写准；§L6 干跑表改为同样的编号。
- N5：写明严格 help 的保证来自审批策略先于 `_locally` 执行；live 桩复查严格形式列为可选。
- N6：`PYTHONPATH` 在 live 模式清掉；仓库相对路径的 help、`python3.x`、live 测试不看 `Result.passed` 这三点写进局限或设计；旁路表加 `--output o; pip install foo` 一行。

**第 2 版（2026-09-30）**：按第 1 轮审核修订。事实与机制直接改；凡是会改动 owner 已有裁定的，放进 §7，并附上审核的推荐。
- 阻断 B1：第 1 版说"`Headroom` 只检查首次调用，B 超过约 12.2k 时 `summary_replaces_head` 会以难懂的断言失败"，这个说法被审核的 `hole2.py` 推翻（本版重跑确认）。B 抬到 11.9k 至 14.0k 时用例照样通过；B = 14,165 时现有的首次调用检查报出可读的 `headroom_infeasible`。原因是 `WARN` 档只 offload 大结果，触发前的几次调用没有可 offload 的内容，进了 `WARN` 也什么都不写回。真正的边界是 `B < 3 × G = 14.1k`（按配置的 `G = 4700`）；第 1 版的 12.2k 用的是实测增长 4796，按配置的 `G` 算应是约 11.9k，而且这个约束本身就不存在。H-B 降为约 15 行的事后检查 `headroom_missed`，外加文档修正；自动标定移到"延后"，给出算账；删掉"读三份表格"的改动（§L6）。
- 阻断 B2：第 1 版 H-D 的审批策略有真实旁路，审核用 `bypass.py` 验证过（本版重跑确认）。策略与兜底桩改为：`--help` 只在命令恰好是 `python <script> --help|-h` 时批准；live 的兜底桩接管 skill 脚本的所有非 help 运行；只读清单拒绝 shell 元字符与 `find -exec` 一类参数；每种旁路写一条测试；§L1 第 6 条的算账按实际旁路重写。
- 阻断 B3：0067 已经弄坏了 `tests/launch/test_grammar.py::test_the_process_entry_points_in_the_tree_are_the_named_ones`（`evals/report.py`、`evals/stubs.py` 的 `__main__` 入口不在 `MODULE_GUARDS` 里，本版单跑确认失败）。H-A 补这两项，H-D 补 `live.py`，两个阶段的测试清单都加上 `test_grammar.py`；这条也作为 Q5a 的证据。
- Q4 改写：加装 fastapi 等于撤回 0067 里 owner 明确要求删掉 `desktop-http` job 的那次裁定所涉及的事，第 1 版"不冲突"的说法删掉，改为直接问 owner 是否愿意撤回。
- 判分规则补上 ReAct 的边界情况：并行 `use_skill`、读了一个 skill 又换、被策略拒绝后反问用户；说明 `RecordingProvider` 怎么记下回复（§L1 第 7 条；取数来源在 2.1 版改为只看 `replies`）。
- 种子的输入文件改为每条显式给出，第 1 版按域取默认值会误导（例如 `genomics__alignment_qc` 拿到的是 vcf）。
- H-C3 换成"sub-agent 的 `bash` 审批请求作为 `APPROVAL_REQUIRED` 到达会话"；原来的委派用例与 `tests/entry/test_subagent_wiring.py` 重复。H-C2 的理由改正：未知工具根本到不了 `GatedTool`。
- Runner 扩展删掉多余的 `Case.timeout_s`（`arun_case` 已有 `timeout_s`），数目改正，补上审批队列的分支与"`network=False` 仍断网"的测试。
- H-E3 写入审核在本机的基线：`tests/launch` + `tests/attachments` 3 failed、329 passed、380 s。
- 成本改为 30 至 90 分钟、3.5M 至 7M 输入 token，按 `.env` 实际的 deepseek 重写。
- 事实：`tests/entry` 替换 `provider_from_env` 的是 14 个文件；`testpaths` 是 `tests` 加 25 个 `skills/*` 目录；记忆抽取只在压缩时运行。
- 补三条局限：SDK 客户端在 `hermetic_env` 里才构造；`HOME` 换掉后 `pip --user` 装的包看不见；live 的工具清单没有 `run_skill`。

**第 1 版（2026-09-30）**：初稿。

**编号约定**：0067 的 owner 裁定写作 0067-D1 至 0067-D9，0067 的开放问题写作 0067-Q1 至 0067-Q11；本计划的限制条目记作 L1 至 L10（对应 brief 的 10 条），阶段记作 H-A 至 H-G，任务记作 H-A1、H-D3 这样，开放问题记作 Q1 至 Q8。

**行号约定**：以 2026-09-30 的工作树为准（`HEAD` 为 `0881aa7b`，0067 的实现尚未提交，行号读的是工作树）。实施时按符号名重新定位。

**代码注释约定**：实施时写的 docstring 与注释只说明函数做什么、有什么前提，不写计划编号、阶段号和决策经过；这些留在本计划里。

**如何核实**：代码逐处读过，没有跑全量。实测包括：
1. scratchpad 脚本对两个压缩用例做"关压缩的干跑"，逐次调用量 token（§L6）；重跑审核的 `hole2.py`，把 B 抬到 11.9k 至 14.2k 看用例结果（§L6）。
2. scratchpad 脚本用 `find_skill_run` 检查 15 种 `bash` 命令写法；重跑审核的 `bypass.py`（§L1、§L3）。
3. scratchpad 脚本解析 94 个 skill 的 `SKILL.md` 里 321 条 `python …` 推荐命令（§L3）。
4. 在装有 fastapi 0.136.1 的 `OmicsClaw` env 里只跑了 `tests/launch/test_surfaces.py`（§L9）；单跑 `tests/launch/test_grammar.py` 的一条测试（B3）。另对 `tests/{launch,bot,attachments,ensemble,routing,runtime}` 做了 `--co` 计数。
5. 审核在本机跑过一次 `tests/launch` + `tests/attachments`（结果见 H-E3），本版引用，未重跑。

**前置与关联**：0067（`omicsclaw/evals/`、26 条用例、`eval.yml`，§9 实施记录）；0043（observability）；0057（`tests/ensemble/tuning/test_live_contract.py`，仓库里唯一的 `eval` marker 用法，本计划的真实模型 eval 沿用它的写法）；`docs/core-features/eval.md` §3、§5 是本计划的问题来源。

---

## 0. 摘要

1. 分诊 10 条限制。要做的：真实模型路由 eval（L1，最大的一项）、压缩用例的事后检查（L6，约 15 行）、3 条新用例（L10）、一组事实修正（含 0067 弄坏的 `test_grammar.py`），两项 CI 覆盖扩展（L9，owner 已裁定，其中 Q4 撤回了 0067 的一次裁定），以及按 Q8 在本计划内清理旧测试（H-H）。不做的：L2、L4、L5、L8（L8 只修一个测试）。L3 在脚本化 eval 里继续不做，live eval 靠审批策略与兜底桩挡住漏网命令并计数。L7 只写验证步骤，标明需 owner 同意。
2. 核实时发现的过时或错误事实：
   - `tests/launch/test_surfaces.py` 的挂住问题在工作树里已经由 `no_web_server` fixture 修好：装了 fastapi 的环境里整个文件 149 passed，1.04 s。`tests/launch` 也不在 job1 白名单里。`eval.yml` 注释和 `eval.md` §3 的"装了 fastapi 会挂住"已经不成立。
   - 0067 让 `tests/launch/test_grammar.py` 的一条测试失败：`evals/report.py`、`evals/stubs.py` 的 `__main__` 入口没登记进 `MODULE_GUARDS`。
   - 压缩用例：现有检查只看首次调用，但这不是漏洞。触发前的调用落进 `WARN` 时没有可 offload 的内容，什么都不写回；真正的边界 `B < 3G ≈ 14.1k` 由首次调用检查可读地报出（§L6）。缺的只是一条事后检查，确认压缩确实发生在指定的那次调用。
3. 真实模型路由 eval：26 条种子，每条默认跑 3 次；判分只读轨迹，主指标取第一个真正执行的 skill 脚本，没执行时取第一次 `use_skill`；skill 执行由打桩接住，没有 fixture 的 skill 用兜底桩，兜底桩接管所有非 help 运行；审批改成策略函数，只批准严格形式的 `--help` 与不含 shell 元字符的只读命令。第一期只做手动本地运行，nightly 延后。
4. 阶段：H-A 事实修正（半天）→ H-B 压缩事后检查（半天）→ H-C 新用例（1 天）→ H-D 真实模型路由 eval（4 至 5 天）→ H-E CI 覆盖扩展（需裁定）→ H-F 真实 GitHub Actions 验证（需 owner 同意）→ H-G live nightly（延后）。
5. 白名单外的旧测试按 owner 的 Q8 裁定在本计划内清理（H-H，盘点见 §3.1）：6 个文件加 2 个空目录直接删；`tests/runtime/consensus` 与 `workflow` 的 22 个文件取决于 `omicsclaw/runtime/` 的去留（PQ1）。盘点还发现 4 个在 index 里的 skill 依赖不可导入的 `omicsclaw.runtime.consensus.run`，`--help` 都跑不起来，这是生产问题，交给 owner（PQ1）。

---

## 1. 目标与非目标

### 1.1 目标

- 有一套能测"模型会不会选对 skill"的真实模型 eval，手动可跑，结果有报告、能和上一次对比，而且跑的时候不会改动 owner 的环境。
- 压缩用例能确认压缩发生在声明的那次调用，而不是更早。
- 补上 0067 候选里值得做的用例。
- 修正文档、注释、测试里已经过时的说法，修好 0067 弄坏的 `test_grammar.py`。
- 把 CI 相关的遗留逐条给出结论，需要 owner 决定的放进 §7。

### 1.2 非目标

- 不自行推翻 0067 的裁定：Q11 的对外动作暂不做，不批量迁移假 provider，脚本化 eval 不加 LLM judge。"不加 desktop-http job" 一条已由 owner 在 Q4 撤回（§7.0），据此在 job1 里跑 desktop HTTP 测试。
- 不测 skill 的科学正确性（L2）。
- 不自行决定生产代码的删改：H-H 里涉及生产代码的项目全部列为 PQ1 至 PQ5。
- 不改 `bash` 的打桩 seam（L4），不给 `AppConfig` 加重试参数（L5）。
- 压缩用例的自动标定延后（§L6）。

---

## 2. 分诊总表

| 编号 | 限制 | 推荐 | 一句理由 | 阶段 |
|---|---|---|---|---|
| L1 | 脚本化 eval 测不到模型决策质量 | 做（手动本地；nightly 延后） | 路由选择是用户能感知的主要失败点，种子和 Runner 已就位，缺记录层、审批策略、判分和报告 | H-D（H-G 延后） |
| L2 | skill 科学正确性不在 eval 测 | 不做 | 打桩后 eval 碰不到计算；归 skill 自己的测试和 ensemble benchmark | 无 |
| L3 | 打桩只认 `python <skill 目录>/<script>.py` | 脚本化 eval 不做；live 由策略与兜底桩挡住并计数 | 321 条文档推荐命令全部能匹配；漏网写法只来自真实模型 | H-D 顺带 |
| L4 | 打桩依赖私有 `bash._locally` | 不做 | 钉子测试已能在改名时报错；公开 seam 要么改提示词，要么为测试改生产代码 | 无 |
| L5 | 重试退避 1 s 不可调 | 不做 | 省 1 s，代价是打破 `engine_config()` "只传两个字段"的约定 | 无 |
| L6 | 压缩用例 `trigger_tokens` 手估 | 只做事后检查；自动标定延后 | `G` 与 B 无关，系统提示变长不会让它失准；B 的边界已能可读地报出 | H-B |
| L7 | `eval.yml` 未在真实 Actions 上跑过 | 只写步骤，需 owner 同意 | 0067-Q11 的对外动作 owner 已决定暂不动 | H-F |
| L8 | 30+ 测试文件各自的假 provider | 不迁；只改 1 个测试 | `tests/entry` 有 14 个文件替换 `provider_from_env`，已覆盖六个消费者 | H-A4 |
| L9 | CI 遗留 | a 做（owner 已撤回 0067 裁定）；b 维持；c 在本计划内清理 | a：原先不装 fastapi 的唯一理由（挂住）已消失；c：owner Q8 裁定并入 | H-A1、H-E、H-H |
| L10 | 其它缺陷与覆盖空白 | 3 条新用例 + 事实修正 | 只加"经过生产装配才可能坏"的用例 | H-A、H-C |

---

## 3. 逐条分诊

### L1 真实模型路由 eval

现状证据：
- `tests/evals/fixtures/live_routing_seed.json`：26 条，7 个域，涉及 22 个 skill；25 条 `decision: route`，`literature__new_method_boundary` 为 `no_skill`。
- `eval` marker 已描述为"真实 LLM、手动或 nightly、永不卡 PR"，默认排除。唯一用例 `tests/ensemble/tuning/test_live_contract.py` 用 `pytestmark = [pytest.mark.eval, skipif(OMICSCLAW_TUNING_LIVE != "1")]`，并自己读仓库根 `.env`，因为 `tests/conftest.py` 每个测试前会清掉 `.env` 里出现的键。
- Runner（`runner.py` 的 `arun_case`）对 provider 只用 `turn_index`、`side_calls`、`calls`、`exhausted`（:229-233、:363、:380-392），类型写死为 `ScriptedProvider`。`case.provider()` 在进入 `hermetic_env` 之前调用（:229 对 :250）。`arun_case` 已有 `timeout_s` 参数（:201）。审批答复取自 `queue = list(case.approvals)`（:247）。
- `hermetic_env` 总是套 `block_network()`，会挡住真实 provider 的连接；`block_network` 只替换本进程的 `socket.connect`，`bash` 子进程不受影响。
- 打桩（`stubs.py` 的 `stubbed_skill_runs`）：`--help` 命令整条交给原 `_locally` 执行（:239-240）；没有 fixture 的 skill 整条真实执行（:242-247）。现有 fixture 7 份，种子涉及的 22 个 skill 里有 15 个没有 fixture。
- `permission/danger.py` 不把 `pip install` 当危险命令，只在 `curl|wget` 带上传参数时拦（:180）。
- 仓库 `.env` 配的是 `LLM_PROVIDER=deepseek`，走 `openai_provider`；它给最后一条消息和最后一个工具加 `cache_control`（`openai_provider.py:230-248`），DeepSeek 本身也自动缓存前缀。
- 基线 `B ≈ 10.3k` token（skill 索引约 8.4k），工具定义约 2.9k；种子涉及的 22 个 `SKILL.md` 估算 742 至 1,830 token，平均 1,238。
- 记忆抽取（`entry/memory.py:236-251` 的 `build_memory_extractor`）只在压缩时运行（`entry/compaction.py:109-111`），不是每次交换都有。

推荐：做。第一期只做手动本地运行（H-D），nightly 延后（H-G）。

理由：脚本化 eval 把模型的每一步写死，`skill_routing` 只证明链路通。`OMICSCLAW.md` 的路由表、skill 描述行和 `use_skill` 的返回改了以后，模型还选不选得对，现在没有任何测量。

成本：代码约 800 至 1,000 行（含单元测试），4 至 5 天。运行成本见第 11 条。

方案：

1. 放在哪里。
   - `omicsclaw/evals/live.py`：`RecordingProvider`、种子加载、`live_case()`、`routing_policy()`、`judge()`、`LiveReport`、`compare()`，以及 `python -m omicsclaw.evals.live compare <旧> <新>`。这个 `__main__` 入口要登记进 `tests/launch/test_grammar.py` 的 `MODULE_GUARDS`（B3）。
   - `tests/evals/live/test_live_routing.py`：`pytestmark = [pytest.mark.eval, pytest.mark.skipif(os.environ.get("OMICSCLAW_EVAL_LIVE") != "1", ...)]`，按种子参数化。
   - `tests/evals/live/conftest.py`：读仓库根 `.env`（照 `test_live_contract.py` 的 `_model()`），构造 provider 工厂；session 结束时写 `live_report.json` 与 `live_report.md`，用自己的收集器，不用 `eval_results`。
   - `tests/evals/test_live.py`：`live.py` 的单元测试，不带 marker，用 `ScriptedProvider` 冒充"会选 skill 的模型"，归 job1。它不往 `eval_results` 里写，否则会和 `tests/evals/conftest.py` 的 `pytest_sessionfinish` 报告撞在一起。
   - `tests/evals/dataset/conftest.py` 的 marker hook 只处理 `tests/evals/dataset/` 下的 item；`test_dataset_floor.py` 只收集 `dataset/` 下的 `CASES`。两者都不受影响。

2. Runner 的五处扩展（默认值保持脚本化用例行为不变）：
   - `case.py`：`Case.provider` 的返回类型放宽为一个 `Protocol`（有 `calls`、`side_calls`、`turn_index`、`exhausted` 即可）。
   - `case.py` 与 `runner.py`：`Case.approvals` 也接受 `Callable[[ApprovalRequest], ApprovalDecision]`。`runner.py:247` 的 `queue = list(case.approvals)` 加一个分支：是函数时每个请求调用它，不记 `approval_unscripted`，答复照常记进 `Result.approvals`。
   - `case.py` 与 `hermetic.py`：新增 `Case.network: bool = False`，为真时 `hermetic_env(..., block_network=False)`，其余隔离照旧。`test_runner.py` 加一条：默认的 `network=False` 下连接非回环地址仍抛 `OSError`。
   - `stubs.py`：`stubbed_skill_runs(..., fallback: StubResult | None = None)`，行为见第 5 条。默认 `None` 时与现在相同。
   - `case.py` 与 `runner.py`：新增 `Case.skill_fallback: StubResult | None = None`，`arun_case` 把它传给 `stubbed_skill_runs(..., fallback=case.skill_fallback)`。默认 `None`，脚本化用例不受影响；`live_case` 设成兜底桩。
   超时不加字段，live 测试直接调 `run_case(case, tmp_path, timeout_s=300)`。

3. `RecordingProvider`：包住一个真实 `LLMProvider`，对外仍是 `LLMProvider`。每次调用记下送出的消息与工具名（沿用 `RecordedCall`），另存一份对应的回复：`RecordedCall` 没有回复字段，`RecordingProvider` 自己维护一个与 `calls` 等长的 `replies: tuple[Message, ...]`（`generate` 取 `Completion.message`，`generate_stream` 取 `DONE` 块的 message），不改 `RecordedCall`，也不改 `ScriptedProvider`。`bind()` 返回共享记录的视图。`tools is None` 的调用记进 `side_calls`。`exhausted` 恒为 0。没有指定模型的 sub-agent 直接用父 provider、不经过 `bind`（`entry/subagent.py:242-245`），它的调用与主线进同一个 `calls`，`bound` 为空，无法区分；所以判分不区分主线与 sub-agent，只按 `replies` 的先后（调用顺序就是时间顺序）取 `use_skill`。

4. provider 与模型：默认用仓库 `.env` 解析出的配置（`resolve_config(env=<.env 合并 os.environ>)`），现在是 deepseek；可用 `OMICSCLAW_EVAL_LIVE_PROVIDER`、`OMICSCLAW_EVAL_LIVE_MODEL` 覆盖。报告记录 provider、model、base_url、temperature。温度不强制为 0。`eval_config` 的 `provider`、`model` 用 `case.config` 覆盖成真实值，使窗口预算与生产一致。见 Q1。

5. 每条用例怎么跑（`live_case(seed, provider_factory, trial)`）：
   - prompt：`seed.query` 后加一行 `Input: <路径>`，工作区放同名的 0 字节文件。输入路径是每条种子的显式字段 `inputs`（列表，大多数一个，`no_skill` 种子为空），不按域取默认值。§L1 附表给出草案，实施时逐条对照对应 `SKILL.md` 的输入格式核实。
   - 配置：`permission="ask"`（`PermissionMode.DEFAULT`）；`skill_env` 用生产默认的 `probe`，让 `use_skill` 的返回与生产一致；`max_turns=6`；sub-agent 保持开启；`network=True`；`skill_fallback` 设为兜底桩；`env={"PYTHONPATH": ""}`，因为 `hermetic_env` 不清 `PYTHONPATH`，而开发环境里它常指向仓库（实施时确认空值与未设置等效，否则改为在 live 模式下从环境里删掉）。
   - 打桩：7 个有 fixture 的 skill 用 fixture；其余 skill 的脚本运行由兜底桩回答（stdout `"[eval] <skill> run recorded; outputs in {output}"`，退出码 0，写一个 `result.json` 占位）。live 模式下兜底桩接管 skill 脚本的所有非 help 运行：命令里没有 `--output` 时，返回退出码 2 和一句说明（"--output is required"），不真实执行，也不记 hard failure；只有第 6 条批准的严格 `--help` 才真实执行。
   - `--help` 真实执行，所以手动运行要在 skill 依赖齐全的环境里做（`OmicsClaw` env，0067 录 fixture 用的也是它）。

6. 审批策略 `routing_policy()`：在 `DEFAULT` 模式下出审批的调用，策略这样回答。
   - `bash`：
     - skill 脚本的 help：命令恰好是 `python <skill 脚本路径> --help` 或 `-h`（允许 `python3` 与当前解释器路径），没有环境变量前缀，不含 `;`、`&`、`|`、`$`、反引号、`<`、`>`、`(`、`)` 与换行时批准。这个保证来自审批的先后：`bash` 的审批在 `_locally` 之前完成，被拒的命令根本到不了 `_locally`，而 `_locally` 里的打桩层对 help 仍是整条真实执行。可选的纵深防御：live 桩在放行 help 前再按同样的规则复查一次，约 3 行。`python3.x` 不在允许的解释器里，这类命令会被拒绝，无害。
     - skill 脚本的运行（被 `find_skill_run` 识别、不是 help）：批准。兜底桩或 fixture 会在 `_locally` 里接住，不会真实执行，命令里附带的其它部分也就不会执行。
     - 只读命令：所有分段的首个词都在清单里（`ls`、`cat`、`head`、`tail`、`wc`、`find`、`grep`、`pwd`、`file`、`stat`、`tree`、`du`），除了清单命令之间的 `|` 以外不含任何 shell 元字符（`;`、`&`、`$`、反引号、`<`、`>`、`(`、`)`、换行），`find` 不带 `-exec`、`-execdir`、`-ok`、`-okdir`、`-delete`、`-fprint`、`-fprint0`、`-fprintf`、`-fls`，`tree` 不带 `-o`，命令里不直接写出 `.env`：批准。`.env` 这一条是尽力而为，`cat .en?`、`grep -r KEY <仓库>` 都能绕过；这里防的是粗心的模型，不是有意对抗的模型，不再加固。
     - 命令里出现 skill 目录路径却没被识别为 skill 脚本：拒绝，记 `unmatched_skill_command`（L3 需要的数据）。
     - 其余一律拒绝，理由 "not permitted in the routing eval"。
   - `web_fetch`、`web_search`：拒绝。
   - `write_file`、`edit_file`：工作区内批准。
   - 其余工具：批准。

   已知旁路与对应处理（审核 `bypass.py` 验证过前五种，本版重跑确认）：

   | 写法 | 第 1 版的结果 | 本版的处理 |
   |---|---|---|
   | `python <skill>.py --help && pip install foo` | `stubs.py:239-240` 把整条命令交给真实执行 | 不是严格 help 形式，也不是 skill 运行（`wants_help` 为真），落到"其余"，拒绝 |
   | `python <skill>.py -h \| tee /etc/x` | 同上 | 同上 |
   | `python <skill>.py --help; pip install foo` | `find_skill_run` 把 `--help;` 当普通参数，走"无 fixture 真实执行"（:242-247） | 识别为 skill 运行，被兜底桩接住，整条不执行 |
   | `python <skill>.py --demo`（无 `--output`） | 无 fixture 时真实执行 | 兜底桩返回退出码 2，不执行 |
   | `find . -exec pip install foo \;` | 只读首词 `find` 通过 | `-exec` 被拒 |
   | `ls $(pip install foo)` | 只读首词 `ls` 通过 | `$` 被拒 |
   | `PYTHONPATH=. python <skill>.py --help`，配合事先写进工作区的 `numpy.py` | help 真实执行，import 被劫持 | 有环境变量前缀，不是严格形式，拒绝；严格形式下脚本目录在 `sys.path[0]`，工作区不在 import 路径上 |
   | `python <skill>.py --input a --output o; pip install foo` | 有 fixture 时被桩接住，没有时真实执行 | 识别为 skill 运行（`--output` 解析成 `o;`），被 fixture 或兜底桩接住，整条不执行 |
   | `cat <仓库>/.env` | 批准，密钥进入对话 | 直接写出 `.env` 的只读命令拒绝（尽力而为，见上） |
   | `find /` | 批准 | 仍批准，只读、低风险，报告里能看到 |

   test_live.py 为上表每一种写法各写一条测试。

   算账：这一层防的是模型在 owner 的 conda 环境里执行 `pip install`、`conda install`、`curl` 之类会改环境或往外发数据的命令，以及 web 工具外发请求。剩下的旁路：严格形式的 `--help` 仍会真实 import skill 脚本，脚本若在 import 时联网或写文件，这里挡不住；只读命令能读到工作区之外的文件，`.env` 规则只挡直接写出文件名的命令，内容会进入发给 provider 的对话；`hermetic_env` 清掉的只是环境变量里的密钥，写在文件里的密钥靠的是 `.env` 规则，其它位置的凭据文件（例如 `~/.aws`）因为 `HOME` 被换成临时目录而读不到默认路径，但绝对路径仍可读。代价是模型的非只读命令会收到拒绝观测，对话走向和生产不同；判分点在这之前，影响有限。值得做：不做的话，一次运行就可能改坏 owner 的分析环境。

7. 判分（`judge(result, seed, replies) -> Verdict`，只读轨迹，不用 LLM）。每次对话记录：
   - `first_use_skill`：`RecordingProvider.replies` 里（按调用先后，主线与 sub-agent 不区分）第一次 `use_skill` 的 `skill_name`。
   - `parallel_use_skill`：同一份 `replies` 里第一条含 `use_skill` 的回复共有几个 `use_skill`（大于 1 表示并行查了多个 skill），以及它们的名字。
   - `executed_skill`：`Result.skill_runs` 的第一条（不含 help）。
   - `chosen`：有 `executed_skill` 时取它，否则取 `first_use_skill`。主指标看 `chosen`，这样"先读 A 又换成 B 并执行 B"按 B 判。
   - `outcome`：`correct`（`chosen` 在 `expected_skills` 里）、`wrong_skill`、`no_skill_called`、`error`（交换以 `ProviderError` 或超时结束）。`no_skill_called` 再按"在此之前有没有被策略拒绝"分成 `no_skill_after_denial` 与 `no_skill_no_denial`，后者里最后一条回复以问号结尾的再标 `asked_user`（启发式，报告里注明）。
   - `no_skill` 种子：没有执行任何 skill 脚本即为 `correct`，允许调 `use_skill` 读 `SKILL.md`，见 Q3。
   - 次要指标，不计入通过率：`args_ok`（种子写了 `expected_args` 时，`executed_skill` 那条命令的参数包含它，且 `--input` 是种子的输入文件、带 `--output`）。`expected_args` 只给 query 点名了方法的种子填：`singlecell__batch_harmony` → `--method harmony`、`singlecell__cell_annotation` → `--method celltypist`、`spatial__ligand_receptor` → `--method liana` 已 grep 核实；`bulkrna__deseq2`、`metabolomics__xcms_raw`、`bulkrna__wgcna` 实施时核实后决定。
   - 每条种子的通过率 = `correct` 次数 /（N − `error` 次数）。全部 N 次都是 `error` 时这条种子在 pytest 里失败，让密钥失效、服务不可用一类故障显形；通过率本身不让任何测试失败。
   - live 测试不看 `Result.passed`：用例不带断言，Runner 记的 hard failure（例如 `stub_target_missing`、`case_timeout`）按次写进报告的 `harness_failures`，不让 pytest 失败，在 `live_report.md` 里单独列出。

8. 次数：`OMICSCLAW_EVAL_LIVE_TRIALS`，默认 3。不做置信区间，也不自适应加跑。报告写明 3 次只能分出 0、33%、67%、100% 四档。

9. 报告：
   - `live_report.json`：`meta`（`run_at`、git commit、provider、model、base_url、temperature、trials、种子文件 sha256）；`seeds[]`（每次的 `outcome`、`first_use_skill`、`parallel_use_skill`、`executed_skill`、`chosen`、`args_ok`、`harness_failures`、模型调用总数（即 `turn_count`，含 sub-agent 的调用）、输入与输出 token、缓存命中 token、耗时）；`domains{}`；`confusion`（expected → chosen）；`denials`（策略拒绝的命令，含 `unmatched_skill_command`）；token 合计。
   - `live_report.md`：总通过率、每域通过率、失败种子、混淆表、`no_skill_called` 的细分。不用 emoji。
   - 趋势：`python -m omicsclaw.evals.live compare old.json new.json` 打印每条种子通过率与 `chosen` 的变化，provider、model 或 base_url 不同时在首行提示。第一期不在仓库里存基线（Q7）。

10. 运行方式（手动）：
    ```bash
    OMICSCLAW_EVAL_LIVE=1 OMICSCLAW_EVAL_LIVE_TRIALS=3 \
    OMICSCLAW_EVAL_REPORT_DIR=build/live-eval \
    /opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:randomly -m eval tests/evals/live
    ```
    按顺序执行，不并行：Runner 改的环境变量与 `_locally` 替换都是进程级的。

11. 成本估算：
    - 每次主线调用的输入约 13.2k token（`B` 10.3k + 工具 2.9k），`use_skill` 返回后再加约 1.2k；一次对话 4 至 6 次调用，输入约 55k 至 90k token，输出约 1k 至 3k。
    - 26 条 × 3 次 = 78 次对话，输入约 3.5M 至 7M token，输出约 0.1M 至 0.25M。
    - 按 Q1a 走 deepseek：每次调用前约 13k token 是相同的前缀，`openai_provider` 已加 `cache_control`，DeepSeek 也自动缓存前缀，所以输入里大部分会按缓存命中计价。费用 ≈ 未命中输入 × 输入单价 + 命中输入 × 缓存单价 + 输出 × 输出单价，单价按实施时的价目表；报告记下缓存命中的 token，实跑后用真实数字替换这里的估算。
    - 压缩不会发生（窗口按生产配置，对话很短），所以没有记忆抽取的旁路调用。
    - 耗时：模型调用每次 5 至 15 s；严格 `--help` 会 import scanpy 一类依赖，每次 5 至 20 s；`skill_env=probe` 在 `use_skill` 时起子进程检查依赖。顺序跑约 30 至 90 分钟。

12. 局限（写进报告与 `eval.md`）：
    - 种子只覆盖 94 个 skill 里的 22 个；query 全是英文，而用户常用中文。
    - 输入文件是 0 字节占位，模型若先 `cat` 或 `head` 它会看到空文件；`Input:` 行是本计划加的，和原 oracle 的 query 略有不同。
    - 判分只看选择和少数参数，不看回答质量。
    - 结果依赖所用模型，换模型不可直接比较。
    - provider 的 SDK 客户端在 `hermetic_env` 里第一次请求时才构造，`api_key` 由 `resolve_config` 显式传入（`anthropic_provider.py:582-583`、`openai_provider.py:469`），但 SDK 自己读环境变量的回退（例如代理或 base_url 类变量）在清过的环境里看不到。
    - 严格 help 里用仓库相对路径（`python skills/…/x.py --help`）时，`cwd` 是工作区，脚本找不到，模型得到一条错误观测，无害；审批策略不能改写命令，所以不做路径规范化。
    - `HOME` 换成临时目录后，用 `pip --user` 装在真实 `HOME` 下的包对 `--help` 与 `probe` 不可见。
    - 工具清单来自 `build_app`，没有 `open_app` 在生产里挂载的 `run_skill`（ensemble），模型在生产里可能选它。

附表：种子输入草案（实施时对照 `SKILL.md` 核实并写进种子文件）

| 种子 | `inputs` |
|---|---|
| `spatial__preprocess_visium` | `data/visium.h5ad` |
| `spatial__spot_deconvolution` | `data/visium.h5ad`、`data/sc_reference.h5ad` |
| `spatial__ligand_receptor` | `data/spatial_annotated.h5ad` |
| `spatial__domains_auto_compute_pca` | `data/spatial.h5ad` |
| `singlecell__cluster_leiden` | `data/normalized.h5ad` |
| `singlecell__cluster_raw_precondition` | `data/raw_counts.h5ad` |
| `singlecell__cluster_incompatible_input` | `data/object.h5ad` |
| `singlecell__cell_annotation` | `data/clustered.h5ad` |
| `singlecell__batch_harmony` | `data/batches.h5ad` |
| `singlecell__velocity_route_noun` | `data/spliced_unspliced.h5ad` |
| `singlecell__de_route_verb` | `data/clustered.h5ad` |
| `genomics__alignment_qc` | `data/sample.bam` |
| `genomics__small_variants` | `data/sample.vcf` |
| `genomics__structural_variants` | `data/sv.vcf` |
| `proteomics__peptide_identification` | `data/peptide.csv` |
| `proteomics__lfq_quantification` | `data/peptide_intensities.tsv` |
| `proteomics__ptm_sites` | `data/phosphosites.tsv` |
| `metabolomics__xcms_raw` | `data/raw/sample1.mzML` |
| `metabolomics__feature_annotation` | `data/features.csv` |
| `metabolomics__two_group_de` | `data/features.csv` |
| `bulkrna__fastq_qc` | `data/sample_R1.fastq.gz` |
| `bulkrna__deseq2` | `data/counts.csv` |
| `bulkrna__wgcna` | `data/cohort_counts.csv` |
| `literature__geo_accessions` | `data/paper.pdf` |
| `literature__paper_pdf` | `data/paper.pdf` |
| `literature__new_method_boundary` | 无 |

### L2 skill 的科学正确性

现状证据：`pyproject.toml` 的 `testpaths` 是 `tests` 加 25 个 `skills/*/tests` 目录，`skills/` 下共 68 个 `test_*.py`；ensemble 的评估在 `omicsclaw/ensemble/evaluation.py` 与 `tests/ensemble/`。eval 里 skill 执行被打桩，桩的输出取自一次录制，不随 skill 代码变化。

推荐：不做。

理由：打桩后 eval 碰不到 skill 的计算，正确性只能在 skill 自己的测试或 benchmark 里真实计算。

顺带说明：job1 白名单只有 `tests/` 下的框架层目录，`skills/*/tests` 不在 CI 里跑（需要 scanpy 等重依赖）。这是 skill 测试的覆盖空白，本计划不处理，H-A2 把它写进 `eval.md` §5。

### L3 打桩只认 `python <skill 目录>/<script>.py`

现状证据：
- `stubs.py` 的 `_script_of` 找 `python`、`python3`、`python3.x` 或当前解释器，跳过以 `-` 开头的参数，取第一个 `.py`；`find_skill_run` 要求脚本的父目录恰好是某个 skill 目录。
- 94 个 skill 的 `SKILL.md` 里以 `python ` 开头的推荐命令共 321 条，全部形如 `python skills/…/<script>.py`，父目录都是 skill 目录；没有 `python -m`、`Rscript`、`cd … &&` 形式的推荐（`Rscript` 只在 4 处作为 skill 内部依赖提到）。
- 15 种写法实测：普通写法、绝对路径、环境变量前缀、`python -u`、`timeout 600 python …`、`… 2>&1 | tail -50`、`conda run -n x python …`、overlay 解释器绝对路径、`mkdir -p out && python …`、`nohup … &`、`--output=out`、反斜杠续行都能识别。识别不了三种：`cd <skill 目录> && python x.py`、`bash -c '…'`、`python -X utf8 …`。

推荐：脚本化 eval 继续不做（维持 0067-Q9）。live eval 里，识别不了的写法落到策略的"含 skill 目录路径却没被识别"或"其余"分支，被拒绝并计入 `unmatched_skill_command`。

理由：脚本化用例的命令是作者写的，漏不掉；漏网写法只会出现在真实模型的输出里。先在 live 报告里数它出现多少次、是哪几种，再决定是否扩展 `_script_of`。

成本：H-D 里约 20 行。

若以后要做：在 `_script_of` 里处理 `cd <dir> &&` 前缀、`bash -c` 的内层字符串、`python -X <opt>` 与 `-W <opt>`。三者都只改 `stubs.py`，各配一条 `test_stubs.py` 用例。

### L4 打桩依赖私有 `bash._locally`

现状证据：`BashTool.execute` 在调用时按模块全局名解析 `_locally`（`tools/builtin/bash.py:676`）；`tests/evals/test_stubs.py` 的钉子测试会在改名或改成绑定时失败。公开 seam 是 `BashEnvironment`（`bash.py:390`），`build_app` 只从 sandbox binding 取（`assembly.py:1240`）；传入后工具描述换成 `local=False` 的版本（`bash.py:609`），审批理由从 "directly on this machine, with no OS isolation" 换成 "in this session's injected execution environment"（:740-742），系统提示的 sandbox 一节也会变。

推荐：不做。

代价对比：

| 方案 | 生产代码改动 | eval 看到的提示词 | 改名时 |
|---|---|---|---|
| 现状：monkeypatch `_locally` + 钉子测试 | 无 | 与生产一致 | 钉子测试报错 |
| `build_app(bash_environment=)` | 加一个参数与透传 | 工具描述、审批理由、sandbox 一节都和生产不同 | 不受影响 |
| `_locally` 改名为公开的 `run_locally` 并写进文档 | 改名与文档 | 与生产一致 | 仍是 monkeypatch，只是名字不太会被随手改 |

理由：第二种让 eval 测的提示词和生产不一样，违背 0067 选生产装配的初衷；第三种得到的保护钉子测试已经给了，为测试改生产代码的名字不划算。

### L5 重试退避 1 s 不可调

现状证据：`EngineConfig.generate_retry_base = 1.0`（`engine/config.py:112`）；`retry.py` 的 `_positive()` 把 0 或负数换成 1.0；`AppConfig.engine_config()`（`entry/config.py:686-695`）只传 `max_turns` 与 `tool_timeout`，docstring 写着 "Two fields cross over and no more"。整个用例集约 1.5 s，其中约 1 s 是 `transient_error_retried` 的退避。

推荐：不做。

理由：收益是每次少 1 s。代价是给 `AppConfig` 加一个只有测试用的字段，并打破 `engine_config()` 的约定；另一条路（Runner 按 `app` 重建引擎）等于在 eval 里复制一段装配。0067-Q5 已接受这 1 s。

### L6 压缩用例 `trigger_tokens` 手估

现状证据：
- `test_compaction.py`：`large_result_offloaded` 为 `Headroom(WARN, 4, 2600)`，`summary_replaces_head` 为 `Headroom(FULL, 4, 4700)`。
- `runner.py` 的 `headroom_budget` 取 `U = floor((B + G) / t)`，检查 `B / U < warn_at` 与 `(B + G) / U < t'`。
- 干跑实测（关压缩，两次结果相同，每条 10 至 30 ms）：

  调用编号从 0 起计，与 `Headroom.trigger_call` 一致（`case.py:42-43`：在这次调用之前到达目标档位）；调用 0 的量就是 `B`，两条用例的 `trigger_call` 都是 4。

  | 用例 | `B`（调用 0） | 调用 1 至 5 相对 `B` 的增长 |
  |---|---|---|
  | `large_result_offloaded` | 10,266 | 调用 1：2,129；调用 2：2,311；调用 3：2,493；调用 4（触发）：2,675；调用 5：2,751 |
  | `summary_replaces_head` | 10,265 | 调用 1：182；调用 2：364；调用 3：546；调用 4（触发）：4,796 |

- 重跑审核的 `hole2.py`（在 prompt 后加填充词抬高 B）：

  | B | `summary_replaces_head` | `large_result_offloaded` |
  |---|---|---|
  | 11,865 至 13,965（5 档） | 通过，压缩记录只有一条 `full`、写回 | 通过 |
  | 14,165 | 失败，首条是可读的 `headroom_infeasible: the first call would already be at WARN (B=14165, G=4700, U=23581, …)` | 通过 |

- 机制：触发前的调用即使落进 `WARN`，`WARN` 档只 offload 大结果；`summary_replaces_head` 触发前只有三次小读，没有可 offload 的内容，这次压缩不写回，用例也不在意。`FULL` 目标真正的约束就是首次调用低于 `WARN`：`B / U < 0.6` 且 `U = (B + G) / 0.8`，即 `B < 3G`，按配置的 `G = 4700` 是 14.1k，现有检查已经把它报成可读的失败。
- `G` 是脚本造成的增长（表格读回的量），和系统提示多长无关。系统提示变长只会抬高 `B`，碰到 14.1k 时首次调用检查会直接说明。`G` 只在两种情况下失准：改了用例脚本，或改了 token 估算器。
- 现在缺的检查：压缩确实发生在第 `trigger_call` 次调用之前，而不是更早写回。现有用例靠 `SentContains(..., call=4)` 与压缩记录的计数间接覆盖，但没有一条统一的、能直接说明原因的检查。

推荐：只做事后检查 `headroom_missed`；自动标定延后。

理由：第 1 版以为的漏洞不存在，自动标定要解决的"系统提示变长后失准"也不会发生（`G` 与 `B` 无关）。它剩下的收益只是省掉用例作者估一次 `G`，而估错时首次调用检查或事后检查都会报出来。事后检查约 15 行，能把"压缩发生得太早"变成一条直接可读的失败。

成本：约半天；`runner.py` 约 15 行、测试约 30 行、文档与 docstring 修正。

方案：
1. `runner.py`：`trigger_call` 从 0 起计，意思是"在调用 `trigger_call` 之前到达目标档位"。收到写回的 `COMPACTION` 帧（`written_back` 为真）时，若此刻 `len(provider.calls) < trigger_call`（压缩发生在比调用 `trigger_call - 1` 更早的调用之前），记 hard failure `headroom_missed`，消息给出当时的 `len(provider.calls)`、档位与 `B`、`G`、`U`。`len(provider.calls) == trigger_call` 是预期的位置。
2. 文档与 docstring：`eval.md` §1.6 与 `Headroom`、`headroom_budget` 的 docstring 写清楚"首次调用低于 `WARN`"对 `FULL` 目标意味着 `B < 3G`，以及 `WARN` 在没有可 offload 内容时不写回；`test_compaction.py` 模块 docstring 里"the call before it stays below WARN"改为"no compaction writes back before the trigger call"。
3. `test_runner.py`：一条人为让压缩提前写回的用例，断言出现 `headroom_missed`。

若以后要做自动标定：Runner 先用 `dataclasses.replace(case, compaction=False, headroom=None, assertions=())` 在另一个临时目录干跑，量出第 0 至 `trigger_call` 次调用的 token `T0 … Tk`；触发前的约束写成"低于第一个会写回的档位"，对 `FULL` 目标就是低于 `soft_at`，不再是 `warn_at`；在可行区间里取中点。按这个约束，`summary_replaces_head` 不需要再加表格。代价约 1 天与 80 行，干跑每条多几十毫秒；收益是作者不用估 `G`。在出现第三条压缩用例、或估算器改动导致手估值反复失准之前，不值得做。

### L7 `eval.yml` 未在真实 GitHub Actions 上跑过

现状证据：0067 §9.3 只在本地 venv 模拟了 job2；job1 的白名单在 CI 模拟 venv 里只跑了已知失败涉及的文件（0067 §9.4）。owner 已决定 0067-Q11 的对外动作暂不动。`actions/setup-python` 的 `cache: pip` 默认按 `**/requirements.txt` 计算缓存键（实施时以 action 文档核实），仓库里只有 `skills/literature/requirements.txt` 能匹配，缓存键不随 `pyproject.toml` 变化。

推荐：只写验证步骤，标注"需 owner 同意后执行"（H-F）。本地能做的准备放在 H-A1 与 H-E3。

理由：推送、开 PR、改坏用例看 CI 变红都是对外可见的动作。

### L8 30+ 测试文件各自的假 provider

现状证据：`async def generate(` 的实现分布在 33 个测试文件（`tests/entry` 18、`tests/engine` 8、`tests/ensemble` 2、`tests/launch` 2、`tests/observability` 2、`tests/provider` 1）。`tests/entry` 里替换 `assembly.provider_from_env` 的有 14 个文件：`test_approval_card`、`test_assembly`、`test_ensemble_golden`、`test_ensemble_wiring`、`test_hook_wiring`、`test_memory_wiring`、`test_open_app`、`test_permission_wiring`、`test_planning`、`test_sandbox`、`test_subagent_wiring`、`test_telemetry_wiring`、`test_turn`、`test_turn_runner`。这种写法六个消费者都拿得到假 provider。只有 `test_telemetry_wiring.py:277` 用事后 `dataclasses.replace(app, provider=...)` 再由 `_engine_over` 重建引擎，所以它的阻塞路径 span 树里没有 `llm_request`；`test_assembly.py:910` 的 `dataclasses.replace` 是有意测"冻结的 app 可以被替换"。

推荐：不批量迁移，维持 0067 的裁定。只改 `test_telemetry_wiring.py` 的那一个测试（H-A4）。

理由：换注入方式或换成 `ScriptedProvider` 不会让任何测试多覆盖一行生产代码。`test_telemetry_wiring.py:277` 是唯一因为注入方式而少测了东西的地方。

成本：H-A4 约 20 行。

### L9 CI 相关遗留

a. desktop HTTP 测试在 CI 被跳过

现状证据：
- `tests/launch/test_surfaces.py` 在工作树里有 `no_web_server` fixture（:314-325），三个会走到依赖检查的 desktop 测试都用了它，属于未提交改动。
- 实测：`OmicsClaw` env（fastapi 0.136.1）里整个文件 149 passed，1.04 s。
- job1 白名单不含 `tests/launch`。
- `tests/entry/test_desktop_*.py` 共 12 个文件，靠 `importorskip` 跳过；0067 §9.3 实测最小 venv 加装 `fastapi httpx uvicorn` 后 563 passed、3 skipped。
- 0067 记录的不装 fastapi 的唯一理由就是挂住（0067 §3.11，"刻意不装 `fastapi`"一条）。之后 owner 在 0067 偏差 11 里明确要求删掉已经加上的 `desktop-http` job。
- `eval.yml` 与 `eval.md` §3 仍写着"装了它会挂住"。

推荐：先修正这两处过时说法（H-A1、H-A2）。owner 已明确撤回 0067 的裁定（Q4a，§7.0）：job1 加装 `fastapi httpx uvicorn`，desktop HTTP 测试随 job1 运行，不新增 job（H-E1）。

理由：0064 时全路由 422 的 bug 就是因为 CI 跳过这些测试才没被发现（0067 R3）。挂住已经不存在，技术上的成本只剩安装三个包和多跑约 560 条测试。

b. 两条非 strict 的 `env` 已知失败：维持，owner 已接受。

c. 白名单外的旧测试：owner 2026-09-30 决定在本计划内清理（Q8b），盘点见 §3.1，阶段见 H-H。

现状证据摘要：`tests/runtime/` 24 个测试文件里 10 个因为 `omicsclaw.skill` 已删而收集失败或全部失败，另有 `tests/test_skill_runner_contract.py`（76 条全失败）、`tests/routing/test_consensus_interpret_hint.py`（9 条全失败）等。生产代码一侧，`omicsclaw/runtime/` 能部分导入，但 4 个在 index 里的 skill 依赖其中不能导入的 `run.py`，`--help` 都跑不起来（§3.1 第 3 部分）。这部分生产代码的去留交给 owner（PQ1 至 PQ5）。`test_grammar.py` 的失败是 0067 引入的回归，不属于旧测试，放在 H-A5 修。

d. 白名单外、属于框架层的测试目录：`tests/launch`（316 条）、`tests/attachments`（19 条）、`tests/ensemble`（560 条）不在 job1 白名单里，也不是旧测试；`tests/bot` 没有测试。`tests/launch` 里的 `test_grammar.py` 正是因为不在 CI 里，0067 弄坏它时没人发现（B3）。owner 已定把 `launch` 与 `attachments` 加进 job1，`ensemble` 延后（Q5a）；H-H 之后若改为跑 `tests/` 全量，ensemble 会一并进来，见 PQ5。

### L10 其它缺陷与覆盖空白

发现的事实问题（H-A 修正）：
1. `eval.yml` 的注释与 `eval.md` §3 关于 fastapi 挂住的说法过时（L9-a）。
2. `tests/launch/test_grammar.py::test_the_process_entry_points_in_the_tree_are_the_named_ones` 失败：`omicsclaw/evals/report.py`、`omicsclaw/evals/stubs.py` 有 `__main__` 入口，没登记进 `MODULE_GUARDS`（本版单跑确认）。
3. `tests/entry/test_assembly.py::test_a_scripted_provider_can_be_substituted_after_assembly` 的 docstring 第一句是 "The seam :func:`build_app` does not offer as a parameter"；0067 之后 `build_app(provider=)` 已经存在。
4. `eval.md` §5 最后一条有错字（"它们，还没迁移"）。
5. `eval.md` §1.6 与 `test_compaction.py` 的 docstring 对压缩约束的说法（L6，归 H-B）。

候选用例的算账：只加"必须经过生产装配才可能坏"的用例。

| 候选 | 单元测试现状 | 装配层可能怎么坏 | 推荐 |
|---|---|---|---|
| `safety/protected_dotenv_asked_in_auto_mode` | `tests/permission/` 覆盖受保护路径 | `build_app` 给权限门的工作区根或规则文件路径错了，受保护路径会漏判；`dangerous_bash_asked_in_auto_mode` 只证明了危险命令分支 | 做 |
| `error_handling/unknown_tool_is_observation` | `tests/tools/test_registry.py:179-198` 只测 registry 本身 | 未知工具名不会经过 `GatedTool`（门只包已注册的工具，`permission/gate.py:454`、`:672`），直接由 registry 返回 `is_error`；空白在于没有引擎或装配层的测试证明这条观测回到模型、循环继续 | 做 |
| `safety/subagent_approval_reaches_session` | `tests/entry/test_subagent_wiring.py`（:288、:569、:615、:663）覆盖委派、收窄 registry 与结论回传 | sub-agent 的工具审批走 `tools/context.py:645-660` 的 `current_context().approval`，由 `ChildRunner`（`entry/subagent.py:264-281`）继承的 registry 与策略决定；若这条通道没接到会话，审批要么抛 `ApprovalUnavailable`，要么绕过会话。H-D 的审批策略依赖 sub-agent 的请求也到达会话 | 做 |
| `tool_calling/task_delegates_to_subagent`（第 1 版的 H-C3） | 同上 | 与 `test_subagent_wiring.py` 重复 | 不做 |
| `safety/child_env_has_no_control_token` | `tests/tools/test_bash_child_environment.py` 已用真实 `bash` 断言 | 装配不改子进程环境 | 不做 |
| `skill_routing/misspelled_name_suggests` | `use_skill` 单元测试 | 8 条 `skill_routing` 用例已证明 `use_skill` 挂着真实 index | 不做 |
| web 工具在 `DEFAULT` 模式要审批 | `test_web_fetch.py`、`test_web_search.py` 断言 `ApprovalMode.ASK` | `ask_mode_denial_blocks_write` 已证明 `DEFAULT` 模式下 ASK 策略经过装配生效 | 不做 |
| MCP | `tests/mcp/`、`tests/tools/test_mcp_tool.py` | Runner 不走 `open_app`，要起假 MCP 服务并改 Runner，成本高 | 不做 |
| channel、desktop 表面 | `test_channel_runtime.py`、`test_desktop_*` | Runner 已经像表面一样驱动 `SessionRegistry` | 不做 |

三条新用例的要点（H-C）：
- `safety/protected_dotenv_asked_in_auto_mode`：auto-approve 下 `write_file(".env", ...)` 出 `write_file`、`high` 的审批卡（0067 附录 B.1 已确认），脚本拒绝，`.env` 不存在。断言 `PermissionRequested("write_file", approved=False)`、`ToolResultContains("write_file", "not approved", is_error=True)`、`fs_changes` 里没有 `.env`。
- `error_handling/unknown_tool_is_observation`：脚本调用 `no_such_tool`，得到 `is_error` 观测，内容列出可用工具，下一轮收敛。断言 `ToolResultContains("no_such_tool", …, is_error=True)`、`NoError`、`StopReasonIs(converged)`、`CountIs(len(approvals), 0)`。
- `safety/subagent_approval_reaches_session`：`permission="ask"`。主线第 1 轮调用 `task`（参数按 `task` 工具的 schema，实施时核对）；sub-agent 共享同一个 `ScriptedProvider`，它的第一轮调用 `bash("ls")`；会话上出现 `APPROVAL_REQUIRED`，脚本拒绝；sub-agent 收到拒绝观测后写结论；主线收敛。断言 `PermissionRequested("bash", approved=False)`、`CountIs(len(approvals), 1)`、`ToolResultContains("task", <结论文本>)`、`NoError`。
- `test_dataset_floor.py` 的 `BASELINE` 从 26 调到 29；类别都在现有 8 类里。


### 3.1 旧测试盘点（H-H 的依据）

范围：`tests/` 下 job1 白名单（含 H-E 加入的 `launch`、`attachments`）以外的全部测试文件，白名单内因依赖已删模块而失败的文件（盘点结果：没有，见下），以及 `testpaths` 与 skill 目录里和已删模块有关的测试。

方法（2026-09-30，未跑全量）：
- 失败状态：本版对 `tests/runtime/**`、`tests/routing/`、`tests/test_skill_runner_contract.py`、`tests/test_bot_n_epochs_routing.py`、`tests/test_control_plane_documentation_contract.py`、`tests/test_discover_file_trust.py` 逐个文件单跑（rapids 环境），结果与 0067 附录 B.3 那次全量的逐文件统计一致；其余文件的通过数取自那次全量日志（`scratchpad/baseline_rapids.txt`，按文件解析），pip 最小环境的差异取自附录 B.2 的日志。失败原因对混合结果的文件用 `--tb=line` 单跑确认。
- 被测模块：scratchpad 脚本解析每个测试文件 import 的 `omicsclaw.*`、`skills.*` 模块并逐个尝试导入；另对 `omicsclaw/runtime/` 与 `omicsclaw/routing/` 的每个子模块做了导入检查。
- skill 目录：对 53 个 `skills/**/tests` 目录做 `--co`（474 条、2 个收集错误）；对 3 个 consensus 相关的 skill 测试目录单跑；对 5 个依赖已删框架模块的 skill 脚本跑 `--help`。

1. 生产模块的可导入性

| 模块 | 状态 | 原因 |
|---|---|---|
| `omicsclaw.runtime.consensus` 下 12 个模块（`continuous_scoring`、`explain`、`integration_panel`、`member`、`operators`（除 `lca_r`）、`plan`、`planners`、`scoring`、`source_registry`、`sources`、`spatial_metrics`、`spatial_panel`） | 可导入 | 顶层不依赖已删模块；`plan.py:93`、`:154` 在函数内延迟导入已删模块，调用到才失败 |
| `omicsclaw.runtime.consensus` 下 10 个模块（`continuous_driver`、`continuous_report`、`dispatch`、`driver`、`narrative`、`operators.lca_r`、`report`、`run`、`team`、`templates`） | 不可导入 | 链条最终落到两处顶层 import：`runtime/workflow/fan_out.py:25`（`omicsclaw.skill.resource_scheduler`）与 `runtime/consensus/operators/lca_r/wrapper.py:25`（`omicsclaw.skill.execution.environment`） |
| `omicsclaw.runtime.workflow` | 不可导入 | 同上，`fan_out.py:25` |
| `omicsclaw.runtime.output_styles` | 可导入 | 框架里没有代码 import 它，只在 `entry/cli/__init__.py:30` 的 docstring 里被提到 |
| `omicsclaw.routing`（`router`、`llm_router`、`consensus_interpret_hint`） | 包不可导入 | `llm_router.py:10`、`:17` import 已删的 `omicsclaw.providers`；单个文件按路径加载时 `router`、`consensus_interpret_hint` 本身能载入。框架里没有代码 import 这个包 |

延迟导入的已删模块另有：`runtime/consensus/run.py:248`（`omicsclaw.skill.registry`）、`runtime/workflow/fan_out.py:322`（`omicsclaw.skill.runner`）、`runtime/consensus/narrative/extractor.py:72` 与 `synthesizer.py:42`（`omicsclaw.providers.chat_completion`）。

谁在用：`omicsclaw/ensemble/` 与框架其它包都不 import `omicsclaw.runtime.*` 或 `omicsclaw.routing`（grep 只命中 docstring）。用它的是 skill：

| skill（均在 index 里） | 依赖 | `--help` |
|---|---|---|
| `sc-consensus-clustering` | `omicsclaw.runtime.consensus.run`（顶层） | `ModuleNotFoundError: No module named 'omicsclaw.skill'` |
| `sc-consensus-integration` | 同上 | 同上 |
| `sc-consensus-pseudotime` | 同上 | 同上 |
| `consensus-domains`（spatial） | 同上 | 同上 |
| `consensus-interpret`（spatial） | `_llm.py:79` 在函数内 import 已删的 `omicsclaw.providers.chat_completion` | 正常；`--no-llm` 路径可用，LLM 路径一调用就失败；它的 skill 测试 81 passed、2 skipped |

也就是说，系统提示的 skill 索引向模型宣传了 4 个一跑就崩的 skill。这是生产问题，不属于测试清理，去留见 PQ1、PQ4。

2. 测试文件逐个分类

分类：(a) 被测代码已删或不可导入，删测试；(b) 被测代码在，测试过时，改测试；(c) 被测代码在，测试暴露真 bug，修代码或进已知失败清单；(keep) 被测代码在、测试通过，只是不在 CI；(PQ1) 取决于 PQ1 的裁定。

| 文件 | 被测模块 | 模块状态 | 结果（rapids） | 分类 | 依据 |
|---|---|---|---|---|---|
| `tests/test_skill_runner_contract.py` | `omicsclaw.skill.evolution`、`.execution.env_resolver` 等 7 个 | 已删 | 76 failed | a | 全部 import 已删模块 |
| `tests/test_bot_n_epochs_routing.py` | `omicsclaw.skill.execution.argv_builder`、`.registry` | 已删 | 4 failed | a | 同上 |
| `tests/test_discover_file_trust.py` | `omicsclaw.services.path_validation` | 已删 | 收集错误 | a | 同上 |
| `tests/test_control_plane_documentation_contract.py` | 读 `docs/design/conversational-control-plane.md`、`docs/CONTEXT.md`、`docs/adr/*` | 后两者已删，前者描述旧架构 | 7 failed、3 passed | a | 失败的 7 条读已删文档；通过的 3 条钉的是旧控制面设计文档，和当前栈无关 |
| `tests/runtime/preflight/test_sc_batch.py` | `omicsclaw.skill.preflight.sc_batch` | 已删 | 10 failed | a | 同上 |
| `tests/routing/test_consensus_interpret_hint.py` | `omicsclaw.routing.consensus_interpret_hint` | 包不可导入 | 9 failed | a（生产代码随 PQ3） | 包 `__init__` 拉 `llm_router` → 已删的 `omicsclaw.providers` |
| `tests/bot/` | 无 | 只剩 `__pycache__` | 无测试 | a | 删目录 |
| `tests/runtime/tools/` | 无 | 只有 `__init__.py` | 无测试 | a | 删目录 |
| `tests/runtime/consensus/test_continuous_driver.py` | `continuous_driver`、`continuous_report` | 不可导入 | 9 failed | PQ1 | 删代码则 a；修代码则成为修复的验收测试 |
| `tests/runtime/consensus/test_driver.py` | `driver`、`operators.lca_r` | 不可导入 | 12 failed | PQ1 | 同上 |
| `tests/runtime/consensus/test_integration_panel.py` | `driver` | 不可导入 | 收集错误 | PQ1 | 同上 |
| `tests/runtime/consensus/test_lca_wrapper.py` | `operators.lca_r.wrapper` | 不可导入 | 收集错误 | PQ1 | 同上 |
| `tests/runtime/consensus/test_plan_narrative.py` | `dispatch`、`narrative.extractor` | 不可导入 | 收集错误 | PQ1 | 同上 |
| `tests/runtime/consensus/test_report_panel_diagnostics.py` | `report` | 不可导入 | 收集错误 | PQ1 | 同上 |
| `tests/runtime/consensus/test_run_entry.py` | `run` | 不可导入 | 收集错误 | PQ1 | 同上（`test_run_entry.py:17` → `run.py:28` → `driver.py:69` → `workflow/__init__.py:11` → `fan_out.py:25`） |
| `tests/runtime/consensus/test_team_runtime.py` | `dispatch`、`team` | 不可导入 | 收集错误 | PQ1 | 同上 |
| `tests/runtime/consensus/test_templates.py` | `dispatch`、`driver` | 不可导入 | 收集错误 | PQ1 | 同上 |
| `tests/runtime/workflow/test_fan_out.py` | `workflow.fan_out`、`consensus.team` | 不可导入 | 收集错误 | PQ1 | 同上 |
| `tests/runtime/consensus/test_planners.py` | `planners`（可导入）、`run`、`workflow` | 部分不可导入 | 4 failed、14 passed | PQ1 | 4 条失败都经 `plan.py:93` 或 `fan_out.py:25` 落到 `omicsclaw.skill` |
| `tests/runtime/consensus/test_continuous_planner_reader.py` | 同上 | 部分不可导入 | 2 failed、8 passed | PQ1 | 2 条失败落到 `fan_out.py:25` |
| `tests/runtime/consensus/test_spatial_panel.py` | `spatial_panel`（可导入）、`driver` | 部分不可导入 | 3 failed、9 passed | PQ1；3 条失败本身是 b | 3 条失败是 "async def functions are not natively supported"（仓库不装 pytest-asyncio，应改 `asyncio.run`） |
| `tests/runtime/consensus/test_spatial_metrics.py` | `spatial_metrics` | 可导入 | 4 failed、9 passed | PQ1；4 条失败是环境 | 失败是 scanpy 要 `igraph`，rapids 环境没装；与 `tests/ensemble/test_spatial_metrics.py` 是两套实现 |
| `tests/runtime/consensus/test_{alignment,categorical_operators,continuous_operators,dlpfc_benchmark,explain,member_scoring,self_consistency,source_registry}.py`（8 个） | 可导入的纯计算模块 | 可导入 | 合计 70 passed、1 skipped | PQ1 | 通过；保留还是随 `runtime` 删掉，取决于 PQ1 |
| `tests/runtime/consensus/test_sc_integrate_cluster.py` | 子进程跑 `skills/singlecell/scrna/sc-integrate-cluster/sc_integrate_cluster.py` | skill 在、可运行 | 1 failed、2 passed | b | 测的是一个活着的 skill，放错了目录；失败是缺 `igraph`（环境）。移到该 skill 的 `tests/` 下，用 `importorskip("igraph")` |
| `skills/spatial/consensus-domains/tests/` | `consensus_domains.py` → `runtime.consensus.run` | 不可导入 | 2 failed | c（随 PQ1） | skill 本身跑不起来 |
| `skills/singlecell/scrna/sc-consensus-clustering/tests/` | 同上 | 不可导入 | 2 failed | c（随 PQ1） | 同上 |
| `skills/spatial/consensus-interpret/tests/` | `consensus_interpret.py` | 可运行（`--no-llm`） | 81 passed、2 skipped | keep；生产问题见 PQ4 | 测试没覆盖 LLM 路径 |
| `skills/singlecell/scrna/sc-cytotrace/tests/test_sc_cytotrace_methods.py` | import `skills.singlecell.scrna.sc_cytotrace` | 该模块路径不存在（目录名带连字符） | 收集错误 | b | 改成按文件路径加载脚本；不在 `testpaths` 里 |
| `skills/singlecell/scrna/sc-drug-response/tests/test_sc_drug_response_methods.py` | import `skills.singlecell.scrna.sc_drug_response` | 同上 | 收集错误 | b | 同上 |
| `tests/test_*.py` 其余 25 个（`env_example`、`genomics_phasing_contract`、`geo_downloader`、`literature_*`（4 个）、`manifest`、`oc_entry_point`、`optional_dependency_constraints`、`output_ownership_contract`、`output_ux`、`plan_slash_command`、`pyproject_thin_pip_layer`、`run_paths`、`sc_ambient_removal`、`sc_batch_integration_preflight`、`sc_preflight`、`sc_standardize_input`、`scrna_console_encoding`、`scrna_method_contracts`、`session`、`setup_env_script`、`user_guidance`、`windows_directory_guard`） | skill 脚本、`pyproject.toml`、打包与入口 | 在 | rapids 全过（`plan_slash_command` 4 条全 skip，实施时确认原因）；pip 最小环境里 `output_ux` 1 条、`sc_ambient_removal` 3 条、`sc_standardize_input` 4 条、`scrna_method_contracts` 4 条失败（缺 scanpy 等） | keep；pip 环境的 12 条是 b | 给这 4 个文件补 `importorskip`，不进已知失败清单 |
| `tests/ensemble/`（36 个文件） | `omicsclaw.ensemble.*` | 在 | 557 passed、3 skipped；3 个文件带 `slow`/`eval` 默认不跑；pip 环境里 `test_tuning_matches_argparse.py` 收集错误（缺依赖） | keep | Q5 定了 ensemble 延后进 CI，见 PQ5 |

白名单内的已知失败（`tests/ci_known_failures.txt` 的 5 条 strict）都不是依赖已删模块造成的，不属于 H-H：其中 `test_ensemble_environment.py::test_a_real_trial_records_its_interpreter`（读不存在的路径）与 `test_install_wiring.py::test_with_run_skill_the_tool_comes_after_it`（挂载顺序已变）是 b，可以在 H-H 顺手改掉并从清单删除；另外 3 条（`cli/_configure.py:482` 读协议没有的属性、第二次压缩、`EMERGENCY` 与 `FULL`）是 c，维持在清单里，不在本计划修。

3. 汇总

| 分类 | 文件数 | 测试条数（rapids） |
|---|---|---|
| a 删测试 | 6 个文件 + 2 个空目录 | 106 条失败、3 条通过、1 个收集错误 |
| PQ1 待定（`tests/runtime/consensus` 与 `workflow`） | 22 | 34 条失败、8 个收集错误、110 条通过、1 skip |
| b 改测试 | 3（`test_sc_integrate_cluster.py` 迁移、两个 skill 测试的 import）+ 4 个补 `importorskip` 的顶层文件 + 2 条可选的白名单已知失败 | 1 条失败、2 个收集错误；pip 环境 12 条 |
| c 修代码 | 2 个 skill 测试目录（随 PQ1）；`consensus-interpret` 的 LLM 路径（PQ4，无失败测试） | 4 条失败 |
| keep | 顶层 25 个、`tests/ensemble` 36 个、`consensus-interpret` 测试 | 全过（pip 环境差异已归入 b） |

---

## 4. 分期与任务

依赖与排期（Q1 至 Q8 已裁定）：

| 顺序 | 阶段 | 工作量 | 前提 |
|---|---|---|---|
| 1 | H-A 事实修正 | 半天 | 无 |
| 2 | H-B 压缩事后检查 | 半天 | 无 |
| 3 | H-C 三条新用例 | 1 天 | 无 |
| 4 | H-H1、H-H2 删 a 类、改 b 类测试 | 1 天 | 无；可与 H-D 并行（文件不重叠） |
| 5 | H-D 真实模型路由 eval | 4 至 5 天 | H-B 之后（少一次 `runner.py` 冲突） |
| 6 | H-H3 `tests/runtime` 与生产代码 | 取决于 PQ1：修复 3 至 5 天；删除约 1 天；移出 index 约半天 | PQ1 至 PQ4 的裁定 |
| 7 | H-H4 CI 范围 + H-E（fastapi、白名单或全量） | 1 天 | H-H1 至 H-H3、PQ5 |
| 8 | H-F 真实 GitHub Actions 验证 | 半天，外加等 CI | owner 同意 |
| 延后 | H-G live nightly | 未估 | 手动运行结果 |

H-E 排在 H-H 之后：H-H 决定了 job1 是扩白名单还是改跑 `tests/` 全量，H-E3 的一次性基线只做一次，放在两者都落定之后。

每个阶段只跑新增测试与直接相关的文件，不跑全量。解释器默认 `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`，desktop HTTP 相关的用 `OmicsClaw` env。开工先记下相关文件已有的失败，验收只看新增失败。

### H-A 事实修正与小修（约半天）

| 任务 | 改动 |
|---|---|
| H-A1 | `.github/workflows/eval.yml`：job1 关于 fastapi 的注释改成事实（desktop HTTP 测试因为没装 fastapi 被 `importorskip` 跳过）；两个 `setup-python` 步骤加 `cache-dependency-path: pyproject.toml` |
| H-A2 | `docs/core-features/eval.md`：§3 最后一段按 H-A1 改；§5 的错字；§5 加一条"`skills/*/tests` 不在 CI 里"（L2） |
| H-A3 | `tests/entry/test_assembly.py::test_a_scripted_provider_can_be_substituted_after_assembly`：docstring 改为只说它测什么，测试体不变 |
| H-A4 | `tests/entry/test_telemetry_wiring.py::test_the_blocking_exchange_really_produces_a_two_level_tree`：改用 `build_app(..., provider=_TwoTurnProvider())`，删掉 `dataclasses.replace` 与 `_engine_over`（若别处不再用）；加断言：两个 `omicsclaw.llm_request`，父链为 `[llm_request, interaction]` |
| H-A5 | `tests/launch/test_grammar.py`：`MODULE_GUARDS` 登记 `evals/report.py` 与 `evals/stubs.py`，说明写各自命令行的用途 |

验收：YAML 能被 `yaml.safe_load` 解析；下列测试除 `tests/ci_known_failures.txt` 里已有的一条外全绿。
测试：`tests/entry/test_assembly.py`、`tests/entry/test_telemetry_wiring.py`、`tests/launch/test_grammar.py`、`tests/evals/test_ci_known_failures.py`。

### H-B 压缩用例的事后检查（约半天）

| 任务 | 改动 |
|---|---|
| H-B1 | `omicsclaw/evals/runner.py`：`headroom_missed`（§L6 方案第 1 条） |
| H-B2 | `omicsclaw/evals/case.py` 的 `Headroom`、`runner.py` 的 `headroom_budget` 与 `arun_case` 的 docstring：写清约束与 `WARN` 不写回的情形，列出新的失败名 |
| H-B3 | `tests/evals/dataset/test_compaction.py`：只改模块 docstring，用例不变 |
| H-B4 | `tests/evals/test_runner.py`：`headroom_missed` 能触发 |
| H-B5 | `docs/core-features/eval.md` §1.3 的失败名表加 `headroom_missed`，§1.6 改写约束，§5 对应一条 |

验收：两条压缩用例照常通过；人为提前写回的单元测试报 `headroom_missed`。
测试：`tests/evals/test_runner.py`、`tests/evals/dataset/test_compaction.py`。

### H-C 三条新用例（约 1 天）

| 任务 | 改动 |
|---|---|
| H-C1 | `tests/evals/dataset/test_safety.py`：`protected_dotenv_asked_in_auto_mode` |
| H-C2 | `tests/evals/dataset/test_error_handling.py`：`unknown_tool_is_observation` |
| H-C3 | `tests/evals/dataset/test_safety.py`：`subagent_approval_reaches_session` |
| H-C4 | `tests/evals/test_dataset_floor.py`：`BASELINE = 29` |
| H-C5 | `docs/core-features/eval.md` §2.1 用例表加三行，"26 个"改为"29 个" |

验收：29 条全过，连续三次结果一致；一次性变异检查（做完即恢复，记进实施记录）：从受保护路径清单里去掉 `.env` 后 H-C1 失败；让 `ChildRunner` 的子 registry 把 `bash` 的策略改成自动放行后 H-C3 失败。
测试：`tests/evals/dataset -m scripted_eval`、`tests/evals/test_dataset_floor.py`。

### H-D 真实模型路由 eval，手动运行（约 4 至 5 天）

| 任务 | 改动 |
|---|---|
| H-D1 | `omicsclaw/evals/case.py`、`runner.py`、`hermetic.py`、`stubs.py`：§L1 方案第 2 条的五处扩展（含 `Case.skill_fallback` 经 `arun_case` 传入 `stubbed_skill_runs`），默认值不改变现有行为 |
| H-D2 | `omicsclaw/evals/live.py`：`RecordingProvider`、种子加载、`live_case`、`routing_policy`、`judge`、`LiveReport`、`compare` 与命令行 |
| H-D3 | `omicsclaw/evals/__init__.py`：按需导出 live 的公开名（沿用 0067 的延迟导入写法）；`tests/launch/test_grammar.py` 的 `MODULE_GUARDS` 登记 `evals/live.py` |
| H-D4 | `tests/evals/fixtures/live_routing_seed.json`：`schema_version` 升到 2，每条加显式 `inputs`（§L1 附表，逐条核实），核实过的种子加 `expected_args`；文件头 `purpose` 同步 |
| H-D5 | `tests/evals/live/conftest.py`、`tests/evals/live/test_live_routing.py` |
| H-D6 | `tests/evals/test_live.py`：`RecordingProvider` 的记录、`replies` 与 `bind`；`routing_policy` 对 §L1 第 6 条表中每种写法各一条测试，外加正常的严格 help、skill 运行、只读命令；兜底桩在无 `--output` 时返回退出码 2 且不执行；`judge` 的各种 `outcome`、`no_skill_called` 的细分、并行 `use_skill`、先读后换；报告与 `compare` 的输出稳定。不写 `eval_results` |
| H-D7 | `tests/evals/test_runner.py`：`network=False` 仍断网；审批策略函数的分支；`Case.skill_fallback` 为 `None` 时行为不变、设了之后无 fixture 的 skill 由它回答。`tests/evals/test_stubs.py`：`fallback` 的行为，含无 `--output` 时退出码 2 |
| H-D8 | `tests/evals/test_fixtures.py`：每条种子都有 `inputs` 字段；`expected_args` 的参数出现在对应 `SKILL.md` 里 |
| H-D9 | `docs/core-features/eval.md`：新增一节"真实模型路由 eval"（运行方式、判分、报告、局限），§5 第一条改写；`CONTRIBUTING.md` 讲 marker 的地方补一句 `OMICSCLAW_EVAL_LIVE` |

验收：
- 不设 `OMICSCLAW_EVAL_LIVE` 时 `tests/evals/live` 全部 skip；`pytest tests/evals` 在 rapids 与最小 venv 里都全绿，脚本化 29 条结果不变。
- owner 在 `OmicsClaw` env 里手动跑一次完整 live eval；报告每条种子都有 3 次记录，`error` 次数为 0 或原因明确；实施记录写下总通过率、每域通过率、`no_skill_called` 的细分、`unmatched_skill_command` 的次数与写法、实际 token 量（含缓存命中）与耗时。
- 完整运行前先用 `OMICSCLAW_EVAL_LIVE_TRIALS=1` 只跑 2 条种子（`-k`）做冒烟。

测试：`tests/evals/test_live.py`、`tests/evals/test_runner.py`、`tests/evals/test_stubs.py`、`tests/evals/test_fixtures.py`、`tests/evals/test_evals_is_not_imported.py`、`tests/launch/test_grammar.py`，最后 `tests/evals` 整目录一次。真实运行由 owner 或经 owner 同意后执行，会产生 API 费用。

### H-E CI 覆盖扩展（Q4、Q5 已裁定；在 H-H 之后做）

| 任务 | 改动 |
|---|---|
| H-E1 | owner 已撤回 0067 "不加 desktop-http job" 的裁定（Q4a）：`.github/workflows/eval.yml` job1 的 `pip install` 行加 `fastapi httpx uvicorn`，desktop HTTP 测试在 job1 里跑，不新增 job；job1 的注释改成这样写 |
| H-E2 | job1 的测试范围按 H-H4 的结论：扩白名单（至少加 `tests/launch tests/attachments`，Q5a），或者改为 `pytest tests`（需 PQ5） |
| H-E3 | 在 CI 模拟 venv（0067 §9.3 的做法，带 fastapi 等三个包）里把 job1 最终的范围跑一次，定下已知失败清单。这是 0067 没做的一步，也是 H-F 的前提，只跑这一次 |
| H-E4 | `docs/core-features/eval.md` §3 同步；0067 R3 与本计划 L9-a 的说法改成已处理 |

H-E3 已知的起点：审核在本机跑 `tests/launch` + `tests/attachments`，3 failed、329 passed，380 s。三条失败是 `test_grammar.py` 那条（B3，H-A5 修掉），以及 `tests/launch/test_configure_command.py` 两条与 `tests/launch/test_cli_command.py::test_the_repl_survives_a_backend_it_cannot_reach`。后三条都是子进程撞上 180 s 超时，原因是本机沙箱的网络环境，不是代码问题。处理：这类由环境造成的超时不写进 strict 的已知失败清单；H-E3 在 CI 模拟 venv 里若仍超时，先查它们等的是哪个连接，确属环境问题的按 `| env` 标成非 strict，并在清单里写明原因。另外，这三条每条耗时约 180 s，对 job1 的 `timeout-minutes: 30` 有影响，H-E3 要记下整体耗时。

验收：H-E3 的结果与 `tests/ci_known_failures.txt` 一致（没有未列出的失败，也没有 XPASS）；整体耗时写进实施记录。
测试：H-E3 本身；之后只跑 `tests/evals/test_ci_known_failures.py`。

### H-H 旧测试清理（Q8b；H-H3、H-H4 等 PQ 裁定）

目标：清理之后，`tests/` 下剩下的目录要么都能加进 job1 白名单，要么干脆取消白名单，job1 改跑 `pytest tests -m "not slow and not demo and not eval and not scripted_eval"`。依据是 §3.1 的盘点。

| 任务 | 改动 | 前提 |
|---|---|---|
| H-H1 | 删 a 类：`tests/test_skill_runner_contract.py`、`tests/test_bot_n_epochs_routing.py`、`tests/test_discover_file_trust.py`、`tests/test_control_plane_documentation_contract.py`、`tests/runtime/preflight/`、`tests/routing/`、`tests/bot/`、`tests/runtime/tools/`；`tests/conftest.py:39` docstring 里提到的旧模块按事实改写 | 无（`tests/routing/` 的删除不等 PQ3：包本来就不可导入） |
| H-H2 | 改 b 类：`tests/runtime/consensus/test_sc_integrate_cluster.py` 移到 `skills/singlecell/scrna/sc-integrate-cluster/tests/`，加 `importorskip("igraph")`；`sc-cytotrace`、`sc-drug-response` 两个 skill 测试改成按文件路径加载脚本；`test_output_ux.py`、`test_sc_ambient_removal.py`、`test_sc_standardize_input.py`、`test_scrna_method_contracts.py` 对缺失的重依赖补 `importorskip`；白名单已知失败里两条 b 类（`test_ensemble_environment.py`、`test_install_wiring.py`）改测试并从 `tests/ci_known_failures.txt` 删除 | 无 |
| H-H3 | `tests/runtime/consensus/`、`tests/runtime/workflow/` 与相关生产代码，按 PQ1 至 PQ4 的裁定处理（见 §7.2 各选项对应的改动） | PQ1 至 PQ4 |
| H-H4 | CI 范围：评估并落实"扩白名单"或"取消白名单跑全量"（见下） | H-H1 至 H-H3、PQ5 |
| H-H5 | 文档：`docs/core-features/README.md` 第 52 行关于 `runtime/`、`routing/` 的说法按 H-H3 的结果更新；`eval.md` §3 与 §5 同步；README "What's New" 记一条里程碑 | H-H3 |

H-H4 的评估：
- 取消白名单跑 `tests/` 全量，在 H-H1 至 H-H3 做完后是可行的：剩下的是顶层 25 个文件、`tests/ensemble`、`tests/launch`、`tests/attachments` 与现有白名单目录，rapids 环境里都能通过（§3.1）；pip 最小环境的差异（顶层 4 个文件 12 条、`tests/ensemble/test_tuning_matches_argparse.py` 的收集错误、`tests/launch` 的 3 条 180 s 超时）由 H-H2 的 `importorskip` 与 H-E3 的 `| env` 标注处理。命令行显式传 `tests`，所以 `pyproject.toml` `testpaths` 里的 25 个 `skills/*/tests` 不会进 job1，skill 测试的重依赖不进 CI。
- 代价：全量会包括 `tests/ensemble`，而 Q5 定的是 ensemble 延后，所以要 owner 再确认（PQ5）；job1 多跑约 900 条测试，耗时由 H-E3 实测。
- 若 PQ5 选"继续白名单"，H-E2 只加 `tests/launch tests/attachments`，顶层 `tests/test_*.py` 可以按文件加进去（它们在 rapids 全过）。
- 起草者推荐取消白名单：白名单本身就是 0067 时为了绕开这些旧测试才设的，清理之后它只会让新目录（像 `tests/launch` 这次）默默漏在 CI 外。

验收：
- `pytest --co -q tests` 没有收集错误。
- 按 H-H3 的结果，`tests/runtime/` 要么已删除，要么在 rapids 环境里全过。
- 4 个 consensus skill 的状态与 PQ1 的裁定一致（修好则 `--help` 与各自的 skill 测试通过；移出 index 则 `use_skill` 查不到、`OMICSCLAW.md` 与 `INDEX.md` 的计数同步）。
- H-E3 的一次性运行结果与 `tests/ci_known_failures.txt` 一致。

测试（只跑动过的目录）：H-H1 之后 `pytest --co -q tests`；H-H2 动过的 7 个文件（含两个 skill 测试目录与新位置的 `test_sc_integrate_cluster.py`）、`tests/skillenv/test_ensemble_environment.py`、`tests/skillenv/test_install_wiring.py`、`tests/evals/test_ci_known_failures.py`；H-H3 之后 `tests/runtime/`（若保留）、`skills/spatial/consensus-domains/tests`、`skills/singlecell/scrna/sc-consensus-clustering/tests`、`skills/spatial/consensus-interpret/tests`，以及 PQ1 选移出 index 时的 `tests/skills/`；H-H4 的整体运行就是 H-E3，只做一次。

### H-F 真实 GitHub Actions 验证（需 owner 同意后执行，不自动执行）

每一步都是对外可见的动作，沿用 0067-Q11 的约定：实施者做到这里先问 owner，同意后再动手；owner 决定暂不做时，本阶段保持未完成，`eval.md` §5 继续写"尚未在 Actions 上验证"。

1. 前提：H-A1、H-A5 与 H-E3 已完成；0067 与本计划的改动由 owner 决定如何提交。
2. 【需 owner 同意】推到一个分支，开一个到 `main` 的草稿 PR。检查：job1 在 30 分钟内结束，已知失败显示为 xfail，没有 XPASS；job2 全部用例通过；Step Summary 有每类通过率表；artifact `eval-report-<run_id>` 可下载，保留 30 天；第二次运行时 pip 缓存命中。
3. 【需 owner 同意】在同一个草稿 PR 上推一个故意改坏一条用例的提交，确认 job2 变红、Step Summary 显示该类通过率下降与失败原因；随后撤销这个提交，确认变回绿色。
4. 【需 owner 同意】合并或推送到 `main` 后看一次 `push` 触发的运行，README 徽章显示状态。
5. 任何一步失败：原因与修复记进本计划的实施记录，修好后从失败的那一步重做。

### H-G live eval 的 nightly workflow（延后）

只写设计，等 H-D 手动跑过两三次、owner 认为结果有用之后再议（Q2）。
- 新文件 `.github/workflows/eval-live.yml`：`workflow_dispatch` 加 `schedule`（每日一次），永不作为 PR 的必需检查。
- 需要 owner 在仓库里配 secrets（provider 的 API key）与 variables（provider、model），这是对外动作。
- runner 上没有 skill 依赖，严格 `--help` 会报 ImportError 并干扰对话，CI 下要让 `--help` 也由桩返回一段固定说明（指向 `SKILL.md` 的 CLI 一节）。这与本地运行的行为不同，报告要注明运行模式。
- 报告作为 artifact 保留 90 天；Step Summary 写总通过率与每域通过率。

---

## 5. 测试与验收汇总

1. H-A：YAML 解析；`test_assembly.py`、`test_telemetry_wiring.py`、`test_grammar.py` 恢复为只剩清单内的已知失败。
2. H-B：`headroom_missed` 能触发，两条压缩用例照常通过。
3. H-C：29 条用例全绿，两次一次性变异检查按预期失败。
4. H-D：live 代码有不联网的单元测试，每种已知旁路一条；owner 的一次完整手动运行产出报告。
5. H-E：CI 模拟 venv 的白名单结果与已知失败清单一致。
6. H-F：按 §4 H-F 的步骤，每步经 owner 同意。
7. H-H：`pytest --co -q tests` 无收集错误；`tests/runtime/` 与 4 个 consensus skill 的状态与 PQ1 一致。
8. 全程不跑全量测试，H-E3 的整体运行只做一次。

---

## 6. 风险

| 编号 | 风险 | 处理 |
|---|---|---|
| R1 | SDK 客户端在 `hermetic_env` 里才构造，SDK 自己的环境变量回退看不到 | `api_key` 由 `resolve_config` 显式传入（`anthropic_provider.py:582-583`、`openai_provider.py:469`）；工厂在进入 `hermetic_env` 前调用；其余回退写进局限（§L1 第 12 条），冒烟运行时确认连得上 |
| R2 | live 运行时模型改动 owner 的环境 | §L1 第 6 条的策略与兜底桩；每种已知旁路有测试；工作区是临时目录；`skill_env=probe` 时不挂 `install_skill_deps`（只有 `skill_env=install` 才挂，`assembly.py:347`）；剩余旁路见第 6 条的算账 |
| R3 | 兜底桩让模型在判分点之后看到不真实的输出 | 主指标取第一个执行的脚本或第一次 `use_skill`，都在桩返回之前；报告注明哪些 skill 用的是兜底桩 |
| R4 | 压缩用例的前提以后被新用例打破（例如触发前就有可 offload 的大结果，`WARN` 提前写回） | `headroom_missed` 直接报出发生在第几次调用；`Headroom` 的 docstring 写明约束 |
| R5 | 白名单扩展后，依赖外部连接的测试在 CI 或本地沙箱里撞上 180 s 超时 | H-E3 记下耗时并查清原因；环境造成的超时按 `| env` 标非 strict，不进 strict 清单；`tests/launch` 里 fastapi 相关的挂住已由 `no_web_server` 处理 |
| R6 | live 通过率在模型、温度不变时也会波动 | 报告写明 3 次的分辨率；`compare` 在首行提示 provider、model、base_url 变化；不据此让任何测试失败 |

---

## 7. 待 owner 裁定的问题

### 7.0 owner 裁定（2026-09-30）

- Q1 选 a：读仓库 `.env` 的配置，现在是 deepseek；报告记录 provider、model、base_url。
- Q2 选 a：第一期只手动本地运行，nightly 延后到 H-G。
- Q3 选 a：没有执行任何 skill 脚本即算正确，反问用户单独统计。
- Q4 选 a：owner 明确撤回 0067 的"不加 desktop-http job"裁定（0067 偏差 11）。job1 加装 `fastapi httpx uvicorn`，desktop HTTP 测试在 job1 里跑，不新增 job（H-E1）。
- Q5 选 a：白名单加 `tests/launch`、`tests/attachments`，`tests/ensemble` 延后（H-H4 若改为跑全量，会把 ensemble 带进来，另见 PQ5）。
- Q6 选 a：不引入 LLM judge。
- Q7 选 a：不把 live 报告的基线提交进仓库。
- Q8 选 b：owner 决定在本计划内清理 `runtime/consensus` 等旧测试，不单列 0069（§3.1、H-H）。

### 7.0.1 owner 对 PQ 的裁定（2026-09-30）

- PQ1 选 c：4 个依赖 `omicsclaw.runtime.consensus.run` 的 skill（`sc-consensus-clustering`、`sc-consensus-integration`、`sc-consensus-pseudotime`、`consensus-domains`）先移出 index，`OMICSCLAW.md` 与 `INDEX.md` 的计数同步；删掉 `tests/runtime/consensus`、`tests/runtime/workflow` 里失败或收集错误的测试，保留 8 个测纯计算模块、能通过的文件。`omicsclaw/runtime/` 的代码不删不修，去留等 ensemble 路线图走到 consensus 时再定。
- PQ2 随 PQ1：`omicsclaw/runtime/output_styles.py` 保留不动。
- PQ3：删除 `omicsclaw/routing/`，同步改 `docs/core-features/README.md` 的阅读约定。
- PQ4 选 b：`consensus-interpret` 默认走 `--no-llm`，LLM 路径明确报"不可用"。
- PQ5：维持 Q5 的原裁定。H-H4 不改为跑 `tests/` 全量，job1 继续用白名单：加 `tests/launch`、`tests/attachments`，顶层 `tests/test_*.py` 可按文件加入，`tests/ensemble` 延后。

### 7.1 原问题与推荐（保留备查）

每题列选项、起草者推荐、审核推荐；两者一致时合并写。

#### Q1 真实模型 eval 用哪个 provider 和模型
- a. 用仓库 `.env` 解析出的配置（现在是 deepseek），可用 `OMICSCLAW_EVAL_LIVE_PROVIDER/MODEL` 覆盖。
- b. 固定一个模型写进代码。
- c. 多个模型做矩阵。

推荐 a（起草者与审核一致）：测的是 owner 实际给用户用的组合。报告记录 provider、model、base_url，换了 `compare` 会提示。c 的费用和耗时按模型数成倍增加。

#### Q2 真实模型 eval 的触发方式
- a. 第一期只手动本地运行（H-D）；nightly 延后到 H-G。
- b. H-D 同时建 nightly workflow，需要 owner 配 secrets。

推荐 a（一致）：手动运行能用本机完整的 skill 环境，`--help` 行为和生产一致；nightly 要对外配置密钥，还要为 CI 改 `--help` 的处理。

#### Q3 `no_skill` 种子怎么判分
- a. 没有执行任何 skill 脚本即算正确，允许调用 `use_skill` 读 `SKILL.md` 后判断没有合适的 skill。
- b. 一次 `use_skill` 都不调才算正确。

推荐 a（一致）。审核补充：反问用户的情形在报告里单独列出（§L1 第 7 条的 `asked_user`）。

#### Q4 是否撤回 0067 "不加 desktop-http job" 这一裁定所涉及的事
0067 实施时加过 `desktop-http` job，owner 明确要求删掉（0067 偏差 11）。在 job1 里加装 `fastapi httpx uvicorn` 虽然不新增 job，效果仍是让 desktop HTTP 测试在 CI 里跑，所以这是一次撤回，需要 owner 明确同意。
- a. 撤回：job1 加装三个包，`tests/entry/test_desktop_*` 随 job1 运行。
- b. 维持：CI 继续跳过 desktop HTTP 测试。

起草者推荐 a。0067 记录的不装 fastapi 的唯一理由（0067 §3.11）是 `tests/launch/test_surfaces.py` 会挂住，这在工作树里已由 `no_web_server` 修好，`tests/launch` 也不在白名单；成本是三个包和约 560 条测试（最小 venv 实测全过）。审核意见：技术上 a 成立，但必须由 owner 明确撤回原裁定，不能由计划默认。

#### Q5 job1 白名单是否扩展
- a. 加 `tests/launch`（316 条）与 `tests/attachments`（19 条）。
- b. 在 a 的基础上再加 `tests/ensemble`（560 条）。
- c. 不扩。

推荐 a（一致）。证据：`tests/launch/test_grammar.py` 正是因为不在 CI 里，0067 弄坏它时没被发现（B3）。审核的条件：先由 H-A5 修好 `test_grammar.py`，再处理三条 180 s 超时的测试（H-E3），`ensemble` 延后。

#### Q6 真实模型 eval 是否引入 LLM judge（是否重议 0067-D2/D9）
- a. 不重议，live eval 只用轨迹判分。
- b. 为 live eval 单独引入 LLM judge，评回答质量（harness9 调研 P1 的做法：每次只评一条标准，要求 JSON 输出）。

推荐 a（一致）：第一期判的是"选没选对 skill"，轨迹里就有确定的答案；judge 本身也要调、要验，会让范围翻倍。

#### Q7 live 报告的基线是否提交进仓库
- a. 不提交，owner 保留本地报告，用 `compare` 对比。
- b. 提交 `tests/evals/fixtures/live_routing_baseline.json`，改动路由相关内容时在 PR 里一并更新。

推荐 a（一致）：结果随模型和日期变化，提交进仓库会制造没有意义的 diff。

#### Q8 白名单外的旧测试
- a. 单列计划，本计划不处理。
- b. 并入本计划作为 H-H。

当时推荐 a；owner 选了 b（§7.0）。`test_grammar.py` 的失败是 0067 的回归，不属于旧测试，放在 H-A5。

### 7.2 新问题：H-H 涉及的生产代码（待 owner 裁定）

这些项目的依据都在 §3.1。计划不替 owner 决定，H-H3、H-H4 在裁定前不动。

#### PQ1 `omicsclaw/runtime/consensus` 与 `omicsclaw/runtime/workflow`，以及依赖它们的 4 个 skill
现状：22 个 consensus 模块里 10 个不可导入，`workflow` 不可导入，断点只有两处顶层 import（`workflow/fan_out.py:25`、`consensus/operators/lca_r/wrapper.py:25`），另有 6 处函数内的延迟导入（`plan.py:93`、`run.py:248`、`fan_out.py:322`，以及 `plan.py:154`、`narrative/extractor.py:72`、`narrative/synthesizer.py:42` 三处 LLM 调用）。框架里没有代码 import `omicsclaw.runtime`，`omicsclaw/ensemble` 也不 import；依赖它的是 `sc-consensus-clustering`、`sc-consensus-integration`、`sc-consensus-pseudotime`、`consensus-domains` 四个 skill，它们在 index 里，但 `--help` 就报 `ModuleNotFoundError: No module named 'omicsclaw.skill'`。
- a. 修复：把上面几处改接到现有栈（skill index `omicsclaw.skills`、ensemble 的执行层、`provider_from_env`），4 个 skill 恢复可用，`tests/runtime/` 的 22 个文件成为修复的验收测试（spatial_panel 的 3 条 async 测试改成 `asyncio.run`）。约 3 至 5 天，另要一个装齐 R/igraph 的环境跑 skill 测试。
- b. 删除：删 `omicsclaw/runtime/consensus`、`omicsclaw/runtime/workflow`、4 个 skill 及其测试、`tests/runtime/`；更新 `OMICSCLAW.md` 的路由表与计数（singlecell 34 → 31、spatial 19 → 18）、两个域的 `INDEX.md`。约 1 天。
- c. 先移出 index：代码留着，4 个 skill 暂时不让 `use_skill` 查到（例如目录改成 `_` 开头，`OMICSCLAW.md` 写明"不是 skill"），`tests/runtime/` 里失败与收集错误的文件删掉，通过的 8 个保留；以后按 ensemble 路线图决定修还是删。约半天。
- d. 生产代码不动，只删或 xfail 测试。

起草者推荐 c：d 会让系统提示继续向模型宣传 4 个一跑就崩的 skill，这是现在就有的用户可见故障；a 和 b 都牵涉 consensus 在 ensemble 路线图里的定位（owner 记忆：consensus 已降为 ensemble 的组件），不宜在一个 eval 计划里定。c 先止住故障，也不丢代码。

#### PQ2 `omicsclaw/runtime/output_styles.py`
能导入，框架里没有代码 import 它（只在 `entry/cli/__init__.py:30` 的 docstring 里被提到）。
- a. 随 PQ1 的结果处理（PQ1 选 b 就一起删）。
- b. 单独删掉。
- c. 保留。

起草者推荐 a。

#### PQ3 `omicsclaw/routing/`
包不可导入（`llm_router.py:10`、`:17` import 已删的 `omicsclaw.providers`），框架与 skill 都不 import 它，`docs/core-features/README.md` 已写明它只作历史参考；唯一的测试 `tests/routing/` 在 H-H1 删除。
- a. 删掉整个包，同步改 `docs/core-features/README.md` 第 52 行与 `entry/cli/__init__.py:32` 附近提到它的 docstring。
- b. 保留在磁盘上作历史参考。

起草者推荐 a：留着的包 import 就报错，只会让以后的盘点再查一遍；历史可以从 git 找回。

#### PQ4 `skills/spatial/consensus-interpret/_llm.py:79`
这个 skill 在 index 里，`--no-llm` 路径可用，skill 测试 81 passed；但 LLM 路径在函数内 import 已删的 `omicsclaw.providers.chat_completion`，一调用就失败。
- a. 改接 `provider_from_env`（或 skill 自带的 HTTP 调用），补一条 LLM 路径的测试（用假 provider）。
- b. 默认改成 `--no-llm` 行为，LLM 路径报一条清楚的"暂不可用"。
- c. 不动。

起草者推荐 b 作为本计划内的最小改动，a 留给 ensemble/consensus 的后续计划；这是 skill 代码，改动要符合 0062 的 skill 边界（skill 可以 import 框架的公开 API，框架不 import skill）。

#### PQ5 H-H 之后 job1 是否取消白名单、改跑 `tests/` 全量
- a. 取消白名单，job1 跑 `pytest tests -m "not slow and not demo and not eval and not scripted_eval"`；这会把 `tests/ensemble` 带进 CI，等于把 Q5 定的"ensemble 延后"提前。
- b. 保留白名单，只加 `tests/launch`、`tests/attachments` 与顶层 `tests/test_*.py`，ensemble 按 Q5 延后。

起草者推荐 a（理由见 H-H4）：`tests/ensemble` 在 rapids 里 557 条全过，pip 环境只有一个收集错误要补 `importorskip`；白名单留着，以后新加的测试目录会默默漏在 CI 外，`tests/launch/test_grammar.py` 这次就是这样坏掉的。

---

## 8. 实施记录（2026-09-30）

按 §4 的顺序实施：H-A → H-B → H-C → H-H1、H-H2 → H-D → H-H3 → H-H4 与 H-E。H-F 与 H-G 没做。每个阶段只跑计划列出的新增与相关测试。没有提交、没有推送，没有碰 git 索引，删除一律用 `rm`。

### 8.1 文件清单

新建：
- `omicsclaw/evals/live.py`
- `tests/evals/test_live.py`、`tests/evals/live/__init__.py`、`tests/evals/live/conftest.py`、`tests/evals/live/test_live_routing.py`
- `skills/singlecell/scrna/sc-integrate-cluster/tests/test_sc_integrate_cluster.py`、`_synth.py`（从 `tests/runtime/consensus/` 移来）

修改：
- `omicsclaw/evals/`：`case.py`（`CaseProvider` 协议、`ApprovalPolicy`、`Case.approvals` 接受函数、`Case.network`、`Case.skill_fallback`、`Headroom` docstring）、`runner.py`（`headroom_missed`、审批函数分支、`network`、`skill_fallback` 透传、docstring）、`hermetic.py`（`hermetic_env(..., block_network=)`）、`stubs.py`（`stubbed_skill_runs(..., fallback=)`）、`__init__.py`（导出与延迟导入）
- `.github/workflows/eval.yml`：job1 注释改为事实、两个 `setup-python` 加 `cache-dependency-path: pyproject.toml`、job1 加装 `fastapi httpx uvicorn`、白名单加 `tests/launch tests/attachments tests/test_*.py`
- `tests/launch/test_grammar.py`：`MODULE_GUARDS` 登记 `evals/report.py`、`evals/stubs.py`、`evals/live.py`
- `tests/entry/test_assembly.py`（H-A3 docstring）、`tests/entry/test_telemetry_wiring.py`（H-A4：`build_app(provider=)`，删 `_engine_over`，加两条 `llm_request` 断言）
- `tests/evals/`：`test_runner.py`（`headroom_missed`、断网默认、审批函数、兜底桩）、`test_stubs.py`（兜底桩 3 条）、`test_fixtures.py`（种子 `inputs` 与 `expected_args`）、`test_dataset_floor.py`（`BASELINE = 29`）、`dataset/test_safety.py`（2 条用例）、`dataset/test_error_handling.py`（1 条用例）、`dataset/test_compaction.py`（模块 docstring）、`fixtures/live_routing_seed.json`（第 2 版）
- `tests/conftest.py`（`.env` 隔离 fixture 的 docstring 按事实改写）、`tests/ci_known_failures.txt`（删两条 b 类，加一条 `env`，改表头）
- `tests/skillenv/test_ensemble_environment.py`、`tests/skillenv/test_install_wiring.py`（两条 b 类改测试）
- `tests/test_sc_ambient_removal.py`、`tests/test_sc_standardize_input.py`（`importorskip("scanpy")`）、`tests/test_scrna_method_contracts.py`（`importorskip("seaborn")`）
- `skills/singlecell/scrna/sc-cytotrace/tests/test_sc_cytotrace_methods.py`、`skills/singlecell/scrna/sc-drug-response/tests/test_sc_drug_response_methods.py`（按文件路径加载脚本）
- PQ1：4 个 consensus skill 的 `SKILL.md` 改名为 `SKILL.md.disabled`；`OMICSCLAW.md`（spatial 19 → 18、singlecell 34 → 31、"all 94" → "all 90"，写明 `SKILL.md.disabled` 的目录不是 skill）；`skills/spatial/INDEX.md`、`skills/singlecell/INDEX.md`（用 `OMICSCLAW_WRITE_SKILL_INDEX=1` 重新生成）；`tests/sdk/test_bootstrap.py`、`tests/sdk/test_help_probe.py`、`tests/skillenv/test_dependencies_section.py`（94 → 90，help 探针不再有预期失败）；`tests/sdk/test_boundary.py`（B3 注释；B2 与 B3 去掉 `_llm.py`）
- PQ4：`skills/spatial/consensus-interpret/`：`consensus_interpret.py`（默认走结构化路径，新增 `--llm`）、`_llm.py`（默认模型调用抛 `LLMUnavailableError`，消息 `LLM_UNAVAILABLE`）、`SKILL.md`（description、流程、Gotchas、退出码、示例）、`tests/test_cli_smoke.py`（LLM 路径的用例加 `--llm`，新增 2 条）
- PQ3：`omicsclaw/entry/cli/__init__.py` 的 docstring、`docs/core-features/README.md` 的阅读约定
- 文档：`docs/core-features/eval.md`、`docs/core-features/agent-skills.md`（计数）、`CONTRIBUTING.md`、`README.md`、`README_zh-CN.md`（计数与 What's new）

删除：
- H-H1：`tests/test_skill_runner_contract.py`、`tests/test_bot_n_epochs_routing.py`、`tests/test_discover_file_trust.py`、`tests/test_control_plane_documentation_contract.py`、`tests/runtime/preflight/`、`tests/routing/`、`tests/bot/`、`tests/runtime/tools/`
- H-H3：`tests/runtime/workflow/`；`tests/runtime/consensus/` 里 13 个失败或收集错误的文件（`continuous_driver`、`driver`、`integration_panel`、`lca_wrapper`、`plan_narrative`、`report_panel_diagnostics`、`run_entry`、`team_runtime`、`templates`、`planners`、`continuous_planner_reader`、`spatial_panel`、`spatial_metrics`），保留 §3.1 列出的 8 个
- PQ3：`omicsclaw/routing/`（删除前 grep 过，只有 `entry/cli/__init__.py` 的 docstring 提到它）

### 8.2 与计划的偏差

1. PQ1 c 的"目录加 `_` 前缀"不可行：`omicsclaw/skills/loader.py` 只跳过 `.` 开头的目录和 `__pycache__`、`node_modules`，`_` 开头的目录照样被扫描、被索引。改用"`SKILL.md` 改名为 `SKILL.md.disabled`"：加载器只认 `SKILL.md` 这个文件名，目录和脚本原地不动，改回原名即恢复，不需要改加载器，也不会像 `.` 前缀那样挪动路径。代价是 `tests/sdk/test_bootstrap.py` 的规范引导块检查不再覆盖这 4 个脚本（`main_scripts()` 按 `SKILL.md` 找脚本）。
2. `test_output_ux.py::test_spatial_genes_help_does_not_require_scanpy_runtime` 没有补 `importorskip`：这条测试要证明的正是"没装 scanpy 时 `--help` 能跑"，补了 `importorskip("scanpy")` 它就只在测不出问题的环境里运行。它在 pip 环境失败是真问题（`spatial_genes.py` 第 29 行在模块顶层 import scanpy），改为写进 `tests/ci_known_failures.txt` 的 `| env` 条目并注明原因。skill 代码没改，见 §8.5。
3. `test_scrna_method_contracts.py` 在 CI 模拟 venv 里本来就通过（CI 装了 seaborn），失败只出现在最小 venv，缺的是 seaborn 而不是 scanpy，所以补的是 `importorskip("seaborn")`。
4. `test_sc_integrate_cluster.py` 的 `importorskip("igraph")` 只加在需要 Leiden 的那一条上：另两条（Harmony 的 PCA 复用、单 batch 报错）不用 igraph，模块级跳过会把它们一起跳掉。它依赖的 `_sc_integration_synth.py` 一并移过去，改名 `_synth.py`，按文件路径加载（仓库用 `--import-mode=importlib`，同目录模块不能直接 import）。
5. `test_install_wiring.py` 的断言改为"`run_skill` 在 `install_skill_deps` 之前、末尾三个是 `optimize_params, install_skill_deps, task`"，因为 ensemble 现在在 `run_skill` 之后还挂 `optimize_params`。`test_ensemble_environment.py` 的那条在测试里把 `runner.repo_root` 设成仓库根：fake skill 放在 `tests/ensemble/` 下，`AppConfig.repo_root()` 由 `skills_dir` 推出，指到了 `tests/ensemble`。
6. `headroom_missed` 在 Runner 看到 `COMPACTION` 帧时读 `len(provider.calls)`。帧晚到只会让次数偏大，所以这条检查可能漏报、不会误报；两条压缩用例实测读到的都是 4，连跑 5 次一致。
7. H-D 的判分与报告放在 `live.py` 一个文件里，另有 `TrialRecord`、`SeedReport`、`to_dict`、`markdown`、`run_meta`、`trial_record` 几个辅助名，计划没有逐一列出。策略拒绝的类别多了 `help_not_strict`（`--help` 被识别但不是严格形式，例如 `--help && pip install foo`）：计划表里这类落到"其余"，单列出来是为了不把它们算进 L3 需要的 `unmatched_skill_command`。
8. 兜底桩在脚本不存在时也返回退出码 2、不记失败（计划只写了缺 `--output` 的情形），避免模型拼错脚本名时整条命令真实执行。有 fixture 的 skill 缺 `--output` 时仍按原规则记 `stub_target_missing`，在 live 报告里作为 `harness_failures` 列出。
9. 可选的"live 桩放行 help 前再按严格规则复查"没有做：策略在 `_locally` 之前完成，旁路测试已经覆盖。
10. 种子输入按 `SKILL.md` 核对后改了三处：`proteomics__peptide_identification` 与 `proteomics__lfq_quantification` 用 `data/peptides.csv`，`proteomics__ptm_sites` 用 `data/phospho_sites.csv`（两个 skill 的文档都用 csv）。`genomics__alignment_qc` 保留 `data/sample.bam`：query 写的是 BAM，skill 只读文本 SAM，模型需要自己处理这个差别。`expected_args` 只填了三条（harmony、celltypist、liana）；`bulkrna-de`、`bulkrna-coexpression`、`metabolomics-xcms-preprocessing` 没有 `--method` 参数，不填。
11. job1 白名单另外加了顶层 `tests/test_*.py`（PQ5 允许按文件加入，这里用 glob 一次加全）。
12. `tests/conftest.py` 的 docstring 按事实改写：原文说 `omicsclaw.runtime.agent.state` 与 `omicsclaw.routing.llm_router` 在 import 时加载 `.env`，前者已不存在，后者随 PQ3 删除；现在把 `.env` 读进进程环境的是 launch 在启动 surface 时调用的 `load_env_file`。
13. PQ4 的"默认走 `--no-llm`"做成：新增 `--llm` 开关，不带它时走结构化路径（`--no-llm` 保留，含义相同）；带 `--llm` 时走原 LLM 路径，默认模型调用抛 `LLMUnavailableError`（退出码 6），消息写明这个版本没有模型客户端。skill 的 description 相应改了一句（它是路由用的文字），两个 domain 的 `INDEX.md` 重新生成。
14. 计划里 H-E3 的起点（`tests/launch` 三条 180 s 超时）这次没有复现：三条都在约 3.3 s 内通过，所以没有加 `| env` 条目。

### 8.3 测试命令与结果

解释器默认 `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`。"CI 模拟 venv"是 scratchpad 里 0067 建的 `venvci`（job1 的整张 pip 列表），本次加装了 `fastapi httpx uvicorn`；"最小 venv"是 `venv311`（只有 `pip install -e . pytest`）。

| 阶段 | 命令 | 结果 |
|---|---|---|
| H-A | `tests/entry/test_assembly.py tests/entry/test_telemetry_wiring.py tests/launch/test_grammar.py tests/evals/test_ci_known_failures.py`；`yaml.safe_load(eval.yml)` | 98 passed、1 xfailed（清单里的 `test_this_layer_reads_no_provider_attribute_the_protocol_omits`）；YAML 可解析 |
| H-B | `tests/evals/test_runner.py tests/evals/dataset/test_compaction.py`；`headroom_missed` 那条连跑 5 次 | 12 passed；5 次一致 |
| H-C | `tests/evals/dataset -m scripted_eval` 连跑 3 次；`tests/evals/test_dataset_floor.py` | 每次 29 passed（约 1.6 s）；5 passed |
| H-C 变异 | 去掉 `gate.py` 里的 `DOTENV_NAME` 检查；`ChildRunner._child_registry` 把 `bash` 的 `approval_mode` 改成 `AUTO`（均从 scratchpad 备份恢复） | 前者 `protected_dotenv_asked_in_auto_mode` 失败（没出审批，`write_file` 自己的 `PathIsSensitive` 仍然拒绝写入）；后者 `subagent_approval_reaches_session` 失败（没有审批请求） |
| H-H1 | `pytest --co -q tests` | 7389/7407 collected，无收集错误 |
| H-H2 | `tests/skillenv/test_ensemble_environment.py tests/skillenv/test_install_wiring.py tests/evals/test_ci_known_failures.py tests/test_output_ux.py tests/test_sc_ambient_removal.py tests/test_sc_standardize_input.py tests/test_scrna_method_contracts.py` 与三个 skill 测试目录（rapids） | 77 passed、1 skipped（缺 igraph 的那条），662 s（skill 测试真实计算） |
| H-H2 | CI 模拟 venv 与最小 venv 里的 4 个顶层文件（改之前） | 定位失败原因：CI venv 8 条缺 scanpy，最小 venv 另 4 条缺 seaborn |
| H-H3 | `tests/runtime tests/skills tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py` 与 3 个 consensus 相关的 skill 测试目录 | 590 passed、4 skipped、4 failed（`consensus-domains` 与 `sc-consensus-clustering` 各 2 条，skill 代码没修，符合 PQ1 c） |
| H-H3 | `tests/skillenv/test_dependencies_section.py`；`OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python ... -m slow tests/sdk/test_help_probe.py` | 100 passed；1 passed（90 个脚本的 `--help` 全部返回 0） |
| H-H3 | `tests/ensemble/tuning/test_a3_prompt.py` | 1 failed、3 passed，见 §8.5 |
| H-D | `tests/evals/test_live.py tests/evals/test_stubs.py tests/evals/test_runner.py tests/evals/test_fixtures.py tests/evals/test_evals_is_not_imported.py tests/launch/test_grammar.py` | 全部通过（`test_live.py` 42 条，OmicsClaw env 里 `test_live.py` + `test_stubs.py` 58 passed） |
| H-D | `tests/evals/live`（不设 `OMICSCLAW_EVAL_LIVE`；以及 `-m eval`） | 26 deselected；26 skipped |
| H-D | `tests/evals` 整目录（rapids 与最小 venv） | 各 167 passed、26 deselected |
| H-E3 | CI 模拟 venv，job1 最终白名单一次（`-m "not slow and not demo and not eval and not scripted_eval" -p no:cacheprovider`，CI 的空 key 与 `OTEL_ENABLED=false`） | 6847 passed、42 skipped、6 xfailed，无 XPASS，无失败，349 s |

H-E3 之后的已知失败清单（`tests/ci_known_failures.txt`）：
- strict：`tests/entry/test_assembly.py::test_this_layer_reads_no_provider_attribute_the_protocol_omits`、`tests/entry/test_session.py::test_a_second_compaction_extends_the_first_instead_of_restarting`、`tests/entry/test_turn.py::test_the_system_message_survives_a_successful_summarization`
- env：`tests/sdk/test_banksy_fallback.py::test_missing_banksy_and_missing_sub_env_raise_env_not_found`、`tests/skillenv/test_overlay_real.py::test_the_overlay_sees_the_base_and_uses_the_base_pip`、`tests/test_output_ux.py::test_spatial_genes_help_does_not_require_scanpy_runtime`（新增）

### 8.4 live 冒烟

先在 OmicsClaw env 里跑了 `tests/evals/test_live.py` 与 `tests/evals/test_stubs.py`（58 passed），确认审批策略与兜底桩生效，再跑一次冒烟：

```bash
OMICSCLAW_EVAL_LIVE=1 OMICSCLAW_EVAL_LIVE_TRIALS=1 OMICSCLAW_EVAL_REPORT_DIR=<scratchpad>/live-smoke \
/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:randomly -m eval tests/evals/live \
  -k "bulkrna__deseq2 or singlecell__batch_harmony"
```

- provider `deepseek`，model `deepseek-v4-flash`，base_url `https://api.deepseek.com`，temperature 0.3（`.env` 解析结果）。
- 2 条种子各 1 次，2 passed，35 秒。两条都判为 `correct`：`bulkrna__deseq2` 第一次 `use_skill` 是 `bulkrna-de`（5 次模型调用），`singlecell__batch_harmony` 是 `sc-batch-integration`（3 次）。两条都没有在 6 轮内执行脚本，所以 `executed_skill` 为空、`args_ok` 为空。
- token：输入 116,186（缓存命中 95,616），输出 3,134，8 次模型调用。
- 策略拒绝 2 条命令，都是 `not_permitted`：`ls -la; echo "---"; ls -la data/ ...; head -3 data/counts.csv ...` 和 `ls -la data/ 2>&1; python -c "import anndata, scanpy; ..."`。都是探查输入文件的写法，被拒的原因是 `;` 与重定向。没有 `unmatched_skill_command`，没有 harness failure。
- 完整的 26 × 3 没有跑，留给 owner 手动触发。

### 8.5 需要 owner 决定的新问题

1. `tests/ensemble/tuning/test_a3_prompt.py::test_the_pinned_prompt_is_the_development_prompt` 现在失败：`golden/a3_dev_prompt.txt` 是 0057 开发运行时见到的系统提示，里面有这 4 个 consensus skill 和 `consensus-interpret` 的旧 description。更新 golden 会让"与开发运行时的提示逐字相同"不再成立；不更新则这条测试一直红。`tests/ensemble` 不在 CI 里，本次没有改 golden。
2. `consensus-interpret` 的 description 仍然让模型"use consensus-domains or sc-consensus-clustering"，而这两个已移出 index；它的输入是 consensus 运行的结果，现在只能来自旧运行。`sc-integrate-cluster` 的 description 也说自己"normally fanned out as a member of sc-consensus-integration"。是否改这两段路由文字、或把 `consensus-interpret` 一并移出 index，需要 owner 决定。
3. `skills/spatial/spatial-genes/spatial_genes.py` 在模块顶层 import scanpy，`--help` 在没有 scanpy 的环境里失败（`test_output_ux.py` 那条测试本来就在防这个）。现在记为 `env` 已知失败；修 skill 代码不在本计划范围。
4. 冒烟里模型的探查命令（带 `;`、`2>&1`、`python -c`）都被策略拒绝，6 轮内两条种子都没走到执行脚本。完整运行时这会压低 `executed_skill` 的比例，主指标退回 `first_use_skill`。是否放宽只读规则（例如允许 `2>&1`），或把 `max_turns` 调高，等完整运行的数据出来再定。
5. `tests/runtime/consensus` 保留的 8 个文件和 `tests/ensemble` 一样不在 job1 白名单里；要不要加进去，按 PQ5 的精神由 owner 定。

### 8.6 仍待 owner 的对外动作（H-F）

- 推到分支、开到 `main` 的草稿 PR，检查 job1 在 30 分钟内结束（本地模拟约 6 分钟）、已知失败显示为 xfail、job2 全过、Step Summary 与 artifact、第二次运行的 pip 缓存命中。
- 在草稿 PR 上推一个故意改坏用例的提交，确认 job2 变红后撤销。
- 合并或推到 `main` 后看一次 `push` 触发的运行与 README 徽章。
- 手动跑一次完整的 live eval（26 × 3），把总通过率、每域通过率、`no_skill_called` 细分、`unmatched_skill_command` 的次数与写法、实际 token 与耗时补进本节。
