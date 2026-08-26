# LJM 记忆系统 v2.0

面向 **Agent Memory Leaderboard（AML）文本记忆赛道·学术榜** 参评的多系统融合记忆系统。以 **MemOS** 为架构基线，深度融合 **Cognee / Mem0 / MemPalace / Vectorize Hindsight** 的核心优势模块，严格对齐 AML 官方 `Add` / `Search` 契约与学术榜合规要求。

---

## 1. 系统概述

本系统面向长期记忆评测场景，实现「写入 → 检索 → 治理」全链路。架构上以 **MemOS** 的分层记忆与时序事件处理为基座，在此基础上融合四类开源系统的关键能力：

| 维度 | 技术来源 |
| --- | --- |
| 时序事件序列 / 混合检索基座 | MemOS |
| 知识图谱实体关系抽取 / 多跳推理 | Cognee |
| 事实自动抽取 / 重要性评分 / 偏好记忆 | Mem0 |
| 分层存储 / 长程记忆锚定 | MemPalace |
| 事后去重降噪 / 记忆治理 | Vectorize Hindsight |

系统仅暴露两个记忆操作 `Add`（写入）与 `Search`（检索），答案生成与评分完全交由 AML 平台统一执行，保证成绩差异来自记忆系统本身而非下游模型。详见 [`docs/fusion_design.md`](docs/fusion_design.md)。

---

## 2. 核心能力

对应 AML 文本记忆七大能力维度：

| # | 能力维度 | 优化点 | 技术来源 |
| --- | --- | --- | --- |
| A | 显式事实召回 | 稠密向量 + BM25 混合检索 + 事实自动抽取 | MemOS / Mem0 |
| B | 关系与多跳组合 | 实体-关系图谱构建，一跳 + 二跳路径召回 | Cognee |
| C | 时序与事件序列 | 时序事件块、相对新鲜度、冲突版本管理 | MemOS / Cognee |
| D | 记忆治理 | 冲突检测、重要性评分、过期淘汰、版本管理 | Mem0 / MemOS / Hindsight |
| E | 个性化与关怀 | 用户偏好 / 身份 / 规则自动抽取与加权 | Mem0 |
| F | 规则与流程执行 | 规则语句抽取 + 时间戳保留 + 最新有效状态 | Mem0 / MemOS |
| G | 认识论安全与隐私 | 相关性阈值门、无匹配返回空数组、`user_id` 严格隔离 | 自研 / AML 规范 |

---

## 3. 快速启动

### Docker（推荐）

```bash
docker compose up --build
```

服务监听 `0.0.0.0:8000`。模型权重（`BAAI/bge-small-en-v1.5`）在镜像**构建阶段**自动在线下载，Git 仓库不含任何二进制权重文件。

### 本地 uvicorn（无 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 4. API 规范

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 → `{"status":"ok"}` |
| `POST` | `/v1/memories/add` | 同步写入，回显 `request_id` |
| `POST` | `/v1/memories/search` | 有序返回记忆证据（或 `{"data":[]}`） |

### Add 请求核心字段

```json
{
  "user_id": "u1",
  "session_id": "s1",
  "request_id": "r1",
  "messages": [
    {"role": "user", "content": "I live in New York.", "timestamp": 1700000000000}
  ]
}
```

- `user_id` 检索隔离作用域；`session_id` 会话分组；`request_id` 响应原样回显；`messages` 有序消息列表。
- **同步返回 200**（写入 + 建索引完成且可检索后才返回）；对额外字段（如历史 `async_mode`）宽容接受，绝不返回 422 / 202 / task_id / 轮询地址。

### Search 请求 / 响应核心字段

```json
// 请求
{"query": "Where do I live?", "user_id": "u1", "top_k": 10, "options": ["New York", "Boston"]}
// 响应（按相关性降序，≤ top_k；无相关记忆返回空数组）
{"data": [{"id": "mem_…", "content": "…", "score": 0.87, "created_at": "2023-11-14T22:13:20.000000Z"}]}
```

完全对齐 AML 官方契约：`Search` 仅返回原始记忆证据，不生成答案、不拼接结论、不伪造记忆；`user_id` 级数据隔离。详见 [`docs/api_compliance.md`](docs/api_compliance.md)。

---

## 5. 原始工作披露（必填核心）

### 基线系统

- **MemOS** — https://github.com/MemTensor/MemOS
  提供分层记忆架构与时序事件处理基座。本系统继承其「时序事件块 + 稠密/BM25 混合检索」思想，重构为「同说话人连续轮次 = 事件块」，并新增多路召回融合（RRF）。

### 融合模块来源

- **Cognee** — https://github.com/topoteretes/cognee
  知识图谱实体关系抽取与多跳推理召回。本系统以确定性启发式 NER 替代图数据库，构建「实体 → 记忆」倒排索引实现一跳 + 二跳路径召回，并复用其事实冲突检测与版本管理思想。
- **Mem0** — https://github.com/mem0ai/mem0
  事实自动抽取、用户偏好记忆、记忆重要性评分机制。本系统以正则抽取「偏好 / 身份 / 规则」三类事实，实现长度 + 信号加权的重要性评分，并采用「语义 + 新鲜度 + 重要性」综合排序。
- **MemPalace** — https://github.com/MemPalace/mempalace
  分层存储结构与长程记忆锚定。本系统采用说话人折叠的分块策略与超长文本切分，实现长上下文的多条独立可检索记忆锚定。
- **Vectorize Hindsight** — https://github.com/vectorize-io/hindsight
  事后去重降噪与记忆治理机制。本系统在写入前用向量相似度检测近重复并跳过冗余记忆，实现增量幂等更新。

### 本次主要改动

1. **混合检索策略优化**：稠密 + BM25 + 图谱三路召回，RRF 融合 + 语义/新鲜度/重要性重排。
2. **冲突检测修正**：偏好 / 规则改为可累加（互不取代），仅互斥属性（地点/职业/姓名）触发版本取代，避免误删互补记忆。
3. **认识论安全门新增**：相关性阈值 + 关键词 + 图谱三重信号门控，无匹配严格返回空数组。
4. **API 契约对齐 AML 官方规范**：字段 / 类型 / 嵌套结构 / 同步语义 / 空结果行为逐条对齐。
5. **嵌入编码修正**：为 bge 模型补上 query 指令前缀，并拆分「返回内容」与「索引文本」，消除时间戳前缀对语义信号的污染。
6. **性能优化**：索引可重建、单锁串行化、嵌入模型启动预热，Add/Search 达 Fast 档位。

---

## 6. 模型与配置说明

- **嵌入模型**：默认 `BAAI/bge-small-en-v1.5`（384 维，本地 ONNX 推理，构建期下载）。
- **可选增强**：`LLM_EXTRACT=1` 时启用 `gpt-4o-mini` 事实/实体抽取增强，**默认关闭**以保证可复现（学术榜要求 Add/Search 所用模型为 `gpt-4o-mini`）。
- **关键配置项**（环境变量）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 嵌入模型 |
| `QUERY_INSTRUCTION` | 自动 | query 侧提示前缀（bge/E5） |
| `MIN_SEMANTIC` | `0.4` | 认识论安全门语义阈值 |
| `DB_PATH` | `data/memory.db` | SQLite 存储位置 |
| `DEFAULT_TOP_K` / `MAX_TOP_K` | `10` / `200` | 检索数量限制 |
| `DENSE_RECALL` / `BM25_RECALL` / `GRAPH_RECALL` | `50` / `50` / `30` | 多路召回宽度 |
| `LLM_EXTRACT` | `0` | 是否启用 gpt-4o-mini 增强 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | — | OpenAI 兼容端点 |

---

## 7. 验证说明

- **宿主机全量冒烟测试通过**（8/8）：健康检查、Add 回显、立即可检索、`user_id` 隔离、认识论安全门、字段格式、真实嵌入模型加载、同义检索。
- **真实嵌入模型验证通过**：`BAAI/bge-small-en-v1.5` 成功加载（未走哈希降级路径），同义检索 `"I enjoy hiking on weekends"` → `"outdoor activities?"` score 0.66 > 0.6。
- **性能基线**：Add 均值 ~62ms、Search 均值 ~60ms（Fast 档位）。
- **15 项单元测试通过**（`pytest -q`）。

```bash
pip install -r requirements-dev.txt
pytest -q                    # 单元测试（哈希降级路径，离线可跑）
python scripts/validate.py   # 全量冒烟 + 真实嵌入 + 性能基线
```

验证详情见 [`docs/validation_report.json`](docs/validation_report.json)。

---

## 8. 本地离线评测

> **声明**：以下为**内部自建自测集**（非 AML 官方基准数据）的本地离线评测结果，分数为**参考分**，**不等同于官方线上榜单得分**，仅作内部优化参考。

综合参考分 **100.0（42/42）**，分维度：

| 维度 | 参考分 | 命中 |
| --- | --- | --- |
| A 显式事实召回 | 100.0 | 7/7 |
| B 关系与多跳组合推理 | 100.0 | 5/5 |
| C 时序与事件序列推理 | 100.0 | 6/6 |
| D 记忆治理 | 100.0 | 5/5 |
| E 个性化与关怀 | 100.0 | 8/8 |
| G 上下文学习与规则执行 | 100.0 | 6/6 |
| H 认识论安全与隐私 | 100.0 | 5/5 |

本阶段已修复三处缺陷：**H 认识论安全门**（阈值 `min_semantic` 0.4→0.52 + 查询级判定）、**D 姓名冲突检测**（姓名抽取与 `name:` 冲突键对齐）、**模型运行时加载**（强制 `local_files_only=True`，避免网络失败静默降级为哈希嵌入）。

详见 [`docs/local_self_evaluation_report.md`](docs/local_self_evaluation_report.md)；测试集与运行脚本见 `tests/benchmark/`。

> 官方首期评测窗口已关闭，系统已完成本地验证，等待 **2026-09-20 第二期**开放后提交官方线上评测。

---

## 数据合规声明

本系统不持久化评测数据用于训练、不分析或共享评测内容、不记录记忆正文日志，数据可在运行结束后 30 天内删除（直接移除 SQLite 文件即可）。
