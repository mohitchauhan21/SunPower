import type { Role } from "@prisma/client";

/**
 * Single source of truth for who can do what. Enforced on the server (services, route handlers,
 * middleware). The UI may read it to hide controls, but hiding is never the protection.
 *
 * This file is imported by middleware, so it must stay edge-safe (no Node or Prisma runtime imports).
 */

export const ROLES = [
  "ADMIN",
  "DIRECTOR",
  "SALES",
  "WAREHOUSE",
  "TECHNICIAN",
  "SUPPORT",
] as const satisfies readonly Role[];

export const PERMISSIONS = [
  // Sales
  "lead:read",
  "lead:write",
  "survey:read",
  "survey:schedule",
  "survey:perform",
  "survey:approve",
  "quote:read",
  "quote:write",
  "payment:record",
  // Orders & warehouse
  "order:read",
  "order:cancel",
  "order:handover",
  "picklist:read",
  "picklist:work",
  "stock:read",
  "stock:adjust",
  "serial:read",
  "serial:scan",
  "dispatch:confirm",
  "delivery:confirm",
  // Field
  "job:read:own",
  "job:read:all",
  "job:schedule",
  "job:complete",
  "timesheet:write:own",
  "expense:write:own",
  // After-sales
  "customer:read",
  "customer:write",
  "ticket:read:own",
  "ticket:read:all",
  "ticket:write",
  "ticket:assign",
  "ticket:work",
  "ticket:close",
  // Finance & reporting — margins, costs and pay live here.
  "finance:read",
  "invoice:read",
  "invoice:write",
  "timesheet:approve",
  "expense:approve",
  "subsidy:read",
  "subsidy:write",
  "report:read",
  "report:share",
  // Catalogue
  "catalog:read",
  "catalog:write",
  "catalog:cost:read",
  // Platform
  "audit:read",
  "user:manage",
  "settings:write",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

const SALES: Permission[] = [
  "lead:read",
  "lead:write",
  "survey:read",
  "survey:schedule",
  "survey:approve",
  "quote:read",
  "quote:write",
  "payment:record",
  "order:read",
  "order:cancel",
  "order:handover",
  "customer:read",
  "customer:write",
  "catalog:read",
  "subsidy:read",
  "subsidy:write",
  "job:read:all",
  "job:schedule",
];

const WAREHOUSE: Permission[] = [
  "order:read",
  "picklist:read",
  "picklist:work",
  "stock:read",
  "stock:adjust",
  "serial:read",
  "serial:scan",
  "dispatch:confirm",
  "delivery:confirm",
  "catalog:read",
  "customer:read",
];

/** Technicians: their own jobs, tickets and time only. No costs, margins or other people's pay. */
const TECHNICIAN: Permission[] = [
  "survey:read",
  "survey:perform",
  "job:read:own",
  "job:complete",
  "ticket:read:own",
  "ticket:work",
  "serial:read",
  "serial:scan",
  "delivery:confirm",
  "timesheet:write:own",
  "expense:write:own",
  "catalog:read",
];

const SUPPORT: Permission[] = [
  "customer:read",
  "customer:write",
  "serial:read",
  "order:read",
  "ticket:read:all",
  "ticket:write",
  "ticket:assign",
  "ticket:work",
  "ticket:close",
  "invoice:read",
  "catalog:read",
  "job:read:all",
];

const DIRECTOR: Permission[] = PERMISSIONS.filter((p) => !["user:manage", "settings:write"].includes(p));

export const ROLE_PERMISSIONS: Readonly<Record<Role, ReadonlySet<Permission>>> = Object.freeze({
  ADMIN: new Set<Permission>(PERMISSIONS),
  DIRECTOR: new Set<Permission>(DIRECTOR),
  SALES: new Set<Permission>(SALES),
  WAREHOUSE: new Set<Permission>(WAREHOUSE),
  TECHNICIAN: new Set<Permission>(TECHNICIAN),
  SUPPORT: new Set<Permission>(SUPPORT),
});

export function hasPermission(role: Role | null | undefined, permission: Permission): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.has(permission) ?? false;
}

/** Costs, margins, profit and pay. Technicians must never see these. */
export function canSeeFinancials(role: Role | null | undefined): boolean {
  return hasPermission(role, "finance:read");
}

// ───────────────────────────── Routes ─────────────────────────────

/** Where each role lands after sign-in. */
export const ROLE_HOME: Readonly<Record<Role, string>> = {
  ADMIN: "/dashboard",
  DIRECTOR: "/dashboard",
  SALES: "/leads",
  WAREHOUSE: "/warehouse",
  TECHNICIAN: "/jobs",
  SUPPORT: "/tickets",
};

/**
 * Page access by path prefix. The first matching prefix wins; unknown app paths are denied.
 * API routes check fine-grained permissions inside their handlers.
 */
export const ROUTE_ACCESS: ReadonlyArray<{ prefix: string; roles: readonly Role[] }> = [
  { prefix: "/dashboard", roles: ["ADMIN", "DIRECTOR"] },
  { prefix: "/reports", roles: ["ADMIN", "DIRECTOR"] },
  { prefix: "/finance", roles: ["ADMIN", "DIRECTOR"] },
  { prefix: "/admin", roles: ["ADMIN"] },
  { prefix: "/leads", roles: ["ADMIN", "DIRECTOR", "SALES"] },
  { prefix: "/quotes", roles: ["ADMIN", "DIRECTOR", "SALES"] },
  { prefix: "/surveys", roles: ["ADMIN", "DIRECTOR", "SALES", "TECHNICIAN"] },
  { prefix: "/orders", roles: ["ADMIN", "DIRECTOR", "SALES", "WAREHOUSE", "SUPPORT"] },
  { prefix: "/customers", roles: ["ADMIN", "DIRECTOR", "SALES", "SUPPORT"] },
  { prefix: "/warehouse", roles: ["ADMIN", "DIRECTOR", "WAREHOUSE"] },
  { prefix: "/jobs", roles: ["ADMIN", "DIRECTOR", "TECHNICIAN", "SALES"] },
  { prefix: "/tickets", roles: ["ADMIN", "DIRECTOR", "SUPPORT", "TECHNICIAN"] },
  { prefix: "/account", roles: ["ADMIN", "DIRECTOR", "SALES", "WAREHOUSE", "TECHNICIAN", "SUPPORT"] },
];

/** Paths anyone can open without signing in. */
export const PUBLIC_PATHS = ["/login", "/enquiry", "/share", "/api/auth", "/api/enquiry", "/api/health"];

export function isPublicPath(pathname: string): boolean {
  return pathname === "/" || PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

function matchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function canAccessPath(role: Role | null | undefined, pathname: string): boolean {
  if (isPublicPath(pathname)) return true;
  if (!role) return false;
  const rule = ROUTE_ACCESS.find((r) => matchesPrefix(pathname, r.prefix));
  return rule ? rule.roles.includes(role) : false;
}
