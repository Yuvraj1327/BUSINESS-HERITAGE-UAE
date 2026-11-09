"""Database connection infrastructure (lazy: importing this module never opens a connection).

Every request session runs as the Postgres role `authenticated` with the caller's verified JWT claims
(`request.jwt.claims`), so `auth.uid()` and every RLS policy apply to every query. The API logs in as the
restricted `app_api` role (NOBYPASSRLS) and never as `postgres` / `service_role`. The role switch is re-applied
at the start of EVERY transaction (SQLAlchemy `after_begin`), so it also survives commit/rollback inside a
request. SET LOCAL / `set_config(..., true)` are transaction-scoped, so nothing leaks to the next pooled use.
"""

import logging
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.core.security import TokenClaims, claims_for_database

logger = logging.getLogger(__name__)

RLS_CLAIMS_KEY = "rls_claims"


class DatabaseNotConfiguredError(ServiceUnavailableError):
    code = "database_not_configured"


def build_engine(settings: Settings) -> Engine:
    url = settings.sqlalchemy_url
    if url is None:
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        # Supabase's transaction pooler cannot keep server-side prepared statements across connections.
        connect_args={"prepare_threshold": None},
    )


@event.listens_for(Session, "after_begin")
def _apply_rls_context(session: Session, _tx: SessionTransaction, connection: Connection) -> None:
    """Start every transaction of an authenticated session as role `authenticated` with the caller's claims."""
    claims_json = session.info.get(RLS_CLAIMS_KEY)
    if claims_json is None:
        return
    connection.exec_driver_sql("SET LOCAL ROLE authenticated")
    connection.exec_driver_sql("SELECT set_config('request.jwt.claims', %s, true)", (claims_json,))


class Database:
    """Owns the engine for one app instance (created lazily, so the API can start without a database)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: Engine | None = None
        self._factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = build_engine(self._settings)
            self._factory = sessionmaker(self._engine, expire_on_commit=False)
        return self._engine

    def session_for(self, claims: TokenClaims) -> Iterator[Session]:
        """One session per request, bound to the verified caller. Rolled back on error, always closed."""
        _ = self.engine
        assert self._factory is not None
        session = self._factory()
        session.info[RLS_CLAIMS_KEY] = claims_for_database(claims)
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine, self._factory = None, None


def ping_database(settings: Settings) -> None:
    """Raises if the database is unreachable. Uses its own short-lived engine so it reflects current settings."""
    engine = build_engine(settings)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    finally:
        engine.dispose()
