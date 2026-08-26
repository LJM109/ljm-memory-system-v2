"""Local self-test runner for the AML 7-dimension capability suite.

Writes all suite sessions via Add, then runs every question via Search against
the running service, applies transparent judge checks, and aggregates per-
dimension reference scores (0-100). Results are saved to
tests/benchmark/self_test_results.json.

Usage:
    python tests/benchmark/run_self_test.py
"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "tests" / "benchmark" / "self_test_suite.json"
OUT = ROOT / "tests" / "benchmark" / "self_test_results.json"

# trust_env=False avoids routing localhost through the host system proxy.
client = httpx.Client(base_url=BASE, timeout=60.0, trust_env=False)


def norm(s: str) -> str:
    return s.lower()


def contents(results: list[dict]) -> list[str]:
    return [norm(m.get("content", "")) for m in results]


def run_check(results: list[dict], check: dict) -> bool:
    t = check["type"]
    if t == "contains":
        return any(any(v.lower() in c for c in contents(results)) for v in check["values"])
    if t == "contains_all":
        return all(any(v.lower() in c for c in contents(results)) for v in check["values"])
    if t == "not_contains":
        return all(not any(v.lower() in c for c in contents(results)) for v in check["values"])
    if t == "empty":
        return len(results) == 0
    if t == "count_eq":
        return sum(1 for c in contents(results) if check["value"].lower() in c) == check["n"]
    raise ValueError(f"unknown check type: {t}")


def target_values(q: dict) -> list[str]:
    for chk in q["judge"]["checks"]:
        if chk["type"] in ("contains", "contains_all", "not_contains"):
            return chk.get("values", [])
        if chk["type"] == "count_eq":
            return [chk["value"]]
    return []


def rank_of(results: list[dict], values: list[str]) -> int | None:
    for i, m in enumerate(results):
        c = norm(m.get("content", ""))
        if any(v.lower() in c for v in values):
            return i + 1
    return None


def main() -> None:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    top_k = suite["meta"].get("top_k", 100)

    # Phase 1: write all sessions (in order) + immediate searchability check.
    write_records: list[dict] = []
    write_verify: list[dict] = []
    for user in suite["users"]:
        uid = user["user_id"]
        for sess in user["sessions"]:
            sid = sess["session_id"]
            msgs = sess["messages"]
            t0 = time.perf_counter()
            r = client.post("/v1/memories/add", json={
                "user_id": uid, "session_id": sid, "request_id": f"req-{uid}-{sid}",
                "messages": msgs,
            })
            dt = (time.perf_counter() - t0) * 1000
            ok = r.status_code == 200
            write_records.append({
                "user_id": uid, "session_id": sid, "ok": ok,
                "status": r.status_code, "ms": round(dt, 2),
            })
            if ok and msgs:
                r2 = client.post("/v1/memories/search", json={
                    "user_id": uid, "query": msgs[0]["content"], "top_k": 5,
                })
                data = r2.json().get("data", [])
                write_verify.append({
                    "user_id": uid, "session_id": sid,
                    "hit": len(data) > 0, "n": len(data),
                })

    # Phase 2: query + judge.
    q_records: list[dict] = []
    for q in suite["questions"]:
        t0 = time.perf_counter()
        r = client.post("/v1/memories/search", json={
            "user_id": q["user_id"], "query": q["query"], "top_k": top_k,
        })
        dt = (time.perf_counter() - t0) * 1000
        data = r.json().get("data", [])

        checks = []
        passed = True
        for chk in q["judge"]["checks"]:
            ok = run_check(data, chk)
            checks.append({"type": chk["type"], "values": chk.get("values", []), "passed": ok})
            passed = passed and ok

        vals = target_values(q)
        rank = rank_of(data, vals) if vals else None
        q_records.append({
            "id": q["id"], "dimension": q["dimension"], "difficulty": q["difficulty"],
            "query": q["query"], "user_id": q["user_id"],
            "passed": passed, "n_returned": len(data), "rank": rank,
            "top1_score": round(data[0]["score"], 4) if data else None,
            "ms": round(dt, 2), "checks": checks,
            "returned": [m["content"] for m in data[:10]],
        })
        print(f"[{'PASS' if passed else 'FAIL'}] {q['id']:5s} {q['dimension']}  n={len(data):3d}  rank={rank}  {q['query'][:48]}")

    # Phase 3: aggregate.
    dims: dict[str, dict] = {}
    for q in q_records:
        d = dims.setdefault(q["dimension"], {"passed": 0, "total": 0})
        d["total"] += 1
        d["passed"] += int(q["passed"])

    total = sum(d["total"] for d in dims.values())
    total_passed = sum(d["passed"] for d in dims.values())
    add_lat = [w["ms"] for w in write_records if w["ok"]]
    search_lat = [q["ms"] for q in q_records]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": suite["meta"]["disclaimer"],
        "dimensions": {
            d: {"score": round(dims[d]["passed"] / dims[d]["total"] * 100, 1),
                "passed": dims[d]["passed"], "total": dims[d]["total"]}
            for d in dims
        },
        "overall": {"score": round(total_passed / total * 100, 1),
                    "passed": total_passed, "total": total},
        "performance": {
            "add_avg_ms": round(statistics.mean(add_lat), 2) if add_lat else 0.0,
            "add_p95_ms": round(sorted(add_lat)[int(len(add_lat) * 0.95) - 1], 2) if add_lat else 0.0,
            "search_avg_ms": round(statistics.mean(search_lat), 2) if search_lat else 0.0,
            "search_p95_ms": round(sorted(search_lat)[int(len(search_lat) * 0.95) - 1], 2) if search_lat else 0.0,
            "write_verify_hit": f"{sum(1 for w in write_verify if w['hit'])}/{len(write_verify)}",
        },
    }

    results = {"summary": summary, "write_records": write_records, "questions": q_records}
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 分维度参考分 ===")
    for d, v in dims.items():
        print(f"  {d} ({suite['meta']['dimensions'].get(d,'')}): {v['passed']}/{v['total']} = {round(v['passed']/v['total']*100,1)}")
    print(f"综合参考分: {total_passed}/{total} = {round(total_passed/total*100,1)}")
    print(f"Add 平均 {summary['performance']['add_avg_ms']}ms | Search 平均 {summary['performance']['search_avg_ms']}ms | 写入立即可检索 {summary['performance']['write_verify_hit']}")
    print(f"结果已写入 {OUT}")


if __name__ == "__main__":
    main()
