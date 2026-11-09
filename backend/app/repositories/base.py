from sqlalchemy.orm import Session


class BaseRepository:
    """Data-access layer: repositories hold queries only, no business rules (those live in services)."""

    def __init__(self, session: Session) -> None:
        self.session = session
