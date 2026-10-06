"""Full Clean charts for one building, solved exactly rather than searched for.

`fcpack.pack` and the passes after it are local search: they move or swap one
apartment at a time and stop when no single move helps. That leaves people on
the table. Lifting a short chart usually needs a chain -- A gives to B, B gives
to C -- and no pairwise trade can see one. Measured on 30 sample days the
heuristic used 894 housekeeper-days where 875 was provably enough under the
very same rules, and was 1-2 people over on 14 of the 30.

This states the problem to a constraint solver (OR-Tools CP-SAT) and asks for
the answer, in three steps, each holding the one before it fixed:

  1. the fewest charts -- a chart is a shift;
  2. at that count, the fewest charts under LOW_MIN -- a short chart is
     somebody sent home at two o'clock;
  3. at both, the nearest-together day: fewest levels spanned, fewest floors
     touched, the least corridor walked on a floor, and a short chart that is
     left anyway topped up as far as nearby rooms allow. The 120+70+70+70
     shape is avoided here too, at no cost to anything above it.

The hard rules are fcpack's, unchanged: the cap, one 140, a 140 beside at most
one 120, apartments never split (the solver places `fcpack.bundles`, never
loose rooms). Buildings 2 and 3 cannot meet because the caller hands this one
building at a time.

The heuristic's own answer goes in as the starting point, so the solver can
only ever match or beat it; and the caller audits what comes back and keeps
the heuristic's charts if anything is wrong. No Streamlit, no database --
testable alone, like fcpack.
"""
import fcpack

# Step 3's prices, in rough minutes-of-walking. Read them as ratios: a level of
# span costs as much as topping a short chart up by 60 minutes, so a short
# chart is filled from its own floor or the next one, not from across the
# building. That is what "filled with nearby rooms" means.
W_SPAN = 60          # per level between a chart's top and bottom floor
W_FLOOR = 20         # per extra floor touched
W_DOOR = 3           # per door-width of corridor on one floor
W_EASY = 40          # a 120+70+70+70 chart
W_DEFICIT = 1        # per minute a short chart sits under LOW_MIN

# Time limits. Deterministic time makes the same sheet give the same charts on
# any machine; the wall-clock limit is only a guard for a slow host. Steps 1
# and 2 usually prove optimal in well under a second. Step 3 never proves and
# runs to its limit. Where steps 1-2 kept the heuristic's count it has little
# left to find by 2.5; where they saved a person the layout can still be
# scattered, which is why the caller polishes with _fc_tighten afterwards.
STEP_DET = (6.0, 6.0, 2.5)
STEP_WALL = (4.0, 4.0, 3.5)
WORKERS = 4


def _chart_of_hint(buns, hint):
    """Which hint chart each bundle starts in, or None if the hint is unusable."""
    if not hint:
        return None
    seat = {}
    for j, chart in enumerate(hint):
        for r in chart:
            seat[str(r.get("room"))] = j
    out = []
    for b in buns:
        j = seat.get(str(b.rooms[0].get("room")))
        if j is None:
            return None
        out.append(j)
    return out


def pack(rooms, cap, loc_of, low_min, hint=None):
    """Exact Full Clean charts for one building's rooms.

    Returns a list of charts (lists of room dicts), or raises -- the caller
    keeps its own charts on any exception. `hint` is the heuristic's charts for
    the same rooms; its length is the most charts the solver may use.
    """
    from ortools.sat.python import cp_model

    if any(loc_of(r) is None for r in rooms):
        raise ValueError("a room the plans cannot place")
    buns = fcpack.bundles(rooms, cap, loc_of)
    n = len(buns)
    if n == 0:
        return []
    start = _chart_of_hint(buns, hint)
    K = len(hint) if hint else n
    if start is not None and max(start) >= K:
        start = None

    T = [b.time for b in buns]
    L = [min(b.levels) for b in buns]
    X = [int(round(b.x)) for b in buns]
    levels = sorted(set(L))
    xmax = max(X) + 1
    # Room counts by size, for the 120+70+70+70 shape. A bundle can hold more
    # than one room, so count rooms, not bundles.
    c70 = [sum(1 for r in b.rooms if r.get("time") == 70) for b in buns]
    c120 = [b.n120 for b in buns]
    c140 = [b.n140 for b in buns]
    other = [len(b.rooms) - c70[i] - c120[i] - c140[i] for i, b in enumerate(buns)]

    m = cp_model.CpModel()
    x = {(i, j): m.NewBoolVar("x%d_%d" % (i, j)) for i in range(n) for j in range(K)}
    y = [m.NewBoolVar("y%d" % j) for j in range(K)]
    for i in range(n):
        m.AddExactlyOne(x[i, j] for j in range(K))

    t, short, deficit, near, easy = [], [], [], [], []
    for j in range(K):
        tj = sum(T[i] * x[i, j] for i in range(n))
        t.append(tj)
        m.Add(tj <= cap * y[j])
        for i in range(n):
            m.AddImplication(x[i, j], y[j])
        h140 = sum(c140[i] * x[i, j] for i in range(n))
        n120 = sum(c120[i] * x[i, j] for i in range(n))
        m.Add(h140 <= 1)
        # a 140 beside at most one 120. h140 is 0 or 1, and no chart can hold
        # more than cap // 120 of them, so this binds only when a 140 is there.
        big = max(1, cap // 120)
        m.Add(n120 + big * h140 <= 1 + big)

        # short: under low_min. deficit is how far under, 0 when not short.
        s = m.NewBoolVar("s%d" % j)
        d = m.NewIntVar(0, low_min, "d%d" % j)
        m.Add(tj >= low_min).OnlyEnforceIf([y[j], s.Not()])
        m.Add(d >= low_min * y[j] - tj)
        m.Add(d <= low_min * s)
        short.append(s)
        deficit.append(d)

        # where the chart is: levels touched, span between them, corridor
        f = {l: m.NewBoolVar("f%d_%d" % (j, l)) for l in levels}
        for i in range(n):
            m.AddImplication(x[i, j], f[L[i]])
        for l in levels:      # a floor counts only if something is on it
            m.AddBoolOr([x[i, j] for i in range(n) if L[i] == l] + [f[l].Not()])
        lo = m.NewIntVar(min(levels), max(levels), "lo%d" % j)
        hi = m.NewIntVar(min(levels), max(levels), "hi%d" % j)
        for l in levels:
            m.Add(hi >= l).OnlyEnforceIf(f[l])
            m.Add(lo <= l).OnlyEnforceIf(f[l])
        sp = m.NewIntVar(0, max(levels) - min(levels), "sp%d" % j)
        m.Add(sp >= hi - lo)
        cost = W_SPAN * sp + W_FLOOR * sum(f.values())
        for l in levels:
            here = [i for i in range(n) if L[i] == l]
            if len(here) < 2:
                continue
            xl = m.NewIntVar(0, xmax, "")
            xh = m.NewIntVar(0, xmax, "")
            for i in here:
                m.Add(xh >= X[i]).OnlyEnforceIf(x[i, j])
                m.Add(xl <= X[i]).OnlyEnforceIf(x[i, j])
            w = m.NewIntVar(0, xmax, "")
            m.Add(w >= xh - xl)
            cost += W_DOOR * w
        near.append(cost)

        # 120+70+70+70: exactly one 120, three 70s, nothing else
        e = m.NewBoolVar("e%d" % j)
        k70 = sum(c70[i] * x[i, j] for i in range(n))
        kot = sum((other[i] + c140[i]) * x[i, j] for i in range(n))
        is120 = _reify_eq(m, n120, 1)
        is70 = _reify_eq(m, k70, 3)
        none = _reify_eq(m, kot, 0)
        m.AddBoolOr([is120.Not(), is70.Not(), none.Not(), e])
        easy.append(e)

    for j in range(K - 1):
        m.Add(y[j] >= y[j + 1])

    if start is not None:
        # the heuristic's charts, renumbered so the used ones come first
        order = sorted(set(start))
        ren = {old: new for new, old in enumerate(order)}
        for i in range(n):
            for j in range(K):
                m.AddHint(x[i, j], 1 if ren[start[i]] == j else 0)
        for j in range(K):
            m.AddHint(y[j], 1 if j < len(order) else 0)

    sv = cp_model.CpSolver()
    sv.parameters.num_workers = WORKERS
    sv.parameters.interleave_search = True

    def run(step, objective):
        m.Minimize(objective)
        sv.parameters.max_deterministic_time = STEP_DET[step]
        sv.parameters.max_time_in_seconds = STEP_WALL[step]
        st = sv.Solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError("no solution at step %d (%s)" % (step + 1, sv.StatusName(st)))
        # carry the answer forward as the next step's starting point
        m.ClearHints()
        for v in list(x.values()) + y:
            m.AddHint(v, sv.Value(v))
        return int(round(sv.ObjectiveValue()))

    count = run(0, sum(y))
    m.Add(sum(y) <= count)
    shorts = run(1, sum(short))
    m.Add(sum(short) <= shorts)
    run(2, sum(near) + W_EASY * sum(easy) + W_DEFICIT * sum(deficit))

    charts = [[r for i in range(n) if sv.Value(x[i, j]) for r in buns[i].rooms]
              for j in range(K)]
    return [c for c in charts if c]


def _reify_eq(m, expr, k):
    b = m.NewBoolVar("")
    m.Add(expr == k).OnlyEnforceIf(b)
    m.Add(expr != k).OnlyEnforceIf(b.Not())
    return b

