import bcrypt from "bcryptjs";
import type { Prisma, PrismaClient } from "@prisma/client";
import { nextDocumentNumber } from "@/server/services/sequence.service";
import {
  CAPACITIES_KW,
  PRODUCTS,
  SYSTEM_TYPES,
  SYSTEM_TYPE_LABEL,
  packageBlueprint,
  packageCode,
} from "./catalog";
import { APP_SETTINGS, CUSTOMERS, OPENING_STOCK, STOCK_LOCATIONS, USERS } from "./people";

export interface SeedOptions {
  password: string;
  log?: (msg: string) => void;
}

export function serialFor(sku: string, index: number): string {
  return `${sku.replace(/-/g, "")}-${String(index).padStart(5, "0")}`;
}

/**
 * Idempotent seed: safe to run repeatedly. Reference data is upserted; opening stock and demo
 * leads are only created when absent.
 */
export async function seed(prisma: PrismaClient, opts: SeedOptions): Promise<void> {
  const log = opts.log ?? (() => {});

  // ── Settings
  for (const [key, value] of Object.entries(APP_SETTINGS)) {
    await prisma.appSetting.upsert({
      where: { key },
      create: { key, value: value as Prisma.InputJsonValue },
      update: { value: value as Prisma.InputJsonValue },
    });
  }

  // ── Users (bcrypt cost 10 keeps the seed fast; production sign-ups use 12)
  const passwordHash = await bcrypt.hash(opts.password, 10);
  for (const u of USERS) {
    await prisma.user.upsert({
      where: { email: u.email },
      create: { ...u, passwordHash },
      update: {
        name: u.name,
        role: u.role,
        phone: u.phone,
        hourlyRatePaise: u.hourlyRatePaise ?? null,
        passwordHash,
        active: true,
      },
    });
  }
  log(`users: ${USERS.length}`);

  // ── Products
  for (const p of PRODUCTS) {
    await prisma.product.upsert({ where: { sku: p.sku }, create: p, update: p });
  }
  const products = await prisma.product.findMany({
    select: { id: true, sku: true, requiresSerial: true, costPaise: true },
  });
  const bySku = new Map(products.map((p) => [p.sku, p]));
  log(`products: ${PRODUCTS.length}`);

  // ── Package templates (bill of materials)
  let templates = 0;
  for (const systemType of SYSTEM_TYPES) {
    for (const kw of CAPACITIES_KW) {
      const code = packageCode(systemType, kw);
      const template = await prisma.packageTemplate.upsert({
        where: { code },
        create: {
          code,
          name: `${kw} kW ${SYSTEM_TYPE_LABEL[systemType]}`,
          systemType,
          capacityWatts: kw * 1000,
        },
        update: {
          name: `${kw} kW ${SYSTEM_TYPE_LABEL[systemType]}`,
          systemType,
          capacityWatts: kw * 1000,
          active: true,
        },
      });
      const lines = packageBlueprint(systemType, kw);
      await prisma.packageItem.deleteMany({ where: { templateId: template.id } });
      await prisma.packageItem.createMany({
        data: lines.map((line, sortOrder) => {
          const product = bySku.get(line.sku);
          if (!product) throw new Error(`Blueprint references unknown SKU ${line.sku}`);
          return { templateId: template.id, productId: product.id, quantity: line.quantity, sortOrder };
        }),
      });
      templates++;
    }
  }
  log(`package templates: ${templates}`);

  // ── Stock locations
  for (const loc of STOCK_LOCATIONS) {
    await prisma.stockLocation.upsert({
      where: { code: loc.code },
      create: { ...loc },
      update: { name: loc.name, type: loc.type },
    });
  }
  const warehouse = await prisma.stockLocation.findUniqueOrThrow({ where: { code: "WH-MAIN" } });
  const supplier = await prisma.stockLocation.findUniqueOrThrow({ where: { code: "SUPPLIER" } });
  const admin = await prisma.user.findUniqueOrThrow({ where: { email: "admin@sunpower.test" } });

  // ── Opening stock (only once)
  if ((await prisma.stockMovement.count()) === 0) {
    await prisma.$transaction(
      async (tx) => {
        for (const [sku, qty] of Object.entries(OPENING_STOCK)) {
          const product = bySku.get(sku);
          if (!product) throw new Error(`Opening stock references unknown SKU ${sku}`);
          if (product.requiresSerial) {
            for (let i = 1; i <= qty; i++) {
              const unit = await tx.serialUnit.create({
                data: {
                  serial: serialFor(sku, i),
                  productId: product.id,
                  status: "IN_STOCK",
                  locationId: warehouse.id,
                },
              });
              await tx.stockMovement.create({
                data: {
                  type: "RECEIPT",
                  productId: product.id,
                  quantity: 1,
                  fromLocationId: supplier.id,
                  toLocationId: warehouse.id,
                  serialUnitId: unit.id,
                  unitCostPaise: product.costPaise,
                  note: "Opening stock",
                  createdById: admin.id,
                },
              });
            }
          } else {
            await tx.stockMovement.create({
              data: {
                type: "RECEIPT",
                productId: product.id,
                quantity: qty,
                fromLocationId: supplier.id,
                toLocationId: warehouse.id,
                unitCostPaise: product.costPaise,
                note: "Opening stock",
                createdById: admin.id,
              },
            });
          }
          await tx.stockLevel.upsert({
            where: { productId_locationId: { productId: product.id, locationId: warehouse.id } },
            create: { productId: product.id, locationId: warehouse.id, quantity: qty },
            update: { quantity: qty },
          });
        }
      },
      { timeout: 60_000 },
    );
    log("opening stock: created");
  }

  // ── Customers and a few fresh enquiries for the lead inbox
  const sales = await prisma.user.findUniqueOrThrow({ where: { email: "sales@sunpower.test" } });
  for (const [i, c] of CUSTOMERS.entries()) {
    const customer = await prisma.customer.upsert({
      where: { phone: c.phone },
      create: { ...c, state: "Maharashtra" },
      update: { name: c.name, addressLine: c.addressLine, city: c.city, pincode: c.pincode, type: c.type },
    });
    if (i < 4 && (await prisma.lead.count({ where: { customerId: customer.id } })) === 0) {
      await prisma.$transaction(async (tx) => {
        await tx.lead.create({
          data: {
            number: await nextDocumentNumber(tx, "lead"),
            customerId: customer.id,
            source: i % 2 === 0 ? "WEB_FORM" : "WHATSAPP",
            status: "NEW",
            systemType: i === 2 ? "ON_GRID" : i === 3 ? "OFF_GRID" : "ON_GRID",
            requestedWatts: [3000, 2000, 5000, 3000][i],
            wantsSubsidy: c.type === "RESIDENTIAL",
            needs:
              c.type === "RESIDENTIAL"
                ? "Wants a rooftop system under the PM Surya Ghar subsidy."
                : "Factory roof, daytime load.",
            assignedToId: i % 2 === 0 ? sales.id : null,
          },
        });
      });
    }
  }
  log(`customers: ${CUSTOMERS.length}`);
}
