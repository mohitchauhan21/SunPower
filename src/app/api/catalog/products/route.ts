import { withActor } from "@/server/http";
import { listProducts } from "@/server/services/catalog.service";

export const dynamic = "force-dynamic";

export const GET = withActor(async (_req, actor) => listProducts(actor));
