// The `/vitest` entry point, not the bare one: the bare entry's types
// (`types/index.d.ts`) do `/// <reference types="jest" />`, which drags
// @types/jest into the program and replaces vitest's two-argument
// `expect(actual, message)` with jest's one-argument form. This entry
// augments vitest's own `Assertion` interface instead.
import "@testing-library/jest-dom/vitest";

// JSDOM does not implement window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
