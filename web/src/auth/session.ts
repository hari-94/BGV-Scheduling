import type { Context } from "hono";
import { deleteCookie, getCookie, setCookie } from "hono/cookie";
import { createMiddleware } from "hono/factory";
import { DAY_MS, HOUR_MS, nowIso, shiftIso } from "../lib/clock";
import { randomToken, sha256Hex } from "../lib/crypto";
import { HttpError } from "../lib/http";
import type { AppEnv } from "../types";
import { can, type Permission } from "./permissions";
import { createSession, deleteSession, findSession, touchSession } from "./store";

/**
 * `__Host-` makes the browser refuse the cookie unless it is Secure, has
 * Path=/ and no Domain, so no other site or subdomain can set or read it.
 */
export const SESSION_COOKIE = "__Host-bgv_session";
export const SESSION_LIFETIME_MS = 30 * DAY_MS;
/** last_seen_at is written at most this often: a write per request would be the biggest writer. */
const TOUCH_EVERY_MS = HOUR_MS;

export async function startSession(c: Context<AppEnv>, accountId: number): Promise<void> {
  const token = randomToken();
  await createSession(c.env.DB, await sha256Hex(token), accountId, SESSION_LIFETIME_MS);
  setCookie(c, SESSION_COOKIE, token, {
    path: "/",
    secure: true,
    httpOnly: true,
    sameSite: "Lax",
    maxAge: SESSION_LIFETIME_MS / 1000,
  });
}

export async function endSession(c: Context<AppEnv>): Promise<void> {
  const token = getCookie(c, SESSION_COOKIE);
  if (token) await deleteSession(c.env.DB, await sha256Hex(token));
  deleteCookie(c, SESSION_COOKIE, { path: "/", secure: true });
}

/** Rejects the request unless it carries a live session; puts the account on the context. */
export const requireSession = createMiddleware<AppEnv>(async (c, next) => {
  const token = getCookie(c, SESSION_COOKIE);
  if (!token) throw new HttpError(401, "signed_out", "Please sign in.");
  const tokenHash = await sha256Hex(token);
  const now = nowIso();
  const found = await findSession(c.env.DB, tokenHash, now);
  if (!found) throw new HttpError(401, "signed_out", "Please sign in.");
  if (found.lastSeenAt < shiftIso(now, -TOUCH_EVERY_MS)) {
    c.executionCtx.waitUntil(touchSession(c.env.DB, tokenHash, now));
  }
  c.set("account", found.account);
  await next();
});

/** Use after `requireSession`. */
export function requirePermission(permission: Permission) {
  return createMiddleware<AppEnv>(async (c, next) => {
    if (!can(c.get("account").role, permission)) {
      throw new HttpError(403, "forbidden", "Your account can't do this.");
    }
    await next();
  });
}
