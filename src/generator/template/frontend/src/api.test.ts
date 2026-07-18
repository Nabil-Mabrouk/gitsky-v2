import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function headersOf(fetchMock: ReturnType<typeof vi.fn>, call: number): Headers {
  return (fetchMock.mock.calls[call][1] as RequestInit).headers as Headers;
}

describe("apiFetch", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("attache le Bearer access token quand il est présent", async () => {
    localStorage.setItem("access_token", "tok-1");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/content/tutorials");

    expect(headersOf(fetchMock, 0).get("Authorization")).toBe("Bearer tok-1");
  });

  it("n'envoie aucun header Authorization sans token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/public");

    expect(headersOf(fetchMock, 0).get("Authorization")).toBeNull();
  });

  it("rafraîchit puis rejoue une seule fois la requête sur 401 (Chap 7)", async () => {
    localStorage.setItem("access_token", "stale");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 })) // requête initiale
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh" })) // refresh
      .mockResolvedValueOnce(jsonResponse({ data: 1 })); // rejeu
    vi.stubGlobal("fetch", fetchMock);

    const res = await apiFetch("/api/content/tutorials");

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/auth/refresh");
    expect(localStorage.getItem("access_token")).toBe("fresh");
    expect(headersOf(fetchMock, 2).get("Authorization")).toBe("Bearer fresh");
    expect(res.status).toBe(200);
  });

  it("ne rejoue pas la requête si le refresh échoue", async () => {
    localStorage.setItem("access_token", "stale");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 })); // refresh KO
    vi.stubGlobal("fetch", fetchMock);

    const res = await apiFetch("/api/content/tutorials");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(res.status).toBe(401);
  });
});
