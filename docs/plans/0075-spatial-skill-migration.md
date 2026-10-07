# 0075 空间转录组函数库迁移

用户确认先迁移空间转录组，再推进其他模态。沿用 0074 的函数库和薄 CLI 方式，保留现有 CLI 的默认参数、数值和输出文件。验收入口为 `load_skill` 的公开函数、CLI，以及示例的 step runner 执行与 replay。起点为 `main` 的 `d70b3225`。

## 范围与顺序

当前 88 个技能中，单细胞 30 个已经完成分类：27 个函数库，3 个保留 CLI。其他域尚有空间 17、bulk RNA-seq 14、基因组 10、蛋白组 8、代谢组 8、文献 1 个。用户在 S1 后确认继续完成其余 16 个空间技能，最后统一合并 main 并推送；实施可按独立批次交给子 agent，最终仍须独立审核。

| 批次 | 技能 | 状态 |
|---|---|---|
| S1 | spatial-preprocess | 本地验收完成，独立审核已关闭 |
| S2 | spatial-de、spatial-enrichment、spatial-genes | 实施与验收中 |
| S3 | spatial-annotate、spatial-domains、spatial-microenvironment-subset、spatial-statistics | 实施与验收中 |
| S4 | spatial-integrate、spatial-register、spatial-condition | 实施与验收中 |
| S5 | spatial-deconv、spatial-communication、spatial-cnv、spatial-trajectory、spatial-velocity | 实施与验收中，逐方法记录可选后端限制 |
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

## 交付记录

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

## Standards

独立子 agent 首轮发现 1 项 P3：输出契约没有列出七个 PNG 文件名。
提交 `d4047a62` 补齐路径和逐项生成条件，原审核 agent 复核关闭。
最终未关闭项为 0。

## Spec

独立子 agent 对照 `d70b3225...HEAD`、本次确认的三个验收入口及 S1
需求，发现 0 项。审核另行执行科学环境 API 测试 17 项、CI 轻环境
示例执行和 fresh-kernel replay 2 项，均通过；核对了两组原 CLI
基线的提交、重复运行一致性和空排除表，未自行重跑 CLI parity。
