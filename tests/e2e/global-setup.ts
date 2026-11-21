import dbGlobalSetup from "../db/global-setup";

/** Fresh, migrated and seeded test database for every E2E run. */
export default function globalSetup(): void {
  dbGlobalSetup();
}
