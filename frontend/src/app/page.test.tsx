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

  it("opens the deterministic GERD simulation without implying custom generation", async () => {
    mockedApi.mockImplementation(async (path, init) => {
      if (path === "/api/fixtures") return fixtures as never;
      if (path === "/api/encounters" && !init) return [] as never;
      return { encounter: { id: "enc_gerd" } } as never;
    });

    render(<Home />);
    const button = await screen.findByRole("button", { name: "Open simulated GERD encounter" });
    fireEvent.click(button);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/encounters/enc_gerd"));
    expect(mockedApi).toHaveBeenCalledWith(
      "/api/encounters",
      expect.objectContaining({ body: JSON.stringify({ fixture_id: "gerd_simulated" }) }),
    );
  });

  it("validates custom transcript format locally without sending transcript data", async () => {
    mockedApi.mockImplementation(async (path) =>
      (path === "/api/fixtures" ? fixtures : []) as never,
    );

    render(<Home />);
    await screen.findByRole("button", { name: "Open guided HFrEF demo" });
    fireEvent.click(screen.getByText("Check a custom synthetic transcript"));

    expect(screen.getByText(/Arbitrary extraction is not available/)).toBeVisible();
    expect(screen.getByText(/Do not enter real patient information/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Synthetic transcript"), {
      target: {
        value:
          "CLINICIAN: What brings you in today?\nPATIENT: This is fictional test content.",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Check transcript format" }));

    expect(screen.getByRole("status")).toHaveTextContent("Text was not sent or saved");
    expect(mockedApi.mock.calls.filter(([, init]) => init)).toHaveLength(0);
  });
});
