import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { Product } from "@prisma/client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { diffForAudit, sanitizeForAudit } from "@/server/audit";
import { ValidationError } from "@/server/errors";
import { outboxBackoffMs } from "@/server/jobs/outbox";
import { parseEventPayload } from "@/server/jobs/events";
import { InMemoryQueue } from "@/server/jobs/queue";
import { ConsoleNotificationProvider, renderTemplate } from "@/server/notifications";
import { assertSafeKey, LocalDiskStorage, sniffContentType, validateUpload } from "@/server/storage";
import { redactProductCost } from "@/server/services/catalog.service";
import { formatIndianMobile, normalizeIndianMobile } from "@/lib/phone";

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0x10]);
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0]);
const PDF = new TextEncoder().encode("%PDF-1.7 ...");
const EXE = new Uint8Array([0x4d, 0x5a, 0x90, 0x00]);

describe("phone normalisation", () => {
  it.each([
    ["+91 98765 43210", "9876543210"],
    ["098765-43210", "9876543210"],
    ["919876543210", "9876543210"],
    ["9876543210", "9876543210"],
  ])("%s → %s", (input, expected) => expect(normalizeIndianMobile(input)).toBe(expected));

  it.each(["12345", "5876543210", "98765432101", "abcdefghij", ""])("rejects %s", (input) =>
    expect(normalizeIndianMobile(input)).toBeNull(),
  );

  it("formats for display", () => expect(formatIndianMobile("9876543210")).toBe("98765 43210"));
});

describe("audit helpers", () => {
  it("redacts secrets and serialises dates", () => {
    const out = sanitizeForAudit({
      email: "a@b.c",
      passwordHash: "x",
      nested: { token: "t" },
      at: new Date("2026-01-01T00:00:00Z"),
    });
    expect(out).toEqual({
      email: "a@b.c",
      passwordHash: "[redacted]",
      nested: { token: "[redacted]" },
      at: "2026-01-01T00:00:00.000Z",
    });
    expect(sanitizeForAudit(undefined)).toBeNull();
  });

  it("diffs only changed fields", () => {
    expect(diffForAudit({ status: "NEW", name: "A" }, { status: "CONTACTED", name: "A" })).toEqual({
      before: { status: "NEW" },
      after: { status: "CONTACTED" },
    });
  });
});

describe("upload validation", () => {
  it("identifies files by their bytes", () => {
    expect(sniffContentType(JPEG)).toBe("image/jpeg");
    expect(sniffContentType(PNG)).toBe("image/png");
    expect(sniffContentType(PDF)).toBe("application/pdf");
    expect(sniffContentType(EXE)).toBeNull();
  });

  it("accepts allowed types and rejects others, whatever the browser claims", () => {
    expect(validateUpload("job-photo", JPEG)).toEqual({ contentType: "image/jpeg", ext: "jpg" });
    expect(() => validateUpload("job-photo", PDF)).toThrow(ValidationError);
    expect(() => validateUpload("job-photo", EXE)).toThrow(ValidationError);
    expect(() => validateUpload("signature", JPEG)).toThrow(ValidationError);
    expect(validateUpload("signature", PNG).contentType).toBe("image/png");
  });

  it("enforces size limits and rejects empty files", () => {
    const big = new Uint8Array(1024 * 1024 + 1);
    big.set(PNG);
    expect(() => validateUpload("signature", big)).toThrow(/too large/);
    expect(() => validateUpload("job-photo", new Uint8Array())).toThrow(/empty/);
  });
});

describe("local disk storage", () => {
  let dir: string;
  let storage: LocalDiskStorage;
  beforeAll(async () => {
    dir = await mkdtemp(path.join(os.tmpdir(), "sunpower-storage-"));
    storage = new LocalDiskStorage(dir);
  });
  afterAll(async () => {
    await rm(dir, { recursive: true, force: true });
  });

  it("round-trips a file", async () => {
    await storage.put("jobs/jb-1/photo-1.jpg", JPEG, "image/jpeg");
    expect(await storage.get("jobs/jb-1/photo-1.jpg")).toEqual(JPEG);
    await storage.delete("jobs/jb-1/photo-1.jpg");
    await expect(storage.get("jobs/jb-1/photo-1.jpg")).rejects.toThrow();
  });

  it.each(["../etc/passwd", "jobs/../../x", "/abs/path", "C:\\windows", "jobs//x", ""])(
    "rejects unsafe key %s",
    (key) => {
      expect(() => assertSafeKey(key)).toThrow(ValidationError);
    },
  );
});

describe("notifications", () => {
  it("fills template placeholders and leaves missing ones visible", () => {
    expect(renderTemplate("ticket_created", { name: "Anil", ticketNumber: "TK-00001" })).toBe(
      "Hi Anil, we've logged your complaint TK-00001. A technician will contact you soon.",
    );
    expect(renderTemplate("ticket_created", { name: "Anil" })).toContain("{ticketNumber}");
  });

  it("console provider records what it would send", async () => {
    const p = new ConsoleNotificationProvider();
    const res = await p.send({
      channel: "WHATSAPP",
      to: "9876543210",
      template: "enquiry_received",
      params: { name: "A", leadNumber: "LD-1" },
    });
    expect(res.providerMessageId).toMatch(/^console-/);
    expect(p.outbox[0]?.text).toContain("LD-1");
  });
});

describe("events and queue", () => {
  it("validates event payloads", () => {
    expect(parseEventPayload("order.confirmed", { orderId: "o1" })).toEqual({ orderId: "o1" });
    expect(() => parseEventPayload("order.confirmed", { orderId: "" })).toThrow();
    expect(() => parseEventPayload("order.confirmed", {})).toThrow();
  });

  it("in-memory queue runs handlers inline", async () => {
    const q = new InMemoryQueue();
    const seen: string[] = [];
    await q.work("order.confirmed", async (p) => void seen.push(p.orderId));
    await q.send("order.confirmed", { orderId: "o1" });
    expect(seen).toEqual(["o1"]);
  });

  it("backs off exponentially up to an hour", () => {
    expect(outboxBackoffMs(1)).toBe(10_000);
    expect(outboxBackoffMs(2)).toBe(20_000);
    expect(outboxBackoffMs(20)).toBe(3_600_000);
  });
});

describe("product cost redaction", () => {
  const product = { id: "p", sku: "X", costPaise: 100, pricePaise: 200 } as Product;

  it("strips cost for technicians, warehouse, sales and support", () => {
    for (const role of ["TECHNICIAN", "WAREHOUSE", "SALES", "SUPPORT"] as const) {
      expect(redactProductCost(product, { id: "u", name: "u", role })).not.toHaveProperty("costPaise");
    }
  });

  it("keeps cost for director and admin", () => {
    expect(redactProductCost(product, { id: "u", name: "u", role: "DIRECTOR" })).toHaveProperty(
      "costPaise",
      100,
    );
    expect(redactProductCost(product, { id: "u", name: "u", role: "ADMIN" })).toHaveProperty(
      "costPaise",
      100,
    );
  });
});
