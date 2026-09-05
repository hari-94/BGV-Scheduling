"""Packing Full Clean so nobody changes building, and few change floor.

The building is decided first and is never crossed. Inside a building the
number of charts is fixed at the fewest that can hold its minutes, and the
rooms are then dealt into those charts a floor at a time, each going to the
chart that is already on its floor. A chart therefore fills up with one
corridor before it takes anything from another, without spending a person on
it -- which is the difference between this and simply packing floor by floor.
"""
import collections, math

BORD = {3: 0, 1: 1, 2: 2}          # west to east, as the property runs


def _fit(rs, cap, order, best_fit):
    """Deal these rooms into charts in the given order; return the loads."""
    bins = []
    for r in order:
        if best_fit:
            room = [i for i, b in enumerate(bins) if b + r["time"] <= cap]
            if room:
                bins[max(room, key=lambda i: bins[i])] += r["time"]
                continue
        else:
            for i, b in enumerate(bins):
                if b + r["time"] <= cap:
                    bins[i] += r["time"]
                    break
            else:
                bins.append(r["time"])
                continue
            continue
        bins.append(r["time"])
    return bins


def _bins_needed(rs, cap, tries=40):
    """Fewest charts that can hold these rooms.

    First-fit-decreasing on its own is not enough here. Building 1 on a real
    day holds 5,260 minutes, which is fourteen charts of 380, and FFD produced
    fifteen -- one whole housekeeper more than the person doing this by hand.
    The room times are a handful of repeated values (70, 120, 140), so a few
    shuffled deals find a perfect fit where the greedy one does not; the same
    trick the main solver already uses.
    """
    import math, random
    lower = math.ceil(sum(r["time"] for r in rs) / cap) if rs else 0
    best = None
    for order, bf in ((sorted(rs, key=lambda r: -r["time"]), False),
                      (sorted(rs, key=lambda r: -r["time"]), True),
                      (list(rs), False)):
        n = len(_fit(rs, cap, order, bf))
        best = n if best is None else min(best, n)
        if best <= lower:
            return best
    rng = random.Random(20240601)
    shuffled = list(rs)
    for _ in range(tries):
        rng.shuffle(shuffled)
        best = min(best, len(_fit(rs, cap, list(shuffled), True)))
        if best <= lower:
            break
    return max(best, lower)


def pack_full_clean(rooms, cap, loc_of, target=None, pool_leftovers=False):
    """Charts that never cross a building and change floor as little as they can.

    `loc_of(room)` gives something with .bld, .level and .x, or None. Rooms the
    plans do not place keep the old behaviour -- they are packed last, together.

    `target` is the most charts this may use. Pass the count the existing
    solver reaches and the result can only be as good or better: the same
    housekeepers, with the crossings removed wherever removing them is free.

    `pool_leftovers` trades a little of that purity for people. Each building
    still fills its own charts, but the rooms left over once it can no longer
    fill one are pooled with the other buildings' leftovers and packed
    together. Every crossing then lands in one of those few tail charts
    instead of being spread about -- which is what the schedulers do by hand,
    and it is the better bargain: a housekeeper is a shift, a crossing is
    minutes.
    """
    placed, unplaced = [], []
    for r in rooms:
        (placed if loc_of(r) else unplaced).append(r)

    out = []
    by_bld = collections.defaultdict(list)
    for r in placed:
        by_bld[loc_of(r).bld].append(r)

    leftovers = []
    for bld in sorted(by_bld, key=lambda b: BORD.get(b, 9)):
        rs = by_bld[bld]
        if pool_leftovers:
            # only the charts this building can fill by itself; whatever will
            # not make a full one goes into the shared pool
            rs, spare = _fill_whole(rs, cap, loc_of)
            leftovers += spare
            if not rs:
                continue
        n = max(_bins_needed(rs, cap), math.ceil(sum(r["time"] for r in rs) / cap))
        bins = [[] for _ in range(n)]
        load = [0.0] * n
        floors_in = [set() for _ in range(n)]

        by_floor = collections.defaultdict(list)
        for r in rs:
            by_floor[loc_of(r).level].append(r)

        # Elevation order, and along the corridor within a floor, so a chart
        # that does take two floors takes neighbouring ones.
        from property_map import LEVEL_IX
        for lv in sorted(by_floor, key=lambda lv: LEVEL_IX[lv]):
            for r in sorted(by_floor[lv], key=lambda r: loc_of(r).x):
                fits = [i for i in range(n) if load[i] + r["time"] <= cap]
                if not fits:
                    # nothing has room: open one rather than break the cap
                    bins.append([]); load.append(0.0); floors_in.append(set())
                    fits = [len(bins) - 1]
                same = [i for i in fits if lv in floors_in[i]]
                if same:
                    # already on this floor: the fullest, so it closes out
                    pick = max(same, key=lambda i: load[i])
                else:
                    # Otherwise the nearest floor, then the emptiest. Counting
                    # floors alone treats Plaza-and-4 as no worse than 2-and-3,
                    # and it is: one is a lift ride past three landings, the
                    # other is a staircase. Distance first, capacity second.
                    here = LEVEL_IX[lv]
                    def _reach(i):
                        if not floors_in[i]:
                            return 0
                        return min(abs(LEVEL_IX[f] - here) for f in floors_in[i])
                    pick = min(fits, key=lambda i: (_reach(i), load[i]))
                bins[pick].append(r)
                load[pick] += r["time"]
                floors_in[pick].add(lv)
        out += [b for b in bins if b]

    if leftovers:
        # The tail. Packed largest-first so the crossings land in as few charts
        # as they can, and ordered west to east so a chart that does cross takes
        # neighbouring buildings rather than 2 and 3, which do not touch.
        leftovers.sort(key=lambda r: (BORD.get(loc_of(r).bld, 9)
                                      if loc_of(r) else 9, -r["time"]))
        cur, t = [], 0.0
        for r in leftovers:
            if cur and t + r["time"] > cap:
                out.append(cur); cur, t = [], 0.0
            cur.append(r); t += r["time"]
        if cur:
            out.append(cur)

    # Building-pure is not free every day. Each building rounds its own minutes
    # up to a whole person, and those part-people add up: over every stored day
    # it would cost about one extra housekeeper a day. A crossing costs some
    # minutes of walking; a housekeeper costs a shift. So the charts are merged
    # back down to the headcount the day would have used anyway, cheapest
    # crossing first -- and on a day where building-pure already fits, nothing
    # is merged and nobody crosses at all.
    if target is not None:
        out = _merge_to(out, target, cap, loc_of)

    if unplaced:
        cur, t = [], 0.0
        for r in unplaced:
            if cur and t + r["time"] > cap:
                out.append(cur); cur, t = [], 0.0
            cur.append(r); t += r["time"]
        if cur:
            out.append(cur)
    return out


def _fill_whole(rs, cap, loc_of):
    """Split a building's rooms into the charts it can fill, and the rest.

    "Can fill" is measured in minutes rather than guessed: a building with
    5,260 minutes fills thirteen charts of 380 outright and has 320 left, and
    it is those 320 that are worth pooling rather than spending a whole
    housekeeper on.
    """
    total = sum(r["time"] for r in rs)
    whole = int(total // cap)
    if whole < 1:
        return [], list(rs)
    from property_map import LEVEL_IX
    order = sorted(rs, key=lambda r: (LEVEL_IX[loc_of(r).level], loc_of(r).x)
                   if loc_of(r) else (99, 0))
    keep, spare, cur, t, made = [], [], [], 0.0, 0
    for r in order:
        if made >= whole:
            spare.append(r)
            continue
        if cur and t + r["time"] > cap:
            keep += cur; made += 1; cur, t = [], 0.0
            if made >= whole:
                spare.append(r)
                continue
        cur.append(r); t += r["time"]
    if cur:
        if made < whole:
            keep += cur
        else:
            spare += cur
    return keep, spare


def _hops(blds):
    """Bridges anyone on a chart must cross: 0, 1 or 2, straight off the map."""
    from property_map import BRIDGES
    bs = sorted(b for b in blds if b in (1, 2, 3))
    worst = 0
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            worst = max(worst, 1 if BRIDGES.get(frozenset((bs[i], bs[j]))) else 2)
    return worst


def _merge_to(charts, target, cap, loc_of):
    """Combine charts until there are no more than `target`, cheapest first.

    Cheapest means fewest bridges crossed, then fewest buildings, then the
    fullest result -- so the crossings that do happen are between neighbours
    and land in as few charts as possible instead of being spread about.
    """
    items = [[c, {loc_of(r).bld for r in c if loc_of(r)},
              sum(r["time"] for r in c)] for c in charts]
    while len(items) > max(target, 1):
        best = None
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i][2] + items[j][2] > cap:
                    continue
                merged = items[i][1] | items[j][1]
                key = (_hops(merged), len(merged), -(items[i][2] + items[j][2]))
                if best is None or key < best[0]:
                    best = (key, i, j)
        if best is None:
            break                     # nothing else fits under the cap
        _, i, j = best
        items[i][0] = items[i][0] + items[j][0]
        items[i][1] |= items[j][1]
        items[i][2] += items[j][2]
        items.pop(j)

    if len(items) > max(target, 1):
        items = _dissolve_to(items, target, cap, loc_of)
    return [it[0] for it in items]


def _dissolve_to(items, target, cap, loc_of):
    """Empty the lightest charts a room at a time when whole ones will not pair.

    Two remainders of three hundred minutes cannot merge under a cap of three
    hundred and eighty, but their rooms can be dealt out among the charts that
    have space. Each room goes to the chart that stays in its own building if
    one has room, and otherwise the fewest bridges away -- so a chart that does
    end up crossing takes one or two rooms, not half a corridor.
    """
    while len(items) > max(target, 1):
        light = min(range(len(items)), key=lambda i: items[i][2])
        moving = sorted(items[light][0], key=lambda r: -r["time"])
        plan = []
        loads = {i: items[i][2] for i in range(len(items)) if i != light}
        for r in moving:
            home = loc_of(r).bld if loc_of(r) else None
            fits = [i for i in loads if loads[i] + r["time"] <= cap]
            if not fits:
                plan = None
                break
            pick = min(fits, key=lambda i: (_hops(items[i][1] | ({home} if home else set())),
                                            len(items[i][1] | ({home} if home else set())),
                                            -loads[i]))
            plan.append((r, pick))
            loads[pick] += r["time"]
        if plan is None:
            break                     # the day genuinely needs this many people
        for r, pick in plan:
            items[pick][0].append(r)
            items[pick][2] += r["time"]
            if loc_of(r):
                items[pick][1].add(loc_of(r).bld)
        items.pop(light)
    return items


def pack_by_floor(rooms, cap, loc_of):
    """Charts that read down the building: one floor, or two touching ones.

    Each building's floors are walked in order and charts filled as they go, so
    a chart holds one corridor, or the tail of one and the head of the floor
    directly above it -- never two floors with others in between. That is what
    "scattered" means to somebody carrying a cart: two floors is a staircase,
    Plaza-and-4 is a lift ride past three landings.

    A second pass then combines any two charts that sit on touching floors of
    the same building and fit together, which buys back most of the people that
    filling strictly in order would otherwise cost.
    """
    from property_map import LEVEL_IX
    by_b = collections.defaultdict(list)
    unplaced = []
    for r in rooms:
        (by_b[loc_of(r).bld].append(r) if loc_of(r) else unplaced.append(r))

    out = []
    for b in sorted(by_b, key=lambda x: BORD.get(x, 9)):
        rs = sorted(by_b[b], key=lambda r: (LEVEL_IX[loc_of(r).level], loc_of(r).x))
        cur, t = [], 0.0
        for r in rs:
            if cur and t + r["time"] > cap:
                out.append(cur)
                cur, t = [], 0.0
            cur.append(r)
            t += r["time"]
        if cur:
            out.append(cur)

    def _levels(c):
        return {LEVEL_IX[loc_of(r).level] for r in c if loc_of(r)}

    def _blds(c):
        return {loc_of(r).bld for r in c if loc_of(r)}

    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if sum(r["time"] for r in out[i]) + sum(r["time"] for r in out[j]) > cap:
                    continue
                if _blds(out[i]) != _blds(out[j]):
                    continue          # never across buildings here
                lv = _levels(out[i]) | _levels(out[j])
                if lv and max(lv) - min(lv) > 1:
                    continue          # only floors that touch
                out[i] = out[i] + out[j]
                out.pop(j)
                merged = True
                break
            if merged:
                break

    if unplaced:
        cur, t = [], 0.0
        for r in unplaced:
            if cur and t + r["time"] > cap:
                out.append(cur); cur, t = [], 0.0
            cur.append(r); t += r["time"]
        if cur:
            out.append(cur)
    return out
