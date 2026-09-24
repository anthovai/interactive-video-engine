"""The studio used the way a customer uses it, in a real browser, on a running
stack — nothing created behind its back.

    KAIIV_ADMIN_PASSWORD=... python kaiiv-studio/tests/browser_e2e.py <video.mp4> [base-url]

  1. the administrator signs in and adds a teacher and a learner
  2. the teacher creates a lesson, uploading the video through the form
  3. the teacher puts one of every kind of question on it, through the
     editor, taking one of the times from the preview with "use this time"
  4. prints the lesson's address and the learner's sign-in for
     moodle/plugins/mod_kaiiv/tests/browser_types.py to answer everything
     as the learner — the same walk that runs against Moodle

The questions are the ones kaiiv-player/examples/server/seed.js makes, which
are the ones browser_types.py knows the answers to.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import secrets
import subprocess
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

VIDEO = sys.argv[1] if len(sys.argv) > 1 else ""
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8300"
ADMIN = os.environ.get("KAIIV_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("KAIIV_ADMIN_PASSWORD", "")
ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED = ROOT / "kaiiv-player/examples/server/seed.js"

if not VIDEO or not pathlib.Path(VIDEO).exists() or not ADMIN_PASSWORD:
    sys.exit(__doc__)

problems: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        problems.append(name)
    return ok


def seed_items() -> list[dict]:
    """The ITEMS array from seed.js, read by node rather than re-typed here.

    Evaluated because it is a JavaScript literal, not JSON — and it is this
    repository's own file, not input from anywhere else.
    """
    script = ("const s=require('fs').readFileSync(process.argv[1],'utf8');"
              "const i=s.indexOf('const ITEMS = ');"
              "const body=s.slice(i+14, s.indexOf('];', i)+1);"
              "process.stdout.write(JSON.stringify(eval(body)));")
    out = subprocess.run(["node", "-e", script, str(SEED)], capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    return json.loads(out)


def sign_in(page, username: str, password: str) -> None:
    page.goto(f"{BASE}/login")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#loginbtn")
    page.wait_for_load_state("networkidle")


def fill_question(page, item: dict) -> None:
    """One question, through the editor's form, as a teacher fills it in."""
    a = item["authored"]
    page.select_option("#type", item["type"])
    page.fill("#starttime", str(item["start"]))
    page.fill("#label", item.get("label", ""))
    if page.locator("#text").is_visible():
        page.fill("#text", re.sub(r"<[^>]+>", "", a.get("text", "")))
    for index, option in enumerate(a.get("options", [])):
        page.fill(f"#option{index}", option["text"])
        if option["correct"]:
            page.check(f"#correct{index}")
    if item["type"] == "truefalse":
        page.select_option("#istrue", "1" if a["correct"] else "0")
    if "accept" in a:
        page.fill("#accept", "\n".join(a["accept"]))
    if "lines" in a:
        page.fill("#lines", "\n".join(a["lines"]))
    if "passage" in a:
        page.fill("#passage", a["passage"])
    if item["type"] in ("image", "link"):
        # The seed's image is a path on the example server; here, one this
        # site serves to anybody.
        page.fill("#url", "/player/images/Oval.svg" if item["type"] == "image" else a["url"])
    if "alt" in a:
        page.fill("#alt", a["alt"])
    if "caption" in a:
        page.fill("#caption", a["caption"])
    if item["type"] == "link":
        page.fill("#linktitle", a["title"])
    if item.get("feedback") and page.locator("#feedback").is_visible():
        page.fill("#feedback", item["feedback"])
    if item.get("display") or item.get("end"):
        page.locator("details[data-types] summary").click()
        if item.get("display"):
            page.select_option("#displaytype", item["display"])
        if item.get("end"):
            page.fill("#endtime", str(item["end"]))


def main() -> int:
    learner = "learner" + secrets.token_hex(3)
    teacher = "teacher" + secrets.token_hex(3)
    password = "Lp" + secrets.token_urlsafe(10) + "7q"
    items = seed_items()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        errors: list[str] = []

        # ---- 1. people -------------------------------------------------------
        print("administrator")
        page = browser.new_context().new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        sign_in(page, ADMIN, ADMIN_PASSWORD)
        check("signed in", page.url.rstrip("/") == BASE.rstrip("/"), page.url)
        page.goto(f"{BASE}/users")
        for username, role in ((teacher, "teacher"), (learner, "learner")):
            page.fill("#new-username", username)
            page.fill("#new-name", username)
            page.select_option("#new-role", role)
            page.fill("#new-password", password)
            page.click("#createuser")
            page.wait_for_load_state("networkidle")
            check(f"added {role} {username}",
                  page.locator(f'tr[data-username="{username}"]').count() == 1)
        page.context.close()

        # ---- 2. the lesson ---------------------------------------------------
        print("teacher")
        page = browser.new_context().new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        sign_in(page, teacher, password)
        page.goto(f"{BASE}/lessons/new")
        page.fill("#title", "บทเรียนทดลอง")
        page.set_input_files("#videofile", VIDEO)
        page.check("#published")
        page.click("#savelesson")
        page.wait_for_load_state("networkidle")
        match = re.search(r"/lessons/(\d+)/edit", page.url)
        if not check("lesson created with the uploaded video", bool(match), page.url):
            page.screenshot(path="reports/studio-lesson-failed.png", full_page=True)
            return 1
        lesson = match.group(1)
        duration = page.evaluate("""() => new Promise((ok) => {
            const v = document.getElementById('preview');
            if (v.readyState >= 1) return ok(v.duration);
            v.addEventListener('loadedmetadata', () => ok(v.duration), {once: true});
            setTimeout(() => ok(-1), 15000);
        })""")
        check("the uploaded video plays in the editor", duration > 40, str(duration))

        # ---- 3. every kind of question, through the form ---------------------
        for position, item in enumerate(items):
            page.goto(f"{BASE}/lessons/{lesson}/edit")
            fill_question(page, item)
            if position == 0:
                # The button a teacher uses: stop the preview on the frame, take its time.
                page.evaluate(f"() => {{ const v = document.getElementById('preview');"
                              f" v.currentTime = {item['start']}; }}")
                page.wait_for_function(
                    f"() => Math.abs(document.getElementById('preview').currentTime - {item['start']}) < 0.2")
                page.fill("#starttime", "")
                page.click("#usetime")
                check("  'use this time' took the time from the preview",
                      page.input_value("#starttime") == str(float(item["start"])).rstrip("0").rstrip("."),
                      page.input_value("#starttime"))
            page.click("#saveinteraction")
            page.wait_for_load_state("networkidle")
            saved = page.locator(".notice.success").count() > 0
            check(f"{item['type']} at {item['start']}s saved through the editor", saved,
                  (page.locator('[data-region="formerror"]').inner_text()
                   if page.locator('[data-region="formerror"]').count() else page.url))
        page.goto(f"{BASE}/lessons/{lesson}/edit")
        page.screenshot(path="reports/studio-editor.png", full_page=True)
        check("all ten are on the timeline",
              page.locator('[data-region="timeline"] tr').count() == len(items))
        page.context.close()
        browser.close()

    check("no JavaScript errors on the teacher's pages", not errors, "; ".join(errors[:3]))

    print()
    print(f"lesson   {BASE}/lessons/{lesson}")
    print(f"learner  {learner}")
    print(f"teacher  {teacher}")
    # For the next step, and for the caller's shell only.
    pathlib.Path("reports/studio-e2e.json").write_text(json.dumps(
        {"lesson": lesson, "learner": learner, "teacher": teacher, "password": password}))
    if problems:
        print(f"\n{len(problems)} problem(s)")
        return 1
    print("\na teacher made a lesson with every kind of question, without Moodle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
