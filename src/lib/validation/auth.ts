import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password.").max(200),
});

export type LoginInput = z.infer<typeof loginSchema>;

/** Only same-site relative paths are allowed as post-login redirects (no open redirects). */
export function safeCallbackUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return null;
  if (value.startsWith("/login") || value.startsWith("/api/")) return null;
  return value;
}
