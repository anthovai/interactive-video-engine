"""Answer every kind of interaction, in a real browser, the way a learner does.

browser_check.py proves the rules: the video stops, cannot be skipped, and
the answer is not in the page. It answers one question. This one answers all
of them, because each kind is drawn by its own renderer in interactions.js,
and a renderer nobody has clicked is a renderer nobody knows works.

It walks the seeded activity from start to end: plays up to each interaction,
does whatever that kind needs — click an option, tick boxes, type, place
words, mark words, open a marker — with the right answer, and checks the
server said correct. Then it presses the card's own Continue, and checks the
video carries on.

    php mod/kaiiv/tests/reset_learner.php <cmid> learner   (in the container)
    KAIIV_LEARNER_PASSWORD=... python moodle/plugins/mod_kaiiv/tests/browser_types.py <cmid> [base-url]
    KAIIV_PAGE=http://127.0.0.1:8200/ python moodle/plugins/mod_kaiiv/tests/browser_types.py

The reset matters: an activity the learner has already answered does not ask
again, which is right for them and useless for this.

The answers below are the ones docker/seed-demo.php authors. They are here in
the test and nowhere a browser can reach — which is the property the rest of
the suite checks.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CMID = sys.argv[1] if len(sys.argv) > 1 else "7"
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8099"
# Any page the player is on, rather than a Moodle activity: the example server
# in kaiiv-player/examples/server, or a customer's own. Opened as it is, with
# no Moodle sign-in, because the page decides who the learner is.
PAGE = os.environ.get("KAIIV_PAGE", "")
# From the environment; see browser_check.py. Only needed for Moodle.
PASSWORD = os.environ.get("KAIIV_LEARNER_PASSWORD", "")
if not PAGE and not PASSWORD:
    sys.exit("set KAIIV_LEARNER_PASSWORD to the test learner's password, "
             "or KAIIV_PAGE to a page that needs no sign-in")

problems: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("  ok    " if ok else "  FAIL  ") + name
          + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        problems.append(name)
    return ok


# ---------------------------------------------------------------------------
# Driving the video
# ---------------------------------------------------------------------------

def video_state(page) -> dict:
    return page.evaluate(
        """() => {
            const v = document.querySelector('[data-region="stage"] video');
            return v ? {at: v.currentTime, paused: v.paused} : {};
        }"""
    )


def play_up_to(page, seconds: float) -> None:  # noqa: unused, kept for manual use
    """Start playback a moment before a point, so it is reached by playing.

    Seeking straight onto it would test the seek, not the question: a question
    that pauses the video is due at an instant, and arriving there by playback
    is what a learner does.
    """
    page.evaluate(
        """(t) => {
            const v = document.querySelector('[data-region="stage"] video');
            v.currentTime = Math.max(0, t);
            return v.play();
        }""",
        seconds - 0.8,
    )


def card(page, kind: str):
    return page.locator(f'.kaiiv-interaction[data-type="{kind}"]').first


def wait_for_card(page, kind: str, timeout: int = 15000) -> bool:
    try:
        page.wait_for_selector(f'.kaiiv-interaction[data-type="{kind}"]',
                               timeout=timeout)
        return True
    except Exception:
        return False


def verdict(page, kind: str) -> dict:
    return page.evaluate(
        """(kind) => {
            const c = document.querySelector(
                '.kaiiv-interaction[data-type="' + kind + '"]');
            const v = c && c.querySelector('[data-region="verdict"]');
            const o = c && c.querySelector('[data-region="outcome"]');
            return {
                shown: !!(o && !o.hidden),
                text: v ? v.innerText : '',
                correct: !!(v && v.classList.contains('text-success')),
            };
        }""",
        kind,
    )


def settle(page, kind: str) -> dict:
    try:
        page.wait_for_selector(
            f'.kaiiv-interaction[data-type="{kind}"] [data-region="outcome"]:not([hidden])',
            timeout=10000)
    except Exception:
        pass
    return verdict(page, kind)


def press_continue(page, kind: str) -> None:
    page.evaluate(
        """(kind) => {
            const c = document.querySelector(
                '.kaiiv-interaction[data-type="' + kind + '"]');
            const buttons = c ? c.querySelectorAll('[data-action="continue"]') : [];
            for (const b of buttons) {
                if (!b.hidden) { b.click(); return true; }
            }
            return false;
        }""",
        kind,
    )


def carries_on(page, after: float) -> bool:
    """The video plays on past a point once the question there is settled."""
    for _ in range(20):
        page.wait_for_timeout(250)
        state = video_state(page)
        if state and not state["paused"] and state["at"] > after + 0.2:
            return True
    return False


# ---------------------------------------------------------------------------
# One per kind. Each does what a learner does, with the right answer.
# ---------------------------------------------------------------------------

def answer_choice(page) -> None:
    card(page, "choice").locator('[data-option="0"]').click()


def answer_truefalse(page) -> None:
    card(page, "truefalse").locator('[data-value="1"]').click()


def answer_multichoice(page) -> None:
    c = card(page, "multichoice")
    for index in (0, 1, 3):
        c.locator(f'input[data-option="{index}"]').check()
    c.locator('[data-action="submit"]').click()


def answer_shorttext(page) -> None:
    c = card(page, "shorttext")
    # Typed with the spacing and capitals a learner might use; the engine is
    # what forgives them, and this is the only place that is seen end to end.
    c.locator('input[data-region="typed"]').fill("  Vector ")
    c.locator('input[data-region="typed"]').press("Enter")


def answer_blanks(page) -> None:
    c = card(page, "blanks")
    c.locator('input[data-gap="0"]').fill("เวกเตอร์")
    c.locator('input[data-gap="1"]').fill("distance")
    c.locator('[data-action="submit"]').click()


def answer_dragtext(page) -> None:
    c = card(page, "dragtext")
    # Pick a word from the bank, then the gap it goes in. The bank arrives
    # shuffled, so words are found by what they say, not by position.
    for gap, word in ((0, "ตรวจจับ"), (1, "เทียบ")):
        c.locator(f'.kaiiv-bank button[data-word="{word}"]').click()
        c.locator(f'span.kaiiv-gap[data-gap="{gap}"]').click()
    c.locator('[data-action="submit"]').click()


def answer_marktheword(page) -> None:
    c = card(page, "marktheword")
    # "ระบบบันทึก *เหตุการณ์* และ *เวลา* แต่ไม่บันทึก ..." — words 1 and 3.
    for index in (1, 3):
        c.locator(f'.kaiiv-word[data-word="{index}"]').click()
    c.locator('[data-action="submit"]').click()


# In the order they come on the video. The walk is by playback only — no
# seeking — because that is what a learner does, and because the fork keeps
# its own idea of which interaction comes next and only a seek through its own
# API resets it. A test that jumped the playhead around would be testing that
# bookkeeping, not the interactions.
TIMELINE = [
    ("choice", 3, answer_choice, '[data-option="0"]'),
    ("truefalse", 8, answer_truefalse, '[data-value="1"]'),
    ("multichoice", 13, answer_multichoice, 'input[data-option="3"]'),
    ("shorttext", 18, answer_shorttext, 'input[data-region="typed"]'),
    ("blanks", 23, answer_blanks, 'input[data-gap="1"]'),
    ("label", 28, None, None),
    ("dragtext", 33, answer_dragtext, '.kaiiv-bank button'),
    ("marktheword", 38, answer_marktheword, '.kaiiv-word[data-word="3"]'),
    # Markers carry their label, which is how a learner tells two apart — and
    # how this test has to: the fork keeps a marker up for a second past its
    # end, so at 00:48 the image's marker and the link's are both on screen,
    # and "press the first one you see" presses the wrong one.
    ("image", 43, "marker", ("img", "แผนผังขั้นตอน")),
    ("link", 48, "marker", ("a[href]", "นโยบายข้อมูล")),
]


def pausing_question(page, kind, at, answer, offers) -> None:
    if not check("  it appeared", wait_for_card(page, kind)):
        return
    state = video_state(page)
    check("  and stopped the video", state.get("paused") is True, str(state))
    check("  it offers what this kind needs",
          card(page, kind).locator(offers).count() > 0, offers)
    page.screenshot(path=f"reports/kaiiv-type-{kind}.png")

    try:
        answer(page)
    except Exception as error:
        # What else is on the video is usually the answer: a card that could
        # not be clicked is a card something else is lying on top of.
        present = page.evaluate(
            "() => [...document.querySelectorAll('.kaiiv-interaction')]"
            ".map((c) => c.getAttribute('data-type')).join(', ')")
        check("  it could be answered", False,
              str(error).splitlines()[0] + f" — cards on the page: {present}")
        return

    result = settle(page, kind)
    check("  the server's verdict was shown", result["shown"], str(result))
    check("  and it was correct", result["correct"], repr(result["text"]))

    press_continue(page, kind)
    check("  Continue carries the video on", carries_on(page, at),
          str(video_state(page)))


def caption(page) -> None:
    if not check("  it appeared", wait_for_card(page, "label")):
        return
    state = video_state(page)
    check("  without stopping the video", state.get("paused") is False, str(state))
    page.screenshot(path="reports/kaiiv-type-label.png")
    # Pressed so that it counts as reached — "answer everything" is about
    # walking through the video, and a caption is a stop on that walk.
    press_continue(page, "label")
    page.wait_for_timeout(600)
    check("  pressing it leaves the video playing",
          video_state(page).get("paused") is False, str(video_state(page)))


def marker(page, kind, spec) -> None:
    inside, label = spec
    # A marker interaction is a button on the video for as long as its window
    # lasts, and opens in the dialog when pressed.
    visible = False
    for _ in range(48):
        visible = page.evaluate(
            """(label) => [...document.querySelectorAll(
                    '.h5p-interaction.h5p-kaiivinteraction-interaction:not(.h5p-poster)')]
                .some((b) => b.offsetParent !== null
                    && ((b.getAttribute('aria-label') || '') + ' ' + b.innerText).includes(label))""",
            label,
        )
        if visible:
            break
        page.wait_for_timeout(250)
    if not check("  its marker came up on the video", visible):
        return

    pressed = page.evaluate(
        """(label) => {
            for (const b of document.querySelectorAll(
                    '.h5p-interaction.h5p-kaiivinteraction-interaction:not(.h5p-poster)')) {
                const named = (b.getAttribute('aria-label') || '') + ' ' + b.innerText;
                if (b.offsetParent !== null && named.includes(label)) {
                    (b.querySelector('.h5p-interaction-button') || b).click();
                    return true;
                }
            }
            return false;
        }""",
        label,
    )
    check(f"  the marker named {label!r} could be pressed", pressed)
    try:
        page.wait_for_selector(
            f'.kaiiv-dialog:not([hidden]) .kaiiv-interaction[data-type="{kind}"] {inside}',
            timeout=8000)
        shown = True
    except Exception:
        shown = False
    check(f"  pressing it opened the dialog showing its {inside}", shown)
    page.screenshot(path=f"reports/kaiiv-type-{kind}.png")
    if not shown:
        return

    page.evaluate(
        """(kind) => {
            const c = document.querySelector(
                '.kaiiv-dialog .kaiiv-interaction[data-type="' + kind + '"]');
            const b = c && c.querySelector('[data-action="continue"]');
            if (b) { b.click(); }
        }""",
        kind,
    )
    page.wait_for_timeout(1000)
    closed = page.evaluate(
        "() => { const d = document.querySelector('.kaiiv-dialog');"
        " return !d || d.hidden; }")
    check("  Continue closed the dialog", closed)
    check("  and the video carries on", video_state(page).get("paused") is False,
          str(video_state(page)))


def main() -> int:
    target = PAGE or f"{BASE}/mod/kaiiv/view.php?id={CMID}"
    print(f"every interaction type, against {target}")
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1400, "height": 1100})

        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" and "favicon" not in m.text else None)

        # Moodle's sign-in, or any other page with the same three fields —
        # the studio's uses them — when KAIIV_LOGIN_URL says where it is.
        login = os.environ.get("KAIIV_LOGIN_URL") or (None if PAGE else f"{BASE}/login/index.php")
        if login:
            page.goto(login)
            page.fill("#username", os.environ.get("KAIIV_LEARNER_USER", "learner"))
            page.fill("#password", PASSWORD)
            page.click("#loginbtn")
            page.wait_for_load_state("networkidle")

        page.goto(target)
        page.wait_for_selector('[data-region="kaiiv"][data-state="ready"]', timeout=30000)
        page.evaluate("() => { const s = document.querySelector('.h5p-splash'); if (s) s.click(); }")

        for kind, at, how, what in TIMELINE:
            print(f"{kind} at {at}s")
            if how is None:
                caption(page)
            elif how == "marker":
                marker(page, kind, what)
            else:
                pausing_question(page, kind, at, how, what)

        real = [e for e in errors if "404" not in e]
        check("no JavaScript errors on the page", not real, "; ".join(real[:3]))

        # Leave the page before closing the browser, and give it a moment.
        # Leaving fires pagehide, which sends the learner's position as a
        # beacon; closing the browser outright can let that beacon land after
        # the next run's reset, and the next run then opens a learner who is
        # half way through the video and was supposed to be at the start.
        page.goto("about:blank")
        page.wait_for_timeout(1500)
        browser.close()

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for name in problems:
            print("  - " + name.strip())
        return 1
    print("every interaction type works in a browser")
    return 0


if __name__ == "__main__":
    sys.exit(main())
