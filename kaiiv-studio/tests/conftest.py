"""The studio against the real engine, in one process.

Not a fake engine: a stub would agree with whatever the studio sends, and the
thing most worth testing is that the two agree with each other. The engine is
loaded from ../kaiiv-service under another name — both packages are called
`app` — and the studio's engine client is pointed at it through TestClient,
which is an httpx.Client and so is exactly what the studio would use anyway.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE_DIR = ROOT / "kaiiv-service" / "app"
KEY = "test-engine-key"
ADMIN_PASSWORD = "Admin-Pass-2345"


def _load_engine():
    if "kaiiv_engine" in sys.modules:
        return sys.modules["kaiiv_engine"]
    spec = importlib.util.spec_from_file_location(
        "kaiiv_engine", ENGINE_DIR / "__init__.py", submodule_search_locations=[str(ENGINE_DIR)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["kaiiv_engine"] = package
    spec.loader.exec_module(package)
    importlib.import_module("kaiiv_engine.main")
    return package


@pytest.fixture
def engine_app(monkeypatch):
    package = _load_engine()
    monkeypatch.setattr(sys.modules["kaiiv_engine.config"], "API_KEY", KEY)
    return sys.modules["kaiiv_engine.main"].app


@pytest.fixture
def studio(tmp_path, monkeypatch, engine_app):
    from app import config, main, security

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "throttle", security.Throttle())
    app = main.create_app(
        settings={"api_key": KEY, "secret": "test-session-secret-0123456789",
                  "admin_user": "admin", "admin_password": ADMIN_PASSWORD},
        engine_client=TestClient(engine_app, base_url="http://engine"),
        database=tmp_path / "studio.sqlite3")
    return app


class Browser:
    """A signed-in person, with the CSRF token their pages carry."""

    def __init__(self, app):
        self.client = TestClient(app, base_url="http://studio.test")

    def csrf(self, path: str = "/login") -> str:
        page = self.client.get(path)
        match = re.search(r'name="csrf" value="([^"]+)"', page.text) or re.search(
            r'name="csrf-token" content="([^"]+)"', page.text)
        assert match, f"no CSRF token on {path}"
        return match.group(1)

    def login(self, username: str, password: str):
        return self.client.post("/login", data={
            "username": username, "password": password, "csrf": self.csrf("/login")},
            follow_redirects=False)

    def post(self, path: str, data: dict, files=None, token_from: str = "/"):
        return self.client.post(path, data={**data, "csrf": self.csrf(token_from)}, files=files,
                                follow_redirects=False)

    def api(self, path: str, body: dict, token_from: str):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.csrf(token_from)})


@pytest.fixture
def admin(studio):
    person = Browser(studio)
    assert person.login("admin", ADMIN_PASSWORD).status_code == 303
    return person


@pytest.fixture
def people(studio, admin):
    """An administrator, a teacher and a learner, each signed in."""
    for username, role in (("teacher1", "teacher"), ("learner1", "learner"), ("learner2", "learner")):
        response = admin.post("/users", {"username": username, "name": username.title(),
                                         "role": role, "password": "Good-Pass-2345"}, token_from="/users")
        assert response.status_code == 303
    teacher, learner, other = Browser(studio), Browser(studio), Browser(studio)
    assert teacher.login("teacher1", "Good-Pass-2345").status_code == 303
    assert learner.login("learner1", "Good-Pass-2345").status_code == 303
    assert other.login("learner2", "Good-Pass-2345").status_code == 303
    return {"admin": admin, "teacher": teacher, "learner": learner, "other": other}


# An MP4 as far as anyone checking the first bytes is concerned.
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 2048
