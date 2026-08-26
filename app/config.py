"""Runtime configuration for the AML memory system.

Every knob is driven by environment variables so the Docker image stays
self-contained (model weights are downloaded at build time, no secrets are
bundled) and the academic-board reproduction requirement (deterministic,
reproducible Add/Search) is satisfiable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class Settings:
    # --- embedding ---------------------------------------------------------
    # fastembed model id. English is the default because the AML textual suite
    # (PersonaMem, LoCoMo, CLBench, BEAM, LongMemEval-S, ScriptMem) is English.
    embedding_model: str = os.environ.get(
        "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
    )
    embedding_dim: int = _env_int("EMBEDDING_DIM", 384)
    # Optional query-instruction prefix (bge/E5 family). Empty = auto-detect
    # from the model name so bge models use their documented query prompt.
    query_instruction: str = os.environ.get("QUERY_INSTRUCTION", "")
    # When True, fall back to a deterministic hashing embedding if the model
    # cannot be loaded (keeps the service alive offline / during tests).
    embedding_fallback: bool = _env_bool("EMBEDDING_FALLBACK", True)

    # --- storage -----------------------------------------------------------
    db_path: str = os.environ.get("DB_PATH", "data/memory.db")

    # --- retrieval ---------------------------------------------------------
    default_top_k: int = _env_int("DEFAULT_TOP_K", 10)
    max_top_k: int = _env_int("MAX_TOP_K", 200)
    # Multi-path recall widths (before fusion / rerank).
    dense_recall: int = _env_int("DENSE_RECALL", 50)
    bm25_recall: int = _env_int("BM25_RECALL", 50)
    graph_recall: int = _env_int("GRAPH_RECALL", 30)
    # Fusion weights (dense / bm25 / graph) for reciprocal-rank fusion.
    fuse_dense: float = _env_float("FUSE_DENSE", 1.0)
    fuse_bm25: float = _env_float("FUSE_BM25", 0.8)
    fuse_graph: float = _env_float("FUSE_GRAPH", 0.6)
    # Rerank weights (semantic similarity / freshness / importance).
    rerank_semantic: float = _env_float("RERANK_SEMANTIC", 0.55)
    rerank_freshness: float = _env_float("RERANK_FRESHNESS", 0.20)
    rerank_importance: float = _env_float("RERANK_IMPORTANCE", 0.25)
    # Epistemic-safety floor: a candidate is "relevant" only if its semantic
    # similarity meets this threshold OR it has BM25 keyword overlap OR a graph
    # path. Below the floor with no keyword/graph signal -> excluded (so Search
    # returns an empty array rather than a weakly-related memory).
    # bge-small-en-v1.5 的无关文本余弦基线约 0.35~0.45；0.52 留出安全裕度，
    # 使无关查询返回空数组（原 0.4 落在基线带内，会把弱相关记忆误放行）。
    min_semantic: float = _env_float("MIN_SEMANTIC", 0.52)

    # --- ingest ------------------------------------------------------------
    # Merge consecutive messages from the same speaker into a single chunk up
    # to this many characters (MemPalace-style chunking / MemOS event blocks).
    chunk_max_chars: int = _env_int("CHUNK_MAX_CHARS", 1600)
    # Number of consecutive same-speaker turns folded into one chunk max.
    chunk_max_turns: int = _env_int("CHUNK_MAX_TURNS", 4)

    # --- governance --------------------------------------------------------
    # Importance thresholds (0..1). Low-value memories are candidates for
    # dedup/merge and are ranked lower.
    importance_fact_boost: float = _env_float("IMPORTANCE_FACT_BOOST", 0.35)
    importance_rule_boost: float = _env_float("IMPORTANCE_RULE_BOOST", 0.30)
    importance_preference_boost: float = _env_float("IMPORTANCE_PREFERENCE_BOOST", 0.30)
    # Near-duplicate Jaccard/similarity threshold for Hindsight-style merge.
    dedup_similarity: float = _env_float("DEDUP_SIMILARITY", 0.92)
    # Maximum retained memories per (user_id, session_id) before low-importance
    # pruning kicks in. Set to 0 to disable pruning.
    retention_max_per_session: int = _env_int("RETENTION_MAX_PER_SESSION", 0)

    # --- optional LLM extraction (Cognee/Mem0 quality path) ----------------
    # Deterministic extraction is always on. If LLM_EXTRACT=1 and an
    # OpenAI-compatible endpoint is configured, Add runs a light gpt-4o-mini
    # fact/entity pass. For academic-board submissions the model must remain
    # gpt-4o-mini per the AML rules.
    llm_extract: bool = _env_bool("LLM_EXTRACT", False)
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "")
    llm_api_key: str = os.environ.get("LLM_API_KEY", "")
    llm_model: str = os.environ.get("LLM_MODEL", "gpt-4o-mini")


settings = Settings()
