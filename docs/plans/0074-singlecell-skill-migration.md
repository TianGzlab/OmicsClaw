# 计划 0074：单细胞其余 26 个 skill 迁移到函数库形态，加上 R 步骤

**状态**：第 3 版实施中（2026-10-07）。第 1 版经独立审核（`docs/plans/0074-singlecell-skill-migration-review.md`），第 2 版已接受该轮审核意见。owner 随后对 N1 选择 c：先用 overlay 安装 pertpy、核实依赖，再按原计划迁移 sc-perturb，并确认本次完成整个 M0–M9、交付审核结果。本版补入这项裁定及实测证据；各期实现、验证和审核状态见 `0074-singlecell-skill-migration-delivery.md`。

### 修订说明

实施核验补充（2026-10-07）：本次按 owner 的整批接续要求在一个本地迁移分支交付，不自动推送或创建分期 PR；GitHub CI 首跑和容器验收单独列为外部待验。paul15 未取得许可依据，M6 按本计划的备选用 pbmc3k_processed。scVelo 0.3.4 在 NumPy 2.4.6 的标量转换失败，轻 CI 固定已实跑的 NumPy 2.0.2；速度示例的 simulation 显式设 n_vars=40，避免默认四基因落入旧 toy fallback。DPT 新 API 不再改全局 NUMBA_DISABLE_JIT，两次 JIT 结果一致，但与旧 CLI 的三列 pseudotime 有最大 6e-7 绝对、2.329e-5 相对差异；仅这些 API 列放宽至 rtol=3e-5、atol=0，其他对照不变。pertpy 的干净环境另需显式 filelock 与 statsmodels 0.14.6，详见交付记录。

第 3 版（2026-10-07）：接续会话 `c56cd644-2cf5-4451-a9f9-fc04ed2d04c3` 的 N1 c 裁定。§9.3 记录 pertpy overlay 的安装、两次真实 Mixscape 运行和 CI 依赖解析；迁移名单、M7 与扩展 CI 示例同步更新。第二轮只读复核另修正三处：sc-velocity 测试加外层墙钟超时；`-SIGKILL` 例外仅限旧 sc-velocity 的完整基线录制；MTX/CSV 改造明确限于双细胞和 MAST，避免扩大现有 R 桥接的迁移范围。

**第 2 版（2026-10-07）**：逐条对应审核报告的编号。

| 审核编号 | 第 2 版的改动 | 位置 |
|---|---|---|
| B1 | job3 改为每期列出要装的包并钉版本，只装示例实际用到的；重依赖的示例放进不做 gate 的扩展 job；每期首跑记下安装与运行耗时，超预算就拆；skill 自带测试只跑不起 CLI 的用例（marker `cli_subprocess`）。这几条写进防线账 G16 至 G18 | §5.4、§5.10、§6 各期 |
| B2 | sc-velocity 的薄壳先结束自己的子进程（joblib 自带的 loky 关掉 worker，必要时用 psutil 补杀），再 `os._exit(0)`；动手前先在 `/tmp` 做"读管道到 EOF、带超时"的探针；新测试给 `run_cli` 设超时并断言按时返回。§2.2.5 补上 sc-velocity 那条会杀掉 pytest 的用例 | §2.2.5、§3.2、M6-4、§7.3 |
| 应改 1 | 第 1 版的 M2（R 步骤）不再是迁移各期的前置，只要求在端到端之前完成；它改为第 4 期。sc-batch-integration、sc-enrichment 提到 M1 之后的 M2。每期一个 PR | §0、§6 |
| 应改 2 | 两份基因集别名表本批不统一，各用各的；`_lib/stat_enrichment` 的共用加载推迟。scvi 开始用 `random_state`、CellPhoneDB 默认种子从随机改为 0、harmony 在小数据上复用 `X_pca` 都列进有意改动 | §3.2、§5.2、§5.11 |
| 应改 3 | 3 个双细胞 R 脚本改用 Matrix Market 加 CSV 交换数据；试点的 `sc_mast_de.R` 一并改，列为有意改动；本机能对 DoubletFinder、scDblFinder 跑 `requires_r` 测试 | §3.2、§5.1 第 5 条、§5.11、M3 |
| 应改 4 | 每个 skill 动手前先在 HEAD 上跑 SKILLCHECK 的前两条，记下既有失败；通过标准改成"除既有失败外全部通过"，每个既有失败写明修了还是保留。审核举的 sc-pathway-scoring 例子在本机其实会被 `skipif` 跳过（`test_sc_pathway_scoring.py:19-25`、`:47`），规则照加 | §2.2.5、§6 |
| 应改 5 | 生成器先把数据写进 demo 缓存目录，再像下载的数据一样读文件、记哈希；合成数据埋入已知结构，示例断言能找回 | §5.4 |
| 应改 6 | `outliers_removed` 只在 sc-filter 自己的 `_api.py` 里改名，通过标准改成一条输入带 `outlier` 列的单元测试 | §3.2、M1 |
| 应改 7 | 删除 sc-integrate-cluster 的改动清单补全（`agent-skills.md` 9 处计数和 `:115` 的未迁移数、`INDEX.md:11`），M2 验收加计数检查 | §4.1、M2 |
| 应改 8 | 防线账补 G11 的旁路，新增 G16 至 G18 | §5.10 |
| 应改 9 | Q11 改为推迟，原 M2-5 删除 | §5.6.5、§9 |
| 应改 10 | 代码基准改为 `4bd83b1e`，计划引用的行号都按它重核过 | 行号约定 |
| 应改 11 | 改共享 `_lib` 之前，先给导入该模块、尚未迁移的 skill 录好 parity 基线 | §5.2 |
| 第 4 节小问题 | `_check_code` 行号；sc-DA 的 `--method` 行号；`reference` 长度；GUARDS 耗时；CellChat 已装但加载失败；`sc_mast_de.R` 的下载前提；被 SIGKILL 的子进程返回 -9；`extract` 本来就能处理缺 h5ad；§4.1 否定备选 c 的理由；`apply_filters`；`OMICSCLAW.md:89-91` 两句；`format_step` 表头；IO 补记持锁与 `read_run` 的新桶；`_build_r_env` 的 `mkdir`；`OMICSCLAW_RSCRIPT` 去掉；`apt-get update`；r-base-core 不带 ggplot2；`.h5ad` 的报错提示；`read_any` 的矛盾；G14 断言名单里的 skill 存在；`yaml.safe_load` 只查语法；sc-grn 不装 arboreto | 散见各节 |
| 第 6 节 Q1 至 Q13 | 按 owner 裁定落定，原问题保留在 §9.2 | §9 |
| 第 7 节砍减 | sc-count、sc-velocity-prep 列入 `CLI_ONLY`；Q11 推迟；R 驱动只做逐 cell 标记和出错 cell 序号，G11 只警告；`DEMOS` 保留 `download`、只加 `generator`，速度示例用 `scvelo.datasets.simulation`；共用基因集加载推迟；sc-perturb 在 CI 装 pertpy 推迟 | §3、§4、§5.4、§5.6 |
| 第 7 节新增 | 双细胞脚本改 MTX/CSV；动手前在 HEAD 上跑测试；CI 钉版本并记首跑耗时；sc-velocity 子进程清理的探针 | §6 |

阶段编号随之改变（第 1 版 → 第 2 版）：M0 → M0；M1 → M1；M2（R 步骤）→ M4；M3 里的 sc-batch-integration 与删除 sc-integrate-cluster → M2，其余 → M3；M4 里的 sc-enrichment → M2，其余 → M5；M5 → M6（sc-velocity-prep 移到 M8，只改 `SKILL.md`）；M6 → M7；M7 → M8；M8 → M9。

**第 1 版（2026-10-07）**：初稿。

**编号约定**：0070 的 D1 至 D18、O1 至 O8（`docs/plans/0070-notebook-skill-runtime.md` §2.1、§7.0）和 0071 的裁定照旧有效。派发时已定的事项记作 S1 至 S9（§2.1）；owner 对本计划的裁定见 §9.1。阶段 M0 至 M9，阶段内任务记作 M3-2 这样；防线接着 0070 的编号，为 G10 至 G18；风险 R1 至 R15；第 1 版的问题 Q1 至 Q13（已裁定），第 2 版新出现的问题记作 N1。

**行号约定**：以 `main` 的 `4bd83b1e` 为准。它相对第 1 版的基准 `915289d3` 从 22 个 CLI 里各删了两三行（`write_replot_hint` 的导入和调用），被引用的主脚本行号大多前移 1 到 2 行；计划引用的 `OMICSCLAW.md`、`llms.txt`、`agent-skills.md` 行号不在改动范围内。实施时按符号名重新定位。

**代码注释约定**：同 0070。实现时写的 docstring 和注释只说明函数做什么、有什么前提，不写计划编号和决策经过。

**如何核实**：
1. 名单：遍历 `skills/singlecell/*/*/`，有 `SKILL.md`、没有 `_api.py` 的目录正好是任务说明列的 26 个，有 `_api.py` 的是 5 个试点；26 个目录各有且只有一个主脚本，`run_cli` 的 `main_script`（`skills/_sdk/notebook/_skills.py:309-315`）对它们都能用。
2. 26 个 skill 的 `SKILL.md`、主脚本、`references/`、`tests/` 和用到的 `skills/singlecell/_lib` 由 5 个子 agent 分组读过，结论带 `file:line`；影响设计的几处我又读了源码。第 2 版把计划里的行号在 `4bd83b1e` 上逐个重核。独立审核另抽查了 40 多条（审核报告 §5）。
3. 在 `/tmp/ocprobe`（`skills/` 的副本）用 `OmicsClaw` 环境把 26 个 CLI 的 `--demo` 各跑一次，记下耗时与退出码（§3.1）。仓库里没有写入任何文件。
4. 两个 conda 环境里逐包 `importlib.util.find_spec`；`OmicsClaw` 的 Rscript（R 4.3.3）里逐包 `requireNamespace`；`importlib.metadata.requires` 查 job3 候选包的依赖（§5.4）。
5. R 步骤驱动的做法用 `/tmp/rprobe` 里的探针跑通过（§5.6.4）。
6. GitHub runner 镜像：读了 `actions/runner-images` 的 `README.md` 和 `images/ubuntu/Ubuntu2404-Readme.md`。`ubuntu-latest` 对应 Ubuntu 24.04；镜像版本 20260927.320.1 的 "Language and Runtime" 里没有 R，全文也没有 Rscript。
7. 跑过的测试只有：`tests/skillenv/test_skill_requires_are_declared.py`（5 passed）；7 个 skill 自带的静态测试（11 failed、21 passed，§2.2.5）；26 个 skill 测试目录的 `--collect-only`。没有跑全量测试。
8. zellkonverter 默认读取器的探针触发了 basilisk 首次安装，4 分钟内下载了约 1.9 GB 仍未完成，已中止（§2.2.1）。

**前置与关联**：0070（运行层、5 个试点）、0071（`run.py reference`、`skills._sdk.notebook.checks`、审查摘要）；0072、0073 是只留本地的论文计划，对 sc-markers、sc-filter、sc-batch-integration、sc-enrichment 有需求（§2.4）。0073 的 C1、C2 不在本计划内（§2.4）。

---

## 0. 摘要

1. 26 个 skill 的处置（§3、§4）：22 个整体迁移，包括 N1 c 已确定的 sc-perturb；每个增加 `_api.py`、CLI 薄壳、生成的 `## API` 段及 `examples/example_step.py`，改造前录 parity 基线。sc-count、sc-velocity-prep、sc-fastq-qc 列入 `CLI_ONLY`，只改 `SKILL.md`（sc-fastq-qc 另修一个相对路径的缺陷）。sc-integrate-cluster 删除，skill 数从 89 降到 88。sc-perturb 在专用 overlay 中验证，依赖与运行证据见 §9.3。
2. R 步骤是单独的一期（M4）。允许 `<k>_<name>.R` 步骤，用 Rscript 无状态执行，按 cell 渲染成"代码加日志"，记账、过期判定、重放、验收与 Python 步骤共用一套逻辑。R 端只提供 `read_input()`、`write_output()`，只登记路径；哈希、契约检查和记账由执行器用 Python 补记。skill 的 R 方法照试点的做法由 Python `_api.py` 经 `RScriptRunner` 调用。M3 将三个双细胞脚本与 MAST 的交换格式改为 Matrix Market 加 CSV；其余现有 R 桥接保留原格式。没有哪个迁移期依赖 R 步骤，它只要在端到端（M9）之前完成。
3. 函数设计沿用试点约定，补 8 条新情况（§5.1）。`_lib` 本批只加不搬（§5.2）。
4. 分十期，每期一个提交、一个 PR。第 2 版估计约 36 个工作日，N1 c 恢复 sc-perturb 整体迁移后，M7 增加约 1 天，合计约 37 天（§6）：

   | 期 | 内容 | 天 |
   |---|---|---|
   | M0 | 迁移工具与守卫 | 2.5 |
   | M1 | sc-filter、sc-markers（论文 pilot 先用），试点 `preprocess` 加 `apply_filters` | 2 |
   | M2 | sc-batch-integration、sc-enrichment（方向 C v1），删除 sc-integrate-cluster | 4.5 |
   | M3 | sc-standardize-input、sc-doublet-detection、sc-ambient-removal；双细胞与 MAST 的 R 脚本改用 MTX/CSV | 3.5 |
   | M4 | R 步骤 | 4 |
   | M5 | sc-pathway-scoring、sc-gene-programs、sc-differential-abundance、sc-cell-communication | 5.5 |
   | M6 | sc-cytotrace、sc-metacell、sc-pseudotime、sc-velocity、sc-grn | 6.5 |
   | M7 | sc-perturb-prep、sc-in-silico-perturbation、sc-drug-response、sc-perturb；扩展 CI job | 4 |
   | M8 | sc-multi-count、scatac-preprocessing；sc-count、sc-velocity-prep、sc-fastq-qc 只改 `SKILL.md` | 2.5 |
   | M9 | 端到端验收与交付记录 | 2 |

5. 盘点时发现的问题，会让函数库给出错误、伪造或危险结果的当场修，列为有意改动（§5.11），并从 parity 比较中排除；其余写进 `SKILL.md` 的 Gotchas。最要紧的几条：`sc_velocity.py` 退出时 `killpg` 自己的进程组，经 `run_cli` 调用会连 kernel 一起杀掉；`sc-pseudotime` 的默认表示用 UMAP，demo 上大批细胞的 pseudotime 为 inf；`sc-enrichment` 默认引擎下 GSEA 恒返回 0 条；`sc-cell-communication` 把 liana 的 `specificity_rank` 当 p 值计数。

---

## 1. 目标与非目标

### 1.1 目标

- 单细胞 31 个 skill 里，除了列入 `CLI_ONLY` 或删除的，都能在步骤里用 `load_skill` 调用；`## API` 段与代码一致；旧 CLI 的结果不变，有意改动逐条列明。
- 模块里可以写 R 步骤，执行、记账、过期、重放、审查摘要、验收都覆盖它。
- 0072 pilot、0073 的 pbmc3k 流程和方向 C v1 要用的 sc-markers、sc-filter、sc-batch-integration、sc-enrichment 最先可用。
- `sc-integrate-cluster` 对 consensus 的从属说法得到处置（0070 §1.3 的推迟项）。

### 1.2 非目标

- genomics、proteomics、metabolomics、空间、bulkrna；`load_demo` 登记 bulk CSV。
- 删除 CLI（另一份计划）；`/outputs` 与 `/recent` 的旧路径。
- 0073 的 C1、C2；skill 的 R 方法记 R 包版本（Q11 推迟，同属 provenance 增强）。
- 进化循环及其依赖项。
- 补装本机缺的 R 包和其他 Python 后端，修改 `environment.yml` 的依赖声明。N1 c 明确授权的 pertpy 专用 overlay 是例外。
- 修 `_lib/viz/` 里"画图即写文件"的函数（§5.1 第 7 条）。
- 统一 sc-enrichment 与 sc-pathway-scoring 的基因集别名表，以及把基因集加载提到 `_lib`（应改 2）。

### 1.3 仍然推迟的项目

0070 §1.3 的推迟项里，R 步骤和改写 `sc-integrate-cluster` 本计划处理。其余照旧推迟：

| 项目 | 这批迁移离不开它吗 | 结论 |
|---|---|---|
| `archive` 子命令 | 不需要，迁移不产生被推翻的模块 | 推迟 |
| 哈希缓存 | 新 demo 最大的是 paul15（约 10 MB），`status` 重算哈希不到 1 秒 | 推迟 |
| 原 G7（桩模式横幅） | 不需要，本计划不加新的桩 | 推迟 |
| 后台运行与 `--detach` | 单个示例在本机最长约 25 s；真实数据上的长步骤仍按步骤逐个 `run` | 推迟 |
| `run.py methods` | 不需要 | 推迟 |

---

## 2. 现状与证据

### 2.1 本次派发时已定（S1 至 S9）

| 编号 | 内容 |
|---|---|
| S1 | 范围是单细胞其余 26 个 skill；计划内分期，R 步骤支持单独一期。原定"排在第一个需要 R 的 skill 之前"，owner 2026-10-07 改为"在端到端之前完成即可"（§9.1） |
| S2 | skill = 手写可演化的 `SKILL.md` 加私有函数库 `_api.py`；跨 skill 的稳定积木才放领域 `_lib`；`## API` 段由签名和 docstring 生成并有一致性测试；每个 skill 一个可执行示例，数据来自 `load_demo`，CI 里真跑（0070 D2、D3） |
| S3 | 过渡期 CLI 改成调用 `_api.py` 的薄壳，用 parity 保证新旧一致；基线必须在改造前用旧 CLI 录，每个 skill 只录默认参数加 1 个变体；删 CLI 另立计划（0070 D6、O1） |
| S4 | 示例和 parity 用 `/opt/conda/envs/OmicsClaw/bin/python`；其余测试用 `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`；`Rscript` 在 `/opt/conda/envs/OmicsClaw/bin/Rscript`（0070 O3） |
| S5 | R 步骤的既定设计：`NN_xxx.R`，Rscript 无状态执行，经 `intermediate/` 文件与 Python 步骤交换数据，渲染成"代码加日志"；sandbox 镜像有 R 步骤时要装 Rscript（0070 D10、D17） |
| S6 | 改写 `sc-integrate-cluster` 的 consensus 从属说法，必要时可以提议删除或合并；其余 0070 §1.3 推迟项照旧，除非有离不开的证据 |
| S7 | genomics、proteomics、metabolomics、空间、bulkrna 不在范围；`load_demo` 登记 bulk CSV 不在范围 |
| S8 | 0073 的 C1、C2 不在范围；迁移若改变它们的必要性，写一句 |
| S9 | 0072 pilot 要用 sc-markers（double dipping）和伪重复相关的 DE，0073 的 pbmc3k 流程里 sc-filter 只有 CLI；分期时排在前面 |

### 2.2 代码事实

#### 2.2.1 运行层与 R

- 执行器拒绝 R 步骤的两处：`_check_runnable` 在模块里有 `.R` 文件时报 "R steps are not supported yet" 并返回 2（`skills/_sdk/notebook/_executor.py:268-276`）；`run_module` 对 `.R` 的步骤目标同样返回 2（`:337-341`）。`replay` 也走 `_check_runnable`（`:511-513`）。
- 步骤文件名的正则只认 `.py`：`LAYOUT["step_file"]`（`contract.py:29`）；validate 步骤 `^\d{2}[a-z]?_validate\.py$`（`:30`）。`Module.r_files()` 收 `.R` 和 `.r`（`_layout.py:94-97`），`resolve_target` 对 `.R` 文件放行，留给后面报错（`:153-155`）。
- `StepRunner` 是一个只有 `run(notebook, *, env, cwd)` 的协议（`_runners.py:45-47`），0070 §3.2.4 已写明 `RscriptRunner` 接在这里。`PythonKernelRunner.kill()` 按 kernel 的进程组发 SIGKILL（`:113-124`）。
- Python 写死的地方：`run_start` 的 `kind="python"`（`_executor.py:166-176`）；每步输出的表头固定打印 `python=...`（`:86`）；manifest 步骤项的 `kind: "python"`（`_manifest.py:181-182`）；`interpreter_info()` 只记 Python 解释器（`:57-68`）；拼接的模块 notebook 的 kernelspec 固定为 python3（`_executor.py:260-262`）；`to_notebook` 同样固定（`_percent.py:158-160`）。
- `_percent._check_code` 用 `ast.parse` 找魔法行（`_percent.py:77-93`），对 R 代码会误报：R 里以 `!` 开头的行是合法的取反。
- `step_context` 只认以 `.py` 结尾的步骤文件（`_io.py:65-74`）。
- 现有的 R 桥是 `skills/_sdk/r_script_runner.py`：`_preferred_rscript_executable` 依次找 `$CONDA_PREFIX/bin/Rscript`、`sys.prefix/bin/Rscript`、`PATH`（`:26-40`），所有领域的 R 调用都经过它；`run_script` 用 `subprocess.run(capture_output=True)`，不新开会话（`:256-262`），所以 skill 的 R 子进程在 kernel 的进程组里，看门狗杀 kernel 进程组时会一起杀掉；`_build_r_env`（`:316-372`）设 `R_LIBS_USER`、`RETICULATE_PYTHON`，并在 conda 前缀下 `mkdir` 一个 `omicsclaw-library` 目录（`:349`），只读的 sandbox 镜像里这一步会失败。共享 R 脚本 28 个，在 `skills/_sdk/r_scripts/`，文件名集合被 `tests/sdk/test_public_surface.py:134-135` 冻结。另有两个 skill 自带脚本目录：`sc-enrichment/rscripts/`、`sc-pathway-scoring/rscripts/`。
- `skill_load` 记的依赖版本用 `importlib.metadata`（`_skills.py:130-137`），R 包一律记成 `None`。
- R 环境（`OmicsClaw`，R 4.3.3）：有 jsonlite、digest、knitr、evaluate、Seurat、SeuratObject、SingleCellExperiment、zellkonverter 1.12.1、DESeq2、edgeR、SoupX、DoubletFinder 2.0.6、scDblFinder 1.16.0、batchelor、clusterProfiler、fgsea、msigdbr、Matrix、reticulate。CellChat 2.2.0.9001 已装，但加载失败（要求 NMF ≥ 0.23.0，本机 0.21.0）。没有 rhdf5、MAST、nichenetr、slingshot、monocle3、AUCell、GSEABase、GSVA、scds、miloR、speckle、scTenifoldKnk、IRkernel、org.Hs.eg.db。rhdf5 在 `environment.yml:206` 声明了，本机却没装；MAST、slingshot、monocle3、AUCell、GSEABase、nichenetr、scds、GSVA 在 `environment.yml` 和 `0_setup_env.sh` 里都找不到。
- zellkonverter 读 h5ad 的两条路在本机都走不通：`readH5AD(path, reader = "R")` 报 "there is no package called 'rhdf5'"；默认读取器第一次用时由 basilisk 下载 Miniconda 并建一个 Python 环境，探针 4 分钟内下载了约 1.9 GB 仍未完成。共享脚本里用默认读取器的有 `sc_doubletfinder.R:29`、`sc_scdblfinder.R:28`、`sc_scds.R:30`、`sc_mast_de.R:39`、`sc_pseudobulk_deseq2.R:35`、`sp_numbat.R:41`。`sc_mast_de.R` 先执行 `library(MAST)`（`:14-17`），本机缺 MAST 会先报错，下载只会发生在装了 MAST 的机器上，例如没有网络的 sandbox。`sc_pseudobulk_deseq2.R` 没有任何 Python 代码调用；试点 `pseudobulk_de` 走的 `_lib/pseudobulk.py` 用 CSV 交换（`:241-297`）。
- `install_skill_deps` 只装 pip 包，R 包只给出提示（`omicsclaw/skillenv/tool.py:135-136`、`:329-339`）。
- `run_cli` 用 `subprocess.Popen` 起 CLI，不新开会话（`_skills.py:428-431`），并用 `for line in process.stdout` 读到 EOF 才 `wait`（`:437-442`）。CLI 子进程与 kernel 同一个进程组。

#### 2.2.2 26 个 skill 的共性

- 9 个在计算里调用 R：sc-ambient-removal（SoupX）、sc-batch-integration（fastMNN、Seurat CCA/RPCA）、sc-cell-communication（CellChat、NicheNet）、sc-differential-abundance（`proportion_test_r`）、sc-doublet-detection（DoubletFinder、scDblFinder、scds）、sc-enrichment（clusterProfiler、`gsea_r`、`gsva_r`）、sc-in-silico-perturbation（scTenifoldKnk）、sc-pathway-scoring（AUCell）、sc-pseudotime（slingshot、monocle3）。8 个经 `RScriptRunner`；sc-in-silico-perturbation 直接 `subprocess.run(["Rscript", ...])`，并把 `R_LIBS_USER` 写死成 `~/R/x86_64-pc-linux-gnu-library/4.1`（`sc_in_silico_perturbation.py:354-362`），而环境是 R 4.3.3。没有一个用 rpy2。24 个主脚本有 `--r-enhanced` 参数，其中 17 个经 `_lib/viz/r` 的 `call_r_plot` 用 R 画图，另外 7 个接受这个参数却不做任何事；画图属于展示层，留在 CLI。
- 没有 skill 必须用 GPU。scvi/scanvi（sc-batch-integration）和 CellBender（sc-ambient-removal）能用 GPU，都有 CPU 回退。
- 依赖外部二进制的只有 sc-count（cellranger 缺、STAR 2.7.11b、simpleaf 0.24.0 但没设 `ALEVIN_FRY_HOME` 时每次调用都失败、kb_python 0.30.1）、sc-velocity-prep（velocyto 已装但导入时报 `undefined symbol: __log10_finite`；STAR）、sc-fastq-qc（FastQC 0.12.1、MultiQC 1.34，可选）。
- 两个环境都缺的 Python 后端：pertpy、sccoda、cnmf、SEACells、pyscenic、omicverse、cellbender、simba-bio。`rapids_singlecell` 还缺 scrublet、harmonypy、scanorama、bbknn、scvi-tools、scvelo、cellrank、palantir、pyVIA、arboreto、gseapy、liana、cellphonedb、igraph、leidenalg、loompy、decoupler，所以这批 skill 的测试、示例和 parity 都只能在 `OmicsClaw` 环境里跑。
- 运行时联网的：sc-enrichment 与 sc-pathway-scoring 的 `--gene-set-db` 经 `gseapy.get_library` 下载 Enrichr 库；CellPhoneDB 首次使用时下载 `ventolab/cellphonedb-data` v4.1.0（约 26.8 MB）。默认参数的 demo 都不联网。
- CLI 的 `--demo` 经 `_lib/io._demo_candidates` 只找仓库的 `data/` 和 `examples/`，不看 `OMICSCLAW_DEMO_DIR`（`skills/singlecell/_lib/io.py:252-270`），找不到就用 scanpy 下载；所以 CI 里任何起 CLI `--demo` 的测试都会重新下载 pbmc3k。
- 3 个现成 demo 都没有样本、供体或条件列，没有剪接与非剪接层，也没有 ATAC 数据。`pbmc3k_processed.X` 和 `pbmc68k_reduced.X` 是 z-scale 过的，对数标准化的矩阵在 `.raw` 里；好几个 skill 的 demo 直接在 scale 过的矩阵上算，结果没有生物学意义（§3.2 各条）。
- 主脚本里的作图大多经 `_lib/viz/*` 的 `save_figure` 直接写文件（`_lib/viz/core.py:51-60`）。试点的做法是在 `_api.py` 里另写返回 `Figure` 的简单函数（如 `sc-clustering/_api.py:204-230`），CLI 的画廊照旧。
- 26 个 `SKILL.md` 和 `references/output_contract.md` 的输出清单几乎都列了不会写出的文件。只有 `sc-integrate-cluster` 还提到已删除的 consensus。
- `_lib` 模块的顶层导入都只有 numpy、pandas、scanpy、anndata、scipy、sklearn 一类基础包，scrublet、harmonypy、scanorama、scvelo、liana 等后端都在函数体内导入（`grep` `_lib/qc.py`、`integration.py`、`stat_enrichment.py`、`differential_abundance.py`、`gene_programs.py`、`metacell.py`、`markers.py`、`trajectory.py`、`grn.py`、`perturbation.py`）。所以一个示例只需要它所调用方法的后端。

#### 2.2.3 `_lib` 的使用面

只被一个 skill 用的是 `ambient`、`differential_abundance`、`gene_programs`、`grn`、`markers`、`metacell`、`pseudoalign`、`pseudobulk`、`stat_enrichment`；`perturbation` 两个（sc-perturb、sc-perturb-prep）；`upstream` 四个（sc-count、sc-fastq-qc、sc-multi-count、sc-velocity-prep）；`trajectory` 三个（sc-pseudotime、sc-velocity、spatial-trajectory）。`adata_utils`、`io`、`export`、`preflight` 几乎每个 skill 都用。

#### 2.2.4 测试与 CI

- CI（`.github/workflows/eval.yml`）的 job1 只跑 `tests/` 下列出的目录（`:37-46`），不跑任何 `skills/*/tests`；job3 `skill-examples`（`:48-85`）装 `"scanpy[leiden]" umap-learn` 等，钉 `anndata==0.11.4`（本机 0.12.11），只预取 `pbmc3k_raw`、`pbmc3k_processed`，缓存键 `demo-data-pbmc3k-v1`，超时 30 分钟。0070 交付记录 §15 记下 job3 首跑 1 分 47 秒。job1 的 `ubuntu-latest` 镜像不带 R（如何核实第 6 条），`requires_r` 用例在那里都会跳过。
- `pyproject.toml:379` 的默认 `addopts` 排除 `slow`、`demo`、`eval`、`skill_example`；`testpaths`（`:380-407`）里单细胞只有 sc-fastq-qc、sc-count、sc-velocity-prep 三个 skill 的测试目录。根 `conftest.py:20-41` 把名字或夹具里带 "demo" 的 skill 测试自动标成 `demo`。marker `requires_r` 已注册（`pyproject.toml:411`）。审核在 OmicsClaw 环境统计：26 个 skill 的测试默认收集 88 条，其中 15 条会起 CLI 子进程（审核报告 §8）。
- `tests/sdk/notebook/test_skill_api_sections.py:17-20` 自动收录所有带 `_api.py` 的 skill，`:39-41` 只断言 5 个试点在内；`test_skill_examples.py:24-27` 自动收录所有 `examples/example_step.py`，每个示例超时 1800 s（`:44`）。
- parity：`tests/parity/snapshot.py` 的 `SCRIPTS`、`CASES` 只有 5 个试点（`:35-49`）；`extract` 遇到没有 `processed.h5ad` 的输出会跳过那一部分（`:118`）；`run_cli` 用 `subprocess.run`，不新开会话（`:71-77`）。`api_runs.py` 按 skill 写死调用。基线目录 `tests/parity/golden/` 被 `.gitignore:38` 忽略。
- 与这批 skill 相关的顶层测试和守卫：
  - `tests/test_scrna_method_contracts.py:35-115` 按路径加载 `sc_integrate.py`、`sc_doublet.py`、`sc_cell_communication.py`，对脚本里的 `integrate_scvi`、`integrate_scanvi`、`run_doubletfinder`、`run_scdblfinder`、`detect_doublets_doubletfinder`、`run_communication` 打桩或直接调用。
  - `tests/test_scrna_console_encoding.py:30-49` 要求 `skills/singlecell/scrna/` 下所有 `*.py` 的 `print` 字符串只含 ASCII。
  - `tests/test_output_ownership_contract.py` 禁止 skill 代码写 `README.md` 等 runner 文件（0070 交付记录 §15）。
  - `tests/skillenv/test_skill_requires_are_declared.py:110-121` 只扫描不以 `_` 开头的主脚本和它们直接导入的 `_lib` 模块，看不到 `_api.py`。`EXCEPTIONS`（`:39-46`）里有 `(sc-filter, scrublet)`、`(scatac-preprocessing, scrublet)`，前提是主脚本导入 `_lib/qc.py`。试点的薄壳仍导入 `_lib/qc`（`sc_qc.py:51`、`sc_preprocess.py:43`）。审核用探针把扫描扩到试点的 `_api.py`，只多出两条已在 `EXCEPTIONS` 里的命中。
  - `tests/sdk/test_r_script_paths.py:40-56` 断言 `sc_enrichment.py` 的 `R_SCRIPTS_DIR`、`R_SCRIPTS_PROJECT_DIR`，以及 `sc_pseudotime.py`、`sc_differential_abundance.py` 的 `R_SCRIPTS_DIR`。
  - `tests/sdk/test_sc_scripts_help.py:25-36` 跑 10 个单细胞 CLI 的 `--help`（标 `slow`）；`tests/sdk/test_help_probe.py:23`、`tests/sdk/test_bootstrap.py:86-88`、`tests/skillenv/test_dependencies_section.py:26` 都断言 89。
  - `tests/test_sc_ambient_removal.py`（3 条）、`tests/test_sc_standardize_input.py`（4 条）以子进程跑 CLI；`tests/test_sc_preflight.py`（35 条）测 `_lib/preflight.py`。
- 26 个 skill 自带的测试：sc-standardize-input、sc-ambient-removal、sc-grn 没有 `tests/` 目录；scatac-preprocessing 的 4 条全被标成 `demo`；sc-pseudotime 有 6 条测试直接 `grep` 脚本源码里的字符串，sc-cytotrace 的 6 条按路径从脚本导入内部函数，代码搬家后都要改指向。
- 审核在 `4bd83b1e` 上跑过本计划的 GUARDS 整组（§6）：803 passed、5 skipped、1 xpassed，63.5 s。

#### 2.2.5 已经失败或有危险的 skill 测试

改动之前就失败的静态测试（`rapids_singlecell` 环境，11 failed、21 passed）。CI 不跑它们，所以一直没人发现：

| skill | 失败的测试 | 原因 |
|---|---|---|
| sc-metacell | `test_methods_are_exposed` | 断言 `SKILL.md` 里有 "Current Methods"，正文没有 |
| sc-gene-programs | `test_methods_are_exposed` | 同上 |
| sc-differential-abundance | `test_methods_are_exposed` | 期望 `choices=["milo", "sccoda", "simple"]`，实际多一个 `proportion_test_r` |
| sc-enrichment | `test_methods_are_registered` | 期望方法表是 `{"ora","gsea"}`，实际 4 个 |
| sc-perturb、sc-perturb-prep | `test_skill_md_matrix_expectations` | 找 "normalized expression"、"raw counts" 等字样 |
| sc-in-silico-perturbation | 5 条 | 找的字样只在 `references/` 里 |

有危险的一条：sc-velocity 的 `test_velocity_from_velocity_prep_output`（`sc-velocity/tests/test_sc_velocity.py:80-87`）默认收集，只有 `skipif(not _has_scvelo())`，用不开新会话的 `subprocess.run` 跑 CLI。CLI 退出时 `killpg` 自己的进程组，在装了 scvelo 的 `OmicsClaw` 环境里会把 pytest 一起杀掉；上面的统计在没有 scvelo 的 `rapids_singlecell` 里跑，这条被跳过，所以没发现。M6 修好之前，在 `OmicsClaw` 环境跑 sc-velocity 的测试一律加 `--deselect` 去掉这条。

另外，`OmicsClaw` 环境里依赖缺失的 R 包的用例会被 `skipif` 跳过，例如 sc-pathway-scoring 的 `test_demo_mode`（`test_sc_pathway_scoring.py:19-25`、`:47`）。各期动手前在 HEAD 上跑一遍，把既有失败和跳过一起记下（§6）。

#### 2.2.6 eval

- 8 条 `skill_routing` 用例用的是 sc-qc、sc-clustering 的桩和 bulkrna-de 的 CLI fixture（`tests/evals/dataset/test_skill_routing.py`），与这 26 个 skill 无关。
- live eval 的种子里有两条涉及本批：`singlecell__batch_harmony`（`expected_args: {"--method": "harmony"}`，`tests/evals/fixtures/live_routing_seed.json:110`）和 `singlecell__velocity_route_noun`（`:125`）。`tests/evals/test_fixtures.py:87-104` 要求 `--method harmony` 或 `method="harmony"` 出现在 sc-batch-integration 的 `SKILL.md` 里。

### 2.3 对 0070 记录与任务说明的更正

1. 0070 §1.3 说"其余 skill 里有 11 个"调用 R。按代码，计算里调用 R 的是 9 个；把用 R 画图的也算上是 17 个（这 9 个都在其中）。
2. 0070 §3.16 的守卫表没有提到 `tests/skillenv/test_skill_requires_are_declared.py`。它不扫描 `_api.py`，函数库里新加的 `require(...)` 不会被核对；目前没有漏网的依赖，缺口是潜在的（M0-3 补）。
3. 任务说明列的三个可能需要 FASTQ 的 skill：sc-count、sc-fastq-qc 确实以 FASTQ 或 Cell Ranger 输出为输入；sc-multi-count 只合并多个 `.h5ad`（`sc_multi_count.py:93`），可以整体迁移。
4. 任务说明里"伪重复相关的 DE"指的方法（`sc-de.pseudobulk_de`）已在试点里迁移，本批不涉及；它走 CSV 交换，不受 basilisk 问题影响。

### 2.4 与论文计划的衔接

- 0072 pilot 的 double dipping 一类用 sc-markers。0072 记下的系统内不对称是"`sc-de` 的 SKILL.md 写了 pseudobulk，`sc-markers` 没提 double dipping"。代码核对：`sc-markers` 目录里搜不到 double dipping 一类字样；`SKILL.md:20-22` 把排序后的 marker 基因说成"as evidence for downstream annotation or interpretation"；`markers_top.csv` 按 `pvals_adj` 排序（`sc_markers.py:145-170`）。迁移只换形态，方法学内容不改，这条不对称照旧（Q7）。pilot 在 M1 合入后用它自己的 tag 冻结。
- 0073 的 pbmc3k 流程（QC、过滤、预处理、聚类）里只有 sc-filter 没有函数库，M1 补上。之后这条流程不再经过 `run_cli`，0073 的 C2（`skill_cli` 补记 git）对它就不需要了；C2 对仍只有 CLI 的 sc-count、sc-velocity-prep、sc-fastq-qc 仍然有用。C1（过期判定纳入 skill 代码哈希）的覆盖面随迁移变大，迁移后的每个 skill 都有 `skill_load.content_sha256` 可比。
- 方向 C 的 v1 要测批次混杂和富集背景集，对应 sc-batch-integration 和 sc-enrichment，所以它们排在 M1 之后的 M2。
- R 步骤不记 skill 调用。0073 的主张"每个结果能追到 skill 函数调用"在含 R 步骤的模块里只能追到步骤与解释器，论文写作时要注明。

---

## 3. 逐个 skill 的盘点

### 3.1 事实表

方法一栏是 `--method` 的选项，默认值写在最前，括号里是主脚本行号；R 一栏只算计算用的 R；测试一栏是"默认收集/总数"，CI 都不跑；demo 一栏是 `OmicsClaw` 环境里 `--demo` 的墙钟和退出码；最后一栏是第 2 版的处置与所在期。

| skill（主脚本行数） | 方法，默认在前 | R（计算） | 外部工具、大数据、联网 | 测试 | demo | 处置 |
|---|---|---|---|---|---|---|
| sc-filter（733） | 无 `--method`；阈值 `--min-genes 200`、`--max-mt-percent 20`、`--min-cells 3`、`--tissue` 预设、默认去双细胞（`:532-547`） | 无 | 无 | 1/3 | 9.6 s，0 | 迁移，M1 |
| sc-markers（442） | wilcoxon、t-test、logreg、cosg（`:94-99`） | 无 | 无 | 0/2 | 12.1 s，0 | 迁移，M1 |
| sc-batch-integration（1065） | harmony、scvi、scanvi、bbknn、fastmnn、seurat_cca、seurat_rpca、scanorama、simba（`:64-114`） | fastMNN、Seurat | simba 往 cwd 写 `graph0/`、`model/`（`:303-313`），未装 | 1/5 | 23.9 s，0 | 迁移，M2 |
| sc-enrichment（1526） | ora、gsea、gsea_r、gsva_r；`--engine auto` 在有 clusterProfiler 时走 R（`:133-154`、`:424-447`） | clusterProfiler、GSEA/GSVA 脚本 | `--gene-set-db` 下载 Enrichr 库 | 4/6 | 23.9 s，0（R 引擎） | 迁移，M2 |
| sc-integrate-cluster（297） | none、harmony、scanorama、scvi（`:205-207`） | 无 | 无 | 3/3 | 9.6 s，0 | 删除，M2 |
| sc-standardize-input（421） | 固定 `canonical_ann_data` | 无 | 无 | 无目录；顶层 4 条 | 4.4 s，0 | 迁移，M3 |
| sc-doublet-detection（939） | scrublet、doubletdetection、doubletfinder、scdblfinder、scds（`:83-109`） | DoubletFinder、scDblFinder、scds | 默认读取器首次触发 basilisk 下载 | 0/3 | 25.9 s，0 | 迁移，M3 |
| sc-ambient-removal（1046） | simple、cellbender、soupx（`:106-123`） | SoupX | CellBender 要原始 10x `.h5`，未装；SoupX 要原始与过滤后的 10x 目录 | 无目录；顶层 3 条 | 7.0 s，0 | 迁移，M3 |
| sc-pathway-scoring（1066） | aucell_r、score_genes_py、aucell_py（`:84-100`） | AUCell（未装） | `--gene-set-db` 下载 Enrichr 库 | 4/7 | 3.7 s，2（预检报缺 AUCell） | 迁移，M5 |
| sc-gene-programs（616） | cnmf（未装时回退 nmf）、nmf（`:89`、`:404-410`） | 无 | 无 | 1/1（已失败） | 4.1 s，0 | 迁移，M5 |
| sc-differential-abundance（888） | milo（缺 pertpy 时回退 milo_like）、sccoda、simple、proportion_test_r（`:533`） | `sc_proportion_test_r.R` | 无 | 1/1（已失败） | 16.7 s，0 | 迁移，M5 |
| sc-cell-communication（1565） | builtin、liana、cellphonedb、cellchat_r、nichenet_r（`:124-152`） | CellChat（加载失败）、NicheNet（未装） | CellPhoneDB 首次下载数据库；NicheNet 的两个 `.rds` 没有任何代码下载 | 4/4 | 6.1 s，0 | 迁移，M5 |
| sc-cytotrace（692） | cytotrace_simple | 无 | 无 | 6/6 | 5.4 s，0 | 迁移，M6 |
| sc-metacell（542） | seacells（未装时回退 kmeans）、kmeans（`:76`、`:328-333`） | 无 | 无 | 1/1（已失败） | 11.6 s，0 | 迁移，M6 |
| sc-pseudotime（1405） | dpt、palantir、via、cellrank、slingshot_r、monocle3_r（`:112-143`） | slingshot、monocle3（都未装） | 无 | 8/8 | 9.9 s，0（结果错误，§3.2） | 迁移，M6 |
| sc-velocity（931） | scvelo_stochastic、scvelo_dynamical、scvelo_steady_state（`:655-662`） | 无 | 无 | 1/3（§2.2.5） | 19.1 s，137（自杀，§3.2） | 迁移，M6 |
| sc-grn（1000） | 无 `--method`，看资源走 pySCENIC 或简化路径（`:781-799`） | 无 | cisTarget 数据库 1.32 GB、motif 表 103.6 MB，代码给的 feather URL 返回 404；pyscenic 未装；GRNBoost2 与 dask 2026.1.1 不兼容 | 无目录 | 24.2 s，0（相关性回退） | 迁移，M6 |
| sc-perturb-prep（427） | 固定 `mapping_tsv` | 无 | 无 | 7/7（1 条已失败） | 3.4 s，0 | 迁移，M7 |
| sc-in-silico-perturbation（719） | grn_ko、sctenifoldknk（`:88-94`） | scTenifoldKnk（未装，直接调 Rscript） | 无 | 14/14（5 条已失败） | 3.5 s，0 | 迁移，M7 |
| sc-drug-response（937） | simple_correlation、cadrres（`:85-96`、`:702`） | 无 | cadrres 要 omicverse 和模型 pickle，代码给的下载 URL 返回 404 | 17/22 | 17.6 s，0 | 迁移，M7 |
| sc-perturb（458） | mixscape（`:76`） | 无 | pertpy 未装 | 7/7（1 条已失败） | 3.5 s，1（缺 pertpy） | N1，M7 |
| sc-multi-count（530） | 固定 merge | 无 | 无 | 2/5 | 5.9 s，0 | 迁移，M8 |
| scatac-preprocessing（880） | tfidf_lsi（`:63-71`） | 无 | 无 | 0/4 | 18.1 s，0 | 迁移，M8 |
| sc-count（665） | cellranger、starsolo、simpleaf、kb_python（`:318-323`） | 无 | 四种比对工具和对应参考索引；`resources/singlecell/references/` 不在仓库里 | 4/8 | 6.2 s，0（只做标准化） | `CLI_ONLY`，M8 |
| sc-velocity-prep（711） | velocyto、starsolo（`:351`） | 无 | velocyto（坏）、STAR；GTF、STAR 索引、白名单 | 1/4 | 6.7 s，0 | `CLI_ONLY`，M8 |
| sc-fastq-qc（477） | 固定 fastqc（Python 采样器总是运行） | 无 | FastQC、MultiQC 可选 | 1/3 | 4.0 s，0 | `CLI_ONLY`，M8 |

### 3.2 各 skill 的要点与拟定函数

每条先写影响迁移的事实，再写拟定的 `_api.py` 公开函数（都另有 `run_info(adata, *, keep=True)`，不重复），最后写 parity 用例、示例数据和示例要 job3 装的包。函数清单是初稿，实施时以 parity 和示例为准微调。

#### sc-filter（M1，难度 S）

整个计算是一次 `_lib.qc.apply_threshold_filtering`（`_lib/qc.py:469-553`）。试点 `sc-preprocessing.preprocess` 内部也会过滤：`_prepare_input` 用 `min_genes`、`min_cells`、`max_mt_pct` 和去双细胞再调一次同一个函数（`sc-preprocessing/_api.py:325-331`），没有跳过的开关，参数名也不同（`max_mt_percent` 与 `max_mt_pct`）。先 sc-filter 再 preprocess，会按 preprocess 的默认阈值再筛一次：用户在 sc-filter 里选了更宽的阈值（例如线粒体 30%）时，preprocess 会按 20% 悄悄再去掉一批细胞，`min_cells` 在更少的细胞上重算，也可能多去掉一些基因。去双细胞只按上游已有的 `predicted_doublet` 或 `doublet_score` 列筛（`_lib/qc.py:530-549`），不会重跑 scrublet。M1 给 `preprocess` 加关键字参数 `apply_filters: bool = True`（细胞与基因过滤一起开关，默认行为不变），sc-filter 的 `SKILL.md` 写明随后调用 `preprocess(..., apply_filters=False)`。

`filter_stats["outliers_removed"]` 统计的是标了 `outlier` 的细胞，这些细胞并没有被去掉（`_lib/qc.py:527-528` 与 `:331-388`）。这个键在共享 `_lib` 里，试点 sc-preprocessing 和 scatac-preprocessing 也经它生成 `filter_summary`，所以只在 sc-filter 自己的 `_api.py` 里把它改名为 `outliers_flagged`（有意改动），`_lib` 不动。demo 数据没有 `outlier` 列，parity 用例碰不到这一点，由一条输入带 `outlier` 列的单元测试钉住。

函数：`filter_cells(adata, *, min_genes=200, max_genes=None, min_counts=None, max_counts=None, max_mt_percent=20.0, min_cells=3, tissue=None, remove_doublets=True, doublet_score_threshold=0.25)` 返回新的 AnnData；`filter_summary`、`filter_stats_table`、`filter_state_table(before, after)`、`tissue_presets()`、`filter_figure(before, after)`。parity：`--demo`；`--demo --tissue pbmc`。示例：`pbmc3k_raw` 经 `sc-qc.calculate_qc` 再 `filter_cells(tissue="pbmc")`，得到 2,638 个细胞，与 `pbmc3k_processed` 的 `obs_names` 完全相同（子 agent 与审核各自验证），可以直接断言。job3 不加包。

#### sc-markers（M1，难度 S）

wilcoxon、t-test、logreg 经 `_lib/markers.find_all_cluster_markers`（`_lib/markers.py:27-149`）：`rank_genes_groups(pts=True, use_raw=False)` 后用 `filter_rank_genes_groups` 过滤，过滤后为空或出错时静默退回未过滤的表（`:107-131`）。cosg 把 `pvals`、`pvals_adj` 填成 0.0（`:347-348`），`SKILL.md:63` 却说没有这两列。demo 在 scale 过的 X 上跑，过滤把所有行去掉，触发退回。函数：`find_markers(adata, *, groupby, method="wilcoxon", n_genes=None, min_in_group_fraction=0.25, min_fold_change=0.25, max_out_group_fraction=0.5, mu=1.0)`、`top_markers(table, *, n_top=10)`、`cluster_summary(table, *, n_top=10)`、`marker_dotplot_figure`。退回未过滤表的情况记进 `run_info`（`filter_fallback: true`）；cosg 的 p 值改为 NaN（有意改动）。`find_markers` 是纯函数，pilot 才能把它用在留出或拆分后的细胞上。方法学正文不加 double dipping 的提醒（Q7）。parity：`--demo`；`--demo --method t-test`。示例：`pbmc68k_reduced` 的 `.raw.to_adata()`，`groupby="bulk_labels"`。job3 不加包。

#### sc-batch-integration（M2，难度 M）

9 个后端；scvi、scanvi 接受 `random_state` 却从不使用（`_lib/integration.py:280`、`:437`）；harmony 默认重算 PCA（`:600-648`），PCA 维数超过 `min(n_obs, n_vars) - 1` 时 scanpy 会报错；demo 的批次标签是不设种子的随机数（`sc_integrate.py:917`）。函数：`integrate(adata, *, method="harmony", batch_key="batch", harmony_theta=2.0, n_pcs=50, n_latent=30, n_epochs=None, use_gpu=True, labels_key=None, bbknn_neighbors_within_batch=3, scanorama_knn=20, integration_features=2000, integration_pcs=30, random_state=0)`（只写 `obsm["X_<method>"]`，近邻与 UMAP 交给 `sc-clustering.cluster(use_rep=...)`）、`integration_metrics`、`batch_mixing_table`、`batch_sizes_table`。`random_state` 传给 scvi（`scvi.settings.seed`）和 harmony（有意改动：scvi 的结果从此可复现）。从 sc-integrate-cluster 搬一条经验：只在重算 PCA 会因数据太小而失败时，复用已有的、截断过的 `X_pca` 跑 harmony（`sc_integrate_cluster.py:130-135` 与 skill 目录里 `tests/test_sc_integrate_cluster.py:72` 的回归测试）；正常大小的数据结果不变，小数据上从报错变成能跑（有意改动）。simba 在临时目录里运行。`SKILL.md` 保留 `method="harmony"` 的写法（§2.2.6）。parity：demo 不确定，改用 parity 工具按固定种子从 `pbmc3k_raw` 生成的两批输入，用例为 harmony 与 scanorama。示例：同样的做法在步骤里生成两批，`method="harmony"`。job3：harmonypy 0.2.0 依赖 torch（`importlib.metadata`），CI 钉一个不依赖 torch 的旧版本（PyPI 上 0.0.x 系列，具体版本与 `_lib/integration.run_harmony_integration` 的兼容性未核实）；M2 实施时先在 `/tmp` 的 venv 里验证，不兼容就把示例改成 `method="scanorama"`（钉 `scanorama==1.7.4`，依赖 annoy、fbpca、geosketch、intervaltree），并在示例第一个 cell 写明原因。

#### sc-enrichment（M2，难度 L）

4 个方法乘 2 个引擎，3 个 R 脚本。本机的默认引擎走 R clusterProfiler；`GSEA(..., seed=TRUE)` 在新会话里失败并被 `tryCatch` 吞掉（DOSE 的 `GSEA_fgsea` 体内是 `if (seed) set.seed(.Random.seed)`；`sc_clusterprofiler_enrichment.R:97`），所以默认引擎下 `--method gsea` 恒返回 0 条。`gsea_r` 映射不到通路时静默换成用前 50 个基因造的 `DEMO_PATHWAY_*`（`sc_gsea_r.R:313-345`），`gsva_r` 用不设种子的 `sample()` 造随机基因集（`sc_gsva_r.R:135-148`）。函数：`rank_groups(adata, *, groupby, method="wilcoxon")`、`load_gene_sets(source, *, species="human")`（GMT/JSON 路径或 Enrichr 别名，后者联网；别名表照 `_lib/stat_enrichment.py:19-26` 原样，本批不与 sc-pathway-scoring 统一）、`demo_gene_sets(*, species="human")`、`marker_gene_sets(markers, ...)`、`ora(ranking, gene_sets, *, background=None, ...)`、`gsea(ranking, gene_sets, *, ..., random_state=123)`、`gsva(adata, gene_sets, *, groupby)`（R）、`top_terms`、`group_summary`、`top_terms_figure`。默认引擎改为 `python`（Q9，有意改动，CHANGELOG 写明 CLI 的默认结果会变）；R 端 GSEA 改 `seed=FALSE`，调用前 `set.seed(gsea_seed)`；两处伪造基因集的回退改为报错。`ora` 的 docstring 写清默认背景集是什么（方向 C v1 的富集背景集陷阱测这一点，正文照现有方法写，不加评价）。parity：`--demo --engine python`；`--demo --engine python --method gsea`。示例：`pbmc3k_processed.raw.to_adata()` 配 `demo_gene_sets()`，`ora`。job3：`ora` 是本地超几何检验，预计不用加包，M2 在干净 venv 里确认。

#### sc-integrate-cluster（M2，删除，Q1）

见 §4.1。

#### sc-standardize-input（M3，难度 S）

逻辑在 `_lib/adata_utils.canonicalize_singlecell_adata`（`adata_utils.py:392-441`）。`smart_load` 读 `.loom` 时把 `min_cells`、`min_genes` 传给不接受它们的 `import_loom_data`，直接 `TypeError`（`_lib/io.py:388-389` 与 `:168-172`）。函数库只收 AnnData，不提供读文件的函数：读 `.h5ad` 用 `read_input` 的默认读取器，读 10x 目录在步骤里传 `reader=sc.read_10x_mtx`，`SKILL.md` 的 "Use from a step" 写这两种。所以 `_api.py` 不依赖 `smart_load`，loom 的缺陷只记进 Gotchas（CLI 的 `.loom` 输入仍会失败）。函数：`standardize(adata, *, species="auto")`、`infer_species(adata)`。parity：`--demo`；`--demo --species human`。示例：在步骤里把 `pbmc3k_raw` 做成"X 已对数化、counts 在 layer 里"的对象再标准化。job3 不加包。

#### sc-doublet-detection（M3，难度 M）

Python 方法经 `_lib.qc.run_scrublet_detection`（`qc.py:592-676`），scrublet 的种子写死为 0，`--random-state` 没有传给它（`sc_doublet.py:787-792`）。R 方法经 `_run_r_doublet_script`（`:140-171`）与 3 个共享脚本，都用默认读取器。函数：`detect_doublets(adata, *, method="scrublet", expected_doublet_rate=0.06, threshold=None, batch_key=None, n_iters=10, standard_scaling=False, scds_mode="cxds", random_state=0)`（只标注 `obs`）、`doublet_calls_table`、`doublet_summary`、`group_summary_table`、`doublet_score_figure`。去除交给 sc-filter。`random_state` 传给 scrublet（默认 0，结果不变）。3 个 R 脚本改用 Matrix Market 加 CSV 交换（§5.1 第 5 条），Python 端用新模块 `_lib/r_exchange.py` 写出（有意改动，§5.11）。本机装了 DoubletFinder 和 scDblFinder，可以跑它们的 `requires_r` 测试；scds 未装，留给 owner 的机器。`SKILL.md` 的例子 `--method scdblfinder --threshold 0.4` 现在在预检处以退出码 2 结束（`_lib/preflight.py:919-922`），例子改掉。parity：`--demo`；`--demo --method doubletdetection`。示例：`pbmc3k_raw`，`method="scrublet"`。job3：`scrublet==0.2.3`（依赖 annoy、scikit-image）。

同一期把试点 sc-de 的 `sc_mast_de.R` 也改成 MTX/CSV 交换（`sc-de/_api.py:325-356` 的 Python 端同步改），有意改动，理由是消除装了 MAST、没有网络的环境（如 sandbox）第一次调用时必然发生的 basilisk 下载失败。本机缺 MAST，只能验证 Python 端写出的文件和 R 脚本能被 `parse()`；完整运行留给 owner 的机器。sc-de 的 parity 用例不含 MAST，不受影响。

#### sc-ambient-removal（M3，难度 M）

simple 是纯计算（`sc_ambient.py:865-900`）；soupx 要原始与过滤后的 10x 目录，失败时退回 simple（`:850-855`）；CellBender 要原始 `.h5`、写检查点、未装，未装时静默改用 simple（`:198-221`）。`SKILL.md:25` 说 soupx 走 rpy2，实际是 Rscript 子进程。函数：`remove_ambient(adata, *, contamination=0.05)`、`remove_ambient_soupx(adata, *, raw)`（在函数里临时导出 10x 目录）、`correction_summary`、`counts_comparison_table`、`ambient_profile_table`、`correction_figure`。CellBender 只留 CLI（大文件、GPU、写检查点）。parity：`--demo`；`--demo --contamination 0.1`。示例：`pbmc3k_raw`（没有空液滴，profile 只是细胞均值，示例里注明仅作演示）。job3 不加包。

#### sc-pathway-scoring（M5，难度 M）

默认 `aucell_r` 在本机缺 AUCell。演示用的基因集是前 60 个 `var_names` 切成 4 组（`:306-316`），没有生物学意义。它有自己的别名表（`:75-82`），小鼠 KEGG 是 `KEGG_2021_Mouse`（`:77`），`_lib/stat_enrichment.py:21` 是 `KEGG_2019_Mouse`；本批两边各用各的，不统一（应改 2）。函数：`score_gene_sets(adata, gene_sets, *, method="aucell_r", auc_max_rank=None, auc_threshold=0.05, ctrl_size=50, n_bins=25, random_state=42)`、`load_gene_sets(source, *, species="human")`（用本 skill 自己的别名表）、`attach_scores`、`gene_set_overlap`、`group_scores`、`top_pathways`、`score_distribution_figure`。parity：`--demo --method aucell_py`；`--demo --method score_genes_py`。示例：`pbmc3k_processed.raw.to_adata()`，用 sc-enrichment 同款的 PBMC 演示基因集（在步骤里写成 dict），`method="aucell_py"`。job3 不加包（M5 在干净 venv 里确认）。

#### sc-gene-programs（M5，难度 S 到 M）

cnmf 未装时回退 nmf；`SKILL.md:67` 把 `--n-iter` 说成重复次数，实际是 NMF 的最大迭代数；`_matrix_from_adata` 静默把负值截成 0（`_lib/gene_programs.py:49`）。函数：`find_programs(adata, *, method="cnmf", n_programs=6, n_iter=400, layer=None, top_genes=30, random_state=0)`、`program_weights`、`top_program_genes`、`program_correlation`、`usage_figure`。parity：`--demo --method nmf`；`--demo --method nmf --n-programs 4`。示例：`pbmc68k_reduced.raw.to_adata()`，`method="nmf"`。job3 不加包。

#### sc-differential-abundance（M5，难度 M）

缺 pertpy 时 milo 静默退回内部的 `milo_like`（`_lib/differential_abundance.py:244-256`）；simple 与 milo_like 在 2 对 2 个样本上做 Mann-Whitney，最小 p 值是 1/3，在 demo 上永远不显著；`proportion_test_r` 在细胞层面置换条件标签、忽略样本（scProportionTest 方法本身的做法）；`--min-count` 解析了却不用。函数：`composition(adata, *, sample_key, celltype_key, condition_key)`、`condition_proportions`、`test_abundance(adata, *, method="milo", ..., random_state=0)`、`proportion_figure`。`run_info` 记实际用的后端。方法学内容照旧，局限写进 Gotchas。parity：`--demo --method simple`；`--demo --method milo`（记下用的是 milo_like）。示例：生成器 demo `multisample_synthetic`（§5.4），断言能找回埋入的那个富集细胞类型。job3：如果 simple 路径要 statsmodels（多重检验），钉 `statsmodels==0.14.6`，M5 在干净 venv 里确认。

#### sc-cell-communication（M5，难度 L）

5 个后端；liana 的 `pvalue` 列取自 `specificity_rank`（`sc_cell_communication.py:618`）并被计入 `n_significant`，demo 报出 806 个"显著"（子 agent 的运行日志，审核未复跑）；liana 不管 `species`；CellPhoneDB 的 `debug_seed` 默认 -1（随机）且没有暴露；NicheNet 的两个资源文件没有任何代码下载（`:192-208` 是死代码）。`tests/test_scrna_method_contracts.py:92-115` 直接调用脚本里的 `run_communication(method="builtin")`。函数：`communicate(adata, *, method="builtin", cell_type_key="cell_type", species="human", ...)`、`builtin_lr`、`liana_lr(..., random_state=1337)`、`cellphonedb_lr(..., random_state=0)`、`cellchat_lr`（R）、`nichenet_ligands`（R）、`sender_receiver_summary`、`top_interactions`、`interaction_heatmap_figure`。liana 的 `specificity_rank` 改回原名，`pvalue` 置 NaN，不计入显著数；CellPhoneDB 的默认种子从随机改为 0（`random_state` 传给 `debug_seed`）。两条都是有意改动。parity：`--demo`；`--demo --method liana`。示例：`pbmc3k_processed.raw.to_adata()`，`cell_type_key="louvain"`，`method="builtin"`。job3 不加包（不装 liana）。

#### sc-cytotrace（M6，难度 S）

约 150 行 numpy，确定性。在 scale 过的 X 上用 `X > 0` 数检出基因（`sc_cytotrace.py:152-157`）；分数先做秩归一再分箱，6 个箱永远等分（`:228-246`）。函数：`cytotrace(adata, *, n_neighbors=30, layer=None)`、`potency_table`、`potency_composition`、`potency_figure`。`layer` 让调用者指定计数矩阵，默认行为不变；分箱方式写进 Gotchas。parity：`--demo`；`--demo --n-neighbors 15`。示例：`paul15`（§5.4），步骤里先做 log1p 与 PCA。job3 不加包。

#### sc-metacell（M6，难度 S 到 M）

SEACells 未装时静默改用 kmeans（`sc_metacell.py:328-333`），`--seed` 没有传给 SEACells；`SKILL.md` 说聚合求和，代码取均值（`_lib/metacell.py:61`）。函数：`metacells(adata, *, method="seacells", use_rep="X_pca", n_metacells=30, min_iter=10, max_iter=30, n_neighbors=15, n_pcs=20, random_state=0)`、`aggregate_metacells`、`metacell_summary`、`cell_to_metacell`、`size_distribution_figure`。回退按 §5.1 第 2 条记录。parity：`--demo --method kmeans`；`--demo --method kmeans --n-metacells 20`。示例：`pbmc3k_processed`，`method="kmeans"`。job3 不加包。

#### sc-pseudotime（M6，难度 L）

6 个后端，其中 2 个 R（本机都缺包），pyVIA 要在运行时打补丁（`_lib/trajectory.py:389-436`）。导入脚本时 `os.environ.setdefault("NUMBA_DISABLE_JIT", "1")`（`sc_pseudotime.py:15`）。`_candidate_reps` 优先用 `X_umap`（`:273-277`），demo 上 DPT 因此跑在不连通的 UMAP 近邻图上，子 agent 的运行里 2,638 个细胞有 1,022 个 pseudotime 为 inf（审核未复跑）；预检却声明用 `X_pca`（`_lib/preflight.py:1164-1192`）。monocle3 的预检用错了 tier（`r_dependency_manager.py:86-90` 不含 monocle3）。函数：`pseudotime(adata, *, method="dpt", cluster_key="leiden", use_rep=None, root_cluster=None, root_cell=None, end_clusters=None, n_neighbors=15, n_pcs=50, n_dcs=10, ..., random_state=20)`、`trajectory_genes`、`pseudotime_table`、`fate_probability_table`、`pseudotime_figure`。`_api.py` 不改环境变量；`use_rep` 的默认优先级改为 `X_pca`，与预检一致（有意改动）。`tests/sdk/test_r_script_paths.py:47-56` 改为检查 `_api.py`。parity：`--demo --use-rep X_pca`；`--demo --use-rep X_pca --method palantir`。示例：`paul15`，`method="dpt"`。job3 不加包（不装 palantir）。

#### sc-velocity（M6，难度 M）

主脚本结束时 `os.killpg(os.getpgid(os.getpid()), signal.SIGKILL)`（`sc_velocity.py:919-931`）。注释写明它要解决两件事：TensorFlow 线程在解释器退出时卡住；loky worker 继承了管道 fd，父进程读不到 EOF。`run_cli` 和 parity 工具都不新开会话，经它们运行时 kernel 或测试进程会被一起杀掉；只换成 `os._exit(0)` 又不够，worker 仍握着 stdout 管道，`run_cli` 的 `for line in process.stdout`（`_skills.py:437`）会一直等到 worker 退出。修法（M6-4）：
1. 动手前在 `/tmp` 写探针：`Popen` 读管道到 EOF 并带超时，分别跑旧脚本去掉 `killpg` 之后的版本和新薄壳，确认挂起能复现、修法能消除它。
2. 薄壳在 `main()` 之后先刷新输出，再用 joblib 自带的 loky 关掉 worker（`joblib.externals.loky.get_reusable_executor().shutdown(kill_workers=True)`；joblib 是 scanpy 的依赖，本机未单独装 loky），仍有子进程时用 psutil（OmicsClaw 环境有，7.2.2）逐个结束，然后 `os._exit(0)`，只结束自己。
3. 新测试：步骤里 `run_cli("sc-velocity", ..., timeout=...)` 按时返回，之后 kernel 仍在。测试将整个步骤运行器放进独立进程组，另设外层墙钟超时；超时后先取得测试的全部后代，再清理运行器、kernel 与 worker，并检查无残留。kernel 会另开 session，不能只杀运行器的进程组。`run_cli` 当前的定时器只结束 CLI 父进程（`_skills.py:433`），worker 若仍持有 stdout，读 EOF 仍会挂住；它的 `timeout` 不能作为这条测试唯一的超时保护。
在步骤里经 `load_skill` 调用 `velocity()` 不受这件事影响：步骤结束时执行器以 `shutdown_kernel(now=True)` 结束 kernel（0070 交付记录 §4）。

`scv.pp.filter_and_normalize` 原地删基因（`_lib/trajectory.py:751-765`），docstring 写明。`## Dependencies` 抄了 pseudotime 的 cellrank、palantir、pyVIA，改成只列 scvelo。函数：`velocity(adata, *, mode="stochastic", n_jobs=4, random_state=0)`（调用 `moments` 之前用给定种子显式建近邻）、`velocity_diagnostics`、`velocity_summary`、`velocity_cells_table`、`top_velocity_genes`、`stream_figure`。parity 工具录旧 CLI 时用 `start_new_session=True`，接受返回码 `-signal.SIGKILL`。parity：`--demo`；`--demo --mode steady_state`。示例：生成器 demo `velocity_simulation`（§5.4）。job3：`scvelo==0.3.4`（带 loompy）。

#### sc-grn（M6，难度 L）

没有 `--method`；完整 pySCENIC 要 3 个外部资源，本机 pyscenic 未装，GRNBoost2 与 dask 2026.1.1 不兼容，所以总是走相关性简化路径。简化路径无视用户给的 TF 列表，总用写死的 20 个 TF（`sc_grn.py:615`，子 agent 用真实 TF 列表复现：日志写 "Using 1 TFs from demo list"）；简化路径的 "AUC" 是靶基因平均表达（`:681-690`）。函数：`infer_adjacencies(adata, *, tfs, method="grnboost2", layer=None, random_state=42, n_top=50)`（`method` 还可取 `"correlation"`）、`prune_regulons(adjacencies, *, database_glob, motif_annotations, ...)`、`regulons_from_adjacencies`、`score_regulons(adata, regulons, *, method="aucell", random_state=42)`、`regulon_heatmap_figure`。无视用户 TF 列表的缺陷改为使用传入的列表（有意改动，只影响非 demo 路径）；"mean" 打分要明说不是 AUCell。parity：`--demo`；`--demo --allow-simplified-grn`（两者都走相关性路径，记录在案）。示例：`pbmc3k_processed.raw.to_adata()`，TF 列表写在步骤里，`method="correlation"`。job3 不加包（不装 arboreto）。

#### sc-perturb-prep（M7，难度 S）

纯 pandas。对照的识别是在大写后的向导名与靶基因上做子串匹配（`_lib/perturbation.py:209-210`），默认模式 `NT` 会把 WNT*、NTRK1、NT5E 的向导当成对照；`SKILL.md` 写的状态值（`single_guide`、`unassigned`）与代码（`assigned`、`control`、`multi_guide`）不符；`## Dependencies` 列了用不到的 pertpy。函数：`standardize_mapping(table, ...)`、`collapse_assignments(mapping, ...)`、`attach_assignments(adata, assignments, ...)`、`assignment_summary`、`perturbation_counts`、`perturbation_counts_figure`。对照匹配改为按分隔符切词后整词匹配（有意改动）。parity：`--demo`；`--demo --keep-multi-guide`。示例：生成器 demo `perturbseq_synthetic`，其中有一个 WNT 开头的诱饵向导，断言它没有被当成对照。job3 不加包。

#### sc-perturb（M7，整体迁移，N1 c）

唯一的方法 mixscape 要 pertpy。N1 c 的安装核验已在 Python 3.11 overlay 中用 `pertpy==1.0.3`、`scikit-learn==1.7.2` 跑通现有 CLI demo（§9.3）；依赖包含 JAX/Flax，所以示例进扩展 CI job。`--seed` 目前只给合成 demo 用，不传给 Mixscape。函数为 `mixscape(adata, *, pert_key="perturbation", control="NT", split_by="replicate", n_neighbors=20, logfc_threshold=0.25, pval_cutoff=0.05, perturbation_type="KO", random_state=0)`、`class_counts`、`global_class_counts`、`global_class_figure`。迁移前在同一 overlay 录两次默认及阈值变体的 CLI 基线，先确定结果是否稳定；随机种子的传递与行为差异写入有意改动。示例数据为 `perturbseq_synthetic`，须检查埋入的 KO 效应能够检出；当前 CLI demo 只能用于兼容性和 parity，不能据退出码 0 宣称算法检出了扰动。

#### sc-in-silico-perturbation（M7，难度 M）

`grn_ko` 把 KO 基因在相关矩阵里的行列置零（`:265-268`），其余每个基因的分数因此就是它与 KO 基因相关系数的绝对值，"p 值"是这个分数在基因间的 z 分数；demo 和 `pbmc3k_raw` 上 SPI1 敲除都只有 KO 基因本身显著。`--corr-threshold` 解析了却不用。scTenifoldKnk 由 f-string 拼出的 R 脚本直接经 Rscript 运行，不设种子，`R_LIBS_USER` 写死为 R 4.1 的路径（`:331-362`）。函数：`knockout_correlation(adata, *, ko_gene, n_top_genes=2000)` 承接 `grn_ko` 的计算，docstring 写明它给出与 KO 基因的相关排序，不模拟敲除的下游效应，表里不再有 p 值列；CLI 的 `--method grn_ko` 保留，输出同样去掉 p 值列（有意改动）；`sctenifoldknk(adata, *, ko_gene, ..., random_state=0)` 改用 skill 目录下的 `rscripts/sc_sctenifoldknk.R` 与 `RScriptRunner`，脚本里 `set.seed`；`top_perturbed_genes`、`perturbed_genes_figure`。parity：`--demo`（比较时排除 p 值列）；`--demo --n-top-genes 500`。示例：`pbmc3k_raw`，`ko_gene="SPI1"`。job3 不加包。

#### sc-drug-response（M7，难度 M）

`simple_correlation` 取每个簇里药物靶基因的平均表达（`:331-335`），靶基因集里混着 ABCB1、MGMT、ERCC1 这类耐药标志，分数越高越"敏感"的说法没有依据；`n_drugs` 不用；报告的免责声明写成 "SpatialClaw … spatial transcriptomics"（`:649`）。cadrres 要 omicverse 和模型文件，代码给的两个下载 URL 返回 404，模型来源未核实。函数：`score_drug_targets(adata, *, cluster_key=None, drug_targets=None)`、`builtin_drug_targets()`、`cadrres(adata, *, cluster_key, model_dir, drug_db="gdsc", n_drugs=10)`、`top_drugs`、`top_drugs_figure`。分数列改名为 `mean_target_expression`，`SKILL.md` 写明它不是敏感度预测；免责声明改成 `skills._sdk.report.DISCLAIMER` 的原文（两条都是有意改动）。parity：`--demo`；一个改变结果的 Python 变体，实施时选定。示例：`pbmc3k_processed.raw.to_adata()`。job3 不加包。

#### sc-multi-count（M8，难度 S）

只合并多个 `.h5ad`。输入已有 `obs["sample_id"]` 时，用户给的 `--sample-id` 只用于条码前缀、不进 `obs`（`:96-99`）；不检查是否是计数矩阵。函数：`merge_samples(adatas, *, sample_ids=None, sample_key="sample_id", join="outer")`、`per_sample_summary`、`barcode_metrics`、`sample_composition_figure`。它导入共享的 `_lib/upstream.py`，同期还要改那里的 FastQC 路径（§4.2），所以先录它的基线再改 `_lib`（§5.2）。parity：`--demo`；`--demo` 加两个 `--sample-id`。示例：在步骤里把 `pbmc3k_raw` 一分为二。job3 不加包。

#### scatac-preprocessing（M8，难度 M）

已有 `preprocess_tfidf_lsi`（`:205-272`），`TruncatedSVD(random_state=0)` 写死，CLI 不暴露种子。经 `smart_load` 读 Cell Ranger ATAC 的 `.h5` 时 `read_10x_h5` 默认 `gex_only=True`，特征数为 0，随即报 "Input matrix is empty"（`_lib/io.py:104`）；`## Dependencies` 列了用不到的 phate，漏了 igraph。函数：`preprocess(adata, *, min_peaks=200, min_cells=5, n_top_peaks=10000, tfidf_scale_factor=1e4, n_lsi=30, n_neighbors=15, leiden_resolution=0.8, random_state=0)`、`read_10x_peaks(path)`（读取器，`gex_only=False`，不改共享 `_lib/io.py`）、`qc_metrics_table`、`peak_summary`、`lsi_variance_table`、`cluster_summary`、`umap_figure`。parity：`--demo`；`--demo --n-lsi 20`。示例：生成器 demo `atac_synthetic`，断言聚出的簇与埋入的 3 个簇基本一致。job3 不加包（`scanpy[leiden]` 已带 igraph）。

#### sc-count、sc-velocity-prep、sc-fastq-qc（M8，`CLI_ONLY`）

见 §4.2。

### 3.3 处置与分期汇总

| 期 | skill | 处置 | 难度 | 估计（天） |
|---|---|---|---|---|
| M1 | sc-filter、sc-markers | 整体迁移 | S、S | 0.8、0.8 |
| M2 | sc-batch-integration、sc-enrichment | 整体迁移 | M、L | 1.6、1.8 |
| M2 | sc-integrate-cluster | 删除 | | 0.6 |
| M3 | sc-standardize-input、sc-doublet-detection、sc-ambient-removal | 整体迁移 | S、M、M | 0.6、1.3、1.0 |
| M3 | 双细胞 R 脚本、`sc_mast_de.R` | 改 MTX/CSV 交换 | | 0.5 |
| M5 | sc-pathway-scoring、sc-gene-programs、sc-differential-abundance、sc-cell-communication | 整体迁移 | M、S、M、L | 1.2、0.8、1.3、2.0 |
| M6 | sc-cytotrace、sc-metacell、sc-pseudotime、sc-velocity、sc-grn | 整体迁移 | S、S、L、M、L | 0.6、0.8、2.0、1.4、1.6 |
| M7 | sc-perturb-prep、sc-in-silico-perturbation、sc-drug-response | 整体迁移 | S、M、M | 0.6、1.0、1.0 |
| M7 | sc-perturb | 整体迁移；专用 overlay 和扩展 CI 示例 | M | 1.3 |
| M8 | sc-multi-count、scatac-preprocessing | 整体迁移 | S、M | 0.6、1.0 |
| M8 | sc-count、sc-velocity-prep、sc-fastq-qc | `CLI_ONLY`，只改 `SKILL.md`（sc-fastq-qc 另修路径） | | 0.3 × 3 |

难度按试点的经验估：S 约 0.6 至 0.8 天，M 约 1.0 至 1.4 天，L 约 1.6 至 2 天，都包括动手前在 HEAD 上跑测试、录基线、`_api.py`、薄壳、`SKILL.md`、示例和测试。试点约 1.1 天一个 skill，CLI 也是 800 到 1,700 行，与这批同一量级。偏乐观的是 L 级 skill 和 M0。

---

## 4. 不按函数库整体迁移的 skill

### 4.1 sc-integrate-cluster：删除

现状：
- `SKILL.md` 第 3 至 31 行和 61 至 89 行把自己写成 `sc-consensus-integration` 的成员，例如第 17 行 "**Role:** consensus member skill"，第 25 至 26 行 "You normally do **not** call this directly — the consensus planner fans it out across methods"。脚本的 docstring（第 3 至 28 行）和 3 个 `references/*.md` 也是这样。这些说法依赖的 consensus skill、`omicsclaw/ensemble`、`ScClusteringArtifactReader` 都已删除。
- 它不调用 sc-batch-integration 或 sc-clustering，而是导入 `_lib.integration`，自己再实现了一遍 scanorama 和 leiden/louvain（`sc_integrate_cluster.py:96-158`）。第 99 至 102 行的注释说 scanorama 的 `correct_scanpy` 不写 `obsm`，在已装的 scanorama 1.7.4 上不成立。
- 仓库里没有调用方：`tests/`、`omicsclaw/evals/`、`omicsclaw/` 都不引用它。
- 迁移后它在步骤里等于两次调用：`batch.integrate(adata, method=...)`，然后 `clustering.cluster(adata, use_rep="X_<method>", resolution=...)`。

删除。理由：它唯一的用途随 consensus 消失了；保留就要在路由上和两个已迁移的 skill 区分，模型选错的机会多一个，而它能做的事两次函数调用就能完成。删除前把唯一值得留的经验（小数据上 harmony 复用已有的 `X_pca`，见 §3.2 sc-batch-integration）移过去。

删除要改的地方：
- skill 目录。
- `skills/singlecell/INDEX.md`：第 11 行 "Skill count: 31" 与第 45 行，用 `OMICSCLAW_WRITE_SKILL_INDEX=1` 重生成。
- `llms.txt:28`（"31 skills"）与 `:49`。
- `OMICSCLAW.md:37`、`:61` 的 31，`:165` 的 89。
- `README.md:32`、`:145`，`README_zh-CN.md:31`、`:129` 的 89。
- `docs/core-features/agent-skills.md`：`:4`、`:21`、`:27`、`:38`、`:140`、`:220`、`:264`、`:324` 的 89，`:134` 的 31；`:115` 的"其余 85 个 skill 还只有 CLI"每期都会变，M9 一次改成最终的数。
- `docs/core-features/eval.md:367` 的 89。
- `tests/sdk/test_bootstrap.py:86-88`、`tests/sdk/test_help_probe.py:23`、`tests/skillenv/test_dependencies_section.py:26` 的 89 改 88。
- `CHANGELOG.md` 一条；0070 §1.3 的这一项随之关闭。

备选：b 是改写成"一次调用完成整合加聚类"的便利 skill；c 是并入 sc-batch-integration，作为 `integrate_and_cluster`（近邻与 leiden 可以复用 `_lib/dimred.py` 的 `build_neighbor_graph`、`cluster_leiden`）。b、c 都保留了一个与 sc-clustering 重叠的入口，路由上的歧义还在。

### 4.2 列入 `CLI_ONLY` 的三个 skill

sc-fastq-qc、sc-count、sc-velocity-prep 的主要工作是在 FASTQ 或 BAM 上运行外部工具，或采样 FASTQ 文件；产物是运行目录和表格，示例在 CI 里跑不到外部工具，函数库能放的只是 scanpy、scvelo 读取器外面的一层薄包装。本批三者都不加 `_api.py`，只改 `SKILL.md`，步骤里经 `run_cli` 调用；`test_skill_api_sections.py` 的 `CLI_ONLY` 名单逐个写明理由。

- sc-fastq-qc：表格全部来自 Python 采样器（`_lib/upstream.py:390-464`），FastQC 和 MultiQC 只是可选地跑一遍，产物不被解析。`SKILL.md` 按事实改写：demo 是合成表格而不是合成 FASTQ；表格总是来自采样；状态在 `figures/manifest.json`；多样本目录要给 `--sample`。修一个缺陷：FastQC 以 `artifacts/` 为 cwd 运行，却拿到未解析的相对输入路径，打印 "Skipping ... didn't exist" 后退出码 0，`result.json` 仍写 `fastqc_used: true`（`_lib/upstream.py:549-557`）；修法是拼命令之前把输入路径解析成绝对路径，加一条单元测试（有意改动）。这一行在共享的 `_lib/upstream.py` 里，导入它的 4 个 skill 的测试都要跑，sc-multi-count 的基线要在改之前录好（§5.2）。
- sc-count：`SKILL.md` 改正 demo 的说法（demo 只把 `pbmc3k_raw` 标准化，不计数）、后端名 `kb_python`、输出清单；Gotchas 写明 simpleaf 要设 `ALEVIN_FRY_HOME`、参考索引的自动探测目录 `resources/singlecell/references/` 不在仓库里。
- sc-velocity-prep：`SKILL.md` 改正 demo 的说法（demo 是按比例缩放的 `pbmc3k_raw`，没有速度信号）、`threads` 的默认值、`kb-python` 标签、输出清单；Gotchas 写明 `--base-h5ad` 合并时把 X 一律标成 `raw_counts`、覆盖 `.raw`、用剪接总数替换 `layers["counts"]`（`sc_velocity_prep.py:501-513`），以及本机 velocyto 导入失败。

三者的 `SKILL.md` 开头都写 "Use from a step: `run_cli("<skill>", "--input", <path>, ..., inputs=[<path>])`"。`skills/bulkrna/bulkrna-read-qc` 有自己的 FASTQ 解析器（`bulkrna_read_qc.py:49`、`:73`），两者合并属于 bulkrna 的范围。

### 4.3 sc-perturb 已纳入整体迁移

N1 c 已确定它在 M7 迁移，见 §3.2 与 §9.3；它不属于 `CLI_ONLY`。

---

## 5. 设计

### 5.1 `_api.py` 的约定

试点的规则全部沿用（0070 §3.13.2、`templates/skill/README.md` 的 "The function library" 一节）：只做计算；第一个参数是数据对象，其余只按关键字传，默认值等于 CLI 的默认值；表格返回 `DataFrame`，图返回 `Figure`；`__all__` 列全公开函数，每个都有 docstring；运行诊断经 `adata.uns` 里的 JSON 字符串和 `run_info` 读回；只 import 本域 `_lib` 和 `skills._sdk`；CLI 用 `load_skill(SKILL_NAME)` 取自己的函数库。新情况补 8 条，M0 写进模板 README：

1. 可选后端在函数体内导入。`load_skill` 导入整个 `_api.py`，顶层只能导入 skill 的基础依赖（anndata、numpy、pandas、scanpy、scipy）。scvi、liana、scvelo 这类后端放进各自方法的函数体，缺包时抛 `ImportError`，消息写包名并提示可以用 `install_skill_deps`。
2. 方法回退。回退到另一个真实方法可以，但要在 `run_info` 里记 `requested_method`、`executed_method`、`fallback_reason`，并打一行警告，与 sc-cell-annotation 一致。回退到伪造或占位的数据（合成基因集、随机基因集、写死的 TF 列表代替用户输入）不允许，一律报错。CLI 薄壳可以保留面向用户的回退：捕获函数库的错误、改调另一个方法，并照旧写进 `result.json`。
3. 读取器函数。名为 `read_*`、第一个参数是 `Path` 的函数可以读文件，但不写；docstring 写明 "pass it as `reader=` to `read_input`"，输入因此经 `read_input` 记账。本批只有 scatac 的 `read_10x_peaks` 一个。外部工具的运行不进 `_api.py`。
4. 种子。随机方法都有 `random_state`，默认值等于 CLI 原来的种子；CLI 原来没有种子的，默认 0。后端能接受种子的都传进去（例如 CellPhoneDB 的 `debug_seed`、scvi 的 `scvi.settings.seed`），由此改变结果的列进有意改动；不接受的，docstring 写明 "results vary between runs"，parity 不录这个方法。
5. R 方法沿用试点：Python 函数在 `tempfile` 临时目录里经 `RScriptRunner` 调 R 脚本。M3 的三个双细胞脚本与 `sc_mast_de.R` 改用 Matrix Market 加 CSV：Python 端用新模块 `skills/singlecell/_lib/r_exchange.py` 把计数矩阵写成 `matrix.mtx`、`barcodes.tsv`、`features.tsv`，把需要的 `obs` 列写成 `obs.csv`；R 端用 `Matrix::readMM` 和 `read.csv` 读回，自己组装 Seurat 或 SingleCellExperiment 对象。其余现有桥接保留原格式，包括 M2 整合的 H5AD 交换和 M7 scTenifoldKnk 的 CSV 交换；对应的 R 包要求与验证限制记入交付记录。新增的数据交换按需要选择 CSV 或 Matrix Market，不引入新的 `readH5AD` 调用。新写的 R 脚本放 skill 目录下的 `rscripts/`（先例：sc-enrichment、sc-pathway-scoring），不加进 `skills/_sdk/r_scripts/`，那里的文件名集合是冻结的。
6. 不在导入时改全局状态。sc-pseudotime 导入时设 `NUMBA_DISABLE_JIT` 这类代码只留在 CLI 薄壳里。
7. 图。每个 `_api.py` 给 1 到 3 个返回 `Figure` 的函数，覆盖最常用的图，在 `_api.py` 里直接写（试点 `sc-clustering/_api.py:204-230` 的做法）；CLI 的画廊照旧用 `_lib/viz`。
8. 输入矩阵。docstring 写明函数读哪个矩阵（`X`、`layers["counts"]`、`.raw`）。示例用 `pbmc3k_processed` 时先 `adata.raw.to_adata()` 取对数标准化矩阵。`print` 的字符串只用 ASCII（`tests/test_scrna_console_encoding.py`）。

### 5.2 `_lib` 的取舍

- 本批不搬移、不删除现有的 `_lib` 代码。只被一个 skill 用的模块（§2.2.3）按 D2 本该归到 skill 里，但搬家没有用户可见的收益，还要过全域回归；它们列进交付记录，留给以后的清理。
- 新的跨 skill 积木只追加。本批只加 `_lib/r_exchange.py`（sc-doublet-detection 与试点 sc-de 共用）。基因集加载不提到 `_lib`，两个 skill 的别名表也不统一（应改 2）。
- 共享 `_lib` 里的缺陷只在迁移的 skill 确实需要时修，并跑所有导入该模块的 skill 的测试。本批只修一处：`_lib/upstream.py` 的 FastQC 相对路径（§4.2）。`smart_load` 读 `.loom` 和 10x ATAC 的 `gex_only` 两个缺陷不修：前者记进 sc-standardize-input 的 Gotchas，后者由 scatac 的 `read_10x_peaks` 绕开。`outliers_removed` 的改名放在 sc-filter 自己的代码里，不动 `_lib/qc.py`。
- 改共享 `_lib` 之前，先给导入该模块、尚未迁移的 skill 录好 parity 基线，否则它们之后录到的"旧 CLI 基线"已经包含这次改动（应改 11）。按现在的分期，受影响的只有 M8：先录 sc-multi-count 的基线，再改 `_lib/upstream.py`。
- `_api.py` 之间不互相 import。sc-markers 和 sc-de 都包一层 `rank_genes_groups`，但过滤与排序不同，各自保留。

### 5.3 `## API` 段与一致性测试

- `tests/sdk/notebook/test_skill_api_sections.py` 已经自动收录所有 `_api.py`，生成器和一致性检查不用改。
- 把 `:39-41` 的"5 个试点都有函数库"改成两张名单：`CLI_ONLY`（只留 CLI 的 skill 及理由：sc-fastq-qc、sc-count、sc-velocity-prep）和 `PENDING_MIGRATION`（M0 时有 23 个，包括 M7 的 sc-perturb 和 M2 才删除的 sc-integrate-cluster；每期删去本期完成或删除的，M8 结束时为空并删除）。新测试：单细胞每个带 `SKILL.md` 的 skill，要么有 `_api.py`，要么在两张名单之一；名单里的 skill 不能有 `_api.py`，而且都要真实存在（防 M2 删除 sc-integrate-cluster 后留下残项）。这是 G14。

### 5.4 示例步骤、demo 数据与 CI

示例的写法同 0070 §3.13.5：`load_demo` 取数据，调 1 到 3 个本 skill 的函数，`write_output`，用 `assert` 或 `checks` 检查。gate 示例只用轻依赖的 Python 方法，不用 R 方法，也不用本机缺的后端；sc-perturb 用专用 overlay 和扩展 CI job。§3.2 每条写了示例用的方法和要装的包。

#### demo 注册表

`DEMOS` 保留现有的 `download` 写法（指 `scanpy.datasets` 的函数名，`_io.py:25-41`、`:314-328`），只新增一种 `generator`：

- 下载型新加 `paul15`（`"download": "paul15"`，10,297,693 字节，2,730 个细胞，造血前体，带 `paul15_clusters`），给 sc-cytotrace、sc-pseudotime 的示例用。许可在代码与 `references/` 里都找不到，未核实；M6 之前由 owner 确认，不行就改用 `pbmc3k_processed`（只能演示调用）。
- 生成器型放在新文件 `skills/_sdk/notebook/_demos.py`，固定种子，只用 numpy、anndata（`velocity_simulation` 例外，调 `scvelo.datasets.simulation`，函数体内导入）。`load_demo` 找不到文件时调用生成器，把结果写成 demo 缓存目录里的 `<name>.h5ad`，再和下载型一样读文件、记 `input` 的 sha256（应改 5）；文件已在就不再生成，免得 HDF5 里的时间戳让同样的数据得到不同的哈希（未核实是否会变，按会变处理）。

| 生成器 | 内容 | 埋入的已知结构，示例断言它 | 用在 |
|---|---|---|---|
| `multisample_synthetic` | 两个条件各 4 个样本、3 种细胞类型的计数 | 一种细胞类型在一个条件里的比例提高到约 3 倍 | sc-differential-abundance |
| `perturbseq_synthetic` | NT 加两个 KO、两个重复的计数，`uns` 里放向导映射表 | 一个 KO 让一组靶基因表达下降；一个 WNT 开头的诱饵向导 | sc-perturb-prep、sc-perturb |
| `atac_synthetic` | 180 个细胞乘 2,000 个峰（仿 `scatac_preprocessing.py:727-765`） | 3 个簇各有一组特异峰 | scatac-preprocessing |
| `velocity_simulation` | `scvelo.datasets.simulation(random_seed=0)`，带剪接与非剪接层 | 模拟的动力学方向 | sc-velocity |

生成器放在 `_sdk`，不复用 `_lib` 里现成的 demo 生成器：B5 不许 `_sdk` import `skills.singlecell._lib`，按字符串动态导入又会绕过这条守卫。代价是几十行的小函数与 CLI 的 `--demo` 数据不同；示例不参与 parity，没有影响。`reference` 打印 `DEMOS` 时一并给出是下载型还是生成器型。

#### CI job3

- gate job（现有的 `skill-examples`）只装示例实际用到的包，并钉版本。按 §3.2，各期要加的只有：M2 的 harmonypy 旧版（或 scanorama 1.7.4），M3 的 scrublet 0.2.3，M5 视情况加 statsmodels 0.14.6，M6 的 scvelo 0.3.4。其余示例只用 scanpy。每期在干净的 venv 里跑一遍本期示例，确认包列表。不装 torch、jax、liana、palantir、arboreto、pertpy、cellphonedb 和 R 包。
- CI 钉的是 `anndata==0.11.4`，本机是 0.12.11；示例在本机验证，CI 首跑是对 0.11.4 的检查（R14）。
- M7 增加扩展 job `skill-examples-extended`，用 marker 将 sc-perturb 的真实示例与 gate job 分开。它装 `pertpy==1.0.3`、`scikit-learn==1.7.2` 及解析报告确定的依赖约束，保持 `anndata==0.11.4`；只使用 CPU，不额外安装 JAX/CUDA extras。该 job 每个 PR 都实际运行，但不设为合并 gate；失败须出现在 CI 结果中，不能用缺包 skip 代替示例。blitzgsea 需要从 sdist 构建 wheel，开发核验及 CI 使用 pip 的隔离构建；这不是线上 `install_skill_deps` 的 wheels-only 路径。
- skill 自带的测试只跑不起 CLI 的用例（Q12）：M0 注册 marker `cli_subprocess`，各期给本期 skill 里起 CLI 子进程的用例打上它（M0 先给 5 个试点的打）；job3 加一步 `pytest <已迁移 skill 的 tests 目录> -m "not demo and not slow and not cli_subprocess"`。这样 CI 不会因为 CLI 的 `--demo` 重新下载 pbmc3k（§2.2.2），也碰不到 sc-velocity 那条会杀进程组的用例。
- 缓存键改为 `demo-data-v2`（M6 加 paul15 时），预取步骤加上 paul15；生成器型不用预取。
- 时间预算：0070 首跑 1 分 47 秒（5 个示例）。本机探针里 CLI 的 demo 是 3 到 26 s，估计每个示例 5 到 20 s。每期的 PR 首跑时，把 job3 的安装耗时和运行耗时记进交付记录；gate job 整体超过 15 分钟就拆分（按期拆成矩阵，或把最慢的示例移进扩展 job）。
- M4 在 job3 加 R：`sudo apt-get update && sudo apt-get install -y --no-install-recommends r-base-core`，然后跑 `-m requires_r tests/sdk/notebook/test_rscript.py`（Q3）。`ubuntu-latest` 当前镜像不带 R（如何核实第 6 条），所以 job1 里的 `requires_r` 用例都会跳过；以后镜像若自带 R，job1 会跑到这些用例，它们只用 base R，照样能过，届时 job3 的安装步骤可以去掉。apt 装到的 R 版本未核实，首跑时记下。

这几条在防线账里是 G16 至 G18。

### 5.5 parity 基线

做法同 0070 §3.13.6，补下面几处（M0-1 实现）：

- `tests/parity/snapshot.py` 的 `SCRIPTS`、`CASES` 改成每个 skill 一项的注册表，每个用例可以带 `exclude`（因有意改动而不比较的列或文件，附理由）和 `input`（由工具按固定种子生成的输入文件，用于 demo 本身不确定的 skill，如 sc-batch-integration）。`extract` 本来就能处理没有 `processed.h5ad` 的输出（`snapshot.py:118`），不用改。CLI 子进程以 `start_new_session=True` 运行，旧版 sc-velocity 的 `killpg` 因此只杀它自己。仅录制旧 sc-velocity 基线时，可以接受 `-signal.SIGKILL`，并须核对本次新输出中的 `result.json`、`processed.h5ad` 与预期表格均完整。其余录制及全部迁移后的 CLI 比较一律要求返回码 0，避免把 OOM 或其他崩溃记为成功。
- `test_sc_pilot_parity.py` 改名为 `test_sc_parity.py`，`api_runs.py` 按注册表分派。
- 每个用例用旧代码录两次。两次不一致的，标成"不确定"，只比较结构（列名、行数、标签集合），并在交付记录里写明原因。
- 不录基线的方法：R 方法；本机缺后端的方法（sccoda、cnmf、SEACells、pyscenic、omicverse、cellbender、simba）；后端不接受种子的方法。它们由单元测试覆盖，在 owner 机器上补测。sc-perturb 用 N1 c 的 overlay 录两次，按实际稳定性选择逐值或结构比较。
- 每个 skill 的用例见 §3.2。默认方法在本机会走 R 或缺后端时，"默认"用例改用显式参数走能跑的 Python 路径（sc-enrichment 的 `--engine python`、sc-pathway-scoring 的 `--method aucell_py`、sc-metacell 的 `--method kmeans`、sc-gene-programs 的 `--method nmf`）。
- 一致的标准不变：分类标签按 `obs_name` 逐值相等，整数逐值相等，浮点 rtol 1e-6，图只比文件名。sc-pseudotime 的 CLI 导入时关掉 numba JIT，函数库不关；函数库一侧的比较如出现浮点差异，先查是否来自 JIT，再决定放宽到 1e-5 并写明。
- 基线录在 `OmicsClaw` 环境，存 `tests/parity/golden/`，不提交，不进 CI。

### 5.6 R 步骤（M4）

#### 5.6.1 为什么做，以及 skill 的 R 方法怎么用

skill 的 R 方法沿用试点的做法：`_api.py` 里的 Python 函数经 `RScriptRunner` 调 R 脚本（例如 `sc-de._run_de_mast`、`sc-cell-annotation.annotate_singler`）。这批 9 个调用 R 的 skill 都这样迁移，`## API` 段、AST 一致性测试、eval 的桩和 `stub_target_missing`、记账里带参数的 `skill_call` 都照常工作，所以没有哪个迁移期依赖 R 步骤。

R 步骤给 agent 自己写的 R 代码用：某个方法只有 R 实现、没有 skill 函数覆盖（例如用 Seurat 的 `FindMarkers` 交叉核对），或者用户要求用 R。要用 skill 的 R 方法，就在 Python 步骤里调用它的函数；不要在 R 步骤里 `system2("Rscript", ...)` 直接跑 skill 的 R 脚本，那样调用不会被记账，也绕过了函数库的参数检查。契约写明这一点（§5.6.8）。

不给 skill 写 `_api.R`：那样要另做一个从 roxygen 注释生成 API 段的生成器、R 端的记账代理、R 端的 eval 桩，每个方法还会有两份实现，而本批没有一个 skill 需要它。

M4 排在第 4 期的理由：没有迁移期依赖它（Q2 a）；论文要用的 skill（M1、M2）应先合入；M3 定下 R 方法的 MTX/CSV 交换格式，R 步骤的契约与 `reference` 直接沿用；排在 M5 至 M8 之前，后面几期手动走查时还能顺带用到它，端到端（M9）之前有时间修问题。

#### 5.6.2 文件与命名

- 步骤文件名：`<k>[v]_<name>.R`，只认大写 `.R`。`LAYOUT["step_file"]` 改为 `^(\d{2})([a-z]?)_([a-z0-9][a-z0-9_]*)\.(py|R)$`。
- validate 步骤只能是 Python（`checks` 和审查摘要的检查函数识别都是 Python 的）；`<k>_validate.R` 报错。
- 同一个模块里不能有同 stem 的 `.py` 和 `.R`：记账目录 `runs/<stem>/`、`notebooks/<stem>.ipynb`、`logs/<stem>.log` 都按 stem 命名，会互相覆盖。
- 以上由新的 `Module.layout_problems()` 检出，`run` 和 `replay` 以退出码 2 列出全部问题，`status` 也列出（G10）。小写 `.r` 文件同样列为问题。
- 格式：percent 子集照旧（`# %%`、`# %% [markdown]`），因为 `#` 也是 R 的注释符。`_percent.parse_cells(text, *, language)` 对 R 跳过 Python 的语法与魔法行检查；R 的语法错误由驱动在运行时报出（报出错的 cell）。

#### 5.6.3 R 端的两个函数

新文件 `skills/_sdk/notebook/step.R`，只用 base R 加 `utils`、`grDevices`、`tools`；`Matrix`、`ggplot2` 只在需要时 `requireNamespace`。步骤的第一个代码 cell 显式加载它，执行器不往代码里注入任何东西（D9）：

```r
source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
counts <- read_input("results/02_export/intermediate/counts/matrix.mtx")
write_output(markers, "tables/seurat_markers.csv")
```

- 步骤上下文：`OMICSCLAW_STEP_FILE`（执行器设）或 `commandArgs()` 里的 `--file=`（单独运行时）；课题根是 `analysis/` 的父目录，与 Python 相同。
- `read_input(path, reader = NULL)`：路径相对课题根；文件不存在时报错；在 `OMICSCLAW_STEP_IO` 指向的文件里追加一行 `input<TAB><绝对路径><TAB>read_input`。默认读取器按后缀：`.csv` 用 `read.csv(check.names = FALSE)`，`.tsv` 用 `read.delim`，`.rds` 用 `readRDS`，`.mtx` 用 `Matrix::readMM`，`.txt`、`.md` 读成字符串，目录和其他后缀返回路径。`.h5ad` 不提供默认读取器，报错提示"在 Python 步骤里写成 Matrix Market 加 CSV，或传 `reader =`"。
- `write_output(obj, path, writer = NULL)`：路径规则与 Python 相同（第一段是 4 个输出目录之一，不许绝对路径和 `..`）；模块冻结时报错（读 manifest 里的 `"frozen": true`）；先写同目录的临时文件再 `file.rename`；追加一行 `output<TAB><相对模块 results 的路径><TAB><第一段>`。默认写法：数据框或矩阵配 `.csv`、`.tsv`；任意对象配 `.rds`；稀疏矩阵配 `.mtx`；ggplot 对象配 `.png`、`.pdf`、`.svg`，用 `ggsave(dpi = 150)`；一个无参函数配图片后缀时打开设备、调用它、关闭设备（不需要 ggplot2，CI 的 r-base-core 不带它，PNG 测试走这条路）；字符串配 `.txt`、`.md`；其余报错并提示用 `writer =`。返回写出的路径。
- 不提供 `load_skill`、`run_cli`、`load_demo` 和 `checks`。
- 单独运行：`OMICSCLAW_SDK_DIR=<checkout>/skills/_sdk Rscript analysis/<NN_slug>/<step>.R`（从课题根）。这时没有 `OMICSCLAW_STEP_IO`，两个函数照常工作、不记账，第一次调用时往 stderr 打一行提示，与 Python 一致。模块 README 模板加上这条命令。

R 端只登记路径，哈希、`outside_contract` 判定和记账事件都由执行器在 Rscript 退出后用 Python 补记（§5.6.5）。哈希规则和契约判定因此只有 `_hashing.py`、`_io.outside_contract` 一份实现，R 端也不需要 jsonlite 或 digest。代价是输入的哈希取的是步骤结束时的内容；步骤改写了它读过的文件时，`output` 事件照样记下最后写入的哈希，与 Python 的处理（0070 交付记录偏差 2）一致。

#### 5.6.4 执行：`RscriptRunner` 与驱动

`skills/_sdk/notebook/_runners.py` 新增 `RscriptRunner`，实现 `StepRunner`：

1. 把 notebook 的代码 cell 依次写成临时目录里的 `cell_001.R`、`cell_002.R`……，记下每个文件对应的 notebook cell 序号。
2. 运行 `[rscript, "--no-init-file", "--no-save", "--no-restore", <_rdriver.R>, <临时目录>]`，cwd 为课题根，`start_new_session=True`，stdout 与 stderr 合并。Rscript 用 `_preferred_rscript_executable()` 找（不改它，所有领域的 R 调用照旧）。环境：当前环境，加 `OMICSCLAW_STEP_FILE`、`OMICSCLAW_STEP_IO`、`OMICSCLAW_SDK_DIR`；`R_LIBS_USER` 只在 `<prefix>/lib/R/omicsclaw-library` 已存在时把它放在最前，`RETICULATE_PYTHON` 与 `_build_r_env` 相同。不调用 `_build_r_env`，因为它会 `mkdir`（`r_script_runner.py:349`），只读的 sandbox 镜像里会失败。
3. 驱动 `skills/_sdk/notebook/_rdriver.R`（约 30 行，只用 base R）：`grDevices::pdf(NULL)`，避免在课题根留下 `Rplots.pdf`；`options(warn = 1)`，警告当场打印在所属 cell 里；对每个 cell 先打印一行标记 `##omicsclaw-cell <i>##`，再 `source(cell, local = globalenv(), print.eval = TRUE, echo = FALSE)`；出错时把 cell 序号、条件类名和消息写进 `error.tsv`，以状态 1 退出；正常结束或出错退出前，把 `R.version.string` 和 `loadedNamespaces()` 的版本写进 `session.tsv`。
4. Python 端按标记把输出切到各 cell 的 `stream` 输出里；有 `error.tsv` 时给出错的 cell 加一个 `error` 输出（`ename` 是 R 的条件类名，`evalue` 是消息，不带调用栈）。
5. `kill()` 对 Rscript 的进程组发 SIGKILL，看门狗（`_watchdog.py`）不用改。

调用栈裁剪和语法错误行号换算（审核第 7 节的砍减）以后再做；出错时 agent 看得到出错的 cell 序号、消息，以及该 cell 之前的全部输出。

探针（`/tmp/rprobe`）验证过 2 至 4 步：3 个 cell，第 2 个 `stop()`；输出按标记切开，可见值被打印，stderr 的 `message()` 落在所属 cell，错误写出 cell 序号、类名和消息，第 3 个 cell 没有运行，课题目录里没有 `Rplots.pdf`，base R 的整次运行 0.22 s。

#### 5.6.5 执行器、记账与 manifest

- `_executor.py`：删掉两处 R 拒绝（`:272-275`、`:339-341`）；`execute_step` 按后缀选 runner（`runners: Mapping[str, StepRunner]`，测试可注入两个假 runner）；`run_start.kind` 取 `"python"` 或 `"r"`；`format_step` 的表头对 R 步骤打印 `Rscript=<路径> (R <版本>)`（现在固定打印 `python=`，`:86`）。R 步骤结束后、写 `run_end` 之前，持有 `_watchdog.ACTIVITY.lock`，把 `OMICSCLAW_STEP_IO` 的每一行转成 `input` 或 `output` 事件（`via: "read_input"`，sha256、字节数、`outside_contract` 用 Python 现有函数算），再追加一条 `r_session` 事件；持锁是为了不让看门狗写的 `run_end` 插在中间。要运行 R 步骤而找不到 Rscript 时，以退出码 2 结束，列出找过的位置。`_kernel_check` 不变：写 notebook 要 nbformat，sandbox 镜像本来就要装 ipykernel（D17）。
- `_ledger.py`：`read_run` 给 `r_session` 加一个桶（`RunRecord.r_sessions`），审查摘要才读得到。
- `contract.py`：`LEDGER_EVENTS` 加 `"r_session": ["rscript", "r_version", "packages"]`；`ENVIRONMENT` 加 `"step_io": "OMICSCLAW_STEP_IO"`、`"sdk_dir": "OMICSCLAW_SDK_DIR"`；`MANIFEST_SCHEMA` 的 `required` 加可为 null 的 `"rscript": "dict"`，加 `"rscript_keys": ["path", "version"]` 和 `"step_kinds": ["python", "r"]`。`omicsclaw/evals/ledger.py` 不读新事件，契约测试的子集关系不变。
- `_manifest.py`：步骤项的 `kind` 取自最近一次运行的 `run_start`；模块级的 `rscript` 在有 R 步骤运行过时记下路径和版本。
- Rscript 核对（G11）：比较 manifest 里 `rscript.path` 的 realpath 与这次的，`run` 和 `replay` 都只警告，警告重复在输出的最后一行。
- 过期判定不变：步骤文件的 sha256，加上记下的每个输入的 sha256。Rscript 或 R 包版本变化不让步骤过期，与 D9 一致，版本变化记在 `r_session` 里。
- skill 的 R 方法不记 R 包版本（Q11 推迟）。以后要做，可以直接用 `validate_r_environment(required_r_packages=...)` 里已有的包列表。

#### 5.6.6 渲染、重放、验收、审查摘要、参考

- 步骤 notebook：kernelspec `{"name": "ir", "display_name": "R", "language": "R"}`，`language_info` 为 R，代码 cell 带各自的输出。装了 IRkernel 的 Jupyter 可以直接打开它；本机没有 IRkernel，只影响交互重跑，不影响阅读。
- 模块 notebook（`stitch`）：仍是 python3 kernelspec；R 步骤的代码 cell 转成 markdown，代码放进 ```` ```r ```` 围栏，输出放进 ```` ```text ```` 围栏，段落头写 "R step, Rscript <版本>"。这样有人对模块 notebook "全部运行"时，R 代码不会被交给 Python kernel。
- `replay`：按文件名顺序对每个步骤用对应的 runner 运行，validate（Python）最后；`changed_outputs`、`orphan_outputs` 的逻辑不变。
- `accept`、`revise`：`module.steps()` 包含 `.R` 之后自然覆盖。
- 审查摘要（`_brief.py`）：R 步骤的第一个 cell 用 `parse_cells(language="r")` 取；记录的调用写 "none (R step)"，另加一行 "R step: Rscript <版本>; packages: …"（最多 8 个）；检查函数的识别只对 Python 的 validate 步骤做。
- `reference`：加一段 "R steps"，从 `step.R` 的 `#'` 注释生成两个函数的说明、单独运行的命令和 MTX/CSV 的交换做法。整段输出仍要在 12,000 字符以内（`tests/sdk/notebook/test_reference.py`；现在约 7,950）。
- `checks`：不变。Python 的 validate 用 `check_files` 检查 R 步骤写出的图和表。

#### 5.6.7 数据交换

与 R 方法相同（§5.1 第 5 条）：表格 CSV；表达矩阵 Matrix Market 加 `barcodes`、`features` 两个文件，Python 步骤用 `scipy.io.mmwrite` 经 `write_output(..., writer=...)` 写；R 对象 RDS。

#### 5.6.8 契约、`install_skill_deps`、sandbox

- `OMICSCLAW.md` 的 "Writing a step"：`:89` 的 "named `<k>_<name>.py`" 改成同时说明 `.R`；`:91` 的 "A step is a plain Python file" 改成 "A Python step is ..."；列表里加一条（M4 定稿前按 writing-for-agents 和 humanizer 各过一遍，下面是草稿）：

  > - A step may be an R file, `<k>_<name>.R`, when the method exists only in R and no skill function covers it, or when the user asks for R. Start it with `source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))`, then read with `read_input()` and write with `write_output()`; they take the same paths as in Python. Exchange data with Python steps through files: CSV for tables, Matrix Market for count matrices, RDS for R objects. To use a skill's R method, call its function from a Python step rather than running the skill's R scripts from an R step. An R step records no skill calls, so its first markdown cell names the method and why it runs in R. The validate step stays in Python.

  估计增加约 200 token。`tests/sdk/notebook/test_contract.py` 加一条：契约里写的 `step.R` 路径在 `_sdk` 里存在，环境变量名与 `ENVIRONMENT` 一致。`tests/entry/test_golden_deployment.py` 的部署旁边没有 `OMICSCLAW.md`，不受影响。
- `install_skill_deps` 不改。R 包仍只给出提示，由 `0_setup_env.sh` 或镜像负责。overlay 是 Python venv，R 步骤用的始终是基础环境的 Rscript。
- sandbox：`docs/core-features/sandbox.md` §13.1 补一句：模块有 R 步骤时镜像要有 Rscript 和步骤用到的 R 包；缺 Rscript 时执行器以退出码 2 结束并说明。sandbox 验收仍待 owner 的机器（0070 交付记录 §11 第 1 条）。

### 5.7 eval

- 8 条 `skill_routing` 用例不动：它们测的是 harness 的路径，用的 sc-qc、sc-clustering 的桩和 bulkrna-de 的 fixture 都不受这次迁移影响。
- 不为 R 步骤加脚本化用例。agent 一侧的路径与 Python 步骤相同（`bash` 跑 `run.py run`），差别都在执行器内部，由单元测试和真实 Rscript 测试覆盖；job2 也没有 R。
- 不加新的桩。
- 要守住的两处：`tests/evals/test_fixtures.py:87-104`（sc-batch-integration 的 `SKILL.md` 保留 `method="harmony"` 或 `--method harmony`）；`test_the_routing_seed_names_skills_that_still_exist`（种子不涉及 sc-integrate-cluster）。
- live eval 不改。

### 5.8 受影响的守卫与既有测试

| 测试 | 原因 | 处理 | 期 |
|---|---|---|---|
| `tests/test_*.py`（顶层） | 0070 首次 CI 就被其中一条拦下（交付记录 §15） | 每期验收都跑（含在 GUARDS 里） | 每期 |
| `tests/test_scrna_method_contracts.py:35-115` | 加载 CLI 脚本里的内部函数 | 改为按路径加载 `_api.py` 里对应的函数，断言不变 | M2、M3、M5 |
| `tests/test_scrna_console_encoding.py` | 扫描所有 scrna `*.py` 的 `print` | 新代码只用 ASCII | 每期 |
| `tests/test_output_ownership_contract.py` | skill 代码不许写 runner 的文件 | `_api.py` 不写文件；R 的两个文件不是 `.py` | 每期 |
| `tests/skillenv/test_skill_requires_are_declared.py` | 只扫主脚本 | 扫描范围加上 `_api.py` 和它直接导入的 `_lib`（G15）；`EXCEPTIONS` 的两条随之挂到 `_api.py` 上，确实不再命中时删除 | M0、M1、M8 |
| `tests/sdk/test_r_script_paths.py:40-56` | 断言 3 个 CLI 模块的常量 | 常量随代码搬到 `_api.py`，测试改为加载 `_api.py`；别名规则 `_SDK_R_SCRIPTS_DIR` 照旧 | M2、M5、M6 |
| `tests/sdk/test_public_surface.py:134-135` | 冻结共享 R 脚本的文件名 | 改的是文件内容（MTX/CSV），文件名不变；新脚本放 skill 的 `rscripts/`；R 步骤的两个 `.R` 文件放 `_sdk/notebook/` | 无 |
| `tests/sdk/test_public_surface.py` 的冻结面 | 门面与 `checks` | 门面仍是 5 个名字；`_demos.py`、`_rdriver.R`、`step.R` 是内部或非 Python 文件 | M0、M4 |
| `tests/sdk/test_bootstrap.py:86-88`、`test_help_probe.py:23`、`tests/skillenv/test_dependencies_section.py:26` | 断言 89 | 删除 sc-integrate-cluster 时改 88 | M2 |
| `tests/sdk/test_sc_scripts_help.py` | 10 个 CLI 的 `--help` | 薄壳的 `--help` 照常成功 | 每期 |
| `tests/sdk/notebook/test_skill_api_sections.py` | 名单 | §5.3 | M0 起每期 |
| `tests/sdk/notebook/test_skill_examples.py` | 自动收录示例 | 不改；超时 1800 s 足够 | 每期 |
| `tests/sdk/notebook/test_reference.py` | 12,000 字符上限 | R 一段加进来后仍要满足 | M4 |
| `tests/sdk/notebook/test_contract.py` | 契约字面量 | 新的 `ENVIRONMENT` 键、`r_session`、`rscript` | M4 |
| `tests/skills/test_domain_index_is_current.py` | `INDEX.md` 与 description | 只有删除 sc-integrate-cluster 时重生成 | M2 |
| `tests/evals/test_fixtures.py` | 种子参数 | §5.7 | M2 |
| skill 自带的 `tests/` | 指向脚本内部；起 CLI 的用例 | 随代码改指向；起 CLI 的用例打 `cli_subprocess`；§2.2.5 的既有失败随 `SKILL.md` 改写一起处理 | 各期 |
| `tests/test_sc_ambient_removal.py`、`tests/test_sc_standardize_input.py` | 以子进程跑 CLI | 薄壳保持行为 | M3 |

### 5.9 契约与文档

- `OMICSCLAW.md`：M2 删除 sc-integrate-cluster 时改 `:37`、`:61` 的 31 和 `:165` 的 89；M4 改 "Writing a step"（§5.6.8）；M6 登记 paul15 时更新 "Demo Data" 一节的数据集列表。路由表的文字不改。
- `README.md`、`README_zh-CN.md`：M2 改 skill 数；M9 在 What's new 加一句（单细胞 skill 都有了函数库、步骤可以用 R），删掉最旧的一条，保持 5 条。
- `CHANGELOG.md`：每期顶部一条；M2 的那条写明 sc-enrichment 的 CLI 默认结果会变（Q9）。
- `docs/core-features/agent-skills.md`：M2 的计数（§4.1）；M4 的 §9.1 加 R 步骤；§9.2 补只留 CLI 的情况；M9 改 `:115` 的未迁移数。`docs/core-features/sandbox.md` §13.1；`docs/core-features/eval.md:367` 的计数。
- `templates/skill/README.md`：§5.1 新增的 8 条；`templates/skill/_api.py` 示范可选后端在函数体内导入。
- `skills/_sdk/notebook/templates/README.md`（模块 README 模板）：加 R 步骤的单独运行命令。
- 每个迁移的 `SKILL.md` 按 0070 附录 B.3 改写，输出清单按代码重写，description 不改。

### 5.10 防线账

执行器不是安全边界（0070 §3.12），下面都不是为了对付恶意的 agent。

| 编号 | 检查 | 防什么 | 旁路 | 单人本机部署下值不值 |
|---|---|---|---|---|
| G10 | R 步骤的命名：validate 只能是 `.py`，同 stem 的 `.py` 与 `.R` 不能并存，不认小写 `.r` | 两个步骤的记账、notebook、日志互相覆盖；validate 写成 R 后用不上 `checks` | 没有，文件名就是执行器的入口 | 值。一个函数加几条测试，报错能告诉 agent 怎么改名 |
| G11 | Rscript 核对：`run`、`replay` 都只警告 | 换了 R 安装后重放，验收依据的环境悄悄变了 | 无视警告；Rscript 路径不变而 R 包升级了，G11 看不到，只能事后在 `r_session` 里查 | 值，代价只是比较两个路径；只警告，不挡探索也不挡验收 |
| G12 | R 端 `write_output` 的路径检查与冻结检查 | 与 G1、G2 相同 | R 里直接 `write.csv` 到任意位置 | 值。与 Python 一侧同样的规则，报错告诉 agent 正确的写法 |
| G13 | Rscript 以 `--no-init-file` 运行 | 用户 `~/.Rprofile` 混进步骤，影响可复现性（与 `IPYTHONDIR` 隔离同理） | `Rprofile.site`、`.Renviron`、`R_PROFILE` | 值。一个参数。不用 `--vanilla`：它还跳过 environ 与 site 文件，conda 的 R 是否靠它们找库未核实 |
| G14 | `test_skill_api_sections.py` 的 `CLI_ONLY`、`PENDING_MIGRATION` 名单，名单里的 skill 必须存在 | 有 skill 悄悄没迁移、只留 CLI 却没写理由，或名单与代码不符 | 改名单（要写理由） | 值。一条测试 |
| G15 | 依赖声明扫描扩到 `_api.py` | 函数库里 `require("x")` 而 `## Dependencies` 没声明，`install_skill_deps` 拒装 | 在函数体里直接 `import x`（扫描只认依赖 API 的调用） | 值。扫描已有，只扩范围 |
| G16 | job3 的 gate 只装示例用到的轻依赖并钉版本；重依赖的示例进不做 gate 的扩展 job；每期记首跑的安装与运行耗时，超 15 分钟就拆 | 示例坏了没人发现、`## API` 段与代码脱节（D3）；同时防 gate 因为装 torch、jax 而变慢、变得不稳 | 示例只覆盖每个 skill 的一个轻方法，其余方法的回归靠本机测试和 parity | 值。代价是每个 PR 多几分钟和一些下载失败的机会，钉版本加预算把它控制住 |
| G17 | job3 用 apt 装 r-base-core，跑 `requires_r` 的执行器测试 | job1 没有 R，R 步骤的驱动、IO 补记、记账一改坏就没人知道 | 只测 base R，R 包相关的问题（Seurat、DoubletFinder）测不到，留给本机 | 值。代价是一次 `apt-get update` 加安装（耗时未核实，首跑记录） |
| G18 | job3 跑已迁移 skill 自带的测试，只跑非 `demo`、非 `slow`、非 `cli_subprocess` 的用例 | §2.2.5 那类既有失败长期无人发现；`_api.py` 的单元测试退化 | 起 CLI 的用例和 demo 用例都不在 CI 里，靠每期的 SKILLCHECK | 值。这些用例不下载、不起 CLI，耗时短（首跑记录） |

不加的：
- 在 `new` 时检查 Rscript：运行 R 步骤时再报就够了，Python 模块不该因为没有 R 而建不起来。
- R 包预检：要从代码里猜包名，R 自己的 "there is no package called" 已经清楚。
- 禁止 R 步骤里的 `system()`：`bash` 是更宽的旁路；契约只写明 skill 的 R 方法要从 Python 步骤调用。
- R 语法预检：驱动报出出错的 cell。
- 静态检查 `_api.py` 不读写文件：读取器函数是合法的例外，静态规则分不清；规则写进模板，由审核看。

### 5.11 有意改动清单

以下改动会改变用户拿到的结果或进程行为，各有一条测试钉住；进 parity 用例的，比较时按 `exclude` 排除并写明理由。

| skill | 改动 | 影响 | 期 |
|---|---|---|---|
| sc-filter | `filter_stats` 的 `outliers_removed` 改名 `outliers_flagged`（只在 sc-filter 的 `_api.py` 里改） | 一个键名；demo 没有 `outlier` 列，parity 碰不到 | M1 |
| sc-markers | cosg 的 `pvals`、`pvals_adj` 从 0.0 改为 NaN | cosg 的表；`top_markers` 改按分数排 | M1 |
| sc-preprocessing（试点） | 新增 `apply_filters` 参数 | 默认不变 | M1 |
| sc-batch-integration | scvi 开始使用 `random_state`；harmony 只在 PCA 重算会因数据太小而失败时复用已有的 `X_pca` | scvi 的结果从此可复现（与以前任何一次运行都不同）；小数据从报错变成能跑 | M2 |
| sc-enrichment | 默认引擎 `auto` 改为 `python`；R 端 GSEA 的种子修好；`gsea_r`、`gsva_r` 伪造基因集的回退改为报错 | CLI 默认结果会变；R 路径不再静默返回 0 条或假结果 | M2 |
| sc-doublet-detection | DoubletFinder、scDblFinder、scds 三个脚本改用 MTX/CSV 交换 | 不再触发 basilisk 下载；结果预期不变（R 方法不录基线，本机对前两者跑 `requires_r` 测试） | M3 |
| sc-de（试点） | `sc_mast_de.R` 改用 MTX/CSV 交换 | 装了 MAST、没有网络的环境第一次调用不再必然失败；本机无 MAST，只验证 Python 端和脚本语法 | M3 |
| sc-cell-communication | liana 的 `specificity_rank` 改回原名，`pvalue` 置 NaN，不计入显著数；CellPhoneDB 的默认种子从随机改为 0 | liana 表的列与显著数；CellPhoneDB 的 p 值从此可复现 | M5 |
| sc-pseudotime | `use_rep` 的默认优先级改为 `X_pca` | 默认参数下的 pseudotime 改变，不再出现 inf | M6 |
| sc-velocity | 退出时不再 `killpg` 进程组，改为结束自己的子进程后 `os._exit(0)` | 只是进程行为；`run_cli` 不再杀 kernel | M6 |
| sc-grn | 简化路径使用用户给的 TF 列表 | 非 demo 路径的结果 | M6 |
| sc-perturb-prep | 对照的识别改为整词匹配 | 含 NT 子串的靶基因（WNT*、NTRK1、NT5E）不再被当成对照 | M7 |
| sc-in-silico-perturbation | `grn_ko` 的表去掉伪 p 值列；函数库里叫 `knockout_correlation` | 输出列 | M7 |
| sc-drug-response | 分数列改名 `mean_target_expression`；报告免责声明改成 OmicsClaw 原文 | 列名、报告文字 | M7 |
| sc-fastq-qc | FastQC 的输入路径先解析成绝对路径 | 相对路径输入时 FastQC 真的运行了 | M8 |

另有几处只是把原来静默的回退记进 `run_info`（sc-metacell、sc-gene-programs、sc-differential-abundance、sc-ambient-removal、sc-markers），结果不变，不列入。

---

## 6. 分期与任务

依赖：M0 先于其余各期；M1 至 M8 之间除"M2 删除 sc-integrate-cluster 要在 sc-batch-integration 搬完 harmony 的经验之后"外没有代码依赖；M4 只要求在 M9 之前完成；M9 最后。顺序按论文需要排：M1（pilot）、M2（方向 C v1）、M3（各条流程共同的 QC 前段），再 M4 至 M8。

分支与提交（沿用 0070、0071，推送与开 PR 由 owner 决定）：本地分支 `plan-0074-singlecell-migration`，每期一个提交、一个 PR，提交说明过 humanizer，不带 Claude 署名，每期在 `CHANGELOG.md` 顶部加一条。

命令：
- `PYTEST` = `/opt/conda/envs/rapids_singlecell/bin/python -m pytest -q -p no:randomly`
- `OCPYTEST` = `/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:randomly`，用于 skill 自带测试、示例和 parity。不要用它跑 `tests/launch/test_surfaces.py`（会挂住）；M6 修好之前，用它跑 sc-velocity 的测试要加 `--deselect skills/singlecell/scrna/sc-velocity/tests/test_sc_velocity.py::test_velocity_from_velocity_prep_output`（§2.2.5）。
- `PERTPYTEST` = `/tmp/omicsclaw-pertpy-probe.YfcLRL/overlay/bin/python -m pytest -q -p no:randomly`，只用于 sc-perturb。临时环境若已清理，按 §9.3 重建并重新核验。
- `GUARDS` = `PYTEST tests/test_*.py tests/sdk/test_boundary.py tests/sdk/test_bootstrap.py tests/sdk/test_public_surface.py tests/sdk/test_r_script_paths.py tests/skillenv/test_skill_requires_are_declared.py tests/skillenv/test_dependencies_section.py tests/skills tests/sdk/notebook/test_skill_api_sections.py tests/evals/test_fixtures.py`（审核在 `4bd83b1e` 上跑过：803 passed、5 skipped、1 xpassed，63.5 s）。
- 每个迁移的 skill 跑 `SKILLCHECK <skill>`：

  ```bash
  OCPYTEST skills/singlecell/<scrna|scatac>/<skill>/tests
  OCPYTEST -m demo skills/singlecell/<scrna|scatac>/<skill>/tests
  OCPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py -k <skill>
  OCPYTEST -m slow tests/parity/test_sc_parity.py -k <skill>
  ```

- 每期末尾：`OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python PYTEST -m slow tests/sdk/test_help_probe.py tests/sdk/test_sc_scripts_help.py`。

已知无关的失败：`tests/tools/test_workspace.py`，以及 `tests/ci_known_failures.txt` 里的条目。只跑新增与相关的测试，不跑全量。

每个 skill 的固定顺序：
0. 在 HEAD 上跑 SKILLCHECK 的前两条，把既有失败和跳过记进交付记录（应改 4）。
1. 用旧代码录基线，录两次。
2. `_api.py` → CLI 薄壳 → `SKILL.md` 按 0070 附录 B.3 改写并生成 API 段 → `examples/example_step.py` → 测试。
3. 有意改动，逐条带测试（§5.11）。
4. 再跑 SKILLCHECK 和 parity。通过标准：除第 0 步记下的既有失败外全部通过，每个既有失败写明是修了还是保留及理由；parity 的差异只出现在 `exclude` 列出的地方。

每期 PR 的 CI 首跑后，把 job3 的安装与运行耗时记进交付记录（G16）。

### M0 迁移工具与守卫（约 2.5 天）

| 任务 | 改动 |
|---|---|
| M0-1 | `tests/parity/`：注册表、`exclude`、`input`、两次录制与"不确定"标记、子进程 `start_new_session=True`；仅旧 sc-velocity 的基线录制按 §5.5 有条件接受 `-signal.SIGKILL`，回归比较仍要求 0；`test_sc_pilot_parity.py` 改名为 `test_sc_parity.py`；5 个试点的用例迁到注册表，结果不变 |
| M0-2 | `skills/_sdk/notebook/_io.py`：`DEMOS` 支持 `generator`，生成后写进缓存再读、记哈希；新文件 `_demos.py`（本期先实现机制和测试用的一个小生成器，具体数据集随用到的那期加）；`reference` 标出下载型与生成器型；`tests/sdk/notebook/test_io.py` 加分派、写缓存、记哈希、生成确定性的测试 |
| M0-3 | `tests/skillenv/test_skill_requires_are_declared.py` 扫描 `_api.py`（G15） |
| M0-4 | `tests/sdk/notebook/test_skill_api_sections.py` 的 `CLI_ONLY`、`PENDING_MIGRATION`，名单里的 skill 必须存在（G14） |
| M0-5 | `templates/skill/README.md` 与 `templates/skill/_api.py`（§5.1） |
| M0-6 | `pyproject.toml` 注册 marker `cli_subprocess`，给 5 个试点里起 CLI 的用例打上；`.github/workflows/eval.yml` 的 job3 加一步跑已迁移 skill 的自带测试（G18） |

验收：`GUARDS`；`PYTEST tests/sdk/notebook`；`OCPYTEST -m slow tests/parity/test_sc_parity.py`（5 个试点的 10 个用例仍全部一致）；`OCPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py`（5 passed）；在本机按 job3 新加的那一步跑一遍 5 个试点的测试，确认不起 CLI、不下载。`yaml.safe_load` 只能检查 `eval.yml` 的语法，工作流本身由 M0 的 PR 首跑检验，结果与耗时记进交付记录。

### M1 论文急需：sc-filter、sc-markers（约 2 天）

| 任务 | 改动 |
|---|---|
| M1-1 | sc-filter 全套（§3.2），`outliers_flagged` 只在它自己的 `_api.py` 里改名 |
| M1-2 | `sc-preprocessing.preprocess` 加 `apply_filters: bool = True`，`SKILL.md` 与 API 段同步；sc-preprocessing 的两个 parity 用例照旧一致 |
| M1-3 | sc-markers 全套（§3.2），cosg 的 p 值改 NaN，退回未过滤表记进 `run_info`；方法学正文不加 double dipping 的内容（Q7） |

验收：`GUARDS`；`SKILLCHECK sc-filter`、`SKILLCHECK sc-markers`；`OCPYTEST -m slow tests/parity/test_sc_parity.py -k sc-preprocessing`。通过标准：4 个 parity 用例逐值一致；`outliers_flagged` 由一条输入带 `outlier` 列的单元测试钉住；示例断言 2,638 个细胞与 `pbmc3k_processed` 的 `obs_names` 相同。job3 不加包。

### M2 方向 C v1：sc-batch-integration、sc-enrichment；删除 sc-integrate-cluster（约 4.5 天）

| 任务 | 改动 |
|---|---|
| M2-1 | sc-batch-integration 全套；`random_state` 传给 scvi 与 harmony；移入 harmony 在小数据上复用 `X_pca` 的处理与测试；在 `/tmp` 的 venv 里验证不依赖 torch 的 harmonypy 版本，决定示例用 harmony 还是 scanorama |
| M2-2 | sc-enrichment 全套；默认引擎 `python`（Q9）；R 端 GSEA 的种子；去掉两处伪造基因集；`tests/sdk/test_r_script_paths.py` 的 sc-enrichment 一处 |
| M2-3 | 删除 sc-integrate-cluster（§4.1 的全部改动） |
| M2-4 | `tests/test_scrna_method_contracts.py` 的 scanvi 一条改指向；job3 加 M2-1 定下的包并钉版本 |

验收：`GUARDS`；两个 skill 的 `SKILLCHECK`；`PYTEST tests/test_sc_preflight.py tests/test_scrna_method_contracts.py`；`OMICSCLAW_WRITE_SKILL_INDEX=1 PYTEST tests/skills/test_domain_index_is_current.py` 之后不带变量再跑一次；`git grep -n "sc-integrate-cluster" -- ':!docs/plans' ':!docs/reviews' ':!docs/presentations' ':!docs/proposals' ':!CHANGELOG.md'` 没有输出；`git grep -nE '\b89\b|\b31 (skills|个)' -- README.md README_zh-CN.md OMICSCLAW.md llms.txt docs/core-features skills/singlecell/INDEX.md tests` 的每一处都确认是有意保留的（应改 7）。

### M3 QC 其余：sc-standardize-input、sc-doublet-detection、sc-ambient-removal（约 3.5 天）

| 任务 | 改动 |
|---|---|
| M3-1 | sc-standardize-input |
| M3-2 | 新模块 `_lib/r_exchange.py`；sc-doublet-detection 全套，3 个 R 脚本改 MTX/CSV；本机加跑 DoubletFinder、scDblFinder 的 `requires_r` 测试 |
| M3-3 | 试点 sc-de 的 `sc_mast_de.R` 与 `_api.py` 对应部分改 MTX/CSV；测试 Python 端写出的文件，并用 `Rscript -e 'invisible(parse(file = ...))'` 检查脚本语法（`requires_r`） |
| M3-4 | sc-ambient-removal |
| M3-5 | `tests/test_scrna_method_contracts.py` 的 doubletfinder 一条改指向；job3 加 `scrublet==0.2.3` |

验收：`GUARDS`；3 个 skill 的 `SKILLCHECK`；`OCPYTEST skills/singlecell/scrna/sc-de/tests`（试点不退化）；`PYTEST tests/test_sc_preflight.py tests/test_sc_ambient_removal.py tests/test_sc_standardize_input.py tests/test_scrna_method_contracts.py`。

### M4 R 步骤（约 4 天）

| 任务 | 改动 |
|---|---|
| M4-1 | `contract.py`、`_layout.py`（正则、`layout_problems`）、`_percent.py`（`language`） |
| M4-2 | `step.R`、`_rdriver.R`、`_runners.RscriptRunner` |
| M4-3 | `_executor.py`（分派、`format_step` 表头、持锁补记 IO、`r_session`、Rscript 检查与核对、`stitch`）、`_ledger.py`（`r_sessions` 桶）、`_manifest.py`（`kind`、`rscript`） |
| M4-4 | `_brief.py`、`_reference.py`、模块 README 模板 |
| M4-5 | `OMICSCLAW.md` 的 `:89`、`:91` 与新的一条；`agent-skills.md` §9.1；`sandbox.md` §13.1 |
| M4-6 | 测试：`test_layout.py`、`test_percent.py`、`test_executor.py`（两个假 runner：混合模块按序运行、`kind`、IO 行变成带 sha256 与 `outside_contract` 的事件、R 输入变化使步骤过期、Rscript 变化时 `run` 与 `replay` 都警告、找不到 Rscript 时退出码 2）、`test_replay.py`（混合模块、摘要含 R 步骤）、`test_reference.py`、`test_contract.py`；新文件 `test_rscript.py`（标 `requires_r`，没有 Rscript 时跳过：逐 cell 输出、出错的 cell 序号与消息、课题根没有 `Rplots.pdf`、`~/.Rprofile` 不生效、CSV 与 RDS 与 PNG（无参函数）的读写、`.h5ad` 的提示性报错、单独 `Rscript` 运行写出同样的 CSV、杀掉外层 shell 后 Rscript 在 10 s 内退出且锁释放） |
| M4-7 | job3 加 `sudo apt-get update && sudo apt-get install -y --no-install-recommends r-base-core`，跑 `-m requires_r tests/sdk/notebook/test_rscript.py`（G17） |

验收：

```bash
PYTEST tests/sdk/notebook tests/sdk/test_r_script_runner.py tests/sdk/test_r_script_runner_environment.py tests/sdk/test_public_surface.py
OCPYTEST tests/sdk/notebook/test_rscript.py
PYTEST tests/entry/test_runtime_contract.py tests/entry/test_assembly.py tests/sdk/notebook/test_contract.py \
  tests/sdk/test_replot_hint.py tests/planning/test_render.py tests/entry/test_golden_deployment.py
PYTEST tests/evals/dataset -m scripted_eval
GUARDS
```

另在临时课题里手动走一遍：Python 步骤导出 Matrix Market，R 步骤用 Seurat 读入并写 CSV，Python validate 用 `check_files` 与 `check_rows`；`run`、`status`、改上游后 `status` 显示 R 步骤 `input changed`、`replay`、写 REPORT 与审查、`accept`；把命令和输出记进交付记录。记下契约改动前后 contract 段的 token 数。

### M5 通路、程序、丰度、通讯（约 5.5 天）

| 任务 | 改动 |
|---|---|
| M5-1 | sc-pathway-scoring（自己的别名表，不统一） |
| M5-2 | sc-gene-programs |
| M5-3 | sc-differential-abundance；生成器 `multisample_synthetic`；`tests/sdk/test_r_script_paths.py` 的 sc-DA 一处 |
| M5-4 | sc-cell-communication；`tests/test_scrna_method_contracts.py` 的 builtin 一条改指向 |
| M5-5 | job3 视示例需要加 `statsmodels==0.14.6` |

验收：`GUARDS`；4 个 skill 的 `SKILLCHECK`；`PYTEST tests/test_sc_preflight.py tests/test_scrna_method_contracts.py`。

### M6 轨迹与动态（约 6.5 天）

| 任务 | 改动 |
|---|---|
| M6-1 | sc-cytotrace；登记 paul15（缓存键 `demo-data-v2`，预取） |
| M6-2 | sc-metacell |
| M6-3 | sc-pseudotime；`tests/sdk/test_r_script_paths.py` 的一处；6 条 `grep` 源码的测试改为检查 `_api.py` |
| M6-4 | sc-velocity：先做 `/tmp` 的挂起探针，再改薄壳的退出（§3.2）；生成器 `velocity_simulation`；新测试：步骤里带超时的 `run_cli("sc-velocity", ...)` 按时返回、kernel 仍在，外层墙钟超时后清理整个测试后代树并检查无残留；`test_velocity_from_velocity_prep_output` 不再需要 `--deselect` |
| M6-5 | sc-grn |
| M6-6 | job3 加 `scvelo==0.3.4` |

验收：`GUARDS`；5 个 skill 的 `SKILLCHECK`（sc-velocity 的第 0 步带 `--deselect`）。

### M7 扰动与药物（约 4 天）

| 任务 | 改动 |
|---|---|
| M7-1 | sc-perturb-prep；生成器 `perturbseq_synthetic`；对照整词匹配 |
| M7-2 | sc-in-silico-perturbation；`rscripts/sc_sctenifoldknk.R` |
| M7-3 | sc-drug-response；免责声明 |
| M7-4 | sc-perturb 全套迁移；使用 N1 c 核验的版本录基线、运行示例和测试；核实种子传递与合成数据中的 KO 检出 |
| M7-5 | 增加 `skill-examples-extended` 和区分轻重示例的 marker；固定 pertpy、scikit-learn 及解析报告中的兼容约束，记录首次安装与运行耗时 |

验收：`GUARDS`；4 个迁移 skill 的 `SKILLCHECK`。sc-perturb 的测试、示例和 parity 使用 N1 c 的 overlay；扩展 job 使用干净的 CPU 环境另跑一次，并确认 gate job 不会收集它。

### M8 计数与 scATAC（约 2.5 天）

| 任务 | 改动 |
|---|---|
| M8-1 | sc-multi-count（先录基线，再做 M8-4） |
| M8-2 | scatac-preprocessing；生成器 `atac_synthetic`；`read_10x_peaks` |
| M8-3 | sc-count、sc-velocity-prep 的 `SKILL.md`（§4.2） |
| M8-4 | sc-fastq-qc 的 `SKILL.md` 与 `_lib/upstream.py` 的路径修复 |
| M8-5 | `PENDING_MIGRATION` 清空并删除 |

验收：`GUARDS`；两个迁移 skill 的 `SKILLCHECK`；`OCPYTEST skills/singlecell/scrna/sc-fastq-qc/tests skills/singlecell/scrna/sc-count/tests skills/singlecell/scrna/sc-velocity-prep/tests skills/singlecell/scrna/sc-multi-count/tests`（共用 `_lib/upstream.py` 的 4 个）。

### M9 端到端验收与交付（约 2 天）

§7 的端到端；全部示例与全部 parity 用例各跑一次；交付记录 `docs/plans/0074-singlecell-skill-migration-delivery.md`；`README.md` 的 What's new；`agent-skills.md:115` 的未迁移数。

验收：

```bash
OCPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py -k 'not sc-perturb'
PERTPYTEST -m skill_example tests/sdk/notebook/test_skill_examples.py -k sc-perturb
OCPYTEST -m slow tests/parity/test_sc_parity.py -k 'not sc-perturb'
PERTPYTEST -m slow tests/parity/test_sc_parity.py -k sc-perturb
GUARDS
PYTEST tests/evals/dataset -m scripted_eval
```

上述 `-k sc-perturb` 也匹配 sc-perturb-prep，所以这两个用例会一起在 overlay 运行；其余 skill 使用基础环境，避免因额外安装 pertpy 改变 sc-differential-abundance 的后端选择。CI 以专用 marker 精确拆分。

---

## 7. 测试与验收

### 7.1 单元测试

各期的新测试列在 §6。每条新测试都在改代码之前或临时撤回改动时跑过，确认它会失败（0070 §12 的做法）；有意改动各有一条测试钉住新行为。

### 7.2 端到端

做法沿用 0070 §8 和 0071 §6：课题目录 `/tmp/oc0074-e2e/project`（起始为空），`OMICSCLAW_SKILLS_DIR=<checkout>/skills`，模型取 `.env`，权限模式 auto-approve，`OmicsClaw` 环境（`PATH` 上有 Rscript）。驱动脚本以 `/tmp/oc0071-e2e/drive.py` 为底，保留它对 `read._read`、`subagent.report_usage`、`ChildRunner.delegate` 的包装。实施者扮演用户；接受时说得明确（"I accept module 01_qc."），不用"把这个模块做完"这类话（0071 交付记录 §8 第 3 条）。

4 条用户消息：
1. "Use pbmc3k_raw. Run QC and detect doublets, then filter cells with the PBMC preset and drop the doublets." 期望：模块 `01`，步骤依次调用 `sc-qc.calculate_qc`、`sc-doublet-detection.detect_doublets`、`sc-filter.filter_cells`，没有 `run_cli`。先检测后过滤，因为 `filter_cells` 只按已有的双细胞列筛。
2. "Preprocess and cluster the filtered cells." 期望：模块 `02`，`preprocess(..., apply_filters=False)`，`cluster`。
3. "Find marker genes for each cluster and run enrichment on them." 期望：模块 `03`，`sc-markers.find_markers`、`sc-enrichment.ora`。
4. "Cross-check the B-cell markers with Seurat's FindMarkers in R." 期望：模块 `04`，一个 Python 步骤导出 Matrix Market，一个 R 步骤用 Seurat，Python validate 比较两边的重叠。

每个模块走完 `replay`、`module-reviewer` 审查、实施者明确接受后 `accept`。

通过标准：
1. 4 个模块都是 `ACCEPTED`。
2. 模块 01 至 03 的 manifest 记下上面列出的 skill 函数，没有 `skill_cli`。
3. 模块 04 的 R 步骤：manifest 的 `kind` 是 `"r"`，有 `rscript`；步骤 notebook 每个 cell 有自己的输出；记账里有 `r_session` 和 Seurat 的版本；`replay` 成功，审查摘要列出这个 R 步骤。
4. 在课题副本里改模块 03 的 marker 表所依赖的步骤并重跑，`status` 显示模块 04 的 R 步骤 `input changed`。
5. 单独运行 R 步骤（`OMICSCLAW_SDK_DIR=... Rscript analysis/04_.../<step>.R`），写出的 CSV 与执行器写出的逐值一致。
6. agent 读 `_sdk` 源码不超过 1 次（0071 的计数规则）。

运行时间、主线模型调用次数、审查次数与耗时、遇到的问题写进交付记录。sandbox 模式记为"待 owner 机器验证"。

### 7.3 变异检查（一次性，记进交付记录）

1. 删掉 sc-filter `_api.py` 的 `filter_summary`：API 段一致性测试失败。
2. 给 `PENDING_MIGRATION` 里的一个 skill 加上 `_api.py` 却不改名单，或在名单里留一个不存在的 skill：G14 的测试失败。
3. 在某个 `_api.py` 里加 `require("not-declared")`：G15 的测试失败。
4. 让执行器不补记 R 的 IO 行：`test_executor.py` 的过期判定那条失败，端到端第 4 条也会失败。
5. 去掉驱动里的 `pdf(NULL)`：`test_rscript.py` 的 `Rplots.pdf` 那条失败。
6. 去掉 `--no-init-file`：`test_rscript.py` 的 `~/.Rprofile` 那条失败。
7. 恢复 sc-velocity 薄壳的 `killpg`：带超时的 `run_cli` 那条失败（kernel 被杀）。
8. 薄壳只 `os._exit(0)`、不结束子进程：同一条测试在外层墙钟超时后失败并清理测试的运行器、kernel 与 worker，确认无残留（B2）；不能只依赖 `run_cli` 的父进程定时器或运行器自身的进程组。
9. 让生成器不落盘、直接返回内存数据：`test_io.py` 的"记哈希"那条失败。
10. 把 sc-cell-communication 的 liana `pvalue` 改回 `specificity_rank`：对应的有意改动测试失败。

---

## 8. 风险

| 编号 | 风险 | 处理 |
|---|---|---|
| R1 | 本机缺很多 R 包（MAST、nichenetr、slingshot、monocle3、AUCell、GSEABase、GSVA、scds、scTenifoldKnk 等），CellChat 装了却加载失败；9 个 skill 的 R 方法迁移后多数在本机跑不了 | R 方法照搬，`requires_r` 的测试在缺包时跳过；交付记录列一张"待 owner 机器补测"的方法清单 |
| R2 | 共享 R 脚本用 zellkonverter 默认读取器，首次使用要下载约 2 GB 的 basilisk 环境，没有网络的 sandbox 必然失败 | M3 把 3 个双细胞脚本和 `sc_mast_de.R` 改成 MTX/CSV；剩下的 `sc_pseudobulk_deseq2.R` 没有调用方，`sp_numbat.R` 属空间，都不在本批，记进交付记录 |
| R3 | 两个环境都缺的 Python 后端（sccoda、cnmf、SEACells、pyscenic、omicverse、cellbender、simba-bio），对应代码路径迁移后没有运行过 | 这些方法的函数只做"导入、调用、整理结果"，单元测试用假模块覆盖调用参数；pertpy 见 N1 |
| R4 | demo 或方法本身不确定（sc-batch-integration 的随机批次、scCODA、monocle3），parity 比不了 | 两次录制标"不确定"；改用固定种子生成的输入；这些方法不录基线 |
| R5 | job3 的安装与运行时间增长、下载失败 | G16：只装用到的、钉版本、记耗时、超预算就拆 |
| R6 | 改写 `SKILL.md` 时改变了 0072 pilot 依赖的内容 | 方法学正文只搬不改（Q7）；pilot 用自己的 tag 冻结 |
| R7 | 顶层守卫或 skill 测试里的隐性耦合，CI 首跑才发现 | 每期验收跑 `GUARDS`（含整组 `tests/test_*.py`）；G18 |
| R8 | 一期 4 到 5 个 skill，审查仍费力 | 每期一个 PR；交付记录按 skill 分节，列基线比较结果与有意改动 |
| R9 | R 步骤与 Python 步骤交换数据不顺手 | 契约与 `reference` 写明 CSV、Matrix Market、RDS 的做法；端到端第 4 条就走这条路 |
| R10 | 删除 sc-integrate-cluster 影响仓库外的用户脚本 | 仓库内没有调用方；`CHANGELOG.md` 写明替代的两次函数调用 |
| R11 | M6 之前，经 `run_cli` 调 sc-velocity 会杀掉 kernel；在 OmicsClaw 环境跑它的测试会杀掉 pytest | M6 修；在那之前跑测试带 `--deselect`（§6） |
| R12 | sc-velocity 的新退出方式仍可能留下 TensorFlow 线程卡住 | 先做 `/tmp` 探针；`os._exit` 不等线程，`run_cli` 的测试带超时 |
| R13 | 工作量估计偏差，L 级 skill 与 M0 偏乐观 | 每期结束时在交付记录里对照估计，偏差超过 30% 时告知 owner |
| R14 | CI 的 `anndata==0.11.4` 与本机 0.12.11 不同，生成器写的 h5ad、示例的行为可能有差别 | 每期 PR 的首跑就是这项检查；有差别时在 job3 里钉成本机的版本，或修示例 |
| R15 | 不依赖 torch 的 harmonypy 旧版与 `_lib/integration.py` 可能不兼容；paul15 的许可未核实 | M2 先在 venv 里验证，不行就改用 scanorama 的示例；paul15 由 owner 在 M6 之前确认，不行就退回 `pbmc3k_processed` |

---

## 9. 裁定

### 9.1 owner 的裁定（2026-10-07）

owner 接受审核意见。各题的落定：

| 问题 | 裁定 | 落在计划的哪里 |
|---|---|---|
| Q1 | a：删除 sc-integrate-cluster，删除清单补全 | §4.1、M2 |
| Q2 | a：skill 的 R 方法由 Python `_api.py` 调用，R 步骤给 agent 自己的 R 代码；契约写明不要在 R 步骤里直接跑 skill 的 R 脚本 | §5.6.1、§5.6.8 |
| Q3 | a：job3 用 apt 装 r-base-core，命令补 `apt-get update`。`ubuntu-latest`（Ubuntu 24.04，镜像 20260927.320.1）不带 R，已核实；以后若自带，job1 会跑到只用 base R 的 `requires_r` 用例，照样能过，届时可去掉 job3 的安装 | §5.4、M4-7 |
| Q4 | a 的主体：缺后端的方法不录基线、不进示例；sc-perturb 的例外先暂缓，随后由 N1 c 恢复，用专用 overlay 验证并纳入 M7 | §3.2、§5.5、§9.3 |
| Q5 | a：`knockout_correlation`，去掉伪 p 值 | §3.2、§5.11 |
| Q6 | a：只修会给出错误、伪造或危险结果的，有意改动清单补全 | §5.11 |
| Q7 | a：不加 double dipping 的提醒 | §2.4、M1 |
| Q8 | paul15 用真实数据；速度示例用 `scvelo.datasets.simulation`，不新增 pancreas，也不做 `("scvelo", ...)` 下载源；差异丰度、扰动、scATAC 用合成生成器 | §5.4 |
| Q9 | a：sc-enrichment 默认引擎改为 `python`，CHANGELOG 写明 CLI 的默认结果会变 | §3.2、§5.9 |
| Q10 | a：sc-fastq-qc 只留 CLI | §4.2 |
| Q11 | b：推迟；skill 的 R 方法不记 R 包版本 | §1.2、§5.6.5 |
| Q12 | 只跑不起 CLI 的用例 | §5.4、G18 |
| Q13 | a，参数名改为 `apply_filters` | §3.2、M1 |

审核补的几件事：
- M4（第 1 版的 M2）不再是迁移各期的硬前置，只要求在 M9 之前完成；排在第 4 期，理由见 §5.6.1。每期一个 PR。
- job3：示例用不到的包不装，装的包钉版本；重的示例放进不做 gate 的扩展 job；首跑记录安装和运行耗时，超预算就拆分（G16 至 G18）。
- R 方法的数据交换用 MTX/CSV，3 个双细胞脚本照此改；试点 `sc_mast_de.R` 一并改，列为有意改动（§5.11）。
- sc-count、sc-velocity-prep 本批列入 `CLI_ONLY`，只改 `SKILL.md`（§4.2）。
- 审核第 7 节的砍减全部接受，新增工作全部加入（修订说明表）。
- 代码基准改为 `4bd83b1e`。

### 9.2 第 1 版的问题（已裁定，保留备查）

#### Q1 sc-integrate-cluster 怎么处置
- a. 删除，skill 数 89 降到 88；harmony 复用 `X_pca` 的经验移到 sc-batch-integration。推荐。
- b. 改写成独立的"整合加聚类"便利 skill，description 去掉 consensus。
- c. 并入 sc-batch-integration，作为 `integrate_and_cluster`。

理由：它唯一的用途随 consensus 消失，迁移后两次函数调用就能替代，留着只会让路由多一个容易混淆的选项。

#### Q2 skill 的 R 方法怎么在步骤里用
- a. 由 Python `_api.py` 经 `RScriptRunner` 调用；R 步骤只给 agent 自己写的 R 代码。推荐。
- b. 另给每个有 R 方法的 skill 写 `_api.R`，R 步骤 `source` 它。
- c. 两者都做。

理由：a 是试点已有的做法，API 段、一致性测试、eval 桩和记账都不用改；b、c 要再做一套 R 版的生成器、记账和桩，本批没有一个 skill 需要。

#### Q3 R 步骤在 CI 里怎么测
- a. job3 用 apt 装 `r-base-core`，跑 `test_rscript.py`；R 包不装。推荐。
- b. 只在本机跑。

理由：R 端两个文件和驱动只用 base R，装 base R 就能在每个 PR 上覆盖执行器的 R 路径。

#### Q4 本机缺的 Python 后端怎么处理
- a. 迁移代码，这些方法不录基线、不进示例，由单元测试和 owner 机器补测；例外是 sc-perturb：用 overlay 装 pertpy 录基线、跑示例，job3 也装 pertpy。推荐。
- b. 本机建一个 overlay 装齐所有缺的后端，全部录基线。
- c. 从 `_api.py` 里拿掉跑不了的方法。

理由：a 保住"每个 skill 至少有一个能跑的示例"，又不为很少用的方法搭整套环境；c 会让函数库与 CLI 的方法不一致。

#### Q5 sc-in-silico-perturbation 的 `grn_ko`
- a. 函数库里改名 `knockout_correlation`，说明它只是与 KO 基因的相关排序，去掉伪 p 值；scTenifoldKnk 改用 `RScriptRunner` 并加种子；CLI 的 `--method grn_ko` 保留，输出同样去掉 p 值列。推荐。
- b. 去掉 `grn_ko`，只留 scTenifoldKnk。
- c. 整个 skill 推迟，只改 `SKILL.md`。

理由：现在的结果总是"只有 KO 基因自己显著"，名字和 p 值都会误导；a 保留了它能给的东西（与 KO 基因共表达的基因排序），也保住可运行的示例。

#### Q6 盘点发现的缺陷怎么处理
- a. 只修会让函数库给出错误、伪造或危险结果的，列为有意改动并从 parity 中排除；其余写进 Gotchas。推荐。
- b. 纯迁移，一个都不修。
- c. 全部修。

理由：函数库是新的公开面，a 不让它一上来就带着已知的错误结果；c 会把方法学的改动混进迁移，parity 失去意义。

#### Q7 迁移 sc-markers 时要不要加 double dipping 的提醒
- a. 不加。方法学正文只搬不改；pilot 在 M1 合入后用自己的 tag 冻结。推荐。
- b. 现在就加。

理由：加了就改变了 pilot 要测的条件。

#### Q8 新的 demo 数据
- a. 轨迹用真实的 paul15，速度用真实的 pancreas，差异丰度、扰动、scATAC 用合成生成器。推荐。
- b. 全部合成，CI 不下载新数据。
- c. 全部真实（另加 Kang 2018、scPerturb、10x ATAC）。

#### Q9 sc-enrichment 的默认引擎
- a. 函数库和 CLI 的默认都改成 `python`；R 的 clusterProfiler 修好种子后作为选项。推荐。
- b. 保持 `auto`。

#### Q10 sc-fastq-qc
- a. 只留 CLI，改 `SKILL.md`，修相对路径。推荐。
- b. 写一个读 FASTQ 的 `_api.py`。
- c. 现在就并入 bulkrna-read-qc。

#### Q11 skill 的 R 方法要不要记 R 包版本
- a. 要：`RScriptRunner` 在步骤里运行时追加 `r_session` 事件。推荐。
- b. 现在不做。

#### Q12 skill 自带的测试进不进 CI
- a. 已迁移 skill 的非 `demo` 测试在 job3 里跑。推荐。
- b. 照旧只在本机跑。

#### Q13 sc-preprocessing 的过滤开关
- a. 给试点 `preprocess` 加一个默认不变的关键字参数，sc-filter 的 `SKILL.md` 写明随后关掉它。推荐。
- b. 不改试点，在 sc-filter 的 `SKILL.md` 里写"随后用宽松阈值调用 `preprocess`"。

### 9.3 N1 的裁定与安装核验

#### N1 sc-perturb 怎么处理

owner 已选 c（2026-10-07）："现在就装 pertpy 查清依赖树，再按原计划迁移"。sc-perturb 纳入 M7 的整体迁移；其依赖核验在迁移前完成。下面保留第 2 版的选项作为裁定背景，a 的推荐已被这项选择取代。

Q4 的 sc-perturb 例外（用 overlay 装 pertpy）暂缓之后，它唯一的方法 mixscape 在本机和 CI 里都跑不了，pertpy 的依赖树也没核实。这样它既录不了 parity 基线，也没有能在 CI 里跑的示例，与 S2（0070 D3：每个 skill 一个示例，CI 里真跑）冲突。

- a. 本批只改 `SKILL.md`（输出清单、`--seed` 只作用于合成 demo 等），列入 `CLI_ONLY` 并写明"pertpy 未装、依赖树未核实，核实后另行迁移"。推荐。
- b. 迁移代码和 `_api.py`，示例在缺 pertpy 时跳过，作为 S2 的书面例外，只在 owner 的机器上跑。
- c. 现在就用 overlay 装 pertpy 核实依赖树，再按 Q4 原推荐迁移。

第 2 版选择这些备选的原因是尚无可运行的 pertpy 环境。N1 c 的核验已完成，结果如下。

#### 安装与真实运行（2026-10-07）

- 基础解释器 `/opt/conda/envs/OmicsClaw/bin/python` 是 Python 3.11.15。用 `python -m venv --system-site-packages` 建立 `/tmp/omicsclaw-pertpy-probe.YfcLRL/overlay`，后续验证都用其中的 `bin/python`。基础环境安装前后的 `pip freeze --all` 完全相同；overlay 的 `pip check` 相较安装前新增问题为 0，原 numba/llvmlite 冲突减少 1 条。基础环境本来已有多条依赖告警，本次没有修复它们。
- [pertpy 1.0.3 的官方元数据](https://pypi.org/pypi/pertpy/1.0.3/json) 要求 Python `>=3.11,<3.14`；1.0.4 及之后要求 3.12。当前 1.4.0 虽然将 JAX 变成可选依赖，不能直接装在这个 Python 3.11 环境。核验固定 `pertpy==1.0.3`，其依赖包含 JAX、Flax、NumPyro 和 ott-jax，没有要求新装 torch。
- 首次 wheels-only 解析失败，因为 [blitzgsea 1.3.54](https://pypi.org/pypi/blitzgsea/1.3.54/json) 只有 sdist。在此开发 overlay 中允许 pip 隔离构建后成功，构建 wheel 为 625,752 字节。因此现有 `install_skill_deps` 的 wheels-only 路径不能直接重建这套环境；本次没有修改该工具的策略。
- pertpy 及依赖安装用时 20.3 秒，随后固定 `scikit-learn==1.7.2` 用时 8.2 秒，均不含之前解析和下载探针的时间。最终 overlay 占用 757 MiB；安装涉及的发行文件约 175.1 MB，下载缓存另占 435 MiB。这些是本机测量，不是 CI 耗时预算。
- sklearn 1.8.0 下，第一次真实 demo 报 `MixscapeGaussianMixture._m_step() got an unexpected keyword argument 'xp'`。这是 pertpy 1.0.3 对 sklearn 内部接口的兼容问题，固定到 1.7.2 后通过。源码可对照 [pertpy 1.0.3](https://github.com/scverse/pertpy/blob/1.0.3/pertpy/tools/_mixscape.py) 与 [sklearn 1.7.2](https://github.com/scikit-learn/scikit-learn/blob/1.7.2/sklearn/mixture/_gaussian_mixture.py)。
- 两次未改造 CLI 的 `--demo` 均返回 0，用时 5.77、5.67 秒。每次写出 180 个细胞、80 个基因的 `processed.h5ad`、表格、图及 `result.json`。分类为 `NT=60`、`KO_A KO=60`、`KO_B KO=60`；两次 `mixscape_cell_classes.csv` 完全一致，概率均在 `[0, 1]` 内。这是安装与默认 demo 的核验；M7 仍须录阈值变体、API parity 和新示例。
- 实际验证版本为 `pertpy==1.0.3`、`scikit-learn==1.7.2`、`scanpy==1.11.5`、`anndata==0.12.11`、`numpy==2.0.2`、`pandas==2.3.3`、`scipy==1.17.1`、`jax==0.10.2`、`jaxlib==0.10.2`、`flax==0.12.8`、`blitzgsea==1.3.54`。CI 使用的 `anndata==0.11.4` 与本机不同，不能以此次运行代替 CI 验收。

可复跑命令（从仓库根运行，输出目录选新的空目录）：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMBA_NUM_THREADS=2 \
  /tmp/omicsclaw-pertpy-probe.YfcLRL/overlay/bin/python \
  skills/singlecell/scrna/sc-perturb/sc_perturb.py \
  --demo --output /tmp/omicsclaw-pertpy-demo-check
```

当前 `split_by` 非空时，helper 传入 `ref_selection_mode="split_by"`，签名使用同组全部对照的均值，`n_neighbors` 不参与这条路径。Mixscape 接受 `random_state`；NN 签名路径通过 `**kwargs` 接受它。M7 的 docstring、参数测试和种子实现要反映这些实际语义。

#### CI 解析与证据

用 `--dry-run --ignore-installed`，固定 `pertpy==1.0.3`、`scikit-learn==1.7.2`、`anndata==0.11.4`、`pandas>=2.0,<3.0`，再加 `scanpy[leiden]`，解析成功。共有 105 个分发包，官方发行文件合计约 380.3 MB（adjustText 的元数据查询超时，少计约 13 KB）；包含 JAX/Flax，不含 torch。这是整套科学环境的解析规模，不是相对已有 gate 的净增量，也不是干净 CI 环境已经安装并运行的证据。M7 将它放进扩展 job，固定 sklearn，安装和运行后再记录结果。

本地原始证据目录为 `/tmp/omicsclaw-pertpy-probe.YfcLRL/`：`summary.json` 保存版本、签名和结果；`install-build-1.0.3-report.json`、`sklearn-install-report.json` 保存安装来源与依赖；`ci-compatible-dry-run-report.json` 是 CI 解析报告；`artifact-sizes.json` 是发行文件大小；`base-*-before.log`、`base-*-after.log` 与 `overlay-check-*.log` 用于环境对比；`demo.log` 是最初失败堆栈；`demo-sklearn172/`、`demo-repeat/` 是两次成功输出。临时目录若被清理，可按上述版本重新建环境，耗时及传递依赖须重新核验。
