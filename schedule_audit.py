"""
schedule_audit.py — the rules a day's charts must keep, checked in one place.

Every rule here was broken at least once without anybody noticing until HP
read the evening card: Full Clean charts crossing buildings to save one
person (7 Nov), a Daily Service round in buildings 2 and 3 (7 Nov), a Daily
Service housekeeper's side chart filled as if it were her whole day -- 705
minutes (8 Nov). The packer has its own guards; this is the second pair of
eyes, run on every build (5 AM, the page's Generate, the 9 PM preview, the
forecast), so a break shows up the day it appears, not when someone spots it.

`check(groups, ...)` returns a list of findings, each
    {"kind": RULE | STAFF | NOTE, "code": str, "msg": str}
  RULE   a hard rule the plan breaks -- the code is wrong, or a hand edit is
  STAFF  not enough people on the staff schedule -- not the plan's fault
  NOTE   worth knowing, not wrong (crossings the day needs, short charts)

The limits mirror cleaning_scheduler's; tests/test_schedule_audit.py fails if
they drift apart. No Streamlit here.
"""
import collections

import fcpack
import property_map as pmap

MAX_FC = 380            # a Full Clean day
LOW_MIN = 330           # under this, a Full Clean chart is short
DS_CAP = 460            # a Daily Service day, weekdays
DS_CAP_WEEKEND = 510    # ... Saturday and Sunday
INSP_ROOM_MAX = 13      # Full Clean rooms one RQS can inspect

RULE, STAFF, NOTE = "rule", "staff", "note"

FC, IH, DS, DV = "Full Clean", "Full Clean (IH)", "Daily Service", "Dust n Vac"
_UNSTAFFED = ("need housekeeper", "no hk available", "no hk")


def _where(r):
    return pmap.parse(str(r.get("room", "")).strip().upper())


def _bld(r):
    loc = _where(r)
    if loc:
        return loc.bld
    s = str(r.get("room", "")).strip()[:1]
    return int(s) if s.isdigit() else None


def _mins(g):
    return sum(int(r.get("time") or 0) for r in g.get("rooms") or [])


def _unstaffed(name):
    return not name or str(name).strip().lower().startswith(_UNSTAFFED)


def _placeholder_rqs(name):
    return not name or str(name).startswith("Inspector ")


def is_weekend(day):
    try:
        return day is not None and day.weekday() >= 5
    except AttributeError:
        return False


def check(groups, day=None, rooms_in=None, present=None, rqs2=None):
    """Findings for one day's charts.

    groups    the charts, as the Schedule page makes them
    day       a date; picks the weekday or weekend Daily Service cap
    rooms_in  every room code the day started with, to prove none was lost
              or doubled (skip the check when None)
    present   names working that day, to catch a chart held by someone off
    rqs2      RQS 2's name, who must inspect every in-house chart
    """
    out = []

    def add(kind, code, msg):
        out.append({"kind": kind, "code": code, "msg": msg})

    ds_cap = DS_CAP_WEEKEND if is_weekend(day) else DS_CAP
    live = [g for g in groups if g.get("rooms")]
    work = [g for g in live if not g.get("verify_group")]

    # -- every room once -------------------------------------------------
    seen = collections.Counter(str(r.get("room", "")).strip().upper()
                               for g in live for r in g["rooms"])
    dup = sorted(k for k, n in seen.items() if n > 1)
    if dup:
        add(RULE, "room_twice", f"rooms on two charts: {', '.join(dup)}")
    if rooms_in is not None:
        want = {str(x).strip().upper() for x in rooms_in if str(x).strip()}
        lost = sorted(want - set(seen))
        extra = sorted(set(seen) - want)
        if lost:
            add(RULE, "room_lost", f"rooms on no chart: {', '.join(lost)}")
        if extra:
            add(RULE, "room_unknown", f"rooms not in the day's list: {', '.join(extra)}")

    labels = collections.Counter(g.get("label") for g in live if g.get("label"))
    same = sorted(l for l, n in labels.items() if n > 1)
    if same:
        add(RULE, "label_twice", f"two charts share a label: {', '.join(same)}")

    for g in live:
        if g.get("verify_group") and (not _unstaffed(g.get("housekeeper"))
                                      or not _placeholder_rqs(g.get("inspector")) and g.get("inspector")):
            add(RULE, "check_assigned", f"{g.get('label')} is held back to check but has a person on it")

    # -- each Full Clean chart --------------------------------------------
    fc = [g for g in work if g.get("service_type") == FC]
    fc_ih = [g for g in work if g.get("service_type") in (FC, IH)]
    names = {"over_cap": "over 380 minutes", "bad_mix": "two 140s, or a 140 with two 120s",
             "split_bundles": "a guest's apartment split", "b2_b3": "buildings 2 and 3 together",
             "easy": "120+70+70+70 of separate apartments"}
    for g in fc_ih:
        a = fcpack.audit([g["rooms"]], MAX_FC, _where, LOW_MIN)
        for k, what in names.items():
            if a.get(k) and k != "split_bundles":
                add(RULE, f"fc_{k}", f"{g.get('label')} ({g.get('housekeeper') or 'nobody'}): {what}")

    # an apartment is one person's, across charts too
    owner = collections.defaultdict(set)
    size = collections.Counter()
    for g in fc_ih:
        for r in g["rooms"]:
            k = fcpack._unit_key(r)
            if k:
                owner[k].add(g.get("label"))
                size[k] += int(r.get("time") or 0)
    for k, ls in owner.items():
        if len(ls) > 1:
            where = ", ".join(sorted(map(str, ls)))
            if size[k] > MAX_FC:     # bigger than a day: split on purpose (fcpack.bundles)
                add(NOTE, "apartment_too_big", f"apartment {k} ({size[k]} min) is split across {where}")
            else:
                add(RULE, "apartment_split", f"apartment {k} is split across {where}")

    # -- each Daily Service round -----------------------------------------
    ds = [g for g in work if g.get("service_type") == DS]
    for g in ds:
        if _mins(g) > ds_cap:
            add(RULE, "ds_over_cap", f"{g.get('label')} ({g.get('housekeeper') or 'nobody'}): "
                                     f"{_mins(g)} min, over the {ds_cap} cap")
        b = {_bld(r) for r in g["rooms"]}
        if 2 in b and 3 in b:
            if len(ds) > 1:
                add(RULE, "ds_b2_b3", f"{g.get('label')} ({g.get('housekeeper') or 'nobody'}): "
                                      "a Daily Service round in buildings 2 and 3")
            else:
                add(NOTE, "ds_one_round", f"{g.get('label')}: the day's only Daily Service round "
                                          "covers every building")

    # -- each person's whole day ------------------------------------------
    day_of = collections.defaultdict(list)
    for g in work:
        p = g.get("housekeeper")
        if _unstaffed(p) or g.get("dv_rqs2") or g.get("service_type") == DV:
            continue
        day_of[p].append(g)
    for p, gs in day_of.items():
        total = sum(_mins(g) for g in gs)
        cap = ds_cap if any(g.get("service_type") == DS for g in gs) else MAX_FC
        if total > cap:
            add(RULE, "person_over_cap", f"{p}: {total} min over {cap} "
                                         f"({', '.join(str(g.get('label')) for g in gs)})")
        b = {_bld(r) for g in gs if g.get("service_type") in (FC, IH) for r in g["rooms"]}
        if 2 in b and 3 in b:
            add(RULE, "person_b2_b3", f"{p}: Full Clean in buildings 2 and 3 "
                                      f"({', '.join(str(g.get('label')) for g in gs)})")
        if present is not None and p not in present:
            add(RULE, "person_off", f"{p} holds {', '.join(str(g.get('label')) for g in gs)} "
                                    "but is not working that day")

    # -- RQS rounds ---------------------------------------------------------
    rq = collections.defaultdict(list)
    for g in fc:
        rq[g.get("inspector") or ""].append(g)
    for q, gs in rq.items():
        if _placeholder_rqs(q):
            add(STAFF, "rqs_missing", f"{len(gs)} Full Clean chart(s) with no RQS "
                                      f"({', '.join(str(g.get('label')) for g in gs)})")
            continue
        n = sum(len(g["rooms"]) for g in gs)
        if n > INSP_ROOM_MAX:
            add(RULE, "rqs_over_cap", f"RQS {q}: {n} Full Clean rooms, over {INSP_ROOM_MAX}")
        b = {_bld(r) for g in gs for r in g["rooms"]}
        if 2 in b and 3 in b:
            add(RULE, "rqs_b2_b3", f"RQS {q}: Full Clean in buildings 2 and 3")
    if rqs2:
        for g in work:
            if g.get("service_type") == IH and g.get("inspector") not in (rqs2, "RQS 2"):
                add(RULE, "ih_not_rqs2", f"{g.get('label')}: in-house chart inspected by "
                                         f"{g.get('inspector') or 'nobody'}, not RQS 2 ({rqs2})")

    # -- staffing, and things worth knowing -------------------------------
    open_ = [g for g in work if _unstaffed(g.get("housekeeper"))
             and not g.get("dv_rqs2") and g.get("service_type") != DV]
    if open_:
        add(STAFF, "unstaffed", f"{len(open_)} chart(s) with nobody on them "
                                f"({', '.join(str(g.get('label')) for g in open_)}, "
                                f"{sum(_mins(g) for g in open_)} min)")
    cross = [g.get("label") for g in fc if len({_bld(r) for r in g["rooms"]}) > 1]
    if cross:
        add(NOTE, "fc_cross", f"{len(cross)} of {len(fc)} Full Clean charts cross buildings "
                              f"({', '.join(map(str, cross))})")
    short = [g.get("label") for g in fc if _mins(g) < LOW_MIN and not _unstaffed(g.get("housekeeper"))]
    if short:
        add(NOTE, "fc_short", f"{len(short)} staffed Full Clean chart(s) under {LOW_MIN} min "
                              f"({', '.join(map(str, short))})")
    return out


def rules(findings):
    return [f for f in findings if f["kind"] == RULE]


def summary(findings):
    """One line: 'rules kept', or how many broken, plus staffing gaps."""
    r = len(rules(findings))
    s = sum(1 for f in findings if f["kind"] == STAFF)
    head = "all rules kept" if not r else f"{r} rule break(s)"
    return head + (f"; {s} staffing gap(s)" if s else "")
