import pytest
from fastapi.testclient import TestClient

from app.core.config import AppEnv, Settings
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"app_env": AppEnv.TEST, "log_level": "WARNING"}
    base.update(overrides)
    # _env_file=None: tests must never depend on a developer's local .env
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.fixture()
def settings() -> Settings:
    return make_settings()


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), raise_server_exceptions=False)


# ---- real-PostgreSQL fixtures (Step 2 migrations + Supabase stub) --------------------------------------------
import pathlib  # noqa: E402
import uuid  # noqa: E402

import psycopg  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[2] / "database"
_ADMIN_DSN = __import__("os").environ.get(
    "TEST_PG_ADMIN_DSN", "host=/tmp port=54329 user=postgres dbname=postgres"
)
APP_API_PASSWORD = "test-only-" + uuid.uuid4().hex


@pytest.fixture(scope="session")
def pg_admin_dsn():
    """Fresh disposable database with the stub auth schema and ALL migrations. Skips if no server is reachable."""
    try:
        admin = psycopg.connect(_ADMIN_DSN, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("no PostgreSQL available (set TEST_PG_ADMIN_DSN to a disposable superuser DSN)")
    name = f"alsafa_auth_{uuid.uuid4().hex[:8]}"
    admin.execute(f'create database "{name}"')
    dsn = _ADMIN_DSN.replace("dbname=postgres", f"dbname={name}")
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((_ROOT / "tests" / "stub_supabase.sql").read_text())
            for m in sorted((_ROOT / "migrations").glob("*.sql")):
                c.execute(m.read_text())
            # Operator step, simulated: give the restricted role a login (production does this out of band).
            c.execute(f"alter role app_api login password '{APP_API_PASSWORD}'")
        yield dsn
    finally:
        admin.execute("alter role app_api nologin")
        admin.execute(f'drop database if exists "{name}" with (force)')
        admin.close()


@pytest.fixture(scope="session")
def app_api_url(pg_admin_dsn: str) -> str:
    dbname = pg_admin_dsn.split("dbname=")[1]
    return f"postgresql://app_api:{APP_API_PASSWORD}@/{dbname}?host=/tmp&port=54329"
