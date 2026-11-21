import type { Role } from "@prisma/client";
import { ForbiddenError, UnauthenticatedError } from "@/server/errors";
import { hasPermission, type Permission } from "./permissions";

/**
 * The person (or system process) performing an action. Every service function takes an Actor,
 * so permission checks and audit entries never depend on UI code.
 */
export interface Actor {
  id: string;
  role: Role;
  name: string;
}

/** For automations (outbox handlers, jobs). Audit entries show actorId = null, actorRole = null. */
export const SYSTEM_ACTOR = Object.freeze({
  id: "system",
  role: "ADMIN",
  name: "System",
} as const satisfies Actor);

export function isSystemActor(actor: Actor): boolean {
  return actor.id === SYSTEM_ACTOR.id;
}

export function requirePermission(actor: Actor | null | undefined, permission: Permission): Actor {
  if (!actor) throw new UnauthenticatedError();
  if (!hasPermission(actor.role, permission)) {
    throw new ForbiddenError();
  }
  return actor;
}

export function requireAnyPermission(
  actor: Actor | null | undefined,
  permissions: readonly Permission[],
): Actor {
  if (!actor) throw new UnauthenticatedError();
  if (!permissions.some((p) => hasPermission(actor.role, p))) throw new ForbiddenError();
  return actor;
}
