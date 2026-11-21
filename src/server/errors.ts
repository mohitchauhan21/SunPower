/**
 * Typed errors thrown by the service layer. Route handlers and server actions map these to
 * HTTP status codes and human-readable messages; nothing else should leak to the client.
 */

export type AppErrorCode =
  | "VALIDATION"
  | "UNAUTHENTICATED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "ILLEGAL_TRANSITION"
  | "BUSINESS_RULE"
  | "RATE_LIMITED";

export class AppError extends Error {
  readonly code: AppErrorCode;
  readonly status: number;
  readonly details?: Record<string, unknown>;

  constructor(code: AppErrorCode, status: number, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = new.target.name;
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export class ValidationError extends AppError {
  constructor(message: string, fieldErrors?: Record<string, string[]>) {
    super("VALIDATION", 400, message, fieldErrors ? { fieldErrors } : undefined);
  }
}

export class UnauthenticatedError extends AppError {
  constructor(message = "Please sign in to continue.") {
    super("UNAUTHENTICATED", 401, message);
  }
}

export class ForbiddenError extends AppError {
  constructor(message = "You don't have permission to do that.") {
    super("FORBIDDEN", 403, message);
  }
}

export class NotFoundError extends AppError {
  constructor(entity: string, id?: string) {
    super("NOT_FOUND", 404, `${entity} not found.`, id ? { id } : undefined);
  }
}

export class ConflictError extends AppError {
  constructor(message: string, details?: Record<string, unknown>) {
    super("CONFLICT", 409, message, details);
  }
}

export class BusinessRuleError extends AppError {
  constructor(message: string, details?: Record<string, unknown>) {
    super("BUSINESS_RULE", 422, message, details);
  }
}

export class RateLimitedError extends AppError {
  constructor(message = "Too many requests. Please wait a moment and try again.") {
    super("RATE_LIMITED", 429, message);
  }
}

export class IllegalTransitionError<S extends string = string> extends AppError {
  readonly machine: string;
  readonly from: S;
  readonly to: S;

  constructor(machine: string, from: S, to: S, allowed: readonly S[]) {
    const allowedText = allowed.length ? allowed.join(", ") : "none (final state)";
    super(
      "ILLEGAL_TRANSITION",
      409,
      `${machine} cannot move from ${from} to ${to}. Allowed next steps: ${allowedText}.`,
      { machine, from, to, allowed: [...allowed] },
    );
    this.machine = machine;
    this.from = from;
    this.to = to;
  }
}

export function isAppError(e: unknown): e is AppError {
  return e instanceof AppError;
}
