# 0032 —— Skill 加载器（`omicsclaw/skills/`）

> 重建的第 5.5 步。上一步（plan 0030）交付了 `omicsclaw/context/`：
> Section 进、一条 system prompt 出。它留下的是**槽位**——
> `Section(key="skills", …)` 的 `source` 该由谁来填，0030 §5.1 明确写了
> 「渲染器在层外」。本步把那个渲染器建出来。
>
> 对标物：harness9 `internal/skills/`（4 个文件、190 行产品代码、
> 338 行测试）与 `internal/context/builder.go:113-119` 的注入点。

## 1. 为什么需要它

当前 prompt composer 的三层结构里：

1. **极简内核** —— 引擎里硬编码的身份与交互模式；
2. **工作区守则** —— `AGENTS.md`，`text_from_file` 已经能读；
3. **技能外挂** —— **没有加载器**。

第 3 层今天只能靠组装根手写一个 `lambda: open("...").read()`。本仓库有
**96 份 `SKILL.md`**（`find skills -name SKILL.md`），正文合计 437 KB
（≈125k token）。没有加载器 = 要么不注入（模型不知道有技能），要么全量
注入（一条 prompt 撑爆窗口）。Progressive Disclosure 需要一个索引层。

plan 0031 §12-1 的 owner 裁定是「skill 整体预留，工具与索引段都不接」，
理由是「当前项目下的 skill 我还得重新设计和迁移」。本步**不推翻那条裁
定**：本步交付的是一个**读 `SKILL.md` 目录树的通用加载器**，它对技能内
容不做任何假设，因此未来 skill 怎么重新设计都不影响它。裁定针对的是
「要不要把今天这批 skill 接进 prompt」，那仍然是组装根（entry 层）的
决定——本步只是把「接」这个动作从一个不存在的能力变成一行代码。

## 2. 位置与依赖方向

```
omicsclaw/
├── schema/    ← skills 依赖（ToolDefinition）
├── tools/     ← skills 依赖（ToolPolicy / FunctionTool）
├── context/   ← 不依赖 skills，skills 也不依赖它
└── skills/    ← 本步
```

**`skills`（复数）不是 `skill`（单数）。** `omicsclaw/skill/` 是旧架构
的 40 个模块（registry / orchestration / evolution_governance …），本包
**一行都不 import 它**，名字差一个字母是真实风险，因此分层探针里
`omicsclaw.skill` 进禁止名单，并且有子进程行为探针兜底——照
`FRAMEWORK-REBUILD.md:296-300` 的要求，抄的是**修好的那版**
（`tests/tools/test_tools_is_a_leaf_layer.py`），不是引擎旁边那版弱的。

白名单是 `omicsclaw.schema` / `omicsclaw.tools` / `omicsclaw.skills`
三项。为什么允许 `omicsclaw.tools`：`use_skill` 要声明自己的
`ToolPolicy`，而 `builtin/read.py:340-368` 已经把「策略声明在工具上、不
靠默认值」立成了本仓库的约定——`ToolPolicy()` 默认是 `HIGH`+`ASK`，漏
声明会让一个只读工具每次加载技能都弹审批。harness9 的 `skills` 包只
import `schema`，是因为它的权限系统在另一个包里；这条偏离是本仓库的约
定，不是疏忽。

**不依赖 `omicsclaw.context`。** 本包只提供 `() -> str` 的可调用对象，
组装根写 `Section("skills", "## 可用 Skills", index.prompt_body)`。
反过来 `context` 也不认识 `skills`——两个叶子，靠组装根接。

## 3. harness9 特性对照

| harness9 | 位置 | 本步 |
|---|---|---|
| `Skill{Name,Description,Trigger,filePath}` | `skill.go:14-21` | ✅ `Skill`，加 `domain` / `directory` |
| `parseFrontmatter` | `skill.go:26-58` | ✅ 扩写，见 §5 |
| `LoadSkills(dir)` 扫描子目录 | `loader.go:30-66` | ✅ 改为**递归**，见 §4-1 |
| 目录不存在 → 空 Index，不报错 | `loader.go:32-34` | ✅ 照搬（零配置可运行） |
| 缺 `SKILL.md` / 缺必填字段 → 跳过 | `loader.go:47-58` | ✅ 语义照搬，**日志改成数据**，见 §4-3 |
| `Index.IsEmpty()` | `index.go:20-22` | ✅ `SkillIndex.is_empty` |
| `Index.Summary()` = `- name: desc` | `index.go:25-34` | ✅ `summary()`，另加 `domain_summary()`，见 §4-2 |
| `Index.GetFullContent(name)` 懒加载正文 | `index.go:38-52` | ✅ `get_full_content(name)` |
| 未找到时返回可用名列表供 LLM 自愈 | `index.go:51` | ✅ 改成**近似匹配 + 总数**，见 §4-4 |
| `Index.Names()` 返回新切片 | `index.go:56-62` | ✅ `names()` 返回 `tuple` |
| `UseSkillTool`（结构化满足工具接口） | `use_skill_tool.go` | ✅ `use_skill_tool(index)` → `FunctionTool` |
| 参数解析失败 / 空名 → 错误 | `use_skill_tool.go:52-58` | ✅ `FunctionTool` 的 schema 校验 + `ToolArgumentError` |
| builder 注入「## 可用 Skills + 用法说明 + 摘要」 | `builder.go:113-119` | ✅ `prompt_body()`，空 Index 返回 `""` 让整段消失 |
| `filePath` 未导出，只能经 Index 访问 | `skill.go:20` | ✅ `Skill.path` 只读属性 + 名字查表，见 §6 |

## 4. 四处偏离，每处都有本仓库的理由

### 4-1 递归扫描，而不是一层子目录

harness9 约定 `skills/<name>/SKILL.md`。本仓库实测三种深度共存：

| 深度 | 数量 | 例 |
|---|---|---|
| `skills/<skill>/SKILL.md` | 2 | `skills/literature/` |
| `skills/<domain>/<skill>/SKILL.md` | 59 | `skills/spatial/spatial-de/` |
| `skills/<domain>/<group>/<skill>/SKILL.md` | 35 | `skills/singlecell/scrna/sc-de/` |

照搬一层扫描会加载到 **2 个**技能。所以递归走。`domain` = 相对根路径的
第一段。

> **实现阶段推翻了原稿的剪枝规则。** 原稿写的是「遇到 `SKILL.md` 就不
> 再往下走」，理由是 `references/` 里万一有一份 `SKILL.md` 应当算资料
> 而不是技能。实测把 96 个加载成 **95** 个：`skills/orchestrator/` 既
> 是一个技能（自己有 `SKILL.md`），又是 `omics-skill-builder` 的父目录，
> 剪枝把后者吃掉了。改成**始终向下走**。假想的 `references/SKILL.md`
> 风险由两件事兜底：它得自带合法的 `name` + `description` 才会被收，
> 以及重名守卫；而**实测语料里一份都没有**。这条记在这里，因为它是
> 「照搬参考实现的约定、而不核对本仓库事实」的典型代价。

### 4-2 两种摘要，因为扁平摘要在这里是 8.5k token

实测：96 条 `- name: description` 共 29,849 字符 ≈ **8.5k token**
（描述平均 288 字符，是刻意写的 "Load when … Skip when …" 路由信号）。
harness9 只有 7 个技能，扁平摘要是免费的；这里不是。

- `summary()` —— harness9 原格式，全量描述，≈8.5k token。它是**稳定
  的**（只在技能增删改时变），因此进前缀缓存是划算的。
- `domain_summary()` —— 每个 domain 一行 + 技能名清单，≈600 token。

**不做截断。** 截掉描述就是截掉路由信号，而路由正是索引存在的理由。
选哪个由组装根决定，两个数字都写进 docstring，让选择有依据。

### 4-3 跳过原因是数据，不是日志

harness9 用 `log.Print` 记录跳过。本重建的相邻层已经立了「no I/O, no
logging」的约定（`omicsclaw/engine/` 模块 docstring）。所以
`SkillIndex.skipped` 是一个 `tuple[SkippedSkill, ...]`，带路径与
`SkipReason` 枚举。组装根要打日志就打，要在 CLI 里报「3 个技能没加载」
也行——而且它是**可断言的**，日志不是。

### 4-4 找不到技能时给近似匹配，不给全表

harness9 把全部技能名拼进错误信息。96 个名字 ≈ 2KB，塞进一条工具
Observation 里既贵又难读。改成 `difflib.get_close_matches` 的前 5 个 +
总数 + 「system prompt 里的索引列了全部」。标准库，无新依赖。

## 5. frontmatter：一个明确划定的 YAML 子集

harness9 的解析器是逐行 `strings.Cut(line, ":")`。本仓库的
`SKILL.md` frontmatter 是 `scripts/generate_skill_md.py` 从 `skill.yaml`
生成的真 YAML，`description` **折行**（218 处续行），`tags` / `requires`
是块序列（1221 处），首行还有一条 `# AUTO-GENERATED` 注释。照搬会把
description 截成第一行。

支持的子集，**只有这些**：

- 文件以 `---\n` 开头，以 `\n---\n` 闭合；否则视为无 frontmatter，
  body = 全文（harness9 `skill.go:29-35` 的语义）；
- 顶格 `key: value` 标量，成对引号剥离；
- **折行续写**：后续缩进行并入上一个标量，用单空格连接（YAML 的 plain
  multiline scalar 折叠规则）；
- **块序列**：`- item` 行收成 `tuple[str, ...]`；
- 顶格 `#` 注释行忽略；
- `|` / `>` **块标量**（实现阶段加进来的：原稿判它「不支持」，但一个
  静默变成 `"|"` 的 description 是比多写 10 行更贵的坑）；
- 其余构造（嵌套映射、锚点、流式集合、双引号转义）**不支持**，遇到时
  跳过该键而不是崩溃。实测 96 份文件里一个都没有。

**这个子集由测试对着 PyYAML 钉住**：`test_real_corpus.py` 把 96 份真文
件同时喂给本解析器和 `yaml.safe_load`，逐键比对。手写解析器最大的风险
是「在真语料上悄悄解析错」，而这条测试正好覆盖它。PyYAML 缺席时
`skip`——本包自身不依赖它。

## 6. 公开面

```python
from omicsclaw.skills import (
    Frontmatter, Skill, SkillIndex, SkipReason, SkippedSkill,
    SKILL_FILENAME, USE_SKILL_TOOL_NAME,
    SkillLoadError, SkillNotFound,
    load_skills, parse_frontmatter, use_skill_tool,
)

index = load_skills("skills")                    # 目录不存在 → 空 Index
assembler.with_section(Section("skills", "## 可用 Skills", index.prompt_body))
registry.register(use_skill_tool(index))
```

**模型给的字符串永远不会变成一个路径。** `get_full_content` 是按名字查
表，拿到的是加载时记下的 `Path`；`skill_name="../../etc/passwd"` 的结局
是「没有这个技能」，不是一次文件读。这条有专门的测试。

## 7. 验收 —— 全部通过

| # | 验收项 | 证据 |
|---|---|---|
| 1 | `tests/skills/` 全绿 | **416 passed**（7 个文件） |
| 2 | 既有层不变红，且纯增量 | `tests/schema provider engine tools context` = **1,637 passed**；`git status --porcelain` 只有三个 `??` |
| 3 | 分层探针 | 源码白名单 + 动态 import 禁令 + 无 PyYAML 导入 + **子进程行为探针**：跑完全部真实路径后 `sys.modules` 里没有 `omicsclaw.skill`（单数）/ `runtime` / `context` |
| 4 | 真语料 | 96/96 加载、0 跳过、名字唯一；96 份 header 与 `yaml.safe_load` **逐键一致**（288 条参数化断言） |
| 5 | 确定性 | 两次加载 `summary()` 字节相同；顺序是排序后的相对路径，`a-b/` vs `a/c/` 这条专门钉住 |
| 6 | 变异验证 | **13/13 杀死**，见下 |
| 7 | 行长 | `awk 'length > 88'` 对本包与本测试目录输出为空 |

实测数字（写下来，免得下一个人重测）：96 个技能、索引 29,849 字符
≈8.5k token、domain 摘要 2,065 字符、正文合计 437 KB、全量重扫 ≈21 ms。

### 13 条变异，每条都被一个具名测试杀死

| 变异 | 杀死它的测试 |
|---|---|
| 遇 `SKILL.md` 剪枝 | `test_a_skill_directory_may_itself_contain_skills` |
| 不按相对路径排序 | `test_the_order_is_the_sorted_relative_path` |
| 去掉重名守卫 | `test_a_duplicate_name_keeps_the_first_and_records_the_second` |
| 根目录缺失改成抛错 | `test_a_missing_root_is_an_empty_index_and_not_an_error` |
| 丢掉折行续写 | `test_an_indented_continuation_folds_into_the_scalar` |
| 嵌套映射压平成标量 | `test_a_nested_mapping_drops_its_key_rather_than_flattening_it` |
| 未闭合 header 当成 header | `test_an_unclosed_header_is_all_body` |
| 按名查表退化成取第一个 | `test_a_name_that_looks_like_a_path_finds_nothing` |
| 空 Index 仍然渲染段落 | `test_an_empty_index_summarises_to_nothing` |
| 正文里留着 frontmatter | `test_get_full_content_returns_the_body_without_its_header` |
| `use_skill` 不声明策略 | `test_loading_a_skill_is_automatic_and_read_only` |
| 去掉技能目录页脚 | `test_it_appends_the_skill_directory` |
| loader 去 import `omicsclaw.skill` | `test_a_skills_module_imports_only_schema_and_tools` |

### 一条实现期补上的性质：绑定 = 快照

`Section("skills", …, index.prompt_body)` 绑的是**一次扫描的快照**，
`create_omics_skill` 中途新建的技能不会出现。要活的就传
`lambda: load_skills(root).prompt_body()`，代价是每次 render 重扫
≈21 ms。两种都合法，`test_a_bound_index_is_a_snapshot_and_a_rescan_closure_is_not`
把两边都钉住了——因为 0030 的 `SectionSource` 设计承诺「写了下一轮就能
看见」，而这里默认拿不到，必须写明而不是让人以为拿得到。

## 8. 不做的事

- ~~**不接线**~~ —— **已接线（2026-09-19，本步之后）**。owner 删掉了整个
  `omicsclaw/skill/`（旧的 40 模块技能系统），plan 0031 §12-1「skill 整体
  预留」的前提随之消失。现在 `omicsclaw/entry/assembly.py` 里：
  `build_skill_index(config)` 扫一次，同一个 index 同时交给
  `default_sections()`（渲染 `## Available skills` 段）和
  `foundation_tools()`（挂 `use_skill`）；`omicsclaw/entry/turn.py` 每轮
  `prompt.render()` → `assemble()` → `measure()` → 必要时 `compact(pinned=1)`
  → `engine.run()`。三档开关 `OMICSCLAW_SKILLS_INDEX=full|compact|off`，
  扫描目录 `OMICSCLAW_SKILLS_DIR`。实测本仓库 full 档整条 system prompt
  12,277 token（技能段 7,523），compact 档 5,301（技能段 547）。
  **一次扫描两个消费者**是这里唯一会静默出错的性质：扫两次会让 prompt
  宣传一个 `use_skill` 加载不到的技能，模型会把自己正确的调用读成自己的
  错误。
- **不做 `list_skills` 工具**。harness9 没有；索引已经在 prompt 里。
- **不读 `skill.yaml`**。它是旧 skill 系统的 schema（`schema_version: 2`，
  带 governance / evaluation 字段），而 owner 说那批 skill 要重新设计。
  本加载器只认 `SKILL.md` frontmatter——一个未来 skill 重设计后大概率
  还在的、和 harness9 / Claude Skills 都对得上的最小公约数。
- **不做 references/ 资源的第三层披露**。`use_skill` 的返回里会带上技能
  目录路径（实测 96 份正文里只有 2 份提到自己的目录，模型光读正文找不
  到脚本），但列目录、读 reference 是 `read_file` 的事。
