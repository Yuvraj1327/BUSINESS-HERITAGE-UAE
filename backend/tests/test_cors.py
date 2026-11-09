from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

ALLOWED = "https://erp.example.com"


def _client() -> TestClient:
    return TestClient(create_app(make_settings(cors_origins=ALLOWED)))


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-request-id",
        },
    )


def test_allowed_origin_preflight_succeeds() -> None:
    r = _preflight(_client(), ALLOWED)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ALLOWED


def test_other_origin_is_not_allowed() -> None:
    r = _preflight(_client(), "https://evil.example.com")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_response_exposes_request_id_to_browsers() -> None:
    r = _client().get("/api/v1/health", headers={"Origin": ALLOWED})
    assert "x-request-id" in r.headers["access-control-expose-headers"].lower()
