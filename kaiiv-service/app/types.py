"""What kinds of interaction exist, and what is true about each one.

This is the replacement for H5P.Question, and it is the reason the player in
moodle/plugins/mod_kaiiv is a fork of H5P Interactive Video rather than an
installation of it.

Upstream, every interaction is a separate H5P library that receives its own
params — correct answers included — and decides in the browser whether the
learner got it right. For content meant to be explored that is a reasonable
design. For an activity sitting next to a proctoring stack it means the
answers are one devtools panel away, and no amount of care on the JavaScript
side fixes that.

So the types are declared here instead, once, in a service no browser can
reach. A host system asks this service what a learner may see, and asks it
again whether an answer was right. The player keeps the job it is good at —
putting the thing on screen at the right moment, in the right place — and
never the job of deciding.

`public` is an allowlist rather than a list of things to strip. A key added to
an interaction next year is invisible to learners until somebody decides it
should not be, which is the safe direction to fail in.
"""
from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------
#   graded      the service marks it, and it counts towards a score
#   pauses      playback stops here until it is dealt with
#   public      keys of `content` a browser may receive
#   bank        True when the answer words themselves must be sent anyway
#
# `bank` exists for exactly one type and is the honest exception to the rule
# the rest of this file enforces. See contract.py.
TYPES: dict[str, dict[str, Any]] = {
    # ---- marked ----------------------------------------------------------
    "choice": {
        "graded": True, "pauses": True,
        "public": ["text", "options"], "bank": False,
    },
    "multichoice": {
        "graded": True, "pauses": True,
        "public": ["text", "options"], "bank": False,
    },
    "truefalse": {
        "graded": True, "pauses": True,
        "public": ["text"], "bank": False,
    },
    "shorttext": {
        "graded": True, "pauses": True,
        "public": ["text"], "bank": False,
    },
    "blanks": {
        # Sentences with gaps. The author writes the accepted words inline
        # between asterisks; authoring.py takes them out before anything is
        # stored, so the raw form never exists outside one function.
        "graded": True, "pauses": True,
        "public": ["text", "lines"], "bank": False,
    },
    "dragtext": {
        # The word bank has to be sent — there is nothing to drag otherwise.
        # What is withheld is which gap each word belongs in, and the bank is
        # shuffled so its order says nothing either.
        "graded": True, "pauses": True,
        "public": ["text", "lines", "bank"], "bank": True,
    },
    "marktheword": {
        # Upstream ships the passage with the correct words wrapped in
        # asterisks and lets the browser compare. Here the passage goes out
        # with every word markable and the marking happens on the indexes.
        "graded": True, "pauses": True,
        "public": ["text", "words"], "bank": False,
    },

    # ---- not marked ------------------------------------------------------
    # These carry no answer, so there is nothing to withhold and the whole
    # content goes out. They are still in the registry because "does this
    # pause the video" is a question asked of every type, and because an empty
    # answer set is a fact worth declaring rather than inferring.
    "label": {
        "graded": False, "pauses": False,
        "public": ["text"], "bank": False,
    },
    "image": {
        "graded": False, "pauses": False,
        "public": ["url", "alt", "caption"], "bank": False,
    },
    "link": {
        "graded": False, "pauses": False,
        "public": ["url", "title"], "bank": False,
    },
}


class UnknownType(ValueError):
    """A type name nothing here recognises.

    Deliberately an error rather than a default. Every default available is
    either "send everything" or "mark nothing", and both are wrong in a way
    that does not show up until it matters.
    """


def spec(name: str) -> dict[str, Any]:
    try:
        return TYPES[name]
    except KeyError:
        raise UnknownType(name) from None


def known(name: str) -> bool:
    return name in TYPES


def is_graded(name: str) -> bool:
    return bool(spec(name)["graded"])


def pauses(name: str) -> bool:
    return bool(spec(name)["pauses"])


def sends_answer_words(name: str) -> bool:
    """Whether this type must send the answer words as part of its content.

    True only for dragtext. Named as a question about the type rather than as
    a flag on a list, because the next person to add a type has to answer it.
    """
    return bool(spec(name)["bank"])


def public_content(name: str, content: dict[str, Any]) -> dict[str, Any]:
    """The part of an interaction a browser may see."""
    return {key: content.get(key) for key in spec(name)["public"]}


def catalogue() -> list[dict[str, Any]]:
    """The registry, for a host system building an authoring screen.

    A host that hard-codes this list will drift from it. One that asks gets an
    editor that grows a field when the engine does.
    """
    return [
        {
            "type": name,
            "graded": entry["graded"],
            "pauses": entry["pauses"],
            "fields": list(entry["public"]),
        }
        for name, entry in TYPES.items()
    ]
