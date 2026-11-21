import { db } from "@/server/db";
import { getNotificationProvider, type NotificationTemplate, TEMPLATES } from "@/server/notifications";
import type { JobQueue } from "./queue";

/**
 * Event handlers. Phase 0 wires notification delivery; later phases add the business automations
 * (order.confirmed → pick list + job, order.delivered → warranty start, ticket.resolved → invoice).
 */
export async function registerHandlers(queue: JobQueue): Promise<void> {
  await queue.work("notification.send", async ({ notificationId }) => {
    const n = await db.notification.findUnique({ where: { id: notificationId } });
    if (!n || n.status === "SENT") return; // idempotent

    if (!(n.template in TEMPLATES)) {
      await db.notification.update({
        where: { id: n.id },
        data: { status: "FAILED", error: `Unknown template ${n.template}`, attempts: { increment: 1 } },
      });
      return;
    }
    try {
      await getNotificationProvider().send({
        channel: n.channel,
        to: n.to,
        template: n.template as NotificationTemplate,
        params: (n.payload ?? {}) as Record<string, string>,
      });
      await db.notification.update({
        where: { id: n.id },
        data: { status: "SENT", sentAt: new Date(), attempts: { increment: 1 }, error: null },
      });
    } catch (err) {
      await db.notification.update({
        where: { id: n.id },
        data: { attempts: { increment: 1 }, error: err instanceof Error ? err.message : String(err) },
      });
      throw err; // let the queue retry
    }
  });
}
