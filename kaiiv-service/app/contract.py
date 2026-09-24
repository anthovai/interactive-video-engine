"""What may leave this service, enforced at the boundary.

The point of running the engine as a separate service is that a rule stops
being a claim about everybody's discipline and becomes a claim about one file.

Inside a single application, "the player never receives the correct answer" is
a promise about every function that touches a timeline, now and in every
version anyone writes afterwards. Here it is a promise about this file, and a
caller — or a future one of us — who gets it wrong receives a 500 with a
diagnosis instead of quietly shipping the answers to a browser.

That distinction is the commercial one as much as the technical one. It lets
us tell a customer that a learner cannot read the answers out of the page, and
point at the code that makes it so, rather than at a paragraph in a document.

Two mechanisms, because they fail differently:

  1. A whitelist of shape. Only the keys types.public_content() names are
     copied out of an interaction. A key added to stored content next year
     does not start flowing to browsers because somebody forgot to filter it.

  2. A search for the answers themselves in the finished payload. This is the
     check that survives a refactor: somebody who adds a convenient
     `"solution"` field and forgets the whitelist is stopped here, because the
     string is found no matter what it is called.

The second check has exactly one exception, and it is declared rather than
tolerated — see below.
"""
from __future__ import annotations

import json
from typing import Any

from . import types


class ContractViolation(RuntimeError):
    """A payload was built that must not be sent.

    Raised rather than logged, and never caught upstream of the response. A
    timeline that cannot be served safely must not be served at all: a broken
    activity is a support call, and a leaked answer key is a re-sat exam for
    everybody who took it.
    """


class BadRequest(ValueError):
    """A payload arrived that cannot be worked with."""


def check_contract_version(version: str) -> None:
    from . import config

    if version not in config.SUPPORTED_CONTRACTS:
        raise BadRequest(
            f"contract {version!r} is not supported by this engine "
            f"(supported: {sorted(config.SUPPORTED_CONTRACTS)})")


def answer_strings(kind: str, answers: list[Any]) -> set[str]:
    """The answer, as text that must not appear in what we send.

    Index answers produce nothing: for a choice question the answer is the
    number 2, and a payload that legitimately contains options and positions
    would collide with it constantly. Withholding those is the whitelist's
    job, and a search for "2" would be noise that trained everyone to ignore
    this check.

    Word answers produce their own text, folded the same way grading folds it
    so that a near-miss spelling is still caught.
    """
    from . import grading

    out: set[str] = set()

    for answer in answers:
        if isinstance(answer, bool) or isinstance(answer, int):
            continue
        if isinstance(answer, str):
            folded = grading.normalise(answer)
            if folded:
                out.add(folded)
        elif isinstance(answer, list):
            for word in answer:
                if isinstance(word, str):
                    folded = grading.normalise(word)
                    if folded:
                        out.add(folded)

    return out


def assert_no_leak(kind: str, answers: list[Any], payload: Any) -> None:
    """Refuse to send a payload containing the answer.

    The one exception is dragtext, whose word bank is the answer words by
    definition: there is nothing to drag otherwise. What that type withholds
    is which gap each word belongs in, and that is withheld by the whitelist
    like everything else. Naming the exception here — rather than skipping the
    check for anything that happens to trip it — means adding a second
    exception is a decision somebody has to write down.
    """
    if types.sends_answer_words(kind):
        return

    wanted = answer_strings(kind, answers)
    if not wanted:
        return

    from . import grading

    haystack = grading.normalise(json.dumps(payload, ensure_ascii=False))

    for word in wanted:
        # Substring rather than word boundaries. A payload that contains the
        # answer inside a longer string is still a payload a learner can read.
        if word in haystack:
            raise ContractViolation(
                f"an interaction of type {kind} was about to be sent with its "
                f"answer inside it. The whitelist in types.py is the thing to "
                f"fix — not this check.")


def limit_interactions(interactions: list[Any]) -> None:
    from . import config

    if len(interactions) > config.MAX_INTERACTIONS:
        raise BadRequest(
            f"{len(interactions)} interactions is more than this engine will "
            f"serve in one timeline ({config.MAX_INTERACTIONS}); a request "
            f"this size is usually the wrong list, not a long video")


def limit_text(value: Any) -> None:
    from . import config

    if isinstance(value, str) and len(value) > config.MAX_TEXT:
        raise BadRequest("that is too much text for one interaction")
