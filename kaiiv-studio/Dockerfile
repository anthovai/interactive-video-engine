# KAISER Interactive Video Studio.
#
# Built from the repository root (see docker-compose.yml), because it carries
# the player's built files from kaiiv-player/dist alongside its own code.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    KAIIV_DATA_DIR=/data KAIIV_PLAYER_DIR=/app/player

WORKDIR /app
COPY kaiiv-studio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kaiiv-studio/app ./app
COPY kaiiv-player/dist ./player
# The notices the player may only be handed on with; see thirdparty/README.md.
COPY kaiiv-player/thirdparty ./player/thirdparty

# Not root: a flaw in a web app should not come with the container's root.
RUN useradd --system --uid 10001 --home /app studio \
    && mkdir -p /data && chown studio:studio /data
USER studio

VOLUME ["/data"]
EXPOSE 8300
HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8300/healthz')"
CMD ["uvicorn", "app.main:app", "--factory", "--host", "0.0.0.0", "--port", "8300"]
