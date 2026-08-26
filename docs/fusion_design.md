# 系统融合设计说明

以 **MemOS** 为基线，融合 **Cognee / Mem0 / MemPalace / Vectorize Hindsight**
的核心优势模块，对齐 **Agent Memory Leaderboard (AML)** 文本记忆赛道的
7 大能力维度与 `Add` / `Search` 官方契约。本文逐仓库说明所提取的核心模块、
具体改动点、以及对应的能力维度收益。

能力维度对照（AML 文本记忆）：

| 代码 | 维度 |
| --- | --- |
| A | 显式事实召回 (Explicit fact recall) |
| B | 关系与多跳组合 (Relational & multi-hop) |
| C | 时序与事件序列 (Temporal & event ordering) |
| D | 记忆治理 (Memory governance) |
| E | 个性化与关怀 (Personalization & care) |
| F | 规则与流程执行 (Rules & process execution) |
| G | 认识论安全与隐私 (Epistemic safety & privacy) |

---

## 1. MemOS（基线）— https://github.com/MemTensor/MemOS

**提取模块：**
- 时序事件序列处理（事件块、时间戳）
- 记忆分层存储（原始事件 → 结构化事实 → 索引）
- 混合检索基座（稠密向量 + BM25 关键词）

**改动点：**
- `ingest/chunker.py`：把「逐条消息 = 事件」重构为「同说话人连续轮次 = 事件块」，
  并保留 `ts / ts_min`（Unix 毫秒）与 `turn_start/turn_end`，强化事件先后顺序。
- `retrieval/hybrid.py`：保留「稠密 + BM25」双路，新增图召回后做
  Reciprocal-Rank Fusion (RRF) 融合，替代单一线性加权。

**对应维度：** C（时序与事件序列）、A（显式事实召回）。

---

## 2. Cognee（知识图谱增强）— https://github.com/topoteretes/cognee

**提取模块：**
- 实体-关系自动抽取
- 结构化图谱构建 / 多跳关联
- 事实冲突检测与修正

**改动点：**
- `ingest/extractor.py`：用**确定性启发式 NER**（邮箱/URL/日期/专名/大写词组）
  替代图数据库与外部模型，抽取 `(entity, type)`，无需 Neo4j 等外部依赖。
- `retrieval/graph_recall.py`：构建「实体 → 记忆」倒排索引，检索时做
  **一跳 + 二跳**实体路径召回，支撑多跳证据关联。
- `governance/conflict.py`：新旧事实同主体异取值时，对「纯单事实记忆」做
  版本标记（`superseded_by`），实现「最新有效状态」；保守策略避免误删多事实记忆。

**对应维度：** B（关系与多跳）、D（记忆治理/冲突）。

---

## 3. Mem0（工业级基线）— https://github.com/mem0ai/mem0

**提取模块：**
- 事实自动提取（偏好 / 身份 / 规则）
- 记忆重要性评分
- 多存储后端兼容
- 相关性排序（语义 + 新鲜度 + 偏好权重）

**改动点：**
- `ingest/scoring.py`：重要性 = 长度 + 偏好/规则/身份信号 + 事实/实体数量，
  说话人加权（用户消息权重更高）。
- `ingest/extractor.py`：正则抽取「偏好 / 身份 / 规则」三类事实字符串。
- `retrieval/rank.py`：综合「语义相似度 + 时序新鲜度（指数衰减）+ 重要性」
  加权排序；`storage/` 提供 SQLite（源）+ numpy 向量（索引）双后端。

**对应维度：** A（显式事实）、E（个性化）、F（规则执行）、G（用户偏好权重）。

---

## 4. MemPalace（长程记忆）— https://github.com/MemPalace/mempalace

**提取模块：**
- 长文本分块 + 语义锚定编码
- 长跨度事实召回

**改动点：**
- `ingest/chunker.py`：超长文本按句子/换行切分到 `chunk_max_chars` 上限，
  每个分块独立可检索，长上下文拆成多条语义锚定的记忆。
- `retrieval/rank.py`：新鲜度采用 30 天半衰期指数衰减，长跨度事实按时间
  相对顺序召回，兼顾旧事实（重要度不衰减为 0）。

**对应维度：** A（长跨度事实召回率）、C（长对话时序）。

---

## 5. Vectorize Hindsight（事后整理）— https://github.com/vectorize-io/hindsight

**提取模块：**
- 对话后结构化总结 / 降噪
- 记忆去重 / 冗余清理
- 增量更新

**改动点：**
- `ingest/dedup.py`：写入前用向量相似度检测近重复（默认阈值 0.92），命中即
  跳过，避免连续会话中重复陈述堆积成冗余记忆。
- 增量更新：`Add` 幂等（记忆 id 由 `user|session|request|turn` 哈希决定），
  重试不产生重复记忆。

**对应维度：** 检索精准度（减少无效记忆干扰）、A（返回内容质量）。

---

## 6. AML 官方评测规范 — https://github.com/AML-memory/agent-memory-leaderboard

**提取与对齐：**
- `Add` / `Search` / `health` 三接口契约（字段、类型、嵌套）
- 7 大能力维度与评分边界
- `Search` 仅返回原始记忆证据、不生成答案的硬约束

**改动点：** `schemas.py`（`extra="allow"` 容忍 `async_mode` 等历史字段，避免
422 契约错配）、`main.py`（同步 Add、按相关性降序返回、无匹配返回空数组）。

**对应维度：** G（认识论安全：检索不到返回空、不编造）+ 全部维度（契约合规）。

---

## 关键设计决策

1. **`user_id` 级隔离，`session_id` 仅分组**：检索作用域严格按 `user_id`，
   `session_id` 只用于写入分组，跨用户检索在存储层被结构性禁止。
2. **同步 Add**：写入 + 建索引完成后才返回 200，杜绝「返回成功但检索不到」。
3. **确定性优先**：默认零外部依赖、零外部模型调用；可选 `gpt-4o-mini` 增强
   （AML 学术榜要求 Add/Search 模型为 gpt-4o-mini，已按此默认）。
4. **索引可重建**：SQLite 为唯一持久化源，向量/BM25/图索引均可从 SQLite
   重建，崩溃后可恢复。
