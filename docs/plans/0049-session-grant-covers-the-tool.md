# 计划 0049 — 审批卡片的 `s` 放行整个工具，危险命令仍逐条询问

**状态**：**已实现**（2026-09-23）。方向由 owner 选定，一轮独立只读审核后返工
（§11），owner 对 §12 三项均按建议裁定后实现，交付记录见 §13。
验证：整栈 **5054 passed, 12 skipped**，另 1 项为已知的时序敏感测试
（`test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget`，
单独重跑 `tests/tools` 775 项全绿，与本改动无关）。

**触发**：owner 在 `oc cli` 里每条 bash 都要按一次 `approve bash [#N]?`。
按过 `a` 也没用，下一条命令照样询问。

---

## 0. 先说清安全含义（审核后补写，owner 做决定前应先读）

**对 bash 按 `s`，在这个会话余下的时间里约等于对 bash 开了 `auto-approve`。**
之后还会拦下来的只有危险命令模式（`omicsclaw/permission/danger.py`），而它是
一份**黑名单**：`rm -rf /` 会被拦，
`python -c "import shutil; shutil.rmtree('/data')"` 或
`eval "$(echo … | base64 -d)"` 不会。这不是本计划引入的，`auto-approve` 模式
今天就是这样；本计划只是让它能在会话中途、针对单个工具开启。

**真正的边界是沙箱**（`OMICSCLAW_SANDBOX=docker`，默认关闭，见
`.env.example:201-214`），不是危险模式。本计划不改变这一点，只在 §8 如实记录。

## 1. 现象与根因

### 1.1 `a`（always）写下的是整条命令原文

`omicsclaw/permission/rules.py:451 literal_pattern` 转义全部通配符，生成**只
匹配这一条调用**的规则。这是刻意设计，且**不能放宽**：`PermissionGate.resolve`
（`gate.py:165-244`）的顺序是

1. `bypass-all` → 2. `read-only` → **3. 规则文件** → **4. 危险命令模式** → 5. `auto-approve` → 6. 工具自己的 `approval_mode`

规则在第 3 步命中即返回（`gate.py:210-217`），无论 allow/deny/ask 都**压过**
第 4 步。`a` 若写成 `bash(git *)`，`git status; rm -rf /` 在第 3 步放行，危险
检查根本不执行。**本计划不动 `a` 的匹配方式。**

### 1.2 `s`（本会话）同样按整条命令原文记——本计划要修的缺陷

`_repl.py` 的 `_grant_key` 是 `(session_id, tool_name, request.arguments)`，
而图例写着 `s = allow for this conversation`。对 bash 几乎等于 `y`。

### 1.3 已有的不改代码的出路

`--permission-mode auto-approve`（或 `.env` 的
`OMICSCLAW_PERMISSION_MODE=auto-approve`）。实测：普通命令 allow (mode)，
`rm -rf /`、`git push --force`、`curl … | sh` 仍 ask (danger)。安全含义同 §0。

## 2. 核心难点：REPL 不知道这次询问为什么发生

`s` 放宽到整个工具后，安全性完全取决于"比工具默认策略更具体的询问不被 `s`
覆盖"。但 REPL 收到的 `ApprovalRequest`（`tools/context.py:185-202`，
`frozen=True, slots=True`，五个字段）不带来源——`Resolution.source` 在
`GatedTool.execute` 的**两条** ASK 路径上都丢了：

- 闸门自己问：`gate.py:350-358`，转成 `require_approval(..., reason=...)`；
- **下放给工具问**：`gate.py:347-348`，`self._inner.execute(arguments)`，工具
  用自己的策略调 `require_approval`。

`risk_level` 不能用来区分：危险模式是**替换**风险等级而非抬高
（`gate.py:226`），`git push`、`sudo` 是 MEDIUM，反而低于 bash 默认的 HIGH。

### 2.1 否决的替代方案

| 方案 | 否决理由 |
|---|---|
| REPL 自己跑一遍 `DangerPatterns().inspect(...)` | 危险判定出现第二个读者；部署自定义的危险模式会被漏掉；也管不到 RULE 来源 |
| REPL 经 `app` 重新 `gate.resolve(...)` | 同一决策算两遍，两次之间规则文件可能已被改写 |
| 按 `risk_level` 判断 | 见上，区分不开 |

## 3. 标记怎么传：两条路径都要带（审核后改为必选方案 B）

### 3.1 为什么不是"只在闸门自己问时传"

bash / edit / write / web_fetch / web_search / MCP 工具都声明
`prompts_for_itself=True`，而 `_tool_asks_better`（`gate.py:364-384`）只要来源
**不是 DANGER** 就下放。已由审核探针实测：规则 `ask: ["bash(git push*)"]` 下，
`git push origin main` 得到 `source=rule` 并**下放**，卡片与普通 POLICY 询问
无法区分。

更严重的是它与 §1.1 的叠加：**一条宽 `ask` 规则会吃掉 DANGER 来源**。运维写
`ask: ["bash"]`（本意"bash 每次都问"），`rm -rf /` 就成了下放的 RULE 询问，
不带标记，按一次 `s` 全部静默。**所以下放路径必须带标记，这是安全前提，不是
偏好。**

### 3.2 初稿的方案 A（收窄下放）被否决

初稿推荐"只有 POLICY 才下放，RULE 由闸门问"。审核指出它会**丢掉工具自己更好
的提示**：闸门的理由只有 `permission rule ask 'bash(git push*)'`
（`gate.py:215`），而 bash 的理由含**完整命令**（`bash.py:693-711`，刻意为之：
"A summary is where `; rm -rf ~` hides"），edit/write 含 diff，web_fetch 含 URL。
Channel 只显示 reason（`render.py:356-366`），批准时就看不到命令了。这正是
`tests/permission/test_gate.py:269-292` 两条测试明确要防的退化。

### 3.3 采用方案 B：一条上下文通道，两条路径都设置

`omicsclaw/tools/context.py` 已有闸门→工具的上下文通道
（`use_effective_policy`，`require_approval` 先读它，`context.py:639-650`）。
在同一文件增加一个同形的：

```python
@contextmanager
def ask_every_time() -> Iterator[None]:
    """在这个作用域里发起的审批，不得被任何"以后别再问"的授权代答。"""
```

- `require_approval` 构造 `ApprovalRequest` 时读取它，写入新字段
  `ask_every_time: bool = False`。**不新增 `require_approval` 的参数。**
- `GatedTool.execute` 在两条 ASK 路径上都包一层：闸门自己问（`gate.py:355-358`）
  与下放（`gate.py:347-348`）。
- 置位条件：`resolution.source is not DecisionSource.POLICY`（即 DANGER 或
  RULE；MODE 从不产出 ASK），**或** `policy.approval_mode is
  ApprovalMode.DENY_UNLESS_TRUSTED`（审核补：它在 `gate.py:238-244` 也产出
  POLICY ASK，今天无工具使用，但语义上不该被 `s` 代答）。
- `_tool_asks_better` **不改**，工具的提示内容全部保留。
- 放在 `tools` 层、用中性名字，不引用 `permission`：满足
  `tests/tools/test_tools_is_a_leaf_layer.py`（白名单
  `("omicsclaw.schema", "omicsclaw.tools")`）。
- 生产代码的构造点只有 `context.py:607` 一处；测试里另有 4 处，均用关键字
  参数、依赖默认值（`test_render.py:134`、`test_events.py:185`、
  `test_cli_render.py:159`、`test_approval.py:40`），不受影响。全仓无
  `fields()`/`asdict`/`replace` 作用于 `ApprovalRequest`。

**线协议**：`to_wire` 把 `APPROVAL_REQUIRED` 映射为 `permission_request`
（`render.py:132`、`572-586`），Desktop 在用。**裁定：新字段不投影到 wire**——
Desktop 没有会话授权概念，也没有回传端点，投影出去没有消费者。Channel 同样
没有会话授权，**两者行为不变**。

## 4. 规则文件自我提权（审核发现，初稿未提）

路径：对 bash 按 `s` → 模型执行一条不命中任何危险模式的普通命令
`printf '{"permissions":{"allow":["bash(*)"]}}' > .omicsclaw/settings.json`
→ 下一条 `rm -rf /` 在第 3 步被 RULE ALLOW 放行，**连询问都不会发生**。

成立的原因均已核实：规则文件默认在 `<workspace>/.omicsclaw/settings.json`
（`entry/config.py:418-429`），bash 的 cwd 就是 workspace，`RuleStore.current`
**每次调用都重读文件**（`rules.py:366-376`）。write_file / edit_file 被 `s`
放行后同理。`auto-approve` 模式下这条路**今天就存在**；本计划让它在 default
模式下也能经 `s` 打开。

它比"混淆命令直接删文件"多出的危害是**持久**：写下的规则跨会话生效。

### 4.1 采用的缓解（写进实现）

| # | 措施 | 性质 |
|---|---|---|
| 1 | write_file / edit_file 的目标路径落在 `permission_rules_path()` 或 `<workspace>/.omicsclaw/` 下时，闸门置 `ask_every_time`（路径是这两个工具的 principal argument，判定可靠） | 可靠 |
| 2 | 新增一条内置危险模式：bash 命令中出现 `.omicsclaw`，风险 HIGH，理由"修改 OmicsClaw 自己的权限/状态文件" | 减速带（可被变量拼接绕过），与危险模式整体性质一致 |
| 3 | `RuleStore` 检测到文件被**非本进程 `remember()`** 改动时，打一条 warning（内容：哪些 allow 规则是新出现的） | 可观测性，不阻断——运维中途手改规则文件是正当用法 |

### 4.2 否决的更强方案

"会话期间只认本进程写入的规则、忽略外部改动"：挡不住跨会话（本会话写、下次
启动加载），又会让运维中途手改规则失效。收益小于代价，不做。

## 5. REPL 侧改动（`omicsclaw/entry/cli/_repl.py`）

| 位置 | 改动 |
|---|---|
| `_grant_key` | `(session_id, tool_name)`；`_granted` 的类型标注（`:380`）与 docstring（`:381-385`，今天写着 `s` "grants less than the rule `a` writes"——改后反过来了）同步改 |
| `_already_granted` | `request.ask_every_time` 为真则**一律 False**；docstring（`:1267`）同步 |
| `_ask` 的 `s` 分支 | 标记为真时：本次放行，**不记入** `_granted`，并回显 `request.reason` 的首行说明为何只放行这一次——措辞中性，因为来源可能是 DANGER 也可能是 RULE |
| 图例 | 普通卡片：`s = allow this tool for the rest of the conversation`；**带标记的卡片打印另一种图例**：`s = allow this call only (it is always asked about)` |
| `s` 的提示语 | `Will not ask about bash again in this conversation, except for calls that are always asked about. Nothing was written to disk.`——保留前缀 `Will not ask about {tool} again in this conversation`（`test_cli_approval_scope.py:65` 断言它） |
| `a` 的提示语 | 仅当 pattern 含 `(` 时追加 `(this exact call only; s stops asking about the tool for this conversation)`。`literal_pattern` 参数为空时返回裸工具名（`rules.py:463-464`），那条规则覆盖整个工具，不能写 "exact" |

**子代理的授权与父会话共享**（审核补）：子代理的审批以 `tool_name="bash"`
进入父 REPL（`tests/entry/test_subagent_wiring.py:649-674`），`_grant_key` 用的
是 REPL 的 `session_id`。裁定：**有意共享**——子代理是本会话里由同一个模型
委派的工作，处在同一个信任域；写进 README，不加进 key。

**`/resume` 会恢复旧会话的授权**（`_repl.py:1256-1264`），按工具授权后影响面
更大，写进 README。

## 6. 非目标

- 不改 `a` 的匹配方式（§1.1）。
- 不改 `_tool_asks_better` 与任何工具的提示内容（§3.2）。
- 不加 `/auto` 运行时切换命令。
- 不改 Channel / Desktop 行为，新字段不上 wire。
- 不改 hook 改写参数后不重审的既有问题（`assembly.py:1094-1099` 已自述；
  hook 属运维配置），只在 §8 记一笔。

## 7. 测试

**要改的**

- `tests/entry/test_cli_approval_scope.py:114`：断言
  `"s = allow for this conversation"`，随新图例改。

**预期仍绿（审核已核）**：`test_cli_approval_scope.py:65`（保留前缀）、
`test_cli_repl.py:589` 的 `Remembered: always allow ask({})`（后缀只在含 `(` 时
追加，`ask({})` 含 `(`——**这条要复核**：若追加，断言是子串仍绿）、
`tests/permission/test_gate.py:269-292`（方案 B 不改下放，reason 不变）。

**新增**

| 测试 | 断言 |
|---|---|
| 同工具不同参数 | 按 `s` 后，第二条不同参数的普通调用不再询问 |
| 危险命令不被 `s` 覆盖 | 按 `s` 后 `rm -rf /` 仍询问 |
| 危险命令上按 `s` | 本次放行、不记入授权；下一条普通命令**仍询问**；卡片打印"只放行这一次"的图例 |
| **宽 ask 规则不遮蔽危险**（M1 的核心用例） | 规则 `ask: ["bash(*)"]`，按 `s` 后 `rm -rf /` 仍询问 |
| 非危险的 RULE ask | 规则 `ask: ["bash(pip install*)"]`，按 `s` 后 `pip install x` 仍询问——**不用 `git push`，它本身命中危险模式，会把两件事混在一起** |
| 下放路径带标记 | RULE 来源、`prompts_for_itself` 工具：`ApprovalRequest.ask_every_time is True` 且 `reason` 仍是工具自己的 |
| 闸门路径带标记 | DANGER 来源同上 |
| POLICY 不带标记 | 普通 bash：`ask_every_time is False` |
| `DENY_UNLESS_TRUSTED` | 带标记 |
| 规则文件路径 | write_file 写 `.omicsclaw/settings.json`：带标记；bash 命令含 `.omicsclaw`：DANGER |
| 外部改动告警 | 规则文件被外部加入 allow 规则后，下一次 `current` 打出 warning |
| 叶子层 | `test_tools_is_a_leaf_layer.py` 保持绿 |

## 8. 风险

| 风险 | 缓解 |
|---|---|
| `s` 放行 bash 后，混淆写法的破坏性命令不被拦 | **不可缓解于本层**：危险模式是黑名单。§0 已向 owner 说明；真正的边界是沙箱 |
| 模型改写规则文件实现持久提权 | §4.1 三项；写入 README |
| 宽 ask 规则遮蔽危险来源 | §3.3 两条路径都带标记；专门测试 |
| 实现时只在闸门路径设置标记、漏了下放路径 | 这是最可能翻车的一处；"下放路径带标记"与"宽 ask 规则"两条测试专门守它 |
| hook 在闸门之后改写参数，危险检查按改写前的做 | 既有问题（`assembly.py:1094-1099`），`s` 放宽后影响面变大；记录，不在本计划修 |
| 参数名不叫 `command` 的 MCP shell 类工具没有危险检查（`gate.py:219`） | `s` 一次即全开；写进 README |
| 回滚 | 删字段、上下文通道与 REPL 三处判断即回到按原文授权 |

## 9. 验证

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest \
  tests/permission tests/tools tests/entry -q -p no:randomly \
  -p no:cacheprovider -o addopts=""
```

再跑 `AGENTS.md` 的整栈命令（审核记录的相关基线：556 条今天全绿）。手工验收：
连续三条不同的普通 bash，第一条按 `s`，后两条不再询问；`rm -rf` 类命令仍询问；
让模型尝试写 `.omicsclaw/settings.json`，仍询问。

## 10. 文档同步

`AGENTS.md:510`（今天写着 "`s` allows that exact call"，与新行为直接矛盾）、
`CLAUDE.md:262`、`README.md:218` 的三种授权说明；README 另记 §5 的子代理共享与
`/resume`、§8 的 MCP 说明。

## 11. 审核记录（2026-09-23，一轮独立只读审核）

结论"需修改后实施"。四条必须修正均已落地：

| # | 审核发现 | 落在 |
|---|---|---|
| M1 | 宽 RULE `ask` 会遮蔽 DANGER，初稿"选项 C"是真实旁路 | §3.1；删除 C；新增"宽 ask 规则"测试；RULE 用例换成非危险命令 |
| M2 | `s` 放行 bash 后可静默改写规则文件，持久绕过危险模式 | 新增 §0、§4 |
| M3 | 初稿推荐的方案 A 会丢掉工具自己的提示（含完整命令），且影响 Channel | §3.2 否决 A；§3.3 改用 B |
| M4 | "已有测试无需修改"不成立；三处文档矛盾 | §7、§10 |

建议补充中采纳：`DENY_UNLESS_TRUSTED`、子代理共享（裁定为有意共享并写明）、
hook 改写参数（记入风险）、REPL 细节五项、gate docstring、§2 两处描述更正、
Desktop wire 表述更正、`/resume`、MCP 无危险检查。

我另行复核属实的：`permission_rules_path` 默认值（`config.py:418-429`）、
`RuleStore.current` 每次重读（`rules.py:366-376`）、bash 理由含完整命令
（`bash.py:693-711`）、`test_gate.py:269-292` 钉住下放时的 reason、
`resolve` 第 3 步先于第 4 步。

## 12. 待 owner 裁定

1. **§0 的安全含义是否接受**：`s` 放行 bash ≈ 本会话内对 bash 开 auto-approve，
   危险模式是黑名单、沙箱才是边界。
2. §4.1 的三项缓解是否足够（倾向：足够，更强方案见 §4.2 的否决理由）。
3. §5 子代理共享授权（倾向：共享）。

## 13. 交付记录（2026-09-23）

§12 三项按建议裁定：接受 §0 的安全含义；§4.1 缓解足够；子代理共享授权。

### 13.1 与计划的一处偏离：保护 `.omicsclaw/` 做成了规则之前的独立阶段

计划 §4.1 第 1、2 项写的是"write/edit 置 `ask_every_time`"与"bash 加一条危险
模式"。实现时发现两者都**挡不住 `auto-approve` 模式**：该模式在第 5 步直接
放行无规则、无危险命中的调用，**根本不产生询问**，标记无处可读——而 0050 的
`/auto` 会让这个模式变得常用。第 2 项的危险模式还排在规则之后，一条
`allow: bash(*)` 就能绕过。

改为 `PermissionGate.resolve` 的 **2½ 阶段**（`DecisionSource.PROTECTED`）：
非只读工具的 principal argument 含 `.omicsclaw` 或规则文件路径时一律 ASK，
**先于规则与模式**，并置 `ask_every_time`。它严格强于原计划：

- `auto-approve` 下仍询问；`allow` 规则打不开它（受保护的正是规则文件）；
- 只读工具（读计划、读 memory）不受影响；
- `bypass-all` 仍然绕过——该模式的定义就是"不检查"；
- 理由文本附上 principal argument，且 `_tool_asks_better` 不下放
  PROTECTED，所以 Channel 用户批准时也看得到完整命令。

第 2 项的危险模式因此不再需要，未添加。第 3 项（外部写入 `allow` 规则告警）
按计划实现于 `RuleStore.current`，本进程 `remember()` 写入的不告警。

### 13.2 顺带修掉的既有缺陷

`_repl.py` 的 "Remembered: always allow …" 以 rich markup 字符串打印规则模式，
而 `literal_pattern` 正是用 `[*]`、`[?]`、`[[]` 转义通配符——rich 会把它们当
样式标签吞掉，屏幕上显示的规则与写进文件的不一致。改为 `Text`。

### 13.3 测试

新增 `tests/permission/test_ask_every_time.py`（13 项：各来源的标记、下放时保留
工具自己的提示、宽 `ask` 规则不遮蔽危险、`DENY_UNLESS_TRUSTED`、标记不泄漏、
受保护目录在 `auto-approve` 与 `allow` 规则下仍询问、只读不受阻、自定义规则
文件路径、外部改动告警）；`tests/entry/test_cli_approval_scope.py` 新增 4 条端到端
（`s` 覆盖同工具不同命令、不覆盖危险命令、危险命令上按 `s` 只放行一次、宽
`ask` 规则在 `s` 之后仍询问）并更新图例断言；`tests/tools/test_tools_is_a_leaf_layer.py`
的导出清单加入 `ask_every_time`（该测试有意让扩大包表面必须改它）。

### 13.4 交付后发现并修补的漏洞：`.env`（2026-09-23，0050 审核发现）

§13.1 只保护了 `.omicsclaw/` 与规则文件。0050 的审核用探针证明 `.env` 同样
决定权限姿态，且**这个洞是 0049 打开的**：

| 模式 | 写 `.env` 设 `bypass-all` |
|---|---|
| default（0049 之前） | 每条 bash 都要人批准，卡片上有完整命令 |
| default + 对 bash 按过 `s`（0049 之后） | POLICY 询问，**被 `s` 静默放行** |
| auto-approve | 第 5 步直接放行（0049 之前即存在） |

`bypass-all` 在第 1 步判定，先于一切检查，所以一次不受监督的写入就让下次启动
全部失效；同一文件里的 `LLM_BASE_URL` 还决定 API key 发往哪里。

修补（owner 裁定"保护决定权限姿态的文件"）：受保护阶段增加 `DOTENV_NAME`，
按文件名匹配 `.env` 类文件，bash 命令与文件工具路径同一规则。界线是"决定
OmicsClaw 自己问不问的文件"——规则文件与 `.env`；`SOUL.md`/`CLAUDE.md`（影响
提示词）、`.git/hooks`、`~/.bashrc` 这类通用持久化点不纳入，它们无法枚举，只有
沙箱能兜底。代价：bash 里提到 `.env.example` 也会询问。新增 9 项测试。

### 13.5 实现后代码审查的修复（2026-09-23，与 0050 一并审查）

受保护阶段改为不区分大小写、自定义规则文件另按文件名识别、只看写入类参数；
受保护卡片不再提供 `a`（其规则永远不会被读取）。详见 0050 §11。
