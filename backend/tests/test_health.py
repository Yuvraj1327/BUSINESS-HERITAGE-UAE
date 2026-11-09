from fastapi.testclient import TestClient

from app.core.config import AppEnv
from app.main import create_app
from tests.conftest import make_settings


def test_health_returns_status_and_service_info(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "ALSAFA Heritage Laundry API"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "test"
    assert body["time"]


def test_request_id_is_generated_and_echoed(client: TestClient) -> None:
    generated = client.get("/api/v1/health").headers["X-Request-ID"]
    assert len(generated) >= 8
    echoed = client.get("/api/v1/health", headers={"X-Request-ID": "abc12345-def"}).headers[
        "X-Request-ID"
    ]
    assert echoed == "abc12345-def"


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    r = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\twith spaces!"})
    assert r.headers["X-Request-ID"] != "bad id\twith spaces!"
    assert r.headers["X-Request-ID"].isalnum()


def test_readiness_without_database_is_degraded_not_error(client: TestClient) -> None:
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "degraded", "database": "not_configured"}


def test_readiness_with_unreachable_database_returns_503_envelope() -> None:
    s = make_settings(database_url="postgresql://u:p@127.0.0.1:1/none")
    r = TestClient(create_app(s)).get("/api/v1/health/ready")
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "database_unavailable"
    assert "127.0.0.1" not in r.text and "u:p" not in r.text  # no connection details leak


def test_docs_enabled_in_test_disabled_in_production(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    prod = make_settings(
        app_env=AppEnv.PRODUCTION,
        database_url="postgresql://u:p@db.example.com/postgres",
        supabase_url="https://abc.supabase.co",
        cors_origins="https://erp.example.com",
    )
    pc = TestClient(create_app(prod))
    assert pc.get("/docs").status_code == 404
    assert pc.get("/openapi.json").status_code == 404
    assert pc.get("/api/v1/health").json()["environment"] == "production"
