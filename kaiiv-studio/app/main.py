"""KAISER Interactive Video Studio.

A complete, small system for interactive video lessons that needs no Moodle:
teachers upload a video and put questions on it, learners watch and answer,
teachers see the scores. The player is kaiiv-player; the marking is
kaiiv-service. This is the part in between — the record, the people, and the
screens — that a host system would otherwise have to supply.

    uvicorn app.main:app

Three rules hold everywhere below, and they are the reason this is safe to
give to a class that would rather not be tested:

  - the engine's key is here and nowhere else; pages never call the engine
  - the answers column is read only to hand it to the engine
  - a page gets the timeline the engine chose for this learner, built into the
    page on the server; there is no endpoint a page can ask for one from
"""
from __future__ import annotations

import csv
import io
import json
import logging
import pathlib
import secrets
from typing import Any

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import authoring, config, db, engine, security

log = logging.getLogger("kaiiv.studio")

HERE = pathlib.Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))
throttle = security.Throttle()

VIDEO_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm"}


class Denied(Exception):
    """Raised by the checks below; turned into a redirect or a 403."""

    def __init__(self, status: int = 403):
        self.status = status


def create_app(settings: dict[str, str] | None = None, engine_client=None,
               database=None) -> FastAPI:
    """Build the app. Arguments are for the tests; in production everything
    comes from the environment."""
    settings = settings or config.load()
    engine.configure(settings["api_key"], engine_client)
    db.init(database)
    (config.DATA_DIR / "media").mkdir(parents=True, exist_ok=True)
    _first_admin(settings)

    app = FastAPI(title="KAISER Interactive Video Studio", docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=settings["secret"],
                       session_cookie="kaiiv_session", max_age=config.SESSION_HOURS * 3600,
                       same_site="lax", https_only=config.SECURE_COOKIES)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.exception_handler(Denied)
    async def denied(request: Request, error: Denied):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=error.status)
        if error.status == 401:
            return RedirectResponse("/login", status_code=303)
        if error.status == 404:
            return page(request, "error.html", {"message": "ไม่พบหน้าที่ต้องการ"}, status=404)
        if error.status == 400:
            return page(request, "error.html", {"message": "คำขอไม่ถูกต้อง"}, status=400)
        return page(request, "error.html", {"message": "คุณไม่มีสิทธิ์เข้าหน้านี้ หรือหน้านี้หมดอายุแล้ว "
                                                       "ลองโหลดใหม่"}, status=403)

    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    if config.PLAYER_DIR.exists():
        app.mount("/player", StaticFiles(directory=str(config.PLAYER_DIR)), name="player")
    else:
        log.error("the player is not at %s; lessons will not play", config.PLAYER_DIR)

    _routes(app)
    return app


def _first_admin(settings: dict[str, str]) -> None:
    """The first administrator, from the environment, once."""
    with db.connect() as con:
        if con.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        password = settings["admin_password"]
        if not password:
            log.warning("no users yet: set KAIIV_ADMIN_PASSWORD to create the first administrator")
            return
        problem = security.password_problem(password)
        if problem:
            log.error("KAIIV_ADMIN_PASSWORD is not usable: %s", problem)
            return
        con.execute(
            "INSERT INTO users (username, name, role, password_hash, created) VALUES (?, ?, 'admin', ?, ?)",
            (settings["admin_user"], "ผู้ดูแลระบบ", security.hash_password(password), db.now()))
        log.info("created administrator %s", settings["admin_user"])


# ---------------------------------------------------------------------------
# Who is asking
# ---------------------------------------------------------------------------

def current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with db.connect() as con:
        row = con.execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()
    if not row:
        request.session.clear()
        return None
    return dict(row)


def require(request: Request, *roles: str) -> dict:
    user = current_user(request)
    if not user:
        raise Denied(401)
    if roles and user["role"] not in roles:
        raise Denied(403)
    return user


def check_csrf(request: Request, given: str | None) -> None:
    if not security.csrf_ok(request.session, given):
        raise Denied(403)


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = security.new_csrf()
    return request.session["csrf"]


def flash(request: Request, message: str, kind: str = "success") -> None:
    request.session.setdefault("flash", []).append({"message": message, "kind": kind})


def page(request: Request, template: str, context: dict | None = None, status: int = 200):
    context = dict(context or {})
    context.update({
        "user": current_user(request),
        "csrf": csrf_token(request),
        "messages": request.session.pop("flash", []),
        "type_labels": authoring.TYPE_LABELS,
    })
    return templates.TemplateResponse(request, template, context, status_code=status)


def lesson_or_404(con, lesson_id: int) -> dict:
    row = con.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not row:
        raise Denied(404)
    return dict(row)


def may_view(user: dict, lesson: dict) -> bool:
    return bool(lesson["published"]) or user["role"] in security.TEACHING


def rules_of(lesson: dict) -> dict[str, Any]:
    return {"allowreview": bool(lesson["allowreview"]), "maxattempts": int(lesson["maxattempts"])}


def video_of(lesson: dict) -> dict[str, str]:
    if lesson["mediafile"]:
        return {"provider": "file", "src": f"/media/{lesson['mediafile']}", "videoid": ""}
    return {"provider": lesson["provider"], "src": lesson["src"], "videoid": lesson["videoid"]}


def client_address(request: Request) -> str:
    return request.client.host if request.client else "?"


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

def _looks_like_video(head: bytes, suffix: str) -> bool:
    """The first bytes, not the name. A file called lesson.mp4 that is an HTML
    page is an HTML page served from this site."""
    if suffix in (".mp4", ".m4v"):
        return len(head) >= 12 and head[4:8] == b"ftyp"
    if suffix == ".webm":
        return head[:4] == b"\x1a\x45\xdf\xa3"
    return False


async def save_upload(upload: UploadFile) -> str:
    suffix = pathlib.Path(upload.filename or "").suffix.lower()
    if suffix not in VIDEO_TYPES:
        raise authoring.FormProblem("รับเฉพาะไฟล์ .mp4 หรือ .webm")
    name = f"{secrets.token_hex(16)}{suffix}"
    target = config.DATA_DIR / "media" / name
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    head = b""
    try:
        with open(target, "wb") as out:
            while chunk := await upload.read(1024 * 1024):
                if not head:
                    head = chunk[:16]
                written += len(chunk)
                if written > limit:
                    raise authoring.FormProblem(f"ไฟล์ใหญ่เกิน {config.MAX_UPLOAD_MB} MB")
                out.write(chunk)
        if not _looks_like_video(head, suffix):
            raise authoring.FormProblem("ไฟล์นี้ไม่ใช่วิดีโอ MP4 หรือ WebM")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return name


def remove_media(name: str) -> None:
    if name:
        (config.DATA_DIR / "media" / name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _routes(app: FastAPI) -> None:

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # ---- signing in ------------------------------------------------------

    @app.get("/login")
    def login_form(request: Request):
        if current_user(request):
            return RedirectResponse("/", status_code=303)
        with db.connect() as con:
            empty = not con.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return page(request, "login.html", {"no_users": empty})

    @app.post("/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""),
              csrf: str = Form("")):
        check_csrf(request, csrf)
        address = client_address(request)
        if throttle.blocked(username, address):
            return page(request, "login.html",
                        {"error": "ลองผิดหลายครั้งเกินไป รอ 15 นาทีแล้วลองใหม่", "username": username},
                        status=429)
        with db.connect() as con:
            row = con.execute("SELECT * FROM users WHERE username = ? AND active = 1",
                              (username.strip(),)).fetchone()
        if not row or not security.check_password(password, row["password_hash"]):
            throttle.failed(username, address)
            return page(request, "login.html",
                        {"error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "username": username}, status=401)
        throttle.succeeded(username)
        # A new session on sign-in, so a session id someone planted before
        # does not become a signed-in one.
        request.session.clear()
        request.session["user_id"] = row["id"]
        request.session["csrf"] = security.new_csrf()
        return RedirectResponse("/", status_code=303)

    @app.post("/logout")
    def logout(request: Request, csrf: str = Form("")):
        check_csrf(request, csrf)
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/account")
    def account(request: Request):
        require(request)
        return page(request, "account.html")

    @app.post("/account")
    def change_password(request: Request, current: str = Form(""), new: str = Form(""),
                        csrf: str = Form("")):
        user = require(request)
        check_csrf(request, csrf)
        if not security.check_password(current, user["password_hash"]):
            return page(request, "account.html", {"error": "รหัสผ่านปัจจุบันไม่ถูกต้อง"}, status=400)
        problem = security.password_problem(new)
        if problem:
            return page(request, "account.html", {"error": problem}, status=400)
        with db.connect() as con:
            con.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                        (security.hash_password(new), user["id"]))
        flash(request, "เปลี่ยนรหัสผ่านแล้ว")
        return RedirectResponse("/account", status_code=303)

    # ---- home ------------------------------------------------------------

    @app.get("/")
    def home(request: Request):
        user = require(request)
        teaching = user["role"] in security.TEACHING
        with db.connect() as con:
            if teaching:
                lessons = con.execute(
                    """SELECT l.*, (SELECT COUNT(*) FROM interactions i WHERE i.lesson_id = l.id) AS items
                         FROM lessons l ORDER BY l.updated DESC""").fetchall()
            else:
                lessons = con.execute(
                    """SELECT l.*, p.furthest, p.finished,
                              (SELECT COUNT(*) FROM interactions i WHERE i.lesson_id = l.id) AS items
                         FROM lessons l LEFT JOIN progress p ON p.lesson_id = l.id AND p.user_id = ?
                        WHERE l.published = 1 ORDER BY l.title""", (user["id"],)).fetchall()
        return page(request, "home.html", {"lessons": [dict(r) for r in lessons], "teaching": teaching})

    # ---- lessons ---------------------------------------------------------

    @app.get("/lessons/new")
    def lesson_new(request: Request):
        require(request, *security.TEACHING)
        return page(request, "lesson_form.html", {"lesson": None, "form": {"source": "upload",
                    "mustanswer": True, "allowreview": True, "maxattempts": 0}})

    async def _save_lesson(request: Request, lesson: dict | None):
        user = require(request, *security.TEACHING)
        form = await request.form()
        check_csrf(request, form.get("csrf"))
        values = {key: form.get(key) for key in form.keys() if key != "videofile"}
        title = str(form.get("title", "")).strip()
        source = str(form.get("source", "upload"))
        try:
            if not title:
                raise authoring.FormProblem("ใส่ชื่อบทเรียน")
            maxattempts = int(form.get("maxattempts") or 0)
            if not 0 <= maxattempts <= 20:
                raise authoring.FormProblem("จำนวนครั้งที่ตอบได้ต้องอยู่ระหว่าง 0 ถึง 20")
            upload = form.get("videofile")
            mediafile = lesson["mediafile"] if lesson else ""
            video = None
            if source == "upload":
                if upload is not None and getattr(upload, "filename", ""):
                    new_file = await save_upload(upload)
                    video = {"provider": "file", "src": "", "videoid": "", "mediafile": new_file}
                elif mediafile:
                    video = {"provider": "file", "src": "", "videoid": "", "mediafile": mediafile}
                else:
                    raise authoring.FormProblem("เลือกไฟล์วิดีโอที่จะอัปโหลด")
            else:
                video = {**authoring.video_source(source, str(form.get("address", ""))),
                         "mediafile": ""}
        except (authoring.FormProblem, ValueError) as problem:
            return page(request, "lesson_form.html",
                        {"lesson": lesson, "form": values, "error": str(problem)}, status=400)

        fields = (title, str(form.get("description", "")).strip(), video["provider"], video["src"],
                  video["videoid"], video["mediafile"], 1 if form.get("mustanswer") else 0,
                  1 if form.get("allowreview") else 0, maxattempts,
                  1 if form.get("published") else 0, db.now())
        with db.connect() as con:
            if lesson:
                con.execute(
                    """UPDATE lessons SET title=?, description=?, provider=?, src=?, videoid=?,
                       mediafile=?, mustanswer=?, allowreview=?, maxattempts=?, published=?, updated=?
                       WHERE id=?""", fields + (lesson["id"],))
                lesson_id = lesson["id"]
            else:
                cursor = con.execute(
                    """INSERT INTO lessons (title, description, provider, src, videoid, mediafile,
                       mustanswer, allowreview, maxattempts, published, updated, created_by, created)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", fields + (user["id"], db.now()))
                lesson_id = cursor.lastrowid
        if lesson and lesson["mediafile"] and lesson["mediafile"] != video["mediafile"]:
            remove_media(lesson["mediafile"])
        flash(request, "บันทึกบทเรียนแล้ว")
        return RedirectResponse(f"/lessons/{lesson_id}/edit", status_code=303)

    @app.post("/lessons/new")
    async def lesson_create(request: Request):
        return await _save_lesson(request, None)

    @app.get("/lessons/{lesson_id}/settings")
    def lesson_settings(request: Request, lesson_id: int):
        require(request, *security.TEACHING)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
        source = "upload" if lesson["mediafile"] else (
            "url" if lesson["provider"] in ("file", "hls") else lesson["provider"])
        address = lesson["src"] if source == "url" else (
            ("https://youtu.be/" + lesson["videoid"]) if source == "youtube" else
            ("https://vimeo.com/" + lesson["videoid"].replace(":", "/")) if source == "vimeo" else "")
        return page(request, "lesson_form.html", {"lesson": lesson, "form": {
            **lesson, "source": source, "address": address}})

    @app.post("/lessons/{lesson_id}/settings")
    async def lesson_update(request: Request, lesson_id: int):
        require(request, *security.TEACHING)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
        return await _save_lesson(request, lesson)

    @app.post("/lessons/{lesson_id}/delete")
    def lesson_delete(request: Request, lesson_id: int, csrf: str = Form("")):
        require(request, *security.TEACHING)
        check_csrf(request, csrf)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
            con.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        remove_media(lesson["mediafile"])
        flash(request, f"ลบบทเรียน “{lesson['title']}” แล้ว")
        return RedirectResponse("/", status_code=303)

    # ---- authoring ---------------------------------------------------------

    def _editor(request: Request, lesson: dict, form: dict | None, error: str | None = None,
                status: int = 200):
        with db.connect() as con:
            rows = [dict(r) for r in con.execute(
                """SELECT i.*, (SELECT COUNT(*) FROM responses r WHERE r.interaction_id = i.id) AS answered
                     FROM interactions i WHERE lesson_id = ? ORDER BY start, id""",
                (lesson["id"],)).fetchall()]
        catalogue = engine.types()
        kinds = [entry["type"] for entry in catalogue.get("types", [])] if catalogue.get("ok") else []
        for row in rows:
            content = json.loads(row["content"])
            row["summary"] = authoring.from_html(content.get("text", "")) or content.get(
                "caption", "") or content.get("title", "") or content.get("url", "")
        return page(request, "editor.html", {
            "lesson": lesson, "video": video_of(lesson), "rows": rows, "kinds": kinds,
            "engine_down": not catalogue.get("ok"), "form": form or {"type": "choice"},
            "error": error, "max_options": authoring.MAX_OPTIONS,
        }, status=status)

    @app.get("/lessons/{lesson_id}/edit")
    def editor(request: Request, lesson_id: int, edit: int = 0):
        require(request, *security.TEACHING)
        form = None
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
            if edit:
                row = con.execute("SELECT * FROM interactions WHERE id = ? AND lesson_id = ?",
                                  (edit, lesson_id)).fetchone()
                if not row:
                    raise Denied(404)
                form = authoring.prefill(dict(row), json.loads(row["content"]),
                                         json.loads(row["answers"]))
        return _editor(request, lesson, form)

    @app.post("/lessons/{lesson_id}/interactions")
    async def interaction_save(request: Request, lesson_id: int):
        require(request, *security.TEACHING)
        form = dict((await request.form()).items())
        check_csrf(request, form.get("csrf"))
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
        existing = int(form.get("id") or 0)
        try:
            where = authoring.placement(form)
            kind = str(form.get("type", ""))
            written = authoring.authored(form)
        except authoring.FormProblem as problem:
            return _editor(request, lesson, form, str(problem), status=400)

        split = engine.author(kind, written)
        if not split.get("ok"):
            # The engine's own words when it has them: "no option is marked
            # correct" is something a teacher can fix.
            message = split.get("detail") or split.get("error") or "บันทึกไม่ได้"
            if split.get("error") in ("unreachable", "bad_key", "malformed"):
                message = "ติดต่อเครื่องยนต์ตรวจคำตอบไม่ได้ (" + split["error"] + ") ยังไม่ได้บันทึก"
            return _editor(request, lesson, form, message, status=400)

        pauses = bool(split.get("pauses"))
        graded = bool(split.get("graded"))
        with db.connect() as con:
            known = not existing or con.execute(
                "SELECT 1 FROM interactions WHERE id = ? AND lesson_id = ?",
                (existing, lesson_id)).fetchone()
            clash = pauses and con.execute(
                """SELECT 1 FROM interactions WHERE lesson_id = ? AND pauses = 1
                   AND start > ? AND start < ? AND id <> ?""",
                (lesson_id, where["start"] - authoring.MIN_GAP, where["start"] + authoring.MIN_GAP,
                 existing)).fetchone()
        # Outside the connection: the editor page opens its own, and the lock
        # that serialises them is not re-entrant.
        if not known:
            raise Denied(404)
        if clash:
            return _editor(request, lesson, form,
                           "มีคำถามอื่นอยู่ใกล้เวลานี้เกินไป เลื่อนให้ห่างกันอย่างน้อยครึ่งวินาที",
                           status=400)
        with db.connect() as con:
            values = (kind, where["start"], authoring.window_end(where["start"], where["end"], pauses),
                      "poster" if graded and pauses else where["display"], 1 if pauses else 0,
                      1 if graded else 0, where["x"], where["y"], where["width"], where["height"],
                      where["label"], json.dumps(split["content"], ensure_ascii=False),
                      json.dumps(split["answers"], ensure_ascii=False), where["feedback"])
            if existing:
                con.execute(
                    """UPDATE interactions SET type=?, start=?, end=?, display=?, pauses=?, graded=?,
                       x=?, y=?, width=?, height=?, label=?, content=?, answers=?, feedback=?
                       WHERE id=?""", values + (existing,))
            else:
                con.execute(
                    """INSERT INTO interactions (type, start, end, display, pauses, graded, x, y, width,
                       height, label, content, answers, feedback, lesson_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values + (lesson_id,))
            con.execute("UPDATE lessons SET updated = ? WHERE id = ?", (db.now(), lesson_id))
        flash(request, "บันทึกแล้ว")
        return RedirectResponse(f"/lessons/{lesson_id}/edit", status_code=303)

    @app.post("/lessons/{lesson_id}/interactions/{interaction_id}/delete")
    def interaction_delete(request: Request, lesson_id: int, interaction_id: int,
                           csrf: str = Form("")):
        require(request, *security.TEACHING)
        check_csrf(request, csrf)
        with db.connect() as con:
            # Its answers go too: rows pointing at a question nobody can read
            # are not a record of anything.
            con.execute("DELETE FROM interactions WHERE id = ? AND lesson_id = ?",
                        (interaction_id, lesson_id))
        flash(request, "ลบแล้ว")
        return RedirectResponse(f"/lessons/{lesson_id}/edit", status_code=303)

    # ---- learning ------------------------------------------------------------

    @app.get("/lessons/{lesson_id}")
    def learn(request: Request, lesson_id: int):
        user = require(request)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
            if not may_view(user, lesson):
                raise Denied(403)
            interactions = db.interactions_for_engine(con, lesson_id)
            seen = db.seen(con, lesson_id, user["id"])
            progress = con.execute("SELECT * FROM progress WHERE lesson_id = ? AND user_id = ?",
                                   (lesson_id, user["id"])).fetchone()
        timeline = engine.timeline(interactions, seen, rules_of(lesson))
        if not timeline.get("ok"):
            # Not played without its questions: a video with nothing on it
            # looks like it worked, and a learner would watch to the end
            # believing they had been assessed.
            reason = timeline.get("error") if user["role"] in security.TEACHING else None
            return page(request, "error.html", {
                "message": "ติดต่อเครื่องยนต์ตรวจคำตอบไม่ได้ จึงแสดงบทเรียนนี้ไม่ได้ ไม่มีอะไรสูญหาย "
                           "ลองใหม่อีกครั้งในอีกสักครู่", "reason": reason}, status=503)
        items = timeline["items"]
        for item in items:
            item["typelabel"] = authoring.TYPE_LABELS.get(item.get("type"), item.get("type"))
        return page(request, "learn.html", {
            "lesson": lesson,
            "player": {
                "video": video_of(lesson),
                "items": items,
                "title": lesson["title"],
                "mustanswer": bool(lesson["mustanswer"]),
                "resumeat": progress["furthest"] if progress else 0,
                "lang": "th",
            },
            "questions": sum(1 for item in items if item.get("graded")),
        })

    async def _json(request: Request) -> dict:
        try:
            body = await request.json()
        except ValueError:
            raise Denied(400)
        if not isinstance(body, dict):
            raise Denied(400)
        return body

    @app.post("/api/lessons/{lesson_id}/answer")
    async def answer(request: Request, lesson_id: int):
        user = require(request)
        check_csrf(request, request.headers.get("X-CSRF-Token"))
        body = await _json(request)
        try:
            interaction_id = int(body.get("interaction"))
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
            if not may_view(user, lesson):
                raise Denied(403)
            interaction = next((i for i in db.interactions_for_engine(con, lesson_id)
                                if i["id"] == interaction_id), None)
            if not interaction:
                return JSONResponse({"ok": False, "error": "no_such_interaction"}, status_code=404)
            before = db.seen(con, lesson_id, user["id"]).get(str(interaction_id))
        verdict = engine.judge(interaction, body.get("response"),
                               before["attempts"] if before else 0,
                               bool(before and before["ever_correct"]), rules_of(lesson))
        if not verdict.get("ok"):
            return JSONResponse({"ok": False, "error": verdict.get("error", "unknown")})
        with db.connect() as con:
            con.execute(
                """INSERT INTO responses (interaction_id, user_id, response, correct, attempt, created)
                   VALUES (?,?,?,?,?,?)""",
                (interaction_id, user["id"], json.dumps(verdict.get("store"), ensure_ascii=False),
                 1 if verdict.get("correct") else 0, int(verdict.get("attempts", 1)), db.now()))
        # Only what the engine chose to release; never `store`.
        return {key: verdict.get(key) for key in (
            "ok", "correct", "revealed", "may_retry", "attempts", "answers", "feedback")}

    @app.post("/api/lessons/{lesson_id}/progress")
    async def progress(request: Request, lesson_id: int):
        user = require(request)
        body = await _json(request)
        # In the body, not a header: this one is also sent with sendBeacon as
        # the page closes, and a beacon cannot set headers.
        check_csrf(request, request.headers.get("X-CSRF-Token") or body.get("csrf"))
        try:
            position = max(0.0, float(body.get("position") or 0))
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
            if not may_view(user, lesson):
                raise Denied(403)
            # The furthest point, not the last reported: scrubbing back to
            # rewatch does not undo what was watched.
            con.execute(
                """INSERT INTO progress (lesson_id, user_id, furthest, finished, updated)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT (lesson_id, user_id) DO UPDATE SET
                     furthest = MAX(furthest, excluded.furthest),
                     finished = MAX(finished, excluded.finished),
                     updated = excluded.updated""",
                (lesson_id, user["id"], position, 1 if body.get("finished") else 0, db.now()))
        return {"ok": True}

    @app.get("/api/lessons/{lesson_id}/score")
    def my_score(request: Request, lesson_id: int):
        user = require(request)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
            if not may_view(user, lesson):
                raise Denied(403)
            result = engine.score(db.interactions_for_engine(con, lesson_id),
                                  db.seen(con, lesson_id, user["id"]))
        return {key: result.get(key) for key in ("ok", "correct", "total", "fraction")}

    @app.get("/media/{name}")
    def media(request: Request, name: str):
        user = require(request)
        with db.connect() as con:
            row = con.execute("SELECT * FROM lessons WHERE mediafile = ?", (name,)).fetchone()
        if not row or not may_view(user, dict(row)):
            raise Denied(404)
        path = config.DATA_DIR / "media" / name
        if not path.is_file():
            raise Denied(404)
        # FileResponse answers Range requests, which is what makes the seek
        # bar work on a long video.
        return FileResponse(path, media_type=VIDEO_TYPES.get(path.suffix, "application/octet-stream"),
                            headers={"Cache-Control": "private, max-age=3600"})

    # ---- reports ---------------------------------------------------------------

    def _report(lesson: dict) -> dict[str, Any]:
        with db.connect() as con:
            interactions = db.interactions_for_engine(con, lesson["id"])
            learners = [dict(r) for r in con.execute(
                "SELECT id, username, name FROM users WHERE role = 'learner' ORDER BY name").fetchall()]
            progress = {r["user_id"]: dict(r) for r in con.execute(
                "SELECT * FROM progress WHERE lesson_id = ?", (lesson["id"],)).fetchall()}
            seen_by = {learner["id"]: db.seen(con, lesson["id"], learner["id"]) for learner in learners}
            graded_ids = {r["id"] for r in con.execute(
                "SELECT id FROM interactions WHERE lesson_id = ? AND graded = 1", (lesson["id"],))}
        graded = [i for i in interactions if i["id"] in graded_ids]
        rows = []
        for learner in learners:
            seen = seen_by[learner["id"]]
            result = engine.score(interactions, seen) if seen else {"ok": True, "correct": 0,
                                                                    "total": len(graded), "fraction": 0}
            rows.append({**learner,
                         "correct": result.get("correct"), "total": result.get("total"),
                         "fraction": result.get("fraction"), "ok": result.get("ok"),
                         "answered": sum(1 for i in graded if str(i["id"]) in seen),
                         "furthest": (progress.get(learner["id"]) or {}).get("furthest", 0),
                         "finished": bool((progress.get(learner["id"]) or {}).get("finished"))})
        questions = []
        for item in graded:
            answered = [s[str(item["id"])] for s in seen_by.values() if str(item["id"]) in s]
            questions.append({
                "start": item["start"], "type": item["type"], "label": item["label"],
                "text": authoring.from_html(item["content"].get("text", "")),
                "answered": len(answered),
                "correct": sum(1 for a in answered if a["correct"]),
            })
        return {"rows": rows, "questions": questions, "engine_ok": all(r["ok"] for r in rows)}

    @app.get("/lessons/{lesson_id}/report")
    def report(request: Request, lesson_id: int):
        require(request, *security.TEACHING)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
        return page(request, "report.html", {"lesson": lesson, **_report(lesson)})

    @app.get("/lessons/{lesson_id}/report.csv")
    def report_csv(request: Request, lesson_id: int):
        require(request, *security.TEACHING)
        with db.connect() as con:
            lesson = lesson_or_404(con, lesson_id)
        data = _report(lesson)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["username", "name", "correct", "total", "answered", "watched_to_seconds",
                         "finished"])
        for row in data["rows"]:
            # A leading = + - @ makes a spreadsheet run the cell as a formula.
            safe = [("'" + str(v)) if str(v)[:1] in "=+-@" else v for v in (row["username"], row["name"])]
            writer.writerow(safe + [row["correct"], row["total"], row["answered"],
                                    round(row["furthest"]), "yes" if row["finished"] else "no"])
        return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="lesson-{lesson_id}-report.csv"'})

    # ---- people ----------------------------------------------------------------

    @app.get("/users")
    def users(request: Request):
        require(request, "admin")
        with db.connect() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM users ORDER BY role, username")]
        return page(request, "users.html", {"rows": rows})

    @app.post("/users")
    def user_create(request: Request, username: str = Form(""), name: str = Form(""),
                    role: str = Form("learner"), password: str = Form(""), csrf: str = Form("")):
        require(request, "admin")
        check_csrf(request, csrf)
        username = username.strip()
        problem = None
        if not username or len(username) > 100 or not username.replace(".", "").replace(
                "_", "").replace("-", "").replace("@", "").isalnum():
            problem = "ชื่อผู้ใช้ใช้ได้เฉพาะตัวอักษร ตัวเลข และ . _ - @"
        elif role not in security.ROLES:
            problem = "บทบาทไม่ถูกต้อง"
        else:
            problem = security.password_problem(password)
        if not problem:
            with db.connect() as con:
                if con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                    problem = "มีชื่อผู้ใช้นี้อยู่แล้ว"
                else:
                    con.execute(
                        "INSERT INTO users (username, name, role, password_hash, created) VALUES (?,?,?,?,?)",
                        (username, name.strip() or username, role, security.hash_password(password), db.now()))
        if problem:
            flash(request, problem, "danger")
        else:
            flash(request, f"เพิ่มผู้ใช้ {username} แล้ว")
        return RedirectResponse("/users", status_code=303)

    @app.post("/users/{user_id}")
    def user_update(request: Request, user_id: int, action: str = Form(""), password: str = Form(""),
                    role: str = Form(""), csrf: str = Form("")):
        me = require(request, "admin")
        check_csrf(request, csrf)
        with db.connect() as con:
            target = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not target:
                raise Denied(404)
            if action == "password":
                problem = security.password_problem(password)
                if problem:
                    flash(request, problem, "danger")
                else:
                    con.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                                (security.hash_password(password), user_id))
                    flash(request, f"ตั้งรหัสผ่านใหม่ให้ {target['username']} แล้ว")
            elif action in ("deactivate", "activate", "role"):
                if user_id == me["id"]:
                    # Otherwise the last administrator can lock everybody out.
                    flash(request, "เปลี่ยนสถานะหรือบทบาทของบัญชีตัวเองไม่ได้", "danger")
                elif action == "role":
                    if role in security.ROLES:
                        con.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
                        flash(request, f"เปลี่ยนบทบาทของ {target['username']} แล้ว")
                else:
                    con.execute("UPDATE users SET active = ? WHERE id = ?",
                                (1 if action == "activate" else 0, user_id))
                    flash(request, f"{'เปิด' if action == 'activate' else 'ปิด'}บัญชี {target['username']} แล้ว")
        return RedirectResponse("/users", status_code=303)


def _app_from_environment() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    return create_app()


# `uvicorn app.main:app --factory` builds it on start, with the environment
# read then rather than at import.
app = _app_from_environment
