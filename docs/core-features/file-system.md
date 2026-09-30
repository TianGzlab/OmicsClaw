# 文件系统能力

## 1. 概述

OmicsClaw 的分析产物几乎都落在文件里：skill 脚本写出的 `.h5ad`、`result.json`、`figure_data/`，模型自己写的分析脚本和报告，以及 agent 关于自身的状态（会话、计划、权限规则、被卸载的大段工具输出）。文件系统能力要回答四个问题：

| 问题 | OmicsClaw 的做法 | 代码位置 |
|---|---|---|
| 模型给出的路径到底指向哪个真实文件，能不能碰 | `Workspace.resolve()`：解析符号链接 → 拒绝凭据路径 → 要求落在工作区内 | `omicsclaw/tools/_workspace.py` |
| 模型怎样读、写、改文件 | 三个内置工具 `read_file` / `write_file` / `edit_file` | `omicsclaw/tools/builtin/read.py`、`write.py`、`edit.py` |
| 两个并发调用写同一个文件时不丢更新 | 引擎写屏障 + 进程级读写路径锁 | `omicsclaw/engine/executor.py`、`omicsclaw/tools/_pathlock.py` |
| 巨大的工具输出撑爆上下文 | 工具自身截断 + 上下文压力达到阈值时把旧的大结果卸载到文件 | 各工具常量、`omicsclaw/context/offload.py`、`omicsclaw/memory/offload.py`、`omicsclaw/entry/compaction.py` |

agent 关于自身的状态统一放在 `<workspace>/.omicsclaw/`（`STATE_DIRNAME`），见第 8 节。

OmicsClaw 没有一个"文件系统 hooks 层"：路径沙箱在工具层，卸载是上下文压缩的一个档位，计划持久化属于 `omicsclaw/planning/`，而 hook 层（`omicsclaw/hooks/`）只承担拦截机制与审计。

## 2. 架构

```
                     模型发出的 path（不可信输入）
                                │
     ┌──────────────────────────┼──────────────────────────┐
     ▼                          ▼                          ▼
 read_file                  write_file                 edit_file
 (FunctionTool, AUTO)       (Tool, ASK)                (Tool, ASK)
     │                          │                          │
     └────────── resolve_workspace(explicit) ──────────────┘
                 构造时给定的 Workspace，或 ToolContext.values["workspace"]
                                │
                    Workspace.resolve(path)
                    1. (root / path).resolve()   ← .. 归一、跟随符号链接
                    2. is_sensitive()            ← 凭据/密钥文件，无论是否在工作区内
                    3. is_relative_to(root)      ← 必须在工作区内
                                │ 真实绝对路径
                                ▼
                    read_lock / write_lock(resolved)   ← _pathlock.PATH_LOCKS
                                │
                                ▼
          本地文件系统（environment=None）或注入的 File*Environment

 ──────────────────────────── 大输出 ────────────────────────────
 工具结果 ─► 工具内截断（bash 16,000 字符 / read 8,192 字节或 500 行 / web_fetch 8,000 字符）
         ─► 进入历史
         ─► 下次模型调用前 ProgressiveCompactor 测量压力
               └─ ≥ WARN：offload_messages()（context/offload.py，决定"哪条、占位符写什么"）
                     └─ FileOffloadStore.put()（memory/offload.py，决定"字节写到哪"）
                           └─ <workspace>/.omicsclaw/tool_results/<session>/<key>.txt
         ─► 模型需要时用 read_file 按工作区相对路径读回
```

## 3. 工作区边界：`Workspace`

`omicsclaw/tools/_workspace.py` 是 `read_file`、`write_file`、`edit_file` 共用的唯一路径解析器（`bash` 不做路径检查，见第 9 节）。它是纯标准库的叶子模块，连 `omicsclaw.tools` 其他模块都不导入。

### 3.1 构造

```python
@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
```

- `__post_init__` 对根目录做 `expanduser().resolve()`：操作员配置里的 `~` 表示操作员的 home；而模型 payload 里的 `~` 只是一个普通目录名。
- 根目录本身若是敏感路径，构造时就抛 `PathIsSensitive`，而不是让之后每次调用都失败。
- 冻结对象：工具不能在运行中放宽边界。
- 生产环境中只在 `entry/assembly.py` 的 `foundation_tools()` 里构造一次，`Workspace(config.workspace)`，同一对象交给三个文件工具和 `bash`。`AppConfig.workspace` 来自 `--workspace` / `OMICSCLAW_WORKSPACE`，缺省为当前工作目录（解析为绝对路径）。

工具构造时没有拿到 `Workspace` 的话，`read.py` 中的 `resolve_workspace()` 会按调用读取 `ToolContext.values` 中键为 `WORKSPACE_KEY = "workspace"` 的值（可以是 `Workspace` 或任意路径），这让一个注册表能服务多个会话；两者都没有时抛 `RuntimeError`（刻意不是 `ToolArgumentError`，因为模型发什么参数也无法绑定工作区）。

### 3.2 `resolve(path)` 的三条规则

按顺序执行：

1. **解析**：`(self.root / Path(path)).resolve()`。相对路径拼到根上，绝对路径按原样判定（Python 的 `/` 运算对绝对路径的第二个操作数直接取它本身，不会拼成 `/ws/etc/passwd`）。`..` 归一化并**跟随符号链接**，判定的是真正会被打开的文件。空字符串和 `"."` 都指根目录。NUL 字节、超长名称、符号链接环等导致 `OSError` / `ValueError` 的输入抛 `PathRefused`。
2. **拒绝凭据**：对解析后的路径调用 `is_sensitive()`，无论它在不在工作区内。工作区里有一份 SSH 私钥，不等于它可读。
3. **要求包含**：`candidate.is_relative_to(root)`，按路径组件比较，`/project-evil` 不会被当成 `/project` 的子路径。

规则 2 排在规则 3 之前，是为了让"尝试访问凭据"与"模型写错了相对路径"在日志里看起来不同。

返回值是绝对、无符号链接的 `Path`，**不保证存在**（`write_file` 正需要这一点）。

### 3.3 敏感路径

| 常量 | 内容 | 匹配方式 |
|---|---|---|
| `CREDENTIAL_PATHS` | `.ssh`、`.aws`、`.kube`、`.gnupg`、`.netrc`、`.config/gcloud`、`.config/gh` | 路径中**连续组件**匹配，不锚定到 home；`sshconfig.md` 不算 |
| `SECRET_FILENAMES` | `.env`、`.env.*`、`.envrc` | 只对文件名做 `fnmatch`；名为 `.env` 的目录（virtualenv 习惯）不受影响 |

`.env` 被加入是因为本仓库在那里保存 `LLM_API_KEY`、`TELEGRAM_BOT_TOKEN`、`FEISHU_APP_SECRET`。

### 3.4 异常层次

| 异常 | 含义 | 给谁看 |
|---|---|---|
| `PathRefused(ValueError)` | 基类：路径不可用 | — |
| `PathEscapesWorkspace` | 解析到工作区外；消息中给出工作区根 | 通常是模型的失误，可纠正 |
| `PathIsSensitive` | 凭据/密钥路径；消息**不回显**解析后的位置 | 对操作员是安全事件 |

`read_file` 让 `PathRefused` 原样传播（不包成 `ToolArgumentError`），以保留子类名；注册表把它转成 `is_error=True` 的 Observation。

## 4. `read_file`

`omicsclaw/tools/builtin/read.py`，由 `read_tool(workspace=None, *, environment=None)` 构造成一个 `FunctionTool`。策略 `LOW` / `AUTO` / `read_only=True` / `concurrency_safe=True` / `allowed_in_background=True`：读不会造成不可逆后果，边界由 `Workspace` 保证，审批只是摩擦。

### 4.1 参数与两种模式

| 参数 | 类型 | 说明 |
|---|---|---|
| `path` | string，必需 | 相对工作区根，如 `results/summary.csv` |
| `start_line` | integer | 设置即进入**行模式**，1 起、包含 |
| `end_line` | integer | 需要 `start_line`；省略则读到文件尾，最多 500 行 |
| `offset` | integer | **字节模式**起始偏移（字节，不是行号），默认 0 |
| `limit` | integer | 字节模式最大字节数，默认 8192，钳制到 100,000 |

schema 设置 `additionalProperties: false`，多余参数变成可纠正的 `input.foo is not allowed`。

**行模式**（推荐）：每行渲染为 `numbered_line()` 的 `%6d\t内容\n`；超过 `MAX_LINES = 500` 截断并提示 `To continue, call again with start_line=N`；`start_line` 超过文件末尾时返回普通文本 `[start_line=N is past the end of ..., which has M lines]`；单行超过 `MAX_LINE_CHARS = 512 * 1024` 字符被拒，并指引改用字节模式。`start_line < 1`、`end_line < start_line`、只给 `end_line` 都是 `ToolArgumentError`。

**字节模式**（回退）：默认窗口 `MAX_READ_BYTES = 8192`，上限 `MAX_LIMIT_BYTES = 100_000`；多读 1 字节以判断是否截断；以 `errors="replace"` 解码；截断时附注已读字节数、文件总字节数和续读用的 `offset`；`offset` 超过文件尾返回说明文本而非错误。

### 4.2 与 `edit_file` 的契约

行号前缀 `%6d\t` 是跨工具契约：工具描述里明确警告，把 `read_file` 的输出粘回 `edit_file` 的 `source_text` 时必须去掉行号和其后的 tab。`edit_file` 另有兜底（见 6.3）。`LINE_NUMBER_WIDTH = 6` 被 `edit.py` 导入以构造反向正则，两边不会漂移。

### 4.3 错误分类

判定标准是"模型下一步应当改什么"：路径不存在、不是普通文件 → 抛出（`is_error`）；文件存在但为空 → 普通输出。文件系统 `OSError`（如 `ENAMETOOLONG`）被改写成带操作系统原因的句子再抛出，不把裸 traceback 片段交给模型。

### 4.4 并发

`_read` 先解析路径，再在 `read_lock(resolved)` 内读取 —— 锁的键必须是解析后的路径。

## 5. `write_file`

`omicsclaw/tools/builtin/write.py`，`WriteTool(workspace=None, *, environment=None)`，手写 `Tool` Protocol（审批提示需要原始 payload）。策略 `HIGH` / `ASK` / `prompts_for_itself=True` / `concurrency_safe=False` / `writes_workspace=True`。

| 属性 | 值 |
|---|---|
| 参数 | `path`（必需）、`content`（必需，空串写空文件） |
| 语义 | **覆盖**：不追加、不合并、不备份；描述中明确告知模型 |
| 父目录 | 自动创建，`DIRECTORY_MODE = 0o755`（仅作用于最末级目录，中间目录按 umask） |
| 新文件权限 | `FILE_MODE = 0o644`，用 `os.open(..., O_WRONLY \| O_CREAT \| O_TRUNC, FILE_MODE)` 真正落实；覆盖已有文件时保留原权限 |
| 返回 | `Wrote <resolved> with N bytes` 或 `Replaced <resolved> with N bytes` |

执行顺序即设计：**解码 → 校验 → 解析 → 审批 → 写入**。

- 审批之前没有任何持久副作用（解析只读不建），拒绝后不留文件；先解析再审批，是为了让提示显示真实落点，而不是模型写的字符串。
- 审批理由由 `_reason()` 生成：新文件为 `create <path> and write N bytes`；已有文件为 `REPLACE the existing <path> (M bytes) with N bytes; its current contents are not recoverable`。
- 写锁在审批**之后**才拿：人的思考时间无上限，不能长时间独占路径锁挡住其他工具（包括用户在决定时正在看的 `read_file`）。
- 锁内再次判断文件是否存在，决定返回 `Wrote` 还是 `Replaced`。
- 只捕获 `OSError` 并改写为 `ToolArgumentError`（`cannot write '<path>': <reason>. Send a different path inside the workspace`）；`CancelledError` 原样穿透。

符号链接陷阱：若工作区内的 `out -> /tmp` 被 `mkdir(parents=True)` 直接使用，会在检查前就在 `/tmp` 下建目录。`write_file` 总是先 `Workspace.resolve()` 再 `mkdir`，`tests/tools/test_write.py` 断言的是"外部目录依然为空"，而不只是"工具返回了错误"。

## 6. `edit_file`

`omicsclaw/tools/builtin/edit.py`，`EditTool(workspace=None, *, environment=None)`，策略与 `write_file` 相同。

| 参数 | 说明 |
|---|---|
| `path` | 必须已存在（新建文件用 `write_file`） |
| `source_text` | 要替换的原文，须在文件中**恰好出现一次** |
| `target_text` | 替换文本；空串表示删除 |

### 6.1 执行顺序：读 → 匹配 → 审批 → 重读 → 写

```
async with read_lock(resolved):  original = _get()
outcome = plan_edit(original, source, target)        # 纯函数，不碰文件系统
await require_approval(..., reason=diff 与匹配级别)
async with write_lock(resolved):
    if _get() != original: 拒绝（审批期间文件被改动）
    if outcome.content == original: 返回"无变化"（幂等，不写）
    _put(outcome.content)
return build_summary(...)
```

审批展示的是 **diff 而不是参数**，并注明匹配级别；diff 超过 `MAX_SUMMARY_LINES = 20` 行时只报增删行数。审批通过的是"针对某份特定字节的 diff"，所以在写锁内重读，发现变化就拒绝。

### 6.2 四级匹配（`replace_once`）

| 级别 | 常量 | 规则 |
|---|---|---|
| L1 | `MATCH_EXACT = 1` | 原样出现一次；出现多次直接报歧义 |
| L2 | `MATCH_NEWLINE = 2` | `\r\n` → `\n` 后匹配，写回时恢复 CRLF 风格 |
| L3 | `MATCH_TRIMMED = 3` | 去掉 anchor 首尾空白后匹配 |
| L4 | `MATCH_LINE_BY_LINE = 4` | 逐行去缩进滑窗匹配，并把 `target_text` 重新缩进到原块位置 |

只有 L1 被报告为精确匹配；L2–L4 为模糊匹配，结果提示模型重新读取检查缩进（对 Python 脚本而言，这是修复与 `IndentationError` 的区别）。L2、L3 的歧义不直接报错而是落到下一级，唯一性校验在最终胜出的那一级成立。

### 6.3 额外的保护

- 空 anchor 或全空白 anchor 按名拒绝（`_reject_empty`）——否则 L4 会匹配每一个空行。
- 所有级别都未找到（`AnchorNotFound`）时，若 `source_text` 的**每一个**非空行都带 `read_file` 行号前缀，则去掉前缀（`strip_line_numbers`）再试一次，此时 `target_text` 也同样去前缀；只有部分行带前缀的视为 TSV 数据，不做处理。
- 文件必须是合法 UTF-8；否则拒绝编辑（替换字符写回会破坏原字节）。
- 本地写入使用同目录临时文件（`tempfile.mkstemp(prefix=".<name>.", suffix=".tmp")`）+ `os.chmod` 保留原权限 + `os.replace` 原子替换；失败时原文件完好、临时文件被删除。

## 7. 路径锁：`_pathlock.py`

屏障（`EngineConfig.serialize_unsafe_tools`）只能排序一个回合内的调用；两个 Channel 会话、子 agent、后台运行各自驱动自己的调度，会同时触碰同一批文件。`_pathlock.py` 是这些场景下的唯一防线。

| 要点 | 说明 |
|---|---|
| 进程级唯一表 | `PATH_LOCKS = PathLockTable()`；工具只经 `read_lock(path)` / `write_lock(path)` 使用 |
| 键 | `Path(path).resolve()`，别名与符号链接归为一把锁 |
| 语义 | 读写锁：多读共享、写独占；**写者优先**，写者排队时新读者等待 |
| 原语 | `asyncio.Condition`，等待者挂起 Task 并把控制权还给事件循环 |
| 引用计数 | 覆盖持有与等待，最后一个离开即删除条目；表的大小等于在途工作量 |
| 不可重入 | 同一 Task 先读锁再写锁会死锁；读-改-写应当只持一把写锁 |
| 假设 | 每进程一个事件循环（Desktop 的 uvicorn、Channel runner 均如此） |

使用方式：`read_file` 全程读锁；`write_file` 审批后写锁；`edit_file` 读锁读取、审批后写锁内重读并写入。`tests/tools/test_pathlock.py` 覆盖读写互斥、写者优先、别名归并、排队中被取消不留条目、事件循环不被阻塞，以及“同回合由屏障排序、跨回合只能靠路径锁”的对照。

## 8. `.omicsclaw/` 工作区状态目录

`omicsclaw/entry/config.py` 中 `STATE_DIRNAME = ".omicsclaw"`，`AppConfig.state_dir()` 返回 `<workspace>/.omicsclaw`（可能尚不存在，各写入方按需创建）。

```
<workspace>/
├── .mcp.json                          # MCP 配置（mcp_config_path() 默认值；可用 OMICSCLAW_MCP_CONFIG 改）
├── skills/                            # skill 目录（skills_root() 默认值；可用 OMICSCLAW_SKILLS_DIR 改）
└── .omicsclaw/
    ├── settings.json                  # 权限规则文件（permission_rules_path()；OMICSCLAW_PERMISSION_RULES 可改到别处）
    ├── memory.db                      # SQLite：会话消息 + 长期记忆（memory 开启时）
    ├── MEMORY.md                      # 长期记忆的渲染摘要，供系统提示词的记忆段读取
    ├── plans/
    │   ├── <session>.json             # 计划的权威存储，会话恢复时读回
    │   └── <session>.md               # 人类可读副本，从不读回
    ├── tool_results/
    │   └── <session>/
    │       └── <call-id>-<sha256前16位>.txt   # 被卸载的工具输出（目录 0700，文件 0600）
    ├── compaction_records/
    │   └── <session>.jsonl            # 每次压缩一条记录，只追加
    └── agents/                        # 子 agent 定义文件（*.md），只读取不创建
```

| 路径 | 常量 / 方法 | 写入方 |
|---|---|---|
| `settings.json` | `AppConfig.permission_rules_path()` | 权限层 `RuleStore`；CLI 审批卡片上的 `a` 写入 `allow` 规则 |
| `memory.db` | `entry/memory.py` `MEMORY_DB_FILENAME`、`memory_db_path()` | `omicsclaw/memory/`（`OMICSCLAW_MEMORY=false` 时不打开） |
| `MEMORY.md` | `PRECIS_FILENAME`、`precis_path()` | `memory/precis.py` `Precis`（由 `entry/memory.py` 构造） |
| `plans/` | `AppConfig.plans_root()` | `planning/archive.py` `FilePlanArchive`，首次保存时才创建目录 |
| `tool_results/` | `entry/compaction.py` `TOOL_RESULTS_DIRNAME`、`offload_store()` | `memory/offload.py` `FileOffloadStore` |
| `compaction_records/` | `RECORDS_DIRNAME`、`compaction_log()` | `memory/compaction_log.py` `JsonlCompactionLog` |
| `agents/` | `AppConfig.agents_root()` | 人工放置；`subagent/loader.py` 读取 |

会话 id 在落盘前经 `safe_name()` 规整为单个可移植路径组件（非法字符替换为 `_` 并在有改动时追加短摘要；空串、`.`、`..` 变为默认值）。审计日志（`OMICSCLAW_AUDIT_LOG`）没有默认位置，只在显式配置时写到指定路径。

### 8.1 对 `.omicsclaw/` 与 `.env` 的保护

`Workspace` 本身**不**阻止访问 `.omicsclaw/`，它就在工作区内：`read_file` 可以（也需要）读回 `.omicsclaw/tool_results/...`。保护在权限层（`omicsclaw/permission/gate.py`）：

- `PROTECTED_DIRNAME = ".omicsclaw"`：能写入那里的工具就能写入 `allow` 规则，从而让权限门失效。因此一个**非 `read_only`** 工具、其写入类主参数（`command`、`path`、`file_path`、`destination` 等）中出现 `.omicsclaw`、`.env`（`DOTENV_NAME`，大小写不敏感）或规则文件路径时，**每次都询问**，任何规则、会话级授权都不能替它回答（`DecisionSource.PROTECTED`）。
- 这是文本检查，对运行时拼出的名字、shell glob 无能为力；对决意绕过的模型，真正的边界只有沙箱。

## 9. 各工具与沙箱的关系

- 三个文件工具都接受一个 `environment` 参数（`FileReadEnvironment` / `FileWriteEnvironment` / `FileEditEnvironment`，均为窄 Protocol）；`None` 表示本地文件系统。传入的路径是**已解析的宿主机路径**，实现需看到同一棵目录树。`write_file` 的实现必须自行创建父目录；`edit_file` 的读与写必须落在同一文件系统。
- 当前装配中，文件工具不传 `environment`，始终在宿主机上受 `Workspace` 约束；只有 `bash` 可能通过 `BashEnvironment` 进入 Docker 沙箱，沙箱把工作区挂载在相同路径上，所以两侧看到的是同一批文件。
- `bash` 没有路径参数也不做路径检查，`cd .. && cat ...` 不受 `Workspace` 限制；它的边界是审批、权限层危险命令模式与规则、以及沙箱。`bash` 的输出先写入系统临时目录中的 `omicsclaw-bash-*.log` 捕获文件，调用返回时删除。

## 10. 大输出：截断与卸载

### 10.1 第一道：工具自身的上限

| 工具 | 上限 |
|---|---|
| `bash` | `MAX_OUTPUT_CHARS = 16_000` 字符，保留头 `HEAD_CHARS`（1/3）+ 尾 `TAIL_CHARS`（2/3）——测试运行器的结论在末尾 |
| `read_file` | 字节模式默认 8,192 字节、最多 100,000；行模式最多 500 行 |
| `web_fetch` | 响应体 `MAX_BODY_BYTES = 1 MiB`，正文默认 8,000 字符、最多 32,000 |
| `memory_search` | `SEARCH_RESULT_MAX_BYTES = 4096` |

因此一次 `bash` 调用即使打印了整个 `adata.obs`，进入历史的也不会超过 16,000 字符。

### 10.2 第二道：压缩时卸载（context 层决定，memory 层落盘）

职责划分：

| 模块 | 负责 | 不负责 |
|---|---|---|
| `omicsclaw/context/offload.py` | **哪条消息该搬走、占位符写什么**：`Offloader`（阈值与预览参数）、`offload_messages()`、`offload_key()`、`render_placeholder()` / `parse_placeholder()`、`render_references()` / `parse_references()`、`OffloadStore` Protocol | 不碰文件系统 |
| `omicsclaw/memory/offload.py` | **字节写到哪**：`FileOffloadStore` 满足 `OffloadStore`，以 `<key>.txt` 形式原子写入 | 不决定是否卸载 |
| `omicsclaw/context/compaction.py` | 何时卸载：`compact()` 在压力高于 `NONE` 时先卸载可压缩头部中的大结果，重新评级后再决定是否摘要；`EMERGENCY` 时连最近的尾部也卸载 | — |
| `omicsclaw/entry/compaction.py` | 装配：`offload_store(config, session_id)` 指向 `.omicsclaw/tool_results/`，`reference_base=config.workspace`；`build_compactor()` 把 `Offloader(offload_store(...))` 交给 `ProgressiveCompactor` | — |

触发条件：

- `ProgressiveCompactor` 在每次模型调用前测量；压力低于 `AppConfig.compact_at`（默认 `Pressure.WARN`，`OMICSCLAW_COMPACT_AT`）时什么也不做。`ContextBudget` 的阈值为 `warn_at = 0.60`、`soft_at = 0.70`、`full_at = 0.80`、`emergency_at = 0.95`（相对可用 token 数）。
- 达到阈值后，只有 `Role.TOOL`、尚未是占位符、估算 token 数超过 `Offloader.min_tokens = 1000` 的消息会被卸载。
- 卸载只作用于**已读过的历史**（可压缩头部），最近的尾部原样保留，除非达到 `EMERGENCY`。一条刚产生的大输出，模型总能先完整看到一次。

占位符格式（`render_placeholder`，预览默认 `preview_lines = 10` 行、最多 `preview_chars = 800` 字符）：

```
[offloaded: .omicsclaw/tool_results/<session>/<key>.txt | 2310 lines / 15872 chars]
Preview (first 10 of 2310 lines):
...前 10 行...
... full output saved to .omicsclaw/tool_results/<session>/<key>.txt; read it with read_file
```

引用是**工作区相对的 POSIX 路径**，模型直接把它交给 `read_file`（行模式或字节模式分页）即可读回；由于 `read_file` 是 `read_only`，读取 `.omicsclaw/` 不会触发权限门的保护检查。

`FileOffloadStore` 细节：

- 键由 `offload_key(tool_call_id, content)` 生成：规整后的 call id（最多 64 字符）+ `-` + 内容 SHA-256 前 16 位；键跟随内容，同一 call id 的不同内容不会共用文件，没有 call id 也有键。
- 键必须匹配 `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`，否则 `ValueError`。
- 已写过的键不再写（内存集合 + 磁盘存在性双重检查），同一结果在多次压缩中只落盘一次。
- 目录 `0700`、文件 `0600`；临时文件 + `os.replace` 原子写入；写入在 `asyncio.to_thread` 中执行。
- 存储失败时该消息保持原样，失败原因记入 `OffloadOutcome.failures` / 压缩记录的 advisories，不中断回合。

摘要消息会携带 `## Offloaded References` 块（`REFERENCES_HEADING`，最多 `MAX_REFERENCES = 50` 条，保留最新），使被摘要掉的历史中曾卸载的文件在压缩后仍可被找到；`collect_references()` 从占位符和旧的引用块中收集它们。每次压缩的记录（含卸载条目）追加到 `.omicsclaw/compaction_records/<session>.jsonl`。

## 11. 配置参数

| 参数 | 位置 | 默认值 | 说明 |
|---|---|---|---|
| `workspace` | `AppConfig`，`--workspace` / `OMICSCLAW_WORKSPACE` | 当前目录 | 文件工具的沙箱根，也是 `.omicsclaw/` 的父目录 |
| `permission_rules` | `AppConfig`，`OMICSCLAW_PERMISSION_RULES` | `<workspace>/.omicsclaw/settings.json` | 权限规则文件 |
| `memory` | `AppConfig`，`OMICSCLAW_MEMORY` | `True` | 是否打开 `memory.db` |
| `compact_at` | `AppConfig`，`OMICSCLAW_COMPACT_AT` | `Pressure.WARN` | 触发压缩（含卸载）的最低压力档 |
| `MAX_READ_BYTES` / `MAX_LIMIT_BYTES` | `read.py` | 8,192 / 100,000 | 字节模式默认窗口与上限 |
| `MAX_LINES` / `MAX_LINE_CHARS` | `read.py` | 500 / 524,288 | 行模式行数上限、单行字符上限 |
| `DIRECTORY_MODE` / `FILE_MODE` | `write.py` | `0o755` / `0o644` | 新建目录/文件权限 |
| `CONTEXT_LINES` / `MAX_SUMMARY_LINES` | `edit.py` | 3 / 20 | 摘要 diff 的上下文行数、改动行数上限 |
| `Offloader.min_tokens` | `context/offload.py` | 1,000 | 超过才卸载 |
| `Offloader.preview_lines` / `preview_chars` | `context/offload.py` | 10 / 800 | 占位符预览 |
| `MAX_REFERENCES` | `context/offload.py` | 50 | 引用块最多条目 |

## 12. 已知限制

- **卸载文件没有回收**：`FileOffloadStore.purge()` 与 `JsonlCompactionLog.purge()` 存在且有测试，但生产代码没有调用方；`memory/sessions.py` 的 `delete()` 只删数据库行，不级联清理 `tool_results/<session>/`、`compaction_records/`、`plans/`。长期运行的工作区会累积这些文件。
- **行模式单行上限不是响应总量上限**：500 行、每行接近 512 KiB 仍可能产生巨大回复。
- **`except OSError` 会连带捕获 `TimeoutError`**：注入的 `Environment` 若以 `asyncio.wait_for` 限时，瞬时基础设施故障会被报告为"换一个路径"。该约定在 `read` / `write` / `edit` / `bash` 中一致，需要统一修改。
- **`edit_file` 没有 `replace_all`**：多处相同文本都要修改时只能用 `write_file` 重写整个文件。
- **`write_file` 使用 `O_TRUNC` 直接覆盖**：与 `edit_file` 不同，它不走临时文件 + `os.replace`，写到一半失败（如 ENOSPC）时目标文件可能已被截断。
- **`DIRECTORY_MODE` 只作用于最末级目录**，中间目录按 umask 创建；在常见的 `022` umask 下结果一致。
- **`FileReadEnvironment` 整文件跨接缝传输**：通过环境读取时无法流式读行，单行上限在字节已到达后才生效。当前装配不给文件工具注入环境，所以只是未来隔离步骤会遇到的问题。
- **`resolve_workspace` 放在 `read.py`**，被 `write.py` / `edit.py` 导入；其 docstring 自己承认应搬到 `_workspace.py`。
- **`.omicsclaw/` 保护是文本匹配**：运行时拼接的文件名、shell glob 不在其视野内；`Workspace` 本身不区分 `.omicsclaw/` 与普通工作区文件。
- **`bash` 不受 `Workspace` 约束**：没有沙箱时，经批准的 shell 命令可以读写工作区外的任何位置。

## 13. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/tools/_workspace.py` | `Workspace`、`is_sensitive`、`CREDENTIAL_PATHS`、`SECRET_FILENAMES`、`WORKSPACE_KEY`、`PathRefused` 及子类 |
| `omicsclaw/tools/_pathlock.py` | `PathLockTable`、`PATH_LOCKS`、`read_lock`、`write_lock` |
| `omicsclaw/tools/builtin/read.py` | `read_file`：`read_tool`、`resolve_workspace`、`numbered_line`、`FileReadEnvironment` |
| `omicsclaw/tools/builtin/write.py` | `write_file`：`WriteTool`、`FileWriteEnvironment`、`DIRECTORY_MODE`、`FILE_MODE` |
| `omicsclaw/tools/builtin/edit.py` | `edit_file`：`EditTool`、`plan_edit`、`replace_once`、`strip_line_numbers`、`FileEditEnvironment` |
| `omicsclaw/context/offload.py` | 卸载策略与占位符格式：`Offloader`、`offload_messages`、`OffloadStore` |
| `omicsclaw/context/compaction.py` | `compact()`：何时卸载、`collect_references` |
| `omicsclaw/memory/offload.py` | `FileOffloadStore`、`safe_name` |
| `omicsclaw/memory/compaction_log.py` | `JsonlCompactionLog` |
| `omicsclaw/entry/compaction.py` | `offload_store`、`compaction_log`、`build_compactor`、`TOOL_RESULTS_DIRNAME`、`RECORDS_DIRNAME` |
| `omicsclaw/entry/config.py` | `STATE_DIRNAME`、`AppConfig.state_dir()` / `permission_rules_path()` / `plans_root()` / `agents_root()` |
| `omicsclaw/entry/memory.py` | `memory_db_path`、`precis_path` |
| `omicsclaw/planning/archive.py` | `FilePlanArchive` |
| `omicsclaw/permission/gate.py` | `PROTECTED_DIRNAME`、`DOTENV_NAME`、`touches_protected` |
| `omicsclaw/entry/assembly.py` | `foundation_tools()`：唯一构造 `Workspace` 的地方 |
| `tests/tools/test_workspace.py`、`test_read.py`、`test_write.py`、`test_edit.py`、`test_pathlock.py` | 边界、三个文件工具、路径锁测试 |
| `tests/context/test_offload.py`、`tests/memory/test_compaction_files.py` | 卸载策略与落盘测试 |
