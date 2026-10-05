from typing import Annotated

from fastapi import Depends, Request

from app.auth.models import User
from app.auth.service import current_user
from app.common.clock import Clock, get_clock
from app.common.config import Settings, get_settings
from app.db.session import DatabaseSession


def get_current_user(
    request: Request,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    return current_user(session, clock, settings, request.cookies.get("access_token"))
