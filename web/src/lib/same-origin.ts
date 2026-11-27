import { createMiddleware } from "hono/factory";
import { HttpError } from "./http";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * Refuses a state-changing request that a browser sent from another site.
 *
 * The session cookie is SameSite=Lax, which already keeps it off most
 * cross-site requests; checking `Origin` as well closes the rest. Browsers
 * always send `Origin` on a cross-origin POST, so a request without one did
 * not come from a page on another site.
 */
export const sameOrigin = createMiddleware(async (c, next) => {
  if (!SAFE_METHODS.has(c.req.method)) {
    const origin = c.req.header("Origin");
    if (origin !== undefined && origin !== new URL(c.req.url).origin) {
      throw new HttpError(403, "cross_origin", "Requests from other sites are not accepted.");
    }
  }
  await next();
});
