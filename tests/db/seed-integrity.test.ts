import { describe, expect, it } from "vitest";
import { db } from "@/server/db";
import { ROLES } from "@/server/auth/permissions";
import {
  CAPACITIES_KW,
  PRODUCTS,
  SYSTEM_TYPES,
  packageBlueprint,
  packageCode,
} from "../../prisma/seed/catalog";
import { CUSTOMERS, OPENING_STOCK, USERS } from "../../prisma/seed/people";
import { seed } from "../../prisma/seed/seed";

async function counts() {
  const [users, products, templates, items, serials, movements, customers, leads] = await Promise.all([
    db.user.count(),
    db.product.count(),
    db.packageTemplate.count(),
    db.packageItem.count(),
    db.serialUnit.count(),
    db.stockMovement.count(),
    db.customer.count(),
    db.lead.count(),
  ]);
  return { users, products, templates, items, serials, movements, customers, leads };
}

describe("seed integrity", () => {
  it("creates at least one active user for every role, and 15 technicians", async () => {
    for (const role of ROLES) {
      expect(await db.user.count({ where: { role, active: true } }), role).toBeGreaterThan(0);
    }
    expect(await db.user.count({ where: { role: "TECHNICIAN" } })).toBe(15);
  });

  it("stores bcrypt hashes, never plain passwords", async () => {
    const users = await db.user.findMany({ select: { passwordHash: true } });
    for (const u of users) expect(u.passwordHash).toMatch(/^\$2[aby]\$\d{2}\$/);
  });

  it("gives every technician a pay rate", async () => {
    const techs = await db.user.findMany({ where: { role: "TECHNICIAN" } });
    for (const t of techs) expect(t.hourlyRatePaise).toBeGreaterThan(0);
  });

  it("loads the full catalogue and all 15 package templates", async () => {
    expect(await db.product.count()).toBe(PRODUCTS.length);
    expect(await db.packageTemplate.count()).toBe(15);
  });

  it("stores each template's bill of materials exactly as the blueprint says", async () => {
    for (const systemType of SYSTEM_TYPES) {
      for (const kw of CAPACITIES_KW) {
        const t = await db.packageTemplate.findUniqueOrThrow({
          where: { code: packageCode(systemType, kw) },
          include: { items: { include: { product: true }, orderBy: { sortOrder: "asc" } } },
        });
        expect(t.capacityWatts).toBe(kw * 1000);
        expect(t.items.map((i) => ({ sku: i.product.sku, quantity: i.quantity }))).toEqual(
          packageBlueprint(systemType, kw),
        );
      }
    }
  });

  it("keeps stock levels equal to the sum of stock movements", async () => {
    const levels = await db.stockLevel.findMany({ include: { product: true, location: true } });
    for (const level of levels) {
      const inbound = await db.stockMovement.aggregate({
        where: { productId: level.productId, toLocationId: level.locationId },
        _sum: { quantity: true },
      });
      const outbound = await db.stockMovement.aggregate({
        where: { productId: level.productId, fromLocationId: level.locationId },
        _sum: { quantity: true },
      });
      expect(level.quantity, level.product.sku).toBe(
        (inbound._sum.quantity ?? 0) - (outbound._sum.quantity ?? 0),
      );
    }
  });

  it("has one in-stock serial unit per unit of serialized stock", async () => {
    for (const [sku, qty] of Object.entries(OPENING_STOCK)) {
      const product = await db.product.findUniqueOrThrow({ where: { sku } });
      const serials = await db.serialUnit.count({ where: { productId: product.id, status: "IN_STOCK" } });
      expect(serials, sku).toBe(product.requiresSerial ? qty : 0);
    }
  });

  it("loads sample customers with normalised phone numbers and a few new leads", async () => {
    expect(await db.customer.count()).toBe(CUSTOMERS.length);
    const customers = await db.customer.findMany();
    for (const c of customers) expect(c.phone).toMatch(/^[6-9]\d{9}$/);
    expect(await db.lead.count({ where: { status: "NEW" } })).toBeGreaterThanOrEqual(4);
  });

  it("is idempotent: running it again changes nothing", async () => {
    const before = await counts();
    await seed(db, { password: process.env.SEED_USER_PASSWORD ?? "SunPower@123" });
    expect(await counts()).toEqual(before);
    expect(before.users).toBe(USERS.length);
  });
});
