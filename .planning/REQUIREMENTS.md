# Requirements — Milestone v2.0 R Enhanced Gallery

## R Enhanced Framework

- [ ] **FW-01**: R Enhanced 绘图框架搭建：ggplot2 3.5.2 pin + common.R 公用函数 + registry.R 统一入口 + Python call_r_plot() 封装
- [ ] **FW-02**: 端到端验证：Python 调 R 画图 → 读 figure_data CSV → 输出 PNG 到 figures/r_enhanced/
- [x] **FW-03**: 更新 singlecell 模板（SC-DEVELOPMENT-CHECKLIST.md, SC-SKILL-TEMPLATE.md）添加 R Enhanced 检查项

## R Analysis Methods

- [ ] **RM-01**: monocle3_r 方法接入 sc-pseudotime（安装 monocle3 + R bridge + 结果 merge 回 adata + Python 标准画图）
- [ ] **RM-02**: gsea_r 方法接入 sc-enrichment（用已装的 fgsea/clusterProfiler + R bridge + 结果 merge + Python 标准画图）
- [ ] **RM-03**: gsva_r 方法接入 sc-enrichment（安装 GSVA + R bridge + group-level pathway score + Python 标准画图）
- [ ] **RM-04**: proportion_test_r 方法接入 sc-differential-abundance（纯 base R permutation test + R bridge + Python 标准画图）

## R Enhanced Shared Plots

- [ ] **SP-01**: embedding.R — CellDimPlot 等效（ggplot2 scatter + 配色 + 标签），读 figure_data embedding CSV
- [ ] **SP-02**: embedding.R — FeatureDimPlot 等效（连续值 scatter + viridis 配色），读 figure_data embedding CSV
- [x] **SP-03**: markers.R — GroupHeatmap 等效（ComplexHeatmap 分组热图），读 figure_data marker CSV

## R Enhanced Skill-Specific Plots

### sc-de / sc-markers
- [ ] **SK-01**: de.R — DEtestPlot volcano（ggplot2 增强版 volcano plot，labeled top genes）
- [ ] **SK-02**: de.R — FeatureHeatmap（ComplexHeatmap 表达热图）

### sc-enrichment
- [ ] **SK-03**: enrichment.R — EnrichmentPlot bar/dot（富集分析条形/点图）
- [ ] **SK-04**: enrichment.R — GSEAPlot line（经典 GSEA mountain plot + running score）
- [ ] **SK-05**: enrichment.R — GSEAPlot comparison（多组 NES heatmap）

### sc-pseudotime
- [ ] **SK-06**: pseudotime.R — LineagePlot（轨迹曲线 + loess 平滑叠加在 embedding 上）
- [ ] **SK-07**: pseudotime.R — DynamicPlot（基因沿拟时序表达趋势 + CI ribbon，Python 无等效）

### sc-cell-communication
- [ ] **SK-08**: communication.R — CCCHeatmap（细胞通讯热图/点图）
- [ ] **SK-09**: communication.R — CCCNetworkPlot（通讯网络图，ggplot2 arc layout）

### sc-velocity
- [ ] **SK-10**: velocity.R — VelocityPlot（RNA velocity stream/grid 图）

### All skills (wiring)
- [ ] **SK-11**: 把 --r-enhanced flag 接入所有需要的 skill（sc-cell-annotation, sc-de, sc-markers, sc-enrichment, sc-pseudotime, sc-cell-communication, sc-velocity, sc-differential-abundance, sc-preprocessing, sc-batch-integration, sc-clustering, sc-grn）

## Completion Criteria

每个 R 方法必须：
1. **跑通**: demo 数据无报错，processed.h5ad + Python 标准图全部生成
2. **输出合理**: 结果在生物学上合理（非全 NaN/空）

每个 R Enhanced 绘图必须：
1. **图片生成**: 从 figure_data/ CSV 读取 → PNG 输出到 figures/r_enhanced/
2. **质量检查**: 人工查看图片，确认可发表质量
3. **容错**: R 绘图失败只 warning，不影响 Python 标准图

## Future Requirements (deferred)

- DynamicHeatmap（需 RunDynamicFeatures GAM pipeline）
- EnrichmentPlot wordcloud（HTML widget，不适合 PNG）
- CCCNetworkPlot chord diagram（circlize PNG 不稳定）
- wot_r coupling matrix（O(n²) 内存）

## Out of Scope

- 其他组学领域的 R Enhanced — 本轮只做 scRNA
- oc chat 路由层的 R Enhanced 适配 — 留后续
- Monocle2 — 已过时，只接 Monocle3
- scvelo dynamical mode R 可视化 — 已知挂起风险
- 直接依赖 scop 包 — 提取代码适配，不 library(scop)

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FW-01 | Phase 13 | Pending |
| FW-02 | Phase 13 | Pending |
| FW-03 | Phase 13 | Complete |
| RM-01 | Phase 15 | Pending |
| RM-02 | Phase 15 | Pending |
| RM-03 | Phase 15 | Pending |
| RM-04 | Phase 15 | Pending |
| SP-01 | Phase 14 | Pending |
| SP-02 | Phase 14 | Pending |
| SP-03 | Phase 14 | Complete |
| SK-01 | Phase 17 | Pending |
| SK-02 | Phase 17 | Pending |
| SK-03 | Phase 16 | Pending |
| SK-04 | Phase 16 | Pending |
| SK-05 | Phase 16 | Pending |
| SK-06 | Phase 16 | Pending |
| SK-07 | Phase 16 | Pending |
| SK-08 | Phase 17 | Pending |
| SK-09 | Phase 17 | Pending |
| SK-10 | Phase 17 | Pending |
| SK-11 | Phase 18 | Pending |

---
*Last updated: 2026-04-11 after milestone v2.0 roadmap creation*
