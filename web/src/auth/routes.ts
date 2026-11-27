import { Hono } from "hono";
import { z } from "zod";
import { MINUTE_MS, nowIso, shiftIso } from "../lib/clock";
import { secretsEqual } from "../lib/crypto";
import { HttpError, readJson } from "../lib/http";
import type { AppEnv } from "../types";
import {
  type Challenge,
  decoyChallenge,
  formatStoredHash,
  isHexKey,
  parseStoredHash,
  ROUNDS,
} from "./passwords";
import { permissionsOf } from "./permissions";
import { endSession, requireSession, startSession } from "./session";
import {
  type AccountRow,
  findAccount,
  recentFailures,
  recordSignIn,
  setPasswordHash,
} from "./store";

/** db.py's rule since 25 Nov: five wrong passwords in 15 minutes locks the username for the rest of them. */
const MAX_FAILURES = 5;
const FAILURE_WINDOW_MS = 15 * MINUTE_MS;

const username = z.string().trim().min(1).max(254);
const hexKey = z.string().refine(isHexKey, "a 64-character lowercase hex key");

const ChallengeRequest = z.object({ username });
const SignInRequest = z.object({
  username,
  proof: hexKey,
  /** Required when the stored hash is the older `pbkdf2` format: the same password in `pbkdf2pre`. */
  upgrade: z.object({ salt: z.string().regex(/^[0-9a-f]{32}$/), key: hexKey }).optional(),
});

export const authRoutes = new Hono<AppEnv>()
  /** Step 1: how the browser should derive its proof for this username. */
  .post("/challenge", async (c) => {
    const { username: name } = await readJson(c, ChallengeRequest);
    const stored = await findAccount(c.env.DB, name);
    const parsed = stored ? parseStoredHash(stored.password_hash) : null;
    const challenge: Challenge = parsed
      ? { scheme: parsed.scheme, salt: parsed.salt, rounds: parsed.rounds }
      : await decoyChallenge(c.env.CHALLENGE_SECRET, name);
    return c.json({ ...challenge, upgradeRounds: ROUNDS });
  })

  /** Step 2: the derived key. On success the session cookie is set. */
  .post("/sign-in", async (c) => {
    const body = await readJson(c, SignInRequest);
    const db = c.env.DB;
    await refuseIfLocked(db, body.username);

    const account = await findAccount(db, body.username);
    const stored = account ? parseStoredHash(account.password_hash) : null;
    if (!account || !stored) {
      await recordSignIn(db, body.username, null, "unknown_user");
      throw wrongCredentials();
    }
    if (!(await secretsEqual(body.proof, stored.key))) {
      await recordSignIn(db, body.username, account.id, "wrong_password");
      throw wrongCredentials();
    }
    if (account.disabled_at !== null) {
      await recordSignIn(db, body.username, account.id, "disabled");
      throw new HttpError(403, "disabled", "This account is switched off. Ask a manager.");
    }
    if (stored.scheme === "pbkdf2") {
      await upgradeHash(db, account, body.upgrade);
    }

    await recordSignIn(db, body.username, account.id, "ok");
    await startSession(c, account.id);
    return c.json({ account: publicAccount(account) });
  })

  .post("/sign-out", async (c) => {
    await endSession(c);
    return c.json({ ok: true });
  })

  .get("/me", requireSession, (c) => c.json({ account: publicAccount(c.get("account")) }));

/**
 * A locked attempt is refused without being recorded: recording it would let
 * anyone spend the free plan's daily writes by hammering a locked name.
 */
async function refuseIfLocked(db: D1Database, name: string): Promise<void> {
  const since = shiftIso(nowIso(), -FAILURE_WINDOW_MS);
  const { count, first } = await recentFailures(db, name, since);
  if (count < MAX_FAILURES || first === null) return;
  const unlockAt = Date.parse(first) + FAILURE_WINDOW_MS;
  const minutes = Math.max(1, Math.ceil((unlockAt - Date.now()) / MINUTE_MS));
  throw new HttpError(429, "locked", `Too many tries. Try again in ${minutes} min.`, { minutes });
}

/** Moves an account from `pbkdf2` to the canonical `pbkdf2pre`, using the key the browser sent. */
async function upgradeHash(
  db: D1Database,
  account: AccountRow,
  upgrade: { salt: string; key: string } | undefined,
): Promise<void> {
  if (!upgrade) {
    throw new HttpError(400, "upgrade_required", "This sign-in needs the upgraded key as well.");
  }
  await setPasswordHash(
    db,
    account.id,
    formatStoredHash("pbkdf2pre", ROUNDS, upgrade.salt, upgrade.key),
  );
}

function wrongCredentials(): HttpError {
  return new HttpError(401, "wrong_credentials", "That username and password don't match.");
}

function publicAccount(account: Pick<AccountRow, "username" | "role" | "language">) {
  return {
    username: account.username,
    role: account.role,
    language: account.language,
    permissions: permissionsOf(account.role),
  };
}
