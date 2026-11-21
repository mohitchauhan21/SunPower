import { withActor } from "@/server/http";
import { ROLE_PERMISSIONS } from "@/server/auth/permissions";

export const dynamic = "force-dynamic";

/** The signed-in user and their permissions (used by the UI to hide controls; never as protection). */
export const GET = withActor(async (_req, actor) => ({
  id: actor.id,
  name: actor.name,
  role: actor.role,
  permissions: [...ROLE_PERMISSIONS[actor.role]],
}));
