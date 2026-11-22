"""The Runner Report's RQS lines: the team's own way of writing rooms, and an
RQS with rooms in two buildings listed under both."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import eng_sheet  # noqa: E402


class RoomsText(unittest.TestCase):
    def test_lockoffs_grouped_and_joined_with_plus(self):
        self.assertEqual(eng_sheet.rooms_text(["1020B", "1010D", "1020A"]), "1010D + 1020AB")
        self.assertEqual(eng_sheet.rooms_text(["3031H", "3031E", "3031G", "3031F", "3010C"]),
                         "3010C + 3031EFGH")
        self.assertEqual(eng_sheet.rooms_text(["3024A", "3024A"]), "3024A")


class RqsRooms(unittest.TestCase):
    def test_two_buildings_two_lines(self):
        rows = [
            {"room": "1010D", "service": "Full Clean", "rqs": "Alex Rivera"},
            {"room": "1020A", "service": "Full Clean", "rqs": "Alex Rivera"},
            {"room": "1020B", "service": "Full Clean", "rqs": "Alex Rivera"},
            {"room": "3010C", "service": "Full Clean", "rqs": "Alex Rivera"},
            {"room": "3241B", "service": "Dust n Vac", "rqs": "Sam Molina"},
        ]
        out = eng_sheet.rqs_rooms(rows)
        self.assertEqual(out["1"], [["Alex", "1010D + 1020AB"]])
        self.assertEqual(out["3"], [["Alex", "3010C"]])
        self.assertNotIn("Sam", str(out))       # Dust n Vac isn't an RQS inspection


if __name__ == "__main__":
    unittest.main()
