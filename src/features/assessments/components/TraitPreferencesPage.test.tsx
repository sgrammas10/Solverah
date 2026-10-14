/**
 * TraitPreferencesPage.test.tsx -- the /trait-preferences retake door. The step itself
 * is covered in TraitPreferencesStep.test.tsx; here it is a stub.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import TraitPreferencesPage from "./TraitPreferencesPage";

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

  it("returns to Work Pulse after a save", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Save stub" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse");
  });

  it("returns to Work Pulse on cancel", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Cancel stub" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse");
  });
});
