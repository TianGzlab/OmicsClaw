# 0074 计划审核报告

审核对象：`docs/plans/0074-singlecell-skill-migration.md`（875 行，基准 `915289d3`）。2026-10-07 由独立的只读子 agent 审核，本文件照录它的报告。

路径都相对仓库根 `/workspace/dataset/private/zhouwg_data/OmicsClaw`。审核期间 `main` 从 `915289d3` 前进到 `4bd83b1e`（应改第 10 条）。下文行号以计划的基准 `915289d3` 为准，另有说明的除外。

## 1. 结论

小改后可交。我抽查了 40 多条代码事实，基本属实，作者报告的几条新发现都成立。运行层和 R 步骤的设计符合已定裁定，也没有提前做 0070 §1.3 里仍推迟的项。要改的主要有三处：CI job3 的依赖安排前后矛盾，也没有算账；sc-velocity 的修法很可能把原脚本要躲的挂起问题带回来；M2 被排成所有迁移期的前置，但按计划自己的 Q2 推荐，迁移并不依赖它。

## 2. 阻塞问题

B1. CI job3 的依赖安排前后矛盾，且没有算账
- 位置：§5.4 "CI job3"、M3-6、M4-6、M5-6、Q4、Q12、§5.10。
- 问题：§5.4 写 job3 "不装 torch"，可 M3-6 要装的 harmonypy 当前版本依赖 torch，M5-6 要装的 palantir 经 mellon 依赖 jax/jaxlib，Q4 例外里的 pertpy 依赖树也没有核实。这些包都没钉版本，而 job3 钉的是 `anndata==0.11.4`，本机是 0.12.11。Q12 要在 job3 里跑的"非 demo"skill 测试中，有 15 条默认收集的用例会起 CLI 子进程。CLI 的 `--demo` 走 `_lib/io._demo_candidates`，只看 `data/` 和 `examples/`，不看 `OMICSCLAW_DEMO_DIR`，所以 CI 每次都会重新下载 pbmc3k。job3 是每个 PR 都要过的 gate，以上每一项都会增加它的耗时和出错机会，§5.10 却没有一行记这笔账。
- 证据：在 OmicsClaw 环境用 `importlib.metadata` 查到，harmonypy 0.2.0 依赖 `torch`；palantir 1.4.2 依赖 `mellon>=1.6.1`，mellon 1.7.1 依赖 `jax, jaxopt`；torch 2.10.0 依赖一串 `nvidia-*-cu12` 包。另见 `.github/workflows/eval.yml:63`、`skills/singlecell/_lib/io.py:252-270`。15 条用例的统计方法见第 8 节。
- 建议：每期写清 job3 要装哪些包、什么版本，例如 `harmonypy<0.2`，或者从 CPU 索引装 torch。示例用不到的包不装：sc-pseudotime 示例用 dpt，不需要 palantir；sc-grn 示例用 correlation，不需要 arboreto；sc-cell-communication 示例用 builtin，不需要 liana。pertpy 先在 overlay 里看清依赖树再决定。Q12 只跑不起 CLI 的用例，或者在工作流里把 `.demo-data` 链接成 `data/`。"job3 扩容"写进防线账，首跑时记下安装和运行时间，超出预算就拆出一个不做 gate 的扩展 job。

B2. sc-velocity 的修法可能把挂起问题带回来
- 位置：§3.2 sc-velocity、M5-4、§7.3 第 7 条、§2.2.5。
- 问题：计划把薄壳末尾的 `killpg` 换成 `os._exit(0)`。脚本自己的注释写明，killpg 要解决两件事：TensorFlow 线程在解释器退出时卡住；loky worker 继承了管道 fd，父进程读不到 EOF。`os._exit(0)` 只结束 CLI 本身，worker 仍然握着 stdout 管道，而 `run_cli` 用 `for line in process.stdout` 一直读到 EOF。这样 kernel 不再被杀，步骤却可能一直挂到 worker 自己退出。另外，sc-velocity 现有的默认收集用例 `test_velocity_from_velocity_prep_output` 用不开新会话的 `subprocess.run` 跑 CLI，在装了 scvelo 的 OmicsClaw 环境里会把 pytest 一起杀掉。§2.2.5 是在没有 scvelo 的 rapids_singlecell 环境里跑的，那里这条被跳过，所以没发现。
- 证据：`skills/singlecell/scrna/sc-velocity/sc_velocity.py:920-933` 的注释和 killpg；`skills/_sdk/notebook/_skills.py:428-441`；`skills/singlecell/scrna/sc-velocity/tests/test_sc_velocity.py:78-87`（只有 `skipif(not _has_scvelo())`，没有 `start_new_session`）。这条用例我没有运行，因为它会杀掉调用方所在的进程组。
- 建议：薄壳退出前先结束自己的子进程，可以用 `psutil.Process().children(recursive=True)` 逐个 kill，或用 loky 的 `get_reusable_executor().shutdown(kill_workers=True)`，然后再 `os._exit(0)`。动手前在 `/tmp` 写一个"Popen 读管道到 EOF 并带超时"的探针，确认不会挂。M5-4 的新测试给 `run_cli` 设超时，并断言它按时返回。§2.2.5 补上这条用例，并写明 M5 修好之前不要在 OmicsClaw 环境里跑 sc-velocity 的测试。

## 3. 应改问题

1. M2 的位置和 PR 划分。
   - 位置：§6 依赖行、§0 第 4 条、S1。
   - 问题：计划写的是 M0 → M2 → M3 → … 的硬依赖，可 §5.6.1 自己说"skill 迁移本身并不依赖 R 步骤"。按 Q2 a，确实没有哪个迁移期需要 R 步骤，唯一用到它的是 M8 端到端第 4 条。把 4.5 天的运行层功能挡在 M3、M4 前面，会推迟方向 C v1 要用的 sc-batch-integration 和 sc-enrichment。
   - 建议：只要求 M2 在 M8 之前完成，具体排在哪里交 owner 定。§6 建议的 4 个 PR 里，M3 至 M5 一个 PR 就有约 21 天、15 个 skill，审查不现实，改成每期一个 PR。

2. 有一处行为改动没列入有意改动：基因集别名表统一。
   - 位置：§3.2 sc-pathway-scoring、§5.2、M4-1。
   - 问题：两份表里小鼠 KEGG 的版本不同，统一必然改变其中一个 skill 的结果。这条路径要联网读 Enrichr，parity 覆盖不到，Q6 的清单里也没有它。
   - 证据：`sc-pathway-scoring/sc_pathway_scoring.py:77` 是 `KEGG_2021_Mouse`，`_lib/stat_enrichment.py:21` 是 `KEGG_2019_Mouse`。
   - 建议：本批不统一，各用各的表；要统一就列为有意改动，写明选哪个版本。另有几处较小的改动也没列出：scvi 开始使用 `random_state`；CellPhoneDB 的默认种子从随机改成 0；harmony 在小数据上改为复用已有的 `X_pca`。它们都不影响 parity 用例，但会改变用户拿到的结果，应写进有意改动表。

3. 双细胞 R 脚本的修法。
   - 位置：§3.2 sc-doublet-detection、M3-2、R2。
   - 问题：改成 `reader = "R"` 后要依赖 rhdf5，本机没装，这个改动在本机验证不了，迁移后的 R 双细胞方法等于一次没跑过。
   - 证据：探针显示 rhdf5 缺失，DoubletFinder 2.0.6 和 scDblFinder 1.16.0 已装；试点的 `_lib/pseudobulk.py` 已经用 CSV 交换数据。
   - 建议：3 个脚本改用 Matrix Market 加 CSV 交换，这也符合 §5.1 第 5 条"优先 CSV 或 Matrix Market"。这样本机就能对 DoubletFinder 和 scDblFinder 跑 `requires_r` 测试，scds 留给 owner 的机器。另外问 owner：试点的 `sc_mast_de.R` 要不要同样处理？装了 MAST 的机器第一次调用它就会下载 basilisk。

4. 验收标准没有处理既有失败。
   - 位置：§6 SKILLCHECK、§2.2.5。
   - 问题：§2.2.5 只覆盖 rapids_singlecell 环境下的静态测试，而 SKILLCHECK 的 `-m demo` 和示例在 OmicsClaw 环境里跑，现在就有会失败的用例。sc-pathway-scoring 的 `test_demo_mode` 用默认的 `aucell_r`，本机缺 AUCell，按计划 §3.1 预检会以退出码 2 结束；sc-velocity 的用例会杀掉 pytest（B2）。
   - 证据：`sc-pathway-scoring/tests/test_sc_pathway_scoring.py:48-50`。
   - 建议：每个 skill 动手前，先在 HEAD 上跑 SKILLCHECK 的前两条，把既有失败记进交付记录。通过标准写成"除既有失败外全部通过"，并逐条说明每个既有失败是修了还是保留。

5. 生成器 demo 怎么记账没写。
   - 位置：§5.4 demo 注册表、M0-2。
   - 问题：`load_demo` 对文件求 sha256，记成 `input`（`_io.py:345-357`）。计划没说生成器的数据是先落盘再读，还是只在内存里生成。不落盘就没有哈希可记，过期判定看不到这份输入。另外，合成数据如果没有埋入已知结构，示例只能断言"跑通了"。
   - 建议：生成器把数据写进 demo 缓存目录（同名 `.h5ad`），之后和下载型数据一样读文件、记哈希。`multisample_synthetic` 埋一个已知富集的细胞类型，`perturbseq_synthetic` 埋一个已知的 KO 效应，让示例断言能把它们找回来。

6. `outliers_removed` 改名改在哪里。
   - 位置：§3.2 sc-filter、M1-1、M1 通过标准。
   - 问题：这个键在共享的 `_lib/qc.py:527-528` 里，试点 sc-preprocessing 和 scatac-preprocessing 都经它生成 `filter_summary`。在 `_lib` 里改名会悄悄改掉试点的 `run_info`，也和 §5.2"只修 upstream 一处"矛盾。此外 demo 数据没有 `outlier` 列（探针：跑完 sc-qc 后 `"outlier" in obs` 为 False），M1 通过标准里"`filter_stats.csv` 改名一列"在 parity 用例里根本不会出现。
   - 建议：只在 sc-filter 自己的代码里改名，通过标准改成一条输入带 `outlier` 列的单元测试。这一项也可以降为写进 Gotchas，因为它只是标签不准，不会产出错误结果。

7. 删除 sc-integrate-cluster 的改动清单不全。
   - 位置：§4.1。
   - 证据：`docs/core-features/agent-skills.md` 里除了 `:4`，还有 `:21`、`:27`、`:38`、`:134`（singlecell 31）、`:140`（合计 89）、`:220`、`:264`、`:324` 处计数；`:115` 的"其余 85 个 skill 还只有 CLI"每期都会变；`skills/singlecell/INDEX.md:11` 重新生成时也会变。
   - 问题：M3 验收只 grep skill 名字，漏改的计数查不出来。
   - 建议：补全清单，M3 验收再加一条 `git grep -nE '\b(89|31) (skills|个)'` 之类的计数检查。

8. 防线账有缺口。
   - 位置：§5.10。
   - 问题：job3 扩容、在 CI 装 r-base-core、Q12 都是加在 PR gate 上的检查，都没写防什么、旁路在哪、代价多少。G11 的旁路也少写了一种：Rscript 路径不变而 R 包升级了，G11 看不到，只能事后在 `r_session` 里查。
   - 建议：补上这几行。

9. Q11（M2-5）建议推迟，理由见第 6 节。

10. 计划的代码基准已经过期。
    - 审核期间有人在本工作树合入了 `4bd83b1e`（作者 zhou-1314，2026-10-07 02:31 UTC，含 `caaa906a`），从 22 个 CLI 里删掉了 `write_replot_hint`。
    - 影响：被引用的主脚本行号多数前移 1 到 2 行，例如 `sc_velocity.py` 的 killpg 现在在 `:929`，`sc_cell_communication.py` 的 `pvalue` 在 `:618`。`OMICSCLAW.md`、`llms.txt`、`agent-skills.md` 也改了其他段落。parity 不受影响，因为 `extract` 只取 `result.json` 的 `summary`。
    - 建议：第 7 行的基准改成 `4bd83b1e`，或注明行号以符号名为准。

11. 跨期共享改动前先录基线。§5.2 规定改共享 `_lib` 时要跑所有导入它的 skill 的测试，建议再加一句：改之前，先给导入该模块、尚未迁移的 skill 录好 parity 基线，否则它们之后录到的"旧 CLI 基线"已经包含这次改动。我按现有分期逐项核对过，实际受影响的只有一处：第 6 条如果改在 `_lib/qc.py` 里。代价很小。

## 4. 小问题

- `_percent._check_code` 实际在 `_percent.py:77-93`，计划写的是 `:73-91`。
- sc-differential-abundance 的 `--method` 在 `:533`，计划写 `:534`。
- `reference` 现在是 7,947 字符，计划写 7,948。
- GUARDS 在 `4bd83b1e` 上 803 passed、5 skipped、1 xpassed，用时 63.5 s；计划估的约 35 s 只是顶层 `tests/test_*.py` 部分。
- CellChat 其实已装（2.2.0.9001），只是加载失败（NMF 0.21.0 < 0.23.0），计划写成了"没有"。
- `sc_mast_de.R` 先执行 `library(MAST)` 再 `readH5AD`，本机缺 MAST 会先报错，不会触发下载；下载只会发生在装了 MAST 的机器上。
- 被 SIGKILL 杀掉的子进程，`subprocess.run` 返回的是 -9，不是 137；parity 工具"接受 137"应写成接受 `-signal.SIGKILL`。
- `snapshot.extract` 本来就能处理没有 `processed.h5ad` 的输出（`tests/parity/snapshot.py:118`），M0-1 不用为此新写代码。
- §4.1 否定备选 c 的理由不准：近邻和 leiden 在 `_lib/dimred.py`（`build_neighbor_graph`、`cluster_leiden`），不需要复制聚类代码。删除的结论不受影响。
- Q13 的参数名 `filter_cells` 和 sc-filter 的函数 `filter_cells` 同名，而且这个开关也会关掉基因过滤，建议改叫 `apply_filters`。
- `OMICSCLAW.md:89-91` 还写着步骤"named `<k>_<name>.py`""A step is a plain Python file"，加 R 那一条时这两句也要改。
- `format_step` 的表头固定打印 `python=...`（`_executor.py:86`），R 步骤应该显示 Rscript。
- R 步骤的 IO 行转成事件时要持有 `_watchdog.ACTIVITY.lock`，否则看门狗的 `run_end` 可能插在中间；`_ledger.read_run` 也要给 `r_session` 加一个桶，审查摘要才读得到。
- `_build_r_env` 会在 conda 前缀下 `mkdir` 一个 `omicsclaw-library` 目录（`r_script_runner.py:349`），sandbox 镜像只读时 R 步骤会因此失败。
- 要让 `OMICSCLAW_RSCRIPT` 生效，就得改 `_preferred_rscript_executable`，这会影响所有领域的 R 调用，M2 任务表里没有列。
- Q3 的命令缺 `sudo apt-get update`。如果 ubuntu-latest 镜像自带 R（未核实），job1 也会跑 `requires_r` 用例。
- r-base-core 不带 ggplot2，`test_rscript.py` 的 PNG 用例要走"无参函数加图片后缀"这条路。
- `step.R` 的 `read_input` 默认用 `readH5AD(reader = "R")` 读 `.h5ad`，本机缺 rhdf5，一用默认路径就会报错；建议报错信息直接提示改用 MTX/CSV。
- sc-standardize-input 的 `read_any(path)` 和"`_api.py` 不依赖 `smart_load`"这两句矛盾，要说明 `read_any` 用什么来读。
- G14 的测试还应断言名单里的 skill 都真实存在，防止 M3 删掉 sc-integrate-cluster 后名单里留下残项。
- M0 验收里的 `yaml.safe_load` 只检查语法。
- sc-grn 只走相关性路径，GRNBoost2 又和 dask 2026.1.1 不兼容（计划自己写过），job3 装 arboreto 没有用处。

## 5. 事实核查表

| # | 条目 | 计划的说法 | 结果 | 证据 |
|---|---|---|---|---|
| 1 | 执行器拒绝 R 步骤 | `_check_runnable`、`run_module` 返回 2，replay 也走前者 | 一致 | `_executor.py:268-276`、`:337-341`、`:511-513` |
| 2 | Python 写死的地方 | `run_start` 的 kind、stitch 与 `to_notebook` 的 kernelspec | 一致 | `_executor.py:166-176`、`:260-262`；`_percent.py:158-160` |
| 3 | 步骤与 validate 的正则只认 `.py` | | 一致 | `contract.py:29-30` |
| 4 | `r_files` 收 `.R`/`.r`，`resolve_target` 放行 `.R` | | 一致 | `_layout.py:94-97`、`:153-155` |
| 5 | `StepRunner` 协议、kernel 进程组 kill | | 一致 | `_runners.py:45-47`、`:113-124` |
| 6 | `interpreter_info` 只记 Python，manifest 的 kind 写死 | | 一致 | `_manifest.py:57-68`；`step_entry` |
| 7 | `_check_code` 会把 R 的 `!` 行误报 | | 一致，行号偏 4 | `_percent.py:77-93` |
| 8 | `step_context` 只认 `.py` | | 一致 | `_io.py:65-74` |
| 9 | `RScriptRunner` 不开新会话；`_build_r_env` | | 一致 | `r_script_runner.py:256-262`、`:316-372` |
| 10 | `run_cli` 不开新会话，CLI 与 kernel 同组 | | 一致；kernel 由 jupyter_client 以新会话启动 | `_skills.py:428-431`；`jupyter_client/launcher.py:151` |
| 11 | sc-velocity 退出时 killpg | | 一致 | `sc_velocity.py:921-933` |
| 12 | `skill_load` 用 `importlib.metadata` 记依赖版本 | | 一致 | `_skills.py:130-137` |
| 13 | 共享 R 脚本 28 个，文件名冻结 | | 一致 | `test_public_surface.py:134-135` |
| 14 | 用默认读取器的 6 个脚本 | | 一致 | grep `readH5AD` |
| 15 | sc-de mast 路径会触发 basilisk | | 一致，有前提：`library(MAST)` 在前，本机先失败 | `sc-de/_api.py:325-356`；`sc_mast_de.R:14-17`、`:39` |
| 16 | `environment.yml:206` 声明了 rhdf5 但本机没装；MAST 等未声明 | | 一致 | `environment.yml`、`0_setup_env.sh`；R 探针 |
| 17 | 本机 R 包清单 | CellChat 等"没有" | 基本一致；CellChat 已装但加载失败 | R 探针 |
| 18 | requires 扫描不看 `_api.py` | | 一致；扩到试点 `_api.py` 只多出两条已在 EXCEPTIONS 里的 | `test_skill_requires_are_declared.py:113`；探针 |
| 19 | 计算调 R 的 9 个、含画图 17 个、24 个有 `--r-enhanced`、其中 7 个不做事 | | 一致 | grep 统计 |
| 20 | 两个环境都缺的 Python 后端 | | 一致 | 两个环境逐包 `find_spec` |
| 21 | CI job1、job3 的内容 | | 一致 | `eval.yml:37-46`、`:48-85` |
| 22 | pytest 配置与 demo 自动标记 | | 一致 | `pyproject.toml:379`、`:380-407`、`:411`；`conftest.py:20-41` |
| 23 | API 段测试、示例测试 | | 一致 | `test_skill_api_sections.py:17-20`、`:39-41`；`test_skill_examples.py:24-27`、`:44` |
| 24 | parity 工具 | | 一致；`extract` 已能处理缺 h5ad | `tests/parity/snapshot.py:35-49`、`:71-77`、`:107-139` |
| 25 | 既有失败 11 failed、21 passed | | 一致（复跑） | 第 8 节 |
| 26 | sc-filter 示例得到 2,638 个细胞，与 `pbmc3k_processed` 相同 | | 一致 | 探针：集合与顺序都相同 |
| 27 | `outliers_removed` 统计的是只标记、没去掉的细胞 | | 一致 | `_lib/qc.py:331-388`、`:527-528` |
| 28 | preprocess 无开关地再过滤一次 | | 一致；Seurat 路径传的是宽松阈值 | `sc-preprocessing/_api.py:325-331`、`:148-152` |
| 29 | cosg 的 p 值填 0.0，过滤结果为空时回退 | | 一致 | `_lib/markers.py:107-131`、`:347-348`；`sc-markers/SKILL.md:63` |
| 30 | liana 的 `pvalue` 取自 `specificity_rank` | | 一致 | `sc_cell_communication.py:619` |
| 31 | scTenifoldKnk 写死 R 4.1 的库路径 | | 一致 | `sc_in_silico_perturbation.py:355-363` |
| 32 | pseudotime 导入时关 JIT，`use_rep` 优先 UMAP，与预检不一致 | | 一致 | `sc_pseudotime.py:15`、`:274-278`；`preflight.py:1164-1192` |
| 33 | GSEA 的 `seed=TRUE` 在新会话里失败 | | 一致（读代码） | DOSE `GSEA_fgsea` 体内是 `if (seed) set.seed(.Random.seed)`；`sc_clusterprofiler_enrichment.R:97` |
| 34 | 两处伪造基因集的回退 | | 一致 | `sc_gsea_r.R:313-345`、`sc_gsva_r.R:135-148` |
| 35 | batch-integration 的 demo 批次没有种子 | | 一致 | `sc_integrate.py:918` |
| 36 | `smart_load` 读 loom 报 TypeError | | 一致 | `_lib/io.py:388-389`、`:168-172`；`sc_standardize_input.py:288` |
| 37 | FastQC 收到未解析的相对路径 | | 一致（读代码） | `_lib/upstream.py:549-557` |
| 38 | sc-integrate-cluster 的从属说法，且没有调用方 | | 一致 | `SKILL.md:17`、`:25-26`；grep |
| 39 | 删除时要改的计数 | | 部分一致：漏了 `agent-skills.md` 多处 | grep（应改第 7 条） |
| 40 | 测试里断言 89 | | 一致 | `test_bootstrap.py:86-88`、`test_help_probe.py:23`、`test_dependencies_section.py:26` |
| 41 | eval 种子要求 harmony 写法 | | 一致 | `tests/evals/test_fixtures.py:87-104`；`live_routing_seed.json` |
| 42 | `reference` 长度 | 7,948 | 7,947 | 探针 |
| 43 | pseudotime 有 1,022 个 inf、liana 报 806 个显著 | | 未核实（需要跑 CLI，没跑） | 无 |
| 44 | 默认引擎下 GSEA 恒为 0 条 | | 机制已从代码确认；条数沿用子 agent 的日志 | `/tmp/inv_C/log_sc-enrichment_gsea_auto.txt`（significant_terms=0） |

## 6. 对 Q1 至 Q13 的意见

| 问题 | 意见 | 理由 |
|---|---|---|
| Q1 | 同意 a | 理由成立，但要补全删除清单（应改第 7 条）。§4.1 否定 c 的理由不准，结论不变。 |
| Q2 | 同意 a | 试点做法本来就覆盖 API 段、桩和记账。建议契约写明：skill 的 R 方法从 Python 步骤调用函数，不要在 R 步骤里 `system2("Rscript", ...)` 直接跑 skill 的 R 脚本。 |
| Q3 | 有条件同意 a | 先确认 ubuntu-latest 是否自带 R（未核实）；命令补上 `apt-get update`；PNG 用例改用 base graphics。 |
| Q4 | 同意 a 的主体，sc-perturb 例外暂缓 | 核实 pertpy 是否会拉进 torch/jax 之前，不要承诺在 job3 里装它。备选：sc-perturb 的示例只在 owner 机器上跑，作为 S2 的书面例外交 owner 定。 |
| Q5 | 同意 a | 去掉伪 p 值、改名都是正确的；CLI 输出的变化已列入有意改动。 |
| Q6 | 同意 a，清单要补 | 补别名表统一、scvi 种子、CellPhoneDB 默认种子、harmony 在小数据上复用 `X_pca`；`outliers_flagged` 改名放在 sc-filter 自己的代码里。 |
| Q7 | 同意 a | pilot 测的就是这个不对称，现在加提醒等于改了实验条件。 |
| Q8 | 部分同意 | paul15 同意。速度示例建议用 `scvelo.datasets.simulation`：离线，没有许可问题，也不用缓存 52 MB；这样 `("scvelo", ...)` 这种下载源类型就不用做。 |
| Q9 | 同意 a | R 端种子修好之后，剩下的理由是结果不该随机器上装了哪些 R 包而变；CHANGELOG 要写明 CLI 的默认结果会变。 |
| Q10 | 同意 a | |
| Q11 | 不同意，推荐 b（推迟） | 它属于 provenance 增强，和 0073 的 C1、C2 同类，那两项都不在本批。从 R 脚本文本里猜包名也不可靠；以后要做，可以直接用 `validate_r_environment(required_r_packages=...)` 里已有的包列表。 |
| Q12 | 部分同意 | 只跑不起 CLI 的用例。15 条默认收集的用例会起 CLI，在 CI 里会重新下载数据；sc-velocity 的用例在 M5 修好前会杀掉 pytest。"1 分钟以内"的估计没有依据。 |
| Q13 | 同意 a | 参数改名为 `apply_filters` 之类。 |

计划漏掉、应该问 owner 的问题：
- M2 是否必须排在 M3 之前。按 Q2 a，两者没有依赖关系。
- job3 能装多重的依赖（torch、jax、pertpy），版本是否钉死，重的示例要不要放进不做 gate 的扩展 job。
- R 方法的数据交换用 MTX/CSV 还是 `reader = "R"`；试点的 `sc_mast_de.R` 是否一起处理。
- sc-count、sc-velocity-prep 是部分迁移，还是本批先列入 `CLI_ONLY`。
- `/root/.cache/R/basilisk` 里 2.3 GB 的半成品目录删不删。计划正文提到了，但没有列成待裁定问题。

## 7. 建议砍减或推迟的内容

| 项目 | 建议 | 省下 |
|---|---|---|
| sc-count、sc-velocity-prep | 本批列入 `CLI_ONLY`，只改 SKILL.md。理由同 sc-fastq-qc：示例跑不到外部工具，读取器只是 scanpy/scvelo 读取器的一层薄包装 | 约 1.3 天 |
| M2-5（Q11） | 推迟到 0073 的 C 系列小计划 | 约 0.5 天 |
| R 驱动的细节 | 只做逐 cell 标记和出错 cell 的序号，调用栈裁剪和语法错误行号换算以后再做；G11 改为只警告 | 约 0.5 天 |
| DEMOS 改造 | 不改成三类 `source`。paul15 本来就是 scanpy 数据集，保留 `download` 写法，只新增 `generator`；速度示例用 simulation | 约 0.5 天 |
| `_lib/stat_enrichment` 共用基因集加载 | 推迟，同时避开应改第 2 条的行为改动 | 约 0.3 天 |
| sc-perturb 在 CI 装 pertpy | 推迟到核实依赖树之后 | 约 0.3 天 |

另外需要新增的工作：双细胞脚本改用 MTX/CSV（+0.3 天）；每个 skill 动手前在 HEAD 上跑一遍测试（+0.3 天）；CI 钉版本并记录首跑耗时（+0.2 天）；sc-velocity 子进程清理的探针（+0.2 天）。合计约 +1 天。

砍完后名义工作量从 38.5 天降到约 36 天。每个 skill 的估计和 0070 试点相当：试点约 1.1 天/skill，CLI 有 800 到 1,700 行，与这批同一量级，所以总数可信。偏乐观的是 L 级 skill 和 M0：parity 注册表、两次录制、demo 改造、两道守卫、模板、CI 加在一起只给了 2 天。R13 设的 30% 告警线合适。

## 8. 运行过的命令与探针

- 读代码：用 `sed`、`grep`、`cat` 读计划引用的文件，以及 `git log`、`git diff 915289d3 HEAD --stat`。
- R：执行 `Rscript --no-init-file -e`，用 `system.file` 和 `packageDescription` 查包，不加载包；`requireNamespace("CellChat")` 调过一次，加载失败，没有下载；读了 DOSE 里 `GSEA_fgsea` 的函数体（会加载 DOSE 命名空间）。
- Python 探针，放在 `/tmp/rv0074`，已删除：
  - `probe_g15.py`：把 requires 扫描扩到 `_api.py`；
  - `probe_filter.py`：对本地 `data/pbmc3k_*.h5ad` 跑 sc-qc 加 `apply_threshold_filtering(tissue="pbmc")`；
  - `sub.py`：统计默认收集的 skill 用例里有多少会起 CLI；
  - 另用 `importlib.metadata` 和 `find_spec` 查了包和依赖。
- pytest：
  - 7 个 skill 的静态测试，rapids_singlecell 环境：11 failed、21 passed；
  - 26 个 skill 测试目录 `--collect-only`，OmicsClaw 环境：默认收集 88 条，共 127 条；
  - 计划的 GUARDS 整组，rapids_singlecell 环境，在 `4bd83b1e` 上：803 passed、5 skipped、1 xpassed，63.5 s。
- pytest 都带了 `-p no:cacheprovider` 和 `PYTHONDONTWRITEBYTECODE=1`。前两个 Python 探针没设这个变量，可能在已被 git 忽略的 `__pycache__` 里留下了 .pyc。
- 没有运行任何 skill CLI，没有跑 R 双细胞、mast 或任何 zellkonverter 读取，没有碰 `/root/.cache/R/basilisk`，没有 pip、conda 或 R 安装，没有联网。
- `git status --porcelain` 自始至终只有计划文件这一个未跟踪文件，`data/` 的时间戳没有变化。HEAD 的变化来自审核期间别人在本工作树的合入，与本次审核无关。
