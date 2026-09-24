"""Marking, including the cases where being generous would be wrong."""
from __future__ import annotations

import pytest

from app import authoring, grading


def mark(kind: str, authored: dict, response):
    content, answers = authoring.split(kind, authored)
    return grading.judge(kind, content, answers, response)


# --------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------

CHOICE = {
    "text": "Which is a river?",
    "options": [
        {"text": "Chao Phraya", "correct": True},
        {"text": "Everest", "correct": False},
        {"text": "Sahara", "correct": False},
    ],
}


def test_the_right_option_is_right():
    _, correct = mark("choice", CHOICE, [0])
    assert correct


def test_a_single_answer_question_refuses_two_answers():
    with pytest.raises(grading.BadResponse):
        mark("choice", CHOICE, [0, 1])


def test_an_option_that_is_not_on_the_question_is_refused():
    with pytest.raises(grading.BadResponse):
        mark("choice", CHOICE, [7])


MULTI = {
    "text": "Which are rivers?",
    "options": [
        {"text": "Chao Phraya", "correct": True},
        {"text": "Mekong", "correct": True},
        {"text": "Everest", "correct": False},
    ],
}


def test_half_the_boxes_is_not_half_a_mark():
    _, correct = mark("multichoice", MULTI, [0])
    assert not correct


def test_ticking_everything_is_not_a_strategy():
    _, correct = mark("multichoice", MULTI, [0, 1, 2])
    assert not correct


def test_order_of_ticking_does_not_matter():
    stored, correct = mark("multichoice", MULTI, [1, 0])
    assert correct
    assert stored == [0, 1]


# --------------------------------------------------------------------------
# Typed text
# --------------------------------------------------------------------------

TYPED = {"text": "Capital of France?", "accept": ["Paris", "paris city"]}


def test_case_and_spacing_are_forgiven():
    _, correct = mark("shorttext", TYPED, "  PARIS  ")
    assert correct


def test_a_second_accepted_spelling_works():
    _, correct = mark("shorttext", TYPED, "Paris   City")
    assert correct


def test_thai_vowels_are_not_stripped():
    """ผู้ and ผู are different words, and treating them as one accepts a
    misspelling rather than forgiving a formatting difference."""
    authored = {"text": "ใครสอน", "accept": ["ผู้สอน"]}
    _, correct = mark("shorttext", authored, "ผูสอน")
    assert not correct


# --------------------------------------------------------------------------
# Gaps
# --------------------------------------------------------------------------

GAPS = {"text": "Fill in", "lines": ["The capital of *France/francia* is *Paris*"]}


def test_all_gaps_right_is_right():
    _, correct = mark("blanks", GAPS, {"0": "france", "1": "Paris"})
    assert correct


def test_one_gap_wrong_is_wrong():
    _, correct = mark("blanks", GAPS, {"0": "France", "1": "Lyon"})
    assert not correct


def test_a_missing_gap_is_wrong_not_an_error():
    """A learner who submits with a box empty gets a mark, not a stack trace."""
    _, correct = mark("blanks", GAPS, {"0": "France"})
    assert not correct


def test_integer_keys_are_read_the_same_as_string_keys():
    _, correct = mark("blanks", GAPS, {0: "France", 1: "Paris"})
    assert correct


def test_a_list_of_gaps_is_read_by_position():
    """What PHP sends after json_decode($x, true) and json_encode again.

    Found in a real browser: every gap answer from Moodle came back "could
    not be marked", because {"0": ..., "1": ...} had become [..., ...] on the
    way through.
    """
    stored, correct = mark("blanks", GAPS, ["France", "Paris"])
    assert correct
    assert stored == {"0": "france", "1": "paris"}


# --------------------------------------------------------------------------
# Marked words
# --------------------------------------------------------------------------

PASSAGE = {"text": "Find the animals", "passage": "the *cat* sat on the *mat*"}


def test_the_right_words_are_right():
    _, correct = mark("marktheword", PASSAGE, [1, 5])
    assert correct


def test_marking_every_word_is_not_full_marks():
    _, correct = mark("marktheword", PASSAGE, [0, 1, 2, 3, 4, 5])
    assert not correct


# --------------------------------------------------------------------------
# Unmarked kinds
# --------------------------------------------------------------------------

def test_a_caption_is_always_correct_and_stores_nothing():
    stored, correct = grading.judge("label", {"text": "hello"}, [], None)
    assert correct
    assert stored is None


# --------------------------------------------------------------------------
# Authoring refusals
# --------------------------------------------------------------------------

def test_a_question_with_no_correct_option_is_refused_at_authoring():
    with pytest.raises(authoring.BadAuthoring):
        authoring.split("choice", {
            "text": "?",
            "options": [{"text": "a"}, {"text": "b"}],
        })


def test_a_gap_exercise_with_no_gaps_is_refused_at_authoring():
    with pytest.raises(authoring.BadAuthoring):
        authoring.split("blanks", {"text": "?", "lines": ["nothing to fill in"]})
