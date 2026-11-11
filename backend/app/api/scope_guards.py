"""Guards for endpoints that only make sense across all branches (owner-wide views)."""

from collections.abc import Callable

from app.api.authz import (
    BranchScope,
    CurrentPrincipal,
    PermissionDeniedError,
    audit_denied,
    get_branch_scope,
)
from app.api.deps import DbSession
from app.core.permissions import Action, Module


def require_all_branches(
    module: Module, action: Action = Action.READ
) -> Callable[..., BranchScope]:
    """Permission on `module` AND the all-branches scope; a branch-scoped caller gets an audited 403."""
    inner = get_branch_scope(module, action)

    def dependency(principal: CurrentPrincipal, session: DbSession) -> BranchScope:
        scope = inner(principal, session)
        if not scope.is_all:
            audit_denied(session, module.value, "all_branches_only")
            raise PermissionDeniedError()
        return scope

    return dependency
