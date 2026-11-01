# lucida-django

Django wrapper over the `lucida` Python SDK (`../python`).

```python
INSTALLED_APPS += ["lucida_django"]
MIDDLEWARE += ["lucida_django.middleware.LucidaMiddleware"]
LUCIDA = {"api_key": "lc_pk_...", "host": "https://app.lucida.dev", "secret_key": None}
```

- `request.lucida.client` / `.distinct_id` / `.flags()`. Distinct id = authenticated user pk, else the `lc_id` cookie, which is written only when the consent cookie (`consent_cookie`, default `lc_consent`) holds a granted value. Set `consent_required: False` if your app gates it already.
- `{% load lucida %}{% lucida_bootstrap %}` emits `<script id="lucida-bootstrap" type="application/json">` (escaped via `json_script`) with `{distinctId, flags}`.

## Request context

`LucidaMiddleware` also opens a fresh Lucida request context (sync and async), so views can call `client.capture(None, "event")`:
the distinct id is the authenticated user pk, else the `X-Lucida-Distinct-Id` tracing header (client-controlled, never an auth
signal), else the consented `lc_id` cookie; `$session_id` comes from `X-Lucida-Session-Id`; every event carries
`$current_url`, `$request_method`, `$request_path`, `$user_agent`, `$ip`. Optional top-level settings:

- `LUCIDA_MW_EXTRA_PROPERTIES = {"svc": "web"}`
- `LUCIDA_MW_REQUEST_FILTER = lambda request: not request.path.startswith("/health")` (False skips the context)
- `LUCIDA_MW_PROPERTIES_MAP = lambda props, request: {...}` (rename or drop stamped properties)
- `LUCIDA_MW_CAPTURE_TRACING_HEADERS = True`, `LUCIDA_MW_TRUST_PROXY = False` (`$ip` from the first `X-Forwarded-For`)

Login signal recipe (identify when a user logs in, linking the anonymous cookie id):

```python
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from lucida_django.conf import get_client

@receiver(user_logged_in)
def lucida_login(sender, request, user, **kw):
    anon = request.COOKIES.get("lc_id")
    if anon:
        get_client().alias(str(user.pk), anon)
    get_client().identify(str(user.pk), {"email": user.email})
```

Tests: `python -m unittest discover -s tests` (needs Django; the base SDK is only imported when no client is injected).

---

This repository is a read-only mirror of the Lucida monorepo (synced by a script, never edited by hand); releases and provenance attestations are built here by GitHub Actions. Issues are welcome, changes land upstream.
