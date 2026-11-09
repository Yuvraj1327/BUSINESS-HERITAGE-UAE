"""Reusable authorization dependencies and branch-isolation helpers.

Chain for a protected route:   verified JWT -> active profile (trusted DB row) -> Principal
                                -> require_permission(module, action)  -> BranchScope / require_branch_access

Nothing here reads a role, branch or user id from a request body, query string, header or token metadata, except
a *requested* branch id, which is only ever compared against the caller's own branch.
Denials are 403 and (for signed-in users) are written to the audit log as ACCESS_DENIED.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import Select, text
from sqlalchemy.orm import Session

from app.api.deps import CurrentProfile, DbSession
from app.core.exceptions import ForbiddenError
from app.core.permissions import Action, Module, Principal, Role, Scope, grant_for

logger = logging.getLogger(__name__)


class PermissionDeniedError(ForbiddenError):
    code = "permission_denied"

    def __init__(self) -> None:
        super().__init__("You do not have permission to do this.")


class BranchAccessDeniedError(ForbiddenError):
    code = "branch_access_denied"

    def __init__(self) -> None:
        # Deliberately identical for "other branch" and "no such branch": no probing of ids.
        super().__init__("You do not have access to this branch.")


def audit_denied(
    session: Session, module: str, action: str, detail: dict[str, Any] | None = None
) -> None:
    """Persist an ACCESS_DENIED audit row for the caller. Never raises; never receives tokens or secrets."""
    try:
        session.execute(
            text("select app.log_access_denied(:m, :a, cast(:d as jsonb))"),
            {"m": module, "a": action, "d": None if detail is None else json.dumps(detail)},
        )
        session.commit()  # the request is about to fail with 403, so commit the audit row now
    except Exception:  # noqa: BLE001 - auditing must never turn a 403 into a 500
        session.rollback()
        logger.warning("could not write access-denied audit event")


def get_principal(profile: CurrentProfile) -> Principal:
    """Principal built from the trusted profile row (already verified active by get_current_profile)."""
    return Principal(
        user_id=profile.user_id,
        role=Role(profile.role),
        branch_id=profile.branch_id,
        full_name=profile.full_name,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_permission(module: Module, action: Action) -> Callable[..., Principal]:
    """Dependency factory: caller's role must hold `action` on `module` (default deny)."""

    def dependency(principal: CurrentPrincipal, session: DbSession) -> Principal:
        if not principal.can(module, action):
            audit_denied(session, module.value, action.value)
            raise PermissionDeniedError()
        return principal

    return dependency


def require_owner(principal: CurrentPrincipal, session: DbSession) -> Principal:
    if not principal.is_owner:
        audit_denied(session, "owner_only", "access")
        raise PermissionDeniedError()
    return principal


OwnerPrincipal = Annotated[Principal, Depends(require_owner)]


@dataclass(frozen=True)
class BranchScope:
    """Which branches the caller may touch for one module/action. Built only from the Principal."""

    principal: Principal
    scope: Scope
    session: Session
    module: str

    @property
    def is_all(self) -> bool:
        return self.scope is Scope.ALL_BRANCHES

    def allows(self, branch_id: uuid.UUID | None) -> bool:
        if branch_id is None:
            return False
        return self.is_all or branch_id == self.principal.branch_id

    def ensure(self, branch_id: uuid.UUID | None) -> uuid.UUID:
        """Return `branch_id` if allowed, else audit + 403. Use for ids from paths, queries, bodies and loaded rows."""
        if branch_id is None or not self.allows(branch_id):
            audit_denied(
                self.session, self.module, "branch_access", {"requested_branch": str(branch_id)}
            )
            raise BranchAccessDeniedError()
        return branch_id

    def resolve(self, requested: uuid.UUID | None) -> uuid.UUID | None:
        """Branch to filter by. Branch users: their own branch (a different requested id is refused).
        Owners: the requested branch, or None meaning "all branches"."""
        if self.is_all:
            return requested
        if requested is not None:
            self.ensure(requested)
        if (
            self.principal.branch_id is None
        ):  # cannot happen (DB CHECK) but must never widen to "all"
            self.ensure(None)
        return self.principal.branch_id

    def apply(
        self, stmt: Select[Any], branch_column: Any, requested: uuid.UUID | None = None
    ) -> Select[Any]:
        """Add the branch restriction to a query (defence in depth; RLS enforces it again in the database)."""
        branch = self.resolve(requested)
        return stmt if branch is None else stmt.where(branch_column == branch)


def get_branch_scope(module: Module, action: Action = Action.READ) -> Callable[..., BranchScope]:
    """Dependency factory: permission check + the caller's branch scope for that module."""

    def dependency(principal: CurrentPrincipal, session: DbSession) -> BranchScope:
        grant = grant_for(principal.role, module)
        if grant is None or action not in grant.actions:
            audit_denied(session, module.value, action.value)
            raise PermissionDeniedError()
        return BranchScope(principal, grant.scope, session, module.value)

    return dependency


def require_branch_access(
    module: Module, action: Action = Action.READ, param: str = "branch_id"
) -> Callable[..., BranchScope]:
    """Dependency factory for routes with a `{branch_id}` path (or `?branch_id=`) parameter.
    Rejects any branch the caller may not access BEFORE the route handler runs."""
    scope_dep = get_branch_scope(module, action)

    def dependency(
        request: Request,
        principal: CurrentPrincipal,
        session: DbSession,
    ) -> BranchScope:
        scope = scope_dep(principal, session)
        raw = request.path_params.get(param) or request.query_params.get(param)
        if raw is not None:
            try:
                branch_id = uuid.UUID(str(raw))
            except ValueError:
                raise BranchAccessDeniedError() from None
            scope.ensure(branch_id)
        return scope

    return dependency


__all__ = [
    "BranchAccessDeniedError",
    "BranchScope",
    "CurrentPrincipal",
    "OwnerPrincipal",
    "PermissionDeniedError",
    "audit_denied",
    "get_branch_scope",
    "get_principal",
    "require_branch_access",
    "require_owner",
    "require_permission",
]
