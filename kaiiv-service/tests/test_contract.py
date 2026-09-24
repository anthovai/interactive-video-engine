"""The tests that exist to be shown to a customer.

Everything else in this suite checks that the engine is right. These check
that it cannot be wrong in the one way that matters: a learner reading the
answers out of the page they are being assessed on.

They test the finished payload, not the function that builds it. A test that
asserts "for_player does not include the answers key" passes forever while
somebody adds a "solution" key beside it. These search the JSON a browser
would actually receive for the words a learner would actually be looking for.
"""
from __future__ import annotations

import json

import pytest

from app import authoring, contract, timeline, types

RULES = {"allowreview": True, "maxattempts": 0}


def build(kind: str, authored: dict) -> dict:
    content, answers = authoring.split(kind, authored)
    return {
        "id": 1, "type": kind, "start": 5.0, "end": 5.0,
        "display": "poster", "pauses": True,
        "content": content, "answers": answers,
        "feedback": "because that is where the river is",
    }


def rendered(row: dict, seen: dict | None = None) -> str:
    items = timeline.for_player([row], seen or {}, RULES)
    return json.dumps(items, ensure_ascii=False).lower()


def test_typed_answer_is_not_in_the_payload():
    row = build("shorttext", {"text": "Capital of France?", "accept": ["Paris"]})
    assert "paris" not in rendered(row)


def test_gap_answer_is_not_in_the_payload():
    row = build("blanks", {
        "text": "Fill in",
        "lines": ["The capital of *France* is Paris"],
    })
    out = rendered(row)
    assert "france" not in out
    # And the gap is still there to be filled, or the question has become
    # unanswerable rather than secure.
    assert "[[0]]" in out


def test_marked_words_are_not_in_the_payload():
    row = build("marktheword", {
        "text": "Find the animals",
        "passage": "the *cat* sat on the *mat*",
    })
    items = timeline.for_player([row], {}, RULES)
    words = items[0]["content"]["words"]

    # The passage is all there — every word, none of them flagged.
    assert words == ["the", "cat", "sat", "on", "the", "mat"]
    assert "*" not in json.dumps(items)
    assert "answers" not in items[0]


def test_thai_answer_is_not_in_the_payload():
    row = build("shorttext", {
        "text": "เมืองหลวงของไทยคือ",
        "accept": ["กรุงเทพมหานคร"],
    })
    assert "กรุงเทพมหานคร" not in rendered(row)


def test_feedback_is_withheld_with_the_answer():
    row = build("shorttext", {"text": "Capital of France?", "accept": ["Paris"]})
    seen = {"1": {"correct": False, "attempts": 1, "response": "lyon"}}
    assert "river" not in rendered(row, seen)


def test_both_are_released_once_the_learner_is_right():
    row = build("shorttext", {"text": "Capital of France?", "accept": ["Paris"]})
    seen = {"1": {"correct": True, "attempts": 1, "response": "paris"}}

    items = timeline.for_player([row], seen, RULES)
    assert items[0]["revealed"] is True
    assert items[0]["answers"] == ["Paris"]
    assert "river" in items[0]["feedback"]


def test_both_are_released_when_no_attempts_remain():
    row = build("shorttext", {"text": "Capital of France?", "accept": ["Paris"]})
    seen = {"1": {"correct": False, "attempts": 2, "response": "lyon"}}

    items = timeline.for_player([row], seen, {"allowreview": True, "maxattempts": 2})
    assert items[0]["revealed"] is True
    assert items[0]["answers"] == ["Paris"]


def test_dragtext_sends_the_words_and_withholds_the_arrangement():
    """The one declared exception, pinned down so it stays the only one."""
    row = build("dragtext", {
        "text": "Drag them in",
        "lines": ["The capital of *France* is *Paris*"],
    })
    items = timeline.for_player([row], {}, RULES)
    bank = items[0]["content"]["bank"]

    # The words have to be there — there is nothing to drag otherwise.
    assert sorted(bank) == ["France", "Paris"]
    # What is not there is which gap each one belongs to.
    assert "answers" not in items[0]


def test_a_leak_is_refused_rather_than_sent():
    """The check that survives a refactor.

    Simulating the mistake it exists to catch: an extra key on the content
    carrying the answer under a name the whitelist never heard of. The
    whitelist is what should stop this, so the whitelist is bypassed here to
    prove the second mechanism works on its own.
    """
    row = build("shorttext", {"text": "Capital of France?", "accept": ["Paris"]})

    with pytest.raises(contract.ContractViolation):
        contract.assert_no_leak("shorttext", row["answers"],
                                {"content": {"hint": "it is Paris"}})


def test_an_unknown_type_is_dropped_not_forwarded():
    row = dict(build("shorttext", {"text": "q", "accept": ["a"]}), type="mystery")
    assert timeline.for_player([row], {}, RULES) == []


def test_the_registry_and_the_handlers_agree():
    """A type that is graded but that nothing knows how to mark is a 500
    waiting for the first learner to reach it."""
    from app import grading

    for name in types.TYPES:
        if types.is_graded(name):
            assert name in grading._HANDLERS, name
            assert name in authoring._HANDLERS, name
