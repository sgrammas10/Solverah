/**
 * ErrorBoundary — the catch mechanism.
 *
 * These cover the class in isolation. The route-level policy built on it, and
 * the TanStack Query integration that makes its retry button actually work,
 * are covered in RouteErrorBoundary.test.tsx.
 */
import { useState } from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ErrorBoundary } from "./ErrorBoundary";

/**
 * React prints a caught error to console.error regardless of whether a boundary
 * handled it, and `componentDidCatch` adds one more. Left alone that is several
 * screens of expected noise per run, which trains everyone to ignore the
 * console — so it is silenced here and restored after.
 */
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

function Boom({ shouldThrow }: { shouldThrow: boolean }): JSX.Element {
  if (shouldThrow) throw new Error("boom");
  return <p>rendered fine</p>;
}

const fallback = (error: Error, reset: () => void) => (
  <div>
    <p>caught: {error.message}</p>
    <button type="button" onClick={reset}>
      retry
    </button>
  </div>
);

describe("ErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary fallback={fallback}>
        <Boom shouldThrow={false} />
      </ErrorBoundary>,
    );

    expect(screen.getByText("rendered fine")).toBeInTheDocument();
  });

  it("renders the fallback instead of unmounting the tree when a child throws", () => {
    render(
      <ErrorBoundary fallback={fallback}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    // The defect Phase 4b exists for: without a boundary this subtree is
    // removed and the user is left with a blank page.
    expect(screen.getByText("caught: boom")).toBeInTheDocument();
  });

  it("passes the thrown error to the fallback", () => {
    function Specific(): JSX.Element {
      throw new Error("profile fetch failed");
    }

    render(
      <ErrorBoundary fallback={fallback}>
        <Specific />
      </ErrorBoundary>,
    );

    expect(screen.getByText("caught: profile fetch failed")).toBeInTheDocument();
  });

  it("re-renders children when reset is called and the cause is gone", async () => {
    const user = userEvent.setup();

    function Harness() {
      const [broken, setBroken] = useState(true);
      return (
        <ErrorBoundary fallback={fallback} onReset={() => setBroken(false)}>
          <Boom shouldThrow={broken} />
        </ErrorBoundary>
      );
    }

    render(<Harness />);
    expect(screen.getByText("caught: boom")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "retry" }));

    expect(screen.getByText("rendered fine")).toBeInTheDocument();
  });

  it("runs onReset before clearing, so the retry sees the repaired cause", async () => {
    const user = userEvent.setup();
    const order: string[] = [];

    function Harness() {
      const [broken, setBroken] = useState(true);
      order.push(broken ? "render:broken" : "render:fixed");
      return (
        <ErrorBoundary
          fallback={fallback}
          onReset={() => {
            order.push("onReset");
            setBroken(false);
          }}
        >
          <Boom shouldThrow={broken} />
        </ErrorBoundary>
      );
    }

    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "retry" }));

    // This ordering is the whole reason onReset exists. If the boundary cleared
    // its own state first, the retry would re-render the still-broken child and
    // throw again before the cause was repaired -- a button that can never work.
    expect(order.indexOf("onReset")).toBeLessThan(order.lastIndexOf("render:fixed"));
    expect(screen.getByText("rendered fine")).toBeInTheDocument();
  });

  it("clears itself when a resetKey changes", () => {
    const { rerender } = render(
      <ErrorBoundary fallback={fallback} resetKeys={["/broken"]}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );
    expect(screen.getByText("caught: boom")).toBeInTheDocument();

    // Stands in for navigating to a different route: the key changes and the
    // child is no longer the throwing one.
    rerender(
      <ErrorBoundary fallback={fallback} resetKeys={["/working"]}>
        <Boom shouldThrow={false} />
      </ErrorBoundary>,
    );

    expect(screen.getByText("rendered fine")).toBeInTheDocument();
  });

  it("stays caught while the resetKeys are unchanged", () => {
    const { rerender } = render(
      <ErrorBoundary fallback={fallback} resetKeys={["/broken"]}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    rerender(
      <ErrorBoundary fallback={fallback} resetKeys={["/broken"]}>
        <Boom shouldThrow={false} />
      </ErrorBoundary>,
    );

    // An unrelated re-render must not silently retry: the child would throw
    // straight back and the fallback would flicker on every parent update.
    expect(screen.getByText("caught: boom")).toBeInTheDocument();
  });

  it("treats a length change in resetKeys as a change", () => {
    const { rerender } = render(
      <ErrorBoundary fallback={fallback} resetKeys={["/a"]}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    rerender(
      <ErrorBoundary fallback={fallback} resetKeys={["/a", "extra"]}>
        <Boom shouldThrow={false} />
      </ErrorBoundary>,
    );

    expect(screen.getByText("rendered fine")).toBeInTheDocument();
  });

  it("reports the error and component stack to onError", () => {
    const onError = vi.fn();

    render(
      <ErrorBoundary fallback={fallback} onError={onError}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    expect(onError).toHaveBeenCalledTimes(1);
    const [error, info] = onError.mock.calls[0];
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe("boom");
    expect(info.componentStack).toEqual(expect.any(String));
  });

  it("logs the failure even when no onError is supplied", () => {
    render(
      <ErrorBoundary fallback={fallback}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    // The fallback deliberately does not show the message to the user, so the
    // console is the only remaining record that a screen died.
    expect(console.error).toHaveBeenCalledWith(
      "Unhandled error in React tree:",
      expect.any(Error),
      expect.any(String),
    );
  });

  it("catches an error thrown from an effect after a clean first render", () => {
    function ThrowsLater(): JSX.Element {
      const [armed, setArmed] = useState(false);
      if (armed) throw new Error("late boom");
      return (
        <button type="button" onClick={() => setArmed(true)}>
          arm
        </button>
      );
    }

    render(
      <ErrorBoundary fallback={fallback}>
        <ThrowsLater />
      </ErrorBoundary>,
    );

    act(() => {
      screen.getByRole("button", { name: "arm" }).click();
    });

    expect(screen.getByText("caught: late boom")).toBeInTheDocument();
  });
});
