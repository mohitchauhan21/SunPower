import type { ProductCategory, ProductKind, SystemType } from "@prisma/client";

/**
 * Catalogue and package bill-of-materials rules. Pure data + pure functions, so the same rules are
 * used by the seed script and checked by unit tests.
 *
 * Prices are realistic placeholders for review; every figure is editable in the app later.
 * Money is in paise (₹1 = 100 paise).
 */

export interface SeedProduct {
  sku: string;
  name: string;
  kind: ProductKind;
  category: ProductCategory;
  unit: string;
  requiresSerial: boolean;
  warrantyMonths: number;
  costPaise: number;
  pricePaise: number;
  gstRateBps: number;
  hsnCode: string;
  ratedWatts?: number;
}

const rs = (rupees: number) => Math.round(rupees * 100);

export const PANEL_WATTS = 540;
export const PANEL_WARRANTY_MONTHS = 20 * 12;
export const ELECTRONICS_WARRANTY_MONTHS = 2 * 12;

export const CAPACITIES_KW = [1, 2, 3, 4, 5] as const;
export type CapacityKw = (typeof CAPACITIES_KW)[number];

const inverterPrice: Record<CapacityKw, [cost: number, price: number]> = {
  1: [18_000, 24_000],
  2: [26_000, 33_000],
  3: [32_000, 41_000],
  4: [40_000, 50_000],
  5: [46_000, 58_000],
};

export const PRODUCTS: SeedProduct[] = [
  {
    sku: "PNL-540-MONO",
    name: "Solar panel 540 Wp mono PERC",
    kind: "GOODS",
    category: "PANEL",
    unit: "pc",
    requiresSerial: true,
    warrantyMonths: PANEL_WARRANTY_MONTHS,
    costPaise: rs(13_500),
    pricePaise: rs(16_500),
    gstRateBps: 1200,
    hsnCode: "8541",
    ratedWatts: PANEL_WATTS,
  },
  ...CAPACITIES_KW.map<SeedProduct>((kw) => ({
    sku: `INV-ONG-${kw}KW`,
    name: `On-grid inverter ${kw} kW`,
    kind: "GOODS",
    category: "INVERTER",
    unit: "pc",
    requiresSerial: true,
    warrantyMonths: ELECTRONICS_WARRANTY_MONTHS,
    costPaise: rs(inverterPrice[kw][0]),
    pricePaise: rs(inverterPrice[kw][1]),
    gstRateBps: 1200,
    hsnCode: "8504",
    ratedWatts: kw * 1000,
  })),
  {
    sku: "CC-MPPT-24V-40A",
    name: "MPPT charge controller 24 V 40 A",
    kind: "GOODS",
    category: "CHARGE_CONTROLLER",
    unit: "pc",
    requiresSerial: true,
    warrantyMonths: ELECTRONICS_WARRANTY_MONTHS,
    costPaise: rs(4_500),
    pricePaise: rs(6_000),
    gstRateBps: 1200,
    hsnCode: "8504",
  },
  {
    sku: "CC-MPPT-48V-60A",
    name: "MPPT charge controller 48 V 60 A",
    kind: "GOODS",
    category: "CHARGE_CONTROLLER",
    unit: "pc",
    requiresSerial: true,
    warrantyMonths: ELECTRONICS_WARRANTY_MONTHS,
    costPaise: rs(8_000),
    pricePaise: rs(10_500),
    gstRateBps: 1200,
    hsnCode: "8504",
  },
  {
    sku: "BAT-12V-150AH",
    name: "Solar tubular battery 12 V 150 Ah",
    kind: "GOODS",
    category: "BATTERY",
    unit: "pc",
    requiresSerial: true,
    warrantyMonths: ELECTRONICS_WARRANTY_MONTHS,
    costPaise: rs(11_000),
    pricePaise: rs(14_500),
    gstRateBps: 1800,
    hsnCode: "8507",
  },
  {
    sku: "MNT-GI-PANEL",
    name: "GI mounting structure (per panel)",
    kind: "GOODS",
    category: "MOUNTING",
    unit: "set",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(1_800),
    pricePaise: rs(2_400),
    gstRateBps: 1800,
    hsnCode: "7308",
  },
  {
    sku: "BOX-AJB",
    name: "Array junction box (wiring box)",
    kind: "GOODS",
    category: "PROTECTION",
    unit: "pc",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(1_600),
    pricePaise: rs(2_200),
    gstRateBps: 1800,
    hsnCode: "8537",
  },
  {
    sku: "BOX-DCDB",
    name: "DC distribution box with SPD",
    kind: "GOODS",
    category: "PROTECTION",
    unit: "pc",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(3_000),
    pricePaise: rs(4_200),
    gstRateBps: 1800,
    hsnCode: "8537",
  },
  {
    sku: "BOX-ACDB",
    name: "AC distribution box with MCB",
    kind: "GOODS",
    category: "PROTECTION",
    unit: "pc",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(2_500),
    pricePaise: rs(3_500),
    gstRateBps: 1800,
    hsnCode: "8537",
  },
  {
    sku: "CBL-DC-4SQ",
    name: "DC solar cable 4 sq mm",
    kind: "GOODS",
    category: "WIRING",
    unit: "m",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(45),
    pricePaise: rs(65),
    gstRateBps: 1800,
    hsnCode: "8544",
  },
  {
    sku: "CBL-AC-4SQ",
    name: "AC cable 4 sq mm",
    kind: "GOODS",
    category: "WIRING",
    unit: "m",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(55),
    pricePaise: rs(80),
    gstRateBps: 1800,
    hsnCode: "8544",
  },
  {
    sku: "CON-MC4-PAIR",
    name: "MC4 connector pair",
    kind: "GOODS",
    category: "CONNECTOR",
    unit: "pair",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(90),
    pricePaise: rs(150),
    gstRateBps: 1800,
    hsnCode: "8536",
  },
  {
    sku: "ERT-KIT",
    name: "Chemical earthing kit (rod + compound)",
    kind: "GOODS",
    category: "EARTHING",
    unit: "set",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(2_200),
    pricePaise: rs(3_000),
    gstRateBps: 1800,
    hsnCode: "8538",
  },
  {
    sku: "ERT-WIRE-10SQ",
    name: "Earthing wire 10 sq mm",
    kind: "GOODS",
    category: "EARTHING",
    unit: "m",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(60),
    pricePaise: rs(90),
    gstRateBps: 1800,
    hsnCode: "8544",
  },
  {
    sku: "ERT-LA",
    name: "Lightning arrester",
    kind: "GOODS",
    category: "EARTHING",
    unit: "pc",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: rs(2_500),
    pricePaise: rs(3_500),
    gstRateBps: 1800,
    hsnCode: "8535",
  },
  {
    sku: "SVC-INSTALL-KW",
    name: "Installation, fitting and testing (per kW)",
    kind: "SERVICE",
    category: "SERVICE",
    unit: "kW",
    requiresSerial: false,
    warrantyMonths: 0,
    costPaise: 0,
    pricePaise: rs(6_000),
    gstRateBps: 1800,
    hsnCode: "9954",
  },
];

export interface BlueprintLine {
  sku: string;
  quantity: number;
}

export function panelsFor(kw: number): number {
  return Math.ceil((kw * 1000) / PANEL_WATTS);
}

/**
 * The bill of materials for each package. "Nobody should have to remember every small part."
 *  - Panel set: panels, connectors, DC cable.
 *  - On-grid: panel set + inverter, stands, wiring boxes, charge controller, earthing, AC cable, installation.
 *  - Off-grid: everything in on-grid + batteries (2 × 12 V 150 Ah per kW).
 */
export function packageBlueprint(systemType: SystemType, kw: CapacityKw): BlueprintLine[] {
  const panels = panelsFor(kw);
  const panelSet: BlueprintLine[] = [
    { sku: "PNL-540-MONO", quantity: panels },
    { sku: "CON-MC4-PAIR", quantity: Math.ceil(panels / 2) + 2 },
    { sku: "CBL-DC-4SQ", quantity: 20 + 10 * kw },
  ];
  if (systemType === "PANEL_SET") return panelSet;

  const onGrid: BlueprintLine[] = [
    ...panelSet,
    { sku: `INV-ONG-${kw}KW`, quantity: 1 },
    { sku: kw <= 2 ? "CC-MPPT-24V-40A" : "CC-MPPT-48V-60A", quantity: 1 },
    { sku: "MNT-GI-PANEL", quantity: panels },
    { sku: "BOX-AJB", quantity: 1 },
    { sku: "BOX-DCDB", quantity: 1 },
    { sku: "BOX-ACDB", quantity: 1 },
    { sku: "CBL-AC-4SQ", quantity: 20 },
    { sku: "ERT-KIT", quantity: 3 },
    { sku: "ERT-WIRE-10SQ", quantity: 30 },
    { sku: "ERT-LA", quantity: 1 },
    { sku: "SVC-INSTALL-KW", quantity: kw },
  ];
  if (systemType === "ON_GRID") return onGrid;

  return [...onGrid, { sku: "BAT-12V-150AH", quantity: 2 * kw }];
}

export const SYSTEM_TYPE_LABEL: Record<SystemType, string> = {
  PANEL_SET: "Solar Panel Set",
  ON_GRID: "On-Grid System",
  OFF_GRID: "Off-Grid System",
};

export function packageCode(systemType: SystemType, kw: number): string {
  const short: Record<SystemType, string> = { PANEL_SET: "PSET", ON_GRID: "ONG", OFF_GRID: "OFG" };
  return `${short[systemType]}-${kw}KW`;
}

export const SYSTEM_TYPES: SystemType[] = ["PANEL_SET", "ON_GRID", "OFF_GRID"];
