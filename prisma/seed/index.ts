import { config } from "dotenv";
config({ quiet: true });
import { PrismaClient } from "@prisma/client";
import { seed } from "./seed";

async function main() {
  if (process.env.NODE_ENV === "production") {
    throw new Error("Refusing to seed demo data in production.");
  }
  const password = process.env.SEED_USER_PASSWORD;
  if (!password || password.length < 8) {
    throw new Error("Set SEED_USER_PASSWORD (at least 8 characters) in .env before seeding.");
  }
  const prisma = new PrismaClient();
  try {
    console.info("Seeding SunPower demo data…");
    await seed(prisma, { password, log: (m) => console.info(`  ✓ ${m}`) });
    console.info("Done.");
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
