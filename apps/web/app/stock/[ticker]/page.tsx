import type { Metadata } from "next";
import { ReportPage } from "@/components/report/report-page";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ ticker: string }>;
}): Promise<Metadata> {
  const { ticker } = await params;
  return { title: decodeURIComponent(ticker).toUpperCase() };
}

export default async function Page({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return <ReportPage ticker={decodeURIComponent(ticker).toUpperCase()} />;
}
