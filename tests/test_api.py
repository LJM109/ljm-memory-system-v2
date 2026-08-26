"""API contract tests: Add/Search round-trip, response shape, error handling."""
from __future__ import annotations

from .conftest import add, search


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_add_returns_200_and_echoes_request_id(client):
    payload = add(client, "u1", ["hello"], request_id="req-123")
    assert payload["request_id"] == "req-123"


def test_add_accepts_extra_fields(client):
    """The evaluator may send fields like async_mode; we must not 422 on them."""
    response = client.post(
        "/v1/memories/add",
        json={
            "user_id": "u1",
            "session_id": "s1",
            "request_id": "r1",
            "async_mode": False,
            "messages": [{"role": "user", "content": "hi", "timestamp": 5}],
        },
    )
    assert response.status_code == 200, response.text


def test_add_and_search_roundtrip(client):
    add(client, "u1", ["I live in New York and work at Google."])
    result = search(client, "u1", "Where do I live?")
    assert result["data"], "expected at least one memory"
    assert any("New York" in item["content"] for item in result["data"])


def test_search_response_shape(client):
    add(client, "u1", ["My favorite color is blue."])
    result = search(client, "u1", "favorite color")
    assert set(result.keys()) == {"data"}
    for item in result["data"]:
        assert set(item.keys()) == {"id", "content", "score", "created_at"}
        assert isinstance(item["id"], str)
        assert isinstance(item["content"], str)
        assert isinstance(item["score"], float)
        assert isinstance(item["created_at"], str)


def test_search_empty_when_no_relevant_memory(client):
    add(client, "u1", ["I like coffee in the morning."])
    result = search(client, "u1", "quantum chromodynamics lattice gauge")
    assert result["data"] == []


def test_top_k_respected(client):
    for i in range(20):
        add(client, "u1", [f"I own a {i}-year-old cat named Pet{i}."], request_id=f"r{i}")
    result = search(client, "u1", "cat", top_k=3)
    assert len(result["data"]) <= 3


def test_add_synchronous_immediately_searchable(client):
    add(client, "u1", ["I am a vegetarian."])
    # No artificial delay: the memory must be searchable right after Add.
    result = search(client, "u1", "vegetarian")
    assert any("vegetarian" in item["content"] for item in result["data"])


def test_add_missing_user_id_returns_422(client):
    response = client.post(
        "/v1/memories/add",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 422


def test_search_missing_query_returns_422(client):
    response = client.post("/v1/memories/search", json={"user_id": "u1"})
    assert response.status_code == 422


def test_empty_messages_returns_200(client):
    response = client.post(
        "/v1/memories/add",
        json={"user_id": "u1", "request_id": "r0", "messages": []},
    )
    assert response.status_code == 200
    assert response.json()["request_id"] == "r0"
