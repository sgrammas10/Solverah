/**
 * Audit 2026-10-02 item 6: once a career status was set it could not be
 * changed from the UI -- the onboarding modal was the only control, and it was
 * reachable only while the status was unset. The Experience tab now carries
 * this control, always.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import CareerStatusControl from "./CareerStatusControl";
import { createQueryClient } from "../../../shared/api/queryClient";
import { profileKeys } from "../useProfile";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
  user: { name: "Ada" } as any,
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, fetchWithAuth: mocks.fetchWithAuth }),
}));

function renderControl(profile: Record<string, unknown>) {
  const client = createQueryClient();
  client.setQueryData(profileKeys.document(), profile);
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <CareerStatusControl />
    </QueryClientProvider>,
  );
  return { client, invalidate };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchWithAuth.mockResolvedValue({ career_status: "between_jobs" });
});

describe("CareerStatusControl", () => {
  it("shows the stored status as the chosen one", () => {
    renderControl({ career_status: "employed" });
    expect(screen.getByRole("radio", { name: /currently employed/i })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /currently unemployed/i })).toHaveAttribute("aria-checked", "false");
  });

  it("changes a status that is already set", async () => {
    const { client, invalidate } = renderControl({ career_status: "employed", summary: "kept" });

    fireEvent.click(screen.getByRole("radio", { name: /currently unemployed/i }));

    await waitFor(() =>
      expect(screen.getByRole("radio", { name: /currently unemployed/i })).toHaveAttribute("aria-checked", "true"),
    );
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/career-status", {
      method: "PATCH",
      body: JSON.stringify({ status: "between_jobs" }),
    });
    expect(client.getQueryData(profileKeys.document())).toEqual({
      career_status: "between_jobs",
      summary: "kept",
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["situationReport"] });
    expect(await screen.findByRole("status")).toHaveTextContent("Status saved.");
  });

  it("offers every status when none is set", () => {
    renderControl({});
    for (const name of [/currently employed/i, /currently unemployed/i, /looking for my first job/i]) {
      expect(screen.getByRole("radio", { name })).toHaveAttribute("aria-checked", "false");
    }
  });

  it("keeps the stored status and says so when the save fails", async () => {
    mocks.fetchWithAuth.mockRejectedValue(new ApiError("boom", { status: 500 }));
    const { client } = renderControl({ career_status: "employed" });

    fireEvent.click(screen.getByRole("radio", { name: /looking for my first job/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't save that just now.");
    expect(screen.getByRole("radio", { name: /currently employed/i })).toHaveAttribute("aria-checked", "true");
    expect(client.getQueryData(profileKeys.document())).toEqual({ career_status: "employed" });
  });

  it("is a set of buttons, so choosing one never submits the profile form", () => {
    renderControl({});
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toHaveAttribute("type", "button");
    }
  });
});
