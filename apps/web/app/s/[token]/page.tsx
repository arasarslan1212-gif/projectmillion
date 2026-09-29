import type { Metadata } from "next";
import { SnapshotView } from "@/components/share/snapshot-view";

export const metadata: Metadata = { title: "Report snapshot", robots: { index: false } };

export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SnapshotView token={decodeURIComponent(token)} />;
}
