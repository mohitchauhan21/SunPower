/**
 * Create the dev and test databases on the local PostgreSQL server if they don't exist.
 * Uses DATABASE_URL / TEST_DATABASE_URL from .env. No Docker needed.
 */
import "dotenv/config";
import { Client } from "pg";

async function ensureDatabase(urlString: string | undefined, label: string): Promise<void> {
  if (!urlString) {
    console.warn(`  ! ${label}: URL not set, skipping`);
    return;
  }
  const url = new URL(urlString);
  const dbName = url.pathname.replace(/^\//, "");
  if (!/^[a-z_][a-z0-9_]*$/i.test(dbName)) throw new Error(`Unsafe database name "${dbName}"`);

  url.pathname = "/postgres";
  url.search = "";
  const client = new Client({ connectionString: url.toString() });
  try {
    await client.connect();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(
      `Could not connect to PostgreSQL for ${label} (${message}). Check the user and password in .env.`,
    );
  }
  try {
    const { rowCount } = await client.query("SELECT 1 FROM pg_database WHERE datname = $1", [dbName]);
    if (rowCount) {
      console.info(`  ✓ ${label}: database "${dbName}" exists`);
    } else {
      await client.query(`CREATE DATABASE "${dbName}"`);
      console.info(`  ✓ ${label}: created database "${dbName}"`);
    }
  } finally {
    await client.end();
  }
}

async function main() {
  await ensureDatabase(process.env.DATABASE_URL, "dev");
  await ensureDatabase(process.env.TEST_DATABASE_URL, "test");
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
