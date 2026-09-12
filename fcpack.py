"""Full Clean charts: one packer, built around what a chart is not allowed to be.

There used to be two of these and a choice on the Schedule page between them.
The choice was never really the scheduler's to make -- both answers were wrong
in the same two ways, and neither was wrong in a way the other fixed. This is
one packer with the rules written down once, at the top, where every pass has
to go through them.

The rules are hard. A chart may not:

  * split an apartment.  A guest holding 2336E, 2336G and 2336H holds one
    lock-off apartment with doors between the rooms. Two housekeepers in it is
    two people doing one turnover, and the floor notices. Rooms are bundled by
    guest *and* room number *and* floor, so a guest who genuinely holds rooms
    in two buildings is still two bundles -- that split is real and fine.
  * run over the cap.
  * hold more than one 140, or a 140 beside more than one 120.  This is the
    rule `_fc_feasible` in the scheduler has always stated; it is here because
    the old packers re-dealt the scheduler's legal charts and broke it. A
    140+120+120 comes to exactly 380 and passes a minutes check, which is why
    a minutes check is not enough.
  * hold rooms in buildings 2 and 3.  They do not touch; building 1 is the
    only way between them, so such a chart pays two bridge crossings.

Within the rules it wants, in order: fewest housekeepers, least walking, and
charts close to full. Count comes first because a housekeeper is a whole shift
and a crossing is a few minutes -- but travel outranks fullness, because a
short chart is somebody's easy day and a long walk is nobody's.
"""
import collections

BORD = {3: 0, 1: 1, 2: 2}          # west to east, as the property runs

SOLO = ("", "---", "unallocated", "n/a", "none")


# ── what a chart may not be ──────────────────────────────────────────────────

def _hops(blds):
    """Bridges anyone on a chart must cross: 0, 1 or 2, straight off the map."""
    from property_map import BRIDGES
    bs = sorted(b for b in blds if b in (1, 2, 3))
    worst = 0
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            worst = max(worst, 1 if BRIDGES.get(frozenset((bs[i], bs[j]))) else 2)
    return worst


def _legal(time, n140, n120, blds, cap):
    """The four hard rules, in one place, so no pass can route around them."""
    if time > cap:
        return False
    if n140 > 1:
        return False
    if n140 >= 1 and n120 > 1:
        return False
    if 2 in blds and 3 in blds:
        return False
    return True


# ── bundles: the smallest thing a chart can be given ─────────────────────────

def _unit_key(r):
    """The apartment a room belongs to, or None if it stands alone.

    The room number without its lock-off letter is the apartment; the guest
    name is what says the lock-offs are currently one household rather than
    three separate lettings.
    """
    guest = str(r.get("guest") or "").strip().lower()
    if guest in SOLO:
        return None
    digits = "".join(c for c in str(r.get("room") or "") if c.isdigit())
    if not digits:
        return None
    return (guest, digits)


class _Bundle(object):
    """Rooms that go to one housekeeper or the day is wrong."""

    __slots__ = ("rooms", "time", "n140", "n120", "blds", "levels", "x")

    def __init__(self, rooms, loc_of):
        self.rooms = list(rooms)
        self.time = sum(r.get("time", 0) for r in rooms)
        self.n140 = sum(1 for r in rooms if r.get("time") == 140)
        self.n120 = sum(1 for r in rooms if r.get("time") == 120)
        locs = [loc_of(r) for r in rooms]
        locs = [l for l in locs if l]
        self.blds = {l.bld for l in locs}
        self.levels = {l.level_ix for l in locs}
        self.x = min([l.x for l in locs] or [0])


def _legal_alone(rooms, cap):
    """Could these rooms be a chart at all? A bundle that cannot must be split."""
    return _legal(sum(r.get("time", 0) for r in rooms),
                  sum(1 for r in rooms if r.get("time") == 140),
                  sum(1 for r in rooms if r.get("time") == 120),
                  set(), cap)


def _split_illegal(rooms, cap):
    """Break an apartment that cannot legally be one chart into the fewest
    pieces that can.

    Keeping rooms together is a rule, but it cannot outrank the rules that say
    what a chart may hold: a guest holding two 140s, or more than 380 minutes
    behind one door, has to go to two people whatever anybody prefers. Without
    this the bundle would be forced whole onto a fresh chart and quietly break
    the cap -- the same class of fault this module exists to stop.
    """
    if _legal_alone(rooms, cap):
        return [list(rooms)]
    out, cur = [], []
    for r in sorted(rooms, key=lambda r: -r.get("time", 0)):
        if cur and _legal_alone(cur + [r], cap):
            cur.append(r)
        elif cur:
            out.append(cur)
            cur = [r]
        else:
            cur = [r]
    if cur:
        out.append(cur)
    return out


def bundles(rooms, cap, loc_of):
    """Group the rooms that must not be split, and leave the rest alone.

    Adjacency is checked, not assumed: rooms are bundled only when they share
    a guest, an apartment number *and* a floor. Jaramillo holds seven rooms
    today across three floors -- that is three bundles, not one 690-minute
    chart nobody could work.
    """
    groups = collections.defaultdict(list)
    loose = []
    for r in rooms:
        key = _unit_key(r)
        if key is None:
            loose.append(r)
            continue
        loc = loc_of(r)
        where = (loc.bld, loc.level_ix) if loc else (None, None)
        groups[(key, where)].append(r)

    out = []
    for v in groups.values():
        for piece in _split_illegal(v, cap):
            out.append(_Bundle(piece, loc_of))
    out += [_Bundle([r], loc_of) for r in loose]
    return out


# ── a chart under construction ───────────────────────────────────────────────

class _Chart(object):
    __slots__ = ("buns", "time", "n140", "n120", "blds", "levels")

    def __init__(self):
        self.buns = []
        self.time = 0
        self.n140 = 0
        self.n120 = 0
        self.blds = set()
        self.levels = set()

    def accepts(self, b, cap):
        return _legal(self.time + b.time, self.n140 + b.n140,
                      self.n120 + b.n120, self.blds | b.blds, cap)

    def add(self, b):
        self.buns.append(b)
        self.time += b.time
        self.n140 += b.n140
        self.n120 += b.n120
        self.blds |= b.blds
        self.levels |= b.levels

    def drop(self, b):
        self.buns.remove(b)
        self.time -= b.time
        self.n140 -= b.n140
        self.n120 -= b.n120
        self.blds = set()
        self.levels = set()
        for x in self.buns:
            self.blds |= x.blds
            self.levels |= x.levels

    def rooms(self):
        return [r for b in self.buns for r in b.rooms]

    def travel(self):
        """What this chart costs to walk, in rough minutes-equivalent.

        A building crossing dwarfs everything else, and the span between the
        top and bottom floor matters more than how many floors are touched --
        Plaza-and-4 is a lift ride past three landings, 2-and-3 is a staircase.
        """
        if not self.levels:
            return 0
        cost = 40 * _hops(self.blds) + 25 * (len(self.blds) - 1)
        cost += 6 * (max(self.levels) - min(self.levels))
        cost += 2 * (len(self.levels) - 1)
        return cost


def _score(charts, low_min):
    """Fewest housekeepers, then least walking, then fewest short days."""
    live = [c for c in charts if c.buns]
    return (len(live),
            sum(c.travel() for c in live),
            sum(1 for c in live if c.time < low_min))


# ── the pack ─────────────────────────────────────────────────────────────────

def _seed(buns, cap):
    """A first arrangement: one building at a time, down the floors in order.

    Bundles are placed heaviest-first within a floor, because the awkward ones
    -- a 380-minute apartment, a 140 -- have the fewest homes and want first
    refusal. A chart already on the floor gets it before an empty one.
    """
    charts = []
    by_bld = collections.defaultdict(list)
    for b in buns:
        key = min(b.blds) if b.blds else 9
        by_bld[key].append(b)

    for bld in sorted(by_bld, key=lambda b: BORD.get(b, 9)):
        here = sorted(by_bld[bld],
                      key=lambda b: (min(b.levels) if b.levels else 99,
                                     -b.time, b.x))
        mine = []
        for b in here:
            lv = min(b.levels) if b.levels else None
            fits = [c for c in mine if c.accepts(b, cap)]
            same = [c for c in fits if lv is not None and lv in c.levels]
            if same:
                pick = max(same, key=lambda c: c.time)
            elif fits:
                def near(c):
                    if not c.levels or lv is None:
                        return 0
                    return min(abs(l - lv) for l in c.levels)
                pick = min(fits, key=lambda c: (near(c), -c.time))
            else:
                pick = _Chart()
                mine.append(pick)
                if not pick.accepts(b, cap):
                    # `bundles` splits anything that cannot be a chart on its
                    # own, so an empty chart always takes it. If that ever
                    # stops being true, say so rather than shipping the day.
                    raise ValueError(
                        "bundle cannot form a legal chart: %s"
                        % ", ".join(str(r.get("room")) for r in b.rooms))
            pick.add(b)
        charts += mine
    return charts


def _improve(charts, cap, low_min, rounds=400):
    """Steepest descent on (count, travel, short days) with the rules held.

    Three moves: shift one bundle, swap two, and empty the lightest chart
    outright. The third is the one that removes a housekeeper; the first two
    are what make room for it.
    """
    charts = [c for c in charts if c.buns]
    best = _score(charts, low_min)

    for _ in range(rounds):
        moved = False

        # empty the lightest chart if every bundle in it has somewhere legal
        order = sorted(range(len(charts)), key=lambda i: charts[i].time)
        for i in order:
            src = charts[i]
            others = [c for j, c in enumerate(charts) if j != i]
            plan, loads = [], {id(c): c for c in others}
            trial = []
            ok = True
            for b in sorted(src.buns, key=lambda b: -b.time):
                cand = [c for c in others if c.accepts(b, cap)]
                if not cand:
                    ok = False
                    break
                pick = min(cand, key=lambda c: (_hops(c.blds | b.blds),
                                                len(c.blds | b.blds),
                                                -c.time))
                pick.add(b)
                trial.append((pick, b))
            if ok:
                kept = [c for c in charts if c is not src]
                s = _score(kept, low_min)
                if s < best:
                    charts = kept
                    best = s
                    moved = True
                    break
            for pick, b in reversed(trial):
                pick.drop(b)
        if moved:
            continue

        # shift one bundle
        for i, src in enumerate(charts):
            for b in list(src.buns):
                for j, dst in enumerate(charts):
                    if i == j or not dst.accepts(b, cap):
                        continue
                    src.drop(b)
                    dst.add(b)
                    s = _score(charts, low_min)
                    if s < best:
                        best = s
                        charts = [c for c in charts if c.buns]
                        moved = True
                        break
                    dst.drop(b)
                    src.add(b)
                if moved:
                    break
            if moved:
                break
        if moved:
            continue

        # swap two bundles
        for i in range(len(charts)):
            for j in range(i + 1, len(charts)):
                a, d = charts[i], charts[j]
                for x in list(a.buns):
                    for y in list(d.buns):
                        a.drop(x); d.drop(y)
                        if a.accepts(y, cap) and d.accepts(x, cap):
                            a.add(y); d.add(x)
                            s = _score(charts, low_min)
                            if s < best:
                                best = s
                                moved = True
                                break
                            a.drop(y); d.drop(x)
                        a.add(x); d.add(y)
                    if moved:
                        break
                if moved:
                    break
            if moved:
                break
        if not moved:
            break

    return [c for c in charts if c.buns]


def pack(rooms, cap, loc_of, low_min=330):
    """The one packer. Returns a list of charts, each a list of room dicts.

    `loc_of(room)` gives something with .bld, .level_ix and .x, or None for a
    room the plans cannot place. Those are packed last and together, as before
    -- they have no location to be tidy about.
    """
    placed, unplaced = [], []
    for r in rooms:
        (placed if loc_of(r) else unplaced).append(r)

    charts = []
    if placed:
        buns = bundles(placed, cap, loc_of)
        charts = _improve(_seed(buns, cap), cap, low_min)

    out = [c.rooms() for c in charts]

    if unplaced:
        cur, t = [], 0
        for r in unplaced:
            if cur and t + r.get("time", 0) > cap:
                out.append(cur)
                cur, t = [], 0
            cur.append(r)
            t += r.get("time", 0)
        if cur:
            out.append(cur)
    return out


def audit(charts, cap, loc_of, low_min=330):
    """What is wrong with a set of charts, for tests and for the page.

    Returns counts, never raises: a caller that wants to assert can, and one
    that only wants to show a warning can do that instead.
    """
    split = collections.defaultdict(set)
    bad_mix = 0
    b23 = 0
    over = 0
    low = 0
    for i, c in enumerate(charts):
        t = sum(r.get("time", 0) for r in c)
        n140 = sum(1 for r in c if r.get("time") == 140)
        n120 = sum(1 for r in c if r.get("time") == 120)
        blds = {loc_of(r).bld for r in c if loc_of(r)}
        if t > cap:
            over += 1
        if t < low_min:
            low += 1
        if n140 > 1 or (n140 >= 1 and n120 > 1):
            bad_mix += 1
        if 2 in blds and 3 in blds:
            b23 += 1
        for r in c:
            k = _unit_key(r)
            if k:
                loc = loc_of(r)
                split[(k, (loc.bld, loc.level_ix) if loc else None)].add(i)
    return {"charts": len(charts),
            "split_bundles": sum(1 for v in split.values() if len(v) > 1),
            "bad_mix": bad_mix, "b2_b3": b23, "over_cap": over, "low": low}
