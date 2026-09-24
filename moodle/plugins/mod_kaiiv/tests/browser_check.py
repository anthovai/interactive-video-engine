"""Drive the player the way a learner does, in a real browser.

Everything else about this plugin has now been checked without one. The engine
has unit tests, the bundle boots under jsdom, and the delivered HTML has been
searched for answers. None of that proves the one thing the activity is for:
that a question appears on the video and refuses to be got past.

So this is the missing half — the same three claims tests/test_15_kaivideo.py
makes about the other player:

  - a question placed at 00:03 actually stops the video at 00:03;
  - dragging the seek bar past a question does not get past the question;
  - the correct answer is not sitting in the page waiting to be read.

Standalone rather than part of the pytest suite next door, because that suite
brings the whole stack up and reseeds it. This one runs against a stack that
is already up, which is what makes it usable while developing.

    KAIIV_LEARNER_PASSWORD=... python moodle/plugins/mod_kaiiv/tests/browser_check.py <cmid> [base-url]

The learner must have accepted the site policy, or every page redirects to it.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

# The questions are in Thai and so are the answers this searches for. On a
# Windows console that defaults to cp1252, printing one raises — and the
# traceback lands in the middle of the results, where it reads like the page
# failed rather than the printing.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8099"
CMID = sys.argv[1] if len(sys.argv) > 1 else "7"

# The test learner's sign-in, from the environment rather than written here,
# because this file is published and a password in it would be a password on
# every site that ever used the same seed.
USERNAME = os.environ.get("KAIIV_LEARNER_USER", "learner")
PASSWORD = os.environ.get("KAIIV_LEARNER_PASSWORD", "")
if not PASSWORD:
    sys.exit("set KAIIV_LEARNER_PASSWORD to the test learner's password")

# The words a learner would be looking for, and that appear in no Moodle
# string, no Bootstrap class and no library — so finding one in the page means
# it came out of the answers column.
ANSWERS = ["เวกเตอร์", "embedding", "ระยะห่าง", "distance"]

problems: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        problems.append(name)
    return ok


def sign_in(page) -> None:
    page.goto(f"{BASE}/login/index.php")
    page.fill("#username", USERNAME)
    page.fill("#password", PASSWORD)
    page.click("#loginbtn")
    page.wait_for_load_state("networkidle")


def seek(page, seconds: float) -> None:
    """Move the playhead the way the seek bar does.

    The video is driven directly rather than played through. Playwright's
    Chromium is built without the proprietary codecs, so an H.264 MP4 may
    never decode a frame here — and waiting for real playback would make this
    a test of the build rather than of the activity.

    It is also the more interesting case: setting currentTime is exactly what
    dragging the seek bar does, and the rule being checked is that arriving at
    a point is what makes a question due, not passing through it.
    """
    page.evaluate(
        """(t) => {
            const video = document.querySelector('[data-region="stage"] video');
            if (!video) { return; }
            video.currentTime = t;
            video.dispatchEvent(new Event('timeupdate'));
            video.dispatchEvent(new Event('seeked'));
        }""",
        seconds,
    )
    page.wait_for_timeout(600)


def interaction_text(page) -> str:
    return page.evaluate(
        """() => {
            const el = document.querySelector('.kaiiv-interaction');
            return el ? el.innerText : '';
        }"""
    )


def main() -> int:
    print(f"browser check against {BASE}/mod/kaiiv/view.php?id={CMID}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        # Tall enough that the video, the question drawn over it and the
        # controls under it are all on screen at once, so the screenshot is
        # evidence rather than a crop.
        page = browser.new_page(viewport={"width": 1400, "height": 1100})

        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        sign_in(page)
        check("signed in", "login" not in page.url, page.url)

        page.goto(f"{BASE}/mod/kaiiv/view.php?id={CMID}")
        page.wait_for_load_state("networkidle")

        check("the activity page loaded", "/mod/kaiiv/view.php" in page.url, page.url)
        check("the player container is there",
              page.locator('[data-region="kaiiv"]').count() == 1)

        # The bundle sets this attribute once the fork has attached. Until it
        # does, nothing below is testing the player.
        try:
            page.wait_for_selector('[data-region="kaiiv"][data-state="ready"]',
                                   timeout=15000)
            ready = True
        except Exception:
            ready = False
        check("the player reported itself ready", ready,
              "data-state is still "
              + str(page.get_attribute('[data-region="kaiiv"]', "data-state")))

        # Printed here rather than only at the end. When the player does not
        # become ready, whatever threw on the way is the answer, and every
        # check after this one is a consequence of it.
        if not ready and console_errors:
            print("\n  what the page reported:")
            for line in console_errors[:6]:
                print("    " + line[:400])
            print()

        check("the fork drew its controls",
              page.locator('[data-region="stage"] .h5p-controls, '
                           '[data-region="stage"] .h5p-control').count() > 0
              or page.locator('[data-region="stage"] > *').count() > 1)

        # Every interaction gets a marker on the seek bar. Ten were seeded,
        # one of each kind the engine knows, so this is also the check that
        # the types nobody has clicked still reach the timeline.
        markers = page.locator(".h5p-seekbar-interaction").count()
        check("every interaction has a marker on the seek bar", markers == 10,
              f"{markers} markers for 10 interactions")

        # ---- the question appears ---------------------------------------
        #
        # Playback has to be started rather than the playhead moved. The fork
        # shows a start screen and does nothing until somebody presses play —
        # which is correct, and means a test that only sets currentTime is
        # testing a player that was never running.
        started = page.evaluate(
            """() => {
                const splash = document.querySelector('.h5p-splash');
                if (splash) { splash.click(); return true; }
                const play = document.querySelector('.h5p-control.h5p-play');
                if (play) { play.click(); return true; }
                return false;
            }"""
        )
        check("the start screen could be pressed", started)

        # The first question is at 3s. Real playback, so this waits rather
        # than asserting immediately.
        try:
            page.wait_for_selector(".kaiiv-interaction", timeout=15000)
            shown = True
        except Exception:
            shown = False
        check("a question appeared when the playhead reached it", shown,
              "nothing with class kaiiv-interaction after 15s of playback")

        if shown:
            # Taken here, while the question is up. The one at the end is
            # taken after it has been answered and is gone, which is a picture
            # of a video rather than of the thing being tested.
            page.locator('[data-region="kaiiv"]').scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.screenshot(path="reports/kaiiv-question.png")
            print("  screenshot: reports/kaiiv-question.png (question on screen)")

            text = interaction_text(page)
            check("it is the question placed at 00:03",
                  "กล้อง" in text or "ผู้เรียนต้องทำ" in text, repr(text[:120]))

        stopped = page.evaluate(
            """() => {
                const v = document.querySelector('[data-region="stage"] video');
                return v ? {paused: v.paused, at: v.currentTime} : null;
            }"""
        )
        check("the video stopped at it",
              bool(stopped) and stopped["paused"] is True, str(stopped))
        check("and stopped at about 00:03",
              bool(stopped) and 2.5 <= stopped["at"] <= 6, str(stopped))

        # ---- answering it ------------------------------------------------
        #
        # The marker's accessible name, checked here because it is built from
        # two fields the fork reads and we supply, and getting either wrong
        # announces "Interaction. undefined" to a screen reader — which sounds
        # like a fault rather than a missing word, and which nobody looking at
        # the screen would ever notice.
        marker_label = page.evaluate(
            """() => {
                const m = document.querySelector('.h5p-seekbar-interaction');
                return m ? (m.getAttribute('aria-label') || '') : '';
            }"""
        )
        check("the seek bar markers are named for a screen reader",
              "undefined" not in marker_label and marker_label.strip() != "",
              repr(marker_label))

        # The question at 3s offers three options and the first is right.
        #
        # Waited for rather than clicked straight away: the seek above sent the
        # playhead back, and the fork redraws the interaction when it does, so
        # there is a moment where the card is on screen and its buttons are not.
        try:
            page.wait_for_selector('.kaiiv-interaction [data-option="0"]',
                                   timeout=10000)
        except Exception:
            pass

        clicked = page.evaluate(
            """() => {
                const button = document.querySelector(
                    '.kaiiv-interaction [data-option="0"]');
                if (!button) { return false; }
                button.click();
                return true;
            }"""
        )
        check("the question offered something to click", clicked)

        if clicked:
            try:
                page.wait_for_selector('.kaiiv-interaction [data-region="outcome"]'
                                       ':not([hidden])', timeout=10000)
                verdict = page.evaluate(
                    """() => {
                        const v = document.querySelector(
                            '.kaiiv-interaction [data-region="verdict"]');
                        return v ? v.innerText : '';
                    }"""
                )
            except Exception:
                verdict = ""
            check("the server's verdict came back and was shown",
                  verdict.strip() != "", repr(verdict))

            # It was the right option, so this question no longer blocks.
            # Moving to 5s — past it, before the next one at 8s — must stick.
            seek(page, 5)
            page.wait_for_timeout(800)
            at = page.evaluate(
                """() => {
                    const v = document.querySelector('[data-region="stage"] video');
                    return v ? v.currentTime : null;
                }"""
            )
            check("answering it lets the video past", at is not None and at > 4,
                  f"playhead came back to {at}")

        # ---- it cannot be skipped ---------------------------------------
        # Dragging far past the remaining questions must not get past them.
        # This is the case a crossing detector misses, and the reason the rule
        # is written as "at or past the point and unanswered" rather than as a
        # crossing.
        seek(page, 90)
        page.wait_for_timeout(900)
        after = page.evaluate(
            """() => {
                const v = document.querySelector('[data-region="stage"] video');
                const card = document.querySelector('.kaiiv-interaction');
                return {
                    at: v ? Number(v.currentTime.toFixed(1)) : null,
                    question: !!card,
                    paused: v ? v.paused : null
                };
            }"""
        )
        check("a question still blocks the way", after["question"], str(after))
        check("and the playhead was pulled back to it",
              after["at"] is not None and after["at"] < 30, str(after))

        # ---- the answer is not in the page ------------------------------
        html = page.content()
        for word in ANSWERS:
            check(f"the answer {word!r} is not in the DOM", word not in html)

        # And the question is, or the absences above mean nothing.
        check("the questions are in the DOM",
              "ข้อมูลใบหน้าถูกเก็บไว้ในรูปแบบใด" in html or shown)

        # ---- nothing threw ----------------------------------------------
        real = [e for e in console_errors
                if "favicon" not in e and "404" not in e]
        check("no JavaScript errors on the page", not real,
              "; ".join(real[:3]))

        page.screenshot(path="reports/kaiiv-browser-check.png", full_page=False)
        print("\n  screenshot: reports/kaiiv-browser-check.png")

        browser.close()

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for name in problems:
            print("  - " + name)
        return 1
    print("the player works in a browser")
    return 0


if __name__ == "__main__":
    sys.exit(main())
