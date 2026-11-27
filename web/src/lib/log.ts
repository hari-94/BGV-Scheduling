type Level = "debug" | "info" | "warn" | "error";

/**
 * One structured line per event. Workers Logs indexes JSON fields, so events
 * can be filtered by name and field instead of by text search.
 */
export function log(level: Level, event: string, fields: Record<string, unknown> = {}): void {
  const line = JSON.stringify({ level, event, ...fields });
  if (level === "error") console.error(line);
  else if (level === "warn") console.warn(line);
  else console.log(line);
}
