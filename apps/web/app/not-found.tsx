import Link from "next/link";
import { STATIC_DEMO } from "@/lib/static";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="mt-2 text-ink-2">
        {STATIC_DEMO
          ? "This static demo only includes the six synthetic example stocks (ZZTEC, ZZBNK, ZZREI, ZZGRO, ZZUTL, ZZSML). Run the app locally to analyze any ticker."
          : "There is nothing at this address."}
      </p>
      <Link href="/" className="mt-4 inline-block text-accent-ink underline">
        Back to search
      </Link>
    </div>
  );
}
