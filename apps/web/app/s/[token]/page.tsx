import type { Metadata } from "next";
import { SnapshotView } from "@/components/share/snapshot-view";
import { staticManifest } from "@/lib/static-params";

export const metadata: Metadata = { title: "Report snapshot", robots: { index: false } };

export function generateStaticParams() {
  return staticManifest().snapshot_tokens.map((token) => ({ token }));
}

export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SnapshotView token={decodeURIComponent(token)} />;
}
