"""
staffing.py — how many people a day needs.

The workbook works it out like this, in hidden rows 5-11 of every sheet:

    HSKP Needed = <daily labour minutes> / 360
    RQS needed  = <checkouts> / 12
    Extras      = HSKP Actual - HSKP Needed

That is a sound first cut and it is what the printed sheet shows, so it stays
here as the baseline. Four things about it are worth improving, and the
estimate below does:

1.  One divisor for two different jobs. 360 is six hours of an eight-hour
    shift. But this property loads a Full Clean housekeeper to 330-380 minutes
    and a Daily Service round to about 460 -- the scheduler's own targets. A
    single 360 therefore asks for too few people on a checkout-heavy day and
    too many on a daily-service one.

2.  Fractional people. "5.75 housekeepers" is not an answer to give a
    supervisor, and the fraction infects the Extras row: Sunday reads "0.49
    extras" when what it means is thirty people for a thirty-person day.

3.  RQS counted from checkouts alone. An inspector also walks the daily
    services; on a heavy DS day the sheet asks for fewer inspectors than the
    day actually needs.

4.  A point estimate for a decision that is not symmetric. Being one
    housekeeper short costs a missed checkout or overtime; being one over
    costs a few idle hours. A range makes that visible, and the plan can lean
    to the safe end when the day is big.

Nothing here invents data. Given only the two numbers the sheet already
carries -- labour minutes and checkouts -- it produces the same shape of
answer with the four corrections applied, and it says which of them moved.
"""
import math
from collections import OrderedDict

#: The scheduler's own loading targets, mirrored here so a planning estimate
#: and a built schedule cannot drift apart. See LOW_MIN / MAX_FC in
#: cleaning_scheduler.py.
FC_LOW, FC_FULL = 330, 380
DS_FULL = 460

#: What the sheet uses, kept for the baseline figure.
SHEET_DIVISOR = 360
#: Rooms one inspector covers in a day. The Reassign board uses the same 12.
ROOMS_PER_RQS = 12

#: Typical minutes a checkout takes here: the scheduler's Full Clean charts
#: run 70/120/140 with 120 the common case.
MINUTES_PER_CHECKOUT = 120
#: A daily service is a touch-up, not a clean.
MINUTES_PER_DAILY = 35


def _ceil(x):
    """People come in whole numbers, and half a person is a whole person."""
    return int(math.ceil(round(x, 6)))


def sheet_estimate(minutes, checkouts):
    """What the workbook's own formulas say, to the digit."""
    return {
        "hskp": (minutes or 0) / SHEET_DIVISOR,
        "rqs": (checkouts or 0) / ROOMS_PER_RQS,
    }


def estimate(minutes=0, checkouts=0, dailies=0, on_hand_hskp=None,
             on_hand_rqs=None, divisor=None):
    """How many people this day needs.

    `minutes` is the day's total cleaning labour, `checkouts` and `dailies`
    the room counts behind it. Everything is optional: with only minutes it
    behaves like the sheet, and every extra number sharpens it.

    `divisor` overrides the Full Clean target when history has measured a
    better one for this property -- see `calibrate`.
    """
    minutes = float(minutes or 0)
    checkouts = int(checkouts or 0)
    dailies = int(dailies or 0)
    fc_target = float(divisor or FC_LOW + (FC_FULL - FC_LOW) / 2)   # 355

    # Split the labour between the two jobs, so each is divided by its own
    # target rather than one number standing for both. Where the room counts
    # are not given, it all falls to Full Clean, which is the busier side and
    # the safer assumption.
    ds_minutes = min(minutes, dailies * MINUTES_PER_DAILY)
    fc_minutes = max(0.0, minutes - ds_minutes)

    fc_people = fc_minutes / fc_target if fc_minutes else 0.0
    ds_people = ds_minutes / DS_FULL if ds_minutes else 0.0
    likely = fc_people + ds_people

    # The band: everyone loaded to the brim, against everyone loaded lightly.
    low = (fc_minutes / FC_FULL if fc_minutes else 0.0) + \
          (ds_minutes / DS_FULL if ds_minutes else 0.0)
    high = (fc_minutes / FC_LOW if fc_minutes else 0.0) + \
           (ds_minutes / (DS_FULL * 0.87) if ds_minutes else 0.0)

    rooms = checkouts + dailies
    rqs = rooms / ROOMS_PER_RQS if rooms else 0.0

    out = OrderedDict()
    out["minutes"] = minutes
    out["checkouts"] = checkouts
    out["dailies"] = dailies
    out["hskp_low"] = _ceil(low) if minutes else 0
    out["hskp"] = _ceil(likely) if minutes else 0
    out["hskp_high"] = _ceil(high) if minutes else 0
    out["rqs"] = _ceil(rqs) if rooms else 0
    out["hskp_raw"] = likely
    out["rqs_raw"] = rqs
    # A day with any work at all needs at least one of each.
    if minutes and not out["hskp"]:
        out["hskp"] = out["hskp_low"] = out["hskp_high"] = 1
    if rooms and not out["rqs"]:
        out["rqs"] = 1

    sheet = sheet_estimate(minutes, checkouts)
    out["sheet_hskp"] = sheet["hskp"]
    out["sheet_rqs"] = sheet["rqs"]
    out["hskp_delta"] = out["hskp"] - _ceil(sheet["hskp"]) if minutes else 0
    out["rqs_delta"] = out["rqs"] - (_ceil(sheet["rqs"]) if checkouts else 0)

    if on_hand_hskp is not None:
        out["on_hand_hskp"] = int(on_hand_hskp)
        out["extra_hskp"] = int(on_hand_hskp) - out["hskp"]
    if on_hand_rqs is not None:
        out["on_hand_rqs"] = int(on_hand_rqs)
        out["extra_rqs"] = int(on_hand_rqs) - out["rqs"]
    return out


def calibrate(history):
    """Measure this property's real minutes per housekeeper.

    `history` is a list of {"minutes", "housekeepers"} from days that were
    actually worked. The scheduler's 330-380 is a target; what a day really
    absorbed is better evidence, when there is enough of it. Returns None
    rather than a shaky number -- fewer than four usable days, or a figure
    outside 250-500, means the assumption stands.
    """
    good = [(float(h["minutes"]), int(h["housekeepers"])) for h in history or []
            if h.get("minutes") and h.get("housekeepers")]
    if len(good) < 4:
        return None
    per = sorted(m / n for m, n in good if n)
    if not per:
        return None
    mid = per[len(per) // 2] if len(per) % 2 else \
        (per[len(per) // 2 - 1] + per[len(per) // 2]) / 2
    return round(mid, 1) if 250 <= mid <= 500 else None


def week_totals(rows):
    """Add a week of daily estimates up, for the line under the table."""
    keys = ("minutes", "checkouts", "dailies", "hskp", "rqs",
            "on_hand_hskp", "on_hand_rqs", "extra_hskp", "extra_rqs")
    out = {k: 0 for k in keys}
    for r in rows:
        for k in keys:
            out[k] += r.get(k) or 0
    return out


#: A checkout here runs 70-140 minutes. Outside this band, the two numbers
#: describing a day disagree with each other.
SANE_PER_CHECKOUT = (60, 175)


def consistency(minutes, checkouts, dailies=0):
    """Do the day's two numbers tell the same story?

    Labour minutes and room counts are typed in by hand, separately, and
    nothing has ever compared them. A day recorded as 4,460 minutes over 85
    checkouts is 52 minutes a room, which is not a checkout clean -- either
    daily services are hiding inside that room count, or the minutes are
    short. Catching that while planning costs nothing; catching it at 7am
    costs a housekeeper.
    """
    minutes = float(minutes or 0)
    checkouts = int(checkouts or 0)
    dailies = int(dailies or 0)
    if not minutes or not checkouts:
        return None
    per = (minutes - dailies * MINUTES_PER_DAILY) / checkouts
    if per < SANE_PER_CHECKOUT[0]:
        return (f"{per:.0f} minutes a checkout is low — are daily services "
                f"counted inside the checkout number, or are the minutes short?")
    if per > SANE_PER_CHECKOUT[1]:
        return (f"{per:.0f} minutes a checkout is high — are stayovers or a "
                f"deep clean included in the minutes?")
    return None
