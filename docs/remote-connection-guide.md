# OmicsClaw-App 远程连接配置指南

本文档说明如何在 OmicsClaw-App 中配置**远程服务器执行**。配置完成后，App 保留在本地负责 UI、聊天和结果浏览，数据处理与作业执行则放在远端 Linux 服务器上。

## 架构概览

```
┌────────── OmicsClaw-App (control plane) ────────┐
│  Next.js UI  ·  Electron                        │
│  SSH Tunnel Manager → 127.0.0.1:<localPort>      │
└──────────────────┬──────────────────────────────┘
                   │  HTTPS/SSE over SSH tunnel
┌──────────────────▼──────────────────────────────┐
│  远程 Linux 服务器 (execution plane)              │
│  oc app-server ── 127.0.0.1:8765                │
│  Remote control plane + notebook routes          │
│  Remote jobs run as local OmicsClaw subprocesses │
│  Datasets / Jobs / Artifacts on workspace disk   │
└─────────────────────────────────────────────────┘
```

## 前置条件

### 远端服务器

| 要求 | 说明 |
|---|---|
| OS | Linux（Ubuntu 20.04+、CentOS 7+、或同等） |
| Python | 3.10+，带 `pip`，推荐 conda/venv 隔离 |
| OmicsClaw | 已完成 `git clone`，并安装 `pip install -e ".[desktop]"` |
| SSH | 开启 sshd，允许公钥认证 |
| 端口 | 无需公网端口 — 所有通信走 SSH tunnel |
| 磁盘 | Workspace 目录至少 20 GB 可用空间 |
| GPU（可选）| CUDA + PyTorch 用于 GPU 加速的 skill（如 scVI、Cell2Location）|

### 本地（App 端）

| 要求 | 说明 |
|---|---|
| OmicsClaw-App | 最新版本（含 Remote Connection 功能） |
| SSH 密钥 | `~/.ssh/id_ed25519` 或 `~/.ssh/id_rsa` |
| ssh-agent | 推荐运行（`eval $(ssh-agent) && ssh-add`） |

## 配置步骤

### Step 1 — 启动远端 `oc app-server`

在远端服务器通过 SSH 登录后执行：

```bash
# 激活 Python 环境
source .venv/bin/activate   # 或 conda activate omicsclaw

# 设置 workspace 目录（所有数据、job产物存放位置）
export OMICSCLAW_WORKSPACE=/data/omicsclaw-workspace
mkdir -p "$OMICSCLAW_WORKSPACE"

# （推荐）设置 bearer token 作为第二层安全
export OMICSCLAW_REMOTE_AUTH_TOKEN="your-secret-token-here"

# 启动 app-server（绑定 127.0.0.1，不暴露公网）
oc app-server --host 127.0.0.1 --port 8765
```

验证：
```bash
curl http://127.0.0.1:8765/health
# 应返回 {"status":"ok","version":"..."}

curl -X POST http://127.0.0.1:8765/connections/test \
  -H "Authorization: Bearer $OMICSCLAW_REMOTE_AUTH_TOKEN"

curl http://127.0.0.1:8765/env/doctor \
  -H "Authorization: Bearer $OMICSCLAW_REMOTE_AUTH_TOKEN"
```

> `oc app-server` 就是 OmicsClaw-App 的统一后端入口。远程模式使用的 control-plane API、嵌入式 notebook 路由，以及可选的 KG 路由都挂在这个进程上，不需要额外再起一个 remote daemon。
>
> **后台运行**：可用 `nohup ... &` 或 `tmux`/`screen` 将 app-server 放到后台，这样断开 SSH 后服务不会停止。

### Step 2 — 在 OmicsClaw-App 创建 Connection Profile

1. 打开 **Settings → Connections** 面板
2. 点击 **"New Connection"**
3. 填写：

| 字段 | 示例值 | 说明 |
|---|---|---|
| Name | Lab GPU Server | 自定义名称 |
| SSH Host | 192.168.1.100 | 服务器 IP 或 hostname |
| SSH Port | 22 | 默认 22 |
| SSH User | zhouwg | 远端 Linux 用户名 |
| SSH Key Path | ~/.ssh/id_ed25519 | 本机私钥绝对路径 |
| Remote Python | /path/to/.venv/bin/python | 远端 Python 路径（可选，用于环境检查） |
| Remote Workspace | /data/omicsclaw-workspace | 与 Step 1 中 `OMICSCLAW_WORKSPACE` 一致 |
| Remote App Server Port | 8765 | 与 Step 1 中 `--port` 一致 |
| Auth Token | your-secret-token-here | 与 Step 1 中 `OMICSCLAW_REMOTE_AUTH_TOKEN` 一致 |

4. 点击 **"Test Connection"** — App 会打通 SSH tunnel，并依次探测 `/connections/test` 和 `/env/doctor`
5. 看到绿色 ✓ 后点 **"Save"**

### Step 3 — 切换到 Remote 模式

1. 在 **Settings → Backend** 面板将模式切换为 **Remote**
2. 选择刚创建的 Connection Profile 为 **Active**
3. 顶栏状态指示器变为 🌐（globe 图标） + 绿色 = 连接正常

### Step 4 — 导入数据

#### 方式 A：远端路径导入（大文件推荐）

适用于已经在服务器上的 `.h5ad` / `.csv` 文件：

1. 将文件 `scp` / `rsync` 到远端 workspace 下任意目录
2. 在 App **Datasets** 面板点 **"Register Remote Path"**
3. 输入远端绝对路径（如 `/data/omicsclaw-workspace/pbmc3k.h5ad`）
4. 点 **"Register"** — 后端校验文件存在并登记为远端 dataset

#### 方式 B：直接上传（小文件）

1. 在 **Datasets** 面板点 **"Upload"**
2. 选择本地文件 → App 通过 HTTP multipart 上传到远端
3. 上传完成后显示 **synced** 状态

> 当前 multipart 上传适合小文件使用；超过约 1 GiB 的数据更适合先 `scp` / `rsync` 到服务器，再走远端路径导入。

### Step 5 — 提交分析任务并观察执行

1. 在聊天窗口描述分析需求，如 "对 pbmc3k.h5ad 运行 spatial-preprocessing"
2. 或在 **Jobs** 面板手动提交：选择 Skill + 选择 Dataset + 设定参数 → Submit
3. Job 会进入 **queued → running → succeeded/failed/canceled** 生命周期
4. 后端会在远端 workspace 中创建持久化的 job 目录，并以本地 OmicsClaw subprocess 执行对应任务
5. **实时日志**在 Jobs 面板以 SSE 流式显示；重连后会从已有日志继续补发
6. 可随时点 **Cancel** 取消运行中的任务；已结束的任务可按需 **Retry**

### Step 6 — 查看产物与恢复上下文

1. Job 完成后进入 **Artifacts** 面板
2. 按 job 分组浏览：`report.md` / `figures/*.png` / `result.json` / processed `.h5ad`
3. 支持 Markdown / 图片预览，以及大文件下载
4. 若连接中断后重新打开 App，运行中的 job 和会话可从远端状态继续恢复

> 失败任务通常会保留 `stdout.log` 以及诊断文件，便于在 App 中回看失败原因。

## 安全说明

| 层 | 机制 |
|---|---|
| 第一层 | SSH tunnel — 所有流量加密；远端 app-server 仅绑 `127.0.0.1` |
| 第二层 | Bearer token — `OMICSCLAW_REMOTE_AUTH_TOKEN` 环境变量；App 会在受保护的 remote 请求上附加 `Authorization: Bearer <token>` |
| 数据隔离 | 遗传数据不离开服务器 — App 只拉 artifact（图表/报告），原始 `.h5ad` 留在远端 |

> **绝不要**将远端 app-server 的端口暴露到公网。如需从外网访问，始终通过 SSH tunnel 或 VPN。

## Session Resume（断线恢复）

- **Tunnel 断开**：App 自动检测断连；恢复后会重新订阅 job 事件并补齐日志
- **窗口关闭再打开**：再次进入 Jobs / Chat 时，App 会从远端状态恢复仍在运行的任务
- **服务器重启**：app-server 会把失去执行上下文的 orphaned `running` job 重新标记为失败，并保留诊断信息

## 故障排查

| 症状 | 检查 |
|---|---|
| Test Connection 失败 | 先确认 `ssh -i <key> <user>@<host>` 能否登录；再确认远端 `oc app-server` 正在运行，token 和端口填写正确 |
| 连接后显示不可用 | 确认 Active Profile 的 workspace / port 与远端实际配置一致；必要时直接 `curl /connections/test` 与 `/env/doctor` 复核 |
| 提示 workspace 未配置或目录不存在 | 确认远端 `OMICSCLAW_WORKSPACE` 已设置且目录真实存在；如需切换目录，也可以让 App 重新同步 workspace |
| 上传失败或提示文件过大 | 改用 `scp` / `rsync` 先传到服务器，再在 App 中走远端路径导入 |
| Job 很快失败 | 先看该 job 的 `stdout.log`；如果有诊断文件，再看 `diagnostics/env_doctor.json` 和 `diagnostics/stdout.log` |
| Job failed + `server_restart_orphaned_job` | 说明 app-server 重启前有未完成任务；这是保护性失败，不是数据损坏 |
| SSE 日志不显示 | 检查 tunnel 状态，确认远端 `/jobs/{id}/events` 可达，且 App 当前连接的是正确 profile |

## 常用命令速查

```bash
# 远端：启动 app-server（前台，便于看日志）
OMICSCLAW_WORKSPACE=/data/ws OMICSCLAW_REMOTE_AUTH_TOKEN=xxx \
  oc app-server --host 127.0.0.1 --port 8765

# 远端：检查健康
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

# 远端：列出 datasets
curl http://127.0.0.1:8765/datasets -H "Authorization: Bearer xxx"

# 远端：列出 jobs
curl http://127.0.0.1:8765/jobs -H "Authorization: Bearer xxx"
```
