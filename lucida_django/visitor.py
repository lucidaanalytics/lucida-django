"""Pure visitor-id resolution (no Django types)."""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping
from typing import Any

_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def consent_granted(cfg: Mapping[str, Any], cookies: Mapping[str, str]) -> bool:
    if not cfg["consent_required"]:
        return True
    return cookies.get(cfg["consent_cookie"]) in cfg["consent_granted"]


def resolve(user_id: str | None, cookies: Mapping[str, str], cfg: Mapping[str, Any]) -> tuple[str, bool]:
    """(distinct_id, set_cookie). User id wins; else the cookie; a new anon id is persisted only with consent."""
    if user_id:
        return user_id, False
    consent = consent_granted(cfg, cookies)
    existing = cookies.get(cfg["cookie_name"])
    if consent and existing and _ID.match(existing):
        return existing, False
    return "anon_" + secrets.token_hex(12), consent
