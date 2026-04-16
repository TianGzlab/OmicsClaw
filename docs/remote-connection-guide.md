# OmicsClaw Desktop 远程连接配置指南

本文档说明如何在 OmicsClaw Desktop App 中配置**远程服务器执行**（control plane / execution plane 分离）。配置完成后，您的分析任务将在远端 Linux 服务器上运行，Desktop App 仅负责 UI 展示和交互。

## 架构概览

```
┌────────── Desktop App (control plane) ──────────┐
│  Next.js UI  ·  Electron                        │
│  SSH Tunnel Manager → 127.0.0.1:<localPort>      │
└──────────────────┬──────────────────────────────┘
                   │  HTTPS/SSE over SSH tunnel
┌──────────────────▼──────────────────────────────┐
│  远程 Linux 服务器 (execution plane)              │
│  oc app-server ── 127.0.0.1:8765                │
│  SubprocessExecutor → python omicsclaw.py run    │
│  Datasets / Jobs / Artifacts on workspace disk   │
└─────────────────────────────────────────────────┘
```

## 前置条件

### 远端服务器

| 要求 | 说明 |
|---|---|
| OS | Linux（Ubuntu 20.04+、CentOS 7+、或同等） |
| Python | 3.10+，带 `pip`，推荐 conda/venv 隔离 |
| OmicsClaw | `git clone` 并 `pip install -e .` 完成 |
| SSH | 开启 sshd，允许公钥认证 |
| 端口 | 无需公网端口 — 所有通信走 SSH tunnel |
| 磁盘 | Workspace 目录至少 20 GB 可用空间 |
| GPU（可选）| CUDA + PyTorch 用于 GPU 加速的 skill（如 scVI、Cell2Location）|

### 本地（Desktop App 端）

| 要求 | 说明 |
|---|---|
| OmicsClaw Desktop | 最新版本（含 Remote Connection 功能） |
| SSH 密钥 | `~/.ssh/id_ed25519` 或 `~/.ssh/id_rsa` |
| ssh-agent | 推荐运行（`eval $(ssh-agent) && ssh-add`） |

## 配置步骤

### Step 1 — 启动远端 OmicsClaw App Server

在远端服务器通过 SSH 登录后执行：

```bash
# 进入 OmicsClaw 仓库
cd /path/to/OmicsClaw

# 激活 Python 环境
source .venv/bin/activate   # 或 conda activate omicsclaw

# 设置 workspace 目录（所有数据、job产物存放位置）
export OMICSCLAW_WORKSPACE=/data/omicsclaw-workspace
mkdir -p "$OMICSCLAW_WORKSPACE"

# （可选）设置 bearer token 作为第二层安全（推荐）
export OMICSCLAW_REMOTE_AUTH_TOKEN="your-secret-token-here"

# 启动 app-server（绑定 127.0.0.1，不暴露公网）
python -m omicsclaw app-server --host 127.0.0.1 --port 8765
```

验证：
```bash
curl http://127.0.0.1:8765/health
# 应返回 {"status":"ok","version":"..."}
```

> **后台运行**：可用 `nohup ... &` 或 `tmux`/`screen` 将 app-server 放到后台，这样断开 SSH 后服务不会停止。

### Step 2 — 在 Desktop App 创建 Connection Profile

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
| Auth Token | your-secret-token-here | 与 Step 1 中 `OMICSCLAW_REMOTE_AUTH_TOKEN` 一致（留空则不使用 token） |

4. 点击 **"Test Connection"** — App 会打通 SSH tunnel → 探测 `/connections/test` + `/env/doctor`
5. 看到绿色 ✓ 后点 **"Save"**

### Step 3 — 切换到 Remote 模式

1. 在 **Settings → Backend** 面板将模式切换为 **Remote**
2. 选择刚创建的 Connection Profile 为 **Active**
3. 顶栏状态指示器变为 🌐（globe 图标） + 绿色 = 连接正常

### Step 4 — 导入数据

#### 方式 A：远端路径注册（大文件推荐）

适用于已经在服务器上的 `.h5ad` / `.csv` 文件：

1. 将文件 `scp` / `rsync` 到远端 workspace 下任意目录
2. 在 App **Datasets** 面板点 **"Register Remote Path"**
3. 输入远端绝对路径（如 `/data/omicsclaw-workspace/pbmc3k.h5ad`）
4. 点 **"Register"** — 后端校验文件存在 + 计算 checksum

#### 方式 B：直接上传（< 1 GB 小文件）

1. 在 **Datasets** 面板点 **"Upload"**
2. 选择本地文件 → App 通过 HTTP multipart 上传到远端
3. 上传完成后显示 **synced** 状态

### Step 5 — 提交分析任务

1. 在聊天窗口描述分析需求，如 "对 pbmc3k.h5ad 运行 spatial-preprocessing"
2. 或在 **Jobs** 面板手动提交：选择 Skill + 选择 Dataset + 设定参数 → Submit
3. Job 进入 **queued → running → succeeded/failed** 生命周期
4. **实时日志**在 Jobs 面板以 SSE 流式显示（断线重连自动续传）
5. 可随时点 **Cancel** 取消运行中的任务（subprocess 会被 SIGTERM）

### Step 6 — 查看产物

1. Job 完成后进入 **Artifacts** 面板
2. 按 job 分组浏览：`report.md` / `figures/*.png` / `result.json` / processed `.h5ad`
3. 支持 Markdown / 图片预览、Range-aware 大文件下载

## 安全说明

| 层 | 机制 |
|---|---|
| 第一层 | SSH tunnel — 所有流量加密；远端 app-server 仅绑 `127.0.0.1` |
| 第二层 | Bearer token — `OMICSCLAW_REMOTE_AUTH_TOKEN` 环境变量；App 自动在每个请求附加 `Authorization: Bearer <token>` |
| 数据隔离 | 遗传数据不离开服务器 — App 只拉 artifact（图表/报告），原始 `.h5ad` 留在远端 |

> **绝不要**将远端 app-server 的端口暴露到公网。如需从外网访问，始终通过 SSH tunnel 或 VPN。

## Session Resume（断线恢复）

- **Tunnel 断开**：App 自动检测 → 显示断连提示 → 重连后自动续传 SSE 日志（Last-Event-ID cursor）
- **窗口关闭再打开**：进入 Jobs 面板 → 之前 running 的 job 仍显示 → SSE 重订阅
- **服务器重启**：app-server 启动时自动 reconcile 孤儿 running job → 标记为 failed 并保存诊断

## 故障排查

| 症状 | 检查 |
|---|---|
| Test Connection 失败 | `ssh -i <key> <user>@<host>` 能否登录？远端 app-server 是否在运行？ |
| 连接后显示 "unavailable" | 确认 Active Profile 的 port/workspace 与远端 app-server 参数一致 |
| Job 一直 queued | 查看远端 app-server 的 stdout 是否有错误日志 |
| Job failed + "executor_not_implemented" | 远端 OmicsClaw 版本过旧；`pip install -e .` 更新到最新 |
| Job failed + "server_restart_orphaned_job" | 正常——说明 app-server 重启前有未完成的 job，已安全标记为失败 |
| SSE 日志不显示 | 检查 tunnel 状态（顶栏图标）；确认远端 `/jobs/{id}/events` 可达 |
| Dataset 删除后重新出现 | 升级 Desktop App 到最新版本（修复了 DELETE 未代理到远端的 bug） |
| Env Doctor 显示 "not_supported" | 远端 OmicsClaw 版本不含 `/env/doctor` 端点；更新到最新 |

## 常用命令速查

```bash
# 远端：启动 app-server（前台，便于看日志）
OMICSCLAW_WORKSPACE=/data/ws OMICSCLAW_REMOTE_AUTH_TOKEN=xxx \
  python -m omicsclaw app-server --host 127.0.0.1 --port 8765

# 远端：检查健康
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/connections/test -X POST
curl http://127.0.0.1:8765/env/doctor

# 远端：列出 datasets
curl http://127.0.0.1:8765/datasets -H "Authorization: Bearer xxx"

# 远端：列出 jobs
curl http://127.0.0.1:8765/jobs -H "Authorization: Bearer xxx"
```
