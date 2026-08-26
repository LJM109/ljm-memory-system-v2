# API 合规校验报告

逐条对照 AML `Add` / `Search` / `health` 官方契约，确认接口字段、类型、
嵌套结构、行为完全符合要求。

## 1. 接口清单

| 项 | 规范要求 | 实现 | 结论 |
| --- | --- | --- | --- |
| 写入接口 | `POST /v1/memories/add` | `app/main.py::add_memories` | ✅ |
| 检索接口 | `POST /v1/memories/search` | `app/main.py::search_memories` | ✅ |
| 健康检查 | `GET /health`（可选） | `app/main.py::health` | ✅ |
| 监听地址 | `0.0.0.0:8000` | uvicorn `--host 0.0.0.0 --port 8000` | ✅ |

## 2. Add 请求字段

| 字段 | 类型 | 规范 | 实现 | 结论 |
| --- | --- | --- | --- | --- |
| `user_id` | string | 检索作用域，原样存储并隔离 | 必填；所有查询按此隔离 | ✅ |
| `session_id` | string | 源会话标识，用于分组 | 可选；写入分组 | ✅ |
| `request_id` | string | 写入唯一标识，响应中原样返回 | 可选；响应回显 | ✅ |
| `messages` | array | 有序消息列表 | `list[AddMessage]`，按序处理 | ✅ |
| `messages[].role` | string | `user`/`assistant`/`system` | 字符串，默认 `user` | ✅ |
| `messages[].content` | string | 原始消息文本 | 字符串 | ✅ |
| `messages[].timestamp` | int | Unix 毫秒（可选） | `int | None` | ✅ |
| 额外字段 | — | 不得 422 拒绝 | `extra="allow"`，忽略 `async_mode` 等 | ✅ |

## 3. Add 响应

| 项 | 规范 | 实现 | 结论 |
| --- | --- | --- | --- |
| 状态码 | 200（同步） | 仅写入+索引完成后返回 | ✅ |
| 禁止 | 202 / task_id / 轮询地址 | 均未实现 | ✅ |
| 响应体 | 回显 `request_id` | `{"request_id": "…"}` | ✅ |
| 立即可检索 | 写入完成即 Search 可见 | 单锁内完成持久化+索引 | ✅ |

## 4. Search 请求字段

| 字段 | 类型 | 规范 | 实现 | 结论 |
| --- | --- | --- | --- | --- |
| `query` | string | 原始问题，保持不变 | 字符串；检索时拼接选项增强召回 | ✅ |
| `options` | array | 选择题候选项，无选项不发送 | 可选，省略时 None | ✅ |
| `user_id` | string | 与 Add 完全一致 | 严格按 user_id 过滤 | ✅ |
| `top_k` | int | 最大返回条数 | `1..200`，默认 10 | ✅ |

## 5. Search 响应

| 字段 | 类型 | 规范 | 实现 | 结论 |
| --- | --- | --- | --- | --- |
| `data` | array | 按相关性降序，最多 top_k 条 | 融合重排后降序截断 | ✅ |
| `data[].id` | string | 稳定标识 | `mem_` + 内容哈希（幂等） | ✅ |
| `data[].content` | string | 提供给回答模型的记忆文本 | 原始证据（含说话人/时间） | ✅ |
| `data[].score` | float | 数值越高越相关 | `[0,1]` 融合分，与顺序单调一致 | ✅ |
| `data[].created_at` | string | 来源/持久化时间戳 | ISO-8601 | ✅ |
| 空结果 | `{"data":[]}` | 无相关记忆返回空数组 | 精确实现，不编造 | ✅ |

## 6. 硬性约束

| 约束 | 实现 | 结论 |
| --- | --- | --- |
| Search 只返回记忆证据，不生成答案 | 直接返回原始 chunk 文本 | ✅ |
| 不拼接结论 / 不伪装记忆 | content 为忠实消息文本 + 说话人/时间元数据 | ✅ |
| user_id 级数据隔离，禁止跨用户检索 | 存储层 `memory_ids_by_user` 过滤 + 图/向量均带 user 作用域 | ✅ |
| 不硬编码评测答案 / 不泄露评测数据 | 无任何内置答案；不写日志；数据可删除 | ✅ |
| 模型权重构建期下载，git 不含二进制 | Dockerfile 构建阶段预下载；`.dockerignore` 排除 | ✅ |

## 7. 评分边界对齐

- **返回体量 Balanced 档**：默认 `top_k=10`，`MAX_TOP_K=200`，避免过度冗余。
- **Fast 档响应速度**：检索为 O(用户记忆数) 矩阵/BM25 计算，毫秒级；嵌入模型
  启动预热一次，后续 Add/Search 无模型加载开销。
- **时序（C 维度）**：保留 `ts/ts_min` 与 `created_at`，冲突记忆按最新优先，
  `event_ordering` 类题目可依据内容内时间戳重建顺序。
- **认识论安全（G 维度）**：`Search` 无匹配时返回 `{"data":[]}`，绝不强行回答。
