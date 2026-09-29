import Link from "next/link";
import { STATIC_DEMO } from "@/lib/static";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="mt-2 text-ink-2">
        {STATIC_DEMO
          ? "This site covers the synthetic test companies only (ZZTEC, ZZBNK, ZZREI, ZZGRO, ZZUTL, ZZSML and their ZQ… peers). Run the app with data providers to analyze real tickers."
          : "There is nothing at this address."}
      </p>
      <Link href="/" className="mt-4 inline-block text-accent-ink underline">
        Back to search
      </Link>
    </div>
  );
}
