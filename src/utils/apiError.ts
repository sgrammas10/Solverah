/**
 * apiError.ts — one place that knows how the API reports a failure.
 *
 * The backend emits two error shapes right now, and will do so until the Phase 1
 * API restructure normalises them (docs/ARCHITECTURE.md):
 *
 *   1. RFC 9457 Problem Details, from the handlers registered in
 *      `solverah/errors.py`. This covers every framework failure — 404, 405,
 *      413, 429, 500 — and everything raised as an `ApiError` server-side:
 *
 *        { "type": "https://solverah.com/errors/validation",
 *          "title": "Validation failed", "status": 422,
 *          "detail": "linkedin_url must be an HTTPS linkedin.com URL",
 *          "request_id": "4f3c…",
 *          "errors": [{ "field": "linkedin_url", "code": "invalid_url" }] }
 *
 *   2. The legacy `{ "error": "..." }` body that the 38 route handlers in
 *      `app.py` still return directly.
 *
 * Every call site in this app reads `data?.error`, which is blind to shape 1.
 * The consequence is that a real, specific message — "The requested URL was not
 * found", "Too many requests" — is present in the response and thrown away, and
 * the user is shown a generic fallback instead.
 *
 * `parseApiError` reads both, preferring the most specific text available, and
 * carries the `request_id` through so a user reporting a problem can quote
 * something that resolves to an exact server log line.
 */

/** RFC 9457 problem document, as emitted by `solverah/errors.py`. */
export interface ProblemDetail {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  request_id?: string;
  errors?: FieldError[];
}

/** A single field-level validation failure. */
export interface FieldError {
  field: string;
  code?: string;
  message?: string;
}

/** Legacy shape still returned by the handlers in `app.py`. */
interface LegacyErrorBody {
  error?: string;
  message?: string;
}

type ErrorBody = ProblemDetail & LegacyErrorBody;

/**
 * An API failure with the server's own diagnostics attached.
 *
 * Extends `Error`, so existing `catch (e) { e.message }` call sites keep working
 * unchanged — they simply start showing a better message.
 */
export class ApiError extends Error {
  /** HTTP status code. 0 when the request never reached the server. */
  readonly status: number;
  /** Short slug from the problem `type` URI, e.g. `validation`, `rate_limited`. */
  readonly code: string;
  /** Field-level failures, empty when the server sent none. */
  readonly fieldErrors: FieldError[];
  /** Correlation id — quote this in a bug report to find the server-side trace. */
  readonly requestId: string | null;

  constructor(
    message: string,
    options: {
      status?: number;
      code?: string;
      fieldErrors?: FieldError[];
      requestId?: string | null;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status ?? 0;
    this.code = options.code ?? "unknown";
    this.fieldErrors = options.fieldErrors ?? [];
    this.requestId = options.requestId ?? null;

    // Guards `instanceof ApiError` against a downlevelled build. The project
    // targets ES2020, where subclassing Error preserves the prototype chain on
    // its own, but a transpiler stepping below ES6 silently breaks it -- and the
    // failure mode is a caught error quietly taking the wrong branch.
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  /** True when the caller can fix this by changing input (4xx). */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }

  /** True when retrying later is reasonable (429, 5xx, or a network failure). */
  get isRetryable(): boolean {
    return this.status === 429 || this.status >= 500 || this.status === 0;
  }

  /** Message for `field`, if the server reported one. */
  errorFor(field: string): FieldError | undefined {
    return this.fieldErrors.find((e) => e.field === field);
  }
}

/** Fallbacks for statuses where neither body shape carried usable text. */
const STATUS_FALLBACKS: Record<number, string> = {
  400: "That request could not be processed.",
  401: "Your session has expired. Please sign in again.",
  403: "You do not have access to that.",
  404: "That could not be found.",
  409: "That conflicts with something that already exists.",
  413: "That file or request is too large.",
  422: "Please check the highlighted fields and try again.",
  429: "Too many attempts. Please wait a moment and try again.",
  500: "Something went wrong on our end. Please try again.",
  502: "We could not reach a service we depend on. Please try again.",
  503: "The service is temporarily unavailable. Please try again shortly.",
  504: "That took too long. Please try again.",
};

/** Extract the slug from a problem `type` URI: `…/errors/validation` -> `validation`. */
function codeFromType(type: string | undefined): string | undefined {
  if (!type) return undefined;
  const slug = type.split("/").pop();
  return slug && slug.length > 0 ? slug : undefined;
}

/**
 * Pick the most useful message from an error body.
 *
 * Order is deliberate — most specific first:
 *   1. `detail`  — problem+json, describes this exact failure
 *   2. `error`   — legacy body, written per-handler and usually specific
 *   3. `message` — legacy alternative
 *   4. `title`   — problem+json, but generic ("Validation failed")
 *   5. the caller's fallback, then a status-derived default
 *
 * `title` sits below the legacy keys on purpose: it names the *class* of error,
 * so preferring it would replace "Email already registered" with "Conflict".
 */
function messageFrom(body: ErrorBody | null, fallback?: string, status?: number): string {
  const candidates = [body?.detail, body?.error, body?.message, body?.title];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim().length > 0) {
      return candidate.trim();
    }
  }
  if (fallback) return fallback;
  if (status && STATUS_FALLBACKS[status]) return STATUS_FALLBACKS[status];
  return "Something went wrong. Please try again.";
}

/** Keep only well-formed field errors; a malformed one must not crash a form. */
function normalizeFieldErrors(raw: unknown): FieldError[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    if (!entry || typeof entry !== "object") return [];
    const { field, code, message } = entry as Record<string, unknown>;
    if (typeof field !== "string" || field.length === 0) return [];
    return [{
      field,
      ...(typeof code === "string" ? { code } : {}),
      ...(typeof message === "string" ? { message } : {}),
    }];
  });
}

/**
 * The minimum a response must expose to be turned into an {@link ApiError}.
 *
 * Deliberately structural rather than `Response`: a real `Response` satisfies
 * it, and so does a plain object, so this stays testable without depending on
 * DOM fetch globals being present in the test environment.
 */
export interface ErrorResponseLike {
  status: number;
  headers?: { get(name: string): string | null };
}

/**
 * Build an {@link ApiError} from a failed response and its parsed body.
 *
 * @param response  The failed response. Supplies the status and the
 *                  `X-Request-Id` header, which is present even when the body
 *                  is empty or unparseable.
 * @param body      The parsed JSON body, or `null` if parsing failed.
 * @param fallback  Call-site-specific wording used only when the server sent
 *                  nothing usable.
 */
export function parseApiError(
  response: ErrorResponseLike,
  body: unknown,
  fallback?: string,
): ApiError {
  const problem = (body && typeof body === "object" ? body : null) as ErrorBody | null;
  const status = response.status ?? 0;

  return new ApiError(messageFrom(problem, fallback, status), {
    status,
    code: codeFromType(problem?.type) ?? String(status),
    fieldErrors: normalizeFieldErrors(problem?.errors),
    // The header is the more reliable source: it is set on every response by
    // `install_request_logging`, including ones with no body at all.
    requestId: response.headers?.get("X-Request-Id") ?? problem?.request_id ?? null,
  });
}

/**
 * Read a failed response and build an {@link ApiError} from it.
 *
 * Consumes the body, so call it only on a response you have already decided is
 * an error and will not read again.
 */
export async function apiErrorFromResponse(
  response: ErrorResponseLike & { json(): Promise<unknown> },
  fallback?: string,
): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  return parseApiError(response, body, fallback);
}

/**
 * Message for any thrown value — API error, network failure, or anything else.
 *
 * For display in a `catch` block, where the thrown value is typed `unknown` and
 * may not be an `Error` at all.
 */
export function errorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error.trim()) return error.trim();
  return fallback;
}
