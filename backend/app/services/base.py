from sqlalchemy.orm import Session


class BaseService:
    """Business-rule layer: calculations, validation across records, transactions and audit reasons.
    Routes stay thin and call services; services call repositories."""

    def __init__(self, session: Session) -> None:
        self.session = session
