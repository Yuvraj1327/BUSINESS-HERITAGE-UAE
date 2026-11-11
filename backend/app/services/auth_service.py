from app.core.exceptions import ForbiddenError
from app.core.permissions import permissions_for
from app.core.security import TokenClaims
from app.models.profile import Profile
from app.repositories.profile_repository import ProfileRepository
from app.schemas.auth import ProfileResponse


class ProfileMissingError(ForbiddenError):
    code = "profile_missing"

    def __init__(self) -> None:
        super().__init__("Your account is not set up yet. Please contact the administrator.")


class AccountInactiveError(ForbiddenError):
    code = "account_inactive"

    def __init__(self) -> None:
        super().__init__("This account is inactive. Please contact the administrator.")


class PasswordChangeRequiredError(ForbiddenError):
    code = "password_change_required"

    def __init__(self) -> None:
        super().__init__("You must change your password before continuing.")


class AuthService:
    def __init__(self, profiles: ProfileRepository) -> None:
        self.profiles = profiles

    def require_active_profile(self, claims: TokenClaims) -> Profile:
        """The profile is looked up by the VERIFIED token subject only; user metadata is never consulted."""
        profile = self.profiles.get(claims.user_id)
        if profile is None:
            raise ProfileMissingError()
        if not profile.is_active:
            raise AccountInactiveError()
        return profile

    def require_ready_profile(self, claims: TokenClaims) -> Profile:
        """Active profile AND no pending first-login password change. Used by every business route."""
        profile = self.require_active_profile(claims)
        if profile.must_change_password:
            raise PasswordChangeRequiredError()
        return profile

    def profile_response(self, claims: TokenClaims) -> ProfileResponse:
        profile = self.require_active_profile(claims)
        return ProfileResponse(
            user_id=profile.user_id,
            full_name=profile.full_name,
            role=profile.role,  # type: ignore[arg-type]
            branch_id=profile.branch_id,
            branch_name=self.profiles.branch_name(profile.branch_id),
            is_active=profile.is_active,
            must_change_password=profile.must_change_password,
            permissions=permissions_for(profile.role),
        )
