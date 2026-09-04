"""
roomstatus.py — one vocabulary for where a room has got to.

The Live board and the housekeepers' page were each writing their own words
into the same column: one said "cleaning_started", the other "in_progress".
Both were right on their own screen and invisible on the other, so a room a
housekeeper had finished still showed as untouched to the supervisor watching
the board.

These are the words. `normalise` accepts either dialect, so rows written
before this existed still read correctly.
"""

PENDING = "pending"
ALREADY_CLEAN = "already_clean"
STARTED = "cleaning_started"
DONE = "cleaning_done"
INSPECTED = "inspected"
DND = "dnd"
HELP = "help"

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
    PENDING:       ("Waiting to clean", "Waiting", "#94a3b8", "#e6ebf2", "#3d4b5c"),
    STARTED:       ("Cleaning",       "Cleaning",  "#e89611", "#fbe3b8", "#7c4a02"),
    DONE:          ("Ready for RQS",  "Ready",     "#2f80ed", "#cfe0fb", "#17376f"),
    INSPECTED:     ("Inspected",      "Inspected", "#1a9e4b", "#c7edd3", "#14532d"),
    ALREADY_CLEAN: ("Already clean",  "Clean",     "#0ea5e9", "#cbe8fa", "#075985"),
    DND:           ("Do not disturb", "DND",       "#a855f7", "#e5dbfa", "#5b21b6"),
    HELP:          ("Needs help",     "Help",      "#ef4444", "#fbd3d3", "#8f1a1a"),
}

#: The one road through the day. Anything else -- do not disturb, needs help,
#: already clean -- is a detour off it, not a step along it.
NEXT = {PENDING: STARTED, STARTED: DONE, DONE: INSPECTED}

#: Only an RQS closes a room. A housekeeper saying "ready for RQS" is the
#: whole point of the handover; letting her also say "inspected" would make
#: the inspection unprovable.
RQS_ONLY = (INSPECTED,)

#: Counted as no longer needing a housekeeper.
CLEANED = (ALREADY_CLEAN, DONE, INSPECTED)

#: Needs someone to look at it, whatever else is going on.
ATTENTION = (HELP,)


def normalise(raw) -> str:
    """The canonical status for whatever is stored on a row."""
    if raw in META:
        return raw
    key = str(raw).strip().lower() if raw is not None else None
    if key in META:
        return key
    return ALIASES.get(key, PENDING)


def label(raw, short=False) -> str:
    m = META[normalise(raw)]
    return m[1] if short else m[0]


def colours(raw):
    """(dot, background, ink) for a status."""
    return META[normalise(raw)][2:]


def is_clean(raw) -> bool:
    return normalise(raw) in CLEANED


def rank(raw) -> int:
    """How far along a room is, for sorting worst-first."""
    st = normalise(raw)
    if st == HELP:
        return -1                      # anything asking for help comes first
    return FLOW.index(st) if st in FLOW else len(FLOW)
