/**
 * useManagerPlaybook.test.ts -- the two 409-code predicates `isNoManagerMatch`
 * and `isNoManagerProfile` (added for USER_SCENARIOS S14.1's client-side
 * gate on ManagerProfilePage). Each must read only its own field+code pair --
 * a bare `Error` or the other predicate's code must not trip it, per this
 * file's own header on why `errorFor(...)?.code` is what call sites branch
 * on rather than the message text.
 */
import { ApiError } from "../../shared/api/apiError";
import { isNoManagerMatch, isNoManagerProfile } from "./useManagerPlaybook";

function noManagerMatchError() {
  return new ApiError("Take ManagerMatch first", {
    status: 409,
    fieldErrors: [{ field: "manager_match", code: "no_manager_match" }],
  });
}

function noManagerProfileError() {
  return new ApiError("Profile your manager first", {
    status: 409,
    fieldErrors: [{ field: "manager_profile", code: "no_manager_profile" }],
  });
}

describe("isNoManagerMatch", () => {
  it("is true for the no_manager_match 409", () => {
    expect(isNoManagerMatch(noManagerMatchError())).toBe(true);
  });

  it("is false for the no_manager_profile 409", () => {
    expect(isNoManagerMatch(noManagerProfileError())).toBe(false);
  });

  it("is false for a non-ApiError", () => {
    expect(isNoManagerMatch(new Error("no_manager_match"))).toBe(false);
  });

  it("is false for undefined", () => {
    expect(isNoManagerMatch(undefined)).toBe(false);
  });
});

describe("isNoManagerProfile", () => {
  it("is true for the no_manager_profile 409", () => {
    expect(isNoManagerProfile(noManagerProfileError())).toBe(true);
  });

  it("is false for the no_manager_match 409", () => {
    expect(isNoManagerProfile(noManagerMatchError())).toBe(false);
  });

  it("is false for a non-ApiError", () => {
    expect(isNoManagerProfile(new Error("no_manager_profile"))).toBe(false);
  });

  it("is false for undefined", () => {
    expect(isNoManagerProfile(undefined)).toBe(false);
  });
});
