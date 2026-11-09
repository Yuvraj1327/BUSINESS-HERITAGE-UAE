from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import NotAuthenticatedError, TokenClaims, TokenVerifier
from app.database.session import Database
from app.models.profile import Profile
from app.repositories.profile_repository import ProfileRepository
from app.services.auth_service import AuthService


def get_app_settings(request: Request) -> Settings:
    """Settings bound to this app instance (lets tests inject their own)."""
    return request.app.state.settings  # type: ignore[no-any-return]


def get_token_verifier(request: Request) -> TokenVerifier:
    state = request.app.state
    if state.token_verifier is None:
        state.token_verifier = TokenVerifier(state.settings)
    return state.token_verifier  # type: ignore[no-any-return]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if not header:
        raise NotAuthenticatedError()
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise NotAuthenticatedError("Authorization header must be 'Bearer <token>'")
    return token.strip()


def get_token_claims(
    request: Request, verifier: Annotated[TokenVerifier, Depends(get_token_verifier)]
) -> TokenClaims:
    """Verified identity from the Authorization header ONLY (never from body, query or other headers)."""
    return verifier.verify(_bearer_token(request))


CurrentClaims = Annotated[TokenClaims, Depends(get_token_claims)]


def get_db_session(request: Request, claims: CurrentClaims) -> Iterator[Session]:
    db: Database = request.app.state.db
    yield from db.session_for(claims)


DbSession = Annotated[Session, Depends(get_db_session)]


def get_auth_service(session: DbSession) -> AuthService:
    return AuthService(ProfileRepository(session))


def get_current_profile(
    claims: CurrentClaims, service: Annotated[AuthService, Depends(get_auth_service)]
) -> Profile:
    """Reusable dependency for protected routes: verified token + existing, ACTIVE profile (403 otherwise)."""
    return service.require_active_profile(claims)


CurrentProfile = Annotated[Profile, Depends(get_current_profile)]
