"""What to clean first, and when each room will actually be reached.

The chart says which rooms; it does not say what order, and the order is where
a day is won or lost. Three things pull against each other:

  * A late checkout is a wall. The guest is still in the room until 10:30, or
    11, or noon; arriving before that wastes the trip twice, once going and
    once coming back.
  * An early check-in is a promise already made at the front desk. It has to be
    done first even if it is in the wrong building.
  * Everything else should be walked as little as possible, which is what
    property_map costs out.

So the order is not a sort. It is a simulation of the day, minute by minute,
choosing at each step the room that costs least to reach *and* is worth doing
next -- where waiting for a guest to leave counts as cost, which is what pushes
late checkouts to the back on their own without a rule saying so.

No Streamlit here, so it can be tested against a real day on its own.
"""

from __future__ import annotations

import re
from datetime import time

import property_map as pm

# The property's day, from HP: carts roll at ten, the floor should be finished
# by half three, guests check in at four. That 330-minute window is the same
# number as LOW_MIN in the scheduler -- a chart packed to MAX_FC (380) cannot
# fit inside the day before a single step is walked, which the timeline shows.
DAY_START = time(10, 0)
TARGET_END = time(15, 30)
CHECKIN = time(16, 0)

# A bare "Late Out" with no time. The explicit values in the data are 10:30,
# 11:00 and 12:00; 11:00 is the middle of them and the safe assumption.
BARE_LATE_OUT = time(11, 0)

# How many seconds of extra walking a rank of urgency is worth. An early
# check-in scores 100, so it can justify roughly ten minutes of detour -- one
# bridge crossing -- which is the intent. Ordinary rooms score 10 and shuffle
# only when it is nearly free.
URGENCY_SECONDS = 6.0

# How much a room's own length pulls it earlier, in seconds of detour per
# minute of cleaning. HP's rule: the big rooms go first unless a late checkout
# says otherwise. The reason is the shape of the day rather than the room -- a
# 140 found at two in the afternoon cannot be finished by half three, and a 70
# can.
#
# 1.0 because the effect saturates there. Measured over all 1,387 stored
# charts, it puts the 140s a third of the way through the day, the 120s at the
# half and the 70s at three quarters -- and 2.0, 3.0 and 5.0 all produce that
# same order while walking 2%, 4% and 8% further. Anything above 1.0 is paying
# for an ordering already bought. It stays well under an early check-in's 600,
# so a promise made at the front desk still outranks a big room.
SIZE_SECONDS = 1.0

_LATE = re.compile(r"(\d{1,2})[:.](\d{2})\s*([ap])\.?m", re.I)


def _mins(t: time) -> int:
    return t.hour * 60 + t.minute


def hhmm(minute: int) -> str:
    """Minutes from midnight as a clock a person reads."""
    minute = int(round(minute))
    h, m = divmod(minute % (24 * 60), 60)
    ampm = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return "%d:%02d%s" % (h12, m, ampm)


def release_minute(room) -> int | None:
    """The earliest minute the room can be started, or None if it is free now.

    Only a late checkout creates one. The text comes off the morning email and
    is not consistently formatted, so parse loosely and fall back rather than
    dropping a constraint on the floor.
    """
    raw = str(room.get("late_checkout") or "").strip()
    if not raw:
        return None
    m = _LATE.search(raw)
    if not m:
        return _mins(BARE_LATE_OUT)
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ap == "p" and h != 12:
        h += 12
    if ap == "a" and h == 12:
        h = 0
    return h * 60 + mi


def _text(room) -> str:
    return " ".join(str(room.get(k) or "") for k in
                    ("notes", "res_type", "status", "service")).lower()


def urgency(room) -> int:
    """How much this room wants to be done early. Bigger is sooner."""
    t = _text(room)
    if "early in" in t or "early check" in t:
        return 100
    if "vip" in t:
        return 70
    if "stayover" in t or "stay over" in t or room.get("verify"):
        return 5          # the guest is still living there; last
    if str(room.get("arriving") or "").strip():
        return 50         # somebody is checking into this room today
    if "owner" in t:
        return 30
    return 10             # nobody arriving: it can slip


def why(room) -> str:
    """The one reason this room sits where it does, for the card to show."""
    t = _text(room)
    if "early in" in t or "early check" in t:
        return "early check-in"
    if "vip" in t:
        return "VIP"
    if "stayover" in t or "stay over" in t or room.get("verify"):
        return "stayover"
    if str(room.get("late_checkout") or "").strip():
        return "late checkout"
    if str(room.get("arriving") or "").strip():
        return "guest arriving"
    return "no arrival today"


# Rooms whose sheet carries no minutes at all -- in practice the Dust n Vac
# round, where the morning report has never had a time column. A touch-up is
# not a clean, so the old fallback of a full 45 minutes turned a 38-room Dust
# n Vac chart into a 28-hour day. This is a stated guess, and `summary` counts
# how many rooms it was applied to so the page can say the estimate is partial
# rather than quietly presenting a made-up number as a plan.
UNTIMED_MINUTES = 12.0

# The fastest the plan will ever ask anybody to work, as a fraction of the
# sheet's minutes. Below this the chart does not fit the day and no pacing will
# make it, so the plan is left overrunning where it can be seen rather than
# quietly demanding an impossible pace.
MIN_PACE = 0.6


def _clean_minutes(room) -> float:
    try:
        return float(room.get("time") or 0) or UNTIMED_MINUTES
    except (TypeError, ValueError):
        return UNTIMED_MINUTES


def _is_untimed(room) -> bool:
    try:
        return not float(room.get("time") or 0)
    except (TypeError, ValueError):
        return True


def _simulate(rooms, start, from_office, scale):
    """Walk the day forward once at a given pace and say when each room falls.

    `scale` multiplies the sheet's minutes. The 70/120/140 on a chart are
    standards, not stopwatch times, and the floor beats them; pacing is what
    turns a standard into a time somebody can actually work to.
    """
    now = float(_mins(start or DAY_START))
    remaining = list(rooms)
    here = None
    out = []

    while remaining:
        best, best_score, best_travel, best_wait = None, None, 0.0, 0.0
        for r in remaining:
            code = str(r["room"]).strip().upper()
            travel = (pm.office_seconds(code) if here is None
                      else pm.travel_seconds(here, code))
            rel = release_minute(r)
            arrive = now + travel / 60.0
            wait = max(0.0, (rel - arrive) * 60.0) if rel is not None else 0.0
            score = (travel + wait
                     - urgency(r) * URGENCY_SECONDS
                     - _clean_minutes(r) * SIZE_SECONDS)
            if best_score is None or score < best_score:
                best, best_score, best_travel, best_wait = r, score, travel, wait
        remaining.remove(best)
        code = str(best["room"]).strip().upper()
        t_min = best_travel / 60.0
        w_min = best_wait / 60.0
        begin = now + t_min + w_min
        nominal = _clean_minutes(best)
        dur = nominal * scale
        out.append({
            "room": code,
            "guest": best.get("guest") or "",
            "service": best.get("service") or "",
            "minutes": dur,
            "nominal": nominal,
            "travel": t_min,
            "wait": w_min,
            "start": begin,
            "end": begin + dur,
            "untimed": _is_untimed(best),
            "urgency": urgency(best),
            "why": why(best),
            "release": release_minute(best),
            "late": str(best.get("late_checkout") or "").strip(),
            "arriving": str(best.get("arriving") or "").strip(),
            "raw": best,
        })
        now = begin + dur
        here = code
    return out


def plan_day(rooms, start=None, from_office=True, fit_to=TARGET_END):
    """The day, paced so the last room lands on the target rather than past it.

    Two passes, because they depend on each other. The order comes first, from
    travel and urgency and the late checkouts. Only then is the pace known:
    whatever is left of the window once the walking and the waiting are taken
    out, divided across the rooms in proportion to their sheet minutes. Changing
    the pace can change the waiting -- compress the morning and a late-checkout
    room is reached before the guest has gone -- so it settles by iteration
    rather than a single division.

    The pace never goes above 1.0. A light chart finishes early; that is a real
    answer and stretching the rooms to fill the day would be a fiction. It will
    not go below MIN_PACE either: past that the chart genuinely does not fit the
    day, and the honest output is a plan that overruns visibly.
    """
    rooms = [r for r in rooms if str(r.get("room") or "").strip()]
    if not rooms:
        return []
    blocks = _simulate(rooms, start, from_office, 1.0)
    if fit_to is None:
        return blocks

    window = _mins(fit_to) - _mins(start or DAY_START)
    scale = 1.0
    for _ in range(6):
        nominal = sum(b["nominal"] for b in blocks)
        if nominal <= 0:
            break
        spare = window - sum(b["travel"] for b in blocks) - sum(b["wait"] for b in blocks)
        want = max(MIN_PACE, min(1.0, spare / nominal))
        if abs(want - scale) < 0.004:
            break
        scale = want
        blocks = _simulate(rooms, start, from_office, scale)
    for b in blocks:
        b["pace"] = scale
    return blocks


def summary(blocks, target=None):
    """The headline numbers under a timeline."""
    if not blocks:
        return {"finish": None, "over": 0.0, "travel": 0.0, "wait": 0.0,
                "clean": 0.0, "rooms": 0, "late_rooms": 0, "untimed": 0,
                "pace": 1.0, "nominal": 0.0}
    tgt = _mins(target or TARGET_END)
    finish = blocks[-1]["end"]
    return {
        "finish": finish,
        "over": max(0.0, finish - tgt),
        "travel": sum(b["travel"] for b in blocks),
        "wait": sum(b["wait"] for b in blocks),
        "clean": sum(b["minutes"] for b in blocks),
        "rooms": len(blocks),
        "late_rooms": sum(1 for b in blocks if b["release"] is not None),
        "untimed": sum(1 for b in blocks if b.get("untimed")),
        "pace": blocks[0].get("pace", 1.0),
        "nominal": sum(b.get("nominal", b["minutes"]) for b in blocks),
    }
