from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.http import HttpRequest, HttpResponse

from lucida import new_context
from lucida import request_context_args

from .conf import get_client, get_mw_settings, get_settings
from .visitor import resolve


@dataclass
class LucidaContext:
    client: Any
    distinct_id: str

    def flags(self) -> dict[str, Any]:
        """Locally decidable flags for this visitor (the base client returns {} when definitions are not loaded)."""
        return self.client.get_all_flags(self.distinct_id, only_evaluate_locally=True)


def context_args(request: HttpRequest, mw: dict[str, Any], user_id: str | None, cookie_id: str | None) -> dict[str, Any]:
    """`new_context` arguments for a request: user pk (else tracing-header id, else consented cookie id) + request props."""
    args = request_context_args(
        lambda name: request.headers.get(name),
        method=request.method,
        url=request.build_absolute_uri(),
        path=request.path,
        remote_addr=request.META.get("REMOTE_ADDR"),
        trust_proxy=mw["trust_proxy"],
        capture_tracing_headers=mw["capture_tracing_headers"],
        extra=mw["extra_properties"],
    )
    if user_id:
        args["distinct_id"] = user_id  # the authenticated user always beats a client-supplied header
    elif not args["distinct_id"]:
        args["distinct_id"] = cookie_id
    if mw["properties_map"]:
        args["properties"] = mw["properties_map"](args["properties"], request)
    return args


class LucidaMiddleware:
    """Attaches `request.lucida`; writes the `lc_id` cookie only when consent is granted.

    Also opens a Lucida request context for the request (sync and async), so `client.capture(None, "event")` inside views
    knows the user and stamps `$current_url`, `$request_method`, `$request_path`, `$user_agent`, `$ip`.
    Configure with `LUCIDA_MW_*` settings (see README).
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        self.get_response = get_response
        self._async = iscoroutinefunction(get_response)
        if self._async:
            markcoroutinefunction(self)

    def _prepare(self, request: HttpRequest) -> tuple[dict[str, Any] | None, bool]:
        """Everything that may touch the DB/session (so it runs in a thread under ASGI)."""
        cfg = get_settings()
        user = getattr(request, "user", None)
        uid = str(user.pk) if user is not None and user.is_authenticated else None
        distinct_id, set_cookie = resolve(uid, request.COOKIES, cfg)
        request.lucida = LucidaContext(get_client(), distinct_id)  # type: ignore[attr-defined]
        mw = get_mw_settings()
        if mw["request_filter"] and not mw["request_filter"](request):
            return None, set_cookie
        cookie_id = distinct_id if request.COOKIES.get(cfg["cookie_name"]) == distinct_id else None
        return context_args(request, mw, uid, cookie_id), set_cookie

    def _finish(self, request: HttpRequest, response: HttpResponse, set_cookie: bool) -> HttpResponse:
        cfg = get_settings()
        if set_cookie:
            response.set_cookie(
                cfg["cookie_name"],
                request.lucida.distinct_id,  # type: ignore[attr-defined]
                max_age=cfg["cookie_max_age"],
                samesite="Lax",
                secure=request.is_secure(),
            )
        return response

    def __call__(self, request: HttpRequest) -> Any:
        if self._async:
            return self._acall(request)
        args, set_cookie = self._prepare(request)
        if args is None:
            return self._finish(request, self.get_response(request), set_cookie)
        with new_context(fresh=True, **args):
            response = self.get_response(request)
        return self._finish(request, response, set_cookie)

    async def _acall(self, request: HttpRequest) -> HttpResponse:
        args, set_cookie = await sync_to_async(self._prepare)(request)
        if args is None:
            return self._finish(request, await self.get_response(request), set_cookie)
        with new_context(fresh=True, **args):
            response = await self.get_response(request)
        return self._finish(request, response, set_cookie)
