// Hands the savings-page figures to the quote form (same tab only).
const KEY = 'sp_quote_prefill';

export function saveQuotePrefill(data) {
  try { sessionStorage.setItem(KEY, JSON.stringify({ ...data, at: Date.now() })); } catch { /* storage off: form starts empty */ }
}

/** The saved figures if they are less than an hour old, else null. */
export function readQuotePrefill() {
  try {
    const d = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    return d && Date.now() - d.at < 3600 * 1000 ? d : null;
  } catch {
    return null;
  }
}

export function clearQuotePrefill() {
  try { sessionStorage.removeItem(KEY); } catch { /* ignore */ }
}

// A guest's filled-in booking form, kept while they sign up (same tab, one hour).
const DRAFT = 'sp_booking_draft';

export function saveBookingDraft(form) {
  try { sessionStorage.setItem(DRAFT, JSON.stringify({ form, at: Date.now() })); } catch { /* storage off */ }
}

export function readBookingDraft() {
  try {
    const d = JSON.parse(sessionStorage.getItem(DRAFT) || 'null');
    return d && Date.now() - d.at < 3600 * 1000 ? d.form : null;
  } catch {
    return null;
  }
}

export function clearBookingDraft() {
  try { sessionStorage.removeItem(DRAFT); } catch { /* ignore */ }
}

/** Indian mobile number as +91XXXXXXXXXX, or null (same rule as the server). */
export function normalizePhone(raw) {
  let d = String(raw || '').replace(/\D/g, '');
  if (d.length === 12 && d.startsWith('91')) d = d.slice(2);
  else if (d.length === 11 && d.startsWith('0')) d = d.slice(1);
  return d.length === 10 && /^[6-9]/.test(d) ? `+91${d}` : null;
}
