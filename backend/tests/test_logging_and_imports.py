import importlib
import json
import logging
import pkgutil

import app
from app.core.context import request_id_var
from app.core.logging import JsonFormatter


def test_every_module_imports_cleanly() -> None:
    failures = []
    for mod in pkgutil.walk_packages(app.__path__, prefix="app."):
        try:
            importlib.import_module(mod.name)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{mod.name}: {exc!r}")
    assert not failures, failures


def test_json_formatter_emits_valid_json_with_request_id_and_extras() -> None:
    token = request_id_var.set("req-12345678")
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        record.status = 200
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-12345678"
    assert payload["status"] == 200
    assert payload["level"] == "INFO"


def test_dubai_today_uses_dubai_calendar() -> None:
    from datetime import UTC, datetime

    from app.utils.time import dubai_today

    # 21:00 UTC is already the next day in Dubai (UTC+4)
    assert dubai_today(datetime(2026, 10, 1, 21, 0, tzinfo=UTC)).isoformat() == "2026-10-02"
