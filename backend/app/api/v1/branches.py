import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.authz import BranchScope, get_branch_scope, require_branch_access
from app.api.deps import DbSession
from app.core.exceptions import NotFoundError
from app.core.permissions import Action, Module
from app.repositories.branch_repository import BranchRepository
from app.schemas.rbac import BranchOut

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("", response_model=list[BranchOut], summary="Branches the caller may see")
def list_branches(
    session: DbSession,
    scope: Annotated[BranchScope, Depends(get_branch_scope(Module.BRANCH_MANAGEMENT, Action.READ))],
    branch_id: uuid.UUID | None = None,
) -> list[dict[str, object]]:
    """Owner: all ten (optionally one). Branch user: only their own; asking for another branch is a 403."""
    return BranchRepository(session).list(scope.resolve(branch_id))


@router.get(
    "/{branch_id}", response_model=BranchOut, summary="One branch (own branch for branch users)"
)
def get_branch(
    branch_id: uuid.UUID,
    session: DbSession,
    _scope: Annotated[
        BranchScope, Depends(require_branch_access(Module.BRANCH_MANAGEMENT, Action.READ))
    ],
) -> dict[str, object]:
    row = BranchRepository(session).get(branch_id)
    if row is None:
        raise NotFoundError(
            "Branch not found"
        )  # only reachable by an owner; branch users are refused earlier
    return row
