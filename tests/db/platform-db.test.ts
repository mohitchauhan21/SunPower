import { describe, expect, it } from "vitest";
import { db, isUniqueViolation, withTransaction } from "@/server/db";
import { writeAudit } from "@/server/audit";
import { SYSTEM_ACTOR, type Actor } from "@/server/auth/actor";
import { verifyCredentials, LOGIN_MAX_ATTEMPTS } from "@/server/auth/credentials";
import { enqueueEvent, relayOutbox, OUTBOX_MAX_ATTEMPTS } from "@/server/jobs/outbox";
import { InMemoryQueue, type JobQueue } from "@/server/jobs/queue";
import { listProducts } from "@/server/services/catalog.service";
import { consumeRateLimit } from "@/server/services/rate-limit.service";
import { nextDocumentNumber, nextSequenceValue } from "@/server/services/sequence.service";

const password = process.env.SEED_USER_PASSWORD ?? "SunPower@123";

async function actorFor(email: string): Promise<Actor> {
  const u = await db.user.findUniqueOrThrow({ where: { email } });
  return { id: u.id, name: u.name, role: u.role };
}

describe("database constraints", () => {
  it("rejects a duplicate serial number", async () => {
    const existing = await db.serialUnit.findFirstOrThrow();
    const err = await db.serialUnit
      .create({ data: { serial: existing.serial, productId: existing.productId } })
      .catch((e: unknown) => e);
    expect(isUniqueViolation(err, "serial")).toBe(true);
  });

  it("rejects a duplicate customer phone", async () => {
    const existing = await db.customer.findFirstOrThrow();
    const err = await db.customer
      .create({ data: { name: "Dup", phone: existing.phone, addressLine: "x", city: "Pune" } })
      .catch((e: unknown) => e);
    expect(isUniqueViolation(err, "phone")).toBe(true);
  });

  it("indexes serial, customer phone and ticket number", async () => {
    const rows = await db.$queryRaw<{ indexname: string }[]>`
      SELECT indexname FROM pg_indexes WHERE schemaname = 'public'`;
    const names = rows.map((r) => r.indexname);
    expect(names).toContain("SerialUnit_serial_key");
    expect(names).toContain("Customer_phone_key");
    expect(names).toContain("Ticket_number_key");
  });

  it("finds a serial and a customer by phone quickly", async () => {
    const serial = await db.serialUnit.findFirstOrThrow({ orderBy: { createdAt: "desc" } });
    const customer = await db.customer.findFirstOrThrow();
    const t0 = performance.now();
    await db.serialUnit.findUnique({
      where: { serial: serial.serial },
      include: { product: true, customer: true },
    });
    await db.customer.findUnique({ where: { phone: customer.phone } });
    expect(performance.now() - t0).toBeLessThan(300);
  });
});

describe("transactions and audit", () => {
  it("rolls back the audit entry with the change it describes", async () => {
    const before = await db.auditLog.count();
    await expect(
      withTransaction(async (tx) => {
        await writeAudit(tx, {
          actor: SYSTEM_ACTOR,
          action: "test.rollback",
          entityType: "Test",
          entityId: "1",
        });
        throw new Error("boom");
      }),
    ).rejects.toThrow("boom");
    expect(await db.auditLog.count()).toBe(before);
  });

  it("records who, what, before, after and when", async () => {
    const sales = await actorFor("sales@sunpower.test");
    await withTransaction((tx) =>
      writeAudit(tx, {
        actor: sales,
        action: "lead.status_changed",
        entityType: "Lead",
        entityId: "lead-1",
        before: { status: "NEW" },
        after: { status: "CONTACTED", passwordHash: "secret" },
      }),
    );
    const entry = await db.auditLog.findFirstOrThrow({
      where: { entityId: "lead-1" },
      orderBy: { createdAt: "desc" },
    });
    expect(entry.actorId).toBe(sales.id);
    expect(entry.actorRole).toBe("SALES");
    expect(entry.before).toEqual({ status: "NEW" });
    expect(entry.after).toEqual({ status: "CONTACTED", passwordHash: "[redacted]" });
    expect(entry.createdAt).toBeInstanceOf(Date);
  });

  it("records automations with no human actor", async () => {
    await writeAudit(db, {
      actor: SYSTEM_ACTOR,
      action: "warranty.started",
      entityType: "SerialUnit",
      entityId: "s-1",
    });
    const entry = await db.auditLog.findFirstOrThrow({ where: { entityId: "s-1" } });
    expect(entry.actorId).toBeNull();
    expect(entry.actorRole).toBeNull();
  });
});

describe("document numbers", () => {
  it("never hands out the same number twice under concurrency", async () => {
    const values = await Promise.all(
      Array.from({ length: 25 }, () => nextSequenceValue(db, "test:concurrency")),
    );
    expect(new Set(values).size).toBe(25);
    expect(Math.max(...values) - Math.min(...values)).toBe(24);
  });

  it("formats documents and restarts invoices each financial year", async () => {
    expect(await nextDocumentNumber(db, "ticket")).toMatch(/^TK-\d{5}$/);
    const a = await nextDocumentNumber(db, "invoice", new Date("2031-03-31T06:00:00Z"));
    const b = await nextDocumentNumber(db, "invoice", new Date("2031-04-01T06:00:00Z"));
    expect(a).toBe("SP/30-31/0001");
    expect(b).toBe("SP/31-32/0001");
  });

  it("doesn't burn a number when the transaction rolls back", async () => {
    await nextSequenceValue(db, "test:rollback");
    await withTransaction(async (tx) => {
      await nextSequenceValue(tx, "test:rollback");
      throw new Error("rollback");
    }).catch(() => {});
    expect(await nextSequenceValue(db, "test:rollback")).toBe(2);
  });
});

describe("sign-in", () => {
  it("accepts the right password and returns the role", async () => {
    const user = await verifyCredentials({ email: "Director@SunPower.test", password });
    expect(user).toMatchObject({ email: "director@sunpower.test", role: "DIRECTOR" });
  });

  it("rejects a wrong password, an unknown email and malformed input the same way", async () => {
    expect(await verifyCredentials({ email: "director@sunpower.test", password: "wrong" })).toBeNull();
    expect(await verifyCredentials({ email: "nobody@sunpower.test", password })).toBeNull();
    expect(await verifyCredentials({ email: "not-an-email", password })).toBeNull();
    expect(await verifyCredentials(null)).toBeNull();
  });

  it("rejects deactivated accounts", async () => {
    await db.user.update({ where: { email: "tech15@sunpower.test" }, data: { active: false } });
    expect(await verifyCredentials({ email: "tech15@sunpower.test", password })).toBeNull();
    await db.user.update({ where: { email: "tech15@sunpower.test" }, data: { active: true } });
  });

  it("locks an email after too many attempts, even with the right password", async () => {
    const email = "tech14@sunpower.test";
    for (let i = 0; i < LOGIN_MAX_ATTEMPTS; i++) await verifyCredentials({ email, password: "wrong" });
    expect(await verifyCredentials({ email, password })).toBeNull();
    await db.rateLimitBucket.delete({ where: { key: `login:${email}` } });
    expect(await verifyCredentials({ email, password })).not.toBeNull();
  });
});

describe("rate limiting", () => {
  it("allows up to the limit then blocks, and resets after the window", async () => {
    const key = `test:${Date.now()}`;
    const results = [];
    for (let i = 0; i < 4; i++) results.push((await consumeRateLimit(db, key, 3, 60_000)).allowed);
    expect(results).toEqual([true, true, true, false]);
    await db.rateLimitBucket.update({
      where: { key },
      data: { windowStart: new Date(Date.now() - 120_000) },
    });
    expect((await consumeRateLimit(db, key, 3, 60_000)).allowed).toBe(true);
  });
});

describe("outbox", () => {
  it("drops events whose transaction rolled back", async () => {
    await withTransaction(async (tx) => {
      await enqueueEvent(tx, "order.confirmed", { orderId: "rolled-back" });
      throw new Error("rollback");
    }).catch(() => {});
    expect(await db.outboxEvent.count({ where: { payload: { equals: { orderId: "rolled-back" } } } })).toBe(
      0,
    );
  });

  it("refuses malformed payloads at write time", async () => {
    await expect(enqueueEvent(db, "order.confirmed", { orderId: "" })).rejects.toThrow();
  });

  it("relays committed events to the queue exactly once", async () => {
    await db.outboxEvent.deleteMany();
    await enqueueEvent(db, "order.confirmed", { orderId: "o-relay" });
    const queue = new InMemoryQueue();
    expect(await relayOutbox(queue)).toBe(1);
    expect(await relayOutbox(queue)).toBe(0);
    expect(queue.sent).toEqual([{ type: "order.confirmed", payload: { orderId: "o-relay" } }]);
    const row = await db.outboxEvent.findFirstOrThrow();
    expect(row.status).toBe("PROCESSED");
  });

  it("retries with back-off and gives up after the maximum attempts", async () => {
    await db.outboxEvent.deleteMany();
    await enqueueEvent(db, "order.delivered", { orderId: "o-fail" });
    const failing: JobQueue = {
      start: async () => {},
      stop: async () => {},
      work: async () => {},
      send: async () => {
        throw new Error("queue down");
      },
    };
    expect(await relayOutbox(failing)).toBe(0);
    let row = await db.outboxEvent.findFirstOrThrow();
    expect(row).toMatchObject({ status: "PENDING", attempts: 1, error: "queue down" });
    expect(row.availableAt.getTime()).toBeGreaterThan(Date.now());

    await db.outboxEvent.update({
      where: { id: row.id },
      data: { attempts: OUTBOX_MAX_ATTEMPTS - 1, availableAt: new Date(0) },
    });
    await relayOutbox(failing);
    row = await db.outboxEvent.findFirstOrThrow();
    expect(row.status).toBe("FAILED");
  });
});

describe("catalogue permissions (field-level)", () => {
  it("technicians receive products without cost", async () => {
    const products = await listProducts(await actorFor("tech@sunpower.test"));
    expect(products.length).toBeGreaterThan(0);
    for (const p of products) expect(p).not.toHaveProperty("costPaise");
  });

  it("the director receives cost", async () => {
    const products = await listProducts(await actorFor("director@sunpower.test"));
    expect(products[0]).toHaveProperty("costPaise");
  });
});
