"""
blocked_rooms.py — rooms taken out of service (a deep clean, a refit) that
nobody cleans or inspects while they are out.

Kept in app_settings under KEY as a list of blocks:

    {"blocks": [{"bld": 1, "levels": ["Plaza", "3"], "rooms": [],
                 "from": "2026-10-17", "to": null,
                 "why": "deep clean", "set_by": ..., "set_at": ...}]}

A block names whole floors (a building and its levels, the way property_map
reads a room code -- "Plaza" is not the same as the 0 digit) and/or single
rooms, from a date and, if it is known, to one. Generate drops a blocked room
before anything is planned, so it gets no housekeeper, no inspector, no
carpet and no stripping, and the push never sends it to HotSOS.

One guard: a blocked room with a guest arriving that day is kept on the plan
and said so -- a room somebody is checking into is never left unprepared on
the strength of a block that may have been meant to end.

No Streamlit here.
"""
import db
import property_map as pmap

KEY = "blocked_rooms"


def blocks(day_iso) -> list:
    """The blocks in force on `day_iso`."""
    rec = db._load_key(KEY) or {}
    out = []
    for b in rec.get("blocks") or []:
        if str(b.get("from") or "") <= day_iso and (not b.get("to") or day_iso <= str(b["to"])):
            out.append(b)
    return out


def why_blocked(room, active) -> str:
    """The block's reason if `room` falls under one of `active`, else ''."""
    code = str(room or "").strip().upper()
    for b in active:
        if code in {str(r).strip().upper() for r in b.get("rooms") or []}:
            return b.get("why") or "blocked"
        loc = pmap.parse(code)
        if loc and loc.bld == b.get("bld") and loc.level in (b.get("levels") or []):
            return b.get("why") or "blocked"
    return ""


def drop(df, day_iso, arriving=lambda r: False):
    """(df without the blocked rooms, [(room, why)] dropped, [(room, why)] kept
    because a guest arrives). `df` is parse_rooms' frame (a "Room" column);
    `arriving(row)` says whether a guest checks in to that room today."""
    active = blocks(day_iso)
    if not active or df is None or df.empty or "Room" not in df.columns:
        return df, [], []
    gone, kept, keep_mask = [], [], []
    for _, r in df.iterrows():
        why = why_blocked(r["Room"], active)
        if why and arriving(r):
            kept.append((str(r["Room"]).strip().upper(), why))
            keep_mask.append(True)
        elif why:
            gone.append((str(r["Room"]).strip().upper(), why))
            keep_mask.append(False)
        else:
            keep_mask.append(True)
    return df[keep_mask].reset_index(drop=True), gone, kept


def describe(gone) -> str:
    """'28 rooms (building 1 Plaza 6, building 1 floor 3 22)' for a note."""
    if not gone:
        return ""
    import collections
    by = collections.Counter()
    for room, _ in gone:
        loc = pmap.parse(room)
        by[f"building {loc.bld} {'floor ' + loc.level if loc.level.isdigit() else loc.level}" if loc else room] += 1
    return f"{len(gone)} rooms ({', '.join(f'{k} {v}' for k, v in by.items())})"
