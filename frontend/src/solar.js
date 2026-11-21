// Same rules of thumb as the back end (backend/app/rules.py: estimate).
// Used for instant feedback while the authoritative figures load from /api/sunpower/estimate.
import { avgSubsidy, subsidyFor } from './subsidy.js';

export const RULES = { unitsPerKw: 120, tariff: 8, minKw: 1, maxKw: 5, costPerKw: 65000, roofPerKw: 100 };

/**
 * opts: { state, topup, table } for the state subsidy;
 *       custom mode: { kw, costPerKw, tariff } replace the defaults.
 */
export function estimateLocal(units = 0, bill = 0, opts = {}) {
  const tariff = opts.tariff || RULES.tariff;
  const u = units || (bill ? bill / tariff : 0);
  if (!u && !opts.kw) return null;
  const kw = opts.kw ? Math.round(Math.min(Math.max(opts.kw, 0.5), 100) * 10) / 10
    : Math.min(Math.max(Math.round(u / RULES.unitsPerKw), RULES.minKw), RULES.maxKw);
  const costPerKw = opts.costPerKw || RULES.costPerKw;
  const generation = kw * RULES.unitsPerKw;
  const monthly = (u ? Math.min(generation, u) : generation) * tariff;
  const cost = kw * costPerKw;
  const sub = subsidyFor(kw, opts.state, opts.topup, opts.table);
  const net = Math.max(cost - sub.total, 0);
  return {
    units: Math.round(u),
    kw,
    system_type: 'on_grid',
    generation: Math.round(generation),
    monthly_saving: Math.round(monthly),
    yearly_saving: Math.round(monthly * 12),
    cost: Math.round(cost),
    subsidy: sub.total,
    subsidy_central: sub.central,
    subsidy_topup: sub.topup,
    topup_available: sub.available,
    state: sub.state,
    category: sub.category,
    net_cost: Math.round(net),
    cost_per_kw: costPerKw,
    tariff,
    payback_years: monthly ? Math.round((net / (monthly * 12)) * 10) / 10 : 0,
    roof_sqft: Math.round(kw * RULES.roofPerKw)
  };
}

/** Home page packages: price and the subsidy averaged across all states/UTs. */
export const packagesWith = (average) => [
  { kw: 1, units: 'Up to 150 units', desc: 'Lights, fans, TV and a fridge in a small flat.' },
  { kw: 2, units: '150–270 units', desc: 'A 1–2 BHK home with everyday appliances.' },
  { kw: 3, units: '270–390 units', desc: 'A 2–3 BHK home running one air conditioner.' },
  { kw: 5, units: '390+ units', desc: 'A bungalow or villa with two or more ACs.' }
].map((p) => {
  const subsidy = (average && average[String(p.kw)]) || avgSubsidy(p.kw);
  const cost = p.kw * RULES.costPerKw;
  return { ...p, cost, subsidy, net: cost - subsidy };
});

export const PACKAGES = packagesWith(null);
