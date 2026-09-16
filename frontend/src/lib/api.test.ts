import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("returns same-origin JSON responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api<{ status: string }>("/api/health")).resolves.toEqual({
      status: "ok",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("preserves structured domain errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "unknown_fixture", message: "Fixture not found" },
          }),
          { status: 404, headers: { "content-type": "application/json" } },
        ),
      ),
    );

    await expect(api("/api/encounters")).rejects.toMatchObject({
      name: "ApiError",
      message: "Fixture not found",
      status: 404,
      code: "unknown_fixture",
    } satisfies Partial<ApiError>);
  });

  it("maps connection failures to a useful local-service error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(api("/api/health")).rejects.toThrow(
      "CardioFlow could not reach its local service",
    );
  });
});
