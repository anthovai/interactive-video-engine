"""Passwords, sessions, CSRF, and who may do what.

scrypt from the standard library for passwords — memory-hard, and no
dependency to keep patched. Sessions are Starlette's signed cookie holding a
user id and a CSRF token; the user is looked up again on every request, so a
deactivated account stops working at its next click rather than at the end of
its session.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

ROLES = ("admin", "teacher", "learner")

# Who may author and see reports. An administrator is also a teacher.
TEACHING = ("admin", "teacher")

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                               n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2)
    return hmac.compare_digest(candidate.hex(), digest)


def password_problem(password: str) -> str | None:
    """Why a password will not do, in words a person can act on, or None."""
    if len(password) < 10:
        return "รหัสผ่านต้องยาวอย่างน้อย 10 ตัวอักษร"
    if password.lower() == password or password.upper() == password or not any(
            c.isdigit() for c in password):
        return "รหัสผ่านต้องมีทั้งตัวพิมพ์เล็ก ตัวพิมพ์ใหญ่ และตัวเลข"
    return None


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(session: dict, given: str | None) -> bool:
    expected = session.get("csrf")
    return bool(expected and given and hmac.compare_digest(expected, given))


class Throttle:
    """Slow down guessing at the sign-in form.

    Five failures for a username, or twenty from one address, in fifteen
    minutes, and further attempts are refused until the window passes. In
    memory, so a restart forgets it — which is acceptable for an obstacle to
    guessing, and not a substitute for good passwords.
    """

    WINDOW = 15 * 60
    PER_USER = 5
    PER_ADDRESS = 20

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.time() - self.WINDOW
        kept = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = kept
        return kept

    def blocked(self, username: str, address: str) -> bool:
        with self._lock:
            return (len(self._recent("u:" + username.lower())) >= self.PER_USER
                    or len(self._recent("a:" + address)) >= self.PER_ADDRESS)

    def failed(self, username: str, address: str) -> None:
        with self._lock:
            for key in ("u:" + username.lower(), "a:" + address):
                self._recent(key).append(time.time())

    def succeeded(self, username: str) -> None:
        with self._lock:
            self._failures.pop("u:" + username.lower(), None)
