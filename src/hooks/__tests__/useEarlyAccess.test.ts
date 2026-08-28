import { renderHook, act } from "@testing-library/react";
import { HttpResponse } from "msw";

import { useEarlyAccess } from "../useEarlyAccess";
import { mock } from "../../../tests/msw/contract";
import { server, useApiMocks, recordRequests } from "../../../tests/msw/server";

/**
 * These tests used to assign a `vi.fn()` over `globalThis.fetch` and hand back
 * bare `{ ok: true }` objects. Two things were wrong with that. The stub
 * answered every URL identically, so nothing here checked that the hook posts
 * to `/intake/early-access` rather than to some other endpoint; and `{ ok: true }`
 * is not a `Response`, so these tests could not have caught the hook calling any
 * method the real object has.
 *
 * The handlers are contract-typed -- see tests/msw/contract.ts -- and unhandled
 * requests are errors, so a call to the wrong path now fails the test that made
 * it rather than being answered anyway.
 */
useApiMocks();
const { requests } = recordRequests();

/** The path the hook is supposed to post to, as `recordRequests` formats it. */
const EARLY_ACCESS = "POST /api/v1/intake/early-access";

/** Fill the three fields `handleSubmit` requires before it will send anything. */
function fillRequired(result: { current: ReturnType<typeof useEarlyAccess> }) {
  act(() => {
    result.current.handleChange("firstName", "Ada");
    result.current.handleChange("lastName", "Lovelace");
    result.current.handleChange("email", "ada@example.com");
  });
}

describe("useEarlyAccess - handleSubmit validation", () => {
  it("sets error when firstName is missing", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Please fill out all required fields.");
  });

  it("sets error when lastName is missing", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    act(() => { result.current.handleChange("firstName", "Ada"); });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Please fill out all required fields.");
  });

  it("sets error when email is missing", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("lastName", "Lovelace");
    });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Please fill out all required fields.");
  });

  it("sets error when all required fields are whitespace only", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "   ");
      result.current.handleChange("lastName", "   ");
      result.current.handleChange("email", "   ");
    });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Please fill out all required fields.");
  });

  it("issues no request when validation fails", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    await act(async () => { await result.current.handleSubmit(); });
    expect(requests).toEqual([]);
  });
});

describe("useEarlyAccess - successful submission", () => {
  it("closes modal and sets success flag on 200", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    act(() => { result.current.setIsOpen(true); });
    fillRequired(result);
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.isOpen).toBe(false);
    expect(result.current.isSuccess).toBe(true);
  });

  it("posts the trimmed form to the early-access endpoint", async () => {
    // Not assertable before this file moved to MSW: the old stub recorded a
    // call to a function, so which URL was hit went unchecked.
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/intake/early-access").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ok: true });
      }),
    );

    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "  Ada  ");
      result.current.handleChange("lastName", "  Lovelace  ");
      result.current.handleChange("email", "  ada@example.com  ");
      result.current.handleChange("phone", " 555-1234 ");
    });
    await act(async () => { await result.current.handleSubmit(); });

    expect(requests).toEqual([EARLY_ACCESS]);
    expect(sent).toMatchObject({
      firstName: "Ada",
      lastName: "Lovelace",
      email: "ada@example.com",
      phone: "555-1234",
      preferredContact: "email",
    });
  });

  it("resets form fields after successful submit", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    fillRequired(result);
    act(() => { result.current.handleChange("phone", "555-1234"); });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.formData.firstName).toBe("");
    expect(result.current.formData.email).toBe("");
    expect(result.current.formData.phone).toBe("");
    expect(result.current.formData.preferredContact).toBe("email");
  });

  it("is not submitting after successful request", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    fillRequired(result);
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.isSubmitting).toBe(false);
  });
});

describe("useEarlyAccess - API error handling", () => {
  it("sets error message from API response body", async () => {
    server.use(
      mock("post", "/api/v1/intake/early-access").reply(400, { error: "Server unavailable" }),
    );
    const { result } = renderHook(() => useEarlyAccess());
    fillRequired(result);
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Server unavailable");
    expect(result.current.isSuccess).toBe(false);
  });

  it("sets fallback error when API returns no error field", async () => {
    // `.resolve` rather than `.reply`, deliberately: the contract's 400 body is
    // `LegacyError`, which *requires* `error`, so this body is one the API is
    // not supposed to be able to send and `.reply` would refuse to compile it.
    // The fallback exists for exactly that case -- a proxy or a truncated
    // response -- so the test has to be able to describe a body off the
    // contract in order to cover it.
    server.use(
      mock("post", "/api/v1/intake/early-access").resolve(() =>
        HttpResponse.json({}, { status: 400 }),
      ),
    );
    const { result } = renderHook(() => useEarlyAccess());
    fillRequired(result);
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Could not send request. Please try again.");
  });

  it("sets fallback error on network failure", async () => {
    server.use(
      mock("post", "/api/v1/intake/early-access").resolve(() => HttpResponse.error()),
    );
    const { result } = renderHook(() => useEarlyAccess());
    fillRequired(result);
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Could not send request. Please try again.");
    expect(result.current.isSubmitting).toBe(false);
  });
});

describe("useEarlyAccess - handleChange", () => {
  it("updates the specified field", () => {
    const { result } = renderHook(() => useEarlyAccess());
    act(() => { result.current.handleChange("email", "test@example.com"); });
    expect(result.current.formData.email).toBe("test@example.com");
  });

  it("does not affect other fields", () => {
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("email", "ada@test.com");
    });
    expect(result.current.formData.firstName).toBe("Ada");
    expect(result.current.formData.lastName).toBe("");
  });
});
