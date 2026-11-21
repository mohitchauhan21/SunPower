import type { Metadata } from "next";
import { Placeholder } from "../placeholder";

export const metadata: Metadata = { title: "Finance" };

export default function Page() {
  return <Placeholder title="Finance" phase="Phase 5" />;
}
