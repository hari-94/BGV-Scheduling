import { Hono } from "hono";
import { authRoutes } from "./auth/routes";
import { healthRoutes } from "./health/routes";
import { errorBody, HttpError } from "./lib/http";
import { log } from "./lib/log";
import { sameOrigin } from "./lib/same-origin";
import type { AppEnv } from "./types";

/** The API. Pages are static files and never reach this code (wrangler.jsonc "assets"). */
export const app = new Hono<AppEnv>()
  .basePath("/api")
  .use(sameOrigin)
  .route("/health", healthRoutes)
  .route("/auth", authRoutes);

app.notFound((c) => c.json(errorBody("not_found", "No such endpoint."), 404));

app.onError((err, c) => {
  if (err instanceof HttpError) {
    return c.json(errorBody(err.code, err.message, err.details), err.status);
  }
  log("error", "unhandled", { method: c.req.method, path: c.req.path, message: err.message });
  return c.json(errorBody("internal", "Something went wrong."), 500);
});
