import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AgentChat from "../AgentChat";
import { useAuth } from "../../contexts/useAuth";

vi.mock("../../contexts/useAuth");

const mockStreamFetch = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    streamFetch: mockStreamFetch,
    fetchWithAuth: vi.fn(),
    user: { id: 1, email: "test@example.com", name: "Test User", role: "job-seeker" },
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    fetchProfile: vi.fn(),
    fetchProfileData: vi.fn(),
    saveProfileData: vi.fn(),
    updateProfile: vi.fn(),
    updateProfileData: vi.fn(),
  } as any);
});

/** Build a mock Response that streams SSE chunks then a done event. */
function makeSseResponse(chunks: string[], model = "llama3"): Response {
  const parts = chunks.map((c) => `data: ${JSON.stringify({ chunk: c })}\n\n`);
  parts.push(`data: ${JSON.stringify({ done: true, model })}\n\n`);
  const sseText = parts.join("");
  const bytes = new TextEncoder().encode(sseText);

  const mockReader = {
    read: vi.fn()
      .mockResolvedValueOnce({ done: false, value: bytes })
      .mockResolvedValue({ done: true, value: undefined }),
    releaseLock: vi.fn(),
  };

  return {
    ok: true,
    status: 200,
    body: { getReader: () => mockReader },
    json: vi.fn(),
  } as unknown as Response;
}

function renderChat() {
  return render(
    <MemoryRouter>
      <AgentChat />
    </MemoryRouter>
  );
}

describe("AgentChat — empty state", () => {
  it("renders heading and empty state prompt", () => {
    renderChat();
    expect(screen.getByText("Solverah AI")).toBeInTheDocument();
    expect(screen.getByText(/ask me anything/i)).toBeInTheDocument();
  });

  it("disables send button when input is empty", () => {
    renderChat();
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });
});

describe("AgentChat — sending a message", () => {
  it("shows user message and streamed assistant reply on success", async () => {
    mockStreamFetch.mockResolvedValueOnce(makeSseResponse(["Great ", "question!"]));

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "What should I study?" } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    });

    await waitFor(() => {
      expect(screen.getByText("What should I study?")).toBeInTheDocument();
      expect(screen.getByText("Great question!")).toBeInTheDocument();
    });
  });

  it("clears the input after submitting", async () => {
    mockStreamFetch.mockResolvedValueOnce(makeSseResponse(["Sure!"]));

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hello" } });
      fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    });

    await waitFor(() => {
      expect(textarea).toHaveValue("");
    });
  });

  it("sends on Enter key (not Shift+Enter)", async () => {
    mockStreamFetch.mockResolvedValueOnce(makeSseResponse(["Got it!"]));

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hi" } });
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    });

    await waitFor(() => {
      expect(mockStreamFetch).toHaveBeenCalledTimes(1);
    });
  });

  it("does NOT send on Shift+Enter", async () => {
    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hello" } });
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    });

    expect(mockStreamFetch).not.toHaveBeenCalled();
  });
});

describe("AgentChat — loading state", () => {
  it("disables the send button while loading", async () => {
    let resolveStream!: (v: Response) => void;
    mockStreamFetch.mockReturnValueOnce(new Promise<Response>((r) => { resolveStream = r; }));

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Question" } });
      fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    });

    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();

    await act(async () => { resolveStream(makeSseResponse(["Done"])); });
  });
});

describe("AgentChat — error state", () => {
  it("shows an error banner when the request fails", async () => {
    mockStreamFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: vi.fn().mockResolvedValue({ error: "AI service unavailable" }),
    } as any);

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hi" } });
      fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/AI service unavailable/i)).toBeInTheDocument();
    });
  });

  it("dismisses the error banner on click", async () => {
    mockStreamFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: vi.fn().mockResolvedValue({ error: "Oops" }),
    } as any);

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hi" } });
      fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    });

    await waitFor(() => screen.getByText("Dismiss"));
    await act(async () => { fireEvent.click(screen.getByText("Dismiss")); });

    expect(screen.queryByText("Dismiss")).not.toBeInTheDocument();
  });
});
