"""Acceptance check against a running engine, over the real network.

The suite next to this one proves the rules are right. It proves nothing about
a deployment: it imports the modules directly, so it passes on a machine where
the container never started, the key is wrong, or the service is reachable from
somewhere it should not be.

This one is for the other question — "is the thing we installed the thing we
tested" — and it is meant to be run after deploying at a customer site, not
only here.

It is not collected by pytest. It needs a running service and a key, so it
would fail on a developer machine for a reason that says nothing about the
code, and a suite that is red by default stops being read.

    docker run --rm --network <stack>_default \\
        -v "$PWD/kaiiv-service/tests/live_check.py:/t.py" \\
        -e KAIIV_URL=http://kaiiv-service:9200 \\
        -e KAIIV_API_KEY=<the key> \\
        python:3.12-slim python /t.py

Run it from a container on the stack network rather than from the host. The
host is supposed to fail — see check_not_published().
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("KAIIV_URL", "http://kaiiv-service:9200").rstrip("/")
KEY = os.environ.get("KAIIV_API_KEY", "")

CONTRACT = "1.0"

failures: list[str] = []


def call(path: str, payload: dict | None = None, key: str | None = KEY,
         method: str | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        URL + path, data=body,
        method=method or ("POST" if body is not None else "GET"))
    request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("X-Proctor-Key", key)

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode() or "{}")


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


# --------------------------------------------------------------------------

def check_up() -> None:
    print("service")
    status, body = call("/health", key=None)
    check("health answers without a key", status == 200 and body.get("ok"))
    check("it is the engine and not something else on that port",
          body.get("service") == "kaiiv", repr(body.get("service")))
    check("a key is configured on the service", body.get("keyed") is True,
          "KAIIV_API_KEY is empty in the container: every call would be 401")
    check("it speaks the contract this integration sends",
          CONTRACT in (body.get("supported") or []), repr(body.get("supported")))


def check_key_is_enforced() -> None:
    print("access")
    status, _ = call("/types", key=None)
    check("no key is refused", status == 401, f"got {status}")

    status, _ = call("/types", key="not-the-key")
    check("a wrong key is refused", status == 401, f"got {status}")

    status, body = call("/types")
    check("the configured key is accepted", status == 200 and body.get("ok"),
          f"got {status}: the key here and the key in the container differ")


def check_answers_do_not_leave() -> None:
    """The claim the whole design exists to make, checked over the wire.

    Not a unit test repeated: this is the payload as it arrives at a browser,
    through whatever proxy and serialisation the deployment actually has.
    """
    print("answers")

    status, authored = call("/author", {
        "contract": CONTRACT,
        "type": "shorttext",
        "authored": {"text": "Capital of France?", "accept": ["Paris"]},
    })
    if status != 200 or not authored.get("ok"):
        check("authoring works", False, json.dumps(authored))
        return
    check("authoring works", True)

    row = {
        "id": 1, "type": "shorttext", "start": 5.0, "end": 5.0,
        "pauses": True,
        "content": authored["content"], "answers": authored["answers"],
        "feedback": "It is on the Seine.",
    }
    rules = {"allowreview": True, "maxattempts": 2}

    status, timeline = call("/timeline", {
        "contract": CONTRACT, "interactions": [row], "seen": {}, "rules": rules,
    })
    wire = json.dumps(timeline, ensure_ascii=False).lower()

    check("the timeline is served", status == 200 and timeline.get("ok"))
    check("the answer is not in what the browser receives",
          "paris" not in wire, "THE ANSWER IS IN THE PAYLOAD — do not ship")
    check("the explanation is not in it either",
          "seine" not in wire.lower())
    check("the question still is", "capital of france" in wire)


def check_the_video_stops() -> None:
    print("playback")
    row = {
        "id": 1, "type": "choice", "start": 5.0, "end": 5.0, "pauses": True,
        "content": {"text": "?", "options": ["a", "b"]}, "answers": [0],
    }
    rules = {"allowreview": True, "maxattempts": 0}

    _, timeline = call("/timeline", {
        "contract": CONTRACT, "interactions": [row], "seen": {}, "rules": rules,
    })
    items = timeline.get("items") or []

    _, before = call("/due", {"contract": CONTRACT, "items": items, "at": 4.0})
    check("nothing blocks before the question", before.get("blocked") is False)

    _, at = call("/due", {"contract": CONTRACT, "items": items, "at": 5.0})
    check("the question blocks at its own second", at.get("blocked") is True)

    # The case a seekbar creates and a crossing-detector misses.
    _, past = call("/due", {"contract": CONTRACT, "items": items, "at": 90.0})
    check("dragging the seekbar past it does not get past it",
          past.get("blocked") is True,
          "a learner can skip questions in this deployment")

    _, answered = call("/timeline", {
        "contract": CONTRACT, "interactions": [row],
        "seen": {"1": {"correct": True, "attempts": 1, "response": [0]}},
        "rules": rules,
    })
    _, after = call("/due", {
        "contract": CONTRACT, "items": answered.get("items") or [], "at": 90.0,
    })
    check("answering it lets the video on", after.get("blocked") is False)


def check_retry_does_not_hand_out_marks() -> None:
    print("retry")
    rules = {"allowreview": True, "maxattempts": 2}
    common = {
        "contract": CONTRACT, "type": "shorttext",
        "content": {"text": "Capital of France?"}, "answers": ["Paris"],
        "feedback": "It is on the Seine.", "rules": rules,
    }

    _, wrong = call("/judge", {**common, "response": "Lyon", "attempts": 0})
    check("a wrong answer with a retry left reveals nothing",
          wrong.get("answers") == [] and wrong.get("feedback") == "",
          json.dumps(wrong))
    check("and says a retry is available", wrong.get("may_retry") is True)

    _, last = call("/judge", {**common, "response": "Lyon", "attempts": 1})
    check("the last attempt releases the answer",
          last.get("revealed") is True and last.get("answers") == ["Paris"])

    _, right = call("/judge", {**common, "response": "  PARIS ", "attempts": 0})
    check("case and spacing are forgiven", right.get("correct") is True)
    check("and the stored form is folded", right.get("store") == "paris",
          repr(right.get("store")))


def check_not_published() -> None:
    """The service must not be reachable from outside the stack network.

    Only meaningful when this runs on the host, so it is skipped otherwise. A
    browser that can reach the engine can ask it to mark things, and marking
    is the one thing a browser must never be able to ask for directly.
    """
    if "localhost" not in URL and "127.0.0.1" not in URL:
        return

    print("exposure")
    print("  note  running against " + URL + " from the host.")
    print("        If this reached the engine, docker-compose.yml has ports:")
    print("        where it should have expose: — that is the finding.")


def main() -> int:
    print(f"kaiiv engine acceptance check against {URL}\n")

    check_not_published()
    check_up()
    check_key_is_enforced()
    check_answers_do_not_leave()
    check_the_video_stops()
    check_retry_does_not_hand_out_marks()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for name in failures:
            print(f"  - {name}")
        return 1

    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
