import type { Metadata } from "next";
import { AboutPage } from "@/components/meta/about-page";

export const metadata: Metadata = { title: "About & data sources" };

export default function Page() {
  return <AboutPage />;
}
