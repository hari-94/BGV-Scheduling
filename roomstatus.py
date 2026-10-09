"""
roomstatus.py — one vocabulary for where a room has got to.

The Live board and the housekeepers' page were each writing their own words
into the same column: one said "cleaning_started", the other "in_progress".
Both were right on their own screen and invisible on the other, so a room a
housekeeper had finished still showed as untouched to the supervisor watching
the board.

These are the words. `normalise` accepts either dialect, so rows written
before this existed still read correctly.

Since October 2026 the floor marks rooms in HotSOS and the app mirrors it
(hotsos_agent.sync_room_status, every two minutes), so the labels are
HotSOS's own and every HotSOS state has a twin here: Vacant Cleaned and
Occupied Cleaned are both "ready for the RQS", Return Later and Service
Refused are their own detours. `HOTSOS` maps its codes to these keys; a code
it has never sent before is kept under its own name rather than read as
"Awaiting Service".
"""
import time as _time

PENDING = "pending"
ALREADY_CLEAN = "already_clean"
STARTED = "cleaning_started"
DONE = "cleaning_done"
INSPECTED = "inspected"
DND = "dnd"
HELP = "help"
OCCUPIED_CLEANED = "occupied_cleaned"
RETURN_LATER = "return_later"
SERVICE_REFUSED = "service_refused"
TO_BE_INSPECTED = "to_be_inspected"

#: HotSOS's serviceStatusEnum -> ours.
HOTSOS = {
    "AWAITING_SERVICE": PENDING,
    "CLEANING_STARTED": STARTED,
    "VACANT_CLEANED": DONE,
    "OCCUPIED_CLEANED": OCCUPIED_CLEANED,
    "TO_BE_INSPECTED": TO_BE_INSPECTED,
    "INSPECTED": INSPECTED,
    "DND": DND,
    "RETURN_LATER": RETURN_LATER,
    "SERVICE_REFUSED": SERVICE_REFUSED,
}

#: HotSOS's "cleaned" states, and its "To Be Inspected", hand the room to the RQS.
READY = (DONE, OCCUPIED_CLEANED, TO_BE_INSPECTED)

#: The order a room moves through, for sorting and for progress bars.
FLOW = [PENDING, STARTED, DONE, INSPECTED]

#: What the other dialect called things.
ALIASES = {
    "not_started": PENDING,
    "": PENDING,
    None: PENDING,
    "in_progress": STARTED,
    "started": STARTED,
    "cleaned": DONE,
    "done": DONE,
    "clean": ALREADY_CLEAN,
    "need_help": HELP,
    "do_not_disturb": DND,
}

#: label, short label, dot colour, card background, ink
#:
#: The four steps of the round are meant to be read as a journey, so their
#: colours travel too: grey while it waits, amber while it is being done,
#: blue once it is someone else's turn to look, and a dark, settled green
#: when the RQS has passed it. Nothing else is green, so green means finished
#: and finished means inspected.
#: A notch back from where this went. The pastels these started as were too
#: faint to tell apart at arm's length; the near-black they became was too
#: heavy to look at all shift. These sit between: enough colour to read a
#: room's state across a corridor, light enough to carry dark text.
META = {
    PENDING:          ("Awaiting Service",     "Awaiting",  "#94a3b8", "#e6ebf2", "#3d4b5c"),
    STARTED:          ("Cleaning Started",     "Started",   "#e89611", "#fbe3b8", "#7c4a02"),
    DONE:             ("Vacant Cleaned",       "Vacant Cln", "#2f80ed", "#cfe0fb", "#17376f"),
    OCCUPIED_CLEANED: ("Occupied Cleaned",     "Occ. Cln",  "#4f6fd9", "#d6dcf7", "#1e2f6f"),
    TO_BE_INSPECTED:  ("To Be Inspected",      "To Inspect", "#0e7490", "#c9eef4", "#164e63"),
    INSPECTED:        ("Inspected",            "Inspected", "#1a9e4b", "#c7edd3", "#14532d"),
    ALREADY_CLEAN:    ("Already clean",        "Clean",     "#0ea5e9", "#cbe8fa", "#075985"),
    DND:              ("DND (Do Not Disturb)", "DND",       "#a855f7", "#e5dbfa", "#5b21b6"),
    RETURN_LATER:     ("Return Later",         "Later",     "#c2410c", "#fde0cc", "#7c2d12"),
    SERVICE_REFUSED:  ("Service Refused",      "Refused",   "#64748b", "#e2e8f0", "#334155"),
    HELP:             ("Needs help",           "Help",      "#ef4444", "#fbd3d3", "#8f1a1a"),
}

#: How a status HotSOS sends that isn't listed above is shown: its own words,
#: neutral grey. `normalise` keeps such keys as they are.
_UNKNOWN = ("#9ca3af", "#eceef1", "#374151")

#: The one road through the day. Anything else -- do not disturb, needs help,
#: already clean -- is a detour off it, not a step along it.
NEXT = {PENDING: STARTED, STARTED: DONE, DONE: INSPECTED, OCCUPIED_CLEANED: INSPECTED,
        TO_BE_INSPECTED: INSPECTED}

#: Only an RQS closes a room. A housekeeper saying "ready for RQS" is the
#: whole point of the handover; letting her also say "inspected" would make
#: the inspection unprovable.
RQS_ONLY = (INSPECTED,)

#: Counted as no longer needing a housekeeper.
CLEANED = (ALREADY_CLEAN, DONE, OCCUPIED_CLEANED, TO_BE_INSPECTED, INSPECTED,
           SERVICE_REFUSED)

#: Needs someone to look at it, whatever else is going on.
ATTENTION = (HELP,)


def normalise(raw) -> str:
    """The canonical status for whatever is stored on a row."""
    if raw in META:
        return raw
    key = str(raw).strip().lower() if raw is not None else None
    if key in META:
        return key
    if key in ALIASES:
        return ALIASES[key]
    # A HotSOS state with no twin here yet: keep it, so it shows as itself.
    return key if key else PENDING


def from_hotsos(enum, text="") -> str:
    """Our key for a HotSOS serviceStatusEnum (e.g. "VACANT_CLEANED")."""
    e = str(enum or "").strip().upper()
    return HOTSOS.get(e) or (e.lower() if e else PENDING)


def _meta(st):
    if st in META:
        return META[st]
    words = str(st).replace("_", " ").title()
    return (words, words) + _UNKNOWN


def label(raw, short=False) -> str:
    m = _meta(normalise(raw))
    return m[1] if short else m[0]


def colours(raw):
    """(dot, background, ink) for a status."""
    return _meta(normalise(raw))[2:]


def is_clean(raw) -> bool:
    return normalise(raw) in CLEANED


def rank(raw) -> int:
    """How far along a room is, for sorting worst-first."""
    st = normalise(raw)
    if st == HELP:
        return -1                      # anything asking for help comes first
    if st in READY:
        st = DONE
    return FLOW.index(st) if st in FLOW else len(FLOW)


# ── who marks rooms ───────────────────────────────────────────────────────────
#: app_settings key. "hotsos": the floor marks rooms in HotSOS and the app
#: mirrors it -- every status button in the app is hidden. Anything else: the
#: app's own buttons, as before. One switch, for the day HotSOS goes.
SOURCE_KEY = "room_status_source"
_src_cache = [0.0, None]


def mirrored() -> bool:
    """Is HotSOS the one place rooms are marked? Read at most once a minute."""
    if _time.time() - _src_cache[0] > 60:
        try:
            import db
            _src_cache[1] = (db._load_key(SOURCE_KEY) or {}).get("source")
        except Exception:
            pass
        _src_cache[0] = _time.time()
    return _src_cache[1] == "hotsos"
