"use client";

import * as Popover from "@radix-ui/react-popover";
import { Check, Copy, Link2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { getJSON } from "@/lib/api";
import { formatDate } from "@/lib/format";

/** Freezes today's report on the server and shows its shareable link. */
export function ShareButton({ ticker }: { ticker: string }) {
  const [state, setState] = useState<{ url?: string; asOf?: string; error?: string; busy?: boolean }>({});
  const [copied, setCopied] = useState(false);

  const create = async () => {
    if (state.url || state.busy) return;
    setState({ busy: true });
    try {
      const r = await getJSON<{ token: string; as_of: string }>(
        `/report/${encodeURIComponent(ticker)}/share`,
        {
          method: "POST",
        },
      );
      setState({ url: `${window.location.origin}/s/${r.token}`, asOf: r.as_of });
    } catch (e) {
      setState({ error: (e as Error).message });
    }
  };

  const copy = async () => {
    if (!state.url) return;
    try {
      await navigator.clipboard.writeText(state.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked: the link is selectable in the field */
    }
  };

  return (
    <Popover.Root onOpenChange={(o) => o && create()}>
      <Popover.Trigger asChild>
        <Button aria-label="Create a shareable snapshot link">
          <Link2 className="size-3.5" />
          <span className="hidden sm:inline">Share</span>
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="z-50 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-line bg-surface p-3 text-sm shadow-lg"
        >
          <p className="font-semibold">Snapshot link</p>
          {state.busy && <p className="mt-1 text-ink-2">Freezing today&apos;s report…</p>}
          {state.error && <p className="mt-1 text-critical-ink">{state.error}</p>}
          {state.url && (
            <>
              <p className="mt-1 text-xs text-ink-2">
                The report as of {formatDate(state.asOf)}, frozen: the link keeps showing these numbers, and
                later how the estimate turned out.
              </p>
              <div className="mt-2 flex gap-1.5">
                <label htmlFor="share-url" className="sr-only">
                  Snapshot link
                </label>
                <input
                  id="share-url"
                  readOnly
                  value={state.url}
                  onFocus={(e) => e.currentTarget.select()}
                  className="h-8 min-w-0 flex-1 rounded-md border border-line bg-surface-2 px-2 text-xs"
                />
                <Button onClick={copy} aria-label="Copy link">
                  {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                </Button>
              </div>
            </>
          )}
          <Popover.Arrow className="fill-[var(--line)]" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
