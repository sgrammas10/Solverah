/**
 * AccountSettingsPage.test.tsx — real hooks, fake transport.
 *
 * Only `fetchWithAuth`, `clearSessionLocally` and `useNavigate` are mocked; the
 * mutations, the query client and the component state all run for real.
 *
 * Two things here exist because this page's failure modes are silent:
 *
 * - jsdom implements no `URL.createObjectURL`/`revokeObjectURL`, so they are
 *   stubbed and restored. The stubs are also the only way to see the Blob: the
 *   download is a synthetic anchor click that leaves nothing in the DOM.
 *
 * - The deletion asserts ORDER, not just that both calls happened, via
 *   `mock.invocationCallOrder`. Clearing the session before navigating away
 *   drops `user` to null while this page is still mounted under `RequireAuth`,
 *   which redirects to /login and swallows the confirmation. Both orders call
 *   both functions exactly once, so only the order distinguishes them.
 *
 * Fixture failures are 4xx: an `ApiError` with a 5xx status would sit in the
 * query client's retry backoff instead of settling.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import AccountSettingsPage, { EXPORT_URL_REVOKE_DELAY_MS } from "./AccountSettingsPage";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  clearSessionLocally: vi.fn(),
  createObjectURL: vi.fn((_blob: Blob) => "blob:fake-url"),
  revokeObjectURL: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth", () => ({
  useAuth: () => ({
    user: { id: "1", name: "Ada Lovelace", email: "ada@example.com" },
    fetchWithAuth: mocks.fetchWithAuth,
    clearSessionLocally: mocks.clearSessionLocally,
  }),
}));

/** A free-text value from the export payload. It belongs in the file, never on screen. */
const SENTINEL = "my manager keeps moving the goalposts";

const EXPORT_PAYLOAD = {
  exported_at: "2026-09-14T00:00:00Z",
  account: { email: "ada@example.com" },
  pulse_events: [{ note: SENTINEL }],
};

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;
let clickSpy: ReturnType<typeof vi.spyOn>;
/** Anchors clicked during the test, captured because the element never enters the DOM for long. */
let clicked: { download: string; href: string }[];

beforeEach(() => {
  vi.clearAllMocks();
  clicked = [];
  URL.createObjectURL = mocks.createObjectURL as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = mocks.revokeObjectURL as unknown as typeof URL.revokeObjectURL;
  clickSpy = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ download: this.download, href: this.href });
    });
});

afterEach(() => {
  vi.useRealTimers();
  clickSpy.mockRestore();
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
});

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <AccountSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** jsdom's Blob implements no `.text()`, so read it the long way. */
function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

/** Open the confirmation block and type `value` into it. */
function startDeletion(value: string) {
  fireEvent.click(screen.getByRole("button", { name: "Delete my account" }));
  fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value } });
}

// ── Export ──────────────────────────────────────────────────────────────────

describe("data export", () => {
  it("downloads the payload as a dated JSON file and revokes the object URL only later", async () => {
    // Fake timers with real time still advancing, so `waitFor` keeps polling
    // while the deferred revoke stays under the test's control.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mocks.fetchWithAuth.mockResolvedValue(EXPORT_PAYLOAD);
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Download a copy of your data" }));

    await waitFor(() => expect(clicked).toHaveLength(1));

    expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/export");

    // The blob carries the whole payload, pretty-printed.
    const blob = mocks.createObjectURL.mock.calls[0][0];
    expect(blob.type).toBe("application/json");
    expect(JSON.parse(await readBlob(blob))).toEqual(EXPORT_PAYLOAD);

    expect(clicked[0].download).toMatch(/^solverah-data-\d{4}-\d{2}-\d{2}\.json$/);

    // Not on the click's own tick — that is the Firefox empty-file bug — but
    // once the delay has elapsed, and exactly once.
    expect(mocks.revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(EXPORT_URL_REVOKE_DELAY_MS);
    expect(mocks.revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(mocks.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");

    // The anchor is removed again — nothing is left behind in the document.
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("never renders any of the exported payload on screen", async () => {
    mocks.fetchWithAuth.mockResolvedValue(EXPORT_PAYLOAD);
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Download a copy of your data" }));
    await waitFor(() => expect(clicked).toHaveLength(1));

    expect(screen.queryByText(SENTINEL)).toBeNull();
    expect(document.body.textContent).not.toContain(SENTINEL);
  });

  it("shows an error panel on failure, and Try again re-fires the request", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new ApiError("boom", { status: 403 }));
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Download a copy of your data" }));

    await screen.findByText("We couldn't prepare your download just now.");
    expect(clicked).toHaveLength(0);

    mocks.fetchWithAuth.mockResolvedValueOnce(EXPORT_PAYLOAD);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2);
  });
});

// ── Deletion: the confirmation gate ─────────────────────────────────────────

describe("delete confirmation gate", () => {
  it.each([
    ["", "empty"],
    ["delete", "lowercase"],
    ["DELET", "truncated"],
  ])("keeps the confirm button disabled for %o (%s)", (value) => {
    renderPage();
    startDeletion(value);

    expect(screen.getByRole("button", { name: "Permanently delete" })).toBeDisabled();
  });

  it.each([["DELETE"], [" DELETE "]])("enables the confirm button for %o", (value) => {
    renderPage();
    startDeletion(value);

    expect(screen.getByRole("button", { name: "Permanently delete" })).toBeEnabled();
  });

  it("sends the literal confirmation, not the text the user typed", async () => {
    mocks.fetchWithAuth.mockResolvedValue({ r2_delete_failures: [] });
    renderPage();
    startDeletion(" DELETE ");

    fireEvent.click(screen.getByRole("button", { name: "Permanently delete" }));

    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalled());
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me", {
      method: "DELETE",
      body: '{"confirm":"DELETE"}',
    });
  });
});

// ── Deletion: the outcomes ──────────────────────────────────────────────────

describe("delete outcomes", () => {
  /** Run a deletion whose request settles as `settle`, and return once it has. */
  async function deleteWith(settle: () => Promise<unknown>) {
    mocks.fetchWithAuth.mockImplementation(settle);
    renderPage();
    startDeletion("DELETE");
    fireEvent.click(screen.getByRole("button", { name: "Permanently delete" }));
  }

  it("navigates home with the confirmation BEFORE clearing the session", async () => {
    await deleteWith(() => Promise.resolve({ r2_delete_failures: [] }));

    await waitFor(() => expect(mocks.clearSessionLocally).toHaveBeenCalled());

    expect(mocks.navigate).toHaveBeenCalledWith("/", {
      replace: true,
      state: { accountDeleted: true, filesLeftBehind: false },
    });
    // Clearing first would unmount this page under RequireAuth and lose the note.
    expect(mocks.navigate.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.clearSessionLocally.mock.invocationCallOrder[0],
    );
  });

  it("flags filesLeftBehind when the backend could not remove every object", async () => {
    await deleteWith(() => Promise.resolve({ r2_delete_failures: ["resumes/abc.pdf"] }));

    await waitFor(() => expect(mocks.clearSessionLocally).toHaveBeenCalled());
    expect(mocks.navigate).toHaveBeenCalledWith("/", {
      replace: true,
      state: { accountDeleted: true, filesLeftBehind: true },
    });
  });

  it("treats a 404 as success — the account is already gone", async () => {
    await deleteWith(() => Promise.reject(new ApiError("User not found", { status: 404 })));

    await waitFor(() => expect(mocks.clearSessionLocally).toHaveBeenCalled());

    expect(mocks.navigate).toHaveBeenCalledWith("/", {
      replace: true,
      state: { accountDeleted: true, filesLeftBehind: false },
    });
    expect(mocks.navigate.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.clearSessionLocally.mock.invocationCallOrder[0],
    );
    expect(screen.queryByText("We couldn't delete your account just now.")).toBeNull();
  });

  it("leaves the session and the page untouched on a real failure", async () => {
    await deleteWith(() => Promise.reject(new ApiError("nope", { status: 403 })));

    await screen.findByText("We couldn't delete your account just now.");

    expect(mocks.clearSessionLocally).not.toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
    // The typed confirmation survives, so a retry is one click and not one retype.
    expect(screen.getByLabelText("Type DELETE to confirm")).toHaveValue("DELETE");
  });
});
