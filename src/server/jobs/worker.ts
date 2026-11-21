/**
 * Background worker: `pnpm worker`.
 * 1. Relays committed outbox events onto the pg-boss queue every 2 seconds.
 * 2. Runs the handler for each event type.
 * Handlers must be idempotent: an event can be delivered more than once after a crash.
 */
import "dotenv/config";
import { db } from "@/server/db";
import { relayOutbox } from "./outbox";
import { PgBossQueue } from "./pgboss-queue";
import { registerHandlers } from "./handlers";

async function main(): Promise<void> {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");

  const queue = new PgBossQueue(url);
  await queue.start();
  await registerHandlers(queue);
  console.info("[worker] started — relaying outbox every 2s");

  let stopping = false;
  const tick = async () => {
    if (stopping) return;
    try {
      const n = await relayOutbox(queue);
      if (n > 0) console.info(`[worker] relayed ${n} event(s)`);
    } catch (err) {
      console.error("[worker] relay failed", err);
    }
    if (!stopping) setTimeout(tick, 2_000);
  };
  void tick();

  const shutdown = async () => {
    stopping = true;
    console.info("[worker] shutting down");
    await queue.stop();
    await db.$disconnect();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
