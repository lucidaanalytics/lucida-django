import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import django
    from django.conf import settings
except ImportError:  # Django not installed: skip the module
    django = None

if django is not None:

    class FakeClient:
        def get_all_flags(self, distinct_id, **kw):
            return {"f": True, "x": "</script><b>&"}

    FAKE = FakeClient()
    if not settings.configured:
        settings.configure(
            SECRET_KEY="t",
            ALLOWED_HOSTS=["*"],
            INSTALLED_APPS=["lucida_django"],
            LUCIDA={"api_key": "k", "client": FAKE},
            TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates", "OPTIONS": {"builtins": []}}],
        )
    django.setup()

    from django.http import HttpResponse
    from django.template import engines
    from django.test import RequestFactory

    from lucida_django.middleware import LucidaMiddleware
    from lucida_django.conf import DEFAULTS
    from lucida_django.visitor import resolve


@unittest.skipIf(django is None, "django not installed")
class VisitorTest(unittest.TestCase):
    def test_resolve(self):
        c = {**DEFAULTS}
        self.assertEqual(resolve("7", {}, c), ("7", False))
        i, s = resolve(None, {}, c)
        self.assertTrue(i.startswith("anon_") and not s)  # no consent: never persisted
        i, s = resolve(None, {"lc_id": "abcdefgh12", "lc_consent": "no"}, c)
        self.assertNotEqual(i, "abcdefgh12")
        self.assertFalse(s)
        self.assertEqual(resolve(None, {"lc_id": "abcdefgh12", "lc_consent": "analytics"}, c), ("abcdefgh12", False))
        self.assertTrue(resolve(None, {"lc_consent": "analytics"}, c)[1])
        self.assertNotEqual(resolve(None, {"lc_id": "<x>", "lc_consent": "analytics"}, c)[0], "<x>")


@unittest.skipIf(django is None, "django not installed")
class MiddlewareTest(unittest.TestCase):
    def run_mw(self, cookies):
        rf = RequestFactory()
        for k, v in cookies.items():
            rf.cookies[k] = v  # SimpleCookie.update would store bare strings, not Morsels
        req = rf.get("/")
        seen = {}

        def view(r):
            seen["l"] = r.lucida
            return HttpResponse("ok")

        return LucidaMiddleware(view)(req), seen

    def test_no_cookie_without_consent(self):
        resp, seen = self.run_mw({})
        self.assertNotIn("lc_id", resp.cookies)
        self.assertIs(seen["l"].client, FAKE)

    def test_cookie_with_consent(self):
        resp, seen = self.run_mw({"lc_consent": "analytics"})
        self.assertEqual(resp.cookies["lc_id"].value, seen["l"].distinct_id)

    def test_bootstrap_tag_escapes(self):
        resp, seen = self.run_mw({})
        t = engines["django"].from_string("{% load lucida %}{% lucida_bootstrap %}")
        class R:  # request stand-in carrying the context
            lucida = seen["l"]
        html = t.render({"request": R()})
        self.assertEqual(html.count("</script>"), 1)
        self.assertNotIn("<b>", html)
        data = json.loads(re.search(r">(.*)</script>", html, re.S).group(1))
        self.assertEqual(data["flags"]["x"], "</script><b>&")
        self.assertEqual(data["distinctId"], seen["l"].distinct_id)


@unittest.skipIf(django is None, "django not installed")
class RequestContextTest(unittest.TestCase):
    def run_mw(self, path="/p?a=1", user=None, filt=None, pmap=None, extra=None, tracing=True, **headers):
        from django.test import override_settings

        from lucida import get_context

        req = RequestFactory().get(path, **headers)
        if user is not None:
            req.user = user
        seen = {}

        def view(r):
            c = get_context()
            seen["c"] = c and (c.distinct_id, c.session_id, dict(c.properties))
            return HttpResponse("ok")

        with override_settings(
            LUCIDA_MW_REQUEST_FILTER=filt, LUCIDA_MW_PROPERTIES_MAP=pmap,
            LUCIDA_MW_EXTRA_PROPERTIES=extra or {}, LUCIDA_MW_CAPTURE_TRACING_HEADERS=tracing,
        ):
            LucidaMiddleware(view)(req)
        return seen["c"]

    def test_props_and_tracing_headers(self):
        did, sid, props = self.run_mw(
            extra={"svc": "web"}, HTTP_USER_AGENT="UA", HTTP_X_LUCIDA_DISTINCT_ID="d1", HTTP_X_LUCIDA_SESSION_ID="s1"
        )
        self.assertEqual((did, sid), ("d1", "s1"))
        self.assertEqual(props["$request_path"], "/p")
        self.assertEqual(props["$request_method"], "GET")
        self.assertTrue(props["$current_url"].endswith("/p?a=1"))
        self.assertEqual((props["$user_agent"], props["svc"], props["$ip"]), ("UA", "web", "127.0.0.1"))

    def test_user_beats_header_and_tracing_off(self):
        class U:
            pk, is_authenticated = 42, True

        did, _, _ = self.run_mw(user=U(), HTTP_X_LUCIDA_DISTINCT_ID="spoof")
        self.assertEqual(did, "42")
        did, sid, _ = self.run_mw(tracing=False, HTTP_X_LUCIDA_DISTINCT_ID="d1")
        self.assertEqual((did, sid), (None, None))

    def test_filter_and_properties_map(self):
        self.assertIsNone(self.run_mw(filt=lambda r: False))
        _, _, props = self.run_mw(pmap=lambda p, r: {k: v for k, v in p.items() if k != "$ip"})
        self.assertNotIn("$ip", props)

    def test_async_path(self):
        import asyncio

        from lucida import get_context

        async def view(r):
            self.assertIsNotNone(get_context())
            return HttpResponse("ok")

        mw = LucidaMiddleware(view)
        resp = asyncio.run(mw(RequestFactory().get("/a")))
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
