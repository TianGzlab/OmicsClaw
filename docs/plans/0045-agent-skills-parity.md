# 0045 — Agent Skills 模块系统对齐与旧 skill 系统清除

## 背景

`omicsclaw/skills/`（plan 0032）已经是一个成熟的 Progressive Disclosure
加载器，并在 `omicsclaw/entry/assembly.py` 里接线完毕：`build_skill_index`
扫一次盘，`foundation_tools` 挂 `use_skill`，`_skills_section` 把索引写进
system prompt。README 里"nothing wired to production"是 plan 0032 当时的状态，
已经过时。

真正的缺口在两处：

1. **harness9 §4.2 的第二条触发通路缺失。** harness9 的 Agent Skills 设计有
   两条路：LLM 通过 `use_skill` 自主选取（工具调用），以及用户在 CLI 里直接
   输入 `/skill-name` 绕过 LLM 判断。OmicsClaw 只有前者。
2. **skills 语料和工具链仍属于旧框架。** 96 个 `SKILL.md` 的头部由
   `skill.yaml` 经 `scripts/generate_skill_md.py` 生成，携带新 loader 一个都
   不读的 `version` / `author` / `license` / `emoji` / `requires`；而整条创作
   链（21 个脚本）import 已删除的 `omicsclaw.skill`（单数），早已无法运行。

本计划按用户决定：采用最通用的 Agent Skills 范式 —— **每个 skill 是一个独立
子目录，`SKILL.md` 是唯一元数据来源** —— 并把旧 skill 系统的残留全部删除。

## 与 harness9 的差异核对

| harness9 特性 | 本次之前 | 本次之后 |
|---|---|---|
| Progressive Disclosure（索引进 prompt，正文按需取） | 已有，且更强 | 不变 |
| `use_skill` 工具 + 可自愈的错误信息 | 已有（difflib 近似名） | 不变 |
| 目录不存在静默为空 / 缺字段跳过 | 已有（跳过记为数据） | 不变 |
| frontmatter `trigger` 字段 | 解析了但 96 个全空、无人读 | 81 个填充，喂给 `/skills` 搜索 |
| **§4.2 `/skill-name [args]` 直通** | 无 | `resolve_slash` + REPL 分发 |
| **Tab 补全 skill 名** | 补的是已退役的 `/run <skill>` | 补 `/skill-name`，与命令同列 |
| 子代理 prompt 预载 skills 索引 | 新栈无 sub-agent 系统 | 不适用 |

OmicsClaw 在三处**超出** harness9，本次保留：递归扫描（harness9 的一层扫描
在本语料只能找到 96 个里的 2 个）、真 YAML 子集解析器（harness9 的逐行解析会
丢掉 description 的 "Skip when" 后半句）、`use_skill` 额外返回 skill 目录。

## 改动

### 一、模块系统 `omicsclaw/skills/`

保持叶子层约束不变（只允许 import `omicsclaw.schema` 与 `omicsclaw.tools`，
由 `test_skills_is_a_leaf_layer.py` 在子进程里验证）。

- `skill.py`：新增 `Skill.triggers`，把 `trigger` 按逗号切成元组。
- `loader.py`：`trigger` 支持标量与块序列两种写法，统一成一个展示字符串。
- `index.py`：新增 `SkillIndex.search(query)`，在 name / domain / tags /
  triggers 上做大小写无关的子串匹配，保持索引顺序、每个 skill 至多出现一次。
- `invocation.py`（新）：`slash_token` / `resolve_slash` / `complete_slash` /
  `SkillInvocation.expand`。全部是纯函数，不碰文件系统 —— 读盘和它可能抛出的
  异常留在调用方手里。`slash_token` 只做解析、不查表，所以调用方能区分"用户
  点了个名但没人应答"和"这行根本不是名字"；它同时把首 token 含分隔符的行判为
  非名字，因为在组学工作区里以 `/` 开头的一行同样可能是粘贴进来的绝对路径。
- `resolve_slash` 精确匹配，**只在大小写上折叠**，且折叠出两个候选时拒绝。
  这不是猜测：命令表和 `complete_slash` 都对大小写不敏感，补全提供了一个
  分发器又拒绝的名字本身就是缺陷。`SkillIndex.get` 保持严格精确 —— 模型是从
  发给它的索引里抄名字的，它拼错时的 "did you mean" 回复正是教它拼对的东西。

`trigger` 只服务于人的检索，**不做自动触发**。这一点与 harness9 的
"documentation only, not used for automatic matching" 一致，且在 docstring
和三份文档里都写明了。

### 二、CLI 接线 `omicsclaw/entry/cli/`

- `_repl.py`：`_dispatch` 在命令目录未命中后、落到模型之前，先问 skill 索引。
  **命令优先**，所以 skill 不会遮蔽 `/help`。两张表都不认的 `/name` 被**当场
  报告**（附 `close_names` 给出的近似名），而不是发给模型 —— 把拼错的技能名
  丢给模型，代价是一次往返换来一段答非所问的散文，用户还学不到自己拼错了。
  `_skills` 改用 `search()` 并按 domain 分组。
- `_skill_invocation` 捕获 `(OSError, UnicodeDecodeError)` 而非只捕获前者。
  `UnicodeDecodeError` 是 `ValueError` 不是 `OSError`，而这条通路不像
  `use_skill` 那样有工具注册表的 `except Exception` 兜底 —— 漏掉它会让一个
  被改坏编码的 SKILL.md 直接杀死整个 REPL 会话。loader 早就成对捕获这两个。
- `_input.py`：`build_completer` / `open_prompt_source` 改为接收 `SkillIndex`
  而非 `Sequence[str]`，补全规则统一由 `complete_slash` 提供。命令与 skill 在
  同一个分支里输出，重名时命令胜出。
- `_slash_command_support.py`：删除 `complete_run_skill_names` —— 它补的
  `/run` 是已删除的 skill runner 的命令，补出来也只会得到"not available in
  this build"。

### 三、96 个 SKILL.md 语料

- 从 `skill.yaml` 的 `summary.trigger_keywords` 生成 `trigger:`（删除
  orchestrator 两个之后剩 81 个有，13 个 singlecell skill 原本就没有关键词，
  留空）。
- 删除 `version` / `author` / `license` / `emoji` / `requires` 五个键。
- `name` / `description` / `tags` 的原始行**逐字保留**（不重新折行），所以
  diff 只包含真实的增删。
- 把 `skill.yaml` 的 `deps.python` 搬进正文的 `## Dependencies` 段。这是
  `skill.yaml` 里唯一没有冗余的信息：输出清单在正文中的覆盖率是 100%，而依赖
  只有 21%，36 个 skill 一个都没提。
- **已退役 CLI 的调用形式全部换成真实脚本路径**，两轮共 756 处、横跨 231 个
  文件：先是 160 处 `oc run <skill>`（47 个文件），审核后又发现同一类谎言的另
  一种写法 `python omicsclaw.py run <skill>` 还有 596 处（184 个文件，含
  `docs/domains/*.mdx`）—— 几乎每个 SKILL.md 的 `## Key CLI` 都是它。其中约
  20 个技能名在索引里根本不存在（`spatial-preprocessing`、`met-annotate`、
  `peptide-id`、`sc-preprocess` 一类 v1 别名，别名表本身存在 `skill.yaml` 里，
  已随之删除），即这些文档在旧 CLI 下就已经是错的，一并映射到了真名。
- 清除 96 个 SKILL.md 正文里的 `<!-- AUTO-GENERATED from skill.yaml … Regenerate:
  python scripts/generate_skill_md.py -->`，以及 97 个 `references/parameters.md`
  的同类声明 —— 脚本和 `skill.yaml` 都已删除，按它操作只会得到"文件不存在"。

### 四、删除 `orchestrator` 与 `omics-skill-builder`（96 → 94，8 → 7 域）

这两个 skill 的脚本同样 import 已删除的 `omicsclaw.skill` 而崩溃，但它们仍在
prompt 索引里叫模型去跑 —— 这是 Agent Skills 系统本身的活缺陷。更根本的是，
**它们的职责已经是框架自带的能力**：

- `orchestrator`（查询 → skill 路由）= prompt 里的 skill 索引 + `use_skill`。
  把路由再包一层 skill，等于让模型先选一个 skill 来帮它选 skill。
- `omics-skill-builder`（脚手架）= `cp -r templates/skill skills/<domain>/<name>`。

整个 `skills/orchestrator/` 目录删除。连带处理：

- `literature` 与 `consensus-interpret` 的 description 里 "use orchestrator"
  的 skip 子句改写 —— 否则它们会指向一个不存在的 skill。
- `skills/orchestrator/` 是全语料**唯一**「既是 skill 又是 skill 父目录」的
  案例，也就是 loader「递归要越过 SKILL.md 继续下降」这条规则在真实语料里的
  唯一见证。`test_real_corpus.py` 里那条断言没有被删掉，而是**反转为断言不存在**
  并写明缘由：规则本身仍由 `test_loader.py` 的合成用例守着，日后若有人再加嵌套
  skill，这条测试会红，真实语料的覆盖可以被恢复而不是被重新发现。
- CLAUDE.md 路由表、7 个 INDEX.md、AGENTS.md、README、README_zh-CN、llms.txt、
  CONTRIBUTING.md、mint.json、`docs/domains/orchestrator.mdx` 同步更新。

### 五、删除旧 skill 系统

- `scripts/` 下 21 个 skill/catalogue 脚本，`scripts/` 从 30 个文件降到 9 个。
- 96 个 `skill.yaml`，以及 `skills/catalog.json`、`skills/skill_dag.json`、
  `skills/skill_dag_reviews.yaml`。
- `omicsclaw/diagnostics.py` —— 它本身已经 import 不了（依赖三个已删包），
  同时是 `catalog.json` 的唯一引用点。
- 11 个只为测这些脚本、或以旧 skill 系统本身为被测对象的测试文件。
- Makefile 的 `catalog` / `audit-requires` / `check-drift` / `eval-snapshot`
  目标，换成一个 `skill-index`。
- CI `core-test` job 里 ~20 步旧 skill 闸门。这个 job 引用的测试文件里有 13 个
  在更早的重构里就已删除，即它在本次改动之前就是红的。

### 六、INDEX.md 改由测试守护

8 个 `skills/<domain>/INDEX.md` 在本次改动**之前**就已陈旧：`bulkrna-cosinor-rhythm`
整条缺失，7 个 skill 的 triggers 被截断。原因就是生成它的
`generate_domain_index.py` 早已不能运行。

不再补一个生成器，改成黄金文件测试
`tests/skills/test_domain_index_is_current.py`：它从 loader 重建 `## Skills`
段和计数行并断言相等，漂移直接让 CI 红；`OMICSCLAW_WRITE_SKILL_INDEX=1` 时
写回。标题、domain key、数据类型、那段说明散文仍然是手写的，测试不碰。

一个生成器没人跑，就是 INDEX.md 陈旧的原因本身 —— 所以这里要的是一个会失败的
测试，而不是一个会被遗忘的脚本。

## 验证

- 五个套件合计 **2576 passed / 2 skipped / 0 failed**
  （`tests/skills` `tests/entry` `tests/launch` `tests/context` `tests/tools`）。
- `tests/tools/test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget`
  在过程中间歇性失败，经 `git stash` 对照为既有的 localhost socket 计时问题，
  与本次改动无关；最终一轮它通过了。
- 语料侧：`load_skills('skills')` 得到 **94 indexed / 0 skipped**，81 个带
  trigger；`test_real_corpus.py` 逐键与 PyYAML 比对全部通过；prompt 索引
  29,277 字符（≈8.4k token），正文合计 433,750 字符（≈124k token）—— 索引
  只占正文的 1/15，这就是 Progressive Disclosure 买到的东西。
- `tests/` 全量收集错误从 57 降到 55。剩下的 55 个属于 autoagent / remote /
  runtime-consensus 等其它遗留子系统，不在本计划范围内。

## 两轮独立审核

实现完成后由两个独立子 agent 审核，结论已全部处理：

- **实现审核**：对 `resolve_slash` / `expand` / 命令优先级 / 补全去重做了变异
  测试（改坏 → 确认变红 → 还原）。发现三条真问题，均已修：`UnicodeDecodeError`
  漏捕获、96+97 个文件里的失效生成器声明、README 与本文三处数字写错
  （scripts 30→9 不是 →8；删除的测试是 11 个不是 10 个；`tests/skills` 是
  480 项不是 484 项）。它还指出 `resolve_slash` 严格区分大小写而补全不区分，
  这条被采纳为上面的折叠匹配。
- **harness9 对照审核**：核实核心特性已对齐，并指出一条本文对照表没写的行为
  分歧 —— harness9 在 `/skill-name` 指向不存在技能时报错且不调用模型，而当时
  的实现会静默发给模型。已按上面的 `_unknown_slash` 修正，并保留路径豁免。
  它对 `use_skill` 错误信息只给 5 个近似名、不给全名单的担忧**前提不成立**：
  `use_skill` 的挂载与 skills section 的注入由同一个 `skills_index is not OFF`
  条件把关（`assembly.py` 两处），所以工具存在时全量技能名必然在 prompt 里，
  compact 模式也仍然列名。此处不改。

## 已知遗留（本计划不处理）

- `omicsclaw/remote/` 整包已死：import `omicsclaw.control`、
  `omicsclaw.skill.execution`、`omicsclaw.skill.resource_scheduler` 等已删模块，
  且挂载在已退役的 `oc desktop-server` 上。
- `tests/` 里 55 个收集错误对应的遗留测试。
- 22 个 skill 的 `result.json` 仍写 `replot` 提示，指向已不存在的命令。
- 本计划实施期间另有会话在同一工作树上推进 plan 0027（`engine.exchange` /
  `PromptSource` / `Conversation`），其中间态一度让 `tests/entry` 出现 73 个
  失败；该工作落定后复测为 0 失败。本文的验证数字取自其落定之后。
