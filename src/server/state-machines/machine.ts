import { IllegalTransitionError } from "@/server/errors";

/**
 * A tiny explicit state machine: a table of allowed transitions.
 * The server calls `assertTransition` before every status change; illegal moves throw
 * IllegalTransitionError, which the UI shows as a readable message.
 */
export interface StateMachine<S extends string> {
  readonly name: string;
  readonly states: readonly S[];
  readonly initial: S;
  readonly transitions: Readonly<Record<S, readonly S[]>>;
  canTransition(from: S, to: S): boolean;
  allowedNext(from: S): readonly S[];
  assertTransition(from: S, to: S): void;
  isFinal(state: S): boolean;
}

export function defineMachine<S extends string>(config: {
  name: string;
  initial: S;
  transitions: Record<S, readonly S[]>;
}): StateMachine<S> {
  const states = Object.keys(config.transitions) as S[];
  for (const [from, tos] of Object.entries(config.transitions) as [S, readonly S[]][]) {
    for (const to of tos) {
      if (!(to in config.transitions)) {
        throw new Error(`${config.name}: transition ${from} → ${to} targets an unknown state`);
      }
    }
  }
  const frozen = Object.freeze({ ...config.transitions });
  return {
    name: config.name,
    states,
    initial: config.initial,
    transitions: frozen,
    canTransition: (from, to) => frozen[from]?.includes(to) ?? false,
    allowedNext: (from) => frozen[from] ?? [],
    assertTransition(from, to) {
      if (!(frozen[from]?.includes(to) ?? false)) {
        throw new IllegalTransitionError(config.name, from, to, frozen[from] ?? []);
      }
    },
    isFinal: (state) => (frozen[state]?.length ?? 0) === 0,
  };
}
