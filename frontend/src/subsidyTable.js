// Generated from backend/app/subsidy.py (same data). Used until the server answers,
// and if it can not, so every state is always selectable.
export const FALLBACK_TABLE = {
 "default": null,
 "researched": "22 Nov 2026",
 "rates": {
  "general": {
   "per_kw": 30000,
   "third_kw": 18000,
   "max": 78000
  },
  "special": {
   "per_kw": 33000,
   "third_kw": 19800,
   "max": 85800
  }
 },
 "states": [
  {
   "name": "Andhra Pradesh",
   "category": "general",
   "topup": null,
   "note": "Reported targeted SC/ST district drives; not universal"
  },
  {
   "name": "Arunachal Pradesh",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Assam",
   "category": "special",
   "topup": {
    "per_kw": 15000,
    "max": 45000
   },
   "note": "Reported ₹15,000/kW, max ₹45,000; availability unclear"
  },
  {
   "name": "Bihar",
   "category": "general",
   "topup": {
    "per_kw": 10000,
    "max": 20000
   },
   "note": "Reported ₹10,000/kW, max ₹20,000; needs verification"
  },
  {
   "name": "Chhattisgarh",
   "category": "general",
   "topup": {
    "tiers": {
     "1": 15000,
     "2": 30000
    }
   },
   "note": "Reported ₹15,000 (1 kW), ₹30,000 (2 kW+)"
  },
  {
   "name": "Goa",
   "category": "general",
   "topup": null,
   "note": "Reported cost-based incentive; amount not verified"
  },
  {
   "name": "Gujarat",
   "category": "general",
   "topup": null,
   "note": "No universal state capital subsidy; regulatory-charge relief reported"
  },
  {
   "name": "Haryana",
   "category": "general",
   "topup": null,
   "note": "Targeted schemes for eligible income groups; amounts vary"
  },
  {
   "name": "Himachal Pradesh",
   "category": "special",
   "topup": null,
   "note": "No additional universal top-up verified"
  },
  {
   "name": "Jharkhand",
   "category": "general",
   "topup": null,
   "note": "Reported income-limited top-up; not verified"
  },
  {
   "name": "Karnataka",
   "category": "general",
   "topup": null,
   "note": "No universal additional top-up verified"
  },
  {
   "name": "Kerala",
   "category": "general",
   "topup": null,
   "note": "No universal additional top-up verified"
  },
  {
   "name": "Madhya Pradesh",
   "category": "general",
   "topup": null,
   "note": "No universal additional top-up verified"
  },
  {
   "name": "Maharashtra",
   "category": "general",
   "topup": null,
   "note": "Targeted MSEDCL schemes reported (SMART); not universal"
  },
  {
   "name": "Manipur",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Meghalaya",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Mizoram",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Nagaland",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Odisha",
   "category": "general",
   "topup": null,
   "note": "Reported additional amounts vary across sources"
  },
  {
   "name": "Punjab",
   "category": "general",
   "topup": null,
   "note": "No universal state top-up identified"
  },
  {
   "name": "Rajasthan",
   "category": "general",
   "topup": null,
   "note": "Reported ₹17,000 only for eligible Mukhyamantri Nishulk Bijli Yojana beneficiaries"
  },
  {
   "name": "Sikkim",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Tamil Nadu",
   "category": "general",
   "topup": {
    "tiers": {
     "1": 5000,
     "2": 10000,
     "3": 22000
    }
   },
   "note": "Reported tiered top-up (₹5,000 / ₹10,000 / ₹22,000)"
  },
  {
   "name": "Telangana",
   "category": "general",
   "topup": null,
   "note": "Reported top-up claims; not verified"
  },
  {
   "name": "Tripura",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Uttar Pradesh",
   "category": "general",
   "topup": {
    "per_kw": 15000,
    "max": 30000
   },
   "note": "Reported ₹15,000/kW up to ₹30,000 via UPNEDA"
  },
  {
   "name": "Uttarakhand",
   "category": "special",
   "topup": null,
   "note": "No universal top-up; earlier state support reportedly discontinued"
  },
  {
   "name": "West Bengal",
   "category": "general",
   "topup": null,
   "note": "Reported tiered top-up; eligibility needs verification"
  },
  {
   "name": "Andaman & Nicobar Islands",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Chandigarh",
   "category": "general",
   "topup": null,
   "note": "Proposed top-up reported; approval not confirmed"
  },
  {
   "name": "Dadra & Nagar Haveli and Daman & Diu",
   "category": "general",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Delhi",
   "category": "general",
   "topup": null,
   "note": "Reported 2026 top-up revisions; amount needs official confirmation"
  },
  {
   "name": "Jammu & Kashmir",
   "category": "special",
   "topup": {
    "per_kw": 3000,
    "max": 9000
   },
   "note": "Reported UT top-up ₹3,000/kW"
  },
  {
   "name": "Ladakh",
   "category": "special",
   "topup": null,
   "note": "Reported local assistance; not verified"
  },
  {
   "name": "Lakshadweep",
   "category": "special",
   "topup": null,
   "note": "No universal top-up verified"
  },
  {
   "name": "Puducherry",
   "category": "general",
   "topup": {
    "per_kw": 9000,
    "max": 27000
   },
   "note": "Reported UT top-up ₹9,000–₹10,000/kW (lower figure used)"
  }
 ],
 "average": {
  "1": 31167,
  "2": 62333,
  "3": 81033,
  "4": 81033,
  "5": 81033,
  "6": 81033,
  "7": 81033,
  "8": 81033,
  "9": 81033,
  "10": 81033
 }
};
