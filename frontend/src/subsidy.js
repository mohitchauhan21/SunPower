// PM Surya Ghar subsidy by state. The table comes from the back end
// (GET /api/sunpower/subsidy-states, built from the state-wise rates sheet);
// the same formula runs here for instant feedback.
import { useEffect, useState } from 'react';
import { get } from './api.js';
import { FALLBACK_TABLE } from './subsidyTable.js';

const RATES = { general: { per_kw: 30000, third_kw: 18000 }, special: { per_kw: 33000, third_kw: 19800 } };
// Average central subsidy across all 36 states/UTs (same as the server), used until the table loads.
export const AVERAGE = { 1: 31167, 2: 62333, 3: 81033 };
export const DEFAULT_STATE = ''; // no state assumed: the visitor picks theirs
const STORE = 'sp_state';

export const avgSubsidy = (kw) => AVERAGE[Math.min(Math.max(Math.round(kw), 0), 3)] || 0;

export function centralFor(kw, category = 'general', rates = RATES) {
  const r = rates[category] || rates.general;
  const k = Math.max(Math.min(kw || 0, 3), 0);
  return Math.round(r.per_kw * Math.min(k, 2) + r.third_kw * Math.max(k - 2, 0));
}

export function topupFor(kw, rule) {
  if (!rule || !kw) return 0;
  if (rule.per_kw) return Math.round(Math.min(rule.per_kw * kw, rule.max));
  const tiers = Object.entries(rule.tiers || {}).map(([s, a]) => [Number(s), a]).sort((a, b) => a[0] - b[0]);
  const hit = tiers.filter(([s]) => kw >= s);
  return hit.length ? hit[hit.length - 1][1] : 0;
}

export function subsidyFor(kw, stateName, includeTopup, table) {
  const s = table?.states.find((x) => x.name === stateName) || { name: '', category: 'general', topup: null };
  const central = centralFor(kw, s.category, table?.rates || RATES);
  const available = topupFor(kw, s.topup);
  const topup = includeTopup ? available : 0;
  return { state: s.name, category: s.category, central, topup, available, total: central + topup, note: s.note };
}

let cache = null;
let pending = null;

/** The state table: the built-in copy at once, replaced by the server's when it answers. */
export function useSubsidyTable() {
  const [table, setTable] = useState(cache || FALLBACK_TABLE);
  useEffect(() => {
    if (cache) return undefined;
    pending = pending || get('/api/sunpower/subsidy-states')
      .then((t) => { if (t?.states?.length) cache = t; return cache; })
      .catch(() => null);
    let alive = true;
    pending.then((t) => { if (alive && t) setTable(t); });
    return () => { alive = false; };
  }, []);
  return table;
}

export function savedState() {
  try { return localStorage.getItem(STORE) || DEFAULT_STATE; } catch { return DEFAULT_STATE; }
}
export function saveState(name) {
  try { localStorage.setItem(STORE, name); } catch { /* private mode: fine */ }
}
