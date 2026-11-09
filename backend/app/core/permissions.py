"""Centralised RBAC definitions: roles, modules, actions and the permission matrix.

This file is the ONLY place that says who may do what. The API enforces it (api/authz.py), the frontend receives
the caller's slice of it from `GET /auth/profile` (it never keeps its own copy of the rules), and the database
enforces the same intent independently with RLS (database/migrations/0008, 0010).

Rules
* Default DENY: a role/module pair that is not listed grants nothing.
* Roles are the database values `owner` and `branch` (profiles.role). "BRANCH_USER" in the brief = `branch`.
* Role and branch always come from the trusted `profiles` row -- never from the request or token metadata.
* Hard deletes of financial/compliance records are not offered to anyone (schema decision D4); corrections
  are audited voids and are modelled as UPDATE.
* APPROVE exists as an action but no approval workflow is defined anywhere, so nobody holds it yet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    BRANCH_USER = "branch"  # database value is "branch"


class Action(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    EXPORT = "export"
    MANAGE = "manage"


class Module(StrEnum):
    DASHBOARD = "dashboard"
    BRANCH_MANAGEMENT = "branch_management"
    DAILY_REPORTS = "daily_reports"
    CASH_BANKS = "cash_banks"
    OPENING_BALANCES = "opening_balances"
    EXPENSES = "expenses"
    SUPPLIERS = "suppliers"
    EMPLOYEES = "employees"
    VISAS_PASSPORTS = "visas_passports"
    TRADE_LICENSES = "trade_licenses"
    RENTALS_CHEQUES = "rentals_cheques"
    TASKS = "tasks"
    REPORTS = "reports"
    USER_MANAGEMENT = "user_management"
    SETTINGS = "settings"
    AUDIT_LOG = "audit_log"


class Scope(StrEnum):
    ALL_BRANCHES = "all_branches"
    OWN_BRANCH = "own_branch"


@dataclass(frozen=True)
class Grant:
    actions: frozenset[Action]
    scope: Scope


A = Action
_FULL = frozenset(
    {A.READ, A.CREATE, A.UPDATE, A.EXPORT, A.MANAGE}
)  # "full" = everything the design allows


def _g(scope: Scope, *actions: Action) -> Grant:
    return Grant(frozenset(actions), scope)


ALL, OWN = Scope.ALL_BRANCHES, Scope.OWN_BRANCH

# fmt: off
PERMISSION_MATRIX: dict[Role, dict[Module, Grant]] = {
    Role.OWNER: {
        Module.DASHBOARD:         _g(ALL, A.READ, A.EXPORT),
        Module.BRANCH_MANAGEMENT: _g(ALL, A.READ, A.UPDATE, A.MANAGE),            # name / order / active only (D16)
        Module.DAILY_REPORTS:     _g(ALL, A.READ, A.CREATE, A.UPDATE, A.EXPORT),  # UPDATE = audited void (D4)
        Module.CASH_BANKS:        _g(ALL, A.READ, A.EXPORT),
        Module.OPENING_BALANCES:  _g(ALL, A.READ, A.CREATE, A.UPDATE, A.EXPORT),
        Module.EXPENSES:          _g(ALL, A.READ, A.CREATE, A.UPDATE, A.EXPORT),
        Module.SUPPLIERS:         _g(ALL, A.READ, A.CREATE, A.UPDATE, A.EXPORT),
        Module.EMPLOYEES:         _g(ALL, A.READ, A.CREATE, A.UPDATE, A.EXPORT),
        Module.VISAS_PASSPORTS:   _g(ALL, A.READ, A.UPDATE, A.EXPORT),
        Module.TRADE_LICENSES:    _g(ALL, A.READ, A.CREATE, A.UPDATE, A.EXPORT),
        Module.RENTALS_CHEQUES:   _g(ALL, A.READ, A.CREATE, A.UPDATE, A.EXPORT),
        Module.TASKS:             _g(ALL, A.READ, A.CREATE, A.UPDATE, A.DELETE, A.EXPORT),
        Module.REPORTS:           _g(ALL, A.READ, A.EXPORT),
        Module.USER_MANAGEMENT:   _g(ALL, A.READ, A.CREATE, A.UPDATE, A.MANAGE),  # no DELETE: deactivate instead
        Module.SETTINGS:          _g(ALL, A.READ, A.UPDATE, A.MANAGE),
        Module.AUDIT_LOG:         _g(ALL, A.READ),
    },
    Role.BRANCH_USER: {
        Module.DASHBOARD:         _g(OWN, A.READ),
        Module.BRANCH_MANAGEMENT: _g(OWN, A.READ),            # may see their own branch record; no management
        Module.DAILY_REPORTS:     _g(OWN, A.READ, A.CREATE),  # never UPDATE / DELETE / EXPORT
        # Everything below is deliberately absent => DENY (see docs/security/PERMISSION_MATRIX.md for open items):
        #   CASH_BANKS, OPENING_BALANCES, EXPENSES (own-branch shop expenses are entered inside the daily report,
        #   covered by DAILY_REPORTS/CREATE), SUPPLIERS, EMPLOYEES, VISAS_PASSPORTS, TRADE_LICENSES,
        #   RENTALS_CHEQUES, TASKS (D11), REPORTS (own history = DAILY_REPORTS/READ), USER_MANAGEMENT,
        #   SETTINGS, AUDIT_LOG
    },
}
# fmt: on


def grant_for(role: Role | str, module: Module) -> Grant | None:
    try:
        r = Role(role)
    except ValueError:
        return None  # unknown role value => nothing
    return PERMISSION_MATRIX.get(r, {}).get(module)


def can(role: Role | str, module: Module, action: Action) -> bool:
    g = grant_for(role, module)
    return g is not None and action in g.actions


def permissions_for(role: Role | str) -> dict[str, dict[str, object]]:
    """JSON-friendly slice sent to the UI (for display decisions only; the API re-checks every request)."""
    try:
        r = Role(role)
    except ValueError:
        return {}
    return {
        m.value: {"actions": sorted(a.value for a in g.actions), "scope": g.scope.value}
        for m, g in PERMISSION_MATRIX.get(r, {}).items()
    }


@dataclass(frozen=True)
class Principal:
    """The authenticated, ACTIVE user as stored in `profiles` -- the only source of role and branch."""

    user_id: uuid.UUID
    role: Role
    branch_id: uuid.UUID | None
    full_name: str

    @property
    def is_owner(self) -> bool:
        return self.role is Role.OWNER

    def can(self, module: Module, action: Action) -> bool:
        return can(self.role, module, action)
