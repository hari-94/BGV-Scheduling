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
