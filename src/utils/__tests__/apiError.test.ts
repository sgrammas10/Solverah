import {
  ApiError,
  apiErrorFromResponse,
  errorMessage,
  parseApiError,
} from "../apiError";

/**
 * Minimal stand-in for the parts of a Response that parseApiError reads.
 *
 * Plain objects rather than `new Headers(...)`: this project's suite mocks fetch
 * with plain objects throughout, and jsdom does not itself provide the fetch
 * globals -- so depending on them here would couple these tests to an
 * environment detail unrelated to what they verify.
 */
function res(status: number, requestId?: string) {
  return {
    status,
    headers: { get: (name: string) => (name === "X-Request-Id" ? requestId ?? null : null) },
  };
}

describe("parseApiError — RFC 9457 problem+json", () => {
  it("reads `detail`, the most specific field", () => {
    const err = parseApiError(res(422), {
      type: "https://solverah.com/errors/validation",
      title: "Validation failed",
      status: 422,
      detail: "linkedin_url must be an HTTPS linkedin.com URL",
    });

    expect(err.message).toBe("linkedin_url must be an HTTPS linkedin.com URL");
    expect(err.status).toBe(422);
    expect(err.code).toBe("validation");
  });

  it("falls back to `title` when there is no `detail`", () => {
    const err = parseApiError(res(409), {
      type: "https://solverah.com/errors/conflict",
      title: "Conflict",
    });

    expect(err.message).toBe("Conflict");
  });

  it("derives `code` from the problem type URI", () => {
    expect(parseApiError(res(429), { type: "https://solverah.com/errors/rate_limited" }).code)
      .toBe("rate_limited");
  });

  it("falls back to the status for `code` when there is no type", () => {
    expect(parseApiError(res(500), { title: "Internal server error" }).code).toBe("500");
  });

  it("collects field errors", () => {
    const err = parseApiError(res(422), {
      title: "Validation failed",
      errors: [
        { field: "email", code: "invalid" },
        { field: "password", code: "too_short", message: "Use 12+ characters" },
      ],
    });

    expect(err.fieldErrors).toHaveLength(2);
    expect(err.errorFor("password")?.message).toBe("Use 12+ characters");
    expect(err.errorFor("nothing")).toBeUndefined();
  });

  it("drops malformed field errors instead of crashing a form", () => {
    const err = parseApiError(res(422), {
      title: "Validation failed",
      errors: [null, "nope", { code: "missing_field_key" }, { field: "email" }, 42],
    });

    expect(err.fieldErrors).toEqual([{ field: "email" }]);
  });

  it("ignores a non-array `errors` value", () => {
    expect(parseApiError(res(422), { title: "x", errors: "boom" }).fieldErrors).toEqual([]);
  });
});

describe("parseApiError — legacy {error} bodies", () => {
  it("reads the legacy `error` key still returned by app.py handlers", () => {
    expect(parseApiError(res(400), { error: "invalid_or_expired_code" }).message)
      .toBe("invalid_or_expired_code");
  });

  it("reads `message` as an alternative", () => {
    expect(parseApiError(res(400), { message: "Something specific" }).message)
      .toBe("Something specific");
  });
});

describe("parseApiError — precedence", () => {
  it("prefers `detail` over every other key", () => {
    const err = parseApiError(res(422), {
      detail: "the specific reason",
      error: "legacy text",
      message: "other text",
      title: "Generic Title",
    });

    expect(err.message).toBe("the specific reason");
  });

  it("prefers the legacy `error` over the generic `title`", () => {
    // Regression guard: `title` names the CLASS of error, so letting it win
    // would replace "Email already registered" with "Conflict".
    const err = parseApiError(res(409), {
      type: "https://solverah.com/errors/conflict",
      title: "Conflict",
      error: "Email already registered",
    });

    expect(err.message).toBe("Email already registered");
  });

  it("skips blank and whitespace-only values", () => {
    const err = parseApiError(res(400), { detail: "   ", error: "", message: "real message" });

    expect(err.message).toBe("real message");
  });

  it("trims surrounding whitespace", () => {
    expect(parseApiError(res(400), { detail: "  padded  " }).message).toBe("padded");
  });
});

describe("parseApiError — no usable body", () => {
  it("uses the caller's fallback", () => {
    expect(parseApiError(res(500), null, "Login failed").message).toBe("Login failed");
  });

  it("uses a status-derived default when there is no fallback", () => {
    expect(parseApiError(res(429), null).message)
      .toBe("Too many attempts. Please wait a moment and try again.");
    expect(parseApiError(res(401), null).message)
      .toBe("Your session has expired. Please sign in again.");
  });

  it("still produces a message for an unmapped status", () => {
    expect(parseApiError(res(418), null).message).toBe("Something went wrong. Please try again.");
  });

  it("tolerates a non-object body", () => {
    expect(parseApiError(res(500), "<html>502 Bad Gateway</html>", "Upstream failed").message)
      .toBe("Upstream failed");
  });
});

describe("parseApiError — request correlation", () => {
  it("prefers the X-Request-Id header, which is set even on empty bodies", () => {
    const err = parseApiError(res(500, "header-id"), { request_id: "body-id" });

    expect(err.requestId).toBe("header-id");
  });

  it("falls back to request_id in the body", () => {
    expect(parseApiError({ status: 500 }, { request_id: "body-id" }).requestId).toBe("body-id");
  });

  it("is null when neither is present", () => {
    expect(parseApiError(res(500), {}).requestId).toBeNull();
  });
});

describe("ApiError", () => {
  it("is an Error, so existing catch blocks keep working", () => {
    const err = parseApiError(res(404), { title: "Not found" });

    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.name).toBe("ApiError");
  });

  it("classifies client errors", () => {
    expect(parseApiError(res(422), {}).isClientError).toBe(true);
    expect(parseApiError(res(500), {}).isClientError).toBe(false);
  });

  it("classifies retryable failures", () => {
    expect(parseApiError(res(429), {}).isRetryable).toBe(true);
    expect(parseApiError(res(503), {}).isRetryable).toBe(true);
    expect(parseApiError(res(422), {}).isRetryable).toBe(false);
  });
});

describe("apiErrorFromResponse", () => {
  it("reads and parses the body", async () => {
    const response = {
      ...res(404, "abc123"),
      json: async () => ({ type: "https://solverah.com/errors/not_found", title: "Not found" }),
    };

    const err = await apiErrorFromResponse(response);

    expect(err.message).toBe("Not found");
    expect(err.code).toBe("not_found");
    expect(err.requestId).toBe("abc123");
  });

  it("survives an unparseable body", async () => {
    const response = {
      ...res(502),
      json: async () => {
        throw new SyntaxError("Unexpected token < in JSON at position 0");
      },
    };

    const err = await apiErrorFromResponse(response, "Upstream failed");

    expect(err.message).toBe("Upstream failed");
    expect(err.status).toBe(502);
  });
});

describe("errorMessage", () => {
  it("reads an ApiError", () => {
    expect(errorMessage(parseApiError(res(404), { detail: "gone" }))).toBe("gone");
  });

  it("reads a plain Error", () => {
    expect(errorMessage(new Error("network down"))).toBe("network down");
  });

  it("reads a thrown string", () => {
    expect(errorMessage("just a string")).toBe("just a string");
  });

  it("falls back for anything else", () => {
    expect(errorMessage(undefined)).toBe("Something went wrong. Please try again.");
    expect(errorMessage({}, "custom")).toBe("custom");
    expect(errorMessage(new Error(""), "custom")).toBe("custom");
  });
});
