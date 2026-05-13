# MinerU 批量文件解析接入

本项目当前不本地安装 MinerU，也不使用 KIE SDK。导入 PDF、docx、xlsx、xls 时，项目侧固定调用 MinerU 官方云端批量文件接口，用户设置页只需要填写 MinerU Token。

## 固定接口

代码层固定维护以下官方接口，不暴露到设置页：

- 批量文件上传申请：`https://mineru.net/api/v4/file-urls/batch`
- 批量结果查询：`https://mineru.net/api/v4/extract-results/batch/{batch_id}`

单文件 URL 解析接口暂不接入，因为当前导入流程处理的是用户本地上传文件；本地文件需要先走批量接口获取签名上传地址。

## 启动配置与租户设置

```env
MINERU_API_TOKEN=
MINERU_PARSE_TIMEOUT_SECONDS=600
MINERU_USE_KB_PACKAGER=true
```

`.env` 只适合放启动级默认值。设置页保存后的租户级 Token、模型、解析开关等配置写入 `data/settings.local.json` 的 `tenants.default`，该文件不提交 Git。

## 导入链路

上传 PDF、docx、xlsx、xls 时，项目会选择 `mineru` 解析器：

1. 保存上传原件到 `UPLOAD_DIR`。
2. 使用 `MINERU_API_TOKEN` 请求 MinerU 批量文件上传地址。
3. 把本地文件 PUT 到 MinerU 返回的签名上传 URL。
4. 轮询批量结果查询接口。
5. 下载结果 zip，优先读取 `*_content_list_v2.json` / `*_content_list.json`，缺失时退回 `full.md` / Markdown。
6. 默认开启 `MINERU_USE_KB_PACKAGER=true`，按 `frondesce/mineru-kb-packager` 的思路做知识库友好再处理。
7. 生成 `import_chunks`，状态进入 `needs_review`，后续仍由 AI 候选 FAQ 和人工审核流程处理。

## 设置页

设置页只暴露：

- 文档解析器：MinerU。
- MinerU API Token。
- 解析超时时间。
- 是否启用知识库再处理层。

接口 URL 不让用户填写；如果 MinerU 官方 URL 后续变化，由代码层更新。
