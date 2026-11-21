import type { Product } from "@prisma/client";
import { db, type DbClient } from "@/server/db";
import { requirePermission, type Actor } from "@/server/auth/actor";
import { hasPermission } from "@/server/auth/permissions";

/** What every role may see about a product. */
export type PublicProduct = Omit<Product, "costPaise">;
/** Product with cost, for roles allowed to see costs and margins. */
export type CostedProduct = Product;

/**
 * Field-level protection: costs are removed on the server for roles without catalog:cost:read
 * (technicians, warehouse, sales, support). The UI never receives the number.
 */
export function redactProductCost(product: Product, actor: Actor): PublicProduct | CostedProduct {
  if (hasPermission(actor.role, "catalog:cost:read")) return product;
  const { costPaise: _cost, ...rest } = product;
  return rest;
}

export async function listProducts(
  actor: Actor,
  client: DbClient = db,
): Promise<(PublicProduct | CostedProduct)[]> {
  requirePermission(actor, "catalog:read");
  const products = await client.product.findMany({
    where: { active: true },
    orderBy: [{ category: "asc" }, { name: "asc" }],
  });
  return products.map((p) => redactProductCost(p, actor));
}

export async function listPackageTemplates(actor: Actor, client: DbClient = db) {
  requirePermission(actor, "catalog:read");
  const templates = await client.packageTemplate.findMany({
    where: { active: true },
    orderBy: [{ systemType: "asc" }, { capacityWatts: "asc" }],
    include: { items: { orderBy: { sortOrder: "asc" }, include: { product: true } } },
  });
  return templates.map((t) => ({
    ...t,
    items: t.items.map((i) => ({ ...i, product: redactProductCost(i.product, actor) })),
  }));
}
