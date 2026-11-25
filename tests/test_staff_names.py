"""A name typed on the staff sheet finds its full name whatever its case,
spacing or trailing dot ("Luis U." one week, "Luis U" the next -- 25 Nov)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import staff_names  # noqa: E402

TABLE = {"Pat Q": "Pat Quill", "Robin": "Robin Mesa"}


class Full(unittest.TestCase):
    def test_trailing_dot_case_and_spaces(self):
        for typed in ("Pat Q", "Pat Q.", "pat q", "PAT  Q.", " Pat Q "):
            self.assertEqual(staff_names.full(typed, TABLE), "Pat Quill", typed)

    def test_section_suffix_kept(self):
        self.assertEqual(staff_names.full("Robin · Houseperson AM", TABLE),
                         "Robin Mesa · Houseperson AM")

    def test_unknown_name_left_as_typed(self):
        self.assertEqual(staff_names.full("Sam T.", TABLE), "Sam T.")


class OneNameEach(unittest.TestCase):
    ATT = [{"id": 1, "label": "Pat Quill"}, {"id": 2, "label": "Robin Mesa"},
           {"id": 3, "label": "Ana Vela"}, {"id": 4, "label": "Ana Cruz"}]

    def test_canon(self):
        self.assertEqual(staff_names.canon("Pat Q.", TABLE), "Pat Quill")          # directory, dotted
        self.assertEqual(staff_names.canon("Robin · Houseperson AM", TABLE), "Robin Mesa")
        self.assertEqual(staff_names.canon("Ana V", {}, self.ATT), "Ana Vela")     # one HotSOS fit
        self.assertEqual(staff_names.canon("Ana", {}, self.ATT), "Ana")            # two fit: as typed
        self.assertEqual(staff_names.canon("Sam", TABLE, self.ATT), "Sam")
        # a full surname is never swapped for another person's with the same initial
        self.assertEqual(staff_names.canon("Ana Cano", {}, self.ATT), "Ana Cano")
        # an initial two people share stays as typed
        both = self.ATT + [{"id": 5, "label": "Ana Cole"}]
        self.assertEqual(staff_names.canon("Ana C.", {}, both), "Ana C.")

    def test_every_spelling_and_section_one_id(self):
        rows = [{"person": p, "home": "", "date": "2026-11-25"}
                for p in ("Pat Q.", "Pat Q", "Pat Quill", "Pat Quill · Houseperson PM")]
        out = staff_names.one_name_each(rows, TABLE)
        self.assertEqual({r["pid"] for r in out}, {"pat quill"})
        self.assertEqual({r["person"] for r in out}, {"Pat Quill"})


class RenameWeeks(unittest.TestCase):
    def test_dotted_spelling_joins_the_full_name(self):
        weeks = {"2026-11-22": {"people": {"Pat Q.": {"name": "Pat Q.", "group": "hk",
                                                      "cells": {"2026-11-25": "ON"}}}}}
        out = staff_names.rename_weeks(weeks, TABLE)
        self.assertEqual(list(out["2026-11-22"]["people"]), ["Pat Quill"])



class AmongToday(unittest.TestCase):
    """A first name spelled a little differently, among today's housekeepers
    (25 Nov: "Jennifer" on the sheet for Jenifer Santana)."""

    def test_one_fits(self):
        import staff_names as sn
        self.assertEqual(sn.resolve_among("Jennifer", ["Jenifer Ruiz", "Pat Quill"]), "Jenifer Ruiz")
        self.assertEqual(sn.resolve_among("Jennyfer", ["Jenifer Ruiz"]), "Jenifer Ruiz")
        self.assertEqual(sn.resolve_among("Jennifer R.", ["Jenifer Ruiz", "Jenifer Lake"]), "Jenifer Ruiz")

    def test_two_fit_or_none_fit_no_guess(self):
        import staff_names as sn
        self.assertEqual(sn.resolve_among("Jennifer", ["Jenifer Ruiz", "Jennyfer Lake"]), "")
        self.assertEqual(sn.resolve_among("Robin", ["Jenifer Ruiz"]), "")
        self.assertEqual(sn.resolve_among("", ["Jenifer Ruiz"]), "")

if __name__ == "__main__":
    unittest.main()
