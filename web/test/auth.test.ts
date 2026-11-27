import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import {
  call,
  createAccount,
  deriveKey,
  resetAuthTables,
  sessionCookieFrom,
  signIn,
  TEST_ROUNDS,
  UPGRADE_SALT,
} from "./helpers";

beforeEach(resetAuthTables);

describe("challenge", () => {
  it("gives an unknown username the same decoy every time, shaped like a real one", async () => {
    const ask = async () =>
      (await call("/api/auth/challenge", { json: { username: "nobody" } })).json();
    const first = (await ask()) as { scheme: string; salt: string; rounds: number };
    expect(first).toMatchObject({ scheme: "pbkdf2pre", rounds: 200_000 });
    expect(first.salt).toMatch(/^[0-9a-f]{32}$/);
    expect(await ask()).toEqual(first);
  });

  it("gives a real account its own salt and rounds", async () => {
    await createAccount({ username: "ana@example.com", password: "pw" });
    const res = await call("/api/auth/challenge", { json: { username: "ana@example.com" } });
    expect(await res.json()).toMatchObject({ scheme: "pbkdf2pre", rounds: TEST_ROUNDS });
  });
});

describe("sign-in", () => {
  it("sets a secure session cookie and records the sign-in", async () => {
    await createAccount({ username: "ana@example.com", password: "right", role: "rqs" });
    const { res, cookie } = await signIn("ana@example.com", "right");

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      account: { username: "ana@example.com", role: "rqs" },
    });
    const setCookie = res.headers.get("Set-Cookie") ?? "";
    for (const part of ["__Host-bgv_session=", "HttpOnly", "Secure", "SameSite=Lax", "Path=/"]) {
      expect(setCookie).toContain(part);
    }
    expect(cookie).toBeDefined();
    const events = await env.DB.prepare("SELECT outcome FROM sign_in_events").all();
    expect(events.results).toEqual([{ outcome: "ok" }]);
  });

  it("is case-insensitive about the username", async () => {
    await createAccount({ username: "ana@example.com", password: "right" });
    expect((await signIn("ANA@Example.com", "right")).res.status).toBe(200);
  });

  it("refuses a wrong password with the same answer as an unknown user", async () => {
    await createAccount({ username: "ana@example.com", password: "right" });
    const wrong = await signIn("ana@example.com", "wrong");
    const unknown = await signIn("nobody@example.com", "whatever");
    expect(wrong.res.status).toBe(401);
    expect(unknown.res.status).toBe(401);
    expect(await wrong.res.json()).toEqual(await unknown.res.json());
    expect(wrong.cookie).toBeUndefined();
  });

  it("locks a username after five wrong passwords, even for the right one", async () => {
    await createAccount({ username: "ana@example.com", password: "right" });
    for (let i = 0; i < 5; i++) {
      expect((await signIn("ana@example.com", "wrong")).res.status).toBe(401);
    }
    const locked = await signIn("ana@example.com", "right");
    expect(locked.res.status).toBe(429);
    expect(await locked.res.json()).toMatchObject({
      error: { code: "locked", details: { minutes: 15 } },
    });
  });

  it("refuses a switched-off account only after the password is right", async () => {
    await createAccount({ username: "gone@example.com", password: "right", disabled: true });
    expect((await signIn("gone@example.com", "wrong")).res.status).toBe(401);
    expect((await signIn("gone@example.com", "right")).res.status).toBe(403);
  });

  it("moves a pbkdf2 account to pbkdf2pre with the key the browser sends", async () => {
    await createAccount({ username: "old@example.com", password: "right", scheme: "pbkdf2" });
    expect((await signIn("old@example.com", "right")).res.status).toBe(200);

    const row = await env.DB.prepare("SELECT password_hash FROM accounts WHERE username = ?")
      .bind("old@example.com")
      .first<{ password_hash: string }>();
    const key = await deriveKey("right", UPGRADE_SALT, TEST_ROUNDS, "pbkdf2pre");
    expect(row?.password_hash).toBe(`pbkdf2pre$200000$${UPGRADE_SALT}$${key}`);
  });

  it("insists on the upgrade key for a pbkdf2 account", async () => {
    await createAccount({ username: "old@example.com", password: "right", scheme: "pbkdf2" });
    const ch = (await (
      await call("/api/auth/challenge", { json: { username: "old@example.com" } })
    ).json()) as {
      salt: string;
    };
    const proof = await deriveKey("right", ch.salt, TEST_ROUNDS, "pbkdf2");
    const res = await call("/api/auth/sign-in", { json: { username: "old@example.com", proof } });
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: { code: "upgrade_required" } });
  });

  it("rejects a malformed request with the reasons", async () => {
    const res = await call("/api/auth/sign-in", { json: { username: "", proof: "short" } });
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: { code: "invalid_request" } });
  });
});

describe("session", () => {
  it("knows who is signed in, with their permissions", async () => {
    await createAccount({ username: "desk@example.com", password: "pw", role: "frontdesk" });
    const { cookie } = await signIn("desk@example.com", "pw");
    const me = await call("/api/auth/me", { cookie });
    expect(me.status).toBe(200);
    expect(await me.json()).toEqual({
      account: {
        username: "desk@example.com",
        role: "frontdesk",
        language: null,
        permissions: ["view_frontdesk"],
      },
    });
  });

  it("stores only a hash of the token", async () => {
    await createAccount({ username: "ana@example.com", password: "pw" });
    const { cookie } = await signIn("ana@example.com", "pw");
    const token = cookie?.split("=")[1] ?? "";
    const row = await env.DB.prepare("SELECT token_hash FROM sessions").first<{
      token_hash: string;
    }>();
    expect(row?.token_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(row?.token_hash).not.toContain(token);
  });

  it("ends on sign-out", async () => {
    await createAccount({ username: "ana@example.com", password: "pw" });
    const { cookie } = await signIn("ana@example.com", "pw");
    const out = await call("/api/auth/sign-out", { method: "POST", cookie });
    expect(sessionCookieFrom(out)).toBe("__Host-bgv_session=");
    expect((await call("/api/auth/me", { cookie })).status).toBe(401);
  });

  it("is refused once expired", async () => {
    await createAccount({ username: "ana@example.com", password: "pw" });
    const { cookie } = await signIn("ana@example.com", "pw");
    await env.DB.prepare("UPDATE sessions SET expires_at = '2000-01-01T00:00:00.000Z'").run();
    expect((await call("/api/auth/me", { cookie })).status).toBe(401);
  });

  it("is refused once the account is switched off", async () => {
    await createAccount({ username: "ana@example.com", password: "pw" });
    const { cookie } = await signIn("ana@example.com", "pw");
    await env.DB.prepare("UPDATE accounts SET disabled_at = '2026-01-01T00:00:00.000Z'").run();
    expect((await call("/api/auth/me", { cookie })).status).toBe(401);
  });
});

describe("cross-site requests", () => {
  it("refuses a POST from another site", async () => {
    const res = await call("/api/auth/challenge", {
      json: { username: "x" },
      origin: "https://evil.test",
    });
    expect(res.status).toBe(403);
    expect(await res.json()).toMatchObject({ error: { code: "cross_origin" } });
  });
});
