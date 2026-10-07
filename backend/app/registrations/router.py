from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.common.clock import Clock, get_clock
from app.common.errors import ErrorResponse
from app.db.session import DatabaseSession
from app.events.router import CurrentUser, private_response
from app.registrations.schemas import RegistrationResponse
from app.registrations.service import (
    cancel_registration,
    get_my_registration,
    register_for_event,
)

router = APIRouter(
    prefix="/api/events",
    tags=["registrations"],
    dependencies=[Depends(private_response)],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
    },
)


@router.post(
    "/{event_id}/registrations", status_code=201, response_model=RegistrationResponse
)
def register(
    event_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> RegistrationResponse:
    return register_for_event(session, clock, user.id, event_id)


@router.get("/{event_id}/my-registration", response_model=RegistrationResponse)
def own(
    event_id: UUID, user: CurrentUser, session: DatabaseSession
) -> RegistrationResponse:
    return get_my_registration(session, user.id, event_id)


@router.delete("/{event_id}/registration", response_model=RegistrationResponse)
def cancel(
    event_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> RegistrationResponse:
    return cancel_registration(session, clock, user.id, event_id)
