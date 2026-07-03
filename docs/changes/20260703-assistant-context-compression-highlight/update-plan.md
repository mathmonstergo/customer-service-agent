# 智能问答上下文压缩和定位高亮变更计划

## 修改目标

1. 智能问答支持当前会话内的轻量上下文。
2. 早期对话以压缩摘要形式进入 prompt，近期对话保留原文。
3. 上下文 prompt 结构参考 `/home/adam/GenericAgent` 的 `WORKING MEMORY` / `earlier_context` / `history` 模式。
4. 右侧消息定位和来源定位增加滚动后的短暂高亮反馈。

## 影响范围

* 后端 RAG prompt 构造和 SSE payload 解析。
* 前端智能问答发送 payload 构造。
* 前端消息流和流程详情抽屉的定位交互。
* 前后端测试和静态构建产物。

## 具体步骤

1. 确认 MVP 路径：采用“前端轻量压缩 + 后端 prompt 拼接”，最近 5 轮保留原文。
2. 增加上下文 payload 类型和构造 helper。
3. 后端接受并按 GenericAgent 风格格式化 `conversation_context`，插入回答 prompt。
4. 消息导航滚动到位后高亮用户提问 body。
5. 来源 chip 打开流程抽屉后定位到具体来源卡片并高亮。
6. 补测试并运行后端、前端质量门。

## 预期效果

* 连续追问时，回答能理解“它 / 上面那个 / 刚才的问题”等简单上下文。
* 旧对话不会无限塞进 prompt。
* UI 点击定位有明确视觉反馈。

## 需要用户确认的问题

* 已确认：第一版采用前端本地压缩，不做模型摘要、不做持久化记忆；最近 5 轮保留原文。
* 已确认：上下文管理参考 `/home/adam/GenericAgent`，但不实现其长期记忆、全局 memory 或 checkpoint 工具。
