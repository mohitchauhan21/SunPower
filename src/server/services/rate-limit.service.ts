import type { DbClient } from "@/server/db";

/**
 * Fixed-window rate limiting stored in Postgres (no Redis). One atomic statement per check.
 * Returns whether this request is allowed and how many requests the window has seen.
 */
export async function consumeRateLimit(
  client: DbClient,
  key: string,
  limit: number,
  windowMs: number,
): Promise<{ allowed: boolean; count: number }> {
  const windowSeconds = Math.ceil(windowMs / 1000);
  const rows = await client.$queryRaw<{ count: number }[]>`
    INSERT INTO "RateLimitBucket" ("key", "windowStart", "count") VALUES (${key}, now(), 1)
    ON CONFLICT ("key") DO UPDATE SET
      "count" = CASE WHEN "RateLimitBucket"."windowStart" < now() - make_interval(secs => ${windowSeconds})
                     THEN 1 ELSE "RateLimitBucket"."count" + 1 END,
      "windowStart" = CASE WHEN "RateLimitBucket"."windowStart" < now() - make_interval(secs => ${windowSeconds})
                     THEN now() ELSE "RateLimitBucket"."windowStart" END
    RETURNING "count"`;
  const count = rows[0]?.count ?? limit + 1;
  return { allowed: count <= limit, count };
}
