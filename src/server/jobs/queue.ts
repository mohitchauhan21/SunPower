import type { EventPayload, EventType } from "./events";

/**
 * Queue abstraction. Dev and production use pg-boss (Postgres-backed, no Redis).
 * Moving to BullMQ + Redis later means writing one more adapter that implements this interface.
 */
export type JobHandler<T extends EventType> = (
  payload: EventPayload<T>,
  meta: { jobId: string },
) => Promise<void>;

export interface JobQueue {
  start(): Promise<void>;
  stop(): Promise<void>;
  send<T extends EventType>(
    type: T,
    payload: EventPayload<T>,
    opts?: { singletonKey?: string },
  ): Promise<void>;
  work<T extends EventType>(type: T, handler: JobHandler<T>): Promise<void>;
}

/** Runs handlers inline. Used by tests and by scripts that need deterministic execution. */
export class InMemoryQueue implements JobQueue {
  private handlers = new Map<EventType, JobHandler<EventType>>();
  readonly sent: { type: EventType; payload: unknown }[] = [];
  private counter = 0;

  async start(): Promise<void> {}
  async stop(): Promise<void> {}

  async send<T extends EventType>(type: T, payload: EventPayload<T>): Promise<void> {
    this.sent.push({ type, payload });
    const handler = this.handlers.get(type) as JobHandler<T> | undefined;
    if (handler) await handler(payload, { jobId: `mem-${++this.counter}` });
  }

  async work<T extends EventType>(type: T, handler: JobHandler<T>): Promise<void> {
    this.handlers.set(type, handler as unknown as JobHandler<EventType>);
  }
}
