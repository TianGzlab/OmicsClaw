# 0076 剩余模态函数库迁移

用户确认沿用 0074、0075 的方式，完成 bulk RNA-seq、基因组、蛋白组、代谢组，另行分类文献技能。基线为 `main` 的 `f97f38c1`，工作分支为 `feat/remaining-modalities-migration`。

## 范围

| 批次 | 数量 | 交付要求 | 状态 |
|---|---:|---|---|
| bulk RNA-seq | 14 | 14 个函数库，包括已有比对结果的读取和统计 | 整体验证中 |
| genomics | 10 | 10 个函数库，解析已有序列或结果，不冒称运行上游工具 | 域内验收通过 |
| proteomics | 8 | 8 个表格分析函数库 | 域内验收通过 |
| metabolomics | 8 | 7 个函数库；XCMS 保留明确的 demo-only CLI | 域内验收通过 |
| literature | 1 | 文本分析函数库；文件读取与网络获取分离 | 域内验收通过 |

计算函数返回 DataFrame、AnnData 或 Figure；CLI 负责参数、文件和报告。DataFrame 的运行诊断通过 `attrs['run_info']` 和公开 `run_info` 读取，AnnData 沿用 JSON `uns` 约定。文件读取函数作为 `read_input(..., reader=...)` 使用，网络获取显式命名。外部工具流程保留 CLI 时，必须说明理由并给出 `run_cli` 示例，不以分类代替已有计算能力的迁移。

## 实施与验收

1. 每域先盘点方法、输入与依赖。改动 CLI 前，在固定输入上录两次原输出；已有失败或非确定性单独记账。
2. 按技能做公开函数的失败测试，实现共用计算逻辑，再让原 CLI 调用它。默认参数、种子、表格和图文件保持兼容；科学错误的修正须有理由和回归证据。
3. 验收三个入口：`load_skill` 公开接口、旧 CLI 数值及文件、示例的 step runner 执行与新内核 replay。CLI-only 流程验收真实可运行的命令边界，不把 demo 当完整科学后端。
4. 更新生成 API 文档、分类守卫、域索引和 CI。依赖安装仅用临时环境，保留基础 conda 环境。
5. 两个独立子 agent 按固定基线分别审核 Standards 与 Spec；关闭问题并记录实测证据后交付。

用户已允许分域并行。各实现批次只修改自己的域和独立 parity 配置；共享 SDK、CI、索引与跨域文档由主 agent 整合。另一会话的演示文稿目录及 CHANGELOG 条目保留，不纳入本次提交。

## 交付证据

本轮新增 40 个函数库和 41 个可执行示例。全仓库为 83 个函数库、5 个 CLI-only 技能，索引共 88 个、0 skipped。整体验证及独立审核未结束，暂不标记为已交付。

### 兼容性与边界

- 修改 CLI 前录制固定输入两次，代码基线均为 `f97f38c1`。本地 golden 不提交；CI 跑已提交的已知答案测试和示例，不假称持有本机数值快照。
- 旧 WGCNA demo 因整数矩阵失败，没有可用旧成功输出；新接口用真实 R WGCNA 检验整数输入、显式 power 和模块结果。旧绘图把颜色字符串当整数的问题同步修复。
- bulk DE 旧 demo 的 R dispersion fit 失败后执行 Welch；保留该数值，但新增 warning 和 requested/executed/fallback 诊断。另以过度离散计数验证真实 DESeq2 无回退通过。现有 R bridge 会按已安装包应用 apeglm/ashr，文档不再一概写成 unshrunk。
- 旧 enrichment ORA 的重叠基因字符串顺序依赖 Python hash；迁移前重录时固定 `PYTHONHASHSEED=0`，数值仍逐项比较。Cosinor 根目录的结果表原未进入快照，已在改算法前扩展快照并重录。
- read-qc 示例的部分序列长 143、质量串长 150，修复后平均读长由 149.6514 变为 150；只排除该字段在表和摘要中的位置。
- TrajBlend 用独立 `random_state=42` 代替依赖 demo 消费后的全局随机状态。一个样本 pseudotime 差 0.0081、std 差 0.0011，邻居距离最大差 0.0015，均值差 0.00081；仅这三列和摘要均值排除，fractions、PC1/PC2、最小/最大值仍严格比较，并测同种子复现与全局 RNG 不变。
- ComBat 校正值可以为负。PCA 改用 signed log2，避免旧转换产生 NaN；after silhouette 从 0.0545 变为 0.0544，仅对应表列和摘要字段排除，校正矩阵与 before 指标严格比较。Python KM 同时事件/删失的风险集计算也有已知答案回归修复。
- PPI demo 固定旧 STRING 查询的边表并标来源；默认保留包含外部邻居的旧统计，显式 `induced=True` 才取查询节点诱导子图。两种图定义都有独立已知答案测试。真实联网仅在 `fetch_*` 入口，失败不替换成模拟网络。
- 缺理论肽数的 iBAQ、缺 pathway reference 的真实富集、缺参考注释的 TrajBlend、完全没有正值的代谢插补等输入明确报错。XCMS 真实 mzML 输入不再生成随机峰。结构蛋白组缺距离返回未检查，不能报告全部通过。
- 真实 FASTQ 比对、变异检测、原始 MS 搜索引擎、真实实验数据和 LLM 自主选用技能不在本次已验证范围。基因组若干指标仍是旧有描述性启发式，已在技能文档说明。

### 环境与阶段证据

基础 conda 环境未修改。Python 科学测试使用 `/opt/conda/envs/OmicsClaw/bin/python`；示例使用独立 venv `/tmp/omicsclaw-0075-ci.huDrtZ/venv/bin/python`，R 后端通过显式 `CONDA_PREFIX` 指向已有科学环境。新增 CI job 从 `environment.yml` 的同名 conda 包安装 R/WGCNA/sva/survival/DESeq2，实际远端 CI 尚未运行。

- 基因组：18 项公开 API、10 项 CLI、24 项旧 CLI/API 对比、10 个 fresh replay 通过。
- 蛋白组：32 项域测试、28 项旧 CLI/API 对比、8 个 fresh replay 通过。
- 代谢组：19 个旧 CLI case 与 18 个 API case 逐值通过，XCMS API 不适用；8 个 fresh replay 通过。
- bulk 主批六技能：16 项旧 CLI/API 对比、27 项目录测试通过；后续补零支持信号、Figure/IO/RNG 和真实 DESeq2 测试，计入最终回归。
- bulk read 三技能：11 项目录测试、6 项旧 CLI/API 对比、3 个 fresh replay 通过。
- API 文档、依赖计数和注册契约最终阶段检查 246 项通过；索引重建及检查 8 项通过。
- 框架首次回归 5,813 passed、16 skipped、3 xfailed，仅两个尚未重建域索引失败；索引已重建。SDK 首次回归的失败来自并行中尚未生成的文档及更新前的依赖计数，最终回归结果待记。

### 独立审核

待执行。固定基线 `f97f38c1`；Standards 与 Spec 由未参与实现的两个子 agent 分别审核。需求依据为本计划及用户确认的三个验收入口。另一会话的演示文稿和 CHANGELOG 条目不纳入此次提交。
