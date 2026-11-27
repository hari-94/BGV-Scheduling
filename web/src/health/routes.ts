import { Hono } from "hono";
import { log } from "../lib/log";
import type { AppEnv } from "../types";

/** For uptime checks: the Worker answers, and so does the database. Reads no rows. */
export const healthRoutes = new Hono<AppEnv>().get("/", async (c) => {
  let database: "ok" | "error" = "ok";
  try {
    await c.env.DB.prepare("SELECT 1").first();
  } catch (err) {
    database = "error";
    log("error", "health.database", { message: err instanceof Error ? err.message : String(err) });
  }
  const ok = database === "ok";
  return c.json({ ok, database, time: new Date().toISOString() }, ok ? 200 : 503);
});
