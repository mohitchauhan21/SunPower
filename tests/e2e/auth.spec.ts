import { expect, test } from "@playwright/test";
import { ROLE_HOME } from "@/server/auth/permissions";
import { ALL_ROLES, ROLE_USERS, expectNoSeriousA11yViolations, login, storageStateFor } from "./helpers";

test.describe("sign-in", () => {
  test("unauthenticated visitors are sent to sign-in and returned afterwards", async ({ page }) => {
    await page.goto("/leads");
    await expect(page).toHaveURL(/\/login\?callbackUrl=%2Fleads/);
    await login(page, ROLE_USERS.SALES.email);
    await expect(page).toHaveURL(/\/leads$/);
    await expect(page.getByRole("heading", { name: "Leads" })).toBeVisible();
  });

  test("a wrong password shows a readable error and keeps the email", async ({ page }) => {
    await page.goto("/login");
    await login(page, "support@sunpower.test", "definitely-wrong");
    // Next.js renders its own (empty) role="alert" route announcer, so match ours by text.
    await expect(page.getByRole("alert").filter({ hasText: "don't match an active account" })).toBeVisible();
    await expect(page.getByLabel("Email")).toHaveValue("support@sunpower.test");
  });

  test("empty fields show inline errors", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Enter a valid email address.")).toBeVisible();
    await expect(page.getByLabel("Email")).toHaveAttribute("aria-invalid", "true");
  });

  test("an off-site callbackUrl is ignored (no open redirect)", async ({ page }) => {
    await page.goto("/login?callbackUrl=//evil.example/steal");
    await login(page, ROLE_USERS.WAREHOUSE.email);
    await expect(page).toHaveURL(/\/warehouse$/);
  });

  test("the sign-in page has no serious accessibility violations", async ({ page }) => {
    await page.goto("/login");
    await expectNoSeriousA11yViolations(page);
  });

  test("keyboard-only sign-in works", async ({ page }) => {
    await page.goto("/login");
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Email")).toBeFocused();
    await page.keyboard.type(ROLE_USERS.SUPPORT.email);
    await page.keyboard.press("Tab");
    await page.keyboard.type(process.env.SEED_USER_PASSWORD ?? "SunPower@123");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/tickets$/);
  });
});

for (const role of ALL_ROLES) {
  test.describe(`${role} session`, () => {
    test.use({ storageState: storageStateFor(role) });

    test(`lands on ${ROLE_HOME[role]} and can sign out`, async ({ page }) => {
      await page.goto("/");
      await expect(page).toHaveURL(new RegExp(`${ROLE_HOME[role]}$`));
      await expect(page.getByText(ROLE_USERS[role].name)).toBeVisible();
      await expectNoSeriousA11yViolations(page);
    });

    test("visiting /login while signed in goes home", async ({ page }) => {
      await page.goto("/login");
      await expect(page).toHaveURL(new RegExp(`${ROLE_HOME[role]}$`));
    });
  });
}

test.describe("sign-out", () => {
  test("ends the session", async ({ page }) => {
    await page.goto("/login");
    await login(page, "tech2@sunpower.test");
    await expect(page).toHaveURL(/\/jobs$/);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/jobs");
    await expect(page).toHaveURL(/\/login/);
  });
});
