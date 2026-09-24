"""The interactive video engine, as a service.

It decides three things and holds none of them: what a learner may see of a
timeline, whether an answer was right, and what a video should do at a given
second. The platform that called keeps the course, the learners, the video and
the record.

Deliberately stateless, and this is the whole design rather than a detail.
Interactive video is being built here to be used by more than one system —
this Moodle build today, and whatever it is merged with next — and two systems
sharing an engine that also owns storage is two systems arguing about whose
copy of a learner is real. An engine that owns nothing can be shared by both.

It is also why there is no database setting in config.py. That is not a
missing feature to add later: adding it would turn a component into a second
platform, and the platform already exists.

Not published to the host. The calling platform reaches it on the internal
network with a shared key, exactly as it reaches the face and AI services.
There is no outside-facing API here and none is planned — a browser that can
reach this service can ask it to mark things, and marking is the one thing a
browser must never be able to ask for directly.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from . import authoring, config, contract, grading, timeline, types

app = FastAPI(
    title="KAISER interactive video engine",
    version=config.SERVICE_VERSION,
    # No interactive docs. They are a convenience for whoever can reach the
    # service, and the list of who can reach it is "the platform".
    docs_url=None,
    redoc_url=None,
)


def require_key(x_proctor_key: str = Header(default="")) -> None:
    if not config.API_KEY or x_proctor_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="bad key")


def _fail(status: int, code: str, detail: str) -> JSONResponse:
    """One error shape for every refusal.

    A caller integrating against this has to be able to tell a bad request
    from a bad answer from a bug in us, and an HTML error page or a bare
    string does not let it.
    """
    return JSONResponse(status_code=status, content={
        "ok": False, "error": code, "detail": detail,
    })


@app.get("/health")
def health() -> dict[str, Any]:
    """Is it up, and what does it speak.

    Unauthenticated, like the other services: the container healthcheck runs
    before anything has a key, and the answer says nothing about any learner.
    """
    return {
        "ok": True,
        "service": "kaiiv",
        "version": config.SERVICE_VERSION,
        "contract": config.CONTRACT_VERSION,
        "supported": sorted(config.SUPPORTED_CONTRACTS),
        "keyed": bool(config.API_KEY),
    }


@app.get("/types", dependencies=[Depends(require_key)])
def catalogue() -> dict[str, Any]:
    """What kinds of interaction exist, and what each one is made of.

    Here so that a host system's authoring screen can be built from the
    engine rather than alongside it. A host that hard-codes this list drifts
    from it; one that asks grows a field when the engine does.
    """
    return {"ok": True, "types": types.catalogue()}


@app.post("/author", dependencies=[Depends(require_key)], response_model=None)
def author(payload: dict[str, Any]) -> Any:
    """Split what a teacher typed into what may be stored and what may not.

    The caller stores both halves in two columns and sends them back to
    /timeline and /judge. The authored form — the one with the answers written
    inline — is never stored by anybody, because it never leaves here intact.
    """
    try:
        contract.check_contract_version(str(payload.get("contract", "")))
        kind = str(payload.get("type", ""))
        raw = payload.get("authored") or {}

        for value in raw.values():
            contract.limit_text(value)

        content, answers = authoring.split(kind, raw)
    except types.UnknownType as error:
        return _fail(422, "unknown_type", str(error))
    except authoring.BadAuthoring as error:
        return _fail(422, "bad_authoring", str(error))
    except contract.BadRequest as error:
        return _fail(422, "bad_request", str(error))

    return {
        "ok": True,
        "type": kind,
        "content": content,
        "answers": answers,
        "graded": types.is_graded(kind),
        "pauses": types.pauses(kind),
    }


@app.post("/timeline", dependencies=[Depends(require_key)], response_model=None)
def build_timeline(payload: dict[str, Any]) -> Any:
    """What this learner may see.

    The request carries the answers, because the caller stored them and the
    engine has to know them to decide which ones have been earned. The
    response does not, except where they have been. contract.py is what makes
    that a statement about code rather than about care.
    """
    try:
        contract.check_contract_version(str(payload.get("contract", "")))
        items = timeline.for_player(
            payload.get("interactions") or [],
            payload.get("seen") or {},
            payload.get("rules") or {},
        )
    except contract.BadRequest as error:
        return _fail(422, "bad_request", str(error))
    except contract.ContractViolation as error:
        # A 500, not a 422. The caller did nothing wrong; we were about to.
        return _fail(500, "contract_violation", str(error))

    return {"ok": True, "items": items}


@app.post("/judge", dependencies=[Depends(require_key)], response_model=None)
def judge(payload: dict[str, Any]) -> Any:
    """Mark one answer, and say how much of it the learner may now be told.

    The caller writes the result down. This service does not remember that it
    was asked, which means a caller replaying the same request gets the same
    answer and no second attempt is recorded anywhere by accident — counting
    attempts belongs to whoever owns the record.
    """
    try:
        contract.check_contract_version(str(payload.get("contract", "")))

        kind = str(payload.get("type", ""))
        content = payload.get("content") or {}
        answers = payload.get("answers") or []
        rules = payload.get("rules") or {}
        before = int(payload.get("attempts", 0))
        attempts = before + 1

        # Refused before anything is marked, and refused here rather than
        # left to each caller. A wrong answer with no attempt left, marked
        # anyway, is a record the caller will read back as the latest word —
        # so a learner who got it wrong once, on a one-attempt question, could
        # post the right answer straight to the caller's endpoint and have it
        # count. The same after a correct answer: the answer has been revealed
        # by then, and marking again is marking something already given away.
        #
        # Every caller gets this by sending what it already knows: how many
        # attempts came before, and whether one of them was right.
        if payload.get("answered_correctly"):
            return _fail(409, "already_correct",
                         "this interaction has already been answered correctly")
        if before > 0 and not timeline.may_retry(rules, before):
            return _fail(409, "no_attempts_left",
                         "no attempts are left on this interaction")

        stored, correct = grading.judge(
            kind, content, answers, payload.get("response"))
    except types.UnknownType as error:
        return _fail(422, "unknown_type", str(error))
    except grading.BadResponse as error:
        return _fail(422, "bad_response", str(error))
    except contract.BadRequest as error:
        return _fail(422, "bad_request", str(error))

    revealed = timeline.is_revealed(rules, correct, attempts)

    return {
        "ok": True,
        "correct": correct,
        "store": stored,
        "attempts": attempts,
        "revealed": revealed,
        "may_retry": timeline.may_retry(rules, attempts),
        # Released together or not at all. The explanation is the reason for
        # asking a question in the middle of a lesson, and an explanation
        # handed over while a retry is still available is the answer in prose.
        "answers": answers if revealed else [],
        "feedback": payload.get("feedback", "") if revealed else "",
    }


@app.post("/due", dependencies=[Depends(require_key)], response_model=None)
def what_is_due(payload: dict[str, Any]) -> Any:
    """What stands between this learner and playing on from here.

    The player works this out too, and has to — it cannot ask across the
    network on every frame. This is the copy that is the record: the player's
    is a convenience, and a convenience is not something to enforce a rule
    with.
    """
    try:
        contract.check_contract_version(str(payload.get("contract", "")))
        items = payload.get("items") or []
        at = float(payload.get("at", 0))
    except (contract.BadRequest, TypeError, ValueError) as error:
        return _fail(422, "bad_request", str(error))

    blocking = timeline.due(items, at)
    return {
        "ok": True,
        "blocked": bool(blocking),
        "due": blocking,
    }


@app.post("/score", dependencies=[Depends(require_key)], response_model=None)
def score(payload: dict[str, Any]) -> Any:
    """What the learner has earned so far, as a fraction."""
    try:
        contract.check_contract_version(str(payload.get("contract", "")))
        result = timeline.score(
            payload.get("interactions") or [],
            payload.get("seen") or {},
        )
    except contract.BadRequest as error:
        return _fail(422, "bad_request", str(error))

    return {"ok": True, **result}
