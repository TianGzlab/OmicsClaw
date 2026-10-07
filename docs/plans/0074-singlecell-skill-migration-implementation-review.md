# 0074 实现审核

日期：2026-10-07。比较基准：`4bd83b1e63097d1433983f6325c1bdd27c6bc2ae`。
首轮被审提交：`239fe4a8`，第二轮：`6fb1ed25`，末轮：`1b883307`。两个独立 reviewer 分别审仓库规范和计划符合性，均未参与这批代码的实现。末轮两轴均通过，各自发现的五项问题全部关闭；下列保留每轮结论。M9 六项核心验收另有真实模型和副本实验的证据，不以代码审核代替。

## Standards

首轮 5 项：

1. P1，velocity 新 API 把旧 helper 的占位结果标为 `scvelo_dynamical`。小矩阵真实探针返回单位图、等距 latent time，却显示 `degenerate=False`，违反“不伪造科学结果”的合同。
2. P2，四个新 MTX/CSV R 桥的 `read.csv(..., row.names=1)` 改写文本标识。真实 R 将 `001` 读成 `1`、分组 `01` 读成整数，破坏交换层的轴标识和输入语义。
3. P2，pathway 的命名基因集入口把 keyword-only 的 `species` 按位置传入，联网前即抛 TypeError，违反公开 API 文档。
4. P2，metacell、gene-programs、GRN 的真实方法回退只记录诊断，不发警告，违反模板的 “warns and records”。
5. P3，部分运行诊断以 dict 存入 AnnData，或 `run_info` 缺少 `keep=False`；部分 CLI 因此把新诊断写入 H5AD，违反模板的 JSON 和清理约定。

这些是合同或行为问题。本轮没有另列 Fowler 启发式异味为阻断项。

## Spec

首轮 4 项：

1. P1，velocity 接受 tiny、graph 和 latent-time 三条占位分支；计划 §5.1 明确要求“回退到伪造或占位的数据……不允许，一律报错”。
2. P2，R CSV 改写细胞和分组文本；违反 §5.1 的 MTX/CSV 交换及 §5.11 的结果保持要求。
3. P2，BBKNN 的后续提示让 `sc-clustering` 重建普通近邻图，丢掉唯一的批次校正；违反 §3.2 的整合后接续聚类要求。reviewer 的真实数据探针中跨批边数从 339 变为 0。
4. P2，`load_gene_sets("hallmark", species="human")` 和 CLI `--gene-set-db` 都在联网前报错；违反计划列出的公开函数与旧 CLI 行为要求。

首轮没有把当时进行中的 M9 验收当成代码缺陷，也没有把缺失后端的协议测试当作真实算法验证。

## 修复与证据

| 问题 | 修复 | 验证 |
|---|---|---|
| velocity 占位结果 | 新 API 和 CLI 始终使用 strict 模式；三个失败分支报错，清除旧成功诊断；其他旧 helper 调用默认不变 | 三条回归先失败后通过；4 项 velocity parity、干净环境示例、2 项进程生命周期检查通过；tiny CLI 退出 1 且无成功 result.json |
| R 文本标识 | R 明确读取字符、保留字面 NA；10x TSV 不添加 CSV 引号；R 输出使用 CSV quoting；Python 先保留标识列文本再设索引 | 12 项身份/通路回归先失败后通过；覆盖前导零、NA、逗号和引号；全部相关 R 与 MAST/步骤检查 33 passed |
| 通路加载 | 按关键字传 `species=species` | 无网络的外部调用边界测试先失败后通过，验证 mouse KEGG 别名及 organism |
| BBKNN 接续 | clustering 新增默认关闭的 `use_existing_graph`；BBKNN 诊断和文档明确要求开启 | 2 项回归先失败后通过；真实 BBKNN 的 342 条跨批边在聚类后仍为 342，邻接矩阵逐元素不变 |
| 回退警告 | metacell、gene-programs、GRN 发出 warning 并保留诊断 | 屏蔽缺失的可选包后，真实替代方法及 warning 捕获测试通过 |
| 诊断接口 | AnnData 的新运行诊断均用 JSON；缺失的 keep 参数补齐，CLI 经公开接口清理；表格诊断仍留在 attrs，不修改输入 AnnData | keep、删除后读取、无关字段保留、真实写入类型和 GRN 深拷贝测试通过 |

补充发现：增加“不得无比较而通过”的 parity 防线后，六个 API 用例原来只比较空的数值列或排除了整张表。现在 standardize、ambient 比较实际摘要数值，in-silico 的真实分数按基因键比较；六项重新通过，没有撤掉防线或改写旧 golden。

完整验证记录见 [交付记录](0074-singlecell-skill-migration-delivery.md)。首轮计数分别为 Standards 5 项（最严重 P1）、Spec 4 项（最严重 P1）；两个维度不合并排序。

## 第二轮与收尾

Standards 复查关闭首轮第 1–4 项；第 5 项还剩 metacell、pseudotime、velocity 三个 CLI 没有清理诊断。reviewer 检查真实 H5AD 复现。新增三个真实 CLI 测试先全部失败（38.14 秒），在各 CLI 保存前经 `run_info(..., keep=False)` 清理后全部通过（37.39 秒），没有删掉科学结果或独立保存的运行信息。

Spec 复查关闭首轮四项，另指出 velocity 示例只证明非退化，未按计划验证模拟数据的已知方向。现在示例从模拟器的 beta、gamma 和原始 spliced/unspliced 层计算导数，逐基因与拟合 velocity 做 Spearman 比较：全部有限、中位数大于 0.5、至少 75% 为正。实测中位数 0.844，40 个基因全部为正。这只验证合成数据的方向，不宣称真实生物学拟合质量。新测试反转全部拟合速度，要求示例拒绝；临时撤去方向断言时，该测试确实失败（17.18 秒），且错误明确显示反向速度被接受。恢复后正常示例和反向拒绝测试均通过（33.36 秒）。

真实端到端还暴露 `cluster_summary` 的字段易误读：`top_effect` 是组内最大值，不一定属于 `top_gene`。补充 docstring 和 Gotchas，提示从 `top_markers` 的同一行读取基因及效应；未改表结构或计算。API 文档与依赖声明复查 35 passed（6.81 秒）。

## 末轮 Standards

原五项问题全部关闭，未发现新增规范违例或 Fowler 阻断项。reviewer 确认固定基准至 `1b883307` 的非空 diff 和三个提交，独立运行三个 CLI 并读取新 H5AD，私有诊断键均不存在。pseudotime 在表图完成后才清理，符合模板契约且保留前序计算。

独立验证：CLI 保存边界 3 passed（48.05 秒）；正常 velocity 示例和反向拒绝 2 passed（35.06 秒）；markers API、API 文档和非 CLI 诊断 46 passed（2.60 秒）。证据在 `/tmp/omicsclaw-standards-last.sjbyhy/`。本轴未决问题：0。

## 末轮 Spec

首轮四项和第二轮新增方向检查均已关闭，未发现新增缺陷。方向真值来自拟合前的模拟输入，不依赖拟合结果自证；反向测试要求具体的方向错误信息。原四项修复及 parity 比较文件在最后一轮没有变动，科学比较未放宽。

独立验证：正常 velocity 示例和反向拒绝 2 passed（28.19 秒）；严格失败分支与真实 velocity CLI 保存边界 7 passed（20.44 秒）。reviewer 另做负对照，仅在临时诊断中撤去方向断言，反向测试如期失败。markers 只澄清字段含义，没有改变算法或表结构。本轴未决代码问题：0。

## M9 证据复核

Standards reviewer 又抽核四模块 manifest、R 运行记录、原件与独立副本的 CSV 哈希及 stale 日志，确认“六项核心验收通过”的措辞有证据。SDK 源码计数为一次失败尝试、零字符。临时路径和 Unicode 审查副本偏差须单独披露，不能称完全无偏差；详细经过见交付记录。最后接受已完成，但 provider 收尾未返回，397 秒后仅中断该验证驱动；最终请求数和用量明确保留为未知，没有用零填补或声称该回合 converged。

Spec reviewer 独立核对原始 manifest、trace、R 账本并重跑只读输出核验，确认四模块 accepted/frozen、函数调用无 CLI 或 stub、R 记录齐全、两张 CSV 一致、上游哈希变化触发过期，以及一次失败源码读取。审查原文与副本仅有三个连字符差异；并补出第二个课题外日志 `/tmp/replay2.log`，已连同 `/tmp/val.log` 在交付记录列明。六项验收通过，原代码 Spec 结论不变。
