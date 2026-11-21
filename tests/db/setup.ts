import { config } from "dotenv";
import { afterAll } from "vitest";

config({ quiet: true });
if (!process.env.TEST_DATABASE_URL) throw new Error("TEST_DATABASE_URL is not set in .env");
// Point the app's Prisma client at the test database before any module imports it.
process.env.DATABASE_URL = process.env.TEST_DATABASE_URL;

afterAll(async () => {
  const { db } = await import("@/server/db");
  await db.$disconnect();
});
