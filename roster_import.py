"""
roster_import.py — Parse the weekly staff Schedule.xlsx into a day roster.

The workbook holds one sheet per week. Every sheet uses the same shape:

    col A            = section header, or a person's name
    cols B..H        = Sunday..Saturday
    a repeated row   = the real dates for those seven columns

Sheet names are unreliable (typos, duplicates, sheets copied without re-dating),
so a day is located by the DATES INSIDE each sheet, never by the sheet name.

Nothing here imports streamlit, so it can be unit-tested on its own.
"""
import re
import datetime as _dt
from collections import OrderedDict

# ── Section headers (verified identical across sheets spanning a full year) ────
HK_SECTIONS = OrderedDict([
    ("housekeeper building 1", 1),
    ("housekeeper building 2", 2),
    ("housekeeper building 3", 3),
])
RQS_SECTION = "room quality supervisors"
OTHER_SECTIONS = OrderedDict([
    ("managers",        "Managers"),
    ("houseperson am",  "Houseperson AM"),
    ("am lead",         "AM Lead"),
    ("houseperson pm",  "Houseperson PM"),
    ("pm leads",        "PM Leads"),
    ("sales/ spa",      "Sales / Spa"),
    ("overnight team",  "Overnight Team"),
    ("ullr - ice rink", "ULLR - Ice Rink"),
])

# Rows that are structure or weekly summary metrics, never a person.
SKIP_LABELS = {
    "", ".", "events", "holds", "daily services", "check outs", "rqs needed",
    "hskp needed", "hskp actual #", "extras hskp",
}

def _norm(s) -> str:
    """Collapse whitespace and lowercase — for matching labels and names."""
    return re.sub(r"\s+", " ", str(s or "").strip()).lower()

def norm_name(s) -> str:
    """Key used to match a sheet name against an existing roster name."""
    return _norm(s).rstrip(".").strip()

# ── Cell status vocabulary ────────────────────────────────────────────────────
# Explicitly not at work.
_OFF_RE = re.compile(
    r"\b(r\s*/?\s*off|off\s*/?\s*granted|off|sick|fmla|vto|vacation|no\s*show|call\s*out)\b")
# At work, but not cleaning guest rooms — so not available to the scheduler.
_OTHER_RE = re.compile(
    r"\b(hsp|keystone|ullr|garages?|projects?|food|maps|stripping\s+linen|rollaways|"
    r"lavar\s+botes|cleaning\s+(windows|carpets)|breck\s*in|training|firc|"
    r"help\s+with\s+party|safety\s+meeting|stairs\s*only|baseboards)\b")
# Inspector role codes.
_RQS_RE = re.compile(r"^(rqs?\s*[12]|rq\s*[12])\b")
# A leading number is the person's chart/zone load — they are working.
_LEAD_NUM_RE = re.compile(r"^\d+(\.\d+)?\s*(\+|-|/|$|\s)")

KIND_WORKING = "working"
KIND_DAILY   = "daily_service"
KIND_OFF     = "off"
KIND_OTHER   = "other_duty"
KIND_UNKNOWN = "unknown"

PRESENT_KINDS = (KIND_WORKING, KIND_DAILY)

def classify(raw) -> str:
    """Map one schedule cell to a status kind.

    Order matters. "VTO + Daily Service" is a daily-service shift, and
    "3 + VTO" is a full shift that ends early — both are present, even though
    each mentions VTO. Only a cell that leads with an off/other code is out.
    """
    s = re.sub(r"\s+", " ", str(raw or "").strip())
    if not s:
        return KIND_OFF
    low = s.lower()
    if "daily service" in low:
        return KIND_DAILY
    # What the cell LEADS with decides it. "3 + VTO" is a shift that ends early,
    # and "RQS 1 + training w/Alejandro" is an RQS 1 shift — neither is time off,
    # even though a later word would otherwise match an off/other-duty rule.
    if _LEAD_NUM_RE.match(s):
        return KIND_WORKING
    if _RQS_RE.match(low):
        return KIND_WORKING
    if low in ("on", "on am", "on pm", "hskp", "housekeeper") or re.match(r"^on\b", low):
        return KIND_WORKING
    if _OFF_RE.search(low):
        return KIND_OFF
    if _OTHER_RE.search(low):
        return KIND_OTHER
    if "lead" in low:
        return KIND_WORKING
    return KIND_UNKNOWN

def rqs_role(raw):
    """Return 1 or 2 when a cell names an explicit RQS role, else None."""
    low = _norm(raw)
    if re.search(r"\b(rqs?\s*1|rq\s*1)\b", low): return 1
    if re.search(r"\b(rqs?\s*2|rq\s*2)\b", low): return 2
    return None

# ── Sheet scanning ────────────────────────────────────────────────────────────
def sheet_dates(ws, max_scan_rows=200):
    """Map date -> column index for one worksheet.

    The date header repeats several times down a sheet; every repeat carries the
    same seven dates, so later rows simply confirm the same mapping.
    """
    out = {}
    for r in range(1, min(ws.max_row, max_scan_rows) + 1):
        for c in range(1, min(ws.max_column, 12) + 1):
            v = ws.cell(r, c).value
            if isinstance(v, (_dt.datetime, _dt.date)):
                d = v.date() if isinstance(v, _dt.datetime) else v
                out.setdefault(d, c)
    return out

def index_workbook(wb):
    """Build {date: [(sheet_name, col), ...]} across the whole workbook."""
    idx = {}
    for ws in wb.worksheets:
        for d, c in sheet_dates(ws).items():
            idx.setdefault(d, []).append((ws.title, c))
    return idx

def available_dates(wb):
    return sorted(index_workbook(wb).keys())

def parse_day(ws, col):
    """Read one day column and return the people found, by section.

    Returns a list of dicts: name, section, building (housekeepers only),
    raw cell text, kind, present, daily_service.
    """
    people = []
    section = None          # ("hk", 1|2|3) | ("rqs", None) | ("other", label) | None
    for r in range(1, ws.max_row + 1):
        label_raw = ws.cell(r, 1).value
        label = _norm(label_raw)
        if label in SKIP_LABELS or label.startswith("schedule subject to change"):
            continue
        if label.startswith("please, assign to each"):
            continue
        if label in HK_SECTIONS:
            section = ("hk", HK_SECTIONS[label]); continue
        if label == RQS_SECTION:
            section = ("rqs", None); continue
        matched_other = next((v for k, v in OTHER_SECTIONS.items() if label.startswith(k)), None)
        if matched_other:
            section = ("other", matched_other); continue
        if section is None or not label:
            continue
        # A date row in column A would already have been skipped as non-text.
        if isinstance(label_raw, (_dt.datetime, _dt.date)):
            continue
        raw = ws.cell(r, col).value
        raw = re.sub(r"\s+", " ", str(raw or "").strip())
        kind = classify(raw)
        kindsec, bld = section
        people.append({
            "name":     re.sub(r"\s+", " ", str(label_raw).strip()),
            "section":  {"hk": f"Building {bld}", "rqs": "RQS", "other": bld}[kindsec],
            "group":    kindsec,
            "building": bld if kindsec == "hk" else None,
            "raw":      raw,
            "kind":     kind,
            "present":  kind in PRESENT_KINDS,
            "daily_service": kind == KIND_DAILY,
        })
    return people

#: Weekly summary rows near the top of every sheet, keyed by their column-A label.
METRIC_LABELS = OrderedDict([
    ("hskp actual #", "HSKP on schedule"),
    ("hskp needed",   "HSKP needed"),
    ("daily services","Daily services"),
    ("check outs",    "Check outs"),
    ("rqs needed",    "RQS needed"),
])

def day_metrics(ws, col):
    """Read the sheet's own headcount figures for one day.

    These are the manager's numbers, not ours — showing them next to what we
    parsed makes a miscount obvious at a glance.
    """
    out = OrderedDict()
    for r in range(1, min(ws.max_row, 40) + 1):
        label = _norm(ws.cell(r, 1).value)
        if label in METRIC_LABELS and METRIC_LABELS[label] not in out:
            v = ws.cell(r, col).value
            if isinstance(v, (int, float)):
                out[METRIC_LABELS[label]] = round(float(v), 2)
    return out

def parse_sheet_for_date(wb, sheet_name, target_date):
    """Parse one named sheet for one date. Raises ValueError if absent."""
    ws = wb[sheet_name]
    col = sheet_dates(ws).get(target_date)
    if col is None:
        raise ValueError(f"{target_date} is not in sheet {sheet_name!r}")
    return parse_day(ws, col)

# ── Turning parsed people into scheduler state ────────────────────────────────
def build_roster_update(people, existing_roster=None):
    """Produce the hk_roster / inspector / ds_team / RQS values for a day.

    Existing roster names win on SPELLING when they match case-insensitively,
    so live room tracking keyed by housekeeper name keeps working. The sheet
    still wins on BUILDING, which is the whole point of importing it.
    """
    existing_roster = existing_roster or {}
    by_norm = {norm_name(n): n for n in existing_roster}

    hk_roster, ds_team, changes, new_people = {}, [], [], []
    inspectors, rqs = {}, {1: "", 2: ""}
    others, unknown = [], []

    for p in people:
        if p["kind"] == KIND_UNKNOWN and p["raw"]:
            unknown.append((p["name"], p["raw"]))
        if p["group"] == "hk":
            canonical = by_norm.get(norm_name(p["name"]), p["name"])
            old = existing_roster.get(canonical, {})
            if old and old.get("building") not in (None, p["building"]):
                changes.append((canonical, old.get("building"), p["building"]))
            if not old:
                new_people.append(canonical)
            hk_roster[canonical] = {"building": p["building"], "present": p["present"]}
            if p["daily_service"]:
                ds_team.append(canonical)
        elif p["group"] == "rqs":
            inspectors[p["name"]] = p["present"]
            role = rqs_role(p["raw"])
            if role and p["present"] and not rqs[role]:
                rqs[role] = p["name"]
        else:
            others.append(p)

    return {
        "hk_roster":   hk_roster,
        "ds_team":     ds_team,
        "insp_roster": inspectors,
        "rqs1":        rqs[1],
        "rqs2":        rqs[2],
        "building_changes": changes,
        "new_people":  new_people,
        "others":      others,
        "unknown":     unknown,
    }
