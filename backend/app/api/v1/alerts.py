import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.alerts import AlertFacets, AlertOut, AlertPage, AlertSummary, UnreadCount
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])
Read = Annotated[object, Depends(require_permission(Module.ALERTS, Action.READ))]
Update = Annotated[object, Depends(require_permission(Module.ALERTS, Action.UPDATE))]

Severity = Literal["critical", "warning", "info"]
Status = Literal["unread", "read", "acknowledged", "resolved"]


def _page(
    session: DbSession,
    scope: str,
    q: str | None,
    kind: str | None,
    severity: str | None,
    branch_id: uuid.UUID | None,
    module: str | None,
    status_: str | None,
    page: int,
    page_size: int,
) -> AlertPage:
    return AlertService(session).search(
        scope, q, kind, severity, branch_id, module, status_, page, page_size
    )


# Static paths are declared before "/{alert_id}" so they are never parsed as ids.
@router.get(
    "/summary", response_model=AlertSummary, summary="Active alert counts and recent alerts"
)
def summary(session: DbSession, _p: Read) -> AlertSummary:
    return AlertService(session).summary()


@router.get(
    "/unread-count", response_model=UnreadCount, summary="Unread active alerts (header bell)"
)
def unread_count(session: DbSession, _p: Read) -> UnreadCount:
    return AlertService(session).unread_count()


@router.get("/facets", response_model=AlertFacets, summary="Alert types and modules for filters")
def facets(session: DbSession, _p: Read) -> AlertFacets:
    f = AlertService(session).facets()
    return AlertFacets(kinds=f["kinds"], modules=f["modules"])


@router.get("", response_model=AlertPage, summary="Active alerts, most important first")
def active(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    kind: str | None = None,
    severity: Severity | None = None,
    branch_id: uuid.UUID | None = None,
    module: str | None = None,
    status: Literal["unread", "read"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AlertPage:
    return _page(session, "active", q, kind, severity, branch_id, module, status, page, page_size)


@router.get("/history", response_model=AlertPage, summary="Acknowledged and resolved alerts")
def history(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    kind: str | None = None,
    severity: Severity | None = None,
    branch_id: uuid.UUID | None = None,
    module: str | None = None,
    status: Literal["acknowledged", "resolved"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AlertPage:
    return _page(session, "history", q, kind, severity, branch_id, module, status, page, page_size)


@router.post(
    "/refresh", response_model=UnreadCount, summary="Recalculate alerts from the real records now"
)
def refresh(session: DbSession, _p: Update) -> UnreadCount:
    return AlertService(session).unread_count()


@router.post("/read-all", response_model=UnreadCount, summary="Mark every active alert read")
def read_all(session: DbSession, _p: Update) -> UnreadCount:
    return AlertService(session).read_all()


@router.post("/{alert_id}/read", response_model=AlertOut, summary="Mark one alert read")
def read(alert_id: uuid.UUID, session: DbSession, _p: Update) -> AlertOut:
    return AlertService(session).mark_read(alert_id)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut, summary="Acknowledge one alert")
def acknowledge(alert_id: uuid.UUID, session: DbSession, _p: Update) -> AlertOut:
    return AlertService(session).acknowledge(alert_id)
