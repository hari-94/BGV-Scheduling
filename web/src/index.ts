import { app } from "./app";
import { runRetention } from "./jobs/retention";

export default {
  fetch: app.fetch,
  async scheduled(_controller, env) {
    await runRetention(env.DB);
  },
} satisfies ExportedHandler<Env>;
