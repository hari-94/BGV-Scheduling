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
META = {
    PENDING:       ("Not started",   "Waiting",   "#94a3b8", "#f1f5f9", "#475569"),
    ALREADY_CLEAN: ("Already clean", "Clean",     "#10b981", "#dcfce7", "#065f46"),
    STARTED:       ("Cleaning",      "Cleaning",  "#f59e0b", "#fef3c7", "#92400e"),
    DONE:          ("Ready for RQS", "Ready",     "#3b82f6", "#dbeafe", "#1e40af"),
    INSPECTED:     ("Inspected",     "Inspected", "#8b5cf6", "#ede9fe", "#5b21b6"),
    DND:           ("Do not disturb", "DND",      "#a855f7", "#f3e8ff", "#6b21a8"),
    HELP:          ("Needs help",    "Help",      "#ef4444", "#fee2e2", "#991b1b"),
}

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
