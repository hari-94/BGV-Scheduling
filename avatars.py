"""
avatars.py — the little people on the Property page, each where they last were.

**One avatar per person, at the room they marked last** (`place_people`,
Hari 19 Nov). Drawing one per room put Grace Vargas at fourteen doors at
once -- she started fourteen rooms in one minute -- and a person who is
everywhere tells you nothing. A person's last mark is the latest of their
started / cleaned times on any room (the HK side) and inspected time (the
RQS side), so somebody who is both counts once. What they are doing is that
mark: vacuuming for a start, cheering for a finish, a thumbs up for an
inspection, waving for help.

Every action is one SVG strip of FRAMES frames side by side, so the 3-D model
(a three.js sprite stepping its texture offset) and the 2-D plan (a CSS
background stepping its position) animate the very same drawing.

**A person's look is set, never guessed.** `avatar_look` in app_settings maps
a name to "f" (woman), "m" (man) or "n" (neutral), and anyone not in it is
drawn neutral. Reading it off a first name would get people wrong on a
bilingual team, and a wrong one on a page managers show around is worse than
a neutral one.

No Streamlit here, so the drawing can be checked on its own.
"""
import datetime as _dt
import functools

import roomstatus as _rst

W, H, FRAMES = 96, 128, 4

SKIN, SKIN_D = "#d6a07a", "#b9845f"
HAIR = "#2a211d"
INK = "#1f2937"
PANTS, SHOE, TIGHTS = "#334155", "#1f2937", "#3b3b45"
APRON = "#f8fafc"
#: housekeepers in the teal of the uniform, RQS in navy, so the two read apart
#: at a distance before anyone reads a name tag
UNIFORM = {"hk": ("#0f766e", "#0b5a54"), "rqs": ("#1e3a8a", "#172c66")}

SETTING_KEY = "avatar_look"
LOOKS = {"f": "Woman", "m": "Man", "n": "Neutral"}

#: no person at all, just the sparkle of a room that needed nothing
PERSONLESS = ("shine",)
#: the order the legend lists them in; the last two are the whole team's
#: people who have marked nothing yet
ORDER = ("clean", "cheer", "pass", "help", "dnd", "later", "refused",
         "wait", "onway")
LIVE = ORDER[:-2]

#: a housekeeper's own mark, read off the room's status. A room the RQS has
#: since passed was, for the housekeeper, a finish.
HK_ACTION = {
    _rst.STARTED: "clean",
    _rst.DONE: "cheer", _rst.OCCUPIED_CLEANED: "cheer",
    _rst.TO_BE_INSPECTED: "cheer", _rst.INSPECTED: "cheer",
    _rst.DND: "dnd", _rst.RETURN_LATER: "later",
    _rst.SERVICE_REFUSED: "refused", _rst.HELP: "help",
}

#: the colour of each action's name tag -- the status colour it stands for
ACT_COLOUR = {
    "clean": _rst.META[_rst.STARTED][2], "cheer": _rst.META[_rst.DONE][2],
    "pass": _rst.META[_rst.INSPECTED][2], "help": _rst.META[_rst.HELP][2],
    "dnd": _rst.META[_rst.DND][2], "later": _rst.META[_rst.RETURN_LATER][2],
    "refused": _rst.META[_rst.SERVICE_REFUSED][2],
    "wait": _rst.META[_rst.PENDING][2], "onway": _rst.META[_rst.TO_BE_INSPECTED][2],
}


# ── where everybody is ──────────────────────────────────────────────────────
#: HotSOS has sent start times hours ahead of the clock (DND rooms, 19 Nov:
#: 14:08 and 14:49 at 12:13). A mark from the future is not a last mark.
_FUTURE_SLACK = _dt.timedelta(minutes=5)


def _when(raw, now):
    if not raw:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return None if t > now + _FUTURE_SLACK else t


def _same(a, b) -> bool:
    """One person under two spellings: 'Amalia H.' on a chart, 'Amalia
    Hernandez' off HotSOS."""
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def place_people(statuses: dict, today: dict, now, whole_team=False) -> list:
    """One entry per person: the room of their latest mark and what it was.

    statuses -- room -> room_status row; today -- room -> the day's chart for
    that room ({"hk", "rqs"}), in chart order. Only rooms on today's charts
    count. With `whole_team`, everyone on a chart who has marked nothing yet
    is put at their first room: a housekeeper waiting by the cart, an RQS on
    the way.

    The fallback to `updated_at` is only for a room with no times of its own:
    the mirror rewrites it for whole batches at once, so as a first choice
    it would put everybody at whichever room the last batch touched.
    """
    best = {}

    def offer(name, t, code, act, role):
        if not is_person(name) or t is None:
            return
        n = _norm(name)
        k = next((k for k in best if _same(k, n)), n)
        if k not in best or t > best[k]["t"]:
            best[k] = {"name": name, "t": t, "code": code, "act": act, "role": role}

    for code, rec in statuses.items():
        if code not in today:
            continue
        st = _rst.normalise(rec.get("status"))
        day = today[code] or {}
        act = HK_ACTION.get(st)
        if act:
            stamps = [_when(rec.get(c), now)
                      for c in ("started_at", "cleaned_at", "marked_clean_at")]
            t = max((s for s in stamps if s), default=None) \
                or _when(rec.get("updated_at"), now)
            offer(rec.get("housekeeper") or day.get("hk"), t, code, act, "hk")
        if st == _rst.INSPECTED:
            t = _when(rec.get("inspected_at"), now) or _when(rec.get("updated_at"), now)
            offer(rec.get("inspector") or day.get("rqs"), t, code, "pass", "rqs")

    if whole_team:
        for code, day in today.items():
            for name, act, role in ((day.get("hk"), "wait", "hk"),
                                    (day.get("rqs"), "onway", "rqs")):
                if not is_person(name):
                    continue
                n = _norm(name)
                if not any(_same(k, n) for k in best):
                    best[n] = {"name": name, "t": None, "code": code,
                               "act": act, "role": role}
    return list(best.values())


# ── who looks like what ─────────────────────────────────────────────────────
def _norm(s) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalpha())


def is_person(name) -> bool:
    """A real name, not the scheduler's placeholder for an unstaffed chart."""
    n = str(name or "").strip()
    low = n.lower()
    return bool(n) and not (low.startswith("need housekeeper")
                            or low.startswith("no hk") or low == "unassigned")


def look_of(looks: dict, name) -> str:
    """'f', 'm' or 'n' for a name, from the stored looks.

    Exact match first; then one stored name being the start of the other
    ("Maricruz" and "Maricruz G."), but only when exactly one stored name
    answers -- two Luises must not share a look by accident.
    """
    if not looks or not is_person(name):
        return "n"
    n = _norm(name)
    for k, v in looks.items():
        if _norm(k) == n:
            return v if v in LOOKS else "n"
    hits = [v for k, v in looks.items()
            if _norm(k) and (_norm(k).startswith(n) or n.startswith(_norm(k)))]
    return hits[0] if len(hits) == 1 and hits[0] in LOOKS else "n"


def short_name(name) -> str:
    """'Maricruz G.' for 'Maricruz Garcia' -- a tag, not a roll call."""
    if not is_person(name):
        return ""
    parts = str(name).split("·")[0].split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1][0]}."
    return parts[0] if parts else ""


# ── drawing ─────────────────────────────────────────────────────────────────
def _arm(sx, sy, hx, hy, col):
    # elbow bowed outward from the body, so arms read as arms and not sticks
    ex = (sx + hx) / 2 + (-4 if hx < 48 else 4)
    ey = (sy + hy) / 2 + 3
    return (f'<path d="M{sx} {sy} Q{ex} {ey} {hx} {hy}" stroke="{col}" '
            f'stroke-width="6.5" stroke-linecap="round" fill="none"/>'
            f'<circle cx="{hx}" cy="{hy}" r="3.3" fill="{SKIN}"/>')


def _star(cx, cy, r, col, op=1.0):
    q = r * 0.32
    return (f'<path d="M{cx} {cy - r} Q{cx + q} {cy - q} {cx + r} {cy} '
            f'Q{cx + q} {cy + q} {cx} {cy + r} Q{cx - q} {cy + q} {cx - r} {cy} '
            f'Q{cx - q} {cy - q} {cx} {cy - r}Z" fill="{col}" opacity="{op}"/>')


def _char(look, role, hl, hr, dx=0, dy=0, feet=((0, 0), (0, 0)),
          mouth="smile", worried=False):
    """One person, facing out. hl/hr are the hands in the person's own frame
    (shoulders at 38,57 and 58,57; feet near y 118)."""
    col, dark = UNIFORM[role]
    s = [f'<g transform="translate({dx} {dy})">']
    if look == "f":   # long hair, behind the head and down to the shoulders
        s.append(f'<path d="M33 38 Q32 21 48 21 Q64 21 63 38 L63 53 Q58 56 55 50 '
                 f'L41 50 Q38 56 33 53Z" fill="{HAIR}"/>')
    # legs
    (lx, ll), (rx, rl) = feet
    if look == "f":
        for x, ox, lift in ((44, lx, ll), (52, rx, rl)):
            s.append(f'<path d="M{x} 98 L{x + ox} {116 - lift}" stroke="{TIGHTS}" '
                     f'stroke-width="4.5" stroke-linecap="round"/>'
                     f'<ellipse cx="{x + ox}" cy="{118 - lift}" rx="4.6" ry="2.8" fill="{SHOE}"/>')
    else:
        for x, ox, lift in ((44, lx, ll), (52, rx, rl)):
            s.append(f'<path d="M{x} 86 L{x + ox} {115 - lift}" stroke="{PANTS}" '
                     f'stroke-width="7" stroke-linecap="round"/>'
                     f'<ellipse cx="{x + ox}" cy="{118 - lift}" rx="5" ry="3" fill="{SHOE}"/>')
    # body
    if look == "f":
        s.append(f'<rect x="37" y="51" width="22" height="26" rx="9" fill="{col}"/>'
                 f'<path d="M38 72 L58 72 L64 101 Q48 105 32 101Z" fill="{col}"/>')
        if role == "hk":
            s.append(f'<rect x="40.5" y="63" width="15" height="31" rx="3" '
                     f'fill="{APRON}" opacity=".93"/>')
    else:
        s.append(f'<rect x="37" y="51" width="22" height="38" rx="8" fill="{col}"/>')
        if role == "hk":
            s.append(f'<rect x="41" y="63" width="14" height="23" rx="3" '
                     f'fill="{APRON}" opacity=".93"/>')
    if role == "rqs":   # collar and a lanyard badge
        s.append('<path d="M44 51 L48 58 L52 51" stroke="#fff" stroke-width="2" fill="none"/>'
                 '<rect x="50" y="64" width="5" height="7" rx="1" fill="#fff"/>')
    s.append(_arm(38, 57, *hl, col) + _arm(58, 57, *hr, col))
    # head
    s.append(f'<rect x="45" y="46" width="6" height="7" fill="{SKIN_D}"/>'
             f'<circle cx="48" cy="37" r="13" fill="{SKIN}"/>'
             f'<circle cx="43.5" cy="38" r="1.7" fill="{INK}"/>'
             f'<circle cx="52.5" cy="38" r="1.7" fill="{INK}"/>'
             '<circle cx="41" cy="42.5" r="2.2" fill="#f472b6" opacity=".3"/>'
             '<circle cx="55" cy="42.5" r="2.2" fill="#f472b6" opacity=".3"/>')
    if worried:
        s.append(f'<path d="M41 33.5 L45.5 32.5 M51 32.5 L55.5 33.5" stroke="{INK}" '
                 f'stroke-width="1.3" stroke-linecap="round"/>')
    s.append({
        "smile": f'<path d="M44.5 43.5 Q48 47 51.5 43.5" stroke="{INK}" '
                 f'stroke-width="1.4" fill="none" stroke-linecap="round"/>',
        "open": '<path d="M44 43 Q48 50 52 43Z" fill="#7f1d1d"/>',
        "o": '<ellipse cx="48" cy="45" rx="1.8" ry="2.4" fill="#7f1d1d"/>',
        "flat": f'<path d="M45 44.5 L51 44.5" stroke="{INK}" stroke-width="1.4" '
                f'stroke-linecap="round"/>',
    }[mouth])
    # hair, front
    if look == "f":
        s.append(f'<path d="M35 35 Q37 22.5 48 22.5 Q59 22.5 61 35 Q56 28 48 29.5 '
                 f'Q40 28 35 35Z" fill="{HAIR}"/>'
                 f'<path d="M41.5 36.6 L40.6 35.7 M54.5 36.6 L55.4 35.7" stroke="{INK}" '
                 f'stroke-width="1"/>')
    elif look == "m":
        s.append(f'<path d="M35 36 Q34 22 48 22.5 Q62 22 61 36 Q60 29 55 28 '
                 f'Q48 26 41 28.5 Q36 30 35 36Z" fill="{HAIR}"/>')
    else:            # a cap in the uniform colour
        s.append(f'<rect x="35" y="33" width="3" height="7" fill="{HAIR}"/>'
                 f'<rect x="58" y="33" width="3" height="7" fill="{HAIR}"/>'
                 f'<path d="M34.5 34 Q35 21 48 21 Q61 21 61.5 34Z" fill="{dark}"/>'
                 f'<path d="M33 33.5 L65 33.5 Q67 36.5 63 36.5 L33 36.5Z" fill="{dark}"/>')
    s.append('</g>')
    return "".join(s)


def _clipboard(dx=0, dy=0):
    return (f'<g transform="translate({dx} {dy})">'
            '<rect x="26" y="60" width="17" height="22" rx="2" fill="#a16207"/>'
            '<rect x="28" y="63" width="13" height="17" fill="#fff"/>'
            '<path d="M30 67 H39 M30 71 H39 M30 75 H36" stroke="#94a3b8" stroke-width="1.2"/>'
            '<rect x="31" y="58.5" width="7" height="3" rx="1" fill="#475569"/></g>')


def _frame(look, action, i):
    """The SVG body of frame i (0..FRAMES-1) of one action."""
    walk = [((-3, 4), (3, 0)), ((0, 0), (0, 0)), ((-3, 0), (3, 4)), ((0, 0), (0, 0))][i]
    bob = [0, -1, 0, -1][i]
    p = ['<ellipse cx="48" cy="121" rx="18" ry="4" fill="#0f172a" opacity=".16"/>']

    if action == "wait":       # beside the cart, tapping a foot
        p.append('<rect x="64" y="76" width="24" height="34" rx="3" fill="#e2e8f0" '
                 'stroke="#64748b" stroke-width="1.5"/>'
                 '<path d="M64 88 H88 M64 99 H88" stroke="#94a3b8" stroke-width="1.3"/>'
                 '<rect x="67" y="79" width="8" height="7" rx="1.5" fill="#fff" stroke="#cbd5e1"/>'
                 '<rect x="77" y="80" width="8" height="6" rx="1.5" fill="#93c5fd"/>'
                 '<rect x="68" y="91" width="4" height="7" rx="1" fill="#22c55e"/>'
                 '<rect x="74" y="91" width="4" height="7" rx="1" fill="#f59e0b"/>'
                 '<path d="M64 80 L59 73" stroke="#64748b" stroke-width="2.5" stroke-linecap="round"/>'
                 '<circle cx="68" cy="112" r="3" fill="#475569"/><circle cx="84" cy="112" r="3" fill="#475569"/>')
        tap = ((0, 3), (0, 0)) if i % 2 else ((0, 0), (0, 0))
        p.append(_char(look, "hk", (34, 80), (69, 74), dx=-10, feet=tap))

    elif action == "clean":    # vacuuming, the head sweeping side to side
        vx = [72, 80, 88, 80][i]
        p.append(f'<path d="M66 70 L{vx} 112" stroke="#475569" stroke-width="2.6"/>'
                 f'<path d="M{66 + (vx - 66) * .3:.1f} {70 + 42 * .3:.1f} '
                 f'L{66 + (vx - 66) * .75:.1f} {70 + 42 * .75:.1f}" stroke="#fbbf24" '
                 f'stroke-width="8" stroke-linecap="round"/>'
                 f'<rect x="{vx - 10}" y="111" width="20" height="7" rx="2.5" fill="#e89611"/>'
                 f'<circle cx="{vx + 13}" cy="{113 - (i % 2) * 3}" r="{2 + (i % 2)}" '
                 f'fill="#cbd5e1" opacity=".8"/>'
                 f'<circle cx="{vx + 17}" cy="{109 + (i % 2) * 2}" r="1.6" fill="#cbd5e1" opacity=".6"/>')
        p.append(_char(look, "hk", (72, 72), (74, 70), dx=-8, dy=-bob))

    elif action == "cheer":    # done: a jump, arms up, sparkles
        up = i % 2 == 0
        hands = ((30, 24), (66, 24)) if up else ((31, 41), (65, 41))
        stars = ([(18, 30, 5), (80, 22, 6), (82, 62, 4)] if up
                 else [(14, 58, 4), (76, 42, 5), (24, 16, 5)])
        for (x, y, r), c in zip(stars, ("#3b82f6", "#fbbf24", "#3b82f6")):
            p.append(_star(x, y, r, c))
        p.append(_char(look, "hk", *hands, dy=-5 if up else 0, mouth="open"))

    elif action == "onway":    # RQS on the way, clipboard under an arm
        dots = "".join(f'<circle cx="{68 + 6 * k}" cy="18" r="1.9" fill="#fff"/>'
                       for k in range(min(i + 1, 3)))
        p.append('<rect x="62" y="9" width="24" height="18" rx="9" fill="#0e7490"/>'
                 '<path d="M66 25 L62 32 L71 26Z" fill="#0e7490"/>' + dots)
        p.append(_char(look, "rqs", (35, 70), (64, 78 + (i % 2) * 4), dy=bob, feet=walk))
        p.append(_clipboard(0, bob))

    elif action == "pass":     # inspected: thumbs up, a green tick
        r = [9, 10.5, 9, 10.5][i]
        p.append(f'<circle cx="76" cy="22" r="{r}" fill="#16a34a"/>'
                 '<path d="M71 22 L75 26 L82 18" stroke="#fff" stroke-width="2.8" '
                 'fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
        if i % 2:
            p.append(_star(20, 26, 5, "#fbbf24"))
        p.append(_char(look, "rqs", (35, 70), (66, 42)))
        p.append(_clipboard()
                 + '<rect x="64.5" y="34" width="3" height="6" rx="1.5" fill="#d6a07a"/>')

    elif action == "help":     # waving both arms, a red "!" bouncing
        hands = ((26, 22), (66, 30)) if i % 2 == 0 else ((30, 30), (70, 22))
        by = [0, -4, 0, -4][i]
        p.append(f'<circle cx="77" cy="{17 + by}" r="11" fill="#ef4444"/>'
                 f'<rect x="75" y="{9 + by}" width="4" height="10" rx="2" fill="#fff"/>'
                 f'<circle cx="77" cy="{23 + by}" r="2.2" fill="#fff"/>')
        p.append(_char(look, "hk", *hands, mouth="o", worried=True))

    elif action == "dnd":      # waiting at a hanger, z's drifting up
        p.append('<rect x="67" y="50" width="20" height="36" rx="4" fill="#a855f7"/>'
                 '<circle cx="77" cy="57" r="4" fill="#fff"/>'
                 '<text x="77" y="75" font-family="Arial,sans-serif" font-size="7.5" '
                 'font-weight="700" fill="#fff" text-anchor="middle">DND</text>')
        for k, (x, y, sz) in enumerate([(60, 30, 8), (66, 22, 10), (73, 13, 12)]):
            op = 0.95 if (k + i) % 3 != 2 else 0.3
            p.append(f'<text x="{x}" y="{y - (i % 2) * 2}" font-family="Arial,sans-serif" '
                     f'font-size="{sz}" font-weight="700" fill="#7c3aed" opacity="{op}">z</text>')
        p.append(_char(look, "hk", (45, 77), (51, 77), dx=-6, mouth="flat"))

    elif action == "later":    # walking off, a clock above
        a = i * 90
        p.append('<circle cx="76" cy="20" r="11" fill="#c2410c"/>'
                 '<circle cx="76" cy="20" r="8" fill="#fff"/>'
                 '<path d="M76 20 L76 15.5" stroke="#1f2937" stroke-width="1.6" stroke-linecap="round"/>'
                 f'<path d="M76 20 L76 13.5" stroke="#c2410c" stroke-width="1.4" '
                 f'stroke-linecap="round" transform="rotate({a} 76 20)"/>')
        sw = (i % 2) * 6
        p.append(_char(look, "hk", (30, 80 - sw), (66, 74 + sw), dx=-4, dy=bob,
                       feet=walk, mouth="flat"))

    elif action == "refused":  # hands up, a no-entry sign
        p.append('<circle cx="76" cy="20" r="10" fill="#fff" stroke="#64748b" stroke-width="3"/>'
                 '<path d="M69 13 L83 27" stroke="#64748b" stroke-width="3"/>')
        p.append(_char(look, "hk", (27, 52), (69, 52), dx=[-1, 1, -1, 1][i] - 4,
                       mouth="flat"))

    elif action == "shine":    # already clean: no person, a twinkle
        p = []
        big = [16, 20, 16, 20][i]
        p.append(f'<circle cx="48" cy="76" r="{big + 10}" fill="#0ea5e9" opacity=".12"/>')
        p.append(_star(48, 76, big, "#0ea5e9", .92))
        for k, (x, y, r) in enumerate([(22, 50, 6), (76, 46, 7), (74, 104, 5), (20, 100, 5)]):
            p.append(_star(x, y, r if (k + i) % 2 else r * .55, "#38bdf8"))
    return "".join(p)


@functools.lru_cache(maxsize=None)
def strip_svg(look: str, action: str) -> str:
    """All FRAMES frames of one action, side by side."""
    frames = "".join(f'<g transform="translate({i * W} 0)">{_frame(look, action, i)}</g>'
                     for i in range(FRAMES))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * FRAMES}" height="{H}" '
            f'viewBox="0 0 {W * FRAMES} {H}">{frames}</svg>')


@functools.lru_cache(maxsize=None)
def strip_uri(look: str, action: str) -> str:
    """A data URI for the strip. Escaped by hand rather than base64: a third
    smaller, and every strip on screen rides in the page's payload."""
    svg = (strip_svg(look, action).replace('"', "'").replace("%", "%25")
           .replace("#", "%23").replace("<", "%3C").replace(">", "%3E"))
    return "data:image/svg+xml," + svg


def key(look: str, action: str) -> str:
    """The one name a strip goes by in the payload and the CSS."""
    return f"n-{action}" if action in PERSONLESS else f"{look}-{action}"


def sprite_css(keys, w=30, h=40, speed=".8s") -> str:
    """CSS for the 2-D plan and the legend: one class per strip, stepped."""
    rules = [f".av{{display:inline-block;vertical-align:middle;"
             f"width:{w}px;height:{h}px;background-size:{w * FRAMES}px {h}px;"
             f"background-repeat:no-repeat;animation:avstep {speed} steps({FRAMES}) infinite}}",
             f"@keyframes avstep{{from{{background-position:0 0}}"
             f"to{{background-position:-{w * FRAMES}px 0}}}}"]
    for k in sorted(set(keys)):
        look, action = k.split("-", 1)
        rules.append(f'.av-{k}{{background-image:url("{strip_uri(look, action)}")}}')
    return "".join(rules)
