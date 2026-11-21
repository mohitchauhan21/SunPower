import { z } from "zod";

/**
 * Every background event the system emits. Payloads are validated when they are written to the
 * outbox and again when a worker picks them up, so a malformed event fails loudly, once.
 */
export const EVENT_SCHEMAS = {
  "notification.send": z.object({
    notificationId: z.string().min(1),
  }),
  "enquiry.received": z.object({
    leadId: z.string().min(1),
  }),
  "order.confirmed": z.object({
    orderId: z.string().min(1),
  }),
  "order.delivered": z.object({
    orderId: z.string().min(1),
  }),
  "ticket.resolved": z.object({
    ticketId: z.string().min(1),
  }),
} as const;

export type EventType = keyof typeof EVENT_SCHEMAS;
export type EventPayload<T extends EventType> = z.infer<(typeof EVENT_SCHEMAS)[T]>;
export const EVENT_TYPES = Object.keys(EVENT_SCHEMAS) as EventType[];

export function isEventType(value: string): value is EventType {
  return value in EVENT_SCHEMAS;
}

export function parseEventPayload<T extends EventType>(type: T, payload: unknown): EventPayload<T> {
  return EVENT_SCHEMAS[type].parse(payload) as EventPayload<T>;
}
