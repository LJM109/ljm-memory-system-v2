"""Pydantic models for the AML Add/Search API contract.

The request models use ``extra="allow"`` deliberately: the AML evaluator may
send fields beyond the documented core (historically ``async_mode``, and the
``request_id`` echo field). Rejecting unknown fields with HTTP 422 is flagged
by the platform as a contract mismatch, so we accept-and-ignore anything extra
instead of forbidding it.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AddMessage(BaseModel):
    """A single ordered message inside an Add request."""

    model_config = ConfigDict(extra="allow")

    role: str = "user"
    content: str = ""
    # Unix milliseconds when available (per the AML contract).
    timestamp: Optional[int] = None


class AddRequest(BaseModel):
    """POST /v1/memories/add request body.

    ``session_id`` accepts ``session_id`` / ``conversation_id`` / ``session``
    aliases because the exact conversation-identifier key is not stable across
    pipeline versions; ``user_id`` is the retrieval-isolation scope.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    user_id: str
    session_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("session_id", "conversation_id", "session"),
    )
    request_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("request_id", "write_id"),
    )
    messages: list[AddMessage] = Field(default_factory=list)


class AddResponse(BaseModel):
    """Add must be synchronous: return 200 only after the messages are stored
    and searchable, echoing the write request id."""

    request_id: str


class SearchRequest(BaseModel):
    """POST /v1/memories/search request body."""

    model_config = ConfigDict(extra="allow")

    query: str
    user_id: str
    top_k: int = Field(default=10, ge=1, le=200)
    # Present only for choice questions; omitted otherwise.
    options: Optional[list[str]] = None


class MemoryResult(BaseModel):
    """A single returned memory evidence item."""

    id: str
    content: str
    score: float
    created_at: str


class SearchResponse(BaseModel):
    """Ordered (most -> least relevant) array of memory evidence. Empty array
    when no relevant memory is available (epistemic-safety requirement)."""

    data: list[MemoryResult]
