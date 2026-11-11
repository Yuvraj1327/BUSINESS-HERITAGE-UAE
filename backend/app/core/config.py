"""Application settings (environment variables, validated at startup).

Only placeholders live in .env.example. Real secrets come from the process environment / a git-ignored
.env file. The service-role key is optional and used only by account provisioning (POST /users).
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Self

from pydantic import AnyHttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_name: str = "ALSAFA Heritage Laundry API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    # None => JSON logs in production, readable logs elsewhere.
    log_json: bool | None = None

    database_url: SecretStr | None = None

    supabase_url: AnyHttpUrl | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_jwks_url: AnyHttpUrl | None = None
    supabase_jwt_audience: str = "authenticated"
    # JWKS cache: keys are re-fetched after the TTL, or (rate-limited) when a token names an unknown `kid`.
    jwks_cache_ttl_seconds: int = 600
    jwks_refresh_cooldown_seconds: int = 60
    # If a refresh fails, previously fetched keys may be used for at most this long past their TTL.
    jwks_max_stale_seconds: int = 3600
    jwt_leeway_seconds: int = 10

    # Optional. Needed for Owner-driven account creation (POST /users) and the first-login password change
    # (POST /auth/change-password): the API then calls the Supabase Auth Admin API. Never sent to the browser,
    # never logged. Without it the API still runs and those endpoints answer 503 "not configured".
    supabase_service_role_key: SecretStr | None = None
    # Owner's account-provisioning decision: mark the email of Owner-created Branch Users as confirmed so they can
    # sign in immediately. If false, Supabase requires them to confirm the email first (they cannot sign in until then).
    provision_email_confirmed: bool = True
    # Only used by the operator script (scripts/provision_account.py) and "Forgot password" emails; the Branch User
    # creation flow sends no email.
    password_reset_redirect_url: str | None = None

    # Comma-separated in the environment, e.g. "http://localhost:5173,https://erp.example.com"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator(
        "database_url",
        "supabase_url",
        "supabase_jwt_issuer",
        "supabase_jwt_jwks_url",
        "supabase_service_role_key",
        "password_reset_redirect_url",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, v: object) -> object:
        # `.env.example` ships blank placeholders (e.g. DATABASE_URL=); treat them as "not configured".
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip().rstrip("/") for o in v.split(",") if o.strip()]
        return v

    @field_validator("cors_origins")
    @classmethod
    def _check_origins(cls, v: list[str]) -> list[str]:
        for origin in v:
            if not origin.startswith(("http://", "https://")):
                raise ValueError(
                    f"CORS origin must start with http:// or https:// (got {origin!r})"
                )
        return v

    @field_validator("log_level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        level = v.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid LOG_LEVEL {v!r}")
        return level

    @model_validator(mode="after")
    def _derive_and_validate(self) -> Self:
        # Supabase's standard issuer/JWKS locations can be derived from SUPABASE_URL.
        if self.supabase_url is not None:
            base = str(self.supabase_url).rstrip("/")
            if self.supabase_jwt_issuer is None:
                self.supabase_jwt_issuer = f"{base}/auth/v1"
            if self.supabase_jwt_jwks_url is None:
                self.supabase_jwt_jwks_url = AnyHttpUrl(f"{base}/auth/v1/.well-known/jwks.json")

        if self.app_env is AppEnv.PRODUCTION:
            missing = [
                name
                for name, value in {
                    "DATABASE_URL": self.database_url,
                    "SUPABASE_URL": self.supabase_url,
                    "SUPABASE_JWT_ISSUER": self.supabase_jwt_issuer,
                    "SUPABASE_JWT_JWKS_URL": self.supabase_jwt_jwks_url,
                }.items()
                if value is None
            ]
            if missing:
                raise ValueError(f"required in production: {', '.join(missing)}")
            for name, url in {
                "SUPABASE_URL": self.supabase_url,
                "SUPABASE_JWT_JWKS_URL": self.supabase_jwt_jwks_url,
            }.items():
                if url is not None and url.scheme != "https":
                    raise ValueError(f"{name} must use https in production")
            if "*" in self.cors_origins:
                raise ValueError(
                    "CORS_ORIGINS must list explicit origins in production (no wildcard)"
                )
            if any(
                o.startswith("http://localhost") or o.startswith("http://127.")
                for o in self.cors_origins
            ):
                raise ValueError("CORS_ORIGINS must not include localhost origins in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def use_json_logs(self) -> bool:
        return self.is_production if self.log_json is None else self.log_json

    @property
    def sqlalchemy_url(self) -> str | None:
        """DATABASE_URL normalised to the psycopg 3 driver; None when not configured."""
        if self.database_url is None:
            return None
        url = self.database_url.get_secret_value().strip()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
