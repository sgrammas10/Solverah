/**
 * PathWantsPanel.test.tsx — the wants panel over a mocked transport.
 *
 * The hook is NOT mocked. It is two `fetchWithAuth` calls and a draft, and
 * mocking it would test the mock; driving the real hook through the already
 * mocked transport exercises the real path, the real method and the real body,
 * which is what `tests/test_frontend_contract.py` scans for on the other side.
 * `PathIntelligencePage.test.tsx` set this precedent for the feedback hooks.
 *
 * Controls are selected by role and by `data-want*`, never by their prose:
 * Julie owns the copy and revises it on the built product, so a wording change
 * must not redden this file.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";

import PathWantsPanel from "./PathWantsPanel";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
  user: {} as Record<string, unknown>,
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth, user: mocks.user }),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ANCHOR = { onet_code: "15-1252.00", title: "Software Developers" };

const TASKS = [
  { key: "t_a1b2c3d4e5f6", label: "Write and test code", verdict: null },
  { key: "t_b2c3d4e5f6a1", label: "Review other people's code", verdict: null },
];

const CONDITIONS = [
  { axis: "people", label: "Time working alongside other people", verdict: null },
  { axis: "public", label: "Dealing with the public", verdict: null },
  { axis: "leading", label: "Leading or coordinating others", verdict: null },
  { axis: "desk", label: "At a desk rather than on your feet", verdict: null },
];

function panelPayload(overrides: Record<string, unknown> = {}) {
  return {
    status: "ok",
    anchor: ANCHOR,
    tasks: TASKS,
    conditions: CONDITIONS,
    ...overrides,
  };
}

/** Requests the panel has issued, in order, as `METHOD` + parsed body. */
type Call = { method: string; body: unknown };

function calls(): Call[] {
  return (mocks.fetchWithAuth.mock.calls as unknown[][])
    .filter((call) => call[0] === "/me/path-wants")
    .map((call) => {
      const init = call[1] as RequestInit | undefined;
      return {
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
      };
    });
}

function puts(): Call[] {
  return calls().filter((call) => call.method === "PUT");
}

function gets(): Call[] {
  return calls().filter((call) => call.method === "GET");
}

/**
 * Answer the GET with `panel`, and every PUT with whatever `onPut` returns —
 * an `Error` is rejected, anything else resolved.
 */
function serve(panel: unknown, onPut?: (body: unknown) => unknown) {
  mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
    if (path !== "/me/path-wants") return Promise.resolve({});
    if ((init?.method ?? "GET") === "GET") return Promise.resolve(panel);
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    const result = onPut ? onPut(body) : panel;
    return result instanceof Error ? Promise.reject(result) : Promise.resolve(result);
  });
}

const onSaved = vi.fn();

function renderPanel(props: { rescoring?: boolean } = {}) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <PathWantsPanel onSaved={onSaved} rescoring={props.rescoring} />
    </QueryClientProvider>
  );
}

/** The collapsed row, which is also the expand/collapse control. */
function toggle(): HTMLElement {
  return screen.getByRole("button", { expanded: false });
}

function expandedToggle(): HTMLElement {
  return screen.getByRole("button", { expanded: true });
}

function groupFor(kind: string, key: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-want="want-${kind}-${key}"]`);
  if (!found) throw new Error(`no row for ${kind} ${key}`);
  return found;
}

/** The "less" / "fine" / "more" radio of one row. */
function choice(kind: string, key: string, value: "less" | "fine" | "more"): HTMLInputElement {
  const input = groupFor(kind, key).querySelector<HTMLInputElement>(`input[value="${value}"]`);
  if (!input) throw new Error(`no ${value} choice for ${kind} ${key}`);
  return input;
}

function saveButton(): HTMLElement {
  const found = document.querySelector<HTMLElement>("[data-wants-save]");
  if (!found) throw new Error("no save control");
  return found;
}

function clearButton(): HTMLElement | null {
  return document.querySelector<HTMLElement>("[data-wants-clear]");
}

/** Open the panel once its GET has landed. */
async function open() {
  await waitFor(() => expect(gets()).toHaveLength(1));
  await waitFor(() => expect(screen.queryByRole("button")).not.toBeNull());
  fireEvent.click(toggle());
  await waitFor(() => expect(expandedToggle()).toBeInTheDocument());
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = {};
});

// ---------------------------------------------------------------------------
// The three statuses
// ---------------------------------------------------------------------------

describe("PathWantsPanel - what it renders at all", () => {
  it("renders nothing while its own request is in flight", () => {
    mocks.fetchWithAuth.mockImplementation(() => new Promise(() => {}));
    const { container } = renderPanel();
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when its own request fails", async () => {
    // A panel nobody asked for does not get to report its outage on a page that
    // is working. Quiet, contained, and the suggestions above are unaffected.
    mocks.fetchWithAuth.mockImplementation(() =>
      Promise.reject(new ApiError("corpus_unavailable", { status: 503 }))
    );
    const { container } = renderPanel();
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("renders nothing for a user with no current job (no_anchor)", async () => {
    serve({ status: "no_anchor", anchor: null, tasks: [], conditions: [] });
    const { container } = renderPanel();
    await waitFor(() => expect(gets()).toHaveLength(1));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("asks the conditions alone when the task sidecar is unavailable", async () => {
    serve({ status: "unavailable", anchor: ANCHOR, tasks: [], conditions: CONDITIONS });
    renderPanel();
    await open();

    expect(document.querySelectorAll("[data-want]")).toHaveLength(4);
    expect(document.querySelectorAll('[data-want^="want-task-"]')).toHaveLength(0);
    // No apology for the half it cannot offer: there is no alert and no
    // explanation of a sidecar the user has never heard of.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Collapsed, then expanded
// ---------------------------------------------------------------------------

describe("PathWantsPanel - collapsing", () => {
  it("is collapsed by default and shows no questions", async () => {
    serve(panelPayload());
    renderPanel();
    await waitFor(() => expect(gets()).toHaveLength(1));

    await waitFor(() => expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false"));
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
  });

  it("expands on click, flipping aria-expanded, and points at what it controls", async () => {
    serve(panelPayload());
    renderPanel();
    await open();

    const control = expandedToggle();
    expect(control).toHaveAttribute("aria-expanded", "true");
    const bodyId = control.getAttribute("aria-controls");
    expect(bodyId).toBeTruthy();
    expect(document.getElementById(bodyId!)).not.toBeNull();

    // Six rows -- two tasks and four conditions -- three choices each.
    expect(document.querySelectorAll("[data-want]")).toHaveLength(6);
    expect(screen.getAllByRole("radio")).toHaveLength(18);
    expect(screen.getByText(/Software Developers/i)).toBeInTheDocument();
  });

  it("collapses again", async () => {
    serve(panelPayload());
    renderPanel();
    await open();
    fireEvent.click(expandedToggle());
    await waitFor(() => expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false"));
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
  });

  it("summarises standing answers on the collapsed row", async () => {
    serve(
      panelPayload({
        tasks: [
          { ...TASKS[0], verdict: "less" },
          { ...TASKS[1], verdict: null },
        ],
        conditions: [
          { ...CONDITIONS[0], verdict: "more" },
          ...CONDITIONS.slice(1),
        ],
      })
    );
    renderPanel();
    await waitFor(() => expect(gets()).toHaveLength(1));
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("2"));
  });
});

// ---------------------------------------------------------------------------
// Answering
// ---------------------------------------------------------------------------

describe("PathWantsPanel - answering", () => {
  it("pre-selects the verdicts the server has stored", async () => {
    serve(
      panelPayload({
        tasks: [{ ...TASKS[0], verdict: "less" }, TASKS[1]],
        conditions: [{ ...CONDITIONS[0], verdict: "more" }, ...CONDITIONS.slice(1)],
      })
    );
    renderPanel();
    await open();

    expect(choice("task", TASKS[0].key, "less")).toBeChecked();
    expect(choice("task", TASKS[1].key, "fine")).toBeChecked();
    expect(choice("condition", "people", "more")).toBeChecked();
    expect(choice("condition", "public", "fine")).toBeChecked();
  });

  it("defaults every unanswered row to 'fine', which means no answer", async () => {
    serve(panelPayload());
    renderPanel();
    await open();

    for (const task of TASKS) expect(choice("task", task.key, "fine")).toBeChecked();
    for (const condition of CONDITIONS) {
      expect(choice("condition", condition.axis, "fine")).toBeChecked();
    }
    expect(clearButton()).toBeNull();
  });

  it("does NOT call the API when a choice is made", async () => {
    // A save re-scores, and the narrator takes seconds. Answering is local.
    serve(panelPayload());
    renderPanel();
    await open();

    fireEvent.click(choice("task", TASKS[0].key, "more"));
    fireEvent.click(choice("condition", "people", "less"));
    fireEvent.click(choice("condition", "desk", "less"));

    expect(puts()).toHaveLength(0);
    expect(gets()).toHaveLength(1);
  });

  it("leaves the save disabled until something has actually changed", async () => {
    serve(panelPayload());
    renderPanel();
    await open();

    expect(saveButton()).toBeDisabled();
    fireEvent.click(choice("task", TASKS[0].key, "more"));
    expect(saveButton()).toBeEnabled();

    // Put back to "fine" and nothing has changed after all.
    fireEvent.click(choice("task", TASKS[0].key, "fine"));
    expect(saveButton()).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Saving
// ---------------------------------------------------------------------------

describe("PathWantsPanel - saving", () => {
  it("sends ONE PUT carrying only what changed, then asks for a re-score", async () => {
    serve(panelPayload(), () =>
      panelPayload({
        tasks: [{ ...TASKS[0], verdict: "more" }, TASKS[1]],
        conditions: [{ ...CONDITIONS[0], verdict: "less" }, ...CONDITIONS.slice(1)],
      })
    );
    renderPanel();
    await open();

    fireEvent.click(choice("task", TASKS[0].key, "more"));
    fireEvent.click(choice("condition", "people", "less"));
    fireEvent.click(saveButton());

    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0].body).toEqual({
      answers: [
        { kind: "task", key: TASKS[0].key, verdict: "more" },
        { kind: "condition", key: "people", verdict: "less" },
      ],
    });
    // The panel starts no job of its own: it tells the page, and the page runs
    // the enqueue-and-poll flow it already has.
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("clears every standing answer through the same save, as nulls", async () => {
    serve(
      panelPayload({
        tasks: [{ ...TASKS[0], verdict: "less" }, TASKS[1]],
        conditions: [{ ...CONDITIONS[0], verdict: "more" }, ...CONDITIONS.slice(1)],
      }),
      () => panelPayload()
    );
    renderPanel();
    await open();

    fireEvent.click(clearButton()!);

    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0].body).toEqual({
      answers: [
        { kind: "task", key: TASKS[0].key, verdict: null },
        { kind: "condition", key: "people", verdict: null },
      ],
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("offers no clear control when there is nothing to clear", async () => {
    serve(panelPayload());
    renderPanel();
    await open();
    expect(clearButton()).toBeNull();
  });

  it("shows progress and locks the controls while the save is in flight", async () => {
    mocks.fetchWithAuth.mockImplementation((_path: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "GET") return Promise.resolve(panelPayload());
      return new Promise(() => {});
    });
    renderPanel();
    await open();

    fireEvent.click(choice("task", TASKS[0].key, "more"));
    fireEvent.click(saveButton());

    await waitFor(() => expect(saveButton()).toHaveAttribute("aria-busy", "true"));
    expect(saveButton()).toBeDisabled();
    expect(choice("task", TASKS[1].key, "more")).toBeDisabled();
  });

  it("reloads the panel and says so when the answers are no longer offered", async () => {
    // 422 `not_offered`: the panel on screen is about a job this user no longer
    // holds -- their job changed in another tab. Nothing was written.
    let served = panelPayload();
    mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
      if (path !== "/me/path-wants") return Promise.resolve({});
      if ((init?.method ?? "GET") === "GET") return Promise.resolve(served);
      served = panelPayload({
        anchor: { onet_code: "41-3091.00", title: "Sales Representatives" },
        tasks: [{ key: "t_ffffffffffff", label: "Call prospects", verdict: null }],
      });
      return Promise.reject(
        new ApiError("key must name a row this user's current occupation offers.", {
          status: 422,
          code: "validation",
          fieldErrors: [{ field: "answers.0.key", code: "not_offered" }],
        })
      );
    });

    renderPanel();
    await open();
    fireEvent.click(choice("task", TASKS[0].key, "more"));
    fireEvent.click(saveButton());

    // Told plainly, inside the panel.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
    // And the panel is reloaded rather than left describing the old job.
    await waitFor(() => expect(gets().length).toBeGreaterThan(1));
    await waitFor(() =>
      expect(screen.getByText(/Sales Representatives/i)).toBeInTheDocument()
    );
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("keeps a refused save inside the panel and says nothing about the page", async () => {
    serve(panelPayload(), () => new ApiError("Too many requests", { status: 429 }));
    renderPanel();
    await open();

    fireEvent.click(choice("condition", "leading", "more"));
    fireEvent.click(saveButton());

    const alert = await screen.findByRole("alert");
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    // The edit is still there to try again with.
    expect(choice("condition", "leading", "more")).toBeChecked();
    expect(saveButton()).toBeEnabled();
    expect(onSaved).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Keyboard
// ---------------------------------------------------------------------------

describe("PathWantsPanel - keyboard", () => {
  it("opens and answers without a mouse", async () => {
    serve(panelPayload());
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() => expect(gets()).toHaveLength(1));

    // Tab to the collapsed row and open it with the keyboard.
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { expanded: false }));
    await user.keyboard("{Enter}");
    await waitFor(() => expect(expandedToggle()).toBeInTheDocument());

    // The next tab stop is the first row's radio group -- ONE stop for the
    // whole group, which is what a real radio group gives you for free, and it
    // lands on the checked option ("fine").
    await user.tab();
    const focused = document.activeElement as HTMLInputElement;
    expect(focused.type).toBe("radio");
    expect(focused.name).toBe(`want-task-${TASKS[0].key}`);
    expect(focused.value).toBe("fine");

    // Arrow keys move within the group and answer it -- no mouse, no Tab per
    // option, no custom key handling of ours.
    await user.keyboard("{ArrowRight}");
    expect(choice("task", TASKS[0].key, "more")).toBeChecked();
    expect(saveButton()).toBeEnabled();
    expect(puts()).toHaveLength(0);
  });
});
