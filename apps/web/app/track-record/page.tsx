import type { Metadata } from "next";
import { TrackRecordPage } from "@/components/track/track-record-page";

export const metadata: Metadata = { title: "Track record" };

export default function Page() {
  return <TrackRecordPage />;
}
