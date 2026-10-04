from sqlalchemy import text
from sqlalchemy.orm import Session


def ping_database(session: Session) -> None:
    session.execute(text("SELECT 1"))
