# 计划 0031 — 入口层 `omicsclaw/entry/`（装配根 / 会话 / 回合 / 事件流 / 三面适配器）

框架重建第 6 步。前序：0026（provider）、0027（engine）、0028（tool
registry）、0029（foundation tools）、0030（context 组装层）。交接文档是
`docs/FRAMEWORK-REBUILD.md`。

本层的存在依据是交接文档自己写下的一句话
（`docs/FRAMEWORK-REBUILD.md:739-741`）：

> 替代物是 **一个新的入口/交互层**，由 owner 单独设计，输入是 harness9
> 加上现有的 CLI / Channel / Desktop 三个 Surface。工具可见性如果还回来，
> 是那一层的事。

> **owner 范围修正（2026-09-19，评审之后到达）**：「计划里的 channel、cli
> 和 desktop app 可以复用当前项目已实现的相关代码组件，只是说需要你帮我
> 搭建一个高内聚低耦合的 entry 组件，使其不要干扰到 agent main loop。」
>
> 这条修正改的不只是工作量，是**依赖箭头的方向**：三个面不再由本层重建，
> 而是**由它们来 import `entry`**。落地见 §2、§4 Q23、§5（整张表的默认值
> 从「丢弃/重建」改为「**复用**」）、§7 Task D 与 §10。**本层因此不含
> `cli/` `desktop/` `channel/` 三个子包。**

> **实现已开始，§3.2 已被代码取代（2026-09-19）。** Wave 1 交付了
> `config.py` / `ingress.py` / `assembly.py` / `events.py` / `stream.py` /
> `render.py` / `turn.py`。**凡是已落地的符号，一律以代码为准**——§3.2 是
> 实现前的草图，前一轮评审已证明它有 6 处与实际不符，实现阶段又发现 10 处
> 需要增补。实测签名与增补清单见附录 B。
>
> **§12-1（skill 整体预留）已被 `docs/plans/0032-skill-loader.md` 取代**
> （owner 协调两个会话后的结果）：新的 `omicsclaw/skills/` 已建好并接进
> `assembly.py`，`SkillsIndex` / `build_skill_index` 在 `entry` 的公开面上。
> 落地见 §12-1 与 Q10 的「已被取代」块。

> **本文件已过一轮双盲独立只读评审（实现前）并全量修复，见附录 C。**
> 评审改掉了 §3.2 API 草图的 6 处会当场报错的断言、§3.3 规范时序的压缩
> 分支、以及 §5.0 的一条裁决边界。**附录 C 是本计划最该先读的部分**：它
> 记录了哪些话原本是错的，以及为什么那种错法当时看起来是对的。

---

## 0. 材料来源与可核实性

| 材料 | 位置 | 本计划的用法 |
|---|---|---|
| harness9 装配根 | `cmd/harness9/main.go`(470) | **全文逐行读过**。本计划所有 `main.go:NN` 均实测 |
| harness9 CLI 面 | `cmd/harness9/cli.go`(105) | **全文逐行读过** |
| harness9 TUI 面 | `tui.go`(377) **全文读过**；`tui_update.go`(1883)、`tui_view.go`(727)、`tui_banner.go`(55) **只读函数清单，未逐行** | 前者用作事件泵的证据；后三者只用来数「一个成熟 TUI 有多大」（非测试合计 **3,042** 行），不引用其内部行为 |
| harness9 事件契约 | `internal/engine/stream.go`(248) | **全文逐行读过**。审批死锁那条消费者契约是陷阱 1 的来源 |
| harness9 自述分层 | `AGENTS.md:408-474`（架构分层图 + 模块职责表） | 用作「入口层在它的分层里处于哪一格」的证据 |
| harness9 `upgrade.go`(312) | 未读 | **不作依据**。自升级是发行渠道的事，本仓库走 conda/pip/npm 三条线 |
| 已交付五层 | 工作区 `omicsclaw/{schema,provider,engine,tools,context}/` 的**实际代码与公开面** | §3、§4 的所有接缝裁决只依据代码。**§3.2 的每一个签名均由 `inspect.signature` 实测**（这是附录 C 的直接产物） |
| 旧 Surface 层 | 工作区 `omicsclaw/surfaces/`，**68 个 `.py` / 38,412 行** | §5 能力对照表的输入。**逐文件读过的只有 `__init__.py`(16) 与 `cli/launcher.py`(24)**；其余依据文件名、行数、import 实测与既有文档 |
| **旧控制面的流式投递实现** | `git show HEAD:omicsclaw/control/event_hub.py`（已 staged 删除）、工作区 `surfaces/desktop/turn_observation.py`、`surfaces/channels/*_delivery.py` | **§4 Q14 的依据**。这三处解决的是跨进程流式投递本身，不是旧框架的特性 |
| **Desktop 前端工程** | `/workspace/algorithm/zhouwg_project/OmicsClaw-App/`（Electron + Next.js）。**读过**：`src/app/api/chat/route.ts`(1303) 的后端调用段与 SSE 处理段、`CONTEXT.md` 头部、API 路由清单（`ls src/app/api` 共 33 组）。**未读**：渲染层、Electron 主进程、测试 | **§4 Q24 的依据**。它是 `/chat/stream` 契约的**消费方**，本层是实现方 |
| **三面耦合度实测** | `grep -cE` 已删包引用行数，逐文件 | §2 与 §5.0.1。**耦合密度 0.39%**（38,412 行 ← 148 行）。复现命令在 §5.0 |

五条声明，先说在前面：

1. **旧 Surface 层已经半死。** 68 个文件里 **30 个** import 了已被 staged
   删除的包。实测：

   ```
   omicsclaw.surfaces.cli.interactive   → ModuleNotFoundError: omicsclaw.control
   omicsclaw.surfaces.channels.telegram → ModuleNotFoundError: omicsclaw.control
   omicsclaw.surfaces.cli._main         → 可导入
   omicsclaw.surfaces.channels.base     → 可导入
   ```

   **今天这个仓库里，从一条用户消息到新引擎没有任何一条通路**，而
   `oc list` / `oc run <skill>`（非 Surface 的技能运行器）仍然活着。这不是
   本计划要修的 bug，这是本计划存在的原因。

2. **本机缺 `fastapi` 与 `textual`，有 `prompt_toolkit`(3.0.52) / `rich` /
   `click`(8.3.1)；缺 `pytest-asyncio`、缺两个厂商 SDK。** 解释器是
   `/opt/conda/envs/rapids_singlecell/bin/python` = **3.13.11**，而默认
   `python3` 是 3.10.14、会失败。Desktop 面的 HTTP 半边与任何 Textual TUI
   **在本机不可测**，§2 的范围裁决受此约束，且**不得**在 docstring 里断言
   未测过的行为。

3. **裁定 0 仍然有效**（`docs/plans/0030-context-assembly-layer.md:2675`）：
   「舍弃原本旧框架的相关能力，一律以 harness9 的相关能力为主」。§5 的默认
   值因此是「旧层独有 ⇒ 丢弃」。**例外有两类**，理由见 §5.0。

4. **harness9 的入口层是单会话、单终端、单进程。** OmicsClaw 三面里有两面
   天然并发（Channel 的多会话交错是构造性的，`omicsclaw/tools/context.py`
   的原话），且有一面在 HTTP 另一侧。**参考实现在这两处没有对应物**，Q6 与
   Q14 各自单独论证——这是本计划唯一两处结构性增量。

5. **工作区基线**：`git status --porcelain` 为 `320` 条 `D `、`4` 条 ` M`、
   `1` 条 ` D`、`19` 条 `??`（**本文件自身已在 `??` 这 19 条里**，与 0030
   的记法一致）。§9 的验收一律按**相对此基线的净增量**判定。

---

## 1. 背景与目标

### 1.1 这一层要解决什么

已交付的五层各自完整，但**没有一个能被用户碰到**：

| 层 | 它知道什么 | 它不知道什么 |
|---|---|---|
| `schema` | 消息长什么样 | 消息从哪来 |
| `provider` | 怎么跟某个厂商说话 | 说什么 |
| `engine` | `run(messages)` 怎么跑到收敛 | messages 从哪来、跑完存哪 |
| `tools` | 一个工具怎么执行、跟谁要授权 | 谁是「谁」、工作区在哪 |
| `context` | 怎么组装、怎么估、怎么压 | 人格文件在哪、模型上限是多少、谁调用它 |

每一层的 docstring 都把缺口点了名：

- `omicsclaw/engine/loop.py:34-38` —— 「对话到达时已经组装好」。
- `omicsclaw/context/__init__.py` —— 「`SOUL.md`、技能索引、模型表、写摘要
  的模型，全都是**装配根**的知识」。
- `omicsclaw/context/compaction.py:152-153` —— `CompactionState`「由调用方在
  回合之间携带；**第 6 步**决定它住在哪」。
- `omicsclaw/tools/builtin/__init__.py` —— 「挂载一个基础工具永远是一次
  『**哪个**工作区』的决定，而这个决定属于**组装注册表的那个人**」。
- `omicsclaw/tools/context.py` Q4.2 —— 「谁设置（out-of-band 通道）？
  **Surface**，在进入 agent 回合之前设置一次」。

五处指的是同一个还不存在的东西。本层就是它。

### 1.2 目标

1. **一个装配根**：把五层按依赖顺序装成一个可运行对象，对标
   `cmd/harness9/main.go`。除它之外，进程里不应有第二处知道
   「provider + registry + assembler + engine 怎么拼」。
2. **一个回合内核**：拥有对话历史**与压缩状态**，按固定时序执行
   `render → assemble → measure → compact → run_stream → persist`。这是
   `omicsclaw/context/` 唯一的生产调用点。
3. **一条有身份的事件流**：`TurnEvent` 带单调 `seq`，一个回合的事件可被
   **多次、从任意游标**观察。这是 Desktop 断线重连与 Channel 重投递的前提，
   也是本计划从评审里学到的最重要一条（Q14）。
4. **一份窄契约**，窄到三个现有 Surface 只需**改接**而不是重写。衡量标准
   是可核实的：`channels/telegram.py`(752) 与 `feishu.py`(766) 今天只缺
   `ChannelSurfaceBinding` **一个符号**（实测），改接后它们应当仍然只依赖
   一个符号。
5. **近乎纯新增**：`omicsclaw/` 下**恰好一处**既有文件的改动——导出
   `Workspace`（§4 Q15，**唯一声明的修订**，照 0027 只带一条 schema 修订的
   先例）。不改 `pyproject.toml`，不动 `oc` 控制台脚本，**也不改三个面的任何
   一行**——改接是后续任务，每面一个（§10）。

### 1.3 非目标（写出来免得被当成遗漏）

- **不做 TUI。** REPL 先行、TUI 后补，是 harness9 自己的顺序。
- **skill 整体预留**（Q10，owner 裁定）：不接 `use_skill` 工具，也不注入
  技能索引段——当前的 skill 正在等重新设计与迁移。
- **不接 MCP、sub-agent、hooks/permission、observability**。四样在 harness9
  都是独立包，在本仓库同样应当是独立步骤。本层只保证接缝不被堵死（Q13）。
- **不做持久化。** `SessionStore` 是 Protocol + 一个内存实现（Q4）。
- **不迁移、不删除旧 `omicsclaw/surfaces/`。** §10。

---

## 2. 范围与非范围（一句话版本）

**范围**：`omicsclaw/entry/` 一个新包（**9 个核心模块 + `cli/` `desktop/`
`channel/` 三个子包**）、`tests/entry/` 一个新测试目录、以及 §4 Q15 那一行
声明修订。

**非范围**：`omicsclaw/` 下的其他任何文件、`pyproject.toml`、`omicsclaw.py`、
`skills/` 的内容、**旧 `omicsclaw/surfaces/` 的任何一行**（它是本步的**输入**
——被读取、被移植，不被修改；删除属迁移，§10）。

**「复用」在本计划里的准确含义**（owner 范围修正）：把现有实现里**已经干净**
的代码搬进 `entry/<面>/` 并改接新契约，而不是在旁边重写一个。三个面的干净
比例实测如下——这是 §5 全表的依据：

| 面 | 直接可复用 | 已焊死 | 焊在哪 |
|---|---|---|---|
| Channel | **4,111 行** | 2,948 | `telegram.py`/`feishu.py` 只缺 **`ChannelSurfaceBinding` 一个符号** |
| CLI | 4,880 行 | 10,056 | `interactive.py` 缺 `ControlRuntime` + `RunRuntime` |
| Desktop | 4,886 行 | 11,515 | `server.py`(9,454) 缺 `ControlRuntime` + `RunRuntime` + 治理状态 |

口径：文件级，`^(from\|import) omicsclaw\.(control\|runtime\.{agent,context,
tools,storage}\|providers\|memory\|execution)` 命中即判「已焊死」。复现命令
在 §5.0。

---

## 3. 目标架构

### 3.1 模块清单

```
omicsclaw/entry/
├── __init__.py       公开面                                    ~60
├── config.py         AppConfig + resolve_app_config            ~220
├── assembly.py       build_app() / AgentApp / aclose()         ~280
├── session.py        Session / SessionStore / SessionRegistry  ~320
├── turn.py           TurnRunner —— 一个回合的规范时序           ~340
├── stream.py         TurnStream：seq + 有界 ring + 多观察者     ~280
├── events.py         TurnEvent / TurnEventType                 ~230
├── approval.py       ApprovalBroker                            ~190
├── render.py         TextRenderer（有状态）+ to_wire（纯）      ~240
├── ingress.py        InboundMessage / SenderPolicy / 投递三态   ~230
├── cli/              **移植** surfaces/cli 的干净部分 + 改接     ~600
├── desktop/          **移植** wire_contract + _chat_sse + 路由   ~500
└── channel/          **移植** surfaces/channels 的干净部分       ~700
                                                       合计 ~4,150
```

**三个子包的性质是「移植 + 改接」，不是「重写」**（owner 范围修正）。每个
子包的输入是现有实现里**已经干净**的那部分（实测：不 import 任何已删包），
改动只发生在它与 agent 的那一条接缝上。逐包的输入清单与行数见 §5，
「哪些不搬」也在那里逐行写明。

> **判据**：一个子包如果最后**重写**的行数超过它**移植**的行数，说明它
> 选错了输入——停下来重新划边界，而不是继续写。这条写进 §9 验收。

行数是**预算不是目标**；超出 20% 要在附录 B 里给理由。

### 3.2 公开 API 草图

> **本节的每一个外部符号与签名都由 `inspect.signature` 实测过。**
> 附录 C 记录了未实测的那一版错在哪——6 处里有 4 处会当场抛异常，另 2 处
> 会静默地让功能消失而测试全绿。

```python
# ---- config.py -----------------------------------------------------
@dataclass(frozen=True, slots=True)
class AppConfig:
    workspace: Path                    # 工具沙箱根；默认 cwd（main.go:5 同构）
    model: str = ""                    # 空 = 交给 provider_from_env 检测
    provider: str = ""
    tool_timeout_s: float = 600.0      # ⚠️ 单一真相源，owner 已裁定，见 §12-2
    max_turns: int = 50
    prompt_files: tuple[Path, ...] = ()
    summary_model: str = ""
    summary_timeout_s: float = 90.0    # ⚠️ 套在 Summarizer 上，不是 compact 上（Q11）
    approval_timeout_s: float | None = None   # Channel 面必须给非 None（Q12）
    turn_timeout_s: float | None = None       # 回合级 wall-clock 上限（Q12）
    compact_at: Pressure = Pressure.FULL      # ⚠️ 不是 HIGH；Pressure 无 HIGH
    max_queued_per_session: int = 2
    delta_ring_size: int = 2048
    max_sessions: int = 256

    def engine_config(self) -> EngineConfig: ...
    def bash_timeout(self) -> float: ...   # = tool_timeout_s - ENGINE_TIMEOUT_MARGIN
    # tool_timeout_s 是这两个数的**唯一**来源：EngineConfig(tool_timeout=T) 与
    # BashTool(timeout=T-15) 都由它派生。**禁止**在别处再写一次任何一个数
    # （§12-2：两个独立字面量 = 迁移那天只抬一半，而半个机制不帮忙）。

def resolve_app_config(argv=None, env=None, **overrides) -> AppConfig: ...
# 本函数是整个进程里唯一读 env / 读 argv 的地方（Q8）。例外恰好一个：
# provider 的密钥仍由 provider_from_env 自己读——搬过来只会多一个泄漏面。

# ---- assembly.py ---------------------------------------------------
@dataclass(frozen=True, slots=True)
class AgentApp:
    provider: LLMProvider
    registry: ToolRegistry          # ⚠️ 必须原样交给 AgentEngine，见 Q16
    engine: AgentEngine
    prompt: PromptAssembler         # ⚠️ 不是 AssembledPrompt；render() 在它身上
    tools_snapshot: tuple[ToolDefinition, ...]
    budget: ContextBudget
    summarizer: Summarizer | None
    config: AppConfig
    sessions: SessionRegistry

    async def aclose(self) -> None: ...   # 停机（Q17）

def build_app(config: AppConfig, *, tools=None, sections=None) -> AgentApp: ...
# tools=None   → 默认挂 6 个基础工具，全部用同一个 Workspace（唯一构造点）
# sections=None → 默认段集合，见 Q9
# 两个参数都可注入 ⇒ 测试不碰环境，迁移不改本函数，子 agent 造子 app 是一次调用。

# ---- session.py ----------------------------------------------------
@dataclass
class Session:
    session_id: str
    history: tuple[Message, ...] = ()         # ⚠️ 不含 system 消息（Q3）
    compaction: CompactionState = CompactionState()   # ⚠️ 不存它 = 每次从白纸重摘要
    created_at: float = ...
    values: Mapping[str, Any] = ...           # 会话级事实；回合级在 TurnRunner 合并

class SessionStore(Protocol):
    async def load(self, session_id: str) -> Session | None: ...
    async def save(self, session: Session) -> None: ...
    async def list(self, limit: int = 50) -> Sequence[Session]: ...
# 持久记忆层将来**结构性**满足它，不 import omicsclaw.entry——
# 与 ToolExecutor 对 ToolRegistry 的关系完全同构。

class SessionRegistry:
    async def submit(self, session_id: str, text: str) -> TurnHandle: ...
    # ⚠️ **立刻**返回 handle（可能处于 QUEUED），不在锁上阻塞（Q7）
    def observe(self, turn_id: str, *, after_seq: int = 0) -> TurnObservation: ...
    async def shutdown(self, grace_s: float) -> None: ...

# ---- stream.py -----------------------------------------------------
class TurnStream:
    """一个回合的事件真相。单调 seq + 有界 delta ring + 不丢的控制事件。"""
    def publish(self, event: TurnEvent) -> None: ...      # 永不阻塞
    def observe(self, *, after_seq: int = 0) -> TurnObservation: ...
    def observer_count(self) -> int: ...

class TurnObservation:
    def __aiter__(self) -> AsyncIterator[TurnEvent]: ...
    # 游标落后到已被淘汰 ⇒ 先收到一条 GAP 事件（带 oldest/latest），不静默跳号

# ---- turn.py -------------------------------------------------------
class TurnHandle:
    turn_id: str
    state: Literal["queued", "running", "terminal"]
    def observe(self, *, after_seq: int = 0) -> TurnObservation: ...  # 可多次调用
    async def approve(self, request_id: str, decision: ApprovalDecision) -> None: ...
    #   ⚠️ 未知或已结算的 request_id 是 no-op，不抛（Q18）
    def cancel(self) -> None: ...

# ---- events.py -----------------------------------------------------
class TurnEventType(StrEnum):
    EXCHANGE_START     # 一次用户往返开始（本层独有）
    QUEUED             # 前面还有 N 条（Q7）
    CONTEXT            # 携带 BudgetReport —— 引擎结构性没有（Q19）
    COMPACTION         # 压缩发生在 run() 之间，引擎看不见
    TEXT_DELTA         # 直通  ┐
    REASONING_DELTA    # 直通  ├ 可丢（有界 ring）
    PROGRESS           # 工具进度（Q20）             ┘
    TOOL_START         # 直通  ┐
    TOOL_RESULT        # 直通  │
    APPROVAL_REQUIRED  # 引擎结构性没有（Q5）│ 永不丢
    APPROVAL_SETTLED   #                     │
    TURN_END           # 直通：**每次模型调用一次**，非每次用户往返（Q21）│
    GAP                # 游标被淘汰                                      │
    EXCHANGE_END       # 终止帧，恰好一条                                ┘

@dataclass(frozen=True, slots=True)
class TurnEvent:
    type: TurnEventType
    seq: int                       # 本回合内单调，从 1 开始
    session_id: str
    turn_id: str
    engine: EngineEvent | None = None      # 直通类携带原件，不重新打包
    approval: ApprovalRequest | None = None
    request_id: str = ""
    progress: ProgressUpdate | None = None
    report: BudgetReport | None = None
    compaction: CompactionRecord | None = None
    terminal: Literal["converged", "cancelled", "failed"] | None = None
    error: BaseException | None = None     # 原件，不转字符串
    gap: tuple[int, int] | None = None      # (oldest_available, latest)

# ---- render.py -----------------------------------------------------
class TextRenderer:                        # 有状态：Channel 要跨事件攒批
    def feed(self, event: TurnEvent) -> str | None: ...
    def flush(self) -> str: ...
def to_wire(event: TurnEvent) -> dict[str, Any]: ...   # 纯函数，JSON 可序列化

# ---- ingress.py ----------------------------------------------------
# 三个面共用的「谁进来、回话有没有被收下」。名字与字段尽量沿用旧控制面，
# 因为三个面今天就在按这些名字 import（Q23 的逐行证据）。
@dataclass(frozen=True, slots=True)
class InboundMessage:                      # ← 旧 RawInboundV1 的对应物
    text: str
    session_id: str
    source_request_id: str                 # ⚠️ 必填，且幂等（Q24）
    sender: str = ""
    surface: str = ""
    values: Mapping[str, Any] = ...

@dataclass(frozen=True, slots=True)
class SenderPolicy:                        # ⚠️ 无默认值：缺省即拒绝启动
    allowed_senders: frozenset[str]        # FEISHU_ALLOWED_SENDERS 的归宿
    bot_identity: str = ""                 # FEISHU_BOT_OPEN_ID：群聊归属证明
    def admits(self, msg: InboundMessage) -> bool: ...

class Acceptance(StrEnum):                 # ← 旧 DeliveryAttemptOutcome 的对应物
    ACCEPTED; REJECTED; UNKNOWN            # UNKNOWN ⇒ Pump 不得盲目重试

@dataclass(frozen=True, slots=True)
class DeliveryResult:
    acceptance: Acceptance
    retry_after: float | None = None
```

> **命名是刻意贴着旧控制面的**，这是本轮范围修正的直接结果：三个面今天就在
> `import ChannelSurfaceBinding` / `RawInboundV1` / `TurnEventFrame`
> （Q23 逐行证据）。名字对齐，改接就是换 import 路径；名字另起，同样的
> 13 行改动会变成 13 处语义翻译。**这不是「保留旧架构」，是保留一套三个面
> 已经在说的词汇。**

### 3.3 一个回合的规范时序（**本计划最重要的一张图**）

```
surface 收到一句话
  └─ SessionRegistry.submit(session_id, text) → **立刻**返回 TurnHandle
       ├─ 该 session 已有回合在跑 ⇒ 入队（深度上限 max_queued_per_session，
       │   满则拒绝），先 publish 一条 QUEUED                          Q7
       └─ 轮到它时，创建 **本回合专属的 asyncio.Task**                陷阱 2
            ├─ 【Task 内】bind ToolContext(approval=broker,
            │                progress=sink, values={**session.values, turn_id})
            ├─ publish EXCHANGE_START
            ├─ prompt   = app.prompt.render()          ← PromptAssembler.render
            ├─ convo    = assemble(prompt, session.history, text)
            ├─ report   = measure(convo, app.tools_snapshot, app.budget)
            │                        ↑ 三个位置参数；少一个直接 TypeError
            ├─ publish CONTEXT(report)                                  Q19
            ├─ if _PRESSURE_ORDER[report.pressure] >= _PRESSURE_ORDER[compact_at]:
            │       ↑ **绝不能写 report.pressure >= compact_at**        陷阱 0
            │     convo, record, state = await compact(
            │         convo, report.budget,            ← 修正后的预算，非原始
            │         summarizer=app.summarizer,       ← 超时套在它身上
            │         state=session.compaction,        ← 不传 = 每次白纸重摘要
            │         pinned=1)
            │     publish COMPACTION(record)
            ├─ async for ev in engine.run_stream(convo):
            │       stream.publish(TurnEvent.from_engine(ev, seq=next()))
            ├─ history' = result.messages[1:]        ← 恰好一次切片       陷阱 4
            └─ finally:
                 publish EXCHANGE_END(terminal=…)    ← **恒发且恰好一条** 陷阱 1b
                 注册表（不在被取消的 Task 里）负责落库             陷阱 3
surface 侧（可以有 0..N 个，可随时来去）
  └─ async for event in handle.observe(after_seq=cursor):
       └─ 看到 APPROVAL_REQUIRED 时调 handle.approve(...)，**并且不停止迭代**
```

四个下标要点，每个都有点名测试（§9）：

1. `assemble()` **总是**自己加**恰好一条** system 消息且在 `[0]`
   （`prompt.py:217`）；`compact(pinned=1)` 返回的历史**含**那条 system；
   `RunResult.messages` **含全部输入**（`engine/types.py:137-144`）。所以
   落库前的 `[1:]` 恰好一次。三条均已实测。
2. **取消路径没有 `RunResult`**：`history` 是 `_kernel` 的局部 `list`
   （`engine/loop.py:209`），唯一出口是最后那条 `DONE` 事件
   （`:267-274`）。因此「取消后修复历史」在本层**不可达**——裁决见陷阱 3。
3. 压缩只能发生在 `run()` **之间**。回合内撑爆窗口本步接不住，债 §11-1。
4. **本层不调用 `repair_tool_pairs`**：正常路径由 `_answer_every_call`
   （`loop.py:482-569`）保证「每个 ToolCall 恰有一条 Observation」；压缩路径
   由 `context` 自己在 `compaction.py:255` / `transcript.py:248,250,289` 调。
   本层再调一次是重复，且会掩盖上面第 2 点。

---

## 4. 硬问题的裁决

### Q1 —— 包名：`omicsclaw/entry/`，且**不**去夺 `surfaces/`

`app` / `entry` / `host` / `shell` / `interface` / `ui` / `session` 七个名字
在 `omicsclaw/` 下**全部空闲**（实测）。

- `app/` 淘汰：本仓库里「App」已专指 Desktop 的 Electron 客户端
  （README:62 `## 🖥️ App Workspace`）。
- `agent/` 淘汰：`omicsclaw/agents/`（复数）活着。
- **`entry/` 采用**：交接文档自己的措辞是「entry/interaction layer」。

**不夺 `surfaces/`**，尽管第 3 步夺了 `engine`。差别可核实：旧 `engine` 的
`__init__.py` 在模块作用域 import `openai`，`omicsclaw.engine.<任何东西>`
**直接 ImportError**（交接文档 :173-181）；旧 `surfaces/__init__.py` 是 16 行
纯 docstring、**可以导入**，且 `cli/_main.py` 仍在服务 `oc list` / `oc run`
（实跑核对）。夺名会弄断一条还在工作的通路，换来一个可 grep 的标签。边界改
由 §8.3 的**行为性**分层探针来守。

### Q2 —— 依赖方向：本层是**顶**，不是叶

前五层都有「叶子层」测试。本层是唯一允许 import 全部五层的地方，所以它的
分层测试是**反向**的两条：

1. 五层中任何模块都不得 import `omicsclaw.entry`（AST + 子进程双查）。
2. `omicsclaw.entry` 驱动完一个真回合后，子进程 `sys.modules` 里**不得**
   出现 `omicsclaw.runtime*`、`omicsclaw.control*`、`omicsclaw.providers`
   （复数）、`omicsclaw.memory`、`omicsclaw.skill*`、`omicsclaw.surfaces*`。

第 2 条必须是**行为性**的：0028 的教训原话是「静态检查查拼写，只有行为探针
查事实」——一次惰性 `importlib` 委派曾让 286 个测试全绿（交接文档
:293-300）。

第三方方向同样定死：**`import omicsclaw.entry` 不得 import `fastapi` /
`prompt_toolkit` / `textual` / 任何厂商 SDK**。三个面各自在工厂函数内部做
**可见的** `import`（不是 `importlib`——交接文档 :681-685）。

### Q3 —— 历史里存不存 system 消息？**不存**

理由三条：(1) `assemble()` 每回合都加一条**新**的，存旧的等于把 `[1:]` 从
一处变成两处；(2) 人格/项目文件会变，存的是**当时**那份，喂回去让模型看到
两份矛盾的 system；(3) 前缀缓存依赖 system 段逐字节稳定，历史里混一条旧的
会在前缀里插一段随会话漂移的内容。

代价，写明：`pinned=1` 的语义是「保住第一条」，所以压缩**必须**在
`assemble` 之后、对完整对话做。时序因此固定为「先组装再压缩」，不可颠倒。

### Q4 —— 会话存储：Protocol + 内存实现，**不**在本步造持久化

harness9 在 `main.go:232-236` 装配 `memory.NewManager(…sessions.db)`、
`:242-245` 建 Session、`:442` 用 `WithSession(sess)` 交给引擎。本仓库的引擎
**没有** Session 概念（0027：「对话进、对话出……第 6 步之前没有 Session，
造半个不值得」），所以历史只能落在本层。

但**造一半持久化是第 1 步已经付过学费的错**。因此：`SessionStore` 是
Protocol，`InMemorySessionStore` 是本步唯一实现，不落盘、不建表、不定 schema。

**`Session.compaction` 是这条裁决里最容易漏的一格。** `context` 自己写明
`CompactionState`「由调用方在回合之间携带；第 6 步决定它住在哪。丢掉它不
致命也不免费：每次压缩都从 `FIRST_TEMPLATE` 重新开始、从白纸重新摘要」
（`compaction.py:150-158`）。「第 6 步决定」的意思不是「第 6 步可以不决定」。

### Q5 —— 事件契约：本层**自己**的 `TurnEvent`，不改引擎

交接文档 :633-636 已把缺口点名：「审批在 `EngineEventType` 里没有表示……
一个 Surface 无法从事件流里得知有人正在被询问」。两条路：(a) 给引擎加成员；
(b) 本层发布自己的超集。**选 (b)**：

1. (a) 改的是前一步的文件。
2. **绑定 `ApprovalChannel` 的是本层**，「有人正在被询问」本层本来就知道。
3. harness9 把审批塞进 `engine.Event`，是因为 **Go 的 channel 装不下异常、
   也装不下第二条流**。Python 没有这个约束。**结构从参考实现来是资产，
   约束从参考实现来是负债**——第 3 步用五个字面量换来的教训。

### Q5b —— 终止：`EXCHANGE_END` **恒发且恰好一条**，取消是它的一个 `terminal` 值

`engine/types.py:93-99` 的裁决（六个成员、无 `ERROR`、异常在消费者的
`async for` 处重抛）对**同进程同 Task** 成立。本层三面里有两面不是：Desktop
的消费者在 HTTP 另一侧，Channel 的消费者是一次 IM 投递，异常都过不去；而
陷阱 1 的队列设计让引擎跑在另一个 Task 里，异常本来就不会在消费者处抛出。

**原稿在这里自相矛盾**（附录 C-Z4）：一边说「取消表现为事件流干净结束」，
一边抄了 harness9「终止事件必达」。两条同时成立时，SSE 消费者看到「流停了
且最后一帧不是终止帧」有三种可能：取消、崩溃、断线——它不知道该不该重连。

裁决：**终止帧恒发且恰好一条**，`terminal ∈ {converged, cancelled, failed}`。
`asyncio.CancelledError` 仍然**不**变成 `failed`（0027 的裁决不重开），它是
`cancelled`；同进程消费者仍可从 `error` 字段拿到原件 `raise`。**不把取消当
失败，和不让流无声消失，是两个问题。**

### Q6 —— 会话注册表：参考实现没有对应物（增量一）

依据是 `omicsclaw/tools/context.py` Q4.5 的原话：两个并发会话「只有在每个
顶层会话跑在自己的 Task 里时才是隔离的。两个会话在一个共享 Task 里 bind
context 是一个长得很像正确 diff 的真缺陷：第二次 `set` 赢，**一个用户的工具
调用会被送到另一个用户的审批提示前**」。

`SessionRegistry` 三条职责：每回合一个专属 Task（隔离 `contextvars`）、
同 session 串行、跨 session 并发。不做鉴权、不做限流。`max_sessions` 到顶时
淘汰最久未用且**空闲**的；正在跑的永不淘汰。

`omicsclaw/tools/_pathlock.py` 的分工没有被取代：写屏障排的是**一个回合内**
的顺序，跨回合重叠正是本注册表允许的东西。

### Q7 —— 排队是一条语义，不是一把锁

原稿只写了「一把 `asyncio.Lock` per session」，那会让 `submit()` 在返回
handle **之前**就 await 锁：用户连发两条，第二条没有任何反馈、没有队列深度
上限、没法取消、也拿不到 handle。harness9 没这个问题是因为它单会话且 REPL
阻塞在 stdin（`cli.go:50`）——这正是声明 4 说的「参考实现没有对应物」。

裁决：`submit()` **立刻**返回 handle 并 publish 一条 `QUEUED`（带前面还有
几条）；深度上限 `max_queued_per_session`，**满了明确拒绝**而不是无限堆积；
排队中的回合可 `cancel()`。策略（排队 / 拒绝 / 取消前一条并替换）是
`AppConfig` 的一个字段，因为这是三个面的语义分歧点，必须在接口上看得见。

### Q8 —— 配置：一个解析点，一个例外

harness9 是 `env.Load(cwd/.env)`（`main.go:117`）+ 到处 `os.Getenv`。本层
收紧成：`resolve_app_config` 是唯一读 env / 读 argv 的函数，例外恰好一个
——`provider_from_env` 继续自己读密钥。

`EngineConfig` 什么都不读（0027：「一个随 shell 变的轮次上限会让同一个
benchmark 任务的两次运行不可比」）。本层因此是**第一个真正给它赋值的地方**，
交接文档 :619-625 那条「`tool_timeout = 60.0` 是一个未被承认的 ported 字面
量」现在到期了——§12-2。

### Q9 —— 默认 system prompt 装哪些段

harness9 `internal/context/builder.go`(190) 最多装**七**段全进 system
prompt：基础 prompt + `AGENTS.md` + skills 索引 + 规划准则 + offload 检索
指引 + **Sandbox 三态说明**(`:150-175`) + 长期记忆精华，并且**每次
`Build()` 注入当前日期**（`AGENTS.md:462` 写明理由：防止 Agent 因训练截止
日期偏差产生陈旧搜索词；注入点 `builder.go:93,103`）。

本层的默认段集合（顺序即 `with_section` 的调用顺序；0030 裁定没有 `order`
字段，顺序由组装根负责）：

| # | 段 | 来源 | 备注 |
|---|---|---|---|
| 1 | persona | `SOUL.md` | |
| 2 | project contract | `CLAUDE.md` | |
| 3 | **safety rules** | `CLAUDE.md` §Safety Rules 的四条 | **不可选**，见下 |
| 4 | tool guidance | 静态文本 | |
| 5 | environment | cwd / 平台 / **当前日期（只到日）** | 见下 |
| 6 | skills index | `omicsclaw/skills/` 的 `SkillIndex` | **已注入**（0032 取代 §12-1）。档位由 `AppConfig.skills_index` 决定：`full`（每技能一行，~8.5k tokens）/ `compact`（每域一行，~600）/ `off`（不注入，且 `use_skill` 也不挂——一个开关一个含义） |

四条裁决：

- **第 3 段不是可选的。** `CLAUDE.md` 的四条安全规则（基因数据不出本机、
  报告必须带免责声明、只用 SKILL.md 的方法学、覆盖前先警告）是本仓库自己的
  契约。重建一层把它悄悄丢掉，是本计划最容易犯且最难被发现的错——§9 有一条
  点名测试。
- **第 5 段只到「日」，绝不到「秒」。** 机制要说准（附录 C-A11 改正了原稿）：
  ADR 0024 的原话是 DeepSeek / OpenAI 做的是**按逐字节前缀自动缓存**，
  OmicsClaw **不需要** `cache_control` 注解（那是 Anthropic 的机制），它只
  需要一个**逐字节稳定的前缀**。所以危害是「前缀变了 ⇒ 缓存全失效」，与
  `cache_control` 断点无关。日期按天变、每天失效一次可接受；时间戳按秒变
  等于每回合全失效。
- **`app.prompt` 是 `PromptAssembler`，每回合 `render()`。** 存
  `AssembledPrompt` 会让「每回合重渲染」静默消失：日期停在进程启动那天、
  `text_from_file` 的重读失效、改 `SOUL.md` 不生效——而 §9 的其余验收一条都
  抓不到（附录 C-Z2）。§9 因此专有一条「换掉 source ⇒ 下一回合 system 必须
  变」。
- **第 6 段本步不注入**（owner 裁定，§12-1）。默认段集合因此是五段。

### Q10 —— ~~skill 整体预留~~ **已被 0032 取代**

> `use_skill` 已挂载、索引段已注入、`omicsclaw/skills/`（**复数**）是一个
> 新包而不是旧的 `omicsclaw/skill/`（**单数**，已删除）。分层探针里单数仍
> 禁、复数放行。理由与连带影响见 §12-1 顶部的「已被取代」块。
>
> 以下为原裁定，保留作记录——**其中一句仍然成立且值得带走**：把 prompt
> 指向一份即将过期的目录，比没有目录更难查。0032 之所以能接，正是因为那份
> 目录不再即将过期。

#### ~~原裁定：工具不接，索引段也不注入~~

**owner 裁定（本轮）**：「skill 暂时预留着，当前项目下的 skill 我还得重新
设计和迁移，现在接进来会造成一些问题。」

这条裁定推翻了本计划评审阶段的建议（原建议是「工具不接，但索引段读
`skills/*/INDEX.md`」）。**推翻的理由比原建议更强，写下来免得被当成保守**：
把 system prompt 指向一份**即将被重新设计与迁移**的技能目录，等于在交付日
烘焙一份马上就要过期的清单——而 prompt 里的一份错目录，代价是模型按它去找
不存在的东西，比「模型不知道有技能库」更难查。

因此本步：不接 `use_skill` 工具、不 import `omicsclaw.skill`、**也不读
`skills/*/INDEX.md`**。分层探针里 `omicsclaw.skill*` 保持在禁止名单上
（Q2 第 2 条）。

**接缝**：技能一旦重新设计完成，接进来是 `build_app(sections=[…, Section(
"skills", …)])` 多传一项、以及（可选）`build_app(tools=[…, use_skill])` 多传
一项。本层不需要为此改任何一行。

**代价，写明**：交付日的 Agent 是一个有读写/编辑/shell/web 的通用 Agent，
**不会做 omics 分析**，也无法用 omics 任务 dogfood 自己。这是一次有意的
排序，不是遗漏。

### Q11 —— 摘要超时套在 **Summarizer** 上，不是套在 `compact()` 上

0030 §5.3 把超时判给调用方，但**落点**是本计划原稿写错、且两份评审独立指出
的同一处：`compact()` 只对 summarizer 的异常做 `except Exception → 回退`
（`compaction.py:565-568`）。把 `asyncio.timeout` 套在 `compact()` 外面，
拿到的是 `TimeoutError` 抛出去、这一回合**没有任何压缩**，而不是「压缩
降级」。0030 自己给的示例（`compaction.py:522-529` 里的
`async with asyncio.timeout(20): await compact(...)`）达不到它想要的效果。

裁决：`AppConfig.summary_timeout_s` 作用在 `assembly` 造的 **Summarizer 包装
器**上（超时后返回空），让 `compact` 自己的回退接住。验收改成「超时 ⇒
`record.degraded` 非空且对话仍被裁到回退目标」。**这两种写法的测试长得一样、
结果完全相反**，所以验收必须断言 `degraded`，不能只断言「没挂」。

### Q12 —— 三条时间契约，缺一条 Channel 就不可用

| 契约 | 裁决 |
|---|---|
| 回合级 wall-clock `turn_timeout_s` | 必须有。没有它，一个卡住的 bash + `tool_timeout=60` + `max_turns=50` 能把一个会话锁 50 分钟 |
| 审批截止 `approval_timeout_s` | `tools/context.py` 原话：「一个询问人的 surface 仍然自己欠一个 deadline……漏掉它现在是这个 surface 自己的报告」。默认 `None`（CLI 可以等人），**Channel 面必须给非 None**，超时 = **拒绝**（fail-closed） |
| 心跳 / 进度 | `TurnEventType.PROGRESS`（Q20）。对 10 分钟的回合，这是唯一让用户知道还活着的东西 |

### Q13 —— 给还没建的四层留的接缝（只留，不建）

| 将来 | 接缝 | 本步要做的 |
|---|---|---|
| hooks / permission | `ToolRegistry` 的 seam 已在它的 `try` **之外** | `build_app(tools=…)` 允许注入已包装的工具；**但包装物必须仍满足 Q16** |
| sub-agent | 「拿父 app 造子 app」 | `build_app` 可注入 tools/sections ⇒ 一次调用；不写 `task` 工具 |
| MCP | `omicsclaw/tools/mcp_tool.py` 已在 | `tools=` 注入即可；不读 `.mcp.json`。**并记下代价**：harness9 是异步启动完再 `InjectTools`（`main.go:313-320`），即工具表在会话开始后才变——而本仓库的工具表顺序是前缀缓存的一部分（0028 的裁决）。接 MCP 那一步必须决定「中途扩表 vs 启动时阻塞等待」，因为它花的是缓存前缀 |
| 持久记忆 | `SessionStore` + `Session.compaction` | 已在 Q4 |

### Q14 —— 跨进程流式投递：参考实现没有对应物（增量二）

**这是本计划从评审里学到的最重要一条，原稿把它整个漏了。**

原稿的 `TurnHandle` 同时是「回合句柄 + 唯一事件消费者 + 审批入口」。三面
推演立刻穿帮：

- **Desktop**：SSE 断连重连时，消费者是**一个新的 HTTP 请求**，拿不到原来
  那个迭代器，已消费的帧也拿不回来。而原稿的陷阱 9 把方向定反了——「消费者
  走开必须真的取消」⇒ **浏览器刷新一次 = 杀掉一个跑了 8 分钟的回合**。
- **Channel**：一条消息投递失败要重发，同样需要按游标重放。

**本仓库自己已经把正确形状写出来了**，而原稿 §5.2 把它折成了一行「重建为
`TurnHandle` + `to_wire`」：`git show HEAD:omicsclaw/control/event_hub.py`
有 `TurnEventFrame.sequence`、每回合一条 `deque(maxlen=…)` 的**有界** ring、
按 `after_sequence` 的原子 gap/replay 判定、结构化断流原因
`cursor_evicted` / `cursor_ahead`、以及 `EventObserverDetached`；
`surfaces/desktop/turn_observation.py` 的模块 docstring 第一句就是
「Durable truth and **cursor recovery** remain behind `ControlRuntime`」。

裁决：**现在就把回合身份和一次观察拆开**（§3.2 的 `TurnStream` /
`TurnObservation`）：

1. `TurnEvent.seq` 每回合单调。
2. `handle.observe(after_seq=N)` **可被调用多次**，并发多个观察者。
3. 每回合一条有界 ring：**delta 类可丢，控制类永不丢**（这同时解决了原稿
   「无界队列」对「慢但在线的消费者」无对策的问题）。
4. 游标落后到被淘汰 ⇒ 收到一条显式 `GAP`，**不静默跳号**。
5. 取消的触发条件改成「**最后一个**观察者离开 + 宽限期到期」，不是「任一
   迭代器 break」。

**这不是持久化，是事件身份。** 它是 §1.3 那一串「延后」里唯一一个**不做就
必须推翻重写**的：不做，`TurnHandle` 的签名、`to_wire` 的帧格式、
`ApprovalBroker` 的寻址、注册表的取消语义会一起返工。

### Q15 —— `Workspace` 不在 `omicsclaw.tools` 的公开面上：**一条声明修订**

实测：`from omicsclaw.tools import Workspace` → `ImportError`；它在私有模块
`_workspace.py`，两个 `__all__` 都没有它。而 Q7 把
`Workspace(root=config.workspace)` 列为本层必经的接缝。

三条路：跨私有边界 import（把 `_` 前缀变成谎话）、在本层重建一个（把安全
边界抄一份，最坏）、**给 `omicsclaw/tools/__init__.py` 加一行导出**。

裁决：**第三条，作为本步唯一声明的修订**，照 0027 只带一条 schema 修订
（`StreamChunk.finish_reason`）的先例。§9 验收 2 把它列为唯一允许的 ` M `。

> **实现结果：只加了 import 行，没有加 `__all__` 一项**（`omicsclaw/tools/__init__.py:73`）。
> 原因是本计划自己的两条验收在这一点上**互斥**，实现时才暴露：
> `tests/tools/test_tools_is_a_leaf_layer.py::test_the_public_surface_is_exactly_what_the_two_plans_delivered`
> 把 `omicsclaw.tools.__all__` **逐项钉死**，而且它的 docstring 明写
> 「What is deliberately absent: `Workspace`…」。加那一项 ⇒ 该测试红 ⇒
> 违反 §9-1；不加 ⇒ 违反 §9-2 的字面表述。
>
> 取舍：**只加 import 行**。Q15 的功能需求（`from omicsclaw.tools import
> Workspace` 不再 ImportError）已满足，「少一行」不破「多一个字符都算违约」
> 这条上界，基线保持全绿。**下一个人要补 `__all__` 时必须同时改那条测试的
> 期望列表与那句 docstring**——否则「deliberately absent」会变成一句自信的
> 错话，而那正是第 4.5 步的评估花了一整轮去抓的东西。

### Q16 —— 交给引擎的必须是 `ToolRegistry` 本身或一个**同样满足两个可选
Protocol** 的包装

`DeadlineAwareExecutor` 与 `ConcurrencyAwareExecutor` 都是
`runtime_checkable` 的（`engine/executor.py:116`），引擎用
`isinstance(executor, DeadlineAwareExecutor)`（`:380-385`）决定要不要下发
`TimeoutPause`。实测 `ToolRegistry` 两个都满足。

**后果**：本层若把 registry 包一层（做日志、做 hooks、做工具过滤）而忘了转发
`use_timeout_pause` / `is_concurrency_safe`，`TimeoutPause` 就不会下发，
**人的审批时间又会被记进 60 秒 `tool_timeout`** ——也就是交接文档
:500-519 说「在任何 Surface 绑 `ApprovalChannel` 之前必须先修好」的那个 R3。
**本层正是第一个绑 `ApprovalChannel` 的东西。** 原稿只写了一句含糊的
「本层只需不要把它撤销」，而撤销它只需要包一层。

裁决：`AgentApp.registry` 原样交给 `AgentEngine`；任何包装物必须转发这两个
方法，并有一条点名测试（审批停顿 > `tool_timeout` 后工具仍成功）+ 一条变异
（包装物吞掉 `use_timeout_pause` ⇒ 该测试必须红）。

### Q17 —— 进程生命周期与优雅停机

`main.go` 有 5 个 `defer`（otel shutdown、`sandboxMgr.DestroyAll`、
`mgr.Close`、`mcpMgr.Stop`、`signal.NotifyContext` 的 `stop`）。原稿一个
都没有对应物：`AgentApp` 是 frozen dataclass 没有 `aclose()`、
`SessionRegistry` 持有 N 个在跑的 Task 没有 drain。CLI 单次跑完退出能糊弄
过去，**Desktop（`uvicorn` lifespan）与 Channel（长驻、收 SIGTERM）两面必须
有**——而 SIGTERM 才是容器里杀进程的方式，原稿把 `main.go:121-122` 只映射成
「CLI 面的取消」。

裁决：`AgentApp.aclose()` + `SessionRegistry.shutdown(grace_s)`（停收新回合
→ 给在跑的回合宽限 → 超时后 cancel 并**回收异常**）；三个面各自接上。

### Q18 —— `approve()` 的竞态：未知或已结算的 `request_id` 是 no-op

决策到达时回合可能已取消、已超时自动拒绝。`Future.set_result` 会
`InvalidStateError`。裁决：no-op，不抛。理由：审批决策来自人，人点两次、
点晚了、在断线后点，都是正常输入而不是编程错误。

`ApprovalChannel = Callable[[ApprovalRequest], Any]`（实测），同步/异步皆可
——`ApprovalBroker` **必须显式选一种并写下来**，不能两种都支持而不说。

### Q19 —— 上下文压力上报：现在到期了

`stream.go:43-45` 的 `EventTokenUpdate`（每次 LLM 调用前报估算 token 与
context window）是 harness9 TUI 状态栏的数据源。`engine/types.py:218-222`
明说这个 pre-call 事件「需要本层没有也不该长出来的 token counter，**它属于
第 5 步**」；交接文档 :790-792 又说「context-window reporting 仍然开着而且
仍然便宜」。第 5 步交付了 `measure`，**第 6 步是唯一调用它的地方**。成本是
一个事件成员：`TurnEventType.CONTEXT` 携带 `BudgetReport`。

顺带把 `measure` 的两个易错点钉住：它是 `measure(messages, tools, budget)`
**三个位置参数**（原稿少传 `tools`，会 `TypeError`，而且 `max(declared,
measured)` 的全部意义都不可达）；下游必须用 `report.budget` 而不是原始
`budget`（`budget.py:282-315`：「两者取更收紧的那个」）；
`report.tool_reserve_shortfall != 0` 要记一条日志。

### Q20 —— 进度事件：绑了 sink 就得有落点

Q7 表里 `use_tool_context(approval=…, progress=…, values=…)` 由 TurnRunner
绑定，陷阱 8 又专门讲「会抛的那个 sink 正是本层写的」。原稿的 11 个事件成员
里却没有进度事件——sink 收到 `ProgressUpdate` 之后无处可去。补
`TurnEventType.PROGRESS`。

### Q21 —— `TURN_END` 是每次**模型调用**一次，不是每次用户往返一次

引擎的 `TURN_END` 在 `while` 循环体内（`loop.py:262`），一个用户往返会有 N
个。原稿把自己新加的 `TURN_START` 与它配对，基数就错了。裁决：本层的往返
边界叫 `EXCHANGE_START` / `EXCHANGE_END`，`TURN_END` 保持直通，两者作用域
在 `events.py` 的 docstring 里写死。

### Q22 —— 日志：本层是**第一个**允许 I/O 的层

`omicsclaw/engine/` 把「无 I/O、无日志」写成约定，且交接文档 :532-538 老实
承认这条约定**没有测试强制**。本层反过来：标准库 `logging`，一个
`omicsclaw.entry` logger，默认 `WARNING`。三条硬规矩：

1. **绝不记录工具参数原文与工具输出原文**——`write_file` 的 content、
   `bash` 的 command、`web_fetch` 的完整 URL（含 query）都可能带受试者标识
   符。`CLAUDE.md` 第 1 条安全规则在这里是可以被日志违反的。
2. REPL 独占终端期间日志必须改道（harness9 `tui.go:365-367` 的做法）。
3. 不引入任何日志第三方库。

### Q23 —— `entry` 与已删的 `omicsclaw/control/` 的边界

**这是 owner 范围修正逼出来的一条，也是全计划最要紧的一条边界。**

实测：三个面的**入口文件**焊死的不是 agent loop，是 `omicsclaw.control`。
逐个点名（`sed -n` 实读）：

```
cli/interactive.py:69      ControlRuntime, ControlRuntimePorts,
                           RawContentBlockV1, RawInboundV1, RunRuntime
desktop/server.py:88-97    ControlRuntime, ControlRuntimePorts,
                           RawContentBlockV1, RawInboundV1,
                           RunAcceptanceStatus, TurnAcceptanceStatus,
                           RunRuntime, EventHubCapacityError
desktop/turn_submission.py:30    RawContentBlockV1, RawInboundV1
desktop/turn_observation.py:17-18 ControlTurnObservation,
                           TurnObservationSnapshot,
                           EventObserverDetached, TurnEventFrame
channels/telegram.py:20    ChannelSurfaceBinding
channels/feishu.py:21      ChannelSurfaceBinding
```

这些符号分成**三族**，本层只接第一族：

| 族 | 符号 | 归属 |
|---|---|---|
| **① 入站 → 回合 → 观察** | `RawInboundV1` / `RawContentBlockV1`、`ChannelSurfaceBinding`、`TurnEventFrame`、`ControlTurnObservation` / `TurnObservationSnapshot`、`EventObserverDetached`、`EventHubCapacityError`、`TurnAcceptanceStatus` | **本层**。`entry` 就是这一族的替代物 |
| ② Run / Receipt / 治理 | `RunRuntime`、`RunAcceptanceStatus`、replay | **不属本层**。它是技能运行器的控制面，而 skill 正在等重新设计（§12-1） |
| ③ 持久记忆 | `get_memory_engine`、`MemoryURI`、scoped memory 一族 | **不属本层**。第 7 步 |

**两条由此而来的裁决**：

1. **`entry` 不复制 `ControlRuntimePorts`。** 实读 `HEAD:control/runtime.py:
   100-124`：22 个字段，其中 **6 个是 `Any`**（`usage_accumulator`、
   `request_tool_approval`、`policy_state`、`runtime_observer`、
   `run_runtime`、`extra_api_params`）。这正是 owner 说的「低耦合」要治的
   东西，也正是 0030 在 `ContextAssemblyRequest`（31 字段）上已经治过一次
   的形状。`entry` 的每回合入参是**入站消息 + 会话 id + 一小撮回合级事实**；
   其余（模型覆盖、输出风格、MCP 列表、策略状态）要么属于部署级的
   `AppConfig`，要么还不存在。**一个 `Any` 都不许有。**
2. **诚实结论：`entry` 落地后，三个面不会全部复活。** 第 ② ③ 族挡着
   `interactive.py` 与 `server.py`。§5 逐行写明每个文件属于哪一族，
   §11 记为债。**把这句话说在前面，好过交付日被当成缺陷。**

### Q24 —— Desktop 的线路契约是**外部客户端定的**，不是本层发明的

Desktop 前端是一个独立工程：`/workspace/algorithm/zhouwg_project/
OmicsClaw-App/`（Electron + Next.js）。它的 `src/app/api/chat/route.ts`
（1,303 行）自述是一个 **Transform Proxy**，注释原话：「Forward to Python
backend (127.0.0.1:8765/chat/stream)」。也就是说：

- **`POST /chat/stream` 的 SSE 是一份已发布的契约**，本层是它的实现方，
  不是它的作者。
- 后端侧的契约声明已经存在且**本来就干净**（不 import 任何已删包）：
  `surfaces/desktop/wire_contract.py`(149) 与 `_chat_sse.py`(200)。前者
  带版本号（`DESKTOP_CHAT_SSE_SCHEMA_VERSION = 1` 等 8 个）与一组自述事实。

**其中三条直接约束本层的设计，而且和本计划已有的裁决对得上**：

| 契约事实 | 对本层的约束 | 与本计划的关系 |
|---|---|---|
| `event_queue_capacity` + `producer_backpressure: True` + `oversize_event_projection: True` | 事件队列**有界**、生产者要承压、超大事件要投影而非截断 | **印证 Q14/Y5**：delta 有界可丢、控制事件不丢。原稿「无界队列」的写法与这份已发布契约直接冲突 |
| `terminal_error_type_preserved: True` | 终止帧必须保住错误类型 | **印证 Q5b**：终止帧恒发且恰好一条，`error` 带原件 |
| `source_request_id_required: True` + `durable_ingress_idempotency: True` | 入站必须带幂等 id，重试解析到**同一个** Turn | **本计划漏了，现补**：`InboundMessage.source_request_id` 必填；同 id 重投 ⇒ 返回同一个 `TurnHandle` 而不是新开一个回合。§9 加一条验收 |

**裁决**：`entry/desktop/` **移植** `wire_contract.py` 与 `_chat_sse.py`
（两者干净，是本步成本最低的一段），实现 `POST /chat/stream` 与
`GET /health`；`server.py`(9,454) 的其余路由**一条都不搬**——它们属第 ②
③ 族。契约版本号不得在本步变更：**改一个外部客户端已经依赖的版本号，属于
迁移的协调工作，不属于一个后端内部重建步骤。**

---

## 5. 现有 Surface 复用对照表

### 5.0 口径

**owner 范围修正把这张表的默认值整个换掉了**：从「丢弃 / 重建」换成
「**移植**」。表的结构相应变成四分类，每个文件恰好落一格：

| 记号 | 含义 | 本步要做的 |
|---|---|---|
| **搬** | 干净（不 import 任何已删包），且属 agent 面 | 移进 `entry/<面>/`，尽量逐字；改动只在接缝 |
| **改接** | 只焊在第 ① 族（Q23）上 | 移进来并把那一条 import 换成 `entry` 的对应物 |
| **挡住** | 焊在第 ② / ③ 族上 | **不搬**。等 Run 治理层或第 7 步；§11 记债 |
| **弃** | 旧框架独有且无对应问题 | 丢弃（裁定 0） |

复现命令：

```bash
DEAD='omicsclaw\.(control|runtime\.(agent|context|tools|storage)|providers|memory|execution)'
grep -lE "^(from|import) +$DEAD" omicsclaw/surfaces/<面>/*.py
```

裁定 0 仍然管「弃」那一格；**它不再是全表的默认值**——一份已经写好、已经
在生产里跑过、且与新契约不冲突的实现，重写一遍不会更好。

原有的两条例外因此降级为两条**提醒**（它们现在由「搬」这一格自然满足）：

> **提醒一：安全控制不是特性。** 一个 fail-closed 的发送者白名单、一个路径
> 沙箱、一个 SSRF 闸，价值在「默认拒绝」而不在「提供了某个能力」。按「旧层
> 独有」丢掉，不会在交付日表现为功能缺失，会在接第一个真实 IM 适配器那天
> 表现为**任何人都能驱动这个 Agent**。⇒ 一律进新层接缝，作**必填参数**。

> **提醒二：跨进程流式投递语义不是旧框架的特性，是问题本身。** 断线重连的
> 游标、有界重放、投递接受性三态——harness9 没有对应物**只是因为它没有
> HTTP 面也没有 IM 面**，不是因为它判断这些不必要。把它们按「旧层独有」
> 丢掉，等于让本层把 Desktop 与 Channel 当成两个 CLI 来设计。
> **范围修正之后这条已经自动成立**：三者的实现都在「搬」那一格里
> （`event_hub` 的游标词汇经 `turn_observation.py`、三态经 `*_delivery.py`），
> 本步是搬不是造。

下表 **一行都不许留空**（0029 §6:501 的规矩：留空即缺陷）。

### 5.0.1 本表最重要的一个数字：**耦合密度 0.39%**

```
旧 Surface 总行数            : 38,412
引用已删包的总行数            :    148
耦合密度                     :  0.39%
只焊在第①族(entry 独力解锁)   : 19 个文件 / 10,255 行，需改 51 行
```

也就是说：**三个面不是「半死」，是「接缝很细」。** 逐个文件的改动量实测
（`grep -cE` 已删包引用的行数）：

| 文件 | 行数 | **要改行** | 接缝族 |
|---|---:|---:|---|
| `desktop/server.py` | 9,454 | **60** | ①②③ |
| `cli/interactive.py` | 2,673 | **10** | ①②③ |
| `cli/tui.py` | 1,550 | **9** | ①③ |
| `channels/telegram.py` | 752 | **9** | **①** |
| `channels/commands/builtins.py` | 353 | **6** | **①** |
| `cli/_main.py` | 1,771 | 4 | ①③ |
| `cli/_plan_mode_support.py` | 1,236 | 4 | **①** |
| `channels/feishu.py` | 766 | **4** | **①** |
| `channels/__main__.py` | 630 | 4 | **①** |
| `channels/base.py` | 532 | **3** | **①** |
| `cli/_pipeline_support.py` | 915 | 3 | **①** |
| `desktop/turn_observation.py` | 442 | 3 | **①** |
| `desktop/turn_submission.py` | 622 | **1** | **①** |
| `cli/_skill_management_support.py` | 1,231 | 1 | **①** |
| `cli/_session.py` | 491 | 1 | **①** |

（完整 28 行见复现命令的输出；上表按行数降序截断。）

> ### ⚠️⚠️ 最终修正（两路独立评估，2026-09-19）：**269 行 / 0.70%**，且 §5.1 判错四项
>
> 这个数字被修正了**三次**，每次都是同一个原因的不同面：
>
> | 口径 | 值 |
> |---|---|
> | 本表原值（只数 `^(from\|import)`） | 148 / 0.39% |
> | 严格重测同一口径 | 43 / 0.11% |
> | **修正口径（任意位置 + 别名使用点，含 `from X import Y as Z`）** | **269 / 0.70%** |
>
> 逐文件：`desktop/server.py` 本表说 60、实为 **139**；`channels/telegram.py` 说 9、实为 **23**；`cli/interactive.py` 说 10、实为 **16**；`cli/tui.py` 说 9、实为 **16**；`commands/builtins.py` 说 6、实为 **13**。**§5.3「双适配器 13 行改动」的真实值是 30 行。**
> （本表的**算术**经独立复核全部正确——1,164 / 1,518 / 2,839 / 834 / 3,569 / 68·38,412 等逐项吻合。错的只有耦合口径。）
>
> ### §5.1 判错四项（实现方实测，评估方复核）
>
> | 本表说 | 实际 |
> |---|---|
> | 8 个 support 模块「全部严格干净」834 行 | **只有 5 个能 import**（401 行）。`_style_support`→`omicsclaw.runtime.output_styles`、`_diagnostics_support`→`omicsclaw.diagnostics`、`_interpret_command_support`→`omicsclaw.routing`，三者今天都 `ModuleNotFoundError` |
> | `_mcp.py`(452)「严格干净、搬」 | `_mcp.py:24` → `omicsclaw.skill.execution.environment`（已删的单数包）；且它管的是 `~/.config/omicsclaw/mcp.yaml` + `langchain_mcp_adapters`，与本层的 `.mcp.json` 是两套。**未移植** |
> | `_session.py`(491)「改 1 行、改接」 | 拉的是已删的 584 行 `runtime/storage/transcript.py`，且 `aiosqlite` 未装；Q4 本步不做持久化。**未移植** |
> | `tui.py`(1550)「改 9 行、改接但不验收」 | **模块作用域** import 12 个被挡的 support 模块，约一半方法是第②③族的处理器。**整个 TUI 面不存在** |
>
> ### §5.0「一行都不许留空」不成立
>
> 4 个文件 / 981 行从未出现在 §5.1/§5.2 里：`cli/_canonical_run_support.py`(422)、
> **`cli/_llm_bridge_support.py`(151)** ← 尤其扎眼，那正是 `entry` 要取代的东西、
> `cli/_omicsclaw_actions.py`(228)、`desktop/thread.py`(180)。
> 另：`cli/_tui_support.py`(33) 判「搬」，是真干净、零依赖，却静悄悄掉了。
>
> ### §9-13 的判据本身要改
>
> 实测：`channel/` 通过（全行 2.4×、仅代码 3.7×），**`cli/`(0.46×) 与
> `desktop/`(0.63×) 不通过**。但两路评估独立给出同一个结论：**该修的是上面这张
> 表，不是代码**——`cli/__init__.py:15-42` 已经诚实写清了它为什么搬不动那四项。
> **判据的缺陷是：它假设「可移植面」是已知的，而这份计划的可移植面是错的。**
> 修正后的判据应当是「**逐文件**说明为什么没搬，而不是用一个包级比值」。
>
> ### 下面是本次修正前的那一版记录（保留）
>
> ### ⚠️ 这张表的绝对值是**低估**的（D1 实测证伪，2026-09-19）
>
> 「要改行」数的是**已删包名出现的行**，而适配器普遍写
> `import omicsclaw.runtime.agent.state as core` 再到处用 `core.*` ——
> **使用点一个都没被数进来**。实测对照：
>
> | 文件 | 本表说 | 含 `core.*` 使用点 |
> |---|---:|---:|
> | `telegram.py` | 9 | **23** |
>
> D1 交付后给出的真实改接量：Channel 面约 **950 行**（而非表上的 13 行），
> 仍远小于它 5,514 行的移植量，**所以「移植 ≫ 重写」这个结论不变，
> 变的是倍率**。
>
> **两条带走**：(1) 本表只能用来**排序**（哪个面先做），不能用来估工时；
> (2) 这正是 0028 那条教训的又一次实例——**静态检查查拼写，只有行为探针查
> 事实**。一个别名 import 就让整套 grep 口径失效。
>
> **同一轮还证伪了 §5.3 的另一句**：「另 7 个适配器全部严格干净」是错的，
> `imessage.py:39` 有 `from omicsclaw.skill.execution.environment import
> scrub_internal_control_credentials` —— 本计划的 `DEAD` 正则**漏了
> `omicsclaw\.skill`**。D1 的处置是把那 32 行安全函数就地内联（它是「默认
> 拒绝」型控制，属提醒一）。

> **一条口径警告，本轮实测踩到的。** 只按模块级 `^(from|import)` 判「干净」
> 是**乐观的**：`cli/tui.py` 模块级干净，但 `:580`、`:856`、`:876` 三处
> 在函数内 `import omicsclaw.runtime.agent.state as core`。两个口径的差额
> 是 channels 626 行、cli **3,321** 行、desktop 207 行。**惰性 import 仍然
> 是耦合**——这正是 0028 那条「静态检查查拼写，只有行为探针查事实」的又一
> 次实例。本表一律用「任意位置」口径。

### 5.1 CLI 面（`surfaces/cli/`，**26 文件 / 14,936 行**）

| 旧能力 | 证据 | 裁决 |
|---|---|---|
| REPL 外壳：样式 / 常量 / 补全 / 历史 / 会话态 | `_style_support.py`(108)、`_constants.py`(85)、`_history_support.py`(113)、`_tui_support.py`(33)、`_session_state.py`(95)、`_slash_command_support.py`(188)、`_interpret_command_support.py`(106)、`_diagnostics_support.py`(106) | **搬**。全部严格干净，合计 **834 行**，逐字移进 `entry/cli/` |
| 交互式 REPL 主体 | `interactive.py`(2673)，**要改 10 行**，族 ①②③ | **改接 ① + 砍 ②③**。搬进来时把 `RunRuntime` 与 memory 两条路径**摘掉而不是重写**——它们各属自己的步骤。这是本子包唯一一处有实质取舍的地方 |
| Textual TUI | `tui.py`(1550)，**要改 9 行**，族 ①③；本机无 `textual` | **改接但不验收**。三处 `import …agent.state as core`（`:580`/`:856`/`:876`）换成 `entry`；因为本机装不了 `textual`，它**不进 §9 验收**，只保证 import 不炸 |
| 会话命令 / 恢复 | `_session.py`(491，改 1 行，族①)、`_session_command_support.py`(1185，改 2 行，族①③) | `_session.py` **改接**；`_session_command_support.py` 的 memory 半边**挡住**（第 7 步） |
| argparse 子命令体系（**35** 处 `add_parser`） | `_main.py`(1771，改 4 行，族①③)，仍可导入，`oc --help` 实跑成功 | **留在原地不动**。它是技能运行器入口，不是 Agent 入口（README:177 自称 "Skill runner (non-Surface)"）。搬它等于把第 ② 族拖进本步 |
| Plan mode | `_plan_mode_support.py`(1236，改 **4** 行，族①) | **挡住**（不是丢弃——改判）。它只焊在第①族上，`entry` 落地后 4 行就能接回来；但 plan 本身是 harness9 的独立包（`internal/planning`），**接回来属它自己那一步** |
| 技能运行 / 回放 / 流水线 | `_skill_management_support.py`(1231,改1)、`_skill_run_support.py`(344,改1)、`_pipeline_support.py`(915,改3)、`_replay_support.py`(159,改1,族①②) | **挡住**（第②族 / skill 重设计）。留在原地 |
| 记忆命令 | `_memory_command_support.py`(515，改 4 行，族③) | **挡住**（第 7 步） |
| setup wizard | `setup_wizard.py`(734，改 1 行，族 PROV) | **挡住**。等 `resolve_app_config` 定稿后它才有东西可写 |
| MCP 管理 | `_mcp.py`(452，严格干净) | **搬**（Q13：只搬管理 UI，不接 MCP 运行时） |

### 5.2 Desktop 面（`surfaces/desktop/`，**21 文件 / 16,401 行**）

> **前端是一个独立工程**（Q24）：`/workspace/algorithm/zhouwg_project/
> OmicsClaw-App/`。本子包是**它已发布契约的实现方**，不是作者。

| 旧能力 | 证据 | 裁决 |
|---|---|---|
| **线路契约（带版本号）** | `wire_contract.py`(149)、`_chat_sse.py`(200)，**两者严格干净** | **搬，尽量逐字**。本步成本最低的一段，也是 Q24 三条约束的来源。**8 个 schema 版本号一个都不许改** |
| `POST /chat/stream` 的 SSE | `server.py`(9454，**改 60 行**，族①②③)；App 侧 `src/app/api/chat/route.ts:305` 自述 "Forward to Python backend (127.0.0.1:8765/chat/stream)" | **只搬这一条路由**。`server.py` 其余路由（skills / providers / MCP / outputs / bridge / memory 代理 / 治理）**一条都不搬**——第②③族 |
| 回合提交 | `turn_submission.py`(622，**改 1 行**，族①) | **改接**。只缺 `RawContentBlockV1` / `RawInboundV1` 两个类型，`entry/ingress.py` 出 |
| **游标恢复观测** | `turn_observation.py`(442，改 3 行，族①) | **改接**。它 import 的 `TurnEventFrame` / `EventObserverDetached` **正是 Q14 定义的词汇**——原计划以为那是我的设计主张，实际是这份代码的接口要求 |
| 压缩事件 → SSE 桥 | `_compaction_event_bridge.py`(83，改若干，族①) | **改接**：`TurnEventType.COMPACTION` |
| 技能日志桥 / 假设面板 / onboarding | `_skill_log_bridge.py`(282)、`hypotheses.py`(207，族③)、`onboarding.py`(117) | 前后两个严格干净但**属第②族的 UI**；**挡住** |
| 自动标题生成 | `title_generation.py`(351，严格干净) | **挡住**（依赖 ticket 机制与治理面），不是丢弃——改判 |
| 笔记本内核 | `notebook/`(**3,569** 合计，严格干净) | **弃**（旧框架独有，裁定 0）。注意它干净 ⇒ 将来若要它，成本是搬不是写 |
| Run/Replay 线路 | `run_wire.py`(432，改 2)、`handoff_executor.py`(302，改 2) | **挡住**（第②族） |

### 5.3 Channel 面（`surfaces/channels/`，**20 文件 / 7,059 行**）

> **三面里复用度最高的一面**，而且是唯一一个**全部接缝都只在第①族**的面
> ——也就是 `entry` 独力就能让它整体复活。这与 harness9 的顺序（CLI 先）
> 和本计划原稿 Task D 的顺序**都相反**，§7 因此改了顺序。

| 旧能力 | 证据 | 裁决 |
|---|---|---|
| **Channel 核心**：基类 / 管理器 / 能力声明 / 配置 / 命令注册表 | `base.py`(532，**改 3 行**，族①)、`manager.py`(348，严格干净)、`capabilities.py`(165)、`config.py`(25)、`commands/_registry.py`(94) | **搬 + 改接**。合计 **1,164 行**，只有 `base.py` 的 3 行需要动 |
| **生产双适配器** | `telegram.py`(752，**改 9 行**)、`feishu.py`(766，**改 4 行**)，两者**只缺 `ChannelSurfaceBinding` 一个符号**（`telegram.py:20`、`feishu.py:21` 实读） | **搬 + 改接**。1,518 行、13 行改动。§12-4 原裁定「本步零适配器」**因此改判**——见 §12-5 |
| 另外 7 个适配器（wechat 551 / email 498 / imessage 466 / dingtalk 389 / qq 342 / slack 322 / discord 271，共 **2,839 行**，全部严格干净；WeCom 与 WeChat 共用一个文件，「10 个平台」不是 10 个文件） | 同左 | **搬，但不验收**。它们零改动即可随包移动；本机无网络无 token，**不为它们写任何测试，也不声称它们能工作** |
| **Owner-only 白名单，fail-closed** | `CLAUDE.md`：「`FEISHU_ALLOWED_SENDERS` … **required**，authoritative Feishu ingress admits nobody else and refuses to start without it」（逐字核对） | **进 `entry/ingress.py`，作必填参数**。`SenderPolicy` 无默认值 |
| **群聊 @-mention 归属证明**（`FEISHU_BOT_OPEN_ID`） | 同上：「group chats fail closed without it」 | 同上，`SenderPolicy` 的一个字段 |
| 多适配器共享一个控制面 | `__main__.py`(630，改 4 行，族① + PROV) | **改接 ① 部分**；PROV 那一处（provider 发现）**挡住** |
| 内置命令 | `commands/builtins.py`(353，**改 6 行**，族①) | **改接**（原判「丢弃」，改判——它只焊在第①族上） |
| 照片 → 组织切片分析 | `capabilities.py`(165) | **弃**。多模态 `Message` 是 schema 的已知缺口（ADR 0077:131 明确排除 content parts），不是接不接的问题 |
| **投递节流 + 接受性三态** | `telegram_delivery.py`(177，改 2)、`feishu_delivery.py`(270，改 2)；`telegram_delivery.py:161-164` 的 `ACCEPTANCE_UNKNOWN` 注释原话：「The Pump must not retry blindly」 | **搬 + 改接**。原计划要「重建三态形状」，实际**它已经实现好了**——搬即可 |
| 出站媒体 | 同上 | **弃**（与照片同一个 schema 缺口） |

### 5.4 结论行

- **搬（含只需改接的）**：Channel 全套（核心 1,164 + 双适配器 1,518 + 投递
  447 + 内置命令 353 + 另 7 个适配器 2,839）、Desktop 的线路契约 349 +
  `/chat/stream` + 回合提交/观测、CLI 的 REPL 外壳 834 + `_mcp.py` 452 +
  `_session.py` 491 + `interactive.py` 的 ① 半边、`tui.py`（不验收）。
- **挡住（不是丢弃，等它自己那一步）**：Plan mode、技能运行/回放/流水线、
  记忆命令、setup wizard、标题生成、Run/Replay 线路、`server.py` 的其余路由。
  **每一条都已量出改动行数**，解锁那天是分钟级的工作。
- **留在原地不动**：`_main.py` 的 35 处子命令（技能运行器入口）。
- **弃（裁定 0）**：笔记本内核、照片入口、出站媒体（3 项，比原稿的 7 项少
  ——4 项在拿到逐文件改动量后从「丢弃」改判为「挡住」）。

> **改判的那 4 项值得单独说一句。** 原稿把 Plan mode、内置命令、标题生成、
> 斜杠命令判成「丢弃」，依据是「旧层独有 ⇒ 裁定 0」。拿到改动量之后它们
> 全部是「只焊 4-6 行、且只焊在第①族」。**「旧层独有」和「应当丢弃」是两
> 件事**，而把它们等同起来的代价，是丢掉几千行已经在生产里跑过的实现去换
> 一个尚未写出的重写版。这是本轮范围修正给整份计划上的最有价值的一课。

---

## 6. 陷阱清单

> 准入规则：**每条都要有一条点名测试或一条变异。** 纯流程规矩不进这张表
> （原稿有三条违反了自己这条规矩，已移进 §8.5）。
> 所有「必须超时/挂起」型判据一律改写成**快速失败**——本机没有
> `pytest-asyncio` 也不能假设有 `pytest-timeout`，「挂」就是真的挂
> （附录 C-Y12）。测试内部自带 `asyncio.wait_for`。

**陷阱 0 —— `Pressure` 没有序关系。** `Pressure` 是 `StrEnum`，`>=` 走字面量
字典序（实测 `sorted` = `emergency < full < none < soft < warn`）。于是
`NONE >= FULL → True`、**`EMERGENCY >= FULL → False`**：最该压的那一档恰好
被跳过，而只用 SOFT/FULL 造触发的测试会全绿。必须自建 `_PRESSURE_ORDER`
映射再比。**测试**：五档逐个断言是否触发。**变异**：换回 `>=` ⇒ EMERGENCY
那条必须红。

**陷阱 1 —— 审批死锁。** harness9 `stream.go:54-57` 把它写成消费者契约：
事件 channel 无缓冲，并发工具时第二个审批请求会阻塞，**UI 必须在展示对话框
期间继续消费事件流**。Python 里更硬：审批的 `await` 在工具内部、在引擎
generator 的 `__anext__` 里，而那个 generator 没有 approval 事件可 yield ⇒
同一个 generator 既不能报告「有人在被问」又不能等待答案。
`omicsclaw/tools/context.py:136-141` 自己给了**两种**出路（独立 Task，
**或**在 `async for` 体内 await 请求队列）；本层选独立 Task，理由是它同时
要把 `APPROVAL_REQUIRED` 放进同一条**有身份**的事件流（Q14）。
**测试**：两个并发工具、两次审批、消费者在第一张卡片前不停止迭代 ⇒ 两次都
拿到决策且在 `wait_for` 内完成。**变异**：控制类事件改走可丢路径 ⇒ 红。

**陷阱 1b —— 终止帧必达。** harness9 用「终止事件直接 `ch <-`」+
`defer close(ch)` 两道保险（`stream.go:133-134`）。本层的回合 Task 在
`async for` 之后还要做落库与清理，任何一步抛异常都会让流永不封口，消费者
挂死在 `queue.get()`——CLI 表现为 REPL 卡住，Desktop 表现为 SSE 永不结束。
**`EXCHANGE_END` 必须在 `finally` 里发。**
**测试**：注入一个会抛的 store ⇒ 消费者在 `wait_for` 内拿到
`terminal="failed"` 并结束。**变异**：删掉 `finally` ⇒ 超时失败。

**陷阱 2 —— `contextvars` 的 Task 边界。** `use_tool_context` 必须在**回合
自己的 Task 内部**绑定。在创建该 Task 的协程里绑定虽然也能被复制走，但那个
协程若同时服务两个会话（Channel 的常态），第二次 `set` 就赢了。
**测试**：从**一个**协程连开两个会话的回合，各自的审批请求只到达各自的
通道。**变异**：把 bind 移到 Task 外 ⇒ 红。

**陷阱 3 —— 取消路径没有 `RunResult`，所以取消即不落库。** 实测：
`history` 是 `_kernel` 的局部 `list`（`loop.py:209`），唯一出口是最后那条
`DONE`（`:267-274`）；`EngineEvent` 里没有任何事件携带装配好的 assistant
消息，从事件流重建是有损的。而正常结束的 `result.messages` **不可能有孤儿**
——`_answer_every_call`（`:482-569`）保证每个 `ToolCall` 恰有一条 Observation。
⇒ 原稿「取消后用 `repair_tool_pairs` 修历史」两头落空（附录 C-B6）。
**裁决**：取消 ⇒ `session.history` **逐字节不变**。
**测试**：在 `TOOL_START` 之后、`TOOL_RESULT` 之前取消 ⇒ 落库后的历史与回合
开始前逐字节相同。

**陷阱 3b —— 落库不能写在被取消的 Task 里。** 取消是往 Task 注入
`CancelledError`，**下一个 await 点立刻再抛**，所以 `finally: await
store.save(...)` 走不完。`InMemorySessionStore` 的 `save` 不真的 await 任何
东西，于是测试全绿；换成 SQLite/HTTP 的那天历史静默丢失。这与 0029 评估
发现 #6（并发测试用本地路径、两个 Task 从未交错）是同一个形状。
**裁决**：落库由**注册表**（取消的发起方，不在被取消的 Task 里）在 reap
之后执行。**测试**：fake store 的 `save` 至少 `await asyncio.sleep(0)` 一次，
断言取消后落库仍然发生。

**陷阱 4 —— `[1:]` 的三个来源。** `assemble` 自己加 system；
`compact(pinned=1)` 返回的历史含 system；`RunResult.messages` 含全部输入。
切一次对，切两次吃掉真正的第一条用户消息，不切让 system 每回合翻倍。
**测试**：跑满 3 个回合后，送进 provider 的 `messages` 里 `role == system`
恰好一条且在 `[0]`，且第一条用户消息仍在。

**陷阱 4b —— `CompactionState` 不回存 = 每次从白纸重摘要。** `compact` 收
`state=` 并返回一个新的；不存它，每次都走 `FIRST_TEMPLATE`，上一轮舍掉的
细节真的没了，还多付一次摘要（`compaction.py:374-382` 把这记成 issue #117
的症状）。**测试**：连续两次触发压缩，第二次必须走 `INCREMENTAL_TEMPLATE`
（用 fake summarizer 断言收到的模板）。

**陷阱 5 —— 缓存前缀里的时间与「render 一次」。** Q9 已裁：日期到日。
**测试 a**：同一天两次 `render()` 逐字节相等（变异：改成 `isoformat()` ⇒ 红）。
**测试 b**：换掉一个 `SectionSource` 的返回值 ⇒ **下一回合**送进 provider 的
system 必须变（变异：把 `AgentApp.prompt` 存成 `AssembledPrompt` ⇒ 红）。
测试 b 是原稿唯一抓不到 `AssembledPrompt` 类型错的缺口。

**陷阱 6 —— `duration_s` 不是「工具花了多久」。** 它由引擎侧测量，**包含**
人类审批时间（`types.py:239-245` 原话：「把它渲染成『工具用了多久』等于把
一个人自己的思考时间展示给他看」）。**判据必须是结构性的，不是对散文做字符串
匹配**（附录 C-Y13）：渲染器拿到的字段名不叫「工具耗时」，或强制带「含等待」
后缀常量。**测试**断言那个常量。

**陷阱 7 —— `usage` 的两个口径。** `run_stream` 的 `TURN_END.usage` 可能是
`None`；`run` 的永不 `None` 但可能全零，而**全零 = 「要么免费要么没报告」**
（`types.py:204-215`）。**测试**：`usage=None` 与 `usage=Usage()` 渲染出的
文本必须不同。

**陷阱 8 —— 进度 sink 抛异常不得让工具失败。** tools 层已把「sink 缺席或
抛异常都当 no-op」修好（`context.py:493-528`），但**会抛的那个 sink 正是本层
写的**（一个断开的 SSE 连接）。**测试**：sink 每次都抛 ⇒ 工具仍成功返回。

**陷阱 9 —— 取消的触发条件是「最后一个观察者离开 + 宽限期」。** 原稿写的
「任一迭代器 break ⇒ 取消」会让浏览器刷新杀掉一个跑了 8 分钟的回合（Q14）。
**测试**：两个观察者，其中一个 break ⇒ 回合继续；两个都走且宽限期到 ⇒
Task 被 cancel 且**异常被消费**（不留 "Task exception was never retrieved"）。

**陷阱 10 —— `asyncio.Queue` 只在单事件循环内的 Task 之间安全。** harness9
的 `p.Send` 确实是 goroutine-safe（`tui.go:371` 的注释是对的），照抄成
「`asyncio.Queue.put_nowait` 是线程安全的」就是一句自信的错话——而 Channel
恰恰是回调常跑在 SDK 自己线程上的那一面。**跨线程必须
`loop.call_soon_threadsafe`。** **测试**：从一个真实的 `threading.Thread`
投递一个事件，断言它到达且没有 `RuntimeError`。

**陷阱 11 —— `approve()` 的竞态**（Q18）。**测试**：对已取消回合调
`approve` ⇒ 不抛。

**陷阱 12 —— 包装 registry 会把 R3 装回去**（Q16）。**测试 + 变异**见 Q16。

**陷阱 13 —— 面子包不得在模块作用域 import 可选依赖。** **测试**：子进程
import `omicsclaw.entry` 后 `sys.modules` 里没有 `fastapi` /
`prompt_toolkit` / `textual`。

**陷阱 14 —— 摘要超时的落点**（Q11）。**测试**：超时 ⇒ `record.degraded`
非空**且**对话仍被裁到回退目标（只断言「没挂」抓不到错的那种写法）。

---

## 7. 任务分解

> 第 3、4 步的教训：**并行子 agent 各自在自己的 lane 里都是对的，缺陷全部
> 长在 lane 之间**（第 4 步 9 个缺陷有 7 个在接缝上）。所以每个 Task 显式
> 写「你负责哪几条接缝」。**审批全链路不再跨 lane**（附录 C-Y2）。

| Task | 产出 | 接缝责任 |
|---|---|---|
| **A** 地基 | `config.py` + `assembly.py` | ① 两个 reserve 字段没有默认值，必须显式算 ② `Workspace` 是六个工具的唯一构造点（含 Q15 的声明修订）③ `tool_timeout_s` 单一真相源，派生 `BashTool(timeout=T-15)` 与 `EngineConfig(tool_timeout=T)`（§12-2）④ `aclose()` |
| **B** 回合内核 + 审批 | `session.py` + `turn.py` + `events.py` + `approval.py` | ① §3.3 的时序一步不许换位 ② 陷阱 0/1/1b/2/3/3b/4/4b/11/14 全在这里 ③ 直通类事件**携带 `EngineEvent` 原件**，不重新打包 ④ Q16：registry 原样交给引擎 |
| **C** 事件流与渲染 | `stream.py` + `render.py` | ① Q14 的全部（seq / 有界 ring / 多观察者 / GAP）② 陷阱 6/7/9/10 ③ `to_wire` 必须 `json.dumps` 得动，**含 `ToolCall.arguments` 逐字节不变**（0027 的裁决：byte-exactness 关系到缓存与回放证据） |
| **D1** Channel（**先做**） | `channel/` | ① 移植 §5.3 的「搬」清单 ② `base.py` 3 行 + `telegram.py` 9 行 + `feishu.py` 4 行 + 投递 4 行的改接 ③ `SenderPolicy` 无默认值、`approval_timeout_s` 非 None ④ 陷阱 10（跨线程投递） |
| **D2** Desktop | `desktop/` | ① 逐字移植 `wire_contract.py` + `_chat_sse.py`，**8 个版本号不动** ② 只实现 `/chat/stream` + `/health` ③ `source_request_id` 幂等（Q24）④ 陷阱 13（懒加载 fastapi） |
| **D3** CLI | `cli/`（含 `__main__.py`） | ① 移植 834 行 REPL 外壳 ② `interactive.py` 改接 ① 族、**摘掉**②③ 族而不是重写 ③ `tui.py` 只保证 import 不炸，不验收 |
| **E** 两个独立只读评估 | 报告 | §8.6 |

**D1 先做，这是本轮范围修正改掉的顺序。** 原稿按 harness9 的顺序（CLI 先）
排，而实测说 Channel 是唯一一个**全部接缝都只在第①族**的面：`entry` 独力
就能让它整体复活，13 行改动换 3,129 行生产代码。它因此也是这份契约最好的
**第一个真实消费者**——一个只能被参考消费者验证的契约，等于没被验证过。

三条贯穿 D1–D3 的接缝责任：三个面**只**依赖 `TurnEvent` + `render.py` +
`ingress.py`，不得 import `omicsclaw.engine`；移植进来的代码不得把第②③族
的 import 一起带进 `entry/`（§9 的反向分层探针会抓）；**重写行数不得超过
移植行数**（§3.1 的判据）。

A 与 B 有依赖（B 需要 A 的 `AgentApp` 形状），先定 §3.2 为契约，可并行。
C 依赖 `events.py` 的定义。D 依赖 A/B/C。

---

## 8. 测试策略

### 8.1 目录

`tests/entry/`，与 `tests/{schema,provider,engine,tools,context}/` 平级。

### 8.2 环境

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest tests/entry/ \
    -p no:cacheprovider -q -o addopts=""
```

- 解释器 3.13.11；默认 `python3` 是 3.10.14、会失败。
- **无网络，两个厂商 SDK、`fastapi`、`textual` 都没装。**
- **`pytest-asyncio` 没装**：异步测试用 `asyncio.run` 驱动。
- **`black` 装不上**：`awk 'length > 88' <files>` 必须无输出。

### 8.3 三类必须有的测试

1. **分层探针（行为性，子进程）** —— Q2 的两条，复制
   `tests/tools/test_tools_is_a_leaf_layer.py` 的**修好版**并反向。
2. **一个真回合的端到端** —— 脚本化假 provider 跑完整 §3.3 时序，断言送进
   provider 的 `messages` 形状、压缩触发点、落库历史、事件序列与 `seq` 单调。
3. **§6 每条陷阱的点名测试 + 对应变异**。

### 8.4 变异纪律

- **必须跑 `-rfE --continue-on-collection-errors`**：破坏 import 的变异会在
  collection 阶段失败，`pytest -rf` 不列 collection error，于是被误报成
  「存活的变异体」。两个 agent 已经在这上面丢过时间（交接文档 :804-816）。
- 「必须超时」型判据一律改写成快速失败（§6 表头）。

### 8.5 流程纪律（原稿误列进陷阱表的三条）

- **借来的字面量必须在 Python 里重新核验**（交接文档 :210-216）。
- **分层探针要行为性的那一版**（Q2）。
- **评估不得被告知已知缺陷**（§8.6）。

### 8.6 两个独立只读评估（Task E）

两个评估**互不知情**：

- **评估一：正确性。** 重点打接缝（§7 的责任表就是它的地图）与 §6 的陷阱，
  并**逐条推演三个面在同一契约下的行为差异**（附录 C-J4：Task D 一个人做三个
  面，没有人在做三面的对照）。
- **评估二：harness9 对照 + docstring 可核验性。** 给它一张特性清单去审，
  **并告诉它不要信这张表**。第 4.5 步的精炼值得照抄：**把评估瞄准
  docstring 本身**——一句自信的错话是真缺陷，因为下一个人会照着做。

三条纪律：**永远不要把你已经知道的缺陷告诉评估者**；修复是**第三个** agent
的独立任务；评估是**只读**的。

---

## 9. 验收标准

1. `tests/entry/` 全绿；`tests/{schema,provider,engine,tools,context,skills}/`
   **2,053 个**（2026-09-19 实测基线，含 0032 交付的 `tests/skills/`；本计划
   开工时的 1,637 已过期）一个不少、一个不改。
   **两条具名豁免**（照 plan 0030 §9-1 的先例，本计划原稿漏抄了这一条）：
   `tests/tools/test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget`
   与 `tests/tools/test_bash.py::test_a_cancelled_turn_leaves_no_capture_file_behind`
   是**负载敏感的既有 flake**（前者是 socket 自己的 `settimeout` 与模块单调
   deadline 抢，测试钉的是后者的措辞；交接文档 :631-632 已把它记为 open）。
   **判据**：失败一条时必须单独重跑，单独跑过 ⇒ 记为 flake 而非回归；
   两条都已实测单独跑通过。**不许为了让它们稳定去改 `_websafety.py`。**
2. `git status --porcelain` **相对 §0 声明 5 的基线零净增**，唯一例外是
   Q15 的声明修订——`omicsclaw/tools/__init__.py` 的 diff 必须**恰好**是一行
   import 加 `__all__` 一项，多一个字符都算违约。
3. `awk 'length > 88'` 对全部新文件无输出。
4. `import omicsclaw.entry` 在无 `fastapi`/`textual`/厂商 SDK 的环境里成功
   （陷阱 13 的子进程断言）。
5. 反向分层探针两条全过（Q2）。
6. **默认 system prompt 里含 `CLAUDE.md` 的四条安全规则**，删掉该段的变异
   必须让它红。
7. 跑满 3 回合后 `role == system` 恰好一条且在 `[0]`，第一条用户消息仍在。
8. **压缩在生产路径上真的跑过**：一条端到端测试断言触发了 `compact`
   （变异：删掉 §3.3 的 compact 分支 ⇒ 必须红）。§1.2 目标 2 的原话是
   「没有它，第 5 步交付的压缩栈在生产里不可达」，所以它必须有一条验收。
9. **`SenderPolicy` 的收紧方向**（附录 C-Y9；0028 的教训：「『有测试』不等于
   『接上了』……必须同时钉住解析与生效，而且要钉**收紧**方向」）：
   (a) 不给 `SenderPolicy` 就构造 Channel 面 ⇒ 抛；
   (b) 白名单外的 sender 发来的消息 ⇒ **不产生任何回合**（断言
   `SessionRegistry.submit` 未被调用，而不是断言回了一句拒绝语）；
   (c) 群聊 @-mention 未证明归属 ⇒ 同样不产生回合。
10. **交付日有一条可跑的命令**：子进程跑 `python -m omicsclaw.entry.cli`
    喂一行输入，stdout 有模型输出（附录 C-Y15）。
11. §6 的 14 条陷阱，每条至少一个「已确认能杀死某条点名测试」的变异，
    逐条列出「变异 → 被杀的测试名」。
12. 每个落地字面量给出来源：本仓库证据 / harness9 且已在 Python 重新核验 /
    **未核实**。**「未核实」必须逐条列出、不超过 2 条、且每条写明「下一个碰
    它的人要验什么」**，否则本条不通过（原稿此条永远无法失败——附录 C-Y11）。
13. **移植优先，可核实**（§3.1 判据、owner 范围修正）：逐子包给出
    「移植行数 / 重写行数」，**任一子包的重写行数不得超过移植行数**。
    超了就是边界划错了，停下来重划，不是继续写。
14. **Desktop 契约不变更**（Q24）：`wire_contract.py` 的 8 个
    `*_SCHEMA_VERSION` 与移植前**逐字节相同**；一条测试断言
    `desktop_chat_contract()` 的返回值与移植前一致。
15. **`source_request_id` 幂等**（Q24，`durable_ingress_idempotency: True`）：
    同一个 `source_request_id` 重复投递 ⇒ 解析到**同一个** `TurnHandle`，
    不新开回合。**变异**：把它当普通字段忽略 ⇒ 必须红。
16. **超时的单一真相源**（§12-2 owner 裁定）：全仓库 grep，`600` 与 `585`
    这两个数各自只出现一次（`AppConfig.tool_timeout_s` 的默认值与派生式），
    且 `EngineConfig.tool_timeout` 与 `BashTool(timeout=…)` 都由它派生。
    **变异**：把 `bash_timeout()` 改成写死 45 ⇒ 必须有一条测试红。
17. ~~skill 未被接入~~ **作废，随 §12-1 被 0032 取代。** 取而代之的是：
    Q2 的子进程探针确认 **`omicsclaw.skill`（单数，已删除的旧包）** 不在
    `sys.modules`；`omicsclaw.skills`（复数）**允许**出现，并由
    `test_entry_is_the_top_layer.py` 的 `_SUPERSEDED` 常量记录这段历史——
    把那个名字挪回禁止名单，探针就会重新变红。
18. **移植没有把第②③族带进来**：反向分层探针（Q2 第 2 条）对
    `entry/{cli,desktop,channel}/` 同样成立——`omicsclaw.control*`、
    `omicsclaw.memory`、`RunRuntime` 一个都不许出现在 `sys.modules` 里。
    这是移植最容易出的错：搬一个文件，把它的 import 一起搬进来。
19. 两个独立只读评估完成，发现全部处置完毕，结论写进附录 B。
20. `README.md` 按仓库契约更新，`docs/FRAMEWORK-REBUILD.md` 增第 6 步一节。
    **只在第 19 项之后**。

---

## 10. 迁移（属后续任务，此处只记下来）

1. `pyproject.toml:441-445` 的 `[project.scripts]` 有**四个**入口：
   `omicsclaw` / `oc` → `surfaces.cli.launcher:main`，
   `omicsclaw-chat` / `oc-chat` → `omicsclaw.surfaces.cli:main`。翻到新入口
   是迁移的事，四个一起算。
2. 旧 `omicsclaw/surfaces/` 68 文件 / 38,412 行的删除是迁移的事。**本步是
   复制不是移动**（债 §11-9），删除要等三件事都落地：第②族（Run 治理）、
   第③族（持久记忆）、以及 `_main.py` 的 35 处子命令有了归宿。
2b. **解锁顺序建议**，依据是 §5.0.1 的改动量而不是直觉：
   Channel（13 行，全①族）→ Desktop `/chat/stream`（4 行，全①族）→
   CLI REPL 的①半边（10 行里的一部分）→ 等第②族 → `server.py` 其余 60 行
   → 等第③族 → 记忆命令与会话命令。
3. `web_fetch` / `web_search` 在新旧两层**同名**（0029 已点名），迁移必须
   退掉一侧。
4. ADR：本层落地后应有一条 ADR 记「入口层是顶层、三面只消费 `TurnEvent`」，
   并**写死 `oc run <skill>` 与 `omicsclaw.entry` 两个入口的分工**（否则下
   一个人会试图合并它们），同时说明它与 ADR 0005（surfaces umbrella）、
   ADR 0006（typed event stream）的关系——**这两条 ADR 描述的是旧架构**。

   > **2026-09-20 更新，两点。**
   > (a) **「两个入口的分工」这一半已取消。** owner 裁定入口只保留
   > cli / channel / desktop 三个，`oc run <skill>` 不保留——于是没有两族入口
   > 可划界，**问题被删掉而不是被回答**。详见
   > `docs/plans/0037-launch-and-entry-points.md` §2 问题 3 与 §5.3。
   > (b) **`docs/adr/` 目录已被整体删除**（随旧架构），所以这条记录的落点是
   > `docs/plans/`，不是一条 ADR。「入口层是顶层、三面只消费 `TurnEvent`」
   > 这一半仍然有效，已写进 `docs/FRAMEWORK-REBUILD.md` 第 6 步。

---

## 11. 已知债务（本层交付后仍然开着的）

| # | 债 | 影响 |
|---|---|---|
| 1 | **回合内压缩接不住** | 0030 §11.B-1 原样继承。形状 harness9 有现成的（`WithCompactor`，`options.go:135-138`） |
| 2 | 未知模型的上限是乐观的 | `get_model_limits` 对未知模型返回 `DEFAULT_MODEL_LIMITS`，`output_tokens=8192` 的含义是「**不知道**」而非「就是 8192」。本层是第一个真正调它的地方 |
| 3 | 审批没有引擎侧表示 | 本层用自己的事件绕过去了，但**子代理层将来会再遇到一次**（子引擎的审批要穿两层） |
| 4 | **没跟真 HTTP / 真 IM 说过话** | 与 provider 层「没跟真端点说过话」同一笔债。第 3 步的评估已证明这笔债的代价不是假设的 |
| 5 | `Message` 装不下 Anthropic thinking 签名 | schema 的已知债，本层只是第一个会被用户看见它的地方 |
| 6 | 没有多模态 | Channel 的照片入口因此丢弃（§5.3） |
| 7 | 投递 Pump（顺序 + 重试）未建 | 旧层已有三态返回，本步搬过来；真正的重试与去重策略仍未建 |
| 8 | **三个面不会全部复活**（Q23） | `cli/interactive.py` 与 `desktop/server.py` 还焊在第②族（`RunRuntime`）与第③族（memory）上。`entry` 落地后，Channel 可整体工作，Desktop 只有 `/chat/stream`，CLI 只有 REPL 的 agent 半边。**每个挡住项的改动行数已量出**（§5.0.1），解锁那天是分钟级的工作 |
| 9 | 旧 `surfaces/` 与 `entry/` 会并存一段时间 | 移植是复制不是移动（§10）。并存期内两处同名文件的分歧是真风险；缓解是旧的那份已经不可导入（30 个文件缺已删包），没人会误用它 |

---

## 12. ~~待 owner 拍板~~ —— **五项全部已裁定**

### 12-1 skill —— ~~整体预留~~ **已被 0032 取代（2026-09-19）**

> **结局先写在前面。** owner 协调两个并发会话之后，`docs/plans/0032-skill-loader.md`
> 落地了一个新的 `omicsclaw/skills/`（harness9 形状：`frontmatter` /
> `index` / `loader` / `skill` / `use_skill`），并接进了 `assembly.py`。
> `entry` 的公开面上现在有 `SkillsIndex` 与 `build_skill_index`，
> `AppConfig.skills_index` 有 `full` / `compact` / `off` 三档。
>
> **本条裁定的前提消失了，所以裁定随之作废**——前提是「那批 skill 正在等
> 重新设计」，而 0032 就是那次重新设计。**这不是推翻，是前提到期。**
>
> 连带失效：Q10（改为「已被取代」）、Q9 段表第 6 段（skills index 现在注入，
> 档位由 `SkillsIndex` 决定）、§9-17（删除）。**仍然有效**：分层探针禁止
> `omicsclaw.skill`（**单数**，旧包，已被删除）；`omicsclaw.skills`（复数）
> 是允许的。`tests/entry/test_entry_is_the_top_layer.py` 用一个具名常量
> `_SUPERSEDED` 把这段历史钉在代码里，而不是抹掉。

以下为原裁定，保留作记录：

#### ~~已裁定：整体预留，工具与索引段都不接~~

> **owner 原话**：「skill 暂时预留着，当前项目下的 skill 我还得重新设计和
> 迁移，现在接进来会造成一些问题。」

这条**推翻了评审阶段的建议**（「工具不接，但索引段读 `skills/*/INDEX.md`」，
理由是那样零新组件就能在交付日做 omics 分析）。推翻是对的：那八个 INDEX.md
描述的正是**即将被重新设计与迁移**的那批技能，把它们烘焙进 system prompt，
代价是模型按一份过期清单去找不存在的东西——比「模型不知道有技能库」更难查。

落地见 Q10（接缝、代价、分层探针名单）与 Q9 段表第 6 行。

### 12-2 `tool_timeout` —— **已裁定：抬到 600 秒，且单一真相源**

> **owner 裁定**：选项 B（600 秒）。

原稿拒绝这个选项的理由是**事实错的**，评审已改正：实测
`BashTool.__init__(..., timeout=DEFAULT_TIMEOUT)`（`bash.py:551-566`）、
`max_timeout` 返回 `self.timeout`（`:582-592`）、`min(requested,
self.max_timeout)`（`:690`）——**`BashTool` 的超时是构造参数**，而 §3.1/Q7
明确 `assembly` 是六个基础工具的**唯一构造点**。所以入口层恰恰是唯一一个能把
两半一次调一致的地方：`BashTool(timeout=585)` + `EngineConfig(
tool_timeout=600)`，`max_timeout` 随之变成 585，模型也就能申请到更长。
「只抬一半」这个风险在这一层消失。

**两条附带约束，都进 §9 验收**：

1. **单一真相源。** `AppConfig.tool_timeout_s = 600.0` 是这两个数的唯一
   来源，`engine_config()` 与 `bash_timeout()` 都由它派生。**留两个独立
   字面量是不可接受的**——那样迁移那天仍然会只抬一半。
2. **必须与「取消真正可用」一起交付。** 把单个工具的上限抬到 10 分钟，意味着
   一个卡住的 bash 能占住一个会话 10 分钟；陷阱 9（最后一个观察者离开 + 宽限
   期 ⇒ cancel 并回收）与 Q12 的 `turn_timeout_s` 是它的前提，不是可选项。

以下为原裁定前的选项表，保留作记录：

| 选项 | 说明 |
|---|---|
| A（保守） | 保持 60。风险是它在第一条生产通路上固化下来 |
| **B（已选）** | 抬到 600。交接文档 :619-625 已给反证：`spatial-deconv` 或 STAR 比对是几分钟到几小时 |
| C | per-tool 超时 —— 新机制，属工具层，会让本步变成两个组件 |

### 12-3 包名 —— **已裁定：`omicsclaw/entry/`**

Q1 已给理由与被淘汰的候选（`app/` 与本仓库 Desktop「App」撞义，`agents/`
复数已被占用）。两份评审均无异议。**不夺 `surfaces/`** 的理由同样确认：它
仍在服务 `oc list` / `oc run`。

### 12-4 Channel 真适配器 —— **原裁定「不带」，因范围修正而作废，见 12-5**

原裁定的前提是「真适配器要从零写，而本机无网络无 token，一行都测不了」。
范围修正之后这个前提不成立：`telegram.py`(752) 与 `feishu.py`(766) **已经
存在且只需改 13 行**。「不带」于是从「谨慎」变成「把 1,518 行现成实现放着
不用」。两条必须做完的形状（`SenderPolicy` 收紧方向、投递三态）**保留且
加强**——后者实测**旧层已经实现好了**（`telegram_delivery.py:161-164` 的
`ACCEPTANCE_UNKNOWN`），本步是搬而不是造。

### 12-5 owner 范围修正（2026-09-19）—— **已裁定：三面复用现有实现**

> **owner 原话**：「计划里的 channel、cli 和 desktop app 可以复用当前项目
> 已实现的相关代码组件，只是说需要你帮我搭建一个高内聚低耦合的 entry
> 组件，使其不要干扰到 agent main loop。」
> 追加：「还是需要有 `cli/` `desktop/` `channel/` 三个子文件夹……desktop
> 我有另一个单独的 OmicsClaw desktop 去实现它。」

**这条裁定推翻了本计划的一个基础假设**，而且它是对的。原稿把三个面判成
「重建」，依据是裁定 0 的「旧层独有 ⇒ 丢弃」。实测之后这个依据站不住：

- 耦合密度 **0.39%**（38,412 行里 148 行）。
- 只焊第①族的有 **19 个文件 / 10,255 行，改 51 行**即可解锁。
- Channel 的两个生产适配器**各缺一个符号**。
- Desktop 的线路契约**已发布、带版本号、且干净**——重写它等于单方面改一份
  外部客户端依赖的协议。

**掀翻的条目**：§1.2 目标 4、§2 范围、§3.1 模块清单（三个子包回来，性质
从「写」变「搬」）、§5 全表（默认值从「丢弃/重建」换成「移植」，**4 项从
丢弃改判为挡住**）、§7 Task D（拆成 D1–D3，**Channel 先做**）、§9（新增
第 13/14/15/18 条）、§10（迁移路线）、§11（新增债 8/9）、本条与 12-4。

**没被掀翻的**：Q1–Q22 的全部裁决、§6 的 14 条陷阱、§8 的测试与评估纪律。
它们讲的是 `entry` 核心自己的形状，与三个面怎么来无关——**这正是「高内聚
低耦合」在这份计划上的检验**：范围换了一次，核心一条没动。

---

## 附录 A —— harness9 入口层原始材料

`cmd/harness9/` 非测试合计 **3,929 行**：`main.go`(470)、`cli.go`(105)、
`tui.go`(377)、`tui_banner.go`(55)、`tui_update.go`(1883)、
`tui_view.go`(727)、`upgrade.go`(312)。

### A.1 `main.go` 的装配顺序（逐行核实）

| 行 | 做什么 | 本层对应 |
|---|---|---|
| :66-72 | `upgrade` 子命令在 flag 解析**前**处理 | 无 |
| :74-110 | flag / usage / `--version` | `resolve_app_config` |
| :112-119 | `os.Getwd()` + `env.Load(cwd/.env)` | 同上，Q8 |
| :121-122 | `signal.NotifyContext(SIGINT, **SIGTERM**)` | CLI 的取消**与 Q17 的停机**——SIGTERM 才是容器里杀进程的方式 |
| :126-136 | Observability，默认 noop，失败降级 | 不做（Q13） |
| :142-145 | 加载 skills（目录不存在静默返回空 Index） | **整个不做**（Q10，owner 裁定）：不接工具，也不注入索引段 |
| :147-163 | provider + Tracing 包装 | `assembly`（不包装） |
| :165-211 | Sandbox：**通知 channel 必须在 Create 之前注册**（:173-174）、**未启用时保持 nil 以免消费者在无发送方的 channel 上永久阻塞**（:175-176）、**降级原因注入 prompt 与状态栏**（:169-171） | 不做 sandbox；但后两条的教训分别进陷阱 1b（一个永远不会有人 put 的队列就是它的 Python 版）与本层 docstring |
| :215-224 | PromptBuilder，三态 sandbox 说明 | `assembly` 的段集合，Q9 |
| :232-236 / :242-245 / :442 | Memory Manager / NewSession / `WithSession` | `session.py`，Q4 |
| :249-265 | 长期记忆 Store + Precis | 不做 |
| :268-289 | Registry + **十个基础工具的唯一注册点**（`registry.Register` 在 :406 还有一次 task 工具，MCP 还会在 :318 `InjectTools`） | `assembly`，六个工具 |
| :291-323 | MCP：异步启动避免冷启动阻塞 TUI | 不做（Q13，含代价说明） |
| :325-338 | hooks：permission / danger / offload / observability | 不做（Q13） |
| :346-409 | Sub-Agent | 不做（Q13） |
| :411-417 | Hook 执行顺序（观测放最后，不干预决策） | 不做 |
| :419-430 | Compactor（extractor / recordStore / offloader） | `assembly.summarizer`，简得多 |
| :440-451 | `engine.NewAgentEngine(llm, hookReg, workDir, opts…)` | `assembly.engine` |
| **:453-468** | **三路分派**：`--prompt-file` → `RunOnce`；`term.IsTerminal(stdin)` → `RunTUI`；否则 → `RunCLI` | **`entry/cli/` 两路**（无 TUI） |

### A.2 `cli.go`（105 行，全部内容）

`RunCLI`(:20-22) 委托给可测内核 `runCLI(ctx, eng, io.Reader, idx)`(:36-79)：
`ctx.Done()` / EOF / `exit|quit` 三个出口。`RunOnce`(:27-33) 把**整个文件**
当一次 `userPrompt`，注释写明理由：「与逐行 REPL 不同，避免多行任务指令被
误拆成多个独立 Turn」。`resolvePrompt`(:83-105) 是 `/skill-name [附加文本]`
的展开。**注入 `io.Reader` 做可测内核这一手值得照抄**。

### A.3 `stream.go` 的三条硬约束（全文读过）

1. **审批消费者契约**（:51-58）→ 陷阱 1。
2. **审批等待用会话级 ctx，不用工具 ctx**（:172-199）→ 本仓库已在 tools 层
   用 `TimeoutPause` 解决得更彻底；**本层要做的不是「不撤销」而是 Q16 那条
   可测的约束**——撤销它只需要包一层。
3. **终止事件直接 `ch <-` 而非 `sendEvent`**（:133-134）+ `defer close(ch)`
   → 陷阱 1b。

### A.4 `tui.go` 的两条（只用结构，不用细节）

- 事件泵是 `readNextEvent(ch) tea.Cmd`（`tui_update.go:203`），Elm 循环每收
  一个事件回一个新 Cmd —— 与本层「观察者迭代 `TurnObservation`」同构。
- 后台通知用 `p.Send`，注释写明 goroutine-safe（`tui.go:370-374`）。
  **本层的等价物只在单事件循环内的 Task 之间安全**——见陷阱 10。

### A.5 未核实

- `upgrade.go`(312) 未读。
- `tui_update.go` / `tui_view.go` / `tui_banner.go` 只读函数清单，未逐行；
  本计划不引用其内部行为。
- harness9 的 `benchmarks/`、`internal/evals/` 未读。

---

## 附录 B —— 交付结果

**全部实现 lane、两路独立只读评估、以及修复轮均已完成（2026-09-19）。**
最终状态：`omicsclaw/entry/` = 10 个核心模块 + `channel/`(8,007) +
`desktop/`(1,593) + `cli/`(2,171)；`tests/entry/` **619 passed, 1 skipped**；
`python -m omicsclaw.entry.cli` 实跑不崩。

**§9-20（收尾）于 2026-09-20 完成**，且按纪律排在第 19 项之后：`README.md`
的「What's New」加了第 6 步一节，`docs/FRAMEWORK-REBUILD.md` 的目标层结构表
`entry/` 打勾、第 6 步一节补齐第二波（会话/事件流/审批/三面）、债表加 4 行、
「Next step」改为第 7 步 `omicsclaw/memory/`（plan 0033）。收尾前由协调者重测：
`tests/entry/` **619 passed, 1 skipped**、其余重建栈（`--ignore=tests/tools/test_workspace.py`）
**2,089 passed**、`python -m omicsclaw.entry.cli` 仅止于 `ProviderError`（本机
无 key / 无网络的预期结果）。

那两件「只在对话里存在过」的待拍板事项已入档到 `docs/FRAMEWORK-REBUILD.md`
第 6 步，并在 **2026-09-20 由 owner 裁定**：

1. **`__main__.py` 的 argv 豁免** —— 两个选项都不选：**旧的启动方式要按新框架
   重新设计**（保持高内聚、低耦合）。该设计是独立任务，落地前豁免继续有效。
2. **`--prompt-file` 一名两义** —— **改 system prompt 那一个**。已落地：
   `--system-prompt-file` / `OMICSCLAW_SYSTEM_PROMPT_FILES` /
   `AppConfig.system_prompt_files`；`--prompt-file` 恢复 harness9 语义（单次
   执行的 user prompt）。**不留别名**——留别名等于保留它要消除的那个失败——
   部署半边现在直接拒绝旧名，由
   `tests/entry/test_config.py::test_the_deployment_half_no_longer_answers_to_the_surface_flag_name`
   钉住，并已做变异验证（把旧名放回去 ⇒ 该测试红）。
   `tests/entry/` 因此从 619 变 **620 passed, 1 skipped**。

### B.0 两路评估的结论，以及本步最贵的一课

两路评估（正确性 / 对照与可核验性）互不知情，**在五条上独立收敛**
（`assembly.py` 的过期断言、`loop.py:262→287`、`interactive.py:2104→2110`、
不存在的 `ADR 0077`、`render.py` 的 `BATCH_CHARS` 证据句）。各自独有的四条
阻断，协调者逐条实跑复验后才派修复：

| # | 缺陷 | **它为什么能全绿** |
|---|---|---|
| R1 | `python -m omicsclaw.entry.cli` 一跑就崩（`provider.model` 不存在），`/health` 同病 | 共用的 provider 替身给自己加了一个 `model` property——**替身比被测协议宽** |
| R2 | `SessionStore` 一抛 ⇒ 整条会话永久卡死、终止帧永不到达、`shutdown()` 救不回来 | 唯一实现 `InMemorySessionStore` 从不抛；**陷阱 1b 的责任随持久化搬到注册表，测试没跟着搬** |
| R3 | 排队中的 `cancel()` 落在 `await store.load()` 窗口里被静默丢弃 | 内存 store 不 await，那个窗口在测试里不存在 |
| R4 | `bot_identity=""` 的群消息 fail-closed 闸**零测试**（唯一存活的变异体） | 所有测试都传非空 `bot_identity` |

> **最贵的一课，也是本计划自己写过又自己犯了的那条。**
> §9-10 我立的验收是「交付日有一条可跑的命令」，交付时它是绿的、协调者也亲自
> 跑过测试——**而真命令一跑就崩**。原因是测试替身声明了一个真协议没有的属性。
> 这正是 §5.0.1 引的 0028 那句「静态检查查拼写，只有行为探针查事实」，**在同一份
> 计划的交付物上、在同一条验收上又犯了一次**。
> **规则**：一个入口层的验收必须由**真 provider、真 `__main__`** 跑出来；
> 一个比协议宽的替身跑出来的绿，证明的是替身。修复轮补了三条纪律测试把它钉死
> （AST 扫「本层读了协议没有的 provider 属性」、扫「替身声明超出协议」、扫
> sitecustomize 垫片同规则）。

修复轮（第三个 agent，既没写代码也没做评估）处置了 R1–R14 与 14 条引用类错误，
并**驳回了评估的 5 处错误**——其中两处是评估自己犯了它刚指出的那个错（grep 错
文件：`route.ts` 只做终止帧的两键校验，词汇表的 switch 在
`useSSEStream.ts`；`tool_use` 与 `status` 客户端其实认识，只有 `event_omitted`
零命中）。另有一处两路评估结论相反（`AGENTS.md:462`），修复轮实测判定：第一路
对，第二路读的是**本仓库**的 `AGENTS.md` 而不是 harness9 的——引用处已加消歧。

修复轮还发现评估的覆盖不全：用户正文写进 INFO 日志的适配器，评估点名 2 处，
实际 **6 处**（另有 discord / slack / wechat 与 telegram 的整条命令行）。
检测器的作用域因此从 4 个模块扩到 `omicsclaw/entry/**` 全树——
**作用域才是缺陷，规则没错。**

### B.1 Wave 1 交付物

### B.1 Wave 1 交付物

| 模块 | 行数 | lane |
|---|---:|---|
| `config.py` | 533 | A（+0032 扩了 `SkillsIndex`） |
| `ingress.py` | 268 | A |
| `assembly.py` | 726 | A（+0032 扩了 skills 接线） |
| `events.py` | 496 | C |
| `stream.py` | 491 | C |
| `render.py` | 544 | C |
| `turn.py` | 253 | A（越界产出，见 B.4） |
| `__init__.py` | 70 | A |
| **合计** | **3,381** | |

`tests/entry/` **197 passed**；`tests/{schema,provider,engine,tools,context,skills}`
**2,053 passed**（§9-1 的新基线）。

### B.2 实测契约（§3.2 已被它取代）

`turn.py` 是一个**函数式内核**，不是 §3.2 的 `TurnRunner`/`TurnHandle`：
`compose` → `prepare`（measure+compact）→ `run_turn` / `stream_turn`，
外加 `TurnOutcome(result, history, prompt, state, compaction)` 与
`at_least(measured, threshold)`（陷阱 0 的档位序）。Wave 2 在它**之上**加
会话归属、Task 隔离、事件流、审批与取消，**不重写它**。

`TurnStream(session_id="", turn_id="", *, ring_size=2048, observer_queue_size=64,
max_observers=16, on_observer_change=None)`，方法 `publish` /
`publish_threadsafe` / `observe(*, after_seq=0)` / `observer_count` /
`latest_seq` / `sealed` / `retained`；`TurnObservation` 有 `aclose` /
`close` / `closed` / `detached`。`TurnEvent` 15 个字段、14 个类型。
`TextRenderer(*, batched=False, batch_chars=2000, show_reasoning=False)`。

### B.3 §3.2 在实现阶段暴露的增补（10 处，全部是「加」不是「改」）

`from_engine` 返回 `TurnEvent | None`（`EngineEventType.DONE` 无对应物，
映射过去会让顺利路径出现两条终止帧）；`queued_ahead` 与 `decision` 两个字段
（Q7 与 `APPROVAL_SETTLED` 原本无处放结论）；`TurnStream.__init__` 在 §3.2
里**根本不存在**而 Wave 2 必须构造它；`TurnObservation.aclose()`（`async for
… break` 对一个有 `__anext__` 的对象没有关闭钩子，陷阱 9 要求「离开可被
观测」）；`on_observer_change` 回调（宽限期定时器需要事件而不是轮询）；
`publish_threadsafe`（陷阱 10 要求存在一条受支持的跨线程通路）；
`EventHubCapacityError` → `ObserverCapacityError`（本层没有 hub，一个 stream
属于一个回合，沿用旧名是在描述一个不存在的组件）；`GAP` 语义扩用到「慢观察
者丢 delta」且 `GAP.seq == oldest_available - 1`，于是把 GAP 帧的 seq 存成
游标再重连是正确的；`to_wire` 的 `"type"` 用 `TurnEventType` 的值而非
`/chat/stream` 帧名（14 个里只有 5 个有已发布名字，替另外 9 个发明名字等于
单方面向外部客户端公布词汇），映射单独导出为 `DESKTOP_CHAT_FRAME_TYPE` 留给
D2；`InboundMessage.values` 用 `Mapping[str, object]` 而非 `Any`。

**本计划自身的错误，实现阶段新发现的 4 条**（实现前那一轮记在附录 C）：

1. **§9-2 与 §9-1 在 Q15 上互斥**，见 Q15 的「实现结果」块。
2. **§9-1 漏抄了 plan 0030 的 flake 具名豁免**，已补（§9-1 现有两条）。
3. **陷阱 10 的判据本身杀不死错误实现**：从外线程直接 `publish` 也会「到达
   且无 `RuntimeError`」，只是要等事件循环因别的原因醒来（本机 5 秒）。判据
   必须加「线程先 park 让 loop 真正停在 `select()` 里 + 断言到达耗时上界」。
   **这是一条通用形状：一个只断言「最终发生了」的测试，测不出「及时发生
   了」。**
4. **`build_app()` 没有 provider 注入口**，而 §8.3-2 要求「脚本化假 provider
   跑完整时序」。当前替代路径是 `dataclasses.replace(app, provider=fake)` 且
   **必须同步 replace `engine`**（否则 engine 里还绑着真 provider，是一个静默
   缺陷）。建议给 `build_app` 补一个 `provider=` 关键字参数。

### B.4 过程教训：两个会话并发写同一批文件

本步是这套「一步一组件 + 双盲评估」流程第一次遇到**两个会话并发**。损害是
可点名的：Wave 1 的 `NotImplementedError` 占位被另一会话删除、
`tests/entry/__init__.py` 被清成 0 字节、一条断言「不注入 skills 段」的测试
被替换成断言「skills 段必须到达 system prompt」、一个子 agent 被终止在
「原子地移除 skills 接线」中途留下**跨文件半途状态**（`config.py` 丢了
`_Option` 与 `_as_pressure` 两个定义、`__init__.py` 仍引用已消失的
`build_skill_index`，整个包不可 import）。

三条带走：

- **一个被终止的 agent 留下的不是「未完成」，是「半完成」。** 终止之后的第一
  件事是查工作区完整性，不是读它的报告。
- **冲突要写进代码，不要抹平。** Wave 1 的处理是对的：`_SUPERSEDED`
  常量把「0031 禁止 / 0032 落地 / 挪回去就会重新变红」钉在测试里，于是这次
  裁定的历史是可执行的而不是口头的。
- **并发会话下，「1637 passed」这种数字本身会漂。** 本步中途 `conftest.py`
  的一条 autouse fixture 让全仓 765 个测试同时 error，与本层无关。基线必须在
  每次派工前重测，而不是沿用上一轮。

---

## 附录 C —— 计划评审结果（实现前）

本计划在实现开始**之前**过了一轮**双盲**独立只读评审：一路查事实可核实性，
一路查设计健全性，互不知情、也都不知道对方存在。**两路独立收敛到同四条**
（`Pressure.HIGH` 不存在、`StrEnum` 的 `>=` 不是档位序、`AssembledPrompt`
没有 `render()`、`CompactionState` 被丢掉）——按 0028 的说法，这种收敛比任何
单份报告都值钱，而且**只有第一次有效**。

全部发现已由本轮修复，且**每一条阻断都由协调者独立复验**（`inspect.signature`
/ 实跑 / 读源码），未直接采信报告。

### C.1 阻断（照做会直接写出错代码）

| # | 一句话 | 复验证据 | 处置 |
|---|---|---|---|
| Z1/B1 | `Pressure.HIGH` 不存在 | 五档实测为 `NONE/WARN/SOFT/FULL/EMERGENCY` | 改 `Pressure.FULL`；陷阱 0 |
| Z1b/B3 | `report.pressure >= compact_at` 是字符串比较 | 实测 `NONE>=FULL → True`、**`EMERGENCY>=FULL → False`** | `_PRESSURE_ORDER` 映射；陷阱 0 + 五档逐个断言 |
| B2 | `measure` 少传 `tools` | 实测签名 `measure(messages, tools, budget, *, counter)` | §3.3 改三参；Q19 |
| Y1 | 下游用了原始 `budget` 而非 `report.budget` | `budget.py:282-315`「两者取更收紧的那个」 | §3.3 改 `report.budget`；Q19 |
| Z2/B4 | `AgentApp.prompt: AssembledPrompt` + `.render()` 自相矛盾 | `render()` 在 `PromptAssembler`(:120)；`AssembledPrompt`(:79) 只有三个 property | 改 `PromptAssembler`；**并补陷阱 5 测试 b**——这是原稿唯一抓不到它的缺口 |
| Z6/B5 | `CompactionState` 被整个丢掉 | `compaction.py:150-158`「由调用方在回合之间携带；第 6 步决定它住在哪」 | `Session.compaction`；陷阱 4b |
| B6 | 陷阱 3（取消后 `repair_tool_pairs`）在自己的时序里不可达 | `loop.py:209`（局部 `history`）、`:267-274`（只在 DONE 出口）、`:482-569`（`_answer_every_call` 保证无孤儿） | 改判「取消即不落库」；并新增 §3.3 要点 4「本层不调 `repair_tool_pairs`」 |
| Z3 | 终止帧没有 `finally`，最可能的真实故障是永久挂起 | `stream.go:133-134` 的两道保险 | 陷阱 1b |
| Z4 | 取消语义与「终止必达」自相矛盾，Desktop 分不清跑完与断线 | — | Q5b 重写：终止帧恒发且恰好一条，取消是 `terminal` 的一个值 |
| Z5 | `await store.save` 写在被取消的 Task 里必然再被取消，而内存 store 让测试因为错误的理由变绿 | 与 0029 评估 #6 同形 | 陷阱 3b：落库移出被取消的 Task；fake store 必须真 await |
| **Z7** | **`TurnHandle` 把回合身份与一次观察合成一个，SSE 重连与 Channel 重投递都无解；陷阱 9 的方向是反的（刷新一次 = 杀掉 8 分钟的回合）** | `HEAD:control/event_hub.py` 的 `sequence` / `deque(maxlen)` / `cursor_evicted` / `EventObserverDetached`；`turn_observation.py` docstring 首句 | **Q14 新增（本轮最大的一处改动）**；§5.0 加例外二；陷阱 9 改写 |
| A1 | `Workspace` 不在公开面上，而 §1.2 又禁止改既有文件 | 实测 `from omicsclaw.tools import Workspace` → ImportError | Q15：一条声明修订，照 0027 先例；§9-2 列为唯一例外 |
| A13 | `DeadlineAwareExecutor` 接缝断了 = 把刚修好的 R3 装回去 | `executor.py:116` runtime_checkable、`:380-385` isinstance；实测 `ToolRegistry` 两个 Protocol 都满足 | Q16 + 陷阱 12 |

### C.2 应修（已全部落地）

A2 `TURN_END` 是每次模型调用一次、与新加的 `TURN_START` 基数不匹配 →
Q21 改名 `EXCHANGE_*`。
A3/Y14a 摘要超时套错位置（套 `compact()` 得到的是异常，不是降级）→ Q11，
**并把验收从「没挂」改成断言 `record.degraded`**。
Y3 绑了 progress sink 却没有落点 → Q20 补 `PROGRESS`。
Y4 上下文压力上报到期 → Q19 补 `CONTEXT`。
Y5 「无界队列是唯一解法」对「慢但在线的消费者」无对策 → 与 Q14 合并为
「delta 可丢 / 控制不可丢」。
Y6 进程生命周期与优雅停机全缺（`main.go` 有 5 个 `defer`）→ Q17。
Y7 「同 session 串行」只有锁没有排队语义 → Q7。
Y8 长回合对 IM 无时间契约 → Q12 三条。
Y9 `SenderPolicy` 被抬成唯一安全例外却零验收 → §9-9 三条，钉**收紧**方向。
Y10 `ChannelTransport.send` 的三态接受性 → §12-4 + §11-7。
Y11 §9-9 原文永远无法失败（「未核实」永远可选）→ §9-12 加上限与要求。
Y12 「必须挂/超时」型变异判据会挂死 suite → §6 表头 + §8.4。
Y13 陷阱表混进三条流程规矩、陷阱 6 对散文做字符串匹配 → 移进 §8.5；
陷阱 6 改结构性判据。
Y14b `asyncio.Queue` 不是线程安全的（A.4 照抄 harness9 会写出一句自信的
错话）→ 陷阱 10。
Y14c `approve()` 竞态 → Q18 + 陷阱 11。
Y14d Task 异常必须被消费 → 陷阱 9。
Y15 交付日没有可跑的命令 → `cli/__main__.py` 进范围 + §9-10。
Y2 审批全链路跨三条 lane → §7 把 `approval.py` 并入 Task B。
Y16/A12 §9-2 按字面不可满足（基线已有 320 条 `D `）→ §0 声明 5 记基线，
§9-2 改判净增量。
A11 ADR 0024 的机制说反了（它说的是**逐字节前缀自动缓存**，OmicsClaw
**不需要** `cache_control`）→ Q9 改正。
A4 `AGENTS.md:465`→**:462**。A5/A6/A7/A9/A10/S7 全部计数改正：CLI
**26 文件 / 14,936 行**、Channel **20 / 7,059**、三组支持文件 **2,649**、
IM 适配器 **9 个 `.py`**（10 是平台数）、harness9 TUI **3,042**、Desktop
**16,401**、notebook **3,569**。A8 「40 余个子命令」改为可复现的
「**35** 处 `add_parser`（含二级）」。
S2 交接文档 `:634-637`→**:633-636**。S3 `:740-742`→**:739-741**。
S4 sandbox 行号 `:174-177`→**:173-174** 与 **:175-176**。
S5 `builder.go` 是**七**段（漏了 Sandbox 三态说明 `:150-175`）。
S6 `AGENTS.md:408-482`→**:408-474**。
S8 「唯一的解法」→ `tools/context.py:136-141` 自己给了**两种**，本层选独立
Task 并说明理由。
S9 chat SSE 的证据补 `_chat_sse.py`(200) 与 `wire_contract.py`(149)。
S10 `[project.scripts]` 是**四个**入口。
S11 「唯一注册点」限定为「十个基础工具的」。
S12 未知模型上限是乐观的 → §11-2。
J1 `render_text` 纯函数装不下 Channel 的批投递 → `TextRenderer` 有状态。
J2 MCP 晚注入花的是缓存前缀 → Q13 那行加代价说明。
J3 回合级事实没有位置 → `TurnRunner` 合并 `{**session.values, turn_id}`。
J4 没人负责三面对照 → §8.6 评估一的 brief 加一条。
J5 压缩在生产路径上真跑过没有验收 → §9-8。
J7 ADR 要写死两个入口的分工 → §10-4。
12-1 索引段可以不留空且零新组件 → §12-1 曾据此改写，**随后被 owner 推翻**
（skill 整个预留，见 §12-1）。记在这里是因为评审的论证本身没错——错的是它
不知道那批 skill 正在等重新设计，而**一份即将过期的目录比没有目录更难查**。
12-2 原稿拒绝选项 B 的理由是事实错的（`BashTool` 的超时是构造参数，而装配
根是唯一构造点）→ §12-2 改写，并把「单一真相源」提为硬约束。

### C.3 评审报告中未采纳的部分

无。两份报告的每一条阻断都经独立复验成立；应修与建议按上表处置。**报告里
引用的行号本轮全部复验，未发现报告自身的行号错误**——这与 0030 那一轮不同
（那一轮评审自己错了 3 处），记在这里是为了让下一次不要默认「评审也会错」
而降低采信强度。
