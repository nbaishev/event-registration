from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.events.models import EventStatus


class EventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    description: Annotated[StrictStr, Field(min_length=1, max_length=10000)]
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    timezone: StrictStr
    capacity: Annotated[StrictInt, Field(ge=1, le=2147483647)]

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def require_iso_datetime(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError("An ISO-8601 datetime is required")
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        try:
            return value.astimezone(UTC)
        except OverflowError:
            raise ValueError("Datetime is outside the supported UTC range") from None

    @field_validator("title", "description")
    @classmethod
    def valid_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Text cannot contain NUL")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid IANA timezone") from None
        return value

    @model_validator(mode="after")
    def valid_interval(self) -> "EventCreateRequest":
        if self.ends_at <= self.starts_at:
            raise ValueError("End must be after start")
        return self


class EventPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[StrictStr | None, Field(min_length=1, max_length=200)] = None
    description: Annotated[StrictStr | None, Field(min_length=1, max_length=10000)] = (
        None
    )
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    timezone: StrictStr | None = None
    capacity: Annotated[StrictInt | None, Field(ge=1, le=2147483647)] = None
    regenerate_slug: StrictBool | None = None

    @model_validator(mode="before")
    @classmethod
    def require_change(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if value.get("regenerate_slug", False) is None:
            raise ValueError("regenerate_slug cannot be null")
        if any(item is None for key, item in value.items() if key != "regenerate_slug"):
            raise ValueError("Event values cannot be null")
        if not any(
            key != "regenerate_slug" or item is True for key, item in value.items()
        ):
            raise ValueError("At least one change is required")
        return value

    @field_validator("title", mode="before")
    @classmethod
    def trim_optional_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def require_optional_iso_datetime(cls, value: object) -> object:
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("An ISO-8601 datetime is required")
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalize_optional_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        try:
            return value.astimezone(UTC)
        except OverflowError:
            raise ValueError("Datetime is outside the supported UTC range") from None

    @field_validator("title", "description")
    @classmethod
    def valid_optional_text(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("Text cannot contain NUL")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_optional_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid IANA timezone") from None
        return value


class EventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    capacity: int
    status: EventStatus


class EventResponse(EventSummary):
    owner_id: UUID
    description: str
    schedule_updated_at: datetime
    published_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublicEventResponse(BaseModel):
    id: UUID
    title: str
    description: str
    slug: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    capacity: int
    status: Literal["PUBLISHED", "FINISHED", "CANCELLED"]
