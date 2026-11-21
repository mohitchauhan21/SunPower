import { execSync } from "node:child_process";
import { config } from "dotenv";

/**
 * Reset the TEST database (never the dev one), apply every migration from scratch and seed it.
 * This doubles as the "migrations apply cleanly on a fresh database" check.
 */
export default function globalSetup(): void {
  config({ quiet: true });
  const url = process.env.TEST_DATABASE_URL;
  if (!url) throw new Error("TEST_DATABASE_URL is not set in .env");
  if (!/sunpower_test/.test(url))
    throw new Error("TEST_DATABASE_URL must point at a database named sunpower_test");

  const env: NodeJS.ProcessEnv = { ...process.env, DATABASE_URL: url, NODE_ENV: "test" };
  execSync("pnpm exec tsx scripts/db-create.ts", { stdio: "inherit", env });
  execSync("pnpm exec prisma migrate reset --force --skip-seed --skip-generate", { stdio: "inherit", env });
  execSync("pnpm exec tsx prisma/seed/index.ts", { stdio: "inherit", env });
}
