import { DAY_MS, nowIso, shiftIso } from "../lib/clock";
import { log } from "../lib/log";

/**
 * Nightly clean-up of rows past their retention (docs/DATA_MODEL.md).
 * Each statement deletes by an indexed column, so it reads only what it removes.
 */
export async function runRetention(
  db: D1Database,
  now = nowIso(),
): Promise<Record<string, number>> {
  const rules: [table: string, sql: string, cutoff: string][] = [
    ["sessions", "DELETE FROM sessions WHERE expires_at <= ?", now],
    ["sign_in_events", "DELETE FROM sign_in_events WHERE at < ?", shiftIso(now, -180 * DAY_MS)],
  ];
  const results = await db.batch(rules.map(([, sql, cutoff]) => db.prepare(sql).bind(cutoff)));
  const deleted = Object.fromEntries(
    rules.map(([table], i) => [table, results[i]?.meta.changes ?? 0]),
  );
  log("info", "retention.done", { deleted });
  return deleted;
}
