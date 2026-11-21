import { expect, test } from "@playwright/test";
import type { Role } from "@prisma/client";
import { canAccessPath } from "@/server/auth/permissions";
import { ALL_ROLES, expectNoSeriousA11yViolations, storageStateFor } from "./helpers";

const AREAS = ["/dashboard", "/finance", "/reports", "/admin", "/leads", "/warehouse", "/jobs", "/tickets"];

/** Every role × every area: allowed pages render; others return HTTP 403 with a friendly page. */
for (const role of ALL_ROLES) {
  test.describe(`${role} page access`, () => {
    test.use({ storageState: storageStateFor(role) });

    for (const path of AREAS) {
      const allowed = canAccessPath(role, path);
      test(`${allowed ? "can" : "cannot"} open ${path}`, async ({ page }) => {
        const res = await page.goto(path);
        if (allowed) {
          expect(res?.status()).toBe(200);
          await expect(page.getByText("You don't have access to this page")).toHaveCount(0);
        } else {
          expect(res?.status()).toBe(403);
          await expect(
            page.getByRole("heading", { name: "You don't have access to this page" }),
          ).toBeVisible();
        }
      });
    }
  });
}

test.describe("forbidden page", () => {
  test.use({ storageState: storageStateFor("TECHNICIAN") });
  test("is accessible", async ({ page }) => {
    await page.goto("/finance");
    await expectNoSeriousA11yViolations(page);
  });
});

test.describe("API permissions", () => {
  test("unauthenticated API calls get 401 JSON", async ({ request }) => {
    const res = await request.get("/api/catalog/products");
    expect(res.status()).toBe(401);
    expect((await res.json()).error.code).toBe("UNAUTHENTICATED");
  });

  const costCases: [Role, boolean][] = ALL_ROLES.map((r) => [r, r === "ADMIN" || r === "DIRECTOR"]);
  for (const [role, seesCost] of costCases) {
    test.describe(`${role} catalogue API`, () => {
      test.use({ storageState: storageStateFor(role) });
      test(`${seesCost ? "includes" : "never includes"} product costs`, async ({ request }) => {
        const res = await request.get("/api/catalog/products");
        expect(res.status()).toBe(200);
        const { data } = (await res.json()) as { data: Record<string, unknown>[] };
        expect(data.length).toBeGreaterThan(0);
        for (const p of data) expect("costPaise" in p).toBe(seesCost);
      });
    });
  }

  test.describe("current user", () => {
    test.use({ storageState: storageStateFor("TECHNICIAN") });
    test("/api/me lists only the technician's permissions", async ({ request }) => {
      const res = await request.get("/api/me");
      const { data } = await res.json();
      expect(data.role).toBe("TECHNICIAN");
      expect(data.permissions).toContain("job:complete");
      expect(data.permissions).not.toContain("finance:read");
      expect(data).not.toHaveProperty("hourlyRatePaise");
    });
  });
});
