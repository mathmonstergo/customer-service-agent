# 文档 embedding review 修复计划

## 修改目标

修复代码评审指出的五个正确性问题，避免文档父子切片 embedding 状态统计错误、手动编辑后旧 child 行卡住 stale、MinerU 资产互相覆盖、保存设置丢失自定义分块配置，以及 child `chunk_index` 与 parent 冲突。

## 影响范围

- `customer_service_agent/admin_server.py`
  - 文档知识单元 child `chunk_index` 生成规则。
  - 设置保存时缺失字段的合并规则。
  - MinerU 客户端资产输出目录。
- `customer_service_agent/db/imports.py`
  - 文档 embedding 摘要 SQL。
  - 手动编辑切片后旧 child 知识单元清理/标记逻辑。
- `tests/`
  - 增加或更新针对以上行为的单元测试。

## 具体步骤

1. 核对现有实现，确认评审点是否符合当前代码。
2. 先补失败测试，覆盖设置保留、child index、MinerU 资产目录、embedding 摘要口径、手动编辑 child 清理。
3. 小步修改后端实现，不调整整体导入流程和数据库 schema。
4. 运行针对性测试；条件允许再运行 `python -m pytest` 和 `python -m ruff check .`。

## 预期效果

- 手动编辑文档切片后，旧 child 知识单元不会继续残留为 stale。
- 文档 embedding 摘要的 ready/total 使用一致的知识单元口径。
- MinerU 结果资产按 import file 独立落目录。
- 保存设置时，UI 未发送的文档分块配置保持当前运行值。
- child `chunk_index` 不再与 parent 正编号冲突。

## 需要用户确认的问题

用户已在 2026-05-22 确认“开始动手修复”。本次按评审项做窄修复，不新增 UI 布局或数据库 schema。

