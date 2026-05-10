import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AgentChat from "../AgentChat";
import { useAuth } from "../../contexts/useAuth";

vi.mock("../../contexts/useAuth");

const mockFetchWithAuth = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    fetchWithAuth: mockFetchWithAuth,
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
  it("shows user message and assistant reply on success", async () => {
    mockFetchWithAuth.mockResolvedValueOnce({ reply: "Great question!", model: "llama3.2" });

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
    mockFetchWithAuth.mockResolvedValueOnce({ reply: "Sure!", model: "llama3.2" });

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
    mockFetchWithAuth.mockResolvedValueOnce({ reply: "Got it!", model: "llama3.2" });

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hi" } });
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    });

    await waitFor(() => {
      expect(mockFetchWithAuth).toHaveBeenCalledTimes(1);
    });
  });

  it("does NOT send on Shift+Enter", async () => {
    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hello" } });
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    });

    expect(mockFetchWithAuth).not.toHaveBeenCalled();
  });
});

describe("AgentChat — loading state", () => {
  it("disables the send button while loading", async () => {
    let resolve: (v: unknown) => void;
    mockFetchWithAuth.mockReturnValueOnce(new Promise((r) => { resolve = r; }));

    renderChat();
    const textarea = screen.getByPlaceholderText(/message solverah ai/i);

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Question" } });
      fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    });

    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();

    await act(async () => { resolve!({ reply: "Done", model: "llama3.2" }); });
  });
});

describe("AgentChat — error state", () => {
  it("shows an error banner when the request fails", async () => {
    mockFetchWithAuth.mockRejectedValueOnce(new Error("AI service unavailable"));

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
    mockFetchWithAuth.mockRejectedValueOnce(new Error("Oops"));

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
