/**
 * usePathWants.test.tsx — the two claims the panel's own test cannot see.
 *
 * `PathWantsPanel.test.tsx` covers what a user does. These two are about the
 * query cache, and they are the whole reason the save re-ranks the page:
 *
 *   1. a landed save drops the suggestion-job cache, so nothing stale can be
 *      shown while the page enqueues the next scoring run — and the hook starts
 *      no job itself, it calls `onSaved` and the page runs the flow it has;
 *   2. the PUT's response IS the panel, so it is written into the panel query
 *      rather than provoking a second GET.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import { createQueryClient } from "../../shared/api/queryClient";
import { pathSuggestionJobKeys } from "./usePathSuggestionJob";
import { pathWantsKeys, usePathWants } from "./usePathWants";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
  user: {} as Record<string, unknown>,
}));

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth, user: mocks.user }),
}));

const PANEL = {
  status: "ok",
  anchor: { onet_code: "15-1252.00", title: "Software Developers" },
  tasks: [{ key: "t_a1b2c3d4e5f6", label: "Write and test code", verdict: null }],
  conditions: [{ axis: "people", label: "Time with other people", verdict: null }],
};

const SAVED = {
  ...PANEL,
  tasks: [{ ...PANEL.tasks[0], verdict: "less" }],
};

function Harness({ onSaved }: { onSaved: () => void }) {
  const wants = usePathWants({ onSaved });
  return (
    <div>
      <span data-testid="status">{wants.status ?? "none"}</span>
      <span data-testid="answered">{wants.answeredCount}</span>
      <button type="button" onClick={() => wants.setVerdict("task", PANEL.tasks[0].key, "less")}>
        mark
      </button>
      <button type="button" onClick={wants.save}>
        save
      </button>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
    if (path !== "/me/path-wants") return Promise.resolve({});
    return Promise.resolve((init?.method ?? "GET") === "GET" ? PANEL : SAVED);
  });
});

describe("usePathWants", () => {
  it("drops the suggestion-job cache and hands the re-score to the caller", async () => {
    const client = createQueryClient();
    // A job result from before the wants changed. It must not survive the save:
    // the answers it was ranked from are no longer the answers.
    client.setQueryData(pathSuggestionJobKeys.status("job-1"), {
      job_id: "job-1",
      status: "succeeded",
      result: { suggestions: [], career_status: "employed", generated_at: "2026-09-01T00:00:00Z" },
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const onSaved = vi.fn();

    render(
      <QueryClientProvider client={client}>
        <Harness onSaved={onSaved} />
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ok"));

    fireEvent.click(screen.getByRole("button", { name: "mark" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: pathSuggestionJobKeys.all });
    // Nothing here enqueues: the page owns the one job flow.
    expect(
      (mocks.fetchWithAuth.mock.calls as unknown[][]).some((call) =>
        String(call[0]).startsWith("/me/path-suggestion-jobs")
      )
    ).toBe(false);
  });

  it("writes the PUT's own response into the panel, rather than re-reading it", async () => {
    const client = createQueryClient();
    render(
      <QueryClientProvider client={client}>
        <Harness onSaved={() => {}} />
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ok"));

    fireEvent.click(screen.getByRole("button", { name: "mark" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));

    await waitFor(() => expect(screen.getByTestId("answered")).toHaveTextContent("1"));
    expect(client.getQueryData(pathWantsKeys.panel())).toEqual(SAVED);
    // One GET, one PUT, and no second read to find out what was stored.
    const paths = (mocks.fetchWithAuth.mock.calls as unknown[][])
      .filter((call) => call[0] === "/me/path-wants")
      .map((call) => (call[1] as RequestInit | undefined)?.method ?? "GET");
    expect(paths).toEqual(["GET", "PUT"]);
  });
});
