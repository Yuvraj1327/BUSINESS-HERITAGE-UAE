from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.exceptions import ConflictError
from app.main import create_app
from tests.conftest import make_settings


class Item(BaseModel):
    title: str
    qty: int


def _client() -> TestClient:
    app = create_app(make_settings())

    @app.post("/_t/items")
    def create_item(item: Item) -> Item:  # test-only route
        return item

    @app.get("/_t/conflict")
    def conflict() -> None:
        raise ConflictError("Already exists", code="duplicate", fields={"name": ["taken"]})

    @app.get("/_t/boom")
    def boom() -> None:
        raise RuntimeError("super secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_unknown_route_uses_error_envelope() -> None:
    r = _client().get("/api/v1/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_method_not_allowed_uses_envelope() -> None:
    r = _client().post("/api/v1/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


def test_validation_errors_list_fields() -> None:
    r = _client().post("/_t/items", json={"title": 5})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert set(err["fields"]) == {"title", "qty"}


def test_app_error_maps_status_code_and_fields() -> None:
    r = _client().get("/_t/conflict")
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "duplicate",
        "message": "Already exists",
        "fields": {"name": ["taken"]},
    }


def test_unhandled_exception_is_500_without_leaking_details() -> None:
    r = _client().get("/_t/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret" not in r.text
    assert r.json()["request_id"]
