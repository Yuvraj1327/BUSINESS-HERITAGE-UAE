import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.exceptions import NotFoundError
from app.core.permissions import Action, Module, Principal
from app.repositories.profile_repository import ProfileRepository
from app.schemas.rbac import UserOut

router = APIRouter(prefix="/users", tags=["users"])

# Read-only on purpose. Create / assign branch / activate / deactivate / update will be added with the User
# Management feature, guarded by app.services.user_admin_policy.authorize_user_change.
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
