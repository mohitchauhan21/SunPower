import type { Prisma } from "@prisma/client";
import type { DbClient } from "@/server/db";
import { db } from "@/server/db";
import { isEventType, parseEventPayload, type EventPayload, type EventType } from "./events";
import type { JobQueue } from "./queue";

export const OUTBOX_MAX_ATTEMPTS = 8;

/**
 * Record an event in the same transaction as the state change that caused it.
 * If the transaction rolls back, the event never existed; if it commits, the event will be delivered.
 */
export async function enqueueEvent<T extends EventType>(
  client: DbClient,
  type: T,
  payload: EventPayload<T>,
  opts: { availableAt?: Date } = {},
): Promise<void> {
  const data = parseEventPayload(type, payload);
  await client.outboxEvent.create({
    data: { type, payload: data as Prisma.InputJsonValue, availableAt: opts.availableAt ?? new Date() },
  });
}

/** Exponential back-off: 10s, 20s, 40s … capped at 1 hour. */
export function outboxBackoffMs(attempts: number): number {
  return Math.min(10_000 * 2 ** Math.max(0, attempts - 1), 3_600_000);
}

/**
 * Move a batch of due outbox events onto the job queue. Rows are locked with SKIP LOCKED,
 * so several workers can run without delivering the same event twice.
 * Returns how many events were relayed.
 */
export async function relayOutbox(queue: JobQueue, batchSize = 50): Promise<number> {
  return db.$transaction(async (tx) => {
    const rows = await tx.$queryRaw<{ id: string; type: string; payload: unknown; attempts: number }[]>`
      SELECT "id", "type", "payload", "attempts" FROM "OutboxEvent"
      WHERE "status" = 'PENDING' AND "availableAt" <= now()
      ORDER BY "createdAt"
      LIMIT ${batchSize}
      FOR UPDATE SKIP LOCKED`;

    let relayed = 0;
    for (const row of rows) {
      try {
        if (!isEventType(row.type)) throw new Error(`Unknown event type ${row.type}`);
        await queue.send(row.type, parseEventPayload(row.type, row.payload), { singletonKey: row.id });
        await tx.outboxEvent.update({
          where: { id: row.id },
          data: { status: "PROCESSED", processedAt: new Date(), attempts: row.attempts + 1, error: null },
        });
        relayed++;
      } catch (err) {
        const attempts = row.attempts + 1;
        await tx.outboxEvent.update({
          where: { id: row.id },
          data: {
            attempts,
            status: attempts >= OUTBOX_MAX_ATTEMPTS ? "FAILED" : "PENDING",
            availableAt: new Date(Date.now() + outboxBackoffMs(attempts)),
            error: err instanceof Error ? err.message.slice(0, 1000) : String(err),
          },
        });
      }
    }
    return relayed;
  });
}
