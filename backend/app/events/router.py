from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.common.clock import Clock, get_clock
from app.common.errors import ErrorResponse
from app.db.session import DatabaseSession
from app.events.broadcaster import StatsNotifications
from app.events.schemas import (
    EventCreateRequest,
    EventPatchRequest,
    EventResponse,
    EventSummary,
    PublicEventResponse,
    StatsResponse,
)
from app.events.service import (
    cancel_owned_event,
    create_event,
    delete_owned_event,
    get_owned_event,
    get_public_event,
    list_owned_events,
    patch_owned_event,
    publish_owned_event,
)
from app.events.stats import get_owned_stats
from app.events.stream import StatsStreamResponse, authorize_stats_stream
from app.notifications.transitions import (
    TransitionDispatcher,
    get_transition_dispatcher,
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


@router.get(
    "/{event_id}/stats",
    response_model=StatsResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def stats(event_id: UUID, user: CurrentUser, session: DatabaseSession) -> StatsResponse:
    return get_owned_stats(session, user.id, event_id)


@router.patch(
    "/{event_id}",
    response_model=EventResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def patch_event(
    event_id: UUID,
    broadcaster: StatsNotifications,
    notification_dispatcher: Annotated[
        TransitionDispatcher, Depends(get_transition_dispatcher)
    ],
    body: EventPatchRequest,
    user: CurrentUser,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> EventResponse:
    return EventResponse.model_validate(
        patch_owned_event(
            session,
            clock,
            user.id,
            event_id,
            body,
            broadcaster=broadcaster,
            notification_dispatcher=notification_dispatcher,
        )
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


@router.post(
    "/{event_id}/cancel",
    response_model=EventResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def cancel_event(
    event_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
    notification_dispatcher: Annotated[
        TransitionDispatcher, Depends(get_transition_dispatcher)
    ],
) -> EventResponse:
    return EventResponse.model_validate(
        cancel_owned_event(
            session,
            clock,
            user.id,
            event_id,
            notification_dispatcher=notification_dispatcher,
        )
    )


@router.delete(
    "/{event_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def delete_event(event_id: UUID, user: CurrentUser, session: DatabaseSession) -> None:
    delete_owned_event(session, user.id, event_id)


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


@router.get(
    "/{event_id}/stats/stream",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def stats_stream(
    event_id: Annotated[UUID, Depends(authorize_stats_stream)],
    broadcaster: StatsNotifications,
) -> StreamingResponse:
    return StatsStreamResponse(broadcaster, event_id)
