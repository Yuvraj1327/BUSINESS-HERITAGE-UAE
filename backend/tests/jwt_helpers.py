"""Locally generated signing keys + token minting. No network, no Supabase."""

import json
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

ISSUER = "https://abcd.supabase.test/auth/v1"
AUDIENCE = "authenticated"


class KeyPair:
    def __init__(self, kid: str, kind: str = "ES256") -> None:
        self.kid, self.alg = kid, kind
        if kind == "ES256":
            self.private = ec.generate_private_key(ec.SECP256R1())
            algo: Any = ECAlgorithm(ECAlgorithm.SHA256)
        else:
            self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            algo = RSAAlgorithm(RSAAlgorithm.SHA256)
        jwk = json.loads(algo.to_jwk(self.private.public_key()))
        jwk.update({"kid": kid, "alg": kind, "use": "sig"})
        self.jwk = jwk

    def sign(
        self, payload: dict[str, Any], *, kid: str | None = None, alg: str | None = None
    ) -> str:
        return jwt.encode(
            payload, self.private, algorithm=alg or self.alg, headers={"kid": kid or self.kid}
        )


_UNSET: Any = object()


def claims(sub: Any = _UNSET, **over: Any) -> dict[str, Any]:
    """Default valid claims. Pass `key=None` to drop a claim (including `sub=None`)."""
    now = int(time.time())
    base: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(uuid.uuid4()) if sub is _UNSET else (None if sub is None else str(sub)),
        "role": "authenticated",
        "email": "person@example.test",
        "session_id": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 3600,
        "aal": "aal1",
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


class FakeJwks:
    """A fetcher whose key set and failure mode the test controls; counts fetches."""

    def __init__(self, *pairs: KeyPair) -> None:
        self.pairs = list(pairs)
        self.calls = 0
        self.fail = False

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("jwks endpoint down")
        return {"keys": [p.jwk for p in self.pairs]}
