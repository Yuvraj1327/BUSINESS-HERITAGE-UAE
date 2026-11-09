"""Authorization rules for the planned Owner user-management actions (Step 5 foundation).

Pure functions: no database, no HTTP, no write endpoints yet. A future user-management service calls
`authorize_user_change` BEFORE touching `profiles`; the database independently enforces the same rules
(RLS owner-only writes, last-owner guard, self-change guard: migrations 0008 and 0010).

Only an active Owner may change roles, branch assignments or active status; nobody may do it to themselves.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.core.exceptions import AppError, ForbiddenError
from app.core.permissions import Action, Module, Principal, Role


class UserAdminAction(StrEnum):
    CREATE_BRANCH_USER = "create_branch_user"
    ASSIGN_BRANCH = "assign_branch"
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    VIEW_PROFILE = "view_profile"
    UPDATE_PROFILE = "update_profile"  # display name etc. -- NOT role/branch/active
    RESET_ACCESS = "reset_access"  # triggers the authorized reset process (password email); never sets a password


_MODULE_ACTION: dict[UserAdminAction, Action] = {
    UserAdminAction.CREATE_BRANCH_USER: Action.CREATE,
    UserAdminAction.ASSIGN_BRANCH: Action.MANAGE,
    UserAdminAction.ACTIVATE: Action.MANAGE,
    UserAdminAction.DEACTIVATE: Action.MANAGE,
    UserAdminAction.VIEW_PROFILE: Action.READ,
    UserAdminAction.UPDATE_PROFILE: Action.UPDATE,
    UserAdminAction.RESET_ACCESS: Action.MANAGE,
}
_SELF_FORBIDDEN = {
    UserAdminAction.ASSIGN_BRANCH,
    UserAdminAction.DEACTIVATE,
    UserAdminAction.ACTIVATE,
}


@dataclass(frozen=True)
class TargetUser:
    user_id: uuid.UUID
    role: Role
    is_active: bool


class UserAdminDenied(ForbiddenError):
    code = "user_admin_denied"


class InvalidUserChange(AppError):
    status_code, code = 422, "invalid_user_change"


def authorize_user_change(
    actor: Principal,
    action: UserAdminAction,
    target: TargetUser | None = None,
    *,
    new_role: Role | None = None,
    new_branch_id: uuid.UUID | None = None,
    active_owner_count: int | None = None,
) -> None:
    """Raise unless `actor` may perform `action`. `actor` must come from the trusted profile (see api/authz.py)."""
    if not actor.can(Module.USER_MANAGEMENT, _MODULE_ACTION[action]):
        raise UserAdminDenied("You do not have permission to manage users.")

    if action in _SELF_FORBIDDEN and target is not None and target.user_id == actor.user_id:
        raise UserAdminDenied("You cannot change your own branch or active status.")
    if (
        new_role is not None
        and target is not None
        and target.user_id == actor.user_id
        and new_role != actor.role
    ):
        raise UserAdminDenied("You cannot change your own role.")

    if action is UserAdminAction.CREATE_BRANCH_USER:
        if new_role not in (None, Role.BRANCH_USER):
            raise InvalidUserChange("Only Branch User accounts can be created here.")
        if new_branch_id is None:
            raise InvalidUserChange("A Branch User must be assigned to exactly one branch.")
    if action is UserAdminAction.ASSIGN_BRANCH:
        if target is not None and target.role is Role.OWNER:
            raise InvalidUserChange("An Owner has no branch assignment.")
        if new_branch_id is None:
            raise InvalidUserChange("A branch is required.")
    if (
        action is UserAdminAction.DEACTIVATE
        and target is not None
        and target.role is Role.OWNER
        and target.is_active
        and active_owner_count is not None
        and active_owner_count <= 1
    ):
        raise InvalidUserChange("The last active Owner cannot be deactivated.")
