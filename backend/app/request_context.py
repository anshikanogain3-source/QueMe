from contextvars import ContextVar
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str] = ContextVar("queme_request_id", default="")


def current_request_id() -> str:
    return _request_id.get() or str(uuid4())


def normalize_request_id(candidate: str | None) -> str:
    if candidate:
        try:
            return str(UUID(candidate))
        except (ValueError, AttributeError):
            pass
    return str(uuid4())


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = normalize_request_id(headers.get(b"x-request-id", b"").decode("latin-1"))
        token = _request_id.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id.reset(token)
