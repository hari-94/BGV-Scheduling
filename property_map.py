"""Where every room is, and what it costs to walk between two of them.

Built from the property's own floor plans -- the maps posted by the service
elevators -- and checked against every room that has ever appeared on a chart.

A room code is BLNNU: building, level digit, room number, unit letter.

Two things about that code are not obvious, and both have to be handled here
rather than guessed at the call site:

  * The level digit is not the level. Digit 0 covers *two* levels, Plaza and
    Terrace, split by room number, in buildings 1 and 3. Building 1 has no
    guest rooms on level 1 (lobby, pool, spa) and building 2 has none on Plaza
    or Terrace (parking, and the housekeeping office).

  * Building 3 renumbers the same floor plate on its low levels. The door at
    the east end of the south corridor is 3240A on level 2, 3020A on Terrace
    and 3010A on Plaza -- one position, three numbers. _canon undoes that so a
    single floor plan serves the whole stack, which is what the plans
    themselves show: every level of building 3 is the same shape.

Buildings 2 and 3 do not touch. Building 1 is the link between them, so a room
in 2 and a room in 3 are always two bridges apart -- the most expensive thing a
chart can do, and the thing this module exists to price.
"""

from __future__ import annotations

import re
from collections import namedtuple

# --------------------------------------------------------------------------
# Levels, in elevation order. The names are the property's own and mean the
# same height in all three buildings, which is what makes a bridge meaningful.
# --------------------------------------------------------------------------
LEVELS = ["Plaza", "Terrace", "1", "2", "3", "4", "5"]
LEVEL_IX = {name: i for i, name in enumerate(LEVELS)}

# Bridges between buildings, by the level they cross at.
BRIDGES = {
    frozenset((1, 2)): ["Plaza", "Terrace", "1", "2"],
    frozenset((1, 3)): ["Plaza", "1"],
    # 2 <-> 3 has no bridge. Routing goes through building 1.
}

# --------------------------------------------------------------------------
# Cost model, in seconds. Every number here is an estimate, not a measurement,
# and they are named so they can be tuned once somebody times a real trip.
# What matters for assignment is the ratio between them: crossing a building
# must cost more than changing floors, which must cost more than walking the
# corridor.
# --------------------------------------------------------------------------
SLOT_SECONDS = 7.0     # one door's width along a corridor
CROSS_HALL = 4.0       # stepping to the other side of the corridor
ELEVATOR_WAIT = 55.0   # one service-elevator call, with a cart
PER_LEVEL = 9.0        # each level the car travels
BRIDGE_CROSS = 75.0    # walking a bridge, elevator core to elevator core
BRIDGE_CHANGE = 90.0   # crossing building 1 to reach its other bridge
UNKNOWN_ROOM = 240.0   # a code the plans do not cover: assume the worst

# --------------------------------------------------------------------------
# Floor plates. (row, x): row 0 is the north side of the corridor, row 1 the
# south side, x runs west to east in door-widths. Taken off the plans.
# --------------------------------------------------------------------------

# Building 1, levels 2-5. Levels 2 and 3 are identical; level 4 swaps the east
# wing for two large units; level 5 is only the west end.
B1_TOWER = {
    ("26", "B"): (0, 0.6), ("26", "A"): (0, 1.5),
    ("24", "H"): (0, 2.4), ("24", "G"): (0, 3.3),
    ("24", "E"): (0, 4.1), ("24", "F"): (0, 5.0),
    ("22", "H"): (0, 9.0), ("22", "G"): (0, 9.9),
    ("22", "E"): (0, 10.9), ("22", "F"): (0, 11.8),
    ("20", "E"): (0, 12.8),
    ("20", "G"): (0, 14.1), ("20", "H"): (0.7, 14.1), ("20", "I"): (1.2, 14.1),
    ("20", "A"): (0, 14.1), ("20", "B"): (1.0, 14.1),   # level 4's east wing
    ("23", "D"): (1, 1.7), ("23", "C"): (1, 2.8),
    ("23", "B"): (1, 3.8), ("23", "A"): (1, 4.9),
    ("21", "D"): (1, 7.3), ("21", "C"): (1, 8.5),
    ("21", "B"): (1, 9.9), ("21", "A"): (1, 11.4),
}
B1_TOWER_ELEV = (1.5, 5.2)

# Building 1, Plaza and Terrace: one strip of six units, same on both levels.
B1_STRIP = {
    ("10", "A"): (1, 4.5), ("10", "B"): (1, 5.5),
    ("10", "C"): (1, 6.7), ("10", "D"): (1, 8.0),
    ("12", "A"): (1, 9.4), ("12", "B"): (1, 10.7),
}
B1_STRIP_ELEV = (0.0, 10.2)

# Building 2, levels 1-4. Level 1 gives its east half to the theatres and the
# lobby, so 31 and 33 are missing there; level 4 swaps 32E-H for 32A/32B.
B2_TOWER = {
    ("36", "G"): (0, 0.4), ("36", "E"): (0, 1.6),
    ("34", "A"): (0, 3.6), ("34", "B"): (0, 4.7),
    ("32", "H"): (0, 6.7), ("32", "G"): (0, 7.7),
    ("32", "E"): (0, 8.7), ("32", "F"): (0, 9.6),
    ("32", "A"): (0, 7.7), ("32", "B"): (0, 8.6),       # level 4
    ("36", "H"): (1, 0.7), ("36", "I"): (1, 1.8),
    ("35", "B"): (1, 3.0), ("35", "A"): (1, 4.3),
    ("33", "D"): (1, 6.6), ("33", "C"): (1, 8.0),
    ("33", "B"): (1, 9.4), ("33", "A"): (1, 10.8),
    ("31", "B"): (0.6, 12.4), ("31", "A"): (1, 12.2),
}
B2_TOWER_ELEV = (1.5, 4.5)

# Building 3: one plate, every level, in canonical (level-2) numbers.
B3_PLATE = {
    ("46", "E"): (0, 0.5), ("46", "G"): (0.5, 0.5),
    ("51", "H"): (0, 2.2), ("51", "G"): (0, 3.0),
    ("51", "E"): (0, 3.8), ("51", "F"): (0, 4.7),
    ("49", "F"): (0, 5.5), ("49", "E"): (0, 6.3),
    ("49", "G"): (0, 7.2), ("49", "H"): (0, 8.0),
    ("47", "A"): (0, 9.6), ("45", "A"): (0, 10.4),
    # Level 3 splits the 45/43 stretch into 43B and 43A and has no 45A, so 43B
    # can take 45A's ground: at 10.5 it sat 0.7 from 43A, closer than any real
    # pair of doors, and the two drew through each other.
    ("43", "B"): (0, 10.3), ("43", "A"): (0, 11.2),
    ("41", "B"): (0, 12.7), ("41", "A"): (0, 13.6),
    ("46", "H"): (1, 0.5), ("46", "I"): (1, 1.4),
    ("44", "A"): (1, 2.2), ("44", "B"): (1, 3.1),
    ("42", "B"): (1, 5.1), ("42", "A"): (1, 6.3),
    ("40", "D"): (1, 9.8), ("40", "C"): (1, 11.0),
    ("40", "B"): (1, 12.2), ("40", "A"): (1, 13.4),
}
B3_PLATE_ELEV = (1.5, 4.2)

# The day starts and ends at the housekeeping office: building 2, Terrace.
OFFICE_BLD = 2
OFFICE_LEVEL = "Terrace"

# The rooms that are not on either side of the corridor but in a short wing
# running across its end. Taken off the plans, not inferred: their row is what
# separates them from each other, so a drawing that pushes them out to a side
# lands two of them on the same spot. 1220I sits at row 1.2 and would pass any
# "is it near the south row" test, which is why this is a list and not a rule.
WINGS = {
    (1, "20", "G"), (1, "20", "H"), (1, "20", "I"),
    (1, "20", "A"), (1, "20", "B"),
    (2, "31", "A"), (2, "31", "B"),
    (3, "46", "E"), (3, "46", "G"), (3, "46", "H"),
}

Loc = namedtuple("Loc", "code bld level level_ix num unit row x elev")

_CODE = re.compile(r"^(\d)(\d)(\d\d)([A-Z]?)$")


def _level_of(bld, digit, num):
    """The named level a code sits on. Digit 0 is two levels, split by number."""
    if digit == 0:
        if bld in (1, 3):
            return "Plaza" if num < 20 else "Terrace"
        return None                      # building 2 has no rooms down there
    if 1 <= digit <= 5:
        return str(digit)
    return None


def _canon(bld, level, num):
    """Building 3's low levels renumber the same doors. Put them back."""
    if bld == 3:
        if level == "Plaza":
            return "%02d" % (num + 30)
        if level == "Terrace":
            return "%02d" % (num + 20)
    if bld == 1 and level == "Terrace":
        return "%02d" % (num - 10)       # 1020A is 1010A one level up
    return "%02d" % num


def _plate(bld, level):
    if bld == 1:
        if level in ("Plaza", "Terrace"):
            return B1_STRIP, B1_STRIP_ELEV
        return B1_TOWER, B1_TOWER_ELEV
    if bld == 2:
        return B2_TOWER, B2_TOWER_ELEV
    if bld == 3:
        return B3_PLATE, B3_PLATE_ELEV
    return None, None


def parse(code):
    """A room code to a place on the property, or None if the plans miss it."""
    if not code:
        return None
    m = _CODE.match(str(code).strip().upper())
    if not m:
        return None
    bld, digit, num, unit = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    level = _level_of(bld, digit, int(num))
    if level is None:
        return None
    plate, elev = _plate(bld, level)
    if plate is None:
        return None
    key = (_canon(bld, level, int(num)), unit)
    spot = plate.get(key)
    if spot is None:
        return None
    return Loc(m.group(0), bld, level, LEVEL_IX[level], key[0], unit,
               spot[0], spot[1], elev)


def _walk(row_a, x_a, row_b, x_b):
    d = abs(x_a - x_b) * SLOT_SECONDS
    if abs(row_a - row_b) > 0.4:
        d += CROSS_HALL
    return d


def _to_elevator(loc):
    return _walk(loc.row, loc.x, loc.elev[0], loc.elev[1])


def _bridge_levels(a, b):
    return BRIDGES.get(frozenset((a, b)), [])


def _ride(level_from, level_to):
    """Riding a service elevator between two named levels in one building."""
    if level_from == level_to:
        return 0.0
    return ELEVATOR_WAIT + abs(LEVEL_IX[level_from] - LEVEL_IX[level_to]) * PER_LEVEL


def _between_buildings(bld_a, level_a, foot_a, bld_b, level_b, foot_b):
    """Cost from a point in one building to a point in another.

    foot_a / foot_b are the walks from the room to its own service elevator;
    a level with no rooms still has a core to arrive at, which is why the
    office can use this with a foot cost of zero.
    """
    direct = _bridge_levels(bld_a, bld_b)
    if direct:
        return min(
            foot_a + _ride(level_a, lv) + BRIDGE_CROSS + _ride(lv, level_b) + foot_b
            for lv in direct
        )
    best = None
    for lv1 in _bridge_levels(bld_a, 1):
        for lv2 in _bridge_levels(1, bld_b):
            c = (foot_a + _ride(level_a, lv1) + BRIDGE_CROSS
                 + _ride(lv1, lv2) + BRIDGE_CHANGE + BRIDGE_CROSS
                 + _ride(lv2, level_b) + foot_b)
            best = c if best is None else min(best, c)
    return best if best is not None else UNKNOWN_ROOM


def travel_seconds(a, b):
    """Roughly how long it takes to get from room a to room b with a cart."""
    la = a if isinstance(a, Loc) else parse(a)
    lb = b if isinstance(b, Loc) else parse(b)
    if la is None or lb is None:
        return UNKNOWN_ROOM
    if la.code == lb.code:
        return 0.0
    if la.bld == lb.bld:
        if la.level == lb.level:
            return _walk(la.row, la.x, lb.row, lb.x)
        return _to_elevator(la) + _ride(la.level, lb.level) + _to_elevator(lb)
    return _between_buildings(la.bld, la.level, _to_elevator(la),
                              lb.bld, lb.level, _to_elevator(lb))


def office_seconds(room):
    """From the housekeeping office (building 2, Terrace) to a room."""
    loc = room if isinstance(room, Loc) else parse(room)
    if loc is None:
        return UNKNOWN_ROOM
    if loc.bld == OFFICE_BLD:
        return _ride(OFFICE_LEVEL, loc.level) + _to_elevator(loc)
    return _between_buildings(OFFICE_BLD, OFFICE_LEVEL, 0.0,
                              loc.bld, loc.level, _to_elevator(loc))


# --------------------------------------------------------------------------
# Whole charts
# --------------------------------------------------------------------------

def best_order(rooms, from_office=True):
    """The order to clean these rooms that walks least.

    Nearest neighbour, then 2-opt. A chart holds ten to twenty rooms, so this
    is exact enough and finishes instantly; a real solver would buy nothing.
    """
    codes = [str(r).strip().upper() for r in rooms if str(r).strip()]
    if len(codes) < 2:
        return list(codes)
    locs = {c: parse(c) for c in codes}

    def hop(x, y):
        return travel_seconds(locs[x] or x, locs[y] or y)

    def total(seq):
        t = office_seconds(locs[seq[0]] or seq[0]) if from_office else 0.0
        return t + sum(hop(seq[i], seq[i + 1]) for i in range(len(seq) - 1))

    remaining = list(codes)
    first = (min(remaining, key=lambda c: office_seconds(locs[c] or c))
             if from_office else remaining[0])
    order = [first]
    remaining.remove(first)
    while remaining:
        nxt = min(remaining, key=lambda c: hop(order[-1], c))
        order.append(nxt)
        remaining.remove(nxt)

    base = total(order)
    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 2, len(order)):
                cand = order[:i + 1] + order[i + 1:j + 1][::-1] + order[j + 1:]
                c = total(cand)
                if c < base - 0.5:
                    order, base, improved = cand, c, True
    return order


def chart_travel(rooms, from_office=True):
    """Seconds of walking a chart costs when cleaned in its best order."""
    order = best_order(rooms, from_office)
    if not order:
        return 0.0
    locs = {c: parse(c) for c in order}
    total = office_seconds(locs[order[0]] or order[0]) if from_office else 0.0
    total += sum(travel_seconds(locs[order[i]] or order[i],
                                locs[order[i + 1]] or order[i + 1])
                 for i in range(len(order) - 1))
    return total


def spread(rooms):
    """What a chart is scattered across -- buildings, levels, unknown codes."""
    blds, floors, unknown = set(), set(), []
    for r in rooms:
        loc = parse(r)
        if loc is None:
            unknown.append(str(r))
            continue
        blds.add(loc.bld)
        floors.add((loc.bld, loc.level))
    return {"buildings": sorted(blds),
            "floors": sorted(floors, key=lambda f: (f[0], LEVEL_IX[f[1]])),
            "n_buildings": len(blds), "n_floors": len(floors),
            "unknown": unknown}


# --------------------------------------------------------------------------
# Geometry, for drawing the property rather than costing it
# --------------------------------------------------------------------------

# Metres-ish per unit of the plate coordinates, and how the three buildings sit
# next to each other. The plans carry no dimensions, so these are proportions
# taken off the drawings: a door is about seven metres of corridor, a level is
# about three metres, and the corridor is about six metres across. The shape is
# right and the topology is exact; the measurements are not survey data.
DOOR_W = 3.6
LEVEL_H = 4.2
HALL_D = 13.0          # the corridor itself, wide enough to read down
BLD_GAP = 74.0
BLD_ORDER = [3, 1, 2]          # west to east, building 1 in the middle


def _bld_offset(bld):
    return BLD_ORDER.index(bld) * BLD_GAP


def layout(codes):
    """Every given room as a box in one world, for a 3-D or plan drawing.

    A plate is shared between levels — building 3 uses one for its whole stack —
    so the plate alone cannot say which rooms a level actually has. The caller
    passes the real room codes; anything the plans do not cover is dropped
    rather than guessed at a wrong position.
    """
    out = []
    for c in codes:
        loc = parse(c)
        if loc is None:
            continue
        out.append({"code": loc.code, "bld": loc.bld, "level": loc.level,
                    "num": loc.num, "unit": loc.unit,
                    # `row` and `side` go out too: a room's depth depends on
                    # how long it takes to clean, which this module has no way
                    # of knowing, so the drawing grows each box away from the
                    # corridor itself. Without the side it would grow across it.
                    "row": loc.row,
                    "side": -1 if loc.row < 0.6 else 1,
                    "wing": (loc.bld, loc.num, loc.unit) in WINGS,
                    "x": round(_bld_offset(loc.bld) + loc.x * DOOR_W, 2),
                    "y": round(loc.level_ix * LEVEL_H, 2),
                    "z": round(loc.row * HALL_D, 2)})
    return out


def bridge_spans():
    """Each bridge as a box between two buildings, for the drawing."""
    spans = []
    for pair, levels in BRIDGES.items():
        a, b = sorted(pair)
        xa, xb = _bld_offset(a), _bld_offset(b)
        for lv in levels:
            lo, hi = (xa, xb) if xa < xb else (xb, xa)
            spans.append({"a": a, "b": b, "level": lv,
                          "x0": round(lo + 14 * DOOR_W, 2),
                          "x1": round(hi + 1 * DOOR_W, 2),
                          "y": round(LEVEL_IX[lv] * LEVEL_H, 2),
                          "z": round(0.5 * HALL_D, 2)})
    return spans


def describe(rooms):
    """One line for a chart card: where it is, and how far apart it is."""
    s = spread(rooms)
    if not s["floors"]:
        return "unplaced"
    where = ", ".join("B%d·%s" % (b, lv) for b, lv in s["floors"])
    return "%s — %.0f min walking" % (where, chart_travel(rooms) / 60.0)
