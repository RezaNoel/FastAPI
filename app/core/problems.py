"""Application errors rendered as RFC 7807 problem documents."""

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.logging import request_id_var


class AppError(Exception):
    status = 400
    title = "Bad request"
    type_name = "bad-request"

    def __init__(self, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


class Unauthorized(AppError):
    status = 401
    title = "Unauthorized"
    type_name = "unauthorized"


class Forbidden(AppError):
    status = 403
    title = "Forbidden"
    type_name = "forbidden"


class NotFound(AppError):
    status = 404
    title = "Not found"
    type_name = "not-found"


class Conflict(AppError):
    status = 409
    title = "Conflict"
    type_name = "conflict"


class PreconditionFailed(AppError):
    status = 412
    title = "Precondition failed"
    type_name = "precondition-failed"


class Unprocessable(AppError):
    status = 422
    title = "Unprocessable"
    type_name = "unprocessable"


def problem_body(
    *,
    status: int,
    title: str,
    detail: str,
    request: Request,
    type_name: str,
    errors: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", None) or request_id_var.get("-")
    body: dict[str, Any] = {
        "type": f"urn:grove:problem:{type_name}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": request_id,
    }
    if errors is not None:
        body["errors"] = jsonable_encoder(errors)
    if extra:
        body.update(extra)
    return body


def problem_response(
    *,
    status: int,
    title: str,
    detail: str,
    request: Request,
    type_name: str,
    errors: Any = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        problem_body(
            status=status,
            title=title,
            detail=detail,
            request=request,
            type_name=type_name,
            errors=errors,
            extra=extra,
        ),
        status_code=status,
        media_type="application/problem+json",
        headers=headers,
    )
