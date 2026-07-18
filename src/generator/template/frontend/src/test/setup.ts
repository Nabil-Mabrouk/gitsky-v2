// Setup global des tests Vitest : ajoute les matchers DOM de jest-dom
// (toBeInTheDocument, toHaveTextContent…) et nettoie le DOM entre chaque test.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
