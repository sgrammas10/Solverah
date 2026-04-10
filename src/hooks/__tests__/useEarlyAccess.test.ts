import { renderHook, act } from "@testing-library/react";
import { useEarlyAccess } from "../useEarlyAccess";

const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

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

  it("does not call fetch when validation fails", async () => {
    const { result } = renderHook(() => useEarlyAccess());
    await act(async () => { await result.current.handleSubmit(); });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("useEarlyAccess - successful submission", () => {
  it("closes modal and sets success flag on 200", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.setIsOpen(true);
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("lastName", "Lovelace");
      result.current.handleChange("email", "ada@example.com");
    });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.isOpen).toBe(false);
    expect(result.current.isSuccess).toBe(true);
  });

  it("resets form fields after successful submit", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("lastName", "Lovelace");
      result.current.handleChange("email", "ada@example.com");
      result.current.handleChange("phone", "555-1234");
    });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.formData.firstName).toBe("");
    expect(result.current.formData.email).toBe("");
    expect(result.current.formData.phone).toBe("");
    expect(result.current.formData.preferredContact).toBe("email");
  });

  it("is not submitting after successful request", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("lastName", "Lovelace");
      result.current.handleChange("email", "ada@example.com");
    });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.isSubmitting).toBe(false);
  });
});

describe("useEarlyAccess - API error handling", () => {
  it("sets error message from API response body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ error: "Server unavailable" }),
    });
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("lastName", "Lovelace");
      result.current.handleChange("email", "ada@example.com");
    });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Server unavailable");
    expect(result.current.isSuccess).toBe(false);
  });

  it("sets fallback error when API returns no error field", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({}),
    });
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("lastName", "Lovelace");
      result.current.handleChange("email", "ada@example.com");
    });
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.error).toBe("Could not send request. Please try again.");
  });

  it("sets fallback error on network failure", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));
    const { result } = renderHook(() => useEarlyAccess());
    act(() => {
      result.current.handleChange("firstName", "Ada");
      result.current.handleChange("lastName", "Lovelace");
      result.current.handleChange("email", "ada@example.com");
    });
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
