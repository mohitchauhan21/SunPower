import type { Metadata } from "next";
import { Placeholder } from "../placeholder";

export const metadata: Metadata = { title: "My jobs" };

export default function Page() {
  return <Placeholder title="My jobs" phase="Phase 3" />;
}
