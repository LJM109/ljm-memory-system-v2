"""Graph-path recall (Cognee-style multi-hop entity association).

The query is mapped onto the entity graph: 1-hop = memories sharing a query
entity; 2-hop = memories sharing an entity with a 1-hop memory. This surfaces
evidence that is semantically related but not lexically overlapping — the
mechanism behind relational / multi-hop recall.
"""
from __future__ import annotations

from ..ingest.extractor import extract_entities
from ..storage.sqlite_store import SQLiteStore


def recall(
    query: str, user_id: str, store: SQLiteStore, k: int
) -> list[tuple[str, float]]:
    """Return top-k (memory_id, graph_score) for a query (user-scoped)."""
    q_entities = [name for name, _etype in extract_entities(query)]
    if not q_entities:
        return []

    # 1-hop: memories directly sharing a query entity.
    hop1: dict[str, int] = {}
    name_to_mems = store.memories_for_entities(q_entities, user_id)
    for name in q_entities:
        for mid in name_to_mems.get(name, []):
            hop1[mid] = hop1.get(mid, 0) + 1

    # 2-hop: entities of hop1 memories -> further memories.
    hop1_entity_names = store.entities_for_memories(list(hop1.keys()), user_id)
    if hop1_entity_names:
        # Exclude entities already directly matched to avoid trivial loops.
        extra = [n for n in hop1_entity_names if n not in set(q_entities)]
        if extra:
            for name in extra:
                for mid in store.memories_for_entities([name], user_id).get(name, []):
                    if mid in hop1:
                        continue
                    hop1[mid] = hop1.get(mid, 0) + 0.5  # type: ignore[assignment]

    scored = sorted(hop1.items(), key=lambda pair: pair[1], reverse=True)
    return [(mid, float(score)) for mid, score in scored[:k]]
