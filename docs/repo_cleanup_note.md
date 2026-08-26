# 仓库净化说明（提交前）

本文件记录提交前为「本地中国网络环境」临时引入、后已全部还原的适配项。目的是确保仓库本身**不含任何代理、镜像源等本地特定配置**，平台可在标准 Linux 环境（无代理）直接构建运行。

---

## 一、本次移除的本地适配项

| 文件 | 本地临时改动 | 已还原为 |
| --- | --- | --- |
| `Dockerfile` | `ARG BASE_IMAGE` + `FROM ${BASE_IMAGE}`（基础镜像走国内镜像加速） | `FROM python:3.11-slim` |
| `Dockerfile` | `ARG HTTP_PROXY / HTTPS_PROXY / NO_PROXY`（构建期代理） | 已移除 |
| `docker-compose.yml` | `build.args.BASE_IMAGE = docker.m.daocloud.io/library/python:3.11-slim` | `build: .` |
| `docker-compose.yml` | `build.args.HTTP_PROXY / HTTPS_PROXY / NO_PROXY`（`host.docker.internal:7993`） | 已移除 |

## 二、本次会话中曾尝试、已提前弃用的适配项

| 文件 | 改动 | 状态 |
| --- | --- | --- |
| `Dockerfile` | `ENV HF_ENDPOINT=https://hf-mirror.com` | 已移除（在净化前即弃用） |
| `docker-compose.yml` | `environment.HF_ENDPOINT: https://hf-mirror.com` | 已移除（同上） |

> `hf-mirror.com` 曾被尝试用于绕过 HuggingFace 境外网络，但因其文件 HEAD 响应缺失 `X-Repo-Commit` 头，与 `huggingface_hub>=0.24` 不兼容（报 `FileMetadataError`），最终弃用，改走宿主机代理直连 huggingface.co。

## 三、背景（为何需要这些适配）

本地为 Windows 11（中国网络），`registry-1.docker.io` 与 `huggingface.co` 直连被阻断，导致构建在拉取基础镜像与下载模型权重两个阶段均失败。为完成本地全量构建与冒烟验证，临时引入：

1. **Docker Hub 镜像加速**：基础镜像 `python:3.11-slim` 改用 `docker.m.daocloud.io` 国内镜像源。
2. **宿主机代理**：Docker Desktop 代理配置为 `127.0.0.1:7993`（Clash），构建期模型下载经 `host.docker.internal:7993` 走代理直连 huggingface.co。

## 四、仓库现状（净化后）

`Dockerfile` 与 `docker-compose.yml` 已恢复为通用无代理版本：

- **基础镜像**：官方 `python:3.11-slim`
- **模型下载**：构建期直接访问 huggingface.co（标准环境可直连）
- **无任何硬编码**：无代理地址、无镜像源、无 `HF_ENDPOINT`

平台在标准 Linux 环境可直接执行 `docker compose up --build` 构建运行，无需任何代理或镜像配置。

## 五、宿主机侧残留（不属于仓库内容）

以下为本地宿主机（非仓库文件）为验证保留的改动，**与评测平台构建无关**：

- Docker Desktop 代理配置 `settings-store.json` 已指向 `127.0.0.1:7993`（原误配为 `7890`）。
- 本地镜像 `aml-memory-system:latest`、容器 `aml-memory`、卷 `memory_data` 可保留本地使用，或用 `docker compose down -v` 清理。

> 评测平台构建环境不读取任何宿主机 Docker Desktop 配置，上述宿主机残留不影响平台构建。
