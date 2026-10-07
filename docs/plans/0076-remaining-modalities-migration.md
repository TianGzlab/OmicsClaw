# 0076 剩余模态函数库迁移

用户确认沿用 0074、0075 的方式，完成 bulk RNA-seq、基因组、蛋白组、代谢组，另行分类文献技能。基线为 `main` 的 `f97f38c1`，工作分支为 `feat/remaining-modalities-migration`。

## 范围

| 批次 | 数量 | 交付要求 | 状态 |
|---|---:|---|---|
| bulk RNA-seq | 14 | 14 个函数库，包括已有比对结果的读取和统计 | 本地验收通过 |
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

本轮新增 40 个函数库和 41 个可执行示例。全仓库为 83 个函数库、5 个 CLI-only 技能，索引共 88 个、0 skipped。实现、独立审核修复及最终整合回归均已完成。

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

基础 conda 环境未修改。初轮 Python 科学测试使用 `/opt/conda/envs/OmicsClaw/bin/python`；示例使用独立 venv `/tmp/omicsclaw-0075-ci.huDrtZ/venv/bin/python`，R 后端通过显式 `CONDA_PREFIX` 指向已有科学环境。新增 CI job 从 `environment.yml` 的同名 conda 包安装 R/WGCNA/sva/survival/DESeq2。远端和干净 checkout 的补验收见下节。

- 审核修复后，全批旧 CLI/API 对比 121 passed、3 skipped，202.24 秒。跳过项是旧 WGCNA 无成功基线对应的 CLI/API 两项，以及 XCMS 无 API 一项。61 个实际基线均核验为 `f97f38c1`、两次确定性录制，没有整个案例仅作结构比较。
- 最终 41 个新示例全部经 step runner 和 fresh-kernel replay 通过，243.88 秒，核对输出文件、表格哈希及重放状态。
- 最终 SDK、技能、依赖环境和 parity 工具回归 1,307 passed、6 skipped、101 deselected、2 xpassed，219.23 秒。两项 XPASS 为原有环境相关标记，不是新增失败。
- 基因组：18 项公开 API、10 项 CLI、24 项旧 CLI/API 对比、10 个 fresh replay 通过。
- 蛋白组：32 项域测试、28 项旧 CLI/API 对比、8 个 fresh replay 通过。
- 代谢组：19 个旧 CLI case 与 18 个 API case 逐值通过，XCMS API 不适用；8 个 fresh replay 通过。
- bulk 主批六技能：16 项旧 CLI/API 对比、27 项目录测试通过；后续补零支持信号、Figure/IO/RNG 和真实 DESeq2 测试，计入最终回归。
- bulk read 三技能：11 项目录测试、6 项旧 CLI/API 对比、3 个 fresh replay 通过。
- API 文档、依赖计数和注册契约最终阶段检查 246 项通过；索引重建及检查 8 项通过。
- 框架最终完整回归 5,815 passed、16 skipped、3 xfailed，165.70 秒。之后两个代谢技能路由描述更新，域索引重新生成并复检 8 项通过。
- 五域完整目录测试在审核修复前 246 passed，500.04 秒；修复后代谢组、结构蛋白组及 CI 示例选择守卫共 42 passed。修复只影响这两域中的三个技能。当前五域共收集到 258 项，不把收集数当通过数。
- 文档、索引、依赖注册、依赖计数和示例选择检查最终 256 passed，3.32 秒。CI job 按域而非 `sc-` 名称前缀选择例子，避免把旧 `scatac-preprocessing` 误放进剩余模态依赖环境。
- 并行实现期间曾出现未生成 API 文档、未更新索引和旧依赖数量断言的失败，均已补齐；保留最终完整回归结果，不把这些中间运行作为交付通过证据。

### 独立审核

固定基线 `f97f38c1`；Standards 与 Spec 由未参与实现的两个子 agent 分别审核。需求依据为本计划及用户确认的三个验收入口。审核覆盖实现提交 `b3cfb738` 及后续工作区修复。

#### Standards

发现 2 项，均已独立复核关闭，无未解决的硬违规。

- P1：代谢通路缺参考时自动使用 demo pathway。API、内部计算和真实 CLI 现均要求显式参考；demo 显式传入示例库并记录来源。同类 annotation 路径、使用示例、参考文档和模型路由描述同步修复。
- P2：贡献指南未同步范围。`CONTRIBUTING.md` 现与 README、AGENTS 一致，说明 83 个函数库、5 个 CLI-only 技能及验收流程。

审核 agent 独立运行两技能 API/CLI 14 项及两个 step/fresh replay，全部通过。域索引随后由主 agent 生成并复检。未另报代码异味建议。

#### Spec

发现 2 项，均已独立复核关闭，无额外范围扩张问题。

- P1：与 Standards 同一缺参考问题；真实 pathway CLI 现在要求 `--pathway-file`，API 必须显式传入参考，demo 单独选择示例集合。
- P2：结构蛋白组的部分缺失距离原被标为失败并计入比例分母。现缺测为 NA，比例只计算有效距离；全缺测的计数和统计为标准 JSON null。API 与真实 CLI 回归包含严格 JSON 解析。

审核 agent 独立验证目录分类和 loader，运行 18 项代表性科学及接口测试（含真实 R，无跳过）、7 项结构蛋白组修复测试、7 项通路修复及示例测试，全部通过。

两轴各发现 2 项、各开放 0 项；最严重问题均为已关闭的 P1 缺参考时采用 demo 数据。

### 复现

```bash
# science_python 使用现有科学环境；ci_python 使用独立 Python venv。
"$science_python" -m pytest skills/bulkrna skills/genomics skills/proteomics \
  skills/metabolomics skills/literature --import-mode=importlib -q -o addopts=""
"$science_python" -m pytest tests/parity/test_sc_parity.py \
  -k 'bulkrna or genomics or proteomics or metabolomics or literature' -q -o addopts=""
CONDA_PREFIX=/opt/conda/envs/OmicsClaw OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 "$ci_python" -m pytest \
  tests/sdk/notebook/test_skill_examples.py -m skill_example_remaining -q -o addopts=""
"$science_python" -m pytest tests/sdk tests/skills tests/skillenv tests/parity/test_snapshot.py \
  --import-mode=importlib -m 'not slow and not skill_example' -q -o addopts=""
```

迁移已合并到 `main` 并推送，交付提交为 `8d8ad9ef`。实时 MyGene/STRING/DOI/PubMed 和真实 PDF/GEO 下载仍未作端到端验收。另一会话的演示文稿和 CHANGELOG 条目保留，不纳入此次提交。

## 远端 CI 和干净 checkout 补验收

2026-10-07，用户要求补齐远端 CI 和干净 checkout 验收，修复基线为 `8d8ad9ef`。原工作区同时有演示文稿和 Desktop 修改；本次在独立 worktree 实施，只从提交创建验收 checkout。

### 发现与修复

- [初轮远端 CI](https://github.com/zhou-1314/OmicsClaw/actions/runs/37611272965) 有两个失败 job。五域测试的八个失败源于六个合成基因组示例被 `*.vcf`、`*.sam`、`*.fastq` 忽略；单测的一个失败源于 phasing API 拒绝合法的零记录 VCF，破坏原 CLI 空表输出契约。
- `6df935ca` 提交六个小型合成示例，并为其增加精确路径例外，真实数据的忽略规则不变。phasing 计算允许带完整列名的空表；其他计算和空表绘图仍拒绝空输入。干净 checkout 先复现缺文件和旧 CLI 的失败，新 API 空输入回归也先失败，再修复。
- [修复后的远端 CI](https://github.com/zhou-1314/OmicsClaw/actions/runs/37616083907) 中，五域、单细胞、空间和 extended CPU job 全部通过。单测暴露另一个请求超时竞态：同步 EOF 超过截止时间时，事件循环可能尚未调度超时回调，session 因而误判成功。OpenAI、Anthropic 两条路径的确定性用例均先失败；流结束前补充时间核对后，provider、engine 和 deadline 共 712 项通过。
- 新 venv 的完整本地单测还暴露 CLI 测试依赖外部 API 的问题。错误路径改用本机 HTTP 401，仍验证 REPL 存活、单次请求非零退出和无 traceback；仅观察首启配置提示的用例直接退出，不发模型请求。46 项 launch/configuration 测试通过。未新增 skip、xfail 或放宽断言。

### 干净 checkout 证据

从 `6df935ca` 新建 `/tmp/omicsclaw-ci-acceptance.NPluim/verify`，运行前后 `git status --porcelain --untracked-files=all` 均为空。新建不继承系统包的 venv `/tmp/omicsclaw-ci-acceptance.NPluim/venv`，将此 checkout 安装为 editable，并核对 `omicsclaw.__file__` 和 `skills._sdk.__file__` 均指向该 checkout。未复制原工作区的忽略文件、`.env`、golden 或演示文稿。`pip check` 无冲突；R 使用已有 `/opt/conda/envs/OmicsClaw`，基础环境未修改。

- 五域按 CI 的路径和 marker 选择：215 passed、45 deselected，327.72 秒，无跳过。
- 41 个示例执行及 fresh-kernel replay：41 passed、46 deselected，239.24 秒。
- Scripted eval：29 passed，14.00 秒。
- 完整单测首次在外部 API 错误路径超时，未作为通过证据。修复 EOF 竞态和 CLI 测试隔离后，需要从最终提交再跑完整单测和远端 CI。

Python 3.11.15；NumPy 2.0.2、pandas 2.3.3、AnnData 0.12.11、SciPy 1.17.1、scikit-learn 1.9.1、nbclient 0.11.0、gseapy 1.2.1。完整环境快照和命令输出保留在 `/tmp/omicsclaw-ci-acceptance.NPluim/`，远端的独立安装及测试记录见上述 Actions 链接。
