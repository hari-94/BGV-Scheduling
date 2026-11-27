/** Times are stored as UTC ISO-8601 with milliseconds (docs/DATA_MODEL.md). */
export function nowIso(): string {
  return new Date().toISOString();
}

/** `iso` moved by `ms` milliseconds (negative for the past). */
export function shiftIso(iso: string, ms: number): string {
  return new Date(Date.parse(iso) + ms).toISOString();
}

export const MINUTE_MS = 60_000;
export const HOUR_MS = 60 * MINUTE_MS;
export const DAY_MS = 24 * HOUR_MS;
