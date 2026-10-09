"""
freetier.py — keep the app inside the free plans, and prove it.

The app runs on Supabase's free plan and Streamlit Community Cloud's, and is
meant to stay there. Their ceilings, as published:

  * Supabase free: 500 MB of database, 5 GB a month of egress (data sent out).
  * Streamlit Community Cloud: 690 MB of memory guaranteed (2.7 GB at most,
    when the platform has it to spare -- not something to plan on).

Three things here:

  1. A meter. Every read that goes over the wire is counted, roughly, in the
     process that made it -- the Cloud app, the office PC agent, the forecast
     run -- and each flushes its count to `usage_<YYYY-MM>_<source>` every ten
     minutes. The bytes are estimated from the JSON size at the ratio gzip
     achieved on this data (measured 9 Oct: 2.3 MB of staff weeks went over
     as 303 KB, 13%; small rows compress less, so 25% is used). An estimate,
     erring high.
  2. Memory. The Cloud app records its own resident memory on each page and
     keeps the day's peak; past 85% of the guaranteed 690 MB it drops its
     caches.
  3. Storage, nightly (office PC, 2 AM). The database's size is measured,
     and old data past its retention is written to a file in SharePoint (the
     synced "App Archive" folder beside the inspection workbooks) -- read
     back to make sure it's whole -- and only then deleted. Retention halves
     when the database passes 60% of its limit. Expired sign-in sessions are
     deleted without a copy: they are tokens, not records, and a file of them
     would only be a way into the app.
"""
import datetime as _dt
import gc
import json
import sys
import threading
import time
from pathlib import Path

import clock
import db

DB_LIMIT_MB = 500
EGRESS_LIMIT_MB = 5 * 1024
MEMORY_LIMIT_MB = 690
WARN, ACT = 0.70, 0.85
GZIP_RATIO = 0.25
STATUS_KEY = "freetier_status"
USAGE_PREFIX = "usage_"

#: days kept in the database (normal, under pressure); older goes to the archive
RETENTION = {
    "schedule_full": (365, 90),     # a day's charts: Dashboard history
    "room_status": (365, 90),       # a day's room marks
    "login_events": (180, 60),      # sign-ins
    "ssrs_rooms": (7, 3),           # the saved SSRS day copies
}

# ── 1. the meter ─────────────────────────────────────────────────────────────
_lock = threading.Lock()
_meter = {"bytes": 0, "calls": 0, "flushed": time.time()}


def count(result):
    try:
        n = len(json.dumps(result, default=str))
    except Exception:
        n = 0
    with _lock:
        _meter["bytes"] += int(n * GZIP_RATIO) + 300      # + headers
        _meter["calls"] += 1


def flush(source: str, every: int = 600, force=False):
    """Add this process's count since the last flush to the month's total."""
    with _lock:
        if not force and time.time() - _meter["flushed"] < every:
            return
        b, c = _meter["bytes"], _meter["calls"]
        _meter["bytes"] = _meter["calls"] = 0
        _meter["flushed"] = time.time()
    if not (b or c):
        return
    key = f"{USAGE_PREFIX}{clock.today():%Y-%m}_{source}"
    try:
        cur = db._load_key(key) or {}
        days = cur.get("days") or {}
        d = clock.today_iso()
        days[d] = int(days.get(d, 0)) + b              # for the Stats page's chart
        cur.update(bytes=int(cur.get("bytes", 0)) + b, calls=int(cur.get("calls", 0)) + c,
                   days=days, updated=clock.stamp())
        db._upsert_key(key, cur)
    except Exception as ex:
        print(f"[freetier] usage not saved: {ex}")
        with _lock:                        # keep it for next time
            _meter["bytes"] += b
            _meter["calls"] += c


def daily_usage(month=None) -> dict:
    """{source: {date: MB}} for the month, for a chart."""
    month = month or f"{clock.today():%Y-%m}"
    out = {}
    for r in db._like_keys(f"{USAGE_PREFIX}{month}_", with_payload=True):
        p = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"] or "{}")
        out[r["key"].rsplit("_", 1)[-1]] = {d: round(v / 2**20, 2)
                                            for d, v in (p.get("days") or {}).items()}
    return out


def month_usage(month=None) -> dict:
    """{source: MB} and the total, for the month's egress so far."""
    month = month or f"{clock.today():%Y-%m}"
    out = {}
    for r in db._like_keys(f"{USAGE_PREFIX}{month}_", with_payload=True):
        p = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"] or "{}")
        out[r["key"].rsplit("_", 1)[-1]] = round(int(p.get("bytes", 0)) / 2**20, 1)
    out["total"] = round(sum(out.values()), 1)
    return out


# ── 2. memory (the Cloud app) ────────────────────────────────────────────────
_mem = {"peak": 0.0, "day": None, "cleared": None, "saved": 0.0}


def memory_mb():
    try:                                   # Linux, which is what Streamlit Cloud runs
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except Exception:
        return None


#: The Cloud app runs on Linux; the office PC (and its 5 AM build, which runs
#: the app's pages to generate) is Windows. Only the Cloud's own memory and
#: reads count as "app" -- the PC's are the agent's. A diagnostic run here once
#: reported 754 MB as the app's memory.
ON_CLOUD = sys.platform.startswith("linux")


def tick(source="app"):
    """Called on every page: track memory, free it if it's high, flush the
    meter now and then. Cheap -- one small file read, a write every 10 min."""
    if not ON_CLOUD:
        return
    m = memory_mb()
    today = clock.today_iso()
    if _mem["day"] != today:
        _mem.update(day=today, peak=0.0)
    if m:
        _mem["peak"] = max(_mem["peak"], m)
        if m > MEMORY_LIMIT_MB * ACT:
            try:
                import streamlit as st
                st.cache_data.clear()
            except Exception:
                pass
            db._weeks_forget()
            gc.collect()
            _mem["cleared"] = clock.stamp()
    if time.time() - _mem["saved"] > 600:
        _mem["saved"] = time.time()
        flush(source, force=True)
        try:
            key = f"{USAGE_PREFIX}memory_{source}"
            prev = db._load_key(key) or {}
            samples = (prev.get("samples") or [])[-143:]     # a day at 10-minute steps
            samples.append([clock.stamp(), round(m or 0, 1)])
            db._upsert_key(key, {
                "now_mb": round(m or 0, 1), "peak_mb": round(_mem["peak"], 1), "day": today,
                "caches_cleared": _mem["cleared"], "at": clock.stamp(), "samples": samples})
        except Exception:
            pass


# ── 3. storage: measure, archive, delete ─────────────────────────────────────
def _size_of(rows):
    return sum(len(json.dumps(r, default=str)) for r in rows)


def _all(query):
    """Every row of a query; PostgREST hands back 1,000 at a time."""
    out, i = [], 0
    while True:
        page = query().range(i, i + 999).execute().data or []
        out += page
        if len(page) < 1000:
            return out
        i += 1000


def measure() -> dict:
    """Approximate size of what's stored, MB per table (data, not indexes --
    Postgres adds some on top, which the 1.3 below and the thresholds allow for)."""
    c = db._client()
    out = {}
    rows = _all(lambda: c.table(db.SETTINGS_TABLE).select("key,payload"))
    out["app_settings"] = _size_of(rows)
    for table in ("schedule_full", "room_status", "login_events", "app_users"):
        try:
            n = c.table(table).select("*", count="exact").limit(1).execute().count or 0
            sample = c.table(table).select("*").limit(50).execute().data or []
            out[table] = int(_size_of(sample) / max(len(sample), 1) * n)
        except Exception as ex:
            out[table] = 0
            print(f"[freetier] {table} not measured: {ex}")
    mb = {k: round(v / 2**20, 2) for k, v in out.items()}
    mb["total"] = round(sum(out.values()) / 2**20 * 1.3, 1)
    return mb


def _write_verified(path: Path, text: str):
    """Write a file in the synced archive and read it back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path.read_text(encoding="utf-8") != text:
        raise IOError(f"archive copy of {path.name} didn't read back the same")


def _csv(rows, cols):
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return buf.getvalue()


def cleanup(archive_dir, pressure=False, dry_run=False) -> dict:
    """Archive then delete what's past retention. Returns what was done."""
    import csv
    c = db._client()
    root = Path(archive_dir)
    keep = {k: v[1 if pressure else 0] for k, v in RETENTION.items()}
    today = clock.today()
    cut = {k: (today - _dt.timedelta(days=d)).isoformat() for k, d in keep.items()}
    done = {"pressure": pressure, "dry_run": dry_run, "archived": [], "deleted": {},
            "errors": []}

    # a day's charts: one JSON file per day
    try:
        old = _all(lambda: c.table("schedule_full").select("date,payload")
                   .lt("date", cut["schedule_full"]))
        for r in old:
            f = root / "schedules" / f"{r['date']}.json"
            if not dry_run:
                p = r["payload"] if isinstance(r["payload"], str) else json.dumps(r["payload"])
                _write_verified(f, p)
                c.table("schedule_full").delete().eq("date", r["date"]).execute()
            done["archived"].append(str(f.relative_to(root)))
        done["deleted"]["schedule_full"] = len(old)
    except Exception as ex:
        done["errors"].append(f"schedule_full: {ex}")

    # room marks and sign-ins: one CSV per month, merged with any earlier
    # copy; then one delete for everything older than the cut -- only after
    # every month's file has been written and read back.
    for table, datecol in (("room_status", "date"), ("login_events", "ts")):
        try:
            rows = _all(lambda: c.table(table).select("*").lt(datecol, cut[table]))
            if not rows:
                done["deleted"][table] = 0
                continue
            cols = sorted({k for r in rows for k in r if k != "id"})
            by_month = {}
            for r in rows:
                by_month.setdefault(str(r[datecol])[:7], []).append(r)
            for month, rs in sorted(by_month.items()):
                f = root / table / f"{month}.csv"
                if not dry_run:
                    prior = []
                    if f.exists():
                        with f.open(encoding="utf-8") as fh:
                            prior = list(csv.DictReader(fh))
                    _write_verified(f, _csv(prior + rs, cols))
                done["archived"].append(str(f.relative_to(root)))
            if not dry_run:
                c.table(table).delete().lt(datecol, cut[table]).execute()
            done["deleted"][table] = len(rows)
        except Exception as ex:
            done["errors"].append(f"{table}: {ex}")

    # the saved SSRS day copies
    try:
        n = 0
        for r in db._like_keys("ssrs_rooms_", with_payload=True):
            day = r["key"][len("ssrs_rooms_"):]
            if day < cut["ssrs_rooms"]:
                f = root / "ssrs_rooms" / f"{day}.json"
                if not dry_run:
                    p = r["payload"] if isinstance(r["payload"], str) else json.dumps(r["payload"])
                    _write_verified(f, p)
                    db._delete_key(r["key"])
                done["archived"].append(str(f.relative_to(root)))
                n += 1
        done["deleted"]["ssrs_rooms"] = n
    except Exception as ex:
        done["errors"].append(f"ssrs_rooms: {ex}")

    # expired sign-in sessions: deleted, never copied (see the top of the file)
    try:
        n = 0
        now = clock.now()
        for r in db._like_keys("session_", with_payload=True):
            p = r["payload"]
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except Exception:
                    p = {}
            exp = (p or {}).get("expires")
            try:
                gone = bool(exp) and _dt.datetime.fromisoformat(
                    str(exp).replace("Z", "+00:00")) < now
            except ValueError:
                gone = False
            if gone:
                if not dry_run:
                    db._delete_key(r["key"])
                n += 1
        done["deleted"]["expired_sessions"] = n
    except Exception as ex:
        done["errors"].append(f"sessions: {ex}")
    return done


def nightly(archive_dir) -> dict:
    """The office PC's 2 AM job: measure, clean, measure again, record."""
    before = measure()
    pressure = before["total"] > DB_LIMIT_MB * 0.60
    done = cleanup(archive_dir, pressure=pressure)
    after = measure() if any(done["deleted"].values()) else before
    rec = {"at": clock.stamp(), "db_mb": after, "db_mb_before": before["total"],
           "egress_mb": month_usage(), "cleanup": done, "archive_dir": str(archive_dir)}
    db._upsert_key(STATUS_KEY, rec)
    return rec
