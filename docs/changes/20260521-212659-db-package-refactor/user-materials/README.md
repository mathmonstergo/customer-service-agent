本次重构由用户在 2026-05-21 提出，目标是把 db.py（2157 行）按业务域拆分到 db/ 包，对标 RAGFlow / Onyx 等前沿 KB 系统的代码组织（一域一文件 service），但因本项目不用 ORM、组件无多实现，所以不引入 ORM 层/base+factory 抽象。
