import json

from django.test import TestCase
from django.urls import reverse

from pad.views import _execute


class SandboxSecurityTests(TestCase):
    """The /pad/run/ endpoint runs user Python in-process, so the AST filter
    is the security boundary. These lock the known escape routes shut."""

    ESCAPES = [
        "().__class__.__base__.__subclasses__()",
        "play_note.__func__.__globals__",
        "print('{0.__class__}'.format(1))",
        "print(__builtins__)",
        "getattr(play_note, 'x')",
        "def g():\n    yield 1\ng().gi_frame",
        "[].__class__",
        "''.join.__self__",
    ]

    def test_escapes_are_blocked(self):
        for code in self.ESCAPES:
            with self.subTest(code=code):
                self.assertIsNotNone(_execute(code)["error"])

    def test_import_blocked(self):
        self.assertIn("import", _execute("import os")["error"])

    def test_legit_music_code_runs(self):
        r = _execute("for i in range(4):\n    play_note(i, quarter_note)")
        self.assertIsNone(r["error"])
        self.assertEqual(len(r["events"]), 4)

    def test_event_cap_enforced(self):
        r = _execute("for i in range(100000):\n    play_note(0)")
        self.assertIsNotNone(r["error"])

    def test_new_instruments_accepted(self):
        for inst in ("guitar", "epiano"):
            with self.subTest(inst=inst):
                r = _execute(f"set_instrument('{inst}')\nplay_note(0)")
                self.assertIsNone(r["error"])
                self.assertEqual(r["events"][0]["instrument"], inst)


class RunEndpointTests(TestCase):
    def test_oversized_track_rejected(self):
        body = {"tracks": [{"code": "x" * 50_001, "armed": True}]}
        res = self.client.post(reverse("pad:run_code"), json.dumps(body), content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_bad_body(self):
        res = self.client.post(reverse("pad:run_code"), "nope", content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("pad:run_code")).status_code, 405)
