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
