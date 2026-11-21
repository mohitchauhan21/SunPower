import type { Prisma } from "@prisma/client";
import type { DbClient } from "@/server/db";
import { isSystemActor, type Actor } from "@/server/auth/actor";

/** Keys that must never be written to the audit trail. */
const REDACTED_KEYS = new Set(["passwordHash", "password", "token", "tokenHash", "secret"]);

export interface AuditEntry {
  actor: Actor;
  /** Verb in dot form, e.g. "lead.status_changed", "order.dispatched", "serial.linked". */
  action: string;
  entityType: string;
  entityId: string;
  before?: unknown;
  after?: unknown;
}

/** Make a value safe to store as JSON: drop secrets, turn Dates into ISO strings, BigInt into strings. */
export function sanitizeForAudit(value: unknown): Prisma.InputJsonValue | null {
  if (value === undefined || value === null) return null;
  return JSON.parse(
    JSON.stringify(value, (key, v: unknown) => {
      if (REDACTED_KEYS.has(key)) return "[redacted]";
      if (typeof v === "bigint") return v.toString();
      return v;
    }),
  ) as Prisma.InputJsonValue;
}

/** Only the fields that changed, so the audit viewer can show a compact diff. */
export function diffForAudit(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): { before: Record<string, unknown>; after: Record<string, unknown> } {
  const b: Record<string, unknown> = {};
  const a: Record<string, unknown> = {};
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    const bv = before[key];
    const av = after[key];
    if (JSON.stringify(bv) !== JSON.stringify(av)) {
      b[key] = bv;
      a[key] = av;
    }
  }
  return { before: b, after: a };
}

/**
 * Write one audit entry. Pass the transaction client so the entry commits (or rolls back)
 * together with the change it describes.
 */
export async function writeAudit(client: DbClient, entry: AuditEntry): Promise<void> {
  const system = isSystemActor(entry.actor);
  await client.auditLog.create({
    data: {
      actorId: system ? null : entry.actor.id,
      actorRole: system ? null : entry.actor.role,
      action: entry.action,
      entityType: entry.entityType,
      entityId: entry.entityId,
      before: sanitizeForAudit(entry.before) ?? undefined,
      after: sanitizeForAudit(entry.after) ?? undefined,
    },
  });
}
