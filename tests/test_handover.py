"""Handing the office PC's Microsoft 365 sign-in over to another account
(m365_login.py, credentials._m365_handover; Hari, 25 Nov). A fake sign-in
page, a made-up account; nothing leaves this PC."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import credentials  # noqa: E402
import m365_login  # noqa: E402
import sharepoint  # noqa: E402

SITE = sharepoint.SITE


class El:
    def __init__(self, page, sel, text=""):
        self.page, self.sel, self.text, self.value = page, sel, text, ""

    def is_visible(self):
        return True

    def fill(self, v):
        self.value = v
        self.page.filled[self.sel] = v

    def input_value(self):
        return self.value

    def inner_text(self):
        return self.text


class FakeSignIn:
    """Microsoft's account page -> ADFS's password page -> a phone approval
    (number 42) -> "Stay signed in?" -> SharePoint."""

    def __init__(self, good_password="right", approve_after=2):
        self.step, self.url, self.filled = "account", "https://login.microsoftonline.com/", {}
        self.good, self.approve_after, self.waits = good_password, approve_after, 0
        self.els = {}

    def _el(self, sel, text=""):
        return self.els.setdefault((self.step, sel), El(self, sel, text))

    def query_selector(self, sel):
        if self.step == "account" and sel == "input[name=loginfmt]":
            return self._el(sel)
        if self.step == "adfs" and sel in ("#passwordInput", "#userNameInput"):
            return self._el(sel)
        if self.step == "adfs_bad" and sel == "#errorText":
            return self._el(sel, "Incorrect user ID or password.")
        if self.step == "approve" and sel == "#idRichContext_DisplaySign":
            return self._el(sel, "42")
        if self.step == "kmsi" and sel == "#KmsiCheckboxField":
            return self._el(sel)
        return None

    def click(self, sel):
        if self.step == "account":
            self.step = "adfs"
        elif self.step == "adfs":
            self.step = "approve" if self.filled.get("#passwordInput") == self.good else "adfs_bad"
        elif self.step == "kmsi":
            self.step, self.url = "done", SITE + "/SitePages/Home.aspx"

    def wait_for_timeout(self, ms):
        if self.step == "approve":
            self.waits += 1
            if self.waits >= self.approve_after:
                self.step = "kmsi"


def done(pg):
    return pg.url.startswith(SITE)


class Drive(unittest.TestCase):
    def test_signs_in_through_adfs_and_shows_the_approval_number(self):
        page, told = FakeSignIn(), []
        ok, msg = m365_login._drive(page, "pat.quill@example.com", "right", told.append,
                                    time.time() + 30, done)
        self.assertTrue(ok, msg)
        self.assertEqual(page.filled["input[name=loginfmt]"], "pat.quill@example.com")
        self.assertEqual(told, ["approve the sign-in on the phone -- number 42"])

    def test_a_wrong_password_says_so(self):
        ok, msg = m365_login._drive(FakeSignIn(), "pat.quill@example.com", "wrong", lambda m: None,
                                    time.time() + 30, done)
        self.assertFalse(ok)
        self.assertIn("Incorrect", msg)

    def test_an_approval_never_given_times_out(self):
        ok, msg = m365_login._drive(FakeSignIn(approve_after=10 ** 6), "pat.quill@example.com",
                                    "right", lambda m: None, time.time() + 0.3, done)
        self.assertFalse(ok)
        self.assertIn("approval", msg)


class HandOver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp.name) / "agent.json"
        self.cfg_path.write_text(json.dumps({"hotsos_user": "x"}))
        self.req = {"id": "1", "service": "m365", "action": "set",
                    "username": "pat.quill@example.com", "sealed": "s", "by": "t"}
        self.old = sharepoint.PROFILE

    def tearDown(self):
        sharepoint.PROFILE = self.old
        self.tmp.cleanup()

    def run_it(self, result):
        with mock.patch.object(credentials, "_open", return_value="pw"), \
                mock.patch.object(credentials, "_private_key"), \
                mock.patch.object(credentials.db, "_upsert_key"), \
                mock.patch.object(m365_login, "sign_in", return_value=result), \
                mock.patch.object(m365_login, "save_password") as saved:
            out = credentials._m365_handover(self.req, json.loads(self.cfg_path.read_text()),
                                             self.cfg_path, "PC1", print)
        return out, saved

    def test_a_failed_sign_in_changes_nothing(self):
        (ok, msg, _), saved = self.run_it((False, "Incorrect user ID or password.", "/new"))
        self.assertFalse(ok)
        self.assertNotIn("m365_user", json.loads(self.cfg_path.read_text()))
        self.assertEqual(sharepoint.PROFILE, self.old)
        saved.assert_not_called()

    def test_a_good_sign_in_switches_the_profile(self):
        (ok, msg, _), saved = self.run_it((True, "signed in; reads GC8 Inspections", "/new"))
        self.assertTrue(ok, msg)
        cfg = json.loads(self.cfg_path.read_text())
        self.assertEqual((cfg["m365_user"], cfg["m365_profile"], cfg["hotsos_user"]),
                         ("pat.quill@example.com", "/new", "x"))
        self.assertEqual(sharepoint.PROFILE, "/new")
        saved.assert_called_once_with("pat.quill@example.com", "pw")

    def test_the_old_window_is_not_used_after_a_hand_over(self):
        sharepoint.PROFILE = "/new"
        with self.assertRaises(RuntimeError):
            sharepoint._cdp(None)


if __name__ == "__main__":
    unittest.main()
