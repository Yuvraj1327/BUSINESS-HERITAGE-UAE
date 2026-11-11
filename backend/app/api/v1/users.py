import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.authz import CurrentPrincipal, require_permission
from app.api.deps import DbSession
from app.core.exceptions import NotFoundError
from app.core.permissions import Action, Module, Principal
from app.repositories.profile_repository import ProfileRepository
from app.schemas.rbac import UserCreate, UserOut
from app.services.user_provisioning_service import UserProvisioningService

router = APIRouter(prefix="/users", tags=["users"])

# Create is Owner-only and Branch-User-only (app.services.user_admin_policy.authorize_user_change); the database
# enforces the same rules again (RLS owner-only writes, role/branch CHECK). Deactivation: scripts/provision_account.py.
OwnerReadUsers = Annotated[
    Principal, Depends(require_permission(Module.USER_MANAGEMENT, Action.READ))
]


@router.get("", response_model=list[UserOut], summary="All user profiles (Owner only)")
def list_users(_p: OwnerReadUsers, session: DbSession) -> list[UserOut]:
    return [
        UserOut.model_validate(p, from_attributes=True)
        for p in ProfileRepository(session).list_all()
    ]


@router.get("/{user_id}", response_model=UserOut, summary="One user profile (Owner only)")
def get_user(user_id: uuid.UUID, _p: OwnerReadUsers, session: DbSession) -> UserOut:
    profile = ProfileRepository(session).get(user_id)
    if profile is None:
        raise NotFoundError("User not found")
    return UserOut.model_validate(profile, from_attributes=True)


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Branch User account (Owner only)",
)
def create_user(
    body: UserCreate, request: Request, principal: CurrentPrincipal, session: DbSession
) -> UserOut:
    """Creates the Auth user with the Owner's initial password and its profile (role 'branch', must change the
    password on first login). No email is sent; the new user can sign in immediately."""
    # The permission check lives in the service (authorize_user_change) so it cannot be skipped by a caller.
    service = UserProvisioningService(ProfileRepository(session), request.app.state.settings)
    profile = service.create_branch_user(principal, body)
    return UserOut.model_validate(profile, from_attributes=True)
