"""FastAPI application exposing the AML Add/Search contract.

Endpoints:
  GET  /health                -> {"status": "ok"}
  POST /v1/memories/add       -> synchronous write, echoes request_id
  POST /v1/memories/search    -> ordered memory evidence (or empty array)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .schemas import AddRequest, AddResponse, MemoryResult, SearchRequest, SearchResponse
from .system import MemorySystem

_system: MemorySystem | None = None


def get_system() -> MemorySystem:
    global _system
    if _system is None:
        _system = MemorySystem()
    return _system


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm the embedding model at startup so the first request is fast.
    try:
        get_system().embedder.embed(["warmup"])
    except Exception:
        pass
    yield


app = FastAPI(title="AML Memory System", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return get_system().health()


@app.post("/v1/memories/add", response_model=AddResponse)
def add_memories(request: AddRequest) -> AddResponse:
    request_id = get_system().add(
        request.user_id,
        request.session_id,
        request.request_id,
        request.messages,
    )
    return AddResponse(request_id=request_id)


@app.post("/v1/memories/search", response_model=SearchResponse)
def search_memories(request: SearchRequest) -> SearchResponse:
    results = get_system().search(
        request.query, request.user_id, request.top_k, request.options
    )
    return SearchResponse(data=[MemoryResult(**item) for item in results])
