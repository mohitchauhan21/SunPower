import type {
  JobStatus,
  LeadStatus,
  OrderStatus,
  PickListStatus,
  QuoteStatus,
  SubsidyStatus,
  SurveyStatus,
  TicketStatus,
} from "@prisma/client";
import { defineMachine } from "./machine";

export { defineMachine, type StateMachine } from "./machine";

/**
 * Lead: New → Contacted → Qualified → Survey Scheduled → Survey Approved → Quote Sent → Won / Lost.
 * - A rejected survey sends the lead back to Qualified (re-survey) or to Lost.
 * - A lead can be lost at any open stage.
 * - Quote Sent → Survey Approved lets sales revise a quote the customer declined.
 */
export const leadMachine = defineMachine<LeadStatus>({
  name: "Lead",
  initial: "NEW",
  transitions: {
    NEW: ["CONTACTED", "LOST"],
    CONTACTED: ["QUALIFIED", "LOST"],
    QUALIFIED: ["SURVEY_SCHEDULED", "LOST"],
    SURVEY_SCHEDULED: ["SURVEY_APPROVED", "QUALIFIED", "LOST"],
    SURVEY_APPROVED: ["QUOTE_SENT", "LOST"],
    QUOTE_SENT: ["WON", "LOST", "SURVEY_APPROVED"],
    WON: [],
    LOST: [],
  },
});

export const surveyMachine = defineMachine<SurveyStatus>({
  name: "Survey",
  initial: "SCHEDULED",
  transitions: {
    SCHEDULED: ["COMPLETED", "CANCELLED"],
    COMPLETED: ["APPROVED", "REJECTED"],
    APPROVED: [],
    REJECTED: [],
    CANCELLED: [],
  },
});

export const quoteMachine = defineMachine<QuoteStatus>({
  name: "Quote",
  initial: "DRAFT",
  transitions: {
    DRAFT: ["SENT", "SUPERSEDED"],
    SENT: ["ACCEPTED", "REJECTED", "EXPIRED", "SUPERSEDED"],
    ACCEPTED: [],
    REJECTED: [],
    EXPIRED: [],
    SUPERSEDED: [],
  },
});

/**
 * Order: (Awaiting advance) → Confirmed → Packed → Dispatched → Delivered → Installed → Handed Over.
 * Cancellation is allowed only before the goods leave the warehouse.
 */
export const orderMachine = defineMachine<OrderStatus>({
  name: "Order",
  initial: "AWAITING_ADVANCE",
  transitions: {
    AWAITING_ADVANCE: ["CONFIRMED", "CANCELLED"],
    CONFIRMED: ["PACKED", "CANCELLED"],
    PACKED: ["DISPATCHED", "CANCELLED"],
    DISPATCHED: ["DELIVERED"],
    DELIVERED: ["INSTALLED"],
    INSTALLED: ["HANDED_OVER"],
    HANDED_OVER: [],
    CANCELLED: [],
  },
});

export const pickListMachine = defineMachine<PickListStatus>({
  name: "Pick list",
  initial: "OPEN",
  transitions: {
    OPEN: ["PICKING", "CANCELLED"],
    PICKING: ["PACKED", "CANCELLED"],
    PACKED: [],
    CANCELLED: [],
  },
});

export const jobMachine = defineMachine<JobStatus>({
  name: "Installation job",
  initial: "SCHEDULED",
  transitions: {
    SCHEDULED: ["IN_PROGRESS", "CANCELLED"],
    IN_PROGRESS: ["COMPLETED"],
    COMPLETED: [],
    CANCELLED: [],
  },
});

/**
 * Ticket: Open → Assigned → In Progress → Resolved → Customer Confirmed → Closed.
 * - Resolved → In Progress: the customer reports it still isn't working (reopen).
 * - Assigned → Assigned is not a transition; reassignment changes the assignee only.
 */
export const ticketMachine = defineMachine<TicketStatus>({
  name: "Ticket",
  initial: "OPEN",
  transitions: {
    OPEN: ["ASSIGNED"],
    ASSIGNED: ["IN_PROGRESS"],
    IN_PROGRESS: ["RESOLVED"],
    RESOLVED: ["CUSTOMER_CONFIRMED", "IN_PROGRESS"],
    CUSTOMER_CONFIRMED: ["CLOSED"],
    CLOSED: [],
  },
});

export const subsidyMachine = defineMachine<SubsidyStatus>({
  name: "Subsidy application",
  initial: "NOT_APPLIED",
  transitions: {
    NOT_APPLIED: ["APPLIED"],
    APPLIED: ["INSPECTION_PENDING", "REJECTED"],
    INSPECTION_PENDING: ["INSPECTED", "REJECTED"],
    INSPECTED: ["APPROVED", "REJECTED"],
    APPROVED: ["DISBURSED"],
    DISBURSED: [],
    REJECTED: ["APPLIED"],
  },
});
