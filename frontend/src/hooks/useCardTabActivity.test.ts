import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

vi.mock("@/api/client", () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from "@/api/client";
import { useCardTabActivity } from "./useCardTabActivity";

const CARD_A = "card-aaaaaaaa";
const CARD_B = "card-bbbbbbbb";
const STORAGE_KEY = "turbo-ea.cardTabsSeen";

function isoMinus(seconds: number): string {
  return new Date(Date.now() - seconds * 1000).toISOString();
}

beforeEach(() => {
  vi.mocked(api.get).mockReset();
  localStorage.clear();
});

describe("useCardTabActivity", () => {
  it("returns no dots on a first-ever visit, even when activity exists", async () => {
    // All activity precedes the (just-stamped) first-visit baseline.
    vi.mocked(api.get).mockResolvedValueOnce([
      { id: "1", event_type: "comment.created", created_at: isoMinus(60) },
      { id: "2", event_type: "card.updated", created_at: isoMinus(120) },
    ]);

    const { result } = renderHook(() => useCardTabActivity(CARD_A));

    await waitFor(() => {
      expect(api.get).toHaveBeenCalled();
    });

    expect(result.current.hasUpdates("comments")).toBe(false);
    expect(result.current.hasUpdates("card")).toBe(false);
    expect(result.current.hasUpdates("history")).toBe(false);
  });

  it("stamps a first-visit baseline that persists across remounts", async () => {
    vi.mocked(api.get).mockResolvedValue([]);
    const { unmount } = renderHook(() => useCardTabActivity(CARD_A));
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    const firstSnapshot = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    const first = firstSnapshot[CARD_A].__first;
    expect(first).toBeDefined();

    unmount();

    // A second mount must NOT overwrite the first-visit timestamp.
    renderHook(() => useCardTabActivity(CARD_A));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    const secondSnapshot = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(secondSnapshot[CARD_A].__first).toBe(first);
  });

  it("shows dots on tabs the user has never opened when activity post-dates first visit", async () => {
    // User A's first visit was a while ago; comment came in afterwards.
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        [CARD_A]: { __first: isoMinus(300) },
        __lru: [CARD_A],
      }),
    );

    vi.mocked(api.get).mockResolvedValueOnce([
      { id: "1", event_type: "comment.created", created_at: isoMinus(60) },
      { id: "2", event_type: "stakeholder.added", created_at: isoMinus(45) },
    ]);

    const { result } = renderHook(() => useCardTabActivity(CARD_A));

    await waitFor(() => {
      expect(result.current.hasUpdates("comments")).toBe(true);
    });
    expect(result.current.hasUpdates("stakeholders")).toBe(true);
    // No risk events in the fetch → no dot.
    expect(result.current.hasUpdates("risks")).toBe(false);
  });

  it("does not show a dot when activity precedes the first visit", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        [CARD_A]: { __first: isoMinus(30) },
        __lru: [CARD_A],
      }),
    );

    vi.mocked(api.get).mockResolvedValueOnce([
      { id: "1", event_type: "comment.created", created_at: isoMinus(120) },
    ]);

    const { result } = renderHook(() => useCardTabActivity(CARD_A));

    await waitFor(() => {
      expect(api.get).toHaveBeenCalled();
    });

    expect(result.current.hasUpdates("comments")).toBe(false);
  });

  it("markSeen clears the dot for that tab without affecting others", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        [CARD_A]: { __first: isoMinus(300) },
        __lru: [CARD_A],
      }),
    );

    vi.mocked(api.get).mockResolvedValueOnce([
      { id: "1", event_type: "stakeholder.added", created_at: isoMinus(30) },
      { id: "2", event_type: "comment.created", created_at: isoMinus(30) },
    ]);

    const { result } = renderHook(() => useCardTabActivity(CARD_A));

    await waitFor(() => {
      expect(result.current.hasUpdates("stakeholders")).toBe(true);
    });
    expect(result.current.hasUpdates("comments")).toBe(true);

    act(() => {
      result.current.markSeen("stakeholders");
    });

    expect(result.current.hasUpdates("stakeholders")).toBe(false);
    // Other tab still dotted.
    expect(result.current.hasUpdates("comments")).toBe(true);

    const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(persisted[CARD_A].stakeholders).toBeDefined();
    expect(persisted[CARD_A].comments).toBeUndefined();
    expect(persisted[CARD_A].__first).toBeDefined();
  });

  it("buckets various event types into the right tabs", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        [CARD_A]: { __first: isoMinus(500) },
        __lru: [CARD_A],
      }),
    );

    vi.mocked(api.get).mockResolvedValueOnce([
      { id: "1", event_type: "relation.created", created_at: isoMinus(10) },
      { id: "2", event_type: "document.added", created_at: isoMinus(10) },
      { id: "3", event_type: "risk.updated", created_at: isoMinus(10) },
      { id: "4", event_type: "file.uploaded", created_at: isoMinus(10) },
    ]);

    const { result } = renderHook(() => useCardTabActivity(CARD_A));

    await waitFor(() => {
      expect(result.current.hasUpdates("card")).toBe(true);
    });
    expect(result.current.hasUpdates("resources")).toBe(true);
    expect(result.current.hasUpdates("risks")).toBe(true);
    expect(result.current.hasUpdates("comments")).toBe(false);
    expect(result.current.hasUpdates("stakeholders")).toBe(false);
  });

  it("evicts oldest cards from the LRU when capacity is exceeded", async () => {
    vi.mocked(api.get).mockResolvedValue([]);

    // Seed the store with 200 cards.
    const seeded: Record<string, Record<string, string>> = {};
    const lru: string[] = [];
    for (let i = 0; i < 200; i++) {
      const id = `card-${i.toString().padStart(4, "0")}`;
      seeded[id] = { __first: isoMinus(1000) };
      lru.push(id);
    }
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...seeded, __lru: lru }),
    );

    renderHook(() => useCardTabActivity("card-NEW"));

    await waitFor(() => {
      const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
      expect(persisted["card-NEW"]).toBeDefined();
    });

    const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(persisted["card-0000"]).toBeUndefined();
    expect(persisted.__lru.length).toBe(200);
    expect(persisted.__lru[persisted.__lru.length - 1]).toBe("card-NEW");
  });

  it("survives a malformed localStorage payload", async () => {
    localStorage.setItem(STORAGE_KEY, "{not json");

    vi.mocked(api.get).mockResolvedValueOnce([
      { id: "1", event_type: "comment.created", created_at: isoMinus(10) },
    ]);

    const { result } = renderHook(() => useCardTabActivity(CARD_A));

    await waitFor(() => {
      expect(api.get).toHaveBeenCalled();
    });

    // First visit just stamped — activity from 10s ago is older. No dot.
    expect(result.current.hasUpdates("comments")).toBe(false);

    act(() => {
      result.current.markSeen("comments");
    });
    const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(persisted[CARD_A].comments).toBeDefined();
    expect(persisted[CARD_A].__first).toBeDefined();
  });

  it("re-fetches when cardId changes", async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { id: "1", event_type: "comment.created", created_at: isoMinus(5) },
      ]);

    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        [CARD_B]: { __first: isoMinus(300) },
        __lru: [CARD_B],
      }),
    );

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useCardTabActivity(id),
      { initialProps: { id: CARD_A } },
    );

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledTimes(1);
    });
    expect(result.current.hasUpdates("comments")).toBe(false);

    rerender({ id: CARD_B });

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledTimes(2);
      expect(result.current.hasUpdates("comments")).toBe(true);
    });
  });
});
