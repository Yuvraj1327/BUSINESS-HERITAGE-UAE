import pytest
from pydantic import ValidationError

from app.core.config import AppEnv, Settings

PROD = {
    "app_env": "production",
    "database_url": "postgresql://u:p@db.example.com/postgres",
    "supabase_url": "https://abc.supabase.co",
    "cors_origins": "https://erp.example.com",
}


def s(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_defaults_are_development_and_safe() -> None:
    cfg = s()
    assert cfg.app_env is AppEnv.DEVELOPMENT
    assert cfg.sqlalchemy_url is None
    assert cfg.cors_origins == ["http://localhost:5173"]
    assert cfg.use_json_logs is False


def test_cors_origins_parse_comma_separated_and_strip_slash() -> None:
    cfg = s(cors_origins="https://a.example.com/, https://b.example.com")
    assert cfg.cors_origins == ["https://a.example.com", "https://b.example.com"]


def test_cors_origin_without_scheme_rejected() -> None:
    with pytest.raises(ValidationError):
        s(cors_origins="erp.example.com")


def test_invalid_environment_and_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        s(app_env="staging-ish")
    with pytest.raises(ValidationError):
        s(log_level="LOUD")


def test_database_url_is_normalised_and_hidden() -> None:
    cfg = s(database_url="postgresql://user:pw@host:5432/db")
    assert cfg.sqlalchemy_url == "postgresql+psycopg://user:pw@host:5432/db"
    assert "pw" not in repr(cfg) and "pw" not in str(cfg.model_dump())
    assert s(database_url="postgres://u:p@h/d").sqlalchemy_url == "postgresql+psycopg://u:p@h/d"


def test_supabase_issuer_and_jwks_are_derived() -> None:
    cfg = s(supabase_url="https://abc.supabase.co")
    assert cfg.supabase_jwt_issuer == "https://abc.supabase.co/auth/v1"
    assert str(cfg.supabase_jwt_jwks_url) == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"


def test_production_valid_config_accepted() -> None:
    cfg = s(**PROD)
    assert cfg.is_production and cfg.use_json_logs


@pytest.mark.parametrize("missing", ["database_url", "supabase_url"])
def test_production_requires_database_and_supabase(missing: str) -> None:
    cfg = {k: v for k, v in PROD.items() if k != missing}
    with pytest.raises(ValidationError, match="required in production"):
        s(**cfg)


def test_production_rejects_wildcard_and_localhost_cors() -> None:
    with pytest.raises(ValidationError, match="must start with"):  # wildcard is never accepted
        s(**{**PROD, "cors_origins": "*"})
    with pytest.raises(ValidationError):
        s(**{**PROD, "cors_origins": "http://localhost:5173"})


def test_service_role_key_is_optional_and_never_printed() -> None:
    # Needed only for Owner-driven account creation (POST /users); the API must still run without it.
    assert Settings(_env_file=None).supabase_service_role_key is None
    cfg = Settings(_env_file=None, supabase_service_role_key="super-secret-value")
    assert "super-secret-value" not in repr(cfg) and "super-secret-value" not in str(cfg)


def test_blank_placeholders_mean_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_JWT_ISSUER", "SUPABASE_JWT_JWKS_URL"):
        monkeypatch.setenv(name, "")
    cfg = Settings(_env_file=None)
    assert cfg.sqlalchemy_url is None and cfg.supabase_url is None
