# 知识图谱 MVP

## Goal

为本地客服知识库增加第一版轻量知识图谱能力：从已审核 FAQ 和文档切片中抽取实体、关系和证据候选，经过人工审核后形成可追溯的结构化知识，并优先用于检索扩展和客服排查，而不是做复杂通用推理或重型图谱可视化。

## What I already know

* 用户确认可以开始知识图谱方向。
* 项目定位是本地客服知识库与 RAG 服务，真实业务资料、上传原件、客户聊天记录和密钥不能提交。
* 当前已有 FAQ、文档导入、MinerU/RAGFlow 后解析、统一 `knowledge_chunks`、混合检索、评测工作台和可读来源追溯。
* 现有 `sql/001_init.sql` 已包含 `faq_documents`、`knowledge_chunks`、`import_files`、`import_chunks`、`import_candidates`、`retrieval_eval_*` 等基础表。
* 现有 `customer_service_agent/db/knowledge.py` 负责统一知识单元写入、向量检索、关键词检索和父块上下文回填。
* 现有 `customer_service_agent/retrieval.py` 已有 query analysis、关键词词表、RRF 融合和评测指标基础能力。
* 现有 `customer_service_agent/import_ai.py` 已有“AI 生成候选 FAQ，人工审核后保存”的模式，知识图谱抽取应复用同样的候选/审核思想。
* 历史调研 `docs/changes/20260514-124612-retrieval-phase-one/research-notes.md` 明确建议：KG 不替代普通 RAG，第一版只做实体识别和关联 chunk 扩展，不做复杂社区报告。
* 参考笔记 `docs/references/ragflow-mineru-knowledge-graph-notes.md` 建议轻量表如 `kg_entities`、`kg_relations`、`kg_evidence`、`faq_entity_links`，且抽取结果必须人工审核。
* 用户澄清要看本地 RAGFlow 仓库 `/home/adam/projects/ragflow`，不是远程资料。
* 本地 RAGFlow 的 GraphRAG 不依赖独立图数据库，而是把 `graph`、`subgraph`、`entity`、`relation`、`community_report` 作为特殊 chunk 写回 doc store。
* 本地 RAGFlow 在检索时通过 `use_kg` 额外生成一条 `Related content in Knowledge Graph` 合成上下文，并插入普通检索结果前面。
* 本地 RAGFlow 的实现没有本项目要求的人工审核闸门，因此只能借鉴存储/检索形态，不能照搬状态流转。
* 用户希望最终能做成“大厂那种 3D 可视化图谱”，并询问是否应先把基础做好再扩展。
* 主流 GraphRAG / KG 产品实践都先做可靠图谱底座：来源切片、实体/关系抽取、schema、证据追溯、审核、检索接入和评测；3D/图形化探索通常是消费层。
* 当前前端 `web/package.json` 没有 Three.js、3d-force-graph、D3、Cytoscape、Sigma 等图可视化依赖；做 3D 需要新增前端渲染栈和专门的局部子图 API。

## Assumptions

* 第一版不引入 Neo4j、Redis、ES、LightRAG 全套框架或 RAGFlow 重型依赖。
* 第一版使用 PostgreSQL 普通表存储实体、关系、证据和审核状态。
* 第一版优先处理中文客服知识中的产品/模块/功能/错误/角色/限制条件/处理步骤等实体。
* 第一版 KG 结果默认进入待审核，不直接进入可检索状态。
* 第一版图谱只作为召回增强和排查线索，最终回答仍必须引用 FAQ/文档切片证据。
* 3D 可视化作为明确路线图目标，但不进入第一版核心实现；第一版只预留可视化所需的数据结构和局部图谱查询接口。

## Open Questions

* 已解决：第一版接入最小 KG 检索增强，但仅作为开关/评测调试路径，不默认影响所有客服回答。

## Requirements (evolving)

* 支持从已审核 FAQ 和可用文档切片生成知识图谱候选。
* 第一版采用“独立审核表 + 确认后投影为可检索 KG chunk + 预留局部子图 API”的路径。
* 第一版实体类型和关系类型采用固定客服领域枚举，不允许模型自由生成新类型。
* 候选实体至少包含名称、类型、别名、描述、来源、状态和置信度。
* 候选关系至少包含头实体、关系类型、尾实体、描述、证据、来源、状态和置信度。
* 实体和关系必须有稳定 ID，方便后续 2D/3D 图谱复用同一套事实来源。
* 证据必须可追溯到 FAQ ID 或文档切片 ID，并尽量保留页码、章节、文件名。
* AI 抽取结果默认 `needs_review` 或等价状态，人工确认后才可用于召回。
* 保存后的实体/关系应支持禁用或待复核状态，避免错误图谱污染召回。
* 检索增强只扩展候选，不绕过现有可用状态、文档禁用、FAQ 状态过滤。
* 第一版提供最小 KG 检索增强：确认后的实体/关系投影为 `knowledge_chunks` 后，可通过显式开关参与扩召回和评测调试。
* KG 检索增强第一版不默认进入所有客服回答链路，避免未评测前影响生产问答体验。
* 后端应预留局部子图查询能力，例如按实体查询 1-hop 关系，支持实体类型、关系类型、状态和数量限制。
* 管理后台 UI 必须显式呈现状态：待抽取、抽取中、待审核、已确认、已禁用、失败可重试。
* 评测工作台后续应能观察 KG 扩召回是否提升，而不是只能凭主观感觉判断。

## Acceptance Criteria (evolving)

* [ ] 有明确的 KG 数据模型和状态流转设计。
* [ ] 有 AI 抽取候选的输入/输出 JSON 契约。
* [ ] 有人工审核入口或明确的第一版管理流程。
* [ ] 有至少一种可验证的检索增强方式，例如 query 实体识别后扩展相关 chunk。
* [ ] KG 检索增强必须由显式开关启用，默认客服回答链路不受影响。
* [ ] KG 候选和已确认结果都能追溯到 FAQ/文档切片证据。
* [ ] 未审核或禁用的实体/关系不会进入检索增强。
* [ ] 已确认实体/关系能以局部子图数据结构返回，后续可直接接 2D/3D 可视化。
* [ ] 有后端测试覆盖 schema/API/抽取解析/检索扩展关键行为。
* [ ] 如涉及 UI，前端构建和 lint 通过，并按项目 UI 讨论流程先确认布局。

## Definition of Done

* 用户确认 MVP 范围和第一版路径。
* `docs/changes/20260629-092142-knowledge-graph-mvp/` 更新计划、确认和验证记录。
* 需要 schema 时提供幂等 SQL 迁移和数据库测试。
* 需要 AI 生成时提供结构化输出解析、错误处理和测试。
* 需要 UI 时先给可用于生成 UI 布局图的 prompt，用户确认图片后再实现。
* 后端 `python -m pytest`、`python -m ruff check .`、`python -m customer_service_agent.cli check-config` 可运行并记录结果。
* 前端变更时 `npm test`、`npm run lint`、`npm run build` 可运行并记录结果。

## Out of Scope

* 复杂社区报告、多跳推理和全局摘要。
* 独立图数据库或重型图谱服务。
* 第一版实现 3D 或大规模图谱可视化。
* 让未审核 AI 抽取结果直接进入正式知识库或回答。
* 修改微信服务、外部 API、权限、审计和公网暴露策略。
* 用 KG 替代现有向量/关键词/混合检索。

## Technical Notes

* 可能影响的后端文件：
  * `sql/001_init.sql`
  * `customer_service_agent/db/knowledge.py`
  * `customer_service_agent/db/models.py`
  * `customer_service_agent/retrieval.py`
  * `customer_service_agent/admin_server.py`
  * 新增 `customer_service_agent/kg.py` 或 `customer_service_agent/db/kg.py`
* 可能影响的前端文件：
  * `web/src/api/schemas.ts`
  * `web/src/api/hooks.ts`
  * `web/src/main.tsx`
  * `web/src/components/layout/sidebar.tsx`
  * 新增 `web/src/pages/KnowledgeGraphPage.tsx` 或先放在文档/FAQ 抽屉内
* 相关历史资料：
  * `docs/references/ragflow-mineru-knowledge-graph-notes.md`
  * `docs/changes/20260514-124612-retrieval-phase-one/research-notes.md`
  * `docs/changes/20260615-130211-assistant-evaluation-workbench/update-plan.md`
* 当前前端没有图可视化依赖；如后续做 3D，候选技术栈包括 Three.js 或 `3d-force-graph`，但需先走 UI 讨论和布局确认流程。

## Research References

* [`research/ragflow-knowledge-graph-local.md`](research/ragflow-knowledge-graph-local.md) — 本地 RAGFlow 采用“KG 产物写回 doc store + use_kg 合成上下文”的模式，但缺少本项目需要的候选审核层。
* [`research/industry-knowledge-graph-visualization.md`](research/industry-knowledge-graph-visualization.md) — 主流实践先做可信图谱底座，再把 2D/3D 图谱作为探索和演示层。

## Candidate MVP Approaches

### Approach A: 独立审核表 + 确认后投影为 KG chunk (Recommended)

借鉴 RAGFlow 的可检索 chunk 思路，但先用独立表保存实体、关系、证据候选。人工确认后，再把实体/关系投影为 `knowledge_chunks` 的特殊来源类型，例如 `kg_entity`、`kg_relation`。检索增强可以生成一条 KG 合成上下文，但只使用 `usable` KG 结果。

优点：同时满足本项目人工审核约束和 RAGFlow 的检索复用优势；后续能用现有向量/关键词/评测基础设施验证效果。
代价：比直接写 `knowledge_chunks` 多一层数据模型和审核 API。

### Approach B: 直接写 KG chunk

更接近 RAGFlow：抽取后直接把实体/关系写成 `knowledge_chunks` 特殊来源类型，再靠状态字段控制是否可检索。

优点：实现链路短，能最快接入检索。
代价：候选治理、证据审核和错误回滚容易混在同一表里，不符合“AI 输出先审核”的项目原则。

### Approach C: 纯独立 KG 表

完全使用 `kg_entities`、`kg_relations`、`kg_evidence` 等表，暂不投影为 `knowledge_chunks`。

优点：结构清晰，人工治理体验更直接。
代价：检索增强要额外写一套查询和排序逻辑，不能充分复用现有混合检索和 embedding 管线。

## Recommendation

采用 Approach A。第一版先把“抽取候选 -> 人工审核 -> 可追溯实体/关系 -> 投影成可检索 KG chunk”打稳，再用评测工作台验证 KG 合成上下文是否改善召回。UI 第一版可以先做审核列表和详情，不做复杂节点图；GraphRAG 的 community report、实体消歧和多跳推理先放到后续。

## Candidate Type Set

推荐第一版使用固定枚举，避免模型随意生成类型导致后续筛选、检索和 3D 可视化难以稳定。

### Entity Types

* `product_platform_module`：产品 / 平台 / 模块。
* `feature_ui_action`：功能 / 页面 / 按钮 / 菜单。
* `error_symptom`：错误码 / 异常现象。
* `process_task_object`：流程 / 任务 / 报告 / 订单。
* `role_permission_channel`：角色 / 权限 / 渠道。
* `condition_policy`：限制条件 / 适用条件 / 转人工条件。

### Relation Types

* `belongs_to`：功能属于模块。
* `requires`：操作需要前置条件。
* `causes`：现象可能由原因导致。
* `resolves_by`：问题可通过步骤解决。
* `blocked_by`：功能受某条件阻塞。
* `available_for`：适用于某角色或渠道。
* `escalate_when`：满足条件需转人工。

## Decision (ADR-lite)

**Context**: 用户希望最终做成 3D 可视化图谱，但项目有明确约束：AI 生成结果必须先审核，正式回答必须保留 FAQ/文档证据，现有系统已经有 `knowledge_chunks`、混合检索和评测基础。

**Decision**: 第一版采用 Approach A：独立审核表保存实体/关系/证据候选，人工确认后投影为 `knowledge_chunks` 的 KG 特殊来源，并预留局部子图 API；3D 可视化作为后续阶段，不进入第一版核心实现。

**Consequences**: 第一版实现面比直接写 KG chunk 略大，但图谱质量、审核、证据追溯、检索复用和后续 2D/3D 可视化扩展更稳。第一版不会交付大规模节点图或 3D 图谱。

## Decision: Type Set (ADR-lite)

**Context**: KG 类型会影响数据库约束、AI 抽取 JSON schema、审核筛选、局部子图 API、检索扩展和后续 3D 图谱配色。如果允许模型自由生成类型，短期灵活但长期治理成本高。

**Decision**: 第一版使用固定客服领域枚举：实体类型采用 `product_platform_module`、`feature_ui_action`、`error_symptom`、`process_task_object`、`role_permission_channel`、`condition_policy`；关系类型采用 `belongs_to`、`requires`、`causes`、`resolves_by`、`blocked_by`、`available_for`、`escalate_when`。

**Consequences**: 抽取和审核更可控，后续检索和可视化更稳定；如果未来业务类型不足，再通过迁移和配置扩展枚举。

## Decision: Retrieval Scope (ADR-lite)

**Context**: KG 只有接入检索才能验证价值，但直接默认进入客服回答链路会放大错误关系和未评测策略的风险。

**Decision**: 第一版接入最小 KG 检索增强。确认后的实体/关系投影为 `knowledge_chunks` 后，通过显式开关参与扩召回和评测调试；默认客服回答链路保持现状。

**Consequences**: 第一版可以用评测工作台观察 KG 是否改善召回，同时避免未验证的图谱上下文直接影响正式回答。后续若评测有效，再决定是否默认启用或接入更多问答入口。

## Visualization Roadmap

### Phase 1: 可信图谱底座

第一版只做可审核、可追溯、可检索的实体/关系，并预留局部子图 API。重点是稳定 ID、类型、状态、证据、来源和检索投影。

### Phase 2: 图谱治理 UI

在审核列表和详情页稳定后，增加局部关系视图。可以先用 2D 或轻量 canvas/SVG 展示 1-hop 关系，用来辅助审核和排查。

### Phase 3: 3D 可视化图谱

在图谱质量和局部查询 API 稳定后，再做 Three.js / `3d-force-graph` 方向的 3D 视图。默认从一个实体展开 1-2 跳，限制节点和边数量，右侧保留证据详情，避免把 3D 当作审核主界面。
