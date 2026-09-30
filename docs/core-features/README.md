# OmicsClaw 核心功能文档

本目录描述 OmicsClaw agent 框架的各个核心能力，以当前代码为唯一事实来源。框架重建的经过见 [`docs/FRAMEWORK-REBUILD.md`](../FRAMEWORK-REBUILD.md)。每篇都带"已知限制"一节。

## 分层总览

```
                 ┌──────────── Surfaces ────────────┐
                 │  oc cli   │  oc desktop │ oc channel │   entry/  launch/
                 └─────┬─────┴──────┬──────┴─────┬─────┘
                       └────── AgentApp (entry/assembly.py) ──────┐
                                    │                              │
   context/ ── prompt · budget · ProgressiveCompactor      memory/ · planning/
                                    │                              │
                          engine/  ReAct Main Loop  ◄── TurnAugmentor
                           │                 │
                  provider/ (OpenAI/Anthropic)   tools/ ◄─ hooks/ ◄─ permission/
                                                 │  builtin · MCP · use_skill · task
                                                 │
                                   sandbox/ (bash)   subagent/   skills/ + skills/<domain>/
   schema/ —— 所有层共享的消息契约          observability/ —— 消费 EngineEvent，零接缝
```

## 文档列表

| 主题 | 文档 | 代码 |
|---|---|---|
| 快速开始 | [quick-start.md](quick-start.md) | — |
| Agent Loop | [agent-loop.md](agent-loop.md) | `schema/` `engine/` |
| 模型适配层 | [provider.md](provider.md) | `provider/` |
| 工具调用 | [tool-calling.md](tool-calling.md) | `tools/` |
| 文件系统 | [file-system.md](file-system.md) | `tools/builtin/{read,write,edit}.py` `_workspace.py` |
| Shell 执行 | [shell-execution.md](shell-execution.md) | `tools/builtin/bash.py` `entry/cli/_shell.py` |
| 沙箱 | [sandbox.md](sandbox.md) | `sandbox/` |
| 权限控制（HITL） | [human-in-the-loop.md](human-in-the-loop.md) | `permission/` `entry/approval.py` |
| Hooks | [hooks.md](hooks.md) | `hooks/` |
| 可观测性 | [observability.md](observability.md) | `observability/` |
| 测试 · 评估（Eval） | [eval.md](eval.md) | `evals/` `tests/evals/` `.github/workflows/eval.yml` |
| 上下文工程 | [context-engineering.md](context-engineering.md) | `context/` |
| 渐进式压缩 | [progressive-compactor.md](progressive-compactor.md) | `context/progressive.py` 等 |
| 会话与长期记忆 | [long-term-memory.md](long-term-memory.md) | `memory/` `entry/memory.py` |
| 执行计划 | [planning.md](planning.md) | `planning/` |
| 子代理 | [sub-agent.md](sub-agent.md) | `subagent/` |
| MCP | [mcp.md](mcp.md) | `mcp/` `tools/mcp_tool.py` |
| 网页搜索与抓取 | [web-search.md](web-search.md) | `tools/builtin/web_*.py` `_websafety.py` |
| 组学 Skill 体系 | [agent-skills.md](agent-skills.md) | `skills/`（加载器）+ `skills/<domain>/` |
| CLI | [cli.md](cli.md) | `launch/` `entry/cli/` |
| 三个入口 | [surfaces.md](surfaces.md) | `entry/` `entry/desktop/` `entry/channel/` |

## 阅读约定

- `omicsclaw/runtime/` 仍在磁盘上，只有部分模块能导入，框架里没有代码 import 它，只作历史参考；文档不把它描述为当前行为。依赖它的 4 个 consensus skill（`sc-consensus-clustering`、`sc-consensus-integration`、`sc-consensus-pseudotime`、`consensus-domains`）已移出 index：`SKILL.md` 改名为 `SKILL.md.disabled`，代码留着，改回原名即恢复。`routing/` 已删除（plan 0068 PQ3）。`surfaces/` 与 `remote/` 已删除（plan 0064 P3）。`autoagent/` 已删除，运行时调参见 `omicsclaw/ensemble/tuning/`。
- 文档引用文件与符号，不引用行号。代码变更后，以代码为准并同步修订对应文档。
