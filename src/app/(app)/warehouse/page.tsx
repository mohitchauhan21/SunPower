import type { Metadata } from "next";
import { Placeholder } from "../placeholder";

export const metadata: Metadata = { title: "Warehouse" };

export default function Page() {
  return <Placeholder title="Warehouse" phase="Phase 2" />;
}
