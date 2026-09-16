const REQUEST_TIMEOUT_MS = 10_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function requestSignal(signal?: AbortSignal | null) {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const res = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(init?.headers || {}),
      },
      cache: "no-store",
      signal: requestSignal(init?.signal),
    });
    const contentType = res.headers.get("content-type") || "";
    const body = contentType.includes("application/json")
      ? await res.json()
      : null;
    if (!res.ok) {
      throw new ApiError(
        body?.error?.message || `CardioFlow request failed (${res.status}).`,
        res.status,
        body?.error?.code,
      );
    }
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError(
        "The CardioFlow service did not respond in time. Check the local API and retry.",
      );
    }
    throw new ApiError(
      "CardioFlow could not reach its local service. Check that the API is running, then retry.",
    );
  }
}
