/**
 * Indian mobile numbers are stored as 10 digits so "+91 98765 43210", "098765-43210"
 * and "9876543210" all match the same customer.
 */
export function normalizeIndianMobile(input: string): string | null {
  let digits = input.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  if (!/^[6-9]\d{9}$/.test(digits)) return null;
  return digits;
}

/** 98765 43210 */
export function formatIndianMobile(tenDigits: string): string {
  return tenDigits.length === 10 ? `${tenDigits.slice(0, 5)} ${tenDigits.slice(5)}` : tenDigits;
}
