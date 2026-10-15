"""
weekend_duties.py — the Carpet and Stripping columns of the day's sheet: who
shampoos the carpets of the pet rooms, and who strips the linen ahead of the
housekeepers.

Both come from the staff schedule, the way the team writes them on weekends:

  * Carpets: a houseperson (or RQS) on "CARPETS/BLD 3" -- earlier "Rollaways
    8-9am and then, Cleaning carpets BLD 3" -- does that building's pet rooms.
    Only the rooms with an X under Pet get a name (HP, 15 Oct), and only the
    Full Cleans: carpets are done when the guest has gone. Saturdays are
    usually one person on BLD 1 and one on BLD 2; Sundays two on BLD 3, who
    split it by area, the 30xx rooms to one and the floors above to the other
    -- as on Aug 16, Sep 6, Sep 13, Oct 4 and Oct 11.
  * Stripping: whoever has "Stripping linen" goes in first on the Full Clean
    rooms, takes the sheets and pillow covers off and the trash out, so the
    housekeeper starts on a stripped room. The team strips the buildings
    where the check-outs are: on eight weekends from Aug 15 to Oct 11 every
    building with 25 Full Cleans or more was stripped and none with fewer --
    buildings 1 and 2 on Saturdays (40-67 each; building 3 had 6-16), and
    building 3 on Sundays (80-95; the others 3-23). Two people on two
    buildings take one each; two on one building split it; one person takes
    the lot (Gerardo, 97 rooms of building 3, Oct 4).

A room left for the RQS to check (no housekeeper on it) gets neither. Days
without such cells -- weekdays, as the schedule is written now -- are left
as they are. No Streamlit here: the 5 AM build and the Schedule page's
download both call `fill`.
"""
import re

STRIP_MIN_ROOMS = 25          # a building with fewer Full Cleans isn't stripped

_CARPET = re.compile(r"carpet|alfombra", re.I)
_BLD = re.compile(r"\b(?:bldg?|bl|building|edificio)\s*[-./#:]?\s*([123])\b", re.I)
_STRIP = re.compile(r"strip", re.I)


def duties(people) -> dict:
    """{"carpets": {building: [names]}, "stripping": [names]} from the day's
    schedule cells. `people` is [{"name", "raw", "kind"...}] as
    roster_import.week_to_people gives them; only a cell naming a building
    counts for carpets ("Cleaning carpets hallways" is no building's)."""
    carpets, strip = {}, []
    for p in people:
        raw = str(p.get("raw") or "")
        name = str(p.get("name") or "").split(" · ")[0].strip()
        if not raw or not name:
            continue
        if _CARPET.search(raw):
            m = _BLD.search(raw)
            if m:
                carpets.setdefault(int(m.group(1)), []).append(name)
        if _STRIP.search(raw):
            strip.append(name)
    return {"carpets": carpets, "stripping": strip}


def for_day(iso) -> dict:
    """The day's duties from the stored staff schedule (in-app edits included)."""
    import db
    import roster_import as ri
    wk = ri.find_week_key(db.staff_week_keys(), iso)
    week = db.load_staff_week(wk) if wk else None
    if not week:
        return {"carpets": {}, "stripping": []}
    eff, _ = ri.apply_overrides(week, db.load_staff_overrides() or {}, wk)
    return duties(ri.week_to_people(eff, iso))


def _full_clean(service) -> bool:
    s = " ".join(str(service or "").lower().split())
    return ("full" in s or "deep" in s or s.startswith(("check out", "early out", "e/o"))) \
        and "dust" not in s


def _chunks(items, k):
    """`items` in k runs of near-equal length, in order."""
    out, start = [], 0
    for i in range(k):
        n = len(items) // k + (1 if i < len(items) % k else 0)
        out.append(items[start:start + n])
        start += n
    return out


def plan(rows, duty) -> tuple:
    """({room: carpet name}, {room: stripping name}) for `rows`, a list of
    {"Room", "Service", "Pet", "HSKP"} dicts."""
    work = [r for r in rows
            if _full_clean(r.get("Service")) and str(r.get("HSKP") or "").strip()
            and re.match(r"^\d{4}[A-I]$", str(r.get("Room") or "").strip().upper())]
    by_bld = {}
    for r in work:
        by_bld.setdefault(int(str(r["Room"]).strip()[0]), []).append(str(r["Room"]).strip().upper())
    for b in by_bld:
        by_bld[b].sort()                  # floor by floor, the corridor in order

    with_pet = {str(r["Room"]).strip().upper() for r in work
                if str(r.get("Pet") or "").strip().upper() == "X"}
    carpet = {}
    for b, names in (duty.get("carpets") or {}).items():
        pets = [r for r in by_bld.get(b, []) if r in with_pet]
        for name, part in zip(names, _chunks(pets, len(names))):
            for room in part:
                carpet[room] = name

    strip = {}
    people = list(dict.fromkeys(duty.get("stripping") or []))
    if people and by_bld:
        blds = sorted((b for b, r in by_bld.items() if len(r) >= STRIP_MIN_ROOMS),
                      key=lambda b: -len(by_bld[b]))
        if not blds:
            blds = [max(by_bld, key=lambda b: len(by_bld[b]))]
        if len(people) >= len(blds):
            # One building each, the busiest first; anyone left over goes to
            # whichever building then has the most rooms per person.
            crew = {b: [p] for b, p in zip(blds, people)}
            for p in people[len(blds):]:
                b = max(blds, key=lambda b: len(by_bld[b]) / len(crew[b]))
                crew[b].append(p)
            for b, names in crew.items():
                for name, part in zip(names, _chunks(by_bld[b], len(names))):
                    for room in part:
                        strip[room] = name
        else:
            # Fewer people than buildings: the buildings shared out in turn.
            for i, b in enumerate(blds):
                for room in by_bld[b]:
                    strip[room] = people[i % len(people)]
    return carpet, strip


def fill(frame, iso, duty=None):
    """The sheet's frame with its Carpet and Stripping columns filled for
    `iso` (an ISO date). Cells somebody already filled are kept."""
    duty = duty if duty is not None else for_day(iso)
    if not (duty.get("carpets") or duty.get("stripping")) or frame is None or frame.empty:
        return frame
    for col in ("Carpet", "Stripping"):
        if col not in frame.columns:
            frame[col] = ""
    carpet, strip = plan(frame.to_dict("records"), duty)
    rooms = frame["Room"].fillna("").astype(str).str.strip().str.upper()
    for col, who in (("Carpet", carpet), ("Stripping", strip)):
        cur = frame[col].fillna("").astype(str).str.strip()
        frame[col] = [c if c and c.lower() != "nan" else who.get(r, "")
                      for c, r in zip(cur, rooms)]
    return frame
