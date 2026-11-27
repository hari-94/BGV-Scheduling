"""
d1store.py -- the D1 client db.py uses during and after the move to Cloudflare.

The client's SQL runs for real: a fake transport answers the D1 REST API from
an in-memory SQLite database built from web/migrations/0001_init.sql, the
same tables the live D1 database has. No network, no Cloudflare account.

Run:  .venv\\Scripts\\python -m unittest tests.test_d1store -v
"""
import json
import pathlib
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx

import d1store

SCHEMA = pathlib.Path(__file__).parents[1] / "web" / "migrations" / "0001_init.sql"


class FakeD1:
    """Answers POST .../query like the D1 REST API, from SQLite."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.statements = []
        self.fail_next = []          # status codes to answer before running anything

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.fail_next:
            status = self.fail_next.pop(0)
            return httpx.Response(status, json={"success": False,
                                                "errors": [{"message": f"fake {status}"}]})
        body = json.loads(request.content)
        self.statements.append(body["sql"])
        try:
            rows = [dict(r) for r in self.db.execute(body["sql"], body["params"]).fetchall()]
        except sqlite3.Error as ex:
            return httpx.Response(400, json={"success": False, "errors": [{"message": str(ex)}]})
        self.db.commit()
        return httpx.Response(200, json={"success": True,
                                         "result": [{"results": rows, "success": True}]})


def make_client() -> tuple[d1store.D1Client, FakeD1]:
    fake = FakeD1()
    http = httpx.Client(transport=httpx.MockTransport(fake))
    return d1store.D1Client("token", http=http), fake


class ReadingTest(unittest.TestCase):
    def setUp(self):
        self.d1, self.fake = make_client()
        self.d1.table("app_settings").upsert([
            {"key": "staffweek_2026-11-22", "payload": json.dumps({"week": 1})},
            {"key": "staffweek_2026-11-29", "payload": json.dumps({"week": 2})},
            {"key": "staffweekly_other", "payload": json.dumps({})},
            {"key": "roster", "payload": json.dumps({"hk": ["Ana"]})},
        ]).execute()

    def test_payload_comes_back_as_supabase_returned_it(self):
        rows = self.d1.table("app_settings").select("key,payload").eq("key", "roster").execute().data
        # db.py stores json.dumps(obj) in a jsonb column, so Supabase hands back a string
        self.assertEqual(rows, [{"key": "roster", "payload": json.dumps({"hk": ["Ana"]})}])

    def test_a_prefix_like_reads_a_key_range_not_the_table(self):
        rows = self.d1.table("app_settings").select("key").like("key", "staffweek_*").execute().data
        self.assertEqual(sorted(r["key"] for r in rows),
                         ["staffweek_2026-11-22", "staffweek_2026-11-29"])
        self.assertIn('"key" >= ? AND "key" < ?', self.fake.statements[-1])
        self.assertNotIn("LIKE", self.fake.statements[-1])

    def test_a_pattern_that_is_not_a_prefix_still_matches(self):
        rows = self.d1.table("app_settings").select("key").like("key", "%11-29").execute().data
        self.assertEqual([r["key"] for r in rows], ["staffweek_2026-11-29"])

    def test_in_takes_more_values_than_d1_allows_parameters(self):
        keys = [f"missing_{i}" for i in range(150)] + ["roster"]
        rows = self.d1.table("app_settings").select("key").in_("key", keys).execute().data
        self.assertEqual(rows, [{"key": "roster"}])

    def test_exact_count_with_a_limit(self):
        r = (self.d1.table("app_settings").select("key", count="exact")
             .like("key", "staffweek_*").order("key", desc=True).limit(1).execute())
        self.assertEqual((r.count, r.data), (2, [{"key": "staffweek_2026-11-29"}]))

    def test_exact_count_of_nothing(self):
        r = self.d1.table("app_settings").select("key", count="exact").eq("key", "none").execute()
        self.assertEqual((r.count, r.data), (0, []))

    def test_range_pages_like_supabase(self):
        page = (self.d1.table("app_settings").select("key").order("key")
                .range(1, 2).execute().data)
        self.assertEqual([r["key"] for r in page], ["staffweek_2026-11-22", "staffweek_2026-11-29"])

    def test_descending_order_puts_empty_values_first_like_postgres(self):
        self.d1.table("room_status").upsert([
            {"date": "2026-11-26", "room": "3240A", "cleaned_at": "2026-11-26T15:00:00+00:00"},
            {"date": "2026-11-26", "room": "3240B"},
        ], on_conflict="date,room").execute()
        rows = (self.d1.table("room_status").select("room").eq("date", "2026-11-26")
                .order("cleaned_at", desc=True).execute().data)
        self.assertEqual([r["room"] for r in rows], ["3240B", "3240A"])


class WritingTest(unittest.TestCase):
    def setUp(self):
        self.d1, self.fake = make_client()

    def stored(self, sql, *params):
        return [dict(r) for r in self.fake.db.execute(sql, params).fetchall()]

    def test_upsert_inserts_then_updates_and_stamps_updated_at(self):
        rs = self.d1.table("room_status")
        rs.upsert({"date": "2026-11-26", "room": "3240A", "status": "pending"},
                  on_conflict="date,room").execute()
        first = self.stored("SELECT status, updated_at FROM room_status")[0]
        with mock.patch.object(d1store, "now_iso", return_value="2099-01-01T00:00:00+00:00"):
            rs.upsert({"date": "2026-11-26", "room": "3240A", "status": "cleaning_done"},
                      on_conflict="date,room").execute()
        rows = self.stored("SELECT status, updated_at FROM room_status")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"status": "cleaning_done", "updated_at": "2099-01-01T00:00:00+00:00"})
        self.assertNotEqual(first["updated_at"], rows[0]["updated_at"])

    def test_upsert_changes_only_the_columns_it_was_given(self):
        rs = self.d1.table("room_status")
        rs.upsert({"date": "2026-11-26", "room": "3240A", "status": "pending", "notes": "towels"},
                  on_conflict="date,room").execute()
        rs.upsert({"date": "2026-11-26", "room": "3240A", "status": "inspected"},
                  on_conflict="date,room").execute()
        self.assertEqual(self.stored("SELECT status, notes FROM room_status"),
                         [{"status": "inspected", "notes": "towels"}])

    def test_insert_returns_the_rows_with_their_ids(self):
        data = self.d1.table("login_events").insert(
            {"username": "ana", "ts": "2026-11-26T10:00:00+00:00"}).execute().data
        self.assertEqual((data[0]["id"], data[0]["username"]), (1, "ana"))

    def test_times_are_stored_as_postgres_gives_them_back(self):
        local = datetime(2026, 11, 26, 6, 30, tzinfo=timezone(timedelta(hours=-7)))
        self.d1.table("login_events").insert([
            {"username": "naive", "ts": "2026-11-26T13:30:00.120000"},
            {"username": "local", "ts": local.isoformat()},
            {"username": "zulu", "ts": "2026-11-26T13:30:00Z"},
        ]).execute()
        self.assertEqual(self.stored("SELECT username, ts FROM login_events ORDER BY id"), [
            {"username": "naive", "ts": "2026-11-26T13:30:00.12+00:00"},
            {"username": "local", "ts": "2026-11-26T13:30:00+00:00"},
            {"username": "zulu", "ts": "2026-11-26T13:30:00+00:00"},
        ])

    def test_update_stamps_and_needs_a_filter(self):
        self.d1.table("app_settings").upsert({"key": "k", "payload": json.dumps(1)}).execute()
        with mock.patch.object(d1store, "now_iso", return_value="2099-01-01T00:00:00+00:00"):
            self.d1.table("app_settings").update({"payload": json.dumps(2)}).eq("key", "k").execute()
        self.assertEqual(self.stored("SELECT payload, updated_at FROM app_settings"),
                         [{"payload": json.dumps(json.dumps(2)), "updated_at": "2099-01-01T00:00:00+00:00"}])
        with self.assertRaises(d1store.D1Error):
            self.d1.table("app_settings").update({"payload": "x"}).execute()

    def test_delete_returns_what_it_removed_and_needs_a_filter(self):
        self.d1.table("login_events").insert([
            {"username": "old", "ts": "2026-01-01T00:00:00+00:00"},
            {"username": "new", "ts": "2026-11-26T00:00:00+00:00"},
        ]).execute()
        gone = self.d1.table("login_events").delete().lt("ts", "2026-06-01").execute().data
        self.assertEqual([r["username"] for r in gone], ["old"])
        with self.assertRaises(d1store.D1Error):
            self.d1.table("login_events").delete().execute()

    def test_a_payload_over_a_megabyte_is_compressed_and_comes_back_whole(self):
        big = json.dumps({"rows": ["x" * 100] * 15000})        # ~1.6 MB
        self.d1.table("app_settings").upsert({"key": "staffsched_file", "payload": big}).execute()
        stored = self.stored("SELECT payload FROM app_settings")[0]["payload"]
        self.assertTrue(stored.startswith("gz:"))
        self.assertLess(len(stored), 100_000)
        back = self.d1.table("app_settings").select("payload").eq("key", "staffsched_file").execute()
        self.assertEqual(back.data[0]["payload"], big)

    def test_a_name_that_is_not_a_column_is_refused(self):
        with self.assertRaises(ValueError):
            self.d1.table("app_settings").select("key; DROP TABLE app_settings").execute()


class TransportTest(unittest.TestCase):
    def test_busy_answers_are_retried(self):
        d1, fake = make_client()
        fake.fail_next = [429, 503]
        with mock.patch.object(d1store.time, "sleep"):
            self.assertEqual(d1.run("SELECT 1 AS one"), [{"one": 1}])

    def test_a_bad_statement_is_not_retried(self):
        d1, fake = make_client()
        with self.assertRaisesRegex(d1store.D1Error, "no such table"):
            d1.run("SELECT * FROM nowhere")
        self.assertEqual(len(fake.statements), 1)


class TeeTest(unittest.TestCase):
    def setUp(self):
        self.primary, self.primary_fake = make_client()
        self.mirror, self.mirror_fake = make_client()
        self.failures = []
        self.tee = d1store.TeeClient(self.primary, self.mirror,
                                     lambda table, ex: self.failures.append(table))

    def test_reads_touch_only_the_primary(self):
        self.tee.table("app_settings").select("*").eq("key", "k").execute()
        self.assertEqual(len(self.primary_fake.statements), 1)
        self.assertEqual(self.mirror_fake.statements, [])

    def test_writes_reach_both(self):
        self.tee.table("app_settings").upsert({"key": "k", "payload": json.dumps(1)}).execute()
        for fake in (self.primary_fake, self.mirror_fake):
            self.assertEqual(fake.db.execute("SELECT count(*) FROM app_settings").fetchone()[0], 1)

    def test_a_failing_mirror_is_reported_never_raised(self):
        self.mirror_fake.fail_next = [400]
        result = self.tee.table("app_settings").upsert({"key": "k", "payload": "1"}).execute()
        self.assertEqual(result.data[0]["key"], "k")
        self.assertEqual(self.failures, ["app_settings"])

    def test_a_failing_primary_is_raised_and_the_mirror_left_alone(self):
        self.primary_fake.fail_next = [400]
        with self.assertRaises(d1store.D1Error):
            self.tee.table("app_settings").upsert({"key": "k", "payload": "1"}).execute()
        self.assertEqual(self.mirror_fake.statements, [])


class ModeTest(unittest.TestCase):
    """d1store.client(): which database each mode reads and writes."""

    def setUp(self):
        self.supabase, _ = make_client()           # any client with the same calls
        self.d1, _ = make_client()
        patches = [
            mock.patch.object(d1store, "_fixed_mode", return_value=""),
            mock.patch.object(d1store, "_d1_client", return_value=self.d1),
            mock.patch.dict(d1store._mode, {"value": "supabase", "read_at": 0.0}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def set_mode(self, mode):
        self.supabase.table("app_settings").upsert(
            {"key": d1store.MODE_KEY, "payload": json.dumps({"mode": mode})}).execute()
        d1store._mode["read_at"] = 0.0

    def test_with_no_mode_set_it_is_supabase_as_before(self):
        self.assertIs(d1store.client(lambda: self.supabase), self.supabase)

    def test_each_mode_routes_reads_and_writes(self):
        self.set_mode("both")
        c = d1store.client(lambda: self.supabase)
        self.assertEqual((c.primary, c.mirror), (self.supabase, self.d1))
        self.set_mode("d1")
        c = d1store.client(lambda: self.supabase)
        self.assertEqual((c.primary, c.mirror), (self.d1, self.supabase))

    def test_the_mode_is_read_at_most_once_a_minute(self):
        self.set_mode("both")
        d1store.client(lambda: self.supabase)                     # reads "both"
        self.set_mode("d1")
        d1store._mode["read_at"] = d1store.time.monotonic()      # as if just read
        self.assertEqual(d1store.current_mode(self.supabase), "both")

    def test_an_unusable_d1_falls_back_to_supabase_while_it_exists(self):
        self.set_mode("d1")
        with mock.patch.object(d1store, "_d1_client", side_effect=RuntimeError("no token")):
            self.assertIs(d1store.client(lambda: self.supabase), self.supabase)

    def test_d1only_never_touches_supabase(self):
        d1store._fixed_mode.return_value = "d1only"
        def no_supabase():
            raise AssertionError("Supabase was asked for")
        self.assertIs(d1store.client(no_supabase), self.d1)


class TimestampTest(unittest.TestCase):
    def test_postgres_format(self):
        cases = {
            datetime(2026, 11, 26, 9, 0, 17, 901396, tzinfo=timezone.utc): "2026-11-26T09:00:17.901396+00:00",
            datetime(2026, 11, 26, 9, 0, 17, 900000, tzinfo=timezone.utc): "2026-11-26T09:00:17.9+00:00",
            datetime(2026, 11, 26, 9, 0, 17, tzinfo=timezone.utc): "2026-11-26T09:00:17+00:00",
            datetime(2026, 11, 26, 2, 0, 17): "2026-11-26T02:00:17+00:00",
        }
        for moment, text in cases.items():
            self.assertEqual(d1store.pg_timestamp(moment), text)


if __name__ == "__main__":
    unittest.main()
