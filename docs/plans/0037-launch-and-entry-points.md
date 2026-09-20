# 0037 —— 启动方式：进程外壳与入口点的重新设计

状态：**已实现并已过两轮独立评估**（2026-09-20）。本文前七节仍是原稿的设计
探索——现状实测、问题陈述、三个候选方案的取舍、推荐方案；**附录 A 是实现方的
交付报告，附录 B 是评估发现的处置**。原状态行写的是「不是实现计划……实现是
另一份计划的事」，那句话在附录 A 出现的那一刻就不再成立，却留了下来——**一份
自述过期的规格书，比没有状态行更贵**，因为读者会按它决定要不要读下去。

owner 于 2026-09-20 给了两条裁定，第二条收窄了第一条的解空间：

1. 旧的启动方式要按新框架重新设计，判据是「保持高内聚低耦合」。
2. **入口只保留 cli、channel、desktop 三个**，`oc run <skill>` 这种进法不保留。

上游：`docs/plans/0031-entry-layer.md`（第 6 步，已交付）、
`docs/FRAMEWORK-REBUILD.md`（第 6 步「Two rulings」第 1 条即本文的起因）。
本文同时处置 0031 §10-4 —— 那条要求「写死 `oc run <skill>` 与 `omicsclaw.entry`
两个入口的分工」。**在第二条裁定之后它被取消而不是回答**，理由见 §2 问题 3。

---

## 1. 现状清点（2026-09-20 实测，不是回忆）

### 1.1 进程能从几个地方进来

| 入口 | 落点 | 归属 | 今天能跑吗 |
|---|---|---|---|
| `omicsclaw` / `oc`（console script） | `omicsclaw.surfaces.cli.launcher:main` → `_main.py` | 旧 | ❌ `ModuleNotFoundError: omicsclaw.skill` |
| `omicsclaw-chat` / `oc-chat`（console script） | `omicsclaw.surfaces.cli:main` | 旧 | ⚠️ 能 import |
| `python omicsclaw.py <args>` | 同 `_main.py` | 旧 | ❌ 同上 |
| `python -m omicsclaw.surfaces.channels --channels …` | 旧 Channel runner（`argparse`） | 旧 | 未核实 |
| `python -m omicsclaw.entry.cli [dep] -- [surface]` | 新入口层的 REPL / RunOnce | **新** | ✅ |
| `python -m omicsclaw`（`omicsclaw/__main__.py`，7 行） | 同 `launcher:main` | 旧 | ❌ 同上 |

> **这张表原本只有五行，漏掉的正是第六行**（评估补入，2026-09-20）。
> `omicsclaw/__main__.py` 一直存在，落点和 `oc` 一样已死。清点表上漏掉的那一
> 条，正好是没人敲过的那一条——与 §1.4-3 的教训互为对偶。它已在交付后被重
> 指向 `omicsclaw.launch:main`，见 §A.4-1。

**六种进法里有三种今天就是坏的**，因为 `_main.py` 在模块作用域 import 了被
owner 删除的 `omicsclaw.skill`。这不是本文要修的缺陷，但它改变了迁移的形状
（§7）——**没有正在跑的东西需要被保护。**

`pyproject.toml` 的 `[project.scripts]` 是 4 行 2 个落点。`_main.py` 有
**35 个 `add_parser`**（`run` / `list` / `replay` / `interactive` / `tui` /
`desktop-server` / `memory-server` / `mcp` / `project` / `knowledge` /
`onboard` / `doctor` / `optimize` / `replot` / `auth` / `control` / …）。

### 1.2 新层这边的实际形态

- `omicsclaw/entry/cli/` **有** `__main__.py`（手写解析器，5 个 flag，在 `--`
  处切开）。
- `omicsclaw/entry/channel/` 与 `omicsclaw/entry/desktop/` **一个进程入口都
  没有**。它们导出的是库形状的工厂：`compose_channel_runtime(...)` /
  `ChannelManager` / `create_desktop_app(...)` / `health_payload(...)`。

**这个不对称就是问题的形状**：三个面里有两个是纯库，一个顺带是个进程。

### 1.3 Q8 的单一解析点，与它现在的两个豁免

`resolve_app_config(argv=None, env=None, **overrides)` 是全进程唯一读
`sys.argv` / `os.environ` 的函数（唯一声明例外：`provider_from_env` 读自己的
API key）。纪律由源码扫描测试
`tests/entry/test_config.py::test_no_other_entry_module_reads_the_environment`
执行，豁免名单是 `_COMMAND_LINE_ENTRY_POINTS = ("__main__.py",)`，且**只豁免
argv 那一半**。

### 1.4 三条不能动的东西（先写在前面，免得方案撞上去）

1. **根 `omicsclaw.py` 不能删。** 它是 source-checkout 哨兵。实测活着的消费者
   有两个：`omicsclaw/common/workspace.py:69`（`(candidate / "omicsclaw.py").is_file()`）
   与**外部客户端** `OmicsClaw-App/electron/python-env.ts:56`
   （`isOmicsClawSourceCheckout`）。
   > 顺带一笔：`omicsclaw.py` 自己的 docstring 列了四个消费者，其中
   > `omicsclaw/execution/executors/default.py` 与 `omicsclaw/runtime/agent/state.py`
   > **已随旧架构被删**。那段 docstring 该修，但哨兵结论不变。
2. **Desktop 的线路契约已发布、带版本号。** 8 个 `*_SCHEMA_VERSION` 与路由是
   外部客户端依赖的协议（0031 §9-14 要求逐字节相同）。启动方式怎么改都不许
   碰到它。
3. ~~**`oc` 这个名字今天就有人在用**~~ —— **实测作废**：`oc` 今天敲下去是一个
   `ModuleNotFoundError`（§1.1）。这条本来是最强的约束，核实之后它变成了最强的
   **许可**：重指向 `oc` 不需要兼容层（§7）。
   > 这条值得单独记一笔：**约束清单上最贵的那一条，正好是没核实过的那一条。**

---

## 2. 问题陈述

**问题 1：进程入口是它所启动的那一层的成员。**
`entry/cli/__main__.py` 住在 `entry/` 里，于是这一层必须自己读 `sys.argv`，
于是纪律测试必须开豁免。豁免不是错的，但它是个信号：**这一层被塞进了一件不属于
它的职责**。入口层的内聚定义是「装配并驱动 agent」，而「是一个进程」——
argv、环境、退出码、信号、stdio 归属——是另一件事。

**问题 2：新框架给 Channel 与 Desktop 留了库，没留进程。**
今天要把新的 Channel 跑起来，没有命令可敲。若照 CLI 的做法各补一个
`__main__.py`，豁免从 1 个文件变 3 个，问题 1 乘以三。

**问题 3：入口在累积，不在收敛。**
今天有五种进法（§1.1），而它们不是被设计出来的，是一层一层叠上来的：每加一个
面、每加一个子命令族，就多一种。0031 §10-4 把这件事记成「要写死 `oc run <skill>`
与 `omicsclaw.entry` 两个入口的分工」，因为它预判了「下一个人会试图把它们合并」。

> **owner 裁定（2026-09-20）：`oc run <skill>` 这种进法不保留，只留 cli、
> channel、desktop 三个。**
> 于是 §10-4 那条不再需要回答——**它被取消了**。新框架下只有一族入口：agent
> 的三个面。确定性技能执行不消失，但它不再是一种「进法」：它是 agent 在会话里
> 做的事，以及面内命令（`entry/cli/_slash_command_support.py` 已有 `/run`、
> `/skills`、`/doctor`，`entry/channel/commands/builtins.py` 已有 `/demo`、
> `/skills`、`/status`）。**少一个顶层名字，比给两个顶层名字划清界线更便宜。**

---

## 3. 判据：这件事上的「高内聚低耦合」具体是什么

不写成形容词，写成可证伪的四条：

1. **进程的知识只在一个地方。** 全仓库 `sys.argv` 的生产用法可数，且都在同一个
   包里；`os.environ` 仍由 `resolve_app_config` 独占（加 `provider_from_env`
   这一条声明例外）。
2. **依赖单向。** 外壳 import 入口层；入口层**不知道外壳存在**，一条反向分层
   探针钉住。
3. **三个面对称。** CLI / Desktop / Channel 在启动这件事上形状相同，都是「外壳
   调一个工厂」，没有哪个顺带是个进程。
4. **入口只有一族，且这件事是可枚举的。** 全仓库的进程入口恰好三个，一条测试
   把它们列出来；第四个想出生，得先让那条测试变红。

---

## 4. 三个候选方案

### 方案 A —— 每个面各补一个 `__main__.py`

`entry/{cli,channel,desktop}/__main__.py`，各自小而薄。

- ✅ 改动最小；与 harness9 的形状一致；与现有 `python -m omicsclaw.surfaces.channels`
  的用户习惯一致。
- ❌ 判据 1 破（三处 argv）、判据 3 破（三个面各自是进程）、判据 4 半破：
  入口确实是三个，但它们**没有一张表**——想知道有几个只能 grep
  `if __name__`，而「第四个想出生要先让一条测试变红」这件事无处落地。
- ❌ 豁免名单从 1 变 3，而豁免名单变长是这套纪律唯一会退化的方式。

### 方案 B —— 把 `python -m` 入口挪回 `pyproject.toml` 的 `oc`

即 FRAMEWORK-REBUILD 里记的第二个选项：迁移期重新指向 `oc` 控制台脚本。

- ✅ `entry/**` 立刻零 argv。
- ❌ **把新层的启动权交回了 `_main.py`** —— 那是 35 个子命令、焊在第②③族上的
  旧文件。等于用「新层不许有进程」换来「新层的进程由旧层提供」，耦合方向反了。
- ❌ 判据 2 破得最彻底。

### 方案 C —— 进程外壳独立成层，位于 `entry/` 之上 ✅ **推荐**

新增 `omicsclaw/launch/`：一个只负责「是一个进程」的薄层。

- ✅ 四条判据全过。
- ✅ 三个面回到纯库，`entry/cli/__main__.py` 删除，豁免名单清空。
- ✅ 给了 `oc` 一条**可测量**的收敛路径（见 §7）。
- ❌ 多一个包，多一层名字。代价真实，但它换掉的是三个豁免加一个反向依赖。

---

## 5. 推荐方案的形状

### 5.1 目录

```
omicsclaw/launch/
├── __init__.py    # main(argv=None, env=None) -> int
│                  # 全层唯一出现 sys.argv / os.environ 的文件
├── __main__.py    # python -m omicsclaw.launch  的三行
├── _grammar.py    # 命令表：名字 -> 消费 (deployment argv, surface argv) 的函数
└── _surfaces.py   # 三个面的启动函数，只 import entry/ 的公开名字
```

> 原稿这张表把 `__main__.py` 注成「`python -m omicsclaw` 的三行」，但 `python
> -m omicsclaw` 跑的是**根包的** `omicsclaw/__main__.py`，它不在这张目录表
> 里。这一行是 `python -m omicsclaw.launch`。两个文件今天都存在，都落在同一个
> `main()` 上（§A.4-1），但它们是两个文件。

依赖方向：`launch → entry → {context, skills, tools, engine, provider, schema}`。
`entry` 不 import `launch`，由探针钉住。

### 5.2 命令语法：三个命令，一个面一个

沿用第 6 步已经证明好用的那条规则——**在 `--` 处切开，两侧有不同的主人**：

```
oc <surface> [deployment flags] [-- surface flags]

oc cli                                      REPL
oc cli -- --prompt-file brief.md            单次执行（harness 的 RunOnce）
oc desktop                                  Desktop 后端（entry/desktop）
oc channel -- --channels telegram,feishu    IM 面（entry/channel）
```

**命令名就是子包名**，一一对应 `entry/{cli,desktop,channel}/`，没有第四个。
`--` 左边永远原样交给 `resolve_app_config`；右边永远交给那个面自己的解析器。
这条规则在第 6 步已经有测试站岗（`test_a_surfaces_own_flags_go_after_the_terminator`），
外壳只是把它从一个面推广到三个。

判据 4 的落地形式：`_grammar.py` 的命令表是**一个三元组常量**，一条测试断言
它的键恰好是 `{"cli", "desktop", "channel"}`，且每个值指向的模块都在
`omicsclaw/entry/` 下。

### 5.3 那 35 个旧子命令去哪：进面内，不进顶层

owner 裁定取消了「两族入口」，于是 `_main.py` 的 35 个子命令不能再指望有一个
顶层位置。它们分三类，各有去处，~~**而且两条路今天就已经修好了一半**~~：

> **「修好了一半」这个说法过强，实测作废**（评估，2026-09-20）。下表用
> 「`_slash_command_support.py` 已列 `/run` `/skills`」来支撑它，但**列在目录里
> ≠ 实现了**：`CLI_SLASH_COMMAND_SPECS` 有 **38** 条规格，
> `REPL_SLASH_COMMAND_SPECS` 只有 **9** 条（`/clear /current /exit /help /mcp
> /new /sessions /skills /usage`）。`/run` `/doctor` `/context` `/memory`
> `/export` 等 29 条敲下去得到的是一条拒绝——那条拒绝路径本身是好的、是有意
> 的（0031 §5.1 封了四个族），而且现在有测试站岗
> （`test_the_commands_plan_0037_called_half_done_are_refused`）。
> **一张目录不是一条通路。** 下表的「去处」一栏仍然成立，它说的是应该去哪，
> 不是已经到了。

| 类别 | 例子 | 去处 |
|---|---|---|
| agent 在会话里能做的 | `run` / `replay` / `list` / `replot` / `optimize` | agent 自己调技能；用户想显式点名就用面内命令 —— `entry/cli/_slash_command_support.py` 已列 `/run` `/skills`，`entry/channel/commands/builtins.py` 已注册 `/demo` `/skills` |
| 会话与工作区管理 | `project` / `knowledge` / `memory-server` / `doctor` / `onboard` | 面内命令（CLI 那张表已有 `/sessions` `/doctor` `/memory` `/context` `/export`），或 Desktop 的 HTTP 端点 |
| 部署配置 | `mcp add/remove/list` / `auth` | 配置文件（`.mcp.json` 已经是这条路）与部署 flag，不是命令 |

**这不是把 35 个命令搬家，是承认其中大部分本来就不该是进程入口。**
一个需要先起 agent 才有意义的操作（`/context`、`/memory`、`/compact`）做成顶层
子命令，代价是它每次都要重新装配一遍五层；做成面内命令，它复用已经开着的那个
`AgentApp`。

**但有一笔债必须点名，不许静默**：今天 `oc run <skill> --demo` 出现在
`README.md` 的 Quick Start、`CLAUDE.md` 的整张 CLI Reference、以及 CI（「repeats
the published run-derived Skill twice through the real shared runner」）。
取消这个顶层入口意味着 **CI 与文档需要一条非 CLI 的确定性执行通路**——库 API
或面内命令二选一。这条留给 §9-3。

### 5.4 最漂亮的一步：把 `entry/` 的 argv/env 清零

`resolve_app_config(argv=None, env=None)` 的两个默认值，是这个函数唯一需要
`import sys` / `import os` 的原因——它本身是个纯函数。外壳一旦总是显式传参，
默认值就可以去掉，于是：

- `config.py` 不再 import `sys` / `os`；
- `test_no_other_entry_module_reads_the_environment` 的**两个豁免全部消失**，
  规则从「除 config.py 与 `__main__.py` 外」变成一句平的「`omicsclaw/entry/**`
  不出现这三个名字」；
- 那两个参数从「为测试而存在的注入口」升级为生产路径上的正常调用——
  **注入口只在测试里被用，本身就是一个设计还没走完的信号。**

唯一不变的是 `provider_from_env` 仍读自己的 key（0031 Q8 的声明例外，理由是
让密钥穿过 dataclass 只会多一个能被打印出来的地方）。

新增一条同形状的探针看住新层：`omicsclaw/launch/**` 里 `sys.argv` 只许出现在
`__init__.py` 的 `main()` 默认值处，`os.environ` 一次都不许出现。

---

## 6. 与 `omicsclaw.py` 和四个 console script 的关系

- **根 `omicsclaw.py` 保留**（§1.4-1），但它的 `from … import main` 改为指向
  `omicsclaw.launch:main`，并修掉 docstring 里两个已失效的消费者。
- `[project.scripts]` 从 4 行收敛到 2 行：`omicsclaw` 与 `oc` 都指向
  `omicsclaw.launch:main`。
- `omicsclaw-chat` / `oc-chat` **在迁移完成时删除**——`oc cli` 已经是同一件
  事，留着是第四个名字。
- `python -m omicsclaw.entry.cli` **不保留兼容别名**。它正是这次要消除的那类
  入口；留一个别名等于留下它。
- `python -m omicsclaw.surfaces.channels` 随旧 `surfaces/` 一起消失，由
  `oc channel` 接替。

---

## 7. 迁移：~~前置分发器~~ —— **不需要，因为旧 CLI 已经死了**

> ### ⚠️ 实测推翻了本节的原稿（2026-09-20）
>
> 原稿写的是「目标态只有三个命令，但到达目标态那天不能是某个早上 `oc list`
> 不认识了」，于是设计了一个**前置分发器**：认识三个新命令，其余原样转交
> `_main.py`。
>
> **这个前提是假的。实测：**
>
> ```
> $ python omicsclaw.py list
> ModuleNotFoundError: No module named 'omicsclaw.skill'
>
> $ python -c "import omicsclaw.surfaces.cli._main"
> ModuleNotFoundError: No module named 'omicsclaw.skill'
> $ python -c "import omicsclaw.surfaces.cli.launcher"   # oc / omicsclaw 的落点
> ModuleNotFoundError: No module named 'omicsclaw.skill'
> ```
>
> `_main.py` 在**模块作用域**import 了 `omicsclaw.skill`（单数，旧的 40 模块
> 技能系统，owner 于 2026-09-19 删除）。所以 `oc` / `omicsclaw` /
> `python omicsclaw.py <任何子命令>` 今天**全部在 import 阶段就崩**。
> 唯一还能 import 的是 `omicsclaw.surfaces.cli`（`oc-chat` 的落点）。
>
> **`oc list` 不是「将要停」，是已经停了。** 分发器要保护的东西不存在。

于是迁移简单得多：

- **`[project.scripts]` 可以第一天就重指向 `omicsclaw.launch:main`**，而且这是
  **严格的改善**——今天敲 `oc` 得到一个 `ModuleNotFoundError`，改完得到一个能
  跑的 CLI。没有「可能弄坏什么」这一问，因为没有什么是好的。
- **不建 `_delegate_to_legacy`，不建 `_LEGACY_COMMANDS`。** 新外壳一行都不
  import `omicsclaw.surfaces`，一条测试钉住这件事。原稿为这条耦合设计的三点
  缓解措施随之全部作废——**最好的缓解是不产生那条耦合。**
- 那 35 个子命令的处置从「搬走还在跑的东西」变成 **「决定让哪些回来」**：按
  §5.3 三选一（进面内命令 / 变配置 / 不回来）。**必须先把 35 个名字列成一张
  清单**，否则「让哪些回来」会退化成「谁想起来算谁」，而一个已经崩了的命令
  和一个被决定不要的命令，在 `git log` 里长得一模一样。

解锁顺序仍沿用 0031 §10-2b 按实测改动量排出的那条，而不是直觉：
Channel（13 行）→ Desktop `/chat/stream`（4 行）→ CLI REPL 的 agent 半边。

解锁顺序沿用 0031 §10-2b 按实测改动量排出的那条，而不是直觉：
Channel（13 行）→ Desktop `/chat/stream`（4 行）→ CLI REPL 的 agent 半边。

---

## 8. 验收判据（给将来那份实现计划）

1. `omicsclaw/entry/**` 对 `sys.argv` / `os.environ` / `os.getenv` **零命中**，
   豁免名单为空。
2. 反向分层探针：`omicsclaw.entry` 的任何模块不得 import `omicsclaw.launch`。
3. ~~迁移期内 35 个旧子命令行为不变~~ **作废（§7）：它们今天全部在 import 阶段
   就崩，没有「不变」可以对比。** 取而代之：交付一张 35 行的清单，逐条标注
   「面内命令 / 配置 / 不回来」，作为「让哪些回来」这件事的可核对基准。
   这张清单是文档交付物，不是代码。
4. **三个面各有一条真进程冒烟，由真 provider、真 `__main__` 跑出来**：
   `oc cli` 喂一行输入、`oc desktop` 起来后 `/health`、`oc channel --list`。
   > 这一条是第 6 步最贵的一课的直接后果：那次 619 条测试全绿而真命令一跑就
   > 崩，因为替身比协议宽。**一个启动方案的验收只能由真进程给出。**
5. `omicsclaw.py` 仍在，且两个哨兵消费者（`common/workspace.py:69`、
   App 的 `python-env.ts:56`）仍判定为 source checkout。
6. Desktop 的 8 个 `*_SCHEMA_VERSION` 与路由逐字节不变。
7. **入口可枚举**：`_grammar.py` 的命令表键恰好是
   `{"cli", "desktop", "channel"}`，且全仓库（迁移完成后）再无第四个进程入口
   ——`grep -rn "if __name__" omicsclaw/` 与 `[project.scripts]` 一起核。

---

## 9. 未决（留给 owner 或实现计划）

1. **包名**：`omicsclaw/launch/` 还是 `omicsclaw/cli/`？后者更常见，但
   `cli` 在这个仓库里已经是「三个面之一」的名字（`entry/cli/`），复用会让
   「哪个 cli」变成一个需要问的问题。本文按 `launch/` 写。
2. ~~**`oc serve` 这一级要不要**~~ **不要了。** owner 裁定入口只有三个面之后
   就没有可分组的东西了：`oc cli` / `oc desktop` / `oc channel`，命令名就是
   子包名，一一对应。
3. **CI 与文档的确定性执行通路。** 取消 `oc run <skill>` 这个顶层入口之后，
   两个地方会断：`README.md` 的 Quick Start 与 `CLAUDE.md` 的整张 CLI Reference
   都在教 `oc run <skill> --demo`；CI 还会「用真 shared runner 把已发布的
   run-derived Skill 重跑两遍」。**这条必须在动手之前有答案**，二选一：
   (a) 库 API —— CI 直接调 `RunRuntime`，命令行不是它的依赖；
   (b) 面内命令 —— CI 走 `oc cli -- --prompt-file`，代价是确定性验证从此要经过
   一个 agent，**而那正好是它想避开的东西**。倾向 (a)。
4. **面内命令的归属还没有层。** §5.3 把 35 个子命令中的两类推进「面内命令」，
   但 CLI 与 Channel 今天各有一套自己的注册表
   （`_slash_command_support.py` 与 `channel/commands/_registry.py`），
   Desktop 一套都没有。三个面各写一遍 `/doctor` 是这个方案最可能长出的冗余，
   实现计划要先回答它。

---

## 附录 A —— 交付结果

**方案 C 已实现（2026-09-20）。** 新增 `omicsclaw/launch/`（4 文件 / 992 行）
与 `tests/launch/`（4 文件 / 1,118 行）；`omicsclaw/entry/cli/__main__.py`
删除，`resolve_app_config` 的两个默认值去掉，`entry/**` 对三个名字零命中、
豁免名单为空；`[project.scripts]` 从 4 行收敛到 2 行，都指向
`omicsclaw.launch:main`。**`omicsclaw/surfaces/` 一行未改**，Desktop 的 8 个
`*_SCHEMA_VERSION` 与两条路由逐字节未动。

### A.1 实测数字

| | 开工前基线（2026-09-20 03:05） | 交付后（03:46） |
|---|---|---|
| `tests/entry/` | 620 passed, 1 skipped | **636 passed, 1 skipped** |
| `tests/launch/` | （不存在） | **56 passed, 1 skipped** |
| `tests/entry/` ＋ `tests/launch/` 合跑 | — | **692 passed, 2 skipped** |
| `tests/{schema,provider,engine,tools,context,skills}` | 2,089 passed | **2,090 passed** |

```bash
P=/opt/conda/envs/rapids_singlecell/bin/python
$P -m pytest tests/entry/ tests/launch/ -p no:cacheprovider -q -o addopts=""
$P -m pytest tests/schema tests/provider tests/engine tests/tools tests/context \
   tests/skills --ignore=tests/tools/test_workspace.py -p no:cacheprovider -q -o addopts=""
```

`tests/entry/` 的 620 → 636 **不全是本任务的**：本任务对它的净贡献是 **−13**
（删 `test_cli_main.py` 的 17 项，加 `test_cli_optional_dependencies.py` 的 3 项
与 `test_config.py` 的 2 项，`test_entry_is_the_top_layer.py` 的逐模块参数化因
少一个模块而 −1）。其余 **+29** 来自另一个并发会话（`docs/plans/0038-permission-layer.md`，
本任务开工后于 03:20 出现在树上），证据是 mtime：
`tests/entry/test_permission_wiring.py` 03:09（本任务取基线 03:05 之后、首次
改动 `tests/` 03:24 之前）、`omicsclaw/entry/assembly.py` 03:30、
`omicsclaw/entry/cli/_repl.py` 03:31、`tests/entry/test_cli_repl.py` 03:37——
最后三个都在本任务已经停止改动 `entry/` 之后。其余重建栈的 2,089 → 2,090 同理。
**这棵树在交付时仍有另一个会话在写**，所以这些数会继续漂；可核对的是本任务
自己的 −13，以及 `tests/launch/` 的 56。

> **这张表已经漂过一轮**（评估，2026-09-20）。处置之后 `tests/launch/` 是
> **165 passed, 1 skipped**（6 个文件），`tests/entry` ＋ `tests/launch` 合跑是
> **808 passed, 2 skipped**，其余重建栈是 **2,093 passed**。行数也变了：
> `omicsclaw/launch/` 四文件 1,443 行，`tests/launch/` 六文件 2,672 行。
> **一张写死数字的表，寿命等于下一次有人改代码。** 见 §B 的表。

### A.2 逐条对照 §8 验收判据

| # | 判据 | 结论 | 依据 |
|---|---|---|---|
| 1 | `entry/**` 对三个名字零命中，豁免名单为空 | **过** | `tests/entry/test_config.py::test_no_entry_module_reads_the_environment`（规则已拍平）与 `::test_the_exemption_list_is_empty`（`_EXEMPT = ()`）。注意规则是**含散文的**原文扫描，所以 `config.py` 的 docstring 一并改写——它本来也已经错了（那个函数不再读任何东西） |
| 2 | 反向分层：`entry` 不得 import `launch` | **过** | `tests/launch/test_launch_is_above_entry.py::test_no_entry_module_imports_the_shell`（AST，解析相对 import）＋ `::test_importing_the_entry_layer_does_not_load_the_shell`（子进程 `sys.modules`，四个目标） |
| 3 | 35 行清单 | **过** | 见 §A.5。**只是建议，最终由 owner 定** |
| 4 | 三个面各一条真进程冒烟 | **两过一未核实** | 见 §A.3 |
| 5 | `omicsclaw.py` 仍在，两个哨兵消费者仍成立 | **过** | `tests/launch/test_grammar.py::test_the_repo_root_sentinel_still_points_at_this_shell`（真子进程跑 `python omicsclaw.py channel -- --list`）＋`::test_the_sentinel_is_still_recognised_as_a_source_checkout`（真调 `resolve_omicsclaw_dir`）。外部客户端 `python-env.ts:56` 实读过，判据只是 `fs.existsSync('omicsclaw.py') && fs.existsSync('omicsclaw/')`，文件仍在 |
| 6 | Desktop 8 个 `*_SCHEMA_VERSION` 与路由逐字节不变 | **过** | `omicsclaw/entry/desktop/` 一个字节未改；八个值全是 `1`，`SERVED_PATHS == ('/chat/stream', '/health')`，`tests/entry/test_desktop_wire_contract.py` 全绿 |
| 7 | 入口可枚举 | **过（有一条声明债）** | `tests/launch/test_grammar.py::test_the_entry_points_are_exactly_three`、`::test_the_process_entry_points_in_the_tree_are_the_named_ones`（AST 找 `__main__` 守卫，不是 grep）、`::test_the_console_scripts_land_on_this_shell`（解析 `pyproject.toml`）。债见 §A.4-1 |

### A.3 §8-4：三条真进程冒烟

| 面 | 命令 | 结果 |
|---|---|---|
| CLI | `env -i … python -c "from omicsclaw.launch import main; sys.exit(main())" cli --workspace /tmp/smoke_ws`，stdin 喂一行 | **过**。横幅、上下文行、`Failed: ProviderError`、`Goodbye!`，退出码 0。本机无 key、无网络，止于 `ProviderError` 是预期结果。用 `-c` 形式是因为本仓库未 `pip install`，控制台脚本不在 PATH，而 `-c` 跑的正是 `[project.scripts]` 会跑的那两行 |
| Channel | `python -m omicsclaw.launch channel -- --list` | **过**。九个适配器，状态从 `Channel.authoritative_ingress` 类属性读（telegram/feishu = authoritative，其余七个 disabled），退出码 0 |
| Desktop | `python -m omicsclaw.launch desktop` | **未核实**。本机无 `fastapi` 也无 `uvicorn`，`GET /health` 跑不了。**已核实的是另一半**：命令在 0.3 秒内以退出码 2 停下，stderr 是 `omicsclaw: the desktop surface needs uvicorn and fastapi (pip install -e '.[desktop]')`，没有 traceback。**下一个人要验的**：`pip install -e '.[desktop]'` 之后 `oc desktop --workspace <dir>`，然后 `curl -s 127.0.0.1:8765/health`，断言返回的 JSON 含 `status/version/launch_id`，并断言带 `OMICSCLAW_REMOTE_AUTH_TOKEN` 起动时无 `Authorization` 头的 `POST /chat/stream` 返回 401 |

§8-4 写的是 `oc channel --list`，**这与 §5.2 冲突**：`--` 左边的东西一律交给
`resolve_app_config`，而 `--list` 不是它的 flag，所以 `oc channel --list` 得到
的是一条拒绝（退出码 2，附 channel 的 usage）。实现按 §5.2 办，冒烟用
`oc channel -- --list`。**唯一的例外是 `--help` / `-h`**：见 §A.4-4。

### A.4 规格书被实现推翻或需要增补的地方

1. **§1.1 的入口清点漏了一个，而且是第六个。** 表里列了五种进法。实测还有
   `python -m omicsclaw`——`omicsclaw/__main__.py` 已经存在（7 行），落点是同一个
   已死的 `omicsclaw.surfaces.cli.launcher:main`，实跑
   `ModuleNotFoundError: No module named 'omicsclaw.skill'`。
   ~~**本任务没有动它**~~ —— **这段自述已过期**（评估，2026-09-20）：交付之后
   协调者把 `omicsclaw/__main__.py` 重指向了 `omicsclaw.launch:main`，配套测试
   `test_python_dash_m_omicsclaw_reaches_this_shell`（真子进程跑
   `python -m omicsclaw channel -- --list`）已在树上。§8-7 的「全repo再无第四个
   进程入口」因此已经成立，`MODULE_GUARDS` 有两个键——`launch/__main__.py` 与
   `__main__.py`——两者落在同一个 `main()` 上，都不是第二个解析点。
   §1.1 的表也已补上第六行。
   > 顺带：§1.4-3 记过「约束清单上最贵的那一条，正好是没核实过的那一条」。
   > 这条是它的对偶：**清点表上漏掉的那一条，正好是没人敲过的那一条。**
2. **§5.4「`config.py` 不再 import `sys` / `os`」只对了一半。** `sys` 去掉了；
   `os` **去不掉**，因为 `_as_paths()` 用 `os.pathsep` 切分路径列表
   （`config.py:493`），那是一个平台相关常量而不是环境读取。这不影响判据——
   §8-1 的三个针是 `sys.argv` / `os.environ` / `os.getenv`，`os.pathsep` 不在
   其中，拍平后的规则照样成立。`config.py` 的模块 docstring 已写明 `os` 为什么
   还在。
3. **§5.1 与 §5.4 对 `os.environ` 的说法互相矛盾。** §5.1 说 `__init__.py` 是
   「全层唯一出现 `sys.argv` / `os.environ` 的文件」，§5.4 的探针却说
   「`os.environ` 一次都不许出现」。后者不可实现：默认值总得在某处解析。
   实现取 §5.1：`os.environ` 与 `sys.argv` 各在 `launch/__init__.py` 出现两次
   （一次解释、一次取用），由 `test_the_shell_reads_each_global_exactly_once`
   钉死，其余三个文件一次都不许出现，由
   `test_only_the_shell_itself_names_the_two_globals` 钉死。
4. **`--help` 需要一条 §5.2 没写的规则。** 严格按 §5.2，`oc cli --help` 里的
   `--help` 在 `--` 左边，会被 `resolve_app_config` 当未知 flag 拒绝——**用户
   得到的是一条 usage error 而不是 usage**。实现加了一条一行的规则：
   **命令名定下来之后，`--help` 只可能在问一件事，所以它从左半边被搬到右半边**
   （`_grammar.split_command_line`）。选它而不是在外壳里另开一条 help 分支，是
   因为后者会造出一个面内解析器永远到不了的分支，而两个答案就是这样漂开的。
   由 `test_a_help_flag_on_the_deployment_side_is_hoisted` 与
   `test_help_needs_no_terminator` 钉住。
5. **§6 对 `omicsclaw-chat` / `oc-chat` 自相矛盾**：第二条说「从 4 行收敛到
   2 行」，第三条说「在迁移完成时删除」。按实测取前者——**§1.1 给 `oc-chat` 的
   「⚠️ 能 import」这个判断太宽**：`omicsclaw.surfaces.cli` 确实 import 得动，
   但 `main()` 一调就 `ModuleNotFoundError: No module named 'omicsclaw.control'`。
   **import 得动不等于跑得动**，所以它和另外三个一样，没有什么好的东西会被删
   坏。理由与 §7 完全同构。
6. **§5.4 说那两个参数会「升级为生产路径上的正常调用」，这条实现之后才发现有
   代价**：`resolve_app_config()` 的零参调用出现在四个 docstring 例子里
   （`entry/__init__.py`、`entry/channel/__init__.py`、`entry/session.py`、
   `memory/__init__.py`），去掉默认值之后它们全部变成会抛 `TypeError` 的示例。
   四处都改成了 `resolve_app_config(argv, env)`。**`docs/FRAMEWORK-REBUILD.md`
   :815 还有一处同样过期的例子，本任务按指示没有动它**（收尾动作排在评估之后）。
7. **§5.1 说 `_surfaces.py` 只放「三个面的启动函数」，但没给三个面自己的 flag
   解析器留位置。** 实现把它们放进了 `_surfaces.py`，于是「`--` 右边交给那个面
   自己的解析器」在字面上不再成立——解析器住在外壳里，不住在面里。这是**有意的
   取舍**：把 `ReplOptions` 放回 `entry/cli/` 需要改 `entry/cli/__init__.py` 的
   公开面，而那是规格书没有要求的越界。代价记在这里：`_surfaces.py` 719 行，是
   这一层最厚的文件，而「薄外壳」这个说法主要靠另外三个文件（103 + 151 + 19）
   撑着。
8. **§9-1（包名）**：按 `launch/` 落地，没有改。**§9-2** 已作废。**§9-3（CI 与
   文档的确定性执行通路）与 §9-4（面内命令没有层）本任务没有处置**——前者需要
   owner 在库 API 与面内命令之间选一个，后者要先决定三个面的命令注册表怎么合并。
   本任务只把 §9-3 的债面扩大了一点点：`oc run <skill>` 现在真的不存在了，
   `README.md` 与 `CLAUDE.md` 的整张 CLI Reference 由此全部失效。

### A.5 §8-3：`_main.py` 的 35 个子命令，逐条建议

口径：`grep -n "add_parser(" omicsclaw/surfaces/cli/_main.py` 恰好 35 行
（`auth` 那一行在 `for _op in ("login","logout","status")` 循环里，展开是三个
子命令，按规格书口径仍记一行）。**下面是建议，不是裁定。**

| # | 子命令 | 建议 | 理由 |
|---|---|---|---|
| 1 | `version` | 面内命令 | Channel 的 `/version` 已经有了；CLI 加一个同名的即可 |
| 2 | `list` | 面内命令 | 三个面都已有 `/skills` |
| 3 | `env` | 面内命令 | 与 `/doctor` 是同一件事的两半，建议并进 `/doctor` |
| 4 | `upload` | 不回来 | 它建的是旧的 spatial session 概念，新框架里没有对应物 |
| 5 | `onboard` | 配置 | 向导写的是 `.env` 与 `.mcp.json`；一个只写配置文件的向导不该是入口 |
| 6 | `interactive`（别名 `chat`） | 不回来 | **`oc cli` 就是它**。保留等于第二个名字 |
| 7 | `tui` | 不回来（本形态） | TUI 尚未移植（0031 债 3）。它将来回来的形态是 `oc cli` 的一个部署 flag，不是第四个命令 |
| 8 | `mcp` | 配置 | `.mcp.json` 已经是这条路 |
| 9 | `mcp list` | 面内命令 | CLI 的 `/mcp` 已经报告在线 manager |
| 10 | `mcp add` | 配置 | 同 8 |
| 11 | `mcp remove` | 配置 | 同 8 |
| 12 | `mcp config` | 面内命令 | 「配置文件在哪」属于 `/mcp` 的输出 |
| 13 | `auth` | 配置 | OAuth 凭据是部署配置；`provider_from_env` 是 0031 Q8 的声明例外 |
| 14 | `auth login/logout/status` | 配置 | 同 13。`status` 可并进 `/doctor` |
| 15 | `memory-server` | 不回来 | 旧图记忆的 REST 服务；新的 `omicsclaw/memory/`（0033）是库，不是服务 |
| 16 | `desktop-server` | **已是 `oc desktop`** | 唯一一个直接变成新顶层命令的 |
| 17 | `doctor` | 面内命令 | CLI 的 `/doctor` 已有 |
| 18 | `control` | 不回来 | 第②族（Run 治理）尚未重建 |
| 19 | `control transcript-migrate` | 不回来 | 一次性离线迁移，属运维脚本而非产品入口 |
| 20 | `knowledge` | 不回来（待第③族） | 知识库随旧架构删除 |
| 21 | `knowledge build` | 不回来（待第③族） | 同 20 |
| 22 | `knowledge search` | 面内命令（待第③族） | 检索是会话里该做的事 |
| 23 | `knowledge stats` | 面内命令（待第③族） | 同 22 |
| 24 | `knowledge list` | 面内命令（待第③族） | 同 22 |
| 25 | `replot` | 面内命令 | agent 在会话里调技能；`/run` 已有 |
| 26 | `optimize` | 不回来 | 旧的 LLM 元 agent，已随旧架构删除 |
| 27 | `project` | 面内命令 | CLI 的 `/sessions` `/new` `/current` 是同一族 |
| 28 | `project list` | 面内命令 | 同 27 |
| 29 | `project current` | 面内命令 | 同 27（`/current` 已有） |
| 30 | `project new` | 面内命令 | 同 27（`/new` 已有） |
| 31 | `project use` | 面内命令 | 同 27 |
| 32 | `project clear` | 面内命令 | 同 27（`/clear` 已有，语义需区分） |
| 33 | `project reindex` | 不回来 | 索引重建是维护动作，不是入口 |
| 34 | `replay` | **库 API** | 这就是 §9-3 那条债：CI 要的是确定性执行通路，不是命令行 |
| 35 | `run` | **库 API + 面内命令** | owner 已裁定顶层不保留。CI 走库（§9-3 倾向 (a)），用户点名走 `/run` |

汇总：面内命令 16、配置 6、不回来 10、已变成顶层命令 1、库 API 2。
~~**其中 13 条（20–24、18–19、26、33、15、4）今天连实现都不在了**~~

> **这一句有三处错，35 行主体本身经逐行核对是对的**（评估，2026-09-20）：
> 表与 `grep -n "add_parser(" omicsclaw/surfaces/cli/_main.py` 同名同序，
> 汇总 16+6+10+1+2 = 35 也对。错的只有这一句：
> 1. **算术**：20–24 是 5 条、18–19 是 2 条，加 26、33、15、4 共 **11** 条，
>    不是 13。
> 2. **`omicsclaw/knowledge/` 仍在，且 `import omicsclaw.knowledge` 今天跑得
>    通**——20–24 这 5 条是「搬家」不是「重建」，理由栏的「知识库随旧架构删除」
>    不成立。
> 3. **`omicsclaw/autoagent/` 目录也仍在**，只是 import 不动
>    （`ModuleNotFoundError: omicsclaw.skill`）。26（`optimize`）的理由该写成
>    「依赖已删的 `omicsclaw.skill`，import 不动」，不是「已随旧架构删除」。
>
> 4. **「实现都不在了」这个口径本身不准。** 逐个 `ls` 之后：`omicsclaw/control/`
>    确实已删（18–19 成立）；`omicsclaw/knowledge/`、`omicsclaw/autoagent/`、
>    `omicsclaw/surfaces/`、`omicsclaw/runtime/` **都还在树上**，而 33
>    （`project reindex`）、15（`memory-server`）、4（`upload`）的实现都住在
>    `surfaces/cli/_main.py` 里——那个文件今天 import 不动，但它在。
>    准确的写法是「**import 不动**」，不是「不在了」，而这两件事的区别正是
>    §7 那条教训（「`oc list` 不是将要停，是已经停了」）的反面：**一个还在树上
>    但跑不动的实现，和一个被删掉的实现，在「要不要重建」这个问题上答案不同。**
>    今天确定要重建的只有 **2 条**（18–19）。

### A.6 对既有文件的改动，逐条

| 文件 | 改了什么 | 规格书依据 |
|---|---|---|
| `omicsclaw/entry/cli/__main__.py` | **删除** | §6「`python -m omicsclaw.entry.cli` 不保留兼容别名」、§5.1「三个面回到纯库」 |
| `omicsclaw/entry/cli/__init__.py` | 包 docstring 的三行用法示例改成 `oc cli …`，并写明本包不再是进程、不留别名 | §6。示例里的命令已经不存在 |
| `omicsclaw/entry/config.py` | `resolve_app_config(argv, env, **overrides)` 去掉两个默认值；`import sys` 删除（`import os` 保留，见 §A.4-2）；模块 docstring、`_ARGV_TERMINATOR` docstring、函数 docstring 改写 | §5.4、§8-1。散文一并改是因为拍平后的规则是原文扫描，**而且那些断言本来就已经错了** |
| `omicsclaw/entry/__init__.py` | docstring 例子 `resolve_app_config()` → `resolve_app_config(argv, env)` | §5.4 的直接后果：零参调用现在抛 `TypeError` |
| `omicsclaw/entry/channel/__init__.py` | 同上 | 同上 |
| `omicsclaw/entry/session.py` | 同上 | 同上 |
| `omicsclaw/memory/__init__.py` | 同上 | 同上。~~**这是本任务唯一一处 `omicsclaw/entry/` 之外的生产改动**~~ —— 同一张表下面还列了 `omicsclaw.py` 与 `pyproject.toml` 两行，所以「唯一一处」在写下的时候就和它自己的表矛盾；评估之后又多了 `omicsclaw/__main__.py`（§A.4-1）。准确的说法是「唯一一处 `entry/` 与 `launch/` 之外的 **Python 生产模块** 改动」，而它是一行 docstring |
| `omicsclaw.py` | `from omicsclaw.surfaces.cli._main import main` → `from omicsclaw.launch import main`，改 `raise SystemExit(main())`；docstring 删掉两个已失效的消费者并注明核实日期 | §6 第一条，与 §1.4-1 的「顺带一笔」 |
| `pyproject.toml` | `[project.scripts]` 4 行 → 2 行，`omicsclaw` / `oc` → `omicsclaw.launch:main`；`omicsclaw-chat` / `oc-chat` 删除 | §6 第二、三条（见 §A.4-5 对第三条的处置理由） |
| `tests/entry/test_config.py` | `_COMMAND_LINE_ENTRY_POINTS` → `_EXEMPT = ()`；`test_no_other_entry_module_reads_the_environment` 改名并拍平；新增 `test_the_exemption_list_is_empty` 与 `test_the_deployment_reader_takes_both_sources_as_arguments` | §5.4、§8-1。「豁免名单为空」得自己有一条测试，否则没人断言它 |
| `tests/entry/test_desktop_wire_contract.py` | `test_the_launch_id_comes_from_the_one_environment_reader` 改名为 `…_one_deployment_reader`，两处 `resolve_app_config([])` 改为显式传 env，`monkeypatch` 去掉 | §5.4 的直接后果。改完反而更强：不再依赖跑测试的机器导出了什么 |
| `tests/entry/test_assembly.py` | 一句 docstring 里的 `test_cli_main.py` 改成 `tests/launch/test_cli_command.py` | 搬家后的交叉引用 |
| `tests/entry/test_cli_main.py` | **删除**，17 项全部搬走，见 §A.7 | §6 ＋ 第 6 步「责任搬家时测试要跟着搬」 |

### A.7 `test_cli_main.py` 的 17 项，逐条对账

| 原测试 | 去处 | 形态 |
|---|---|---|
| `test_the_command_answers_one_line_from_a_pipe` | `tests/launch/test_cli_command.py` | 命令改成 `python -m omicsclaw.launch cli` |
| `test_the_whole_prompt_file_is_one_exchange` | 同上 | `main(["cli", …, "--", "--prompt-file", …], {})` |
| `test_the_shim_backend_is_no_wider_than_the_provider_protocol` | 同上 | 原样 |
| `test_an_empty_prompt_file_is_refused_rather_than_sent` | 同上 | `CliOptions` → `ReplOptions` |
| `test_the_command_line_is_cut_at_the_terminator` | `tests/launch/test_grammar.py` | `split_argv` → `split_command_line` |
| `test_a_command_line_with_no_terminator_is_all_deployment` | 同上 | 同上 |
| `test_a_surface_flag_before_the_terminator_is_refused` | `tests/launch/test_cli_command.py` | 原样 |
| `test_an_unknown_surface_flag_is_refused_too` | 同上 | 原样 |
| `test_each_surface_flag_lands_where_it_says` ×4 | 同上 | 四个参数一个不少 |
| `test_a_surface_flag_without_its_value_is_refused` | 同上 | 原样 |
| `test_help_prints_the_usage_and_starts_nothing` | 同上 | 断言 `usage: oc cli`；`"is a deployment"` 收紧成 `"is a deployment flag"` |
| `test_the_process_entry_point_reads_argv_and_nothing_else` ＋ `SURFACE_FLAGS` / `_flags_this_file_acts_on` | `tests/launch/test_launch_is_above_entry.py` | **拆成四条，且更强**：`test_only_the_shell_itself_names_the_two_globals`（覆盖全包，不只一个文件）、`test_the_shell_reads_each_global_exactly_once`（`sys.argv` 与 `os.environ` 各两次）、`test_the_shell_hands_both_globals_down_explicitly`（名了还要用）、`test_the_flags_the_shell_acts_on_are_exactly_these`。**最主要的强化是 `test_the_shell_names_no_deployment_flag`：禁止集不再手抄，而是从 `config.py` 的 `_BY_FLAG` 派生**——明天给 `AppConfig` 加一个 flag，不需要有人记得来改这里。配套的 `test_the_surface_flags_and_the_deployment_flags_do_not_overlap` 保证这条规则不是因为两个集合天生不相交才通过的 |
| `test_importing_the_surface_costs_no_optional_dependency` | `tests/entry/test_cli_optional_dependencies.py` | **留在 `tests/entry/`**：它测的是 `omicsclaw/entry/cli/` 这个**库**的性质，不是命令的。`tests/launch/` 另有一条覆盖整个外壳（8 个可选依赖）的同形探针 |
| `test_a_pipe_is_read_as_a_stream_and_not_through_a_terminal_library` | 同上 | 同上 |
| `test_the_surface_still_works_with_neither_optional_package_installed` | 同上 | 同上 |

### A.8 变异清单

跑法一律带 `-rfE --continue-on-collection-errors`——破坏 import 的变异在
collection 阶段失败，`pytest -rf` 不列它，会被误报成存活。每条变异后都
`md5sum` 对回原文件，8 个文件全部逐字节相同。

| # | 变异 | 被杀的测试 |
|---|---|---|
| 1 | `entry/session.py` 模块作用域 `import omicsclaw.launch` | **collection error**（循环 import）——只有带 `--continue-on-collection-errors` 才看得见 |
| 1b | 同上，但放进函数体（不产生 import 期循环） | `test_no_entry_module_imports_the_shell` |
| 2 | `launch/_surfaces.py` `import omicsclaw.surfaces` | `test_the_shell_names_no_replaced_package`、`test_driving_the_shell_loads_nothing_it_replaced` |
| 3 | `_surfaces.py` 改读 `os.environ` 而不是入参 `env` | `test_only_the_shell_itself_names_the_two_globals` |
| 4 | `ReplOptions.parse` 增加一个 `--model` 分支 | `test_the_shell_names_no_deployment_flag`、`test_the_flags_the_shell_acts_on_are_exactly_these` |
| 5 | `COMMANDS` 加第四个键 `"tui"` | `test_the_entry_points_are_exactly_three`、`test_every_command_names_a_subpackage_of_the_entry_layer` |
| 6 | `cli` 的 `module` 改成 `omicsclaw.surfaces.cli` | `test_every_command_names_a_subpackage_of_the_entry_layer` |
| 7 | 重新造一个 `entry/cli/__main__.py` | `test_the_process_entry_points_in_the_tree_are_the_named_ones`、`test_the_entry_layer_no_longer_ships_a_process`、`test_no_entry_module_imports_the_shell` |
| 8 | `pyproject.toml` 的 `oc` 指回旧 launcher | `test_the_console_scripts_land_on_this_shell` |
| 9 | `resolve_app_config` 把两个默认值放回去 | `test_the_deployment_reader_takes_both_sources_as_arguments` |
| 10 | `config.py` 里 `source = dict(os.environ) \| dict(env)` | `test_no_entry_module_reads_the_environment` |
| 11 | `_EXEMPT = ("config.py",)` | `test_the_exemption_list_is_empty` |
| 12 | 去掉 `split_command_line` 的 help 搬运 | `test_a_help_flag_on_the_deployment_side_is_hoisted[--help]`、`[-h]`、`test_help_needs_no_terminator` |
| 13 | Desktop 的依赖检查挪到 `open_app` 之后 | **第一次尝试时存活**，见下 |
| 14 | `main` 把拿到的 `env` 丢掉，传 `{}` | `test_the_shell_hands_both_globals_down_explicitly`、`test_the_environment_handed_to_main_reaches_the_surface[env1]`、`[env2]` |
| 15 | `omicsclaw.py` 指回 `surfaces.cli._main` | `test_the_repo_root_sentinel_still_points_at_this_shell` |
| 16 | 删掉 `--show-reasoning` 分支 | `test_each_surface_flag_lands_where_it_says[…show_reasoning…]`、`test_the_flags_the_shell_acts_on_are_exactly_these` |
| 17 | `split_command_line` 顺手吃掉一个部署 flag | `test_the_command_line_is_cut_at_the_terminator` |

**变异 13 存活过一次，值得单独记。** 原来的测试断言退出码 2、错误文本、无
traceback、耗时 < 30 秒——四条全过，而变异体确实先装配了 agent。原因是
**装配在本机只要 0.2 秒且不产生任何可观察输出**：一个松到不会 flake 的时间
上界，也就松到什么都测不出。「先于装配」是一条**顺序**断言，所以现在测的是
顺序——`test_the_desktop_command_checks_the_dependency_before_assembling` 用
替身记录 `_asgi_server_module` 与 `open_app` 的调用次序，真进程那条冒烟留在
`test_the_desktop_command_names_its_missing_dependency_and_stops`。
这是 0030/0031 那条「只断言『最终发生了』的测试，测不出『及时发生了』」的
同一个形状，换了一个面孔：**只断言『最终失败了』的测试，测不出『在正确的
时刻失败了』。**

### A.9 本任务没做的

1. ~~**`omicsclaw/__main__.py` 没动**~~ —— **已作废**：交付之后由协调者重指向
   `omicsclaw.launch:main`，见 §A.4-1。
2. **`README.md` 与 `docs/FRAMEWORK-REBUILD.md` 没动**——按 0031 §9-19/20 的
   纪律，收尾排在独立评估之后。两处都有失效内容需要收尾时处理：`README.md`
   的 Quick Start 教 `oc run <skill> --demo`，`FRAMEWORK-REBUILD.md:815`
   有一处 `resolve_app_config()` 零参示例。
3. **`CLAUDE.md` 的整张 CLI Reference 没动**——它通篇教
   `python omicsclaw.py run <skill>` 与 `omicsclaw.py list`，这些今天全部不
   存在。这是 §9-3 那条债的文档面，需要 owner 先在库 API 与面内命令之间选一个。
4. **`oc desktop` 的 `/health` 未核实**（§A.3）。
5. **§9-3 与 §9-4 未处置**（§A.4-8）。

---

## 附录 B —— 两轮独立评估的处置（2026-09-20）

两路评估互不知情，各自读了 `omicsclaw/launch/`、`tests/launch/` 与本文。
owner 在处置中途改了优先级：**CLI 面先修好**，其余两个面排在其后。下面按
「修了 / 驳回 / 记成债」三分，一条不漏。

实测数字（`-p no:cacheprovider -q -o addopts=""`）：

| | 处置前 | 处置后 |
|---|---|---|
| `tests/entry` ＋ `tests/launch` | 693 passed, 2 skipped | **808 passed, 2 skipped** |
| `tests/{schema,provider,engine,tools,context,skills}` | 2,090 passed | **2,093 passed** |

两组数里都掺了另一个并发会话（`omicsclaw/planning/`，05:51–06:02 出现在树上）
的贡献；本处置自己的净增量是 `tests/launch/` 的 +109 与 `tests/entry/` 的 +4。

### B.1 修了

| # | 发现 | 处置 | 变异 → 被杀的测试 |
|---|---|---|---|
| B1 | `SIGTERM` 无人接管，进程被就地杀掉，`stop_all` / `runtime.close` / `AgentApp.aclose` 全不跑 | `_surfaces._stop_signals`：在**建第一个适配器之前**就装上 `SIGTERM`＋`SIGINT` 的 loop handler，取消当前 task，让 `ChannelManager.run` 的 `finally` 走完 | 去掉 SIGTERM / 把 handler 装到 `start_all` 之后 / 删 `app.aclose()` / 删 `runtime.close()` → `test_a_signal_drains_the_channels_and_is_reported_as_128_plus_it[sigterm|sigint]` |
| B2 | Ctrl-C 清理跑了但退出码 0 | 退出码由外壳给：`128 + signum`（130 / 143），`EXIT_TERMINATED` 新增进契约 | `exit_code` 恒返回 0 → 上面三条＋`test_a_signal_guard_reports_128_plus_the_first_signal` |
| B3 | `main()` 只 catch 三类异常，「raises nothing」是假的 | 补 `SystemExit`（保留它自己选的码）与 `BaseException`（rc 1，一行 `类型: 消息`，无 traceback）两条兜底；`_build_telegram` 增加与 Feishu 对称的 allowlist 预检（rc 2） | 删兜底 / 兜底吞掉原因 → `test_an_unanticipated_failure_is_an_exit_code_and_not_a_traceback[×4]`、`test_the_backstop_names_the_failure_it_caught` |
| R1 | `--list` / `--help` 在 `resolve_app_config` 之前 return，未知部署 flag 被静默丢弃（§5.2 被违反） | 三个面一律「先解析面内 flag，再解析部署半边，最后才答 `--help` / `--list`」 | 把 `resolve_app_config` 移回早退之后 → `test_an_unknown_deployment_flag_is_never_discarded_by_a_surface[channel --bogus -- --list|--help]` |
| R1b | §8-4 的 Channel 冒烟是假烟（在装配之前返回） | 换成真进程：`tests/launch/test_channel_command.py` 起一个真 `oc channel`，真 `open_app`、真 `compose_channel_runtime`、真 `ChannelManager`，只有**适配器**是 `Channel` 的真子类替身（本机无 SDK 无网络），断言三层各自的启动日志 | 见 B1 那一行——同一批测试 |
| R2 | 非回环 bind ＋ 空 token 不被拒绝，下游 `server.py:303` 是 `if not bearer_token: return True` | `_refuse_an_open_unauthenticated_bind`，允许表而非拒绝表（`CLAUDE.md` 安全规则 1：问题是「是否已知为私网」而不是「是否已知为公网」），错误消息点名 `OMICSCLAW_REMOTE_AUTH_TOKEN`，且排在 uvicorn 依赖检查**之前** | 删调用 / 把 `0.0.0.0` 加进回环表 → `test_the_desktop_command_refuses_an_open_bind_before_it_needs_uvicorn`、`test_an_off_machine_bind_without_a_token_is_refused[0.0.0.0]` |
| R3 | `.env` 的责任在搬家途中掉了（承诺在三处，实现在零处） | **实现**（owner 裁定，且被提为 CLI 面第一优先）：`launch._adopt_dotenv` 读 repo 根与 `cwd` 的 `.env`，`override=False`，**只在 `env is None` 时执行**——`main(argv, env)` 显式传入的映射仍是那次部署的唯一真相，测试因此保持隔离 | `_adopt_dotenv` 变空 / `main` 不再调它 → `test_a_dotenv_file_reaches_the_surface`、`test_an_exported_variable_beats_the_file` |
| R4 | 探针口径三个洞＋行为探针只 import 四个目标 | `_imported_modules` 补 `ImportFrom.names`（`from omicsclaw import launch`）与 `importlib.import_module("…")` 字符串实参；needle 表补 `from os import` / `from sys import` / `environb`，并搬进 `tests/_env_probe.py` 供两处共用（家族性弱点的结构性修法）；新增一条子进程探针 import `entry/` 下**每一个**模块 | 四条变异全杀：`from omicsclaw import launch`、`importlib.import_module('omicsclaw.launch')`、`from os import environ`、模块作用域 `import omicsclaw.launch`（后者是 collection error，只有带 `--continue-on-collection-errors` 才看得见） |
| R5 | 判据 1 在实质上是假的 | **取「把断言改准确并让它可执行」这一支**（见 B.3 对另一支的说明）：新增 `tests/launch/test_the_environment_is_read_in_known_places.py`，把重建栈 12 个包里 **8 个** 读进程全局的文件逐条列出并写明理由，其中 4 条标为 UNDECLARED；另加一条「只有外壳能写环境」的断言。`launch/__init__.py`、`entry/config.py`、`entry/ingress.py` 里三处「恰好一个例外」的散文一并改准 | 给 `mcp/manager.py` 加一处 `os.environ` → `test_the_environment_is_read_only_in_the_places_named_here` |
| R6 | `_replay` 在非中断失败时整包丢日志；`_LOG_TAIL_CHARS` 教的「先装文件 handler」办法不成立 | `_replay` 移进 `finally`（且在 `with` 之外，日志接管已还原）；docstring 改成说明 `terminal_owned_logging` 做的是 `root.handlers = [handler]`，预装 handler 整段会话收不到东西，真正的修法是一个 `--log-file` 部署 flag（记成债） | 还原成「`_replay` 在 `with` 之后」 → `test_the_held_log_is_printed_even_when_the_run_fails` |
| R7 | `tests/test_oc_entry_point.py` 反向断言旧契约 | 更新到 `omicsclaw.launch:main` 两行，并新增「`oc-chat` / `omicsclaw-chat` 必须**不**注册」；未 pip install 的 checkout 里跳过而不是红（那里「没有 metadata」不等于「entry point 错了」，manifest 那半由 `test_grammar.py` 看着） | 指回 `surfaces.cli.launcher` → `test_console_script_target_imports[omicsclaw.surfaces.cli.launcher:main]` |
| R8 | `_surfaces.py` 297 条语句 83 条零执行 | 新增 `tests/launch/test_surfaces.py`（92 项）覆盖 `DesktopOptions` / `ChannelOptions` / `_as_port` / `_as_channel_names` / `_build_telegram` / `_interrupts` / `_replay` / `_stop_signals` / 三处中断退出码 | 逐条见本表其余行 |
| G4 | 第二次 Ctrl-C 把 `app.aclose()` 腰斩而退出码仍报 130 | `_release`：`asyncio.shield` 让取消落在调用方的 `await` 上而不是落进 `aclose` 里，**恰好吸收一次**额外中断；仍未完成则返回 `False`，`_run_cli` 据此报 1 而不是 130 | 去掉 `shield` → `test_a_second_interrupt_does_not_cut_the_release_in_half`、`test_a_release_that_cannot_finish_is_reported_rather_than_claimed` |
| G5 | 取消路径跳过 `source.close()` | 放进 `finally` | 还原成「`repl.run()` 之后一句」 → `test_the_prompt_source_is_closed_when_the_repl_is_interrupted` |
| G6 | `--session` 与 `--prompt` 同给时前者被静默忽略 | 拒绝（`run_once` 本来就没有会话可续），`CLI_USAGE` 写明 `--session` 仅 REPL | 删拒绝 → `test_a_session_to_continue_and_a_single_exchange_are_refused_together[--prompt|--prompt-file]` |
| — | `--help` 提升会吃掉部署 flag 的值（`oc cli --workspace --help /data` 变成一个**另一个合法的**部署加一屏 help） | `_help_in_flag_position` 按 `_from_argv` 的步长走，只提升处在 flag 位置的 help | 还原成旧的列表推导 → `test_a_help_flag_that_is_a_value_is_not_hoisted[--help|-h]` |
| — | CLI 的真进程验收只有「有替身的完整一次交换」那一条 | 补另一条：无 key 无网络时 REPL 止于 `ProviderError`、退出码 0、无 traceback；`--prompt` 同样情形退出码 1 | —（这两条是验收，不是防回归；它们各自的行为由上面的修复保证） |
| — | 38 条斜杠命令只实现 9 条，拒绝路径无专门测试 | 拒绝路径**本来就有**一条站岗（`test_help_lists_what_this_build_runs_and_a_blocked_command_says_so`，用 `/research`）；补一条点名 `/run` `/doctor` `/context` `/memory` 的，因为它们正是 §5.3 用来支撑「已修好一半」的名字 | 把不实现的命令转发给模型 → 上述两条共 5 个用例 |

文档与引用，逐条核对后修：`_surfaces.py` 的 `CHANNEL_USAGE` 指向不存在的
`omicsclaw/entry/channel/README`（真 README 在 `surfaces/channels/README.md`）；
`_grammar.py` 引用了不存在的测试名 `test_the_shell_reads_no_deployment_flag`
（真名 `..._names_...`）；`start_cli` 对 harness9 的引用错两处（TUI 是**中间
那支** `case term.IsTerminal`，且是 **Bubble Tea**（`tui.go:17`）不是 Textual）；
`ReplOptions` 的「caller has an app to close」（它是 `start_cli` 第一条语句，
那时没有 app——真正的理由是 `argparse` 会自己决定退出码）；模块 docstring 的
「九个平台 SDK 在工厂里可见 import」（这个文件一个平台 SDK 都没有，九个适配器
是 `get_channel_class` → `importlib.import_module` 解析的）；`config.py:790`
自称 `resolve_app_config` 是 "pure" 而 `:813` 调 `Path.cwd()`；
`tests/entry/test_cli_repl.py` 与 `test_cli_render.py`（以及
`entry/cli/_input.py` 两处，评估未列）仍举 `python -m omicsclaw.entry.cli`；
`tests/launch/test_grammar.py` 两条名字承诺「prints the usage」而只断言返回值
（现已断言 stdout/stderr 的内容，删掉 print 会红）；
`_OPTIONAL_DEPENDENCIES` 的 docstring 措辞过强（blocker 挡 5 个不是 8 个，
理由已写明：`prompt_toolkit` 装着且是 CLI 的硬依赖，两个平台 SDK 在适配器方法
里才 import）。

### B.2 驳回（附证据）

1. **「`entry/` 有 5+ 处 docstring 直接点名 `omicsclaw.launch`」——计数不实。**
   `grep -rn "omicsclaw\.launch" omicsclaw/entry/` 今天只有 **2 个文件 4 处**
   （`config.py` ×3，其中 1 处是本次新增的 `.env` 说明；`entry/cli/__init__.py`
   ×1）。评估点名的 `entry/__init__.py:12`、`channel/__init__.py:16`、
   `session.py:850` 三处写的是 `resolve_app_config(argv, env)`，**一个字都没有
   提到外壳**；`ingress.py:147` 提的是 `resolve_app_config`，不是 `launch`。
2. **「散文点名外壳违反 §3-2」——不采纳，改的是散文的**断言**而不是散文。**
   §3-2 可以被执行的那一半是**依赖箭头**：`entry` 不许 `import` 外壳，由
   `test_no_entry_module_imports_the_shell` 钉住（本次还加强了它，见 R4）。
   「入口层不知道外壳存在」那句一行小结过强：一个拒绝说出自己唯一调用者是谁
   的模块，文档更差而架构一点没变好。这条与
   `test_no_entry_module_reads_the_environment` 连散文一起扫的做法**不矛盾**：
   那里的散文是**假的**（这个包确实已经不读那两个全局了），这里的散文是真的。
   两条测试的 docstring 都写明了这个区别，免得下一个人「顺手统一」。
   `ingress.py:147` 那句「exactly one function allowed to read the environment」
   **是**假的，已按 R5 改准。
3. **「A.5 的 35 行主体有问题」——主体没问题。** 与
   `grep -n "add_parser(" omicsclaw/surfaces/cli/_main.py` 逐行同名同序，
   汇总 16+6+10+1+2 = 35 也对。错的只有汇总后那一句的算术与三处理由栏，
   已在 §A.5 下逐条标注。

### B.3 记成债（附理由与「下一个人要验什么」）

1. **§9-3：CI 与 Makefile 今天全不成立，但不许在这里定。**
   `.github/workflows/pr-ci.yml:94` 的 `python omicsclaw.py list`（实测该行为
   `- name: Test OmicsClaw CLI` 的 `run:`）与 Makefile 里 **24 条**
   `omicsclaw.py run …`（`omicsclaw.py` 共出现 29 次）全部落在已取消的顶层入口
   上——`oc list` 与 `oc run <skill>` 今天都不是命令了。
   它们的归宿取决于 §9-3 的未决（库 API vs 面内命令），**owner 还没选**，所以
   本次一行未动。
   *下一个人要验什么*：owner 选定之后，CI 里那条「用真 shared runner 把已发布
   的 run-derived Skill 重跑两遍」必须仍然跑得动，并且不经过 agent（那正是它
   想避开的东西）。
2. **`.mcp.json` 的 `${VAR}` 仍按实时进程环境展开。**
   `entry/assembly.py` 调 `load_mcp_config(config.mcp_config_path())` 不传
   `env`，而 `load_mcp_config` **已经**有 `env=` 参数。这是 R5 那一支没选的
   修法：把 `env` 从 `open_app` 穿下去是一个 keyword 参数加一行，但
   `entry/assembly.py` 当时正被另一个会话并发改写（`omicsclaw/planning/` 在
   05:51–06:02 之间出现），在别人手底下改签名换不来这一步的价值。
   *下一个人要验什么*：写一个含 `${OC_PROBE}` 的 `.mcp.json`，用
   `main(argv, {"OC_PROBE": "x"})` 驱动，断言展开用的是传入的映射而不是进程
   环境；同时 `mcp/stdio.py:102` 的 `child_environment` 默认值要一起决定
   （子进程的环境是不是进程事实，可以两说）。
3. **适配器把缺失的平台 SDK 报成 `RuntimeError`，于是落在 rc 1 而不是 rc 2。**
   `entry/channel/telegram.py:222` 与 `feishu.py:164` 都把 `ImportError` 翻成
   带安装命令的 `RuntimeError`，消息是好的，但外壳只能按「没预料到的失败」处理
   （rc 1）。外壳这边已经有一条 `except ImportError` 把未翻译的
   （`feishu.py:223/241` 两处裸 import）变成 rc 2 的 `MissingSurfaceDependency`。
   *下一个人要验什么*：若决定统一到 rc 2，改的是那两个适配器（让它们抛
   `ImportError` 或一个共用的异常），然后
   `test_a_surface_dependency_that_is_absent_is_a_refusal_not_a_crash` 要能
   覆盖真适配器路径而不只是替身。
4. **`--log-file` 部署 flag 不存在。** `terminal_owned_logging` 做的是
   `root.handlers = [handler]`，所以「想要全部日志就先装一个文件 handler」这条
   办法不成立；今天唯一的出口是 `_LOG_TAIL_CHARS` 这 4000 字的尾巴。
   *下一个人要验什么*：加 flag 之后，REPL 会话期间预装的 file handler 必须真的
   收到记录（现在收不到），并且 `_replay` 不应把同样的内容再打一遍。
5. **`oc desktop` 的 `/health` 仍未核实**（§A.3 原样保留）。本机无 `fastapi`
   无 `uvicorn`。已核实的仍是另一半（rc 2、点名依赖、无 traceback、且现在**在**
   安全拒绝之后）。
   *下一个人要验什么*：`pip install -e '.[desktop]'` 之后
   `oc desktop --workspace <dir>`，`curl 127.0.0.1:8765/health` 断言 JSON 含
   `status/version/launch_id`；再带 `OMICSCLAW_REMOTE_AUTH_TOKEN` 起动，断言无
   `Authorization` 头的 `POST /chat/stream` 返回 401；最后断言
   `oc desktop -- --host 0.0.0.0` 在没有该变量时仍然拒绝启动。
6. **§9-4（面内命令没有层）未处置**，且 §5.3 的「已修好一半」已被证伪
   （38 条规格 / 9 条实现）。
   *下一个人要验什么*：三个面各自的注册表合并方案，以及合并后
   `REPL_SLASH_COMMAND_SPECS` 与 `CLI_SLASH_COMMAND_SPECS` 的差集是否仍然落在
   那条拒绝路径上。
