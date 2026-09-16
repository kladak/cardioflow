import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";
import { api } from "@/lib/api";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/api", () => ({
  api: vi.fn(),
}));

const fixtures = [
  {
    id: "hfref_golden",
    title: "Golden encounter",
    description: "Complete deterministic path",
    purpose: "golden",
  },
  {
    id: "hfref_ambiguous",
    title: "Adversarial encounter",
    description: "Incomplete evidence path",
    purpose: "adversarial",
  },
  {
    id: "gerd_simulated",
    title: "GERD simulation",
    description: "Synthetic consultation path",
    purpose: "simulation",
  },
];

const mockedApi = vi.mocked(api);

describe("CardioFlow landing workflow", () => {
  beforeEach(() => {
    push.mockReset();
    mockedApi.mockReset();
  });

  it("surfaces initial API failure and recovers through retry", async () => {
    let available = false;
    mockedApi.mockImplementation(async (path) => {
      if (!available) throw new Error("Local API unavailable");
      return (path === "/api/fixtures" ? fixtures : []) as never;
    });

    render(<Home />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Local API unavailable",
    );
    expect(
      screen.getByRole("button", { name: "Open guided HFrEF demo" }),
    ).toBeDisabled();

    available = true;
    fireEvent.click(screen.getByRole("button", { name: "Retry connection" }));

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Open guided HFrEF demo" }),
      ).toBeEnabled(),
    );
  });

  it("creates the golden encounter and navigates", async () => {
    mockedApi.mockImplementation(async (path, init) => {
      if (path === "/api/fixtures") return fixtures as never;
      if (path === "/api/encounters" && !init) return [] as never;
      return { encounter: { id: "enc_demo" } } as never;
    });

    render(<Home />);
    const button = await screen.findByRole("button", {
      name: "Open guided HFrEF demo",
    });
    fireEvent.click(button);

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/encounters/enc_demo"),
    );
    expect(button).toHaveTextContent("Open guided HFrEF demo");
  });

  it("clears busy state after failed encounter creation", async () => {
    mockedApi.mockImplementation(async (path, init) => {
      if (path === "/api/fixtures") return fixtures as never;
      if (path === "/api/encounters" && !init) return [] as never;
      throw new Error("Creation failed");
    });

    render(<Home />);
    const button = await screen.findByRole("button", {
      name: "Open guided HFrEF demo",
    });
    fireEvent.click(button);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Creation failed",
    );
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent("Open guided HFrEF demo");
    expect(push).not.toHaveBeenCalled();
  });

  it("discloses the deterministic fallback and opens the GERD simulation", async () => {
    mockedApi.mockImplementation(async (path, init) => {
      if (path === "/api/fixtures") return fixtures as never;
      if (path === "/api/encounters" && !init) return [] as never;
      return { encounter: { id: "enc_gerd" } } as never;
    });

    render(<Home />);
    await screen.findByRole("button", { name: "Open simulated GERD encounter" });
    fireEvent.click(screen.getByRole("button", { name: "Describe a scenario" }));

    expect(screen.getByText(/Live transcript generation is not configured/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Synthetic patient situation"), {
      target: { value: "Burning after meals" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open deterministic fallback" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/encounters/enc_gerd"));
    expect(mockedApi).toHaveBeenCalledWith(
      "/api/encounters",
      expect.objectContaining({ body: JSON.stringify({ fixture_id: "gerd_simulated" }) }),
    );
  });
});
