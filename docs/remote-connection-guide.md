# OmicsClaw-App 远程连接配置指南

本文档说明如何在 OmicsClaw-App 中把**数据处理/作业执行**放在远端 Linux 服务器上，App 本身留在本地负责 UI、聊天、结果浏览。

> 对齐版本：OmicsClaw-App **v0.1.3+**（引入 `Runtimes` 页面与 Bundled 运行时）。

## 架构概览

OmicsClaw-App 通过一个统一的 **Runtimes** 抽象来管理"Python 到底跑在哪"，目前有四种 `RuntimeKind`：

| Runtime Kind | 说明 | 传输方式 | 典型场景 |
|---|---|---|---|
| `bundled` | App 自带的便携 Python（PBS）+ `omicsclaw[desktop]`，零配置 | IPC / 本地 HTTP | 开箱即用的桌面体验（Linux x64/arm64、macOS arm64、Windows x64） |
| `local-python` | 指向用户本机的 Python 解释器（由 `launcher_python_path` 决定） | 本地 HTTP | 已有 conda / venv 想复用 |
| `remote-ssh` | `connection_profiles` 记录 + 非空 `ssh_host`，由 Electron 隧道管理器把 `127.0.0.1:<动态端口>` 前向到 `<ssh_host>:<remote_port>` | HTTP over SSH tunnel | **本文档主要场景** |
| `remote-url` | `connection_profiles` 记录 + 空 `ssh_host` + 直接 URL（或旧版 `remote_backend_url` fallback） | HTTP 直连 | 已有自己的 `ssh -L` / VPN / 直达公网 URL |

同一时刻只有**一个** runtime 是激活的；切换通过 Runtimes 页面的 **Make Active** 完成。

```
┌────────── OmicsClaw-App (control plane) ────────┐
│  Next.js UI · Electron                          │
│  Runtimes 页面（增/删/改/激活 4 类 runtime）     │
│  TunnelManager → 127.0.0.1:<dynamic-local>      │
└──────────────────┬──────────────────────────────┘
                   │  HTTPS/SSE over SSH tunnel
┌──────────────────▼──────────────────────────────┐
│  远程 Linux 服务器 (execution plane)              │
│  oc app-server ── 127.0.0.1:8765                │
│  Control plane + notebook + optional KG routes  │
│  Jobs 以本地 OmicsClaw subprocess 运行            │
│  Datasets / Jobs / Artifacts on workspace disk  │
└─────────────────────────────────────────────────┘
```

## 前置条件

### 远端服务器

| 要求 | 说明 |
|---|---|
| OS | Linux（Ubuntu 20.04+、CentOS 7+、或同等） |
| Python | 3.10+，推荐 conda/venv 隔离 |
| OmicsClaw | 已完成 `git clone`，并安装 `pip install -e ".[desktop]"` |
| SSH | sshd 允许公钥认证 |
| 对外端口 | 无需 — 所有通信走 SSH tunnel |
| 磁盘 | Workspace 目录至少 20 GB 可用 |
| GPU（可选）| CUDA + PyTorch，用于 GPU 加速的 skill（scVI、Cell2Location 等）|

### 本地（App 端）

| 要求 | 说明 |
|---|---|
| OmicsClaw-App | v0.1.3+（含 Runtimes 页面） |
| SSH 密钥 | `~/.ssh/id_ed25519` 或 `~/.ssh/id_rsa`（未加密或已加入 ssh-agent） |
| ssh-agent | 推荐运行（`eval $(ssh-agent) && ssh-add`） |

> App 端**不**负责生成/导入 SSH 密钥、也不提示 passphrase — 必须是用户事先准备好并可用的私钥。

## 配置步骤

### Step 1 — 在远端启动 `oc app-server`

SSH 登录到远端服务器后执行：

```bash
# 激活 Python 环境
source .venv/bin/activate        # 或 conda activate omicsclaw

# Workspace：所有 dataset 登记、job 产物、artifact 的根目录
export OMICSCLAW_WORKSPACE=/data/omicsclaw-workspace
mkdir -p "$OMICSCLAW_WORKSPACE"

# 推荐：设置 Bearer token 作为 SSH 之外的第二层鉴权
export OMICSCLAW_REMOTE_AUTH_TOKEN="your-secret-token-here"

# 启动 app-server（仅绑 127.0.0.1，切勿暴露公网）
oc app-server --host 127.0.0.1 --port 8765
```

自检：

```bash
curl http://127.0.0.1:8765/health
# => {"status":"ok","version":"..."}

curl -X POST http://127.0.0.1:8765/connections/test \
  -H "Authorization: Bearer $OMICSCLAW_REMOTE_AUTH_TOKEN"

curl http://127.0.0.1:8765/env/doctor \
  -H "Authorization: Bearer $OMICSCLAW_REMOTE_AUTH_TOKEN"
```

> `oc app-server` 是 OmicsClaw-App 所有后端能力的统一入口：remote control-plane、notebook 路由、可选的 KG 路由都挂在这个进程上，不需要再起额外 daemon。
>
> **后台运行**：`nohup oc app-server ... &`、`tmux`、`screen`、`systemd --user` 均可；断开 SSH 后服务继续。

### Step 2 — 在 Runtimes 页面新建 Remote Runtime

1. 打开 App，进入 **Runtimes** 页面（非 "Settings → Connections"，v0.1.3 起已合并）
2. 点击 **"New Runtime"** → 选择新建 connection profile
3. 填写字段（仅以下字段实际存库，**不再**有 "Remote Python" / "Remote Workspace" —— 前者是远端自身的环境，后者是远端 `OMICSCLAW_WORKSPACE` 的角色，不必在 App 中重复配置）：

| 字段 | 存库键 | 示例 | 说明 |
|---|---|---|---|
| Name | `name` | Lab GPU Server | UI 显示名 |
| URL | `url` | `http://127.0.0.1:8765` | **direct-URL 场景必填**；SSH 场景可留空（以隧道为唯一入口） |
| Auth Token | `auth_token` | your-secret-token-here | 与 Step 1 的 `OMICSCLAW_REMOTE_AUTH_TOKEN` 一致；存库后 GET 以 `***<后8位>` 遮罩返回 |
| SSH Host | `ssh_host` | 192.168.1.100 | **填了它** = SSH-tunneled；**留空** = direct-URL profile |
| SSH Port | `ssh_port` | 22 | 默认 22 |
| SSH User | `ssh_user` | zhouwg | 远端 Linux 用户名 |
| SSH Key Path | `ssh_key_path` | `~/.ssh/id_ed25519` | 本机私钥**绝对路径**（App 不管理密钥生命周期） |
| Remote Port | `remote_port` | 8765 | 远端 `oc app-server` 监听端口；默认 8765 |

4. 保存 → 回到 Runtimes 列表 → 选中该条 → 点 **"Run Ping"**
   - App 会先通过隧道 `GET /health`
   - `/health` 通过后**自动带 Bearer token** 再探一次 `/env/doctor`（Bearer 校验同步做掉，防止"表面 200、实际 API 全 401"的假绿灯）
5. 看到 `ok` 状态后点 **"Make Active"**

> **SSH 隧道是动态端口的**：TunnelManager 打开 SSH 后会随机绑定一个本地 TCP 端口（写入 `active_tunnel_local_port` setting），后续所有 `backendFetch` 都走 `127.0.0.1:<dynamic>`。你**不需要**也**不应该**手动指定本地端口。
>
> 编辑 profile 的 host / user / key / port 字段时，隧道会依据指纹重开，避免"改了配置但仍连旧 host"。

### Step 3 — 确认当前 Active Runtime

- Runtimes 列表中，激活项会显示绿色圆点 + "Active" 标记
- 顶栏状态指示器：
  - 🖥 Bundled / Local Python
  - 🌐 Remote SSH / Remote URL（绿色 = 隧道已开 + 最近健康探测 ok）

### Step 4 — 导入数据

#### 方式 A：远端路径登记（大文件推荐）

文件已在服务器上（`.h5ad` / `.csv` / …）：

1. 用 `scp` / `rsync` 放到 `$OMICSCLAW_WORKSPACE` 下任意目录
2. App **Datasets** 面板 → **"Register Remote Path"**
3. 输入远端绝对路径，例如 `/data/omicsclaw-workspace/pbmc3k.h5ad`
4. 点 **Register** — 后端校验存在并登记为远端 dataset（`storage_uri` 形如 `ssh://<profile_id>/path`）

#### 方式 B：直接上传（小文件）

1. **Datasets** → **"Upload"**
2. 选本地文件，App 通过 HTTP multipart 上传到远端 workspace
3. 完成后显示 **synced**

> multipart 上传只适合小文件；超过约 1 GiB 推荐 `scp` / `rsync` 后走方式 A。

### Step 5 — 提交分析任务并观察执行

1. 在聊天窗口发起分析请求，例如 "对 pbmc3k.h5ad 运行 spatial-preprocessing"
2. 或在 **Jobs** 面板手动提交：选择 Skill + Dataset + 参数 → Submit
3. Job 生命周期：`queued → running → succeeded / failed / canceled`
4. 后端在远端 workspace 建立持久化 job 目录，以本地 OmicsClaw subprocess 执行
5. **实时日志**在 Jobs 面板通过 SSE 流式显示；重连后从已有日志续发
6. 可随时 **Cancel**；已结束任务可 **Retry**

### Step 6 — 查看产物与上下文恢复

1. Job 完成后进入 **Artifacts** 面板
2. 按 job 分组浏览：`report.md` / `figures/*.png` / `result.json` / 处理后的 `.h5ad`
3. 支持 Markdown / 图片预览 + 大文件下载
4. 断线或 App 重启后，运行中的 job 与会话可从远端状态恢复

> 失败任务会保留 `stdout.log` 和诊断文件（如 `diagnostics/env_doctor.json`），便于复盘。

## Bundled vs Local vs Remote — 怎么选？

| 场景 | 推荐 Runtime |
|---|---|
| 只在本机偶尔试一下，不想装 Python | `bundled`（Linux x64/arm64、macOS arm64、Windows x64 自带；Intel Mac 和 Windows arm64 回退 BYO） |
| 已有 conda/venv 想复用科学计算栈 | `local-python`（Settings → Python environment 指定路径） |
| 数据/算力在实验室服务器 | `remote-ssh`（本文主场景） |
| 已有自己的 `ssh -L` / VPN / 直达公网 URL | `remote-url`（ssh_host 留空，只填 URL） |

> Bundled runtime 只自带 app-server + notebook 必需的最小依赖，不包含 scanpy/numpy/pandas 等科学栈。**首次用到时**在 notebook 里 `!pip install scanpy anndata` 即可，包会装进 bundled 的 site-packages 并持久保留。详见 `OmicsClaw-App/docs/bundled-backend.md`。

## 安全说明

| 层 | 机制 |
|---|---|
| 第一层 | SSH tunnel — 所有流量加密；远端 `oc app-server` 仅绑 `127.0.0.1` |
| 第二层 | Bearer token — 来自远端 `OMICSCLAW_REMOTE_AUTH_TOKEN`；App 在受保护路由（`/connections/test`、`/env/doctor`、`/datasets`、`/jobs/*`…）上附加 `Authorization: Bearer <token>` |
| Token 存储 | App 端 SQLite 明文存（与 `anthropic_auth_token` 处理方式一致），GET 路由以 `***<后8位>` 返回，PUT 识别遮罩值即跳过覆盖 |
| 数据隔离 | 遗传/原始数据不离开服务器，App 只拉 artifact（图表/报告） |

> **严禁**把远端 `oc app-server` 的端口暴露到公网。外网访问请始终走 SSH tunnel 或 VPN。

## Session Resume（断线恢复）

- **Tunnel 断开**：App 自动检测，恢复后重新订阅 job 事件、补齐日志；`active_tunnel_local_port` 按需重新发布
- **窗口关闭再打开**：Jobs / Chat 会从远端状态恢复仍在运行的任务
- **服务器重启**：`oc app-server` 会把失去执行上下文的 orphaned `running` job 标记为失败（`server_restart_orphaned_job`），保留诊断信息

## 故障排查

| 症状 | 检查 |
|---|---|
| "Run Ping" `/health` 失败 | 先确认 `ssh -i <key> <user>@<host>` 本机能登录；再确认远端 `oc app-server` 在跑，port/remote_port 一致 |
| `/health` 绿但 `/env/doctor` 红 | Bearer token 不匹配 — 核对远端 `OMICSCLAW_REMOTE_AUTH_TOKEN` 与 profile `auth_token`（注意 GET 返回的是 `***<后8位>` 遮罩） |
| 顶栏图标绿但实际请求 401 | 同上；v0.1.3 起 ping 会主动做这层校验，老 profile 建议改密码后重新 Save |
| 提示 workspace 未配置 / 目录不存在 | 远端 `OMICSCLAW_WORKSPACE` 未 export 或目录不存在 |
| 上传失败 / 文件过大 | 改走 **Register Remote Path**，先 `scp` / `rsync` 上去 |
| Job 很快失败 | 看 job 的 `stdout.log`；再看 `diagnostics/env_doctor.json` + `diagnostics/stdout.log` |
| Job failed + `server_restart_orphaned_job` | app-server 重启前有未完成任务；这是保护性失败，非数据损坏 |
| SSE 日志不显示 | 隧道是否存活、`active_tunnel_local_port` 是否仍有效、当前 Active Runtime 是否变过 |
| 编辑了 SSH 字段没生效 | 指纹变更会触发隧道重开；如未发生，检查 Runtimes 页面是否仍 Active，或手动 "Make Active" 一次 |

## 常用命令速查

```bash
# 远端：前台启动 app-server（便于看日志）
OMICSCLAW_WORKSPACE=/data/ws OMICSCLAW_REMOTE_AUTH_TOKEN=xxx \
  oc app-server --host 127.0.0.1 --port 8765

# 远端：环境体检（同 App 端 Run Ping 的第二阶段）
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
#   GET  /api/runtimes               列出所有 runtime（bundled/local/remote-ssh/remote-url）
#   GET  /api/runtimes/:id           单个 runtime 详情 + 最近健康快照
#   POST /api/runtimes/:id/ping      手动触发 /health + /env/doctor（含 Bearer 校验）
```

## 相关文档

- `OmicsClaw-App/docs/bundled-backend.md` — bundled runtime 的构建/目录契约与 BYO 回退规则
- `OmicsClaw-App/docs/LOCAL_SETUP_GUIDE.md` — 本地 / bundled / local-python 的首次配置
- `OmicsClaw-App/src/lib/runtimes/types.ts` — `RuntimeKind` / `RuntimeTransport` / 健康快照字段的权威定义
- `OmicsClaw-App/src/types/index.ts`（`ConnectionProfile`）— Profile 字段及语义
