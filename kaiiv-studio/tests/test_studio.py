"""What the studio promises, checked against the real engine.

Grouped by promise rather than by page: that answers never reach a page, that
marking cannot be got round, that people only reach what their role allows,
that what a teacher types cannot run as script — and that a teacher can
actually make a lesson with every kind of question on it without Moodle.
"""
from __future__ import annotations

import json
import re
import sqlite3

import pytest

from .conftest import FAKE_MP4, Browser

# The same ten the Moodle seed and the example server use, as the form sends them.
QUESTIONS = [
    {"type": "choice", "starttime": "3", "label": "Q1", "text": "Which is a capital?",
     "option0": "Lyon", "option1": "Paris", "correct1": "1", "option2": "Nice",
     "feedback": "Paris is the capital."},
    {"type": "truefalse", "starttime": "8", "text": "Water is wet.", "istrue": "1"},
    {"type": "multichoice", "starttime": "13", "text": "Pick the primes",
     "option0": "2", "correct0": "1", "option1": "4", "option2": "7", "correct2": "1"},
    {"type": "shorttext", "starttime": "18", "text": "Capital of Japan?", "accept": "Tokyo\nโตเกียว"},
    {"type": "blanks", "starttime": "23", "text": "Fill in",
     "lines": "The capital of *France/francia* is Paris"},
    {"type": "label", "starttime": "28", "text": "A note on screen"},
    {"type": "dragtext", "starttime": "33", "text": "Drag",
     "lines": "First *detect* then *compare*"},
    {"type": "marktheword", "starttime": "38", "text": "Mark the nouns",
     "passage": "the *cat* sat on the *mat*"},
    {"type": "image", "starttime": "43", "endtime": "48", "displaytype": "button", "label": "Diagram",
     "url": "https://example.com/diagram.png", "alt": "a diagram", "caption": "Steps"},
    {"type": "link", "starttime": "48", "endtime": "53", "displaytype": "button", "label": "Policy",
     "url": "https://example.com/policy", "linktitle": "Read the policy"},
]

# Words that are answers and nothing else in the lesson, and an explanation
# that is only shown once a question is answered. Not the drag-the-words
# words: those have to be sent, or there is nothing to drag — the engine
# withholds which word goes in which gap, and shuffles the bank.
SECRETS = ["francia", "Tokyo", "โตเกียว", "Paris is the capital."]


def make_lesson(teacher: Browser, published: bool = True, **extra) -> int:
    data = {"title": "Safety induction", "description": "d", "source": "upload",
            "mustanswer": "1", "allowreview": "1", "maxattempts": "0", **extra}
    if published:
        data["published"] = "1"
    response = teacher.post("/lessons/new", data, token_from="/lessons/new",
                            files={"videofile": ("lesson.mp4", FAKE_MP4, "video/mp4")})
    assert response.status_code == 303, response.text[:500]
    return int(re.search(r"/lessons/(\d+)/edit", response.headers["location"]).group(1))


def add(teacher: Browser, lesson: int, question: dict):
    return teacher.post(f"/lessons/{lesson}/interactions", question, token_from=f"/lessons/{lesson}/edit")


def rows(studio_db, sql, *args):
    con = sqlite3.connect(studio_db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


@pytest.fixture
def lesson_with_all(people):
    lesson = make_lesson(people["teacher"])
    for question in QUESTIONS:
        response = add(people["teacher"], lesson, question)
        assert response.status_code == 303, (question["type"], response.text[-800:])
    return lesson


def ids_by_type(tmp_path, lesson):
    return {r["type"]: r["id"] for r in rows(tmp_path / "studio.sqlite3",
                                               "SELECT id, type FROM interactions WHERE lesson_id = ?", lesson)}


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------

def test_the_first_administrator_comes_from_the_environment(studio):
    person = Browser(studio)
    assert person.login("admin", "wrong-password-1A").status_code == 401
    assert person.login("admin", "Admin-Pass-2345").status_code == 303
    assert "ผู้ใช้" in person.client.get("/").text


def test_signing_in_needs_the_form_token(studio):
    person = Browser(studio)
    response = person.client.post("/login", data={"username": "admin", "password": "Admin-Pass-2345"},
                                  follow_redirects=False)
    assert response.status_code == 403


def test_guessing_is_slowed_down(studio):
    person = Browser(studio)
    for _ in range(5):
        assert person.login("admin", "nope-Nope-1").status_code == 401
    # Right password, but too many wrong ones just before it.
    assert person.login("admin", "Admin-Pass-2345").status_code == 429


def test_a_deactivated_account_stops_working_at_its_next_click(people, tmp_path):
    learner = people["learner"]
    assert learner.client.get("/").status_code == 200
    target = rows(tmp_path / "studio.sqlite3", "SELECT id FROM users WHERE username = 'learner1'")[0]["id"]
    people["admin"].post(f"/users/{target}", {"action": "deactivate"}, token_from="/users")
    assert learner.client.get("/", follow_redirects=False).status_code == 303


def test_weak_passwords_are_refused(people, tmp_path):
    people["admin"].post("/users", {"username": "weak", "role": "learner", "password": "password"},
                         token_from="/users")
    assert not rows(tmp_path / "studio.sqlite3", "SELECT 1 FROM users WHERE username = 'weak'")


def test_an_administrator_cannot_lock_themselves_out(people, tmp_path):
    me = rows(tmp_path / "studio.sqlite3", "SELECT id FROM users WHERE username = 'admin'")[0]["id"]
    people["admin"].post(f"/users/{me}", {"action": "deactivate"}, token_from="/users")
    assert rows(tmp_path / "studio.sqlite3", "SELECT active FROM users WHERE id = ?", me)[0]["active"] == 1


# ---------------------------------------------------------------------------
# Authoring, without Moodle
# ---------------------------------------------------------------------------

def test_a_teacher_can_put_every_kind_on_a_lesson(lesson_with_all, tmp_path):
    stored = rows(tmp_path / "studio.sqlite3",
                  "SELECT type, pauses, graded, content, answers FROM interactions WHERE lesson_id = ?",
                  lesson_with_all)
    assert sorted(r["type"] for r in stored) == sorted(q["type"] for q in QUESTIONS)
    assert sum(r["graded"] for r in stored) == 7
    # The authored form, with the answers in asterisks, is never stored.
    for row in stored:
        assert "*" not in row["content"], row


def test_the_engines_own_words_reach_the_teacher(people):
    lesson = make_lesson(people["teacher"])
    response = add(people["teacher"], lesson, {"type": "choice", "starttime": "3", "text": "?",
                                               "option0": "a", "option1": "b"})
    assert response.status_code == 400
    assert "correct" in response.text  # the engine's "no option is marked correct"


def test_two_questions_at_the_same_moment_are_refused(people):
    lesson = make_lesson(people["teacher"])
    assert add(people["teacher"], lesson, QUESTIONS[1]).status_code == 303
    clash = {**QUESTIONS[1], "starttime": "8.2"}
    assert add(people["teacher"], lesson, clash).status_code == 400


def test_editing_shows_what_the_teacher_wrote(lesson_with_all, people, tmp_path):
    blanks = ids_by_type(tmp_path, lesson_with_all)["blanks"]
    page = people["teacher"].client.get(f"/lessons/{lesson_with_all}/edit?edit={blanks}").text
    assert "The capital of *France/francia* is Paris" in page


def test_an_edit_replaces_rather_than_adds(lesson_with_all, people, tmp_path):
    choice = ids_by_type(tmp_path, lesson_with_all)["choice"]
    response = add(people["teacher"], lesson_with_all, {**QUESTIONS[0], "id": str(choice),
                                                        "text": "Changed?"})
    assert response.status_code == 303
    stored = rows(tmp_path / "studio.sqlite3", "SELECT content FROM interactions WHERE type = 'choice'")
    assert len(stored) == 1 and "Changed?" in stored[0]["content"]


def test_only_videos_are_accepted(people):
    teacher = people["teacher"]
    for name, body in (("lesson.mp4", b"<html><script>alert(1)</script></html>"),
                       ("lesson.exe", FAKE_MP4)):
        response = teacher.post("/lessons/new", {"title": "x", "source": "upload"},
                                token_from="/lessons/new", files={"videofile": (name, body, "video/mp4")})
        assert response.status_code == 400, name


def test_youtube_and_vimeo_addresses_are_read(people, tmp_path):
    teacher = people["teacher"]
    for source, address, videoid in (("youtube", "https://www.youtube.com/watch?v=aqz-KE-bpKQ", "aqz-KE-bpKQ"),
                                     ("vimeo", "https://vimeo.com/76979871", "76979871")):
        response = teacher.post("/lessons/new", {"title": source, "source": source, "address": address},
                                token_from="/lessons/new")
        assert response.status_code == 303
    stored = {r["provider"]: r["videoid"] for r in rows(tmp_path / "studio.sqlite3",
                                                          "SELECT provider, videoid FROM lessons")}
    assert stored == {"youtube": "aqz-KE-bpKQ", "vimeo": "76979871"}


# ---------------------------------------------------------------------------
# The answers never reach a page
# ---------------------------------------------------------------------------

def test_no_answer_is_in_the_lesson_page(lesson_with_all, people):
    page = people["learner"].client.get(f"/lessons/{lesson_with_all}").text
    assert "Which is a capital?" in page  # the questions are there
    for word in SECRETS:
        assert word not in page, word
    config = json.loads(re.search(r'id="lesson-config" type="application/json">(.*?)</script>',
                                  page, re.S).group(1))
    assert len(config["items"]) == 10
    assert all("answers" not in item or not item["answers"] for item in config["items"])


def test_there_is_no_endpoint_that_hands_out_a_timeline(lesson_with_all, people):
    for path in (f"/api/lessons/{lesson_with_all}/timeline", f"/api/lessons/{lesson_with_all}"):
        assert people["learner"].client.get(path).status_code in (404, 405)


# ---------------------------------------------------------------------------
# Marking cannot be got round
# ---------------------------------------------------------------------------

def test_a_wrong_answer_reveals_nothing_while_a_retry_is_left(lesson_with_all, people, tmp_path):
    choice = ids_by_type(tmp_path, lesson_with_all)["choice"]
    learner = people["learner"]
    wrong = learner.api(f"/api/lessons/{lesson_with_all}/answer",
                        {"interaction": choice, "response": [0]}, f"/lessons/{lesson_with_all}").json()
    assert wrong == {"ok": True, "correct": False, "revealed": False, "may_retry": True,
                     "attempts": 1, "answers": [], "feedback": ""}
    right = learner.api(f"/api/lessons/{lesson_with_all}/answer",
                        {"interaction": choice, "response": [1]}, f"/lessons/{lesson_with_all}").json()
    assert right["correct"] is True and right["revealed"] is True
    assert "Paris is the capital." in right["feedback"]
    assert "store" not in right


def test_a_correct_answer_cannot_be_answered_again(lesson_with_all, people, tmp_path):
    choice = ids_by_type(tmp_path, lesson_with_all)["choice"]
    learner = people["learner"]
    learner.api(f"/api/lessons/{lesson_with_all}/answer", {"interaction": choice, "response": [1]},
                f"/lessons/{lesson_with_all}")
    again = learner.api(f"/api/lessons/{lesson_with_all}/answer", {"interaction": choice, "response": [0]},
                        f"/lessons/{lesson_with_all}").json()
    assert again == {"ok": False, "error": "already_correct"}


def test_no_answer_is_marked_after_the_last_attempt(people, tmp_path):
    teacher, learner = people["teacher"], people["learner"]
    lesson = make_lesson(teacher, maxattempts="1")
    add(teacher, lesson, QUESTIONS[1])
    truefalse = ids_by_type(tmp_path, lesson)["truefalse"]
    first = learner.api(f"/api/lessons/{lesson}/answer", {"interaction": truefalse, "response": False},
                        f"/lessons/{lesson}").json()
    assert first["correct"] is False and first["may_retry"] is False
    second = learner.api(f"/api/lessons/{lesson}/answer", {"interaction": truefalse, "response": True},
                         f"/lessons/{lesson}").json()
    assert second == {"ok": False, "error": "no_attempts_left"}
    assert len(rows(tmp_path / "studio.sqlite3", "SELECT 1 FROM responses")) == 1


def test_answering_needs_the_page_token(lesson_with_all, people, tmp_path):
    choice = ids_by_type(tmp_path, lesson_with_all)["choice"]
    response = people["learner"].client.post(f"/api/lessons/{lesson_with_all}/answer",
                                             json={"interaction": choice, "response": [1]})
    assert response.status_code == 403


def test_an_answer_to_another_lessons_question_is_refused(lesson_with_all, people, tmp_path):
    other = make_lesson(people["teacher"])
    choice = ids_by_type(tmp_path, lesson_with_all)["choice"]
    response = people["learner"].api(f"/api/lessons/{other}/answer", {"interaction": choice, "response": [1]},
                                     f"/lessons/{other}")
    assert response.status_code == 404


def test_the_score_counts_questions_not_captions(lesson_with_all, people, tmp_path):
    ids = ids_by_type(tmp_path, lesson_with_all)
    learner = people["learner"]
    learner.api(f"/api/lessons/{lesson_with_all}/answer", {"interaction": ids["choice"], "response": [1]},
                f"/lessons/{lesson_with_all}")
    learner.api(f"/api/lessons/{lesson_with_all}/answer", {"interaction": ids["shorttext"],
                                                           "response": " tokyo "},
                f"/lessons/{lesson_with_all}")
    score = learner.client.get(f"/api/lessons/{lesson_with_all}/score").json()
    assert score == {"ok": True, "correct": 2, "total": 7, "fraction": pytest.approx(2 / 7)}


# ---------------------------------------------------------------------------
# People reach only what their role allows
# ---------------------------------------------------------------------------

def test_a_learner_cannot_reach_the_teaching_pages(lesson_with_all, people, tmp_path):
    learner = people["learner"]
    choice = ids_by_type(tmp_path, lesson_with_all)["choice"]
    for path in (f"/lessons/{lesson_with_all}/edit", f"/lessons/{lesson_with_all}/report",
                 f"/lessons/{lesson_with_all}/report.csv", f"/lessons/{lesson_with_all}/settings",
                 "/lessons/new", "/users"):
        assert learner.client.get(path).status_code == 403, path
    # Nor post to them with a token taken from a page they can reach.
    response = learner.post(f"/lessons/{lesson_with_all}/interactions/{choice}/delete", {},
                            token_from="/")
    assert response.status_code == 403


def test_a_teacher_cannot_manage_people(people):
    assert people["teacher"].client.get("/users").status_code == 403


def test_a_draft_is_invisible_to_learners(people):
    lesson = make_lesson(people["teacher"], published=False)
    learner = people["learner"]
    assert learner.client.get(f"/lessons/{lesson}").status_code == 403
    assert f"/lessons/{lesson}\"" not in learner.client.get("/").text


def test_videos_are_served_only_to_people_signed_in(people, tmp_path):
    lesson = make_lesson(people["teacher"], published=False)
    media = rows(tmp_path / "studio.sqlite3", "SELECT mediafile FROM lessons WHERE id = ?",
                 lesson)[0]["mediafile"]
    assert Browser(people["teacher"].client.app).client.get(
        f"/media/{media}", follow_redirects=False).status_code == 303
    assert people["learner"].client.get(f"/media/{media}").status_code == 404
    teacher_copy = people["teacher"].client.get(f"/media/{media}", headers={"Range": "bytes=0-99"})
    assert teacher_copy.status_code == 206 and len(teacher_copy.content) == 100


# ---------------------------------------------------------------------------
# What a teacher types cannot run as script
# ---------------------------------------------------------------------------

def test_question_text_is_shown_as_text(people, tmp_path):
    teacher = people["teacher"]
    lesson = make_lesson(teacher)
    add(teacher, lesson, {**QUESTIONS[1], "text": "<script>alert(1)</script>",
                          "feedback": "<img src=x onerror=alert(2)>"})
    page = people["learner"].client.get(f"/lessons/{lesson}").text
    assert "<script>alert(1)" not in page
    assert "<img src=x" not in page
    # Stored as text for an HTML context, which is where the player puts both.
    stored = rows(tmp_path / "studio.sqlite3", "SELECT content, feedback FROM interactions")[0]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in stored["content"]
    assert stored["feedback"] == "&lt;img src=x onerror=alert(2)&gt;"


def test_a_script_link_is_refused(people):
    teacher = people["teacher"]
    lesson = make_lesson(teacher)
    response = add(teacher, lesson, {**QUESTIONS[9], "url": "javascript:alert(1)"})
    assert response.status_code == 400


def test_a_spreadsheet_formula_in_a_name_is_neutralised(people, lesson_with_all):
    people["admin"].post("/users", {"username": "sneaky", "name": "=HYPERLINK(\"x\")", "role": "learner",
                                    "password": "Good-Pass-2345"}, token_from="/users")
    csv = people["teacher"].client.get(f"/lessons/{lesson_with_all}/report.csv").text
    assert "'=HYPERLINK" in csv


# ---------------------------------------------------------------------------
# Progress and reports
# ---------------------------------------------------------------------------

def test_progress_keeps_the_furthest_point(lesson_with_all, people, tmp_path):
    learner = people["learner"]
    page = f"/lessons/{lesson_with_all}"
    learner.api(f"/api/lessons/{lesson_with_all}/progress", {"position": 30}, page)
    learner.api(f"/api/lessons/{lesson_with_all}/progress", {"position": 12}, page)
    # The beacon's way: the token in the body.
    token = learner.csrf(page)
    learner.client.post(f"/api/lessons/{lesson_with_all}/progress",
                        json={"position": 40, "finished": True, "csrf": token})
    stored = rows(tmp_path / "studio.sqlite3", "SELECT furthest, finished FROM progress")[0]
    assert stored == {"furthest": 40.0, "finished": 1}


def test_the_report_shows_each_learner(lesson_with_all, people, tmp_path):
    ids = ids_by_type(tmp_path, lesson_with_all)
    people["learner"].api(f"/api/lessons/{lesson_with_all}/answer",
                          {"interaction": ids["choice"], "response": [1]}, f"/lessons/{lesson_with_all}")
    page = people["teacher"].client.get(f"/lessons/{lesson_with_all}/report").text
    row = re.search(r'data-username="learner1">(.*?)</tr>', page, re.S).group(1)
    assert "1 / 7" in row
    other = re.search(r'data-username="learner2">(.*?)</tr>', page, re.S).group(1)
    assert "0 / 7" in other


# ---------------------------------------------------------------------------
# When the engine is down
# ---------------------------------------------------------------------------

def test_a_lesson_is_not_played_without_its_questions(lesson_with_all, people, monkeypatch):
    from app import engine
    monkeypatch.setattr(engine, "post", lambda *a, **k: {"ok": False, "error": "unreachable"})
    response = people["learner"].client.get(f"/lessons/{lesson_with_all}")
    assert response.status_code == 503
    assert "kaiiv-player.js" not in response.text
    assert "unreachable" not in response.text  # a learner is not told the cause
    assert "unreachable" in people["teacher"].client.get(f"/lessons/{lesson_with_all}").text
