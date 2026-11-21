import { describe, expect, it } from "vitest";
import {
  documentTotals,
  formatINR,
  gstOn,
  lineTotals,
  parseRupeesToPaise,
  percentOf,
  sumPaise,
} from "@/lib/money";

describe("formatINR", () => {
  it("uses Indian digit grouping", () => {
    expect(formatINR(150_000_00)).toBe("₹1,50,000");
    expect(formatINR(1_23_45_678_00)).toBe("₹1,23,45,678");
    expect(formatINR(999_00)).toBe("₹999");
  });

  it("shows paise only when present, or always in exact mode", () => {
    expect(formatINR(2499_50)).toBe("₹2,499.5");
    expect(formatINR(2499_50, { exact: true })).toBe("₹2,499.50");
    expect(formatINR(0, { exact: true })).toBe("₹0.00");
  });

  it("rejects non-integer paise", () => {
    expect(() => formatINR(10.5)).toThrow(RangeError);
  });
});

describe("parseRupeesToPaise", () => {
  it.each([
    ["1,50,000", 150_000_00],
    ["₹ 2,499.5", 2499_50],
    ["1500.75", 1500_75],
    ["0", 0],
    ["Rs. 100", 100_00],
    [42, 42_00],
  ])("parses %s", (input, expected) => {
    expect(parseRupeesToPaise(input)).toBe(expected);
  });

  it.each(["", "abc", "-100", "1.234", "1e5", "12.3.4"])("rejects %s", (input) => {
    expect(parseRupeesToPaise(input)).toBeNull();
  });

  it("never introduces floating-point error", () => {
    expect(parseRupeesToPaise("0.29")).toBe(29);
    expect(parseRupeesToPaise("1.15")).toBe(115);
  });

  it("rejects amounts above the Int column limit", () => {
    expect(parseRupeesToPaise("99999999")).toBeNull();
  });
});

describe("GST and totals", () => {
  it("computes GST in basis points with half-up rounding", () => {
    expect(gstOn(100_00, 1800)).toBe(18_00);
    expect(gstOn(16_500_00, 1200)).toBe(1_980_00);
    expect(gstOn(1, 1800)).toBe(0); // 0.18 paise rounds to 0
    expect(gstOn(3, 1800)).toBe(1); // 0.54 rounds to 1
  });

  it("rejects invalid rates", () => {
    expect(() => gstOn(100, -1)).toThrow();
    expect(() => gstOn(100, 10_001)).toThrow();
    expect(() => gstOn(100, 12.5)).toThrow();
  });

  it("computes line and document totals", () => {
    const panel = { quantity: 6, unitPricePaise: 16_500_00, gstRateBps: 1200 };
    const cable = { quantity: 50, unitPricePaise: 65_00, gstRateBps: 1800 };
    expect(lineTotals(panel)).toEqual({ netPaise: 99_000_00, taxPaise: 11_880_00, grossPaise: 1_10_880_00 });
    expect(documentTotals([panel, cable])).toEqual({
      netPaise: 99_000_00 + 3_250_00,
      taxPaise: 11_880_00 + 585_00,
      grossPaise: 99_000_00 + 3_250_00 + 11_880_00 + 585_00,
    });
  });

  it("rejects fractional quantities", () => {
    expect(() => lineTotals({ quantity: 1.5, unitPricePaise: 100, gstRateBps: 0 })).toThrow();
  });

  it("computes percentages (e.g. 30% advance)", () => {
    expect(percentOf(2_00_000_00, 3000)).toBe(60_000_00);
  });

  it("sums integers and rejects floats", () => {
    expect(sumPaise([1, 2, 3])).toBe(6);
    expect(() => sumPaise([1, 0.5])).toThrow();
  });
});
