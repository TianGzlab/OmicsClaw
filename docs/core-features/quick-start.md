# OmicsClaw 快速开始

> 本文带你完成安装、配置 LLM、第一次运行 `oc cli`、跑通一个 skill demo。
> 所有命令、变量与默认值均按当前代码核实（`pyproject.toml`、`environment.yml`、`0_setup_env.sh`、`omicsclaw/launch/`、`omicsclaw/entry/`、`.env.example`）。

---

## 1. 前置条件

| 项 | 要求 |
|---|---|
| Python | `>=3.11,<3.14`（`pyproject.toml` `requires-python`）；`environment.yml` 固定 `python=3.11` |
| 包管理 | 推荐 mamba（Miniforge 自带），conda 可作回退 |
| 平台 | Linux / macOS；R 与生信 CLI 工具由 conda 环境提供 |
| LLM | 任一 OpenAI 兼容或 Anthropic 的 API key；或本地 Ollama |

---

## 2. 安装

### 2.1 完整环境（推荐，真实分析用）

```bash
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw
bash 0_setup_env.sh                 # 默认环境名 OmicsClaw；bash 0_setup_env.sh my_env 自定义
conda activate OmicsClaw
```

`0_setup_env.sh` 分层完成：

1. `mamba env create` / `conda env create` 读 `environment.yml`：工具链、R 与生信 CLI、重量级 Python 科学栈，
   以及 agent 运行所需的 `rich`、`prompt-toolkit`、`openai`、`fastapi`、`uvicorn` 等；
2. `uv pip install -e ".[full,singlecell-upstream]"`（没有 uv 时退回 pip）安装 omicsclaw 本身与 PyPI-only 包；
3. `Rscript` 安装 GitHub 上的 R 包；
4. 链接 `tools/` 下的 vendored 二进制（当前为空）。

可选环境变量：`OMICSCLAW_TORCH_BACKEND=auto|cuda|cpu`、`OMICSCLAW_WITH_BANKSY=1`（额外建 banksy 子环境）。
`make setup-env` / `make setup-env-name NAME=foo` 是同一脚本的快捷方式。

### 2.2 轻量安装（只想跑 agent 或纯 Python skill）

```bash
pip install -e .                    # 核心依赖：rich、openai、anthropic、setuptools、socksio、pydantic
```

纯 pip 环境装完就能运行 `oc cli` 并调用模型。`fastapi`/`uvicorn`、`prompt-toolkit`、`questionary`、`python-dotenv` 和科学计算栈只在 `environment.yml` 里：
`oc desktop` 在纯 pip 环境里要自己补装 `fastapi` 与 `uvicorn`；没有 `prompt_toolkit` 时 REPL 降级为无补全的行读取，
没有 `questionary` 时 `--configure` 改用编号菜单，没有 `python-dotenv` 时 `.env` 由内置的解析器读取，三者都不会失败。

### 2.3 可选 extras

| extra | 用途 |
|---|---|
| `.[channels]` | `python-telegram-bot`、`lark-oapi`（Telegram、飞书）；其他平台见 `pyproject.toml` 注释（`slack-sdk aiohttp`、`discord.py`、`httpx websockets`、`qq-botpy`，Email 只用标准库） |
| `.[otel]` | OpenTelemetry OTLP 导出 |
| `.[spatial]`、`.[singlecell]`、`.[bulkrna]`、`.[full]` … | 各领域分析方法的 PyPI-only 依赖 |

### 2.4 启动命令

安装后有两个等价的 console script：`oc` 与 `omicsclaw`（都指向 `omicsclaw.launch:main`）。没装进 PATH 时：

```bash
python omicsclaw.py cli             # 源码 checkout
python -m omicsclaw.launch cli
python -m omicsclaw cli
```

验证：

```bash
$ oc --help
usage: oc <surface> [deployment flags] [-- surface flags]

Surfaces:
  cli       terminal REPL, or one exchange with --prompt-file
  desktop   HTTP backend for the OmicsClaw-App client
  channel   instant-messaging adapters (Telegram, Feishu, ...)
...
```

`oc` 只有这三个子命令；没有 `oc run`、`oc onboard`、`oc interactive`、`oc tui`、`oc upgrade`。

---

## 3. 配置 LLM

### 3.1 最省事：配置向导

```bash
oc cli --configure
```

依次询问 provider、API key、model、endpoint、workspace，以及可选的 Telegram / 飞书 / Desktop token，然后写入外壳加载的 `.env`
（保留你已有的注释和其他变量，旧文件备份为 `.env.backup-<时间戳>`，密钥只显示末 4 位）。结束时打印"本部署现在解析为"的 provider / model / endpoint。

### 3.2 手写 `.env`

```bash
cp .env.example .env
```

```env
# 必填：key（先读 LLM_API_KEY，再读 OMICSCLAW_API_KEY）
LLM_API_KEY=sk-...

# 可选：留空则按 key 推断 / 用预设默认
LLM_PROVIDER=deepseek        # anthropic dashscope deepseek gemini moonshot nvidia ollama openai openrouter siliconflow volcengine zhipu custom
LLM_MODEL=                   # 空 = 预设默认，例如 deepseek → deepseek-v4-flash
LLM_BASE_URL=                # 空 = 预设自己的地址；换厂商时记得清空，否则会劫持下一个 provider
```

也可以只设厂商专用 key（`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`、`OPENROUTER_API_KEY`、`DASHSCOPE_API_KEY` …），
provider 会按 `DETECT_ORDER`（deepseek、openai、anthropic、gemini、nvidia、siliconflow、openrouter、volcengine、dashscope、moonshot、zhipu）自动探测。
本地 Ollama：`LLM_PROVIDER=ollama`，默认地址 `http://localhost:11434/v1`，无需 key。

### 3.3 `.env` 放在哪、谁优先

外壳启动时读两个 `.env`（`omicsclaw/launch/_dotenv.py`）：先读**项目根**（`OMICSCLAW_DIR`，或含 `omicsclaw.py` 的源码根），再读**当前目录**；
都以 `override=False` 加载。

**优先级：命令行 flag > 已 `export` 的变量 > `.env` 文件 > 默认值。**

> `.env` 含密钥，不要提交到 Git。

---

## 4. 首次运行

**在仓库根目录启动**（workspace 默认是当前目录，`skills/` 从 workspace 读，运行时契约 `OMICSCLAW.md` 从 `skills/` 旁读）：

```bash
cd OmicsClaw
oc cli
```

你会看到 OmicsClaw 的 ASCII Logo、会话 id / workspace / model / provider 横幅，以及一句欢迎语，然后是提示符：

```
❯
```

直接用自然语言提问：

```
❯ 有哪些空间转录组的 skill？哪个适合做反卷积？
❯ 用 bulkrna-de 跑一下 demo，输出到 /tmp/de_demo，然后解释火山图
❯ 我有 data/visium.h5ad，先做预处理再找空间域
```

agent 会调用 `use_skill` 读取对应 `SKILL.md`，再用 `bash` 运行 skill 脚本。`bash`、`write_file`、`edit_file`、`web_fetch`、`web_search`
默认需要审批，终端会出现审批卡片：

```
approve bash [#1]? [y/N/a=always]
```

| 回答 | 效果 |
|---|---|
| `y` | 允许这一次 |
| `s` | 本会话内不再询问这个工具 |
| `a` | 为这个精确调用写一条 `allow` 规则到 `.omicsclaw/settings.json` |
| 其他 / 回车 | 拒绝 |

嫌频繁确认可以输入 `/auto`（切到 `auto-approve`，并记住到下次 `oc cli` 启动）；危险命令、显式 `ask` 规则、对 `.omicsclaw/` 或 `.env` 的改动仍会询问。
执行分析时建议开沙箱：`oc cli --sandbox docker --sandbox-image <已拉取的镜像>`。

按 `Ctrl-C` 取消当前回答（会话保留）；空闲时 `Ctrl-C`、`/exit`、`/quit`、`/q` 或 `Ctrl-D` 退出。

### 4.1 一次性执行

```bash
oc cli --prompt "列出 skills/bulkrna 下的 skill 并各用一句话说明"
oc cli --prompt-file task.md            # 整个文件作为一条消息
```

一次性执行**没有人回答审批**，所有需审批的工具都会被拒绝；需要跑脚本时加 `--permission-mode auto-approve`（部署 flag）：

```bash
oc cli --permission-mode auto-approve --prompt "用 bulkrna-de 跑 demo 到 /tmp/de_demo 并总结结果"
```

stdout 不是终端时默认只输出答案（不含推理），适合 `> answer.txt`。收敛退出码为 0，否则 1。

---

## 5. 跑一个 skill demo

### 5.1 不经过 agent，直接跑脚本

每个 skill 的脚本都能独立运行，`--help` 查看参数，`--demo` 使用合成数据：

```bash
python skills/bulkrna/bulkrna-de/bulkrna_de.py --demo --output /tmp/de_demo
python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/spatial_pp_demo
make demo                    # = spatial-preprocess 的 demo，输出到 /tmp/omicsclaw_demo
```

`bulkrna-de` demo 的实际输出：

```
Success: bulkrna-de
  Output: /tmp/de_demo
  Method: ttest
  DE genes: 100 (up=50, down=50)

/tmp/de_demo/
├── report.md
├── result.json
├── figures/      volcano_plot.png  ma_plot.png  de_barplot.png  pvalue_histogram.png
├── tables/       de_results.csv  de_significant.csv
└── reproducibility/commands.sh
```

`examples/` 下有若干演示输入（如 `examples/demo_bulkrna_counts.csv`、`demo_proteomics.csv`、`demo_metabolomics.csv`）；
当前工作树里**没有** `examples/demo_visium.h5ad`，空间 skill 请用 `--demo`。

### 5.2 让 agent 跑

```
❯ 用 bulkrna-de 跑 demo，输出到 /tmp/de_demo，打开 report.md 给我总结
```

链式分析时，先跑领域的基础步（空间：`spatial-preprocess`；单细胞：`sc-preprocessing`），再把它输出目录里的处理后 `.h5ad` 交给下一步。
详见 [agent-skills.md](agent-skills.md)。

### 5.3 浏览 skill

```
❯ /skills                # 按领域列出全部 94 个
❯ /skills deconv         # 在 name / domain / tags / triggers 中搜索
```

skill 不是斜杠命令：`/spatial-de` 会被告知"没有这个命令"。在请求里提到 skill 名或直接描述任务即可。
命令行里也可以 `make list` 查看索引（打印 skill 数、跳过数与每个领域的名字）。

---

## 6. 常用 REPL 命令

| 命令 | 说明 |
|---|---|
| `/help` | 列出可用命令 |
| `/skills [query]` | 列出 / 搜索 skill |
| `/new`、`/clear` | 开始新会话（旧会话仍可恢复） |
| `/sessions` | 最近的会话 |
| `/resume [id\|编号]` | 恢复会话；无参数时方向键选择 |
| `/compact` | 立即压缩上下文 |
| `/plan`、`/tasks` | 查看 agent 的执行计划 |
| `/usage` | 本次 REPL 的 token 用量 |
| `/mcp` | `.mcp.json` 中 MCP 服务器状态 |
| `/auto [on\|off\|status]` | 切换自动批准 |
| `/current` | 当前会话、workspace、权限模式 |
| `!<cmd>` | 在 workspace 里直接跑 shell 命令（不经模型、不审批、60 秒上限），输出会附在你的下一个问题前 |
| `/exit`（`/quit`、`/q`） | 退出 |

完整说明见 [cli.md](cli.md)。

---

## 7. 项目规范文件

OmicsClaw 从 **workspace** 读取以下文件：

| 文件 | 作用 | 说明 |
|---|---|---|
| `OMICSCLAW.md` | 运行时契约，system prompt 第一段 | 从 skill 树旁读（未设 `skills_dir` 时即 workspace）；每轮重新读取；不存在则整段省略。安全规则不在这里，是常量 `SAFETY_RULES` |
| `skills/` | skill 语料 | `--skills-dir` / `OMICSCLAW_SKILLS_DIR` 可改；`--skills-index full\|compact\|off` |
| `.mcp.json` | MCP 服务器 | `--mcp-config` 可改；启动时并发连接 |
| `.omicsclaw/settings.json` | 权限规则 | 审批时答 `a` 会写这里 |
| `.omicsclaw/agents/` | 子代理定义 | |
| `.omicsclaw/memory.db` | 会话与长期记忆 | `--memory false` 则不落盘 |

`--system-prompt-file a.md:b.md`（或 `OMICSCLAW_SYSTEM_PROMPT_FILES`）用自己的文件**替换** `OMICSCLAW.md`；
safety、tool guidance、environment 三段不是文件，不能被替换或关闭。

---

## 8. 其他入口

```bash
# Desktop：OmicsClaw-App 的后端，默认 127.0.0.1:8765；一个进程服务一个工作区
oc desktop --workspace <项目目录>
OMICSCLAW_REMOTE_AUTH_TOKEN=... oc desktop --workspace <dir> -- --host 0.0.0.0     # 非回环地址必须设 token

# Channel：IM 机器人（必须配置 owner allowlist 与审批期限）
pip install -e ".[channels]"
oc channel --list
oc channel --approval-timeout 120 --channels telegram
```

Channel 需要的变量见 `.env.example` 第 11 节；飞书需要 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_ALLOWED_SENDERS` 与 `FEISHU_BOT_OPEN_ID`
（当前代码四者缺一即拒绝启动）。一个平台一个进程更稳妥。详见 [surfaces.md](surfaces.md)。

---

## 9. 常见问题

**Q：启动时提示 `omicsclaw: no LLM API key is configured. Set one up with: oc cli --configure`**
没有找到任何 key。运行 `oc cli --configure`，或确认 `.env` 在项目根 / 当前目录、变量名是 `LLM_API_KEY` 或厂商专用名。

**Q：`/skills` 显示 "No skills indexed for this workspace."**
你不是在仓库根目录启动的。workspace 默认是当前目录，skill 从 `<workspace>/skills` 扫描。回到仓库根启动，或设置
`OMICSCLAW_SKILLS_DIR=/path/to/OmicsClaw/skills`（此时运行时契约 `OMICSCLAW.md` 也从仓库读）。把这一行写进仓库根的 `.env`，从任何目录启动都会同时拿到仓库的 skill 和契约，不需要改代码。

**Q：`omicsclaw: unknown option '--xxx'; pass a surface's own flags after '--'`**
`--xxx` 既不是部署 flag 也不是本界面的 flag。`oc cli --help` 查看界面 flag；部署 flag 的完整列表见 `.env.example` 或 `omicsclaw/entry/config.py`。
值本身像 flag 时放到 `--` 之后：`oc cli -- --prompt --model`。

**Q：反卷积 / 比对跑到一半被杀**
工具默认上限 600 秒。调大 `--tool-timeout 3600`（或 `OMICSCLAW_TOOL_TIMEOUT_S`），`bash` 自动跟随（减 15 秒余量），不要设第二个数。

**Q：一次性 `--prompt` 执行时脚本都没跑**
一次性执行无人回答审批，需加 `--permission-mode auto-approve`。

**Q：`oc desktop` 报 `the desktop surface needs uvicorn and fastapi`**
当前环境缺 fastapi/uvicorn。它们由 conda 管理：`mamba env update -f environment.yml`，或 `mamba install -c conda-forge fastapi uvicorn`（`[desktop]` extra 已删除）。

**Q：`oc channel` 启动失败，提示必须设置 `approval_timeout_s`**
Channel 界面要求审批期限：加 `--approval-timeout <秒>` 或 `OMICSCLAW_APPROVAL_TIMEOUT_S`。注意当前 Channel 上还无法回答审批，需要审批的工具会在期限到时被拒。

**Q：有没有 `oc run <skill>`、`python omicsclaw.py replot`？**
没有，都已删除。直接运行 `python skills/<domain>/<skill>/<script>.py`，或让 agent 在会话里跑。`result.json` 里的 `replot` 提示指向的命令不存在。

**Q：会话存在哪里？怎么继续？**
`<workspace>/.omicsclaw/memory.db`。`/sessions` 查看，`/resume` 或 `oc cli --session <id>` 继续。

**Q：每份报告里的免责声明是什么？**
"OmicsClaw is a research and educational tool for multi-omics analysis. It is not a medical device and does not provide clinical diagnoses. Consult a domain expert before making decisions based on these results."——它同时写在 system prompt 的 safety 段与 `omicsclaw/common/report.py` 的 `DISCLAIMER` 中。

---

## 10. 已知限制

1. 纯 `pip install -e .` 不含 `fastapi`/`uvicorn`，`oc desktop` 需要 conda 环境或自行补装。
2. `examples/demo_visium.h5ad` 不存在。
3. Channel 还不能回答审批；Desktop 通过 App 的卡片回答（见 surfaces.md §8.2、§10）。

---

## 11. 文件索引

| 文件 | 内容 |
|---|---|
| `0_setup_env.sh`、`environment.yml` | 完整 conda 环境 |
| `pyproject.toml` | 核心依赖、extras、`[project.scripts]`（`oc`、`omicsclaw`） |
| `Makefile` | `setup-env`、`install`、`demo`、`list`、`skill-index`、`test` 等快捷方式 |
| `.env.example` | 全部环境变量（12 节） |
| `omicsclaw/launch/` | `oc` 外壳：文法、`.env`、三个界面的启动 |
| `omicsclaw/entry/cli/_configure.py` | `oc cli --configure` 向导 |
| `omicsclaw/provider/config.py` | `PRESETS`、`DETECT_ORDER`、`resolve_config` |
| `OMICSCLAW.md` | 运行时契约（system prompt 第一段） |
| `skills/`、`templates/skill/` | skill 语料与模板 |
| [agent-skills.md](agent-skills.md)、[cli.md](cli.md)、[surfaces.md](surfaces.md) | 深入文档 |
