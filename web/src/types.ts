import type { SessionAccount } from "./auth/store";

/** Hono's view of this Worker: its bindings, and what middleware puts on the context. */
export interface AppEnv {
  Bindings: Env;
  Variables: { account: SessionAccount };
}
