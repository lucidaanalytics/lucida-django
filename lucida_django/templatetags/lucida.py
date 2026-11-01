from __future__ import annotations

from typing import Any

from django import template
from django.utils.html import json_script
from django.utils.safestring import SafeString

register = template.Library()


def bootstrap_html(distinct_id: str, flags: dict[str, Any]) -> SafeString:
    """`<script id="lucida-bootstrap" type="application/json">`; json_script escapes < > & and U+2028/9."""
    return json_script({"distinctId": distinct_id, "flags": flags}, "lucida-bootstrap")


@register.simple_tag(takes_context=True)
def lucida_bootstrap(context: template.Context) -> SafeString | str:
    """Read it with `JSON.parse(document.getElementById("lucida-bootstrap").textContent)` and pass it to the JS SDK `bootstrap`."""
    ctx = getattr(context.get("request"), "lucida", None)
    return bootstrap_html(ctx.distinct_id, ctx.flags()) if ctx else ""
