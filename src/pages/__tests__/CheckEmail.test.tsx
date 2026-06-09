import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import CheckEmail from "../CheckEmail";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

beforeEach(() => {
  vi.clearAllMocks();
});

function renderCheckEmail(state?: object, search = "") {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/check-email", search, state }]}>
      <CheckEmail />
    </MemoryRouter>
  );
}

describe("CheckEmail - redirect behavior", () => {
  it("redirects to /verify-email with email from location state", () => {
    renderCheckEmail({ email: "user@example.com" });
    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      replace: true,
      state: { email: "user@example.com" },
    });
  });

  it("redirects to /verify-email with email from query param", () => {
    renderCheckEmail(undefined, "?email=user%40example.com");
    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      replace: true,
      state: { email: "user@example.com" },
    });
  });

  it("redirects to /verify-email with empty string when no email provided", () => {
    renderCheckEmail();
    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      replace: true,
      state: { email: "" },
    });
  });

  it("renders nothing — returns null", () => {
    const { container } = renderCheckEmail({ email: "a@b.com" });
    expect(container.firstChild).toBeNull();
  });

  it("prefers location.state.email over query param", () => {
    renderCheckEmail({ email: "state@example.com" }, "?email=query%40example.com");
    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      replace: true,
      state: { email: "state@example.com" },
    });
  });
});
