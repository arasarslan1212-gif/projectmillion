import type { Metadata } from "next";
import { MethodologyPage } from "@/components/meta/methodology-page";

export const metadata: Metadata = { title: "Glossary" };

export default function Page() {
  return <MethodologyPage glossaryOnly />;
}
