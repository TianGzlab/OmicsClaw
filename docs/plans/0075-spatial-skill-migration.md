# 0075 空间转录组函数库迁移

用户确认先迁移空间转录组，再推进其他模态。沿用 0074 的函数库和薄 CLI 方式，保留现有 CLI 的默认参数、数值和输出文件。验收入口为 `load_skill` 的公开函数、CLI，以及示例的 step runner 执行与 replay。起点为 `main` 的 `d70b3225`。

## 范围与顺序

当前 88 个技能中，单细胞 30 个已经完成分类：27 个函数库，3 个保留 CLI。其他域尚有空间 17、bulk RNA-seq 14、基因组 10、蛋白组 8、代谢组 8、文献 1 个。用户在 S1 后确认继续完成其余 16 个空间技能，最后统一合并 main 并推送；实施可按独立批次交给子 agent，最终仍须独立审核。

| 批次 | 技能 | 状态 |
|---|---|---|
| S1 | spatial-preprocess | 本地验收完成，独立审核已关闭 |
| S2 | spatial-de、spatial-enrichment、spatial-genes | 本地验收完成 |
| S3 | spatial-annotate、spatial-domains、spatial-microenvironment-subset、spatial-statistics | 本地验收完成 |
| S4 | spatial-integrate、spatial-register、spatial-condition | 本地验收完成 |
| S5 | spatial-deconv、spatial-communication、spatial-cnv、spatial-trajectory、spatial-velocity | 本地验收完成；可选后端限制见下文 |
| S6 | spatial-raw-processing | 保留 CLI_ONLY；合成示例执行与 replay 已通过，真实 FASTQ 未验收 |

各批次开始前检查现有算法和依赖，不承诺缺包、数据库或真实输入的后端已经通过验收。文献技能是否适合函数库单独判断，不计作组学模态。

## S1 接口与验证

`preprocess` 接收原始计数 AnnData，返回新的处理后对象，不改调用者的数据。`X` 为 log-normalized 表达，`layers['counts']` 和 `raw` 保留过滤后的计数。公开 `run_info`、簇汇总、QC 表、PCA 方差表及空间分布图；CLI 继续负责读取、报告、画廊和文件输出。

计算复用 `skills/spatial/_lib/preprocessing.py`。目前只有本技能直接调用该模块。补齐随机种子传递，默认 0，与 Scanpy 原来的默认值一致；加载函数库不设置缓存环境变量。组织预设沿用旧行为：等于默认值的阈值仍被预设替换，不能把它描述成“显式传入默认值也能覆盖预设”。

实施次序：

1. 修改算法和 CLI 前，在固定输入上各录两次默认参数及多分辨率变体，保存数值基线。
2. 从公开函数的失败测试开始，实现计算、诊断和返回对象；不复制整套 CLI。
3. CLI 改调函数库，比较旧基线的表、标签、数值列、摘要和图文件名。
4. 增加固定种子的空间合成 demo，明确它不是真实组织测量。示例验证输入不变、计数保存及已知分区的恢复，并运行 replay。
5. 更新生成的 API 文档、空间迁移分类守卫和 CI。独立审核 Standards 与 Spec，修复问题后记录交付证据。

本地 parity 基线位于忽略目录 `tests/parity/golden/`，不进版本库；CI 使用提交的公开行为测试与示例。科学环境为 `/opt/conda/envs/OmicsClaw/bin/python`，另用 CI 的轻依赖环境核验示例。

## S1 交付记录（当时状态）

S1 已完成本地验收和独立审核，位于 `feat/spatial-skill-migration`，尚未合并或推送。后续 16 个空间技能不因计划列出而视为已交付。

- 旧 CLI 默认参数和多分辨率变体各录两次，均逐值一致；记录的代码基线为 `d70b3225`，不排除数值列。
- 科学环境的技能及 CLI/API parity 最终检查 29 项通过，耗时 67.54 秒；独立审核重跑 API 17 项通过。临时 CI 环境的空间技能快速测试、API 文档和 demo 读写检查 74 项通过，示例执行和 fresh-kernel replay 2 项通过。
- 生成文档、空间技能分类、域索引和 parity 工具共 56 项通过。
- 首次 SDK、技能加载和依赖环境回归为 1,233 passed、6 skipped、2 xpassed、5 failed。五项失败均来自新增依赖后的固定数量或映射断言；补齐 `scikit-misc -> skmisc`、`umap-learn -> umap` 并更新断言后，155 项相关测试通过。完整重跑为 1,242 passed、6 skipped、44 deselected、2 xpassed，耗时 213.74 秒。两项 XPASS 是仓库已有的环境相关标记，不是本批新增失败。
- 缺后端测试先发现缺少安装提示；原来的四乘五常数矩阵在 LOESS 内触发原生崩溃。现改为真实合成输入，并在计算前检查后端、给出 `install_skill_deps` 提示。崩溃转储移至 `/tmp/omicsclaw-0075-loess.core`，不提交。此批不承诺 Seurat v3 对任意退化矩阵均可拟合。
- CI 的原有临时 venv 仅新增 [scikit-misc 0.5.2](https://pypi.org/project/scikit-misc/0.5.2/)，未改基础 conda 环境；远端 CI 尚未运行。
- 索引核验为 88 个技能、0 skipped；函数库为单细胞 27 个、空间 1 个。CLI `--help` 与 `git diff --check` 均通过。

复现主要检查：

```bash
NUMBA_DISABLE_JIT=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  /opt/conda/envs/OmicsClaw/bin/python -m pytest \
  skills/spatial/spatial-preprocess/tests tests/parity/test_sc_parity.py \
  -k spatial --import-mode=importlib -q -o addopts=""

/opt/conda/envs/OmicsClaw/bin/python -m pytest \
  tests/sdk tests/skills tests/skillenv tests/parity/test_snapshot.py \
  --import-mode=importlib -m "not slow and not skill_example" -q -o addopts=""

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  /tmp/omicsclaw-0074-m1.plB2Nv/ci-venv/bin/python -m pytest \
  tests/sdk/notebook/test_skill_examples.py -k spatial -q -o addopts=""
```

真实组织数据、LLM 自主选用技能、真实容器和远端 CI 不在本批已验证范围。

### S1 Standards

独立子 agent 首轮发现 1 项 P3：输出契约没有列出七个 PNG 文件名。
提交 `d4047a62` 补齐路径和逐项生成条件，原审核 agent 复核关闭。
最终未关闭项为 0。

### S1 Spec

独立子 agent 对照 `d70b3225...HEAD`、本次确认的三个验收入口及 S1
需求，发现 0 项。审核另行执行科学环境 API 测试 17 项、CI 轻环境
示例执行和 fresh-kernel replay 2 项，均通过；核对了两组原 CLI
基线的提交、重复运行一致性和空排除表，未自行重跑 CLI parity。

## S2–S6 交付记录

空间域 17 个技能已完成分类：16 个函数库，`spatial-raw-processing` 保留 CLI_ONLY。
每个技能都有可执行示例；raw-processing 示例只验收合成输出转换，不代表真实 FASTQ 管线。
加上单细胞，现有 43 个函数库和 4 个 CLI_ONLY 技能。其他模态不在本次交付范围。

### 三个验收入口

- 干净 CI 环境的空间公开 API 测试在审核前通过 87 项；审核修复后最终重跑 96 项通过，42.96 秒。
- 28 个固定输入案例的旧 CLI/API 对比共 56 项通过，耗时 378.30 秒。默认数值、表格、标签、摘要及图文件名与迁移前录制比较；没有任何整个案例仅做结构比较。
- 17 个技能示例及 S1 的专门重放检查共 18 项通过，耗时 373.61 秒。每个示例经 step runner 执行，再在新内核 replay，核对表格哈希、输出存在性和重放状态。
- SDK、技能加载、依赖环境及 parity 工具回归：1,259 passed、6 skipped、60 deselected、2 xpassed，217.66 秒。两项 XPASS 沿用旧标记；有一条 asyncio 子进程析构警告，无失败。
- 框架层回归：5,403 passed、16 skipped、3 xfailed，164.15 秒，解释器为 `/opt/conda/envs/rapids_singlecell/bin/python`。生成 API 文档、域索引、依赖注册和 parity 工具最终检查 186 项通过；88 个技能均可加载，0 skipped。
- 审核修复后，富集、分域、配准和统计的四个示例重新 run/replay，4 项通过。富集新增本地 GMT 的 step 输入哈希检查独立通过，并加入空间 CI job。分域 4 项、富集 6 项 CLI/API 对比复跑通过。

数值比较有三类明确例外，全部在 `tests/parity/` 案例配置中写明原因：

1. PASTE 原实现把 reference-by-source 耦合矩阵用反，并吞掉求解错误，仍报告成功。现在用按源点归一化的 `pi.T @ ref_coords`，失败直接抛出；旧无位移指标及新增 disparity 图不作等值要求。另用不等大小切片和已知耦合矩阵验证映射方向，实际 CPU 求解验证可运行。
2. GSEA/ssGSEA 新增的 requested/executed/fallback 三个诊断字段不与旧摘要作等值要求，原数值表仍严格比较。
3. 旧 scVelo 两次录制仅三个 `velocity_pseudotime` 列不同。仅排除这三列，其余数值仍严格比较；示例的 CSV 不包含该不稳定列，H5AD 保留后端结果。

另外修正了 LIANA rank 被当作 p 值、富集资源失败后静默替换、Getis-Ord 图权重 dtype 不匹配，以及条件比较接受非整数计数的问题。条件比较两种方法都是样本级 pseudobulk，文档已更正。富集文件与远程库读取从计算函数移出，CLI 参数保持兼容。

### 环境与复现

基础科学环境未改动。PASTE 1.4.0 与基础 POT 0.9.6.post1 的 line-search 接口不兼容；POT 0.9.5 也未通过。临时 overlay `/tmp/omicsclaw-0075-paste.tBbG4n/venv` 使用 POT 0.9.4，通过实际 PASTE CPU 测试。独立 venv `/tmp/omicsclaw-0075-ci.huDrtZ/venv` 按新增 CI job 的完整依赖命令安装，`pip check` 通过；不继承基础环境的科学包。

```bash
# ci_python 指向上述干净 venv；parity_python 指向 PASTE overlay。
NUMBA_DISABLE_JIT=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  "$ci_python" -m pytest skills/spatial/*/tests/test_api.py --import-mode=importlib -q -o addopts=""
NUMBA_DISABLE_JIT=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  "$ci_python" -m pytest tests/sdk/notebook/test_skill_examples.py \
  -m skill_example_spatial --import-mode=importlib -q -o addopts=""
NUMBA_DISABLE_JIT=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  "$parity_python" -m pytest tests/parity/test_sc_parity.py -k spatial --import-mode=importlib -q -o addopts=""
```

本地 golden 位于忽略目录，未提交；缺 golden 的 parity 测试会跳过。CI 运行提交的 API 行为测试和全部空间示例，不宣称远端有本地数值快照。一次错误的 `-k 'spatial-velocity or snapshot'` 选择器额外运行了单细胞 CLI，在基础环境发现 PASTE 版本不兼容、pertpy 缺包和两个单细胞 velocity 数值差异后中断（46 passed、5 failed）。这不是本次空间验收结果；改用正确环境和 `-k spatial` 后得到上述 56 项通过，未修改无关单细胞实现。

### 已知边界

- LIANA、GSEApy、Squidpy、PyDESeq2、FlashDeconv、PASTE、infercnvpy、Palantir 和 scVelo 已实际执行。CellRank、dynamical、VELOVI 有 CPU 小规模运行证据；短训练不是收敛或真实组织效果证明。
- 新 CellChat/Numbat R 脚本使用技能内 Rscript 和 MTX/TSV/CSV 交换。矩阵方向、barcode、标签和临时文件生命周期已测，R 语法通过。CellChat 环境中的 NMF 版本过旧，Numbat 缺真实 phased allele 数据；不能声称两者科学计算已验收。
- CellPhoneDB/FastCCC 缺本地数据库；STalign、部分深度学习域识别与去卷积后端没有完整真实训练验收。STalign 信号回退使用外部求解器替身测试，不等于验证了 LDDMM 算法效果。
- 双变量 Moran 的 esda 后端没有 seed 参数，结果会变；文档、警告和 `run_info` 明确 `seed_supported=False`，未录成确定性 parity。
- 真实 FASTQ、真实组织、LLM 自主选用这些技能、容器和远端 CI 未包含在本地验收证据中。

### 独立审核

基线为 `d70b3225`，范围是本计划 S1–S6 及模板中的三个公开验收入口。
两个独立子 agent 分别审核 Standards 和 Spec，未参与本批实现。
Standards 首轮 2 项 P2：富集计算内读文件、STalign 信号回退诊断不实。
Spec 首轮 2 项 P2：三个域识别方法默认 seed 与 CLI 不同、双变量 Moran 静默忽略 seed。
Standards 复核另发现一项 CLI 子进程测试缺 marker，已补齐。两项 P2 与此项测试标记问题均复核关闭；独立运行 registration API 6 项、enrichment API 与输入哈希 step 12 项，全部通过。
Spec 两项 P2 均复核关闭；独立运行 domains 与 statistics 公开 API 26 项通过。
最终 Standards 发现 3 项、开放 0 项；Spec 发现 2 项、开放 0 项。修复前均有失败测试或公开入口复现证据。

代码和本地验收已完成，随本记录提交准备合并到 `main` 并推送。远端推送结果以交付回复中的提交号为准，不把本地测试描述成远端 CI 结果。另一会话的演示文稿目录和 CHANGELOG 条目保留在工作区，不随本次提交。
