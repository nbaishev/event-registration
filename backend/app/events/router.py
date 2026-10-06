from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.common.clock import Clock, get_clock
from app.common.errors import ErrorResponse
from app.db.session import DatabaseSession
from app.events.schemas import (
    EventCreateRequest,
    EventPatchRequest,
    EventResponse,
    EventSummary,
    PublicEventResponse,
)
from app.events.service import (
    create_event,
    get_owned_event,
    get_public_event,
    list_owned_events,
    patch_owned_event,
    publish_owned_event,
)


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/events",
    tags=["events"],
    dependencies=[Depends(private_response)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", status_code=201, response_model=EventResponse)
def create(
    body: EventCreateRequest,
    user: CurrentUser,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> EventResponse:
    return EventResponse.model_validate(create_event(session, clock, user.id, body))


@router.get("/mine", response_model=list[EventSummary])
def mine(user: CurrentUser, session: DatabaseSession) -> list[EventSummary]:
    return [
        EventSummary.model_validate(event)
        for event in list_owned_events(session, user.id)
    ]


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    responses={404: {"model": ErrorResponse}},
)
def detail(
    event_id: UUID, user: CurrentUser, session: DatabaseSession
) -> EventResponse:
    return EventResponse.model_validate(get_owned_event(session, user.id, event_id))


@router.patch(
    "/{event_id}",
    response_model=EventResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def patch_event(
    event_id: UUID,
    body: EventPatchRequest,
    user: CurrentUser,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> EventResponse:
    return EventResponse.model_validate(
        patch_owned_event(session, clock, user.id, event_id, body)
    )


@router.post(
    "/{event_id}/publish",
    response_model=EventResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def publish_event(
    event_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> EventResponse:
    return EventResponse.model_validate(
        publish_owned_event(session, clock, user.id, event_id)
    )


public_router = APIRouter(
    prefix="/api/public/events",
    tags=["public events"],
    dependencies=[Depends(private_response)],
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)


@public_router.get("/{slug}", response_model=PublicEventResponse)
def public_detail(
    slug: str,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> PublicEventResponse:
    return get_public_event(session, clock, slug)
