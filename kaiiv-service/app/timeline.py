"""The timeline: what is on it, what blocks playback, and what it is worth.

Everything a player receives is built by for_player(). There is no second
path, which is the only reason a claim about what a browser has can be checked
by reading one function.

The engine holds nothing. A caller sends the interactions it has stored and
the answers it has recorded, and gets back a payload. That is not an
efficiency choice — it is what lets a second host system, with its own
database and its own idea of what a course is, use the same engine without
either of them growing a second copy of the other's records.
"""
from __future__ import annotations

import random
from typing import Any

from . import contract, grading, types


def for_player(interactions: list[dict[str, Any]],
               seen: dict[str, dict[str, Any]],
               rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the payload a player may receive.

    :param interactions: stored rows, answers included
    :param seen: interaction id to what this learner has already done
    :param rules: allowreview and maxattempts, from the activity
    """
    contract.limit_interactions(interactions)

    out: list[dict[str, Any]] = []

    for row in interactions:
        kind = str(row.get("type", ""))

        if not types.known(kind):
            # Skipped rather than passed through. An unknown type is exactly
            # the case where "what of this is secret" has no answer, and a
            # player missing an interaction is a visible bug while one
            # shipping an unfiltered row is not.
            continue

        content = row.get("content") or {}
        answers = row.get("answers") or []

        public = types.public_content(kind, content)

        if kind == "dragtext" and isinstance(public.get("bank"), list):
            # Shuffled again on the way out, so that two learners looking at
            # each other's screens are not looking at the same arrangement,
            # and so that repeating the activity is not a memorised sequence.
            public["bank"] = list(public["bank"])
            random.shuffle(public["bank"])

        item: dict[str, Any] = {
            "id": row.get("id"),
            "type": kind,
            "start": float(row.get("start", 0)),
            "end": float(row.get("end", 0)),
            "display": row.get("display", "poster"),
            "pauses": bool(row.get("pauses", types.pauses(kind))),
            "x": float(row.get("x", 20)),
            "y": float(row.get("y", 20)),
            "width": float(row.get("width", 60)),
            "height": float(row.get("height", 40)),
            "label": row.get("label", ""),
            "graded": types.is_graded(kind),
            "content": public,
        }

        record = seen.get(str(row.get("id")))
        if record:
            attempts = int(record.get("attempts", 1))
            correct = bool(record.get("correct", False))
            revealed = is_revealed(rules, correct, attempts)

            item.update({
                "answered": True,
                "correct": correct,
                "attempts": attempts,
                "response": record.get("response"),
                "revealed": revealed,
            })
            if revealed:
                item["answers"] = answers
                item["feedback"] = row.get("feedback", "")
        else:
            item.update({"answered": False, "attempts": 0, "revealed": False})

        # Checked after the item is finished rather than on the content alone,
        # so that a field added to the item above is covered too. The released
        # case is skipped: the learner has earned the answer by then, and
        # checking it would fail on the very payload the rule is designed to
        # allow.
        if not item.get("revealed"):
            contract.assert_no_leak(kind, answers, item)

        out.append(item)

    out.sort(key=lambda entry: (entry["start"], entry.get("id") or 0))
    return out


def is_revealed(rules: dict[str, Any], correct: bool, attempts: int) -> bool:
    """Whether the learner has been shown the answer to this one.

    A wrong answer with another attempt still to come is the one case where
    the answer and the explanation both stay hidden. Showing them and then
    offering "try again" makes the second attempt free, which is not a second
    attempt at anything — it is a button that awards a mark.

    Worked out rather than remembered. A stored flag outlives the rule that
    produced it, and nothing afterwards can tell whether it was set under the
    current rule or an old one. The cost is real and worth stating: an author
    who raises the attempt limit part way through will hide an explanation
    somebody had already read. That is visible and recoverable.
    """
    if correct:
        return True
    if not rules.get("allowreview", True):
        # No retry was ever on offer, so nothing is being made free.
        return True
    limit = int(rules.get("maxattempts", 0) or 0)
    return limit > 0 and attempts >= limit


def may_retry(rules: dict[str, Any], attempts: int) -> bool:
    if not rules.get("allowreview", True):
        return False
    limit = int(rules.get("maxattempts", 0) or 0)
    return limit == 0 or attempts < limit


def due(items: list[dict[str, Any]], at: float) -> list[dict[str, Any]]:
    """Which interactions are standing in the way at this point in the video.

    The first way to write this is to watch for the playhead crossing a
    timestamp, and it is wrong: the learner drags the seekbar past it and
    nothing ever crosses anything.

    An interaction is due when the playhead is at or past its point and it has
    not been answered. Written that way, ordinary playback, dragging the
    seekbar, and coming back tomorrow to a half-finished video are all the same
    case, and there is no fourth case left to forget.
    """
    return [
        item for item in items
        if item.get("pauses") and not item.get("answered")
        and item["start"] <= at
    ]


def score(interactions: list[dict[str, Any]],
          seen: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Correct answers over interactions that can be answered.

    Not over interactions attempted, which would give full marks to somebody
    who answered one question and stopped. The unmarked kinds are in neither
    figure: reading a caption is not a question, and counting it would push
    everybody's percentage up by however many captions an author happened to
    add.
    """
    total = 0
    right = 0

    for row in interactions:
        kind = str(row.get("type", ""))
        if not types.known(kind) or not types.is_graded(kind):
            continue
        total += 1
        record = seen.get(str(row.get("id")))
        if record and record.get("correct"):
            right += 1

    return {
        "correct": right,
        "total": total,
        "fraction": (right / total) if total else 0.0,
    }
