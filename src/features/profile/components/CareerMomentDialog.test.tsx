import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import CareerMomentDialog from "./CareerMomentDialog";
import { createQueryClient } from "../../../shared/api/queryClient";
import { profileKeys } from "../useProfile";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ user: { id: "7" }, fetchWithAuth: mocks.fetchWithAuth }),
}));

const LABELS = [
  "Something's off at work",
  "Deciding whether to stay or go",
  "Looking for my next role",
  "Between jobs",
  "Looking for my first job",
  "Understanding how I work",
];

function renderDialog(
  careerStatus: string | null | undefined = null,
  client = createQueryClient(),
) {
  const onNotNow = vi.fn();
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <CareerMomentDialog careerStatus={careerStatus} onNotNow={onNotNow} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onNotNow, onClose, client };
}

/** The bodies sent to PATCH /me/onboarding, parsed. */
const onboardingBodies = () =>
  mocks.fetchWithAuth.mock.calls
    .filter(([path]) => path === "/me/onboarding")
    .map(([, init]) => JSON.parse(init.body));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchWithAuth.mockImplementation((_path: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body));
    return Promise.resolve({
      career_moment: body.career_moment ?? null,
      career_status: body.career_status ?? null,
      own_words: body.own_words ?? null,
    });
  });
});

describe("CareerMomentDialog - step 1", () => {
  it("offers the six career moments as large choices", () => {
    renderDialog();

    expect(screen.getByRole("dialog", { name: "What brings you here?" })).toBeInTheDocument();
    for (const label of LABELS) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("puts focus on the first choice", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: LABELS[0] })).toHaveFocus();
  });

  it.each([
    ["Something's off at work", "off_at_work"],
    ["Deciding whether to stay or go", "stay_or_go"],
    ["Between jobs", "between_jobs"],
    ["Looking for my first job", "first_job"],
  ])("%s saves straight away, with no follow-up", async (label, id) => {
    renderDialog(null);

    fireEvent.click(screen.getByRole("button", { name: label }));

    expect(screen.queryByText("Are you working right now?")).toBeNull();
    await screen.findByRole("dialog", { name: "In your own words" });
    expect(onboardingBodies()).toEqual([{ career_moment: id }]);
  });

  it.each([
    ["Looking for my next role", "job_hunting"],
    ["Understanding how I work", "curious"],
  ])("%s asks whether the user is working, then saves both", async (label, id) => {
    renderDialog(null);

    fireEvent.click(screen.getByRole("button", { name: label }));

    expect(screen.getByText("Are you working right now?")).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Yes" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Not right now" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "I haven't had my first job yet" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Not right now" }));

    await screen.findByRole("dialog", { name: "In your own words" });
    expect(onboardingBodies()).toEqual([{ career_moment: id, career_status: "between_jobs" }]);
  });

  it("skips the follow-up when the profile already has a status", async () => {
    renderDialog("employed");

    fireEvent.click(screen.getByRole("button", { name: "Looking for my next role" }));

    expect(screen.queryByText("Are you working right now?")).toBeNull();
    await screen.findByRole("dialog", { name: "In your own words" });
    expect(onboardingBodies()).toEqual([{ career_moment: "job_hunting" }]);
  });

  it("does not open the follow-up on an undefined status as if one were set", () => {
    // undefined is "unknown", which must still ask rather than guess.
    renderDialog(undefined);
    fireEvent.click(screen.getByRole("button", { name: "Understanding how I work" }));
    expect(screen.getByText("Are you working right now?")).toBeInTheDocument();
  });

  it("'Not now' snoozes without saving", () => {
    const { onNotNow, onClose } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(onNotNow).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("Esc acts as 'Not now'", () => {
    const { onNotNow } = renderDialog();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onNotNow).toHaveBeenCalledTimes(1);
  });

  it("keeps Tab inside the dialog", () => {
    renderDialog();
    const notNow = screen.getByRole("button", { name: "Not now" });
    const first = screen.getByRole("button", { name: LABELS[0] });

    notNow.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(first).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(notNow).toHaveFocus();
  });

  it("shows a plain error and stays on step 1 when the save fails", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("invalid_career_moment"));
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Between jobs" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't save that");
    expect(screen.getByRole("dialog", { name: "What brings you here?" })).toBeInTheDocument();
  });

  it("writes the saved answers into the cached profile document", async () => {
    const client = createQueryClient();
    client.setQueryData(profileKeys.document(), { summary: "s" });
    renderDialog(null, client);

    fireEvent.click(screen.getByRole("button", { name: "Something's off at work" }));

    await screen.findByRole("dialog", { name: "In your own words" });
    expect(client.getQueryData(profileKeys.document())).toEqual({
      summary: "s",
      career_moment: "off_at_work",
    });
  });
});

describe("CareerMomentDialog - step 2", () => {
  async function toStepTwo(careerStatus: string | null = null) {
    const handles = renderDialog(careerStatus);
    fireEvent.click(screen.getByRole("button", { name: "Between jobs" }));
    await screen.findByRole("dialog", { name: "In your own words" });
    return handles;
  }

  it("asks one optional question, with the helper line and no promise about who sees it", async () => {
    await toStepTwo();

    const box = screen.getByLabelText("What's going on, in a sentence or two?");
    expect(box).toHaveFocus();
    expect(box).toHaveAttribute("maxLength", "1000");
    expect(
      screen.getByText(
        "Optional. It stays in your words; we'll show it back to you, and it's never scored.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/employer|private|only you/i)).toBeNull();
  });

  it("Save sends the trimmed text and closes", async () => {
    const { onClose } = await toStepTwo();

    fireEvent.change(screen.getByLabelText("What's going on, in a sentence or two?"), {
      target: { value: "  My manager keeps moving the goalposts.  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onboardingBodies()[1]).toEqual({ own_words: "My manager keeps moving the goalposts." });
  });

  it("Save is off while the box is blank", async () => {
    await toStepTwo();

    fireEvent.change(screen.getByLabelText("What's going on, in a sentence or two?"), {
      target: { value: "   " },
    });

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("Skip closes without saving anything more", async () => {
    const { onClose, onNotNow } = await toStepTwo();

    fireEvent.click(screen.getByRole("button", { name: "Skip" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onNotNow).not.toHaveBeenCalled();
    expect(onboardingBodies()).toHaveLength(1);
  });

  it("Esc acts as 'Skip' on step 2, not 'Not now'", async () => {
    const { onClose, onNotNow } = await toStepTwo();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onNotNow).not.toHaveBeenCalled();
  });
});
