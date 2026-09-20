# 0040 —— 把 `omicsclaw/memory/` 接进 agent 主循环

计划 0033 把 `omicsclaw/memory/` 建完了，并在 §10 末尾明确写着「接线：开机跑
`purge_expired` + `regenerate`、把精华挂进 `default_sections()`、
`memory_write`/`memory_search` 工具 —— 要改 `entry/` 和 `tools/`，属于下一步」。

这就是下一步。本文档记录接线做了什么、每个决定的理由、与 harness9 的差异、变异表，
以及没做和不确定的部分。

状态：已实现，并已按一次独立评估的裁定修复一条缺陷（§11）。变异 **45/45 killed**。

全文里凡是写「对标 harness9」的地方，都是实际读了
`/workspace/dataset/private/zhouwg_data/harness9` 的源码，不是推测。
第一稿曾凭印象断言「harness9 把 LTM 块放在 prompt 中段」，读了
`internal/context/builder.go` 才发现它也在最后一段 —— 这条已改正，记在这里
是因为「未经核对的 file:line 引用是缺陷」这条在 0039 已经吃过一次亏。

## 1. 接线前的实际状况

改动前对 core 代码做了一遍搜索，结论是整层**零调用者**：

| 组件 | 改动前的调用者 |
|---|---|
| `Database` / `LongTermStore` | 无。运行时根本没有 LTM 存储 |
| `MemoryExtractor`（具体实现） | 无。`AgentApp.memory_extractor` 恒为 `None` |
| `Precis` | 无。`MEMORY.md` 从来不生成 |
| `SqliteSessionStore` | 无。`SessionRegistry` 永远回落到 `InMemorySessionStore` |
| `purge_expired` / `Precis.regenerate` | 无 |

`FileOffloadStore` 与 `JsonlCompactionLog` 是例外 —— `entry/compaction.py`
已经接了它们，本次照抄了那个模块的形态。

## 2. 新增模块：`omicsclaw/entry/memory.py`

与 `entry/compaction.py` 平行的接线模块，**不把逻辑塞进 `assembly.py`**。
它提供四个接缝和一份开机维护：

| 导出 | 作用 |
|---|---|
| `open_memory(config)` | 打开 `<workspace>/.omicsclaw/memory.db`，返回 `MemoryBinding(database, store, precis)`；`config.memory=False` 时返回 `None` |
| `memory_section(binding)` | System Prompt 的长期记忆段，**闭包**读 `MEMORY.md` |
| `memory_tools(binding)` | `memory_search` + `memory_write`，各自自带 `ToolPolicy` |
| `build_memory_extractor(binding, summarizer)` | 压缩前提取，写完 LTM 顺手重生成精华 |
| `session_store(binding)` | `SqliteSessionStore`，结构化满足 `entry.SessionStore` |
| `prepare_memory(binding)` | 开机维护：`purge_expired()` + `Precis.regenerate()` |

## 3. 六项接入点

| # | 组件 | 接入点 |
|---|---|---|
| 1 | `Database` + `LongTermStore` | `entry/assembly.py:972`（`build_app` 内的 `open_memory(config)`）；实现 `entry/memory.py:129` |
| 2 | `MemoryExtractor` | `entry/compaction.py:109-111`（`build_compactor` 内派生）；包装类 `entry/memory.py:PrecisRefreshingExtractor`，工厂 `entry/memory.py:226` |
| 3 | `Precis` 进 System Prompt | `entry/assembly.py:542-543` + `:553`（`default_sections` 末段）；闭包 `entry/memory.py:172` |
| 4 | `memory_search` / `memory_write` | `entry/assembly.py:338-339`（`foundation_tools` 末尾）；工具 `entry/memory.py:memory_tools` 起 |
| 5 | `SqliteSessionStore` | `entry/session.py:866-867`（`attach_sessions` 的 `store is None` 分支）；工厂 `entry/memory.py:244` |
| 6 | 开机维护 | `entry/assembly.py:_swept()`，由 `open_app` 的两条返回路径各调一次；实现 `entry/memory.py:146` |

配套改动：`AgentApp` 新增 `memory` 字段、`aclose()` 关连接、`AppConfig.memory`
开关与 `AppConfig.state_dir()`。

## 4. 每个决定的理由

### 4-1 为什么不在 `build_app` 里设 `AgentApp.memory_extractor`

任务简报说「`build_app` 从不设置 `memory_extractor`」是缺陷，让我去设。**实测发现
照做会引入一个更隐蔽的缺陷**，所以改成在 `build_compactor` 里派生。

`MemoryExtractor(summarizer, store)` 在构造时**捕获** summarizer。而
`AgentApp` 是 frozen dataclass，`dataclasses.replace(app, summarizer=X)` 是这个
仓库里替换摘要模型的标准写法（`AgentApp.summarizer` 的 docstring 和多个现有测试都这么用）。
一旦在 `build_app` 里构造好 extractor，`replace` 之后这两个字段就不一致了：
压缩走新 summarizer，提取仍然打老的。

这不是理论风险 —— 在 `build_app` 里设字段之后，`tests/entry/` 里
**2 条既有测试**（`test_compaction_in_loop.py` 的
`test_an_emergency_truncation_leaves_room_to_summarize_next` 与
`test_compact_summarizes_a_quiet_session_in_its_lane`）立刻变红：
它们替换掉的 summarizer 被忽略，提取转而去调那个被脚本化的 *provider*，
把测试数好的回复吃掉了（后者断言 `provider.calls == 1`，实测 2）。

> 订正（独立评估复核）：初稿这里写的是「四个测试变红」。实测是
> **2 条既有 + 3 条新测试**，另两条当时的红
> （`test_turn.py` 与 `test_session.py` 的档位断言）是工具表变长导致的，
> 属于 §8 那一类，与本条无关。原文把两件事算成了一件。

裁定：`build_compactor` 每次从 `app.memory` + `app.summarizer` 现场派生，
两个字段在同一口气里读出来，不可能不一致。`AgentApp.memory_extractor` 保留为
**覆盖点**（已有 `test_the_memory_extractor_reads_what_is_summarized_away` 在用），
设了就用设的。

代价：`app.memory_extractor is None` 不再等于「不提取」。这条写进了字段 docstring。

### 4-2 为什么记忆段排在 `environment` **之后**

`default_sections` 的既有排序原则是「易变的块放后面，改一块少失效一点缓存前缀」。
`environment` 每天变一次（日期），记忆段在 agent 跑的过程中被 `memory_write` 改写 ——
它比 `environment` 更易变，所以排最后。有 `test_the_memory_block_is_the_last_section_of_the_prompt`
钉住。

harness9 的 `internal/context/builder.go:Build()` 也把长期记忆放在最后一段
（第 6 段，在 sandbox 之后），结论一致但理由不同：它没有前缀缓存的约束，
本仓库有 ADR 0024。

### 4-2b 记忆段里**不**写工具用法

harness9 的记忆段带一句指引：「需要更多历史细节时用 `memory_search`；
发现值得长期保留的新信息时用 `memory_write`」。本实现没有照抄，理由是
`assembly.py` 的 `TOOL_GUIDANCE` docstring 已经定了规矩 ——
「工具定义自带描述，在这里重复就是一件事两个来源」。那两句话因此写在
两个工具各自的 description 里（`memory_search` 的描述明说「在问用户一件他们
可能已经告诉过你的事之前先搜」）。

附带好处：记忆段因此是纯内容，不承诺任何工具存在。调用方自带 `tools=` 而没挂
记忆工具时，Prompt 不会指着一个不存在的工具 —— 这正是 `plan_tool=` 参数
为规划段解决的问题，而记忆段靠「不说」就绕过了。

### 4-3 为什么段的 source 必须是闭包

`omicsclaw/context/sections.py` 开头就用 MEMORY.md 举例说明这条：快照会让 agent
读到自己刚写之前的版本。`memory_section` 因此闭包住 `binding.precis` 并在每次
render 时 `precis.read()`。变异「段持快照」被
`test_the_memory_block_is_re_read_on_every_render` 杀掉。

### 4-4 为什么提取之后要重生成精华

`MemoryExtractor` 只写 store，不碰 `MEMORY.md`。不补这一步，压缩提取出的记忆要等到
下一次 `memory_write` 或下一次开机才进 Prompt —— 闭环是断的。
`PrecisRefreshingExtractor` 是 entry 层的组合包装：调底层提取 → 记日志 →
存了东西就 `regenerate()`。**memory 层一行没改**。

这个包装同时解决了 0033 §10-3 留下的「fail-open 但不打日志，由调用方决定怎么记」：
entry 是第一个允许打日志的层，所以记在这里。**只记条数，不记内容** ——
`CLAUDE.md` 安全第一条 + `assembly.py` 的「no tool argument and no tool output is
ever logged」，记忆内容来自对话，同理。

### 4-5 `memory_search` 为什么 `read_only=False`

`LongTermStore.search` 会给命中条目 `use_count += 1`（0033 §10-2：不加这个，
`stale_candidates` 的 `use_count = 0` 条件恒真，整个功能退化）。所以它**是**写操作。
`ToolPolicy` 的 claims 是「关于副作用的断言」，声明 `read_only=True` 就是声明一个
它不遵守的事实，而权限层有资格据此放行。有具名测试钉住。

两个工具都显式声明 policy（`LOW` / `AUTO`），照 `use_skill_tool` 与 `plan_write_tool`
的形态：不声明就继承 `HIGH` / `ASK`，而没有绑定审批通道时审批 fail-closed ——
结果不是「更安全」，是「agent 再也不记东西了」。

### 4-5b `memory_write` 有三个 action，`memory_search` 返回 JSON

第一版只做了 `add`，读了 `internal/tools/memory_write.go` 才补上 `update` 与
`remove` —— harness9 是三个 action，而且这两个 action 是
`LongTermStore.update` 与 `soft_delete` 仅有的可能调用者：不做它们，
本步就仍然留着两个零调用者的组件，与任务目标矛盾。

连带的后果是 `memory_search` **必须返回 id**，否则模型看得见一条记忆过时了
却叫不出它的名字。所以搜索结果从精华用的 Markdown 换成 JSON
（`id` / `title` / `content` / `category` / `importance`），与 harness9 一致。
`test_a_search_hit_carries_the_id_an_update_needs` 把这条耦合钉在一个测试里。

一处比 harness9 好：**`importance` / `ttl_days` 的「未提供」可表达。**
harness9 用 Go 的零值判断（`if in.Importance != 0`），它自己的注释承认这个限制：
无法通过 update 把重要度显式设回 0。Python 侧用 `None` 默认值区分「没说」与
「说了 0」，`_changes()` 只收模型真的给了的字段。

没照抄的：`tags`。store 存得下，但精华与搜索结果都不渲染它，
让模型填一个没人读的字段是纯浪费。

### 4-5c 搜索结果的上界，以及它一度造成的静默空结果

harness9 的 `memory_search` 直接 `json.Marshal` 全部命中，**没有上界**
（`internal/tools/memory_search.go:61-65`）。本实现加了
`SEARCH_RESULT_MAX_BYTES`（4096），理由是无界的搜索结果能把窗口吃掉，而且
**按字节截断一个 JSON 数组得到的不是 JSON** —— 模型会把解析失败读成
「记忆坏了」而不是「还有更多」，所以要丢就丢整条。

**这个上界第一版写错了，是相对 harness9 的回归，独立评估复现并裁定必修。**
原实现无条件从末尾丢整条直到装得下；一条 JSON 表示超过 4096 字节的记忆
因此被丢成 `[]`：

```
store.search 命中   : 1
memory_search 返回  : '[]'   ← 模型被告知「什么都没找到」
use_count 事后      : 2      ← 命中计数照加，污染 stale_candidates 唯一的判据
```

命中了却报空比报错更坏：模型据此去问用户已经告诉过它的事，而且回复里
**没有任何信号**表明发生过截断。同一个上界在整个 `tests/` 里当时零测试。

**修法**（`_fit` / `_shortened`）：

1. 仍然从末尾丢整条，但**只在还剩不止一条时丢** —— 排第一的最佳命中永不丢弃。
2. 唯一那条仍装不下时，**截断它的正文**（`truncate_utf8`，UTF-8 边界安全，
   自带 `…(truncated)` 尾巴），并在该条上置 `content_truncated: true`。
3. 正文与**标题一起**折半收缩。标题同样没有上限，`content` 极短而 `title`
   极长时只收正文会走到正文为空、标题原封不动，答案仍然超界，
   而 `id`（模型再次够到这条记忆的唯一途径）就永远到不了。
4. `content_truncated` 只在真的截断时出现，它的**缺席**就是「正文完整」的断言。

这样上界、合法 JSON、以及「命中必有回音」三件事同时成立。四条具名测试 +
六条变异钉住（§6 的 21-26）。

harness9 在这一点上仍然与本实现不同：它会把那条超长记忆原样返回。
本实现是「有界且不静默」，不是「无界」，也不再是「有界但会静默丢失」。

### 4-6 `category` 的重复校验被删掉了

`_write` 原本既在 `MEMORY_WRITE_SCHEMA` 里声明 `enum`，又在函数体里再查一遍。
变异验证直接抓到：改掉函数体里的检查，测试仍然绿 —— 因为
`FunctionTool.execute` 先按 schema 校验过了，函数体那个分支**永远到不了**。
两个互相遮蔽的守卫等于两个都没测到。

裁定：删掉函数体里的检查，留 schema 的 `enum`（它同时也是模型能看见的合法值表）。
这与 0033 §9「变异验证抓到一处死代码（显式 `PRAGMA busy_timeout`），已删除」
是同一条处理方式。

注意这与 `planning/tool.py` 的 `_decode` 逐字段复查**不矛盾**：那里校验的是数组元素
里的嵌套字段，且它的错误信息带下标，是 schema 给不出的东西。

### 4-7 `AppConfig.state_dir()`

`entry/memory.py` 原本从 `entry/compaction.py` import `STATE_DIRNAME`，而
第 4-1 条的裁定要求 `compaction.py` 反过来 import `memory.py` —— 循环。

解法是把 `STATE_DIRNAME` 和 `state_dir()` 提到 `config.py`，两边都向下依赖它。
顺手把 `permission_rules_path()` 和 `plans_root()` 里的两个 `".omicsclaw"`
字面量也换成 `state_dir()`：改之前这个字面量在仓库里有三份。
`compaction.py` 仍然 re-export `STATE_DIRNAME`，外部导入者不受影响。

### 4-8 会话持久化的默认行为：持久化

`attach_sessions(app, store=None)` 现在的含义是「用这个 app 自己的库」，
不是「用内存」：

- app 开了记忆库 → `SqliteSessionStore(app.memory.database)`，对话跨进程存活。
- app 没有（`memory=False`，或手搭的 app）→ 照旧回落 `InMemorySessionStore`。
- 显式传 `store=` → 永远赢。

理由：真正的调用点在交互层（`entry/cli/__main__.py` 等），owner 正在单独优化那一层，
本次不碰。要让「默认就有持久化」成立而又不改那一层，唯一的位置就是
`attach_sessions` 的默认值。**「短写法就有持久化」比「知道要问才有」更难写错** ——
一个 surface 忘了传 store 的后果是用户的对话悄悄消失，而这类缺陷没人会报。

复用记忆库的同一个 `Database`（同一个文件、同一个连接），而不是另开一个：
`memory.db` 的 schema 本来就同时建了 `sessions` / `messages` / `long_term_memories`
三张表（0033 的 `SCHEMA`），两个连接打同一个文件只是白白多一份锁竞争。

### 4-9 `config.memory` 开关

照 `planning: bool` 的先例：一个开关一个含义，同时决定库、两个工具、Prompt 段、
提取、会话存储。半个（Prompt 里有块但没人写，或提取器在填一个没人读的库）比两个都没有更糟。
默认 `True`，理由同 `planning` 的 docstring：一个默认关闭的能力是带额外步骤的模式。

命令行 `--memory`，环境变量 `OMICSCLAW_MEMORY`。注意它与容器内存上限
`--sandbox-memory` 无关，字段 docstring 里写明了。

### 4-10 路径

`<workspace>/.omicsclaw/memory.db` 与 `<workspace>/.omicsclaw/MEMORY.md`，
与 offload、压缩记录、plans、permission 规则同一个目录。

`MEMORY.md` 没有放在 workspace 根：那会让它出现在用户的项目树里，
并且 agent 自己的 `read_file` / `edit_file` 会直接改它，绕开 `memory_write`
的去重与重要度。

### 4-11 资源归属

- `build_app` 打开库；中途抛异常就在 `except BaseException` 里关掉再抛
  （与 `open_app` 对 sandbox / MCP 的处理对称）。
- `AgentApp.aclose()` 在 sessions drain、MCP、sandbox 之后关库 ——
  宽限期内还在跑的工具调用要留着一个可写的记忆。
- `open_app` 的开机维护包在 `_swept()` 里，只有取消能逃出去，逃出去时把库关掉。

## 5. 与 harness9 的差异

| harness9 | 本实现 | 理由 |
|---|---|---|
| `internal/ltm/extractor.go`：fail-open + `log.Print` | 提取本身不打日志，由 `entry` 层的 `PrecisRefreshingExtractor` 记 | 0033 的分层裁定：`memory` 是叶子层，`entry` 是第一个允许打日志的层 |
| extractor 在装配时构造一次（`cmd/harness9/main.go`） | 每次压缩从 `app` 现场派生 | §4-1：Python 侧 `dataclasses.replace` 会让捕获的 summarizer 过期，Go 侧没有这个写法 |
| `builder.go` 的长期记忆段带「用 `memory_search` / `memory_write`」指引 | 段里只有精华内容 | §4-2b：`TOOL_GUIDANCE` 已裁定工具用法归工具描述；顺带让记忆段不承诺工具存在 |
| `cmd/harness9/main.go:254` 精华文件在 harness 的状态目录 | `<workspace>/.omicsclaw/MEMORY.md` | 与本仓库既有的 `.omicsclaw/` 一致 |
| `main.go:256-259` 启动时 `PurgeExpired` + `Regenerate` | 同，但在 `open_app`（async）而不是 `build_app` | `purge_expired` / `regenerate` 是 async，`build_app` 是同步函数 |
| `memory_write` 三个 action | 同 | §4-5b |
| `memory_write` 的 `update` 无法把 importance / ttl_days 设回 0（其源码注释自陈） | `None` 默认值区分「没说」与「说了 0」 | §4-5b |
| `memory_search` 返回全部命中的 JSON，无上界，超长条目照样返回 | 同样 JSON，但有 4096 字节上界：多余的整条丢弃，最佳命中永不丢、改为截断正文并标 `content_truncated` | §4-5c。上界是本实现加的；第一版的丢弃策略会把唯一命中丢成 `[]`，是相对 harness9 的回归，已修 |
| `memory_write` / `memory_search` 无 approval 概念 | 显式 `ToolPolicy(LOW, AUTO)` | 本仓库有权限层，不声明 = 每次弹审批 |
| `memory_write` 支持 `tags` | 未做 | 精华与搜索结果都不渲染 tags |
| `ltm/provider.go`（Embedder / Consolidator） | 未做 | 0033 §2 已声明非目标；harness9 自己也只有 noopProvider |

## 6. 变异表

脚本 `/tmp/mutate_memory_wiring.py`（`REPEATS=3`，每条变异连跑三次才判定存活）。
每条：改一处 → 跑具名测试 → 要求变红 → 还原 → 校验 SHA256 与改前一致。

**45/45 killed。**（前 39 条是接线本身，21-26 是独立评估之后补的搜索上界修复。）

| # | 变异 | 应变红的测试 |
|---|---|---|
| 1 | `build_app` 不开库 | `test_building_an_app_opens_the_memory_database` |
| 2 | `open_memory` 无视开关 | `test_memory_off_opens_nothing_and_mounts_nothing` |
| 3 | `state_dir()` 指向别处 | `test_the_database_and_the_precis_sit_beside_the_other_state` |
| 4 | `build_app` 不挂记忆工具 | `test_the_memory_tools_reach_the_registry` |
| 5 | 同上（权限普查） | `test_permission_wiring.py::test_every_mounted_tool_is_gated` |
| 6 | 工具插在列表前面而不是追加 | `test_the_memory_tools_are_mounted_after_everything_else` |
| 7 | `memory_write` 不声明 policy | `test_neither_memory_tool_stops_to_ask_a_human` |
| 8 | `memory_search` 声明 `read_only=True` | `test_memory_search_does_not_claim_to_be_read_only` |
| 9 | `memory_write` 的 add 不重生成精华 | `test_memory_write_stores_an_entry_and_rewrites_the_precis` |
| 10 | 搜索结果不带 id | `test_a_search_hit_carries_the_id_an_update_needs` |
| 11 | update 覆盖没给的字段 | `test_memory_write_updates_only_the_fields_it_was_given` |
| 12 | 「没说重要度」被读成 0 | 同上 |
| 13 | update 不重生成精华 | 同上 |
| 14 | remove 不重生成精华 | `test_memory_write_removes_what_stopped_being_true` |
| 15 | 删一条不存在的也报成功 | `test_memory_write_refuses_an_id_the_store_does_not_hold` |
| 16 | update / remove 接受空 id | 同上 |
| 17 | schema 去掉 `category` 的 enum | `test_memory_write_refuses_a_category_it_does_not_have` |
| 18 | 接受空 content | `test_memory_write_refuses_blank_content` |
| 19 | 接受空 query | `test_memory_search_refuses_an_empty_query` |
| 20 | 不钳 search 的 limit | `test_memory_search_clamps_the_limit_it_is_given` |
| 21 | 唯一一条装不下就丢掉 | `test_a_match_too_large_to_fit_is_shortened_rather_than_dropped` |
| 22 | 超长条目原样返回（破上界） | `test_a_shortened_answer_is_still_json_and_still_bounded` |
| 23 | 截断正文但不标 `content_truncated` | `test_a_match_too_large_to_fit_is_shortened_rather_than_dropped` |
| 24 | 没截断也标 `content_truncated` | `test_a_match_that_fits_is_not_marked_as_shortened` |
| 25 | 只收正文不收标题 | `test_an_entry_whose_title_alone_overflows_is_still_answerable` |
| 26 | 上界实际不生效 | `test_a_shortened_answer_is_still_json_and_still_bounded` |
| 27 | `default_sections` 不加记忆段 | `test_a_compaction_reaches_the_next_system_prompt` |
| 28 | 记忆段排在 `environment` 之前 | `test_the_memory_block_is_the_last_section_of_the_prompt` |
| 29 | `build_app` 不把 binding 交给段 | `test_the_memory_block_is_re_read_on_every_render` |
| 30 | 段持快照而不是闭包 | 同上 |
| 31 | `build_compactor` 不派生提取器 | `test_a_compaction_extracts_into_the_long_term_store` |
| 32 | `build_compactor` 无视覆盖字段 | `test_an_explicit_extractor_wins_over_the_derived_one` |
| 33 | 派生时用的不是 app 当前的 summarizer | `test_the_extractor_follows_a_substituted_summarizer` |
| 34 | 提取后不重生成精华 | `test_a_compaction_reaches_the_next_system_prompt` |
| 35 | 没有 summarizer 也造提取器 | `test_no_summarizer_means_no_extractor` |
| 36 | 没有 store 也造提取器 | `test_extraction_without_memory_is_simply_off` |
| 37 | 开机不清理过期 | `test_starting_up_purges_the_expired_and_rebuilds_the_precis` |
| 38 | 开机不重建精华 | 同上 |
| 39 | 维护失败向上抛 | `test_a_broken_memory_does_not_stop_the_process_starting` |
| 40 | `open_app` 不做开机维护 | `test_open_app_sweeps_a_memory_left_by_an_earlier_process` |
| 41 | `attach_sessions` 没有默认 store | `test_attaching_sessions_defaults_to_the_apps_own_database` |
| 42 | 默认 store 覆盖调用方传的 | `test_a_caller_s_own_store_still_wins` |
| 43 | 同 41（跨进程视角） | `test_a_conversation_outlives_the_process_that_held_it` |
| 44 | `aclose` 不关库 | `test_closing_the_app_closes_the_memory_database` |
| 45 | 装配失败泄漏连接 | `test_an_assembly_that_raises_closes_the_memory_it_opened` |

第一轮（32 条）跑出 2 条 SURVIVED、2 条 BROKEN：

- SURVIVED「接受任意 category」→ 发现函数体里的检查被 schema enum 完全遮蔽，
  是不可达分支。按 §4-6 删掉函数体的检查，变异改为打 schema。
- SURVIVED「没有 summarizer 也造提取器」→ 原测试用的是「没有 store」那条路径，
  覆盖不到。补 `test_no_summarizer_means_no_extractor`。
- BROKEN ×2 是锚点缩进写错（`build_app` 的那段改进 try 块之后缩进从 12 变 16）。

补上搜索上界的六条之后又出过 1 条 SURVIVED：「只收正文不收标题」在
正文与标题长度相当时是**等价变异**（两者同步折半，正文先空时标题已经够小）。
它只在 `title/content` 比值超过约 4096 时才有差别 —— 而那是模型
真能写出来的形状。补 `test_an_entry_whose_title_alone_overflows_is_still_answerable`
（content 一个词、title 12 万字节）打中这条路径，变异随即被杀。
这条记在这里是因为它是本轮唯一一次「看起来像测试洞、其实要先判断是不是等价变异」
的情况，而判断结论是**可达**，所以补测试而不是删代码。

## 7. 端到端自证

`/tmp/prove_memory_loop.py`（临时脚本，不进仓库）。用假 summarizer 驱动一次真实压缩，
逐步断言闭环：压缩前 Prompt 没有记忆段 → 压缩 → 条目进 LTM → `MEMORY.md` 被重写 →
**下一次 render 的 System Prompt 里出现那条记忆** → 换一个新 app（模拟重启）仍然读得到 →
`memory_search` 也能搜到。16 项全 PASS。

## 8. 被迫改动的既有测试

「纯增量」在本步做不到，因为本步**就是**改既有装配。三处既有测试被改：

| 文件 | 改动 | 理由 |
|---|---|---|
| `tests/entry/test_permission_wiring.py` | `MOUNTED` 加两个名字 | 它是「挂载了哪些工具」的普查表，新工具必须进表才能被「每个工具都被 gate」这条断言覆盖 |
| `tests/entry/test_turn.py::test_the_system_message_survives_a_successful_summarization` | 配置加 `memory=False` | 它断言的是压缩**档位**，而 `measure` 按 `tools_snapshot` 的实际声明预留 token —— 多两个工具就把这段历史从 `full` 顶进 `emergency`，测试不再测它要测的东西 |
| `tests/entry/test_session.py::test_a_second_compaction_extends_the_first_instead_of_restarting` | 同上 | 同上；`emergency` 档根本不调 summarizer |

后两处是这次接线的**真实代价**：工具表变长，可用窗口变窄。记录在此，
因为下一个往 `foundation_tools` 加工具的人会再遇到一次。

## 9. 测试数字

| 范围 | 改前 | 改后 |
|---|---|---|
| `tests/memory tests/context tests/entry` | 1067 passed, 1 failed, 1 skipped | **1150 passed, 1 skipped** |
| `tests/skills tests/tools tests/schema tests/provider` | 1560 passed | 1560 passed |
| 新增 `tests/entry/test_memory_wiring.py` | — | 39 passed |

第一行的总数在本步进行期间是**移动靶**：另一个 agent 在并发写
`omicsclaw/entry/`，期间总数从 1067 涨到 1109 又涨到 1145，中途还出现过
两条与本步无关的红（`test_planning.py` 的 provider double 多声明了 `model`、
`cli/_configure.py` 的 `provider.upper()` 被 AST 守卫误判），都在几分钟内
由对方修掉。本步自己负责的增量是那 39 条（接线 35 条 + 搜索上界修复 4 条）。

改前那 1 条 failed 是 `test_assembly.py::test_no_provider_double_declares_more_interface_than_the_protocol`
（`tests/entry/test_planning.py:46` 的 `_ScriptedProvider.model`），与本步无关，
过程中被并发的另一个 agent 修掉了。

`tests/tools/test_workspace.py` 收集失败（`omicsclaw/services/path_validation.py` 已被
重建删除）和 `tests/launch/test_surfaces.py` 的两条 dotenv 失败（仓库根多了一个本地
`.env`），都是本步之外的既有问题，未处理。

## 10. 没做的 / 不确定的

1. **没改交互层。** `entry/cli/__main__.py` 等真实调用点是 owner 在单独优化的范围。
   本步只保证「默认就有持久化」在 `attach_sessions` 这一层成立。

2. **没为 `MEMORY.md` / `memory.db` 设文件权限。** 0033 §9 的 B7 还挂着：
   长期记忆含用户偏好与项目名，现在是 0644/0755，多用户机器上同机可读。
   harness9 是 0600/0700。本步没碰，因为它属于 `omicsclaw/memory/` 内部而本步尽量不动那层。

   补充（独立评估）：**`memory.db-wal` 与 `memory.db-shm` 同样是 0644**，
   而 WAL 里装着尚未 checkpoint 的同一批内容。只改主库和 `MEMORY.md` 的
   权限是不够的。

3. **中文检索比「整段连写才命中」更糟。** 初稿把 0033 §9 B9 记轻了。
   独立评估实测：不是「需要连续的词」，而是**任何自然子串都不命中** ——
   对「这个项目的空间域识别一律用 leiden」这条记忆，搜 `域识别` 和 `这个项目`
   都是 0 命中，只有整句原文、或被标点/空格切开的那些片段能中。
   FTS5 默认分词器把一整串连续汉字当成**一个 token**。

   严重的地方在于这不是边缘路径：`extractor.py:25-26` 明确指示模型
   「用对话的语言写 title 和 content」，所以中文用户的**默认路径**
   产出的就是自己搜不到的记忆。`tokenize='trigram'` 可解，
   但要改 `omicsclaw/memory/` 的建表语句（本步不动那层），且需要迁移既有库。

4. **漏了 harness9 的 `WithMemoryNudge`**（`cmd/harness9/main.go:446`、
   `internal/engine/options.go:69-71`）：它每 10 轮往**临时**历史里注入一条
   「有值得长期保留的信息就调 `memory_write`」的提醒。这是独立评估找出的
   **唯一一条本文档没记录的 harness9 缺口**。

   后果不小：没有它，「记」这一半完全押在自动提取器上，而提取器**只在压缩时跑** ——
   一个从不触发压缩的短会话，什么都不会被记下来。OmicsClaw 有现成的座
   （`TurnAugmentor`，planning 正在用它注入计划块），接上去不需要新机制。

5. **精华标题与 prompt 章节同级**（`omicsclaw/memory/precis.py:53` 用 `## `）。
   记忆内容是模型写的、原样落盘、原样注入，所以一条被注入过的会话可以种下
   一条渲染成 `## Safety rules` 的**兄弟节**；又因为记忆块按 §4-2 排在最后，
   那个伪章节排在真 safety 之后。

   harness9 的标题级别相同，但它的记忆段有一句引导语框住整块；本实现按 §4-2b
   去掉了引导语，所以**这一点比 harness9 差**。便宜的修法是把精华标题降成
   `### ` 或列表项，并补一句框定语 —— 两者都要动 `omicsclaw/memory/precis.py`
   或 §4-2b 的裁定，本步（owner 裁定只修搜索上界）未做。

6. **`stale_candidates` 与 `touch` 仍然没有调用者。**
   `stale_candidates`「只回答问题，删不删由调用方定」，而本步没想清楚谁是那个
   调用方（开机时提议？让模型自己看？），所以没接；`purge_expired`（TTL 到期）
   接了，两者不是一回事。`touch` 则是被 `search` 内联的那段计数更新取代了，
   它作为公开方法没有第二个用途 —— 要么给它找一个，要么删掉，本步两件都没做。

   `LongTermStore.update` 与 `soft_delete` 原本也在这张单子上，
   §4-5b 补上 `memory_write` 的 update / remove 之后不再是。

7. **没有证据说明什么样的提取质量是够的。** 提取的 prompt 与解析全部沿用 0033，
   本步只保证它会被调用。真实模型上一次压缩提取出几条、有多少是废话，没有测过。

8. **`concurrency_safe=True` 给 `memory_search` 是判断，不是测量。** 理由是
   `Database` 有锁、search 只加计数器。如果将来 search 变成会改内容的东西，
   这个声明要重新想。

9. **跨进程并发：已验通过，但 `MEMORY.md` 的写入不是原子的。**
   初稿把这条列为「没验」。独立评估补了实测：3 进程 × 60 次
   `add` + `regenerate` 打同一个 `memory.db` → **180/180 行落库、0 错误**，
   WAL + 15 s busy timeout 扛住了，0033 §9 的 B1/B13 有效。

   剩下的那半仍然不确定：`Precis.regenerate` 用 `Path.write_text`
   （先截断再写，非原子），所以并发的读者可能读到**撕裂的 MEMORY.md** ——
   也就是撕裂的 system prompt。harness9 的 `os.WriteFile` 同样如此，
   属于**继承而非本步新引入**。真要修是「写临时文件 + `os.replace`」，
   那要动 `omicsclaw/memory/precis.py`。

## 11. 独立评估后的修复（2026-09-20）

一个只读评估 agent 复核了本步。裁定：六个接入点全部真接上、闭环经独立探针证实、
§8 那三处既有测试改动正当（量化为 **+589 token = 窗口的 0.23%**）、
§4-1 推翻任务书前提的裁定正确、循环 import 确已消除、新测试变异全杀。

owner 裁定**只修一条**，其余记入遗留清单：

| 缺陷 | 处置 |
|---|---|
| `memory_search` 的上界会把唯一一条超长命中丢成 `[]`（相对 harness9 的回归，该上界当时零测试） | **已修**，见 §4-5c；先写复现测试确认变红再改实现；变异 45/45 killed |
| 漏了 harness9 的 `WithMemoryNudge` | 记入 §10-4 |
| 中文检索比初稿承认的更糟（任何自然子串都不命中） | 记入 §10-3 |
| 精华标题与 prompt 章节同级，可被种伪 `## Safety rules` | 记入 §10-5 |
| `memory.db-wal` / `-shm` 同样 0644 | 记入 §10-2 |

两条记述订正（不涉及代码）：§4-1 的「四个既有测试变红」实测是
**2 条既有 + 3 条新测试**；§10 的跨进程并发从「没验」改为
**已验通过**，并注明 `Precis.regenerate` 非原子写这一继承来的半条。
