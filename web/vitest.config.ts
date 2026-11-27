import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

// Tests run inside the real Workers runtime with a fresh local D1 that has
// every migration applied (test/setup.ts), so SQL and constraints are tested
// for real, not mocked.
export default defineConfig(async () => {
  const migrations = await readD1Migrations("./migrations");
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          bindings: { TEST_MIGRATIONS: migrations, CHALLENGE_SECRET: "test-challenge-secret" },
        },
      }),
    ],
    test: { setupFiles: ["./test/setup.ts"] },
  };
});
