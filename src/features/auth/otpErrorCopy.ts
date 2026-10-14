/**
 * otpErrorCopy.ts — user-facing wording for a rejected one-time code (G8).
 *
 * The two OTP endpoints answer a bad code with the legacy `{ "error": "..." }`
 * body, and the string in it is terse by design: `invalid code`, `code
 * expired`, `invalid_or_expired_code`. Those strings are the machine-readable
 * codes -- the body has no other field to carry one, the contract baseline
 * records `{"error":"invalid code"}` byte-for-byte, and the server names them
 * as constants (`auth_service.CONFIRM_INVALID_CODE` and siblings) so a reword
 * there is a deliberate wire change. Until this file the verify-email screen
 * printed them raw.
 *
 * Keyed on the exact string, never on a regex over the prose, so a server
 * message this table does not know falls through to whatever `parseApiError`
 * chose -- a 429's "Too many attempts" must stay a 429 message rather than be
 * mistaken for a wrong code.
 */
import { ApiError } from "../../shared/api/apiError";

/** Server `error` string -> what the person reads. Best-guess copy; Julie revises. */
export const OTP_ERROR_COPY: Readonly<Record<string, string>> = {
  "invalid code":
    "That code didn't match. Check the six digits and try again, or request a new code below.",
  "code expired":
    "That code has expired. Request a new one below and we'll send it right away.",
  invalid_or_expired_code:
    "That code is invalid or has expired. Request a new one below and try again.",
  "email and code are required": "Please enter the 6-digit code from your email.",
};

/**
 * Message to show for a failed OTP request.
 *
 * An {@link ApiError} whose message is one of the known codes gets the friendly
 * copy; any other ApiError keeps the message `parseApiError` picked, which is
 * already the most specific text the server sent. Anything that is not an
 * ApiError never reached the server (a dropped connection, an abort), so the
 * caller's network fallback is the honest message -- not `TypeError: Failed
 * to fetch`.
 */
export function otpErrorMessage(error: unknown, networkFallback: string): string {
  if (error instanceof ApiError) {
    return OTP_ERROR_COPY[error.message] ?? (error.message || networkFallback);
  }
  return networkFallback;
}
