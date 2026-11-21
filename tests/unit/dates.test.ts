import { describe, expect, it } from "vitest";
import {
  addMonths,
  calendarDate,
  financialYearLabel,
  formatCalendarDate,
  isInWarranty,
  istCalendarDate,
  warrantyPeriod,
} from "@/lib/dates";

describe("istCalendarDate", () => {
  it("uses the Indian calendar day, not UTC", () => {
    // 20:00 UTC on 31 Mar = 01:30 IST on 1 Apr
    expect(istCalendarDate(new Date("2026-03-31T20:00:00Z"))).toEqual(calendarDate(2026, 4, 1));
    expect(istCalendarDate(new Date("2026-03-31T18:00:00Z"))).toEqual(calendarDate(2026, 3, 31));
  });
});

describe("addMonths", () => {
  it("clamps to the end of shorter months", () => {
    expect(addMonths(calendarDate(2026, 1, 31), 1)).toEqual(calendarDate(2026, 2, 28));
    expect(addMonths(calendarDate(2028, 1, 31), 1)).toEqual(calendarDate(2028, 2, 29));
  });
  it("handles year rollover and negatives", () => {
    expect(addMonths(calendarDate(2026, 11, 15), 3)).toEqual(calendarDate(2027, 2, 15));
    expect(addMonths(calendarDate(2026, 2, 15), -3)).toEqual(calendarDate(2025, 11, 15));
  });
});

describe("warrantyPeriod", () => {
  it("2-year inverter: ends the day before the anniversary", () => {
    const p = warrantyPeriod(new Date("2026-03-15T06:30:00Z"), 24);
    expect(p.start).toEqual(calendarDate(2026, 3, 15));
    expect(p.end).toEqual(calendarDate(2028, 3, 14));
  });

  it("20-year panel", () => {
    const p = warrantyPeriod(new Date("2026-03-15T06:30:00Z"), 240);
    expect(p.end).toEqual(calendarDate(2046, 3, 14));
  });

  it("starts on the IST day of delivery even late at night", () => {
    // 23:00 IST on 10 Jun = 17:30 UTC on 10 Jun → still 10 Jun
    expect(warrantyPeriod(new Date("2026-06-10T17:30:00Z"), 24).start).toEqual(calendarDate(2026, 6, 10));
    // 00:30 IST on 11 Jun = 19:00 UTC on 10 Jun → 11 Jun
    expect(warrantyPeriod(new Date("2026-06-10T19:00:00Z"), 24).start).toEqual(calendarDate(2026, 6, 11));
  });

  it("handles leap-day deliveries", () => {
    const p = warrantyPeriod(new Date("2028-02-29T06:00:00Z"), 24);
    expect(p.end).toEqual(calendarDate(2030, 2, 27)); // 28 Feb 2030 − 1 day
  });

  it("rejects zero or fractional months", () => {
    expect(() => warrantyPeriod(new Date(), 0)).toThrow();
    expect(() => warrantyPeriod(new Date(), 1.5)).toThrow();
  });
});

describe("isInWarranty", () => {
  const end = calendarDate(2028, 3, 14);
  it("is inclusive of the last day (IST)", () => {
    expect(isInWarranty(end, new Date("2028-03-14T18:00:00Z"))).toBe(true); // 23:30 IST on 14 Mar
    expect(isInWarranty(end, new Date("2028-03-14T18:31:00Z"))).toBe(false); // 00:01 IST on 15 Mar
  });
  it("is false with no end date", () => {
    expect(isInWarranty(null)).toBe(false);
  });
  it("matches the rainy-season scene: 18 months after delivery is in warranty", () => {
    const p = warrantyPeriod(new Date("2026-03-15T06:30:00Z"), 24);
    expect(isInWarranty(p.end, new Date("2027-09-15T06:30:00Z"))).toBe(true);
  });
});

describe("financialYearLabel", () => {
  it("runs April to March", () => {
    expect(financialYearLabel(new Date("2026-01-15T06:00:00Z"))).toBe("25-26");
    expect(financialYearLabel(new Date("2026-03-31T18:00:00Z"))).toBe("25-26"); // 23:30 IST 31 Mar
    expect(financialYearLabel(new Date("2026-03-31T19:00:00Z"))).toBe("26-27"); // 00:30 IST 1 Apr
    expect(financialYearLabel(new Date("2099-12-01T00:00:00Z"))).toBe("99-00");
  });
});

describe("formatCalendarDate", () => {
  it("formats in Indian style", () => {
    expect(formatCalendarDate(calendarDate(2028, 3, 14))).toBe("14 Mar 2028");
  });
});
