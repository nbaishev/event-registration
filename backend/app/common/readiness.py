from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.readiness import ping_database


def database_is_ready(session: Session) -> bool:
    try:
        ping_database(session)
    except SQLAlchemyError:
        session.rollback()
        return False
    return True
