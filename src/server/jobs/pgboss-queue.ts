import PgBoss from "pg-boss";
import { EVENT_TYPES, parseEventPayload, type EventPayload, type EventType } from "./events";
import type { JobHandler, JobQueue } from "./queue";

/** pg-boss adapter: jobs live in the `pgboss` schema of the same PostgreSQL database. */
export class PgBossQueue implements JobQueue {
  private readonly boss: PgBoss;

  constructor(connectionString: string) {
    this.boss = new PgBoss({ connectionString, schema: "pgboss" });
    this.boss.on("error", (err) => console.error("[queue] pg-boss error", err));
  }

  async start(): Promise<void> {
    await this.boss.start();
    for (const type of EVENT_TYPES) {
      await this.boss.createQueue(type, {
        name: type,
        retryLimit: 5,
        retryDelay: 30,
        retryBackoff: true,
      });
    }
  }

  async stop(): Promise<void> {
    await this.boss.stop({ graceful: true });
  }

  async send<T extends EventType>(
    type: T,
    payload: EventPayload<T>,
    opts: { singletonKey?: string } = {},
  ): Promise<void> {
    await this.boss.send(type, payload as object, { singletonKey: opts.singletonKey });
  }

  async work<T extends EventType>(type: T, handler: JobHandler<T>): Promise<void> {
    await this.boss.work(type, async (jobs) => {
      for (const job of jobs) {
        await handler(parseEventPayload(type, job.data), { jobId: job.id });
      }
    });
  }
}
