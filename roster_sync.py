"""
roster_sync.py — store a Schedule.xlsx the way Roster Import's Save does.

Two callers, one path: the Upload & sync tab, when somebody presses Save, and
hotsos_agent.py, when the SharePoint-synced Schedule.xlsx changes on the
office PC. Keeping the save in one place is what stops an automatic import
from storing something the page would not have.

No Streamlit here.
"""
import datetime
import io

import clock
import db
import roster_import as ri


def parse(raw: bytes):
    """(weeks, number of sheets). Opened twice: openpyxl gives cached values OR
    styles, never both, and the red no-call fills are styles."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    try:
        wbs = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)
    except Exception:
        wbs = None
    return ri.parse_all_weeks(wb, wbs), len(wb.worksheets)


def touches_day(d, incoming, day_iso: str) -> bool:
    """Whether a diff changes who works on `day_iso`."""
    for wk in d["new_weeks"]:
        if day_iso in incoming[wk].get("dates", []):
            return True
    for wk, dd in d["changed_weeks"].items():
        if any(ch["date"] == day_iso for ch in dd["changed"]):
            return True
        if (dd["added_people"] or dd["removed_people"]) and \
                day_iso in incoming[wk].get("dates", []):
            return True
    return False


def save(raw: bytes, file_name: str, by: str, incoming=None, n_sheets=None,
         stored=None, reset_today="always"):
    """Write the new and changed weeks, the meta row and the workbook itself.

    `reset_today` decides whether today's attendance is re-applied on the
    Schedule page's next load: "always" (a person pressed Save, as before),
    or "if_today_changed" (the agent). Re-applying wipes any roster fixes made
    in the app since the morning, so an automatic import that only moved next
    week must not do it.

    Returns {"saved", "failed", "diff", "today_changed"}.
    """
    if incoming is None:
        incoming, n_sheets = parse(raw)
    if not incoming:
        raise ValueError("No dated sheets found -- is this the weekly schedule workbook?")
    # The sheet keeps whatever spelling the team types; what's stored is the
    # HotSOS full name (staff_names). Idempotent, so a caller that already
    # renamed (Roster Import, for its diff) loses nothing.
    import staff_names
    incoming = staff_names.rename_weeks(incoming, staff_names.aliases())
    stored = db.load_staff_weeks() if stored is None else stored
    d = ri.diff_all(stored, incoming)
    touched = set(d["new_weeks"]) | set(d["changed_weeks"])
    to_write = touched if stored else set(incoming)
    ok, failed = 0, []
    for wk in sorted(to_write):
        try:
            db.save_staff_week(wk, incoming[wk])
            ok += 1
        except Exception as ex:
            failed.append(f"{wk}: {ex}")
    all_dates = sorted(x for w in incoming.values() for x in w["dates"])
    try:
        db.save_staff_meta({
            "uploaded_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "uploaded_by": by,
            "file_name":   file_name,
            "n_sheets":    n_sheets,
            "n_weeks":     len(incoming),
            "date_min":    all_dates[0] if all_dates else "",
            "date_max":    all_dates[-1] if all_dates else "",
            "last_diff": {
                "new_weeks": d["new_weeks"],
                "n_changed_cells": d["n_changed_cells"],
                # Bounded so the meta row stays small.
                "changed": [
                    {"week": wk, **ch}
                    for wk, dd in sorted(d["changed_weeks"].items())
                    for ch in dd["changed"]][:500],
            },
        })
    except Exception as ex:
        failed.append(f"meta: {ex}")
    # Keep the workbook itself so the Excel export works any day, not only in
    # a session where someone happened to upload it.
    try:
        db.save_staff_file(raw, file_name)
    except Exception as ex:
        failed.append(f"workbook: {ex}")
    today_changed = touches_day(d, incoming, clock.today_iso())
    if reset_today == "always" or today_changed:
        try:
            db.save_autoapply({})
        except Exception:
            pass
    return {"saved": ok, "failed": failed, "diff": d, "today_changed": today_changed}
