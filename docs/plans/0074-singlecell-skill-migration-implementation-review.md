# 0074 实现审核

日期：2026-10-07。比较基准：`4bd83b1e63097d1433983f6325c1bdd27c6bc2ae`。
首轮被审提交：`239fe4a8`。两个独立 reviewer 分别审仓库规范和计划符合性，均未参与这批代码的实现。下列为首轮结论；修复复审和 M9 最终验收尚未完成。

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

没有把进行中的 M9 验收当成代码缺陷，也没有把缺失后端的协议测试当作真实算法验证。

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
