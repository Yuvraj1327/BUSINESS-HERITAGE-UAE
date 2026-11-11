from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import CurrentClaims, DbSession, get_auth_service
from app.repositories.profile_repository import ProfileRepository
from app.schemas.auth import AuthMeResponse, ChangePasswordRequest, ProfileResponse
from app.services.auth_service import AuthService
from app.services.user_provisioning_service import change_own_password

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


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password for the signed-in user (clears the first-login requirement)",
)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    claims: CurrentClaims,
    session: DbSession,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Deliberately NOT behind the first-login gate: it is the one thing a user with a pending change may do.
    The user id comes from the verified token only. The password is forwarded to Supabase Auth, never stored/logged."""
    profile = service.require_active_profile(claims)
    change_own_password(
        ProfileRepository(session),
        request.app.state.settings,
        profile.user_id,
        body.new_password.get_secret_value(),
    )
