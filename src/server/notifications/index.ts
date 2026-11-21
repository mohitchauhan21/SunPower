import type { NotificationChannel } from "@prisma/client";

/**
 * Customer notifications go through this adapter. Dev uses the console provider; a real
 * WhatsApp/SMS provider is plugged in (behind config) in Phase 6.
 */
export interface OutgoingMessage {
  channel: NotificationChannel;
  /** 10-digit mobile or email address. */
  to: string;
  template: NotificationTemplate;
  params: Record<string, string>;
}

export interface NotificationProvider {
  readonly name: string;
  send(message: OutgoingMessage): Promise<{ providerMessageId: string }>;
}

export const TEMPLATES = {
  enquiry_received:
    "Hi {name}, thanks for contacting SunPower Solutions. Our team will call you shortly. Ref: {leadNumber}",
  survey_scheduled:
    "Hi {name}, your roof survey is scheduled for {date}. Our technician {technician} will visit.",
  quote_sent: "Hi {name}, your quote {quoteNumber} for {system} is ready: {total}.",
  order_confirmed: "Hi {name}, we have received your advance of {amount}. Order {orderNumber} is confirmed.",
  order_dispatched: "Hi {name}, your solar kit for order {orderNumber} is on its way.",
  installation_complete: "Hi {name}, your {system} system is installed. Warranty is active from {date}.",
  ticket_created:
    "Hi {name}, we've logged your complaint {ticketNumber}. A technician will contact you soon.",
  ticket_resolved: "Hi {name}, complaint {ticketNumber} is resolved. Please confirm everything is working.",
} as const;

export type NotificationTemplate = keyof typeof TEMPLATES;

/** Fill {placeholders}; any placeholder without a value is left visible so it's caught in review. */
export function renderTemplate(template: NotificationTemplate, params: Record<string, string>): string {
  return TEMPLATES[template].replace(/\{(\w+)\}/g, (match, key: string) => params[key] ?? match);
}

export class ConsoleNotificationProvider implements NotificationProvider {
  readonly name = "console";
  readonly outbox: { to: string; channel: NotificationChannel; text: string }[] = [];

  async send(message: OutgoingMessage): Promise<{ providerMessageId: string }> {
    const text = renderTemplate(message.template, message.params);
    this.outbox.push({ to: message.to, channel: message.channel, text });
    if (process.env.NODE_ENV !== "test") {
      console.info(`[notify:${message.channel}] → ${message.to}: ${text}`);
    }
    return { providerMessageId: `console-${Date.now()}-${this.outbox.length}` };
  }
}

let provider: NotificationProvider | undefined;

export function getNotificationProvider(): NotificationProvider {
  if (provider) return provider;
  const configured = process.env.NOTIFICATION_PROVIDER ?? "console";
  switch (configured) {
    case "console":
      provider = new ConsoleNotificationProvider();
      return provider;
    default:
      throw new Error(`Unknown NOTIFICATION_PROVIDER "${configured}"`);
  }
}

/** Tests can swap in a fake. */
export function setNotificationProvider(p: NotificationProvider | undefined): void {
  provider = p;
}
