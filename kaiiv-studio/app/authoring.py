"""From the question form to what the engine expects, and back again.

The same mapping mod_kaiiv's edit.php makes, so a question written here and one
written in Moodle reach the engine in the same shape.

Two things are different from Moodle, and both are about the page.

Teachers here type plain text, and the player puts a question's text and its
explanation on the page as HTML — in Moodle they come from Moodle's editor,
which cleans them. So both are escaped here, before they are stored: a teacher
who types <script> gets the characters <script> on the card, not a script.

And an image or a link takes a URL, which is checked to be http(s) or a path
on this site. A `javascript:` link on a question card is a script too.
"""
from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

MAX_OPTIONS = 6

# Two questions closer together than this pause the video in the same moment,
# and the second opens on top of the first. Same as mod_kaiiv.
MIN_GAP = 0.5

# How long something that does not pause stays up when the author gave no end.
DEFAULT_DURATION = 5.0

TYPE_LABELS = {
    "choice": "ตอบข้อเดียว",
    "multichoice": "ตอบหลายข้อ",
    "truefalse": "ถูกหรือผิด",
    "shorttext": "พิมพ์คำตอบ",
    "blanks": "เติมคำในช่องว่าง",
    "dragtext": "ลากคำไปเติม",
    "marktheword": "เลือกคำในข้อความ",
    "label": "ข้อความ",
    "image": "รูปภาพ",
    "link": "ลิงก์",
}


class FormProblem(ValueError):
    """Something the teacher has to change, said in words they can act on."""


# ---------------------------------------------------------------------------
# Text that becomes HTML
# ---------------------------------------------------------------------------

def to_html(text: str) -> str:
    """Plain text, escaped, with its line breaks kept."""
    return html.escape(text.strip()).replace("\r\n", "\n").replace("\n", "<br>")


def from_html(value: str) -> str:
    """The reverse, for filling the form in again."""
    return html.unescape(re.sub(r"<br\s*/?>", "\n", value or ""))


def safe_url(value: str) -> str:
    """An http(s) URL or a path on this site, or FormProblem."""
    url = (value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return url
    if not parsed.scheme and not parsed.netloc and url.startswith("/") and not url.startswith("//"):
        return url
    raise FormProblem("ที่อยู่ต้องขึ้นต้นด้วย http:// หรือ https://")


def lines_of(raw: str) -> list[str]:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# The form
# ---------------------------------------------------------------------------

def _number(form: dict, name: str, default: float, low: float = 0, high: float = 10 ** 6) -> float:
    raw = str(form.get(name, "") or "").strip()
    if raw == "":
        return default
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        raise FormProblem(f"ช่อง {name} ต้องเป็นตัวเลข")
    if not low <= value <= high:
        raise FormProblem(f"ช่อง {name} ต้องอยู่ระหว่าง {low:g} ถึง {high:g}")
    return value


def authored(form: dict) -> dict[str, Any]:
    """What the teacher wrote, in the engine's authored shape.

    Only the fields of the chosen type. The form carries every type's fields
    at once, so that switching type does not lose what was typed; passing the
    others on would have the engine refusing a question over a box the
    teacher was no longer looking at.
    """
    kind = form.get("type", "")
    text = to_html(str(form.get("text", "")))

    if kind in ("choice", "multichoice"):
        options = []
        for index in range(MAX_OPTIONS):
            option = str(form.get(f"option{index}", "")).strip()
            if not option:
                # A tick next to an empty box goes with it, so the indexes the
                # engine gets count filled options only.
                continue
            options.append({"text": option, "correct": bool(form.get(f"correct{index}"))})
        return {"text": text, "options": options}
    if kind == "truefalse":
        return {"text": text, "correct": str(form.get("istrue", "1")) == "1"}
    if kind == "shorttext":
        return {"text": text, "accept": lines_of(str(form.get("accept", "")))}
    if kind in ("blanks", "dragtext"):
        return {"text": text, "lines": lines_of(str(form.get("lines", "")))}
    if kind == "marktheword":
        return {"text": text, "passage": str(form.get("passage", "")).strip()}
    if kind == "image":
        return {"url": safe_url(str(form.get("url", ""))),
                "alt": str(form.get("alt", "")).strip(),
                "caption": str(form.get("caption", "")).strip()}
    if kind == "link":
        return {"url": safe_url(str(form.get("url", ""))),
                "title": str(form.get("linktitle", "")).strip()}
    return {"text": text}


def placement(form: dict) -> dict[str, Any]:
    """Where and how it sits on the video."""
    start = _number(form, "starttime", -1)
    if start < 0:
        raise FormProblem("ใส่เวลาที่จะให้แสดง (วินาที)")
    display = form.get("displaytype", "poster")
    return {
        "start": start,
        "end": _number(form, "endtime", 0),
        "display": display if display in ("poster", "button") else "poster",
        "label": str(form.get("label", "")).strip()[:200],
        "feedback": to_html(str(form.get("feedback", ""))),
        "x": _number(form, "x", 20, 0, 100),
        "y": _number(form, "y", 20, 0, 100),
        "width": _number(form, "width", 60, 5, 100),
        "height": _number(form, "height", 40, 5, 100),
    }


def window_end(start: float, end: float, pauses: bool) -> float:
    """A question that pauses ends when it is answered; anything else stays up
    for as long as the author said, or DEFAULT_DURATION."""
    if pauses:
        return start
    return end if end > start else start + DEFAULT_DURATION


# ---------------------------------------------------------------------------
# Back into the form
# ---------------------------------------------------------------------------

def prefill(row: dict, content: dict, answers: list) -> dict[str, Any]:
    """The form, filled in from a stored interaction.

    The authored form — `the capital of *France* is Paris` — was never stored,
    so it is rebuilt from the two halves. A gap that accepted several
    spellings comes back with all of them.
    """
    kind = row["type"]
    data: dict[str, Any] = {
        "id": row["id"],
        "type": kind,
        "starttime": f'{row["start"]:g}',
        "endtime": f'{row["end"]:g}' if row["end"] > row["start"] else "",
        "displaytype": row["display"],
        "label": row["label"],
        "feedback": from_html(row["feedback"]),
        "text": from_html(content.get("text", "")),
        "x": f'{row["x"]:g}', "y": f'{row["y"]:g}',
        "width": f'{row["width"]:g}', "height": f'{row["height"]:g}',
        "url": content.get("url", ""),
        "alt": content.get("alt", ""),
        "caption": content.get("caption", ""),
        "linktitle": content.get("title", ""),
    }
    if kind in ("choice", "multichoice"):
        marked = {int(a) for a in answers}
        for index, option in enumerate(content.get("options", [])):
            data[f"option{index}"] = option
            data[f"correct{index}"] = index in marked
    elif kind == "truefalse":
        data["istrue"] = "1" if answers and answers[0] else "0"
    elif kind == "shorttext":
        data["accept"] = "\n".join(str(a) for a in answers)
    elif kind in ("blanks", "dragtext"):
        def regap(line: str) -> str:
            return re.sub(r"\[\[(\d+)\]\]", lambda m: "*" + "/".join(
                answers[int(m.group(1))] if int(m.group(1)) < len(answers) else []) + "*", line)
        data["lines"] = "\n".join(regap(line) for line in content.get("lines", []))
    elif kind == "marktheword":
        marked = {int(a) for a in answers}
        data["passage"] = " ".join(f"*{word}*" if index in marked else word
                                   for index, word in enumerate(content.get("words", [])))
    return data


# ---------------------------------------------------------------------------
# Where the video comes from
# ---------------------------------------------------------------------------

def video_source(kind: str, address: str) -> dict[str, str]:
    """A video address as the player's {provider, src, videoid}.

    kind is what the teacher picked: upload (handled by the caller), url,
    youtube or vimeo. A YouTube or Vimeo address is accepted in any of the
    forms people paste, and reduced to its id.
    """
    address = (address or "").strip()
    if kind == "youtube":
        parsed = urlparse(address if "//" in address else "https://youtu.be/" + address)
        videoid = ""
        if parsed.netloc.endswith("youtu.be"):
            videoid = parsed.path.strip("/")
        elif "youtube" in parsed.netloc:
            videoid = (parse_qs(parsed.query).get("v") or [""])[0] or parsed.path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", videoid or ""):
            raise FormProblem("อ่านรหัสวิดีโอ YouTube จากที่อยู่นี้ไม่ได้")
        return {"provider": "youtube", "src": "", "videoid": videoid}
    if kind == "vimeo":
        match = re.search(r"(?:vimeo\.com/(?:video/)?)?(\d{5,12})(?:/([0-9a-f]{6,20}))?", address)
        if not match:
            raise FormProblem("อ่านรหัสวิดีโอ Vimeo จากที่อยู่นี้ไม่ได้")
        hashpart = match.group(2) or (parse_qs(urlparse(address).query).get("h") or [""])[0]
        return {"provider": "vimeo", "src": "",
                "videoid": match.group(1) + (":" + hashpart if hashpart else "")}
    if kind == "url":
        url = safe_url(address)
        if not url:
            raise FormProblem("ใส่ที่อยู่ของวิดีโอ")
        path = urlparse(url).path.lower()
        return {"provider": "hls" if path.endswith(".m3u8") else "file", "src": url, "videoid": ""}
    raise FormProblem("เลือกที่มาของวิดีโอ")
