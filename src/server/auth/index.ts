import "server-only";
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import { cache } from "react";
import { db } from "@/server/db";
import { authConfig } from "./auth.config";
import { verifyCredentials } from "./credentials";
import type { Actor } from "./actor";

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    Credentials({
      credentials: { email: {}, password: {} },
      authorize: (raw) => verifyCredentials(raw),
    }),
  ],
});

/**
 * The signed-in person for this request, re-checked against the database so a deactivated
 * account loses access immediately (not only when its 12-hour session expires).
 * Cached per request.
 */
export const getCurrentActor = cache(async (): Promise<Actor | null> => {
  const session = await auth();
  const id = session?.user?.id;
  if (!id) return null;
  const user = await db.user.findUnique({
    where: { id },
    select: { id: true, name: true, role: true, active: true },
  });
  if (!user?.active) return null;
  return { id: user.id, name: user.name, role: user.role };
});
