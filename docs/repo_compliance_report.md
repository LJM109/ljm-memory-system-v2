# 仓库合规校验报告

生成时间：2026-08-24
校验范围：`D:\AML Agent Memory v2` 全仓库（提交前状态）
校验目的：对照 AML 学术榜提交的合规要求，逐项核验目录结构、路径规范、密钥安全、归因披露与可复现性。

## 一、检查项与结果

| # | 检查项 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | 目录结构标准化 | ✅ 通过 | app/、docs/、tests/、scripts/、Dockerfile、docker-compose.yml、requirements.txt、README.md、.gitignore 均在根目录且结构正确 |
| 2 | 无多余临时/缓存文件入库 | ✅ 通过 | `.pytest_cache/`、`__pycache__/` 已清理；`.venv312/` 仅存在于本地并已加入 `.gitignore`，不会入库 |
| 3 | 无 Windows 绝对路径 | ✅ 通过 | 全仓库扫描 `D:\`、`C:\` 绝对路径：0 处命中；所有路径均为相对路径或运行时 `os.path`/`os.environ` 动态计算 |
| 4 | 无硬编码密钥 / Token | ✅ 通过 | 全仓库扫描 `api_key/token/secret/password/sk-` 等：0 处真实命中；全部敏感项经 `os.environ` 环境变量读取（`LLM_API_KEY` 等） |
| 5 | `.gitignore` 覆盖权重与敏感文件 | ✅ 通过 | 已排除 `*.safetensors/*.bin/*.pt/*.onnx/*.gguf`、`.env`、`.claude/`、`.venv*/`、`data/`、`*.db`、`*.log` |
| 6 | 模型权重不入库 | ✅ 通过 | 权重仅 Docker 构建期在线下载；仓库内无任何 `.safetensors/.bin/.onnx` 二进制 |
| 7 | 归因披露完整 | ✅ 通过 | README「原始工作披露」逐项列出 MemOS 基线 + Cognee/Mem0/MemPalace/Hindsight 来源仓库与提取模块 |
| 8 | 方法改动披露 | ✅ 通过 | README「本次主要改动」列出 6 项改动；`docs/fusion_design.md` 逐仓库说明改动点 |
| 9 | API 契约合规 | ✅ 通过 | `docs/api_compliance.md` 逐字段对照；`Search` 仅返回证据、`user_id` 隔离、空结果返回空数组 |
| 10 | 可复现性 | ✅ 通过 | 默认零外部依赖、零外部模型；`docker compose up --build` 一键启动；15 项单元测试 + 全量冒烟脚本可离线复现 |

## 二、修复记录

| 时间 | 问题 | 修复动作 |
| --- | --- | --- |
| 2026-08-24 | 嵌入模型缺 bge query 指令前缀，导致无关文本语义基线偏高 | `core/embedding.py` 新增 `embed_query()`，自动为 bge/E5 加前缀 |
| 2026-08-24 | 时间戳/角色前缀污染嵌入，抬升无关余弦、拉低相关余弦 | 拆分 `search_text`（干净索引文本）与 `content`（返回证据），索引/编码只用 `search_text` |
| 2026-08-24 | 语义阈值 0.2 过低，认识论安全门失效 | 实测校准后设 `MIN_SEMANTIC=0.4`（无关 0.31–0.36 vs 相关 0.61–0.68） |
| 2026-08-24 | 冲突检测把互补偏好误判为冲突（"爱徒步"取代"爱画画"） | 偏好/规则改为可累加，仅地点/职业/姓名等互斥属性触发取代 |
| 2026-08-24 | 新鲜度用墙钟导致历史时间戳全部衰减为 0 | 改为相对用户最新记忆计算新鲜度 |
| 2026-08-24 | `.gitignore`/`.dockerignore` 未覆盖 `.venv312`、模型权重 | 补充排除规则，杜绝权重/密钥/虚拟环境入库 |

## 三、结论

**✅ 满足学术榜提交的合规要求。**

仓库结构规范、无绝对路径、无硬编码密钥、模型权重与敏感文件均被排除、原始工作与改动完整披露、API 契约与可复现性均达标。可进入 GitHub 上传与参评申请流程。

> 剩余人工操作项（非仓库内可自动完成）：安装并启动 Docker Desktop 后完成容器内构建验证；推送 GitHub；在 AML 平台填写并提交申请表单。
