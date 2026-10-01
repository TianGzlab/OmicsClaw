# Sandbox 沙箱系统

OmicsClaw 的 Sandbox 系统让模型发起的 `bash` 命令在一个 Docker（或 Docker 兼容运行时，如
Podman）容器内执行：默认**无网络**、丢弃全部 Linux capability、禁止提权、以宿主用户的
`uid:gid` 运行，workspace 以**相同路径**读写挂载。引擎与工具层对此一无所知——`bash`
工具只看到一个注入的 `BashEnvironment`，启用前后工具接口和 Observation 格式完全一致。

**只有 `bash` 进容器。** `read_file` / `write_file` / `edit_file` 仍在宿主上执行，由
`Workspace` 边界约束；web 工具、MCP stdio server、CLI 的 `!<cmd>` 也都在宿主上。

> ⚠️ 旧架构中 `omicsclaw/autonomous/` 与 `omicsclaw/skill/execution/` 下基于
> **bubblewrap** 的隔离属于已拆除的旧系统（owner，2026-09-18），两个包都已删除；
> 曾引用 `bwrap` 的 `omicsclaw/autoagent/` 也已删除。它们不是本层的
> 前身，也不应被复用。当前唯一的隔离实现是本文描述的 `omicsclaw/sandbox/`。

---

## 1. 为什么需要 Sandbox？

沙箱关闭时（默认），`bash` 以运行 agent 的用户身份直接在本机执行，唯一的边界是逐条
人工审批。对多组学场景，这有两个具体问题：

- **数据外流。** 这台机器上放着基因组数据和可读的 `.env`（API key）。`SAFETY_RULES`
  第 1 条是"遗传数据不离开本机"。威胁主要是数据被发出去，而不是宿主被写坏——所以
  本层的首要控制是 `--network none`。
- **审批疲劳。** 一个分析流程要跑几十条 `python skills/...`、`ls`、`head`，逐条确认会让
  人要么放弃要么无脑按 `y`。只有在隔离真实存在时，才值得把逐条审批关掉
  （`sandbox_auto_approve`）。

---

## 2. 快速启动

```bash
# 1. 确认 daemon 在运行，并预先拉好镜像（启动时绝不自动拉取）
docker info
docker pull <your-omics-image>

# 2. 在 .env 中启用（或用等价的 --sandbox 旗标）
OMICSCLAW_SANDBOX=docker
OMICSCLAW_SANDBOX_IMAGE=<your-omics-image>
# 可选：沙箱就绪且无网络时，bash 不再逐条询问
OMICSCLAW_SANDBOX_AUTO_APPROVE=true

# 3. 启动任一 surface
oc cli
# 或用旗标：oc cli --sandbox docker --sandbox-image <your-omics-image>
```

启动日志（`omicsclaw.entry.sandbox` / `omicsclaw.entry.assembly` logger）：

```
sandbox running: image=<your-omics-image> network=none container=3a2f9c1b7d0e
assembled: provider=... sandbox=running permission=default ...
bash runs without approval: sandbox has no network          # 仅当 auto_approve 生效
```

镜像需要包含 `bash`、`sleep`，以及 skill 脚本所需的 Python / R 环境——容器里没有网络，
`pip install` / `conda install` 会按设计失败。`OMICSCLAW_SANDBOX_BOOTSTRAP` 可以在容器
就绪后于 workspace 中跑一次初始化命令（同样无网络）。

---

## 3. 架构设计

### 3.1 整体结构

```
omicsclaw/sandbox/            标准库 only，不 import 任何 omicsclaw 包，不写日志，不读环境变量
├── __init__.py               公共导出
├── config.py                 SandboxConfig（冻结、自校验）、host_user、check_mount_path
├── runner.py                 CommandRunner Protocol、SubprocessRunner、SandboxError、CommandTimedOut
├── daemon.py                 ensure_daemon_ready（探测 → 可选拉起 → 有界轮询）、desktop_starter
├── container.py              ContainerState 五状态、run_arguments、Container 生命周期
├── environment.py            DockerEnvironment.run_bash → ExecResult
└── manager.py                SandboxManager、SandboxInfo、ReapReport、owner_is_dead

omicsclaw/entry/              唯一同时认识 sandbox 与 tools 的层
├── config.py                 SandboxMode + sandbox_* 字段 → AppConfig.sandbox_config()
├── sandbox.py                SandboxBinding、open_sandbox、unstarted_sandbox、sandbox_section、bash_policy
├── assembly.py               open_app 先开沙箱；BashTool(environment=…)；_apply_bash_policy；aclose 回收
└── subagent.py               子代理沿用父代理的 bash 与沙箱 prompt 段
```

依赖方向：`omicsclaw/tools/builtin/bash.py` **声明** `BashEnvironment` Protocol；
`omicsclaw/sandbox/environment.py` 的 `DockerEnvironment` **结构化满足**它，但不 import
`omicsclaw.tools`（连 `CommandOutcome` 都不借，`ExecResult` 的字段是其超集）；只有
`omicsclaw/entry/` 把两者接起来。`tests/sandbox/test_sandbox_is_a_leaf_layer.py` 用 AST
白名单 + 子进程行为探针守住这一点。

### 3.2 组件

| 组件 | 代码位置 | 职责 |
|---|---|---|
| `SandboxConfig` | `omicsclaw/sandbox/config.py` | 镜像、网络、资源、用户、挂载、bootstrap、超时；构造时校验 |
| `CommandRunner` / `SubprocessRunner` | `omicsclaw/sandbox/runner.py` | 所有容器 CLI 调用的唯一出口；可换 `podman`，可被测试替身替换 |
| `ensure_daemon_ready` | `omicsclaw/sandbox/daemon.py` | `<cli> info` 探测；macOS 上可拉起 Docker Desktop |
| `Container` | `omicsclaw/sandbox/container.py` | 一个容器的 `start` / `stop` 与交换目录 |
| `run_arguments` | `omicsclaw/sandbox/container.py` | 生成 `docker run` 参数（安全加固都在这里） |
| `DockerEnvironment` | `omicsclaw/sandbox/environment.py` | `run_bash(command, cwd, timeout)`：`docker exec` + PID 文件 + 日志文件 |
| `SandboxManager` | `omicsclaw/sandbox/manager.py` | 创建 / 重试 / 销毁 / 列表 / 孤儿回收 / 变更通知 |
| `SandboxBinding` | `omicsclaw/entry/sandbox.py` | 一次部署得到的结果：off / running / degraded |
| `open_sandbox` | `omicsclaw/entry/sandbox.py` | 回收孤儿 → 创建（带重试）→ 降级或拒绝 |
| `sandbox_section` | `omicsclaw/entry/sandbox.py` | 系统提示中的 "## Execution sandbox" 段 |
| `bash_policy` / `_apply_bash_policy` | `omicsclaw/entry/sandbox.py`、`omicsclaw/entry/assembly.py` | 满足三重条件时把 `bash` 放宽为 `AUTO` |

### 3.3 工具路由

```
LLM ToolCall "bash"
  → GatedTool → HookedTool → BashTool.execute(arguments)
      ├── require_approval(...)            reason 写明 "in this session's injected execution environment"
      ├── self._environment is None
      │     → _locally(): bash -c <cmd> 在宿主上       [沙箱 off 或 degraded]
      └── self._environment is DockerEnvironment
            → _in_environment(): asyncio.timeout(t) 包住
                DockerEnvironment.run_bash(cmd, cwd=<workspace>, timeout=t)
                  → docker exec --workdir <workspace> <cid> bash -c WRAPPER <pid> <cmd> <log>
                                                     [沙箱 running]

read_file / write_file / edit_file → Workspace.resolve() → 宿主文件系统
                                     （workspace 同路径 bind mount，与容器内视图是同一批字节）
```

### 3.4 启动与接线

```
oc cli / oc channel / oc desktop
  → launch: resolve_app_config(argv, env) → AppConfig
  → open_app(config, on_sandbox_change=…)
       │
       ├─ load_mcp_config(...)
       ├─ open_sandbox(config)                          ← 先于 MCP
       │     sandbox_config = config.sandbox_config()   off → SandboxBinding()（直接返回）
       │                                                非法设置 → SandboxConfigError（启动失败）
       │     manager = SandboxManager(sandbox_config, on_change=…)
       │     manager.reap_orphans()                     失败只记 warning
       │     manager.create_with_retry(config.workspace)
       │        ├─ ensure_daemon_ready(...)
       │        ├─ create()  → Container.start() → DockerEnvironment → bootstrap（若配置）
       │        └─ 失败再 create() 一次
       │     成功 → SandboxBinding(mode, environment, manager, config)
       │     失败 → manager.aclose()；
       │            sandbox_required ? raise SandboxError : _degraded(...)（warning + 降级绑定）
       │
       ├─ build_app(config, sandbox=binding)
       │     foundation_tools(..., bash_environment=binding.environment)
       │     hook_tools → gate_tools → build_registry
       │     _apply_bash_policy(registry, mounted, binding, config)   仅当调用方未自带 tools
       │     default_sections(..., sandbox=binding)  → "## Execution sandbox"
       │     ChildRunner(..., sandbox=binding)       子代理拿到同一段环境描述
       │
       └─ 之后任何一步抛异常 → sandbox.aclose()

AgentApp.aclose()
  sessions.shutdown(grace) → mcp.aclose() → sandbox.aclose() → memory.close() → telemetry.aclose()
```

`build_app` 是同步的，**从不启动沙箱**：没有传入绑定时它用 `unstarted_sandbox(config)`，
对请求了沙箱的配置报告 degraded（原因
`this deployment was built without starting it (use open_app)`），`sandbox_required`
时直接抛 `SandboxError`。所有三个 surface 都走 `open_app`。

进程收到 `SIGTERM` / `SIGINT` 时，`omicsclaw/launch/_surfaces.py` 的 `_stop_signals`
与 `_release` 保证 `AgentApp.aclose()` 跑完（`_release` 可吸收一次额外的 Ctrl-C），
避免遗留容器。

---

## 4. Container 生命周期

```
         Container(...)
              ↓
          [PENDING]      ← _check_mounts → _make_io_dir → docker run --detach
              ↓            轮询 docker inspect "{{.State.Status}} {{.State.ExitCode}}"（每 0.2 s）
              ↓ status == running
          [RUNNING]      ← 接受 run_bash
              ↓ stop()
         [STOPPING]      ← docker stop --time ceil(stop_grace_s)
              ↓            无论成败都 docker rm --force；删除交换目录
        [TERMINATED]

  PENDING 中任何失败 → [FAILED]
     挂载源缺失 / 与 workspace 相同、workspace 不是目录、镜像不存在、
     容器启动后立即退出、start_timeout_s 超时、start 被取消
     → docker rm --force（按 id，拿不到 id 时按名字）+ 删除交换目录 → raise SandboxError
```

- 失败的启动**不留任何东西**；`SandboxManager.create` 的 `finally` 也会再 `stop()` 一次。
- 缺镜像时错误信息会追加 `run \`docker pull <image>\` first`：镜像从不自动拉取。
- `stop()` 幂等；停止失败记录在 `Container.error`，不抛出。
- 容器名 `omicsclaw-sandbox-<16 位 hex>`，标签 `omicsclaw.sandbox=1` 与
  `omicsclaw.sandbox.owner=<hostname>:<pid>`。

---

## 5. 命令执行：`DockerEnvironment.run_bash`

```
run_bash(command, cwd, timeout)
  │
  ├─ 在交换目录 <workspace>/.omicsclaw/sandbox/<sandbox_id>-XXXX/ 中
  │  以 O_EXCL、0600 创建 <token>.pid 与 <token>.log
  │     失败 → SandboxError("the sandbox is not available (was it stopped?)")
  │
  ├─ docker exec --workdir <cwd> <container_id> bash -c WRAPPER <pid_file> <command> <log_file>
  │     WRAPPER = 'echo "$$" > "$0" && exec bash -c "$1" > "$2" 2>&1 < /dev/null'
  │     ─ 先记下自己的 PID，再 exec 成为命令本身 → 记录的就是命令的 PID
  │     ─ 输出写文件而不是 exec 的 stdio → 后台进程挂不住 docker exec
  │     ─ 命令作为独立 argv 传入，无需转义
  │
  ├─ 自身截止 = timeout + OWN_DEADLINE_GRACE_S(5 s)
  │     到期 → _kill(pid_file) → ExecResult(output=log, exit_code=137, timed_out=True)
  │
  ├─ 被取消 → _shielded(_abandon)：在容器内 kill -KILL <pid>，删文件，然后重新抛出
  │
  ├─ pid 文件为空且 exec 失败 → SandboxError("the sandbox could not start the command")
  │     （容器已停、daemon 断连、镜像没有 bash）
  │
  └─ 否则 → ExecResult(output=log, exit_code=exec 的返回码)；删除两个文件
```

几点关键语义：

- **超时 / 取消会杀掉容器内的进程。** 杀掉宿主上的 `docker exec` 客户端并不会停止它在
  容器里启动的进程；`_kill` 等待至多 `PID_WAIT_S`（2 s）读到 PID，再用
  `docker exec <cid> bash -c 'kill -KILL "$0"' <pid>` 杀掉（`KILL` 常量，bash 内建，
  镜像里不需要 `kill` 二进制）。与本地路径一致，只杀直接子进程。
- **`bash` 工具的截止先到。** 从 `bash` 调用时，工具用 `asyncio.timeout(timeout)`
  包住 `run_bash`，比 `run_bash` 自己的截止早 5 s；于是内层走"被取消"分支杀进程，
  模型读到的是 `[TIMEOUT …]` 横幅（此时没有部分输出）。`run_bash` 自己的截止只服务于
  bootstrap 这类没有外层截止的调用方。
- **"命令失败"与"容器不在"可区分。** 前者是带退出码的 `ExecResult`；后者是
  `SandboxError`（`OSError` 子类），`bash` 工具把它包成
  `RuntimeError("the execution environment could not run the command: …")`，registry
  标记 `is_error=True`。
- **交换目录在 workspace 内**（`EXCHANGE_DIR = .omicsclaw/sandbox`），因此不需要单独的
  挂载；目录由 `tempfile.mkdtemp` 创建（0700），`stop()` 时删除。

---

## 6. 安全加固

`run_arguments` 为每个容器生成的参数（`SandboxConfig(image="img:1", user="1000:1000")`，
workspace 为 `/ws` 时的实际输出）：

```
run --detach --init --pull=never --name omicsclaw-sandbox-<id>
    --label omicsclaw.sandbox=1 --label omicsclaw.sandbox.owner=<host>:<pid>
    --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 4096
    --network none --tmpfs /tmp:rw,nosuid,nodev,size=1g --env HOME=/tmp
    --user 1000:1000 --volume /ws:/ws --workdir /ws img:1 sleep infinity
```

| 参数 | 默认值 | 作用 |
|---|---|---|
| `--network` | `none` | 只有 loopback，命令无法访问任何网络——**首要控制** |
| `--cap-drop ALL` | — | 丢弃全部 capability，**不加回**任何一个 |
| `--security-opt no-new-privileges:true` | — | 禁止 setuid 提权 |
| `--user` | 宿主 `uid:gid`（`host_user()`） | 写进 workspace 的文件归用户所有，而不是 root |
| `--pids-limit` | `4096` | 防 fork bomb；线程也计入，BLAS / numba 在多核机器上会开上百线程 |
| `--init` | — | PID 1 收割被杀命令留下的孤儿，避免僵尸占用 pids 配额 |
| `--pull=never` | — | GB 级组学镜像在启动超时内拉不完；缺镜像立即报错 |
| `--tmpfs /tmp` | `rw,nosuid,nodev,size=1g`（**无** `noexec`） | R `sourceCpp` 等需要在临时目录编译并加载 |
| `--env HOME=/tmp` | — | 以任意 uid 运行时仍有可写的 HOME |
| `--volume <ws>:<ws>` | 读写 | workspace 同路径挂载，路径在宿主与容器中一致 |
| `--volume <m>:<m>:ro` | 由 `sandbox_mounts` 指定 | 额外只读数据（参考基因组、注释库等） |
| `--memory` / `--cpus` / `--gpus` | 空 = 不传 | 需要时显式配置；一次 `sc.pp.neighbors()` 就可能超过 512m |

`SandboxConfig.__post_init__` 的校验：`image`、`network`、`user`、资源值不能为空、不能以
`-` 开头（否则会被 CLI 当成选项）、不能含空白；挂载路径必须是绝对路径且不含 `:`；
`pids_limit >= 1`，超时为正。`Container._check_mounts` 在启动前再检查挂载源存在（否则
Docker 会在宿主上创建一个空的、root 所有的目录）且不等于 workspace。

---

## 7. 审批与权限的关系

`bash` 的声明策略是 `ApprovalMode.ASK`。`sandbox_auto_approve=true` 时，
`_apply_bash_policy` 调用 `bash_policy(binding, current, auto_approve=True)`，只有**同时**
满足下列三条才把 `approval_mode` 改为 `AUTO` 并通过 `registry.replace` 重新注册：

1. 沙箱**正在运行**（`SandboxBinding.active`，不是 degraded）；
2. 网络是 `none`（`SandboxConfig.isolates_network`）；
3. `bash` 是装配层自己构造的那一个（调用方通过 `build_app(tools=…)` 自带工具时不调用
   `_apply_bash_policy`）。

任一条件不满足：记录 `sandbox_auto_approve ignored: …; bash still asks`，策略不变。
**降级只会收紧，不会放松。**

放宽的只是权限闸门决策链的最后一步（工具自身的 `approval_mode`）。`PermissionGate.resolve`
的前几步仍然生效：

| 情况 | 沙箱 running + `sandbox_auto_approve` 时 |
|---|---|
| 普通命令（`python skills/...`、`ls`） | 直接执行，不询问 |
| 命中 `DangerPatterns`（如 `rm -rf`、`sudo`） | 仍然询问（闸门亲自提问） |
| 改动 `.omicsclaw/`、规则文件、`.env` | 仍然询问 |
| 规则文件中的 `deny` / `ask` | 照常生效 |
| `--permission-mode read-only` | `bash` 被拒绝 |
| `--permission-mode bypass-all` | 与沙箱无关，全部放行 |

`_apply_bash_policy` 会把包装链（`GatedTool` → `HookedTool` → `BashTool`）逐层解开来识别
`bash`（`_is_bash`），但重新注册的是**外层的 `GatedTool`**，所以放宽后 `bash` 依旧经过规则
文件与危险模式检查。`tests/entry/test_hook_wiring.py` 钉住双层包装的情况。

与 CLI 的 `/auto`（`PermissionMode.AUTO_APPROVE`）的区别：`/auto` 对所有普通工具调用生效，
不论 `bash` 在哪里运行；它的提示文字会读取实时绑定（`Repl._sandbox_state`）告诉用户
"bash runs in the sandbox container." / "a sandbox was requested but is not in use …" /
"bash runs directly on this machine; OMICSCLAW_SANDBOX=docker puts it in a container."。

---

## 8. 降级与 fail-closed

| 情况 | 结果 |
|---|---|
| `sandbox=off`（默认） | `SandboxBinding()`；系统提示无沙箱段；`bash` 在宿主执行 |
| 配置非法（如 `docker` 模式缺 `sandbox_image`） | `SandboxConfigError`，**启动失败**（不降级） |
| daemon 不可用 / 镜像缺失 / 两次创建都失败，且 `sandbox_required=false` | **降级**：warning 日志 `sandbox unavailable, bash runs on this machine without isolation: …`；`bash` 在宿主执行；`bash` 仍需审批 |
| 同上，且 `sandbox_required=true` | `SandboxError("sandbox_required is set and the sandbox is unavailable: …")`，**拒绝启动** |
| bootstrap 失败或超时 | 记录在 `SandboxInfo.bootstrap`，warning 日志，**继续**（fail-open） |

降级时系统提示中的 "## Execution sandbox" 段（`_degraded_text`，原因截到 300 字符）：

```
- A container sandbox was requested but is not running: <reason>
- `bash` therefore runs directly on this machine, as the user running this agent,
  with no isolation. Ask the user before anything destructive or irreversible.
```

运行时（`_running_text`）则告诉模型：`bash` 在容器（镜像名）中执行；工作目录是同路径挂载的
workspace，文件工具与 web 工具在宿主运行；网络为 `none` 时下载、安装包、远程 API 都会按设计
失败，应使用镜像中已有的软件；只读挂载列表；workspace 之外写入的内容在会话结束时丢失。

---

## 9. 并发与子代理

- **每个进程一个 `SandboxManager`，每次部署一个 `main` 容器。** 同一进程内所有会话
  （CLI 的多个对话、channel 的多个聊天）共享这一个容器与同一个 workspace。
- **子代理共用父代理的容器。** `task` 工具委派的子代理拿到的是父 registry 的收窄副本，
  其中的 `bash` 就是父代理那个（同一个 `DockerEnvironment`）；`ChildRunner._child_prompt`
  把同一段沙箱描述（`_environment_text`）写进子代理提示，避免子代理在降级时误以为自己在
  容器里而往用户机器上装包。
- **多沙箱的接缝已在。** `SandboxManager.create(workspace, label="sub-1")` 可以为另一个
  agent 起独立容器（`tests/sandbox/test_manager.py::test_each_agent_gets_its_own_sandbox_under_its_own_label`），
  但目前没有调用方。
- **多进程并存安全。** 孤儿回收只动属主进程已死的容器（见下节），不会删除旁边另一个
  OmicsClaw 进程正在使用的容器。
- `SandboxManager` 只在单个事件循环内使用，**非线程安全**；`Container.start` 不支持并发调用。

---

## 10. 孤儿容器回收

`open_sandbox` 在创建之前调用一次 `SandboxManager.reap_orphans()`：

```
docker ps --all --quiet --filter label=omicsclaw.sandbox=1
  对每个容器：
    docker inspect --format '{{index .Config.Labels "omicsclaw.sandbox.owner"}}'
    owner_is_dead("<hostname>:<pid>") ?
       是 → docker rm --force <id>        → ReapReport.removed / failed
       否 → 保留                           → ReapReport.kept += 1
```

`owner_is_dead` 只有在**能证明**属主已死时才返回 `True`：hostname 等于本机、PID 是数字、
不是本进程、`os.kill(pid, 0)` 抛 `ProcessLookupError`。其他宿主、存活或无权探测的 PID
（含 PID 被复用）、标签缺失或格式错误、Windows——一律保留。**宁可泄漏，不可误杀。**
列表失败只记 warning，不阻止启动。

---

## 11. Daemon 就绪检查

`ensure_daemon_ready(runner, start_daemon=…)`：

1. 先探测一次 `<cli> info --format {{.ServerVersion}}`（单次探测 10 s 超时）；成功即返回。
2. 失败则调用 `start_daemon`：macOS 上且 runtime 为 `docker` 时是 `desktop_starter`
   （`open -a Docker`）；Linux 上不尝试（daemon 由 init 系统管理，需要 root）。
3. 每 `PROBE_INTERVAL_S`（0.5 s）重试，直到 `START_TIMEOUT_S`（90 s，已尝试拉起）或
   `RESTART_GRACE_S`（2 s，未拉起，覆盖 daemon 正在重启的情况）。
4. CLI 本身不存在时立即抛 `SandboxError("cannot run 'docker': … Is the container runtime installed and on PATH?")`。

---

## 12. 可观察性

- 本包**不写日志**，只通过返回值、`SandboxInfo` 快照、`ReapReport`、异常和
  `ChangeListener` 回调汇报；所有日志在 `omicsclaw/entry/sandbox.py` 与
  `omicsclaw/entry/assembly.py`。
- `SandboxManager.list_all()` → `tuple[SandboxInfo, ...]`（`id`、`label`、`state`、
  `image`、`workspace`、`docker_id` 前 12 位、`error`、`bootstrap`）。
- `open_app(on_sandbox_change=…)` 在每次状态变化时收到最新快照（PENDING → RUNNING → 移除）；
  回调抛出的异常被吞掉。
- `AgentApp.sandbox` 保存 `SandboxBinding`，surface 可读取 `active` / `degraded` /
  `unavailable`。

---

## 13. 配置参数

所有配置在 `omicsclaw/entry/config.py` 统一解析（`resolve_app_config`，优先级：环境变量 <
命令行 < 关键字覆盖）；`.env` 由 `omicsclaw.launch` 在此之前加载，不覆盖已导出的变量。
非法值抛 `AppConfigError`，不静默回落。

| `AppConfig` 字段 | 旗标 | 环境变量 | 默认 | 说明 |
|---|---|---|---|---|
| `sandbox` | `--sandbox` | `OMICSCLAW_SANDBOX` | `off` | `off` 或 `docker`（`SandboxMode`） |
| `sandbox_image` | `--sandbox-image` | `OMICSCLAW_SANDBOX_IMAGE` | 无 | `docker` 模式必填，须已本地存在 |
| `sandbox_network` | `--sandbox-network` | `OMICSCLAW_SANDBOX_NETWORK` | `none` | 其他值原样传给 `--network` |
| `sandbox_memory` | `--sandbox-memory` | `OMICSCLAW_SANDBOX_MEMORY` | 空 = 不限 | 如 `32g` |
| `sandbox_cpus` | `--sandbox-cpus` | `OMICSCLAW_SANDBOX_CPUS` | 空 = 不限 | 如 `8` |
| `sandbox_gpus` | `--sandbox-gpus` | `OMICSCLAW_SANDBOX_GPUS` | 空 = 无 GPU | 如 `all`；需 NVIDIA container toolkit |
| `sandbox_user` | `--sandbox-user` | `OMICSCLAW_SANDBOX_USER` | 空 = 宿主 `uid:gid` | rootless Docker / Podman 通常要 `0:0` |
| `sandbox_mounts` | `--sandbox-mount`（可重复） | `OMICSCLAW_SANDBOX_MOUNTS`（`os.pathsep` 分隔） | 无 | 额外只读、同路径挂载 |
| `sandbox_bootstrap` | `--sandbox-bootstrap` | `OMICSCLAW_SANDBOX_BOOTSTRAP` | 空 | 容器就绪后在 workspace 执行一次 |
| `sandbox_bootstrap_timeout_s` | `--sandbox-bootstrap-timeout` | `OMICSCLAW_SANDBOX_BOOTSTRAP_TIMEOUT_S` | `600.0` | 与工具超时无关 |
| `sandbox_runtime` | `--sandbox-runtime` | `OMICSCLAW_SANDBOX_RUNTIME` | `docker` | `PATH` 上的名字或路径；`podman` 兼容 |
| `sandbox_required` | `--sandbox-required` | `OMICSCLAW_SANDBOX_REQUIRED` | `false` | `true` = 起不来就拒绝启动 |
| `sandbox_auto_approve` | `--sandbox-auto-approve` | `OMICSCLAW_SANDBOX_AUTO_APPROVE` | `false` | 见第 7 节 |

`SandboxConfig` 中不经 `AppConfig` 暴露、只能用默认值的字段：

| 字段 | 默认 |
|---|---|
| `pids_limit` | `4096` |
| `tmpfs_size` | `1g` |
| `start_timeout_s` | `60.0`（`docker run` + 就绪等待） |
| `stop_grace_s` | `5.0`（SIGTERM 到 SIGKILL） |

`bash` 在容器内的超时仍由 `OMICSCLAW_TOOL_TIMEOUT_S` 派生（默认 585 s），见
[shell-execution.md](shell-execution.md#44-超时)。

使用 Podman：`OMICSCLAW_SANDBOX=docker OMICSCLAW_SANDBOX_RUNTIME=podman`（模式名仍是
`docker`，运行时由 `sandbox_runtime` 选择）。

---

## 13.1 步骤执行器在容器里

分析模块的步骤由 `skills/_sdk/notebook/run.py` 执行（计划 0070），它在一次性的 IPython kernel 里逐 cell 运行步骤，kernel 用的就是调用执行器的那个解释器。所以沙箱镜像里要装 `nbclient` 和 `ipykernel`；缺了的话，执行器在启动 kernel 之前就报错 "the step runner needs nbclient and ipykernel in <interpreter>"，并以退出码 2 结束。镜像把代码打进去（`sandbox_code_in_image`）时，宿主机上的执行器路径在容器里不一定存在，Environment 段因此写成 `python -m skills._sdk.notebook`。

执行器的状态（记账、manifest、锁）都写在 `results/<NN_slug>/provenance/` 下，它在读写挂载的工作区里，宿主机看得到；`.omicsclaw/` 在容器里被 1 MB 的 tmpfs 盖住，执行器不读也不写它。模块锁用 `fcntl.flock`，容器与宿主机共用内核和 inode，两边互斥；网络文件系统和 Docker Desktop 的 macOS 文件共享不保证这一点。容器里取不到 `.git`，记账里 skill 的 `git` 字段记为 `null`，只保留内容哈希。

步骤里的 `load_demo` 按 `$OMICSCLAW_DEMO_DIR`、仓库的 `data/` 与 `examples/`、`$XDG_CACHE_HOME/omicsclaw/demo/` 的顺序找 demo 数据，都找不到时才用 scanpy 下载。沙箱默认没有网络，仓库的 `data/` 也不挂进容器，所以要事先把 `pbmc3k_raw.h5ad` 等文件放进一个目录，用 `sandbox_mounts` 挂进去，再让 `OMICSCLAW_DEMO_DIR` 指向挂载点：`docker exec` 不传宿主机的环境变量，这个变量要在镜像里设好，或者写在执行器命令的前面（`OMICSCLAW_DEMO_DIR=<挂载点> python -m skills._sdk.notebook run ...`）。找不到时报错信息会列出这几个位置。

## 14. 已知限制

- **从未在真实 Docker daemon 上运行过。** 开发机没有 Docker；加固参数组合、
  `--network none`、容器内 kill、宿主 uid 写 workspace 只由
  `tests/sandbox/test_docker_integration.py`（2 个测试）覆盖，在无 daemon 时 skip
  （FRAMEWORK-REBUILD.md Step 6.7 "Open"）。
- **`--gpus` 与 `--cap-drop ALL` 的组合未验证**；Podman 兼容只按 CLI 参数核对过。
- **没有 apptainer / singularity 支持**（HPC 常见，CLI 语义差异大，plan 0036 非目标）。
- **只有 `bash` 被隔离。** MCP stdio server、`web_fetch` / `web_search`、文件工具、CLI 的
  `!<cmd>` 都在宿主执行；文件工具受 `Workspace` 边界约束，而 `!` 不受任何约束。
- **容器可写整个 workspace**，包括 `.omicsclaw/`（规则文件、记忆库、offload 结果）；
  这部分只由权限闸门的"受保护路径"检查拦截命令文本，不是 OS 级隔离。
- **子代理不隔离**：共用父代理容器，没有 per-sub-agent 沙箱。
- **沙箱路径超时没有部分输出**：`bash` 的截止先到时只返回横幅。
- **没有 `/sandbox` 状态命令**，也没有 SandboxBar；状态只能从启动日志、`/auto` 的提示文字
  或 `AgentApp.sandbox` 读到。
- **同一进程的所有会话共享一个容器**，彼此的后台进程和 `/tmp` 可见。
- **`.env.example` 的注释与代码不一致**：它写着 `# off | docker | podman`，但
  `SandboxMode` 只有 `off` 和 `docker`，`OMICSCLAW_SANDBOX=podman` 会抛
  `AppConfigError: ... is not a sandbox mode (off, docker)`；Podman 应通过
  `OMICSCLAW_SANDBOX_RUNTIME=podman` 选择。
- **FRAMEWORK-REBUILD.md Step 6.7 的示例命令写的是 `oc interactive`**，当前 surface 是
  `oc cli`。
- **镜像内容由运维负责**：没有默认的组学镜像，镜像中缺少 skill 所需的依赖时脚本会在容器内
  失败，且无网络无法现场安装。

---

## 15. 测试

本机没有 Docker，测试用三种替身：

| 层次 | 位置 | 做法 |
|---|---|---|
| 纯逻辑 | `tests/sandbox/test_container.py`、`test_manager.py`、`test_daemon.py`、`test_runner.py`、`test_config.py` | 进程内脚本化 `CommandRunner`：状态机、重试、孤儿回收、daemon 轮询，可注入任意失败 |
| 真实进程 | `tests/sandbox/fake_docker.py` + `test_environment.py`、`tests/entry/test_sandbox.py` | 假 `docker` 可执行文件，`exec` 子命令**真的**执行 `bash -c`，包装脚本、PID 文件、容器内 kill 全走真实进程；经 `sandbox_runtime` 注入，打通 `open_app` → ReAct 循环 → `bash` |
| 真实 Docker | `tests/sandbox/test_docker_integration.py` | `docker info` 成功时才跑，否则 skip |
| 分层守卫 | `tests/sandbox/test_sandbox_is_a_leaf_layer.py` | AST 白名单 + 子进程行为探针，断言不 import 其他 `omicsclaw` 包 |

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest tests/sandbox/ tests/entry/test_sandbox.py \
    -p no:cacheprovider -q -o addopts=""
```

---

## 16. 参考

- plan 0036 `docs/plans/0036-sandbox-layer.md`：能力清单与处置、默认值重新标定、
  Q1–Q7 关键决策、两轮独立审计结果。
- `docs/FRAMEWORK-REBUILD.md` Step 6.7。
- plan 0029 Q11（`BashEnvironment` 接缝）与附录 B.5（"能否关掉审批"作为验收判据）。
- plan 0038（权限闸门）。

---

## 17. 文件索引

| 内容 | 文件 | 符号 |
|---|---|---|
| 公共导出 | `omicsclaw/sandbox/__init__.py` | — |
| 配置 | `omicsclaw/sandbox/config.py` | `SandboxConfig`、`SandboxConfigError`、`NETWORK_NONE`、`host_user`、`check_mount_path` |
| CLI 调用 | `omicsclaw/sandbox/runner.py` | `CommandRunner`、`SubprocessRunner`、`Completed`、`SandboxError`、`CommandTimedOut` |
| daemon | `omicsclaw/sandbox/daemon.py` | `ensure_daemon_ready`、`desktop_starter`、`PROBE_INTERVAL_S`、`RESTART_GRACE_S`、`START_TIMEOUT_S` |
| 容器 | `omicsclaw/sandbox/container.py` | `Container`、`ContainerState`、`run_arguments`、`owner_token`、`LABEL`、`OWNER_LABEL`、`NAME_PREFIX`、`EXCHANGE_DIR` |
| 执行 | `omicsclaw/sandbox/environment.py` | `DockerEnvironment`、`ExecResult`、`WRAPPER`、`KILL`、`OWN_DEADLINE_GRACE_S`、`TIMED_OUT_EXIT` |
| 管理 | `omicsclaw/sandbox/manager.py` | `SandboxManager`、`SandboxInfo`、`ReapReport`、`BootstrapOutcome`、`ChangeListener`、`owner_is_dead` |
| 部署绑定 | `omicsclaw/entry/sandbox.py` | `SandboxBinding`、`open_sandbox`、`unstarted_sandbox`、`sandbox_section`、`bash_policy` |
| 配置解析 | `omicsclaw/entry/config.py` | `SandboxMode`、`AppConfig.sandbox_*`、`AppConfig.sandbox_config`、`_OPTIONS` |
| 装配 | `omicsclaw/entry/assembly.py` | `open_app`、`build_app`、`foundation_tools`、`_apply_bash_policy`、`_is_bash`、`AgentApp.aclose` |
| 子代理 | `omicsclaw/entry/subagent.py` | `ChildRunner._child_prompt`、`_environment_text` |
| 注入接缝 | `omicsclaw/tools/builtin/bash.py` | `BashEnvironment`、`CommandOutcome`、`_in_environment` |
| CLI 状态文字 | `omicsclaw/entry/cli/_repl.py` | `Repl._sandbox_state`、`Repl._auto_on_notice` |
| 关闭保障 | `omicsclaw/launch/_surfaces.py` | `_release`、`_stop_signals` |
| 示例配置 | `.env.example` | 第 7 节 "Sandbox" |
| 测试 | `tests/sandbox/`、`tests/entry/test_sandbox.py` | — |
