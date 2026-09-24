"""Configuration for the interactive video engine.

Same shape as the face and AI services, for the same reason: what the engine
does is code, and who is allowed to call it is deployment.

There is no database setting here, and that is the central design decision of
this service rather than an omission — see main.py.
"""
import os

# --------------------------------------------------------------------------
# Access control
# --------------------------------------------------------------------------
# Shared secret sent by the calling platform as X-Proctor-Key. Same pattern as
# the face service and the AI service, and the same key: a deployment has one
# internal secret, not three to rotate separately.
API_KEY = os.environ.get("KAIIV_API_KEY", "").strip()

SERVICE_VERSION = "1.1.0"

# The payload contract version. Callers send it and we check it, so that a
# customer running an older integration gets a clear refusal rather than a
# timeline built from fields we have since redefined.
CONTRACT_VERSION = "1.0"

SUPPORTED_CONTRACTS = {"1.0"}

# --------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------
# A timeline longer than this is refused rather than served slowly. The number
# is not a performance limit — the engine is pure arithmetic and would manage
# far more — it is a shape check: a request carrying ten thousand interactions
# is a caller sending the wrong thing, and answering it politely would hide
# that until somebody noticed the response size.
MAX_INTERACTIONS = int(os.environ.get("KAIIV_MAX_INTERACTIONS", 2000))

# How much authored text one interaction may carry. Generous for a question,
# small enough that a video file posted into the wrong field is refused.
MAX_TEXT = int(os.environ.get("KAIIV_MAX_TEXT", 20000))
