import type { DbClient } from "@/server/db";
import { financialYearLabel } from "@/lib/dates";

/**
 * Atomically take the next number in a named series. Uses INSERT … ON CONFLICT so two people
 * creating a lead at the same moment can never get the same number. Run inside the transaction
 * that creates the document, so a rolled-back document doesn't burn a number.
 */
export async function nextSequenceValue(client: DbClient, key: string): Promise<number> {
  const rows = await client.$queryRaw<{ value: number }[]>`
    INSERT INTO "DocumentSequence" ("key", "value") VALUES (${key}, 1)
    ON CONFLICT ("key") DO UPDATE SET "value" = "DocumentSequence"."value" + 1
    RETURNING "value"`;
  const value = rows[0]?.value;
  if (typeof value !== "number") throw new Error(`Sequence ${key} returned no value`);
  return value;
}

export type DocumentKind = "lead" | "quote" | "order" | "picklist" | "job" | "ticket" | "invoice";

const PREFIX: Record<DocumentKind, string> = {
  lead: "LD",
  quote: "QT",
  order: "SO",
  picklist: "PK",
  job: "JB",
  ticket: "TK",
  invoice: "SP",
};

/**
 * Human-readable document numbers.
 *  - Most documents: LD-00042
 *  - Invoices: one gap-free series per Indian financial year, SP/25-26/0001 (GST requirement).
 */
export async function nextDocumentNumber(
  client: DbClient,
  kind: DocumentKind,
  now = new Date(),
): Promise<string> {
  if (kind === "invoice") {
    const fy = financialYearLabel(now);
    const n = await nextSequenceValue(client, `invoice:${fy}`);
    return `${PREFIX.invoice}/${fy}/${String(n).padStart(4, "0")}`;
  }
  const n = await nextSequenceValue(client, kind);
  return `${PREFIX[kind]}-${String(n).padStart(5, "0")}`;
}
