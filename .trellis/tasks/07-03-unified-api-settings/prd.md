# 统一 API 设置菜单页

## Goal

新增一个独立的设置菜单页，把项目里的全局 API / 服务配置集中管理，减少配置散落在智能问答会话抽屉、后端 `.env` / `settings.local.json` 和不同功能页里的割裂感。智能问答仍保留会话级 provider 覆盖能力；全局设置页负责默认配置和其他非会话级服务配置。

## What I already know

* 用户希望“做新菜单页”，统一统计并管理项目现在有哪些 API 设置。
* 用户明确例外：智能问答的会话级 API 仍然支持在会话页面单独设置。
* 后端已有 `/api/settings`：
  * `GET /api/settings` 返回当前 `Settings` 快照。
  * `POST /api/settings` 保存到 `data/settings.local.json`，并刷新运行时 `settings`、chat/embedding/rerank client 缓存。
* 后端设置字段已经覆盖：
  * 数据库：`database_url`
  * Chat：`chat_base_url`、`chat_api_key`、`chat_model`
  * Embedding：`embedding_base_url`、`embedding_api_key`、`embedding_model`、`embedding_dimensions`
  * WeChat：`wechat_token_file`、`wechat_message_chunk_size`
  * RAG：`rag_top_k`、`rag_min_score`
  * Upload：`upload_dir`
  * MinerU：`mineru_api_token`、`mineru_parse_timeout_seconds`、`mineru_use_kb_packager`
  * Document chunking：`document_chunk_token_num`、`document_chunker_type`、`document_chunk_delimiter`、`document_chunk_overlap_percent`、`document_children_delimiter`、`document_table_context_size`、`document_image_context_size`
  * Rerank：`rerank_base_url`、`rerank_api_key`、`rerank_model`、`rerank_input_size`
* 前端目前只有智能问答会话级 `ProviderDrawer` 读取 `/api/settings` 作为“全局默认模型”提示，没有独立全局设置页。
* 前端已有可复用 provider 体验：
  * 供应商预设
  * base_url / api_key / model 表单
  * 拉取模型列表 `/api/assistant/models`
  * 测试连通 `/api/assistant/probe`
  * API Key 显示/隐藏
* 当前主路由在 `web/src/main.tsx`，侧边栏在 `web/src/components/layout/sidebar.tsx`，顶栏标题在 `web/src/components/layout/topbar.tsx`。

## Assumptions

* 新设置页是本地内部工具页，不新增登录鉴权。
* 第一版优先复用现有 `/api/settings`，不重做后端配置存储结构。
* “API 设置”不只包含 LLM provider，也包含 MinerU、Embedding、Rerank、数据库、微信 token 路径等会影响服务调用的配置。
* 不把会话级 provider 从智能问答页移除，只在全局设置页展示/编辑默认 Chat provider。

## Requirements

* 侧边栏新增“设置”菜单，进入新页面，例如 `/settings`。
* 新设置页按用途分组展示全局配置，每个具体设置项做成同尺寸卡片：
  * 模型服务：Chat、KG 实体/关系抽取、Embedding、Rerank
  * 文档与检索：MinerU、RAG 参数、chunker 参数
  * 系统连接：数据库、上传目录、微信 token / 消息分段
* 卡片只展示简短摘要和当前配置状态，点击卡片中心区域后打开居中的具体配置弹窗。
* 具体配置只在弹窗里编辑，弹窗采用接近 iOS 系统的丝滑动效：从被点击卡片位置扩展到居中弹窗，背景遮罩和模糊效果随弹窗放大进度逐渐增强。
* Chat 全局配置应复用会话级供应商抽屉的主要交互：预设、拉取模型、测试连通、API Key 显示/隐藏。
* KG 实体/关系抽取当前复用全局 Chat 默认配置，设置页必须显式提供“实体提取”卡片；点击该卡片进入同一组 Chat 默认配置，避免用户误以为抽取模型不可配置。
* DeepSeek 官方 API 应作为预设之一，避免继续依赖有问题的聚合代理来做 KG 抽取。
* Embedding / Rerank / MinerU 第一版先保存配置，不额外新增各自的连通测试。
* 保存后应调用现有 `/api/settings`，并刷新相关 query cache。
* API Key / Token / 数据库密码类敏感值不能在前端获取已填写的明文；设置快照只允许返回脱敏摘要或“已配置”状态。
* 弹窗里密钥字段默认为空，用户输入新值才覆盖旧值；留空表示保留当前已配置值。
* 会话级设置继续存在，并且文案说明“留空则走设置页里的全局默认”。

## Acceptance Criteria

* [ ] 左侧菜单有“设置”，顶部标题能正确显示。
* [ ] `/settings` 页面可加载当前全局配置。
* [ ] 页面以同尺寸设置卡片展示当前配置摘要。
* [ ] 模型服务分组包含“实体提取”卡片，明确展示其跟随 Chat 默认配置。
* [ ] 点击卡片后，从卡片位置丝滑扩展出居中配置弹窗，背景随进度逐渐模糊。
* [ ] 页面能通过弹窗编辑并保存 `/api/settings` 支持的主要字段。
* [ ] Chat 全局配置支持预设、拉取模型和测试连通。
* [ ] DeepSeek 官方 API 预设可选。
* [ ] 前端无法读取已填写的 API Key / Token / 数据库密码明文，只能看到脱敏摘要或已配置状态。
* [ ] 密钥字段留空保存时保留旧值，输入新值时才覆盖旧值。
* [ ] 智能问答会话级 provider 仍能单独覆盖全局设置。
* [ ] 保存成功后，不刷新页面即可让后续全局 Chat / KG 抽取走新配置。
* [ ] Python / frontend tests、lint、build 通过。

## Candidate Approaches

### Approach A: 单页同尺寸卡片 + 居中配置弹窗 (Selected)

在 `/settings` 做一个工具型设置页，不增加内部导航和子路由。页面按大分组纵向隔开，每个设置项是同尺寸卡片，卡片展示摘要；点击卡片后打开居中弹窗编辑具体配置。复用现有 `/api/settings`，前端新增 `useSettings` / `useUpdateSettings`。

优点：首屏规整、信息密度可控，避免长表单拥挤；配置复杂度收敛在弹窗里；符合用户确认的视觉方向。
代价：需要处理弹窗动效、卡片摘要和敏感字段脱敏语义。

### Approach B: 单页长表单

在 `/settings` 直接把所有字段按分组纵向展开。

优点：实现简单，字段一眼可编辑。
代价：页面拥挤，用户已明确希望用卡片摘要 + 弹窗。

### Approach C: 多个设置子页

拆成 `/settings/models`、`/settings/documents`、`/settings/system`。

优点：单页信息密度低，后续扩展更清楚。
代价：路由和导航更多，用户已明确不需要额外导航。

## Recommendation

采用 Approach A。这个项目是本地管理后台，设置页应该是信息密集但清晰的操作面板，不做营销式页面。第一版用同尺寸卡片提供配置总览，用居中弹窗承载具体编辑，并强化 Chat 全局 provider 能力，解决 KG 抽取依赖错误代理的问题。

## Open Questions

* 暂无阻塞问题。第一版连接测试范围收敛为 Chat；Embedding / Rerank / MinerU 先只保存配置。

## Out of Scope

* 不移除智能问答会话级 provider 覆盖。
* 不新增数据库 schema。
* 不新增多租户切换 UI。
* 不把 API key 提交到 Git。
* 不允许前端读取或回显已保存的敏感字段明文。
* 不做公网安全能力，如登录、审计日志、密钥加密存储。

## Definition of Done

* 用户确认 MVP 范围和布局方向。
* `docs/changes/20260703-104226-unified-api-settings/` 记录计划、用户确认和外部资料状态。
* 实现设置页、路由、菜单、API hooks/types。
* 更新必要测试。
* 运行 `python -m pytest`、`python -m ruff check .`、`python -m customer_service_agent.cli check-config`、`pnpm test`、`pnpm lint`、`pnpm build`。
* 准备可提交 diff；仅在用户明确要求时提交 Git commit。
