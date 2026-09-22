/**
 * usePathFeedback.test.tsx — the deep fit's cache behaviour (W-9).
 *
 * `PathIntelligencePage.test.tsx` covers what a user does with the panel. These
 * are the claims that live below it, in the query cache, and they are the whole
 * reason the deep fit stopped being a mutation:
 *
 *   1. a card is requested once, however many times it is opened;
 *   2. the three cards on screen can be warmed before anybody clicks, and a
 *      click on a warm card asks for nothing;
 *   3. a failed prefetch is silent, is not retried behind the user's back, and
 *      does not flash its failure at whoever opens that card next.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { createQueryClient } from "../../shared/api/queryClient";
import { pathFitKeys, usePathFit, usePrefetchPathFits } from "./usePathFeedback";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
  user: {} as Record<string, unknown>,
}));

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth, user: mocks.user }),
}));

const CODE_A = "11-2021.00";
const CODE_B = "15-1252.00";

function fitFor(onetCode: string) {
  return { onet_code: onetCode, title: onetCode, fit_score: 0.5, onet_calls: 0 };
}

/** How many times the deep-fit endpoint was asked about *onetCode*. */
function requestsFor(onetCode: string): number {
  return mocks.fetchWithAuth.mock.calls.filter(
    (call) => String(call[0]) === `/me/path-fit/${onetCode}`,
  ).length;
}

function Harness({ codes = [] as string[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const prefetch = usePrefetchPathFits();
  const fit = usePathFit(open);
  return (
    <div>
      <button type="button" onClick={() => prefetch(codes)}>
        warm
      </button>
      <button type="button" onClick={() => setOpen(CODE_A)}>
        open A
      </button>
      <button type="button" onClick={() => setOpen(CODE_B)}>
        open B
      </button>
      <button type="button" onClick={() => setOpen(null)}>
        close
      </button>
      <button type="button" onClick={fit.retry}>
        retry
      </button>
      <span data-testid="state">
        {fit.isPending ? "pending" : fit.isError ? "error" : fit.data ? "ready" : "idle"}
      </span>
      <span data-testid="title">{fit.data?.title ?? ""}</span>
    </div>
  );
}

function renderHarness(codes: string[] = []) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <Harness codes={codes} />
    </QueryClientProvider>,
  );
}

const state = () => screen.getByTestId("state").textContent;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchWithAuth.mockImplementation((path: string) =>
    Promise.resolve(fitFor(path.replace("/me/path-fit/", ""))),
  );
});

describe("usePathFit", () => {
  it("asks for nothing until a card is open", () => {
    renderHarness();

    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
    expect(state()).toBe("pending");
  });

  it("POSTs the open card's code and nothing else", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("open A"));

    await waitFor(() => expect(state()).toBe("ready"));
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
      `/me/path-fit/${CODE_A}`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
  });

  it("reopening a card costs no second request", async () => {
    // THE complaint, as a test: every open used to be a fresh POST.
    renderHarness();
    fireEvent.click(screen.getByText("open A"));
    await waitFor(() => expect(state()).toBe("ready"));

    fireEvent.click(screen.getByText("close"));
    fireEvent.click(screen.getByText("open A"));

    await waitFor(() => expect(state()).toBe("ready"));
    expect(requestsFor(CODE_A)).toBe(1);
  });

  it("keeps each occupation in its own entry", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("open A"));
    await waitFor(() => expect(screen.getByTestId("title")).toHaveTextContent(CODE_A));

    fireEvent.click(screen.getByText("open B"));

    await waitFor(() => expect(screen.getByTestId("title")).toHaveTextContent(CODE_B));
    expect(requestsFor(CODE_B)).toBe(1);
  });

  it("does not retry a failure on its own", async () => {
    // The client default retries a 429 or a 5xx twice. Wrong here: this route
    // carries a rate limit precisely because it reaches a provider.
    mocks.fetchWithAuth.mockRejectedValue(new Error("corpus_unavailable"));
    renderHarness();

    fireEvent.click(screen.getByText("open A"));

    await waitFor(() => expect(state()).toBe("error"));
    expect(requestsFor(CODE_A)).toBe(1);
  });

  it("retry asks again", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("corpus_unavailable"));
    renderHarness();
    fireEvent.click(screen.getByText("open A"));
    await waitFor(() => expect(state()).toBe("error"));

    fireEvent.click(screen.getByText("retry"));

    await waitFor(() => expect(state()).toBe("ready"));
    expect(requestsFor(CODE_A)).toBe(2);
  });

  it("closing a card does not cancel or clear anything", async () => {
    // A close used to call `mutation.reset()`. Dropping cache entries here
    // would now be able to tear down a prefetch a different card is waiting on.
    renderHarness();
    fireEvent.click(screen.getByText("open A"));
    await waitFor(() => expect(state()).toBe("ready"));

    fireEvent.click(screen.getByText("close"));
    fireEvent.click(screen.getByText("open A"));

    expect(state()).toBe("ready");
    expect(requestsFor(CODE_A)).toBe(1);
  });
});

describe("usePrefetchPathFits", () => {
  it("warms every code it is given, once each", async () => {
    renderHarness([CODE_A, CODE_B]);

    fireEvent.click(screen.getByText("warm"));

    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2));
    expect(requestsFor(CODE_A)).toBe(1);
    expect(requestsFor(CODE_B)).toBe(1);
  });

  it("a click on a warm card asks for nothing and shows it at once", async () => {
    renderHarness([CODE_A]);
    fireEvent.click(screen.getByText("warm"));
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByText("open A"));

    // No await: the point is that there is nothing to wait for.
    expect(state()).toBe("ready");
    expect(requestsFor(CODE_A)).toBe(1);
  });

  it("a second warming of the same list re-requests nothing", async () => {
    renderHarness([CODE_A, CODE_B]);
    fireEvent.click(screen.getByText("warm"));
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByText("warm"));

    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2));
  });

  it("does not warm a card that is already open", async () => {
    renderHarness([CODE_A]);
    fireEvent.click(screen.getByText("open A"));
    await waitFor(() => expect(state()).toBe("ready"));

    fireEvent.click(screen.getByText("warm"));

    await waitFor(() => expect(requestsFor(CODE_A)).toBe(1));
  });

  it("a refused prefetch is silent and is not retried", async () => {
    // A 429 on something the user never asked for. Nothing may reach the
    // screen, and the prefetcher may not spend a second request on it.
    mocks.fetchWithAuth.mockRejectedValue(new Error("rate_limited"));
    renderHarness([CODE_A]);

    fireEvent.click(screen.getByText("warm"));
    await waitFor(() => expect(requestsFor(CODE_A)).toBe(1));

    expect(state()).toBe("pending"); // no card open, so nothing is shown
    fireEvent.click(screen.getByText("warm"));
    await waitFor(() => expect(requestsFor(CODE_A)).toBe(1));
  });

  it("a click after a failed prefetch retries rather than showing the old failure", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("rate_limited"));
    renderHarness([CODE_A]);
    fireEvent.click(screen.getByText("warm"));
    await waitFor(() => expect(requestsFor(CODE_A)).toBe(1));

    fireEvent.click(screen.getByText("open A"));

    // Never "error" on the way through: a retry in flight is pending, so the
    // panel cannot flash a failure the user was never told about.
    expect(state()).toBe("pending");
    await waitFor(() => expect(state()).toBe("ready"));
    expect(requestsFor(CODE_A)).toBe(2);
  });

  it("ignores an empty code rather than POSTing to a bare path", () => {
    renderHarness([""]);

    fireEvent.click(screen.getByText("warm"));

    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("stores warm cards under the key the open card reads", async () => {
    // If these two ever disagreed the prefetch would be spent and ignored --
    // the one failure mode a prefetch has that nobody would notice.
    expect(pathFitKeys.one(CODE_A)).toEqual(["path-fit", CODE_A]);
  });
});
