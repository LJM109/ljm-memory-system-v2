"""Shared test fixtures: isolated SQLite DB + FastAPI TestClient.

The embedding model falls back to deterministic feature hashing when the
ONNX model is unavailable, so tests run offline without network access.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "llm_extract", False)
    monkeypatch.setattr(settings, "embedding_fallback", True)
    # Disable dedup merging so distinct test messages are never folded together.
    monkeypatch.setattr(settings, "dedup_similarity", 0.999)
    main._system = None
    with TestClient(main.app) as c:
        yield c
    main._system = None


def add(client: TestClient, user_id: str, texts: list[str], **extra) -> dict:
    messages = [
        {"role": "user", "content": text, "timestamp": 1000 + i}
        for i, text in enumerate(texts)
    ]
    body = {
        "user_id": user_id,
        "session_id": extra.pop("session_id", "s1"),
        "request_id": extra.pop("request_id", f"req-{user_id}"),
        "messages": messages,
    }
    body.update(extra)
    response = client.post("/v1/memories/add", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def search(client: TestClient, user_id: str, query: str, top_k: int = 10) -> dict:
    response = client.post(
        "/v1/memories/search",
        json={"user_id": user_id, "query": query, "top_k": top_k},
    )
    assert response.status_code == 200, response.text
    return response.json()
