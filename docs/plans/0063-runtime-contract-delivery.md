# 计划 0063 交付记录 — 运行时契约 `OMICSCLAW.md`

**日期**：2026-09-27。**规格**：`docs/plans/0063-runtime-contract.md` 第 3 版（owner 已裁定 Q1–Q8 全部按推荐项执行）。本记录不改动计划正文。
**范围**：阶段 0–3。阶段 4（O 表的措辞与剪枝）不在本次授权内，没有做。
**状态**：阶段 0–3 都已实施并验收；独立评估后的修复见 §10。没有 commit，也没有 `git add`：`SOUL.md` 是用 `rm` 删的，新文件都未跟踪。
**开工状态**：`0881aa7b` 加上大量未提交改动（0061、0062、审计总补丁、0057 的 T8 等），全部保留。

## 1. 结论

| 阶段 | 验收结论 | 关键证据 |
|---|---|---|
| 0 | **通过** | 基线目录、逐文件副本、`stash create` 引用都已建立；两项前置检查通过（§2.2） |
| 1 | **通过** | 新测试先红后绿；§11.1 渲染对比全部符合期望（R1 从 `## Safety rules` 起逐字节相同，R3、R4 全文相同）；附录 B 逐字核对 256 项全部通过；§11.4 命令为 588 passed、1 failed（既有失败）、1 skipped |
| 2 | **通过**（一处按派发要求未改，见偏离 1） | §11.3 第一条 grep 交付时只剩 `omicsclaw/tools/builtin/web_fetch.py:9`，这一处后来由主会话改好，现在为空（§10）；docstring 改动涉及的测试文件全部通过 |
| 3 | **通过** | 16 个文档文件；读文档的测试只有既有失败 |

token（本仓库 `estimate_text_tokens`）：

| 部署 | 改动前 | 改动后 | 变化 |
|---|---|---|---|
| R1 workspace 为仓库根（M1） | 11,925（persona 291 + project 3,691 + 其余 7,943） | **10,148**（contract 2,205 + 其余 7,943） | −1,777 |
| R2 空数据目录 + `skills_dir=<仓库>/skills`（M2） | 7,935（无前置段） | 10,140 | +2,205 |
| R3 空数据目录，未设 skills_dir（M3） | 547 | 547 | 0，全文相同 |
| R4 仓库根 + `system_prompt_files`（M7） | 7,948 | 7,948 | 0，全文相同 |

计划估算为约 2,206 ± 60、全提示约 10,150，实测 2,205、10,148。

## 2. 阶段 0：基线

基线目录 `$B = /workspace/dataset/private/zhouwg_data/0063-baseline`，在仓库外，也不在 `/tmp`。

| 文件 | 内容 |
|---|---|
| `files-phase1.txt`、`files-phase2.txt`、`files-phase3.txt` | 各阶段文件清单（18、40、16 个，与计划 L1–L3 的差异见偏离 1、2） |
| `tree/` | 清单内每个已存在文件在改动前的工作树副本（`cp --parents -p`），含 `SOUL.md`、`CLAUDE.md` 与未跟踪的 `docs/core-features/`、`tests/sdk/test_replot_hint.py` |
| `stash-sha.txt` | `git stash create` 的结果 `b72050f5b2e34e82bc36079c370eed155e04be64`，已用 `git update-ref refs/backup/0063-base` 钉住。只含已跟踪文件；未跟踪文件以 `tree/` 为准。可选的"临时索引全量快照"没有做 |
| `render.py`、`render/` | 附录 A 的脚本；`before-*`、`after-*` 四种部署的渲染文本与 `*-stats.json`；`checks.txt` 是 §11.1 的核对输出；`front-R1.diff` 是 R1 前置段的差异；`after-R2-pinned.txt` 见 §3.5 |
| `processes.txt`、`preflight.txt` | §12.2 第 5、6 步 |
| `tests-before.txt`、`tests-before-wide.txt`、`tests-red.txt`、`tests-after-phase1*.txt`、`tests-after.txt`、`tests-after-wide.txt` | 测试记录 |
| `verbatim.py`、`verbatim.txt` | 附录 B 的核对脚本与逐行结果 |
| `phase2_omicsclaw.py`、`phase2_tests.py`、`phase3_docs.py` | 阶段 2、3 的一次性替换脚本（每处替换都断言原文恰好出现一次） |
| `grep-after-phase2.txt`、`entry-changed.txt` | §11.3 的 grep 结果；改动过的 `omicsclaw/entry/**` 文件及其 sha256 前缀 |
| `0063-phase1.diff`、`0063-phase2.diff`、`0063-phase3.diff` | 各阶段补丁（§8） |
| `files-fixup.txt`、`tree-fixup/`、`0063-fixup.diff`、`tests-after-fixup.txt` | 评估后修复的文件清单、修复前副本、补丁与测试记录（§10） |
| `omicsclaw-before-fixup.sha256`、`fixup-start.marker` | 评估后修复开工时 `omicsclaw/` 全部文件的 sha256 与时间戳标记，用来确认修复没有碰 `omicsclaw/` |

### 2.1 长驻进程

`pgrep -af "oc (channel|desktop)|omicsclaw\.launch"` 命中的只有两个 2026-09-20 遗留的 pytest 探针子进程（`/tmp/pytest-of-root/pytest-1742/test_a_signal_drains_the_chann*`），按派发说明不 kill、不重启。另有一个 2026-09-23 起处于停止态（`T`）的 `oc cli`，不属于 channel/desktop，未动。所以阶段 1 第 1 步无进程可停，第 7 步无进程可启。

### 2.2 前置检查（§12.2 第 6 步）

- **0057 未冻结**：`docs/plans/0057-validation/` 下只有 `frozen_settings.json`（`freeze.py write` 的手写输入），没有 `freeze.json`；仓库、`/tmp/0057_dev`、`/tmp/0057_holdout` 下都找不到 `freeze.json`；`0057-dev-report.md` 第 4、99 行写明冻结等协调方通知。阶段 2 开始前复查一次，结果相同。
- **A3 已钉住前置段**：`run_arms.py` 的 `a3_config()`（:307）写出 `base/empty_front_matter.txt`（内容为空），并传 `system_prompt_files=(empty,)`（:325）；A3 驱动在 :255 调用它。

### 2.3 测试基线

- §11.4 阶段 0 命令：**579 passed、1 failed、1 skipped**。失败的是 `test_turn.py::test_the_system_message_survives_a_successful_summarization`（`EMERGENCY` 而不是 `FULL`，`tokens_before=5229`）。
- 扩展集（`tests/entry` 全部、`tests/ensemble/tuning/test_a3_prompt.py`、阶段 2 将改 docstring 的 10 个测试文件）：**1874 passed、2 failed、2 skipped**。另一个失败是 `tests/entry/test_session.py::test_a_second_compaction_extends_the_first_instead_of_restarting`（工具定义超出保留量 2,266 token 后进入 `EMERGENCY`，同样对尺寸敏感），不在计划的已知失败清单里，改动前后状态相同。
- 计划列为既有失败、但在本工作树上**通过**的：`tests/tools/test_workspace.py`；`tests/entry/test_permission_wiring.py::test_the_gate_does_not_change_what_the_model_is_shown`（协调方已更正为不再是已知失败，改动前后都通过）。

## 3. 阶段 1

### 3.1 先红

写完 §8.1、§8.2 的测试后运行 `test_runtime_contract.py` 与 `test_assembly.py`：**11 failed、46 passed**（`$B/tests-red.txt`）。没有变红的新用例是 M6、M7 与免责声明三条，它们描述的行为改动前就成立。

### 3.2 实施

- **`omicsclaw/entry/assembly.py`**：
  - 删除 `DEFAULT_PERSONA_FILE`、`DEFAULT_CONTRACT_FILE`，新增 `CONTRACT_FILE = "OMICSCLAW.md"`，`__all__` 同步。
  - `_front_matter` 改为一段 `Section("contract", "", text_from_file(config.repo_root() / CONTRACT_FILE))`；`system_prompt_files` 非空时的分支不变。
  - `SAFETY_RULES` 的 docstring 按注释约定重写，常量正文一字未改。
  - `default_sections` 的顺序说明、`skills_index=off` 一句、缺文件一句；模块 docstring :5、:48，`build_prompt` 与 `AgentApp.prompt` 的 docstring。
  - 0057 的 T8 改动（`foundation_tools` 的 `tuning_model`、`_ensemble_tools`、`build_tuning_model`、`build_app` 调用处、import 与 TYPE_CHECKING）都在基线里，补丁中没有它们的块。
- **`omicsclaw/entry/config.py`**：模块 docstring :7、:47，`system_prompt_files` 的 docstring。字段、选项表、解析函数不变。0057 的新字段、解析器与 `_Option` 同样不在补丁中。
- **`OMICSCLAW.md`**（新建，182 行，8,793 字节）：按 §3 迁移，结构为 `# OmicsClaw` → `## Identity` → `## Operating Rules` → `## Skill Routing Table` → `## How to Use a Skill`（`### Skills with Python scripts`、`### Dependencies`、`### Chaining skills`）→ `## Finding a skill` → `## Demo Data` → `## Re-rendering plots` → `## User-facing notes`（`### What the user can type`、`### Desktop`、`### Channel — IM bots`）。非逐字改动只有 §3.4 的 N1–N9 与 FX1–FX4。
- **`CLAUDE.md`**：§4.3 的第三人称指针段加 C5、C6 原文（后者从基线副本逐行复制）。
- **`SOUL.md`**：删除。
- **测试**：§8.1、§8.2、§8.3；另改 `tests/entry/test_cli_activity.py`（偏离 2）。
- **文档**：§9.1 的 `AGENTS.md` 7 处；§9.2 的 `.env.example`（第 2 节受信目录说明、`OMICSCLAW_SYSTEM_PROMPT_FILES`、`OMICSCLAW_SKILLS_DIR`、第 6 节 safety 措辞、`FEISHU_BOT_OPEN_ID`）、`CONTRIBUTING.md` 两处、`templates/skill/README.md`、`llms.txt`、`mint.json`。

### 3.3 §11.1 渲染对比（`$B/render/checks.txt`）

| 检查 | 结果 |
|---|---|
| R1：从 `## Safety rules` 起的 diff | 空 |
| R1 前置段 | 一个 `contract` 段；"You are **OmicsClaw**" 恰好 1 次；`## Project contract`、`Repository Maintenance Contract`、`gh issue`、`pip install -e`、`<!-- ROUTING-TABLE`、`fully functional`、`works on every primary script` 都是 0 次 |
| R2 | 改动前从 `## Safety rules` 开始，改动后从 `# OmicsClaw` 开始；`## Safety rules` 之后与改动前相同；前置段与 R1 相同 |
| R3、R4 | 全文相同 |
| token | 见 §1 |

R1 前置段的变化要点（`$B/render/front-R1.diff`，删 177 行、增 29 行）：
- 删去：SOUL.md 的标题与 S3 身份句、`## Project contract` 标题、`# CLAUDE.md — …` 标题、Repository Maintenance Contract、Agent skills（issue tracker、triage 标签）、两行 ROUTING-TABLE 标记、frontmatter 四键规则、整节 Surfaces（CLI 命令表、审批授权、Desktop 与 Channel 的安装、启动与环境变量）、重复的 Safety Rules。
- 新增或移动：`# OmicsClaw`；C4 移到路由小节；FX2 的路径句、FX3 的 `--help` 句；`### Dependencies`（C14）；`## User-facing notes` 下的 C12、C20、C25。
- 身份段顺序：C2 → S4 → C3（FX4）；规则 1–9 与 `SOUL.md` 逐字节相同。

### 3.4 §11.2 逐字核对（`$B/verbatim.txt`）

256 项全部通过。做法按附录 B：原文每行合并空白后，断言它是目标文件（同样合并空白）的子串；`gone` 断言在新 `OMICSCLAW.md`、`CLAUDE.md` 中都不出现。豁免与特殊行：
- C1、S1 不核对；空行跳过。
- 纯 Markdown 语法行（代码围栏、表格分隔行）记为"语法行，不核对"，共 16 行。它们在 `gone` 方向上必然误报。
- C3（FX4）：改后句在，"fully functional" 不在。
- C4：从 `CLAUDE.md:5` 的 "fully functional. " 处切出后半句，单独核对。
- FX2、FX3：改后句在，原句不在。
- C20：从 "**Known gap**" 起，连同 `### Desktop` 标题一起核对。
- C25：连同 `### Channel — IM bots` 标题一起核对。
- C12：连同原标题整块核对。
- C22：在 `AGENTS.md` 中。
- C23：改写句在 `AGENTS.md` 中，`AGENTS.md` 不再出现 `SOUL.md`。
- 规则 1–9：作为整块逐字节核对，编号与原文相同。

### 3.5 对 0057 A3 的核对

- `AppConfig(workspace=<空目录>, skills_dir=<仓库>/skills, system_prompt_files=(<空文件>,))`，即 A3 的形态，改动后的渲染与改动前 R2 的渲染**逐字节相同**（`$B/render/after-R2-pinned.txt`）。A3 的系统提示没有变。
- 0057 自己的 `tests/ensemble/tuning/test_a3_prompt.py` 有两条会因此变红，见 §9。

### 3.6 §11.4 测试

| 命令 | 改动前 | 改动后 |
|---|---|---|
| §11.4 命令（改动后加 `test_runtime_contract.py`） | 579 passed、1 failed、1 skipped | **588 passed、1 failed、1 skipped**（多出的 9 个是新用例） |
| 既有失败 `test_the_system_message_survives_a_successful_summarization` | `EMERGENCY`，`tokens_before=5229` | 仍为 `EMERGENCY`，`tokens_before=5224`（少了 `## Project contract` 标题），档位没有翻转 |

## 4. 阶段 2（docstring 出处）

- `omicsclaw/` 下 22 个文件、33 处；`tests/` 下 18 个文件、25 处。按 §7.4 的五类映射：S 类改指 `SAFETY_RULES` 第 1 条（摘要行用短写 ``SAFETY_RULES``，正文用 `:data:` 引用）；C 类去掉出处、保留规则原文；E 类改指 `.env.example`；P 类改为 `OMICSCLAW.md` 或泛指的提示文件；X 类按代码改写。
- **X 类两处的核实**：
  - `context/tokens.py:22`：去掉"本仓库的提示是中文"的文件清单，只留"中文文本会被低估"的一般论断。
  - `context/tokens.py:75`：核实过，今天没有任何界面把图片交给模型。Telegram 拒收照片（`entry/channel/telegram.py:666-686`）；Feishu 丢弃非文本消息（`feishu.py:604-615`）；Slack、Discord、DingTalk、QQ、Email 的 `attachment_input_enabled=False`；MCP 的图片块变成一行文字占位（`mcp/client.py:251-256`）。据此改写为"今天不可达；schema 带上图片分片后预算会偏乐观"。
  - `launch/_surfaces.py:328`：改为直接陈述 "The Electron client connects to 127.0.0.1:8765"。
- `desktop/server.py` 的 `omicsclaw_dir` 说明按计划删去 `SOUL.md`，写明 skills（未设 `skills_dir` 时）与 `.mcp.json` 相对 workspace 解析。
- §11.3 的三条 grep（`$B/grep-after-phase2.txt`）：
  - 第一条交付时只剩 `omicsclaw/tools/builtin/web_fetch.py:9`（偏离 1）。这一处后来由主会话改好，现在第一条为空（§10）；
  - 第二条只剩新测试里的否定断言 `"## Project contract" not in system`；
  - 第三条为空。
  - `tests/` 下剩余的 `SOUL.md` 引用只有计划标为"不改"的 `tests/context/test_sections.py`、`tests/engine/test_prompt_source.py`，以及新测试文件里的旧布局用例。

## 5. 阶段 3（说明文档）

- `README.md`："What's New" 最前面新增一条，写明契约迁到 `OMICSCLAW.md`、契约跟随 skill 树（M1、M2、M3 的区别）、零代码做法（仓库 `.env` 设 `OMICSCLAW_SKILLS_DIR`）、旧工作目录的 `SOUL.md` 与 `CLAUDE.md` 不再读取，以及 token 变化和缓存一次性失效。计划所指的 `:70`、`:76` 历史里程碑未动（新条目插入后它们各下移两行）。
- `docs/FRAMEWORK-REBUILD.md`：指针表在 "Repo agent contract" 之后新增一行 `OMICSCLAW.md`，带日期的小节未动。
- `docs/safety/rules-and-disclaimer.mdx:30`：出处改为 `SAFETY_RULES` 第 2 条。
- `docs/core-features/` 13 个文件，按 §9.3 的必改与顺手改清单逐条修改。`context-engineering.md` 的 §4.2 段序表重排为 8 行，§4.3 改写为单一契约文件与定位规则，免责声明的漂移检查改为描述新测试。`quick-start.md:308` 与 `cli.md:364` 写入零代码做法。`surfaces.md` 的三处"与 `CLAUDE.md` 的出入"改为只陈述代码行为。

## 6. 偏离与理由

1. **`omicsclaw/tools/builtin/web_fetch.py:9` 没有改。**派发说明禁止修改 `omicsclaw/tools/builtin/`，那里的描述问题由另一项工作处理。所以它从 `files-phase2.txt` 中移除，基线副本也删去，以免那项工作的并发改动被算进本计划的补丁。§11.3 第一条 grep 因此在交付时还剩这一处（S 类）。它之后已由主会话改为 `SAFETY_RULES` rule 1，见 §10。
2. **`tests/entry/test_cli_activity.py:996, 1014` 改了**，计划 §7.4 原写"不改"。这条用例用 `read_file` 读 `SOUL.md`，而这个文件只是因为共用的 `make_app`（`test_turn_runner.py`）会写它才存在。§8.3 把 `make_app` 改为写 `OMICSCLAW.md` 后，这条用例变红。因此把路径和提问里的文件名改成 `OMICSCLAW.md`。这是计划的事实遗漏。该文件在改动前补做了基线副本（文件的 mtime 是 2026-09-23，早于本次开工），并加进 `files-phase1.txt`。
3. **FX5 的措辞。**计划要求加 "Required" 并保留理由原句。原文 "Optional, but group chats fail closed without it" 中的"群聊失败关闭"在必填之后已不是实际后果，代码是拒绝启动（`launch/_surfaces.py:1610-1615`）。所以 `AGENTS.md` 写作 "**Required**: ingress refuses to start without it, because a group @-mention cannot otherwise be attributed…"；`.env.example` 写作 "Required. … Feishu ingress refuses to start without it, because an @-mention cannot otherwise be attributed to this bot."。理由从句原样保留。
4. **新测试里"首段是什么"用渲染后的段键判断**（`section_stats`），不用 `default_sections` 返回的键。`default_sections` 总会带上 `contract` 这个 `Section` 对象，文件缺失时是渲染阶段才把它丢掉。所以 M6 用例若看 `default_sections` 的键会得到 `contract`，看渲染结果才是 `safety`。
5. **`test_assembly.py` 的用例改名**：
   - 段序用例 → `test_the_default_prompt_is_contract_then_safety_then_guidance_in_this_order`；
   - 索引关闭用例 → `test_the_catalogue_can_be_switched_off_and_its_section_goes`；
   - 缺文件用例 → `test_a_missing_contract_file_removes_its_section`，断言提示以 `## Safety rules` 开头；
   - 替换用例 → `test_prompt_files_replace_the_contract`。

   计划要求"用例名按内容命名，不再写数字"，这里照做。
6. **`test_turn_runner.py` 的 `make_app`** 与 `test_turn.py` 一样合成一份 `OMICSCLAW.md`（"You are OmicsClaw.\n\nRoute to a skill."）。计划只写了"改为写 `OMICSCLAW.md`"，没有指定内容。
7. **`.env.example` 的 `OMICSCLAW_SKILLS_DIR`**：计划示意是行内注释。实际改为变量上方的三行注释，变量行本身不变，避免一行过长。`mint.json` 的排除列表按字母序插入 `OMICSCLAW.md`，没有放在 `SOUL.md` 原来的位置。
8. **文档的几处小补充**，都在计划列出的文件与段落之内：
   - `context-engineering.md` 配置表 `skills_dir` 一行补"`OMICSCLAW.md` 从它的上一级读取"；
   - `shell-execution.md` 的示例路径随 FX2 改为 `<skill 目录>/<script>.py`；
   - `agent-skills.md:406` 的 `DISCLAIMER` 出处改为 skill 实际使用的 `skills/_sdk/report.py`（F21），与新的漂移检查一致；
   - `agent-skills.md:499` 与 `quick-start.md:341` 只去掉 `CLAUDE.md` 出处，保留 "`examples/demo_visium.h5ad` 不存在" 这一事实。
9. **`FRAMEWORK-REBUILD.md`** 是新增一行，没有改原有的 "Repo agent contract" 行。

## 7. 改动文件清单

**新增**
- `OMICSCLAW.md`
- `tests/entry/test_runtime_contract.py`（9 个用例）
- `docs/plans/0063-runtime-contract-delivery.md`（本文件，不在任何阶段补丁里）

**删除**
- `SOUL.md`

**修改**
- 阶段 1：`CLAUDE.md`、`AGENTS.md`、`CONTRIBUTING.md`、`.env.example`、`llms.txt`、`mint.json`、`templates/skill/README.md`、`omicsclaw/entry/assembly.py`、`omicsclaw/entry/config.py`、`tests/entry/test_assembly.py`、`test_turn.py`、`test_turn_runner.py`、`test_memory_wiring.py`、`test_entry_is_the_top_layer.py`、`test_cli_activity.py`
- 阶段 2（omicsclaw，22 个文件）：
  - `context/__init__.py`、`sections.py`、`tokens.py`
  - `entry/__init__.py`、`ingress.py`、`turn.py`、`desktop/server.py`
  - `entry/channel/__init__.py`、`binding.py`、`feishu.py`、`runtime.py`、`telegram.py`
  - `entry/cli/_configure.py`、`_screen.py`
  - `launch/__init__.py`、`_dotenv.py`、`_surfaces.py`
  - `observability/__init__.py`、`config.py`
  - `planning/render.py`
  - `tools/_websafety.py`、`_workspace.py`
- 阶段 2（tests，18 个文件，只改 docstring 或注释）：
  - `observability/test_config.py`、`test_scope.py`
  - `tools/test_web_fetch.py`、`test_workspace.py`
  - `entry/test_cli_configure.py`、`test_cli_logging.py`、`test_approval.py`、`test_ingress.py`、`test_channel_adapters.py`、`test_channel_ingress.py`、`test_cli_repl.py`
  - `permission/test_modes.py`、`test_danger.py`
  - `launch/test_configure_command.py`、`test_surfaces.py`、`test_grammar.py`
  - `planning/test_render.py`
  - `sdk/test_replot_hint.py`
- 阶段 3：
  - `README.md`、`docs/FRAMEWORK-REBUILD.md`、`docs/safety/rules-and-disclaimer.mdx`
  - `docs/core-features/`：`context-engineering.md`、`quick-start.md`、`cli.md`、`surfaces.md`、`agent-loop.md`、`sub-agent.md`、`agent-skills.md`、`observability.md`、`web-search.md`、`sandbox.md`、`shell-execution.md`、`mcp.md`、`human-in-the-loop.md`

没有改动：`omicsclaw/ensemble/`、`omicsclaw/tools/builtin/`、`docs/plans/0057-*`、`docs/plans/0057-validation/`、`tests/ensemble/`、golden 文件 `tests/entry/golden/*`（golden 不需要重新生成，`test_ensemble_golden.py` 改动前后都通过）。

## 8. 补丁与回退

**补丁**：`$B/0063-phase{1,2,3}.diff`，按附录 C 生成，原文一侧取自 `$B/tree/`。三份各自生成后都通过了 `git apply --check -R`，三份合并后也通过。

- 逐块检查：阶段 1 有 49 个块，阶段 2 有 57 个，阶段 3 有 34 个，全部是本计划写的。
- 每个阶段开始前，都用 `cmp` 确认该阶段的文件自基线以来没有被别的会话改动。0057 T8 在 `assembly.py`、`config.py` 里的改动早于基线，不在补丁中。
- 在 `/tmp` 的临时目录里演练过一次：取当前版本，按 3 → 2 → 1 的顺序反向应用，结果与 `$B/tree/` 逐文件相同（`OMICSCLAW.md` 与新测试被删除，`SOUL.md` 恢复为改动前工作树的版本）。

**补丁生成之后的并发改动**：2026-09-27 06:37:46 UTC，另一个会话在 `omicsclaw/entry/config.py` 与 `.env.example` 里新增了 `ensemble_seed`（字段、`_as_seed`、`_Option`、对应的环境变量）。这些块不是本计划的，也不在补丁里。复查时三份补丁合并后仍能通过 `git apply --check -R`：反向应用只撤回本计划的块，那部分新增会保留。

> **⚠️ 0057 冻结期间不要用补丁回退阶段 1、2。**阶段 1、2 的补丁都改 `omicsclaw/entry/**`，而这个目录在 0057 `freeze.py` 的 `CODE_GLOBS` 里；代码摘要与 `freeze.json` 不符时，`run_holdout` 拒绝运行。所以从 0057 写出 `freeze.json` 起，到它的留出运行全部结束为止：
> - 回退阶段 1 或 2，会让留出运行拒绝启动；在运行中途回退，会让冻结与实际代码不一致。**这期间不要做。**
> - 需要恢复旧提示，只能用下面"只恢复旧提示、不回退代码"的做法（设 `OMICSCLAW_SYSTEM_PROMPT_FILES`）。它不改任何冻结范围内的文件；A3 直接构造 `AppConfig` 并显式钉住前置段，不读这个环境变量，所以也影响不到 A3。
> - 阶段 3 与 `0063-fixup.diff` 只改文档、测试和 `.env.example`，都不在冻结范围内，随时可以回退。

**回退步骤**（§12.4）：
1. 停掉长驻进程。今天没有需要停的，见 §2.1。
2. 在仓库根按从后往前的顺序回退：先 `git apply -R --check $B/0063-fixup.diff && git apply -R $B/0063-fixup.diff`（§10 的修复），再对 phase3、phase2、phase1 做同样的事。
3. `--check` 失败，说明有人在本计划之后改了同一段落。`git apply` 这时整份拒绝、不做半截应用，不会误伤别人的改动。处理方法见下面的"整份拒绝时的手工回退"。
4. 重启长驻进程。

**整份拒绝时的手工回退**。已知有两种情形会让补丁整份被拒：

- **阶段 3：README 里 0057 的条目变了。**0063 的 README 块以下一条（0057 的 "Ensemble tuning …" 条目）作尾部上下文，0057 更新自己的状态句后，`git apply -R --check $B/0063-phase3.diff` 报 `patch failed: README.md:35`，其余 15 个文档也跟着回退不了。做法：
  1. `git apply -R --check --exclude=README.md $B/0063-phase3.diff && git apply -R --exclude=README.md $B/0063-phase3.diff`，先回退其余 15 个文档；
  2. 在 `README.md` 里手工删掉以 `` - **📜 One runtime contract: `OMICSCLAW.md`** `` 开头的那一行，以及它后面的一个空行。0057 的条目不要动。
- **阶段 1：`OMICSCLAW.md` 在本计划之后被编辑过**，例如 R13 的计数、阶段 4 的 O 项。补丁里删除新建文件的那一段要求文件与交付时逐字节相同，否则 `git apply -R --check $B/0063-phase1.diff` 报 `patch failed: OMICSCLAW.md:1`。做法：
  1. 先确认之后的那些编辑是否也要一起放弃。回退 0063 就是放弃整个契约文件，之后的编辑也会一起丢掉；如果要保留，先另存一份；
  2. `git apply -R --check --exclude=OMICSCLAW.md $B/0063-phase1.diff && git apply -R --exclude=OMICSCLAW.md $B/0063-phase1.diff`；
  3. `rm OMICSCLAW.md`。
- **其他文件冲突**：对冲突文件用 `diff $B/tree/<file> <file>` 手工只撤回本计划的块，用 `--exclude=<file>` 让其余文件照常回退。**不要**把副本直接拷回去，那会抹掉别人之后的改动。

以上两种情形已在 `/tmp` 的临时副本里演练：把 0057 的状态句改掉、往 `OMICSCLAW.md` 末尾加一行，再按 fixup → 3（排除 README）→ 手工删 README 条目 → 2 → 1（排除 `OMICSCLAW.md`）→ 删 `OMICSCLAW.md` 的顺序回退。结果与 `$B/tree/` 相比，只剩别的会话之后的改动（0057 的 README 状态句、`ensemble_seed`）。

**只恢复旧提示、不回退代码**：设 `OMICSCLAW_SYSTEM_PROMPT_FILES=$B/tree/SOUL.md:$B/tree/CLAUDE.md`。实测渲染结果与改动前的 R1 只差 `## Project contract` 这一行标题（以及它后面的空行）。0057 冻结期间，这是恢复旧提示的唯一做法（见上面的警告）。

**与审计总补丁的先后**：本计划落地后，`/tmp/prompt-audit/applied-facts.diff` 中涉及 `CLAUDE.md`、`SOUL.md` 的部分已不能直接 `git apply -R`。两者都要撤回时，**先撤回本计划**（上面三步），再撤回审计补丁。

**`refs/backup/0063-base`** 指向改动前已跟踪文件的快照，确认不再需要后可以 `git update-ref -d refs/backup/0063-base` 删掉。

## 9. 遗留

- **0057 的 `tests/ensemble/tuning/test_a3_prompt.py`**：交付时有两条用例变红（`test_the_pinned_prompt_equals_the_unpinned_one_in_a_fresh_workspace`、`test_the_pinned_prompt_equals_what_the_development_run_rendered`）。原因是它们拿不钉住的 A3 形态（`skills_dir=<仓库>/skills`，即 M2）作对照，而本计划有意让 M2 读到仓库的 `OMICSCLAW.md`（Q2 = a）。0057 已改好对照口径，**现在 4 passed**（§10）。钉住的 A3 提示本身始终没有变（§3.5）。
- **`omicsclaw/tools/builtin/web_fetch.py:9`**：已由主会话改好，见 §10。
- **等 0057 的留出运行全部结束后再改**（都在冻结范围 `omicsclaw/entry/**` 内，现在改会让冻结摘要失配）：
  - `omicsclaw/entry/assembly.py:67-69` 模块 docstring 的 "returns six sections rather than five"、"restores the five-section prompt"，数字已与现实不符；
  - `AppConfig.repo_root()` 与 `skills_dir` 的 docstring 没有提到契约从这里定位；
  - `repo_root()` 不解析符号链接（见下一条已知限制）。是否改成解析，届时再定。
- **已知限制：`<workspace>/skills` 是指向仓库的符号链接时，契约不会跟过去。**`repo_root()` 返回 `skills_root().parent`，按路径名取上一级，不解析符号链接：在数据目录里建 `skills -> <仓库>/skills` 启动，skill 能扫到，契约却要在数据目录里找，结果没有契约；显式传一个本身是符号链接的 `skills_dir`，情形相同。这是 `repo_root()` 的既有语义，`code_mounts`、skill_env、`entry/ensemble.py` 都这样用，不是本计划引入的，不改代码。需要检出目录的契约时，把 `OMICSCLAW_SKILLS_DIR` 设为检出目录下 `skills/` 的绝对路径。
- **FX2 的句子没有覆盖 `skills/literature/`**：这个 skill 比常规少一层，直接在 `skills/literature/`。句子用 "usually" 限定，并以 `use_skill` 返回的目录为准，所以仍成立；要进一步改措辞，属于阶段 4 的会话对比。
- **尺寸敏感的既有失败**：`test_turn.py` 的 summarization 用例与 `test_session.py` 的二次压缩用例，改动前后都失败，档位没有变。
- **冒烟（§11.5）没有执行**，它需要真实的 LLM key，由 owner 决定。
- **阶段 4（O1–O11）**按 Q4 = a、Q7 = a 另开一项，本次未动。R13（consensus skill 裁定对路由表计数的依赖）照旧。
- **历史文档**里仍有 `SOUL.md`、`CLAUDE.md` 的说法，属于计划的非目标（R7），包括 README 的旧里程碑、`docs/FRAMEWORK-REBUILD.md` 带日期的小节、`docs/plans/*`、`docs/product-overview.md` 等。
- **暂存区（评估 m6）**：`OMICSCLAW.md`、`tests/entry/test_runtime_contract.py`、本交付记录都未跟踪，`SOUL.md` 的删除也没有暂存，提交时由 owner 处理。漏掉 `git add OMICSCLAW.md` 的后果是：干净检出下 M1 会静默失去契约段，因为缺文件就是"没有这一段"，不会报错。好在 `test_the_real_contract_*` 在干净检出下会因 `FileNotFoundError` 变红，CI 能发现。

## 10. 评估后修复（2026-09-27）

独立评估报告为 `/tmp/omicsclaw-0063-eval.md`，总评"需小修"，没有阻断项，全部发现都在 `omicsclaw/` 之外。按协调方的派发，这一轮**没有改 `omicsclaw/` 下任何文件**，因为 0057 正按当前的 `omicsclaw/entry/**` 冻结。

**交付后事实更正**
- **`omicsclaw/tools/builtin/web_fetch.py:9`**：主会话已把出处改为 ``:data:`~omicsclaw.entry.assembly.SAFETY_RULES` rule 1``，§11.3 第一条 grep 现在为空。这处改动**不在任何阶段补丁里**，所以回退 0063 不会撤回它，也不需要撤回：`SAFETY_RULES` 在 0063 之前就存在。同一文件里另有 tools/builtin 描述工作的改动，不属于 0063。
- **`tests/ensemble/tuning/test_a3_prompt.py`**：0057 已改好对照口径，现在 4 passed。

**修复项**

| 评估编号 | 改动 | 位置 |
|---|---|---|
| I1 | §8 加警告：0057 冻结后、留出运行结束前，不用补丁回退阶段 1、2，恢复旧提示只用 `OMICSCLAW_SYSTEM_PROMPT_FILES` | 本文件 §8 |
| m1 | `web_fetch.py:9` 与 `test_a3_prompt` 的过时陈述已更新 | 本文件 §1、§4、§6 偏离 1、§9 |
| m2 | 写明阶段 3（README 里 0057 的条目变了）与阶段 1（`OMICSCLAW.md` 被后续编辑）整份拒绝的情形，以及用 `--exclude` 的手工回退步骤，并已演练 | 本文件 §8 |
| m3 | 符号链接不跟随记为已知限制 | 本文件 §9 |
| m4 | 零代码做法写明 `OMICSCLAW_SKILLS_DIR` 要用绝对路径，相对路径按进程启动目录解析 | `.env.example` 第 4 节 |
| m5 | 测试 docstring 去掉 M1–M7 标签，改为用文字描述部署形态，哨兵 `CONTRACT-M1` 改名为 `CHECKOUT-CONTRACT`；免责声明用例改为判断渲染后首段键为 `contract`，不再依赖 "You are **OmicsClaw**" 的措辞；3 行超过 88 列的折行；`test_cli_repl.py` 的出处改为 `AGENTS.md`（CLI 命令表在那里） | `tests/entry/test_runtime_contract.py`、`test_assembly.py`、`test_channel_adapters.py`、`test_cli_repl.py` |
| m7 | 计划状态行改为"已实施（2026-09-27），见交付记录" | `docs/plans/0063-runtime-contract.md` 第 3 行 |

m6（新文件未 `git add`）与 m7 中其余几项只登记在 §9，没有改。

**补丁**：`$B/0063-fixup.diff`，共 6 个文件、10 个块。原文一侧是修复开工前的副本 `$B/tree-fixup/`，所以只含这一轮的改动。之所以另出一份，而不重新生成阶段 1、2 的补丁：`.env.example` 已带有别的会话后加的 `ensemble_seed`，从 `$B/tree/` 重新生成会把它误算成本计划的改动。回退时 fixup 最先撤，见 §8。
- `git apply --check -R` 通过；
- 在临时副本里按 fixup → 3 → 2 → 1 演练过一次，结果与 `$B/tree/` 相比只差别的会话之后的改动（`ensemble_seed`）。

**测试**：`tests/entry/test_runtime_contract.py`、`test_assembly.py`、`test_channel_adapters.py`、`test_cli_repl.py` 与 `tests/test_env_example.py`，**144 passed**（`$B/tests-after-fixup.txt`）。

**`omicsclaw/` 未改动的核对**：修复开工时把 `omicsclaw/` 下全部 325 个文件（不含 `__pycache__`）的 sha256 记入 `$B/omicsclaw-before-fixup.sha256`，并建立时间戳标记 `$B/fixup-start.marker`。修复结束后重算：
- sha256 与开工时相同；
- 没有任何 `omicsclaw/` 文件的 mtime 晚于标记。
