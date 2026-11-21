import { Prisma, PrismaClient } from "@prisma/client";

/**
 * One PrismaClient per process. In dev, Next.js hot-reload would otherwise open a new pool
 * on every edit, so the client is cached on globalThis.
 */
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const db: PrismaClient =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.PRISMA_LOG_QUERIES === "1" ? ["query", "warn", "error"] : ["warn", "error"],
  });

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = db;

/** A Prisma transaction client. Services accept this so callers can compose them in one transaction. */
export type Tx = Prisma.TransactionClient;

/** Either the root client or a transaction client. */
export type DbClient = PrismaClient | Tx;

/**
 * Run work in a single DB transaction. Multi-row operations (dispatch, payments, stock) must use this.
 * Serializable is available for the few places where it matters (e.g. stock reservation).
 */
export function withTransaction<T>(
  fn: (tx: Tx) => Promise<T>,
  opts: { isolationLevel?: Prisma.TransactionIsolationLevel; timeoutMs?: number } = {},
): Promise<T> {
  return db.$transaction(fn, {
    isolationLevel: opts.isolationLevel,
    timeout: opts.timeoutMs ?? 15_000,
    maxWait: 5_000,
  });
}

/** True when an error is a Postgres unique-constraint violation (Prisma P2002). */
export function isUniqueViolation(e: unknown, field?: string): boolean {
  if (!(e instanceof Prisma.PrismaClientKnownRequestError) || e.code !== "P2002") return false;
  if (!field) return true;
  const target = e.meta?.target;
  return Array.isArray(target) ? target.includes(field) : String(target ?? "").includes(field);
}
