import type { Metadata } from "next";
import { Sun } from "lucide-react";
import { safeCallbackUrl } from "@/lib/validation/auth";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string }>;
}) {
  const { callbackUrl } = await searchParams;
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <span className="bg-accent text-accent-foreground flex size-10 items-center justify-center rounded-xl">
            <Sun className="size-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">SunPower Solutions</h1>
            <p className="text-muted-foreground text-sm">Sign in to your workspace</p>
          </div>
        </div>
        <div className="border-border bg-surface rounded-[var(--radius-card)] border p-6 shadow-sm">
          <LoginForm callbackUrl={safeCallbackUrl(callbackUrl) ?? undefined} />
        </div>
      </div>
    </main>
  );
}
