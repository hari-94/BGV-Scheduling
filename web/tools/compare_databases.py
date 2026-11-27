"""
compare_databases.py -- are Supabase and D1 the same, row for row?

Step 3 of docs/CLOUDFLARE_MIGRATION.md writes every change to both databases
(d1store.TeeClient copies each stored row exactly, ids and times included),
so they should be identical. This reads every v1 table from both, compares
row by primary key, then reads the differing rows again after a pause: a row
saved while the comparison ran shows up once and is not drift. Read-only on
both databases.

    python web/tools/compare_databases.py [--secrets PATH] [--settle 20]

Exit status 0 when they match, 1 when a difference survives the re-read.
Keys of sign-in sessions are never printed.
"""
import argparse
import json
import sys
import time

# copy_from_supabase puts the repo root on sys.path, so it is imported first
from copy_from_supabase import TABLES, cf_token, export_table, supabase_creds

import appsecrets
import d1store


def _key(row: dict, pk: str):
    return row.get(pk)


def _shown(key) -> str:
    text = str(key)
    return "session_(hidden)" if text.startswith("session_") else text


def _canon(row: dict, cols: list[str]) -> str:
    return json.dumps([row.get(c) for c in cols], sort_keys=True, ensure_ascii=False, default=str)


def differences(left: list[dict], right: list[dict], pk: str, cols: list[str]) -> set:
    a = {_key(r, pk): _canon(r, cols) for r in left}
    b = {_key(r, pk): _canon(r, cols) for r in right}
    return {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}


def read_rows(url, key, d1, table, pk, cols, only=None):
    """Both databases' rows of one table (all of them, or just the keys in `only`)."""
    if only is None:
        sb = export_table(url, key, table, pk)
        dd = d1.table(table).select(",".join(cols)).execute().data
    else:
        wanted = sorted(only, key=str)
        sb = [r for r in export_table(url, key, table, pk) if _key(r, pk) in only]
        dd = d1.table(table).select(",".join(cols)).in_(pk, wanted).execute().data
    return sb, dd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--secrets", help="a secrets.toml with SUPABASE_URL and SUPABASE_KEY")
    ap.add_argument("--settle", type=float, default=20.0, help="seconds before re-reading differences")
    args = ap.parse_args()

    url, key = supabase_creds(args.secrets)
    d1 = d1store.D1Client(appsecrets.get("D1_API_TOKEN") or cf_token())

    suspects = {}
    for table, (pk, cols) in TABLES.items():
        sb, dd = read_rows(url, key, d1, table, pk, cols)
        diff = differences(sb, dd, pk, cols)
        if diff:
            suspects[table] = diff
        print(f"read  {table:14s} supabase {len(sb):6d}  d1 {len(dd):6d}  differing {len(diff)}")

    if suspects:
        time.sleep(args.settle)
    drift = 0
    for table, keys in suspects.items():
        pk, cols = TABLES[table]
        sb, dd = read_rows(url, key, d1, table, pk, cols, only=keys)
        still = differences(sb, dd, pk, cols)
        drift += len(still)
        shown = ", ".join(sorted({_shown(k) for k in still}, key=str)[:10])
        print(f"again {table:14s} {len(still)} still differ" + (f": {shown}" if still else ""))

    print("SAME" if drift == 0 else f"DIFFERENT: {drift} rows")
    sys.exit(0 if drift == 0 else 1)


if __name__ == "__main__":
    main()
