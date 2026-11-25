"""Passwords (25 Nov): stored as PBKDF2, old one-round hashes still sign in
and are rewritten at that sign-in, and a username is refused for a while
after five wrong passwords. Made-up accounts; no database."""
import hashlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402


class Hashes(unittest.TestCase):
    def test_new_hashes_are_pbkdf2_and_check(self):
        h = db._hash_pw("Pat1234", rounds=1000)
        self.assertTrue(h.startswith("pbkdf2$1000$"))
        self.assertTrue(db._check_pw("Pat1234", h))
        self.assertFalse(db._check_pw("pat1234", h))

    def test_old_forms_still_sign_in(self):
        plain = hashlib.sha256(b"Pat1234").hexdigest()
        salted = "ab12:" + hashlib.sha256(b"ab12Pat1234").hexdigest()
        self.assertTrue(db._check_pw("Pat1234", plain))
        self.assertTrue(db._check_pw("Pat1234", salted))
        self.assertTrue(db._needs_rehash(plain) and db._needs_rehash(salted))
        self.assertFalse(db._needs_rehash(db._hash_pw("x")))


class SignIn(unittest.TestCase):
    def setUp(self):
        db._LOGIN_FAILS.clear()
        self.user = {"username": "pquill@example.com", "role": "housekeeper",
                     "password_hash": hashlib.sha256(b"Pat1234").hexdigest()}
        self.client = mock.MagicMock()

    def sign_in(self, pw):
        with mock.patch.object(db, "get_user", return_value=dict(self.user)), \
                mock.patch.object(db, "_client", return_value=self.client):
            return db.authenticate("pquill@example.com", pw)

    def test_an_old_hash_is_rewritten_at_sign_in(self):
        self.assertIsNotNone(self.sign_in("Pat1234"))
        stored = [c.args[0] for c in self.client.table.return_value.update.call_args_list
                  if "password_hash" in c.args[0]]
        self.assertEqual(len(stored), 1)
        self.assertTrue(db._check_pw("Pat1234", stored[0]["password_hash"]))

    def test_five_wrong_passwords_lock_the_username(self):
        for _ in range(db.LOGIN_MAX_FAILS):
            self.assertIsNone(self.sign_in("wrong"))
        self.assertGreater(db.login_locked("PQuill@example.com "), 0)
        self.assertIsNone(self.sign_in("Pat1234"))          # even the right one, for now
        self.assertEqual(db.login_locked("someone.else@example.com"), 0)

    def test_the_lock_ends_and_a_success_clears_the_count(self):
        for _ in range(db.LOGIN_MAX_FAILS - 1):
            self.sign_in("wrong")
        self.assertIsNotNone(self.sign_in("Pat1234"))
        self.assertEqual(db._LOGIN_FAILS.get("pquill@example.com"), None)
        import time
        for _ in range(db.LOGIN_MAX_FAILS):
            self.sign_in("wrong")
        self.assertEqual(db.login_locked("pquill@example.com", now=time.time() + db.LOGIN_WINDOW + 1), 0)


if __name__ == "__main__":
    unittest.main()
