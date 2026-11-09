from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentClaims, get_auth_service
from app.schemas.auth import AuthMeResponse, ProfileResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

# There is deliberately no /auth/logout: sign-out is a Supabase client operation, and an issued access token
# stays valid until it expires (short-lived). Pretending a server endpoint could revoke it would be false.


@router.get("/me", response_model=AuthMeResponse, summary="Identity proven by the access token")
def me(claims: CurrentClaims) -> AuthMeResponse:
    return AuthMeResponse(
        user_id=claims.user_id,
        email=claims.email,
        session_id=claims.session_id,
        expires_at=claims.expires_at,
    )


@router.get(
    "/profile", response_model=ProfileResponse, summary="Profile of the signed-in (active) user"
)
def profile(
    claims: CurrentClaims, service: Annotated[AuthService, Depends(get_auth_service)]
) -> ProfileResponse:
    return service.profile_response(claims)
