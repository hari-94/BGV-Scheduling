"""
The scheduling rules, pinned down.

Run:  .venv\\Scripts\\python -m unittest discover -s tests -v

Every test here is a rule that was broken without anyone noticing until HP
read the evening card -- 7 Nov (12 of 24 Full Clean charts crossing buildings
to save one person; a Daily Service round in buildings 2 and 3) and 8 Nov (a
Daily Service housekeeper's side chart filled to a whole Full Clean day: 705
minutes) -- plus the checker that now watches for them (schedule_audit).

The packing tests run the Schedule page's own functions (daily_build.borrow /
forecast_sim.pack_day), on the real room lists of 7 and 8 Nov with the guests'
names replaced. No database, no Streamlit page. The two solver tests take
about a minute between them.
"""
import datetime as dt
import re
import unittest
from pathlib import Path

import fcpack
import fcsolve
import forecast_sim
import property_map as pmap
import schedule_audit as sa
from daily_build import borrow

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIX = HERE / "fixtures"


def _where(r):
    return pmap.parse(str(r.get("room", "")).strip().upper())


def _bld(r):
    return _where(r).bld


def _mins(rooms):
    return sum(int(r.get("time") or 0) for r in rooms)


def room(code, time=70, svc="Full Clean", guest=None):
    return {"room": code, "time": time, "service": svc,
            "guest": guest or f"Guest {code}, Test", "bld": int(code[0])}


def chart(label, rooms, svc="Full Clean", hk="", insp="", **kw):
    g = {"label": label, "rooms": rooms, "service_type": svc, "housekeeper": hk,
         "inspector": insp, "time": _mins(rooms), "blds": {int(r["room"][0]) for r in rooms}}
    g.update(kw)
    return g


# ── the checker itself ───────────────────────────────────────────────────────
class AuditLimits(unittest.TestCase):
    def test_limits_match_the_page(self):
        """schedule_audit's numbers are the page's numbers."""
        src = (ROOT / "cleaning_scheduler.py").read_text(encoding="utf-8")

        def val(name):
            m = re.search(rf"^\s*{name}\s*=\s*(\d+)", src, re.M)
            self.assertIsNotNone(m, f"{name} not found in cleaning_scheduler.py")
            return int(m.group(1))
        for name in ("MAX_FC", "LOW_MIN", "DS_CAP", "DS_CAP_WEEKEND", "INSP_ROOM_MAX"):
            self.assertEqual(getattr(sa, name), val(name), name)


class AuditFindsBreaks(unittest.TestCase):
    sat = dt.date(2026, 11, 7)
    fri = dt.date(2026, 11, 6)

    def codes(self, groups, **kw):
        return {f["code"] for f in sa.rules(sa.check(groups, **kw))}

    def test_clean_day_has_no_rules_broken(self):
        g = [chart("FC-A", [room("1010A", 140), room("1010C", 120), room("1010D", 70)],
                   hk="A", insp="R1"),
             chart("DS-A", [room("2136E", 40, "Daily Service")], svc="Daily Service", hk="B")]
        self.assertEqual(self.codes(g, day=self.fri), set())

    def test_ds_round_in_2_and_3(self):
        g = [chart("DS-A", [room("2136E", 40, "Daily Service"), room("3010C", 20, "Daily Service")],
                   svc="Daily Service", hk="A"),
             chart("DS-B", [room("1221A", 35, "Daily Service")], svc="Daily Service", hk="B")]
        self.assertIn("ds_b2_b3", self.codes(g, day=self.fri))

    def test_the_only_ds_round_may_cover_everything(self):
        g = [chart("DS-A", [room("2136E", 40, "Daily Service"), room("3010C", 20, "Daily Service")],
                   svc="Daily Service", hk="A")]
        self.assertNotIn("ds_b2_b3", self.codes(g, day=self.fri))

    def test_person_over_cap_ds_plus_side_chart(self):
        """8 Nov: 325 of Daily Service and a 380-minute Full Clean side chart."""
        ds = [room(c, 25, "Daily Service") for c in ("1221A", "1221B", "1224H", "1226B", "1320H",
                                                    "1320I", "1323C", "1421C", "1421B", "1423B",
                                                    "1020B", "1224E", "1222F")]
        g = [chart("DS-A", ds, svc="Daily Service", hk="Darling"),
             chart("FC-T", [room("2236H", 70), room("2232H", 70), room("2233A", 120), room("2135A", 120)],
                   hk="Darling", insp="R1")]
        self.assertIn("person_over_cap", self.codes(g, day=self.dt8))

    dt8 = dt.date(2026, 11, 8)

    def test_fc_chart_rules(self):
        g = [chart("FC-A", [room("2433B", 140), room("3149E", 140)], hk="A", insp="R")]
        c = self.codes(g, day=self.fri)
        self.assertIn("fc_b2_b3", c)
        self.assertIn("fc_bad_mix", c)

    def test_person_fc_in_2_and_3(self):
        g = [chart("FC-A", [room("2433B")], hk="A", insp="R"),
             chart("FC-B", [room("3149E")], hk="A", insp="R")]
        self.assertIn("person_b2_b3", self.codes(g, day=self.fri))

    def test_rqs_rounds(self):
        g = [chart(f"FC-{i}", [room(f"1{i:03d}A")] * 1, hk=f"H{i}", insp="R") for i in range(14)]
        g += [chart("FC-X", [room("2433B")], hk="X", insp="Q"),
              chart("FC-Y", [room("3149E")], hk="Y", insp="Q")]
        c = self.codes(g, day=self.fri)
        self.assertIn("rqs_over_cap", c)
        self.assertIn("rqs_b2_b3", c)

    def test_apartment_split(self):
        a = [room("2433B", 70, guest="Same, Guest"), room("2433C", 70, guest="Same, Guest")]
        g = [chart("FC-A", [a[0]], hk="A", insp="R"), chart("FC-B", [a[1]], hk="B", insp="R")]
        self.assertIn("apartment_split", self.codes(g, day=self.fri))

    def test_rooms_lost_doubled_and_held_back_with_a_person(self):
        g = [chart("FC-A", [room("1010A"), room("1010C")], hk="A", insp="R"),
             chart("FC-B", [room("1010A")], hk="B", insp="R"),
             chart("CHECK-A", [room("1010D")], hk="C", verify_group=True)]
        c = self.codes(g, day=self.fri, rooms_in=["1010A", "1010C", "1010D", "1012A"])
        self.assertIn("room_twice", c)
        self.assertIn("room_lost", c)
        self.assertIn("check_assigned", c)

    def test_person_off_today(self):
        g = [chart("FC-A", [room("1010A")], hk="Gone", insp="R")]
        self.assertIn("person_off", self.codes(g, day=self.fri, present={"Here"}))

    def test_staffing_is_not_a_rule(self):
        g = [chart("FC-A", [room("1010A")], hk="No HK available 1", insp="Inspector 3")]
        f = sa.check(g, day=self.fri)
        self.assertEqual(sa.rules(f), [])
        self.assertEqual({x["code"] for x in f if x["kind"] == sa.STAFF}, {"unstaffed", "rqs_missing"})


# ── the packer, on real days ─────────────────────────────────────────────────
def _day(iso):
    return (FIX / f"rooms_{iso}.tsv").read_text(encoding="utf-8"), dt.date.fromisoformat(iso)


class PackedDays(unittest.TestCase):
    """The page's packing (build_all_groups), checked by schedule_audit."""

    @classmethod
    def setUpClass(cls):
        cls.days = {iso: forecast_sim.pack_day(*_day(iso)) for iso in ("2026-11-07", "2026-11-08")}

    def test_no_rule_broken(self):
        for iso, fg in self.days.items():
            with self.subTest(day=iso):
                self.assertEqual([f["msg"] for f in sa.rules(sa.check(fg, day=dt.date.fromisoformat(iso)))], [])

    def test_7nov_full_clean_crossings_are_only_the_leftovers(self):
        """12 of 24 crossed before the solver's crossing step; the day needs 2."""
        fc = [g for g in self.days["2026-11-07"] if g["service_type"] == "Full Clean"
              and not g.get("verify_group")]
        cross = [g for g in fc if len({_bld(r) for r in g["rooms"]}) > 1]
        self.assertLessEqual(len(cross), 2, [g["label"] for g in cross])

    def test_7nov_daily_service_keeps_buildings_apart(self):
        """Santos 510 (3 + part of 1) and Ana 415 (2 + 3) before; now one round
        is building 3 alone and the other 1 + 2."""
        ds = [g for g in self.days["2026-11-07"] if g["service_type"] == "Daily Service"]
        self.assertEqual(len(ds), 2)
        blds = sorted(tuple(sorted({_bld(r) for r in g["rooms"]})) for g in ds)
        self.assertEqual(blds, [(1, 2), (3,)])
        for g in ds:
            self.assertLessEqual(_mins(g["rooms"]), sa.DS_CAP_WEEKEND)


class Solver(unittest.TestCase):
    def test_merged_buildings_cross_only_where_it_saves_someone(self):
        """fcsolve's step 3: buildings 1 and 2 handed over together pack to the
        same count with almost every chart inside one building."""
        text, day = _day("2026-11-07")
        fg = forecast_sim.pack_day(text, day)
        rooms = [r for g in fg if g["service_type"] == "Full Clean" and not g.get("verify_group")
                 for r in g["rooms"] if _bld(r) in (1, 2)]
        hint = fcpack.pack(rooms, sa.MAX_FC, _where, sa.LOW_MIN)
        got = fcsolve.pack(rooms, sa.MAX_FC, _where, sa.LOW_MIN, hint=hint)
        self.assertLessEqual(len(got), len(hint))
        cross = [c for c in got if len({_bld(r) for r in c}) > 1]
        self.assertLessEqual(len(cross), 2)


# ── the staffing passes (page functions, run on their own) ──────────────────
class Staffing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # In a dict: as class attributes, plain functions become methods.
        cls.f = dict(zip(("fill", "leftover_to", "overflow", "move", "mk"), borrow(
            "fill_from_unstaffed", "leftover_to", "overflow_to_rqs12", "move_inspections", "mk")))

    def test_side_chart_is_not_filled_past_the_person(self):
        """8 Nov: Darling's 325-minute round plus a Full Clean side chart was
        filled to 380 as if the chart were her day -- 705 minutes."""
        fg = forecast_sim.pack_day(*_day("2026-11-08"))
        ds = next(g for g in fg if g["service_type"] == "Daily Service")
        fcs = [g for g in fg if g["service_type"] == "Full Clean" and not g.get("verify_group")]
        side_rooms = fcs[0]["rooms"][:1]
        rest = fcs[0]["rooms"][1:] + [r for g in fcs[1:3] for r in g["rooms"]]
        groups = [dict(ds, housekeeper="Darling", label="DS-A"),
                  dict(self.f["mk"](side_rooms, "Full Clean"), housekeeper="Darling", label="FC-A·Darling"),
                  dict(self.f["mk"](rest, "Full Clean"), housekeeper="No HK available 1", label="FC-B")]
        out = self.f["fill"](groups, {"Darling": {"building": 1}})
        day = sum(g["time"] for g in out if g.get("housekeeper") == "Darling")
        self.assertLessEqual(day, sa.DS_CAP_WEEKEND)

    def test_leftover_to_keeps_caps_and_buildings(self):
        open_ds = chart("DS-X", [room("1221A", 20, "Daily Service")], svc="Daily Service",
                        hk="No HK available 1")
        open_fc3 = chart("FC-X", [room("3149E", 70)], hk="No HK available 2")
        open_fc1 = chart("FC-Y", [room("1010A", 70)], hk="No HK available 3")
        g = [chart("DS-A", [room("1221B", 500, "Daily Service")], svc="Daily Service", hk="Dee"),
             chart("FC-A", [room("2433B", 200)], hk="Bee"),
             open_ds, open_fc3, open_fc1]
        _, given = self.f["leftover_to"](g, ["Dee", "Bee"])
        got = {n: rooms for n, rooms in given}
        self.assertNotIn("1221A", got.get("Dee", []))        # 520 > any Daily Service cap
        self.assertNotIn("3149E", got.get("Bee", []))        # building 2 person, building 3 room
        self.assertIn("1010A", got.get("Bee", []))           # 270 < 380, building 1: fine

    def test_overflow_avoids_2_and_3(self):
        g = [chart("FC-A", [room("2433B")] * 2, hk="A", insp="R1"),
             chart("FC-B", [room("3149E")] * 8, hk="B", insp="R2"),
             chart("FC-C", [room("3149F")] * 3, hk="C", insp="Inspector 3")]
        ins = [{"name": "Inspector 3", "role": "FC", "groups": ["FC-C"]}]
        g, _ = self.f["overflow"](g, ins, "R1", "R2")
        self.assertEqual(next(x for x in g if x["label"] == "FC-C")["inspector"], "R2")

    def test_move_inspections_skips_2_and_3(self):
        g = [chart("FC-A", [room("3149E")], hk="A", insp="From"),
             chart("FC-B", [room("2433B")], hk="B", insp="To")]
        g, _, done = self.f["move"](g, [{"name": "From", "role": "FC", "groups": ["FC-A"]},
                                   {"name": "To", "role": "FC", "groups": ["FC-B"]}],
                               [{"from": "From", "to": "To"}])
        self.assertEqual(next(x for x in g if x["label"] == "FC-A")["inspector"], "From")


class SheetAndHotSOS(unittest.TestCase):
    def test_held_back_room_given_to_someone_is_an_ordinary_room(self):
        """'CHECK-A·Lilliam': a held-back room HotSOS gave somebody kept the
        held-back flag -- no RQS, out of the counts."""
        import app_sync
        kind = app_sync._kind({"service_type": "Full Clean", "verify_group": True},
                              {"room": "1010A", "service": "Full Clean"})
        self.assertEqual(kind, ("Full Clean", False, False))


if __name__ == "__main__":
    unittest.main()
