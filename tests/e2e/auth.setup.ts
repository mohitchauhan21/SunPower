import { expect, test as setup } from "@playwright/test";
import { ALL_ROLES, ROLE_USERS, login, storageStateFor } from "./helpers";

/** Sign in once per role and save the session, so permission tests don't hit the login rate limit. */
for (const role of ALL_ROLES) {
  setup(`sign in as ${role}`, async ({ page }) => {
    await page.goto("/login");
    await login(page, ROLE_USERS[role].email);
    await expect(page.getByText(ROLE_USERS[role].name)).toBeVisible();
    await page.context().storageState({ path: storageStateFor(role) });
  });
}
