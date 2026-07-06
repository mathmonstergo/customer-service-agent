# 统一 API 设置菜单页变更计划

## 修改目标

1. 新增“设置”主菜单页，集中管理项目全局 API / 服务配置。
2. 保留智能问答会话级 provider 单独覆盖能力。
3. 解决 KG 抽取等后台能力只能走全局配置、且全局配置不易发现的问题。
4. 用同尺寸卡片做设置总览，具体配置通过居中弹窗编辑。
5. 敏感配置只展示脱敏摘要或已配置状态，前端不能获取已保存明文。

## 当前配置清单

后端 `/api/settings` 已支持以下字段：

* 数据库：`database_url`
* Chat / KG 实体提取：`chat_base_url`、`chat_api_key`、`chat_model`
* Embedding：`embedding_base_url`、`embedding_api_key`、`embedding_model`、`embedding_dimensions`
* WeChat：`wechat_token_file`、`wechat_message_chunk_size`
* RAG：`rag_top_k`、`rag_min_score`
* 上传：`upload_dir`
* MinerU：`mineru_api_token`、`mineru_parse_timeout_seconds`、`mineru_use_kb_packager`
* 文档切分：`document_chunk_token_num`、`document_chunker_type`、`document_chunk_delimiter`、`document_chunk_overlap_percent`、`document_children_delimiter`、`document_table_context_size`、`document_image_context_size`
* Rerank：`rerank_base_url`、`rerank_api_key`、`rerank_model`、`rerank_input_size`

## 影响范围

* 前端主路由和侧边栏菜单。
* 前端 settings 页面、弹窗动效、hooks、schemas。
* 现有会话级 provider 抽屉文案和可复用 provider 控件。
* 后端设置 API 需要支持敏感字段脱敏快照和“留空保留旧值”的保存语义。
* 前端构建产物。

## 具体步骤

1. 用户确认 MVP 范围和 UI 信息层级。
2. 更新 PRD 和确认记录。
3. 实现 `/settings` 路由和侧边栏入口。
4. 新增设置页卡片总览：模型服务、文档与检索、系统连接分组，上下分组清晰隔离。
5. 在模型服务分组显式展示“实体提取”卡片；该卡片编辑全局 Chat 默认配置，因为 KG 抽取后端当前复用 ChatClient。
6. 新增居中配置弹窗；弹窗从被点击卡片位置扩展出来，背景随进度渐进虚化。
7. 复用或抽取 Chat provider 预设、拉取模型、测试连通控件。
8. 调整设置快照和保存逻辑，避免 API Key / Token / 数据库密码明文回传前端。
9. 保存时调用 `/api/settings` 并刷新缓存。
10. 更新测试并跑质量门。

## 预期效果

* 用户能在一个页面看到项目全部全局 API / 服务配置。
* 首屏以等尺寸卡片展示摘要，复杂表单只在弹窗内出现。
* 用户能在设置页直接看到“实体提取”配置入口，并理解它跟随 Chat 默认模型。
* 弹窗出现和背景虚化动效更接近 iOS 系统的连续过渡。
* KG 抽取、FAQ 优化、文档解析、Embedding、RAG 等后端能力的默认 provider 更容易调整。
* 智能问答会话级 provider 继续作为 per-session override 存在。
* 前端无法查看已经填写的敏感字段明文，只能通过输入新值覆盖。

## 需要用户确认的问题

已确认：第一版只给 Chat 做测试连接和模型拉取；Embedding / Rerank / MinerU 先只保存配置。
