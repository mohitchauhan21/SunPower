/**
 * Money helpers. All amounts are integer paise. ₹1 = 100 paise.
 * Never use floats for money: parse strings, round once, store integers.
 */

export type Paise = number;

/** Largest amount we store in a single Int column (₹2.1 crore). */
export const MAX_PAISE = 2_147_483_647;

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

const inrFormatterExact = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function assertPaise(value: number, label = "amount"): asserts value is Paise {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(`${label} must be a whole number of paise, got ${value}`);
  }
}

/** ₹1,50,000 — Indian digit grouping. Paise are shown only when non-zero. */
export function formatINR(paise: Paise, opts: { exact?: boolean } = {}): string {
  assertPaise(paise);
  const rupees = paise / 100;
  if (opts.exact) return inrFormatterExact.format(rupees);
  return inrFormatter.format(rupees);
}

/**
 * Parse a rupee amount typed by a person ("1,50,000", "₹ 2499.5", "1500.75") into paise.
 * Returns null when the input is not a valid non-negative amount with at most 2 decimals.
 */
export function parseRupeesToPaise(input: string | number): Paise | null {
  const raw = typeof input === "number" ? input.toString() : input;
  const cleaned = raw.replace(/[₹,\s]/g, "").replace(/^Rs\.?/i, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole, frac = ""] = cleaned.split(".");
  const paise = Number(whole) * 100 + Number(frac.padEnd(2, "0"));
  if (!Number.isSafeInteger(paise) || paise > MAX_PAISE) return null;
  return paise;
}

/** Round half away from zero, applied to integer maths only. */
function roundDiv(numerator: number, denominator: number): number {
  const q = numerator / denominator;
  return q >= 0 ? Math.floor(q + 0.5) : -Math.floor(-q + 0.5);
}

/** GST on an amount, rate in basis points (12% = 1200). Rounded to the nearest paisa. */
export function gstOn(amount: Paise, rateBps: number): Paise {
  assertPaise(amount);
  if (!Number.isInteger(rateBps) || rateBps < 0 || rateBps > 10_000) {
    throw new RangeError(`Invalid GST rate ${rateBps} bps`);
  }
  return roundDiv(amount * rateBps, 10_000);
}

/** Percentage of an amount in basis points, e.g. 30% advance = 3000 bps. */
export function percentOf(amount: Paise, bps: number): Paise {
  return roundDiv(amount * bps, 10_000);
}

export function sumPaise(values: readonly Paise[]): Paise {
  let total = 0;
  for (const v of values) {
    assertPaise(v);
    total += v;
  }
  assertPaise(total, "total");
  return total;
}

export interface LineInput {
  quantity: number;
  unitPricePaise: Paise;
  gstRateBps: number;
}

export interface LineTotals {
  netPaise: Paise;
  taxPaise: Paise;
  grossPaise: Paise;
}

/** Totals for one line: tax is computed per line so invoices reconcile line by line. */
export function lineTotals(line: LineInput): LineTotals {
  if (!Number.isInteger(line.quantity) || line.quantity < 0) {
    throw new RangeError(`Quantity must be a whole number, got ${line.quantity}`);
  }
  const netPaise = line.quantity * line.unitPricePaise;
  assertPaise(netPaise, "line amount");
  const taxPaise = gstOn(netPaise, line.gstRateBps);
  return { netPaise, taxPaise, grossPaise: netPaise + taxPaise };
}

export function documentTotals(lines: readonly LineInput[]): LineTotals {
  const each = lines.map(lineTotals);
  return {
    netPaise: sumPaise(each.map((l) => l.netPaise)),
    taxPaise: sumPaise(each.map((l) => l.taxPaise)),
    grossPaise: sumPaise(each.map((l) => l.grossPaise)),
  };
}
