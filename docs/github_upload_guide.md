# GitHub 上传指引

## 方式一：本地 Git 命令（PowerShell）

在 PowerShell 中逐段复制执行（`<your-account>` 替换为你的 GitHub 用户名）：

```powershell
# 1. 进入项目根目录
cd "D:\AML Agent Memory v2"

# 2. 初始化仓库并切换到 main 分支
git init
git branch -M main

# 3. 添加所有文件（.gitignore 已自动排除缓存/权重/密钥）
git add -A

# 4. 确认暂存内容（确认无 .venv312、无 *.bin、无 .env）
git status

# 5. 生成规范提交信息并提交
$body = @"
- 基线MemOS，融合Cognee/Mem0/MemPalace/Hindsight核心模块
- 修复嵌入编码前缀、语义阈值、时间衰减三个核心问题
- 全量冒烟+真实嵌入模型验证通过，性能Fast档位
- 完整归因披露，符合学术榜合规要求
"@
git commit -m "feat: v2.0 多系统融合记忆系统 | 宿主机全量验证通过 | API对齐AML官方契约 | 七大能力维度优化" -m $body

# 6. 关联远程仓库并推送（先在 GitHub 网页创建空仓库 ljm-memory-system）
git remote add origin https://github.com/<your-account>/ljm-memory-system.git
git push -u origin main
```

> 若第 6 步 push 因网络失败，改用「方式二」网页手动上传。

## 方式二：GitHub 网页手动上传（兜底）

在 GitHub 新建仓库 `ljm-memory-system`（**不要**勾选自动生成 README/.gitignore，保持空仓库），然后按以下顺序上传：

### 第 1 步：根目录文件（先上传，一次一个）

点击「Add file → Upload files」，将以下 **7 个文件**直接拖入仓库**根目录**（不要放进任何子文件夹）：

1. `Dockerfile`
2. `docker-compose.yml`
3. `requirements.txt`
4. `requirements-dev.txt`
5. `README.md`
6. `.gitignore`
7. `.dockerignore`

> `.gitignore` / `.dockerignore` 是隐藏文件（以点开头），如网页看不到，需在文件资源管理器开启「显示隐藏文件」。

### 第 2 步：app 文件夹（整体上传，保持内部结构）

「Add file → Upload files」，拖入本地 **`app` 文件夹**（GitHub 会自动保留 `core/`、`ingest/`、`storage/`、`retrieval/`、`governance/` 子目录及所有 `.py` 文件）。确认上传后目录为：

```
app/
├── __init__.py
├── config.py
├── main.py
├── schemas.py
├── system.py
├── core/       (__init__.py, bm25.py, clock.py, embedding.py)
├── ingest/     (__init__.py, chunker.py, extractor.py, scoring.py, dedup.py)
├── storage/    (__init__.py, sqlite_store.py, vector_store.py)
├── retrieval/  (__init__.py, graph_recall.py, hybrid.py, rank.py)
└── governance/ (__init__.py, conflict.py, retention.py)
```

### 第 3 步：docs 文件夹

「Add file → Upload files」，拖入本地 `docs` 文件夹，确认包含：

```
docs/
├── fusion_design.md
├── api_compliance.md
├── validation_report.json
├── repo_compliance_report.md
└── github_upload_guide.md
```

### 第 4 步：tests 文件夹

拖入本地 `tests` 文件夹，确认包含：

```
tests/
├── __init__.py
├── conftest.py
├── test_api.py
└── test_governance.py
```

### 第 5 步：scripts 文件夹

拖入本地 `scripts` 文件夹，确认包含：

```
scripts/
└── validate.py
```

### 第 6 步：核对

上传完成后，在仓库首页核对根目录结构应为：

```
app/  docs/  tests/  scripts/  Dockerfile  docker-compose.yml
requirements.txt  requirements-dev.txt  README.md  .gitignore  .dockerignore
```

确认 **没有任何** `.venv312/`、`*.bin`、`*.safetensors`、`.env`、`__pycache__/` 被上传。

> 提示：网页上传单个文件夹超过 100 个文件会失败——本项目远低于该上限，可整文件夹拖拽。
