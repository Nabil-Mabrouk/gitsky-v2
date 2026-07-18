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

describe("Composer", () => {
  beforeEach(() => mockApi.mockReset());

  it("charge le catalogue et affiche les chanteurs", async () => {
    mockApi.mockResolvedValueOnce(jsonRes(CATALOG));
    render(<Composer />);
    expect(await screen.findByText("Slah")).toBeInTheDocument();
  });

  it("compose une spec et l'envoie à l'API au clic sur Sauvegarder", async () => {
    mockApi
      .mockResolvedValueOnce(jsonRes(CATALOG)) // catalogue
      .mockResolvedValueOnce(jsonRes({ id: 7, title: "Ma chanson", status: "draft", structure: [] }));
    render(<Composer />);
    await screen.findByText("Slah");

    fireEvent.click(screen.getByText("Slah"));
    fireEvent.change(screen.getByLabelText("Thème"), { target: { value: "Fête" } });
    fireEvent.change(screen.getByLabelText("Rythme"), { target: { value: "Allala" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Mezoued" }));
    fireEvent.click(screen.getByText("+ refrain"));
    fireEvent.click(screen.getByText("+ couplet"));

    fireEvent.click(screen.getByText("Sauvegarder"));

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(2));
    const [path, opts] = mockApi.mock.calls[1];
    expect(path).toBe("/api/songs");
    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body.singer).toBe("Slah");
    expect(body.theme).toBe("Fête");
    expect(body.rhythm).toBe("Allala");
    expect(body.instruments).toContain("Mezoued");
    expect(body.structure).toEqual(["refrain", "couplet"]);
    expect(await screen.findByRole("status")).toHaveTextContent("#7");
  });

  it("réordonne la structure avec les flèches", async () => {
    mockApi.mockResolvedValueOnce(jsonRes(CATALOG));
    render(<Composer />);
    await screen.findByText("Slah");

    fireEvent.click(screen.getByText("+ intro"));
    fireEvent.click(screen.getByText("+ refrain"));
    fireEvent.click(screen.getByLabelText("Monter refrain"));

    const items = screen.getAllByTestId("section-item").map((n) => n.textContent);
    expect(items[0]).toContain("refrain");
    expect(items[1]).toContain("intro");
  });

  it("désactive Concept et Generate en T1", async () => {
    mockApi.mockResolvedValueOnce(jsonRes(CATALOG));
    render(<Composer />);
    await screen.findByText("Slah");
    expect(screen.getByText("Concept")).toBeDisabled();
    expect(screen.getByText("Generate")).toBeDisabled();
  });
});
