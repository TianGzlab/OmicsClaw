# 计划 0074 交付记录

日期：2026-10-07。基准：`4bd83b1e`。规格：旁边的 `0074-singlecell-skill-migration.md`。本记录随分期验收更新。

当前状态：N1 c、M0–M9 的本地实施与验收已完成；Standards、Spec 独立审核各五项发现全部关闭，M9 六项核心检查通过。交付在本地分支 `feat/0074-singlecell-library-migration`，未推送或创建 PR。外部待验、既有框架失败和端到端偏差在下面单独列明，不包含在本地通过结论中。

## N1 c：pertpy 安装核验

专用解释器：`/tmp/omicsclaw-pertpy-probe.YfcLRL/overlay/bin/python`。

`pertpy==1.0.3` 是本次 Python 3.11 环境可安装的最新版本。初次 demo 因 pertpy 与 sklearn 1.8 的 `_m_step(..., xp=...)` 接口冲突失败，固定 `scikit-learn==1.7.2` 后，两次真实 demo 均通过，耗时 5.77、5.67 秒；每次 180 个细胞、80 个基因，`NT=60`、`KO_A KO=60`、`KO_B KO=60`。两次逐细胞分类与概率 CSV 完全一致。

overlay 最终占用 757 MiB，`pip check` 未新增冲突；基础环境的 `pip freeze --all` 安装前后相同。CI 的 `anndata==0.11.4` 组合仅完成全新环境依赖解析，共 105 个包，约 380.3 MB 发行文件；尚未在干净 CI 环境运行。M7 使用扩展 job，固定 sklearn 版本。blitzgsea 仅有 sdist，需要 pip 隔离构建，因此本次安装不能等同于线上 `install_skill_deps` 的 wheels-only 路径。详细版本、命令、上游来源和本地证据位置见计划 §9.3。

## 计划复核

第二轮只读复核发现并修订了三处：sc-velocity 的防挂起测试加外层进程组与墙钟超时；`-SIGKILL` 仅在旧 sc-velocity 基线录制且产物完整时接受；本批 MTX/CSV 改造明确限于双细胞与 MAST，其余现有 R 桥接保留原交换格式。N1 c 同步为 22 个整体迁移、3 个 CLI_ONLY、1 个删除，sc-perturb 纳入 M7。

## 改造前检查

| 范围 | 解释器 | 命令 | 结果 |
|---|---|---|---|
| API 文档和依赖声明守卫 | rapids_singlecell | `python -m pytest tests/sdk/notebook/test_skill_api_sections.py tests/skillenv/test_skill_requires_are_declared.py -q -p no:randomly -p no:cacheprovider` | 12 passed，5.61 秒 |
| M1 的既有用例（包含 demo） | OmicsClaw | `python -m pytest skills/singlecell/scrna/sc-filter/tests skills/singlecell/scrna/sc-markers/tests -q -p no:randomly -p no:cacheprovider -o addopts=''` | 5 passed，34.73 秒 |

科学运行限制 `OMP_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、`MKL_NUM_THREADS`、`NUMBA_NUM_THREADS` 为 2；没有运行旧 sc-velocity 的危险用例。

## M0：迁移工具与守卫

parity 改用逐技能注册表，支持带原因的排除、固定输入与文件哈希、双录和结构比较。旧 sc-velocity 的 SIGKILL 例外只在基线录制且产物完整时接受，新 CLI 对照仍要求退出码 0。生成器 demo 先写缓存文件再读取、记哈希；依赖守卫覆盖 `_api.py` 及其直接 `_lib` 引用；迁移名单防遗漏，CI 增加非 CLI 测试。

验证：五试点旧工具 parity 20 passed/216.13 秒；新工具 20 passed/222.07 秒；五示例 5 passed/41.55 秒；当时 notebook 与 parity 轻测 222 passed/36.15 秒；最终 parity/IO/reference/依赖守卫 45 passed/7.56 秒；help 探针 11 passed/61.30 秒。13 个试点非 CLI 测试在禁止网络连接和 skill CLI 的 audit hook 下通过。G14 三种名单变异均被拒绝。GUARDS 的 4 个施工期失败来自当时尚未收尾的 M1 文档/名单，不能用这一轮声称总守卫已全绿。

## M1：筛选、标记基因与 preprocessing 开关

sc-filter、sc-markers 提供函数库、薄 CLI、生成 API 段和真实示例。sc-filter 仅在自己的库里改用 `outliers_flagged`；COSG 的假 p 值改为 NaN，top markers 按分数排。`preprocess(apply_filters=False)` 跳过重复筛选，包括 R 方法的过滤参数，默认不变。marker 表的 `run_info` 从表属性读取过滤回退，不在输入 AnnData 上留下计算副作用。

四个旧 CLI 用例各运行两次，均逐值一致，原始输出保留在 `/tmp/omicsclaw-0074-m1.plB2Nv/`，golden 不提交。CLI/API parity（包括 preprocessing）12 passed/82.14 秒；两个示例 2 passed/11.81 秒，筛选示例确认 2,638 个细胞和参考细胞名完全一致；最终非 CLI 测试 17 passed/12.92 秒；help 11 passed/57.62 秒。API 守卫在临时副本删除公开函数时确实报错。

干净 CI venv `/tmp/omicsclaw-0074-m1.plB2Nv/ci-venv` 使用 `anndata==0.11.4`，未继承 conda 包；安装 58.537 秒，示例 2 passed/18.33 秒，非 CLI 测试 17 passed/11.81 秒，不需要新增依赖。GUARDS 当时 804 passed、6 skipped、1 xpassed，2 个失败来自 M2 在写的 API 文档与 pending 名单。没有 MT 基因且无 `pct_counts_mt` 时默认过滤会报错、binary logreg 的 Scanpy 表缺 group 时会报错，均属原有边界，已写入 Gotchas，未扩展算法修复。

## M2：整合、富集与删除旧组合技能

两个技能完成函数库、薄 CLI、文档和示例。删除 sc-integrate-cluster 的七个文件，技能总数改为 88、单细胞为 30；删除内容可从基准提交 `4bd83b1e` 恢复。四个旧用例双录均确定，八项 CLI/API parity 通过。两个干净环境示例通过；独立环境安装 68.6 秒、945 MiB，pip check 通过，基础环境不变。

有意改动：不再用输入基因拼造假通路；R 随机方法接收种子；整合 demo 的 batch 固定 seed 0；SIMBA 返回真正嵌入的子集；GSVA 尊重显式 GMT。R 的 UMAP 和富集图表暂存数据不进入 run_info JSON。clusterProfiler GSEA 真实运行及重复种子检查通过；GSVA 缺包，只验协议和语法。最终非 CLI/API/R：14 passed、1 skipped；边界、依赖、索引和 eval 定向 159 passed、2 skipped。当时排除的依赖总数问题来自 M3 删除唯一 h5py 声明，现已改为 64，不是删除组合技能造成。

证据：`/tmp/omicsclaw-m2.1wIV3Q/validation-summary.md`。

## M3：输入标准化、双细胞与环境 RNA

三个技能完成 API、CLI、文档和示例。DoubletFinder、scDblFinder、scds 和 MAST 改用 MTX/CSV；SoupX 保留既有桥接。六个旧用例双录均确定；含 sc-de 的 16 项 parity 通过（131.21 秒），三个示例 18.88 秒。DoubletFinder、scDblFinder 用 350 个 PBMC 细胞真实运行通过（2 passed/51.92 秒），没有回退。MAST、scds 缺包，只验交换协议和 R 语法；SoupX 压缩 10x 读取通过，不代表完整校正已实跑。

默认 Python 数值对照不变；R 方法按 API 固定种子，Scrublet 的用户种子开始生效。最终 sc-de 和双细胞 demo 7 passed/90.92 秒，API/MAST 非 R 7 passed/1.72 秒，边界、依赖和 R 路径 22 passed/20.09 秒。没有删除本机损坏的 basilisk 缓存。

## M4：R 步骤

支持大写 `.R` 的 percent 步骤；validate 保持 Python，同 stem 和小写 `.r` 拒绝运行。Rscript 逐 cell 执行并保留部分输出；`step.R` 提供原子读写、输出路径和冻结检查。执行器补记 IO 哈希及 R 包版本，混合模块可重放、生成摘要和判断过期；拼接 notebook 中 R 代码是 markdown。Rscript 路径变化只警告。参考、运行契约、模块模板和 sandbox 文档已更新，CI 增加 base R 测试步骤。

真实 R 测试覆盖 CSV/RDS/PNG、用户 profile 隔离、独立运行、路径错误、H5AD 提示、冻结保护、外层 shell 退出后的 Rscript 清理，以及 IO 文件被删后留下失败记账。`OmicsClaw` Python + R 4.3.3：13 passed/7.43 秒。干净 M1 venv + 系统 R 4.1.2：13 passed/4.87 秒。`rapids_singlecell` 下 `tests/sdk/notebook -k 'not skill_api_sections' -m 'not skill_example'`：228 passed/40.21 秒；施工中的 API 段和科学示例单独按期验证。加入双 runner 分派测试后，`test_executor.py` 31 passed/3.27 秒。真实 GitHub Actions 的 apt 安装耗时和只读 Docker 运行尚未验证。

独立审核复现三项问题：SIGINT/SIGTERM 后 R 继续写文件；符号链接换目标后仍显示 up-to-date；`tables/./x` 被误判为孤立输出。证据在 `/tmp/omicsclaw-0074-m4-review.dq0afI/`。新增测试分别先失败，再修复进程回收、输入逻辑路径和输出标准化。SIGTERM 经前台入口的终止处理记 failed ledger；SIGINT 保留部分 notebook。修复后真实 R 17 passed/11.17 秒，执行器相关 233 passed/44.47 秒。整批两轴复查及 M9 真实 R 验收已完成，见后文。

## M5：通路、基因程序、丰度和通信

四个技能完成 API、CLI、文档和示例。八个旧用例双录均确定；16 项 CLI/API parity 通过（最终 107.22 秒）。四示例 21.97 秒；固定 statsmodels 0.14.6 的干净环境中 14.00 秒。最终非 CLI 20 passed/2.91 秒；全域 help 11 passed/53.75 秒；三项参数/回退变异测试均先失败再恢复通过。

LIANA 相关分数不再冒充通信概率或 p 值，简化 Milo 路径如实命名。pathway API 默认 seed 42，CLI score_genes_py 显式传 0 保持旧结果；AUCell R 接收种子，但本机缺包，只验语法和桥参数。DA 保留既有 R seed 42 和独立 scCODA 采样方式，诊断记录有效种子，不声称全部后端均受用户种子控制。

证据：`/tmp/omicsclaw-0074-m5.WHaeZC/`。

## M6：轨迹、velocity 与调控网络

五个技能完成函数库、薄 CLI、示例和文档。10 个旧 CLI 用例双录均确定；最终 CLI/API parity 20 passed/260.35 秒。基础环境非 CLI 21 passed/13.57 秒；干净环境 21 passed/18.93 秒、五示例 103.72 秒。五个 frontmatter 与基准逐字一致。

velocity CLI 清理自己的 worker，不再向 notebook 的进程组发信号。生命周期测试 2 passed/26.11 秒；原三个 CLI 用例 149.55 秒通过，跟踪的 13 个后代无残留。恢复旧 killpg 的变异由外层 150 秒超时捕获，并清理后代；恢复安全实现后重测通过。删除 killpg 的两次旧脚本探针没有复现 EOF 挂起，跨 session 的继承管道子进程测试属于受控验证，不是实际复现。

scVelo 0.3.4 在 NumPy 2.4.6 失败，干净环境和轻 CI 固定已验证的 2.0.2。DPT 两次 JIT 输出逐 CSV 相同，无 JIT API 满足旧 golden 的 1e-6 阈值；与旧 CLI 的差异仅在三个 pseudotime 列，最大绝对差 6e-7、相对差 2.329e-5。这三个 API 列采用 rtol=3e-5、atol=0，并有超阈值反向测试，CLI 与其他列不变。paul15 未取得许可依据，使用计划允许的 PBMC 备选。缺失的 Slingshot/Monocle3 和完整 pySCENIC 数据库流程未验证。

证据目录：`/tmp/omicsclaw-0074-m6.1q7nxj/`。

## M7：扰动与药物响应

四个技能完成函数库、薄 CLI、示例和文档。控制组识别按完整 token 匹配，WNT3、NTRK1、NT5E 不再误认 NT；删除 DR 的假 p 值，药物分数不冒称预测疗效。24 项 parity 通过，包括更名和重排后按基因键核对的八项数值检查。轻环境 52 项测试及三个示例通过；旧 drug demo 七项通过。

干净 CPU 环境实际安装并运行了 Mixscape 示例，补上上游漏列的 filelock 4.0.12，并固定 statsmodels 0.14.6 和 sklearn 1.7.2。156 个发行包共 1.61 GiB，初装 69.9 秒、补核心包 14.9 秒，两个兼容包的补装未单独计时；pip check 清洁，没有 CUDA/Torch。合成数据把两个 KO 对应基因块下调至 NT 均值的约 5%，H5AD 保存 guide mapping；真实示例中两个 KO 各检出 60/60。这是合成数据结构验证，不是生物学效果证明。扩展 CI job 不作为 required check；远端设置由 owner 决定。

scTenifoldKnk 缺 R 包，只验语法和调用边界；CaDRReS 缺真实模型，只验边界。未改基础 conda 环境。证据：`/tmp/omicsclaw-m7.0i4owa/validation-summary.md`。本节的干净环境实跑取代 N1 初期仅做依赖解析的阶段性记录。

## M8：多样本、ATAC 和 CLI_ONLY

sc-multi-count、scatac-preprocessing 完成 API、CLI、示例及输出文档；三项上游技能保留 CLI，补上 run_cli 用法，纠正 demo、后端名、输出清单和环境限制。FastQC 输入在切换 cwd 前转为绝对路径；新增测试先失败、修复后通过。

多样本 demo 原本忽略第二用例的 --sample-id，因此不能把它当作不同标签算法的覆盖；公共 API 测试另行检查显式 ID、既有标签、特征对齐和计数守恒。ATAC 10x 读取使用 gex_only=False 并保留 Peaks；真实微型 multiome H5 测试确认不混入 RNA。支持 dense 输入不改变旧 sparse demo 的数值。

四个旧用例双录均确定，CLI/API parity 8 passed/63.96 秒。两个示例 19.17 秒，干净 CI venv 中 26.63 秒；ATAC 恢复合成数据三组（ARI > 0.9），不是生物学验证。五个技能完整测试 30 passed/158.50 秒，包含共享 upstream 的四个调用者。该轮 GUARDS 811 passed、6 skipped、1 xpassed，五个失败均为 M6 施工中的 API 段/名单，不能算整批全绿。

## 整批审核与回归

实现检查点为 `239fe4a8`。两个未参与实现的 reviewer 独立审核：Standards 首轮 5 项、Spec 首轮 4 项，有三项重合。问题、修复和证据分轴保留在 [实现审核](0074-singlecell-skill-migration-implementation-review.md)，不是用一次总评覆盖另一轴。

修复后的干净轻环境再次跑完 26 个示例（217.10 秒）；真实 CPU Mixscape 示例另跑通过（4.88 秒）。轻 CI 的精确测试选择在禁止 IP 网络连接和技能 CLI 调用的 audit hook 下为 177 passed、3 skipped、62 deselected（193.06 秒）；本机 Unix socket 留给 scVelo 的 multiprocessing。最初的探针错误地取消了 pytest 的 importlib 模式、又拦住 Unix socket，已修正探针，未为此改业务实现。

框架回归为 5,783 passed、16 skipped、3 xfailed、2 failed（163.21 秒）。两条失败是 `tests/entry/test_cli_activity.py` 的 `test_c1_controls_and_format_characters_never_reach_the_terminal` 和 `test_what_a_tool_says_survives_its_own_tool_start`；在干净基准 worktree `/tmp/omicsclaw-0074-baseline.67pGE6` 上同样失败，未用本次变更掩盖。GUARDS 整组为 821 passed、7 skipped、1 xpassed（125.39 秒）；其中新增诊断测试在没有 Scanpy 的轻框架环境跳过，在科学环境和轻 CI 单独实跑。审核后真实 R/MAST/步骤测试 33 passed（71.67 秒）。

首轮全量基础环境 parity 为 90 passed、10 failed。六项失败是新增防线发现原 API 比较没有实际数值：standardize、ambient 补上与旧 CLI 摘要的数值核对，in-silico 按基因对齐真实分数后，六项全部通过（18.64 秒）。另外四项源于基线线程环境未固定：Harmony 原录制脚本设置五种线程变量为 1；DoubletDetection 原基线没有四种线程覆盖。对同一 PBMC 输入，旧、新 DoubletDetection 在无覆盖时各两次均为 37 个双细胞、所有表格 exact 相等；线程数为 2 时旧、新均为 41，表格也 exact 相等。旧代码自己即可重现 2,687 个分数和六个分类的差异，不能把它算成迁移数值回归。现在 CLI/API 共用各用例明确声明的环境，新录制 metadata 记录线程值；没有改写旧 golden。

四项线程环境重跑全部通过（84.58 秒）；加上首轮 90 项、六项比较修复和 overlay 八项，108 项主 parity 都已有通过结果，分批覆盖，不是声称一次全绿。另八项按基因键的数值对照通过（43.82 秒）。没有改写旧 golden。

本节原始日志集中在 `/tmp/omicsclaw-0074-final.nBqCmC/`。变更过的 clustering、pathway、gene-programs、multi-count、ATAC 的 20 项 parity 已再次通过（169.82 秒）；pertpy/prep 八项通过（34.04 秒），velocity 四项通过（58.96 秒）。脚本化 eval 为 29 passed（26.82 秒），notebook 非示例、非诊断测试为 262 passed（46.54 秒）。

第二轮独立审核的剩余诊断清理和新增 velocity 方向检查已修复，末轮复查通过。三个真实 CLI 的内部诊断清理回归先 3 failed、后 3 passed（37.39 秒）。velocity 的已知方向检查及反向速度拒绝测试通过；撤去方向检查后，反向测试确实失败，恢复后两项再通过（33.36 秒）。真实端到端两次混淆 `cluster_summary.top_gene` 与 `top_effect`，因此补清它们不是同一基因/效应对的文档，未改算法和表结构。全域 help 探针和独立工作目录调用为 11 passed（59.40 秒）。

末轮审查固定到 `1b883307`，Standards 五项、Spec 五项分别全部关闭，没有新增发现。两位 reviewer 独立执行真实 CLI 保存检查、正常和反向 velocity 示例；Spec 还独立验证撤去方向断言后的负对照。完整命令范围、时长及结论分轴保留在实现审核中。

末次三个 CLI 清理后，metacell、pseudotime、velocity 的 12 项 CLI/API parity 全部再通过（157.34 秒）。最终目录核验为 88 个技能、0 skipped；单细胞 30 个，其中 27 个函数库及 `sc-count`、`sc-fastq-qc`、`sc-velocity-prep` 三个 CLI_ONLY。

交付文档更新后的索引、API 段、依赖清单和声明检查为 141 passed（6.57 秒），`git diff --check` 无输出。实现审核固定到 `1b883307`；此后的提交仅整理计划状态、交付记录、审核结果和 CHANGELOG，没有再修改实现。

## M9：真实模型验收

首轮课题 `/tmp/oc0074-e2e/project` 的四个模块均已 ACCEPTED/frozen。模块 01–03 只调用函数库；模块 04 记录 R 4.3.3、Seurat 5.3.0、SeuratObject 5.2.0，五个 R cell 均执行。独立副本单独运行 R 后，两张 CSV 与原件逐值且逐字节一致；修改模块 03 的 marker 生成步骤并重跑后，模块 04 的 R 步骤明确显示 `input changed`。

这一轮只通过 5/6 项验收：主 agent 读了三次 SDK 源码，并为修正审核格式改写了 reviewer 回复，违反约定。这些行为保留在 `interventions.md` 和 `audit.json`，不把最终四个 ACCEPTED 当作整体验收通过。首轮共 100 次主线、87 次 reviewer 模型调用，六次真实审查，合计 2,182 秒。

全新课题 `/tmp/oc0074-e2e-clean.OXUCNs/project`、会话 `E2E-0074-CLEAN` 的六项核心验收已通过。使用部署配置的 `deepseek-v4-flash`；实施者只给任务、缓存路径、离线富集偏好和原样保存审核的规则，没有替模型写步骤或提供结果。每个模块先由真实 module-reviewer 审查，再明确接受。

| 计划 §7.2 项目 | 实测证据 |
|---|---|
| 四模块 ACCEPTED | `01_qc_filter`、`02_preprocess_cluster`、`03_markers_enrichment`、`04_seurat_bcell_crosscheck` 的 manifest 均为 accepted、frozen=true |
| 前三模块用函数库 | QC、doublet、filter、preprocess、cluster、markers、ora 调用均有记录，skill_cli 为 0；preprocess 明确 `apply_filters=False` |
| 真实 R 步骤 | manifest 的 kind=r；R 4.3.3、Seurat 5.3.0、SeuratObject 5.2.0 进入 r_session；五个 R cell 执行序号 1–5，其中三个有 stream、两个静默；混合 replay 成功，brief 包含 R 步骤，拼接 notebook 用 markdown 表示 R |
| 上游变动使 R 过期 | 在课题副本中修改 marker 生成步骤，仅反转输出行序，真实重跑后 `02_seurat_findmarkers.R` 显示 `stale: input changed: results/03_markers_enrichment/tables/markers_all.csv` |
| R 单独运行一致 | 在副本中用普通 Rscript 执行，同一 1614×6 marker CSV 和 10×2 记录 CSV 均逐值、逐字节一致；另核对导出的 13603×2602 MTX 与原 counts 逐元素相等，特征、细胞和标签顺序相同 |
| SDK 源码预算 | 仅一次 reviewer 读取 `skills/_sdk/notebook/checks.py` 的尝试，路径不存在，返回 0 字符；按尝试计数仍为 1，满足不超过 1 次 |

重跑也有两类额外 prompt 偏差，不将其说成完全无偏差：M02 曾把执行日志写到课题外的 `/tmp/val.log` 和 `/tmp/replay2.log`；其 APPROVE 审查副本把三个技能名中的不换行连字符换成 ASCII 连字符，不是逐字保存，但 verdict、问题和论据未改。原回复、存档和精确 diff 都保留在 `audit.json`。这两类偏差不改变上述六项验收结果，也不代表运行时已强制实现目录限制或审查原文不可变。

真实审查中，M02 因缺少矩阵和原始 counts 的逐元素证据被要求修改，模型补验证后再审通过；M03 因把组内最大效应归给另一基因被要求修改，模型改成逐基因表后通过。M04 的 validate 初次把最显著基因 CD79A 误作最大效应基因，模型自行纠正为 IGLL5 后重放通过。实施者没有代写这些修复。

完整证据在 `/tmp/oc0074-e2e-clean.OXUCNs/`：`audit.json`（调用、审查和源码读取）、`verification.json`（独立 CSV 和导出核对）、`standalone-r.log`、`stale-run.log`、`stale-status.log`、`execution-notes.md` 及原始 `logs/`。四轮分析合计 103 次主模型、79 次 reviewer 调用，六次审查，1,828 秒。

最后明确接受的独立模型 turn 在约第 6 秒成功执行 accept，此后 provider 的收尾回复未返回。等候共 397 秒后，只对该验证驱动进程发送 SIGINT，finally 保留 trace，退出码 130，无残留驱动或 R 进程；未中断其他任务或更改已验收输出。这一回合至少完成一次产生工具调用的模型响应，完整请求数、engine outcome 和 token usage 未知，不记为零或 converged。总计至少 104 次已完成主模型调用；已观测的回合耗时合计 2,225 秒，不含回合间停顿及独立副本检查。六次审查共 815.32 秒。`accept-interruption.json` 保留这项限制，六项功能验收不依赖缺失的最终自然语言回复。

外部待验仍为真实 GitHub Actions 首跑和只读容器/sandbox；本次未推送代码、创建 PR 或更改远端 required checks。缺包和缺数据库的科学后端仍按各期列为未验证，没有用协议测试替代真实算法验证。

## 交付后的 CI 与环境核验（2026-10-07）

上述本地交付之后，`57ad6d83` 已按用户要求推送至 `origin/main`。
[首轮 Eval CI](https://github.com/zhou-1314/OmicsClaw/actions/runs/37590039984)
的普通技能示例和扩展 CPU 示例均通过；单元测试为 7072 passed、2 failed，
scripted eval 因依赖单元测试而跳过。两项失败是依赖 fallback 名单未更新、
Scanpy 替身没有覆盖整段测试执行。本轮 reliability 分支已修正这两项，
并明确终端测试的 `TERM=xterm`，保留专门的 dumb-terminal 测试。

本机没有 Docker 或 Podman，仍不能声称已完成真实只读容器验收。
对 `OmicsClaw` 基础环境的只读检查确认 MAST、scds、GSVA、AUCell、
slingshot、monocle3、scTenifoldKnk 不可加载；DoubletFinder、scDblFinder、
clusterProfiler、Seurat 可加载。Python 包发现检查没有找到 pertpy、
pyscenic、memento；pertpy 的已通过证据来自前文记录的独立 overlay，
不表示基础环境装有它。本轮没有安装或升级科学后端。

请求期限和审核原文自动归档的后续实现见
[`FRAMEWORK-REBUILD.md`](../FRAMEWORK-REBUILD.md)。这次测试没有重新运行
M9 的付费模型验收，不能把离线回归说成新的一轮真实模型验证。
