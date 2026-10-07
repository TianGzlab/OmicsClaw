# 计划 0074 交付记录

日期：2026-10-07。基准：`4bd83b1e`。规格：旁边的 `0074-singlecell-skill-migration.md`。本记录随分期验收更新。

当前状态：范围为整个 M0–M9。N1 c、M0–M8 已实现并完成本地针对性验证；M4 独立审核的三项问题已修复。M9 端到端与整批两轴审核进行中。本地分支为 `feat/0074-singlecell-library-migration`，不自动推送或创建 PR，本记录不表示整批已经交付。

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

独立审核复现三项问题：SIGINT/SIGTERM 后 R 继续写文件；符号链接换目标后仍显示 up-to-date；`tables/./x` 被误判为孤立输出。证据在 `/tmp/omicsclaw-0074-m4-review.dq0afI/`。新增测试分别先失败，再修复进程回收、输入逻辑路径和输出标准化。SIGTERM 经前台入口的终止处理记 failed ledger；SIGINT 保留部分 notebook。修复后真实 R 17 passed/11.17 秒，执行器相关 233 passed/44.47 秒。尚待最终两轴审核复查。

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
