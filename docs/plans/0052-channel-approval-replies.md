# 计划 0052 — Channel 上的审批：先做文本回复，按钮放到第二阶段

**状态**：第三版（2026-09-23）。经独立审核、架构审核与 harness9 对照，owner 按推荐裁定，已据此返工。**第三版修订**（同日）：写入第四轮收敛审核的 N3、N4 与 owner 第四轮裁定（第 1、2、4、5 项与共用作答词表的行为变化），并对齐第三批代码修复已交付的 `approval_body` 与提及中和。**第五轮修订**（2026-09-24）：按第五轮审核与 owner 同日裁定，改写 §4.7 的注记与宽度论证、抽出 `inert_body` 的显示层前置步、`WRAP_PREFIX`、QQ 进 T2、过渡期、§9 的提及窗口与行号。待 owner 过目。未写任何生产代码。

**前置**：0031（entry 层，Q6 / Q12 / Q18 / Q22、陷阱 10）、0038 §8.3、0044（channel
全平台接入与 conformance）、0046 §7.1、0049（`s` 覆盖整个工具、`ask_every_time`）、
0050、0051（已实施）；缺陷修复 D3（`Repl._read_card`）、D4（`tools/preview.py`），均已在
工作树。另依赖**正在实施、不在本计划范围**的缺陷修复 E1/E2（§3.2）：`tools/preview.py` 的
`escape_unsafe`、`redact_credentials`；`entry/display.py` 的 `inert_line`、`inert_block`、
`arguments_block`（后者已在第三批返工中删除，参数改由 `approval_body` 渲染；`inert_block` 由 §4.7 的
显示层前置步删除）；`ApprovalRequest.reason_shows_call`（经 `require_approval(...,
reason_shows_call=)` 设置）；`render._approval_line` 对所有 surface 统一中和 reason，
`reason_shows_call` 为假时附上参数段。第三批代码修复（第四轮 N1、N2 与 owner 第四轮裁定第 1、2、3、6
项，正在实施，不在本计划范围）又提前交付了本计划原定的两件事：`display.py` 的 `approval_body`、
`MAX_APPROVAL_BODY_LINES`、`MAX_APPROVAL_BODY_CHARS`，`_approval_line` 已改为调用它（§4.7）；Slack、
Discord、Feishu 三个 delivery adapter 对所有出站文本的提及中和（§4.8）。同批的 `inert_prose` 与
模型 `bash` 杀整个进程组与本计划没有接口关系。

**范围**：7 个平台——Telegram、Feishu、Slack、Discord、DingTalk、QQ、Email
（`CHANNEL_REGISTRY`，`entry/channel/__init__.py:78-86`）。**分两阶段**（裁定 4）。第一阶段
是本计划的交付主体：T0 超时；T1 会合原语 `Rendezvous`、子代理归属（S-attr）与 `expires_at`；
T2 逐字投递与 QQ 的提及中和（其余三家已由第三批交付）；T3 待决请求台、`ApprovalReplies` 与共用作答词表 `entry/replies.py`
（CLI 改用），Email 用 `mail` 风格。做完后 7 个平台都能用文本作答。第二阶段是按钮（§7）。

> 行号以 2026-09-23 第三版返工时的工作树为准，并附符号名。E1/E2 与其他会话仍在改这些文件，
> 实施时按符号名重新定位。

**引用**：审核记录 `docs/reviews/2026-09-23-plans-0047-0052-0053-0054.md`。"审核 Mn/Sn"指
第一轮"0052 审核"，"接缝 …"指接缝审核，"架构 Mn/Sn/On"指第二轮架构审核，"对照"指第三轮
harness9 对照，"裁定 n"指 owner 2026-09-23 第 n 条。逐条处置见 §13。

## 0. 摘要

1. **今天断在三处**：没有作答入口（`settle_approval*` 在生产代码里零调用）；没有归属（不记录
   这一轮由谁发起，子代理名到不了 surface）；审批行在投递时会走样，还能提及全体（提及已由第三批中和）。E2 之后
   审批行已中和、DANGER 也附上命令，但仍是一行普通文字，每个 ASK 都在超时后被拒。
2. **会合原语**（O1）：T1 从 `ApprovalBroker` 抽出 `entry/rendezvous.py` 的 `Rendezvous`，
   broker 组合持有它，行为与接口不变；`expires_at` 由原语提供；`TurnHandle` 的共享计数器让
   审批与 0054 的提问 `#n` 不重号。
3. **待决请求台**：`entry/channel/desk.py` 的 `RequestDesk` 与 kind 无关，语义全在各 kind 的
   `ReplyHandler`（建卡、会话授权预检、解读、回显，架构 M3）；审批的实现是
   `entry/channel/approvals.py` 的 `ApprovalReplies`，提问的是 0054 的 `QuestionReplies`。
4. **作答词表收拢**（架构 S7）：`entry/replies.py` 放词表、规范化、`grant_eligible` 与
   `GrantTable`，CLI 与 channel 共用。**CLI 行为变化**：输入"好""approve"原本被当作拒绝，
   今后按批准处理（§4.4，owner 已确认）。
5. **文本回复在 `submit` 里截获**，同步结算，提示交给 runtime 的 Task，被消费的消息返回
   `REPLY_CONSUMED`（审核 M5）。
6. **卡片正文复用 `entry/display.py` 的 `approval_body`**（第三批已交付），附不附参数只看
   `reason_shows_call`（架构 M1、M2、O4）；不截断，超长直接拒绝；按分条长度折行，分条永不在行内切
   （第四轮 N4）。本计划只负责平台特有的逐字投递与 QQ 的提及中和；Slack、Discord、Feishu 的提及中和已由
   第三批修复提前交付，对所有出站文本生效（架构 S3、owner 第四轮裁定第 1 项）。
7. **其余**：授权只有 `y`、`s`、`n`，`s` 按（会话、发起人、工具）记 60 分钟；只认已呈现的卡；
   终局回显挂在 `EXCHANGE_END` 与 pump 的 `finally` 上；`oc channel` 未配超时取 600 s。

## 1. 缘起

2026-09-23 的审计发现 **Channel 上的审批是断的**：`bash` 在 default 模式下是 ASK
（`tools/builtin/bash.py:474` `_POLICY`），channel 用户基本跑不了 skill 脚本。第二版裁定先做文本；
第三轮对照 harness9 后维持原方案，并采纳调研中的细化。

## 2. 目标

| # | 目标 | 可证伪的判据 |
|---|---|---|
| G1 | 7 个平台都能用文本作答 | §4.11 的 A 组规则在 7 个 adapter 上全绿 |
| G2 | 卡片上看得见在批准什么 | 卡片正文与 `_approval_line` 出自同一个 `display.py` 函数；不截断、不变形；参数不进任何日志 |
| G3 | 只有发起人能作答 | 陌生人、同群其他 owner、错误代码、Email 无代码回信，各有测试 |
| G4 | 不会批准没看到的卡 | "连发两个 `y`""卡片还没送达时的 `y`""上一轮迟到的 `y 1`"，各有测试 |
| G5 | 每张卡都有终局回显 | 批准、拒绝、超时、`handle.cancel()`、`turn_timeout_s`、投递失败，都有回显 |
| G6 | 子代理发起的审批标明是谁 | 帧带 `subagent`；CLI 那一行、CLI 提示符、channel 卡片都显示；wire 不带 |
| G7 | 不配超时也能启动；配错时在登录任何平台之前报错 | launch 测试 |
| G8 | desk 不懂 kind；`submit` 不等网络 | 结构测试：`desk.py` 不引用 `approvals`、`ApprovalRequest`、`ApprovalDecision`、`RequestKind.APPROVAL`；delivery 挂起时 `submit` 在一个 loop tick 内返回 |
| G9 | desk 为"问题"预留分派点 | 注册一个假的 QUESTION 处理器：发起人的文字交给它，"其他文字即拒绝"不作用于它 |
| G10 | 作答词表与授权规则只写一次；出站文本不能提及全体 | 结构测试：`_repl.py` 与 `entry/channel/` 下不再定义词表，也不再读 `ask_every_time` 判断授权；A11 |

## 3. 现状：读代码得到的事实

### 3.1 审批帧只是一行文字，也没有作答入口

- `ApprovalBroker.__call__` 发布 `APPROVAL_REQUIRED`，`request_id` 为 `f"{turn_id}#{n}"`，`n` 是
  私有计数 `_issued`（`entry/approval.py:125-185`）；broker 由 `TurnHandle.__init__` 构造
  （`entry/turn.py:826`）。两种审批帧在 `DEFAULT_DELIVERED_TYPES` 里（`runtime.py:139-146`），
  `ChannelRuntime._pump_reply`（`:568-632`）用 `TextRenderer` 把它们渲染成 `_approval_line`
  （`entry/render.py:370`）当普通文本投递；自带的 `delivered_types` 漏掉它们时连这一行都没有。
- `settle_approval*` / `_settle_now`（`runtime.py:467-525`）只有 `test_channel_runtime.py:339,445,
  452,483,506` 用到。用户回的 `y` 经 `registry.deliver`（`:413`）成为排在后面的新一轮，要等前一轮
  超时被拒（`TIMEOUT_REASON`，`approval.py:67`）后才轮到。

### 3.2 E2 之后，审批行上看得见什么

`_approval_line` 输出标题（工具名经 `inert_line`）与正文。E2 时正文是 `inert_block(reason)`，
`reason_shows_call` 为假时再加一行 `arguments: ` 与 `arguments_block(arguments)`，两个块各自上限
40 行、4,000 字符；第三批修复把这两步收进 `display.approval_body`，上限改为理由与参数合计 400 行、
12,000 字符（§4.7），`arguments_block` 随之删除。字段由写 reason 的一方声明，而写 reason 的不只有工具，还有
权限网关（对照 O4）：

| 询问来源 | reason | `reason_shows_call` |
|---|---|---|
| `bash` 自己问（`bash.py:623`） | 完整命令 | 真 |
| `edit_file` 自己问（`edit.py:308`） | 路径与 diff；diff 过大时只有行数 | 有 diff 时真 |
| `write_file` 自己问（`write.py:357` `_reason`） | 路径与字节数 | 假：附写入内容（**Q16 由此满足**） |
| `web_fetch` / `web_search` | URL / 查询 | 真 |
| MCP（`mcp_tool.py:280`） | 服务器、工具名、参数预览 | 预览未截断时真 |
| 网关 PROTECTED（`PermissionGate.resolve`，`gate.py:310-319`） | 说明加主参数 | 主参数就是整个调用时真（`_is_the_whole_call`） |
| 网关 RULE / DANGER / POLICY（`gate.py:323-355`） | 规则、模式或策略说明，不含参数 | 假：附参数 |

以 E2 的代码为准。卡片**只读这个字段**，不再用子串启发式，也不设 `approval_subject`（架构 M2、
O4）。E2 不管平台投递：QQ、DingTalk、Slack、Discord 仍会改写这一行（§4.8）。Slack `<!channel>`、
Discord `@everyone`、Feishu `<at user_id="all">` 提及全体的问题，已由第三批修复在这三个 delivery
adapter 里对所有出站文本中和（架构 S3、第四轮 N2、owner 第四轮裁定第 1 项）。

### 3.3 其他平台事实

| 平台 | 会话键（`base.py:532-541` `Channel.session_id`） | 群里的文本要 @ | 入站线程 | 平台给出的发送时间 |
|---|---|---|---|---|
| Telegram | `telegram:<chat_id>` | 要；文本**不剥离** `@handle` | loop | `message.date` |
| Feishu | `feishu:<chat_id>` | 要 | **lark WS 线程**，经 `_run_async(..., timeout=None)` 同步等 `submit`（`feishu.py:656-665`） | `create_time`（毫秒） |
| Slack | `slack:<channel>` | 要 | loop | `ts` |
| Discord | `discord:<channel>` | 要 | loop | `created_at` |
| DingTalk | `dingtalk:<staff_id>`（按人），回复进私聊 | 群里要 | loop | `createAt`（毫秒） |
| QQ | `qq:<group_openid>` / `qq:<user_openid>` | 要 | loop | `timestamp` |
| Email | `email:<from>` | 无群 | executor → loop | `Date` 头（可伪造，mail 风格靠代码而不靠时间） |

- 7 个 adapter 对 `submit` 的结果**只判断 `is REJECTED`**（`telegram.py:501`、`feishu.py:802` 等），
  新增非拒绝状态是安全的；**`submit` 里等一次网络就会堵住该平台后续的全部事件**（审核 M5）。
- Email 的身份就是 `From` 头（无 DKIM/SPF），有主题时正文被拼成 `Subject: …\n\n<body>`
  （`email.py:405`）。runtime 只持有 binding，binding 不引用 `ChannelCapabilities`，所以
  **runtime 要读的平台事实必须放在 binding 上**（审核 M2）。

### 3.4 CLI 的作答词表与会话授权

`_repl.py` 自有三张词表：`_YES = {"y","yes","ok","allow"}`（`:200`）、`_ALWAYS`（`:206`）、
`_FOR_THIS_SESSION`（`:220`）；`Repl._ask`（`:1466`）用 `answer.strip().lower()`（`:1532`）比对，
其余一律拒绝并以原文为理由。会话授权是 `Repl._granted`（`:535`），键由 `_grant_key`（`:1743`）
给出，`ask_every_time` 规则写在 `_already_granted`（`:1753`）。第二版要在 channel 再写一遍（架构 S7）。

## 4. 设计

### 4.1 分层与模块

```
工具 ─ require_approval ─► ApprovalBroker(Rendezvous) ─ 帧 ─► _pump_reply ─► desk.register/settled/end_exchange ─► 出卡、回显
文本 ─► adapter ─► submit ─► admits ─► 去重 ─► desk.intercept ─┬─ 消费：runtime 结算，提示交给 Task → REPLY_CONSUMED
                                                               └─ 不消费：registry.deliver（照旧）
```

| 模块 | 职责 | 不做什么 |
|---|---|---|
| `entry/rendezvous.py`（新，T1） | `Rendezvous`：编号、future 表、期限、取消清理、只结算一次、abandon、`pending`、`expires_at` | 不知道审批或问题；帧由构造回调给出 |
| `entry/approval.py`（T1） | `ApprovalBroker` 组合持有 `Rendezvous`；决定帧、到期答复、读子代理名 | 公开接口与行为不变 |
| `entry/replies.py`（新，T3） | 作答词表与规范化、`grant_eligible`、`GrantTable` | 不做 I/O；不知道 surface |
| `entry/display.py`（E2，复用） | 对人显示前的中和；`approval_body`、`MAX_APPROVAL_BODY_*`、`unreadable_arguments_note` 已由第三批交付；显示层前置步抽出 `inert_body`（带 `width` 与 `WRAP_PREFIX`）并删除 `inert_block`（§4.7，N4） | 不知道 surface |
| `entry/channel/desk.py`（新，T3） | `RequestDesk`、`ReplyHandler` 与值对象；登记、编号、代码、呈现时刻、发起人校验、`mail` 门槛、按 kind 分派、墓碑、已消费回复去重 | 不懂任何 kind 的语义；不做 I/O；不调 broker |
| `entry/channel/approvals.py`（新，T3） | `ApprovalReplies`：卡片、授权预检、解读、回显文案 | 不做 I/O |
| `entry/channel/runtime.py` | 接线：帧交给 desk，按 kind 选 broker，**唯一**调结算的地方，持有提示 Task | 不解析文本 |
| delivery adapter | `verbatim` 分支；Slack、Discord、Feishu 的提及中和（第三批已交付）；QQ 的提及中和（T2） | 不知道审批的存在 |
| channel adapter | 入站带平台发送时间；Email 另带正文，binding 声明 `mail` | 不碰 desk，不结算 |

**内聚与耦合**：平台特有代码只做渲染、回调解析（第二阶段）与投递；词表、授权、会合、中和、待决
项索引都在 entry。`tools` 仍是叶子层；runtime 不再有跨线程的结算入口，
`test_only_the_adapter_whose_sdk_uses_a_thread_hops_between_loops`（`test_channel_cutover_conformance.py:719`）照旧成立。

`runtime.py` 的改动：

1. `_start_reply` 把 `message.sender` 作为**发起人**传给 `_pump_reply`。
2. `_pump_reply` 在 `delivered_types` 过滤**之前**把审批帧与 `EXCHANGE_END` 交给 desk，审批帧不再
   进 `TextRenderer`，`DEFAULT_DELIVERED_TYPES` 去掉它们；出卡前先 `renderer.flush()` 发出已有文字。
3. `submit` 依次做 `admits`、空文本检查、**去重**、`desk.intercept`，最后才是
   `registry.deliver`。去重（审核 S1）：`(session_id, source_request_id)` 已在 `_accepted` 里
   就走原有的 DUPLICATE 路径，否则原消息被重投时会被当成"其他文字"而拒绝全部待批。
4. 私有映射 `_broker(kind, handle)`：APPROVAL → `handle.approvals`（0054 加 QUESTION →
   `handle.questions`）。结算、`reset_session` 与 pump 提前退出时的 `abandon` 都经它。
5. 新增 `reset_session`；删除 `settle_approval*` 与 `_settle_now`，改写模块 docstring"三项义务"
   的第 3 条。`close()` 先回收 reply Task，提示 Task 分享剩余宽限，到期即取消，最后清空 desk。

### 4.2 会合原语 `Rendezvous`（T1，O1）

`ApprovalBroker`（`approval.py:84-257`）约 130 行里，编号、future 表、期限、取消清理、只结算
一次、同步 abandon 并发结算帧、`pending()` 都与"审批"无关。T1 把它们原样搬进
`entry/rendezvous.py`，帧由两个构造回调决定，期限到时的答复由 `on_expired()` 产出：

```python
class Rendezvous(Generic[Req, Ans]):
    """Numbered requests that one Task awaits and another Task answers."""

    def __init__(
        self,
        stream: TurnStream,
        *,
        asked: Callable[[Req, str], TurnEvent],
        settled: Callable[[str, Ans], TurnEvent],
        on_expired: Callable[[], Ans],
        timeout_s: float | None = None,
        numbering: Iterator[int] | None = None,
    ) -> None:
        """Ids are ``<turn id>#<n>`` with n drawn from *numbering*, a private count from 1 by default."""

    async def ask(self, request: Req) -> Ans:
        """Publish the request, then wait for its answer or its deadline."""
    def settle(self, request_id: str, answer: Ans) -> bool:
        """Answer one outstanding request; False when it is unknown or already answered."""
    def abandon(self, answer: Ans) -> None:
        """Answer everything outstanding with *answer*, publishing a settlement for each."""
    def pending(self) -> tuple[str, ...]:
        """Ids still waiting, oldest first."""
    def expires_at(self, request_id: str) -> float | None:
        """Loop time at which the request's deadline passes; None without one or once answered."""
```

- **行为照搬**：取消时先删挂起项再抛出，不发结算帧（§4.9 的 ENDED 回显正是为此）；abandon
  之后不重复发结算帧；`settle` 对未知 id 返回 `False`；构造时拒绝非正的 `timeout_s`（`ValueError`，
  今天在 `ApprovalBroker.__init__`，`approval.py:118-119`）。期限**只由原语校验**，两个 broker 都不再
  自查（第四轮）。
- **`ApprovalBroker`** 组合持有它：`__call__`、`settle`、`abandon(reason=ABANDONED_REASON)`、
  `pending` 的签名，`TIMEOUT_REASON`、`ABANDONED_REASON` 的值，INFO 日志的内容（不记参数）都不变；
  非正超时照旧在构造时抛 `ValueError`，改由原语抛出，文字不再提"审批"（`test_approval.py:199` 只断言
  异常类型）；新增 `expires_at(request_id)` 与可选的 `numbering=`。`asked` 回调在工具的
  上下文里执行，顺手读 `context_value(SUBAGENT_VALUE_KEY, "")`（§4.10）。
- **共享计数器**：`TurnHandle` 持有私有的 `itertools.count(1)`，经 `numbering=` 传给 `approvals`，
  0054 的 `questions` 传同一个；直接构造 `ApprovalBroker(stream)` 的测试照旧得到自己的计数。
  提问特有的策略（超时一次后短路、abandon 后立即返回）留在 `QuestionBroker`，不进原语。

### 4.3 待决请求台与 `ReplyHandler`

**待决项** `PendingRequest(kind, request_id, turn_id, session_id, initiator, surface, ordinal,
code, event, expires_in_s, card_target, presented_at, answer_target)`，desk 是唯一写入者：

- `ordinal`：按会话单调递增，卡上显示为 `#n`，不随轮次重置，迟到的 `y 1` 碰不到新卡（审核 M3）。
- `code`：6 位 Crockford base32（去掉 I、L、O、U），`secrets` 生成，约 30 bit，在"待决 + 墓碑"
  内唯一，大小写不敏感；对 Email 它是真正的能力凭据。
- `presented_at`：卡片投递返回 ACCEPTED 或 UNKNOWN 的时刻（可注入时钟）；此前任何文本都不能批准它。
- `answer_target`：作答消息自己的 reply target，回显发往那里（审核 S7）。

**处理器契约**（方法名由 owner 裁定；desk 只经它接触语义）：

```python
class ReplyHandler(Protocol):
    """How one kind of pending request is shown, pre-answered, answered and closed."""

    kind: RequestKind

    def card(self, pending: PendingRequest) -> Card | Settlement:
        """The card that asks, or the settlement to make when the request cannot be shown whole."""
    def settle_from_grant(self, pending: PendingRequest) -> Settlement | None:
        """The settlement a standing grant already gives, or None to ask."""
    def interpret(self, pending: Sequence[PendingRequest], reply: InboundReply) -> Interpretation:
        """What the reply settles among the sender's pending requests of this kind."""
    def echo(self, pending: PendingRequest, outcome: Outcome) -> str:
        """The line telling the person how a request ended; "" sends nothing."""
```

值对象（冻结，定义在 `desk.py`）：

| 名字 | 字段 | 说明 |
|---|---|---|
| `Card` | `body`、`legend`、`undelivered` | `body` 已中和，可长，runtime 逐字分条；`legend` 是最后一条的作答说明；`undelivered` 是卡片出不去时的结算值 |
| `Settlement` | `request`、`answer`、`ending` | 结算哪一项、用什么值、属于哪种结局 |
| `InboundReply` | `text`、`style`、`sent_at`、`received_at`、`waiting_on_others`、`ended` | `text` 是原文（chat 为整条，mail 为首个非空、非 `>` 行）；`ended` 是发送者在本会话墓碑里、被文本引用到的项 |
| `Interpretation` | `settlements`、`notice`、`consumed` | `consumed=False` 时这条消息照常成为一轮 |
| `Outcome` | `ending`、`answer` | `Ending`：REPLIED、GRANTED、WITHHELD（过长或投递被拒）、LAPSED（broker 自己结算：期限到或放弃）、ENDED（交换结束仍无结算帧） |

`interpret` 收的是**序列**而不是单项：裸动词要知道有几张卡、DENY 要一次拒绝全部，这些判断
属于审批语义，不该回流到 desk。另有模块级纯函数 `was_seen(pending, reply) -> bool`：卡已呈现；
`reply.sent_at` 存在时晚于 `presented_at`；`received_at >= presented_at + MIN_CARD_AGE_S`
（3 s）。它只是时间事实，由处理器决定何时要求它，desk 不替任何处理器检查（第四轮 N3）。审批一侧的
要求见 §4.6（只约束授予类裸动词）；问题一侧由 0054 的 `QuestionReplies.interpret` 实现：对发起人的
每条回复先查 `was_seen(pending[0], reply)`，为假就**消费**这条消息、不结算，回
`Not taken as an answer: the question had not been shown yet. Please read it, then reply.`（owner
第四轮裁定第 4 项；英文正文，照 §4.9 回显的风格，Q11）。

**生命周期**（全部同步，全部在 loop 线程上）：

| 调用 | 调用方 | 做什么 |
|---|---|---|
| `register(kind, event, *, session, sender, surface, expires_in_s)` | pump | 分配序号与代码，登记；先问 `settle_from_grant`，命中则返回那个 `Settlement`；否则返回 `card()` 的结果 |
| `presented(request_id)` | pump，发卡返回 ACCEPTED/UNKNOWN 后 | 记下 `presented_at` |
| `intercept(message, style)` | `submit` | 见下；返回 `Interpretation` 或 `None` |
| `settled(request_id, answer)` | pump，收到结算帧时 | 出列，写墓碑；以记录过的结局（否则 LAPSED）调 `echo`，返回待决项、回显与目标 |
| `end_exchange(turn_id)` | pump，`EXCHANGE_END` 时**和** `finally` 里 | 这一轮还没结局的项按 ENDED 出列、写墓碑并取回显；幂等 |
| `reset_session(session_id)` | runtime，`/new`、`/clear` 之后 | 交出该会话的全部待决项（审核 S11） |

**`intercept` 的通用顺序**：

1. `(session_id, source_request_id)` 在已消费回复的 LRU 里（平台重投）：消费，静默。
2. 取文本：`mail` 取 `values[VALUE_REPLY_TEXT]` 首个非空、不以 `>` 开头的行；`chat` 取整条。
3. 会话里没有待决项：文本里有一个词等于**这位发送者**的墓碑代码时，交给该墓碑 kind 的处理器
   （`pending=()`、`ended` 非空）；否则不截获。
4. `mail` 风格：那一行里没有任何待决项或该发送者墓碑项的代码，就**不截获**（审核 M2）。
5. 发送者是发起人时 `pending` 为该会话的待决项，否则为空并置 `waiting_on_others`（同一会话同一
   时刻只有一轮在跑，`ask_user` 又是屏障，所以待决项只属于一个发起人、一种 kind）。
6. 调该 kind 处理器的 `interpret`；desk 丢弃指向 `pending` 以外的结算（纵深防御），记下其余结算
   的结局与 `answer_target`，登记已消费 LRU；`consumed=False` 或无处理器时返回 `None`。

**结算与 I/O 分离**（审核 M5）：runtime 在 `submit` 里对每个 `Settlement` 同步调
`_broker(kind, handle).settle(...)`，提示交给 `_notify`（每条一个 Task，登记在 `_notices`，
`close()` 时回收），立即返回 `REPLY_CONSUMED`。

### 4.4 作答词表与授权：`entry/replies.py`

```python
class ApprovalVerb(StrEnum):
    ONCE = "once"; SESSION = "session"; ALWAYS = "always"; DENY = "deny"

def normalize_reply(text: str) -> str:
    """NFKC, mentions removed, trailing punctuation removed, casefolded, spaces collapsed."""
def approval_verb(text: str) -> ApprovalVerb | None:
    """The verb a whole reply spells after normalising, or None."""
def grant_eligible(request: ApprovalRequest) -> bool:
    """Whether a standing grant may answer this request."""

class GrantTable(Generic[K]):
    """Standing grants under keys the surface chooses, optionally expiring and bounded."""
    def __init__(self, *, ttl_s: float | None = None, max_entries: int | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None: ...
    def grant(self, key: K) -> None: ...
    def covers(self, key: K) -> bool: ...
    def revoke(self, where: Callable[[K], bool]) -> int: ...
```

| 动词 | 英文 | 中文 |
|---|---|---|
| ONCE | `y` `yes` `ok` `okay` `approve` `allow` | `批准` `同意` `允许` `可以` `好` `好的` `是` `确认` |
| SESSION | `s` `session` | `本会话` `会话` `本会话允许` |
| ALWAYS | `a` `always` | `总是允许` |
| DENY | `n` `no` `deny` `reject` | `拒绝` `不同意` `不允许` `不行` `不要` `不` `否` `取消` |

- **规范化**：NFKC → 去掉提及记号（`@\S+`、`<@…>`，Telegram 不替我们剥离 `@handle`）→ 去掉
  首尾空白与句末标点（`.。!！~～`）→ casefold → 合并连续空白。整条精确匹配；规范化后超过
  40 字符不算动词，`好的，再帮我看看 X` 不是动词。
- **`grant_eligible`** 即 `not request.ask_every_time`，CLI 与 channel 都经它，不再各写一遍。
- **`GrantTable`**：键与寿命作参数，实例由各 surface 持有。CLI 用 `(session_id, tool)`，不设
  期限与上限；channel 用 `(session, sender, tool)`，`ttl_s=3600`，`max_entries=max_sessions`
  做 LRU，查询时顺带清理过期项。

**Channel 的授权**：只有 ONCE、SESSION、DENY（裁定 6）。ALWAYS 写的规则进了
`<workspace>/.omicsclaw/settings.json` 就对所有入口永久生效，不该在手机上改，发起人打 `a` 按
"其他文字"处理（Q17）。SESSION 在 `grant_eligible` 为假时按 ONCE 处理并在回显里说明。键多一个
发起人，因为群聊会话是共享的；60 分钟、重启、`/new`、`/clear` 任一先到即失效，因为 IM 会话永远
开着。子代理与父会话共享授权（0049 §5）；自动放行不发消息；一次 `s` 只结算它作答的那张卡。

**CLI 改用**（T3）：`Repl._granted` 换成 `GrantTable`；`_already_granted` 改为
`grant_eligible(request) and self._grants.covers(key)`；`_ask` 的 `verdict` 改用
`approval_verb`，拒绝理由仍是原文（以 `/` 开头的仍换成 `denied at the terminal`）；三张词表
连同 docstring 里的理由移到 `replies.py`。**这是行为变化，owner 已确认（2026-09-23，第四轮裁定）**：

| 输入 | 今天 | 之后 |
|---|---|---|
| `好`、`approve`、`批准`、`okay` | 拒绝，理由为原文 | 批准一次 |
| `Y.`、`ｙｅｓ`（全角）、` YES ` | `Y.` 与全角拒绝；` YES ` 批准 | 都批准一次 |
| `本会话` | 拒绝 | 本会话授权 |
| `总是允许` | 拒绝 | 批准并写规则 |
| `no, use the other file` | 拒绝，理由为原文 | 不变 |

CLI 的图例（`_APPROVAL_LEGEND` 等）措辞不变，"anything else denies"仍然成立。

### 4.5 谁能作答

回答者必须在 binding 的 owner 名单里（`SenderPolicy.admits` 保证，含群聊 @ 闸门），**并且
等于这一轮的发起人**，即触发这一轮的那条消息的 `InboundMessage.sender`。子代理发起的卡片，
发起人是父回合的发起人。同群其他 owner 发来动词，得到"只有发起这次请求的人能作答"的提示，
不结算；发来其他文字，照旧成为普通一轮。陌生人被 ingress 挡住，得不到任何回话。

### 4.6 文本回复：语法与判定（`ApprovalReplies.interpret`）

```
chat（整条消息恰好一行）：reply := VERB | VERB " " REF      REF := "#"? DIGITS | CODE
mail（首个非引用行）：    reply := VERB " " CODE
```

**呈现时间判定**（审核 M3）：授予类（ONCE、SESSION）**裸**动词要生效，目标卡必须
`was_seen`。带 `#n` 或代码的只要求目标已呈现（序号单调、代码随机，指不到人没看过的卡）；
DENY 与"其他文字"本身 fail-closed，不受约束。

**`chat` 风格**：

| 情况 | 结果 | 消费？ |
|---|---|---|
| `waiting_on_others`，文本是动词 | 回"只有发起这次请求的人能作答"，不结算 | 是 |
| `waiting_on_others`，其他文字 | — | 否 |
| `ended` 非空，文本是 `VERB CODE` | 回"那张卡已结束" | 是 |
| 授予类裸动词，恰有一张 `was_seen` 的卡，且没有正在发送的卡 | 结算这张 | 是 |
| 授予类裸动词，有卡未呈现、刚呈现不足 3 s，或消息发送早于呈现 | 回"卡片刚发出，请看过后再答"，不结算 | 是 |
| 授予类裸动词，有多张已呈现的卡 | 列出 `#n 工具名` 与作答方式，不结算 | 是 |
| 动词 + `#n` 或代码 | 命中已呈现的卡就结算；命中未呈现的回"卡片正在发送"；未命中回"没有这张待批卡" | 是 |
| DENY 裸动词 | 拒绝发起人在本会话的全部待批 | 是 |
| 其他任何文字（含 ALWAYS） | 拒绝全部待批，理由 `the person replied with a message instead of approving; their message: <文字>`（截断到 2,000 字符）；回"已拒绝，你的消息已转给助手"。与 CLI"其他回答都算拒绝并作为理由"同构 | 是 |

**`mail` 风格**（Email）：desk 的门槛已保证首行含有效代码。

| 首行 | 结果 | 消费？ |
|---|---|---|
| `VERB CODE`，CODE 命中发起人已呈现的待批 | 结算 | 是 |
| `VERB CODE`，CODE 在发送者的墓碑里 | 回"那张卡已结束" | 是 |
| 其他（含 ALWAYS、`CODE thanks`） | 不截获，照常成为一轮 | 否 |

第二版的"错误代码满 5 次锁定"删去：门槛使未命中的代码不被截获，那一行不可达；30 bit 代码在
600 s 内按每秒一封猜中的概率约 6×10⁻⁷。Email adapter 把**正文**（不含拼上去的 `Subject:` 行）
放进 `values[VALUE_REPLY_TEXT]`。只有 HTML 的回信经 `strip_html` 后引用行没有 `>`，所以卡片里
**任何一行**都不得被 mail 语法接受（性质测试，审核 S9），作答说明写成
`Reply with this as the first line: y K7Q2PX`。mail 不做呈现时间判定（代码只随卡片寄到 owner
邮箱）。`reply_style` 是 **binding 字段**（`ReplyStyle.CHAT` / `MAIL`，默认 `CHAT`），由
`EmailChannel.prepare_control_binding` 填 `MAIL`；fixture 必须显式声明，漏填由 A8 抓住。

### 4.7 卡片内容（`ApprovalReplies.card`）

依次是：标题（`#n`、代码、工具名、风险，子代理发起时加 ` for sub-agent <name>`，名字经
`inert_line`）；正文，**首行接在标题行末**，以 ` - ` 相连（与 `_approval_line` 相同，理由见下文
N4）；"约 N 分钟内有效，不答即拒绝"；`ask_every_time` 的卡注明"`s` 只放行这一次"；
最后是作答说明，chat 风格为
`Reply: y = allow once · s = allow <tool> here for 60 min · n = deny (y/批准 · s/本会话 · n/拒绝) · add #n if several are waiting`，
mail 风格见 §4.6。

**正文与 `_approval_line` 出自同一个函数** `display.approval_body`。它与两个上限常量已由第三批代码
修复交付（owner 第四轮裁定第 2 项），`_approval_line` 已改为调用它（`f"{header} - {body}"`），CLI 卡片
按同一上限显示，提示符还重复它的注记（`approval_body_note`，§4.10）。T3 不再新增它们。E2 时的
`arguments_block` 已在第三批返工中**删除**：`approval_body` 自己渲染参数；参数无法按 JSON 读出时，
卡片与 TOOL_START 转录行共用公开函数 `unreadable_arguments_note`，只显示长度。已交付的形状：

```python
MAX_APPROVAL_BODY_LINES = 400
MAX_APPROVAL_BODY_CHARS = 12_000

def approval_body(
    request: ApprovalRequest, *,
    max_lines: int = MAX_APPROVAL_BODY_LINES, max_chars: int = MAX_APPROVAL_BODY_CHARS,
) -> tuple[str, bool]:
    """The body of the approval card for *request*, and whether it was cut."""
def unreadable_arguments_note(arguments: str) -> str:
    """What is shown in place of a tool call's arguments that are not JSON."""
```

- **内容**：理由，以及 `reason_shows_call` 为假时的一行 `arguments:` 与参数（缩进、键排序的 JSON，
  凭据键的值遮蔽；空载荷或空对象不显示），全部按 `inert_prose` 中和。两行及以上的连续空行显示为一个
  空行；只有匹配 `[ \t]*` 的行算空行，NBSP、U+3000 等组成的行照原样显示（bash 把它们当普通字符，
  折掉就能藏内容）。
- **截断**：上限对理由与参数**合计**，按屏幕上显示的文字（折叠、转义之后）计；只在原文字符之间切，
  不切断转义序列；只显示了开头的行以 `…` 结尾（`…` 与注记不计入上限）。截断与否由 `display.py`
  自己判定，调用方不解析注记。
- **注记**：正文被截断、发生空行折叠、原文超过 `TALL_APPROVAL_BODY_LINES`（20）行，或显示超过
  `TALL_APPROVAL_BODY_CHARS`（2,000）字符时，首行以注记开头。行数与字符数一律按**原文**计，即转义、
  折叠、截断之前；换行是 `\n`，CRLF 算一个换行、两个字符。截断时分子与分母用同一单位：折叠的一段按
  它代表的全部行计，只显示了开头的行计入分子；"N blank lines folded"只统计已显示部分里的折叠。例：
  `[21 lines, 157 characters]`、`[502 lines, 518 characters; 499 blank lines folded]`、
  `[showing 64 of 70 lines, 77 of 89 characters; 49 blank lines folded]`。
- 卡片以默认上限调用，**被截断就不出卡**，返回 `Settlement(ending=WITHHELD)`，理由为
  `too long to review in a chat; split the work into smaller calls`（Q7）。CLI 照截断显示，带注记。

**按宽度折行（第四轮 N4，owner 第四轮裁定第 5 项，T3 之前必须定稿）**。T2 原定的 `split_verbatim`
遇到超长的单行在行内硬切，续段没有 `  │ ` 前缀：正文可达 12,000 字符，Discord 分条长度只有 1,000，
一行长命令被切开后，下一条消息就以攻击者的文字开头，能伪造卡头。改为在 display 层保证没有超长行，
`split_verbatim` 永远不必在行内切：

- **显示层前置步：抽出 `inert_body`**（第五轮；与 0054 §3.5.3 一致）。把 `approval_body` 的正文渲染
  （空行折叠、截断、`…`、注记规则与 `TALL_APPROVAL_BODY_*` 阈值）抽成通用函数
  `inert_body(text, *, max_lines, max_chars, width=None) -> tuple[str, bool]`，配套
  `inert_body_note(text, *, max_lines, max_chars) -> str`；`approval_body` / `approval_body_note` 只拼出
  理由与参数原文再交给它们，行为与既有测试不变。0054 的 `question_card` 同样用它。抽出之后删除
  `inert_block` 与 `MAX_BLOCK_*`：它们已无生产调用者，计数也有旧问题（切在行尾时写 "showing 2 of 2"，
  截断处没有 `…`）。这一步单独提交，排在本计划 T3 与 0054 任务 B 之前，`width` 与 `WRAP_PREFIX` 在
  这一步一起加上。
- `inert_body` 的 `width: int | None = None`，`approval_body` 透传。给定时，截断与注记照旧先做（是否
  截断与宽度无关，CLI 与 channel 判定一致），再把每一行折成不超过 `width` 个字符的段。**折出来的续段
  以 `WRAP_PREFIX = "  ┆ "` 开头**，与原文换行之后的 `CONTINUATION_PREFIX`（`  │ `）不同，读者能分清
  "原文换行"与"显示层折行"，这在 bash 里语义不同（owner 裁定 2026-09-24）。`width` 连前缀一起计（两个
  前缀等长）；不把一个 `\uXXXX` 转义拆到两行；`width` 容不下前缀加一个转义（小于 10）时抛
  `ValueError`。`None` 不折行，CLI 与 `_approval_line` 都不传，输出逐字不变。测试（`test_display.py`）：
  每行连前缀不超过 `width`；原文换行与折行的前缀各归其位；不拆 `\uXXXX`；截断与注记与 `width` 无关；
  `width` 过小抛错；`approval_body` 的既有用例零改动。变异：折行续段用 `CONTINUATION_PREFIX` ⇒ 前缀用例
  红；折行先于截断 ⇒ 无关性用例红。
- **正文首行接在标题行末**：正文首行没有前缀，单独起行就可能落在某条消息的行首。这样每条消息的行首
  不是带前缀的正文续行，就是 desk 自己写的固定文字。
- **宽度换算**（T3 在 `ApprovalReplies.card` 里做，0054 的 `QuestionReplies.card` 照用）：分条长度
  `L = binding.text_chunk_limit // 2`。减半的作用因平台而异，不是统一的保证：Discord 的 markdown 转义
  每个字符至多加一个反斜杠，Feishu 只在 `<at` 的 `<` 后加一个 U+2060，都至多翻倍，减半保证转义后不超过
  `text_chunk_limit`。Slack 把 `&` 写成 `&amp;`，最多膨胀 5 倍，减半**不**构成保证；Slack 上靠的是它的
  硬上限远大于分条长度：按 Slack 官方文档（`chat.postMessage` 的 `text` 参数），建议不超过 4,000 字符，
  超过 40,000 字符才截断；默认 `text_chunk_limit = 4096` 时 `L = 2048`，最坏膨胀到 10,240 字符加代码块
  围栏，仍远低于 40,000（**未实测**；超过 4,000 字符时的显示效果也未实测）。Slack 超过 40,000 是静默截断
  而不是报错，所以 T2 的 Slack `verbatim` 分支发送前自查转义后长度，超过 40,000 即返回
  `REJECTED_PERMANENT`（`text_chunk_limit` 配到 16,000 以上才可能触发）。display 层的 `\uXXXX` 转义
  发生在折行之前，已经算进宽度。`width = L - 1 - len(标题行里正文之前的部分，含 " - ")`，减 1 留给
  换行符；所有行共用这个宽度，续行至多浪费一个标题的长度。例：Discord `text_chunk_limit = 2000`，
  `L = 1000`，标题连同 ` - ` 共 80 字符时 `width = 919`。
- **折行后仍有超长行就是缺陷**：`split_verbatim` 不再硬切（§4.8），遇到超过 `limit` 的行抛
  `ValueError`。runtime 在分条处捕获，记一条 ERROR（只记工具名与 `#n`），按"卡片投递被拒"处理：
  以 `Card.undelivered` 结算（WITHHELD，拒绝），与 adapter 返回 `REJECTED_PERMANENT` 同一路径，
  fail-closed。测试里它是性质测试的断言失败。
- 超过单条消息上限时用 `split_verbatim(text, L)` 分条先发，最后一条是作答说明；平台转义后仍超长则
  adapter 返回 `REJECTED_PERMANENT`，同样按投递被拒处理。
- 中和规则只在 `display.py` 一处。第二版在 `inert_text` 里按值形态遮蔽凭据（`sk-…` 等）的设计
  随之删去；如果需要，应加在 `display.py` 里对所有 surface 生效。
- **日志**：参数上审批行是 E2 之后所有 surface 的规则，不另立 Q22 的例外；desk、approvals、
  runtime 只记工具名、`#n` 与结局。T3 的 `test_a_card_argument_never_reaches_a_log_record`：
  哨兵参数出现在投递的文本里，不出现在任何日志记录里（先例 `test_cli_logging.py`）。

### 4.8 逐字投递与提及中和（T2）

命令来自可能被注入的模型。平台特有的只有两件事：

1. **提及中和，对所有出站文本生效**（不看 `verbatim`）：答复与审批行同样由模型书写，bot 没有
   正当理由提及全体。Feishu、Slack、Discord **已由第三批代码修复提前交付**（owner 第四轮裁定第 1 项），
   由 conformance rule 9（`test_a_mention_in_outbound_text_notifies_nobody` 等，fixture 的
   `mention_guard`）守住；T2 保证 `verbatim=True` 的分支不绕过它，并补上 QQ（owner 裁定 2026-09-24）。
   Telegram 与 DingTalk 见下表。
2. **逐字**：`DeliveryAttemptRequest.verbatim: bool = False`，经 `deliver`、`_send` 透传。T2 起
   pump 发审批帧那一行时置真，T3 之后 desk 发起的全部消息（卡片、提示、回显）都置真。

T2 因此只剩：`verbatim` 字段、各平台的 `verbatim` 分支（下表最后一列）、`split_verbatim`、
`ChannelFixture.displayed` 与 A9（及 A11 的 `verbatim=True` 部分），以及 QQ 的提及中和。

| 平台 | 今天（第三批之前） | 提及中和（总是；Feishu、Slack、Discord 第三批已交付，QQ 由 T2 补） | `verbatim=True` 另加（T2） |
|---|---|---|---|
| Telegram | 纯文本，无 `parse_mode`（`telegram_delivery.py:88` `_send_message_arguments`） | —。没有点名全体的写法，但 `@username` 能点名（通知）个人。**本期不处理**：它只能通知一名成员，危害远小于 S3 针对的全群提及；Telegram 纯文本没有转义手段，中和只能插入不可见字符，会让卡片里的命令、路径、邮箱地址不能原样复制，与"逐字"冲突 | 不变 |
| Email | 纯文本 | — | 不变 |
| Feishu | `msg_type=text`（`feishu_delivery.py:104-105`）；`<at user_id="all">` 会 @ 全体 | `<at` 中间插入 U+2060（WORD JOINER）（Q19） | 同左 |
| Slack | `text` 按 mrkdwn 解析（`slack_delivery.py:113-117` `_post_message_arguments`）；`<!channel>` 会 @ 全体 | 按 Slack 的规则转义 `&` `<` `>` | 放进 ``` 代码块 |
| Discord | `channel.send(request.text)`，未设 `allowed_mentions`（`discord_delivery.py:125`） | `allowed_mentions=AllowedMentions.none()` | markdown 转义（`discord.utils.escape_markdown` 或等价实现） |
| DingTalk | `sampleMarkdown`（`dingtalk_delivery.py:80`） | —（未见点名全体的文本写法，未核实）。`sampleMarkdown` 会渲染模型写的链接与图片（**未核实**）；`verbatim=True` 改用 `sampleText` 只覆盖卡片与 desk 的消息，普通答复仍走 `sampleMarkdown`，列入 §11 实测 | 改用 `sampleText` |
| QQ | 无条件 `strip_markdown`（`qq_delivery.py:196`）：`` curl `echo x` `` 变成 `curl echo x`；`<qqbot-at-everyone />`、`<@user_id>` 原样发出（`strip_markdown` 不处理尖括号） | **T2 补**（owner 裁定 2026-09-24）：先按 QQ 官方文档核实 v2 群接口（`msg_type=0` 文本）是否解析 `<qqbot-at-everyone />`、`<@user_id>` 等写法，核实后再中和，核实结果与出处写进交付记录；文档说不解析则只记结论、不改代码 | 跳过 `strip_markdown`（`msg_type=0` 本来就是纯文本） |

`base.py` 新增 `split_verbatim(text, limit) -> list[str]`：只在行边界切分，**从不在行内切**，某一行
超过 `limit` 即抛 `ValueError`（调用方的缺陷，见 §4.7 N4）；不增删字符，各段拼起来就是原文
（`chunk_text` 会补代码围栏、吞空白，不能用于卡片）。`verbatim=False` 时行为不变（提及中和第三批
已做），现有 rule 8（`test_outbound_text_is_formatted_for_the_platform_that_receives_it`，
`test_channel_cutover_conformance.py:491`）继续成立：其探针不含 `&<>` 与提及。

### 4.9 终局回显（审核 M1）

**现状**：broker 被取消时先 pop 挂起项再抛出（`approval.py:160-164`），`TurnRunner.run` 的
`finally` 再 `abandon()` 并发布 `EXCHANGE_END`（`entry/turn.py:575-585`），此时挂起表已空，不发
`APPROVAL_SETTLED`。`turn_timeout_s`、`handle.cancel()`、关停、无人观察的宽限取消、pump 提前
返回后被放弃的交换都走这条路。`EXCHANGE_END` 总会发布，所以终局回显挂在它上面，`finally` 兜底。

| 结局 | 从哪里得知 | `ApprovalReplies.echo`（英文正文，Q11） |
|---|---|---|
| REPLIED | desk 自己记录的结算 | `Approved (this call only).` / `Approved; <tool> will not be asked about again here for 60 minutes (calls that are always asked about still are).` / `Denied.` / `Denied; your message was passed to the assistant.` |
| GRANTED | 会话授权命中 | `""`，不发 |
| WITHHELD | 过长或卡片投递被拒 | `Denied automatically: …` |
| LAPSED | 结算帧理由为 `TIMEOUT_REASON` / `ABANDONED_REASON` | `No answer within N minutes; denied.` / 同 ENDED |
| ENDED | `EXCHANGE_END` 或 `finally` 时仍未结局 | `The request ended before this was answered; denied.` |

- pump 的 `finally` 发现交换仍在运行（pump 提前返回），先对 `_broker(kind, handle)` 调
  `abandon()` 让挂起的工具立即被拒，再调 `desk.end_exchange`；回显经 `_notify` 发出。
- 卡片投递被拒 ⇒ 立即以 `Card.undelivered`（`the approval request could not be delivered to the person`）结算；结果未知 ⇒ 按已呈现处理。
- `reset_session`：runtime 调 `ApprovalReplies.forget_session(session_id)` 撤销该会话的授权，
  再对 desk 交出的项所属交换调 `_broker(kind, handle).abandon()`，回显走 LAPSED。

### 4.10 子代理归属（S-attr，T1）

**现状**：`TaskTool.execute` 把子代理名放进工具上下文（`subagent/task_tool.py:163`），
`ApprovalRequest` 与 `TurnEvent.approval_required`（`entry/events.py:409-425`）都不带它；broker
在工具的上下文里被调用，是唯一能顺手记下它的地方。依据裁定 10，同时服务 CLI、channel 与 0047：

- 新增 `TurnEvent.subagent: str = ""` 与 `approval_required(..., subagent="")`；
  `ApprovalBroker` 的 `asked` 回调读 `context_value(SUBAGENT_VALUE_KEY, "")`；`ApprovalRequest`
  不加字段（0046 §7.1）。
- `render._approval_line`：`subagent` 非空时在工具名后追加 ` for sub-agent {name}`，为空时
  **逐字不变**。
- CLI 提示符（`_repl.py:171` `_APPROVAL_PROMPT`，在 `Repl._ask` 里格式化）：第三批之后它是
  `approve {name} [{card}]{size}? [y/N/a=always] `，`{size}` 为空或一个空格加正文注记
  （`approval_body_note`）。非空时为 `approve <tool> for sub-agent <agent> [#N]<size>? [y/N/a=always] `
  （架构 S12），为空时逐字不变。
- `to_wire` 不带这个字段（Desktop 没有消费者，与 0049 对 `ask_every_time` 的处理相同）。
- **名字从哪里来**：今天只有 `TaskTool.execute` 写入 `SUBAGENT_VALUE_KEY`（`subagent/task_tool.py:163`）；
  不经 `TaskTool` 的委派路径（0047 暂缓的后台与 `@agent`）会让子代理的卡片看起来像父代理发起的。
  0054 §3.8 在 `ChildRunner.delegate` 统一重绑工具上下文时一并写入 `SUBAGENT_VALUE_KEY:
  definition.name`（第四轮建议），归属从此不依赖路径；T1 不依赖这一改动（今天唯一的委派路径就是
  `TaskTool`），`TaskTool.execute` 里的同一写入保留。

### 4.11 conformance 扩展

`ChannelFixture` 新增：`reply_style`（必填）；`displayed(payload) -> str`，客户端把负载显示成的
文字（Slack 反转义并去掉代码块，Discord 去掉转义反斜杠，Feishu 去掉 U+2060）；
`reply(channel, text, *, sender, group, mention, sent_at)`，经 adapter **真实的**入站入口送回复。

| # | 断言（每个 authoritative adapter） | 任务 |
|---|---|---|
| A1 | 一轮会询问的交换经本 adapter 出一张卡，卡文含工具名、`#n`、代码与作答说明 | T3 |
| A2 | 发起人经真实入站入口作答（`chat` 发 `y`；`mail` 首行 `y CODE`）⇒ 批准，不触发模型调用，`submit` 返回 `REPLY_CONSUMED` | T3 |
| A3 | 陌生人发同一条回复 ⇒ 不结算，也没有任何回话 | T3 |
| A4 | 有群的平台：群里不带 @ 的 `y` 不结算，带 @ 的发起人 `y` 结算；无群的平台：标成群消息的 `y` 不结算 | T3 |
| A5 | 截止到期与 `handle.cancel()` ⇒ 都有终局回显 | T3 |
| A6 | `chat`：发起人的普通文字 ⇒ 拒绝，模型收到的理由含这段文字；`mail`：普通邮件、首行裸 `y`、引用里有整张卡的"谢谢" ⇒ **不截获** | T3 |
| A7 | 同一条回复被重投 ⇒ 只结算一次，只回显一次 | T3 |
| A8 | binding 的 `reply_style` 等于 fixture 声明的值 | T3 |
| A9 | 探针串（`` ` ``、`**`、`_x_`、行首 `#`、`\|\|`、`<!channel>`、`@everyone`、`<at user_id="all"></at>`、`data/**/x.h5ad`、`a & b < c`）以 `verbatim=True` 经 `accepting_delivery` 发出后 `displayed(sent) == 探针` | T2 |
| A10 | `chat` 风格 adapter 的入站消息带有限的 `VALUE_SENT_AT`（epoch 秒） | T3 |
| A11 | 同一探针发出：Slack、Feishu 的负载里提及记号已中和，Discord 每次发送都带 `allowed_mentions` 为 none。不依赖 `verbatim` 的部分已由第三批修复作为 conformance rule 9 交付（`test_a_mention_in_outbound_text_notifies_nobody` 等）；T2 补上以 `verbatim=True` 发出时同样成立，QQ 核实后加入 | 第三批；T2 补 `verbatim=True` 与 QQ |

**S1（结构）**：`omicsclaw/entry/channel/` 下只有 `runtime.py` 可以出现 `.approve(`、
`.approvals.settle(`、`settle_approval`、`answer_question`；0054 接入后加上 `.questions.settle(`
与 `handle.answer(`（不用裸 `.answer(`，以免误中第二阶段 Telegram 的 `query.answer()`）。

### 4.12 超时默认值与校验（T0）

**现状**：`AppConfig.approval_timeout_s` 默认 `None`（`entry/config.py:206`），旋钮是
`OMICSCLAW_APPROVAL_TIMEOUT_S` / `--approval-timeout`（`:675-680`）；`_as_optional_float`
（`:537-545`）放行 `0`、`-5`、`nan`。`ChannelRuntime.__init__` 只查 `None`、报错不点名旋钮
（`runtime.py:276-281`），且在平台登录与 `open_app`（`launch/_surfaces.py:1301`，
`_serve_channels`）之后才抛；`0`、`-5` 要到首次审批才由 broker 抛错（`approval.py:118-119`）。

- `launch/_surfaces.py` 新增 `SurfaceName = Literal["repl", "once", "piped", "desktop", "channel"]`
  与 `surface_config(config: AppConfig, surface: SurfaceName) -> AppConfig`，是"按 surface 修正
  配置"的**唯一**位置（接缝 D6），不读环境变量（0031 Q8）。五个值由 T0 一次定全（各入口的对应见
  0054 §3.6.1），0054 只加行、不加值；用 `Literal` 与 `entry/events.py` 的 `Terminal`、
  `entry/turn.py` 的 `TurnState` 同例，它只约束静态检查，所以函数对表外的值抛 `ValueError`。第一阶段只做一件事：channel 上把
  为 `None` 的超时换成 `CHANNEL_APPROVAL_TIMEOUT_S = 600.0`（Q1），记一行 INFO；以后 0054 在
  这里给结果送不到人的入口关掉 `ask_user`（裁定 9）。`start_channel`（`:1124`）在
  `resolve_app_config`（`:1146`）之后、构建任何 adapter 之前调用它。
- **校验**（审核 S3）：换一个解析器，拒绝 `0`、负数、`nan`、`inf`，抛 `AppConfigError` 并点名
  两个旋钮，对所有 surface 生效；`ChannelRuntime.__init__` 的守卫改为要求有限正数，报错同样
  点名两个旋钮，作为库级约束保留。
- **文档**：`approval_timeout_s` 的 docstring 写明 `oc channel` 未配置时实际生效 600 s（架构
  S8）；`.env.example:91` 合成一句（接缝 D7）`empty = oc cli waits for the human; oc channel uses
  600 (a chat cannot wait forever)`；README 的 "Channel sets a deadline" 改准确；CLAUDE.md /
  AGENTS.md 的 Channel 一节补上超时，并提示 Email 部署调大超时。

### 4.13 其余新增公开名

`runtime.py`：`VALUE_REPLY_TEXT = "reply_text"`、`VALUE_SENT_AT = "sent_at"`（epoch 秒）、
`TurnAcceptanceStatus.REPLY_CONSUMED`、`ChannelRuntime.reset_session`（`ChannelSubmission.handle`
的 docstring 改为 "`None` when no exchange was started"）；`binding.py`：`ReplyStyle` 与
`ChannelSurfaceBinding.reply_style`；`delivery.py`：`DeliveryAttemptRequest.verbatim`；`base.py`：
`split_verbatim`、`inbound(..., sent_at=None)`；`approvals.py`：`ApprovalReplies`（另有
`forget_session`）；`display.py`（显示层前置步）：`inert_body`、`inert_body_note`、`WRAP_PREFIX` 与
`approval_body` 的 `width` 形参，删除 `inert_block`、`MAX_BLOCK_*`（`approval_body`、
`MAX_APPROVAL_BODY_*`、`unreadable_arguments_note` 本身已由第三批交付）；`launch/_surfaces.py`：模块私有的 `SurfaceName`；
desk、原语、词表的名字见 §4.2–§4.4。

## 5. 已裁定

**第二版裁定**：Q1 channel 默认 600 s 并校验正数；Q2 不开放 `a`；Q3 `s` 按（会话、发起人、
工具）记 60 分钟；Q4 只有发起人能作答；Q5 `chat` 下其他文字即拒绝、`mail` 下照常成为一轮；Q6
词表收 `ok`、`好`、`可以`，受呈现时间约束；Q7 不截断、不变形；Q8 按钮开关见 §7；Q9 删除
`settle_approval*`；Q10 子代理名由 S-attr 承载；Q11 英文正文、作答说明双语；Q12 DingTalk、QQ
不做按钮；Q13 自动放行不回显；Q14 卡片显示参数；Q15 desk 做成通用的待决请求台。

**第三轮裁定**（2026-09-23，按推荐）：Q16 `write_file` 的卡片附写入内容，由 E2 的
`reason_shows_call=False` 加参数段自动满足（§3.2）；Q17 第一阶段发起人打 `a` 按"其他文字"
处理（§4.6）；Q18 `MIN_CARD_AGE_S = 3`，实测后可调；Q19 Feishu 用 U+2060 中和 `<at`，真实平台
核实（§11）；O1 抽出 `Rendezvous`，裁定 7 放宽为"行为与接口不变"（§4.2）；O4 附不附参数由
reason 的书写者声明（E2）；S7 词表与授权收进 `entry/replies.py`，CLI 改用（§4.4）；S9 desk
维持在 `entry/channel/`（§8.1）；S12 CLI 提示符统一为 `approve <tool> for sub-agent <agent> [#N]?`。
harness9 没有可直接采纳的架构，其余按原方案。

**第四轮裁定**（2026-09-23，按推荐）：第 1 项提及中和由第三批代码修复提前交付，T2 只剩逐字投递与
`split_verbatim`（§4.8）；第 2 项 `approval_body`、`MAX_APPROVAL_BODY_LINES = 400`、
`MAX_APPROVAL_BODY_CHARS = 12_000` 由第三批交付，上限对理由与参数合计，连续空行折为一行，首行注明真实
总行数（§4.7）；第 4 项问题卡未呈现时发起人的消息被消费并提示，由 0054 的 `QuestionReplies` 实现
（§4.3、§8.2）；第 5 项 display 层按宽度折行，`split_verbatim` 永不行内切（§4.7、§4.8）；共用作答
词表的 CLI 行为变化获确认（§4.4）。

## 6. 第一阶段任务

**依赖**：T0 独立；T1 在 E2 与第三批修复之后 rebase（同改 `_approval_line`）；T2 独立（提及中和
已由第三批交付，T2 不再为架构 S3 赶工）；T3 依赖 T1、T2、E2、第三批修复（`approval_body`）与显示层前置步
（`inert_body` 与 N4 的折行，§4.7，单独提交，也是 0054 任务 B 的前置）；可按"`replies.py` 与 CLI → desk 与 approvals → runtime 与 7 个 adapter"
三次提交。每个任务单独提交，文档随任务交付，测试命令见 §12。

### T0 — 超时默认值、校验、报错与文档

- **改动**：`launch/_surfaces.py` 的 `surface_config`（由 `start_channel` 调用）；
  `entry/config.py` 的解析器与 `approval_timeout_s` 的 docstring；`runtime.py` 的守卫；
  `.env.example:91`、README、CLAUDE.md、AGENTS.md。
- **验收**：不设超时时 runtime 的超时为 600；显式 `--approval-timeout 5` 仍为 5；`0`、`-5`、
  `nan` 在登录任何平台之前报错（退出码 2，点名两个旋钮）；`oc cli` 的 `None` 不变。
- **测试**：`tests/launch/test_channel_command.py` 加不带 `--approval-timeout` 的探针进程与 `0`、
  `nan` 报错用例；`test_config.py` 测解析器；`test_channel_ingress.py` 测守卫；`test_env_example.py` 保持绿。
- **定点变异**：删掉注入 ⇒ 探针用例红；无条件覆盖 ⇒ 显式 5 红；解析器放过 `0` ⇒ 报错用例红。

### T1 — `Rendezvous`、S-attr、`expires_at`

- **改动**：新增 `entry/rendezvous.py`；`entry/approval.py` 改为组合；`entry/turn.py` 的
  `TurnHandle` 持有计数器并传入；`entry/events.py`；`render._approval_line`；`_repl.py` 的提示符。
- **验收**：`tests/entry/test_approval.py` **不改**且全绿；子代理里 bash 的帧 `subagent ==
  "general-purpose"`，渲染行与提示符都显示它；父代理的帧为 `""`，渲染行与提示符逐字不变；`to_wire`
  不变；`expires_at` 约等于发布时刻加超时。
- **测试**：新增 `tests/entry/test_rendezvous.py`：注入的计数器被使用；两个原语共用一个计数器时
  id 不重号；到期答复来自 `on_expired`；取消后挂起表为空且流上没有结算帧；只结算一次；abandon
  为每个挂起项发一帧；`expires_at` 的三种 `None`；非正 `timeout_s` 在构造时 `ValueError`。
  `test_subagent_wiring.py` 的新用例放在
  `test_the_child_s_approval_request_becomes_a_parent_turn_frame`（`:1036`）旁；
  `test_render.py` 测文本行含名字、wire 不含；`test_cli_repl.py` 测提示符。
- **定点变异**：原语忽略注入的计数器 ⇒ 共用计数器用例红；取消时也发结算帧 ⇒ 取消用例红；broker
  不读上下文 ⇒ 归属用例红；`subagent` 写死为非空 ⇒ 父代理的逐字断言红；`to_wire` 带出
  `subagent` ⇒ wire 用例红；结算后 `expires_at` 仍返回值 ⇒ 红；原语不校验期限 ⇒ 非正期限用例红
  （`test_approval.py:199` 同时变红）。

### T2 — 逐字投递与 QQ 的提及中和（Feishu、Slack、Discord 的提及中和已由第三批交付）

- **改动**：`DeliveryAttemptRequest.verbatim` 与 `deliver`、`_send` 的透传；pump 发审批帧那一行
  时置 `verbatim=True`，经 `split_verbatim(text, binding.text_chunk_limit // 2)` 分条；Slack、
  Discord、DingTalk、QQ 的 `verbatim` 分支（Feishu、Slack、Discord 的提及中和第三批已做，分支不得
  绕过它）；`base.split_verbatim`（从不在行内切，§4.8）；`ChannelFixture.displayed`；conformance A9
  与 A11 的 `verbatim=True` 部分；Slack 的 `verbatim` 分支发送前自查转义后长度，超过 40,000 返回
  `REJECTED_PERMANENT`（§4.7 宽度换算）；**QQ 的提及中和**（owner 裁定 2026-09-24）：先按 QQ 官方文档
  核实 v2 群接口是否解析 `<qqbot-at-everyone />`、`<@user_id>` 等写法，核实后在 `qq_delivery.py` 对所有
  出站文本中和，`qq` 加入 `MENTION_GUARDED_ADAPTERS`，fixture 声明核实过的 `live_spellings`；核实结果与
  出处写进交付记录。Telegram 的 `@username` 与 DingTalk 的 `sampleMarkdown` 本期不改（§4.8）。不新建任何
  转义函数：正文的中和由 `display.py` 负责，T2 只保证它的输出逐字到达。
- **过渡期**（owner 裁定 2026-09-24 接受，理由是 fail-closed）：T2 到 T3 之间审批行仍出自
  `TextRenderer`、不折行，含超过分条长度的行时 `split_verbatim` 抛错，pump 记一条 WARNING（只记工具名
  与 id）、**不投递这一行**；这段时间 channel 本就无法作答，审批照旧到期被拒，不会因此批准任何东西。
- **验收**：§4.8 的全部规则；rule 8 与第三批的 rule 9 保持绿，QQ 核实为会解析时 rule 9 也覆盖 QQ。
- **测试**：A9 与 A11 的 `verbatim=True` 部分在 7 个 adapter 上跑；`split_verbatim` 的性质测试（各段
  拼起来等于原文、只在行边界切、每段不超过 limit；有一行超过 limit 时抛 `ValueError` 而不切开）；
  `test_channel_runtime.py` 断言审批帧那一行以 `verbatim=True` 投递，答复仍为 `False`，含超长行的
  审批行不投递且有 WARNING；`test_channel_slack.py`：`verbatim=True` 下转义后超过 40,000 的文本返回
  `REJECTED_PERMANENT`、不调 SDK；QQ：`MENTION_PROBE` 里核实过的写法经 `accepting_delivery` 发出后不再
  点名（rule 9 参数化自动覆盖），`test_every_platform_that_renders_mentions_declares_how_it_neutralises_them`
  保持绿。
- **定点变异**：QQ 的 `verbatim` 分支仍调 `strip_markdown` ⇒ A9 红；Discord 的 `verbatim` 分支漏设
  `allowed_mentions` ⇒ A11（`verbatim=True`）红；Slack 的代码块分支不转义 `&<>` ⇒ A9 或 A11 红；
  `split_verbatim` 去掉行尾空白 ⇒ 拼接用例红；`split_verbatim` 恢复行内硬切 ⇒ 超长行用例红；Slack 不做
  40,000 自查 ⇒ Slack 超长用例红；QQ 只在 `verbatim=True` 时中和 ⇒ rule 9 的 QQ 参数红。

### T3 — 待决请求台、`ApprovalReplies`、`replies.py`（7 个平台，含 Email 的 `mail` 风格）

chat 截获与 Email 的 mail 风格一起交付，不会出现 Email 走 chat 规则的中间状态（审核 M2）。

- **改动**：新增 `entry/replies.py`，CLI 改用（§4.4）；用显示层前置步的 `width`（§4.7；`display.py`
  本身在 T3 不改）；新增 `desk.py`、`approvals.py`，`ApprovalReplies.card` 按 §4.7 换算宽度、
  正文首行接在标题行末；runtime 在分条处捕获 `split_verbatim` 的 `ValueError`，按投递被拒结算；
  `runtime.py` 按 §4.1；`ReplyStyle` 与 `binding.reply_style`；Email adapter 放入
  `VALUE_REPLY_TEXT` 并填 `MAIL`；6 个 IM adapter 调 `inbound(..., sent_at=…)`；
  `Channel.answer_slash_command` 在 `/new`、`/clear` 成功后调 `runtime.reset_session`；删除
  `settle_approval*`，`test_channel_runtime.py` 里用到它的 4 个测试改成经文本作答（线程那一例改为
  Feishu adapter 在真实线程上收到 `y`，经 `_run_async` 结算）；conformance A1–A8、A10 与 S1；
  CLAUDE.md / AGENTS.md 的 Channel 一节写明怎么作答、群里要 @、Email 要带代码；阶段结束时在
  README 记里程碑。
- **验收**：§4.3–§4.7、§4.9 的全部判定；7 个平台经各自真实的入站入口都能作答；CLI 按 §4.4 的
  表作答，`test_cli_approval_scope.py` 与 `test_cli_repl.py` 的既有用例不改且全绿。
- **测试**：
  - `tests/entry/test_replies.py`（新）：新词表是 CLI 旧三张表的超集；规范化（全角、`@bot y`、
    `Y.`、`好的！`）；超过 40 字符不是动词；`GrantTable` 的期限（注入时钟）、LRU、按条件撤销；
    `grant_eligible`。`test_cli_repl.py` 加 §4.4 表的每一行。
  - `tests/entry/test_channel_desk.py`（新）：desk 单元测试，以及沿用 `test_channel_runtime.py`
    的 `Transport` / `Scripted` / `Asking` 替身的集成测试——连发两个 `y` 不会批准 1 s 后出现的
    #2；投递挂起时的 `y` 得到"正在发送"；迟到的 `y 1` 碰不到新卡；平台时间早于呈现的 `y` 不结算
    （审核 M3）；`handle.cancel()` 与 `turn_timeout_s` 都有 ENDED 回显，之后 `y CODE` 得到
    "已结束"（M1）；delivery 挂起时 `submit` 一个 tick 内返回、`close()` 回收提示 Task（M5）；
    原消息重投得到 DUPLICATE（S1）；非发起人只得到提示；`s` 之后同工具不同参数不再出卡，
    `ask_every_time` 不受影响，两位 owner 互不覆盖，跨过 60 分钟重新出卡；`/new` 撤销授权并拒绝
    挂着的卡；普通文字 ⇒ `ApprovalDenied` 含原话；自定义 `delivered_types` 不含审批帧时仍可作答；
    出卡被拒或正文被截断 ⇒ 立即拒绝；分条时 `split_verbatim` 报缺陷 ⇒ 立即拒绝，ERROR 日志只含
    工具名与 `#n`；G8–G10；`test_a_card_argument_never_reaches_a_log_record`。
  - `tests/entry/test_channel_approvals.py`（新）：`reason_shows_call` 真假两种卡；正文等于
    `approval_body(request, width=…)` 的输出；mail 卡没有一行能被 mail 语法接受（性质测试）；`echo`
    的每种结局；**分条性质测试**（N4）：对 7 个 adapter 的 `text_chunk_limit`，正文含 12,000 字符的
    单行命令、超长 MCP 参数、真实换行与不安全字符时，整张卡经 `split_verbatim(text, L)` 不抛错，
    第一条之后的每条都以 `CONTINUATION_PREFIX` 或 desk 自己的固定文字开头，没有一条以
    `Approval required [` 或攻击者文字开头。
  - `tests/entry/test_display.py` 的 `width` 用例随显示层前置步交付（§4.7）；T3 只要求它们与
    `_approval_line` 的逐字断言保持绿。
  - `test_channel_email.py`：顶部回复 `批准 CODE` ⇒ 批准；首行 "thanks" 而引用里有整张卡、首行
    裸 `y` ⇒ 不截获；只有 HTML 的回信按首行判定。
- **定点变异**：CLI 仍用 `.strip().lower()` ⇒ "好"用例红；`grant_eligible` 恒真 ⇒
  `test_s_does_not_cover_a_dangerous_command` 与 channel 的 `ask_every_time` 用例红；`GrantTable`
  忽略期限 ⇒ 60 分钟用例红；去掉发起人校验、`was_seen`、会话内单调序号 ⇒ 非发起人、连发两个
  `y`、迟到的 `y 1` 各自红；回显只挂在结算帧上 ⇒ 取消用例红；在 `submit` 里 await 提示 ⇒ tick
  用例红；先截获后去重 ⇒ 重投用例红；Email binding 写成 `CHAT` ⇒ A8 与 A6 红；解析整段正文 ⇒
  引用用例红；授权键去掉发起人 ⇒ 双 owner 用例红；审批帧仍受 `delivered_types` 过滤 ⇒ 自定义
  集合用例红；`REPLY_CONSUMED` 误写成 `REJECTED` ⇒ "没有发出拒绝提示且 adapter 记下了 message id"
  的用例红（审核 S13）；忽略 `approval_body` 的截断标志 ⇒ 过长用例红；desk 里出现
  `RequestKind.APPROVAL` ⇒ G8 红；卡片正文进 INFO 日志 ⇒ 日志用例红；卡片不传 `width` ⇒ 分条性质
  用例红；折行续段不加前缀 ⇒ 行首用例红；正文首行单独起行 ⇒ 行首用例红；runtime 不捕获 `split_verbatim` 的 `ValueError` ⇒ 缺陷用例红（卡片挂到
  超时而不是立即拒绝）。

## 7. 第二阶段：按钮（概要）

第一阶段交付并在真实平台验收后才开工，届时另写补遗。每张卡始终保留文本作答说明作兜底；平台
凭据与按钮开关都在 `launch/_surfaces.py` 的 builder 里读取，adapter 不读环境变量（0044 §3 判据
2）；按钮编码只服务审批，问题要按钮须另设前缀并单独审核。

| 任务 | 内容 | 默认 |
|---|---|---|
| B1 按钮接缝 | `ApprovalPresenter`（post / resolve），作为 **binding 字段** `approval_presenter`；desk 经它出卡，被拒时降级为文本卡；`deliver` 带回平台消息 id 供改卡使用；conformance B 组（有 presenter 就必须有能力声明、编解码互逆、负载有上限、陌生人的 ack 不带文字、重复点击、过期、未知代码）；runtime 新增 `answer_approval(answer)`，校验 `answer.surface` 等于卡所属的 binding（审核 S8），**不提供** threadsafe 版本（审核 S2） | — |
| B2 Telegram | `InlineKeyboard`，`callback_data = oc1:<o\|s\|d>:<CODE>`（≤ 64 字节）。`start_polling` **显式**传含 `callback_query` 的 `allowed_updates`（审核 S4）。每个回调都调 `answer_callback_query` | 开 |
| B3 Discord | 用 `on_interaction` 加 `custom_id` 前缀，而不用 `View` 回调，这样重启后的旧卡也能处理（审核 S6）；3 秒内响应；优先用交互响应本身改卡 | 开 |
| B4 Slack | Socket Mode 新增 `interactive` / `block_actions` 分支；需要在后台打开 Interactivity | **关**（审核 S5），真实平台验收后显式打开 |
| B5 Feishu | `register_p2_card_action_trigger` 挂在现有长连接上；回调留在 `feishu.py` 里，经 `_run_async` 跳回 loop，trap-10 子进程探针改挂到这条路径（审核 S2）；群卡片需要 `update_multi` | **关**；开工前核实 lark-oapi 长连接卡片回调的最低版本 |
| B6 | "批准全部"（只作用于已呈现、非 `ask_every_time` 的卡）；ALWAYS 词的提示；发卡结果为 UNKNOWN 时不比对消息位置（审核 S8） | 按需 |

## 8. 非目标，与 0054 的接入契约

### 8.1 非目标

- Desktop 的 `/chat/permission`（应独立成计划）。**它落地时**把 desk 里与 surface 无关的一半
  （登记、结算、墓碑、发起人校验）从 `entry/channel/` 提到 `entry` 共用；此前留在原处（架构 S9）。
- channel 上的 `a`；DingTalk、QQ 的按钮；webhook 回调；待决项跨进程保存；卡片倒计时；斜杠命令
  形式的作答（`dispatch` 按整条文本精确匹配，`commands/_registry.py:100-106`，不支持参数）。
- **问题（`ask_user`）的解读逻辑**：desk 只提供分派点与契约，实现属于 0054 的任务 D。

### 8.2 0054 如何接入（最终版）

1. **会合**：`QuestionBroker`（`entry/question.py`）以组合持有 `Rendezvous`，提供自己的
   `asked`、`settled`、`on_expired`（问题专用的超时理由常量，不改 `TIMEOUT_REASON` /
   `ABANDONED_REASON`）；`TurnHandle` 构造 `questions` 时传入与 `approvals` 同一个计数器，id 为
   `f"{turn_id}#{n}"`，不再用 `#q<n>`，0054 的 Q14 随之消失。结算方法与
   `ApprovalBroker.settle(request_id, answer) -> bool` 同形（名字由 0054 定，建议 `settle`）；
   `expires_at`、`pending`、`abandon` 由原语提供。"超时一次后短路""abandon 后立即返回"留在
   `QuestionBroker`。
2. **不自建路由**：不加 `pending_requests()`、`answer_question` / `answer_question_threadsafe`；
   `ChannelRuntime` 上不新增任何问题结算入口（接缝 D3、D4、M1）。
3. **帧**：pump 在 `delivered_types` 过滤之前，把 `QUESTION_ASKED` 交给
   `desk.register(RequestKind.QUESTION, event, session=…, sender=…, surface=…, expires_in_s=…)`，
   把 `QUESTION_SETTLED` 交给 `desk.settled(request_id, answer)`；两种帧**不加入**
   `DEFAULT_DELIVERED_TYPES`（接缝 M2）。runtime 的 `_broker` 映射加一行 QUESTION →
   `handle.questions`，`reset_session` 与 pump 提前退出时同样对它 `abandon()`。
4. **处理器**：`entry/channel/questions.py` 的 `QuestionReplies` 实现 `ReplyHandler`：
   - `kind = RequestKind.QUESTION`；
   - `card(pending) -> Card | Settlement`：正文用 `question_card(request, ref, width=…)`，`ref` 是
     desk 的 `#n` 与代码，经 `display.py` 的 `inert_body` 中和，宽度按 §4.7 换算；与审批卡一致，
     **截断即不出卡**，返回 WITHHELD 结算并让工具向模型报错（owner 裁定 2026-09-24，细节见 0054 任务 D）；
   - `settle_from_grant(pending) -> None`，恒为 `None`；
   - `interpret(pending, reply) -> Interpretation`：`waiting_on_others` 时返回 `consumed=False`；
     否则先查 `was_seen(pending[0], reply)`，为假时消费这条消息、不结算，回 `Not taken as an answer:
     the question had not been shown yet. Please read it, then reply.`（owner 第四轮裁定第 4 项）；
     为真才用 `read_reply`，发起人的文字就是回答，"其他文字即拒绝"不适用；
   - `echo(pending, outcome) -> str`：结算、超时、ENDED 的回显文案。
   runtime 构造 desk 时注册它。
5. **desk 已经保证的**：发起人校验；序号与代码；呈现时刻（`presented_at`）；墓碑；`mail` 门槛；
   已消费回复去重；ENDED 回显；`REPLY_CONSUMED`；提示走 runtime 的 Task；逐字投递（提及中和在
   delivery adapter，第三批已交付）。**`was_seen` 不在其列**：它是 §4.3 的时间事实，desk 不替处理器
   检查，何时要求由处理器决定（第四轮 N3）；`QuestionReplies` 对发起人的每条回复都要求它，见第 4 条。
6. **结算只在 `runtime.py`**：S1 结构测试的正则同步加上 `.questions.settle(` 与 `handle.answer(`。
7. **Email**（接缝 M5）：mail 风格下 desk 只在首个非引用行含有待决项代码时才分派；回答格式由
   0054 定（例如 `CODE <回答>`），必须满足这条门槛；做到之前，0054 的目标里不列 Email。
8. **期限与入口**：channel 上问题与审批共用 `approval_timeout_s`（T0 后默认 600 s）；结果送不到
   人的入口（`--prompt`、非 TTY stdin、Desktop、任务 D 前的 Channel）由 `surface_config` 关掉
   `ask_user`（裁定 9）。
9. **次序**：0054 任务 B 排在本计划 T1 之后（建在 `Rendezvous` 上）；任务 D 严格排在 T3 之后。

## 9. 风险

| 风险 | 缓解 |
|---|---|
| **模型可控的文字在群里提及全体**（架构 S3、第四轮 N2）：E2 之后 DANGER 命令与参数都上审批行，经 `TextRenderer` 进 IM 群，答复文本同理 | Slack、Discord、Feishu 已由第三批修复覆盖：delivery adapter 对所有出站文本中和提及（A11，即 conformance rule 9；owner 第四轮裁定第 1 项）。**QQ 未覆盖**：`<qqbot-at-everyone />`、`<@user_id>` 今天原样发出，v2 群接口是否解析未核实，由 T2 核实后中和。**Telegram** 没有点名全体的写法，但 `@username` 能点名个人，本期不处理（理由见 §4.8）。**DingTalk** 未见点名全体的文本写法（未核实），`sampleMarkdown` 会渲染模型写的链接与图片（未核实），列入 §11 实测。T2 之前 QQ 的窗口仍在，README 的已知限制按此写 |
| 按宽度折出的续段若与原文换行后的续行同以 `CONTINUATION_PREFIX` 开头，channel 卡片上分不清一行是被折开的还是本来就换了行（bash 里两者语义不同）；CLI 不折行，不受影响 | **已裁定**（owner 2026-09-24）：折出的续段改用 `WRAP_PREFIX = "  ┆ "`，与 `CONTINUATION_PREFIX`（`  │ `）区分（§4.7 N4） |
| 普通消息被当成拒绝，用户意外 | 只针对发起人、只在有待批时；回显明说"已拒绝，你的消息已转给助手"；模型同一轮就能回应 |
| CLI 词表放宽后，原本表示"不"的输入被读成批准 | 新增的都是明确的同意词；超过 40 字符的句子不算动词；§4.4 的表逐行有测试 |
| 子代理的卡被普通消息拒绝时，这段话进的是子代理；平台或本机时钟偏差 | 子代理的结论会回到父代理，写进文档；两条时间判定同时要求，失败的方向是"提示"而不是"批准" |
| Email 发件人可以伪造 | 必须带随机代码；只解析首行；不带有效代码一律不截获 |
| `s` 在 60 分钟内等于该工具的 `auto-approve` | 危险命令、规则、受保护路径仍然每次都问；有 TTL，`/new` 可以撤销；沙箱才是边界 |
| Telegram 上 `/new`、`/clear` 无处可达（§10 第 4 条）；Feishu 上 `/compact` 会等排在待批轮后的压缩，经 `_run_async(timeout=None)` 把 WS 线程堵到审批超时（审核 S11） | 前者只剩 TTL 与重启，后者写进文档；都另开小修 |
| 群聊里卡片把命令暴露给群成员，命令也经过 IM 服务商 | 暴露面与 E2 之后的审批行相同；参数按键名遮蔽；建议敏感工作用私聊 |
| 卡片正文超过上限被拒；0053 放开 MCP 并行后同时待批的卡更多 | 拒绝理由让模型拆小，上限可调；多张卡时裸动词只给提示，序号与代码没有歧义 |
| QQ 被动回复窗口过后，卡片或回显发不出去 | 回显发往作答消息自己的 target（审核 S7）；发不出只记日志；真实平台验收 |

## 10. 与上游和并行计划描述不一致的事实

1. **0038 §8.3** 说"adapter 渲染审批卡时已持有参数"：没有 adapter 看到过审批帧。**0046 §7.1 与
   `delegate.py:11-18`** 说 surface 会读 `SUBAGENT_VALUE_KEY`：实际没有，T1 之后 broker 是第一个读者。
2. **0049 §3.2 / §13.1** 只覆盖 bash 自己问与 PROTECTED；网关按 DANGER 问时 reason 不含命令，由 E2
   的 `reason_shows_call=False` 补上。**0031 Q22 规则 1** 的"approval lines excepted"由 E2 扩展到
   参数段，channel 卡片沿用，不另立例外。
3. **0031 Q12** 要求 channel 给出非 None 的超时，实现成了"登录之后才拒绝启动"，报错不点名旋钮，
   `.env.example:91` 与 README 与之不符（T0 修正）；它要求的 `turn_timeout_s` 检查不在本计划范围。
4. 建议另修的两个缺陷：Telegram 只注册 5 个 `CommandHandler`（`telegram.py:234-238`），`/new`、
   `/clear` 等 9 个内置命令无处可达（与 0044 §5.3 以它为基准相悖）；Email adapter 按小写比较 owner
   （`email.py:399`），交给 ingress 的 `sender` 却保留原始大小写，`From: Owner@Example.com` 被静默丢弃。
5. **0054 第二版**：§3.5.1 的独立计数与 `#q<n>`、Q14、任务 D 里"补一个同形 `expires_at`"都随 O1
   失效；删 `pending_requests()` 与 `answer_question*`；`QUESTION_*` 不进默认集合；按 §8.2 改。
6. **0047 A2** 与 T1 是同一个改动，已删除并引用 §4.10；T3 之后 channel 卡片由 desk 生成，措辞与
   `_approval_line` 相同（接缝 M8）。**0053 F9 / R5** 把 `settle_approval` 当作结算现状（接缝 M16），
   **0053 §4.4** 对 desk 的描述（按钮带代码、`all`）已推到第二阶段（架构 S5）。

## 11. 只能在真实平台上验收的行为（第一阶段）

本机没有 IM SDK，测试都基于假 SDK。下列各项记入交付记录，未实测的写明：

| 平台 | 必须实测 |
|---|---|
| Telegram | 群聊（含隐私模式）里的 `@bot y`；`date` 的精度；长卡分条后顺序不乱 |
| Feishu | `<at` 中和后的显示；WS 线程上 `y` 的结算；`create_time` |
| Slack | 转义后普通答复与代码块里卡片的显示；`<!channel>` 不 @ 全体；卡片落在 thread 里 |
| Discord | markdown 转义后是否逐字；`@everyone` 不 ping 全体 |
| DingTalk | `sampleText` 的呈现；群里发起、私聊作答的完整链路；普通答复的 `sampleMarkdown` 是否渲染模型写的链接与图片 |
| QQ | 卡片与回显是否落在被动回复窗口内；同一 `msg_id` 的回复次数上限；中和后的 `<qqbot-at-everyone />`、`<@user_id>` 确实不再点名 |
| Email | Gmail / Outlook / Apple Mail / Foxmail 的引用格式；只有 HTML 的回信；线程头；轮询延迟与截止时间的关系 |

## 12. 验证

每个任务交付时运行下面的命令，再跑 `AGENTS.md` 的整栈命令（与本计划无关的三项既有失败照旧
记录）；定点变异逐个施加，确认被点名的测试抓住后再还原。

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest \
  tests/entry tests/launch tests/permission tests/subagent tests/tools \
  -p no:cacheprovider -q -o addopts=""
```

## 13. 审核处置

"审核"指第一轮"0052 审核"，条目直接写编号；"接缝""架构""对照"分别指接缝审核、第二轮架构审核、
第三轮 harness9 对照；缺陷修复批次写作"缺陷 D1""E1"等，以免与接缝 D4 混淆。

| 审核条目 | 处置 | 位置或理由 |
|---|---|---|
| M1 取消类路径没有结算帧 | 采纳 | §4.9、§4.3 `end_exchange`；T3 的取消用例与变异 |
| M2 T3 先于 T4 会给 Email 打开批准路径 | 采纳 | T3 与 T4 合并；`reply_style` 改为 binding 字段；A6、A8；§4.6 |
| M3 文本会批准人还没看到的卡 | 采纳；"批准全部"推迟 | §4.3（`presented_at`、单调 `#n`、`was_seen`）、§4.6、§7 B6 |
| M4 卡片正文不能逐字显示，还能触发群提及 | 采纳 | §4.8 `verbatim` 与提及中和、A9、A11 |
| M5 `submit` 里不能等网络 I/O | 采纳 | §4.3"结算与 I/O 分离"、§4.1 第 3 条；T3 的 tick 用例 |
| M6 G3 的机制与测试不一致 | 采纳；第三版改由 E2 实现 | §3.2 的 `reason_shows_call`；Q16 自动满足 |
| M7 与 0047、0054 的契约冲突 | 采纳 | §4.10 S-attr；§4.3 kind 分派；中性命名；§8.2；§10 第 5、6 条 |
| S1 先查重再截获 | 采纳 | §4.1 第 3 条；T3 的变异 |
| S2、S4、S5、S6、S8 按钮相关 | 采纳（第二阶段） | §7 B1–B6：不提供 threadsafe 版本；显式 `allowed_updates`；Slack、Feishu 默认关；`on_interaction`；校验 surface、UNKNOWN 时不比对 |
| S3 超时要求有限正数并点名旋钮 | 采纳 | §4.12；T0 |
| S7 提示与回显发往作答消息自己的 target | 采纳 | §4.3 `answer_target`；§4.9 |
| S9 mail 卡不得含可解析的行；裸 `y` 消费并提示；注明主题与时间 | 部分采纳 | 性质测试已加（§4.6、T3）。"裸 `y` 消费并提示"不采纳：Email 不带代码时**不截获**，不变式更简单。主题由同线程回信（`Re: <原主题>`）满足；时间不加 |
| S10 参数上卡是 Q22 的例外，须点名，并加日志测试 | 采纳 | E2 之后参数上审批行已是所有 surface 的规则（§4.7、§10 第 2 条）；日志测试保留 |
| S11 `/new` 拒绝待批；授权表有界；Feishu `/compact` 风险 | 采纳 | §4.3 `reset_session`、§4.9；§4.4 `GrantTable`；§9 |
| S12 `s` 顺带结算同工具的其他卡 | 不采纳 | 一次作答只结算一张卡，与 CLI `Repl._ask` 一致；可在 B6 与"批准全部"一起重议 |
| S13 `REPLY_CONSUMED` 变异的断言方式；为 M1、M3–M5 补变异 | 采纳 | T3 的定点变异 |
| S14 推迟项 | 采纳 | 第一阶段为 T0–T3；按钮、"批准全部"、ALWAYS 提示放到 §7 |
| 事实核对（有问题的各条） | 采纳 | `_settle_now` 的 `:445`、write_file、`open_app` 行号、CLI 行号（改为附符号名）、`allowed_updates`、线程跳转测试的含义、abandon 与结算帧，都已在 §3、§4.1、§4.9、§7 修正 |
| Q1–Q15 | 采纳（Q5、Q6 附条件，Q8 按审核修改，Q9 不新增 threadsafe 版本，Q10 由 S-attr 统一实现） | §5 |
| 接缝 D1–D4 子代理归属、截获、作答入口、待决索引重复 | 采纳 | 归属归 T1（0047 A2 删除，§4.10）；其余归 desk，问题与审批都经 desk 与 runtime 结算（§8.2 第 2、3、6 条） |
| 接缝 D6、D7 按 surface 修正配置；`.env.example:91` | 采纳 | `surface_config` 由 T0 建立；注释合成一句；§4.12、§8.2 第 8 条 |
| 接缝 M1–M5 0054 的入口、帧投递、按钮编码、R1–R5、Email | 采纳（按钮推迟） | §8.2 各条；S1 正则含 `answer_question`；R5 命名为 `REPLY_CONSUMED`；§7 |
| 接缝 M8、M16 0047 A2 与 0053 F9 的前提 | 采纳（记录在案） | §10 第 6 条 |
| 接缝 Q-A / Q-B / Q-D / Q-E | 按裁定 10 / 8 / 9；Ctrl-C 由缺陷 D3 处理（已落地） | §4.10；§4.3；§8.2 第 8 条 |
| 架构 M1 `inert_text` 不应放进 `tools/preview.py` | 采纳 | 删去 `inert_text`；中和由 E1/E2 的 `escape_unsafe` 与 `entry/display.py` 负责，卡片复用；§4.7 |
| 架构 M2 `approval_subject` 挂错位置、判定不可靠 | 采纳 | 删去 `approval_subject` 与子串启发式；参数段是 `display.py` 的多行块；§3.2、§4.7 |
| 架构 M3 `ReplyHandler` 契约不完整 | 采纳 | 四个方法（`card`、`settle_from_grant`、`interpret`、`echo`）；`register` 显式参数；G8 结构测试；§4.3 |
| 架构 M4 / O1 会合机制重复 | 采纳 | `Rendezvous` 由 T1 抽出，共享计数器，`expires_at` 由原语提供；裁定 7 放宽；§4.2、§8.2 第 1 条 |
| 架构 O4 附不附参数由谁判断 | 采纳：书写者声明 | E2 的 `reason_shows_call`；§3.2 |
| 架构 S3 提及注入在 T2 前已可发生 | 采纳 | 提及中和提前到 T2 并对所有出站文本生效；§4.8、§9 第 1 行、A11 |
| 架构 S6 不必改 `test_the_public_surface_is_exactly_what_the_two_plans_delivered` | 采纳 | 该说法已删；那条测试钉的是 `omicsclaw.tools.__all__` |
| 架构 S7 作答词表与授权表重复 | 采纳 | `entry/replies.py`，CLI 改用；§4.4、G10 |
| 架构 S8 600 s 默认值写进 docstring | 采纳 | §4.12；T0。isatty 那一半属于 0054 |
| 架构 S9 desk 的位置 | 采纳 | 维持在 `entry/channel/`；Desktop 落地时提到 entry；§8.1 |
| 架构 S12 CLI 提示符措辞 | 采纳 | `approve <tool> for sub-agent <agent> [#N]?`；§4.10 |
| 对照 O1、O4、转义序列、S7 | 采纳；O4 与转义由 E1/E2 实施 | `Rendezvous` 按对照表的形状，提问特有策略留在 `QuestionBroker`（§4.2）；网关也是 reason 的书写者（§3.2）；卡片复用 `display.py`（§4.7）；词表、`grant_eligible`、`GrantTable` 与 CLI 行为变化（§4.4） |
| 第四轮 N3 `was_seen` 契约自相矛盾（§4.3 与 §8.2 第 5 条） | 采纳：以 §4.3 为准 | §8.2 第 5 条删去"desk 保证 `was_seen`"，改为由处理器要求；§4.3 点明问题一侧由 0054 的 `QuestionReplies` 实现；§8.2 第 4 条 |
| owner 第四轮裁定第 4 项：问题卡未呈现时发起人的消息 | 采纳 | 消费并回 `Not taken as an answer: the question had not been shown yet. Please read it, then reply.`；§4.3、§8.2 第 4 条，实现在 0054 任务 D |
| 第四轮 N4 `split_verbatim` 行内硬切可伪造卡头；owner 第四轮裁定第 5 项 | 采纳 | §4.7：`approval_body`、`inert_block` 加 `width`，截断先于折行，续段加 `CONTINUATION_PREFIX`，正文首行接在标题行末；宽度 `L - 1 - len(标题前缀)`，`L = text_chunk_limit // 2`；仍有超长行时 `split_verbatim` 抛 `ValueError`，runtime 按投递被拒结算（fail-closed）；§4.8；T2、T3 的改动、测试与变异；§9 新增一行"折行与换行不可区分" |
| 第四轮"逐项判断"：`approval_body` 的上限、截断标志、常量位置；owner 第四轮裁定第 2 项 | 采纳：按第三批已交付的形状改写 | §4.7：上限对理由与参数合计；截断由 `display.py` 判定，`inert_block` 公开签名不变；`MAX_APPROVAL_BODY_*` 在 `display.py` 与 CLI 共用；空行折叠与总行数注记。T3 不再新增它们，只以默认上限调用、截断即不出卡；`arguments_block(..., max_lines=)` 不再需要（`approval_body` 不经它）；§4.1、§4.13、T3 |
| owner 第四轮裁定第 1 项：Slack、Discord、Feishu 的提及中和提前交付 | 采纳 | §4.8 注明该列已交付，T2 只剩 `verbatim` 字段与分支、`split_verbatim`、`ChannelFixture.displayed`、A9；A11 注明不依赖 `verbatim` 的部分已由第三批（rule 9）覆盖；T2 条目；§9 第一行：README 已知限制不再需要；§0、§3.2、§4.1 |
| 共用作答词表的 CLI 行为变化 | owner 已确认（2026-09-23） | §4.4、§0 第 4 条；T3 实施 |
| 第四轮其余：建议 `ChildRunner.delegate` 自己绑定 `SUBAGENT_VALUE_KEY` | 采纳：属本计划的归属契约，不属 0047 | §4.10 写明名字的来源；写入点放在 0054 §3.8 已有的 `ChildRunner.delegate` 重绑里，T1 不依赖它 |
| 第四轮其余：`surface_config` 的 `surface` 宜用 Literal 或 StrEnum | 采纳：`Literal` | §4.12 `SurfaceName`，五个值由 T0 定全，表外值抛 `ValueError`；0054 §3.6.1 引用 |
| 第四轮其余：0054"原语不查则本类查" | 采纳：定死由原语校验 | §4.2：`Rendezvous` 构造时拒绝非正期限，两个 broker 不再自查；T1 的测试与变异 |
| owner 裁定 2026-09-24 (a)：折行续段改用不同标记 | 采纳 | §4.7：`WRAP_PREFIX = "  ┆ "`，与 `CONTINUATION_PREFIX` 区分，连前缀计入 `width`；§9 该行改为已裁定 |
| owner 裁定 2026-09-24 (b)：T2 到 T3 过渡期含超长行的审批行不投递 | 采纳：fail-closed | T2 新增"过渡期"一条：只记 WARNING、不投递，审批照旧到期被拒 |
| owner 裁定 2026-09-24：QQ 写进 T2 | 采纳 | §4.8 表 QQ 一行：先按 QQ 官方文档核实 v2 群接口是否解析 `<qqbot-at-everyone />`、`<@user_id>`，核实后中和；Telegram `@username` 能点名个人，本期不处理并写明理由；DingTalk `sampleMarkdown` 渲染链接与图片（未核实）；T2 的改动、测试、变异；A11；§11 实测项 |
| 第五轮"plan 与代码不一致"：§9"窗口已不存在"说过头 | 采纳 | §9 第一行：Slack、Discord、Feishu 已覆盖；QQ 由 T2 处理；Telegram、DingTalk 如实写明 |
| 第五轮"plan 与代码不一致"：§4.7 字符数实为转义后、"减半给 Slack 留余量"不构成保证 | 采纳：按第三批返工后的 `display.py` 改写 | §4.7：注记一律按原文计（CRLF 一个换行、两个字符），截断时分子分母同单位，`…` 标记，折叠只认 `[ \t]*`，截断按显示文字且不切断转义；`arguments_block` 已删除、`unreadable_arguments_note` 公开；宽度换算改为逐平台论证：Discord、Feishu 至多翻倍，Slack 靠官方文档的 40,000 字符截断线（建议 4,000，未实测），并加 Slack 40,000 自查 |
| 第五轮 建议 7 `arguments_block` 无生产调用者（已删除）；`inert_block` 同样无调用者且计数有旧问题 | 采纳 | §4.7 显示层前置步：从 `approval_body` 抽出 `inert_body` / `inert_body_note`，`width` 与 `WRAP_PREFIX` 落在它上面，0054 `question_card` 共用，随后删除 `inert_block` 与 `MAX_BLOCK_*`；§4.1、§4.13、§6 依赖、T3；"前置"与 §3.2 的 `arguments_block` 改为现状 |
| 第五轮"行号漂移" | 采纳：按符号名重新定位 | `render.py:370` `_approval_line`；`_repl.py:171` `_APPROVAL_PROMPT`（第三批后含 `{size}`，§4.10 的子代理提示符随之写明）；§3.4 的 `_YES` :200、`_ALWAYS` :206、`_FOR_THIS_SESSION` :220、`Repl._ask` :1466、`.strip().lower()` :1532、`_granted` :535、`_grant_key` :1743、`_already_granted` :1753；rule 8 `test_outbound_text_is_formatted_for_the_platform_that_receives_it` :491；`test_only_the_adapter_whose_sdk_uses_a_thread_hops_between_loops` :719 |
