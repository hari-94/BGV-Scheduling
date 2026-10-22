"""
app_sync.py — after a Push, make the app's charts say what HotSOS now says.

The 5 AM build saves its charts to the app; then the team edits the sheet --
a call-off's chart goes to someone else, a room is swapped -- and pushes the
final sheet to HotSOS. Without this the phones (My Rooms) would still show
the 5 AM charts. So the pushed plan is applied to today's stored schedule:

  * a chart whose rooms all went to one other person changes housekeeper;
  * rooms that went somewhere else join a chart of that person of the same
    service, or a new chart for them -- never a chart of another service, so
    a room keeps its Full Clean / Daily Service / Dust n Vac;
  * a chart left empty is dropped;
  * minutes, buildings and floors are recounted, and the inspectors list is
    rebuilt from the charts, as the Schedule page's own _save_reassignment does.

Only rooms the push actually placed (assigned, moved or already right) count;
a room the plan skipped keeps its chart. No Streamlit here.
"""
import copy

import clock
import db
import hotsos_sync as hs
import staff_names


def from_hotsos(save=True):
    """Today's charts brought in line with who holds each room in HotSOS now.

    People change assignments in HotSOS directly -- a call-off, a swap -- and
    the app kept the people it was given, so the Schedule page, the dashboard
    and the inspectors' lists named the wrong housekeeper (9 Oct: Darling and
    Melissa swapped charts in HotSOS, Jennyfer's went to Alejandro). The
    status mirror records HotSOS's holder on each room; this turns that into
    the same plan a Push produces and applies it the same way.

    Every room HotSOS has a holder for is in the plan, the unchanged ones too:
    `apply` renames a chart only when all of its rooms went to one person, and
    a plan listing just the moved rooms would read as the whole chart moving.
    The Dust n Vac round is RQS 2's and its own rooms are left alone; a room
    of another service that got into it (see `_kind`) is in the plan, so it
    can come back out."""
    sched = db.load_full_schedule() or {}
    statuses = db.get_room_statuses() or {}
    plan = []
    for g in sched.get("groups_data") or []:
        for r in g.get("rooms") or []:
            stray = _kind(g, r) != _kind(g)
            if g.get("dv_rqs2") and not stray:
                continue
            who = str((statuses.get(str(r.get("room", ""))) or {}).get("housekeeper") or "")
            if not who:
                continue
            plan.append({"room": r.get("room"), "hotsos_name": who,
                         "action": hs.ALREADY if who == g.get("housekeeper") and not stray
                         else hs.MOVE})
    if not any(l["action"] == hs.MOVE for l in plan):
        return {"changed": False, "renamed": [], "moved": [], "inspectors": []}
    return apply(plan, save=save)


_SHORT = {"Full Clean": "FC", "Full Clean (IH)": "IH", "Daily Service": "DS", "Dust n Vac": "DV"}


def _kind(g, r=None):
    """The kind of chart a room belongs in: (service, Dust n Vac round,
    set aside). Without `r`, the chart's own kind. RQS 2's Dust n Vac round
    is built from the Dust n Vac rooms alone, so any other room in it was put
    there by a move and belongs in a chart of its own service -- 1423A and
    1524F, two Full Cleans, sat in it on 17 Oct."""
    own = (g.get("service_type"), bool(g.get("dv_rqs2")), bool(g.get("verify_group")))
    if r is not None and g.get("dv_rqs2") and r.get("service") and r.get("service") != g.get("service_type"):
        return (r.get("service"), False, False)
    return own


def _recount(g):
    rooms = g.get("rooms") or []
    g["time"] = sum(int(float(r.get("time") or 0)) for r in rooms)
    g["blds"] = sorted({r.get("bld") for r in rooms if r.get("bld") is not None})
    g["floors"] = sorted({r.get("floor") for r in rooms if r.get("floor") is not None})
    g["cross_bld"] = len(g["blds"]) > 1
    g["c140"] = sum(1 for r in rooms if int(float(r.get("time") or 0)) == 140)
    g["c120"] = sum(1 for r in rooms if int(float(r.get("time") or 0)) == 120)


def apply(plan, save=True):
    """Bring today's charts in line with a pushed plan. Returns a summary;
    with save=False nothing is written (for a look first)."""
    sched = db.load_full_schedule()
    if not sched or not sched.get("groups_data"):
        return {"changed": False, "why": "no schedule in the app today"}
    aliases = staff_names.aliases()
    target = {l["room"]: l["hotsos_name"] for l in plan
              if l.get("hotsos_name") and l["action"] in (hs.ASSIGN, hs.MOVE, hs.ALREADY)}
    rqs_for = {l["room"]: staff_names.full(l["rqs"], aliases) for l in plan if l.get("rqs")}
    fg = copy.deepcopy(sched["groups_data"])

    renamed, moved = [], []
    # 1. A chart that went whole to one other person just changes hands --
    #    judged on its own rooms, so a stray Full Clean in the Dust n Vac
    #    round can't carry the round off to that room's housekeeper.
    for g in fg:
        people = {target.get(r.get("room")) for r in g.get("rooms") or []
                  if _kind(g, r) == _kind(g)} - {None}
        if len(people) == 1:
            p = people.pop()
            if p != g.get("housekeeper"):
                renamed.append((g["label"], g.get("housekeeper", ""), p))
                g["housekeeper"] = p
    # 2. Rooms whose person differs from their chart's move to that person.
    labels = {g.get("label") for g in fg}
    for g in fg:
        keep = []
        for r in g.get("rooms") or []:
            p = target.get(r.get("room"))
            kind = _kind(g, r)
            if not p or (p == g.get("housekeeper") and kind == _kind(g)):
                keep.append(r)
                continue
            # Only into a chart of the room's own kind. Falling back to any
            # chart of theirs put 1423A and 1524F, Full Cleans of 120 and 70,
            # into the Dust n Vac round on 17 Oct when HotSOS gave them to
            # David Serrano (RQS 2, whose only chart that was), and the app
            # showed them as Dust n Vac. Nothing of that kind -> a new chart.
            dest = next((x for x in fg if x.get("housekeeper") == p and _kind(x) == kind), None)
            if dest is None:
                if kind == _kind(g):
                    dest = {k: v for k, v in g.items() if k not in ("rooms", "label")}
                    label = f"{g.get('label', 'X')}·{p.split()[0]}"
                else:                      # out of the Dust n Vac round
                    dest = {"service_type": kind[0], "c140": 0, "c120": 0}
                    label = f"{_SHORT.get(kind[0], 'X')}·{p.split()[0]}"
                while label in labels:
                    label += "'"
                labels.add(label)
                dest.update(label=label, rooms=[], housekeeper=p,
                            inspector=rqs_for.get(r.get("room")) or g.get("inspector", ""))
                fg.append(dest)
            dest.setdefault("rooms", []).append(r)
            moved.append((r.get("room"), g.get("housekeeper", ""), p))
        g["rooms"] = keep
    fg = [g for g in fg if g.get("rooms")]
    for g in fg:
        _recount(g)

    # 3. Inspectors: a chart whose rooms all name one RQS in the sheet takes it.
    reinsp = []
    for g in fg:
        names = {rqs_for.get(r.get("room")) for r in g.get("rooms") or []} - {None, ""}
        if len(names) == 1:
            n = names.pop()
            if n != g.get("inspector") and not n.lower().startswith(("rqs 2", "inspector ")):
                reinsp.append((g["label"], g.get("inspector", ""), n))
                g["inspector"] = n

    if not renamed and not moved and not reinsp:
        return {"changed": False, "renamed": [], "moved": [], "inspectors": []}
    summary = {"changed": True, "renamed": renamed, "moved": moved, "inspectors": reinsp}
    if not save:
        return summary

    # Inspectors rebuilt from the charts, as _save_reassignment does.
    roles = {i.get("name"): i.get("role") for i in sched.get("inspectors_data") or []}
    order, entries = [], {}
    for g in fg:
        name = g.get("inspector") or ""
        if not name:
            continue
        if name not in entries:
            order.append(name)
            entries[name] = {"id": len(order), "name": name, "role": roles.get(name, "FC"),
                             "groups": [], "buildings": set()}
        entries[name]["groups"].append(g["label"])
        entries[name]["buildings"] |= set(g.get("blds") or [])
    inspectors = []
    for name in order:
        e = entries[name]
        e["buildings"] = sorted(e["buildings"])
        inspectors.append(e)
    used = sorted({g.get("housekeeper") for g in fg if g.get("housekeeper")
                   and not str(g["housekeeper"]).lower().startswith("no hk")})
    db.save_full_schedule(dict(sched, groups_data=fg, inspectors_data=inspectors,
                               used_hk_set=used, updated_from_sheet_at=clock.stamp()))
    # Rooms already started on the floor carry their chart and person too.
    label_of = {r.get("room"): (g["label"], g.get("housekeeper", "")) for g in fg
                for r in g.get("rooms") or []}
    started = db.get_room_statuses() or {}
    rows = [{"room": room, "group_label": label_of[room][0], "housekeeper": label_of[room][1]}
            for room in started if room in label_of
            and (started[room].get("housekeeper"), started[room].get("group_label"))
            != (label_of[room][1], label_of[room][0])]
    if rows:
        db.bulk_upsert_room_statuses(rows)
    return summary


# ── the sheet, as the team edits it through the day ─────────────────────────
_SVC = (("daily", "Daily Service"), ("sheet", "Daily Service"), ("towel", "Daily Service"),
        ("stay", "Daily Service"), ("dust", "Dust n Vac"), ("vac", "Dust n Vac"))


def _service(raw):
    s = " ".join(str(raw or "").lower().split())
    if ("full" in s or s.startswith("fc")) and "ih" in s:
        return "Full Clean (IH)"
    for word, svc in _SVC:
        if word in s:
            return svc
    return "Full Clean"


def _rqs_name(typed, aliases):
    """The inspector a sheet's RQS cell names: the first name in it ("Grace/Dania"
    is Grace with a trainee, as the Report reads it), or '' for a placeholder."""
    first = str(typed or "").replace("+", "/").replace("&", "/").split("/")[0].strip()
    if not first or first.lower().replace(" ", "").startswith(("rqs", "inspector", "n/a", "-")):
        return ""
    return staff_names.resolve(first, aliases)


def from_sheet(rows, save=True):
    """Today's charts brought in line with what the team has typed in the day's
    tab since the push (HP, 22 Oct: "they changed the rqs in the sheet after 8,
    the app didn't update it" -- 18 rooms that day, so the RQS on the phones,
    the Live board and the Report's Timing tab were the 5 AM ones).

      * The RQS on each room. A chart whose rooms now name two RQS is split, a
        chart per RQS, same housekeeper and service, so each RQS's team view
        holds exactly their rooms.
      * Rooms added by hand: a room the app has no chart for, whose HSKP cell
        names somebody the app knows (staff_names.resolve), joins that
        person's chart of the same service and RQS (or a new one). Rooms with
        nobody, or nobody clear, named are only reported.

    Who cleans a room is HotSOS's business (from_hotsos) and is left alone
    here. `rows` are hotsos_sync.read_rows lines. Returns a summary; with
    save=False nothing is written."""
    sched = db.load_full_schedule()
    if not sched or not sched.get("groups_data"):
        return {"changed": False, "why": "no schedule in the app today"}
    aliases = staff_names.aliases()
    fg = copy.deepcopy(sched["groups_data"])
    labels = {g.get("label") for g in fg}
    sheet = {r["room"]: r for r in rows}
    charted = {r.get("room") for g in fg for r in g.get("rooms") or []}

    def new_label(base, who):
        lab = f"{base}·{who.split()[0]}" if who else f"{base}·"
        while lab in labels:
            lab += "'"
        labels.add(lab)
        return lab

    # 1. The RQS on each room.
    rqs_changed, split, out = [], [], []
    for g in fg:
        want = {}
        for r in g.get("rooms") or []:
            line = sheet.get(r.get("room"))
            name = _rqs_name(line["rqs"], aliases) if line else ""
            want[r.get("room")] = name or g.get("inspector") or ""
        names = list(dict.fromkeys(want.values()))
        if len(names) <= 1:
            n = names[0] if names else (g.get("inspector") or "")
            if n != (g.get("inspector") or ""):
                rqs_changed += [(r.get("room"), g.get("inspector") or "", n) for r in g["rooms"]]
                g["inspector"] = n
            out.append(g)
            continue
        # Split: the current RQS keeps their rooms on this chart if any are
        # left; otherwise the RQS with the most rooms keeps it.
        keep = g.get("inspector") if g.get("inspector") in names else \
            max(names, key=lambda n: sum(1 for v in want.values() if v == n))
        rooms_of = {n: [r for r in g["rooms"] if want[r.get("room")] == n] for n in names}
        for n in names:
            if n == keep:
                part = g
                part["rooms"] = rooms_of[n]
            else:
                part = {k: v for k, v in g.items() if k not in ("rooms", "label")}
                part.update(label=new_label(g.get("label", "X"), n), rooms=rooms_of[n])
                split.append((g.get("label"), part["label"], n))
            if n != (g.get("inspector") or ""):
                rqs_changed += [(r.get("room"), g.get("inspector") or "", n) for r in rooms_of[n]]
            part["inspector"] = n
            out.append(part)
    fg = out

    # 2. Rooms added on the sheet by hand.
    added, unplaced = [], []
    for room, line in sheet.items():
        if room in charted:
            continue
        hk = staff_names.resolve(line["hskp"].split("/")[0].strip(), aliases) if line["hskp"] else ""
        if not hk:
            unplaced.append(room)
            continue
        svc = _service(line["service"])
        try:
            t = int(float(line.get("time") or 0))
        except ValueError:
            t = 0
        rec = {"room": room, "service": svc, "time": t, "pet": "", "guest": line.get("guest", ""),
               "arriving": line.get("arriving", ""), "bld": int(room[0]),
               "floor": int(room[1]) if room[1].isdigit() else 0,
               "num": int("".join(c for c in room[2:] if c.isdigit()) or 0),
               "late_checkout": "", "status": "", "notes": "added on the sheet",
               "verify": False, "res_type": ""}
        rqs = _rqs_name(line["rqs"], aliases)
        dest = next((g for g in fg if g.get("housekeeper") == hk and g.get("service_type") == svc
                     and not g.get("verify_group") and not g.get("dv_rqs2")
                     and (g.get("inspector") or "") == rqs), None)
        if dest is None:
            short = {"Daily Service": "DS", "Dust n Vac": "DV", "Full Clean (IH)": "IH"}.get(svc, "FC")
            dest = {"service_type": svc, "housekeeper": hk, "inspector": rqs, "rooms": [],
                    "label": new_label(short + "+", hk), "c140": 0, "c120": 0}
            fg.append(dest)
        dest["rooms"].append(rec)
        added.append((room, hk, svc))
    for g in fg:
        _recount(g)

    summary = {"changed": bool(rqs_changed or added), "rqs": rqs_changed, "split": split,
               "added": added, "unplaced": unplaced}
    if not summary["changed"] or not save:
        return summary
    roles = {i.get("name"): i.get("role") for i in sched.get("inspectors_data") or []}
    order, entries = [], {}
    for g in fg:
        name = g.get("inspector") or ""
        if not name:
            continue
        if name not in entries:
            order.append(name)
            entries[name] = {"id": len(order), "name": name, "role": roles.get(name, "FC"),
                             "groups": [], "buildings": set()}
        entries[name]["groups"].append(g["label"])
        entries[name]["buildings"] |= set(g.get("blds") or [])
    inspectors = []
    for name in order:
        e = entries[name]
        e["buildings"] = sorted(e["buildings"])
        inspectors.append(e)
    used = sorted({g.get("housekeeper") for g in fg if g.get("housekeeper")
                   and not str(g["housekeeper"]).lower().startswith(("no hk", "need"))})
    db.save_full_schedule(dict(sched, groups_data=fg, inspectors_data=inspectors,
                               used_hk_set=used, updated_from_sheet_at=clock.stamp()))
    # The mirror copies a chart's inspector onto its rooms on its next pass;
    # done here as well so the Timing tab and the phones don't wait for it.
    insp_of = {r.get("room"): (g["label"], g.get("inspector") or "") for g in fg
               for r in g.get("rooms") or []}
    now = db.get_room_statuses() or {}
    rows_out = [{"room": room, "group_label": insp_of[room][0], "inspector": insp_of[room][1]}
                for room in now if room in insp_of
                and ((now[room].get("inspector") or ""), now[room].get("group_label"))
                != (insp_of[room][1], insp_of[room][0])]
    if rows_out:
        db.bulk_upsert_room_statuses(rows_out)
    return summary
