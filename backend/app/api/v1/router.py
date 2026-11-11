from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    auth,
    branch_date_view,
    branches,
    cash_banks,
    compliance_alerts,
    customers,
    daily_reports,
    dashboard,
    employees,
    expenses,
    health,
    opening_balances,
    order_operations,
    orders,
    pdc_cheques,
    rentals,
    reports,
    suppliers,
    tasks,
    trade_licenses,
    users,
    visas_passports,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(branches.router)
api_router.include_router(users.router)
api_router.include_router(daily_reports.router)
api_router.include_router(dashboard.router)
api_router.include_router(branch_date_view.router)
# Business routers are registered here in later steps (modules in Steps 7-11).
api_router.include_router(opening_balances.router)
api_router.include_router(cash_banks.router)
api_router.include_router(expenses.router)
api_router.include_router(suppliers.router)
api_router.include_router(employees.router)
api_router.include_router(visas_passports.router)
api_router.include_router(trade_licenses.router)
api_router.include_router(compliance_alerts.router)
api_router.include_router(rentals.router)
api_router.include_router(pdc_cheques.router)
api_router.include_router(tasks.router)
api_router.include_router(alerts.router)
api_router.include_router(reports.router)
api_router.include_router(customers.router)
api_router.include_router(orders.router)
api_router.include_router(order_operations.router)
