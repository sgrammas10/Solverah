/**
 * TraitPreferencesStep.test.tsx -- the tolerance and must-have step, over the real
 * hooks and a real query client (only `fetchWithAuth` is mocked, per
 * PulseCheckinPage.test.tsx's precedent).
 *
 * Two rules matter most: skipping sends nothing (an unanswered user must keep today's
 * behaviour), and nothing is pre-selected for a user who never answered (a default
 * tolerance would be a choice the user never made).
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import TraitPreferencesStep, { SAVE_ERROR_MESSAGE } from "./TraitPreferencesStep";
import { TRAIT_COPY } from "./traitPreferencesCopy";
import { createQueryClient } from "../../../shared/api/queryClient";
import { TRAIT_KEYS } from "../useTraitPreferences";
import type { TraitPreferencesDocument } from "../useTraitPreferences";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

const UNANSWERED: TraitPreferencesDocument = {
  answered: false,
  max_must_haves: 2,
  traits: TRAIT_KEYS.map((key) => ({
    dimension_key: key,
    under_steps: null,
    over_steps: null,
    must_have: false,
    answered: false,
  })),
};

const ANSWERED: TraitPreferencesDocument = {
  answered: true,
  max_must_haves: 2,
  traits: TRAIT_KEYS.map((key) => ({
    dimension_key: key,
    under_steps: key === "pace" ? 0 : 1,
    over_steps: 2,
    must_have: key === "pace",
    answered: true,
  })),
};

function serve(current: TraitPreferencesDocument, putResult?: () => Promise<unknown>) {
  mocks.fetchWithAuth.mockImplementation((_path: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      return putResult ? putResult() : Promise.resolve(JSON.parse(String(init.body)));
    }
    return Promise.resolve(current);
  });
}

function renderStep(onFinished = vi.fn(), skipLabel?: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <TraitPreferencesStep onFinished={onFinished} skipLabel={skipLabel} />
    </QueryClientProvider>
  );
  return onFinished;
}

function section(key: keyof typeof TRAIT_COPY) {
  return screen.getByRole("region", { name: TRAIT_COPY[key].label });
}

function answerAll(over: string, under: string) {
  for (const key of TRAIT_KEYS) {
    const s = section(key);
    const [moreGroup, lessGroup] = within(s).getAllByRole("group");
    fireEvent.click(within(moreGroup).getByLabelText(over));
    fireEvent.click(within(lessGroup).getByLabelText(under));
  }
}

function putCalls() {
  return mocks.fetchWithAuth.mock.calls.filter(([, init]) => init?.method === "PUT");
}

beforeEach(() => {
  mocks.fetchWithAuth.mockReset();
});

describe("TraitPreferencesStep", () => {
  it("shows all six traits with both questions, nothing pre-selected for a new user", async () => {
    serve(UNANSWERED);
    renderStep();

    await screen.findByRole("heading", { name: /how much give is there/i });
    for (const key of TRAIT_KEYS) {
      const s = section(key);
      expect(within(s).getByText(TRAIT_COPY[key].description)).toBeInTheDocument();
      expect(within(s).getByText(/more of this than you prefer/i)).toBeInTheDocument();
      expect(within(s).getByText(/less of this than you prefer/i)).toBeInTheDocument();
      for (const radio of within(s).getAllByRole("radio")) {
        expect(radio).not.toBeChecked();
      }
    }
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("'Skip for now' sends nothing and finishes as skipped", async () => {
    serve(UNANSWERED);
    const onFinished = renderStep();

    fireEvent.click(await screen.findByRole("button", { name: "Skip for now" }));

    expect(onFinished).toHaveBeenCalledWith("skipped");
    expect(putCalls()).toHaveLength(0);
  });

  it("saves all six traits with the chosen steps and must-haves", async () => {
    serve(UNANSWERED);
    const onFinished = renderStep();
    await screen.findByRole("heading", { name: /how much give is there/i });

    answerAll("A lot is fine", "Not at all");
    fireEvent.click(within(section("pace")).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onFinished).toHaveBeenCalledWith("saved"));
    const [[path, init]] = putCalls();
    expect(path).toBe("/me/trait-preferences");
    const sent = JSON.parse(String(init.body));
    expect(sent.traits.map((t: { dimension_key: string }) => t.dimension_key)).toEqual([
      ...TRAIT_KEYS,
    ]);
    for (const trait of sent.traits) {
      expect(trait.over_steps).toBe(2);
      expect(trait.under_steps).toBe(0);
      expect(trait.must_have).toBe(trait.dimension_key === "pace");
    }
  });

  it("disables the remaining must-have boxes once two are ticked", async () => {
    serve(UNANSWERED);
    renderStep();
    await screen.findByRole("heading", { name: /how much give is there/i });

    fireEvent.click(within(section("pace")).getByRole("checkbox"));
    fireEvent.click(within(section("feedback")).getByRole("checkbox"));

    expect(within(section("autonomy")).getByRole("checkbox")).toBeDisabled();
    expect(within(section("pace")).getByRole("checkbox")).toBeEnabled();
    expect(screen.getByText(/the most you can choose/i)).toBeInTheDocument();

    fireEvent.click(within(section("pace")).getByRole("checkbox"));
    expect(within(section("autonomy")).getByRole("checkbox")).toBeEnabled();
  });

  it("prefills a retake from the latest sitting", async () => {
    serve(ANSWERED);
    renderStep(vi.fn(), "Cancel");

    await screen.findByRole("heading", { name: /how much give is there/i });
    const [moreGroup, lessGroup] = within(section("pace")).getAllByRole("group");
    expect(within(moreGroup).getByLabelText("A lot is fine")).toBeChecked();
    expect(within(lessGroup).getByLabelText("Not at all")).toBeChecked();
    expect(within(section("pace")).getByRole("checkbox")).toBeChecked();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("keeps the choices and shows the house message when the save fails", async () => {
    serve(UNANSWERED, () => Promise.reject(new Error("at most 2 traits can be must-haves")));
    const onFinished = renderStep();
    await screen.findByRole("heading", { name: /how much give is there/i });

    answerAll("A little is fine", "A little is fine");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(SAVE_ERROR_MESSAGE);
    expect(onFinished).not.toHaveBeenCalled();
    const [moreGroup] = within(section("autonomy")).getAllByRole("group");
    expect(within(moreGroup).getByLabelText("A little is fine")).toBeChecked();
  });

  it("still lets the user answer when the current answers cannot be loaded", async () => {
    mocks.fetchWithAuth.mockImplementation((_path: string, init?: RequestInit) =>
      init?.method === "PUT"
        ? Promise.resolve(ANSWERED)
        : Promise.reject(new Error("offline"))
    );
    renderStep();

    expect(
      await screen.findByRole("heading", { name: /how much give is there/i }, { timeout: 5000 })
    ).toBeInTheDocument();
  });
});
