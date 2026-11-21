"use server";

import { AuthError } from "next-auth";
import { signIn } from "@/server/auth";
import { loginSchema, safeCallbackUrl } from "@/lib/validation/auth";

export interface LoginState {
  error?: string;
  fieldErrors?: Partial<Record<"email" | "password", string>>;
  email?: string;
}

export async function loginAction(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const parsed = loginSchema.safeParse({ email: formData.get("email"), password: formData.get("password") });
  const email = typeof formData.get("email") === "string" ? String(formData.get("email")) : "";
  if (!parsed.success) {
    const f = parsed.error.flatten().fieldErrors;
    return { email, fieldErrors: { email: f.email?.[0], password: f.password?.[0] } };
  }
  try {
    await signIn("credentials", {
      ...parsed.data,
      redirectTo: safeCallbackUrl(formData.get("callbackUrl")) ?? "/",
    });
    return {};
  } catch (err) {
    if (err instanceof AuthError) {
      return {
        email,
        error:
          "That email and password don't match an active account. Too many tries will pause sign-in for 15 minutes.",
      };
    }
    throw err; // NEXT_REDIRECT on success
  }
}
