"""
d1store.py -- Cloudflare D1 for db.py, through the calls db.py already makes
on Supabase's client (docs/CLOUDFLARE_MIGRATION.md, step 2).

    d1 = D1Client.from_secrets()
    d1.table("app_settings").select("key,payload").eq("key", "roster").execute().data

It speaks the part of the supabase-py query builder this codebase uses --
select / insert / upsert / update / delete; eq, neq, lt, lte, gt, gte, like,
in_; order, limit, range; count="exact" -- and answers as Supabase would: the
same rows in `.data`, `.count`, jsonb columns decoded. Anything else raises
AttributeError instead of guessing.

What it copies from the Supabase *database*, not only its API:
  * `updated_at` is stamped on every write to the tables whose triggers did
    it (STAMPED); ids and other defaults come from the D1 table definitions.
  * Timestamps are stored the way Postgres' timestamptz gives them back: in
    UTC, '+00:00', trailing zeros of the fraction dropped. A naive time is
    taken as UTC, as Supabase's session does. Code that compares or parses
    them sees no difference.
  * An UPDATE or DELETE without a filter is refused, like Supabase's
    safe-update guard.
  * A payload over 1 MB is stored compressed (D1 refuses rows over 2 MB) and
    expanded on the way out -- web/tools/copy_from_supabase.py stores it the
    same way.

Two differences, on purpose:
  * A `like` that is a plain prefix ('staffweek_*') becomes a key range, which
    reads only the matching rows; LIKE reads the whole table (measured: 643
    rows against 1). The prefix is taken literally: '_' is a character, not
    the one-character wildcard it is in SQL.
  * Other patterns use GLOB, which is case-sensitive like Postgres' LIKE.

It uses the D1 REST API rather than a Worker, so the PCs and Streamlit don't
spend the Worker's 100,000 requests a day. `client()` at the bottom is what
db._client() returns: Supabase, D1, or both, by the database mode.
"""
from __future__ import annotations

import base64
import functools
import gzip
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

import appsecrets

ACCOUNT_ID = "5203a9b813c556e90a14110cb9613e53"
DATABASE_ID = "f105d97e-4c45-45c1-84f2-1d00ee819f14"

JSON_COLUMNS = frozenset({"payload"})
#: Postgres timestamptz columns (web/migrations/0001_init.sql).
TIMESTAMP_COLUMNS = frozenset({"created_at", "updated_at", "last_login", "ts", "started_at",
                               "cleaned_at", "inspected_at", "marked_clean_at"})
#: Tables whose updated_at Supabase set with a trigger on every write.
STAMPED = frozenset({"app_settings", "schedule_full", "schedule_log", "room_status"})
#: The upsert key when the caller names none (Supabase uses the primary key).
PRIMARY_KEYS = {"app_settings": ("key",)}
BIG = 1_000_000

_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def _quote(name: str) -> str:
    """A table or column name, checked and quoted: names never come from users."""
    if not _NAME.match(name):
        raise ValueError(f"not a table or column name: {name!r}")
    return f'"{name}"'


def pg_timestamp(moment: datetime) -> str:
    """`moment` as Postgres prints a timestamptz: UTC, '+00:00', no trailing zeros."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    text = moment.astimezone(timezone.utc).isoformat(timespec="microseconds")
    stamp, offset = text[:-6], text[-6:]
    if "." in stamp:
        stamp = stamp.rstrip("0").rstrip(".")
    return stamp + offset


def now_iso() -> str:
    return pg_timestamp(datetime.now(timezone.utc))


def _as_timestamp(value: Any) -> Any:
    """A time written to a timestamptz column, normalised as Postgres would store it."""
    if isinstance(value, datetime):
        return pg_timestamp(value)
    if isinstance(value, str) and value:
        try:
            return pg_timestamp(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return value  # not a time: Postgres would have refused it; let D1 store it as given
    return value


def encode_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    if len(text.encode("utf-8")) > BIG:
        packed = gzip.compress(text.encode("utf-8"), 9)
        text = "gz:" + base64.b64encode(packed).decode("ascii")
    return text


def decode_json(text: str | None) -> Any:
    if text is None:
        return None
    if text.startswith("gz:"):
        text = gzip.decompress(base64.b64decode(text[3:])).decode("utf-8")
    return json.loads(text)


@dataclass
class Result:
    """What .execute() returns, shaped like supabase-py's APIResponse."""
    data: list[dict]
    count: int | None = None


class D1Error(RuntimeError):
    pass


# ── the client ───────────────────────────────────────────────────────────────

class D1Client:
    #: 429s and 5xx are retried; a transport error too (a retried INSERT can,
    #: rarely, land twice -- only login_events is plain INSERT, and a doubled
    #: sign-in line is harmless).
    TRIES = 4

    def __init__(self, token: str, account_id: str = ACCOUNT_ID,
                 database_id: str = DATABASE_ID, http: httpx.Client | None = None):
        self._url = (f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
                     f"/d1/database/{database_id}/query")
        self._http = http or httpx.Client(
            timeout=20.0, headers={"Authorization": f"Bearer {token}"})

    @classmethod
    def from_secrets(cls) -> D1Client:
        token = appsecrets.get("D1_API_TOKEN")
        if not token:
            raise RuntimeError("Missing D1_API_TOKEN (environment, .streamlit/secrets.toml "
                               "or Streamlit Cloud's Secrets).")
        return cls(token, appsecrets.get("D1_ACCOUNT_ID") or ACCOUNT_ID,
                   appsecrets.get("D1_DATABASE_ID") or DATABASE_ID)

    def table(self, name: str) -> Query:
        return Query(self, name)

    def run(self, sql: str, params: list | tuple = ()) -> list[dict]:
        """One statement; its rows."""
        body = {"sql": sql, "params": list(params)}
        last: Exception | None = None
        for attempt in range(self.TRIES):
            if attempt:
                time.sleep(0.5 * 2 ** (attempt - 1))
            try:
                r = self._http.post(self._url, json=body)
            except httpx.TransportError as ex:
                last = ex
                continue
            if r.status_code == 200:
                return r.json()["result"][0]["results"]
            last = D1Error(_error_text(r))
            if r.status_code != 429 and r.status_code < 500:
                raise last
        raise D1Error(f"D1 didn't answer after {self.TRIES} tries: {last}")


def _error_text(r: httpx.Response) -> str:
    try:
        errors = r.json().get("errors") or []
        return "; ".join(str(e.get("message", e)) for e in errors) or f"HTTP {r.status_code}"
    except ValueError:
        return f"HTTP {r.status_code}: {r.text[:200]}"


# ── the query builder ────────────────────────────────────────────────────────

@dataclass
class Query:
    client: D1Client
    table_name: str
    _op: str = "select"
    _columns: str = "*"
    _count: bool = False
    _rows: list[dict] = field(default_factory=list)
    _values: dict = field(default_factory=dict)
    _conflict: tuple[str, ...] = ()
    _where: list[str] = field(default_factory=list)
    _params: list = field(default_factory=list)
    _order: list[str] = field(default_factory=list)
    _limit: int | None = None
    _offset: int | None = None

    # what to do
    def select(self, columns: str = "*", count: str | None = None) -> Query:
        if count not in (None, "exact"):
            raise ValueError(f"count={count!r}: only 'exact' is supported")
        self._op, self._columns, self._count = "select", columns, count == "exact"
        return self

    def insert(self, rows: dict | list[dict]) -> Query:
        self._op, self._rows = "insert", _as_rows(rows)
        return self

    def upsert(self, rows: dict | list[dict], on_conflict: str | None = None) -> Query:
        self._op, self._rows = "upsert", _as_rows(rows)
        self._conflict = (tuple(c.strip() for c in on_conflict.split(",")) if on_conflict
                          else PRIMARY_KEYS.get(self.table_name, ("id",)))
        return self

    def update(self, values: dict) -> Query:
        self._op, self._values = "update", dict(values)
        return self

    def delete(self) -> Query:
        self._op = "delete"
        return self

    # which rows
    def _compare(self, column: str, op: str, value: Any) -> Query:
        self._where.append(f"{_quote(column)} {op} ?")
        self._params.append(_bind(column, value))
        return self

    def eq(self, column: str, value: Any) -> Query:
        return self._compare(column, "=", value)

    def neq(self, column: str, value: Any) -> Query:
        return self._compare(column, "<>", value)

    def lt(self, column: str, value: Any) -> Query:
        return self._compare(column, "<", value)

    def lte(self, column: str, value: Any) -> Query:
        return self._compare(column, "<=", value)

    def gt(self, column: str, value: Any) -> Query:
        return self._compare(column, ">", value)

    def gte(self, column: str, value: Any) -> Query:
        return self._compare(column, ">=", value)

    def like(self, column: str, pattern: str) -> Query:
        pattern = pattern.replace("*", "%")
        head = pattern[:-1]
        if pattern.endswith("%") and "%" not in head:
            if head:
                self._where.append(f"{_quote(column)} >= ? AND {_quote(column)} < ?")
                self._params += [head, head[:-1] + chr(ord(head[-1]) + 1)]
        else:
            self._where.append(f"{_quote(column)} GLOB ?")
            self._params.append(_like_to_glob(pattern))
        return self

    def in_(self, column: str, values) -> Query:
        # one bound value however long the list: D1 allows 100 per statement
        self._where.append(f"{_quote(column)} IN (SELECT value FROM json_each(?))")
        self._params.append(json.dumps(list(values)))
        return self

    # how many, in what order
    def order(self, column: str, desc: bool = False) -> Query:
        # Postgres puts NULLs last going up and first going down
        self._order.append(f"{_quote(column)} {'DESC NULLS FIRST' if desc else 'ASC NULLS LAST'}")
        return self

    def limit(self, n: int) -> Query:
        self._limit = int(n)
        return self

    def range(self, start: int, end: int) -> Query:
        self._offset, self._limit = int(start), int(end) - int(start) + 1
        return self

    # run it
    def execute(self) -> Result:
        return getattr(self, f"_run_{self._op}")()

    def _where_sql(self) -> str:
        return f" WHERE {' AND '.join(self._where)}" if self._where else ""

    def _run_select(self) -> Result:
        columns = ("*" if self._columns.strip() == "*"
                   else ", ".join(_quote(c.strip()) for c in self._columns.split(",")))
        total = ", count(*) OVER () AS __total" if self._count else ""
        sql = f"SELECT {columns}{total} FROM {_quote(self.table_name)}{self._where_sql()}"
        if self._order:
            sql += " ORDER BY " + ", ".join(self._order)
        if self._limit is not None:
            sql += f" LIMIT {self._limit}"
        if self._offset:
            sql += f" OFFSET {self._offset}"
        rows = self.client.run(sql, self._params)
        count = None
        if self._count:
            count = rows[0]["__total"] if rows else self._count_all()
            for r in rows:
                r.pop("__total", None)
        return Result([_decode_row(r) for r in rows], count)

    def _count_all(self) -> int:
        """The count when the page asked for is past the last row."""
        if not self._offset:
            return 0
        sql = f"SELECT count(*) AS n FROM {_quote(self.table_name)}{self._where_sql()}"
        return self.client.run(sql, self._params)[0]["n"]

    def _run_insert(self) -> Result:
        return self._write_rows(upsert=False)

    def _run_upsert(self) -> Result:
        return self._write_rows(upsert=True)

    def _write_rows(self, upsert: bool) -> Result:
        if not self._rows:
            return Result([])
        columns: list[str] = []
        for row in self._rows:
            columns += [c for c in row if c not in columns]
        stamp = self.table_name in STAMPED and "updated_at" not in columns
        if stamp:
            columns.append("updated_at")
        now = now_iso()
        packed = json.dumps([[now if (stamp and c == "updated_at") else _bind(c, row.get(c))
                              for c in columns] for row in self._rows], ensure_ascii=False)
        picks = ", ".join(f"json_extract(value, '$[{i}]')" for i in range(len(columns)))
        sql = (f"INSERT INTO {_quote(self.table_name)} ({', '.join(map(_quote, columns))}) "
               f"SELECT {picks} FROM json_each(?) WHERE true")
        if upsert:
            changes = [f"{_quote(c)} = excluded.{_quote(c)}"
                       for c in columns if c not in self._conflict]
            target = ", ".join(map(_quote, self._conflict))
            sql += (f" ON CONFLICT ({target}) DO UPDATE SET {', '.join(changes)}" if changes
                    else f" ON CONFLICT ({target}) DO NOTHING")
        rows = self.client.run(sql + " RETURNING *", [packed])
        return Result([_decode_row(r) for r in rows])

    def _run_update(self) -> Result:
        self._refuse_unfiltered()
        values = dict(self._values)
        if self.table_name in STAMPED and "updated_at" not in values:
            values["updated_at"] = now_iso()
        sets = ", ".join(f"{_quote(c)} = ?" for c in values)
        params = [_bind(c, v) for c, v in values.items()] + self._params
        rows = self.client.run(
            f"UPDATE {_quote(self.table_name)} SET {sets}{self._where_sql()} RETURNING *", params)
        return Result([_decode_row(r) for r in rows])

    def _run_delete(self) -> Result:
        self._refuse_unfiltered()
        rows = self.client.run(
            f"DELETE FROM {_quote(self.table_name)}{self._where_sql()} RETURNING *", self._params)
        return Result([_decode_row(r) for r in rows])

    def _refuse_unfiltered(self) -> None:
        if not self._where:
            raise D1Error(f"{self._op} on {self.table_name} without a filter is refused")


def _as_rows(rows: dict | list[dict]) -> list[dict]:
    return [rows] if isinstance(rows, dict) else list(rows)


def _bind(column: str, value: Any) -> Any:
    if column in JSON_COLUMNS:
        return encode_json(value)
    if column in TIMESTAMP_COLUMNS:
        return _as_timestamp(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _decode_row(row: dict) -> dict:
    return {k: decode_json(v) if k in JSON_COLUMNS else v for k, v in row.items()}


def _like_to_glob(pattern: str) -> str:
    out = []
    for ch in pattern:
        if ch in "[*?":
            out.append(f"[{ch}]")
        elif ch == "%":
            out.append("*")
        elif ch == "_":
            out.append("?")
        else:
            out.append(ch)
    return "".join(out)


# ── both databases at once, during the switch ────────────────────────────────

#: What identifies a row in both databases. login_events has no such key: its
#: rows are only ever inserted, and deleted by age.
NATURAL_KEYS = {
    "app_settings": ("key",),
    "app_users": ("username",),
    "room_status": ("date", "room"),
    "schedule_full": ("date",),
    "schedule_log": ("date",),
}


class TeeClient:
    """Reads from `primary`. Each write runs on `primary`, then the mirror
    receives the rows the primary actually stored -- not the same command run
    again, which would stamp its own times and number its own ids, so the two
    would drift by milliseconds and the nightly comparison could never be exact.

    `copy_ids`: while Supabase is primary, the mirror (D1) takes Supabase's ids
    too, so the databases stay identical row for row. While D1 is primary, the
    mirror (Supabase) assigns its own: writing ids into Postgres would leave its
    sequences behind, and going back to Supabase would then collide on them.
    Rows are matched on their natural key instead.

    A mirror failure is reported to `on_mirror_error` and never raised: the
    database being switched to must not be able to take the live app down.
    The nightly comparison finds anything the mirror missed.
    """
    WRITES = frozenset({"insert", "upsert", "update", "delete"})

    def __init__(self, primary, mirror, on_mirror_error: Callable[[str, Exception], None],
                 *, copy_ids: bool):
        self.primary, self.mirror, self.on_mirror_error = primary, mirror, on_mirror_error
        self.copy_ids = copy_ids

    def table(self, name: str) -> _TeeQuery:
        return _TeeQuery(self, name)


class _TeeQuery:
    def __init__(self, tee: TeeClient, table: str):
        self._tee, self._table, self._calls = tee, table, []

    def __getattr__(self, method: str):
        def record(*args, **kwargs):
            self._calls.append((method, args, kwargs))
            return self
        return record

    def _replay(self, client):
        query = client.table(self._table)
        for method, args, kwargs in self._calls:
            query = getattr(query, method)(*args, **kwargs)
        return query.execute()

    def execute(self):
        result = self._replay(self._tee.primary)
        write = next((m for m, _, _ in self._calls if m in TeeClient.WRITES), None)
        if write:
            try:
                self._mirror(write, result.data or [])
            except Exception as ex:  # reported, never raised: see TeeClient
                self._tee.on_mirror_error(self._table, ex)
        return result

    def _mirror(self, write: str, stored: list[dict]) -> None:
        if write == "delete":
            self._replay(self._tee.mirror)          # the same rows, by the same filter
            return
        if not stored:
            return
        mirror = self._tee.mirror.table(self._table)
        if self._tee.copy_ids:
            key = PRIMARY_KEYS.get(self._table, ("id",))
            mirror.upsert(stored, on_conflict=",".join(key)).execute()
            return
        rows = [{c: v for c, v in row.items() if c != "id"} for row in stored]
        natural = NATURAL_KEYS.get(self._table)
        if natural:
            mirror.upsert(rows, on_conflict=",".join(natural)).execute()
        else:
            mirror.insert(rows).execute()


# ── which database, now ──────────────────────────────────────────────────────
#
#   supabase  read Supabase, write Supabase           (today)
#   both      read Supabase, write Supabase + D1      (step 3)
#   d1        read D1,       write D1 + Supabase      (step 4: going back loses nothing)
#   d1only    read D1,       write D1                 (step 6: Supabase retired)
#
# The mode is the BGV_DB_MODE secret if one is set (the way to say "d1only"
# once Supabase is gone), else the `db_mode` row in Supabase's app_settings,
# re-read every minute so a switch reaches every process without a restart.

MODES = ("supabase", "both", "d1", "d1only")
MODE_KEY = "db_mode"
MODE_TTL = 60.0

_mode = {"value": "supabase", "read_at": 0.0}
mirror_failures = {"count": 0, "last": ""}


@functools.cache
def _d1_client() -> D1Client:
    """One client (and one connection pool) per process. Two threads racing
    on the first call can each build one; one is kept, which is harmless."""
    return D1Client.from_secrets()


def _report_mirror_failure(table: str, ex: Exception) -> None:
    mirror_failures["count"] += 1
    mirror_failures["last"] = f"{now_iso()} {table}: {ex}"
    print(f"[d1store] mirror write to {table} failed: {ex}", flush=True)


@functools.cache
def _fixed_mode() -> str:
    """BGV_DB_MODE, read once: changing it is a restart, like any secret."""
    fixed = appsecrets.get("BGV_DB_MODE")
    if fixed and fixed not in MODES:
        raise RuntimeError(f"BGV_DB_MODE={fixed!r} is not one of {MODES}")
    return fixed


def current_mode(supabase) -> str:
    """The database mode, at most a minute old (see the table above)."""
    if _fixed_mode():
        return _fixed_mode()
    if time.monotonic() - _mode["read_at"] < MODE_TTL:
        return _mode["value"]
    try:
        rows = supabase.table("app_settings").select("payload").eq("key", MODE_KEY).execute().data
        payload = rows[0]["payload"] if rows else {}
        payload = json.loads(payload) if isinstance(payload, str) else payload
        mode = payload.get("mode", "supabase")
        _mode["value"] = mode if mode in MODES else "supabase"
    except Exception as ex:  # keep the last known mode; try again in a minute
        print(f"[d1store] database mode not read, staying {_mode['value']}: {ex}", flush=True)
    _mode["read_at"] = time.monotonic()
    return _mode["value"]


def client(supabase_factory: Callable[[], Any]):
    """The client for this call, by the database mode (db._client() returns this).

    While Supabase is still there ("both" and "d1"), a D1 that can't even be
    set up -- a missing token, say -- means Supabase alone, loudly, rather
    than an app that can't reach any database. Supabase has every write in
    those modes, so nothing is lost; the nightly comparison shows the gap.
    """
    if _fixed_mode() == "d1only":
        return _d1_client()
    supabase = supabase_factory()
    mode = current_mode(supabase)
    if mode == "supabase":
        return supabase
    try:
        d1 = _d1_client()
    except Exception as ex:
        _report_mirror_failure("(setup)", ex)
        return supabase
    if mode == "both":
        return TeeClient(supabase, d1, _report_mirror_failure, copy_ids=True)
    if mode == "d1":
        return TeeClient(d1, supabase, _report_mirror_failure, copy_ids=False)
    return d1
