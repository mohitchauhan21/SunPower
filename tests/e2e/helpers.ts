import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";
import type { Role } from "@prisma/client";

export const PASSWORD = process.env.SEED_USER_PASSWORD ?? "SunPower@123";

export const ROLE_USERS: Record<Role, { email: string; name: string }> = {
  ADMIN: { email: "admin@sunpower.test", name: "Asha Admin" },
  DIRECTOR: { email: "director@sunpower.test", name: "Devendra Rao" },
  SALES: { email: "sales@sunpower.test", name: "Sneha Joshi" },
  WAREHOUSE: { email: "warehouse@sunpower.test", name: "Wasim Shaikh" },
  TECHNICIAN: { email: "tech@sunpower.test", name: "Ravi Patil" },
  SUPPORT: { email: "support@sunpower.test", name: "Pooja Nair" },
};

export const ALL_ROLES = Object.keys(ROLE_USERS) as Role[];

export const storageStateFor = (role: Role) => `tests/e2e/.auth/${role.toLowerCase()}.json`;

export async function login(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

/** Zero serious or critical axe violations (WCAG 2.1 AA). */
export async function expectNoSeriousA11yViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    serious.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`),
  ).toEqual([]);
}

/** No horizontal scrolling at the current viewport. */
export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}
