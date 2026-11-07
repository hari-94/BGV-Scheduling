"""The morning Teams notes: who the card names for each room.

Run: .venv\\Scripts\\python -m unittest tests.test_teams_notes -v
"""
import datetime as dt
import unittest

import teams_notes as tn

ROWS = [{"room": "1324E", "hskp": "Elizabeth Rivera", "rqs": "Claudia Perez"},
        {"room": "1222E", "hskp": "Federico Lopez", "rqs": "Hari Vardan"},
        {"room": "1222F", "hskp": "Bryan Molina", "rqs": "Bryan Molina"}]


class RoomMoves(unittest.TestCase):
    def test_move_into_a_lockoff_names_each_door(self):
        # 7 Nov: "1324E - 1222EF" went out as "to: not on today's sheet",
        # though the sheet had 1222E and 1222F, each with someone on it.
        msg = tn.build(dt.date(2026, 11, 7), "Room Moves:\n1324E - 1222EF\n", ROWS)
        heads = dict(msg["housekeeping"]["blocks"])
        line = heads["Room Moves"][0]
        self.assertNotIn("not on today's sheet", line)
        self.assertIn("1222E: HK Federico Lopez", line)
        self.assertIn("1222F: HK Bryan Molina", line)
        self.assertIn("from: HK Elizabeth Rivera", line)

    def test_room_truly_off_the_sheet_still_says_so(self):
        msg = tn.build(dt.date(2026, 11, 7), "Room Moves:\n1324E - 3349AB\n", ROWS)
        line = dict(msg["housekeeping"]["blocks"])["Room Moves"][0]
        self.assertIn("to: not on today's sheet", line)


if __name__ == "__main__":
    unittest.main()
