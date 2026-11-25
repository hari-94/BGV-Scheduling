"""The login message the Admin page offers to copy after Create User or a
password reset (Hari, 25 Nov). Made-up people."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import account_links  # noqa: E402


class Welcome(unittest.TestCase):
    def test_new_housekeeper(self):
        t = account_links.welcome_text("pquill@example.com", "Pat1234", "Pat Quill", "housekeeper")
        self.assertTrue(t.startswith("Hi Pat, welcome to the GC8 Housekeeping app!"))
        for line in (f"Website: {account_links.APP_URL}", "Login ID: pquill@example.com",
                     "Password: Pat1234", "My Home", "Profile page"):
            self.assertIn(line, t)

    def test_reset_and_no_name(self):
        t = account_links.welcome_text("rmesa@example.com", "Rob9876", "", "rqs", reset=True)
        self.assertTrue(t.startswith("Hi, your password for the GC8 Housekeeping app has been reset."))
        self.assertIn("Password: Rob9876", t)


if __name__ == "__main__":
    unittest.main()
