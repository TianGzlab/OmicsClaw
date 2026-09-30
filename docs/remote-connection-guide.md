# OmicsClaw-App 远程连接配置指南

远程模式的说明已经合并到一页：[`docs/engineering/remote-execution.mdx`](engineering/remote-execution.mdx)。那里写了怎样在服务器上启动 `oc desktop`（推荐的启动命令、`--abandon-grace`、`--delta-ring-size`、`OMICSCLAW_SKILLS_DIR`）、sshd 的 keepalive 设置、token 放在哪里、App 里怎样建连接配置、断线重连与刷新后的恢复、只读的文件查看、已接受的风险和排错。

本文原先描述的是已删除的旧后端（`oc desktop-server` 加 `omicsclaw/remote/` 的 jobs、datasets、artifacts 路由），历史原文保留在 [`docs/_legacy/remote-connection-guide.md`](_legacy/remote-connection-guide.md)。
