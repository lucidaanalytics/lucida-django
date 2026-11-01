"""Settings reader: `LUCIDA = {...}` in settings.py."""

from __future__ import annotations

import threading
from typing import Any

from django.conf import settings

DEFAULTS: dict[str, Any] = {
    "api_key": "",
    "secret_key": None,
    "host": "https://app.lucida.dev",
    "disabled": False,
    "cookie_name": "lc_id",
    "cookie_max_age": 60 * 60 * 24 * 365,
    # required=False means the app already gates the middleware behind its own consent flow.
    "consent_required": True,
    "consent_cookie": "lc_consent",
    "consent_granted": ("analytics", "granted", "true", "1"),
    "client": None,  # inject a ready client (tests, custom transports)
}

_MW_DEFAULTS: dict[str, Any] = {
    "extra_properties": {},  # LUCIDA_MW_EXTRA_PROPERTIES: dict stamped on every request context
    "request_filter": None,  # LUCIDA_MW_REQUEST_FILTER: callable(request) -> bool, False skips the context
    "properties_map": None,  # LUCIDA_MW_PROPERTIES_MAP: callable(properties, request) -> properties (rename/drop)
    "capture_tracing_headers": True,  # LUCIDA_MW_CAPTURE_TRACING_HEADERS: read X-Lucida-Distinct-Id / -Session-Id
    "trust_proxy": False,  # LUCIDA_MW_TRUST_PROXY: take $ip from the first X-Forwarded-For entry
}

_lock = threading.Lock()
_client: Any = None


def get_settings() -> dict[str, Any]:
    return {**DEFAULTS, **getattr(settings, "LUCIDA", {})}


def get_mw_settings() -> dict[str, Any]:
    """`LUCIDA_MW_*` top-level Django settings with defaults."""
    return {k: getattr(settings, f"LUCIDA_MW_{k.upper()}", d) for k, d in _MW_DEFAULTS.items()}


def get_client() -> Any:
    """Process-wide client built lazily from settings."""
    global _client
    cfg = get_settings()
    if cfg["client"] is not None:
        return cfg["client"]
    with _lock:
        if _client is None:
            from lucida import Lucida

            kw: dict[str, Any] = {"host": cfg["host"].rstrip("/"), "disabled": cfg["disabled"]}
            if cfg["secret_key"]:
                kw["secret_key"] = cfg["secret_key"]
            _client = Lucida(cfg["api_key"], **kw)
        return _client
