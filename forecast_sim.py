"""
forecast_sim.py — a coming day's staffing, worked out the way the 5 AM build
will actually work it out.

`staffing.estimate` divides the SSRS minutes by a target load. Checked against
the build for 10 October it asked for 28 housekeepers and 12 RQS where the
built schedule needed 26 and 10, for three reasons:

  * SSRS counts Unallocated and Buyback Full Cleans as work. The build keeps
    them off the charts (probably clean; the RQS checks them) -- 36 rooms and
    3,190 minutes that day.
  * The SSRS minutes are not the app's. Its Full Cleans averaged 71 minutes a
    room; the charts use the 70/120/140 standards, which averaged 93.
  * Weekends put a Daily Service day just over one round on one person, and
    RQS 1 is a head every day (projects) whether or not it holds rooms.

So instead of arithmetic, this runs the Schedule page's own parsing and
packing (`daily_build.borrow`, so the two cannot drift): the day's rooms
become charts, the charts are handed to as many inspectors as it takes, and
the counts are read off the result. No Streamlit runs.
"""
import datetime as _dt
import io
import math

import daily_build

_FUNCS = None


def _funcs():
    global _FUNCS
    if _FUNCS is None:
        names = ("excel_to_room_text", "parse_rooms", "build_all_groups", "assign_inspectors",
                 "get_building", "SVC_FC", "SVC_IH", "SVC_DS", "SVC_DV")
        _FUNCS = dict(zip(names, daily_build.borrow(*names)))
    return _FUNCS


def room_text(ssrs_xlsx: bytes):
    """(room text, room count): the export as the Schedule page's room box
    takes it -- what "Load this day" puts there."""
    text, n, _ = _funcs()["excel_to_room_text"](io.BytesIO(ssrs_xlsx))
    return text, int(n)


def simulate(ssrs_xlsx: bytes, day: _dt.date) -> dict:
    """{hskp, hskp_fc, hskp_ds, rqs, rqs_fc, fc_rooms, check_rooms, check_minutes}
    for one day's Housekeeping Dashboard export."""
    return simulate_text(*room_text(ssrs_xlsx), day)


def simulate_text(room_text: str, n_rooms: int, day: _dt.date) -> dict:
    f = _funcs()
    df = f["parse_rooms"](room_text)
    if df.empty:
        return {"hskp": 0, "hskp_fc": 0, "hskp_ds": 0, "rqs": 0, "rqs_fc": 0,
                "fc_rooms": 0, "check_rooms": 0, "check_minutes": 0, "rooms": 0}
    rds = []
    for r in df.to_dict("records"):
        late = str(r.get("LateCheckout") or "").strip()
        notes = str(r.get("NotesRaw") or "").strip()
        verify = bool(r.get("verify")) or any(
            k in notes.lower() for k in ("stayover", "stay over", "p/u model", "pu model"))
        rds.append({"room": r["Room"], "service": r["Service"], "time": r["Time"],
                    "pet": r["Pet"], "guest": r["Guest"],
                    "bld": r.get("bld", f["get_building"](r["Room"])),
                    "floor": r.get("floor", 0), "num": r.get("num", 0),
                    "late_checkout": "Late Out" if late else "",
                    "status": r.get("Status", ""), "notes": notes,
                    "arriving": r.get("ArrivingGuest", ""), "res_type": r.get("ResType", ""),
                    "uncertain": bool(r.get("uncertain")), "verify": verify})
    fg = [g for g in f["build_all_groups"](rds, weekend=day.weekday() >= 5) if g["rooms"]]
    for i, g in enumerate(fg):
        g["label"] = f"G{i + 1}"
        g["housekeeper"] = f"H{i + 1}"
        g["cross_bld"] = len(g["blds"]) > 1
    live = [g for g in fg if not g.get("verify_group")]
    fc = [g for g in live if g.get("service_type") == f["SVC_FC"]]
    ih = [g for g in live if g.get("service_type") == f["SVC_IH"]]
    ds = [g for g in live if g.get("service_type") == f["SVC_DS"]]
    dv = [g for g in live if g.get("service_type") == f["SVC_DV"]]
    check = [r for g in fg if g.get("verify_group") for r in g["rooms"]]
    # Inspectors: the fewest that cover every Full Clean chart, the way the
    # page batches them. Given more than it needs, the page keeps each
    # building's leftover batch to itself; the build day only ever has so
    # many, and then those are merged -- so the need is the smallest pool
    # with no chart left to an "Inspector N" slot or put on RQS 2. RQS 2
    # taking a small leftover is how a short day copes, not what it needs:
    # ideally RQS 1 and 2 hold no Full Clean at all (the manager's words).
    fc_rooms = sum(len(g["rooms"]) for g in fc)
    rqs_fc = 0
    if fc:
        k = max(1, math.ceil(fc_rooms / 13))
        while k < 60:
            pool = [f"I{i}" for i in range(k)]
            for g in fg:
                g.pop("inspector", None)
            f["assign_inspectors"](fg, pool, 3, "RQS1", "RQS2")
            if all(g.get("inspector") in pool for g in fc):
                break
            k += 1
        rqs_fc = len({g.get("inspector") for g in fc})
    rqs2 = 1 if (ds or dv or ih) else 0
    return {
        "rooms": int(n_rooms),
        "hskp_fc": len(fc) + len(ih),
        "hskp_ds": len(ds),
        "hskp": len(fc) + len(ih) + len(ds),
        "rqs_fc": rqs_fc,
        # RQS 2 for the Daily Service / Dust n Vac round, RQS 1 always
        # (projects) -- the scheduled side counts every working RQS too.
        "rqs": rqs_fc + rqs2 + 1,
        "fc_rooms": fc_rooms,
        "check_rooms": len(check),
        "check_minutes": int(sum(float(r.get("time") or 0) for r in check)),
    }
