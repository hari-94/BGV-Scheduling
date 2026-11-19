"""
arrival_mail.py — the safety net under the "Save Arrival Report to SharePoint"
flow (Hari, 14 Nov).

The flow saves the front desk's e-mail (any subject with "Arrival", in Hari's
Inbox) into the Arrival Reports folder, where the 5 AM build and the 7:30
Teams notes read it. After the Outlook outage of 12 Nov its trigger stopped
firing -- no failed runs, no runs at all -- and for three nights the report
reached the inbox and never the folder; 14 Nov was built without it.
Turning the flow off and on brought it back. This module is the net for the
next time: when the next day's report still isn't in the folder late in the
evening, the office PC opens Outlook in the agent's own signed-in browser
profile (the one SharePoint reads use), finds the newest message whose
subject has "Arrival" and the day's date, and saves its text to the folder
as "Arrival Report MM-DD-YYYY (from Outlook).txt".

Every fetch is recorded under KEY, so agent_watch can say that the flow
missed one and wants turning off and on.

Uses the browser lock in sharepoint.py: two Chromes can't share the profile.
"""
import datetime as _dt
import os
import re
import time
from pathlib import Path

import clock
import db

KEY = "arrival_fetch"
PROFILE = os.path.join(os.path.expanduser("~"), ".bgv-agent", "pa-browser")
OWA = "https://outlook.office.com/mail/inbox"


def _subject_day(label: str, day: _dt.date) -> bool:
    """Whether an Outlook list entry's text names `day`: "Arrivals 11/15",
    "Arrival Report 11/14/26", "Arrivals Report 11/12/2026". Only a
    slash-written month/day counts -- the entry also carries the time it
    came in ("10:09 PM"), which a looser reader took for a year -- and only
    the first date, the subject's: an older message also shows the day it
    arrived after it ("Arrivals report 11/11/26 Tue 11/10")."""
    m = re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/:])", label)
    if not m:
        return False
    mo, d, y = int(m.group(1)), int(m.group(2)), m.group(3)
    return (mo, d) == (day.month, day.day) and (y is None or int(y) % 100 == day.year % 100)


def fetch(day: _dt.date, folder, log=print, headless=True):
    """Save `day`'s Arrival Report from Outlook into `folder`. Returns the
    record written under KEY: status "saved" (with file, subject), "none"
    (no such e-mail yet) or "error"."""
    import sharepoint
    rec = {"date": day.isoformat(), "at": clock.stamp()}
    if not sharepoint._ONE_AT_A_TIME.acquire(timeout=150):
        rec.update(status="error", why="the browser profile is busy")
        return rec
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(PROFILE, channel="chrome", headless=headless,
                                                       viewport={"width": 1500, "height": 1000})
            try:
                pg = ctx.pages[0] if ctx.pages else ctx.new_page()
                pg.goto(OWA, timeout=90000)
                box = pg.locator("#topSearchInput, input[aria-label*='Search']").first
                box.wait_for(timeout=90000)
                time.sleep(3)
                box.click()
                box.fill("subject:Arrival")
                pg.keyboard.press("Enter")
                time.sleep(10)
                opts = pg.locator("[role=option]")
                hit = None
                for i in range(min(opts.count(), 15)):
                    lab = opts.nth(i).get_attribute("aria-label") or opts.nth(i).inner_text()
                    if "arriv" in lab.lower() and _subject_day(lab, day):
                        hit = (opts.nth(i), lab)
                        break
                if not hit:
                    rec.update(status="none", why="no e-mail with 'Arrival' and that date in the Inbox yet")
                    return rec
                hit[0].click()
                time.sleep(6)
                body = pg.locator("[aria-label='Message body'], div[role=document]").first.inner_text()
            finally:
                ctx.close()
        rooms = len(set(re.findall(r"\b\d{4}[A-Ia-i]+\b", body)))
        if rooms < 3:
            rec.update(status="error", why=f"the e-mail's text looks empty ({len(body)} characters)")
            return rec
        name = f"Arrival Report {day:%m-%d-%Y} (from Outlook).txt"
        path = Path(folder) / name
        subject = hit[1][:120]
        path.write_text(f"Saved from Outlook by the office PC: {subject}\n\n{body}", encoding="utf-8")
        rec.update(status="saved", file=name, subject=subject, rooms=rooms)
        log(f"arrival report {day}: saved from Outlook ({rooms} room codes) -- "
            f"the Save Arrival Report flow didn't save it")
        return rec
    except Exception as ex:
        rec.update(status="error", why=f"{type(ex).__name__}: {str(ex)[:200]}")
        return rec
    finally:
        sharepoint._ONE_AT_A_TIME.release()
        try:
            db._upsert_key(KEY, rec)
        except Exception:
            pass
