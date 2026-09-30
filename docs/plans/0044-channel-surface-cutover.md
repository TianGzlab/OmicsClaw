# 计划 0044 — Channel 面全平台接入：把另外 7 个适配器接进 agent 主循环

> 输入：owner 的观察——「entry 层对 channel 支持多种平台，但目前似乎只有
> feishu 和 telegram 接入了 agent main loop」。
> 目标：把其余适配器接进同一条主循环，**不破坏高内聚低耦合**；收尾后移除
> `omicsclaw/surfaces/channels/`。
>
> 前置计划：0031（entry 层，§5.3 判定「搬，但不验收」）、0037（launch 层，
> §3 的四条可证伪判据）。本计划是 0031 §5.3 那一行的兑现。

---

## 1. 现状：差距不在「没有适配器」，而在三道一致的门

九个适配器文件**全部已经在** `omicsclaw/entry/channel/`，共 2,921 行（实测 `wc -l`），是 0031
task D1 零改动搬过来的。差距是三道门，从下往上：

| # | 门 | 位置 | 表现 |
|---|---|---|---|
| 1 | `authoritative_ingress = False` | `base.py:264`，7 个适配器均未覆写；`manager.py:159` 调 `require_authoritative_ingress()` | `start()` 第一行就抛 `RuntimeError` |
| 2 | `prepare_control_binding()` 返回 `None` | `base.py:305-324` 的默认实现 | `runtime.py:837-842` 拒绝**整个** composition |
| 3 | `_CHANNEL_BUILDERS` 只有两项 | `launch/_surfaces.py:1073-1076` | `build_channel` 抛 `AppConfigError`「no launch configuration yet」 |

三道门互相一致，不是遗漏。`base.py:17-19` 把话说得很直白：「ported, not
accepted; no tests are written for them and no claim is made that they work」。

**本计划就是逐道打开这三扇门的工程，并且为每一扇门补上它缺的那条测试。**

---

## 2. 真正的缺口只有一条：这 7 个适配器走的是「第二条进出路」

| | 双适配器（已验收） | 另外 7 个 |
|---|---|---|
| **进** | `runtime.submit(self.inbound(...))`，带真 idempotency key（`telegram.py:529-543`） | `base.process_message()`（`base.py:531-597`）→ `submit(..., deliver_reply=False)`，**`source_request_id=""`**（`base.py:584`） |
| **出** | 只走 delivery pump，出站四态分类（`delivery.py:93-116`） | `Channel.send()` → `_send_chunk()` 直连 provider，**不分类接受性** |
| **闸门** | `SenderPolicy` 在 `runtime.submit` 里先于 registry 生效（`runtime.py:401-408`） | 同样生效，但群聊闸门因为没有 `bot_identity` 会**全拒** |

`base.py:579-583` 自己写明了为什么不验收：

> "No platform message id reaches this signature, so one exchange per call is
> the most this can promise. … this path is the reason plan 0031 §5.3 does not
> accept these eight adapters."

**但这 7 个适配器其实每一个都已经算出了平台消息 id，只是算完拿去做本地
`DedupCache` 就丢了**：

| 适配器 | 消息 id 来源 | 现在用在哪 |
|---|---|---|
| discord | `str(message.id)` `discord.py:168` | `is_duplicate` `:169` |
| slack | `ts = event["ts"]` `slack.py:185` | `is_duplicate` `:200` |
| dingtalk | `headers["messageId"]` `dingtalk.py:214` | `is_duplicate` `:265` |
| qq | `message.id` `qq.py:181` | `_processed_ids` `:181-183`，**另外还是出站必需的 `msg_id`** |
| wechat | `MsgId` `wechat.py:315` | `is_duplicate` `:356-357` |
| email | `Message-ID` `email.py:286` | 仅用于 `In-Reply-To` / `References` 表头 `:417-421` |
| imessage | **没有** | 全文件无 `is_duplicate` 调用 —— **本计划删除它，见 §6.1** |

所以「接入主循环」对多数平台**不是重写**，而是三件事：

1. 把已经算出来的 id 接到 `source_request_id` 上；
2. 写一个单次投递适配器（`*_delivery.py`），把 provider 调用分类成三态；
3. 关掉第二条路——`process_message` / `send` / `_send_chunk` 改为拒绝，
   像 `telegram.py:361-398` 那样。

---

## 3. 判据：本计划上的「高内聚低耦合」具体是什么

沿用 0037 §3 的写法——不写形容词，写成可证伪的四条：

1. **一个面只有一条进路、一条出路。** 收尾后 `Channel.process_message`、
   `Channel.send` 的通用实现、`collect_reply`、`submit(deliver_reply=)` 全部
   删除。进 agent 的路径全仓库可枚举，且由一条测试列出。
2. **平台知识只在适配器里，部署知识只在 launch 里。** 适配器**不读 env**；
   launch **不 import 平台 SDK**（0031 陷阱 13）。理由是 `launch/_surfaces.py`
   自己的模块 docstring 写下的（它据此引用 0037 §2 问题 1）：

   > it is why the channel credentials are read here rather than in
   > `omicsclaw.entry.channel`: **which** variables name a Telegram bot is a
   > property of a deployment, and a deployment is what a process shell owns

   两条现有探针
   （`tests/launch/test_launch_is_above_entry.py`、
   `test_the_environment_is_read_in_known_places.py`）继续钉住。
3. **不为 8 个适配器造框架。** 新增的共享**代码**必须每一行都对应一个
   「不共享就会**静默**出错」的失败模式；其余一致性用**共享测试**保证，
   不用共享基类保证。
4. **每个被点亮的适配器都有点名测试。** `authoritative_ingress = True` 与
   conformance 测试同生共死：一条参数化测试遍历注册表，凡声明为
   authoritative 的必须过全部八项。

---

## 4. 方案取舍

### 方案 A — 抽一个 `ChannelPlugin` 基类 / 能力驱动的通用适配层 ❌

把「认证 → 读回身份 → 建 binding → 归一化入站 → 分类出站」抽成模板方法，
8 个适配器只填空。

- ✅ 重复最少。
- ❌ **破判据 3。** 九个平台的差异恰好落在模板方法最不擅长的地方：
  transport 生命周期（长轮询 / WS / webhook server / IMAP 轮询 / 子进程 RPC）、
  归属证明的来源（本地比对 vs 平台断言 vs 没有群）、出站的必需参数
  （QQ 要 `msg_id`+`msg_seq`，email 要 `In-Reply-To`，wecom 要 `agentid`）。
  模板方法会把这些差异逼进 `**kwargs` 和 `if self.name ==` ——
  也就是 0031 §开篇批评的 `ControlRuntimePorts`「二十二个字段、六个 `Any`」
  的形状，正是 owner 那句「高内聚低耦合」当初针对的东西。
- ❌ 现有双适配器要为了迁就框架被改写，而它们是**唯一有生产记录**的两个。

### 方案 B — 九份复制粘贴，各写各的 ❌

- ✅ 改动局部，零抽象成本。
- ❌ **破判据 3 的另一半。** reply_target 的键名要在 8 个构造点和 8 个校验点
  之间保持一致；写错一个键 ⇒ 校验失败 ⇒ `REJECTED_PERMANENT` ⇒
  `runtime.py:697-701` 打一条 WARNING 然后**停止发送剩余部分**。
  用户看到的是「机器人不回话」，日志里是一行 warning。**静默。**

### 方案 C — 三条窄接缝 + 一份 conformance 测试 ✅ **推荐**

只共享「不共享就会静默出错」的三样东西，其余用测试对齐。详见 §5。

---

## 5. 三条窄接缝（每条都对应一个静默失败模式）

### 5.1 新增 `entry/channel/reply_target.py`：构造与校验是同一份知识

**失败模式**：构造端和校验端对键名/`schema_version` 的理解不一致 ⇒ 答案静默
丢失（见方案 B 的分析）。今天这份知识已经在两处重复：
`telegram.py:519-528` 构造、`telegram_delivery.py:82-103` 校验；feishu 再来一份。
8 个平台就是 16 个必须互相同意的点。

```python
REPLY_TARGET_SCHEMA_VERSION: Final = 1

class InvalidReplyTarget(ValueError): ...

def build(adapter: str, account_namespace: str, destination_id: str,
          **extras: object) -> dict[str, object]:
    """入站侧唯一构造 reply target 的地方。extras 是平台自己的键。"""

def read(request: DeliveryAttemptRequest, *, adapter: str) -> Mapping[str, object]:
    """出站侧唯一校验的地方：kind / adapter / destination_id / text 非空。
    平台自己的 extras 由调用者在这之后自取。"""
```

**边界**：`build` 不知道任何平台的键名，`read` 只校验四个公共字段。
`thread_ts` / `msg_id` / `touser` / `original_message_id` 全部留在各自适配器里。

**钉住它的测试**：conformance 第 4 项——每个适配器用 `build` 造出的 target，
必须被它**自己的** delivery adapter 接受。

> **这会动到生产代码。** 断言 4 对所有 authoritative 适配器生效，所以
> `telegram.py:519-528`、`telegram_delivery.py:82-103` 和 feishu 的对应两处
> 必须一起迁到 `build`/`read`。这是任务 A 里**唯一**触碰已验收适配器的改动，
> 单独点名，不要在任务 B 里顺手做。

### 5.2 `chunk_text` 的两个死循环，以及 `binding` 的守卫

**失败模式**：`chunk_text`（`base.py:41-126`）在两种输入下不是抛异常，是
**无限循环**。而且它是**同步**循环，`asyncio.timeout` 打不断它，整个 event
loop 连同进程里所有会话一起卡死。

**本机实测**（`PYTHONPATH=. python`，用 `SIGALRM` 3 秒设界）：

```
limit=0  -> HANG (infinite loop)
limit=-1 -> HANG (infinite loop)
limit=5  -> 199 chunks      # 正常
limit=10 -> 100 chunks      # 正常
chunk_text("```py\n" + "x = 1\n"*200 + "```", 10)  -> HANG
```

两条路径：

1. **`limit <= 0`**：`effective_limit=0` ⇒ `segment=""` ⇒ 三个 `rfind` 全 -1
   ⇒ `best = effective_limit = 0` ⇒ `remaining = remaining[0:]` 原地踏步
   （`base.py:66/72/96-97/124`）。
2. **`limit <= 20` 且文本进入代码块**：`effective_limit = limit - 20`
   **变负**（`base.py:66`），后续切片行为翻转，同样不收敛。
   这一条是实测发现的，不在原稿里。

**是不是假想？** `capabilities.py` 的 `EMAIL` 声明 `max_text_length=0`，
注释写 "No practical limit"。`telegram.py:204-206` 的惯用写法是
`self.config.text_chunk_limit or self.capabilities.max_text_length`——
email 上一旦 config 侧也是 0，就正好得到 0。第 2 条路径今天只能由代码里
的误配置触达（没有对应的环境变量），但它**已经存在**，与本计划无关。

**两处改动**：

1. `binding.py:99-128` 的 `__post_init__` 加守卫。下界取 **21** 而不是 1，
   因为 20 是 `base.py:66` 自己给代码围栏留的余量：

```python
if not isinstance(self.text_chunk_limit, int) or self.text_chunk_limit <= 20:
    raise ValueError(
        "text_chunk_limit must exceed the 20 characters chunk_text() "
        "reserves for code fences; at or below it the chunker loops forever"
    )
```

2. `base.py:66` 把余量夹住：`effective_limit = max(1, limit - (20 if in_code_block else 0))`。
   守卫防的是配置错误，夹住防的是守卫之外的调用者（`telegram._send_long_message`
   `:489` 直接用 `capabilities.max_text_length` 调 `chunk_text`，不经过 binding）。

email 的 binding 明确给一个正数上限（建议 `100_000`，SMTP 单封正文的现实上界），
而不是「无限」。

### 5.3 新增 `Channel.command_context()`：斜杠命令今天只有 telegram 能用

**实测的遗漏**：全仓库唯一调用 `dispatch()` 的地方是 `telegram.py:623`。
**feishu 也没接**——所以这一条不只是「新点亮的 6 个要补」，**已验收的 feishu
也缺**，它属于任务 A 而不是任务 B/C/D。 于是 `/clear` `/compact` `/new` `/files` `/outputs` `/recent` `/skills`
`/status` `/version` `/demo` `/examples` `/help` 这 **12** 个内置命令
（`commands/builtins.py`，实测 `grep -c '^@register('` = 12）
在 Telegram 以外的每一个面上，都会被当成普通文本送进模型——用户打 `/clear`，
得到的是模型对「/clear」四个字的解释，而不是清空会话。

`commands/_registry.py:9-12` 的契约本身**已经是平台无关的**：

> A channel calls ``await dispatch(ctx)`` and treats ``None`` as
> "not a command — hand it to the agent instead".

所以缺的不是设计，是接线。每个适配器要做的是在 `submit` 之前插一句：

```python
reply = await dispatch(self.command_context(chat_id, user_id, text))
if reply is not None:
    await <平台的直连短回复>；return
```

**共享的那一半**是 `SlashCommandContext` 的构造——`telegram.py:593-613`
现在的实现除了「从 update 里取 chat/user」之外**没有一行是 Telegram 特有的**：
platform 是 `self.name`，workspace 和 app 来自 `self._control_runtime.app`，
session_id 来自 `self.session_id(chat_id)`。复制 7 份的失败模式是具体的：
漏掉 `session_id` 不会报错，只会让 `/clear` 和 `/compact` 静默地作用于
「没有会话」（`_registry.py:56` 的 `session_id: str = ""` 就是这个意思）。

**改动**：`base.py` 加一个方法，`telegram._command_context` 改为调它。

```python
def command_context(self, chat_id: str, user_id: str | None,
                    text: str) -> SlashCommandContext:
    app = self._control_runtime.app if self._control_runtime else None
    ...
```

**边界**：这个方法**只构造 context**，不决定「是不是命令」（那是 `dispatch`
的事），也不决定「怎么把回复送出去」（那是各平台的直连短回复，与
`telegram._send_long_message:480-497` 同类，不走 delivery pump——
命令输出不需要接受性分类）。

> **Telegram 的命令走的是平台原生注册**（`CommandHandler("skills", …)`，
> `telegram.py:233-237`），不是文本前缀。新点亮的适配器按文本前缀接即可：
> `capabilities.native_commands` 在 DISCORD/SLACK 上是 `True`，但原生注册
> 需要在各平台后台配置命令表，**不在本计划范围**——文本前缀在九个平台上
> 都能工作，且与 `dispatch` 的契约完全对齐。

### 5.4 conformance 测试套件（共享测试，不是共享代码）

新增 `tests/entry/test_channel_cutover_conformance.py`，参数化遍历
`CHANNEL_REGISTRY`，对每个 `authoritative_ingress is True` 的适配器断言八项：

| # | 断言 | 防的是 |
|---|---|---|
| 1 | `prepare_control_binding()` 在 fake provider 上返回一个 `ChannelSurfaceBinding`，且 `binding.adapter == channel.name` | 门 2；以及 §8 陷阱 12（surface 名与 binding 键不一致） |
| 2 | 适配器上**不存在**可用的第二条进出路：`process_message` / `send` / `_send_chunk` / `send_media` 要么抛 `RuntimeError`（任务 B/C/D 阶段），要么**根本没有这个属性**（任务 F 删掉基类实现之后）。断言写成 `pytest.raises((RuntimeError, AttributeError))` 或 `not callable(getattr(ch, name, None)) or raises(...)`，**两个阶段都成立** | 判据 1；以及 §11 任务 F 会把「抛」变成「没有」 |
| 3 | delivery adapter 的四态分类（`delivery.py:93-116` 定义、`:254-322` 消费）：超时 ⇒ `ACCEPTANCE_UNKNOWN`；任意未知异常 ⇒ `ACCEPTANCE_UNKNOWN`；**只有**带 retry-after 证据的限流 ⇒ `NOT_ACCEPTED_RETRYABLE` | §8 陷阱 3：重试出第二条可见回复 |
| 4 | `reply_target.build(...)` 造的 target 被自己的 delivery adapter 接受 | §5.1 |
| 5 | 白名单外的 sender 不产生 exchange，且**不回话** | `CLAUDE.md` 的 owner-only 契约 |
| 6 | 若该平台有群（见 §6 表的「群」列）：群消息无 @ 不产生 exchange；**无群的平台（email/wechat）断言的是另一件事**——`bot_identity` 为空，且一条被标成 group 的消息一律不产生 exchange | `SenderPolicy` 群聊 fail-closed |
| 7 | `/skills` 这类已注册命令走 `dispatch` 而不是进模型；未注册的 `/foo` 照常进模型 | §5.3：命令在 Telegram 以外静默失效 |
| 8 | 出站文本经过该平台的格式化：给 delivery adapter 喂 `**粗体**`，断言 QQ / 微信 MP 收到的是去掉星号的纯文本 | §8 陷阱 13：`_format_chunk` 被架空 |

**这是本计划最高杠杆的产出物。** 它把「9 份相似实现」从耦合负债变成被钉住的
契约，而**没有**引入一个基类。第 10 个适配器想出生，先让这条测试变红。

> 与现有测试的关系：`tests/entry/test_channel_adapters.py`（761 行）保留，
> 它测的是 telegram/feishu 的**平台特有**语义（两种 mention 拼法、SDK 线程、
> 非文本消息）。conformance 测的是**跨平台共有**的八条。两者不重叠。

---

## 6. 分级：哪些现在点亮，依据是什么

依据是三个结构性问题：**有没有稳定的每消息 id**（`source_request_id` 的前提）、
**归属证明从哪来**（群聊闸门的前提）、**本机能不能验收**（无网络、无 SDK、Linux）。

| 平台 | 每消息 id | 群 / 归属证明 | transport | 本机可验收 | 裁决 |
|---|---|---|---|---|---|
| **slack** | `ts` ✅ | ✅ `channel_type=="im"` 判 DM；`app_mention` 事件；`auth_test()["user_id"]` 本地可比对 | Socket Mode（aiohttp，loop 原生） | ✅ fake WebClient | **T1 点亮** |
| **discord** | `message.id` ✅ | ✅ `DMChannel` 判 DM；`client.user in message.mentions` 本地可比对 | Gateway（discord.py，loop 原生） | ✅ fake Client | **T1 点亮** |
| **dingtalk** | `headers.messageId` ✅ | ⚠️ `conversationType=="2"` 判群；归属靠平台布尔 `isInAtList`，**无本地 bot id** | Stream WS（`websockets`，loop 原生） | ✅ fake WS payload | **T1 点亮**（见陷阱 4） |
| **qq** | `message.id` ✅ | ⚠️ 群消息由网关预过滤（只投 @ 过的），**无本地 bot id** | botpy（loop 原生） | ✅ fake botpy client | **T1 点亮**（见陷阱 1、4） |
| **email** | `Message-ID` ✅ | N/A（无群） | IMAP 轮询 + SMTP，阻塞调用走 `run_in_executor` | ✅ fake imaplib/smtplib | **T2 点亮**，带保留（陷阱 2、6） |
| **wechat**（含 wecom） | `MsgId` ✅ | N/A（1:1） | **aiohttp webhook server，需要公网可达** | ⚠️ fake request 可测逻辑，**不能验证平台可达性** | **T2 点亮**，带保留（陷阱 5、11） |
| **imessage** | ❌ 通知里一个都没有 | ❌ 有 `is_group` 但**完全没有闸门** | 外部 `imsg` CLI 的 JSON-RPC 子进程 | ❌ macOS-only，本机 Linux | **删除** —— 见 §6.1 |

收尾后：注册表 **8 个名字，8 个 authoritative**。「注册了但不能启动」这个状态
在本计划之后**不再存在**——这正是判据 4 想要的。

### 6.1 iMessage：删除

> **owner 裁定（2026-09-20）：删除。**

`imessage.py` 的问题不是「没接」，是**缺前提**：

- 通知里没有任何稳定消息 id（全文件无 `is_duplicate` 调用），所以
  `source_request_id` 无从取；伪造一个（sender+text 的 hash）比留空更糟——
  两条一模一样的消息会被静默折叠成一条。
- `is_group` 读到了却完全没用来把关（`imessage.py:384`），而
  `SenderPolicy` 的群闸门要求本地身份，iMessage 没有。
- macOS-only，本机无法跑任何端到端验证。

而收尾后 `Channel.process_message` 会被删除（判据 1），于是它会变成一个
**唯一进路已被删除、且启动即被拒**的 513 行文件——对下一个读代码的人只有
误导价值。要支持 iMessage 的那天，它应该按本计划的模式**新写**（先在一台
Mac 上确认 `imsg` 的通知带稳定 message guid），而不是解冻一份不能启动的旧代码。

删除清单（并入任务 F）：

| 项 | 动作 |
|---|---|
| `omicsclaw/entry/channel/imessage.py`（513 行） | 删 |
| `CHANNEL_REGISTRY` 的 `"imessage"` 项（`__init__.py:84`） | 删 |
| `__init__.py` 模块 docstring 里「nine platforms」「Nine names for ten platforms」等计数 | 改为八 |
| `.env.example` §12 的 `IMESSAGE_CLI_PATH` / `IMESSAGE_SERVICE` / `IMESSAGE_REGION` / `IMESSAGE_ALLOWED_SENDERS` | 删（不是移进 live 段） |
| `tests/test_env_example.py` 的 `RETIRED` 里的 `IMESSAGE_CLI_PATH` | 删 |
| `capabilities.py` 的 `IMESSAGE` 能力档（`:170`） | 删 |
| `tests/entry/test_channel_runtime.py:885` 提到 `imessage.py` 的那句 docstring | 改（只是注释；**实测该文件已无任何 `omicsclaw.*` import**，那句话描述的是旧文件） |
| `tests/test_channels.py` 的 15 处 iMessage 测试 | 随 §10.2 一起删（它们 import 的是已死的 `surfaces.channels.imessage`） |
| `imessage.py:44-59` 的 `_INTERNAL_CONTROL_CREDENTIALS` 及其 docstring | **先摘进 README 或一条 ADR，再删文件。** 它记录的是一个真实缺陷与一次真实修正：三个控制面 token 不能传给 AppleScript 子进程；原实现 import `omicsclaw/skill/execution/environment.py`（**该路径在旧 `surfaces/channels/imessage.py:39` 仍在，是旧包第四个 import 就坏的模块**），移植时内联并写明了「a scrub that silently stops scrubbing is how a control-plane token ends up in a subprocess environment」。这个教训不该随文件消失 |

实测确认删除是干净的：`grep IMESSAGE` 在 `omicsclaw/` 里只剩
`capabilities.py:170` 与 `__init__.py:84` 两处，没有任何其它生产引用。

### 6.2 一个被放大的影响半径：`start_all` 是全有全无的

`ChannelManager.start_all`（`manager.py:117-153`）在**任何一个** channel 启动
失败时 `stop_all()` 并抛错。这条设计是对的——「ingress 为所有 Channel 一起
打开，或者一个都不开」，否则半个部署在应答消息。

但**从 2 个平台扩到 8 个，这条设计的代价变成 4 倍**：一个写错的
`WECOM_SECRET` 会让已经在生产上跑的 telegram 和 feishu 一起起不来。

**本计划不改这条设计**（改了就是引入半启动状态），而是靠两件事缓解：

1. **`--channels` 是显式清单**（`_surfaces.py:741`），不是「启动所有已配置的」。
   一个部署要跑哪几个，是命令行上写死的，不会因为多配了一组变量就被拖下水。
2. **凭据错误在 builder 阶段就报**（§9 末：白名单为空、必填缺失都在
   `build_channel` 里抛 `AppConfigError`），发生在
   `attach_sessions(await open_app(config))` **之前**（`_surfaces.py:945-946`），
   所以它不会浪费一次 MCP 启动，也不会与「已经起来的 channel 被拖垮」混为一谈。

**要写进 `CHANNEL_USAGE` 的一句话**：生产部署建议一个进程一个平台，
除非你确实要它们共享一个会话注册表。
---

## 7. 逐平台改动清单

每个平台的改动都是同一组**五件事**，下表只列**该平台特有的那一件**。

通用五件事：

1. `prepare_control_binding()` —— 认证、读回账号身份、建 `SenderPolicy` 与
   `DeliveryAdapter`、返回 binding；
2. `<name>_delivery.py` —— 单次投递 + 四态分类，**并承接 `_format_chunk`
   的格式化职责**（陷阱 13）；
3. 入站改走 `runtime.submit`：接上已有的消息 id、`reply_target.build`、
   `VALUE_CHAT_TYPE`/`VALUE_MENTIONS`，并把本地判重改成两段式（陷阱 12）；
4. 接上 `dispatch()`（§5.3）；
5. 关掉第二条路 + `authoritative_ingress = True`。

> **第 ③ 件的工作量不要按「改一行」估。** 它不是把 `source_request_id` 填上
> 就完事：每个适配器内部的 `self.send(...)` / `self.process_message(...)`
> 调用点（全部 7 个适配器合计约 13 处）都要重写成 telegram 的
> `_submit_control_inbound` 形状——提交、看 acceptance、只在安全时告知拒绝原因。
> 这是逐平台任务里最大的一块。

### 7.1 slack（最先做，作为模式的样板）

- `prepare_control_binding`：`auth_test()` → `account_namespace = f"team-{auth['team_id']}"`（或 `bot-{user_id}`），`bot_identity = f"<@{auth['user_id']}>"`。
- 归属证明：把 `<@U…>` 的出现写进 `VALUE_MENTIONS`；Slack 的 `app_mention`
  事件本身就是证明，但仍要把身份放进 mentions 以走同一条闸门。
- `VALUE_CHAT_TYPE`：`event["channel_type"] == "im"` ⇒ `"private"`，否则 `"group"`。
- reply_target extras：`thread_ts`（保住现有的线程内回复行为，`slack.py:234`）。
- delivery：`chat_postMessage`；`SlackApiError` 且 `response.status_code == 429`
  ⇒ `NOT_ACCEPTED_RETRYABLE` + `Retry-After` 头；`invalid_auth`/`channel_not_found`
  ⇒ `REJECTED_PERMANENT`；其余一律 `ACCEPTANCE_UNKNOWN`。
- 删除 `_send_typing` 用发一条 "…" 再删的把戏（`slack.py:297-319`）？**不删**，
  它不经过 delivery pump，是命令级的直连调用，与 `telegram._send_long_message`
  同类。但要在 docstring 里写明它「不报告接受性，只对提示可接受」。

### 7.2 discord

- `prepare_control_binding`：需要先 `login()` 拿到 `client.user`；
  `account_namespace = f"bot-{client.user.id}"`，`bot_identity = str(client.user.id)`。
  注意 discord.py 的 `on_ready` 是在 `start()` 之后才触发的——**phase 1 必须
  等到 `user` 可读**，否则 binding 里的身份是空的，群聊全部 fail-closed。
  用 `await client.login(token)` 即可，不必 `connect()`。
- `VALUE_MENTIONS`：`tuple(str(u.id) for u in message.mentions)`。
- `VALUE_CHAT_TYPE`：`DMChannel` ⇒ `"private"`，否则 `"group"`。
- reply_target extras：无（`destination_id = channel.id` 足够）。
- delivery：`channel.send(text)`；`discord.errors.HTTPException` 且
  `status == 429` ⇒ retryable + `retry_after`；`Forbidden`/`NotFound` ⇒
  permanent；其余 ⇒ unknown。

### 7.3 dingtalk

- `prepare_control_binding`：取 token 的 `_refresh_token()` / `_ensure_token()`
  已有（`dingtalk.py:132-142` 一带）；
  `account_namespace = f"robot-{client_id}"`，`bot_identity = client_id`。
- **归属证明见陷阱 4**：只有 `payload["isInAtList"]` 为真时，才把
  `bot_identity` 放进 `VALUE_MENTIONS`。
- reply_target extras：`robot_code`（出站 `batchSend` 必需）。
- delivery：`POST /v1.0/robot/oToMessages/batchSend`。**现在完全不看响应**
  （`dingtalk.py:316-330`）——必须改为看 HTTP 状态与 body 的 `code`，
  `429`/`requestLimit` ⇒ retryable，`4xx` ⇒ permanent，超时/`5xx` ⇒ unknown。

### 7.4 qq

- `prepare_control_binding`：`account_namespace = f"app-{app_id}"`，
  `bot_identity = app_id`。
- 归属证明：`on_group_at_message_create` 这个回调名本身就是网关的断言
  （只有 @ 过的群消息才会走这个回调）；仅在这个回调里把 `bot_identity`
  放进 `VALUE_MENTIONS`，`on_c2c_message_create` 标为 `"private"`。
- reply_target extras：**`msg_id`（入站消息 id）**——QQ 的被动回复必需。
- delivery：`post_group_message` / `post_c2c_message`，`msg_seq` 见**陷阱 1**。

### 7.5 email

- 无群、无 mention：`bot_identity` **留空**。空身份 ⇒ 任何被标成 group 的
  消息一律 fail-closed（`ingress.py:227-228`），正是想要的。
- `account_namespace = from_address`；`source_request_id = Message-ID`；
  `session_id` 按发件人（`chat_id = from_addr`，与现状一致）。
- reply_target extras：`original_message_id`（`In-Reply-To`/`References`）、`subject`。
- `text_chunk_limit`：显式正数（见 §5.2），**不能**取 `EMAIL` 能力表里的 `0`。
- delivery：`smtplib` 的**类型化**异常，不再用现在的字符串匹配
  （`email.py:379-386` 在异常消息里找 `"550"`/`"auth"`）：
  `SMTPRecipientsRefused`/`SMTPSenderRefused`/`SMTPAuthenticationError` ⇒ permanent；
  `SMTPServerDisconnected`/`socket.timeout`/`SMTPResponseException(4xx)` ⇒ unknown；
  没有 retry-after 概念 ⇒ **永不 retryable**。
- 删除附件落盘死代码（陷阱 6）。
- **`send_media` 是主动关闭，不是删死代码。** `email._smtp_send_attachment`
  （`:455-501`）是一份**能用**的出站附件实现，只是今天没有调用者
  （全仓库 `grep '.send_media('` 零命中）。cut-over 把它关掉，理由与照片入口
  同一条：本层没有产物引用，附件发什么由谁决定无人回答。**要在 §13 里说出来**，
  不能混在「删死代码」里一笔带过。

### 7.6 wechat（含 wecom）

- 无群、无 mention，`bot_identity` 留空，理由同 email。
- `account_namespace`：wecom 用 `f"{corp_id}:{agent_id}"`，mp 用 `app_id`。
- **`platform=` 必须传 `"wechat"`**，不能再传 `f"wechat-{backend}"`（陷阱 12）。
- reply_target extras：`backend`（`"wecom"` / `"mp"`）、wecom 还要 `agent_id`。
- delivery：现有 `_wecom_send_markdown` → 失败退 `_wecom_send_text` 的两段式
  （`wechat.py:398-405`）要保留，但**退化本身不是一次新的 attempt**：
  markdown 被拒退到 text 仍算**同一次** attempt，只有两者都失败才返回分类结果。
  `errcode` 映射：`45009`/`45047`（频率/并发限制）⇒ retryable；
  `40001`/`42001`（token 失效）⇒ **先刷新 token 再重试一次**，仍失败 ⇒ permanent；
  网络异常/超时 ⇒ unknown。
- 入站的图片/语音/位置/链接转文本占位符（`wechat.py:322-348`）**保留**——
  它产出的就是文本，与本层 `Message.content: str` 相容。
- **这是一次安全行为变化，要写进 commit message。** `wechat.py` 今天**完全不读**
  `self.config.allowed_senders`——也就是说 wecom/mp 现在**没有任何 owner 白名单**。
  接进 `SenderPolicy` 会顺带补上这个缺口。这是本计划的净收益，但它改变了一个
  已有部署的可达性（原本能对话的人可能被挡），必须显式说明而不是当作副作用。
- email / imessage 各自有 ad-hoc 的发件人检查；email 的那层在 `SenderPolicy`
  之后成为冗余——**保留**（两层都是 deny-by-default，冗余的方向是安全的），
  但不再是权威，docstring 要说清楚。

---

## 8. 陷阱清单

> 准入规则沿用 0031 §6：**每条都要有一条点名测试或一条变异**。
> 纯流程规矩不进这张表。

**陷阱 1 —— QQ 的 `msg_seq` 必须由 `item_id` 决定，不能由计数器决定。**
QQ 要求回复带入站 `msg_id` 和在该 `msg_id` 下**递增**的 `msg_seq`；现有
`qq.py:251-262` 用一个自增计数器。搬进 delivery adapter 后，`deliver()` 对
同一个 chunk 最多调 3 次（`delivery.py:267`），而 `item_id` 跨 attempt 稳定
（`delivery.py:128-135`）。计数器给法会让重试拿到**新** seq ⇒ QQ 视为新消息
⇒ 用户看到两条一样的回复——这正是 `ACCEPTANCE_UNKNOWN` 存在的理由被绕过。
`msg_seq` 必须是「该 `msg_id` 下 `item_id` 的稳定序号」。
**测试**：同一个 `DeliveryAttemptRequest` 连调两次，两次 `msg_seq` 相同；
两个不同 `item_id`，seq 递增。**变异**：改回计数器 ⇒ 红。

**陷阱 2 —— `chunk_text` 有两个死循环，不是异常。**
`limit <= 0`，以及 `limit <= 20` 且文本进入代码块。见 §5.2 的实测输出。
同步循环，`asyncio.timeout` 打不断，整个进程的所有会话一起卡死。
**测试**：`ChannelSurfaceBinding(..., text_chunk_limit=0)` 与 `=20` 都抛
`ValueError`；`chunk_text("```py\n…", 10)` 在 `SIGALRM` 3 秒内返回。
**变异**：删掉 `max(1, …)` 的夹取 ⇒ 代码围栏那条变红（超时）。

**陷阱 3 —— 把「不知道有没有送到」分类成「可重试」会产生第二条可见回复。**
7 个适配器今天根本没有自己的出站分类：`_send_chunk` 一律不带 try/except，
兜底的是基类 `Channel.send` 的 `except Exception`（`base.py:399`）——它把
**任何**失败都变成一个 `return False`，调用方无从区分「没送到」和「可能送到了」。
各适配器里那些 `except Exception`（`discord.py:251`、`qq.py:343`、
`imessage.py:511`）是 `send_media` 的，不在文本回复路径上。dingtalk 更进一步，
连 POST 的响应都不看（`dingtalk.py:316-330`）。写 delivery
adapter 时最容易犯的错，是把超时判成 `NOT_ACCEPTED_RETRYABLE`——
`delivery.py:172-179` 里**只有这一个** outcome 会被重试，而重试一条可能已经
在用户眼前的消息，比丢一条更糟，且**造成它的进程看不见**。
**测试**：conformance 第 3 项。**变异**：任一 adapter 把兜底 `except`
映射成 retryable ⇒ 红。

**陷阱 4 —— DingTalk / QQ 没有本地可比对的 bot 身份，照抄 telegram 会把群聊全拒或全放。**
`SenderPolicy.admits`（`ingress.py:223-236`）要求 `bot_identity` 非空**且**
出现在 `VALUE_MENTIONS` 里。DingTalk 的归属证明是平台给的布尔
`isInAtList`（`dingtalk.py:261`），QQ 是网关只投递 @ 过的群消息
（`qq.py:171`）——两者都没有「本地已知的 bot id 出现在 mention 列表里」这回事。

**裁决：不改 `SenderPolicy`**（它是三个面共用的安全对象，为一个平台放宽
它等于为三个面放宽）。改为在适配器里把平台的断言**翻译**成这套词汇：
`bot_identity = <client_id / app_id>`，**且仅在平台断言为真时**把该身份写进
`VALUE_MENTIONS`。

这比 Telegram 弱一档，必须写进适配器 docstring：我们验证的是「平台说这条消息
@ 了我们」，而不是「我们自己在 mention 列表里找到了自己」。（Telegram 的
entity 列表同样来自平台，差别只在匹配由谁做。）

**必须被测试拒绝的写法**：无条件把 `bot_identity` 塞进 `VALUE_MENTIONS` ——
那样群闸门恒真，等于没有闸门。
**测试**：群消息 + `isInAtList=False` ⇒ 不产生 exchange。**变异**：改成无条件
塞 ⇒ 红。

**陷阱 5 —— WeChat/WeCom 的 `chat_id` 就是 `sender_id`。**
`wechat.py:353` `chat_id = from_user`。1:1 平台上这是对的，但它意味着
reply_target 的 `destination_id` 与 sender 同值。**要在 docstring 里钉死
「本适配器只支持 1:1」**，并让 `bot_identity` 留空——这样万一哪天有消息被标成
group，闸门会 fail-closed 而不是把群消息回给发言人。
**测试**：构造一条 `VALUE_CHAT_TYPE="group"` 的 wechat 入站 ⇒ 不产生 exchange。

**陷阱 6 —— Email 正在往 `/tmp` 写**攻击者命名**的附件，然后没人读。**
`email.py:265-268` 把附件 `write_bytes` 到 `f"/tmp/email_{mid}_{filename}"`，
结果放进 `results[...]["attachments"]`（`:289`）。实测 `grep -n attachments
email.py` 只有 5 个命中，**全部是写侧**——`["attachments"]` 在全文件里没有
任何读取点。

两个问题叠在一起：

1. **死代码**：写了没人读。
2. **`filename` 来自邮件的 `Content-Disposition` 头**，是未经净化的外部输入，
   直接拼进路径。一个 `filename="../../../tmp/x"` 就写出了 `/tmp` 之外。
   这不是本计划引入的，是本计划**顺手删掉**的。

**整段删除**，与照片路径同一裁决（0031 §5.3）。
**测试**：处理一封带附件、且 `filename` 含 `../` 的信 ⇒ 不产生任何文件写入
（monkeypatch `Path.write_bytes` 断言未被调用）。

**陷阱 7 ——（否定结论）本轮 7 个适配器都不需要跨线程投递。**
0031 陷阱 10（`call_soon_threadsafe`）是 feishu 专属的：lark SDK 在自己的
WebSocket 线程上投递回调，所以有 `_run_async`（`feishu.py:586-599`）。
本轮的 7 个**没有一个**是这样：discord.py / slack_sdk 的 aiohttp Socket Mode /
botpy / `websockets` / aiohttp web server / `asyncio.subprocess` 全是 loop 原生；
email 的阻塞调用走 `run_in_executor`，结果是被 `await` 回 loop 的，不是回调。
**这条写进计划是为了阻止下一个人照抄 feishu 的 `_run_async` 给 slack 也来一份**
——那会凭空增加一个线程边界。
**测试**：conformance 之外加一条源码探针——非 feishu 的适配器源码中不出现
`run_coroutine_threadsafe`。

**陷阱 8 —— 删 `process_message` 会连带三样东西，必须一起收。**
`Channel.process_message`（`base.py:531-597`）是全仓库唯一的
`deliver_reply=False` 生产用法（`base.py:587`）。删它就要一起删：
`ChannelRuntime.submit` 与 `submit_and_wait` 的 `deliver_reply` 参数
（`runtime.py:379/438/452/461`）、`collect_reply` 与 `_report`
（`runtime.py:737-803`）、两处 `__init__.py` 导出，以及
`tests/entry/test_channel_runtime.py:761-801` 那两条专测「8 个未验收适配器走的路」
的测试。漏收一样，就留下一条没有调用者的第二进路。
**测试**：判据 1 的枚举测试——`ChannelRuntime` 的公开签名里不再有 `deliver_reply`。

**陷阱 9 —— `.env.example` 的 retired 契约是一条会变红的测试，要顺着它走。**
`tests/test_env_example.py` 断言 retired 变量「被提到但不可设」
（`_SETTABLE` 正则扫 `^\s*#?\s*NAME=`）。点亮 slack 后，`SLACK_BOT_TOKEN`
必须从 `.env.example` §12 移进一个 live 段、从测试的 `RETIRED` 元组移出、
并至少有一个代表进 `READ_BY_THE_STACK`。**忘了做，测试会抓住你**——
这是好消息，要在任务清单里点名而不是靠记性。

**陷阱 10 —— 适配器模块顶层不能 import 平台 SDK。**
`_surfaces.py:830-832` 的 `--list` 会 `get_channel_class(name)` 从而 import
适配器模块，只为读一个类属性。今天 `telegram.py:216` / `slack.py:87` 都把
SDK import 放在函数内，`telegram_delivery.py:36-48` 用 `lru_cache` 包住。
新写的 6 个 `*_delivery.py` 必须照办，否则没装 `discord.py` 的机器上
`oc channel --list` 会把 discord 显示成 `unavailable`。
**测试**：在 `sys.modules` 里屏蔽全部平台 SDK 的前提下，`--list` 打印 8 行且不抛。

**陷阱 11 —— `platform=` 传的字符串必须等于 binding 的 `adapter`。**
`Channel.inbound`（`base.py:527`）把 `surface = platform or self.name`，而
`ChannelRuntime.submit`（`runtime.py:397`）用 `self._bindings.get(message.surface)`
查 binding。`wechat.py:371-376` 现在传 `f"wechat-{self._backend}"`——
cut-over 后每一条消息都会落到 `CODE_UNKNOWN_ADAPTER`，而那是一条
WARNING 加一次静默拒绝。
**测试**：conformance 第 1 项断言 `binding.adapter == channel.name`，
另加一条：每个适配器归一化出来的 `InboundMessage.surface` 等于 `channel.name`。

**陷阱 12 —— `DedupCache` 是「看到即标记」，而 feishu 已经为此交过学费。**
基类 `DedupCache.is_duplicate()`（`base.py:146-163`）在**第一次看到**消息 id
时就把它记下并返回 `False`。discord（`:169`）、slack（`:200`）、
dingtalk（`:265`）、wechat（`:356-357`）今天全部在 `submit` **之前**调它。

feishu 走的是另一条路，而且把理由写在了代码里
（`feishu.py:525-542` 的 `_is_duplicate_feishu` docstring，逐字）：

> It must NOT mark a message as seen before that acceptance, and does not:
> a failed submission plus a Feishu redelivery inside the TTL would
> otherwise lose the message silently.

**这是一条静默丢消息的路径**：提交失败（队列满、runtime 未启动、网络抖动）之后，
平台在 TTL（默认 3600 秒）内重投同一条消息，本地判重把它当重复丢掉，
于是**用户的消息永远没有被回答，而日志里什么都没有**。

**裁决**：6 个适配器一律改成 feishu 的两段式——`_is_duplicate_*` 只读不写，
`_remember_*` 在 `runtime.submit` 返回 ACCEPTED/DUPLICATE 之后才调。
**测试**：submit 抛 `QueueFull` ⇒ 同一 id 第二次重投仍然产生一次 submit 尝试。
**变异**：改回看到即标记 ⇒ 红。

> **与 `ChannelRuntime._accepted` 的分工（本计划的表态）**：cut-over 后
> `source_request_id` 第一次有真值，`_accepted`（`runtime.py:706-728`）成为
> **权威**的幂等来源。各适配器的 `DedupCache` **保留**，但降级为 feishu
> docstring 里的定位——"An optimization only"，省掉为一条显然的重投重新
> 构造消息。不是双重记账，因为它不再有裁决权。

**陷阱 13 —— `_format_chunk()` 会被 cut-over 静默架空，QQ 和微信 MP 会吐出裸 Markdown。**
`_format_chunk` 全仓库**唯一**的调用点是 `base.py:396`，在即将被删除的
`Channel.send()` 里面。而 QQ（`qq.py:296`）和微信 MP（`wechat.py:409`）
覆写了它，承担的是真实职责：把 Markdown 转成这两个平台能正常显示的纯文本。

新出站路径是 `runtime._pump_reply` → `chunk_text` → `delivery.deliver` →
`*_delivery.py`，**全程对 `_format_chunk` 零调用**（实测 grep）。所以
cut-over 当天，QQ 和微信 MP 的用户会看到 `**粗体**` 的星号。

而 conformance 第 3 项只分类 accept/reject，**抓不到内容层面的回归**——
这正是它需要单独一条断言（第 8 项）的原因。

**裁决**：格式化职责迁进各自的 `*_delivery.py`，在 `_send_*_arguments` 之前
施加。理由是它属于"这个平台怎么收一条消息"，与 reply_target 的校验同层；
放在 runtime 里会让 runtime 知道九种 Markdown 方言。
`base.Channel._format_chunk` 随基类 `send` 一起删除。
**测试**：conformance 第 8 项。**变异**：delivery adapter 直接透传 `request.text`
⇒ QQ/微信那两条红。

---

## 9. launch 层：8 个 builder，**不**做配置 DSL

现在 `_CHANNEL_BUILDERS` 两项（`_surfaces.py:1073`）。要补到 8 项（iMessage 已按 §6.1 删除，
不占名字）。

**诱惑**：把每个 channel 写成一张声明式的表
（`{required: [...], ints: {...}, senders: "X_ALLOWED_SENDERS"}`）然后一个
通用 builder 吃它。**拒绝**：那是把 8 个 10-20 行的函数换成一个必须表达
「wechat 的两个后端二选一」「email 的四个必填跨 IMAP/SMTP 两组」的小语言。
`launch/_surfaces.py` 的模块 docstring 已经把这件事说清楚了（见 §3 判据 2 的
引文）：**哪些变量指代一个部署，是进程外壳的知识**——而这种知识写成 `if`
比写成表更容易读。

**做法**：保持「一个 channel 一个 `_build_x(env)` 函数」，补齐六个新 builder，
并只抽出三个已经重复的原语：

- `_allowed_senders(env, var)` —— 已有（`:987-990`）
- `_as_int(env, var, default)` —— 已有（`:993-1000`）
- `_required(env, var, why)` —— **新增**，取代现在每个 builder 里
  `if not x: raise AppConfigError(...)` 的三行重复
- `_as_bool(env, var, default)` —— **新增**，email 的
  `EMAIL_IMAP_USE_SSL` / `EMAIL_SMTP_STARTTLS` / `EMAIL_MARK_SEEN` 需要

每个 builder 落在 10-25 行，显式、可 grep、与现有两个同形。

**每个 builder 必须在这里（而不是在适配器里）拒绝的东西**：白名单为空。
理由 `_build_telegram` 的 docstring（`:1004-1013`）已经写过：两处都是
「这个部署没配好」，必须是同一类事件；留给适配器抛 `RuntimeError` 会让
外壳只能报成「意料之外的失败」。

---

## 10. 收尾：删掉第二条路，再删掉旧 `surfaces/channels/`

### 10.1 第二条路（见陷阱 8）

| 删除 | 位置 | 删除后的替代 |
|---|---|---|
| `Channel.process_message` | `base.py:531-597` | `runtime.submit(self.inbound(...))` |
| `collect_reply` + `_report` | `runtime.py:737-803` | delivery pump |
| `submit(deliver_reply=)` 与 `submit_and_wait(deliver_reply=)` | `runtime.py:379/438/452/461` | 唯一取值恒为 `True` |
| `Channel.send` 通用实现 | `base.py:380-401` | delivery pump |
| `_send_chunk` 抽象方法 | `base.py:403-419` | 各 `*_delivery.py` |
| `Channel._format_chunk` | `base.py:433-438` | 各 `*_delivery.py`（陷阱 13） |
| `Channel.send_media` + 8 处覆写 | `base.py:421-429` 等 | **无**——见下 |

> **`send_media` 是主动关闭一条能力，不是删死代码。** 全仓库
> `grep '.send_media('` **零命中**：8 个适配器的覆写今天全部没有调用者。
> 但 email（`:455-501`）、wechat、qq、slack 的实现是**写好且能用**的，
> 与陷阱 6 那段「写了没人读」的附件落盘不是一回事。关掉的理由是本层没有
> 产物引用（0031 §5.3 的同一条裁决），**必须在 §13 里说出来**。
>
> **删基类实现比「覆写成拒绝」干净。** `telegram.py:366-375` 现在是覆写成
> 抛 `RuntimeError`；8 个适配器全部 cut-over 后基类实现没有调用者，
> 「没有这个方法」好过「有但会抛」。**代价是 conformance 断言 2 的形状**——
> 见 §5.4 第 2 项，它从一开始就要写成两阶段兼容的。
>
> 唯一保留的直连出站，是命令级短回复（`telegram._send_long_message:480-497`、
> slack 的 typing 占位）。它们本来就不走 `send`，也不需要接受性分类。

### 10.2 删除 `omicsclaw/surfaces/channels/`

**这一步很便宜，但不要把理由说过头。** 实测的真实状态是**半死**，不是全死：

```
$ python -m pytest tests/bot/ tests/test_channels.py --collect-only -q
ERROR tests/bot/test_channel_cutover_gate.py
ERROR tests/bot/test_commands_registry.py
ModuleNotFoundError: No module named 'omicsclaw.runtime.agent'

$ python -m pytest tests/test_channels.py -q
15 failed, 44 passed in 0.33s
```

**四个模块在 import 层面就坏了**，因为它们引用的包已被删除：

| 模块 | 坏在哪 | 被删的包与提交 |
|---|---|---|
| `base.py:492-494` | `omicsclaw.runtime.agent.dispatcher` | `259fb52a` |
| `telegram.py:20` | `omicsclaw.control` | `33720785` |
| `__main__.py` | `omicsclaw.providers.registry` | `33720785` |
| `imessage.py:39` | `omicsclaw.skill.execution.environment`（包名本就写错，应为 `omicsclaw.skills`） | 从未存在 |

**其余模块仍可独立 import 并通过测试**——slack / discord / dingtalk / wechat /
qq / email / capabilities / config / `chunk_text` / `DedupCache` / `RateLimiter`
合计 44 个用例现在是绿的。

**所以删除的理由不是「它已经死了」，而是「`entry/channel/` 取代了它」。**
这个理由独立成立，且更诚实：删除会连带丢掉 44 个目前能跑的用例，
而它们测的东西已经由 `tests/entry/test_channel_*` 和新的 conformance 套件覆盖——
**任务 F 的验收里要逐条确认这件事，不能默认。**

删除清单：

| 项 | 动作 |
|---|---|
| `omicsclaw/surfaces/channels/`（20 文件 / 7,059 行） | 删 |
| `tests/bot/test_channel_cutover_gate.py`、`tests/bot/test_commands_registry.py` | 删（**当前就收集失败**，删掉是净收益） |
| `tests/bot/test_inbound_pipeline.py`、`tests/test_channels.py` | 删或改指向 `entry.channel`（先看它们还测什么） |
| `tests/entry/test_assembly.py`、`tests/entry/test_channel_commands.py` 里的 `surfaces.channels` 引用 | 改指向 `entry.channel` |
| ~~`.github/workflows/pr-ci.yml`~~ | **已于 2026-09-21 按 owner 裁定整体删除**——它的 `bot-core-test` job 直接点名跑 `tests/test_channels.py`（`:216`），而那个 job 本来就已经是红的。CI 等新框架定型后重建，**本计划不负责恢复它**。实现者不要为 CI 补任何东西。 |
| `Makefile:158-168` 的 `bot-telegram` / `bot-multi` / `bot-list` | 改成 `oc channel --channels …` / `oc channel -- --list` |
| `CLAUDE.md` §Surfaces 的 Channel 行与全部 `python -m omicsclaw.surfaces.channels` 示例 | 改成 `oc channel` |
| `_surfaces.py:163` `CHANNEL_USAGE` 里指向 `omicsclaw/surfaces/channels/README.md` 的那句 | 改指向 `.env.example` |
| `.env.example` §12 里被点亮平台的变量 | 移进 live 段（陷阱 9） |
| `README.md` | 按维护契约记录这次里程碑 |

**明确不在本计划范围**：`omicsclaw/surfaces/cli/` 与 `omicsclaw/surfaces/desktop/`。
它们还有活的引用——`diagnostics.py:193/199` import `surfaces.cli._session` 与
`_mcp`，`remote/routers/env.py:46` import `surfaces.desktop.server`。
**实现者不要顺手删整个 `surfaces/` 树。**

---

## 11. 任务切分

每个任务自带验收，可独立派给一个子 agent。

> **B/C/D 在代码上无依赖，但在一个文件上冲突：** 三者都要往同一份新文件
> `tests/entry/test_channel_cutover_conformance.py` 里加参数化用例。
> 并行派三个子 agent 几乎必然产生合并冲突。**做法**：任务 A 把该文件的
> 参数化骨架写成「遍历 `CHANNEL_REGISTRY` 里 `authoritative_ingress` 为真的
> 适配器」，B/C/D 就**不需要碰这个文件**——它们只改适配器和自己的
> `test_channel_<platform>.py`，conformance 自动把新点亮的适配器纳入。
> 这也是 §5.4 选参数化而不是逐平台写用例的另一个理由。

| 任务 | 内容 | 依赖 | 验收 |
|---|---|---|---|
| **A** 接缝与守卫 | `reply_target.py`（§5.1）**并把已在生产的 telegram/feishu 迁过去**——否则它们过不了 conformance 第 4 项；`chunk_text` 夹取 + `binding` 守卫（§5.2）；`Channel.command_context` 并把 **feishu 也接上 `dispatch`**（§5.3）；conformance 骨架（此时只覆盖 telegram/feishu） | — | 现有 1021 条全绿；telegram **与 feishu** 都过 conformance 八项 |
| **B** slack + discord | §7.1、§7.2 的四件事 + 各自的点名测试 | A | conformance 对 4 个适配器全绿 |
| **C** dingtalk + qq | §7.3、§7.4；重点是陷阱 1 与陷阱 4 | A | 同上；陷阱 1/4 的变异测试各自变红 |
| **D** email + wechat | §7.5、§7.6；重点是陷阱 2、5、6、11 | A | 同上；删附件落盘的测试通过 |
| **E** launch builders | §9 的 6 个 builder + 两个新原语；`.env.example` 与 `tests/test_env_example.py` | B、C、D | `oc channel --list` 显示 **9 个名字、8 个 authoritative**（imessage 此时尚在注册表，任务 F 才删）；`--channels slack` 在缺凭据时报 `AppConfigError`；`--channels imessage` 仍报「disabled pending cutover」 |
| **F** 收尾 | §10.1 删第二条路（含 `_format_chunk`、`send_media`）；**§6.1 删 imessage**；§10.2 删旧包与文档同步 | E | 全量 `pytest tests/` 的收集错误从 2 变 0；`CHANNEL_REGISTRY` 八项且八项全 authoritative；判据 1 的枚举测试存在；**逐条确认 §10.2 那 44 个用例覆盖的行为已被新测试接管** |

> **任务 F 会让 conformance 断言 2 换一种成立方式**（「抛」变成「没有这个属性」）。
> §5.4 第 2 项已经写成两阶段兼容，但 F 的验收要显式跑一遍
> conformance——否则 B/C/D 留下的绿会在 F 之后集体变红而没人发现。

---

## 12. 验证

```bash
# 基线：开工前**重新采一次**，不要用这里的数字
python -m pytest tests/entry/ tests/launch/ -q
#   本计划撰写期间两次采样得到 1021 与 1022 passed（工作区有未提交改动），
#   所以这里记的是方法而不是数字：任务 A 开工前采一次并写进 commit message。

# 每个任务后
python -m pytest tests/entry/ tests/launch/ -q

# 任务 F 后，收集错误必须归零
python -m pytest tests/ --collect-only -q 2>&1 | tail -5
#   基线：ERROR tests/bot/test_channel_cutover_gate.py
#         ERROR tests/bot/test_commands_registry.py

# 无 SDK 环境下的注册表（陷阱 10）
oc channel -- --list
```

> 测试在 `rapids_singlecell` 环境下跑（默认 python 没有 pytest）。

---

## 13. 明确**不**做的事

1. **不改 `SenderPolicy` / `InboundMessage` / `Acceptance`**。它们是三个面共用的，
   为一个平台放宽等于为三个面放宽（陷阱 4）。
2. **不做附件 / 多模态**，并且**主动关闭出站媒体**。`Message.content: str`
   没有 content parts，这是 schema 层的已知缺口（0031 §5.3）。本计划做两件事：
   **删除**已经在往磁盘写、没人读的入站附件落盘（陷阱 6）；**关闭**
   `send_media`——它在 email / wechat / qq / slack 上是写好能用的实现，
   今天零调用者，关掉的理由是本层没有产物引用，不是它坏了。
   哪天做产物引用，它按本计划的 delivery 模式重新接回来。
3. **不补 email 的跨重启幂等性。** 现在靠 IMAP `\Seen`（`email.py:277-278`），
   fetch 之后、置位之前进程死掉，重启会重答。cut-over 后 `Message-ID` 成为
   `source_request_id`，但 `ChannelRuntime._accepted`（`runtime.py:706-728`）
   **只在同一进程内**解重复。持久化是 0031 §11 明确推迟的，不是 email 独有的
   缺陷。**写进适配器 docstring，不写进代码**——这条曾经放在陷阱清单里，
   但它没有测试也没有变异，破坏了 §8 自己的准入规则，所以搬到这里。
4. **不做持久化 outbox**。0031 §11 已推迟；上一条是它在 email 上的具体表现。
5. **不做多账号**（一个进程两个 Feishu app）。`ChannelRuntime` 按 adapter 单键
   索引并显式拒绝两个同名 binding（`runtime.py:285-293`），
   `binding.account_key` 是为那一天留的钩子，本计划不碰。
6. **不删 `surfaces/cli/` 与 `surfaces/desktop/`**（§10.2 末）。
7. **不给 channel 面加流式回复**。`DEFAULT_DELIVERED_TYPES`
   （`runtime.py:140-184`）的理由逐条成立，且它已经是可配置的——
   想要流式的部署传自己的集合即可。

---

## 14. 这份计划回答的问题

- **「为什么只有两个接了？」** —— 三道门是一致且故意的（§1），
  0031 §5.3 的原话是「搬，但不验收」。
- **「接一个平台要做什么？」** —— 四件事（§7 开头），其中多数平台的
  idempotency key 已经算好了只是没往下传（§2 的表）。
- **「怎么在不造框架的前提下保证 8 个实现一致？」** —— 三条窄接缝管静默失败，
  一份八项断言的 conformance 测试管其余（§5）。
- **「全部都接吗？」** —— 8 个平台全接；iMessage 缺前提，owner 裁定删除（§6.1）。
  收尾后「注册了但不能启动」这个状态不再存在。
- **「旧包怎么删？」** —— 它是**半死**（4 个模块 import 就坏，其余 44 个用例仍绿），
  删除的理由是被 `entry/channel/` 取代而不是「它已经死了」，清单在 §10.2。
