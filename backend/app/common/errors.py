from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, object]


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(
    status: int, code: str, message: str, details: dict[str, object] | None = None
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details or {})
    )
    return JSONResponse(status_code=status, content=body.model_dump())


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status, exc.code, exc.message)


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = []
    for error in exc.errors():
        location = error["loc"]
        if location == ("body", "email") and error["type"] == "value_error":
            fields.append({"field": "email", "code": "INVALID_EMAIL"})
        elif location == ("body", "password") and error["type"] in {
            "string_too_short",
            "string_too_long",
        }:
            fields.append({"field": "password", "code": "PASSWORD_LENGTH"})
        else:
            # Malformed bodies/type/missing-field errors never expose submitted input.
            return error_response(422, "VALIDATION_ERROR", "Invalid request.")
    return error_response(
        422,
        "VALIDATION_ERROR",
        "Invalid request.",
        {"fields": fields} if fields else {},
    )
