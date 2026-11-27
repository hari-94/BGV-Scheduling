import { hmacSha256Hex } from "../lib/crypto";

/**
 * Stored password formats (docs/DATA_MODEL.md "Sign-in"):
 *
 *   pbkdf2$<rounds>$<salt>$<key>     key = PBKDF2-SHA256(password, salt)
 *                                    -- today's format (db.py, 25 Nov)
 *   pbkdf2pre$<rounds>$<salt>$<key>  key = PBKDF2-SHA256(hex(SHA-256(password)), salt)
 *                                    -- the canonical format; also how the
 *                                       accounts migration wraps the old bare
 *                                       SHA-256 hashes without any resets
 *
 * A Worker can't afford PBKDF2 at 200,000 rounds (the runtime caps it at
 * 100,000 and the free plan allows 10 ms of CPU), so the browser derives the
 * key and sends it; the Worker only compares. Salts are text and are used as
 * their UTF-8 bytes; keys are 32 bytes, lowercase hex.
 */
export type Scheme = "pbkdf2" | "pbkdf2pre";

export interface Challenge {
  scheme: Scheme;
  salt: string;
  rounds: number;
}

export interface StoredHash extends Challenge {
  key: string;
}

/** Rounds for every new or upgraded hash. */
export const ROUNDS = 200_000;

const HEX_KEY = /^[0-9a-f]{64}$/;

export function parseStoredHash(stored: string): StoredHash | null {
  const [scheme, rounds, salt, key] = stored.split("$");
  if ((scheme !== "pbkdf2" && scheme !== "pbkdf2pre") || !salt || !key || !HEX_KEY.test(key)) {
    return null;
  }
  const n = Number(rounds);
  return Number.isInteger(n) && n > 0 ? { scheme, rounds: n, salt, key } : null;
}

export function formatStoredHash(
  scheme: Scheme,
  rounds: number,
  salt: string,
  key: string,
): string {
  return `${scheme}$${rounds}$${salt}$${key}`;
}

/**
 * The challenge for a username nobody has. It is derived from a server secret
 * so it is the same every time it is asked for, and it looks like a real
 * account's, so the answer doesn't reveal which usernames exist.
 */
export async function decoyChallenge(secret: string, username: string): Promise<Challenge> {
  const salt = (await hmacSha256Hex(secret, `salt:${username.toLowerCase()}`)).slice(0, 32);
  return { scheme: "pbkdf2pre", salt, rounds: ROUNDS };
}

export function isHexKey(value: string): boolean {
  return HEX_KEY.test(value);
}
