# 用户确认记录

- 确认时间：2026-05-14 10:41 Asia/Shanghai
- 用户要求：文档管理页面需要标识已经完成 embedding 的状态；切片查看框需要可以编辑内容并保存。
- 已确认方案：展示文档级向量状态；切片原文改为可编辑；保存切片后同步更新 `import_chunks.source_text`，并把已有 `knowledge_chunks` 记录标记为 `stale`，提示重新生成 embedding。
