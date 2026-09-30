# 计划 0057 交付记录（冻结前部分）

**规格**：`docs/plans/0057-ensemble-tuning.md` 第 3.1 版，另加 owner 于 2026-09-27 作出的裁定 N1–N4。本记录不改动计划正文。
**状态**：T0–T11 已实施。T10 完成到第 4 步：开发报告已写好，`freeze.json`、冻结附录和环境锁定已生成，owner 签字栏留空。开发阶段的结果见 `docs/plans/0057-dev-report.md`。T12 留出集已于 2026-09-28 跑完，42 个单元每个 13 步；收尾分析在 2026-09-30 完成，报告见 `docs/plans/0057-holdout-report.md`，DLPFC 上的无效停止线没有触发，J1 判读句触发。

## 1. 落点

| 步骤 | 内容 | 文件 |
|---|---|---|
| T1 | 面板 v3：PAS 0.5 + 原值 silhouette 0.5，另外输出 SE 所需的量；缺 `X_pca` 时拒绝打分；`--describe-input` 新增 `obsm_keys` 和 `n_vars` | `omicsclaw/ensemble/metrics/{__init__,spatial,score}.py` |
| T2 | `k_control` 的加载与校验；leiden/louvain 的 cpus 设为 2 | `omicsclaw/ensemble/space.py`、`skills/spatial/spatial-domains/tuning.yaml` |
| T3–T7 | 调参包 | `omicsclaw/ensemble/tuning/*.py`、`templates/` |
| T8 | 三个工具；`run_skill` 的按方法预算和 `fixed_k_score`；配置项；entry 层注入 provider；子代理用量上报 | `omicsclaw/ensemble/tuning/tools.py`、`omicsclaw/ensemble/tool.py`、`omicsclaw/entry/assembly.py`（`_ensemble_tools`、`build_tuning_model`）、`omicsclaw/entry/config.py`（`ensemble_tools` … `ensemble_seed`）、`omicsclaw/entry/subagent.py`、`omicsclaw/tools/context.py`（`use_usage_sink`/`report_usage`） |
| N1 | 运行器层种子注入 | `omicsclaw/ensemble/_seed/sitecustomize.py`、`omicsclaw/ensemble/runner.py`（`seed_environment`、`seed_sitecustomize_sha256`）、`omicsclaw/entry/ensemble.py` |
| T9 | 验证脚本 | `docs/plans/0057-validation/`：`common`、`prepare_dev`、`prepare_dlpfc`（含 truth 阶段）、`prepare_cosmx`、`define_population`、`run_arms`（`guard`、`a3_config`、`drive_a3`）、`run_holdout`（双份、哈希链式的计次日志）、`freeze`（`content_sha256`、`sign`、`appendix`）、`evaluate`（`truth_gate`）、`panel_compare`、`seed_spread`、`cost`、`power_0059`、`report`、`frozen_settings` |
| T11 | 删除 `omicsclaw/autoagent/` 和 21 个旧测试；更新活文档；`B4_KNOWN` 清空 | 由子 agent 执行，清单见对话中的汇报 |

## 2. 偏离

1. **A3 驱动**：通过 `omicsclaw.entry.turn` 的私有辅助函数，直接驱动 `exchange_stream`。权限模式为 auto-approve，deny 规则仍然生效。token 超过上限时，当前 exchange 不直接中断，而是在下一次模型调用时由包装后的 provider 返回一条结束回复。这条回复不消耗 token。这样 engine 能正常提交轨迹，随后的提醒就能看到完整历史。
2. **LLM 驱动在 OmicsClaw 环境运行**：rapids_singlecell 环境里没有安装 openai 包。
3. **峰值判定**：峰值只与"有定义的相邻 K"比较。这沿用了计划作者预检脚本的口径。
4. **`select_result` 接受跨 run 的试验引用**：写成 `<run_id>/tNNNN`，用来选择探测中的默认试验。
5. **`ensemble_tuning_images=true` 会拒绝启动**：依据 O5，因为调参模型的消息只能携带文本。
6. **冻结附录单独成文件**：写在 `docs/plans/0057-validation/freeze_appendix.md`，因为派发要求不改动计划文件，所以没有追加到计划末尾。

owner 裁定（不算偏离）：N1 种子注入；N2 跳过规则与 1-SE 保持现状；N3/N4 A3 上限维持 3M、max_turns 50，不设思考预算和 `max_tokens`。

## 3. 冻结：owner 裁定取消技术层面的冻结校验（2026-09-27）

owner 原话："当前项目还在开发过程中，难免会存在某些模块变化的情况……首要是先把整个核心流程成功跑下来，确定当前的框架基本没问题，之后再完善不足的地方。"按这条裁定，**本轮没有做技术层面的冻结校验**。这是 owner 裁定，不算偏离。具体处理如下：

- 删除了以下内容：`freeze.py`、`freeze.json`、冻结附录、环境锁定、签名流程、`run_arms` 的 `guard`、`run_holdout` 的冻结检查与计次（双份日志、哈希链）、`evaluate`/`prepare_dlpfc` 的真值闸门，以及对应的测试。签字前复评的结论随之作废。
- 保留了种子注入（N1），因为它的作用是保证结果可复现，不属于校验。
- `frozen_settings.json` 改为记录文档：逐项记下留出集运行使用的设置，并补上 `measured_on_development` 和 CosMx 源文件信息（sha256 为 `abd2c693…`）。每次运行开始时，`run_holdout.py` 会把它连同模型 ID、种子、git 状态和代码摘要一起写入 `<root>/runs/<时间戳>/`。这些只作记录，运行时不做比对。
- 流程纪律改由报告约束：设置先在开发集上定好，再在留出集上运行；留出集每个臂只跑规定的次数，不挑选结果。
- 0063 已完成对 `omicsclaw/entry/**` 的改动，之后只会改文档和测试。**留出集运行期间不要使用 0063 的阶段回退补丁**：这些补丁会改动 entry/**，届时运行目录里记录的代码摘要就不再对应实际运行的代码。
- 留出数据和 manifest 已迁到持久目录 `/workspace/dataset/private/zhouwg_data/0057_runs/holdout/`。开发集的运行结果仍留在 `/tmp/0057_dev`（269 GB），另有 `0057_runs/dev_measured.json` 记录开发集的关键数字。
