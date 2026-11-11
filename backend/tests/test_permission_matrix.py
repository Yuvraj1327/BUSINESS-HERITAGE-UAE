"""Pure unit tests: the permission matrix and the user-admin policy (no database, no HTTP)."""

import uuid

import pytest

from app.core.permissions import (
    PERMISSION_MATRIX,
    Action,
    Module,
    Principal,
    Role,
    Scope,
    can,
    grant_for,
    permissions_for,
)
from app.services.user_admin_policy import (
    InvalidUserChange,
    TargetUser,
    UserAdminAction,
    UserAdminDenied,
    authorize_user_change,
)

OWNER_ONLY = [
    Module.CASH_BANKS,
    Module.OPENING_BALANCES,
    Module.EXPENSES,
    Module.SUPPLIERS,
    Module.EMPLOYEES,
    Module.VISAS_PASSPORTS,
    Module.TRADE_LICENSES,
    Module.RENTALS_CHEQUES,
    Module.TASKS,
    Module.ALERTS,
    Module.REPORTS,
    Module.USER_MANAGEMENT,
    Module.SETTINGS,
    Module.AUDIT_LOG,
]


def principal(role: Role, branch: uuid.UUID | None = None) -> Principal:
    return Principal(uuid.uuid4(), role, branch, "T")


def test_roles_match_database_values() -> None:
    assert {r.value for r in Role} == {"owner", "branch"}


@pytest.mark.parametrize("module", OWNER_ONLY)
@pytest.mark.parametrize("action", list(Action))
def test_branch_user_denied_on_owner_only_modules(module: Module, action: Action) -> None:
    assert not can(Role.BRANCH_USER, module, action)
    assert grant_for(Role.BRANCH_USER, module) is None


def test_branch_user_allowed_set_is_exactly_this() -> None:
    allowed = {(m, a) for m, g in PERMISSION_MATRIX[Role.BRANCH_USER].items() for a in g.actions}
    assert allowed == {
        (Module.DASHBOARD, Action.READ),
        (Module.BRANCH_MANAGEMENT, Action.READ),
        (Module.DAILY_REPORTS, Action.READ),
        (Module.DAILY_REPORTS, Action.CREATE),
        # Step 13 (customer orders), own branch; no cancel / refund / delete. Assumption O1 awaits Owner approval.
        (Module.ORDERS, Action.READ),
        (Module.ORDERS, Action.CREATE),
        (Module.ORDERS, Action.UPDATE),
        (Module.ORDERS, Action.EXPORT),
        (Module.CUSTOMERS, Action.READ),
        (Module.CUSTOMERS, Action.CREATE),
        (Module.CUSTOMERS, Action.UPDATE),
        (Module.ORDER_PAYMENTS, Action.READ),
        (Module.ORDER_PAYMENTS, Action.CREATE),
    }
    assert all(g.scope is Scope.OWN_BRANCH for g in PERMISSION_MATRIX[Role.BRANCH_USER].values())


@pytest.mark.parametrize(
    "action", [Action.UPDATE, Action.DELETE, Action.EXPORT, Action.APPROVE, Action.MANAGE]
)
def test_branch_user_cannot_modify_reports_or_manage(action: Action) -> None:
    assert not can(Role.BRANCH_USER, Module.DAILY_REPORTS, action)
    assert not can(Role.BRANCH_USER, Module.BRANCH_MANAGEMENT, action)


def test_owner_covers_every_module_across_all_branches() -> None:
    assert set(PERMISSION_MATRIX[Role.OWNER]) == set(Module)
    for m, g in PERMISSION_MATRIX[Role.OWNER].items():
        assert g.scope is Scope.ALL_BRANCHES and Action.READ in g.actions, m


def test_nobody_can_delete_reports_or_approve_yet() -> None:
    for role in Role:
        assert not can(role, Module.DAILY_REPORTS, Action.DELETE)
        for m in Module:
            assert not can(role, m, Action.APPROVE)


@pytest.mark.parametrize("bad", ["", "admin", "OWNER", "superuser", None])
def test_unknown_role_gets_nothing(bad: object) -> None:
    assert not can(bad, Module.DASHBOARD, Action.READ)  # type: ignore[arg-type]
    assert permissions_for(bad) == {}  # type: ignore[arg-type]


def test_permissions_payload_shape() -> None:
    p = permissions_for("branch")
    assert p["daily_reports"] == {"actions": ["create", "read"], "scope": "own_branch"}
    assert "suppliers" not in p and "user_management" not in p


# ---- user admin policy ------------------------------------------------------------------------------------
def test_only_owner_may_administer_users() -> None:
    branch = principal(Role.BRANCH_USER, uuid.uuid4())
    for a in UserAdminAction:
        with pytest.raises(UserAdminDenied):
            authorize_user_change(branch, a, TargetUser(uuid.uuid4(), Role.BRANCH_USER, True))


def test_owner_can_create_branch_user_with_branch() -> None:
    owner = principal(Role.OWNER)
    authorize_user_change(
        owner,
        UserAdminAction.CREATE_BRANCH_USER,
        new_role=Role.BRANCH_USER,
        new_branch_id=uuid.uuid4(),
    )
    with pytest.raises(InvalidUserChange):
        authorize_user_change(owner, UserAdminAction.CREATE_BRANCH_USER, new_role=Role.BRANCH_USER)
    with pytest.raises(InvalidUserChange):
        authorize_user_change(
            owner,
            UserAdminAction.CREATE_BRANCH_USER,
            new_role=Role.OWNER,
            new_branch_id=uuid.uuid4(),
        )


def test_owner_cannot_change_own_role_branch_or_status() -> None:
    owner = principal(Role.OWNER)
    me = TargetUser(owner.user_id, Role.OWNER, True)
    with pytest.raises(UserAdminDenied):
        authorize_user_change(owner, UserAdminAction.DEACTIVATE, me)
    with pytest.raises(UserAdminDenied):
        authorize_user_change(owner, UserAdminAction.UPDATE_PROFILE, me, new_role=Role.BRANCH_USER)


def test_last_owner_cannot_be_deactivated() -> None:
    owner = principal(Role.OWNER)
    other_owner = TargetUser(uuid.uuid4(), Role.OWNER, True)
    with pytest.raises(InvalidUserChange):
        authorize_user_change(owner, UserAdminAction.DEACTIVATE, other_owner, active_owner_count=1)
    authorize_user_change(owner, UserAdminAction.DEACTIVATE, other_owner, active_owner_count=2)


def test_owner_has_no_branch_assignment() -> None:
    with pytest.raises(InvalidUserChange):
        authorize_user_change(
            principal(Role.OWNER),
            UserAdminAction.ASSIGN_BRANCH,
            TargetUser(uuid.uuid4(), Role.OWNER, True),
            new_branch_id=uuid.uuid4(),
        )


# ---- BranchScope (application-layer branch guard), independent of the database -------------------------------
def _scope(role: Role, branch: uuid.UUID | None):
    from unittest.mock import MagicMock

    from app.api.authz import BranchScope

    session = MagicMock()
    grant = grant_for(role, Module.DAILY_REPORTS)
    assert grant is not None
    return BranchScope(principal(role, branch), grant.scope, session, "daily_reports"), session


def test_branch_scope_owner_allows_any_branch_and_none_means_all() -> None:
    scope, _ = _scope(Role.OWNER, None)
    b = uuid.uuid4()
    assert scope.ensure(b) == b and scope.resolve(None) is None and scope.resolve(b) == b


def test_branch_scope_branch_user_is_pinned_to_own_branch() -> None:
    from app.api.authz import BranchAccessDeniedError

    mine, other = uuid.uuid4(), uuid.uuid4()
    scope, session = _scope(Role.BRANCH_USER, mine)
    assert scope.resolve(None) == mine and scope.resolve(mine) == mine
    with pytest.raises(BranchAccessDeniedError):
        scope.resolve(other)
    with pytest.raises(BranchAccessDeniedError):
        scope.ensure(other)
    with pytest.raises(BranchAccessDeniedError):
        scope.ensure(None)
    assert session.commit.called  # denials are persisted to the audit log


def test_branch_user_without_assigned_branch_matches_nothing() -> None:
    from app.api.authz import BranchAccessDeniedError

    scope, _ = _scope(Role.BRANCH_USER, None)
    with pytest.raises(BranchAccessDeniedError):
        scope.ensure(uuid.uuid4())
    with pytest.raises(BranchAccessDeniedError):
        scope.resolve(None)  # must never widen to "all branches"
