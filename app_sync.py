"""
app_sync.py — after a Push, make the app's charts say what HotSOS now says.

The 5 AM build saves its charts to the app; then the team edits the sheet --
a call-off's chart goes to someone else, a room is swapped -- and pushes the
final sheet to HotSOS. Without this the phones (My Rooms) would still show
the 5 AM charts. So the pushed plan is applied to today's stored schedule:

  * a chart whose rooms all went to one other person changes housekeeper;
  * rooms that went somewhere else join a chart of that person (same service
    first), or a new chart for them;
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


def _recount(g):
    rooms = g.get("rooms") or []
    g["time"] = sum(int(float(r.get("time") or 0)) for r in rooms)
    g["blds"] = sorted({r.get("bld") for r in rooms if r.get("bld") is not None})
    g["floors"] = sorted({r.get("floor") for r in rooms if r.get("floor") is not None})
    g["cross_bld"] = len(g["blds"]) > 1


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
    # 1. A chart that went whole to one other person just changes hands.
    for g in fg:
        people = {target.get(r.get("room")) for r in g.get("rooms") or []} - {None}
        if len(people) == 1:
            p = people.pop()
            if p != g.get("housekeeper"):
                renamed.append((g["label"], g.get("housekeeper", ""), p))
                g["housekeeper"] = p
    # 2. Rooms whose person differs from their chart's move to that person.
    for g in fg:
        keep = []
        for r in g.get("rooms") or []:
            p = target.get(r.get("room"))
            if not p or p == g.get("housekeeper"):
                keep.append(r)
                continue
            dest = next((x for x in fg if x.get("housekeeper") == p
                         and x.get("service_type") == g.get("service_type")), None) \
                or next((x for x in fg if x.get("housekeeper") == p), None)
            if dest is None:
                dest = {k: v for k, v in g.items() if k not in ("rooms", "label")}
                dest.update(label=f"{g.get('label', 'X')}·{p.split()[0]}", rooms=[],
                            housekeeper=p,
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
