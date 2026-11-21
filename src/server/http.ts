import "server-only";
import { NextResponse } from "next/server";
import { ZodError } from "zod";
import { isAppError } from "@/server/errors";
import { getCurrentActor } from "@/server/auth";
import type { Actor } from "@/server/auth/actor";
import { UnauthenticatedError } from "@/server/errors";

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
}

/** Map any thrown error to a safe JSON response. Unknown errors never leak internals. */
export function toErrorResponse(err: unknown): NextResponse<ApiErrorBody> {
  if (isAppError(err)) {
    return NextResponse.json(
      { error: { code: err.code, message: err.message, details: err.details } },
      { status: err.status },
    );
  }
  if (err instanceof ZodError) {
    return NextResponse.json(
      {
        error: {
          code: "VALIDATION",
          message: "Some fields need attention.",
          details: { fieldErrors: err.flatten().fieldErrors },
        },
      },
      { status: 400 },
    );
  }
  console.error("[api] unexpected error", err);
  return NextResponse.json(
    { error: { code: "INTERNAL", message: "Something went wrong on our side. Please try again." } },
    { status: 500 },
  );
}

/**
 * Thin wrapper for route handlers: resolves the signed-in actor, runs the service call,
 * and turns errors into JSON. Business logic stays in services.
 */
export function withActor<Ctx>(
  handler: (req: Request, actor: Actor, ctx: Ctx) => Promise<Response | unknown>,
) {
  return async (req: Request, ctx: Ctx): Promise<Response> => {
    try {
      const actor = await getCurrentActor();
      if (!actor) throw new UnauthenticatedError();
      const result = await handler(req, actor, ctx);
      return result instanceof Response ? result : NextResponse.json({ data: result });
    } catch (err) {
      return toErrorResponse(err);
    }
  };
}
