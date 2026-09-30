# 计划 0048 — surface 标志由 surface 自己认领

**状态**：**已实现**（2026-09-22）。方向由 owner 选定（三选一中的 C），
一轮独立只读审核后返工（§11），owner 批准 §10 的两项裁定后按本文实现，
交付结果与实现期发现见 §12。
验证：`tests/launch` 250 + `tests/entry` 1148 全绿；整套重建栈
**5017 passed, 12 skipped**（2026-09-22 实测）。§8 的五条手工验收逐条跑过。

> 整栈那个数字是**某一时刻的测量值**：这棵树同时有几个 session 在写，
> `AGENTS.md` 记录的 4982 是 2026-09-21 的数，本次改动只贡献其中 24 项。

**前置**：计划 0037 §5.2 交付的切分规则（`oc <surface> [部署] -- [surface]`），
以及它在 `omicsclaw/launch/_grammar.py` 与 `omicsclaw/launch/_surfaces.py`
的落地形态。

**触发**：owner 实际敲了 `oc cli --configure` 与 `oc cli --show-reasoning`，
两条都被拒绝。

---

## 1. 现象

```
$ oc cli --configure
omicsclaw: unknown option '--configure'; pass a surface's own flags after '--'

usage: oc cli [deployment flags] [-- surface flags]
...
  --configure        ask for a provider, a key, a model, an endpoint and
                     a workspace, and write them to the .env this shell
                     loads. ...
```

`--show-reasoning` 同样。**报错说"这个选项不认识"，紧接着打印的 usage 里又
逐字列着它**——这是当前形态最糟的部分：用户读到的是自相矛盾，而不是"位置写
错了"。

而且这道门槛不只绊到 owner：仓库自己的文档里**已经有一批写成了新拼法**，
今天全是坏的——`AGENTS.md:89` 的 `oc cli --prompt-file <f>`、`AGENTS.md:460`
与 `:464`、`.env.example:248` 的 `oc desktop --host 0.0.0.0`、`README.md:45`
的 `oc cli --prompt … > answer.txt`。写文档的人（包括写下这条规则的人）在不
照抄的时候，自然写出来的就是不带 `--` 的那种。

## 2. 根因（精确到行）

1. `omicsclaw/launch/__init__.py:143` 取出命令名后调用
   `_grammar.split_command_line(rest)`，在**第一个 `--`** 处把命令行切成
   两半：左半边给 `resolve_app_config`，右半边给该 surface 自己的解析器。
2. `_grammar.py:131-138` 只把 **`--help` / `-h`** 从左半边上提到右半边
   （`_help_in_flag_position`）。其余任何 surface 标志写在 `--` 左边，都会
   原样进入左半边。
3. `--configure` / `--show-reasoning` 是 CLI surface 自己的标志，由
   `_surfaces.py:250 ReplOptions.parse` 解析（usage 里分别是 `:133` 与 `:132`）。
4. 于是它们被送进 `omicsclaw/entry/config.py:_from_argv`，那里只认
   `_OPTIONS` 里的三十余个部署标志，未命中即在 `config.py:872-875` 抛
   `AppConfigError("unknown option …")`。
5. `launch/__init__.py:146-148` 捕获后打印 `command.usage`，也就是
   `CLI_USAGE`——那份 usage 正是列出 `--configure` 的地方。矛盾感由此而来。

**还有三个参与者，审核时才浮出来，写在这里免得实现时再发现一次：**

- `_surfaces.py:102` 的 `_HELP_FLAGS` 是 help 标志集的**第二份拷贝**
  （`_grammar.py:49` 的 `HELP_FLAGS` 是第一份）。
- `config.py:_ARGV_TERMINATOR` 让 `_from_argv` 自己也会在 `--` 处 `break`；
  生产路径上左半边不可能含 `--`，所以那是一段死代码，但直接单测 `_from_argv`
  时它是活的。
- **`_help_in_flag_position` 其实并没有 mirror `_from_argv`**，尽管它的
  docstring 逐字这么写。见 §4.1 的裁定 B——这是本计划最容易翻车的一处。

当前唯一可用的拼法是 `oc cli -- --configure`。

## 3. 既有设计的论证，以及为什么仍要改

`_surfaces.py:start_cli` 的 docstring 写明：

> `--configure` 是 surface 标志，和其它 surface 标志一样写在 `--` 之后——
> `split_command_line` 里的上提只给 `--help`，**每开一个例外都在削弱这条
> 规则**。

`tests/launch/test_configure_command.py:286` 与
`tests/launch/test_cli_command.py:298` 两条测试把它钉死。

这条论证在"例外"的框架下是对的。本计划换一个框架：**不是给切分规则开例外，
而是明确每个标志的归属**。

- 切分规则真正保护的是*没有第二个读者去抢解释部署标志*（计划 0031 Q8）。
- surface 标志集与部署标志集**互不相交**，而且这件事**已经被测试钉住**：
  `tests/launch/test_launch_is_above_entry.py`
  `test_the_surface_flags_and_the_deployment_flags_do_not_overlap` 断言
  `not SHELL_FLAGS & DEPLOYMENT_FLAGS`。
- 既然不相交，"`--configure` 属于谁"就与它写在 `--` 的哪一侧无关，是一个
  **无歧义**的事实。让 surface 把属于自己的标志认领走，不产生第二个部署标志
  读者，Q8 的性质原样保持。

`--` 因此从"必须敲的分隔符"降级为"消歧用的显式写法"。它仍然是唯一能表达
下面两件事的写法，且旧拼法逐字兼容：

- **值恰好长得像标志**：`oc cli -- --prompt --model`。
- **值恰好是一个部署标志**：`oc cli --prompt --workspace /data` 改后会把
  `--workspace` 当成提示词正文，左半边只剩 `/data`，报错从今天清楚的
  `unknown option '--prompt'` 变成 `unknown option '/data'`。**这个坑修不掉**
  ——要判断"值位上的 token 是不是部署标志"，`_surfaces` 就得知道部署标志集，
  而 `test_the_shell_names_no_deployment_flag` 禁止它出现部署标志字面量、
  `test_the_shell_imports_only_public_names_of_the_entry_layer` 禁止它 import
  `config._BY_FLAG`。所以只能文档化：这正是 `--` 还存在的理由。
- 同源的次要后果：`oc cli --session --bogus` 改后会起一个 session id 叫
  `--bogus` 的 REPL（今天被拒）。值位不做检查是上面那条的必然结果。

## 4. 方案

### 4.1 认领算法（逐 token 写死，不外包给"同一步长"四个字）

在 `_surfaces.py` 新增共享函数，三个 surface 各调一次：

```python
def _claim_surface_flags(
    deployment: Sequence[str], owned: Mapping[str, int]
) -> tuple[list[str], list[str]]:
    """把左半边里属于本 surface 的标志（连同它的值）取出来。"""
```

返回 `(留给部署的 tokens, 认领到的 tokens)`。**算法逐 token 写死**：

```
i = 0
while i < len(tokens):
    token = tokens[i]
    if token == "--":                      # 裁定 A
        kept.extend(tokens[i:]); break
    flag, _, inline = token.partition("=")
    arity = owned.get(flag)
    if arity is None:                      # 不是本 surface 的
        kept.append(token)
        if inline:                         # 裁定 B：inline 非空才算自带值
            i += 1
        elif i + 1 < len(tokens):
            kept.append(tokens[i + 1]); i += 2
        else:
            i += 1                         # 裁定 C：缺值留给 _from_argv 去报
        continue
    if inline:                             # 本 surface 的，自带值（§4.4）
        claimed.extend([flag, inline]); i += 1
    elif arity == 1 and i + 1 < len(tokens):
        claimed.extend([flag, tokens[i + 1]]); i += 2
    else:
        claimed.append(token); i += 1      # 裁定 D：缺值留给 surface 解析器去报
```

四条裁定，逐条给理由：

**裁定 A（裸 `--`）**：停止认领，其后全部原样留给部署侧。走 `main` 时左半边
不可能含 `--`（`split_command_line` 在第一个 `--` 处切），但 §7 要对这个函数
做直接单测，行为必须有定义；且与 `_from_argv` 自己的 `break` 一致。

**裁定 B（inline 判定）——本计划最关键的一行**。真实的 `_from_argv`
（`config.py:869-881`）是 `flag, _, inline = token.partition("=")` 后
`if inline:`，即**分隔符存在且值非空**才算自带值；`--workspace=` 会去吃**下一个
token** 当值。而 `_grammar.py:158` 写的是 `index += 1 if "=" in token else 2`,
两者在 `--workspace=` 上分道扬镳：

| 命令行 | `_help_in_flag_position` 认为 | `_from_argv` 实际 |
|---|---|---|
| `--workspace= --help` | `--help` 在标志位 → 上提 | `--help` 是 `--workspace` 的值 |

认领函数**必须用 `_from_argv` 的那一种**（`if inline:`），否则
`oc cli --workspace= --configure` 里的 `--configure` 会被认领走，而部署侧认为
它是 `--workspace` 的值——两边对同一个 token 的位置判断打架。

> **实现者注意**：现有测试 `test_the_inline_spelling_advances_one_token_not_two`
> 只覆盖 `--workspace=/data`（inline 非空），**区分不出这两种实现**。照抄
> `_grammar.py:158` 那一行会得到一个错的认领器并通过全绿的测试。§7 因此要求
> 给 `test_grammar.py` 和认领单测各补一个 `--workspace=` 用例。

顺带修 `_grammar.py:143-152` 那句"Mirrors `config.py`'s `_from_argv` stride"的
docstring——它今天是不准确的——并让 `_help_in_flag_position` 复用同一个共享体，
偏离一并消除。（import 方向：`_grammar.py:29` 已 `from ._surfaces import …`，
反向会成环，所以共享体放 `_surfaces`，`_grammar` 取用。）

**裁定 C / D（缺值一律不在认领函数里报）**：`_claim_surface_flags`
**不抛任何异常**。缺值的部署标志原样留下，由 `_from_argv` 报它自己的
`"{flag} needs a value"`；缺值的 surface 标志原样认领，由该 surface 的解析器
报**同一句话**（`_surfaces.py:273-274` 等）。好处是错误只有两个来源，不新增
第三个，消息文案也不必复制一份。

**未命中的 token 用"跳 2"而不是 `_from_argv` 的"直接 raise"**，这是认领函数
唯一一处刻意的近似（它不知道部署标志集，也不许知道，见 §3）。这个近似恰好
保住了 §8 验收第 4 条：`oc cli --bogus --configure` 里 `--configure` 落在
`--bogus` 的值位、不被认领，左半边仍因 `--bogus` 被拒。

**其余边界的既定行为**（写进单测，不改实现）：

| 情形 | 行为 |
|---|---|
| `oc cli --workspace --configure /data` | `--configure` 在值位，不认领（与 `test_a_help_flag_that_is_a_value_is_not_hoisted` 的裁定一致） |
| `--session a --session b` | 两个都认领，解析器后者胜——与 §4.3 的跨侧优先级同一条规则 |
| `--channels a --channels b` | 同上，静默覆盖。`_as_channel_names`（`_surfaces.py:768-770`）只拒**一次调用内**的重复，这是今天右半边就有的行为，不是本计划引入的 |
| 空 token `""` | `owned.get("")` 未命中 → 按未命中走；最终由 `_from_argv` 报 `unknown option ''` |

### 4.2 每个 surface 的标志表

紧挨各自的 options 类声明一张 `Mapping[str, int]`（flag → arity）：

```python
CLI_FLAGS = MappingProxyType({
    "--help": 0, "-h": 0, "--configure": 0, "--show-reasoning": 0,
    "--session": 1, "--prompt": 1, "--prompt-file": 1,
})
```

desktop 为 `{--help, -h: 0, --host, --port: 1}`，channel 为
`{--help, -h, --list, --verbose: 0, --channels, --health-port: 1}`。
三张表的内容已逐项核对与解析器一致（17 个 flag × 3 个解析器实跑，§11）。

`--help`/`-h` 登记进表的理由见 §4.5。为了不让 help 标志集出现**第三份**
拷贝（`_grammar.HELP_FLAGS`、`_surfaces._HELP_FLAGS` 已是两份），三张表里的
这一对从 `_HELP_FLAGS` 派生而不是重打一遍；`HELP_FLAGS` 这个名字必须继续留在
`_grammar`（`tests/launch/test_grammar.py:26` 直接 import 它）。

**不改写三个手写解析器**（它们手写有理由，见 `ReplOptions` docstring：argparse
会自己 `sys.exit`，两种拒绝就会有两种退出码）。表与解析器的漂移由一条**交叉
探针测试**守住：

> 对 `SHELL_FLAGS - {"--"}` 里的**每一个**标志，向三个解析器各探一次
> `parse([flag])`：抛 `unknown surface option` ⇒ 不属于该 surface，必须不在
> 它的表里；抛 `"needs a value"` ⇒ arity 1；正常返回 ⇒ arity 0。表与探针结果
> 逐项相等。

这条链是闭合的：新加一个 surface 标志，会先让
`test_the_flags_the_shell_acts_on_are_exactly_these`（它断言包内标志字面量
与 `SHELL_FLAGS` **精确相等**）红，逼人把它加进 `SHELL_FLAGS`；再让这条交叉
探针红，逼人登记进表。

> 初稿写的是"从解析器反推标志集"，**做不到**——`parse([x])` 没法枚举无限的
> 输入空间，只能发现"表里有、解析器没有"，恰恰发现不了计划点名的那种漂移。
> 以 `SHELL_FLAGS` 为枚举源是审核给出的修正。

单标志探针对 arity 可用这点已实测：`--prompt-file` 的缺值检查在读文件**之前**
（`_surfaces.py:273-274`），探针不会碰文件系统；互斥规则只在两个标志同时给出
时才触发（`_surfaces.py:285-294`），单标志探针碰不到。

### 4.3 三个 `start_*` 的接线

三处形状完全一致，各加一行：

```python
deployment, claimed = _claim_surface_flags(deployment, CLI_FLAGS)
options = ReplOptions.parse([*claimed, *surface])
config = resolve_app_config(deployment, env)
```

- **认领到的排在前面**，`--` 之后的排在后面：同一标志两侧都写时，更显式的
  那个（`--` 之后的）后解析、生效。写进 docstring 并加测试。
- 三个 `start_*` 今天都是 **parse 先、resolve 后**（`_surfaces.py:341-342` /
  `631-632` / `794-795`），这是计划 0037 R1 的明文裁定，认领插在最前面**不改变
  这个相对顺序**。已逐个核对：`oc cli --bogus -- --nonsense` 今天与改后都先报
  `unknown surface option '--nonsense'`；`test_an_unknown_deployment_flag_is_never_discarded_by_a_surface`
  的四条 argv（`--bogus` 后无 token，认领跳到末尾不认领任何东西）保持绿。
- **一处窄但真实的变化**，不要写成"性质原样保持"：左半边现在可能产出 surface
  侧的拒绝。`oc cli --bogus x --session` 改后先报 `--session needs a value`，
  `--bogus` 不再被提及（今天报的是 `unknown option '--bogus'`）。0037 §5.2/R1
  保护的性质是"**部署侧的错字不能被早退（exit 0）吞掉**"，这些仍然是退出码 2
  的拒绝，性质成立；但措辞要精确，并加一条测试钉住"认领引发的拒绝不会让命令
  退 0"。
- 互斥规则（`--configure` 与 `--session/--prompt` 不能同时给）落在
  `ReplOptions.parse` 内，认领不改变它，`oc cli --configure -- --prompt x`
  照旧被拒。

### 4.4 inline `=` 拼法的裁定

部署标志支持 `--workspace=/data`；三个 surface 解析器**今天都不支持**
`--session=run-7`。若认领只处理裸拼法，`oc cli --session=run-7` 会落到
`resolve_app_config` 报 "unknown option"，又回到本计划要消灭的那类错报。

**裁定：三个 surface 解析器一并支持 inline 拼法**（`token.partition("=")`，
arity 0 的标志带非空值则拒绝 `"{flag} takes no value"`），认领函数同样处理
（§4.1 的 inline 分支）。理由：`--session=run-7` 在 `--` 两侧必须得到同一个
答案，否则修掉一种不一致又造出另一种。

注意它恰好踩在裁定 B 上：`--session=run-7` 是 1 个 token，而 `--session=`
（空 inline）要去吃下一个 token——同一个函数伺候两种语义，裁定 B 已经写死，
实现者不要另做判断。

这是本计划唯一一处**扩大**行为的改动，单列供 owner 否决；否决则退回"认领只
认裸拼法，inline 命中本 surface 的标志时抛一句指明正确写法的拒绝"。

### 4.5 `_grammar.py` 不改行为

`--help` 的上提保留（它与 surface 无关，三个 surface 都有），切分规则本身、
`TERMINATOR`、`split_command_line` 的签名与返回一律不动；唯一的改动是让
`_help_in_flag_position` 复用 §4.1 的共享步长（裁定 B），以及修正那句不准确
的 docstring。

`--help`/`-h` 仍登记进三张表，是为了覆盖上提够不到的情形：
`oc cli --configure --help` 里 `--help` 被上提步长当作 `--configure` 的值而
跳过（实测 `_help_in_flag_position` 返回 `None`），今天这条命令报错；改后两个
都被认领，`start_cli` 先看 `options.help` → 打印 usage 退 0。

## 5. 非目标

- 不动 `omicsclaw/entry/config.py` 的部署标志集与其拒绝消息。
- 不引入 argparse，不把手写解析器改成表驱动（§4.2）。
- 不给部署标志做反向认领（部署标志写在 `--` 右边仍应被 surface 拒绝）。
- 不修 §3 那条"值位上的部署标志被吃掉"（结构上修不了，只文档化）。
- 不碰 desktop `/chat/permission` 缺口、不碰 channel 凭据校验。

## 6. 逐文件改动清单

| 文件 | 改动 |
|---|---|
| `omicsclaw/launch/_surfaces.py` | 新增 `_claim_surface_flags` 与共享步长；三张 `*_FLAGS` 表；三个 `start_*` 各加一行接线；三个解析器加 inline 拼法（§4.4）；`start_cli` 那段"`--configure` 走 `--` 之后"的 docstring 改写为新裁定；三份 `*_USAGE` 的 "Surface flags (after --)" 改为"可写在 `--` 前后" |
| `omicsclaw/launch/_grammar.py` | `_help_in_flag_position` 改用共享步长；修正"Mirrors `_from_argv` stride"的 docstring；"One cut, two owners" 补一句 surface 认领自己的标志；**`usage()` 正文（`:176-179`）**的 "Deployment flags go before --…" 一并改——它是打印给用户看的，且没有测试会因此变红 |
| `omicsclaw/launch/__init__.py:188` | `_adopt_dotenv` docstring 里的 `oc cli -- --configure` |
| `omicsclaw/launch/_dotenv.py:5` | 同上 |
| `omicsclaw/entry/cli/_configure.py:725-727` | `missing_credential_hint` 的 `oc cli -- --configure` → `oc cli --configure` |
| `omicsclaw/entry/cli/__init__.py:9` | 模块 docstring 的示例行 |
| `CLAUDE.md:232-233`、`AGENTS.md:83` | "Deployment flags go before `--`…" 补一句 surface 标志也可直接写。`oc cli --permission-mode read-only -- --session <id>` 这类示例仍然有效，不必改 |
| `.env.example`（19/22/256/260/265/405）、`README.md` / `README_zh-CN.md` / `docs/` 中的 `-- --` 拼法 | 统一为推荐拼法 |

`Makefile:145/151/154` 用的是 `oc channel -- --channels …`，兼容，不改。
`pyproject.toml:471-473`（`oc`/`omicsclaw` → `omicsclaw.launch:main`）、
`omicsclaw/__main__.py`、仓库根 `omicsclaw.py` 三个入口都落在同一个 `main`，
不受影响。`omicsclaw/entry/cli/_slash_command_support.py` 解析的是会话内用户
输入，与 argv 无交集，无冲突。

## 7. 测试

**要改的（2 条语义反转 + 3 处文案）**

- `tests/launch/test_configure_command.py:286`
  `test_the_flag_goes_after_the_terminator_like_every_other_surface_flag`
  → 反转并改名为 `test_the_flag_needs_no_terminator`：`oc cli --configure`
  必须真的进 wizard。**须改用同文件的 `configure(tmp_path, _ANSWERS)` 夹具**，
  否则 wizard 读到 EOF；顺带把该夹具对两种拼法参数化。
- `tests/launch/test_cli_command.py:298`
  `test_a_surface_flag_before_the_terminator_is_refused`
  → 反转：`oc cli --workspace X --session run-7` 应当起 REPL 且
  `session_id == "run-7"`。**初稿漏了这条，是审核找出来的**；它今天是绿的，
  语义正是本计划要推翻的那一条。
  同时在 `docs/plans/0037-launch-and-entry-points.md:593`（把它登记为"原样"
  迁移的那一行）加一句指向 0048 的注记。
- hint 文案的三处断言：`tests/entry/test_cli_configure.py:534`、
  `tests/launch/test_configure_command.py:386`、`:404`。全仓库断言
  `oc cli -- --configure` 的**只有这三处**（`:393` 的
  `assert "--configure" not in stderr` 不受影响）。

**要加的**

| 测试 | 断言 |
|---|---|
| 认领：arity 0 | `["--configure"]` → `([], ["--configure"])` |
| 认领：arity 1 连值 | `["--session", "run-7"]` → `([], ["--session", "run-7"])` |
| 认领：部署标志原样留下 | `["--workspace", "/data", "--configure"]` → `(["--workspace", "/data"], ["--configure"])` |
| 认领：值位不认领 | `["--workspace", "--configure", "/data"]` → 全部留在部署侧 |
| **认领：空 inline（裁定 B）** | `["--workspace=", "--configure"]` → `--configure` 是 `--workspace` 的值，**不认领** |
| 认领：inline 自带值 | `["--session=run-7"]` → `([], ["--session", "run-7"])` |
| 认领：裸 `--`（裁定 A） | `["--configure", "--", "--session", "x"]` → `--` 及其后原样留在部署侧 |
| 认领：缺值不在这里报（裁定 C/D） | `_claim_surface_flags(["--session"], CLI_FLAGS)` 不抛异常；拒绝由解析器给出 |
| 优先级 | `oc cli --session a -- --session b` → `session_id == "b"` |
| 认领引发的拒绝仍是退出码 2 | `oc cli --bogus x --session` → 2，且不是 0 |
| 端到端 · cli | **走子进程 + 空管道**（照 `test_cli_command.py:101-131` 的 `run_command`），不要 in-process 起 REPL——本包没有 `pytest-timeout`，会挂 |
| 端到端 · desktop | `main(["desktop", "--host", "127.0.0.1", "--help"])` → 0。**不要用 `--port 0`**：`_as_port` 是 `not 0 < port < 65536`，0 被故意拒绝（`_surfaces.py:605-606`，`test_surfaces.py:77-87` 钉着），且 `parse` 在 help 分支之前 |
| 端到端 · channel | `main(["channel", "--list"], {})` → 0 |
| 表与解析器不漂移 | §4.2 的交叉探针，以 `SHELL_FLAGS - {"--"}` 为枚举源，三个 surface 各一条 |
| `test_grammar.py` 补空 inline | `split_command_line(["--workspace=", "--help"])` 的裁定钉住（跟随裁定 B 后其结果会变，这是**有意的**） |

**已有的、本次当作守卫依赖的**（均已实测属实，见 §11）

- `test_the_surface_flags_and_the_deployment_flags_do_not_overlap`（§3 的前提）
- `test_the_flags_the_shell_acts_on_are_exactly_these`：新表里的
  `MappingProxyType({...})` 字面量会被它的 `_flag_literals` 收集，且全部已在
  `SHELL_FLAGS` 中，**不需要改这条测试**；`-h` 能通过 `_looks_like_a_flag`
  且已在 `SHELL_FLAGS`
- `test_the_shell_names_no_deployment_flag`（新表若混入部署标志则红）
- `test_an_unknown_deployment_flag_is_never_discarded_by_a_surface`（保持绿）

## 8. 验证

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest \
  tests/launch tests/entry -q -p no:randomly -p no:cacheprovider -o addopts=""
```

再跑一次 `AGENTS.md` 里那条整栈命令作为回归信号。手工验收五条：

```bash
oc cli --configure            # 进 wizard
oc cli --show-reasoning       # 起 REPL 并打印推理
oc cli -- --configure         # 旧拼法逐字兼容
oc cli --bogus --configure    # 仍因 --bogus 被拒，退出码 2
oc cli --workspace= --configure   # 裁定 B：--configure 是 --workspace 的值
```

> 手工验收第 1 条会**写 `.env`**。仓库根的 `.env` 是 owner 的真实凭据，必须
> 在临时目录 + `OMICSCLAW_DIR` 指向临时目录下跑（照
> `tests/launch/test_configure_command.py` 的夹具），
> `test_the_repository_dotenv_is_never_touched` 是最后一道保险。

## 9. 风险与回滚

| 风险 | 缓解 |
|---|---|
| **实现者照抄 `_grammar.py:158` 的 `"=" in token`**，得到与部署侧不一致的位置判断，且现有测试区分不出来 | §4.1 裁定 B 写死算法；§7 的空 inline 用例两处 |
| 某天新增的部署标志与 surface 标志重名 | 既有的不相交测试先红；新表在 `_surfaces.py` 内，`test_the_shell_names_no_deployment_flag` 也会红 |
| 表与解析器漂移 | §4.2 的交叉探针，枚举源是被精确钉住的 `SHELL_FLAGS` |
| 值位上的部署标志被 surface 标志吃掉 | 结构上修不了（§3），文档化；`--` 仍是消歧写法 |
| inline 支持扩大了行为面 | §4.4 单列，可被 owner 否决而不影响主体 |
| 回滚 | 改动集中在 `_surfaces.py` 的一个函数 + 三行接线 + 三张表；删掉即回到今天的行为 |

## 10. 待 owner 裁定

1. §4.4 —— 三个 surface 解析器是否一并支持 `--flag=value`（倾向：是）。
2. §6 —— `missing_credential_hint` 与文档是否统一改成不带 `--` 的拼法
   （倾向：是；旧拼法仍然可用，但推荐拼法只该有一个）。

## 11. 审核记录（2026-09-22，一轮独立只读审核）

结论是"需修改后实施"，方向无硬伤。本文已按其返工，四条必须修正逐条落地：

| # | 审核发现 | 落在 |
|---|---|---|
| M1 | 初稿漏了必然变红的 `test_a_surface_flag_before_the_terminator_is_refused` | §7「要改的」第 2 条 |
| M2 | "与 `_from_argv` 同一步长"不成立：终止符 break、未命中直接 raise、`if inline:` 判非空——三个分支都不能照搬；且 `_help_in_flag_position` 本身已偏离而 docstring 声称没有 | §4.1 裁定 A–D、§2 第三个参与者、§9 头号风险 |
| M3 | "从解析器反推标志集"做不到，推不出它声称要守的那种漂移 | §4.2 改为以 `SHELL_FLAGS` 为枚举源的交叉探针 |
| M4 | `main(["desktop","--port","0","--help"])` 用例本身错（0 被 `_as_port` 拒），且 cli 那条端到端 in-process 起 REPL 会挂（本包无 `pytest-timeout`） | §7 端到端三行 |

建议补充中采纳：值位上的部署标志被吃掉（§3）、重复标志与空 token（§4.1 表）、
0037 §5.2 措辞精确化 + 新增退出码测试（§4.3）、漏掉的四处文档（§6）、
help 标志集第三份拷贝（§4.2）、仓库里已有一批写成新拼法的文档（§1）。

我另行复核并确认属实的：`test_cli_command.py:298` 今天为绿且语义正被推翻；
`_as_port` 的 `not 0 < port < 65536`；`config.py:876` 的 `if inline:` 与
`_grammar.py:158` 的 `"=" in token` 确实分歧；`--prompt-file` 的缺值检查先于
读文件。

## 12. 交付记录（2026-09-22）

按 §4 实现，四条裁定逐条落地，没有偏离。实现期的三点补充：

**1. 认领函数最终不抛任何异常，S2 那个"窄例外"因此收窄了一半。**
§4.1 的裁定 C/D 原本只说"缺值不在这里报"，实现时发现把它推到极致更省：
`_claim_surface_flags` 一条 `raise` 都没有，缺值的 surface 标志原样认领、由
surface 解析器报，未知部署标志原样留下、由 `_from_argv` 报。于是拒绝仍然只有
两个来源。§4.3 记的那个变化依然存在（`oc cli --bogus x --session` 先报
`--session needs a value`），但它来自"parse 先于 resolve"这条既有顺序，不是
认领新引入的第三个报错点。

**2. 交叉探针测试发现三张表与解析器完全一致，一次就绿。**
`test_the_flag_table_matches_the_parser` 以 `SHELL_FLAGS - {"--"}` 为枚举源
反探三个解析器，17 个标志 × 3 面，首次运行即通过——说明 §4.2 手写的三张表
没有抄错。这条测试的价值在将来：它是防漂移的，不是防抄错的。

**3. 一处计划没预料到的文档回归，改文档时自己撞上的。**
把 `oc <surface> -- --flag` 批量收敛成 `oc <surface> --flag` 时，
`AGENTS.md:464-466` 那句「`oc cli --help` 列部署标志；`oc cli -- --help` 列
REPL 自己的」被折成了两句一模一样的话。**那句话本来就是错的**——`--help`
一直被上提，两种拼法打印的是同一份 `CLI_USAGE`——只是收敛拼法让它的错暴露了
出来。已改写为：`oc cli --help` 打印本 surface 的标志，部署标志由
`resolve_app_config` 读、拿一个未知的去问它才看得到列表。

### 落地的文件

`omicsclaw/launch/_surfaces.py`（`flag_stride` / `_split_inline` /
`_refuse_a_value` / `_claim_surface_flags`、三张 `*_FLAGS` 表、三个解析器的
inline 支持、三处接线、三份 usage 与 `start_cli` 的 docstring）、
`omicsclaw/launch/_grammar.py`（`_help_in_flag_position` 改用共享步长、
docstring 与 `usage()` 正文）、`omicsclaw/launch/__init__.py`、
`omicsclaw/launch/_dotenv.py`、`omicsclaw/entry/cli/_configure.py`（hint 与
wizard 收尾打印的启动命令）、`omicsclaw/entry/cli/__init__.py`，以及
`README.md` / `CLAUDE.md` / `AGENTS.md` / `.env.example` / `Makefile` 的拼法。

### 测试

新增 `tests/launch/test_flag_claiming.py`（21 项）、`test_grammar.py` 的
`test_an_empty_inline_value_is_not_a_value`（2 项）、`test_cli_command.py` 的
`test_an_unknown_deployment_flag_survives_the_claim`；反转两条
（`test_the_flag_needs_no_terminator`、
`test_a_surface_flag_before_the_terminator_is_claimed`）并新增
`test_both_spellings_reach_the_same_wizard`；hint 文案三处断言随之更新。

### 未做、留给 owner 决定的一件事

`omicsclaw/entry/config.py:873` 的拒绝消息仍是
`unknown option '--bogus'; pass a surface's own flags after '--'`。
§5 把它列为非目标，所以没动；但 surface 标志现在根本走不到这条消息，
那半句建议对着一个真正的错字已经是死建议。要改的话是一处独立的小改动。
