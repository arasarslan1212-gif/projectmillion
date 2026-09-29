"use client";

import { useEffect, useState } from "react";
import { getJSON } from "./api";
import { syncWatchlist } from "./recent";

let synced = false;

/** Unread alert count for the header badge; refreshed every few minutes and whenever alerts change. */
export function useUnreadAlerts(): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!synced) {
      synced = true;
      syncWatchlist();
    }
    let alive = true;
    const load = () =>
      getJSON<{ unread: number }>("/alerts/unread")
        .then((r) => alive && setN(r.unread))
        .catch(() => {
          /* engine unavailable: keep the last count */
        });
    load();
    const id = setInterval(load, 5 * 60 * 1000);
    window.addEventListener("alerts-changed", load);
    return () => {
      alive = false;
      clearInterval(id);
      window.removeEventListener("alerts-changed", load);
    };
  }, []);
  return n;
}
