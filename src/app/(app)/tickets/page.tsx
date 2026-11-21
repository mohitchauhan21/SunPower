import type { Metadata } from "next";
import { Placeholder } from "../placeholder";

export const metadata: Metadata = { title: "Service tickets" };

export default function Page() {
  return <Placeholder title="Service tickets" phase="Phase 4" />;
}
