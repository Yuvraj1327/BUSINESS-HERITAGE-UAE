import logging
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.authz import PermissionDeniedError, require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module, Principal
from app.schemas.analytics import ChartSet, Overview, Period, ReportCatalogItem, ReportOut
from app.services import export_service as exp
from app.services.analytics_service import RF, AnalyticsService
from app.utils.time import dubai_today

logger = logging.getLogger("app.audit")
router = APIRouter(prefix="/reports", tags=["reports"])
Read = Annotated[Principal, Depends(require_permission(Module.REPORTS, Action.READ))]
Export = Annotated[Principal, Depends(require_permission(Module.REPORTS, Action.EXPORT))]
Audit = Annotated[Principal, Depends(require_permission(Module.AUDIT_LOG, Action.READ))]


def _filters(
    date_from: date | None = None,
    date_to: date | None = None,
    period: Period = "day",
    branch_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    account: str | None = None,
    kind: str | None = None,
    module: str | None = None,
    action: Literal["INSERT", "UPDATE", "DELETE"] | None = None,
    actor_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> RF:
    today = dubai_today()
    end = date_to or today
    return RF(
        d_from=date_from or end.replace(day=1),
        d_to=end, period=period, branch_id=branch_id, supplier_id=supplier_id, account=account, kind=kind,
        module=module, action=action, actor_id=actor_id, q=q, page=page, page_size=page_size,
    )  # fmt: skip


Filters = Annotated[RF, Depends(_filters)]


def _export(report: ReportOut, fmt: str, who: Principal) -> Response:
    data = exp.to_csv(report) if fmt == "csv" else exp.to_xlsx(report)
    logger.info(
        "report_export key=%s format=%s rows=%d user=%s from=%s to=%s branch=%s",
        report.key, fmt, report.total, who.user_id, report.filters.date_from, report.filters.date_to,
        report.filters.branch_id,
    )  # fmt: skip
    return Response(
        content=data,
        media_type=exp.CSV_TYPE if fmt == "csv" else exp.XLSX_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{exp.filename(report, fmt)}"',
            "Cache-Control": "no-store",
        },
    )


# Static paths are declared before "/{key}" so they are never parsed as report keys.
@router.get("/catalog", response_model=list[ReportCatalogItem], summary="Available reports")
def catalog(session: DbSession, _p: Read) -> list[ReportCatalogItem]:
    return AnalyticsService(session).catalog()


@router.get("/overview", response_model=Overview, summary="KPI cards for the selected filters")
def overview(session: DbSession, _p: Read, rf: Filters) -> Overview:
    return AnalyticsService(session).overview(rf)


@router.get("/charts", response_model=ChartSet, summary="Chart data for the selected filters")
def charts(session: DbSession, _p: Read, rf: Filters) -> ChartSet:
    return AnalyticsService(session).charts(rf)


@router.get("/activity/actors", summary="Users who appear in the activity history")
def actors(session: DbSession, _p: Audit) -> list[dict[str, str]]:
    return [
        {"id": str(a["user_id"]), "name": a["full_name"]}
        for a in AnalyticsService(session).repo.actors()
    ]


@router.get("/activity", response_model=ReportOut, summary="Activity history (Owner only)")
def activity(session: DbSession, _p: Audit, rf: Filters) -> ReportOut:
    return AnalyticsService(session).run("activity", rf, None, False)


@router.get("/activity/export", summary="Export the complete filtered activity history")
def activity_export(
    session: DbSession,
    p: Audit,
    rf: Filters,
    fmt: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "csv",
) -> Response:
    if not p.can(Module.REPORTS, Action.EXPORT):
        raise PermissionDeniedError()
    return _export(AnalyticsService(session).full("activity", rf), fmt, p)


@router.get("/{key}", response_model=ReportOut, summary="One report (filters, sort, pagination)")
def report(
    key: str,
    session: DbSession,
    _p: Read,
    rf: Filters,
    sort: Annotated[str | None, Query(max_length=40)] = None,
    desc: bool = False,
) -> ReportOut:
    return AnalyticsService(session).run(key, rf, sort, desc)


@router.get("/{key}/export", summary="Export the complete filtered report as CSV or Excel")
def export(
    key: str,
    session: DbSession,
    p: Export,
    rf: Filters,
    fmt: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "csv",
) -> Response:
    return _export(AnalyticsService(session).full(key, rf), fmt, p)
