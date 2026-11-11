"""Rental / PDC alerts and the rental summary for the Owner dashboard. Calculated from real dates on every request."""

from decimal import Decimal

from app.core.calculations import money
from app.schemas.rentals import RentalAlert, RentalAlertFeed, RentalSummary
from app.services.cheque_service import ChequeService
from app.utils.time import dubai_today

_TITLES = {
    "rental_expired": ("danger", "Rental agreement ended - not renewed"),
    "rental_ending": ("warning", "Rental agreement ending soon"),
    "rental_renewal_upcoming": ("warning", "Rental renewal coming up"),
    "cheque_overdue": ("danger", "PDC cheque overdue"),
    "cheque_due_7": ("danger", "PDC cheque due within 7 days"),
    "cheque_due_30": ("warning", "PDC cheque due within 30 days"),
    "cheque_bounced": ("danger", "PDC cheque bounced - needs a replacement"),
}


class RentalAlertService(ChequeService):
    def alerts(self) -> RentalAlertFeed:
        today = dubai_today()
        items: list[RentalAlert] = []
        for r in self.rent.alert_rows(today):
            kind = r["kind"]
            severity, title = _TITLES[kind]
            is_cheque = kind.startswith("cheque_")
            days = (r["due"] - today).days if r["due"] else None
            amount = money(r["amount"]) if r["amount"] is not None else None
            what = (
                f"Cheque {r['cheque_no']} ({r['bank']}, AED {amount:,.2f})"
                if is_cheque
                else "Agreement"
            )
            when = r["due"].isoformat() if r["due"] else ""
            items.append(
                RentalAlert(
                    key=f"{kind}:{r['record_id']}",
                    kind=kind,
                    severity=severity,  # type: ignore[arg-type]
                    title=title,
                    detail=f"{r['branch_name']} - {r['landlord']}: {what} - {when}",
                    branch_name=r["branch_name"],
                    landlord=r["landlord"],
                    cheque_no=r["cheque_no"],
                    amount=amount,
                    bank=r["bank"],
                    due_date=r["due"],
                    days_remaining=days if kind != "cheque_bounced" else None,
                    href=f"/pdc-cheques/{r['record_id']}"
                    if is_cheque
                    else f"/rentals/{r['record_id']}",
                )
            )
        danger = sum(1 for i in items if i.severity == "danger")
        return RentalAlertFeed(
            items=items, total=len(items), danger=danger, warning=len(items) - danger
        )

    def rental_summary(self) -> RentalSummary:
        today = dubai_today()
        a = self.rent.agreement_summary(today)
        return RentalSummary(
            agreements_active=int(a["agreements_active"]),
            expiring_30=int(a["expiring_30"]),
            expired_unrenewed=int(a["expired_unrenewed"]),
            renewal_approaching=int(a["renewal_approaching"]),
            annual_rent_active=money(a["annual_rent_active"] or Decimal("0")),
            cheques=self.summary(),
        )
