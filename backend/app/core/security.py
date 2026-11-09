"""Supabase access-token verification (JWKS).

Rules enforced for every token:
* Algorithm allow-list: asymmetric only (ES256 / RS256). `none` and HS* are rejected, so a token signed with a
  public key used as an HMAC secret (algorithm confusion) can never verify.
* Signature is checked against a key from the project's JWKS, chosen by `kid`.
* `iss` must equal the configured issuer, `aud` the configured audience, `exp` must be in the future (small
  leeway), and `sub` must be a UUID.
* The anonymous/service API-key JWTs (role `anon` / `service_role`) are rejected: only end-user sessions pass.

Identity is taken from the verified token only; nothing from request bodies or other headers.
"""

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from jwt import PyJWK

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError, UnauthorizedError

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS = ("ES256", "RS256")
_BEARER = {"WWW-Authenticate": "Bearer"}


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"

    def __init__(self, message: str = "Invalid authentication token", *, code: str | None = None):
        super().__init__(message, code=code, headers=_BEARER)


class TokenExpiredError(InvalidTokenError):
    code = "token_expired"

    def __init__(self) -> None:
        super().__init__("Your session has expired. Please sign in again.", code="token_expired")


class NotAuthenticatedError(UnauthorizedError):
    code = "not_authenticated"

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, headers=_BEARER)


class AuthKeysUnavailableError(ServiceUnavailableError):
    code = "auth_keys_unavailable"


@dataclass(frozen=True)
class TokenClaims:
    """The verified, minimal view of an access token. `raw` is kept only to forward to the database (RLS)."""

    user_id: uuid.UUID
    email: str | None
    session_id: str | None
    issued_at: int | None
    expires_at: int
    aal: str | None
    raw: dict[str, Any] = field(repr=False, compare=False, default_factory=dict)


JwksFetcher = Callable[[], dict[str, Any]]


def http_jwks_fetcher(url: str, timeout: float = 5.0) -> JwksFetcher:
    def fetch() -> dict[str, Any]:
        resp = httpx.get(url, timeout=timeout, follow_redirects=False)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            raise ValueError("JWKS response has no 'keys' list")
        return data

    return fetch


class JwksCache:
    """Thread-safe JWKS cache.

    * Fresh for `ttl` seconds.
    * Unknown `kid` (key rotation) triggers one refresh, at most once per `cooldown` seconds, so garbage
      tokens cannot make us hammer the auth server.
    * If a refresh fails, the last good keys keep working for at most `max_stale` seconds past expiry; after
      that verification fails closed (503).
    """

    def __init__(
        self,
        fetcher: JwksFetcher,
        *,
        ttl: float,
        cooldown: float,
        max_stale: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetcher
        self._ttl, self._cooldown, self._max_stale = ttl, cooldown, max_stale
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None

    def _refresh_locked(self) -> None:
        now = self._clock()
        self._last_attempt = now
        try:
            data = self._fetch()
            keys: dict[str, PyJWK] = {}
            for jwk in data["keys"]:
                try:
                    kid = jwk.get("kid")
                    if kid and jwk.get("alg", "ES256") in ALLOWED_ALGORITHMS:
                        keys[kid] = PyJWK.from_dict(jwk)
                except Exception:  # noqa: BLE001 - skip one unusable key (e.g. unsupported type), keep the rest
                    logger.warning("ignoring unusable JWKS entry")
            if not keys:
                raise ValueError("JWKS contains no usable signing keys")
        except Exception as exc:  # noqa: BLE001 - any fetch/parse failure must fall back to cached keys
            logger.warning("JWKS refresh failed: %s", type(exc).__name__)
            return
        self._keys, self._fetched_at = keys, now

    def get_key(self, kid: str) -> PyJWK:
        with self._lock:
            now = self._clock()
            expired = self._fetched_at is None or now - self._fetched_at >= self._ttl
            can_retry = self._last_attempt is None or now - self._last_attempt >= self._cooldown
            if (expired or kid not in self._keys) and can_retry:
                self._refresh_locked()
                now = self._clock()
            if self._fetched_at is None or now - self._fetched_at > self._ttl + self._max_stale:
                self._keys = {}
                raise AuthKeysUnavailableError("Authentication service is temporarily unavailable")
            key = self._keys.get(kid)
        if key is None:
            raise InvalidTokenError()  # unknown kid: indistinguishable from any other bad token
        return key


class TokenVerifier:
    def __init__(self, settings: Settings, fetcher: JwksFetcher | None = None) -> None:
        issuer = settings.supabase_jwt_issuer
        jwks_url = settings.supabase_jwt_jwks_url
        if issuer is None or (fetcher is None and jwks_url is None):
            raise AuthKeysUnavailableError("Supabase authentication is not configured")
        self._issuer = issuer
        self._audience = settings.supabase_jwt_audience
        self._leeway = settings.jwt_leeway_seconds
        self.cache = JwksCache(
            fetcher or http_jwks_fetcher(str(jwks_url)),
            ttl=settings.jwks_cache_ttl_seconds,
            cooldown=settings.jwks_refresh_cooldown_seconds,
            max_stale=settings.jwks_max_stale_seconds,
        )

    def verify(self, token: str) -> TokenClaims:
        if not token or len(token) > 8192:
            raise InvalidTokenError()
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise InvalidTokenError() from None
        alg, kid = header.get("alg"), header.get("kid")
        if alg not in ALLOWED_ALGORITHMS or not isinstance(kid, str) or not kid:
            raise InvalidTokenError()
        key = self.cache.get_key(kid)
        try:
            payload = jwt.decode(
                token,
                key.key,
                algorithms=[alg],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError() from None
        except jwt.PyJWTError:
            raise InvalidTokenError() from None

        if payload.get("role") != "authenticated" or payload.get("is_anonymous") is True:
            raise InvalidTokenError()
        try:
            user_id = uuid.UUID(str(payload["sub"]))
        except ValueError:
            raise InvalidTokenError() from None
        email = payload.get("email")
        return TokenClaims(
            user_id=user_id,
            email=email if isinstance(email, str) else None,
            session_id=payload.get("session_id")
            if isinstance(payload.get("session_id"), str)
            else None,
            issued_at=payload.get("iat") if isinstance(payload.get("iat"), int) else None,
            expires_at=int(payload["exp"]),
            aal=payload.get("aal") if isinstance(payload.get("aal"), str) else None,
            raw=payload,
        )


def claims_for_database(claims: TokenClaims) -> str:
    """The JSON placed in `request.jwt.claims` so `auth.uid()` resolves. Only verified, minimal fields."""
    return json.dumps({"sub": str(claims.user_id), "role": "authenticated"}, separators=(",", ":"))
