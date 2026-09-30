# 计划 0054 — `ask_user`：工具在执行中向人要一个答复

**状态**：第三版（2026-09-23）。经独立审核、架构审核与 harness9 对照，owner 按推荐裁定，已据此返工。第四轮收敛审核后修订（第三版修订：任务 D 的 `was_seen` 与 owner 第四轮裁定第 4 项、问题卡按宽度折行、禁词核实、§3.5.3 与 §3.6.2 措辞、原语校验归属）；第五轮审核与 owner 裁定（2026-09-24）后再修订（`QUESTION_ASKED` 经 `inert_prose`、问题卡改走 `inert_body`、折行标记、Channel 上截断即不出卡、行号）。待 owner 过目。未写任何生产代码。

**依赖**：A 随时可做。**B 依赖 0052 T1**（抽出会合原语 `Rendezvous` 到 `entry/rendezvous.py`、
`TurnHandle` 持有审批与提问共用的编号计数器、加 `TurnEvent.subagent`；本计划字段追加其后，裁定
10）与缺陷修复 E1（`entry/display.py`，函数已在工作树）。C 依赖 B 与已扩展的 `Repl._read_card`
（架构 S2，已在工作树）。D 是桩，严格排在 0052 T3（desk 与 `entry/replies.py`）之后补写。

**引用**：审核记录 `docs/reviews/2026-09-23-plans-0047-0052-0053-0054.md`。"裁定 n"指 owner
2026-09-23 第 n 条；"审核""接缝"指第一轮的"0054 审核""接缝审核"；"架构"指第二轮；"对照 X"指
第三轮 harness9 表中的行。行号以 2026-09-23 工作树为准并附符号名；未落地的名字（`Rendezvous`
的方法、desk 的 `ReplyHandler`）以落地后为准。逐条处置见 §10。

## 0. 缘起

0029 留下两个未决项（`docs/plans/0029-foundation-tools.md:509`、`:512`、`:741-743`）。owner
裁定：**保留 `ask_user`**，本计划只做这一件；**放弃 `glob_files` / `grep_files`**，由 `bash` 承担。

## 1. 目标

| # | 目标 | 验收口径 |
|---|---|---|
| G1 | 内置工具 `ask_user`：模型在执行中向人提**一个**问题，同一交换内拿到回答后继续 | 脚本化 provider 调 `ask_user`，测试经 `TurnHandle.answer` 作答，工具结果进入 `TurnOutcome.history` |
| G2 | CLI REPL 呈现问题并收集回答：编号选项、多选、自由文本、跳过；Ctrl-C 取消交换而不退出 REPL | CLI 测试（含按键路径）+ 真实 pty 手工验收 |
| G3 | 结果送不到人的入口不提供该工具：`--prompt` / `--prompt-file`、非 TTY stdin、Desktop、任务 D 落地前的 Channel（裁定 9） | **唯一防线**是 launch 的 `surface_config`（§3.6.1）：这些入口交给 `open_app` 的配置 `ask_user is False` 并记一条 info。直接调 `build_app` / `open_app` 的组合根按配置原样挂载 |
| G4 | 等人的时间不计入 `tool_timeout`；期限沿用 `approval_timeout_s`（CLI 默认 `None` 即一直等；Channel 必有期限）；到期返回 `no_answer` 而非错误；本交换一次超时后不再等 | 暂停、期限、短路测试 |
| G5 | Channel 上 Telegram、Feishu、Slack、Discord、DingTalk、QQ 以文本回复作答，经 0052 的 desk；Email 规则另定 | 任务 D（桩） |
| G6 | 一个开关整体关掉：`AppConfig.ask_user` / `--ask-user` / `OMICSCLAW_ASK_USER`；B 默认关，C 翻为开（审核 M1） | 配置与挂载测试 |
| G7 | `read-only` 下可用；`auto-approve` 不代答；工具本身不走审批；`ApprovalBroker` 行为与接口不变（裁定 7 已放宽） | 权限接线测试；本计划不改 `entry/approval.py`、`entry/rendezvous.py`，`test_approval.py` 零 diff |

---

## 2. 现状

- **工具通道**：`ToolContext`（`tools/context.py:253-294`）只有 `approval`、`progress`、`values`；
  `use_tool_context`（:336-368）替换而非合并；生产代码的重新绑定点三处：`turn.py` `_session_bound`
  （:339）与 `TurnRunner.run`（:532）、`TaskTool.execute`（`subagent/task_tool.py:160`）。样板是
  `require_approval`（:571-667），等待包在只停表的 `pause_tool_timeout()` 里。`validate_arguments`
  不查 `minItems` / `maxItems` / `minLength`；`test_tools_is_a_leaf_layer.py` 钉住依赖方向与 `__all__`。
- **审批 broker**：`ApprovalBroker`（`entry/approval.py:84-257`）今天独自实现整套会合（私有计数
  `_issued` → `f"{turn_id}#{n}"`、future 表、`_decide` 期限、取消先删挂起项、只结算一次、同步
  `abandon`、`pending()`），0052 T1 将抽成 `Rendezvous`。`TurnHandle.__init__` 建 `self.approvals`
  （`turn.py:826`），`approve`（:838）；lane 泵以 `approval=handle.approvals` 构造 `TurnRunner`
  （`session.py:764-775`）；`TurnRunner.run` 的 `finally` 判空后 `abandon()`（:576-577）。
- **事件与渲染**：`TurnEventType` 14 个成员，由 `test_events.py` :35 与 :54 两条测试逐个枚举；
  `test_render.py` `_one_of_every_type`（:133）覆盖全部类型。`TextRenderer._control_line`
  （`render.py:269`）对未处理类型返回 `None`；`to_wire`（:430）末尾 `return {}`；
  `desktop_chat_frame`（`desktop/turn_observation.py:178`）对无名类型返回 `None`，由
  `test_desktop_stream.py` :611 逐类型钉住。
- **显示层**（E1 与第三批修复，已在工作树）：`entry/display.py` 的 `inert_line` 把换行画成
  `LINE_BREAK_MARK`（` ↵ `）；`inert_prose` 保留换行与制表符、不加前缀、不截断；`approval_body`
  渲染审批卡正文：续行以 `CONTINUATION_PREFIX`（`  │ `）开头，理由与参数合计受上限约束，截断处以
  `…` 标出，首行注记按原文计数（规则见 0052 §4.7）；不安全字符统一由 `tools/preview.escape_unsafe`
  转义。`render._approval_line`（:370）用 `approval_body`，`_activity.sanitize` 与 `_transcript` 用
  `inert_line` / `inert_prose`；非工具帧在 `ToolTranscript.render`（`_transcript.py:185`）里是
  `Text(inert_prose(head), style="dim")`。`inert_block` 与 `MAX_BLOCK_*` 已无生产调用者，且计数有
  旧问题（切在行尾时写 "showing 2 of 2"，截断处没有 `…`），任务 B 之前删除（§3.5.3）。
- **CLI**：`Repl._pump`（`_repl.py:1119`）读到 `APPROVAL_REQUIRED` 调 `_ask_human`（:1352：hold、
  另起 Task 跑 `_answer`（:1370）→ `_ask`（:1466）、进 `_asking`、`_forget_asking`（:1391）取回
  异常）。`_read_card(prompt, *, subject, settled_as, refuse)`（:1409）接管全部"没拿到一行"的
  路径，各 `await refuse(reason)` 恰好一次：Ctrl-C → `_INTERRUPTED_REASON` 并 `interrupt()`；EOF
  或取消 → `_NO_OPERATOR_REASON`（:196）；其他异常 → 黄色行
  `Could not ask about <subject>: <error>. <settled_as>.`。`_card`（:319）取最后一个 `#` 之后作
  标签；`_RENDERED_ELSEWHERE`（`_transcript.py:78`）只有 `plan_write`。
- **其他入口**：`start_cli`（`launch/_surfaces.py:518`）；`--prompt` / `--prompt-file` 走 `run_once`
  （`_repl.py:1841`，`ScriptedSource(())`）；REPL 经 `_run_cli` 调 `open_prompt_source()`（:719），
  它自行判定 stdin 是否为 TTY（`_input.py:416-420`），已接受 `interactive=`（:395）；非 TTY 时选
  `StreamSource`，卡片会读走脚本下一行（审核 S8）。Channel 在 0052 T0 后默认期限 600 s；Telegram
  文本处理器带 `~filters.COMMAND`（`telegram.py:258`，审核 S10）。Desktop 无回传端点、不设期限。
- **子代理**：`entry/subagent.py` `_WITHHELD_FROM_SUB_AGENTS: Mapping[str, str]`（:55，"不下发给
  子代理的工具 → 理由"，现有 `plan_write`、`memory_write`）由 `_child_registry` 剔除、
  `_warn_withheld` 按理由告警；`GENERAL_PURPOSE.description` 由 `_general_purpose_description`
  （:99）从映射渲染成 "`<name>`, which `<reason>`"，`test_subagent_wiring.py` :703 按**整词**比对。
- **权限、引擎、记忆**：`read-only` 只拒绝未声明 `read_only` 的工具（`gate.py:293`）。
  `test_permission_wiring.py` :247 `test_the_gate_does_not_change_what_the_model_is_shown` 按**整词**
  断言工具快照不含 `_POLICY_WORDS`（:215）的 7 个词：`gate`、`gated`、`Gated`、`GatedTool`、
  `permission`、`approval_mode`、`prompts_for_itself`（接缝 M10）。匹配对象是全部工具定义经
  `dataclasses.asdict` 后的 JSON，正则 `\b<词>\b`、区分大小写，所以 `delegate`、`investigate` 里的
  `gate` 不算命中（:295 `test_the_policy_word_check_tells_a_leak_from_a_substring` 钉住）。`concurrency_safe=False` 的调用单独成批、按
  消息顺序执行（`executor.py:307`）；`StopReason` 没有"工具要求结束交换"；`render_conversation`
  （`memory/extractor.py:52`）丢掉只有 `tool_calls` 的助手消息（审核 S2）。

---

## 3. 设计

### 3.1 形态：阻塞式的第四条带外通道

```
AskUserTool ─► ask_question ─► ToolContext.question（本交换的 QuestionBroker ─ Rendezvous）
  ─► QUESTION_ASKED（与审批同一条 TurnStream）─► surface 另起 Task 作答 ─► TurnHandle.answer
  ─► 原语结算 Future ─► 工具结果
```

不走带内协议（引擎没有"工具要求结束交换"，Q1）；不复用审批通道（回答不是同意，CLI 的 `s`、
`/auto` 与 Desktop 的 `permission_request` 都会误处理它，裁定 7）。共用的只是**会合机制**（§3.5.1）。

### 3.2 schema：一次一个问题

```json
{"type": "object", "required": ["question"], "additionalProperties": false,
 "properties": {
   "question": {"type": "string", "description": "The whole question, self-contained: the person may read it away from this conversation, on a phone."},
   "options": {"type": "array", "description": "2 to 6 answers to offer when the choice is among known alternatives. Omit for an open question.",
     "items": {"type": "object", "required": ["label"], "additionalProperties": false,
       "properties": {"label": {"type": "string", "description": "Short answer text, at most 80 characters, not a bare number."},
                      "description": {"type": "string", "description": "What choosing it means, if the label does not say."}}}},
   "multi_select": {"type": "boolean", "description": "True when more than one option may be chosen."}}}
```

工具体内自查，违反抛 `ToolArgumentError`：`question` 非空、≤ 2000 字符；`options` 缺省或为空
即开放问题，否则 2–6 个；`label` 非空、≤ 80、大小写折叠后互不相同，**不得是纯数字或数字列表**
（与按编号作答冲突，审核 S5）；`description` ≤ 300；`multi_select` 须带选项。自由文本恒允许。

### 3.3 返回给模型的内容

JSON（`ensure_ascii=False`），`is_error` 为假，**每种结局都带问题原文**（审核 S2）：

```json
{"status": "answered", "question": "…", "selected": ["Leiden"], "reply": "1"}
{"status": "declined", "question": "…", "note": "The person chose not to answer. Do not ask this again in this request; proceed on your best judgement and say what you assumed."}
{"status": "no_answer", "question": "…", "reason": "no answer before the question deadline", "note": "Nobody answered. They may reply later in a new message. Finish what does not depend on the answer, then end your reply by restating the question."}
```

`reply` 是原文，`selected` 是 surface 的解读（自由文本时为空）。无通道时抛 `QuestionUnavailable`，
注册表转成 `is_error`："nobody can be asked in this session; do not call ask_user again, proceed
on your best judgement and state your assumptions"。

### 3.4 tools 层

`tools/context.py` 与审批类型并列（数据类均 `frozen`、`slots`）：`AnswerStatus(StrEnum)` 取
`answered` / `declined` / `no_answer`；`QuestionOption(label, description="")`；
`QuestionRequest(question, options=(), multi_select=False)`；`QuestionAnswer(status, reply="",
selected=(), reason="")`；`QuestionChannel = Callable[[QuestionRequest], Any]`；
`QuestionUnavailable(RuntimeError)`；以及：

```python
async def ask_question(request: QuestionRequest) -> QuestionAnswer:
    """Put *request* to the bound question channel and return its answer."""
```

- `ToolContext` 增字段 `question: QuestionChannel | None = None`，`use_tool_context` 增同名参数，
  仍然替换而非合并。`ask_question` 在 `pause_tool_timeout()` 里等；通道返回 `None` 读作
  `NO_ANSWER`，其他类型抛 `TypeError`。
- 工具 `tools/builtin/ask_user.py`：手写类 `AskUserTool`，`TOOL_NAME = "ask_user"`，**只经
  `ToolContext.question` 与 entry 交互**，不导入 entry。策略 `ToolPolicy(risk_level=LOW,
  approval_mode=AUTO, read_only=True, concurrency_safe=False, allowed_in_background=False)`：提问
  不改任何东西；"能否提问"的卡片没有意义；屏障见 §3.7。`omicsclaw.tools` 导出工具与上述七个名字。

**工具描述**（约束全在这里，不进系统提示；不含 §2 的 7 个禁词，按整词计）：

```text
Ask the person you are working for one question, and wait for the answer.

Use it only when you cannot do the task well without something only they know or decide: which group is the control, which organism or genome build, whether to overwrite an existing report, which of two defensible analyses they want. Look first: a question the data, the files, the metadata or a SKILL.md can answer is not a question for the person.

Do not use it to ask whether you may run a tool (tools that need consent ask for it themselves), to ask whether to continue, or to confirm a plan you could simply carry out. Do not ask about parameters or thresholds a skill's methodology already fixes. Never ask for a password, API key, token or other secret.

Offer 2 to 6 options when the choice is among known alternatives, with a short label each and a description where the label is not enough. Put the option you recommend first and say so in its description. Set multi_select when more than one may apply. The person can always answer in their own words instead.

One question per call. Calls placed after this one in the same message wait for the answer but were decided before it; put anything that depends on the answer in a later message.

The result is JSON with status answered, declined or no_answer, and repeats the question. After declined or no_answer, do not ask the same question again in this request.
```

### 3.5 entry 层

#### 3.5.1 `QuestionBroker`：`entry/question.py`，与 `ApprovalBroker` 并列建在 `Rendezvous` 上

会合机制只有一份，即 0052 T1 的 `Rendezvous[Req, Ans]`：编号（可注入共享计数器）、future 表、
期限（到期由 `on_expired()` 产出答复）、取消先删挂起项、只结算一次、同步
`abandon(answer)` 为每个挂起项发结算帧、`pending()`、`expires_at()`；帧由两个构造回调决定。
`QuestionBroker` 以组合持有它，只加提问特有的策略：

```python
class QuestionBroker:
    """One exchange's outstanding questions to the person, addressable by id."""
    def __init__(self, stream: TurnStream, *, timeout_s: float | None = None,
                 numbering: Iterator[int] | None = None) -> None:
        """Wait up to *timeout_s* per question; draw ids from *numbering*."""
        self._stream, self._closed = stream, False
        self._rendezvous = Rendezvous(stream, asked=self._asked, settled=self._settled,
            on_expired=self._expired, timeout_s=timeout_s, numbering=numbering)
    async def __call__(self, request: QuestionRequest) -> QuestionAnswer:
        """Publish the question and return its answer; no_answer at once when closed."""
        if self._closed:
            return _unanswered(NOT_ASKED_REASON)
        return await self._rendezvous.ask(request)
    def settle(self, request_id: str, answer: QuestionAnswer) -> bool:
        """Answer one outstanding question; return whether it took effect."""
    def abandon(self, reason: str = QUESTION_ABANDONED_REASON) -> None:
        """Settle every outstanding question as unanswered, and ask no more."""
    def pending(self) -> tuple[str, ...]: ...                  # 转发原语
    def expires_at(self, request_id: str) -> float | None: ...  # 转发原语
    def _expired(self) -> QuestionAnswer:
        """Stop asking in this exchange, and answer the expired question."""
        self._closed = True
        return _unanswered(QUESTION_TIMEOUT_REASON)
    # _asked / _settled：以 self._stream 的 id 构造 TurnEvent.question_asked / question_settled
```

- **原语与策略的分界**：`Rendezvous` 里没有"问题"，`QuestionBroker` 里没有 future。提问特有的
  三条都不进原语：(1) 到期答复是 `NO_ANSWER(QUESTION_TIMEOUT_REASON)`，**从不因没人回答而抛**；
  (2) 本交换一旦有问题到期（`_expired`）或被 `abandon`（先置 `_closed` 再
  `_rendezvous.abandon(_unanswered(reason))`），之后的调用立即返回 `NO_ANSWER(NOT_ASKED_REASON)`，
  不发帧、记一条 info（审核 S1；`timeout_s=None` 下也不会永久挂起）；(3) 理由常量
  `QUESTION_TIMEOUT_REASON`、`QUESTION_ABANDONED_REASON`、`NOT_ASKED_REASON` 与审批的
  `TIMEOUT_REASON`、`ABANDONED_REASON` 各自独立（接缝 M15）。
- **id 与审批共用 `#n`**：`numbering` 是 `TurnHandle` 持有的 `itertools.count(1)`（T1 引入），id 同为
  `f"{turn_id}#{n}"`，同一交换内不重号，CLI `_card` 不改即得 `#n`；第二版的 `#q<n>` 与 Q14 删除。
- **与 `ApprovalBroker` 同形**：`settle(request_id, answer) -> bool`、`abandon()`（缺省理由）、
  `pending()`、`expires_at()` 的形状两者一致，runtime 的 `_broker(kind, handle)` 因而不按 kind
  分支；未知或已结算的 id 返回 `False`（0031 Q18）；`abandon` 同步（trap 3b）；只在 loop 线程调用；
  日志只记 id 与 `status`（Q22）；非正期限由 `Rendezvous` 在构造时拒绝（0052 §4.2），`QuestionBroker`
  不再自查。`Rendezvous` 签名取自 0052 第三版 §4.2，原语缺的能力在 T1 补。

#### 3.5.2 `TurnHandle` 与 `TurnRunner`

- `TurnHandle` 增 slot `questions = QuestionBroker(self.stream, timeout_s=approval_timeout_s,
  numbering=<T1 的共享计数器>)` 与 `async def answer(request_id, answer) -> None`（与 `approve`
  对称，内部调 `questions.settle`，无事可结算时记 debug）。
- `TurnRunner.__init__` 增 `questions: QuestionBroker | None = None`，lane 泵传
  `questions=handle.questions`。`run` 绑定 `question=self._questions if self._app.config.ask_user
  else None`（审核 M5 的判空），`finally` 对两个 broker 各自判空后 `abandon()` 一次。
- `_session_bound` 转发 `question=outer.question`，否则 `run_turn` / `stream_turn` 会静默解绑外层通道。

#### 3.5.3 事件与渲染

- `TurnEventType` 在 `APPROVAL_SETTLED` 后加 `QUESTION_ASKED`、`QUESTION_SETTLED`；`TurnEvent`
  末尾（`subagent` 之后）加 `question: QuestionRequest | None`、`answer: QuestionAnswer | None`，
  默认 `None`；构造器 `question_asked`、`question_settled`。问题帧的 `subagent` 恒为空（§3.8）。
- `TextRenderer._control_line`：`QUESTION_ASKED` → `question_card(event.question, event.request_id)`
  加一行 `reply_hint(event.question)`；`QUESTION_SETTLED` 在 `ANSWERED` 时不出字，`DECLINED` 为
  `Skipped [id].`，`NO_ANSWER` 为 `No answer [id]: <reason>`。理由不全是固定常量：CLI `_read_card`
  在输入源抛异常时以 `the terminal could not ask: <error>` 结算，带异常原文；所以 `<reason>` 与第三批
  修复（N1）后 `_control_line` 的其他变量字段一样经 `inert_line`。问题上屏不违反 Q22 规则 1；日志不记。
- **显示层**：问题与选项文本都由模型控制，`question_card` 内部经 `entry/display.py`。原计划的
  `inert_block` 有计数缺陷（切在行尾时写 "showing 2 of 2"，截断处没有 `…`），且已无生产调用者
  （第五轮）。改为：**任务 B 之前**，把 `approval_body` 的正文渲染抽成通用函数
  `inert_body(text, *, max_lines, max_chars, width=None) -> tuple[str, bool]`，配套
  `inert_body_note(text, *, max_lines, max_chars) -> str`，与现有 `approval_body` /
  `approval_body_note` 成对的形状相同。空行折叠、按显示文字截断且不切断转义、截断处的 `…`、按原文计数
  的首行注记、`TALL_APPROVAL_BODY_*` 阈值随之移入；`approval_body` 只负责拼出理由与参数原文再交给它。
  0052 N4 的 `width` 也落在它上面（0052 §4.7）。抽出之后删除 `inert_block` 与 `MAX_BLOCK_*`；上限常量
  是否改为不带 `APPROVAL` 的名字，由实施时定。
- `question_card` 把问题正文与选项行拼成一段文字交给 `inert_body`，上限与审批卡相同
  （`MAX_APPROVAL_BODY_*`）。选项行先各自经 `inert_line` 压成一行，所以截断、注记与折行对问题和选项
  一视同仁；续行带 `CONTINUATION_PREFIX`，伪造不出以 `Approval required [` 或 `Question [` 开头的行。
  问题虽 ≤ 2000 字符，但上限按显示文字计：行数超过上限，或不安全字符写成 `\uXXXX` 后超过字符上限，
  都会截断。CLI 照截断显示、带注记；Channel 上截断即不出卡（任务 D，owner 裁定 2026-09-24）。Channel
  分条投递时，"伪造不出"还要靠按宽度折行（第四轮 N4）：`question_card` 把 `width` 传给 `inert_body`，
  折出来的续段用 `WRAP_PREFIX`（0052 §4.7）；CLI 不传。中和只在这一处，CLI 与 Channel 都经它（对照
  "转义序列"）。
- `to_wire` 与 `desktop_chat_frame` **不加分支**（审核 S3）：前者只剩身份字段，后者返回 `None`。

#### 3.5.4 卡片与回复解读（同在 `entry/question.py`）

卡片编号与回复语法必须一致，所以同在一个模块，CLI 与 desk 共用：

```python
def question_card(
    request: QuestionRequest, ref: str, *, width: int | None = None
) -> tuple[str, bool]:
    """The question headed by *ref* and its numbered options, as inert text, no line over *width*; and whether it was cut."""
def reply_hint(request: QuestionRequest) -> str:
    """How to reply to *request*, worded for its shape."""
def read_reply(request: QuestionRequest, text: str) -> QuestionAnswer:
    """Read a typed reply as an answer to *request*."""
```

`ref` 由调用方给：`TextRenderer` 传 `request_id`，desk 传它的 `#n` 与代码；`width` 只有 desk 传
（0052 §4.7 的换算），`None` 不折行；`TextRenderer` 不看截断标志，desk 看（任务 D）。卡片为
`Question [<ref>]: <question>`，每个选项一行 `  │ <n>. <label> - <description>`（选项行随正文经
`inert_body`，所以带续行前缀）。作答提示由
`reply_hint` 单独给出（desk 的 `Card` 放进 `legend`），按形态（审核 S4）："Reply with an option
number, or in your own words."（单选）、"Reply with one or more option numbers separated by
commas, or in your own words."（多选）、"Reply in your own words."（开放）。`read_reply` 的
`reply` 始终是原文：

| 输入 | 结果 |
|---|---|
| 去空白后为空 | `DECLINED` |
| 有选项，整行是 1..n 的编号（逗号或空白分隔）；单选时恰好一个 | `ANSWERED`，`selected` 为对应 label，去重保序 |
| 有选项，整行（大小写折叠）等于某个 label | `ANSWERED`，`selected=(label,)` |
| 单选给了多个编号、编号越界、其他任何文本 | `ANSWERED`，`selected=()` |

**与 `entry/replies.py`（0052 T3）的边界**（架构 S7）：`replies.py` 收审批作答词表、
`grant_eligible`、`GrantTable`；`question.py` 收 broker、卡片、`read_reply` 与理由常量，不认审批
动词、不碰会话授权；两者互不导入。边界由结构保证：同一会话同一时刻只有一种待决项（`ask_user` 是
屏障，子代理没有它），CLI 按帧类型、desk 按 `kind` 分派。于是问题卡片上的 `y`、`s`、`/auto` 只是
回答原文，审批卡片上的 `1`、`Leiden` 只按审批语义处理。

### 3.6 入口

#### 3.6.1 launch：一处按入口修正配置，stdin 只判定一次（接缝 D6、裁定 9、架构 S8）

0052 T0 在 `launch/_surfaces.py` 建立 `surface_config(config, surface: SurfaceName) -> AppConfig`
（`SurfaceName` 是 T0 定义的 `Literal`，取值即下表第一列，0052 §4.12），作为按入口修正配置的**唯一**位置，由各 `start_*` 在 `resolve_app_config` 之后调用；本计划只给它加行（若 B
先于 T0 落地，由 B 以同名同签名建立，T0 再加 channel 的期限）：

| `surface` | 调用处 | `ask_user` | `approval_timeout_s`（0052 T0） |
|---|---|---|---|
| `repl` | `start_cli`，无 prompt，`interactive` 为真 | B 期间关；C 起保留 | 保留 |
| `once` | `start_cli`，`--prompt` / `--prompt-file` | 关 | 保留 |
| `piped` | `start_cli`，无 prompt，`interactive` 为假 | 关 | 保留 |
| `desktop` | `start_desktop` | 关 | 保留 |
| `channel` | `start_channel` | 任务 D 之前关 | `None` → 600 |

- **stdin 只判定一次**：把 `_input.py:416-420` 的判定原样抽成 `is_interactive(stream=None) -> bool`
  （缺省读 `sys.stdin`，由 `omicsclaw.entry.cli` 导出），`open_prompt_source(interactive=None)` 的
  缺省分支改为调用它，既有调用方不变。`start_cli` 在 `--help` / `--configure` 之后调用它一次，结果
  既选出 `repl` / `piped`，又经 `_run_cli(..., interactive=)` 传给 `open_prompt_source(interactive=)`。
  不新增 `_stdin_is_a_terminal()`；`_stdout_is_a_terminal()` 判的是另一件事，不动。
- 由真改假时**无条件**记一条 info：launch 分不清显式开启与默认值，也不得再读 env 或标志（0031 Q8、
  `test_the_shell_names_no_deployment_flag` 扫描字符串首词，文案不以 `--ask-user` 开头）。

#### 3.6.2 CLI REPL（任务 C）

- `_pump` 读到 `QUESTION_ASKED` 调 `_ask_question`：与 `_ask_human` / `_answer` 平行的一对方法
  （hold、建 Task、进 `_asking`、挂 `_forget_asking`、结束时 release），审批路径不动。
- `_question` 打印图例 `"empty line skips · Ctrl-C cancels the request"`，然后：
  ```python
  line = await self._read_card(
      f"answer [{_card(request_id)}]> ", subject="the question", settled_as="Not answered",
      refuse=lambda reason: handle.answer(request_id, QuestionAnswer(AnswerStatus.NO_ANSWER, reason=reason)))
  ```
  Ctrl-C、EOF、取消、异常的理由与打印都由 `_read_card` 负责（审核 M2、架构 S2），`_question`
  不再写这些分支；返回 `None` 即已结算，否则 `read_reply` 后 `handle.answer`。
- 问题提示符上**没有斜杠命令**：`/data/ref.h5ad` 是自然的回答，`/auto` 也只是文本（§3.5.4）；补全器
  照常列出斜杠命令，在这里选中也只是文本。
- `ToolTranscript.render` 今天对非工具帧返回一个 `Text(inert_prose(head), style="dim")`
  （`_transcript.py:185`）。对 `QUESTION_ASKED` 改为按行返回正常样式（非 dim）的 `Text`，每行同样
  **经 `inert_prose`**，不能例外，否则它会成为唯一不经中和的非工具帧。`inert_prose` 保留换行，所以
  不会像 `inert_line` 那样把换行压成 ` ↵ `；正文已由 `question_card` 中和，再过一遍 `inert_prose`
  不改变文字。`_RENDERED_ELSEWHERE` 加入 `ask_user`。
  `_read_card` 落到同一个 `self._source.read(prompt)`，不按次传 `completer=` / `history=`（会粘住
  后续提示，审核 S13）；补全照常，回答进 `FileHistory`（Q11）。

### 3.7 超时、并行、取消

- 期限是 `approval_timeout_s`（Q5）；`turn_timeout_s` 覆盖整个交换，先到者生效。
- `concurrency_safe=False` 使每次 `ask_user` 单独成批：同一消息里排在前面的调用先运行，排在后面
  的在回答后才运行；两个 `ask_user` 依次呈现；同一时刻至多一个问题，且不与审批并存。
- Ctrl-C 或 `TurnHandle.cancel()` 取消等待，之后的回答是无操作，交换 `cancelled`、history 不变；
  交换中途失败时 `abandon()` 结算，工具不悬挂。

### 3.8 权限与子代理

- `read-only` 下可用；`auto-approve`、`/auto`、`bypass-all` 照常提问、不代答；CLI 的 `s` / `a` 只作用
  于审批；规则 `deny` 得到 `PermissionDenied`、`ask` 先审批再提问，关掉它应当用开关。
- **子代理没有 `ask_user`**（裁定 1、3）：`_WITHHELD_FROM_SUB_AGENTS` 加一项，键取自
  `omicsclaw.tools.builtin.ask_user.TOOL_NAME`，理由"子代理没有可以提问的人"写成以工具为主语的
  英文短语，如 `"asks a person, and a sub-agent has nobody to ask"`，不含 §2 的 7 个禁词与任何工具名
  （都按整词比对：理由会渲染进 `task` 的定义，受 `test_permission_wiring.py` :247 检查；:703 比对工具名）。`_child_registry`、`_warn_withheld` 与描述随之生效，描述不手改；开关为关
  时描述也会提到 `ask_user`（与 `memory_write` 相同）。
- `ChildRunner.delegate` 围绕子引擎的迭代显式绑定 `use_tool_context(approval=outer.approval,
  question=None, progress=outer.progress, values={**outer.values, SUBAGENT_VALUE_KEY: definition.name})`，
  一处覆盖所有委派路径（`TaskTool`、以后的后台与 `@agent`，接缝 M9）。子代理名一并在这里写入，
  0052 §4.10 的归属因此不依赖请求是否经过 `TaskTool`（第四轮建议）。`TaskTool.execute` 不改，它在
  `task_tool.py:163` 写入的同一个值照旧保留。重新绑定点由此变为四处。

### 3.9 开关、挂载、历史

- `AppConfig.ask_user: bool`，B 为 `False`，C 翻为 `True`；`_Option("ask_user", "--ask-user",
  ("OMICSCLAW_ASK_USER",), _as_bool)` 放在 `subagents`（`config.py:713`）旁；同时决定挂载与绑定。
- `foundation_tools`（`assembly.py:295`）在开关为真时把 `AskUserTool()` 追加在 `memory_*` 之后；
  MCP 与 `task` 后移一位，前缀缓存一次性失效。调用方自带 `tools` 时不挂载。
- `.env.example` 第 9 节加 `#OMICSCLAW_ASK_USER=true` 与"无人值守部署设 false"；`:91` 的注释与
  0052 T0 合并为一句（接缝 D7），写明期限也作用于问题；`approval_timeout_s` 的 docstring 同步。
  问答留在轨迹里并写入 `memory.db`，不自动写入长期记忆；日志、审计、遥测不记原文。

### 3.10 模块与依赖方向

| 位置 | 内容 | 只经由 |
|---|---|---|
| `tools/context.py`、`tools/builtin/ask_user.py` | 类型、`ask_question`、工具 | `ToolContext.question`；不导入 entry |
| `entry/rendezvous.py`（T1）；`entry/approval.py` ∥ `entry/question.py` | 原语不认识审批与问题；两个 broker 并列组合它 | 两个 broker 互不导入；`question.py` 与 `replies.py` 互不导入 |
| `entry/display.py`（E1） | 对人显示前的中和 | `question_card` 与 `_approval_line` 共用 |
| `entry/turn.py`、`session.py`、`subagent.py`；`launch/_surfaces.py` | 建 broker、绑定通道、`TurnHandle.answer`、映射加一项；`surface_config` 加行 | launch 经 `omicsclaw.entry.cli.is_interactive` |
| `entry/cli/_repl.py`；`entry/channel/questions.py`（任务 D） | 两个 surface 的呈现与读取 | `_read_card`；desk，结算只在 `runtime.py` |

## 4. 仍需 owner 裁定

无。Q1–Q13 已定（§10）；Q14 随共用计数器消失（§3.5.1）。任务 D 的两项在补写时再定。

## 5. 任务拆分

顺序 **A → B → C**，**D 在 C 与 0052 T3 之后补写**。每个任务结束跑 §9 与整栈。

### 任务 A — tools 层

**改动**：`tools/context.py`（§3.4）；新增 `tools/builtin/ask_user.py`；两处 `__init__` 导出。
**验收**：绑定假通道即可独立使用；分层守卫绿；未绑定时 `is_error`。

| 测试（`tests/tools/test_ask_user.py`、`test_context.py`） | 断言 |
|---|---|
| 参数校验 | 空问题、1 与 7 个选项、大小写不同的重复 label、`"3"` 与 `"1, 2"` 形 label、超长、`multi_select` 无选项 → `ToolArgumentError` |
| 结局 | §3.3 的 JSON 含问题原文、`is_error` 为假；通道返回 `None` → `no_answer`，其他类型 → `TypeError`；无通道 → `is_error` 且含 "do not call ask_user again" |
| 暂停、替换 | 假 `TimeoutPause` 下等待处于暂停；`use_tool_context(approval=…)` 不带 `question` → `None` |
| 策略与描述 | §3.4 策略五项；描述含 "Look first"、"One question per call"、"password"，不含 §2 的 7 个禁词（整词） |

**定点变异**：去掉 `pause_tool_timeout()`；`concurrency_safe=True`；删选项数量自查；无通道返回
`ANSWERED("")`；`None` 读作 `ANSWERED`；结果去掉 `question`；描述写回 "permission"。
**要改的既有测试**：`test_tools_is_a_leaf_layer.py` :436 的公开名清单与 docstring。

### 任务 B — entry 管线、默认关的开关、挂载、子代理、launch

**前置**：0052 T1（`Rendezvous`、共享计数器、`TurnEvent.subagent`）；E1（`entry/display.py`）；
0052 §4.7 的显示层前置步（抽出 `inert_body` 并带上 `width` 与 `WRAP_PREFIX`，删除 `inert_block` 与
`MAX_BLOCK_*`，§3.5.3）。
**改动**：新增 `entry/question.py`；`events.py`；`render.py`；`turn.py`（`TurnHandle`、`TurnRunner`、
`_session_bound`）；`session.py`（lane 泵）；`config.py`（默认 `False`）；`assembly.py`
`foundation_tools`；`subagent.py`（映射加一项、`delegate`）；`cli/_input.py` 抽出 `is_interactive`
并由 `cli/__init__.py` 导出；`launch/_surfaces.py`（`surface_config` 加行、`start_cli` 判定一次
`interactive` 并传给 `_run_cli`、`start_desktop` 的调用；`repl` 行此时也关）。
**验收**：`ask_user=True` 的 app 上，脚本化 provider 发出 `ask_user`，测试从 `handle.observe()`
读到 `QUESTION_ASKED` 并 `handle.answer()`，交换收敛、history 含工具结果；`entry/approval.py`、
`entry/rendezvous.py` 与 `test_approval.py` 零 diff。

| 测试 | 断言 |
|---|---|
| broker 与短路 | 发 `QUESTION_ASKED`；`settle` 结算并发 `QUESTION_SETTLED`；未知或重复 id → `False`；到期 → `QUESTION_TIMEOUT_REASON`；取消后的回答无操作；`abandon` 每项只发一次；一次超时后下一问立即 `no_answer(NOT_ASKED_REASON)` 且不发帧；`abandon` 后的调用在 `timeout_s=None` 下也立即返回 |
| 共用编号 | 同一交换审批、问题、审批依次为 `t#1`、`t#2`、`t#3`；两个 broker 的 `pending()` 互不包含对方的 id |
| 卡片、解读、边界 | §3.5.4 逐行；单选下 "1,3" 与越界编号是自由文本；三种提示随形态变化；`y`、`s`、`/auto` 读作原文；问题正文含 ESC、U+202E、`\x9b` 与 `"\nApproval required [t#9]"` 时，卡片里没有这些控制字符，也没有以 `Approval required [` 开头的行；传 `width` 时（含超长单行问题与超长选项）每行连同前缀都不超过 `width`，原文换行后的行以 `CONTINUATION_PREFIX`、折出的续段以 `WRAP_PREFIX` 开头；超过上限（如 401 行的问题）时截断标志为真、首行带注记、截断处带 `…`，CLI 渲染行照截断显示；`entry/question.py` 与 `entry/replies.py` 互不导入（T3 落地后生效） |
| 事件与渲染 | 16 个成员，新类型是控制帧；`ANSWERED` 的结算帧不出字；`to_wire` 只有身份字段且过 `json.dumps(allow_nan=False)`；`desktop_chat_frame` 返回 `None` |
| 绑定 | 开：工具读到 `handle.questions`；关：不在 `tools_snapshot`、通道 `None`；`run_turn` 路径转发外层通道；`approval=None, questions=None` 的 `TurnRunner` 照常运行 |
| 屏障、权限 | 一条消息里 `read_file`、`ask_user`、`ask_user`：`read_file` 先完成，第二问在第一问结算后才出现；`read-only` 可用；`auto-approve` 下问题照样到通道；`deny` 规则拒绝 |
| 子代理 | 开关为真时子工具表不含 `ask_user`；agent 文件列出它时 warning 带映射里的理由；委派内 `question is None` 而 `approval` 仍是父会话的 |
| launch、配置 | `once`、`piped`、`desktop`、`channel` 与 B 期间的 `repl` 交给 `open_app` 的配置 `ask_user is False` 且各记一条 info，本已为假时不记；`start_cli` 只调一次 `is_interactive`，`open_prompt_source` 收到同一个值；默认 `False`，`--ask-user true` 与 `OMICSCLAW_ASK_USER=true` 生效 |

**定点变异**：`TurnRunner` 无视开关总绑定；`finally` 漏问题 broker 的 `abandon`；`_session_bound`
不转发；`delegate` 不绑 `None`；从映射删掉 `ask_user`；`_expired` 不置 `_closed`；不传
`numbering`（得到 `t#1`、`t#1`、`t#2`）；`question_card` 绕过 `inert_body`；`question_card` 丢掉截断标志（恒返回 `False`）；`surface_config` 漏
`piped`；`start_cli` 不把 `interactive` 传下去；`_control_line` 对 `QUESTION_ASKED` 返回 `None`。
**要改的既有测试**：`test_events.py` 两条；`test_render.py` `_one_of_every_type`；`test_desktop_stream.py`
:611 的参数。`test_subagent_wiring.py` :703 由映射驱动，自动跟随；默认关，挂载相关断言不动。

### 任务 C — CLI 与默认开启

**前置**：B；已扩展的 `_read_card`（§2）。
**改动**：`cli/_repl.py`（`_pump` 分支、`_ask_question` 一对方法、`_question`、提示符与图例常量）；
`cli/_transcript.py`；`config.py` 默认翻为 `True`；`launch/_surfaces.py` 放开 `repl`；`.env.example` 与
`test_env_example.py` `READ_BY_THE_STACK`；README、`CLAUDE.md`、`AGENTS.md` 的 CLI 说明（卡片用法；
回答进历史文件，Q11；开了 `/auto` 又会离开的用户宜设 `OMICSCLAW_ASK_USER=false`，审核 S9）。
**验收**：测试全绿；pty 手工验收：选项作答、自由文本（含 `/` 开头的路径）、一条消息两个问题依次
出现、问题处按 Ctrl-C 取消交换并回到提示符。

| 测试（`tests/entry/test_cli_question.py`） | 断言 |
|---|---|
| 作答 | `2` → 第二个 label；`1, 3` → 两个；句子 → `selected=[]`、`reply` 原文；`/data/ref.h5ad` 与 `y` 都是回答 |
| 跳过与没拿到回答 | 空行 → `declined`，屏上有 `Skipped [`；源读尽 → `no_answer(_NO_OPERATOR_REASON)`；源抛 `RuntimeError` → `no_answer` 且黄色行以 `Not answered.` 结尾；交换都收敛 |
| **Ctrl-C 按键** | 输入源在 `answer` 提示符上抛 `KeyboardInterrupt`：无异常穿出 `asyncio.run`；交换 `cancelled`；REPL 接着回答下一行；history 不含被取消的交换；`not repl._asking` |
| 标签、回收、转写稿 | 同一交换审批 `#1`、问题 `#2`；交换先结束时问题 Task 被取消，无 "never retrieved"；问题里的 ESC 不上屏；`ask_user` 的参数与输出不被预览 |

**定点变异**：空行读作 `ANSWERED("")`；`_question` 改用 `self._source.read` 而不经 `_read_card`
（`KeyboardInterrupt` 穿出、EOF 不结算）；`refuse` 以 `DECLINED` 结算（源读尽用例红）；`/` 开头
按命令处理；不进 `_asking`；从 `_RENDERED_ELSEWHERE` 删掉。
**要改的既有测试（默认翻开引起）**：`test_permission_wiring.py` `MOUNTED`（:49，`memory_write` 与
`task` 之间插入 `ask_user`）；`test_subagent_wiring.py` :590
`test_the_child_inherits_the_rest_of_the_parent_s_table_in_order`（逐字列出的排除集合加 `ask_user`）；
`test_turn.py`、`test_session.py` 压力档测试加 `ask_user=False`（接缝 M11）；B 里"`repl` 也关"的
断言翻转。核对无需改：`test_assembly.py`（前缀断言）、`test_channel_runtime.py`。

### 任务 D — Channel（桩，0052 T3 之后补写）

按 0052 第三版 §4.3 与 §8.2 的契约接入 `RequestDesk`（`entry/channel/desk.py`），补写时以届时代码为准：

- **帧与 broker**：pump 在 `delivered_types` 过滤**之前**把 `QUESTION_ASKED` 交给
  `desk.register(RequestKind.QUESTION, event, session=…, sender=…, surface=…, expires_in_s=…)`，
  `QUESTION_SETTLED` 交给 `desk.settled(request_id, answer)`；二者**不进** `DEFAULT_DELIVERED_TYPES`。
  runtime 的 `_broker(kind, handle)` 加一行 QUESTION → `handle.questions`，结算、`reset_session` 与
  pump 提前退出时的 `abandon()` 都经它（§3.5.1 的同形保证无需分支）。
- **处理器**：新增 `entry/channel/questions.py`（与 `approvals.py` 并列），runtime 构造 desk 时注册
  `QuestionReplies`（`kind = RequestKind.QUESTION`），它实现 `ReplyHandler` 的四个方法：
  `card(pending)` 返回 `Card`，`body` 为 `question_card(request, ref, width=…)` 的正文（宽度按 0052
  §4.7 由 `binding.text_chunk_limit` 换算），`legend` 为 `reply_hint(request)`
  （`mail` 风格改为首行带代码的说明），`undelivered` 为 `NO_ANSWER("the question could not be
  delivered to the person")`。**截断即不出卡**（owner 裁定 2026-09-24，与审批卡一致）：`question_card`
  的截断标志为真时，`card` 返回 `Settlement(ending=WITHHELD)`，答复为
  `QuestionAnswer(NO_ANSWER, reason=QUESTION_TOO_LONG_REASON)`，回显为空（那人没见过这张卡）。
  `QUESTION_TOO_LONG_REASON = "the question is too long to show in a chat"` 定义在
  `tools/context.py`，由 `omicsclaw.tools` 导出（`test_tools_is_a_leaf_layer.py` 的公开名清单随之改），
  因为要认出它的是工具层：`AskUserTool` 收到带这个理由的 `NO_ANSWER` 时抛
  `ToolArgumentError("the question is too long to show in a chat; ask it again in fewer lines and
  characters, leaving out anything the person does not need in order to answer")`，注册表把它作为
  `is_error` 原文交给模型，模型据此改短再问。这次结算不置 `_closed`（不是期限到期），同一交换里改短后的
  问题照常出卡。CLI 不受影响，照截断显示；`settle_from_grant(pending)` 恒返回 `None`（问题从不由会话授权代答）；
  `interpret(pending, reply)`：`waiting_on_others` 时返回 `consumed=False`；否则**先查**
  `was_seen(pending[0], reply)`（0052 §4.3 的模块级纯函数；同一时刻至多一个问题，§3.7，`pending`
  非空时只有一项）。为假，即卡片还没呈现、呈现不足 `MIN_CARD_AGE_S`，或平台发送时间早于呈现，这条
  消息**被消费**、不结算，`notice` 为 `Not taken as an answer: the question had not been shown yet.
  Please read it, then reply.`（英文正文，照 0052 §4.9 回显的风格，Q11；owner 第四轮裁定第 4 项），
  它不会转给模型，发起人要看过卡片后重发；为真才把 `reply.text` 经 `read_reply` 读作回答；
  `echo(pending, outcome)` 按 REPLIED、WITHHELD、LAPSED、ENDED 给回显，LAPSED 以 `QUESTION_TIMEOUT_REASON` / `QUESTION_ABANDONED_REASON` 区分超时与交换结束（二者的值
  此后不得随意改）。`QuestionReplies` 不用 `entry/replies.py` 的词表、`grant_eligible` 与 `GrantTable`。
- desk 已保证发起人校验、序号与代码、呈现时刻、墓碑、`mail` 门槛、已消费去重、ENDED 回显、
  `REPLY_CONSUMED` 与逐字投递。`was_seen` **不在其列**：desk 只提供这个时间事实，何时要求由处理器
  决定（0052 §4.3），上面的 `interpret` 就是问题这一侧的要求。"其他文字即拒绝"只对审批；对问题，
  看过卡片后发起人的文字就是回答。聊天没有空消息，跳过只能等期限，卡片不提"空行跳过"。
- **结算只在 `runtime.py`**，不新增公开结算入口；0052 S1 结构测试的正则加入 `.questions.settle(` 与
  `handle.answer(`（不用裸 `.answer(`，免得误中 Telegram 的 `query.answer()`，接缝 M1）。
- **截断的测试**（补写时放进 `tests/entry/test_channel_questions.py`，工具层一条放进
  `tests/tools/test_ask_user.py`）：401 行的问题（不到 2,000 字符）与由 2,000 个 U+E0001 组成、转义后
  24,000 字符的问题（2,000 个 U+202E 转义后恰为 12,000，不超上限，不能用作这条用例），都**不出卡**，没有回显，工具结果 `is_error` 且含 `too long to show in a chat`；随后同一交换里
  一个短问题照常出卡、照常作答；工具层：`NO_ANSWER` 带 `QUESTION_TOO_LONG_REASON` 时 `is_error`，
  带其他理由时仍是 `no_answer` 的 JSON。定点变异：`card` 忽略截断标志 ⇒ 不出卡用例红；工具把它当普通
  `no_answer` ⇒ `is_error` 用例红；WITHHELD 也置 `_closed` ⇒ 随后短问题用例红。
- 补写时请 owner 裁定：Email 的作答格式（须过 `mail` 门槛，如首行 `CODE <回答>`，`interpret` 去掉
  代码后再 `read_reply`）；Telegram `~filters.COMMAND` 丢掉的 `/` 开头回答（审核 S10）是放行给
  desk，还是卡片提示改以 `./` 开头。
- 完成后 `surface_config` 的 `channel` 行放开 `ask_user`。无按钮（裁定 4；0052 的按钮编码只服务审批）。

---

## 6. 非目标

`glob_files` / `grep_files`；Desktop 的提问与作答（另立计划，先定 `/chat/permission` 与外部客户端
契约）；按钮；一次多题；回答自动写入长期记忆；提问次数上限与独立的问题期限；子代理或后台提问；
引擎停止原因；线协议键改名；修改 `Rendezvous`、`ApprovalBroker`、`_read_card` 或
`entry/replies.py`（分属 0052 T1、T3 与架构 S2）；问题的会话授权或代答；问题另起编号序列。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| 模型用提问逃避执行，或问本可自查的事 | 描述约束并由测试钉住关键句；日志记每次提问供事后统计 |
| 借提问钓鱼（被注入的内容让模型索要密钥） | 描述明令不索要密钥；Channel 只认发起人（任务 D） |
| 模型借问题正文伪造审批卡或注入转义序列 | 卡片经 `entry/display.py` 中和，续行加前缀；Channel 分条时另靠按宽度折行（§3.5.3）；任务 B 的伪造卡用例 |
| 挂起期间发来的是新请求而不是回答 | 原文交给模型，模型可改变方向；阻塞式的固有代价，写进文档 |
| 回答含受试者标识 | 与用户消息同等对待：进 history 与 `memory.db`，不进日志与审计；CLI 历史文件见 Q11 |
| 无人值守处或第三方组合根打开开关 | launch 关闭（G3）；有期限时到期即 `no_answer`，本交换随即短路；Desktop 期限为 `None` 会等到交换被放弃 |
| 依赖未落地的 0052 T1；与 0052 同改 `turn.py`、`events.py`、`launch/_surfaces.py` | B 排在 T1 后；签名与草图不同时只改 `QuestionBroker` 内部；`surface_config` 由 T0 建立，本计划只加行 |
| 共用 `#n` 后问题编号不连续 | 可接受：卡片首词 `Question` / `Approval required` 已区分，编号只用于对应卡片与提示符 |
| 回滚 | `OMICSCLAW_ASK_USER=false` 即时关闭；代码回滚为删工具、通道字段、两个事件类型、`entry/question.py` 与映射中的一项 |

## 8. 与上游描述不一致的事实

1. 0029 §6 指向的 `runtime/tools/builders/engineering.py:521` 已随 `259fb52a` 删除；旧实现是带内
   协议（立即返回 `needs_user_input`，靠描述要求模型停下）。
2. `CLAUDE.md` 与 README 说 Desktop 上待审批的工具 "waits for its timeout"；实际不设期限，等到交换
   被放弃（`DEFAULT_ABANDON_GRACE_S`）或 `turn_timeout_s` 到期。
3. 更正第一版：14 个事件类型被**两条**测试钉住；`test_assembly.py:79-80` 是前缀断言，无需改。
4. 更正第二版：抽出原语后"共用计数器"与"审批类行为不变"不再冲突，Q14 不成立（架构 M4）；
   `_PARENT_SESSION_TOOLS` 已改为映射 `_WITHHELD_FROM_SUB_AGENTS`，描述由映射渲染；
   `_read_card(prompt, *, decline)` 已扩展为 `subject`、`settled_as`、`refuse` 并接管全部非回答路径。

## 9. 验证

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest \
  tests/tools tests/entry tests/subagent tests/permission tests/launch \
  tests/test_env_example.py -p no:cacheprovider -q -o addopts=""
```

再跑 `AGENTS.md` 的整栈命令，记录与本改动无关的已知失败。手工验收在临时目录进行（设置
`OMICSCLAW_DIR`），对仓库根 `.env` 前后做校验和比对。

## 10. 审核处置

| 审核条目 | 处置 | 位置或理由 |
|---|---|---|
| 审核 M1 B 单独交付会挂死 | 采纳 | §3.9、§3.6.1：B 默认关且 `repl` 也关；C 翻为开 |
| 审核 M2 Ctrl-C 退出 REPL | 采纳 | §3.6.2 经 `_read_card`；任务 C 按键路径测试 |
| 审核 M3 新建 `QuestionBroker` | 采纳（第三版） | 新建、同一 stream、各自 `abandon`；共用计数器经 `Rendezvous` 实现（§3.5.1），第二版的 `#q<n>` 与 Q14 撤销 |
| 审核 M4 与 0052 冲突 | 采纳 | 删 `pending_requests()` 与 `answer_question*`；G5 去掉 Email；任务 D 为桩 |
| 审核 M5 G3 纵深防御不成立 | 采纳 | G3 改写；§3.6.1 无条件 info；§3.5.2 判空 |
| 审核 S1 按文本去重；Q9 | 采纳 | §3.5.1 超时后短路（`_expired`） |
| 审核 S2 结果带问题原文；S3 删 `to_wire` 载荷；S6 独立理由常量、G4 矛盾 | 采纳 | §3.3；§3.5.3；§3.5.1、G4 |
| 审核 S4 措辞；S5 数字 label；S12 不索要密钥 | 采纳 | §3.4 描述、§3.5.4 按形态提示；§3.2 |
| 审核 S7 既有测试清单 | 部分采纳 | `test_events.py` 两条、`test_desktop_stream.py` 已列；`test_channel_runtime.py` 核对后无需改 |
| 审核 S8 非 TTY stdin | 采纳 | §3.6.1 `piped`；判定方式见架构 S8 |
| 审核 S9 `/auto` 用户离开；S13 补全器；Q11 `FileHistory` | 采纳 | 任务 C 文档；§3.6.2 |
| 审核 S10 Telegram `filters.COMMAND`；S11 Email 放宽期限 | 采纳 | 任务 D 待裁定项；Q5 行 |
| 审核 S14 篇幅；事实核对的遗漏 | 采纳 | Desktop 分析并入 §2；任务 D 为桩；无按钮；§8-3 |
| 审核 Q1 阻塞式；Q2 单题；Q6 无通道 `is_error` | 采纳 | §3.1；§3.2；§3.3 |
| 审核 Q3 反对扩展审批 broker | 采纳 | 裁定 7（第三版放宽为"行为与接口不变"）；两 broker 组合同一原语，审批语义不外溢 |
| 审核 Q4 新增两个事件类型 | 采纳 | §3.5.3；两处冻结测试有意识地改 |
| 审核 Q5 复用 `approval_timeout_s` | 采纳 | §3.7；为 Email 放宽它也放宽审批窗口，任务 D 补写时写进文档 |
| 审核 Q7 Channel 默认开，有条件；Q8 子代理不能用 | 采纳 | 任务 D 后随默认值开启；§3.8 |
| 审核 Q10 不设提问上限；Q12 空回复即跳过；Q13 只在未回答时出字 | 采纳 | §6；§3.5.4；§3.5.3，Channel 回显由 `QuestionReplies.echo` 负责 |
| 接缝 冲突表（`events.py`、冻结测试、`ApprovalBroker`、`_repl.py`、`channel/runtime.py`、`turn.py` / `session.py` / `assembly.py`、子代理剔除、`ToolContext`、`AppConfig` / `.env.example`、launch 各处 `replace`） | 采纳 | 依赖行、各任务的改动与既有测试清单；通道是 `ToolContext` 字段；本计划不改 `_approval_line` |
| 接缝 D2–D4 截获、回答入口、待决索引归 desk；M1、M2 | 采纳 | 任务 D：按 kind 分派；只在 `runtime.py` 经 `_broker` 调 `questions.settle` 并进 S1 正则；过滤前交给 desk |
| 接缝 D5 剔除机制统一；架构 S1 扩展点不唯一 | 采纳 | §3.8：映射 `_WITHHELD_FROM_SUB_AGENTS`（原 `_PARENT_SESSION_TOOLS`）已落地，本计划只加一项，描述随之渲染 |
| 接缝 D6 按入口修正配置；D7 `.env.example:91` | 采纳 | §3.6.1；§3.9 |
| 接缝 M3 按钮；M4 R1–R5；M5 Email 未定义 | 采纳 | 无按钮；R2 由 kind 分派满足，R5 即 `REPLY_CONSUMED`；G5 去掉 Email |
| 接缝 M6 0047 对 `ask_user` 的假设 | 不涉及 | 0047 第二版已更正 |
| 接缝 M9 `@agent` 绕过 `TaskTool`；Q-C | 采纳 | §3.8 `delegate` 统一绑 `None` |
| 接缝 M10 禁词；M11 压力档测试；M15 `TIMEOUT_REASON` | 采纳 | §3.4、§3.8；任务 C；§3.5.1 |
| 接缝 M12、Q-E 提示符 Ctrl-C；M13、Q-D 一次性模式 | 采纳 | D3 与架构 S2，任务 C 复用；裁定 9，§3.6.1 |
| 接缝 Q-B desk 通用化；推荐落地顺序 | 采纳 | 裁定 8，任务 D；依赖行 |
| 架构 M1 显示前的中和散落三处 | 采纳 | §3.5.3：`question_card` 经 `entry/display.py`，surface 不再各自清洗 |
| 架构 M3 `ReplyHandler` 契约不完整 | 采纳 | 任务 D：`QuestionReplies` 按 0052 §4.3 实现 `card`、`settle_from_grant`（恒 `None`）、`interpret`、`echo`；`register` 显式带 `kind` 与发起信息 |
| 架构 M4 / O1 会合机制重复 | 采纳 | §3.5.1：建在 0052 T1 的 `Rendezvous` 上；共用 `#n`；裁定 7 放宽；Q14 删；B 依赖 T1 |
| 架构 S2 `_read_card` 只接管 Ctrl-C | 采纳 | 已落地；§3.6.2 `_question` 只提供 `refuse`、`subject`、`settled_as` |
| 架构 S7 作答词表收拢 | 采纳 | §3.5.4：审批词表在 `entry/replies.py`，问题解读在 `entry/question.py`，互不导入 |
| 架构 S8 stdin 判定两次 | 采纳 | §3.6.1：抽出 `is_interactive`，launch 判定一次，以 `interactive=` 传下；删 `_stdin_is_a_terminal()` |
| 架构 S12 子代理措辞统一 | 不涉及 | 问题帧从不来自子代理，`subagent` 恒空；措辞只作用于审批 |
| 对照 O1 会合原语 | 采纳 | §3.5.1：原语形状照对照表；"超时后短路""abandon 后立即返回"留在 `QuestionBroker` |
| 对照 转义序列 | 采纳 | §3.5.3：正文 `inert_block`（续行前缀防伪造卡），选项 `inert_line`；任务 B 伪造卡用例。第五轮起正文改走 `inert_body` |
| 对照 S7 作答词表 | 采纳 | 超集词表的行为变化只涉及审批；问题卡片上的 `好`、`approve` 仍是回答原文 |
| 对照 O3 剔除机制 | 采纳 | §3.8：映射加 `ask_user` 与理由"子代理没有可以提问的人" |
| 对照 后台（暂缓）、O4、`!cmd`、引擎审批事件、O2、M5、M6、A3 / S4 | 不涉及 | 分属 0047、0052、0055 与缺陷修复；harness9 非 TUI 模式丢结果，印证 §3.6.1 在无人处关闭；问题事件同样只在 entry 层表示 |
| 第四轮 N3 `was_seen` 契约自相矛盾；owner 第四轮裁定第 4 项 | 采纳 | 任务 D：`interpret` 先查 `was_seen(pending[0], reply)`，未看过卡的消息消费并回 `Not taken as an answer: the question had not been shown yet. Please read it, then reply.`；"desk 已保证"一句去掉 `was_seen`，改为由处理器要求（与 0052 §4.3、§8.2 第 5 条一致） |
| 第四轮 N4 分条硬切能伪造卡头（问题卡同样受影响） | 采纳 | §3.5.3、§3.5.4：`question_card(..., width=None)`，问题正文与选项行按宽度折行、续段加前缀；任务 B 加宽度用例；任务 D 按 0052 §4.7 换算后传入 |
| 第四轮其余：§2、§3.4、任务 A 仍写"子串匹配 / 五个禁词" | 采纳：已读 `test_permission_wiring.py` 核实 | `_POLICY_WORDS`（:215）7 个词 `gate`、`gated`、`Gated`、`GatedTool`、`permission`、`approval_mode`、`prompts_for_itself`，以 `\b<词>\b` 区分大小写整词匹配全部工具定义的 JSON（:227-244），:295 钉住 `delegate` 等不算命中；§2、§3.4、任务 A 与同一事实的 §3.8 一并改 |
| 第四轮其余：§3.5.3 措辞 | 采纳：逐句对照代码与 0052 第三版 | 两处与事实不符：`NO_ANSWER` 的理由"都是固定常量"不成立（`_read_card` 的 `the terminal could not ask: <error>` 带异常原文），改为经 `inert_line`；"问题 ≤ 2000 字符在 `MAX_BLOCK_CHARS` 内"不成立（上限按转义后计）。另补 Channel 上"伪造不出"依赖 N4 折行 |
| 第四轮其余：§3.6.2 措辞 | 采纳：逐句对照 `_repl.py`、`_transcript.py` | 当时按"`ToolTranscript.render` 对非工具帧不套 `inert_line`"改为"同样不套"；**第五轮更正**：第三批之后非工具帧是 `Text(inert_prose(head), …)`，`QUESTION_ASKED` 改为"每行经 `inert_prose`"，见下方第五轮一行。补一句补全器照常列出斜杠命令但只是文本。其余句子（`_read_card` 的四条路径与理由、`self._source.read(prompt)`、`FileHistory`、`_card`）与代码一致 |
| 第四轮其余："原语不查则本类查" | 采纳：定死由原语校验 | §3.5.1；0052 §4.2 写明 `Rendezvous` 构造时拒绝非正期限 |
| 第四轮其余：`surface_config` 的 `surface` 宜用 Literal 或 StrEnum | 采纳：由建立它的 0052 T0 定义 `SurfaceName = Literal[...]` | §3.6.1 引用；定义在 0052 §4.12 |
| 第四轮其余：建议 `ChildRunner.delegate` 自己绑定 `SUBAGENT_VALUE_KEY` | 采纳：属 0052 的归属契约（§4.10），绑定点在本计划 §3.8 | §3.8：同一次 `use_tool_context` 写入子代理名；`TaskTool.execute` 不改 |
| 第五轮"plan 与代码不一致"：§2（原 :54-55）与 §3.6.2（原 :317-318）写非工具帧不经中和、`QUESTION_ASKED`"同样不套" | 采纳：已读 `_transcript.py:185` 核实非工具帧为 `Text(inert_prose(head), style="dim")` | §2 显示层一条按现状改写；§3.6.2：`QUESTION_ASKED` 每行经 `inert_prose`，不作唯一例外 |
| 第五轮 建议 7 `inert_block` 无生产调用者、计数有旧问题；问题卡改走通用正文函数 | 采纳 | §3.5.3：任务 B 之前抽出 `inert_body` / `inert_body_note`，与 `approval_body` 共用，随后删除 `inert_block` 与 `MAX_BLOCK_*`；`question_card` 返回 `(正文, 是否截断)`，选项行随正文经它，布局改为 `  │ <n>. …`；§2、§3.5.4、任务 B 的前置、测试与变异 |
| owner 裁定 2026-09-24 (a)：折行续段改用不同标记 | 采纳 | §3.5.3、任务 B：折出的续段以 `WRAP_PREFIX`（0052 §4.7）开头，与原文换行的 `CONTINUATION_PREFIX` 区分 |
| owner 裁定 2026-09-24 (c)：Channel 上的问题卡被截断 | 采纳：与审批卡一致，不出卡并向模型报错 | 任务 D：WITHHELD 结算，理由 `QUESTION_TOO_LONG_REASON`（`tools/context.py`），`AskUserTool` 转成 `ToolArgumentError`，错误文字与测试、变异均已写明；不置 `_closed` |
| 第五轮"行号漂移" | 采纳：按符号名重新定位 | `_repl.py`：`_pump` :1119、`_ask_human` :1352、`_answer` :1370、`_ask` :1466、`_forget_asking` :1391、`_read_card` :1409、`_NO_OPERATOR_REASON` :196、`_card` :319、`run_once` :1841；`render.py`：`_control_line` :269、`to_wire` :430、`_approval_line` :370；`_transcript.py` `_RENDERED_ELSEWHERE` :78；`test_render.py` `_one_of_every_type` :133 |
