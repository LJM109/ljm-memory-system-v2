"""Structured extraction: entities (Cognee-style) + facts (Mem0-style).

Deterministic, dependency-light extraction runs on every Add. It pulls out
(i) entity strings for the graph index and (ii) fact strings for importance
scoring and conflict detection. An optional OpenAI-compatible LLM pass
(gpt-4o-mini per AML academic-board rules) can enrich this when configured;
it is never required, and failures silently fall back to the deterministic
path so Add stays synchronous and fast.
"""
from __future__ import annotations

import re
from typing import Optional

from ..config import settings

# --- entity patterns -------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://[^\s]+")
_DATE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:st|nd|rd|th)?(?:,? \d{4})?\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\b(?:\$|€|£|¥)?\d[\d,.]*(?:\s?(?:dollars?|euros?|pounds?|yuan|years?|days?|months?|weeks?|kg|km|miles?|%))?\b")
_PROPER = re.compile(r"\b(?:[A-Z][a-z]{1,20}\s+){1,3}[A-Z][a-z]{1,20}\b")
_SINGLE_PROPER = re.compile(r"\b[A-Z][a-z]{2,20}\b")

_STOP_PROPER = {
    "The", "This", "That", "There", "They", "Then", "When", "What", "Where",
    "Which", "While", "With", "Would", "Could", "Should", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January",
    "February", "March", "April", "June", "July", "August", "September",
    "October", "November", "December", "Yes", "No", "Ok", "Okay", "Hi",
    "Hello", "Thanks", "Thank", "Please",
}

# --- fact patterns (subject = user, predicate = relation) -----------------
_PREFERENCE_WORDS = r"(?:like|love|prefer|enjoy|favorite|favourite|hate|dislike|can't stand|cannot stand|don't like|do not like)"
_IDENTITY_WORDS = r"(?:am|'m|name is|live in|lives in|work at|works at|work for|studied|study|born in|from|speak|my)"
_RULE_WORDS = r"(?:always|never|must|mustn't|should|shouldn't|have to|need to|remember to|don't forget|make sure|no longer)"

_PREFERENCE_RE = re.compile(
    rf"\b(?:I|i|we|my|our)\s+(?:{_PREFERENCE_WORDS})\s+([^.!?]+)", re.IGNORECASE
)
_IDENTITY_RE = re.compile(
    rf"\b(?:I|i)\s+(?:{_IDENTITY_WORDS})\s+([^.!?]+)", re.IGNORECASE
)
_RULE_RE = re.compile(rf"\b(?:{_RULE_WORDS})\s+([^.!?]+)", re.IGNORECASE)

# Name statements for identity conflict detection (single-value, mutually
# exclusive). Covers "My name is X", "Call me X", "You can call me X",
# "I'm called X", "I am called X".
_NAME_RE = re.compile(
    r"\b(?:my\s+name\s+is|call\s+me|you\s+can\s+call\s+me|i'?m\s+called|i\s+am\s+called)"
    r"\s+([A-Za-z][A-Za-z .'-]{1,40})",
    re.IGNORECASE,
)
# Bare "I'm Alice" / "I am Alice": a single capitalised token with no leading
# determiner, so "I am a software engineer" is not misread as a name. The
# (?i:...) scope makes only the subject case-insensitive; the name token still
# requires a leading capital (so "I am hungry" is not treated as a name).
_BARE_NAME_RE = re.compile(r"\b(?i:i'?m|i\s+am)\s+([A-Z][a-z]{1,30})(?=[\s.,!?]|$)")


def extract_entities(text: str) -> list[tuple[str, str]]:
    """Return [(entity_name, type)] for a chunk's raw text."""
    found: dict[str, str] = {}

    def add(name: str, etype: str) -> None:
        name = name.strip().strip(".,!?;:'\"()[]{}")
        if len(name) < 2 or len(name) > 64:
            return
        found.setdefault(name.lower(), (name, etype))

    for match in _EMAIL.findall(text):
        add(match, "email")
    for match in _URL.findall(text):
        add(match, "url")
    for match in _DATE.findall(text):
        add(match, "date")
    for match in _PROPER.findall(text):
        add(match, "entity")
    for match in _SINGLE_PROPER.findall(text):
        if match in _STOP_PROPER:
            continue
        add(match, "entity")
    return list(found.values())


def extract_facts(text: str) -> list[str]:
    """Return extracted fact strings (preferences, identity, rules, names)."""
    facts: list[str] = []
    for match in _PREFERENCE_RE.finditer(text):
        fact = match.group(0).strip().strip(".,; ")
        if 3 < len(fact) < 200:
            facts.append(f"preference: {fact}")
    for match in _IDENTITY_RE.finditer(text):
        fact = match.group(0).strip().strip(".,; ")
        if 3 < len(fact) < 200:
            facts.append(f"identity: {fact}")
    for match in _RULE_RE.finditer(text):
        fact = match.group(0).strip().strip(".,; ")
        if 3 < len(fact) < 200:
            facts.append(f"rule: {fact}")
    # Name statements: extracted separately so identity conflict detection can
    # key on a stable "name:" prefix and supersede the previous name.
    for match in _NAME_RE.finditer(text):
        name = match.group(1).strip().strip(".,; ")
        if 1 < len(name) < 60:
            facts.append(f"name: {name}")
    for match in _BARE_NAME_RE.finditer(text):
        name = match.group(1).strip().strip(".,; ")
        if 1 < len(name) < 60:
            facts.append(f"name: {name}")
    return facts


def extract(raw_texts: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Extract entities and facts from a chunk's raw message texts."""
    entities: dict[str, str] = {}
    facts: list[str] = []
    joined = "\n".join(raw_texts)
    for name, etype in extract_entities(joined):
        entities.setdefault(name.lower(), (name, etype))
    facts.extend(extract_facts(joined))
    return list(entities.values()), facts


# --- optional LLM enrichment (gpt-4o-mini, academic-board compliant) -------
_LLM_PROMPT = (
    "Extract from the following conversation messages: (1) named entities "
    "(people, places, organizations, dates) and (2) user facts/preferences/"
    "rules/constraints. Return strict JSON: {\"entities\": [\"...\"], "
    "\"facts\": [\"...\"]}. Do not invent anything not stated.\n\n"
    "Messages:\n{text}"
)


def extract_with_llm(raw_texts: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Deterministic extraction + optional LLM enrichment (best-effort)."""
    entities, facts = extract(raw_texts)
    if not (settings.llm_extract and settings.llm_base_url and settings.llm_api_key):
        return entities, facts
    try:
        import httpx

        text = "\n".join(raw_texts)[:6000]
        resp = httpx.post(
            settings.llm_base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": "You return only JSON."},
                    {"role": "user", "content": _LLM_PROMPT.format(text=text)},
                ],
                "temperature": 0,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = _parse_json_loose(content)
        for name in data.get("entities", []):
            if isinstance(name, str) and name.strip():
                entities.append((name.strip(), "entity"))
        for fact in data.get("facts", []):
            if isinstance(fact, str) and fact.strip():
                facts.append(fact.strip())
    except Exception:
        pass
    return entities, facts


def _parse_json_loose(text: str) -> dict:
    import json

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
        return {}
