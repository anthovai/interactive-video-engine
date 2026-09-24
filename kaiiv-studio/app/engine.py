"""The engine, from the studio's side.

Every call goes from here — the server — and never from a page: the page has
no key, and a page that could reach the engine could ask it to mark things.

Refusals come back as the engine named them ({ok: false, error, detail}), so
"no option is marked correct" reaches the teacher who can fix it. A failure to
connect is named here, because an engine that cannot be reached cannot say so.
"""
from __future__ import annotations

from typing import Any

import httpx

from . import config

_client: httpx.Client | None = None
_key = ""


def configure(key: str, client: httpx.Client | None = None) -> None:
    """Set the key, and — for the tests — the client to call the engine with."""
    global _client, _key
    _key = key
    _client = client or httpx.Client(base_url=config.ENGINE_URL, timeout=config.ENGINE_TIMEOUT)


def _read(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 401:
        return {"ok": False, "error": "bad_key", "detail": "the engine refused our key"}
    try:
        body = response.json()
    except ValueError:
        return {"ok": False, "error": "malformed", "detail": response.text[:200]}
    if not isinstance(body, dict):
        return {"ok": False, "error": "malformed", "detail": "not an object"}
    return body


def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = _client.post(path, json={"contract": config.CONTRACT, **payload},
                                headers={"X-Proctor-Key": _key})
    except httpx.HTTPError as error:
        return {"ok": False, "error": "unreachable", "detail": str(error)}
    return _read(response)


def get(path: str) -> dict[str, Any]:
    try:
        response = _client.get(path, headers={"X-Proctor-Key": _key})
    except httpx.HTTPError as error:
        return {"ok": False, "error": "unreachable", "detail": str(error)}
    return _read(response)


def author(kind: str, authored: dict[str, Any]) -> dict[str, Any]:
    return post("/author", {"type": kind, "authored": authored})


def timeline(interactions: list, seen: dict, rules: dict) -> dict[str, Any]:
    return post("/timeline", {"interactions": interactions, "seen": _plain(seen), "rules": rules})


def judge(interaction: dict, response: Any, attempts: int, answered_correctly: bool,
          rules: dict) -> dict[str, Any]:
    return post("/judge", {
        "type": interaction["type"],
        "content": interaction["content"],
        "answers": interaction["answers"],
        "feedback": interaction["feedback"],
        "response": response,
        "attempts": attempts,
        "answered_correctly": answered_correctly,
        "rules": rules,
    })


def score(interactions: list, seen: dict) -> dict[str, Any]:
    return post("/score", {"interactions": interactions, "seen": _plain(seen)})


def types() -> dict[str, Any]:
    return get("/types")


def health() -> dict[str, Any]:
    try:
        return _read(_client.get("/health"))
    except httpx.HTTPError as error:
        return {"ok": False, "error": "unreachable", "detail": str(error)}


def _plain(seen: dict) -> dict:
    """The engine's shape of `seen`, without the studio's own bookkeeping."""
    return {key: {"response": value["response"], "correct": value["correct"],
                  "attempts": value["attempts"]} for key, value in seen.items()}
