import { nowIso, shiftIso } from "../lib/clock";

/** Database access for accounts, sessions and sign-in events. */

export interface AccountRow {
  id: number;
  username: string;
  password_hash: string;
  role: string;
  language: string | null;
  person_id: number | null;
  disabled_at: string | null;
}

export interface SessionAccount {
  id: number;
  username: string;
  role: string;
  language: string | null;
  personId: number | null;
}

export type SignInOutcome = "ok" | "wrong_password" | "unknown_user" | "locked" | "disabled";

export function findAccount(db: D1Database, username: string): Promise<AccountRow | null> {
  return db
    .prepare(
      `SELECT id, username, password_hash, role, language, person_id, disabled_at
         FROM accounts WHERE username = ?`,
    )
    .bind(username)
    .first<AccountRow>();
}

export async function setPasswordHash(db: D1Database, accountId: number, hash: string) {
  await db
    .prepare("UPDATE accounts SET password_hash = ? WHERE id = ?")
    .bind(hash, accountId)
    .run();
}

/** Failed attempts for `username` since `sinceIso`, and when the first one was. */
export async function recentFailures(
  db: D1Database,
  username: string,
  sinceIso: string,
): Promise<{ count: number; first: string | null }> {
  const row = await db
    .prepare(
      `SELECT count(*) AS count, min(at) AS first FROM sign_in_events
        WHERE username = ? AND at > ? AND outcome IN ('wrong_password', 'unknown_user')`,
    )
    .bind(username, sinceIso)
    .first<{ count: number; first: string | null }>();
  return row ?? { count: 0, first: null };
}

export async function recordSignIn(
  db: D1Database,
  username: string,
  accountId: number | null,
  outcome: SignInOutcome,
) {
  const at = nowIso();
  const statements = [
    db
      .prepare(
        `INSERT INTO sign_in_events (username, account_id, outcome, client, at)
         VALUES (?, ?, ?, 'web', ?)`,
      )
      .bind(username, accountId, outcome, at),
  ];
  if (outcome === "ok" && accountId !== null) {
    statements.push(
      db.prepare("UPDATE accounts SET last_sign_in_at = ? WHERE id = ?").bind(at, accountId),
    );
  }
  await db.batch(statements);
}

export async function createSession(
  db: D1Database,
  tokenHash: string,
  accountId: number,
  lifetimeMs: number,
) {
  const now = nowIso();
  await db
    .prepare(
      `INSERT INTO sessions (token_hash, account_id, created_at, expires_at, last_seen_at, client)
       VALUES (?, ?, ?, ?, ?, 'web')`,
    )
    .bind(tokenHash, accountId, now, shiftIso(now, lifetimeMs), now)
    .run();
}

interface SessionRow {
  expires_at: string;
  last_seen_at: string;
  id: number;
  username: string;
  role: string;
  language: string | null;
  person_id: number | null;
  disabled_at: string | null;
}

/** The live session for a token hash, with its account; null if none, expired or disabled. */
export async function findSession(
  db: D1Database,
  tokenHash: string,
  now: string,
): Promise<{ account: SessionAccount; lastSeenAt: string } | null> {
  const row = await db
    .prepare(
      `SELECT s.expires_at, s.last_seen_at,
              a.id, a.username, a.role, a.language, a.person_id, a.disabled_at
         FROM sessions s JOIN accounts a ON a.id = s.account_id
        WHERE s.token_hash = ?`,
    )
    .bind(tokenHash)
    .first<SessionRow>();
  if (!row || row.expires_at <= now || row.disabled_at !== null) return null;
  return {
    account: {
      id: row.id,
      username: row.username,
      role: row.role,
      language: row.language,
      personId: row.person_id,
    },
    lastSeenAt: row.last_seen_at,
  };
}

export async function touchSession(db: D1Database, tokenHash: string, now: string) {
  await db
    .prepare("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?")
    .bind(now, tokenHash)
    .run();
}

export async function deleteSession(db: D1Database, tokenHash: string) {
  await db.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(tokenHash).run();
}
