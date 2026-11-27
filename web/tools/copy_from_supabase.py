"""
copy_from_supabase.py -- copy the live Supabase database into Cloudflare D1.

Used in steps 1 and 4 of docs/CLOUDFLARE_MIGRATION.md. It only *reads*
Supabase. It replaces whatever is in D1's v1 tables (each is emptied first),
so it can be re-run at any time, and it ends by reading D1 back through the
same client db.py uses and comparing a checksum per table.

    python web/tools/copy_from_supabase.py [--secrets PATH] [--dry-run]

Credentials, none of them stored here:
  * Supabase: SUPABASE_URL and SUPABASE_KEY, found as db.py finds them
    (appsecrets.py), or from the secrets.toml given with --secrets.
  * Cloudflare: CLOUDFLARE_API_TOKEN if set, else this PC's `wrangler login`.

Values are stored exactly as d1store.py stores them (it does the encoding),
so the copy and the live client can't disagree about the format.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB_DIR = REPO / "web"
sys.path.insert(0, str(REPO))

import appsecrets  # noqa: E402  (the repo root is on the path only from here)
import d1store  # noqa: E402

DATABASE_NAME = "bgv"

# table -> (primary-key column used to page through it, columns in order)
TABLES = {
    "app_users": ("id", ["id", "username", "password_hash", "role", "created_at",
                         "last_login", "display_name"]),
    "login_events": ("id", ["id", "username", "display_name", "role", "ts"]),
    "room_status": ("id", ["id", "date", "room", "status", "group_label", "housekeeper",
                           "inspector", "started_at", "cleaned_at", "inspected_at",
                           "marked_clean_at", "notes", "swapped_from", "updated_by",
                           "updated_at"]),
    "schedule_full": ("id", ["id", "date", "payload", "created_at", "updated_at"]),
    "schedule_log": ("id", ["id", "date", "payload", "created_at", "updated_at"]),
    "app_settings": ("key", ["key", "payload", "updated_at"]),
}

STATEMENT_MAX = 90_000   # D1 refuses SQL statements over 100 KB; keep under it
PAGE = 1000


# ── Supabase (read-only) ─────────────────────────────────────────────────────

def supabase_creds(secrets_path: str | None) -> tuple[str, str]:
    if secrets_path:
        data = tomllib.loads(Path(secrets_path).read_text(encoding="utf-8"))
        url, key = data.get("SUPABASE_URL", ""), data.get("SUPABASE_KEY", "")
    else:
        url, key = appsecrets.get("SUPABASE_URL"), appsecrets.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("Supabase credentials not found: set them, or pass --secrets PATH.")
    return url.rstrip("/"), key


def export_table(url: str, key: str, table: str, pk: str) -> list[dict]:
    rows, start = [], 0
    headers = {"apikey": key, "Authorization": "Bearer " + key, "Range-Unit": "items"}
    while True:
        req = urllib.request.Request(f"{url}/rest/v1/{table}?select=*&order={pk}.asc",
                                     headers={**headers, "Range": f"{start}-{start + PAGE - 1}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            page = json.loads(r.read())
        rows += page
        if len(page) < PAGE:
            return rows
        start += PAGE


def read_supabase(url: str, key: str) -> tuple[dict, dict]:
    """Every table's rows, and a checksum of each."""
    data, sums = {}, {}
    for table, (pk, cols) in TABLES.items():
        rows = export_table(url, key, table, pk)
        extra = set().union(*(r.keys() for r in rows)) - set(cols) if rows else set()
        if extra:
            sys.exit(f"{table}: columns not in this copy's table: {sorted(extra)} -- add them first")
        data[table], sums[table] = rows, checksum(rows, cols)
        print(f"read  {table:14s} {len(rows):6d} rows  checksum {sums[table]}")
    return data, sums


def checksum(rows: list[dict], cols: list[str]) -> str:
    """Order-free: Postgres and SQLite sort text keys differently."""
    h = hashlib.sha256()
    for line in sorted(json.dumps([r.get(c) for c in cols], ensure_ascii=False, sort_keys=True,
                                  default=str) for r in rows):
        h.update(line.encode("utf-8"))
    return h.hexdigest()[:16]


# ── D1 ───────────────────────────────────────────────────────────────────────

def cf_token() -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if token:
        return token
    # `whoami` refreshes wrangler's OAuth token if it has lapsed; then read it
    subprocess.run("npx wrangler whoami", shell=True, cwd=WEB_DIR, capture_output=True,
                   check=False, env={**os.environ, "WRANGLER_SEND_METRICS": "false"})
    cfg = Path(os.environ.get("APPDATA", "")) / "xdg.config/.wrangler/config/default.toml"
    match = re.search(r'oauth_token\s*=\s*"([^"]+)"', cfg.read_text(encoding="utf-8"))
    if not match:
        sys.exit("No Cloudflare token: set CLOUDFLARE_API_TOKEN or run `npx wrangler login`.")
    return match.group(1)


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def stored_row(cols: list[str], row: dict) -> list:
    """A Supabase row as D1 keeps it: payloads encoded by d1store, the rest as given."""
    return [d1store.encode_json(row[c]) if c in d1store.JSON_COLUMNS and row.get(c) is not None
            else row.get(c) for c in cols]


def build_statements(data: dict) -> tuple[list[str], list[tuple]]:
    """SQL text for the bulk import, plus rows too long to inline (bound one by one)."""
    statements = [f"DELETE FROM {t};" for t in TABLES]
    too_long = []
    for table, (_pk, cols) in TABLES.items():
        head = f"INSERT INTO {table} ({','.join(cols)}) VALUES "
        chunk, size = [], len(head)
        for row in data[table]:
            values = stored_row(cols, row)
            literal = "(" + ",".join(sql_literal(v) for v in values) + ")"
            n = len(literal.encode("utf-8")) + 1
            if n > STATEMENT_MAX - len(head):
                too_long.append((table, cols, values))
                continue
            if chunk and size + n > STATEMENT_MAX:
                statements.append(head + ",".join(chunk) + ";")
                chunk, size = [], len(head)
            chunk.append(literal)
            size += n
        if chunk:
            statements.append(head + ",".join(chunk) + ";")
    return statements, too_long


def run_sql_file(statements: list[str]) -> None:
    """wrangler's bulk import: one upload, however many statements."""
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write("\n".join(statements))
        path = f.name
    try:
        print(f"write {len(statements)} statements ({Path(path).stat().st_size / 1e6:.1f} MB) ...")
        r = subprocess.run(
            f'npx wrangler d1 execute {DATABASE_NAME} --remote --yes --file "{path}"',
            shell=True, cwd=WEB_DIR, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False,
            env={**os.environ, "WRANGLER_SEND_METRICS": "false", "CI": "1"})
        if r.returncode != 0:
            sys.exit("wrangler d1 execute failed:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    finally:
        os.unlink(path)


def verify(d1: d1store.D1Client, data: dict, sums: dict) -> bool:
    """Reads every table back through d1store and compares checksums."""
    ok = True
    for table, (pk, cols) in TABLES.items():
        back = d1.table(table).select(",".join(cols)).order(pk).execute().data
        same = len(back) == len(data[table]) and checksum(back, cols) == sums[table]
        ok &= same
        print(f"check {table:14s} {len(back):6d} rows  {'same' if same else 'DIFFERENT'}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--secrets", help="a secrets.toml with SUPABASE_URL and SUPABASE_KEY")
    ap.add_argument("--dry-run", action="store_true", help="read and report; write nothing")
    args = ap.parse_args()

    data, sums = read_supabase(*supabase_creds(args.secrets))
    if args.dry_run:
        return
    statements, too_long = build_statements(data)
    run_sql_file(statements)
    d1 = d1store.D1Client(cf_token())
    for table, cols, values in too_long:
        d1.run(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
               values)
    if too_long:
        print(f"write {len(too_long)} long rows one at a time")
    sys.exit(0 if verify(d1, data, sums) else 1)


if __name__ == "__main__":
    main()
