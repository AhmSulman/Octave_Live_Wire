import json

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse


PAGES = [
    "backing_track_creator:home",
    "backing_track_creator:media_player",
    "backing_track_creator:piano_learner",
    "backing_track_creator:guitar_fretboard",
    "backing_track_creator:backing_track",
    "backing_track_creator:contact",
    "pad:pad",
]


class PageRenderTests(TestCase):
    def test_every_page_renders_with_analytics_and_contact_link(self):
        contact_url = reverse("backing_track_creator:contact")
        for name in PAGES:
            with self.subTest(page=name):
                res = self.client.get(reverse(name))
                self.assertEqual(res.status_code, 200)
                html = res.content.decode()
                self.assertIn("/_vercel/insights/script.js", html)
                self.assertNotIn("cdn.vercel-analytics.com", html)
                if name != "backing_track_creator:contact":
                    self.assertIn(f'href="{contact_url}"', html)

    def test_instrument_pages_load_the_soundfont_sampler(self):
        # Piano, Guitar and Backing Track each wire in the shared sampler.
        for name in (
            "backing_track_creator:piano_learner",
            "backing_track_creator:guitar_fretboard",
            "backing_track_creator:backing_track",
        ):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn("window.OLWSampler", html)
                self.assertIn("gleitz/midi-js-soundfonts", html)  # CC-BY attribution

    def test_contact_page_lists_public_profiles(self):
        html = self.client.get(reverse("backing_track_creator:contact")).content.decode()
        for url in (
            "https://ahmed-salman.vercel.app/",
            "https://github.com/AhmSulman",
            "https://www.linkedin.com/in/ahmed-salman-maan",
            "https://www.youtube.com/@Ahm3dSulman",
        ):
            self.assertIn(url, html)


VALID = {"name": "Test Person", "email": "tester@example.com", "subject": "Hi", "message": "Love the piano page!"}


@override_settings(
    CONTACT_EMAIL="owner@example.com",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="site@example.com",
)
class ContactApiTests(TestCase):
    url = "/api/contact/"

    def post(self, data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_valid_message_is_emailed_with_reply_to(self):
        res = self.post(VALID)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["owner@example.com"])
        self.assertIn("tester@example.com", sent.reply_to[0])
        self.assertIn("Love the piano page!", sent.body)

    def test_validation_errors(self):
        res = self.post({"name": "", "email": "nope", "message": "short"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(set(res.json()["errors"]), {"name", "email", "message"})
        self.assertEqual(len(mail.outbox), 0)

    def test_header_injection_rejected(self):
        res = self.post({**VALID, "subject": "Hi\r\nBcc: victim@example.com"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("subject", res.json()["errors"])
        self.assertEqual(len(mail.outbox), 0)

    def test_honeypot_silently_drops(self):
        res = self.post({**VALID, "website": "http://spam.example"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_json(self):
        res = self.client.post(self.url, "not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    @override_settings(CONTACT_EMAIL="")
    def test_unconfigured_returns_503(self):
        res = self.post(VALID)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(len(mail.outbox), 0)
