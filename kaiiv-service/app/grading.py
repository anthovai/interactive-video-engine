"""Marking. The only place a right answer is compared with a given one.

The caller sends the stored interaction — content and answers both — and what
the learner said. It gets back whether that was right, and what is worth
keeping as a record of it.

Two things come back rather than one because for several types the thing worth
storing is not the thing that arrived: typed text is stored folded, chosen
options are stored sorted. A report that cannot group "Bangkok", "bangkok "
and "  Bangkok" as the same answer is a report that says three people gave
three different answers.
"""
from __future__ import annotations


import re
from typing import Any

from . import types


class BadResponse(ValueError):
    """Something arrived that cannot be read as an answer to this question."""


def judge(kind: str, content: dict[str, Any], answers: list[Any],
          response: Any) -> tuple[Any, bool]:
    """Mark one response.

    :returns: (what to store, whether it was right)
    """
    if not types.is_graded(kind):
        # Seen, not answered. Recorded so a report can say the learner reached
        # it, and always correct because there was nothing to get wrong. It
        # stays out of the divisor — see timeline.score().
        return None, True

    if not answers:
        raise BadResponse(f"{kind} is marked but no answers were supplied")

    return _HANDLERS[kind](content, answers, response)


# --------------------------------------------------------------------------
# Folding
# --------------------------------------------------------------------------

def normalise(value: str) -> str:
    """Fold away the differences that are not the learner's answer.

    Surrounding and repeated whitespace goes, and English letter case goes.

    Thai tone marks and vowels stay. Treating ผู้ and ผู as the same word
    accepts a misspelling rather than forgiving a formatting difference, and
    an author who wants a variant accepted can add it as another spelling —
    the judgement belongs to the person who knows the subject, not to a
    normaliser that cannot tell a typo from a different word.
    """
    return re.sub(r"\s+", " ", str(value).strip()).lower()


# --------------------------------------------------------------------------
# One per graded type
# --------------------------------------------------------------------------

def _indexes(raw: Any, limit: int) -> list[int]:
    if not isinstance(raw, list):
        raise BadResponse("expected a list of indexes")

    seen: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int):
            raise BadResponse("indexes must be whole numbers")
        if value < 0 or value >= limit:
            raise BadResponse(f"index {value} is not on this question")
        if value not in seen:
            seen.append(value)
    return sorted(seen)


def _options(content, answers, response, single: bool):
    chosen = _indexes(response, len(content.get("options") or []))

    if single and len(chosen) != 1:
        raise BadResponse("this question takes exactly one answer")

    want = sorted(int(index) for index in answers)

    # All of them and nothing else. No partial credit: half a mark for half
    # the boxes reads as generous and is not. It invites an argument about the
    # scheme that neither the learner nor the teacher can settle from the
    # record, and it pays somebody who ticked everything except the hard one
    # the same as somebody who understood the question.
    return chosen, chosen == want


def _choice(content, answers, response):
    return _options(content, answers, response, single=True)


def _multichoice(content, answers, response):
    return _options(content, answers, response, single=False)


def _truefalse(content, answers, response):
    if not isinstance(response, bool):
        raise BadResponse("expected true or false")
    return response, response == bool(answers[0])


def _shorttext(content, answers, response):
    if not isinstance(response, str):
        raise BadResponse("expected typed text")
    typed = normalise(response)
    return typed, typed in {normalise(word) for word in answers}


def _gaps(content, answers, response):
    """Gaps in a sentence, whether typed or dragged.

    Both arrive as gap index to word, so they are marked the same way. The
    difference between them is entirely on screen, and keeping it there means
    a teacher can switch an interaction from typing to dragging without the
    marking changing under the learners who already answered.

    All gaps or none, for the same reason the several-answers case above
    refuses partial credit.
    """
    # A list is accepted as well as a mapping, position meaning gap. Not for
    # convenience: PHP's json_decode($x, true) turns {"0": "a", "1": "b"} into
    # an array with integer keys, and re-encoding that produces ["a", "b"].
    # Our own Moodle client did exactly that, and every gap answer came back
    # "could not be marked". Any caller that round-trips JSON through a
    # language with that habit would hit the same, and the answer the learner
    # gave is the same answer either way.
    if isinstance(response, list):
        response = {str(index): word for index, word in enumerate(response)}

    if not isinstance(response, dict):
        raise BadResponse("expected a mapping of gap to word")

    stored: dict[str, str] = {}
    correct = True

    for gap, accepted in enumerate(answers):
        # JSON object keys are strings whichever end wrote them, and a caller
        # that sends integers through a language where they stay integers
        # should not get a different mark for it.
        said = normalise(str(response.get(str(gap), response.get(gap, ""))))
        stored[str(gap)] = said
        if said not in {normalise(word) for word in accepted}:
            correct = False

    return stored, correct


def _marktheword(content, answers, response):
    """Words picked out of a passage.

    Marking something that should not be marked costs the same as missing
    something that should be. Counting only the hits would let a learner mark
    every word and score full marks, which is not a reading task.
    """
    marked = _indexes(response, len(content.get("words") or []))
    want = sorted(int(index) for index in answers)
    return marked, marked == want


_HANDLERS = {
    "choice": _choice,
    "multichoice": _multichoice,
    "truefalse": _truefalse,
    "shorttext": _shorttext,
    "blanks": _gaps,
    "dragtext": _gaps,
    "marktheword": _marktheword,
}
