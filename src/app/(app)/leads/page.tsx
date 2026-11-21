import type { Metadata } from "next";
import { Placeholder } from "../placeholder";

export const metadata: Metadata = { title: "Leads" };

export default function Page() {
  return <Placeholder title="Leads" phase="Phase 1" />;
}
