import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Composer from "./Composer";
import { apiFetch } from "../api";

vi.mock("../api", () => ({ apiFetch: vi.fn() }));
const mockApi = vi.mocked(apiFetch);

const CATALOG = {
  singers: [{ name: "Slah", voice: "warm-baritone", avatar: "🎤", tagline: "chaud" }],
  themes: [{ name: "Fête" }],
  rhythms: [{ name: "Allala", bpm: 140 }],
  instruments: [
    { name: "Mezoued", family: "vent" },
    { name: "Darbouka", family: "percussion" },
  ],
};

function jsonRes(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response;
}
const notFound = (): Response => jsonRes({}, false, 404);

// Au montage, Composer appelle apiFetch deux fois : /api/songs/catalog puis
// /api/agent-services/credits (détection de la génération, absente en T1).
function mountMocks(creditsAvailable: boolean) {
  mockApi.mockResolvedValueOnce(jsonRes(CATALOG));
  mockApi.mockResolvedValueOnce(creditsAvailable ? jsonRes({ balance: 10 }) : notFound());
}

describe("Composer", () => {
  beforeEach(() => mockApi.mockReset());

  it("charge le catalogue et affiche les chanteurs", async () => {
    mountMocks(false);
    render(<Composer />);
    expect(await screen.findByText("Slah")).toBeInTheDocument();
  });

  it("désactive Concept/Generate quand l'agentic est indisponible (T1)", async () => {
    mountMocks(false);
    render(<Composer />);
    await screen.findByText("Slah");
    expect(screen.getByText("Concept")).toBeDisabled();
    expect(screen.getByText("Generate")).toBeDisabled();
  });

  it("compose une spec et l'envoie à l'API au clic sur Sauvegarder", async () => {
    mountMocks(false);
    mockApi.mockResolvedValueOnce(
      jsonRes({ id: 7, title: "Ma chanson", status: "draft", structure: [] }),
    );
    render(<Composer />);
    await screen.findByText("Slah");

    fireEvent.click(screen.getByText("Slah"));
    fireEvent.change(screen.getByLabelText("Thème"), { target: { value: "Fête" } });
    fireEvent.change(screen.getByLabelText("Rythme"), { target: { value: "Allala" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Mezoued" }));
    fireEvent.click(screen.getByText("+ refrain"));

    fireEvent.click(screen.getByText("Sauvegarder"));

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(3));
    const [path, opts] = mockApi.mock.calls[2];
    expect(path).toBe("/api/songs");
    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body.singer).toBe("Slah");
    expect(body.structure).toEqual(["refrain"]);
    expect(await screen.findByRole("status")).toHaveTextContent("#7");
  });

  it("réordonne la structure avec les flèches", async () => {
    mountMocks(false);
    render(<Composer />);
    await screen.findByText("Slah");

    fireEvent.click(screen.getByText("+ intro"));
    fireEvent.click(screen.getByText("+ refrain"));
    fireEvent.click(screen.getByLabelText("Monter refrain"));

    const items = screen.getAllByTestId("section-item").map((n) => n.textContent);
    expect(items[0]).toContain("refrain");
    expect(items[1]).toContain("intro");
  });

  it("génère les paroles avec Concept quand l'agentic est disponible (T2)", async () => {
    mountMocks(true);
    mockApi.mockResolvedValueOnce(
      jsonRes({ id: 1, status: "completed", result: { output: "Ya leyla ya leyl" } }),
    );
    render(<Composer />);
    await screen.findByText("Slah");
    fireEvent.click(screen.getByText("Slah"));

    const concept = screen.getByText("Concept");
    expect(concept).not.toBeDisabled();
    fireEvent.click(concept);

    expect(await screen.findByText(/Ya leyla/)).toBeInTheDocument();
  });

  it("Generate lance un job et affiche le lecteur audio après polling (T2)", async () => {
    mountMocks(true);
    mockApi
      .mockResolvedValueOnce(jsonRes({ id: 42, status: "pending", result: null })) // execute song
      .mockResolvedValueOnce(
        jsonRes({ id: 42, status: "completed", result: { suno: { audio_url: "https://cdn/x.mp3" } } }),
      ) // poll
      .mockResolvedValueOnce(jsonRes({ balance: 7 })); // refresh crédits
    render(<Composer />);
    await screen.findByText("Slah");
    fireEvent.click(screen.getByText("Slah"));

    fireEvent.click(screen.getByText("Generate"));

    const audio = await screen.findByTestId("audio-player");
    expect(audio).toHaveAttribute("src", "https://cdn/x.mp3");
  });
});
