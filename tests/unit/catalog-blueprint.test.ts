import { describe, expect, it } from "vitest";
import {
  CAPACITIES_KW,
  PANEL_WATTS,
  PRODUCTS,
  SYSTEM_TYPES,
  packageBlueprint,
  packageCode,
  panelsFor,
} from "../../prisma/seed/catalog";

const skus = new Set(PRODUCTS.map((p) => p.sku));
const qty = (lines: { sku: string; quantity: number }[], sku: string) =>
  lines.find((l) => l.sku === sku)?.quantity ?? 0;

describe("product catalogue", () => {
  it("has unique SKUs", () => {
    expect(skus.size).toBe(PRODUCTS.length);
  });

  it("uses integer paise and valid GST rates", () => {
    for (const p of PRODUCTS) {
      expect(Number.isInteger(p.costPaise)).toBe(true);
      expect(Number.isInteger(p.pricePaise)).toBe(true);
      expect(p.pricePaise).toBeGreaterThanOrEqual(p.costPaise);
      expect([0, 500, 1200, 1800, 2800]).toContain(p.gstRateBps);
    }
  });

  it("applies the default warranties: panels 20 years; inverter, battery, charge controller 2 years", () => {
    for (const p of PRODUCTS) {
      if (p.category === "PANEL") expect(p.warrantyMonths).toBe(240);
      if (["INVERTER", "BATTERY", "CHARGE_CONTROLLER"].includes(p.category))
        expect(p.warrantyMonths).toBe(24);
    }
  });

  it("requires serial scanning for every warrantied unit (panel, inverter, battery, charge controller)", () => {
    for (const p of PRODUCTS) {
      const serialized = ["PANEL", "INVERTER", "BATTERY", "CHARGE_CONTROLLER"].includes(p.category);
      expect(p.requiresSerial).toBe(serialized);
    }
  });
});

describe.each(CAPACITIES_KW)("%i kW packages", (kw) => {
  const panelSet = packageBlueprint("PANEL_SET", kw);
  const onGrid = packageBlueprint("ON_GRID", kw);
  const offGrid = packageBlueprint("OFF_GRID", kw);

  it("only references products that exist, with positive whole quantities, no duplicates", () => {
    for (const lines of [panelSet, onGrid, offGrid]) {
      const lineSkus = lines.map((l) => l.sku);
      expect(new Set(lineSkus).size).toBe(lineSkus.length);
      for (const l of lines) {
        expect(skus.has(l.sku)).toBe(true);
        expect(Number.isInteger(l.quantity) && l.quantity > 0).toBe(true);
      }
    }
  });

  it("has enough panels to reach the rated capacity", () => {
    expect(qty(panelSet, "PNL-540-MONO") * PANEL_WATTS).toBeGreaterThanOrEqual(kw * 1000);
    expect(qty(panelSet, "PNL-540-MONO")).toBe(panelsFor(kw));
  });

  it("panel set = panels, connectors and wires only", () => {
    expect(panelSet.map((l) => l.sku).sort()).toEqual(["CBL-DC-4SQ", "CON-MC4-PAIR", "PNL-540-MONO"]);
  });

  it("on-grid includes inverter of the same size, wiring boxes, charge controller, panels, earthing, stands and installation", () => {
    expect(qty(onGrid, `INV-ONG-${kw}KW`)).toBe(1);
    expect(onGrid.filter((l) => l.sku.startsWith("INV-"))).toHaveLength(1);
    expect(onGrid.filter((l) => l.sku.startsWith("CC-"))).toHaveLength(1);
    for (const sku of ["BOX-AJB", "BOX-DCDB", "BOX-ACDB", "ERT-KIT", "ERT-WIRE-10SQ", "ERT-LA"]) {
      expect(qty(onGrid, sku)).toBeGreaterThan(0);
    }
    expect(qty(onGrid, "MNT-GI-PANEL")).toBe(qty(onGrid, "PNL-540-MONO"));
    expect(qty(onGrid, "SVC-INSTALL-KW")).toBe(kw);
    expect(qty(onGrid, "BAT-12V-150AH")).toBe(0);
  });

  it("off-grid = everything in on-grid plus batteries", () => {
    const withoutBattery = offGrid.filter((l) => l.sku !== "BAT-12V-150AH");
    expect(withoutBattery).toEqual(onGrid);
    expect(qty(offGrid, "BAT-12V-150AH")).toBe(2 * kw);
  });
});

describe("package codes", () => {
  it("are unique across all 15 packages", () => {
    const codes = SYSTEM_TYPES.flatMap((t) => CAPACITIES_KW.map((kw) => packageCode(t, kw)));
    expect(new Set(codes).size).toBe(15);
    expect(codes).toContain("ONG-3KW");
  });
});
