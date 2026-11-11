import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.authz import BranchScope, get_branch_scope
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.dashboard import MissingReports
from app.schemas.reports import DailyReportCreate, DailyReportOut, DailyReportPage, VoidRequest
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService
from app.utils.time import dubai_today

router = APIRouter(prefix="/daily-reports", tags=["daily-reports"])

ReadScope = Annotated[BranchScope, Depends(get_branch_scope(Module.DAILY_REPORTS, Action.READ))]
CreateScope = Annotated[BranchScope, Depends(get_branch_scope(Module.DAILY_REPORTS, Action.CREATE))]
UpdateScope = Annotated[BranchScope, Depends(get_branch_scope(Module.DAILY_REPORTS, Action.UPDATE))]


@router.post(
    "",
    response_model=DailyReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a daily report",
)
def create_report(
    body: DailyReportCreate, session: DbSession, scope: CreateScope
) -> DailyReportOut:
    """Branch users submit for their own branch only; the owner chooses the branch. One report per branch/date."""
    return ReportService(session).create(scope, body)


@router.get("", response_model=DailyReportPage, summary="Report history (latest first)")
def list_reports(
    session: DbSession,
    scope: ReadScope,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DailyReportPage:
    return ReportService(session).list(scope, branch_id, date_from, date_to, page, page_size)


# NOTE: declared before "/{report_id}" so "missing" is not parsed as an id.
@router.get("/missing", response_model=MissingReports, summary="Branches/dates with no report")
def missing_reports(
    session: DbSession,
    scope: ReadScope,
    date_from: date,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
) -> MissingReports:
    branch = scope.resolve(branch_id)
    today = dubai_today()
    end = date_to or date_from
    return DashboardService(session).missing(branch, date_from, min(end, today), today)


@router.get("/{report_id}", response_model=DailyReportOut, summary="One report")
def get_report(report_id: uuid.UUID, session: DbSession, scope: ReadScope) -> DailyReportOut:
    return ReportService(session).get(scope, report_id)


@router.post(
    "/{report_id}/void",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Owner: void a report with a reason",
)
def void_report(
    report_id: uuid.UUID, body: VoidRequest, session: DbSession, _scope: UpdateScope
) -> Response:
    """The only correction path (decision D4): audited, reason required, frees the date for a fresh report."""
    ReportService(session).void(report_id, body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
