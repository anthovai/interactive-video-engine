"""Everything the studio is told by its environment.

Read once, at import. The three that have no safe default — the engine's key,
the secret that signs sessions, and the first administrator's password — are
required, and the studio refuses to start without them rather than inventing
one: a default secret is a secret every installation shares.
"""
from __future__ import annotations

import os
import pathlib


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ConfigError(f"set {name}")
    return value


ENGINE_URL = os.environ.get("KAIIV_ENGINE_URL", "http://kaiiv-service:9200").rstrip("/")
ENGINE_TIMEOUT = float(os.environ.get("KAIIV_ENGINE_TIMEOUT", "10"))
CONTRACT = "1.0"

DATA_DIR = pathlib.Path(os.environ.get("KAIIV_DATA_DIR", "/data"))
PLAYER_DIR = pathlib.Path(os.environ.get(
    "KAIIV_PLAYER_DIR",
    str(pathlib.Path(__file__).resolve().parents[2] / "kaiiv-player" / "dist")))

# A lesson video, not a film library. Raised by the operator if they need it.
MAX_UPLOAD_MB = int(os.environ.get("KAIIV_MAX_UPLOAD_MB", "1024"))

# Behind HTTPS in production, which is where the session cookie must be
# Secure. Off by default only so that http://127.0.0.1 works on first run.
SECURE_COOKIES = os.environ.get("KAIIV_SECURE_COOKIES", "0") == "1"

# Hours a sign-in lasts.
SESSION_HOURS = int(os.environ.get("KAIIV_SESSION_HOURS", "12"))


def load() -> dict[str, str]:
    """The required settings, checked. Called at startup, not at import, so the
    tests can set them first."""
    return {
        "api_key": _required("KAIIV_API_KEY"),
        "secret": _required("KAIIV_STUDIO_SECRET"),
        "admin_user": os.environ.get("KAIIV_ADMIN_USER", "admin"),
        # Only used the first time, to create the first administrator.
        "admin_password": os.environ.get("KAIIV_ADMIN_PASSWORD", ""),
    }
