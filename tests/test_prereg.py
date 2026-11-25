"""The front desk's Pre-Reg list on their board (prereg.py; Hari, 25 Nov).
Made-up guests and numbers throughout."""
import io
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import db  # noqa: E402
import frontdesk as fd  # noqa: E402
import prereg  # noqa: E402

KNOWN = {"3246E", "3246G", "3246H", "3246I", "1426A", "1426B", "2336H", "2336I", "1430A"}


def workbook(rows):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "FD Daily Task List"
    ws = wb.create_sheet("Pre-Reg")
    ws.append([None] * 12)
    ws.append(["Name", "Room", "Phone number", "Text or call", "Keys Made y/n",
               "TSW Check-In Status ( Pre check-in = Before 12:00 PM)",
               "NOTES - Add if a Fixed Week or if added from Arrivals", "Mobile Keys y/n",
               "Other numbers that want keys", "Rushed? Do NOT rush after 1pm!",
               "Added to the pre-reg Zingle.", "Room Ready Zingled"])
    for r in rows:
        ws.append(r)
    for _ in range(60):                       # the tab's formatted blank rows
        ws.append([None] * 9 + [False, False, False])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Split(unittest.TestCase):
    def test_combined_units_come_apart(self):
        self.assertEqual(prereg.split("3246EGHI", KNOWN), ["3246E", "3246G", "3246H", "3246I"])
        self.assertEqual(prereg.split("2336HI", KNOWN), ["2336H", "2336I"])
        self.assertEqual(prereg.split("2336 H/I", KNOWN), ["2336H", "2336I"])
        self.assertEqual(prereg.split("3246eghi", KNOWN), ["3246E", "3246G", "3246H", "3246I"])

    def test_several_units_in_one_cell(self):
        self.assertEqual(prereg.split("1426B + 2336HI", KNOWN), ["1426B", "2336H", "2336I"])
        self.assertEqual(prereg.split("1426B, 1430A and 2336HI", KNOWN),
                         ["1426B", "1430A", "2336H", "2336I"])

    def test_a_bare_number_is_every_room_of_it(self):
        self.assertEqual(prereg.split("1426", KNOWN), ["1426A", "1426B"])
        self.assertEqual(prereg.split("9999", KNOWN), ["9999"])

    def test_nothing_that_is_not_a_room(self):
        self.assertEqual(prereg.split("", KNOWN), [])
        self.assertEqual(prereg.split("walk-in", KNOWN), [])


class Parse(unittest.TestCase):
    def test_rows_read_and_private_columns_left_behind(self):
        data = workbook([
            ["Quill", "3246EGHI", "5550100", "Text or call", "y", "Pre check-in", "Fixed week",
             "y", "5550199", True, True, False],
            ["Mesa", "1426B", "5550101", "Text or call", "n", "Pending", "", "", "", False, False, False],
            [None, None, None, None, None, None, None, None, None, False, False, False],
            ["Tide", "2336HI", "5550102", "", "n", "", "GC8 Club", "", "", False, True, True],
        ])
        es = prereg.parse(data, KNOWN)
        self.assertEqual([e["rooms"] for e in es],
                         [["3246E", "3246G", "3246H", "3246I"], ["1426B"], ["2336H", "2336I"]])
        first = es[0]
        self.assertEqual((first["keys"], first["mobile"], first["rushed"], first["zingle_added"],
                          first["ready_zingled"], first["checkin"], first["notes"]),
                         (True, True, True, True, False, "Pre check-in", "Fixed week"))
        flat = repr(es)
        for private in ("Quill", "Mesa", "Tide", "5550100", "5550199"):
            self.assertNotIn(private, flat)


class Days(unittest.TestCase):
    E = [{"unit": "1426B", "rooms": ["1426B"], "checkin": "", "notes": ""}]

    def test_yesterdays_list_not_cleared_is_not_todays(self):
        prev = {"date": "2026-11-24", "first_seen": "2026-11-24", "entries": self.E}
        rec = prereg.keep(self.E, day="2026-11-25", prev=prev)
        self.assertTrue(rec["carried"])
        self.assertEqual(prereg.for_day(rec, "2026-11-25"), {})

    def test_a_new_list_counts(self):
        prev = {"date": "2026-11-24", "first_seen": "2026-11-24", "entries": self.E}
        new = self.E + [{"unit": "2336HI", "rooms": ["2336H", "2336I"], "checkin": "", "notes": ""}]
        rec = prereg.keep(new, day="2026-11-25", prev=prev)
        self.assertFalse(rec["carried"])
        self.assertEqual(sorted(prereg.for_day(rec, "2026-11-25")), ["1426B", "2336H", "2336I"])
        self.assertEqual(prereg.for_day(rec, "2026-11-26"), {})

    def test_a_failed_read_keeps_the_last_list(self):
        prev = {"date": "2026-11-25", "first_seen": "2026-11-25", "entries": self.E}
        with mock.patch.object(db, "_load_key", return_value=prev), \
                mock.patch.object(db, "_upsert_key") as up:
            out = prereg.refresh(fetch=lambda: (None, {"error": "signed out"}))
        self.assertEqual(out, {"error": "signed out"})
        kept = up.call_args[0][1]
        self.assertEqual(kept["entries"], self.E)
        self.assertEqual(kept["error"], "signed out")


class Board(unittest.TestCase):
    CHARTS = [{"label": "FC-A", "service_type": "Full Clean", "housekeeper": "Ann Ray",
               "inspector": "Bea Cole",
               "rooms": [{"room": "2336H", "time": 120, "arriving": "Quill, P"},
                         {"room": "1430A", "time": 70}]}]

    def test_pre_reg_rooms_carry_the_list_and_off_chart_ones_show(self):
        e = {"unit": "2336HI", "rooms": ["2336H", "2336I"], "keys": True, "checkin": "Pending",
             "notes": "", "rushed": False, "mobile": False, "zingle_added": True, "ready_zingled": False}
        statuses = {"2336I": {"status": "inspected", "housekeeper": "Cy Park"}}
        rows = {r["room"]: r for r in fd.board(self.CHARTS, statuses, {},
                                               prereg={"2336H": e, "2336I": e})}
        self.assertEqual(rows["2336H"]["prereg"]["unit"], "2336HI")
        self.assertEqual(rows["2336H"]["hk"], "Ann Ray")
        self.assertIsNone(rows["1430A"]["prereg"])
        self.assertTrue(rows["2336I"]["off_charts"])
        self.assertEqual(rows["2336I"]["status"], "inspected")
        self.assertEqual(rows["2336I"]["hk"], "Cy Park")


if __name__ == "__main__":
    unittest.main()
