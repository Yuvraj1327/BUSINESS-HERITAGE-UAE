import uuid

from app.core.exceptions import ForbiddenError, UnprocessableError
from app.core.permissions import permissions_for
from app.core.security import TokenClaims
from app.models.profile import Profile
from app.repositories.profile_repository import ProfileRepository
from app.schemas.auth import ProfileResponse
from app.schemas.settings import Preferences, ProfileUpdate, avatar_belongs_to


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
            phone=profile.phone,
            avatar_path=profile.avatar_path,
            preferences=self._preferences(profile.user_id),
            must_change_password=profile.must_change_password,
            permissions=permissions_for(profile.role),
        )

    def _preferences(self, user_id: uuid.UUID) -> Preferences:
        """Stored preferences, tolerating old or damaged JSON: anything invalid falls back to the defaults."""
        try:
            return Preferences.model_validate(self.profiles.get_preferences(user_id))
        except ValueError:
            return Preferences()

    def update_own_profile(self, claims: TokenClaims, data: ProfileUpdate) -> ProfileResponse:
        """Self-service edit of name, phone and photo. The target row is the verified token subject, never a
        request value; role, branch and active status are not part of the input and not touched by the database
        function. Fields not sent keep their current value."""
        profile = self.require_ready_profile(claims)
        sent = data.model_fields_set
        avatar = data.avatar_path if "avatar_path" in sent else profile.avatar_path
        if avatar is not None and not avatar_belongs_to(avatar, profile.user_id):
            raise UnprocessableError(
                "Invalid photo.", fields={"avatar_path": ["The photo must be your own upload"]}
            )
        self.profiles.update_own_profile(
            data.full_name if "full_name" in sent and data.full_name else profile.full_name,
            data.phone if "phone" in sent else profile.phone,
            avatar,
        )
        return self.profile_response(claims)

    def save_preferences(self, claims: TokenClaims, preferences: Preferences) -> ProfileResponse:
        profile = self.require_ready_profile(claims)
        self.profiles.save_preferences(profile.user_id, preferences.model_dump())
        return self.profile_response(claims)
