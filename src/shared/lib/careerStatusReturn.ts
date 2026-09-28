/**
 * careerStatusReturn — where to offer to send a user after they set their
 * career status.
 *
 * Path Intelligence and the Situation Report both send a user to
 * `/job-seeker/profile?tab=experience` with `showCareerStatusModal` in router
 * state. They also put a `returnTo` there, so once the status is saved the
 * profile page can ask "Go back to <label>?" instead of dumping the user
 * somewhere they never asked to go.
 *
 * Router state is client-forgeable (history.pushState can plant any value), so
 * `readCareerStatusReturnTo` accepts only an in-app absolute path -- starts
 * with "/" but not "//" or "/\", which browsers treat as another host -- and a
 * short string label. Anything else reads as "no returnTo".
 */

export interface CareerStatusReturnTo {
  /** In-app path, including any query string. */
  path: string;
  /** Human name of the page, e.g. "Path Intelligence". */
  label: string;
}

export interface CareerStatusNavState {
  showCareerStatusModal: true;
  returnTo: CareerStatusReturnTo;
}

const MAX_LABEL = 80;

export function careerStatusNavState(path: string, label: string): CareerStatusNavState {
  return { showCareerStatusModal: true, returnTo: { path, label } };
}

export function readCareerStatusReturnTo(state: unknown): CareerStatusReturnTo | null {
  if (typeof state !== "object" || state === null) return null;
  const returnTo = (state as { returnTo?: unknown }).returnTo;
  if (typeof returnTo !== "object" || returnTo === null) return null;
  const { path, label } = returnTo as { path?: unknown; label?: unknown };
  if (typeof path !== "string" || !/^\/(?![/\\])/.test(path)) return null;
  if (typeof label !== "string" || !label.trim() || label.length > MAX_LABEL) return null;
  return { path, label: label.trim() };
}
