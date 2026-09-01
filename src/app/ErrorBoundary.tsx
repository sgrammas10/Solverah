/**
 * ErrorBoundary.tsx — the catch mechanism, with no opinion about what to draw.
 *
 * React has exactly one way to stop a render-phase throw from unmounting the
 * whole tree, and it is a class component with `getDerivedStateFromError`.
 * There is no hook equivalent. So this file holds the class, and the two
 * *policies* built on it live next door in `AppErrorBoundary` (root, full page)
 * and `RouteErrorBoundary` (per route, inside the shell). Splitting mechanism
 * from policy is what lets both share one tested implementation.
 *
 * `resetKeys` is the part that matters for routing. A boundary that has caught
 * stays caught until something tells it otherwise, so without this a broken
 * screen would poison every subsequent navigation: the user clicks a working
 * link in the Header, React Router changes `location`, and the boundary — which
 * knows nothing about routing — keeps rendering the old error. Passing the
 * pathname as a reset key ties "we navigated" to "clear the error", which is
 * the whole reason navigation survives a broken route.
 *
 * `onReset` exists for TanStack Query. A boundary-caught query error leaves the
 * query itself in an error state, so clearing only this component's state would
 * re-render the consumer, re-read the still-failed query, and throw again
 * immediately — a retry button that cannot ever work. `QueryErrorResetBoundary`
 * supplies the function that clears the query, and it is wired in through here.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

export interface ErrorBoundaryProps {
  children: ReactNode;
  /**
   * Rendered in place of `children` once a descendant throws.
   *
   * Receives the error and a `reset` callback. Calling `reset` clears the
   * caught error and re-renders `children`, which is only useful if whatever
   * caused the throw has plausibly changed — hence `onReset`.
   */
  fallback: (error: Error, reset: () => void) => ReactNode;
  /**
   * Clear the caught error whenever any of these values changes.
   *
   * Compared shallowly, in order. Length changes count as a change.
   */
  resetKeys?: readonly unknown[];
  /** Run just before the error is cleared, by `reset` or by `resetKeys`. */
  onReset?: () => void;
  /** Reporting hook. Called from `componentDidCatch` with React's stack info. */
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** Shallow, order-sensitive comparison of two reset-key lists. */
function keysChanged(prev: readonly unknown[], next: readonly unknown[]): boolean {
  if (prev.length !== next.length) return true;
  return prev.some((value, i) => !Object.is(value, next[i]));
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept unconditional. This is the only record that a screen died: the
    // fallback below deliberately does not print the message at the user, so
    // without this the failure would be invisible in the console too.
    console.error("Unhandled error in React tree:", error, info.componentStack);
    this.props.onError?.(error, info);
  }

  componentDidUpdate(prev: ErrorBoundaryProps) {
    if (this.state.error === null) return;
    const before = prev.resetKeys ?? [];
    const after = this.props.resetKeys ?? [];
    if (keysChanged(before, after)) {
      this.reset();
    }
  }

  reset = () => {
    // `onReset` first: it is what clears the *cause* (the failed query), and
    // running it after setState would let the re-render read the stale failure.
    this.props.onReset?.();
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (error !== null) {
      return this.props.fallback(error, this.reset);
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
