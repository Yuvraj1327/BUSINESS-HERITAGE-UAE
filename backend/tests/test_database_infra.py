import os

import pytest

from app.database.session import DatabaseNotConfiguredError, build_engine, ping_database
from tests.conftest import make_settings


def test_engine_requires_configuration() -> None:
    with pytest.raises(DatabaseNotConfiguredError):
        build_engine(make_settings())


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
def test_ping_real_database() -> None:
    ping_database(make_settings(database_url=os.environ["TEST_DATABASE_URL"]))
