import bcrypt from "bcryptjs";
import type { Role } from "@prisma/client";
import { db, type DbClient } from "@/server/db";
import { loginSchema } from "@/lib/validation/auth";
import { consumeRateLimit } from "@/server/services/rate-limit.service";

export const LOGIN_MAX_ATTEMPTS = 10;
export const LOGIN_WINDOW_MS = 15 * 60 * 1000;

let dummyHash: string | undefined;
/** Compared when the email is unknown, so response time doesn't reveal which emails exist. */
function getDummyHash(): string {
  dummyHash ??= bcrypt.hashSync("not-a-real-password-placeholder", 10);
  return dummyHash;
}

export interface VerifiedUser {
  id: string;
  name: string;
  email: string;
  role: Role;
}

/**
 * Check an email/password pair. Returns the user, or null for any failure (unknown email,
 * wrong password, deactivated account, too many attempts) — callers can't tell which.
 */
export async function verifyCredentials(raw: unknown, client: DbClient = db): Promise<VerifiedUser | null> {
  const parsed = loginSchema.safeParse(raw);
  if (!parsed.success) return null;
  const { email, password } = parsed.data;

  const limit = await consumeRateLimit(client, `login:${email}`, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_MS);
  if (!limit.allowed) return null;

  const user = await client.user.findUnique({ where: { email } });
  const ok = await bcrypt.compare(password, user?.passwordHash ?? getDummyHash());
  if (!user || !user.active || !ok) return null;

  return { id: user.id, name: user.name, email: user.email, role: user.role };
}
