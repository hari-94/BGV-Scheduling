"""Read a multi-day Housekeeping Dashboard export and say what each day needs.

The single-day version of this export already flows through
`cleaning_scheduler.excel_to_room_text`. This is the same report run over a
date range -- eighteen days in the September file -- and it is the only place
the property's *future* workload is written down before somebody types it into
a plan by hand.

Three things about the format, all of them learned the hard way:

* **Column positions move between exports.** In the 12 September file Time was
  column 4; in the 13-30 September file it is column 3. Every column is found
  by its header label, and the header row is re-read at every date block rather
  than assumed to hold for the whole sheet.

* **The sheet has more than one table.** After the cleaning services come
  "Housekeeping Hold, UT, Unallocated" and the non-clean services, and *the
  same dates appear again* in each. Reading to the end of the file counts the
  hold list as cleaning work and quietly doubles some days. The cleaning table
  ends at its "Total Labor (Minutes):" footer, and that is where this stops.

* **The workbook states its own totals.** Each day carries "Rooms: N" in its
  header and "Daily Labor (Minutes): N" in its footer. Those are not ignored --
  they are compared against what was counted, and a disagreement is reported
  rather than smoothed over. A parser that silently disagrees with the sheet it
  is reading is worse than no parser.

No Streamlit here, so it can be tested on its own.
"""
import datetime
import re

import openpyxl

#: Section titles that appear in column 0. Only the first holds cleaning work.
_CLEANING = "cleaning services"
_OTHER_SECTIONS = ("housekeeping hold", "non-clean services", "hold count")
#: The cleaning table's own footer; nothing after it is a service row.
_END_MARKERS = ("total labor", "total housekeeper shifts")

_ROOM_RE = re.compile(r"^[1-9]\d{3}[A-Z]{1,4}$")
_NUM_RE = re.compile(r"(-?\d[\d,]*\.?\d*)")

#: How a service line is classified. Matched on a lowercased prefix.
FULL_CLEAN = "full clean"
DAILY = "daily service"
DUST = "dust n vac"
PU = "p/u models"


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = _NUM_RE.search(str(v).replace(",", ""))
    return float(m.group(1)) if m else None


def _as_date(v):
    """A date cell, however the export wrote it."""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
                "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _label(row):
    """The text in column 0, lowercased, or ''."""
    return str(row[0]).strip().lower() if row and row[0] is not None else ""


def _blank_day(d):
    return {
        "date": d.isoformat(),
        "rooms": 0, "minutes": 0,
        "checkouts": 0, "checkout_minutes": 0,
        "dailies": 0, "daily_minutes": 0,
        "dustnvac": 0, "pu_models": 0, "other": 0,
        "stated_rooms": None, "stated_clean_count": None,
        "stated_minutes": None, "stated_shifts": None,
    }


def read_dashboard(source):
    """Parse the export. Returns {"days": [...], "warnings": [...]}.

    `source` is anything openpyxl accepts: a path, or the file object Streamlit
    hands back from an uploader.
    """
    wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    sheet = None
    for name in wb.sheetnames:
        if "housekeeping dashboard" in str(name).strip().lower():
            sheet = name
            break
    if sheet is None:
        sheet = wb.sheetnames[-1]
    ws = wb[sheet]

    days = {}
    order = []
    warnings = []
    in_cleaning = False
    cur = None
    cols = None

    for row in ws.iter_rows(values_only=True):
        if not row:
            continue
        lab = _label(row)

        if lab.startswith(_END_MARKERS):
            break                               # the cleaning table is over
        if lab == _CLEANING:
            in_cleaning, cur, cols = True, None, None
            continue
        if lab.startswith(_OTHER_SECTIONS):
            in_cleaning, cur, cols = False, None, None
            continue
        if not in_cleaning:
            continue

        d = _as_date(row[0]) if row[0] is not None else None
        if d is not None:
            cur = d.isoformat()
            if cur not in days:
                days[cur] = _blank_day(d)
                order.append(cur)
            # the header line states the day's own totals; keep them to check
            for cell in row[1:]:
                s = str(cell or "").strip()
                if not s:
                    continue
                low = s.lower()
                if low.startswith("rooms"):
                    days[cur]["stated_rooms"] = _num(s)
                elif low.startswith("clean count"):
                    days[cur]["stated_clean_count"] = _num(s)
            cols = None
            continue

        vals = [str(c).strip() for c in row if c is not None]
        if "Room" in vals and "Service" in vals:
            # Column positions move between exports; re-read them every time.
            cols = {str(c).strip(): j for j, c in enumerate(row) if c is not None}
            continue

        if cur is None:
            continue

        # The day's own footer. Its number is taken as the first numeric cell
        # rather than from a column position, because the position moves and
        # the row holds nothing else.
        if lab.startswith("daily labor"):
            days[cur]["stated_minutes"] = next(
                (_num(c) for c in row[1:] if _num(c) is not None), None)
            continue
        if lab.startswith("daily housekeeper shifts"):
            days[cur]["stated_shifts"] = next(
                (_num(c) for c in row[1:] if _num(c) is not None), None)
            continue

        if cols is None or row[0] is None:
            continue
        room = str(row[0]).strip().upper()
        if not _ROOM_RE.match(room):
            continue

        def get(name):
            j = cols.get(name)
            if j is None or j >= len(row) or row[j] is None:
                return ""
            return str(row[j]).strip()

        svc = get("Service").lower()
        mins = _num(get("Time")) or 0
        rec = days[cur]
        rec["rooms"] += 1
        rec["minutes"] += mins
        if svc.startswith(FULL_CLEAN):
            rec["checkouts"] += 1
            rec["checkout_minutes"] += mins
        elif svc.startswith(DAILY):
            rec["dailies"] += 1
            rec["daily_minutes"] += mins
        elif svc.startswith(DUST):
            rec["dustnvac"] += 1
        elif svc.startswith(PU):
            rec["pu_models"] += 1
        else:
            rec["other"] += 1

    out = [days[k] for k in order]
    for rec in out:
        sr = rec["stated_rooms"]
        if sr is not None and abs(sr - rec["rooms"]) > 0.5:
            warnings.append(
                "%s: the sheet says %d rooms, %d were read"
                % (rec["date"], int(sr), rec["rooms"]))
        sm = rec["stated_minutes"]
        if sm is not None and rec["minutes"] and abs(sm - rec["minutes"]) > 1:
            warnings.append(
                "%s: the sheet says %d labour minutes, %d were counted"
                % (rec["date"], int(sm), int(rec["minutes"])))
    if not out:
        warnings.append("No cleaning-services rows found — is this the right export?")
    return {"days": out, "warnings": warnings, "sheet": sheet}


def forecast(days, estimate, on_hand=None):
    """Attach a staffing estimate to each day.

    `estimate` is `staffing.estimate`, passed in rather than imported so this
    module stays free of the app. `on_hand` may be a function taking the ISO
    date and returning {"hk": n, "rqs": n} for days the plan already covers.
    """
    out = []
    for d in days:
        extra = (on_hand or (lambda _iso: {}))(d["date"]) or {}
        est = estimate(d["minutes"], d["checkouts"], d["dailies"],
                       on_hand_hskp=extra.get("hk"),
                       on_hand_rqs=extra.get("rqs"))
        merged = dict(d)
        merged.update(est)
        merged["date"] = d["date"]
        out.append(merged)
    return out
