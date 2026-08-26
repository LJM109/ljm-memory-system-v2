"""Isolation, temporal update, and ordering tests."""
from __future__ import annotations

from .conftest import add, search


def test_user_isolation(client):
    add(client, "alice", ["I live in Paris."])
    add(client, "bob", ["I live in Tokyo."])
    result = search(client, "alice", "where do I live")
    # alice must never see bob's memory.
    assert all("Paris" in item["content"] for item in result["data"])
    assert not any("Tokyo" in item["content"] for item in result["data"])


def test_search_isolated_by_user_id_not_session(client):
    add(client, "alice", ["I love hiking."], session_id="session-a")
    add(client, "alice", ["I love painting."], session_id="session-b")
    # Search spans all sessions of the same user.
    result = search(client, "alice", "what do I love")
    contents = " ".join(item["content"] for item in result["data"])
    assert "hiking" in contents and "painting" in contents


def test_latest_state_preferred(client):
    add(client, "u1", ["I live in New York."], request_id="r-ny")
    add(client, "u1", ["I live in Boston."], request_id="r-boston")
    result = search(client, "u1", "where do I live", top_k=5)
    assert result["data"], "expected a memory"
    # The most recent location should appear; the stale one should be superseded.
    top_contents = [item["content"] for item in result["data"]]
    assert any("Boston" in c for c in top_contents)
    assert not any("New York" in c for c in top_contents)


def test_results_ordered_by_relevance(client):
    add(client, "u1", ["I love dogs."], request_id="r-dogs")
    add(client, "u1", ["The stock market closed higher today."], request_id="r-stock")
    result = search(client, "u1", "dogs", top_k=2)
    contents = [item["content"] for item in result["data"]]
    assert contents, "expected at least one memory"
    assert "dogs" in contents[0].lower()
