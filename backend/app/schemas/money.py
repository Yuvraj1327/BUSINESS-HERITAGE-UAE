from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer

MAX_DIGITS = 14
DECIMAL_PLACES = 2

# API output: decimal strings with exactly two places ("1250.50"), as the API specification requires.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]

# API input: non-negative, at most 2 decimals, fits numeric(14,2). Accepts JSON strings or numbers.
MoneyIn = Annotated[
    Decimal,
    Field(ge=0, max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, allow_inf_nan=False),
]

# Strictly positive amounts (payments, transfers, expenses): same precision rules, but zero is refused.
PositiveMoneyIn = Annotated[
    Decimal,
    Field(gt=0, max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, allow_inf_nan=False),
]
