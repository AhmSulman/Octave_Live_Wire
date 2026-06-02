from django.test import TestCase
from django.urls import reverse


class BassistViewTests(TestCase):
    def test_url_resolves(self):
        self.assertEqual(reverse("bassist:bassist"), "/bassist/")

    def test_page_renders(self):
        """The page must render (catches template syntax/tag errors)."""
        resp = self.client.get("/bassist/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "bassist/bassist.html")

    def test_sets_csrf_cookie(self):
        resp = self.client.get("/bassist/")
        self.assertIn("csrftoken", resp.cookies)

    def test_has_core_ui_hooks(self):
        """Key element IDs the front-end JS depends on must be present."""
        body = self.client.get("/bassist/").content.decode()
        for hook in (
            'id="playBtn"', 'id="micBtn"', 'id="bpm"', 'id="pattern"',
            'id="drumStyle"', 'id="intensity"', 'id="fillSel"',
            'id="cmdInput"', 'id="quickCmds"', 'id="bandLog"',
            'id="strings"', 'id="tunerMode"', 'id="tuneStatus"',
            'id="detNote"', 'id="needle"', 'id="levelFill"',
            'id="recBtn"', 'id="recList"', 'id="waitOn"',
        ):
            self.assertIn(hook, body, f"missing UI hook: {hook}")

    def test_loads_tonejs(self):
        body = self.client.get("/bassist/").content.decode()
        self.assertIn("tone@14", body)


class HomeIntegrationTests(TestCase):
    def test_home_links_to_bassist(self):
        body = self.client.get("/").content.decode()
        self.assertIn("/bassist/", body)
        self.assertIn("Bassist Bot", body)
