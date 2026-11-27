import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { can, permissionsOf } from "../src/auth/permissions";
import { runRetention } from "../src/jobs/retention";
import { call, createAccount, resetAuthTables } from "./helpers";

describe("health", () => {
  it("reports the Worker and the database up", async () => {
    const res = await call("/api/health");
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, database: "ok" });
  });

  it("answers unknown API paths with the standard error shape", async () => {
    const res = await call("/api/nope");
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({
      error: { code: "not_found", message: "No such endpoint." },
    });
  });
});

describe("permissions (ported from auth.py)", () => {
  it("matches the Streamlit app's table", () => {
    expect(permissionsOf("admin")).toHaveLength(10);
    expect(permissionsOf("rqs")).toEqual([
      "generate",
      "paste_input",
      "view_groups",
      "view_hk_tab",
      "view_insp_tab",
      "view_dashboard",
    ]);
    expect(permissionsOf("housekeeper")).toEqual(["view_groups", "view_hk_tab"]);
    expect(permissionsOf("houseperson")).toEqual(permissionsOf("housekeeper"));
    expect(permissionsOf("frontdesk")).toEqual(["view_frontdesk"]);
  });

  it("gives a role it doesn't know nothing", () => {
    expect(permissionsOf("intern")).toEqual([]);
    expect(can("intern", "view_groups")).toBe(false);
  });
});

describe("schema", () => {
  it("rejects a role that isn't in the roles table", async () => {
    await expect(
      env.DB.prepare(
        "INSERT INTO accounts (username, password_hash, role, created_at) VALUES ('x', 'h', 'intern', 'now')",
      ).run(),
    ).rejects.toThrow(/FOREIGN KEY/);
  });

  it("rejects settings that aren't JSON", async () => {
    await expect(
      env.DB.prepare(
        "INSERT INTO settings (key, value, updated_by, updated_at) VALUES ('k', 'not json', 't', 'now')",
      ).run(),
    ).rejects.toThrow(/CHECK/);
  });

  it("has the reference rows staff see, in both languages", async () => {
    const statuses = await env.DB.prepare(
      "SELECT count(*) AS n FROM room_statuses WHERE label_en <> '' AND label_es <> ''",
    ).first<{ n: number }>();
    expect(statuses?.n).toBe(11);
  });
});

describe("retention", () => {
  it("deletes expired sessions and sign-ins older than 180 days, nothing else", async () => {
    await resetAuthTables();
    const id = await createAccount({ username: "ana@example.com", password: "pw" });
    const now = "2026-11-26T09:00:00.000Z";
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO sessions (token_hash, account_id, created_at, expires_at, last_seen_at, client)
         VALUES ('old', ?1, ?2, '2026-11-01T00:00:00.000Z', ?2, 'web'),
                ('live', ?1, ?2, '2026-12-20T00:00:00.000Z', ?2, 'web')`,
      ).bind(id, now),
      env.DB.prepare(
        `INSERT INTO sign_in_events (username, outcome, client, at)
         VALUES ('ana@example.com', 'ok', 'web', '2026-01-01T00:00:00.000Z'),
                ('ana@example.com', 'ok', 'web', '2026-11-20T00:00:00.000Z')`,
      ),
    ]);

    expect(await runRetention(env.DB, now)).toEqual({ sessions: 1, sign_in_events: 1 });
    const left = await env.DB.prepare("SELECT token_hash FROM sessions").all();
    expect(left.results).toEqual([{ token_hash: "live" }]);
  });
});
