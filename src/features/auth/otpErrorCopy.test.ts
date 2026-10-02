import { ApiError, parseApiError } from "../../shared/api/apiError";
import { OTP_ERROR_COPY, otpErrorMessage } from "./otpErrorCopy";

const NETWORK = "Network error. Please try again.";

/** The three strings the server pins (auth_service.CONFIRM_* / RESET_*). */
const WIRE = ["invalid code", "code expired", "invalid_or_expired_code"];

describe("otpErrorMessage", () => {
  it.each(WIRE)("maps the wire string %j to copy that never repeats it", (wire) => {
    const err = parseApiError({ status: 400 }, { error: wire });
    const shown = otpErrorMessage(err, NETWORK);
    expect(shown).toBe(OTP_ERROR_COPY[wire]);
    expect(shown).not.toBe(wire);
    // Friendly copy reads as a sentence, not a slug.
    expect(shown).toMatch(/^[A-Z].*[.!]$/);
    expect(shown).not.toMatch(/_/);
  });

  it("leaves an unknown server message alone (a 429 is not a wrong code)", () => {
    const err = parseApiError({ status: 429 }, { detail: "Too many attempts. Wait a minute." });
    expect(otpErrorMessage(err, NETWORK)).toBe("Too many attempts. Wait a minute.");
  });

  it("uses the network fallback for anything that never reached the server", () => {
    expect(otpErrorMessage(new TypeError("Failed to fetch"), NETWORK)).toBe(NETWORK);
    expect(otpErrorMessage(undefined, NETWORK)).toBe(NETWORK);
    expect(otpErrorMessage("nope", NETWORK)).toBe(NETWORK);
  });

  it("falls back when an ApiError somehow carries an empty message", () => {
    expect(otpErrorMessage(new ApiError("", { status: 400 }), NETWORK)).toBe(NETWORK);
  });
});
