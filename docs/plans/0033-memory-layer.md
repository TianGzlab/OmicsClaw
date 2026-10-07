# 0033 —— `omicsclaw/memory/`：会话持久化与长期记忆

重建的第 7 步。对标 harness9 的 `internal/memory` 与 `internal/ltm` 两个包。

状态：已交付（2026-10-07 核对），计划 0040 已把本层接进 agent 主循环。以下是写计划时的情况：上游 `omicsclaw/entry/` 已就绪，本层是纯增量，只新建
`omicsclaw/memory/` 与 `tests/memory/`。

## 1. 为什么现在能做

旧的 `omicsclaw/memory/`（28 模块的图谱记忆系统）已被 owner 删除，名字是空的。
重建文档 step 3 的教训是「名字被占用要先解决」——这次不需要解决，磁盘上没有这个目录，
git 索引里是 32 条 staged deletion。

两个接缝在 step 6 就已经留好，本层落进去不用改 `entry/` 一行：

| 接缝 | 位置 | 本层提供 |
|---|---|---|
| `SessionStore` Protocol | `omicsclaw/entry/session.py:162` | SQLite 实现 |
| `attach_sessions(app, store=)` | `omicsclaw/entry/session.py:677` | 注入点，已有 `store=` 参数 |

`CompactionState` 的 docstring（`omicsclaw/context/compaction.py:152`）写着
「step 6 decides where it lives (a session row, memory, nowhere)」——持久化它
正是预留给本层的职责。

## 2. 目标与非目标

**目标**

1. 会话跨进程存活：重启后 `load(session_id)` 能拿回历史与压缩状态。
2. 长期记忆：跨会话的知识/偏好/任务/技能条目，带去重、重要度、TTL、全文检索。
3. 精华视图：把 top-N 高价值条目渲染成**有界**的 Markdown，供 System Prompt 注入。

**非目标**

- 不做向量检索。FTS5 已经够用，向量库会把一个叶子层变成有外部依赖的层。
- 不改 `entry/`。把精华段挂进 `default_sections()` 是下一步的接线工作，不属于本步。
- 不做图谱关系。旧 memory 的图谱是被删掉的那套，不复活。

## 3. 依赖方向

```
schema ← context ← memory
```

`memory` 只 import `omicsclaw.schema`（`Message`、`Role`、`ToolCall`）和
`omicsclaw.context`（`CompactionState`、`Anchors`）。

**绝不 import `omicsclaw.entry`。** `SessionStore` 是 Protocol，结构化满足即可。
代价是本层要自己定义一个与 `entry.Session` 形状相同的记录类型
（`StoredSession`），这不是重复定义而是依赖方向的必然结果：让底层 import 顶层
才是真正的错误。有具名测试 `test_memory_is_a_leaf_layer.py` 钉住这条。

## 4. 模块划分

| 文件 | 职责 |
|---|---|
| `record.py` | `StoredSession`——`entry.Session` 的结构化孪生 |
| `database.py` | 连接管理、schema 建表、PRAGMA、线程亲和 |
| `sessions.py` | `SqliteSessionStore`，满足 `SessionStore` Protocol |
| `longterm.py` | `MemoryEntry`、`Category`、去重指纹、TTL 判定 |
| `store.py` | `LongTermStore`——写入去重、FTS5 检索、软删除、过期清理 |
| `precis.py` | `Precis`——MEMORY.md 物化视图，按 UTF-8 边界截断 |

## 5. 三个必须做对的技术决定

### 5-1 async 签名 + 同步 SQLite

`SessionStore` 每个方法都是 `async`（`entry/session.py:171` 的裁定：同步签名等于
在没资格做这个决定的地方断言「存储是本地的」）。但标准库 `sqlite3` 是同步的，
`aiosqlite` 这台机器上没有。

裁定：**所有 SQLite 调用走 `asyncio.to_thread`**。不引入第三方依赖，也不在事件
循环里做阻塞 I/O。代价是每次调用一次线程切换，对会话存储这个量级可以忽略。

### 5-2 连接的线程亲和

`sqlite3.Connection` 默认只能在创建它的线程用。而 `to_thread` 每次可能是不同的
工作线程。

裁定：`check_same_thread=False` + 一把 `threading.Lock` 串行化所有访问。
不用「每线程一连接」，因为那样 `:memory:` 数据库会变成每线程各一个空库——
测试里最常用的形态会静默失效。这条必须有测试钉住：**在 `:memory:` 上跨多次
`to_thread` 调用读写，断言读得回来**。

### 5-3 FTS5 是手动同步的 standalone 索引

`memories_fts` 不用 external-content 表。external content 需要触发器维护，
而触发器在 `content=` 表被 UPDATE 时的行为容易写错且难测。

裁定：`long_term_memories` 是唯一事实源，`memories_fts` 由 `add` / `update` /
`soft_delete` 显式同步。钉住它的测试必须**改完再搜**，只验证写入的测试区分不了
索引有没有同步。

## 6. 去重语义

`signature = sha256(normalize(content))`，`normalize` 做「小写 + 折叠空白 + 去首尾」。
表上 `signature TEXT UNIQUE`。

写入同指纹内容时**不报错**，而是更新已有条目的 `updated_at` / `importance`
（取较大值）并返回原 ID。理由：记忆写入发生在 agent 循环里，一次重复写入让整个
回合失败是不划算的。

## 7. 验收

- `tests/memory/` 全绿。
- `tests/entry` 等新栈现有测试**一条都不改**（纯增量的定义）。
- `SqliteSessionStore` 能直接传进 `attach_sessions(app, store=...)`，不需要适配器。
- 变异验证：每条不变式改一处、确认具名测试变红、还原、确认字节一致。

## 8. 变异表

脚本 `/tmp/mutate_memory.py`。每条：改一处 → 跑具名测试 → 要求变红 → 还原 →
校验 SHA256 与改前一致。并发相关的变异**必须重复跑**（脚本里 `REPEATS=8`），
单跑一次碰不上间歇失败，会把真变异误报成存活。

| # | 变异 | 应变红的测试 |
|---|---|---|
| 1 | `check_same_thread=True` | `test_database.py::test_shared_connection_survives_thread_hops` |
| 2 | 去掉 `database.py` 的 `Lock` | `test_database.py::test_concurrent_writers_do_not_interleave` |
| 3 | `add` 命中同指纹时抛错而非合并 | `test_store.py::test_duplicate_content_merges` |
| 4 | `update` 不同步 FTS5 | `test_store.py::test_search_sees_updated_content` |
| 5 | `precis` 按字节切而非按 rune 边界切 | `test_precis.py::test_truncation_keeps_utf8_intact` |
| 6 | TTL 判定用 `created_at` 而非 `updated_at` | `test_longterm.py::test_expiry_runs_from_the_update_not_the_creation` |
| 7 | `save` 把 system 消息也存回去 | `test_sessions.py::test_history_round_trip_has_no_system_message` |
| 8 | `list` 不按 `created_at` 倒序 | `test_sessions.py::test_list_is_newest_first` |

## 9. 独立评估后的修复（2026-09-19）

一个只读评估 agent 对标 harness9 复核了本层，报了 19 条。下面 7 条已修，
全部先写复现测试确认变红再改实现，变异 **8/8 killed**：

| # | 缺陷 | 修法 |
|---|---|---|
| B1 | `_add` 的 SELECT-then-INSERT 是 TOCTOU，跨进程抛 `IntegrityError` | 换成 `ON CONFLICT (signature) DO UPDATE ... RETURNING` 单语句 |
| B2 | FTS 查询用空格拼接 = 隐式 AND，整句查询召回 0 | 改 `" OR "`，与 harness9 `ltm/store.go:170` 一致 |
| B3 | `update` 改成已存在内容抛 `IntegrityError` | 先吸收同指纹的另一条（取较大 importance）再写 |
| B4 | `add` 实际使用 `entry.id`，与 docstring 承诺相反 | 始终自生成 id，read-modify-add 不再撞主键 |
| B5 | `soft_delete` 不清 `signature`，软删除被同内容 `add` 撤销 | 补 `signature = NULL`，与 harness9 一致 |
| B6 | `_escape_fts` 不过滤 NUL，抛 `unterminated string` | NUL 替换为空格 |
| B13 | 两个连接同时建 schema → `database is locked` | `connect(timeout=)` + 容忍 `journal_mode=WAL` 的 `SQLITE_BUSY` |

**变异验证抓到一处死代码**：显式 `PRAGMA busy_timeout` 是等价变异，
因为 `sqlite3.connect(timeout=)` 已经设过同一个值。已删除。

### 未修，需要决定

| # | 缺陷 | 说明 |
|---|---|---|
| B9 | 中文只能整段连写命中（`域识别` 搜不到 `域识别默认用`） | 默认分词器把连续汉字当一个 token。改 `tokenize='trigram'` 可解。已由 `test_chinese_matches_only_a_whole_unbroken_run` 标记 |
| B7 | MEMORY.md / DB 落盘 0644、目录 0755（harness9 是 0600/0700） | 长期记忆含用户偏好与项目名，多用户机器上同机可读 |
| B8 | `Lock` 非 `RLock`，`run()` 重入会永久死锁 | 当前无重入路径，但 `run()` 是公开 API |
| B11/B12/B15–B19 | 索引卫生、`list()` N+1、无 schema 版本、`rollback` 遮蔽原异常等 | 详见评估报告 |

## 10. LTM 补齐（2026-09-19，第二轮）

对标 harness9 `internal/ltm` 把三处缺口补上。变异 **14/14 killed**。

### 10-1 `stale_candidates`

对标 `store.go:336`。三个条件**同时**成立才算候选：`importance <= 1` 且
`use_count = 0` 且 `updated_at` 超过 60 天。少任何一条，它就会开始提议删除
「只是旧」或「只是没评分」的记忆，那样的清单没人敢用。

不删任何东西，只回答问题，删不删由调用方定。`now=` 参数与 `purge_expired`
一致，测试因此可以推进时钟而不用绕过公开接口改数据库行。

### 10-2 搜索命中强化

对标 `store.go:201-213`。这条**不是可选的**：`stale_candidates` 的核心条件是
`use_count = 0`，而在此之前没有任何调用者会增加它（`touch()` 无人调用），
所以那个条件恒为真，整个功能会退化成「列出全部低分条目」。

`search` 因此变成写操作，docstring 已写明。`updated_at` 不动——条目是被
**查阅**了，不是被**确认**了，TTL 继续走。`test_searching_for_an_entry_stops_it_looking_stale`
把这个耦合钉在一个测试里。

### 10-3 `MemoryExtractor`

对标 `ltm/extractor.go`。这是让 LTM 有数据的唯一途径。

**分层解法**：它复用 `omicsclaw.context.Summarizer` 这个**已有**的 Protocol
（`async summarize(prompt, *, system) -> str`），而不是另造一个 Generator
接口。因此 memory 仍然不 import `omicsclaw.provider`，叶子层守卫不用放宽。
评估报告建议「归属 context 层」——实测不必，注入既有 Protocol 就够了。

**fail-open 但不打日志**：harness9 是 fail-open + `log.Print`，但本仓库
`assembly.py` 裁定 entry 是第一个允许打日志的层。所以 `extract()` 返回
`ExtractionResult(stored, rejected, failure)`，由调用方决定怎么记。
模型超时、返回散文、store 写失败，三条路径都不抛。

**对模型输出不信任**：容忍 ```json 围栏、丢弃空 content、未知 category 归空、
importance 钳到 0–10、非整数 importance 归 0。每条都有具名测试和变异。

变异验证补上一个洞：「store 写入失败时 fail-open」这条路径原本**没有任何测试
覆盖**——因为 B1 修好后 `add` 在正常路径上不再抛异常，那个 `except` 成了裸奔
代码。已补 `test_a_failing_store_is_reported_with_what_was_already_written`。

### 仍未做（对标结论：都不属于本层）

| harness9 | 判定 |
|---|---|
| `ltm/provider.go`（Embedder / Consolidator） | 计划 §2 已声明非目标；harness9 自己也只有 noopProvider，主流程零调用 |
| 接线：开机跑 `purge_expired` + `regenerate`、把精华挂进 `default_sections()`、`memory_write`/`memory_search` 工具 | 要改 `entry/` 和 `tools/`，属于下一步 |
| `compaction_offloader.go`、`record_store.go` | 责任在 step 5/6 之间，见 §9 |
