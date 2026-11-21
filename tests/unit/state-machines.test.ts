import { describe, expect, it } from "vitest";
import { IllegalTransitionError } from "@/server/errors";
import {
  defineMachine,
  jobMachine,
  leadMachine,
  orderMachine,
  pickListMachine,
  quoteMachine,
  subsidyMachine,
  surveyMachine,
  ticketMachine,
  type StateMachine,
} from "@/server/state-machines";

const machines: StateMachine<string>[] = [
  leadMachine,
  surveyMachine,
  quoteMachine,
  orderMachine,
  pickListMachine,
  jobMachine,
  ticketMachine,
  subsidyMachine,
];

describe.each(machines.map((m) => [m.name, m] as const))("%s machine", (_name, machine) => {
  it("allows exactly the listed transitions and rejects every other pair", () => {
    for (const from of machine.states) {
      for (const to of machine.states) {
        const allowed = machine.transitions[from]!.includes(to);
        expect(machine.canTransition(from, to)).toBe(allowed);
        if (allowed) {
          expect(() => machine.assertTransition(from, to)).not.toThrow();
        } else {
          expect(() => machine.assertTransition(from, to)).toThrow(IllegalTransitionError);
        }
      }
    }
  });

  it("never allows a self-transition", () => {
    for (const s of machine.states) expect(machine.canTransition(s, s)).toBe(false);
  });

  it("can reach every state from the initial state", () => {
    const seen = new Set([machine.initial]);
    const queue = [machine.initial];
    while (queue.length) {
      for (const next of machine.allowedNext(queue.shift()!)) {
        if (!seen.has(next)) {
          seen.add(next);
          queue.push(next);
        }
      }
    }
    expect([...seen].sort()).toEqual([...machine.states].sort());
  });
});

function walk<S extends string>(machine: StateMachine<S>, path: S[]): void {
  for (let i = 1; i < path.length; i++) machine.assertTransition(path[i - 1]!, path[i]!);
}

describe("Lead workflow", () => {
  it("follows the happy path to Won", () => {
    expect(() =>
      walk(leadMachine, [
        "NEW",
        "CONTACTED",
        "QUALIFIED",
        "SURVEY_SCHEDULED",
        "SURVEY_APPROVED",
        "QUOTE_SENT",
        "WON",
      ]),
    ).not.toThrow();
  });

  it("cannot jump to quote without an approved survey", () => {
    expect(() => leadMachine.assertTransition("QUALIFIED", "QUOTE_SENT")).toThrow(IllegalTransitionError);
    expect(() => leadMachine.assertTransition("SURVEY_SCHEDULED", "QUOTE_SENT")).toThrow(
      IllegalTransitionError,
    );
    expect(() => leadMachine.assertTransition("NEW", "WON")).toThrow(IllegalTransitionError);
  });

  it("sends a rejected survey back to Qualified", () => {
    expect(leadMachine.canTransition("SURVEY_SCHEDULED", "QUALIFIED")).toBe(true);
  });

  it("treats Won and Lost as final", () => {
    expect(leadMachine.isFinal("WON")).toBe(true);
    expect(leadMachine.isFinal("LOST")).toBe(true);
    expect(() => leadMachine.assertTransition("LOST", "NEW")).toThrow(IllegalTransitionError);
  });

  it("produces a readable error with the allowed next steps", () => {
    try {
      leadMachine.assertTransition("NEW", "WON");
      expect.unreachable();
    } catch (e) {
      const err = e as IllegalTransitionError;
      expect(err.code).toBe("ILLEGAL_TRANSITION");
      expect(err.status).toBe(409);
      expect(err.message).toBe("Lead cannot move from NEW to WON. Allowed next steps: CONTACTED, LOST.");
      expect(err.details).toMatchObject({ from: "NEW", to: "WON", allowed: ["CONTACTED", "LOST"] });
    }
  });
});

describe("Order workflow", () => {
  it("follows Confirmed → Packed → Dispatched → Delivered → Installed → Handed Over", () => {
    expect(() =>
      walk(orderMachine, [
        "AWAITING_ADVANCE",
        "CONFIRMED",
        "PACKED",
        "DISPATCHED",
        "DELIVERED",
        "INSTALLED",
        "HANDED_OVER",
      ]),
    ).not.toThrow();
  });

  it("cannot skip packing or delivery", () => {
    expect(() => orderMachine.assertTransition("CONFIRMED", "DISPATCHED")).toThrow(IllegalTransitionError);
    expect(() => orderMachine.assertTransition("DISPATCHED", "INSTALLED")).toThrow(IllegalTransitionError);
  });

  it("cannot be cancelled once goods have left the warehouse", () => {
    expect(orderMachine.canTransition("PACKED", "CANCELLED")).toBe(true);
    expect(orderMachine.canTransition("DISPATCHED", "CANCELLED")).toBe(false);
    expect(orderMachine.canTransition("DELIVERED", "CANCELLED")).toBe(false);
  });
});

describe("Ticket workflow", () => {
  it("follows Open → Assigned → In Progress → Resolved → Customer Confirmed → Closed", () => {
    expect(() =>
      walk(ticketMachine, ["OPEN", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CUSTOMER_CONFIRMED", "CLOSED"]),
    ).not.toThrow();
  });

  it("cannot close without customer confirmation", () => {
    expect(() => ticketMachine.assertTransition("RESOLVED", "CLOSED")).toThrow(IllegalTransitionError);
    expect(() => ticketMachine.assertTransition("OPEN", "CLOSED")).toThrow(IllegalTransitionError);
  });

  it("reopens when the customer says it still doesn't work", () => {
    expect(ticketMachine.canTransition("RESOLVED", "IN_PROGRESS")).toBe(true);
  });
});

describe("defineMachine", () => {
  it("rejects a table that targets an unknown state", () => {
    expect(() =>
      defineMachine<"A" | "B">({ name: "Bad", initial: "A", transitions: { A: ["C" as "B"], B: [] } }),
    ).toThrow(/unknown state/);
  });
});
