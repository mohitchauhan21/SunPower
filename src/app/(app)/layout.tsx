import Link from "next/link";
import { redirect } from "next/navigation";
import { LogOut, Sun } from "lucide-react";
import { getCurrentActor, signOut } from "@/server/auth";

/**
 * Temporary signed-in frame for Phase 0a. Phase 0b replaces it with the full app shell
 * (collapsible sidebar, Cmd/Ctrl+K search, mobile bottom navigation).
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const actor = await getCurrentActor();
  if (!actor) redirect("/login");

  async function signOutAction() {
    "use server";
    await signOut({ redirectTo: "/login" });
  }

  return (
    <div className="min-h-dvh">
      <header className="border-border bg-surface flex h-14 items-center justify-between border-b px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Sun className="text-accent size-5" aria-hidden />
          SunPower
        </Link>
        <div className="flex items-center gap-3 text-sm">
          <span>
            <span className="font-medium">{actor.name}</span>
            <span className="text-muted-foreground"> · {actor.role.toLowerCase()}</span>
          </span>
          <form action={signOutAction}>
            <button
              type="submit"
              className="hover:bg-surface-muted inline-flex h-11 items-center gap-1.5 rounded-lg px-3"
            >
              <LogOut className="size-4" aria-hidden />
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
