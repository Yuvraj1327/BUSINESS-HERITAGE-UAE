from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable constraint names keep Alembic autogenerate diffs deterministic.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base. ORM models mirror the schema created by database/migrations/*.sql (Step 4+).
    Tables are never created from metadata (no create_all): the SQL migrations own the schema."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
