# 本地自测验证报告

> **前置声明**：本报告基于**内部自建的自测集**（`tests/benchmark/self_test_suite.json`），
> 所有用例为人工设计的**确定性合成样本**，与 AML 官方基准数据集**无关**。
> 本报告分数为**本地参考分**，**不等同于、也不代表官方线上榜单得分**，仅用于内部迭代优化。
> 官方首期评测窗口已关闭，系统已完成本地验证，等待 2026-09-20 第二期开放后提交官方线上评测。

---

## 一、测试环境

| 项 | 值 |
| --- | --- |
| 评测对象 | `aml-memory-system:latest`（Docker 容器，`http://localhost:8000`） |
| 嵌入模型 | `BAAI/bge-small-en-v1.5`（384 维，真实模型，非哈希降级） |
| 检索参数 | `top_k=100`，`min_semantic=0.52`（认识论安全门，已校准） |
| 测试集 | 自建 7 维能力用例，42 题（A/B/C/D/E/G/H），每维 5–8 题 |
| 判定方式 | 基于 Search 返回的原始记忆证据做透明子串命中判定（见 `self_test_suite.json`） |
| 可复现 | `python tests/benchmark/run_self_test.py`（需**全新卷**启动，见「复现方式」） |

## 二、总体结果

**综合参考分：100.0（42/42 题命中）**

| 维度 | 得分 | 命中 |
| --- | --- | --- |
| A 显式事实召回 | **100.0** | 7/7 |
| B 关系与多跳组合推理 | **100.0** | 5/5 |
| C 时序与事件序列推理 | **100.0** | 6/6 |
| D 记忆治理 | **100.0** | 5/5 |
| E 个性化与关怀 | **100.0** | 8/8 |
| G 上下文学习与规则执行 | **100.0** | 6/6 |
| H 认识论安全与隐私 | **100.0** | 5/5 |

## 三、分维度分析

### A 显式事实召回 —— 100（7/7）
职业、地点、纪念日、车辆、数字类事实、相似表述区分、长文本低频事实全部命中。
长文本低频事实 `Kowalczyk`（埋在 ~380 字符填充文本中）被 BM25 关键字兜底正确召回。

### B 关系与多跳组合 —— 100（5/5）
一跳/二跳/三跳证据链均可在 `top_k=100` 下被多路召回 + RRF 融合同时返回。
**注意**：这仅证明「证据链可被同时召回」，不代表系统具备真正的多跳推理（单次 Search 无法迭代式关联），真实大规模多跳题仍会变难。

### C 时序与事件序列 —— 100（6/6）
按天事件映射、最新状态、时间范围均命中；时间戳保留与相对新鲜度排序正常。

### D 记忆治理 —— 100（5/5）✅（修复后）
- ✅ 地点覆盖：`I live in Boston` → `I live in Seattle` 后仅返回 Seattle。
- ✅ 职业覆盖：`Acme` → `Globex` 正确覆盖。
- ✅ 姓名覆盖：`I'm called Alice` → `I'm called Carol` 后仅返回 Carol（旧值被取代）。
- ✅ 多值偏好累加：coffee 与 tea 均保留。
- ✅ 去重：重复写入 `I have a cat named Luna` 仅保留 1 条。

### E 个性化与关怀 —— 100（8/8）
偏好、忌口、过敏、负面偏好、长期习惯、身份背景、多偏好组合全部命中。

### G 上下文学习与规则执行 —— 100（6/6）
`always/never/must/make sure/have to/don't forget` 六类规则语句全部正确召回。

### H 认识论安全与隐私 —— 100（5/5）✅（修复后）
- ✅ 无关查询返回空数组（`quantum mechanics` / `blood type` / `FIFA` 均空）。
- ✅ 用户隔离：`u_h` 不泄露 `u_h2` 的 Paris。
- ✅ 隐私隔离：`u_h` 查询不泄露 `u_h2` 的信用卡号。

## 四、修复说明（本阶段落地）

| # | 短板 | 根因 | 修复 | 效果 |
| --- | --- | --- | --- | --- |
| 1 | H 认识论安全（原 40 分） | `min_semantic=0.4` 落在 bge-small 无关文本余弦基线（0.35~0.45）内，无关查询误返回记忆 | ①阈值上调至 `0.52`；②检索门改为**查询级判定**（`app/retrieval/hybrid.py`：查询有任一强信号才返回候选，否则空数组），避免逐候选过滤误杀多跳证据链 | 40 → **100** |
| 2 | D 姓名覆盖（原 80 分） | 姓名冲突检测为死代码：`_IDENTITY_RE` 的 `\b(?:I\|i)\s+` 要求 I 后有空格，导致 `I'm` 收缩式与 `My name is` 均不产生事实，`_NAME_RE` 永远匹配不到 | ①`app/ingest/extractor.py` 新增姓名抽取正则 `_NAME_RE`（`my name is / call me / you can call me / I'm called / I am called`）+ 裸姓名 `_BARE_NAME_RE`（`I'm X / I am X`，仅单大写词避免误判职业）；②`app/governance/conflict.py` 的 `_fact_key` 识别 `name:` 前缀 | 80 → **100** |
| 3 | 模型运行时降级（隐藏缺陷） | fastembed 运行时 `local_files_only=False` 会联网校验/下载模型，网络被墙失败后**静默降级为哈希嵌入**，破坏语义检索 | `app/core/embedding.py` 加载时传 `local_files_only=True`（模型已在构建期预下载进镜像） | 稳定真实加载（`using_fallback=False`） |

## 五、性能数据

| 指标 | 值 |
| --- | --- |
| Add 平均耗时 | 78.82 ms |
| Add p95 | 120.54 ms |
| Search 平均耗时 | 75.34 ms |
| Search p95 | 83.21 ms |
| 写入立即可检索 | 32/32（100%） |

> 结论：Add/Search 均处于 Fast 档位（<200ms），同步语义稳定。

## 六、复现方式

```bash
# 1. 全新卷启动（务必用 down -v 彻底清卷，rm db + restart 会因 SQLite 连接残留导致脏数据）
docker compose down -v && docker compose up -d

# 2. 运行自测
python tests/benchmark/run_self_test.py

# 3. 结果
#    tests/benchmark/self_test_results.json  —— 逐题命中/耗时明细
#    tests/benchmark/self_test_suite.json    —— 用例定义（可复现）
```

> 说明：评测期间曾出现「姓名事实抽取正确却未存储」的假象，最终定位为**陈旧数据库残留**——
> `docker exec rm /data/memory.db` + `docker compose restart` 并未真正清库（优雅关闭时已打开的
> SQLite 连接会重建文件），导致自测在脏数据上运行、所有写入被去重跳过。改用 `docker compose down -v`
> 彻底清卷后问题消失，D 维与 H 维修复全部生效。
