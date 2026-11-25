"""warm.py fills the shared caches once per server process, in the
background, and never stops a page when a read fails (25 Nov)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warm  # noqa: E402


class Warm(unittest.TestCase):
    def setUp(self):
        if hasattr(sys, warm._FLAG):
            delattr(sys, warm._FLAG)

    tearDown = setUp

    def test_once_per_process(self):
        with mock.patch("threading.Thread") as th:
            warm.start()
            warm.start()
        self.assertEqual(th.call_count, 1)
        self.assertTrue(th.call_args.kwargs.get("daemon"))

    def test_a_failed_read_is_only_logged(self):
        import db
        with mock.patch.object(db, "load_staff_weeks", side_effect=RuntimeError("network")), \
                mock.patch.object(db, "load_staff_overrides", return_value={}), \
                mock.patch("floor.today"), mock.patch("staff_names.aliases"), \
                mock.patch("staff_names.attendants"):
            warm._run()          # no raise


if __name__ == "__main__":
    unittest.main()
