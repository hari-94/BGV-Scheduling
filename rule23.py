"""
rule23.py — the hard rule: in Full Clean, nobody works building 2 AND building 3.

Buildings 2 and 3 don't touch -- building 1 is the only way between them --
so one person with Full Clean rooms in both walks the whole property twice.
A single chart has never been allowed to mix them (fcpack._legal); this is the
same rule for a PERSON across all their Full Clean charts, housekeeper or
RQS. Daily Service and Dust n Vac are exempt: those rounds cover the whole
property by design.

One place states it, every step uses it:
  * the Schedule page's assign_inspectors refuses to merge or swap inspector
    rounds into a 2+3 mix, and `repair_inspectors` fixes any that remain;
  * the daily sheet's light-chart suggestions never propose one;
  * Preview/Push check the sheet as edited (`violations`) and say so.

No Streamlit here.
"""

FULL_CLEAN = ("full clean",)             # Full Clean and Full Clean (IH)


def _is_fc(service) -> bool:
    return str(service or "").strip().lower().startswith(FULL_CLEAN)


def _bld(room) -> str:
    return str(room or "").strip()[:1]


def mixes(blds) -> bool:
    """True when a set of buildings holds both 2 and 3 (ints or strings)."""
    s = {str(b) for b in blds}
    return "2" in s and "3" in s


def violations(rows, who_col, service_col="Service", room_col="Room"):
    """{person: sorted buildings} for everyone with Full Clean rooms in both
    2 and 3. `rows` are dicts (a sheet's rows or a push plan's lines)."""
    seen = {}
    for r in rows:
        if not _is_fc(r.get(service_col)):
            continue
        p = str(r.get(who_col) or "").strip()
        if not p or p.lower().startswith(("no hk", "need housekeeper", "rqs 2", "inspector ")):
            continue
        seen.setdefault(p, set()).add(_bld(r.get(room_col)))
    return {p: sorted(b) for p, b in seen.items() if mixes(b)}


def chart_blds(g):
    return {int(b) for b in (g.get("blds") or []) if str(b).isdigit()} or \
        {int(_bld(r.get("room"))) for r in g.get("rooms") or [] if _bld(r.get("room")).isdigit()}


def repair_inspectors(groups, free_inspectors=(), room_max=13):
    """Make every inspector's Full Clean charts sit on one side of the 2/3 line.

    For an inspector who has both, the charts on the smaller side move: to an
    inspector already on that side with room to spare (fewest rooms first),
    else to a free inspector, else to a new "Inspector N" slot -- the same
    placeholder the page uses when it runs out of people. Returns a list of
    (chart label, from, to) moves. Mutates groups' "inspector"."""
    def fc(g):
        return _is_fc(g.get("service_type")) and not g.get("verify_group")

    def load(name):
        return sum(len(g.get("rooms") or []) for g in groups if g.get("inspector") == name)

    def sides(name):
        s = set()
        for g in groups:
            if g.get("inspector") == name and fc(g):
                s |= chart_blds(g)
        return s

    free = [n for n in free_inspectors if n and not any(g.get("inspector") == n for g in groups)]
    moves = []
    names = sorted({g.get("inspector") for g in groups if g.get("inspector") and fc(g)})
    for name in names:
        mine = [g for g in groups if g.get("inspector") == name and fc(g)]
        if not mixes(sides(name)):
            continue
        rooms2 = sum(len(g["rooms"]) for g in mine if 2 in chart_blds(g))
        rooms3 = sum(len(g["rooms"]) for g in mine if 3 in chart_blds(g))
        move_side = 2 if rooms2 <= rooms3 else 3
        other = 3 if move_side == 2 else 2
        for g in [g for g in mine if move_side in chart_blds(g)]:
            n = len(g["rooms"])
            cands = sorted((x for x in {h.get("inspector") for h in groups if fc(h)}
                            if x and x != name and other not in sides(x)
                            and move_side in sides(x) and load(x) + n <= room_max),
                           key=load)
            if cands:
                to = cands[0]
            elif free:
                to = free.pop(0)
            else:
                k = 1
                while any(h.get("inspector") == f"Inspector {k}" for h in groups):
                    k += 1
                to = f"Inspector {k}"
            g["inspector"] = to
            moves.append((g.get("label", "?"), name, to))
    return moves
