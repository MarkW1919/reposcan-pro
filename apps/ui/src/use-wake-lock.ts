import { useEffect, useRef } from "react";

/*
 * Screen Wake Lock.
 *
 * A repo driver leaves the app open on a mounted screen while navigating to a
 * recovery and scanning. If the OS dims/sleeps the display mid-route, the
 * driver loses the map and live LPR view exactly when they need them. This
 * hook holds a screen wake lock whenever `active` is true.
 *
 * Wake locks are automatically released when the page is hidden (tab switch,
 * screen off), so we re-acquire on visibilitychange while still active. All
 * access is feature-detected and best-effort: on browsers without the API the
 * hook is a no-op.
 */

type WakeLockSentinelLike = {
  release: () => Promise<void>;
  addEventListener?: (type: "release", listener: () => void) => void;
};

type WakeLockNavigator = Navigator & {
  wakeLock?: { request: (type: "screen") => Promise<WakeLockSentinelLike> };
};

export function useScreenWakeLock(active: boolean): void {
  const sentinelRef = useRef<WakeLockSentinelLike | null>(null);

  useEffect(() => {
    if (typeof navigator === "undefined") {
      return;
    }
    const wakeLock = (navigator as WakeLockNavigator).wakeLock;
    if (!wakeLock) {
      return;
    }

    let cancelled = false;

    async function acquire(): Promise<void> {
      if (cancelled || sentinelRef.current !== null || document.visibilityState !== "visible") {
        return;
      }
      try {
        const sentinel = await wakeLock!.request("screen");
        if (cancelled) {
          void sentinel.release().catch(() => undefined);
          return;
        }
        sentinelRef.current = sentinel;
        // The sentinel auto-releases when the page is hidden; clear our ref so
        // the visibility handler knows to re-acquire when visible again.
        sentinel.addEventListener?.("release", () => {
          sentinelRef.current = null;
        });
      } catch {
        // Permission denied / not allowed in this context — degrade silently.
      }
    }

    function release(): void {
      const sentinel = sentinelRef.current;
      sentinelRef.current = null;
      if (sentinel) {
        void sentinel.release().catch(() => undefined);
      }
    }

    function handleVisibility(): void {
      if (active && document.visibilityState === "visible") {
        void acquire();
      }
    }

    if (active) {
      void acquire();
      document.addEventListener("visibilitychange", handleVisibility);
    }

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", handleVisibility);
      release();
    };
  }, [active]);
}
