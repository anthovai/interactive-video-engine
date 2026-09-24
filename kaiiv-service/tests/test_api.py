"""The API as a caller meets it.

The other suites test the engine. These test the promises a host system
integrates against: that a call without the key is refused, that a refusal is
named rather than merely a status code, and that an answer round-trips from
/author through /timeline and /judge without the host ever having to know how
any of it is stored.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config, main

KEY = "test-key"
HEAD = {"X-Proctor-Key": KEY}


@pytest.fixture(autouse=True)
def keyed(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", KEY)
    yield


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_needs_no_key(client):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["service"] == "kaiiv"
    assert body["keyed"] is True


def test_everything_else_needs_the_key(client):
    for path in ["/types", "/author", "/timeline", "/judge", "/due", "/score"]:
        response = client.request(
            "GET" if path == "/types" else "POST", path, json={})
        assert response.status_code == 401, path


def test_a_wrong_contract_version_is_refused_by_name(client):
    response = client.post("/author", headers=HEAD, json={
        "contract": "0.9", "type": "shorttext", "authored": {},
    })
    assert response.status_code == 422
    assert response.json()["error"] == "bad_request"


def test_an_unknown_type_is_refused_by_name(client):
    response = client.post("/author", headers=HEAD, json={
        "contract": "1.0", "type": "interpretive_dance", "authored": {},
    })
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_type"


def test_a_question_round_trips(client):
    """Author it, show it, answer it wrong, answer it right.

    Written as one test rather than four because the thing worth checking is
    that the halves fit together: a host stores what /author returned and
    hands it straight back, and nothing in between needs to understand it.
    """
    authored = client.post("/author", headers=HEAD, json={
        "contract": "1.0",
        "type": "shorttext",
        "authored": {"text": "Capital of France?", "accept": ["Paris"]},
    }).json()
    assert authored["ok"] and authored["graded"]

    row = {
        "id": 7, "type": "shorttext", "start": 12.0, "end": 12.0,
        "pauses": True,
        "content": authored["content"],
        "answers": authored["answers"],
        "feedback": "It is on the Seine.",
    }
    rules = {"allowreview": True, "maxattempts": 2}

    # Nothing answered yet: the answer is not in what the player receives.
    first = client.post("/timeline", headers=HEAD, json={
        "contract": "1.0", "interactions": [row], "seen": {}, "rules": rules,
    }).json()
    assert first["ok"]
    assert "paris" not in str(first).lower()

    # And it is standing in the way at 20 seconds.
    blocked = client.post("/due", headers=HEAD, json={
        "contract": "1.0", "items": first["items"], "at": 20.0,
    }).json()
    assert blocked["blocked"] is True

    # Wrong, with a retry left: told it is wrong and nothing else.
    wrong = client.post("/judge", headers=HEAD, json={
        "contract": "1.0", "type": "shorttext",
        "content": row["content"], "answers": row["answers"],
        "feedback": row["feedback"], "response": "Lyon",
        "attempts": 0, "rules": rules,
    }).json()
    assert wrong["correct"] is False
    assert wrong["may_retry"] is True
    assert wrong["revealed"] is False
    assert wrong["answers"] == []
    assert wrong["feedback"] == ""

    # Right: the answer and the explanation arrive together.
    right = client.post("/judge", headers=HEAD, json={
        "contract": "1.0", "type": "shorttext",
        "content": row["content"], "answers": row["answers"],
        "feedback": row["feedback"], "response": "  paris ",
        "attempts": 1, "rules": rules,
    }).json()
    assert right["correct"] is True
    assert right["revealed"] is True
    assert right["answers"] == ["Paris"]
    assert "Seine" in right["feedback"]
    assert right["store"] == "paris"

    # Now it no longer blocks, and the score reflects it.
    seen = {"7": {"correct": True, "attempts": 2, "response": right["store"]}}
    after = client.post("/timeline", headers=HEAD, json={
        "contract": "1.0", "interactions": [row], "seen": seen, "rules": rules,
    }).json()
    assert client.post("/due", headers=HEAD, json={
        "contract": "1.0", "items": after["items"], "at": 20.0,
    }).json()["blocked"] is False

    score = client.post("/score", headers=HEAD, json={
        "contract": "1.0", "interactions": [row], "seen": seen,
    }).json()
    assert score == {"ok": True, "correct": 1, "total": 1, "fraction": 1.0}


def test_an_answer_past_the_last_attempt_is_not_marked(client):
    """The bypass this closes: wrong once on a one-attempt question, then the
    right answer posted straight at the caller's endpoint.

    The caller's record reads the latest response as the word on that
    question, so a second answer that got marked would replace the first —
    after the answer had already been revealed to the learner.
    """
    authored = client.post("/author", headers=HEAD, json={
        "contract": "1.0", "type": "truefalse",
        "authored": {"text": "Water is wet.", "correct": True},
    }).json()
    judged = lambda attempts, response, rules, **extra: client.post(
        "/judge", headers=HEAD, json={
            "contract": "1.0", "type": "truefalse",
            "content": authored["content"], "answers": authored["answers"],
            "response": response, "attempts": attempts, "rules": rules,
            **extra,
        })

    one_go = {"allowreview": True, "maxattempts": 1}
    first = judged(0, False, one_go).json()
    assert first["correct"] is False and first["may_retry"] is False
    assert first["revealed"] is True

    again = judged(1, True, one_go)
    assert again.status_code == 409
    assert again.json()["error"] == "no_attempts_left"
    assert "correct" not in again.json()

    # No retries at all, whatever the limit says.
    no_review = judged(1, True, {"allowreview": False, "maxattempts": 0})
    assert no_review.json()["error"] == "no_attempts_left"

    # Unlimited retries are unlimited...
    unlimited = {"allowreview": True, "maxattempts": 0}
    assert judged(5, True, unlimited).json()["correct"] is True

    # ...until one of them is right.
    done = judged(2, True, unlimited, answered_correctly=True)
    assert done.status_code == 409
    assert done.json()["error"] == "already_correct"


def test_a_caption_is_not_in_the_divisor(client):
    """A video with one question and three captions is marked out of one."""
    rows = [
        {"id": 1, "type": "choice", "start": 1, "end": 1,
         "content": {"text": "?", "options": ["a", "b"]}, "answers": [0]},
        {"id": 2, "type": "label", "start": 2, "end": 4,
         "content": {"text": "note"}, "answers": []},
    ]
    seen = {"1": {"correct": True, "attempts": 1, "response": [0]}}

    score = client.post("/score", headers=HEAD, json={
        "contract": "1.0", "interactions": rows, "seen": seen,
    }).json()
    assert score["total"] == 1
    assert score["fraction"] == 1.0


def test_the_types_catalogue_is_askable(client):
    body = client.get("/types", headers=HEAD).json()
    names = {entry["type"] for entry in body["types"]}
    assert {"choice", "blanks", "dragtext", "label"} <= names
    assert all("fields" in entry for entry in body["types"])
