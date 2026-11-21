import { redirect } from "next/navigation";
import { getCurrentActor } from "@/server/auth";
import { ROLE_HOME } from "@/server/auth/permissions";

export default async function Home() {
  const actor = await getCurrentActor();
  redirect(actor ? ROLE_HOME[actor.role] : "/login");
}
