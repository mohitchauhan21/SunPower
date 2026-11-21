/**
 * Date helpers. The business runs in India (Asia/Kolkata, UTC+05:30, no DST).
 * Calendar dates (warranty start/end, schedules) are stored as DATE columns, which
 * Prisma represents as a JS Date at 00:00 UTC on that calendar day.
 */

export const BUSINESS_TZ = "Asia/Kolkata";
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

/** A calendar date with no time, represented as a Date at 00:00 UTC (matches Postgres DATE). */
export type CalendarDate = Date;

export function calendarDate(year: number, month1: number, day: number): CalendarDate {
  return new Date(Date.UTC(year, month1 - 1, day));
}

/** The IST calendar day an instant falls on. 23:30 UTC on 1 Jan is 2 Jan in India. */
export function istCalendarDate(instant: Date): CalendarDate {
  const shifted = new Date(instant.getTime() + IST_OFFSET_MS);
  return calendarDate(shifted.getUTCFullYear(), shifted.getUTCMonth() + 1, shifted.getUTCDate());
}

function daysInMonth(year: number, month0: number): number {
  return new Date(Date.UTC(year, month0 + 1, 0)).getUTCDate();
}

/** Add calendar months, clamping to the month's last day (31 Jan + 1 month = 28/29 Feb). */
export function addMonths(date: CalendarDate, months: number): CalendarDate {
  if (!Number.isInteger(months)) throw new RangeError("months must be an integer");
  const total = date.getUTCMonth() + months;
  const year = date.getUTCFullYear() + Math.floor(total / 12);
  const month0 = ((total % 12) + 12) % 12;
  const day = Math.min(date.getUTCDate(), daysInMonth(year, month0));
  return new Date(Date.UTC(year, month0, day));
}

export function addDays(date: CalendarDate, days: number): CalendarDate {
  return new Date(date.getTime() + days * 86_400_000);
}

export interface WarrantyPeriod {
  start: CalendarDate;
  /** Inclusive last day of cover. */
  end: CalendarDate;
}

/**
 * Warranty cover from the IST delivery day for N months.
 * Rule: end = start + N months − 1 day (inclusive). 24 months from 15 Mar 2026 ends 14 Mar 2028.
 */
export function warrantyPeriod(deliveredAt: Date, warrantyMonths: number): WarrantyPeriod {
  if (!Number.isInteger(warrantyMonths) || warrantyMonths <= 0) {
    throw new RangeError(`warrantyMonths must be a positive integer, got ${warrantyMonths}`);
  }
  const start = istCalendarDate(deliveredAt);
  return { start, end: addDays(addMonths(start, warrantyMonths), -1) };
}

/** True when `on` (an instant, judged on its IST calendar day) is within the inclusive cover. */
export function isInWarranty(end: CalendarDate | null | undefined, on: Date = new Date()): boolean {
  if (!end) return false;
  return istCalendarDate(on).getTime() <= end.getTime();
}

/** Indian financial year label: April–March. 15 Jan 2026 → "25-26", 1 Apr 2026 → "26-27". */
export function financialYearLabel(instant: Date): string {
  const d = istCalendarDate(instant);
  const y = d.getUTCFullYear();
  const startYear = d.getUTCMonth() >= 3 ? y : y - 1;
  const two = (n: number) => String(n % 100).padStart(2, "0");
  return `${two(startYear)}-${two(startYear + 1)}`;
}

const dateFormatter = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** Format a calendar date, e.g. "14 Mar 2028". */
export function formatCalendarDate(date: CalendarDate): string {
  return dateFormatter.format(date);
}
