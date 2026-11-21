import { expect, test } from "@playwright/test";
import { expectNoHorizontalOverflow, expectNoSeriousA11yViolations, storageStateFor } from "./helpers";

/** Runs in the desktop (1280), tablet (768) and phone (375) projects. */
test.describe("responsive", () => {
  test("sign-in page fits the screen with large tap targets", async ({ page }) => {
    await page.goto("/login");
    await expectNoHorizontalOverflow(page);
    const button = await page.getByRole("button", { name: "Sign in" }).boundingBox();
    const email = await page.getByLabel("Email").boundingBox();
    expect(button?.height).toBeGreaterThanOrEqual(44);
    expect(email?.height).toBeGreaterThanOrEqual(44);
    await expectNoSeriousA11yViolations(page);
  });

  test.describe("technician home", () => {
    test.use({ storageState: storageStateFor("TECHNICIAN") });
    test("fits the screen", async ({ page }) => {
      await page.goto("/jobs");
      await expect(page.getByRole("heading", { name: "My jobs" })).toBeVisible();
      await expectNoHorizontalOverflow(page);
      const signOut = await page.getByRole("button", { name: "Sign out" }).boundingBox();
      expect(signOut?.height).toBeGreaterThanOrEqual(44);
    });
  });
});
