import NextAuth from "next-auth";
import { NextResponse } from "next/server";
import { authConfig } from "@/server/auth/auth.config";
import { ROLE_HOME, canAccessPath, isPublicPath } from "@/server/auth/permissions";

const { auth } = NextAuth(authConfig);

/**
 * First line of defence: page access by role. Services and API handlers check fine-grained
 * permissions again, so this is never the only protection.
 */
export default auth((req) => {
  const { pathname, search } = req.nextUrl;
  const role = req.auth?.user?.role;

  if (pathname === "/login" && role) {
    return NextResponse.redirect(new URL(ROLE_HOME[role], req.url));
  }
  if (isPublicPath(pathname)) return NextResponse.next();

  if (!req.auth?.user) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { error: { code: "UNAUTHENTICATED", message: "Please sign in to continue." } },
        { status: 401 },
      );
    }
    const login = new URL("/login", req.url);
    login.searchParams.set("callbackUrl", pathname + search);
    return NextResponse.redirect(login);
  }

  // API handlers enforce their own permissions.
  if (pathname.startsWith("/api/")) return NextResponse.next();

  if (!canAccessPath(role, pathname)) {
    return NextResponse.rewrite(new URL("/forbidden", req.url), { status: 403 });
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|webp|ico|txt)$).*)"],
};
