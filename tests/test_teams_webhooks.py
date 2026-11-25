"""The Teams chats' workflow addresses (25 Nov): set from the Admin page, the
old one kept for an undo, never shown in full. Made-up addresses."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402
import teams_notes as tn  # noqa: E402

A = ("https://example0001.aa.environment.api.powerplatform.com:443/powerautomate/automations/"
     "direct/workflows/aaa/triggers/manual/paths/invoke?api-version=1&sp=%2Fx&sv=1.0&sig=SECRETAAA111")
B = A.replace("aaa", "bbb").replace("SECRETAAA111", "SECRETBBB222")


class Webhooks(unittest.TestCase):
    def setUp(self):
        self.store = {tn.WEBHOOKS_KEY: {"housekeeping": A, "flows": {"housekeeping": "old flow"}}}
        self.p1 = mock.patch.object(db, "_load_key", side_effect=lambda k: self.store.get(k))
        self.p2 = mock.patch.object(db, "_upsert_key", side_effect=lambda k, v: self.store.__setitem__(k, v))
        self.p1.start(); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop()

    def test_only_a_workflow_address_is_taken(self):
        self.assertIsNone(tn.valid_url(A))
        self.assertIsNotNone(tn.valid_url("http://example.com/x"))
        self.assertIsNotNone(tn.valid_url("https://evil.example.com/" + "x" * 80))
        self.assertIsNotNone(tn.valid_url(A[:50]))
        with self.assertRaises(ValueError):
            tn.set_webhook("housekeeping", "https://nope", "t")
        with self.assertRaises(ValueError):
            tn.set_webhook("somewhere", A, "t")

    def test_a_new_address_keeps_the_old_one_for_undo(self):
        tn.set_webhook("housekeeping", B, "pat", "new flow")
        rec = self.store[tn.WEBHOOKS_KEY]
        self.assertEqual(rec["housekeeping"], B)
        self.assertEqual(rec["flows"]["housekeeping"], "new flow")
        self.assertEqual(rec["history"]["housekeeping"][0]["url"], A)
        tn.undo_webhook("housekeeping", "pat")
        self.assertEqual(self.store[tn.WEBHOOKS_KEY]["housekeeping"], A)

    def test_the_address_is_never_shown_in_full(self):
        m = tn.mask(A)
        self.assertNotIn("SECRETAAA", m)
        self.assertNotIn("workflows/aaa", m)
        self.assertEqual(tn.mask(""), "not set")


if __name__ == "__main__":
    unittest.main()
