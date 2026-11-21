// Same rules of thumb as the engine (sunpower_website/controllers/main.py).
// Used for instant feedback while the authoritative figures load from /api/sunpower/estimate.
export const RULES = { unitsPerKw: 120, tariff: 8, minKw: 1, maxKw: 5, costPerKw: 65000, roofPerKw: 100 };

export const subsidyFor = (kw) => Math.min(kw, 2) * 30000 + (kw >= 3 ? 18000 : 0);

export function estimateLocal(units = 0, bill = 0) {
  const u = units || (bill ? bill / RULES.tariff : 0);
  if (!u) return null;
  const kw = Math.min(Math.max(Math.round(u / RULES.unitsPerKw), RULES.minKw), RULES.maxKw);
  const generation = kw * RULES.unitsPerKw;
  const monthly = Math.min(generation, u) * RULES.tariff;
  const cost = kw * RULES.costPerKw;
  const subsidy = subsidyFor(kw);
  const net = cost - subsidy;
  return {
    units: Math.round(u),
    kw,
    system_type: 'on_grid',
    generation,
    monthly_saving: Math.round(monthly),
    yearly_saving: Math.round(monthly * 12),
    cost,
    subsidy,
    net_cost: net,
    payback_years: monthly ? Math.round((net / (monthly * 12)) * 10) / 10 : 0,
    roof_sqft: kw * RULES.roofPerKw
  };
}

export const PACKAGES = [
  { kw: 1, units: 'Up to 150 units', desc: 'Lights, fans, TV and a fridge in a small flat.' },
  { kw: 2, units: '150–270 units', desc: 'A 1–2 BHK home with everyday appliances.' },
  { kw: 3, units: '270–390 units', desc: 'A 2–3 BHK home running one air conditioner.' },
  { kw: 5, units: '390+ units', desc: 'A bungalow or villa with two or more ACs.' }
].map((p) => ({ ...p, cost: p.kw * RULES.costPerKw, subsidy: subsidyFor(p.kw), net: p.kw * RULES.costPerKw - subsidyFor(p.kw) }));
