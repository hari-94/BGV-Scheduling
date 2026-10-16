"""
arrival_sections.py — the names the front desk's Arrival Report headings go by.

One table, read by the Schedule page (cleaning_scheduler.parse_email_notes,
which files each note against its room) and by the morning Teams messages
(teams_notes.py, which keep the desk's lines under their headings). When the
desk spells a heading a new way, add the spelling here and both follow.

Keys are normalised headings: punctuation dropped, case and spacing
flattened (see norm_heading).
"""
import re

NOTE_SECTIONS = {
    "vip inspections": "VIP", "vip inspection": "VIP", "vips": "VIP",
    "room moves": "Room Move", "room move": "Room Move", "moves": "Room Move",
    "stayovers": "Stayover", "stayover": "Stayover", "stay overs": "Stayover",
    "robes": "Robes", "robe": "Robes",
    "pack n play": "Pack n Play", "pack and play": "Pack n Play",
    "packnplay": "Pack n Play", "pnp": "Pack n Play",
    "cribs": "Pack n Play", "crib": "Pack n Play",
    "highchairs": "Highchair", "highchair": "Highchair",
    "high chairs": "Highchair", "high chair": "Highchair",
    "rollaway": "Rollaway", "rollaways": "Rollaway", "roll away": "Rollaway",
    "special requests": "Special Request", "special request": "Special Request",
    "requests": "Special Request",
    "dogs arriving": "Dog arriving", "dog arriving": "Dog arriving",
    "dogs": "Dog arriving", "pets": "Dog arriving", "pets arriving": "Dog arriving",
    "celebrations": "Celebration", "celebration": "Celebration",
    "early ins": "Early In", "early in": "Early In", "early arrivals": "Early In",
    "early check ins": "Early In", "early checkins": "Early In",
    "late arrival": "Late Arrival", "late arrivals": "Late Arrival",
}
LATE_SECTIONS = {"late checkouts", "late checkout", "late check outs",
                 "late check out", "late outs", "late out", "late c o",
                 "late cos", "late co"}
# Headings that carry no per-room information. They are named so their contents
# cannot leak into whichever section came before them.
SKIP_SECTIONS = {"check ins", "check in", "checkins", "arrivals",
                 "check outs", "check out", "checkouts", "departures",
                 "notes", "reminders", "general notes"}


def norm_heading(s: str) -> str:
    """Flatten a heading so spelling and punctuation stop mattering."""
    s = re.sub(r'[^A-Za-z ]+', ' ', str(s or ""))
    return re.sub(r'\s+', ' ', s).strip().lower()
