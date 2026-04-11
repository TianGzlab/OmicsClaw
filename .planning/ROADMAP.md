# Roadmap: OmicsClaw scRNA R Enhanced Gallery

## Milestones

- ✅ **v1.0 scRNA Python 全覆盖** - Phases 1-12 (shipped 2026-04-10)
- 🚧 **v2.0 R Enhanced Gallery** - Phases 13-18 (in progress)

## Phases

<details>
<summary>✅ v1.0 scRNA Python 全覆盖 (Phases 1-12) — SHIPPED 2026-04-10</summary>

### Phase 1: 模版对齐 — sc-differential-abundance
**Goal:** 对齐 SC-DEVELOPMENT-CHECKLIST，补 UX guardrail，验证 simple/milo/sccoda Python 输出
**Requirements:** ALIGN-01
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. Python 路径跑通 pbmc3k 数据
  2. processed.h5ad + figures + report.md + result.json 全部生成
  3. 通过 SC-DEVELOPMENT-CHECKLIST 所有项
  4. UX: degenerate output 检测 + actionable error messages
**Plans**: Complete

### Phase 2: 模版对齐 — sc-metacell
**Goal:** 对齐模版，补 preflight/output contract，验证 kmeans/seacells Python 输出
**Requirements:** ALIGN-02
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. kmeans 和 seacells 方法跑通
  2. 输出 metacell assignment 合理（非全 NaN）
  3. 通过 SC-DEVELOPMENT-CHECKLIST
  4. UX guardrail 到位
**Plans**: Complete

### Phase 3: 模版对齐 — sc-gene-programs
**Goal:** 对齐模版，补 preflight/output contract，验证 nmf/cnmf Python 输出
**Requirements:** ALIGN-03
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. nmf 和 cnmf 方法跑通
  2. gene program 输出有意义（非空）
  3. 通过 SC-DEVELOPMENT-CHECKLIST
  4. UX guardrail 到位
**Plans**: Complete

### Phase 4: 标准化 — sc-velocity + sc-velocity-prep
**Goal:** 对照模版标准化 velocity 相关 skill
**Requirements:** STD-01, STD-02
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. sc-velocity-prep 处理 spliced/unspliced layers 正确
  2. sc-velocity scvelo 方法跑通
  3. velocity stream plot 生成且合理
  4. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 5: 标准化 — sc-grn
**Goal:** 对照模版标准化 GRN skill，测试 Python GRN 方法
**Requirements:** STD-03
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. Python GRN 方法（GRNBoost2/pySCENIC）跑通
  2. regulon 输出非空
  3. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 6: 标准化 — sc-cell-communication
**Goal:** 检查 liana 等 Python 方法，对齐模版
**Requirements:** STD-04
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. Python 通信方法（liana/cellphonedb）跑通
  2. ligand-receptor interaction 结果非空
  3. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 7: 标准化 — sc-ambient-removal
**Goal:** 对照模版标准化，测试 Python 去环境 RNA 方法
**Requirements:** STD-05
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. Python ambient removal 方法跑通
  2. 输出 cleaned counts 合理
  3. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 8: 标准化 — sc-perturb + sc-perturb-prep
**Goal:** 对照模版标准化扰动分析 skill
**Requirements:** STD-06, STD-07
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. sc-perturb-prep 数据准备流程跑通
  2. sc-perturb Mixscape 等 Python 路径跑通
  3. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 9: 标准化 — sc-in-silico-perturbation
**Goal:** 对照模版标准化 in-silico 扰动 skill
**Requirements:** STD-08
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. Python 路径跑通
  2. perturbation score 输出合理
  3. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 10: 标准化 — sc-fastq-qc + sc-count + sc-multi-count
**Goal:** 对照模版标准化上游 QC 和计数 skill
**Requirements:** STD-09, STD-10, STD-11
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. sc-fastq-qc 输出 QC 报告
  2. sc-count 处理计数矩阵正确
  3. sc-multi-count 多样本计数正确
  4. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 11: 标准化 — sc-standardize-input
**Goal:** 对照模版标准化输入标准化 skill
**Requirements:** STD-12
**Depends on:** —
**Success Criteria** (what must be TRUE):
  1. 各种输入格式（h5ad/h5/mtx/csv）正确转换
  2. 输出 standardized AnnData 格式正确
  3. 通过 SC-DEVELOPMENT-CHECKLIST + UX
**Plans**: Complete

### Phase 12: 最终报告与整合验证
**Goal:** 生成全覆盖报告，验证 skill 间数据流的一致性
**Requirements:** 全部
**Depends on:** Phase 1-11
**Success Criteria** (what must be TRUE):
  1. 每个 skill 的状态总结（通过/修复/跳过/阻塞）
  2. 修改内容清单
  3. 端到端 pipeline smoke 通过
  4. 报告提交
**Plans**: Complete

</details>

---

### 🚧 v2.0 R Enhanced Gallery (In Progress)

**Milestone Goal:** 补全 R 分析方法 + R Enhanced 绘图能力，让每个 skill 都能用 R 画出高质量图

## Phase Details

### Phase 13: R Enhanced Framework Foundation
**Goal**: Users can call R plotting from Python through a stable registry — ggplot2 is pinned and a round-trip test passes
**Depends on**: Nothing (milestone entry point)
**Requirements**: FW-01, FW-02, FW-03
**Success Criteria** (what must be TRUE):
  1. `call_r_plot()` executes registry.R with figure_data CSV input and writes PNG to figures/r_enhanced/
  2. ggplot2 3.5.2 is pinned in OMICSCLAW_R_LIBS and the `+` operator works correctly (no S7 breakage)
  3. R script failure produces a Python warning, not a crash — Python standard figures are unaffected
  4. SC-DEVELOPMENT-CHECKLIST.md and SC-SKILL-TEMPLATE.md contain R Enhanced checklist items
**Plans**: 2 plans
Plans:
- [x] 13-01-PLAN.md — ggplot2 pin + viz/r/ R layer (common.R, registry.R) + Python call_r_plot() wrapper + round-trip test
- [x] 13-02-PLAN.md — SC-DEVELOPMENT-CHECKLIST.md and SC-SKILL-TEMPLATE.md R Enhanced sections

### Phase 14: Shared Embedding and Marker Plots
**Goal**: All skills that produce embeddings or marker gene results can generate publication-quality R plots from their figure_data CSVs
**Depends on**: Phase 13
**Requirements**: SP-01, SP-02, SP-03
**Success Criteria** (what must be TRUE):
  1. embedding.R produces a cell scatter plot with discrete cell-type colors and cluster labels from embedding CSV (CellDimPlot equivalent)
  2. embedding.R produces a continuous feature expression overlay on the embedding with viridis colorscale (FeatureDimPlot equivalent)
  3. markers.R produces a grouped heatmap of marker genes across clusters from marker CSV (GroupHeatmap equivalent using ComplexHeatmap)
  4. All three plots are verifiable by opening the PNG — axes labeled, legend present, no blank output
**Plans**: 2 plans
Plans:
- [ ] 14-01-PLAN.md — embedding.R: discrete cell-type scatter + continuous feature overlay (SP-01, SP-02)
- [x] 14-02-PLAN.md — markers.R: ComplexHeatmap grouped marker heatmap (SP-03)

### Phase 15: R Analysis Methods
**Goal**: Users can run 4 new R-backed analysis methods (monocle3, gsea, gsva, proportion_test) that produce results merged back into the AnnData object
**Depends on**: Phase 13
**Requirements**: RM-01, RM-02, RM-03, RM-04
**Success Criteria** (what must be TRUE):
  1. `--method monocle3_r` in sc-pseudotime runs Monocle3 via R bridge, pseudotime scores are written to adata.obs, and Python standard trajectory plot is generated
  2. `--method gsea_r` in sc-enrichment runs fgsea/clusterProfiler, enrichment scores are non-NaN, and Python standard enrichment plot is generated
  3. `--method gsva_r` in sc-enrichment runs GSVA, group-level pathway scores are written to adata.uns, and Python standard plot is generated
  4. `--method proportion_test_r` in sc-differential-abundance runs base R permutation test, p-values are written to result, and Python standard plot is generated
**Plans**: 4 plans
Plans:
- [x] 15-01-PLAN.md — gsea_r: clusterProfiler + fgsea R bridge → sc-enrichment (RM-02)
- [x] 15-02-PLAN.md — proportion_test_r: base-R permutation test → sc-differential-abundance (RM-04)
- [ ] 15-03-PLAN.md — gsva_r: GSVA install + group-level scoring → sc-enrichment (RM-03)
- [ ] 15-04-PLAN.md — monocle3_r: monocle3 install + principal graph → sc-pseudotime (RM-01)

### Phase 16: Trajectory and Enrichment R Enhanced Plots
**Goal**: sc-pseudotime and sc-enrichment skills generate R Enhanced plots that show trajectory curves and enrichment landscapes not available in Python
**Depends on**: Phase 14, Phase 15
**Requirements**: SK-03, SK-04, SK-05, SK-06, SK-07
**Success Criteria** (what must be TRUE):
  1. pseudotime.R LineagePlot outputs a trajectory curve with loess smoothing overlaid on the embedding scatter, readable PNG
  2. pseudotime.R DynamicPlot outputs a gene expression trend over pseudotime with confidence interval ribbon — this plot has no Python equivalent
  3. enrichment.R EnrichmentPlot outputs a bar/dot plot of enriched terms ranked by significance
  4. enrichment.R GSEAPlot outputs a classic mountain plot (running score + hit positions) for a single gene set
  5. enrichment.R GSEAPlot comparison outputs a multi-group NES heatmap
**Plans**: 2 plans
Plans:
- [x] 16-01-PLAN.md — pseudotime.R: LineagePlot (trajectory + loess) + DynamicPlot (gene trend + CI ribbon) (SK-06, SK-07)
- [x] 16-02-PLAN.md — enrichment.R: EnrichmentPlot bar + GSEAPlot mountain + GSEAPlot NES heatmap (SK-03, SK-04, SK-05)

### Phase 17: CCC, Velocity, and DE R Enhanced Plots
**Goal**: sc-cell-communication, sc-velocity, sc-de, and sc-markers skills generate R Enhanced plots that enhance visualization of interactions, dynamics, and differential expression
**Depends on**: Phase 14
**Requirements**: SK-01, SK-02, SK-08, SK-09, SK-10
**Success Criteria** (what must be TRUE):
  1. de.R volcano plot labels top differentially expressed genes and uses ggplot2 color coding (up/down/ns), readable PNG
  2. de.R FeatureHeatmap outputs a ComplexHeatmap of expression across groups with annotation tracks
  3. communication.R CCCHeatmap outputs a heatmap or dot plot of ligand-receptor interaction strengths between cell types
  4. communication.R CCCNetworkPlot outputs a network arc diagram of cell-cell communication edges using ggplot2
  5. velocity.R VelocityPlot outputs an RNA velocity stream or grid overlay on the embedding
**Plans**: 3 plans
Plans:
- [ ] 17-01-PLAN.md — de.R: volcano plot (SK-01) + FeatureHeatmap (SK-02)
- [ ] 17-02-PLAN.md — communication.R: CCCHeatmap (SK-08) + CCCNetworkPlot (SK-09)
- [ ] 17-03-PLAN.md — velocity.R: VelocityPlot grid mode (SK-10)
**UI hint**: yes

### Phase 18: Skill Wiring — --r-enhanced Flag Across All Skills
**Goal**: Every targeted skill accepts --r-enhanced and invokes the R Enhanced plotting pipeline after Python standard figures are complete
**Depends on**: Phase 16, Phase 17
**Requirements**: SK-11
**Success Criteria** (what must be TRUE):
  1. Running any of the 12 targeted skills with `--r-enhanced` flag generates figures in figures/r_enhanced/ without disrupting figures/ Python outputs
  2. Running without `--r-enhanced` flag produces identical output to pre-milestone behavior (no regression)
  3. An R plotting failure during `--r-enhanced` run prints a warning to stdout and continues — result.json still written as success
  4. Demo mode with `--r-enhanced` runs end-to-end without manual intervention on all 12 targeted skills
**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. 模版对齐 sc-differential-abundance | v1.0 | - | Complete | 2026-04-10 |
| 2. 模版对齐 sc-metacell | v1.0 | - | Complete | 2026-04-10 |
| 3. 模版对齐 sc-gene-programs | v1.0 | - | Complete | 2026-04-10 |
| 4. 标准化 sc-velocity | v1.0 | - | Complete | 2026-04-10 |
| 5. 标准化 sc-grn | v1.0 | - | Complete | 2026-04-10 |
| 6. 标准化 sc-cell-communication | v1.0 | - | Complete | 2026-04-10 |
| 7. 标准化 sc-ambient-removal | v1.0 | - | Complete | 2026-04-10 |
| 8. 标准化 sc-perturb | v1.0 | - | Complete | 2026-04-10 |
| 9. 标准化 sc-in-silico-perturbation | v1.0 | - | Complete | 2026-04-10 |
| 10. 标准化上游 QC | v1.0 | - | Complete | 2026-04-10 |
| 11. 标准化 sc-standardize-input | v1.0 | - | Complete | 2026-04-10 |
| 12. 最终验证 | v1.0 | - | Complete | 2026-04-10 |
| 13. R Enhanced Framework Foundation | v2.0 | 2/2 | Complete   | 2026-04-11 |
| 14. Shared Embedding and Marker Plots | v2.0 | 1/2 | In Progress|  |
| 15. R Analysis Methods | v2.0 | 2/4 | In Progress|  |
| 16. Trajectory and Enrichment R Enhanced Plots | v2.0 | 2/2 | Complete   | 2026-04-11 |
| 17. CCC, Velocity, and DE R Enhanced Plots | v2.0 | 0/? | Not started | - |
| 18. Skill Wiring --r-enhanced Flag | v2.0 | 0/? | Not started | - |

---
*Last updated: 2026-04-11 after Phase 16 plan creation*
