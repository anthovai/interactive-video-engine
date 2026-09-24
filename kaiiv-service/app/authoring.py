"""Turning what a teacher typed into what may be stored and what may be sent.

Authors write answers inline — asterisks around the word that goes in the gap,
a tick against the option that is right — because that is how the question
reads while you are writing it, and because anyone who has used H5P already
types it that way.

The split has to happen somewhere. Doing it in the host system means every
host that integrates repeats it, and repeats the chance of storing the
authored form by mistake; a single stored string containing `*France*` is a
leak that no amount of care at the sending end can undo, because by then the
answer is part of the text.

So it happens here, at the moment content is created, and the authored form
never reaches storage at all. What comes back is two things the caller stores
in two columns: `content`, which may be shown, and `answers`, which may not.
"""
from __future__ import annotations

import random
import re
from typing import Any

from . import types

# `*France*`, or `*France/france/FRANCE*` for several accepted spellings.
_GAP = re.compile(r"\*([^*]+)\*")

# Words, for marktheword. Punctuation is kept out of the token so that marking
# "cat" and marking "cat," are the same act; a learner clicking a word is not
# making a claim about the comma after it.
_WORD = re.compile(r"[^\s]+")


class BadAuthoring(ValueError):
    """Content that cannot be turned into a question."""


def split(kind: str, authored: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    """Split authored content into what may be shown and what may not.

    :returns: (content, answers)
    """
    spec = types.spec(kind)

    if not spec["graded"]:
        # Nothing to hide. Returned through the same function anyway so that a
        # caller has one code path, and so that adding a graded type later
        # cannot be done by forgetting to route it here.
        return dict(authored), []

    handler = _HANDLERS.get(kind)
    if handler is None:
        raise types.UnknownType(kind)
    return handler(authored)


# --------------------------------------------------------------------------
# One per graded type
# --------------------------------------------------------------------------

def _options(authored: dict[str, Any], single: bool) -> tuple[dict[str, Any], list[Any]]:
    raw = authored.get("options") or []
    if len(raw) < 2:
        raise BadAuthoring("a question with fewer than two options is not a choice")

    texts: list[str] = []
    correct: list[int] = []
    for index, option in enumerate(raw):
        if not isinstance(option, dict):
            raise BadAuthoring("each option must be an object with text and correct")
        texts.append(str(option.get("text", "")))
        if option.get("correct"):
            correct.append(index)

    if not correct:
        raise BadAuthoring("no option is marked correct")
    if single and len(correct) != 1:
        raise BadAuthoring("a single-answer question has exactly one correct option")

    return {"text": str(authored.get("text", "")), "options": texts}, correct


def _choice(authored):
    return _options(authored, single=True)


def _multichoice(authored):
    return _options(authored, single=False)


def _truefalse(authored):
    if "correct" not in authored:
        raise BadAuthoring("a true/false question needs a correct value")
    return {"text": str(authored.get("text", ""))}, [bool(authored["correct"])]


def _shorttext(authored):
    accepted = [str(word).strip() for word in (authored.get("accept") or [])]
    accepted = [word for word in accepted if word]
    if not accepted:
        raise BadAuthoring("a typed answer needs at least one accepted spelling")
    return {"text": str(authored.get("text", ""))}, accepted


def _gapped(authored: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    """Blank out `*word*` and collect what each gap accepts.

    The placeholder is positional and carries nothing about the answer: gap
    three is `[[3]]` whether the word is "France" or "a".
    """
    lines_out: list[str] = []
    accepted: list[list[str]] = []

    for line in authored.get("lines") or []:
        def take(match: re.Match) -> str:
            words = [word.strip() for word in match.group(1).split("/")]
            words = [word for word in words if word]
            if not words:
                raise BadAuthoring("an empty gap accepts nothing and can never be right")
            accepted.append(words)
            return f"[[{len(accepted) - 1}]]"

        lines_out.append(_GAP.sub(take, str(line)))

    if not accepted:
        raise BadAuthoring("no gaps found: mark them by wrapping a word in asterisks")

    return lines_out, accepted


def _blanks(authored):
    lines, accepted = _gapped(authored)
    return {"text": str(authored.get("text", "")), "lines": lines}, accepted


def _dragtext(authored):
    lines, accepted = _gapped(authored)

    # The bank is the first accepted spelling of each gap. Later spellings
    # exist to forgive typing, and there is nothing to forgive when the word
    # arrives by being dragged.
    bank = [words[0] for words in accepted]

    # Shuffled before storing, so the order sitting in the caller's database
    # is not a map of where the words go. timeline.py shuffles it again on the
    # way out; this one is what protects a host that reads the row without
    # going through us.
    #
    # Sorting instead would be reproducible and also a map — alphabetical
    # order against gap order gives the answer away for any sentence whose
    # gaps happen to be alphabetical, which is not rare in a list.
    random.shuffle(bank)

    return {
        "text": str(authored.get("text", "")),
        "lines": lines,
        "bank": bank,
    }, accepted


def _marktheword(authored):
    passage = str(authored.get("passage", ""))
    if not passage.strip():
        raise BadAuthoring("nothing to mark")

    words: list[str] = []
    correct: list[int] = []

    for token in _WORD.findall(passage):
        match = _GAP.fullmatch(token)
        if match:
            words.append(match.group(1))
            correct.append(len(words) - 1)
        else:
            # An asterisk in the middle of a token — "wasn*t" — is a typo, not
            # a mark. Left alone rather than guessed at, so the author sees
            # their own text and can fix it.
            words.append(token)

    if not correct:
        raise BadAuthoring("no word is marked: wrap the ones to find in asterisks")

    return {"text": str(authored.get("text", "")), "words": words}, correct


_HANDLERS = {
    "choice": _choice,
    "multichoice": _multichoice,
    "truefalse": _truefalse,
    "shorttext": _shorttext,
    "blanks": _blanks,
    "dragtext": _dragtext,
    "marktheword": _marktheword,
}
