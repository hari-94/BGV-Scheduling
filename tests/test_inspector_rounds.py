"""Inspector rounds use the fewest people (Hari, 25 Nov: "max utilization --
one RQS can do 13"), never more than 13 Full Clean rooms each, and never
buildings 2 and 3 together. The page's own function, as the 5 AM build runs it."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def chart(label, rooms):
    return {"label": label, "service_type": "Full Clean", "time": 90 * len(rooms),
            "rooms": [{"room": r, "time": 90} for r in rooms],
            "blds": {int(r[0]) for r in rooms}}


class Rounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import daily_build
        fn, = daily_build.borrow("assign_inspectors")
        cls.assign = staticmethod(fn)

    def test_26_nov_two_rounds_not_three(self):
        # 26 Nov's four charts: FC-A crosses 1 and 3, FC-D crosses 1 and 2.
        groups = [chart("FC-A", ["1321A", "3346H", "3349H"]),
                  chart("FC-B", ["2331A", "2331B", "2434A", "2434B"]),
                  chart("FC-C", ["2334B", "2335B", "2336E", "2336G"]),
                  chart("FC-D", ["1424H", "2135A", "2135B", "2334A"])]
        self.assign(groups, ["Ann Ray", "Bea Cole", "Cy Park"], 3, "Rae One", "Rob Two")
        rounds = {}
        for g in groups:
            rounds.setdefault(g["inspector"], []).append(g)
        self.assertEqual(len(rounds), 2, {k: [g["label"] for g in v] for k, v in rounds.items()})
        for name, gs in rounds.items():
            self.assertLessEqual(sum(len(g["rooms"]) for g in gs), 13)
            blds = set().union(*(g["blds"] for g in gs))
            self.assertFalse({2, 3} <= blds, f"{name} holds buildings 2 and 3")
        # The neediest (first in the list) takes the big round.
        self.assertEqual(sorted(g["label"] for g in rounds["Ann Ray"]), ["FC-B", "FC-C", "FC-D"])
        self.assertNotIn("Cy Park", rounds)


if __name__ == "__main__":
    unittest.main()
