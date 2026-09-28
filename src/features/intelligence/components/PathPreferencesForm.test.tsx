/**
 * PathPreferencesForm.test.tsx
 *
 * Regression coverage for the "Adjust search preferences" re-entry defect: the
 * form used to start every one of its three questions blank even when the
 * user already had `path_preferences` saved. The page (owned elsewhere) hands
 * this form only `onComplete`, so it reads the same profile document the page
 * already has cached via `useProfile()` -- mocked here the way
 * `FocusTypePage.test.tsx` and `PathIntelligencePage.test.tsx` mock it.
 *
 * Options are selected by role and `aria-pressed`, never by their prose:
 * Julie owns the copy.
 */
import { render, screen, fireEvent } from "@testing-library/react";

import PathPreferencesForm from "./PathPreferencesForm";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
  updateProfileData: vi.fn(),
  profile: {} as Record<string, unknown>,
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

vi.mock("../../profile/useProfileActions", () => ({
  useProfileActions: () => ({ updateProfileData: mocks.updateProfileData }),
}));

vi.mock("../../profile/useProfile", () => ({
  useProfile: () => ({ data: mocks.profile, isLoading: false }),
}));

function pressedOption(): HTMLElement | null {
  return document.querySelector('[aria-pressed="true"]');
}

function nextButton(): HTMLElement {
  return screen.getByRole("button", { name: /next|see my paths/i });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.profile = {};
});

describe("PathPreferencesForm - first visit, nothing saved", () => {
  it("opens every question with nothing selected", () => {
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    expect(pressedOption()).toBeNull();
    expect(nextButton()).toBeDisabled();
  });
});

describe("PathPreferencesForm - re-entry with saved preferences", () => {
  beforeEach(() => {
    mocks.profile = {
      path_preferences: {
        move_intent: "adjacent",
        seniority_intent: "move_up",
        priority: "learning_growth",
      },
    };
  });

  it("opens the first step with the stored move_intent option pressed", () => {
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    const pressed = pressedOption();
    expect(pressed).not.toBeNull();
    expect(pressed).toHaveTextContent(/adjacent/i);
    // Already answered, so advancing does not require a fresh tap.
    expect(nextButton()).toBeEnabled();
  });

  it("opens the second step with the stored seniority_intent option pressed", () => {
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    fireEvent.click(nextButton());
    const pressed = pressedOption();
    expect(pressed).not.toBeNull();
    expect(pressed).toHaveTextContent(/looking to move up/i);
  });

  it("opens the third step with the stored priority option pressed", () => {
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    fireEvent.click(nextButton());
    fireEvent.click(nextButton());
    const pressed = pressedOption();
    expect(pressed).not.toBeNull();
    expect(pressed).toHaveTextContent(/learning & growth/i);
  });

  it("still lets a different option be chosen, replacing the stored one", () => {
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /fresh direction/i }));
    expect(pressedOption()).toHaveTextContent(/fresh direction/i);
  });
});

// ─── W-13: exactly one option may read as selected ─────────────────────────
//
// The third browser test: after moving the choice from "Fresh direction" to
// "Stay in my field", the old option kept a faint green tint and no tick. The
// state was never wrong -- `selected` is an equality against one stored value
// -- so the first test below passed before the fix and is here to pin that.
// The defect was the palette: green was the selected signal AND the hover
// signal, so the pointer resting anywhere on its way down the list lit a
// second option in the colour that means "chosen".

describe("PathPreferencesForm - only one option reads selected", () => {
  function optionButtons(): HTMLElement[] {
    return Array.from(document.querySelectorAll<HTMLElement>("[aria-pressed]"));
  }

  it("moves aria-pressed to the option just clicked and leaves none behind", () => {
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /fresh direction/i }));
    fireEvent.click(screen.getByRole("button", { name: /stay in my field/i }));

    const pressed = optionButtons().filter(
      (b) => b.getAttribute("aria-pressed") === "true"
    );
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent(/stay in my field/i);
  });

  it("gives the tick to the selected option alone", () => {
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /fresh direction/i }));
    fireEvent.click(screen.getByRole("button", { name: /stay in my field/i }));

    const ticked = optionButtons().filter((b) => (b.textContent ?? "").includes("✓"));
    expect(ticked).toHaveLength(1);
    expect(ticked[0]).toHaveTextContent(/stay in my field/i);
  });

  it("reserves the selected palette for the selected option, hover included", () => {
    // The regression. An unselected option must carry NO forest-green class at
    // all -- not on rest, and not behind a `hover:` prefix. Green on this
    // control means chosen, and a second green option is the defect however it
    // was painted there.
    render(<PathPreferencesForm onComplete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /fresh direction/i }));
    fireEvent.click(screen.getByRole("button", { name: /stay in my field/i }));

    for (const button of optionButtons()) {
      const green = Array.from(button.classList).filter((c) => c.includes("forest"));
      if (button.getAttribute("aria-pressed") === "true") {
        expect(green).toEqual(
          expect.arrayContaining(["border-forest-dark", "bg-forest-pale"])
        );
      } else {
        expect(green).toEqual([]);
      }
    }
  });
});
