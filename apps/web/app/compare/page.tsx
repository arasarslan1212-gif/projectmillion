import type { Metadata } from "next";
import { Suspense } from "react";
import { ComparePage } from "@/components/compare/compare-page";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Compare" };

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-6">
          <Skeleton className="h-8 w-48" />
        </div>
      }
    >
      <ComparePage />
    </Suspense>
  );
}
