# OmicsClaw 论文落点研究笔记

日期：2026-09-30

这份笔记整理 2024 至 2026 年间与生物信息学 agent、科学 agent、技能学习和自演化 agent 相关的一手来源。文中“当前实现”指 OmicsClaw 已经存在的代码和文档能力；“潜在方向”指需要补实验或补实现后才能写入论文的主张。

## 先给结论

“又一个生物医学 agent”已经很拥挤。OmicsClaw 更合适的论文主线是：

> **OmicsClaw: A local-first, governed execution substrate for reproducible multi-omics agents**

论文应研究如何把异构多组学工具封装成可组合、环境和权限受控、可审计、可过程级评估的技能，并量化可靠性、分析质量和成本之间的关系。当前仓库已经具备跨七个组学域的技能目录、脚本化执行、依赖声明、sandbox、权限、result schema、ensemble trial 和资源约束等基础。论文还需要补充统一的任务矩阵、对照实验和过程级指标，才能支撑方法论文的中心主张。

## 当前实现与潜在方向

| 维度 | 当前仓库可据实描述 | 仍需验证或实现 |
| --- | --- | --- |
| 覆盖范围 | 7 个组学域，技能以 `SKILL.md` 和脚本组织 | 不应仅以技能数量宣称科学效果，需要跨域任务结果 |
| 执行方式 | 本地优先；技能脚本直接运行；框架提供工具、权限、sandbox 和会话层 | 需要报告不同隔离模式下的成功率、失败类型和开销 |
| 技能契约 | 名称、描述、输入输出说明、依赖区段、脚本入口、`result.json` 约定 | 需要定义跨技能可组合性和契约违规测试集 |
| 评测基础 | `ensemble` 支持受监督 trial、资源限制和指标面板 | 需要建立多组学过程级 benchmark，而不是只测最终标签 |
| 自演化 | 有技能、memory、tuning 和 ensemble 方向的基础部件 | 安全的候选技能生成、sandbox 验证、人工批准、版本和回滚仍是潜在方向 |
| 科学发现 | 已有分析技能和文献相关能力 | 假设生成、证据链和湿实验验证不应在没有实验时写成当前能力 |

## 代表性系统

### Biomni

**时间与来源。** Huang 等，bioRxiv 2025。论文：[Biomni: A General-Purpose Biomedical AI Agent](https://doi.org/10.1101/2025.05.30.656746)；官方仓库：[snap-stanford/Biomni](https://github.com/snap-stanford/Biomni)。

**核心能力。** Biomni-E1 以 25 个生物医学主题的论文为资源，挖掘工具、数据库和实验协议，形成统一动作空间。Biomni-A1 将检索增强规划与代码执行结合起来，动态组合任务流程，覆盖基因、药物、罕病、微生物组和分子克隆等任务。

**评测。** 论文报告 LAB-Bench DBQA 74.4%，专家为 74.7%；SeqQA 为 81.9%，专家为 78.8%；Humanity’s Last Exam 生物医学子集为 17.3%，基础模型为 6.0%。论文还报告了八个真实任务和湿实验克隆案例。

**与 OmicsClaw 的关系。** 两者都涉及生物工具编排和代码执行。Biomni 的优势是通用生物动作空间和任务广度；OmicsClaw 当前更适合从技能契约、依赖隔离、权限、sandbox、本地执行和结果审计来形成差异。技能数量或“通用生物 agent”不适合作为唯一创新点。

### CellAgent

**时间与来源。** Xiao 等，2024 年预印本，后发表于 ICLR 2026。论文：[CellAgent](https://arxiv.org/abs/2407.09811)；ICLR 版本的可复现说明：[OpenReview PDF](https://openreview.net/pdf?id=BsA2GNkJhz)；早期实现：[liu-shiqiang/CellAgent](https://github.com/liu-shiqiang/CellAgent)。

**核心能力。** CellAgent 使用 Planner、Executor 和 Evaluator 三类角色进行任务分解、顺序执行和自迭代优化，自动选择单细胞分析工具与参数，并生成可执行代码。

**评测。** 跨组织和细胞类型数据的批次校正与生物保真总体分数为 0.684，scVI 为 0.642；PBMC 数据中 17 个 cluster 有 94% 获得有效标注；轨迹推断总体分数为 0.496，Slingshot 为 0.473。

**与 OmicsClaw 的关系。** CellAgent 已覆盖单细胞工作流中的规划、工具调用和评估，因此 OmicsClaw 不宜把“自动单细胞分析”作为论文创新。可强调七个组学域的统一执行契约、环境治理、可追踪产物和系统级资源调度。

### SpatialAgent

**时间与来源。** Genentech 官方实现：[Genentech/SpatialAgent](https://github.com/Genentech/SpatialAgent)。

**核心能力。** 仓库将 SpatialAgent 描述为空间转录组、单细胞 RNA 测序和分子生物学的自主 agent，支持动态工具执行和自适应推理，范围从实验设计到多模态数据分析与假设生成。

**评测。** 官方仓库没有提供与 Biomni 或 CellAgent 同等完整的统一 benchmark 数值。论文写作中应将其作为能力范围和系统参照，不替它推断 SOTA 结果。

**与 OmicsClaw 的关系。** SpatialAgent 与 OmicsClaw 的空间、单细胞技能有明显重叠。OmicsClaw 可从跨域技能、脚本化产物、隔离执行和过程审计切入。

### ChatSpatial

**时间与来源。** Zhang 等，bioRxiv 2026。论文：[ChatSpatial](https://www.biorxiv.org/content/10.64898/2026.02.26.708361v1.full)；代码：[cafferychen777/ChatSpatial](https://github.com/cafferychen777/ChatSpatial)。

**核心能力。** ChatSpatial 采用 MCP 和 schema-enforced orchestration，把 LLM 的选择限制在预验证工具及参数空间内，桥接 Python 和 R，协调 60 多种方法、15 个分析类别。

**评测。** 论文报告复现两篇已发表研究、28 个验证场景和四种空间转录组平台，并测试 Claude Sonnet 4.5、Gemini 2.5 Flash 与 GPT-5 Mini。

**与 OmicsClaw 的关系。** 这是与 OmicsClaw 最接近的可靠性参照。OmicsClaw 不应声称首次提出 schema 约束或可复现 agent，而应说明自己的增量在跨七个组学域的技能契约、依赖和权限治理、资源调度以及过程级评测。

### Agent Laboratory

**时间与来源。** Schmidgall 等，Findings of EMNLP 2025。论文：[ACL Anthology](https://aclanthology.org/2025.findings-emnlp.320/)；代码：[SamuelSchmidgall/AgentLaboratory](https://github.com/SamuelSchmidgall/AgentLaboratory)。

**核心能力。** 系统从人类研究想法出发，依次进行文献综述、实验和报告写作，输出代码仓库与研究报告，并允许研究者在各阶段提供反馈。

**评测。** 论文报告 o1-preview 产生的研究结果最好；生成的机器学习代码可达到与现有方法相当的表现；人工参与提高总体质量；相较此前自主科研方法，研究成本下降 84%。

**与 OmicsClaw 的关系。** Agent Laboratory 关注科研项目流程和报告产出。OmicsClaw 可以定位为其中缺失的多组学计算执行底座，重点处理工具异构、依赖、数据契约和复现，而不竞争“自动写完整论文”。

### Google AI Co-Scientist

**时间与来源。** 预印本：[Towards an AI co-scientist](https://arxiv.org/abs/2502.18864)；Nature 版本：[Accelerating scientific discovery with Co-Scientist](https://www.nature.com/articles/s41586-026-10644-y)；官方介绍：[Google DeepMind](https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/)。

**核心能力。** Co-Scientist 使用 Gemini 多 agent 生成、批评和精炼假设，通过 tournament evolution 和 test-time compute 扩展搜索；系统还使用文献和外部工具核验，并提出实验方案。它的设计目标是协作式科学思考，不是完全替代研究者。

**评测。** Nature 论文报告了 203 个研究目标，并在药物再利用、新治疗靶点和抗菌药物耐药机制三个方向进行端到端湿实验验证。自动评估显示，增加 test-time compute 后假设质量继续提升。完整系统代码没有公开。

**与 OmicsClaw 的关系。** OmicsClaw 可作为假设到数据分析验证之间的执行层，提供可复现的多组学证据。若没有独立的假设生成和实验验证结果，不应把自己定位成 Co-Scientist 的替代品。

### STELLA

**时间与来源。** Jin 等，2025。论文：[STELLA](https://arxiv.org/abs/2507.02004)；官方实现：[asfarasimconcerned/STELLA](https://github.com/asfarasimconcerned/STELLA)。

**核心能力。** STELLA 由 Manager、Dev、Critic 和 Tool Creation Agent 协作，演化 Template Library 中的推理策略，并通过 Tool Ocean 发现、创建和集成生物信息学工具。

**评测。** 论文摘要报告 Humanity’s Last Exam 生物医学约 26%、LAB-Bench DBQA 54%、LitQA 63%，最高比领先模型高 6 个百分点；Humanity’s Last Exam 的准确率随试验次数增加接近翻倍。

**与 OmicsClaw 的关系。** 两者都涉及技能、工具、记忆和经验积累。OmicsClaw 更可行的研究方向是受控技能演化：候选技能生成后在 sandbox 中验证，由人批准后版本化，并支持回滚。把系统自改代码直接称为“自演化”会带来安全和复现风险。

### Darwin Gödel Machine

**时间与来源。** 论文：[Darwin Gödel Machine](https://arxiv.org/abs/2505.22954)；论文仓库：[lemoz/darwin-godel-machine](https://github.com/lemoz/darwin-godel-machine)。

**核心能力。** DGM 维护代码 agent archive，从 archive 中取出一个 agent，由基础模型生成新版本，并用开放式分支探索多个改进路径。保留与否由真实编码 benchmark 反馈决定。

**评测。** 80 轮后，SWE-bench 从 20.0% 提高到 50.0%；Polyglot 子集从 14.0% 提高到 38.0%，完整 Polyglot 从 14.2% 提高到 30.7%。系统优于缺少自改进或开放探索的基线，并展示了跨模型迁移。

**与 OmicsClaw 的关系。** DGM 是编码 agent 的自我改进研究，不是多组学系统。它可启发 OmicsClaw 的 ensemble 和 tuning 搜索，但不应直接采用任意自改代码。OmicsClaw 若研究演化，应将目标限制为技能、参数和工作流候选，并加入科学质量、复现率、成本和安全门槛。

### SkillFoundry

**时间与来源。** Shen 等，2026。论文：[SkillFoundry](https://arxiv.org/abs/2604.03964)。

**核心能力。** SkillFoundry 从论文、代码仓库、API、脚本、文档和数据库等异构资源中提取操作契约，把它们编译为包含任务范围、输入输出、步骤、环境、来源和测试的 agent skill，并通过扩展、修复、合并和剪枝形成闭环。

**评测。** 论文报告 71.1% 的挖掘技能与 SkillHub 和 SkillSMP 中的已有技能不同；在 MoSciBench 六个数据集中的五个上改善 coding agent 表现；按需生成的技能改善了 cell type annotation 和 scDRS 两个基因组任务。

**与 OmicsClaw 的关系。** SkillFoundry 使“拥有技能库”不足以成为 OmicsClaw 的唯一创新。OmicsClaw 的论文应强调技能生命周期治理：输入输出契约、依赖隔离、权限和 sandbox、审计、资源调度、回归测试以及跨多组学的真实结果评估。

## 论文实验建议

可行的实验设计如下：

1. 建立跨空间、单细胞、基因组、蛋白组、代谢组、bulk RNA-seq 和文献任务的任务矩阵，覆盖多个数据规模和失败模式。
2. 比较自由代码生成、普通工具调用、schema 或技能约束执行三种设置，并控制相同模型和任务。
3. 记录最终结果之外的过程指标，包括输入识别、方法选择、参数合法性、数据契约、错误恢复、结果正确性、生物保真、复现率、运行时间和成本。
4. 对 sandbox、依赖说明、技能正文、权限策略和 ensemble 资源池做消融。
5. 选择两到三个公开研究做端到端复现，并保存脚本、环境、日志、结果摘要和失败记录。
6. 如果加入技能演化，只允许候选技能在隔离环境中运行，通过测试和人工批准后进入版本库；比较固定技能库与受控演化技能库的覆盖率和回归率。

## 适合的论文落点

按当前完成度，Bioinformatics、Briefings in Bioinformatics、Patterns 和 npj Systems Biology and Applications 的方法或系统论文路线较现实。若补齐跨域 benchmark、公开复现案例和可验证的新生物发现，再考虑更高档期刊。论文摘要应把贡献写成“受治理的多组学 agent 执行与评测框架”，不要把贡献写成“首个生物 agent”“首个技能库”或“首个自演化科研系统”。
