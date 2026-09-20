# 0036 — Sandbox 层：`omicsclaw/sandbox/`

> 状态：已交付（2026-09-19），经两轮独立只读审计（正确性 / harness9 对照）与一轮修复。参照系：harness9 `internal/sandbox/`（1,793 行含测试）
> + `cmd/harness9/main.go:165-226` 的接线 + `internal/context/builder.go:150-176`
> 的 prompt 注入 + `internal/subagent/runner.go:92-100` 的子代理沙箱。
> 前置：plan 0029 §4 Q11 留下的 `Environment` 接缝，与附录 B 的四处重新标定。

## 1. 目标与非目标

**目标**：让重构后的 Agent 主循环里，模型发出的 `bash` 命令可以在一个 Docker
容器内执行，获得 OS 级隔离（独立进程空间、无网络、capability 全丢、资源配额），
且对引擎透明——`engine/` 一行不改，`tools/` 一行不改。

**验收判据**（附录 B.5）：隔离做到位之后，`bash` 可以**关掉逐条审批**。本步把它
落成一个显式开关 `sandbox_auto_approve`，并且只在「容器确实在跑 **且** 网络确实为
`none`」时生效；降级、网络放开、调用方自带工具三种情况一律保持 `ASK`。

**非目标**：

- 不做 TUI 的 SandboxBar——Surface 的事；本层提供 `SandboxInfo` 快照与
  `on_change` 回调两个接缝（与 MCP 层同构）。
- 不做子代理沙箱——重建里还没有子代理层；`SandboxManager` 支持多个沙箱并带
  `label`，子代理层落地时一次 `create(label="sub-1")` 即可。
- 不沙箱 MCP stdio server 与 web 工具——它们在宿主进程侧运行，各有自己的闸门。
- 不支持 apptainer / singularity——HPC 常见，但 CLI 语义差异大，单列。

## 2. harness9 能力清单与处置

| # | harness9 能力 | 出处 | 处置 |
|---|---|---|---|
| 1 | `Environment` 接口（RunBash/ReadFile/WriteFile/ID/Close） | `environment.go` | ◐ 工具层已按能力切成三个 Protocol（plan 0029 Q11）。沙箱只实现 `run_bash`，见 Q1。**隔离面与 harness9 相同**：它的 `DockerEnvironment.ReadFile/WriteFile`（`docker_environment.go:46-57`）也是宿主侧 `os.ReadFile/WriteFile`，从不经过 `docker exec`；差别只在本项目不写那两个空转方法 |
| 2 | `LocalEnvironment` | `local_environment.go` | ❌ 不移植：`environment=None` 即本地路径，且它用的 `CombinedOutput()` 正是 `bash` 工具避开的 pipe 阻塞 bug |
| 3 | `DockerEnvironment`：`docker exec` 执行 | `docker_environment.go` | ✅ `environment.py`，另补超时/取消时**杀容器内进程**（Q3）与「容器已不在」可区分（Q4） |
| 4 | 配置：Enabled/Image/CPUs/Memory/Pids/超时/Bootstrap/BlockedHosts | `config.go` | ◐ `SandboxConfig` 不读环境变量，由 `entry/config.py` 统一解析；默认值重新标定（§4） |
| 5 | 容器五状态机 Pending→Running→Stopping→Terminated / Failed | `container.go` | ✅ `ContainerState` |
| 6 | 启动：`docker run -d` + 轮询 `inspect` + 超时后 `rm -f` | `container.go:112-172` | ✅ |
| 7 | 停止：`stop -t` 后无论成败都 `rm` | `container.go:178-196` | ✅ |
| 8 | 加固：cap-drop all、no-new-privileges、pids-limit、tmpfs /tmp | `container.go:118-131` | ✅ 另加 `--init`、`--network none`、`--user` 宿主 uid、`--pull=never`；**不加回**三个 cap（Q5） |
| 9 | 网络：`--add-host` DNS 黑洞，自陈非安全边界 | `container.go:132-134` | ◐ **替换**为 `--network none` 默认（附录 B.3-1）；需要出网者指定一个自管的 docker network |
| 10 | 工作区同路径 bind mount | `container.go:138` | ✅，另支持只读的额外数据挂载（参考基因组等） |
| 11 | Manager：Create / Destroy / DestroyAll / ListAll / 通知回调 | `manager.go` | ✅；回调抛错被吞掉（与 MCP 层同约定，本层不写日志） |
| 12 | `CreateWithRetry`：先确保 daemon，再失败重试一次 | `manager.go:88-110` | ✅ |
| 13 | daemon 探测 + macOS 自动拉起 + 有界轮询 | `daemon*.go` | ✅ `daemon.py` |
| 14 | `ReapOrphans` 按 label 清理 | `manager.go:167-211` | ◐ **收紧**：按「宿主名 + 属主 PID」标签只清理属主进程已死的容器（Q6） |
| 15 | Bootstrap 命令 + 独立超时，fail-open | `manager.go:112-127` | ✅，并且真的能判出失败（harness9 的 RunBash 永远返回 nil，失败分支不可达） |
| 16 | 降级为本地：日志 + prompt + TUI 可见 | `main.go:196-218` | ✅ 日志 + prompt 段 + `AgentApp.sandbox`；另加 `sandbox_required` 让运维选择 fail-closed |
| 17 | prompt 三态：运行中 / 降级 / 未启用 | `builder.go:150-176` | ✅ `entry/sandbox.py` 的 `sandbox_section` |
| 18 | 每个子代理一个沙箱 | `subagent/runner.go:92-100` | ⏸ 接缝在（多沙箱 + label），调用方未到 |
| 19 | cmdRunner 注入供单测 | `container.go:47-54` | ✅ `CommandRunner` Protocol；另有一个真实执行命令的假 `docker` 可执行文件 |
| 20 | 沙箱路径上的 `[TIMEOUT …]` 横幅 | `tools/bash.go:139-151,199-203` | ✅ 由 `tools/builtin/bash.py::_in_environment` 的截止时间触发、`_timed_out` 渲染；`run_bash` 自带截止晚 5 s，保证工具的截止先到。`test_the_bash_tools_own_deadline_wins_and_the_command_dies` 断言横幅文字且容器内进程已死 |

## 3. 包结构与依赖方向

```
omicsclaw/sandbox/          标准库 only，不 import 任何 omicsclaw 包
├── config.py               SandboxConfig（冻结、自校验）
├── runner.py               CommandRunner Protocol + SubprocessRunner + SandboxError
├── daemon.py               ensure_daemon_ready（探测 → 拉起 → 有界轮询）
├── container.py            ContainerState、run_arguments、Container 生命周期
├── environment.py          DockerEnvironment.run_bash → ExecResult
└── manager.py              SandboxManager、SandboxInfo、ReapReport

omicsclaw/entry/
├── config.py               SandboxMode + sandbox_* 字段 → AppConfig.sandbox_config()
├── sandbox.py              SandboxBinding、open_sandbox、prompt 段、bash 审批策略
└── assembly.py             open_app 先开沙箱；BashTool(environment=…)；aclose 回收
```

依赖方向与 plan 0029 附录 B.4 一致并更严：`tools` 定义 `BashEnvironment`，
`sandbox` **结构化满足**它而不 import `tools`（连 `CommandOutcome` 都不借——
`ExecResult` 字段是其超集，由测试钉住）；只有 `entry` 同时认识两边。

## 4. 默认值重新标定（附录 B.3）

| 项 | harness9 | 本项目 | 理由 |
|---|---|---|---|
| 启用 | `SANDBOX_ENABLED != "false"`（默认开，与自家文档矛盾） | `sandbox=off` | 本机不一定有 docker，也没有适合所有组学任务的默认镜像 |
| 镜像 | `ubuntu:22.04` | **无默认**，`docker` 模式下必填 | 组学镜像是 GB 级 conda/CUDA 环境，只有运维知道用哪个 |
| 拉取 | 隐式 pull | `--pull=never` | GB 级镜像在启动超时内拉不完，只会变成两次失败后的降级；缺镜像时报「先 docker pull」 |
| 网络 | 全通 + DNS 黑洞 | `none` | 威胁是**数据外流**（CLAUDE.md 第一条），不是宿主被写坏 |
| 内存 / CPU | `512m` / `1.0` | 不限 | 一次 `sc.pp.neighbors()` 就超 512m；需要时显式配置 |
| pids-limit | 256 | 4096 | 线程计入 pids cgroup，BLAS/numba 在多核机器上一次就上百 |
| 用户 | 镜像默认（root） | 宿主 `uid:gid` | 容器写进工作区的文件归用户所有，而非 root |
| /tmp | tmpfs 256m, noexec | tmpfs 1g, 无 noexec | R `sourceCpp` 等要在 tempdir 里编译并加载 |
| PID 1 | `sleep infinity` | `--init` + `sleep infinity` | 超时被杀后留下的孤儿要有人收尸，否则僵尸计入 pids-limit |
| GPU | 无 | `--gpus` 透传（默认不给） | `rapids_singlecell`；与 `--cap-drop ALL` 的组合**未在本机验证**（无 docker/GPU） |

## 4.5 关键决策

### Q1 —— 文件工具不走沙箱，只有 `bash` 走

plan 0029 Q11 预留了三个文件 Protocol，理由是「只有 bash 走隔离、write 直写宿主，
隔离就是摆设」。逐条核对后结论相反：

1. `read_file` / `write_file` / `edit_file` 各自有边界——`Workspace.resolve`
   （解析符号链接、拒绝凭据、要求在工作区内）。它们**逃不出工作区**，所以不存在
   「改用 write 逃逸」这条路。
2. 工作区同路径 bind mount，宿主侧读写与容器内视图**逐字节相同**。harness9 的
   `DockerEnvironment.ReadFile/WriteFile` 本身就是宿主侧 `os.ReadFile`——路由过去
   在隔离上**零收益**。
3. 路由过去有真实代价：`FileReadEnvironment` 一次取回整个文件，行模式不能流式。
   在一个放着 GB 级 h5ad / FASTQ 的工作区里，模型用 `read_file(offset=0, limit=100)`
   嗅探一个文件头，就会把整个文件读进内存。

所以沙箱只实现 `run_bash`，不实现从不被调用的 `read_file`/`write_file`（那正是
harness9「持有 env 却只写 TODO」的死状态）。

### Q2 —— 沙箱包不写日志、不读环境变量

与 `mcp` 同约定：本层只通过返回值、`SandboxInfo`、`ReapReport` 与异常汇报，
日志全部在 `entry/sandbox.py`；环境变量全部在 `entry/config.py` 解析。

### Q3 —— 超时 / 取消时杀掉**容器内**进程

harness9 的 `exec.CommandContext` 超时只杀宿主上的 `docker` 客户端，容器里的命令
照跑。本实现：

- 命令包一层 `echo $$ > <pidfile>; exec bash -c "$1" > <logfile> 2>&1 </dev/null`，
  pidfile / logfile 放在工作区内的 `.omicsclaw/sandbox/<id>-*/`（0700）——工作区本来
  就同路径挂载，交换目录不需要自己的挂载（最初放在宿主 `/tmp` 下另挂一次，会嵌套在
  容器 `/tmp` tmpfs 之下、依赖运行时的挂载排序，审计指出后改掉，见 §7）；
- 输出写文件而不是 docker 的 stdio 管道——后台化的进程继承的是文件，`docker exec`
  不会被它挂住（与本地路径 Q5 同一个坑）；
- 被取消时：先杀宿主客户端，再 `docker exec <id> bash -c 'kill -KILL "$0"' <pid>`，
  屏蔽二次取消、有界等待。语义与本地路径一致：只杀直接子进程。
- `run_bash` 自己的截止时间是 `timeout + 5 s`，保证从 `bash` 工具调用时**工具的**
  截止先到、模型看到的是 `[TIMEOUT …]` 横幅；自带截止只服务于 bootstrap 这类没有
  外层截止的调用方。

### Q4 —— 「命令失败」与「容器不在」可区分

pidfile 为空说明包装脚本根本没跑起来（容器已停、daemon 断连、镜像里没有 bash），
抛 `SandboxError`（`OSError` 子类），`bash` 工具把它报成「执行环境无法运行命令」；
pidfile 非空则一律是命令自己的退出码。harness9 把两者都折叠成输出字符串。

### Q5 —— 不加回 `DAC_OVERRIDE` / `SETUID` / `SETGID`

harness9 加这三个 cap 是为了 root 下 `apt-get` 能降权。本项目默认以宿主 uid 运行、
默认无网络，包管理器本就用不了；加回去只会扩大容器内 root 的能力。

### Q6 —— 孤儿回收只动「属主已死」的容器

harness9 的 `ReapOrphans` 在启动时、自己还没建任何容器前运行，于是会把**另一个
正在运行的 harness9 进程**的容器一并删掉。本实现给每个容器打
`omicsclaw.sandbox.owner=<hostname>:<pid>` 标签，只回收「同一宿主、PID 已不存在」
的；其他宿主、PID 仍存活（含 PID 被复用）、标签缺失的一律保留——宁可泄漏，
不可误杀。

### Q7 —— 审批放开的三重条件

`sandbox_auto_approve=true` 只有在「沙箱运行中 + `network=none` + `bash` 是装配层
自己构造的那一个」三者同时成立时才把 `bash` 的 `approval_mode` 改成 `AUTO`。
降级永远只会收紧，不会放松。

## 5. 配置

| 字段 | 旗标 / 环境变量 | 默认 |
|---|---|---|
| `sandbox` | `--sandbox` / `OMICSCLAW_SANDBOX` | `off`（可选 `docker`） |
| `sandbox_image` | `--sandbox-image` / `OMICSCLAW_SANDBOX_IMAGE` | 无；`docker` 模式必填 |
| `sandbox_network` | `--sandbox-network` / `OMICSCLAW_SANDBOX_NETWORK` | `none` |
| `sandbox_memory` / `_cpus` / `_gpus` | `--sandbox-memory` … | 空 = 不限 / 不给 GPU |
| `sandbox_user` | `--sandbox-user` / `OMICSCLAW_SANDBOX_USER` | 空 = 宿主 `uid:gid`；rootless Docker / Podman 通常要 `0:0` |
| `sandbox_mounts` | `--sandbox-mount`（可重复）/ `OMICSCLAW_SANDBOX_MOUNTS`（`os.pathsep` 分隔） | 无；只读、同路径 |
| `sandbox_bootstrap` | `--sandbox-bootstrap` / `OMICSCLAW_SANDBOX_BOOTSTRAP` | 空 |
| `sandbox_bootstrap_timeout_s` | `--sandbox-bootstrap-timeout` | 600 |
| `sandbox_runtime` | `--sandbox-runtime` / `OMICSCLAW_SANDBOX_RUNTIME` | `docker`（podman 兼容） |
| `sandbox_required` | `--sandbox-required` / `OMICSCLAW_SANDBOX_REQUIRED` | `false`；`true` 时起不来就拒绝启动 |
| `sandbox_auto_approve` | `--sandbox-auto-approve` / `OMICSCLAW_SANDBOX_AUTO_APPROVE` | `false`；见 Q7 |

## 6. 测试策略

本机没有 docker。三种替身，各管一段：

1. **进程内脚本化 runner**（`CommandRunner` Protocol）——状态机、重试、孤儿回收、
   daemon 轮询等纯逻辑，确定、快速，可注入任意失败。
2. **假 `docker` 可执行文件**（`tests/sandbox/fake_docker.py`）——`exec` 子命令
   **真的**在本机执行 `bash -c`，于是包装脚本、pidfile、输出文件、超时/取消时的
   容器内 kill 全部走真实进程。经 `sandbox_runtime` 注入，一路打通到
   `open_app` → `BashTool` → `ToolRegistry.execute`。
3. **真实 docker 集成测试**——`docker info` 成功时才跑，否则 skip。

分层守卫照抄修复后的版本（plan 0028 附录 B）：AST 白名单 + 动态 import 检查 +
子进程行为探针（跑一遍真实路径后断言 `sys.modules` 里没有 `omicsclaw.tools` 等）。

## 7. 结果

**交付**：`omicsclaw/sandbox/` 6 个模块，标准库 only；`entry/sandbox.py` + `config.py` /
`assembly.py` / `__init__.py` 的接线；`engine/`、`tools/` 零改动。
`tests/sandbox/` + `tests/entry/test_sandbox.py` 共 172 个测试（2 个真实 docker
集成测试在本机 skip）；重建层全量（schema provider engine tools context skills
entry mcp memory sandbox）全绿，唯一既有的收集错误是 `tests/tools/test_workspace.py`
引用已删除的旧模块。17 个变异各被一个具名测试杀死；首轮幸存的一个暴露出孤儿回收里
一段与「属主 PID == 本进程」重复的防护，已删除。

**两轮独立只读审计（Sonnet）**：

*harness9 对照*：逐项核对 §2 表与所有关于 harness9 的断言（RunBash 永不返回错误、
ReapOrphans 误杀并行进程的容器、超时只杀 docker 客户端、DefaultConfig 与文档矛盾），
**全部属实，无虚假陈述，无无理偏离**；唯一未落地的核心能力是子代理沙箱（⏸，接缝在）。
两条文字订正已采纳：Q1 表述会让人误以为 harness9 的文件工具被容器隔离过（并没有，
表第 1 行已写明隔离面相同）；沙箱路径的 `[TIMEOUT …]` 横幅补入表第 20 行。
另注：harness9 自家文档对 ReapOrphans 的描述（`--filter status=exited`）也已与代码
脱节，本计划未依赖它。

*正确性*：无高危问题。采纳并修复：

| # | 级别 | 问题 | 处置 |
|---|---|---|---|
| 1 | 中 | 交换目录在宿主 `/tmp` 下，另挂一次嵌套在容器 `/tmp` tmpfs 之下，依赖运行时挂载排序，本机无法验证 | 移入工作区 `.omicsclaw/sandbox/`，删掉这次挂载；测试钉住「只有一个读写挂载」与目录权限 0700 |
| 2 | 低 | 无 `getuid` 的宿主上容器用镜像默认用户（常为 root） | `host_user()` docstring 写明 |
| 3 | 低 | `_shielded` 吞掉二次取消，读起来像红旗 | 加注释：只在处理第一次取消时调用，调用方会重新抛出第一次 |
| 4 | nit | `stop_grace_s` 用 `int()` 截断 | 改 `math.ceil` |

未采纳：`Container.start` 只对三类异常记录失败状态（其他类型当前不可达，且
`manager.create` 的 `finally` 仍会回收）；同一 `Container` 并发 `stop()`（公共 API
下不可达）。

**仍然开放**：本机没有 docker，真实 daemon 上的行为（加固参数组合、`--network none`、
容器内 kill、宿主 uid 写工作区）只由 `test_docker_integration.py` 覆盖、在此 skip；
Podman 兼容只按 CLI 参数核对过；`--gpus` 与 `--cap-drop ALL` 的组合未验证；CLI REPL
没有 `/sandbox` 状态命令；子代理层未到。
