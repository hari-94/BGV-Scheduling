"""
manager_questions.py — the few decisions the 5 AM run has to guess today,
asked of the managers in plain words. Only questions whose answer changes
what the app does on its own are here. No Streamlit: the page
(pages/12_Questions.py) draws it, and each manager's answers are one
app_settings row, KEY_PREFIX + username, so two managers saving at once can't
overwrite each other.

Every question says what the app does today ("now"), from the code, so most
answers are "keep it" or the one thing to change. A question's `key` is
stable -- answers are stored under it and turned into rules from it -- so
reword a question freely but never rename its key. An answer stores the
option's text, so once managers have answered, reword an option only with a
migration of the saved answers.

Field kinds:
  one   pick one (radio)            -> str
  all   tick all that apply         -> [str]
  rank  pick in order, first = 1st  -> [str] in the order picked
  num   a number                    -> int | None
  text  a short answer              -> str
  long  a longer answer             -> str
Every question also gets a free "notes" box.
"""

KEY_PREFIX = "mq_"
KEEP = "Keep it as it is"
RANK_HELP = "Pick in order: your first pick comes first. Leave out anything you'd never do."

PARTS = [
    ("Short of housekeepers", [
        dict(key="fc_short_order",
             q="Not enough housekeepers for the check-out rooms. Who should clean them first?",
             now="Every housekeeper is filled up to a full day. Then whoever is on Dust n Vac helps, "
                 "then housekeepers on projects.",
             fields=[("rank", "order", RANK_HELP,
                      ["Whoever is on Dust n Vac (housekeeper or RQS 2)", "Housekeepers on projects",
                       "Housepersons (HSP)", "Housekeepers on deep cleans", "Daily Service housekeepers",
                       "An inspector (RQS) cleaning rooms", "Overtime for housekeepers already working",
                       "A supervisor or manager cleaning rooms", "Leave rooms for tomorrow"])]),
        dict(key="fc_overtime",
             q="Can one housekeeper get more than a full day of check-out rooms?",
             now="No. A housekeeper's full day is 380 minutes and no housekeeper gets more.",
             fields=[("one", "choice", "Your answer",
                      ["No, keep 380 minutes as the most", "Yes, if the housekeeper agrees",
                       "Yes, if a manager says OK"]),
                     ("num", "max_minutes", "If yes, the most minutes for one housekeeper in one day")]),
        dict(key="fc_must_first",
             q="If some rooms can't be cleaned today, which rooms must the housekeepers do first?",
             now="No order. Rooms no housekeeper can take just say “No HK available”.",
             fields=[("all", "first", "Tick all that must be done first",
                      ["Early check-ins", "VIP rooms", "Owner stays", "Any room with a guest arriving today"])]),
    ]),
    ("Daily Service", [
        dict(key="ds_who",
             q="The schedule has no housekeeper on Daily Service. Which housekeeper should the app put on it?",
             now="A housekeeper working today who hasn't done Daily Service yet this week.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Always the same housekeepers", "Housekeepers take turns, everyone equally",
                       "The most experienced housekeeper"]),
                     ("text", "names", "If always the same housekeepers, who?")]),
        dict(key="ds_full_day",
             q="How many minutes of Daily Service is a full day for one housekeeper?",
             now="460 minutes on weekdays, 510 on weekends (the minutes on the room list).",
             fields=[("num", "weekday", "Weekdays (leave empty to keep 460)"),
                     ("num", "weekend", "Weekends (leave empty to keep 510)")]),
        dict(key="ds_short_order",
             q="Not enough housekeepers for Daily Service. What should happen first?",
             now="The rooms say “Need Housekeeper”. No housekeeper is moved from check-out rooms until "
                 "every Daily Service list is full.",
             fields=[("rank", "order", RANK_HELP,
                      ["Move a housekeeper from check-out rooms", "Use whoever is on Dust n Vac (housekeeper or RQS 2)",
                       "Quick service in some rooms (towels and trash only)", "Skip some rooms until tomorrow",
                       "Overtime for Daily Service housekeepers"])]),
    ]),
    ("Inspectors (RQS)", [
        dict(key="rqs_rooms",
             q="How many check-out rooms can one inspector (RQS) check in a day?",
             now="12, and never more than 13.",
             fields=[("num", "rooms", "Rooms per inspector (leave empty to keep 12)")]),
        dict(key="rqs_short_order",
             q="Not enough inspectors (RQS). Who should inspect the extra rooms first?",
             now="Inspectors (RQS) on projects first. RQS 1 and RQS 2 only if no other inspector is free.",
             fields=[("rank", "order", RANK_HELP,
                      ["Inspectors (RQS) on projects", "RQS 2", "RQS 1", "A supervisor or manager",
                       "Leave some rooms not inspected"])]),
    ]),
    ("During the day", [
        dict(key="callout",
             q="A housekeeper calls out after the 5 AM lists are made. What should the app do?",
             now="Nothing. The inspector (RQS) moves that housekeeper's rooms by hand.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Give only that housekeeper's rooms to other housekeepers nearby",
                       "Make all the lists again"])]),
        dict(key="short_shift",
             q="A housekeeper works a short shift (for example 10 to 2). How many rooms should the housekeeper get?",
             now="A full day, like every other housekeeper.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Fewer rooms, based on the housekeeper's hours", "Give the housekeeper Daily Service"])]),
        dict(key="quiet_day",
             q="More housekeepers than rooms. What should the app do?",
             now="It gives full days to as few housekeepers as possible. The other housekeepers get no rooms.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Give every housekeeper fewer rooms", "Offer early leave (VTO) to housekeepers",
                       "Send the extra housekeepers to projects"])]),
        dict(key="auto_push",
             q="Should the lists go to HotSOS by themselves, without an inspector (RQS) or manager pressing Push?",
             now="Only on days a manager picks.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Every day", "Weekends only",
                       "Only if no inspector (RQS) or manager has pressed Push by a set time"]),
                     ("text", "time", "If by a set time, what time?")]),
    ]),
]

QUESTIONS = [q for _, qs in PARTS for q in qs]
NUMBER = {q["key"]: i + 1 for i, q in enumerate(QUESTIONS)}


def answered(q, a) -> bool:
    """Whether a question has any answer in it (notes count)."""
    a = a or {}
    return any(a.get(k) not in (None, "", []) for k in [f[1] for f in q["fields"]] + ["notes"])


def summary(q, a) -> str:
    """One line for the side-by-side table."""
    a = a or {}
    bits = []
    for kind, fkey, label, *rest in q["fields"]:
        v = a.get(fkey)
        if v in (None, "", []):
            continue
        if kind == "rank":
            bits.append("  ".join(f"{i + 1}. {x}" for i, x in enumerate(v)))
        elif kind == "all":
            bits.append(", ".join(v))
        elif kind == "one":
            bits.append(str(v))
        else:
            bits.append(f"{label.split(', ')[-1].split(' (')[0]}: {v}")
    if a.get("notes"):
        bits.append(f"Note: {a['notes']}")
    return " · ".join(bits)
