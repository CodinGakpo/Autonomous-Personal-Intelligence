"""Ops-console API tests. SQLite per test (no live Postgres needed); ClickUp faked."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clickup.client import TaskRef
from console.backend.config import Settings
from console.backend.main import create_app
from console.backend.onboarding import get_clickup_client

ADMIN_EMAIL = "admin@agent-os.local"
ADMIN_PASSWORD = "changeme"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        clickup_token="t",
        slack_bot_token=None,
        fathom_api_key=None,
        admin_email=ADMIN_EMAIL,
        admin_password=ADMIN_PASSWORD,
        clickup_employees_list_id="900",
        database_url=f"sqlite:///{tmp_path}/test.db",
        secret_key="test-secret-at-least-32-bytes-long!!",
        brain_api_base_url="http://localhost:8080",
    )


class _FakeClickUp:
    def create_task(self, list_id: str, name: str, description: str) -> TaskRef:
        return TaskRef(id="abc123", url="https://app.clickup.com/t/abc123")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(_settings(tmp_path))
    app.dependency_overrides[get_clickup_client] = lambda: _FakeClickUp()
    with TestClient(app) as test_client:  # triggers lifespan (DB setup + seed)
        yield test_client


def _token(client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD) -> str:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return str(res.json()["token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_reports_configuration(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    names = {i["name"]: i["status"] for i in res.json()["integrations"]}
    assert names == {"clickup": "configured", "slack": "not_configured", "fathom": "not_configured"}


def test_seeded_admin_can_log_in(client: TestClient) -> None:
    assert _token(client)  # non-empty token


def test_login_rejects_bad_credentials(client: TestClient) -> None:
    res = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert res.status_code == 401


def test_me_returns_current_user(client: TestClient) -> None:
    res = client.get("/auth/me", headers=_bearer(_token(client)))
    assert res.status_code == 200
    assert res.json()["email"] == ADMIN_EMAIL
    assert res.json()["role"] == "admin"


def test_onboarding_requires_auth(client: TestClient) -> None:
    assert client.post("/onboarding", json={}).status_code == 401


def test_onboarding_creates_clickup_task_and_appears_in_roster(client: TestClient) -> None:
    payload = {
        "name": "Sajal Mondal",
        "email": "sajal@agent-os.local",
        "role": "sales",
        "slack_handle": "@sajal",
        "products": ["product_one", "product_two"],
    }
    res = client.post("/onboarding", json=payload, headers=_bearer(_token(client)))
    assert res.status_code == 201, res.text
    assert res.json()["clickup_task_id"] == "abc123"

    roster = client.get("/roster", headers=_bearer(_token(client)))
    assert roster.status_code == 200
    assert any(p["name"] == "Sajal Mondal" for p in roster.json())


def test_admin_can_create_user_who_can_then_log_in(client: TestClient) -> None:
    res = client.post(
        "/auth/users",
        json={"email": "gtm@agent-os.local", "password": "pw123456", "role": "gtm"},
        headers=_bearer(_token(client)),
    )
    assert res.status_code == 201, res.text
    # The new user can authenticate.
    assert _token(client, "gtm@agent-os.local", "pw123456")


def test_non_admin_cannot_create_user(client: TestClient) -> None:
    client.post(
        "/auth/users",
        json={"email": "sales@agent-os.local", "password": "pw123456", "role": "sales"},
        headers=_bearer(_token(client)),
    )
    sales_token = _token(client, "sales@agent-os.local", "pw123456")
    res = client.post(
        "/auth/users",
        json={"email": "x@agent-os.local", "password": "pw123456", "role": "sales"},
        headers=_bearer(sales_token),
    )
    assert res.status_code == 403
