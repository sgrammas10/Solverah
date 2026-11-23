/**
 * TraitPreferencesPage.test.tsx -- the /trait-preferences retake door. The step itself
 * is covered in TraitPreferencesStep.test.tsx; here it is a stub.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import TraitPreferencesPage from "./TraitPreferencesPage";
import { RETAKE_SITTING_NOTE } from "./traitPreferencesCopy";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  stepProps: null as null | { skipLabel?: string },
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("./TraitPreferencesStep", () => ({
  default: (props: { skipLabel?: string; onFinished: (o: "saved" | "skipped") => void }) => {
    mocks.stepProps = props;
    return (
      <div>
        <button type="button" onClick={() => props.onFinished("saved")}>
          Save stub
        </button>
        <button type="button" onClick={() => props.onFinished("skipped")}>
          Cancel stub
        </button>
      </div>
    );
  },
}));

beforeEach(() => {
  mocks.navigate.mockReset();
  mocks.stepProps = null;
});

function renderPage() {
  render(
    <MemoryRouter>
      <TraitPreferencesPage />
    </MemoryRouter>
  );
}

describe("TraitPreferencesPage", () => {
  it("labels the way out 'Cancel', since leaving keeps the earlier answers", () => {
    renderPage();
    expect(mocks.stepProps?.skipLabel).toBe("Cancel");
  });

  it("tells the user when a change reaches the Situation Report", () => {
    renderPage();
    expect(screen.getByText(RETAKE_SITTING_NOTE)).toBeInTheDocument();
    expect(RETAKE_SITTING_NOTE).toMatch(/Situation Report/);
  });

  it("the note is true for a first answer as well as a later change (G49)", () => {
    // The tolerance pin (situation_report_service, D-15): a report with no tolerance
    // answers yet takes the first ones at once; only a LATER change waits for a
    // retake and the report's Re-read. The old note promised the wait for both.
    expect(RETAKE_SITTING_NOTE).toMatch(/first answers you save here straight away/);
    expect(RETAKE_SITTING_NOTE).toMatch(/later change reaches it only after you retake/);
    expect(RETAKE_SITTING_NOTE).not.toMatch(/picks them up the next time/);
  });

  it("returns to Work Pulse after a save, flagged so it can say 'saved' (G48)", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Save stub" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse", {
      state: { traitPreferencesSaved: true },
    });
  });

  it("returns to Work Pulse on cancel with no 'saved' flag (G48)", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Cancel stub" }));
    expect(mocks.navigate).toHaveBeenCalledTimes(1);
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse");
  });
});
