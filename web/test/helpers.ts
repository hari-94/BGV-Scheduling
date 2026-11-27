import { env, exports } from "cloudflare:workers";
import { sha256Hex, toHex } from "../src/lib/crypto";

export const ORIGIN = "https://bgv.test";

/**
 * Tests derive keys with few rounds: the runtime caps PBKDF2 at 100,000, which
 * is exactly why production asks the browser to do it.
 */
export const TEST_ROUNDS = 1000;
export const UPGRADE_SALT = "fedcba9876543210fedcba9876543210";

interface CallInit {
  method?: string;
  json?: unknown;
  cookie?: string | undefined;
  /** Defaults to the Worker's own origin; null sends none (a non-browser client). */
  origin?: string | null;
}

/** A request to the Worker as a same-site browser page would make it. */
export function call(path: string, init: CallInit = {}): Promise<Response> {
  const headers = new Headers();
  const origin = init.origin === undefined ? ORIGIN : init.origin;
  if (origin !== null) headers.set("Origin", origin);
  if (init.cookie) headers.set("Cookie", init.cookie);
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  return exports.default.fetch(
    new Request(`${ORIGIN}${path}`, {
      method: init.method ?? (init.json === undefined ? "GET" : "POST"),
      headers,
      ...(init.json === undefined ? {} : { body: JSON.stringify(init.json) }),
    }),
  );
}

/** The browser's half of sign-in: PBKDF2-SHA256 over the password (or its SHA-256 hex). */
export async function deriveKey(
  password: string,
  salt: string,
  rounds: number,
  scheme: "pbkdf2" | "pbkdf2pre",
): Promise<string> {
  const secret = scheme === "pbkdf2pre" ? await sha256Hex(password) : password;
  const enc = new TextEncoder();
  const base = await crypto.subtle.importKey("raw", enc.encode(secret), "PBKDF2", false, [
    "deriveBits",
  ]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: enc.encode(salt), iterations: rounds },
    base,
    256,
  );
  return toHex(bits);
}

interface NewAccount {
  username: string;
  password: string;
  role?: string;
  scheme?: "pbkdf2" | "pbkdf2pre";
  disabled?: boolean;
}

export async function createAccount(a: NewAccount): Promise<number> {
  const scheme = a.scheme ?? "pbkdf2pre";
  const salt = "0123456789abcdef0123456789abcdef";
  const key = await deriveKey(a.password, salt, TEST_ROUNDS, scheme);
  const row = await env.DB.prepare(
    `INSERT INTO accounts (username, password_hash, role, created_at, disabled_at)
     VALUES (?, ?, ?, ?, ?) RETURNING id`,
  )
    .bind(
      a.username,
      `${scheme}$${TEST_ROUNDS}$${salt}$${key}`,
      a.role ?? "housekeeper",
      new Date().toISOString(),
      a.disabled ? new Date().toISOString() : null,
    )
    .first<{ id: number }>();
  if (!row) throw new Error("account not created");
  return row.id;
}

/** Signs in the way the page does: challenge, derive, send. Returns the response and cookie. */
export async function signIn(
  username: string,
  password: string,
): Promise<{ res: Response; cookie: string | undefined }> {
  const ch = await call("/api/auth/challenge", { json: { username } });
  const challenge = (await ch.json()) as {
    scheme: "pbkdf2" | "pbkdf2pre";
    salt: string;
    rounds: number;
  };
  const proof = await deriveKey(password, challenge.salt, challenge.rounds, challenge.scheme);
  // A real browser derives the upgrade key at the challenge's `upgradeRounds`
  // (200,000); the test runtime can't, so the tests check how it is stored.
  const upgrade =
    challenge.scheme === "pbkdf2"
      ? {
          salt: UPGRADE_SALT,
          key: await deriveKey(password, UPGRADE_SALT, TEST_ROUNDS, "pbkdf2pre"),
        }
      : undefined;
  const res = await call("/api/auth/sign-in", { json: { username, proof, upgrade } });
  return { res, cookie: sessionCookieFrom(res) };
}

export function sessionCookieFrom(res: Response): string | undefined {
  const header = res.headers.get("Set-Cookie") ?? "";
  const match = /(__Host-bgv_session=[^;]*)/.exec(header);
  return match?.[1];
}

export async function resetAuthTables(): Promise<void> {
  await env.DB.batch(
    ["sessions", "sign_in_events", "accounts"].map((t) => env.DB.prepare(`DELETE FROM ${t}`)),
  );
}
