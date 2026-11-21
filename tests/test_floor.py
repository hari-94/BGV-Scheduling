"""
The shared floor (floor.py) and the front desk's board and marks
(frontdesk.py), pinned down -- plus the office PC's rule that makes it the
only place charts follow HotSOS (hotsos_agent.reconcile_charts).

Run:  .venv\\Scripts\\python -m unittest discover -s tests -v

No database: db's functions are replaced for each test.
"""
import copy
import datetime as dt
import unittest
from unittest import mock

import clock
import daystart
import db
import floor
import frontdesk as fd

DAY = "2026-11-21"
NOW = dt.datetime(2026, 11, 21, 11, 0, tzinfo=clock.MTN)

CHARTS = [
    {"label": "FC-A", "service_type": "Full Clean", "housekeeper": "Ana Lopez",
     "inspector": "Grace Vargas",
     "rooms": [{"room": "2336E", "time": 120, "late_checkout": "Late Out: 12:00 pm",
                "notes": "Dog arriving", "arriving": "Smith, Jo", "guest": "Lee, Al"},
               {"room": "2336G", "time": 70, "late_checkout": "", "notes": "",
                "arriving": ""}]},
    {"label": "FC-B", "service_type": "Full Clean", "housekeeper": "No HK available",
     "inspector": "Inspector 3",
     "rooms": [{"room": "3024A", "time": 120, "notes": "added on the sheet",
                "added_on_sheet": "2026-11-21T10:40:00-07:00"}]},
    {"label": "VERIFY-A", "service_type": "Full Clean", "housekeeper": "", "inspector": "",
     "verify_group": True, "rooms": [{"room": "2233A", "time": 70}]},
]
STATUSES = {
    "2336E": {"status": "cleaning_started", "housekeeper": "Ana Lopez",
              "started_at": "2026-11-21T16:30:00+00:00"},          # 9:30 am
    # Return Later: HotSOS's timeline carries when it *expects* the start.
    "2336G": {"status": "return_later", "housekeeper": "Ana Lopez",
              "started_at": "2026-11-21T21:48:00+00:00"},          # 2:48 pm, still to come
}


class Marks(unittest.TestCase):
    def test_late_out_reaches_the_route(self):
        r = fd.overlay_room(CHARTS[0]["rooms"][0], {"late_out": "13:00"})
        self.assertEqual(r["late_checkout"], "Late Out: 1:00 pm")
        self.assertEqual(r["late_checkout_report"], "Late Out: 12:00 pm")
        self.assertEqual(daystart.release_minute(r), 13 * 60)

    def test_departed_means_nothing_to_wait_for(self):
        r = fd.overlay_room(CHARTS[0]["rooms"][0],
                            {"late_out": "13:00", "departed_at": "2026-11-21T10:42:00-07:00"})
        self.assertEqual(r["late_checkout"], "")
        self.assertIsNone(daystart.release_minute(r))
        self.assertEqual(r["fd_departed"], "2026-11-21T10:42:00-07:00")

    def test_apply_never_changes_the_charts_it_is_given(self):
        before = copy.deepcopy(CHARTS)
        out = fd.apply(CHARTS, {"2336E": {"notes": [{"id": "a", "text": "crib"}]}})
        self.assertEqual(CHARTS, before)
        self.assertEqual(out[0]["rooms"][0]["fd_notes"], ["crib"])

    def test_offered_times(self):
        self.assertEqual(fd.LATE_TIMES[0], "10:15")
        self.assertEqual(fd.LATE_TIMES[-1], "18:00")
        self.assertEqual(fd.hhmm12("12:00"), "12:00 pm")
        self.assertEqual(fd.hhmm12("10:30"), "10:30 am")

    def test_a_time_not_offered_or_not_a_room_is_refused(self):
        with mock.patch.object(db, "_load_key_raw", return_value=None), \
                mock.patch.object(db, "_upsert_key") as up:
            with self.assertRaises(ValueError):
                fd.set_late_out(DAY, "2336E", "09:00", "t")
            with self.assertRaises(ValueError):
                fd.add_note(DAY, "ZZZ", "x", "t")
            with self.assertRaises(ValueError):
                fd.add_note(DAY, "2336E", "   ", "t")
            up.assert_not_called()

    def test_a_room_left_with_nothing_is_deleted(self):
        saved = {"room": "2336E", "date": DAY, "late_out": "13:00"}
        with mock.patch.object(db, "_load_key_raw", return_value=saved), \
                mock.patch.object(db, "_upsert_key") as up, \
                mock.patch.object(db, "_delete_key") as dl:
            fd.set_late_out(DAY, "2336e", None, "Front Desk")
            dl.assert_called_once_with(f"fdmark_{DAY}_2336E")
            up.assert_not_called()


class Board(unittest.TestCase):
    def rows(self, marks=None, unplaced=()):
        return {r["room"]: r for r in fd.board(CHARTS, STATUSES, marks or {}, now=NOW,
                                               unplaced=unplaced)}

    def test_every_room_once_with_people_and_status(self):
        rows = self.rows()
        self.assertEqual(sorted(rows), ["2233A", "2336E", "2336G", "3024A"])
        e = rows["2336E"]
        self.assertEqual((e["hk"], e["rqs"], e["label"]), ("Ana Lopez", "Grace Vargas",
                                                            "Cleaning Started"))
        self.assertEqual(e["started"], "9:30 am")
        # "No HK available" and "Inspector 3" are holes, not people.
        self.assertEqual((rows["3024A"]["hk"], rows["3024A"]["rqs"]), ("", ""))
        self.assertTrue(rows["2233A"]["held"])

    def test_a_start_still_to_come_is_not_shown(self):
        self.assertEqual(self.rows()["2336G"]["started"], "")

    def test_the_arrival_reports_late_out_is_captured_by_itself(self):
        e = self.rows()["2336E"]
        self.assertEqual((e["late_report"], e["late_report_value"], e["late_out"]),
                         ("12:00 pm", "12:00", ""))

    def test_the_desks_late_out_wins_and_the_report_is_kept(self):
        e = self.rows({"2336E": {"late_out": "13:30"}})["2336E"]
        self.assertEqual((e["late_out"], e["late_out_value"], e["late_report"]),
                         ("1:30 pm", "13:30", "12:00 pm"))

    def test_rooms_added_on_the_sheet(self):
        rows = self.rows(unplaced=[{"room": "1421c", "service": "Full Clean", "rqs": "Hari",
                                    "notes": "early departure"},
                                   {"room": "2336E", "service": "Full Clean"}])  # charted: once
        self.assertTrue(rows["3024A"]["added"])
        self.assertEqual(rows["3024A"]["notes"], [])          # the tag says it, not a note
        self.assertTrue(rows["1421C"]["added"] and rows["1421C"]["unassigned"])
        self.assertEqual(rows["1421C"]["notes"], ["early departure"])
        self.assertEqual(len(rows), 5)


class SharedFloor(unittest.TestCase):
    def setUp(self):
        floor._SNAP.clear()
        floor._STALE.clear()
        self.fetches = 0

        def fetch(day):
            self.fetches += 1
            return floor.Floor(day, {"groups_data": CHARTS}, STATUSES,
                               {"2336E": {"late_out": "13:00"}}, [], {"at": "x"})
        self.p = mock.patch.object(floor, "_fetch", side_effect=fetch)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        floor._SNAP.clear()
        floor._STALE.clear()

    def test_one_read_serves_every_page(self):
        for _ in range(20):
            floor.today(day=DAY)
        self.assertEqual(self.fetches, 1)

    def test_a_write_makes_it_fresh(self):
        floor.today(day=DAY)
        floor.invalidate(DAY)
        floor.today(day=DAY)
        self.assertEqual(self.fetches, 2)

    def test_marks_are_on_the_charts_every_page_reads(self):
        f = floor.today(day=DAY)
        self.assertEqual(f.charts[0]["rooms"][0]["late_checkout"], "Late Out: 1:00 pm")
        self.assertEqual(f.raw_charts[0]["rooms"][0]["late_checkout"], "Late Out: 12:00 pm")

    def test_copies_protect_the_shared_floor(self):
        f = floor.today(day=DAY)
        charts, statuses = floor.copies(f)
        charts[0]["rooms"].clear()
        statuses.clear()
        self.assertEqual(len(f.charts[0]["rooms"]), 2)
        self.assertEqual(len(f.statuses), 2)

    def test_a_failed_refresh_keeps_the_last_floor(self):
        first = floor.today(day=DAY)
        self.p.stop()
        with mock.patch.object(floor, "_fetch", side_effect=RuntimeError("network")):
            self.assertIs(floor.today(fresh=True, day=DAY), first)
        self.p.start()

    def test_db_writes_to_the_floors_tables_make_it_stale(self):
        floor.today(day=clock.today_iso())
        with mock.patch.object(db, "_client"):
            db._upsert_key("fdmark_2000-01-01_1111A", {"room": "1111A"})
        self.assertTrue(floor._STALE.get(clock.today_iso()))
        floor._STALE.clear()
        with mock.patch.object(db, "_client"):
            db._upsert_key("report_names", {})                 # not the floor's
        self.assertFalse(floor._STALE.get(clock.today_iso()))


class HandedOutInHotSOS(unittest.TestCase):
    """No push got through today, yet the team is handing rooms out in HotSOS
    (20 Nov): the office PC takes HotSOS as the truth -- the only place the
    charts follow it now that the pages no longer do (floor.py)."""

    def run_it(self, held, truth=None, generated_by="auto-5am"):
        import hotsos_agent as ag
        import app_sync
        sched = {"groups_data": CHARTS, "generated_by": generated_by,
                 "generated_at": "2026-11-21T05:05:00-07:00"}
        written = {}
        with mock.patch.object(ag.db, "_load_key", return_value=truth or {}), \
                mock.patch.object(ag.db, "load_full_schedule", return_value=sched), \
                mock.patch.object(ag.db, "_upsert_key", side_effect=lambda k, v: written.update({k: v})), \
                mock.patch.object(ag, "log"), \
                mock.patch.object(app_sync, "from_hotsos",
                                  return_value={"changed": False}) as fh:
            ag.reconcile_charts(held)
        return written, fh.called

    def test_hotsos_holding_todays_rooms_becomes_the_truth(self):
        written, ran = self.run_it(held=12)
        self.assertIn("hotsos_truth_since", written)
        self.assertTrue(ran)

    def test_a_few_stray_holders_are_not_enough(self):
        written, ran = self.run_it(held=2)
        self.assertEqual(written, {})
        self.assertFalse(ran)

    def test_a_plan_made_after_the_build_is_left_alone(self):
        written, ran = self.run_it(held=12, generated_by="hvardan@grandtimber.com")
        self.assertEqual(written, {})
        self.assertFalse(ran)


class BoardScript(unittest.TestCase):
    """The board's script has no build step and nothing checks it but a
    browser: on 21 Nov one apostrophe in a tooltip ("today's") ended a
    single-quoted string and the board never drew. node checks it where node
    exists (the GitHub runner has it)."""

    def test_the_board_script_parses(self):
        import pathlib
        import re
        import shutil
        import subprocess
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed here")
        html = (pathlib.Path(__file__).resolve().parent.parent / "components" / "frontdesk_board"
                / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(scripts)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write("\n".join(scripts))
        out = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main()
