"""Step 7 - the single place the reconciliation arithmetic lives."""

from decimal import Decimal as D

from app.core import calculations as c


def test_total_received_is_sum_of_four_channels() -> None:
    assert c.total_received(D("100.10"), D("50"), D("25.05"), D("0.01")) == D("175.16")


def test_difference_is_sales_minus_received_and_can_be_negative() -> None:
    assert c.difference(D("500"), D("480")) == D("20.00")
    assert c.difference(D("500"), D("510")) == D("-10.00")
    assert c.not_yet_received(D("500"), D("500")) == D("0.00")


def test_check_label() -> None:
    assert c.check_label(D("0.00")) == "Matches"
    assert c.check_label(D("0.01")) == "Diff"
    assert c.check_label(D("-5")) == "Diff"


def test_expenses_excluding_savings() -> None:
    assert c.shop_expenses_excl_savings(D("300"), D("120")) == D("180.00")
    assert c.head_office_excl_savings(D("1000"), D("1000")) == D("0.00")


def test_total_savings_and_sales_minus_expenses() -> None:
    assert c.total_savings(D("120"), D("30")) == D("150.00")
    assert c.sales_minus_expenses(D("1000"), D("180"), D("70")) == D("750.00")


def test_money_rounds_half_up_and_handles_none() -> None:
    assert c.money(D("1.005")) == D("1.01")
    assert c.money(None) == D("0.00")
