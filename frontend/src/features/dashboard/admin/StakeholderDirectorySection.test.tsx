import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/api/client", () => ({
  api: { get: vi.fn() },
}));

vi.mock("@/hooks/useResolveLabel", () => ({
  useResolveLabel: () => (label: string) => label,
  useResolveMetaLabel: () => (label: string) => label,
}));

// The widget renders StakeholderHoverCard around each user chip; stub it to
// keep this test focused on the directory tree.
vi.mock("@/components/StakeholderHoverCard", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { api } from "@/api/client";
import StakeholderDirectorySection from "./StakeholderDirectorySection";

const DIRECTORY = {
  card_types: [
    {
      type_key: "Application",
      type_label: "Application",
      type_icon: "apps",
      type_color: "#0f7eb5",
      holders_count: 2,
      roles: [
        {
          role_key: "responsible",
          role_label: "Application Owner",
          role_color: "#1976d2",
          role_translations: {},
          users: [
            { user_id: "u-alice", display_name: "Alice", email: "a@x", card_count: 2 },
            { user_id: "u-bob", display_name: "Bob", email: "b@x", card_count: 1 },
          ],
        },
      ],
    },
    {
      type_key: "BusinessProcess",
      type_label: "Business Process",
      type_icon: "route",
      type_color: "#028f00",
      holders_count: 1,
      roles: [
        {
          role_key: "responsible",
          role_label: "Process Owner",
          role_color: "#1976d2",
          role_translations: {},
          users: [
            { user_id: "u-bob", display_name: "Bob", email: "b@x", card_count: 1 },
          ],
        },
      ],
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
});

function renderSection() {
  return render(
    <MemoryRouter>
      <StakeholderDirectorySection />
    </MemoryRouter>,
  );
}

describe("StakeholderDirectorySection", () => {
  it("fetches and renders the card-type tree; first type auto-expands", async () => {
    vi.mocked(api.get).mockResolvedValue(DIRECTORY);
    renderSection();

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith("/reports/stakeholder-directory");
    });

    // Both card types appear as rows. `useResolveMetaLabel` falls back to
    // the type_key (the stub takes the first arg), so we match those.
    expect(await screen.findByText("Application")).toBeInTheDocument();
    expect(screen.getByText("BusinessProcess")).toBeInTheDocument();

    // The first card type is auto-expanded → its role + users render.
    expect(screen.getByText("Application Owner")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();

    // The second card type is collapsed by default — its role doesn't show.
    expect(screen.queryByText("Process Owner")).not.toBeInTheDocument();
  });

  it("expands a card type on click to reveal its role chips", async () => {
    vi.mocked(api.get).mockResolvedValue(DIRECTORY);
    renderSection();
    await screen.findByText("Application");

    // BusinessProcess starts collapsed.
    expect(screen.queryByText("Process Owner")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("BusinessProcess"));
    expect(await screen.findByText("Process Owner")).toBeInTheDocument();
  });

  it("renders the empty state when no stakeholders exist", async () => {
    vi.mocked(api.get).mockResolvedValue({ card_types: [] });
    renderSection();

    expect(
      await screen.findByText("No stakeholders are assigned yet."),
    ).toBeInTheDocument();
  });
});
