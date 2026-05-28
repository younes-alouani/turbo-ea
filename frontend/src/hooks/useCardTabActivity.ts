import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import type { EventEntry } from "@/types";

const STORAGE_KEY = "turbo-ea.cardTabsSeen";
const LRU_CAP = 200;
const HISTORY_PAGE_SIZE = 50;
// Sentinel timestamp captured on the very first hook mount per card; never
// overwritten on subsequent visits. Acts as the fallback "you've been here"
// baseline for tabs the user has never explicitly opened.
const FIRST_VISIT_KEY = "__first";

const EVENT_TAB_MAP: Record<string, string> = {
  "comment.created": "comments",
  "stakeholder.added": "stakeholders",
  "stakeholder.role_changed": "stakeholders",
  "stakeholder.removed": "stakeholders",
  "risk.added": "risks",
  "risk.updated": "risks",
  "risk.removed": "risks",
  "document.added": "resources",
  "document.removed": "resources",
  "file.uploaded": "resources",
  "file.deleted": "resources",
  "card.created": "card",
  "card.updated": "card",
  "card.archived": "card",
  "card.restored": "card",
  "card.approval_status.approve": "card",
  "card.approval_status.reject": "card",
  "card.approval_status.reset": "card",
  "relation.created": "card",
  "relation.updated": "card",
  "relation.deleted": "card",
};

type StoreShape = {
  __lru?: string[];
  [cardId: string]: Record<string, string> | string[] | undefined;
};

function readStore(): StoreShape {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return parsed as StoreShape;
  } catch {
    return {};
  }
}

function writeStore(store: StoreShape) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // localStorage may be disabled, full, or unavailable (SSR); silently skip.
  }
}

function bumpLru(store: StoreShape, cardId: string) {
  const lru = (store.__lru ?? []).filter((id) => id !== cardId);
  lru.push(cardId);
  while (lru.length > LRU_CAP) {
    const evict = lru.shift();
    if (evict) delete store[evict];
  }
  store.__lru = lru;
}

function getCardEntry(store: StoreShape, cardId: string): Record<string, string> {
  const entry = store[cardId];
  if (!entry || Array.isArray(entry)) return {};
  return entry;
}

export interface UseCardTabActivity {
  hasUpdates: (tabKey: string) => boolean;
  markSeen: (tabKey: string) => void;
}

export function useCardTabActivity(cardId: string): UseCardTabActivity {
  const [latestActivity, setLatestActivity] = useState<Record<string, string>>({});
  const [seenVersion, setSeenVersion] = useState(0);

  // Stamp the card's first-visit baseline once, when the hook mounts for a
  // card that has never been visited before. Tabs the user has never opened
  // fall back to this timestamp for the "what counts as new" comparison.
  useEffect(() => {
    const store = readStore();
    const entry = getCardEntry(store, cardId);
    if (!entry[FIRST_VISIT_KEY]) {
      entry[FIRST_VISIT_KEY] = new Date().toISOString();
      store[cardId] = entry;
      bumpLru(store, cardId);
      writeStore(store);
      setSeenVersion((n) => n + 1);
    }
  }, [cardId]);

  useEffect(() => {
    let cancelled = false;
    setLatestActivity({});
    api
      .get<EventEntry[]>(
        `/cards/${cardId}/history?page=1&page_size=${HISTORY_PAGE_SIZE}`,
      )
      .then((events) => {
        if (cancelled) return;
        const latest: Record<string, string> = {};
        for (const e of events) {
          if (!e.created_at) continue;
          const tabKey = EVENT_TAB_MAP[e.event_type];
          if (!tabKey) continue;
          const current = latest[tabKey];
          if (!current || e.created_at > current) {
            latest[tabKey] = e.created_at;
          }
        }
        setLatestActivity(latest);
      })
      .catch(() => {
        if (!cancelled) setLatestActivity({});
      });
    return () => {
      cancelled = true;
    };
  }, [cardId]);

  const cardEntry = useMemo(() => {
    return getCardEntry(readStore(), cardId);
    // seenVersion intentionally in deps: markSeen bumps it to force re-read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardId, seenVersion]);

  const hasUpdates = useCallback(
    (tabKey: string): boolean => {
      const firstVisit = cardEntry[FIRST_VISIT_KEY];
      if (!firstVisit) return false; // card has never been visited
      const latest = latestActivity[tabKey];
      if (!latest) return false;
      // Tabs the user has explicitly opened use that timestamp; otherwise
      // fall back to the card-wide first-visit baseline.
      const baseline = cardEntry[tabKey] || firstVisit;
      return latest > baseline;
    },
    [latestActivity, cardEntry],
  );

  const markSeen = useCallback(
    (tabKey: string) => {
      const store = readStore();
      const existing = getCardEntry(store, cardId);
      existing[tabKey] = new Date().toISOString();
      store[cardId] = existing;
      bumpLru(store, cardId);
      writeStore(store);
      setSeenVersion((n) => n + 1);
    },
    [cardId],
  );

  return { hasUpdates, markSeen };
}
