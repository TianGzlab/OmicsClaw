# OmicsClaw-App 远程连接配置指南

本文档说明如何在 OmicsClaw-App 中把**数据处理 / 作业执行**放在远端
Linux 服务器上，App 本身留在本地负责 UI、聊天、结果浏览。

> 对齐版本：OmicsClaw-App **v0.1.3+**（引入 `Runtimes` 页面与 Bundled
> 运行时）。本文是 legacy Markdown 版；当前文档站入口见
> `docs/engineering/remote-execution.mdx`。

## 架构概览

OmicsClaw-App 通过统一的 **Runtimes** 抽象管理"Python 到底跑在哪"。
目前有四种 `RuntimeKind`：

| Runtime Kind | 说明 | 传输方式 | 典型场景 |
|---|---|---|---|
| `bundled` | App 自带便携 Python + 最小 app-server 运行时 | IPC / 本地 HTTP | 开箱即用的桌面体验 |
| `local-python` | 指向用户本机 Python 解释器 | 本地 HTTP | 本机已有 conda / venv 想复用 |
| `remote-ssh` | App 通过 SSH tunnel 连接远端 `oc app-server` | HTTP over SSH tunnel | **本文档主要场景** |
| `remote-url` | App 直连一个已有 URL | HTTP 直连 | 已有 `ssh -L` / VPN / 内网 URL |

同一时刻只有**一个** runtime 是激活的；切换通过 Runtimes 页面的
**Make Active** 完成。

```text
┌────────── OmicsClaw-App (control plane) ────────┐
│  Next.js UI · Electron                          │
│  Runtimes 页面（增/删/改/激活 4 类 runtime）     │
│  TunnelManager → 127.0.0.1:<dynamic-local>      │
└──────────────────┬──────────────────────────────┘
                   │  HTTP/SSE over SSH tunnel
┌──────────────────▼──────────────────────────────┐
│  远程 Linux 服务器 (execution plane)              │
│  conda env: OmicsClaw                            │
│  oc app-server ── 127.0.0.1:8765                │
│  Chat + remote control-plane + notebook + KG     │
│  Jobs 以本机 OmicsClaw subprocess 运行            │
│  Datasets / Jobs / Artifacts on workspace disk   │
└─────────────────────────────────────────────────┘
```

远端 `oc app-server` 是统一 backend 进程：它同时承载 chat streaming、
remote control-plane、notebook 路由、可选 KG 路由和作业执行入口。不要再为
remote mode 额外启动一个独立 daemon。

## 前置条件

### 远端服务器

| 要求 | 说明 |
|---|---|
| OS | Linux / WSL2 / 远端 Linux 服务器。完整 `environment.yml` 含 `gxx_linux-64`、`sysroot_linux-64` 等 Linux toolchain 包 |
| Conda | `conda` 或 `mamba` 在 `PATH` 上；推荐 Miniforge |
| OmicsClaw | 已 `git clone` 并通过 `bash 0_setup_env.sh` 完成完整环境 |
| SSH | sshd 允许公钥认证 |
| 对外端口 | 无需；推荐只走 SSH tunnel |
| 磁盘 | Workspace 目录建议至少 20 GB 可用，真实项目按数据规模增加 |
| GPU（可选） | NVIDIA GPU + CUDA；用 `OMICSCLAW_TORCH_BACKEND=auto/cuda` 在远端安装 PyTorch CUDA wheel |

远程分析服务器不要只装 `pip install -e ".[desktop]"` 或一个轻量 venv。
这类环境可以启动部分 App backend，但分析 job 可能缺 R、samtools、STAR、
fastqc、scanpy/scvi-tools 等依赖。完整远端分析路径应使用
`bash 0_setup_env.sh`。

### 本地 App 端

| 要求 | 说明 |
|---|---|
| OmicsClaw-App | v0.1.3+（含 Runtimes 页面） |
| SSH 密钥 | `~/.ssh/id_ed25519` 或 `~/.ssh/id_rsa`；未加密或已加入 ssh-agent |
| ssh-agent | 推荐运行：`eval $(ssh-agent) && ssh-add` |

App 端**不**负责生成 / 导入 SSH 密钥，也不提示 passphrase。必须是用户事先
准备好并可用的私钥。

## Step 0 — 准备远端 OmicsClaw 环境

SSH 登录远端 Linux 服务器：

```bash
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw

# CPU-safe baseline
bash 0_setup_env.sh

# GPU 服务器可改用强制 CUDA；失败时让 setup 直接退出，避免静默落到 CPU。
# OMICSCLAW_TORCH_BACKEND=cuda OMICSCLAW_PYTORCH_CUDA_VERSION=12.1 bash 0_setup_env.sh

conda activate OmicsClaw
oc env
oc list
```

脚本会安装 R 4.3、bioinformatics CLIs、heavy Python science stack、editable
OmicsClaw 和 GitHub-only R 包。重复执行会就地更新现有环境。

共享 conda 安装上，脚本默认使用私有包缓存 `~/.conda/pkgs`。如需指定：

```bash
export CONDA_PKGS_DIRS=/path/to/writable/pkgs
bash 0_setup_env.sh
```

如果远端已有旧的 `OmicsClaw` env，但 `/env/doctor` 显示缺依赖，优先重跑：

```bash
bash 0_setup_env.sh
```

必要时干净重建：

```bash
mamba env remove -n OmicsClaw -y
bash 0_setup_env.sh
```

## Step 1 — 在远端启动 `oc app-server`

在远端服务器上执行：

```bash
cd /path/to/OmicsClaw
conda activate OmicsClaw

# Workspace：dataset 登记、job 状态、stdout.log、artifact 的根目录
export OMICSCLAW_WORKSPACE=/data/omicsclaw-workspace
mkdir -p "$OMICSCLAW_WORKSPACE"

# 推荐：SSH 之外的第二层鉴权
export OMICSCLAW_REMOTE_AUTH_TOKEN="your-secret-token-here"

# 仅绑定 localhost；不要暴露公网
oc app-server --host 127.0.0.1 --port 8765
```

自检：

```bash
curl http://127.0.0.1:8765/health
# 期望包含：{"status":"ok", ...}

curl -X POST http://127.0.0.1:8765/connections/test \
  -H "Authorization: Bearer $OMICSCLAW_REMOTE_AUTH_TOKEN"

curl http://127.0.0.1:8765/env/doctor \
  -H "Authorization: Bearer $OMICSCLAW_REMOTE_AUTH_TOKEN"
```

`/connections/test` 会返回版本、GPU 探测和磁盘信息。`/env/doctor` 复用
`oc doctor` 的诊断逻辑，App 的 Run Ping 会用它判断远端环境是否可用。

后台运行可用 `tmux`、`screen`、`nohup` 或 `systemd --user`。例如：

```bash
cd /path/to/OmicsClaw
conda activate OmicsClaw
export OMICSCLAW_WORKSPACE=/data/omicsclaw-workspace
export OMICSCLAW_REMOTE_AUTH_TOKEN="your-secret-token-here"
nohup oc app-server --host 127.0.0.1 --port 8765 > app-server.log 2>&1 &
```

## Step 2 — 在 Runtimes 页面新建 Remote Runtime

1. 打开 App，进入 **Runtimes** 页面。
2. 点击 **New Runtime**，选择新建 connection profile。
3. 填写字段。没有 "Remote Python" / "Remote Workspace" 字段：远端 Python
   由你在服务器上激活的 conda env 决定，远端 workspace 由
   `OMICSCLAW_WORKSPACE` 决定。

| 字段 | 存库键 | 示例 | 说明 |
|---|---|---|---|
| Name | `name` | Lab GPU Server | UI 显示名 |
| URL | `url` | `http://127.0.0.1:8765` | direct-URL 场景必填；SSH 场景可留空 |
| Auth Token | `auth_token` | your-secret-token-here | 与远端 `OMICSCLAW_REMOTE_AUTH_TOKEN` 一致；GET 返回时遮罩 |
| SSH Host | `ssh_host` | 192.168.1.100 | 填写即为 SSH-tunneled profile |
| SSH Port | `ssh_port` | 22 | 默认 22 |
| SSH User | `ssh_user` | zhouwg | 远端 Linux 用户名 |
| SSH Key Path | `ssh_key_path` | `/home/me/.ssh/id_ed25519` | 本机私钥绝对路径；App 不管理密钥生命周期 |
| Remote Port | `remote_port` | 8765 | 远端 `oc app-server` 监听端口 |
| Auto-start Command | `remote_bootstrap_command` | 见下方示例 | 可选；仅 SSH 模式生效 |

推荐 Auto-start Command：

```bash
bash -lc 'cd /path/to/OmicsClaw && source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate OmicsClaw && export OMICSCLAW_WORKSPACE=/data/omicsclaw-workspace && export OMICSCLAW_REMOTE_AUTH_TOKEN="your-secret-token-here" && nohup oc app-server --host 127.0.0.1 --port 8765 > app-server.log 2>&1 &'
```

如果远端 shell 已自动初始化 conda，也可以简化为：

```bash
bash -lc 'cd /path/to/OmicsClaw && conda activate OmicsClaw && OMICSCLAW_WORKSPACE=/data/omicsclaw-workspace OMICSCLAW_REMOTE_AUTH_TOKEN="your-secret-token-here" nohup oc app-server --host 127.0.0.1 --port 8765 > app-server.log 2>&1 &'
```

保存后回到 Runtimes 列表：

1. 选中 profile。
2. 点击 **Run Ping**。
3. App 先探测 `/health`，再带 Bearer token 探测 `/env/doctor`。
4. 看到 ok 状态后点击 **Make Active**。

SSH tunnel 使用动态本地端口。App 会把本地 `127.0.0.1:<dynamic>` 转发到远端
`127.0.0.1:<remote_port>`；你不需要手动指定本地端口。编辑 host / user /
key / port 后，隧道会按新指纹重开。

## Step 3 — 确认当前 Active Runtime

- Runtimes 列表中，激活项显示绿色圆点和 **Active**。
- 顶栏状态指示器显示 Remote SSH / Remote URL。
- 绿色状态表示隧道已开且最近健康探测通过。

## Step 4 — 导入数据

### 方式 A：远端路径登记（大文件推荐）

文件已在服务器上：

1. 用 `scp` / `rsync` 放到 `$OMICSCLAW_WORKSPACE` 下任意目录。
2. App **Datasets** 面板点击 **Register Remote Path**。
3. 输入远端绝对路径，例如：

```text
/data/omicsclaw-workspace/pbmc3k.h5ad
```

后端校验文件存在并登记 dataset。import-remote 类型只保存元数据，不复制源
文件；删除 dataset 记录不会删除原始源文件。

### 方式 B：直接上传（小文件）

1. **Datasets** 面板点击 **Upload**。
2. 选择本地文件。
3. App 通过 HTTP multipart 上传到远端 workspace。

超过约 1 GiB 的文件推荐先 `scp` / `rsync`，再走方式 A。

## Step 5 — 提交分析任务并观察执行

1. 在聊天窗口发起分析请求，或在 **Jobs** 面板手动提交。
2. Job 生命周期：`queued -> running -> succeeded / failed / canceled`。
3. 后端在 `<workspace>/.omicsclaw/remote/jobs/<job_id>/` 建立持久化 job
   目录。
4. 作业以远端 `OmicsClaw` conda 环境中的本地 subprocess 执行。
5. 实时日志通过 SSE 流式显示；重连后从已有日志续发。
6. 可随时 Cancel；已结束任务可 Retry。

## Step 6 — 查看产物与上下文恢复

Job 完成后进入 **Artifacts** 面板，按 job 分组浏览：

- `report.md`
- `figures/*.png`
- `result.json`
- 处理后的 `.h5ad`
- 其他 skill 输出文件

失败任务会保留 `stdout.log` 和诊断文件，例如
`diagnostics/env_doctor.json`。

断线或 App 重启后，Jobs / Chat 会从远端状态恢复。服务器重启时，
`oc app-server` 会把失去执行上下文的 orphaned `running` job 标记为失败
（`server_restart_orphaned_job`），并保留诊断信息。

## Bundled vs Local vs Remote — 怎么选？

| 场景 | 推荐 Runtime |
|---|---|
| 只在本机试 UI / notebook，不想装 Python | `bundled` |
| 本机已有轻量 Python 环境，只跑 chat / routing | `local-python` |
| 数据或算力在实验室 Linux 服务器 | `remote-ssh` |
| 已有自己的 `ssh -L` / VPN / 内网 URL | `remote-url` |

Bundled runtime 只适合最小 app-server / notebook 体验，不等同于完整分析环境。
需要真实分析能力时，远端服务器应使用 `bash 0_setup_env.sh` 完成全量安装。

## 安全说明

| 层 | 机制 |
|---|---|
| 第一层 | SSH tunnel；远端 `oc app-server` 只绑定 `127.0.0.1` |
| 第二层 | Bearer token；设置 `OMICSCLAW_REMOTE_AUTH_TOKEN` 后所有 remote routers 都要求 `Authorization: Bearer <token>` |
| Token 存储 | App 端 profile 存 token；展示时遮罩 |
| 数据隔离 | 原始数据留在服务器，App 只拉取报告、图表、日志和用户请求的 artifact |

不要把远端 `oc app-server` 的端口暴露到公网。需要跨网络访问时，优先使用 SSH
tunnel 或 VPN；如果必须走 `remote-url`，务必使用内网、反向代理鉴权和 HTTPS。

## 故障排查

| 症状 | 检查 |
|---|---|
| Run Ping `/health` 失败 | 先确认 `ssh -i <key> <user>@<host>` 能登录；再确认远端 `oc app-server` 正在监听 `127.0.0.1:<remote_port>` |
| `/health` 绿但 `/env/doctor` 红 | Bearer token 不匹配，或远端 workspace / 依赖不完整；核对 `OMICSCLAW_REMOTE_AUTH_TOKEN`，再看 `/env/doctor` 返回的 checks |
| `/env/doctor` 显示大量依赖缺失 | 远端可能仍是旧 venv 或未完成 env update；在远端运行 `conda activate OmicsClaw && bash 0_setup_env.sh`，必要时重建 env |
| 提示 workspace 未配置 / 目录不存在 | 远端 `OMICSCLAW_WORKSPACE` 未 export，或目录不存在；创建目录后重启 `oc app-server` |
| Auto-start 失败 | 在远端手动执行同一条 `remote_bootstrap_command`；常见原因是非交互 shell 没加载 conda，需要 `source "$(conda info --base)/etc/profile.d/conda.sh"` |
| 上传失败 / 文件过大 | 改走 Register Remote Path，先 `scp` / `rsync` 到远端 |
| Job 很快失败 | 查看 job 的 `stdout.log`、`diagnostics/env_doctor.json` 和 skill 输出目录 |
| Job failed + `server_restart_orphaned_job` | app-server 重启前有未完成任务；这是保护性失败，不表示数据损坏 |
| SSE 日志不显示 | 检查隧道是否存活、当前 Active Runtime 是否变化、`active_tunnel_local_port` 是否刷新 |
| 编辑 SSH 字段没生效 | 指纹变更会触发隧道重开；如未发生，手动 Make Active 一次 |

## 常用命令速查

```bash
# 远端：安装 / 更新完整分析环境
cd /path/to/OmicsClaw
bash 0_setup_env.sh
conda activate OmicsClaw

# 远端：验证 CLI 和依赖状态
oc env
oc list
python -c "import scanpy, anndata; print('science stack OK')"

# 远端：前台启动 app-server（便于看日志）
export OMICSCLAW_WORKSPACE=/data/ws
export OMICSCLAW_REMOTE_AUTH_TOKEN=xxx
oc app-server --host 127.0.0.1 --port 8765

# 远端：健康检查
curl http://127.0.0.1:8765/health
curl -X POST http://127.0.0.1:8765/connections/test \
  -H "Authorization: Bearer xxx"
curl http://127.0.0.1:8765/env/doctor \
  -H "Authorization: Bearer xxx"

# 远端：查看 / 同步 workspace
curl http://127.0.0.1:8765/workspace
curl -X PUT http://127.0.0.1:8765/workspace \
  -H "Content-Type: application/json" \
  -d '{"workspace":"/data/ws"}'

# 远端：列 datasets / jobs
curl http://127.0.0.1:8765/datasets -H "Authorization: Bearer xxx"
curl http://127.0.0.1:8765/jobs     -H "Authorization: Bearer xxx"

# App 端（Next.js 路由，调试用）
#   GET  /api/runtimes
#   GET  /api/runtimes/:id
#   POST /api/runtimes/:id/ping
```

## 相关文档

- [INSTALLATION.md](INSTALLATION.md) — 当前 `0_setup_env.sh` 安装模型
- `docs/engineering/remote-execution.mdx` — 当前文档站远程执行页
- `omicsclaw/app/server.py` — `oc app-server` 的 FastAPI 入口
- `omicsclaw/remote/` — remote control-plane routers / auth / storage
- `OmicsClaw-App/docs/bundled-backend.md` — bundled runtime 构建和 BYO 回退规则
- `OmicsClaw-App/src/lib/runtimes/types.ts` — Runtime 类型字段定义
