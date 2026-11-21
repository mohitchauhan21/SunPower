import type { Role } from "@prisma/client";
import { describe, expect, it } from "vitest";
import { requirePermission, SYSTEM_ACTOR } from "@/server/auth/actor";
import {
  canAccessPath,
  canSeeFinancials,
  hasPermission,
  isPublicPath,
  PERMISSIONS,
  ROLE_HOME,
  ROLES,
  type Permission,
} from "@/server/auth/permissions";
import { ForbiddenError, UnauthenticatedError } from "@/server/errors";
import { safeCallbackUrl } from "@/lib/validation/auth";

const FINANCIAL: Permission[] = [
  "finance:read",
  "catalog:cost:read",
  "report:read",
  "report:share",
  "timesheet:approve",
  "expense:approve",
  "invoice:write",
];

describe("permission matrix", () => {
  it("technicians never see margins, costs or other technicians' pay", () => {
    for (const p of FINANCIAL) expect(hasPermission("TECHNICIAN", p)).toBe(false);
    expect(canSeeFinancials("TECHNICIAN")).toBe(false);
    expect(hasPermission("TECHNICIAN", "job:read:all")).toBe(false);
    expect(hasPermission("TECHNICIAN", "ticket:read:all")).toBe(false);
  });

  it("only director and admin see financials", () => {
    const allowed = ROLES.filter((r) => canSeeFinancials(r));
    expect(allowed.sort()).toEqual(["ADMIN", "DIRECTOR"]);
  });

  it("admin has every permission; director has all except user and settings management", () => {
    for (const p of PERMISSIONS) expect(hasPermission("ADMIN", p)).toBe(true);
    expect(hasPermission("DIRECTOR", "user:manage")).toBe(false);
    expect(hasPermission("DIRECTOR", "settings:write")).toBe(false);
    expect(hasPermission("DIRECTOR", "report:share")).toBe(true);
  });

  it.each<[Role, Permission, boolean]>([
    ["SALES", "lead:write", true],
    ["SALES", "survey:approve", true],
    ["SALES", "dispatch:confirm", false],
    ["SALES", "catalog:cost:read", false],
    ["WAREHOUSE", "serial:scan", true],
    ["WAREHOUSE", "dispatch:confirm", true],
    ["WAREHOUSE", "lead:read", false],
    ["WAREHOUSE", "payment:record", false],
    ["TECHNICIAN", "job:complete", true],
    ["TECHNICIAN", "survey:perform", true],
    ["TECHNICIAN", "survey:approve", false],
    ["TECHNICIAN", "payment:record", false],
    ["SUPPORT", "ticket:assign", true],
    ["SUPPORT", "ticket:close", true],
    ["SUPPORT", "quote:write", false],
    ["SUPPORT", "finance:read", false],
  ])("%s → %s = %s", (role, permission, expected) => {
    expect(hasPermission(role, permission)).toBe(expected);
  });

  it("denies everything when there is no role", () => {
    expect(hasPermission(null, "lead:read")).toBe(false);
    expect(hasPermission(undefined, "catalog:read")).toBe(false);
  });
});

describe("requirePermission", () => {
  it("throws Unauthenticated without an actor and Forbidden without the permission", () => {
    expect(() => requirePermission(null, "lead:read")).toThrow(UnauthenticatedError);
    expect(() => requirePermission({ id: "u", name: "T", role: "TECHNICIAN" }, "finance:read")).toThrow(
      ForbiddenError,
    );
    expect(requirePermission({ id: "u", name: "S", role: "SALES" }, "lead:read").id).toBe("u");
  });

  it("lets the system actor run automations", () => {
    expect(() => requirePermission(SYSTEM_ACTOR, "delivery:confirm")).not.toThrow();
  });
});

describe("route access", () => {
  const cases: Record<string, Role[]> = {
    "/dashboard": ["ADMIN", "DIRECTOR"],
    "/finance/invoices": ["ADMIN", "DIRECTOR"],
    "/reports": ["ADMIN", "DIRECTOR"],
    "/admin/audit": ["ADMIN"],
    "/leads/kanban": ["ADMIN", "DIRECTOR", "SALES"],
    "/warehouse/pick/PK-00001": ["ADMIN", "DIRECTOR", "WAREHOUSE"],
    "/jobs/JB-1": ["ADMIN", "DIRECTOR", "SALES", "TECHNICIAN"],
    "/tickets": ["ADMIN", "DIRECTOR", "SUPPORT", "TECHNICIAN"],
  };

  for (const [path, allowed] of Object.entries(cases)) {
    it(`${path} is open to ${allowed.join(", ")} only`, () => {
      for (const role of ROLES) expect(canAccessPath(role, path)).toBe(allowed.includes(role));
    });
  }

  it("matches whole path segments, not string prefixes", () => {
    expect(canAccessPath("SALES", "/leadsomething")).toBe(false);
    expect(canAccessPath("SALES", "/dashboards")).toBe(false);
  });

  it("denies unknown paths to every role (deny by default)", () => {
    for (const role of ROLES) expect(canAccessPath(role, "/secret-area")).toBe(false);
  });

  it("leaves public pages open", () => {
    for (const p of ["/", "/login", "/enquiry", "/share/abc", "/api/auth/session", "/api/health"]) {
      expect(isPublicPath(p)).toBe(true);
      expect(canAccessPath(null, p)).toBe(true);
    }
    expect(isPublicPath("/api/catalog/products")).toBe(false);
  });

  it("sends every role to a home page it can open", () => {
    for (const role of ROLES) expect(canAccessPath(role, ROLE_HOME[role])).toBe(true);
  });
});

describe("safeCallbackUrl (no open redirects)", () => {
  it.each([
    ["/leads", "/leads"],
    ["/jobs?date=today", "/jobs?date=today"],
    ["//evil.example", null],
    ["/\\evil.example", null],
    ["https://evil.example", null],
    ["/login", null],
    ["/api/me", null],
    [undefined, null],
  ])("%s → %s", (input, expected) => {
    expect(safeCallbackUrl(input)).toBe(expected);
  });
});
