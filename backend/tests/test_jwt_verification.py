import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.security import TokenVerifier
from app.main import create_app
from tests.conftest import make_settings
from tests.jwt_helpers import ISSUER, FakeJwks, KeyPair, claims

SUPABASE = {"supabase_url": "https://abcd.supabase.test"}


def build(fake: FakeJwks, **settings_over: object) -> tuple[TestClient, TokenVerifier, FakeJwks]:
    settings = make_settings(**SUPABASE, **settings_over)
    app = create_app(settings)
    verifier = TokenVerifier(settings, fetcher=fake)
    app.state.token_verifier = verifier
    return TestClient(app, raise_server_exceptions=False), verifier, fake


@pytest.fixture()
def key() -> KeyPair:
    return KeyPair("kid-1")


def get_me(client: TestClient, token: str | None, scheme: str = "Bearer"):
    headers = {} if token is None else {"Authorization": f"{scheme} {token}"}
    return client.get("/api/v1/auth/me", headers=headers)


def assert_401(resp, code: str) -> None:
    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["code"] == code
    assert resp.headers["www-authenticate"] == "Bearer"


def test_issuer_derived_from_supabase_url() -> None:
    s = make_settings(**SUPABASE)
    assert s.supabase_jwt_issuer == ISSUER
    assert (
        str(s.supabase_jwt_jwks_url) == "https://abcd.supabase.test/auth/v1/.well-known/jwks.json"
    )


def test_valid_es256_token(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    uid = uuid.uuid4()
    r = get_me(client, key.sign(claims(uid)))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == str(uid) and body["authenticated"] is True
    assert set(body) == {"user_id", "email", "session_id", "expires_at", "authenticated"}


def test_valid_rs256_token() -> None:
    k = KeyPair("rsa-1", "RS256")
    client, *_ = build(FakeJwks(k))
    assert get_me(client, k.sign(claims())).status_code == 200


def test_missing_token(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, None), "not_authenticated")


@pytest.mark.parametrize("scheme", ["Basic", "Token", ""])
def test_wrong_scheme(key: KeyPair, scheme: str) -> None:
    client, *_ = build(FakeJwks(key))
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"{scheme} abc".strip()})
    assert_401(r, "not_authenticated")


@pytest.mark.parametrize("junk", ["abc", "a.b.c", "x" * 9000, "..", "eyJ.eyJ.sig"])
def test_malformed_token(key: KeyPair, junk: str) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, junk), "invalid_token")


def test_expired_token(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    past = int(time.time()) - 3600
    assert_401(get_me(client, key.sign(claims(iat=past - 60, exp=past))), "token_expired")


def test_expiry_leeway_is_small(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    just = int(time.time()) - 3  # inside 10s leeway
    assert get_me(client, key.sign(claims(exp=just))).status_code == 200
    assert_401(get_me(client, key.sign(claims(exp=int(time.time()) - 60))), "token_expired")


def test_wrong_issuer(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, key.sign(claims(iss="https://evil.test/auth/v1"))), "invalid_token")


def test_wrong_audience(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, key.sign(claims(aud="other"))), "invalid_token")


@pytest.mark.parametrize("missing", ["exp", "sub", "iss", "aud"])
def test_required_claims(key: KeyPair, missing: str) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, key.sign(claims(**{missing: None}))), "invalid_token")


def test_non_uuid_subject(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, key.sign(claims(sub="not-a-uuid"))), "invalid_token")


@pytest.mark.parametrize("role", ["anon", "service_role", None])
def test_non_user_roles_rejected(key: KeyPair, role: str | None) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, key.sign(claims(role=role))), "invalid_token")


def test_anonymous_sign_in_rejected(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, key.sign(claims(is_anonymous=True))), "invalid_token")


def test_signature_from_unknown_key(key: KeyPair) -> None:
    attacker = KeyPair("kid-1")  # same kid, different key material
    client, *_ = build(FakeJwks(key))
    assert_401(get_me(client, attacker.sign(claims())), "invalid_token")


def test_tampered_payload(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    h, p, s = key.sign(claims()).split(".")
    other = key.sign(claims(sub=uuid.uuid4())).split(".")[1]
    assert_401(get_me(client, f"{h}.{other}.{s}"), "invalid_token")


def test_alg_none_rejected(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    tok = jwt.encode(claims(), None, algorithm="none", headers={"kid": "kid-1"})
    assert_401(get_me(client, tok), "invalid_token")


def test_hs256_algorithm_confusion_rejected(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    tok = jwt.encode(claims(), "x" * 64, algorithm="HS256", headers={"kid": "kid-1"})
    assert_401(get_me(client, tok), "invalid_token")


def test_missing_kid_rejected(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    tok = jwt.encode(claims(), key.private, algorithm="ES256")
    assert_401(get_me(client, tok), "invalid_token")


# ---- JWKS cache / rotation ------------------------------------------------------------------------------


def test_jwks_cached_between_requests(key: KeyPair) -> None:
    client, _, fake = build(FakeJwks(key))
    for _ in range(5):
        assert get_me(client, key.sign(claims())).status_code == 200
    assert fake.calls == 1


def test_key_rotation_refreshes_on_unknown_kid(key: KeyPair) -> None:
    fake = FakeJwks(key)
    client, verifier, _ = build(fake)
    assert get_me(client, key.sign(claims())).status_code == 200
    new = KeyPair("kid-2")
    fake.pairs = [key, new]
    verifier.cache._last_attempt -= 120  # cooldown elapsed
    assert get_me(client, new.sign(claims())).status_code == 200
    assert fake.calls == 2
    assert (
        get_me(client, key.sign(claims())).status_code == 200
    )  # old key still valid during rollover


def test_unknown_kid_refresh_is_rate_limited(key: KeyPair) -> None:
    client, _, fake = build(FakeJwks(key))
    get_me(client, key.sign(claims()))
    stranger = KeyPair("nope")
    for _ in range(10):
        assert_401(get_me(client, stranger.sign(claims())), "invalid_token")
    assert fake.calls == 1  # cooldown prevents hammering the auth server


def test_jwks_down_at_start_fails_closed(key: KeyPair) -> None:
    fake = FakeJwks(key)
    fake.fail = True
    client, *_ = build(fake)
    r = get_me(client, key.sign(claims()))
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_keys_unavailable"


def test_stale_keys_served_briefly_then_fail_closed(key: KeyPair) -> None:
    now = [1000.0]
    fake = FakeJwks(key)
    settings = make_settings(
        **SUPABASE,
        jwks_cache_ttl_seconds=100,
        jwks_refresh_cooldown_seconds=10,
        jwks_max_stale_seconds=500,
    )
    from app.core.security import JwksCache

    cache = JwksCache(fake, ttl=100, cooldown=10, max_stale=500, clock=lambda: now[0])
    cache.get_key("kid-1")
    fake.fail = True
    now[0] += 200  # past TTL, refresh fails -> stale key still usable
    assert cache.get_key("kid-1") is not None
    now[0] += 600  # past TTL + max_stale -> fail closed
    from app.core.security import AuthKeysUnavailableError

    with pytest.raises(AuthKeysUnavailableError):
        cache.get_key("kid-1")
    assert settings.jwks_max_stale_seconds == 500


def test_identity_never_taken_from_body_or_headers(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    uid, other = uuid.uuid4(), uuid.uuid4()
    r = client.get(
        "/api/v1/auth/me",
        params={"user_id": str(other)},
        headers={"Authorization": f"Bearer {key.sign(claims(uid))}", "X-User-Id": str(other)},
    )
    assert r.json()["user_id"] == str(uid)


def test_auth_not_configured_is_503() -> None:
    client = TestClient(create_app(make_settings()), raise_server_exceptions=False)
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 503


def test_error_does_not_leak_details(key: KeyPair) -> None:
    client, *_ = build(FakeJwks(key))
    r = get_me(client, key.sign(claims(aud="other")))
    assert "aud" not in r.text.lower() and "Traceback" not in r.text


def test_production_requires_https_supabase() -> None:
    with pytest.raises(ValueError, match="https"):
        make_settings(
            app_env="production",
            database_url="postgresql://x",
            supabase_url="http://abcd.supabase.test",
            cors_origins="https://erp.example.com",
        )
