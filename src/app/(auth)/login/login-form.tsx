"use client";

import { useActionState } from "react";
import { LoaderCircle, LogIn } from "lucide-react";
import { loginAction, type LoginState } from "./actions";

export function LoginForm({ callbackUrl }: { callbackUrl?: string }) {
  const [state, formAction, pending] = useActionState<LoginState, FormData>(loginAction, {});

  return (
    <form action={formAction} className="space-y-5" noValidate>
      {callbackUrl ? <input type="hidden" name="callbackUrl" value={callbackUrl} /> : null}

      {state.error ? (
        <p
          role="alert"
          className="border-danger/40 bg-danger/10 text-foreground rounded-lg border px-3 py-2 text-sm"
        >
          {state.error}
        </p>
      ) : null}

      <div className="space-y-1.5">
        <label htmlFor="email" className="block text-sm font-medium">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
          defaultValue={state.email}
          aria-invalid={Boolean(state.fieldErrors?.email)}
          aria-describedby={state.fieldErrors?.email ? "email-error" : undefined}
          className="border-border bg-surface focus-visible:border-ring block h-11 w-full rounded-lg border px-3 text-base outline-none"
        />
        {state.fieldErrors?.email ? (
          <p id="email-error" className="text-danger text-sm">
            {state.fieldErrors.email}
          </p>
        ) : null}
      </div>

      <div className="space-y-1.5">
        <label htmlFor="password" className="block text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          aria-invalid={Boolean(state.fieldErrors?.password)}
          aria-describedby={state.fieldErrors?.password ? "password-error" : undefined}
          className="border-border bg-surface focus-visible:border-ring block h-11 w-full rounded-lg border px-3 text-base outline-none"
        />
        {state.fieldErrors?.password ? (
          <p id="password-error" className="text-danger text-sm">
            {state.fieldErrors.password}
          </p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={pending}
        className="bg-primary text-primary-foreground inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg px-4 font-medium transition-opacity duration-200 disabled:opacity-70"
      >
        {pending ? (
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
        ) : (
          <LogIn className="size-4" aria-hidden />
        )}
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
