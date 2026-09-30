# Long-Term Memory：会话状态与跨会话长期记忆

## 1. 背景与设计目标

### 1.1 两种"记忆"

OmicsClaw 把"记住"拆成两件性质完全不同的事，它们共用一个 SQLite 文件，但由不同的类负责：

| 记忆 | 回答的问题 | 生命周期 | 实现 |
|------|-----------|---------|------|
| **会话状态**（Session State） | "这段对话说到哪了？" | 一个会话，可跨进程 `/resume` | `SqliteSessionStore`（`omicsclaw/memory/sessions.py`） |
| **长期记忆**（Long-Term Memory, LTM） | "这个用户 / 这个项目有什么稳定事实？" | 跨会话，直到被删除或过期 | `LongTermStore` + `Precis` + `MemoryExtractor` |

引擎本身（`omicsclaw/engine/`）没有 `Session` 概念——"一段对话进去，一段对话出来"。对话历史与压缩状态住在 `omicsclaw/entry/session.py` 的 `Session` 上，由 `SessionRegistry` 在每次 exchange 结束后通过 `SessionStore` Protocol 落盘；长期记忆则由组合根 `omicsclaw/entry/memory.py` 接进工具、system prompt 和压缩器。

对一个多组学 agent 来说，前者保证"昨天跑到一半的 Visium 分析今天接着跑"，后者保证"这个项目的空间域识别一律用 leiden、用户偏好中文报告"这类事实不必每次重说。

### 1.2 设计目标

| 目标 | 实现机制 |
|------|---------|
| **会话跨进程存活** | `sessions` + `messages` 两张表；每次 exchange 结束由 `SessionRegistry` 保存 |
| **压缩状态不丢** | `sessions.summary` / `sessions.anchors` 持久化 `CompactionState`，下次压缩接着上次的摘要走 |
| **跨会话持久化** | `long_term_memories` 表，与会话共用 `<workspace>/.omicsclaw/memory.db` |
| **有界 Token 注入** | `MEMORY.md` 物化视图（≤ 5120 字节、≤ 30 条），作为 system prompt 最后一段 |
| **按需深度检索** | FTS5 全文检索，`memory_search` 工具 |
| **两路自动写入** | 显式工具 `memory_write` + 压缩前 `MemoryExtractor` |
| **去重与遗忘** | SHA-256 内容指纹去重 + TTL 过期删除 + 软删除 + 陈旧候选查询 |
| **零新增依赖** | 标准库 `sqlite3` + `asyncio.to_thread`，不依赖 `aiosqlite` |
| **一个开关** | `AppConfig.memory`（`--memory` / `OMICSCLAW_MEMORY`）同时控制库、两个工具、prompt 段、提取器与会话存储 |

---

## 2. 架构与包边界

```
┌──────────────────────────────────────────────────────────────────────────┐
│ omicsclaw/launch/_surfaces.py   _run_cli / _serve_desktop / _serve_channels│
│      app = attach_sessions(await open_app(config))                        │
└───────────────┬──────────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────────┐
│ omicsclaw/entry/  （组合根，唯一允许打日志的层）                             │
│                                                                          │
│  assembly.build_app ──► memory.open_memory(config) ──► MemoryBinding       │
│     │                     (database, store, precis)                      │
│     ├─ foundation_tools(..., memory=)  ──► memory_search / memory_write    │
│     ├─ default_sections(..., memory=)  ──► "## Long-term memory" 段（闭包） │
│     └─ AgentApp.memory                                                   │
│  assembly.open_app ──► _swept ──► memory.prepare_memory                   │
│                         (purge_expired + precis.regenerate)              │
│  compaction.build_compactor ──► memory.build_memory_extractor             │
│                         ──► PrecisRefreshingExtractor                    │
│  session.attach_sessions ──► memory.session_store ──► SqliteSessionStore  │
│  session.SessionRegistry  load() 首次取用 / save() 每次 exchange 结束       │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  结构化满足 SessionStore / OffloadStore / MemoryExtractor
┌───────────────▼──────────────────────────────────────────────────────────┐
│ omicsclaw/memory/   （叶子层：只 import schema 与 context）                 │
│                                                                          │
│  Database ── 一个连接 + threading.Lock + WAL + busy timeout 15 s          │
│    ├── SqliteSessionStore   load / save / list / delete                  │
│    ├── LongTermStore        add / get / update / search / list / touch    │
│    │                        soft_delete / stale_candidates / purge_expired│
│    ├── Precis               regenerate / read  ──► MEMORY.md             │
│    └── MemoryExtractor      extract(messages) ──► ExtractionResult        │
│  FileOffloadStore           压缩卸载的工具结果（文件）                       │
│  JsonlCompactionLog         每次压缩一条 JSONL 记录                          │
└───────────────┬──────────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────────┐
│ <workspace>/.omicsclaw/                                                   │
│   memory.db (+ -wal / -shm)   sessions / messages / long_term_memories /  │
│                               memories_fts                               │
│   MEMORY.md                   Precis 物化视图                              │
│   tool_results/<session>/     compaction_records/<session>.jsonl          │
└──────────────────────────────────────────────────────────────────────────┘
```

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| `Database` | `omicsclaw/memory/database.py` | 单连接、线程锁、建表（`SCHEMA`）、`run` / `arun` 事务 |
| `StoredSession` | `omicsclaw/memory/record.py` | 与 `entry.Session` 字段一一对应的存储记录 |
| `SqliteSessionStore` | `omicsclaw/memory/sessions.py` | 结构化满足 `entry.SessionStore` |
| `MemoryEntry` / `Category` / `signature` | `omicsclaw/memory/longterm.py` | 条目、分类、去重指纹、TTL 判定 |
| `LongTermStore` | `omicsclaw/memory/store.py` | 去重写入、FTS5 检索、强化、软删除、过期清理、陈旧候选 |
| `Precis` | `omicsclaw/memory/precis.py` | `MEMORY.md` 渲染与读取，UTF-8 安全截断 |
| `MemoryExtractor` | `omicsclaw/memory/extractor.py` | 压缩前让模型提取持久事实，fail-open |
| `FileOffloadStore` / `JsonlCompactionLog` | `omicsclaw/memory/offload.py`、`compaction_log.py` | 压缩留下的两类文件 |
| `open_memory` / `MemoryBinding` | `omicsclaw/entry/memory.py` | 打开 `memory.db`，构造 store 与 precis |
| `memory_section` | `omicsclaw/entry/memory.py` | system prompt 的长期记忆段 |
| `memory_tools` | `omicsclaw/entry/memory.py` | `memory_search` + `memory_write` |
| `build_memory_extractor` / `PrecisRefreshingExtractor` | `omicsclaw/entry/memory.py` | 派生提取器，存入后重建精华，记日志 |
| `session_store` | `omicsclaw/entry/memory.py` | 在同一个 `Database` 上构造 `SqliteSessionStore` |
| `prepare_memory` | `omicsclaw/entry/memory.py` | 启动维护：清过期 + 重建精华 |
| `Session` / `SessionStore` / `SessionRegistry` / `attach_sessions` | `omicsclaw/entry/session.py` | 会话对象、存储协议、按会话串行的队列与持久化时机 |

**依赖方向**：`schema ← context ← memory ← entry`。`omicsclaw/memory/` 绝不 import `omicsclaw.entry`——`SessionStore` 是 Protocol，`StoredSession` 与 `entry.Session` 字段一致，所以 store 直接传给 `attach_sessions(app, store=...)` 无需适配器。这条由 `tests/memory/test_memory_is_a_leaf_layer.py` 钉住。提取器复用 `omicsclaw.context.Summarizer` Protocol，因此本层也不 import `omicsclaw.provider`。

### 2.1 关于 `entry/memory.py` 的接线状态

`docs/FRAMEWORK-REBUILD.md` 开头的警告提到，step 6.9 评估期间工作区里有一个"未跟踪、半接线"的 `omicsclaw/entry/memory.py`，与 `entry/compaction.py` 有真实的循环 import。那是当时的快照。**当前状态**（以代码为准）：

- 该文件已随 `c23ec181` 提交进仓库，接线工作由 plan 0040 完成；
- `entry/compaction.py` 顶层 `from .memory import build_memory_extractor`，而 `entry/memory.py` 只 import `omicsclaw.context`、`omicsclaw.memory`、`omicsclaw.tools` 与 `.config`，不再反向 import `compaction`；
- 六个接入点（开库、提取器、prompt 段、两个工具、会话存储、启动维护）全部在 `build_app` / `open_app` / `build_compactor` / `attach_sessions` 中真实调用，`tests/entry/test_memory_wiring.py` 覆盖每一个；
- `tests/memory tests/planning tests/entry/test_memory_wiring.py tests/entry/test_planning.py` 本地运行结果为 381 passed, 5 skipped。

---

## 3. 包结构

```
omicsclaw/memory/
├── __init__.py        # 导出面 + 用法示例
├── database.py        # SCHEMA、BUSY_TIMEOUT_S、Database（run / arun / close）
├── record.py          # StoredSession
├── sessions.py        # SqliteSessionStore（load / save / list / delete）
├── longterm.py        # Category、normalize、signature、MemoryEntry（expired）
├── store.py           # LongTermStore、STALE_AFTER_DAYS、STALE_MAX_IMPORTANCE
├── precis.py          # PRECIS_MAX_BYTES、PRECIS_MAX_ENTRIES、truncate_utf8、render、Precis
├── extractor.py       # EXTRACTION_SYSTEM_PROMPT、ExtractionResult、render_conversation、parse_facts、MemoryExtractor
├── offload.py         # safe_name、FileOffloadStore
└── compaction_log.py  # LoggedCompaction、record_from_dict、JsonlCompactionLog

omicsclaw/entry/
├── memory.py          # open_memory、prepare_memory、memory_section、memory_tools、
│                      # build_memory_extractor、PrecisRefreshingExtractor、session_store
├── session.py         # Session、SessionStore、InMemorySessionStore、SessionRegistry、attach_sessions
└── compaction.py      # build_compactor（派生提取器）、offload_store、compaction_log

tests/memory/          # 叶子层单元测试 + 分层守卫
tests/entry/test_memory_wiring.py   # 接线测试
tests/entry/test_session.py         # 会话注册表
```

---

## 4. 存储布局与 Schema

### 4.1 文件布局

所有文件都在 `AppConfig.state_dir()` = `<workspace>/.omicsclaw/` 之下（`STATE_DIRNAME = ".omicsclaw"`）：

| 路径 | 内容 | 写入者 |
|------|------|-------|
| `memory.db`（`MEMORY_DB_FILENAME`） | 会话 + 长期记忆，WAL 模式 | `Database` |
| `MEMORY.md`（`PRECIS_FILENAME`） | 精华视图 | `Precis.regenerate` |
| `tool_results/<session>/<key>.txt` | 压缩卸载的工具结果 | `FileOffloadStore` |
| `compaction_records/<session>.jsonl` | 压缩记录 | `JsonlCompactionLog` |
| `plans/<session>.json` / `.md` | 执行计划（见 `planning.md`） | `FilePlanArchive` |

`MEMORY.md` 没有放在 workspace 根：那样它会出现在用户项目树里，而且 agent 自己的 `read_file` / `edit_file` 可以直接改它，绕过 `memory_write` 的去重与重要度。

### 4.2 SQL Schema（`omicsclaw/memory/database.py: SCHEMA`）

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',   -- CompactionState.summary
    anchors     TEXT NOT NULL DEFAULT '',   -- CompactionState.anchors 的 JSON，全空时为 ''
    values_json TEXT NOT NULL DEFAULT ''    -- Session.values 的 JSON
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    position    INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    reasoning   TEXT NOT NULL DEFAULT '',
    tool_calls  TEXT NOT NULL DEFAULT '',   -- [{id, name, arguments}] 的 JSON
    tool_call_id TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL DEFAULT '',
    is_error    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, position);

CREATE TABLE IF NOT EXISTS long_term_memories (
    id           TEXT PRIMARY KEY,           -- uuid4().hex，由 store 生成
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT '',   -- knowledge | preference | task | skill | ''
    importance   INTEGER NOT NULL DEFAULT 0, -- 0-10
    signature    TEXT UNIQUE,                -- sha256(normalize(content))；软删除置 NULL
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    last_used_at REAL,
    use_count    INTEGER NOT NULL DEFAULT 0,
    ttl_days     INTEGER,                    -- NULL 或 <=0 = 永不过期
    disabled     INTEGER NOT NULL DEFAULT 0, -- 软删除标志
    tags         TEXT NOT NULL DEFAULT ''    -- JSON 数组或 ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
    USING fts5(id UNINDEXED, title, content);
```

要点：

- 时间戳是 `REAL`（epoch 秒，`time.time()`），不是整数。
- `messages` 里**不存 system 消息**：`SqliteSessionStore.save` 过滤 `Role.SYSTEM`，因为 prompt 组装每轮都会加一条新的，存下来会在当前 persona 旁边叠一条陈旧的。
- `sessions` 表**没有 owner / scope 列**。`SqliteSessionStore.list` 的 docstring 明说："范围就是数据库文件本身，本方法不做任何隔离"。
- `memories_fts` 是 **standalone** FTS5 表（不是 external-content），由 `LongTermStore` 每个写方法手动同步（`_reindex` / `DELETE FROM memories_fts`），不依赖触发器。
- 没有 schema 版本号，也没有迁移逻辑——每次打开都是 `CREATE ... IF NOT EXISTS`。

### 4.3 Python 数据结构

```python
# omicsclaw/memory/record.py —— 与 entry.Session 字段一致
@dataclass(slots=True)
class StoredSession:
    session_id: str
    history: tuple[Message, ...] = ()
    compaction: CompactionState = field(default_factory=CompactionState)
    created_at: float = field(default_factory=time.time)
    values: Mapping[str, object] = ...
    updated_at: float = field(default_factory=time.time)

# omicsclaw/memory/longterm.py
class Category(StrEnum):
    KNOWLEDGE = "knowledge"; PREFERENCE = "preference"; TASK = "task"; SKILL = "skill"

@dataclass(slots=True)
class MemoryEntry:
    id: str = ""; title: str = ""; content: str = ""
    category: Category | str = ""
    importance: int = 0
    created_at: float; updated_at: float
    last_used_at: float | None = None
    use_count: int = 0
    ttl_days: int = 0          # <=0 永不过期
    disabled: bool = False
    tags: tuple[str, ...] = ()
    # signature 属性、expired(now) 方法
```

`MemoryEntry.expired()` 从 `updated_at` 起算：重写一条记忆会推迟它的过期，读它不会——"去翻一条记忆不能证明它仍然成立"。

### 4.4 并发模型（`Database`）

- **一个连接**：`sqlite3.connect(path, check_same_thread=False, timeout=BUSY_TIMEOUT_S)`，`BUSY_TIMEOUT_S = 15.0`。
- **一把 `threading.Lock`** 串行化所有语句。不用"每线程一连接"，因为那样 `":memory:"` 会变成每线程一个空库。
- **async 签名 + 同步 SQLite**：所有 store 方法都是 `async`，内部 `Database.arun` → `asyncio.to_thread(self.run, work)`。`run` 成功即 `commit`，任何异常先 `rollback` 再抛。
- **PRAGMA**：`foreign_keys = ON`；`journal_mode = WAL`，若同一时刻另一个进程也在打开同一文件而得到 `SQLITE_BUSY`，吞掉这个 `OperationalError`——WAL 是文件属性，谁先到谁转换。
- **跨进程去重是单语句**：`LongTermStore._add` 用 `INSERT ... ON CONFLICT (signature) DO UPDATE ... RETURNING`，查找与写入不会被另一个进程插进来。

---

## 5. 会话持久化

### 5.1 `SqliteSessionStore`

| 方法 | 语义 |
|------|------|
| `load(session_id)` | 读 `sessions` 行 + 按 `position` 排序的 `messages`，重建 `StoredSession`；不存在返回 `None` |
| `save(session)` | UPSERT `sessions` 行；**删除该会话全部 `messages` 后整段重写**（过滤 system 消息）；`values` 无法 JSON 编码时抛 `TypeError`，事务回滚，什么都不写 |
| `list(limit=50)` | 按 `updated_at DESC, created_at DESC` 返回会话（每个会话再 `_load` 一次） |
| `delete(session_id)` | 删除消息与会话行；返回是否删除了会话 |

`values` 以 JSON 存储，只有 JSON 能表示的值会原样回来——tuple 回来是 list，非字符串 key 回来是字符串。

### 5.2 何时读、何时写（`SessionRegistry`）

```
submit(session_id, text) ──► 立即返回 TurnHandle（不 await 任何东西）
        │
        ▼  lane pump（每个 session 一条，串行）
_attempt(handle)
  ├─ _session(id)：内存里有就用；没有就 store.load(id)；再没有就新建 Session
  ├─ TurnRunner(history=session.history, compaction=session.compaction, ...)
  ├─ 在独立 Task 里跑 exchange，asyncio.wait 等它结束
  ├─ terminal == "converged" 时：session.history / session.compaction 整体替换
  │   （cancelled / failed 的 exchange 保持历史字节不变）
  ├─ session.updated_at = time.time()
  └─ await store.save(session)      ◄── 每个 exchange 结束都保存，包括失败的
```

- **持久化在 pump 里做，不在 exchange 的 Task 里做**：取消一个 Task 会在它下一个 `await` 注入 `CancelledError`，`finally: await store.save(...)` 不一定能完成；pump 是"请求取消的一方"，先收割 Task 再保存。
- `save` 抛异常时，流上已经发出 `converged` 帧，但 `TurnHandle.terminal` 记为 `failed`——"历史没进存储的 exchange 不算完成"。
- 内存中最多保留 `max_sessions`（默认 256）个会话，按 LRU 淘汰**空闲**会话；有 exchange 在跑或排队的会话永不淘汰。被淘汰的会话下次 `_session()` 会从 store 重新加载。
- `/compact`（`SessionRegistry.compact`）也走同一条 lane，以 `compaction_only=True` 的 FULL 压缩运行，结果同样保存。

### 5.3 `attach_sessions` 的默认存储

```python
app = attach_sessions(await open_app(resolve_app_config(argv, env)))
```

`store=None` 的含义是"这个 app 自己的库"，不是"内存"：

| 情况 | 使用的 store |
|------|-------------|
| `AppConfig.memory=True`（默认），`build_app` 打开了库 | `SqliteSessionStore(app.memory.database)`——与长期记忆**同一个连接** |
| `memory=False` 或手工构造的 app（`app.memory is None`） | `InMemorySessionStore`，进程退出即丢 |
| 调用方显式传 `store=` | 永远以调用方为准 |

`SessionRegistry.persistent` 通过 store 类型判断会话能否跨进程存活（`not isinstance(store, InMemorySessionStore)`）。三个 surface（`launch/_surfaces.py` 的 `_run_cli`、`_serve_desktop`、`_serve_channels`）都用 `attach_sessions(await open_app(config))` 这一短写法，因此默认全部持久化。

### 5.4 各 surface 的会话标识与命令

| Surface | session_id 来源 |
|---------|----------------|
| CLI REPL | `--session <id>`；缺省为 `new_turn_id()[:8]`（8 位 hex） |
| Channel | `ChannelAdapter.session_id(chat_id)` = `"<platform>:<chat_id>"`，按聊天而非按人 |
| Desktop | 请求体里的 `session_id`；缺省时为 `uuid.uuid4().hex`（`entry/desktop/turn_submission.py`） |

CLI 的会话命令（`omicsclaw/entry/cli/_repl.py`）：

| 命令 / 参数 | 行为 |
|------------|------|
| `oc cli --session <id>` | 以该 id 进入 REPL；registry 首次取用时从 `memory.db` 加载历史。与 `--prompt` / `--prompt-file` 互斥（单次问答没有可续的会话） |
| `/sessions` | `list_sessions(SESSION_LIST_LIMIT=10)`，按最近活跃排序；说明本工作区是否保存会话；当前会话尚未保存时单独提示 |
| `/resume` | 无参数：`prompt_toolkit` 可用时弹出方向键选择器，否则列出并提示 `/resume <id>` 或 `/resume <number>` |
| `/resume <id\|number>` | 先按 id 查（`load_session`，只读不收养），查不到再按 `/sessions` 的序号查；切换后打印最近几条对话摘要 |
| `/new`、`/clear` | 换一个从未用过的 session id；原会话仍在库里可 `/resume` |
| `/compact` | 立即对当前会话做 FULL 压缩；会话有 exchange 在跑时拒绝 |

没有 `/memory` 命令：它在移植的命令目录里（`_constants.py`），但不在 `REPL_SLASH_COMMAND_SPECS` 中，输入会得到"not available in this build"。

---

## 6. 长期记忆 Store（`LongTermStore`）

| 方法 | 语义 |
|------|------|
| `add(entry) -> str` | 写入；忽略 `entry.id`，总是生成新 id。同指纹时**不报错**：保留原 id，`importance` 取两者较大值，刷新 `updated_at`，并置 `disabled=0`。返回存储/合并后的 id |
| `get(id)` | 按 id 取（含已禁用条目，便于审计）；无则 `None` |
| `update(id, **changes)` | 只允许 `title`/`content`/`category`/`importance`/`ttl_days`/`tags`，其他字段抛 `ValueError`；重算指纹；若新内容与**另一条**记忆指纹相同，吸收那一条（删除它，取较大 importance）而不是撞 UNIQUE；重建 FTS |
| `search(query, limit=10)` | FTS5 检索未禁用、未过期条目，按 `rank` 排序。**这是写操作**：命中条目 `use_count+1`、`last_used_at=now`，`updated_at` 不动 |
| `list(limit=30)` | 未禁用、未过期条目，按 `importance DESC, updated_at DESC` |
| `touch(id)` | 单条 `use_count+1`、`last_used_at=now` |
| `soft_delete(id)` | `disabled=1`、`signature=NULL`（释放 UNIQUE 槽位）、`updated_at=now`，移出 FTS；行保留供审计 |
| `stale_candidates(now=, max_importance=1, after_days=60.0)` | 同时满足 `importance <= 1`、`use_count = 0`、`updated_at` 早于 60 天前的未禁用条目，最旧优先。只回答问题，不删除 |
| `purge_expired(now=)` | **物理删除** TTL 已过（`updated_at + ttl_days*86400 < now`）的条目及其 FTS 行，返回删除数 |

**查询转义**（`_escape_fts`）：把每个空白分隔的词包成双引号字面量，用 `OR` 连接（而非 FTS5 默认的隐式 AND），NUL 替换为空格。理由：查询常是整句，AND 语义下任一词缺失都会零命中；排序交给 FTS5 的 rank。

---

## 7. MEMORY.md 物化视图（`Precis`）

`long_term_memories` 是唯一事实源；`MEMORY.md` 是从 `LongTermStore.list(max_entries)` 渲染出来的有界文件。

```python
PRECIS_MAX_ENTRIES = 30
PRECIS_MAX_BYTES = 5120
TRUNCATION_MARKER = "\n…(truncated)"

class Precis:
    def __init__(self, store, path, max_bytes=PRECIS_MAX_BYTES, max_entries=PRECIS_MAX_ENTRIES)
    async def regenerate(self) -> str   # list → render → mkdir → write_text
    def read(self) -> str               # 文件不存在返回 ""
```

渲染格式（`render`）：每条 `## {title} \`{category}\``（无 category 时省略反引号部分）+ 换行 + 正文，条目间空一行；整体超过 `max_bytes` 时 `truncate_utf8` 在字符边界截断并追加 `TRUNCATION_MARKER`。`max_bytes <= 0` 时回退为默认值。

`regenerate` 的调用时机：

1. 启动维护 `prepare_memory`（`purge_expired` 之后）；
2. `memory_write` 的 add / update / remove 任一成功后（`_written`）；
3. 压缩前提取**实际存入了条目**之后（`PrecisRefreshingExtractor`）。

三处都是 fail-soft：写不了 `MEMORY.md` 只记警告，不让工具调用或压缩失败——`memory_write` 在这种情况下返回的 JSON 带 `"precis": "not rewritten"`。

---

## 8. 写入途径

### 8.1 `memory_write`（显式工具）

参数 schema `MEMORY_WRITE_SCHEMA`，`required: ["action"]`，`additionalProperties: False`：

| `action` | 必需 | 行为 |
|----------|------|------|
| `add` | `content` | `title` 缺省取正文前 60 字符；`category` 必须属于四个枚举值；`importance` 钳到 0-10；`ttl_days` 负数归 0（永不过期）。同内容命中去重 |
| `update` | `id` + 至少一个字段 | 只改模型实际给出的字段；`importance` / `ttl_days` 用 `None` 区分"没说"与"说了 0"。id 不存在 → `ToolArgumentError` |
| `remove` | `id` | 软删除；id 不存在 → `ToolArgumentError` |

返回 JSON，如 `{"action": "add", "id": "..."}`，update 额外带 `"changed": [...]`。

### 8.2 `memory_search`（按需检索）

参数 `query`（必填）、`limit`（默认 `DEFAULT_SEARCH_LIMIT = 5`，钳到 `1..MAX_SEARCH_LIMIT = 20`）。返回 JSON 数组，每条 `{id, title, content, category, importance}`——带 id 是因为 update / remove 需要它。

答案上界 `SEARCH_RESULT_MAX_BYTES = 4096`（`_fit`）：

1. 超界时从末尾整条丢弃（排名靠后的先走），保证返回的永远是合法 JSON；
2. **最佳命中永不丢弃**：只剩一条仍超界时，标题与正文同步折半直到装得下，并标 `"content_truncated": true`。丢掉它会让模型读到 `[]`——"从没告诉过你"——而这条记忆的 `use_count` 已经被加过了。

### 8.3 两个工具的 `ToolPolicy`

| 字段 | `memory_write` | `memory_search` | 理由 |
|------|---------------|----------------|------|
| `risk_level` / `approval_mode` | `LOW` / `AUTO` | `LOW` / `AUTO` | 爆炸半径是 agent 自己在 `.omicsclaw/` 下的笔记；默认 `HIGH`/`ASK` 会让每条记忆都弹审批 |
| `read_only` | `False` | **`False`** | search 会改 `use_count` / `last_used_at`，声称只读就是声称一个不存在的无副作用 |
| `concurrency_safe` | `False` | `True` | 两个 write 同轮并发会各自从对方正在改的 store 重建精华；search 的写只是库内计数器，由锁串行 |
| `tags` | `{"memory"}` | `{"memory", "inspection"}` | |

两个工具挂在 `foundation_tools` 末尾（`plan_write` 之后），追加而非插入，保持缓存前缀里既有工具的字节顺序不变。

### 8.4 压缩前提取（`MemoryExtractor`）

```
ProgressiveCompactor（每次模型调用前）
  └─ compact()：档位为 SOFT 或 FULL 且有 summarizer
       └─ _summarize_and_extract：asyncio.gather(
              summarizer.summarize(...),                 # 写摘要
              extractor.extract(head_before_offload))    # 同时提取
```

- **触发时机**：只在需要写摘要的档位（`SOFT` / `FULL`，包括 `/compact`）且有 summarizer 时运行；`WARN`（只卸载）与 `EMERGENCY`（不调模型的截断）不提取。输入是即将被摘要替换的 head，取**卸载之前**的原始消息。
- **派生而非持有**：`build_compactor` 每次调用都执行 `app.memory_extractor or build_memory_extractor(app.memory, app.summarizer)`。在 `build_app` 里构造一次会捕获 summarizer，而 `dataclasses.replace(app, summarizer=X)` 是本仓库替换摘要模型的标准写法，捕获会让提取继续打旧模型。`AgentApp.memory_extractor` 非 `None` 时作为覆盖优先。
- **提取流程**（`MemoryExtractor.extract`）：
  1. `render_conversation`：每条非 system、内容非空的消息渲染成 `role: content` 一行（工具结果消息也在内）；为空则直接返回空结果；
  2. 以 `EXTRACTION_SYSTEM_PROMPT` 调 `summarizer.summarize(transcript, system=...)`——提示要求只保留会话结束后仍然成立的东西（偏好、项目/数据的稳定事实、已定决策、可复用流程），排除单次运行的路径、中间结果、下一步打算；要求用会话所用的语言写 title 和 content；
  3. `parse_facts`：容忍 ```` ```json ```` 围栏，必须是 JSON 数组；
  4. 逐条 `_to_entry`：空 content 丢弃（计入 `rejected`），未知 category 归空，importance 钳到 0-10，非整数归 0；
  5. 逐条 `store.add`（去重）。
- **fail-open 且不打日志**：模型异常、非 JSON、store 失败都不抛，原因写在 `ExtractionResult.failure`。日志由 entry 层的 `PrecisRefreshingExtractor` 负责——只记条数，不记内容。即便提取器意外抛出，`compaction.py` 也只把它记进 `CompactionRecord.advisories`，不影响压缩本身。

### 8.5 没有 Turn 粒度的 nudge

**OmicsClaw 没有按轮次提醒模型调用 `memory_write` 的机制**（plan 0040 §10-4）。后果：除了模型主动调用 `memory_write`，"记"完全依赖压缩前提取，而一个从未触发 SOFT/FULL 压缩的短会话不会自动记下任何东西。

---

## 9. Context 注入

### 9.1 System Prompt 段

`default_sections` 的顺序：

```
persona → project contract → Safety rules → Tool guidance → [Planning]
→ [Execution sandbox] → [skills] → environment → [Long-term memory]
```

长期记忆段放在**最后**：它是 prompt 中最易变的块（`memory_write` 会在会话中改写它），放最后使一次改写对缓存前缀的失效最小。

```python
MEMORY_SECTION_KEY = "memory"
MEMORY_SECTION_HEADING = "## Long-term memory"

def memory_section(binding):
    precis = binding.precis
    def read() -> str:
        return precis.read()
    return Section(MEMORY_SECTION_KEY, MEMORY_SECTION_HEADING, read)
```

- **source 是闭包**：每次 `PromptAssembler.render()` 都重读 `MEMORY.md`。
- **空即不出现**：`MEMORY.md` 为空或不存在时整段（含标题）不渲染。
- **只有内容，没有工具用法指引**：`memory_search` / `memory_write` 的用法写在两个工具各自的 description 里（`TOOL_GUIDANCE` 的规则是工具用法归工具描述），因此该段不承诺任何工具存在。
- **可见时机**：engine 在每个 exchange 开始时渲染一次 system prompt（`AgentEngine.exchange` / `exchange_stream`），所以本 exchange 内 `memory_write` 写入的内容，从**下一个 exchange** 起出现在 system prompt 中；本 exchange 内模型已经从工具返回值里看到了自己写的东西。

### 9.2 按需检索

`memory_search` 把长尾记忆以工具 Observation 的形式带进当前 turn，不占固定 prompt 预算。

---

## 10. 冲突 / 遗忘 / 强化

| 机制 | 实现 |
|------|------|
| **内容去重** | `signature = sha256(normalize(content))`，`normalize` = 小写 + 折叠空白 + 去首尾；`add` 命中时合并（importance 取大、刷新 `updated_at`、复活 `disabled`） |
| **编辑撞重** | `update` 到另一条已有内容时吸收那一条，被编辑的 id 存活 |
| **TTL 过期** | `ttl_days > 0` 时从 `updated_at` 起算；`list` / `search` 读时过滤；`purge_expired` 在启动时**物理删除** |
| **软删除** | `memory_write action=remove` → `soft_delete`：`disabled=1`、`signature=NULL`，行保留；同内容以后可重新写成新条目 |
| **强化** | `search` 命中即 `use_count+1`、`last_used_at=now`；不推迟过期 |
| **陈旧识别** | `stale_candidates`：`importance<=1 AND use_count=0 AND updated_at < now-60 天`；**当前没有调用者** |
| **矛盾冲突** | 系统不做自动仲裁；由模型通过 `memory_write update / remove` 处理 |
| **注入预算** | `MEMORY.md` 最多 30 条、5120 字节，按 importance 排序；超出部分只能通过 `memory_search` 取到 |

---

## 11. 压缩留下的文件

这两个类在 `omicsclaw/memory/` 里，但服务于压缩（详见上下文压缩文档），此处只列存储形态：

| 类 | 路径 | 语义 |
|----|------|------|
| `FileOffloadStore` | `<workspace>/.omicsclaw/tool_results/<safe_name(session)>/<key>.txt` | 满足 `context.OffloadStore`；key 已存在不重写；临时文件 + `os.replace` 原子写；目录 `0700`、文件 `0600`；引用相对 workspace，模型可用 `read_file` 读回。例如一次返回巨量 `adata.obs` 摘要的 `bash` 结果被卸载后，对话里只剩占位符与这个路径 |
| `JsonlCompactionLog` | `<workspace>/.omicsclaw/compaction_records/<safe_name(session)>.jsonl` | 只追加；每行 `{id, session_id, timestamp, ...CompactionRecord}`；读不回的行跳过 |

`safe_name` 会把非 `[A-Za-z0-9_.-]` 字符替换为 `_` 并在改动过时追加原文的 8 位 sha1 摘要，因此 `telegram:42` 这类 channel 会话 id 不会与另一个 id 撞名。两者都有 `purge` 方法，但当前没有会话删除入口调用它们。

---

## 12. 启动与关闭序列

```python
# 1. build_app（同步）：打开 memory.db，构造 store 与 precis
remembering = open_memory(config)          # config.memory=False → None
mounted = foundation_tools(config, ..., plans=plans, memory=remembering)
sections = default_sections(config, ..., memory=remembering)
# AgentApp(memory=remembering, ...)；build_app 中途抛异常则关闭连接后重抛

# 2. open_app（async）：_swept(app) → prepare_memory(app.memory)
purged = await binding.store.purge_expired()
await binding.precis.regenerate()          # 失败只记 warning，进程照常启动

# 3. attach_sessions(app)：store 默认 = SqliteSessionStore(app.memory.database)

# 4. 每个 exchange：build_compactor 派生提取器；registry 结束时 save(session)

# 5. AgentApp.aclose()：sessions.shutdown → MCP → sandbox → memory.close() → telemetry
```

关闭顺序中记忆库在 sessions 排空之后关闭，保证宽限期内仍在跑的工具调用拿到的是可写的库。

---

## 13. 配置参数

| 配置 | 命令行 / 环境变量 | 默认 | 说明 |
|------|------------------|------|------|
| `AppConfig.memory` | `--memory` / `OMICSCLAW_MEMORY` | `True` | 一个开关同时控制 `memory.db`、两个工具、prompt 段、提取器、SQLite 会话存储。`false` 时会话只在进程内存中。与容器内存上限 `sandbox_memory`（`--sandbox-memory`）无关 |
| `AppConfig.workspace` | `--workspace` | — | 决定 `state_dir()` = `<workspace>/.omicsclaw` |
| `AppConfig.max_sessions` | `--max-sessions` / `OMICSCLAW_MAX_SESSIONS` | `256` | 内存中保留的会话数（空闲 LRU 淘汰） |
| `AppConfig.compact_at` | `--compact-at` / `OMICSCLAW_COMPACT_AT` | `WARN` | 压缩起始档位；只有 SOFT / FULL 会触发提取 |
| `BUSY_TIMEOUT_S` | 常量 | `15.0` | SQLite busy timeout |
| `PRECIS_MAX_BYTES` / `PRECIS_MAX_ENTRIES` | 常量 | `5120` / `30` | 精华上限 |
| `DEFAULT_SEARCH_LIMIT` / `MAX_SEARCH_LIMIT` | 常量 | `5` / `20` | `memory_search` 条数 |
| `SEARCH_RESULT_MAX_BYTES` | 常量 | `4096` | `memory_search` 答案字节上界 |
| `STALE_AFTER_DAYS` / `STALE_MAX_IMPORTANCE` | 常量 | `60.0` / `1` | 陈旧候选阈值 |
| `SESSION_LIST_LIMIT` | 常量（CLI） | `10` | `/sessions`、`/resume` 列表长度 |

布尔值接受 `1/true/yes/on` 与 `0/false/no/off`，例如 `oc cli --memory false`。

---

## 14. 端到端示例

一个空间转录组用户的两次会话：

```
会话 A（oc cli --session visium-01）
  用户：以后这个项目的空间域识别都用 leiden，报告用中文。
  模型：memory_write {action: add, content: "...空间域识别一律用 leiden...", category: preference, importance: 8}
        → store.add → Precis.regenerate → MEMORY.md 有了这一条
  ……后续跑 spatial-preprocess、spatial-domains，多次 bash 输出很长，
     某次模型调用前达到 SOFT：
        summarizer 写摘要 ‖ extractor 从被摘要的 head 中提取
        "样本来自小鼠脑 Visium，已做过 QC，阈值 min_genes=200" 之类事实 → store.add
        → PrecisRefreshingExtractor 重建 MEMORY.md
  exchange 结束 → SessionRegistry save：messages + summary/anchors 写入 memory.db

进程退出，第二天重启 oc cli
  open_app → prepare_memory：清过期条目、重建 MEMORY.md
  新会话 B：system prompt 末尾出现 "## Long-term memory" 段，含上面的偏好
  用户：/resume → 选择 visium-01 → 历史与压缩摘要从 memory.db 读回，继续 spatial-de
```

注意示例中"min_genes=200"这类数值是否被提取取决于模型对 `EXTRACTION_SYSTEM_PROMPT` 的理解；提示明确要求排除"一次运行的中间结果"，提取质量没有经过真实模型的量化评估（见已知限制）。

---

## 15. 关键设计决策

| 决策 | 原因 |
|------|------|
| **会话与 LTM 共用一个 `memory.db`、一个连接** | 一个部署一个文件；同一文件两个连接只是多一份锁竞争 |
| **`memory` 是叶子层，`SessionStore` 是 Protocol** | 底层 import 顶层才是真正的错误；`StoredSession` 与 `entry.Session` 同形是依赖方向的必然结果 |
| **async 签名 + `asyncio.to_thread`** | `SessionStore` 裁定为 async；标准库 `sqlite3` 是同步的且 `aiosqlite` 不可用 |
| **单连接 + `threading.Lock`** | 每线程一连接会让 `:memory:` 变成多个空库 |
| **standalone FTS5，手动同步** | 不依赖触发器，写入/删除时机显式可见 |
| **去重用 `ON CONFLICT ... RETURNING` 单语句** | SELECT-then-INSERT 在多进程下是 TOCTOU（plan 0033 §9 B1） |
| **FTS 查询用 OR 连接** | 整句查询在 AND 语义下几乎总是零命中 |
| **`search` 是写操作** | 否则没有任何路径增加 `use_count`，`stale_candidates` 会退化成"列出全部低分条目" |
| **提取器在 `build_compactor` 中派生** | 避免捕获过期的 summarizer（plan 0040 §4-1） |
| **提取器不打日志，返回 `ExtractionResult`** | entry 是第一个允许打日志的层；只记条数不记内容 |
| **记忆段是闭包、放最后、不写工具用法** | 读到最新精华；最小化缓存前缀失效；不承诺可能未挂载的工具 |
| **`attach_sessions(store=None)` 默认持久化** | surface 忘传 store 的后果是对话悄悄消失，而这类缺陷没人会报 |
| **一个 `memory` 开关控制五件事** | 半套（有段没人写、有提取器没人读）比完全没有更糟 |

---

## 16. 已知限制

1. **中文检索基本不可用于子串。** FTS5 默认分词器把一串连续汉字当成一个 token：对"这个项目的空间域识别一律用 leiden"这条记忆，搜"域识别"或"这个项目"都是 0 命中，只有整段原文或被标点/空格切开的片段能中。而 `EXTRACTION_SYSTEM_PROMPT` 要求用对话语言写记忆，中文用户的默认路径就会产出自己搜不到的记忆。`tokenize='trigram'` 可解，但要改建表语句并迁移既有库（plan 0033 §9 B9、plan 0040 §10-3；`tests/memory/test_store.py::test_chinese_matches_only_a_whole_unbroken_run` 标记了现状）。
2. **没有 Turn 粒度的记忆 nudge。** 不触发 SOFT/FULL 压缩的短会话，除非模型主动调用 `memory_write`，否则什么也不会被记下（plan 0040 §10-4）。
3. **文件权限。** `memory.db`、`memory.db-wal`、`memory.db-shm` 与 `MEMORY.md` 按进程 umask 创建（通常 0644 / 目录 0755），多用户机器上同机可读。offload 与 compaction log 已是 0700 / 0600（plan 0033 §9 B7、plan 0040 §10-2）。
4. **精华标题与 prompt 章节同级。** `render` 用 `## ` 作条目标题，内容由模型写入并原样注入；一条被注入的记忆可以渲染成 `## Safety rules` 之类的伪章节，并因记忆段位于最后而排在真正的安全规则之后（plan 0040 §10-5）。
5. **`MEMORY.md` 写入不是原子的。** `Precis.regenerate` 用 `Path.write_text`（先截断再写），并发读者可能读到撕裂的文件，也就是撕裂的 system prompt。多进程写同一 `memory.db` 本身已实测可行（3 进程 × 60 次 add 全部落库），问题只在 `MEMORY.md`（plan 0040 §10-9）。
6. **`stale_candidates` 与 `touch` 没有调用者。** 陈旧识别只是一个可查询的能力，没有任何自动清理；`touch` 被 `search` 内联的计数更新取代。
7. **没有会话删除入口。** `SqliteSessionStore.delete`、`FileOffloadStore.purge`、`JsonlCompactionLog.purge` 都存在，但没有命令或 API 调用它们；会话、卸载文件与压缩日志只增不减。
8. **`list()` 没有隔离。** `sessions` 表无 owner 列，`/sessions` 列出该文件中的全部会话。多人共用一个 workspace（例如一个 Channel 进程服务多个群）时，隔离完全取决于谁能访问 CLI 列表；Channel 本身不暴露 `/sessions`。
9. **`save` 整段重写消息。** 每次 exchange 结束都 `DELETE` 该会话全部消息再插入，长会话的保存成本随历史线性增长；`list()` 对每个会话再 `_load` 一次（N+1）。
10. **没有 schema 版本与迁移。** 任何建表语句变更（包括上面的 trigram 修复）都需要自己处理既有库。
11. **`Database` 用 `Lock` 而非 `RLock`。** `run()` 内部若重入会永久死锁；当前没有重入路径，但 `run` 是公开 API（plan 0033 §9 B8）。
12. **提取质量未经评估。** 没有真实模型上的数据说明一次压缩提取出几条、有多少是噪声（plan 0040 §10-7）。
13. **子代理只读长期记忆。** `task` 派生的子代理继承父代理除 `task`、`plan_write`、`memory_write` 外的全部工具（`entry/subagent.py` 的 `_WITHHELD_FROM_SUB_AGENTS`），因此能 `memory_search`、不能 `memory_write`：写入的条目会进入以后每个会话的系统提示，读到恶意文件的子代理不能借此种下永久注入。子代理自己没有压缩器，也就没有提取。

---

## 17. 文件索引

| 文件 | 内容 |
|------|------|
| `omicsclaw/memory/__init__.py` | 导出面与用法示例 |
| `omicsclaw/memory/database.py` | `SCHEMA`、`BUSY_TIMEOUT_S`、`Database` |
| `omicsclaw/memory/record.py` | `StoredSession` |
| `omicsclaw/memory/sessions.py` | `SqliteSessionStore` |
| `omicsclaw/memory/longterm.py` | `Category`、`normalize`、`signature`、`MemoryEntry` |
| `omicsclaw/memory/store.py` | `LongTermStore`、`STALE_AFTER_DAYS`、`STALE_MAX_IMPORTANCE`、`_escape_fts` |
| `omicsclaw/memory/precis.py` | `Precis`、`render`、`truncate_utf8`、`PRECIS_MAX_BYTES`、`PRECIS_MAX_ENTRIES` |
| `omicsclaw/memory/extractor.py` | `MemoryExtractor`、`EXTRACTION_SYSTEM_PROMPT`、`ExtractionResult`、`parse_facts`、`render_conversation` |
| `omicsclaw/memory/offload.py` | `FileOffloadStore`、`safe_name` |
| `omicsclaw/memory/compaction_log.py` | `JsonlCompactionLog`、`LoggedCompaction`、`record_from_dict` |
| `omicsclaw/entry/memory.py` | `open_memory`、`MemoryBinding`、`prepare_memory`、`memory_section`、`memory_tools`、`memory_search_tool`、`memory_write_tool`、`build_memory_extractor`、`PrecisRefreshingExtractor`、`session_store` |
| `omicsclaw/entry/session.py` | `Session`、`SessionStore`、`InMemorySessionStore`、`SessionRegistry`、`attach_sessions` |
| `omicsclaw/entry/compaction.py` | `build_compactor`、`offload_store`、`compaction_log` |
| `omicsclaw/entry/assembly.py` | `foundation_tools`、`default_sections`、`build_app`、`open_app`、`_swept`、`AgentApp.memory` / `memory_extractor` / `aclose` |
| `omicsclaw/entry/config.py` | `AppConfig.memory`、`state_dir()`、`STATE_DIRNAME` |
| `omicsclaw/context/compaction.py` | `MemoryExtractor` Protocol、`_summarize_and_extract` |
| `omicsclaw/entry/cli/_repl.py` | `/sessions`、`/resume`、`/new`、`/compact`、`SESSION_LIST_LIMIT` |
| `omicsclaw/launch/_surfaces.py` | `--session` 解析；三个 surface 的 `attach_sessions(await open_app(config))` |
| `tests/memory/` | 叶子层测试与分层守卫 |
| `tests/entry/test_memory_wiring.py` | 六个接入点的接线测试 |
| `docs/plans/0033-memory-layer.md` | 叶子层计划、评估修复、未修清单 |
| `docs/plans/0040-memory-wiring.md` | 接线计划、遗留问题 |
