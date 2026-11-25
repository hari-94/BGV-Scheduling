"""Fair share (Hari, 25 Nov): rooms go first to whoever has had the fewest
lately, the biggest charts and rounds to them, and whoever has had the most is
the one left over -- instead of the bottom of the staff sheet's list."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import fairness  # noqa: E402

LED = {"from": "2026-10-28", "to": "2026-11-24", "people": {
    "Pat Quill": {"role": "hk", "rooms": 80, "free": 0, "busy": 10, "sched": 10},
    "Robin Mesa": {"role": "hk", "rooms": 20, "free": 3, "busy": 5, "sched": 8},
    "Sam Tide": {"role": "hk", "rooms": 20, "free": 1, "busy": 5, "sched": 6},
}}


class NeedOrder(unittest.TestCase):
    def test_fewest_rooms_first_then_most_free_days(self):
        names = ["Pat Quill", "Sam Tide", "Robin Mesa", "New Person"]
        self.assertEqual(fairness.need_order(names, LED, {}, []),
                         ["New Person", "Robin Mesa", "Sam Tide", "Pat Quill"])

    def test_level_people_keep_the_sheet_order(self):
        led = {"people": {"A B": {"rooms": 5}, "C D": {"rooms": 5}}}
        self.assertEqual(fairness.need_order(["C D", "A B"], led, {}, []), ["C D", "A B"])

    def test_per_day_not_totals_a_new_hire_is_not_favoured_for_months(self):
        # 200 days and 1,200 rooms against 20 days and 160: per day the new
        # hire (8 a day) has had more than the veteran (6), so the veteran goes first.
        led = {"people": {"Vera Old": {"rooms": 1200, "sched": 200, "rate": 6.0},
                          "Nina New": {"rooms": 160, "sched": 20, "rate": 8.0}}}
        self.assertEqual(fairness.need_order(["Nina New", "Vera Old"], led, {}, []),
                         ["Vera Old", "Nina New"])

    def test_the_figure_is_the_rooms_views_rooms_per_day_with_rooms(self):
        # Hari, 25 Nov: rooms over the days they had rooms, every day the same.
        on = {"sched": [("rqs", "RQS", "working", "ON")]}
        by_day = {"2025-12-01": dict(on, **{"in": list("abcdefgh")}),     # 8, a year ago
                  "2026-11-20": dict(on, **{"in": list("abcd")}),         # 4, last week
                  "2026-11-21": dict(on)}                                 # ON, no rooms
        self.assertEqual(fairness._weighted_rate(by_day, "2025-11-25", "2026-11-24", "rqs"), 6.0)

    def test_a_day_with_rooms_is_a_day_on_whatever_the_sheet_said(self):
        by_day = {"2026-11-20": {"fc": ["a", "b", "c", "d"], "sched": []}}
        self.assertEqual(fairness._weighted_rate(by_day, "2026-11-01", "2026-11-24", "hk"), 12.0)

    def test_rqs_role_and_other_work_days_are_not_days_without_rooms(self):
        on = lambda cell, kind="working": {"sched": [("rqs", "RQS", kind, cell)]}
        self.assertTrue(fairness.free_to_work(on("ON"), "rqs"))
        self.assertFalse(fairness.free_to_work(on("RQS 1"), "rqs"))
        self.assertFalse(fairness.free_to_work(on("RQS 2"), "rqs"))
        self.assertFalse(fairness.free_to_work(on("Projects", "other_duty"), "rqs"))
        self.assertTrue(fairness.free_to_work(dict(on("RQS 1"), **{"in": ["a"]}), "rqs"))  # had rooms
        # 10 rooms over one ON day and one RQS 1 day: 10 a day free to inspect, not 5.
        by_day = {"2026-11-20": dict(on("ON"), **{"in": list("abcdefghij")}),
                  "2026-11-21": on("RQS 1")}
        self.assertEqual(fairness._weighted_rate(by_day, "2026-11-01", "2026-11-24", "rqs"), 10.0)

    def test_full_clean_outweighs_daily_service_and_dust_n_vac_is_not_counted(self):
        day = {"fc": ["a"], "ds": ["b", "c"], "dvc": ["d", "e"], "in": ["x"]}
        self.assertEqual(fairness.points(day, "hk"), 3 + 2)
        self.assertEqual(fairness.points(day, "rqs"), 1)      # Full Clean inspections only

    def test_a_first_name_alone_finds_the_one_person_with_it(self):
        self.assertEqual(fairness.lookup("Robin", LED, {}, [])["rooms"], 20)
        led = {"people": {"Sam Tide": {"rooms": 1}, "Sam Lake": {"rooms": 2}}}
        self.assertEqual(fairness.lookup("Sam", led, {}, []), {})      # two Sams: no guess

    def test_snapshot_carries_numbers_and_notes(self):
        s = fairness.snapshot("2026-11-26", LED, ["Robin Mesa", "Pat Quill"], ["Pat Quill"],
                              {}, [], notes={"Pat Quill": "RQS 1 -- no rooms by role"})
        self.assertEqual([(r["rank"], r["name"], r["rooms"]) for r in s["hk"]],
                         [(1, "Robin Mesa", 20), (2, "Pat Quill", 80)])
        self.assertEqual(s["rqs"][0]["note"], "RQS 1 -- no rooms by role")


class HandOut(unittest.TestCase):
    """The scheduler's own functions, taken from the page as the 5 AM build does."""

    @classmethod
    def setUpClass(cls):
        import daily_build
        fn, = daily_build.borrow("assign_hk_building_aware")
        cls.assign_hk = staticmethod(fn)

    def test_biggest_chart_to_the_neediest_and_the_last_left_free(self):
        groups = [
            {"label": "FC-A", "service_type": "Full Clean", "time": 200, "blds": {1}, "rooms": []},
            {"label": "FC-B", "service_type": "Full Clean", "time": 380, "blds": {1}, "rooms": []},
            {"label": "FC-C", "service_type": "Full Clean", "time": 300, "blds": {1}, "rooms": []},
        ]
        roster = {n: {"building": 1, "present": True} for n in ("Ann", "Bea", "Cy", "Di")}
        assignment, used = self.assign_hk(groups, ["Ann", "Bea", "Cy", "Di"], roster)
        self.assertEqual(assignment, {"FC-B": "Ann", "FC-C": "Bea", "FC-A": "Cy"})
        self.assertNotIn("Di", used)


if __name__ == "__main__":
    unittest.main()
