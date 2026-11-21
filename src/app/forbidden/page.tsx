import type { Metadata } from "next";
import Link from "next/link";
import { ShieldAlert } from "lucide-react";

export const metadata: Metadata = { title: "No access" };

export default function ForbiddenPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <div className="max-w-md text-center">
        <ShieldAlert className="text-muted-foreground mx-auto mb-4 size-10" aria-hidden />
        <h1 className="text-xl font-semibold">You don&apos;t have access to this page</h1>
        <p className="text-muted-foreground mt-2">
          Your role doesn&apos;t include this area. If you need it, ask an administrator.
        </p>
        <Link
          href="/"
          className="bg-primary text-primary-foreground mt-6 inline-flex h-11 items-center rounded-lg px-4 font-medium"
        >
          Go to my home page
        </Link>
      </div>
    </main>
  );
}
