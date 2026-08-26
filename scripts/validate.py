"""End-to-end validation of the AML memory service.

Runs the full smoke suite (health / add echo / immediate-search / isolation /
epistemic-safety / response-shape), verifies the *real* embedding model is
active (not the hashing fallback), performs the synonym-retrieval check, and
records an Add/Search latency baseline.

Usage:
    ./.venv312/Scripts/python.exe scripts/validate.py     # or any python with deps

Writes a JSON report to docs/validation_report.json and prints a summary.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone

# Ensure the project root (parent of scripts/) is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.core.embedding import get_embedding_model


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def main_run() -> None:
    settings.db_path = os.path.join(tempfile.mkdtemp(), "validate.db")
    settings.llm_extract = False
    main._system = None

    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

    with TestClient(main.app) as client:
        embedder = get_embedding_model()
        using_fallback = embedder.using_fallback
        check(
            "real_embedding_active",
            not using_fallback,
            f"fastembed model={settings.embedding_model} dim={embedder.dim}"
            + (" (FALLBACK — model failed to load)" if using_fallback else ""),
        )

        # 1. health
        r = client.get("/health")
        check("health_200", r.status_code == 200, f"status={r.status_code}")

        # 2. add with standard + extra field
        t0 = now_ms()
        r = client.post(
            "/v1/memories/add",
            json={
                "user_id": "alice",
                "session_id": "s1",
                "request_id": "req-1",
                "async_mode": False,
                "messages": [
                    {"role": "user", "content": "I live in New York.", "timestamp": t0}
                ],
            },
        )
        check(
            "add_200_and_echo",
            r.status_code == 200 and r.json().get("request_id") == "req-1",
            f"status={r.status_code} body={r.text}",
        )

        # 3. immediate searchability
        r = client.post(
            "/v1/memories/search",
            json={"user_id": "alice", "query": "Where do I live?", "top_k": 5},
        )
        data = r.json().get("data", [])
        check(
            "immediate_search_hit",
            r.status_code == 200 and any("New York" in m["content"] for m in data),
            f"n={len(data)}",
        )

        # 4. user_id isolation
        client.post(
            "/v1/memories/add",
            json={
                "user_id": "bob",
                "request_id": "req-2",
                "messages": [{"role": "user", "content": "I live in Tokyo."}],
            },
        )
        r = client.post(
            "/v1/memories/search",
            json={"user_id": "alice", "query": "Where do I live?", "top_k": 5},
        )
        alice_data = r.json().get("data", [])
        check(
            "user_id_isolation",
            all("Tokyo" not in m["content"] for m in alice_data),
            f"alice sees {len(alice_data)} memories, none from bob",
        )

        # 5. epistemic safety (empty on irrelevant query)
        r = client.post(
            "/v1/memories/search",
            json={"user_id": "alice", "query": "quantum field theory vacuum", "top_k": 5},
        )
        check("epistemic_safety_empty", r.json() == {"data": []}, f"body={r.text}")

        # 6. response field shape + ISO-8601 created_at
        r = client.post(
            "/v1/memories/search",
            json={"user_id": "alice", "query": "New York", "top_k": 5},
        )
        items = r.json().get("data", [])
        shape_ok = bool(items) and all(
            set(m.keys()) == {"id", "content", "score", "created_at"} for m in items
        )
        iso_ok = all(isinstance(m["created_at"], str) and "T" in m["created_at"] for m in items)
        check(
            "response_shape_iso8601",
            shape_ok and iso_ok,
            f"keys_ok={shape_ok} iso_ok={iso_ok}",
        )

        # 7. synonym retrieval (real embeddings only meaningful here)
        client.post(
            "/v1/memories/add",
            json={
                "user_id": "alice",
                "request_id": "req-3",
                "messages": [
                    {"role": "user", "content": "I enjoy hiking on weekends.", "timestamp": now_ms()}
                ],
            },
        )
        r = client.post(
            "/v1/memories/search",
            json={
                "user_id": "alice",
                "query": "Does the user like outdoor activities?",
                "top_k": 5,
            },
        )
        syn = r.json().get("data", [])
        hit = any("hiking" in m["content"] for m in syn)
        top_score = syn[0]["score"] if syn else 0.0
        check(
            "synonym_retrieval",
            hit and top_score > 0.6,
            f"hit={hit} top_score={top_score}",
        )

        # 8. latency baseline (after warmup)
        add_lat, search_lat = [], []
        for i in range(20):
            t = time.perf_counter()
            client.post(
                "/v1/memories/add",
                json={
                    "user_id": "alice",
                    "request_id": f"perf-{i}",
                    "messages": [{"role": "user", "content": f"Memory number {i} about travel."}],
                },
            )
            add_lat.append((time.perf_counter() - t) * 1000)
        for _ in range(20):
            t = time.perf_counter()
            client.post(
                "/v1/memories/search",
                json={"user_id": "alice", "query": "travel", "top_k": 10},
            )
            search_lat.append((time.perf_counter() - t) * 1000)

        def stats(xs):
            return {
                "avg_ms": round(statistics.mean(xs), 2),
                "p95_ms": round(sorted(xs)[int(len(xs) * 0.95) - 1], 2),
                "max_ms": round(max(xs), 2),
            }

        perf = {"add": stats(add_lat), "search": stats(search_lat)}
        print(f"\nLatency baseline: add={perf['add']} search={perf['search']}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": settings.embedding_model,
        "real_embedding_active": not using_fallback,
        "checks": checks,
        "latency": perf,
        "all_passed": all(c["passed"] for c in checks),
    }
    os.makedirs("docs", exist_ok=True)
    with open("docs/validation_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\nReport written to docs/validation_report.json  (all_passed={report['all_passed']})")
    raise SystemExit(0 if report["all_passed"] else 1)


if __name__ == "__main__":
    main_run()
